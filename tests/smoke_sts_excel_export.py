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


def rgb_endswith(cell, suffix):
    value = getattr(cell.fill.fgColor, 'rgb', None) or ''
    return str(value).upper().endswith(suffix)


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

    ci1 = ContractInfo(no='K1', platform='AKINCI', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='2026-01-01', t0_date='2026-01-02', t0_months=3, completion_date='2026-04-02')
    ci2 = ContractInfo(no='K2', platform='TB2', user='U1', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    systems = [SystemInfo(name='S1', components={'C1':3,'C2':2}), SystemInfo(name='S2', components={'C1':1})]
    deliveries = {
        'S1':[DeliveryInfo(name='Kabul 1', status='Devam Ediyor', acceptance_date='', note='N1', planned={'C1':2,'C2':2}, delivered={'C1':1,'C2':2})],
        'S2':[DeliveryInfo(name='Kabul 2', status='Tamamlandı', acceptance_date='2026-03-01', note='', planned={'C1':1}, delivered={'C1':1})],
    }
    s.write_contract(ci1, systems, deliveries)
    s.write_contract(ci2, systems, deliveries)

    progress = []
    out1 = Path(td)/'full.xlsx'
    s.export_to_excel(out1, options={'scope':'all'}, progress_cb=lambda p,m: progress.append((p,m)))
    assert out1.exists() and len(progress) >= 3
    wb1 = load_workbook(out1)
    assert 'Özet' in wb1.sheetnames
    assert 'AKINCI' in wb1.sheetnames and 'TB2' in wb1.sheetnames

    ws = wb1['AKINCI']
    expected_base_headers = [
        'Sözleşme No', 'Sözleşme Türü', 'Sistem Adı', 'Kabul Adı', 'Kullanıcı', 'Yİ/YD',
        'Durum', 'İmza Tarihi', 'T0 Tarihi', 'T0 Ay', 'Termin Tarihi', 'Kabul Tarihi',
        'Etiketler', 'Not',
    ]
    header_row = [cell.value for cell in ws[1]]
    assert header_row[:14] == expected_base_headers
    assert header_row[14:] == [
        'C1 Teslim Edilecek', 'C1 Teslim Edilen', 'C1 Kalan',
        'C2 Teslim Edilecek', 'C2 Teslim Edilen', 'C2 Kalan',
    ]
    assert ws.max_row == 3  # her kabul/teslimat ayrı satır
    assert [ws.cell(row=i, column=4).value for i in range(2, 4)] == ['Kabul 1', 'Kabul 2']
    assert ws.cell(row=2, column=17).value == 1  # C1 kalan = 2 - 1, formülsüz sayı
    assert ws.cell(row=2, column=20).value == 0  # C2 kalan = 2 - 2

    assert rgb_endswith(ws['A1'], '0D2B55')
    assert ws['A1'].font.bold is True
    assert str(ws['A1'].font.color.rgb).upper().endswith('FFFFFF')
    assert ws.row_dimensions[1].height == 22
    assert ws.freeze_panes == 'A2'
    assert ws.auto_filter.ref == f'A1:T{ws.max_row}'
    assert rgb_endswith(ws['Q2'], 'FFF2CC')
    assert rgb_endswith(ws['T2'], 'FFFFFF')
    assert rgb_endswith(ws['G2'], 'DDEEFF')
    assert rgb_endswith(ws['G3'], 'C6EFCE')
    assert 'A2:A3' in {str(rng) for rng in ws.merged_cells.ranges}
    assert 'B2:B3' in {str(rng) for rng in ws.merged_cells.ranges}

    ws_tb2 = wb1['TB2']
    tb2_headers = [cell.value for cell in ws_tb2[1]]
    assert tb2_headers[14:] == ['C1 Teslim Edilecek', 'C1 Teslim Edilen', 'C1 Kalan']

    out2 = Path(td)/'selected.xlsx'
    s.export_to_excel(out2, options={'scope':'selected','platforms':['AKINCI']})
    wb2 = load_workbook(out2, read_only=True)
    assert 'AKINCI' in wb2.sheetnames
    assert 'TB2' not in wb2.sheetnames

    out3 = Path(td)/'summary.xlsx'
    s.export_to_excel(out3, options={'scope':'summary_only'})
    wb3 = load_workbook(out3, read_only=True)
    assert wb3.sheetnames == ['Özet']

    logs = s.list_logs(limit=200)
    ex = [x for x in logs if x.get('action') == 'excel_exported']
    assert ex
    assert 'options' in (ex[0].get('payload_json') or '')

print('ok')
