"""Beszel capacity contracts / Beszel 容量数据契约测试。"""
import json
import unittest
from unittest.mock import patch

from beszel_client import BeszelClient


class CapacityTests(unittest.TestCase):
    def test_primary_filesystem_and_units(self):
        # Reserved space means dp need not equal du/d / 保留空间使 dp 不等于 du/d。
        stats = {"m": 15.08, "d": 116.34, "du": 52.94, "dp": 47.96,
                 "efs": {"data": {"d": 9000, "du": 8000}}}
        client = BeszelClient("http://invalid.test")
        with patch.object(client, "get_systems", return_value=[
            {"id": "linked", "info": {"dp": 20, "mp": 30}}
        ]), patch.object(client, "get_latest_stats", return_value={"stats": stats}):
            result = client.get_snapshot()[0]
        self.assertEqual(result["memory_total"], 15.08)
        self.assertEqual(result["disk_total"], 116.34)
        self.assertEqual(result["disk_used"], 52.94)
        self.assertEqual(result["disk_usage_percent"], 47.96)
        self.assertEqual(result["disk_percent"], 20)  # Existing API / 旧接口
        self.assertAlmostEqual(result["disk_available"], 52.94 * (100 - 47.96) / 47.96)
        self.assertTrue(result["disk_available_estimated"])
        self.assertNotAlmostEqual(result["disk_available"], 116.34 - 52.94)
        self.assertEqual(result["capacity_unit"], "GiB")
        self.assertEqual(result["beszel_system_id"], "linked")

    def test_invalid_capacities_are_json_null(self):
        for value in [None, "", "8", False, [], {}, -1, float("nan"),
                      float("inf"), 10**1000]:
            with self.subTest(value=type(value).__name__):
                result = BeszelClient.capacity_metrics({"m": value, "d": value,
                                                       "du": value, "dp": value})
                for key in ["memory_total", "disk_total", "disk_used", "disk_usage_percent"]:
                    self.assertIsNone(result[key])
                self.assertIsNone(result["disk_available"])
                self.assertFalse(result["disk_available_estimated"])
                json.dumps(result, allow_nan=False)

    def test_empty_full_and_partial_samples(self):
        for used, percent in [(0, 0), (100, 100)]:
            result = BeszelClient.capacity_metrics({"m": 0, "d": 100, "du": used, "dp": percent})
            self.assertEqual(result["disk_used"], used)
            self.assertEqual(result["disk_usage_percent"], percent)
            self.assertIsNone(result["memory_total"])
            self.assertEqual(result["disk_available"], None if percent == 0 else 0)
        for stats in [{}, {"d": 0, "du": 0, "dp": 0}, {"d": 10, "du": 11, "dp": 80},
                      {"d": 10}, {"d": 10, "du": 1, "dp": 101}]:
            self.assertIsNone(BeszelClient.capacity_metrics(stats)["disk_usage_percent"])

    def test_malformed_stats_keep_device_identity(self):
        client = BeszelClient("http://invalid.test")
        for stats in [None, [], "bad"]:
            with patch.object(client, "get_systems", return_value=[{"id": "linked"}]), \
                 patch.object(client, "get_latest_stats", return_value={"stats": stats}):
                result = client.get_snapshot()[0]
            self.assertEqual(result["beszel_system_id"], "linked")
            self.assertIsNone(result["disk_total"])

    def test_estimate_boundaries_and_reliability(self):
        # Linux/Windows share the same normalized sample / Linux 与 Windows 采用同一统计口径。
        for total, used, percent, expected in [(116.34, 53.14, 48.14, 57.24637308),
                                               (100, 50, 50, 50), (100, 90, 100, 0),
                                               (2048, 1024, 50, 1024)]:
            with self.subTest(percent=percent, used=used):
                result = BeszelClient.capacity_metrics({"d": total, "du": used, "dp": percent})
                self.assertAlmostEqual(result["disk_available"], expected, places=5)
                self.assertTrue(result["disk_available_estimated"])
        for stats in [{"d": 100, "du": 0, "dp": 0}, {"d": 100, "du": 1, "dp": 0},
                      {"d": 100, "du": 0, "dp": 100}, {"d": 100, "du": 50, "dp": 1},
                      {"d": 100, "du": 0.01, "dp": 0.01},
                      {"d": 1e308, "du": 1e307, "dp": 0.01},
                      {"d": 100, "du": 50}, {"d": 100, "dp": 50}, {"du": 50, "dp": 50}]:
            with self.subTest(stats=stats):
                result = BeszelClient.capacity_metrics(stats)
                self.assertIsNone(result["disk_available"])
                self.assertFalse(result["disk_available_estimated"])
                json.dumps(result, allow_nan=False)
        for key in ["d", "du", "dp"]:
            for invalid in [None, False, "50", -1, float("nan"), float("inf")]:
                stats = {"d": 100, "du": 50, "dp": 50}
                stats[key] = invalid
                with self.subTest(key=key, invalid=invalid):
                    result = BeszelClient.capacity_metrics(stats)
                    self.assertIsNone(result["disk_available"])
                    json.dumps(result, allow_nan=False)
