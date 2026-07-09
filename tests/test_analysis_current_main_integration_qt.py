from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from src.ui.analysis_center_window import AnalysisCenterWindow
from src.ui.main_page_analysis_window import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _reports_menu(window):
    menu = window.top_actions_menu
    return next(
        action.menu()
        for action in menu.actions()
        if action.menu() is not None and str(action.text() or "").replace("&", "") == "Raporlar"
    )


def test_compact_main_window_keeps_ui_and_adds_analysis_center_report_action(qt_app):
    window = MainWindow()
    try:
        reports = _reports_menu(window)
        labels = [str(action.text() or "").replace("&", "") for action in reports.actions()]
        assert labels.count("Analiz Merkezi") == 1
        assert "Tahmini Teslimat Takvimi" in labels
        assert "Platform Teslimat Özeti" in labels
    finally:
        window.close()


def test_analysis_center_uses_current_tool_window_lifecycle_and_export_permission(
    qt_app,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "STS-A1__v17__2026-07-09_10-00.sts"

    class DummyDB:
        path = source

    class DummyStore:
        db = DummyDB()
        path = source

    window = MainWindow()
    try:
        window.store = DummyStore()
        window.path = source
        window.contract_index = [{"id": 7, "platform": "AKINCI"}]
        monkeypatch.setattr(window, "is_sts_mode", lambda: True)

        permission_calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            window,
            "require_permission_ui",
            lambda code, title="": permission_calls.append((code, title)) or False,
        )

        opened: dict[str, object] = {}

        def fake_open_or_raise(key, title, factory):
            opened.update(key=key, title=title, factory=factory)
            return "analysis-window"

        monkeypatch.setattr(window, "open_or_raise_tool_window", fake_open_or_raise)

        captured: dict[str, object] = {}

        class FakeAnalysisCenterWindow:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "src.ui.analysis_center_window.AnalysisCenterWindow",
            FakeAnalysisCenterWindow,
        )

        result = window.open_analysis_center()
        assert result == "analysis-window"
        assert opened["key"] == "report:analysis_center"
        assert opened["title"] == "Analiz Merkezi"

        factory = opened["factory"]
        fake_widget = factory()
        assert isinstance(fake_widget, FakeAnalysisCenterWindow)
        assert Path(captured["source"]) == source
        assert captured["contract_index"] == [{"id": 7, "platform": "AKINCI"}]
        assert captured["parent"] is window

        export_guard = captured["export_guard"]
        assert export_guard() is False
        assert permission_calls == [("export_data", "Dashboard Excel")]
    finally:
        window.store = None
        window.close()


def test_current_analysis_window_blocks_dashboard_export_before_tur21_export_flow(
    qt_app,
    tmp_path,
    monkeypatch,
):
    calls: list[str] = []
    window = AnalysisCenterWindow(
        settings=VisualSettings(
            show_disabled_sections=False,
            empty_state_uses_sample=True,
        ),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards-guard"),
        export_guard=lambda: False,
    )
    try:
        monkeypatch.setattr(
            "analysis_center.analysis_qt_window.AnalysisCenterWindow._export_dashboard_to_excel",
            lambda self: calls.append("base-export"),
        )

        window._export_dashboard_to_excel()

        assert calls == []
        assert window._dashboard_excel_thread is None
    finally:
        window.close()
