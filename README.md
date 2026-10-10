# HomeLab Portal

**Give Old Devices a Second Life.** HomeLab Portal is a lightweight,
self-hosted HomeLab monitoring dashboard and device registry built with Python,
Flask, SQLite, vanilla JavaScript and SVG. It combines Heartbeat-reported device
addresses with Beszel system metrics and history, without a frontend framework.

Try an unused iPad, Android phone or tablet as a lightweight HomeLab monitoring
screen. Safari on an iPad mini 1 (user-reported iOS 9.1.3) has been used successfully;
Android and other older browsers have not all been tested on real devices.
See [browser compatibility](#browser-compatibility) for the confirmed scope.

This README describes current `main`, including merged
[PR #2](https://github.com/hhb-coding/homelab-portal/pull/2) (Device UI V3),
[PR #3](https://github.com/hhb-coding/homelab-portal/pull/3) (Network and Updated),
[PR #4](https://github.com/hhb-coding/homelab-portal/pull/4) (offline Last seen) and
[PR #5](https://github.com/hhb-coding/homelab-portal/pull/5) (readable offline layout).
**v0.2.0 is planned**; this is not a tag or Release announcement.
[中文说明](#中文说明) follows the English guide. Licensed under [MIT](LICENSE).

## Features

- Linux/Python and Windows/PowerShell Heartbeat clients with shared-token authentication.
- Separate LAN and optional ZeroTier IPv4 addresses, last-seen time and SQLite IP-change events.
- Beszel CPU, RAM, disk, load averages, temperature, uptime and device status.
- Device UI V3: selectable Mini Cards, capacity-aware details, CPU/RAM/disk bars,
  and live/historical SVG trends.
- Lite Style: compact live device cards, without charts or history requests.
- Network tab: status/address counts, reported LAN/ZeroTier addresses and last Heartbeat.
- Updated warning when the latest valid source observation is over 30 minutes old.
- Offline-only Last seen with a readable separate line and an automatically updated age.
- ES5 JavaScript, XMLHttpRequest, responsive legacy CSS, missing-data placeholders
  and retained-data warnings after request failures.
- Isolated Flask smoke tests, mocked frontend behavior tests and GitHub Actions CI.

## Architecture

```text
Linux / Windows clients -- POST /api/heartbeat --> Flask --> SQLite
                                                   |
                                      Beszel / PocketBase REST API
                                                   |
Browser <--- /api/dashboard and optional /api/history
```

`app.py` defines routes; `config.py` loads `.env`; `db.py` and `schema.sql` manage
`devices` and `ip_events`. `beszel_client.py` normalizes metrics;
`dashboard_service.py` joins them to local devices using `beszel_system_id`;
`history_service.py` reads Beszel one-minute `system_stats` records.

One Beszel system can be linked to at most one Portal device. Heartbeat is
responsible for identity, LAN/ZeroTier addresses and `last_seen`; Beszel supplies
status and metrics. No IP-change history API or editor is currently provided.

## Requirements

- Python **3.12** is the tested CI baseline; Git, pip and Python venv support.
  Other Python versions have not been certified by this project's CI.
- SQLite support in Python, a writable configured database directory and a browser.
- A Beszel Hub/account or token is required for metrics and persistent history;
  the device registry can still be used without configured Beszel credentials.
- Linux clients require Python 3 and `ip` (iproute2); the bundled scheduling units
  require systemd user services. ZeroTier is optional.
- Windows clients require PowerShell and the `Get-NetAdapter`, `Get-NetIPAddress`
  and `Get-NetRoute` networking cmdlets; scheduling uses Windows Task Scheduler.
- Node.js **22** is the CI baseline for frontend tests, not a runtime server dependency.

## Installation

Use a new checkout; do not copy production databases or private `.env` files into
public examples. The systemd templates assume the checkout is `~/homelab-portal`.
Choose another directory if that path already exists, and adjust the templates.

```sh
git clone --branch main https://github.com/hhb-coding/homelab-portal.git
cd homelab-portal
# Record the complete revision used for this installation.
git log -1 --format='%H %s'
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
# Copy only if a local configuration does not already exist.
test -e .env || cp .env.example .env
chmod 600 .env
```

The commands install current `main`, which includes the features described here.
For a reproducible installation, record and select an approved complete commit.
For the planned v0.2.0 release, use its published revision once available; these
instructions do not require a future tag to exist. Existing installations should
back up the database and private configuration before reviewing any upgrade.
Edit `.env` before starting. Importing `app.py` initializes the configured SQLite
schema; no separate database-initialization command is required.

## Configuration

Only these server configuration fields are currently read by `config.py`:

| Field | Code default | Purpose |
|---|---|---|
| `APP_NAME` | `HomeLab Portal` | Page/service name |
| `HOST` | `0.0.0.0` | Listen address; use `127.0.0.1` for local-only access |
| `PORT` | `8088` | HTTP port |
| `DEBUG` | `false` | Keep disabled on shared/live instances |
| `DATABASE_PATH` | `data/homelab.db` | Absolute path or path relative to project root |
| `HEARTBEAT_TOKEN` | empty | Shared secret; an empty value disables Heartbeat requests |
| `BESZEL_URL` | `http://127.0.0.1:8090` | Your Beszel Hub URL |
| `BESZEL_TOKEN` | empty | Preferred authentication method when provided |
| `BESZEL_EMAIL`, `BESZEL_PASSWORD` | empty | Used together if no token is provided |
| `BESZEL_TIMEOUT` | `10` | Per-request timeout in seconds |

Generate a new private Heartbeat token locally, put it in the server `.env` and
the clients' private configurations, and never publish the result:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Replace every `change-me`/example host in client examples. OS environment values
already set take precedence over `.env` values through python-dotenv's default
behavior. A client on another device needs a reachable Portal address; enabling
remote access requires deliberate listen-address, firewall and access-control setup.

To link registered devices to Beszel after the first Heartbeat:

```sh
python tools/link_beszel_devices.py
```

This tool **writes device links**: it automatically matches unambiguous normalized
names, then asks about unresolved devices. Review assignments and back up your
local database first; it does not match devices by their IP address.
`python tools/beszel_probe.py --url http://127.0.0.1:8090` is an optional interactive
connectivity probe. Its operational output can contain private device details;
do not upload that output publicly.

## Running the server

With the virtual environment active and `.env` configured:

```sh
python app.py
```

Open `http://127.0.0.1:8088/` locally (adjust the port if configured differently).
`app.py` starts Flask's built-in server; this is a small trusted-network prototype,
not a hardened public-internet service.

Optional Linux user service, for a **new installation** at `~/homelab-portal`:

```sh
mkdir -p ~/.config/systemd/user
# Do not overwrite an existing local unit without reviewing it.
test -e ~/.config/systemd/user/homelab-portal.service || cp systemd/user/homelab-portal.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now homelab-portal.service
systemctl --user status homelab-portal.service
```

This is an installation example, not an instruction to change an existing
production service. User-service startup at boot depends on your host's user-session
configuration; configure that separately if needed.

## Client Heartbeat

Each client invocation sends **one** Heartbeat; it is not a resident collector.

### Linux

Store a private copy of `clients/heartbeat.env.example` outside the checkout at
`~/.config/homelab-portal/heartbeat.env`. Set `HOMELAB_PORTAL_URL`,
`HOMELAB_HEARTBEAT_TOKEN`, a unique stable `HOMELAB_DEVICE_ID` and optional
`HOMELAB_DISPLAY_NAME`. The client uses the default route for LAN IPv4 and the
first `zt` interface address for optional ZeroTier IPv4.

```sh
mkdir -p ~/.config/homelab-portal
test -e ~/.config/homelab-portal/heartbeat.env || cp clients/heartbeat.env.example ~/.config/homelab-portal/heartbeat.env
chmod 600 ~/.config/homelab-portal/heartbeat.env
# Edit the private copy before running the client.
```

To run it once, load the trusted private environment file in your shell:

```sh
set -a
. ~/.config/homelab-portal/heartbeat.env
set +a
python3 clients/linux-heartbeat.py
```

For periodic execution, install the provided `systemd/user/homelab-heartbeat.service`
and `.timer` in your user systemd directory, review their `%h/homelab-portal`
paths and enable `homelab-heartbeat.timer`. The timer starts after about 30 seconds
and runs again **5 minutes after the previous invocation finishes** (with
`AccuracySec=30s`). This is separate from the browser's 5-second polling interval.
Protect the environment file with owner-only permissions.

For a new client installation at the template's expected path:

```sh
mkdir -p ~/.config/systemd/user
test -e ~/.config/systemd/user/homelab-heartbeat.service || cp systemd/user/homelab-heartbeat.service ~/.config/systemd/user/
test -e ~/.config/systemd/user/homelab-heartbeat.timer || cp systemd/user/homelab-heartbeat.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now homelab-heartbeat.timer
systemctl --user list-timers homelab-heartbeat.timer
```

### Windows

Store a private copy of `clients/heartbeat.windows.example.json` at
`%USERPROFILE%\.config\homelab-portal\heartbeat.json`. Configure `portal_url`,
`heartbeat_token`, `device_id` and `display_name`. From the checkout:

```powershell
powershell.exe -File .\clients\windows-heartbeat.ps1
# A custom private config path is also supported:
# powershell.exe -File .\clients\windows-heartbeat.ps1 -ConfigPath <path>
```

The script reports hostname, default-route LAN IPv4 and optional ZeroTier adapter
IPv4. Configure a recurring Windows Task Scheduler task; the script imposes
**no fixed scheduling interval**. No Windows task installer is bundled.

Example Heartbeat payload (documentation-only addresses, not real device data):

```json
{
  "device_id": "example-device",
  "hostname": "example-host",
  "display_name": "Example Device",
  "lan_ip": "192.0.2.10",
  "zerotier_ip": "198.51.100.10"
}
```

Send it to `POST /api/heartbeat` with `X-Heartbeat-Token`. Use a different stable
`device_id` per device. LAN and ZeroTier addresses are never merged. IP changes
on existing devices are logged independently to SQLite `ip_events`.

## Dashboard

`/` opens the Full dashboard with Device selected. Mini Cards choose the device
shown in Device Details; Device/Network switching retains that selection.
Addresses, local-time last-seen, CPU/RAM/disk, load, temperature and uptime are
shown when available. Missing numbers use a dash; genuine zero values remain zero.

- Live CPU/RAM/Load 1m SVG trends retain up to **120 browser-memory samples**, about
  10 minutes at 5-second polling. Reloading resets live samples.
- Persistent CPU/RAM/Load 1m trends request `/api/history?minutes=60` every
  **60 seconds**, using the latest Beszel one-minute records. The API accepts
  `minutes` clamped to 10–360 as a sample limit; it does not time-filter records,
  so gaps can make the displayed data span more than the nominal window.
- Both views reuse `/api/dashboard`, normally refreshed every **5 seconds**;
  history completion also triggers a dashboard refresh on Full.
- Beszel `up` is online, `down`/`paused` offline, other/missing status unknown.
  Status is not derived from Heartbeat age or a ping check.

Handled API failures keep old displayed data and show a stale-data warning.
Missing monitoring credentials leave the registry usable. Not every transport
failure is normalized by the backend; some errors can return HTTP 500.

## Lite Style

`/lite` or the Full page's **Lite Style** link opens compact cards with status,
name, LAN IP, optional ZeroTier IP, CPU, RAM, disk and Load 1m. On offline cards,
the order is OFFLINE / 离线, Last seen, then the device name and metrics.
**Full View** returns to `/`. Lite polls every 5 seconds, has no history requests
or charts, and hides current metrics for offline/unknown devices. Invalid
individual entries are skipped. Its summary shows the browser refresh time;
it does not use Full's source-age Updated warning.

## Browser compatibility

The UI uses ES5 JavaScript, XMLHttpRequest and responsive CSS without CSS Grid
or CSS variables. Full provides details and SVG charts; Lite reduces rendering
and request work for older screens.

The user previously confirmed Lite working in Safari on a real **iPad mini 1
with user-reported iOS 9.1.3**; an earlier Full page was also confirmed on iOS 9 Safari.
These reports do not certify every later UI change. Latest Device UI V3,
Network, Updated and offline layout changes have automated behavior and Chrome
layout checks; they are not a recorded complete iOS 9.1.3 acceptance test.
Long-duration Lite refresh testing has not been explicitly confirmed.

Unused Android phones, tablets and other old browsers are candidates to try,
not a fully tested compatibility list. Check layout, refresh, navigation and
sleep/resume on your own device. Historical [browser validation notes](docs/legacy-browser-validation.md)
contain a manual checklist; their original pending statements predate the
user-confirmed Lite result described above.

## Network tab

Full's **Network** tab hides Device Details and shows device totals,
online/offline/unknown counts, LAN/ZeroTier address-reporting counts, and
per-device registered addresses and last Heartbeat. Missing LAN addresses and
optional missing ZeroTier addresses have explanatory placeholders.

This is a **summary of device-reported network information**, not a network
scanner, ping sweep, link map or automatic topology discovery. A recorded
address does not establish reachability. No extra network service or API is used.
Desktop label columns are 180px; at 600px and below, labels and values stack
vertically and long addresses wrap.

## Beszel metrics and disk estimates

CPU/RAM percentages, load averages (when supplied), temperature and uptime come
from Beszel `systems.info`; capacities come from the latest `system_stats`
sample (`m`, `d`, `du`, `dp`). Missing metrics remain `—`. Status comes from
Beszel, while device identity, LAN/ZeroTier addresses and Last seen come from
Heartbeat. Versions and platforms may omit fields; no new collector is bundled.

Device UI V3 Mini Cards show LAN, CPU, RAM capacity/usage and disk
capacity/estimated available space. The selected device uses a three-row,
four-column information table on desktop and equal-height 24px CPU/RAM/disk
bars. Disk segments read `USED:` and `FREE:`; narrow labels are hidden to avoid
overlap while accessible descriptions retain values and the estimate meaning.

- G and T mean GiB and TiB, with one decimal; 1024 GiB becomes 1.0T.
- Disk total is Beszel's monitored **primary filesystem**, not nominal hardware
  capacity. Extra `efs` filesystems are not summed. Verify the configured
  filesystem in Beszel; the API fields used here do not identify its mount point.
- Available space is estimated from the **same** `d/du/dp` sample using
  `du × (100 - dp) / dp`. It is not an exact `statvfs` value or simply `d - du`.
- Invalid, missing or unreliable samples, including zero `du` or `dp`, show `—`.
  Rounding intervals must pass feasibility and error checks; very small
  percentages can amplify rounding error. A valid 100% sample can estimate zero.
- Mini Cards display estimated available GiB without an `≈` prefix. Full disk
  segments retain an explicit estimate explanation; Lite labels trusted available
  percentage as `可用≈`, calculated as `100 - dp`. The legacy `disk_percent`
  remains a used percentage and is not Lite's available percentage.

See [Device UI V3 development notes](docs/device-ui-v3.md) for data-source and
rounding details. Those notes also contain intermediate layouts; this README
and current code describe the final behavior.

## Updated source-age warning

Full's Updated uses `/api/dashboard.data_updated_at`: the newest valid timestamp
among registered Heartbeat receipts and linked nonempty Beszel samples.
`server_time` anchors elapsed age; polling does not make old observations new.
It is an aggregate timestamp, not a guarantee that every device or metric is fresh.

When age is **strictly greater than 30 minutes**, a red bold
`已断开更新 XX 分钟` warning appears, with whole minutes rounded down.
A one-second timer continues after request failures and checks again on resume.
Missing, invalid or future times do not create a new warning or overwrite an
existing valid observation; older responses cannot rewind its timestamp.
Portal ONLINE, Database READY and Beszel status keep their separate meanings.

## Offline Last seen

Beszel `down`/`paused` devices show an offline-only hint; ONLINE and UNKNOWN do
not. Full Mini Cards show the name first, bold red OFFLINE second, and
`Last seen: 21:30 (1h 37m ago)` third, followed by the divider and LAN/CPU/RAM/DISK.
Lite shows bold red OFFLINE / 离线, then Last seen, then the name and metrics.
Last seen is a separate **13px, normal-weight, dark gray** line. Mini Cards are
kept equal in height when offline hints are present and resize with the window.

Both views share `static/offline-seen.js`. The source is the last valid Heartbeat
receipt (`last_seen`, SQLite UTC), not the exact shutdown/disconnection time or
the length of an outage. Heartbeat can remain recent while Beszel reports offline.
Times display in the browser's local timezone. Crossing a local calendar date
adds the full date; multi-day ages include days, hours and minutes. Missing,
invalid or future values, or an unavailable server clock, show `Last seen: —`.
Strict parsing handles UTC and explicit offsets without relying on legacy
`Date.parse`. Age updates every second, including after failed requests and on
resume; online recovery removes the hint.

Updated and Last seen use server-clock anchors plus elapsed wall/monotonic time
where available. Keep the server clock accurate. A large manual forward change
to the browser clock during failed requests can temporarily overstate age;
the next valid response recalibrates it.

## API endpoints

Read endpoints currently have **no Portal login/access-control layer**.

| Method | Path | Behavior |
|---|---|---|
| GET | `/` | Full dashboard HTML |
| GET | `/lite` | Lite HTML |
| GET | `/api/health` | Service status and database readiness; inspect the JSON database field, not only HTTP 200 |
| GET | `/api/devices` | `{ "devices": [...] }` registered devices |
| GET | `/api/devices/<device_id>` | One device or HTTP 404 |
| POST | `/api/heartbeat` | Token-authenticated registration/update and address-change flags; 400 invalid body/ID, 401 invalid token, 503 no server token |
| GET | `/api/metrics` | Beszel normalized systems; 503 missing credentials, 502 handled Beszel API errors |
| GET | `/api/dashboard` | Registry + metrics: status, count, sources, metrics_error, devices, data_updated_at, server_time |
| GET | `/api/history?minutes=60` | One-minute historical samples, 10–360 sample limit, default 60; handled global failures return 502 |

For precise payload fields see `app.py`, `dashboard_service.py` and
`history_service.py`. No IP-event endpoint, scan endpoint or topology API exists.

## Testing

With the virtual environment active and Node.js 22 available:

```sh
python -B -m unittest discover -s tests -v
python -B -c "import ast, pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts]"
node --check static/dashboard.js
node --check static/lite.js
node --check static/offline-seen.js
node tests/test_lite.js
node tests/test_network.js
node tests/test_device_v3.js
node tests/test_freshness.js
node tests/test_offline_seen.js
```

Current coverage: **17 Python tests** across Flask/static compatibility, Beszel
capacity estimates and source freshness; **33 Lite assertions**, **45 Network
assertions**, and separate Device UI V3, Updated and offline Last seen suites.
The isolated Python suite uses temporary SQLite, skips local `.env` loading and
blocks live HTTP. JS behavior tests use mock DOM/XHR, including failures,
selection, timestamps, clock skew, resume and online recovery. GitHub Actions
runs these suites and syntax checks without production credentials.

Optional real Chrome layout regression (Node 22 built-ins; Chrome must be
installed separately):

```sh
CHROME_BIN=/opt/google/chrome/chrome node tests/test_offline_layout.js
# Adjust CHROME_BIN to your local Chrome executable.
```

It uses a random local port, fixture APIs and a temporary browser profile;
it does not contact production instances. Full/Lite checks cover
**320, 375, 768 and 1024px**, long names, missing/multi-day timestamps,
13px normal-weight dark gray hints on separate lines, equal Mini Card heights,
overflow, timer updates and online recovery. This layout test is optional and
is not part of the current CI workflow. Automated results do not replace iOS
or Android hardware acceptance. A basic manual test page remains at
[legacy browser test](docs/legacy-browser-test/helloworld.html).

[Fresh installation acceptance](docs/installation-validation.md) records an
earlier revision's checks and limitations; its branch/release instructions and
test counts are historical, not the installation guide for current main.

## Security notes

- Keep `.env`, real client configs, passwords, tokens, private keys, databases,
  screenshots with private details, venvs and caches out of Git. Examples contain
  placeholders; replace them locally. `.gitignore` is not a secrets scanner.
- Heartbeat uses a shared token but read APIs and dashboard have no built-in login;
  expose the service only within a trusted network or behind external access
  control. Plain HTTP does not encrypt tokens or private device information.
- Leave `DEBUG=false`. Flask's built-in server is not a public-internet deployment
  solution. No public deployment or reverse-proxy configuration is bundled.
- Protect and back up your SQLite database and private configuration independently.
  Beszel history stays in Beszel, not the Portal database.
- Tokens/configuration should not be pasted into issue reports; sanitize probe
  output, logs and screenshots. Device display data is HTML-escaped by the UI,
  but Heartbeat only validates JSON object and nonempty string device ID;
  optional fields have no strict type/IPv4 schema validation yet.

## Roadmap

Not implemented: strict Heartbeat payload validation, Portal user authentication,
network reachability checks, topology discovery, IP-event browsing UI, a device
management editor and a hardened public deployment guide. These are possible
future directions, not commitments for v0.2.0. Complete latest-UI hardware
acceptance, long-duration refresh testing and broader Android/browser,
dependency and Beszel-version compatibility testing remain open.

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Hongbin He

See the [changelog](CHANGELOG.md) for historical changes. Older release-preparation
documents are historical drafts, not the current installation or compatibility
reference. No v0.2.0 tag or Release is created by this documentation update.

---

## 中文说明

### 项目简介

**Give Old Devices a Second Life — 让旧设备重获新生。** HomeLab Portal 是基于
Python、Flask、SQLite、原生 JavaScript 和 SVG 的轻量自托管 HomeLab 监控仪表盘与
设备登记工具，将 Heartbeat 上报的地址与 Beszel 系统指标、历史趋势整合在一起，无需前端框架。

可以尝试把闲置 iPad、安卓手机或平板作为轻量 HomeLab 监控屏幕。
iPad mini 1 / 用户报告的 iOS 9.1.3 Safari 已有实际使用确认，但 Android 和其他老旧浏览器
尚未全部经过真机验证，具体范围见下方兼容性说明。

本文对应当前 main，包含已合并的 PR #2（Device UI V3）、#3（Network/Updated）、
#4（OFFLINE Last seen）、#5（离线提示分行样式）。**v0.2.0 为计划版本**，不是
已发布 Tag 或 Release 的声明。本项目采用 [MIT License](LICENSE)。

### 已实现功能

- Linux Python 与 Windows PowerShell 心跳客户端，使用共享 Token 鉴权。
- 分别记录 LAN、可选 ZeroTier IPv4、最后心跳和 IP 变更事件。
- Beszel CPU、内存、磁盘、负载、温度、运行时间和设备状态。
- Device UI V3：可选择的 Mini Card、容量信息、详情横条和实时/历史 SVG 趋势。
- Lite 轻量实时卡片；Network 上报地址与状态摘要。
- Full Updated 的源数据超过 30 分钟警告；OFFLINE 独立行 Last seen 与自动更新年龄。
- ES5/XHR、响应式旧式 CSS、缺失数据提示、失败保留旧数据及自动测试/CI。

### 系统架构

客户端通过 `POST /api/heartbeat` 写入 Flask/SQLite，Portal 调用 Beszel REST API
获取指标和历史，再由 `/api/dashboard` 与 `/api/history` 提供给浏览器。
设备通过唯一的 `beszel_system_id` 关联；Heartbeat 是设备身份、地址和最后心跳
的来源，Beszel 是状态与指标的来源，不把 Beszel host 当成真实 LAN 地址。
SQLite 表为 `devices`、`ip_events`，目前没有 IP 事件查询 API。

### 系统要求

服务器 CI 基线为 Python 3.12，需 Git、pip、venv、Python SQLite 和可写数据目录。
指标/历史需要 Beszel Hub 账号或 Token；无 Beszel 时仍可使用设备登记。
Linux 客户端需要 Python 3 与 iproute2，systemd 用于可选定时运行；Windows
客户端需要 PowerShell 与相应网络 cmdlet。ZeroTier 可选。前端测试 CI 使用
Node.js 22，运行服务器不需要 Node.js；其他版本尚未完整认证。

### 安装步骤

在新目录按英文 Installation 命令使用 `git clone --branch main`，记录完整提交号、
创建 `.venv`、安装 `requirements.txt`，仅在 `.env` 不存在时复制示例。
当前 main 已包含本文描述的功能，不使用旧开发或发布准备分支安装。
不覆盖已有实例、配置或数据库；升级前独立备份数据库和私有配置。
可复现安装应选择已批准的完整不可变提交；计划中的 v0.2.0 发布后再使用其实际发布
修订，不依赖尚未发布的 Tag。`app.py` 导入时初始化 SQLite，无需额外初始化命令。

### 配置方法

完整字段及代码默认值见上方 Configuration 表。`.env` 配置名称、监听地址、
端口、调试开关、数据库路径、Heartbeat Token 和 Beszel URL/认证/超时。
空 `HEARTBEAT_TOKEN` 会禁用上报；本地生成随机 Token，在服务器与客户端保持一致。
Beszel 优先使用 Token，否则使用邮箱和密码。环境变量优先于 `.env`。
本机访问建议 `HOST=127.0.0.1`，其他设备访问需明确配置监听与防火墙。
首次心跳后运行 `python tools/link_beszel_devices.py` 建立关联；该工具会写入数据库，
先备份并核对名称自动匹配和人工选择。探测工具输出可能包含私有设备信息，不应公开。

### 启动服务

激活虚拟环境后运行 `python app.py`，本机访问 `http://127.0.0.1:8088/`。
提供的可选 systemd 用户服务默认安装位置为 `~/homelab-portal`；其他位置需
自行调整模板，不覆盖已有本地 unit。服务使用 Flask 内置服务器，适合可信网络
原型；不是面向公网的加固方案。不要将新安装示例直接用于变更既有生产实例。

### 客户端心跳上报

Linux 私有配置位于 `~/.config/homelab-portal/heartbeat.env`，字段为
`HOMELAB_PORTAL_URL`、`HOMELAB_HEARTBEAT_TOKEN`、`HOMELAB_DEVICE_ID`、
`HOMELAB_DISPLAY_NAME`。加载可信环境文件后运行 `python3 clients/linux-heartbeat.py`。
示例 systemd timer 约 30 秒后首次运行，前次完成约 **5 分钟后**再次上报，
`AccuracySec=30s`。客户端每次执行只发送一次心跳。

Windows 私有 JSON 默认位于 `%USERPROFILE%\.config\homelab-portal\heartbeat.json`，
字段为 `portal_url`、`heartbeat_token`、`device_id`、`display_name`。
用 `powershell.exe -File .\clients\windows-heartbeat.ps1` 运行，支持 `-ConfigPath`。
定时任务需用户在 Task Scheduler 配置；脚本没有固定上报周期或任务安装器。
每台设备使用稳定且唯一的 ID；LAN 和 ZeroTier 地址独立保存，变更记录在 SQLite。

### 仪表盘

`/` 默认显示 Device，保留 Mini Card 选择、详情和 SVG 图表，切换 Network
保留选中设备。网页每 **5 秒**刷新，与客户端约 5 分钟上报无关。
实时趋势保留最多 120 个浏览器内样本（约 10 分钟），刷新页面重置。
历史趋势每 **60 秒**读取 Beszel 的最新 60 条一分钟记录；`minutes` 为 10–360
条样本上限，未按时间过滤，因此缺测时可能跨越更长时间。历史保存在 Beszel。
在线状态来自 Beszel，不通过心跳年龄或 Ping 推断。缺失指标显示横线，零值显示零；
处理过的请求失败保留旧数据显示过期提示，部分传输错误仍可能返回 HTTP 500。

### Lite Style / 旧设备兼容页面

`/lite` 显示状态、名称、LAN/可选 ZeroTier、CPU、RAM、磁盘和一分钟负载。
离线卡片按 OFFLINE / 离线、Last seen、名称和指标排列。每 5 秒刷新，
不请求历史或显示图表；离线/未知设备不展示当前指标，支持返回 Full。
Lite 摘要显示浏览器刷新时间，不使用 Full 的源数据年龄 Updated 警告。

ES5/XHR 与不使用 CSS Grid、CSS 变量的响应式 CSS 面向旧设备。
**此前用户已确认 iPad mini 1（用户报告的 iOS 9.1.3）Safari 使用 Lite 正常**，
早期 Full 也曾在 iOS 9 Safari 正常显示。这些结果不代表后续全部改动通过真机验收。
最新 Device UI V3、Network、Updated 和离线分行布局已有行为/Chrome 自动检查，
尚不能写成完整的 iOS 9.1.3 真机验收结果；Lite 长时间刷新也未明确确认。
安卓手机、平板及其他旧浏览器可尝试使用，但不是已完整实测的兼容性清单。
请在自己的设备检查布局、刷新、导航和休眠恢复。
[历史浏览器验收清单](docs/legacy-browser-validation.md) 的初始待验收描述早于上述 Lite 确认。

### Network Tab / 网络信息页面

显示设备总数、在线/离线/未知数量、LAN/ZeroTier 上报数量、登记地址和最后心跳，
隐藏 Device Details。仅汇总客户端上报的信息，**不是网络扫描器或自动拓扑发现**，
不进行 Ping、不推断连接关系。登记地址不代表可达性，不新增后台服务或 API。
桌面标签列为 180px；600px 及以下采用标签和值上下排列，长地址可换行。

### Beszel 指标与磁盘估算限制

CPU/RAM 百分比、可用的系统负载、温度和运行时间来自 Beszel `systems.info`；
容量取最新 `system_stats` 的 `m/d/du/dp`。不同平台或版本可能缺少字段，缺失显示 `—`。
Device UI V3 Mini Card 显示 LAN、CPU、RAM 总容量/使用率、磁盘容量/估算可用空间；
选中设备桌面信息表为三行四列，CPU/RAM/Disk 横条统一 24px 高。
Disk 标注 `USED:` 和 `FREE:`，窄区段隐藏文字但保留无障碍数值与估算含义。

G/T 为 GiB/TiB，保留一位小数，1024 GiB 起显示 T。磁盘总量是 Beszel 监控的
主文件系统容量，不是硬件标称容量，不累计 `efs` 数据盘；使用的 API 字段不提供挂载点，
需自行核对 Beszel 配置。可用空间采用同一 `d/du/dp` 样本的
`du × (100 - dp) / dp` 估算，不是 `statvfs` 精确值，也不是简单的 `d-du`。
缺失、非法、`du/dp` 为零或舍入误差不可靠时显示 `—`；有效 100% 样本可估算为零。
Mini Card 可用容量不带 `≈`，Full Disk 区段下方保留估算说明；Lite 的可信可用
比例显示 `可用≈`，采用 `100-dp`。旧 `disk_percent` 仍为已用比例。
[Device UI V3 开发记录](docs/device-ui-v3.md) 包含中间样式；最终行为以当前代码和本文为准。

### Updated / 数据更新时间

Full Updated 来自 `/api/dashboard.data_updated_at`：已登记设备 Heartbeat 与
关联 Beszel 非空统计样本中最新的有效时间。`server_time` 校准年龄；
网页轮询不会使旧数据变新，汇总时间不代表每台设备、每项指标都新鲜。
数据年龄**严格超过 30 分钟**时显示红色粗体“已断开更新 XX 分钟”，分钟向下取整。
独立一秒计时器在请求失败后继续更新，恢复页面时重新检查；缺失、非法、未来时间
不创建新警告、不覆盖已有有效时间，旧响应不能倒退时间。
Portal ONLINE、Database READY 和 Beszel 状态含义各自独立。

### OFFLINE Last seen / 最后有效心跳

仅 Beszel `down/paused` 显示提示，ONLINE/UNKNOWN 不显示。
Full Mini Card 先显示名称，再显示红色粗体 OFFLINE，第三行独立显示
`Last seen: 21:30 (1h 37m ago)`，之后才是分隔线和 LAN/CPU/RAM/DISK。
Lite 先 OFFLINE / 离线，下一行 Last seen，然后名称和指标。
Last seen 为 **13px、正常字重、深灰色**；有离线提示时 Mini Card 按最高卡片等高，缩放时重算。

两种视图共用 `static/offline-seen.js`，来源为 SQLite UTC 的最后有效 Heartbeat
接收时间 `last_seen`，不是精确关机/断网时间或已离线时长；Beszel 离线时心跳仍可能很新。
按浏览器本地时区显示；跨本地日期附完整日期，多日显示天/小时/分钟。
缺失、非法、未来时间或无可靠服务器时间时显示 `Last seen: —`，严格解析 UTC/时区偏移，
不依赖旧 Safari `Date.parse`。每秒更新，请求失败、页面恢复仍继续；恢复在线后移除提示。
Updated 与 Last seen 采用服务器时间加墙钟/可用单调时间；服务器时钟需准确。
持续请求失败时大幅手动前调浏览器时钟可能暂时放大年龄，下次有效响应重新校准。

### API 接口

方法、路径、主要返回行为和错误码见英文 API endpoints 表：`/`、`/lite`、
`/api/health`、`/api/devices`、`/api/devices/<device_id>`、`POST /api/heartbeat`、
`/api/metrics`、`/api/dashboard`、`/api/history?minutes=60`。读取 API 没有 Portal 登录，
只有心跳写接口使用共享 Token。健康端点的 HTTP 200 不替代 JSON 数据库状态检查。

### 测试方法

按英文 Testing 命令运行 unittest、Python AST、Node 语法及五套前端行为测试。
当前有 **17 项 Python 测试、33 项 Lite 断言、45 项 Network 断言**，另有
Device UI V3、Updated 和 OFFLINE Last seen 专项测试。
Python 隔离测试使用临时数据库、不加载本地 `.env`、禁止真实 HTTP；JS 使用模拟 DOM/XHR。
CI 运行这些行为与语法检查，不需要生产凭据。
可选 `test_offline_layout.js` 需要独立安装 Chrome 和 Node 22，使用随机本地端口、
测试样本 API 和临时浏览器配置，不访问生产实例，也不在当前 CI 中执行。
覆盖 Full/Lite 的 320/375/768/1024px、长名称、多日/缺失时间、13px 分行样式、
四卡等高、无溢出、持续更新和在线恢复；自动测试不能替代 iOS/Android 真机验收。
保留 [基础手工浏览器测试页](docs/legacy-browser-test/helloworld.html)。
[早期全新安装验收](docs/installation-validation.md) 的分支命令和测试数量仅为历史记录。

### 安全注意事项

不提交 `.env`、真实客户端配置、密码/Token/私钥、数据库、私有截图、虚拟环境或缓存。
共享 Token 不等于读取权限控制；页面/API 需仅向可信网络开放，或配置外部访问控制。
HTTP 不加密信息，调试必须关闭；Flask 内置服务器不是公网部署方案。
数据库和配置独立备份；严格的可选字段类型与 IPv4 验证尚未实现，提交日志、
探测结果或截图前先脱敏。`.gitignore` 不等于密钥扫描工具。

### 后续规划

严格的心跳数据校验、Portal 用户认证、连通性检测、拓扑发现、IP 事件浏览界面、
设备管理编辑和加固部署指南均未实现，只是潜在方向，不是 v0.2.0 承诺。
最新 UI 的完整真机验收、长时间刷新、更多 Android/旧浏览器及 Beszel/依赖版本验证仍需继续。

### 许可证信息

本项目采用 [MIT License](LICENSE)。

Copyright (c) 2026 Hongbin He

历史变更见 [CHANGELOG](CHANGELOG.md)。旧发布准备文档为历史草稿，
不是当前安装或兼容性依据。本次文档更新不创建 v0.2.0 Tag 或 Release。
