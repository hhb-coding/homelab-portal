# Step 7.03 CPU Frequency / 跨平台 CPU 主频

**Current deployment snapshot (operator-confirmed, 2026-11-05):** HP Linux and ThinkPad X230 Windows one-minute CPU frequency collection and history are deployed and producing valid samples. **Dell is not accepted/deployed for CPU frequency collection** and is pending operating-system reinstallation/follow-up. The original Phase 1 tests and architecture below remain historical design records; synthetic tests alone did not establish production status. This internal Step number is not a GitHub Release.

Sources: [Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11),
[ROADMAP](ROADMAP.md), [archive](historical-metrics-archive.md),
[CONTRIBUTING](../CONTRIBUTING.md).

**中文：**用户于 2026-11-05 确认 HP 和 X230 的主频采集与历史数据可用。Dell 尚待系统重装及采集部署，不能宣称三台机器全部完成。下文 Phase 1 为当时的技术设计与隔离测试记录。

## Architecture / 架构

Separate one-minute oneshots → authenticated API → existing registry's temporary
inbox → existing five-minute archive runner → same protected HDD history database.
Existing five-minute Heartbeat schedules and 7.01/7.02 display are unchanged.
Configuration, X-Heartbeat-Token and transport helpers are shared with Heartbeat.
Frequency uploads do not refresh Heartbeat last_seen or register unknown devices.
No resident collector, X230 history database or dashboard is added.

独立一分钟任务不替代五分钟心跳。客户端 JSON 及注册库 inbox 只用于短期重试；
长期历史仍为所有设备共用的 HDD 库。Web 请求不写 HDD，也不迁移历史库。

## Measurements / 观测口径

- Linux: average valid online logical CPUs' `scaling_cur_freq` kHz / 1,000,000.
  Per-logical-CPU reads weight shared policies by their online CPU membership.
  Read failures reduce coverage and mark partial/unavailable; CPU hotplug is racy.
  This preserves the existing sysfs mechanism, not a privileged hardware probe.
- Windows PowerShell 5.1: localized `Processor Information(*)\% Processor
  Performance`, two sets one second apart; use the second set's valid individual
  CPU instances, exclude totals/duplicates. Scale the dynamic percentage by the
  single package's Win32_Processor.MaxClockSpeed reference MHz:
  `GHz = reference_MHz × dynamic_percentage / 100000`. Turbo percentages above
  100 are permitted. Static MHz is never emitted alone as a current observation.
- The Windows reference must be validated against the actual CPU nominal clock
  on X230 before enabling. Multiple packages, absent counters and invalid
  references fail closed; there is no static-clock fallback. Windows is an OS
  performance-counter estimate with a 1000ms window. Real counter availability,
  reference accuracy and response to power states require hardware acceptance.
- Linux scaling_cur_freq can represent a requested P-state rather than exact
  hardware frequency. Neither platform promises a continuous one-minute mean or
  identical measurement precision. No new privilege is requested for cpuinfo_cur_freq.

