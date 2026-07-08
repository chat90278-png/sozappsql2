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
    MergeOperationTargetNotFoundError,
    RemoteDocumentHashMismatchError,
    ShareMergeApplyValidationError,
    SharePackageAlreadyAppliedError,
    apply_resolved_share_merge,
    preflight_resolved_share_merge,
)
from src.services.share_merge_service import prepare_share_merge_plan
from src.services.share_package_service import build_base_snapshot_from_source, make_v2_metadata, write_share_base_snapshot, write_share_metadata
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.share_history_service import list_contract_share_history
from src.ui.presenters.share_history_presenter import present_merge_result
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
    assert resolved.operations == []
    result = apply_resolved_share_merge(source, share.path, resolved)
    assert result.success
    assert result.operations_requested == 0
    assert result.operations_applied == 0
    assert result.operations_skipped == 0
    assert _note(source, cid) == "LOCAL"
    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == SHARE_STATUS_MERGED
    assert registry["merge_result_sha256"] == result.post_apply_snapshot_hash
    assert registry["merge_result_operations_applied"] == 0
    assert registry["merge_result_operations_skipped"] == 0
    assert registry["merged_at"]
    source.db.close()
    reopened = STSStore(source.path)
    try:
        reopened_registry = reopened.get_share_package(metadata["share_package_id"])
        assert reopened_registry["merge_result_operations_applied"] == 0
        assert reopened_registry["merge_result_operations_skipped"] == 0
        rows = list_contract_share_history(reopened, metadata["source_contract_merge_uid"])
        record = next(r for r in rows if r.share_package_id == metadata["share_package_id"])
        assert record.merge_result_operations_applied == 0
        assert record.merge_result_operations_skipped == 0
        presentation = present_merge_result(record)
        assert presentation.recorded is True
        assert "yeni değişiklik yoktu" in presentation.summary_label
    finally:
        reopened.db.close(); share.db.close()


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
    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == status
    assert registry["merge_result_operations_applied"] == result.operations_applied
    assert registry["merge_result_operations_skipped"] == result.operations_skipped
    assert registry["merged_at"]
    if status == SHARE_STATUS_PARTIALLY_MERGED:
        assert result.operations_skipped == len(resolved.operations) - result.operations_applied


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


def _snapshots(source, share, cid):
    import json
    from src.services.share_package_service import read_share_base_snapshot
    base = json.loads(read_share_base_snapshot(share.path).snapshot_json)
    remote_cid = share.db.conn.execute("SELECT id FROM contracts WHERE merge_uid=(SELECT merge_uid FROM contracts WHERE id=?)", (cid,)).fetchone()[0]
    return base, build_contract_snapshot(source.db.conn, cid), build_contract_snapshot(share.db.conn, remote_cid)


def _resolve_with_graph(source, share, cid):
    base, local, remote = _snapshots(source, share, cid)
    return resolve_merge_plan(prepare_share_merge_plan(source, share.path), base_snapshot=base, local_snapshot=local, remote_snapshot=remote)


def _op_index(resolved, kind, uid=None):
    for i, op in enumerate(resolved.operations):
        if op.operation_kind == kind and (uid is None or op.entity_uid == uid):
            return i
    raise AssertionError(f"operation not found: {kind} {uid}")


def test_remote_system_and_delivery_add_parent_first_and_persistent(tmp_path):
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    ci, systems, deliveries = share.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    new_system = SystemInfo("SYS-REMOTE", {"C": 2})
    systems.append(new_system)
    deliveries["SYS-REMOTE"] = [DeliveryInfo("DEL-REMOTE", "PLAN", "", "", {"C": 2}, {"C": 0})]
    share.write_contract(ci, systems, deliveries)

    resolved = _resolve_with_graph(source, share, cid)
    assert not resolved.has_unresolved_conflicts and not resolved.has_structural_issues
    system_uid = next(op.entity_uid for op in resolved.operations if op.operation_kind == MergeOperationKind.ADD_SYSTEM and op.entity_label == "SYS-REMOTE")
    delivery_uid = next(op.entity_uid for op in resolved.operations if op.operation_kind == MergeOperationKind.ADD_DELIVERY and op.entity_label == "DEL-REMOTE")
    assert _op_index(resolved, MergeOperationKind.ADD_SYSTEM, system_uid) < _op_index(resolved, MergeOperationKind.ADD_DELIVERY, delivery_uid)
    preflight_resolved_share_merge(source, share.path, resolved)
    apply_resolved_share_merge(source, share.path, resolved)

    row = source.db.conn.execute("SELECT id FROM systems WHERE contract_id=? AND name='SYS-REMOTE'", (cid,)).fetchone()
    assert row is not None
    drow = source.db.conn.execute("SELECT id FROM deliveries WHERE contract_id=? AND name='DEL-REMOTE' AND system_id=?", (cid, row[0])).fetchone()
    assert drow is not None
    source.db.close(); reopened = STSStore(source.path)
    try:
        assert reopened.db.conn.execute("SELECT 1 FROM deliveries d JOIN systems s ON s.id=d.system_id WHERE s.name='SYS-REMOTE' AND d.name='DEL-REMOTE'").fetchone()
    finally:
        reopened.db.close(); share.db.close()


