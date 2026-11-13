"""Synthetic HTTP discovery + private mapping only / 模拟 HTTP、临时配置与映射。"""
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import network_discovery as discovery
from network_history import ROLES


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.scan, self.state, self.roles_path = (self.root / n for n in ('scan.json', 'state.json', 'roles.json'))
        # Synthetic RFC1918 range, unrelated to a deployed LAN / 合成私网范围。
        self.scan.write_text(json.dumps(dict(start='10.254.253.2', end='10.254.253.25')))
        self.roles = dict(system_id='synthetic-hp', targets={r:'192.0.2.'+str(i+1) for i,r in enumerate(ROLES)})
        self.roles_path.write_text(json.dumps(self.roles))
        env = patch.dict(os.environ, dict(NETWORK_TPLINK_SCAN_FILE=str(self.scan), NETWORK_ENDPOINT_B_STATE_FILE=str(self.state),
                                         NETWORK_HISTORY_ROLES_FILE=str(self.roles_path)), clear=False)
        env.start(); self.addCleanup(env.stop)
        self.net = patch('requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.target = '10.254.253.9'
        self.probe = patch('network_discovery.probe', side_effect=lambda ip: ip == self.target)
        self.probe.start(); self.addCleanup(self.probe.stop)
        self.api = Mock()
        self.records = []
        self.api.get_network_monitors_page.side_effect = lambda after, size: sorted(
            [r for r in self.records if after is None or r['id'] > after], key=lambda r:r['id'])[:size]

    def record(self, **changes):
        return dict(dict(id='hp-icmp', system=self.roles['system_id'], target=self.target, protocol='icmp', interval=10, enabled=True), **changes)

    def ready(self):
        state = discovery.discover()
        self.records = [self.record()]
        return state

    def test_none_unique_multiple_and_server_only_range(self):
        original_roles = self.roles_path.read_bytes()
        for matches, expected in (([], 'none'), ([self.target], 'unique'), ([self.target, '10.254.253.10'], 'multiple')):
            if self.state.exists(): self.state.unlink()
            with patch('network_discovery.probe', side_effect=lambda ip: ip in matches) as probe:
                state = discovery.discover()
                self.assertEqual(state['discovery']['status'], expected)
                self.assertEqual(state['discovery']['matches'], matches)
                self.assertEqual(probe.call_count, 24)
                self.assertFalse(discovery.status(state, self.roles, [])['can_save'])
        self.assertEqual(self.roles_path.read_bytes(), original_roles)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_private_range_validation_and_missing_configuration(self):
        for start, end in [('127.0.0.1','127.0.0.2'), ('169.254.1.1','169.254.1.2'), ('203.0.113.1','203.0.113.2'),
                           ('::1','::2'), ('10.0.0.1','10.0.2.1'), ('10.0.0.3','10.0.0.1'), ('host.invalid','host.invalid')]:
            self.scan.write_text(json.dumps(dict(start=start,end=end)))
            with self.assertRaises(discovery.DiscoveryError): discovery.settings()
        with patch.dict(os.environ, {'NETWORK_TPLINK_SCAN_FILE':''}):
            with self.assertRaisesRegex(discovery.DiscoveryError, '') as caught: discovery.settings()
            self.assertEqual(caught.exception.code, 'discovery_not_configured')

    def test_parallel_scan_single_flight_and_cooldown(self):
        entered, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        running, peak = 0, 0
        def probe(ip):
            nonlocal running, peak
            with lock:
                running += 1; peak = max(peak, running)
                if running == 12: entered.set()
            self.assertTrue(release.wait(5))
            with lock: running -= 1
            return ip == self.target
        with patch('network_discovery.probe', side_effect=probe), ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(discovery.discover)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(discovery.DiscoveryError) as caught: discovery.discover()
                self.assertEqual(caught.exception.code, 'discovery_busy')
            finally: release.set()
            task.result()
        self.assertEqual(peak, 12)
        with self.assertRaises(discovery.DiscoveryError) as caught: discovery.discover()
        self.assertEqual(caught.exception.code, 'discovery_cooldown')

    def test_waiting_preselection_only_enabled_hp_icmp_and_ambiguity(self):
        state = discovery.discover()
        self.records = [self.record(id='other-system',system='other'), self.record(id='tcp',protocol='tcp'),
                        self.record(id='disabled',enabled=False)]
        self.assertEqual(discovery.eligible_monitors(self.api, self.roles['system_id']), [])
        self.assertEqual(discovery.status(state, self.roles, [])['probe_status'], 'waiting_beszel')
        self.records.append(self.record())
        monitors = discovery.eligible_monitors(self.api, self.roles['system_id'])
        result = discovery.status(state, self.roles, monitors)
        self.assertTrue(result['can_save']); self.assertEqual(result['selected_monitor_id'],'hp-icmp')
        result = discovery.status(state, self.roles, monitors+[dict(monitors[0],id='second')])
        self.assertEqual(result['probe_status'], 'ambiguous'); self.assertFalse(result['can_save'])

    def test_save_revalidates_nonce_target_system_protocol_enabled_and_expiry(self):
        state = self.ready()
        for changes in (dict(target='192.0.2.99'), dict(system='other'), dict(protocol='tcp'), dict(enabled=False)):
            self.records = [self.record(**changes)]
            with self.assertRaises(discovery.DiscoveryError): discovery.save(state['discovery']['id'], 'hp-icmp', self.api)
        self.records = [self.record()]
        with self.assertRaises(discovery.DiscoveryError): discovery.save('stale-discovery','hp-icmp',self.api)
        with patch('network_discovery.time.time', return_value=state['discovery']['checked_at']+601):
            with self.assertRaises(discovery.DiscoveryError): discovery.save(state['discovery']['id'],'hp-icmp',self.api)
        self.roles['targets']['endpoint_a'] = self.target
        self.roles_path.write_text(json.dumps(self.roles))
        with self.assertRaises(discovery.DiscoveryError): discovery.save(state['discovery']['id'],'hp-icmp',self.api)
        self.assertIsNone(discovery.read_state(self.state)['mapping'])

    def test_atomic_idempotent_save_preserves_roles_and_previous_mapping(self):
        state = self.ready(); original = self.roles_path.read_bytes()
        first = discovery.save(state['discovery']['id'],'hp-icmp',self.api)['mapping']
        discovery.save(state['discovery']['id'],'hp-icmp',self.api)
        self.assertEqual(discovery.read_state(self.state)['previous_mappings'], [])
        self.assertEqual(discovery.saved_mapping(self.roles), first)
        changed = discovery.read_state(self.state)
        changed['discovery']['matches'] = ['10.254.253.10']
        discovery.write_state(self.state,changed)
        self.records = [self.record(id='new-icmp',target='10.254.253.10')]
        with patch('network_discovery.os.replace',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): discovery.save(changed['discovery']['id'],'new-icmp',self.api)
        self.assertEqual(discovery.saved_mapping(self.roles), first)
        discovery.save(changed['discovery']['id'],'new-icmp',self.api)
        self.assertEqual(discovery.read_state(self.state)['previous_mappings'], [first])
        self.assertEqual(self.roles_path.read_bytes(),original)
        self.assertEqual(list(self.root.glob('.endpoint-b-*')),[])

    def test_http_api_rejects_cross_origin_and_client_scan_ranges(self):
        # app/db cache configuration at import; isolate from other suites' DBs.
        # app/db 导入会缓存配置，独立进程避免污染其他测试的临时库。
        if os.getenv('NETWORK_DISCOVERY_API_SUBPROCESS') != '1':
            result = subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests',
                '-p','test_network_discovery.py','-k','http_api'],
                env={**os.environ,'NETWORK_DISCOVERY_API_SUBPROCESS':'1'},
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout)
            return
        with patch('dotenv.load_dotenv'):
            config = importlib.import_module('config')
        with patch.object(config,'DATABASE_PATH',self.root/'portal.sqlite3'):
            app = importlib.import_module('app')
            app.app.config['TESTING'] = True
            client = app.app.test_client()
            headers = {'X-Portal-Request':'1'}
            self.assertEqual(client.post('/api/network/endpoint-b/discover',json={}).status_code,403)
            self.assertEqual(client.post('/api/network/endpoint-b/discover',json={},headers={**headers,'Origin':'https://other.invalid'}).status_code,403)
            self.assertEqual(client.post('/api/network/endpoint-b/discover',json={'start':'host.invalid'},headers=headers).status_code,400)
            # Reverse proxy terminates HTTPS while Flask sees HTTP / 支持 HTTPS 反向代理。
            response = client.post('/api/network/endpoint-b/discover',json={},headers={**headers,'Origin':'https://localhost'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['probe_status'],'beszel_unavailable')
            self.assertIn(self.target,response.get_data(as_text=True))
            self.assertNotIn(str(self.scan),response.get_data(as_text=True))
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            with patch('app.network_beszel_client',return_value=self.api):
                self.records = [self.record()]
                result = client.get('/api/network/endpoint-b').json
                self.assertTrue(result['can_save'])
                saved = client.post('/api/network/endpoint-b',json=dict(discovery_id=result['discovery']['id'],monitor_id='hp-icmp'),headers=headers)
                self.assertEqual(saved.status_code,200)
                self.assertEqual(saved.json['mapping']['target'],self.target)


class HTTPFingerprintTests(unittest.TestCase):
    def test_case_insensitive_http_fingerprint_and_bounded_curl(self):
        with patch('network_discovery.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'<title>tl-WDR5620</title>')) as run:
            self.assertTrue(discovery.probe('192.0.2.2'))
            args = run.call_args.args[0]
            self.assertEqual(args[-1], 'http://192.0.2.2/')
            self.assertEqual(args[0:4], ['curl','--disable','--noproxy','*'])
            self.assertNotIn('-L',args)
            self.assertEqual(run.call_args.kwargs['timeout'],2)
        for result in (SimpleNamespace(returncode=22,stdout=b'TL-WDR5620'),SimpleNamespace(returncode=0,stdout=b'Other router')):
            with patch('network_discovery.subprocess.run',return_value=result): self.assertFalse(discovery.probe('192.0.2.2'))
        with patch('network_discovery.subprocess.run',side_effect=subprocess.TimeoutExpired('curl',2)):
            self.assertFalse(discovery.probe('192.0.2.2'))


if __name__ == '__main__': unittest.main()
