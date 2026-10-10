import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import dashboard_service as service
from beszel_client import BeszelAPIError

class FreshnessTests(unittest.TestCase):
    def test_source_time_validation(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()
        expected = now - 60
        for value in ['2026-01-01 23:59:00', '2026-01-01T23:59:00Z',
                      '2026-01-01T18:59:00-05:00']:
            self.assertEqual(service.source_timestamp(value, now), expected)
        for value in [None, '', False, 123, 'bad', '2026-01-01', '2026-02-30 00:00:00',
                      '2026-01-02T00:01:00Z']:
            self.assertIsNone(service.source_timestamp(value, now))

    def test_data_timestamp_survives_polling_and_metrics_failure(self):
        with patch.object(service, '_get_registry_devices', return_value=[
            {'last_seen': '2026-01-01 23:00:00', 'beszel_system_id': 'a'}]), \
             patch.object(service, '_get_beszel_snapshot', return_value=[
                 {'beszel_system_id': 'a', 'latest_stats_created': '2026-01-01T23:30:00Z', 'stats_keys': ['cpu']}]), \
             patch.object(service.time, 'time', return_value=1767312000):
            first = service.build_dashboard()
            second = service.build_dashboard()
            self.assertEqual(first['data_updated_at'], second['data_updated_at'])
            self.assertEqual(first['data_updated_at'], 1767310200)
            with patch.object(service, '_get_beszel_snapshot', side_effect=BeszelAPIError('down')):
                degraded = service.build_dashboard()
            self.assertEqual(degraded['data_updated_at'], 1767308400)
            self.assertEqual(degraded['status'], 'ok')
        with patch.object(service, '_get_registry_devices', return_value=[]), \
             patch.object(service, '_get_beszel_snapshot', return_value=[]):
            self.assertIsNone(service.build_dashboard()['data_updated_at'])
