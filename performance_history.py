"""Bounded archive queries and current inbox values / 有界历史查询及队列当前值。"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
import sqlite3
import time

from frequency import TelemetryError, parse_time, stamp

METRICS = (("cpu_frequency_ghz", "CPU Frequency", "GHz"),
           ("cpu_percent", "CPU Usage", "%"),
           ("cpu_temperature_c", "CPU Temperature", "°C"))

EXTENDED_METRICS = (("memory_percent", "Memory Usage", "%"),
                    ("disk_percent", "Disk Usage", "%"),
                    ("network_upload_bytes_per_second", "Upload / 上传", "B/s"),
                    ("network_download_bytes_per_second", "Download / 下载", "B/s"))


def bandwidth(sample):
    """Beszel stats.b = [sent B/s, received B/s]; never infer legacy ns/nr units."""
    value = sample.get("b")
    if not isinstance(value, list) or len(value) != 2:
        return (None, None)
    return tuple(number(v, 0, 10_000_000_000) for v in value)


def device_role(device, local_device_id):
    if local_device_id and device.get("device_id") == local_device_id:
        return "hp"
    # Scope only the established X230 registration / 仅识别现有 X230 登记。
    identity = " ".join(str(device.get(k) or "") for k in ("device_id", "hostname", "display_name"))
    return "x230" if "x230" in identity.lower() else None


def number(value, low, high):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None


def latest_frequency(path, device_id, now=None):
    """Read receipts too; sampled time, not arrival order / 同时读取回执，以采样时间排序。"""
    now = now or datetime.now(timezone.utc)
    result = {"cpu_frequency_ghz": None, "frequency_sampled_utc": None,
              "frequency_source": None, "frequency_quality": None, "frequency_freshness": "unavailable"}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
            conn.execute("PRAGMA query_only=ON")
            latest = None
            for body, in conn.execute("SELECT payload FROM frequency_inbox WHERE device_id=?", (device_id,)):
                sample = json.loads(body)
                when = parse_time(sample.get("sampled_utc"))
                key = (when, sample.get("sample_id", ""))
                if latest is None or key > latest[0]:
                    latest = (key, sample)
        if latest:
            (when, _), sample = latest
            age = (now - when).total_seconds()
            value = number(sample.get("cpu_frequency_ghz"), 0.000001, 20)
            fresh = 0 <= age <= 120 and sample.get("quality") == "ok" and value is not None
            result.update(cpu_frequency_ghz=value if fresh else None,
                          frequency_sampled_utc=stamp(when), frequency_source=sample.get("source"),
                          frequency_quality=sample.get("quality"),
                          frequency_freshness="fresh" if fresh else "stale" if age > 120 else "invalid")
    except (sqlite3.Error, ValueError, TypeError, AttributeError):
        pass  # Inbox failure cannot break the dashboard / 队列故障不影响其他指标。
    return result


def query(conn, device, role, start, end, extended=False):
    start, end = parse_time(start), parse_time(end)
    seconds = (end-start).total_seconds()
    if not 0 < seconds <= 180 * 86400:
        raise TelemetryError("invalid_range")
    if conn.execute("PRAGMA user_version").fetchone()[0] not in (2, 3):
        raise TelemetryError("archive_migration_required", 503)
    # At most 500 bins; source rows stream, never fetchall / 最多500桶，流式读取原始行。
    if seconds <= 3600:
        width = 60
    elif seconds <= 6 * 3600:
        width = 300
    elif seconds <= 24 * 3600:
        width = 900
    else:
        width = max(60, math.ceil(seconds / 500 / 60) * 60)
    size = math.ceil(seconds / width)
    sensor = "k10temp" if role == "hp" else "CPU Package"
    metrics = METRICS + EXTENDED_METRICS if extended else METRICS
    series = []
    for key, label, unit in metrics:
        series.append({"metric": key, "label": label, "unit": unit,
                       "sensor": sensor if key == "cpu_temperature_c" else None,
                       "points": [], "stats": {"count": 0, "average": None, "peak": None}})
    bins = [[[] for _ in range(size)] for _ in metrics]
    # Each accumulator is constant-sized / 每桶仅保留固定大小累加器。
    def add(metric, timestamp, value):
        index = int((parse_time(timestamp)-start).total_seconds() // width)
        if not 0 <= index < size:
            return
        bucket = bins[metric][index]
        if value is None:
            if not bucket:
                bucket.extend([0, 0.0, None, None, None, None, False])
            bucket[6] = True
            return
        if not bucket:
            bucket.extend([0, 0.0, value, value, timestamp, timestamp, False])
        if bucket[5] and (parse_time(timestamp)-parse_time(bucket[5])).total_seconds() > 90:
            bucket[6] = True
        bucket[0] += 1
        bucket[1] += value
        bucket[2] = value if bucket[2] is None else min(bucket[2], value)
        bucket[3] = value if bucket[3] is None else max(bucket[3], value)
        bucket[4] = bucket[4] or timestamp
        bucket[5] = timestamp
        stats = series[metric]["stats"]
        stats["count"] += 1
        stats["sum"] = stats.get("sum", 0.0) + value
        if stats["peak"] is None or value > stats["peak"]:
            stats["peak"], stats["peak_at"] = value, timestamp

    deadline = time.monotonic() + 5
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        for timestamp, body in conn.execute("""SELECT sampled_utc,payload FROM cpu_frequency_samples
                WHERE device_id=? AND sampled_utc>=? AND sampled_utc<? ORDER BY sampled_utc,sample_id""",
                (device["device_id"], stamp(start), stamp(end))):
            sample = json.loads(body)
            value = number(sample.get("cpu_frequency_ghz"), 0.000001, 20) if sample.get("quality") == "ok" else None
            add(0, timestamp, value)
            if time.monotonic() > deadline:
                raise TelemetryError("query_timeout", 503)
        for timestamp, body in conn.execute("""SELECT created_utc,stats_json FROM samples
                WHERE system_id=? AND created_utc>=? AND created_utc<? ORDER BY created_utc,record_id""",
                (device.get("beszel_system_id"), stamp(start), stamp(end))):
            sample = json.loads(body)
            temperatures = sample.get("t")
            add(1, timestamp, number(sample.get("cpu"), 0, 100))
            add(2, timestamp, number(temperatures.get(sensor), -50, 150) if isinstance(temperatures, dict) else None)
            if extended:
                add(3, timestamp, number(sample.get("mp"), 0, 100))
                add(4, timestamp, number(sample.get("dp"), 0, 100))
                upload, download = bandwidth(sample)
                add(5, timestamp, upload)
                add(6, timestamp, download)
            if time.monotonic() > deadline:
                raise TelemetryError("query_timeout", 503)
    finally:
        conn.set_progress_handler(None, 0)
    for metric, item in enumerate(series):
        previous = None
        for index, b in enumerate(bins[metric]):
            valid = bool(b and b[0])
            item["points"].append({"timestamp": stamp(start+timedelta(seconds=index*width)),
                "value": b[1]/b[0] if valid else None, "count": b[0] if b else 0,
                "min": b[2] if valid else None, "max": b[3] if valid else None,
                "first_sample": b[4] if valid else None, "last_sample": b[5] if valid else None,
                "gap": bool(b and b[6]) or bool(valid and previous and
                    (parse_time(b[4])-parse_time(previous)).total_seconds() > 90)})
            previous = b[5] if valid else None
        stats = item["stats"]
        total = stats.pop("sum", 0)
        stats["average"] = total/stats["count"] if stats["count"] else None
    return {"status": "ok", "device_id": device["device_id"], "start": stamp(start), "end": stamp(end),
            "interval": "[start,end)", "bucket_seconds": width, "series": series,
            "mapping_note": "Current Beszel mapping only; historical rebinding cannot be reconstructed / 使用当前关联，无法还原历史重绑定",
            "missing": "No interpolation; partial buckets marked gap / 不插值，部分缺失桶标记 gap"}
