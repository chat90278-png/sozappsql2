from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame

from analysis_center.analysis_builder import ANALYSIS_BUILDER_ID
from analysis_center.analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from analysis_center.analysis_dashboard_canvas import DashboardQuickAction
from analysis_center.analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspaceError,
    DashboardWorkspaceStore,
)
from analysis_center.analysis_models import CardType, VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow
from analysis_center.analysis_repository import (
    AnalysisRepositoryCorruptError,
    FileAnalysisRepository,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings():
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=True)


def _window(qt_app, tmp_path, *, workspace_store=None):
    repository = FileAnalysisRepository(None, tmp_path / "analyses")
    window = AnalysisCenterWindow(
        settings=_settings(),
        workspace_store=workspace_store or DashboardWorkspaceStore(tmp_path / "dashboards"),
        analysis_repository=repository,
    )
    window.resize(1280, 820)
    window.show()
    qt_app.processEvents()
    return window, repository


def _open_screen(window, qt_app, screen_id: str):
    window.navigation.setCurrentRow(window._item_ids.index(screen_id))
    qt_app.processEvents()
    return window.stack.currentWidget()


def _open_builder(window, qt_app):
    _open_screen(window, qt_app, ANALYSIS_BUILDER_ID)
    return window._analysis_builder_widget


def _open_dashboard(window, qt_app):
    _open_screen(window, qt_app, CUSTOM_DASHBOARD_ID)
    return window._dashboard_canvas


def _configure_chart(builder, *, title="Hızlı Düzenlenen Analiz"):
    builder.dataset_combo.setCurrentIndex(builder.dataset_combo.findData("acceptances"))
    builder.visualization_combo.setCurrentIndex(
        builder.visualization_combo.findData("horizontal_bar")
    )
    builder.group_combo.setCurrentIndex(builder.group_combo.findData("platform"))
    builder.aggregation_combo.setCurrentIndex(
        builder.aggregation_combo.findData("count_rows")
    )
    builder.title_edit.setText(title)


def _save_and_pin_custom(window, qt_app, *, title="Hızlı Düzenlenen Analiz") -> str:
    builder = _open_builder(window, qt_app)
    _configure_chart(builder, title=title)
    QTest.mouseClick(builder.preview_button, Qt.LeftButton)
    qt_app.processEvents()
    QTest.mouseClick(builder.save_button, Qt.LeftButton)
    qt_app.processEvents()
    analysis_id = builder.controller.current_saved_analysis_id
    assert analysis_id and analysis_id.startswith("custom-")
    QTest.mouseClick(builder.dashboard_button, Qt.LeftButton)
    qt_app.processEvents()
    assert window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id)
    return analysis_id


def _pin_prepared(window):
    item = next(item for item in window._dashboard_items if item.item_id == "executive_summary")
    card = next(card for card in item.cards if card.enabled)
    window._toggle_dashboard_card(card)
    placement = window.workspace.placement_for_source(item.item_id, card.card_id)
    assert placement is not None
    return card, placement


def _placement_signature(window, source_id: str, card_id: str):
    placement = window.workspace.placement_for_source(source_id, card_id)
    assert placement is not None
    return (
        placement.placement_id,
        placement.x,
        placement.y,
        placement.w,
        placement.h,
    )


def _custom_frame(window, qt_app, analysis_id: str):
    canvas = _open_dashboard(window, qt_app)
    placement = window.workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        analysis_id,
    )
    assert placement is not None
    return canvas, canvas._frames[placement.placement_id]


