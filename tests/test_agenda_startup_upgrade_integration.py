from __future__ import annotations

import ast
from pathlib import Path


def test_worker_keeps_schema_gate_as_only_upgrade_entrypoint():
    source = Path("src/workers/sts_load_worker.py").read_text(encoding="utf-8")
    assert (
        "from src.services.sts_schema_upgrade_gate import upgrade_sts_file"
        in source
    )
    assert (
        "from src.services.sts_schema_upgrade import upgrade_sts_file"
        not in source
    )
    assert "upgrade_result = upgrade_sts_file(" in source
    assert source.index("upgrade_result = upgrade_sts_file(") < source.index(
        "store = STSStore("
    )


def test_app_share_startup_stays_separate_from_normal_main_window():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "open_share_contract_window" in source
    assert "MainWindow(initial_path=selected_path, current_staff=staff)" in source
    share_branch = source.index(
        "if cli_path and _share_metadata_from_path(cli_path):"
    )
    normal_window = source.index(
        "MainWindow(initial_path=selected_path, current_staff=staff)"
    )
    assert share_branch < normal_window


def test_runtime_fix_install_order_is_unchanged():
    source = Path("app.py").read_text(encoding="utf-8")
    calls = [
        "install_multiplatform_contract_persistence_fix()",
        "install_multiplatform_context_refresh_fix()",
        "install_corner_menu_runtime_fix()",
        "install_main_page_identity_runtime_fix()",
        "install_contract_edit_timing_fix()",
        "install_sd_edit_timing_fix()",
        "install_contract_save_telemetry_fix()",
    ]
    positions = [source.index(call) for call in calls]
    assert positions == sorted(positions)


def test_main_window_open_sequence_keeps_worker_before_store():
    source = Path("src/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    start = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "start_sts_load"
    )
    finished = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_on_sts_load_finished"
    )

    def called_names(node: ast.AST) -> set[str]:
        names: set[str] = set()
        for item in ast.walk(node):
            if not isinstance(item, ast.Call):
                continue
            func = item.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        return names

    start_calls = called_names(start)
    finished_calls = called_names(finished)

    assert "STSLoadWorker" in start_calls
    assert "STSStore" not in start_calls
    assert "STSStore" in finished_calls
