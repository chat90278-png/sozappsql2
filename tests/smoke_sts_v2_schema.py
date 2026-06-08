import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    store = STSStore(Path(td) / 'v2.sts')
    store.create_platform('AKINCI')
    store.write_users([{'name': 'U1', 'yi_yd': 'Yİ', 'active': True, 'note': ''}])
    store.write_components([
        ComponentDef(name='C1', platforms={'AKINCI': True}),
        ComponentDef(name='C2', platforms={'AKINCI': True}),
        ComponentDef(name='ZERO', platforms={'AKINCI': True}),
    ])
    ci = ContractInfo(no='K1', platform='AKINCI', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    systems = [SystemInfo(name='S1', components={'C1': 3, 'ZERO': 0})]
    deliveries = {'S1': [DeliveryInfo(name='D1', status='PLAN', acceptance_date='', note='', delivery_user='U1', planned={'C1': 2, 'ZERO': 0}, delivered={'C1': 1, 'C2': 4, 'ZERO': 0})]}
    store.write_contract(ci, systems, deliveries)

    conn = store.db.conn
    contract = conn.execute('SELECT platform_id FROM contracts').fetchone()
    assert contract['platform_id'] == store.get_platform_id('AKINCI')
    assert 'user_id' not in {row[1] for row in conn.execute('PRAGMA table_info(contracts)')}
    assert conn.execute('SELECT COUNT(*) FROM contract_users WHERE user_id=?', (store.get_user_id('U1'),)).fetchone()[0] == 1
    assert {r[0] for r in conn.execute('SELECT c.name FROM system_components sc JOIN components c ON c.id=sc.component_id')} == {'C1'}
    assert {r[0] for r in conn.execute('SELECT c.name FROM delivery_components dc JOIN components c ON c.id=dc.component_id')} == {'C1', 'C2'}
    assert conn.execute("SELECT dc.planned,dc.delivered FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE c.name='C2'").fetchone()[:] == (0.0, 4.0)
    assert conn.execute('SELECT system_id FROM deliveries').fetchone()[0] is not None
    assert 'delivery_user_id' not in {row[1] for row in conn.execute('PRAGMA table_info(systems)')}
    assert conn.execute('SELECT delivery_user_id FROM deliveries').fetchone()[0] == store.get_user_id('U1')

    loaded_ci, loaded_systems, loaded_deliveries = store.load_contract_structure('AKINCI', 'K1')
    assert loaded_ci.platform == 'AKINCI' and loaded_ci.user == 'U1'
    assert loaded_systems[0].components == {'C1': 3.0}
    assert loaded_deliveries['S1'][0].delivered == {'C1': 1.0, 'C2': 4.0}
    assert loaded_deliveries['S1'][0].delivery_user == 'U1'
    assert conn.execute('PRAGMA foreign_key_check').fetchall() == []

print('ok')
