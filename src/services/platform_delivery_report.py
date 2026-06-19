from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import quote_sheetname

from src.services.sts_database import now_iso

NAVY = "123E7C"
LIGHT_BLUE = "DCEAF8"
COLORS = ["F2DF92", "26A9CF", "D8D8D8", "F6C7D8", "F4A261", "B7E4B2", "D6BCFA", "FFD6A5"]
STATUSES = ["", "Hazırlıkta", "Süreci Devam Ediyor", "Kontrol Bekliyor", "Teslim Edildi", "Gecikmede"]

@dataclass
class ReportLine:
    user_id: int; user: str; contract_id: int; contract: str; delivery_date: str
    component_id: int; component: str; quantity: float; serial_no: str; serial_key: str
    internal_location: str = ""; note: str = ""; delivery_location: str = ""

@dataclass
class SummaryRow:
    user_id: int; user: str; contract_id: int; contract: str; delivery_date: str
    status: str = ""; description: str = ""

@dataclass
class ReportData:
    platform_id: int; platform: str; locations: list[str]
    summary: list[SummaryRow] = field(default_factory=list)
    details: "OrderedDict[tuple[int,int], list[ReportLine]]" = field(default_factory=OrderedDict)


def _fmt_qty(v: Any) -> float:
    try: return float(v or 0)
    except Exception: return 0.0


def load_report_data(store, platform_name: str, user_id: int | None = None, contract_id: int | None = None) -> ReportData:
    conn = store.db.conn
    prow = conn.execute("SELECT id,name FROM platforms WHERE name=?", (platform_name,)).fetchone()
    if not prow:
        return ReportData(0, platform_name or "Platform", [])
    pid = int(prow["id"])
    locations = [str(r[0]) for r in conn.execute("SELECT name FROM internal_locations WHERE COALESCE(is_active,1)=1 ORDER BY sort_order,name").fetchall()]
    params: list[Any] = [pid]
    clauses = ["cp.platform_id=?"]
    if user_id:
        clauses.append("d.delivery_user_id=?"); params.append(int(user_id))
    if contract_id:
        clauses.append("c.id=?"); params.append(int(contract_id))
    rows = conn.execute(f"""
        SELECT c.id AS contract_id, c.contract_no, COALESCE(d.planned_acceptance_date,d.acceptance_date,c.acceptance_date,c.completion_date,'') AS delivery_date,
               u.id AS user_id, COALESCE(u.name,'Tanımsız') AS user_name,
               comp.id AS component_id, comp.name AS component_name, dc.planned, dc.delivered,
               CASE WHEN NULLIF(TRIM(COALESCE(dcu.identifier,'')), '') IS NOT NULL THEN TRIM(dcu.identifier) ELSE 'TBD' END AS serial_no,
               CASE WHEN NULLIF(TRIM(COALESCE(dcu.identifier,'')), '') IS NOT NULL THEN TRIM(dcu.identifier) ELSE 'DC-' || dc.id END AS serial_key,
               COALESCE(pdl.internal_location,'') AS saved_location, COALESCE(pdl.note,'') AS saved_note, COALESCE(pdl.delivery_location,'') AS saved_delivery_location,
               COALESCE(pds.status,'') AS saved_status, COALESCE(pds.description,'') AS saved_description
        FROM deliveries d
        JOIN contracts c ON c.id=d.contract_id
        JOIN contract_platforms cp ON cp.contract_id=c.id
        LEFT JOIN users u ON u.id=d.delivery_user_id
        JOIN delivery_components dc ON dc.delivery_id=d.id
        JOIN components comp ON comp.id=dc.component_id
        LEFT JOIN delivery_component_units dcu ON dcu.delivery_component_id=dc.id
        LEFT JOIN platform_delivery_report_summary pds ON pds.platform_id=cp.platform_id AND pds.user_id=u.id AND pds.contract_id=c.id
        LEFT JOIN platform_delivery_report_lines pdl ON pdl.platform_id=cp.platform_id AND pdl.user_id=u.id AND pdl.contract_id=c.id AND pdl.component_id=comp.id AND pdl.serial_key=CASE WHEN NULLIF(TRIM(COALESCE(dcu.identifier,'')), '') IS NOT NULL THEN TRIM(dcu.identifier) ELSE 'DC-' || dc.id END
        WHERE {' AND '.join(clauses)}
        ORDER BY u.name COLLATE NOCASE, c.contract_no, comp.name COLLATE NOCASE, dcu.slot_no, d.id
    """, params).fetchall()
    data = ReportData(pid, str(prow["name"]), locations)
    seen = set()
    for r in rows:
        uid = int(r["user_id"] or 0); cid = int(r["contract_id"] or 0)
        key = (uid, cid)
        if key not in seen:
            seen.add(key)
            data.summary.append(SummaryRow(uid, str(r["user_name"] or "Tanımsız"), cid, str(r["contract_no"] or "-"), str(r["delivery_date"] or ""), str(r["saved_status"] or ""), str(r["saved_description"] or "")))
            data.details[key] = []
        qty = _fmt_qty(r["planned"] if r["planned"] is not None else r["delivered"])
        data.details[key].append(ReportLine(uid, str(r["user_name"] or "Tanımsız"), cid, str(r["contract_no"] or "-"), str(r["delivery_date"] or ""), int(r["component_id"] or 0), str(r["component_name"] or "-"), qty, str(r["serial_no"] or "TBD"), str(r["serial_key"] or r["serial_no"] or "TBD"), str(r["saved_location"] or ""), str(r["saved_note"] or ""), str(r["saved_delivery_location"] or "")))
    return data


