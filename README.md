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
