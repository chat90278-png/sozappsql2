from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("src/ui/main_page_analysis_window.py")


def _text() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _method(name: str) -> ast.FunctionDef:
    tree = ast.parse(_text())
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_current_main_analysis_and_corner_routes_are_preserved():
    source = _text()
    assert '"report:analysis_center"' in source
    assert "ContractStatusSummaryWidget" in source
    assert "CornerMenuOverlay" in source
    assert "CompactMainWindow" in source


def test_header_semantic_order_is_status_agenda_calendar():
    source = _text()
    assert source.index("self._install_contract_status_widget()") < source.index(
        "self._install_personal_agenda_widget()"
    )
    status = ast.get_source_segment(
        source,
        _method("_install_contract_status_widget"),
    )
    agenda = ast.get_source_segment(
        source,
        _method("_install_personal_agenda_widget"),
    )
    assert "calendar_layout.insertWidget" in status
    assert "calendar_layout.insertWidget" in agenda
    assert "calendar_layout.indexOf(calendar_widget)" in status
    assert "calendar_layout.indexOf(calendar_widget)" in agenda


def test_refresh_and_contract_navigation_use_existing_main_hooks():
    source = _text()
    refresh = ast.get_source_segment(source, _method("update_alert_strip"))
    navigation = ast.get_source_segment(source, _method("_open_agenda_contract"))
    assert refresh.count("super().update_alert_strip()") == 1
    assert refresh.count("schedule_agenda_refresh()") == 1
    assert "self.contract_index" in navigation
    assert "self.open_contract_item(match)" in navigation
    assert "contract_id" in navigation


def test_permission_and_system_admin_paths_fail_closed():
    source = ast.get_source_segment(
        _text(),
        _method("_sync_agenda_permission_visibility"),
    )
    assert "self.current_staff" in source
    assert 'has_permission("view_contracts")' in source
    assert "allowed = False" in source


def test_file_switch_and_close_cleanup_are_present():
    source = _text()
    switch = ast.get_source_segment(source, _method("start_sts_load"))
    close = ast.get_source_segment(source, _method("closeEvent"))
    assert "_reset_agenda_binding" in switch
    assert "super().start_sts_load(path)" in switch
    assert "timer.stop()" in close
    assert "detail.close()" in close
    assert "super().closeEvent(event)" in close
