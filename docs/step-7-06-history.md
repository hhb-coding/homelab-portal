# Step 7.06 simplified Phase 1 / 简化版历史面板

Step 7.06.1 is deployed at `d6f2eb56df5027c9364feb422ffb705a204b677c` (user-confirmed baseline).
7.06.1 已部署（用户确认基线）；7.06.2 开发供审核，未批准合并或部署。

## Current frequency / 当前主频

Full and Lite use the same one-decimal °C / two-decimal GHz formatting. HP retains
its existing local scaling frequency reader. X230 reads the existing inbox and
archived receipts, ordered by payload sampling time rather than arrival order.
Only `quality=ok`, finite positive frequencies sampled within the preceding
120 seconds are displayed. Future, stale, partial and unavailable samples display
`—`; an older good sample never replaces the newest unavailable observation.
Frequency remains independent of Beszel availability. The existing shared clock
expires retained DOM values even when polling fails, including on page resume.

Full/Lite 统一温度一位、主频两位小数。HP 保留本机实现；X230 只读现有队列及回执，
按采样时间选最新记录。超过120秒、未来时间或质量非 ok 均显示占位符，不回退旧值。
复用现有服务端时钟及定时器，断网后仍过期；不修改采集或归档机制。

## Archive API / 归档接口

`GET /api/history/v2/performance?device_id=example-x230&start=<UTC>&end=<UTC>`

- Reuses the existing `FREQUENCY_HISTORY_ENABLED` opt-in gate and HDD read guard;
  this change does **not** enable it. Connections use `mode=ro` and `query_only`.
- Existing `/api/history` and `/api/history/v2` responses remain compatible.
- Range is `[start,end)`, greater than zero and at most 180 days. Bins are
  60s for ≤1h, 300s for ≤6h, 900s for ≤24h; longer ranges retain
  `max(60, ceil(range_seconds / 500 / 60) * 60)` seconds, anchored at request start.
  Thus each of three series has at most 500 points, including empty bins.
- Frequency comes from `cpu_frequency_samples.payload.cpu_frequency_ghz` with
  `quality=ok`; usage from `samples.stats_json.cpu` (%); temperature from
  `stats_json.t.k10temp` for HP, `stats_json.t["CPU Package"]` for X230 (°C).
- Each bucket contains average, minimum, maximum, count, source first/last times,
  and a gap flag. Whole-range average is weighted by valid source observations;
  peak and peak time come from source observations, not bucket averages.
- Null, nonnumeric, nonfinite and out-of-domain values are excluded, never zero-filled.
  Empty buckets stay null. Known invalid observations and sampling gaps over
  90 seconds mark partial buckets; the renderer isolates these instead of joining
  lines through holes. Bucket averages summarize observations, not missing time.
- Source rows stream through constant-sized accumulators; no raw `fetchall` or
  additional database/table/service is needed. A five-second query budget fails
  closed with 503; SQLite lock wait is bounded. No dedicated 180-day load test was run.
- Missing/offline data stays absent. Historical archive timestamps are source
  record times; frequency keeps its own sampling timestamps. No nearest-neighbor join.

只读复用 Schema v2、现有开关及保护逻辑；最多180天，每指标最多500桶。
1h 为1分钟桶（60点）、6h 为5分钟桶（72点）、24h 为15分钟桶（96点）；7d 默认21分钟桶、30d 默认87分钟桶；每次请求统一桶宽和范围。
均值按有效原始观测加权，峰值取原始观测；缺失留空、部分缺失桶断线，不插值。

## Device identity and UI / 设备身份及界面

HP uses the existing explicit `LOCAL_DEVICE_ID`. X230 is recognized by `x230`
in the registered ID/hostname/display name; no private IDs enter source code.
Renaming all these fields to remove `x230` removes it from this phase's scope.
Other devices are excluded. Usage/temperature use the current registered
`beszel_system_id`; historical rebinding cannot be reconstructed. Changing this
link can change which old observations are displayed. No mapping-version table.

Full keeps Live trends and Historical trends, and adds a third Performance history
row (default 24h, shared 1h/6h/24h selector): Frequency GHz, Usage %, Temperature °C. All three use the same requested
time axis, independent vertical scales, legacy floats, and narrow-screen wrapping.
History is a sibling of Device/Network, with supported-device selection,
24h/7d/30d presets and custom UTC text input `YYYY-MM-DD HH:mm` (≤180 days), plus
average/peak/count statistics. Requests ignore superseded responses. Detail data
is cached for one minute; History refreshes on explicit range/device/query action.
ES5, XHR and SVG are retained; no new frontend runtime dependency.

HP 通过现有本机 ID 识别，X230 通过登记名称/ID 中的 x230 识别；设备关联只使用当前值，
历史重绑定限制在页面明确提示。新增第三排及 History 标签，保留原两排图表和旧浏览器技术栈。
温度当前值仍保留 Beszel `systems.info.dt` 语义，不宣称与历史 CPU 传感器选择完全相同。

## Validation and rollback / 验证及回滚

Synthetic Python/API and Node DOM tests cover source selection, missing values,
weighted statistics, point cap, read-only access, expiry, out-of-order samples,
request races, custom ranges and navigation. CI runs these with existing suites,
including the existing Windows PowerShell synthetic job. The optional Chrome
layout test uses a local mock server and verifies 320/375/768/1024px layouts,
Full/Lite, preserved trends, three charts and History controls. It does not use
production APIs. Chrome results do not constitute iOS 9 physical-device acceptance.

No production database, timer, service or private configuration is changed.
Rollback application/static files to the previous version; leave Schema v2,
frequency collection and archives intact. Existing history gate can keep archive
reading disabled. Deployment and any gate enablement require separate approval.

测试仅使用合成数据和隔离临时库；Chrome 回归不代表 iOS 9 实机验收。
回滚应用/静态资源即可，无数据库迁移或数据删除；部署、启用读取仍需单独批准。

## Step 7.06.1 chart readability / 图表可读性增量

Full retains all three chart rows. Only Performance history gains a shared range
selector on the right; changing it fetches all three metrics once with one time
window, retains the selection across refresh/device switches, and ignores late
responses. History retains its existing presets and custom UTC range inputs.

The common SVG renderer removes per-point circles. CPU Usage starts at zero and
sets its upper bound from the raw whole-range peak (10% headroom, rounded steps,
minimum 1%, capped at 100%), not from bucket averages. Frequency/temperature keep
dynamic padded scales. Each chart shows identical start/mid/end UTC ticks; dates
appear for long ranges or midnight crossings. Empty buckets break lines;
isolated/partial buckets use a short vertical mark so they remain visible without
inventing a connecting line or time coverage. Raw means/peaks and collection are
unchanged. No database, migration, client, timer or production change is involved.

三排布局保留，第三排右侧共用1h/6h/24h选择器。三图统一UTC起点/中点/终点刻度；
Usage从0起按原始峰值自适应，另两图动态留白。取消逐点圆圈，缺口断线，孤立/部分桶
以竖向短线标记；均值/峰值仍来自原始有效观测。History继续支持原有范围及设备选择。

## Step 7.06.2 Local time and freshness

Shared charts use browser Local time with per-instant UTC offsets (ES5 Date, including DST). Custom inputs and API requests remain UTC. Each metric shows the maximum valid last_sample within the queried range, or —, never a bucket/window end or sync execution time. Refresh and cache cadence remain unchanged.
