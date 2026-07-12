from __future__ import annotations

from dataclasses import dataclass

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
class AgendaSourceBundle:
    calendar: tuple[AgendaCalendarSource, ...] = ()
    returned_shares: tuple[ReturnedShareAgendaSource, ...] = ()

    def __post_init__(self) -> None:
        calendar = tuple(self.calendar or ())
        returned_shares = tuple(self.returned_shares or ())
        if any(not isinstance(source, AgendaCalendarSource) for source in calendar):
            raise TypeError("calendar must contain only AgendaCalendarSource values.")
        if any(not isinstance(source, ReturnedShareAgendaSource) for source in returned_shares):
            raise TypeError("returned_shares must contain only ReturnedShareAgendaSource values.")
        object.__setattr__(self, "calendar", calendar)
        object.__setattr__(self, "returned_shares", returned_shares)
