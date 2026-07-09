from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_definitions import AnalysisDefinition, MeasureDefinition
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import FileAnalysisRepository


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _window(qt_app, tmp_path, *, repo=None):
    repository = repo or FileAnalysisRepository(None, tmp_path / "analyses")
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
        analysis_repository=repository,
    )
    window.show()
    qt_app.processEvents()
    return window, repository


def _open_builder(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
    qt_app.processEvents()
    assert window._analysis_builder_widget is not None
    return window._analysis_builder_widget


def _open_library(window, qt_app):
    window.navigation.setCurrentRow(window._item_ids.index(MY_ANALYSES_ID))
    qt_app.processEvents()
    assert window._analysis_library_widget is not None
    return window._analysis_library_widget


def _configure_chart(builder):
    builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
    builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("horizontal_bar"))
    builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
    builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
    builder.title_edit.setText("Platform Bazlı Teslimatlar")


def _save_chart(window, qt_app):
    builder = _open_builder(window, qt_app)
    _configure_chart(builder)
    QTest.mouseClick(builder.preview_button, Qt.LeftButton)
    qt_app.processEvents()
    assert builder._preview_widget.findChild(QLabel, "analysisCardTitle") is not None
    QTest.mouseClick(builder.save_button, Qt.LeftButton)
    qt_app.processEvents()
    return builder, builder.controller.current_saved_analysis_id


def test_analizlerim_navigation_empty_state_and_new_action(qt_app, tmp_path):
    window, _repo = _window(qt_app, tmp_path)
    try:
        assert "Analizlerim" in [window.navigation.item(i).text() for i in range(window.navigation.count())]
        library = _open_library(window, qt_app)
        empty = library.findChild(QLabel, "analysisBuilderPreviewInfo")
        assert empty is not None
        assert "Henüz kaydedilmiş analiziniz yok" in empty.text()
        QTest.mouseClick(library.new_button, Qt.LeftButton)
        qt_app.processEvents()
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        assert window._analysis_builder_controller.current_saved_analysis_id is None
    finally:
        window.close()


def test_builder_save_library_open_edit_copy_delete_lifecycle(qt_app, tmp_path):
    window, repo = _window(qt_app, tmp_path)
    try:
        builder, saved_id = _save_chart(window, qt_app)
        assert saved_id is not None and saved_id.startswith("custom-")
        assert builder.save_status.text() == "Analiz kaydedildi."
        assert repo.get_analysis(saved_id) is not None

        library = _open_library(window, qt_app)
        assert len(library.items) == 1
        item = library.items[0]
        assert item.title == "Platform Bazlı Teslimatlar"
        assert item.dataset_title == "Teslimatlar / Kabuller"
        assert item.visualization_title == "Yatay Çubuk"
        assert "acceptances" not in item.dataset_title
        assert "horizontal_bar" not in item.visualization_title

        library.open_analysis(saved_id)
        qt_app.processEvents()
        assert library._preview_widget.findChild(QLabel, "analysisCardTitle") is not None
        assert library.last_preview_analysis_id == saved_id
        assert library.last_result.meta["result_row_count"] == 2

        window._edit_saved_analysis(saved_id)
        qt_app.processEvents()
        edited = window._analysis_builder_widget
        assert edited is not None
        assert edited.screen_title.text() == "Analizi Düzenle"
        assert edited.dataset_combo.currentData() == "acceptances"
        assert edited.visualization_combo.currentData() == "horizontal_bar"
        assert edited.group_combo.currentData() == "platform"
        assert edited.aggregation_combo.currentData() == "count_rows"
        assert edited.controller.current_saved_analysis_id == saved_id
        assert edited.controller.dirty is False
        assert edited.save_button.text() == "Değişiklikleri Kaydet"
        assert edited.save_button.isEnabled() is False

        edited.title_edit.setText("Platform Bazlı Teslimatlar Güncel")
        qt_app.processEvents()
        assert edited.controller.dirty is True
        QTest.mouseClick(edited.save_button, Qt.LeftButton)
        qt_app.processEvents()
        assert edited.controller.current_saved_analysis_id == saved_id
        assert edited.controller.dirty is False
        assert repo.get_analysis(saved_id).title == "Platform Bazlı Teslimatlar Güncel"
        assert len(repo.list_analyses()) == 1

        library = _open_library(window, qt_app)
        library.copy_analysis(saved_id)
        qt_app.processEvents()
        ids = {item.analysis_id for item in library.items}
        assert len(ids) == 2
        assert saved_id in ids
        copied_id = next(item_id for item_id in ids if item_id != saved_id)
        assert repo.get_analysis(copied_id).title == "Platform Bazlı Teslimatlar Güncel Kopya"

        assert library.delete_analysis(copied_id, confirmed=False) is False
        assert len(repo.list_analyses()) == 2
        assert library.delete_analysis(copied_id, confirmed=True) is True
        assert [item.analysis_id for item in repo.list_analyses()] == [saved_id]
    finally:
        window.close()


