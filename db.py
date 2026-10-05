"""
SQLite database helpers for HomeLab Portal.
HomeLab Portal 的 SQLite 数据库辅助模块。
"""

import sqlite3

from config import BASE_DIR, DATABASE_PATH


def get_connection():
    """
    Create and return a SQLite connection.
    创建并返回 SQLite 数据库连接。
    """

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    # Return rows that can be accessed by column name.
    # 让查询结果可以通过字段名称访问。
    connection.row_factory = sqlite3.Row

    # Enforce SQLite foreign-key relationships.
    # 启用 SQLite 外键约束。
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def init_db():
    """
    Initialize the database using schema.sql.
    使用 schema.sql 初始化数据库。
    """

    schema_path = BASE_DIR / "schema.sql"

    with get_connection() as connection:
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            connection.executescript(schema_file.read())


def database_is_ready():
    """
    Verify that the devices table exists.
    检查 devices 数据表是否已经存在。
    """

    try:
        with get_connection() as connection:
            result = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name='devices'
                """
            ).fetchone()

        return result is not None

    except sqlite3.Error:
        return False


def upsert_device(
    device_id,
    hostname=None,
    display_name=None,
    lan_ip=None,
    zerotier_ip=None,
):
    """
    Create a device or update its latest heartbeat information.

    创建新设备，或根据最新 heartbeat 更新设备信息。

    LAN and ZeroTier addresses are stored separately.
    LAN 地址与 ZeroTier 地址始终分别保存，互不覆盖。
    """

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT device_id, hostname, display_name,
                   lan_ip, zerotier_ip
            FROM devices
            WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()

        # First heartbeat from this device.
        # 这是该设备第一次发送 heartbeat。
        if existing is None:
            connection.execute(
                """
                INSERT INTO devices (
                    device_id,
                    hostname,
                    display_name,
                    lan_ip,
                    zerotier_ip,
                    last_seen,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """,
                (
                    device_id,
                    hostname,
                    display_name,
                    lan_ip,
                    zerotier_ip,
                ),
            )

            return {
                "created": True,
                "lan_ip_changed": False,
                "zerotier_ip_changed": False,
            }

        old_lan_ip = existing["lan_ip"]
        old_zerotier_ip = existing["zerotier_ip"]

        lan_ip_changed = old_lan_ip != lan_ip
        zerotier_ip_changed = old_zerotier_ip != zerotier_ip

        # Record LAN address changes independently.
        # 独立记录局域网 IP 地址变化。
        if lan_ip_changed:
            connection.execute(
                """
                INSERT INTO ip_events (
                    device_id,
                    event_type,
                    old_ip,
                    new_ip
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    device_id,
                    "LAN_IP_CHANGE",
                    old_lan_ip,
                    lan_ip,
                ),
            )

        # Record ZeroTier address changes independently.
        # 独立记录 ZeroTier IP 地址变化。
        if zerotier_ip_changed:
            connection.execute(
                """
                INSERT INTO ip_events (
                    device_id,
                    event_type,
                    old_ip,
                    new_ip
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    device_id,
                    "ZEROTIER_IP_CHANGE",
                    old_zerotier_ip,
                    zerotier_ip,
                ),
            )

        # Refresh the current device record.
        # 更新设备当前状态和最后在线时间。
        connection.execute(
            """
            UPDATE devices
            SET
                hostname = COALESCE(?, hostname),
                display_name = COALESCE(?, display_name),
                lan_ip = ?,
                zerotier_ip = ?,
                last_seen = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
            """,
            (
                hostname,
                display_name,
                lan_ip,
                zerotier_ip,
                device_id,
            ),
        )

        return {
            "created": False,
            "lan_ip_changed": lan_ip_changed,
            "zerotier_ip_changed": zerotier_ip_changed,
        }


def get_device(device_id):
    """
    Return one registered device.
    返回一个已经登记的设备。
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM devices
            WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def list_devices():
    """
    Return all registered devices ordered by display name or hostname.
    返回所有设备，并按显示名称或主机名排序。
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM devices
            ORDER BY
                COALESCE(display_name, hostname, device_id)
            """
        ).fetchall()

    return [dict(row) for row in rows]
