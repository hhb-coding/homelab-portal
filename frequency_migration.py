"""Explicit additive archive migration / 显式、增量历史库迁移。

Caller must hold the archive writer lock and provide the HDD guard.
调用方必须持有归档锁，并在提交前校验 HDD。
"""
from metrics_archive import ArchiveError


def migrate(conn, target, check_mount):
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if target not in (1, 2) or current not in (1, 2):
        raise ArchiveError("Unsupported migration version")
    if current == target:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        if target == 2:
            conn.execute("""CREATE TABLE cpu_frequency_samples (
                device_id TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                sampled_utc TEXT NOT NULL,
                payload TEXT NOT NULL,
                received_utc TEXT NOT NULL,
                archived_utc TEXT NOT NULL,
                PRIMARY KEY(device_id,sample_id))""")
            conn.execute("CREATE INDEX frequency_device_time ON cpu_frequency_samples(device_id,sampled_utc,sample_id)")
            conn.execute("CREATE INDEX frequency_retention ON cpu_frequency_samples(sampled_utc)")
        else:
            if conn.execute("SELECT count(*) FROM cpu_frequency_samples").fetchone()[0]:
                raise ArchiveError("Nonempty frequency history: use compatibility rollback; no data may be dropped")
            conn.execute("DROP TABLE cpu_frequency_samples")
        conn.execute("PRAGMA user_version=" + str(target))
        check_mount()
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
