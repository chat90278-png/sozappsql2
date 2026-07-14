from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.models import (
    AgendaContext,
    AgendaItem,
    AgendaPresentationProfile,
    AgendaResult,
)
from src.domain.agenda.source_models import (
    AgendaCalendarSource,
    AgendaSourceBundle,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_RETURNED


def _profile(permissions=()):
    return AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Kişisel",
        description="Kişisel gündem profili",
        permissions=permissions,
    )


def _item(**overrides):
    values = {
        "key": "deadline:contract:42",
        "provider_code": "deadline",
        "kind": "contract_deadline",
        "lifecycle_type": AgendaLifecycleType.CONDITION,
        "title": "Teslim tarihi yaklaşıyor",
        "description": "Sözleşme teslim tarihi için gündem maddesi",
        "priority": 30,
        "severity": AgendaSeverity.ATTENTION,
        "version": "UPCOMING_30",
    }
    values.update(overrides)
    return AgendaItem(**values)


def _returned(**overrides):
    values = {
        "registry_id": 1,
        "share_package_id": "pkg-1",
        "contract_id": 42,
        "status": SHARE_STATUS_RETURNED,
    }
    values.update(overrides)
    return ReturnedShareAgendaSource(**values)


def test_agenda_item_defensively_copies_detail_payload():
    source = {"contract_id": 42}
    item = _item(detail_payload=source)
    source["contract_id"] = 99
    assert item.detail_payload["contract_id"] == 42
    with pytest.raises(TypeError):
        item.detail_payload["contract_id"] = 7


def test_agenda_item_normalizes_action_hints_to_tuple():
    hints = ["open_contract", "snooze"]
    item = _item(action_hints=hints)
    hints.append("dismiss")
    assert item.action_hints == ("open_contract", "snooze")
    assert isinstance(item.action_hints, tuple)


def test_agenda_profile_permissions_are_frozenset_snapshot():
    permissions = {"view_contracts", "edit_contracts"}
    profile = _profile(permissions)
    permissions.add("manage_staff")
    assert profile.permissions == frozenset({"view_contracts", "edit_contracts"})
    assert isinstance(profile.permissions, frozenset)


def test_agenda_result_defensively_copies_counts_by_kind():
    counts = {"contract_deadline": 1}
    result = AgendaResult(
        profile=_profile(),
        items=[_item()],
        new_count=1,
        active_count=1,
        counts_by_kind=counts,
    )
    counts["contract_deadline"] = 5
    assert result.items == (_item(),)
    assert result.counts_by_kind["contract_deadline"] == 1
    with pytest.raises(TypeError):
        result.counts_by_kind["contract_deadline"] = 2


def test_agenda_context_snapshots_current_staff_and_contract_ids():
    staff = {"id": 7, "full_name": "Test Personel"}
    contract_ids = {10, 20}
    permissions = {"view_contracts"}
    context = AgendaContext(
        now=datetime(2026, 7, 10, 12, 0, 0),
        today=date(2026, 7, 10),
        presentation_profile=_profile(),
        current_staff=staff,
        staff_id=7,
        permissions=permissions,
        personal_contract_ids=contract_ids,
    )
    staff["full_name"] = "Değişti"
    contract_ids.add(30)
    permissions.add("edit_contracts")
    assert context.current_staff["full_name"] == "Test Personel"
    assert context.personal_contract_ids == frozenset({10, 20})
    assert context.permissions == frozenset({"view_contracts"})
    with pytest.raises(TypeError):
        context.current_staff["full_name"] = "Yazılamaz"


def test_returned_share_source_normalizes_and_validates_fields():
    source = _returned(
        registry_id="7",
        share_package_id="  pkg-stable  ",
        contract_id="42",
        status=" returned ",
        source_contract_revision="3",
        share_format_version="2",
        snapshot_format_version="1",
        return_count="4",
        created_by_staff_id="5",
        last_imported_by_staff_id="6",
        contract_no=" C-42 ",
    )
    assert source.registry_id == 7
    assert source.share_package_id == "pkg-stable"
    assert source.contract_id == 42
    assert source.status == SHARE_STATUS_RETURNED
    assert source.source_contract_revision == 3
    assert source.return_count == 4
    assert source.created_by_staff_id == 5
    assert source.last_imported_by_staff_id == 6
    assert source.contract_no == "C-42"


def test_returned_share_source_accepts_official_final_status():
    assert _returned(status=SHARE_STATUS_MERGED).status == SHARE_STATUS_MERGED


@pytest.mark.parametrize(
    "overrides",
    [
        {"registry_id": 0},
        {"share_package_id": ""},
        {"contract_id": -1},
        {"status": "NOT_OFFICIAL"},
        {"source_contract_revision": -1},
        {"share_format_version": -1},
        {"snapshot_format_version": -1},
        {"return_count": -1},
        {"created_by_staff_id": 0},
        {"last_imported_by_staff_id": 0},
    ],
)
def test_returned_share_source_rejects_invalid_values(overrides):
    with pytest.raises(ValueError):
        _returned(**overrides)


def test_agenda_source_bundle_snapshots_mutable_inputs():
    calendar_values = [
        AgendaCalendarSource(
            entity_type="contract",
            entity_id=42,
            contract_id=42,
        )
    ]
    returned_values = [_returned()]
    bundle = AgendaSourceBundle(
        calendar=calendar_values,
        returned_shares=returned_values,
    )
    calendar_values.clear()
    returned_values.clear()
    assert len(bundle.calendar) == 1
    assert len(bundle.returned_shares) == 1
    assert isinstance(bundle.calendar, tuple)
    assert isinstance(bundle.returned_shares, tuple)


def test_agenda_source_bundle_validates_member_types():
    with pytest.raises(TypeError):
        AgendaSourceBundle(calendar=(object(),))
    with pytest.raises(TypeError):
        AgendaSourceBundle(returned_shares=(object(),))
