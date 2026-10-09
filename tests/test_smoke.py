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
            HEARTBEAT_TOKEN="smoke-test-only", BESZEL_TOKEN="",
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
        for marker in (b'id="device-panel"', b'id="network-panel" class="hidden"', b'id="network-summary"', b'id="network-devices"'):
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
        for path in ("/static/lite.js", "/static/lite.css", "/static/dashboard.js", "/static/style.css"):
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
        for name in ("dashboard.js", "lite.js"):
            source = (root / "static" / name).read_text()
            code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
            self.assertNotRegex(code, r"\b(?:const|let)\s+\w|=>|\?\.|\bfetch\s*\(")
            self.assertIn("XMLHttpRequest", source)
        for name in ("style.css", "lite.css"):
            css = re.sub(r"/\*.*?\*/", "", (root / "static" / name).read_text(), flags=re.S)
            self.assertNotRegex(css, r"display\s*:\s*(?:inline-)?grid|\bvar\s*\(|(?:^|[;{])\s*(?:gap|row-gap|column-gap|--[\w-]+)\s*:")

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
                           disk_available=None, disk_usage_percent=18, capacity_unit="GiB")
        with patch("dashboard_service._get_beszel_snapshot", return_value=snapshot):
            data = self.client.get("/api/dashboard").json
        device = data["devices"][0]
        self.assertEqual(data["count"], 1)
        self.assertEqual(device["lan_ip"], "192.0.2.10")
        self.assertEqual(device["beszel_status"], "up")
        self.assertTrue(device["metrics_available"])
        self.assertEqual(device["cpu_percent"], 0)
        for key in ("memory_total", "disk_total", "disk_used", "disk_available", "disk_usage_percent", "capacity_unit"):
            self.assertEqual(device[key], snapshot[0][key])
        self.assertIsNone(device["zerotier_ip"])
        snapshot[0]["status"] = "down"
        with patch("dashboard_service._get_beszel_snapshot", return_value=snapshot):
            self.assertEqual(self.client.get("/api/dashboard").json["devices"][0]["beszel_status"], "down")
        data = self.client.get("/api/dashboard").json
        self.assertEqual(data["sources"]["metrics_status"], "unavailable")
        self.assertFalse(data["devices"][0]["metrics_available"])
        self.assertIsNone(data["devices"][0]["cpu_percent"])
        self.assertIsNone(data["devices"][0]["disk_total"])
        self.assertEqual(data["devices"][0]["lan_ip"], "192.0.2.10")

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
