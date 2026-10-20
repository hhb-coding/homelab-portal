"""CPU telemetry contract and bounded durable inbox / 频率契约及有界持久队列。

No configuration or database is opened on import / 导入不读取配置或打开数据库。
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import re
import sqlite3

UTC = timezone.utc
MAX_ROWS = 14400  # ten devices, 24 hours / 十台设备一天
MAX_BYTES = 16 * 1024 * 1024
MAX_BATCH = 120
SOURCES = {"linux_scaling_cur_freq", "linux_cpuinfo_cur_freq", "windows_processor_performance"}


class TelemetryError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value):
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError()
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        raise TelemetryError("invalid_timestamp") from None


def canonical(sample, now):
    fields = {"sample_id", "sampled_utc", "cpu_frequency_ghz", "source", "quality",
              "logical_cpu_count", "valid_cpu_count", "window_ms", "error"}
    if not isinstance(sample, dict) or set(sample) != fields:
        raise TelemetryError("invalid_fields")
    if not isinstance(sample["sample_id"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,64}", sample["sample_id"]):
        raise TelemetryError("invalid_sample_id")
    when = parse_time(sample["sampled_utc"])
    if when.microsecond % 1000:
        raise TelemetryError("unsupported_timestamp_precision")
    if when < now - timedelta(hours=24):
        raise TelemetryError("sample_expired", 422)
    if when > now + timedelta(minutes=5):
        raise TelemetryError("clock_ahead", 422)
    total, valid = sample["logical_cpu_count"], sample["valid_cpu_count"]
    if (type(total) is not int or type(valid) is not int or not 0 <= valid <= total <= 4096
            or type(sample["window_ms"]) is not int or not 0 <= sample["window_ms"] <= 10000):
        raise TelemetryError("invalid_cpu_counts")
    if (not isinstance(sample["source"], str) or not isinstance(sample["quality"], str)
            or sample["source"] not in SOURCES or sample["quality"] not in {"ok", "partial", "unavailable"}):
        raise TelemetryError("invalid_source_or_quality")
    value = sample["cpu_frequency_ghz"]
    error = sample["error"]
    if error is not None and (not isinstance(error, str) or error not in {"read_failed", "invalid_counter", "partial_read"}):
        raise TelemetryError("invalid_error")
    if sample["quality"] == "unavailable":
        if value is not None or valid != 0 or error is None:
            raise TelemetryError("invalid_missing_sample")
    elif (type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 20
          or valid == 0 or (sample["quality"] == "ok" and (valid != total or error is not None))
          or (sample["quality"] == "partial" and (valid >= total or error != "partial_read"))):
        raise TelemetryError("invalid_frequency")
    normalized = dict(sample, sampled_utc=stamp(when))
    if value is not None:
        normalized["cpu_frequency_ghz"] = float(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)


def connect_registry(path):
    # Existing file only; never create a misconfigured registry / 不创建误配注册库。
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def receive(path, device_id, samples, now=None, max_rows=MAX_ROWS, max_bytes=MAX_BYTES):
    now = now or datetime.now(UTC)
    if not isinstance(device_id, str) or not 1 <= len(device_id) <= 128:
        raise TelemetryError("invalid_device_id")
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_BATCH:
        raise TelemetryError("invalid_batch")
    prepared = [json.loads(canonical(s, now)) for s in samples]
    with closing(connect_registry(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not conn.execute("SELECT 1 FROM devices WHERE device_id=?", (device_id,)).fetchone():
                raise TelemetryError("unknown_device", 403)
            expired = conn.execute("SELECT count(*) FROM frequency_inbox WHERE received_utc < ? AND archived=0",
                                   (stamp(now-timedelta(hours=24)),)).fetchone()[0]
            conn.execute("UPDATE frequency_queue_status SET expired=expired+? WHERE singleton=1", (expired,))
            conn.execute("DELETE FROM frequency_inbox WHERE received_utc < ?", (stamp(now-timedelta(hours=24)),))
            accepted, duplicates = [], []
            for s in prepared:
                body = json.dumps(s, sort_keys=True, separators=(",", ":"), allow_nan=False)
                key = (device_id, s["sample_id"])
                old = conn.execute("SELECT payload FROM frequency_inbox WHERE device_id=? AND sample_id=?", key).fetchone()
                if old:
                    if old[0] != body:
                        raise TelemetryError("sample_conflict", 409)
                    duplicates.append(s["sample_id"])
                else:
                    conn.execute("INSERT INTO frequency_inbox VALUES (?,?,?,?,?,0)",
                                 (*key, stamp(now), body, len(body.encode("utf-8"))))
                    accepted.append(s["sample_id"])
            count, size = conn.execute("SELECT count(*),coalesce(sum(payload_bytes),0) FROM frequency_inbox").fetchone()
            device_count = conn.execute("SELECT count(*) FROM frequency_inbox WHERE device_id=?", (device_id,)).fetchone()[0]
            if count > max_rows or size > max_bytes or device_count > 1440:
                raise TelemetryError("queue_full", 503)
            conn.commit()
            return {"accepted": accepted, "duplicates": duplicates, "expired_unarchived": expired}
        except BaseException:
            conn.rollback()
            raise


def queue_status(path):
    with closing(connect_registry(path)) as conn:
        pending, size = conn.execute("SELECT count(*),coalesce(sum(payload_bytes),0) FROM frequency_inbox WHERE archived=0").fetchone()
        expired = conn.execute("SELECT expired FROM frequency_queue_status WHERE singleton=1").fetchone()[0]
        return {"pending": pending, "pending_payload_bytes": size, "expired_unarchived_total": expired,
                "ttl_hours": 24, "max_rows_including_receipts": MAX_ROWS, "max_payload_bytes": MAX_BYTES}


def drain(archive, registry_path, check_mount, now=None, batch_size=120):
    """Archive commit precedes inbox ACK; replay is idempotent / 先提交再确认。"""
    now = now or datetime.now(UTC)
    if archive.execute("PRAGMA user_version").fetchone()[0] != 2:
        raise TelemetryError("archive_migration_required", 503)
    with closing(connect_registry(registry_path)) as inbox:
        with inbox:
            cutoff = stamp(now-timedelta(hours=24))
            expired = inbox.execute("SELECT count(*) FROM frequency_inbox WHERE received_utc < ? AND archived=0", (cutoff,)).fetchone()[0]
            inbox.execute("UPDATE frequency_queue_status SET expired=expired+? WHERE singleton=1", (expired,))
            inbox.execute("DELETE FROM frequency_inbox WHERE received_utc < ?", (cutoff,))
        rows = inbox.execute("SELECT device_id,sample_id,payload,received_utc FROM frequency_inbox WHERE archived=0 ORDER BY received_utc,device_id,sample_id LIMIT ?",
                             (batch_size,)).fetchall()
        check_mount()
        with archive:
            for device, identity, body, received in rows:
                sample = json.loads(body)
                old = archive.execute("SELECT payload FROM cpu_frequency_samples WHERE device_id=? AND sample_id=?", (device, identity)).fetchone()
                if old and old[0] != body:
                    raise TelemetryError("archive_sample_conflict", 409)
                archive.execute("INSERT OR IGNORE INTO cpu_frequency_samples VALUES (?,?,?,?,?,?)",
                                (device, identity, sample["sampled_utc"], body, received, stamp(now)))
            archive.execute("DELETE FROM cpu_frequency_samples WHERE sampled_utc < ?", (stamp(now-timedelta(days=180)),))
            check_mount()
        with inbox:
            inbox.executemany("UPDATE frequency_inbox SET archived=1 WHERE device_id=? AND sample_id=? AND payload=?", [r[:3] for r in rows])
        return len(rows)
