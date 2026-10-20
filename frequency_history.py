"""Executable Step 7.06 frequency query contract / 可执行统一历史查询契约。

Other metrics retain their source timestamps; no nearest-neighbour fabrication.
其他指标保留来源时间轴，不做伪造的最近邻同步。
"""
from datetime import timedelta
import json

from frequency import TelemetryError, parse_time, stamp


def query(conn, device_id, start, end, after=None, limit=2000):
    start, end = parse_time(start), parse_time(end)
    if not start < end or end-start > timedelta(days=180) or not 1 <= limit <= 2000:
        raise TelemetryError("invalid_range")
    if conn.execute("PRAGMA user_version").fetchone()[0] != 2:
        raise TelemetryError("archive_migration_required", 503)
    cursor_time, cursor_id = stamp(start), ""
    if after:
        try:
            cursor_time, cursor_id = json.loads(after)
            cursor_time = stamp(parse_time(cursor_time))
            if not isinstance(cursor_id, str) or len(cursor_id) > 64:
                raise ValueError()
        except (ValueError, TypeError):
            raise TelemetryError("invalid_cursor") from None
    rows = conn.execute("""SELECT sampled_utc,sample_id,payload FROM cpu_frequency_samples
        WHERE device_id=? AND sampled_utc>=? AND sampled_utc<?
        AND (sampled_utc>? OR (sampled_utc=? AND sample_id>?))
        ORDER BY sampled_utc,sample_id LIMIT ?""",
                        (device_id, stamp(start), stamp(end), cursor_time, cursor_time, cursor_id, limit+1)).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"device_id": device_id, "metric": "cpu_frequency_ghz", "unit": "GHz", "resolution": "raw",
            "start": stamp(start), "end": stamp(end), "interval": "[start,end)",
            "points": [json.loads(row[2]) for row in rows],
            "next_cursor": json.dumps(list(rows[-1][:2]), separators=(",", ":")) if more else None,
            "missing": "gaps; unavailable observations have null values; no interpolation"}
