from __future__ import annotations

from src.domain.agenda.constants import AgendaLifecycleType
from src.domain.agenda.deadline_stage import (
    DeadlineStage,
    deadline_stage_for_remaining_days,
    deadline_stage_severity,
    deadline_stage_version,
)
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaCalendarSource, AgendaSourceBundle
from src.domain.calendar_timing import (
    calendar_date_kind,
    calendar_effective_date_raw,
    classify_calendar_event,
    parse_calendar_date,
)


_STAGE_PRIORITY = {
    DeadlineStage.OVERDUE: 1000,
    DeadlineStage.CRITICAL_1: 970,
    DeadlineStage.CRITICAL_3: 950,
    DeadlineStage.CRITICAL_7: 930,
    DeadlineStage.CRITICAL_15: 900,
    DeadlineStage.UPCOMING_30: 700,
    DeadlineStage.UPCOMING_60: 600,
}


def _date_field(source: AgendaCalendarSource) -> str:
    if source.entity_type == "delivery":
        actual = source.acceptance_date.strip()
        return "acceptance_date" if actual and actual != "-" else "planned_acceptance_date"
    return "completion_date"


def _subject(source: AgendaCalendarSource) -> str:
    contract = source.contract_no or f"#{source.contract_id}"
    if source.entity_type == "contract":
        return contract
    if source.entity_type == "system":
        return f"{contract} · {source.system_name}".strip()
    return f"{contract} · {source.system_name} / {source.delivery_name}".strip()


def _title(source: AgendaCalendarSource, overdue: bool) -> str:
    suffix = "gecikti" if overdue else "yaklaşıyor"
    subject = _subject(source)
    if source.entity_type == "delivery":
        return f"{subject} kabulü {suffix}"
    return f"{subject} termini {suffix}"


def _description(remaining_days: int) -> str:
    if remaining_days < 0:
        return f"{abs(remaining_days)} gün gecikti"
    if remaining_days == 0:
        return "Bugün"
    return f"{remaining_days} gün kaldı"


class DeadlineAgendaProvider:
    code = "deadline"

    def is_enabled(self, context: AgendaContext) -> bool:
        return "view_contracts" in context.permissions

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        items: list[AgendaItem] = []
        for source in sources.calendar:
            calendar_item = source.as_calendar_item()
            raw = calendar_effective_date_raw(calendar_item)
            if calendar_date_kind(raw) != "exact":
                continue
            effective_date = parse_calendar_date(raw)
            if effective_date is None:
                continue
            if classify_calendar_event(calendar_item, effective_date, context.today, "exact") == "tamamlandi":
                continue
            remaining_days = (effective_date - context.today).days
            stage = deadline_stage_for_remaining_days(remaining_days)
            if stage == DeadlineStage.NONE:
                continue
            items.append(
                AgendaItem(
                    key=build_agenda_key(
                        provider_code=self.code,
                        entity_type=source.entity_type,
                        entity_id=source.entity_id,
                    ),
                    provider_code=self.code,
                    kind="deadline",
                    lifecycle_type=AgendaLifecycleType.CONDITION,
                    title=_title(source, remaining_days < 0),
                    description=_description(remaining_days),
                    priority=_STAGE_PRIORITY[stage],
                    severity=deadline_stage_severity(stage),
                    version=deadline_stage_version(stage),
                    presentation_scope=context.presentation_profile.code,
                    contract_id=source.contract_id,
                    platform=source.platform,
                    contract_no=source.contract_no,
                    contract_type=source.contract_type,
                    system_id=source.system_id,
                    delivery_id=source.delivery_id,
                    effective_date=effective_date,
                    remaining_days=remaining_days,
                    reason_code=stage.value,
                    reason_text=stage.value,
                    detail_payload={
                        "source_type": source.entity_type,
                        "date_field": _date_field(source),
                        "date_raw": raw,
                        "deadline_stage": stage.value,
                        "system_name": source.system_name,
                        "delivery_name": source.delivery_name,
                    },
                    action_hints=("open_contract",),
                    supports_snooze=True,
                )
            )
        return tuple(items)
