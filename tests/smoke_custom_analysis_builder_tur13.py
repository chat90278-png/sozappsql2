from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import CardType, VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


ROOT = Path(__file__).resolve().parents[1]
STS_PATH = ROOT / "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"


def choose(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0, f"combo value not found: {value}"
    combo.setCurrentIndex(index)


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
    )

    with TemporaryDirectory(prefix="tur13-dashboard-") as temp_dir:
        window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=DashboardWorkspaceStore(Path(temp_dir) / "dashboards"),
        )
        window.show()
        app.processEvents()
        print(f"source={STS_PATH.name}")
        print(f"status={window.status_text.text()}")

        nav_titles = [window.navigation.item(i).text() for i in range(window.navigation.count())]
        print(f"navigation={nav_titles}")
        assert "Analiz Oluştur" in nav_titles

        builder_row = window._item_ids.index(ANALYSIS_BUILDER_ID)
        window.navigation.setCurrentRow(builder_row)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder is not None
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        print("builder_screen=open")

        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Platform Bazlı Teslimatlar")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()

        assert builder.last_definition is not None
        assert builder.last_result is not None
        assert builder.last_card is not None
        assert builder.last_card.card_type == CardType.CHART
        assert builder.last_result.meta["source_row_count"] == 2
        assert builder.last_result.meta["filtered_row_count"] == 2
        assert builder.last_result.meta["result_row_count"] == 1
        assert builder.findChild(QPushButton, "analysisPinButton") is None
        print(
            "chart_preview="
            f"dataset={builder.last_definition.dataset},"
            f"group={builder.last_definition.dimensions[0]},"
            f"aggregation={builder.last_definition.measures[0].aggregation},"
            f"filtered={builder.last_result.meta['filtered_row_count']},"
            f"rows={builder.last_result.meta['result_row_count']}"
        )

        QTest.mouseClick(builder.add_filter_button, Qt.LeftButton)
        app.processEvents()
        filter_row = builder._filter_rows[0]
        choose(filter_row.field_combo, "platform")
        choose(filter_row.operator_combo, "equals")
        filter_row.value_edit.setText("AKINCI")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        assert builder.last_result.meta["filtered_row_count"] == 0
        assert builder.last_result.meta["result_row_count"] == 0
        print(
            "filtered_chart="
            "field=platform,operator=equals,value=AKINCI,"
            f"filtered={builder.last_result.meta['filtered_row_count']},"
            f"rows={builder.last_result.meta['result_row_count']}"
        )

        filter_row.value_edit.setText("SİVRİSİNEK")
        choose(builder.visualization_combo, "kpi")
        choose(builder.aggregation_combo, "count_rows")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_card is not None and builder.last_card.card_type == CardType.KPI
        assert builder.last_result is not None and builder.last_result.value == 2
        print(
            "kpi_preview="
            f"aggregation={builder.last_definition.measures[0].aggregation},"
            f"value={builder.last_result.value},"
            f"filtered={builder.last_result.meta['filtered_row_count']}"
        )

        choose(builder.visualization_combo, "table")
        selected_fields = {"platform", "name", "status", "planned_total"}
        for index in range(builder.table_fields.count()):
            item = builder.table_fields.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in selected_fields else Qt.Unchecked)
        app.processEvents()
        choose(builder.sort_combo, "planned_total")
        choose(builder.sort_direction_combo, "desc")
        choose(builder.limit_combo, 5)
        builder.title_edit.setText("Teslimat Detayı")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_card is not None and builder.last_card.card_type == CardType.TABLE
        assert builder.last_result is not None
        expected_columns = [
            builder.table_fields.item(index).data(Qt.UserRole)
            for index in range(builder.table_fields.count())
            if builder.table_fields.item(index).checkState() == Qt.Checked
        ]
        assert builder.last_result.columns == expected_columns
        assert set(builder.last_result.columns) == selected_fields
        assert builder.last_result.meta["result_row_count"] == 2
        assert builder.last_definition is not None
        assert builder.last_definition.sort[0].field == "planned_total"
        assert builder.last_definition.limit == 5
        print(
            "table_preview="
            f"fields={builder.last_result.columns},"
            f"sort={builder.last_definition.sort[0].field}:{builder.last_definition.sort[0].direction},"
            f"limit={builder.last_definition.limit},"
            f"rows={builder.last_result.meta['result_row_count']}"
        )

        choose(builder.visualization_combo, "kpi")
        choose(builder.aggregation_combo, "sum")
        measure_ids = {builder.measure_combo.itemData(i) for i in range(builder.measure_combo.count())}
        assert "name" not in measure_ids
        assert "planned_total" in measure_ids
        print(f"sum_measure_options={sorted(str(item) for item in measure_ids if item)}")

        choose(builder.aggregation_combo, "count_rows")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        draft_id = builder.controller.draft.analysis_id
        draft_signature = (
            builder.controller.draft.title,
            builder.controller.draft.dataset_id,
            builder.controller.draft.visualization,
            len(builder.controller.draft.filters),
        )
        window.refresh_data()
        app.processEvents()
        refreshed = window._analysis_builder_widget
        assert refreshed is not None
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        assert refreshed.controller.draft.analysis_id == draft_id
        assert (
            refreshed.controller.draft.title,
            refreshed.controller.draft.dataset_id,
            refreshed.controller.draft.visualization,
            len(refreshed.controller.draft.filters),
        ) == draft_signature
        assert refreshed.last_result is None
        assert refreshed._preview_widget.text() == "Veri yenilendi. Analizi tekrar önizleyin."
        print(
            "refresh="
            f"screen={window.current_item_id()},draft_id={draft_id},"
            "preview=stale-cleared"
        )

        dashboard_row = window._item_ids.index(CUSTOM_DASHBOARD_ID)
        window.navigation.setCurrentRow(dashboard_row)
        app.processEvents()
        assert window.current_item_id() == CUSTOM_DASHBOARD_ID
        prepared_row = window._item_ids.index("executive_summary")
        window.navigation.setCurrentRow(prepared_row)
        app.processEvents()
        assert window.current_item_id() == "executive_summary"
        print("existing_screens=dashboard:PASS,executive_summary:PASS")

        window.close()
        app.processEvents()

    print("TUR 13 CUSTOM ANALYSIS BUILDER SMOKE: PASS")


if __name__ == "__main__":
    main()
