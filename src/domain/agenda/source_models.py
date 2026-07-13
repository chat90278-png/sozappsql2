from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from src.domain.agenda.activity import CONTRACT_ACTIVITY_FIELDS_BY_ACTION
from src.models.share_models import SHARE_PACKAGE_STATUSES


_ENTITY_TYPES = frozenset({"contract", "system", "delivery"})


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return parsed


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name)


def _text(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be bool-compatible.") from exc


@dataclass(frozen=True)
class AgendaCalendarSource:
    entity_type: str
    entity_id: int
    contract_id: int
    system_id: int | None = None
    delivery_id: int | None = None
    platform: str = ""
    contract_no: str = ""
    contract_type: str = ""
    system_name: str = ""
    delivery_name: str = ""
    status: str = ""
    completion_date: str = ""
    acceptance_date: str = ""
    planned_acceptance_date: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        entity_type = _text(self.entity_type).lower()
        if entity_type not in _ENTITY_TYPES:
            raise ValueError(f"Unsupported agenda calendar entity_type: {entity_type!r}")
        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "entity_id", _positive_int(self.entity_id, "entity_id"))
        object.__setattr__(self, "contract_id", _positive_int(self.contract_id, "contract_id"))
        if self.system_id is not None:
            object.__setattr__(self, "system_id", _positive_int(self.system_id, "system_id"))
        if self.delivery_id is not None:
            object.__setattr__(self, "delivery_id", _positive_int(self.delivery_id, "delivery_id"))
        if entity_type == "system" and self.system_id is None:
            raise ValueError("system sources require system_id.")
        if entity_type == "delivery" and self.delivery_id is None:
            raise ValueError("delivery sources require delivery_id.")
        for field_name in (
            "platform", "contract_no", "contract_type", "system_name", "delivery_name",
            "status", "completion_date", "acceptance_date", "planned_acceptance_date", "note",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))

    def as_calendar_item(self) -> dict:
        item_type = {
            "contract": "Sözleşme",
            "system": "Sistem",
            "delivery": "Teslimat",
        }[self.entity_type]
        return {
            "type": item_type,
            "status": self.status,
            "completion_date": self.completion_date,
            "acceptance_date": self.acceptance_date,
            "planned_acceptance_date": self.planned_acceptance_date,
            "platform": self.platform,
            "contract_no": self.contract_no,
            "contract_type": self.contract_type,
            "system_name": self.system_name,
            "delivery_name": self.delivery_name,
            "note": self.note,
        }


@dataclass(frozen=True)
class ReturnedShareAgendaSource:
    registry_id: int
    share_package_id: str
    contract_id: int

    contract_merge_uid: str = ""
    contract_no: str = ""
    contract_type: str = ""
    platform: str = ""

    status: str = ""
    source_contract_revision: int = 0
    permission_mode: str = ""
    share_format_version: int = 0
    snapshot_format_version: int = 0
    base_snapshot_sha256: str = ""

    created_at: str = ""
    created_by_staff_id: int | None = None
    created_by_full_name: str = ""
    exported_filename: str = ""

    last_imported_at: str = ""
    last_imported_by_staff_id: int | None = None
    last_remote_snapshot_sha256: str = ""
    return_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _positive_int(self.registry_id, "registry_id"))
        package_id = _text(self.share_package_id)
        if not package_id:
            raise ValueError("share_package_id must be a non-empty stable string.")
        object.__setattr__(self, "share_package_id", package_id)
        object.__setattr__(self, "contract_id", _positive_int(self.contract_id, "contract_id"))

        status = _text(self.status).upper()
        if status not in SHARE_PACKAGE_STATUSES:
            raise ValueError(f"Unsupported share package status: {status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "source_contract_revision",
            _non_negative_int(self.source_contract_revision, "source_contract_revision"),
        )
        object.__setattr__(
            self,
            "share_format_version",
            _non_negative_int(self.share_format_version, "share_format_version"),
        )
        object.__setattr__(
            self,
            "snapshot_format_version",
            _non_negative_int(self.snapshot_format_version, "snapshot_format_version"),
        )
        object.__setattr__(self, "return_count", _non_negative_int(self.return_count, "return_count"))
        object.__setattr__(
            self,
            "created_by_staff_id",
            _optional_positive_int(self.created_by_staff_id, "created_by_staff_id"),
        )
        object.__setattr__(
            self,
            "last_imported_by_staff_id",
            _optional_positive_int(self.last_imported_by_staff_id, "last_imported_by_staff_id"),
        )

        for field_name in (
            "contract_merge_uid",
            "contract_no",
            "contract_type",
            "platform",
            "permission_mode",
            "base_snapshot_sha256",
            "created_at",
            "created_by_full_name",
            "exported_filename",
            "last_imported_at",
            "last_remote_snapshot_sha256",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))


