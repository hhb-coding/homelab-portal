#!/usr/bin/env python3
"""Private PR30 deployment checks. No SQLite writes, migrations or upstream edits."""
import hashlib
import ipaddress
import re
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

B = Path(__file__).resolve().parent
P = Path('/home/daniel/homelab-portal')
C = Path('/home/daniel/.config/homelab-portal')
BASE = '10875361198982d2135bc168ca686e929460addf'
TARGET = os.environ['PORTAL_DEPLOY_TARGET']
DROP = Path('/home/daniel/.config/systemd/user/homelab-portal.service.d/90-endpoint-b-discovery.conf')
STATE = C / 'endpoint-b/state.json'
UNITS = ['homelab-portal.service', 'homelab-metrics-archive.service',
         'homelab-metrics-archive.timer', 'homelab-cpu-frequency.timer',
         'homelab-heartbeat.timer']
PROPS = ['ActiveState', 'SubState', 'Result', 'ExecMainStatus', 'MainPID',
         'NRestarts', 'InvocationID', 'LastTriggerUSecMonotonic',
         'ExecMainStartTimestampMonotonic', 'NextElapseUSecRealtime',
         'WorkingDirectory', 'ExecStart', 'Environment', 'EnvironmentFiles']


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.PIPE).strip()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_file(path):
    from dotenv import dotenv_values
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def monotonic_usec(value):
    """systemctl prints either raw microseconds or a human duration."""
    if value.isdigit():
        return int(value)
    units = {'d':86400, 'h':3600, 'min':60, 's':1, 'ms':Decimal('.001'),
             'us':Decimal('.000001'), 'µs':Decimal('.000001'), 'μs':Decimal('.000001')}
    tokens = re.findall(r'(\d+(?:\.\d+)?)(d|h|min|ms|us|µs|μs|s)', value)
    if not tokens or re.sub(r'(\d+(?:\.\d+)?)(d|h|min|ms|us|µs|μs|s)', '', value).strip():
        raise ValueError('Invalid systemd monotonic duration: ' + repr(value))
    return int(sum((Decimal(n)*units[u] for n,u in tokens), Decimal(0))*1000000)


def unit(name):
    args = ['systemctl', '--user', 'show', name]
    for prop in PROPS:
        args += ['-p', prop]
    return dict(line.split('=', 1) for line in run(*args).splitlines() if '=' in line)


def unit_env(name):
    return dict(v.split('=', 1) for v in shlex.split(unit(name)['Environment']) if '=' in v)


def portal_env():
    # Reproduce config.py's load_dotenv(override=False) using the live Web
    # process's initial environment. Do not import app.py (it initializes SQLite).
    service = unit('homelab-portal.service')
    check(service['ActiveState'] == 'active' and int(service['MainPID']) > 0,
          'Cannot read effective Portal configuration: Web is not active')
    initial = dict(part.split('=', 1) for part in
                   Path('/proc', service['MainPID'], 'environ').read_bytes().decode().split('\0')
                   if '=' in part)
    code = ('import config,json; keys=' + repr([
        'LOCAL_DEVICE_ID', 'DATABASE_PATH', 'PORT', 'BESZEL_URL', 'BESZEL_TOKEN',
        'BESZEL_EMAIL', 'BESZEL_PASSWORD', 'BESZEL_TIMEOUT'])
        + '; print(json.dumps({k:str(getattr(config,k)) for k in keys}))')
    result = json.loads(subprocess.check_output(
        [str(P / '.venv/bin/python'), '-B', '-c', code], cwd=P,
        env=initial, text=True, stderr=subprocess.PIPE))
    check(unit('homelab-portal.service')['InvocationID'] == service['InvocationID'],
          'Portal restarted while reading effective configuration; retry preflight')
    return result


