from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import FileAnalysisRepository


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

    with TemporaryDirectory(prefix="tur15-custom-dashboard-") as temp_dir:
        temp_root = Path(temp_dir)
        analyses_root = temp_root / "analyses"
        dashboard_root = temp_root / "dashboards"
        repository = FileAnalysisRepository(STS_PATH, analyses_root)
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

        prepared_card = window._dashboard_items[0].cards[0]
        window._toggle_dashboard_card(prepared_card)
        prepared_signature = (prepared_card.screen_id, prepared_card.card_id)
        assert window.workspace.contains(*prepared_signature)
        print(f"prepared_card={prepared_signature[0]}:{prepared_signature[1]}")

        builder = open_builder(window, app)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Platform Bazlı Teslimatlar")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        initial_filtered = builder.last_result.meta["filtered_row_count"]
        initial_rows = builder.last_result.meta["result_row_count"]
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id and saved_id.startswith("custom-")
        print(
            "created_preview="
            f"dataset=acceptances,group=platform,aggregation=count_rows,"
            f"filtered_row_count={initial_filtered},result_row_count={initial_rows}"
        )
        print(f"saved_analysis_id={saved_id}")

        library = open_library(window, app)
        button = dashboard_button(library, saved_id)
        assert button.text() == "+ Dashboard"
        QTest.mouseClick(button, Qt.LeftButton)
        app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        print("library_pin=PASS")

        canvas = open_dashboard(window, app)
        placement = window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert placement is not None
        placement_id = placement.placement_id
        assert canvas is not None and placement_id in canvas._frames
        assert canvas._frames[placement_id].card.title == "Platform Bazlı Teslimatlar"
        print(f"dashboard_render=placement_id={placement_id},card_type={canvas._frames[placement_id].card.card_type.value}")

        window._enter_dashboard_edit()
        app.processEvents()
        canvas = window._dashboard_canvas
        session = window._dashboard_edit_session
        placement = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        frame = canvas._frames[placement.placement_id]
        before_geometry = (placement.x, placement.y, placement.w, placement.h)
        drag_start = frame.drag_handle.rect().center()
        QTest.mousePress(frame.drag_handle, Qt.LeftButton, Qt.NoModifier, drag_start)
        QTest.mouseMove(frame.drag_handle, QPoint(drag_start.x() + 220, drag_start.y() + 80))
        QTest.mouseRelease(
            frame.drag_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(drag_start.x() + 220, drag_start.y() + 80),
        )
        app.processEvents()
        moved = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        frame = canvas._frames[moved.placement_id]
        resize_start = frame.resize_handle.rect().center()
        QTest.mousePress(frame.resize_handle, Qt.LeftButton, Qt.NoModifier, resize_start)
        QTest.mouseMove(frame.resize_handle, QPoint(resize_start.x() + 110, resize_start.y() + 70))
        QTest.mouseRelease(
            frame.resize_handle,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(resize_start.x() + 110, resize_start.y() + 70),
        )
        app.processEvents()
        resized = session.working_workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        after_geometry = (resized.x, resized.y, resized.w, resized.h)
        assert after_geometry != before_geometry
        assert session.undo_depth == 2
        window._save_dashboard_edit()
        app.processEvents()
        assert window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ).placement_id == placement_id
        print(f"dashboard_edit=before={before_geometry},after={after_geometry},undo_steps=2")

        window.close()
        app.processEvents()

        reloaded_repository = FileAnalysisRepository(STS_PATH, analyses_root)
        reloaded_store = DashboardWorkspaceStore(dashboard_root)
        reloaded = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=reloaded_store,
            analysis_repository=reloaded_repository,
        )
        reloaded.show()
        app.processEvents()
        canvas = open_dashboard(reloaded, app)
        placement = reloaded.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        assert placement is not None and placement.placement_id == placement_id
        assert canvas is not None and canvas._frames[placement_id].card.title == "Platform Bazlı Teslimatlar"
        restart_geometry = (placement.x, placement.y, placement.w, placement.h)
        assert restart_geometry == after_geometry
        print(f"restart_pinned=PASS,geometry={restart_geometry}")

        reloaded._edit_saved_analysis(saved_id)
        app.processEvents()
        builder = reloaded._analysis_builder_widget
        assert builder is not None
        real_platform = str(reloaded.controller.analysis_service.data["acceptances"][0]["platform"])
        builder.title_edit.setText("Platform Bazlı Teslimatlar Güncel")
        QTest.mouseClick(builder.add_filter_button, Qt.LeftButton)
        app.processEvents()
        filter_row = builder._filter_rows[0]
        choose(filter_row.field_combo, "platform")
        choose(filter_row.operator_combo, "equals")
        filter_row.value_edit.setText(real_platform)
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        filtered_count = builder.last_result.meta["filtered_row_count"]
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        assert builder.controller.current_saved_analysis_id == saved_id
        print(f"edit_same_id={saved_id},filter_platform={real_platform},filtered_row_count={filtered_count}")

        canvas = open_dashboard(reloaded, app)
        placement = reloaded.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        card = canvas._frames[placement.placement_id].card
        assert card.title == "Platform Bazlı Teslimatlar Güncel"
        assert card.meta["filtered_row_count"] == filtered_count
        print(f"dashboard_after_edit=title={card.title},filtered_row_count={card.meta['filtered_row_count']}")

        library = open_library(reloaded, app)
        library.copy_analysis(saved_id)
        app.processEvents()
        copied = next(item for item in library.items if item.analysis_id != saved_id)
        copied_id = copied.analysis_id
        assert not reloaded.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, copied_id)
        print(f"copied_analysis_id={copied_id},copy_auto_pinned=False")
        print(f"list_count_after_copy={len(library.items)}")

        assert library.delete_analysis(saved_id, confirmed=True) is True
        app.processEvents()
        assert reloaded_repository.get_analysis(saved_id) is None
        assert not reloaded.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert reloaded.workspace.contains(*prepared_signature)
        assert reloaded_repository.get_analysis(copied_id) is not None
        print(
            "delete_original="
            f"custom_placement_present={reloaded.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)},"
            f"prepared_present={reloaded.workspace.contains(*prepared_signature)},"
            f"library_count={len(reloaded_repository.list_analyses())}"
        )

        canvas = open_dashboard(reloaded, app)
        assert reloaded.workspace.contains(*prepared_signature)
        assert all(
            frame.card.card_id != saved_id
            for frame in (canvas._frames.values() if canvas is not None else [])
        )
        print("prepared_dashboard_preserved=PASS")
        print("human_visual_qa=NOT_PERFORMED_OFFSCREEN")
        reloaded.close()
        app.processEvents()

    print("TUR 15 CUSTOM DASHBOARD INTEGRATION SMOKE: PASS")


if __name__ == "__main__":
    main()
