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

APP_STATUS_VALUES = ["Eksik", "Gecikti", "Teslim Edildi", "Planlandı", "Teslim Edildi"]

ALLOWED_ENTITY_TYPES = {"contract", "contracts", "delivery", "deliveries", "acceptance", "term", "calendar"}
ALLOWED_ACTION_KEYWORDS = {"create", "created", "update", "updated", "delete", "deleted", "delivery", "contract", "acceptance", "teslim", "sözleşme", "sozlesme", "termin", "takvim"}
BLOCKED_KEYWORDS = {
    "yoğun test log kaydı", "test log", "stress", "bulk", "dummy", "seed", "sql_query_executed",
    "belge klasörü oluşturuldu", "klasör oluşturuldu", "folder created", "document folder",
    "bileşen listesi güncellendi", "bilesen listesi guncellendi",
    "bileşen sırası güncellendi", "bilesen sirasi guncellendi",
    "bileşen eklendi", "bilesen eklendi",
    "bileşen güncellendi", "bilesen guncellendi",
    "component list", "component order", "component updated", "component added",
}

# Fields that indicate a meaningful content change (not just structural/meta changes)
CONTENT_FIELDS = {
    "planned", "delivered", "remaining", "quantity", "qty", "miktar", "adet",
    "planned_acceptance_date", "acceptance_date",
    "delivery_user_id", "status", "note", "option", "opsiyon",
    "configuration_type", "config_type", "konfigurasyon_tipi", "konfigürasyon_tipi",
    "contract_no", "yi_yd",
}
FIELD_LABELS = {
    "planned_acceptance_date": "Planlanan Teslimat Tarihi",
    "acceptance_date": "Gerçek Teslimat Tarihi",
    "delivery_user_id": "Teslim Kullanıcısı",
    "planned": "Sözleşme Adeti",
    "delivered": "Teslim Edilen Miktar",
    "status": "Durum",
    "note": "Not",
    "contract_no": "Sözleşme No",
    "yi_yd": "Yİ/YD",
    "configuration_type": "Konfigürasyon Tipi",
    "config_type": "Konfigürasyon Tipi",
    "option": "Opsiyon",
    "opsiyon": "Opsiyon",
    "remaining": "Kalan",
    "konfigurasyon_tipi": "Konfigürasyon Tipi",
    "konfigürasyon_tipi": "Konfigürasyon Tipi",
}


class ExcelComUnavailableError(RuntimeError):
    """Raised when pywin32 or Microsoft Excel COM automation is unavailable."""


def _conn_from_store(store: object) -> Optional[sqlite3.Connection]:
    """Return an SQLite connection from STSStore/STSDatabase safely.

    The dialog usually passes an already-open STSStore, but exported reports
    may also be triggered from a lightweight wrapper that only exposes a path.
    Keep this helper defensive so the Excel exporter never crashes just because
    the store shape is slightly different.
    """
    if store is None:
        return None
    db = getattr(store, "db", None)
    conn = getattr(db, "conn", None)
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        return conn
    conn = getattr(store, "conn", None)
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        return conn
    path = getattr(store, "path", None) or getattr(db, "path", None)
    if path:
        created = sqlite3.connect(str(path))
        created.row_factory = sqlite3.Row
        try:
            created.execute("PRAGMA foreign_keys=ON")
            created.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        return created
    return None


def extract_year_from_date_text(value: object) -> Optional[int]:
    text = str(value or "").strip()
    match = re.search(r"(?<!\d)(19\d{2}|20\d{2}|21\d{2})(?!\d)", text)
    return int(match.group(1)) if match else None


def normalize_report_date_display(value: object) -> str:
    """Return a visible report date, preserving uncertain/TBD dates.

    Supported examples:
    - empty / None / TBD       -> TBD-TBD-TBD
    - 2026                    -> TBD-TBD-2026
    - 06-2026 / 2026-06       -> TBD-06-2026
    - TBD-06-2026             -> TBD-06-2026
    - 2026-TBD-TBD            -> TBD-TBD-2026
    - 15-06-2026 / 2026-06-15 -> 15-06-2026
    """
    raw = str(value or "").strip()
    if not raw:
        return "TBD-TBD-TBD"

    text = raw.replace("/", "-").replace(".", "-").strip().upper()
    compact_unknown = re.sub(r"[^A-Z0-9]+", "", text)
    if compact_unknown in {"", "TBD", "TBDBELIRLENECEK", "BELIRSIZ", "BILINMIYOR", "UNKNOWN", "N/A", "NA", "NONE", "NULL"}:
        return "TBD-TBD-TBD"

    def is_year(part: str) -> bool:
        return bool(re.fullmatch(r"(19\d{2}|20\d{2}|21\d{2})", str(part or "").strip()))

    def is_unknown(part: str) -> bool:
        token = re.sub(r"[^A-Z0-9]+", "", str(part or "").strip().upper())
        return token in {"", "0", "00", "TBD", "BELIRSIZ", "BILINMIYOR", "UNKNOWN", "NA", "NONE", "NULL"}

    def two_digit(part: str) -> str:
        part = str(part or "").strip().upper()
        if is_unknown(part):
            return "TBD"
        return part.zfill(2) if part.isdigit() and len(part) <= 2 else part

    parts = [p.strip() for p in text.split("-") if p.strip()]

    year = next((p for p in parts if is_year(p)), None)
    if year is None:
        extracted = extract_year_from_date_text(text)
        if extracted:
            return f"TBD-TBD-{extracted}"
        return "TBD-TBD-TBD" if any(is_unknown(p) for p in parts) else text

    if len(parts) == 1:
        return f"TBD-TBD-{year}"

    if len(parts) == 2:
        other = parts[1] if is_year(parts[0]) else parts[0]
        # With two-part dates, treat the non-year token as month.
        return f"TBD-{two_digit(other)}-{year}"

    if is_year(parts[0]):
        year, month, day = parts[0], parts[1], parts[2]
        return f"{two_digit(day)}-{two_digit(month)}-{year}"
    if is_year(parts[2]):
        day, month, year = parts[0], parts[1], parts[2]
        return f"{two_digit(day)}-{two_digit(month)}-{year}"

    return f"TBD-TBD-{year}"


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


