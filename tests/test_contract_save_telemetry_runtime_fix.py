from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from src.services import contract_save_telemetry_runtime_fix as runtime_fix
from src.services import perf_tracker


def _capture_records(monkeypatch):
    records = []

    def fake_record(op, data_path, duration_ms, success=True, meta=None):
        records.append(
            {
                "op": op,
                "data_path": Path(data_path),
                "duration_ms": float(duration_ms),
                "success": bool(success),
                "meta": dict(meta or {}),
            }
        )
        return True

    monkeypatch.setattr(runtime_fix.perf_tracker, "record", fake_record)
    return records


def test_new_contract_direct_write_is_measured(tmp_path: Path, monkeypatch):
    records = _capture_records(monkeypatch)

    class FakeStore:
        def __init__(self):
            self.path = tmp_path / "sample.sts"
            self.calls = 0

        def write_contract(self, ci, systems, deliveries):
            self.calls += 1
            return 42

    class FakeMainWindow:
        def __init__(self):
            self.store = FakeStore()

        def new_contract(self):
            ci = SimpleNamespace(platform="AKINCI", no="141414")
            return self.store.write_contract(ci, [], {})

    runtime_fix._patch_main_window_class(FakeMainWindow)
    window = FakeMainWindow()

    assert window.new_contract() == 42
    assert window.store.calls == 1
    assert len(records) == 1
    assert records[0]["op"] == perf_tracker.OP_CONTRACT_SAVE
    assert records[0]["success"] is True
    assert records[0]["meta"]["save_mode"] == "create"
    assert records[0]["meta"]["platform"] == "AKINCI"
    assert records[0]["meta"]["contract_no"] == "141414"


def test_family_transaction_is_measured_once(tmp_path: Path, monkeypatch):
    records = _capture_records(monkeypatch)

    class FakeStore:
        def __init__(self):
            self.path = tmp_path / "sample.sts"
            self.commits = 0

        @contextmanager
        def batch_save(self):
            yield
            self.commits += 1

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
                pass
            return True

    runtime_fix._patch_contract_work_window_class(FakeContractWindow)
    window = FakeContractWindow()

    assert window._save_context_family() is True
    assert window.store.commits == 1
    assert len(records) == 1
    assert records[0]["op"] == perf_tracker.OP_CONTRACT_SAVE
    assert records[0]["success"] is True
    assert records[0]["meta"]["save_mode"] == "family"
    assert records[0]["meta"]["context_count"] == 2


def test_validation_return_without_transaction_is_not_counted(tmp_path: Path, monkeypatch):
    records = _capture_records(monkeypatch)

    class FakeStore:
        path = tmp_path / "sample.sts"

        @contextmanager
        def batch_save(self):
            yield

    class FakeContractWindow:
        def __init__(self):
            self.store = FakeStore()
            self.ci = SimpleNamespace(platform="AKINCI", no="141414")
            self._context_cache = {}

        def _save_context_family(self):
            return True

    runtime_fix._patch_contract_work_window_class(FakeContractWindow)
    window = FakeContractWindow()

    assert window._save_context_family() is True
    assert records == []


def test_failed_family_transaction_is_recorded_as_failure(tmp_path: Path, monkeypatch):
    records = _capture_records(monkeypatch)

    class FakeStore:
        path = tmp_path / "sample.sts"

        @contextmanager
        def batch_save(self):
            yield

    class FakeContractWindow:
        def __init__(self):
            self.store = FakeStore()
            self.ci = SimpleNamespace(platform="AKINCI", no="141414")
            self._context_cache = {}

        def _save_context_family(self):
            with self.store.batch_save():
                raise RuntimeError("save failed")

    runtime_fix._patch_contract_work_window_class(FakeContractWindow)
    window = FakeContractWindow()

    try:
        window._save_context_family()
    except RuntimeError as exc:
        assert str(exc) == "save failed"
    else:
        raise AssertionError("Expected save failure")

    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["meta"]["error"] == "save failed"
