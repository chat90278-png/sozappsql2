from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import FileAnalysisRepository


ROOT = Path(__file__).resolve().parents[1]
STS_PATH = ROOT / "STS-S-VR-S-NEK---TBD---1__share-edit__2026-07-07_14-04.sts"


def open_screen(window: AnalysisCenterWindow, app: QApplication, screen_id: str):
    window.navigation.setCurrentRow(window._item_ids.index(screen_id))
    app.processEvents()
    return window.stack.currentWidget()


def card_frame(screen, title: str) -> QFrame:
    for frame in screen.findChildren(QFrame, "analysisCard"):
        label = frame.findChild(QLabel, "analysisCardTitle")
        if label is not None and label.text() == title:
            return frame
    raise AssertionError(f"card not found: {title}")


def template_button(frame: QFrame) -> QPushButton | None:
    for button in frame.findChildren(QPushButton, "analysisCardAction"):
        if button.text() == "Kopyala ve Düzenle":
            return button
    return None


def library_item(library, analysis_id: str) -> QFrame:
    for frame in library.findChildren(QFrame, "analysisLibraryItem"):
        if frame.property("analysisId") == analysis_id:
            return frame
    raise AssertionError(f"library item not found: {analysis_id}")


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
        upcoming_days=60,
    )

    with TemporaryDirectory(prefix="tur18-prepared-template-") as temp_dir:
        temp_root = Path(temp_dir)
        repository = FileAnalysisRepository(STS_PATH, root=temp_root / "analyses")
        workspace_store = DashboardWorkspaceStore(temp_root / "dashboards")
        window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            analysis_repository=repository,
            workspace_store=workspace_store,
        )
        window.resize(1600, 920)
        window.show()
        app.processEvents()

        print(f"source={STS_PATH.name}")
        print(f"repository_path={repository.repository_path()}")
        print(f"workspace_path={workspace_store.workspace_path(STS_PATH)}")
        print(f"generated_at={window._payload['metrics']['generated_at']}")

        executive = open_screen(window, app, "executive_summary")
        prepared_frame = card_frame(executive, "Yaklaşan Termin")
        prepared_action = template_button(prepared_frame)
        assert prepared_action is not None and prepared_action.isVisible()
        prepared_card = next(
            card
            for item in window._dashboard_items
            if item.item_id == "executive_summary"
            for card in item.cards
            if card.card_id == "exec_upcoming_deadlines"
        )
        prepared_before = deepcopy(prepared_card.to_dict())
        print(
            "prepared_action="
            f"screen={prepared_card.screen_id},card_id={prepared_card.card_id},"
            f"builtin={prepared_card.meta.get('analysis_id')},visible=True"
        )

        QTest.mouseClick(prepared_action, Qt.LeftButton)
        app.processEvents()
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        builder = window._analysis_builder_widget
        assert builder is not None
        assert builder.controller.current_saved_analysis_id is None
        assert builder.controller.draft.analysis_id.startswith("preview-")
        assert builder.controller.dirty is True
        assert builder.dataset_combo.currentData() == "deadlines"
        assert builder.visualization_combo.currentData() == "kpi"
        assert builder.aggregation_combo.currentData() == "count_rows"
        assert len(builder.controller.draft.filters) == 3
        original_preview_id = builder.controller.draft.analysis_id
        filter_signature = [
            (item.field_id, item.operator, item.raw_value)
            for item in builder.controller.draft.filters
        ]
        print(
            "template_hydration="
            f"preview_id={original_preview_id},dataset={builder.dataset_combo.currentData()},"
            f"visualization={builder.visualization_combo.currentData()},"
            f"aggregation={builder.aggregation_combo.currentData()},filters={filter_signature}"
        )

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        first_value = builder.last_result.value
        print(
            "template_preview="
            f"value={first_value},filtered={builder.last_result.meta['filtered_row_count']}"
        )

        upper_filter_index = next(
            index
            for index, item in enumerate(builder.controller.draft.filters)
            if item.field_id == "due_date" and item.operator == "less_than_or_equal"
        )
        generated_at = str(window._payload["metrics"]["generated_at"])
        builder._filter_rows[upper_filter_index].value_edit.setText(generated_at)
        app.processEvents()
        assert builder.last_result is None
        assert "Tekrar Önizle" in builder._preview_widget.text()
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        filtered_value = builder.last_result.value
        assert filtered_value <= first_value
        print(
            "template_changed_preview="
            f"upper_due_date={generated_at},value={filtered_value},"
            f"filtered={builder.last_result.meta['filtered_row_count']}"
        )

        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        first_custom_id = builder.controller.current_saved_analysis_id
        assert first_custom_id and first_custom_id.startswith("custom-")
        assert first_custom_id != prepared_card.meta.get("analysis_id")
        first_custom = repository.get_analysis(first_custom_id)
        assert first_custom is not None
        first_custom_before_second_template = deepcopy(first_custom.to_dict())
        print(f"first_custom_id={first_custom_id}")

        library = open_screen(window, app, MY_ANALYSES_ID)
        item = library_item(library, first_custom_id)
        assert item.findChild(QLabel, "analysisLibraryItemTitle").text() == prepared_card.title
        dashboard_button = item.findChild(QPushButton, "analysisLibraryDashboardButton")
        assert dashboard_button is not None
        QTest.mouseClick(dashboard_button, Qt.LeftButton)
        app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, first_custom_id)

        open_screen(window, app, CUSTOM_DASHBOARD_ID)
        placement = window.workspace.placement_for_source(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            first_custom_id,
        )
        assert placement is not None
        canvas = window._dashboard_canvas
        assert canvas is not None
        custom_frame = canvas._frames[placement.placement_id]
        assert custom_frame.card.title == prepared_card.title
        print(
            "dashboard_render="
            f"analysis_id={first_custom_id},placement_id={placement.placement_id},"
            f"card_type={custom_frame.card.card_type.value},title={custom_frame.card.title!r}"
        )

        # The builtin/prepared card remains untouched after custom save and Dashboard pin.
        assert prepared_card.to_dict() == prepared_before
        print("builtin_mutation=False")

        # Open the saved custom edit session first, then replace it with another prepared template.
        library = open_screen(window, app, MY_ANALYSES_ID)
        edit_button = library_item(library, first_custom_id).findChild(
            QPushButton,
            "analysisLibraryEditButton",
        )
        assert edit_button is not None
        QTest.mouseClick(edit_button, Qt.LeftButton)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder is not None
        assert builder.controller.current_saved_analysis_id == first_custom_id

        platform_screen = open_screen(window, app, "platform_analysis")
        platform_action = template_button(card_frame(platform_screen, "Platform Dağılımı"))
        assert platform_action is not None
        QTest.mouseClick(platform_action, Qt.LeftButton)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder is not None
        assert builder.controller.current_saved_analysis_id is None
        assert builder.controller.draft.analysis_id.startswith("preview-")
        assert builder.controller.draft.analysis_id != original_preview_id
        assert builder.dataset_combo.currentData() == "contracts"
        assert builder.visualization_combo.currentData() == "horizontal_bar"
        assert builder.group_combo.currentData() == "platform_bucket"
        builder.title_edit.setText("Platform Dağılımı Özel")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        second_custom_id = builder.controller.current_saved_analysis_id
        assert second_custom_id and second_custom_id.startswith("custom-")
        assert second_custom_id != first_custom_id
        assert repository.get_analysis(first_custom_id).to_dict() == first_custom_before_second_template
        assert len(repository.list_analyses()) == 2
        print(
            "edit_session_template_regression="
            f"existing_id={first_custom_id},new_id={second_custom_id},"
            "existing_overwritten=False"
        )

        contracts = open_screen(window, app, "contract_analysis")
        legacy_action = template_button(card_frame(contracts, "Toplam Sözleşme"))
        assert legacy_action is None
        print("legacy_unbacked_action_visible=False")

        print("human_visual_qa=NOT_PERFORMED_OFFSCREEN")
        print("offscreen_verification=Qt action visibility + Builder hydration + real engine preview + persistence + Dashboard")
        window.close()
        app.processEvents()

    print("TUR 18 PREPARED ANALYSIS TEMPLATE SMOKE: PASS")


if __name__ == "__main__":
    main()
