from __future__ import annotations
import json
import sqlite3
import platform as platform_module
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List

from src.auth import ensure_document_locks_table, ensure_staff_table
from src.services import perf_tracker


def now_iso() -> str:
    """Return sortable local computer time for persisted audit timestamps."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_log_timestamp(value) -> str:
    """Display legacy ISO timestamps without rewriting historical records."""
    return str(value or "").replace("T", " ", 1)


def device_name() -> str:
    return str(platform_module.node() or "-").strip() or "-"


def sql_operation(sql: str) -> str:
    cleaned = re.sub(r"^\s*(--[^\n]*\n|/\*.*?\*/\s*)*", "", str(sql or ""), flags=re.S).strip()
    operation = cleaned.split(None, 1)[0].upper() if cleaned else ""
    if operation == "WITH":
        mutation = re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", cleaned, flags=re.I)
        if mutation:
            return mutation.group(1).upper()
    return operation


def should_audit_sql(sql_or_operation: str) -> bool:
    operation = sql_operation(sql_or_operation) if any(ch.isspace() for ch in str(sql_or_operation or "")) else str(sql_or_operation or "").strip().upper()
    return operation not in {"", "SELECT", "PRAGMA", "WITH", "EXPLAIN"}


def sql_query_preview(sql: str, limit: int = 200) -> str:
    return " ".join(str(sql or "").split())[:max(1, int(limit or 200))]


def quote_identifier(identifier: str) -> str:
    return '"' + str(identifier or "").replace('"', '""') + '"'


LEGACY_CONTRACT_PARENT_NO_COLUMN = "parent_contract_" "no"
LEGACY_CONTRACT_USERS_COLUMN = "user_" "names"
LEGACY_DELIVERY_SYSTEM_LABEL_COLUMN = "system_" "name"
CURRENT_SCHEMA_VERSION = 16


class STSMigrationError(RuntimeError):
    """Raised when a legacy STS schema cannot be safely migrated."""

    def __init__(self, user_message: str, *, backup_path: Path | None = None, technical_detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.backup_path = backup_path
        self.technical_detail = technical_detail


def _parse_schema_version(value) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except Exception:
        return None


def read_sts_schema_version(path: Path | str) -> int | None:
    """Read meta.schema_version without creating or mutating the database."""
    p = Path(path)
    if not p.exists():
        return None
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta' LIMIT 1"
        ).fetchone()
        if not row:
            return None
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return _parse_schema_version(row[0] if row else None)
    finally:
        conn.close()


def make_migration_backup_path(path: Path | str, from_version: int | None, to_version: int = CURRENT_SCHEMA_VERSION) -> Path:
    p = Path(path)
    backup_dir = p.parent / "yedekler"
    backup_dir.mkdir(parents=True, exist_ok=True)
    version_label = f"v{from_version}" if from_version is not None else "legacy"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    base = backup_dir / f"{p.stem}__backup_before_migration_{version_label}_to_v{to_version}__{stamp}{p.suffix}"
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = backup_dir / f"{base.stem}__{counter}{base.suffix}"
        counter += 1
    return candidate


def diagnose_sts_file(path: Path | str) -> dict:
    """Return debug diagnostics for an STS/SQLite file without changing it."""
    p = Path(path)
    result = {"path": str(p), "schema_version": None, "tables": [], "integrity_check": None, "foreign_key_check": []}
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        result["schema_version"] = read_sts_schema_version(p)
        result["tables"] = [
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        ]
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result["integrity_check"] = row[0] if row else None
        result["foreign_key_check"] = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
        return result
    finally:
        conn.close()


def print_sts_diagnostics(path: Path | str) -> dict:
    """Print and return schema/integrity diagnostics for manual debugging."""
    result = diagnose_sts_file(path)
    print(f"STS file: {result['path']}")
    print(f"schema_version: {result['schema_version']}")
    print("tables:")
    for table in result["tables"]:
        print(f"  - {table}")
    print(f"integrity_check: {result['integrity_check']}")
    print(f"foreign_key_check: {result['foreign_key_check']}")
    return result


class STSDatabase:
    def __init__(self, path: Path | str, source: str = "Main UI"):
        self.path = Path(path)
        self.source = str(source or "Main UI")
        database_existed = self.path.exists()
        self.migration_backup_path: Path | None = None
        self.migration_from_version: int | None = None
        self.migration_performed = False
        needs_migration_backup = False
        if database_existed:
            try:
                self.migration_from_version = read_sts_schema_version(self.path)
            except Exception as exc:
                raise STSMigrationError(
                    "STS dosyasının şema bilgisi okunamadı. Dosya güncellenemedi.",
                    technical_detail=str(exc),
                ) from exc
            if self.migration_from_version is not None and self.migration_from_version > CURRENT_SCHEMA_VERSION:
                raise STSMigrationError(
                    f"STS dosyası daha yeni bir şema sürümüyle oluşturulmuş (v{self.migration_from_version}). "
                    f"Bu uygulama en fazla v{CURRENT_SCHEMA_VERSION} destekliyor.",
                )
            needs_migration_backup = self.migration_from_version is None or self.migration_from_version < CURRENT_SCHEMA_VERSION
            if needs_migration_backup:
                self.migration_backup_path = make_migration_backup_path(self.path, self.migration_from_version)
                try:
                    shutil.copy2(self.path, self.migration_backup_path)
                except Exception as exc:
                    raise STSMigrationError(
                        "STS dosyası eski sürümde ancak migration öncesi yedek alınamadı. Dosyada değişiklik yapılmadı.",
                        backup_path=self.migration_backup_path,
                        technical_detail=str(exc),
                    ) from exc
        migrated = False
        with perf_tracker.measure(
            perf_tracker.OP_DB_OPEN,
            self.path,
            meta={"database_existed": database_existed},
        ):
            self.conn = sqlite3.connect(str(self.path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA journal_mode=WAL")   # WAL: concurrent reader + writer, crash recovery
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA cache_size=-64000")
            try:
                migrated = self.init_schema()
                if needs_migration_backup:
                    self._validate_after_migration()
                    self.migration_performed = True
            except Exception as exc:
                self.conn.close()
                if needs_migration_backup and self.migration_backup_path and self.migration_backup_path.exists():
                    try:
                        shutil.copy2(self.migration_backup_path, self.path)
                    except Exception as restore_exc:
                        raise STSMigrationError(
                            "STS dosyası güncellenemedi ve orijinal dosya yedekten geri yüklenemedi. Lütfen yedek dosyayı kullanın.",
                            backup_path=self.migration_backup_path,
                            technical_detail=f"Migration: {exc}; Restore: {restore_exc}",
                        ) from exc
                raise STSMigrationError(
                    "STS dosyası güncellenemedi. Orijinal dosya korunmaya çalışıldı. Lütfen yedek dosyayı kullanın.",
                    backup_path=self.migration_backup_path,
                    technical_detail=str(exc),
                ) from exc
        if migrated:
            self.add_log("schema_migrated", entity_type="database", message="Veritabanı şeması güncellendi", actor="Sistem", source="Migration", payload={"columns": migrated, "backup_path": str(self.migration_backup_path or "")})
        self.add_log(
            "database_opened" if database_existed else "database_created",
            entity_type="database",
            message="Veritabanı açıldı" if database_existed else "Veritabanı oluşturuldu",
            actor="Sistem",
            source=self.source,
        )

    def close(self):
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        self.conn.close()

    @contextmanager
    def tx(self):
        """Transaction context manager.

        Ust uste cagrildiginda (ornegin batch_save() icinde write_contract())
        ic cagrı SAVEPOINT kullanir — dis transaction'i erken kapatmaz.
        Bu sayede dis kod rollback yapabilir, atomicity korunur.
        """
        if self.conn.in_transaction:
            # Zaten acik bir transaction var — SAVEPOINT ile ic transaction ac
            sp = f"_tx_{id(self) & 0xFFFF}"
            self.conn.execute(f"SAVEPOINT {sp}")
            try:
                yield
                self.conn.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.conn.execute(f"RELEASE SAVEPOINT {sp}")
                raise
        else:
            try:
                yield
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def _table_columns(self, table: str) -> set[str]:
        rows = self.conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
        return {str(row[1]) for row in rows}

    def _table_exists(self, table: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table or ""),),
        ).fetchone()
        return row is not None

    def _column_exists(self, table: str, column: str) -> bool:
        return self._table_exists(table) and str(column or "") in self._table_columns(table)

    def _ensure_column(self, table: str, name: str, ddl: str) -> bool:
        if name not in self._table_columns(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            return True
        return False

    def _table_column_info(self, table: str) -> dict[str, sqlite3.Row]:
        return {str(row[1]): row for row in self.conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()}

    def _backfill_component_display_order(self) -> bool:
        rows = self.conn.execute(
            "SELECT id FROM components WHERE display_order IS NULL ORDER BY name ASC, id ASC"
        ).fetchall()
        if not rows:
            return False
        used = self.conn.execute("SELECT COALESCE(MAX(display_order), -1) FROM components").fetchone()[0]
        start = int(used if used is not None else -1) + 1
        for offset, row in enumerate(rows):
            self.conn.execute(
                "UPDATE components SET display_order=? WHERE id=?",
                (start + offset, int(row[0])),
            )
        return True

    def _backfill_platform_sort_order(self, force: bool = False) -> bool:
        if force:
            rows = self.conn.execute("SELECT id FROM platforms ORDER BY name ASC, id ASC").fetchall()
            start = 0
        else:
            rows = self.conn.execute(
                "SELECT id FROM platforms WHERE sort_order IS NULL ORDER BY name ASC, id ASC"
            ).fetchall()
            used = self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM platforms").fetchone()[0]
            start = int(used if used is not None else -1) + 1
        if not rows:
            return False
        for offset, row in enumerate(rows):
            self.conn.execute(
                "UPDATE platforms SET sort_order=? WHERE id=?",
                (start + offset, int(row[0])),
            )
        return True

    def _legacy_user_list(self, raw, fallback_user_id=None) -> list[str]:
        values: list[str] = []
        txt = str(raw or "").strip()
        if txt:
            try:
                parsed = json.loads(txt)
                if isinstance(parsed, list):
                    values = [str(item or "").strip() for item in parsed]
                else:
                    values = [part.strip() for part in txt.split(",")]
            except Exception:
                values = [part.strip() for part in txt.split(",")]
        if not values and fallback_user_id is not None:
            row = self.conn.execute("SELECT name FROM users WHERE id=?", (int(fallback_user_id),)).fetchone()
            if row:
                values = [str(row[0] or "").strip()]
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    def _user_id_for_bridge(self, name: str) -> int:
        clean = str(name or "").strip()
        row = self.conn.execute("SELECT id FROM users WHERE name=?", (clean,)).fetchone()
        if row:
            return int(row[0])
        ts = now_iso()
        columns = self._table_columns("users")
        names = ["name"]
        values = [clean]
        if "yi_yd" in columns:
            names.append("yi_yd"); values.append("Yİ")
        if "active" in columns:
            names.append("active"); values.append(1)
        if "created_at" in columns:
            names.append("created_at"); values.append(ts)
        if "updated_at" in columns:
            names.append("updated_at"); values.append(ts)
        placeholders = ",".join("?" for _ in names)
        self.conn.execute(f"INSERT INTO users({','.join(names)}) VALUES({placeholders})", values)
        return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def _migrate_contract_user_bridge(self) -> bool:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contract_users (
                contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY(contract_id, user_id)
            )
            """
        )
        columns = self._table_columns("contracts")
        if not columns:
            return False
        select_columns = ["id"]
        select_columns.append("user_id" if "user_id" in columns else "NULL AS user_id")
        select_columns.append(LEGACY_CONTRACT_USERS_COLUMN if LEGACY_CONTRACT_USERS_COLUMN in columns else f"NULL AS {LEGACY_CONTRACT_USERS_COLUMN}")
        changed = False
        if "user_id" in columns:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO contract_users(contract_id, user_id)
                SELECT lc.id, lc.user_id
                FROM contracts AS lc
                WHERE lc.user_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM contract_users cu
                    WHERE cu.contract_id = lc.id
                      AND cu.user_id = lc.user_id
                  )
                """
            )
            changed = changed or bool(cursor.rowcount and cursor.rowcount > 0)
        for row in self.conn.execute(f"SELECT {', '.join(select_columns)} FROM contracts").fetchall():
            names = self._legacy_user_list(row[2], row[1])
            for name in names:
                uid = self._user_id_for_bridge(name)
                cursor = self.conn.execute("INSERT OR IGNORE INTO contract_users(contract_id,user_id) VALUES(?,?)", (int(row[0]), uid))
                changed = changed or bool(cursor.rowcount and cursor.rowcount > 0)
        return changed

    def _rebuild_contracts_without_legacy_columns(self) -> set[str]:
        columns = self._table_columns("contracts")
        removed = ({LEGACY_CONTRACT_PARENT_NO_COLUMN, LEGACY_CONTRACT_USERS_COLUMN, "user_id"} & columns)
        if not removed:
            return set()
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("PRAGMA legacy_alter_table=ON")
        try:
            self.conn.execute("ALTER TABLE contracts RENAME TO contracts_legacy_model")
            self.conn.execute(
                """
                CREATE TABLE contracts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform_id INTEGER NOT NULL,
                    contract_no TEXT NOT NULL,
                    yi_yd TEXT,
                    contract_type TEXT,
                    type_display TEXT,
                    link_type TEXT,
                    status TEXT,
                    signed_date TEXT,
                    t0_date TEXT,
                    t0_months INTEGER,
                    completion_date TEXT,
                    acceptance_date TEXT,
                    content TEXT,
                    note TEXT,
                    is_main INTEGER DEFAULT 1,
                    parent_contract_id INTEGER,
                    search_text TEXT,
                    payload_json TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(platform_id,contract_no,contract_type),
                    FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE RESTRICT,
                    FOREIGN KEY(parent_contract_id) REFERENCES contracts(id) ON DELETE SET NULL
                )
                """
            )
            copy_columns = [
                "id", "platform_id", "contract_no", "yi_yd", "contract_type", "type_display",
                "link_type", "status", "signed_date", "t0_date", "t0_months", "completion_date",
                "acceptance_date", "content", "note", "is_main", "parent_contract_id", "search_text",
                "payload_json", "created_at", "updated_at",
            ]
            available = self._table_columns("contracts_legacy_model")
            select_exprs = [name if name in available else "NULL" for name in copy_columns]
            self.conn.execute(
                f"INSERT INTO contracts({', '.join(copy_columns)}) SELECT {', '.join(select_exprs)} FROM contracts_legacy_model"
            )
            self.conn.execute("DROP TABLE contracts_legacy_model")
            self.conn.commit()
        finally:
            self.conn.execute("PRAGMA legacy_alter_table=OFF")
            self.conn.execute("PRAGMA foreign_keys=ON")
        return removed

    def _delivery_system_id(self, row: sqlite3.Row, has_legacy_name: bool) -> int | None:
        current = row["system_id"] if "system_id" in row.keys() else None
        if current is not None:
            return int(current)
        label = str(row[LEGACY_DELIVERY_SYSTEM_LABEL_COLUMN] if has_legacy_name else "" or "Sistem").strip() or "Sistem"
        contract_id = int(row["contract_id"])
        system_columns = self._table_columns("systems")
        order_by = "sort_order,id" if "sort_order" in system_columns else "id"
        found = self.conn.execute(
            f"SELECT id FROM systems WHERE contract_id=? AND name=? ORDER BY {order_by} LIMIT 1",
            (contract_id, label),
        ).fetchone()
        if found:
            return int(found[0])
        names = ["contract_id", "name"]
        values = [contract_id, label]
        if "status" in system_columns:
            names.append("status"); values.append("Başlanmadı")
        if "sort_order" in system_columns:
            sort_order = int(self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM systems WHERE contract_id=?", (contract_id,)).fetchone()[0] or 0)
            names.append("sort_order"); values.append(sort_order)
        placeholders = ",".join("?" for _ in names)
        self.conn.execute(f"INSERT INTO systems({','.join(names)}) VALUES({placeholders})", values)
        return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def _rebuild_deliveries_without_legacy_system_label(self) -> bool:
        info = self._table_column_info("deliveries")
        if not info:
            return False
        needs_rebuild = LEGACY_DELIVERY_SYSTEM_LABEL_COLUMN in info or not bool(info.get("system_id") and int(info["system_id"][3] or 0) == 1)
        if not needs_rebuild:
            return False
        has_legacy_name = LEGACY_DELIVERY_SYSTEM_LABEL_COLUMN in info
        normalized = []
        def raw_value(row, key, default=None):
            return row[key] if key in row.keys() else default
        for raw in self.conn.execute("SELECT * FROM deliveries").fetchall():
            sid = self._delivery_system_id(raw, has_legacy_name)
            if sid is None:
                continue
            normalized.append({
                "id": raw["id"],
                "contract_id": raw["contract_id"],
                "system_id": sid,
                "delivery_user_id": raw_value(raw, "delivery_user_id"),
                "name": raw_value(raw, "name", "Teslimat"),
                "status": raw_value(raw, "status"),
                "planned_acceptance_date": raw_value(raw, "planned_acceptance_date", ""),
                "acceptance_date": raw_value(raw, "acceptance_date"),
                "note": raw_value(raw, "note"),
                "sort_order": raw_value(raw, "sort_order", 0),
                "payload_json": raw_value(raw, "payload_json"),
            })
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("PRAGMA legacy_alter_table=ON")
        try:
            self.conn.execute("ALTER TABLE deliveries RENAME TO deliveries_legacy_model")
            self.conn.execute(
                """
                CREATE TABLE deliveries(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    system_id INTEGER NOT NULL,
                    delivery_user_id INTEGER,
                    name TEXT NOT NULL,
                    status TEXT,
                    planned_acceptance_date TEXT DEFAULT '',
                    acceptance_date TEXT,
                    note TEXT,
                    sort_order INTEGER DEFAULT 0,
                    payload_json TEXT,
                    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                    FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE,
                    FOREIGN KEY(delivery_user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            for row in normalized:
                self.conn.execute(
                    """
                    INSERT INTO deliveries(id,contract_id,system_id,delivery_user_id,name,status,planned_acceptance_date,acceptance_date,note,sort_order,payload_json)
                    VALUES(:id,:contract_id,:system_id,:delivery_user_id,:name,:status,:planned_acceptance_date,:acceptance_date,:note,:sort_order,:payload_json)
                    """,
                    row,
                )
            self.conn.execute("DROP TABLE deliveries_legacy_model")
            self.conn.commit()
        finally:
            self.conn.execute("PRAGMA legacy_alter_table=OFF")
            self.conn.execute("PRAGMA foreign_keys=ON")
        return True

    def _create_runtime_indexes(self) -> None:
        # Keep runtime indexes safe for legacy databases while migrations are still
        # adding nullable columns/tables. Indexes that reference optional/newer
        # columns are created only after the needed table/columns exist.
        def create_if(table: str, columns: tuple[str, ...], sql: str) -> None:
            if self._table_exists(table) and all(self._column_exists(table, col) for col in columns):
                self.conn.execute(sql)

        create_if("contracts", ("platform_id",), "CREATE INDEX IF NOT EXISTS idx_contracts_platform_id ON contracts(platform_id)")
        create_if("contracts", ("platform_id", "status"), "CREATE INDEX IF NOT EXISTS idx_contracts_platform_status ON contracts(platform_id,status)")
        create_if("contracts", ("completion_date",), "CREATE INDEX IF NOT EXISTS idx_contracts_completion_date ON contracts(completion_date)")
        create_if("contracts", ("contract_no",), "CREATE INDEX IF NOT EXISTS idx_contracts_contract_no ON contracts(contract_no)")
        create_if("contracts", ("contract_type",), "CREATE INDEX IF NOT EXISTS idx_contracts_contract_type ON contracts(contract_type)")
        create_if("contracts", ("parent_contract_id",), "CREATE INDEX IF NOT EXISTS idx_contracts_parent_contract_id ON contracts(parent_contract_id)")
        create_if("contract_users", ("user_id",), "CREATE INDEX IF NOT EXISTS idx_contract_users_user_id ON contract_users(user_id)")
        create_if("systems", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_systems_contract_id ON systems(contract_id)")
        create_if("systems", ("completion_date",), "CREATE INDEX IF NOT EXISTS idx_systems_completion_date ON systems(completion_date)")
        create_if("systems", ("contract_id", "name"), "CREATE INDEX IF NOT EXISTS idx_systems_contract_name ON systems(contract_id, name)")
        create_if("system_components", ("component_id",), "CREATE INDEX IF NOT EXISTS idx_system_components_component_id ON system_components(component_id)")
        create_if("deliveries", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_deliveries_contract_id ON deliveries(contract_id)")
        create_if("deliveries", ("system_id",), "CREATE INDEX IF NOT EXISTS idx_deliveries_system_id ON deliveries(system_id)")
        create_if("deliveries", ("contract_id", "system_id"), "CREATE INDEX IF NOT EXISTS idx_deliveries_contract_system ON deliveries(contract_id,system_id)")
        create_if("deliveries", ("acceptance_date",), "CREATE INDEX IF NOT EXISTS idx_deliveries_acceptance_date ON deliveries(acceptance_date)")
        create_if("delivery_components", ("component_id",), "CREATE INDEX IF NOT EXISTS idx_delivery_components_component_id ON delivery_components(component_id)")
        create_if("contract_file_folders", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_contract_file_folders_contract_id ON contract_file_folders(contract_id)")
        create_if("contract_file_folders", ("parent_id",), "CREATE INDEX IF NOT EXISTS idx_contract_file_folders_parent_id ON contract_file_folders(parent_id)")
        create_if("contract_files", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_contract_files_contract_id ON contract_files(contract_id)")
        create_if("contract_files", ("contract_id", "size_bytes", "sha256"), "CREATE INDEX IF NOT EXISTS idx_contract_files_contract_size_sha256 ON contract_files(contract_id,size_bytes,sha256)")
        create_if("activity_logs", ("created_at",), "CREATE INDEX IF NOT EXISTS idx_logs_created_at ON activity_logs(created_at)")
        create_if("activity_logs", ("action",), "CREATE INDEX IF NOT EXISTS idx_logs_action ON activity_logs(action)")
        create_if("activity_logs", ("entity_type", "entity_id"), "CREATE INDEX IF NOT EXISTS idx_logs_entity ON activity_logs(entity_type,entity_id)")
        create_if("activity_logs", ("platform_id", "contract_no"), "CREATE INDEX IF NOT EXISTS idx_activity_logs_platform_contract ON activity_logs(platform_id, contract_no)")
        create_if("contract_platforms", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_contract_platforms_contract ON contract_platforms(contract_id)")
        create_if("contract_platforms", ("platform_id",), "CREATE INDEX IF NOT EXISTS idx_contract_platforms_platform ON contract_platforms(platform_id)")
        create_if("contract_responsible_engineers", ("contract_id",), "CREATE INDEX IF NOT EXISTS idx_contract_resp_eng_contract ON contract_responsible_engineers(contract_id)")
        create_if("contract_responsible_engineers", ("staff_id",), "CREATE INDEX IF NOT EXISTS idx_contract_resp_eng_staff ON contract_responsible_engineers(staff_id)")
        create_if("systems", ("contract_id", "platform_id"), "CREATE INDEX IF NOT EXISTS idx_systems_contract_platform ON systems(contract_id, platform_id)")

    def init_schema(self):
        migrated = []
        self.conn.executescript(
            """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,display_name TEXT,is_active INTEGER DEFAULT 1,is_excluded INTEGER DEFAULT 0,logo_blob BLOB,logo_ext TEXT,logo_mime TEXT,logo_updated_at TEXT,sort_order INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,yi_yd TEXT DEFAULT 'Yİ',active INTEGER DEFAULT 1,note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS components(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,version TEXT,unit TEXT DEFAULT 'Adet',active INTEGER DEFAULT 1,usage REAL DEFAULT 1,note TEXT,display_order INTEGER,payload_json TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS component_platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,component_id INTEGER NOT NULL,platform_id INTEGER NOT NULL,enabled INTEGER DEFAULT 1,UNIQUE(component_id,platform_id),FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE,FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,color TEXT,kind TEXT DEFAULT 'contract',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,platform_id INTEGER NOT NULL,merge_uid TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 1,contract_no TEXT NOT NULL,yi_yd TEXT,contract_type TEXT,type_display TEXT,link_type TEXT,status TEXT,signed_date TEXT,t0_date TEXT,t0_months INTEGER,completion_date TEXT,acceptance_date TEXT,content TEXT,note TEXT,is_main INTEGER DEFAULT 1,parent_contract_id INTEGER,search_text TEXT,payload_json TEXT,created_at TEXT,updated_at TEXT,UNIQUE(platform_id,contract_no,contract_type),FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE RESTRICT,FOREIGN KEY(parent_contract_id) REFERENCES contracts(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS contract_users(contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(contract_id,user_id));
CREATE TABLE IF NOT EXISTS contract_platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,platform_id INTEGER NOT NULL,sort_order INTEGER DEFAULT 0,is_primary INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE,UNIQUE(contract_id,platform_id));
CREATE TABLE IF NOT EXISTS systems(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,merge_uid TEXT NOT NULL DEFAULT '',platform_id INTEGER,name TEXT NOT NULL,status TEXT,completion_date TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS system_components(id INTEGER PRIMARY KEY AUTOINCREMENT,system_id INTEGER NOT NULL,component_id INTEGER NOT NULL,qty REAL DEFAULT 0,note TEXT,UNIQUE(system_id,component_id),FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE,FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,merge_uid TEXT NOT NULL DEFAULT '',system_id INTEGER NOT NULL,delivery_user_id INTEGER,name TEXT NOT NULL,status TEXT,planned_acceptance_date TEXT DEFAULT '',acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE,FOREIGN KEY(delivery_user_id) REFERENCES users(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS delivery_components(id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_id INTEGER NOT NULL,component_id INTEGER NOT NULL,planned REAL DEFAULT 0,delivered REAL DEFAULT 0,UNIQUE(delivery_id,component_id),FOREIGN KEY(delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_tags(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,tag_id INTEGER NOT NULL,UNIQUE(contract_id,tag_id),FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_file_folders(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,merge_uid TEXT NOT NULL DEFAULT '',parent_id INTEGER,name TEXT NOT NULL,created_at TEXT,updated_at TEXT,UNIQUE(contract_id,parent_id,name),FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(parent_id) REFERENCES contract_file_folders(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_files(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,merge_uid TEXT NOT NULL DEFAULT '',folder_id INTEGER,filename TEXT NOT NULL,original_path TEXT,file_ext TEXT,mime_type TEXT,size_bytes INTEGER NOT NULL DEFAULT 0,sha256 TEXT DEFAULT '',content_blob BLOB NOT NULL,note TEXT,created_at TEXT,updated_at TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(folder_id) REFERENCES contract_file_folders(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,actor TEXT,source TEXT,device_name TEXT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,entity_key TEXT,platform_id INTEGER,contract_no TEXT,message TEXT,before_json TEXT,after_json TEXT,payload_json TEXT,FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE SET NULL);
            """
        )
        if self._migrate_contract_user_bridge():
            migrated.append("contract_users")
        removed_contract_columns = self._rebuild_contracts_without_legacy_columns()
        if removed_contract_columns:
            if "user_id" in removed_contract_columns:
                migrated.append("contracts.user_id")
            if {LEGACY_CONTRACT_PARENT_NO_COLUMN, LEGACY_CONTRACT_USERS_COLUMN} & removed_contract_columns:
                migrated.append("contracts.cleaned_model")
        if self._rebuild_deliveries_without_legacy_system_label():
            migrated.append("deliveries.cleaned_model")

        with self.tx():
            # Multi-platform contracts were added after the initial normalized STS schema.
            # Keep contracts.platform_id as the primary/default platform and add a bridge
            # table plus systems.platform_id in-place for legacy .sts compatibility.
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS contract_platforms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    platform_id INTEGER NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    is_primary INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
                    UNIQUE(contract_id, platform_id)
                )
            """)
            if self._ensure_column("systems", "platform_id", "INTEGER"):
                migrated.append("systems.platform_id")
            cp_inserted = self.conn.execute("""
                INSERT OR IGNORE INTO contract_platforms(contract_id, platform_id, sort_order, is_primary)
                SELECT id, platform_id, 0, 1
                FROM contracts
                WHERE platform_id IS NOT NULL
            """).rowcount
            if cp_inserted and cp_inserted > 0:
                migrated.append("contract_platforms.backfill")
            sys_updated = self.conn.execute("""
                UPDATE systems
                SET platform_id = (SELECT platform_id FROM contracts WHERE contracts.id = systems.contract_id)
                WHERE platform_id IS NULL
            """).rowcount
            if sys_updated and sys_updated > 0:
                migrated.append("systems.platform_id.backfill")
            contracts = self.conn.execute("SELECT id, platform_id FROM contracts WHERE platform_id IS NOT NULL").fetchall()
            platforms_by_contract = {}
            for row in self.conn.execute(
                """
                SELECT id, contract_id, platform_id, is_primary, sort_order
                FROM contract_platforms
                ORDER BY contract_id ASC, is_primary DESC, sort_order ASC, id ASC
                """
            ).fetchall():
                platforms_by_contract.setdefault(int(row[1]), []).append(row)
            missing_platforms = [
                (int(contract[0]), int(contract[1]))
                for contract in contracts
                if int(contract[0]) not in platforms_by_contract
            ]
            if missing_platforms:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,0,1)",
                    missing_platforms,
                )
                platforms_by_contract = {}
                for row in self.conn.execute(
                    """
                    SELECT id, contract_id, platform_id, is_primary, sort_order
                    FROM contract_platforms
                    ORDER BY contract_id ASC, is_primary DESC, sort_order ASC, id ASC
                    """
                ).fetchall():
                    platforms_by_contract.setdefault(int(row[1]), []).append(row)
            primary_updates = []
            contract_updates = []
            for contract in contracts:
                cid = int(contract[0])
                rows = platforms_by_contract.get(cid, [])
                if not rows:
                    continue
                primary_id = None; selected_pid = None
                for row in rows:
                    if primary_id is None and int(row[3] or 0) == 1:
                        primary_id = int(row[0]); selected_pid = int(row[2])
                if primary_id is None:
                    primary_id = int(rows[0][0]); selected_pid = int(rows[0][2])
                primary_updates.append((primary_id, cid))
                contract_updates.append((selected_pid, cid))
            self.conn.executemany("UPDATE contract_platforms SET is_primary=CASE WHEN id=? THEN 1 ELSE 0 END WHERE contract_id=?", primary_updates)
            self.conn.executemany("UPDATE contracts SET platform_id=? WHERE id=?", contract_updates)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_platforms_contract ON contract_platforms(contract_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_platforms_platform ON contract_platforms(platform_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_systems_contract_platform ON systems(contract_id, platform_id)")
    
        # Existing v2 files may predate the sortable platform/component manager.
        platform_sort_added = self._ensure_column("platforms", "sort_order", "INTEGER DEFAULT 0")
        if platform_sort_added:
            migrated.append("platforms.sort_order")
        if self._backfill_platform_sort_order(force=platform_sort_added):
            migrated.append("platforms.sort_order.backfill")
        if self._ensure_column("components", "display_order", "INTEGER"):
            migrated.append("components.display_order")
        if self._backfill_component_display_order():
            migrated.append("components.display_order.backfill")

        # Existing v2 files may predate delivery-level responsibility. SQLite
        # cannot add foreign-key constraints with ALTER TABLE, but adding the
        # nullable column keeps those files readable and writable. New files
        # still receive the foreign keys from the CREATE TABLE definitions.
        if self._ensure_column("deliveries", "delivery_user_id", "INTEGER"):
            migrated.append("deliveries.delivery_user_id")
        if self._ensure_column("deliveries", "planned_acceptance_date", "TEXT DEFAULT ''"):
            migrated.append("deliveries.planned_acceptance_date")
        # Component notes were added after the initial v2 schema. Keep legacy
        # STS files readable by adding the nullable column in place.
        if self._ensure_column("components", "note", "TEXT"):
            migrated.append("components.note")
        if self._ensure_column("system_components", "note", "TEXT"):
            migrated.append("system_components.note")
        # Audit metadata columns were added after the initial activity log schema.
        for column in ("source", "device_name"):
            if self._ensure_column("activity_logs", column, "TEXT"):
                migrated.append(f"activity_logs.{column}")
        # Document folders were added after embedded contract files shipped.
        if self._ensure_column("contract_files", "folder_id", "INTEGER"):
            migrated.append("contract_files.folder_id")
        if self._ensure_column("contract_files", "sha256", "TEXT DEFAULT ''"):
            migrated.append("contract_files.sha256")
        if self._ensure_column("contracts", "responsible_engineer_id", "INTEGER"):
            migrated.append("contracts.responsible_engineer_id")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_responsible_engineer_id ON contracts(responsible_engineer_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_delivery_user_id ON deliveries(delivery_user_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_file_folders_contract_id ON contract_file_folders(contract_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_file_folders_parent_id ON contract_file_folders(parent_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_files_folder_id ON contract_files(folder_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_files_contract_size_sha256 ON contract_files(contract_id,size_bytes,sha256)")
        self._create_runtime_indexes()
        ensure_staff_table(self.conn)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_staff_role_id ON staff(role_id)")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_responsible_engineers (
                contract_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                sort_order INTEGER DEFAULT 0,
                is_primary INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(contract_id, staff_id),
                FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_resp_eng_contract ON contract_responsible_engineers(contract_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_resp_eng_staff ON contract_responsible_engineers(staff_id)")
        ensure_document_locks_table(self.conn)
        if "contract_id" not in self._table_columns("document_locks"):
            # Legacy document_locks was a single global row constrained to id=1.
            # Recreate it so per-contract locks are not blocked by that CHECK.
            self.conn.execute("DROP TABLE IF EXISTS document_locks")
            ensure_document_locks_table(self.conn)
            migrated.append("document_locks.contract_id")
        elif "id" not in self._table_columns("document_locks"):
            # Tablo var ama id kolonu yok (çok eski şema). Yeniden oluştur.
            self.conn.execute("DROP TABLE IF EXISTS document_locks")
            ensure_document_locks_table(self.conn)
            migrated.append("document_locks.id")
        self.conn.execute("DROP INDEX IF EXISTS idx_document_locks_id")
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_locks_contract_id "
            "ON document_locks(contract_id)"
        )
        # --- Schema v11: unit tracking için yeni kolon ve tablo ---
        if self._ensure_column("components", "requires_unit_tracking", "INTEGER DEFAULT 0"):
            migrated.append("components.requires_unit_tracking")
        if self._ensure_column("components", "unit_tracking_label", "TEXT DEFAULT ''"):
            migrated.append("components.unit_tracking_label")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_component_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_component_id INTEGER NOT NULL,
                slot_no INTEGER NOT NULL,
                identifier TEXT DEFAULT '',
                is_delivered INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(delivery_component_id, slot_no),
                FOREIGN KEY(delivery_component_id) REFERENCES delivery_components(id) ON DELETE CASCADE
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_component_units_dc "
            "ON delivery_component_units(delivery_component_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_component_units_identifier "
            "ON delivery_component_units(identifier)"
        )
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_schedule_revision_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                delivery_id INTEGER,
                system_name TEXT,
                revision_date TEXT,
                user_name TEXT,
                contract_no TEXT,
                delivery_name TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                description TEXT,
                source TEXT DEFAULT 'manual',
                is_deleted INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                created_by TEXT,
                updated_by TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_schedule_rev_hidden_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL UNIQUE,
                hidden_by TEXT,
                hidden_at TEXT,
                reason TEXT
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_schedule_revision_rows_contract "
            "ON delivery_schedule_revision_rows(contract_no)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_schedule_revision_rows_deleted "
            "ON delivery_schedule_revision_rows(is_deleted)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_schedule_rev_hidden_logs_log "
            "ON delivery_schedule_rev_hidden_logs(log_id)"
        )
        # --- Schema v12: Platform Teslimat Durumu Raporu manuel alanları ---
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS platform_delivery_report_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                contract_id INTEGER NOT NULL,
                status TEXT DEFAULT '',
                description TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(platform_id, user_id, contract_id),
                FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS platform_delivery_report_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                contract_id INTEGER NOT NULL,
                component_id INTEGER NOT NULL,
                serial_no TEXT DEFAULT '',
                serial_key TEXT NOT NULL DEFAULT '',
                internal_location TEXT DEFAULT '',
                note TEXT DEFAULT '',
                delivery_location TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(platform_id, user_id, contract_id, component_id, serial_key),
                FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS internal_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        ts = now_iso()
        for order, name in enumerate(("Keşan", "Hadımköy", "Çorlu")):
            self.conn.execute(
                "INSERT OR IGNORE INTO internal_locations(name,is_active,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)",
                (name, 1, order, ts, ts),
            )
        if self._ensure_column("platform_delivery_report_lines", "serial_key", "TEXT NOT NULL DEFAULT ''"):
            migrated.append("platform_delivery_report_lines.serial_key")
        self.conn.execute("UPDATE platform_delivery_report_lines SET serial_key=COALESCE(NULLIF(TRIM(serial_key), ''), NULLIF(TRIM(serial_no), ''), 'TBD') WHERE serial_key IS NULL OR TRIM(serial_key)=''")
        duplicate_groups = self.conn.execute("""
            SELECT platform_id,user_id,contract_id,component_id,serial_key,COUNT(*) AS n
            FROM platform_delivery_report_lines
            GROUP BY platform_id,user_id,contract_id,component_id,serial_key
            HAVING n > 1
        """).fetchall()
        for group in duplicate_groups:
            rows = self.conn.execute("""
                SELECT id FROM platform_delivery_report_lines
                WHERE platform_id=? AND user_id=? AND contract_id=? AND component_id=? AND serial_key=?
                ORDER BY id
            """, (group[0], group[1], group[2], group[3], group[4])).fetchall()
            for row in rows[1:]:
                self.conn.execute("UPDATE platform_delivery_report_lines SET serial_key=? WHERE id=?", (f"{group[4]}#ROW-{row[0]}", row[0]))

        # --- Schema v14: STS identity, merge UIDs and contract revision foundation ---
        self.conn.execute("CREATE TABLE IF NOT EXISTS sts_metadata(key TEXT PRIMARY KEY, value TEXT)")
        row = self.conn.execute("SELECT value FROM sts_metadata WHERE key='sts_instance_id'").fetchone()
        if not row or not str(row[0] or '').strip():
            generated_instance_id = str(uuid.uuid4())
            self.conn.execute("INSERT OR IGNORE INTO sts_metadata(key,value) VALUES('sts_instance_id',?)", (generated_instance_id,))
            self.conn.execute("UPDATE sts_metadata SET value=? WHERE key='sts_instance_id' AND (value IS NULL OR TRIM(value)='')", (generated_instance_id,))
            migrated.append("sts_metadata.sts_instance_id")
        for table in ("contracts", "systems", "deliveries", "contract_file_folders", "contract_files"):
            if self._ensure_column(table, "merge_uid", "TEXT NOT NULL DEFAULT ''"):
                migrated.append(f"{table}.merge_uid")
        if self._ensure_column("contracts", "revision", "INTEGER NOT NULL DEFAULT 1"):
            migrated.append("contracts.revision")
        for table in ("contracts", "systems", "deliveries", "contract_file_folders", "contract_files"):
            rows = self.conn.execute(f"SELECT id FROM {table} WHERE merge_uid IS NULL OR TRIM(merge_uid)='' ").fetchall()
            if rows:
                self.conn.executemany(f"UPDATE {table} SET merge_uid=? WHERE id=?", [(str(uuid.uuid4()), int(r[0])) for r in rows])
                migrated.append(f"{table}.merge_uid.backfill")
            self.conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_merge_uid ON {table}(merge_uid) WHERE merge_uid IS NOT NULL AND merge_uid<>''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_revision ON contracts(revision)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pdr_summary_scope ON platform_delivery_report_summary(platform_id,user_id,contract_id)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pdr_lines_serial_key ON platform_delivery_report_lines(platform_id,user_id,contract_id,component_id,serial_key)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pdr_lines_scope ON platform_delivery_report_lines(platform_id,user_id,contract_id,component_id,serial_key)")

        # --- Schema v15: share package registry for future return/merge tracking ---
        self.conn.execute("""
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
                merge_result_operations_applied INTEGER,
                merge_result_operations_skipped INTEGER,
                merged_at TEXT,
                return_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_share_packages_contract_merge_uid ON share_packages(contract_merge_uid)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_share_packages_contract_status ON share_packages(contract_merge_uid,status)")
        if self._ensure_column("share_packages", "merge_result_operations_applied", "INTEGER"):
            migrated.append("share_packages.merge_result_operations_applied")
        if self._ensure_column("share_packages", "merge_result_operations_skipped", "INTEGER"):
            migrated.append("share_packages.merge_result_operations_skipped")
        if self._ensure_column("share_packages", "merged_at", "TEXT"):
            migrated.append("share_packages.merged_at")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_share_packages_created_at ON share_packages(created_at)")
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(CURRENT_SCHEMA_VERSION),))
        self.conn.commit()
        return migrated


    def _validate_after_migration(self) -> None:
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        integrity = str(row[0] if row else "").strip()
        if integrity.lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check başarısız: {integrity}")
        fk_rows = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            details = [tuple(row) for row in fk_rows[:10]]
            raise RuntimeError(f"SQLite foreign_key_check hatası: {details}")
        version = read_sts_schema_version(self.path)
        if version != CURRENT_SCHEMA_VERSION:
            raise RuntimeError(f"schema_version beklenen {CURRENT_SCHEMA_VERSION}, bulunan {version}")

    def _platform_id(self, platform: str | None):
        name = str(platform or "").strip()
        if not name:
            return None
        row = self.conn.execute("SELECT id FROM platforms WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row else None

    def add_log(self, action: str, entity_type: str = "", entity_key: str = "", message: str = "", payload: dict | None = None,
                actor: str | None = None, source: str | None = None, device: str | None = None,
                entity_id: str | int | None = None, platform: str | None = None,
                contract_no: str | None = None, before: dict | None = None, after: dict | None = None):
        try:
            self.conn.execute(
                "INSERT INTO activity_logs(created_at,actor,source,device_name,action,entity_type,entity_id,entity_key,platform_id,contract_no,message,before_json,after_json,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    now_iso(), actor or "Kullanıcı", source or self.source or "Main UI", device or device_name(), action or "", entity_type or "", "" if entity_id is None else str(entity_id),
                    entity_key or "", self._platform_id(platform), contract_no or "", message or "",
                    json.dumps(before, ensure_ascii=False) if before is not None else None,
                    json.dumps(after, ensure_ascii=False) if after is not None else None,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                )
            )
            self.conn.commit()
        except Exception:
            pass

    def add_sql_query_log(self, sql: str, duration_ms: int, affected_rows: int = 0) -> bool:
        operation = sql_operation(sql)
        if not should_audit_sql(operation):
            return False
        self.add_log(
            "sql_query_executed",
            entity_type="database",
            actor="Kullanıcı",
            source="SQL Terminal",
            message="SQL terminal üzerinden veri değiştiren sorgu çalıştırıldı",
            payload={
                "operation": operation,
                "duration_ms": int(duration_ms or 0),
                "changed": True,
                "affected_rows": int(affected_rows or 0),
                "query_preview": sql_query_preview(sql),
            },
        )
        return True

    def list_logs(self, limit: int = 500, action: str | None = None, entity_type: str | None = None,
                  platform: str | None = None, contract_no: str | None = None, search: str | None = None):
        q = "SELECT l.*, p.name AS platform FROM activity_logs l LEFT JOIN platforms p ON p.id=l.platform_id WHERE 1=1"
        params = []
        if action:
            q += " AND l.action=?"; params.append(action)
        if entity_type:
            q += " AND l.entity_type=?"; params.append(entity_type)
        if platform:
            q += " AND p.name=?"; params.append(platform)
        if contract_no:
            q += " AND l.contract_no=?"; params.append(contract_no)
        if search:
            q += " AND (l.message LIKE ? OR l.entity_key LIKE ? OR l.actor LIKE ? OR l.source LIKE ? OR l.device_name LIKE ? OR l.action LIKE ? OR p.name LIKE ? OR l.contract_no LIKE ?)"
            s = f"%{search}%"; params.extend([s, s, s, s, s, s, s, s])
        q += " ORDER BY l.created_at DESC"
        if limit and int(limit) > 0:
            q += " LIMIT ?"; params.append(int(limit))
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]


    def list_user_tables(self) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        return [str(row[0]) for row in rows]

    def database_stats(self):
        tables = self.list_user_tables()
        counts = {}
        for table in tables:
            try:
                counts[table] = int(self.conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0])
            except Exception:
                counts[table] = 0
        meta = {}
        try:
            for r in self.conn.execute("SELECT key,value FROM meta").fetchall():
                meta[str(r[0])] = r[1]
        except Exception:
            pass
        sz = self.path.stat().st_size if self.path.exists() else 0
        jm = self.conn.execute("PRAGMA journal_mode").fetchone()[0]
        page_count = int(self.conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(self.conn.execute("PRAGMA page_size").fetchone()[0])
        freelist = int(self.conn.execute("PRAGMA freelist_count").fetchone()[0])
        return {
            "path": str(self.path),
            "file_size_bytes": sz,
            "file_size_mb": round(sz / (1024*1024), 3),
            "journal_mode": jm,
            "page_count": page_count,
            "page_size": page_size,
            "freelist_count": freelist,
            "table_counts": counts,
            "meta": meta,
        }

    def integrity_check(self):
        return [str(r[0]) for r in self.conn.execute("PRAGMA integrity_check").fetchall()]

    def foreign_key_check(self):
        rows = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        return [dict(r) for r in rows]

    def vacuum(self):
        before = self.path.stat().st_size if self.path.exists() else 0
        self.conn.execute("VACUUM")
        self.conn.commit()
        after = self.path.stat().st_size if self.path.exists() else 0
        return {"before_bytes": before, "after_bytes": after}

    def optimize(self):
        self.conn.execute("PRAGMA optimize")
        self.conn.commit()
        return {"ok": True}

    def backup_to(self, target_path):
        dest = sqlite3.connect(str(target_path))
        try:
            self.conn.backup(dest)
            dest.execute("PRAGMA journal_mode=DELETE")
            dest.commit()
        finally:
            dest.close()
        p = Path(target_path)
        return {"target_path": str(p), "size_bytes": p.stat().st_size if p.exists() else 0}


    def preview_table(self, table_name, limit=100):
        t = str(table_name or "").strip()
        if t not in set(self.list_user_tables()):
            raise ValueError("Geçersiz tablo adı")
        lim = max(1, min(1000, int(limit or 100)))
        quoted_table = quote_identifier(t)
        if t == "activity_logs":
            preferred = [
                "id", "created_at", "actor", "source", "device_name", "action", "entity_type", "entity_id",
                "entity_key", "platform_id", "contract_no", "message", "before_json", "after_json", "payload_json",
            ]
            existing = self._table_columns(t)
            selected = [column for column in preferred if column in existing]
            selected.extend(column for column in existing if column not in selected)
            columns = ", ".join(quote_identifier(column) for column in selected) or "*"
            rows = self.conn.execute(f"SELECT {columns} FROM {quoted_table} LIMIT ?", (lim,)).fetchall()
        else:
            rows = self.conn.execute(f"SELECT * FROM {quoted_table} LIMIT ?", (lim,)).fetchall()
        return [dict(r) for r in rows]


    def recent_performance_logs(self, limit=100):
        lim = max(1, min(1000, int(limit or 100)))
        rows = self.conn.execute(
            "SELECT l.*, p.name AS platform FROM activity_logs l LEFT JOIN platforms p ON p.id=l.platform_id ORDER BY l.created_at DESC LIMIT ?", (lim * 4,)
        ).fetchall()
        out = []
        perf_actions = {
            "performance_measurement", "excel_exported", "database_optimize_completed", "database_vacuum_completed",
            "sts_opened", "platform_refresh", "contract_detail_open", "contract_saved"
        }
        for r in rows:
            item = dict(r)
            payload = {}
            raw = item.get("payload_json")
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {}
            has_dur = any(k in payload for k in ("duration_ms", "duration_sec", "elapsed_ms"))
            if item.get("action") in perf_actions or has_dur:
                out.append(item)
            if len(out) >= lim:
                break
        return out

    def add_performance_log(self, metric, duration_ms=None, duration_sec=None, payload=None):
        pl = dict(payload or {})
        pl["metric"] = str(metric or "")
        if duration_ms is not None:
            pl["duration_ms"] = float(duration_ms)
        if duration_sec is not None:
            pl["duration_sec"] = float(duration_sec)
        self.add_log(
            action="performance_measurement",
            entity_type="performance",
            entity_key=str(metric or ""),
            message=f"Performans ölçümü: {metric}",
            payload=pl,
        )

    def performance_stats(self):
        base = self.database_stats()
        counts = base.get("table_counts", {})
        logs = self.recent_performance_logs(limit=200)
        recent_metrics = {}
        for it in logs:
            action = str(it.get("action") or "")
            payload = {}
            raw = it.get("payload_json")
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {}
            metric = str(payload.get("metric") or action or "")
            if not metric:
                continue
            if metric not in recent_metrics:
                recent_metrics[metric] = payload
        total_records = sum(int(v or 0) for v in counts.values())
        return {
            **base,
            "total_records": total_records,
            "platform_count": int(counts.get("platforms", 0)),
            "contract_count": int(counts.get("contracts", 0)),
            "system_count": int(counts.get("systems", 0)),
            "delivery_count": int(counts.get("deliveries", 0)),
            "component_count": int(counts.get("components", 0)),
            "activity_log_count": int(counts.get("activity_logs", 0)),
            "recent_metrics": recent_metrics,
        }
