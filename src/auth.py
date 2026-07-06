from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import socket
import sqlite3
from pathlib import Path
from typing import Any, Optional

ROLE_LABELS = {
    "admin": "Admin",
    "manager": "Yönetici",
    "personnel": "Personel",
    "viewer": "Görüntüleyici",
    # Legacy value kept only for old rows until migrated to roles.role_id.
    "staff": "Personel",
}

FULL_ACCESS_PERMISSIONS = {
    "manage_staff",
    "manage_roles",
}

# Development switch: keep the authorization schema, roles and permission
# definitions in place, but temporarily stop permission checks from blocking
# users. Flip this back to True when the restrictions should be enforced again.
PERMISSION_RESTRICTIONS_ENABLED = True

AUTHORIZATION_REQUIRED_PERMISSIONS = {
    "manage_staff",
    "manage_roles",
}

PERMISSION_GROUPS = [
    (
        "Sözleşme İşlemleri",
        [
            ("view_contracts", "Sözleşme Listeleme", "Ana sözleşme tablosunu görüntüler."),
            ("create_contracts", "Sözleşme Ekleme", "Yeni sözleşme kaydı oluşturur."),
            ("edit_contracts", "Sözleşme Düzenleme", "Mevcut sözleşme bilgilerini değiştirir."),
            ("delete_contracts", "Sözleşme Silme", "Sözleşme kaydını sistemden kaldırır."),
            ("export_data", "Dışa Aktarma", "Excel veya rapor çıktısı alır."),
        ],
    ),
    (
        "Operasyon Yönetimi",
        [
            ("manage_acceptances", "Teslimat Yönetimi", "Teslimat kayıtlarını yönetir."),
            ("manage_terms", "Termin Yönetimi", "Termin/takvim bilgilerini yönetir."),
            ("manage_labels", "Etiket Yönetimi", "Etiket tanımlarını yönetir."),
            ("manage_platforms", "Platform / Bileşen Yönetimi", "Platform ve bileşen tanımlarını yönetir."),
            ("manage_components", "Bileşen Yönetimi", "Bileşen tanımlarını yönetir."),
        ],
    ),
    (
        "SQL / Terminal",
        [
            ("open_sql_panel", "SQL Paneli Erişimi", "Database sorgu ekranını açar."),
            ("sql_read", "SQL Sorgu Çalıştırma", "SELECT ve güvenli okuma sorguları çalıştırır."),
            ("sql_write", "SQL Veri Değiştirme", "INSERT, UPDATE, DELETE gibi işlemleri yapar."),
            ("terminal_full_access", "Terminal Tam Erişim", "Terminali kısıtlamasız kullanır."),
        ],
    ),
    (
        "Personel Yönetimi",
        [
            ("manage_staff", "Personel Listeleme", "Kullanıcı listesini görüntüler."),
            ("create_staff", "Personel Ekleme", "Yeni kullanıcı oluşturur."),
            ("edit_staff", "Personel Düzenleme", "Kullanıcı bilgilerini günceller."),
            ("manage_roles", "Rol / Yetki Değiştirme", "Kullanıcı rolü ve rol yetkilerini düzenler."),
            ("change_staff_roles", "Personel Rolü Değiştirme", "Personelin bağlı olduğu rolü değiştirir."),
            ("reset_staff_passwords", "Şifre Sıfırlama", "Personel şifresini yeniler."),
        ],
    ),
    (
        "Diğer",
        [
            ("view_action_history", "İşlem Geçmişi Görüntüleme", "Uygulama içi yapılan işlemleri görüntüler."),
            ("access_settings", "Sistem Ayarları Yönetimi", "Genel uygulama ayarlarını değiştirir."),
            ("access_backup", "Yedekleme", "Yedekleme işlemlerini çalıştırır."),
            ("access_database_tools", "Database Araçları", "Database araçlarına erişir."),
            ("lock_documents", "Belge Kilitleme", "Sözleşme belgelerini kilitler."),
            ("unlock_own_documents", "Kendi Kilidini Açma", "Kendi kilitlediği belgelerin kilidini açar."),
            ("unlock_all_documents", "Tüm Kilitleri Açma", "Tüm belge kilitlerini açar."),
        ],
    ),
]

DEFAULT_PERMISSIONS = [
    (code, display, desc, category)
    for category, permissions in PERMISSION_GROUPS
    for code, display, desc in permissions
]

# Backward-compatible aliases are seeded and checked, but new code should use
# the canonical permission codes above.
LEGACY_PERMISSION_ALIASES = {
    "assign_roles": "change_staff_roles",
    "reset_staff_password": "reset_staff_passwords",
}
LEGACY_PERMISSIONS = [
    ("assign_roles", "Rol atama", "Eski sürümlerden gelen rol atama yetkisi.", "Personel Yönetimi"),
    ("reset_staff_password", "Şifre sıfırlama", "Eski sürümlerden gelen şifre sıfırlama yetkisi.", "Personel Yönetimi"),
]

DEFAULT_ROLE_PERMISSIONS = {
    "manager": {
        "view_contracts", "create_contracts", "edit_contracts", "delete_contracts", "export_data",
        "manage_acceptances", "manage_terms", "manage_labels", "manage_platforms", "manage_components",
        "open_sql_panel", "sql_read", "sql_write", "terminal_full_access",
        "view_action_history", "access_database_tools", "lock_documents", "unlock_own_documents",
        "unlock_all_documents",
    },
    "personnel": {"view_contracts", "create_contracts", "edit_contracts", "export_data", "open_sql_panel", "sql_read", "lock_documents", "unlock_own_documents"},
    "viewer": {"view_contracts"},
}

current_staff: Optional[dict[str, Any]] = None


_SYSTEM_ADMINS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS system_admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    last_login_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
"""


_STAFF_INVITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS staff_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invite_code_hash TEXT NOT NULL,
    invite_code_hint TEXT,
    role_id INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1,
    max_uses INTEGER DEFAULT 1,
    used_count INTEGER DEFAULT 0,
    expires_at TEXT,
    created_by_admin_id INTEGER,
    created_by_staff_id INTEGER,
    created_by_full_name TEXT,
    created_by_device_name TEXT,
    used_at TEXT,
    used_by_staff_id INTEGER,
    used_by_full_name TEXT,
    used_by_device_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY(created_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL,
    FOREIGN KEY(used_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL
);
"""