def test_remote_delivery_and_system_delete_child_first_and_persistent(tmp_path):
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    share.db.conn.execute("DELETE FROM deliveries WHERE name='DEL'")
    share.db.conn.execute("DELETE FROM systems WHERE name='SYS'")
    share.db.conn.commit()
    resolved = _resolve_with_graph(source, share, cid)
    assert not resolved.has_unresolved_conflicts and not resolved.has_structural_issues
    assert _op_index(resolved, MergeOperationKind.DELETE_DELIVERY) < _op_index(resolved, MergeOperationKind.DELETE_SYSTEM)
    apply_resolved_share_merge(source, share.path, resolved)
    assert source.db.conn.execute("SELECT COUNT(*) FROM deliveries WHERE contract_id=?", (cid,)).fetchone()[0] == 0
    assert source.db.conn.execute("SELECT COUNT(*) FROM systems WHERE contract_id=?", (cid,)).fetchone()[0] == 0
    source.db.close(); reopened = STSStore(source.path)
    try:
        assert reopened.db.conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0] == 0
    finally:
        reopened.db.close(); share.db.close()


def test_invalid_projected_graph_parent_delete_child_keep_fails_closed(tmp_path):
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    local_delivery_id = source.db.conn.execute("SELECT id FROM deliveries WHERE contract_id=?", (cid,)).fetchone()[0]
    source.db.conn.execute("UPDATE deliveries SET note=? WHERE id=?", ("LOCAL CHILD", local_delivery_id))
    source.db.conn.commit()
    share.db.conn.execute("PRAGMA foreign_keys=OFF")
    share.db.conn.execute("DELETE FROM systems WHERE name='SYS'")
    share.db.conn.commit()
    resolved = _resolve_with_graph(source, share, cid)
    assert any(issue.code in {"PARENT_DELETE_CHILD_KEEP_CONFLICT", "ABSENT_DELIVERY_PARENT_SYSTEM"} for issue in resolved.issues)
    before = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    with pytest.raises(ShareMergeApplyValidationError):
        apply_resolved_share_merge(source, share.path, resolved, allow_partial=True)
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before
    assert source.db.conn.execute("SELECT note FROM deliveries WHERE id=?", (local_delivery_id,)).fetchone()[0] == "LOCAL CHILD"
    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == SHARE_STATUS_OPEN
    assert registry["merge_result_operations_applied"] is None
    assert registry["merge_result_operations_skipped"] is None
    assert registry["merged_at"] is None


def test_graph_operation_ordering_is_deterministic(tmp_path):
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    ci, systems, deliveries = share.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    systems.extend([SystemInfo("B-SYS", {"C": 1}), SystemInfo("A-SYS", {"C": 1})])
    deliveries["A-SYS"] = [DeliveryInfo("A-DEL", "PLAN", "", "", {"C": 1}, {"C": 0})]
    deliveries["B-SYS"] = [DeliveryInfo("B-DEL", "PLAN", "", "", {"C": 1}, {"C": 0})]
    share.write_contract(ci, systems, deliveries)
    r1 = _resolve_with_graph(source, share, cid)
    r2 = _resolve_with_graph(source, share, cid)
    assert [(op.operation_kind, op.entity_uid) for op in r1.operations] == [(op.operation_kind, op.entity_uid) for op in r2.operations]
    assert r1.operations_hash == r2.operations_hash


