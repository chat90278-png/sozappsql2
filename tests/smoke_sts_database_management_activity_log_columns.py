import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_database import STSDatabase


EXPECTED = [
    "id", "created_at", "actor", "source", "device_name", "action", "entity_type", "entity_id",
    "entity_key", "platform_id", "contract_no", "message", "before_json", "after_json", "payload_json",
]

with TemporaryDirectory() as td:
    path = Path(td) / "management-preview.sts"
    db = STSDatabase(path)
    db.add_log("preview_test", actor="Kullanıcı", source="Database Management", device="TEST-PC")
    rows = db.preview_table("activity_logs", limit=100)
    assert rows
    assert list(rows[0]) == EXPECTED
    assert rows[-1]["source"] == "Database Management"
    assert rows[-1]["device_name"] == "TEST-PC"

    # Other previews retain their natural SQLite column order.
    assert db.preview_table("platforms", limit=100) == []
    db.conn.execute("INSERT INTO platforms(name) VALUES('AKINCI')")
    db.conn.commit()
    assert list(db.preview_table("platforms", limit=100)[0]) == [row[1] for row in db.conn.execute("PRAGMA table_info(platforms)")]
    db.close()

    # Legacy-compatible safety: if preview is used against an older connection,
    # optional activity log columns are selected only when they actually exist.
    legacy_path = Path(td) / "legacy-preview.sts"
    legacy = sqlite3.connect(legacy_path)
    legacy.execute("CREATE TABLE activity_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, actor TEXT, action TEXT NOT NULL)")
    legacy.execute("INSERT INTO activity_logs(created_at,actor,action) VALUES('2026-06-02 10:00:00','Kullanıcı','legacy')")
    legacy.commit()
    legacy.close()

    preview = STSDatabase.__new__(STSDatabase)
    preview.path = legacy_path
    preview.source = "Test"
    preview.conn = sqlite3.connect(legacy_path)
    preview.conn.row_factory = sqlite3.Row
    rows = preview.preview_table("activity_logs", limit=100)
    assert list(rows[0]) == ["id", "created_at", "actor", "action"]
    preview.close()

print("ok")