_STAFF_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'personnel',
    role_id INTEGER,
    is_active INTEGER DEFAULT 1,
    last_login_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE SET NULL
);
"""


def _database_path_from_connection(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        if row:
            return str(row[2] if not isinstance(row, sqlite3.Row) else row["file"])
    except Exception:
        pass
    return ""


def _connection_from(db_or_path: sqlite3.Connection | str | Path) -> tuple[sqlite3.Connection, bool]:
    if isinstance(db_or_path, sqlite3.Connection):
        db_or_path.row_factory = sqlite3.Row
        return db_or_path, False
    conn = sqlite3.connect(str(Path(db_or_path)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn, True


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def ensure_staff_table(db_or_path: sqlite3.Connection | str | Path) -> None:
    conn, should_close = _connection_from(db_or_path)
    try:
        ensure_authorization_schema(conn)
        conn.commit()
    finally:
        if should_close:
            conn.close()


def ensure_authorization_schema(db_or_path: sqlite3.Connection | str | Path) -> None:
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                is_system INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                description TEXT,
                category TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL,
                permission_code TEXT NOT NULL,
                is_allowed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(role_id, permission_code),
                FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY(permission_code) REFERENCES permissions(code) ON DELETE CASCADE
            )
            """
        )
        conn.execute(_STAFF_TABLE_SQL)
        conn.execute(_SYSTEM_ADMINS_TABLE_SQL)
        conn.execute(_STAFF_INVITES_TABLE_SQL)
        columns = _table_columns(conn, "staff")
        for name, ddl in (
            ("role_id", "INTEGER"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("last_login_at", "TEXT"),
            ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TEXT"),
            ("device_name", "TEXT"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE staff ADD COLUMN {name} {ddl}")
        if "role" not in columns:
            conn.execute("ALTER TABLE staff ADD COLUMN role TEXT DEFAULT 'personnel'")
        columns = _table_columns(conn, "staff")
        if "device_name" in columns:
            fallback_columns = [name for name in ("username", "device", "hostname") if name in columns]
            for fallback in fallback_columns:
                conn.execute(f"UPDATE staff SET device_name={fallback} WHERE (device_name IS NULL OR TRIM(device_name)='') AND {fallback} IS NOT NULL AND TRIM({fallback})<>''")
            conn.execute("UPDATE staff SET device_name='STAFF-' || id WHERE device_name IS NULL OR TRIM(device_name)=''")
        _seed_authorization_defaults(conn)
        _migrate_staff_roles(conn)
        conn.commit()
    finally:
        if should_close:
            conn.close()


def _seed_authorization_defaults(conn: sqlite3.Connection) -> None:
    roles = [
        ("manager", "Yönetici", 1),
        ("personnel", "Personel", 1),
        ("viewer", "Görüntüleyici", 1),
    ]
    for name, display, is_system in roles:
        conn.execute(
            "INSERT INTO roles(name, display_name, is_system, created_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(name) DO UPDATE SET display_name=excluded.display_name, is_system=excluded.is_system",
            (name, display, is_system),
        )
    for code, display, desc, category in [*DEFAULT_PERMISSIONS, *LEGACY_PERMISSIONS]:
        conn.execute(
            "INSERT INTO permissions(code, display_name, description, category) VALUES(?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET display_name=excluded.display_name, description=excluded.description, category=excluded.category",
            (code, display, desc, category),
        )

    role_ids = {str(r["name"]): int(r["id"]) for r in conn.execute("SELECT id,name FROM roles")}
    canonical_codes = [code for code, *_ in DEFAULT_PERMISSIONS]
    for role_name, allowed in DEFAULT_ROLE_PERMISSIONS.items():
        role_id = role_ids.get(role_name)
        if role_id is None:
            continue
        for code in canonical_codes:
            # Preserve existing admin/user customizations, but initialize missing
            # role_permission rows whenever new permissions are introduced.
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?)",
                (role_id, code, 1 if code in allowed else 0),
            )
        for legacy_code, canonical_code in LEGACY_PERMISSION_ALIASES.items():
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?)",
                (role_id, legacy_code, 1 if canonical_code in allowed else 0),
            )


def _migrate_staff_roles(conn: sqlite3.Connection) -> None:
    role_ids = {str(r["name"]): int(r["id"]) for r in conn.execute("SELECT id,name FROM roles")}
    default_role_id = role_ids.get("personnel")
    manager_role_id = role_ids.get("manager", default_role_id)
    admin_role_id = role_ids.get("admin")
    has_system_admin = conn.execute("SELECT 1 FROM system_admins WHERE COALESCE(is_active,1)=1 LIMIT 1").fetchone() is not None
    staff_columns = _table_columns(conn, "staff")
    role_name_expr = "role_name" if "role_name" in staff_columns else "NULL AS role_name"
    staff_rows = conn.execute(f"SELECT id, role, role_id, {role_name_expr} FROM staff").fetchall()
    single_staff_id = int(staff_rows[0]["id"]) if len(staff_rows) == 1 else None
    for row in staff_rows:
        legacy = str(row["role"] or "personnel").strip()
        legacy_role_name = str(row["role_name"] or "").strip() if "role_name" in row.keys() else ""
        role_id = int(row["role_id"]) if row["role_id"] is not None else None
        is_admin_staff = legacy == "admin" or legacy_role_name == "admin" or (admin_role_id is not None and role_id == int(admin_role_id))
        if is_admin_staff and has_system_admin:
            conn.execute(
                "UPDATE staff SET role_id=?, role=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (manager_role_id, "manager", int(row["id"])),
            )
            continue
        if row["role_id"] is not None:
            continue
        normalized = "manager" if single_staff_id == int(row["id"]) else ("personnel" if legacy in {"staff", "admin"} else legacy)
        conn.execute(
            "UPDATE staff SET role_id=?, role=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (role_ids.get(normalized, default_role_id), normalized, int(row["id"])),
        )



NORMAL_ROLE_NAMES = {"manager", "personnel", "viewer"}


def normalize_invite_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())


def generate_invite_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(7))
    return f"STS-{raw[:4]}-{raw[4:]}"


def _invite_code_hint(invite_code: str) -> str:
    normalized = normalize_invite_code(invite_code)
    return f"****-{normalized[-3:]}" if normalized else "****"


def _role_row(conn: sqlite3.Connection, role_id: int):
    return conn.execute("SELECT id,name,display_name FROM roles WHERE id=?", (int(role_id),)).fetchone()


def _is_normal_role(row) -> bool:
    return bool(row and str(row["name"] or "") in NORMAL_ROLE_NAMES)


