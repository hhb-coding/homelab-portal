"""Small synthetic databases only / 仅使用小型合成数据库。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from frequency import TelemetryError, stamp
from performance_history import query, latest_frequency, device_role

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def archive():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''PRAGMA user_version=2;
        CREATE TABLE samples(system_id,record_id,created_utc,stats_json);
        CREATE TABLE cpu_frequency_samples(device_id,sample_id,sampled_utc,payload);''')
    return conn


class PerformanceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = archive()
        self.addCleanup(self.conn.close)
        self.device = {'device_id': 'example-x230', 'beszel_system_id': 'example-system'}

    def sample(self, minute, cpu, temperature=None, system='example-system'):
        self.conn.execute('INSERT INTO samples VALUES (?,?,?,?)',
            (system, str(minute), stamp(NOW+timedelta(minutes=minute)),
             json.dumps({'cpu': cpu, 't': temperature})))

    def result(self, minutes=10, role='x230'):
        return query(self.conn, self.device, role, stamp(NOW), stamp(NOW+timedelta(minutes=minutes)))

    def test_sources_units_gaps_mapping_and_exclusive_end(self):
        self.sample(0, 0, {'CPU Package': 49, 'ssd_0': 99, 'k10temp': 44})
        self.sample(1, 100, {'ssd_0': 88})
        self.sample(3, 30, {'CPU Package': 51})
        self.sample(10, 99, {'CPU Package': 90})
        self.sample(2, 88, {'CPU Package': 88}, system='other')
        self.conn.execute('INSERT INTO cpu_frequency_samples VALUES (?,?,?,?)',
            ('example-x230', 'a', stamp(NOW), json.dumps({'cpu_frequency_ghz': 1.19, 'quality': 'ok'})))
        self.conn.execute('PRAGMA query_only=ON')
        data = self.result()
        frequency, usage, temperature = data['series']
        self.assertEqual([s['unit'] for s in data['series']], ['GHz', '%', '°C'])
        self.assertEqual(frequency['points'][0]['value'], 1.19)
        self.assertEqual(usage['stats']['count'], 3)
        self.assertAlmostEqual(usage['stats']['average'], 130/3)
        self.assertEqual(usage['stats']['peak'], 100)
        self.assertIsNone(usage['points'][2]['value'])
        self.assertEqual(temperature['stats']['average'], 50)
        self.assertEqual(temperature['sensor'], 'CPU Package')
        self.assertIsNone(temperature['points'][1]['value'])
        hp = self.result(role='hp')['series'][2]
        self.assertEqual(hp['stats']['average'], 44)
        self.assertIn('Current Beszel mapping', data['mapping_note'])

    def test_aggregation_cap_weighted_statistics_and_partial_buckets(self):
        # 30d => 87-minute bins; uneven occupancy must not bias the mean.
        self.sample(0, 10, {'CPU Package': 40})
        self.sample(1, 20, {'CPU Package': 42})
        self.sample(100, 90, {})
        data = self.result(minutes=30*1440)
        for item in data['series']:
            self.assertLessEqual(len(item['points']), 500)
        usage = data['series'][1]
        self.assertEqual(usage['points'][0]['value'], 15)
        self.assertEqual(usage['stats']['average'], 40)
        self.assertEqual(usage['stats']['peak'], 90)
        self.assertTrue(usage['points'][1]['gap'])
        self.assertIsNone(usage['points'][2]['value'])

    def test_readability_ranges_density_raw_statistics_and_gaps(self):
        self.sample(0, 10, {'CPU Package': 40})
        self.sample(1, 90, {'CPU Package': 60})
        self.sample(3, 20, {})
        self.sample(59, 40, {'CPU Package': 50})
        for minute, value in [(0, 1.0), (1, 3.0), (59, 2.0)]:
            self.conn.execute('INSERT INTO cpu_frequency_samples VALUES (?,?,?,?)',
                ('example-x230', str(minute), stamp(NOW+timedelta(minutes=minute)),
                 json.dumps({'cpu_frequency_ghz': value, 'quality': 'ok'})))
        self.conn.execute('PRAGMA query_only=ON')
        reference = None
        for minutes, width, count in [(60, 60, 60), (360, 300, 72), (1440, 900, 96)]:
            with self.subTest(minutes=minutes):
                data = self.result(minutes=minutes)
                self.assertEqual(data['bucket_seconds'], width)
                self.assertEqual([len(s['points']) for s in data['series']], [count]*3)
                stats = [s['stats'] for s in data['series']]
                if reference is None: reference = stats
                else: self.assertEqual(stats, reference)
                self.assertEqual(stats[0]['average'], 2.0)
                self.assertEqual(stats[0]['peak'], 3.0)
                self.assertEqual(stats[1]['average'], 40)
                self.assertEqual(stats[1]['peak'], 90)
                self.assertEqual(stats[2]['count'], 3)
                self.assertEqual(stats[2]['average'], 50)
                self.assertEqual(stats[2]['peak'], 60)
                if minutes > 60:
                    self.assertLess(max(p['value'] for p in data['series'][1]['points'] if p['value'] is not None), 90)
                    self.assertTrue(data['series'][1]['points'][0]['gap'])
                    self.assertTrue(any(p['value'] is None for p in data['series'][1]['points']))
        self.assertEqual(self.result(minutes=7*1440)['bucket_seconds'], 1260)
        self.assertLessEqual(len(self.result(minutes=30*1440)['series'][0]['points']), 500)

    def test_invalid_values_and_range(self):
        for i, value in enumerate([None, True, '3', -1, 101]):
            self.sample(i, value, {'CPU Package': value})
        self.assertEqual(self.result()['series'][1]['stats']['count'], 0)
        with self.assertRaises(TelemetryError): self.result(minutes=0)
        with self.assertRaises(TelemetryError): self.result(minutes=181*1440)
        with self.assertRaises(TelemetryError):
            query(self.conn, self.device, 'x230', '2026-01-01', stamp(NOW))
        self.conn.execute('PRAGMA user_version=1')
        with self.assertRaisesRegex(TelemetryError, 'archive_migration_required'): self.result()

    def test_extended_metrics_strict_values_statistics_and_default_compatibility(self):
        rows = [
            {'cpu': 4, 'mp': 25, 'dp': 60, 'b': [1000, 2000]},
            {'mp': 75, 'dp': 80, 'b': [3000, 6000]},
            {'mp': None, 'dp': '20', 'b': [None, 8000]},
            {'mp': True, 'dp': 101, 'b': [False, -1]},
            {'mp': -1, 'dp': {}, 'b': [1]},
            {'mp': '30', 'b': 'unknown', 'ns': 1, 'nr': 2},
            {'mp': float('nan'), 'dp': float('inf'), 'b': [float('inf'), '4']},
            {'mp': 0, 'dp': 0, 'b': [0, 0]},
        ]
        for i, row in enumerate(rows):
            self.conn.execute('INSERT INTO samples VALUES (?,?,?,?)',
                ('example-system', str(i), stamp(NOW+timedelta(minutes=i)), json.dumps(row)))
        self.conn.execute('PRAGMA query_only=ON')
        default = self.result()
        data = query(self.conn, self.device, 'x230', stamp(NOW), stamp(NOW+timedelta(minutes=10)), extended=True)
        self.assertEqual(data['series'][:3], default['series'])
        self.assertEqual(len(default['series']), 3)
        self.assertEqual(len(data['series']), 7)
        memory, disk, upload, download = data['series'][3:]
        self.assertEqual([s['unit'] for s in data['series'][3:]], ['%', '%', 'B/s', 'B/s'])
        self.assertAlmostEqual(memory['stats']['average'], 100/3)
        self.assertEqual(disk['stats']['peak'], 80)
        self.assertEqual(upload['stats']['average'], 4000/3)
        self.assertEqual(download['stats']['average'], 4000)
        self.assertIsNone(upload['points'][2]['value'])
        self.assertEqual(download['points'][2]['value'], 8000)
        self.assertEqual(upload['points'][7]['value'], 0)
        for item in data['series'][3:]:
            self.assertIsNone(item['points'][5]['value'])
            self.assertIsNone(item['points'][6]['value'])
        aggregated = query(self.conn, self.device, 'hp', stamp(NOW), stamp(NOW+timedelta(hours=6)), extended=True)
        self.assertTrue(all(s['points'][0]['gap'] for s in aggregated['series'][3:]))
        long = query(self.conn, self.device, 'hp', stamp(NOW), stamp(NOW+timedelta(days=180)), extended=True)
        self.assertTrue(all(len(s['points']) <= 500 for s in long['series']))
        self.assertEqual(long['series'][5]['stats'], upload['stats'])

    def test_extended_missing_has_no_fabricated_zero_or_legacy_network_units(self):
        self.sample(0, 5)
        data = query(self.conn, self.device, 'hp', stamp(NOW), stamp(NOW+timedelta(hours=1)), extended=True)
        for item in data['series'][3:]:
            self.assertEqual(item['stats']['count'], 0)
            self.assertIsNone(item['stats']['average'])
            self.assertTrue(all(p['value'] is None for p in item['points']))

    def test_extended_timeout_releases_progress_handler(self):
        from unittest.mock import patch
        self.sample(0, 5)
        with patch('performance_history.time.monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(TelemetryError, 'query_timeout'):
                query(self.conn, self.device, 'hp', stamp(NOW), stamp(NOW+timedelta(hours=1)), extended=True)
        self.assertEqual(self.result()['series'][1]['stats']['count'], 1)

    def test_device_scope(self):
        self.assertEqual(device_role({'device_id': 'local'}, 'local'), 'hp')
        self.assertEqual(device_role({'device_id': 'example-x230'}, ''), 'x230')
        self.assertIsNone(device_role({'device_id': 'example-dell'}, 'local'))

    def test_latest_sample_not_latest_arrival_and_strict_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'registry.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE frequency_inbox(device_id,payload,archived)')
                def insert(seconds, quality='ok', value=1.19, archived=0):
                    payload = {'sampled_utc': stamp(NOW+timedelta(seconds=seconds)), 'sample_id': str(seconds),
                               'quality': quality, 'source': 'windows_processor_performance', 'cpu_frequency_ghz': value}
                    conn.execute('INSERT INTO frequency_inbox VALUES (?,?,?)', ('example-x230', json.dumps(payload), archived))
                    conn.commit()
                insert(-120, archived=1)
                insert(-500)
                self.assertEqual(latest_frequency(path, 'example-x230', NOW)['cpu_frequency_ghz'], 1.19)
                self.assertIsNone(latest_frequency(path, 'example-x230', NOW+timedelta(milliseconds=1))['cpu_frequency_ghz'])
                insert(-10, quality='unavailable', value=None)
                self.assertIsNone(latest_frequency(path, 'example-x230', NOW)['cpu_frequency_ghz'])
                insert(-5, quality='partial')
                self.assertIsNone(latest_frequency(path, 'example-x230', NOW)['cpu_frequency_ghz'])
                insert(1)
                self.assertEqual(latest_frequency(path, 'example-x230', NOW)['frequency_freshness'], 'invalid')
            self.assertIsNone(latest_frequency(Path(directory)/'missing.db', 'example-x230', NOW)['cpu_frequency_ghz'])
            self.assertFalse((Path(directory)/'missing.db').exists())
