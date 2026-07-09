from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow, _AnalysisChartWidget
from analysis_center.analysis_repository import FileAnalysisRepository
from analysis_center.analysis_visual_settings import CHART_PALETTES


ROOT = Path(__file__).resolve().parents[1]
STS_PATH = ROOT / "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"


def choose(combo, value) -> None:
    index = combo.findData(value)
    assert index >= 0, f"combo value not found: {value!r}"
    combo.setCurrentIndex(index)


def open_screen(window: AnalysisCenterWindow, app: QApplication, screen_id: str):
    window.navigation.setCurrentRow(window._item_ids.index(screen_id))
    app.processEvents()
    return window.stack.currentWidget()


def open_builder(window: AnalysisCenterWindow, app: QApplication):
    open_screen(window, app, ANALYSIS_BUILDER_ID)
    assert window._analysis_builder_widget is not None
    return window._analysis_builder_widget


def open_dashboard(window: AnalysisCenterWindow, app: QApplication):
    open_screen(window, app, CUSTOM_DASHBOARD_ID)
    assert window._dashboard_canvas is not None
    return window._dashboard_canvas


def custom_frame(window: AnalysisCenterWindow, app: QApplication, analysis_id: str):
    canvas = open_dashboard(window, app)
    placement = window.workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        analysis_id,
    )
    assert placement is not None
    return placement, canvas._frames[placement.placement_id]