def test_quick_menu_only_custom_normal_mode_and_emits_typed_actions(qt_app, tmp_path):
    window, _repository = _window(qt_app, tmp_path)
    try:
        _prepared_card, prepared_placement = _pin_prepared(window)
        saved_id = _save_and_pin_custom(window, qt_app)
        canvas, custom_frame = _custom_frame(window, qt_app, saved_id)
        prepared_frame = canvas._frames[prepared_placement.placement_id]

        assert custom_frame.quick_button.isVisible() is True
        assert prepared_frame.quick_button.isVisible() is False
        assert [action.text() for action in custom_frame.quick_menu.actions()] == [
            "Analizi Düzenle",
            "Görünümü Düzenle",
            "Dashboard'dan Kaldır",
        ]

        emitted = []
        canvas._quick_action_callback = lambda placement_id, action_id: emitted.append(
            (placement_id, action_id)
        )
        for action in custom_frame.quick_menu.actions():
            action.trigger()
        assert [item[1] for item in emitted] == [
            DashboardQuickAction.EDIT_ANALYSIS,
            DashboardQuickAction.EDIT_VISUAL,
            DashboardQuickAction.UNPIN,
        ]
        assert {item[0] for item in emitted} == {custom_frame.placement_id}

        window._enter_dashboard_edit()
        qt_app.processEvents()
        editing_frame = window._dashboard_canvas._frames[custom_frame.placement_id]
        assert editing_frame.quick_button.isVisible() is False
        assert editing_frame.drag_handle.isVisible() is True
        assert editing_frame.resize_handle.isVisible() is True

        window._cancel_dashboard_edit()
        qt_app.processEvents()
        canvas, returned_frame = _custom_frame(window, qt_app, saved_id)
        assert returned_frame.quick_button.isVisible() is True
    finally:
        window.close()


def test_quick_edit_analysis_keeps_same_id_and_placement_while_card_type_updates(qt_app, tmp_path):
    window, repository = _window(qt_app, tmp_path)
    try:
        _prepared_card, prepared_placement = _pin_prepared(window)
        prepared_before = _placement_signature(
            window,
            prepared_placement.source_screen_id,
            prepared_placement.card_id,
        )
        saved_id = _save_and_pin_custom(window, qt_app, title="Chart Başlığı")
        custom_before = _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )

        _canvas, frame = _custom_frame(window, qt_app, saved_id)
        frame.quick_menu.actions()[0].trigger()
        qt_app.processEvents()
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        builder = window._analysis_builder_widget
        assert builder.controller.current_saved_analysis_id == saved_id

        builder.title_edit.setText("KPI Başlığı Güncel")
        builder.visualization_combo.setCurrentIndex(
            builder.visualization_combo.findData("kpi")
        )
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()

        assert builder.controller.current_saved_analysis_id == saved_id
        saved = repository.get_analysis(saved_id)
        assert saved is not None
        assert saved.analysis_id == saved_id
        assert saved.title == "KPI Başlığı Güncel"
        assert saved.visualization == "kpi"

        canvas, updated_frame = _custom_frame(window, qt_app, saved_id)
        assert updated_frame.card.title == "KPI Başlığı Güncel"
        assert updated_frame.card.card_type == CardType.KPI
        assert updated_frame.card.value is not None
        assert _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ) == custom_before
        assert _placement_signature(
            window,
            prepared_placement.source_screen_id,
            prepared_placement.card_id,
        ) == prepared_before
        window.workspace.validate()
    finally:
        window.close()


def test_quick_edit_visual_focuses_existing_section_and_updates_same_dashboard_card(qt_app, tmp_path):
    window, repository = _window(qt_app, tmp_path)
    try:
        saved_id = _save_and_pin_custom(window, qt_app)
        placement_before = _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        _canvas, frame = _custom_frame(window, qt_app, saved_id)
        frame.quick_menu.actions()[1].trigger()
        QTest.qWait(20)
        qt_app.processEvents()

        builder = window._analysis_builder_widget
        assert window.current_item_id() == ANALYSIS_BUILDER_ID
        assert builder.controller.current_saved_analysis_id == saved_id
        assert builder.visual_settings_expanded is True
        assert builder.visual_settings_content.isVisible() is True
        assert builder.form_scroll.verticalScrollBar().value() > 0

        QTest.mouseClick(builder.preview_button, Qt.LeftButton)
        qt_app.processEvents()
        assert builder.last_definition is not None
        builder.chart_palette.setCurrentIndex(builder.chart_palette.findData("monochrome"))
        qt_app.processEvents()
        assert builder.controller.dirty is True
        assert builder.last_definition is None
        assert "Tekrar Önizle" in builder._preview_widget.text()

        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        saved = repository.get_analysis(saved_id)
        assert saved is not None and saved.analysis_id == saved_id

        _canvas, updated_frame = _custom_frame(window, qt_app, saved_id)
        assert updated_frame.card.meta["visual_settings"].chart.palette == "monochrome"
        assert _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ) == placement_before
    finally:
        window.close()


