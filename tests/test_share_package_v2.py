import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from src.domain.contract_snapshot import build_contract_snapshot, hash_contract_snapshot, serialize_contract_snapshot, CONTRACT_SNAPSHOT_FORMAT_VERSION
from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.models.share_models import SHARE_FORMAT_V2, SHARE_STATUS_OPEN, ShareBaseSnapshot, SharePackageRegistryEntry
from src.services.share_package_service import (
    build_base_snapshot_from_source,
    build_current_share_snapshot,
    make_v2_metadata,
    read_share_base_snapshot,
    read_share_metadata,
    validate_share_package,
    write_share_base_snapshot,
    write_share_metadata,
)
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.sts_store import STSStore


def contract(no="C-1"):
    return ContractInfo(no=no, platform="AKINCI", user="SSB", yi_yd="Yİ", contract_type="Ana Sözleşme", signature_date="2026-01-01", t0_date="2026-01-02", t0_months=1, completion_date="2026-02-02", status="PLAN", note="base")


def make_source(tmp_path):
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    store = STSStore(tmp_path / "source.sts")
    ci = contract()
    sys = SystemInfo("SYS", {"C": 1})
    delivery = DeliveryInfo("DEL", "PLAN", "", "", {"C": 1}, {"C": 0})
    cid = store.write_contract(ci, [sys], {"SYS": [delivery]})
    return store, ci, cid


def make_share_from_source(tmp_path):
    source, ci, cid = make_source(tmp_path)
    created_at = "2026-07-07T00:00:00"
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at=created_at)
    share = STSStore(tmp_path / "share.sts")
    loaded_ci, systems, deliveries = source.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    loaded_ci.entry_start_row = loaded_ci.id = loaded_ci.contract_id = 0
    loaded_ci.platform_ids = []; loaded_ci.platforms = []; loaded_ci.platform_id = 0; loaded_ci.primary_platform_id = 0
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
    return source, share, ci, cid, base, metadata


def test_v1_share_metadata_is_supported_without_merge(tmp_path):
    p = tmp_path / "v1.sts"
    db = STSStore(p); db.db.close()
    write_share_metadata(p, {"share_mode": "true", "permission_mode": "view"})
    result = validate_share_package(p)
    assert result.is_share_package
    assert result.format_version == 1
    assert result.is_supported
    assert result.is_valid
    assert not result.supports_merge


def test_v2_metadata_source_identity_and_base_snapshot(tmp_path):
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path)
    result = validate_share_package(share.path)
    assert result.is_valid and result.supports_merge
    uuid.UUID(result.metadata.share_package_id)
    assert result.metadata.source_sts_instance_id == source.sts_instance_id()
    assert source.sts_instance_id() != share.sts_instance_id()
    assert result.metadata.source_contract_merge_uid == ci.merge_uid
    assert share.db.conn.execute("SELECT merge_uid FROM contracts").fetchone()[0] == ci.merge_uid
    stored = read_share_base_snapshot(share.path)
    assert stored.snapshot_sha256 == base.snapshot_sha256
    assert json.loads(stored.snapshot_json)["contract"]["merge_uid"] == ci.merge_uid
    assert result.metadata.base_revision == ci.revision


def test_base_snapshot_is_from_source_and_immutable_while_current_changes(tmp_path):
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path)
    before_base = read_share_base_snapshot(share.path)
    current_json, current_hash = build_current_share_snapshot(share.path)
    loaded_ci, systems, deliveries = share.load_contract_structure("AKINCI", ci.no, contract_type=ci.contract_type)
    loaded_ci.note = "remote edit"
    share.write_contract(loaded_ci, systems, deliveries)
    after_base = read_share_base_snapshot(share.path)
    edited_json, edited_hash = build_current_share_snapshot(share.path)
    assert before_base == after_base
    assert current_hash != edited_hash
    source_hash = hash_contract_snapshot(build_contract_snapshot(source.db.conn, cid))
    assert before_base.snapshot_sha256 == source_hash


def test_base_snapshot_integrity_failures(tmp_path):
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path)
    conn = sqlite3.connect(share.path)
    conn.execute("UPDATE share_base_snapshot SET snapshot_json=? WHERE id=1", ('{"tampered":true}',))
    conn.commit(); conn.close()
    assert not validate_share_package(share.path).is_valid
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path / "case2")
    conn = sqlite3.connect(share.path)
    conn.execute("UPDATE share_base_snapshot SET snapshot_sha256='bad' WHERE id=1")
    conn.commit(); conn.close()
    assert not validate_share_package(share.path).is_valid
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path / "case3")
    raw = read_share_metadata(share.path); raw["base_snapshot_sha256"] = "bad"
    write_share_metadata(share.path, raw)
    assert not validate_share_package(share.path).is_valid


def test_unsupported_share_format_is_invalid(tmp_path):
    p = tmp_path / "future.sts"
    db = STSStore(p); db.db.close()
    write_share_metadata(p, {"share_mode": "true", "share_format_version": "999"})
    result = validate_share_package(p)
    assert result.is_share_package
    assert result.format_version == 999
    assert not result.is_supported
    assert not result.is_valid


def test_share_registry_idempotent_and_conflict_detection(tmp_path):
    source, share, ci, cid, base, metadata = make_share_from_source(tmp_path)
    entry = SharePackageRegistryEntry(
        share_package_id=metadata["share_package_id"],
        contract_id=cid,
        contract_merge_uid=ci.merge_uid,
        source_contract_revision=ci.revision,
        permission_mode="edit",
        share_format_version=SHARE_FORMAT_V2,
        snapshot_format_version=CONTRACT_SNAPSHOT_FORMAT_VERSION,
        base_snapshot_sha256=base.snapshot_sha256,
        created_at=metadata["created_at"],
        created_by_staff_id=42,
        created_by_username="tester",
        created_by_full_name="Test User",
        exported_filename="share.sts",
        status=SHARE_STATUS_OPEN,
    )
    first_id = source.register_share_package(entry)
    second_id = source.register_share_package(entry)
    assert first_id == second_id
    row = source.get_share_package(entry.share_package_id)
    assert row["status"] == SHARE_STATUS_OPEN
    assert row["contract_merge_uid"] == ci.merge_uid
    assert source.list_contract_share_packages(ci.merge_uid)[0]["share_package_id"] == entry.share_package_id
    changed = SharePackageRegistryEntry(**{**entry.as_db_values(), "base_snapshot_sha256": "different"})
    with pytest.raises(ValueError):
        source.register_share_package(changed)


def test_base_snapshot_write_is_immutable(tmp_path):
    p = tmp_path / "base.sts"
    db = STSStore(p); db.db.close()
    s1 = ShareBaseSnapshot(1, "c", '{"a":1}', hash_contract_snapshot({"a": 1}), "now")
    write_share_base_snapshot(p, s1)
    write_share_base_snapshot(p, s1)
    s2 = ShareBaseSnapshot(1, "c", '{"a":2}', hash_contract_snapshot({"a": 2}), "now")
    with pytest.raises(ValueError):
        write_share_base_snapshot(p, s2)
