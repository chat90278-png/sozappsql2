from __future__ import annotations

import hashlib
import hmac
import os
import socket
import sqlite3
from pathlib import Path
from typing import Any, Optional

ROLE_LABELS = {
    "admin": "Yönetici",
    "manager": "Birim Sorumlusu",
    "staff": "Personel",
    "viewer": "Görüntüleyici",
}

current_staff: Optional[dict[str, Any]] = None

_STAFF_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'staff',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
"""


def _connection_from(db_or_path: sqlite3.Connection | str | Path) -> tuple[sqlite3.Connection, bool]:
    if isinstance(db_or_path, sqlite3.Connection):
        db_or_path.row_factory = sqlite3.Row
        return db_or_path, False
    conn = sqlite3.connect(str(Path(db_or_path)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn, True


def ensure_staff_table(db_or_path: sqlite3.Connection | str | Path) -> None:
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(_STAFF_TABLE_SQL)
        conn.commit()
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


def get_staff_by_device(db_or_path: sqlite3.Connection | str | Path, device_name: str):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return conn.execute(
            "SELECT id, device_name, full_name, password_hash, role, is_active FROM staff WHERE device_name=?",
            (str(device_name or ""),),
        ).fetchone()
    finally:
        if should_close:
            conn.close()


def create_staff(db_or_path: sqlite3.Connection | str | Path, device_name: str, full_name: str, password: str):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO staff(device_name, full_name, password_hash, role, is_active)
            VALUES(?, ?, ?, 'staff', 1)
            """,
            (str(device_name or ""), str(full_name or "").strip(), hash_password(password)),
        )
        conn.commit()
        return conn.execute(
            "SELECT id, device_name, full_name, password_hash, role, is_active FROM staff WHERE device_name=?",
            (str(device_name or ""),),
        ).fetchone()
    finally:
        if should_close:
            conn.close()


def build_current_staff(row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "device_name": str(row["device_name"] or ""),
        "full_name": str(row["full_name"] or ""),
        "role": str(row["role"] or "staff"),
        "is_active": int(row["is_active"] if row["is_active"] is not None else 1),
    }


def has_role(role: str, staff: Optional[dict[str, Any]] = None) -> bool:
    candidate = staff if staff is not None else current_staff
    return bool(candidate and str(candidate.get("role") or "") == str(role or ""))


def staff_has_permission(permission: str, staff: Optional[dict[str, Any]] = None) -> bool:
    # Yetki kuralları sonraki aşamada tanımlanacak. Şimdilik sadece altyapı hazır.
    return bool(staff if staff is not None else current_staff)



