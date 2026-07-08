from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
try:
    from PySide6.QtWidgets import QFileDialog
except ImportError as exc:
    pytest.skip(f"PySide6 Qt runtime unavailable: {exc}", allow_module_level=True)


def test_window_orchestration_requires_qt_runtime():
    # Real ContractWorkWindow orchestration tests live behind the Qt runtime gate;
    # this assertion prevents an empty module when Qt is available.
    assert QFileDialog is not None
