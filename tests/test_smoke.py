"""Isolated Flask smoke tests / 隔离的 Flask 冒烟测试。

Run in a fresh process: python -B -m unittest discover -s tests -v
在独立进程中运行；导入应用前切换到临时数据库，禁止网络请求。
"""
import importlib
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PortalSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="portal-smoke-")
        cls.addClassCleanup(cls.temp.cleanup)
        # Never read local .env or use live credentials / 不读取本地配置或真实凭据。
        with patch("dotenv.load_dotenv"):
            config = importlib.import_module("config")
        cls.config = config
        cls.settings = patch.multiple(
            config, DATABASE_PATH=Path(cls.temp.name) / "test.db",
            HEARTBEAT_TOKEN="smoke-test-only", BESZEL_TOKEN="", LOCAL_DEVICE_ID="",
            BESZEL_EMAIL="", BESZEL_PASSWORD="",
        )
        cls.settings.start()
        cls.addClassCleanup(cls.settings.stop)
        cls.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Network forbidden in tests"))
        cls.network.start()
        cls.addClassCleanup(cls.network.stop)
        cls.app_module = importlib.import_module("app")
        cls.app_module.app.config.update(TESTING=True)
        cls.db = importlib.import_module("db")

    def setUp(self):
        self.client = self.app_module.app.test_client()
        with self.db.get_connection() as connection:
            connection.execute("DELETE FROM devices")

    def heartbeat(self, **values):
        payload = {"device_id": "test-device", "lan_ip": "192.0.2.10"}
        payload.update(values)
        return self.client.post("/api/heartbeat", json=payload, headers={"X-Heartbeat-Token": "smoke-test-only"})

    def test_pages_and_assets(self):
        full = self.client.get("/")
        self.assertEqual(full.status_code, 200)
        for marker in (b'href="/lite"', b'id="mini-devices"', b'id="devices"', b'dashboard.js'):
            self.assertIn(marker, full.data)
        for marker in (b'id="device-panel"', b'id="network-panel" class="hidden"', b'id="network-summary"', b'id="network-devices"', b'id="tab-history"', b'id="history-panel" class="hidden"', b'performance-history.js'):
            self.assertIn(marker, full.data)
        self.assertNotIn(b'disabled="disabled"', full.data)
        self.assertNotIn(b'Select a mini card above', full.data)
        self.assertNotIn(b'Device Details', full.data)
        lite = self.client.get("/lite")
        self.assertEqual(lite.status_code, 200)
        for marker in (b'href="/"', b'Full View', b'lite.js', b'lite.css'):
            self.assertIn(marker, lite.data)
        for marker in (b'dashboard.js', b'/api/history', b'<svg'):
            self.assertNotIn(marker, lite.data)
        for path in ("/static/lite.js", "/static/lite.css", "/static/dashboard.js", "/static/style.css", "/static/offline-seen.js", "/static/performance-history.js"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()
        script = (Path(__file__).resolve().parents[1] / "static/lite.js").read_text()
        self.assertNotIn("/api/history", script)
        self.assertIn("XMLHttpRequest", script)
        self.assertIn("setInterval(refresh, 5000)", script)

    def test_health_and_empty_registry(self):
        self.assertEqual(self.client.get("/api/health").json["database"], "ok")
        self.assertEqual(self.client.get("/api/devices").json, {"devices": []})
        self.assertEqual(self.client.get("/api/devices/missing").status_code, 404)
        dashboard = self.client.get("/api/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json["devices"], [])

    def test_legacy_frontend_guards(self):
        """Guard known iOS 9 incompatibilities / 防止引入已知的 iOS 9 不兼容语法。"""
        root = Path(__file__).resolve().parents[1]
        for name in ("dashboard.js", "lite.js", "offline-seen.js", "performance-history.js"):
            source = (root / "static" / name).read_text()
            code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
            self.assertNotRegex(code, r"\b(?:const|let)\s+\w|=>|\?\.|\bfetch\s*\(")
            if name != "offline-seen.js":
                self.assertIn("XMLHttpRequest", source)
        for name in ("style.css", "lite.css"):
            css = re.sub(r"/\*.*?\*/", "", (root / "static" / name).read_text(), flags=re.S)
            self.assertNotRegex(css, r"display\s*:\s*(?:inline-)?grid|\bvar\s*\(|(?:^|[;{])\s*(?:gap|row-gap|column-gap|--[\w-]+)\s*:")

    def test_equal_progress_bar_heights(self):
        """Bar height and label centering regression / 横条等高与文字垂直居中回归。"""
        source = (Path(__file__).resolve().parents[1] / "static/style.css").read_text()
        def rule(selector):
            return re.search(re.escape(selector) + r"\s*\{([^}]+)\}", source).group(1)
        self.assertRegex(rule(".bar"), r"height:24px")
        self.assertRegex(rule(".fill"), r"height:100%")
        self.assertNotIn("height:", rule(".disk-bar"))
        self.assertRegex(rule(".disk-used, .disk-free"), r"height:100%")
        self.assertRegex(rule(".disk-label"), r"line-height:22px")
        self.assertRegex(rule(".metric"), r"line-height:24px")

    def test_heartbeat_validation(self):
        self.assertEqual(self.client.post("/api/heartbeat", json={}).status_code, 401)
        headers = {"X-Heartbeat-Token": "smoke-test-only"}
        for payload in ([], {}, {"device_id": " "}):
            self.assertEqual(self.client.post("/api/heartbeat", json=payload, headers=headers).status_code, 400)
        with patch.object(self.config, "HEARTBEAT_TOKEN", ""):
            self.assertEqual(self.client.post("/api/heartbeat", json={}).status_code, 503)

    def test_heartbeat_registry_and_ip_events(self):
        self.assertTrue(self.heartbeat().json["created"])
        response = self.heartbeat(lan_ip="192.0.2.11", zerotier_ip="198.51.100.10")
        self.assertFalse(response.json["created"])
        self.assertTrue(response.json["lan_ip_changed"])
        self.assertTrue(response.json["zerotier_ip_changed"])
        self.assertEqual(self.client.get("/api/devices/test-device").json["lan_ip"], "192.0.2.11")
        with self.db.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ip_events").fetchone()[0], 2)

    def test_dashboard_merge_and_missing_metrics(self):
        self.heartbeat()
        with self.db.get_connection() as connection:
            connection.execute("UPDATE devices SET beszel_system_id = 'test-system'")
        snapshot = [{"beszel_system_id": "test-system", "status": "up", "host": "203.0.113.99", "cpu_percent": 0, "memory_percent": 42, "disk_percent": 18, "load_1": 0.25}]
        snapshot[0].update(memory_total=8, disk_total=100, disk_used=18,
                           disk_available=82, disk_available_estimated=True, disk_usage_percent=18, capacity_unit="GiB")
        with patch("dashboard_service._get_beszel_snapshot", return_value=snapshot):
            data = self.client.get("/api/dashboard").json
        device = data["devices"][0]
        self.assertEqual(data["count"], 1)
        self.assertEqual(device["lan_ip"], "192.0.2.10")
        self.assertEqual(device["beszel_status"], "up")
        self.assertTrue(device["metrics_available"])
        self.assertEqual(device["cpu_percent"], 0)
        self.assertIsNone(device["cpu_frequency_ghz"])
        for key in ("memory_total", "disk_total", "disk_used", "disk_available", "disk_available_estimated", "disk_usage_percent", "capacity_unit"):
            self.assertEqual(device[key], snapshot[0][key])
        self.assertIsNone(device["zerotier_ip"])
        with patch("dashboard_service._get_beszel_snapshot", return_value=snapshot), \
             patch.object(self.config, "LOCAL_DEVICE_ID", "test-device"), \
             patch("dashboard_service.local_cpu_frequency_ghz", return_value=1.4):
            response = self.client.get("/api/dashboard")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["devices"][0]["cpu_frequency_ghz"], 1.4)
        snapshot[0]["status"] = "down"
        with patch("dashboard_service._get_beszel_snapshot", return_value=snapshot):
            self.assertEqual(self.client.get("/api/dashboard").json["devices"][0]["beszel_status"], "down")
        data = self.client.get("/api/dashboard").json
        self.assertEqual(data["sources"]["metrics_status"], "unavailable")
        self.assertFalse(data["devices"][0]["metrics_available"])
        self.assertIsNone(data["devices"][0]["cpu_percent"])
        self.assertIsNone(data["devices"][0]["disk_total"])
        self.assertEqual(data["devices"][0]["lan_ip"], "192.0.2.10")

    def test_frequency_auth_identity_and_validation(self):
        from datetime import datetime, timezone
        from test_frequency_pipeline import observation
        row = observation(when=datetime.now(timezone.utc))
        route = '/api/telemetry/cpu-frequency'
        headers = {'X-Heartbeat-Token':'smoke-test-only'}
        payload = {'device_id':'test-device','samples':[row]}
        self.assertEqual(self.client.post(route,json=payload).status_code,401)
        with patch.object(self.config,'HEARTBEAT_TOKEN',''):
            self.assertEqual(self.client.post(route,json=payload,headers=headers).status_code,503)
        self.assertEqual(self.client.post(route,json=payload,headers=headers).status_code,403)
        self.heartbeat()
        response=self.client.post(route,json=payload,headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['accepted'],[row['sample_id']])
        self.assertEqual(self.client.post(route,json=payload,headers=headers).json['duplicates'],[row['sample_id']])
        payload['samples'][0]['cpu_frequency_ghz']=3
        self.assertEqual(self.client.post(route,json=payload,headers=headers).status_code,409)
        payload['samples'][0]['source']=[]
        self.assertEqual(self.client.post(route,json=payload,headers=headers).status_code,400)
        self.assertEqual(self.client.post(route,data='x'*131073,headers=headers).status_code,413)

    def test_frequency_receive_does_not_update_heartbeat(self):
        from datetime import datetime, timezone
        from test_frequency_pipeline import observation
        self.heartbeat()
        old=self.client.get('/api/devices/test-device').json['last_seen']
        with patch('frequency.receive',return_value={'accepted':[],'duplicates':[]}):
            self.assertEqual(self.client.post('/api/telemetry/cpu-frequency',
                json={'device_id':'test-device','samples':[observation(when=datetime.now(timezone.utc))]},
                headers={'X-Heartbeat-Token':'smoke-test-only'}).status_code,200)
        self.assertEqual(self.client.get('/api/devices/test-device').json['last_seen'],old)

    def test_frequency_inbox_busy_and_overflow_feedback(self):
        from frequency import TelemetryError
        import sqlite3
        payload={'device_id':'test-device','samples':[]}
        headers={'X-Heartbeat-Token':'smoke-test-only'}
        for error in [TelemetryError('queue_full',503),sqlite3.OperationalError('synthetic')]:
            with patch('frequency.receive',side_effect=error):
                response=self.client.post('/api/telemetry/cpu-frequency',json=payload,headers=headers)
                self.assertEqual(response.status_code,503)

    def test_frequency_history_disabled_by_default(self):
        self.assertEqual(self.client.get('/api/history/v2').status_code,503)

    def test_frequency_history_query_only_synthetic_archive(self):
        from datetime import datetime, timedelta, timezone
        from test_frequency_pipeline import observation
        from frequency import receive, drain, stamp
        from frequency_migration import migrate
        from metrics_archive import writer
        self.heartbeat()
        now=datetime.now(timezone.utc)
        archive=Path(self.temp.name)/'query-history.db'
        receive(self.config.DATABASE_PATH,'test-device',[observation(800,when=now)],now)
        with writer(archive,lambda p:p) as c:
            migrate(c,2,lambda:None);drain(c,self.config.DATABASE_PATH,lambda:None,now)
        args={'device_id':'test-device','start':stamp(now-timedelta(seconds=1)),'end':stamp(now+timedelta(seconds=1))}
        with patch.object(self.config,'FREQUENCY_HISTORY_ENABLED',True), \
             patch.dict('os.environ',{'METRICS_ARCHIVE_PATH':str(archive)}), \
             patch('metrics_archive.require_hdd',side_effect=lambda p,*a:p):
            response=self.client.get('/api/history/v2',query_string=args)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['unit'],'GHz')
            self.assertTrue(response.json['points'])
            self.assertEqual(self.client.get('/api/history/v2',query_string=dict(args,metric='cpu_percent')).status_code,400)
            self.assertEqual(self.client.get('/api/history/v2',query_string=dict(args,limit='bad')).status_code,400)

    def test_x230_frequency_survives_beszel_failure_and_retains_source_time(self):
        from datetime import datetime, timezone
        from frequency import stamp
        self.heartbeat(device_id="example-x230")
        sample = {"sample_id": "a"*32, "sampled_utc": stamp(datetime.now(timezone.utc)),
                  "cpu_frequency_ghz": 1.19, "quality": "ok", "source": "windows_processor_performance",
                  "logical_cpu_count": 4, "valid_cpu_count": 4, "window_ms": 1000, "error": None}
        response = self.client.post("/api/telemetry/cpu-frequency", json={"device_id": "example-x230", "samples": [sample]},
                                    headers={"X-Heartbeat-Token": "smoke-test-only"})
        self.assertEqual(response.status_code, 200)
        data = self.client.get("/api/dashboard").json["devices"][0]
        self.assertFalse(data["metrics_available"])
        self.assertTrue(data["performance_history_supported"])
        self.assertEqual(data["cpu_frequency_ghz"], 1.19)
        self.assertEqual(data["frequency_sampled_utc"], sample["sampled_utc"])
        self.assertEqual(data["frequency_freshness"], "fresh")

    def test_performance_api_isolated_archive_and_disabled_default(self):
        import sqlite3
        from performance_history import query as real_query
        self.heartbeat(device_id="example-x230")
        self.assertEqual(self.client.get("/api/history/v2/performance?device_id=example-x230").status_code, 503)
        archive = Path(self.temp.name)/"performance.sqlite3"
        with sqlite3.connect(archive) as conn:
            conn.executescript("PRAGMA user_version=2; CREATE TABLE samples(system_id,record_id,created_utc,stats_json); CREATE TABLE cpu_frequency_samples(device_id,sample_id,sampled_utc,payload);")
        args = "?device_id=example-x230&start=2026-01-01T00:00:00Z&end=2026-01-02T00:00:00Z"
        with patch.object(self.config, "FREQUENCY_HISTORY_ENABLED", True), \
             patch.dict("os.environ", {"METRICS_ARCHIVE_PATH": str(archive)}), \
             patch("metrics_archive.require_hdd"):
            def checked_query(conn, *args, **kwargs):
                self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
                return real_query(conn, *args, **kwargs)
            with patch("performance_history.query", side_effect=checked_query):
                response = self.client.get("/api/history/v2/performance"+args)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["series"]), 3)
            extended = self.client.get("/api/history/v2/performance"+args+"&extended=1")
            self.assertEqual(extended.status_code, 200)
            self.assertEqual(len(extended.json["series"]), 7)
            for value in ['0', 'true', 'unknown']:
                legacy = self.client.get("/api/history/v2/performance"+args+"&extended="+value)
                self.assertEqual(len(legacy.json['series']), 3)
            self.assertEqual(response.json["bucket_seconds"], 900)
            self.assertEqual(len(response.json["series"][0]["points"]), 96)
            for hours, width, count in [(1, 60, 60), (6, 300, 72)]:
                end = "2026-01-01T%02d:00:00Z" % hours
                response = self.client.get("/api/history/v2/performance", query_string={
                    "device_id": "example-x230", "start": "2026-01-01T00:00:00Z", "end": end})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["bucket_seconds"], width)
                self.assertEqual(len(response.json["series"][0]["points"]), count)
            self.assertEqual(self.client.get("/api/history/v2/performance?device_id=example-x230").status_code, 400)
            self.assertEqual(self.client.get("/api/history/v2/performance?device_id=missing").status_code, 404)
            self.heartbeat(device_id="example-dell")
            self.assertEqual(self.client.get("/api/history/v2/performance?device_id=example-dell").status_code, 400)

    def test_metrics_and_history_without_credentials(self):
        self.assertEqual(self.client.get("/api/metrics").status_code, 503)
        self.assertEqual(self.client.get("/api/history").status_code, 502)

    def test_history_parameter_and_failure(self):
        from beszel_client import BeszelAPIError
        with patch("history_service.build_history", return_value={"status": "ok", "devices": []}) as build:
            self.assertEqual(self.client.get("/api/history?minutes=bad").status_code, 200)
            build.assert_called_once_with(minutes=60)
        with patch("history_service.build_history", side_effect=BeszelAPIError("test failure")):
            self.assertEqual(self.client.get("/api/history").json["error"], "beszel_history_unavailable")


if __name__ == "__main__":
    unittest.main()
