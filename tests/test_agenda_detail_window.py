from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.models import AgendaItem, AgendaItemState, AgendaPresentationProfile
from src.domain.agenda.presentation import AgendaPresentationSnapshot
from src.ui.agenda_detail_window import AgendaDetailWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _item(key: str, *, lifecycle=AgendaLifecycleType.CONDITION, snooze=True, contract_id=4):
    return AgendaItem(
        key=key,
        provider_code="test",
        kind="deadline",
        lifecycle_type=lifecycle,
        title=f"Başlık {key}",
        description=f"Açıklama {key}",
        priority=10,
        severity=AgendaSeverity.ATTENTION,
        version="v1",
        contract_id=contract_id,
        contract_no="S-1",
        platform="P1",
        remaining_days=3,
        supports_snooze=snooze,
    )


def _snapshot(items=(), *, new_keys=(), snoozed=0, states=None):
    items = tuple(items)
    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Kişisel",
        description="",
        permissions=frozenset({"view_contracts"}),
    )
    return AgendaPresentationSnapshot(
        profile=profile,
        all_items=items,
        compact_items=items[:2],
        detail_items=items[:20],
        active_count=len(items),
        new_count=len(new_keys),
        snoozed_count=snoozed,
        filtered_count=0,
        new_keys=frozenset(new_keys),
        states_by_key=states or {},
        compact_limit=2,
        detail_limit=20,
        has_more=len(items) > 20,
    )


def test_window_is_non_modal_tool(qapp):
    window = AgendaDetailWindow()
    assert window.windowFlags() & Qt.Tool
    assert window.windowModality() == Qt.NonModal


def test_renders_detail_items_only(qapp):
    window = AgendaDetailWindow()
    items = tuple(_item(str(i)) for i in range(4))
    snapshot = _snapshot(items)
    object.__setattr__(snapshot, "detail_items", items[:3])
    window.set_snapshot(snapshot)
    assert [row.item.key for row in window._rows] == ["0", "1", "2"]


def test_max_twenty_from_snapshot(qapp):
    window = AgendaDetailWindow()
    items = tuple(_item(str(i)) for i in range(25))
    window.set_snapshot(_snapshot(items))
    assert len(window._rows) == 20


def test_summary_counts(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([_item("a")], new_keys={"a"}, snoozed=2))
    assert "1 aktif" in window.summary_label.text()
    assert "1 yeni" in window.summary_label.text()
    assert "2 ertelendi" in window.summary_label.text()


def test_new_badge_from_new_keys(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([_item("a")], new_keys={"a"}))
    assert window._rows[0].findChild(QLabel, "agendaDetailNewBadge") is not None


def test_seen_item_remains_visible(qapp):
    item = _item("a")
    state = AgendaItemState(
        staff_id=1,
        agenda_key="a",
        seen_at="2026-07-11T10:00:00",
        seen_version="v1",
    )
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([item], states={"a": state}))
    assert [row.item.key for row in window._rows] == ["a"]


def test_condition_shows_snooze_actions(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([_item("a")]))
    assert window._rows[0].findChild(QToolButton, "agendaDetailSnooze") is not None


def test_event_hides_snooze_action(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(
        _snapshot(
            [_item("a", lifecycle=AgendaLifecycleType.EVENT, snooze=False)]
        )
    )
    assert window._rows[0].findChild(QToolButton, "agendaDetailSnooze") is None


def test_preset_signal_codes(qapp):
    window = AgendaDetailWindow()
    item = _item("a")
    window.set_snapshot(_snapshot([item]))
    spy = QSignalSpy(window.snooze_requested)
    row = window._rows[0]
    row.snooze_requested.emit(item, "tomorrow")
    row.snooze_requested.emit(item, "three_days")
    row.snooze_requested.emit(item, "one_week")
    assert [spy.at(i)[1] for i in range(spy.count())] == [
        "tomorrow",
        "three_days",
        "one_week",
    ]


def test_open_contract_signal(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([_item("a", contract_id=91)]))
    spy = QSignalSpy(window.open_contract_requested)
    window._rows[0].open_contract_requested.emit(91)
    assert spy.count() == 1
    assert spy.at(0)[0] == 91


def test_selection_dwell_seen(qapp):
    window = AgendaDetailWindow()
    item = _item("a")
    window.set_snapshot(_snapshot([item]))
    spy = QSignalSpy(window.item_dwell_seen_requested)
    window._rows[0].selected.emit(item)
    QTest.qWait(450)
    assert spy.count() == 0
    QTest.qWait(300)
    assert spy.count() == 1


def test_close_cancels_dwell(qapp):
    window = AgendaDetailWindow()
    item = _item("a")
    window.set_snapshot(_snapshot([item]))
    spy = QSignalSpy(window.item_dwell_seen_requested)
    window._rows[0].selected.emit(item)
    window.close()
    QTest.qWait(750)
    assert spy.count() == 0


def test_loading_error_empty_states(qapp):
    window = AgendaDetailWindow()
    window.set_loading(True)
    assert window.state_label.text() == "Yükleniyor…"
    window.set_error("detail")
    assert window.state_label.text() == "Gündem yüklenemedi"
    window.set_snapshot(_snapshot())
    assert window.state_label.text() == "Şu anda gündeminiz temiz."


def test_snapshot_order_preserved(qapp):
    window = AgendaDetailWindow()
    window.set_snapshot(_snapshot([_item("z"), _item("a"), _item("m")]))
    assert [row.item.key for row in window._rows] == ["z", "a", "m"]
