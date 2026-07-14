from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.services.sts_database import (
    CURRENT_SCHEMA_VERSION,
    STSDatabase,
    STSMigrationError,
    read_sts_schema_version,
)
from src.services import sts_schema_upgrade_gate as gate


_BASE_SHARE_PACKAGE_COLUMNS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_package_id TEXT NOT NULL UNIQUE,
    contract_id INTEGER NOT NULL,
    contract_merge_uid TEXT NOT NULL,
    source_contract_revision INTEGER NOT NULL,
    permission_mode TEXT NOT NULL,
    share_format_version INTEGER NOT NULL,
    snapshot_format_version INTEGER NOT NULL,
    base_snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by_staff_id INTEGER,
    created_by_username TEXT NOT NULL DEFAULT '',
    created_by_full_name TEXT NOT NULL DEFAULT '',
    exported_filename TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN',
    last_imported_at TEXT,
    last_imported_by_staff_id INTEGER,
    last_remote_snapshot_sha256 TEXT NOT NULL DEFAULT '',
    merge_result_sha256 TEXT NOT NULL DEFAULT '',
    return_count INTEGER NOT NULL DEFAULT 0
"""

_V16_SHARE_PACKAGE_COLUMNS = """
    merge_result_operations_applied INTEGER,
    merge_result_operations_skipped INTEGER,
    merged_at TEXT
"""

_V17_SHARE_PACKAGE_COLUMNS = """
    cancelled_at TEXT,
    cancelled_by_staff_id INTEGER,
    cancelled_by_username TEXT NOT NULL DEFAULT '',
    cancelled_by_full_name TEXT NOT NULL DEFAULT ''
