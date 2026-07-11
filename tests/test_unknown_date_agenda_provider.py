from __future__ import annotations

from datetime import date, datetime

from src.domain.agenda.constants import AgendaPresentationProfileCode, AgendaSeverity
from src.domain.agenda.models import AgendaContext, AgendaPresentationProfile
from src.domain.agenda.providers.unknown_date import UnknownDateAgendaProvider
from src.domain.agenda.source_models import AgendaCalendarSource


def _context():
    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset({"view_contracts"}),
    )
    return AgendaContext(
        now=datetime(2026, 7, 11, 12),
        today=date(2026, 7, 11),
        presentation_profile=profile,
        staff_id=1,
        permissions=frozenset({"view_contracts"}),
    )


def _source(entity_type="contract", raw="TBD", status="Açık"):
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


def test_fully_unknown_contract():
    item = UnknownDateAgendaProvider().build(_context(), [_source()])[0]
    assert item.detail_payload["date_kind"] == "fully_unknown"


def test_month_unknown_day_system():
    item = UnknownDateAgendaProvider().build(_context(), [_source("system", "2026-07-TBD")])[0]
    assert item.description == "Yıl ve ay belli, gün TBD."


def test_year_only_delivery():
    item = UnknownDateAgendaProvider().build(_context(), [_source("delivery", "2026-TBD-TBD")])[0]
    assert "kabul tarihi" in item.title


def test_exact_date_is_skipped():
    assert UnknownDateAgendaProvider().build(_context(), [_source(raw="2026-07-20")]) == ()


def test_na_or_malformed_date_is_skipped():
    provider = UnknownDateAgendaProvider()
    assert provider.build(_context(), [_source(raw="-")]) == ()
    assert provider.build(_context(), [_source(raw="not-a-date")]) == ()


def test_completed_unknown_source_is_skipped():
    assert UnknownDateAgendaProvider().build(_context(), [_source(raw="TBD", status="Tamamlandı")]) == ()


def test_unknown_key_stable_when_raw_date_changes():
    provider = UnknownDateAgendaProvider()
    a = provider.build(_context(), [_source(raw="TBD")])[0]
    b = provider.build(_context(), [_source(raw="2026-TBD-TBD")])[0]
    assert a.key == b.key


def test_unknown_version_changes_when_date_shape_changes():
    provider = UnknownDateAgendaProvider()
    a = provider.build(_context(), [_source(raw="TBD")])[0]
    b = provider.build(_context(), [_source(raw="2026-TBD-TBD")])[0]
    assert a.version != b.version


def test_unknown_payload_requests_seven_day_resurface():
    item = UnknownDateAgendaProvider().build(_context(), [_source()])[0]
    assert item.detail_payload["resurface_interval_days"] == 7


def test_unknown_item_supports_snooze():
    item = UnknownDateAgendaProvider().build(_context(), [_source()])[0]
    assert item.supports_snooze
    assert item.severity == AgendaSeverity.ATTENTION
    assert item.presentation_scope == AgendaPresentationProfileCode.PERSONAL
