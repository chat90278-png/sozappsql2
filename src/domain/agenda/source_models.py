from __future__ import annotations

from dataclasses import dataclass


_ENTITY_TYPES = frozenset({"contract", "system", "delivery"})


def _positive_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


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
        entity_type = str(self.entity_type or "").strip().lower()
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
            object.__setattr__(self, field_name, str(getattr(self, field_name) or "").strip())

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