"""


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
        (str(int(version)),),
    )


def _drop_share_package_indexes(conn: sqlite3.Connection) -> None:
    for index_name in (
        "idx_share_packages_contract_merge_uid",
        "idx_share_packages_contract_status",
        "idx_share_packages_created_at",
    ):
        conn.execute(f'DROP INDEX IF EXISTS "{index_name}"')


def _create_share_packages_for_version(
    conn: sqlite3.Connection,
    version: int,
) -> None:
    columns = [_BASE_SHARE_PACKAGE_COLUMNS]
    if version >= 16:
        columns.append(_V16_SHARE_PACKAGE_COLUMNS)
    if version >= 17:
        columns.append(_V17_SHARE_PACKAGE_COLUMNS)
    ddl = ",\n".join(part.strip() for part in columns)
    conn.execute(f"CREATE TABLE share_packages ({ddl})")
    conn.execute(
        "CREATE INDEX idx_share_packages_contract_merge_uid "
        "ON share_packages(contract_merge_uid)"
    )
    conn.execute(
        "CREATE INDEX idx_share_packages_contract_status "
        "ON share_packages(contract_merge_uid,status)"
    )
    conn.execute(
        "CREATE INDEX idx_share_packages_created_at "
        "ON share_packages(created_at)"
    )


def _make_historical_database(path: Path, version: int) -> None:
    assert 14 <= version <= CURRENT_SCHEMA_VERSION
    db = STSDatabase(path)
    db.close()

    conn = sqlite3.connect(path)
    try:
        _drop_share_package_indexes(conn)
        if version <= 17:
            conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_staff")
            conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_snoozed")
            conn.execute("DROP TABLE IF EXISTS staff_agenda_state")
        conn.execute("DROP TABLE IF EXISTS share_packages")
        if version >= 15:
            _create_share_packages_for_version(conn, version)
        _set_schema_version(conn, version)
        conn.commit()
    finally:
        conn.close()


def _create_legacy_unversioned_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE platforms("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT UNIQUE NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE components("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT UNIQUE NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE systems("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "contract_id INTEGER NOT NULL,"
            "name TEXT NOT NULL,"
            "status TEXT,"
            "completion_date TEXT,"
            "acceptance_date TEXT,"
            "note TEXT,"
            "sort_order INTEGER DEFAULT 0,"
            "payload_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE deliveries("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "contract_id INTEGER NOT NULL,"
            "system_id INTEGER,"
            "system_name TEXT NOT NULL,"
            "name TEXT NOT NULL,"
            "status TEXT,"
            "acceptance_date TEXT,"
            "note TEXT,"
            "sort_order INTEGER DEFAULT 0,"
            "payload_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE contract_files("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "contract_id INTEGER NOT NULL,"
            "filename TEXT NOT NULL,"
            "original_path TEXT,"
            "file_ext TEXT,"
            "mime_type TEXT,"
            "size_bytes INTEGER NOT NULL DEFAULT 0,"
            "content_blob BLOB NOT NULL,"
            "note TEXT,"
            "created_at TEXT,"
            "updated_at TEXT)"
        )
        conn.commit()
    finally:
        conn.close()


def test_fingerprint_manifest_covers_registry_floor_through_current_schema():
    assert gate.FINGERPRINT_MIN_VERSION == gate.VERSIONED_MIGRATION_FLOOR
    assert gate.FINGERPRINT_MAX_VERSION == CURRENT_SCHEMA_VERSION
    assert gate.FINGERPRINT_VERSIONS == tuple(
        range(gate.VERSIONED_MIGRATION_FLOOR, CURRENT_SCHEMA_VERSION + 1)
    )
    for version in gate.FINGERPRINT_VERSIONS:
        fingerprint = gate.schema_fingerprint_for_version(version)
        assert fingerprint.version == version


def test_realistic_v14_upgrade_passes_gate_and_stsdatabase_does_not_migrate_again(
    tmp_path: Path,
):
    path = tmp_path / "realistic-v14.sts"
    _make_historical_database(path, 14)
    progress: list[tuple[int, str]] = []

    result = gate.upgrade_sts_file(
        path,
        progress_callback=lambda value, message: progress.append((value, message)),
    )

    assert result.status == "upgraded"
    assert result.from_version == 14
    assert result.to_version == CURRENT_SCHEMA_VERSION
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
    fingerprint = gate.validate_versioned_schema_fingerprint(
        path,
        CURRENT_SCHEMA_VERSION,
    )
    assert fingerprint.version == CURRENT_SCHEMA_VERSION
    assert any("şema sözleşmesine göre" in message for _, message in progress)
    assert any("son doğrulamasından" in message for _, message in progress)

    db = STSDatabase(path)
    try:
        assert db.migration_from_version == CURRENT_SCHEMA_VERSION
        assert db.migration_backup_path is None
        assert db.migration_performed is False
    finally:
        db.close()


def test_mislabeled_v14_missing_foundation_fails_before_backup_or_mutation(
    tmp_path: Path,
):
    path = tmp_path / "fake-v14.sts"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        _set_schema_version(conn, 14)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(STSMigrationError) as exc_info:
        gate.upgrade_sts_file(path)

    error = exc_info.value
    assert "şema sürümü ile gerçek veri yapısı uyuşmuyor" in error.user_message
    assert "schema_fingerprint_mismatch=v14" in error.technical_detail
    assert "missing_table:sts_metadata" in error.technical_detail
    assert read_sts_schema_version(path) == 14
    assert not (tmp_path / "yedekler").exists()


def test_current_v18_with_v16_shape_is_rejected_instead_of_silent_noop(
    tmp_path: Path,
):
    path = tmp_path / "drifted-current.sts"
    _make_historical_database(path, 16)
    conn = sqlite3.connect(path)
    try:
        _set_schema_version(conn, CURRENT_SCHEMA_VERSION)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(STSMigrationError) as exc_info:
        gate.upgrade_sts_file(path)

    error = exc_info.value
    assert "şema sürümü ile gerçek veri yapısı uyuşmuyor" in error.user_message
    assert "schema_fingerprint_mismatch=v18" in error.technical_detail
    assert "missing_column:share_packages.cancelled_at" in error.technical_detail
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
    assert not (tmp_path / "yedekler").exists()


def test_v16_upgrade_is_postflight_validated_as_current_schema(tmp_path: Path):
    path = tmp_path / "realistic-v16.sts"
    _make_historical_database(path, 16)

    result = gate.upgrade_sts_file(path)

    assert result.applied_migrations == (
        "v16_to_v17_share_cancellation_audit",
        "v17_to_v18_staff_agenda_state",
    )
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
    assert (
        gate.validate_versioned_schema_fingerprint(
            path,
            CURRENT_SCHEMA_VERSION,
        ).version
        == CURRENT_SCHEMA_VERSION
    )


def test_legacy_bootstrap_output_must_pass_current_fingerprint(tmp_path: Path):
    path = tmp_path / "legacy.sts"
    _create_legacy_unversioned_db(path)

    result = gate.upgrade_sts_file(path)

    assert result.status == "upgraded"
    assert result.from_version is None
    assert result.to_version == CURRENT_SCHEMA_VERSION
    assert (
        gate.validate_versioned_schema_fingerprint(
            path,
            CURRENT_SCHEMA_VERSION,
        ).version
        == CURRENT_SCHEMA_VERSION
    )


def test_missing_future_fingerprint_contract_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = tmp_path / "current.sts"
    db = STSDatabase(path)
    db.close()

    monkeypatch.setattr(gate, "FINGERPRINT_VERSIONS", (14, 15, 16))

    with pytest.raises(STSMigrationError) as exc_info:
        gate.validate_versioned_schema_fingerprint(
            path,
            CURRENT_SCHEMA_VERSION,
        )

    assert "şema doğrulama sözleşmesi kayıtlı değil" in exc_info.value.user_message
    assert "schema_fingerprint_not_registered=v18" in exc_info.value.technical_detail


def test_sts_load_worker_uses_schema_upgrade_gate_entrypoint():
    source = Path("src/workers/sts_load_worker.py").read_text(encoding="utf-8")

    assert (
        "from src.services.sts_schema_upgrade_gate import upgrade_sts_file"
        in source
    )
    assert (
        "from src.services.sts_schema_upgrade import upgrade_sts_file"
        not in source
    )