def _build_staff_register_dialog(db_or_path: sqlite3.Connection | str | Path, device_name: str, parent=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
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
            form.addRow("Cihaz Adı", self.device_edit)
            form.addRow("Personel Adı Soyadı", self.full_name_edit)
            form.addRow("Şifre Belirle", self.password_edit)
            form.addRow("Şifre Tekrar", self.password_repeat_edit)
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

        def _submit(self):
            full_name = self.full_name_edit.text().strip()
            password = self.password_edit.text()
            password_repeat = self.password_repeat_edit.text()
            if not full_name:
                QMessageBox.warning(self, "Eksik bilgi", "Personel Adı Soyadı boş bırakılamaz.")
                self.full_name_edit.setFocus()
                return
            if not password:
                QMessageBox.warning(self, "Eksik bilgi", "Şifre boş bırakılamaz.")
                self.password_edit.setFocus()
                return
            if password != password_repeat:
                QMessageBox.warning(self, "Şifreler eşleşmiyor", "Girdiğiniz şifreler eşleşmiyor. Lütfen tekrar deneyin.")
                self.password_repeat_edit.setFocus()
                self.password_repeat_edit.selectAll()
                return
            try:
                row = create_staff(db_or_path, str(device_name or ""), full_name, password)
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Kayıt mevcut", "Bu cihaz için personel kaydı zaten mevcut. Lütfen giriş yapın.")
                return
            self.staff = build_current_staff(row)
            self.accept()

    return StaffRegisterDialog()


def _build_staff_login_dialog(db_or_path: sqlite3.Connection | str | Path, row, parent=None):
    from PySide6.QtWidgets import (
        QDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
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

        def _submit(self):
            if int(row["is_active"] if row["is_active"] is not None else 1) == 0:
                QMessageBox.warning(self, "Personel pasif", "Bu personel kaydı pasif durumda.")
                return
            password = self.password_edit.text()
            if not password:
                QMessageBox.warning(self, "Eksik bilgi", "Personel Şifresi boş bırakılamaz.")
                self.password_edit.setFocus()
                return
            if not verify_password(password, str(row["password_hash"] or "")):
                QMessageBox.warning(self, "Giriş başarısız", "Personel şifresi hatalı. Lütfen tekrar deneyin.")
                self.password_edit.setFocus()
                self.password_edit.selectAll()
                return
            self.staff = build_current_staff(row)
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
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(parent, "Personel pasif", "Bu personel kaydı pasif durumda.")
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
        staff = build_current_staff(row)
    else:
        staff = show_staff_register_dialog(db_or_path, device_name, parent)
    current_staff = staff
    return staff


def ensure_document_locks_table(db_or_path: sqlite3.Connection | str | Path) -> None:
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_locks (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_locked INTEGER NOT NULL DEFAULT 0,
                locked_by_staff_id INTEGER,
                locked_by_device_name TEXT,
                locked_by_full_name TEXT,
                locked_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(locked_by_staff_id) REFERENCES staff(id) ON DELETE SET NULL
            )
            """
        )
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_document_lock_state(db_or_path: sqlite3.Connection | str | Path) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        row = conn.execute(
            """
            SELECT id, is_locked, locked_by_staff_id, locked_by_device_name,
                   locked_by_full_name, locked_at, updated_at
            FROM document_locks
            WHERE id=1
            """
        ).fetchone()
        if not row:
            return {
                "id": 1,
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


def lock_documents(db_or_path: sqlite3.Connection | str | Path, staff: dict[str, Any]) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO document_locks(
                id, is_locked, locked_by_staff_id, locked_by_device_name,
                locked_by_full_name, locked_at, updated_at
            )
            VALUES(1, 1, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                is_locked=1,
                locked_by_staff_id=excluded.locked_by_staff_id,
                locked_by_device_name=excluded.locked_by_device_name,
                locked_by_full_name=excluded.locked_by_full_name,
                locked_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(staff.get("id")) if staff and staff.get("id") is not None else None,
                str((staff or {}).get("device_name") or ""),
                str((staff or {}).get("full_name") or ""),
            ),
        )
        conn.commit()
        return get_document_lock_state(conn)
    finally:
        if should_close:
            conn.close()


def unlock_documents(db_or_path: sqlite3.Connection | str | Path) -> dict[str, Any]:
    ensure_document_locks_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        conn.execute(
            """
            INSERT INTO document_locks(id, is_locked, updated_at)
            VALUES(1, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                is_locked=0,
                locked_by_staff_id=NULL,
                locked_by_device_name=NULL,
                locked_by_full_name=NULL,
                locked_at=NULL,
                updated_at=CURRENT_TIMESTAMP
            """
        )
        conn.commit()
        return get_document_lock_state(conn)
    finally:
        if should_close:
            conn.close()


def can_current_staff_access_documents(lock_state: Optional[dict[str, Any]], staff: Optional[dict[str, Any]]) -> bool:
    state = lock_state or {}
    if int(state.get("is_locked") or 0) == 0:
        return True
    if not staff:
        return False
    return str(staff.get("device_name") or "") == str(state.get("locked_by_device_name") or "")


def get_staff_by_id(db_or_path: sqlite3.Connection | str | Path, staff_id: int):
    ensure_staff_table(db_or_path)
    conn, should_close = _connection_from(db_or_path)
    try:
        return conn.execute(
            "SELECT id, device_name, full_name, password_hash, role, is_active FROM staff WHERE id=?",
            (int(staff_id),),
        ).fetchone()
    finally:
        if should_close:
            conn.close()


def verify_staff_password_by_id(db_or_path: sqlite3.Connection | str | Path, staff_id: int, password: str) -> bool:
    row = get_staff_by_id(db_or_path, int(staff_id))
    if not row or int(row["is_active"] if row["is_active"] is not None else 1) == 0:
        return False
    return verify_password(password, str(row["password_hash"] or ""))


def require_document_unlock_password(parent, db_or_path: sqlite3.Connection | str | Path, lock_state: dict[str, Any]) -> bool:
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

    staff_id = lock_state.get("locked_by_staff_id")
    if staff_id is None:
        QMessageBox.warning(parent, "Belgeler Kilitli", "Kilidi açacak personel kaydı bulunamadı veya pasif durumda.")
        return False
    row = get_staff_by_id(db_or_path, int(staff_id))
    if not row or int(row["is_active"] if row["is_active"] is not None else 1) == 0:
        QMessageBox.warning(parent, "Belgeler Kilitli", "Kilidi açacak personel kaydı bulunamadı veya pasif durumda.")
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
            QMessageBox.warning(dlg, "Eksik bilgi", "Personel Şifresi boş bırakılamaz.")
            password_edit.setFocus()
            return
        valid = verify_staff_password_by_id(db_or_path, int(staff_id), password)
        if not valid:
            QMessageBox.warning(dlg, "Şifre hatalı", "Şifre hatalı.")
            password_edit.setFocus()
            password_edit.selectAll()
            return
        unlock_documents(db_or_path)
        dlg.accept()

    cancel.clicked.connect(dlg.reject)
    ok.clicked.connect(submit)
    password_edit.returnPressed.connect(submit)
    return dlg.exec() == QDialog.Accepted
