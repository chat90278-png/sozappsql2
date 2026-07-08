from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import uuid

import pytest

from src.domain.contract_snapshot import build_contract_snapshot, hash_contract_snapshot, CONTRACT_SNAPSHOT_FORMAT_VERSION
from src.domain.share_merge_resolution import resolve_merge_plan, hash_merge_operations
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.models.share_models import SHARE_FORMAT_V2, SHARE_STATUS_MERGED, SHARE_STATUS_OPEN, SHARE_STATUS_PARTIALLY_MERGED, SharePackageRegistryEntry
from src.models.share_merge_models import MergeChangeKind
from src.models.share_merge_resolution_models import MergeDecision, MergeDecisionKind, MergeOperationKind
from src.services.share_merge_apply_service import (
    MergeSourceChangedError,
    RemoteDocumentHashMismatchError,
    ShareMergeApplyValidationError,
    SharePackageAlreadyAppliedError,
    apply_resolved_share_merge,
    preflight_resolved_share_merge,
)
from src.services.share_merge_service import prepare_share_merge_plan
from src.services.share_package_service import build_base_snapshot_from_source, make_v2_metadata, write_share_base_snapshot, write_share_metadata
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.sts_store import STSStore


def _contract(note="A", status="BASE"):
    return ContractInfo(no="C-1", platform="AKINCI", user="SSB", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="2026-01-01", t0_date="2026-01-02", t0_months=1, completion_date="2026-02-02", status=status, note=note)


def make_registered_share(tmp_path: Path):
    source = STSStore(tmp_path / f"source-{uuid.uuid4()}.sts")
    ci = _contract()
    sys = SystemInfo("SYS", {"C": 1})
    sys.note = "X"
    cid = source.write_contract(ci, [sys], {"SYS": [DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0})]})
    created_at = "2026-07-07T00:00:00"
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at=created_at)
    share = STSStore(tmp_path / f"share-{uuid.uuid4()}.sts")
    loaded_ci, systems, deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    loaded_ci.entry_start_row = loaded_ci.id = loaded_ci.contract_id = 0
    loaded_ci.platform_ids = []; loaded_ci.platforms = []; loaded_ci.platform_id = 0; loaded_ci.primary_platform_id = 0
    package_contract_id = share.write_contract(loaded_ci, systems, deliveries)
    package_id = str(uuid.uuid4())
    metadata = make_v2_metadata(share_package_id=package_id, permission_mode="edit", source_sts_instance_id=source.sts_instance_id(), source_schema_version=CURRENT_SCHEMA_VERSION, source_contract_id=cid, source_contract_merge_uid=base.contract_merge_uid, source_contract_no=ci.no, base_revision=ci.revision, base_snapshot_sha256=base.snapshot_sha256, created_at=created_at, created_by_staff_id=42, created_by_username="tester", created_by_full_name="Test User", document_count=0, document_bytes=0)
    metadata["contract_id"] = str(package_contract_id)
    write_share_metadata(share.path, metadata)
    write_share_base_snapshot(share.path, base)
    source.register_share_package(SharePackageRegistryEntry(share_package_id=package_id, contract_id=cid, contract_merge_uid=base.contract_merge_uid, source_contract_revision=ci.revision, permission_mode="edit", share_format_version=SHARE_FORMAT_V2, snapshot_format_version=CONTRACT_SNAPSHOT_FORMAT_VERSION, base_snapshot_sha256=base.snapshot_sha256, created_at=created_at, created_by_staff_id=42, created_by_username="tester", created_by_full_name="Test User", exported_filename=share.path.name, status=SHARE_STATUS_OPEN))
    return source, share, ci, cid, metadata


def _edit_note(store, value):
    ci, systems, deliveries = store.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    ci.note = value
    store.write_contract(ci, systems, deliveries)


def _note(store, cid):
    return store.db.conn.execute("SELECT note FROM contracts WHERE id=?", (cid,)).fetchone()[0]


def test_remote_only_merge_persists_after_reopen(tmp_path):
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE")
    plan = prepare_share_merge_plan(source, share.path)
    assert any(c.change_kind == MergeChangeKind.REMOTE_ONLY and c.field_name == "note" for c in plan.changes)
    resolved = resolve_merge_plan(plan)
    assert not resolved.has_unresolved_conflicts
    assert any(d.decision == MergeDecisionKind.REMOTE_USE for d in resolved.decisions)
    preflight_resolved_share_merge(source, share.path, resolved)
    result = apply_resolved_share_merge(source, share.path, resolved)
    assert result.success and _note(source, cid) == "REMOTE"
    assert source.get_share_package(metadata["share_package_id"])["status"] == SHARE_STATUS_MERGED
    source.db.close()
    reopened = STSStore(source.path)
    try:
        assert _note(reopened, cid) == "REMOTE"
    finally:
        reopened.db.close(); share.db.close()


def test_local_only_merge_is_noop_and_keeps_local_value(tmp_path):
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(source, "LOCAL")
    plan = prepare_share_merge_plan(source, share.path)
    assert any(c.change_kind == MergeChangeKind.LOCAL_ONLY and c.field_name == "note" for c in plan.changes)
    resolved = resolve_merge_plan(plan)
    assert all(op.operation_kind != MergeOperationKind.SET_CONTRACT_FIELD for op in resolved.operations)
    result = apply_resolved_share_merge(source, share.path, resolved)
    assert _note(source, cid) == "LOCAL"
    assert result.operations_applied == 0
    assert source.get_share_package(metadata["share_package_id"])["status"] == SHARE_STATUS_MERGED


