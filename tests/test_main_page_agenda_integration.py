from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = Path("src/ui/main_page_analysis_window.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def _class_node() -> ast.ClassDef:
    tree = ast.parse(_source())
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )


def _method(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in _class_node().body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_agenda_inserted_between_status_and_calendar():
    source = _source()
    status_pos = source.index("self._install_contract_status_widget()")
    agenda_pos = source.index("self._install_personal_agenda_widget()")
    assert status_pos < agenda_pos
    method = ast.get_source_segment(
        source,
        _method("_install_personal_agenda_widget"),
    )
    assert "calendar_layout.indexOf(calendar_widget)" in method
    assert "calendar_layout.insertWidget" in method


def test_missing_view_contracts_hides_widget_without_load():
    source = ast.get_source_segment(
        _source(),
        _method("_sync_agenda_permission_visibility"),
    )
    assert 'has_permission("view_contracts")' in source
    assert "setVisible(allowed)" in source
    assert ".load(" not in source


def test_refresh_loads_compact_2_detail_20():
    source = ast.get_source_segment(_source(), _method("refresh_agenda"))
    assert "compact_limit=2" in source
    assert "detail_limit=20" in source


def test_refresh_does_not_mark_seen():
    source = ast.get_source_segment(_source(), _method("refresh_agenda"))
    assert "mark_seen" not in source


def test_seen_interaction_calls_facade_and_refreshes():
    source = ast.get_source_segment(_source(), _method("_agenda_mark_seen"))
    assert "facade.mark_seen" in source
    assert "refresh_agenda" in source


def test_snooze_uses_facade_preset_and_refreshes():
    source = ast.get_source_segment(_source(), _method("_agenda_snooze"))
    assert "snooze_until_for_preset" in source
    assert "facade.snooze" in source
    assert "refresh_agenda" in source


def test_detail_window_uses_stable_current_main_registry():
    source = ast.get_source_segment(_source(), _method("_open_agenda_details"))
    assert "open_or_raise_tool_window" in source
    assert '"agenda:detail"' in source
    assert "self._create_agenda_detail_window" in source


def test_open_contract_delegates_existing_navigation():
    source = ast.get_source_segment(_source(), _method("_open_agenda_contract"))
    assert "self.contract_index" in source
    assert "self.open_contract_item(match)" in source


def test_refresh_error_does_not_crash_main_page():
    source = ast.get_source_segment(_source(), _method("refresh_agenda"))
    assert "except Exception as exc" in source
    assert "widget.set_error" in source


def test_sts_switch_rebinds_facade_if_source_supports_switch_hook():
    reset = ast.get_source_segment(_source(), _method("_reset_agenda_binding"))
    switch = ast.get_source_segment(_source(), _method("start_sts_load"))
    assert "self._agenda_facade = None" in reset
    assert "self._reset_agenda_binding()" in switch
    assert "super().start_sts_load(path)" in switch


def test_no_new_sqlite_connection():
    source = _source()
    assert "import sqlite3" not in source
    assert "sqlite3.connect" not in source
    assert "PersonalAgendaFacade(db)" in source


def test_ui_imports_do_not_create_qapplication():
    tree = ast.parse(_source())
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            called = ast.unparse(node.value.func)
            assert called not in {"QApplication", "QApplication.instance"}


def test_refresh_hook_debounces_agenda():
    source = ast.get_source_segment(_source(), _method("update_alert_strip"))
    schedule = ast.get_source_segment(
        _source(),
        _method("schedule_agenda_refresh"),
    )
    assert "schedule_agenda_refresh" in source
    assert "timer.start(200)" in schedule


def test_ui_has_no_raw_agenda_sql_or_state_repository_write():
    source = _source()
    assert "AgendaStateRepository" not in source
    assert "staff_agenda_state" not in source
    assert ".execute(" not in source


def test_widget_and_timer_installation_are_idempotent_by_construction():
    status = ast.get_source_segment(_source(), _method("_install_contract_status_widget"))
    agenda = ast.get_source_segment(_source(), _method("_install_personal_agenda_widget"))
    assert "qt_obj_alive(widget)" in status
    assert "qt_obj_alive(widget)" in agenda
    assert "qt_obj_alive(timer)" in agenda