@dataclass(frozen=True)
class DocumentLockAgendaSource:
    contract_id: int

    contract_no: str = ""
    contract_type: str = ""
    platform: str = ""

    is_locked: bool | int = True
    locked_by_staff_id: int | None = None
    locked_by_device_name: str = ""
    locked_by_full_name: str = ""
    locked_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _positive_int(self.contract_id, "contract_id"))
        object.__setattr__(self, "is_locked", _bool(self.is_locked, "is_locked"))
        object.__setattr__(
            self,
            "locked_by_staff_id",
            _optional_positive_int(self.locked_by_staff_id, "locked_by_staff_id"),
        )
        for field_name in (
            "contract_no",
            "contract_type",
            "platform",
            "locked_by_device_name",
            "locked_by_full_name",
            "locked_at",
            "updated_at",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))
        if not self.locked_at:
            raise ValueError("locked_at must be a non-empty timestamp string.")


@dataclass(frozen=True)
class ActivityAgendaSource:
    log_id: int
    contract_id: int
    action: str
    created_at: str

    contract_no: str = ""
    contract_type: str = ""
    platform: str = ""

    entity_type: str = "contract"
    entity_id: str = ""

    actor_name: str = ""
    device_name: str = ""
    log_source: str = ""
    message: str = ""

    before_values: Mapping[str, Any] = field(default_factory=dict)
    after_values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        log_id = _positive_int(self.log_id, "log_id")
        contract_id = _positive_int(self.contract_id, "contract_id")
        action = _text(self.action)
        created_at = _text(self.created_at)
        entity_type = _text(self.entity_type).lower()
        entity_id = _text(self.entity_id) or str(contract_id)

        if action not in CONTRACT_ACTIVITY_FIELDS_BY_ACTION:
            raise ValueError(f"Unsupported contract activity action: {action!r}")
        if not created_at:
            raise ValueError("created_at must be a non-empty timestamp string.")
        if entity_type != "contract":
            raise ValueError("entity_type must be 'contract'.")
        if entity_id != str(contract_id):
            raise ValueError("entity_id must exactly match contract_id.")
        if not isinstance(self.before_values, Mapping):
            raise TypeError("before_values must be a mapping.")
        if not isinstance(self.after_values, Mapping):
            raise TypeError("after_values must be a mapping.")

        object.__setattr__(self, "log_id", log_id)
        object.__setattr__(self, "contract_id", contract_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "entity_id", entity_id)
        for field_name in (
            "contract_no",
            "contract_type",
            "platform",
            "actor_name",
            "device_name",
            "log_source",
            "message",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))
        object.__setattr__(
            self,
            "before_values",
            MappingProxyType(dict(self.before_values)),
        )
        object.__setattr__(
            self,
            "after_values",
            MappingProxyType(dict(self.after_values)),
        )


@dataclass(frozen=True)
class AgendaSourceBundle:
    calendar: tuple[AgendaCalendarSource, ...] = ()
    returned_shares: tuple[ReturnedShareAgendaSource, ...] = ()
    document_locks: tuple[DocumentLockAgendaSource, ...] = ()
    activities: tuple[ActivityAgendaSource, ...] = ()

    def __post_init__(self) -> None:
        calendar = tuple(self.calendar or ())
        returned_shares = tuple(self.returned_shares or ())
        document_locks = tuple(self.document_locks or ())
        activities = tuple(self.activities or ())
        if any(not isinstance(source, AgendaCalendarSource) for source in calendar):
            raise TypeError("calendar must contain only AgendaCalendarSource values.")
        if any(not isinstance(source, ReturnedShareAgendaSource) for source in returned_shares):
            raise TypeError("returned_shares must contain only ReturnedShareAgendaSource values.")
        if any(not isinstance(source, DocumentLockAgendaSource) for source in document_locks):
            raise TypeError("document_locks must contain only DocumentLockAgendaSource values.")
        if any(not isinstance(source, ActivityAgendaSource) for source in activities):
            raise TypeError("activities must contain only ActivityAgendaSource values.")
        object.__setattr__(self, "calendar", calendar)
        object.__setattr__(self, "returned_shares", returned_shares)
        object.__setattr__(self, "document_locks", document_locks)
        object.__setattr__(self, "activities", activities)