def test_quick_unpin_removes_only_placement_preserves_saved_analysis_and_does_not_reload_sts(qt_app, tmp_path):
    window, repository = _window(qt_app, tmp_path)
    try:
        _prepared_card, prepared_placement = _pin_prepared(window)
        prepared_before = _placement_signature(
            window,
            prepared_placement.source_screen_id,
            prepared_placement.card_id,
        )
        saved_id = _save_and_pin_custom(window, qt_app)
        window.controller.refresh_payload = lambda: (_ for _ in ()).throw(
            AssertionError("unexpected STS reload")
        )

        _canvas, frame = _custom_frame(window, qt_app, saved_id)
        frame.quick_menu.actions()[2].trigger()
        qt_app.processEvents()

        assert not window.workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved_id)
        assert repository.get_analysis(saved_id) is not None
        assert _placement_signature(
            window,
            prepared_placement.source_screen_id,
            prepared_placement.card_id,
        ) == prepared_before
    finally:
        window.close()


def test_quick_unpin_save_failure_keeps_placement_and_ui_state(qt_app, tmp_path, monkeypatch):
    class SwitchableFailStore:
        def __init__(self, root):
            self.inner = DashboardWorkspaceStore(root)
            self.fail = False

        def load(self, *args, **kwargs):
            return self.inner.load(*args, **kwargs)

        def save(self, *args, **kwargs):
            if self.fail:
                raise DashboardWorkspaceError("save failed")
            return self.inner.save(*args, **kwargs)

    store = SwitchableFailStore(tmp_path / "dashboards")
    window, repository = _window(qt_app, tmp_path, workspace_store=store)
    monkeypatch.setattr(
        "analysis_center.analysis_qt_window.QMessageBox.warning",
        lambda *args, **kwargs: None,
    )
    try:
        saved_id = _save_and_pin_custom(window, qt_app)
        placement_before = _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        store.fail = True
        _canvas, frame = _custom_frame(window, qt_app, saved_id)
        frame.quick_menu.actions()[2].trigger()
        qt_app.processEvents()

        assert _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ) == placement_before
        assert repository.get_analysis(saved_id) is not None
        assert frame.quick_button.isVisible() is True
    finally:
        window.close()


def test_quick_edit_missing_or_repository_error_is_controlled_and_never_removes_placement(
    qt_app,
    tmp_path,
    monkeypatch,
):
    warnings = []
    monkeypatch.setattr(
        "analysis_center.analysis_qt_window.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    window, repository = _window(qt_app, tmp_path)
    try:
        saved_id = _save_and_pin_custom(window, qt_app)
        placement_before = _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        )
        _canvas, frame = _custom_frame(window, qt_app, saved_id)

        assert repository.delete_analysis(saved_id) is True
        frame.quick_menu.actions()[0].trigger()
        qt_app.processEvents()
        assert warnings[-1][1] == "Kaydedilmiş analiz bulunamadı."
        assert _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ) == placement_before

        # Recreate the definition, keep the rendered frame, then simulate a protected repository state.
        builder = _open_builder(window, qt_app)
        _configure_chart(builder, title="Repository Error Analizi")
        QTest.mouseClick(builder.save_button, Qt.LeftButton)
        qt_app.processEvents()
        repository._load_error = AnalysisRepositoryCorruptError("broken repository")
        window._dashboard_quick_action(
            placement_before[0],
            DashboardQuickAction.EDIT_VISUAL,
        )
        qt_app.processEvents()
        assert "Kaydedilmiş analizler yüklenemedi" in warnings[-1][1]
        assert _placement_signature(
            window,
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            saved_id,
        ) == placement_before
    finally:
        window.close()
