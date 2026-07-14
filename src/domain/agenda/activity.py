from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType

ACTIVITY_PROVIDER_CODE = "activity"
ACTIVITY_SOURCE_LOOKBACK_DAYS = 8

CONTRACT_ACTIVITY_FIELDS_BY_ACTION = MappingProxyType(
    {
        "contract_updated": (
            "completion_date",
            "acceptance_date",
        ),
        "contract_status_changed": (
            "status",
        ),
    }
)

CONTRACT_ACTIVITY_FIELD_PRESENTATION = MappingProxyType(
    {
        "status": MappingProxyType(
            {
                "title_label": "durumu değişti",
                "reason_text": "STATUS_CHANGED",
            }
        ),
        "completion_date": MappingProxyType(
            {
                "title_label": "tamamlanma tarihi değişti",
                "reason_text": "COMPLETION_DATE_CHANGED",
            }
        ),
        "acceptance_date": MappingProxyType(
            {
                "title_label": "kabul tarihi değişti",
                "reason_text": "ACCEPTANCE_DATE_CHANGED",
            }
        ),
    }
)


def activity_source_cutoff(now: datetime) -> datetime:
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime value.")
    return now.replace(tzinfo=None) - timedelta(days=ACTIVITY_SOURCE_LOOKBACK_DAYS)


__all__ = [
    "ACTIVITY_PROVIDER_CODE",
    "ACTIVITY_SOURCE_LOOKBACK_DAYS",
    "CONTRACT_ACTIVITY_FIELDS_BY_ACTION",
    "CONTRACT_ACTIVITY_FIELD_PRESENTATION",
    "activity_source_cutoff",
]
