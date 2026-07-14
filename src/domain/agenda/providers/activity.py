from __future__ import annotations

from typing import Any

from src.domain.agenda.activity import (
    ACTIVITY_PROVIDER_CODE,
    CONTRACT_ACTIVITY_FIELD_PRESENTATION,
    CONTRACT_ACTIVITY_FIELDS_BY_ACTION,
)
from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import ActivityAgendaSource, AgendaSourceBundle


_ALLOWED_SCALAR_TYPES = (str, int, float, bool, type(None))


def _normalized_scalar(value: Any) -> tuple[str, Any] | None:
    if not isinstance(value, _ALLOWED_SCALAR_TYPES):
        return None
    if value is None:
        return ("empty", None)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, str):
        stripped = value.strip()
        return ("empty", None) if not stripped else ("str", stripped)
    if isinstance(value, (int, float)):
        return ("number", value)
    return None


def _display_scalar(normalized: tuple[str, Any]) -> str:
    kind, value = normalized
    if kind == "empty":
        return "Boş"
    return str(value)


class ActivityAgendaProvider:
    code = ACTIVITY_PROVIDER_CODE

    def is_enabled(self, context: AgendaContext) -> bool:
        return "view_contracts" in context.permissions

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        items: list[AgendaItem] = []
        for source in sources.activities:
            fields = CONTRACT_ACTIVITY_FIELDS_BY_ACTION.get(source.action, ())
            for field_name in fields:
                if field_name not in source.before_values and field_name not in source.after_values:
                    continue
                old_value = _normalized_scalar(source.before_values.get(field_name))
                new_value = _normalized_scalar(source.after_values.get(field_name))
                if old_value is None or new_value is None or old_value == new_value:
                    continue

                presentation = CONTRACT_ACTIVITY_FIELD_PRESENTATION[field_name]
                contract_label = source.contract_no or "Sözleşme"
                items.append(
                    AgendaItem(
                        key=build_agenda_key(
                            provider_code=self.code,
                            entity_type="activity_log",
                            entity_id=source.log_id,
                            discriminator=field_name,
                        ),
                        provider_code=self.code,
                        kind="activity",
                        lifecycle_type=AgendaLifecycleType.EVENT,
                        title=f"{contract_label} {presentation['title_label']}",
                        description=(
                            f"{_display_scalar(old_value)} → {_display_scalar(new_value)}"
                        ),
                        priority=450,
                        severity=AgendaSeverity.INFO,
                        version=(
                            f"ACTIVITY:{source.log_id}:{field_name}:{source.created_at}"
                        ),
                        presentation_scope=context.presentation_profile.code,
                        contract_id=source.contract_id,
                        platform=source.platform,
                        contract_no=source.contract_no,
                        contract_type=source.contract_type,
                        actor_staff_id=None,
                        actor_name=source.actor_name,
                        event_at=source.created_at,
                        effective_date=source.created_at,
                        reason_code="CONTRACT_ACTIVITY",
                        reason_text=str(presentation["reason_text"]),
                        detail_payload={
                            "source_type": "activity_log",
                            "log_id": source.log_id,
                            "action": source.action,
                            "entity_type": source.entity_type,
                            "entity_id": source.entity_id,
                            "contract_id": source.contract_id,
                            "field_name": field_name,
                            "old_value": old_value[1],
                            "new_value": new_value[1],
                            "created_at": source.created_at,
                            "actor_name": source.actor_name,
                            "device_name": source.device_name,
                            "log_source": source.log_source,
                            "message": source.message,
                            "actor_identity_verified": False,
                        },
                        action_hints=("open_contract",),
                        supports_snooze=False,
                    )
                )
        return tuple(items)


__all__ = ["ActivityAgendaProvider"]
