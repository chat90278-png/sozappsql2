from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class STSDatabase:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.init_schema()

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
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r[1]) for r in rows}

    def _ensure_column(self, table: str, name: str, ddl: str):
        if name not in self._table_columns(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def init_schema(self):
        self.conn.executescript(
            """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,display_name TEXT,is_active INTEGER DEFAULT 1,is_excluded INTEGER DEFAULT 0,logo_blob BLOB,logo_ext TEXT,logo_mime TEXT,logo_updated_at TEXT,sort_order INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,yi_yd TEXT DEFAULT 'Yİ',active INTEGER DEFAULT 1,note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS components(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,version TEXT,unit TEXT DEFAULT 'Adet',active INTEGER DEFAULT 1,usage REAL DEFAULT 1,payload_json TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS component_platforms(id INTEGER PRIMARY KEY AUTOINCREMENT,component_id INTEGER NOT NULL,platform_name TEXT NOT NULL,enabled INTEGER DEFAULT 1,UNIQUE(component_id,platform_name),FOREIGN KEY(component_id) REFERENCES components(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,color TEXT,kind TEXT DEFAULT 'contract',created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,platform TEXT NOT NULL,contract_no TEXT NOT NULL,user_name TEXT,yi_yd TEXT,contract_type TEXT,type_display TEXT,link_type TEXT,status TEXT,signed_date TEXT,t0_date TEXT,t0_months INTEGER,completion_date TEXT,acceptance_date TEXT,content TEXT,note TEXT,is_main INTEGER DEFAULT 1,parent_contract_id INTEGER,parent_contract_no TEXT,search_text TEXT,payload_json TEXT,created_at TEXT,updated_at TEXT,UNIQUE(platform,contract_no,contract_type),FOREIGN KEY(parent_contract_id) REFERENCES contracts(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS systems(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,name TEXT NOT NULL,status TEXT,completion_date TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS system_components(id INTEGER PRIMARY KEY AUTOINCREMENT,system_id INTEGER NOT NULL,component_name TEXT NOT NULL,qty REAL DEFAULT 0,UNIQUE(system_id,component_name),FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,system_id INTEGER,system_name TEXT NOT NULL,name TEXT NOT NULL,status TEXT,acceptance_date TEXT,note TEXT,sort_order INTEGER DEFAULT 0,payload_json TEXT,FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,FOREIGN KEY(system_id) REFERENCES systems(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS delivery_components(id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_id INTEGER NOT NULL,component_name TEXT NOT NULL,planned REAL DEFAULT 0,delivered REAL DEFAULT 0,UNIQUE(delivery_id,component_name),FOREIGN KEY(delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS contract_tags(id INTEGER PRIMARY KEY AUTOINCREMENT,contract_id INTEGER NOT NULL,tag_name TEXT NOT NULL,UNIQUE(contract_id,tag_name),FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,actor TEXT,action TEXT NOT NULL,entity_type TEXT,entity_id TEXT,entity_key TEXT,platform TEXT,contract_no TEXT,message TEXT,before_json TEXT,after_json TEXT,payload_json TEXT);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON activity_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_action ON activity_logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_entity_type ON activity_logs(entity_type);
CREATE INDEX IF NOT EXISTS idx_logs_platform ON activity_logs(platform);
CREATE INDEX IF NOT EXISTS idx_logs_contract_no ON activity_logs(contract_no);
"""
        )
        # migration-safe columns
        self._ensure_column("platforms", "logo_mime", "TEXT")
        self._ensure_column("platforms", "logo_updated_at", "TEXT")
        self._ensure_column("activity_logs", "actor", "TEXT")
        self._ensure_column("activity_logs", "entity_id", "TEXT")
        self._ensure_column("activity_logs", "platform", "TEXT")
        self._ensure_column("activity_logs", "contract_no", "TEXT")
        self._ensure_column("activity_logs", "before_json", "TEXT")
        self._ensure_column("activity_logs", "after_json", "TEXT")
        self.conn.commit()

    def add_log(self, action: str, entity_type: str = "", entity_key: str = "", message: str = "", payload: dict | None = None,
                actor: str | None = None, entity_id: str | int | None = None, platform: str | None = None,
                contract_no: str | None = None, before: dict | None = None, after: dict | None = None):
        try:
            self.conn.execute(
                "INSERT INTO activity_logs(created_at,actor,action,entity_type,entity_id,entity_key,platform,contract_no,message,before_json,after_json,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    now_iso(), actor or "", action or "", entity_type or "", "" if entity_id is None else str(entity_id),
                    entity_key or "", platform or "", contract_no or "", message or "",
                    json.dumps(before, ensure_ascii=False) if before is not None else None,
                    json.dumps(after, ensure_ascii=False) if after is not None else None,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                )
            )
            self.conn.commit()
        except Exception:
            pass

    def list_logs(self, limit: int = 500, action: str | None = None, entity_type: str | None = None,
                  platform: str | None = None, contract_no: str | None = None, search: str | None = None):
        q = "SELECT * FROM activity_logs WHERE 1=1"
        params = []
        if action:
            q += " AND action=?"; params.append(action)
        if entity_type:
            q += " AND entity_type=?"; params.append(entity_type)
        if platform:
            q += " AND platform=?"; params.append(platform)
        if contract_no:
            q += " AND contract_no=?"; params.append(contract_no)
        if search:
            q += " AND (message LIKE ? OR entity_key LIKE ? OR actor LIKE ? OR action LIKE ? OR platform LIKE ? OR contract_no LIKE ?)"
            s = f"%{search}%"; params.extend([s, s, s, s, s, s])
        q += " ORDER BY created_at DESC"
        if limit and int(limit) > 0:
            q += " LIMIT ?"; params.append(int(limit))
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]
