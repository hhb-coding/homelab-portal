# Step 8.03.3 — Network ranges and statistics / 网络时段与统计

Branch `feature/step-8-03-3-network-range-stats` starts from the latest fetched
`origin/main`, `046be3f` (merged PR #28, the operator-confirmed production baseline).
This step implements, tests and submits the change for review; it is not deployed.

指定分支从最新获取的 `origin/main`（`046be3f`，PR #28 合并提交、用户确认的生产基线）
建立。本步骤实现、验收并提交评审，尚未部署。

## Behavior / 行为

- Buttons follow **1h, 3h, 6h, 10h, 24h, 7d, 30d**. All hour ranges read minute
  records; 7d/30d read UTC daily summaries, including the UTC day intersecting the
  left boundary. Existing read-only API, archive schema, row limits and HDD guard
  are reused. No archive job, migration, polling interval or dependency changes.
- Private RTT, public RTT and packet loss each show a statistics bar below the
  graph: role name, IP, range, valid sample count, maximum, minimum and average.
  The count means valid **plotted points** (minutes or daily summaries), not probes.
  Extremes are those point values, not underlying single-probe RTT extrema.
- Private RTT initially pins the upstream gateway; public RTT pins public primary,
  and loss pins upstream gateway. Charts select independently. Hovering a curve,
  loss point or legend temporarily previews that target; leaving restores the pin.
  Clicking a curve/point/legend pins it. Native legend buttons support touch,
  keyboard focus preview, Enter/Space selection and `aria-pressed` state.
- Range changes and redraws retain the pinned target and clear temporary preview.
  Hiding a pinned target falls back to the first shown role in that chart;
  deselecting all targets leaves empty statistics. Loss spikes and the existing
  selectable records still expose exact failed/total counts and local timestamps.
- RTT average = `sum(point.rtt_ms * point.success_count) / sum(success_count)`.
  Loss average = `100 * sum(failed_count) / sum(count)`. Both use only points valid
  for the current graph and range. Zero loss is valid. All-failed buckets count
  toward loss and have no RTT. Missing/zero-probe buckets stay absent; unavailable
  extrema/averages display `—`, with a valid count of zero for an empty series.
- ES5/XHR and the legacy CSS layout remain in use. Full dashboard JavaScript and
  CSS cache keys advance to `8033-network-range-stats`.

- 按钮依次为 **1h、3h、6h、10h、24h、7d、30d**；小时读分钟归档，7d/30d 读 UTC
  日汇总，包含与左边界相交的 UTC 日桶。复用只读接口、归档结构、行数限制和 HDD 校验。
- 三条图各有图下统计栏，显示角色名、IP、时段、有效样本数及最大/最小/平均值。
  样本数为有效的图中点数（分钟或日汇总），极值为这些点的值。
- 私网默认固定上游网关，公网默认主目标，丢包默认上游网关；各图独立。
  悬停曲线、尖峰或图例临时查看，移开恢复固定目标；点击固定。
  原生图例按钮支持触屏、键盘聚焦临时查看、Enter/空格固定及无障碍按下状态。
- 切换时段或重绘保留固定目标并清除临时查看；隐藏固定目标则选本图首个可见目标，
  全部隐藏时统计为空。尖峰和记录列表仍可查看单次记录的失败数、探测总数与本地时间。
- RTT 均值按 `success_count` 加权，丢包均值为总失败数/总探测数；只统计当前图有效点。
  0% 丢包有效，全丢包纳入丢包而 RTT 为空；缺测与零探测不补零，空统计显示 `—`、点数 0。
- 保留 ES5/XHR 与旧式 CSS，相关 JS/CSS 资源版本更新为 `8033-network-range-stats`。

## Validation / 验证

- **150 Python tests passed**, including exact start-inclusive/end-exclusive hour
  boundaries for all five hour ranges, minute versus daily source selection,
  UTC daily boundaries with a non-UTC caller, counts and unchanged read-only data.
- **All seven CI JavaScript regression programs passed**, including the extended
  Network readability tests: weighted RTT/loss, valid-point extrema/counts, zeros,
  empty/all-failed data, intersecting daily buckets, hover/leave, focus/blur,
  independent pins, Enter/Space, range redraw, filtering, escaping and late XHR.
- **Cached Chromium outside the execution sandbox passed at 1440px and 390px**:
  ordered seven ranges; full rows and aligned axes; statistics below every plot;
  weighted values and pinned-target recomputation across every range; real mouse
  hover/leave and curve click; touch legend selection; keyboard focus, Enter and
  Space; loss point/record interaction; stable styles; no horizontal overflow or
  page exceptions. Screenshots and JSON report: `/tmp/portal08-step8033-browser-kcymUK`.
- Python parsing, JavaScript syntax checks and `git diff --check` passed.
  Tests use isolated Flask/SQLite data and RFC 5737 addresses, intercept all browser
  HTTP over a CDP pipe, and require no live upstream or production archive.

- **150 项 Python 测试、七组 CI JavaScript 回归通过**，覆盖新增时段边界、分钟/日汇总
  来源、带时区输入的 UTC 日边界、实际计数和只读性；前端覆盖有效点极值、加权均值、
  零值、空数据、全丢包、悬停/固定/键盘、时段重算、筛选、转义与过期 XHR。
- **沙箱外缓存 Chromium 在 1440px、390px 均通过**：七时段、整行图与对齐坐标轴、
  图下统计、固定目标跨时段重算、真实鼠标操作、触屏图例、键盘操作、尖峰记录、样式稳定，
  无横向溢出或页面异常。截图及 JSON 报告保存在上述临时目录。
- Python/JS 语法与 diff 检查通过。验收仅用隔离合成数据，不连接生产归档或上游；
  本验收不代表旧 iOS 真机或生产部署验收。

The sandbox blocks Chromium sockets (`SIGTRAP`, `setsockopt: Operation not permitted`);
the successful run used approved execution outside it. Recheck from ordinary HP SSH:

执行沙箱限制 Chromium 套接字；已通过获准的沙箱外执行完成验收。HP 普通 SSH 一条命令复验：

```sh
cd ~/homelab-portal-08 && NETWORK_BROWSER_PYTHON=~/homelab-portal-dev/.venv/bin/python ~/.nvm/versions/node/v22.23.3/bin/node tests/test_network_readability_browser.js
```

Set `CHROMIUM_BINARY` if the cached browser is elsewhere, and adjust the Python/Node
paths for another host. Failure returns nonzero and saves step/width, DOM and
screenshot diagnostics when available. / 路径不同时调整 Python/Node，浏览器用
`CHROMIUM_BINARY` 指定；失败返回非零并尽量保存步骤、宽度、DOM 与截图诊断。