def settings():
    # .env is parsed, never sourced by a shell and never printed.
    env = portal_env()
    archive = env_file(C / 'archive.env')
    web = unit_env('homelab-portal.service')
    collector = unit('homelab-metrics-archive.service')
    check(str(C / 'archive.env') in collector['EnvironmentFiles'], 'Collector does not load prepared archive.env')
    database = Path(web.get('METRICS_ARCHIVE_PATH', archive.get('METRICS_ARCHIVE_PATH', '')))
    roles = Path(web.get('NETWORK_HISTORY_ROLES_FILE') or archive.get('NETWORK_ARCHIVE_ROLES_FILE', ''))
    check(roles == C / 'network-archive-roles.json', 'Web roles path differs from prepared configuration')
    check(archive.get('NETWORK_ARCHIVE_ROLES_FILE') == str(roles), 'Collector and Web roles differ')
    check(archive.get('METRICS_ARCHIVE_PATH') == str(database), 'Collector and Web archive differ')
    for key in ['METRICS_ARCHIVE_MOUNT', 'METRICS_ARCHIVE_UUID']:
        check(archive.get(key) == web.get(key), 'Web/collector HDD guard mismatch')
    effective = {**archive, **unit_env('homelab-metrics-archive.service')}
    # EnvironmentFile has priority over Environment in systemd.
    effective.update(archive)
    check(effective.get('METRICS_ARCHIVE_PYTHON') == str(P / '.venv/bin/python')
          and effective.get('METRICS_ARCHIVE_SCRIPT') == str(P / 'tools/archive_metrics.py'), 'Collector uses another checkout')
    from metrics_archive import require_hdd
    require_hdd(database, Path(archive['METRICS_ARCHIVE_MOUNT']), archive['METRICS_ARCHIVE_UUID'])
    return env, archive, web, database, roles


def connection(database):
    conn = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    conn.execute('PRAGMA query_only=ON')
    return conn


def api(path):
    import requests
    env = portal_env()
    base = 'http://127.0.0.1:' + env.get('PORT', '8088')
    with requests.Session() as client:
        client.trust_env = False
        response = client.get(base + path, timeout=45)
        check(response.status_code == 200, 'Portal GET failed: ' + path.split('?')[0])
        return response.json()


def hp_check(roles):
    from beszel_client import BeszelClient
    env = portal_env()
    client = BeszelClient(env['BESZEL_URL'], timeout=int(env.get('BESZEL_TIMEOUT', 10)))
    try:
        if env.get('BESZEL_TOKEN'):
            client.authenticate_with_token(env['BESZEL_TOKEN'])
        else:
            client.authenticate_with_password(env['BESZEL_EMAIL'], env['BESZEL_PASSWORD'])
        systems = [x for x in client.get_systems() if x['id'] == roles['system_id']]
        check(len(systems) == 1, 'Roles system_id is absent or ambiguous in live Beszel')
        check(systems[0]['name'] == 'HP-Homelab', 'Roles system_id points to another Beszel system')
        check(systems[0]['status'] == 'up', 'Configured Beszel HP system is not online')
        devices = api('/api/dashboard')
        check(devices['status'] == 'ok' and devices['sources']['metrics_status'] == 'ok', 'Live Beszel dashboard unavailable')
        hp = [x for x in devices['devices'] if x['device_id'] == env['LOCAL_DEVICE_ID']]
        check(bool(env['LOCAL_DEVICE_ID']) and len(hp) == 1,
              'Effective LOCAL_DEVICE_ID does not select exactly one live registry device')
        # device_id is the configured stable registry key; hp-linux is a hostname.
        check(hp[0]['hostname'] == 'hp-linux',
              'Effective LOCAL_DEVICE_ID selects a registry device with another hostname')
        check(hp[0]['beszel_system_id'] == roles['system_id'],
              'Selected registry device beszel_system_id differs from roles system_id')
        return systems[0], hp[0], client
    except BaseException:
        client.session.close()
        raise


