"""Export isolated Flask/SQLite responses for browser checks / 导出隔离浏览器样本。

Only synthetic RFC 5737 targets; never load .env, contact Beszel or open the HDD.
仅使用示例地址，不读取私有配置、不连接上游、不访问生产归档。
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from network_history import ROLES, RANGES
from network_migration import migrate


def export(directory):
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / 'archive.sqlite3'
    roles_path = directory / 'roles.json'
    roles = dict(system_id='preview-system0001', targets={r: '192.0.2.'+str(i+1) for i,r in enumerate(ROLES)})
    roles_path.write_text(json.dumps(roles))
    now = int(datetime.now(timezone.utc).timestamp()*1000)
    midnight = now//86_400_000*86_400_000
    with sqlite3.connect(archive) as conn:
        conn.executescript('''PRAGMA user_version=2;
            CREATE TABLE samples(system_id,record_id,created_utc,created_raw,updated_raw,stats_json,archived_utc);
            CREATE TABLE checkpoints(system_id,created_utc);
            CREATE TABLE cpu_frequency_samples(device_id,sample_id,sampled_utc,payload,received_utc,archived_utc);''')
        migrate(conn, lambda: None)
        for i, role in enumerate(ROLES):
            identity = 'previewmonitor%02d' % i
            conn.execute('INSERT INTO network_monitors VALUES (?,?,?,?,?,?,?,?)',
                         (identity,roles['system_id'],roles['targets'][role],'icmp',10,1,'{}',now))
            if role == 'endpoint_b':
                continue  # missing target / 缺测目标
            for age in range(1,1441):
                if age == 10:
                    continue  # real gap / 实际断点
                stamp = now-age*60_000
                total = 6 if age <= 60 else 12
                success = max(1,5-i) if age == 40 else total
                if i == 4 and age == 5:
                    success = 0  # all failed / 全丢包
                base = (i+1)*1000 if i < 4 else (i+1)*10_000
                rtt = base * (2 if age == 1 else 1 if age <= 60 else 2 if age <= 180 else
                              3 if age <= 360 else 4 if age <= 600 else 5)
                conn.execute('INSERT INTO network_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                             (identity,'1m','preview%02d%04d' % (i,age),stamp,roles['system_id'],
                              rtt if success else None,rtt if success else None,success*rtt,total,success,'{}',now))
            for day in range(31):
                stamp = midnight-day*86_400_000
                total, success = (12000,10000) if day > 7 else (6000,5000) if day else (120,120)
                rtt = base * (5 if day > 7 else 3 if day else 1)
                conn.execute('INSERT INTO network_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                             (identity,'1m',stamp,1000,total,success,success*rtt,rtt,rtt,stamp,stamp+60_000))
        conn.commit()
    env = dict(DATABASE_PATH=str(directory/'portal.sqlite3'), METRICS_ARCHIVE_PATH=str(archive),
               NETWORK_HISTORY_ROLES_FILE=str(roles_path))
    with patch.dict(os.environ,env,clear=True), patch('dotenv.load_dotenv'), \
         patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')):
        import app
        app.app.config['TESTING'] = True
        client = app.app.test_client()
        responses = {}
        with patch('metrics_archive.require_hdd',return_value=archive):
            for key in RANGES:
                url = '/api/history/v3/network?range='+key
                response = client.get(url)
                assert response.status_code == 200
                result = response.json
                assert result['targets'][0]['latest_sample']['loss_pct'] == 0
                assert round(result['targets'][0]['peak_loss_pct'],1) == 16.7
                responses[url] = dict(type='application/json',body=response.get_data(as_text=True))
            assert client.get('/api/history/v3/network?range=invalid').status_code == 400
        response = client.get('/')
        responses['/'] = dict(type='text/html',body=response.get_data(as_text=True))
        responses['/api/dashboard'] = dict(type='application/json',body=json.dumps(dict(status='ok',devices=[],sources={})))
        responses['/api/history'] = dict(type='application/json',body=json.dumps(dict(status='ok',devices=[])))
        for filename in ('style.css','dashboard.js','offline-seen.js','performance-history.js','endpoint-b.js'):
            response = client.get('/static/'+filename)
            responses['/static/'+filename] = dict(type=response.content_type,body=response.get_data(as_text=True))
            response.close()
        (directory/'responses.json').write_text(json.dumps(responses))
    print('Synthetic read-only Flask/SQLite fixture: seven ranges, weighted counts, gaps, 100% loss and 16.7% peak passed')


if __name__ == '__main__':
    export(Path(sys.argv[1]).resolve())
