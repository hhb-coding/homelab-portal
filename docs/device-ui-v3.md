# Device UI V3 验证记录 / Validation notes

基线为 `bd4892b4d419198891e3cab7eab9627f9bd5ff25`，分支为 `feature/device-ui-v3`。
开发、依赖安装、自动测试和浏览器测试均在开发目录进行；没有启动或重启生产服务。

## 数据来源 / Data sources

LAN、ZeroTier 和 Last Seen 继续来自 SQLite Heartbeat，关联继续使用
`beszel_system_id`。在线状态、CPU、RAM 百分比、温度、Uptime 和负载沿用原来源。

2026-10-09 从开发目录只读核查现有 Beszel API：四台设备的最新 `type='1m'`
记录均有 `stats.m`、`stats.d`、`stats.du`、`stats.dp`，没有可用空间字段。
探测只输出版本、字段名和容量，没有输出密码或 Token，也没有保存认证响应。
设备 Agent 版本为 0.20.0 和 0.18.8。

新增 `/api/dashboard` 和 Beszel snapshot 字段：

| 字段 | 来源与单位 |
| --- | --- |
| `memory_total` | 同一统计记录的 `stats.m`，GiB |
| `disk_total` | `stats.d`，主文件系统容量，GiB；并非硬件标称容量 |
| `disk_used` | `stats.du`，主文件系统已用容量，GiB |
| `disk_usage_percent` | 同一记录的 `stats.dp`，避免与较新的 `systems.info.dp` 混用 |
| `disk_available` | 当前源缺失，返回 JSON null，UI 显示 `—` |
| `capacity_unit` | `GiB`，前端确认单位后显示容量 |

原 `disk_percent` 字段保留其原来源和语义，Lite、历史和原 API 消费者保持兼容。
容量显示 G = GiB、T = TiB，均保留一位小数，达到 1024 GiB 时使用 T。
不将硬件标称 GB 换算或补齐成某个示例容量，不累计 `stats.efs` 数据盘。

官方依据：

- [Beszel 0.20.0 字段定义](https://github.com/henrygd/beszel/blob/v0.20.0/internal/entities/system/system.go)
- [GiB 换算：bytes / 1073741824](https://github.com/henrygd/beszel/blob/v0.20.0/agent/utils/utils.go)
- [0.20.0 主文件系统与磁盘采集](https://github.com/henrygd/beszel/blob/v0.20.0/agent/disk.go)
- [0.18.8 主文件系统与磁盘采集](https://github.com/henrygd/beszel/blob/v0.18.8/agent/disk.go)

Beszel 默认从 Linux `/`、Windows `SystemDrive`（通常 C:）采集主文件系统；
`FILESYSTEM` 配置可覆盖主文件系统，不可变 Linux 也可能使用 `/sysroot`。
这些版本的 API 统计没有导出挂载点，本次沿用现有 Beszel 主盘数据，未更改 Agent 配置。
人工验收应确认各设备 Beszel 主盘确为 `/` 或 C:，若有覆盖配置则另行处理，不能仅凭容量猜盘。

## 缺失字段与后续方案 / Missing metric

当前只有 `disk_available` 无法直接取得。Linux 保留块等原因使 `total-used`
不一定等于用户可用空间；`dp` 也不一定等于 `du/d`。因此不反推可用容量，不强行相加，
不把文件系统容量当作标称硬盘容量。深色横条宽度取同一采样的真实 `dp`，文字取 `du`；
浅色部分的可用容量显示 `—`，有明确的未上报提示。

本次无需更新 Heartbeat 客户端。若后续要求显示真实可用空间，需要另行批准采集方案：
优先在 Beszel Agent/Hub 中暴露同一主文件系统、同一时刻的真实 available/free 指标，
明确 Linux `Bavail` 和 Windows C: 可用空间语义，再统一容量与使用率口径。
本次没有猜测新 Beszel 字段，也没有修改所有 Heartbeat 客户端。

## 自动验证 / Automated validation

```sh
.venv/bin/python -B -m unittest discover -s tests -v
.venv/node/bin/node tests/test_lite.js
.venv/node/bin/node tests/test_network.js
.venv/node/bin/node tests/test_device_v3.js
.venv/node/bin/node --check static/dashboard.js
git diff --check
```

结果：12 项 Python 测试通过；Lite 21 项断言通过；Network 45 项断言通过；
V3 容量格式化、缺失值、异常值、四行 Mini Card、三行四列详情、Disk 0%/100%/窄区段、
文字宽度、选择和刷新、Live/Historical trends 测试通过。
CI 已增加 V3 JavaScript 测试。

本地 Chrome 无头浏览器在 1024px 和 375px 宽度渲染隔离测试页面，三行表格、标签/值背景、
横条文字宽度检查通过。测试页面与截图放在被忽略的 `.venv/`，使用明确的测试样本而非生产数据。
Chrome 验证不替代真实 iOS 9 Safari 验收；生产服务未用于测试。

## 人工浏览器验收 / Manual acceptance

1. 在开发实例的桌面及 iPad mini 1 Safari 打开 Full View，确认四台 Mini Card 的
   LAN/CPU/RAM/DISK 四行、真实容量、ONLINE 状态及点击选择；旋转屏幕后布局正常。
2. 确认没有外层 Device Details 标题或边框；选中设备保留名称和状态，信息三行四列对齐，
   标签浅灰、值白色，Last Seen 为本地时间。
3. 核对 Beszel 主盘为 Linux `/` / Windows C:，确认深灰 Disk 横条的使用率与已用容量；
   当前缺失可用空间显示 `—`，窄区段文字隐藏且不重叠。
4. Device/Network 来回切换，确认设备选择和自动刷新保留；检查 Live 与 Historical trends、
   Lite 页面、缺失指标及刷新失败后的旧数据保留。
