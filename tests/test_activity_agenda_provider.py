from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from src.domain.agenda.activity import (
    ACTIVITY_PROVIDER_CODE,
    ACTIVITY_SOURCE_LOOKBACK_DAYS,
    CONTRACT_ACTIVITY_FIELD_PRESENTATION,
    CONTRACT_ACTIVITY_FIELDS_BY_ACTION,
    activity_source_cutoff,
)
from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.models import AgendaContext, AgendaPresentationProfile
from src.domain.agenda.providers.activity import ActivityAgendaProvider
from src.domain.agenda.source_models import (
    ActivityAgendaSource,
    AgendaCalendarSource,
    AgendaSourceBundle,
    DocumentLockAgendaSource,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_RETURNED


NOW = datetime(2026, 7, 13, 12, 0, 0)


def _context(*, permissions=frozenset({"view_contracts"}), role="personnel"):
    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset(permissions),
    )
    return AgendaContext(
        now=NOW,
        today=date(2026, 7, 13),
        presentation_profile=profile,
        current_staff={
            "id": 7,
            "full_name": "Same Actor",
            "device_name": "same-device",
            "role": role,
            "permissions": frozenset(permissions),
        },
        staff_id=7,
        permissions=frozenset(permissions),
    )


def _source(**overrides):
    value = {
        "log_id": 23,
        "contract_id": 9,
        "action": "contract_updated",
        "created_at": "2026-07-13 10:30:00",
        "contract_no": " C-9 ",
        "contract_type": " Ana ",
        "platform": " P1 ",
        "entity_type": "contract",
        "entity_id": "9",
        "actor_name": " Same Actor ",
        "device_name": " same-device ",
        "log_source": " Contract UI ",
        "message": " Updated ",
        "before_values": {
            "completion_date": " 2026-07-20 ",
            "acceptance_date": "",
            "status": "Açık",
            "note": "old",
        },
        "after_values": {
            "completion_date": "2026-07-21",
            "acceptance_date": "2026-08-01",
            "status": "Kapalı",
            "note": "new",
        },
    }
    value.update(overrides)
    return ActivityAgendaSource(**value)


def test_activity_policy_contract_is_exact_and_immutable():
    assert ACTIVITY_PROVIDER_CODE == "activity"
    assert ACTIVITY_SOURCE_LOOKBACK_DAYS == 8
    assert dict(CONTRACT_ACTIVITY_FIELDS_BY_ACTION) == {
        "contract_updated": ("completion_date", "acceptance_date"),
        "contract_status_changed": ("status",),
    }
    assert "status" not in CONTRACT_ACTIVITY_FIELDS_BY_ACTION["contract_updated"]
    assert "contract_created" not in CONTRACT_ACTIVITY_FIELDS_BY_ACTION
    assert CONTRACT_ACTIVITY_FIELD_PRESENTATION["status"]["reason_text"] == "STATUS_CHANGED"
    with pytest.raises(TypeError):
        CONTRACT_ACTIVITY_FIELDS_BY_ACTION["contract_created"] = ()
    with pytest.raises(TypeError):
        CONTRACT_ACTIVITY_FIELD_PRESENTATION["status"]["reason_text"] = "changed"


