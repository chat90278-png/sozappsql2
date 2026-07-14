from __future__ import annotations

import importlib
import json
import os
import inspect
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from src.models.app_models import ContractInfo
from src.services import contract_save_telemetry_runtime_fix as runtime_fix
from src.services import perf_tracker
from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.sts_database import CURRENT_SCHEMA_VERSION, read_sts_schema_version
from src.services.sts_store import STSStore
from src.ui.dialogs.activity_logs import ActivityLogDialog
from src.ui.dialogs.performance_tracking import PerformanceTrackingDialog
from src.ui.main_window import MainWindow
from src.ui.widgets.contract_status_summary import ContractStatusSummaryWidget
from tests.qt_wait_helpers import wait_until_ready


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _contract(no: str = "P5-001", *, note: str = "") -> ContractInfo:
    return ContractInfo(
        no=no,
        platform="AKINCI",
        user="",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="",
        t0_date="",
        t0_months=0,
        completion_date="",
        status="PLAN",
        note=note,
        acceptance_date="",
    )


def _activity_count(store: STSStore, action: str | None = None) -> int:
    if action:
        return int(store.db.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE action=?", (action,)).fetchone()[0])
    return int(store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0])


def _perf_records(path: Path):
    return perf_tracker.load_records(path, last_n=100, range_key="all")


