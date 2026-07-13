from __future__ import annotations

import pytest

from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.models import (
    AgendaItem,
    AgendaItemState,
    AgendaPresentationProfile,
    AgendaResult,
)
from src.domain.agenda.presentation import project_agenda_result


def _profile():
    return AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Kişisel kapsam",
        description="Test",
        permissions=frozenset({"view_contracts"}),
    )


def _item(index: int, severity: AgendaSeverity = AgendaSeverity.INFO):
    return AgendaItem(
        key=f"item-{index}",
        provider_code="test",
        kind="deadline" if index % 2 else "unknown_date",
        lifecycle_type=AgendaLifecycleType.CONDITION,
        title=f"Item {index}",
        description="Description",
        priority=100 - index,
        severity=severity,
        version=f"v{index}",
        supports_snooze=True,
    )


def _result(items):
    items = tuple(items)
    states = {
        items[0].key: AgendaItemState(staff_id=3, agenda_key=items[0].key)
    } if items else {}
    return AgendaResult(
        profile=_profile(),
        items=items,
        new_count=min(2, len(items)),
        active_count=len(items),
        counts_by_kind={"deadline": sum(item.kind == "deadline" for item in items)},
        new_keys=frozenset(item.key for item in items[:2]),
        states_by_key=states,
        snoozed_count=1,
        filtered_count=2,
    )


def test_service_order_is_preserved_without_resort():
    items = (_item(3), _item(1), _item(2))
    snapshot = project_agenda_result(_result(items))
    assert snapshot.all_items == items
    assert snapshot.compact_items == items[:2]
    assert snapshot.detail_items == items


def test_default_compact_limit_is_two():
    items = tuple(_item(index) for index in range(5))
    snapshot = project_agenda_result(_result(items))
    assert snapshot.compact_limit == 2
    assert snapshot.compact_items == items[:2]


def test_default_detail_limit_is_twenty_and_has_more_uses_active_count():
    items = tuple(_item(index) for index in range(22))
    snapshot = project_agenda_result(_result(items))
    assert snapshot.detail_limit == 20
    assert snapshot.detail_items == items[:20]
    assert snapshot.has_more is True


def test_has_more_is_false_at_exact_detail_boundary():
    items = tuple(_item(index) for index in range(20))
    snapshot = project_agenda_result(_result(items))
    assert snapshot.has_more is False


def test_severity_counts_use_stable_enum_values():
    items = (
        _item(1, AgendaSeverity.INFO),
        _item(2, AgendaSeverity.ATTENTION),
        _item(3, AgendaSeverity.ATTENTION),
        _item(4, AgendaSeverity.CRITICAL),
    )
    snapshot = project_agenda_result(_result(items))
    assert dict(snapshot.counts_by_severity) == {
        "INFO": 1,
        "ATTENTION": 2,
        "CRITICAL": 1,
    }


def test_mapping_and_collection_snapshots_are_immutable():
    items = (_item(1),)
    snapshot = project_agenda_result(_result(items))
    assert isinstance(snapshot.all_items, tuple)
    assert isinstance(snapshot.compact_items, tuple)
    assert isinstance(snapshot.detail_items, tuple)
    assert isinstance(snapshot.new_keys, frozenset)
    with pytest.raises(TypeError):
        snapshot.counts_by_kind["x"] = 1
    with pytest.raises(TypeError):
        snapshot.counts_by_severity["INFO"] = 99
    with pytest.raises(TypeError):
        snapshot.states_by_key["x"] = AgendaItemState(staff_id=3, agenda_key="x")


def test_negative_and_boolean_limits_are_rejected():
    result = _result((_item(1),))
    for field_name, kwargs in (
        ("compact", {"compact_limit": -1}),
        ("detail", {"detail_limit": -1}),
        ("compact_bool", {"compact_limit": True}),
        ("detail_bool", {"detail_limit": False}),
    ):
        with pytest.raises(ValueError, match="limit"):
            project_agenda_result(result, **kwargs)


def test_compact_and_detail_limits_are_independent():
    items = tuple(_item(index) for index in range(10))
    snapshot = project_agenda_result(
        _result(items),
        compact_limit=5,
        detail_limit=3,
    )
    assert snapshot.compact_items == items[:5]
    assert snapshot.detail_items == items[:3]
    assert snapshot.has_more is True


def test_zero_limits_are_valid():
    items = (_item(1),)
    snapshot = project_agenda_result(
        _result(items),
        compact_limit=0,
        detail_limit=0,
    )
    assert snapshot.compact_items == ()
    assert snapshot.detail_items == ()
    assert snapshot.has_more is True


def test_projection_does_not_mutate_result_or_items():
    items = [_item(2), _item(1)]
    result = _result(items)
    original_items = result.items
    original_counts = dict(result.counts_by_kind)
    snapshot = project_agenda_result(result, compact_limit=1, detail_limit=1)
    assert result.items == original_items
    assert dict(result.counts_by_kind) == original_counts
    assert snapshot.all_items == original_items