def _filter_text_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    repl = {"ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def _is_all_filter_value(value: Any, all_text: str = "Tümü") -> bool:
    return _filter_text_key(value) == _filter_text_key(all_text)


def _normalize_yi_yd_value(value: Any) -> str:
    key = _filter_text_key(value).replace(" ", "")
    if key in {"yi", "yici", "yurtici", "yurtiçi"} or "yurtici" in key:
        return "Yİ"
    if key in {"yd", "yddisi", "yurtdisi", "yurtdışı"} or "yurtdisi" in key:
        return "YD"
    return str(value or "").strip().upper()


def _matches_filters(row: dict[str, Any], filters: Optional[dict[str, Any]]) -> bool:
    if not filters:
        return True
    start_year = filters.get("start_year")
    end_year = filters.get("end_year")
    if start_year and end_year:
        year = row.get("Yıl")
        # Unknown/TBD dates must stay visible in the report/export. Known
        # years continue to obey the selected year range.
        if year in (None, "", "TBD"):
            pass
        else:
            try:
                if not (int(start_year) <= int(year) <= int(end_year)):
                    return False
            except (TypeError, ValueError):
                pass
    checks = [
        ("platform", "Platform", "Tümü"),
        ("yi_yd", "Yİ/YD", "Tümü"),
        ("user", "Teslim Kullanıcısı", "Tümü"),
        ("delivery_user", "Teslim Kullanıcısı", "Tümü"),
        ("status", "Durum", "Tümü"),
    ]
    for filter_key, row_key, all_value in checks:
        value = filters.get(filter_key)
        if not value or _is_all_filter_value(value, all_value):
            continue
        if filter_key == "yi_yd":
            if _normalize_yi_yd_value(row.get(row_key)) != _normalize_yi_yd_value(value):
                return False
        elif str(row.get(row_key) or "") != str(value):
            return False
    owner = filters.get("owner")
    if owner and not _is_all_filter_value(owner, "Tümü"):
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
            "Yıl": year or "TBD",
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


def _normalize_field_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_content_field_change(data: dict) -> bool:
    """Return True if the log row contains a change in a meaningful CONTENT_FIELDS key."""
    payload = _json_dict(data.get("payload_json"))
    before = _json_dict(data.get("before_json"))
    after = _json_dict(data.get("after_json"))
    field_name = _normalize_field_key(payload.get("field") or payload.get("column") or payload.get("name"))
    if field_name and field_name in CONTENT_FIELDS:
        return True
    all_keys = {_normalize_field_key(key) for key in (set(before.keys()) | set(after.keys()) | set(payload.keys()))}
    return bool(all_keys & CONTENT_FIELDS)


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
    # If message matches a blocked keyword, only allow it if a real content field changed
    if any(keyword in combined for keyword in BLOCKED_KEYWORDS):
        return _has_content_field_change(data)
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
        "source": "auto",
        "log_id": int(row.get("id") or 0),
        "manual_id": None,
        "date": str(row.get("created_at") or ""),
        "user": str(row.get("actor") or "-"),
        "contract": str(row.get("resolved_contract_no") or row.get("contract_no") or "-"),
        "delivery": entity_key or "-",
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
        "description": str(row.get("message") or ""),
    }


def _selected_contracts_from_filters(filters: Optional[dict[str, Any]]) -> set[str]:
    if not filters:
        return set()
    explicit = filters.get("_selected_contracts") or filters.get("selected_contracts") or []
    if isinstance(explicit, str):
        explicit = [explicit]
    selected = {str(item).strip() for item in explicit if str(item or "").strip()}
    contract = str(filters.get("contract") or "").strip()
    if contract and contract not in {"Tüm seçili sözleşmeler", "Tümü", "-"}:
        selected.add(contract)
    return selected


