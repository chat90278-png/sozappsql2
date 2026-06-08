from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src import auth
from src.ui.theme import STYLE


class StaffManagementDialog(QDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(parent)
        auth.require_permission(current_user, "manage_staff", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.setWindowTitle("Personel Yönetimi")
        self.resize(1000, 640)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Personel Yönetimi", objectName="mainTitle"))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Cihaz", "Ad Soyad", "Rol", "Aktif", "Son Giriş", "Kayıt"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        root.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        for text, handler in (
            ("Ekle", self.add_staff),
            ("Düzenle", self.edit_staff),
            ("Aktif/Pasif", self.toggle_staff),
            ("Şifre Sıfırla", self.reset_password),
            ("Yenile", self.refresh),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        close = QPushButton("Kapat")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.refresh()

    def refresh(self):
        rows = auth.list_staff(self.db_or_path)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row.get("id"), row.get("device_name"), row.get("full_name"),
                row.get("role_display_name") or row.get("role_name") or row.get("role"),
                "Evet" if int(row.get("is_active") if row.get("is_active") is not None else 1) else "Hayır",
                row.get("last_login_at") or "", row.get("created_at") or "",
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(str(val or ""))
                if c == 0:
                    item.setData(Qt.UserRole, int(row.get("id") or 0))
                self.table.setItem(r, c, item)

    def _selected_staff_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Seçim gerekli", "Önce bir personel seçin.")
            return None
        return int(self.table.item(row, 0).data(Qt.UserRole))

    def _roles(self):
        return auth.list_roles(self.db_or_path)

    def _staff_form(self, title: str, row: Optional[dict] = None, include_device: bool = False):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        layout = QFormLayout(dlg)
        device = QLineEdit(str((row or {}).get("device_name") or ""))
        full_name = QLineEdit(str((row or {}).get("full_name") or ""))
        password = QLineEdit()
        password.setEchoMode(QLineEdit.Password)
        role_combo = QComboBox()
        roles = self._roles()
        for role in roles:
            role_combo.addItem(str(role["display_name"]), int(role["id"]))
        current_role_id = (row or {}).get("role_id")
        if current_role_id is not None:
            idx = role_combo.findData(int(current_role_id))
            if idx >= 0:
                role_combo.setCurrentIndex(idx)
        if include_device:
            layout.addRow("Cihaz adı", device)
            layout.addRow("Geçici şifre", password)
        layout.addRow("Ad soyad", full_name)
        layout.addRow("Rol", role_combo)
        actions = QHBoxLayout()
        ok = QPushButton("Kaydet")
        cancel = QPushButton("Vazgeç")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        actions.addStretch(1); actions.addWidget(cancel); actions.addWidget(ok)
        layout.addRow(actions)
        if dlg.exec() != QDialog.Accepted:
            return None
        return {
            "device_name": device.text().strip(),
            "full_name": full_name.text().strip(),
            "password": password.text(),
            "role_id": int(role_combo.currentData()),
        }

    def add_staff(self):
        try:
            data = self._staff_form("Personel Ekle", include_device=True)
            if not data:
                return
            if not data["device_name"] or not data["full_name"] or not data["password"]:
                QMessageBox.warning(self, "Eksik bilgi", "Cihaz, ad soyad ve şifre zorunludur.")
                return
            auth.create_staff_by_admin(self.db_or_path, self.current_user, data["device_name"], data["full_name"], data["password"], data["role_id"])
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Personel Ekle", str(exc))

    def edit_staff(self):
        sid = self._selected_staff_id()
        if sid is None:
            return
        row = next((r for r in auth.list_staff(self.db_or_path) if int(r["id"]) == sid), None)
        data = self._staff_form("Personel Düzenle", row=row)
        if not data:
            return
        try:
            auth.update_staff_record(self.db_or_path, self.current_user, sid, full_name=data["full_name"], role_id=data["role_id"])
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Personel Düzenle", str(exc))

    def toggle_staff(self):
        sid = self._selected_staff_id()
        if sid is None:
            return
        row = next((r for r in auth.list_staff(self.db_or_path) if int(r["id"]) == sid), None)
        if not row:
            return
        new_active = 0 if int(row.get("is_active") if row.get("is_active") is not None else 1) else 1
        try:
            auth.update_staff_record(self.db_or_path, self.current_user, sid, is_active=new_active)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Aktif/Pasif", str(exc))

    def reset_password(self):
        sid = self._selected_staff_id()
        if sid is None:
            return
        pwd, ok = QLineEdit(), QDialog(self)
        ok.setWindowTitle("Şifre Sıfırla")
        form = QFormLayout(ok)
        pwd.setEchoMode(QLineEdit.Password)
        form.addRow("Yeni şifre", pwd)
        row = QHBoxLayout(); cancel = QPushButton("Vazgeç"); save = QPushButton("Kaydet")
        cancel.clicked.connect(ok.reject); save.clicked.connect(ok.accept)
        row.addStretch(1); row.addWidget(cancel); row.addWidget(save); form.addRow(row)
        if ok.exec() != QDialog.Accepted:
            return
        if not pwd.text():
            QMessageBox.warning(self, "Eksik bilgi", "Şifre boş olamaz.")
            return
        try:
            auth.reset_staff_password(self.db_or_path, self.current_user, sid, pwd.text())
            QMessageBox.information(self, "Şifre Sıfırla", "Şifre güncellendi.")
        except Exception as exc:
            QMessageBox.warning(self, "Şifre Sıfırla", str(exc))


class RolePermissionsDialog(QDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(parent)
        auth.require_permission(current_user, "manage_roles", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.setWindowTitle("Roller ve Yetkiler")
        self.resize(1100, 700)
        self.setStyleSheet(STYLE)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Roller ve Yetkiler", objectName="mainTitle"))
        root.addWidget(QLabel("Her rolün yetkilerini checkbox ile düzenleyebilirsiniz. Son tam yetkili aktif kullanıcıyı kaldıran değişiklikler engellenir."))
        self.table = QTableWidget(0, 0)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)
        buttons = QHBoxLayout(); buttons.addStretch(1)
        close = QPushButton("Kapat"); close.clicked.connect(self.accept); buttons.addWidget(close)
        root.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.roles = auth.list_roles(self.db_or_path)
        self.permissions = auth.list_permissions(self.db_or_path)
        role_map = auth.get_role_permission_map(self.db_or_path)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.permissions))
        self.table.setColumnCount(2 + len(self.roles))
        self.table.setHorizontalHeaderLabels(["Kategori", "Yetki"] + [r["display_name"] for r in self.roles])
        for r, perm in enumerate(self.permissions):
            self.table.setItem(r, 0, QTableWidgetItem(str(perm.get("category") or "")))
            self.table.setItem(r, 1, QTableWidgetItem(f"{perm['display_name']}\n{perm['code']}"))
            for c, role in enumerate(self.roles, start=2):
                box = QCheckBox()
                box.setChecked(bool(role_map.get(int(role["id"]), {}).get(str(perm["code"]), False)))
                box.setProperty("role_id", int(role["id"]))
                box.setProperty("permission_code", str(perm["code"]))
                box.stateChanged.connect(self._permission_changed)
                wrapper = QWidget(); lay = QHBoxLayout(wrapper); lay.setContentsMargins(0,0,0,0); lay.addWidget(box, 0, Qt.AlignCenter)
                self.table.setCellWidget(r, c, wrapper)
        self.table.blockSignals(False)

    def _permission_changed(self, _state):
        box = self.sender()
        if box is None:
            return
        role_id = int(box.property("role_id"))
        code = str(box.property("permission_code"))
        try:
            auth.set_role_permission(self.db_or_path, self.current_user, role_id, code, bool(box.isChecked()))
        except Exception as exc:
            box.blockSignals(True)
            box.setChecked(not bool(box.isChecked()))
            box.blockSignals(False)
            QMessageBox.warning(self, "Yetki Güncelleme", str(exc))
