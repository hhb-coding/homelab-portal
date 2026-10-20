#!/usr/bin/env python3
"""One current-frequency observation and bounded retry / 单次观测及有界重试。"""
from datetime import datetime, timedelta, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import uuid

from heartbeat_transport import send_json

UTC = timezone.utc
MAX_ROWS = 1440
MAX_BYTES = 1024 * 1024


def sample(root=Path("/sys/devices/system/cpu"), now=None):
    now = now or datetime.now(UTC)
    values = []
    online = []
    for cpu in sorted(root.glob("cpu[0-9]*")):
        if not cpu.name[3:].isdigit():
            continue
        try:
            if (cpu / "online").exists() and (cpu / "online").read_text().strip() == "0":
                continue
        except OSError:
            continue
        online.append(cpu)
    # Per logical CPU paths deliberately weight shared policies by online CPU count.
    # 每逻辑 CPU 读取，共享 policy 按在线逻辑 CPU 数加权；保留 7.01 的来源语义。
    for cpu in online:
        try:
            value = float((cpu / "cpufreq/scaling_cur_freq").read_text()) / 1000000
            if math.isfinite(value) and 0 < value <= 20:
                values.append(value)
        except (OSError, ValueError, UnicodeError):
            pass
    quality = "ok" if values and len(values) == len(online) else "partial" if values else "unavailable"
    return {"sample_id": uuid.uuid4().hex, "sampled_utc": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "cpu_frequency_ghz": sum(values)/len(values) if values else None,
            "source": "linux_scaling_cur_freq", "logical_cpu_count": len(online), "valid_cpu_count": len(values),
            "quality": quality, "window_ms": 0,
            "error": None if quality == "ok" else "partial_read" if values else "read_failed"}


def save(path, rows):
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(rows) > MAX_ROWS or len(encoded) > MAX_BYTES:
        raise RuntimeError("client_queue_full")
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def run(path, device, url, token, observation, now=None, transport=send_json):
    now = now or datetime.now(UTC)
    if not device or not token or not url:
        raise RuntimeError("configuration_missing")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.with_suffix(".lock").is_symlink():
        raise RuntimeError("unsafe_queue_path")
    with open(path.with_suffix(".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            raise RuntimeError("client_queue_full")
        rows = json.loads(path.read_text()) if path.exists() else []
        retained = [r for r in rows if datetime.fromisoformat(r["sampled_utc"].replace("Z", "+00:00")) >= now-timedelta(hours=24)]
        expired = len(rows)-len(retained)
        if expired:
            print("Frequency queue expired samples: " + str(expired), file=sys.stderr)
        rows = retained
        # Free a full backlog before accepting a new sample / 满队列先发送积压。
        if len(rows) >= MAX_ROWS and rows:
            batch = rows[:120]
            reply = transport(url.rstrip("/")+"/api/telemetry/cpu-frequency", token, {"device_id": device, "samples": batch})
            if set(reply.get("accepted", []) + reply.get("duplicates", [])) != {r["sample_id"] for r in batch}:
                raise RuntimeError("invalid_acknowledgement")
            rows = rows[len(batch):]
            save(path, rows)
        # Persist before upload; errors leave samples for next execution / 上传前持久化。
        rows.append(observation)
        save(path, rows)
        for _ in range(12):
            if not rows:
                break
            batch = rows[:120]
            reply = transport(url.rstrip("/")+"/api/telemetry/cpu-frequency", token, {"device_id": device, "samples": batch})
            expected = {r["sample_id"] for r in batch}
            ack = set(reply.get("accepted", []) + reply.get("duplicates", []))
            if ack != expected:
                raise RuntimeError("invalid_acknowledgement")
            rows = rows[len(batch):]
            save(path, rows)
        return expired


def main():
    try:
        path = Path(os.environ.get("HOMELAB_FREQUENCY_QUEUE", str(Path.home()/".local/state/homelab-portal/frequency.json")))
        expired = run(path, os.environ.get("HOMELAB_DEVICE_ID", ""), os.environ.get("HOMELAB_PORTAL_URL", ""),
                      os.environ.get("HOMELAB_HEARTBEAT_TOKEN", ""), sample())
        return 1 if expired else 0
    except Exception as exc:
        print("Frequency sampling failed: " + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
