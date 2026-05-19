import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.app_models import ComponentDef, ContractInfo, DeliveryInfo, SystemInfo
from src.services.sts_store import STSStore

try:
    from openpyxl import load_workbook
except Exception:
    print('skip: openpyxl not installed')
    raise SystemExit(0)

with TemporaryDirectory() as td:
    db = Path(td) / 'e.sts'
    s = STSStore(db)
    s.create_platform('AKINCI')
    s.create_platform('TB2')
    s.write_users([{'name':'U1','yi_yd':'Yİ','active':True,'note':''}])
    s.write_components([
        ComponentDef(name='C1', platforms={'AKINCI': True, 'TB2': True}),
        ComponentDef(name='C2', platforms={'AKINCI': True, 'TB2': False}),
    ])

    ci1 = ContractInfo(no='K1', platform='AKINCI', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    ci2 = ContractInfo(no='K2', platform='TB2', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    systems = [SystemInfo(name='S1', components={'C1':3,'C2':2}), SystemInfo(name='S2', components={'C1':1})]
    deliveries = {'S1':[DeliveryInfo(name='Kabul 1', status='PLAN', acceptance_date='', note='', planned={'C1':2}, delivered={'C1':1})], 'S2':[DeliveryInfo(name='Kabul 1', status='PLAN', acceptance_date='', note='', planned={'C1':1}, delivered={'C1':0})]}
    s.write_contract(ci1, systems, deliveries)
    s.write_contract(ci2, systems, deliveries)

    progress = []
    out1 = Path(td)/'full.xlsx'
    s.export_to_excel(out1, options={'scope':'all'}, progress_cb=lambda p,m: progress.append((p,m)))
    assert out1.exists() and len(progress) >= 3
    wb1 = load_workbook(out1, read_only=True)
    assert 'Özet' in wb1.sheetnames
    assert any('AKINCI' in x for x in wb1.sheetnames) and any('TB2' in x for x in wb1.sheetnames)

    out2 = Path(td)/'selected.xlsx'
    s.export_to_excel(out2, options={'scope':'selected','platforms':['AKINCI']})
    wb2 = load_workbook(out2, read_only=True)
    assert any('AKINCI' in x for x in wb2.sheetnames)
    assert not any('TB2' in x for x in wb2.sheetnames)

    out3 = Path(td)/'summary.xlsx'
    s.export_to_excel(out3, options={'scope':'summary_only'})
    wb3 = load_workbook(out3, read_only=True)
    assert wb3.sheetnames == ['Özet']

    out4 = Path(td)/'nocomp.xlsx'
    s.export_to_excel(out4, options={'scope':'selected','platforms':['AKINCI'],'include_component_columns':False})
    wb4 = load_workbook(out4, read_only=True)
    ws4 = wb4[[n for n in wb4.sheetnames if 'AKINCI' in n][0]]
    header_row = list(ws4.iter_rows(min_row=3, max_row=3, values_only=True))[0]
    assert not any((isinstance(x,str) and 'Sözleşme Adedi' in x) for x in header_row if x is not None)

    logs = s.list_logs(limit=200)
    ex = [x for x in logs if x.get('action') == 'excel_exported']
    assert ex
    assert 'options' in (ex[0].get('payload_json') or '')

print('ok')
