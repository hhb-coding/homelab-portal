#!/usr/bin/env python3
"""Run one protected archive pass / 执行一次受保护归档。"""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from beszel_client import BeszelClient
from metrics_archive import collect, require_hdd, writer


def main():
    # Reuse this checkout's existing config only. Never auto-load production.
    # 仅使用当前安装目录配置，不自动读取其他生产目录。
    client = None
    try:
        import config
        database = Path(os.getenv("METRICS_ARCHIVE_PATH", "/srv/data/homelab-portal-archive/metrics.sqlite3"))
        mount = Path(os.getenv("METRICS_ARCHIVE_MOUNT", "/srv/data"))
        uuid = os.getenv("METRICS_ARCHIVE_UUID", "")
        guard = lambda path: require_hdd(path, mount, uuid)
        guard(database)
        client = BeszelClient(config.BESZEL_URL, timeout=config.BESZEL_TIMEOUT)
        if config.BESZEL_TOKEN:
            client.authenticate_with_token(config.BESZEL_TOKEN)
        elif config.BESZEL_EMAIL and config.BESZEL_PASSWORD:
            client.authenticate_with_password(config.BESZEL_EMAIL, config.BESZEL_PASSWORD)
        else:
            print("Archive failed: credentials unavailable", file=sys.stderr)
            return 1
        with writer(database, guard) as conn:
            report = collect(conn, client, check_mount=lambda: guard(database))
        print(json.dumps(report, sort_keys=True))
        return 1 if report["failed"] else 0
    except Exception as exc:
        print("Archive failed: " + type(exc).__name__, file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.session.close()


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
