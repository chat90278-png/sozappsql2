from __future__ import annotations

from datetime import date, datetime
import unicodedata
from typing import Optional


def normalize_status(text: str) -> str:
    value = str(text or "").strip().lower().replace("ı", "i")
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def is_completed_status(status: str) -> bool:
    normalized = normalize_status(status)
    return "teslim edildi" in normalized or "tamam" in normalized


def parse_iso_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def contract_timing(deadline, acceptance="", status: str = "", today: Optional[date] = None) -> tuple[str, Optional[int], str]:
    """Return display text, numeric day value and semantic timing kind."""
    deadline_date = parse_iso_date(deadline)
    if not deadline_date:
        return "—", None, "normal"

    if is_completed_status(status):
        acceptance_date = parse_iso_date(acceptance)
        if not acceptance_date:
            return "Teslim tarihi yok", None, "teslim_tarihi_yok"
        diff = (acceptance_date - deadline_date).days
        if diff < 0:
            return f"{abs(diff)} gün erken teslim edildi", diff, "erken_teslim"
        if diff > 0:
            return f"{diff} gün gecikmeli teslim edildi", diff, "gecikmeli_teslim"
        return "Termin gününde teslim edildi", 0, "zamaninda_teslim"

    remaining = (deadline_date - (today or date.today())).days
    return f"{remaining} gün", remaining, "devam_ediyor"
