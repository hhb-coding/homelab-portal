"""Receipt retention must not consume pending capacity / 回执与积压容量回归。

Only temporary registries/archives and in-process transports are used.
仅使用临时数据库及进程内传输，不读取生产配置或访问网络。
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from urllib.error import HTTPError

from frequency import canonical, drain, queue_status, receive, stamp, TelemetryError
from frequency_migration import migrate
from metrics_archive import writer
from test_frequency_pipeline import linux

ROOT = Path(__file__).resolve().parents[1]


class FrequencyCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='frequency-capacity-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = self.root / 'registry.db'
        self.archive = self.root / 'archive.db'
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        with closing(sqlite3.connect(self.registry)) as conn:
            conn.executescript((ROOT / 'schema.sql').read_text())
            conn.executemany('INSERT INTO devices(device_id) VALUES (?)',
                             [('example-a',), ('example-b',)])
            conn.commit()

    def sample(self, index, when=None, **changes):
        row = dict(sample_id=f'{index:032d}', sampled_utc=stamp(when or self.now),
                   cpu_frequency_ghz=2.5, source='linux_scaling_cur_freq',
                   logical_cpu_count=4, valid_cpu_count=4, quality='ok',
                   window_ms=0, error=None)
        row.update(changes)
        return row

    def seed(self, count, device='example-a', archived=1, start=0, received=None):
        # Insert the existing six-column schema directly, as an older installation.
        # 使用旧版六列表结构，验证无需迁移即可接收。
        received = received or self.now
        with closing(sqlite3.connect(self.registry)) as conn:
            for index in range(start, start + count):
                body = canonical(self.sample(index, received), received)
                conn.execute('INSERT INTO frequency_inbox VALUES (?,?,?,?,?,?)',
                             (device, self.sample(index)['sample_id'], stamp(received),
                              body, len(body.encode('utf-8')), archived))
            conn.commit()

    def ingest(self, rows, device='example-a', **kwargs):
        return receive(self.registry, device, rows, now=self.now, **kwargs)

    def counts(self):
        with closing(sqlite3.connect(self.registry)) as conn:
            return conn.execute('SELECT count(*),coalesce(sum(archived=0),0) FROM frequency_inbox').fetchone()

    def archive_all(self):
        with writer(self.archive, lambda p: Path(p)) as archive:
            if archive.execute('PRAGMA user_version').fetchone()[0] == 1:
                migrate(archive, 2, lambda: None)
            total = 0
            while True:
                count = drain(archive, self.registry, lambda: None, self.now)
                total += count
                if count < 120:
                    return total

    def test_http_new_sample_after_1440_archived_receipts_without_migration(self):
        self.seed(1440)
        with closing(sqlite3.connect(self.registry)) as conn:
            schema = conn.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall()
        # app initializes db on import, and db caches its configured path. Isolate
        # this import so the existing smoke suite keeps its own temporary DB.
        # 应用导入会初始化并缓存数据库路径，使用子进程避免污染其他测试。
        probe = '''
import json, sys
from pathlib import Path
from unittest.mock import patch
with patch('dotenv.load_dotenv'):
    import config
config.DATABASE_PATH = Path(sys.argv[1])
config.HEARTBEAT_TOKEN = 'synthetic-only'
import app
response = app.app.test_client().post('/api/telemetry/cpu-frequency',
    json={'device_id': 'example-a', 'samples': [json.loads(sys.argv[2])]},
    headers={'X-Heartbeat-Token': 'synthetic-only'})
print(json.dumps({'status': response.status_code, 'body': response.get_json()}))
'''
        result = subprocess.run([sys.executable, '-B', '-c', probe,
                                 str(self.registry), json.dumps(self.sample(2000))],
                                cwd=ROOT, check=True, capture_output=True, text=True, timeout=15)
        response = json.loads(result.stdout)
        self.assertEqual(response['status'], 200, response['body'])
        self.assertEqual(response['body']['accepted'], [self.sample(2000)['sample_id']])
        self.assertEqual(self.counts(), (1441, 1))
        with closing(sqlite3.connect(self.registry)) as conn:
            self.assertEqual(conn.execute('SELECT sql FROM sqlite_master ORDER BY name').fetchall(), schema)

    def test_1416_receipts_allow_whole_120_sample_backfill(self):
        self.seed(1416)
        batch = [self.sample(i) for i in range(2000, 2120)]
        self.assertEqual(len(self.ingest(batch)['accepted']), 120)
        self.assertEqual(len(self.ingest(batch)['duplicates']), 120)
        self.assertEqual(self.counts(), (1536, 120))

    def test_linux_1440_sample_backfill_then_retry_archives_once(self):
        self.seed(1440)
        path = self.root / 'client.json'
        backlog = [self.sample(2000 + i, self.now - timedelta(minutes=1439-i))
                   for i in range(1439)]
        linux.save(path, backlog)
        batch_sizes = []

        def transport(url, token, payload):
            batch_sizes.append(len(payload['samples']))
            return self.ingest(payload['samples'], payload['device_id'])

        latest = self.sample(3439)
        linux.run(path, 'example-a', 'https://example.invalid', 'synthetic-only',
                  latest, self.now, transport)
        self.assertEqual(batch_sizes, [120] * 12)
        self.assertEqual(json.loads(path.read_text()), [])
        self.assertEqual(self.counts(), (2880, 1440))
        self.assertEqual(self.archive_all(), 1440)
        for offset in range(0, 1440, 120):
            batch = (backlog + [latest])[offset:offset + 120]
            self.assertEqual(len(self.ingest(batch)['duplicates']), 120)
        self.assertEqual(self.archive_all(), 0)
        with closing(sqlite3.connect(self.archive)) as archive:
            self.assertEqual(archive.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0], 1440)

    def test_real_per_device_backlog_rejects_atomically_and_keeps_receipts(self):
        self.seed(1440)
        self.seed(1440, archived=0, start=2000)
        self.assertEqual(self.ingest([self.sample(2000)])['duplicates'], [self.sample(2000)['sample_id']])
        with self.assertRaisesRegex(TelemetryError, 'queue_full') as error:
            self.ingest([self.sample(0), self.sample(4000), self.sample(4001)])
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.counts(), (2880, 1440))
        self.assertEqual(self.ingest([self.sample(0)])['duplicates'], [self.sample(0)['sample_id']])

    def test_linux_503_keeps_original_sample_and_recovers_after_drain(self):
        self.seed(1440)
        self.seed(1440, archived=0, start=2000)
        path = self.root / 'client.json'
        first = self.sample(4000)

        def transport(url, token, payload):
            try:
                return self.ingest(payload['samples'])
            except TelemetryError as exc:
                raise HTTPError(url, exc.status, exc.code, {}, None) from None

        with self.assertRaises(HTTPError) as error:
            linux.run(path, 'example-a', 'https://example.invalid', 'synthetic-only',
                      first, self.now, transport)
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(json.loads(path.read_text()), [first])
        self.assertEqual(self.archive_all(), 1440)
        linux.run(path, 'example-a', 'https://example.invalid', 'synthetic-only',
                  self.sample(4001), self.now, transport)
        self.assertEqual(json.loads(path.read_text()), [])
        self.assertEqual(self.counts(), (2882, 2))

    def test_receipts_still_consume_total_byte_budget_without_eviction(self):
        self.seed(1440)
        with closing(sqlite3.connect(self.registry)) as conn:
            size = conn.execute('SELECT sum(payload_bytes) FROM frequency_inbox').fetchone()[0]
        sample = self.sample(2000)
        exact = size + len(canonical(sample, self.now).encode('utf-8'))
        with self.assertRaisesRegex(TelemetryError, 'queue_full'):
            self.ingest([sample], max_bytes=exact-1)
        self.assertEqual(self.counts(), (1440, 0))
        self.assertEqual(len(self.ingest([self.sample(0)], max_bytes=size)['duplicates']), 1)
        self.assertEqual(len(self.ingest([sample], max_bytes=exact)['accepted']), 1)

    def test_archived_conflict_rolls_back_new_samples_without_replacing_receipt(self):
        self.seed(1440)
        with self.assertRaisesRegex(TelemetryError, 'sample_conflict'):
            self.ingest([self.sample(2000), self.sample(0, cpu_frequency_ghz=3.0)])
        self.assertEqual(self.counts(), (1440, 0))
        self.assertEqual(len(self.ingest([self.sample(0)])['duplicates']), 1)

    def test_receipt_at_exact_24_hours_deduplicates_and_detects_conflict(self):
        cutoff = self.now - timedelta(hours=24)
        self.seed(1, received=cutoff)
        sample = self.sample(0, cutoff)
        self.assertEqual(self.ingest([sample])['duplicates'], [sample['sample_id']])
        with self.assertRaisesRegex(TelemetryError, 'sample_conflict'):
            self.ingest([dict(sample, cpu_frequency_ghz=3.0)])
        with closing(sqlite3.connect(self.registry)) as conn:
            self.assertEqual(conn.execute('SELECT received_utc FROM frequency_inbox').fetchone()[0], stamp(cutoff))

    def test_after_24_hours_expires_receipts_and_counts_only_unarchived_loss(self):
        expired = self.now - timedelta(hours=24, milliseconds=1)
        boundary = self.now - timedelta(hours=24)
        self.seed(1, received=expired)
        self.seed(1, archived=0, start=1, received=expired)
        self.seed(1, archived=0, start=2, received=boundary)
        result = self.ingest([self.sample(2000)])
        self.assertEqual(result['expired_unarchived'], 1)
        self.assertEqual(self.counts(), (2, 2))
        self.assertEqual(queue_status(self.registry)['expired_unarchived_total'], 1)
        with self.assertRaisesRegex(TelemetryError, 'sample_expired') as error:
            self.ingest([self.sample(0, expired)])
        self.assertEqual(error.exception.status, 422)

    def test_failed_capacity_check_rolls_back_expiration_too(self):
        self.seed(1, archived=0, received=self.now-timedelta(hours=25))
        self.seed(1, archived=0, start=1)
        with self.assertRaisesRegex(TelemetryError, 'queue_full'):
            self.ingest([self.sample(2000)], max_rows=1)
        self.assertEqual(self.counts(), (2, 2))
        self.assertEqual(queue_status(self.registry)['expired_unarchived_total'], 0)
        self.assertEqual(self.ingest([self.sample(2000)], max_rows=2)['expired_unarchived'], 1)

    def parallel_uploads(self, max_rows=14400):
        barrier = Barrier(2)
        batch = [self.sample(i) for i in range(2000, 2120)]

        def upload(device):
            barrier.wait(timeout=5)
            try:
                return self.ingest(batch, device, max_rows=max_rows)
            except TelemetryError as exc:
                return exc.code, exc.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(upload, ['example-a', 'example-b']))

    def test_parallel_devices_can_backfill_after_1440_receipts_each(self):
        for device in ['example-a', 'example-b']:
            self.seed(1440, device)
        for reply in self.parallel_uploads():
            self.assertIsInstance(reply, dict)
            self.assertEqual(len(reply['accepted']), 120)
        for reply in self.parallel_uploads():
            self.assertEqual(len(reply['duplicates']), 120)
        self.assertEqual(self.counts(), (3120, 240))
        with closing(sqlite3.connect(self.registry)) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_parallel_devices_cannot_overrun_global_pending_budget(self):
        for device in ['example-a', 'example-b']:
            self.seed(1440, device)
        replies = self.parallel_uploads(max_rows=120)
        self.assertEqual(sum(isinstance(reply, dict) for reply in replies), 1)
        self.assertIn(('queue_full', 503), replies)
        self.assertEqual(self.counts(), (3000, 120))

    def test_archive_ack_failure_replays_once_after_receipt_saturation(self):
        self.seed(1440)
        self.ingest([self.sample(2000)])
        with closing(sqlite3.connect(self.registry)) as conn:
            conn.execute("CREATE TRIGGER deny_ack BEFORE UPDATE OF archived ON frequency_inbox BEGIN SELECT RAISE(ABORT,'synthetic'); END")
            conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive_all()
        self.assertEqual(self.counts(), (1441, 1))
        with closing(sqlite3.connect(self.registry)) as conn:
            conn.execute('DROP TRIGGER deny_ack')
            conn.commit()
        self.assertEqual(self.archive_all(), 1)
        with closing(sqlite3.connect(self.archive)) as archive:
            self.assertEqual(archive.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0], 1)
        self.assertEqual(len(self.ingest([self.sample(2000)])['duplicates']), 1)

    def test_status_distinguishes_pending_limits_and_total_receipt_bytes(self):
        self.seed(1440)
        self.seed(2, archived=0, start=2000)
        status = queue_status(self.registry)
        self.assertEqual(status['pending'], 2)
        self.assertEqual(status['receipts'], 1440)
        self.assertEqual(status['max_pending_rows'], 14400)
        self.assertEqual(status['max_pending_rows_per_device'], 1440)
        self.assertEqual(status['max_payload_bytes'], 16*1024*1024)
        self.assertGreater(status['total_payload_bytes'], status['pending_payload_bytes'])