def signature(window: AnalysisCenterWindow, source_id: str, card_id: str):
    placement = window.workspace.placement_for_source(source_id, card_id)
    assert placement is not None
    return (
        placement.placement_id,
        placement.x,
        placement.y,
        placement.w,
        placement.h,
    )


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
    )

    with TemporaryDirectory(prefix="tur19-dashboard-quick-edit-") as temp_dir:
        root = Path(temp_dir)
        analyses_root = root / "analyses"
        dashboard_root = root / "dashboards"
        repository = FileAnalysisRepository(STS_PATH, analyses_root)
        workspace_store = DashboardWorkspaceStore(dashboard_root)
        window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=workspace_store,
            analysis_repository=repository,
        )
        window.resize(1360, 860)
        window.show()
        app.processEvents()

        print(f"source={STS_PATH.name}")
        print(f"repository_path={repository.repository_path()}")
        print(f"workspace_path={workspace_store.workspace_path(STS_PATH)}")

        prepared_item = next(
            item for item in window._dashboard_items if item.item_id == "executive_summary"
        )
        prepared_card = next(card for card in prepared_item.cards if card.enabled)
        window._toggle_dashboard_card(prepared_card)
        prepared_before = signature(window, prepared_item.item_id, prepared_card.card_id)
        print(f"prepared_card={prepared_item.item_id}:{prepared_card.card_id}")

        builder = open_builder(window, app)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Dashboard Hızlı Düzenleme")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        initial_result_rows = builder.last_result.meta["result_row_count"]
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        analysis_id = builder.controller.current_saved_analysis_id
        assert analysis_id and analysis_id.startswith("custom-")
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id)
        placement_before = signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            analysis_id,
        )
        print(
            f"custom_created={analysis_id},initial_result_rows={initial_result_rows},"
            f"placement={placement_before}"
        )

        refresh_calls = 0
        real_refresh = window.controller.refresh_payload

        def spy_refresh():
            nonlocal refresh_calls
            refresh_calls += 1
            return real_refresh()

        window.controller.refresh_payload = spy_refresh

        canvas = open_dashboard(window, app)
        custom_placement = window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            analysis_id,
        )
        custom_card_frame = canvas._frames[custom_placement.placement_id]
        prepared_frame = canvas._frames[prepared_before[0]]
        assert custom_card_frame.quick_button.isVisible() is True
        assert prepared_frame.quick_button.isVisible() is False
        print("quick_menu_visibility=custom:VISIBLE,prepared:HIDDEN")

        custom_card_frame.quick_menu.actions()[0].trigger()
        app.processEvents()
        builder = window._analysis_builder_widget
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        assert builder.controller.current_saved_analysis_id == analysis_id
        first_acceptance = window.controller.analysis_service.data["acceptances"][0]
        filter_name = str(first_acceptance["name"])
        builder.title_edit.setText("Dashboard Hızlı Düzenleme Güncel")
        QTest.mouseClick(builder.add_filter_button, Qt.LeftButton)
        app.processEvents()
        row = builder._filter_rows[0]
        choose(row.field_combo, "name")
        choose(row.operator_combo, "equals")
        row.value_edit.setText(filter_name)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        filtered_row_count = builder.last_result.meta["filtered_row_count"]
        assert filtered_row_count == 1
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        assert builder.controller.current_saved_analysis_id == analysis_id

        updated_placement, updated_frame = custom_frame(window, app, analysis_id)
        assert updated_frame.card.title == "Dashboard Hızlı Düzenleme Güncel"
        assert signature(window, CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id) == placement_before
        print(
            f"quick_edit_analysis=same_id:{analysis_id},filtered_row_count={filtered_row_count},"
            f"placement_unchanged=PASS"
        )

        updated_frame.quick_menu.actions()[1].trigger()
        QTest.qWait(20)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder.controller.current_saved_analysis_id == analysis_id
        assert builder.visual_settings_expanded is True
        assert builder.form_scroll.verticalScrollBar().value() > 0
        choose(builder.chart_palette, "pastel")
        assert builder.controller.dirty is True
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()

        same_placement, visual_frame = custom_frame(window, app, analysis_id)
        assert same_placement.placement_id == placement_before[0]
        chart = visual_frame.content.findChild(_AnalysisChartWidget)
        assert chart is not None and chart.palette == CHART_PALETTES["pastel"]
        assert signature(window, CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id) == placement_before
        print("quick_edit_visual=focus:PASS,palette=pastel,same_placement=PASS")

        window._enter_dashboard_edit()
        app.processEvents()
        canvas = window._dashboard_canvas
        session = window._dashboard_edit_session
        edit_placement = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            analysis_id,
        )
        edit_frame = canvas._frames[edit_placement.placement_id]
        assert edit_frame.quick_button.isVisible() is False
        drag_start = edit_frame.drag_handle.rect().center()
        QTest.mousePress(edit_frame.drag_handle, Qt.LeftButton, Qt.NoModifier, drag_start)
        QTest.mouseMove(edit_frame.drag_handle, QPoint(drag_start.x() + 180, drag_start.y() + 70))
        QTest.mouseRelease(
            edit_frame.drag_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(drag_start.x() + 180, drag_start.y() + 70),
        )
        app.processEvents()
        moved = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            analysis_id,
        )
        edit_frame = canvas._frames[moved.placement_id]
        resize_start = edit_frame.resize_handle.rect().center()
        QTest.mousePress(edit_frame.resize_handle, Qt.LeftButton, Qt.NoModifier, resize_start)
        QTest.mouseMove(edit_frame.resize_handle, QPoint(resize_start.x() + 100, resize_start.y() + 70))
        QTest.mouseRelease(
            edit_frame.resize_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(resize_start.x() + 100, resize_start.y() + 70),
        )
        app.processEvents()
        assert session.undo_depth == 2
        window._save_dashboard_edit()
        app.processEvents()
        _normal_placement, normal_frame = custom_frame(window, app, analysis_id)
        assert normal_frame.quick_button.isVisible() is True
        print("dashboard_edit_mode=quick_hidden,drag_resize=PASS,quick_returned=PASS")

        normal_frame.quick_menu.actions()[2].trigger()
        app.processEvents()
        assert not window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id)
        assert repository.get_analysis(analysis_id) is not None
        assert signature(window, prepared_item.item_id, prepared_card.card_id) == prepared_before
        open_screen(window, app, MY_ANALYSES_ID)
        library_ids = [item.analysis_id for item in window._analysis_library_widget.items]
        assert analysis_id in library_ids
        assert refresh_calls == 0
        print(
            f"quick_unpin=placement_removed,saved_analysis_preserved,prepared_preserved,"
            f"sts_refresh_calls={refresh_calls}"
        )
        print("human_visual_qa=NOT_PERFORMED_OFFSCREEN")

        window.close()
        app.processEvents()

    print("TUR 19 DASHBOARD QUICK EDIT SMOKE: PASS")


if __name__ == "__main__":
    main()
