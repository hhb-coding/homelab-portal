"""Local CPU frequency and identity contracts / 本机频率及身份契约。"""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

with patch("dotenv.load_dotenv"):
    service = importlib.import_module("dashboard_service")


class CPUFrequencyTests(unittest.TestCase):
    def test_multicore_current_frequency_and_invalid_samples(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for index, value in enumerate(["1000000", "1800000", "0", "-1",
                                           "nan", "inf", "bad", "", "1e999"]):
                directory = root / ("cpu%d" % index) / "cpufreq"
                directory.mkdir(parents=True)
                (directory / "scaling_cur_freq").write_text(value)
                (directory / "cpuinfo_max_freq").write_text("9000000")
            (root / "cpu99" / "cpufreq").mkdir(parents=True)
            self.assertAlmostEqual(service.local_cpu_frequency_ghz(root), 1.4)

    def test_missing_invalid_and_unreadable_sources(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            self.assertIsNone(service.local_cpu_frequency_ghz(root))
            path = root / "cpu0" / "cpufreq" / "scaling_cur_freq"
            path.parent.mkdir(parents=True)
            path.write_text("0")
            self.assertIsNone(service.local_cpu_frequency_ghz(root))
            with patch.object(Path, "read_text", side_effect=PermissionError):
                self.assertIsNone(service.local_cpu_frequency_ghz(root))
            path.write_bytes(b"\xff")
            self.assertIsNone(service.local_cpu_frequency_ghz(root))
        with patch.object(Path, "glob", side_effect=OSError):
            self.assertIsNone(service.local_cpu_frequency_ghz())

    def test_mapping_and_additive_api(self):
        registry = [{"device_id": "local-test", "beszel_system_id": "one"},
                    {"device_id": "remote-test", "beszel_system_id": "two"}]
        metrics = [{"beszel_system_id": key, "temperature": 39.0, "cpu_percent": 12}
                   for key in ("one", "two")]
        with patch.object(service, "_get_registry_devices", return_value=registry), \
             patch.object(service, "_get_beszel_snapshot", return_value=metrics), \
             patch.object(service.config, "LOCAL_DEVICE_ID", "local-test"), \
             patch.object(service, "local_cpu_frequency_ghz", return_value=1.4) as sample:
            result = service.build_dashboard()
            sample.assert_called_once_with()
            local, remote = result["devices"]
            self.assertEqual(local["cpu_frequency_ghz"], 1.4)
            self.assertIsNone(remote["cpu_frequency_ghz"])
            for device in (local, remote):
                self.assertEqual(device["temperature"], 39.0)
                self.assertEqual(device["cpu_percent"], 12)
                self.assertTrue(device["metrics_available"])
            json.dumps(result, allow_nan=False)
            for identity in ("", "unregistered"):
                with patch.object(service.config, "LOCAL_DEVICE_ID", identity):
                    sample.reset_mock()
                    self.assertTrue(all(d["cpu_frequency_ghz"] is None
                                        for d in service.build_dashboard()["devices"]))
                    sample.assert_not_called()
            with patch.object(service, "local_cpu_frequency_ghz", return_value=None):
                self.assertIsNone(service.build_dashboard()["devices"][0]["cpu_frequency_ghz"])
            with patch.object(service, "_get_beszel_snapshot", side_effect=service.BeszelAPIError("test")):
                result = service.build_dashboard()
                self.assertEqual(result["sources"]["metrics_status"], "unavailable")
                self.assertEqual(result["devices"][0]["cpu_frequency_ghz"], 1.4)
            with patch.object(service, "_get_registry_devices", return_value=[registry[0]] * 2):
                sample.reset_mock()
                self.assertTrue(all(d["cpu_frequency_ghz"] is None
                                    for d in service.build_dashboard()["devices"]))
                sample.assert_not_called()
