from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping

from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)


@dataclass(frozen=True)
class AgendaItem:
    key: str
    provider_code: str
    kind: str
    lifecycle_type: AgendaLifecycleType
    title: str
    description: str
    priority: int
    severity: AgendaSeverity
    version: str
    presentation_scope: AgendaPresentationProfileCode | None = None
    contract_id: int | None = None
    platform: str = ""
    contract_no: str = ""
    contract_type: str = ""
    system_id: int | None = None
    delivery_id: int | None = None
    share_package_id: str = ""
    actor_staff_id: int | None = None
    actor_name: str = ""
    event_at: datetime | str | None = None
    effective_date: date | datetime | str | None = None
    remaining_days: int | None = None
    reason_code: str = ""
    reason_text: str = ""
    detail_payload: Mapping[str, Any] = field(default_factory=dict)
    action_hints: tuple[str, ...] = ()
    supports_snooze: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail_payload", MappingProxyType(dict(self.detail_payload or {})))
        object.__setattr__(self, "action_hints", tuple(str(hint) for hint in (self.action_hints or ())))


@dataclass(frozen=True)
class AgendaItemState:
    staff_id: int
    agenda_key: str
    first_presented_at: str | None = None
    last_presented_at: str | None = None
    seen_at: str | None = None
    seen_version: str = ""
    snoozed_until: str | None = None
    snoozed_version: str = ""
    snoozed_severity: str = ""
    dismissed_at: str | None = None
    dismissed_version: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class AgendaPresentationProfile:
    code: AgendaPresentationProfileCode
    display_name: str
    description: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", frozenset(str(code) for code in self.permissions))


@dataclass(frozen=True)
class AgendaResult:
    profile: AgendaPresentationProfile
    items: tuple[AgendaItem, ...]
    new_count: int
    active_count: int
    counts_by_kind: Mapping[str, int]
    new_keys: frozenset[str] = field(default_factory=frozenset)
    states_by_key: Mapping[str, AgendaItemState] = field(default_factory=dict)
    snoozed_count: int = 0
    filtered_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "counts_by_kind", MappingProxyType(dict(self.counts_by_kind)))
        object.__setattr__(self, "new_keys", frozenset(str(key) for key in self.new_keys))
        object.__setattr__(self, "states_by_key", MappingProxyType(dict(self.states_by_key)))
        for field_name in ("new_count", "active_count", "snoozed_count", "filtered_count"):
            value = int(getattr(self, field_name))
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative.")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class AgendaContext:
    now: datetime
    today: date
    presentation_profile: AgendaPresentationProfile
    current_staff: Mapping[str, Any] | None = None
    staff_id: int | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    personal_contract_ids: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        staff_snapshot = None if self.current_staff is None else MappingProxyType(dict(self.current_staff))
        object.__setattr__(self, "current_staff", staff_snapshot)
        object.__setattr__(self, "permissions", frozenset(str(code) for code in self.permissions))
        object.__setattr__(self, "personal_contract_ids", frozenset(int(contract_id) for contract_id in self.personal_contract_ids))
