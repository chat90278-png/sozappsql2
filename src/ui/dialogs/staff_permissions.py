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
    ROLE_ORDER = ["admin", "manager", "personnel", "viewer"]

    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(parent)
        auth.require_permission(current_user, "manage_roles", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.checkboxes: dict[tuple[int, str], QCheckBox] = {}
        self.setWindowTitle("Yetki Yönetimi")
        self.resize(980, 720)
        self.setStyleSheet(STYLE + self._local_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        icon = QLabel("▢"); icon.setObjectName("permissionIcon")
        title = QLabel("Yetki Yönetimi"); title.setObjectName("mainTitle")
        header.addWidget(icon); header.addWidget(title); header.addStretch(1)
        root.addLayout(header)

        tab_bar = QFrame(); tab_bar.setObjectName("roleTabs")
        tab_layout = QHBoxLayout(tab_bar); tab_layout.setContentsMargins(8, 8, 8, 0); tab_layout.setSpacing(0)
        self.roles = sorted(auth.list_roles(self.db_or_path), key=lambda r: self.ROLE_ORDER.index(r["name"]) if r.get("name") in self.ROLE_ORDER else 99)
        for role in self.roles:
            lbl = QLabel(f"♟  {role['display_name']}")
            lbl.setObjectName("roleTab")
            if str(role.get("name")) == "admin":
                lbl.setProperty("active", "true")
            tab_layout.addWidget(lbl, 1)
        root.addWidget(tab_bar)

        info = QLabel("ℹ  Rol seçerek ilgili rolün modül ve işlem yetkilerini düzenleyebilirsiniz.")
        info.setObjectName("permissionInfo")
        root.addWidget(info)
        selected = QLabel("Seçili rol: Admin")
        selected.setObjectName("selectedRole")
        root.addWidget(selected)

        self.table = QTableWidget(0, 0)
        self.table.setObjectName("permissionMatrix")
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        defaults = QPushButton("↺ Varsayılanlara Dön"); defaults.clicked.connect(self.restore_defaults)
        buttons.addWidget(defaults); buttons.addStretch(1)
        cancel = QPushButton("İptal"); cancel.clicked.connect(self.reject)
        save = QPushButton("▣ Kaydet"); save.setObjectName("primaryBtn"); save.clicked.connect(self.save)
        buttons.addWidget(cancel); buttons.addWidget(save)
        root.addLayout(buttons)
        self.refresh()

    def _local_style(self) -> str:
        return """
        QDialog { background:#f4f7fb; }
        QLabel#permissionIcon { background:#eef5ff; color:#1d4ed8; border:1px solid #d7e7ff; border-radius:6px; padding:2px 6px; font-weight:900; }
        QFrame#roleTabs { background:#ffffff; border:1px solid #d8e2ed; border-radius:10px; }
        QLabel#roleTab { background:#ffffff; color:#0f172a; font-weight:800; padding:12px 18px; border-bottom:3px solid transparent; }
        QLabel#roleTab[active='true'] { color:#1459e6; border-bottom:3px solid #1d5cff; }
        QLabel#permissionInfo { background:#f8fbff; border:1px solid #d7e6fb; border-radius:8px; padding:9px 12px; color:#1f3b58; font-size:12px; }
        QLabel#selectedRole { background:#ffffff; border:1px dashed #cbdcf0; border-radius:8px; padding:9px 12px; color:#1f3b58; font-size:12px; }
        QTableWidget#permissionMatrix { background:#ffffff; border:1px solid #d8e2ed; border-radius:8px; gridline-color:#e7eef7; selection-background-color:#eef5ff; }
        QHeaderView::section { background:#f8fbff; color:#0f1e35; border:0; border-bottom:1px solid #d8e2ed; padding:8px; font-weight:900; }
        QPushButton#primaryBtn { background:#1d5bd8; color:white; border:0; border-radius:8px; padding:8px 18px; font-weight:900; }
        """

    def refresh(self):
        self.roles = sorted(auth.list_roles(self.db_or_path), key=lambda r: self.ROLE_ORDER.index(r["name"]) if r.get("name") in self.ROLE_ORDER else 99)
        permission_rows = []
        for category, permissions in auth.PERMISSION_GROUPS:
            permission_rows.append((category, None, None, None))
            for code, display, desc in permissions:
                permission_rows.append((category, code, display, desc))
        role_map = auth.get_role_permission_map(self.db_or_path)
        self.checkboxes.clear()
        self.table.setRowCount(len(permission_rows))
        self.table.setColumnCount(1 + len(self.roles))
        self.table.setHorizontalHeaderLabels(["Modül / İşlem"] + [r["display_name"] for r in self.roles])
        for row_index, (_category, code, display, desc) in enumerate(permission_rows):
            if code is None:
                item = QTableWidgetItem(f"▼ {_category}")
                item.setFlags(Qt.ItemIsEnabled)
                font = item.font(); font.setBold(True); item.setFont(font)
                self.table.setItem(row_index, 0, item)
                for c in range(1, 1 + len(self.roles)):
                    filler = QTableWidgetItem(""); filler.setFlags(Qt.ItemIsEnabled); self.table.setItem(row_index, c, filler)
                self.table.setSpan(row_index, 0, 1, 1 + len(self.roles))
                self.table.setRowHeight(row_index, 30)
                continue
            item = QTableWidgetItem(f"{display}\n{desc or code}")
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row_index, 0, item)
            self.table.setRowHeight(row_index, 38)
            for col_index, role in enumerate(self.roles, start=1):
                box = QCheckBox()
                role_id = int(role["id"])
                box.setChecked(bool(role_map.get(role_id, {}).get(str(code), False)))
                wrapper = QWidget(); lay = QHBoxLayout(wrapper); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(box, 0, Qt.AlignCenter)
                self.table.setCellWidget(row_index, col_index, wrapper)
                self.checkboxes[(role_id, str(code))] = box
        self.table.resizeRowsToContents()

    def _collect_permissions(self) -> dict[int, dict[str, bool]]:
        out: dict[int, dict[str, bool]] = {}
        for (role_id, code), box in self.checkboxes.items():
            out.setdefault(role_id, {})[code] = bool(box.isChecked())
        return out

    def save(self):
        try:
            auth.set_role_permissions_bulk(self.db_or_path, self.current_user, self._collect_permissions())
            if self.current_user is not None:
                refreshed = auth.enrich_staff_permissions(self.db_or_path, self.current_user)
                if refreshed:
                    self.current_user.update(refreshed)
                    auth.current_staff = self.current_user
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
            QMessageBox.information(self, "Yetki Yönetimi", "Yetkiler kaydedildi.")
            self.accept()
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))

    def restore_defaults(self):
        answer = QMessageBox.question(
            self,
            "Varsayılanlara Dön",
            "Varsayılan rol/yetki şablonu geri yüklensin mi?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            auth.reset_role_permissions_to_defaults(self.db_or_path, self.current_user)
            self.refresh()
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
            QMessageBox.information(self, "Yetki Yönetimi", "Varsayılan yetkiler geri yüklendi.")
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))
