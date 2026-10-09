"""
HomeLab Portal unified dashboard service.
HomeLab Portal 统一 Dashboard 数据服务。

This module merges:

1. Device registry / heartbeat information from SQLite
   SQLite 中的设备注册、LAN IP、ZeroTier IP、Last Seen

2. System performance metrics from Beszel
   Beszel 中的 CPU、RAM、Disk、Load、Temperature

Device identity is linked through beszel_system_id.
设备身份通过 beszel_system_id 建立稳定关联。
"""

import sqlite3
from typing import Any, Dict, List

import config
from beszel_client import BeszelAPIError, BeszelClient


def _get_registry_devices() -> List[Dict[str, Any]]:
    """
    Read registered devices from SQLite.
    从 SQLite 读取 Heartbeat 注册设备。
    """

    conn = sqlite3.connect(
        config.DATABASE_PATH
    )

    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            device_id,
            hostname,
            display_name,
            lan_ip,
            zerotier_ip,
            beszel_system_id,
            last_seen
        FROM devices
        ORDER BY
            COALESCE(display_name, hostname, device_id)
        """
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


def _get_beszel_snapshot() -> List[Dict[str, Any]]:
    """
    Read current system metrics from Beszel.
    从 Beszel 获取当前性能指标。
    """

    client = BeszelClient(
        config.BESZEL_URL,
        timeout=config.BESZEL_TIMEOUT,
    )

    if config.BESZEL_TOKEN:

        client.authenticate_with_token(
            config.BESZEL_TOKEN
        )

    elif (
        config.BESZEL_EMAIL
        and config.BESZEL_PASSWORD
    ):

        client.authenticate_with_password(
            config.BESZEL_EMAIL,
            config.BESZEL_PASSWORD,
        )

    else:
        raise BeszelAPIError(
            "Beszel credentials are not configured."
        )

    return client.get_snapshot()


def build_dashboard() -> Dict[str, Any]:
    """
    Build one unified device list for the front end.

    为前端生成统一设备列表。

    Important:
    Beszel host/IP is intentionally NOT used as the LAN IP.

    注意：
    Beszel 中的 host/IP 不作为设备真实 LAN IP。
    LAN IP 始终来自 HomeLab Portal heartbeat。
    """

    registry_devices = _get_registry_devices()

    metrics_status = "ok"
    metrics_error = None

    try:
        beszel_systems = _get_beszel_snapshot()

    except BeszelAPIError:
        # The IP registry should remain useful even if Beszel is down.
        # 即使 Beszel 临时不可用，IP Dashboard 仍然应该工作。
        beszel_systems = []
        metrics_status = "unavailable"
        metrics_error = "beszel_api_unavailable"

    metrics_by_id = {
        item.get("beszel_system_id"): item
        for item in beszel_systems
        if item.get("beszel_system_id")
    }

    devices = []

    for registry in registry_devices:

        beszel_id = registry.get(
            "beszel_system_id"
        )

        metric = metrics_by_id.get(
            beszel_id,
            {},
        )

        devices.append(
            {
                # ------------------------------------------------
                # Device identity / 设备身份
                # ------------------------------------------------
                "device_id": registry.get("device_id"),
                "hostname": registry.get("hostname"),
                "display_name": registry.get(
                    "display_name"
                ),

                # ------------------------------------------------
                # Network identity from heartbeat
                # 网络地址只来自 heartbeat
                # ------------------------------------------------
                "lan_ip": registry.get("lan_ip"),
                "zerotier_ip": registry.get(
                    "zerotier_ip"
                ),
                "last_seen": registry.get(
                    "last_seen"
                ),

                # ------------------------------------------------
                # Persistent Beszel link
                # Beszel 持久关联
                # ------------------------------------------------
                "beszel_system_id": beszel_id,
                "beszel_name": metric.get("name"),
                "beszel_status": metric.get(
                    "status"
                ),

                # ------------------------------------------------
                # Core performance metrics
                # 核心性能指标
                # ------------------------------------------------
                "metrics_available": bool(metric),

                # Additive API fields; existing percentages stay compatible.
                # 新增容量字段，保留旧百分比字段以兼容现有客户端。
                "memory_total": metric.get("memory_total"),
                "disk_total": metric.get("disk_total"),
                "disk_used": metric.get("disk_used"),
                "disk_available": metric.get("disk_available"),
                "disk_available_estimated": metric.get("disk_available_estimated", False),
                "disk_usage_percent": metric.get("disk_usage_percent"),
                "capacity_unit": metric.get("capacity_unit"),

                "cpu_percent": metric.get(
                    "cpu_percent"
                ),

                "memory_percent": metric.get(
                    "memory_percent"
                ),

                "disk_percent": metric.get(
                    "disk_percent"
                ),

                "load_1": metric.get("load_1"),
                "load_5": metric.get("load_5"),
                "load_15": metric.get("load_15"),

                "temperature": metric.get(
                    "temperature"
                ),

                "uptime_seconds": metric.get(
                    "uptime_seconds"
                ),
            }
        )

    return {
        "status": "ok",
        "count": len(devices),

        "sources": {
            "registry": "sqlite-heartbeat",
            "metrics": "beszel",
            "metrics_status": metrics_status,
        },

        "metrics_error": metrics_error,

        "devices": devices,
    }
