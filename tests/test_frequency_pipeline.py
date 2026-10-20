"""Synthetic telemetry lifecycle; no live configuration / 全链路合成测试，不访问生产。"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from frequency import canonical, receive, drain, stamp, TelemetryError
from frequency_history import query
from frequency_migration import migrate
from metrics_archive import writer, ArchiveError, MountError, collect

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
sys.path.insert(0, str(ROOT/'clients'))
spec = importlib.util.spec_from_file_location('linux_frequency', ROOT/'clients/linux-frequency.py')
linux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linux)


def observation(index=1, when=NOW, **changes):
    row = dict(sample_id=f'{index:032d}', sampled_utc=stamp(when), cpu_frequency_ghz=2.5,
               source='linux_scaling_cur_freq', logical_cpu_count=4, valid_cpu_count=4,
               quality='ok', window_ms=0, error=None)
    row.update(changes)
    return row


class FrequencyPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='frequency-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = self.root/'registry.db'
        with closing(sqlite3.connect(self.registry)) as c:
            c.executescript((ROOT/'schema.sql').read_text())
            c.execute("INSERT INTO devices(device_id) VALUES ('example-device')")
            c.commit()
        self.archive = self.root/'archive.db'
        self.guard = lambda p: Path(p)

    def receive(self, rows=None, **kwargs):
        return receive(self.registry, 'example-device', rows or [observation()], now=NOW, **kwargs)

    def test_validate_numeric_and_quality(self):
        for value in [0, -1, True, '2', float('nan'), float('inf'), 21, None]:
            with self.subTest(value=value), self.assertRaises(TelemetryError):
                canonical(observation(cpu_frequency_ghz=value), NOW)
        self.assertEqual(json.loads(canonical(observation(cpu_frequency_ghz=0.1), NOW))['cpu_frequency_ghz'], 0.1)
        canonical(observation(quality='partial', valid_cpu_count=2, error='partial_read'), NOW)
        canonical(observation(quality='unavailable', valid_cpu_count=0, cpu_frequency_ghz=None, error='read_failed'), NOW)

    def test_invalid_structure_never_raises_unhandled_type_error(self):
        for key, value in [('source', []), ('quality', {}), ('error', []), ('valid_cpu_count', True), ('window_ms', -1), ('sampled_utc', 'yesterday'), ('sample_id', 'x')]:
            with self.subTest(key=key), self.assertRaises(TelemetryError):
                canonical(observation(**{key:value}), NOW)

    def test_timestamp_bounds(self):
        canonical(observation(when=NOW-timedelta(hours=24)), NOW)
        for when in [NOW-timedelta(hours=24, milliseconds=1), NOW+timedelta(minutes=6)]:
            with self.assertRaises(TelemetryError): canonical(observation(when=when), NOW)
        with self.assertRaises(TelemetryError): canonical(observation(sampled_utc='2026-10-19T12:00:00'), NOW)

    def test_dedup_conflict_and_atomic_batch(self):
        self.assertEqual(len(self.receive()['accepted']), 1)
        self.assertEqual(len(self.receive()['duplicates']), 1)
        with self.assertRaisesRegex(TelemetryError, 'sample_conflict'):
            self.receive([observation(2), observation(cpu_frequency_ghz=3)])
        with closing(sqlite3.connect(self.registry)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM frequency_inbox').fetchone()[0], 1)

    def test_unknown_identity_and_batch_limit(self):
        with self.assertRaisesRegex(TelemetryError, 'unknown_device'):
            receive(self.registry, 'unknown', [observation()], NOW)
        for rows in [[], [observation()]*121, {}]:
            with self.assertRaises(TelemetryError): receive(self.registry, 'example-device', rows, NOW)

    def test_row_and_byte_overflow_roll_back(self):
        for kwargs in [dict(max_rows=0),dict(max_bytes=1)]:
            with self.assertRaisesRegex(TelemetryError, 'queue_full'): self.receive(**kwargs)
        with closing(sqlite3.connect(self.registry)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM frequency_inbox').fetchone()[0],0)

    def test_queue_expiration_is_counted(self):
        self.receive()
        receive(self.registry, 'example-device', [observation(2, when=NOW+timedelta(hours=25))], NOW+timedelta(hours=25))
        with closing(sqlite3.connect(self.registry)) as c:
            self.assertEqual(c.execute('SELECT expired FROM frequency_queue_status').fetchone()[0],1)

    def test_migration_keeps_beszel_and_compatibility_reopen(self):
        with writer(self.archive,self.guard) as c:
            c.execute("INSERT INTO checkpoints VALUES ('example-system','2026-10-19T00:00:00.000Z')")
            c.commit()
            migrate(c,2,lambda:None)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],2)
        with writer(self.archive,self.guard) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM checkpoints').fetchone()[0],1)
            migrate(c,1,lambda:None)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_migration_mount_loss_rolls_back(self):
        with writer(self.archive,self.guard) as c:
            with self.assertRaises(MountError): migrate(c,2,Mock(side_effect=MountError('test')))
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='cpu_frequency_samples'").fetchone())

    def test_v1_drain_refuses_without_automatic_migration(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            with self.assertRaisesRegex(TelemetryError,'migration_required'): drain(c,self.registry,lambda:None,NOW)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)

    def test_replay_after_archive_commit_before_ack(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            self.assertEqual(drain(c,self.registry,lambda:None,NOW),1)
            with closing(sqlite3.connect(self.registry)) as inbox:
                inbox.execute('UPDATE frequency_inbox SET archived=0'); inbox.commit()
            self.assertEqual(drain(c,self.registry,lambda:None,NOW),1)
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],1)
            with self.assertRaises(ArchiveError): migrate(c,1,lambda:None)
        self.assertEqual(len(self.receive()['duplicates']),1)

    def test_mount_failure_leaves_inbox_pending(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            with self.assertRaises(MountError): drain(c,self.registry,Mock(side_effect=MountError('test')),NOW)
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],0)
        with closing(sqlite3.connect(self.registry)) as c:
            self.assertEqual(c.execute('SELECT archived FROM frequency_inbox').fetchone()[0],0)

    def test_concurrent_archive_writer_rejected(self):
        with writer(self.archive,self.guard):
            with self.assertRaises(ArchiveError):
                with writer(self.archive,self.guard): pass

    def test_registry_busy_returns_failure(self):
        with closing(sqlite3.connect(self.registry)) as c:
            c.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError): self.receive()

    def test_pagination_time_and_gaps(self):
        self.receive([observation(1),observation(2),observation(3, when=NOW+timedelta(minutes=1))])
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None); drain(c,self.registry,lambda:None,NOW)
            args=(c,'example-device',stamp(NOW),stamp(NOW+timedelta(minutes=1)))
            first=query(*args,limit=1)
            second=query(*args,after=first['next_cursor'],limit=1)
            self.assertEqual(first['points'][0]['sample_id'],observation(1)['sample_id'])
            self.assertEqual(second['points'][0]['sample_id'],observation(2)['sample_id'])
            self.assertIsNone(second['next_cursor'])
            with self.assertRaises(TelemetryError): query(c,'x',stamp(NOW),stamp(NOW+timedelta(days=181)))

    def test_linux_online_logical_average_and_partial(self):
        for i,value in enumerate(['1000000','3000000','nan']):
            p=self.root/f'cpu{i}'/'cpufreq'; p.mkdir(parents=True); (p/'scaling_cur_freq').write_text(value)
        (self.root/'cpu2'/'online').write_text('0')
        result=linux.sample(self.root,NOW)
        self.assertEqual((result['cpu_frequency_ghz'],result['logical_cpu_count'],result['quality']),(2,2,'ok'))
        (self.root/'cpu1'/'cpufreq/scaling_cur_freq').unlink()
        result=linux.sample(self.root,NOW)
        self.assertEqual((result['cpu_frequency_ghz'],result['valid_cpu_count'],result['quality']),(1,1,'partial'))

    def test_linux_unavailable_never_uses_maximum(self):
        p=self.root/'cpu0/cpufreq';p.mkdir(parents=True);(p/'cpuinfo_max_freq').write_text('9000000')
        result=linux.sample(self.root,NOW)
        self.assertIsNone(result['cpu_frequency_ghz']);self.assertEqual(result['quality'],'unavailable')

    def test_client_network_failure_preserves_then_retries(self):
        path=self.root/'client.json'
        with self.assertRaises(TimeoutError): linux.run(path,'example-device','https://example.invalid','test',observation(),NOW,Mock(side_effect=TimeoutError))
        self.assertEqual(len(json.loads(path.read_text())),1)
        sent=[]
        def ack(url,token,payload):
            sent.extend(payload['samples']);return {'accepted':[s['sample_id'] for s in payload['samples']], 'duplicates':[]}
        linux.run(path,'example-device','https://example.invalid','test',observation(2),NOW,ack)
        self.assertEqual(len(sent),2);self.assertEqual(json.loads(path.read_text()),[])

    def test_client_overflow_and_invalid_ack_keep_data(self):
        path=self.root/'client.json'
        with patch.object(linux,'MAX_ROWS',0),self.assertRaisesRegex(RuntimeError,'queue_full'):
            linux.run(path,'example-device','https://example.invalid','test',observation(),NOW)
        with self.assertRaisesRegex(RuntimeError,'acknowledgement'):
            linux.run(path,'example-device','https://example.invalid','test',observation(),NOW,lambda *a:{})
        self.assertEqual(len(json.loads(path.read_text())),1)

    def test_runner_frequency_before_beszel_auth_failure(self):
        spec=importlib.util.spec_from_file_location('archive_runner',ROOT/'tools/archive_metrics.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with patch('dotenv.load_dotenv'): config=importlib.import_module('config')
        self.receive()
        with writer(self.archive,self.guard) as c: migrate(c,2,lambda:None)
        with patch.dict('os.environ', {'METRICS_ARCHIVE_PATH':str(self.archive),'FREQUENCY_ARCHIVE_ENABLED':'true'}), \
             patch.object(runner,'require_hdd',side_effect=lambda p,*a:Path(p)), \
             patch.multiple(config,DATABASE_PATH=self.registry,BESZEL_TOKEN='',BESZEL_EMAIL='',BESZEL_PASSWORD=''):
            self.assertEqual(runner.main(now=NOW),1)
        with writer(self.archive,self.guard) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],1)

    def test_full_client_recovers_before_accepting_new_sample(self):
        path=self.root/'full.json'
        linux.save(path,[observation()])
        def ack(url,token,payload):
            return {'accepted':[s['sample_id'] for s in payload['samples']],'duplicates':[]}
        with patch.object(linux,'MAX_ROWS',1):
            linux.run(path,'example-device','https://example.invalid','test',observation(2),NOW,ack)
        self.assertEqual(json.loads(path.read_text()),[])

    def test_expired_client_reports_loss_without_retiming(self):
        path=self.root/'old.json'
        linux.save(path,[observation(when=NOW-timedelta(hours=25))])
        sent=[]
        def ack(url,token,payload):
            sent.extend(payload['samples']);return {'accepted':[s['sample_id'] for s in payload['samples']],'duplicates':[]}
        self.assertEqual(linux.run(path,'example-device','https://example.invalid','test',observation(2),NOW,ack),1)
        self.assertEqual([s['sample_id'] for s in sent],[observation(2)['sample_id']])

    def test_retention_boundary_keeps_exactly_180_days(self):
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            boundary=NOW-timedelta(days=180)
            for i,when in enumerate([boundary-timedelta(milliseconds=1),boundary]):
                body=json.dumps(observation(i,when=when))
                c.execute('INSERT INTO cpu_frequency_samples VALUES (?,?,?,?,?,?)',('example-device',str(i),stamp(when),body,stamp(NOW),stamp(NOW)))
            c.commit()
            drain(c,self.registry,lambda:None,NOW)
            self.assertEqual(c.execute('SELECT sampled_utc FROM cpu_frequency_samples').fetchall(),[(stamp(boundary),)])

    def test_archive_conflict_keeps_pending_and_original(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            c.execute('INSERT INTO cpu_frequency_samples VALUES (?,?,?,?,?,?)',('example-device',observation()['sample_id'],stamp(NOW),'{}',stamp(NOW),stamp(NOW)));c.commit()
            with self.assertRaisesRegex(TelemetryError,'archive_sample_conflict'): drain(c,self.registry,lambda:None,NOW)
            self.assertEqual(c.execute('SELECT payload FROM cpu_frequency_samples').fetchone()[0],'{}')
        with closing(sqlite3.connect(self.registry)) as c:
            self.assertEqual(c.execute('SELECT archived FROM frequency_inbox').fetchone()[0],0)

    def test_mount_loss_at_commit_rolls_back_rows(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            guard=Mock(side_effect=[None,MountError('synthetic')])
            with self.assertRaises(MountError):drain(c,self.registry,guard,NOW)
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],0)

    def test_registry_commit_failure_replays_archive(self):
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            with closing(sqlite3.connect(self.registry)) as inbox:
                inbox.execute("CREATE TRIGGER deny_ack BEFORE UPDATE OF archived ON frequency_inbox BEGIN SELECT RAISE(ABORT,'synthetic'); END");inbox.commit()
            with self.assertRaises(sqlite3.IntegrityError):drain(c,self.registry,lambda:None,NOW)
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],1)
            with closing(sqlite3.connect(self.registry)) as inbox:
                inbox.execute('DROP TRIGGER deny_ack');inbox.commit()
            self.assertEqual(drain(c,self.registry,lambda:None,NOW),1)
            self.assertEqual(c.execute('SELECT count(*) FROM cpu_frequency_samples').fetchone()[0],1)

    def test_migration_cli_backup_and_safe_downgrade(self):
        spec=importlib.util.spec_from_file_location('migration_runner',ROOT/'tools/migrate_metrics_archive.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        with writer(self.archive,self.guard) as c:
            c.execute("INSERT INTO checkpoints VALUES ('example-system',?)",(stamp(NOW),));c.commit()
        backup=self.root/'backup.db'
        args=['migrate','--database',str(self.archive),'--backup',str(backup),'--to','2']
        with patch.object(cli,'require_hdd',side_effect=lambda p,*a:Path(p)),patch.object(sys,'argv',args):
            self.assertEqual(cli.main(),0)
            self.assertEqual(cli.main(),1)  # existing backup must never be overwritten
        with closing(sqlite3.connect(backup)) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM checkpoints').fetchone()[0],1)
        with writer(self.archive,self.guard) as c:
            migrate(c,1,lambda:None)
            self.assertEqual(c.execute('SELECT count(*) FROM checkpoints').fetchone()[0],1)

    def test_per_device_inbox_limit(self):
        with closing(sqlite3.connect(self.registry)) as c:
            for i in range(1440):
                body=canonical(observation(i),NOW)
                c.execute('INSERT INTO frequency_inbox VALUES (?,?,?,?,?,1)',('example-device',observation(i)['sample_id'],stamp(NOW),body,len(body)))
            c.commit()
        with self.assertRaisesRegex(TelemetryError,'queue_full'):self.receive([observation(1441)])

    def test_shared_heartbeat_transport_headers_and_failure(self):
        import heartbeat_transport
        response=Mock()
        response.read.return_value=b'{"accepted":[]}'
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        with patch.object(heartbeat_transport.urllib.request,'urlopen',return_value=response) as opening:
            reply=heartbeat_transport.send_json('https://example.invalid/api/heartbeat','synthetic-test',{'device_id':'example-device'})
            self.assertEqual(reply,{'accepted':[]})
            request=opening.call_args.args[0]
            self.assertEqual(request.get_header('X-heartbeat-token'),'synthetic-test')
            self.assertEqual(json.loads(request.data),{'device_id':'example-device'})
        with patch.object(heartbeat_transport.urllib.request,'urlopen',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):heartbeat_transport.send_json('https://example.invalid','synthetic-test',{})

    def test_existing_linux_heartbeat_reuses_transport(self):
        spec=importlib.util.spec_from_file_location('linux_heartbeat',ROOT/'clients/linux-heartbeat.py')
        heartbeat=importlib.util.module_from_spec(spec);spec.loader.exec_module(heartbeat)
        with patch.dict('os.environ',{'HOMELAB_DEVICE_ID':'example-device','HOMELAB_HEARTBEAT_TOKEN':'synthetic-test','HOMELAB_PORTAL_URL':'https://example.invalid'}), \
             patch.object(heartbeat,'run_command',return_value=''), \
             patch.object(heartbeat,'send_json',return_value={}) as transport:
            heartbeat.send_heartbeat()
            self.assertEqual(transport.call_args.args[:2],('https://example.invalid/api/heartbeat','synthetic-test'))
            self.assertNotIn('samples',transport.call_args.args[2])

    def test_beszel_collection_still_works_on_v2(self):
        from test_metrics_archive import FakeClient, sample
        records=[sample(i) for i in range(1,4)]
        self.receive()
        with writer(self.archive,self.guard) as c:
            migrate(c,2,lambda:None)
            self.assertEqual(collect(c,FakeClient(records),now=NOW)['inserted'],3)
            before=c.execute('SELECT * FROM samples ORDER BY record_id').fetchall()
            drain(c,self.registry,lambda:None,NOW)
            self.assertEqual(collect(c,FakeClient(records),now=NOW)['inserted'],0)
            self.assertEqual(c.execute('SELECT * FROM samples ORDER BY record_id').fetchall(),before)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
