from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .analysis_models import NormalizedAnalysisData
from .analysis_settings import COMPLETED_STATUS_KEYS, IN_PROGRESS_STATUS_KEYS, NOT_STARTED_STATUS_KEYS


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    text = _text(value).replace("ı", "i").replace("İ", "i").casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _date(value: Any) -> Optional[date]:
    text = _text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date()
    except Exception:
        return None


def _completed_status(status: Any) -> bool:
    return _norm(status) in {_norm(item) for item in COMPLETED_STATUS_KEYS}


def _status_bucket(status: Any) -> str:
    key = _norm(status)
    if not key:
        return "Eksik durum"
    if key in {_norm(item) for item in COMPLETED_STATUS_KEYS}:
        return "Tamamlanan"
    if key in {_norm(item) for item in NOT_STARTED_STATUS_KEYS}:
        return "Başlanmadı"
    if key in {_norm(item) for item in IN_PROGRESS_STATUS_KEYS}:
        return "Devam ediyor"
    return _text(status)


def _record_completed(item: Mapping[str, Any]) -> bool:
    return _completed_status(item.get("status")) or bool(_text(item.get("acceptance_date")))


def _acceptance_completed(item: Mapping[str, Any]) -> bool:
    if _record_completed(item):
        return True
    planned = float(item.get("planned_total") or 0)
    delivered = float(item.get("delivered_total") or 0)
    return planned > 0 and delivered >= planned


def _dist(counter: Counter) -> List[Dict[str, Any]]:
    return [{"label": str(label), "value": int(value)} for label, value in counter.most_common()]


def _deadline_rows(deadlines: Iterable[Mapping[str, Any]], today: date, upcoming_days: int) -> Dict[str, List[Dict[str, Any]]]:
    limit = today + timedelta(days=max(1, int(upcoming_days or 60)))
    upcoming: List[Dict[str, Any]] = []
    past: List[Dict[str, Any]] = []
    all_rows: List[Dict[str, Any]] = []
    for item in deadlines:
        due = _date(item.get("due_date"))
        if due is None:
            continue
        row = {"entity": _text(item.get("entity")), "platform": _text(item.get("platform")), "contract_no": _text(item.get("contract_no")), "name": _text(item.get("name")), "due_date": due.isoformat(), "status": _text(item.get("status")), "days": (due - today).days}
        all_rows.append(row)
        if _completed_status(item.get("status")):
            continue
        if due < today:
            past.append(row)
        elif today <= due <= limit:
            upcoming.append(row)
    for rows in (upcoming, past, all_rows):
        rows.sort(key=lambda r: (r["due_date"], r["platform"], r["contract_no"]))
    return {"upcoming": upcoming, "past": past, "all": all_rows}


def _acceptance_summary(acceptances: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(acceptances)
    table = []
    status_counter = Counter(_status_bucket(item.get("status")) for item in rows)
    completed = 0
    for item in rows:
        done = _acceptance_completed(item)
        completed += 1 if done else 0
        table.append({"platform": _text(item.get("platform")), "contract_no": _text(item.get("contract_no")), "system_name": _text(item.get("system_name")), "name": _text(item.get("name")), "status": _text(item.get("status")), "acceptance_date": _text(item.get("acceptance_date")), "planned_total": float(item.get("planned_total") or 0), "delivered_total": float(item.get("delivered_total") or 0), "completed": done})
    return {"total": len(rows), "completed": completed, "open": max(0, len(rows) - completed), "status_distribution": _dist(status_counter), "table": table}


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


def _missing_items(data: NormalizedAnalysisData) -> List[Dict[str, Any]]:
    items = [dict(item) for item in data.get("health_items", [])]
    if items:
        return items
    out: List[Dict[str, Any]] = []
    for contract in data.get("contracts", []):
        for field, label in (("platform", "Eksik platform bilgisi"), ("contract_no", "Eksik sözleşme numarası"), ("status", "Eksik durum bilgisi"), ("completion_date", "Eksik termin tarihi"), ("user", "Eksik kullanıcı bilgisi")):
            if not _text(contract.get(field)):
                out.append({"entity": "contract", "platform": _text(contract.get("platform")), "contract_no": _text(contract.get("contract_no")), "field": field, "label": label})
        if not contract.get("tags"):
            out.append({"entity": "contract", "platform": _text(contract.get("platform")), "contract_no": _text(contract.get("contract_no")), "field": "tags", "label": "Etiketsiz kayıt"})
    return out


def compute_metrics(data: NormalizedAnalysisData, today: date | None = None, upcoming_days: int = 60) -> Dict[str, Any]:
    current = today or date.today()
    contracts = list(data.get("contracts", []))
    acceptances = list(data.get("acceptances", []))
    deadlines = _deadline_rows(data.get("deadlines", []), current, upcoming_days)
    acceptance_summary = _acceptance_summary(acceptances)
    missing = _missing_items(data)
    unlabeled = [{"platform": _text(item.get("platform")), "contract_no": _text(item.get("contract_no")), "contract_type": _text(item.get("contract_type")), "status": _text(item.get("status"))} for item in contracts if not item.get("tags")]
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
        "platform_distribution": _dist(Counter(_text(item.get("platform")) or "Eksik platform" for item in contracts)),
        "platform_table": _platform_table(contracts, acceptances),
        "status_distribution": _dist(Counter(_status_bucket(item.get("status")) for item in contracts)),
        "acceptance_status_distribution": acceptance_summary["status_distribution"],
        "acceptance_table": acceptance_summary["table"],
        "upcoming_deadlines": deadlines["upcoming"],
        "past_deadlines": deadlines["past"],
        "all_deadlines": deadlines["all"],
        "missing_info_items": missing,
        "missing_info_count": len(missing),
        "unlabeled_contracts": unlabeled,
        "unlabeled_contract_count": len(unlabeled),
    }
