from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime, timedelta
from typing import Any

from src.domain.agenda.constants import AgendaLifecycleType
from src.domain.agenda.models import AgendaContext, AgendaItem, AgendaItemState
from src.domain.agenda.presentation import AgendaPresentationSnapshot, project_agenda_result
from src.services.agenda_context_factory import PersonalAgendaContextFactory
from src.services.agenda_state_repository import AgendaStateRepository
from src.services.staff_agenda_service import StaffAgendaService
from src.services.sts_database import STSDatabase


class AgendaInteractionError(ValueError):
    pass


def _normalize_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AgendaInteractionError(f"{field_name} must be a datetime value.")
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.replace(tzinfo=None)
    return value


def snooze_until_for_preset(preset: str, *, now: datetime) -> datetime:
    normalized_now = _normalize_datetime(now, "now")
    code = str(preset or "").strip().casefold()
    if code == "tomorrow":
        return (normalized_now + timedelta(days=1)).replace(
            hour=9,
            minute=0,
            second=0,
            microsecond=0,
        )
    if code == "three_days":
        return (normalized_now + timedelta(days=3)).replace(second=0, microsecond=0)
    if code == "one_week":
        return (normalized_now + timedelta(days=7)).replace(second=0, microsecond=0)
    raise AgendaInteractionError(f"Unknown snooze preset: {preset}")


class PersonalAgendaFacade:
    def __init__(
        self,
        db: STSDatabase,
        context_factory: PersonalAgendaContextFactory | None = None,
        agenda_service: StaffAgendaService | None = None,
        state_repository: AgendaStateRepository | None = None,
    ):
        self.db = db
        service_state_repository = getattr(agenda_service, "state_repository", None)
        if state_repository is not None and service_state_repository is not None:
            if state_repository is not service_state_repository:
                raise ValueError("agenda_service and facade must share the same state repository.")
        self.state_repository = (
            state_repository
            or service_state_repository
            or AgendaStateRepository(db)
        )
        self.context_factory = context_factory or PersonalAgendaContextFactory()
        self.agenda_service = agenda_service or StaffAgendaService(
            db,
            state_repository=self.state_repository,
        )

    def _interaction_context(
        self,
        current_staff: Mapping[str, Any] | None,
    ) -> AgendaContext:
        context = self.context_factory.build(current_staff)
        if "view_contracts" not in context.permissions:
            raise AgendaInteractionError("view_contracts permission is required.")
        if context.staff_id is None or int(context.staff_id) <= 0:
            raise AgendaInteractionError("A valid current staff identity is required.")
        return context

    @staticmethod
    def _item_identity(item: AgendaItem) -> tuple[str, str]:
        key = str(item.key or "").strip()
        version = str(item.version or "").strip()
        if not key:
            raise AgendaInteractionError("Agenda item key cannot be empty.")
        if not version:
            raise AgendaInteractionError("Agenda item version cannot be empty.")
        return key, version

    def load(
        self,
        current_staff: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
        personal_contract_ids: Collection[int] = (),
        compact_limit: int = 2,
        detail_limit: int = 20,
        touch_presented: bool = True,
    ) -> AgendaPresentationSnapshot:
        context = self.context_factory.build(
            current_staff,
            now=now,
            personal_contract_ids=personal_contract_ids,
        )
        result = self.agenda_service.build(
            context,
            touch_presented=touch_presented,
        )
        return project_agenda_result(
            result,
            compact_limit=compact_limit,
            detail_limit=detail_limit,
        )

    def mark_seen(
        self,
        current_staff: Mapping[str, Any] | None,
        item: AgendaItem,
        *,
        seen_at: datetime | str | None = None,
    ) -> AgendaItemState:
        context = self._interaction_context(current_staff)
        key, version = self._item_identity(item)
        state = self.state_repository.mark_seen(
            int(context.staff_id),
            key,
            version,
            seen_at=seen_at,
        )
        if state is None:
            state = self.state_repository.get_states(int(context.staff_id), [key]).get(key)
        if state is None:
            raise AgendaInteractionError("Seen state could not be persisted.")
        return state

    def snooze(
        self,
        current_staff: Mapping[str, Any] | None,
        item: AgendaItem,
        *,
        until: datetime,
        now: datetime | None = None,
    ) -> AgendaItemState:
        context = self._interaction_context(current_staff)
        key, version = self._item_identity(item)
        if item.lifecycle_type != AgendaLifecycleType.CONDITION:
            raise AgendaInteractionError("Only condition items can be snoozed.")
        if not item.supports_snooze:
            raise AgendaInteractionError("This agenda item does not support snooze.")
        normalized_until = _normalize_datetime(until, "until")
        normalized_now = _normalize_datetime(now or datetime.now(), "now")
        if normalized_until <= normalized_now:
            raise AgendaInteractionError("Snooze until must be in the future.")

        state = self.state_repository.snooze(
            int(context.staff_id),
            key,
            version,
            item.severity.value,
            normalized_until,
        )
        if state is None:
            state = self.state_repository.get_states(int(context.staff_id), [key]).get(key)
        if state is None:
            raise AgendaInteractionError("Snooze state could not be persisted.")
        return state

    def clear_snooze(
        self,
        current_staff: Mapping[str, Any] | None,
        item: AgendaItem,
    ) -> AgendaItemState | None:
        context = self._interaction_context(current_staff)
        key, _version = self._item_identity(item)
        return self.state_repository.clear_snooze(int(context.staff_id), key)

    @staticmethod
    def snooze_until_for_preset(preset: str, *, now: datetime) -> datetime:
        return snooze_until_for_preset(preset, now=now)
