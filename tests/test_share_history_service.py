from __future__ import annotations

import uuid
import pytest

from src.domain.contract_snapshot import build_contract_snapshot, hash_contract_snapshot
from src.models.app_models import ContractInfo
from src.models.share_models import (
    SHARE_FORMAT_V2,
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
    SharePackageRegistryEntry,
)
from src.services.share_history_service import list_contract_share_history
from src.ui.presenters.share_history_presenter import present_merge_result
from src.services.sts_store import STSStore


def _contract(no):
    return ContractInfo(no=no, platform="AKINCI", user="SSB", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="2026-01-01", t0_date="2026-01-02", t0_months=1, completion_date="2026-02-02", status="PLAN")


def _register(store, contract_id, merge_uid, package_id, created_at, status=SHARE_STATUS_OPEN, filename="share.sts"):
    store.register_share_package(SharePackageRegistryEntry(
        share_package_id=package_id,
        contract_id=contract_id,
        contract_merge_uid=merge_uid,
        source_contract_revision=1,
        permission_mode="edit",
        share_format_version=SHARE_FORMAT_V2,
        snapshot_format_version=1,
        base_snapshot_sha256="sha-" + package_id,
        created_at=created_at,
        created_by_staff_id=42,
        created_by_username="tester",
        created_by_full_name="Test User",
        exported_filename=filename,
        status=status,
    ))


def _snapshot_hash(conn, contract_id):
    return hash_contract_snapshot(build_contract_snapshot(conn, contract_id))


def test_history_service_filters_current_contract_and_orders_deterministically(tmp_path):
    store = STSStore(tmp_path / "history.sts")
    cid1 = store.write_contract(_contract("C-1"), [], {})
    cid2 = store.write_contract(_contract("C-2"), [], {})
    uid1 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid1,)).fetchone()[0]
    uid2 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid2,)).fetchone()[0]
    _register(store, cid1, uid1, "pkg-old", "2026-07-07T10:00:00", SHARE_STATUS_OPEN, "old.sts")
    _register(store, cid1, uid1, "pkg-new-b", "2026-07-08T10:00:00", SHARE_STATUS_MERGED, "new-b.sts")
    _register(store, cid1, uid1, "pkg-new-a", "2026-07-08T10:00:00", SHARE_STATUS_RETURNED, "new-a.sts")
    _register(store, cid2, uid2, "pkg-other", "2026-07-09T10:00:00", SHARE_STATUS_OPEN, "other.sts")

    rows = list_contract_share_history(store, uid1)

    assert [r.share_package_id for r in rows] == ["pkg-new-b", "pkg-new-a", "pkg-old"]
    assert {r.contract_merge_uid for r in rows} == {uid1}


