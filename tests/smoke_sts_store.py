import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from tempfile import TemporaryDirectory
from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo, TagDef
from src.services.sts_store import STSStore
with TemporaryDirectory() as td:
 s=STSStore(Path(td)/'b.sts'); s.create_platform('P1'); s.write_users([{'name':'U1','yi_yd':'Yİ','active':True,'note':''}]); s.write_components([ComponentDef(name='C1',platforms={'P1':True})]); s.write_tag_snapshot([TagDef(name='T1')],{}); ci=ContractInfo(no='K1',platform='P1',user='U1',yi_yd='Yİ',contract_type='Ana Sözleşme',signature_date='',t0_date='',t0_months=0,completion_date=''); s.write_contract(ci,[SystemInfo(name='S1',components={'C1':1})],{'S1':[DeliveryInfo(name='D1',status='PLAN',acceptance_date='',note='',planned={'C1':2},delivered={'C1':1})]}); assert s.build_contract_index(); s.save_contract_tags('P1','K1','Ana Sözleşme',['T1']); assert s.load_contract_tags('P1','K1','Ana Sözleşme'); s.set_platform_logo_bytes('P1',b'x'); assert s.get_platform_logo_bytes('P1')==b'x'; s.delete_contract('P1','K1');
print('ok')
