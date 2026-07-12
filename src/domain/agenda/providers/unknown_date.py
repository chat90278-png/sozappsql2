from __future__ import annotations

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaCalendarSource, AgendaSourceBundle
from src.domain.calendar_timing import (
    calendar_date_kind,
    calendar_effective_date_raw,
    classify_calendar_event,
)


_UNKNOWN_DESCRIPTIONS = {
    "fully_unknown": "Tarih TBD olarak tanımlı.",
    "month_unknown_day": "Yıl ve ay belli, gün TBD.",
    "year_only": "Yalnız yıl belli; ay ve gün TBD.",
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


class UnknownDateAgendaProvider:
    code = "unknown_date"

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        items: list[AgendaItem] = []
        for source in sources.calendar:
            calendar_item = source.as_calendar_item()
            raw = calendar_effective_date_raw(calendar_item)
            date_kind = calendar_date_kind(raw)
            if date_kind not in _UNKNOWN_DESCRIPTIONS:
                continue
            if classify_calendar_event(calendar_item, None, context.today, date_kind) == "tamamlandi":
                continue
            subject = _subject(source)
            title = (
                f"{subject} kabul tarihi kesin değil"
                if source.entity_type == "delivery"
                else f"{subject} için termin kesin değil"
            )
            items.append(
                AgendaItem(
                    key=build_agenda_key(
                        provider_code=self.code,
                        entity_type=source.entity_type,
                        entity_id=source.entity_id,
                    ),
                    provider_code=self.code,
                    kind="unknown_date",
                    lifecycle_type=AgendaLifecycleType.CONDITION,
                    title=title,
                    description=_UNKNOWN_DESCRIPTIONS[date_kind],
                    priority=500,
                    severity=AgendaSeverity.ATTENTION,
                    version=f"UNKNOWN:{date_kind}:{raw}",
                    presentation_scope=context.presentation_profile.code,
                    contract_id=source.contract_id,
                    platform=source.platform,
                    contract_no=source.contract_no,
                    contract_type=source.contract_type,
                    system_id=source.system_id,
                    delivery_id=source.delivery_id,
                    effective_date=raw,
                    remaining_days=None,
                    reason_code="UNKNOWN_DATE",
                    reason_text=date_kind,
                    detail_payload={
                        "source_type": source.entity_type,
                        "date_field": _date_field(source),
                        "date_raw": raw,
                        "date_kind": date_kind,
                        "system_name": source.system_name,
                        "delivery_name": source.delivery_name,
                        "resurface_interval_days": 7,
                    },
                    action_hints=("open_contract",),
                    supports_snooze=True,
                )
            )
        return tuple(items)
