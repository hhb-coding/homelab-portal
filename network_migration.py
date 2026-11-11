"""Explicit v3 network archive migration; caller holds writer lock / 显式迁移。"""
from metrics_archive import ArchiveError
from frequency_migration import create_frequency_schema


TABLES = {
    "network_archive_meta": "singleton,retention_floor_ms",
    "network_monitors": "monitor_id,system_id,target,protocol,interval,enabled,config_json,archived_ms",
    "network_samples": "monitor_id,type,record_id,created_ms,system_id,res_min,res_max,res_sum,total_count,success_count,raw_json,archived_ms",
    "network_checkpoints": "monitor_id,type,created_ms,record_id",
    "network_daily": "monitor_id,type,day_ms,sample_count,total_count,success_count,res_sum,res_min,res_max,first_ms,last_ms",
    "network_events": "event_id,stream_key,kind,monitor_id,started_ms,detected_ms,recovered_ms,recovery_detected_ms,details_json",
    "network_event_state": "stream_key,last_bucket_ms,abnormal_run,recovery_run,candidate_ms,open_event_id",
}

DDL = (
    """CREATE TABLE network_archive_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), retention_floor_ms INTEGER NOT NULL)""",
    "INSERT INTO network_archive_meta VALUES (1,0)",
    """CREATE TABLE network_monitors (
        monitor_id TEXT PRIMARY KEY, system_id TEXT NOT NULL, target TEXT NOT NULL,
        protocol TEXT NOT NULL, interval INTEGER NOT NULL, enabled INTEGER NOT NULL,
        config_json TEXT NOT NULL, archived_ms INTEGER NOT NULL)""",
    """CREATE TABLE network_samples (
        monitor_id TEXT NOT NULL, type TEXT NOT NULL CHECK(type='1m'), record_id TEXT NOT NULL,
        created_ms INTEGER NOT NULL, system_id TEXT NOT NULL, res_min REAL, res_max REAL,
        res_sum INTEGER NOT NULL, total_count INTEGER NOT NULL, success_count INTEGER NOT NULL,
        raw_json TEXT NOT NULL, archived_ms INTEGER NOT NULL,
        PRIMARY KEY(monitor_id,type,record_id))""",
    "CREATE INDEX network_samples_time ON network_samples(monitor_id,type,created_ms,record_id)",
    "CREATE INDEX network_samples_retention ON network_samples(created_ms)",
    """CREATE TABLE network_checkpoints (
        monitor_id TEXT NOT NULL, type TEXT NOT NULL, created_ms INTEGER NOT NULL,
        record_id TEXT NOT NULL, PRIMARY KEY(monitor_id,type))""",
    """CREATE TABLE network_daily (
        monitor_id TEXT NOT NULL, type TEXT NOT NULL, day_ms INTEGER NOT NULL,
        sample_count INTEGER NOT NULL, total_count INTEGER NOT NULL, success_count INTEGER NOT NULL,
        res_sum INTEGER NOT NULL, res_min REAL, res_max REAL, first_ms INTEGER NOT NULL,
        last_ms INTEGER NOT NULL, PRIMARY KEY(monitor_id,type,day_ms))""",
    """CREATE VIEW network_daily_stats AS SELECT *,
        CASE WHEN success_count>0 THEN res_sum/1000.0/success_count END AS avg_ms,
        CASE WHEN total_count>0 THEN 100.0*(total_count-success_count)/total_count END AS loss_pct
        FROM network_daily""",
    """CREATE TABLE network_events (
        event_id TEXT PRIMARY KEY, stream_key TEXT NOT NULL, kind TEXT NOT NULL,
        monitor_id TEXT, started_ms INTEGER NOT NULL, detected_ms INTEGER NOT NULL,
        recovered_ms INTEGER, recovery_detected_ms INTEGER, details_json TEXT NOT NULL,
        UNIQUE(stream_key,started_ms))""",
    "CREATE INDEX network_events_time ON network_events(started_ms,event_id)",
    """CREATE TABLE network_event_state (
        stream_key TEXT PRIMARY KEY, last_bucket_ms INTEGER NOT NULL,
        abnormal_run INTEGER NOT NULL, recovery_run INTEGER NOT NULL,
        candidate_ms INTEGER, open_event_id TEXT)""",
)


def validate_schema(conn):
    for table, columns in TABLES.items():
        if [r[1] for r in conn.execute("PRAGMA table_info(" + table + ")")] != columns.split(","):
            raise ArchiveError("Unsupported network archive schema")
    if conn.execute("SELECT count(*) FROM network_archive_meta WHERE singleton=1").fetchone()[0] != 1:
        raise ArchiveError("Missing network archive metadata")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='view' AND name='network_daily_stats'").fetchone() is None:
        raise ArchiveError("Missing network daily view")


def migrate(conn, check_mount):
    """Add network tables atomically; v1 also gains the v2 frequency table / 原子增量。"""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 3:
        validate_schema(conn)
        return
    if current not in (1, 2):
        raise ArchiveError("Existing v1/v2 archive required")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if current == 1:
            create_frequency_schema(conn)
        for statement in DDL:
            conn.execute(statement)
        conn.execute("PRAGMA user_version=3")
        validate_schema(conn)
        check_mount()
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
