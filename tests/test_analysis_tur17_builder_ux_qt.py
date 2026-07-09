from __future__ import annotations

import copy
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_preview_qt import AnalysisPreviewCardHost
from analysis_center.analysis_qt_window import AnalysisCenterWindow, _AnalysisChartWidget
from analysis_center.analysis_repository import MemoryAnalysisRepository


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _open_builder(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
        analysis_repository=MemoryAnalysisRepository(),
    )
    window.resize(1700, 1000)
    window.show()
    window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
    qt_app.processEvents()
    return window, window._analysis_builder_widget


def test_form_section_order_panel_width_and_visual_settings_are_collapsible(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        assert builder.section_order == (
            "ANALİZ",
            "HESAPLAMA",
            "FİLTRELER",
            "SIRALAMA / LİMİT",
            "GÖRÜNÜM",
            "GÖRÜNÜM AYARLARI",
        )
        scroll = builder.findChild(QScrollArea, "analysisBuilderFormScroll")
        assert scroll.minimumWidth() == 400
        assert scroll.maximumWidth() == 460
        assert builder.visual_settings_content.isVisible() is False

        QTest.mouseClick(builder.visual_settings_toggle, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.visual_settings_content.isVisible() is True
        assert "Gizle" in builder.visual_settings_toggle.text()
        QTest.mouseClick(builder.visual_settings_toggle, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.visual_settings_content.isVisible() is False
    finally:
        window.close()


def test_components_group_combo_hides_id_and_uses_semantic_default(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("components"))
        qt_app.processEvents()
        ids = [builder.group_combo.itemData(index) for index in range(builder.group_combo.count())]
        assert "id" not in ids
        assert builder.group_combo.currentData() == "unit"
        assert builder.group_combo.currentText() == "Birim"
    finally:
        window.close()


def test_preview_card_is_bounded_and_donut_does_not_fill_giant_host(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("donut"))
        builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        wrapper = builder._preview_widget
        assert isinstance(wrapper, AnalysisPreviewCardHost)
        chart = wrapper.findChild(_AnalysisChartWidget)
        assert chart is not None
        assert wrapper.preview_maximum_size.width() == 760
        assert wrapper.preview_maximum_size.height() == 460
        assert chart.width() <= 760
        assert chart.height() <= 460
        assert builder.preview_host.height() >= chart.height()
    finally:
        window.close()


def test_high_cardinality_donut_shows_guidance_without_mutating_result(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.controller.service.data["components"] = [
            {"id": index, "name": f"Bileşen {index}", "version": "1", "unit": f"Birim {index}", "active": True}
            for index in range(14)
        ]
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("components"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("donut"))
        builder.group_combo.setCurrentIndex(builder.group_combo.findData("unit"))
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()

        assert len(builder.last_result.rows) == 14
        before = copy.deepcopy(builder.last_result.rows)
        assert builder.preview_guidance.isVisible() is True
        assert "Yatay çubuk" in builder.preview_guidance.text()
        assert builder.last_result.rows == before
    finally:
        window.close()


def test_count_kpi_preview_uses_integer_default_and_explicit_decimal_is_preserved(qt_app, tmp_path):
    window, builder = _open_builder(qt_app, tmp_path)
    try:
        builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("components"))
        builder.visualization_combo.setCurrentIndex(builder.visualization_combo.findData("kpi"))
        builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
        qt_app.processEvents()
        assert builder.kpi_decimal_places.value() == 0

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        value = builder._preview_widget.findChild(type(builder.screen_title), "analysisKpiValue")
        assert value is not None
        assert ",00" not in value.text()

        builder.visual_settings_toggle.setChecked(True)
        builder._toggle_visual_settings()
        builder.kpi_decimal_places.setValue(1)
        qt_app.processEvents()
        builder.aggregation_combo.setCurrentIndex(builder.aggregation_combo.findData("count_rows"))
        assert builder.kpi_decimal_places.value() == 1
    finally:
        window.close()
