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
import src.auth as auth_module


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


def test_require_staff_login_sets_current_staff_for_register_and_login():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_staff_table(conn)

    original_device = auth_module.get_device_name
    original_register = auth_module.show_staff_register_dialog
    original_login = auth_module.show_staff_login_dialog
    try:
        auth_module.current_staff = None
        auth_module.get_device_name = lambda: "startup-cihaz"

        def fake_register(db_or_path, device_name, parent=None):
            return build_current_staff(create_staff(db_or_path, device_name, "Startup Personel", "gizli"))

        auth_module.show_staff_register_dialog = fake_register
        registered = auth_module.require_staff_login(conn)
        assert registered == auth_module.current_staff
        assert registered["device_name"] == "startup-cihaz"
        assert registered["full_name"] == "Startup Personel"

        def fake_login(db_or_path, row, parent=None):
            assert row["device_name"] == "startup-cihaz"
            return build_current_staff(row)

        auth_module.show_staff_login_dialog = fake_login
        logged_in = auth_module.require_staff_login(conn)
        assert logged_in == auth_module.current_staff
        assert logged_in["id"] == registered["id"]
    finally:
        auth_module.get_device_name = original_device
        auth_module.show_staff_register_dialog = original_register
        auth_module.show_staff_login_dialog = original_login
        auth_module.current_staff = None


def test_document_lock_helpers_are_exported():
    for name in (
        "ensure_document_locks_table",
        "get_document_lock_state",
        "lock_documents",
        "unlock_documents",
        "can_current_staff_access_documents",
        "verify_staff_password_by_id",
    ):
        assert hasattr(auth_module, name), name
        assert callable(getattr(auth_module, name)), name


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
    assert not verify_staff_password_by_id(conn, 999999, "gizli")
    conn.execute("UPDATE staff SET is_active=0 WHERE id=?", (staff["id"],))
    conn.commit()
    assert not verify_staff_password_by_id(conn, staff["id"], "gizli")
    conn.execute("UPDATE staff SET is_active=1 WHERE id=?", (staff["id"],))
    conn.commit()

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
    test_require_staff_login_sets_current_staff_for_register_and_login()
    test_document_lock_helpers_are_exported()
    test_document_lock_state_and_device_access()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_sts_database_initializes_staff_table(Path(td))
    print("ok")