def create_staff_invite(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]], role_id: int, expires_at=None, max_uses: int = 1) -> dict[str, Any]:
    if not (actor and bool(actor.get("is_admin"))):
        require_any_permission(actor, db_or_path, "manage_staff", "create_staff")
        require_any_permission(actor, db_or_path, "change_staff_roles", "manage_roles")
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        role = _role_row(conn, int(role_id))
        if not _is_normal_role(role):
            raise ValueError("Yetki kodu yalnızca normal rollere bağlanabilir.")
        code = generate_invite_code()
        max_uses_i = max(1, int(max_uses or 1))
        admin_id = actor.get("admin_id") if actor and actor.get("is_admin") else None
        staff_id = actor.get("id") if actor and not actor.get("is_admin") else None
        conn.execute(
            """
            INSERT INTO staff_invites(
                invite_code_hash, invite_code_hint, role_id, is_active, max_uses, used_count,
                expires_at, created_by_admin_id, created_by_staff_id, created_by_full_name,
                created_by_device_name, created_at, updated_at
            ) VALUES(?, ?, ?, 1, ?, 0, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                hash_password(normalize_invite_code(code)), _invite_code_hint(code), int(role_id), max_uses_i,
                str(expires_at) if expires_at else None, int(admin_id) if admin_id is not None else None,
                int(staff_id) if staff_id is not None else None, str((actor or {}).get("full_name") or ""),
                str((actor or {}).get("device_name") or ""),
            ),
        )
        conn.commit()
        invite_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        row = conn.execute(
            "SELECT si.*, r.name AS role_name, r.display_name AS role_display_name FROM staff_invites si JOIN roles r ON r.id=si.role_id WHERE si.id=?",
            (invite_id,),
        ).fetchone()
        out = dict(row)
        out["invite_code"] = code
        return out
    finally:
        if should_close:
            conn.close()


def list_staff_invites(db_or_path: sqlite3.Connection | str | Path) -> list[dict[str, Any]]:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        rows = conn.execute(
            """
            SELECT si.*, r.name AS role_name, r.display_name AS role_display_name,
                   CASE
                     WHEN COALESCE(si.is_active,1) <> 1 THEN 'Pasif'
                     WHEN COALESCE(si.used_count,0) >= COALESCE(si.max_uses,1) THEN 'Kullanıldı'
                     WHEN si.expires_at IS NOT NULL AND datetime(si.expires_at) <= datetime('now') THEN 'Süresi Doldu'
                     ELSE 'Aktif'
                   END AS status_text
            FROM staff_invites si
            LEFT JOIN roles r ON r.id=si.role_id
            ORDER BY si.created_at DESC, si.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if should_close:
            conn.close()


def validate_staff_invite(db_or_path: sqlite3.Connection | str | Path, invite_code: str) -> dict[str, Any] | None:
    ensure_authorization_schema(db_or_path)
    normalized = normalize_invite_code(invite_code)
    if not normalized:
        return None
    conn, should_close = _connection_from(db_or_path)
    try:
        rows = conn.execute(
            """
            SELECT si.*, r.name AS role_name, r.display_name AS role_display_name
            FROM staff_invites si
            JOIN roles r ON r.id=si.role_id
            WHERE COALESCE(si.is_active,1)=1
              AND COALESCE(si.used_count,0) < COALESCE(si.max_uses,1)
              AND (si.expires_at IS NULL OR datetime(si.expires_at) > datetime('now'))
            ORDER BY si.created_at DESC, si.id DESC
            """
        ).fetchall()
        for row in rows:
            if str(row["role_name"] or "") not in NORMAL_ROLE_NAMES:
                continue
            if verify_password(normalized, str(row["invite_code_hash"] or "")):
                return dict(row)
        return None
    finally:
        if should_close:
            conn.close()


def consume_staff_invite_and_create_staff(db_or_path: sqlite3.Connection | str | Path, device_name: str, full_name: str, password: str, invite_code: str) -> dict[str, Any]:
    ensure_authorization_schema(db_or_path)
    invite = validate_staff_invite(db_or_path, invite_code)
    if not invite:
        # TODO: staff_invite_failed olayı mevcut log altyapısına güvenli bağlanınca yazılacak.
        raise ValueError("Yetki kodu geçersiz, pasif, kullanılmış veya süresi dolmuş.")
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute("SELECT * FROM staff_invites WHERE id=?", (int(invite["id"]),)).fetchone()
        if not row or int(row["is_active"] if row["is_active"] is not None else 1) != 1 or int(row["used_count"] or 0) >= int(row["max_uses"] or 1):
            raise ValueError("Yetki kodu artık geçerli değil.")
        if row["expires_at"] is not None and conn.execute("SELECT datetime(?) <= datetime('now')", (row["expires_at"],)).fetchone()[0]:
            raise ValueError("Yetki kodunun süresi dolmuş.")
        role = _role_row(conn, int(row["role_id"]))
        if not _is_normal_role(role):
            raise ValueError("Yetki kodu geçerli bir role bağlı değil.")
        conn.execute(
            """
            INSERT INTO staff(device_name, full_name, password_hash, role, role_id, is_active, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(device_name or ""), str(full_name or "").strip(), hash_password(password), str(role["name"]), int(role["id"])),
        )
        staff_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            UPDATE staff_invites
            SET used_count=COALESCE(used_count,0)+1, used_at=CURRENT_TIMESTAMP,
                used_by_staff_id=?, used_by_full_name=?, used_by_device_name=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (staff_id, str(full_name or "").strip(), str(device_name or ""), int(row["id"])),
        )
        conn.commit()
        # TODO: staff_invite_used olayı mevcut log altyapısına güvenli bağlanınca yazılacak.
        staff_row = conn.execute(_staff_select_sql("WHERE s.id=?"), (staff_id,)).fetchone()
        return build_current_staff(staff_row)
    except sqlite3.IntegrityError as exc:
        raise ValueError("Bu cihaz için personel kaydı zaten mevcut.") from exc
    finally:
        if should_close:
            conn.close()


def get_device_name() -> str:
    return socket.gethostname()


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    ).hex()
    return f"{salt}:{digest}"


def verify_password(password: str, stored_password_hash: str) -> bool:
    stored = str(stored_password_hash or "")
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    if not salt or not expected:
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            bytes.fromhex(salt),
            120_000,
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(digest, expected)


def _staff_select_sql(where: str = "") -> str:
    return f"""
        SELECT s.id, s.device_name, s.full_name, s.password_hash, s.role, s.role_id,
               s.is_active, s.last_login_at, s.created_at, s.updated_at,
               r.name AS role_name, r.display_name AS role_display_name
        FROM staff s
        LEFT JOIN roles r ON r.id=s.role_id
        {where}
    """


def get_staff_by_device(db_or_path: sqlite3.Connection | str | Path, device_name: str):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return conn.execute(_staff_select_sql("WHERE s.device_name=?"), (str(device_name or ""),)).fetchone()
    finally:
        if should_close:
            conn.close()


def _default_role_for_new_staff(conn: sqlite3.Connection) -> int:
    has_staff = int(conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0] or 0) > 0
    role_name = "personnel" if has_staff else "manager"
    row = conn.execute("SELECT id FROM roles WHERE name=?", (role_name,)).fetchone()
    return int(row["id"])


def create_staff(db_or_path: sqlite3.Connection | str | Path, device_name: str, full_name: str, password: str, role_id: int | None = None):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        rid = int(role_id) if role_id is not None else _default_role_for_new_staff(conn)
        role = conn.execute("SELECT name FROM roles WHERE id=?", (rid,)).fetchone()
        if not role:
            raise ValueError("Geçersiz rol")
        conn.execute(
            """
            INSERT INTO staff(device_name, full_name, password_hash, role, role_id, is_active, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (str(device_name or ""), str(full_name or "").strip(), hash_password(password), str(role["name"]), rid),
        )
        conn.commit()
        return conn.execute(_staff_select_sql("WHERE s.device_name=?"), (str(device_name or ""),)).fetchone()
    finally:
        if should_close:
            conn.close()


def build_current_staff(row) -> dict[str, Any]:
    # staff.role TEXT is a migration remnant kept only as a display fallback;
    # authorization decisions must use role_id/role_permissions instead.
    role_name = str(row["role_name"] if "role_name" in row.keys() and row["role_name"] else row["role"] or "personnel")
    return {
        "id": int(row["id"]),
        "device_name": str(row["device_name"] or ""),
        "full_name": str(row["full_name"] or ""),
        "username": str(row["device_name"] or ""),
        "role": role_name,
        "role_name": role_name,
        "role_id": int(row["role_id"]) if row["role_id"] is not None else None,
        "role_display_name": str(row["role_display_name"] if "role_display_name" in row.keys() and row["role_display_name"] else ROLE_LABELS.get(role_name, role_name)),
        "is_active": int(row["is_active"] if row["is_active"] is not None else 1),
    }


def has_active_system_admin(db_or_path: sqlite3.Connection | str | Path) -> bool:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute("SELECT 1 FROM system_admins WHERE COALESCE(is_active,1)=1 LIMIT 1").fetchone()
        return row is not None
    finally:
        if should_close:
            conn.close()


def create_system_admin(db_or_path: sqlite3.Connection | str | Path, admin_name: str, password: str):
    ensure_authorization_schema(db_or_path)
    name = str(admin_name or "").strip()
    if not name:
        raise ValueError("Admin adı boş bırakılamaz.")
    if not password:
        raise ValueError("Admin şifresi boş bırakılamaz.")
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO system_admins(admin_name, password_hash, is_active, created_at, updated_at)
            VALUES(?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (name, hash_password(password)),
        )
        conn.commit()
        return conn.execute("SELECT * FROM system_admins WHERE admin_name=?", (name,)).fetchone()
    finally:
        if should_close:
            conn.close()


def verify_system_admin_login(db_or_path: sqlite3.Connection | str | Path, admin_name: str, password: str) -> dict[str, Any] | None:
    ensure_authorization_schema(db_or_path)
    name = str(admin_name or "").strip()
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute(
            "SELECT * FROM system_admins WHERE admin_name=? AND COALESCE(is_active,1)=1",
            (name,),
        ).fetchone()
        if not row or not verify_password(password, str(row["password_hash"] or "")):
            # TODO: Bağlantı noktası netleştirilince başarısız sistem yöneticisi giriş denemeleri mevcut log altyapısına yazılacak.
            return None
        conn.execute("UPDATE system_admins SET last_login_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(row["id"]),))
        conn.commit()
        row = conn.execute("SELECT * FROM system_admins WHERE id=?", (int(row["id"]),)).fetchone()
        # TODO: Bağlantı noktası netleştirilince başarılı sistem yöneticisi girişleri mevcut log altyapısına yazılacak.
        return dict(row) if row else None
    finally:
        if should_close:
            conn.close()


def build_system_admin_session(row, device_name: str) -> dict[str, Any]:
    admin_id = int(row["id"] if hasattr(row, "keys") else row.get("id"))
    admin_name = str(row["admin_name"] if hasattr(row, "keys") else row.get("admin_name") or "")
    is_active = row["is_active"] if hasattr(row, "keys") else row.get("is_active")
    return {
        "id": 0,
        "admin_id": admin_id,
        "full_name": admin_name,
        "device_name": str(device_name or ""),
        "is_admin": True,
        "role_display_name": "Sistem Yöneticisi",
        "is_active": int(is_active if is_active is not None else 1),
    }


def has_role(role: str, staff: Optional[dict[str, Any]] = None) -> bool:
    raise RuntimeError("Sabit rol kontrolü kullanılmamalı; has_permission(current_user, permission_code) kullanın.")


def _staff_permission_rows(conn: sqlite3.Connection, staff_id: int):
    return conn.execute(
        """
        SELECT p.code, COALESCE(rp.is_allowed, 0) AS is_allowed
        FROM permissions p
        JOIN staff s ON s.id=?
        LEFT JOIN role_permissions rp ON rp.role_id=s.role_id AND rp.permission_code=p.code
        WHERE COALESCE(s.is_active, 1)=1
        """,
        (int(staff_id),),
    ).fetchall()


def has_permission(current_user: Optional[dict[str, Any]], permission_code: str, db_or_path: sqlite3.Connection | str | Path | None = None) -> bool:
    user = current_user if current_user is not None else current_staff
    code = str(permission_code or "").strip()
    if not code:
        return False
    if user and bool(user.get("is_admin")) and int(user.get("is_active") if user.get("is_active") is not None else 1) != 0:
        return True
    if not PERMISSION_RESTRICTIONS_ENABLED:
        return True
    if not user or int(user.get("is_active") if user.get("is_active") is not None else 1) == 0:
        return False
    canonical_code = LEGACY_PERMISSION_ALIASES.get(code, code)
    alias_codes = {legacy for legacy, canonical in LEGACY_PERMISSION_ALIASES.items() if canonical == canonical_code}
    if db_or_path is None:
        db_or_path = user.get("db_path") or user.get("_db_path")
    if db_or_path is None:
        user_permissions = set(user.get("permissions") or [])
        return canonical_code in user_permissions or bool(alias_codes & user_permissions)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute(
            """
            SELECT COALESCE(rp.is_allowed, 0) AS is_allowed
            FROM staff s
            LEFT JOIN role_permissions rp ON rp.role_id=s.role_id AND rp.permission_code=?
            WHERE s.id=? AND COALESCE(s.is_active, 1)=1 AND s.role_id IS NOT NULL
            """,
            (canonical_code, int(user.get("id"))),
        ).fetchone()
        if row and int(row["is_allowed"] or 0) == 1:
            return True
        for alias_code in alias_codes:
            row = conn.execute(
                """
                SELECT COALESCE(rp.is_allowed, 0) AS is_allowed
                FROM staff s
                LEFT JOIN role_permissions rp ON rp.role_id=s.role_id AND rp.permission_code=?
                WHERE s.id=? AND COALESCE(s.is_active, 1)=1 AND s.role_id IS NOT NULL
                """,
                (alias_code, int(user.get("id"))),
            ).fetchone()
            if row and int(row["is_allowed"] or 0) == 1:
                return True
        return False
    finally:
        if should_close:
            conn.close()


def staff_has_permission(permission: str, staff: Optional[dict[str, Any]] = None, db_or_path: sqlite3.Connection | str | Path | None = None) -> bool:
    return has_permission(staff if staff is not None else current_staff, permission, db_or_path)


def enrich_staff_permissions(db_or_path: sqlite3.Connection | str | Path, staff: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not staff:
        return staff
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        permissions = {str(r["code"]) for r in _staff_permission_rows(conn, int(staff["id"])) if int(r["is_allowed"] or 0) == 1}
        out = dict(staff)
        out["permissions"] = permissions
        path = _database_path_from_connection(conn)
        if path:
            out["db_path"] = path
        return out
    finally:
        if should_close:
            conn.close()


def require_permission(current_user: Optional[dict[str, Any]], permission_code: str, db_or_path: sqlite3.Connection | str | Path | None = None) -> None:
    if not has_permission(current_user, permission_code, db_or_path):
        raise PermissionError(f"Bu işlem için '{permission_code}' yetkisi gerekli.")


def list_roles(db_or_path: sqlite3.Connection | str | Path) -> list[dict[str, Any]]:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id,name,display_name,is_system,created_at,updated_at FROM roles WHERE name <> 'admin' ORDER BY id"
            ).fetchall()
        ]
    finally:
        if should_close:
            conn.close()


def list_permissions(db_or_path: sqlite3.Connection | str | Path) -> list[dict[str, Any]]:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return [dict(r) for r in conn.execute("SELECT id,code,display_name,description,category FROM permissions ORDER BY category, id").fetchall()]
    finally:
        if should_close:
            conn.close()


def get_role_permission_map(db_or_path: sqlite3.Connection | str | Path) -> dict[int, dict[str, bool]]:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        out: dict[int, dict[str, bool]] = {}
        for r in conn.execute("SELECT role_id, permission_code, is_allowed FROM role_permissions").fetchall():
            out.setdefault(int(r["role_id"]), {})[str(r["permission_code"])] = bool(int(r["is_allowed"] or 0))
        return out
    finally:
        if should_close:
            conn.close()


def list_staff(db_or_path: sqlite3.Connection | str | Path) -> list[dict[str, Any]]:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return [dict(r) for r in conn.execute(_staff_select_sql("ORDER BY s.full_name COLLATE NOCASE, s.id")).fetchall()]
    finally:
        if should_close:
            conn.close()


def _role_has_full_access(conn: sqlite3.Connection, role_id: int) -> bool:
    rows = conn.execute("SELECT permission_code, is_allowed FROM role_permissions WHERE role_id=?", (int(role_id),)).fetchall()
    allowed = {str(r["permission_code"]) for r in rows if int(r["is_allowed"] or 0) == 1}
    return AUTHORIZATION_REQUIRED_PERMISSIONS.issubset(allowed)


def count_full_access_users(db_or_path: sqlite3.Connection | str | Path, excluding_staff_id: int | None = None) -> int:
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        if conn.execute("SELECT 1 FROM system_admins WHERE COALESCE(is_active,1)=1 LIMIT 1").fetchone() is not None:
            return 1
        count = 0
        for row in conn.execute("SELECT id, role_id FROM staff WHERE COALESCE(is_active,1)=1 AND role_id IS NOT NULL").fetchall():
            if excluding_staff_id is not None and int(row["id"]) == int(excluding_staff_id):
                continue
            if _role_has_full_access(conn, int(row["role_id"])):
                count += 1
        return count
    finally:
        if should_close:
            conn.close()


def _would_keep_full_access_user(conn: sqlite3.Connection, changed_staff_id: int | None = None, changed_role_id: int | None = None, changed_role_permissions: dict[str, bool] | None = None, changed_active: int | None = None) -> bool:
    if conn.execute("SELECT 1 FROM system_admins WHERE COALESCE(is_active,1)=1 LIMIT 1").fetchone() is not None:
        return True
    for row in conn.execute("SELECT id, role_id, is_active FROM staff").fetchall():
        sid = int(row["id"])
        active = int(row["is_active"] if row["is_active"] is not None else 1)
        role_id = int(row["role_id"]) if row["role_id"] is not None else None
        if changed_staff_id is not None and sid == int(changed_staff_id):
            if changed_active is not None:
                active = int(changed_active)
            if changed_role_id is not None:
                role_id = int(changed_role_id)
        if active != 1 or role_id is None:
            continue
        if changed_role_id is not None and role_id == int(changed_role_id) and changed_role_permissions is not None:
            if AUTHORIZATION_REQUIRED_PERMISSIONS.issubset({c for c, ok in changed_role_permissions.items() if ok}):
                return True
        elif _role_has_full_access(conn, role_id):
            return True
    return False


def _has_any_permission(actor: Optional[dict[str, Any]], db_or_path: sqlite3.Connection | str | Path | None, *permission_codes: str) -> bool:
    return any(has_permission(actor, code, db_or_path) for code in permission_codes)


def has_any_permission(actor: Optional[dict[str, Any]], db_or_path: sqlite3.Connection | str | Path | None, *permission_codes: str) -> bool:
    return _has_any_permission(actor, db_or_path, *permission_codes)


def require_any_permission(actor: Optional[dict[str, Any]], db_or_path: sqlite3.Connection | str | Path | None, *permission_codes: str) -> None:
    if not _has_any_permission(actor, db_or_path, *permission_codes):
        joined = " / ".join(permission_codes)
        raise PermissionError(f"Bu işlem için '{joined}' yetkilerinden biri gerekli.")


def update_staff_record(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]], staff_id: int, *, full_name: str | None = None, device_name: str | None = None, role_id: int | None = None, is_active: int | None = None) -> None:
    if full_name is not None or device_name is not None:
        require_any_permission(actor, db_or_path, "edit_staff", "manage_staff")
    if role_id is not None:
        require_any_permission(actor, db_or_path, "change_staff_roles", "manage_roles")
    if is_active is not None:
        require_permission(actor, "manage_staff", db_or_path)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        if is_active is not None and int(is_active) == 0 and not _would_keep_full_access_user(conn, changed_staff_id=int(staff_id), changed_active=0):
            raise ValueError("Bu işlem yapılamaz. Sistemde en az bir yetkili kullanıcı kalmalıdır.")
        assignments = []
        params: list[Any] = []
        if full_name is not None:
            assignments.append("full_name=?")
            params.append(str(full_name or "").strip())
        if device_name is not None:
            assignments.append("device_name=?")
            params.append(str(device_name or "").strip())
        if role_id is not None:
            role = conn.execute("SELECT name FROM roles WHERE id=?", (int(role_id),)).fetchone()
            if not role:
                raise ValueError("Geçersiz rol")
            if not _would_keep_full_access_user(conn, changed_staff_id=int(staff_id), changed_role_id=int(role_id)):
                raise ValueError("Bu işlem yapılamaz. Sistemde en az bir yetkili kullanıcı kalmalıdır.")
            assignments.extend(["role_id=?", "role=?"])
            params.extend([int(role_id), str(role["name"])])
        if is_active is not None:
            assignments.append("is_active=?")
            params.append(1 if int(is_active) else 0)
        if not assignments:
            return
        assignments.append("updated_at=CURRENT_TIMESTAMP")
        params.append(int(staff_id))
        conn.execute(f"UPDATE staff SET {', '.join(assignments)} WHERE id=?", params)
        conn.commit()
    finally:
        if should_close:
            conn.close()


