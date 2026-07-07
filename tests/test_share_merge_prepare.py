import sqlite3
import uuid
from pathlib import Path

import pytest

from src.domain.contract_snapshot import CONTRACT_SNAPSHOT_FORMAT_VERSION, build_contract_snapshot, hash_contract_snapshot
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.models.share_models import SHARE_FORMAT_V2, SHARE_STATUS_CANCELLED, SHARE_STATUS_OPEN, SharePackageRegistryEntry
from src.models.share_merge_models import MergeChangeKind
from src.services.share_merge_service import (
    PackageRegistryMismatchError,
    SharePackageStatusError,
    ShareSourceMismatchError,
    UnknownSharePackageError,
    UnsupportedShareMergePackageError,
    prepare_share_merge_plan,
)
from src.services.share_package_service import (
    build_base_snapshot_from_source,
    make_v2_metadata,
    read_share_metadata,
    write_share_base_snapshot,
    write_share_metadata,
)
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.sts_store import STSStore


def contract(no="C-1"):
    return ContractInfo(no=no, platform="AKINCI", user="SSB", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="2026-01-01", t0_date="2026-01-02", t0_months=1, completion_date="2026-02-02", status="BASE", note="base")


def make_source(tmp_path):
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    store = STSStore(Path(tmp_path) / "source.sts")
    ci = contract()
    system = SystemInfo("SYS", {"C": 1})
    delivery = DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0})
    cid = store.write_contract(ci, [system], {"SYS": [delivery]})
    return store, ci, cid


def make_registered_share(tmp_path, permission="edit"):
    source, ci, cid = make_source(tmp_path)
    created_at = "2026-07-07T00:00:00"
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at=created_at)
    share = STSStore(Path(tmp_path) / "share.sts")
    loaded_ci, systems, deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    loaded_ci.entry_start_row = loaded_ci.id = loaded_ci.contract_id = 0
    loaded_ci.platform_ids = []
    loaded_ci.platforms = []
    loaded_ci.platform_id = 0
    loaded_ci.primary_platform_id = 0
    package_contract_id = share.write_contract(loaded_ci, systems, deliveries)
    package_id = str(uuid.uuid4())
    metadata = make_v2_metadata(
        share_package_id=package_id,
        permission_mode=permission,
        source_sts_instance_id=source.sts_instance_id(),
        source_schema_version=CURRENT_SCHEMA_VERSION,
        source_contract_id=cid,
        source_contract_merge_uid=base.contract_merge_uid,
        source_contract_no=ci.no,
        base_revision=ci.revision,
        base_snapshot_sha256=base.snapshot_sha256,
        created_at=created_at,
        created_by_staff_id=7,
        created_by_username="tester",
        created_by_full_name="Test User",
        document_count=0,
        document_bytes=0,
    )
    metadata["contract_id"] = str(package_contract_id)
    write_share_metadata(share.path, metadata)
    write_share_base_snapshot(share.path, base)
    entry = SharePackageRegistryEntry(
        share_package_id=package_id,
        contract_id=cid,
        contract_merge_uid=base.contract_merge_uid,
        source_contract_revision=ci.revision,
        permission_mode=permission,
        share_format_version=SHARE_FORMAT_V2,
        snapshot_format_version=CONTRACT_SNAPSHOT_FORMAT_VERSION,
        base_snapshot_sha256=base.snapshot_sha256,
        created_at=created_at,
        created_by_staff_id=7,
        created_by_username="tester",
        created_by_full_name="Test User",
        exported_filename="share.sts",
        status=SHARE_STATUS_OPEN,
    )
    source.register_share_package(entry)
    return source, share, ci, cid, base, metadata


def change(plan, path):
    return next(c for c in plan.changes if c.field_path == path)


