from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.contract_snapshot import (
    CONTRACT_SNAPSHOT_FORMAT_VERSION,
    build_contract_snapshot,
    hash_contract_snapshot,
    serialize_contract_snapshot,
)
from src.models.share_models import (
    SHARE_FORMAT_V1,
    SHARE_FORMAT_V2,
    SUPPORTED_SHARE_FORMATS,
    ShareBaseSnapshot,
    SharePackageMetadata,
    SharePackageValidationResult,
)

SHARE_METADATA_TABLE_SQL = "CREATE TABLE IF NOT EXISTS share_metadata(key TEXT PRIMARY KEY, value TEXT)"
SHARE_BASE_SNAPSHOT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_base_snapshot (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    snapshot_format_version INTEGER NOT NULL,
    contract_merge_uid TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _to_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value if value is not None else "").strip()
        return int(text) if text else int(default)
    except Exception:
        return int(default)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value or ""))
        return True
    except Exception:
        return False


def utcish_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_share_metadata(path: Path | str) -> dict[str, str]:
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".sts":
        return {}
    try:
        conn = _connect(p)
        try:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='share_metadata'").fetchone()
            if not row:
                return {}
            rows = conn.execute("SELECT key,value FROM share_metadata").fetchall()
            meta = {str(r["key"]): str(r["value"] or "") for r in rows}
            return meta if str(meta.get("share_mode", "")).lower() == "true" else {}
        finally:
            conn.close()
    except Exception:
        return {}


def parse_share_metadata(raw: dict[str, str]) -> SharePackageMetadata:
    raw = {str(k): str(v or "") for k, v in dict(raw or {}).items()}
    fmt = _to_int(raw.get("share_format_version"), SHARE_FORMAT_V1) or SHARE_FORMAT_V1
    return SharePackageMetadata(
        raw=raw,
        share_mode=str(raw.get("share_mode", "")).lower() == "true",
        format_version=fmt,
        share_package_id=str(raw.get("share_package_id") or ""),
        permission_mode="edit" if str(raw.get("permission_mode") or "view").lower() == "edit" else "view",
        source_sts_instance_id=str(raw.get("source_sts_instance_id") or ""),
        source_schema_version=_to_int(raw.get("source_schema_version")),
        source_contract_id=_to_int(raw.get("source_contract_id") or raw.get("contract_id")),
        source_contract_merge_uid=str(raw.get("source_contract_merge_uid") or ""),
        source_contract_no=str(raw.get("source_contract_no") or ""),
        base_revision=_to_int(raw.get("base_revision")),
        base_snapshot_sha256=str(raw.get("base_snapshot_sha256") or ""),
        snapshot_format_version=_to_int(raw.get("snapshot_format_version")),
        created_at=str(raw.get("created_at") or ""),
        created_by_staff_id=_to_int(raw.get("created_by_staff_id")),
        created_by_username=str(raw.get("created_by_username") or ""),
        created_by_full_name=str(raw.get("created_by_full_name") or ""),
        document_count=_to_int(raw.get("document_count")),
        document_bytes=_to_int(raw.get("document_bytes")),
    )


