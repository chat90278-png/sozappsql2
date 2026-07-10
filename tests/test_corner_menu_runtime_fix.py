# -*- coding: utf-8 -*-
"""Regression tests for the compact corner-menu runtime hardening."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_app_installs_corner_menu_runtime_fix() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = False
    called = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.ui.corner_menu_runtime_fix":
            imported = any(alias.name == "install_corner_menu_runtime_fix" for alias in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called = called or node.func.id == "install_corner_menu_runtime_fix"
    assert imported
    assert called


def test_corner_menu_fix_removes_graphics_effect_and_preopen_callback() -> None:
    source = (ROOT / "src" / "ui" / "corner_menu_runtime_fix.py").read_text(encoding="utf-8")
    assert "before_open=None" in source
    assert "setGraphicsEffect(None)" in source
    assert "shadow_path = QPainterPath(path)" in source


def test_corner_menu_fix_detaches_old_rows_before_submenu_measurement() -> None:
    source = (ROOT / "src" / "ui" / "corner_menu_runtime_fix.py").read_text(encoding="utf-8")
    assert "CornerMenuPanel._clear_rows = clear_panel_rows" in source
    assert "widget.setParent(None)" in source
    assert "self._layout.invalidate()" in source
