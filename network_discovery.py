"""Private, bounded HTTP discovery and local Endpoint B mapping / 私有发现与本地映射。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
from ipaddress import IPv4Address, IPv4Network
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from network_archive import load_roles

PRIVATE_NETWORKS = tuple(IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class DiscoveryError(RuntimeError):
    def __init__(self, code, status=503):
        self.code, self.status = code, status


def roles_path():
    return os.getenv("NETWORK_HISTORY_ROLES_FILE") or os.getenv("NETWORK_ARCHIVE_ROLES_FILE", "")


def settings():
    scan = os.getenv("NETWORK_TPLINK_SCAN_FILE", "")
    state = os.getenv("NETWORK_ENDPOINT_B_STATE_FILE", "")
    if not scan or not state:
        raise DiscoveryError("discovery_not_configured")
    try:
        scan, state = Path(scan), Path(state)
        roles = load_roles(roles_path())
        if (not scan.is_absolute() or not state.is_absolute() or not roles
                or state.resolve() in (scan.resolve(), Path(roles_path()).resolve())
                or state.with_suffix(state.suffix + ".lock").resolve() in (scan.resolve(), Path(roles_path()).resolve())):
            raise ValueError()
        config = json.loads(scan.read_text())
        first, last = IPv4Address(config["start"]), IPv4Address(config["end"])
        if not any(first in n and last in n for n in PRIVATE_NETWORKS) or not 1 <= int(last)-int(first)+1 <= 254:
            raise ValueError()
        return [str(IPv4Address(n)) for n in range(int(first), int(last)+1)], state, roles
    except (OSError, ValueError, KeyError, TypeError):
        raise DiscoveryError("invalid_discovery_config") from None


def read_state(path):
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError()
        return value
    except FileNotFoundError:
        return {"version": 1, "discovery": None, "mapping": None, "previous_mappings": []}


@contextmanager
def state_lock(path):
    # Shared by scan/save and all WSGI workers / 跨进程排他，避免重复扫描或覆盖保存。
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DiscoveryError("discovery_busy", 409) from None
        yield


def write_state(path, value):
    fd, staging = tempfile.mkstemp(prefix=".endpoint-b-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def probe(address):
    """Same hp-linux curl fingerprint, 12 workers, .5/1.5s deadlines / 复用实测方式。"""
    try:
        result = subprocess.run(
            ["curl", "--disable", "--noproxy", "*", "-fsS", "--connect-timeout", "0.5",
             "--max-time", "1.5", "--max-filesize", "262144", "--proto", "=http", "http://" + address + "/"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, check=False)
    except subprocess.TimeoutExpired:
        return False
    # No redirect following, proxy, login, ICMP prerequisite or router mutation.
    # 不跟随跳转、不走代理、不登录、不要求能 ping 通、不修改路由器。
    return result.returncode == 0 and b"tl-wdr5620" in result.stdout.lower()


def discover():
    addresses, path, roles = settings()
    with state_lock(path):
        state = read_state(path)
        old = state.get("discovery")
        if old and time.time()-old["checked_at"] < 30:
            raise DiscoveryError("discovery_cooldown", 429)
        try:
            with ThreadPoolExecutor(max_workers=12) as pool:
                matches = [address for address, found in zip(addresses, pool.map(probe, addresses)) if found]
        except (OSError, subprocess.SubprocessError):
            raise DiscoveryError("discovery_failed") from None
        state["discovery"] = dict(id=uuid4().hex, system_id=roles["system_id"], matches=matches,
                                  checked_at=time.time(), status="unique" if len(matches) == 1 else "multiple" if matches else "none")
        write_state(path, state)
    return state


def eligible_monitors(client, system_id):
    monitors, after = [], None
    for _ in range(50):
        page = client.get_network_monitors_page(after, 200)
        if not isinstance(page, list) or len(page) > 200:
            raise DiscoveryError("beszel_unavailable")
        if not page:
            return monitors
        for record in page:
            from network_archive import _monitor
            monitor = _monitor(record)
            if after is not None and monitor[0] <= after:
                raise DiscoveryError("beszel_unavailable")
            after = monitor[0]
            if monitor[1] == system_id and monitor[3] == "icmp" and monitor[5]:
                monitors.append(dict(id=monitor[0], target=monitor[2], interval=monitor[4]))
    raise DiscoveryError("beszel_unavailable")


def status(state, roles, monitors):
    discovery = state.get("discovery")
    if discovery and discovery["system_id"] != roles["system_id"]:
        discovery = None
    result = dict(status="ok", discovery=discovery, monitors=monitors, mapping=state.get("mapping"),
                  probe_status="idle", can_save=False, selected_monitor_id=None)
    if not discovery or discovery["status"] != "unique":
        return result
    target = discovery["matches"][0]
    matches = [m for m in monitors if m["target"] == target]
    result["probe_status"] = "ready" if len(matches) == 1 else "ambiguous" if matches else "waiting_beszel"
    if time.time()-discovery["checked_at"] > 600:
        result["probe_status"] = "expired"
    if target in (v for k, v in roles["targets"].items() if k != "endpoint_b"):
        result["probe_status"] = "role_conflict"
    result["can_save"] = result["probe_status"] == "ready"
    if len(matches) == 1:
        result["selected_monitor_id"] = matches[0]["id"]
    return result


def save(discovery_id, monitor_id, client):
    _, path, roles = settings()
    with state_lock(path):
        state = read_state(path)
        result = status(state, roles, eligible_monitors(client, roles["system_id"]))
        if (not result["can_save"] or result["discovery"]["id"] != discovery_id
                or result["selected_monitor_id"] != monitor_id):
            raise DiscoveryError("mapping_not_ready", 409)
        mapping = dict(system_id=roles["system_id"], target=result["discovery"]["matches"][0],
                       monitor_id=monitor_id, saved_at=time.time())
        old = state.get("mapping")
        if not old or any(old[k] != mapping[k] for k in ("system_id", "target", "monitor_id")):
            if old:
                state.setdefault("previous_mappings", []).append(old)
            state["mapping"] = mapping
            write_state(path, state)
    return status(state, roles, result["monitors"])


def saved_mapping(roles):
    path = os.getenv("NETWORK_ENDPOINT_B_STATE_FILE", "")
    mapping = read_state(path).get("mapping") if path else None
    if mapping and (not roles or mapping["system_id"] != roles["system_id"]):
        raise ValueError("mapping_system_changed")
    return mapping
