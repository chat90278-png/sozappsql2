from __future__ import annotations

from datetime import date, datetime

from src.domain.agenda.constants import AgendaPresentationProfileCode, AgendaSeverity
from src.domain.agenda.models import AgendaContext, AgendaPresentationProfile
from src.domain.agenda.providers.deadline import DeadlineAgendaProvider
from src.domain.agenda.source_models import (
    AgendaCalendarSource,
    AgendaSourceBundle,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_RETURNED


def _context(today=date(2026, 7, 11)):
    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset({"view_contracts"}),
    )
    return AgendaContext(
        now=datetime.combine(today, datetime.min.time()),
        today=today,
        presentation_profile=profile,
        staff_id=1,
        permissions=frozenset({"view_contracts"}),
    )


def _source(entity_type="contract", raw="2026-07-20", status="Açık"):
    kwargs = dict(
        entity_type=entity_type,
        entity_id={"contract": 1, "system": 2, "delivery": 3}[entity_type],
        contract_id=1,
        platform="P1",
        contract_no="C-1",
        contract_type="Ana",
        status=status,
        completion_date=raw if entity_type != "delivery" else "",
        acceptance_date="",
        planned_acceptance_date=raw if entity_type == "delivery" else "",
    )
    if entity_type in {"system", "delivery"}:
        kwargs["system_id"] = 2
        kwargs["system_name"] = "System A"
    if entity_type == "delivery":
        kwargs["delivery_id"] = 3
        kwargs["delivery_name"] = "Delivery A"
    return AgendaCalendarSource(**kwargs)


def _bundle(*sources, returned_shares=()):
    return AgendaSourceBundle(calendar=tuple(sources), returned_shares=tuple(returned_shares))


def _returned():
    return ReturnedShareAgendaSource(
        registry_id=1,
        share_package_id="pkg-1",
        contract_id=1,
        status=SHARE_STATUS_RETURNED,
    )


def test_contract_deadline_item():
    item = DeadlineAgendaProvider().build(_context(), _bundle(_source()))[0]
    assert item.contract_id == 1 and item.kind == "deadline"


def test_system_deadline_item():
    item = DeadlineAgendaProvider().build(_context(), _bundle(_source("system")))[0]
    assert item.system_id == 2 and "System A" in item.title


def test_delivery_uses_planned_acceptance_when_actual_missing():
    item = DeadlineAgendaProvider().build(_context(), _bundle(_source("delivery")))[0]
    assert item.detail_payload["date_field"] == "planned_acceptance_date"


def test_completed_source_is_skipped():
    assert DeadlineAgendaProvider().build(_context(), _bundle(_source(status="Tamamlandı"))) == ()


def test_non_exact_date_is_skipped():
    assert DeadlineAgendaProvider().build(_context(), _bundle(_source(raw="TBD"))) == ()


def test_more_than_sixty_days_is_skipped():
    assert DeadlineAgendaProvider().build(_context(), _bundle(_source(raw="2026-09-10"))) == ()


def test_overdue_priority_and_description():
    item = DeadlineAgendaProvider().build(_context(), _bundle(_source(raw="2026-07-10")))[0]
    assert item.priority == 1000
    assert item.severity == AgendaSeverity.CRITICAL
    assert item.description == "1 gün gecikti"


def test_deadline_key_is_stable_across_stage_change():
    provider = DeadlineAgendaProvider()
    one = provider.build(_context(), _bundle(_source(raw="2026-07-12")))[0]
    fifteen = provider.build(_context(), _bundle(_source(raw="2026-07-26")))[0]
    assert one.key == fifteen.key


def test_deadline_version_changes_with_stage():
    provider = DeadlineAgendaProvider()
    one = provider.build(_context(), _bundle(_source(raw="2026-07-12")))[0]
    fifteen = provider.build(_context(), _bundle(_source(raw="2026-07-26")))[0]
    assert one.version != fifteen.version


def test_deadline_item_carries_personal_profile_and_contract_ids():
    item = DeadlineAgendaProvider().build(_context(), _bundle(_source("delivery")))[0]
    assert item.presentation_scope == AgendaPresentationProfileCode.PERSONAL
    assert item.contract_id == 1 and item.system_id == 2 and item.delivery_id == 3


def test_deadline_boundaries():
    provider = DeadlineAgendaProvider()
    expected = {
        -1: "OVERDUE",
        0: "CRITICAL_1",
        1: "CRITICAL_1",
        15: "CRITICAL_15",
        16: "UPCOMING_30",
        60: "UPCOMING_60",
    }
    for days, version in expected.items():
        raw = date.fromordinal(_context().today.toordinal() + days).isoformat()
        assert provider.build(_context(), _bundle(_source(raw=raw)))[0].version == version
    raw_61 = date.fromordinal(_context().today.toordinal() + 61).isoformat()
    assert provider.build(_context(), _bundle(_source(raw=raw_61))) == ()


def test_deadline_provider_ignores_returned_share_sources():
    bundle = _bundle(returned_shares=(_returned(),))
    assert DeadlineAgendaProvider().build(_context(), bundle) == ()
