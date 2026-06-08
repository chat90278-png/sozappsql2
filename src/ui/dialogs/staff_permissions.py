from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
    ROLE_COLORS = {
        "admin": "#1457d9",
        "manager": "#21a047",
        "personnel": "#f59e0b",
        "viewer": "#7c3aed",
    }
    ROLE_LABELS = {
        "admin": "Admin",
        "manager": "Yönetici",
        "personnel": "Personel",
        "viewer": "Görüntüleyici",
    }

    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(parent)
        auth.require_permission(current_user, "manage_roles", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.roles: list[dict[str, Any]] = []
        self.permissions: list[dict[str, Any]] = []
        self._checkboxes: dict[tuple[int, str], QCheckBox] = {}
        self._pending_permissions: dict[int, dict[str, bool]] = {}
        self._active_role_name = "admin"

        self.setWindowTitle("Yetki Yönetimi")
        self.resize(820, 760)
        self.setMinimumSize(760, 620)
        self.setStyleSheet(STYLE + self._permission_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QFrame()
        body.setObjectName("permissionBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(12)
        body_layout.addWidget(self._build_role_tabs())
        body_layout.addWidget(self._build_info_box())
        self.selected_role_note = QLabel()
        self.selected_role_note.setObjectName("selectedRoleNote")
        body_layout.addWidget(self.selected_role_note)
        self.table = QTableWidget(0, 0)
        self.table.setObjectName("permissionTable")
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        body_layout.addWidget(self.table, 1)
        root.addWidget(body, 1)
        root.addWidget(self._build_footer())
        self.refresh()

    def _permission_style(self) -> str:
        return """
        QDialog { background:#f3f6fb; }
        QFrame#permissionHeader { background:#ffffff; border-bottom:1px solid #dbe3ef; }
        QLabel#permissionTitle { font-size:18px; font-weight:900; color:#0f172a; }
        QLabel#shieldIcon { background:#eaf1ff; color:#1457d9; border-radius:8px; font-size:15px; }
        QPushButton#closeBtn { background:transparent; border:0; color:#334155; font-size:20px; border-radius:8px; }
        QPushButton#closeBtn:hover { background:#f1f5f9; }
        QFrame#permissionBody { background:#ffffff; }
        QFrame#roleTabs { background:#ffffff; border:1px solid #dbe3ef; border-radius:12px; }
        QPushButton#roleTab { background:#ffffff; border:0; border-bottom:3px solid transparent; color:#334155; padding:13px 10px; font-weight:900; }
        QPushButton#roleTab:hover { background:#f8fafc; }
        QFrame#infoBox { background:#f8fbff; border:1px solid #e1ecff; border-radius:9px; }
        QLabel#infoText { color:#31528a; font-size:12px; font-weight:600; }
        QLabel#selectedRoleNote { background:#f8fafc; border:1px dashed #dbe3ef; border-radius:9px; padding:9px 11px; color:#475569; font-size:12px; }
        QTableWidget#permissionTable { background:#ffffff; border:1px solid #dbe3ef; border-radius:10px; gridline-color:#eef2f7; color:#1f2937; font-size:12px; }
        QTableWidget#permissionTable::item { padding:3px 9px; }
        QHeaderView::section { background:#f8fafc; color:#334155; border:0; border-bottom:1px solid #dbe3ef; padding:8px 10px; font-weight:900; }
        QFrame#permissionFooter { background:#fbfdff; border-top:1px solid #dbe3ef; }
        QPushButton#secondaryBtn { background:#ffffff; color:#334155; border:1px solid #dbe3ef; border-radius:9px; padding:9px 15px; font-weight:800; }
        QPushButton#secondaryBtn:hover { background:#f8fafc; }
        QPushButton#primaryBtn { background:#1457d9; color:#ffffff; border:1px solid #1457d9; border-radius:9px; padding:9px 18px; font-weight:900; }
        QPushButton#primaryBtn:hover { background:#0f48b8; }
        """

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("permissionHeader")
        header.setFixedHeight(58)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 14, 0)
        shield = QLabel("🛡")
        shield.setObjectName("shieldIcon")
        shield.setFixedSize(28, 28)
        shield.setAlignment(Qt.AlignCenter)
        title = QLabel("Yetki Yönetimi")
        title.setObjectName("permissionTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(34, 34)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(shield)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(close_btn)
        return header

    def _build_role_tabs(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("roleTabs")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.role_tab_buttons: dict[str, QPushButton] = {}
        for role_name in ("admin", "manager", "personnel", "viewer"):
            btn = QPushButton(f"👤  {self.ROLE_LABELS[role_name]}")
            btn.setObjectName("roleTab")
            btn.clicked.connect(lambda _=False, rn=role_name: self._select_role_tab(rn))
            layout.addWidget(btn, 1)
            self.role_tab_buttons[role_name] = btn
        return wrap

    def _build_info_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("infoBox")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(11, 9, 11, 9)
        icon = QLabel("ℹ️")
        text = QLabel("Rol seçerek ilgili rolün modül ve işlem yetkilerini düzenleyebilirsiniz.")
        text.setObjectName("infoText")
        layout.addWidget(icon)
        layout.addWidget(text, 1)
        return box

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("permissionFooter")
        footer.setFixedHeight(66)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 0, 18, 0)
        defaults = QPushButton("↺ Varsayılanlara Dön")
        defaults.setObjectName("secondaryBtn")
        defaults.clicked.connect(self.restore_defaults)
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondaryBtn")
        cancel.clicked.connect(self.reject)
        save = QPushButton("💾 Kaydet")
        save.setObjectName("primaryBtn")
        save.clicked.connect(self.save_changes)
        layout.addWidget(defaults)
        layout.addStretch(1)
        layout.addWidget(cancel)
        layout.addWidget(save)
        return footer

    def refresh(self):
        self.roles = auth.list_roles(self.db_or_path)
        self.permissions = auth.list_permissions(self.db_or_path)
        self._pending_permissions = auth.get_role_permission_map(self.db_or_path)
        self._render_permission_table()
        self._select_role_tab(self._active_role_name)

    def _render_permission_table(self):
        self._checkboxes.clear()
        role_headers = [self.ROLE_LABELS.get(str(r["name"]), str(r["display_name"])) for r in self.roles]
        rows: list[tuple[str, Optional[dict[str, Any]]]] = []
        last_category = None
        for perm in self.permissions:
            category = str(perm.get("category") or "Diğer")
            if category != last_category:
                rows.append(("group", {"category": category}))
                last_category = category
            rows.append(("permission", perm))

        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(1 + len(self.roles))
        self.table.setHorizontalHeaderLabels(["Modül / İşlem"] + role_headers)
        for row_idx, (row_type, payload) in enumerate(rows):
            if row_type == "group":
                self.table.setSpan(row_idx, 0, 1, 1 + len(self.roles))
                item = QTableWidgetItem(f"▼  {payload['category']}")
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(Qt.GlobalColor.transparent)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                self.table.setItem(row_idx, 0, item)
                self.table.setRowHeight(row_idx, 34)
                continue

            perm = payload or {}
            label = f"{perm['display_name']}\n{perm.get('description') or perm['code']}"
            item = QTableWidgetItem(label)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row_idx, 0, item)
            code = str(perm["code"])
            for col_idx, role in enumerate(self.roles, start=1):
                role_id = int(role["id"])
                role_name = str(role["name"])
                box = QCheckBox()
                box.setChecked(bool(self._pending_permissions.get(role_id, {}).get(code, False)))
                color = self.ROLE_COLORS.get(role_name, "#1457d9")
                box.setStyleSheet(
                    "QCheckBox::indicator { width:16px; height:16px; } "
                    f"QCheckBox::indicator:checked {{ background:{color}; border:1px solid {color}; }}"
                )
                box.stateChanged.connect(lambda state, rid=role_id, pcode=code: self._set_pending_permission(rid, pcode, int(state) == int(Qt.CheckState.Checked.value)))
                wrapper = QWidget()
                layout = QHBoxLayout(wrapper)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(box, 0, Qt.AlignCenter)
                self.table.setCellWidget(row_idx, col_idx, wrapper)
                self._checkboxes[(role_id, code)] = box
            self.table.setRowHeight(row_idx, 42)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.setUpdatesEnabled(True)

    def _set_pending_permission(self, role_id: int, code: str, allowed: bool):
        self._pending_permissions.setdefault(int(role_id), {})[str(code)] = bool(allowed)

    def _select_role_tab(self, role_name: str):
        if role_name not in self.role_tab_buttons:
            role_name = "admin"
        self._active_role_name = role_name
        for name, btn in self.role_tab_buttons.items():
            active = name == role_name
            color = self.ROLE_COLORS.get(name, "#1457d9")
            btn.setStyleSheet(
                f"color:{color if active else '#334155'}; "
                f"border-bottom:3px solid {color if active else 'transparent'};"
            )
        label = self.ROLE_LABELS.get(role_name, role_name)
        color = self.ROLE_COLORS.get(role_name, "#1457d9")
        self.selected_role_note.setText(f"Seçili rol: <b style='color:{color}'>{label}</b>")
        role_index = next((idx for idx, role in enumerate(self.roles, start=1) if str(role["name"]) == role_name), None)
        if role_index is not None:
            self.table.selectColumn(role_index)
            self.table.clearSelection()

    def restore_defaults(self):
        role_name_by_id = {int(role["id"]): str(role["name"]) for role in self.roles}
        for role_id, role_name in role_name_by_id.items():
            defaults = auth.DEFAULT_ROLE_PERMISSIONS.get(role_name)
            if defaults is None:
                continue
            for perm in self.permissions:
                code = str(perm["code"])
                allowed = code in defaults
                self._pending_permissions.setdefault(role_id, {})[code] = allowed
                box = self._checkboxes.get((role_id, code))
                if box is not None:
                    box.blockSignals(True)
                    box.setChecked(allowed)
                    box.blockSignals(False)
        QMessageBox.information(self, "Varsayılanlar", "Varsayılan yetkiler ekrana yüklendi. Kalıcı yapmak için Kaydet'e basın.")

    def save_changes(self):
        try:
            for role in self.roles:
                role_id = int(role["id"])
                for perm in self.permissions:
                    code = str(perm["code"])
                    allowed = bool(self._pending_permissions.get(role_id, {}).get(code, False))
                    auth.set_role_permission(self.db_or_path, self.current_user, role_id, code, allowed)
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Kaydetme", str(exc))
            self.refresh()
            return
        QMessageBox.information(self, "Yetki Yönetimi", "Rol yetkileri kaydedildi.")
        self.accept()
