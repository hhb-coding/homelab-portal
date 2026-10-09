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
| `disk_available` | 同一 `d/du/dp` 样本估算可用容量，GiB；不可靠时 JSON null |
| `disk_available_estimated` | 是否有可用估算值；为 true 时前端始终显示 `≈` |
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

## 方案 A：估算可用空间 / Estimated availability

用户确认统一使用 Beszel 现有数据，Linux 与 Windows 采用相同计算方式：

`available = du × (100 - dp) / dp`

这是估算值，不等于 `statvfs` 返回的精确可用空间。
Mini Card 右侧按最新确认只显示数字和 G 单位；详情浅色横条仍标注 `≈`，
深色横条显示实际 `du`，宽度取同一记录的 `dp`。
总容量仍显示文件系统 `d`，不是硬件标称容量；不累计 `efs` 数据盘。
Linux 保留块使 `d-du` 不一定等于可用空间，不能以简单相减替代此公式。

验证规则：`d/du/dp` 必须为有限数字，`d>0`、`0≤du≤d`、`0≤dp≤100`。
当 `dp=0` 或 `du=0` 时不反推；`dp=100` 且 `du>0`、数据合理时可显示 `≈0.0G`。
结果必须有限、非负且不超过 `d`；估算舍入区间的下界必须不超过 `d-du+0.01 GiB`，
确保舍入区间与物理可行范围有交集。这里的 `d-du` 仅用于合理性上限检查，绝不作为可用空间结果。

Beszel 将容量和百分比保留两位小数，按各自 ±0.005 的舍入范围计算估算上下界。
若误差超过 `max(0.1 GiB, 估算值的 5%)`，认为反推不可靠并返回 null，前端显示 `—`。
特别小的 `dp` 可能放大舍入误差，因此不会仅凭非零百分比输出巨大估算值。
容量按一位小数显示，G = GiB、T = TiB；估算标识与说明保留在无障碍文字中，窄区段隐藏文字以免重叠。

本次不修改 Heartbeat 客户端，也不新增 Agent 采集指标。旧 `disk_percent` 保持兼容，
新增估算布尔标记仅供新前端识别近似值。原提交 `abd94f9` 保留，方案 A 通过新增提交实现。
本次修订没有访问外网、安装软件、读取生产配置或调用生产服务。

## 自动验证 / Automated validation

```sh
.venv/bin/python -B -m unittest discover -s tests -v
.venv/node/bin/node tests/test_lite.js
.venv/node/bin/node tests/test_network.js
.venv/node/bin/node tests/test_device_v3.js
.venv/node/bin/node --check static/dashboard.js
git diff --check
```

本轮结果：15 项 Python 测试通过；Lite 33 项断言通过；Network 45 项断言通过；
V3 容量格式化、缺失值、异常值、四行 Mini Card、三行四列详情、Disk 0%/100%/窄区段、
文字宽度、选择和刷新、Live/Historical trends 测试通过。
CI 已增加 V3 JavaScript 测试。

初版 V3 已用本地 Chrome 无头浏览器在 1024px 和 375px 宽度渲染隔离测试页面，三行表格、标签/值背景、
横条文字宽度检查通过。测试页面与截图放在被忽略的 `.venv/`，使用明确的测试样本而非生产数据。
Chrome 验证不替代真实 iOS 9 Safari 验收；生产服务未用于测试。

## 人工浏览器验收 / Manual acceptance

1. 在开发实例的桌面及 iPad mini 1 Safari 打开 Full View，确认四台 Mini Card 的
   LAN/CPU/RAM/DISK 四行、真实容量、ONLINE 状态及点击选择；旋转屏幕后布局正常。
2. 确认没有外层 Device Details 标题或边框；选中设备保留名称和状态，信息三行四列对齐，
   标签浅灰、值白色，Last Seen 为本地时间。
3. 核对 Beszel 主盘为 Linux `/` / Windows C:，确认深灰 Disk 横条的使用率与已用容量；
   Mini Card 可用容量不带 `≈`；详情浅色 Disk 区段仍带 `≈`，不能与 `statvfs` 精确值混淆；
   `dp=0`、缺失或不可靠数据显示 `—`，窄区段文字隐藏且不重叠。
4. Device/Network 来回切换，确认设备选择和自动刷新保留；检查 Live 与 Historical trends、
   Lite 页面、缺失指标及刷新失败后的旧数据保留。

## 本轮四项小范围调整 / Final focused refinements

Dell Host 的真实同一统计记录为 `d=953.87`、`du=223.62`、`dp=23.44`。
设备关联及字段映射正确；公式给出约 `730.390G`，比 `d-du=730.250G` 高 `0.140G`，
原固定 `0.02G` 校验错误拒绝了估算。两位小数的 dp 会放大反推误差：
其舍入区间下界约为 `730.170G`，与物理可行范围有交集。
现在校验该交集，同时保留原舍入误差可靠性门槛，继续使用公式点估算；不截断或替换为 d-du。
例如把该样本 dp 改成 23.43，使舍入区间完全超出物理上限时，仍返回 null。

Mini Card 右侧统一显示一位小数的 G 容量，不显示近似符号；详情保留 `≈` 和估算说明。
CPU、RAM、Disk 横条统一外框高度 24px，内部高度 22px，容量文字垂直居中，原窄区段隐藏逻辑保留。
Lite 使用 `Disk (99.3G) 可用≈54.3%`：括号为实际文件系统容量，
可信可用比例采用 `100-dp`，等价于 `estimated_available/(du+estimated_available)`。
仅在后端确认可信估算、单位及数值合理时显示可用比例；dp=0、缺失、异常、估算不可信或离线时显示 `—`。
旧 `disk_percent` 仍是已用比例，不用于 Lite 可用比例。

验收补充：Dell Host 卡片应出现约 730.4G（随实时数据变化）；详情保留近似标记，
三条横条等高，Lite 的可用比例应与已用比例互补，Network、刷新与趋势保留。