def test_library_list_refresh_does_not_bulk_execute_saved_analyses(qt_app, tmp_path):
    repo = FileAnalysisRepository(None, tmp_path / "analyses")
    for index in range(100):
        repo.save_analysis(
            AnalysisDefinition(
                analysis_id=f"custom-{index:03d}",
                title=f"Analiz {index:03d}",
                dataset="contracts",
                visualization="kpi",
                measures=[MeasureDefinition("", "count_rows")],
            )
        )
    window, _ = _window(qt_app, tmp_path, repo=repo)
    try:
        calls = 0
        real_execute = window.controller.analysis_service.execute_analysis

        def spy(definition):
            nonlocal calls
            calls += 1
            return real_execute(definition)

        window.controller.analysis_service.execute_analysis = spy
        library = _open_library(window, qt_app)
        library.refresh_items()
        qt_app.processEvents()
        assert len(library.items) == 100
        assert calls == 0
        library.open_analysis(library.items[0].analysis_id)
        qt_app.processEvents()
        assert calls == 1
    finally:
        window.close()


def test_invalid_saved_definition_does_not_crash_library_and_delete_remains_available(qt_app, tmp_path):
    repo = FileAnalysisRepository(None, tmp_path / "analyses")
    repo.save_analysis(
        AnalysisDefinition(
            "custom-invalid", "Stale Analiz", "missing_dataset", "kpi",
            measures=[MeasureDefinition("", "count_rows")],
        )
    )
    window, _ = _window(qt_app, tmp_path, repo=repo)
    try:
        library = _open_library(window, qt_app)
        assert len(library.items) == 1
        assert library.items[0].is_valid is False
        frame = library.list_host.findChild(type(library.list_host), "never")
        copy_buttons = library.findChildren(QPushButton, "analysisLibraryCopyButton")
        assert len(copy_buttons) == 1
        assert copy_buttons[0].isEnabled() is False
        library.open_analysis("custom-invalid")
        assert library._preview_widget.objectName() == "analysisBuilderPreviewError"
        assert library.delete_analysis("custom-invalid", confirmed=True) is True
        assert repo.list_analyses() == []
    finally:
        window.close()


