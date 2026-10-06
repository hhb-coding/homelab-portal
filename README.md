# HomeLab Portal

A lightweight self-hosted dashboard for HomeLab device discovery,
IP tracking, heartbeat monitoring, and system metrics.

一个轻量级的自托管 HomeLab 设备、IP 与系统监控门户。

## Project Goals

HomeLab Portal combines:

- LAN IP tracking
- Optional ZeroTier IP tracking
- Device heartbeat monitoring
- Beszel system metrics
- Lightweight dynamic dashboard
- Legacy browser compatibility

Future dashboard metrics include:

- CPU usage
- Memory usage
- Disk usage
- Load average
- Device online/offline state
- LAN IP address
- Optional ZeroTier IP address
- Last seen time

## Architecture

HomeLab devices send lightweight heartbeat information to HomeLab Portal.

Beszel continues to collect system performance metrics.

HomeLab Portal combines both data sources into one lightweight web interface.

Architecture overview:

    HomeLab Devices
          |
          | Heartbeat
          v
    HomeLab Portal
    Flask + SQLite
          |
          | REST API
          v
      Beszel Hub

## Legacy Browser Support

The frontend intentionally avoids unnecessary modern JavaScript frameworks
and modern browser-only features.

The goal is to remain usable on older devices and browsers where practical,
including legacy Safari.

## Development Status

Current phase:

Step 1 - Project Foundation

Completed:

- Python virtual environment
- Flask installation
- SQLite schema
- Basic HTML dashboard
- Legacy browser compatibility test

Planned:

- Device heartbeat
- Beszel integration
- Live metrics
- Dynamic charts
- Production systemd service

## Security and Configuration

Environment-specific configuration, passwords, API tokens, private URLs,
and other secrets must never be committed to Git.

The public repository provides:

    .env.example

Each installation should create its own private:

    .env

The private .env file is excluded by .gitignore.

## Technology Stack

- Python 3
- Flask
- SQLite
- HTML
- CSS
- Vanilla JavaScript
- Beszel REST API

## License

A license will be selected before the first public release.


---

## Device Heartbeat and IP Registry

HomeLab Portal includes a lightweight heartbeat system for tracking devices across a home lab.

HomeLab Portal 包含一个轻量级设备 Heartbeat 系统，用于记录家庭实验室中的设备地址和在线状态。

### Features

- Linux heartbeat client written in Python
- Windows heartbeat client written in PowerShell
- Automatic LAN IPv4 detection
- Optional ZeroTier IPv4 detection
- LAN and ZeroTier addresses are stored separately
- Device `last_seen` tracking
- LAN and ZeroTier IP change history
- Shared-token authentication for heartbeat clients
- Linux automation with a systemd user timer
- Windows automation with Task Scheduler

### Architecture

```text
Linux / Windows devices
        |
        | heartbeat
        v
+-----------------------+
| HomeLab Portal        |
| Flask REST API        |
+-----------+-----------+
            |
            v
+-----------------------+
| SQLite                |
|                       |
| devices               |
| ip_events             |
+-----------------------+
```

### Device Address Model

HomeLab Portal treats LAN and ZeroTier addresses as separate network identities.

- `lan_ip`: primary local-network IPv4 address
- `zerotier_ip`: optional ZeroTier overlay address

A ZeroTier address never overwrites or replaces the LAN address.

局域网地址是设备的主要本地地址；ZeroTier 地址作为独立的可选地址保存，不会覆盖或替代 LAN IP。

### Heartbeat API

Heartbeat clients send device information to:

```text
POST /api/heartbeat
```

Example payload:

```json
{
  "device_id": "example-device",
  "hostname": "example-host",
  "display_name": "Example Device",
  "lan_ip": "192.168.1.10",
  "zerotier_ip": "10.0.0.10"
}
```

Authentication uses the HTTP header:

```text
X-Heartbeat-Token
```

The real token must never be committed to Git.

### Linux Client

Linux client:

```text
clients/linux-heartbeat.py
```

Public example configuration:

```text
clients/heartbeat.env.example
```

Example systemd user units:

```text
systemd/user/homelab-heartbeat.service
systemd/user/homelab-heartbeat.timer
```

Device-specific configuration should be stored outside the repository, for example:

```text
~/.config/homelab-portal/heartbeat.env
```

### Windows Client

Windows heartbeat client:

```text
clients/windows-heartbeat.ps1
```

Example configuration:

```text
clients/heartbeat.windows.example.json
```

A device-specific configuration can be stored at:

```text
%USERPROFILE%\.config\homelab-portal\heartbeat.json
```

The Windows client can be executed periodically using Windows Task Scheduler.

### Security

Do not commit:

- `.env`
- heartbeat tokens
- passwords
- private credentials
- runtime databases
- environment-specific configuration

Only example configuration files should be committed.

### Current Development Status

Implemented:

- Project skeleton
- Flask application
- SQLite database
- Device heartbeat API
- Linux heartbeat client
- Windows heartbeat client
- LAN / ZeroTier address tracking
- IP change history
- Automatic Linux heartbeat scheduling
- Automatic Windows heartbeat scheduling

Planned next:

- Beszel API integration
- CPU / memory / disk / load metrics
- Unified dashboard API
- Legacy-browser-compatible live dashboard

## Beszel Metrics Integration

