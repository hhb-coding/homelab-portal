# Step 8.02 — Network archive / 网络归档

Backend on baseline `7a21774` (PRs #22/#24), **not deployed**. Step 8.01
verified six enabled 10-second ICMP monitors through the existing account's API.
Charts and HTTP history endpoints belong to 8.03.

基于已核验基线实现后端，尚未部署；8.01 已核实六项 10 秒 ICMP 监控。
本轮仅修改开发 worktree，图表及历史 HTTP 接口交给 8.03。

## Migration and configuration / 迁移与配置

Reuse the 7.04 SQLite, HDD UUID/ext4/rw/path guards, writer lock, Beszel auth
and five-minute timer. Upstream access is authentication plus GET only. Explicit
`--to 3` adds network tables atomically to v1/v2; v1 also gains the v2 frequency
table. Mandatory online backup includes WAL. Rerunning at v3 validates the schema
and succeeds without overwriting the backup. Failed migration rolls back schema
and version together. Network collection defaults off and never auto-migrates.

`METRICS_ARCHIVE_MIN_FREE_BYTES` reserves at least 1 GiB by default. The HDD guard
checks free space before opening the writer and before page commits/cleanup;
invalid or exhausted reserves fail closed. Backup staging also needs room for
the full snapshot and restore copies in addition to this reserve.
The migration command verifies full snapshot headroom before creating its backup
and rechecks the HDD guard during paged online copying.

复用既有归档库、挂载保护、文件锁、认证与 timer；Beszel 只经 API 读取。
v1/v2 可备份后显式升 v3，失败整笔回滚，v3 重跑不覆盖备份；默认关闭、不自动迁移。
空间保护默认预留 1 GiB（上述私有环境变量可设正整数），打开库、逐页提交和清理前
均核验；门槛非法或空间不足时拒绝写入。备份演练还需额外容纳完整快照及恢复副本。
迁移命令在创建备份前验证完整快照所需空间，并在分批在线复制中重复核验保护。

For future deployment, first load private HDD environment settings; use a new
backup path on that verified HDD. These commands were **not run in production**:

下列命令仅供后续部署；先加载私有挂载环境变量，备份需为同一 HDD 上的新文件：

```sh
"<python-path>" -B tools/migrate_metrics_archive.py \
  --database "<existing-archive.sqlite3>" --backup "<new-backup.sqlite3>" --to 3
"<python-path>" -B tools/archive_metrics.py
```

Copy [the role example](../examples/network-archive-roles.json) outside the checkout
(recommended `0600`), replacing every placeholder privately. Resolve targets against
one Beszel system. NX30 `lan_gateway` and `upstream_gateway` are distinct;
Cloudflare is `public_primary`, Google is `public_control`, and the other internal
targets are `endpoint_a`/`endpoint_b`. Add to the existing private archive environment:

将示例复制到仓库外私有文件并替换占位值；LAN 与上游网关不得混用，生产地址不提交。
在既有私有归档环境中设置：

```dotenv
NETWORK_ARCHIVE_ENABLED=true
NETWORK_ARCHIVE_ROLES_FILE=/absolute/private/network-archive-roles.json
```

Blank role-file settings allow archival/target events without public correlation.
Invalid files fail the network job; missing/ambiguous/disabled correlation monitors
are unknown. Logs contain counters/exception classes, never secrets or API bodies.

未指定角色文件时仍可归档，但不做公网关联；非法配置报错，关联角色缺失、歧义或
停用时为未知。日志只含计数和异常类别，不输出凭据、响应正文或私有映射。

## Collection and retention / 采集与保留

Discover all account-visible monitors by ID cursor, including disabled targets'
remaining history. IDs are opaque strings (7–8-character monitor and 10-character
sample IDs supported); `created` is Unix **milliseconds**. Each run fixes its UTC
upper bound, filters `monitor` and `type='1m'`, and uses `sort=created,id`, `page=1`,
`perPage=200` with strict tuple continuation. Continue after short pages until empty.
Resume ten minutes before the last committed sample. Initial fill takes only API
records currently visible within 90 days; unavailable earlier history stays unknown.

监控按账号可见性发现，ID 不假设固定长度；时间使用 Unix 毫秒，固定本轮上界，
联合游标升序分页到空页，重叠补采十分钟。首次仅回填 API 可见记录，早期缺测保持未知。

Each page atomically commits samples, daily increments and `(created,id)` checkpoint.
Deduplicate by `(monitor_id,type,record_id)`; empty pages never advance checkpoints.
Conflicting content for an existing immutable record fails that page. One monitor's
failure does not stop others. Updated code opens v1/v2 and keeps v3 frequency drain
and existing history readers working. Older binaries cannot open v3: compatibility
rollback means disabling network collection with v3-capable code; full old-binary
rollback needs the backup and loses subsequent writes.

An existing monitor ID cannot change system/target/protocol: that monitor fails
closed to preserve historical identity; use a new upstream ID for a new binding.

每页样本、日汇总和断点原子提交，重跑去重、空页不推进、单目标失败隔离；内容冲突
拒绝当前页。新代码兼容旧库，v3 保留频率采集和历史查询。回滚应关闭网络功能并保留
支持 v3 的代码；回退旧二进制需恢复备份，会丢失备份后写入。
同一 ID 更换系统、目标或协议时拒绝归档；新绑定应使用新监控 ID，避免混合历史。

Raw network samples retain 90 days. Daily totals, metadata, checkpoints and
incident/state tables have no TTL. Increment daily totals **only on first insert**;
never rebuild them from partially pruned raw data. A persisted monotonic retention
floor blocks expired replay after clock rollback. API auth failure still permits
local maintenance/pruning. `network_daily_stats` derives probe-weighted values:

分钟数据保留 90 天，日汇总和事件等必要状态长期保留；日汇总仅首次插入累加，不从
已清理的原始数据重建。持久化保留下界防止时钟回退后重复计数，API 故障时仍维护本地
保留策略。`network_daily_stats` 视图按次数加权：

- Mean latency ms = `sum(res_sum)/sum(success_count)/1000`.
- Loss % = `100*(sum(total_count)-sum(success_count))/sum(total_count)`.
- `res_min/res_max/res_sum` retain microseconds; min/max exclude failed probes.
  Zero-success latency and zero-attempt loss are NULL. Missing minutes/days remain
  absent/unknown; observed record counts never imply complete coverage or uptime.

延迟按成功次数、丢包按探测次数加权；无成功或无探测时相应结果为空，缺测不补零。

## Events and validation / 事件与验收

Combine actual counts per monitor/UTC minute. Any loss with attempts is abnormal;
zero loss with attempts is healthy; missing/zero-attempt buckets are unknown.
Default trigger: **three consecutive abnormal minutes**; recovery: **two consecutive
healthy minutes** (private thresholds 1–60). Unknown/gaps reset streaks, and cannot
open or recover an event. An open incident remains unresolved until valid recovery.

默认任意丢包连续三分钟触发，零丢包连续两分钟恢复，可私有配置；缺测打断计数，
不能触发或恢复事件，已打开事件保留待确认状态。

Each monitor produces `target_anomaly`. `suspected_public_connectivity` requires
both public targets abnormal in the **same** consecutive minutes and the configured
upstream gateway healthy each minute; recovery requires all three healthy. LAN
reachability alone is insufficient. Partial API rounds defer correlation, whose
frontier is limited by the least-advanced source checkpoint.

单公网持续丢包记目标异常；双公网同期持续异常且上游网关健康时，才记疑似公网
连通性异常；三者持续健康才恢复。LAN 网关不能替代上游，API 部分失败时暂缓关联。

Evaluate only ten minutes after a minute ends, allowing bounded late arrivals.
Store the first bad/recovered minute and their confirmation minutes. Events and
state commit together and survive raw pruning; reruns are idempotent. Later arrivals
still update retained raw/daily history but do not rewrite confirmed events.
Rule/role/monitor rebinding starts a new diagnosis stream; preserve old incidents
without inventing recovery for a different source.

分钟结束十分钟后判定；事件与状态原子提交、重跑幂等、跨清理保留。超窗迟到数据
仍更新归档和汇总，但不改写已确认事件；重绑定开启新判定流，旧事件保留。

Synthetic API/temp SQLite tests cover migration/backup, pagination, overlap,
interruption, retries, weighted totals, partial-day TTL, unknowns and recovery.
Local validation: 145 Python tests (38 network archive tests), six Node behavior
suites, Python AST and diff whitespace checks passed.
Before deployment verify backup **restore**, HDD protection/space, v3 frequency/history
compatibility, all six private role/10-second ICMP mappings, API visibility/freshness,
and timer runtime/lag. Upstream minute TTL limits outage catch-up; Portal's 90-day
history accumulates after enablement. 8.03 reads this archive for all six latency/loss
curves including both public targets and displays gaps.

部署前验证备份恢复、HDD、v3 兼容、六项角色及配置、权限/样本时效和 timer 延迟；
补采受上游分钟保留期限制，90天历史需上线后积累；8.03 从本库绘制六项目标曲线并保留断点。
本地 145 项 Python（含 38 项网络归档测试）、六套 Node 行为回归、语法和差异检查通过。

### Pre-merge copy rehearsal / 合并前副本演练（2026-11-11）

Using the established private configuration, opened the live v2 archive read-only
and used SQLite online backup into a protected, isolated HDD directory. Restore
and integrity checks passed; explicit v2→v3 migration and identical CLI rerun
passed. All legacy table contents and two devices' frequency/default/extended
history query results matched before/after migration and real network ingestion.
UUID/path/low-space rejection was verified without filling the disk; approximately
589 GiB remained. Added the missing free-space reserve and backup-headroom checks.

正式 v2 库仅以只读连接生成在线快照，写入均在 HDD 隔离副本；恢复、完整性、迁移及
重跑通过，旧表内容及两台设备的频率/默认/扩展历史查询结果完全一致。UUID、路径与
低空间拒写已验证（未填满磁盘），剩余约589 GiB；补齐空间预留及完整备份空间检查。

Resolved six private roles against enabled 10-second ICMP monitors, keeping the
upstream and NX30 LAN gateways distinct. First fill: 520 records across eight
visible monitors, 65 per required target. Full-range replay: zero inserts/520
duplicates with unchanged daily/checkpoint/event state; normal overlap: zero
inserts/88 duplicates. Four subsequent minutes added 32 records, four per required
target; latest samples were about 26 seconds old, recent successes 90/90 each.
The live archive remained v2 without network tables. No snapshot, real address,
monitor/system/device ID, authentication material or private role file is committed.

六项私有角色均匹配启用的10秒ICMP，上游与LAN网关严格区分；首次520条（验收六项各
65条），全范围重跑零新增、520次去重，常规重叠零新增、88次去重，日汇总/断点/事件
不重复。随后四分钟新增32条，六项各增4条，最新约26秒，近期各90/90成功。正式库仍为
v2、无网络表，真实地址、ID、配置、凭据和数据库副本均不提交。

Read-only service checks confirmed the existing persistent five-minute timer and
its configured Python/archive-script command; last execution succeeded. Production
network enablement, real timer-to-archive lag and failure/recovery under operational
conditions remain deployment acceptance, alongside backup freshness/restore,
current mappings, permissions, space policy and v3 frequency/history behavior.

正式timer周期、持久补触发和执行命令已只读核对、最近成功；正式网络启用后的实际
归档延迟及现场故障/恢复行为仍属部署验收，并须复核最新备份、角色/权限、空间策略和
v3下频率/历史功能。本次未安装、启停或重载服务与timer。
