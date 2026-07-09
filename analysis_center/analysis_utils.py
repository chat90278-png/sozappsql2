from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Any, Mapping

from .analysis_settings import COMPLETED_STATUS_KEYS, IN_PROGRESS_STATUS_KEYS, NOT_STARTED_STATUS_KEYS


def text_value(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    text = text_value(value).replace("ı", "i").replace("İ", "i").casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())




def is_completed_status(value: Any) -> bool:
    return normalize_text(value) in {normalize_text(item) for item in COMPLETED_STATUS_KEYS}


def is_record_completed(item: Mapping[str, Any]) -> bool:
    return is_completed_status(item.get("status")) or bool(text_value(item.get("acceptance_date")))


def is_acceptance_completed(item: Mapping[str, Any]) -> bool:
    if is_record_completed(item):
        return True
    planned = float(item.get("planned_total") or 0)
    delivered = float(item.get("delivered_total") or 0)
    return planned > 0 and delivered >= planned

def normalize_status_bucket(value: Any) -> str:
    key = normalize_text(value)
    if not key:
        return "Eksik durum"
    if key in {normalize_text(item) for item in COMPLETED_STATUS_KEYS}:
        return "Tamamlanan"
    if key in {normalize_text(item) for item in NOT_STARTED_STATUS_KEYS}:
        return "Başlanmadı"
    if key in {normalize_text(item) for item in IN_PROGRESS_STATUS_KEYS}:
        return "Devam ediyor"
    return text_value(value)


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = text_value(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            candidate = text[:19] if "%H" in fmt else text[:10]
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = text_value(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
