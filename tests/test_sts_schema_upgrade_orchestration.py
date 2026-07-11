from __future__ import annotations

import ast
from pathlib import Path


MAIN_WINDOW_PATH = Path("src/ui/main_window.py")


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    module = ast.parse(MAIN_WINDOW_PATH.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"method not found: {class_name}.{method_name}")


def _called_names(method: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def test_main_window_keeps_schema_upgrade_at_user_file_open_boundary():
    start_load_calls = _called_names(_method_node("MainWindow", "start_sts_load"))
    load_finished_calls = _called_names(
        _method_node("MainWindow", "_on_sts_load_finished")
    )
    start_index_calls = _called_names(
        _method_node("MainWindow", "_start_sts_index_build")
    )

    assert "STSLoadWorker" in start_load_calls
    assert "STSStore" not in start_load_calls
    assert "STSIndexWorker" not in start_load_calls

    assert "STSStore" in load_finished_calls
    assert "_start_sts_index_build" in load_finished_calls

    assert "STSIndexWorker" in start_index_calls


def test_sts_load_worker_is_the_only_upgrade_entrypoint_in_open_sequence():
    worker_source = Path("src/workers/sts_load_worker.py").read_text(encoding="utf-8")

    assert (
        "from src.services.sts_schema_upgrade_gate import upgrade_sts_file"
        in worker_source
    )
    assert "upgrade_result = upgrade_sts_file(" in worker_source
