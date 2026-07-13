from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from inspect import signature

from src.domain.agenda.activity import activity_source_cutoff
from src.domain.agenda.constants import AgendaContractScopeCode, AgendaPresentationProfileCode
from src.domain.agenda.lifecycle import AgendaLifecycleEngine
from src.domain.agenda.models import AgendaContext, AgendaItem, AgendaResult
from src.domain.agenda.priority import severity_rank
from src.domain.agenda.providers import (
    ActivityAgendaProvider,
    AgendaProvider,
    DeadlineAgendaProvider,
    DocumentLockAgendaProvider,
    ReturnedShareAgendaProvider,
    UnknownDateAgendaProvider,
)
from src.services.agenda_source_repository import AgendaSourceRepository
from src.services.agenda_state_repository import AgendaStateRepository
from src.services.sts_database import STSDatabase


class AgendaBuildError(RuntimeError):
    def __init__(self, message: str, *, provider_code: str = ""):
        super().__init__(message)
        self.provider_code = provider_code


def _event_sort_value(item: AgendaItem) -> float:
    value = item.event_at
    if isinstance(value, datetime):
        parsed = value.replace(tzinfo=None)
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value)).replace(tzinfo=None)
        except ValueError:
            return 0.0
    else:
        return 0.0
    return parsed.timestamp()


class StaffAgendaService:
    def __init__(
        self,
        db: STSDatabase,
        state_repository: AgendaStateRepository | None = None,
        source_repository: AgendaSourceRepository | None = None,
        providers: Sequence[AgendaProvider] | None = None,
        lifecycle_engine: AgendaLifecycleEngine | None = None,
    ):
        self.db = db
        self.state_repository = state_repository or AgendaStateRepository(db)
        self.source_repository = source_repository or AgendaSourceRepository(db)
        self.providers = tuple(providers) if providers is not None else (
            DeadlineAgendaProvider(),
            ReturnedShareAgendaProvider(),
            DocumentLockAgendaProvider(),
            UnknownDateAgendaProvider(),
            ActivityAgendaProvider(),
        )
        self.lifecycle_engine = lifecycle_engine or AgendaLifecycleEngine()

    @staticmethod
    def _empty(context: AgendaContext) -> AgendaResult:
        return AgendaResult(
            profile=context.presentation_profile,
            items=(),
            new_count=0,
            active_count=0,
            counts_by_kind={},
            new_keys=frozenset(),
            states_by_key={},
            snoozed_count=0,
            filtered_count=0,
        )

    def build(
        self,
        context: AgendaContext,
        *,
        touch_presented: bool = True,
    ) -> AgendaResult:
        if "view_contracts" not in context.permissions:
            return self._empty(context)
        if (
            context.presentation_profile.code == AgendaPresentationProfileCode.SYSTEM
            and context.staff_id is None
        ):
            # Exact system-admin sessions have a system_admins.id, not a staff.id.
            # Until a principal-aware agenda-state model exists, do not query
            # sources/providers or touch staff_agenda_state.
            return self._empty(context)
        if context.staff_id is None or int(context.staff_id) <= 0:
            raise ValueError("context.staff_id must be a positive integer.")
        staff_id = int(context.staff_id)

        if context.personal_contract_ids:
            contract_ids = context.personal_contract_ids
        elif context.contract_scope == AgendaContractScopeCode.RESPONSIBLE:
            contract_ids = self.source_repository.list_personal_contract_ids(staff_id)
        elif context.contract_scope == AgendaContractScopeCode.ALL_VISIBLE:
            contract_ids = self.source_repository.list_all_contract_ids()
        else:
            raise ValueError(f"Unsupported agenda contract scope: {context.contract_scope}")

        if not contract_ids:
            return self._empty(context)

        load_sources = self.source_repository.load_personal_sources
        if "activity_since" in signature(load_sources).parameters:
            sources = load_sources(
                contract_ids,
                activity_since=activity_source_cutoff(context.now),
            )
        else:
            # Compatibility for existing source-repository test doubles and
            # third-party adapters that predate the activity source window.
            sources = load_sources(contract_ids)
        raw_items: list[AgendaItem] = []
        seen_keys: set[str] = set()
        for provider in self.providers:
            provider_code = str(getattr(provider, "code", "") or "").strip()
            try:
                if not provider.is_enabled(context):
                    continue
                built = tuple(provider.build(context, sources))
            except Exception as exc:
                raise AgendaBuildError(
                    f"Agenda provider failed: {provider_code or provider.__class__.__name__}",
                    provider_code=provider_code,
                ) from exc
            for item in built:
                if item.key in seen_keys:
                    raise AgendaBuildError(
                        f"Duplicate agenda key: {item.key}",
                        provider_code=provider_code,
                    )
                seen_keys.add(item.key)
                raw_items.append(item)

        if not raw_items:
            return self._empty(context)

        states = self.state_repository.get_states(staff_id, [item.key for item in raw_items])
        visible: list[AgendaItem] = []
        new_keys: set[str] = set()
        visible_states = {}
        snoozed_count = 0
        filtered_count = 0

        for item in raw_items:
            state = states.get(item.key)
            decision = self.lifecycle_engine.evaluate(item, state, context.now)
            if not decision.visible:
                filtered_count += 1
                if decision.reason == "snoozed":
                    snoozed_count += 1
                continue
            visible.append(decision.item)
            if decision.is_new:
                new_keys.add(decision.item.key)
            if state is not None:
                visible_states[decision.item.key] = state

        visible.sort(
            key=lambda item: (
                0 if item.key in new_keys else 1,
                -int(item.priority),
                -severity_rank(item.severity),
                item.remaining_days is None,
                item.remaining_days if item.remaining_days is not None else 0,
                -_event_sort_value(item),
                item.key,
            )
        )

        if touch_presented and visible:
            self.state_repository.touch_presented(
                staff_id,
                [item.key for item in visible],
                presented_at=context.now,
            )

        counts = Counter(item.kind for item in visible)
        return AgendaResult(
            profile=context.presentation_profile,
            items=tuple(visible),
            new_count=len(new_keys),
            active_count=len(visible),
            counts_by_kind=dict(counts),
            new_keys=frozenset(new_keys),
            states_by_key=visible_states,
            snoozed_count=snoozed_count,
            filtered_count=filtered_count,
        )