def _prepare_keep_both_conflict(tmp_path, existing_names=()):
    source, share, ci, cid, metadata = make_registered_share(tmp_path)
    folder = source.create_contract_file_folder("AKINCI", ci.no, ci.contract_type, name="F")
    p = tmp_path / "Rapor.pdf"; p.write_bytes(b"A")
    fid = source.add_contract_file("AKINCI", ci.no, p, ci.contract_type, folder_id=folder["id"])
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at="2026-07-07T00:00:00")
    meta = dict(metadata); meta["base_snapshot_sha256"] = base.snapshot_sha256
    write_share_metadata(share.path, meta)
    share.db.conn.execute("DELETE FROM share_base_snapshot"); share.db.conn.commit(); write_share_base_snapshot(share.path, base)
    source.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?", (base.snapshot_sha256, meta["share_package_id"]))
    src_folder = source.db.conn.execute("SELECT * FROM contract_file_folders WHERE id=?", (folder["id"],)).fetchone()
    share.db.conn.execute("INSERT INTO contract_file_folders(contract_id,merge_uid,parent_id,name,created_at,updated_at) VALUES(?,?,?,?,?,?)", (1, src_folder["merge_uid"], None, "F", src_folder["created_at"], src_folder["updated_at"]))
    row = source.db.conn.execute("SELECT * FROM contract_files WHERE id=?", (fid,)).fetchone()
    share_folder_id = share.db.conn.execute("SELECT id FROM contract_file_folders WHERE merge_uid=?", (src_folder["merge_uid"],)).fetchone()[0]
    share.db.conn.execute("INSERT INTO contract_files(contract_id,merge_uid,folder_id,filename,original_path,file_ext,mime_type,size_bytes,sha256,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (1, row["merge_uid"], share_folder_id, row["filename"], "", row["file_ext"], row["mime_type"], 1, hashlib.sha256(b"C").hexdigest(), b"C", row["note"], row["created_at"], row["updated_at"]))
    source.db.conn.execute("UPDATE contract_files SET size_bytes=?,sha256=?,content_blob=? WHERE id=?", (1, hashlib.sha256(b"B").hexdigest(), b"B", fid))
    for name in existing_names:
        source.db.conn.execute("INSERT INTO contract_files(contract_id,merge_uid,folder_id,filename,original_path,file_ext,mime_type,size_bytes,sha256,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (cid, str(uuid.uuid4()), folder["id"], name, "", Path(name).suffix.lower().lstrip('.'), "application/pdf", 1, hashlib.sha256(name.encode()).hexdigest(), name.encode(), "", row["created_at"], row["updated_at"]))
    source.db.conn.commit(); share.db.conn.commit()
    return source, share, cid, fid, metadata


@pytest.mark.parametrize("existing, expected", [([], "Rapor (2).pdf"), (["Rapor (2).pdf"], "Rapor (3).pdf"), (["Rapor (2).pdf", "Rapor (3).pdf", "Rapor (4).pdf"], "Rapor (5).pdf")])
def test_document_keep_both_collision_matrix(tmp_path, existing, expected):
    source, share, cid, fid, _metadata = _prepare_keep_both_conflict(tmp_path, existing)
    plan = prepare_share_merge_plan(source, share.path)
    unresolved = resolve_merge_plan(plan)
    item = next(i for i in unresolved.resolution_items if i.target.field_name == "sha256" and i.is_conflict)
    assert MergeDecisionKind.DOCUMENT_KEEP_BOTH in item.allowed_decisions
    resolved = resolve_merge_plan(plan, {i.target.target_id: (MergeDecisionKind.DOCUMENT_KEEP_BOTH if MergeDecisionKind.DOCUMENT_KEEP_BOTH in i.allowed_decisions else MergeDecisionKind.LOCAL_KEEP) for i in unresolved.resolution_items if i.is_conflict})
    apply_resolved_share_merge(source, share.path, resolved)
    rows = source.db.conn.execute("SELECT filename,merge_uid,sha256,content_blob FROM contract_files WHERE contract_id=? ORDER BY filename", (cid,)).fetchall()
    by_name = {r["filename"]: r for r in rows}
    assert bytes(by_name["Rapor.pdf"]["content_blob"]) == b"B"
    assert bytes(by_name[expected]["content_blob"]) == b"C"
    assert by_name["Rapor.pdf"]["merge_uid"] != by_name[expected]["merge_uid"]
    assert by_name[expected]["sha256"] == hashlib.sha256(b"C").hexdigest()


def test_keep_both_insert_failure_rolls_back(monkeypatch, tmp_path):
    import src.services.share_merge_apply_service as apply_service
    source, share, cid, _fid, metadata = _prepare_keep_both_conflict(tmp_path)
    plan = prepare_share_merge_plan(source, share.path)
    unresolved = resolve_merge_plan(plan)
    item = next(i for i in unresolved.resolution_items if i.target.field_name == "sha256" and i.is_conflict)
    resolved = resolve_merge_plan(plan, {i.target.target_id: (MergeDecisionKind.DOCUMENT_KEEP_BOTH if MergeDecisionKind.DOCUMENT_KEEP_BOTH in i.allowed_decisions else MergeDecisionKind.LOCAL_KEEP) for i in unresolved.resolution_items if i.is_conflict})
    before = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    original = apply_service._keep_both_file
    def boom(ctx, op):
        original(ctx, op)
        raise RuntimeError("fault after keep-both insert")
    monkeypatch.setattr(apply_service, "_keep_both_file", boom)
    apply_service._HANDLERS[MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE] = boom
    with pytest.raises(RuntimeError):
        apply_resolved_share_merge(source, share.path, resolved)
    apply_service._HANDLERS[MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE] = original
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_files WHERE contract_id=?", (cid,)).fetchone()[0] == 1
    assert source.get_share_package(metadata["share_package_id"])["status"] == SHARE_STATUS_OPEN


def test_mid_operation_and_registry_finalize_failures_roll_back(monkeypatch, tmp_path):
    import src.services.share_merge_apply_service as apply_service
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE NOTE")
    ci, systems, deliveries = share.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    systems.append(SystemInfo("REMOTE-SYS", {"C": 1}))
    deliveries["REMOTE-SYS"] = [DeliveryInfo("REMOTE-DEL", "PLAN", "", "", {"C": 1}, {"C": 0})]
    share.write_contract(ci, systems, deliveries)
    resolved = _resolve_with_graph(source, share, cid)
    before = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    revision_before = source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    registry_before = dict(source.get_share_package(metadata["share_package_id"]))
    original_apply_op = apply_service._apply_operation
    calls = {"n": 0}
    def fail_third(ctx, op):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("fault at third operation")
        return original_apply_op(ctx, op)
    monkeypatch.setattr(apply_service, "_apply_operation", fail_third)
    with pytest.raises(RuntimeError):
        apply_resolved_share_merge(source, share.path, resolved)
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before
    assert source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0] == revision_before
    mid_registry = source.get_share_package(metadata["share_package_id"])
    assert mid_registry["status"] == SHARE_STATUS_OPEN
    assert mid_registry["merge_result_operations_applied"] is None
    assert mid_registry["merge_result_operations_skipped"] is None
    assert mid_registry["merged_at"] is None
    assert mid_registry["merge_result_sha256"] == registry_before["merge_result_sha256"]
    monkeypatch.setattr(apply_service, "_apply_operation", original_apply_op)
    original_update = apply_service._update_registry
    registry_apply_calls = {"n": 0}
    def count_apply(ctx, op):
        registry_apply_calls["n"] += 1
        return original_apply_op(ctx, op)
    def fail_registry(*args, **kwargs):
        raise RuntimeError("fault at registry finalize")
    monkeypatch.setattr(apply_service, "_apply_operation", count_apply)
    monkeypatch.setattr(apply_service, "_update_registry", fail_registry)
    with pytest.raises(RuntimeError):
        apply_resolved_share_merge(source, share.path, resolved)
    assert registry_apply_calls["n"] > 0
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before
    assert source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0] == revision_before
    final_registry = source.get_share_package(metadata["share_package_id"])
    assert final_registry["status"] == registry_before["status"] == SHARE_STATUS_OPEN
    assert final_registry["merge_result_operations_applied"] is None
    assert final_registry["merge_result_operations_skipped"] is None
    assert final_registry["merged_at"] is None
    assert final_registry["merge_result_sha256"] == registry_before["merge_result_sha256"]
    monkeypatch.setattr(apply_service, "_apply_operation", original_apply_op)
    monkeypatch.setattr(apply_service, "_update_registry", original_update)


