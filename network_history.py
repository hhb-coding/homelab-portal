"""Bounded read-only network archive queries / 有界只读网络归档查询。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

RANGES = {"1h": (timedelta(hours=1), "1m"), "3h": (timedelta(hours=3), "1m"),
          "6h": (timedelta(hours=6), "1m"), "10h": (timedelta(hours=10), "1m"),
          "24h": (timedelta(hours=24), "1m"),
          "7d": (timedelta(days=7), "1d"), "30d": (timedelta(days=30), "1d")}
ROLES = ("lan_gateway", "upstream_gateway", "endpoint_a", "endpoint_b", "public_primary", "public_control")


def sample(time, res_sum, total, success):
    """Keep exact archived counts; never infer failures from rounded loss / 保留实际计数。"""
    return dict(time=time, rtt_ms=(res_sum / success / 1000 if success else None),
                loss_pct=(100 * (total - success) / total if total else None),
                count=total, success_count=success, failed_count=total-success)


def query(conn, roles_path, range_key, now=None):
    if range_key not in RANGES:
        raise ValueError("invalid_range")
    span, grain = RANGES[range_key]
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("invalid_time")
    now = now.astimezone(timezone.utc)
    config = None
    if roles_path:
        config = json.loads(Path(roles_path).read_text())
        if not isinstance(config, dict) or not isinstance(config.get("system_id"), str) or not isinstance(config.get("targets"), dict):
            raise ValueError("invalid_roles")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    targets = []
    monitor_ids = []
    if config:
        for role in ROLES:
            target = config["targets"].get(role)
            if not isinstance(target, str) or not target:
                raise ValueError("invalid_roles")
            if version != 3:
                targets.append(dict(role=role,target=target,monitor_id=None,protocol=None,interval=None,latest=None,latest_sample=None,peak_loss_pct=None,rows=[]))
                continue
            monitor = conn.execute("""SELECT monitor_id,protocol,interval FROM network_monitors
                WHERE system_id=? AND target=? AND enabled=1""", (config["system_id"], target)).fetchall()
            if len(monitor) != 1:
                targets.append(dict(role=role,target=target,monitor_id=None,protocol=None,interval=None,latest=None,latest_sample=None,peak_loss_pct=None,rows=[]))
                continue
            identity, protocol, interval = monitor[0]
            monitor_ids.append(identity)
            latest_row = conn.execute("""SELECT created_ms,res_sum,total_count,success_count
                FROM network_samples WHERE monitor_id=? AND type='1m' AND created_ms<?
                ORDER BY created_ms DESC,record_id DESC LIMIT 1""", (identity,int(now.timestamp()*1000))).fetchone()
            latest_sample = sample(*latest_row) if latest_row else None
            if grain == "1m":
                rows = conn.execute("""SELECT created_ms,res_min,res_max,res_sum,total_count,success_count
                    FROM network_samples WHERE monitor_id=? AND type='1m' AND created_ms>=? AND created_ms<?
                    ORDER BY created_ms,record_id LIMIT 1440""", (identity,int((now-span).timestamp()*1000),int(now.timestamp()*1000))).fetchall()
                points = [sample(r[0],r[3],r[4],r[5]) for r in rows]
            else:
                rows = conn.execute("""SELECT day_ms,res_sum,success_count,total_count,sample_count
                    FROM network_daily WHERE monitor_id=? AND type='1m' AND day_ms>=? AND day_ms<?
                    ORDER BY day_ms LIMIT 31""", (identity,int((now-span).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000),int(now.timestamp()*1000))).fetchall()
                points = [dict(sample(r[0],r[1],r[3],r[2]), samples=r[4]) for r in rows]
            peak = max((p['loss_pct'] for p in points if p['loss_pct'] is not None), default=None)
            targets.append(dict(role=role,target=target,monitor_id=identity,protocol=protocol,interval=interval,
                                latest=latest_row[0] if latest_row else None,latest_sample=latest_sample,
                                peak_loss_pct=peak,rows=points))
    events = []
    if version == 3 and config and monitor_ids:
        placeholders = ",".join("?" for _ in monitor_ids)
        events = [dict(id=r[0],kind=r[1],monitor_id=r[2],started=r[3],detected=r[4],recovered=r[5],
                       duration_ms=max(0,(r[5] or int(now.timestamp()*1000))-r[3]),details=json.loads(r[6]))
                  for r in conn.execute("""SELECT event_id,kind,monitor_id,started_ms,detected_ms,recovered_ms,details_json
                    FROM network_events WHERE (monitor_id IN ("""+placeholders+""" ) OR kind='suspected_public_connectivity')
                    AND started_ms>=? AND started_ms<? ORDER BY started_ms DESC,event_id LIMIT 200""",
                    (*monitor_ids,int((now-span).timestamp()*1000),int(now.timestamp()*1000)))]
    return dict(status="ok",schema_version=version,range=range_key,granularity=grain,
                start=int((now-span).timestamp()*1000),end=int(now.timestamp()*1000),targets=targets,events=events)
