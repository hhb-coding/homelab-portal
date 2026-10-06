#!/usr/bin/env python3

"""
Link HomeLab Portal devices to Beszel systems.
将 HomeLab Portal 设备与 Beszel system 建立持久关联。

Important design rule / 重要设计原则：

We do NOT use the Beszel host/IP address as the primary identity,
because Beszel may retain an old DHCP address.

我们不使用 Beszel 的 host/IP 作为主要设备身份，
因为 Beszel 中可能保留旧的 DHCP 地址。

The persistent link is stored in devices.beszel_system_id.
真正的关联关系保存在 devices.beszel_system_id。
"""

import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from beszel_client import BeszelAPIError, BeszelClient


def normalize_name(value):
    """
    Normalize a hostname/name for conservative automatic matching.
    对设备名称做保守标准化，用于自动匹配。
    """
    if not value:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        value.lower(),
    )


def get_beszel_systems():
    """Authenticate and return Beszel systems."""
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
        raise RuntimeError(
            "Beszel credentials are not configured."
        )

    return client.get_systems()


def main():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    devices = conn.execute(
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
        ORDER BY device_id
        """
    ).fetchall()

    try:
        systems = get_beszel_systems()
    except (BeszelAPIError, RuntimeError) as exc:
        print("ERROR:", exc)
        return 1

    print()
    print("============================================================")
    print(" HomeLab Portal devices / 本地设备")
    print("============================================================")

    for index, device in enumerate(devices, start=1):
        print(
            f"{index}. {device['device_id']} | "
            f"hostname={device['hostname']} | "
            f"LAN={device['lan_ip']} | "
            f"ZeroTier={device['zerotier_ip']} | "
            f"BeszelID={device['beszel_system_id']}"
        )

    print()
    print("============================================================")
    print(" Beszel systems / Beszel设备")
    print("============================================================")

    for index, system in enumerate(systems, start=1):
        print(
            f"{index}. {system.get('name')} | "
            f"id={system.get('id')} | "
            f"status={system.get('status')}"
        )

    # --------------------------------------------------------
    # Conservative automatic matching by names only.
    # 只根据名称进行保守自动匹配，不根据 IP。
    # --------------------------------------------------------

    system_by_normalized_name = {}

    for system in systems:
        name = normalize_name(system.get("name"))

        if name:
            system_by_normalized_name.setdefault(
                name,
                [],
            ).append(system)

    changed = False

    print()
    print("============================================================")
    print(" Automatic matching / 自动匹配")
    print("============================================================")

    for device in devices:

        if device["beszel_system_id"]:
            print(
                f"KEEP: {device['device_id']} already linked -> "
                f"{device['beszel_system_id']}"
            )
            continue

        candidates = set()

        for value in (
            device["device_id"],
            device["hostname"],
            device["display_name"],
        ):
            normalized = normalize_name(value)

            if not normalized:
                continue

            matches = system_by_normalized_name.get(
                normalized,
                [],
            )

            for system in matches:
                candidates.add(system["id"])

        if len(candidates) == 1:
            system_id = next(iter(candidates))

            system_name = next(
                (
                    system.get("name")
                    for system in systems
                    if system.get("id") == system_id
                ),
                system_id,
            )

            conn.execute(
                """
                UPDATE devices
                SET
                    beszel_system_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE device_id = ?
                """,
                (
                    system_id,
                    device["device_id"],
                ),
            )

            changed = True

            print(
                f"AUTO: {device['device_id']} -> "
                f"{system_name}"
            )

        else:
            print(
                f"MANUAL REQUIRED: {device['device_id']}"
            )

    if changed:
        conn.commit()

    # Reload after automatic matching.
    devices = conn.execute(
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
        ORDER BY device_id
        """
    ).fetchall()

    # --------------------------------------------------------
    # Interactive mapping for unresolved devices.
    # 对无法自动匹配的设备进行一次人工选择。
    # --------------------------------------------------------

    unresolved = [
        device
        for device in devices
        if not device["beszel_system_id"]
    ]

    if unresolved:

        print()
        print("============================================================")
        print(" Manual linking / 人工关联")
        print("============================================================")
        print()
        print(
            "For each unresolved device, enter the matching "
            "Beszel number."
        )
        print(
            "对于没有自动匹配的设备，输入对应的 Beszel 编号。"
        )
        print(
            "Enter 0 to leave a device unlinked."
        )
        print("输入 0 可以暂时跳过。")
        print()

        for device in unresolved:

            print("--------------------------------------------")
            print("Local device / 本地设备:")
            print(" device_id   :", device["device_id"])
            print(" hostname    :", device["hostname"])
            print(" display_name:", device["display_name"])
            print(" LAN IP      :", device["lan_ip"])
            print(" ZeroTier IP :", device["zerotier_ip"])
            print()

            for index, system in enumerate(
                systems,
                start=1,
            ):
                print(
                    f" {index} = {system.get('name')}"
                )

            print(" 0 = Skip / 暂时跳过")

            while True:
                answer = input(
                    "Beszel number: "
                ).strip()

                try:
                    selection = int(answer)
                except ValueError:
                    print("Please enter a number.")
                    continue

                if selection == 0:
                    print("Skipped.")
                    break

                if 1 <= selection <= len(systems):

                    selected = systems[selection - 1]

                    conn.execute(
                        """
                        UPDATE devices
                        SET
                            beszel_system_id = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE device_id = ?
                        """,
                        (
                            selected["id"],
                            device["device_id"],
                        ),
                    )

                    conn.commit()

                    print(
                        f"LINKED: {device['device_id']} -> "
                        f"{selected.get('name')}"
                    )

                    break

                print("Invalid selection.")

    print()
    print("============================================================")
    print(" Final mapping / 最终设备关联")
    print("============================================================")

    rows = conn.execute(
        """
        SELECT
            device_id,
            hostname,
            lan_ip,
            zerotier_ip,
            beszel_system_id
        FROM devices
        ORDER BY device_id
        """
    ).fetchall()

    system_names = {
        system["id"]: system.get("name")
        for system in systems
    }

    for row in rows:
        beszel_name = system_names.get(
            row["beszel_system_id"],
            "UNLINKED",
        )

        print(
            f"{row['device_id']} | "
            f"LAN={row['lan_ip']} | "
            f"ZT={row['zerotier_ip']} | "
            f"Beszel={beszel_name}"
        )

    conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
