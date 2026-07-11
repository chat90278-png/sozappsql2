from __future__ import annotations

import os
from datetime import date

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
from src.domain.agenda.models import AgendaItem, AgendaPresentationProfile
from src.domain.agenda.presentation import AgendaPresentationSnapshot
from src.ui.agenda_compact_widget import AgendaCompactWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _item(key: str, *, severity=AgendaSeverity.INFO, remaining=5, contract_id=10):
    return AgendaItem(
        key=key,
        provider_code="test",
        kind="deadline",
        lifecycle_type=AgendaLifecycleType.CONDITION,
        title=f"Başlık {key}",
        description=f"Açıklama {key}",
        priority=100,
        severity=severity,
        version="v1",
        contract_id=contract_id,
        contract_no="S-1",
        platform="P1",
        effective_date=date(2026, 7, 15),
        remaining_days=remaining,
        supports_snooze=True,
    )


def _snapshot(items=(), *, new_keys=(), active_count=None, new_count=None):
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
        active_count=len(items) if active_count is None else active_count,
        new_count=len(new_keys) if new_count is None else new_count,
        snoozed_count=0,
        filtered_count=0,
        new_keys=frozenset(new_keys),
        compact_limit=2,
        detail_limit=20,
        has_more=len(items) > 2,
    )


def test_fixed_height_matches_header_contract(qapp):
    widget = AgendaCompactWidget()
    assert widget.minimumHeight() == 112
    assert widget.maximumHeight() == 112


def test_empty_state_text(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot())
    assert "Şu anda gündeminiz temiz." in widget.state_label.text()


def test_renders_only_compact_items(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a"), _item("b"), _item("c")]))
    assert [row.item.key for row in widget._rows] == ["a", "b"]


def test_preserves_snapshot_order(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("z"), _item("a")]))
    assert [row.item.key for row in widget._rows] == ["z", "a"]


def test_new_badge(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a")], new_keys={"a"}))
    assert widget.new_badge.text() == "1 yeni"
    assert widget.new_badge.isVisible() or not widget.isVisible()


@pytest.mark.parametrize(
    ("severity", "color"),
    [
        (AgendaSeverity.CRITICAL, "#DC2626"),
        (AgendaSeverity.ATTENTION, "#F59E0B"),
        (AgendaSeverity.INFO, "#2563EB"),
    ],
)
def test_severity_dot_mapping(qapp, severity, color):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a", severity=severity)]))
    dot = widget._rows[0].findChild(QLabel, "agendaSeverityDot")
    assert color.lower() in dot.styleSheet().lower()


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [(-2, "2 gün gecikti"), (0, "Bugün"), (4, "4 gün")],
)
def test_remaining_day_labels(qapp, remaining, expected):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a", remaining=remaining)]))
    label = widget._rows[0].findChild(QLabel, "agendaCompactDate")
    assert label.text() == expected


def test_open_details_signal(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a")]))
    spy = QSignalSpy(widget.open_details_requested)
    QTest.mouseClick(widget.details_button, Qt.LeftButton)
    assert spy.count() == 1


def test_open_contract_signal_uses_contract_id(qapp):
    widget = AgendaCompactWidget()
    widget.set_snapshot(_snapshot([_item("a", contract_id=77)]))
    spy = QSignalSpy(widget.open_contract_requested)
    button = widget._rows[0].findChild(QToolButton, "agendaCompactOpenContract")
    assert button is not None
    widget._rows[0].open_contract_requested.emit(77)
    assert spy.count() == 1
    assert spy.at(0)[0] == 77


def test_loading_and_error_states(qapp):
    widget = AgendaCompactWidget()
    widget.set_loading(True)
    assert widget.state_label.text() == "Yükleniyor…"
    widget.set_error("technical detail")
    assert widget.state_label.text() == "Gündem yüklenemedi"
    assert widget.state_label.toolTip() == "technical detail"


def test_dwell_emits_after_650ms(qapp):
    widget = AgendaCompactWidget()
    item = _item("a")
    widget.set_snapshot(_snapshot([item]))
    spy = QSignalSpy(widget.item_dwell_seen_requested)
    widget._rows[0].selected.emit(item)
    QTest.qWait(450)
    assert spy.count() == 0
    QTest.qWait(300)
    assert spy.count() == 1


def test_dwell_cancelled_when_selection_changes(qapp):
    widget = AgendaCompactWidget()
    first, second = _item("a"), _item("b")
    widget.set_snapshot(_snapshot([first, second]))
    spy = QSignalSpy(widget.item_dwell_seen_requested)
    widget._rows[0].selected.emit(first)
    QTest.qWait(250)
    widget._rows[1].selected.emit(second)
    QTest.qWait(450)
    assert spy.count() == 0
    QTest.qWait(300)
    assert spy.count() == 1
    assert spy.at(0)[0].key == "b"


def test_clear_cancels_timer(qapp):
    widget = AgendaCompactWidget()
    item = _item("a")
    widget.set_snapshot(_snapshot([item]))
    spy = QSignalSpy(widget.item_dwell_seen_requested)
    widget._rows[0].selected.emit(item)
    widget.clear()
    QTest.qWait(750)
    assert spy.count() == 0


def test_set_snapshot_does_not_mutate_snapshot(qapp):
    items = (_item("a"), _item("b"), _item("c"))
    snapshot = _snapshot(items)
    before = snapshot.compact_items
    widget = AgendaCompactWidget()
    widget.set_snapshot(snapshot)
    assert snapshot.compact_items == before
    assert snapshot.all_items == items
