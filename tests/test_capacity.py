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
        self.assertIsNone(result["disk_available"])
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
                json.dumps(result, allow_nan=False)

    def test_empty_full_and_partial_samples(self):
        for used, percent in [(0, 0), (100, 100)]:
            result = BeszelClient.capacity_metrics({"m": 0, "d": 100, "du": used, "dp": percent})
            self.assertEqual(result["disk_used"], used)
            self.assertEqual(result["disk_usage_percent"], percent)
            self.assertIsNone(result["memory_total"])
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
