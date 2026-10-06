"""
HomeLab Portal historical metrics service.
HomeLab Portal 历史性能指标服务。

Reads persistent 1-minute history from Beszel system_stats.
从 Beszel system_stats 读取持久化的 1 分钟历史数据。
"""

import sqlite3

import config
from beszel_client import BeszelAPIError, BeszelClient

MIN_HISTORY_MINUTES = 10
MAX_HISTORY_MINUTES = 360
DEFAULT_HISTORY_MINUTES = 60


def _client():
    """Create an authenticated Beszel client. / 创建已认证的 Beszel 客户端。"""
    client = BeszelClient(
        config.BESZEL_URL,
        timeout=config.BESZEL_TIMEOUT,
    )

    if config.BESZEL_TOKEN:
        client.authenticate_with_token(config.BESZEL_TOKEN)
    elif config.BESZEL_EMAIL and config.BESZEL_PASSWORD:
        client.authenticate_with_password(
            config.BESZEL_EMAIL,
            config.BESZEL_PASSWORD,
        )
    else:
        raise BeszelAPIError("Beszel credentials are not configured.")

    return client


def _devices():
    """Read local devices and their persistent Beszel links. / 读取本地设备及 Beszel 关联。"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT device_id, hostname, display_name, beszel_system_id
        FROM devices
        ORDER BY COALESCE(display_name, hostname, device_id)
        """
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def _point(record):
    """Normalize one Beszel system_stats record. / 标准化一条历史记录。"""
    stats = record.get("stats") or {}
    load = stats.get("la") or []

    return {
        "timestamp": record.get("created"),
        "cpu_percent": stats.get("cpu"),
        "memory_percent": stats.get("mp"),
        "disk_percent": stats.get("dp"),
        "load_1": load[0] if isinstance(load, list) and load else None,
    }


def build_history(minutes=DEFAULT_HISTORY_MINUTES):
    """Build normalized historical metrics for all registered devices.
    为所有已登记设备生成统一历史指标。
    """
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        minutes = DEFAULT_HISTORY_MINUTES

    minutes = max(
        MIN_HISTORY_MINUTES,
        min(minutes, MAX_HISTORY_MINUTES),
    )

    client = _client()
    result = []

    for device in _devices():
        system_id = device.get("beszel_system_id")
        points = []
        error = None

        if system_id:
            url = (
                config.BESZEL_URL.rstrip("/")
                + "/api/collections/system_stats/records"
            )

            try:
                response = client.session.get(
                    url,
                    params={
                        "page": 1,
                        "perPage": minutes,
                        "sort": "-created",
                        "filter": "type='1m' && system='%s'" % system_id,
                        "fields": "created,stats",
                    },
                    timeout=config.BESZEL_TIMEOUT,
                )
                response.raise_for_status()

                records = response.json().get("items", [])
                records.reverse()
                points = [_point(record) for record in records]

            except Exception:
                error = "history_unavailable"

        result.append(
            {
                "device_id": device.get("device_id"),
                "hostname": device.get("hostname"),
                "display_name": device.get("display_name"),
                "beszel_system_id": system_id,
                "count": len(points),
                "error": error,
                "points": points,
            }
        )

    return {
        "status": "ok",
        "source": "beszel-system_stats",
        "resolution": "1m",
        "minutes": minutes,
        "devices": result,
    }