def test_history_service_reads_all_lifecycle_statuses_and_legacy_nulls(tmp_path):
    store = STSStore(tmp_path / "statuses.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    for idx, status in enumerate([SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED, SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED]):
        _register(store, cid, uid, f"pkg-{idx}", f"2026-07-0{idx+1}T00:00:00", status, "")
    store.db.conn.execute("UPDATE share_packages SET last_imported_at=NULL, last_imported_by_staff_id=NULL WHERE share_package_id='pkg-0'")
    store.db.conn.commit()

    rows = list_contract_share_history(store, uid)

    assert {r.status for r in rows} == {SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED, SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED}
    assert next(r for r in rows if r.share_package_id == "pkg-0").last_imported_at == ""


def test_history_read_and_refresh_are_no_write_operations(tmp_path):
    store = STSStore(tmp_path / "readonly.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, str(uuid.uuid4()), "2026-07-08T00:00:00")
    before_snapshot = _snapshot_hash(store.db.conn, cid)
    before_rows = [dict(r) for r in store.db.conn.execute("SELECT * FROM share_packages ORDER BY id").fetchall()]

    first = list_contract_share_history(store, uid)
    second = list_contract_share_history(store, uid)

    assert len(first) == len(second) == 1
    assert _snapshot_hash(store.db.conn, cid) == before_snapshot
    assert [dict(r) for r in store.db.conn.execute("SELECT * FROM share_packages ORDER BY id").fetchall()] == before_rows


def test_history_service_handles_zero_and_large_package_sets(tmp_path):
    store = STSStore(tmp_path / "large.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    assert list_contract_share_history(store, uid) == []
    for idx in range(500):
        _register(store, cid, uid, f"pkg-{idx:03d}", f"2026-07-{(idx % 28) + 1:02d}T{idx % 24:02d}:00:00", SHARE_STATUS_OPEN, f"share-{idx}.sts")

    rows = list_contract_share_history(store, uid)

    assert len(rows) == 500
    assert rows == sorted(rows, key=lambda r: (r.created_at or "", r.share_package_id or ""), reverse=True)


def test_history_service_reads_persisted_merge_result_fields_and_nulls(tmp_path):
    store = STSStore(tmp_path / "result-fields.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-result", "2026-07-08T00:00:00", SHARE_STATUS_MERGED)
    _register(store, cid, uid, "pkg-legacy", "2026-07-07T00:00:00", SHARE_STATUS_MERGED)
    store.db.conn.execute(
        "UPDATE share_packages SET merge_result_operations_applied=?, merge_result_operations_skipped=?, merged_at=? WHERE share_package_id=?",
        (5, 0, "2026-07-08 09:10:00", "pkg-result"),
    )
    store.db.conn.commit()
    store.db.close()

    reopened = STSStore(tmp_path / "result-fields.sts")
    rows = list_contract_share_history(reopened, uid)

    result = next(r for r in rows if r.share_package_id == "pkg-result")
    assert result.merge_result_operations_applied == 5
    assert result.merge_result_operations_skipped == 0
    assert result.merged_at == "2026-07-08 09:10:00"
    legacy = next(r for r in rows if r.share_package_id == "pkg-legacy")
    assert legacy.merge_result_operations_applied is None
    assert legacy.merge_result_operations_skipped is None


def test_history_service_treats_malformed_result_counts_as_unavailable(tmp_path):
    store = STSStore(tmp_path / "malformed-result-fields.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-bad", "2026-07-08T00:00:00", SHARE_STATUS_MERGED)
    store.db.conn.execute("UPDATE share_packages SET merge_result_operations_applied=-1, merge_result_operations_skipped='bad' WHERE share_package_id='pkg-bad'")
    store.db.conn.commit()

    row = list_contract_share_history(store, uid)[0]

    assert row.merge_result_operations_applied is None
    assert row.merge_result_operations_skipped is None


def test_history_service_roundtrips_legacy_unknown_and_recorded_zero_results(tmp_path):
    store = STSStore(tmp_path / "zero-vs-legacy.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-legacy", "2026-07-07T00:00:00", SHARE_STATUS_MERGED)
    _register(store, cid, uid, "pkg-zero", "2026-07-08T00:00:00", SHARE_STATUS_MERGED)
    store.db.conn.execute(
        "UPDATE share_packages SET merge_result_operations_applied=0, merge_result_operations_skipped=0, merged_at='2026-07-08 09:10:00' WHERE share_package_id='pkg-zero'"
    )
    store.db.conn.commit()
    store.db.close()

    reopened = STSStore(tmp_path / "zero-vs-legacy.sts")
    rows = list_contract_share_history(reopened, uid)

    legacy = next(r for r in rows if r.share_package_id == "pkg-legacy")
    assert legacy.merge_result_operations_applied is None
    assert legacy.merge_result_operations_skipped is None
    assert present_merge_result(legacy).recorded is False

    zero = next(r for r in rows if r.share_package_id == "pkg-zero")
    assert zero.merge_result_operations_applied == 0
    assert zero.merge_result_operations_skipped == 0
    zero_presentation = present_merge_result(zero)
    assert zero_presentation.recorded is True
    assert "yeni değişiklik yoktu" in zero_presentation.summary_label


def test_history_service_parses_numeric_strings_but_rejects_bad_count_values(tmp_path):
    store = STSStore(tmp_path / "count-types.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-string", "2026-07-08T00:00:00", SHARE_STATUS_MERGED)
    _register(store, cid, uid, "pkg-null", "2026-07-07T00:00:00", SHARE_STATUS_MERGED)
    _register(store, cid, uid, "pkg-bad", "2026-07-06T00:00:00", SHARE_STATUS_MERGED)
    store.db.conn.execute("UPDATE share_packages SET merge_result_operations_applied='7', merge_result_operations_skipped='0' WHERE share_package_id='pkg-string'")
    store.db.conn.execute("UPDATE share_packages SET merge_result_operations_applied=NULL, merge_result_operations_skipped=NULL WHERE share_package_id='pkg-null'")
    store.db.conn.execute("UPDATE share_packages SET merge_result_operations_applied=-2, merge_result_operations_skipped='bad' WHERE share_package_id='pkg-bad'")
    store.db.conn.commit()

    rows = list_contract_share_history(store, uid)

    string_row = next(r for r in rows if r.share_package_id == "pkg-string")
    assert string_row.merge_result_operations_applied == 7
    assert string_row.merge_result_operations_skipped == 0
    null_row = next(r for r in rows if r.share_package_id == "pkg-null")
    assert null_row.merge_result_operations_applied is None
    assert null_row.merge_result_operations_skipped is None
    bad_row = next(r for r in rows if r.share_package_id == "pkg-bad")
    assert bad_row.merge_result_operations_applied is None
    assert bad_row.merge_result_operations_skipped is None

from src.services.share_lifecycle_service import (
    ShareLifecycleContextError,
    ShareLifecyclePermissionError,
    SharePackageContractMismatchError,
    SharePackageNotCancelableError,
    SharePackageNotFoundError,
    cancel_share_package,
    list_active_share_packages,
)

_ADMIN = {"is_admin": True, "is_active": 1, "id": 1, "username": "admin"}
_DENIED = {"id": 999, "is_active": 1, "permissions": []}


def test_cancel_open_share_package_is_registry_only_and_durable(tmp_path):
    store = STSStore(tmp_path / "cancel-open.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-open", "2026-07-08T00:00:00", SHARE_STATUS_OPEN)
    before_snapshot = _snapshot_hash(store.db.conn, cid)
    before_contract = dict(store.db.conn.execute("SELECT revision,updated_at FROM contracts WHERE id=?", (cid,)).fetchone())

    row = cancel_share_package(store, uid, "pkg-open", current_staff=_ADMIN)

    assert row["status"] == SHARE_STATUS_CANCELLED
    assert _snapshot_hash(store.db.conn, cid) == before_snapshot
    assert dict(store.db.conn.execute("SELECT revision,updated_at FROM contracts WHERE id=?", (cid,)).fetchone()) == before_contract
    db_row = store.get_share_package("pkg-open")
    assert db_row["merge_result_operations_applied"] is None
    assert db_row["merge_result_operations_skipped"] is None
    assert not db_row["merged_at"]
    assert not db_row["merge_result_sha256"]
    assert int(db_row["return_count"] or 0) == 0
    store.db.close()
    reopened = STSStore(tmp_path / "cancel-open.sts")
    assert reopened.get_share_package("pkg-open")["status"] == SHARE_STATUS_CANCELLED


def test_cancel_returned_allowed_but_final_and_repeated_rejected(tmp_path):
    store = STSStore(tmp_path / "cancel-matrix.sts")
    cid = store.write_contract(_contract("C-1"), [], {})
    uid = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    _register(store, cid, uid, "pkg-returned", "2026-07-08T00:00:00", SHARE_STATUS_RETURNED)
    cancel_share_package(store, uid, "pkg-returned", current_staff=_ADMIN)
    with pytest.raises(SharePackageNotCancelableError):
        cancel_share_package(store, uid, "pkg-returned", current_staff=_ADMIN)
    for status in [SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED, SHARE_STATUS_REJECTED]:
        package_id = f"pkg-{status.lower()}"
        _register(store, cid, uid, package_id, "2026-07-08T01:00:00", status)
        with pytest.raises(SharePackageNotCancelableError):
            cancel_share_package(store, uid, package_id, current_staff=_ADMIN)
        assert store.get_share_package(package_id)["status"] == status


def test_cancel_unknown_wrong_contract_permission_and_share_mode_guards(tmp_path):
    store = STSStore(tmp_path / "cancel-guards.sts")
    cid1 = store.write_contract(_contract("C-1"), [], {})
    cid2 = store.write_contract(_contract("C-2"), [], {})
    uid1 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid1,)).fetchone()[0]
    uid2 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid2,)).fetchone()[0]
    _register(store, cid2, uid2, "pkg-b", "2026-07-08T00:00:00", SHARE_STATUS_OPEN)
    with pytest.raises(SharePackageNotFoundError):
        cancel_share_package(store, uid1, "missing", current_staff=_ADMIN)
    with pytest.raises(SharePackageContractMismatchError):
        cancel_share_package(store, uid1, "pkg-b", current_staff=_ADMIN)
    with pytest.raises(ShareLifecyclePermissionError):
        cancel_share_package(store, uid2, "pkg-b", current_staff=_DENIED)
    setattr(store, "share_mode_enabled", True)
    with pytest.raises(ShareLifecycleContextError):
        cancel_share_package(store, uid2, "pkg-b", current_staff=_ADMIN)
    assert store.get_share_package("pkg-b")["status"] == SHARE_STATUS_OPEN


def test_active_share_packages_filter_current_contract_and_status_without_blob_reads(tmp_path, monkeypatch):
    store = STSStore(tmp_path / "active.sts")
    cid1 = store.write_contract(_contract("C-1"), [], {})
    cid2 = store.write_contract(_contract("C-2"), [], {})
    uid1 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid1,)).fetchone()[0]
    uid2 = store.db.conn.execute("SELECT merge_uid FROM contracts WHERE id=?", (cid2,)).fetchone()[0]
    for status in [SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED, SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED]:
        _register(store, cid1, uid1, f"pkg-{status}", f"2026-07-08T0{len(status)%10}:00:00", status)
    _register(store, cid2, uid2, "pkg-other", "2026-07-09T00:00:00", SHARE_STATUS_OPEN)

    rows = list_active_share_packages(store, uid1)

    assert {row["status"] for row in rows} == {SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED}
    assert {row["contract_merge_uid"] for row in rows} == {uid1}
    assert all("base_snapshot_sha256" not in row and "merge_result_sha256" not in row for row in rows)