def test_activity_source_cutoff_is_exact_eight_days_and_naive():
    aware = datetime(2026, 7, 13, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    assert activity_source_cutoff(aware) == datetime(2026, 7, 5, 12, 0)
    assert activity_source_cutoff(aware).tzinfo is None
    with pytest.raises(TypeError):
        activity_source_cutoff("2026-07-13")


def test_activity_source_model_normalizes_and_snapshots_mappings():
    before = {"completion_date": "2026-07-20"}
    after = {"completion_date": "2026-07-21"}
    source = _source(before_values=before, after_values=after)
    before["completion_date"] = "mutated"
    after["completion_date"] = "mutated"

    assert source.log_id == 23
    assert source.contract_id == 9
    assert source.contract_no == "C-9"
    assert source.contract_type == "Ana"
    assert source.platform == "P1"
    assert source.actor_name == "Same Actor"
    assert source.device_name == "same-device"
    assert source.log_source == "Contract UI"
    assert source.message == "Updated"
    assert source.before_values == {"completion_date": "2026-07-20"}
    assert source.after_values == {"completion_date": "2026-07-21"}
    assert isinstance(source.before_values, MappingProxyType)
    with pytest.raises(TypeError):
        source.before_values["completion_date"] = "x"


@pytest.mark.parametrize("field_name", ["log_id", "contract_id"])
@pytest.mark.parametrize("value", [0, -1, True, "x"])
def test_activity_source_model_rejects_invalid_ids(field_name, value):
    with pytest.raises(ValueError):
        _source(**{field_name: value})


def test_activity_source_model_enforces_action_timestamp_and_contract_identity():
    with pytest.raises(ValueError, match="Unsupported"):
        _source(action="contract_created")
    with pytest.raises(ValueError, match="created_at"):
        _source(created_at=" ")
    with pytest.raises(ValueError, match="entity_type"):
        _source(entity_type="system")
    with pytest.raises(ValueError, match="entity_id"):
        _source(entity_id="09")
    assert _source(entity_id="").entity_id == "9"


def test_activity_source_model_requires_mapping_values():
    with pytest.raises(TypeError, match="before_values"):
        _source(before_values=[])
    with pytest.raises(TypeError, match="after_values"):
        _source(after_values="{}")


def test_bundle_accepts_activity_tuple_and_preserves_existing_families():
    calendar = AgendaCalendarSource(entity_type="contract", entity_id=9, contract_id=9)
    returned = ReturnedShareAgendaSource(
        registry_id=1,
        share_package_id="pkg",
        contract_id=9,
        status=SHARE_STATUS_RETURNED,
    )
    lock = DocumentLockAgendaSource(
        contract_id=9,
        locked_at="2026-07-13 09:00:00",
    )
    activity = _source()
    bundle = AgendaSourceBundle(
        calendar=[calendar],
        returned_shares=[returned],
        document_locks=[lock],
        activities=[activity],
    )
    assert bundle.calendar == (calendar,)
    assert bundle.returned_shares == (returned,)
    assert bundle.document_locks == (lock,)
    assert bundle.activities == (activity,)
    with pytest.raises(TypeError, match="activities"):
        AgendaSourceBundle(activities=[calendar])


def test_provider_capability_is_view_only_and_not_role_or_edit_based():
    provider = ActivityAgendaProvider()
    assert provider.code == ACTIVITY_PROVIDER_CODE
    assert provider.is_enabled(_context(permissions={"view_contracts"})) is True
    assert provider.is_enabled(_context(permissions={"view_contracts", "edit_contracts"})) is True
    assert provider.is_enabled(_context(permissions={"edit_contracts"}, role="manager")) is False
    assert provider.is_enabled(_context(permissions=set(), role="manager")) is False


def test_contract_updated_expands_only_changed_date_fields():
    source = _source()
    items = ActivityAgendaProvider().build(
        _context(),
        AgendaSourceBundle(activities=(source,)),
    )
    assert [item.detail_payload["field_name"] for item in items] == [
        "completion_date",
        "acceptance_date",
    ]
    assert all(item.detail_payload["field_name"] not in {"status", "note"} for item in items)
    assert [item.key for item in items] == [
        "activity:activity_log:23:completion_date",
        "activity:activity_log:23:acceptance_date",
    ]


def test_contract_status_changed_emits_only_status():
    source = _source(
        action="contract_status_changed",
        before_values={"status": "Açık", "completion_date": "2026-07-20"},
        after_values={"status": "Kapalı", "completion_date": "2026-07-21"},
    )
    items = ActivityAgendaProvider().build(
        _context(),
        AgendaSourceBundle(activities=(source,)),
    )
    assert len(items) == 1
    assert items[0].detail_payload["field_name"] == "status"
    assert items[0].reason_text == "STATUS_CHANGED"


def test_equal_and_nested_values_fail_closed():
    equal = _source(
        before_values={"completion_date": " 2026-07-20 "},
        after_values={"completion_date": "2026-07-20"},
    )
    nested_before = _source(
        before_values={"completion_date": {"year": 2026}},
        after_values={"completion_date": "2026-07-20"},
    )
    nested_after = _source(
        before_values={"completion_date": "2026-07-20"},
        after_values={"completion_date": ["2026-07-21"]},
    )
    provider = ActivityAgendaProvider()
    assert provider.build(_context(), AgendaSourceBundle(activities=(equal,))) == ()
    assert provider.build(_context(), AgendaSourceBundle(activities=(nested_before,))) == ()
    assert provider.build(_context(), AgendaSourceBundle(activities=(nested_after,))) == ()


def test_none_and_empty_string_are_same_empty_value():
    source = _source(
        before_values={"completion_date": None},
        after_values={"completion_date": "  "},
    )
    assert ActivityAgendaProvider().build(
        _context(), AgendaSourceBundle(activities=(source,))
    ) == ()


def test_activity_item_contract_and_actor_identity_limit():
    source = _source(
        before_values={"completion_date": ""},
        after_values={"completion_date": "2026-07-21"},
    )
    context = _context()
    item = ActivityAgendaProvider().build(
        context,
        AgendaSourceBundle(activities=(source,)),
    )[0]

    assert item.provider_code == "activity"
    assert item.kind == "activity"
    assert item.lifecycle_type == AgendaLifecycleType.EVENT
    assert item.priority == 450
    assert item.severity == AgendaSeverity.INFO
    assert item.version == "ACTIVITY:23:completion_date:2026-07-13 10:30:00"
    assert item.presentation_scope == AgendaPresentationProfileCode.PERSONAL
    assert item.contract_id == 9
    assert item.contract_no == "C-9"
    assert item.contract_type == "Ana"
    assert item.platform == "P1"
    assert item.title == "C-9 tamamlanma tarihi değişti"
    assert item.description == "Boş → 2026-07-21"
    assert item.actor_staff_id is None
    assert item.actor_name == "Same Actor"
    assert item.event_at == source.created_at
    assert item.effective_date == source.created_at
    assert item.reason_code == "CONTRACT_ACTIVITY"
    assert item.reason_text == "COMPLETION_DATE_CHANGED"
    assert item.supports_snooze is False
    assert item.action_hints == ("open_contract",)
    assert "dismiss" not in item.action_hints
    assert "snooze" not in item.action_hints
    assert item.detail_payload == {
        "source_type": "activity_log",
        "log_id": 23,
        "action": "contract_updated",
        "entity_type": "contract",
        "entity_id": "9",
        "contract_id": 9,
        "field_name": "completion_date",
        "old_value": None,
        "new_value": "2026-07-21",
        "created_at": "2026-07-13 10:30:00",
        "actor_name": "Same Actor",
        "device_name": "same-device",
        "log_source": "Contract UI",
        "message": "Updated",
        "actor_identity_verified": False,
    }


def test_actor_and_device_collision_do_not_filter_event():
    source = _source(actor_name="Same Actor", device_name="same-device")
    items = ActivityAgendaProvider().build(
        _context(),
        AgendaSourceBundle(activities=(source,)),
    )
    assert len(items) == 2
    assert all(item.actor_staff_id is None for item in items)


def test_title_and_value_fallbacks_are_exact():
    source = _source(
        contract_no="",
        action="contract_status_changed",
        before_values={"status": None},
        after_values={"status": "Kapalı"},
    )
    item = ActivityAgendaProvider().build(
        _context(),
        AgendaSourceBundle(activities=(source,)),
    )[0]
    assert item.title == "Sözleşme durumu değişti"
    assert item.description == "Boş → Kapalı"


def test_provider_does_not_mutate_source_or_context():
    before = {"completion_date": "2026-07-20"}
    after = {"completion_date": "2026-07-21"}
    source = _source(before_values=before, after_values=after)
    context = _context()
    source_snapshot = (
        dict(source.before_values),
        dict(source.after_values),
        source.actor_name,
        source.device_name,
    )
    context_snapshot = (context.permissions, dict(context.current_staff or {}))
    ActivityAgendaProvider().build(context, AgendaSourceBundle(activities=(source,)))
    assert source_snapshot == (
        dict(source.before_values),
        dict(source.after_values),
        source.actor_name,
        source.device_name,
    )
    assert context_snapshot == (context.permissions, dict(context.current_staff or {}))