def test_relation_add_remove_and_missing_target_fail_closed(tmp_path):
    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    # target-present add for user, responsible engineer, tag; platform relation already has primary platform.
    source.db.conn.execute("INSERT INTO users(name,yi_yd) VALUES('REMOTEUSER','Yİ')")
    share.db.conn.execute("INSERT INTO users(name,yi_yd) VALUES('REMOTEUSER','Yİ')")
    source.db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('dev','Remote Engineer','x','user',1)")
    share.db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('dev','Remote Engineer','x','user',1)")
    source.db.conn.execute("INSERT INTO tags(name,color,kind) VALUES('RemoteTag','#111','contract')")
    share.db.conn.execute("INSERT INTO tags(name,color,kind) VALUES('RemoteTag','#111','contract')")
    share.db.conn.execute("INSERT INTO contract_users(contract_id,user_id) SELECT 1,id FROM users WHERE name='REMOTEUSER'")
    share.db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,sort_order,is_primary) SELECT 1,id,0,1 FROM staff WHERE full_name='Remote Engineer'")
    share.db.conn.execute("INSERT INTO contract_tags(contract_id,tag_id) SELECT 1,id FROM tags WHERE name='RemoteTag'")
    source.db.conn.commit(); share.db.conn.commit()
    apply_resolved_share_merge(source, share.path, resolve_merge_plan(prepare_share_merge_plan(source, share.path)))
    assert source.db.conn.execute("SELECT 1 FROM contract_users cu JOIN users u ON u.id=cu.user_id WHERE u.name='REMOTEUSER'").fetchone()
    assert source.db.conn.execute("SELECT 1 FROM contract_responsible_engineers cre JOIN staff s ON s.id=cre.staff_id WHERE s.full_name='Remote Engineer'").fetchone()
    assert source.db.conn.execute("SELECT 1 FROM contract_tags ct JOIN tags t ON t.id=ct.tag_id WHERE t.name='RemoteTag'").fetchone()
    assert source.db.conn.execute("SELECT COUNT(*) FROM users WHERE name='REMOTEUSER'").fetchone()[0] == 1

    # target-missing on a fresh package fails closed and does not auto-create master data.
    source2, share2, _ci2, cid2, metadata2 = make_registered_share(tmp_path)
    share2.db.conn.execute("INSERT INTO users(name,yi_yd) VALUES('MISSINGUSER','Yİ')")
    share2.db.conn.execute("INSERT INTO contract_users(contract_id,user_id) SELECT 1,id FROM users WHERE name='MISSINGUSER'")
    share2.db.conn.commit()
    resolved = resolve_merge_plan(prepare_share_merge_plan(source2, share2.path))
    with pytest.raises(MergeOperationTargetNotFoundError):
        apply_resolved_share_merge(source2, share2.path, resolved)
    assert source2.db.conn.execute("SELECT COUNT(*) FROM users WHERE name='MISSINGUSER'").fetchone()[0] == 0
    assert source2.get_share_package(metadata2["share_package_id"])["status"] == SHARE_STATUS_OPEN


