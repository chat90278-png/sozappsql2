from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from src import auth
from src.services.sts_database import now_iso
from src.models.share_models import (
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
)

ACTIVE_SHARE_STATUSES = frozenset({SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED})
CANCELABLE_SHARE_STATUSES = frozenset({SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED})
FINAL_SHARE_STATUSES = frozenset({SHARE_STATUS_MERGED, SHARE_STATUS_PARTIALLY_MERGED, SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED})
CANCEL_SHARE_PERMISSION = "edit_contracts"


class ShareLifecycleError(RuntimeError):
    pass


class ShareLifecyclePermissionError(ShareLifecycleError):
    pass


class ShareLifecycleContextError(ShareLifecycleError):
    pass


class SharePackageNotFoundError(ShareLifecycleError):
    pass


class SharePackageContractMismatchError(ShareLifecycleError):
    pass


class SharePackageNotCancelableError(ShareLifecycleError):
    pass


@dataclass(frozen=True)
class ShareLifecycleDecision:
    is_active: bool
    can_cancel: bool
    cancel_label: str = "Paylaşımı İptal Et"


def is_active_share_status(status: str) -> bool:
    return str(status or "").strip() in ACTIVE_SHARE_STATUSES


def can_cancel_share_status(status: str) -> bool:
    return str(status or "").strip() in CANCELABLE_SHARE_STATUSES


def share_lifecycle_decision(status: str) -> ShareLifecycleDecision:
    active = is_active_share_status(status)
    return ShareLifecycleDecision(is_active=active, can_cancel=can_cancel_share_status(status))


def _conn(store_or_conn: Any) -> sqlite3.Connection:
    conn = getattr(getattr(store_or_conn, "db", None), "conn", None)
    if isinstance(conn, sqlite3.Connection):
        return conn
    if isinstance(store_or_conn, sqlite3.Connection):
        return store_or_conn
    raise ShareLifecycleContextError("Geçerli kaynak STS bağlantısı bulunamadı.")


def _tx_owner(store_or_conn: Any):
    db = getattr(store_or_conn, "db", None)
    tx = getattr(db, "tx", None)
    return tx if callable(tx) else None


def _is_share_mode(store_or_conn: Any) -> bool:
    if bool(getattr(store_or_conn, "share_mode_enabled", False)) or bool(getattr(store_or_conn, "share_mode", False)):
        return True
    metadata = getattr(store_or_conn, "metadata", None)
    if isinstance(metadata, dict) and str(metadata.get("share_mode") or "").lower() in {"1", "true", "yes"}:
        return True
    return False



def _actor_metadata(current_staff: Any) -> tuple[int | None, str, str]:
    if not isinstance(current_staff, dict):
        return None, "", ""
    staff_id = None
    try:
        parsed = int(current_staff.get("id") or 0)
        if parsed > 0 and not bool(current_staff.get("is_admin")):
            staff_id = parsed
    except (TypeError, ValueError):
        staff_id = None
    username = str(current_staff.get("username") or current_staff.get("device_name") or "").strip()
    full_name = str(current_staff.get("full_name") or current_staff.get("admin_name") or "").strip()
    return staff_id, username, full_name

def ensure_can_cancel_share_package(store_or_conn: Any, contract_merge_uid: str, share_package_id: str, *, current_staff: Any = None) -> dict[str, Any]:
    package_id = str(share_package_id or "").strip()
    uid = str(contract_merge_uid or "").strip()
    if not package_id:
        raise SharePackageNotFoundError("Paylaşım paketi bulunamadı.")
    if not uid:
        raise SharePackageContractMismatchError("Sözleşme kimliği doğrulanamadı.")
    if _is_share_mode(store_or_conn):
        raise ShareLifecycleContextError("Paylaşım dosyası içinde lifecycle işlemi yapılamaz.")
    conn = _conn(store_or_conn)
    if not auth.has_permission(current_staff, CANCEL_SHARE_PERMISSION, conn):
        raise ShareLifecyclePermissionError("Bu paylaşımı iptal etmek için yetkiniz yok.")
    row = conn.execute("SELECT * FROM share_packages WHERE share_package_id=?", (package_id,)).fetchone()
    if row is None:
        raise SharePackageNotFoundError("Paylaşım paketi bulunamadı.")
    data = {key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row)
    if str(data.get("contract_merge_uid") or "") != uid:
        raise SharePackageContractMismatchError("Paylaşım paketi bu sözleşmeye ait değil.")
    status = str(data.get("status") or "")
    if not can_cancel_share_status(status):
        raise SharePackageNotCancelableError("Paylaşım paketi bu durumdayken iptal edilemez.")
    return data


def cancel_share_package(store_or_conn: Any, contract_merge_uid: str, share_package_id: str, *, current_staff: Any = None) -> dict[str, Any]:
    """Atomically mark an active source-registry package as CANCELLED.

    This lifecycle write only updates the registry status. It intentionally does not
    touch contract business rows, revisions, merge result fields, timestamps, BLOBs,
    or exported files.
    """
    package_id = str(share_package_id or "").strip()
    conn = _conn(store_or_conn)
    tx = _tx_owner(store_or_conn)

    def _write() -> dict[str, Any]:
        before = ensure_can_cancel_share_package(store_or_conn, contract_merge_uid, package_id, current_staff=current_staff)
        cancelled_at = now_iso()
        actor_staff_id, actor_username, actor_full_name = _actor_metadata(current_staff)
        cur = conn.execute(
            """
            UPDATE share_packages
            SET status=?,cancelled_at=?,cancelled_by_staff_id=?,cancelled_by_username=?,cancelled_by_full_name=?
            WHERE share_package_id=? AND contract_merge_uid=? AND status IN (?,?)
            """,
            (
                SHARE_STATUS_CANCELLED, cancelled_at, actor_staff_id, actor_username, actor_full_name,
                package_id, str(contract_merge_uid or "").strip(), SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED,
            ),
        )
        if cur.rowcount != 1:
            raise SharePackageNotCancelableError("Paylaşım paketi iptal edilemedi; durum değişmiş olabilir.")
        row = conn.execute("SELECT * FROM share_packages WHERE share_package_id=?", (package_id,)).fetchone()
        return {key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row)

    if tx is not None:
        with tx():
            return _write()
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = _write()
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def list_active_share_packages(store: Any, contract_merge_uid: str) -> list[dict[str, Any]]:
    uid = str(contract_merge_uid or "").strip()
    if not uid:
        return []
    conn = _conn(store)
    rows = conn.execute(
        """
        SELECT id,share_package_id,contract_id,contract_merge_uid,permission_mode,created_at,exported_filename,status
        FROM share_packages
        WHERE contract_merge_uid=? AND status IN (?,?)
        ORDER BY created_at DESC,id DESC
        """,
        (uid, SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED),
    ).fetchall()
    return [{key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row) for row in rows]
