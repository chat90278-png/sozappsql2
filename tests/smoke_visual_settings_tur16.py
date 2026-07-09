from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow, _AnalysisChartWidget
from analysis_center.analysis_repository import FileAnalysisRepository
from analysis_center.analysis_visual_settings import AnalysisVisualSettings, CHART_PALETTES


ROOT = Path(__file__).resolve().parents[1]
STS_PATH = ROOT / "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"


def choose(combo, value) -> None:
    index = combo.findData(value)
    assert index >= 0, f"combo value not found: {value!r}"
    combo.setCurrentIndex(index)


def open_builder(window: AnalysisCenterWindow, app: QApplication):
    window.navigation.setCurrentRow(window._item_ids.index(ANALYSIS_BUILDER_ID))
    app.processEvents()
    assert window._analysis_builder_widget is not None
    return window._analysis_builder_widget


def open_library(window: AnalysisCenterWindow, app: QApplication):
    window.navigation.setCurrentRow(window._item_ids.index(MY_ANALYSES_ID))
    app.processEvents()
    assert window._analysis_library_widget is not None
    return window._analysis_library_widget


def open_dashboard(window: AnalysisCenterWindow, app: QApplication):
    window.navigation.setCurrentRow(window._item_ids.index(CUSTOM_DASHBOARD_ID))
    app.processEvents()
    return window._dashboard_canvas


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
    )

    with TemporaryDirectory(prefix="tur16-visual-settings-") as temp_dir:
        root = Path(temp_dir)
        analyses_root = root / "analyses"
        dashboard_root = root / "dashboards"
        repository = FileAnalysisRepository(STS_PATH, root=analyses_root)
        workspace_store = DashboardWorkspaceStore(dashboard_root)
        window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=workspace_store,
            analysis_repository=repository,
        )
        window.show()
        app.processEvents()

        print(f"source={STS_PATH.name}")
        print(f"repository_path={repository.repository_path()}")
        print(f"workspace_path={workspace_store.workspace_path(STS_PATH)}")

        builder = open_builder(window, app)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Pastel Platform Analizi")
        choose(builder.chart_palette, "pastel")
        choose(builder.chart_legend_position, "bottom")
        builder.chart_show_legend.setChecked(True)
        builder.chart_show_values.setChecked(True)
        builder.chart_max_categories.setValue(1)
        builder.chart_group_others.setChecked(True)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        chart = builder._preview_widget.findChild(_AnalysisChartWidget)
        assert chart is not None
        assert chart.palette == CHART_PALETTES["pastel"]
        assert chart.legend_position == "bottom"
        assert chart.show_values is True
        assert builder.last_card.meta["visual_settings"].chart.max_categories == 1
        print(
            "chart_preview="
            f"palette=pastel,legend=bottom,show_values={chart.show_values},"
            f"max_categories=1,render_rows={len(builder.last_card.data)}"
        )

        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        chart_id = builder.controller.current_saved_analysis_id
        assert chart_id and chart_id.startswith("custom-")
        saved = repository.get_analysis(chart_id)
        saved_visual = AnalysisVisualSettings.from_options(saved.options, strict=True)
        assert saved_visual.chart.palette == "pastel"
        print(f"saved_chart_id={chart_id}")

        library = open_library(window, app)
        library.open_analysis(chart_id)
        app.processEvents()
        library_chart = library._preview_widget.findChild(_AnalysisChartWidget)
        assert library_chart is not None
        assert library_chart.palette == CHART_PALETTES["pastel"]
        assert library_chart.legend_position == "bottom"
        print("library_preview_settings=PASS")

        assert library.toggle_dashboard(chart_id) is True
        app.processEvents()
        canvas = open_dashboard(window, app)
        placement = window.workspace.placement_for_source(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, chart_id)
        assert placement is not None
        placement_id = placement.placement_id
        dashboard_chart = canvas._frames[placement_id].content.findChild(_AnalysisChartWidget)
        assert dashboard_chart is not None
        assert dashboard_chart.palette == CHART_PALETTES["pastel"]
        assert dashboard_chart.legend_position == "bottom"
        print(f"dashboard_visual=placement_id={placement_id},palette=pastel")

        window._edit_saved_analysis(chart_id)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder.controller.current_saved_analysis_id == chart_id
        choose(builder.chart_palette, "monochrome")
        builder.chart_show_legend.setChecked(False)
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        assert builder.controller.current_saved_analysis_id == chart_id

        canvas = open_dashboard(window, app)
        same_placement = window.workspace.placement_for_source(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, chart_id)
        assert same_placement.placement_id == placement_id
        updated_chart = canvas._frames[placement_id].content.findChild(_AnalysisChartWidget)
        assert updated_chart.palette == CHART_PALETTES["monochrome"]
        assert updated_chart.legend_visible is False
        print("dashboard_same_id_update=palette=monochrome,legend_hidden=True")

        window.close()
        app.processEvents()
        reloaded_repository = FileAnalysisRepository(STS_PATH, root=analyses_root)
        reloaded = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=DashboardWorkspaceStore(dashboard_root),
            analysis_repository=reloaded_repository,
        )
        reloaded.show()
        app.processEvents()
        reloaded_definition = reloaded_repository.get_analysis(chart_id)
        reloaded_visual = AnalysisVisualSettings.from_options(reloaded_definition.options, strict=True)
        assert reloaded_visual.chart.palette == "monochrome"
        canvas = open_dashboard(reloaded, app)
        reloaded_placement = reloaded.workspace.placement_for_source(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, chart_id)
        assert reloaded_placement.placement_id == placement_id
        reloaded_chart = canvas._frames[placement_id].content.findChild(_AnalysisChartWidget)
        assert reloaded_chart.palette == CHART_PALETTES["monochrome"]
        print("restart_visual_settings=PASS")

        builder = open_builder(reloaded, app)
        QTest.mouseClick(builder.reset_button, Qt.LeftButton)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "kpi")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("KPI Format")
        builder.kpi_subtitle.setText("Teslimat sayısı")
        builder.kpi_prefix.setText("#")
        builder.kpi_suffix.setText(" adet")
        builder.kpi_decimal_places.setValue(1)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        kpi_values = builder._preview_widget.findChildren(QLabel, "analysisKpiValue")
        kpi_subtitles = builder._preview_widget.findChildren(QLabel, "analysisCardSubtitle")
        assert [label.text() for label in kpi_values] == ["#2,0 adet"]
        assert [label.text() for label in kpi_subtitles] == ["Teslimat sayısı"]
        print(f"kpi_render={kpi_values[0].text()},subtitle={kpi_subtitles[0].text()}")

        QTest.mouseClick(builder.reset_button, Qt.LeftButton)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "table")
        builder.title_edit.setText("Kolon Sıralı Tablo")
        selected = ["platform", "name", "status"]
        for index in range(builder.table_fields.count()):
            item = builder.table_fields.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in selected else Qt.Unchecked)
        app.processEvents()
        status_row = next(
            index
            for index in range(builder.table_column_order.count())
            if builder.table_column_order.item(index).data(Qt.UserRole) == "status"
        )
        builder.table_column_order.setCurrentRow(status_row)
        for _ in range(status_row):
            QTest.mouseClick(builder.table_column_up, Qt.LeftButton)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        table = builder._preview_widget.findChild(QTableWidget, "analysisTable")
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        assert headers == ["Durum", "Platform", "Ad"]
        print(f"table_column_order={headers}")

        prepared_item = reloaded._dashboard_items[0]
        prepared_card = prepared_item.cards[0]
        assert not prepared_card.meta.get("visual_settings_enabled", False)
        reloaded.navigation.setCurrentRow(reloaded._item_ids.index(prepared_item.item_id))
        app.processEvents()
        prepared_charts = reloaded.stack.currentWidget().findChildren(_AnalysisChartWidget)
        assert all(widget.visual_settings is None for widget in prepared_charts)
        print(f"prepared_legacy_branch=PASS,chart_widgets={len(prepared_charts)}")
        print("human_visual_qa=NOT_PERFORMED_OFFSCREEN")
        reloaded.close()
        app.processEvents()

    print("TUR 16 VISUAL SETTINGS SMOKE: PASS")


if __name__ == "__main__":
    main()
