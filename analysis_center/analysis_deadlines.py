from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping

from .analysis_models import NormalizedAnalysisData
from .analysis_utils import (
    is_acceptance_completed,
    is_completed_status,
    is_record_completed,
    parse_date,
    text_value,
)


class DeadlineDateStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class DeadlineDateValue:
    raw_value: str
    parsed_date: date | None
    status: DeadlineDateStatus


_MISSING_DATE_MARKERS = {"-", "—"}


def classify_deadline_date(value: Any) -> DeadlineDateValue:
    """Classify a termin value without changing the application's global date parser."""

    if isinstance(value, datetime):
        return DeadlineDateValue(value.isoformat(), value.date(), DeadlineDateStatus.KNOWN)
    if isinstance(value, date):
        return DeadlineDateValue(value.isoformat(), value, DeadlineDateStatus.KNOWN)

    raw_value = text_value(value)
    if not raw_value or raw_value in _MISSING_DATE_MARKERS:
        return DeadlineDateValue(raw_value, None, DeadlineDateStatus.MISSING)

    parsed = parse_date(raw_value)
    if parsed is not None:
        return DeadlineDateValue(raw_value, parsed, DeadlineDateStatus.KNOWN)
    return DeadlineDateValue(raw_value, None, DeadlineDateStatus.UNKNOWN)


def _deadline_source(
    entity: str,
    item: Mapping[str, Any],
) -> tuple[str, Any]:
    if entity == "acceptance":
        for field_name in (
            "planned_acceptance_date",
            "planned_delivery_date",
            "completion_date",
        ):
            value = item.get(field_name)
            if classify_deadline_date(value).status != DeadlineDateStatus.MISSING:
                return field_name, value
        return "planned_acceptance_date", ""
    return "completion_date", item.get("completion_date")


def build_deadline_rows(data: NormalizedAnalysisData) -> list[dict[str, Any]]:
    """Build one canonical termin event per contract, system or acceptance record."""

    rows: list[dict[str, Any]] = []
    source_specs = (
        ("contracts", "contract", "contract_type"),
        ("systems", "system", "name"),
        ("acceptances", "acceptance", "name"),
    )
    for source_key, entity, name_key in source_specs:
        for index, item in enumerate(data.get(source_key, []), start=1):
            date_field, raw_date = _deadline_source(entity, item)
            classified = classify_deadline_date(raw_date)
            if classified.status == DeadlineDateStatus.MISSING:
                continue
            source_id = item.get("id")
            identity = str(source_id) if source_id is not None else str(index)
            completed = (
                is_acceptance_completed(item)
                if entity == "acceptance"
                else is_record_completed(item)
            )
            rows.append({
                "event_id": f"{entity}:{identity}",
                "source_type": entity,
                "source_id": source_id,
                "entity": entity,
                "platform": text_value(item.get("platform")),
                "contract_no": text_value(item.get("contract_no")),
                "name": text_value(item.get(name_key)) or entity,
                "date_field": date_field,
                "raw_date_value": classified.raw_value,
                "due_date": classified.raw_value,
                "date_status": classified.status.value,
                "completed": completed,
                "status": text_value(item.get("status")),
            })
    return rows


def _normalized_deadline_row(item: Mapping[str, Any], today: date) -> dict[str, Any] | None:
    raw_value = item.get("raw_date_value", item.get("due_date"))
    classified = classify_deadline_date(raw_value)
    if classified.status == DeadlineDateStatus.MISSING:
        return None

    completed_value = item.get("completed")
    completed = (
        bool(completed_value)
        if completed_value is not None
        else is_completed_status(item.get("status"))
    )
    row = {
        "event_id": text_value(item.get("event_id")),
        "source_type": text_value(item.get("source_type") or item.get("entity")),
        "source_id": item.get("source_id"),
        "entity": text_value(item.get("entity") or item.get("source_type")),
        "platform": text_value(item.get("platform")),
        "contract_no": text_value(item.get("contract_no")),
        "name": text_value(item.get("name")),
        "date_field": text_value(item.get("date_field")) or "due_date",
        "raw_date_value": classified.raw_value,
        "due_date": classified.parsed_date.isoformat() if classified.parsed_date else classified.raw_value,
        "date_status": classified.status.value,
        "completed": completed,
        "status": text_value(item.get("status")),
        "days": (classified.parsed_date - today).days if classified.parsed_date else None,
    }
    return row


def classify_deadline_rows(
    deadlines: Iterable[Mapping[str, Any]],
    *,
    today: date,
    upcoming_days: int,
) -> dict[str, list[dict[str, Any]]]:
    """Classify active known/unknown termin events with deterministic ordering."""

    limit = today + timedelta(days=max(1, int(upcoming_days or 60)))
    upcoming: list[dict[str, Any]] = []
    past: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    for index, item in enumerate(deadlines):
        row = _normalized_deadline_row(item, today)
        if row is None:
            continue
        event_id = row["event_id"] or f"legacy:{row['entity']}:{row['source_id']}:{index}"
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        row["event_id"] = event_id
        all_rows.append(row)
        if row["completed"]:
            continue
        if row["date_status"] == DeadlineDateStatus.UNKNOWN.value:
            unknown.append(row)
            continue
        due = parse_date(row["due_date"])
        if due is None:
            unknown.append(row)
        elif due < today:
            past.append(row)
        elif due <= limit:
            upcoming.append(row)

    known_key = lambda row: (
        str(row.get("due_date") or ""),
        str(row.get("platform") or ""),
        str(row.get("contract_no") or ""),
        str(row.get("event_id") or ""),
    )
    unknown_key = lambda row: (
        str(row.get("platform") or ""),
        str(row.get("contract_no") or ""),
        str(row.get("entity") or ""),
        str(row.get("name") or ""),
        str(row.get("event_id") or ""),
    )
    upcoming.sort(key=known_key)
    past.sort(key=known_key)
    unknown.sort(key=unknown_key)
    all_rows.sort(
        key=lambda row: (
            row.get("date_status") != DeadlineDateStatus.KNOWN.value,
            *known_key(row),
        )
    )
    known_columns = ("platform", "contract_no", "entity", "name", "due_date", "days", "status")
    return {
        "upcoming": [{key: row.get(key) for key in known_columns} for row in upcoming],
        "past": [{key: row.get(key) for key in known_columns} for row in past],
        "unknown": unknown,
        "all": all_rows,
    }
