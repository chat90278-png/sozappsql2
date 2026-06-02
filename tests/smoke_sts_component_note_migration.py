import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_database import STSDatabase


with TemporaryDirectory() as td:
    path = Path(td) / "legacy-component-notes.sts"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE system_components(id INTEGER PRIMARY KEY AUTOINCREMENT,system_id INTEGER NOT NULL,component_id INTEGER NOT NULL,qty REAL DEFAULT 0,UNIQUE(system_id,component_id))")
    conn.execute("INSERT INTO system_components(system_id,component_id,qty) VALUES(1,2,3)")
    conn.commit()
    conn.close()

    db = STSDatabase(path)
    columns = {row[1] for row in db.conn.execute("PRAGMA table_info(system_components)")}
    assert "note" in columns
    row = db.conn.execute("SELECT system_id,component_id,qty,note FROM system_components").fetchone()
    assert row[:] == (1, 2, 3.0, None)
    db.close()

print("ok")
