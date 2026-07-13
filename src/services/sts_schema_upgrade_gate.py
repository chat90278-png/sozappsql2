from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.services.sts_database import (
    CURRENT_SCHEMA_VERSION,
    STSMigrationError,
    read_sts_schema_version,
)
from src.services.sts_schema_upgrade import (
    VERSIONED_MIGRATION_FLOOR,
    UpgradeResult,
    upgrade_sts_file as _upgrade_sts_file,
)


ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class SchemaFingerprint:
    version: int
    required_columns: tuple[tuple[str, tuple[str, ...]], ...]
    required_indexes: tuple[str, ...] = ()
    required_metadata: tuple[tuple[str, str], ...] = ()


_V14_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("meta", ("key", "value")),
    ("platforms", ("id", "name", "sort_order")),
    ("users", ("id", "name")),
    ("components", ("id", "name", "display_order")),
    ("component_platforms", ("id", "component_id", "platform_id")),
    ("tags", ("id", "name")),
    ("contracts", ("id", "platform_id", "merge_uid", "revision")),
    ("contract_users", ("contract_id", "user_id")),
    (
        "contract_platforms",
        ("id", "contract_id", "platform_id", "sort_order", "is_primary"),
    ),
    ("systems", ("id", "contract_id", "merge_uid", "platform_id")),
    (
        "system_components",
        ("id", "system_id", "component_id", "qty", "note"),
    ),
    (
        "deliveries",
        (
            "id",
            "contract_id",
            "system_id",
            "delivery_user_id",
            "merge_uid",
            "planned_acceptance_date",
        ),
    ),
    (
        "delivery_components",
        ("id", "delivery_id", "component_id", "planned", "delivered"),
    ),
    (
        "delivery_component_units",
        (
            "id",
            "delivery_component_id",
            "slot_no",
            "identifier",
            "is_delivered",
            "note",
        ),
    ),
    ("contract_tags", ("id", "contract_id", "tag_id")),
    (
        "contract_file_folders",
        (
            "id",
            "contract_id",
            "merge_uid",
            "parent_id",
            "name",
            "created_at",
            "updated_at",
        ),
    ),
    (
        "contract_files",
        (
            "id",
            "contract_id",
            "merge_uid",
            "folder_id",
            "filename",
            "original_path",
            "file_ext",
            "mime_type",
            "size_bytes",
            "sha256",
            "content_blob",
            "note",
            "created_at",
            "updated_at",
        ),
    ),
    (
        "activity_logs",
        ("id", "platform_id", "entity_type", "entity_id", "source", "device_name"),
    ),
    (
        "delivery_schedule_revision_rows",
        ("id", "contract_id", "delivery_id", "contract_no", "field_name", "is_deleted"),
    ),
    ("delivery_schedule_rev_hidden_logs", ("id", "log_id")),
    (
        "platform_delivery_report_summary",
        ("id", "platform_id", "user_id", "contract_id", "status", "description"),
    ),
    (
        "platform_delivery_report_lines",
        (
            "id",
            "platform_id",
            "user_id",
            "contract_id",
            "component_id",
            "serial_no",
            "serial_key",
        ),
    ),
    ("internal_locations", ("id", "name", "is_active", "sort_order")),
    (
        "contract_responsible_engineers",
        ("contract_id", "staff_id", "sort_order", "is_primary"),
    ),
    ("sts_metadata", ("key", "value")),
)

_V14_INDEXES = (
    "idx_contracts_revision",
    "ux_contracts_merge_uid",
    "ux_systems_merge_uid",
    "ux_deliveries_merge_uid",
    "ux_contract_file_folders_merge_uid",
    "ux_contract_files_merge_uid",
)

_V15_SHARE_PACKAGE_COLUMNS = (
    "id",
    "share_package_id",
    "contract_id",
    "contract_merge_uid",
    "source_contract_revision",
    "permission_mode",
    "share_format_version",
    "snapshot_format_version",
    "base_snapshot_sha256",
    "created_at",
    "created_by_staff_id",
    "created_by_username",
    "created_by_full_name",
    "exported_filename",
    "status",
    "last_imported_at",
    "last_imported_by_staff_id",
    "last_remote_snapshot_sha256",
    "merge_result_sha256",
    "return_count",
)

