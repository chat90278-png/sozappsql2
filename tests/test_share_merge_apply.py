import uuid
from pathlib import Path

import pytest

from src.domain.contract_snapshot import CONTRACT_SNAPSHOT_FORMAT_VERSION
from src.domain.share_merge_resolution import resolve_merge_plan
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.models.share_models import SHARE_FORMAT_V2, SHARE_STATUS_MERGED, SHARE_STATUS_OPEN, SharePackageRegistryEntry
from src.models.share_merge_resolution_models import MergeOperationKind
from src.services.share_merge_apply_service import (
    MergeSourceChangedError,
    SharePackageAlreadyAppliedError,
    apply_resolved_share_merge,
)
from src.services.share_merge_service import prepare_share_merge_plan
from src.services.share_package_service import build_base_snapshot_from_source, make_v2_metadata, write_share_base_snapshot, write_share_metadata
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.sts_store import STSStore


def contract(no="C-1"):
    return ContractInfo(
        no=no,
        platform="AKINCI",
        user="SSB",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="2026-01-01",
        t0_date="2026-01-02",
        t0_months=1,
        completion_date="2026-02-02",
        status="BASE",
        note="base",
    )


def make_registered_share(tmp_path):
    source = STSStore(Path(tmp_path) / "source.sts")
    ci = contract()
    system = SystemInfo("SYS", {"C": 1})
    delivery = DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0})
    cid = source.write_contract(ci, [system], {"SYS": [delivery]})
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
        permission_mode="edit",
        source_sts_instance_id=source.sts_instance_id(),
        source_schema_version=CURRENT_SCHEMA_VERSION,
        source_contract_id=cid,
        source_contract_merge_uid=base.contract_merge_uid,
        source_contract_no=ci.no,
        base_revision=ci.revision,
        base_snapshot_sha256=base.snapshot_sha256,
        created_at=created_at,
        created_by_staff_id=42,
        created_by_username="tester",
        created_by_full_name="Test User",
        document_count=0,
        document_bytes=0,
    )
    metadata["contract_id"] = str(package_contract_id)
    write_share_metadata(share.path, metadata)
    write_share_base_snapshot(share.path, base)
    source.register_share_package(
        SharePackageRegistryEntry(
            share_package_id=package_id,
            contract_id=cid,
            contract_merge_uid=base.contract_merge_uid,
            source_contract_revision=ci.revision,
            permission_mode="edit",
            share_format_version=SHARE_FORMAT_V2,
            snapshot_format_version=CONTRACT_SNAPSHOT_FORMAT_VERSION,
            base_snapshot_sha256=base.snapshot_sha256,
            created_at=created_at,
            created_by_staff_id=42,
            created_by_username="tester",
            created_by_full_name="Test User",
            exported_filename="share.sts",
            status=SHARE_STATUS_OPEN,
        )
    )
    return source, share, ci, cid, metadata


def test_apply_contract_field_keeps_local_only_data_and_updates_registry_backup_revision(tmp_path):
    source, share, ci, cid, metadata = make_registered_share(tmp_path)
    local_ci, local_systems, local_deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    local_ci.status = "LOCAL"
    source.write_contract(local_ci, local_systems, local_deliveries)
    revision_before = source.db.conn.execute("SELECT revision FROM contracts WHERE id=?", (cid,)).fetchone()[0]

    remote_ci, remote_systems, remote_deliveries = share.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    remote_ci.note = "remote note"
    share.write_contract(remote_ci, remote_systems, remote_deliveries)

    plan = prepare_share_merge_plan(source, share.path)
    resolved = resolve_merge_plan(plan)
    assert {op.operation_kind for op in resolved.operations} == {MergeOperationKind.SET_CONTRACT_FIELD}

    result = apply_resolved_share_merge(source, share.path, resolved)

    row = source.db.conn.execute("SELECT status,note,revision FROM contracts WHERE id=?", (cid,)).fetchone()
    assert row["status"] == "LOCAL"
    assert row["note"] == "remote note"
    assert row["revision"] == revision_before + 1
    registry = source.get_share_package(metadata["share_package_id"])
    assert registry["status"] == SHARE_STATUS_MERGED
    assert registry["last_remote_snapshot_sha256"] == result.remote_snapshot_hash
    assert registry["merge_result_sha256"] == result.post_apply_snapshot_hash
    assert Path(result.backup_path).exists()
    assert result.operations_applied == len(resolved.operations)


def test_apply_rejects_stale_local_plan_before_backup_or_write(tmp_path):
    source, share, ci, cid, metadata = make_registered_share(tmp_path)
    remote_ci, remote_systems, remote_deliveries = share.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    remote_ci.note = "remote note"
    share.write_contract(remote_ci, remote_systems, remote_deliveries)
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))

    local_ci, local_systems, local_deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    local_ci.status = "changed after plan"
    source.write_contract(local_ci, local_systems, local_deliveries)

    with pytest.raises(MergeSourceChangedError):
        apply_resolved_share_merge(source, share.path, resolved)
    assert not list((Path(tmp_path) / "yedekler").glob("*pre_merge*"))


def test_apply_adds_remote_document_blob_and_rejects_duplicate_full_merge(tmp_path):
    source, share, ci, cid, metadata = make_registered_share(tmp_path)
    remote_doc = Path(tmp_path) / "remote.txt"
    remote_doc.write_text("remote bytes", encoding="utf-8")
    share.add_contract_file("AKINCI", ci.no, remote_doc, ci.contract_type)
    resolved = resolve_merge_plan(prepare_share_merge_plan(source, share.path))
    assert any(op.operation_kind == MergeOperationKind.ADD_DOCUMENT_FILE for op in resolved.operations)

    result = apply_resolved_share_merge(source, share.path, resolved)

    file_row = source.db.conn.execute("SELECT filename,sha256,content_blob FROM contract_files WHERE contract_id=?", (cid,)).fetchone()
    assert file_row["filename"] == "remote.txt"
    assert bytes(file_row["content_blob"]) == b"remote bytes"
    assert result.registry_status == SHARE_STATUS_MERGED
    with pytest.raises(SharePackageAlreadyAppliedError):
        apply_resolved_share_merge(source, share.path, resolved)
