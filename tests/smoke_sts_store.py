import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.app_models import ComponentDef, ContractInfo, TagDef
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    p = Path(td)/'s.sts'
    s = STSStore(p)
    s.create_platform('AKINCI')
    s.set_platform_logo_bytes('AKINCI', b'test-logo', ext='png')
    assert s.get_platform_logo_bytes('AKINCI') == b'test-logo'
    s.write_users([{'name':'Serhat','yi_yd':'Yİ','active':True,'note':''}], actor='admin')
    s.write_components([ComponentDef(name='GÖVDE', platforms={'AKINCI':True})], actor='admin')
    s.upsert_tag_def(TagDef(name='Deneme'),)
    ci = ContractInfo(no='K1',platform='AKINCI',user='Serhat',yi_yd='Yİ',contract_type='Ana Sözleşme',signature_date='',t0_date='',t0_months=0,completion_date='')
    s.write_contract(ci, [], {})
    s.save_contract_tags('AKINCI','K1','Ana Sözleşme',['Deneme', 'Deneme', {'name': 'Deneme'}])
    assigned = s.load_contract_tags('AKINCI','K1','Ana Sözleşme')
    assert len(assigned) == 1 and assigned[0]['name'] == 'Deneme'
    contract_id = s._find_contract_id('AKINCI','K1','Ana Sözleşme')
    assert s.db.conn.execute('SELECT COUNT(*) FROM contract_tags WHERE contract_id=?', (contract_id,)).fetchone()[0] == 1
    s.delete_contract('AKINCI','K1')
    logs = s.list_logs(limit=100)
    assert logs
    actions = {x.get('action') for x in logs}
    assert 'platform_created' in actions
    assert 'platform_logo_updated' in actions
    assert 'users_updated' in actions
    assert 'components_updated' in actions
    assert 'tag_upserted' in actions
    assert ('contract_created' in actions) or ('contract_updated' in actions)
    assert 'contract_tags_updated' in actions
    assert 'contract_deleted' in actions
    assert s.list_logs(search='AKINCI')
    assert s.list_logs(platform='AKINCI')
print('ok')
