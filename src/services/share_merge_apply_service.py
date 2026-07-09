from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.domain.contract_snapshot import build_contract_snapshot, hash_contract_snapshot
from src.domain.share_merge_resolution import hash_merge_operations
from src.models.share_merge_apply_models import (
    AppliedMergeOperationResult,
    ShareMergeApplyResult,
    ShareMergeApplyStatus,
    ShareMergeBackupInfo,
)
from src.models.share_merge_resolution_models import MergeOperation, MergeOperationKind, ResolvedMergePlan
from src.models.share_models import (
    SHARE_FORMAT_V2,
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
)
from src.services.share_package_service import read_share_base_snapshot, validate_share_package
from src.services.sts_database import device_name, now_iso

_log = logging.getLogger(__name__)


class ShareMergeApplyError(RuntimeError):
    pass


class ShareMergeApplyValidationError(ShareMergeApplyError):
    pass


class SharePackageAlreadyAppliedError(ShareMergeApplyValidationError):
    pass


class StaleMergePlanError(ShareMergeApplyValidationError):
    pass


class MergePackageChangedError(ShareMergeApplyValidationError):
    pass


class MergeSourceChangedError(StaleMergePlanError):
    pass


class MergeOperationApplyError(ShareMergeApplyError):
    pass


class MergeOperationTargetNotFoundError(MergeOperationApplyError):
    pass


class MergeOperationTargetAmbiguousError(MergeOperationApplyError):
    pass


class RemoteDocumentNotFoundError(MergeOperationApplyError):
    pass


class RemoteDocumentHashMismatchError(MergeOperationApplyError):
    pass


class MergeBackupError(ShareMergeApplyError):
    pass


class MergeTransactionError(ShareMergeApplyError):
    pass


class MergePostValidationError(ShareMergeApplyError):
    pass


class MergeRegistryUpdateError(ShareMergeApplyError):
    pass


CONTRACT_FIELD_DB_COLUMN = {
    "contract_no": "contract_no",
    "yi_yd": "yi_yd",
    "contract_type": "contract_type",
    "type_display": "type_display",
    "link_type": "link_type",
    "status": "status",
    "signed_date": "signed_date",
    "t0_date": "t0_date",
    "t0_months": "t0_months",
    "completion_date": "completion_date",
    "acceptance_date": "acceptance_date",
    "content": "content",
    "note": "note",
    "is_main": "is_main",
}
SYSTEM_FIELD_DB_COLUMN = {
    "platform_id": "platform_id",
    "name": "name",
    "status": "status",
    "completion_date": "completion_date",
    "acceptance_date": "acceptance_date",
    "note": "note",
    "sort_order": "sort_order",
    "payload_json": "payload_json",
}
DELIVERY_FIELD_DB_COLUMN = {
    "name": "name",
    "status": "status",
    "planned_acceptance_date": "planned_acceptance_date",
    "acceptance_date": "acceptance_date",
    "note": "note",
    "sort_order": "sort_order",
    "payload_json": "payload_json",
    "delivery_user_id": "delivery_user_id",
}
FOLDER_FIELD_DB_COLUMN = {"name": "name"}
FILE_FIELD_DB_COLUMN = {
    "filename": "filename",
    "file_ext": "file_ext",
    "mime_type": "mime_type",
    "size_bytes": "size_bytes",
    "sha256": "sha256",
    "note": "note",
}


@dataclass
class _ApplyContext:
    source: sqlite3.Connection
    source_path: Path
    share_path: Path
    share: sqlite3.Connection
    contract_id: int
    contract_merge_uid: str
    contract_no: str
    share_package_id: str
    operations_hash: str
    actor: str
    current_staff_id: int


def apply_resolved_share_merge(
    source_store_or_conn: Any,
    share_path: Path | str,
    resolved_plan: ResolvedMergePlan,
    *,
    current_staff: Any = None,
    allow_partial: bool = False,
    require_backup: bool = True,
) -> ShareMergeApplyResult:
    """Apply a validated ResolvedMergePlan to the source STS with operation-only writes."""
    conn, source_path = _source_conn_and_path(source_store_or_conn)
    share_path = Path(share_path)
    actor = _actor_from_staff(current_staff, source_store_or_conn)
    staff_id = _staff_id(current_staff)

    validation_data = _preflight_validate(conn, source_store_or_conn, share_path, resolved_plan, allow_partial=allow_partial)
    metadata = validation_data["metadata"]
    contract = validation_data["contract"]
    registry = validation_data["registry"]
    current_remote_hash = validation_data["remote_hash"]
    pre_hash = validation_data["local_hash"]
    operations_hash = validation_data["operations_hash"]

    backup_info = None
    if require_backup:
        backup_info = _create_backup(conn, source_path, metadata.share_package_id)

    share_conn = sqlite3.connect(str(share_path))
    share_conn.row_factory = sqlite3.Row
    ctx = _ApplyContext(
        source=conn,
        source_path=source_path,
        share_path=share_path,
        share=share_conn,
        contract_id=int(contract["id"]),
        contract_merge_uid=str(contract["merge_uid"] or ""),
        contract_no=str(contract["contract_no"] or ""),
        share_package_id=metadata.share_package_id,
        operations_hash=operations_hash,
        actor=actor,
        current_staff_id=staff_id,
    )
    operation_results: list[AppliedMergeOperationResult] = []
    applied_ids: list[str] = []
    revision_before = int(contract["revision"] or 1)
    registry_status = SHARE_STATUS_PARTIALLY_MERGED if resolved_plan.is_partial else SHARE_STATUS_MERGED
    post_hash = pre_hash
    revision_after = revision_before
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception as exc:
            raise MergeTransactionError("BEGIN IMMEDIATE başlatılamadı.") from exc

        try:
            current_registry = _one(conn, "SELECT status FROM share_packages WHERE share_package_id=?", (metadata.share_package_id,), "Paylaşım paketi registry içinde bulunamadı.", "Paylaşım paketi registry içinde belirsiz.")
            current_status = str(current_registry["status"] or "")
            if current_status in {SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED}:
                raise ShareMergeApplyValidationError("Paylaşım paketi durumu apply için kapalı.")
            if current_status not in {SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED}:
                raise ShareMergeApplyValidationError(f"Bilinmeyen paylaşım paket durumu: {current_status}")

            for operation in resolved_plan.operations:
                result = _apply_operation(ctx, operation)
                operation_results.append(result)
                if result.status == "APPLIED":
                    applied_ids.append(operation.operation_id)

            post_snapshot = build_contract_snapshot(conn, ctx.contract_id)
            post_hash = hash_contract_snapshot(post_snapshot)
            if resolved_plan.operations and applied_ids and post_hash == pre_hash:
                _log.warning("Merge apply operations completed but snapshot hash did not change package=%s", metadata.share_package_id)

            if applied_ids and post_hash != pre_hash:
                revision_after = revision_before + 1
                conn.execute(
                    "UPDATE contracts SET revision=?,updated_at=? WHERE id=?",
                    (revision_after, now_iso(), ctx.contract_id),
                )

            if resolved_plan.is_partial:
                registry_status = SHARE_STATUS_PARTIALLY_MERGED
            elif post_hash == pre_hash and not applied_ids:
                registry_status = SHARE_STATUS_MERGED
            else:
                registry_status = SHARE_STATUS_MERGED
            _update_registry(ctx, registry_status, current_remote_hash, post_hash, len(applied_ids), len(resolved_plan.operations) - len(applied_ids))
            _insert_audit_log(ctx, registry_status, revision_before, revision_after, pre_hash, current_remote_hash, post_hash, len(resolved_plan.operations), len(applied_ids), str(backup_info.path if backup_info else ""))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        share_conn.close()

    status = ShareMergeApplyStatus.PARTIALLY_MERGED if registry_status == SHARE_STATUS_PARTIALLY_MERGED else (
        ShareMergeApplyStatus.NO_CHANGE if post_hash == pre_hash and not applied_ids else ShareMergeApplyStatus.MERGED
    )
    _log.info(
        "Share merge apply success package=%s contract=%s applied=%s revision=%s->%s post=%s registry=%s",
        metadata.share_package_id,
        metadata.source_contract_merge_uid,
        len(applied_ids),
        revision_before,
        revision_after,
        post_hash[:12],
        registry_status,
    )
    return ShareMergeApplyResult(
        share_package_id=metadata.share_package_id,
        contract_merge_uid=metadata.source_contract_merge_uid,
        status=status,
        operations_requested=len(resolved_plan.operations),
        operations_applied=len(applied_ids),
        operations_skipped=len(resolved_plan.operations) - len(applied_ids),
        operations_failed=0,
        applied_operation_ids=applied_ids,
        base_snapshot_hash=resolved_plan.base_snapshot_hash,
        pre_apply_local_snapshot_hash=pre_hash,
        remote_snapshot_hash=current_remote_hash,
        post_apply_snapshot_hash=post_hash,
        operations_hash=operations_hash,
        backup_path=str(backup_info.path if backup_info else ""),
        contract_revision_before=revision_before,
        contract_revision_after=revision_after,
        registry_status=registry_status,
        is_partial=resolved_plan.is_partial,
        success=True,
        warnings=list(validation_data["warnings"]),
        backup=backup_info,
        operation_results=operation_results,
    )


