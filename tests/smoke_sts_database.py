import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.sts_database import STSDatabase

with TemporaryDirectory() as td:
    db = STSDatabase(Path(td)/'db.sts')
    db.add_log(action='x', entity_type='contract', entity_key='k', message='m', payload={'a':1}, actor='u', entity_id=5, platform='AKINCI', contract_no='K1', before={'b':1}, after={'b':2})
    rows = db.list_logs(limit=10)
    assert rows and rows[0].get('action') == 'x'
    assert rows[0].get('before_json') and rows[0].get('after_json') and rows[0].get('payload_json')
    assert db.list_logs(search='AKINCI')
    assert db.list_logs(platform='AKINCI')
    cols = {r[1] for r in db.conn.execute('PRAGMA table_info(activity_logs)').fetchall()}
    for c in ['actor','entity_id','platform','contract_no','before_json','after_json','payload_json']:
        assert c in cols
print('ok')
