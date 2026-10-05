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
