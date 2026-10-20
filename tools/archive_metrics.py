#!/usr/bin/env python3
"""Run one protected archive pass / 执行一次受保护归档。"""
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from beszel_client import BeszelClient
from metrics_archive import collect, require_hdd, writer
from frequency import drain, stamp, queue_status


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
        with writer(database, guard) as conn:
            # Frequency drain does not depend on Hub authentication or availability.
            # 先归档已接收频率，不依赖 Hub 认证或采集是否成功。
            report = {"frequency_archived": 0, "frequency_failed": 0, "failed": 0}
            if os.getenv("FREQUENCY_ARCHIVE_ENABLED", "false").lower() == "true":
                try:
                    for _ in range(120):
                        count = drain(conn, config.DATABASE_PATH, lambda: guard(database))
                        report["frequency_archived"] += count
                        if count < 120:
                            break
                    report["frequency_queue"] = queue_status(config.DATABASE_PATH)
                except Exception as exc:
                    report["frequency_failed"] = 1
                    print("Frequency archive failed: " + type(exc).__name__, file=sys.stderr)
            try:
                client = BeszelClient(config.BESZEL_URL, timeout=config.BESZEL_TIMEOUT)
                if config.BESZEL_TOKEN:
                    client.authenticate_with_token(config.BESZEL_TOKEN)
                elif config.BESZEL_EMAIL and config.BESZEL_PASSWORD:
                    client.authenticate_with_password(config.BESZEL_EMAIL, config.BESZEL_PASSWORD)
                else:
                    raise ValueError("Credentials unavailable")
                report.update(collect(conn, client, check_mount=lambda: guard(database)))
            except Exception as exc:
                report["failed"] = 1
                print("Beszel archive failed: " + type(exc).__name__, file=sys.stderr)
            # Compatibility rollback still enforces history TTL / 兼容回滚仍清理过期历史。
            if conn.execute("PRAGMA user_version").fetchone()[0] == 2:
                guard(database)
                with conn:
                    report["frequency_pruned"] = conn.execute("DELETE FROM cpu_frequency_samples WHERE sampled_utc < ?",
                        (stamp(datetime.now(timezone.utc)-timedelta(days=180)),)).rowcount
        print(json.dumps(report, sort_keys=True))
        return 1 if report["failed"] or report["frequency_failed"] else 0
    except Exception as exc:
        print("Archive failed: " + type(exc).__name__, file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.session.close()


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
