"""Independent raw Beszel archive / 独立 Beszel 原始指标归档。

No production configuration is imported and no filesystem changes occur at import.
导入时不读取生产配置，也不创建文件。
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
from requests.exceptions import RequestException

UTC = timezone.utc


class ArchiveError(RuntimeError):
    pass


class MountError(ArchiveError):
    """Fatal storage guard failure / 挂载检查失败，立即终止本轮。"""
    pass


def utc_time(value):
    if not isinstance(value, str):
        raise ArchiveError("Invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ArchiveError("Invalid timestamp") from None
    if parsed.tzinfo is None:
        raise ArchiveError("Timestamp has no timezone")
    return parsed.astimezone(UTC)


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def api_stamp(value):
    return stamp(value).replace("T", " ")


def require_hdd(database, mount=Path("/srv/data"), expected_uuid=""):
    """Fail before mkdir/open if the actual destination is not the expected HDD."""
    database, mount = Path(database), Path(mount)
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", expected_uuid):
        raise MountError("A valid HDD UUID must be configured")
    if not database.is_absolute() or not mount.is_absolute():
        raise MountError("Archive paths must be absolute")
    safe_paths(database)
    resolved, root = database.resolve(), mount.resolve()
    if root != mount or not resolved.is_relative_to(root) or resolved == root:
        raise MountError("Archive must be inside the HDD mount")
    # Check nearest existing parent too, rejecting nested mounts and symlinks
    # that lead to another filesystem. / 同时拒绝其他文件系统上的子挂载。
    parent = resolved if resolved.exists() else resolved.parent
    while not parent.exists():
        parent = parent.parent
    for target in (root, parent):
        try:
            result = subprocess.run(
                ["findmnt", "--json", "--target", str(target), "--output", "TARGET,UUID,FSTYPE,OPTIONS"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            entry = json.loads(result.stdout)["filesystems"][0]
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
            raise MountError("Cannot verify HDD mount") from None
        if (entry.get("target") != str(root) or entry.get("uuid") != expected_uuid
                or entry.get("fstype") != "ext4" or "rw" not in entry.get("options", "").split(",")):
            raise MountError("HDD mount verification failed")
    return resolved


def safe_paths(database):
    """Reject links and unsafe ancestors, including SQLite and lock sidecars."""
    database = Path(database)
    if not database.is_absolute():
        raise MountError("Archive path must be absolute")
    for parent in reversed(database.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise MountError("Archive ancestor is not a plain directory")
        if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise MountError("Archive ancestor is writable by other users")
    for path in (database, Path(str(database) + ".lock"),
                 Path(str(database) + "-wal"), Path(str(database) + "-shm"),
                 Path(str(database) + "-journal")):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise MountError("Unsafe archive file or sidecar")


@contextmanager
def writer(database, guard=require_hdd):
    """One local writer; recheck the mount before opening SQLite / 单写入者。"""
    database = guard(Path(database))
    safe_paths(database)
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    guard(database)
    safe_paths(database)
    lock_fd = os.open(str(database) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        info = os.fstat(lock.fileno())
        if info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise MountError("Unsafe archive lock")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ArchiveError("Archive writer already running") from None
        guard(database)
        safe_paths(database)
        # Reserve the database with O_NOFOLLOW and restrictive permissions before
        # SQLite opens it. Parents must be controlled by the collector user.
        fd = os.open(database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        guard(database)
        safe_paths(database)
        conn = sqlite3.connect(database, timeout=10)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )}
            expected = {"samples", "checkpoints"}
            if version == 2:
                expected.add("cpu_frequency_samples")
            if (version not in (0, 1, 2) or (version == 0 and tables)
                    or (version in (1, 2) and tables != expected)):
                raise ArchiveError("Destination is not a supported archive database")
            if version == 2:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(cpu_frequency_samples)")]
                if columns != ["device_id", "sample_id", "sampled_utc", "payload", "received_utc", "archived_utc"]:
                    raise ArchiveError("Unsupported frequency history columns")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS samples (
                    system_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    created_raw TEXT NOT NULL,
                    updated_raw TEXT,
                    stats_json TEXT NOT NULL,
                    archived_utc TEXT NOT NULL,
                    PRIMARY KEY (system_id, record_id)
                );
                CREATE INDEX IF NOT EXISTS samples_system_time
                    ON samples(system_id, created_utc, record_id);
                CREATE INDEX IF NOT EXISTS samples_retention ON samples(created_utc);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    system_id TEXT PRIMARY KEY,
                    created_utc TEXT NOT NULL
                );
            """)
            if version == 0:
                conn.execute("PRAGMA user_version=1")
            yield conn
        finally:
            conn.close()


