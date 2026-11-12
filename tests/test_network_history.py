"""Synthetic, read-only network history query coverage / 合成网络历史查询。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from network_history import query, ROLES
from network_migration import migrate


class NetworkHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.db = sqlite3.connect(self.path/'archive.sqlite3')
        self.now = datetime(2026, 1, 31, 12, tzinfo=timezone.utc)
        self.roles = dict(system_id='system000000001', targets={r:'192.0.2.'+str(i+1) for i,r in enumerate(ROLES)})
        self.roles_path = self.path/'roles.json'
        self.roles_path.write_text(json.dumps(self.roles))

    def migrate(self):
        self.db.executescript('''PRAGMA user_version=2; CREATE TABLE samples(system_id,record_id,created_utc,created_raw,updated_raw,stats_json,archived_utc);
            CREATE TABLE checkpoints(system_id,created_utc); CREATE TABLE cpu_frequency_samples(device_id,sample_id,sampled_utc,payload,received_utc,archived_utc);''')
        migrate(self.db, lambda: None)
        for i, role in enumerate(ROLES):
            self.db.execute('INSERT INTO network_monitors VALUES (?,?,?,?,?,?,?,?)',
                (f'monitor{i:04d}',self.roles['system_id'],self.roles['targets'][role],'icmp',10,1,'{}',int(self.now.timestamp()*1000)))
        self.db.commit()

    def test_v2_empty_cards_and_reject_bounds(self):
        self.db.execute('PRAGMA user_version=2')
        result=query(self.db,str(self.roles_path),'1h',self.now)
        self.assertEqual(len(result['targets']),6)
        self.assertTrue(all(not target['rows'] for target in result['targets']))
        self.assertEqual(result['events'],[])
        with self.assertRaisesRegex(ValueError,'invalid_range'): query(self.db,str(self.roles_path),'180d',self.now)

    def test_minutes_daily_weighting_gaps_loss_events_and_limits(self):
        self.migrate()
        end=int(self.now.timestamp()*1000); minute=end-60_000
        # One zero-loss minute, one total-loss minute, and an absent minute.
        self.db.execute('INSERT INTO network_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('monitor0000','1m','record000001',minute,self.roles['system_id'],1000,3000,6000,3,3,'{}',end))
        self.db.execute('INSERT INTO network_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('monitor0000','1m','record000002',end-120_000,self.roles['system_id'],None,None,0,2,0,'{}',end))
        self.db.execute('INSERT INTO network_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            ('monitor0000','1m',end-86_400_000,2,10,8,16000,1000,3000,end-86_400_000,end-1))
        self.db.execute('INSERT INTO network_events VALUES (?,?,?,?,?,?,?,?,?)',
            ('event001','stream001','target_anomaly','monitor0000',end-3600000,end-3480000,None,None,'{}'))
        self.db.execute('INSERT INTO network_events VALUES (?,?,?,?,?,?,?,?,?)',
            ('event002','stream002','target_anomaly','monitor0000',end-7200000,end-7140000,end-3600000,end-3540000,'{}'))
        self.db.commit()
        hourly=query(self.db,str(self.roles_path),'1h',self.now)
        pts=hourly['targets'][0]['rows']
        self.assertEqual(len(pts),2)  # no synthetic gap point
        self.assertIsNone(pts[0]['rtt_ms'])  # all probes failed
        self.assertEqual(pts[0]['loss_pct'],100)
        self.assertAlmostEqual(pts[1]['rtt_ms'],2)
        self.assertEqual(pts[1]['loss_pct'],0)
        self.assertEqual(hourly['events'][0]['duration_ms'],3600000)
        self.assertIsNone(hourly['events'][0]['recovered'])
        daily=query(self.db,str(self.roles_path),'7d',self.now)
        self.assertEqual(daily['granularity'],'1d')
        self.assertAlmostEqual(daily['targets'][0]['rows'][0]['rtt_ms'],2)
        self.assertEqual(daily['targets'][0]['rows'][0]['loss_pct'],20)
        self.assertEqual(daily['events'][1]['duration_ms'],3600000)
        monthly=query(self.db,str(self.roles_path),'30d',self.now)
        self.assertEqual(daily['events'][0]['duration_ms'],monthly['events'][0]['duration_ms'])
        for key in ('24h','30d'):
            self.assertEqual(query(self.db,str(self.roles_path),key,self.now)['range'],key)


if __name__=='__main__': unittest.main()
