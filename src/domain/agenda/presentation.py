from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from src.domain.agenda.models import (
    AgendaItem,
    AgendaItemState,
    AgendaPresentationProfile,
    AgendaResult,
)


def _normalize_limit(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer.") from exc
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return normalized


@dataclass(frozen=True)
class AgendaPresentationSnapshot:
    profile: AgendaPresentationProfile
    all_items: tuple[AgendaItem, ...]
    compact_items: tuple[AgendaItem, ...]
    detail_items: tuple[AgendaItem, ...]

    active_count: int
    new_count: int
    snoozed_count: int
    filtered_count: int

    counts_by_kind: Mapping[str, int] = field(default_factory=dict)
    counts_by_severity: Mapping[str, int] = field(default_factory=dict)

    new_keys: frozenset[str] = field(default_factory=frozenset)
    states_by_key: Mapping[str, AgendaItemState] = field(default_factory=dict)

    compact_limit: int = 2
    detail_limit: int = 20
    has_more: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "all_items", tuple(self.all_items or ()))
        object.__setattr__(self, "compact_items", tuple(self.compact_items or ()))
        object.__setattr__(self, "detail_items", tuple(self.detail_items or ()))
        object.__setattr__(self, "counts_by_kind", MappingProxyType(dict(self.counts_by_kind or {})))
        object.__setattr__(self, "counts_by_severity", MappingProxyType(dict(self.counts_by_severity or {})))
        object.__setattr__(self, "new_keys", frozenset(str(key) for key in (self.new_keys or ())))
        object.__setattr__(self, "states_by_key", MappingProxyType(dict(self.states_by_key or {})))

        for field_name in ("active_count", "new_count", "snoozed_count", "filtered_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool):
                raise ValueError(f"{field_name} must be a non-negative integer.")
            normalized = int(value)
            if normalized < 0:
                raise ValueError(f"{field_name} must be a non-negative integer.")
            object.__setattr__(self, field_name, normalized)

        object.__setattr__(self, "compact_limit", _normalize_limit(self.compact_limit, "compact_limit"))
        object.__setattr__(self, "detail_limit", _normalize_limit(self.detail_limit, "detail_limit"))
        object.__setattr__(self, "has_more", bool(self.has_more))


def project_agenda_result(
    result: AgendaResult,
    *,
    compact_limit: int = 2,
    detail_limit: int = 20,
) -> AgendaPresentationSnapshot:
    normalized_compact_limit = _normalize_limit(compact_limit, "compact_limit")
    normalized_detail_limit = _normalize_limit(detail_limit, "detail_limit")
    all_items = tuple(result.items)
    severity_counts = Counter(item.severity.value for item in all_items)

    return AgendaPresentationSnapshot(
        profile=result.profile,
        all_items=all_items,
        compact_items=all_items[:normalized_compact_limit],
        detail_items=all_items[:normalized_detail_limit],
        active_count=result.active_count,
        new_count=result.new_count,
        snoozed_count=result.snoozed_count,
        filtered_count=result.filtered_count,
        counts_by_kind=result.counts_by_kind,
        counts_by_severity=dict(severity_counts),
        new_keys=result.new_keys,
        states_by_key=result.states_by_key,
        compact_limit=normalized_compact_limit,
        detail_limit=normalized_detail_limit,
        has_more=result.active_count > normalized_detail_limit,
    )
