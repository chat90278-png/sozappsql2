from __future__ import annotations
import time
from collections import defaultdict
from pathlib import Path


def _safe_sheet_name(name: str, used: set[str]) -> str:
    bad = ':\\/?*[]'
    n = ''.join('_' if ch in bad else ch for ch in str(name or '').strip())[:31] or 'Platform'
    base = n
    i = 2
    while n in used:
        suf = f'_{i}'
        n = (base[:31-len(suf)] + suf)
        i += 1
    used.add(n)
    return n


def export_sts_to_excel(db, output_path, options=None, progress_cb=None):
    opts = {
        "scope": "all", "platforms": None, "include_summary": True,
        "include_contract_rows": True, "include_system_rows": True,
        "include_delivery_rows": True, "include_component_columns": True,
        "include_tags": True,
    }
    if isinstance(options, dict):
        opts.update(options)
    if progress_cb:
        progress_cb(0, "Excel oluşturma başlatılıyor...")
    try:
        from openpyxl import Workbook
    except Exception as exc:
        raise RuntimeError('Excel aktarımı için openpyxl kurulu olmalıdır.') from exc

    t0 = time.time(); conn = db.conn; out = Path(output_path); wb = Workbook(write_only=True)
    comp_names = [r[0] for r in conn.execute("SELECT name FROM components WHERE active=1 ORDER BY name").fetchall()]
    all_platforms = [r[0] for r in conn.execute("SELECT name FROM platforms WHERE is_active=1 ORDER BY sort_order,name").fetchall()]
    scope = str(opts.get('scope') or 'all')
    if scope == 'selected':
        platforms = [p for p in (opts.get('platforms') or []) if p in all_platforms]
    elif scope == 'active':
        platforms = [p for p in (opts.get('platforms') or []) if p in all_platforms][:1]
    elif scope == 'summary_only':
        platforms = []
        opts['include_summary'] = True
    else:
        platforms = list(all_platforms)

    c_count = conn.execute('SELECT COUNT(*) FROM contracts').fetchone()[0]
    s_count = conn.execute('SELECT COUNT(*) FROM systems').fetchone()[0]
    d_count = conn.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]
    l_count = conn.execute('SELECT COUNT(*) FROM activity_logs').fetchone()[0]

    if opts.get('include_summary', True):
        if progress_cb: progress_cb(5, "Özet hazırlanıyor...")
        summary = wb.create_sheet('Özet')
        summary.append(['Öğe', 'Değer'])
        summary.append(['Oluşturma zamanı', time.strftime('%Y-%m-%d %H:%M:%S')])
        summary.append(['Kaynak STS', str(getattr(db, 'path', ''))])
        summary.append(['Platform sayısı', len(platforms) if platforms else len(all_platforms)])
        summary.append(['Sözleşme sayısı', c_count]); summary.append(['Sistem sayısı', s_count])
        summary.append(['Kabul/Teslimat sayısı', d_count]); summary.append(['Bileşen sayısı', len(comp_names)])
        summary.append(['Log sayısı', l_count]); summary.append([])
        summary.append(['Platform', 'Sözleşme Sayısı', 'Sistem Sayısı', 'Teslimat Sayısı'])
        for p in (platforms if platforms else all_platforms):
            p_contracts = conn.execute('SELECT COUNT(*) FROM contracts WHERE platform=?', (p,)).fetchone()[0]
            p_systems = conn.execute('SELECT COUNT(*) FROM systems s JOIN contracts c ON c.id=s.contract_id WHERE c.platform=?', (p,)).fetchone()[0]
            p_delivs = conn.execute('SELECT COUNT(*) FROM deliveries d JOIN contracts c ON c.id=d.contract_id WHERE c.platform=?', (p,)).fetchone()[0]
            summary.append([p, p_contracts, p_systems, p_delivs])

    if progress_cb: progress_cb(10, "Platformlar hazırlanıyor...")
    used = {'Özet'}
    main_headers = ['Sözleşme Türü','Sözleşme No','Kullanıcı','Yİ/YD','Durum','İmza Tarihi','T0 Tarihi','T0 Ay','Termin Tarihi','Kabul Tarihi','İçerik / Not']
    if opts.get('include_tags', True): main_headers.append('Etiketler')
    main_headers.extend(['Sistem','Kabul / Teslimat','Satır Türü'])
    comp_used = comp_names if opts.get('include_component_columns', True) else []

    for pi,p in enumerate(platforms):
        if progress_cb:
            pct = 10 + int((pi / max(1, len(platforms))) * 80)
            progress_cb(pct, f"{p} platformu yazılıyor...")
        ws = wb.create_sheet(_safe_sheet_name(p, used))
        ws.append([f'Platform: {p}']); ws.append([])
        headers = list(main_headers)
        for c in comp_used: headers.extend([f'{c} Sözleşme Adedi', f'{c} Teslim Edilen', f'{c} Kalan'])
        ws.append(headers)

        contracts = conn.execute("SELECT id,contract_type,contract_no,user_name,yi_yd,status,signed_date,t0_date,t0_months,completion_date,acceptance_date,note,content FROM contracts WHERE platform=? ORDER BY id", (p,)).fetchall()
        for c in contracts:
            cid = c[0]
            tag_names = [r[0] for r in conn.execute('SELECT tag_name FROM contract_tags WHERE contract_id=? ORDER BY tag_name', (cid,)).fetchall()]
            tag_txt = ', '.join(tag_names)
            base = [c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10], c[12] or c[11]]
            if opts.get('include_tags', True): base.append(tag_txt)
            systems = conn.execute('SELECT id,name FROM systems WHERE contract_id=? ORDER BY sort_order,id', (cid,)).fetchall()
            if opts.get('include_contract_rows', True):
                sys_qty = defaultdict(float); sys_del = defaultdict(float)
                for r in conn.execute('SELECT sc.component_name,SUM(sc.qty) FROM system_components sc JOIN systems s ON s.id=sc.system_id WHERE s.contract_id=? GROUP BY sc.component_name', (cid,)).fetchall(): sys_qty[r[0]] = float(r[1] or 0)
                for r in conn.execute('SELECT dc.component_name,SUM(dc.delivered) FROM delivery_components dc JOIN deliveries d ON d.id=dc.delivery_id WHERE d.contract_id=? GROUP BY dc.component_name', (cid,)).fetchall(): sys_del[r[0]] = float(r[1] or 0)
                row = base + ['GENEL', 'Ana Sözleşme Toplamı', 'Sözleşme Toplamı']
                for n in comp_used:
                    q = sys_qty.get(n, 0.0); d = sys_del.get(n, 0.0); row.extend([q,d,q-d])
                ws.append(row)

            for sid, sname in systems:
                qmap = {r[0]: float(r[1] or 0) for r in conn.execute('SELECT component_name,qty FROM system_components WHERE system_id=?', (sid,)).fetchall()}
                dmap = {r[0]: float(r[1] or 0) for r in conn.execute('SELECT dc.component_name,SUM(dc.delivered) FROM delivery_components dc JOIN deliveries d ON d.id=dc.delivery_id WHERE d.system_id=? GROUP BY dc.component_name', (sid,)).fetchall()}
                if opts.get('include_system_rows', True):
                    row = base + [sname, 'Sistem Toplamı', 'Sistem Toplamı']
                    for n in comp_used:
                        q = qmap.get(n, 0.0); d = dmap.get(n, 0.0); row.extend([q,d,q-d])
                    ws.append(row)
                if opts.get('include_delivery_rows', True):
                    dels = conn.execute('SELECT id,name FROM deliveries WHERE contract_id=? AND system_name=? ORDER BY sort_order,id', (cid, sname)).fetchall()
                    for did, dname in dels:
                        mp = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in conn.execute('SELECT component_name,planned,delivered FROM delivery_components WHERE delivery_id=?', (did,)).fetchall()}
                        row = base + [sname, dname, 'Kabul']
                        for n in comp_used:
                            pl, dl = mp.get(n, (0.0, 0.0)); row.extend([pl,dl,pl-dl])
                        ws.append(row)

    if progress_cb: progress_cb(95, "Excel dosyası kaydediliyor...")
    wb.save(str(out))
    duration = round(time.time() - t0, 3)
    if progress_cb: progress_cb(100, "Excel dosyası oluşturuldu.")
    return {'output_path': str(out), 'platform_count': len(platforms), 'contract_count': c_count, 'duration_sec': duration}
