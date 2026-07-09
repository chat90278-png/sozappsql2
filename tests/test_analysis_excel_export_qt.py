from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_excel_export import DashboardExcelExportResult
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _button(window, text: str) -> QPushButton:
    return next(
        button
        for button in window.stack.currentWidget().findChildren(QPushButton)
        if button.text() == text
    )


def _open_dashboard(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(CUSTOM_DASHBOARD_ID))
    qt_app.processEvents()


def test_dashboard_excel_action_visible_normal_hidden_edit_and_does_not_refresh_source(
    qt_app,
    tmp_path,
    monkeypatch,
):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    try:
        prepared = next(
            card
            for item in window._dashboard_items
            if item.item_id == "executive_summary"
            for card in item.cards
            if card.enabled
        )
        window._toggle_dashboard_card(prepared)
        _open_dashboard(window, qt_app)
        window.show()
        qt_app.processEvents()

        export_button = _button(window, "Excel'e Aktar")
        assert export_button.isVisible() is True
        baseline_payload = id(window._payload)
        refresh_calls = 0
        real_refresh = window.controller.refresh_payload

        def refresh_spy():
            nonlocal refresh_calls
            refresh_calls += 1
            return real_refresh()

        window.controller.refresh_payload = refresh_spy
        selected = tmp_path / "dashboard-output"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(selected), "Excel Dosyası (*.xlsx)"),
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
        exported: list[Path] = []

        def fake_export(path, **kwargs):
            exported.append(Path(path))
            assert len(kwargs["collection"].items) == 1
            assert kwargs["registry"] is window.controller.analysis_service.registry
            assert kwargs["workspace_card_count"] == len(window.workspace.placements)
            return DashboardExcelExportResult(
                output_path=Path(path).with_suffix(".xlsx"),
                exported_card_count=1,
                warning_count=0,
                sheet_count=2,
            )

        window._dashboard_excel_exporter = fake_export
        QTest.mouseClick(export_button, Qt.LeftButton)
        for _ in range(200):
            qt_app.processEvents()
            if window._dashboard_excel_thread is None:
                break
            QTest.qWait(5)

        assert window._dashboard_excel_thread is None
        assert exported == [selected]
        assert refresh_calls == 0
        assert id(window._payload) == baseline_payload

        window._enter_dashboard_edit()
        qt_app.processEvents()
        assert not any(
            button.text() == "Excel'e Aktar" and button.isVisible()
            for button in window.findChildren(QPushButton)
        )
    finally:
        window.close()


def test_dashboard_excel_worker_keeps_qt_event_loop_responsive(
    qt_app,
    tmp_path,
    monkeypatch,
):
    import threading

    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards-worker"),
    )
    release = threading.Event()
    started = threading.Event()
    try:
        prepared = next(
            card
            for item in window._dashboard_items
            if item.item_id == "executive_summary"
            for card in item.cards
            if card.enabled
        )
        window._toggle_dashboard_card(prepared)
        _open_dashboard(window, qt_app)
        window.show()
        qt_app.processEvents()

        selected = tmp_path / "background-dashboard.xlsx"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(selected), "Excel Dosyası (*.xlsx)"),
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

        def slow_export(path, **kwargs):
            started.set()
            assert release.wait(timeout=5)
            return DashboardExcelExportResult(
                output_path=Path(path),
                exported_card_count=1,
                warning_count=0,
                sheet_count=2,
            )

        window._dashboard_excel_exporter = slow_export
        export_button = _button(window, "Excel'e Aktar")
        QTest.mouseClick(export_button, Qt.LeftButton)
        assert started.wait(timeout=2)

        event_loop_tick: list[str] = []
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: event_loop_tick.append("tick"))
        for _ in range(20):
            qt_app.processEvents()
            if event_loop_tick:
                break
            QTest.qWait(5)
        assert event_loop_tick == ["tick"]
        assert window._dashboard_excel_thread is not None
        assert export_button.isEnabled() is False

        release.set()
        for _ in range(200):
            qt_app.processEvents()
            if window._dashboard_excel_thread is None:
                break
            QTest.qWait(5)
        assert window._dashboard_excel_thread is None
        assert window._last_dashboard_excel_export_result is not None
    finally:
        release.set()
        window.close()