def _first_json_value(data: dict[str, Any], *keys: str) -> str:
    key_set = {key.lower() for key in keys}
    for json_key in ("payload_json", "before_json", "after_json"):
        payload = _json_dict(data.get(json_key))
        for key, value in payload.items():
            if str(key).strip().lower() in key_set and value not in (None, ""):
                return str(value).strip()
    return ""


def _resolve_contract_no_by_id(conn: sqlite3.Connection, contract_id: Any) -> str:
    try:
        if contract_id in (None, ""):
            return ""
        row = conn.execute("SELECT contract_no FROM contracts WHERE id=?", (int(contract_id),)).fetchone()
        return str(row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _resolve_delivery_contract_no(conn: sqlite3.Connection, delivery_id: Any) -> str:
    try:
        if delivery_id in (None, ""):
            return ""
        row = conn.execute(
            """
            SELECT c.contract_no
            FROM deliveries d
            JOIN contracts c ON c.id = d.contract_id
            WHERE d.id=?
            """,
            (int(delivery_id),),
        ).fetchone()
        return str(row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _resolve_log_contract_no(conn: sqlite3.Connection, data: dict[str, Any]) -> str:
    for key in ("resolved_contract_no", "contract_no", "contract", "contract_number", "sozlesme", "sözleşme"):
        value = str(data.get(key) or "").strip()
        if value and value != "-":
            return value
    direct = _first_json_value(data, "contract_no", "contract", "contract_number", "sozlesme", "sözleşme")
    if direct:
        return direct
    contract_id = data.get("contract_id") or _first_json_value(data, "contract_id")
    resolved = _resolve_contract_no_by_id(conn, contract_id)
    if resolved:
        return resolved
    entity_type = str(data.get("entity_type") or "").strip().lower()
    entity_id = data.get("entity_id") or data.get("entity") or data.get("id")
    if entity_type in {"contract", "contracts"}:
        resolved = _resolve_contract_no_by_id(conn, entity_id)
        if resolved:
            return resolved
    if entity_type in {"delivery", "deliveries", "acceptance"}:
        resolved = _resolve_delivery_contract_no(conn, entity_id)
        if resolved:
            return resolved
    delivery_id = _first_json_value(data, "delivery_id", "teslimat_id")
    resolved = _resolve_delivery_contract_no(conn, delivery_id)
    if resolved:
        return resolved
    entity_key = str(data.get("entity_key") or "").strip()
    match = re.search(r"\bSTS[-_ ]?\d+\b", entity_key, flags=re.IGNORECASE)
    if match:
        return match.group(0).replace("_", "-").replace(" ", "-").upper()
    match = re.fullmatch(r"(?:contract|contracts):?(\d+)", entity_key, flags=re.IGNORECASE)
    if match:
        return _resolve_contract_no_by_id(conn, match.group(1))
    match = re.fullmatch(r"(?:delivery|deliveries|acceptance):?(\d+)", entity_key, flags=re.IGNORECASE)
    if match:
        return _resolve_delivery_contract_no(conn, match.group(1))
    return ""


def _fetch_activity_log_rows(conn: sqlite3.Connection, limit: int) -> list[Any]:
    cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(activity_logs)").fetchall()}
    select_contract = "'' AS resolved_contract_no"
    joins: list[str] = []
    coalesce_parts: list[str] = []
    if "contract_id" in cols:
        joins.append("LEFT JOIN contracts c_direct ON c_direct.id = l.contract_id")
        coalesce_parts.append("c_direct.contract_no")
    if "entity_id" in cols and "entity_type" in cols:
        joins.append("LEFT JOIN contracts c_entity ON c_entity.id = l.entity_id AND lower(l.entity_type) IN ('contract','contracts')")
        joins.append("LEFT JOIN deliveries d_entity ON d_entity.id = l.entity_id AND lower(l.entity_type) IN ('delivery','deliveries','acceptance')")
        joins.append("LEFT JOIN contracts c_delivery ON c_delivery.id = d_entity.contract_id")
        coalesce_parts.extend(["c_entity.contract_no", "c_delivery.contract_no"])
    if coalesce_parts:
        select_contract = f"COALESCE({', '.join(coalesce_parts)}, '') AS resolved_contract_no"
    query = f"""
        SELECT l.*, {select_contract}
        FROM activity_logs l
        {' '.join(joins)}
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT ?
    """
    return conn.execute(query, (max(int(limit or 200) * 8, int(limit or 200)),)).fetchall()


def load_meaningful_revision_logs(store: object, limit: int = 200, filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    conn = _conn_from_store(store)
    if conn is None:
        return []
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_logs'"
        ).fetchone()
        if not table:
            return []
        rows = _fetch_activity_log_rows(conn, limit)
    except Exception:
        return []
    selected_contracts = _selected_contracts_from_filters(filters)
    result: list[dict[str, Any]] = []
    for row in rows:
        data = _as_dict(row)
        if not is_meaningful_revision_log(data):
            continue
        resolved_contract = _resolve_log_contract_no(conn, data)
        if selected_contracts:
            if not resolved_contract or resolved_contract not in selected_contracts:
                continue
        if resolved_contract:
            data["resolved_contract_no"] = resolved_contract
        result.append(_revision_log_to_row(data, len(result) + 1))
        if len(result) >= int(limit or 200):
            break
    return result



REV_MANUAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS delivery_schedule_revision_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER,
    delivery_id INTEGER,
    system_name TEXT,
    revision_date TEXT,
    user_name TEXT,
    contract_no TEXT,
    delivery_name TEXT,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    description TEXT,
    source TEXT DEFAULT 'manual',
    is_deleted INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    created_by TEXT,
    updated_by TEXT
)
"""
REV_HIDDEN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS delivery_schedule_rev_hidden_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL UNIQUE,
    hidden_by TEXT,
    hidden_at TEXT,
    reason TEXT
)
"""


def ensure_revision_edit_tables(conn: sqlite3.Connection) -> None:
    conn.execute(REV_MANUAL_TABLE_SQL)
    conn.execute(REV_HIDDEN_TABLE_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_schedule_revision_rows_contract ON delivery_schedule_revision_rows(contract_no)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_schedule_revision_rows_deleted ON delivery_schedule_revision_rows(is_deleted)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_schedule_rev_hidden_logs_log ON delivery_schedule_rev_hidden_logs(log_id)")
    conn.commit()


def _hidden_revision_log_ids(conn: sqlite3.Connection) -> set[int]:
    try:
        ensure_revision_edit_tables(conn)
        return {int(row[0]) for row in conn.execute("SELECT log_id FROM delivery_schedule_rev_hidden_logs").fetchall()}
    except Exception:
        return set()


def _manual_revision_rows(conn: sqlite3.Connection, filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Return only user-entered REV rows.

    Activity/application logs are intentionally not included in REV Takip for now.
    The existing table schema is reused: field_name stores the visible
    "Revizyon Bilgisi" value, revision_date stores the visible "Tarih" value.
    """
    try:
        ensure_revision_edit_tables(conn)
        rows = conn.execute(
            """
            SELECT id, revision_date, field_name, description, source,
                   created_at, updated_at, created_by, updated_by
            FROM delivery_schedule_revision_rows
            WHERE COALESCE(is_deleted,0)=0
            ORDER BY id ASC
            """
        ).fetchall()
    except Exception:
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        data = _as_dict(row)
        revision_info = str(data.get("field_name") or "").strip()
        result.append({
            "revision": revision_info,
            "revision_info": revision_info,
            "source": "manual",
            "log_id": None,
            "manual_id": int(data.get("id") or 0),
            "date": str(data.get("revision_date") or ""),
            "field": revision_info,
            "description": str(data.get("description") or ""),
        })
    return result


def build_delivery_schedule_revision_rows(store: object, limit: int = 200, filters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    conn = _conn_from_store(store)
    if conn is None:
        return []
    # Only manual rows are shown/exported. Do not merge activity_logs into REV Takip.
    return _manual_revision_rows(conn, filters=None)[: int(limit or 200)]


def save_manual_revision_row(store: object, values: dict[str, Any], row_id: Optional[int] = None) -> int:
    conn = _conn_from_store(store)
    if conn is None:
        raise RuntimeError("Açık STS veritabanı bulunamadı.")
    ensure_revision_edit_tables(conn)
    now = datetime.now().isoformat(timespec="seconds")
    actor = str(values.get("updated_by") or values.get("created_by") or values.get("user_name") or "Kullanıcı")
    revision_info = str(values.get("revision_info") or values.get("field_name") or values.get("revision") or "").strip()
    revision_date = str(values.get("revision_date") or values.get("date") or "").strip()
    description = str(values.get("description") or "").strip()

    if row_id:
        conn.execute(
            """
            UPDATE delivery_schedule_revision_rows
            SET revision_date=?, field_name=?, description=?, updated_at=?, updated_by=?
            WHERE id=? AND COALESCE(is_deleted,0)=0
            """,
            (revision_date, revision_info, description, now, actor, int(row_id)),
        )
        conn.commit()
        return int(row_id)

    cur = conn.execute(
        """
        INSERT INTO delivery_schedule_revision_rows(
            contract_id, delivery_id, system_name, revision_date, user_name, contract_no,
            delivery_name, field_name, old_value, new_value, description, source,
            is_deleted, created_at, updated_at, created_by, updated_by
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            values.get("contract_id"), values.get("delivery_id"), str(values.get("system_name") or ""),
            revision_date, actor, str(values.get("contract_no") or ""),
            str(values.get("delivery_name") or ""), revision_info, "", "", description,
            "manual", 0, now, now, actor, actor,
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def hide_revision_row(store: object, row: dict[str, Any], actor: str = "", reason: str = "") -> None:
    conn = _conn_from_store(store)
    if conn is None:
        raise RuntimeError("Açık STS veritabanı bulunamadı.")
    ensure_revision_edit_tables(conn)
    now = datetime.now().isoformat(timespec="seconds")
    manual_id = int(row.get("manual_id") or 0)
    if manual_id:
        conn.execute(
            "UPDATE delivery_schedule_revision_rows SET is_deleted=1, updated_at=?, updated_by=? WHERE id=?",
            (now, actor or "Kullanıcı", manual_id),
        )
        conn.commit()


def load_activity_rows(store: object, filters: Optional[dict[str, Any]] = None) -> list[list[Any]]:
    rows = build_delivery_schedule_revision_rows(store, limit=200, filters=None)
    return [
        [
            str(log.get("revision_info") or log.get("field") or log.get("revision") or ""),
            str(log.get("date") or ""),
            str(log.get("description") or ""),
        ]
        for log in rows
    ]


def _build_pivot_source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add zero-value seed rows so the Durum slicer always matches app statuses.

    These extra rows are only written to the hidden pivot source sheet. Since all
    numeric measures are zero, totals and charts remain unchanged, but Excel can
    still show the full application status list in the slicer. Seed rows are
    prepended in application order so the slicer can follow the same order.
    """
    if not rows:
        return rows
    base_row = dict(rows[0])
    seeded: list[dict[str, Any]] = []
    for status in APP_STATUS_VALUES:
        seed = dict(base_row)
        seed["Durum"] = status
        seed["Sözleşme Adeti"] = 0
        seed["Teslim Edilen"] = 0
        seed["Kalan"] = 0
        seed["Opsiyon / Not"] = ""
        seeded.append(seed)
    seeded.extend(rows)
    return seeded


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
    """Write the matrix exactly in the approved report layout.

    Row 1 is the dark title band, row 2 contains date/user subheaders,
    data starts on row 3. Parça Numarası is intentionally blank for now.
    """
    users = sorted({str(row["Teslim Kullanıcısı"]) for row in rows})
    user_dates = {
        user: sorted({str(row["Tarih"]) for row in rows if row["Teslim Kullanıcısı"] == user and row["Tarih"]})
        for user in users
    }
    last_col = 4 + len(users)
    total_col = last_col

    ws.Cells(1, 1).Value = f"{report_date}\nREV:{REVISION[-3:]}"
    ws.Cells(1, 1).Interior.Color = 0x79360B
    ws.Cells(1, 1).Font.Color = 0xFFFFFF
    ws.Cells(1, 1).Font.Bold = True
    ws.Cells(1, 1).HorizontalAlignment = -4108
    ws.Cells(1, 1).VerticalAlignment = -4108
    ws.Cells(1, 1).WrapText = True

    ws.Range(ws.Cells(1, 2), ws.Cells(1, 3)).Merge()
    ws.Cells(1, 2).Value = "Teslimat Adı:"
    ws.Range(ws.Cells(1, 2), ws.Cells(1, 3)).Interior.Color = 0x79360B
    ws.Range(ws.Cells(1, 2), ws.Cells(1, 3)).Font.Color = 0xFFFFFF
    ws.Range(ws.Cells(1, 2), ws.Cells(1, 3)).Font.Bold = True
    ws.Range(ws.Cells(1, 2), ws.Cells(1, 3)).HorizontalAlignment = -4108

    ws.Cells(2, 1).Value = "Seviye"
    ws.Cells(2, 2).Value = "Parça Numarası"
    ws.Cells(2, 3).Value = "Teslimat Zamanı"

    for idx, user in enumerate(users, start=4):
        ws.Cells(1, idx).Value = user
        ws.Cells(1, idx).Interior.Color = 0x79360B
        ws.Cells(1, idx).Font.Color = 0xFFFFFF
        ws.Cells(1, idx).Font.Bold = True
        ws.Cells(1, idx).HorizontalAlignment = -4108
        ws.Cells(2, idx).Value = ", ".join(user_dates.get(user, [])[:2])
        ws.Cells(2, idx).Font.Bold = True
        ws.Cells(2, idx).HorizontalAlignment = -4108

    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).Merge()
    ws.Cells(1, total_col).Value = "TOPLAM"
    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).Interior.Color = 0x79360B
    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).Font.Color = 0xFFFFFF
    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).Font.Bold = True
    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).HorizontalAlignment = -4108
    ws.Range(ws.Cells(1, total_col), ws.Cells(2, total_col)).VerticalAlignment = -4108

    by_part: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        by_part[str(row["Parça"])][str(row["Teslim Kullanıcısı"])] += _safe_float(row["Sözleşme Adeti"])

    r = 3
    for part in sorted(by_part, key=lambda p: sum(by_part[p].values()), reverse=True):
        ws.Cells(r, 1).Value = "1"
        ws.Cells(r, 2).Value = ""  # Parça Numarası şimdilik boş.
        ws.Cells(r, 3).Value = part
        total = 0.0
        for idx, user in enumerate(users, start=4):
            value = by_part[part].get(user, 0.0)
            total += value
            ws.Cells(r, idx).Value = _fmt_amount(value)
        ws.Cells(r, total_col).Value = _fmt_amount(total)
        r += 1

    _format_table(ws, 1, 1, max(r - 1, 3), total_col, header_rows=1)
    row2 = ws.Range(ws.Cells(2, 1), ws.Cells(2, total_col - 1))
    row2.Interior.Color = 0xFFFFFF
    row2.Font.Color = 0x79360B
    row2.Font.Bold = True
    row2.HorizontalAlignment = -4108
    # Strong black closing border below the last data row.
    closing = ws.Range(ws.Cells(max(r - 1, 3), 1), ws.Cells(max(r - 1, 3), total_col))
    closing.Borders(9).LineStyle = 1  # xlEdgeBottom
    closing.Borders(9).Weight = 3
    closing.Borders(9).Color = 0x000000
    ws.Columns.AutoFit()

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
    headers = [
        "PARÇA NUMARASI", "KULLANICI ADI", "PARÇA ADI", "MİKTAR", "İHA",
        "TESLİMAT ZAMANI", "TESLİMAT ZAMANI", "TESLİMAT ADI", "Yİ/YD", "YIL",
        "SÖZLEŞME ADI", "Konfigürasyon Tipi", "Opsiyon / Not",
    ]
    last_col = len(headers)

    ws.Range(ws.Cells(1, 1), ws.Cells(2, 2)).Merge()
    ws.Cells(1, 1).Value = f"{report_date}\nREV:{REVISION[-3:]}"
    ws.Range(ws.Cells(1, 1), ws.Cells(2, 2)).HorizontalAlignment = -4108
    ws.Range(ws.Cells(1, 1), ws.Cells(2, 2)).VerticalAlignment = -4108
    ws.Range(ws.Cells(1, 1), ws.Cells(2, 2)).WrapText = True
    ws.Range(ws.Cells(1, 1), ws.Cells(2, 2)).Font.Bold = True

    ws.Range(ws.Cells(1, 3), ws.Cells(2, last_col)).Merge()
    ws.Cells(1, 3).Value = f"{platform_title} Tahmini Teslimat Takvimi"
    ws.Range(ws.Cells(1, 3), ws.Cells(2, last_col)).HorizontalAlignment = -4108
    ws.Range(ws.Cells(1, 3), ws.Cells(2, last_col)).VerticalAlignment = -4108
    ws.Range(ws.Cells(1, 3), ws.Cells(2, last_col)).Font.Bold = True
    ws.Range(ws.Cells(1, 3), ws.Cells(2, last_col)).Font.Size = 14

    # Row 3 is part of the visual header area as a grey separator band.
    row3 = ws.Range(ws.Cells(3, 1), ws.Cells(3, last_col))
    row3.Interior.Color = 0xE7E6E6
    row3.HorizontalAlignment = -4108
    row3.VerticalAlignment = -4108

    for col, header in enumerate(headers, start=1):
        ws.Cells(4, col).Value = header

    r = 5
    last_user = None
    sorted_rows = sorted(rows, key=lambda item: (str(item["Teslim Kullanıcısı"]), str(item["Sözleşme"]), str(item["Parça"])))
    for row in sorted_rows:
        user = str(row["Teslim Kullanıcısı"])
        if user != last_user:
            ws.Cells(r, 1).Value = user
            ws.Range(ws.Cells(r, 1), ws.Cells(r, last_col)).Merge()
            ws.Range(ws.Cells(r, 1), ws.Cells(r, last_col)).Interior.Color = 0xFCE4D6
            ws.Range(ws.Cells(r, 1), ws.Cells(r, last_col)).Font.Bold = True
            ws.Range(ws.Cells(r, 1), ws.Cells(r, last_col)).HorizontalAlignment = -4108
            ws.Range(ws.Cells(r, 1), ws.Cells(r, last_col)).VerticalAlignment = -4108
            r += 1
            last_user = user

        values = [
            "", user, row["Parça"], row["Sözleşme Adeti"], "",
            str(row["Tarih"] or ""), str(row["Tarih"] or ""), row["Teslimat"], row["Yİ/YD"], row["Yıl"],
            row["Sözleşme"], row["Konfigürasyon Tipi"], row["Opsiyon / Not"],
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.Cells(r, col)
            if col in (6, 7):
                cell.NumberFormat = "@"
                cell.Value = str(value or "")
            else:
                cell.Value = value
            cell.HorizontalAlignment = -4108
            cell.VerticalAlignment = -4108
        r += 1

    _format_table(ws, 4, 1, max(r - 1, 4), last_col)
    used = ws.Range(ws.Cells(1, 1), ws.Cells(max(r - 1, 4), last_col))
    used.HorizontalAlignment = -4108
    used.VerticalAlignment = -4108
    ws.Columns("F:G").NumberFormat = "@"
    ws.Columns.AutoFit()

def _write_source_sheet(ws, rows: list[dict[str, Any]]) -> None:
    for col, header in enumerate(SOURCE_HEADERS, start=1):
        ws.Cells(1, col).Value = header
    for r, row in enumerate(rows, start=2):
        for c, header in enumerate(SOURCE_HEADERS, start=1):
            cell = ws.Cells(r, c)
            value = row.get(header, "")
            if header == "Tarih":
                cell.NumberFormat = "@"
                cell.Value = str(value or "")
            else:
                cell.Value = value
            cell.HorizontalAlignment = -4108
            cell.VerticalAlignment = -4108
    _format_table(ws, 1, 1, max(len(rows) + 1, 1), len(SOURCE_HEADERS))
    ws.Columns.AutoFit()


def _write_rev_sheet(ws, activity_rows: list[list[Any]]) -> None:
    headers = ["Revizyon Bilgisi", "Tarih", "Açıklama"]
    for col, header in enumerate(headers, start=1):
        ws.Cells(1, col).Value = header
    for r, row in enumerate(activity_rows, start=2):
        for c, value in enumerate(row[:len(headers)], start=1):
            cell = ws.Cells(r, c)
            if c == 2:
                cell.NumberFormat = "@"
                cell.Value = str(value or "")
            else:
                cell.Value = value
    _format_table(ws, 1, 1, max(len(activity_rows) + 1, 1), len(headers))



def _build_dashboard(wb, ws, source_range: str, rows: list[dict[str, Any]], platform_title: str, report_date: str):
    xl_database = 1
    xl_row_field = 1
    xl_column_field = 2
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
    ws.Range("A1").HorizontalAlignment = -4108
    ws.Range("A1").VerticalAlignment = -4108

    ws.Range("A2:N2").Merge()
    ws.Range("A2").Value = f"Rapor Tarihi: {report_date}    Revizyon: {REVISION}    Değer Türü: Sözleşme Adeti / Teslim Edilecek"
    ws.Range("A2").HorizontalAlignment = -4108
    ws.Range("A2").VerticalAlignment = -4108

    total = sum(_safe_float(row["Sözleşme Adeti"]) for row in rows)
    users = len({row["Teslim Kullanıcısı"] for row in rows})
    contracts = len({row["Sözleşme"] for row in rows})
    risk = sum(1 for row in rows if _safe_float(row["Kalan"]) > 0 and "tamam" not in str(row["Durum"]).lower())

    kpi_specs = [
        ("SÖZLEŞME ADETİ", total, 1),
        ("TESLİM KULLANICISI", users, 4),
        ("SÖZLEŞME", contracts, 7),
        ("RİSKLİ SATIR", risk, 10),
    ]
    for label, value, col in kpi_specs:
        outer = ws.Range(ws.Cells(4, col), ws.Cells(6, col + 2))
        outer.Interior.Color = 0xFFF4E8
        outer.Borders.LineStyle = 1
        outer.Borders.Color = 0xBFD5F2

        title_rng = ws.Range(ws.Cells(4, col), ws.Cells(4, col + 2))
        title_rng.Merge()
        title_rng.Value = label
        title_rng.Font.Bold = True
        title_rng.Font.Color = 0x79360B
        title_rng.HorizontalAlignment = -4108
        title_rng.VerticalAlignment = -4108

        value_rng = ws.Range(ws.Cells(5, col), ws.Cells(6, col + 2))
        value_rng.Merge()
        value_rng.Value = _fmt_amount(value)
        value_rng.Font.Bold = True
        value_rng.Font.Size = 18
        value_rng.Font.Color = 0xE12D0B
        value_rng.HorizontalAlignment = -4108
        value_rng.VerticalAlignment = -4108

    cache = wb.PivotCaches().Create(SourceType=xl_database, SourceData=source_range)
    pivot_ws = wb.Worksheets("Pivot Ozet")
    pt = cache.CreatePivotTable(TableDestination=pivot_ws.Range("A3"), TableName="ptSiparisDurumu")
    pt.PivotFields("Parça").Orientation = xl_row_field
    pt.PivotFields("Teslim Kullanıcısı").Orientation = xl_column_field
    data_field = pt.AddDataField(pt.PivotFields("Sözleşme Adeti"), "Sum of Sözleşme Adeti", xl_sum)
    data_field.NumberFormat = "#,##0"

    pt_part = _create_small_pivot_chart(wb, cache, ws, "Parça", "Sözleşme Adeti", "Parça Bazlı Sözleşme Adeti", xl_bar_clustered, 30, 170, 360, 210, "ptParca")
    pt_yiyd = _create_small_pivot_chart(wb, cache, ws, "Yİ/YD", "Sözleşme Adeti", "Yİ / YD Dağılımı", xl_doughnut, 410, 170, 300, 210, "ptYiyd")
    pt_year = _create_small_pivot_chart(wb, cache, ws, "Yıl", "Sözleşme Adeti", "Yıllara Göre Sözleşme Adeti", xl_line, 730, 170, 340, 210, "ptYil")

    chart_obj = ws.ChartObjects().Add(30, 430, 760, 360)
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

    _add_slicers(wb, ws, pt, [pt_part, pt_yiyd, pt_year])
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


def _slicer_registry_key(ws, field_name: str) -> tuple[str, str]:
    try:
        sheet_name = str(ws.Name)
    except Exception:
        sheet_name = "Dashboard"
    return (sheet_name, str(field_name or "").strip().casefold())


def _try_delete_shape_by_name(ws, shape_name: str) -> None:
    """Best-effort cleanup for stale manual/COM slicer shapes with the same object name."""
    try:
        shapes = ws.Shapes
        for idx in range(shapes.Count, 0, -1):
            shp = shapes.Item(idx)
            if str(getattr(shp, "Name", "") or "") == shape_name:
                shp.Delete()
    except Exception:
        pass


def add_unique_slicer(
    wb,
    ws,
    pivot_table,
    field_name: str,
    slicer_name: str,
    left: int,
    top: int,
    width: int,
    height: int,
    created_slicers: set[tuple[str, str]],
    extra_pivot_tables=None,
):
    """Create exactly one slicer per worksheet+field for this export run.

    Excel COM keeps slicer caches and slicer shapes separately.  The previous
    implementation created the same slicer twice from the same cache, which
    produced two differently styled boxes for fields such as Durum/Sözleşme.
    This helper centralizes creation and uses a per-run registry before touching
    COM, so duplicate cache/shape creation is prevented at the source.
    """
    field_name = str(field_name or "").strip()
    if not field_name:
        return None
    key = _slicer_registry_key(ws, field_name)
    if key in created_slicers:
        return None
    created_slicers.add(key)
    _try_delete_shape_by_name(ws, slicer_name)

    try:
        cache = wb.SlicerCaches.Add2(pivot_table, field_name)
    except Exception:
        try:
            cache = wb.SlicerCaches.Add(pivot_table, field_name)
        except Exception:
            return None

    for pt in list(extra_pivot_tables or []):
        try:
            cache.PivotTables.AddPivotTable(pt)
        except Exception:
            pass

    try:
        slicer = cache.Slicers.Add(ws, None, slicer_name, field_name, left, top, width, height)
    except Exception:
        try:
            slicer = cache.Slicers.Add(
                SlicerDestination=ws,
                Name=slicer_name,
                Caption=field_name,
                Left=left,
                Top=top,
                Width=width,
                Height=height,
            )
        except Exception:
            return None

    try:
        slicer.NumberOfColumns = 1
    except Exception:
        pass
    try:
        slicer.Style = "SlicerStyleLight2"
    except Exception:
        pass
    try:
        cache.CrossFilterType = 1
    except Exception:
        pass
    try:
        cache.SortItems = 1
    except Exception:
        pass
    return slicer


def _add_slicers(wb, ws, pivot_table, extra_pivot_tables=None) -> None:
    """Add one real Excel slicer per field and connect it to all dashboard pivots."""
    fields = ["Yİ/YD", "Yıl", "Teslimat", "Platform", "Sözleşme", "Durum"]
    left = 1110
    top = 380
    created_slicers: set[tuple[str, str]] = set()
    extra_pivot_tables = list(extra_pivot_tables or [])
    for idx, field in enumerate(fields):
        height = 125 if field == "Durum" else 75
        name = f"sl_{idx}_{_safe_filename(field)}"
        add_unique_slicer(
            wb,
            ws,
            pivot_table,
            field,
            name,
            left,
            top + idx * 82,
            170,
            height,
            created_slicers,
            extra_pivot_tables=extra_pivot_tables,
        )


def export_delivery_schedule_report(store, output_path, filters=None, progress_cb=None) -> dict:
    output_path = Path(output_path)
    rows = load_delivery_schedule_rows(store, filters=filters)
    source_rows = _build_pivot_source_rows(rows)
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
        _write_source_sheet(ws_source, source_rows)
        source_range = f"'Pivot Kaynak'!R1C1:R{max(len(source_rows) + 1, 2)}C{len(SOURCE_HEADERS)}"
        _write_delivery_entry(ws_entry, rows, report_date, platform_title)
        _write_matrix(ws_matrix, rows, report_date)
        rev_filters = dict(filters or {})
        rev_filters["_selected_contracts"] = sorted({str(row.get("Sözleşme") or "") for row in rows if row.get("Sözleşme")})
        _write_rev_sheet(ws_rev, load_activity_rows(store, filters=rev_filters))
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
