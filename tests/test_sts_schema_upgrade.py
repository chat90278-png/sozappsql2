from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.services import sts_schema_upgrade as upgrade
from src.services.sts_database import (
    CURRENT_SCHEMA_VERSION,
    STSDatabase,
    STSMigrationError,
    read_sts_schema_version,
)


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO meta(key,value) VALUES('schema_version',?)",
        (str(version),),
    )


def _create_share_packages_v15(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE share_packages (
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
        )
        """
    )


def _create_versioned_db(path: Path, version: int) -> None:
    conn = sqlite3.connect(path)
    try:
        _set_version(conn, version)
        if version >= 15:
            _create_share_packages_v15(conn)
        if version >= 16:
            conn.execute(
                "ALTER TABLE share_packages "
                "ADD COLUMN merge_result_operations_applied INTEGER"
            )
            conn.execute(
                "ALTER TABLE share_packages "
                "ADD COLUMN merge_result_operations_skipped INTEGER"
            )
            conn.execute("ALTER TABLE share_packages ADD COLUMN merged_at TEXT")
        if version >= 17:
            conn.execute("ALTER TABLE share_packages ADD COLUMN cancelled_at TEXT")
            conn.execute(
                "ALTER TABLE share_packages "
                "ADD COLUMN cancelled_by_staff_id INTEGER"
            )
            conn.execute(
                "ALTER TABLE share_packages "
                "ADD COLUMN cancelled_by_username TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE share_packages "
                "ADD COLUMN cancelled_by_full_name TEXT NOT NULL DEFAULT ''"
            )
        conn.commit()
    finally:
        conn.close()


def _columns(path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {
            str(row[1])
            for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        }
    finally:
        conn.close()


def _tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
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


def test_v14_runs_exact_registry_chain_and_creates_verified_backup(tmp_path: Path):
    path = tmp_path / "v14.sts"
    _create_versioned_db(path, 14)
    progress: list[tuple[int, str]] = []

    result = upgrade.upgrade_sts_file(
        path,
        progress_callback=lambda value, message: progress.append((value, message)),
    )

    assert result.status == "upgraded"
    assert result.from_version == 14
    assert result.to_version == CURRENT_SCHEMA_VERSION == 17
    assert result.applied_migrations == (
        "v14_to_v15_share_package_registry",
        "v15_to_v16_merge_result_audit",
        "v16_to_v17_share_cancellation_audit",
    )
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.parent.name == "yedekler"
    assert read_sts_schema_version(result.backup_path) == 14
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION

    expected_columns = {
        "merge_result_operations_applied",
        "merge_result_operations_skipped",
        "merged_at",
        "cancelled_at",
        "cancelled_by_staff_id",
        "cancelled_by_username",
        "cancelled_by_full_name",
    }
    assert expected_columns <= _columns(path, "share_packages")
    assert any("v14 → v15" in message for _, message in progress)
    assert any("Veri bütünlüğü doğrulanıyor" in message for _, message in progress)


def test_v16_runs_only_v16_to_v17(tmp_path: Path):
    path = tmp_path / "v16.sts"
    _create_versioned_db(path, 16)

    result = upgrade.upgrade_sts_file(path)

    assert result.applied_migrations == (
        "v16_to_v17_share_cancellation_audit",
    )
    assert read_sts_schema_version(path) == 17
    assert {
        "cancelled_at",
        "cancelled_by_staff_id",
        "cancelled_by_username",
        "cancelled_by_full_name",
    } <= _columns(path, "share_packages")


def test_registry_is_contiguous_and_targets_current_schema():
    assert upgrade.MIGRATIONS
    assert upgrade.MIGRATIONS[0].from_version == upgrade.VERSIONED_MIGRATION_FLOOR
    assert upgrade.MIGRATIONS[-1].to_version == CURRENT_SCHEMA_VERSION
    assert len({step.from_version for step in upgrade.MIGRATIONS}) == len(
        upgrade.MIGRATIONS
    )
    for current_step, next_step in zip(
        upgrade.MIGRATIONS,
        upgrade.MIGRATIONS[1:],
    ):
        assert current_step.to_version == next_step.from_version


def test_backup_creation_failure_leaves_source_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = tmp_path / "backup-failure.sts"
    _create_versioned_db(path, 14)

    def _fail_backup(*args, **kwargs):
        raise RuntimeError("injected backup failure")

    monkeypatch.setattr(upgrade, "_create_verified_backup", _fail_backup)

    with pytest.raises(STSMigrationError) as exc_info:
        upgrade.upgrade_sts_file(path)

    assert "dosyasında değişiklik yapılmadı" in exc_info.value.user_message
    assert read_sts_schema_version(path) == 14
    assert "share_packages" not in _tables(path)


def test_current_schema_is_noop_and_does_not_create_backup(tmp_path: Path):
    path = tmp_path / "current.sts"
    db = STSDatabase(path)
    db.close()

    result = upgrade.upgrade_sts_file(path)

    assert result.status == "current"
    assert result.from_version == CURRENT_SCHEMA_VERSION
    assert result.to_version == CURRENT_SCHEMA_VERSION
    assert result.backup_path is None
    assert result.applied_migrations == ()
    assert not (tmp_path / "yedekler").exists()


def test_future_schema_fails_closed_without_mutation(tmp_path: Path):
    path = tmp_path / "future.sts"
    _create_versioned_db(path, CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(STSMigrationError) as exc_info:
        upgrade.upgrade_sts_file(path)

    assert "daha yeni bir şema sürümüyle" in exc_info.value.user_message
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION + 1
    assert not (tmp_path / "yedekler").exists()


def test_failed_step_restores_original_database_from_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = tmp_path / "rollback.sts"
    _create_versioned_db(path, 15)

    def _failing_migration(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE migration_should_rollback(id INTEGER)")
        raise RuntimeError("injected migration failure")

    monkeypatch.setitem(
        upgrade._MIGRATIONS_BY_FROM,
        15,
        upgrade.MigrationStep(
            15,
            16,
            "injected_failure",
            _failing_migration,
        ),
    )

    with pytest.raises(STSMigrationError) as exc_info:
        upgrade.upgrade_sts_file(path)

    error = exc_info.value
    assert "yedekten geri yüklendi" in error.user_message
    assert error.backup_path is not None
    assert error.backup_path.exists()
    assert read_sts_schema_version(path) == 15
    assert "migration_should_rollback" not in _tables(path)
    assert "injected_failure" in error.technical_detail


def test_unversioned_legacy_file_uses_compatibility_bootstrap(tmp_path: Path):
    path = tmp_path / "legacy.sts"
    _create_legacy_unversioned_db(path)

    result = upgrade.upgrade_sts_file(path)

    assert result.status == "upgraded"
    assert result.from_version is None
    assert result.to_version == CURRENT_SCHEMA_VERSION
    assert result.applied_migrations == (
        f"legacy_compatibility_bootstrap_to_v{CURRENT_SCHEMA_VERSION}",
    )
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION
    assert "share_packages" in _tables(path)