def write_share_metadata(path: Path | str, metadata: dict[str, Any]) -> None:
    conn = _connect(path)
    try:
        conn.execute(SHARE_METADATA_TABLE_SQL)
        for key, value in dict(metadata or {}).items():
            conn.execute(
                "INSERT INTO share_metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )
        conn.commit()
    finally:
        conn.close()


def is_share_package(path: Path | str) -> bool:
    return bool(read_share_metadata(path))


def get_share_format_version(path: Path | str) -> int:
    meta = read_share_metadata(path)
    return parse_share_metadata(meta).format_version if meta else 0


def _ensure_base_snapshot_table(conn: sqlite3.Connection) -> None:
    conn.execute(SHARE_BASE_SNAPSHOT_TABLE_SQL)


def write_share_base_snapshot(path: Path | str, snapshot: ShareBaseSnapshot) -> None:
    conn = _connect(path)
    try:
        _ensure_base_snapshot_table(conn)
        row = conn.execute("SELECT * FROM share_base_snapshot WHERE id=1").fetchone()
        if row:
            existing = ShareBaseSnapshot(
                snapshot_format_version=int(row["snapshot_format_version"]),
                contract_merge_uid=str(row["contract_merge_uid"] or ""),
                snapshot_json=str(row["snapshot_json"] or ""),
                snapshot_sha256=str(row["snapshot_sha256"] or ""),
                created_at=str(row["created_at"] or ""),
            )
            if existing == snapshot:
                return
            raise ValueError("Paylaşım temel snapshot kaydı immutable; farklı snapshot ile değiştirilemez.")
        conn.execute(
            "INSERT INTO share_base_snapshot(id,snapshot_format_version,contract_merge_uid,snapshot_json,snapshot_sha256,created_at) VALUES(1,?,?,?,?,?)",
            (int(snapshot.snapshot_format_version), snapshot.contract_merge_uid, snapshot.snapshot_json, snapshot.snapshot_sha256, snapshot.created_at),
        )
        conn.commit()
    finally:
        conn.close()


def read_share_base_snapshot(path: Path | str) -> ShareBaseSnapshot | None:
    try:
        conn = _connect(path)
        try:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='share_base_snapshot'").fetchone()
            if not row:
                return None
            data = conn.execute("SELECT * FROM share_base_snapshot WHERE id=1").fetchone()
            if not data:
                return None
            return ShareBaseSnapshot(
                snapshot_format_version=int(data["snapshot_format_version"]),
                contract_merge_uid=str(data["contract_merge_uid"] or ""),
                snapshot_json=str(data["snapshot_json"] or ""),
                snapshot_sha256=str(data["snapshot_sha256"] or ""),
                created_at=str(data["created_at"] or ""),
            )
        finally:
            conn.close()
    except Exception:
        return None


def build_base_snapshot_from_source(conn: sqlite3.Connection, contract_id: int, *, created_at: str | None = None) -> ShareBaseSnapshot:
    snapshot = build_contract_snapshot(conn, int(contract_id))
    snapshot_json = serialize_contract_snapshot(snapshot)
    snapshot_sha = hash_contract_snapshot(snapshot)
    merge_uid = str(((snapshot.get("contract") if isinstance(snapshot, dict) else {}) or {}).get("merge_uid") or "")
    return ShareBaseSnapshot(
        snapshot_format_version=CONTRACT_SNAPSHOT_FORMAT_VERSION,
        contract_merge_uid=merge_uid,
        snapshot_json=snapshot_json,
        snapshot_sha256=snapshot_sha,
        created_at=created_at or utcish_now(),
    )


def validate_share_base_snapshot(path: Path | str, metadata: SharePackageMetadata | None = None) -> list[str]:
    errors: list[str] = []
    base = read_share_base_snapshot(path)
    if base is None:
        return ["Paylaşım paketinin temel karşılaştırma verisi bulunamadı."]
    if base.snapshot_format_version != CONTRACT_SNAPSHOT_FORMAT_VERSION:
        errors.append("Paylaşım temel snapshot biçimi desteklenmiyor.")
    if metadata:
        if base.contract_merge_uid != metadata.source_contract_merge_uid:
            errors.append("Paylaşım temel snapshot sözleşme kimliği metadata ile uyuşmuyor.")
        if metadata.base_snapshot_sha256 and metadata.base_snapshot_sha256 != base.snapshot_sha256:
            errors.append("Paylaşım temel snapshot hash değeri metadata ile uyuşmuyor.")
        if metadata.snapshot_format_version and metadata.snapshot_format_version != base.snapshot_format_version:
            errors.append("Paylaşım snapshot format version metadata ile uyuşmüyor.")
    try:
        parsed = json.loads(base.snapshot_json)
        actual_hash = hash_contract_snapshot(parsed)
        if actual_hash != base.snapshot_sha256:
            errors.append("Paylaşım paketinin temel karşılaştırma verisi bozuk veya değiştirilmiş.")
    except Exception:
        errors.append("Paylaşım temel snapshot JSON verisi okunamadı.")
    return errors


def validate_share_package(path: Path | str) -> SharePackageValidationResult:
    raw = read_share_metadata(path)
    if not raw:
        return SharePackageValidationResult(is_share_package=False)
    metadata = parse_share_metadata(raw)
    errors: list[str] = []
    warnings: list[str] = []
    if metadata.format_version not in SUPPORTED_SHARE_FORMATS:
        return SharePackageValidationResult(
            is_share_package=True,
            format_version=metadata.format_version,
            is_supported=False,
            is_valid=False,
            supports_merge=False,
            errors=["Bu paylaşım dosyası daha yeni veya desteklenmeyen bir paylaşım biçimi kullanıyor."],
            metadata=metadata,
        )
    if metadata.format_version == SHARE_FORMAT_V1:
        return SharePackageValidationResult(True, SHARE_FORMAT_V1, True, True, False, [], warnings, metadata)
    if not _is_uuid(metadata.share_package_id):
        errors.append("V2 paylaşım paket kimliği eksik veya geçersiz.")
    if not _is_uuid(metadata.source_sts_instance_id):
        errors.append("Kaynak STS kimliği eksik veya geçersiz.")
    if not metadata.source_contract_merge_uid:
        errors.append("Kaynak sözleşme merge UID değeri eksik.")
    if metadata.base_revision <= 0:
        errors.append("Base revision metadata değeri eksik veya geçersiz.")
    if metadata.snapshot_format_version != CONTRACT_SNAPSHOT_FORMAT_VERSION:
        errors.append("Snapshot format version desteklenmiyor.")
    if not metadata.base_snapshot_sha256:
        errors.append("Base snapshot hash metadata değeri eksik.")
    errors.extend(validate_share_base_snapshot(path, metadata))
    return SharePackageValidationResult(
        is_share_package=True,
        format_version=SHARE_FORMAT_V2,
        is_supported=True,
        is_valid=not errors,
        supports_merge=not errors,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


def build_current_share_snapshot(path: Path | str) -> tuple[str, str]:
    result = validate_share_package(path)
    if not result.is_share_package or not result.is_valid or not result.supports_merge or not result.metadata:
        raise ValueError("Geçerli V2 paylaşım paketi değil.")
    conn = _connect(path)
    try:
        row = conn.execute("SELECT id FROM contracts WHERE merge_uid=?", (result.metadata.source_contract_merge_uid,)).fetchone()
        if not row:
            raise ValueError("Paylaşım paketindeki kaynak sözleşme kimliği bulunamadı.")
        snapshot = build_contract_snapshot(conn, int(row["id"]))
        return serialize_contract_snapshot(snapshot), hash_contract_snapshot(snapshot)
    finally:
        conn.close()


def make_v2_metadata(*, share_package_id: str, permission_mode: str, source_sts_instance_id: str,
                     source_schema_version: int, source_contract_id: int, source_contract_merge_uid: str,
                     source_contract_no: str, base_revision: int, base_snapshot_sha256: str,
                     created_at: str, created_by_staff_id: int = 0, created_by_username: str = "",
                     created_by_full_name: str = "", document_count: int = 0,
                     document_bytes: int = 0) -> dict[str, str]:
    return {
        "share_mode": "true",
        "share_format_version": str(SHARE_FORMAT_V2),
        "share_package_id": str(share_package_id),
        "permission_mode": "edit" if str(permission_mode or "").lower() in {"edit", "duzenle"} else "view",
        "source_sts_instance_id": str(source_sts_instance_id),
        "source_schema_version": str(int(source_schema_version or 0)),
        "source_contract_id": str(int(source_contract_id or 0)),
        "contract_id": str(int(source_contract_id or 0)),
        "source_contract_merge_uid": str(source_contract_merge_uid),
        "source_contract_no": str(source_contract_no),
        "base_revision": str(int(base_revision or 0)),
        "base_snapshot_sha256": str(base_snapshot_sha256),
        "snapshot_format_version": str(CONTRACT_SNAPSHOT_FORMAT_VERSION),
        "created_at": str(created_at),
        "created_by_staff_id": str(int(created_by_staff_id or 0)),
        "created_by_username": str(created_by_username or ""),
        "created_by_full_name": str(created_by_full_name or ""),
        "document_count": str(int(document_count or 0)),
        "document_bytes": str(int(document_bytes or 0)),
    }
