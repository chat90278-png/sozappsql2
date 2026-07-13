from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from src.services import contract_save_telemetry_runtime_fix as save_runtime_fix
from src.services import perf_tracker
from src.services.sts_database import STSDatabase
from src.ui.dialogs.performance_tracking import (
    PerformanceTrackingDialog,
    format_bytes,
    format_duration,
)


class _FakePerformanceStore:
    def __init__(self, path: Path):
        self.path = path

    def database_stats(self):
        return {
            "table_counts": {
                "contracts": 2,
                "systems": 3,
                "deliveries": 4,
                "components": 5,
            }
        }


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_measure_context_records_success_and_failure(tmp_path: Path, monkeypatch):
    captured = []

    def fake_record(op, data_path, duration_ms, success=True, meta=None):
        captured.append(
            {
                "op": op,
                "path": Path(data_path),
                "duration_ms": float(duration_ms),
                "success": bool(success),
                "meta": dict(meta or {}),
            }
        )
        return True

    monkeypatch.setattr(perf_tracker, "record", fake_record)
    sts_path = tmp_path / "sample.sts"

    with perf_tracker.measure(
        perf_tracker.OP_CACHE_BUILD,
        sts_path,
        meta={"source": "release-gate"},
    ):
        pass

    with pytest.raises(RuntimeError, match="boom"):
        with perf_tracker.measure(perf_tracker.OP_CONTRACT_OPEN, sts_path):
            raise RuntimeError("boom")

    assert [item["success"] for item in captured] == [True, False]
    assert captured[0]["op"] == perf_tracker.OP_CACHE_BUILD
    assert captured[0]["meta"]["source"] == "release-gate"
    assert captured[1]["op"] == perf_tracker.OP_CONTRACT_OPEN
    assert all(item["duration_ms"] >= 0 for item in captured)


