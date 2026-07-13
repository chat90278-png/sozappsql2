from __future__ import annotations

import time

import pytest
from PySide6.QtTest import QTest


def wait_until_ready(window, qt_app, timeout_ms: int = 10_000) -> None:
    """Boundedly drain the Qt event loop until AnalysisCenterWindow is rendered."""
    if not window.isVisible():
        window.show()
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_state: dict[str, object] = {}
    while time.monotonic() < deadline:
        qt_app.processEvents()
        item_ids = list(getattr(window, "_item_ids", []) or [])
        navigation = getattr(window, "navigation", None)
        stack = getattr(window, "stack", None)
        payload = getattr(window, "_payload", None)
        nav_count = navigation.count() if navigation is not None else -1
        stack_count = stack.count() if stack is not None else -1
        last_state = {
            "item_ids": item_ids,
            "navigation_count": nav_count,
            "stack_count": stack_count,
            "payload_ready": bool(payload),
        }
        if item_ids and nav_count == len(item_ids) and stack_count == len(item_ids) and payload:
            return
        QTest.qWait(10)
    pytest.fail(
        f"AnalysisCenterWindow did not become ready within {timeout_ms} ms; last_state={last_state}"
    )
