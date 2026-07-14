from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.lifecycle import AgendaLifecycleEngine
from src.domain.agenda.models import AgendaItem, AgendaItemState


NOW = datetime(2026, 7, 11, 12, 0, 0)


def _item(
    *,
    lifecycle=AgendaLifecycleType.CONDITION,
    version="V1",
    severity=AgendaSeverity.ATTENTION,
    supports_snooze=True,
    event_at=None,
    payload=None,
):
    return AgendaItem(
        key="test:contract:1",
        provider_code="test",
        kind="test",
        lifecycle_type=lifecycle,
        title="Test",
        description="Test",
        priority=100,
        severity=severity,
        version=version,
        event_at=event_at,
        detail_payload=payload or {},
        supports_snooze=supports_snooze,
    )


def _state(**kwargs):
    return AgendaItemState(staff_id=1, agenda_key="test:contract:1", **kwargs)


def test_condition_is_visible_when_unseen():
    decision = AgendaLifecycleEngine().evaluate(_item(), None, NOW)
    assert decision.visible and decision.is_new and not decision.is_seen


def test_condition_seen_same_version_remains_visible_but_not_new():
    decision = AgendaLifecycleEngine().evaluate(_item(), _state(seen_version="V1"), NOW)
    assert decision.visible and decision.is_seen and not decision.is_new


def test_condition_version_change_resurfaces_as_new():
    decision = AgendaLifecycleEngine().evaluate(_item(version="V2"), _state(seen_version="V1"), NOW)
    assert decision.visible and decision.is_new


def test_condition_dismiss_state_is_ignored():
    decision = AgendaLifecycleEngine().evaluate(_item(), _state(dismissed_version="V1"), NOW)
    assert decision.visible


def test_active_snooze_hides_condition():
    state = _state(snoozed_until="2026-07-12 12:00:00", snoozed_version="V1", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(_item(), state, NOW)
    assert not decision.visible and decision.is_snoozed and decision.reason == "snoozed"


def test_snooze_expiry_restores_condition():
    state = _state(snoozed_until="2026-07-11 12:00:00", snoozed_version="V1", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(_item(), state, NOW)
    assert decision.visible and decision.reason == "snooze_expired"


def test_snooze_version_change_breaks_snooze():
    state = _state(snoozed_until="2026-07-12 12:00:00", snoozed_version="OLD", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(_item(), state, NOW)
    assert decision.visible and decision.reason == "snooze_version_changed"


def test_severity_increase_breaks_snooze():
    state = _state(snoozed_until="2026-07-12 12:00:00", snoozed_version="V1", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(_item(severity=AgendaSeverity.CRITICAL), state, NOW)
    assert decision.visible and decision.reason == "snooze_severity_increased"


def test_invalid_saved_snooze_severity_fails_open():
    state = _state(snoozed_until="2026-07-12 12:00:00", snoozed_version="V1", snoozed_severity="CORRUPT")
    decision = AgendaLifecycleEngine().evaluate(_item(), state, NOW)
    assert decision.visible and not decision.is_snoozed
    assert decision.reason == "snooze_severity_invalid"


def test_invalid_snooze_timestamp_fails_open():
    state = _state(snoozed_until="not-a-time", snoozed_version="V1", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(_item(), state, NOW)
    assert decision.visible and decision.reason == "snooze_timestamp_invalid"


def test_unknown_condition_resurfaces_after_seven_days():
    item = _item(payload={"resurface_interval_days": 7})
    state = _state(first_presented_at="2026-07-04 12:00:00", seen_version="V1|R7:0")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.item.version == "V1|R7:1"
    assert decision.is_new


def test_unknown_condition_does_not_resurface_before_seven_days():
    item = _item(payload={"resurface_interval_days": 7})
    state = _state(first_presented_at="2026-07-05 12:00:00", seen_version="V1|R7:0")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.item.version == "V1|R7:0"
    assert decision.is_seen


def test_event_unseen_is_visible_before_seven_days():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW - timedelta(days=6))
    decision = AgendaLifecycleEngine().evaluate(item, None, NOW)
    assert decision.visible and decision.is_new


def test_event_unseen_expires_at_seven_day_boundary():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW - timedelta(days=7))
    decision = AgendaLifecycleEngine().evaluate(item, None, NOW)
    assert not decision.visible and decision.reason == "event_unseen_ttl_expired"


def test_event_seen_is_visible_before_twenty_four_hours():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW - timedelta(days=2))
    state = _state(seen_version="V1", seen_at="2026-07-10 12:00:01")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible and decision.is_seen and not decision.is_new


def test_event_seen_expires_at_twenty_four_hour_boundary():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW - timedelta(days=2))
    state = _state(seen_version="V1", seen_at="2026-07-10 12:00:00")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert not decision.visible and decision.reason == "event_seen_ttl_expired"


def test_event_new_version_resurfaces():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, version="V2", event_at=NOW)
    state = _state(seen_version="V1", seen_at="2026-07-11 11:00:00")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible and decision.is_new


def test_event_dismissed_version_is_hidden():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW)
    decision = AgendaLifecycleEngine().evaluate(item, _state(dismissed_version="V1"), NOW)
    assert not decision.visible and decision.reason == "dismissed"


def test_event_missing_timestamp_is_hidden():
    decision = AgendaLifecycleEngine().evaluate(_item(lifecycle=AgendaLifecycleType.EVENT, event_at=None), None, NOW)
    assert not decision.visible and decision.reason == "event_timestamp_invalid"


def test_event_invalid_seen_timestamp_fails_open_as_new():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW)
    state = _state(seen_version="V1", seen_at="corrupt")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible and decision.is_new
    assert decision.reason == "event_seen_timestamp_invalid"


def test_event_snooze_state_is_ignored():
    item = _item(lifecycle=AgendaLifecycleType.EVENT, event_at=NOW)
    state = _state(snoozed_until="2026-07-12 12:00:00", snoozed_version="V1", snoozed_severity="ATTENTION")
    decision = AgendaLifecycleEngine().evaluate(item, state, NOW)
    assert decision.visible and not decision.is_snoozed
