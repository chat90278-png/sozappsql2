from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import CardType, VisualSettings
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
    builder = window._analysis_builder_widget
    assert builder is not None
    return builder


def open_library(window: AnalysisCenterWindow, app: QApplication):
    window.navigation.setCurrentRow(window._item_ids.index(MY_ANALYSES_ID))
    app.processEvents()
    library = window._analysis_library_widget
    assert library is not None
    return library


def main() -> None:
    assert STS_PATH.exists(), STS_PATH
    app = QApplication.instance() or QApplication([])
    settings = VisualSettings(
        show_disabled_sections=False,
        empty_state_uses_sample=False,
        max_table_rows=100,
    )

    with TemporaryDirectory(prefix="tur14-custom-analysis-") as temp_dir:
        temp_root = Path(temp_dir)
        analyses_root = temp_root / "analyses"
        dashboard_root = temp_root / "dashboards"
        repository = FileAnalysisRepository(STS_PATH, analyses_root)
        window = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=DashboardWorkspaceStore(dashboard_root),
            analysis_repository=repository,
        )
        window.show()
        app.processEvents()

        print(f"source={STS_PATH.name}")
        print(f"repository_path={repository.repository_path()}")
        print(f"status={window.status_text.text()}")
        nav_titles = [window.navigation.item(i).text() for i in range(window.navigation.count())]
        print(f"navigation={nav_titles}")
        assert "Analiz Oluştur" in nav_titles
        assert "Analizlerim" in nav_titles

        library = open_library(window, app)
        assert library.items == []
        assert any(
            "Henüz kaydedilmiş analiziniz yok" in label.text()
            for label in library.list_host.findChildren(QLabel)
        )
        print("library_empty=PASS")

        builder = open_builder(window, app)
        choose(builder.dataset_combo, "acceptances")
        choose(builder.visualization_combo, "horizontal_bar")
        choose(builder.group_combo, "platform")
        choose(builder.aggregation_combo, "count_rows")
        builder.title_edit.setText("Platform Bazlı Teslimatlar")
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        assert builder.last_card is not None and builder.last_card.card_type == CardType.CHART
        assert builder.findChild(type(builder.save_button), "analysisPinButton") is None
        print(
            "initial_preview="
            f"dataset={builder.last_definition.dataset},"
            f"group={builder.last_definition.dimensions[0]},"
            f"aggregation={builder.last_definition.measures[0].aggregation},"
            f"filtered_row_count={builder.last_result.meta['filtered_row_count']},"
            f"result_row_count={builder.last_result.meta['result_row_count']}"
        )

        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id is not None and saved_id.startswith("custom-")
        assert repository.get_analysis(saved_id) is not None
        print(f"saved_analysis_id={saved_id}")

        library = open_library(window, app)
        assert len(library.items) == 1
        assert library.items[0].analysis_id == saved_id
        assert library.items[0].title == "Platform Bazlı Teslimatlar"
        library.open_analysis(saved_id)
        app.processEvents()
        assert library.last_result is not None
        print(
            "library_open="
            f"analysis_id={saved_id},"
            f"filtered_row_count={library.last_result.meta['filtered_row_count']},"
            f"result_row_count={library.last_result.meta['result_row_count']}"
        )

        window._edit_saved_analysis(saved_id)
        app.processEvents()
        builder = window._analysis_builder_widget
        assert builder is not None
        assert builder.controller.current_saved_analysis_id == saved_id
        assert builder.dataset_combo.currentData() == "acceptances"
        assert builder.visualization_combo.currentData() == "horizontal_bar"
        assert builder.group_combo.currentData() == "platform"
        assert builder.aggregation_combo.currentData() == "count_rows"

        real_platform = str(window.controller.analysis_service.data["acceptances"][0]["platform"])
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
        print(
            "edited_preview="
            f"filter=platform:equals:{real_platform},"
            f"filtered_row_count={filtered_count},"
            f"result_row_count={builder.last_result.meta['result_row_count']}"
        )
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        app.processEvents()
        assert builder.controller.current_saved_analysis_id == saved_id
        assert repository.get_analysis(saved_id).filters[0].value == real_platform
        print(f"edit_save_same_id={builder.controller.current_saved_analysis_id}")

        window.close()
        app.processEvents()

        reloaded_repository = FileAnalysisRepository(STS_PATH, analyses_root)
        reloaded = AnalysisCenterWindow(
            source=STS_PATH,
            settings=settings,
            workspace_store=DashboardWorkspaceStore(dashboard_root),
            analysis_repository=reloaded_repository,
        )
        reloaded.show()
        app.processEvents()
        library = open_library(reloaded, app)
        assert len(library.items) == 1
        assert library.items[0].analysis_id == saved_id
        print(f"restart_persistence_count={len(library.items)}")

        reloaded._edit_saved_analysis(saved_id)
        app.processEvents()
        builder = reloaded._analysis_builder_widget
        assert builder is not None
        assert len(builder._filter_rows) == 1
        assert builder._filter_rows[0].filter_draft.raw_value == real_platform
        print(f"hydrated_filter_value={builder._filter_rows[0].filter_draft.raw_value}")

        library = open_library(reloaded, app)
        library.copy_analysis(saved_id)
        app.processEvents()
        assert len(library.items) == 2
        copied = next(item for item in library.items if item.analysis_id != saved_id)
        copied_id = copied.analysis_id
        assert copied_id.startswith("custom-") and copied_id != saved_id
        assert copied.title == "Platform Bazlı Teslimatlar Kopya"
        print(f"copied_analysis_id={copied_id}")
        print(f"copy_title={copied.title}")
        print(f"list_count_after_copy={len(library.items)}")

        assert library.delete_analysis(copied_id, confirmed=True) is True
        assert reloaded_repository.get_analysis(saved_id) is not None
        assert reloaded_repository.get_analysis(copied_id) is None
        assert len(reloaded_repository.list_analyses()) == 1
        print(f"list_count_after_delete={len(reloaded_repository.list_analyses())}")

        reloaded._edit_saved_analysis(saved_id)
        app.processEvents()
        builder = reloaded._analysis_builder_widget
        assert builder is not None
        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        app.processEvents()
        assert builder.last_result is not None
        assert builder._preview_widget.objectName() == "analysisPreviewCardHost"
        builder._filter_rows[0].value_edit.setText(real_platform + "-DEĞİŞTİ")
        app.processEvents()
        assert builder._preview_widget.objectName() == "analysisBuilderPreviewInfo"
        assert builder._preview_widget.text() == "Analiz ayarları değişti. Tekrar Önizle'ye basın."
        print("stale_preview_after_filter_change=PASS")

        draft_id = builder.controller.draft.analysis_id
        draft_filter = builder._filter_rows[0].filter_draft.raw_value
        reloaded.refresh_data()
        app.processEvents()
        builder = reloaded._analysis_builder_widget
        assert reloaded.current_item_id() == ANALYSIS_BUILDER_ID
        assert builder is not None
        assert builder.controller.draft.analysis_id == draft_id
        assert builder._filter_rows[0].filter_draft.raw_value == draft_filter
        assert builder._preview_widget.text() == "Veri yenilendi. Analizi tekrar önizleyin."
        print(
            "builder_refresh="
            f"screen={reloaded.current_item_id()},draft_id={draft_id},preview=stale-cleared"
        )

        library = open_library(reloaded, app)
        library.open_analysis(saved_id)
        app.processEvents()
        assert library.last_definition is not None
        reloaded.refresh_data()
        app.processEvents()
        assert reloaded.current_item_id() == MY_ANALYSES_ID
        library = reloaded._analysis_library_widget
        assert library is not None
        assert library._preview_widget.text() == "Veri yenilendi. Analizi tekrar açın."
        print("library_refresh=screen-preserved,preview=stale-cleared")

        dashboard_row = reloaded._item_ids.index(CUSTOM_DASHBOARD_ID)
        reloaded.navigation.setCurrentRow(dashboard_row)
        app.processEvents()
        assert reloaded.current_item_id() == CUSTOM_DASHBOARD_ID
        prepared_row = reloaded._item_ids.index("executive_summary")
        reloaded.navigation.setCurrentRow(prepared_row)
        app.processEvents()
        assert reloaded.current_item_id() == "executive_summary"
        print("existing_screens=dashboard:PASS,executive_summary:PASS")

        print(f"final_saved_analysis_id={saved_id}")
        print(f"final_copied_analysis_id={copied_id}")
        print(f"final_list_count={len(reloaded_repository.list_analyses())}")
        print(f"final_filtered_row_count={filtered_count}")
        reloaded.close()
        app.processEvents()

    print("TUR 14 CUSTOM ANALYSIS PERSISTENCE SMOKE: PASS")


if __name__ == "__main__":
    main()
