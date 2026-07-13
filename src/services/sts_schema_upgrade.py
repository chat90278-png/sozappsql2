from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from src.services.sts_database import (
    ACTIVITY_LOG_COLUMNS,
    ACTIVITY_LOG_INDEX_SQL,
    CURRENT_SCHEMA_VERSION,
    STSDatabase,
    STSMigrationError,
    make_migration_backup_path,
    read_sts_schema_version,
)


ProgressCallback = Callable[[int, str], None]
MigrationCallable = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class MigrationStep:
    from_version: int
    to_version: int
    name: str
    apply: MigrationCallable


@dataclass(frozen=True)
class UpgradeResult:
    status: Literal["current", "upgraded"]
    from_version: int | None
    to_version: int
    backup_path: Path | None = None
    applied_migrations: tuple[str, ...] = ()


def _emit(progress_callback: ProgressCallback | None, percent: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(max(0, min(100, int(percent))), str(message or ""))


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
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{escaped}")').fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> bool:
    if not _table_exists(conn, table):
        raise RuntimeError(f"Migration tablosu bulunamadı: {table}")
    if str(name or "") in _table_columns(conn, table):
        return False
    escaped_table = str(table or "").replace('"', '""')
    escaped_name = str(name or "").replace('"', '""')
    conn.execute(f'ALTER TABLE "{escaped_table}" ADD COLUMN "{escaped_name}" {ddl}')
    return True


def _require_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> None:
    actual = _table_columns(conn, table)
    missing = set(required) - actual
    if missing:
        raise RuntimeError(
            f"{table} tablosu beklenen migration yapısıyla uyumlu değil. "
            f"Eksik kolonlar: {', '.join(sorted(missing))}"
        )


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
        (str(int(version)),),
    )


