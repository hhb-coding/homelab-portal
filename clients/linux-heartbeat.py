#!/usr/bin/env python3
"""
HomeLab Portal Linux Heartbeat Client
=====================================

Reports a Linux device's hostname, LAN IP, and optional ZeroTier IP
to the HomeLab Portal heartbeat API.

向 HomeLab Portal heartbeat API 上报 Linux 设备的主机名、
LAN IP 和可选的 ZeroTier IP。
"""

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request


def run_command(command):
    """
    Run a local command and return stripped stdout.

    执行本地命令并返回去除首尾空白后的标准输出。
    """

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def detect_lan_ip():
    """
    Detect the primary LAN IPv4 address.

    优先通过默认路由识别主要 LAN IPv4 地址。
    """

    output = run_command(
        ["ip", "-4", "route", "get", "1.1.1.1"]
    )

    fields = output.split()

    if "src" in fields:
        index = fields.index("src")

        if index + 1 < len(fields):
            return fields[index + 1]

    return None


def detect_zerotier_ip():
    """
    Detect an IPv4 address assigned to a ZeroTier interface.

    查找 ZeroTier 网络接口上的 IPv4 地址。
    """

    output = run_command(
        ["ip", "-4", "-o", "addr", "show"]
    )

    for line in output.splitlines():
        fields = line.split()

        if len(fields) < 4:
            continue

        interface_name = fields[1]

        # ZeroTier Linux interfaces normally begin with "zt".
        # ZeroTier Linux 网络接口通常以 "zt" 开头。
        if not interface_name.startswith("zt"):
            continue

        address = fields[3].split("/")[0]

        return address

    return None


def send_heartbeat():
    """
    Build and send one heartbeat request.

    创建并发送一次 heartbeat 请求。
    """

    portal_url = os.getenv(
        "HOMELAB_PORTAL_URL",
        "http://127.0.0.1:8088",
    ).rstrip("/")

    heartbeat_token = os.getenv("HOMELAB_HEARTBEAT_TOKEN", "")
    device_id = os.getenv("HOMELAB_DEVICE_ID", "")
    display_name = os.getenv("HOMELAB_DISPLAY_NAME", "")

    if not heartbeat_token:
        raise RuntimeError(
            "HOMELAB_HEARTBEAT_TOKEN is not configured."
        )

    if not device_id:
        raise RuntimeError(
            "HOMELAB_DEVICE_ID is not configured."
        )

    hostname = socket.gethostname()
    lan_ip = detect_lan_ip()
    zerotier_ip = detect_zerotier_ip()

    payload = {
        "device_id": device_id,
        "hostname": hostname,
        "display_name": display_name or hostname,
        "lan_ip": lan_ip,
        "zerotier_ip": zerotier_ip,
    }

    request_data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{portal_url}/api/heartbeat",
        data=request_data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Heartbeat-Token": heartbeat_token,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            response_body = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Portal returned HTTP {error.code}: {body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Unable to reach HomeLab Portal: {error.reason}"
        ) from error

    print(response_body)


def main():
    """
    Application entry point.
    程序入口。
    """

    try:
        send_heartbeat()
        return 0

    except Exception as error:
        print(
            f"Heartbeat failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