def identity(destination):
    env = portal_env()
    roles_path = Path(unit_env('homelab-portal.service').get('NETWORK_HISTORY_ROLES_FILE')
                      or unit_env('homelab-portal.service').get('NETWORK_ARCHIVE_ROLES_FILE', ''))
    check(roles_path == C / 'network-archive-roles.json', 'Unexpected effective Web roles path')
    check(env_file(C / 'archive.env').get('NETWORK_ARCHIVE_ROLES_FILE') == str(roles_path),
          'Collector and Web roles differ')
    roles = load(roles_path)
    system, hp, client = hp_check(roles)
    client.session.close()
    with connection(Path(env['DATABASE_PATH'])) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            'SELECT device_id,hostname,beszel_system_id FROM devices WHERE device_id=?',
            (env['LOCAL_DEVICE_ID'],))]
    check(len(rows) == 1 and all(rows[0][key] == hp.get(key) for key in rows[0]),
          'Read-only device registry differs from live Dashboard identity')
    dump(destination / 'identity.private.json', dict(
        checked_at=datetime.now(timezone.utc).isoformat(),
        local_device_id=env['LOCAL_DEVICE_ID'], database=env['DATABASE_PATH'],
        registry=rows[0], dashboard={k: hp[k] for k in rows[0]},
        roles_path=str(roles_path), roles_system_id=roles['system_id'],
        beszel_system_id=system['id'], beszel_name=system['name'], beszel_status=system['status'],
        old_device_id_literal_check=hp['device_id'] == 'hp-linux',
        hostname_check=hp['hostname'] == 'hp-linux', stable_identity_check=True))
    print('生效 LOCAL_DEVICE_ID、只读注册表、HP 主机名、角色与在线 Beszel 身份：通过', flush=True)


def offline():
    manifest = load(B / 'manifest.private.json')
    check(manifest['production_commit'] == BASE and manifest['target_commit'] == TARGET, 'Manifest version mismatch')
    for name, expected in load(B / 'checksums.private.json').items():
        check(digest(B / name) == expected, 'Rollback package checksum mismatch: ' + name)
    check(run('git', 'rev-parse', 'HEAD', cwd=P) == BASE, 'Production HEAD changed; prepare a new baseline')
    check(not run('git', 'diff', '--cached', '--name-only', cwd=P), 'Staged production changes detected')
    names = run('git', 'diff', '--name-only', cwd=P).splitlines()
    check(sorted(names) == sorted(manifest['modified_files']), 'Tracked changes differ from package')
    for name in manifest['modified_files']:
        check((P / name).read_bytes() == (B / 'original' / name).read_bytes(), 'Local patch changed: ' + name)
    untracked = run('git', 'ls-files', '--others', '--exclude-standard', cwd=P).splitlines()
    check(sorted(untracked) == sorted(manifest['untracked_files']), 'Untracked files changed')
    for name in untracked:
        check((P / name).read_bytes() == (B / 'untracked' / name).read_bytes(), 'Untracked backup mismatch')
    for name in ['.env', 'archive.env', 'network-archive-roles.json', 'network-tplink-scan.json']:
        live = P / name if name == '.env' else C / name
        check(live.is_file() and not live.is_symlink() and live.stat().st_uid == os.getuid()
              and stat.S_IMODE(live.stat().st_mode) == 0o600, 'Unsafe private config: ' + name)
        check(live.read_bytes() == (B / 'private-config' / name).read_bytes(), 'Private config changed: ' + name)
    parent = STATE.parent
    check(parent.is_dir() and not parent.is_symlink() and parent.stat().st_uid == os.getuid()
          and stat.S_IMODE(parent.stat().st_mode) == 0o700 and os.access(parent, os.W_OK), 'Unsafe state parent')
    check(not STATE.is_symlink(), 'State path must not be a symlink')
    if STATE.exists():
        check(digest(STATE) == manifest['state_sha256'], 'Saved private state changed after preparation')
    check(not DROP.exists() and not DROP.is_symlink(), 'Discovery drop-in already exists')
    scan = load(C / 'network-tplink-scan.json')
    first, last = (ipaddress.IPv4Address(scan[k]) for k in ('start', 'end'))
    check(int(last) - int(first) + 1 == 253, 'Prepared scan range mismatch')
    prepared = (B / '90-endpoint-b-discovery.conf.prepared').read_text()
    check(prepared == '[Service]\nEnvironment="NETWORK_TPLINK_SCAN_FILE=' + str(C / 'network-tplink-scan.json')
          + '"\nEnvironment="NETWORK_ENDPOINT_B_STATE_FILE=' + str(STATE) + '"\n', 'Prepared drop-in mismatch')
    archive = env_file(C / 'archive.env')
    check(all(archive.get(k, '').lower() == 'true' for k in ['NETWORK_ARCHIVE_ENABLED', 'FREQUENCY_ARCHIVE_ENABLED']), 'Archive features disabled')
    check(archive['METRICS_ARCHIVE_SCRIPT'] == str(P / 'tools/archive_metrics.py'), 'Wrong collector checkout')
    check(archive['METRICS_ARCHIVE_PYTHON'] == str(P / '.venv/bin/python'), 'Wrong collector Python')
    print('回退包、本机改动、253 地址扫描配置、0600/0700 权限和私有路径：通过', flush=True)


