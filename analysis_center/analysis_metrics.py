from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping

from .analysis_deadlines import classify_deadline_rows
from .analysis_models import NormalizedAnalysisData
from .analysis_utils import (
    is_acceptance_completed,
    is_completed_status,
    is_record_completed,
    normalize_status_bucket,
    normalize_text,
    parse_date,
    text_value,
)


def _text(value: Any) -> str:
    return text_value(value)


def _norm(value: Any) -> str:
    return normalize_text(value)


def _date(value: Any) -> date | None:
    return parse_date(value)


def _completed_status(status: Any) -> bool:
    return is_completed_status(status)


def _status_bucket(status: Any) -> str:
    return normalize_status_bucket(status)


def _record_completed(item: Mapping[str, Any]) -> bool:
    return is_record_completed(item)


def _acceptance_completed(item: Mapping[str, Any]) -> bool:
    return is_acceptance_completed(item)


def _dist(counter: Counter) -> List[Dict[str, Any]]:
    return [{"label": str(label), "value": int(value)} for label, value in counter.most_common()]


def _acceptance_summary(acceptances: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(acceptances)
    table = []
    status_counter = Counter(_status_bucket(item.get("status")) for item in rows)
    completed = 0
    for item in rows:
        done = _acceptance_completed(item)
        completed += 1 if done else 0
        table.append({
            "platform": _text(item.get("platform")),
            "contract_no": _text(item.get("contract_no")),
            "system_name": _text(item.get("system_name")),
            "name": _text(item.get("name")),
            "status": _text(item.get("status")),
            "planned_acceptance_date": _text(item.get("planned_acceptance_date")),
            "acceptance_date": _text(item.get("acceptance_date")),
            "planned_total": float(item.get("planned_total") or 0),
            "delivered_total": float(item.get("delivered_total") or 0),
            "completed": done,
        })
    return {
        "total": len(rows),
        "completed": completed,
        "open": max(0, len(rows) - completed),
        "status_distribution": _dist(status_counter),
        "table": table,
    }


def _platform_table(contracts: Iterable[Mapping[str, Any]], acceptances: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    by_platform: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"platform": "", "contract_count": 0, "completed_contract_count": 0, "acceptance_count": 0, "completed_acceptance_count": 0})
    for item in contracts:
        p = _text(item.get("platform")) or "Eksik platform"
        row = by_platform[p]
        row["platform"] = p
        row["contract_count"] += 1
        row["completed_contract_count"] += 1 if _record_completed(item) else 0
    for item in acceptances:
        p = _text(item.get("platform")) or "Eksik platform"
        row = by_platform[p]
        row["platform"] = p
        row["acceptance_count"] += 1
        row["completed_acceptance_count"] += 1 if _acceptance_completed(item) else 0
    return sorted(by_platform.values(), key=lambda r: (-r["contract_count"], r["platform"]))


def compute_metrics(data: NormalizedAnalysisData, today: date | None = None, upcoming_days: int = 60) -> Dict[str, Any]:
    current = today or date.today()
    contracts = list(data.get("contracts", []))
    acceptances = list(data.get("acceptances", []))
    deadlines = classify_deadline_rows(data.get("deadlines", []), today=current, upcoming_days=upcoming_days)
    acceptance_summary = _acceptance_summary(acceptances)
    return {
        "generated_at": current.isoformat(),
        "total_contracts": len(contracts),
        "total_platforms": len(data.get("platforms", [])),
        "total_systems": len(data.get("systems", [])),
        "total_components": len(data.get("components", [])),
        "total_users": len(data.get("users", [])),
        "total_tags": len(data.get("tags", [])),
        "completed_contract_count": sum(1 for item in contracts if _record_completed(item)),
        "not_started_contract_count": sum(1 for item in contracts if _status_bucket(item.get("status")) == "Başlanmadı"),
        "in_progress_contract_count": sum(1 for item in contracts if _status_bucket(item.get("status")) == "Devam ediyor"),
        "total_acceptances": acceptance_summary["total"],
        "completed_acceptances": acceptance_summary["completed"],
        "open_acceptances": acceptance_summary["open"],
        "upcoming_deadline_count": len(deadlines["upcoming"]),
        "past_deadline_count": len(deadlines["past"]),
        "unknown_deadline_count": len(deadlines["unknown"]),
        "platform_distribution": _dist(Counter(_text(item.get("platform")) or "Eksik platform" for item in contracts)),
        "platform_table": _platform_table(contracts, acceptances),
        "status_distribution": _dist(Counter(_status_bucket(item.get("status")) for item in contracts)),
        "acceptance_status_distribution": acceptance_summary["status_distribution"],
        "acceptance_table": acceptance_summary["table"],
        "upcoming_deadlines": deadlines["upcoming"],
        "past_deadlines": deadlines["past"],
        "unknown_deadlines": deadlines["unknown"],
        "all_deadlines": deadlines["all"],
    }
