from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.services import perf_tracker
from src.ui.dialogs.performance_tracking import PerformanceTrackingDialog


class FakePerformanceStore:
    def __init__(self, path: Path):
        self.path = path

    def database_stats(self):
        return {
            "table_counts": {
                "contracts": 4,
                "systems": 11,
                "deliveries": 16,
                "components": 9,
                "activity_logs": 35,
            }
        }


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_performance_dialog_uses_real_telemetry_and_business_counts(tmp_path: Path):
    app = _application()
    sts_path = tmp_path / "STS-A1__v001__2026-07-13_08-00.sts"
    sts_path.write_bytes(b"SQLite format 3\x00" + b"x" * 2048)

    samples = {
        perf_tracker.OP_DB_OPEN: [120, 150, 180],
        perf_tracker.OP_CONTRACT_LIST_LOAD: [220, 260, 300],
        perf_tracker.OP_CONTRACT_OPEN: [320, 350, 400],
        perf_tracker.OP_CONTRACT_SAVE: [500, 550, 600],
    }
    for operation, durations in samples.items():
        for duration in durations:
            assert perf_tracker.record(operation, sts_path, duration)

    dialog = PerformanceTrackingDialog(FakePerformanceStore(sts_path))
    dialog.show()
    app.processEvents()

    assert dialog.metric_cards[perf_tracker.OP_DB_OPEN].value.text() != "-"
    assert dialog.metric_cards[perf_tracker.OP_CONTRACT_SAVE].badge.text() == "Normal"
    assert dialog.summary_values["contracts"].text() == "4"
    assert dialog.summary_values["systems"].text() == "11"
    assert dialog.summary_values["deliveries"].text() == "16"
    assert dialog.summary_values["measurements"].text() == "12"
    assert dialog.table.rowCount() == 12
    assert dialog.table.columnCount() == 6

    preview_path = str(os.environ.get("PERFORMANCE_PREVIEW_PATH") or "").strip()
    if preview_path:
        target = Path(preview_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        assert dialog.grab().save(str(target), "PNG")
        assert target.exists() and target.stat().st_size > 0

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_performance_dialog_filters_failed_measurements(tmp_path: Path):
    app = _application()
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")

    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_OPEN,
        sts_path,
        250,
        success=True,
        meta={"contract_no": "OK-1"},
    )
    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_OPEN,
        sts_path,
        1800,
        success=False,
        meta={"contract_no": "FAIL-1", "error": "test error"},
    )

    dialog = PerformanceTrackingDialog(FakePerformanceStore(sts_path))
    failed_index = dialog.status_combo.findData("failed")
    dialog.status_combo.setCurrentIndex(failed_index)
    app.processEvents()

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == "Başarısız"
    assert "FAIL-1" in dialog.table.item(0, 4).text()

    dialog.close()
    dialog.deleteLater()
    app.processEvents()