Sources: [Linux CPUFreq](https://www.kernel.org/doc/html/latest/admin-guide/pm/cpufreq.html),
[Microsoft counters](https://learn.microsoft.com/en-us/windows/win32/perfctrs/collecting-performance-data),
[Win32_Processor](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-processor).

Linux 为在线逻辑核心等权平均，Windows 为动态计数器估算平均；模拟测试不证明硬件
准确性。采样失败记录 null 与原因；离线无观测，不补点、不沿用旧频率、不以静态时钟降级。

## API / 接口

`POST /api/telemetry/cpu-frequency`, X-Heartbeat-Token, ≤128 KiB, 1–120 samples.
Token must be configured and device_id must already exist in the registry.
The existing shared token authenticates the installation, not exclusive ownership
of a device. Only trusted clients should hold it; per-device credentials are a
separate hardening task. Reuse the existing protected transport, never expose
credentials or response bodies in logs.

```json
{"device_id":"example-device","samples":[{
  "sample_id":"00000000000000000000000000000001",
  "sampled_utc":"2026-10-19T12:00:00.000Z",
  "cpu_frequency_ghz":2.5,
  "source":"linux_scaling_cur_freq",
  "logical_cpu_count":4,"valid_cpu_count":4,
  "quality":"ok","window_ms":0,"error":null
}]}
```

Sources: linux_scaling_cur_freq, reserved linux_cpuinfo_cur_freq,
windows_processor_performance. Quality: ok/partial/unavailable. Errors:
null/partial_read/read_failed/invalid_counter. Reject nonfinite values, booleans,
nonpositive or >20GHz values; 20GHz is a sanity ceiling, not a base-clock cap.
Timezone is mandatory; normalize to UTC with millisecond-or-coarser precision.
Reject samples older than 24 hours or >5 minutes in the future.

Response: accepted IDs, duplicate IDs, expired_unarchived count. ACK means durable
inbox receipt, not HDD archival. Whole-batch transactions roll back on conflict or
overflow. Same ID + identical canonical content is idempotent; different content
is a conflict. Client retries retain the original ID and timestamp.

Errors: 400 validation, 401 token, 403 unknown device, 409 conflicting content,
413 body size, 422 expired/future sample, 503 unconfigured/busy/full storage.
Clients delete only fully acknowledged batches, otherwise preserve data and fail.
错误必须明确反馈，不能把接收确认当作已归档确认。

## Bounds and recovery / 上限及恢复

- Client: 24 hours, 1440 records, 1 MiB JSON, exclusive lock and atomic flushed
  replacement; Linux also fsyncs the directory. Private user state contains no
  credentials. Row-full queues try uploading backlog before adding observations.
- Server: frequency_inbox and frequency_queue_status in the existing registry,
  24h from receipt. Pending samples (`archived=0`) are limited to 1440/device and
  14400 globally. **All retained payloads, including archived dedup receipts,
  share the existing 16 MiB limit.** Receipts are not evicted early to admit data;
  valid pending samples are not evicted for capacity either. Indexes/free pages
  add overhead; this is not a cap on the entire registry file or unrelated IP
  events. No automatic VACUUM.
- Client expiration reports a count and nonzero exit. Server expired unarchived
  rows increment a persistent counter, reported in archive runner frequency_queue;
  reception also reports newly expired rows. Expiration is explicit retention loss.
  Cleanup occurs on the next receive/drain activity; no cleanup task is installed.
- Full queues reject new data; failed persistence means that observation was not
  accepted and is reported as failure. Network errors retain pending observations.
- Archive commits before inbox ACK. Crash between the two causes safe replay via
  historical PK. Receipts survive until TTL to detect conflicts after archival.
  Old samples after receipt expiration are rejected by their timestamp.
- Beszel authentication/listing/page failure cannot block already received
  frequency data. Drain runs first under the same archive flock; ≤120×120 rows
  per pass, short transactions, no additional HDD writer.

两个库没有分布式事务，通过先提交后确认、至少一次投递和主键幂等恢复；冲突不覆盖。
任务非零退出、过期计数和积压都需要运维关注，24 小时不是无限离线交付保证。

### Receipt capacity correction / 回执容量修复

Counting archived receipts toward the pending row limits rejected new samples
with `503 {"error":"queue_full"}` even when the archive had drained everything.
A batch is checked as a whole: 1416 receipts plus 25 new samples already exceed
the old per-device limit. One-minute sampling also has no room for scheduling
jitter at exactly 1440 receipts/24h. Backfill makes this worse: receipt TTL starts
at **receipt time**, so a 120-sample catch-up batch occupies 120 receipt slots
together, regardless of when those samples were measured.

The correction changes only row accounting and queue reporting. It retains the
same tables, payloads, 24h receipt TTL, canonical conflict checks, BEGIN IMMEDIATE
transaction, rollback behavior, archive PK, and archive-commit-before-inbox-ACK
recovery. There is no registry/archive migration, queue reset, history deletion,
or early receipt eviction. More receipt rows can remain than before, but their
total payload bytes remain bounded together with pending data at 16 MiB.

Linux and Windows both persist before upload, send oldest first in batches of
at most 120, and remove a batch only when accepted + duplicate IDs exactly match
the batch. A 503/timeout/invalid ACK stops that pass, preserving the unacknowledged
tail with original IDs/timestamps for the next scheduled minute. Each pass sends
up to 12 batches after appending the observation; a row-full local queue first
tries one backlog batch before appending. If that preliminary upload fails, the
existing queue survives, but the new observation is not saved. Both clients cap
local state at 1440 rows/1 MiB and expire by **sample time**, reporting loss. A
timeout/task deadline can interrupt a long catch-up; durable queues allow retry.
No client or task change is required for this server correction.

X230 Windows PowerShell 5.1 hardware validation is **deferred and unverified**;
it is not an acceptance gate for this server correction. No local Windows tests
were executed during this repair. The existing Windows CI job runs synthetic
tests separately and does not establish X230 hardware or scheduled-task health.
X230 的 Windows PowerShell 5.1 实机验证已延后、尚未验证，不作为本次服务端修复
的验收前提；本次未执行本地 Windows 测试，CI 合成测试不代表实机或计划任务验收。

中文：已归档回执不再占用未归档行数配额，但回执和积压仍共同受 16 MiB 载荷限制。
批量补传整批检查上限，因此“尚不足 1440 条”也可能返回 queue_full。回执按接收时间
保留 24 小时，客户端按采样时间过期；补传集中到达会放大二者冲突。保留有效回执和
未归档数据，不通过提前清理让出容量；真正积压或总字节超限仍原子拒绝。两端失败后
下一分钟重试，完整确认后才删除该批；本地已满且预发送失败时，新观测无法持久化。

Queue reports retain pending/expiry fields and `max_payload_bytes`; the obsolete
`max_rows_including_receipts` key becomes `max_pending_rows` plus
`max_pending_rows_per_device`. `receipts` and `total_payload_bytes` expose receipt
pressure. Update any external log consumer of the old key when deploying.

Future validation after separately approved deployment (not performed here):

1. Review tests and back up the registry using SQLite online backup; record
   per-device pending/receipt counts, byte usage, expiry counter, client backlog
   and latest archive timestamps. Preserve private data outside Git.
2. Deploy the reviewed server module via the normal service rollout. No schema,
   environment, client queue, Windows task or archive migration is needed.
3. Let existing minute schedules retry. Verify HTTP 200 and complete ACKs for
   both platforms, decreasing local backlogs, then HDD archival through existing
   five-minute passes. Verify real pending overflow still returns queue_full/503
   in an isolated copy, without filling production queues for a test.
4. Observe beyond 24h: receipts can exceed 1440/device while pending stays low;
   total bytes stay bounded, expired_unarchived_total does not unexpectedly rise,
   receipt TTL/conflict checks and history PK uniqueness remain valid. Check
   existing Heartbeat, Beszel and history queries as well.
5. Roll back code only if required; preserve all queues and databases. The old
   code can read the unchanged schema but may reproduce receipt-driven 503s.
   Never delete receipts or history as a rollback shortcut.

## Schema / 数据结构

Compatible writer accepts exact v1 tables samples/checkpoints, or v2 plus
cpu_frequency_samples. It never upgrades v1 automatically; new archives start v1.
Beszel columns, raw JSON, PK, indexes and checkpoints remain unchanged.

V2 adds cpu_frequency_samples(device_id, sample_id, sampled_utc, payload,
received_utc, archived_utc), PK(device_id,sample_id), device/time and retention
indexes. Payload preserves the validated GHz/source/quality/coverage contract.
No existing device mappings are rewritten. Both sources retain 180 days by sample
time. Compatibility rollback still prunes frequency history. WAL/FULL, busy timeout,
single-writer flock, private permissions and UUID/path safeguards remain mandatory.

## Deployment and rollback / 部署与回滚

**Future operator steps only; separate approval required. Nothing below has been
executed on production.** 以下仅为后续运维步骤，本阶段未执行。

1. Review/merge PR and CI, back up registry with SQLite online backup, verify
   intended paths, private permissions, mount and real counters. Deploy compatible
   v1/v2 archive code first, leaving frequency drain off. Additive inbox tables
   use existing registry initialization; this never migrates the history archive.
2. Supply METRICS_ARCHIVE_UUID privately and execute the explicit migration tool
   with reviewed placeholders, never during Web request/startup:

   ```sh
   python -B tools/migrate_metrics_archive.py --database /MOUNT/archive/metrics.sqlite3 --backup /MOUNT/archive/pre-v2.sqlite3 --to 2
   ```

   Source must exist, backup must not exist, both must pass HDD guard. The tool
   holds the writer lock, makes an online backup, checks integrity and commits
   schema changes atomically. Failure may leave a partial backup file; it is not
   automatically a good restore point. There is no guard bypass CLI.
3. Enable FREQUENCY_ARCHIVE_ENABLED=true in the archive's private environment.
   Optionally enable FREQUENCY_HISTORY_ENABLED=true for Portal read queries.
4. Linux: review/copy the separate homelab-cpu-frequency service/timer templates,
   using existing heartbeat.env; optional HOMELAB_FREQUENCY_QUEUE sets the private
   queue path. One-minute calendar, 5s accuracy, 50s timeout, no persistent replay.
   Leave heartbeat.timer unchanged. Do not install or enable during development.
5. Windows: review windows-frequency.task.xml, replace placeholder path, choose
   intended account/ACL, then import only after separate approval. It uses
   InteractiveToken (requires login), IgnoreNew, no wake, 50s timeout, one-minute
   repeat. Unattended coverage needs a separately reviewed principal. ConfigPath
   reuses heartbeat.json; QueuePath is private local JSON, not a history database.
   Existing Heartbeat task stays unchanged. Review TLS and counter access first.
6. Observe at least 24h on all three devices: timestamp intervals, missing quality,
   queue depth/expiry, archive latency/integrity and existing display/Heartbeat/
   Beszel behavior. Verify Windows reference and dynamic counter response with an
   independent hardware-aware tool. No production stress testing is implied.

Rollback: stop only newly approved frequency tasks, disable frequency flags, keep
the reviewed v1/v2-compatible runner (including frequency retention) and preserve
v2 data so Beszel can continue. The first writer-only compatibility commit is a
schema compatibility checkpoint, not a complete operational rollback release. Never run
the old v1-only executable on v2. Explicit --to 1 requires another backup and
refuses any nonempty frequency table; no collected history is dropped. Physical
restore needs separate approval, quiesced writers and integrity/record/checkpoint
checks; account for data newer than the backup and possible upstream loss.

优先功能回滚并保留数据；不能把旧版 v1 写入器当作 v2 回滚目标。生产迁移、重启、
安装及启用任务都需独立授权，合并 PR 不等于部署许可。

## Step 7.06 contract / 统一历史契约

GET /api/history/v2?device_id=example-device&start=<UTC>&end=<UTC>&limit=2000.
Default off; enabled reads verify HDD then use SQLite mode=ro/query_only. Existing
Portal ingress authentication protects read APIs; never expose Flask directly.
All three devices use the same endpoint and table. Implemented metric is
cpu_frequency_ghz; unsupported metric parameters return 400. Original source,
quality and observation window are returned with GHz units and raw resolution.
Range is [start,end), ≤180 days, ≤2000 points/page; next_cursor is opaque and
passed as cursor. Stable (sampled_utc,sample_id) pagination handles equal times.
Missing minutes remain gaps; unavailable observations are null. No interpolation.

Executable contract: frequency_history.query and synthetic pagination tests.
24h/7d/30d/custom are future UTC UI presets. Planned companion usage series reads
unchanged Beszel samples.stats_json.cpu via the registry beszel_system_id mapping.
Temperature requires verification of the actual archived field; do not invent a
key from live unarchived info. Future multi-metric contract must keep per-series
units, source timestamps, coverage, mapping epochs and explicit aggregation.
Nearest-neighbour joins and dashboard implementation are outside Phase 1.

## Tests / 测试

Python synthetic tests cover Linux sampling, auth, queue overflow/conflicts,
recovery, migration/compatibility rollback, HDD/lock failures and query gaps.
`test_frequency_capacity.py` also covers 1440 archived receipts followed by new
data, 1440-sample catch-up, real pending/total-byte overflow, exact 24h boundaries,
parallel devices, atomic expiration rollback and failed archive ACK recovery.
Native Windows PowerShell 5.1 synthetic checks run in windows-frequency CI, stubbing
network/counters and using temporary JSON only. Existing test job retains Python,
Node and ES5/browser syntax regression. Hardware and full-scale 180-day performance
acceptance remain separate gates; mocks and green CI do not prove deployment health.
