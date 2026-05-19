import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore

try:
    import openpyxl  # noqa: F401
except Exception:
    print('skip: openpyxl not installed')
    raise SystemExit(0)

with TemporaryDirectory() as td:
    db = Path(td) / 'e.sts'
    out = Path(td) / 'out.xlsx'
    s = STSStore(db)
    s.create_platform('AKINCI')
    s.write_users([{'name':'U1','yi_yd':'Yİ','active':True,'note':''}])
    s.write_components([
        ComponentDef(name='C1', platforms={'AKINCI': True}),
        ComponentDef(name='C2', platforms={'AKINCI': True}),
    ])
    ci = ContractInfo(no='K1', platform='AKINCI', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    systems = [SystemInfo(name='S1', components={'C1':3,'C2':2}), SystemInfo(name='S2', components={'C1':1})]
    deliveries = {
        'S1':[DeliveryInfo(name='Kabul 1', status='PLAN', acceptance_date='', note='', planned={'C1':2}, delivered={'C1':1}), DeliveryInfo(name='Kabul 2', status='PLAN', acceptance_date='', note='', planned={'C2':2}, delivered={'C2':2})],
        'S2':[DeliveryInfo(name='Kabul 1', status='PLAN', acceptance_date='', note='', planned={'C1':1}, delivered={'C1':0}), DeliveryInfo(name='Kabul 2', status='PLAN', acceptance_date='', note='', planned={'C1':0}, delivered={'C1':0})],
    }
    s.write_contract(ci, systems, deliveries)
    s.export_to_excel(out)
    assert out.exists() and out.stat().st_size > 0

    from openpyxl import load_workbook
    wb = load_workbook(out, read_only=True)
    assert 'Özet' in wb.sheetnames
    assert any('AKINCI' in n for n in wb.sheetnames)
    ws = wb[[n for n in wb.sheetnames if 'AKINCI' in n][0]]
    rows = list(ws.iter_rows(min_row=1, max_row=8, values_only=True))
    assert any((r and any('Sözleşme Türü' == str(x) for x in r if x is not None)) for r in rows)
    assert ws.max_row >= 4
    logs = s.list_logs(limit=100)
    assert any(x.get('action') == 'excel_exported' for x in logs)

print('ok')
