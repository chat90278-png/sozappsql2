from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_custom_library import MY_ANALYSES_ID
from analysis_center.analysis_dashboard_workspace import DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import FileAnalysisRepository


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _window(qt_app, tmp_path):
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=DashboardWorkspaceStore(tmp_path / "dashboards"),
        analysis_repository=FileAnalysisRepository(None, tmp_path / "analyses"),
    )
    window.show()
    qt_app.processEvents()
    return window


def _open_screen(window, qt_app, screen_id: str):
    window.navigation.setCurrentRow(window._item_ids.index(screen_id))
    qt_app.processEvents()
    return window.stack.currentWidget()


def _card_frame(screen, title: str) -> QFrame:
    for frame in screen.findChildren(QFrame, "analysisCard"):
        label = frame.findChild(QLabel, "analysisCardTitle")
        if label is not None and label.text() == title:
            return frame
    raise AssertionError(f"Card frame not found: {title}")


def _template_buttons(frame: QFrame) -> list[QPushButton]:
    return [
        button
        for button in frame.findChildren(QPushButton, "analysisCardAction")
        if button.text() == "Kopyala ve Düzenle"
    ]


def test_supported_prepared_card_shows_template_action_while_legacy_and_unsupported_cards_hide_it(qt_app, tmp_path):
    window = _window(qt_app, tmp_path)
    try:
        executive = _open_screen(window, qt_app, "executive_summary")
        supported = _card_frame(executive, "Toplam Sözleşme")
        assert len(_template_buttons(supported)) == 1

        unsupported_builtin = _card_frame(executive, "Yaklaşan Termin Listesi")
        assert _template_buttons(unsupported_builtin) == []

        contracts = _open_screen(window, qt_app, "contract_analysis")
        legacy = _card_frame(contracts, "Toplam Sözleşme")
        assert _template_buttons(legacy) == []
    finally:
        window.close()


def test_copy_and_edit_opens_builder_hydrated_preview_saves_custom_and_uses_existing_dashboard_flow(qt_app, tmp_path):
    window = _window(qt_app, tmp_path)
    try:
        platform_screen = _open_screen(window, qt_app, "platform_analysis")
        frame = _card_frame(platform_screen, "Platform Dağılımı")
        button = _template_buttons(frame)[0]
        QTest.mouseClick(button, Qt.LeftButton)
        qt_app.processEvents()

        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        builder = window._analysis_builder_widget
        assert builder is not None
        assert builder.controller.current_saved_analysis_id is None
        assert builder.controller.dirty is True
        assert builder.controller.draft.analysis_id.startswith("preview-")
        assert builder.title_edit.text() == "Platform Dağılımı"
        assert builder.dataset_combo.currentData() == "contracts"
        assert builder.visualization_combo.currentData() == "horizontal_bar"
        assert builder.group_combo.currentData() == "platform_bucket"
        assert builder.aggregation_combo.currentData() == "count_rows"
        assert "Hazır analiz ayarları yüklendi" in builder._preview_widget.text()

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.last_definition is not None
        assert builder.last_result is not None
        preview_title = builder._preview_widget.findChild(QLabel, "analysisCardTitle")
        assert preview_title is not None
        assert preview_title.text() == "Platform Dağılımı"

        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        saved_id = builder.controller.current_saved_analysis_id
        assert saved_id is not None and saved_id.startswith("custom-")
        assert saved_id != "platform_distribution"

        library_screen = _open_screen(window, qt_app, MY_ANALYSES_ID)
        assert "Platform Dağılımı" in [
            label.text() for label in library_screen.findChildren(QLabel)
        ]

        _open_screen(window, qt_app, ANALYSIS_BUILDER_ID)
        builder = window._analysis_builder_widget
        assert builder is not None
        QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
        qt_app.processEvents()
        assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
    finally:
        window.close()


def test_template_action_resets_existing_saved_edit_identity_before_first_save(qt_app, tmp_path):
    window = _window(qt_app, tmp_path)
    try:
        builder = _open_screen(window, qt_app, ANALYSIS_BUILDER_ID)
        widget = window._analysis_builder_widget
        widget.visualization_combo.setCurrentIndex(widget.visualization_combo.findData("kpi"))
        widget.title_edit.setText("Korunacak Özel Analiz")
        QTest.mouseClick(widget.save_button, Qt.LeftButton)
        qt_app.processEvents()
        old_id = widget.controller.current_saved_analysis_id
        old_definition = window.controller.analysis_service.get_saved_analysis(old_id)
        assert old_definition is not None

        executive = _open_screen(window, qt_app, "executive_summary")
        template_button = _template_buttons(_card_frame(executive, "Toplam Sözleşme"))[0]
        QTest.mouseClick(template_button, Qt.LeftButton)
        qt_app.processEvents()
        widget = window._analysis_builder_widget
        assert widget.controller.current_saved_analysis_id is None
        assert widget.controller.draft.analysis_id.startswith("preview-")

        widget.title_edit.setText("Hazırdan Yeni Analiz")
        QTest.mouseClick(widget.save_button, Qt.LeftButton)
        qt_app.processEvents()
        new_id = widget.controller.current_saved_analysis_id
        assert new_id is not None and new_id != old_id
        assert window.controller.analysis_service.get_saved_analysis(old_id).to_dict() == old_definition.to_dict()
        assert window.controller.analysis_service.get_saved_analysis(new_id) is not None
    finally:
        window.close()