def test_app_import_installs_telemetry_without_removing_activity_history():
    code = r"""
import app
from src.services import contract_save_telemetry_runtime_fix as runtime_fix
from src.ui.main_window import MainWindow
from src.ui.contract.contract_work_window import ContractWorkWindow
assert callable(app.install_contract_save_telemetry_fix)
assert getattr(MainWindow, runtime_fix._MAIN_PATCH_FLAG) is True
assert getattr(ContractWorkWindow, runtime_fix._WORK_PATCH_FLAG) is True
assert callable(MainWindow.open_activity_logs)
assert callable(MainWindow.open_performance_tracking)
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")


def test_main_window_exposes_both_menu_actions():
    source = inspect.getsource(MainWindow._build_top_actions_menu)
    refresh_source = inspect.getsource(MainWindow._refresh_permission_actions)
    assert '"Performans İzleme"' in source
    assert '"İşlem Geçmişi"' in source
    assert "performance_tracking_action" in refresh_source
    assert "activity_logs_action" in refresh_source
    assert callable(MainWindow.open_activity_logs)
    assert callable(MainWindow.open_performance_tracking)


def test_direct_contract_create_writes_one_perf_record_and_activity_operation(tmp_path):
    store = STSStore(tmp_path / "direct.sts", actor_context={"id": 7, "full_name": "Ayşe"}, session_id="p5-session")

    class IntegratedMain:
        def __init__(self):
            self.store = store

        def new_contract(self):
            return self.store.write_contract(_contract(), [], {})

    runtime_fix._patch_main_window_class(IntegratedMain)
    try:
        contract_id = IntegratedMain().new_contract()
        assert contract_id > 0
        records = [r for r in _perf_records(store.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]
        assert len(records) == 1
        assert records[0]["success"] is True
        assert records[0]["save_mode"] == "create"
        rows = store.db.conn.execute("SELECT action,operation_id,session_id FROM activity_logs ORDER BY id").fetchall()
        assert [row["action"] for row in rows] == ["contract_created"]
        assert rows[0]["operation_id"]
        assert rows[0]["session_id"] == "p5-session"
    finally:
        store.db.close()


def test_failed_direct_save_records_failure_and_rolls_back_activity(tmp_path, monkeypatch):
    store = STSStore(tmp_path / "direct-fail.sts", actor="Ayşe")
    original = store._write_contract_in_transaction

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("integrated failure")

    monkeypatch.setattr(store, "_write_contract_in_transaction", fail_after_write)

    class IntegratedMain:
        def __init__(self):
            self.store = store

        def new_contract(self):
            return self.store.write_contract(_contract("P5-FAIL"), [], {})

    runtime_fix._patch_main_window_class(IntegratedMain)
    try:
        with pytest.raises(RuntimeError, match="integrated failure"):
            IntegratedMain().new_contract()
        assert store.db.conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 0
        assert _activity_count(store) == 0
        records = [r for r in _perf_records(store.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]
        assert len(records) == 1
        assert records[0]["success"] is False
    finally:
        store.db.close()


def test_telemetry_exception_never_breaks_business_save(tmp_path, monkeypatch):
    store = STSStore(tmp_path / "telemetry-error.sts", actor="Ayşe")
    monkeypatch.setattr(runtime_fix.perf_tracker, "record", lambda *a, **k: (_ for _ in ()).throw(OSError("log down")))

    class IntegratedMain:
        def __init__(self):
            self.store = store

        def new_contract(self):
            return self.store.write_contract(_contract("P5-SAFE"), [], {})

    runtime_fix._patch_main_window_class(IntegratedMain)
    try:
        assert IntegratedMain().new_contract() > 0
        assert store.db.conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 1
        assert _activity_count(store, "contract_created") == 1
    finally:
        store.db.close()


def test_family_save_is_measured_once_and_child_activity_shares_operation(tmp_path):
    store = STSStore(tmp_path / "family.sts", actor_context={"id": 8, "full_name": "Mehmet"})

    class IntegratedFamilyWindow:
        def __init__(self):
            self.store = store
            self.ci = _contract("P5-F1")
            self._context_cache = {"one": {}, "two": {}}

        def _save_context_family(self):
            with self.store.activity_operation(name="family-save"):
                with self.store.batch_save():
                    self.store.write_contract(_contract("P5-F1"), [], {})
                    self.store.write_contract(_contract("P5-F2"), [], {})
            return True

    runtime_fix._patch_contract_work_window_class(IntegratedFamilyWindow)
    try:
        assert IntegratedFamilyWindow()._save_context_family() is True
        records = [r for r in _perf_records(store.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]
        assert len(records) == 1
        assert records[0]["save_mode"] == "family"
        rows = store.db.conn.execute("SELECT action,operation_id FROM activity_logs ORDER BY id").fetchall()
        assert [row["action"] for row in rows] == ["contract_created", "contract_created"]
        assert len({row["operation_id"] for row in rows}) == 1
    finally:
        store.db.close()


def test_failed_family_save_rolls_back_business_and_activity(tmp_path):
    store = STSStore(tmp_path / "family-fail.sts", actor="Ayşe")

    class IntegratedFamilyWindow:
        def __init__(self):
            self.store = store
            self.ci = _contract("P5-FAMILY-FAIL")
            self._context_cache = {"one": {}}

        def _save_context_family(self):
            with self.store.activity_operation(name="family-save"):
                with self.store.batch_save():
                    self.store.write_contract(self.ci, [], {})
                    raise RuntimeError("family rollback")

    runtime_fix._patch_contract_work_window_class(IntegratedFamilyWindow)
    try:
        with pytest.raises(RuntimeError, match="family rollback"):
            IntegratedFamilyWindow()._save_context_family()
        assert store.db.conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 0
        assert _activity_count(store) == 0
        record = [r for r in _perf_records(store.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE][0]
        assert record["success"] is False
    finally:
        store.db.close()


def test_perf_metadata_does_not_copy_into_activity_payload(tmp_path):
    store = STSStore(tmp_path / "separation.sts", actor="Ayşe")

    class IntegratedMain:
        def __init__(self):
            self.store = store

        def new_contract(self):
            return self.store.write_contract(_contract("P5-SEP"), [], {})

    runtime_fix._patch_main_window_class(IntegratedMain)
    try:
        IntegratedMain().new_contract()
        serialized = json.dumps(dict(store.db.conn.execute("SELECT * FROM activity_logs").fetchone()), ensure_ascii=False)
        assert "duration_ms" not in serialized
        assert "save_mode" not in serialized
        assert "source_path_key" not in serialized
    finally:
        store.db.close()


def test_activity_sanitizer_data_is_not_written_to_perf_metadata(tmp_path):
    path = tmp_path / "metadata.sts"
    store = STSStore(path, actor_context={"id": 4, "full_name": "Ali", "password": "hidden"})
    try:
        runtime_fix._record_save(store, 12.5, success=True, source="Test", save_mode="direct", platform="AKINCI", contract_no="P5-META")
        raw = perf_tracker._log_path(path).read_text(encoding="utf-8")
        assert "hidden" not in raw
        assert "password" not in raw
        assert "P5-META" in raw
    finally:
        store.db.close()


def test_noop_save_keeps_activity_suppression_while_perf_still_measures(tmp_path):
    store = STSStore(tmp_path / "noop.sts", actor="Ayşe")
    ci = _contract("P5-NOOP")

    class IntegratedMain:
        def __init__(self):
            self.store = store

        def new_contract(self):
            return self.store.write_contract(ci, [], {})

    runtime_fix._patch_main_window_class(IntegratedMain)
    try:
        window = IntegratedMain()
        window.new_contract()
        window.new_contract()
        assert _activity_count(store, "contract_created") == 1
        assert _activity_count(store, "contract_updated") == 0
        assert len([r for r in _perf_records(store.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]) == 2
    finally:
        store.db.close()


def test_telemetry_never_creates_activity_technical_events(tmp_path):
    store = STSStore(tmp_path / "no-technical-event.sts", actor="Ayşe")
    try:
        runtime_fix._record_save(store, 8.0, success=True, source="Test", save_mode="direct")
        assert _activity_count(store) == 0
        assert store.db.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE category='TECHNICAL'").fetchone()[0] == 0
    finally:
        store.db.close()


def test_activity_and_performance_dialogs_open_in_same_session(qapp, tmp_path):
    store = STSStore(tmp_path / "dialogs.sts", actor_context={"is_admin": True, "is_active": 1, "full_name": "Admin"})
    store.write_contract(_contract("P5-DLG"), [], {})
    runtime_fix._record_save(store, 5.0, success=True, source="Test", save_mode="direct")
    access = ActivityHistoryAccess(True, frozenset({"USER", "MANAGEMENT", "TECHNICAL"}), True, True, True)
    activity = ActivityLogDialog(store, access=access)
    performance = PerformanceTrackingDialog(store)
    try:
        activity.show(); performance.show(); qapp.processEvents()
        assert activity.isVisible()
        assert performance.isVisible()
        assert activity.objectName() == "activityHistoryDialog"
        assert activity.styleSheet() != performance.styleSheet()
    finally:
        activity.close(); performance.close(); store.db.close()


def test_dialog_qss_does_not_leak_to_generic_dialog(qapp, tmp_path):
    store = STSStore(tmp_path / "qss.sts", actor="Ayşe")
    access = ActivityHistoryAccess(True, frozenset({"USER", "MANAGEMENT"}), False, False, False)
    activity = ActivityLogDialog(store, access=access)
    performance = PerformanceTrackingDialog(store)
    generic = QDialog()
    try:
        assert "activityHistoryDialog" in activity.styleSheet()
        assert "activityHistoryDialog" not in performance.styleSheet()
        assert generic.styleSheet() == ""
    finally:
        activity.close(); performance.close(); generic.close(); store.db.close()


def test_contract_status_summary_keeps_main_fixed_geometry(qapp):
    widget = ContractStatusSummaryWidget()
    try:
        assert (widget.width(), widget.height()) == (460, 112)
        assert "QFrame#contractStatusSummaryWidget:hover" in widget.styleSheet()
    finally:
        widget.close()


def test_analysis_readiness_helper_returns_for_ready_window(qapp):
    class ReadyWindow:
        _item_ids = ["overview"]
        _payload = {"contracts": []}

        def __init__(self):
            self.navigation = SimpleNamespace(count=lambda: 1)
            self.stack = SimpleNamespace(count=lambda: 1)

        def isVisible(self):
            return True

        def show(self):
            return None

    wait_until_ready(ReadyWindow(), qapp, timeout_ms=100)


def test_share_merge_dialog_and_confirmation_paths_remain_importable(qapp):
    from src.ui.contract.contract_work_window import ContractWorkWindow
    from src.ui.dialogs.share_merge_dialog import ShareMergeDialog

    assert issubclass(ShareMergeDialog, QDialog)
    assert callable(ContractWorkWindow._confirm_active_share_creation)


def test_performance_records_remain_isolated_by_sts_source(tmp_path):
    first = STSStore(tmp_path / "first.sts", actor="A")
    second = STSStore(tmp_path / "second.sts", actor="B")
    try:
        runtime_fix._record_save(first, 1.0, success=True, source="Test", save_mode="direct", contract_no="FIRST")
        runtime_fix._record_save(second, 2.0, success=True, source="Test", save_mode="direct", contract_no="SECOND")
        first_records = [r for r in _perf_records(first.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]
        second_records = [r for r in _perf_records(second.path) if r["op"] == perf_tracker.OP_CONTRACT_SAVE]
        assert [r["contract_no"] for r in first_records] == ["FIRST"]
        assert [r["contract_no"] for r in second_records] == ["SECOND"]
    finally:
        first.db.close(); second.db.close()



def test_multiplatform_adapter_commits_before_external_share_metadata_write():
    code = r"""
