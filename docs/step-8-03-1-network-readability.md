# Step 8.03.1 — Network readability / 网络可读性

Implemented locally on `feature/step-8-03-1-network-readability`, based on the
GitHub main merge `24f85a7` (PR #26). GitHub confirmed that main was at that exact
commit. Direct SSH fetch failed under the execution sandbox's DNS restriction;
the identical object was fetched from the existing local checkout into
`origin/main`, and ancestry was checked before creating the branch.

本地实现基于 GitHub 已确认的最新 main：`24f85a7`（8.03 / PR #26）。执行沙箱禁止
DNS，直接 SSH 获取失败；从本机已有副本获取同一哈希对象至 `origin/main`，检查祖先
关系后新建指定分支。沙箱也拒绝连接 tmux 套接字，无法操作 portal08 会话；代码操作
在 hp-linux 的指定开发工作树中完成。

The Network quality panel has three full-width rows: four private-role RTT
series, two public-role RTT series, then all selected packet-loss series. Every
plot uses identical time bounds and horizontal gutters; RTT plots have independent
ms ticks, and loss ticks always cover 0–100%. Resize and tab opening recalculate
SVG dimensions so mobile labels remain readable. Missing samples and null RTT
break paths; an all-failed bucket has 100% loss and no RTT.

网络质量区依次为四个私网角色 RTT、两个公网角色 RTT、全部已选目标丢包率，均为整行。
三图时间范围与左右绘图区对齐；两张 RTT 图独立显示 ms 刻度，丢包轴固定 0–100%。
窗口调整或打开标签页时重新计算 SVG 尺寸。缺测与 RTT 空值断线，全丢包不制造 RTT。

All six cards use the existing private role-to-IP mapping. Each shows its role,
target IP, latest archived minute RTT/loss/local timestamp, and the selected
range's peak loss. `latest_sample` is queried independently of chart granularity;
an old minute retains its real timestamp, while missing data stays unavailable.
7d/30d peaks explicitly describe the maximum **daily weighted loss**, not the
maximum minute loss. Existing daily range behavior includes intersecting UTC day
buckets; their whole-day counts are retained and the first point is placed at the
visible left edge when its UTC midnight precedes the rolling start time.

六卡从已有私有角色配置读取 IP，显示角色、目标、最新归档分钟 RTT/丢包/本地时间及
所选时段峰值。`latest_sample` 独立读取最新分钟，不把日汇总冒充最新分钟；旧分钟保留
真实时间，无样本显示缺失。7d/30d 标注为日汇总峰值，即按探测次数加权的日丢包率最大值，
并非分钟峰值。沿用与时段相交的 UTC 日桶，保留整日计数；首日 UTC 零点在滚动起点前时，
图点放在可见左边界，详情仍显示原始桶时间。

Color, dash and symbol are keyed by role rather than selection index. Unselected
cards remain visible and marked hidden; their plot legends, paths, point markers
and record buttons are removed together. Nonzero loss markers support hover,
tap/click, focus and Enter/Space. A scrollable record list also selects each point,
including overlapping points. Details show local time, IP, loss and the exact
archived `failed_count / count`; no counts are reconstructed from rounded loss.

颜色、线型、标记按角色固定。未选卡片保留并标注隐藏，对应图例、曲线、点位和记录同步
筛除。非零丢包点支持悬停、点击/轻触、聚焦和回车/空格；可滚动记录列表可点选重叠点。
详情含本地时间、IP、丢包率及实际失败数/总探测数，不从四舍五入后的百分比反推次数。

The existing read-only v3 route, HDD guard, SQLite schema and ES5/XHR transport
are reused. No archive migration, collector, private configuration, deployment,
service or timer change is part of this work.

复用 v3 只读接口、HDD 校验、SQLite 架构和 ES5/XHR。此步骤不包含归档迁移、采集器、
私有配置、部署、服务或定时任务变更。

## Validation / 验证

- HP's existing Python 3.12 virtual environment: **148 tests passed**, including
  temporary SQLite cases for latest 0% versus historical 16.7%, absent/zero-probe
  data, total loss, minute/day weighting, exact counts and all four ranges.
- nvm Node **22.23.3**: seven CI JavaScript regression programs passed, including
  the new Network readability regression. Python parsing, JavaScript syntax and
  `git diff --check` passed.
- The isolated Flask fixture exercised the real read-only HTTP route for all
  four ranges and rejected an invalid range. All addresses are synthetic RFC 5737
  examples; external HTTP is blocked and only temporary SQLite is used.
- **1440px / 390px browser acceptance is pending.** Cached Chromium aborted with
  `SIGTRAP` / `setsockopt: Operation not permitted`; cached headless shell also
  aborted on a sandbox-denied socket operation. The existing optional
  `test_offline_layout.js` browser check could not listen on localhost (`EPERM`).
  No screenshots or browser passes are claimed.

- 复用 HP Python 虚拟环境，148 项测试通过；临时库覆盖最新 0% / 历史 16.7%、缺测、
  零探测、全丢包、分钟/日加权、实际计数和四种范围。
- 复用 nvm Node 22.23.3，七个 CI JavaScript 回归程序通过；语法及 diff 检查通过。
- 隔离 Flask 样本通过真实只读接口验证四种范围及非法范围，禁用外部 HTTP，仅用临时库。
- **1440px / 390px 浏览器验收未完成**：沙箱禁止 Chromium 所需的套接字操作，启动即退出；
  现有可选离线布局检查也因 localhost 监听被拒而无法执行，不能据此宣称视觉/触控通过。

Re-run browser acceptance in an execution context that permits Chromium:

在允许 Chromium 运行的执行环境中重跑（无需下载依赖或启动监听服务）：

```sh
NETWORK_BROWSER_PYTHON=/path/to/existing/.venv/bin/python \
CHROMIUM_BINARY=/path/to/cached/chrome \
node tests/test_network_readability_browser.js
```

The script exports synthetic Flask/SQLite responses, intercepts browser requests
over a CDP pipe, checks full-width rows/aligned axes, hover/tap/list selection,
exact counts, colors after filtering and all ranges at both widths, then writes
screenshots into its printed temporary artifact directory. Its own failure is
reported with a nonzero exit status.

脚本导出合成接口响应，通过 CDP 管道拦截请求，在两种宽度验证整行布局、共用横轴、
悬停/触控/记录点选、实际计数、筛选后颜色及四种范围，并输出临时截图目录；失败返回非零。
