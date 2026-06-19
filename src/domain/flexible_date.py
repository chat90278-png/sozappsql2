from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

_EXACT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAY_TBD_RE = re.compile(r"^\d{4}-\d{2}-TBD$", re.IGNORECASE)
_MONTH_DAY_TBD_RE = re.compile(r"^\d{4}-TBD-TBD$", re.IGNORECASE)
_SPECIALS = {"TBD", "-"}


def _clean(text: object) -> str:
    return str(text or "").strip()


def parse_flexible_date(text: object) -> Optional[date]:
    value = _clean(text)
    if not _EXACT_RE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def is_exact_date(text: object) -> bool:
    return parse_flexible_date(text) is not None


def validate_flexible_date(text: object, allow_empty: bool = True) -> Tuple[bool, str]:
    value = _clean(text)
    if not value:
        return (True, "") if allow_empty else (False, "Tarih boş bırakılamaz.")
    upper = value.upper()
    if upper in _SPECIALS:
        return True, ""
    if _DAY_TBD_RE.fullmatch(value):
        month = int(value[5:7])
        if 1 <= month <= 12:
            return True, ""
        return False, "Ay 01-12 arasında olmalı."
    if _MONTH_DAY_TBD_RE.fullmatch(value):
        return True, ""
    if _EXACT_RE.fullmatch(value):
        return (True, "") if parse_flexible_date(value) else (False, "Geçersiz kesin tarih.")
    return False, "Tarih YYYY-MM-DD, YYYY-MM-TBD, YYYY-TBD-TBD, TBD veya - olmalı."


def flexible_or_blank(text: object) -> str:
    value = _clean(text)
    ok, _message = validate_flexible_date(value, allow_empty=True)
    if not ok:
        return ""
    if value.upper() in _SPECIALS:
        return value.upper()
    if _DAY_TBD_RE.fullmatch(value) or _MONTH_DAY_TBD_RE.fullmatch(value):
        return value.upper()
    return value


def format_flexible_date(text: object) -> str:
    value = flexible_or_blank(text)
    if not value:
        return "-"
    if is_exact_date(value):
        return value
    return "Belirsiz" if value.upper() != "-" else "-"
