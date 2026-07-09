from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_builder_qt import AnalysisFilterRowWidget
from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _open_builder(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
    )
    window.show()
    row = window._item_ids.index(ANALYSIS_BUILDER_ID)
    window.navigation.setCurrentRow(row)
    qt_app.processEvents()
    assert window._analysis_builder_widget is not None
    return window, window._analysis_builder_widget


def test_analysis_builder_navigation_and_registry_dataset_options(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        assert window.navigation.item(window._item_ids.index(ANALYSIS_BUILDER_ID)).text() == "Analiz Oluştur"
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        assert window.stack.currentWidget() is builder
        assert [builder.dataset_combo.itemData(i) for i in range(builder.dataset_combo.count())] == [
            item.dataset_id for item in builder.controller.registry.list_datasets()
        ]
        assert [builder.dataset_combo.itemText(i) for i in range(builder.dataset_combo.count())] == [
            item.title for item in builder.controller.registry.list_datasets()
        ]
    finally:
        window.close()


def test_dataset_change_refreshes_field_controls_from_registry(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        acceptances_index = builder.dataset_combo.findData("acceptances")
        builder.dataset_combo.setCurrentIndex(acceptances_index)
        qt_app.processEvents()

        group_ids = {builder.group_combo.itemData(i) for i in range(builder.group_combo.count())}
        measure_ids = {builder.measure_combo.itemData(i) for i in range(builder.measure_combo.count())}
        table_ids = {
            builder.table_fields.item(i).data(Qt.UserRole)
            for i in range(builder.table_fields.count())
        }
        assert "platform" in group_ids
        assert "planned_total" in table_ids
        assert "delivered_total" in table_ids
        assert "planned_total" not in measure_ids  # count_rows is the current aggregation

        sum_index = builder.aggregation_combo.findData("sum")
        builder.aggregation_combo.setCurrentIndex(sum_index)
        qt_app.processEvents()
        measure_ids = {builder.measure_combo.itemData(i) for i in range(builder.measure_combo.count())}
        assert "planned_total" in measure_ids
        assert "delivered_total" in measure_ids
        assert "name" not in measure_ids
    finally:
        window.close()


def test_visualization_mode_updates_visible_controls(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("kpi"))
        qt_app.processEvents()
        assert builder.group_combo.isVisible() is False
        assert builder.aggregation_combo.isVisible() is True
        assert builder.table_fields.isVisible() is False
        assert builder.limit_combo.isVisible() is False

        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("bar"))
        qt_app.processEvents()
        assert builder.group_combo.isVisible() is True
        assert builder.aggregation_combo.isVisible() is True
        assert builder.table_fields.isVisible() is False
        assert builder.limit_combo.isVisible() is True

        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("table"))
        qt_app.processEvents()
        assert builder.group_combo.isVisible() is False
        assert builder.aggregation_combo.isVisible() is False
        assert builder.table_fields.isVisible() is True
        assert builder.limit_combo.isVisible() is True
    finally:
        window.close()


def test_filter_row_add_remove_and_operator_options_follow_field_type(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        QTest.mouseClick(builder.add_filter_button, Qt.LeftButton)
        qt_app.processEvents()
        assert len(builder._filter_rows) == 1
        row = builder._filter_rows[0]
        assert isinstance(row, AnalysisFilterRowWidget)

        row.field_combo.setCurrentIndex(row.field_combo.findData("planned_total"))
        qt_app.processEvents()
        operator_ids = {
            row.operator_combo.itemData(i) for i in range(row.operator_combo.count())
        }
        assert "between" in operator_ids
        assert "greater_than" in operator_ids
        assert "contains" not in operator_ids

        remove = row.findChild(QPushButton, "analysisBuilderFilterRemove")
        assert remove is not None
        QTest.mouseClick(remove, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.controller.draft.filters == []
        assert builder._filter_rows == []
    finally:
        window.close()


def test_preview_click_uses_real_engine_and_existing_card_renderer(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("horizontal_bar"))
        builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
        builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
        builder.title_edit.setText("Platform Bazlı Teslimatlar")
        qt_app.processEvents()

        # Preview must use normalized in-memory data. A reload here is a regression.
        builder.controller.service.refresh_data = lambda: (_ for _ in ()).throw(AssertionError("unexpected source reload"))
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        assert builder._preview_widget is not None
        assert builder._preview_widget.findChild(QLabel, "analysisCardTitle") is not None
        titles = builder._preview_widget.findChildren(QLabel, "analysisCardTitle")
        assert [label.text() for label in titles] == ["Platform Bazlı Teslimatlar"]
        assert builder.last_definition is not None
        assert builder.last_result is not None
        assert builder.last_card is not None
        assert builder.last_definition.analysis_id == builder.controller.draft.analysis_id
        assert builder.last_result.meta["result_row_count"] == 2
    finally:
        window.close()


def test_invalid_form_shows_user_message_without_crash(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("bar"))
        builder.group_combo.setCurrentIndex(builder.group_combo.findData(""))
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        assert builder._preview_widget is not None
        assert builder._preview_widget.objectName() == "analysisBuilderPreviewError"
        assert "gruplama alanı" in builder._preview_widget.text()
        assert "Traceback" not in builder._preview_widget.text()
    finally:
        window.close()


def test_table_preview_selected_fields_sort_and_limit(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("table"))
        wanted = {"platform", "name", "planned_total"}
        for index in range(builder.table_fields.count()):
            item = builder.table_fields.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in wanted else Qt.Unchecked)
        qt_app.processEvents()
        builder.sort_combo.setCurrentIndex(builder.sort_combo.findData("planned_total"))
        builder.sort_direction_combo.setCurrentIndex(builder.sort_direction_combo.findData("desc"))
        builder.limit_combo.setCurrentIndex(builder.limit_combo.findData(5))
        builder.title_edit.setText("Teslimat Tablosu")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        assert builder._preview_widget is not None
        assert builder._preview_widget.findChild(QLabel, "analysisCardTitle") is not None
        definition = builder.controller.build_definition()
        assert definition.select_fields == [
            field.field_id
            for field in builder.controller.table_fields()
            if field.field_id in wanted
        ]
        assert definition.sort[0].field == "planned_total"
        assert definition.limit == 5
    finally:
        window.close()


def test_refresh_preserves_builder_screen_and_draft_but_clears_stale_preview(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("kpi"))
        builder.title_edit.setText("Yenileme Sonrası Analiz")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        assert builder._preview_widget.findChild(QLabel, "analysisCardTitle") is not None
        draft_id = builder.controller.draft.analysis_id

        window.refresh_data()
        qt_app.processEvents()

        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        refreshed = window._analysis_builder_widget
        assert refreshed is not None
        assert refreshed.controller.draft.analysis_id == draft_id
        assert refreshed.title_edit.text() == "Yenileme Sonrası Analiz"
        assert refreshed.dataset_combo.currentData() == "acceptances"
        assert refreshed.visualization_combo.currentData() == "kpi"
        assert refreshed._preview_widget.objectName() == "analysisBuilderPreviewInfo"
        assert refreshed._preview_widget.text() == "Veri yenilendi. Analizi tekrar önizleyin."
    finally:
        window.close()