def test_record_rejects_invalid_duration_and_protects_reserved_fields(tmp_path: Path):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")

    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, -1) is False
    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, float("nan")) is False
    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, float("inf")) is False
    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, "not-a-number") is False

    assert perf_tracker.record(
        perf_tracker.OP_DB_OPEN,
        sts_path,
        12,
        meta={
            "op": "spoofed",
            "duration_ms": 999,
            "success": False,
            "source_path_key": "spoofed",
            "source": "Release gate",
        },
    )

    rows = [
        json.loads(line)
        for line in perf_tracker._log_path(sts_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["op"] == perf_tracker.OP_DB_OPEN
    assert row["duration_ms"] == 12.0
    assert row["success"] is True
    assert row["source_path_key"] == perf_tracker.source_path_key(sts_path)
    assert row["source"] == "Release gate"


def test_loader_reports_malformed_lines_and_only_accepts_unambiguous_legacy(tmp_path: Path):
    sts_path = tmp_path / "only.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    log_path = perf_tracker._log_path(sts_path)
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": now,
                        "op": perf_tracker.OP_DB_OPEN,
                        "duration_ms": 10,
                        "success": True,
                    }
                ),
                "{not-json",
                json.dumps(["not", "a", "dict"]),
                json.dumps(
                    {
                        "ts": now,
                        "op": perf_tracker.OP_DB_OPEN,
                        "duration_ms": -5,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    status = perf_tracker.load_records_with_status(sts_path, last_n=20)
    assert len(status["records"]) == 1
    assert status["invalid_lines"] == 3
    assert status["legacy_records_included"] is True

    (tmp_path / "second.sts").write_bytes(b"SQLite format 3\x00")
    isolated = perf_tracker.load_records_with_status(sts_path, last_n=20)
    assert isolated["records"] == []
    assert isolated["legacy_records_included"] is False


def test_log_rotation_is_bounded_and_keeps_newest_records(tmp_path: Path, monkeypatch):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    monkeypatch.setattr(perf_tracker, "MAX_LOG_BYTES", 1)
    monkeypatch.setattr(perf_tracker, "LOG_BACKUP_COUNT", 2)

    for duration in (1, 2, 3, 4):
        assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, duration)

    log_path = perf_tracker._log_path(sts_path)
    assert log_path.exists()
    assert log_path.with_name(log_path.name + ".1").exists()
    assert log_path.with_name(log_path.name + ".2").exists()
    assert not log_path.with_name(log_path.name + ".3").exists()

    status = perf_tracker.load_records_with_status(sts_path, last_n=20)
    assert [item["duration_ms"] for item in status["records"]] == [2.0, 3.0, 4.0]
    assert status["log_files_read"] == 3


def test_build_report_orders_newest_first_and_finds_relative_slowest(tmp_path: Path):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    log_path = perf_tracker._log_path(sts_path)
    base = datetime.now().astimezone() - timedelta(minutes=10)
    rows = []
    sequence = [
        (perf_tracker.OP_DB_OPEN, 100, True),
        (perf_tracker.OP_DB_OPEN, 200, True),
        (perf_tracker.OP_DB_OPEN, 300, True),
        (perf_tracker.OP_CONTRACT_OPEN, 700, True),
        (perf_tracker.OP_CONTRACT_OPEN, 800, True),
        (perf_tracker.OP_CONTRACT_OPEN, 900, True),
        (perf_tracker.OP_CONTRACT_SAVE, 50, False),
    ]
    for index, (operation, duration, success) in enumerate(sequence):
        rows.append(
            {
                "schema_version": 2,
                "ts": (base + timedelta(seconds=index)).isoformat(timespec="milliseconds"),
                "op": operation,
                "duration_ms": duration,
                "success": success,
                "source_path_key": perf_tracker.source_path_key(sts_path),
                "source_lineage_key": perf_tracker.source_lineage_key(sts_path),
                "source_file": sts_path.name,
            }
        )
    log_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    report = perf_tracker.build_report(sts_path, range_key="all", last_n=100)

    assert report["records"][0]["op"] == perf_tracker.OP_CONTRACT_SAVE
    assert report["records"][-1]["op"] == perf_tracker.OP_DB_OPEN
    assert report["summary"]["measurement_count"] == 7
    assert report["summary"]["failure_count"] == 1
    assert report["summary"]["failure_rate"] == pytest.approx(14.29, abs=0.01)
    assert report["summary"]["slowest_operation"] == perf_tracker.OP_CONTRACT_OPEN
    assert report["stats"][perf_tracker.OP_CONTRACT_SAVE]["status"] == "failed"


def test_real_sts_database_open_produces_db_measurement(tmp_path: Path, monkeypatch):
    captured = []

    def fake_record(op, data_path, duration_ms, success=True, meta=None):
        captured.append((op, Path(data_path), bool(success), dict(meta or {})))
        return True

    monkeypatch.setattr(perf_tracker, "record", fake_record)
    sts_path = tmp_path / "created.sts"
    database = STSDatabase(sts_path, source="Release Gate")
    database.close()

    db_rows = [row for row in captured if row[0] == perf_tracker.OP_DB_OPEN]
    assert len(db_rows) == 1
    assert db_rows[0][1] == sts_path
    assert db_rows[0][2] is True
    assert db_rows[0][3]["database_existed"] is False
    assert sts_path.exists()


def test_dialog_operation_search_filters_and_refresh_pick_up_new_record(tmp_path: Path):
    app = _app()
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_OPEN,
        sts_path,
        250,
        meta={"platform": "AKINCI", "contract_no": "A-1", "source": "Ana uygulama"},
    )
    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_SAVE,
        sts_path,
        350,
        meta={"platform": "HÜRJET", "contract_no": "B-2", "source": "Sözleşme detay ekranı"},
    )

    dialog = PerformanceTrackingDialog(_FakePerformanceStore(sts_path))
    dialog.show()
    app.processEvents()
    assert dialog.table.rowCount() == 2

    save_index = dialog.operation_combo.findData(perf_tracker.OP_CONTRACT_SAVE)
    dialog.operation_combo.setCurrentIndex(save_index)
    app.processEvents()
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "Sözleşme kaydetme"

    dialog.search.setText("B-2")
    app.processEvents()
    assert dialog.table.rowCount() == 1
    dialog.search.setText("yok")
    app.processEvents()
    assert dialog.table.isHidden()
    assert dialog.empty_label.isVisible()

    dialog.search.clear()
    dialog.operation_combo.setCurrentIndex(0)
    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_LIST_LOAD,
        sts_path,
        80,
        meta={"row_count": 8, "source": "Release gate"},
    )
    dialog.refresh_all()
    app.processEvents()
    assert dialog.table.rowCount() == 3
    assert dialog.summary_values["measurements"].text() == "3"
    assert dialog.refresh_button.isEnabled()

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_dialog_read_failure_is_visible_and_refresh_is_reenabled(tmp_path: Path, monkeypatch):
    app = _app()
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")

    def fail_report(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(perf_tracker, "build_report", fail_report)
    dialog = PerformanceTrackingDialog(_FakePerformanceStore(sts_path))
    dialog.show()
    app.processEvents()

    assert dialog.refresh_button.isEnabled()
    assert dialog.empty_label.isVisible()
    assert "okunamadı" in dialog.empty_label.text().casefold()
    assert "permission denied" in dialog.empty_label.text()

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_save_runtime_patch_is_idempotent_nested_and_restores_store_method(tmp_path: Path, monkeypatch):
    captured = []

    def fake_record(op, data_path, duration_ms, success=True, meta=None):
        captured.append(
            {
                "op": op,
                "path": Path(data_path),
                "success": bool(success),
                "meta": dict(meta or {}),
            }
        )
        return True

    monkeypatch.setattr(save_runtime_fix.perf_tracker, "record", fake_record)

    class FakeStore:
        def __init__(self):
            self.path = tmp_path / "sample.sts"
            self.entries = 0

        @contextmanager
        def batch_save(self):
            self.entries += 1
            yield

    class FakeContractWindow:
        def __init__(self):
            self.store = FakeStore()
            self.ci = SimpleNamespace(platform="AKINCI", no="141414")
            self._context_cache = {
                ("AKINCI", "141414", "Ana Sözleşme"): {},
                ("AKINCI", "141414", "SD-1"): {},
            }

        def _save_context_family(self):
            with self.store.batch_save():
                with self.store.batch_save():
                    pass
            return True

    save_runtime_fix._patch_contract_work_window_class(FakeContractWindow)
    save_runtime_fix._patch_contract_work_window_class(FakeContractWindow)
    window = FakeContractWindow()

    assert window._save_context_family() is True
    assert "batch_save" not in window.store.__dict__
    assert len(captured) == 1
    assert captured[0]["op"] == perf_tracker.OP_CONTRACT_SAVE
    assert captured[0]["success"] is True
    assert captured[0]["meta"]["context_count"] == 2

    assert window._save_context_family() is True
    assert len(captured) == 2


def test_human_readable_format_boundaries():
    assert format_duration(999) == "999 ms"
    assert format_duration(1000) == "1.0 sn"
    assert format_duration(60_000) == "1 dk 0 sn"
    assert format_duration(3_600_000) == "1 sa 0 dk"
    assert format_duration(None) == "-"

    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024**2) == "1.0 MB"
    assert format_bytes(1024**3) == "1.00 GB"