def create_staff_by_admin(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]], device_name: str, full_name: str, password: str, role_id: int, is_active: int = 1) -> None:
    require_any_permission(actor, db_or_path, "create_staff", "manage_staff")
    if role_id is not None:
        require_any_permission(actor, db_or_path, "change_staff_roles", "manage_roles")
    row = create_staff(db_or_path, device_name, full_name, password, int(role_id))
    if int(is_active) != 1:
        update_staff_record(db_or_path, actor, int(row["id"]), is_active=int(is_active))


def reset_staff_password(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]], staff_id: int, new_password: str) -> None:
    require_permission(actor, "reset_staff_passwords", db_or_path)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute("UPDATE staff SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (hash_password(new_password), int(staff_id)))
        conn.commit()
    finally:
        if should_close:
            conn.close()


def set_role_permission(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]], role_id: int, permission_code: str, is_allowed: bool) -> None:
    require_permission(actor, "manage_roles", db_or_path)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        permissions = {str(r["permission_code"]): bool(int(r["is_allowed"] or 0)) for r in conn.execute("SELECT permission_code,is_allowed FROM role_permissions WHERE role_id=?", (int(role_id),)).fetchall()}
        permissions[str(permission_code)] = bool(is_allowed)
        if not _would_keep_full_access_user(conn, changed_role_id=int(role_id), changed_role_permissions=permissions):
            raise ValueError("Bu işlem yapılamaz. Sistemde en az bir yetkili kullanıcı kalmalıdır.")
        conn.execute(
            "INSERT INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?) "
            "ON CONFLICT(role_id, permission_code) DO UPDATE SET is_allowed=excluded.is_allowed",
            (int(role_id), str(permission_code), 1 if is_allowed else 0),
        )
        conn.execute("UPDATE roles SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(role_id),))
        conn.commit()
    finally:
        if should_close:
            conn.close()



def set_role_permissions_bulk(
    db_or_path: sqlite3.Connection | str | Path,
    actor: Optional[dict[str, Any]],
    role_permission_map: dict[int, dict[str, bool]],
) -> None:
    require_permission(actor, "manage_roles", db_or_path)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        normalized = {int(role_id): {str(code): bool(allowed) for code, allowed in permissions.items()} for role_id, permissions in role_permission_map.items()}
        for role_id, permissions in normalized.items():
            existing = {str(r["permission_code"]): bool(int(r["is_allowed"] or 0)) for r in conn.execute("SELECT permission_code,is_allowed FROM role_permissions WHERE role_id=?", (role_id,)).fetchall()}
            existing.update(permissions)
            if not _would_keep_full_access_user(conn, changed_role_id=role_id, changed_role_permissions=existing):
                raise ValueError("Bu işlem yapılamaz. Sistemde en az bir yetkili kullanıcı kalmalıdır.")
        for role_id, permissions in normalized.items():
            for code, is_allowed in permissions.items():
                conn.execute(
                    "INSERT INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?) "
                    "ON CONFLICT(role_id, permission_code) DO UPDATE SET is_allowed=excluded.is_allowed",
                    (role_id, code, 1 if is_allowed else 0),
                )
            conn.execute("UPDATE roles SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (role_id,))
        conn.commit()
    finally:
        if should_close:
            conn.close()


def reset_role_permissions_to_defaults(db_or_path: sqlite3.Connection | str | Path, actor: Optional[dict[str, Any]]) -> None:
    require_permission(actor, "manage_roles", db_or_path)
    ensure_authorization_schema(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        role_ids = {str(r["name"]): int(r["id"]) for r in conn.execute("SELECT id,name FROM roles")}
        codes = [code for code, *_ in DEFAULT_PERMISSIONS]
        role_permission_map = {
            role_ids[role_name]: {code: code in allowed for code in codes}
            for role_name, allowed in DEFAULT_ROLE_PERMISSIONS.items()
            if role_name in role_ids
        }
        for role_id, permissions in role_permission_map.items():
            if not _would_keep_full_access_user(conn, changed_role_id=role_id, changed_role_permissions=permissions):
                raise ValueError("Bu işlem yapılamaz. Sistemde en az bir yetkili kullanıcı kalmalıdır.")
        for role_id, permissions in role_permission_map.items():
            for code, is_allowed in permissions.items():
                conn.execute(
                    "INSERT INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?) "
                    "ON CONFLICT(role_id, permission_code) DO UPDATE SET is_allowed=excluded.is_allowed",
                    (role_id, code, 1 if is_allowed else 0),
                )
            for legacy_code, canonical_code in LEGACY_PERMISSION_ALIASES.items():
                conn.execute(
                    "INSERT INTO role_permissions(role_id, permission_code, is_allowed) VALUES(?,?,?) "
                    "ON CONFLICT(role_id, permission_code) DO UPDATE SET is_allowed=excluded.is_allowed",
                    (role_id, legacy_code, 1 if permissions.get(canonical_code) else 0),
                )
            conn.execute("UPDATE roles SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (role_id,))
        conn.commit()
    finally:
        if should_close:
            conn.close()



def _build_system_admin_setup_dialog(db_or_path: sqlite3.Connection | str | Path, parent=None):
    from src.ui.message_boxes import show_warning
    from PySide6.QtWidgets import QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
    from src.ui.theme import STYLE

    class SystemAdminSetupDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Sistem Yöneticisi Kurulumu")
            self.setModal(True)
            self.setStyleSheet(STYLE)
            self.setFixedWidth(460)
            root = QVBoxLayout(self)
            root.setContentsMargins(22, 22, 22, 22)
            root.setSpacing(14)
            heading = QLabel("Sistem Yöneticisi Kurulumu")
            heading.setObjectName("mainTitle")
            root.addWidget(heading)
            card = QFrame(); card.setObjectName("card")
            lay = QVBoxLayout(card); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(12)
            root.addWidget(card)
            info = QLabel("Bu STS dosyası için cihazdan bağımsız ilk sistem yöneticisi hesabını oluşturun.")
            info.setWordWrap(True); info.setObjectName("muted")
            lay.addWidget(info)
            form = QFormLayout()
            self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Admin Adı")
            self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password)
            self.repeat_edit = QLineEdit(); self.repeat_edit.setEchoMode(QLineEdit.Password)
            form.addRow("Admin Adı", self.name_edit)
            form.addRow("Admin Şifresi", self.password_edit)
            form.addRow("Şifre Tekrar", self.repeat_edit)
            lay.addLayout(form)
            row = QHBoxLayout(); row.addStretch()
            cancel = QPushButton("Vazgeç"); cancel.clicked.connect(self.reject)
            primary = QPushButton("Kurulumu Tamamla"); primary.setDefault(True); primary.clicked.connect(self._submit)
            row.addWidget(cancel); row.addWidget(primary); lay.addLayout(row)
            self.name_edit.returnPressed.connect(self._submit)
            self.password_edit.returnPressed.connect(self._submit)
            self.repeat_edit.returnPressed.connect(self._submit)

        def _submit(self):
            name = self.name_edit.text().strip()
            password = self.password_edit.text()
            repeat = self.repeat_edit.text()
            if not name or not password or not repeat:
                show_warning(self, "Eksik bilgi", "Admin adı ve şifre alanları boş bırakılamaz.")
                return
            if password != repeat:
                show_warning(self, "Şifreler eşleşmiyor", "Girdiğiniz şifreler eşleşmiyor. Lütfen tekrar deneyin.")
                self.repeat_edit.setFocus(); self.repeat_edit.selectAll()
                return
            try:
                create_system_admin(db_or_path, name, password)
            except sqlite3.IntegrityError:
                show_warning(self, "Kayıt mevcut", "Bu admin adı zaten kullanılıyor.")
                return
            except Exception as exc:
                show_warning(self, "Kurulum başarısız", str(exc))
                return
            self.accept()

    return SystemAdminSetupDialog()


def ensure_system_admin_setup(db_or_path: sqlite3.Connection | str | Path, parent=None) -> bool:
    from PySide6.QtWidgets import QDialog
    ensure_authorization_schema(db_or_path)
    if has_active_system_admin(db_or_path):
        return True
    dlg = _build_system_admin_setup_dialog(db_or_path, parent)
    return dlg.exec() == QDialog.Accepted and has_active_system_admin(db_or_path)


def show_system_admin_login_dialog(db_or_path: sqlite3.Connection | str | Path, parent=None) -> Optional[dict[str, Any]]:
    from src.ui.message_boxes import show_warning
    from PySide6.QtWidgets import QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
    from src.ui.theme import STYLE

    class SystemAdminLoginDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Sistem Yöneticisi Girişi")
            self.setModal(True)
            self.setStyleSheet(STYLE)
            self.setFixedWidth(440)
            self.staff: Optional[dict[str, Any]] = None
            root = QVBoxLayout(self); root.setContentsMargins(22, 22, 22, 22); root.setSpacing(14)
            heading = QLabel("Sistem Yöneticisi Girişi"); heading.setObjectName("mainTitle"); root.addWidget(heading)
            card = QFrame(); card.setObjectName("card"); lay = QVBoxLayout(card); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(12); root.addWidget(card)
            form = QFormLayout()
            self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Admin Adı")
            self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password); self.password_edit.setPlaceholderText("Admin Şifresi")
            form.addRow("Admin Adı", self.name_edit); form.addRow("Admin Şifresi", self.password_edit); lay.addLayout(form)
            row = QHBoxLayout(); row.addStretch()
            cancel = QPushButton("Vazgeç"); cancel.clicked.connect(self.reject)
            primary = QPushButton("Giriş Yap"); primary.setDefault(True); primary.clicked.connect(self._submit)
            row.addWidget(cancel); row.addWidget(primary); lay.addLayout(row)
            self.name_edit.returnPressed.connect(self._submit); self.password_edit.returnPressed.connect(self._submit)

        def _submit(self):
            name = self.name_edit.text().strip(); password = self.password_edit.text()
            if not name or not password:
                show_warning(self, "Eksik bilgi", "Admin adı ve şifre boş bırakılamaz.")
                return
            row = verify_system_admin_login(db_or_path, name, password)
            if not row:
                show_warning(self, "Giriş başarısız", "Admin adı veya şifre hatalı.")
                self.password_edit.setFocus(); self.password_edit.selectAll()
                return
            self.staff = build_system_admin_session(row, get_device_name())
            self.accept()

    dlg = SystemAdminLoginDialog()
    return dlg.staff if dlg.exec() == QDialog.Accepted else None

def _build_staff_register_dialog(db_or_path: sqlite3.Connection | str | Path, device_name: str, parent=None):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence, QShortcut
    from src.ui.message_boxes import show_warning
    from PySide6.QtWidgets import (
        QDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
    )

    from src.ui.theme import STYLE

    class StaffRegisterDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Personel Kaydı")
            self.setModal(True)
            self.setStyleSheet(STYLE)
            self.setFixedWidth(440)
            self.staff: Optional[dict[str, Any]] = None
            root = QVBoxLayout(self)
            root.setContentsMargins(22, 22, 22, 22)
            root.setSpacing(14)
            heading = QLabel("Personel Kaydı")
            heading.setObjectName("mainTitle")
            root.addWidget(heading)
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            card_layout.setSpacing(12)
            root.addWidget(card)
            info = QLabel("Bu cihaz adı otomatik algılandı.")
            info.setObjectName("muted")
            card_layout.addWidget(info)
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignLeft)
            self.device_edit = QLineEdit(str(device_name or ""))
            self.device_edit.setReadOnly(True)
            self.full_name_edit = QLineEdit()
            self.full_name_edit.setPlaceholderText("Personel Adı Soyadı")
            self.password_edit = QLineEdit()
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.password_repeat_edit = QLineEdit()
            self.password_repeat_edit.setEchoMode(QLineEdit.Password)
            self.invite_code_edit = QLineEdit()
            self.invite_code_edit.setPlaceholderText("STS-7K4P-92D")
            form.addRow("Cihaz Adı", self.device_edit)
            form.addRow("Personel Adı Soyadı", self.full_name_edit)
            form.addRow("Şifre Belirle", self.password_edit)
            form.addRow("Şifre Tekrar", self.password_repeat_edit)
            form.addRow("Yetki Kodu", self.invite_code_edit)
            card_layout.addLayout(form)
            row = QHBoxLayout()
            row.addStretch()
            cancel = QPushButton("Vazgeç")
            cancel.clicked.connect(self.reject)
            primary = QPushButton("Kaydı Tamamla")
            primary.setDefault(True)
            primary.clicked.connect(self._submit)
            row.addWidget(cancel)
            row.addWidget(primary)
            card_layout.addLayout(row)
            self.full_name_edit.returnPressed.connect(self._submit)
            self.password_edit.returnPressed.connect(self._submit)
            self.password_repeat_edit.returnPressed.connect(self._submit)
            self.invite_code_edit.returnPressed.connect(self._submit)
            QShortcut(QKeySequence("Ctrl+Alt+Shift+A"), self).activated.connect(self._admin_login)

        def _admin_login(self):
            self.staff = show_system_admin_login_dialog(db_or_path, self)
            if self.staff:
                self.accept()

        def _submit(self):
            full_name = self.full_name_edit.text().strip()
            password = self.password_edit.text()
            password_repeat = self.password_repeat_edit.text()
            if not full_name:
                show_warning(self, "Eksik bilgi", "Personel Adı Soyadı boş bırakılamaz.")
                self.full_name_edit.setFocus()
                return
            if not password:
                show_warning(self, "Eksik bilgi", "Şifre boş bırakılamaz.")
                self.password_edit.setFocus()
                return
            if password != password_repeat:
                show_warning(self, "Şifreler eşleşmiyor", "Girdiğiniz şifreler eşleşmiyor. Lütfen tekrar deneyin.")
                self.password_repeat_edit.setFocus()
                self.password_repeat_edit.selectAll()
                return
            invite_code = self.invite_code_edit.text().strip()
            if not invite_code:
                show_warning(self, "Eksik bilgi", "Yetki Kodu boş bırakılamaz.")
                self.invite_code_edit.setFocus()
                return
            try:
                self.staff = enrich_staff_permissions(
                    db_or_path,
                    consume_staff_invite_and_create_staff(db_or_path, str(device_name or ""), full_name, password, invite_code),
                )
            except Exception as exc:
                show_warning(self, "Kayıt başarısız", str(exc))
                self.invite_code_edit.setFocus()
                self.invite_code_edit.selectAll()
                return
            self.accept()

    return StaffRegisterDialog()


def _build_staff_login_dialog(db_or_path: sqlite3.Connection | str | Path, row, parent=None):
    from src.ui.message_boxes import show_warning
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
    )

    from src.ui.theme import STYLE

    class StaffLoginDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Personel Girişi")
            self.setModal(True)
            self.setStyleSheet(STYLE)
            self.setFixedWidth(440)
            self.staff: Optional[dict[str, Any]] = None
            root = QVBoxLayout(self)
            root.setContentsMargins(22, 22, 22, 22)
            root.setSpacing(14)
            heading = QLabel("Personel Girişi")
            heading.setObjectName("mainTitle")
            root.addWidget(heading)
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 18, 18, 18)
            card_layout.setSpacing(12)
            root.addWidget(card)
            hello = QLabel(f"Merhaba {str(row['full_name'] or '')}")
            hello.setObjectName("sectionTitle")
            card_layout.addWidget(hello)
            form = QFormLayout()
            self.device_edit = QLineEdit(str(row["device_name"] or ""))
            self.device_edit.setReadOnly(True)
            self.password_edit = QLineEdit()
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.password_edit.setPlaceholderText("Personel Şifresi")
            form.addRow("Cihaz Adı", self.device_edit)
            form.addRow("Personel Şifresi", self.password_edit)
            card_layout.addLayout(form)
            row_layout = QHBoxLayout()
            row_layout.addStretch()
            cancel = QPushButton("Vazgeç")
            cancel.clicked.connect(self.reject)
            primary = QPushButton("Giriş Yap")
            primary.setDefault(True)
            primary.clicked.connect(self._submit)
            row_layout.addWidget(cancel)
            row_layout.addWidget(primary)
            card_layout.addLayout(row_layout)
            self.password_edit.returnPressed.connect(self._submit)
            QShortcut(QKeySequence("Ctrl+Alt+Shift+A"), self).activated.connect(self._admin_login)

        def _admin_login(self):
            self.staff = show_system_admin_login_dialog(db_or_path, self)
            if self.staff:
                self.accept()

        def _submit(self):
            if int(row["is_active"] if row["is_active"] is not None else 1) == 0:
                show_warning(self, "Personel pasif", "Bu kullanıcı pasif durumdadır. Sistem yöneticinizle iletişime geçin.")
                return
            password = self.password_edit.text()
            if not password:
                show_warning(self, "Eksik bilgi", "Personel Şifresi boş bırakılamaz.")
                self.password_edit.setFocus()
                return
            if not verify_password(password, str(row["password_hash"] or "")):
                show_warning(self, "Giriş başarısız", "Personel şifresi hatalı. Lütfen tekrar deneyin.")
                self.password_edit.setFocus()
                self.password_edit.selectAll()
                return
            self.staff = enrich_staff_permissions(db_or_path, build_current_staff(row))
            self.accept()

    return StaffLoginDialog()


