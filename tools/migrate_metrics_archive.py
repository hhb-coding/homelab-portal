#!/usr/bin/env python3
"""Operator-only migration with mandatory backup / 运维显式迁移，必须备份。"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metrics_archive import require_hdd, writer, safe_paths
from frequency_migration import migrate
from network_migration import migrate as migrate_network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--to", required=True, type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    # No config import: UUID supplied privately in environment / UUID 仅来自私有环境。
    guard = lambda p: require_hdd(p, Path(os.environ.get("METRICS_ARCHIVE_MOUNT", "/srv/data")), os.environ.get("METRICS_ARCHIVE_UUID", ""))
    try:
        if not args.database.is_file():
            raise ValueError("Existing database required")
        guard(args.database)
        guard(args.backup)
        safe_paths(args.backup)
        with writer(args.database, guard) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Integrity check failed")
            if args.to == 3 and conn.execute("PRAGMA user_version").fetchone()[0] == 3:
                print("Archive already at requested version; no changes")
                return 0
            # Reserve space for a complete online snapshot before creating its file.
            # 备份创建前同时预留完整快照空间与最低剩余空间。
            snapshot_bytes = (conn.execute("PRAGMA page_count").fetchone()[0]
                              * conn.execute("PRAGMA page_size").fetchone()[0])
            reserve_bytes = int(os.environ.get("METRICS_ARCHIVE_MIN_FREE_BYTES", "1073741824"))
            require_hdd(args.backup, Path(os.environ.get("METRICS_ARCHIVE_MOUNT", "/srv/data")),
                        os.environ.get("METRICS_ARCHIVE_UUID", ""), reserve_bytes+snapshot_bytes)
            fd = os.open(args.backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(args.backup)) as backup:
                conn.backup(backup, pages=256, progress=lambda *_: guard(args.backup))
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            guard(args.database)
            guard(args.backup)
            if args.to == 3:
                migrate_network(conn, lambda: guard(args.database))
            else:
                migrate(conn, args.to, lambda: guard(args.database))
        print("Migration complete; backup retained")
        return 0
    except Exception as exc:
        print("Migration failed: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
