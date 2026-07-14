from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase


EXPECTED_COLUMNS = {
    "staff_id",
    "agenda_key",
    "first_presented_at",
    "last_presented_at",
    "seen_at",
    "seen_version",
    "snoozed_until",
    "snoozed_version",
    "snoozed_severity",
    "dismissed_at",
    "dismissed_version",
    "created_at",
    "updated_at",
}


with TemporaryDirectory() as td:
    path = Path(td) / "agenda-schema.sts"
    db = STSDatabase(path, source="Agenda Schema Smoke")

    tables = {
        str(row[0])
        for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "staff_agenda_state" in tables
    assert "agenda_items" not in tables

    table_info = db.conn.execute("PRAGMA table_info(staff_agenda_state)").fetchall()
    columns = {str(row[1]) for row in table_info}
    assert columns == EXPECTED_COLUMNS, (EXPECTED_COLUMNS - columns, columns - EXPECTED_COLUMNS)

    pk_positions = {str(row[1]): int(row[5] or 0) for row in table_info}
    assert pk_positions["staff_id"] == 1
    assert pk_positions["agenda_key"] == 2

    foreign_keys = db.conn.execute("PRAGMA foreign_key_list(staff_agenda_state)").fetchall()
    staff_fk = [
        row
        for row in foreign_keys
        if str(row[2]) == "staff" and str(row[3]) == "staff_id" and str(row[4]) == "id"
    ]
    assert len(staff_fk) == 1
    assert str(staff_fk[0][6]).upper() == "CASCADE"

    indexes = {
        str(row[1])
        for row in db.conn.execute("PRAGMA index_list(staff_agenda_state)").fetchall()
    }
    assert "idx_staff_agenda_state_staff" in indexes
    assert "idx_staff_agenda_state_snoozed" in indexes

    schema_version = db.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert CURRENT_SCHEMA_VERSION == 19
    assert schema_version == str(CURRENT_SCHEMA_VERSION)

    db.init_schema()
    schema_version_after_second_init = db.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert schema_version_after_second_init == "19"

    tables_after_second_init = {
        str(row[0])
        for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "staff_agenda_state" in tables_after_second_init
    assert "agenda_items" not in tables_after_second_init
    assert db.foreign_key_check() == []
    assert db.integrity_check() == ["ok"]

    db.close()

print("agenda_schema=PASS")
print("schema_version=19")