@pytest.mark.parametrize("change_kind", ["title", "filter_value", "sort"])
def test_builder_definition_change_invalidates_success_preview(qt_app, tmp_path, change_kind):
    window, _repo = _window(qt_app, tmp_path)
    try:
        builder = _open_builder(window, qt_app)
        _configure_chart(builder)
        if change_kind == "filter_value":
            QTest.mouseClick(builder.add_filter_button, Qt.LeftButton)
            qt_app.processEvents()
            row = builder._filter_rows[0]
            row.field_combo.setCurrentIndex(row.field_combo.findData("platform"))
            row.operator_combo.setCurrentIndex(row.operator_combo.findData("equals"))
            row.value_edit.setText("AKINCI")
        elif change_kind == "sort":
            builder.sort_combo.setCurrentIndex(builder.sort_combo.findData("value"))
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        assert builder._preview_widget.findChild(QLabel, "analysisCardTitle") is not None

        if change_kind == "title":
            builder.title_edit.setText("Başlık Değişti")
        elif change_kind == "filter_value":
            builder._filter_rows[0].value_edit.setText("TB2")
        else:
            builder.sort_direction_combo.setCurrentIndex(builder.sort_direction_combo.findData("asc"))
        qt_app.processEvents()

        assert builder._preview_widget.objectName() == "analysisBuilderPreviewInfo"
        assert builder._preview_widget.text() == "Analiz ayarları değişti. Tekrar Önizle'ye basın."
        assert builder.controller.dirty is True
    finally:
        window.close()


def test_refresh_preserves_selected_library_and_marks_saved_preview_stale(qt_app, tmp_path):
    window, _repo = _window(qt_app, tmp_path)
    try:
        _builder, saved_id = _save_chart(window, qt_app)
        library = _open_library(window, qt_app)
        library.open_analysis(saved_id)
        qt_app.processEvents()
        assert library._preview_widget.findChild(QLabel, "analysisCardTitle") is not None

        window.refresh_data()
        qt_app.processEvents()
        assert window.current_item_id() == MY_ANALYSES_ID
        refreshed = window._analysis_library_widget
        assert refreshed is not None
        assert refreshed._preview_widget.objectName() == "analysisBuilderPreviewInfo"
        assert refreshed._preview_widget.text() == "Veri yenilendi. Analizi tekrar açın."
    finally:
        window.close()


def test_delete_currently_edited_analysis_resets_builder_session(qt_app, tmp_path):
    window, _repo = _window(qt_app, tmp_path)
    try:
        _builder, saved_id = _save_chart(window, qt_app)
        window._edit_saved_analysis(saved_id)
        assert window._analysis_builder_controller.current_saved_analysis_id == saved_id
        library = _open_library(window, qt_app)
        assert library.delete_analysis(saved_id, confirmed=True) is True
        assert window._analysis_builder_controller.current_saved_analysis_id is None
        assert window._analysis_builder_controller.draft.analysis_id.startswith("preview-")
    finally:
        window.close()


def test_builder_draft_is_preserved_when_navigating_away_and_back(qt_app, tmp_path):
    window, _repo = _window(qt_app, tmp_path)
    try:
        builder = _open_builder(window, qt_app)
        builder.title_edit.setText("Kaydedilmemiş Taslak")
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        draft_id = builder.controller.draft.analysis_id
        window.navigation.setCurrentRow(window._item_ids.index("executive_summary"))
        qt_app.processEvents()
        builder = _open_builder(window, qt_app)
        assert builder.controller.draft.analysis_id == draft_id
        assert builder.title_edit.text() == "Kaydedilmemiş Taslak"
        assert builder.dataset_combo.currentData() == "acceptances"
        assert builder.controller.dirty is True
    finally:
        window.close()


def test_save_copy_delete_only_refresh_local_library_not_sts_source(qt_app, tmp_path):
    window, repo = _window(qt_app, tmp_path)
    try:
        window.controller.refresh_payload = lambda: (_ for _ in ()).throw(AssertionError("unexpected STS reload"))
        builder = _open_builder(window, qt_app)
        _configure_chart(builder)
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id is not None

        library = _open_library(window, qt_app)
        library.copy_analysis(saved_id)
        qt_app.processEvents()
        copied_id = next(item.analysis_id for item in library.items if item.analysis_id != saved_id)
        assert library.delete_analysis(copied_id, confirmed=True) is True
        assert [item.analysis_id for item in repo.list_analyses()] == [saved_id]
    finally:
        window.close()
