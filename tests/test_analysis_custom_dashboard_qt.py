from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspaceError,
    DashboardWorkspaceStore,
)
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import FileAnalysisRepository


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _window(qt_app, tmp_path, *, workspace_store=None):
    repo_root = tmp_path / "analyses"
    workspace_root = tmp_path / "dashboards"
    repository = FileAnalysisRepository(None, repo_root)
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=workspace_store or DashboardWorkspaceStore(workspace_root),
        analysis_repository=repository,
    )
    window.show()
    qt_app.processEvents()
    return window, repository, repo_root, workspace_root


def _open_builder(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
    qt_app.processEvents()
    return window._analysis_builder_widget


def _open_library(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(MY_ANALYSES_ID))
    qt_app.processEvents()
    return window._analysis_library_widget


def _open_dashboard(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(CUSTOM_DASHBOARD_ID))
    qt_app.processEvents()
    return window._dashboard_canvas


def _configure_chart(builder, *, title="Platform Bazlı Teslimatlar"):
    builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
    builder.visualization_combo.setCurrentIndex(
        builder.visualization_combo.findData("horizontal_bar")
    )
    builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
    builder.aggregation_combo.setCurrentIndex(
        builder.aggregation_combo.findData("count_rows")
    )
    builder.title_edit.setText(title)


def _save_chart(window, qt_app, *, title="Platform Bazlı Teslimatlar"):
    builder = _open_builder(window, qt_app)
    _configure_chart(builder, title=title)
    QTest.mouseClick(builder.preview_button, Qt.LeftButton)
    qt_app.processEvents()
    QTest.mouseClick(builder.save_button, Qt.LeftButton)
    qt_app.processEvents()
    return builder, builder.controller.current_saved_analysis_id


def _library_dashboard_button(library, analysis_id: str) -> QPushButton:
    for frame in library.findChildren(QFrame, "analysisLibraryItem"):
        if frame.property("analysisId") == analysis_id:
            button = frame.findChild(QPushButton, "analysisLibraryDashboardButton")
            assert button is not None
            return button
    raise AssertionError(f"Library item not found: {analysis_id}")


def test_builder_unsaved_rejects_dashboard_then_saved_analysis_can_pin(qt_app, tmp_path):
    window, _repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        builder = _open_builder(window, qt_app)
        assert builder.dashboard_button.text() == "Dashboard'a Ekle"
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        assert "önce analizi kaydedin" in builder.save_status.text()
        assert not any(
            placement.source_screen_id == CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
            for placement in window.workspace.placements
        )

        _configure_chart(builder)
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id and saved_id.startswith("custom-")
        assert builder.dashboard_button.text() == "Dashboard'a Ekle"

        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert builder.dashboard_button.text() == "Dashboard'dan Kaldır"
    finally:
        window.close()


def test_library_dashboard_button_pin_state_and_unpin(qt_app, tmp_path):
    window, _repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        _builder, saved_id = _save_chart(window, qt_app)
        library = _open_library(window, qt_app)
        button = _library_dashboard_button(library, saved_id)
        assert button.text() == "+ Dashboard"
        assert button.isEnabled() is True

        QTest.mouseClick(button, Qt.LeftButton)
        qt_app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        button = _library_dashboard_button(library, saved_id)
        assert button.text() == "✓ Dashboard'da"

        QTest.mouseClick(button, Qt.LeftButton)
        qt_app.processEvents()
        assert not window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert _library_dashboard_button(library, saved_id).text() == "+ Dashboard"
    finally:
        window.close()


def test_custom_card_renders_in_existing_canvas_and_uses_drag_resize_edit_path(qt_app, tmp_path):
    window, _repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        builder, saved_id = _save_chart(window, qt_app)
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        canvas = _open_dashboard(window, qt_app)
        assert canvas is not None
        placement = window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert placement is not None
        frame = canvas._frames[placement.placement_id]
        assert frame.card.title == "Platform Bazlı Teslimatlar"
        assert frame.card.meta["custom_analysis_id"] == saved_id

        window._enter_dashboard_edit()
        qt_app.processEvents()
        canvas = window._dashboard_canvas
        session = window._dashboard_edit_session
        placement = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        frame = canvas._frames[placement.placement_id]
        drag_start = frame.drag_handle.rect().center()
        QTest.mousePress(frame.drag_handle, Qt.LeftButton, Qt.NoModifier, drag_start)
        QTest.mouseMove(frame.drag_handle, QPoint(drag_start.x() + 160, drag_start.y()))
        QTest.mouseRelease(
            frame.drag_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(drag_start.x() + 160, drag_start.y()),
        )
        qt_app.processEvents()
        moved = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert session.undo_depth == 1

        frame = canvas._frames[moved.placement_id]
        before_size = (moved.w, moved.h)
        resize_start = frame.resize_handle.rect().center()
        QTest.mousePress(frame.resize_handle, Qt.LeftButton, Qt.NoModifier, resize_start)
        QTest.mouseMove(
            frame.resize_handle,
            QPoint(resize_start.x() + 120, resize_start.y() + 80),
        )
        QTest.mouseRelease(
            frame.resize_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(resize_start.x() + 120, resize_start.y() + 80),
        )
        qt_app.processEvents()
        resized = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert (resized.w, resized.h) != before_size
        assert session.undo_depth == 2
        window._save_dashboard_edit()
        qt_app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
    finally:
        window.close()


def test_restart_resolves_pinned_custom_card_and_edit_same_id_updates_dashboard(qt_app, tmp_path):
    window, repo, repo_root, workspace_root = _window(qt_app, tmp_path)
    builder, saved_id = _save_chart(window, qt_app)
    QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
    qt_app.processEvents()
    placement_id = window.workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        saved_id,
    ).placement_id
    window.close()

    repository = FileAnalysisRepository(None, repo_root)
    reloaded = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(workspace_root),
        analysis_repository=repository,
    )
    reloaded.show()
    qt_app.processEvents()
    try:
        canvas = _open_dashboard(reloaded, qt_app)
        placement = reloaded.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert placement is not None and placement.placement_id == placement_id
        assert canvas._frames[placement_id].card.title == "Platform Bazlı Teslimatlar"

        reloaded._edit_saved_analysis(saved_id)
        qt_app.processEvents()
        edited = reloaded._analysis_builder_widget
        edited.title_edit.setText("Platform Bazlı Teslimatlar Güncel")
        QTest.mouseClick(edited.save_button, Qt.LeftButton)
        qt_app.processEvents()
        assert edited.controller.current_saved_analysis_id == saved_id
        canvas = _open_dashboard(reloaded, qt_app)
        placement = reloaded.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert placement.placement_id == placement_id
        assert canvas._frames[placement_id].card.title == "Platform Bazlı Teslimatlar Güncel"

        library = _open_library(reloaded, qt_app)
        library.copy_analysis(saved_id)
        qt_app.processEvents()
        copied_id = next(item.analysis_id for item in library.items if item.analysis_id != saved_id)
        assert not reloaded.workspace.contains(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            copied_id,
        )
    finally:
        reloaded.close()