def test_document_revision_snapshot_matrix(tmp_path):
    source, _share, ci, cid, _metadata = make_registered_share(tmp_path)
    def state():
        return source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0], hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    matrix = {}
    rev0, hash0 = state()
    p = tmp_path / "matrix.txt"; p.write_bytes(b"A")
    fid = source.add_contract_file("AKINCI", ci.no, p, ci.contract_type)
    matrix["add"] = (state()[0] != rev0, state()[1] != hash0)
    rev1, hash1 = state(); source.db.conn.execute("UPDATE contract_files SET filename='matrix-renamed.txt', file_ext='txt' WHERE id=?", (fid,)); source.db.conn.commit(); matrix["rename"] = (state()[0] != rev1, state()[1] != hash1)
    folder = source.create_contract_file_folder("AKINCI", ci.no, ci.contract_type, name="MoveTarget")
    rev2, hash2 = state(); source.move_contract_file(fid, folder["id"]); matrix["move"] = (state()[0] != rev2, state()[1] != hash2)
    rev3, hash3 = state(); source.db.conn.execute("UPDATE contract_files SET content_blob=?,size_bytes=?,sha256=? WHERE id=?", (b"B", 1, hashlib.sha256(b"B").hexdigest(), fid)); source.db.conn.commit(); matrix["content_replace"] = (state()[0] != rev3, state()[1] != hash3)
    rev4, hash4 = state(); source.delete_contract_file(fid); matrix["delete"] = (state()[0] != rev4, state()[1] != hash4)
    assert all(changed for _rev_changed, changed in matrix.values()), matrix


