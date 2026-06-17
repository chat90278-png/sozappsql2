from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Optional

EXCEL_REQUIRED_MESSAGE = "Bu raporun PivotTable / PivotChart / Dilimleyici özellikleri için Microsoft Excel kurulu olmalıdır."
REVISION = "R006"
VISIBLE_SHEETS = ["Dashboard", "Teslimat Veri Girişi", "Tahmini Teslimat Takvimi", "REV Takip"]
HIDDEN_SHEETS = ["Pivot Kaynak", "Pivot Ozet", "Grafik Kaynak", "Parametreler"]
SOURCE_HEADERS = [
    "Platform", "Sözleşme", "Sözleşme Sahibi", "Teslim Kullanıcısı", "Yİ/YD", "Teslimat", "Tarih", "Yıl",
    "Seviye", "Parça No", "Parça", "Sözleşme Adeti", "Teslim Edilen", "Kalan", "Konfigürasyon Tipi", "Opsiyon / Not", "Durum",
]

ALLOWED_ENTITY_TYPES = {"contract", "contracts", "delivery", "deliveries", "acceptance", "term", "calendar"}
ALLOWED_ACTION_KEYWORDS = {"create", "created", "update", "updated", "delete", "deleted", "delivery", "contract", "acceptance", "teslim", "sözleşme", "sozlesme", "termin", "takvim"}
BLOCKED_KEYWORDS = {"yoğun test log kaydı", "test log", "stress", "bulk", "dummy", "seed", "sql_query_executed"}
FIELD_LABELS = {
    "planned_acceptance_date": "Tahmini Teslimat Tarihi",
    "acceptance_date": "Gerçek Teslim/Kabul Tarihi",
    "delivery_user_id": "Teslim Kullanıcısı",
    "planned": "Planlanan Miktar",
    "delivered": "Teslim Edilen Miktar",
    "status": "Durum",
    "note": "Not",
    "contract_no": "Sözleşme No",
    "yi_yd": "Yİ/YD",
    "configuration_type": "Konfigürasyon Tipi",
    "config_type": "Konfigürasyon Tipi",
    "option": "Opsiyon",
}


class ExcelComUnavailableError(RuntimeError):
    """Raised when pywin32 or Microsoft Excel COM automation is unavailable."""


def _conn_from_store(store: object) -> Optional[sqlite3.Connection]:
    db = getattr(store, "db", None)
    conn = getattr(db, "conn", None)
    return conn if conn is not None else getattr(store, "conn", None)


def extract_year_from_date_text(value: object) -> Optional[int]:
    text = str(value or "").strip()
    match = re.search(r"(?<!\d)(19\d{2}|20\d{2}|21\d{2})(?!\d)", text)
    return int(match.group(1)) if match else None


def normalize_report_date_display(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("/", "-").replace(".", "-").upper()
    parts = [p.strip() for p in text.split("-") if p.strip()]
    if len(parts) != 3:
        year = extract_year_from_date_text(text)
        return f"TBD-TBD-{year}" if year else text

    def is_year(part: str) -> bool:
        return bool(re.fullmatch(r"(19\d{2}|20\d{2}|21\d{2})", part))

    def two_digit(part: str) -> str:
        return part.zfill(2) if part.isdigit() and len(part) <= 2 else part

    if is_year(parts[0]):
        year, month, day = parts
        return f"{'TBD' if day == 'TBD' else two_digit(day)}-{'TBD' if month == 'TBD' else two_digit(month)}-{year}"
    if is_year(parts[2]):
        day, month, year = parts
        return f"{'TBD' if day == 'TBD' else two_digit(day)}-{'TBD' if month == 'TBD' else two_digit(month)}-{year}"
    return text


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_amount(value: object) -> int | float:
    number = _safe_float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _payload_value(text: str, *keys: str) -> str:
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _json_summary(text: str) -> str:
    if not text:
        return ""
    try:
        value = json.loads(text)
    except Exception:
        return str(text)[:120]
    if isinstance(value, dict):
        for key in ("field", "name", "column", "value", "old", "new", "message"):
            if value.get(key) not in (None, ""):
                return str(value.get(key))[:120]
        return ", ".join(str(k) for k in list(value.keys())[:4])
    return str(value)[:120]


def _safe_sheet_name(value: str) -> str:
    text = re.sub(r"[\\/*?:\[\]]+", "_", str(value or "Rapor")).strip()[:31]
    return text or "Rapor"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü_.-]+", "_", str(value or "Rapor")).strip("_") or "Rapor"


