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