def collect(conn, client, now=None, retention_days=180, page_size=200, overlap_minutes=10,
            check_mount=lambda: None):
    """Commit samples and watermark together for each page / 每页原子提交。

    Recover from the last committed page with a ten-minute overlap. Empty/offline
    devices never advance their watermark. No synthetic samples are generated.
    断点恢复并重叠补采；空设备不推进游标，不制造数据。
    """
    if not 1 <= retention_days <= 180 or not 1 <= page_size <= 500 or overlap_minutes < 1:
        raise ArchiveError("Invalid archive limits")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ArchiveError("Run time must include timezone")
    now = now.astimezone(UTC)
    cutoff = now - timedelta(days=retention_days)
    report = {"systems": 0, "inserted": 0, "duplicates": 0, "failed": 0, "pruned": 0}
    systems = client.get_systems()
    if not isinstance(systems, list):
        raise ArchiveError("Invalid systems response")
    seen = set()
    for system in systems:
        try:
            system_id = system["id"]
            if not re.fullmatch(r"[a-z0-9]{15}", system_id) or system_id in seen:
                raise ArchiveError("Invalid or duplicate system")
            seen.add(system_id)
            report["systems"] += 1
            row = conn.execute("SELECT created_utc FROM checkpoints WHERE system_id=?", (system_id,)).fetchone()
            start = max(cutoff, utc_time(row[0]) - timedelta(minutes=overlap_minutes)) if row else cutoff
            if start > now:
                raise ArchiveError("Checkpoint is ahead of run time")
            after = None
            while True:
                records = client.get_archive_page(system_id, api_stamp(start), api_stamp(now), after, page_size)
                if not isinstance(records, list) or len(records) > page_size:
                    raise ArchiveError("Invalid page")
                if not records:
                    break
                prepared = []
                previous = after
                for record in records:
                    if not isinstance(record, dict):
                        raise ArchiveError("Invalid sample object")
                    created = utc_time(record.get("created"))
                    if created.microsecond % 1000:
                        raise ArchiveError("Sample exceeds supported millisecond precision")
                    record_id = record.get("id", "")
                    key = (api_stamp(created), record_id)
                    if (record.get("system") != system_id or record.get("type") != "1m"
                            or not re.fullmatch(r"[a-z0-9]{15}", record_id)
                            or not isinstance(record.get("stats"), dict)
                            or not start <= created <= now or (previous is not None and key <= previous)):
                        raise ArchiveError("Invalid or unordered sample")
                    raw = json.dumps(record["stats"], ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                    prepared.append((system_id, record_id, stamp(created), record["created"],
                                     record.get("updated"), raw, stamp(now)))
                    previous = key
                check_mount()
                with conn:
                    before = conn.total_changes
                    conn.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?)", prepared)
                    inserted = conn.total_changes - before
                    conn.execute("""INSERT INTO checkpoints VALUES (?,?)
                        ON CONFLICT(system_id) DO UPDATE SET created_utc=MAX(created_utc,excluded.created_utc)""",
                                 (system_id, prepared[-1][2]))
                report["inserted"] += inserted
                report["duplicates"] += len(prepared) - inserted
                after = previous
                # Always request the next cursor page, including after a short
                # page: server-side page caps need not match our requested size.
        except MountError:
            raise
        except (KeyError, TypeError, ValueError, RuntimeError, sqlite3.Error, RequestException):
            # Never print exception bodies: upstream responses may contain secrets.
            # 不输出上游错误内容或认证信息。
            report["failed"] += 1
    check_mount()
    with conn:
        report["pruned"] = conn.execute("DELETE FROM samples WHERE created_utc < ?", (stamp(cutoff),)).rowcount
    return report