def test_relation_remove_preserves_master_rows_and_other_contract_relations(tmp_path):
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    other = _contract(note="other")
    other.no = "C-OTHER"
    other_id = source.write_contract(other, [SystemInfo("OTHER-SYS", {"C": 1})], {"OTHER-SYS": []})
    source.db.conn.execute("INSERT INTO users(name,yi_yd) VALUES('REMOVEUSER','Yİ')")
    source.db.conn.execute("INSERT INTO tags(name,color,kind) VALUES('RemoveTag','#222','contract')")
    source.db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('dev2','Remove Engineer','x','user',1)")
    for contract_id in (cid, other_id):
        source.db.conn.execute("INSERT INTO contract_users(contract_id,user_id) SELECT ?,id FROM users WHERE name='REMOVEUSER'", (contract_id,))
        source.db.conn.execute("INSERT INTO contract_tags(contract_id,tag_id) SELECT ?,id FROM tags WHERE name='RemoveTag'", (contract_id,))
        source.db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,sort_order,is_primary) SELECT ?,id,0,1 FROM staff WHERE full_name='Remove Engineer'", (contract_id,))
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at="2026-07-07T00:00:00")
    meta = dict(_metadata); meta["base_snapshot_sha256"] = base.snapshot_sha256
    write_share_metadata(share.path, meta)
    share.db.conn.execute("DELETE FROM share_base_snapshot"); share.db.conn.commit(); write_share_base_snapshot(share.path, base)
    source.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?", (base.snapshot_sha256, meta["share_package_id"]))
    # Mirror master rows into the share but intentionally leave contract relations absent: remote removed them.
    share.db.conn.execute("INSERT INTO users(name,yi_yd) VALUES('REMOVEUSER','Yİ')")
    share.db.conn.execute("INSERT INTO tags(name,color,kind) VALUES('RemoveTag','#222','contract')")
    share.db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('dev2','Remove Engineer','x','user',1)")
    source.db.conn.commit(); share.db.conn.commit()

    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    assert any(op.operation_kind.name.startswith("DELETE_USER_RELATION") for op in resolved.operations)
    assert any(op.operation_kind.name.startswith("DELETE_TAG_RELATION") for op in resolved.operations)
    assert any(op.operation_kind.name.startswith("DELETE_RESPONSIBLE_ENGINEER_RELATION") for op in resolved.operations)
    apply_resolved_share_merge(source, share.path, resolved)

    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_users cu JOIN users u ON u.id=cu.user_id WHERE cu.contract_id=? AND u.name='REMOVEUSER'", (cid,)).fetchone()[0] == 0
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_tags WHERE contract_id=?", (cid,)).fetchone()[0] == 0
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_responsible_engineers WHERE contract_id=?", (cid,)).fetchone()[0] == 0
    assert source.db.conn.execute("SELECT COUNT(*) FROM users WHERE name='REMOVEUSER'").fetchone()[0] == 1
    assert source.db.conn.execute("SELECT COUNT(*) FROM tags WHERE name='RemoveTag'").fetchone()[0] == 1
    assert source.db.conn.execute("SELECT COUNT(*) FROM staff WHERE full_name='Remove Engineer'").fetchone()[0] == 1
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_users cu JOIN users u ON u.id=cu.user_id WHERE cu.contract_id=? AND u.name='REMOVEUSER'", (other_id,)).fetchone()[0] == 1
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_tags WHERE contract_id=?", (other_id,)).fetchone()[0] == 1
    assert source.db.conn.execute("SELECT COUNT(*) FROM contract_responsible_engineers WHERE contract_id=?", (other_id,)).fetchone()[0] == 1