def save_report_data(store, data: ReportData, summary_rows: list[dict], line_rows: list[dict]) -> None:
    conn = store.db.conn; ts = now_iso()
    with store.db.tx():
        for r in summary_rows:
            conn.execute("""INSERT INTO platform_delivery_report_summary(platform_id,user_id,contract_id,status,description,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(platform_id,user_id,contract_id) DO UPDATE SET status=excluded.status,description=excluded.description,updated_at=excluded.updated_at""",
            (data.platform_id, int(r['user_id']), int(r['contract_id']), r.get('status',''), r.get('description',''), ts, ts))
        for r in line_rows:
            serial_key = str(r.get('serial_key') or r.get('serial_no') or 'TBD').strip() or 'TBD'
            serial_no = str(r.get('serial_no') or serial_key).strip() or serial_key
            conn.execute("""INSERT INTO platform_delivery_report_lines(platform_id,user_id,contract_id,component_id,serial_no,serial_key,internal_location,note,delivery_location,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform_id,user_id,contract_id,component_id,serial_key) DO UPDATE SET serial_no=excluded.serial_no,internal_location=excluded.internal_location,note=excluded.note,delivery_location=excluded.delivery_location,updated_at=excluded.updated_at""",
            (data.platform_id, int(r['user_id']), int(r['contract_id']), int(r['component_id']), serial_no, serial_key, r.get('internal_location',''), r.get('note',''), r.get('delivery_location',''), ts, ts))


def safe_sheet_title(name: str, used: set[str] | None = None) -> str:
    bad = '[]:*?/\\'
    base = ''.join('_' if c in bad else c for c in str(name or 'Sayfa')).strip() or 'Sayfa'
    used = used if used is not None else set()
    title = base[:31]
    if title not in used:
        used.add(title)
        return title
    counter = 2
    while True:
        suffix = f" ({counter})"
        title = f"{base[:31-len(suffix)]}{suffix}"
        if title not in used:
            used.add(title)
            return title
        counter += 1


def export_report_to_excel(data: ReportData, path: str | Path) -> Path:
    wb = Workbook(); used_sheet_names: set[str] = set(); ws = wb.active; ws.title = safe_sheet_title(f"{data.platform} Teslimat Durumu", used_sheet_names); ws.sheet_properties.tabColor = "E11D48"
    thin = Side(style="thin", color="000000"); border = Border(left=thin,right=thin,top=thin,bottom=thin)
    head = PatternFill("solid", fgColor=NAVY); light = PatternFill("solid", fgColor=LIGHT_BLUE)
    ws.merge_cells("A1:E1"); ws["A1"] = f"{data.platform} TESLİMAT DURUMU"; ws["A1"].fill=head; ws["A1"].font=Font(color="FFFFFF", bold=True); ws["A1"].alignment=Alignment(horizontal="center")
    headers = ["Kullanıcı", "Sözleşme Adı veya Numarası", "Teslimat Tarihi", "Durum", "Açıklama"]
    for c,h in enumerate(headers,1):
        cell=ws.cell(2,c,h); cell.fill=head; cell.font=Font(color="FFFFFF", bold=True); cell.alignment=Alignment(horizontal="center"); cell.border=border
    sheet_names = {key: safe_sheet_title(f"{rows[0].user} Teslimat Durumu", used_sheet_names) for key, rows in data.details.items() if rows}
    for r_idx, row in enumerate(data.summary,3):
        vals=[f"{row.user} ↗", row.contract, row.delivery_date, row.status, row.description]
        for c,v in enumerate(vals,1):
            cell=ws.cell(r_idx,c,v); cell.fill=light; cell.border=border; cell.alignment=Alignment(horizontal="center" if c<5 else "left", vertical="center")
        if (row.user_id,row.contract_id) in sheet_names:
            ws.cell(r_idx,1).hyperlink = f"#{quote_sheetname(sheet_names[(row.user_id,row.contract_id)])}!A1"
            ws.cell(r_idx,1).style = "Hyperlink"
    for w, width in zip("ABCDE", [24,30,18,24,50]): ws.column_dimensions[w].width = width
    for key, lines in data.details.items():
        if not lines: continue
        ws = wb.create_sheet(sheet_names[key]); ws.sheet_properties.tabColor = "22C55E"
        user = lines[0].user; date = lines[0].delivery_date
        ws.merge_cells("A1:E1"); ws["A1"] = f"{user}\nTESLİMAT DURUMU"; ws["A1"].fill=head; ws["A1"].font=Font(color="FFFFFF", bold=True); ws["A1"].alignment=Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws["F1"] = f"TESLİMAT TARİHİ\n({date or 'TBD'})"; ws["F1"].fill=head; ws["F1"].font=Font(color="FFFFFF", bold=True); ws["F1"].alignment=Alignment(horizontal="center", wrap_text=True)
        for c,h in enumerate(["ANA SİSTEM","MİKTAR","KUYRUK NO / SERİ NO","LOKASYON","NOT","TESLİM EDİLECEK LOKASYON"],1):
            cell=ws.cell(2,c,h); cell.fill=head; cell.font=Font(color="FFFFFF", bold=True); cell.border=border; cell.alignment=Alignment(horizontal="center")
        comp_color = {}
        for idx, line in enumerate(lines,3):
            comp_color.setdefault(line.component, COLORS[len(comp_color)%len(COLORS)])
            fill=PatternFill("solid", fgColor=comp_color[line.component])
            for c,v in enumerate([line.component, line.quantity, line.serial_no, line.internal_location, line.note, line.delivery_location],1):
                cell=ws.cell(idx,c,v); cell.fill=fill; cell.border=border; cell.alignment=Alignment(horizontal="center" if c<5 else "left", vertical="center")
        for w,width in zip("ABCDEF", [22,12,28,22,44,36]): ws.column_dimensions[w].width=width
    wb.save(path)
    return Path(path)
