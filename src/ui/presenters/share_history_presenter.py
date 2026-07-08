from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from src.models.share_models import (
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
)
from src.services.share_history_service import ShareHistoryRecord


@dataclass(frozen=True)
class ShareHistoryStatusPresentation:
    raw_status: str
    label: str
    role: str


@dataclass(frozen=True)
class ShareHistorySummary:
    total: int
    by_status: dict[str, int]
    open_count: int
    merged_count: int
    partially_merged_count: int
    cancelled_count: int
    rejected_count: int
    returned_count: int


_STATUS_LABELS = {
    SHARE_STATUS_OPEN: ("Açık", "info"),
    SHARE_STATUS_RETURNED: ("Geri Döndü", "attention"),
    SHARE_STATUS_MERGED: ("Birleştirildi", "success"),
    SHARE_STATUS_PARTIALLY_MERGED: ("Kısmi Birleştirildi", "warning"),
    SHARE_STATUS_CANCELLED: ("İptal Edildi", "neutral"),
    SHARE_STATUS_REJECTED: ("Reddedildi", "error"),
}

_PERMISSION_LABELS = {
    "view": "Görüntüleme",
    "VIEW": "Görüntüleme",
    "goruntule": "Görüntüleme",
    "edit": "Düzenleme",
    "EDIT": "Düzenleme",
    "duzenle": "Düzenleme",
}


def present_share_status(status: str) -> ShareHistoryStatusPresentation:
    raw = str(status or "").strip()
    label, role = _STATUS_LABELS.get(raw, ("Bilinmeyen Durum", "neutral"))
    return ShareHistoryStatusPresentation(raw, label, role)


def present_share_permission(permission_mode: str) -> str:
    return _PERMISSION_LABELS.get(str(permission_mode or "").strip(), "Bilinmeyen Yetki")


def format_share_history_datetime(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Tarih bilgisi yok"
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    return parsed.strftime("%d.%m.%Y %H:%M")


def display_share_filename(record: ShareHistoryRecord) -> str:
    name = str(record.exported_filename or "").strip()
    if name:
        return name
    package_id = str(record.share_package_id or "").strip()
    if package_id:
        return f"Paylaşım {package_id[:8]}"
    return "Paylaşım paketi"


def summarize_share_history(records: Iterable[ShareHistoryRecord]) -> ShareHistorySummary:
    by_status: dict[str, int] = {}
    total = 0
    for record in records:
        total += 1
        status = str(record.status or "").strip()
        by_status[status] = by_status.get(status, 0) + 1
    return ShareHistorySummary(
        total=total,
        by_status=by_status,
        open_count=by_status.get(SHARE_STATUS_OPEN, 0),
        merged_count=by_status.get(SHARE_STATUS_MERGED, 0),
        partially_merged_count=by_status.get(SHARE_STATUS_PARTIALLY_MERGED, 0),
        cancelled_count=by_status.get(SHARE_STATUS_CANCELLED, 0),
        rejected_count=by_status.get(SHARE_STATUS_REJECTED, 0),
        returned_count=by_status.get(SHARE_STATUS_RETURNED, 0),
    )