def _platform_id(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM platforms WHERE name=?", (name,)).fetchone()
    if row:
        return int(row[0])
    conn.execute("INSERT INTO platforms(name,display_name,is_active) VALUES(?,?,1)", (name, name))
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_platform_relation_add_remove_primary_and_missing_target(tmp_path):
    # Remote add: source has master platform, remote adds relation with attributes.
    source, share, _ci, cid, _metadata = make_registered_share(tmp_path)
    source_platform_id = _platform_id(source.db.conn, "TB2")
    share_platform_id = _platform_id(share.db.conn, "TB2")
    share.db.conn.execute("INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,0)", (1, share_platform_id, 7))
    source.db.conn.commit(); share.db.conn.commit()
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    assert any(op.operation_kind == MergeOperationKind.ADD_PLATFORM_RELATION for op in resolved.operations)
    apply_resolved_share_merge(source, share.path, resolved)
    assert tuple(source.db.conn.execute("SELECT sort_order,is_primary FROM contract_platforms WHERE contract_id=? AND platform_id=?", (cid, source_platform_id)).fetchone()) == (7, 0)
    assert source.db.conn.execute("SELECT COUNT(*) FROM platforms WHERE name='TB2'").fetchone()[0] == 1
    source.db.close(); reopened = STSStore(source.path)
    try:
        assert reopened.db.conn.execute("SELECT 1 FROM contract_platforms cp JOIN platforms p ON p.id=cp.platform_id WHERE p.name='TB2'").fetchone()
    finally:
        reopened.db.close(); share.db.close()

    # Remote remove: only the package contract relation is removed; master and another contract relation survive.
    source2, share2, _ci2, cid2, metadata2 = make_registered_share(tmp_path)
    other = _contract(note="platform-other"); other.no = "C-PLAT-OTHER"
    other_id = source2.write_contract(other, [SystemInfo("OTHER", {"C": 1})], {"OTHER": []})
    src_pid = _platform_id(source2.db.conn, "HURKUS")
    share_pid = _platform_id(share2.db.conn, "HURKUS")
    for contract_id in (cid2, other_id):
        source2.db.conn.execute("INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,0)", (contract_id, src_pid, 3))
    share2.db.conn.commit()
    base = build_base_snapshot_from_source(source2.db.conn, cid2, created_at="2026-07-07T00:00:00")
    meta = dict(metadata2); meta["base_snapshot_sha256"] = base.snapshot_sha256
    write_share_metadata(share2.path, meta)
    share2.db.conn.execute("DELETE FROM share_base_snapshot"); share2.db.conn.commit(); write_share_base_snapshot(share2.path, base)
    source2.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?", (base.snapshot_sha256, meta["share_package_id"]))
    # Master exists in share, relation intentionally absent to represent remote remove.
    source2.db.conn.commit(); share2.db.conn.commit()
    resolved2 = resolve_merge_plan(prepare_share_merge_plan(source2, share2.path))
    assert any(op.operation_kind == MergeOperationKind.DELETE_PLATFORM_RELATION for op in resolved2.operations)
    apply_resolved_share_merge(source2, share2.path, resolved2)
    assert source2.db.conn.execute("SELECT COUNT(*) FROM contract_platforms WHERE contract_id=? AND platform_id=?", (cid2, src_pid)).fetchone()[0] == 0
    assert source2.db.conn.execute("SELECT COUNT(*) FROM platforms WHERE name='HURKUS'").fetchone()[0] == 1
    assert source2.db.conn.execute("SELECT COUNT(*) FROM contract_platforms WHERE contract_id=? AND platform_id=?", (other_id, src_pid)).fetchone()[0] == 1

    # Remote primary/attribute update for existing relation.
    source3, share3, _ci3, cid3, _metadata3 = make_registered_share(tmp_path)
    src_pid3 = _platform_id(source3.db.conn, "KIZILELMA")
    share_pid3 = _platform_id(share3.db.conn, "KIZILELMA")
    source3.db.conn.execute("INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,0)", (cid3, src_pid3, 1))
    share3.db.conn.execute("INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,1)", (1, share_pid3, 9))
    share3.db.conn.commit()
    base3 = build_base_snapshot_from_source(source3.db.conn, cid3, created_at="2026-07-07T00:00:00")
    meta3 = make_v2_metadata(share_package_id=_metadata3["share_package_id"], permission_mode="edit", source_sts_instance_id=source3.sts_instance_id(), source_schema_version=CURRENT_SCHEMA_VERSION, source_contract_id=cid3, source_contract_merge_uid=base3.contract_merge_uid, source_contract_no="C-1", base_revision=1, base_snapshot_sha256=base3.snapshot_sha256, created_at="2026-07-07T00:00:00", created_by_staff_id=42, created_by_username="tester", created_by_full_name="Test User", document_count=0, document_bytes=0)
    meta3["contract_id"] = "1"; write_share_metadata(share3.path, meta3); share3.db.conn.execute("DELETE FROM share_base_snapshot"); share3.db.conn.commit(); write_share_base_snapshot(share3.path, base3)
    source3.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?", (base3.snapshot_sha256, meta3["share_package_id"])); source3.db.conn.commit(); share3.db.conn.commit()
    resolved3 = resolve_merge_plan(prepare_share_merge_plan(source3, share3.path))
    assert any(op.operation_kind == MergeOperationKind.SET_PLATFORM_RELATION_FIELD for op in resolved3.operations)
    apply_resolved_share_merge(source3, share3.path, resolved3)
    assert tuple(source3.db.conn.execute("SELECT sort_order,is_primary FROM contract_platforms WHERE contract_id=? AND platform_id=?", (cid3, src_pid3)).fetchone()) == (9, 1)

    # Missing source master target fails closed.
    source4, share4, _ci4, cid4, metadata4 = make_registered_share(tmp_path)
    missing_pid = _platform_id(share4.db.conn, "MISSING-PLATFORM")
    share4.db.conn.execute("INSERT INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,0)", (1, missing_pid, 1)); share4.db.conn.commit()
    before = hash_contract_snapshot(build_contract_snapshot(source4.db.conn, cid4))
    with pytest.raises(MergeOperationTargetNotFoundError):
        apply_resolved_share_merge(source4, share4.path, resolve_merge_plan(prepare_share_merge_plan(source4, share4.path)))
    assert hash_contract_snapshot(build_contract_snapshot(source4.db.conn, cid4)) == before
    assert source4.db.conn.execute("SELECT COUNT(*) FROM platforms WHERE name='MISSING-PLATFORM'").fetchone()[0] == 0
    assert source4.get_share_package(metadata4["share_package_id"])["status"] == SHARE_STATUS_OPEN


def test_cancelled_exported_package_prepare_rejected_and_registry_only(tmp_path):
    from src.models.share_models import SHARE_STATUS_CANCELLED
    from src.services.share_lifecycle_service import cancel_share_package
    from src.services.share_merge_service import SharePackageStatusError

    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE-CANCELLED")
    before_hash = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    before_revision = source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    cancel_share_package(source, metadata["source_contract_merge_uid"], metadata["share_package_id"], current_staff={"is_admin": True, "is_active": 1})

    with pytest.raises(SharePackageStatusError):
        prepare_share_merge_plan(source, share.path)

    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == SHARE_STATUS_CANCELLED
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before_hash
    assert source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0] == before_revision
    assert registry["merge_result_operations_applied"] is None
    assert registry["merge_result_operations_skipped"] is None
    assert not registry["merged_at"]
    assert not registry["merge_result_sha256"]


