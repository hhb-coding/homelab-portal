# HomeLab Portal

A lightweight self-hosted device registry and monitoring dashboard for a home lab.
Python, Flask, SQLite, vanilla JavaScript and native SVG; no frontend framework.

**v0.1.0 release preparation:** application baseline
`f261de40280dfd9cbd57a1c9ef24bf83e4fbd347` (Stages 6-C, 6-D and 6-E).
A version tag and GitHub Release have not been created. A license has not been
selected; see [License](#license). [中文说明](#中文说明) follows the English guide.

## Project overview

Devices report identity and addresses through Heartbeat. Beszel supplies system
metrics and persistent history. HomeLab Portal combines them without using
Beszel's configured host address as the authoritative LAN address.

## Features

- Linux/Python and Windows/PowerShell Heartbeat clients with shared-token authentication.
- Separate LAN and optional ZeroTier IPv4 addresses, last-seen time and SQLite IP-change events.
- Beszel CPU, RAM, disk, load averages, temperature, uptime and device status.
- Full dashboard: Mini Cards, selected Device Details, live and historical SVG trends.
- Lite Style: compact live device cards, without charts or history requests.
- Network tab: counts and reported device addresses; no scanner or topology discovery.
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
git clone https://github.com/hhb-coding/homelab-portal.git
cd homelab-portal
# Explicitly select the currently verified application baseline.
git checkout --detach f261de40280dfd9cbd57a1c9ef24bf83e4fbd347
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
# Copy only if a local configuration does not already exist.
test -e .env || cp .env.example .env
chmod 600 .env
```

No `v0.1.0` tag exists yet. After release, choose the approved release revision.
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
`tools/beszel_probe.py --url http://127.0.0.1:8090` is an optional interactive
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

`/lite` or the Full page's **Lite Style** link opens compact cards: name, status,
LAN IP, optional ZeroTier IP, CPU, RAM, disk and Load 1m. **Full View** returns to `/`.
Lite polls every 5 seconds, has no history requests or charts, and hides current
metrics for offline/unknown devices. Invalid individual entries are skipped.

Lite targets older devices using ES5 and XMLHttpRequest. **Real iOS 9 Safari
validation is still pending**. Earlier Full-page iPad mini 1 / iOS 9 Safari testing
was successful, but does not certify Lite, the new Network view or the 6-E changes.
See [browser validation](docs/legacy-browser-validation.md).

## Network tab

Full's **Network** tab hides Device Details and shows device totals,
online/offline/unknown counts, LAN/ZeroTier address-reporting counts, and
per-device registered addresses and last Heartbeat. Missing LAN addresses and
optional missing ZeroTier addresses have explanatory placeholders.

This is a **summary of device-reported network information**, not a network
scanner, ping sweep, link map or automatic topology discovery. A recorded
address does not establish reachability. No extra network service or API is used.

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
| GET | `/api/dashboard` | Registry + metrics: status, count, sources, metrics_error, devices |
| GET | `/api/history?minutes=60` | One-minute historical samples, 10–360 sample limit, default 60; handled global failures return 502 |

For precise payload fields see `app.py`, `dashboard_service.py` and
`history_service.py`. No IP-event endpoint, scan endpoint or topology API exists.

## Testing

With the virtual environment active:

```sh
python -B -m unittest discover -s tests -v
python -B -c "import ast, pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts]"
node --check static/dashboard.js
node --check static/lite.js
node tests/test_lite.js
node tests/test_network.js
```

Current coverage: **8 Flask/static compatibility tests**, **21 Lite assertions**
and **45 Full/Network assertions**. Flask tests skip `.env`, initialize temporary
SQLite before importing the app and block outgoing HTTP. JavaScript tests use
mock DOM/XHR. GitHub Actions runs these suites and syntax checks without live
Beszel or production credentials. Automated logic/syntax tests do not replace
layout validation on real devices. A basic manual HTML/CSS/JS page is retained
at `docs/legacy-browser-test/helloworld.html`.

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
future directions, not commitments or v0.1.0 features. Real-device Lite/Network
validation and dependency/Beszel-version compatibility testing remain pending.

## License

**No license has been selected and no LICENSE file is provided.** Public source
availability alone is not an explicit open-source license grant. Choose and
approve a license before advertising a licensed open-source release. MIT is a
candidate for a small permissive project; Apache-2.0 is an alternative if an
explicit patent grant is important. Neither is adopted by this preparation.
Compare the primary texts: [MIT](https://opensource.org/license/mit) and
[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

Release material: [changelog](CHANGELOG.md), [draft release notes](docs/releases/v0.1.0.md),
[release checklist](docs/release-checklist.md). Sanitized screenshots of Full,
Network and Lite could be added here later; no screenshots are fabricated.

---

## 中文说明

### 项目简介

HomeLab Portal 是基于 Python、Flask、SQLite、原生 JavaScript 和 SVG 的轻量
自托管设备登记与监控仪表盘。v0.1.0 正在准备，应用基线为
`f261de40280dfd9cbd57a1c9ef24bf83e4fbd347`；尚未创建版本 Tag、Release 或确定许可证。

### 已实现功能

- Linux Python 与 Windows PowerShell 心跳客户端，使用共享 Token 鉴权。
- 分别记录 LAN、可选 ZeroTier IPv4、最后心跳和 IP 变更事件。
- Beszel CPU、内存、磁盘、负载、温度、运行时间和设备状态。
- Full 的 Mini Card、选中设备详情、实时与持久 SVG 趋势图。
- Lite 轻量实时卡片；Network 上报地址与状态摘要。
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

在新目录按英文 Installation 的命令克隆、选择验证过的 Commit、创建 `.venv`、
安装 `requirements.txt` 并仅在 `.env` 不存在时复制示例。不覆盖现有实例、
配置或数据库。当前没有 `v0.1.0` Tag，不要使用尚不存在的版本安装命令。
`app.py` 导入时会初始化配置路径下的 SQLite，无需另一个初始化命令。

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

`/lite` 显示名称、状态、LAN/可选 ZeroTier、CPU、RAM、磁盘和一分钟负载。
每 5 秒刷新，不请求历史或显示图表；离线/未知设备不展示当前指标，支持双向导航。
ES5/XHR 面向老设备，但 **Lite 尚未在 iOS 9 Safari 实测**。Full 曾在 iPad mini 1
的 iOS 9 Safari 成功显示；不代表本次整理、新版 Network 或 Lite 已完成实测。
见 [浏览器验收](docs/legacy-browser-validation.md)，待验收项目不标记 PASS。

### Network Tab / 网络信息页面

显示设备总数、在线/离线/未知数量、LAN/ZeroTier 上报数量、登记地址和最后心跳，
隐藏 Device Details。仅汇总客户端上报的信息，**不是网络扫描器或自动拓扑发现**，
不进行 Ping、不推断连接关系。登记地址不代表可达性，不新增后台服务或 API。

### API 接口

方法、路径、主要返回行为和错误码见英文 API endpoints 表：`/`、`/lite`、
`/api/health`、`/api/devices`、`/api/devices/<device_id>`、`POST /api/heartbeat`、
`/api/metrics`、`/api/dashboard`、`/api/history?minutes=60`。读取 API 没有 Portal 登录，
只有心跳写接口使用共享 Token。健康端点的 HTTP 200 不替代 JSON 数据库状态检查。

### 测试方法

按英文 Testing 命令运行 unittest、Python AST、Node 语法检查和两套前端测试。
当前为 8 项 Flask/静态兼容性测试、21 项 Lite 断言、45 项 Full/Network 断言。
测试使用临时数据库、不读取 `.env`、禁止真实外部 HTTP；前端使用模拟 DOM/XHR。
GitHub Actions 不需要生产凭据或真实 Beszel；自动测试不能替代真实设备布局验收。
保留 `docs/legacy-browser-test/helloworld.html` 基础手工兼容性测试页面。

### 安全注意事项

不提交 `.env`、真实客户端配置、密码/Token/私钥、数据库、私有截图、虚拟环境或缓存。
共享 Token 不等于读取权限控制；页面/API 需仅向可信网络开放，或配置外部访问控制。
HTTP 不加密信息，调试必须关闭；Flask 内置服务器不是公网部署方案。
数据库和配置独立备份；严格的可选字段类型与 IPv4 验证尚未实现，提交日志、
探测结果或截图前先脱敏。`.gitignore` 不等于密钥扫描工具。

### 后续规划

严格的心跳数据校验、Portal 用户认证、连通性检测、拓扑发现、IP 事件浏览界面、
设备管理编辑和加固部署指南均未实现，只是潜在方向，不属于 v0.1.0。
Lite/Network 实机验证及 Beszel/依赖版本兼容性测试待完成。

### 许可证信息

尚未选择许可证、未提供 LICENSE，公开源代码本身不等于开源许可授权。
可考虑 MIT（简洁宽松）或 Apache-2.0（含明确专利授权）；本次不代为采纳任何许可证。
正式宣称开源发布前需由维护者决定并确认。

发布资料：[CHANGELOG](CHANGELOG.md)、[双语 Release Notes 草稿](docs/releases/v0.1.0.md)、
[发布前检查清单](docs/release-checklist.md)。之后可在 README 加入已脱敏的真实
Full/Network/Lite 截图，当前不伪造或添加截图。
