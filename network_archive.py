"""API-only minute archive; incremental durable daily totals / 网络分钟归档与长期汇总。"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from requests.exceptions import RequestException

from beszel_client import network_identity, network_timestamp
from metrics_archive import ArchiveError, MountError

MINUTE = 60_000
DAY = 86_400_000
RETENTION = 90 * DAY
OVERLAP = 10 * MINUTE
DEFAULT_RULES = {"abnormal_minutes": 3, "recovery_minutes": 2}
REQUIRED_ROLES = {"upstream_gateway", "lan_gateway", "public_primary", "public_control"}
CORRELATION_ROLES = ("public_primary", "public_control", "upstream_gateway")
FAILURES = (KeyError, TypeError, ValueError, RuntimeError, sqlite3.Error, RequestException)


def milliseconds(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ArchiveError("Timezone-aware run time required")
    return network_timestamp(int(now.timestamp() * 1000))


def compact(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def load_roles(path):
    """Private file only; no production defaults embedded / 仅本机配置，无生产默认地址。"""
    if not path:
        return None
    config = json.loads(Path(path).read_text())
    network_identity(config["system_id"])
    targets = config["targets"]
    if not isinstance(targets, dict) or not REQUIRED_ROLES <= targets.keys():
        raise ValueError("Missing network roles")
    values = list(targets.values())
    if any(not isinstance(x, str) or not x or "<" in x or ">" in x for x in values):
        raise ValueError("Replace role placeholders privately")
    if len(set(values)) != len(values):
        raise ValueError("Network role targets must be distinct")
    rules = {k: config.get(k, v) for k, v in DEFAULT_RULES.items()}
    if any(type(v) is not int or not 1 <= v <= 60 for v in rules.values()):
        raise ValueError("Invalid network event thresholds")
    return {"system_id": config["system_id"], "targets": targets, **rules}


def _monitor(record):
    identity, system = network_identity(record["id"]), network_identity(record["system"])
    target = record["target"]
    if (not isinstance(target, str) or not target or record["protocol"] not in ("icmp", "tcp", "http", "dns")
            or type(record["interval"]) is not int or record["interval"] <= 0
            or type(record["enabled"]) is not bool):
        raise ArchiveError("Invalid network monitor")
    return (identity, system, target, record["protocol"], record["interval"], int(record["enabled"]))


def _sample(record, monitor, start, end, previous):
    identity = network_identity(record["id"])
    created = network_timestamp(record["created"])
    key = (created, identity)
    if (record["monitor"] != monitor[0] or record["system"] != monitor[1] or record["type"] != "1m"
            or not start <= created <= end or (previous is not None and key <= previous)):
        raise ArchiveError("Invalid or unordered network sample")
    total, success, summed = (record[k] for k in ("total_count", "success_count", "res_sum"))
    if any(type(v) is not int or not 0 <= v <= 2**63-1 for v in (total, success, summed)) or success > total:
        raise ArchiveError("Invalid probe counts or response sum")
    low, high = record["res_min"], record["res_max"]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (low, high)):
        raise ArchiveError("Invalid response bounds")
    if success:
        if not low <= summed / success <= high:
            raise ArchiveError("Response sum outside bounds")
    elif summed:
        raise ArchiveError("Failed probes cannot contribute latency")
    else:
        low = high = None
    return key, (monitor[0], "1m", identity, created, monitor[1], low, high, summed, total, success,
                 compact(record))


def _insert(conn, row, run_ms):
    old = conn.execute("""SELECT created_ms,system_id,res_min,res_max,res_sum,total_count,success_count
        FROM network_samples WHERE monitor_id=? AND type=? AND record_id=?""", row[:3]).fetchone()
    if old:
        if old != row[3:10]:
            raise ArchiveError("Conflicting immutable network sample")
        return False
    conn.execute("INSERT INTO network_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*row, run_ms))
    monitor, kind, _, created, _, low, high, summed, total, success = row[:10]
    # Only newly inserted rows contribute. Never rebuild totals from a pruned day.
    # 仅首次插入时累加；禁止从已清理的原始行重建日汇总。
    conn.execute("""INSERT INTO network_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(monitor_id,type,day_ms) DO UPDATE SET
        sample_count=network_daily.sample_count+1,
        total_count=network_daily.total_count+excluded.total_count,
        success_count=network_daily.success_count+excluded.success_count,
        res_sum=network_daily.res_sum+excluded.res_sum,
        res_min=CASE WHEN excluded.res_min IS NULL THEN network_daily.res_min
            WHEN network_daily.res_min IS NULL THEN excluded.res_min
            ELSE min(network_daily.res_min,excluded.res_min) END,
        res_max=CASE WHEN excluded.res_max IS NULL THEN network_daily.res_max
            WHEN network_daily.res_max IS NULL THEN excluded.res_max
            ELSE max(network_daily.res_max,excluded.res_max) END,
        first_ms=min(network_daily.first_ms,excluded.first_ms),
        last_ms=max(network_daily.last_ms,excluded.last_ms)""",
        (monitor, kind, created//DAY*DAY, 1, total, success, summed, low, high, created, created))
    return True


def collect(conn, client, now=None, page_size=200, check_mount=lambda: None, roles=None):
    """Reuse the 7.04 writer lock/guard; never migrate automatically / 不自动迁移。"""
    if conn.execute("PRAGMA user_version").fetchone()[0] != 3:
        raise ArchiveError("Explicit network archive migration required")
    if type(page_size) is not int or not 1 <= page_size <= 500:
        raise ArchiveError("Invalid network page size")
    run_ms = milliseconds(now or datetime.now(timezone.utc))
    floor = conn.execute("SELECT retention_floor_ms FROM network_archive_meta WHERE singleton=1").fetchone()[0]
    cutoff = max(0, run_ms-RETENTION, floor)
    if cutoff > run_ms:
        raise ArchiveError("Network clock is behind retention floor")
    report = {"network_monitors": 0, "network_inserted": 0, "network_duplicates": 0,
              "network_failed": 0, "network_pruned": 0, "network_correlation_ready": 0}
    after_monitor = None
    while True:
        try:
            monitors = client.get_network_monitors_page(after_monitor, page_size)
            if not isinstance(monitors, list) or len(monitors) > page_size:
                raise ArchiveError("Invalid monitor page")
            if not monitors:
                break
            previous = after_monitor
            prepared = []
            for record in monitors:
                monitor = _monitor(record)
                if previous is not None and monitor[0] <= previous:
                    raise ArchiveError("Repeated or unordered monitor page")
                prepared.append((monitor, compact(record)))
                previous = monitor[0]
        except FAILURES:
            report["network_failed"] += 1
            break
        for monitor, raw in prepared:
            report["network_monitors"] += 1
            try:
                binding = conn.execute("SELECT system_id,target,protocol FROM network_monitors WHERE monitor_id=?",
                                       (monitor[0],)).fetchone()
                if binding is not None and binding != monitor[1:4]:
                    raise ArchiveError("Monitor identity rebound; a new monitor ID is required")
                check_mount()
                with conn:
                    conn.execute("""INSERT INTO network_monitors VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(monitor_id) DO UPDATE SET system_id=excluded.system_id,
                        target=excluded.target,protocol=excluded.protocol,interval=excluded.interval,
                        enabled=excluded.enabled,config_json=excluded.config_json,archived_ms=excluded.archived_ms""",
                        (*monitor, raw, run_ms))
                    check_mount()
                checkpoint = conn.execute("""SELECT created_ms,record_id FROM network_checkpoints
                    WHERE monitor_id=? AND type='1m'""", (monitor[0],)).fetchone()
                if checkpoint and checkpoint[0] > run_ms:
                    raise ArchiveError("Network checkpoint is ahead of run time")
                start = max(cutoff, checkpoint[0]-OVERLAP) if checkpoint else cutoff
                after = None
                while True:
                    records = client.get_network_archive_page(monitor[0], start, run_ms, after, page_size)
                    if not isinstance(records, list) or len(records) > page_size:
                        raise ArchiveError("Invalid network sample page")
                    if not records:
                        break  # No checkpoint for an empty page / 空页不推进断点。
                    rows, previous = [], after
                    for record in records:
                        previous, row = _sample(record, monitor, start, run_ms, previous)
                        rows.append(row)
                    check_mount()
                    inserted = 0
                    with conn:
                        for row in rows:
                            inserted += _insert(conn, row, run_ms)
                        conn.execute("""INSERT INTO network_checkpoints VALUES (?,'1m',?,?)
                            ON CONFLICT(monitor_id,type) DO UPDATE SET
                            created_ms=excluded.created_ms,record_id=excluded.record_id
                            WHERE excluded.created_ms>network_checkpoints.created_ms OR
                            (excluded.created_ms=network_checkpoints.created_ms AND excluded.record_id>network_checkpoints.record_id)""",
                            (monitor[0], previous[0], previous[1]))
                        check_mount()
                    report["network_inserted"] += inserted
                    report["network_duplicates"] += len(rows)-inserted
                    after = previous  # Request again after short pages too / 短页仍继续。
            except MountError:
                raise
            except FAILURES:
                report["network_failed"] += 1
        after_monitor = prepared[-1][0][0]
    report.update(maintain(conn, run_ms, roles, check_mount,
                           allow_correlation=not report["network_failed"]))
    return report


def maintain(conn, run_ms, roles=None, check_mount=lambda: None, allow_correlation=True):
    """Local retention/events also work when API authentication is unavailable."""
    if conn.execute("PRAGMA user_version").fetchone()[0] != 3:
        raise ArchiveError("Explicit network archive migration required")
    ready = evaluate_events(conn, run_ms, roles, check_mount, allow_correlation)
    prune(conn, max(0, run_ms-RETENTION), check_mount)
    return {"network_correlation_ready": ready,
            "network_pruned": conn.execute("SELECT changes()").fetchone()[0]}


def prune(conn, cutoff, check_mount=lambda: None):
    """A durable monotonic floor blocks replay of expired records after clock rollback."""
    check_mount()
    with conn:
        conn.execute("UPDATE network_archive_meta SET retention_floor_ms=max(retention_floor_ms,?) WHERE singleton=1", (cutoff,))
        conn.execute("DELETE FROM network_samples WHERE created_ms < (SELECT retention_floor_ms FROM network_archive_meta WHERE singleton=1)")
        check_mount()


def _observations(conn, monitor_ids, after, upper):
    placeholders = ",".join("?" for _ in monitor_ids)
    return conn.execute(f"""SELECT (created_ms/60000)*60000 AS bucket,monitor_id,
        sum(total_count),sum(success_count) FROM network_samples
        WHERE type='1m' AND monitor_id IN ({placeholders}) AND created_ms>=? AND created_ms<=?
        GROUP BY bucket,monitor_id ORDER BY bucket,monitor_id""", (*monitor_ids, after+MINUTE, upper))


def _buckets(conn, monitor_ids, after, upper):
    previous, values = None, {}
    for bucket, monitor, total, success in _observations(conn, monitor_ids, after, upper):
        if previous is not None and bucket != previous:
            yield previous, values
            values = {}
        values[monitor] = None if total == 0 else ("healthy" if success == total else "abnormal")
        previous = bucket
    if previous is not None:
        yield previous, values


def _event_stream(conn, key, kind, monitor_id, ids, upper, rules, details, check_mount):
    state = conn.execute("SELECT last_bucket_ms,abnormal_run,recovery_run,candidate_ms,open_event_id FROM network_event_state WHERE stream_key=?", (key,)).fetchone()
    last, bad, good, candidate, opened = state or (-MINUTE, 0, 0, None, None)
    changed = False
    check_mount()
    with conn:
        for bucket, values in _buckets(conn, ids, last, upper):
            changed = True
            if bucket-last != MINUTE:
                bad = good = 0
                candidate = None
            if kind == "target_anomaly":
                status = values.get(ids[0])
            else:
                primary, control, upstream = (values.get(i) for i in ids)
                status = ("abnormal" if primary == control == "abnormal" and upstream == "healthy"
                          else "healthy" if primary == control == upstream == "healthy" else None)
            if status is None:
                bad = good = 0
                candidate = None  # Unknown never opens or recovers an incident / 缺测不触发或恢复。
            elif status == "abnormal":
                good = 0
                candidate = bucket if bad == 0 else candidate
                bad = min(bad+1, rules["abnormal_minutes"])
                if opened is None and bad >= rules["abnormal_minutes"]:
                    opened = hashlib.sha256(f"{key}:{candidate}".encode()).hexdigest()
                    conn.execute("INSERT INTO network_events VALUES (?,?,?,?,?,?,NULL,NULL,?)",
                        (opened, key, kind, monitor_id, candidate, bucket, compact(details)))
            else:
                bad, candidate = 0, None
                good = min(good+1, rules["recovery_minutes"])
                if opened and good >= rules["recovery_minutes"]:
                    conn.execute("UPDATE network_events SET recovered_ms=?,recovery_detected_ms=? WHERE event_id=?",
                        (bucket-(rules["recovery_minutes"]-1)*MINUTE, bucket, opened))
                    opened = None
            last = bucket
        if changed:
            conn.execute("""INSERT INTO network_event_state VALUES (?,?,?,?,?,?)
                ON CONFLICT(stream_key) DO UPDATE SET last_bucket_ms=excluded.last_bucket_ms,
                abnormal_run=excluded.abnormal_run,recovery_run=excluded.recovery_run,
                candidate_ms=excluded.candidate_ms,open_event_id=excluded.open_event_id""",
                (key, last, bad, good, candidate, opened))
        check_mount()


def evaluate_events(conn, run_ms, roles=None, check_mount=lambda: None, allow_correlation=True):
    """Wait ten minutes after a UTC minute ends; persist streaks beyond raw TTL.

    任意丢包连续三分钟触发，零丢包连续两分钟恢复；十分钟迟到窗口后判定。
    """
    rules = {k: (roles or {}).get(k, v) for k, v in DEFAULT_RULES.items()}
    upper = (run_ms-OVERLAP)//MINUTE*MINUTE-1
    monitors = conn.execute("SELECT monitor_id,system_id,target,protocol,enabled FROM network_monitors ORDER BY monitor_id").fetchall()
    for identity, system, target, protocol, enabled in monitors:
        details = {"system_id": system, "target": target, "protocol": protocol, **rules}
        signature = hashlib.sha256(compact(details).encode()).hexdigest()[:16]
        _event_stream(conn, "target:"+identity+":"+signature, "target_anomaly", identity,
                      [identity], upper, rules, details, check_mount)
    if not roles or not allow_correlation:
        return 0
    mapping = {}
    for role in CORRELATION_ROLES:
        target = roles["targets"][role]
        matches = [m[0] for m in monitors if m[1] == roles["system_id"] and m[2] == target
                   and m[3] == "icmp" and m[4]]
        if len(matches) != 1:
            return 0  # Missing/ambiguous correlation roles are unknown / 关联角色未知。
        mapping[role] = matches[0]
    ids = [mapping[r] for r in CORRELATION_ROLES]
    checkpoints = [conn.execute("SELECT created_ms FROM network_checkpoints WHERE monitor_id=? AND type='1m'", (i,)).fetchone() for i in ids]
    if not all(checkpoints):
        return 0
    upper = min(upper, (min(c[0] for c in checkpoints)//MINUTE+1)*MINUTE-1)
    # Include resolved IDs, so replacing a monitor cannot continue another monitor's incident.
    details = {"system_id": roles["system_id"], "monitor_ids": mapping,
               "targets": {r: roles["targets"][r] for r in CORRELATION_ROLES}, **rules}
    key = "public:"+hashlib.sha256(compact(details).encode()).hexdigest()
    _event_stream(conn, key, "suspected_public_connectivity", None, ids, upper,
                  rules, details, check_mount)
    return 1