_V15_INDEXES = (
    "idx_share_packages_contract_merge_uid",
    "idx_share_packages_contract_status",
    "idx_share_packages_created_at",
)

_V16_COLUMNS = (
    "merge_result_operations_applied",
    "merge_result_operations_skipped",
    "merged_at",
)

_V17_COLUMNS = (
    "cancelled_at",
    "cancelled_by_staff_id",
    "cancelled_by_username",
    "cancelled_by_full_name",
)

_V18_ACTIVITY_COLUMNS = (
    "occurred_at_utc",
    "category",
    "status",
    "operation_id",
    "actor_type",
    "actor_staff_id",
    "actor_admin_id",
    "actor_display_name",
    "session_id",
    "contract_id",
    "platform_name_snapshot",
    "contract_no_snapshot",
    "changed_fields_json",
    "technical_payload_json",
    "event_schema_version",
)

_V18_ACTIVITY_INDEXES = (
    "idx_activity_logs_occurred_id",
    "idx_activity_logs_category_occurred",
    "idx_activity_logs_actor_staff_occurred",
    "idx_activity_logs_operation_id",
    "idx_activity_logs_action_occurred",
    "idx_activity_logs_entity_occurred",
    "idx_activity_logs_contract_occurred",
    "idx_activity_logs_platform_occurred",
)

FINGERPRINT_MIN_VERSION = VERSIONED_MIGRATION_FLOOR
FINGERPRINT_MAX_VERSION = CURRENT_SCHEMA_VERSION
FINGERPRINT_VERSIONS = tuple(
    range(FINGERPRINT_MIN_VERSION, FINGERPRINT_MAX_VERSION + 1)
)


