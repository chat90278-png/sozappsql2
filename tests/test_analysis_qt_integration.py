from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from analysis_center.analysis_dashboard_canvas import (
    DRAG_HANDLE_HIT_WIDTH,
    RESIZE_HANDLE_HIT_SIZE,
    auto_scroll_delta,
)
from analysis_center.analysis_dashboard_geometry import GridGeometry
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=True,
    )


def test_analysis_center_window_renders_dashboard_and_tur9_analysis_screens(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        assert window.navigation.count() == 8
        assert window.current_item_id() == CUSTOM_DASHBOARD_ID
        assert window.navigation.item(0).text() == "Dashboard"
        assert "Salt-okunur" not in window.status_text.text()
        assert "Örnek veri" in window.status_text.text()
        assert window.stack.count() == 8
    finally:
        window.close()


def test_analysis_center_refresh_preserves_selected_screen(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        platform_row = window._item_ids.index("platform_analysis")
        window.navigation.setCurrentRow(platform_row)
        assert window.current_item_id() == "platform_analysis"
        window.refresh_data()
        assert window.current_item_id() == "platform_analysis"
    finally:
        window.close()


def test_analysis_center_pins_live_card_to_persistent_dashboard_without_engine_refresh(qt_app, tmp_path):
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    window = AnalysisCenterWindow(settings=_settings(), workspace_store=store)
    try:
        executive = next(item for item in window._dashboard_items if item.item_id == "executive_summary")
        source_card = executive.cards[0]
        payload_identity = id(window._payload)

        window._toggle_dashboard_card(source_card)

        assert id(window._payload) == payload_identity
        assert window.workspace.contains(source_card.screen_id, source_card.card_id) is True
        assert store.load(None).contains(source_card.screen_id, source_card.card_id) is True
        cards, missing = window.workspace.resolve_cards(window._dashboard_items)
        assert missing == []
        assert cards[0].value == source_card.value
    finally:
        window.close()

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton


def _pin_dashboard_cards(window, card_ids):
    index = {
        card.card_id: card
        for item in window._dashboard_items
        for card in item.cards
    }
    for card_id in card_ids:
        window._toggle_dashboard_card(index[card_id])


def _placement_by_card(workspace, card_id):
    return next(item for item in workspace.placements if item.card_id == card_id)


def _button_texts(window):
    return {button.text() for button in window.findChildren(QPushButton)}


def test_dashboard_edit_mode_real_mouse_drag_resize_history_and_cancel(qt_app, tmp_path):
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    window = AnalysisCenterWindow(settings=_settings(), workspace_store=store)
    try:
        _pin_dashboard_cards(
            window,
            ["exec_total_contracts", "exec_upcoming_deadlines", "exec_status_distribution"],
        )
        saved_before = window.workspace.to_dict()
        window.show()
        qt_app.processEvents()

        assert "Dashboard'u Düzenle" in _button_texts(window)
        window._enter_dashboard_edit()
        qt_app.processEvents()

        assert {"Kaydet", "Vazgeç", "Yerleşimi Sıfırla", "Geri Al", "Yinele"} <= _button_texts(window)
        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None
        assert canvas is not None

        kpi = _placement_by_card(session.working_workspace, "exec_total_contracts")
        drag_handle = canvas._frames[kpi.placement_id].drag_handle
        start = drag_handle.rect().center()
        QTest.mousePress(drag_handle, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(drag_handle, QPoint(start.x() + int(canvas.width() * 0.35), start.y()))
        QTest.mouseRelease(
            drag_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(start.x() + int(canvas.width() * 0.35), start.y()),
        )
        qt_app.processEvents()

        moved = _placement_by_card(session.working_workspace, "exec_total_contracts")
        pushed = _placement_by_card(session.working_workspace, "exec_upcoming_deadlines")
        assert moved.x > 0
        assert pushed.y > 0
        assert session.undo_depth == 1
        assert window.workspace.to_dict() == saved_before

        chart = _placement_by_card(session.working_workspace, "exec_status_distribution")
        resize_handle = canvas._frames[chart.placement_id].resize_handle
        assert resize_handle.isVisible() is True
        original_size = (chart.w, chart.h)
        resize_start = resize_handle.rect().center()
        QTest.mousePress(resize_handle, Qt.LeftButton, Qt.NoModifier, resize_start)
        QTest.mouseMove(resize_handle, QPoint(resize_start.x() + 120, resize_start.y() + 80))
        QTest.mouseRelease(
            resize_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(resize_start.x() + 120, resize_start.y() + 80),
        )
        qt_app.processEvents()

        resized = _placement_by_card(session.working_workspace, "exec_status_distribution")
        assert (resized.w, resized.h) != original_size
        assert session.undo_depth == 2

        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        qt_app.processEvents()
        assert session.undo_depth == 1
        assert session.can_redo is True
        QTest.keyClick(window, Qt.Key_Y, Qt.ControlModifier)
        qt_app.processEvents()
        assert session.undo_depth == 2

        window._cancel_dashboard_edit()
        qt_app.processEvents()
        assert window._dashboard_edit_session is None
        assert window.workspace.to_dict() == saved_before
        assert "Dashboard'u Düzenle" in _button_texts(window)
    finally:
        window.close()


def test_dashboard_edit_save_persists_and_reset_cancel_restores_saved_layout(qt_app, tmp_path):
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    window = AnalysisCenterWindow(settings=_settings(), workspace_store=store)
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_status_distribution"])
        window.show()
        qt_app.processEvents()
        window._enter_dashboard_edit()
        qt_app.processEvents()

        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        kpi = _placement_by_card(session.working_workspace, "exec_total_contracts")
        drag_handle = canvas._frames[kpi.placement_id].drag_handle
        start = drag_handle.rect().center()
        QTest.mousePress(drag_handle, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(drag_handle, QPoint(start.x() + int(canvas.width() * 0.5), start.y() + 140))
        QTest.mouseRelease(
            drag_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(start.x() + int(canvas.width() * 0.5), start.y() + 140),
        )
        qt_app.processEvents()
        working_after_drag = session.working_workspace.to_dict()

        window._save_dashboard_edit()
        qt_app.processEvents()
        assert window._dashboard_edit_session is None
        assert window.workspace.to_dict() == working_after_drag
        assert store.load(None, dashboard_items=window._dashboard_items).to_dict() == working_after_drag

        saved_before_reset = window.workspace.to_dict()
        window._enter_dashboard_edit()
        qt_app.processEvents()
        window._reset_dashboard_edit()
        assert window._dashboard_edit_session is not None
        assert window._dashboard_edit_session.working_workspace.to_dict() != saved_before_reset
        window._cancel_dashboard_edit()
        qt_app.processEvents()
        assert window.workspace.to_dict() == saved_before_reset
    finally:
        window.close()


def test_dashboard_mouse_preview_does_not_persist_or_reload_analysis_payload(qt_app, tmp_path):
    class CountingStore(DashboardWorkspaceStore):
        def __init__(self, root):
            super().__init__(root)
            self.save_calls = 0

        def save(self, source, workspace):
            self.save_calls += 1
            return super().save(source, workspace)

    store = CountingStore(tmp_path / "dashboards")
    window = AnalysisCenterWindow(settings=_settings(), workspace_store=store)
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_upcoming_deadlines"])
        baseline_save_calls = store.save_calls
        payload_identity = id(window._payload)
        window.show()
        qt_app.processEvents()
        window._enter_dashboard_edit()
        qt_app.processEvents()

        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        placement = _placement_by_card(session.working_workspace, "exec_total_contracts")
        handle = canvas._frames[placement.placement_id].drag_handle
        start = handle.rect().center()
        QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, start)
        for offset in (40, 80, 120, 160, 200, 240):
            QTest.mouseMove(handle, QPoint(start.x() + offset, start.y() + 30))
            qt_app.processEvents()
            assert store.save_calls == baseline_save_calls
            assert id(window._payload) == payload_identity
        QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + 240, start.y() + 30))
        qt_app.processEvents()

        assert store.save_calls == baseline_save_calls
        assert id(window._payload) == payload_identity
        window._save_dashboard_edit()
        assert store.save_calls == baseline_save_calls + 1
    finally:
        window.close()


def test_dashboard_locked_affordances_are_hidden_and_remove_is_undoable(qt_app, tmp_path):
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    window = AnalysisCenterWindow(settings=_settings(), workspace_store=store)
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_upcoming_deadlines"])
        locked = _placement_by_card(window.workspace, "exec_total_contracts")
        locked.locked = True
        window.workspace.validate()
        window._render_items(CUSTOM_DASHBOARD_ID)
        window.show()
        qt_app.processEvents()
        window._enter_dashboard_edit()
        qt_app.processEvents()

        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        locked = _placement_by_card(session.working_workspace, "exec_total_contracts")
        locked_frame = canvas._frames[locked.placement_id]
        assert locked_frame.drag_handle.isVisible() is False
        assert locked_frame.resize_handle.isVisible() is False

        removable = _placement_by_card(session.working_workspace, "exec_upcoming_deadlines")
        removable_frame = canvas._frames[removable.placement_id]
        assert removable_frame.remove_button.isVisible() is True
        QTest.mouseClick(removable_frame.remove_button, Qt.LeftButton)
        qt_app.processEvents()
        assert all(item.placement_id != removable.placement_id for item in session.working_workspace.placements)
        assert removable_frame.isVisible() is False
        assert session.undo_depth == 1

        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        qt_app.processEvents()
        assert any(item.placement_id == removable.placement_id for item in session.working_workspace.placements)
        assert removable_frame.isVisible() is True
    finally:
        window.close()


def test_dashboard_canvas_viewport_resize_changes_pixel_rect_not_logical_layout(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_status_distribution"])
        window.resize(1000, 700)
        window.show()
        qt_app.processEvents()
        canvas = window._dashboard_canvas
        assert canvas is not None
        session = canvas.session
        logical_before = session.working_workspace.to_dict()
        placement = _placement_by_card(session.working_workspace, "exec_status_distribution")
        frame = canvas._frames[placement.placement_id]
        rect_before = frame.geometry()

        window.resize(1500, 800)
        qt_app.processEvents()
        rect_after = frame.geometry()

        assert rect_after.width() != rect_before.width()
        assert session.working_workspace.to_dict() == logical_before
    finally:
        window.close()



def test_dashboard_tur12_edit_chrome_placeholder_and_toolbar_hierarchy(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_upcoming_deadlines"])
        window.resize(1200, 800)
        window.show()
        qt_app.processEvents()
        window._enter_dashboard_edit()
        qt_app.processEvents()

        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        placement = _placement_by_card(session.working_workspace, "exec_total_contracts")
        frame = canvas._frames[placement.placement_id]

        assert frame.edit_bar.height() == 28
        assert frame.drag_handle.width() == DRAG_HANDLE_HIT_WIDTH
        assert frame.drag_handle.text() == "⠿"
        assert frame.resize_handle.width() == RESIZE_HANDLE_HIT_SIZE
        assert frame.resize_handle.height() == RESIZE_HANDLE_HIT_SIZE

        buttons = {button.text(): button for button in window.findChildren(QPushButton)}
        assert buttons["Geri Al"].objectName() == "analysisDashboardUtilityButton"
        assert buttons["Yinele"].objectName() == "analysisDashboardUtilityButton"
        assert buttons["Yerleşimi Sıfırla"].objectName() == "analysisDashboardUtilityButton"
        assert buttons["Vazgeç"].objectName() == "analysisDashboardCancelButton"
        assert buttons["Kaydet"].objectName() == "analysisDashboardSaveButton"
        assert buttons["Geri Al"].isEnabled() is False
        assert buttons["Yinele"].isEnabled() is False

        logical_before = (placement.x, placement.y, placement.w, placement.h)
        press_point = QPoint(max(1, frame.drag_handle.width() - 3), 4)
        QTest.mousePress(frame.drag_handle, Qt.LeftButton, Qt.NoModifier, press_point)
        qt_app.processEvents()
        current = _placement_by_card(session.working_workspace, "exec_total_contracts")
        assert (current.x, current.y, current.w, current.h) == logical_before
        assert canvas.drag_placeholder_visible is True
        geometry = GridGeometry(canvas.width(), session.working_workspace.layout)
        expected = geometry.placement_rect(current)
        placeholder = canvas.drag_placeholder_geometry
        assert (placeholder.x(), placeholder.y(), placeholder.width(), placeholder.height()) == (
            expected.x,
            expected.y,
            expected.width,
            expected.height,
        )

        target = QPoint(press_point.x() + int(geometry.column_pitch * 4.1), press_point.y())
        QTest.mouseMove(frame.drag_handle, target)
        qt_app.processEvents()
        moved = _placement_by_card(session.working_workspace, "exec_total_contracts")
        expected = GridGeometry(canvas.width(), session.working_workspace.layout).placement_rect(moved)
        placeholder = canvas.drag_placeholder_geometry
        assert (placeholder.x(), placeholder.y(), placeholder.width(), placeholder.height()) == (
            expected.x,
            expected.y,
            expected.width,
            expected.height,
        )

        QTest.mouseRelease(frame.drag_handle, Qt.LeftButton, Qt.NoModifier, target)
        qt_app.processEvents()
        assert canvas.drag_placeholder_visible is False
        assert buttons["Geri Al"].isEnabled() is True

        current = _placement_by_card(session.working_workspace, "exec_total_contracts")
        QTest.mousePress(frame.drag_handle, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3))
        qt_app.processEvents()
        assert canvas.drag_placeholder_visible is True
        canvas.cancel_active_interaction()
        qt_app.processEvents()
        assert canvas.drag_placeholder_visible is False
        assert session.interaction_mode.value == "idle"
    finally:
        window.close()


def test_dashboard_auto_scroll_helper_is_bounded_and_canvas_is_idle_safe(qt_app, tmp_path):
    assert auto_scroll_delta(300, 600) == 0
    assert -18 <= auto_scroll_delta(0, 600) < 0
    assert 0 < auto_scroll_delta(599, 600) <= 18

    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        _pin_dashboard_cards(window, ["exec_total_contracts", "exec_upcoming_deadlines"])
        window.resize(900, 420)
        window.show()
        qt_app.processEvents()
        window._enter_dashboard_edit()
        qt_app.processEvents()
        canvas = window._dashboard_canvas
        session = window._dashboard_edit_session
        assert canvas is not None and session is not None
        scroll = canvas._scroll_area()
        assert scroll is not None
        bar = scroll.verticalScrollBar()
        before = bar.value()
        canvas._auto_scroll_drag(QPoint(0, 0))
        qt_app.processEvents()
        assert session.interaction_mode.value == "idle"
        assert bar.value() == before
    finally:
        window.close()
