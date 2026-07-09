from __future__ import annotations

import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QFrame, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement
from analysis_center.analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspace,
    DashboardWorkspaceStore,
    source_workspace_key,
)
from analysis_center.analysis_models import CardLayoutHints, VisualSettings
from analysis_center.analysis_preview_qt import AnalysisPreviewCardHost
from analysis_center.analysis_qt_window import AnalysisCenterWindow, _AnalysisChartWidget
from analysis_center.analysis_repository import FileAnalysisRepository


ROOT = Path(__file__).resolve().parents[1]
STS_PATH = ROOT / "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"
REMOVED_CARD_ID = "contract_unlabeled_table"


def choose(combo, value: object) -> None:
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


def dashboard_button(library, analysis_id: str) -> QPushButton:
    for frame in library.findChildren(QFrame, "analysisLibraryItem"):
        if frame.property("analysisId") == analysis_id:
            button = frame.findChild(QPushButton, "analysisLibraryDashboardButton")
            assert button is not None
            return button
    raise AssertionError(f"library item not found: {analysis_id}")


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
    )

    with TemporaryDirectory(prefix="tur17-builder-ux-") as temp_dir:
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
        window.resize(1700, 1000)
        window.show()
        app.processEvents()

        print(f"source={STS_PATH.name}")
        print(f"repository_path={repository.repository_path()}")
        print(f"workspace_path={workspace_store.workspace_path(STS_PATH)}")

        builder = open_builder(window, app)
        choose(builder.dataset_combo, "components")
        app.processEvents()
        group_ids = [builder.group_combo.itemData(i) for i in range(builder.group_combo.count())]
        assert "id" not in group_ids
        assert builder.group_combo.currentData() != "id"
        assert builder.group_combo.currentData() == "unit"
        print(
            "semantic_group="
            f"dataset=components,default={builder.group_combo.currentData()},"
            f"label={builder.group_combo.currentText()},technical_id_visible={'id' in group_ids}"
        )

        choose(builder.visualization_combo, "donut")
        choose(builder.group_combo, "unit")
        choose(builder.aggregation_combo, "count_rows")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        wrapper = builder._preview_widget
        assert isinstance(wrapper, AnalysisPreviewCardHost)
        chart = wrapper.findChild(_AnalysisChartWidget)
        assert chart is not None
        assert chart.width() <= 760 and chart.height() <= 460
        print(
            "bounded_preview="
            f"host={builder.preview_host.width()}x{builder.preview_host.height()},"
            f"chart={chart.width()}x{chart.height()},max=760x460"
        )

        assert builder.visual_settings_content.isVisible() is False
        QTest.mouseClick(builder.visual_settings_toggle, Qt.LeftButton)
        app.processEvents()
        assert builder.visual_settings_content.isVisible() is True
        choose(builder.chart_palette, "pastel")
        choose(builder.chart_legend_position, "bottom")
        app.processEvents()
        assert builder.last_definition is None
        stale_text = builder._preview_widget.text() if isinstance(builder._preview_widget, QLabel) else ""
        assert "Tekrar Önizle" in stale_text
        QTest.mouseClick(builder.visual_settings_toggle, Qt.LeftButton)
        app.processEvents()
        assert builder.visual_settings_content.isVisible() is False
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        chart = builder._preview_widget.findChild(_AnalysisChartWidget)
        assert chart is not None and chart.legend_position == "bottom"
        print("visual_settings=collapse_expand_PASS,palette=pastel,legend=bottom,stale_preview=PASS")

        QTest.mouseClick(builder.reset_button, Qt.LeftButton)
        choose(builder.dataset_combo, "components")
        choose(builder.visualization_combo, "kpi")
        choose(builder.aggregation_combo, "count_rows")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        kpi_value = builder._preview_widget.findChild(QLabel, "analysisKpiValue")
        assert kpi_value is not None
        assert ",00" not in kpi_value.text()
        assert ".00" not in kpi_value.text()
        print(f"count_kpi={kpi_value.text()},integer_default=True")

        # Guard-path verification uses real STS-loaded service data but only augments the
        # in-memory normalized components dataset. The STS source file is never mutated.
        builder.controller.service.data["components"] = [
            {
                "id": index,
                "name": f"Bileşen {index}",
                "version": "1",
                "unit": f"Birim {index}",
                "active": True,
            }
            for index in range(14)
        ]
        QTest.mouseClick(builder.reset_button, Qt.LeftButton)
        choose(builder.dataset_combo, "components")
        choose(builder.visualization_combo, "donut")
        choose(builder.group_combo, "unit")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        raw_rows = copy.deepcopy(builder.last_result.rows)
        assert len(raw_rows) == 14
        assert builder.preview_guidance.isVisible()
        assert "Yatay çubuk" in builder.preview_guidance.text()
        assert builder.last_result.rows == raw_rows
        print(
            "donut_guard="
            f"categories={len(raw_rows)},warning={builder.preview_guidance.text()!r},"
            "source_mutated=False,in_memory_guard_fixture=True"
        )

        contract_screen_id = next(
            item.item_id for item in window._dashboard_items if item.title == "Sözleşme Analizi"
        )
        window.navigation.setCurrentRow(window._item_ids.index(contract_screen_id))
        app.processEvents()
        card_titles = [
            label.text()
            for label in window.stack.currentWidget().findChildren(QLabel, "analysisCardTitle")
        ]
        assert "Etiketsiz Kayıtlar" not in card_titles
        assert all(card.card_id != REMOVED_CARD_ID for item in window._dashboard_items for card in item.cards)
        print(f"contract_cleanup=removed_title_present={('Etiketsiz Kayıtlar' in card_titles)}")

        # Existing Tur 14–16 custom save/library/dashboard flow remains operational.
        builder = open_builder(window, app)
        QTest.mouseClick(builder.reset_button, Qt.LeftButton)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Tur 17 Teslimat Analizi")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        custom_id = builder.controller.current_saved_analysis_id
        assert custom_id and custom_id.startswith("custom-")
        library = open_library(window, app)
        button = dashboard_button(library, custom_id)
        assert button.text() == "+ Dashboard"
        QTest.mouseClick(button, Qt.LeftButton)
        app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, custom_id)
        canvas = open_dashboard(window, app)
        custom_placement = window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            custom_id,
        )
        assert custom_placement is not None
        assert canvas is not None and custom_placement.placement_id in canvas._frames
        print(
            "custom_lifecycle="
            f"saved_id={custom_id},library=PASS,dashboard_placement={custom_placement.placement_id}"
        )

        # Build a real old-workspace fixture containing the removed prepared card.
        prepared_card = next(
            card
            for item in window._dashboard_items
            if item.item_id == contract_screen_id
            for card in item.cards
        )
        orphan_root = root / "orphan-dashboards"
        orphan_store = DashboardWorkspaceStore(orphan_root)
        old_workspace = DashboardWorkspace(source_key=source_workspace_key(STS_PATH))
        assert old_workspace.pin(prepared_card)
        valid_before = old_workspace.placement_for_source(prepared_card.screen_id, prepared_card.card_id)
        assert valid_before is not None
        valid_signature = (
            valid_before.placement_id,
            valid_before.x,
            valid_before.y,
            valid_before.w,
            valid_before.h,
        )
        old_workspace.add_placement(
            DashboardCardPlacement(
                placement_id="legacy-unlabeled",
                source_screen_id="contract_analysis",
                card_id=REMOVED_CARD_ID,
                x=0,
                y=8,
                w=12,
                h=5,
            ),
            layout_hints=CardLayoutHints(min_w=1, min_h=1, default_w=12, default_h=5),
        )
        orphan_store.save(STS_PATH, old_workspace)
        assert old_workspace.contains("contract_analysis", REMOVED_CARD_ID)

        orphan_window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=orphan_store,
            analysis_repository=FileAnalysisRepository(STS_PATH, root=root / "orphan-analyses"),
        )
        orphan_window.show()
        app.processEvents()
        assert not orphan_window.workspace.contains("contract_analysis", REMOVED_CARD_ID)
        valid_after = orphan_window.workspace.placement_for_source(
            prepared_card.screen_id,
            prepared_card.card_id,
        )
        assert valid_after is not None
        assert (
            valid_after.placement_id,
            valid_after.x,
            valid_after.y,
            valid_after.w,
            valid_after.h,
        ) == valid_signature
        orphan_canvas = open_dashboard(orphan_window, app)
        assert orphan_canvas is not None
        print(
            "orphan_cleanup="
            f"removed={REMOVED_CARD_ID},valid_card={prepared_card.card_id},"
            f"valid_geometry={valid_signature[1:]},other_placement_preserved=True"
        )

        print("human_visual_qa=NOT_PERFORMED_OFFSCREEN")
        print("offscreen_verification=Qt state + widget geometry + renderer branches")
        orphan_window.close()
        window.close()
        app.processEvents()

    print("TUR 17 BUILDER UX CLEANUP SMOKE: PASS")


if __name__ == "__main__":
    main()
