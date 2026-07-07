from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from src.domain.contract_snapshot import build_contract_snapshot
from src.domain.share_merge import build_merge_plan
from src.models.share_models import SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED
from src.models.share_merge_models import MergePlan
from src.services.share_package_service import read_share_base_snapshot, validate_share_package

_log = logging.getLogger(__name__)


class ShareMergePreparationError(RuntimeError):
    pass


class UnsupportedShareMergePackageError(ShareMergePreparationError):
    pass


class ShareSourceMismatchError(ShareMergePreparationError):
    pass


class UnknownSharePackageError(ShareMergePreparationError):
    pass


class PackageRegistryMismatchError(ShareMergePreparationError):
    pass


class SourceContractNotFoundError(ShareMergePreparationError):
    pass


class SharePackageStatusError(ShareMergePreparationError):
    pass


def _source_conn_and_owner(source_store_or_conn: Any) -> tuple[sqlite3.Connection, bool]:
    conn = getattr(getattr(source_store_or_conn, "db", None), "conn", None)
    if isinstance(conn, sqlite3.Connection):
        return conn, False
    if isinstance(source_store_or_conn, sqlite3.Connection):
        return source_store_or_conn, False
    raise TypeError("source_store_or_conn STSStore veya sqlite3.Connection olmalı.")


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in keys()}
    return dict(row)


def _source_instance_id(source_store_or_conn: Any, conn: sqlite3.Connection) -> str:
    if hasattr(source_store_or_conn, "sts_instance_id"):
        return str(source_store_or_conn.sts_instance_id() or "")
    row = conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()
    return str(row[0] or "") if row else ""


def prepare_share_merge_plan(source_store_or_conn: Any, share_path: Path | str) -> MergePlan:
    """Read-only V2 share merge preparation.

    Validates package provenance, reads BASE from share_base_snapshot, builds LOCAL
    from the source STS DB, builds REMOTE from the share STS DB, and returns a
    pure MergePlan. This function does not mutate source/share databases.
    """
    validation = validate_share_package(share_path)
    if not validation.is_share_package or not validation.is_supported or not validation.is_valid or not validation.supports_merge or not validation.metadata:
        raise UnsupportedShareMergePackageError("V2 merge destekleyen geçerli paylaşım paketi değil: " + "; ".join(validation.errors))
    metadata = validation.metadata
    conn, _ = _source_conn_and_owner(source_store_or_conn)
    source_instance_id = _source_instance_id(source_store_or_conn, conn)
    if source_instance_id != metadata.source_sts_instance_id:
        raise ShareSourceMismatchError("Paylaşım paketi farklı bir STS instance için oluşturulmuş.")
    registry = None
    cur = conn.execute("SELECT * FROM share_packages WHERE share_package_id=?", (metadata.share_package_id,))
    row = cur.fetchone()
    if row:
        if hasattr(row, "keys"):
            registry = _row_to_dict(row)
        else:
            registry = {desc[0]: value for desc, value in zip(cur.description, row)}
    if not registry:
        raise UnknownSharePackageError("Paylaşım paketi ana STS registry içinde bulunamadı.")
    if str(registry.get("status") or "") in {SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED}:
        raise SharePackageStatusError("Paylaşım paketi durumu merge hazırlığına kapalı.")
    if str(registry.get("contract_merge_uid") or "") != metadata.source_contract_merge_uid:
        raise PackageRegistryMismatchError("Registry contract merge UID metadata ile uyuşmuyor.")
    if str(registry.get("base_snapshot_sha256") or "") != metadata.base_snapshot_sha256:
        raise PackageRegistryMismatchError("Registry base snapshot hash metadata ile uyuşmuyor.")
    if int(registry.get("share_format_version") or 0) != int(metadata.format_version or 0):
        raise PackageRegistryMismatchError("Registry share format version metadata ile uyuşmuyor.")

    base = read_share_base_snapshot(share_path)
    if base is None:
        raise UnsupportedShareMergePackageError("Base snapshot bulunamadı.")
    try:
        base_snapshot = json.loads(base.snapshot_json)
    except Exception as exc:
        raise UnsupportedShareMergePackageError("Base snapshot JSON okunamadı.") from exc

    source_contract = conn.execute("SELECT id FROM contracts WHERE merge_uid=?", (metadata.source_contract_merge_uid,)).fetchone()
    if not source_contract:
        raise SourceContractNotFoundError("Kaynak sözleşme ana STS içinde bulunamadı.")
    local_snapshot = build_contract_snapshot(conn, int(source_contract[0]))

    share_conn = sqlite3.connect(str(share_path))
    share_conn.row_factory = sqlite3.Row
    try:
        remote_contract = share_conn.execute("SELECT id FROM contracts WHERE merge_uid=?", (metadata.source_contract_merge_uid,)).fetchone()
        if not remote_contract:
            raise SourceContractNotFoundError("Paylaşım STS içinde kaynak sözleşme bulunamadı.")
        remote_snapshot = build_contract_snapshot(share_conn, int(remote_contract[0]))
    finally:
        share_conn.close()

    plan = build_merge_plan(base_snapshot, local_snapshot, remote_snapshot)
    _log.debug(
        "Prepared share merge plan package=%s contract=%s base=%s local=%s remote=%s conflicts=%s safe_remote=%s",
        metadata.share_package_id,
        metadata.source_contract_merge_uid,
        plan.base_snapshot_hash[:12],
        plan.local_snapshot_hash[:12],
        plan.remote_snapshot_hash[:12],
        len(plan.conflicts),
        plan.safe_remote_change_count,
    )
    return plan