def show_staff_register_dialog(db_or_path: sqlite3.Connection | str | Path, device_name: str, parent=None) -> Optional[dict[str, Any]]:
    from PySide6.QtWidgets import QDialog

    dlg = _build_staff_register_dialog(db_or_path, device_name, parent)
    return dlg.staff if dlg.exec() == QDialog.Accepted else None


def show_staff_login_dialog(db_or_path: sqlite3.Connection | str | Path, row, parent=None) -> Optional[dict[str, Any]]:
    from PySide6.QtWidgets import QDialog

    dlg = _build_staff_login_dialog(db_or_path, row, parent)
    return dlg.staff if dlg.exec() == QDialog.Accepted else None


def _show_staff_inactive_message(parent=None) -> None:
    try:
        from src.ui.message_boxes import show_warning

        show_warning(parent, "Personel pasif", "Bu kullanıcı pasif durumdadır. Sistem yöneticinizle iletişime geçin.")
    except Exception:
        pass


def require_staff_login(db_or_path: sqlite3.Connection | str | Path, parent=None) -> Optional[dict[str, Any]]:
    global current_staff
    ensure_staff_table(db_or_path)
    device_name = get_device_name()
    row = get_staff_by_device(db_or_path, device_name)
    if row:
        if int(row["is_active"] if row["is_active"] is not None else 1) == 0:
            current_staff = None
            _show_staff_inactive_message(parent)
            return None
        # device_name STS içinde tekildir; kayıtlı ve aktif cihazlar için tekrar
        # şifre sormadan personel oturumunu aç. Şifre yine kilitli belgeleri
        # farklı cihazdan açmak için staff.password_hash üzerinde kullanılmaya devam eder.
        conn, should_close = _connection_from(db_or_path)
        try:
            conn.execute("UPDATE staff SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (int(row["id"]),))
            conn.commit()
        finally:
            if should_close:
                conn.close()
        staff = enrich_staff_permissions(db_or_path, build_current_staff(row))
    else:
        staff = show_staff_register_dialog(db_or_path, device_name, parent)
        staff = enrich_staff_permissions(db_or_path, staff)
    current_staff = staff
    return staff


def ensure_document_locks_table(db_or_path: sqlite3.Connection | str | Path) -> None:
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL UNIQUE,
                is_locked INTEGER NOT NULL DEFAULT 0,
                locked_by_staff_id INTEGER,
                locked_by_device_name TEXT,
                locked_by_full_name TEXT,
                locked_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                FOREIGN KEY(locked_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL
            )
            """
        )
        columns = _table_columns(conn, "document_locks")
        for name, ddl in (
            ("is_locked", "INTEGER NOT NULL DEFAULT 0"),
            ("locked_by_staff_id", "INTEGER"),
            ("locked_by_device_name", "TEXT"),
            ("locked_by_full_name", "TEXT"),
            ("locked_at", "TEXT"),
            ("updated_at", "TEXT"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE document_locks ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_document_lock_state(
    db_or_path: sqlite3.Connection | str | Path,
    contract_id: int,
) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute(
            """
            SELECT id, contract_id, is_locked, locked_by_staff_id,
                   locked_by_device_name, locked_by_full_name, locked_at, updated_at
            FROM document_locks
            WHERE contract_id=?
            """,
            (int(contract_id),),
        ).fetchone()
        if not row:
            return {
                "contract_id": int(contract_id),
                "is_locked": 0,
                "locked_by_staff_id": None,
                "locked_by_device_name": None,
                "locked_by_full_name": None,
                "locked_at": None,
                "updated_at": None,
            }
        return dict(row)
    finally:
        if should_close:
            conn.close()


def lock_documents(
    db_or_path: sqlite3.Connection | str | Path,
    contract_id: int,
    staff: dict[str, Any],
) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO document_locks(
                contract_id, is_locked, locked_by_staff_id,
                locked_by_device_name, locked_by_full_name, locked_at, updated_at
            )
            VALUES(?, 1, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(contract_id) DO UPDATE SET
                is_locked=1,
                locked_by_staff_id=excluded.locked_by_staff_id,
                locked_by_device_name=excluded.locked_by_device_name,
                locked_by_full_name=excluded.locked_by_full_name,
                locked_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(contract_id),
                int(staff.get("id")) if staff and staff.get("id") is not None else None,
                str((staff or {}).get("device_name") or ""),
                str((staff or {}).get("full_name") or ""),
            ),
        )
        conn.commit()
        return get_document_lock_state(conn, contract_id)
    finally:
        if should_close:
            conn.close()


def unlock_documents(
    db_or_path: sqlite3.Connection | str | Path,
    contract_id: int,
) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO document_locks(contract_id, is_locked, updated_at)
            VALUES(?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(contract_id) DO UPDATE SET
                is_locked=0,
                locked_by_staff_id=NULL,
                locked_by_device_name=NULL,
                locked_by_full_name=NULL,
                locked_at=NULL,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(contract_id),),
        )
        conn.commit()
        return get_document_lock_state(conn, contract_id)
    finally:
        if should_close:
            conn.close()


def can_current_staff_access_documents(lock_state: Optional[dict[str, Any]], staff: Optional[dict[str, Any]]) -> bool:
    state = lock_state or {}
    if int(state.get("is_locked") or 0) == 0:
        return True
    if staff and bool(staff.get("is_admin")) and int(staff.get("is_active") if staff.get("is_active") is not None else 1) != 0:
        return True
    if not staff:
        return False
    return str(staff.get("device_name") or "") == str(state.get("locked_by_device_name") or "")


def get_staff_by_id(db_or_path: sqlite3.Connection | str | Path, staff_id: int):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return conn.execute(_staff_select_sql("WHERE s.id=?"), (int(staff_id),)).fetchone()
    finally:
        if should_close:
            conn.close()


def verify_staff_password_by_id(db_or_path: sqlite3.Connection | str | Path, staff_id: int, password: str) -> bool:
    row = get_staff_by_id(db_or_path, int(staff_id))
    if not row or int(row["is_active"] if row["is_active"] is not None else 1) == 0:
        return False
    return verify_password(password, str(row["password_hash"] or ""))


def require_document_unlock_password(parent, db_or_path: sqlite3.Connection | str | Path, lock_state: dict[str, Any]) -> bool:
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

    from src.ui.message_boxes import show_warning

    staff_id = lock_state.get("locked_by_staff_id")
    if staff_id is None:
        show_warning(parent, "Belgeler Kilitli", "Kilidi açacak personel kaydı bulunamadı veya pasif durumda.")
        return False
    row = get_staff_by_id(db_or_path, int(staff_id))
    if not row or int(row["is_active"] if row["is_active"] is not None else 1) == 0:
        show_warning(parent, "Belgeler Kilitli", "Kilidi açacak personel kaydı bulunamadı veya pasif durumda.")
        return False

    full_name = str(lock_state.get("locked_by_full_name") or row["full_name"] or "Personel")
    dlg = QDialog(parent)
    dlg.setWindowTitle("Belgeler Kilitli")
    dlg.setModal(True)
    dlg.setFixedWidth(440)
    try:
        from src.ui.theme import STYLE
        dlg.setStyleSheet(STYLE)
    except Exception:
        pass
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(12)
    title = QLabel("Belgeler Kilitli")
    title.setObjectName("mainTitle")
    layout.addWidget(title)
    desc = QLabel(f"Bu belgeler {full_name} tarafından kilitlendi. Açmak için kilitleyen personelin şifresini girin.")
    desc.setWordWrap(True)
    desc.setObjectName("muted")
    layout.addWidget(desc)
    password_edit = QLineEdit()
    password_edit.setEchoMode(QLineEdit.Password)
    password_edit.setPlaceholderText("Personel Şifresi")
    layout.addWidget(password_edit)
    row_layout = QHBoxLayout()
    row_layout.addStretch(1)
    cancel = QPushButton("Vazgeç")
    ok = QPushButton("Kilidi Aç")
    ok.setDefault(True)
    row_layout.addWidget(cancel)
    row_layout.addWidget(ok)
    layout.addLayout(row_layout)

    def submit():
        password = password_edit.text()
        if not password:
            show_warning(dlg, "Eksik bilgi", "Personel Şifresi boş bırakılamaz.")
            password_edit.setFocus()
            return
        valid = verify_staff_password_by_id(db_or_path, int(staff_id), password)
        if not valid:
            show_warning(dlg, "Şifre hatalı", "Şifre hatalı.")
            password_edit.setFocus()
            password_edit.selectAll()
            return
        cid = lock_state.get("contract_id")
        if cid is not None:
            unlock_documents(db_or_path, int(cid))
        dlg.accept()

    cancel.clicked.connect(dlg.reject)
    ok.clicked.connect(submit)
    password_edit.returnPressed.connect(submit)
    return dlg.exec() == QDialog.Accepted