def test_pinned_analysis_delete_removes_only_custom_placement_and_preserves_prepared(qt_app, tmp_path):
    window, repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        prepared_card = window._dashboard_items[0].cards[0]
        window._toggle_dashboard_card(prepared_card)
        prepared_key = (prepared_card.screen_id, prepared_card.card_id)
        builder, saved_id = _save_chart(window, qt_app)
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        assert window.workspace.contains(*prepared_key)
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)

        library = _open_library(window, qt_app)
        assert library.delete_analysis(saved_id, confirmed=True) is True
        qt_app.processEvents()
        assert repo.get_analysis(saved_id) is None
        assert window.workspace.contains(*prepared_key)
        assert not window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert len(window.workspace.placements) == 1
    finally:
        window.close()


def test_workspace_save_failure_does_not_commit_custom_pin_ui_state(qt_app, tmp_path, monkeypatch):
    class FailingSaveStore:
        def __init__(self, root):
            self.inner = DashboardWorkspaceStore(root)

        def load(self, *args, **kwargs):
            return self.inner.load(*args, **kwargs)

        def save(self, *_args, **_kwargs):
            raise DashboardWorkspaceError("save failed")

    monkeypatch.setattr("analysis_center.analysis_qt_window.QMessageBox.warning", lambda *args: None)
    store = FailingSaveStore(tmp_path / "dashboards")
    window, _repo, _repo_root, _workspace_root = _window(
        qt_app,
        tmp_path,
        workspace_store=store,
    )
    try:
        builder, saved_id = _save_chart(window, qt_app)
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        assert not window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert builder.dashboard_button.text() == "Dashboard'a Ekle"
    finally:
        window.close()


def test_custom_pin_unpin_does_not_reload_sts_payload(qt_app, tmp_path):
    window, _repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        _builder, saved_id = _save_chart(window, qt_app)
        refresh_calls = 0
        real_refresh = window.controller.refresh_payload

        def spy_refresh():
            nonlocal refresh_calls
            refresh_calls += 1
            return real_refresh()

        window.controller.refresh_payload = spy_refresh
        library = _open_library(window, qt_app)
        QTest.mouseClick(_library_dashboard_button(library, saved_id), Qt.LeftButton)
        qt_app.processEvents()
        QTest.mouseClick(_library_dashboard_button(library, saved_id), Qt.LeftButton)
        qt_app.processEvents()
        assert refresh_calls == 0
    finally:
        window.close()


def test_invalid_saved_analysis_dashboard_action_is_disabled(qt_app, tmp_path):
    window, repo, _repo_root, _workspace_root = _window(qt_app, tmp_path)
    try:
        from analysis_center.analysis_definitions import AnalysisDefinition, MeasureDefinition

        repo.save_analysis(
            AnalysisDefinition(
                analysis_id="custom-invalid-dashboard",
                title="Stale Dashboard Analizi",
                dataset="missing_dataset",
                visualization="kpi",
                measures=[MeasureDefinition("", "count_rows")],
            )
        )
        library = _open_library(window, qt_app)
        library.refresh_items()
        qt_app.processEvents()
        button = _library_dashboard_button(library, "custom-invalid-dashboard")
        assert button.isEnabled() is False
        assert button.text() == "+ Dashboard"
    finally:
        window.close()