def test_prepared_plan_cancelled_before_apply_is_rejected_without_mutation(tmp_path, monkeypatch):
    from src.models.share_models import SHARE_STATUS_CANCELLED
    from src.services.share_lifecycle_service import cancel_share_package

    source, share, _ci, cid, metadata = make_registered_share(tmp_path)
    _edit_note(share, "REMOTE-RACE")
    plan = prepare_share_merge_plan(source, share.path)
    resolved = resolve_merge_plan(plan)
    before_hash = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    before_revision = source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0]
    cancel_share_package(source, metadata["source_contract_merge_uid"], metadata["share_package_id"], current_staff={"is_admin": True, "is_active": 1})
    apply_calls = []

    def fail_if_operation_starts(*args, **kwargs):
        apply_calls.append((args, kwargs))
        raise AssertionError("operation apply should not start after cancellation")

    monkeypatch.setattr("src.services.share_merge_apply_service._apply_operation", fail_if_operation_starts)

    with pytest.raises(ShareMergeApplyValidationError):
        apply_resolved_share_merge(source, share.path, resolved, require_backup=False)

    assert apply_calls == []

    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == SHARE_STATUS_CANCELLED
    assert hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid)) == before_hash
    assert source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0] == before_revision
    assert registry["merge_result_operations_applied"] is None
    assert registry["merge_result_operations_skipped"] is None
    assert not registry["merged_at"]
    assert not registry["merge_result_sha256"]