def contract_owner_text(conn: sqlite3.Connection, contract_id: int) -> str:
    rows = conn.execute(
        """
        SELECT u.name
        FROM contract_users cu
        JOIN users u ON u.id = cu.user_id
        WHERE cu.contract_id=?
        ORDER BY u.name
        """,
        (int(contract_id),),
    ).fetchall()
    return ", ".join(str(row[0] or "").strip() for row in rows if str(row[0] or "").strip())


def _matches_filters(row: dict[str, Any], filters: Optional[dict[str, Any]]) -> bool:
    if not filters:
        return True
    start_year = filters.get("start_year")
    end_year = filters.get("end_year")
    if start_year and end_year:
        year = row.get("Yıl")
        if not year or not (int(start_year) <= int(year) <= int(end_year)):
            return False
    checks = [
        ("platform", "Platform", "Tümü"),
        ("yi_yd", "Yİ/YD", "Tümü"),
        ("user", "Teslim Kullanıcısı", "Tümü"),
        ("status", "Durum", "Tümü"),
    ]
    for filter_key, row_key, all_value in checks:
        value = filters.get(filter_key)
        if value and value != all_value and str(row.get(row_key) or "") != str(value):
            return False
    owner = filters.get("owner")
    if owner and owner != "Tümü":
        owners = [part.strip() for part in str(row.get("Sözleşme Sahibi") or "").split(",")]
        if str(owner) not in owners:
            return False
    contract = filters.get("contract")
    if contract and contract != "Tüm seçili sözleşmeler" and str(row.get("Sözleşme") or "") != str(contract):
        return False
    return True


