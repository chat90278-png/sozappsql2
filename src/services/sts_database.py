from __future__ import annotations
import json
import sqlite3
import platform as platform_module
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List

from src.auth import ensure_document_locks_table, ensure_staff_table


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


class STSDatabase:
    def __init__(self, path: Path | str, source: str = "Main UI"):
        self.path = Path(path)
        self.source = str(source or "Main UI")
        database_existed = self.path.exists()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")
        migrated = self.init_schema()
        if migrated:
            self.add_log("schema_migrated", entity_type="database", message="Veritabanı şeması güncellendi", actor="Sistem", source="Migration", payload={"columns": migrated})
        self.add_log(
            "database_opened" if database_existed else "database_created",
            entity_type="database",
            message="Veritabanı açıldı" if database_existed else "Veritabanı oluşturuldu",
            actor="Sistem",
            source=self.source,
        )

    def close(self):
        self.conn.close()

    @contextmanager
    def tx(self):
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _table_columns(self, table: str) -> set[str]:
        rows = self.conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
        return {str(row[1]) for row in rows}

    def _ensure_column(self, table: str, name: str, ddl: str) -> bool:
        if name not in self._table_columns(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            return True
        return False

    def init_schema(self):
        migrated = []
        self.conn.executescript(
            """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,display_name TEXT,is_active INTEGER DEFAULT 1,is_excluded INTEGER DEFAULT 0,logo_blob BLOB,logo_ext TEXT,logo_mime TEXT,logo_updated_at TEXT,sort_order INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,yi_yd TEXT DEFAULT 'Yİ',active INTEGER DEFAULT 1,note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS components(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,version TEXT,unit TEXT DEFAULT 'Adet',active INTEGER DEFAULT 1,usage REAL DEFAULT 1,payload_json TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS component_platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,component_id INTEGER NOT NULL,platform_id INTEGER NOT NULL,enabled INTEGER DEFAULT 1,UNIQUE(component_id,platform_id),FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE,FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,color TEXT,kind TEXT DEFAULT 'contract',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,platform_id INTEGER NOT NULL,user_id INTEGER,contract_no TEXT NOT NULL,user_names TEXT,yi_yd TEXT,contract_type TEXT,type_display TEXT,link_type TEXT,status TEXT,signed_date TEXT,t0_date TEXT,t0_months INTEGER,completion_date TEXT,acceptance_date TEXT,content TEXT,note TEXT,is_main INTEGER DEFAULT 1,parent_contract_id INTEGER,parent_contract_no TEXT,search_text TEXT,payload_json TEXT,created_at TEXT,updated_at TEXT,UNIQUE(platform_id,contract_no,contract_type),FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE RESTRICT,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,FOREIGN KEY(parent_contract_id) REFERENCES contracts(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS systems(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,name TEXT NOT NULL,status TEXT,completion_date TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS system_components(id INTEGER PRIMARY KEY AUTOINCREMENT,system_id INTEGER NOT NULL,component_id INTEGER NOT NULL,qty REAL DEFAULT 0,note TEXT,UNIQUE(system_id,component_id),FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE,FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,system_id INTEGER,delivery_user_id INTEGER,system_name TEXT NOT NULL,name TEXT NOT NULL,status TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE SET NULL,FOREIGN KEY(delivery_user_id) REFERENCES users(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS delivery_components(id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_id INTEGER NOT NULL,component_id INTEGER NOT NULL,planned REAL DEFAULT 0,delivered REAL DEFAULT 0,UNIQUE(delivery_id,component_id),FOREIGN KEY(delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_tags(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,tag_id INTEGER NOT NULL,UNIQUE(contract_id,tag_id),FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_file_folders(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,parent_id INTEGER,name TEXT NOT NULL,created_at TEXT,updated_at TEXT,UNIQUE(contract_id,parent_id,name),FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(parent_id) REFERENCES contract_file_folders(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_files(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,folder_id INTEGER,filename TEXT NOT NULL,original_path TEXT,file_ext TEXT,mime_type TEXT,size_bytes INTEGER NOT NULL DEFAULT 0,content_blob BLOB NOT NULL,note TEXT,created_at TEXT,updated_at TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(folder_id) REFERENCES contract_file_folders(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,actor TEXT,source TEXT,device_name TEXT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,entity_key TEXT,platform_id INTEGER,contract_no TEXT,message TEXT,before_json TEXT,after_json TEXT,payload_json TEXT,FOREIGN KEY(platform_id) REFERENCES platforms(id) ON DELETE SET NULL);
CREATE INDEX IF NOT EXISTS idx_contracts_platform_id ON contracts(platform_id);
CREATE INDEX IF NOT EXISTS idx_contracts_platform_status ON contracts(platform_id,status);
CREATE INDEX IF NOT EXISTS idx_contracts_completion_date ON contracts(completion_date);
CREATE INDEX IF NOT EXISTS idx_systems_contract_id ON systems(contract_id);
CREATE INDEX IF NOT EXISTS idx_systems_completion_date ON systems(completion_date);
CREATE INDEX IF NOT EXISTS idx_system_components_component_id ON system_components(component_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_contract_id ON deliveries(contract_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_system_id ON deliveries(system_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_contract_system ON deliveries(contract_id,system_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_acceptance_date ON deliveries(acceptance_date);
CREATE INDEX IF NOT EXISTS idx_delivery_components_component_id ON delivery_components(component_id);
CREATE INDEX IF NOT EXISTS idx_contract_file_folders_contract_id ON contract_file_folders(contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_file_folders_parent_id ON contract_file_folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_contract_files_contract_id ON contract_files(contract_id);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON activity_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_action ON activity_logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_entity ON activity_logs(entity_type,entity_id);
            """
        )
        # Existing v2 files may predate delivery-level responsibility. SQLite
        # cannot add foreign-key constraints with ALTER TABLE, but adding the
        # nullable column keeps those files readable and writable. New files
        # still receive the foreign keys from the CREATE TABLE definitions.
        if self._ensure_column("deliveries", "delivery_user_id", "INTEGER"):
            migrated.append("deliveries.delivery_user_id")
        # Component notes were added after the initial v2 schema. Keep legacy
        # STS files readable by adding the nullable column in place.
        if self._ensure_column("system_components", "note", "TEXT"):
            migrated.append("system_components.note")
        # Audit metadata columns were added after the initial activity log schema.
        for column in ("source", "device_name"):
            if self._ensure_column("activity_logs", column, "TEXT"):
                migrated.append(f"activity_logs.{column}")
        # Document folders were added after embedded contract files shipped.
        if self._ensure_column("contract_files", "folder_id", "INTEGER"):
            migrated.append("contract_files.folder_id")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_delivery_user_id ON deliveries(delivery_user_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_file_folders_contract_id ON contract_file_folders(contract_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_file_folders_parent_id ON contract_file_folders(parent_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_files_folder_id ON contract_files(folder_id)")
        ensure_staff_table(self.conn)
        ensure_document_locks_table(self.conn)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_document_locks_id ON document_locks(id)")
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','4')")
        self.conn.commit()
        return migrated

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
