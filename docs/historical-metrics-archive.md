# Step 7.04 Historical Metrics Archive / 历史指标归档

Step 7.03 extension under review: [CPU frequency design](cpu-frequency.md).
The compatible writer accepts v1/v2 but never auto-migrates. Beszel tables stay
unchanged; an explicit backed-up migration adds frequency history on the same HDD.
V1 remains supported. / 7.03 扩展需显式备份迁移，不自动升级，不改变 Beszel 原始表。

> **Status context / 阶段说明 (reviewed 2026-10-19):** Step 7.04 code was merged into `main` via [PR #9](https://github.com/hhb-coding/homelab-portal/pull/9) on 2026-10-12. The Phase B “not deployed” statements below are an **accurate historical description of that development phase**, not a claim that the HP host is still undeployed. Later operator checks reported an enabled archive timer and successful initial collection; continued production health, the current running checkout, and archive counts require fresh read-only verification on HP. Existing Portal historical charts continue querying Beszel; archive-backed charts are planned for Step 7.06.
>
> **状态说明：**Phase B“未部署”是历史阶段记录。之后用户曾核验计时器与首次采集，但本仓库不能直接证明如今 HP 的实时运行状态。Step 7.04 源码已合并，Step 7.06 历史页面仍待开发。


## Status / 状态

Phase B implements an independent collector, SQLite schema, HDD guard, timer
templates and isolated tests. It has **not** been deployed or run against the
production HDD. The existing `/api/history` and charts still read Beszel directly.
No service or timer has been installed, enabled or restarted.

Phase B 已实现独立采集器、SQLite 结构、HDD 保护、timer 模板及隔离测试。
尚未部署，也未在正式 HDD 上运行。现有 `/api/history` 和图表仍直接读取 Beszel。
未安装、启用或重启任何服务或 timer。

## Collection contract / 采集约定

- Schedule: every five minutes via `OnCalendar=*:0/5`, with `Persistent=true`
  for one catch-up activation after downtime. A running oneshot is not started
  twice; `flock` also prevents concurrent manual writers. Initial backlog runs
  have a 15-minute service timeout and resume from committed pages next time.
  Calendar activations during an active run are skipped, not queued; the 15-second
  accuracy window means starts need not occur at the exact boundary.
  / 每五分钟执行；停机后补一次触发，不逐次重放。单服务与文件锁防止并发写入；
  首次补采超时后，下次从已提交页面恢复。运行期间的触发会跳过，不排队；
  15 秒精度窗口意味着启动时间不保证恰好落在五分钟边界。
- Source: authenticated `system_stats`, `type='1m'`, for every system visible
  to the existing Beszel account, including offline systems with remaining data.
  The existing client lists up to 200 systems, sufficient for the ten-device target.
  No upstream records or configuration are changed. / 仅归档当前账号可见设备的
  一分钟原始数据，包括离线设备尚存的数据；设备列表最多 200 台，覆盖 10 台目标。
  不修改上游记录或配置。
- Authentication reuses this installation's `config.py` and `.env`/environment.
  Token takes precedence over password authentication. The runner never loads
  another installation's production config automatically. Errors report only
  exception classes or aggregate counters, never HTTP bodies or credentials.
  / 复用当前安装的认证配置，Token 优先；不会自动加载其他安装目录配置。
  错误只输出类别或计数，不输出响应正文、密码或 Token。
- Fixed UTC run upper bound; a new device starts at `now - 180 days`. Established
  devices start at the last committed sample minus ten minutes, clamped to the
  retention cutoff. This catches bounded late arrivals and makes retries safe.
  Empty results do not advance checkpoints. No values or missing minutes are
  fabricated. / 固定本轮 UTC 上界；首次回溯 180 天，后续从最后样本前 10 分钟
  重叠补采；空结果不推进断点，不插值，不生成缺失分钟。
- Pages use `sort=created,id`, `perPage=200`, a bounded time filter and a strict
  `(created,id)` continuation filter. Each request uses `page=1` within its cursor
  range, rather than offset paging a changing collection. Continue until an empty
  page, even if the server returned a short page. Unexpected, unordered, repeated,
  wrong-system or non-JSON-compatible records fail that device's page.
  / 使用时间与 ID 联合游标分页，每次查询游标之后的第一页，直到空页；
  短页不会提前终止，异常结构、乱序、重复页面或设备不匹配时拒绝当前页。
- Samples and checkpoint are committed atomically per page. A failed device
  increments `failed`; other devices continue. The runner returns nonzero for
  partial failure, allowing systemd to show failure and retry at the next schedule.
  / 每页样本与断点原子提交；单台失败不阻止其他设备，部分失败返回非零退出码。

## Storage and retention / 存储与保留

Default file: `/srv/data/homelab-portal-archive/metrics.sqlite3`, independent of
Portal's registry and Beszel's own databases. The command refuses an existing
unrecognized database, including Portal's registry. Schema version is 1.

默认文件独立于 Portal 注册库和 Beszel 数据库；拒绝已有的不兼容数据库，
包括误指定的 Portal 注册库。结构版本为 1。

`samples` stores `system_id`, `record_id`, normalized `created_utc`, original
`created_raw`, `updated_raw`, complete `stats_json` and `archived_utc`. Primary
key `(system_id,record_id)` deduplicates immutable samples. Indexes cover device
time queries and retention. `checkpoints` stores each system's greatest committed
timestamp. The archive uses stable Beszel IDs; Portal device mappings remain in
the existing registry and can be joined by readers without copying or altering it.

完整保存 `stats`，包括零值、null、未知字段、`efs`、温度、GPU、网络及 I/O；
不丢弃字段、不提前统一单位。归一化 UTC 时间便于查询，原始毫秒时间戳同时保存。
使用 Beszel ID 作为稳定设备键；Portal 映射仍由现有注册库维护，未来读取层可以关联。

Rows strictly older than the UTC 180-day cutoff are deleted after a collection
pass. A total failure listing systems skips pruning; per-device failures still
allow retention pruning. Checkpoints remain for returning devices. WAL, FULL
synchronization and a ten-second busy timeout protect committed pages. Retention
deletion frees pages for reuse; no automatic VACUUM or daily shrinking is performed.

每轮删除严格早于 180 天边界的样本；设备列表整体失败时不清理，单台失败仍执行保留
策略。保留断点以支持恢复。WAL、FULL 同步与 10 秒锁等待保护已提交数据。
删除释放页面供后续复用，不自动 VACUUM，不承诺文件每日缩小。

Ten devices × 1,440 samples/day × 180 days = **2,592,000 records**. At a measured
average JSON size of 1–4 KiB, payload alone would be about 2.5–9.9 GiB, plus SQLite
rows, indexes, WAL and backup space. This is a sizing estimate, not a benchmark;
GPU/network/filesystem cardinality can increase payload size. Validate actual
bytes per row, disk headroom, pruning duration and read latency before rollout.

10 台设备 180 天约 259.2 万条。若实际测得每条 JSON 为 1–4 KiB，单纯载荷约
2.5–9.9 GiB，另需数据库结构、索引、WAL 和备份空间。这是容量估算，未完成规模
性能验收；设备扩展指标可能增加体积。部署前需测量实际单条大小、清理耗时及查询延迟。

## HDD protection / HDD 保护

Before creating the directory or opening SQLite, `findmnt --json` must show:

- exact mount target `/srv/data`;
- UUID equal to the privately configured `METRICS_ARCHIVE_UUID` (required);
- ext4 and `rw`;
- resolved database path and nearest existing parent on that same mount.

Missing mounts, SSD fallback, nested mounts, read-only mounts and symlink escapes
fail closed. Blank or invalid UUID configuration fails before any directory or
database creation. No real installation UUID is distributed with the code.
The guard is rechecked after acquiring the lock and before each page
commit and retention deletion. The runner has no CLI bypass. `UMask=0077` protects
new files and new directories default to `0700`. Only the collector user needs write
access. Operators must not unmount or replace the filesystem while the collector
is running: repeated checks reduce risk but cannot eliminate an unmount race.
All symlink path components, database/lock/WAL/SHM/journal symlinks and hardlinks
are rejected; existing files must belong to the collector user with no group/other
permissions. Non-sticky ancestors writable by other users are rejected. The lock
and database reservation use `O_NOFOLLOW`. These protections assume administrators
and the collector account do not concurrently replace directories or mounts.

创建目录或打开数据库之前，必须验证准确挂载点、HDD UUID、ext4、可写选项和目标
实际路径。挂载缺失、退回 SSD、其他子挂载、只读或符号链接越界都会拒绝。
获取锁后、每页提交前及清理前再次检查；命令行无绕过开关。新文件受 `0077` umask
保护，新目录为 `0700`。运行期间不可人为卸载或替换磁盘；重复检查不能完全消除竞态。
UUID 必须在私有配置中填写，留空或格式无效会在创建任何目录、数据库之前失败。
代码不携带真实 UUID。拒绝路径中的符号链接及数据库、锁、WAL、SHM、journal 的
符号链接或硬链接；已有文件必须属于运行用户且不可对组或其他用户开放权限。
拒绝可被其他用户写入且无 sticky 位的祖先目录；锁及数据库预创建使用 `O_NOFOLLOW`。
防护前提是管理员和运行账号不会并发替换目录或挂载。

## Templates and configuration / 模板及配置

The optional `.env.example` fields are `METRICS_ARCHIVE_PATH`,
`METRICS_ARCHIVE_MOUNT`, `METRICS_ARCHIVE_UUID`. Retention is fixed at 180 days
for the runner. Timer/service templates reside in `systemd/user/` and assume a
future installation at `%h/homelab-portal`; they are templates, not an instruction
to install them during Phase B. Review paths, permissions, UUID and credentials
before any separately authorized rollout. No dependencies were added.

The service optionally reads `%h/.config/homelab-portal/archive.env`, a private
systemd EnvironmentFile. Override `METRICS_ARCHIVE_PYTHON` and
`METRICS_ARCHIVE_SCRIPT` there for another installation path. It can also set all
archive and Beszel environment values; these override the checkout's `.env`.
The EnvironmentFile location itself can be changed in a service drop-in.
Keep credentials and the actual UUID out of tracked templates and documentation.

配置字段见 `.env.example`；运行器固定保留 180 天。用户级 systemd 模板假定未来
安装在 `%h/homelab-portal`，Phase B 不安装、不启动。后续授权部署前应核对路径、
权限、UUID 和认证。没有新增依赖。
service 可读取私有 `%h/.config/homelab-portal/archive.env`；在其中覆盖
`METRICS_ARCHIVE_PYTHON` 和 `METRICS_ARCHIVE_SCRIPT` 即可调整安装路径。
归档及 Beszel 参数也可在该文件设置，优先于安装目录 `.env`；EnvironmentFile
自身路径可通过 service drop-in 覆盖。真实 UUID 和凭据不得写入版本控制模板。

## Isolated verification / 隔离验证

Run `python -B -m unittest discover -s tests -p test_metrics_archive.py -v` using
the existing environment. These tests use temporary directories, synthetic API
responses and an injected test-only guard; they never access the real HDD or Hub.
Tests cover recovery after interrupted pages, overlap, same-timestamp records,
deduplication, raw fields, UTC, ten devices, retention boundaries, network and
malformed-page failures, locking, database misuse and mount protection.

测试仅使用临时目录、模拟 API 和测试内注入的挂载检查，不访问正式 HDD 或 Hub。
覆盖断点恢复、重叠补采、同时间戳、去重、原始字段、UTC、10 台设备、180 天边界、
网络和非法页面、并发锁、误用数据库及挂载保护。

Phase B verification on 2026-10-12: all 37 Python tests passed, including 17 archive
tests. `git diff --check` passed. `systemd-analyze --user verify` passed for both
new templates without installing or starting them. No live API integration or
2,592,000-row performance run was performed.

2026-10-12 Phase B 验证：全部 37 项 Python 测试通过，其中归档测试 17 项；
差异格式检查通过；两个 systemd 模板静态验证通过，未安装或启动。
尚未进行真实 API 联调或 259.2 万条性能测试。

Read-only live API integration passed using a temporary database: 241 real
records, zero inserts on repeat, one local synthetic insert, and recovery of
56 records after a simulated second-page timeout. No production database was opened.

只读真实 API 联调已通过：临时库首次 241 条，重复新增 0 条；本地模拟新增 1 条；
模拟第二页超时后恢复剩余 56 条。未打开正式归档数据库。

Remaining rollout acceptance: real Hub version, actual upstream retention,
full-scale performance and later archive-backed query/UI work.
The archive cannot recover samples already deleted upstream, or late inserts older
than its ten-minute overlap. It stores raw metrics, not local CPU-frequency samples.

后续验收：Hub 实际版本、上游保留期、完整规模性能，以及后续归档查询/UI 接入。
上游已删除或迟到超过重叠窗口的
样本无法自动恢复；本归档保存 Beszel 原始指标，不额外采集本机 CPU 频率。

## Backup and restore / 备份与恢复

Use SQLite's online backup API (`source.backup(destination)`), not a copy of just
the main file while WAL is active. Keep source and destination connections open
through the backup call and explicitly close them afterward; Python's connection
transaction context does not close connections. Store backups with mode `0600`.
Restore into a separate file, check `PRAGMA integrity_check`, compare both samples
and checkpoints, close connections, then validate the HDD and permissions before
any separately authorized production replacement. Never replace a live archive.

使用 SQLite 在线备份 API，不可在 WAL 活跃时只复制主文件。备份期间保留连接，
完成后显式关闭；Python 的连接事务上下文不会关闭连接。备份权限为 `0600`。
恢复到独立文件后执行完整性检查，并比较样本和断点；关闭连接后，后续正式替换必须
另行授权并重新核实 HDD 和权限，不可直接替换正在运行的归档库。

Phase C verification: all 44 Python tests (24 archive tests) and five existing
Node regression suites passed. Both systemd templates passed static verification;
the calendar expression produced five-minute boundaries. A separate temporary
online-WAL backup/restore acceptance preserved all 80 synthetic samples and four
checkpoints, with matching content hashes and `integrity_check=ok` on all three
databases. Repeat synchronization after restore inserted zero rows. Acceptance
directories were removed. No private IP, installation UUID, personal home path
or populated credential setting was found in the changed files.

Phase C 验证：全部 44 项 Python 测试（归档 24 项）及五个既有 Node 回归套件通过；
systemd 模板静态验证通过，日历表达式显示五分钟边界。独立临时库 WAL 在线备份、
恢复保留全部 80 条合成样本及 4 个断点，内容哈希一致，三个库完整性检查均为 `ok`；
恢复后重复同步新增 0 条。验收临时目录已清理。修改文件未发现私人 IP、真实安装
UUID、个人 home 路径或已填入凭据的配置。

WAL/SHM files may persist after a read-only reopen; do not delete them manually
while any connection is active. Test cleanup occurs only after all connections
close and only inside directories created by that test.

只读重新打开后 WAL/SHM 可能仍存在；有连接活动时不可手工删除。
测试仅在所有连接关闭后清理本次创建的临时目录。
