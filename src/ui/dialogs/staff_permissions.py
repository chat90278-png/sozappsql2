from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    ROLE_ORDER = ["admin", "manager", "personnel", "viewer"]
    ROLE_COLORS = {
        "admin": "#1457d9",
        "manager": "#22a447",
        "personnel": "#f59e0b",
        "viewer": "#7c3aed",
    }

    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(parent)
        auth.require_permission(current_user, "manage_roles", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.roles = self._ordered_roles()
        self.role_by_id = {int(role["id"]): role for role in self.roles}
        self.role_tabs: dict[int, QPushButton] = {}
        self.checkboxes: dict[str, QCheckBox] = {}
        self.active_role_id = self._initial_role_id()

        self.setWindowTitle("Yetki Yönetimi")
        self.resize(860, 720)
        self.setStyleSheet(STYLE + self._local_style())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(); header.setObjectName("permissionHeader")
        header_layout = QHBoxLayout(header); header_layout.setContentsMargins(18, 0, 14, 0); header_layout.setSpacing(10)
        icon = QLabel("🛡"); icon.setObjectName("permissionIcon")
        title = QLabel("Yetki Yönetimi"); title.setObjectName("permissionTitle")
        close = QPushButton("×"); close.setObjectName("closeBtn"); close.clicked.connect(self.reject)
        header_layout.addWidget(icon); header_layout.addWidget(title); header_layout.addStretch(1); header_layout.addWidget(close)
        root.addWidget(header)

        body = QFrame(); body.setObjectName("permissionBody")
        body_layout = QVBoxLayout(body); body_layout.setContentsMargins(18, 12, 18, 12); body_layout.setSpacing(12)
        root.addWidget(body, 1)

        content = QFrame(); content.setObjectName("contentBox")
        content_layout = QVBoxLayout(content); content_layout.setContentsMargins(0, 0, 0, 0); content_layout.setSpacing(0)
        body_layout.addWidget(content, 1)

        tabs = QFrame(); tabs.setObjectName("roleTabs")
        tabs_layout = QHBoxLayout(tabs); tabs_layout.setContentsMargins(0, 0, 0, 0); tabs_layout.setSpacing(0)
        for role in self.roles:
            role_id = int(role["id"])
            btn = QPushButton(f"♟  {role['display_name']}")
            btn.setObjectName("roleTab")
            btn.setProperty("roleName", str(role.get("name") or ""))
            btn.clicked.connect(lambda _checked=False, rid=role_id: self.set_active_role(rid))
            tabs_layout.addWidget(btn, 1)
            self.role_tabs[role_id] = btn
        content_layout.addWidget(tabs)

        info_area = QFrame(); info_area.setObjectName("infoArea")
        info_layout = QVBoxLayout(info_area); info_layout.setContentsMargins(12, 10, 12, 0); info_layout.setSpacing(8)
        info = QLabel("ℹ  Rol seçerek ilgili rolün modül ve işlem yetkilerini düzenleyebilirsiniz.")
        info.setObjectName("permissionInfo")
        self.selected_role_label = QLabel()
        self.selected_role_label.setObjectName("selectedRole")
        info_layout.addWidget(info)
        info_layout.addWidget(self.selected_role_label)
        content_layout.addWidget(info_area)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("permissionList")
        self.table.setHorizontalHeaderLabels(["Yetki / İşlem", "Açıklama", "Durum"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(True)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        content_layout.addWidget(self.table, 1)

        footer = QFrame(); footer.setObjectName("permissionFooter")
        footer_layout = QHBoxLayout(footer); footer_layout.setContentsMargins(18, 0, 18, 0); footer_layout.setSpacing(10)
        defaults = QPushButton("↺ Varsayılanlara Dön"); defaults.setObjectName("resetBtn"); defaults.clicked.connect(self.restore_defaults)
        cancel = QPushButton("İptal"); cancel.clicked.connect(self.reject)
        save = QPushButton("💾 Kaydet"); save.setObjectName("primaryBtn"); save.clicked.connect(self.save)
        footer_layout.addWidget(defaults); footer_layout.addStretch(1); footer_layout.addWidget(cancel); footer_layout.addWidget(save)
        root.addWidget(footer)

        self.set_active_role(self.active_role_id)

    def _ordered_roles(self) -> list[dict[str, Any]]:
        roles = auth.list_roles(self.db_or_path)
        return sorted(roles, key=lambda r: self.ROLE_ORDER.index(str(r.get("name"))) if str(r.get("name")) in self.ROLE_ORDER else 99)

    def _initial_role_id(self) -> int:
        current_role_id = (self.current_user or {}).get("role_id")
        if current_role_id is not None and int(current_role_id) in {int(r["id"]) for r in self.roles}:
            return int(current_role_id)
        return int(self.roles[0]["id"])

    def _active_role(self) -> dict[str, Any]:
        return self.role_by_id[int(self.active_role_id)]

    def _active_role_name(self) -> str:
        return str(self._active_role().get("name") or "")

    def _active_color(self) -> str:
        return self.ROLE_COLORS.get(self._active_role_name(), "#1457d9")

    def _local_style(self) -> str:
        return """
        QDialog { background:#eef2f7; }
        QFrame#permissionHeader { background:#ffffff; border-bottom:1px solid #d7dfeb; min-height:54px; max-height:54px; }
        QLabel#permissionIcon { background:#f2f6ff; color:#1457d9; border:1px solid #dbe8ff; border-radius:7px; min-width:24px; min-height:24px; max-width:24px; max-height:24px; qproperty-alignment: AlignCenter; }
        QLabel#permissionTitle { background:transparent; color:#111827; font-size:15px; font-weight:900; }
        QPushButton#closeBtn { background:transparent; border:0; border-radius:8px; font-size:18px; font-weight:600; min-width:32px; min-height:32px; max-width:32px; max-height:32px; }
        QPushButton#closeBtn:hover { background:#f1f5f9; }
        QFrame#permissionBody { background:#eef2f7; }
        QFrame#contentBox { background:#ffffff; border:1px solid #d7dfeb; border-radius:10px; }
        QFrame#roleTabs { background:#ffffff; border-bottom:1px solid #d7dfeb; min-height:58px; max-height:58px; }
        QPushButton#roleTab { background:#ffffff; border:0; border-bottom:3px solid transparent; color:#1f2937; font-weight:900; padding:0 12px; }
        QPushButton#roleTab:hover { background:#fbfdff; }
        QPushButton#roleTab[active='true'][roleName='admin'] { color:#1457d9; border-bottom-color:#1457d9; }
        QPushButton#roleTab[active='true'][roleName='manager'] { color:#22a447; border-bottom-color:#22a447; }
        QPushButton#roleTab[active='true'][roleName='personnel'] { color:#f59e0b; border-bottom-color:#f59e0b; }
        QPushButton#roleTab[active='true'][roleName='viewer'] { color:#7c3aed; border-bottom-color:#7c3aed; }
        QFrame#infoArea { background:#ffffff; }
        QLabel#permissionInfo { background:#f4f8ff; border:1px solid #dce9ff; border-radius:8px; color:#244a84; padding:8px 10px; font-size:12px; }
        QLabel#selectedRole { background:#fbfdff; border:1px dashed #d7dfeb; border-radius:8px; color:#475569; padding:8px 10px; font-size:12px; }
        QTableWidget#permissionList { margin:12px; background:#ffffff; border:1px solid #d7dfeb; border-radius:9px; gridline-color:#edf1f6; color:#1f2937; }
        QHeaderView::section { background:#f8fafc; color:#1f2937; border:0; border-bottom:1px solid #d7dfeb; padding:8px 10px; font-size:12px; font-weight:900; }
        QFrame#permissionFooter { background:#fbfdff; border-top:1px solid #d7dfeb; min-height:66px; max-height:66px; }
        QPushButton { background:#ffffff; border:1px solid #d7dfeb; border-radius:8px; color:#1f2937; font-size:12px; font-weight:900; padding:8px 14px; }
        QPushButton:hover { background:#f8fafc; }
        QPushButton#primaryBtn { background:#1457d9; border-color:#1457d9; color:#ffffff; min-width:104px; }
        QPushButton#primaryBtn:hover { background:#0f48b8; }
        QPushButton#resetBtn { min-width:152px; }
        """

    def _switch_style(self) -> str:
        color = self._active_color()
        return f"""
        QCheckBox {{ background:transparent; spacing:0; }}
        QCheckBox::indicator {{ width:38px; height:21px; border-radius:10px; background:#cbd5e1; border:0; }}
        QCheckBox::indicator:checked {{ background:{color}; }}
        """

    def _permission_rows(self) -> list[tuple[str, str | None, str | None, str | None]]:
        rows: list[tuple[str, str | None, str | None, str | None]] = []
        for category, permissions in auth.PERMISSION_GROUPS:
            rows.append((category, None, None, None))
            for code, display, desc in permissions:
                rows.append((category, code, display, desc))
        return rows

    def set_active_role(self, role_id: int) -> None:
        if int(role_id) not in self.role_by_id:
            return
        self.active_role_id = int(role_id)
        active_role = self._active_role()
        active_name = self._active_role_name()
        active_color = self._active_color()
        for rid, btn in self.role_tabs.items():
            btn.setProperty("active", "true" if int(rid) == int(role_id) else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)
        display_name = str(active_role.get("display_name") or active_name)
        self.selected_role_label.setText(f"Seçili rol: <b><font color='{active_color}'>{display_name}</font></b>")
        self.refresh_permissions()

    def refresh_permissions(self) -> None:
        role_map = auth.get_role_permission_map(self.db_or_path)
        permissions_for_role = role_map.get(int(self.active_role_id), {})
        rows = self._permission_rows()
        self.checkboxes.clear()
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Yetki / İşlem", "Açıklama", "Durum"])
        for row_index, (category, code, display, desc) in enumerate(rows):
            if code is None:
                item = QTableWidgetItem(f"▼  {category}")
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(Qt.GlobalColor.transparent)
                font = item.font(); font.setBold(True); item.setFont(font)
                self.table.setItem(row_index, 0, item)
                self.table.setSpan(row_index, 0, 1, 3)
                self.table.setRowHeight(row_index, 34)
                continue
            name_item = QTableWidgetItem(str(display or code))
            desc_item = QTableWidgetItem(str(desc or ""))
            for item in (name_item, desc_item):
                item.setFlags(Qt.ItemIsEnabled)
            font = name_item.font(); font.setBold(True); name_item.setFont(font)
            self.table.setItem(row_index, 0, name_item)
            self.table.setItem(row_index, 1, desc_item)
            box = QCheckBox()
            box.setStyleSheet(self._switch_style())
            box.setChecked(bool(permissions_for_role.get(str(code), False)))
            wrapper = QWidget()
            layout = QHBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(box, 0, Qt.AlignCenter)
            self.table.setCellWidget(row_index, 2, wrapper)
            self.checkboxes[str(code)] = box
            self.table.setRowHeight(row_index, 44)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)

    def _collect_active_permissions(self) -> dict[int, dict[str, bool]]:
        return {int(self.active_role_id): {code: bool(box.isChecked()) for code, box in self.checkboxes.items()}}

    def _refresh_parent_permissions(self) -> None:
        if self.current_user is not None:
            refreshed = auth.enrich_staff_permissions(self.db_or_path, self.current_user)
            if refreshed:
                self.current_user.update(refreshed)
                auth.current_staff = self.current_user
        if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
            self.parent()._refresh_permission_actions()

    def save(self):
        try:
            auth.set_role_permissions_bulk(self.db_or_path, self.current_user, self._collect_active_permissions())
            self._refresh_parent_permissions()
            QMessageBox.information(self, "Yetki Yönetimi", "Yetkiler kaydedildi.")
            self.accept()
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))
            self.refresh_permissions()

    def restore_defaults(self):
        answer = QMessageBox.question(
            self,
            "Varsayılanlara Dön",
            "Seçili rolün yetkileri varsayılan değerlere döndürülecek. Devam edilsin mi?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            auth.reset_role_permissions_to_default(self.db_or_path, self.current_user, int(self.active_role_id))
            self.refresh_permissions()
            self._refresh_parent_permissions()
            QMessageBox.information(self, "Yetki Yönetimi", "Varsayılan yetkiler geri yüklendi.")
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))
            self.refresh_permissions()
