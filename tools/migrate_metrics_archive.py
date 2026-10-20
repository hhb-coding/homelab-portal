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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--to", required=True, type=int, choices=(1, 2))
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
            fd = os.open(args.backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(args.backup)) as backup:
                conn.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            guard(args.database)
            guard(args.backup)
            migrate(conn, args.to, lambda: guard(args.database))
        print("Migration complete; backup retained")
        return 0
    except Exception as exc:
        print("Migration failed: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