def load_delivery_schedule_rows(store: object, filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    conn = _conn_from_store(store)
    if conn is None:
        return []
    rows = conn.execute(
        """
        SELECT p.name AS platform_name, c.id AS contract_id, c.contract_no, c.yi_yd AS contract_yi_yd,
               c.status AS contract_status, c.note AS contract_note, c.payload_json AS contract_payload_json,
               s.name AS system_name, d.id AS delivery_id, d.name AS delivery_name, d.status AS delivery_status,
               d.planned_acceptance_date, d.acceptance_date, d.note AS delivery_note,
               d.payload_json AS delivery_payload_json, du.name AS delivery_user_name,
               du.yi_yd AS delivery_user_yi_yd, comp.name AS component_name, dc.planned, dc.delivered
        FROM deliveries d
        JOIN contracts c ON c.id = d.contract_id
        LEFT JOIN platforms p ON p.id = c.platform_id
        LEFT JOIN systems s ON s.id = d.system_id
        LEFT JOIN users du ON du.id = d.delivery_user_id
        JOIN delivery_components dc ON dc.delivery_id = d.id
        JOIN components comp ON comp.id = dc.component_id
        ORDER BY p.name, c.contract_no, d.sort_order, d.id, comp.name
        """
    ).fetchall()
    owner_cache: dict[int, str] = {}
    result: list[dict[str, Any]] = []
    for item in rows:
        contract_id = int(item["contract_id"] or 0)
        if contract_id not in owner_cache:
            owner_cache[contract_id] = contract_owner_text(conn, contract_id)
        planned = _safe_float(item["planned"])
        delivered = _safe_float(item["delivered"])
        remaining = max(planned - delivered, 0.0)
        date_text = normalize_report_date_display(item["planned_acceptance_date"] or item["acceptance_date"] or "")
        year = extract_year_from_date_text(date_text)
        delivery_payload = item["delivery_payload_json"] if "delivery_payload_json" in item.keys() else ""
        contract_payload = item["contract_payload_json"] if "contract_payload_json" in item.keys() else ""
        row = {
            "Platform": str(item["platform_name"] or "Tanımsız"),
            "Sözleşme": str(item["contract_no"] or "-"),
            "Sözleşme Sahibi": owner_cache.get(contract_id) or "-",
            "Teslim Kullanıcısı": str(item["delivery_user_name"] or "Tanımsız"),
            "Yİ/YD": str(item["delivery_user_yi_yd"] or item["contract_yi_yd"] or "-"),
            "Teslimat": str(item["delivery_name"] or "-"),
            "Tarih": date_text,
            "Yıl": year or "",
            "Seviye": "1",
            "Parça No": "",
            "Parça": str(item["component_name"] or "-"),
            "Sözleşme Adeti": _fmt_amount(remaining),
            "Teslim Edilen": _fmt_amount(delivered),
            "Kalan": _fmt_amount(remaining),
            "Konfigürasyon Tipi": _payload_value(delivery_payload, "configuration_type", "config_type", "konfigurasyon_tipi") or _payload_value(contract_payload, "configuration_type", "config_type", "konfigurasyon_tipi"),
            "Opsiyon / Not": str(item["delivery_note"] or item["contract_note"] or ""),
            "Durum": str(item["delivery_status"] or item["contract_status"] or "-"),
        }
        if _matches_filters(row, filters):
            result.append(row)
    return result



def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    try:
        return {key: row[key] for key in row.keys()}
    except Exception:
        return {}


def _json_dict(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text) if isinstance(text, str) else text
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _readable_field_name(value: Any) -> str:
    field = str(value or "").strip()
    if not field or len(field) <= 1:
        return ""
    return FIELD_LABELS.get(field, field.replace("_", " ").strip().title())


def _technical_entity_key(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(re.fullmatch(r"(contract|contracts|delivery|deliveries|acceptance|log|row):?\d+", text) or re.fullmatch(r"[a-z_]+:\d+", text))


def _extract_revision_parts(row: dict[str, Any]) -> tuple[str, str, str]:
    before = _json_dict(row.get("before_json"))
    after = _json_dict(row.get("after_json"))
    payload = _json_dict(row.get("payload_json"))
    field = payload.get("field") or payload.get("column") or payload.get("name")
    if not field and len(before) == 1 and len(after) == 1:
        before_key = next(iter(before.keys()))
        after_key = next(iter(after.keys()))
        if before_key == after_key:
            field = before_key
    old_value = payload.get("old") if payload.get("old") is not None else payload.get("before")
    new_value = payload.get("new") if payload.get("new") is not None else payload.get("after")
    if field and old_value is None and field in before:
        old_value = before.get(field)
    if field and new_value is None and field in after:
        new_value = after.get(field)
    if old_value is None and len(before) == 1:
        old_value = next(iter(before.values()))
    if new_value is None and len(after) == 1:
        new_value = next(iter(after.values()))
    return _readable_field_name(field), "" if old_value is None else str(old_value), "" if new_value is None else str(new_value)


def is_meaningful_revision_log(row: dict) -> bool:
    data = _as_dict(row)
    action = str(data.get("action") or "").strip().lower()
    message = str(data.get("message") or "").strip().lower()
    source = str(data.get("source") or "").strip().lower()
    entity_type = str(data.get("entity_type") or "").strip().lower()
    entity_key = str(data.get("entity_key") or "").strip().lower()
    combined = " ".join([action, message, source, entity_type, entity_key])
    if "sql terminal" in source:
        return False
    if any(keyword in combined for keyword in BLOCKED_KEYWORDS):
        return False
    allowed = entity_type in ALLOWED_ENTITY_TYPES or any(keyword in combined for keyword in ALLOWED_ACTION_KEYWORDS)
    if not allowed:
        return False
    field, old_value, new_value = _extract_revision_parts(data)
    has_json = any(str(data.get(key) or "").strip() not in {"", "{}", "[]", "null"} for key in ("before_json", "after_json", "payload_json"))
    meaningful_message = len(message) >= 8 and not _technical_entity_key(message)
    if not has_json and not meaningful_message:
        return False
    if not field and not old_value and not new_value and not meaningful_message:
        return False
    return True


def _revision_log_to_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    field, old_value, new_value = _extract_revision_parts(row)
    entity_key = "" if _technical_entity_key(row.get("entity_key")) else str(row.get("entity_key") or "")
    return {
        "revision": f"R{index:03d}",
        "date": str(row.get("created_at") or ""),
        "user": str(row.get("actor") or "-"),
        "contract": str(row.get("contract_no") or "-"),
        "delivery": entity_key or "-",
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "description": str(row.get("message") or ""),
    }


def load_meaningful_revision_logs(store: object, limit: int = 200) -> list[dict[str, Any]]:
    conn = _conn_from_store(store)
    if conn is None:
        return []
    rows = conn.execute(
        """
        SELECT l.*
        FROM activity_logs l
        ORDER BY l.created_at DESC
        LIMIT ?
        """,
        (max(int(limit or 200) * 5, int(limit or 200)),),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        data = _as_dict(row)
        if is_meaningful_revision_log(data):
            result.append(_revision_log_to_row(data, len(result) + 1))
        if len(result) >= int(limit or 200):
            break
    return result

def load_activity_rows(store: object) -> list[list[Any]]:
    return [
        [
            log["revision"], log["date"], log["user"], log["contract"], log["delivery"],
            log["field"], log["old_value"], log["new_value"], log["description"],
        ]
        for log in load_meaningful_revision_logs(store, limit=200)
    ]


def suggested_output_filename(rows: list[dict[str, Any]], created_at: Optional[date] = None) -> str:
    created_at = created_at or date.today()
    platforms = sorted({str(row.get("Platform") or "") for row in rows if row.get("Platform")})
    platform = platforms[0] if len(platforms) == 1 else "Coklu_Platform"
    return f"{_safe_filename(platform)}_Tahmini_Teslimat_Takvimi_R006_{created_at:%Y_%m_%d}.xlsx"


def _progress(progress_cb: Optional[Callable[[int, str], None]], value: int, message: str) -> None:
    if progress_cb:
        progress_cb(value, message)


def _ensure_excel():
    try:
        import pythoncom  # type: ignore
        import win32com.client as win32  # type: ignore
    except Exception as exc:
        raise ExcelComUnavailableError(EXCEL_REQUIRED_MESSAGE) from exc
    try:
        pythoncom.CoInitialize()
        excel = win32.DispatchEx("Excel.Application")
    except Exception as exc:
        raise ExcelComUnavailableError(EXCEL_REQUIRED_MESSAGE) from exc
    return excel


def _write_matrix(ws, rows: list[dict[str, Any]], report_date: str) -> None:
    users = sorted({str(row["Teslim Kullanıcısı"]) for row in rows})
    user_dates = {user: sorted({str(row["Tarih"]) for row in rows if row["Teslim Kullanıcısı"] == user and row["Tarih"]}) for user in users}
    headers = ["Seviye", "Parça Numarası", "Teslimat Zamanı"] + users + ["TOPLAM"]
    ws.Cells(1, 1).Value = report_date
    ws.Cells(2, 1).Value = f"REV:{REVISION[-3:]}"
    ws.Cells(2, 4).Value = "Teslimat Adı:"
    for col, header in enumerate(headers, start=1):
        ws.Cells(4, col).Value = header
        if 4 <= col < 4 + len(users):
            ws.Cells(5, col).Value = ", ".join(user_dates.get(header, [])[:2])
    by_part: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_part[str(row["Parça"])][str(row["Teslim Kullanıcısı"])] += _safe_float(row["Sözleşme Adeti"])
        if row.get("Tarih"):
            dates[str(row["Parça"])].add(str(row["Tarih"]))
    r = 6
    for part in sorted(by_part):
        ws.Cells(r, 1).Value = "1"
        ws.Cells(r, 2).Value = ""
        ws.Cells(r, 3).Value = ", ".join(sorted(dates[part])[:3])
        total = 0.0
        for idx, user in enumerate(users, start=4):
            value = by_part[part].get(user, 0.0)
            total += value
            ws.Cells(r, idx).Value = _fmt_amount(value)
        ws.Cells(r, 4 + len(users)).Value = _fmt_amount(total)
        r += 1
    _format_table(ws, 4, 1, max(r - 1, 5), len(headers), header_rows=2)


def _format_table(ws, first_row: int, first_col: int, last_row: int, last_col: int, header_rows: int = 1) -> None:
    navy = 0x79360B
    light = 0xFFF4E8
    black = 0x000000
    rng = ws.Range(ws.Cells(first_row, first_col), ws.Cells(last_row, last_col))
    rng.Borders.LineStyle = 1
    rng.Borders.Color = black
    for row in range(first_row, first_row + header_rows):
        header = ws.Range(ws.Cells(row, first_col), ws.Cells(row, last_col))
        header.Interior.Color = navy
        header.Font.Color = 0xFFFFFF
        header.Font.Bold = True
    for row in range(first_row + header_rows, last_row + 1):
        if (row - first_row) % 2 == 0:
            ws.Range(ws.Cells(row, first_col), ws.Cells(row, last_col)).Interior.Color = light
    ws.Columns.AutoFit()


def _write_delivery_entry(ws, rows: list[dict[str, Any]], report_date: str, platform_title: str) -> None:
    headers = ["PARÇA NUMARASI", "KULLANICI ADI", "PARÇA ADI", "MİKTAR", "İHA", "TESLİMAT ZAMANI", "TESLİMAT ZAMANI", "TESLİMAT ADI", "Yİ/YD", "YIL", "SÖZLEŞME ADI", "Konfigürasyon Tipi", "Opsiyon / Not"]
    ws.Cells(1, 1).Value = report_date
    ws.Cells(2, 1).Value = f"REV:{REVISION[-3:]}"
    ws.Cells(2, 4).Value = f"{platform_title} Tahmini Teslimat Takvimi"
    for col, header in enumerate(headers, start=1):
        ws.Cells(4, col).Value = header
    r = 5
    last_user = None
    for row in sorted(rows, key=lambda item: (str(item["Teslim Kullanıcısı"]), str(item["Sözleşme"]), str(item["Parça"]))):
        user = str(row["Teslim Kullanıcısı"])
        if user != last_user:
            ws.Cells(r, 1).Value = user
            ws.Range(ws.Cells(r, 1), ws.Cells(r, len(headers))).Merge()
            ws.Range(ws.Cells(r, 1), ws.Cells(r, len(headers))).Interior.Color = 0xFCE4D6
            ws.Range(ws.Cells(r, 1), ws.Cells(r, len(headers))).Font.Bold = True
            r += 1
            last_user = user
        values = ["", user, row["Parça"], row["Sözleşme Adeti"], "", row["Tarih"], row["Tarih"], row["Teslimat"], row["Yİ/YD"], row["Yıl"], row["Sözleşme"], row["Konfigürasyon Tipi"], row["Opsiyon / Not"]]
        for col, value in enumerate(values, start=1):
            ws.Cells(r, col).Value = value
        r += 1
    _format_table(ws, 4, 1, max(r - 1, 4), len(headers))


def _write_source_sheet(ws, rows: list[dict[str, Any]]) -> None:
    for col, header in enumerate(SOURCE_HEADERS, start=1):
        ws.Cells(1, col).Value = header
    for r, row in enumerate(rows, start=2):
        for c, header in enumerate(SOURCE_HEADERS, start=1):
            ws.Cells(r, c).Value = row.get(header, "")
    _format_table(ws, 1, 1, max(len(rows) + 1, 1), len(SOURCE_HEADERS))


def _write_rev_sheet(ws, activity_rows: list[list[Any]]) -> None:
    headers = ["Revizyon Bilgisi", "Tarih", "Kullanıcı", "Sözleşme", "Teslimat", "Alan", "Eski Değer", "Yeni Değer", "Açıklama"]
    for col, header in enumerate(headers, start=1):
        ws.Cells(1, col).Value = header
    for r, row in enumerate(activity_rows, start=2):
        for c, value in enumerate(row, start=1):
            ws.Cells(r, c).Value = value
    _format_table(ws, 1, 1, max(len(activity_rows) + 1, 1), len(headers))


def _build_dashboard(wb, ws, source_range: str, rows: list[dict[str, Any]], platform_title: str, report_date: str):
    xl_database = 1
    xl_row_field = 1
    xl_column_field = 2
    xl_page_field = 3
    xl_sum = -4157
    xl_column_clustered = 51
    xl_bar_clustered = 57
    xl_doughnut = -4120
    xl_line = 4
    ws.Range("A1:N1").Merge()
    ws.Range("A1").Value = f"{platform_title} · Tahmini Teslimat Takvimi"
    ws.Range("A1").Interior.Color = 0x79360B
    ws.Range("A1").Font.Color = 0xFFFFFF
    ws.Range("A1").Font.Bold = True
    ws.Range("A1").Font.Size = 18
    ws.Range("A2").Value = f"Rapor Tarihi: {report_date}    Revizyon: {REVISION}    Değer Türü: Sözleşme Adeti / Teslim Edilecek"

    total = sum(_safe_float(row["Sözleşme Adeti"]) for row in rows)
    users = len({row["Teslim Kullanıcısı"] for row in rows})
    contracts = len({row["Sözleşme"] for row in rows})
    risk = sum(1 for row in rows if _safe_float(row["Kalan"]) > 0 and "tamam" not in str(row["Durum"]).lower())
    for idx, (label, value) in enumerate((("SÖZLEŞME ADETİ", total), ("TESLİM KULLANICISI", users), ("SÖZLEŞME", contracts), ("RİSKLİ SATIR", risk)), start=1):
        col = 1 + (idx - 1) * 3
        box = ws.Range(ws.Cells(4, col), ws.Cells(5, col + 1))
        box.Merge(); box.Interior.Color = 0xFFF4E8; box.Borders.LineStyle = 1
        ws.Cells(4, col).Value = label
        ws.Cells(5, col).Value = _fmt_amount(value)
        ws.Cells(5, col).Font.Bold = True
        ws.Cells(5, col).Font.Size = 16

    cache = wb.PivotCaches().Create(SourceType=xl_database, SourceData=source_range)
    pivot_ws = wb.Worksheets("Pivot Ozet")
    pt = cache.CreatePivotTable(TableDestination=pivot_ws.Range("A3"), TableName="ptSiparisDurumu")
    pt.PivotFields("Parça").Orientation = xl_row_field
    pt.PivotFields("Teslim Kullanıcısı").Orientation = xl_column_field
    data_field = pt.AddDataField(pt.PivotFields("Sözleşme Adeti"), "Sum of Sözleşme Adeti", xl_sum)
    data_field.NumberFormat = "#,##0"

    _create_small_pivot_chart(wb, cache, ws, "Parça", "Sözleşme Adeti", "Parça Bazlı Sözleşme Adeti", xl_bar_clustered, 30, 130, 360, 210, "ptParca")
    _create_small_pivot_chart(wb, cache, ws, "Yİ/YD", "Sözleşme Adeti", "Yİ / YD Dağılımı", xl_doughnut, 410, 130, 300, 210, "ptYiyd")
    _create_small_pivot_chart(wb, cache, ws, "Yıl", "Sözleşme Adeti", "Yıllara Göre Sözleşme Adeti", xl_line, 730, 130, 340, 210, "ptYil")

    chart_obj = ws.ChartObjects().Add(30, 380, 760, 360)
    chart = chart_obj.Chart
    chart.SetSourceData(pt.TableRange2)
    chart.ChartType = xl_column_clustered
    chart.HasTitle = True
    chart.ChartTitle.Text = "YURTİÇİ/YURTDIŞI ve YILLARA GÖRE SİPARİŞ DURUMU"
    chart.HasDataTable = True
    chart.DataTable.ShowLegendKey = True
    chart.HasLegend = True
    try:
        chart.ApplyDataLabels()
    except Exception:
        pass
    _add_slicers(wb, ws, pt)
    ws.Columns.AutoFit()


def _create_small_pivot_chart(wb, cache, dashboard_ws, row_field: str, value_field: str, title: str, chart_type: int, left: int, top: int, width: int, height: int, table_name: str):
    xl_row_field = 1
    xl_sum = -4157
    pivot_ws = wb.Worksheets("Grafik Kaynak")
    destination_cols = {"ptParca": 1, "ptYiyd": 6, "ptYil": 11}
    destination = pivot_ws.Cells(3, destination_cols.get(table_name, 16))
    pt = cache.CreatePivotTable(TableDestination=destination, TableName=table_name)
    pt.PivotFields(row_field).Orientation = xl_row_field
    pt.AddDataField(pt.PivotFields(value_field), f"Sum of {value_field}", xl_sum)
    chart_obj = dashboard_ws.ChartObjects().Add(left, top, width, height)
    chart = chart_obj.Chart
    chart.SetSourceData(pt.TableRange2)
    chart.ChartType = chart_type
    chart.HasTitle = True
    chart.ChartTitle.Text = title
    return pt


def _add_slicers(wb, ws, pivot_table) -> None:
    fields = ["Yİ/YD", "Yıl", "Teslimat", "Platform", "Sözleşme", "Durum"]
    left = 830
    top = 380
    for idx, field in enumerate(fields):
        try:
            cache = wb.SlicerCaches.Add2(pivot_table, field)
            cache.Slicers.Add(ws, None, f"sl_{idx}_{field}", field, left, top + idx * 82, 170, 75)
        except Exception:
            continue


def export_delivery_schedule_report(store, output_path, filters=None, progress_cb=None) -> dict:
    output_path = Path(output_path)
    rows = load_delivery_schedule_rows(store, filters=filters)
    report_date = date.today().isoformat()
    platforms = sorted({str(row["Platform"]) for row in rows if row.get("Platform")})
    platform_title = platforms[0] if len(platforms) == 1 else "Çoklu Platform"
    if output_path.suffix.lower() != ".xlsx":
        output_path = output_path.with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    excel = _ensure_excel()
    excel.DisplayAlerts = False
    wb = None
    try:
        _progress(progress_cb, 10, "Excel çalışma kitabı hazırlanıyor")
        wb = excel.Workbooks.Add()
        while wb.Worksheets.Count < len(VISIBLE_SHEETS) + len(HIDDEN_SHEETS):
            wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
        all_names = VISIBLE_SHEETS + HIDDEN_SHEETS
        for idx, name in enumerate(all_names, start=1):
            wb.Worksheets(idx).Name = _safe_sheet_name(name)
        ws_dashboard = wb.Worksheets("Dashboard")
        ws_entry = wb.Worksheets("Teslimat Veri Girişi")
        ws_matrix = wb.Worksheets("Tahmini Teslimat Takvimi")
        ws_rev = wb.Worksheets("REV Takip")
        ws_source = wb.Worksheets("Pivot Kaynak")
        _progress(progress_cb, 25, "Veriler yazılıyor")
        _write_source_sheet(ws_source, rows)
        source_range = f"'Pivot Kaynak'!R1C1:R{max(len(rows) + 1, 2)}C{len(SOURCE_HEADERS)}"
        _write_delivery_entry(ws_entry, rows, report_date, platform_title)
        _write_matrix(ws_matrix, rows, report_date)
        _write_rev_sheet(ws_rev, load_activity_rows(store))
        _progress(progress_cb, 55, "Pivot ve grafikler oluşturuluyor")
        _build_dashboard(wb, ws_dashboard, source_range, rows, platform_title, report_date)
        for name in HIDDEN_SHEETS:
            wb.Worksheets(name).Visible = 0
        wb.Worksheets("Dashboard").Activate()
        _progress(progress_cb, 90, "Dosya kaydediliyor")
        wb.SaveAs(str(output_path), FileFormat=51)
        return {"output_path": str(output_path), "row_count": len(rows), "platform": platform_title, "created_at": report_date, "pivot_enabled": True}
    except ExcelComUnavailableError:
        raise
    except Exception:
        raise
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
        try:
            excel.Quit()
        except Exception:
            pass
