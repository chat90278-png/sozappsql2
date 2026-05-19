import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.sts_database import STSDatabase

with TemporaryDirectory() as td:
    p = Path(td) / 'legacy.sts'
    conn = sqlite3.connect(p)
    conn.execute('CREATE TABLE activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, action TEXT, entity_type TEXT, entity_key TEXT)')
    conn.commit(); conn.close()

    db = STSDatabase(p)
    cols = {r[1] for r in db.conn.execute('PRAGMA table_info(activity_logs)').fetchall()}
    for c in ['platform', 'contract_no', 'actor', 'entity_id', 'before_json', 'after_json', 'payload_json']:
        assert c in cols
    idx = {r[1] for r in db.conn.execute('PRAGMA index_list(activity_logs)').fetchall()}
    assert 'idx_logs_platform' in idx

    db.add_log(action='legacy_test', platform='AKINCI', contract_no='1', payload={'x': 1})
    rows = db.list_logs(platform='AKINCI')
    assert rows and rows[0].get('platform') == 'AKINCI'

print('ok')