def timer_health(before=None):
    result = {name: unit(name) for name in UNITS}
    check(result['homelab-portal.service']['ActiveState'] == 'active', 'Portal Web inactive')
    for name in UNITS:
        if name.endswith('.timer'):
            check(result[name]['ActiveState'] == 'active', 'Timer inactive: ' + name)
            check(run('systemctl', '--user', 'is-enabled', name) == 'enabled', 'Timer not enabled: ' + name)
            if before:
                check(result[name]['InvocationID'] == before[name]['InvocationID'], 'Timer restarted: ' + name)
    return result


def cpu_history(start, end, device):
    from urllib.parse import urlencode
    query = urlencode(dict(device_id=device, start=start, end=end, extended='1'))
    data = api('/api/history/v2/performance?' + query)
    check(data.get('status') == 'ok', 'CPU performance history unavailable')
    series = {s['metric']: s for s in data['series']}
    check('cpu_frequency_ghz' in series, 'CPU frequency series missing')
    frequency = series['cpu_frequency_ghz']
    check(frequency['stats']['count'] > 0, 'CPU history has no samples')
    stats = frequency['stats']
    check(stats['min'] <= stats['average'] <= stats['max'], 'CPU aggregate min/avg/max invalid')
    for point in frequency['points']:
        if point['count']:
            check(point['min'] <= point['value'] <= point['max'] and point['avg'] == point['value'], 'CPU bucket bounds invalid')
    raw = api('/api/history/v2?' + urlencode(dict(device_id=device, start=start, end=end, limit=2000)))
    check(raw['metric'] == 'cpu_frequency_ghz' and raw['points'], 'Raw CPU history unavailable')
    return data, raw