def preflight_resolved_share_merge(
    source_store_or_conn: Any,
    share_path: Path | str,
    resolved_plan: ResolvedMergePlan,
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Validate a ResolvedMergePlan before the UI asks for final confirmation.

    This is intentionally a thin public wrapper around the same validation path
    used by apply_resolved_share_merge, so preview/preflight and write behavior
    cannot drift apart.
    """
    conn, _source_path = _source_conn_and_path(source_store_or_conn)
    return _preflight_validate(conn, source_store_or_conn, Path(share_path), resolved_plan, allow_partial=allow_partial)


def _source_conn_and_path(source_store_or_conn: Any) -> tuple[sqlite3.Connection, Path]:
    conn = getattr(getattr(source_store_or_conn, "db", None), "conn", None)
    path = getattr(getattr(source_store_or_conn, "db", None), "path", None) or getattr(source_store_or_conn, "path", None)
    if not isinstance(conn, sqlite3.Connection) and isinstance(source_store_or_conn, sqlite3.Connection):
        conn = source_store_or_conn
        row = conn.execute("PRAGMA database_list").fetchone()
        path = row[2] if row else ""
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("source_store_or_conn STSStore veya sqlite3.Connection olmalı.")
    source_path = Path(path or "")
    if not source_path:
        raise MergeBackupError("Kaynak STS dosya yolu belirlenemedi.")
    conn.row_factory = sqlite3.Row
    return conn, source_path


def _source_instance_id(source_store_or_conn: Any, conn: sqlite3.Connection) -> str:
    if hasattr(source_store_or_conn, "sts_instance_id"):
        return str(source_store_or_conn.sts_instance_id() or "")
    row = conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()
    return str(row[0] or "") if row else ""


def _actor_from_staff(current_staff: Any, source_store_or_conn: Any) -> str:
    if isinstance(current_staff, dict):
        return str(current_staff.get("full_name") or current_staff.get("username") or "").strip() or "Kullanıcı"
    if current_staff is not None:
        return str(getattr(current_staff, "full_name", "") or getattr(current_staff, "username", "") or current_staff).strip() or "Kullanıcı"
    return str(getattr(source_store_or_conn, "actor", "") or "Kullanıcı")


def _staff_id(current_staff: Any) -> int:
    try:
        if isinstance(current_staff, dict):
            return int(current_staff.get("id") or current_staff.get("staff_id") or 0)
        return int(getattr(current_staff, "id", 0) or getattr(current_staff, "staff_id", 0) or 0)
    except Exception:
        return 0


def _preflight_validate(conn: sqlite3.Connection, source_store_or_conn: Any, share_path: Path, resolved_plan: ResolvedMergePlan, *, allow_partial: bool) -> dict[str, Any]:
    validation = validate_share_package(share_path)
    if not validation.is_share_package or validation.format_version != SHARE_FORMAT_V2 or not validation.is_supported or not validation.is_valid or not validation.supports_merge or not validation.metadata:
        raise ShareMergeApplyValidationError("Geçerli ve merge destekleyen V2 paylaşım paketi değil: " + "; ".join(validation.errors))
    metadata = validation.metadata
    if resolved_plan.contract_merge_uid != metadata.source_contract_merge_uid:
        raise ShareMergeApplyValidationError("Resolved plan contract merge UID metadata ile uyuşmuyor.")

    source_instance_id = _source_instance_id(source_store_or_conn, conn)
    if source_instance_id != metadata.source_sts_instance_id:
        raise ShareMergeApplyValidationError("Paylaşım paketi farklı bir STS instance için oluşturulmuş.")

    contract = _one(conn, "SELECT * FROM contracts WHERE merge_uid=?", (metadata.source_contract_merge_uid,), "Kaynak sözleşme bulunamadı.", "Kaynak sözleşme merge UID birden fazla satıra çözülüyor.")
    registry = _one(conn, "SELECT * FROM share_packages WHERE share_package_id=?", (metadata.share_package_id,), "Paylaşım paketi registry içinde bulunamadı.", "Paylaşım paketi registry içinde belirsiz.")
    if str(registry["contract_merge_uid"] or "") != metadata.source_contract_merge_uid:
        raise ShareMergeApplyValidationError("Registry contract merge UID metadata ile uyuşmuyor.")
    if str(registry["base_snapshot_sha256"] or "") != metadata.base_snapshot_sha256:
        raise ShareMergeApplyValidationError("Registry base snapshot hash metadata ile uyuşmuyor.")
    if int(registry["share_format_version"] or 0) != int(metadata.format_version or 0):
        raise ShareMergeApplyValidationError("Registry share format version metadata ile uyuşmuyor.")
    if int(registry["snapshot_format_version"] or 0) != int(metadata.snapshot_format_version or 0):
        raise ShareMergeApplyValidationError("Registry snapshot format version metadata ile uyuşmuyor.")

    base = read_share_base_snapshot(share_path)
    if base is None:
        raise ShareMergeApplyValidationError("Base snapshot bulunamadı.")
    try:
        base_snapshot = json.loads(base.snapshot_json)
    except Exception as exc:
        raise ShareMergeApplyValidationError("Base snapshot JSON okunamadı.") from exc
    base_hash = hash_contract_snapshot(base_snapshot)
    if base_hash != metadata.base_snapshot_sha256 or base_hash != resolved_plan.base_snapshot_hash:
        raise ShareMergeApplyValidationError("Base snapshot hash apply öncesi doğrulanamadı.")

    share_conn = sqlite3.connect(str(share_path))
    share_conn.row_factory = sqlite3.Row
    try:
        remote_contract = _one(share_conn, "SELECT id FROM contracts WHERE merge_uid=?", (metadata.source_contract_merge_uid,), "Paylaşım sözleşmesi bulunamadı.", "Paylaşım sözleşmesi belirsiz.")
        remote_snapshot = build_contract_snapshot(share_conn, int(remote_contract["id"]))
        remote_hash = hash_contract_snapshot(remote_snapshot)
    finally:
        share_conn.close()

    status = str(registry["status"] or "")
    if status in {SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED}:
        raise ShareMergeApplyValidationError("Paylaşım paketi durumu apply için kapalı.")
    if status not in {SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED}:
        raise ShareMergeApplyValidationError(f"Bilinmeyen paylaşım paket durumu: {status}")
    if status == SHARE_STATUS_MERGED and str(registry["last_remote_snapshot_sha256"] or "") == remote_hash:
        raise SharePackageAlreadyAppliedError("Aynı remote snapshot daha önce tamamen merge edilmiş.")

    local_snapshot = build_contract_snapshot(conn, int(contract["id"]))
    local_hash = hash_contract_snapshot(local_snapshot)

    if remote_hash != resolved_plan.remote_snapshot_hash:
        raise MergePackageChangedError("Paylaşım paketi resolved plan hazırlandıktan sonra değişmiş.")
    if local_hash != resolved_plan.local_snapshot_hash:
        raise MergeSourceChangedError("Ana STS resolved plan hazırlandıktan sonra değişmiş; plan yeniden hazırlanmalı.")

    operations_hash = hash_merge_operations(resolved_plan.operations)
    if operations_hash != resolved_plan.operations_hash:
        raise ShareMergeApplyValidationError("Resolved plan operations_hash doğrulanamadı.")
    seen: set[str] = set()
    for operation in resolved_plan.operations:
        if not isinstance(operation.operation_kind, MergeOperationKind):
            raise ShareMergeApplyValidationError(f"Bilinmeyen operation kind: {operation.operation_kind}")
        if not operation.operation_id or operation.operation_id in seen:
            raise ShareMergeApplyValidationError("Operation ID değerleri boş veya duplicate.")
        seen.add(operation.operation_id)
    if resolved_plan.has_structural_issues:
        raise ShareMergeApplyValidationError("Resolved plan structural issue içeriyor.")
    if (resolved_plan.has_unresolved_conflicts or resolved_plan.is_partial) and not allow_partial:
        raise ShareMergeApplyValidationError("Partial/unresolved merge plan explicit allow_partial olmadan uygulanamaz.")

    return {
        "metadata": metadata,
        "contract": contract,
        "registry": registry,
        "base_hash": base_hash,
        "local_hash": local_hash,
        "remote_hash": remote_hash,
        "operations_hash": operations_hash,
        "warnings": list(validation.warnings),
    }


def _create_backup(conn: sqlite3.Connection, source_path: Path, share_package_id: str) -> ShareMergeBackupInfo:
    try:
        backup_dir = source_path.parent / "yedekler"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = str(share_package_id or "share")[:8]
        base = backup_dir / f"{source_path.stem}__pre_merge__{prefix}__{stamp}{source_path.suffix}"
        target = base
        counter = 2
        while target.exists():
            target = backup_dir / f"{base.stem}__{counter}{base.suffix}"
            counter += 1
        dest = sqlite3.connect(str(target))
        try:
            conn.backup(dest)
            dest.commit()
            row = dest.execute("PRAGMA integrity_check").fetchone()
            integrity = str(row[0] if row else "")
        finally:
            dest.close()
        if integrity.lower() != "ok":
            raise MergeBackupError(f"Backup integrity_check başarısız: {integrity}")
        return ShareMergeBackupInfo(path=str(target), size_bytes=target.stat().st_size, integrity_check=integrity)
    except MergeBackupError:
        raise
    except Exception as exc:
        raise MergeBackupError("Merge öncesi SQLite backup oluşturulamadı.") from exc


def _one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...], missing: str, ambiguous: str) -> sqlite3.Row:
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        raise MergeOperationTargetNotFoundError(missing)
    if len(rows) > 1:
        raise MergeOperationTargetAmbiguousError(ambiguous)
    return rows[0]


def _value(operation: MergeOperation) -> Any:
    return operation.value if operation.value_present else None


def _apply_operation(ctx: _ApplyContext, operation: MergeOperation) -> AppliedMergeOperationResult:
    handler = _HANDLERS.get(operation.operation_kind)
    if handler is None:
        raise MergeOperationApplyError(f"Operation handler bulunamadı: {operation.operation_kind}")
    handler(ctx, operation)
    return AppliedMergeOperationResult(
        operation_id=operation.operation_id,
        operation_kind=operation.operation_kind.value,
        entity_kind=operation.entity_kind.value,
        entity_uid=operation.entity_uid,
    )


def _resolve_by_uid(ctx: _ApplyContext, table: str, uid: str) -> sqlite3.Row:
    return _one(ctx.source, f"SELECT * FROM {table} WHERE contract_id=? AND merge_uid=?", (ctx.contract_id, str(uid or "")), f"{table} target bulunamadı: {uid}", f"{table} target belirsiz: {uid}")


def _component_id(ctx: _ApplyContext, name: str, *, create: bool = True) -> int:
    clean = str(name or "").strip()
    if not clean:
        raise MergeOperationTargetNotFoundError("Bileşen adı boş.")
    rows = ctx.source.execute("SELECT id FROM components WHERE name=?", (clean,)).fetchall()
    if len(rows) > 1:
        raise MergeOperationTargetAmbiguousError(f"Bileşen belirsiz: {clean}")
    if rows:
        return int(rows[0]["id"])
    if not create:
        raise MergeOperationTargetNotFoundError(f"Bileşen bulunamadı: {clean}")
    ts = now_iso()
    ctx.source.execute("INSERT INTO components(name,created_at,updated_at) VALUES(?,?,?)", (clean, ts, ts))
    return int(ctx.source.execute("SELECT last_insert_rowid()").fetchone()[0])


def _set_contract_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    column = CONTRACT_FIELD_DB_COLUMN.get(op.field_name)
    if not column:
        raise MergeOperationApplyError(f"Contract field desteklenmiyor: {op.field_name}")
    ctx.source.execute(f"UPDATE contracts SET {column}=?,updated_at=? WHERE id=?", (_value(op), now_iso(), ctx.contract_id))


def _add_system(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    if ctx.source.execute("SELECT 1 FROM systems WHERE merge_uid=?", (op.entity_uid,)).fetchone():
        raise MergeOperationTargetAmbiguousError(f"System merge UID zaten mevcut: {op.entity_uid}")
    ts_payload = data.get("payload_json")
    ctx.source.execute(
        "INSERT INTO systems(contract_id,merge_uid,platform_id,name,status,completion_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            ctx.contract_id,
            str(data.get("merge_uid") or op.entity_uid),
            _int_or_none(data.get("platform_id")),
            str(data.get("name") or op.entity_label or ""),
            str(data.get("status") or ""),
            str(data.get("completion_date") or ""),
            str(data.get("acceptance_date") or ""),
            str(data.get("note") or ""),
            int(data.get("sort_order") or 0),
            str(ts_payload or ""),
        ),
    )
    system_id = int(ctx.source.execute("SELECT last_insert_rowid()").fetchone()[0])
    for component in data.get("components") or []:
        _upsert_system_component(ctx, system_id, str(component.get("name") or ""), component.get("qty"), component.get("note"))


def _delete_system(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "systems", op.entity_uid)
    child = ctx.source.execute("SELECT COUNT(*) FROM deliveries WHERE system_id=?", (int(row["id"]),)).fetchone()[0]
    if int(child or 0):
        raise MergeOperationApplyError("System silinemez; bağlı delivery mevcut.")
    ctx.source.execute("DELETE FROM system_components WHERE system_id=?", (int(row["id"]),))
    ctx.source.execute("DELETE FROM systems WHERE id=?", (int(row["id"]),))


def _set_system_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "systems", op.entity_uid)
    column = SYSTEM_FIELD_DB_COLUMN.get(op.field_name)
    if not column:
        raise MergeOperationApplyError(f"System field desteklenmiyor: {op.field_name}")
    ctx.source.execute(f"UPDATE systems SET {column}=? WHERE id=?", (_value(op), int(row["id"])))


def _set_system_component(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "systems", op.entity_uid)
    component_name = str(op.metadata.get("component_name") or "")
    field = str(op.metadata.get("component_field") or op.field_name or "")
    existing = _system_component_row(ctx, int(row["id"]), component_name)
    if field == "qty":
        note = existing["note"] if existing else ""
        _upsert_system_component(ctx, int(row["id"]), component_name, _value(op), note)
    elif field == "note":
        qty = existing["qty"] if existing else 0
        _upsert_system_component(ctx, int(row["id"]), component_name, qty, _value(op))
    else:
        raise MergeOperationApplyError(f"System component field desteklenmiyor: {field}")


def _system_component_row(ctx: _ApplyContext, system_id: int, component_name: str) -> sqlite3.Row | None:
    return ctx.source.execute(
        "SELECT sc.* FROM system_components sc JOIN components c ON c.id=sc.component_id WHERE sc.system_id=? AND c.name=?",
        (system_id, str(component_name or "")),
    ).fetchone()


def _upsert_system_component(ctx: _ApplyContext, system_id: int, name: str, qty: Any, note: Any) -> None:
    cid = _component_id(ctx, name, create=True)
    existing = ctx.source.execute("SELECT id FROM system_components WHERE system_id=? AND component_id=?", (system_id, cid)).fetchone()
    value = float(qty or 0)
    text_note = "" if note is None else str(note)
    if existing:
        ctx.source.execute("UPDATE system_components SET qty=?,note=? WHERE id=?", (value, text_note, int(existing["id"])))
    else:
        ctx.source.execute("INSERT INTO system_components(system_id,component_id,qty,note) VALUES(?,?,?,?)", (system_id, cid, value, text_note))


def _add_delivery(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    if ctx.source.execute("SELECT 1 FROM deliveries WHERE merge_uid=?", (op.entity_uid,)).fetchone():
        raise MergeOperationTargetAmbiguousError(f"Delivery merge UID zaten mevcut: {op.entity_uid}")
    system_uid = str(data.get("system_merge_uid") or "")
    system = _resolve_by_uid(ctx, "systems", system_uid)
    user_id = _existing_user_id_by_id(ctx, data.get("delivery_user_id"))
    ctx.source.execute(
        "INSERT INTO deliveries(contract_id,merge_uid,system_id,delivery_user_id,name,status,planned_acceptance_date,acceptance_date,note,sort_order,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            ctx.contract_id,
            str(data.get("merge_uid") or op.entity_uid),
            int(system["id"]),
            user_id,
            str(data.get("name") or op.entity_label or ""),
            str(data.get("status") or ""),
            str(data.get("planned_acceptance_date") or ""),
            str(data.get("acceptance_date") or ""),
            str(data.get("note") or ""),
            int(data.get("sort_order") or 0),
            str(data.get("payload_json") or ""),
        ),
    )
    delivery_id = int(ctx.source.execute("SELECT last_insert_rowid()").fetchone()[0])
    for component in data.get("components") or []:
        dc_id = _upsert_delivery_component(ctx, delivery_id, str(component.get("name") or ""), component.get("planned"), component.get("delivered"))
        _replace_delivery_component_units(ctx, dc_id, component.get("units") or [])


def _delete_delivery(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "deliveries", op.entity_uid)
    for dc in ctx.source.execute("SELECT id FROM delivery_components WHERE delivery_id=?", (int(row["id"]),)).fetchall():
        ctx.source.execute("DELETE FROM delivery_component_units WHERE delivery_component_id=?", (int(dc["id"]),))
    ctx.source.execute("DELETE FROM delivery_components WHERE delivery_id=?", (int(row["id"]),))
    ctx.source.execute("DELETE FROM deliveries WHERE id=?", (int(row["id"]),))


def _set_delivery_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "deliveries", op.entity_uid)
    if op.field_name == "system_merge_uid":
        system = _resolve_by_uid(ctx, "systems", str(_value(op) or ""))
        ctx.source.execute("UPDATE deliveries SET system_id=? WHERE id=?", (int(system["id"]), int(row["id"])))
        return
    column = DELIVERY_FIELD_DB_COLUMN.get(op.field_name)
    if not column:
        raise MergeOperationApplyError(f"Delivery field desteklenmiyor: {op.field_name}")
    value = _existing_user_id_by_id(ctx, op.value) if column == "delivery_user_id" else _value(op)
    ctx.source.execute(f"UPDATE deliveries SET {column}=? WHERE id=?", (value, int(row["id"])))


def _set_delivery_component(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "deliveries", op.entity_uid)
    component_name = str(op.metadata.get("component_name") or "")
    field = str(op.metadata.get("component_field") or op.field_name or "")
    existing = _delivery_component_row(ctx, int(row["id"]), component_name)
    planned = existing["planned"] if existing else 0
    delivered = existing["delivered"] if existing else 0
    if field == "planned":
        planned = _value(op) or 0
    elif field == "delivered":
        delivered = _value(op) or 0
    elif field == "units":
        dc_id = _upsert_delivery_component(ctx, int(row["id"]), component_name, planned, delivered)
        _replace_delivery_component_units(ctx, dc_id, _value(op) if op.value_present else [])
        return
    else:
        raise MergeOperationApplyError(f"Delivery component field desteklenmiyor: {field}")
    _upsert_delivery_component(ctx, int(row["id"]), component_name, planned, delivered)


def _delivery_component_row(ctx: _ApplyContext, delivery_id: int, component_name: str) -> sqlite3.Row | None:
    return ctx.source.execute(
        "SELECT dc.* FROM delivery_components dc JOIN components c ON c.id=dc.component_id WHERE dc.delivery_id=? AND c.name=?",
        (delivery_id, str(component_name or "")),
    ).fetchone()


def _upsert_delivery_component(ctx: _ApplyContext, delivery_id: int, name: str, planned: Any, delivered: Any) -> None:
    cid = _component_id(ctx, name, create=True)
    existing = ctx.source.execute("SELECT id FROM delivery_components WHERE delivery_id=? AND component_id=?", (delivery_id, cid)).fetchone()
    p = float(planned or 0)
    d = float(delivered or 0)
    if existing:
        ctx.source.execute("UPDATE delivery_components SET planned=?,delivered=? WHERE id=?", (p, d, int(existing["id"])))
        return int(existing["id"])
    else:
        ctx.source.execute("INSERT INTO delivery_components(delivery_id,component_id,planned,delivered) VALUES(?,?,?,?)", (delivery_id, cid, p, d))
        return int(ctx.source.execute("SELECT last_insert_rowid()").fetchone()[0])


def _replace_delivery_component_units(ctx: _ApplyContext, delivery_component_id: int, units: Any) -> None:
    ts = now_iso()
    ctx.source.execute("DELETE FROM delivery_component_units WHERE delivery_component_id=?", (int(delivery_component_id),))
    if not isinstance(units, list):
        return
    seen_slots: set[int] = set()
    for unit in units:
        if not isinstance(unit, dict):
            continue
        try:
            slot_no = int(unit.get("slot_no", 0) or 0)
        except Exception:
            slot_no = 0
        if slot_no < 1 or slot_no in seen_slots:
            continue
        seen_slots.add(slot_no)
        ctx.source.execute(
            "INSERT INTO delivery_component_units(delivery_component_id,slot_no,identifier,is_delivered,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (
                int(delivery_component_id),
                slot_no,
                str(unit.get("identifier") or "").strip(),
                int(bool(unit.get("is_delivered", 0))),
                str(unit.get("note") or ""),
                ts,
                ts,
            ),
        )


def _add_folder(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    parent_id = _folder_id(ctx, str(data.get("parent_merge_uid") or ""))
    _ensure_folder_name_available(ctx, parent_id, str(data.get("name") or ""))
    ts = now_iso()
    ctx.source.execute(
        "INSERT INTO contract_file_folders(contract_id,merge_uid,parent_id,name,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (ctx.contract_id, str(data.get("merge_uid") or op.entity_uid), parent_id, str(data.get("name") or ""), ts, ts),
    )


def _delete_folder(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "contract_file_folders", op.entity_uid)
    child_folders = ctx.source.execute("SELECT COUNT(*) FROM contract_file_folders WHERE parent_id=?", (int(row["id"]),)).fetchone()[0]
    child_files = ctx.source.execute("SELECT COUNT(*) FROM contract_files WHERE folder_id=?", (int(row["id"]),)).fetchone()[0]
    if int(child_folders or 0) or int(child_files or 0):
        raise MergeOperationApplyError("Folder silinemez; child folder/file mevcut.")
    ctx.source.execute("DELETE FROM contract_file_folders WHERE id=?", (int(row["id"]),))


def _set_folder_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "contract_file_folders", op.entity_uid)
    if op.field_name == "parent_merge_uid":
        parent_id = _folder_id(ctx, str(_value(op) or ""))
        _ensure_not_folder_descendant(ctx, int(row["id"]), parent_id)
        ctx.source.execute("UPDATE contract_file_folders SET parent_id=?,updated_at=? WHERE id=?", (parent_id, now_iso(), int(row["id"])))
        return
    column = FOLDER_FIELD_DB_COLUMN.get(op.field_name)
    if not column:
        raise MergeOperationApplyError(f"Folder field desteklenmiyor: {op.field_name}")
    _ensure_folder_name_available(ctx, row["parent_id"], str(_value(op) or ""), exclude_id=int(row["id"]))
    ctx.source.execute(f"UPDATE contract_file_folders SET {column}=?,updated_at=? WHERE id=?", (_value(op), now_iso(), int(row["id"])))


def _add_file(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    remote = _remote_file(ctx, str(data.get("merge_uid") or op.entity_uid), str(data.get("sha256") or ""))
    folder_id = _folder_id(ctx, str(data.get("folder_merge_uid") or ""))
    ts = now_iso()
    ctx.source.execute(
        "INSERT INTO contract_files(contract_id,merge_uid,folder_id,filename,original_path,file_ext,mime_type,size_bytes,sha256,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ctx.contract_id,
            str(data.get("merge_uid") or op.entity_uid),
            folder_id,
            str(remote["filename"] or data.get("filename") or ""),
            str(remote["original_path"] or ""),
            str(remote["file_ext"] or data.get("file_ext") or ""),
            str(remote["mime_type"] or data.get("mime_type") or "application/octet-stream"),
            int(remote["size_bytes"] or 0),
            str(remote["sha256"] or ""),
            bytes(remote["content_blob"]),
            str(data.get("note") or remote["note"] or ""),
            ts,
            ts,
        ),
    )


def _delete_file(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "contract_files", op.entity_uid)
    ctx.source.execute("DELETE FROM contract_files WHERE id=?", (int(row["id"]),))


def _set_file_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "contract_files", op.entity_uid)
    if op.field_name == "folder_merge_uid":
        folder_id = _folder_id(ctx, str(_value(op) or ""))
        ctx.source.execute("UPDATE contract_files SET folder_id=?,updated_at=? WHERE id=?", (folder_id, now_iso(), int(row["id"])))
        return
    column = FILE_FIELD_DB_COLUMN.get(op.field_name)
    if not column:
        raise MergeOperationApplyError(f"File field desteklenmiyor: {op.field_name}")
    ctx.source.execute(f"UPDATE contract_files SET {column}=?,updated_at=? WHERE id=?", (_value(op), now_iso(), int(row["id"])))


def _replace_file_content(ctx: _ApplyContext, op: MergeOperation) -> None:
    row = _resolve_by_uid(ctx, "contract_files", op.entity_uid)
    expected = str(op.metadata.get("expected_remote_sha256") or op.value or "")
    remote = _remote_file(ctx, op.entity_uid, expected)
    ctx.source.execute(
        "UPDATE contract_files SET size_bytes=?,sha256=?,content_blob=?,mime_type=?,file_ext=?,updated_at=? WHERE id=?",
        (int(remote["size_bytes"] or 0), str(remote["sha256"] or ""), bytes(remote["content_blob"]), str(remote["mime_type"] or ""), str(remote["file_ext"] or ""), now_iso(), int(row["id"])),
    )


def _keep_both_file(ctx: _ApplyContext, op: MergeOperation) -> None:
    source_uid = str(op.metadata.get("source_remote_file_merge_uid") or op.entity_uid)
    expected = str(op.metadata.get("remote_sha256") or "")
    remote = _remote_file(ctx, source_uid, expected)
    data = op.value if isinstance(op.value, dict) else {}
    local_row = _resolve_by_uid(ctx, "contract_files", op.entity_uid)
    remote_folder_uid = str(data.get("folder_merge_uid") or op.metadata.get("remote_folder_merge_uid") or "")
    folder_id = _folder_id(ctx, remote_folder_uid) if remote_folder_uid else local_row["folder_id"]
    filename = _unique_filename(ctx, folder_id, str(remote["filename"] or op.metadata.get("remote_filename") or "remote-file"))
    ext = str(remote["file_ext"] or Path(filename).suffix.lower().lstrip("."))
    mime = str(remote["mime_type"] or mimetypes.guess_type(filename)[0] or "application/octet-stream")
    ts = now_iso()
    ctx.source.execute(
        "INSERT INTO contract_files(contract_id,merge_uid,folder_id,filename,original_path,file_ext,mime_type,size_bytes,sha256,content_blob,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ctx.contract_id, str(uuid.uuid4()), folder_id, filename, "", ext, mime, int(remote["size_bytes"] or 0), str(remote["sha256"] or ""), bytes(remote["content_blob"]), str(remote["note"] or data.get("note") or ""), ts, ts),
    )


def _remote_file(ctx: _ApplyContext, merge_uid: str, expected_sha: str = "") -> sqlite3.Row:
    row = _one(ctx.share, "SELECT * FROM contract_files WHERE merge_uid=?", (str(merge_uid or ""),), f"Remote document bulunamadı: {merge_uid}", f"Remote document belirsiz: {merge_uid}")
    raw = bytes(row["content_blob"])
    actual = hashlib.sha256(raw).hexdigest()
    declared = str(row["sha256"] or "")
    if declared and declared != actual:
        raise RemoteDocumentHashMismatchError("Remote document declared sha256 ile içerik uyuşmuyor.")
    if expected_sha and actual != expected_sha:
        raise RemoteDocumentHashMismatchError("Remote document expected sha256 ile içerik uyuşmuyor.")
    return row


def _folder_id(ctx: _ApplyContext, folder_merge_uid: str) -> int | None:
    if not str(folder_merge_uid or "").strip():
        return None
    row = _resolve_by_uid(ctx, "contract_file_folders", folder_merge_uid)
    return int(row["id"])


def _ensure_folder_name_available(ctx: _ApplyContext, parent_id: Any, name: str, exclude_id: int = 0) -> None:
    params: list[Any] = [ctx.contract_id, str(name or "")]
    sql = "SELECT id FROM contract_file_folders WHERE contract_id=? AND name=? AND "
    if parent_id in (None, "", 0):
        sql += "parent_id IS NULL"
    else:
        sql += "parent_id=?"
        params.append(int(parent_id))
    if exclude_id:
        sql += " AND id<>?"
        params.append(int(exclude_id))
    if ctx.source.execute(sql, params).fetchone():
        raise MergeOperationApplyError("Aynı parent altında folder adı çakışıyor.")


def _ensure_not_folder_descendant(ctx: _ApplyContext, folder_id: int, parent_id: int | None) -> None:
    cur = parent_id
    while cur:
        if int(cur) == int(folder_id):
            raise MergeOperationApplyError("Folder parent cycle oluşur.")
        row = ctx.source.execute("SELECT parent_id FROM contract_file_folders WHERE id=?", (int(cur),)).fetchone()
        cur = int(row["parent_id"]) if row and row["parent_id"] else None


def _unique_filename(ctx: _ApplyContext, folder_id: int | None, filename: str) -> str:
    base = Path(filename).stem or "remote-file"
    suffix = Path(filename).suffix
    candidate = f"{base}{suffix}"
    index = 2
    while _filename_exists(ctx, folder_id, candidate):
        candidate = f"{base} ({index}){suffix}"
        index += 1
    return candidate


def _filename_exists(ctx: _ApplyContext, folder_id: int | None, filename: str) -> bool:
    if folder_id is None:
        return ctx.source.execute("SELECT 1 FROM contract_files WHERE contract_id=? AND folder_id IS NULL AND filename=?", (ctx.contract_id, filename)).fetchone() is not None
    return ctx.source.execute("SELECT 1 FROM contract_files WHERE contract_id=? AND folder_id=? AND filename=?", (ctx.contract_id, folder_id, filename)).fetchone() is not None


def _relation_name(op: MergeOperation) -> str:
    data = op.value if isinstance(op.value, dict) else {}
    for key in ("stable_uid", "name", "full_name", "key"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return str(op.entity_uid or "").strip()


def _global_row(ctx: _ApplyContext, table: str, column: str, value: str) -> sqlite3.Row:
    rows = ctx.source.execute(f"SELECT * FROM {table} WHERE {column}=?", (str(value or ""),)).fetchall()
    if not rows:
        rows = ctx.source.execute(f"SELECT * FROM {table} WHERE lower({column})=lower(?)", (str(value or ""),)).fetchall()
    if not rows:
        raise MergeOperationTargetNotFoundError(f"{table}.{column} bulunamadı: {value}")
    ids = {int(row["id"]) for row in rows}
    if len(ids) > 1:
        raise MergeOperationTargetAmbiguousError(f"{table}.{column} belirsiz: {value}")
    return rows[0]


def _add_platform_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    platform = _global_row(ctx, "platforms", "name", _relation_name(op))
    is_primary = int(data.get("is_primary") or 0)
    if is_primary:
        ctx.source.execute("UPDATE contract_platforms SET is_primary=0 WHERE contract_id=?", (ctx.contract_id,))
        ctx.source.execute("UPDATE contracts SET platform_id=? WHERE id=?", (int(platform["id"]), ctx.contract_id))
    ctx.source.execute(
        "INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,?,?)",
        (ctx.contract_id, int(platform["id"]), int(data.get("sort_order") or 0), is_primary),
    )


def _delete_platform_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    platform = _global_row(ctx, "platforms", "name", _relation_name(op))
    remaining = ctx.source.execute("SELECT COUNT(*) FROM contract_platforms WHERE contract_id=? AND platform_id<>?", (ctx.contract_id, int(platform["id"]))).fetchone()[0]
    if int(remaining or 0) <= 0:
        raise MergeOperationApplyError("Sözleşmenin son platform ilişkisi silinemez.")
    ctx.source.execute("DELETE FROM contract_platforms WHERE contract_id=? AND platform_id=?", (ctx.contract_id, int(platform["id"])))
    _ensure_primary_platform(ctx)


def _set_platform_relation_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    platform = _global_row(ctx, "platforms", "name", _relation_name(op))
    if op.field_name not in {"sort_order", "is_primary"}:
        raise MergeOperationApplyError(f"Platform relation field desteklenmiyor: {op.field_name}")
    if op.field_name == "is_primary" and int(_value(op) or 0):
        ctx.source.execute("UPDATE contract_platforms SET is_primary=0 WHERE contract_id=?", (ctx.contract_id,))
        ctx.source.execute("UPDATE contracts SET platform_id=? WHERE id=?", (int(platform["id"]), ctx.contract_id))
    ctx.source.execute(f"UPDATE contract_platforms SET {op.field_name}=? WHERE contract_id=? AND platform_id=?", (_value(op), ctx.contract_id, int(platform["id"])))
    _ensure_primary_platform(ctx)


def _ensure_primary_platform(ctx: _ApplyContext) -> None:
    row = ctx.source.execute("SELECT platform_id FROM contract_platforms WHERE contract_id=? AND is_primary=1 ORDER BY sort_order,id LIMIT 1", (ctx.contract_id,)).fetchone()
    if not row:
        row = ctx.source.execute("SELECT platform_id,id FROM contract_platforms WHERE contract_id=? ORDER BY sort_order,id LIMIT 1", (ctx.contract_id,)).fetchone()
        if not row:
            raise MergeOperationApplyError("Sözleşme platform ilişkisi kalmadı.")
        ctx.source.execute("UPDATE contract_platforms SET is_primary=CASE WHEN id=? THEN 1 ELSE 0 END WHERE contract_id=?", (int(row["id"]), ctx.contract_id))
    ctx.source.execute("UPDATE contracts SET platform_id=? WHERE id=?", (int(row["platform_id"]), ctx.contract_id))


def _add_user_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    user = _global_row(ctx, "users", "name", _relation_name(op))
    ctx.source.execute("INSERT OR IGNORE INTO contract_users(contract_id,user_id) VALUES(?,?)", (ctx.contract_id, int(user["id"])))


def _delete_user_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    user = _global_row(ctx, "users", "name", _relation_name(op))
    ctx.source.execute("DELETE FROM contract_users WHERE contract_id=? AND user_id=?", (ctx.contract_id, int(user["id"])))


def _set_user_relation_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    user = _global_row(ctx, "users", "name", _relation_name(op))
    if op.field_name != "yi_yd":
        raise MergeOperationApplyError(f"User relation field desteklenmiyor: {op.field_name}")
    ctx.source.execute("UPDATE users SET yi_yd=?,updated_at=? WHERE id=?", (_value(op), now_iso(), int(user["id"])))


def _add_responsible_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    data = _entity_snapshot(op)
    staff = _global_row(ctx, "staff", "full_name", _relation_name(op))
    is_primary = int(data.get("is_primary") or 0)
    if is_primary:
        ctx.source.execute("UPDATE contract_responsible_engineers SET is_primary=0 WHERE contract_id=?", (ctx.contract_id,))
        ctx.source.execute("UPDATE contracts SET responsible_engineer_id=? WHERE id=?", (int(staff["id"]), ctx.contract_id))
    ctx.source.execute(
        "INSERT OR IGNORE INTO contract_responsible_engineers(contract_id,staff_id,sort_order,is_primary) VALUES(?,?,?,?)",
        (ctx.contract_id, int(staff["id"]), int(data.get("sort_order") or 0), is_primary),
    )


def _delete_responsible_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    staff = _global_row(ctx, "staff", "full_name", _relation_name(op))
    ctx.source.execute("DELETE FROM contract_responsible_engineers WHERE contract_id=? AND staff_id=?", (ctx.contract_id, int(staff["id"])))
    row = ctx.source.execute("SELECT staff_id FROM contract_responsible_engineers WHERE contract_id=? ORDER BY is_primary DESC,sort_order,staff_id LIMIT 1", (ctx.contract_id,)).fetchone()
    ctx.source.execute("UPDATE contracts SET responsible_engineer_id=? WHERE id=?", (int(row["staff_id"]) if row else None, ctx.contract_id))


def _set_responsible_relation_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    staff = _global_row(ctx, "staff", "full_name", _relation_name(op))
    if op.field_name not in {"sort_order", "is_primary"}:
        raise MergeOperationApplyError(f"Responsible engineer relation field desteklenmiyor: {op.field_name}")
    if op.field_name == "is_primary" and int(_value(op) or 0):
        ctx.source.execute("UPDATE contract_responsible_engineers SET is_primary=0 WHERE contract_id=?", (ctx.contract_id,))
        ctx.source.execute("UPDATE contracts SET responsible_engineer_id=? WHERE id=?", (int(staff["id"]), ctx.contract_id))
    ctx.source.execute(f"UPDATE contract_responsible_engineers SET {op.field_name}=? WHERE contract_id=? AND staff_id=?", (_value(op), ctx.contract_id, int(staff["id"])))


def _add_tag_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    tag = _global_row(ctx, "tags", "name", _relation_name(op))
    ctx.source.execute("INSERT OR IGNORE INTO contract_tags(contract_id,tag_id) VALUES(?,?)", (ctx.contract_id, int(tag["id"])))


def _delete_tag_relation(ctx: _ApplyContext, op: MergeOperation) -> None:
    tag = _global_row(ctx, "tags", "name", _relation_name(op))
    ctx.source.execute("DELETE FROM contract_tags WHERE contract_id=? AND tag_id=?", (ctx.contract_id, int(tag["id"])))


def _set_tag_relation_field(ctx: _ApplyContext, op: MergeOperation) -> None:
    tag = _global_row(ctx, "tags", "name", _relation_name(op))
    if op.field_name not in {"color", "kind", "name"}:
        raise MergeOperationApplyError(f"Tag relation field desteklenmiyor: {op.field_name}")
    ctx.source.execute(f"UPDATE tags SET {op.field_name}=?,updated_at=? WHERE id=?", (_value(op), now_iso(), int(tag["id"])))


def _entity_snapshot(op: MergeOperation) -> dict[str, Any]:
    if isinstance(op.value, dict):
        return op.value
    if isinstance(op.metadata.get("entity_snapshot"), dict):
        return op.metadata["entity_snapshot"]
    raise MergeOperationApplyError("Entity operation snapshot payload içermiyor.")


def _existing_user_id_by_id(ctx: _ApplyContext, value: Any) -> int | None:
    if value in (None, "", 0):
        return None
    row = ctx.source.execute("SELECT id FROM users WHERE id=?", (int(value),)).fetchone()
    return int(row["id"]) if row else None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _update_registry(ctx: _ApplyContext, status: str, remote_hash: str, post_hash: str, operations_applied: int, operations_skipped: int) -> str:
    try:
        applied = int(operations_applied)
        skipped = int(operations_skipped)
        if applied < 0 or skipped < 0:
            raise MergeRegistryUpdateError("Registry result count negatif olamaz.")
        merged_at = now_iso()
        cur = ctx.source.execute(
            """
            UPDATE share_packages
            SET status=?,last_imported_at=?,last_imported_by_staff_id=?,last_remote_snapshot_sha256=?,merge_result_sha256=?,
                merge_result_operations_applied=?,merge_result_operations_skipped=?,merged_at=?,return_count=COALESCE(return_count,0)+1
            WHERE share_package_id=?
            """,
            (status, merged_at, ctx.current_staff_id or None, remote_hash, post_hash, applied, skipped, merged_at, ctx.share_package_id),
        )
        if cur.rowcount < 1:
            raise MergeRegistryUpdateError("Registry update hiçbir satırı etkilemedi.")
        return merged_at
    except MergeRegistryUpdateError:
        raise
    except Exception as exc:
        raise MergeRegistryUpdateError("Registry update başarısız.") from exc


def _insert_audit_log(ctx: _ApplyContext, status: str, rev_before: int, rev_after: int, pre_hash: str, remote_hash: str, post_hash: str, requested: int, applied: int, backup_path: str) -> None:
    payload = {
        "share_package_id": ctx.share_package_id,
        "contract_merge_uid": ctx.contract_merge_uid,
        "registry_status": status,
        "operations_requested": requested,
        "operations_applied": applied,
        "operations_hash": ctx.operations_hash,
        "pre_apply_local_snapshot_hash": pre_hash,
        "remote_snapshot_hash": remote_hash,
        "post_apply_snapshot_hash": post_hash,
        "revision_before": rev_before,
        "revision_after": rev_after,
        "backup_path": backup_path,
    }
    ctx.source.execute(
        "INSERT INTO activity_logs(created_at,actor,source,device_name,action,entity_type,entity_id,entity_key,contract_no,message,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            now_iso(),
            ctx.actor,
            "Share Merge Apply",
            device_name(),
            "share_merge_applied",
            "share_package",
            ctx.share_package_id,
            ctx.contract_merge_uid,
            ctx.contract_no,
            "Paylaşım merge operasyonları uygulandı",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )


_HANDLERS: dict[MergeOperationKind, Callable[[_ApplyContext, MergeOperation], None]] = {
    MergeOperationKind.SET_CONTRACT_FIELD: _set_contract_field,
    MergeOperationKind.ADD_SYSTEM: _add_system,
    MergeOperationKind.DELETE_SYSTEM: _delete_system,
    MergeOperationKind.SET_SYSTEM_FIELD: _set_system_field,
    MergeOperationKind.SET_SYSTEM_COMPONENT: _set_system_component,
    MergeOperationKind.SET_SYSTEM_COMPONENT_NOTE: _set_system_component,
    MergeOperationKind.ADD_DELIVERY: _add_delivery,
    MergeOperationKind.DELETE_DELIVERY: _delete_delivery,
    MergeOperationKind.SET_DELIVERY_FIELD: _set_delivery_field,
    MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD: _set_delivery_component,
    MergeOperationKind.ADD_DOCUMENT_FOLDER: _add_folder,
    MergeOperationKind.DELETE_DOCUMENT_FOLDER: _delete_folder,
    MergeOperationKind.SET_DOCUMENT_FOLDER_FIELD: _set_folder_field,
    MergeOperationKind.ADD_DOCUMENT_FILE: _add_file,
    MergeOperationKind.DELETE_DOCUMENT_FILE: _delete_file,
    MergeOperationKind.SET_DOCUMENT_FILE_FIELD: _set_file_field,
    MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT: _replace_file_content,
    MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE: _keep_both_file,
    MergeOperationKind.ADD_PLATFORM_RELATION: _add_platform_relation,
    MergeOperationKind.DELETE_PLATFORM_RELATION: _delete_platform_relation,
    MergeOperationKind.SET_PLATFORM_RELATION_FIELD: _set_platform_relation_field,
    MergeOperationKind.ADD_USER_RELATION: _add_user_relation,
    MergeOperationKind.DELETE_USER_RELATION: _delete_user_relation,
    MergeOperationKind.SET_USER_RELATION_FIELD: _set_user_relation_field,
    MergeOperationKind.ADD_RESPONSIBLE_ENGINEER_RELATION: _add_responsible_relation,
    MergeOperationKind.DELETE_RESPONSIBLE_ENGINEER_RELATION: _delete_responsible_relation,
    MergeOperationKind.SET_RESPONSIBLE_ENGINEER_RELATION_FIELD: _set_responsible_relation_field,
    MergeOperationKind.ADD_TAG_RELATION: _add_tag_relation,
    MergeOperationKind.DELETE_TAG_RELATION: _delete_tag_relation,
    MergeOperationKind.SET_TAG_RELATION_FIELD: _set_tag_relation_field,
}