def _emit(
    progress_callback: ProgressCallback | None,
    percent: int,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(max(0, min(100, int(percent))), str(message or ""))


def _merge_required_columns(
    base: tuple[tuple[str, tuple[str, ...]], ...],
    table: str,
    columns: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    merged = {name: set(required) for name, required in base}
    merged.setdefault(table, set()).update(columns)
    return tuple(
        (name, tuple(sorted(required)))
        for name, required in sorted(merged.items())
    )


def schema_fingerprint_for_version(version: int) -> SchemaFingerprint:
    version = int(version)
    if version not in FINGERPRINT_VERSIONS:
        raise ValueError(
            f"schema fingerprint kayıtlı değil: v{version}; "
            f"supported={FINGERPRINT_VERSIONS}"
        )

    columns = _V14_COLUMNS
    indexes = set(_V14_INDEXES)
    if version >= 15:
        columns = _merge_required_columns(
            columns,
            "share_packages",
            _V15_SHARE_PACKAGE_COLUMNS,
        )
        indexes.update(_V15_INDEXES)
    if version >= 16:
        columns = _merge_required_columns(
            columns,
            "share_packages",
            _V16_COLUMNS,
        )
    if version >= 17:
        columns = _merge_required_columns(
            columns,
            "share_packages",
            _V17_COLUMNS,
        )
    if version >= 18:
        columns = _merge_required_columns(
            columns,
            "activity_logs",
            _V18_ACTIVITY_COLUMNS,
        )
        indexes.update(_V18_ACTIVITY_INDEXES)

    return SchemaFingerprint(
        version=version,
        required_columns=columns,
        required_indexes=tuple(sorted(indexes)),
        required_metadata=(("sts_metadata", "sts_instance_id"),),
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (str(table or ""),),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    escaped = str(table or "").replace('"', '""')
    return {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{escaped}")').fetchall()
    }


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


def _fingerprint_issues(
    conn: sqlite3.Connection,
    fingerprint: SchemaFingerprint,
) -> tuple[str, ...]:
    issues: list[str] = []

    for table, required_columns in fingerprint.required_columns:
        if not _table_exists(conn, table):
            issues.append(f"missing_table:{table}")
            continue
        actual_columns = _table_columns(conn, table)
        missing_columns = set(required_columns) - actual_columns
        for column in sorted(missing_columns):
            issues.append(f"missing_column:{table}.{column}")

    actual_indexes = _index_names(conn)
    for index_name in fingerprint.required_indexes:
        if index_name not in actual_indexes:
            issues.append(f"missing_index:{index_name}")

    for table, key in fingerprint.required_metadata:
        columns = _table_columns(conn, table)
        if not {"key", "value"} <= columns:
            continue
        escaped_table = str(table).replace('"', '""')
        row = conn.execute(
            f'SELECT value FROM "{escaped_table}" WHERE key=? LIMIT 1',
            (key,),
        ).fetchone()
        if row is None or not str(row[0] or "").strip():
            issues.append(f"missing_metadata:{table}.{key}")

    return tuple(issues)


def validate_versioned_schema_fingerprint(
    path: Path | str,
    expected_version: int,
) -> SchemaFingerprint:
    sts_path = Path(path)
    try:
        fingerprint = schema_fingerprint_for_version(expected_version)
    except ValueError as exc:
        raise STSMigrationError(
            "Bu uygulama sürümünde şema doğrulama sözleşmesi kayıtlı değil. "
            "Güvenli otomatik güncelleme durduruldu.",
            technical_detail=(
                f"schema_fingerprint_not_registered=v{expected_version}; "
                f"error={exc}"
            ),
        ) from exc
    uri = f"file:{sts_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        actual_version = read_sts_schema_version(sts_path)
        if actual_version != fingerprint.version:
            raise STSMigrationError(
                "STS dosyasının şema sürümü doğrulanamadı. "
                "Güvenli otomatik güncelleme durduruldu.",
                technical_detail=(
                    f"schema_version_mismatch; expected=v{fingerprint.version}; "
                    f"actual=v{actual_version}"
                ),
            )

        integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0] if integrity_row else "").strip()
        if integrity.lower() != "ok":
            raise STSMigrationError(
                "STS veri bütünlüğü doğrulanamadı. "
                "Güvenli otomatik güncelleme durduruldu.",
                technical_detail=f"integrity_check={integrity}",
            )

        foreign_key_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_rows:
            raise STSMigrationError(
                "STS ilişkisel veri bütünlüğü doğrulanamadı. "
                "Güvenli otomatik güncelleme durduruldu.",
                technical_detail=(
                    "foreign_key_check="
                    f"{[tuple(row) for row in foreign_key_rows[:10]]}"
                ),
            )

        issues = _fingerprint_issues(conn, fingerprint)
        if issues:
            raise STSMigrationError(
                "STS dosyasının şema sürümü ile gerçek veri yapısı uyuşmuyor. "
                "Güvenli otomatik güncelleme durduruldu.",
                technical_detail=(
                    f"schema_fingerprint_mismatch=v{fingerprint.version}; "
                    f"issues={';'.join(issues)}"
                ),
            )
        return fingerprint
    finally:
        conn.close()


def upgrade_sts_file(
    path: Path | str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> UpgradeResult:
    """Run the schema upgrade engine behind a version/fingerprint safety gate."""

    sts_path = Path(path)
    try:
        from_version = read_sts_schema_version(sts_path)
    except Exception:
        # The core upgrade engine owns the canonical unreadable-schema error.
        from_version = None

    if (
        from_version is not None
        and VERSIONED_MIGRATION_FLOOR
        <= from_version
        <= CURRENT_SCHEMA_VERSION
    ):
        _emit(
            progress_callback,
            25,
            f"Veri yapısı v{from_version} şema sözleşmesine göre doğrulanıyor...",
        )
        validate_versioned_schema_fingerprint(sts_path, from_version)

    result = _upgrade_sts_file(
        sts_path,
        progress_callback=progress_callback,
    )

    if result.to_version == CURRENT_SCHEMA_VERSION:
        _emit(
            progress_callback,
            83,
            f"Veri yapısı v{CURRENT_SCHEMA_VERSION} son doğrulamasından geçiriliyor...",
        )
        validate_versioned_schema_fingerprint(
            sts_path,
            CURRENT_SCHEMA_VERSION,
        )

    return result