def test_prepare_v2_open_package_builds_read_only_plan(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path)
    local_ci, local_systems, local_deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    local_ci.status = "LOCAL"
    source.write_contract(local_ci, local_systems, local_deliveries)
    remote_ci, remote_systems, remote_deliveries = share.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    remote_ci.note = "remote note"
    share.write_contract(remote_ci, remote_systems, remote_deliveries)

    before_source_packages = [dict(r) for r in source.db.conn.execute("SELECT * FROM share_packages").fetchall()]
    before_share_metadata = read_share_metadata(share.path)
    plan = prepare_share_merge_plan(source, share.path)
    after_source_packages = [dict(r) for r in source.db.conn.execute("SELECT * FROM share_packages").fetchall()]
    after_share_metadata = read_share_metadata(share.path)

    assert change(plan, "contract.status").change_kind == MergeChangeKind.LOCAL_ONLY
    assert change(plan, "contract.note").change_kind == MergeChangeKind.REMOTE_ONLY
    assert not plan.conflicts
    assert before_source_packages == after_source_packages
    assert before_share_metadata == after_share_metadata


def test_prepare_fails_closed_for_source_mismatch(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path / "a")
    other = STSStore(tmp_path / "other.sts")
    with pytest.raises(ShareSourceMismatchError):
        prepare_share_merge_plan(other, share.path)


def test_prepare_fails_closed_for_unknown_registry(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path)
    source.db.conn.execute("DELETE FROM share_packages WHERE share_package_id=?", (metadata["share_package_id"],))
    source.db.conn.commit()
    with pytest.raises(UnknownSharePackageError):
        prepare_share_merge_plan(source, share.path)


def test_prepare_fails_closed_for_registry_mismatches(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path / "uid")
    source.db.conn.execute("UPDATE share_packages SET contract_merge_uid='wrong' WHERE share_package_id=?", (metadata["share_package_id"],))
    source.db.conn.commit()
    with pytest.raises(PackageRegistryMismatchError):
        prepare_share_merge_plan(source, share.path)

    source, share, ci, cid, base, metadata = make_registered_share(tmp_path / "hash")
    source.db.conn.execute("UPDATE share_packages SET base_snapshot_sha256='wrong' WHERE share_package_id=?", (metadata["share_package_id"],))
    source.db.conn.commit()
    with pytest.raises(PackageRegistryMismatchError):
        prepare_share_merge_plan(source, share.path)


def test_prepare_fails_before_engine_for_invalid_v2_and_v1(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path / "invalid")
    conn = sqlite3.connect(share.path)
    conn.execute("UPDATE share_base_snapshot SET snapshot_json=? WHERE id=1", ('{"tampered": true}',))
    conn.commit(); conn.close()
    with pytest.raises(UnsupportedShareMergePackageError):
        prepare_share_merge_plan(source, share.path)

    v1 = tmp_path / "v1.sts"
    db = STSStore(v1); db.db.close()
    write_share_metadata(v1, {"share_mode": "true", "permission_mode": "edit"})
    with pytest.raises(UnsupportedShareMergePackageError):
        prepare_share_merge_plan(source, v1)


def test_prepare_rejects_cancelled_package(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path)
    source.db.conn.execute("UPDATE share_packages SET status=? WHERE share_package_id=?", (SHARE_STATUS_CANCELLED, metadata["share_package_id"]))
    source.db.conn.commit()
    with pytest.raises(SharePackageStatusError):
        prepare_share_merge_plan(source, share.path)


def test_prepare_does_not_shortcut_with_revision_when_local_document_snapshot_changes(tmp_path):
    source, share, ci, cid, base, metadata = make_registered_share(tmp_path)
    # Simulate a direct document metadata mutation without relying on contract revision.
    source.db.conn.execute(
        "INSERT INTO contract_files(contract_id, merge_uid, folder_id, filename, original_path, file_ext, mime_type, size_bytes, sha256, content_blob, note, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, "doc-uid", None, "doc.txt", "doc.txt", ".txt", "text/plain", 3, "abc", b"abc", "local doc", "now", "now"),
    )
    source.db.conn.commit()
    plan = prepare_share_merge_plan(source, share.path)
    doc_change = next(c for c in plan.changes if c.entity_uid == "doc-uid" and c.change_kind == MergeChangeKind.LOCAL_ADDED)
    assert doc_change.entity_uid == "doc-uid"
    assert source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0] == ci.revision
