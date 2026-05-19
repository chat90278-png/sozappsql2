import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore

with TemporaryDirectory() as td:
    p = Path(td)/'noexcel.sts'
    s = STSStore(p)
    s.create_platform('P1')
    ci = ContractInfo(no='K1', platform='P1', user='', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    s.write_contract(ci,[SystemInfo(name='S1',components={})],{'S1':[DeliveryInfo(name='D1',status='PLAN',acceptance_date='',note='',planned={},delivered={})]})
    s.build_contract_index()
    s.load_contract_structure('P1','K1')
print('ok')