from pathlib import Path
from tempfile import TemporaryDirectory
from src.models.app_models import ContractInfo
from src.services.multiplatform_contract_persistence import install_multiplatform_contract_persistence_fix
from src.services.share_package_service import write_share_metadata, read_share_metadata
from src.services.sts_store import STSStore
install_multiplatform_contract_persistence_fix()
with TemporaryDirectory() as directory:
    path = Path(directory) / 'share.sts'
    store = STSStore(path, actor='Test')
    ci = ContractInfo(no='P5-SHARE', platform='AKINCI', user='', yi_yd='Yİ', contract_type='Ana Sözleşme', signature_date='', t0_date='', t0_months=0, completion_date='')
    store.write_contract(ci, [], {})
    assert store.db.conn.in_transaction is False
    write_share_metadata(path, {'share_mode': 'true', 'contract_id': '1'})
    assert read_share_metadata(path)['share_mode'] == 'true'
    store.db.close()
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")

def test_schema_version_remains_19_after_integration(tmp_path):
    store = STSStore(tmp_path / "schema.sts")
    try:
        assert CURRENT_SCHEMA_VERSION == 19
        assert read_sts_schema_version(store.path) == 19
    finally:
        store.db.close()


def test_runtime_patch_is_idempotent_for_real_classes():
    code = r"""
from src.services import contract_save_telemetry_runtime_fix as runtime_fix
from src.ui.main_window import MainWindow
from src.ui.contract.contract_work_window import ContractWorkWindow
runtime_fix.install_contract_save_telemetry_fix()
first_main = MainWindow.new_contract
first_family = ContractWorkWindow._save_context_family
runtime_fix.install_contract_save_telemetry_fix()
assert MainWindow.new_contract is first_main
assert ContractWorkWindow._save_context_family is first_family
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")


def test_perf_tracker_rejects_invalid_duration_without_business_side_effect(tmp_path):
    store = STSStore(tmp_path / "invalid-duration.sts", actor="Ayşe")
    try:
        assert perf_tracker.record(perf_tracker.OP_CONTRACT_SAVE, store.path, float("nan")) is False
        store.write_contract(_contract("P5-VALID"), [], {})
        assert store.db.conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 1
        assert _activity_count(store, "contract_created") == 1
    finally:
        store.db.close()
