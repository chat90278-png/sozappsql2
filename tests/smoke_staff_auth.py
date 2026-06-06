import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth import (
    ROLE_LABELS,
    build_current_staff,
    create_staff,
    ensure_document_locks_table,
    ensure_staff_table,
    get_document_lock_state,
    get_staff_by_device,
    hash_password,
    lock_documents,
    unlock_documents,
    can_current_staff_access_documents,
    verify_staff_password_by_id,
    verify_password,
)
from src.services.sts_database import STSDatabase


def test_password_hashing_uses_salt_and_verifies():
    first = hash_password("gizli")
    second = hash_password("gizli")
    assert ":" in first
    assert first != second
    assert verify_password("gizli", first)
    assert not verify_password("yanlis", first)


def test_staff_table_create_and_current_staff_payload():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_staff_table(conn)

    row = create_staff(conn, "cihaz-1", "Test Personel", "gizli")
    saved = get_staff_by_device(conn, "cihaz-1")
    current_staff = build_current_staff(saved)

    assert row["role"] == "staff"
    assert ROLE_LABELS["staff"] == "Personel"
    assert verify_password("gizli", saved["password_hash"])
    assert current_staff == {
        "id": saved["id"],
        "device_name": "cihaz-1",
        "full_name": "Test Personel",
        "role": "staff",
        "is_active": 1,
    }


def test_document_lock_state_and_device_access():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_staff_table(conn)
    ensure_document_locks_table(conn)

    row = create_staff(conn, "kilitleyen-cihaz", "Kilitleyen Personel", "gizli")
    staff = build_current_staff(row)
    other_staff = {**staff, "device_name": "baska-cihaz"}

    initial = get_document_lock_state(conn)
    assert initial["is_locked"] == 0
    assert can_current_staff_access_documents(initial, other_staff)

    locked = lock_documents(conn, staff)
    assert locked["is_locked"] == 1
    assert locked["locked_by_staff_id"] == staff["id"]
    assert locked["locked_by_device_name"] == "kilitleyen-cihaz"
    assert can_current_staff_access_documents(locked, staff)
    assert not can_current_staff_access_documents(locked, other_staff)
    assert verify_staff_password_by_id(conn, staff["id"], "gizli")
    assert not verify_staff_password_by_id(conn, staff["id"], "yanlis")

    unlocked = unlock_documents(conn)
    assert unlocked["is_locked"] == 0
    assert unlocked["locked_by_staff_id"] is None
    assert can_current_staff_access_documents(unlocked, other_staff)


def test_sts_database_initializes_staff_table(tmp_path):
    db = STSDatabase(tmp_path / "auth.sts")
    try:
        tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in db.conn.execute("PRAGMA table_info(staff)")}
        lock_columns = {row[1] for row in db.conn.execute("PRAGMA table_info(document_locks)")}
        stats = db.database_stats()
    finally:
        db.close()

    assert "staff" in tables
    assert "staff" in stats["table_counts"]
    assert "document_locks" in stats["table_counts"]
    assert "sqlite_sequence" not in stats["table_counts"]
    assert {"device_name", "full_name", "password_hash", "role", "is_active"}.issubset(columns)
    assert {"is_locked", "locked_by_staff_id", "locked_by_device_name", "locked_by_full_name"}.issubset(lock_columns)


if __name__ == "__main__":
    test_password_hashing_uses_salt_and_verifies()
    test_staff_table_create_and_current_staff_payload()
    test_document_lock_state_and_device_access()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_sts_database_initializes_staff_table(Path(td))
    print("ok")
