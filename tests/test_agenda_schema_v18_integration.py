from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.auth import ensure_staff_table
from src.services import sts_schema_upgrade as upgrade
from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase, read_sts_schema_version
from src.services.sts_schema_upgrade_gate import validate_versioned_schema_fingerprint


EXPECTED_COLUMNS = (
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
)


def _columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")'))


def _pk(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return tuple(
        str(row[1])
        for row in sorted((row for row in rows if row[5]), key=lambda row: row[5])
    )


def test_helper_creates_exact_transaction_neutral_contract(tmp_path: Path):
    path = tmp_path / "helper.sts"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_staff_table(conn)
    conn.commit()

    conn.execute("BEGIN")
    created = upgrade.ensure_staff_agenda_state_schema(conn)
    assert conn.in_transaction
    assert created == (
        "staff_agenda_state",
        "idx_staff_agenda_state_staff",
        "idx_staff_agenda_state_snoozed",
    )
    assert _columns(conn, "staff_agenda_state") == EXPECTED_COLUMNS
    assert _pk(conn, "staff_agenda_state") == ("staff_id", "agenda_key")
    fk = conn.execute('PRAGMA foreign_key_list("staff_agenda_state")').fetchall()
    assert [(row[3], row[2], row[4], row[6].upper()) for row in fk] == [
        ("staff_id", "staff", "id", "CASCADE")
    ]
    assert tuple(
        row[2]
        for row in conn.execute(
            'PRAGMA index_info("idx_staff_agenda_state_staff")'
        )
    ) == ("staff_id",)
    assert tuple(
        row[2]
        for row in conn.execute(
            'PRAGMA index_info("idx_staff_agenda_state_snoozed")'
        )
    ) == ("staff_id", "snoozed_until")
    assert upgrade.ensure_staff_agenda_state_schema(conn) == ()
    assert conn.in_transaction
    conn.rollback()
    conn.close()


def test_helper_fails_closed_without_staff_parent(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "missing-parent.sts")
    with pytest.raises(RuntimeError, match="staff"):
        upgrade.ensure_staff_agenda_state_schema(conn)
    conn.close()


def test_helper_rejects_malformed_preexisting_table(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "malformed.sts")
    ensure_staff_table(conn)
    conn.execute("CREATE TABLE staff_agenda_state(staff_id INTEGER, agenda_key TEXT)")
    with pytest.raises(RuntimeError, match="kolon"):
        upgrade.ensure_staff_agenda_state_schema(conn)
    conn.close()


def test_real_v17_without_agenda_state_upgrades_to_v18(tmp_path: Path):
    path = tmp_path / "real-v17.sts"
    db = STSDatabase(path)
    db.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_staff")
    conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_snoozed")
    conn.execute("DROP TABLE IF EXISTS staff_agenda_state")
    conn.execute("UPDATE meta SET value='17' WHERE key='schema_version'")
    conn.commit()
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='staff_agenda_state'"
    ).fetchone() is None
    conn.close()

    result = upgrade.upgrade_sts_file(path)
    assert result.applied_migrations == ("v17_to_v18_staff_agenda_state",)
    assert read_sts_schema_version(path) == CURRENT_SCHEMA_VERSION == 18
    validate_versioned_schema_fingerprint(path, 18)


def test_state_survives_reopen_and_staff_delete_cascades(tmp_path: Path):
    path = tmp_path / "cascade.sts"
    db = STSDatabase(path)
    try:
        staff_id = db.conn.execute(
            "INSERT INTO staff(username,password_hash,full_name,is_active,is_admin) "
            "VALUES('agenda-user','x','Agenda User',1,0)"
        ).lastrowid
        db.conn.execute(
            "INSERT INTO staff_agenda_state(staff_id,agenda_key,seen_version) "
            "VALUES(?,?,?)",
            (staff_id, "deadline:contract:1", "v1"),
        )
        db.conn.commit()
    finally:
        db.close()

    reopened = STSDatabase(path)
    try:
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM staff_agenda_state"
        ).fetchone()[0] == 1
        reopened.conn.execute("DELETE FROM staff WHERE id=?", (staff_id,))
        reopened.conn.commit()
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM staff_agenda_state"
        ).fetchone()[0] == 0
        assert reopened.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agenda_items'"
        ).fetchone() is None
    finally:
        reopened.close()
