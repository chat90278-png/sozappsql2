import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth import ensure_document_locks_table


EXPECTED_COLUMNS = {
    "is_locked",
    "locked_by_staff_id",
    "locked_by_device_name",
    "locked_by_full_name",
    "locked_at",
    "updated_at",
}

with TemporaryDirectory() as td:
    path = Path(td) / "legacy-document-locks.sts"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE document_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL UNIQUE
        )
        """
    )
    conn.execute("INSERT INTO document_locks(contract_id) VALUES(1)")
    conn.commit()
    conn.close()

    ensure_document_locks_table(path)

    conn = sqlite3.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(document_locks)")}
    assert EXPECTED_COLUMNS.issubset(columns)
    row = conn.execute("SELECT is_locked FROM document_locks WHERE contract_id=1").fetchone()
    assert row == (0,)
    conn.close()

print("ok")