def test_parallel_safe_contract_and_system_changes_are_preserved(tmp_path):
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    _edit_note(source, "B")
    share.db.conn.execute("UPDATE systems SET note=?", ("Y",))
    share.db.conn.commit()
    apply_resolved_share_merge(source, share.path, resolve_merge_plan(prepare_share_merge_plan(source, share.path)))
    row = source.db.conn.execute("SELECT note FROM contracts WHERE id=?", (cid,)).fetchone()
    sysrow = source.db.conn.execute("SELECT note FROM systems WHERE contract_id=?", (cid,)).fetchone()
    assert row[0] == "B" and sysrow[0] == "Y"


@pytest.mark.parametrize("decision, expected, status", [(MergeDecisionKind.LOCAL_KEEP, "B", SHARE_STATUS_MERGED), (MergeDecisionKind.REMOTE_USE, "C", SHARE_STATUS_MERGED), (MergeDecisionKind.SKIP, "B", SHARE_STATUS_PARTIALLY_MERGED)])
def test_field_conflict_requires_explicit_decision(tmp_path, decision, expected, status):
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(source, "B"); _edit_note(share, "C")
    plan = prepare_share_merge_plan(source, share.path)
    assert plan.has_conflicts
    unresolved = resolve_merge_plan(plan)
    assert unresolved.has_unresolved_conflicts
    with pytest.raises(ShareMergeApplyValidationError):
        preflight_resolved_share_merge(source, share.path, unresolved)
    conflict_targets = [i.target.target_id for i in unresolved.resolution_items if i.is_conflict]
    resolved = resolve_merge_plan(plan, {target: decision for target in conflict_targets})
    result = apply_resolved_share_merge(source, share.path, resolved, allow_partial=decision == MergeDecisionKind.SKIP)
    assert _note(source, cid) == expected
    assert result.registry_status == status
    assert source.get_share_package(metadata["share_package_id"])["status"] == status


def test_document_replace_validates_real_blob_bytes_and_replay(tmp_path):
    source, share, ci, cid, _metadata = make_registered_share(tmp_path)
    p = tmp_path / "doc.txt"; p.write_bytes(b"base")
    source.add_contract_file("AKINCI", ci.no, p, ci.contract_type, note="keep-note")
    # Re-baseline this package after adding the document so the test exercises a
    # true BASE -> REMOTE content replacement rather than a remote add.
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at="2026-07-07T00:00:00")
    meta = dict(_metadata)
    meta["base_snapshot_sha256"] = base.snapshot_sha256
    write_share_metadata(share.path, meta)
    share.db.conn.execute("DELETE FROM share_base_snapshot")
    share.db.conn.commit()
    write_share_base_snapshot(share.path, base)
    source.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?", (base.snapshot_sha256, meta["share_package_id"]))
    source.db.conn.commit()
    # mirror the added document into the already-created share with the same merge_uid
    row = source.db.conn.execute("SELECT * FROM contract_files WHERE contract_id=?", (cid,)).fetchone()
    share.db.conn.execute("INSERT INTO contract_files(contract_id,merge_uid,filename,original_path,file_ext,mime_type,size_bytes,sha256,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (1, row["merge_uid"], row["filename"], "", row["file_ext"], row["mime_type"], 6, hashlib.sha256(b"remote").hexdigest(), b"remote", row["note"], row["created_at"], row["updated_at"]))
    share.db.conn.commit()
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    assert any(op.operation_kind == MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT for op in resolved.operations)
    apply_resolved_share_merge(source, share.path, resolved)
    final = source.db.conn.execute("SELECT filename,note,sha256,content_blob FROM contract_files WHERE id=?", (row["id"],)).fetchone()
    assert bytes(final["content_blob"]) == b"remote"
    assert final["sha256"] == hashlib.sha256(b"remote").hexdigest()
    assert final["filename"] == "doc.txt" and final["note"] == "keep-note"
    with pytest.raises(SharePackageAlreadyAppliedError):
        preflight_resolved_share_merge(source, share.path, resolved)


def test_document_tamper_fails_closed_without_source_mutation(tmp_path):
    source, share, ci, cid, _metadata = make_registered_share(tmp_path)
    p = tmp_path / "remote.txt"; p.write_bytes(b"remote bytes")
    share.add_contract_file("AKINCI", ci.no, p, ci.contract_type)
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    before = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    share.db.conn.execute("UPDATE contract_files SET content_blob=?", (b"tampered",)); share.db.conn.commit()
    with pytest.raises(RemoteDocumentHashMismatchError):
        apply_resolved_share_merge(source, share.path, resolved)
    after = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    assert before == after
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_files WHERE contract_id=?", (cid,)).fetchone()[0] == 0


def test_operations_hash_and_stale_plan_are_enforced(tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE")
    plan = prepare_share_merge_plan(source, share.path)
    r1 = resolve_merge_plan(plan); r2 = resolve_merge_plan(plan, list(reversed(r1.decisions)))
    assert r1.operations_hash == r2.operations_hash == hash_merge_operations(r1.operations)
    tampered_op = replace(r1.operations[0], value="MUTATED")
    tampered = replace(r1, operations=[tampered_op])
    with pytest.raises(ShareMergeApplyValidationError):
        preflight_resolved_share_merge(source, share.path, tampered)
    _edit_note(source, "LOCAL AFTER PLAN")
    with pytest.raises(MergeSourceChangedError):
        apply_resolved_share_merge(source, share.path, r1)
