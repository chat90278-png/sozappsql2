import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    db = Path(td)/'m.sts'
    bak = Path(td)/'m_backup.sts'
    s = STSStore(db)
    s.create_platform('AKINCI')
    s.write_users([{'name':'U1','yi_yd':'Yİ','active':True,'note':''}])
    s.write_components([ComponentDef(name='C1', platforms={'AKINCI': True})])
    ci = ContractInfo(no='K1', platform='AKINCI', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    s.write_contract(ci, [], {})

    stats = s.database_stats()
    assert 'table_counts' in stats
    assert stats['table_counts'].get('contracts', 0) >= 1
    assert 'staff' in stats['table_counts']
    assert 'sqlite_sequence' not in stats['table_counts']
    s.db.conn.execute('CREATE TABLE custom_management_table(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
    s.db.conn.execute("INSERT INTO custom_management_table(name) VALUES('visible')")
    s.db.conn.commit()
    refreshed_stats = s.database_stats()
    assert refreshed_stats['table_counts'].get('custom_management_table') == 1
    assert s.preview_table('staff') == []
    assert s.preview_table('custom_management_table')[0]['name'] == 'visible'
    assert any(x.lower() == 'ok' for x in s.integrity_check())
    assert s.foreign_key_check() == []
    b = s.backup_database(bak)
    assert Path(b['target_path']).exists() and b['size_bytes'] > 0
    assert s.optimize().get('ok') is True
    v = s.vacuum()
    assert 'before_bytes' in v and 'after_bytes' in v

print('ok')