def snapshot(destination):
    env, archive, web, database, roles_path = settings()
    roles = load(roles_path)
    system, hp, client = hp_check(roles)
    client.session.close()
    check(web.get('FREQUENCY_HISTORY_ENABLED', '').lower() == 'true', 'Web history disabled')
    check(not web.get('NETWORK_TPLINK_SCAN_FILE') and not web.get('NETWORK_ENDPOINT_B_STATE_FILE'), 'Discovery already configured')
    units = timer_health()
    check(units['homelab-portal.service']['WorkingDirectory'] == str(P), 'Web uses different checkout')
    check(str(P / 'app.py') in units['homelab-portal.service']['ExecStart'], 'Wrong Web ExecStart')
    check('homelab-portal/tools/archive_metrics.py' not in units['homelab-metrics-archive.service']['ExecStart']
          or str(P / 'tools/archive_metrics.py') in units['homelab-metrics-archive.service']['ExecStart'], 'Wrong archive ExecStart')
    health = api('/api/health')
    check(health['status'] == 'ok' and health['database'] == 'ok', 'Web baseline unhealthy')
    now = datetime.now(timezone.utc)
    # Fixed window means before/after CPU responses must be identical.
    end = (now - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    start = (now - timedelta(hours=25)).isoformat().replace('+00:00', 'Z')
    performance, raw = cpu_history(start, end, env['LOCAL_DEVICE_ID'])
    history = api('/api/history/v3/network?range=1h')
    check(history['status'] == 'ok' and history['schema_version'] == 3, 'Network history baseline unavailable')
    with connection(database) as conn:
        check(conn.execute('PRAGMA user_version').fetchone()[0] == 3, 'Archive schema is not v3')
        monitors = conn.execute('SELECT monitor_id,system_id,target,protocol FROM network_monitors ORDER BY monitor_id').fetchall()
        # Keep immutable representative rows for EVERY archive identity, plus all daily counters.
        samples = []
        for identity, *_ in monitors:
            samples += conn.execute("SELECT * FROM network_samples WHERE monitor_id=? AND created_ms>? ORDER BY created_ms DESC LIMIT 100",
                                    (identity, int((now - timedelta(days=89)).timestamp() * 1000))).fetchall()
        frequency = []
        for device, in conn.execute('SELECT DISTINCT device_id FROM cpu_frequency_samples'):
            frequency += conn.execute('SELECT * FROM cpu_frequency_samples WHERE device_id=? AND sampled_utc>? ORDER BY sampled_utc DESC LIMIT 100',
                                      (device, (now - timedelta(days=179)).isoformat().replace('+00:00', 'Z'))).fetchall()
        daily = conn.execute('SELECT * FROM network_daily').fetchall()
        events = conn.execute('SELECT event_id,stream_key,kind,monitor_id,started_ms,detected_ms FROM network_events').fetchall()
        latest_frequency = conn.execute('SELECT max(sampled_utc) FROM cpu_frequency_samples WHERE device_id=?', (env['LOCAL_DEVICE_ID'],)).fetchone()[0]
        latest_metrics = conn.execute('SELECT max(created_utc) FROM samples WHERE system_id=?', (roles['system_id'],)).fetchone()[0]
        checkpoints = conn.execute('SELECT * FROM network_checkpoints').fetchall()
    check(latest_frequency and latest_metrics and samples, 'Baseline archive lacks live history')
    dump(destination / 'baseline.private.json', dict(created_at=time.time(), units=units, health=health,
         system=system, hp=hp, database=str(database), roles=roles, monitors=monitors,
         samples=samples, frequency=frequency, daily=daily, events=events, checkpoints=checkpoints,
         latest_frequency=latest_frequency, latest_metrics=latest_metrics,
         cpu_start=start, cpu_end=end, performance=performance, raw=raw, network=history))
    dump(destination / 'runtime.private.json', dict(base_url='http://127.0.0.1:' + env.get('PORT', '8088'),
         system_id=roles['system_id'], device_id=env['LOCAL_DEVICE_ID']))
    print('在线 Portal/Beszel HP 身份、CPU 历史、v3 归档与三个 timer 基线：通过', flush=True)


def preserved(conn, baseline):
    for row in baseline['monitors']:
        check(conn.execute('SELECT monitor_id,system_id,target,protocol FROM network_monitors WHERE monitor_id=?', (row[0],)).fetchone() == tuple(row), 'Old monitor identity changed')
    for row in baseline['samples']:
        current = conn.execute('SELECT * FROM network_samples WHERE monitor_id=? AND type=? AND record_id=?', tuple(row[:3])).fetchone()
        check(current == tuple(row), 'Old network sample changed/disappeared')
    for row in baseline['frequency']:
        current = conn.execute('SELECT * FROM cpu_frequency_samples WHERE device_id=? AND sample_id=?', tuple(row[:2])).fetchone()
        check(current == tuple(row), 'Old CPU sample changed/disappeared')
    for row in baseline['daily']:
        current = conn.execute('SELECT * FROM network_daily WHERE monitor_id=? AND type=? AND day_ms=?', tuple(row[:3])).fetchone()
        check(current is not None and all(current[i] >= row[i] for i in [3, 4, 5, 6])
              and current[9] <= row[9] and current[10] >= row[10], 'Old daily archive regressed')
    for row in baseline['checkpoints']:
        current = conn.execute('SELECT * FROM network_checkpoints WHERE monitor_id=? AND type=?', tuple(row[:2])).fetchone()
        check(current is not None and tuple(current[2:]) >= tuple(row[2:]), 'Old checkpoint regressed')
    for row in baseline['events']:
        check(conn.execute('SELECT event_id,stream_key,kind,monitor_id,started_ms,detected_ms FROM network_events WHERE event_id=?', (row[0],)).fetchone() == tuple(row), 'Old event identity changed')


def common_health(destination, final=False):
    baseline = load(destination / 'baseline.private.json')
    env, archive, web, database, roles_path = settings()
    check(load(roles_path) == baseline['roles'], 'Private roles were modified')
    for name in ['.env', 'archive.env', 'network-archive-roles.json', 'network-tplink-scan.json']:
        live = P / name if name == '.env' else C / name
        check(live.read_bytes() == (B / 'private-config' / name).read_bytes(), 'Private config drift: ' + name)
    health = api('/api/health')
    check(health['status'] == 'ok' and health['database'] == 'ok', 'Portal Web unhealthy')
    system, hp, client = hp_check(baseline['roles'])
    client.session.close()
    units = timer_health(baseline['units'])
    performance, raw = cpu_history(baseline['cpu_start'], baseline['cpu_end'], env['LOCAL_DEVICE_ID'])
    check(performance == baseline['performance'] and raw == baseline['raw'], 'Fixed CPU history differs from baseline')
    with connection(database) as conn:
        check(conn.execute('PRAGMA user_version').fetchone()[0] == 3, 'Archive schema changed')
        preserved(conn, baseline)
        if final:
            check(conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'Archive SQLite integrity failed')
    return baseline, database, units


def health(destination, mode):
    deadline = time.monotonic() + 60
    while True:
        try:
            baseline, database, units = common_health(destination)
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(3)
    if mode == 'rollback':
        history = api('/api/history/v3/network?range=1h')
        check(history['status'] == 'ok', 'Rollback network history unavailable')
        check(not unit_env('homelab-portal.service').get('NETWORK_TPLINK_SCAN_FILE')
              and not unit_env('homelab-portal.service').get('NETWORK_ENDPOINT_B_STATE_FILE'), 'Rollback discovery settings still enabled')
        previous_trigger = monotonic_usec((destination / 'rollback-timer-trigger.private.txt').read_text().strip())
        deadline = time.monotonic() + 1200
        print('回退 Web 已恢复；等待既有归档 timer 自然完成一轮以复核兼容采集器。', flush=True)
        while True:
            timer = unit('homelab-metrics-archive.timer')
            service = unit('homelab-metrics-archive.service')
            if monotonic_usec(timer['LastTriggerUSecMonotonic']) > previous_trigger and service['ActiveState'] == 'inactive':
                check(service['Result'] == 'success' and service['ExecMainStatus'] == '0', 'Rollback natural archive pass failed')
                break
            check(time.monotonic() < deadline, 'Rollback natural archive pass timed out')
            time.sleep(15)
        common_health(destination, final=True)
    elif mode == 'deployed':
        web = unit_env('homelab-portal.service')
        check(web.get('NETWORK_TPLINK_SCAN_FILE') == str(C / 'network-tplink-scan.json')
              and web.get('NETWORK_ENDPOINT_B_STATE_FILE') == str(STATE), 'Prepared discovery settings not loaded')
        # Validate the effective configuration with the production module; no scan here.
        os.environ.update(web)
        from network_discovery import settings as discovery_settings
        addresses, state, roles = discovery_settings()
        check(len(addresses) == 253 and state == STATE, 'Effective discovery configuration mismatch')
        check(monotonic_usec(units['homelab-portal.service']['ExecMainStartTimestampMonotonic'])
              > monotonic_usec(baseline['units']['homelab-portal.service']['ExecMainStartTimestampMonotonic']), 'Portal Web was not restarted')
        dump(destination / 'web-running.private.json', units['homelab-portal.service'])
    print('Web、CPU 旧历史、旧归档、角色配置和 timer 健康复核：通过 (' + mode + ')', flush=True)


def final(destination):
    baseline, database, units = common_health(destination, final=True)
    running = load(destination / 'web-running.private.json')
    check(units['homelab-portal.service']['InvocationID'] == running['InvocationID']
          and units['homelab-portal.service']['NRestarts'] == running['NRestarts'], 'Portal restarted/crashed during acceptance')
    live = load(destination / 'live-browser.private.json')
    check(live['accepted'] is True, 'Browser acceptance incomplete')
    mapping = load(STATE)['mapping']
    check(mapping['target'] == live['target'] and mapping['monitor_id'] == live['monitor_id']
          and mapping['system_id'] == baseline['roles']['system_id'], 'Saved mapping differs from browser evidence')
    system, hp, client = hp_check(baseline['roles'])
    try:
        from network_discovery import eligible_monitors
        matches = [m for m in eligible_monitors(client, mapping['system_id']) if m['target'] == mapping['target']]
        check(len(matches) == 1 and matches[0]['id'] == mapping['monitor_id'], 'Beszel HP ICMP changed after saving')
    finally:
        client.session.close()
    history = api('/api/history/v3/network?range=1h')
    endpoint = next(t for t in history['targets'] if t['role'] == 'endpoint_b')
    check(endpoint['target'] == mapping['target'] and endpoint.get('mapping_status') == 'active'
          and endpoint['latest_sample']['time'] > live['saved_at_ms'], 'No new Endpoint B sample after save')
    check(endpoint['latest_sample'] in endpoint['rows'] and endpoint['latest_sample']['count'] > 0,
          'Card and curve do not contain the same observed sample')
    check(any(p['time'] > live['saved_at_ms'] and p['success_count'] > 0 for p in endpoint['rows']),
          'New archive received, but no successful probe after saving')
    check(time.time() * 1000 - endpoint['latest_sample']['time'] < 12 * 60 * 1000, 'Endpoint B sample is stale')
    with connection(database) as conn:
        meta = conn.execute('SELECT system_id,target,protocol,enabled,config_json FROM network_monitors WHERE monitor_id=?', (endpoint['monitor_id'],)).fetchone()
        check(meta is not None and meta[:4] == (mapping['system_id'], mapping['target'], 'icmp', 1), 'Archive binding mismatch')
        check(json.loads(meta[4])['id'] == mapping['monitor_id'], 'Archive source monitor mismatch')
        frequency = conn.execute('SELECT max(sampled_utc) FROM cpu_frequency_samples WHERE device_id=?', (hp['device_id'],)).fetchone()[0]
        metrics = conn.execute('SELECT max(created_utc) FROM samples WHERE system_id=?', (mapping['system_id'],)).fetchone()[0]
        check(frequency > baseline['latest_frequency'] and metrics > baseline['latest_metrics'], 'CPU or performance archive did not advance')
        for value in [frequency, metrics]:
            check(time.time() - datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() < 720, 'CPU/performance archive stale')
    timer = units['homelab-metrics-archive.timer']
    service = units['homelab-metrics-archive.service']
    check(monotonic_usec(timer['LastTriggerUSecMonotonic']) > monotonic_usec(baseline['units']['homelab-metrics-archive.timer']['LastTriggerUSecMonotonic']), 'Archive timer did not naturally fire')
    check(service['ActiveState'] == 'inactive' and service['Result'] == 'success' and service['ExecMainStatus'] == '0', 'Latest archive run not completed successfully')
    journal = run('journalctl', '--user', '-u', 'homelab-metrics-archive.service', '--since',
                  '@' + str(int(baseline['created_at'])), '--no-pager', '-o', 'cat')
    reports = []
    for line in journal.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and 'network_inserted' in value:
                reports.append(value)
        except ValueError:
            pass
    check(reports and all(v == 0 for k, v in reports[-1].items() if k.endswith('failed')), 'Archive journal contains failures/no completed report')
    latest_end = datetime.now(timezone.utc)
    cpu_history((latest_end - timedelta(hours=1)).isoformat().replace('+00:00', 'Z'),
                latest_end.isoformat().replace('+00:00', 'Z'), hp['device_id'])
    dump(destination / 'acceptance.private.json', dict(accepted=True, production=TARGET,
         local_patch=digest(B / 'production-on-pr30.patch'), endpoint=endpoint, mapping=mapping,
         cpu_latest=frequency, metrics_latest=metrics, archive_report=reports[-1], units=units))
    print('真实发现/HP ICMP/保存映射/卡片与曲线新样本/CPU 新旧历史/自然归档/Web：全部通过', flush=True)


if __name__ == '__main__':
    sys.path.insert(0, str(P))
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        action = sys.argv[1]
        if action == 'offline':
            offline()
        elif action == 'identity':
            identity(Path(sys.argv[2]))
        elif action == 'snapshot':
            snapshot(Path(sys.argv[2]))
        elif action == 'health':
            health(Path(sys.argv[2]), sys.argv[3])
        elif action == 'final':
            final(Path(sys.argv[2]))
        else:
            raise RuntimeError('Unknown action')
    except Exception as exc:
        # Credentials, response bodies and environment values must stay private.
        import traceback
        traceback.print_exc()
        print('检查失败：' + (str(exc) if type(exc) is RuntimeError else type(exc).__name__), file=sys.stderr, flush=True)
        sys.exit(1)
