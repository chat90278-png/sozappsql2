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
    enrich_staff_permissions,
    has_permission,
    list_roles,
    list_permissions,
    set_role_permission,
    update_staff_record,
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

    assert row["role"] == "admin"
    assert ROLE_LABELS["personnel"] == "Personel"
    assert verify_password("gizli", saved["password_hash"])
    assert current_staff["id"] == saved["id"]
    assert current_staff["device_name"] == "cihaz-1"
    assert current_staff["full_name"] == "Test Personel"
    assert current_staff["role"] == "admin"
    assert current_staff["role_id"] is not None
    assert current_staff["role_display_name"] == "Admin"
    assert current_staff["is_active"] == 1


def test_require_staff_login_sets_current_staff_for_register_and_auto_device_login():
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

        def fail_login(*_args, **_kwargs):
            raise AssertionError("Kayıtlı cihaz için şifre/login dialogu açılmamalı")

        auth_module.show_staff_register_dialog = fake_register
        registered = auth_module.require_staff_login(conn)
        assert registered == auth_module.current_staff
        assert registered["device_name"] == "startup-cihaz"
        assert registered["full_name"] == "Startup Personel"

        auth_module.show_staff_login_dialog = fail_login
        logged_in = auth_module.require_staff_login(conn)
        assert logged_in == auth_module.current_staff
        assert logged_in["id"] == registered["id"]
        assert logged_in["device_name"] == "startup-cihaz"
    finally:
        auth_module.get_device_name = original_device
        auth_module.show_staff_register_dialog = original_register
        auth_module.show_staff_login_dialog = original_login
        auth_module.current_staff = None


def test_permission_defaults_and_last_full_access_guard():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_staff_table(conn)
    admin_row = create_staff(conn, "admin-cihaz", "Admin", "gizli")
    admin = enrich_staff_permissions(conn, build_current_staff(admin_row))
    assert auth_module.PERMISSION_RESTRICTIONS_ENABLED is False
    assert has_permission(None, "manage_roles", conn)
    assert has_permission(admin, "manage_roles", conn)
    assert has_permission(admin, "sql_write", conn)

    roles = {r["name"]: r for r in list_roles(conn)}
    permissions = {p["code"] for p in list_permissions(conn)}
    assert {"admin", "manager", "personnel", "viewer"}.issubset(roles)
    assert {"manage_staff", "manage_roles", "open_sql_panel", "sql_read", "sql_write", "view_action_history", "change_staff_roles", "reset_staff_passwords"}.issubset(permissions)

    manager = create_staff(conn, "manager-cihaz", "Manager", "gizli", role_id=roles["manager"]["id"])
    manager_user = enrich_staff_permissions(conn, build_current_staff(manager))
    assert has_permission(manager_user, "manage_staff", conn)
    assert has_permission(manager_user, "sql_write", conn)
    assert has_permission(manager_user, "view_action_history", conn)

    original_restrictions_enabled = auth_module.PERMISSION_RESTRICTIONS_ENABLED
    try:
        auth_module.PERMISSION_RESTRICTIONS_ENABLED = True
        assert not has_permission(manager_user, "manage_staff", conn)
        assert has_permission(manager_user, "sql_write", conn)
        assert has_permission(manager_user, "view_action_history", conn)
    finally:
        auth_module.PERMISSION_RESTRICTIONS_ENABLED = original_restrictions_enabled

    try:
        update_staff_record(conn, admin, admin["id"], is_active=0)
    except ValueError as exc:
        assert "yetkili kullanıcı" in str(exc)
    else:
        raise AssertionError("Son yetkili kullanıcı pasifleştirilememeli")

    set_role_permission(conn, admin, roles["manager"]["id"], "sql_write", True)
    manager_user = enrich_staff_permissions(conn, build_current_staff(get_staff_by_device(conn, "manager-cihaz")))
    assert has_permission(manager_user, "sql_write", conn)


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

    initial = get_document_lock_state(conn, 1)
    assert initial["is_locked"] == 0
    assert initial["contract_id"] == 1
    assert can_current_staff_access_documents(initial, other_staff)

    locked = lock_documents(conn, 1, staff)
    assert locked["is_locked"] == 1
    assert locked["contract_id"] == 1
    assert locked["locked_by_staff_id"] == staff["id"]
    assert locked["locked_by_device_name"] == "kilitleyen-cihaz"
    assert can_current_staff_access_documents(locked, staff)
    assert not can_current_staff_access_documents(locked, other_staff)

    other_contract = get_document_lock_state(conn, 2)
    assert other_contract["is_locked"] == 0
    assert other_contract["contract_id"] == 2
    assert verify_staff_password_by_id(conn, staff["id"], "gizli")
    assert not verify_staff_password_by_id(conn, staff["id"], "yanlis")
    assert not verify_staff_password_by_id(conn, 999999, "gizli")
    conn.execute("UPDATE staff SET is_active=0 WHERE id=?", (staff["id"],))
    conn.commit()
    assert not verify_staff_password_by_id(conn, staff["id"], "gizli")
    conn.execute("UPDATE staff SET is_active=1 WHERE id=?", (staff["id"],))
    conn.commit()

    unlocked = unlock_documents(conn, 1)
    assert unlocked["is_locked"] == 0
    assert unlocked["contract_id"] == 1
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

    assert {"roles", "permissions", "role_permissions", "staff"}.issubset(tables)
    assert "staff" in stats["table_counts"]
    assert "roles" in stats["table_counts"]
    assert "permissions" in stats["table_counts"]
    assert "role_permissions" in stats["table_counts"]
    assert "document_locks" in stats["table_counts"]
    assert "sqlite_sequence" not in stats["table_counts"]
    assert {"device_name", "full_name", "password_hash", "role", "role_id", "is_active", "last_login_at", "created_at", "updated_at"}.issubset(columns)
    assert {"contract_id", "is_locked", "locked_by_staff_id", "locked_by_device_name", "locked_by_full_name"}.issubset(lock_columns)


if __name__ == "__main__":
    test_password_hashing_uses_salt_and_verifies()
    test_staff_table_create_and_current_staff_payload()
    test_require_staff_login_sets_current_staff_for_register_and_auto_device_login()
    test_permission_defaults_and_last_full_access_guard()
    test_document_lock_helpers_are_exported()
    test_document_lock_state_and_device_access()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_sts_database_initializes_staff_table(Path(td))
    print("ok")
