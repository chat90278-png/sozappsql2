import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo, TagDef
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    dbp = Path(td) / 'persist.sts'
    s = STSStore(dbp)
    s.create_platform('P1')
    s.write_users([{'name':'U1','yi_yd':'Yİ','active':True,'note':'n'}])
    s.write_components([ComponentDef(name='C1', platforms={'P1': True})])
    s.write_tag_snapshot([TagDef(name='T1')], {})
    ci = ContractInfo(no='K1', platform='P1', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    s.write_contract(ci, [SystemInfo(name='SYS', components={'C1': 2})], {'SYS': [DeliveryInfo(name='D1', status='PLAN', acceptance_date='', note='', planned={'C1':2}, delivered={'C1':1})]})

    s2 = STSStore(dbp)
    assert 'P1' in s2.platform_names()
    assert any(u['name']=='U1' for u in s2.load_users(active_only=False))
    assert any(c.name=='C1' for c in s2.load_components())
    assert any(t.name=='T1' for t in s2.load_tags())
    idx = s2.build_contract_index(); assert any(i.get('no')=='K1' for i in idx)
    _ci, systems, deliveries = s2.load_contract_structure('P1','K1')
    assert systems and deliveries and 'SYS' in deliveries
    s2.delete_contract('P1','K1')

    s3 = STSStore(dbp)
    idx2 = s3.build_contract_index()
    assert not any(i.get('no')=='K1' for i in idx2)

print('ok')