def _migrate_14_to_15(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS share_packages (
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
    _require_columns(
        conn,
        "share_packages",
        {
            "share_package_id",
            "contract_id",
            "contract_merge_uid",
            "source_contract_revision",
            "permission_mode",
            "share_format_version",
            "snapshot_format_version",
            "base_snapshot_sha256",
            "created_at",
            "status",
            "merge_result_sha256",
            "return_count",
        },
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_share_packages_contract_merge_uid "
        "ON share_packages(contract_merge_uid)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_share_packages_contract_status "
        "ON share_packages(contract_merge_uid,status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_share_packages_created_at "
        "ON share_packages(created_at)"
    )


def _migrate_15_to_16(conn: sqlite3.Connection) -> None:
    _require_columns(conn, "share_packages", {"share_package_id", "contract_merge_uid"})
    _ensure_column(conn, "share_packages", "merge_result_operations_applied", "INTEGER")
    _ensure_column(conn, "share_packages", "merge_result_operations_skipped", "INTEGER")
    _ensure_column(conn, "share_packages", "merged_at", "TEXT")


def _migrate_16_to_17(conn: sqlite3.Connection) -> None:
    _require_columns(conn, "share_packages", {"share_package_id", "contract_merge_uid"})
    _ensure_column(conn, "share_packages", "cancelled_at", "TEXT")
    _ensure_column(conn, "share_packages", "cancelled_by_staff_id", "INTEGER")
    _ensure_column(
        conn,
        "share_packages",
        "cancelled_by_username",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "share_packages",
        "cancelled_by_full_name",
        "TEXT NOT NULL DEFAULT ''",
    )


def _migrate_17_to_18(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            actor TEXT,
            source TEXT,
            device_name TEXT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            entity_key TEXT,
            platform_id INTEGER,
            contract_no TEXT,
            message TEXT,
            before_json TEXT,
            after_json TEXT,
            payload_json TEXT
        )
        """
    )
    _require_columns(conn, "activity_logs", {"id", "created_at", "action"})
    for name, ddl in ACTIVITY_LOG_COLUMNS:
        _ensure_column(conn, "activity_logs", name, ddl)
    for sql in ACTIVITY_LOG_INDEX_SQL:
        conn.execute(sql)


MIGRATIONS: tuple[MigrationStep, ...] = (
    MigrationStep(14, 15, "v14_to_v15_share_package_registry", _migrate_14_to_15),
    MigrationStep(15, 16, "v15_to_v16_merge_result_audit", _migrate_15_to_16),
    MigrationStep(16, 17, "v16_to_v17_share_cancellation_audit", _migrate_16_to_17),
    MigrationStep(17, 18, "v17_to_v18_activity_history_infrastructure", _migrate_17_to_18),
)

_MIGRATIONS_BY_FROM: dict[int, MigrationStep] = {
    step.from_version: step for step in MIGRATIONS
}
VERSIONED_MIGRATION_FLOOR = min(_MIGRATIONS_BY_FROM)


def _build_migration_chain(from_version: int) -> tuple[MigrationStep, ...]:
    current = int(from_version)
    steps: list[MigrationStep] = []
    visited: set[int] = set()
    while current < CURRENT_SCHEMA_VERSION:
        if current in visited:
            raise STSMigrationError(
                "STS migration zincirinde döngü tespit edildi. Dosyada değişiklik yapılmadı.",
                technical_detail=f"migration_cycle_at=v{current}",
            )
        visited.add(current)
        step = _MIGRATIONS_BY_FROM.get(current)
        if step is None:
            raise STSMigrationError(
                "Bu STS veri sürümü için güvenli otomatik güncelleme adımı bulunamadı.",
                technical_detail=(
                    f"missing_migration_step=v{current}; "
                    f"target=v{CURRENT_SCHEMA_VERSION}"
                ),
            )
        if step.to_version <= current or step.to_version > CURRENT_SCHEMA_VERSION:
            raise STSMigrationError(
                "STS migration zinciri geçersiz. Dosyada değişiklik yapılmadı.",
                technical_detail=(
                    f"invalid_migration_step={step.name}; "
                    f"from=v{step.from_version}; to=v{step.to_version}"
                ),
            )
        steps.append(step)
        current = step.to_version
    return tuple(steps)


def _integrity_check(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "").strip()


def _validate_connection(
    conn: sqlite3.Connection,
    *,
    expected_version: int | None = None,
    check_foreign_keys: bool = True,
) -> None:
    integrity = _integrity_check(conn)
    if integrity.lower() != "ok":
        raise RuntimeError(f"SQLite integrity_check başarısız: {integrity}")
    if check_foreign_keys:
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            details = [tuple(row) for row in fk_rows[:10]]
            raise RuntimeError(f"SQLite foreign_key_check hatası: {details}")
    if expected_version is not None:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        version = None
        if row:
            try:
                version = int(str(row[0] or "").strip())
            except Exception:
                version = None
        if version != int(expected_version):
            raise RuntimeError(
                f"schema_version beklenen {expected_version}, bulunan {version}"
            )


def _validate_sqlite_file(
    path: Path,
    *,
    expected_version: int | None = None,
    check_foreign_keys: bool = False,
) -> None:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        _validate_connection(
            conn,
            expected_version=expected_version,
            check_foreign_keys=check_foreign_keys,
        )
    finally:
        conn.close()


def _create_verified_backup(
    path: Path,
    *,
    from_version: int,
    progress_callback: ProgressCallback | None,
) -> Path:
    _emit(progress_callback, 42, "Güncelleme öncesi yedek oluşturuluyor...")
    backup_path = make_migration_backup_path(
        path,
        from_version,
        CURRENT_SCHEMA_VERSION,
    )
    source_uri = f"file:{path.as_posix()}?mode=ro"
    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    try:
        source = sqlite3.connect(source_uri, uri=True)
        target = sqlite3.connect(str(backup_path))
        source.backup(target)
        target.close()
        target = None
        source.close()
        source = None

        _validate_sqlite_file(
            backup_path,
            expected_version=from_version,
            check_foreign_keys=False,
        )
        if not backup_path.exists() or backup_path.stat().st_size <= 0:
            raise RuntimeError("Migration yedeği oluşturulamadı veya boş.")
        return backup_path
    except Exception:
        try:
            if backup_path.exists():
                backup_path.unlink()
        except Exception:
            pass
        raise
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()


def _restore_backup(
    backup_path: Path,
    path: Path,
    *,
    expected_version: int,
) -> None:
    _remove_sqlite_sidecars(path)
    shutil.copy2(backup_path, path)
    _validate_sqlite_file(
        path,
        expected_version=expected_version,
        check_foreign_keys=False,
    )


def _validate_rolled_back_source(path: Path, *, expected_version: int) -> None:
    _validate_sqlite_file(
        path,
        expected_version=expected_version,
        check_foreign_keys=False,
    )


def _upgrade_with_legacy_compatibility(
    path: Path,
    *,
    from_version: int | None,
    progress_callback: ProgressCallback | None,
) -> UpgradeResult:
    _emit(
        progress_callback,
        45,
        "Eski veri yapısı güvenli uyumluluk migration'larıyla güncelleniyor...",
    )
    db: STSDatabase | None = None
    try:
        db = STSDatabase(path, source="Schema Upgrade Legacy Bootstrap")
        backup_path = db.migration_backup_path
        performed = bool(db.migration_performed)
    finally:
        if db is not None:
            db.close()

    version = read_sts_schema_version(path)
    if version != CURRENT_SCHEMA_VERSION:
        raise STSMigrationError(
            "Eski STS veri dosyası güncel şemaya yükseltilemedi.",
            backup_path=backup_path if "backup_path" in locals() else None,
            technical_detail=(
                f"legacy_bootstrap_result=v{version}; "
                f"target=v{CURRENT_SCHEMA_VERSION}"
            ),
        )
    return UpgradeResult(
        status="upgraded" if performed or from_version != version else "current",
        from_version=from_version,
        to_version=version,
        backup_path=backup_path,
        applied_migrations=(
            (f"legacy_compatibility_bootstrap_to_v{CURRENT_SCHEMA_VERSION}",)
            if performed or from_version != version
            else ()
        ),
    )


def upgrade_sts_file(
    path: Path | str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> UpgradeResult:
    """Upgrade an STS SQLite file to the supported schema version.

    v14 and newer files use the explicit migration registry. Older/unversioned
    files keep the repository's proven legacy compatibility migration path until
    their exact historical version boundaries are extracted into the registry.
    """

    sts_path = Path(path)
    if not sts_path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {sts_path}")
    if not sts_path.is_file():
        raise ValueError(f"Geçerli bir dosya değil: {sts_path}")

    _emit(progress_callback, 30, "Veri dosyası sürümü kontrol ediliyor...")
    try:
        from_version = read_sts_schema_version(sts_path)
    except Exception as exc:
        raise STSMigrationError(
            "STS dosyasının şema bilgisi okunamadı. Dosya güncellenemedi.",
            technical_detail=str(exc),
        ) from exc

    if (
        from_version is not None
        and from_version > CURRENT_SCHEMA_VERSION
    ):
        raise STSMigrationError(
            f"STS dosyası daha yeni bir şema sürümüyle oluşturulmuş "
            f"(v{from_version}). Bu uygulama en fazla "
            f"v{CURRENT_SCHEMA_VERSION} destekliyor."
        )

    if from_version == CURRENT_SCHEMA_VERSION:
        _emit(progress_callback, 55, "Veri yapısı güncel.")
        return UpgradeResult(
            status="current",
            from_version=from_version,
            to_version=CURRENT_SCHEMA_VERSION,
        )

    if from_version is None or from_version < VERSIONED_MIGRATION_FLOOR:
        return _upgrade_with_legacy_compatibility(
            sts_path,
            from_version=from_version,
            progress_callback=progress_callback,
        )

    chain = _build_migration_chain(from_version)
    if not chain:
        return UpgradeResult(
            status="current",
            from_version=from_version,
            to_version=CURRENT_SCHEMA_VERSION,
        )

    backup_path: Path | None = None
    active_step: MigrationStep | None = None
    conn: sqlite3.Connection | None = None
    transaction_started = False
    committed = False
    try:
        backup_path = _create_verified_backup(
            sts_path,
            from_version=from_version,
            progress_callback=progress_callback,
        )

        conn = sqlite3.connect(str(sts_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        transaction_started = True

        total_steps = len(chain)
        for index, step in enumerate(chain):
            active_step = step
            percent = 50 + int((index / max(1, total_steps)) * 25)
            _emit(
                progress_callback,
                percent,
                f"Veri yapısı v{step.from_version} → v{step.to_version} güncelleniyor...",
            )
            step.apply(conn)
            _set_schema_version(conn, step.to_version)

        _emit(progress_callback, 78, "Veri bütünlüğü doğrulanıyor...")
        _validate_connection(
            conn,
            expected_version=CURRENT_SCHEMA_VERSION,
            check_foreign_keys=True,
        )
        conn.commit()
        committed = True
        conn.close()
        conn = None
        _validate_sqlite_file(
            sts_path,
            expected_version=CURRENT_SCHEMA_VERSION,
            check_foreign_keys=True,
        )
    except Exception as exc:
        rollback_succeeded = False
        rollback_error = ""
        if conn is not None:
            if transaction_started and not committed:
                try:
                    conn.rollback()
                    rollback_succeeded = True
                except Exception as rollback_exc:
                    rollback_error = str(rollback_exc)
            try:
                conn.close()
            except Exception as close_exc:
                if rollback_error:
                    rollback_error = f"{rollback_error}; close={close_exc}"
                else:
                    rollback_error = f"close={close_exc}"
            conn = None

        if backup_path is None:
            raise STSMigrationError(
                "Güncelleme öncesi güvenli yedek oluşturulamadığı için "
                "STS dosyasında değişiklik yapılmadı.",
                technical_detail=(
                    f"backup_creation_failed; from=v{from_version}; "
                    f"target=v{CURRENT_SCHEMA_VERSION}; error={exc}"
                ),
            ) from exc

        if not transaction_started:
            raise STSMigrationError(
                "STS dosyası güncelleme için kilitlenemedi veya migration "
                "başlatılamadı. Dosyada değişiklik yapılmadı.",
                backup_path=backup_path,
                technical_detail=(
                    f"migration_not_started; from=v{from_version}; "
                    f"target=v{CURRENT_SCHEMA_VERSION}; error={exc}"
                ),
            ) from exc

        rollback_validation_error = ""
        if rollback_succeeded and not committed:
            try:
                _validate_rolled_back_source(
                    sts_path,
                    expected_version=from_version,
                )
            except Exception as validation_exc:
                rollback_validation_error = str(validation_exc)
            else:
                raise STSMigrationError(
                    "STS dosyası güncellenemedi. Migration işlemi geri alındı "
                    "ve orijinal veri dosyası korundu.",
                    backup_path=backup_path,
                    technical_detail=(
                        f"migration={active_step.name if active_step else 'transaction'}; "
                        f"from=v{from_version}; target=v{CURRENT_SCHEMA_VERSION}; "
                        f"rollback=validated; error={exc}"
                    ),
                ) from exc

        if backup_path.exists():
            try:
                _restore_backup(
                    backup_path,
                    sts_path,
                    expected_version=from_version,
                )
            except Exception as restore_exc:
                raise STSMigrationError(
                    "STS dosyası güncellenemedi ve orijinal dosya yedekten "
                    "geri yüklenemedi. Lütfen yedek dosyayı kullanın.",
                    backup_path=backup_path,
                    technical_detail=(
                        f"migration={active_step.name if active_step else 'transaction'}; "
                        f"error={exc}; "
                        f"rollback={rollback_error or rollback_validation_error or 'unavailable'}; "
                        f"restore={restore_exc}"
                    ),
                ) from exc

        raise STSMigrationError(
            "STS dosyası güncellenemedi. Orijinal veri dosyası yedekten "
            "geri yüklendi.",
            backup_path=backup_path,
            technical_detail=(
                f"migration={active_step.name if active_step else 'transaction'}; "
                f"from=v{from_version}; target=v{CURRENT_SCHEMA_VERSION}; "
                f"rollback={rollback_error or rollback_validation_error or 'unavailable'}; "
                f"error={exc}"
            ),
        ) from exc
    finally:
        if conn is not None:
            conn.close()

    _emit(
        progress_callback,
        82,
        f"Veri dosyası v{from_version} → v{CURRENT_SCHEMA_VERSION} güncellendi.",
    )
    return UpgradeResult(
        status="upgraded",
        from_version=from_version,
        to_version=CURRENT_SCHEMA_VERSION,
        backup_path=backup_path,
        applied_migrations=tuple(step.name for step in chain),
    )
