import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth import (
    ROLE_LABELS,
    build_current_staff,
    create_staff,
    ensure_staff_table,
    get_staff_by_device,
    hash_password,
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


def test_sts_database_initializes_staff_table(tmp_path):
    db = STSDatabase(tmp_path / "auth.sts")
    try:
        tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in db.conn.execute("PRAGMA table_info(staff)")}
    finally:
        db.close()

    assert "staff" in tables
    assert {"device_name", "full_name", "password_hash", "role", "is_active"}.issubset(columns)


if __name__ == "__main__":
    test_password_hashing_uses_salt_and_verifies()
    test_staff_table_create_and_current_staff_payload()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_sts_database_initializes_staff_table(Path(td))
    print("ok")


# ---------------------------------------------------------------------------
# Belge Kilidi (Document Lock) smoke testleri
# ---------------------------------------------------------------------------

from src.auth import (
    can_current_staff_access_documents,
    ensure_document_locks_table,
    get_document_lock_state,
    lock_documents,
    unlock_documents,
    verify_staff_password_by_id,
)


def test_document_lock_functions_exist():
    import src.auth as _auth
    for fn_name in [
        "get_document_lock_state",
        "lock_documents",
        "unlock_documents",
        "can_current_staff_access_documents",
        "verify_staff_password_by_id",
        "require_document_unlock_password",
    ]:
        assert hasattr(_auth, fn_name), f"src.auth eksik fonksiyon: {fn_name}"


def test_get_document_lock_state_empty_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    state = get_document_lock_state(conn)
    assert state["is_locked"] == 0
    assert state["locked_by_device_name"] is None


def test_lock_and_unlock_documents():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_document_locks_table(conn)

    staff = {"id": 1, "device_name": "cihaz-A", "full_name": "Test Kişi", "role": "staff", "is_active": 1}
    locked = lock_documents(conn, staff)
    assert locked["is_locked"] == 1
    assert locked["locked_by_device_name"] == "cihaz-A"
    assert locked["locked_by_full_name"] == "Test Kişi"

    unlocked = unlock_documents(conn)
    assert unlocked["is_locked"] == 0
    assert unlocked["locked_by_device_name"] is None


def test_can_current_staff_access_documents():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    staff_a = {"id": 1, "device_name": "cihaz-A", "full_name": "Kişi A", "role": "staff", "is_active": 1}
    staff_b = {"id": 2, "device_name": "cihaz-B", "full_name": "Kişi B", "role": "staff", "is_active": 1}

    # lock_state None → True
    assert can_current_staff_access_documents(None, None) is True

    # unlocked → True
    state = get_document_lock_state(conn)
    assert can_current_staff_access_documents(state, staff_a) is True

    # kilitlendi — aynı cihaz True, farklı cihaz False
    locked = lock_documents(conn, staff_a)
    assert can_current_staff_access_documents(locked, staff_a) is True
    assert can_current_staff_access_documents(locked, staff_b) is False
    assert can_current_staff_access_documents(locked, None) is False

    # kilidi kaldır → True
    unlocked = unlock_documents(conn)
    assert can_current_staff_access_documents(unlocked, staff_b) is True


def test_verify_staff_password_by_id():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_staff_table(conn)
    create_staff(conn, "cihaz-test", "Doğrulama Testi", "gizli123")
    row = get_staff_by_device(conn, "cihaz-test")
    staff_id = int(row["id"])

    assert verify_staff_password_by_id(conn, staff_id, "gizli123") is True
    assert verify_staff_password_by_id(conn, staff_id, "yanlis") is False
    assert verify_staff_password_by_id(conn, 9999, "gizli123") is False
