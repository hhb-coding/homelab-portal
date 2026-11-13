# Step 8.03.2 — Network device cards / 网络设备卡

[PR #28](https://github.com/hhb-coding/homelab-portal/pull/28) merged as
`046be3f`. HP deployed and accepted it on 2026-11-12. Live checks covered
status and uptime/Heartbeat ordering, the 1440px 3+2 layout and the 390px view.

PR #28 合并提交 `046be3f` 于 2026-11-12 在 HP 部署并验收，实测了状态、
开机时长与心跳排序，以及 1440px 的 3+2 布局和 390px 窄屏布局。

Device cards now use the summary cards' desktop width and compact typography.
Five cards form **3+2 at 1440px**; at 900px and below they use two columns, and
at 600px and below one column. Floats, row clearing and word wrapping retain the
existing legacy-browser CSS approach. Fields are device name, `networkState`
status, LAN IP, ZeroTier IP and the last Heartbeat in browser-local time.
Only online cards include current boot uptime, using existing `uptime_seconds`
and `uptime()` formatting. Missing addresses retain their explanatory notes;
missing/invalid Heartbeats and unavailable uptime show `—`, while zero uptime
shows `0m`.

设备卡采用摘要卡的桌面宽度与紧凑字号；1440px 五台排成 **3+2**，900px 及以下两列，
600px 及以下单列。沿用浮动、清除行和文字换行，不引入 CSS Grid 或新依赖。
卡片显示设备名、`networkState` 当前状态、LAN IP、ZeroTier IP 和浏览器本地最后心跳。
仅在线卡显示本次开机时长，复用既有 `uptime_seconds` 与 `uptime()`；地址缺失说明保留，
缺失/无效心跳和不可用时长显示 `—`，真实零时长显示 `0m`。

Only a separate Network list is sorted:

1. Online: valid, nonnegative uptime descending; unavailable values last.
2. Unknown: original order.
3. Offline (including paused): last Heartbeat descending; missing/invalid times last.

Original indices break ties explicitly, including on ES5 engines whose native
sort is not stable. The shared device array, Device mini cards, History selector,
API contracts and polling remain unchanged. Heartbeats use the existing strict
`OfflineSeen.parse()` parser, including UTC and explicit timezone offsets.

仅对 Network 使用的独立列表排序：在线按有效非负开机时长降序，缺时长排在在线组末尾；
未知组保留原顺序；离线（含 paused）按最后心跳降序，缺失/无效时间垫底。
同值用原索引保持顺序，兼容原生 sort 不稳定的旧浏览器。共享设备数组、Device 摘要卡、
History 选择器、接口及轮询不变；心跳复用既有严格时间解析器，支持 UTC 与显式时区。

## Validation / 验证

- Existing Network regression: **77 assertions passed**, covering status order,
  uptime/Heartbeat sorting, missing and invalid values, zero uptime, stable ties,
  local timestamps, escaping and preservation of the input/shared/Device order.
- **148 Python tests and all seven CI JavaScript regression programs passed**;
  Python parsing, JavaScript syntax and `git diff --check` also passed.
- Cached Chromium on HP outside the execution sandbox: **1440px 3+2**, **768px
  2+2+1** and **390px single-column** layouts passed. All fields, online-only
  uptime, summary-card width, missing values, long-content wrapping, escaping
  and zero page errors passed. No horizontal overflow at any width.
- Screenshots and JSON report: `/tmp/portal-network-device-cards-LodSdM`.
- Browser checks use synthetic RFC 5737 addresses and intercepted fixture
  responses over a CDP pipe; no server, production data or downloads are needed.

- 现有 Network 回归 **77 项断言通过**，覆盖排序、缺值/无效值、零时长、稳定同值顺序、
  本地时间、转义，以及输入、共享列表和 Device 顺序不变。
- **148 项 Python 测试和七组 CI JavaScript 回归通过**；Python、JS 语法与 diff 检查通过。
- HP 沙箱外缓存 Chromium 验收通过：**1440px 3+2、768px 2+2+1、390px 单列**；
  所有字段、仅在线显示时长、卡片同宽、缺值、长内容换行和转义均通过，无横向溢出或页面异常。
- 上述临时目录保存截图与 JSON 报告。使用示例地址和 CDP 管道合成响应，不依赖生产数据。

The execution sandbox still blocks Chromium sockets (`SIGTRAP` / `setsockopt:
Operation not permitted`). Recheck from an ordinary HP SSH session:

执行沙箱仍限制 Chromium 套接字，可在 HP 普通 SSH 中执行以下一条命令复验：

```sh
cd ~/homelab-portal-08 && ~/.nvm/versions/node/v22.23.3/bin/node tests/test_network_device_cards_browser.js
```

Set `CHROMIUM_BINARY` when the cached browser is elsewhere. The script exits
nonzero on failure and saves width/step, DOM and screenshot diagnostics when
available. This browser acceptance is synthetic; it is not an iOS hardware test.

缓存路径不同时设置 `CHROMIUM_BINARY`。失败返回非零并尽量保存宽度/步骤、DOM 和截图；
本验收为合成样本浏览器检查，不代表 iOS 真机验收。