HomeLab Portal combines two data sources:

- **Heartbeat / SQLite**: device identity, LAN IP, optional ZeroTier IP, and last-seen time.
- **Beszel**: CPU, memory, disk, load average, temperature, uptime, and status.

Devices are linked using `beszel_system_id`. A database-level unique index prevents one Beszel system from being assigned to multiple Portal devices.

### IP design rule

Beszel's configured host/IP is not treated as the authoritative LAN IP because DHCP addresses may change. HomeLab Portal uses Heartbeat for LAN/ZeroTier addresses and Beszel for performance metrics.

APIs:

- `GET /api/metrics` — normalized Beszel metrics.
- `GET /api/dashboard` — unified device registry + metrics.

### 中文说明

HomeLab Portal 将 Heartbeat/SQLite 与 Beszel 合并：前者负责设备身份、LAN IP、可选 ZeroTier IP 和 Last Seen；后者负责 CPU、内存、磁盘、Load、温度、Uptime 和在线状态。

两套数据通过 `beszel_system_id` 关联，并通过数据库唯一索引避免一个 Beszel 设备被重复绑定。Beszel 中配置的 host/IP 不作为真实 LAN IP；真实 LAN/ZeroTier 地址始终来自 Heartbeat。

## Live Dashboard UI

Step 4 adds a lightweight browser dashboard powered by the unified `/api/dashboard` endpoint.

Features:

- shows registered HomeLab devices in one page
- displays LAN IP and optional ZeroTier IP
- shows Beszel online/offline status
- displays CPU, memory, disk, load average, temperature, and uptime
- refreshes automatically every 5 seconds
- converts UTC heartbeat timestamps to the browser's local time
- uses ES5-style JavaScript and `XMLHttpRequest` for legacy Safari / iOS 9 compatibility
- has been tested successfully on a legacy iPad mini running iOS 9

### 中文说明

第四步加入了轻量级动态 Dashboard 首页，并使用统一的 `/api/dashboard` 作为数据源。

主要功能：

- 在一个页面显示所有 HomeLab 设备
- 显示 LAN IP 和可选 ZeroTier IP
- 显示 Beszel 在线/离线状态
- 显示 CPU、内存、磁盘、Load Average、温度和 Uptime
- 每 5 秒自动刷新
- 将数据库中的 UTC Heartbeat 时间转换为浏览器本地时间
- 使用 ES5 风格 JavaScript 和 `XMLHttpRequest`，兼容旧版 Safari / iOS 9
- 已在运行 iOS 9 的老款 iPad mini 上实机测试通过

<!-- DASHBOARD-HISTORY-SECTION -->

## Dashboard monitoring / 仪表盘监控

HomeLab Portal provides two complementary metric timelines for each device.

HomeLab Portal 为每台设备提供两种互补的监控时间尺度。

### Live trends / 实时趋势

- Polls the unified dashboard API every 5 seconds.
- Keeps up to 120 samples in browser memory.
- Represents approximately the latest 10 minutes.
- Displays CPU, RAM and Load 1m.
- Uses lightweight native SVG charts without Chart.js or other front-end frameworks.
- Live samples are intentionally browser-local and reset when the page is reloaded.

- 每 5 秒轮询一次统一 Dashboard API。
- 浏览器内最多保留 120 个采样点。
- 大约表示最近 10 分钟。
- 展示 CPU、RAM 和 Load 1m。
- 使用原生 SVG，不依赖 Chart.js 或其他前端框架。
- Live 数据保存在浏览器内存中，刷新页面后会重新采集。

### Historical trends / 历史趋势

- Reads persistent Beszel `system_stats` data.
- Uses Beszel 1-minute samples.
- Shows the latest 60 minutes by default.
- Historical data survives browser refreshes.
- Available through `/api/history?minutes=60`.

- 读取 Beszel 持久化的 `system_stats` 数据。
- 使用 Beszel 的 1 分钟历史采样。
- 默认展示最近 60 分钟。
- 浏览器刷新后历史数据不会丢失。
- API 地址为 `/api/history?minutes=60`。

### Legacy browser compatibility / 老设备兼容

The dashboard intentionally uses simple HTML, CSS, ES5-style JavaScript,
`XMLHttpRequest`, and native SVG so that it can run on much older browsers.

The current dashboard has been successfully tested on an iPad mini 1 running
iOS 9 Safari.

Dashboard 有意采用简单 HTML、CSS、ES5 风格 JavaScript、`XMLHttpRequest`
和原生 SVG，以提高老浏览器兼容性。

当前版本已经在运行 iOS 9 Safari 的 iPad mini 1 上实际测试通过。

### Metric source separation / 数据来源分离

HomeLab Portal treats heartbeat and monitoring data as separate sources:

- Heartbeat data is authoritative for device identity, LAN IP, ZeroTier IP and `last_seen`.
- Beszel supplies CPU, memory, disk, load, temperature, uptime and persistent history.
- Beszel host addresses are not treated as authoritative LAN IP addresses.

HomeLab Portal 将设备心跳数据和监控数据分开处理：

- Heartbeat 负责设备身份、LAN IP、ZeroTier IP 和 `last_seen`。
- Beszel 负责 CPU、内存、磁盘、Load、温度、Uptime 和持久历史。
- Beszel 中记录的 host 地址不会被当作权威 LAN IP。
