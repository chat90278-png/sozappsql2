from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow, _AnalysisChartWidget
from analysis_center.analysis_repository import MemoryAnalysisRepository
from analysis_center.analysis_visual_settings import CHART_PALETTES


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
        analysis_repository=MemoryAnalysisRepository(),
    )
    window.show()
    window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
    qt_app.processEvents()
    return window, window._analysis_builder_widget


def _set_visualization(builder, visualization: str, qt_app) -> None:
    builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData(visualization))
    qt_app.processEvents()


def test_visual_settings_controls_follow_visualization(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.visual_settings_toggle.setChecked(True)
        builder._toggle_visual_settings()
        qt_app.processEvents()
        _set_visualization(builder, "kpi", qt_app)
        assert builder.kpi_settings_host.isVisible() is True
        assert builder.chart_settings_host.isVisible() is False
        assert builder.table_settings_host.isVisible() is False

        _set_visualization(builder, "horizontal_bar", qt_app)
        assert builder.chart_settings_host.isVisible() is True
        assert builder.kpi_settings_host.isVisible() is False
        assert builder.table_settings_host.isVisible() is False

        _set_visualization(builder, "table", qt_app)
        assert builder.table_settings_host.isVisible() is True
        assert builder.chart_settings_host.isVisible() is False
        assert builder.kpi_settings_host.isVisible() is False

        _set_visualization(builder, "line", qt_app)
        assert builder.chart_show_legend.isEnabled() is False
        assert builder.chart_group_others.isEnabled() is False
    finally:
        window.close()


def test_chart_settings_preview_uses_palette_legend_values_and_category_transform(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        _set_visualization(builder, "horizontal_bar", qt_app)
        builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
        builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
        builder.chart_palette.setCurrentIndex(builder.chart_palette.findData("pastel"))
        builder.chart_legend_position.setCurrentIndex(builder.chart_legend_position.findData("bottom"))
        builder.chart_show_legend.setChecked(True)
        builder.chart_show_values.setChecked(True)
        builder.chart_max_categories.setValue(1)
        builder.chart_group_others.setChecked(True)
        qt_app.processEvents()

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        chart = builder._preview_widget.findChild(_AnalysisChartWidget)
        assert chart is not None
        assert chart.visual_settings is not None
        assert chart.legend_visible is True
        assert chart.legend_position == "bottom"
        assert chart.show_values is True
        assert chart.palette == CHART_PALETTES["pastel"]
        assert builder.last_card.data[-1]["label"] == "Diğer"
        assert len(builder.last_card.data) == 2  # max_categories=1 + Other
    finally:
        window.close()


def test_visual_setting_change_marks_dirty_and_invalidates_old_preview(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.last_definition is not None

        builder.chart_palette.setCurrentIndex(builder.chart_palette.findData("green"))
        qt_app.processEvents()

        assert builder.controller.dirty is True
        assert builder.last_definition is None
        assert isinstance(builder._preview_widget, QLabel)
        assert "Tekrar Önizle" in builder._preview_widget.text()
    finally:
        window.close()


def test_kpi_visual_settings_apply_subtitle_prefix_suffix_and_decimal(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        _set_visualization(builder, "kpi", qt_app)
        builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
        builder.kpi_subtitle.setText("Aktif kayıt")
        builder.kpi_prefix.setText("#")
        builder.kpi_suffix.setText(" adet")
        builder.kpi_decimal_places.setValue(1)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        values = builder._preview_widget.findChildren(QLabel, "analysisKpiValue")
        subtitles = builder._preview_widget.findChildren(QLabel, "analysisCardSubtitle")
        assert [item.text() for item in values] == ["#2,0 adet"]
        assert [item.text() for item in subtitles] == ["Aktif kayıt"]
    finally:
        window.close()


def test_table_column_order_buttons_change_preview_header_order(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        _set_visualization(builder, "table", qt_app)
        wanted = ["platform", "name", "status"]
        for index in range(builder.table_fields.count()):
            item = builder.table_fields.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in wanted else Qt.Unchecked)
        qt_app.processEvents()
        assert list(builder.controller.visual_settings().table.column_order) == ["platform", "status", "name"]

        builder.table_column_order.setCurrentRow(2)
        QTest.mouseClick(builder.table_column_up, Qt.LeftButton)
        QTest.mouseClick(builder.table_column_up, Qt.LeftButton)
        qt_app.processEvents()
        assert list(builder.controller.visual_settings().table.column_order) == ["name", "platform", "status"]

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        table = builder._preview_widget.findChild(QTableWidget, "analysisTable")
        assert table is not None
        assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())] == [
            "Ad",
            "Platform",
            "Durum",
        ]
    finally:
        window.close()


def test_saved_visual_settings_hydrate_and_reload_in_builder(qt_app, tmp_path):
    repository = MemoryAnalysisRepository()
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
        analysis_repository=repository,
    )
    window.show()
    try:
        window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
        qt_app.processEvents()
        builder = window._analysis_builder_widget
        builder.chart_palette.setCurrentIndex(builder.chart_palette.findData("warm"))
        builder.chart_legend_position.setCurrentIndex(builder.chart_legend_position.findData("bottom"))
        builder.chart_show_values.setChecked(True)
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id

        saved = window.controller.analysis_service.get_saved_analysis(saved_id)
        builder.controller.reset()
        builder.controller.load_definition(saved)
        builder.refresh_from_draft()
        qt_app.processEvents()

        assert builder.chart_palette.currentData() == "warm"
        assert builder.chart_legend_position.currentData() == "bottom"
        assert builder.chart_show_values.isChecked() is True
        assert builder.controller.dirty is False
    finally:
        window.close()


def test_chart_widget_exposes_hidden_and_right_legend_states(qt_app):
    from analysis_center.analysis_models import ChartType
    from analysis_center.analysis_visual_settings import ChartVisualSettings

    hidden = _AnalysisChartWidget(
        [{"label": "A", "value": 1}],
        ChartType.DONUT,
        visual_settings=ChartVisualSettings(show_legend=False),
    )
    right = _AnalysisChartWidget(
        [{"label": "A", "value": 1}],
        ChartType.BAR,
        visual_settings=ChartVisualSettings(show_legend=True, legend_position="right"),
    )
    try:
        assert hidden.legend_visible is False
        assert right.legend_visible is True
        assert right.legend_position == "right"
    finally:
        hidden.deleteLater()
        right.deleteLater()
