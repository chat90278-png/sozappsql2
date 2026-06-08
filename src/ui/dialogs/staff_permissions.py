from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src import auth
from src.ui.theme import STYLE

ROLE_ORDER = ["admin", "manager", "personnel", "viewer"]
ROLE_COLORS = {
    "admin": "#1457d9",
    "manager": "#22a447",
    "personnel": "#f59e0b",
    "viewer": "#7c3aed",
}
VISIBLE_PERMISSION_GROUPS = [
    ("Sözleşme İşlemleri", ["view_contracts", "create_contracts", "edit_contracts", "delete_contracts", "export_data"]),
    ("SQL / Terminal", ["open_sql_panel", "sql_read", "sql_write", "terminal_full_access"]),
    ("Personel Yönetimi", ["manage_staff", "create_staff", "edit_staff", "manage_roles", "change_staff_roles", "reset_staff_passwords"]),
    ("Diğer", ["view_action_history", "access_settings", "access_database_tools", "lock_documents", "unlock_own_documents", "unlock_all_documents"]),
]


class StaffPermissionsDialog(QDialog):
    permissions_saved = Signal()

    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None, initial_tab: str = "staffRoles"):
        super().__init__(parent)
        if initial_tab == "rolePermissions":
            auth.require_permission(current_user, "manage_roles", db_or_path)
        else:
            auth.require_permission(current_user, "manage_staff", db_or_path)
        self.db_or_path = db_or_path
        self.current_user = current_user
        self.roles: list[dict[str, Any]] = []
        self.staff_rows: list[dict[str, Any]] = []
        self.selected_staff_id: Optional[int] = None
        self.active_role_id: Optional[int] = None
        self.active_role_name = "manager"
        self.permission_checks: dict[str, QCheckBox] = {}
        self.setWindowTitle("Kullanıcı ve Yetki Yönetimi")
        self.resize(1020, 720)
        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        self.refresh_all()
        if initial_tab == "rolePermissions":
            self.tabs.setCurrentWidget(self.role_tab)
        else:
            self.tabs.setCurrentWidget(self.staff_tab)
        self._sync_footer()

    def _local_style(self) -> str:
        return """
        QDialog { background:#eef2f7; }
        QFrame#panelCard { background:#ffffff; border:1px solid #d7dfeb; border-radius:10px; }
        QLabel#mainTitle { color:#0f172a; font-size:15px; font-weight:900; }
        QLabel#infoBox { background:#f4f8ff; border:1px solid #dce9ff; border-radius:8px; color:#244a84; padding:8px 10px; font-size:12px; }
        QLabel#panelTitle { color:#111827; font-size:13px; font-weight:900; padding:8px 10px; }
        QLabel#formTitle { color:#111827; font-size:14px; font-weight:900; }
        QLabel#noteBox { background:#f8fafc; border:1px dashed #d7dfeb; border-radius:8px; color:#64748b; padding:9px; font-size:11px; }
        QTableWidget { background:#ffffff; border:1px solid #d7dfeb; border-radius:8px; gridline-color:#edf1f6; selection-background-color:#eef6ff; }
        QHeaderView::section { background:#fbfdff; color:#111827; border:0; border-bottom:1px solid #d7dfeb; padding:8px; font-weight:900; }
        QPushButton { background:#ffffff; border:1px solid #d7dfeb; border-radius:8px; padding:7px 12px; color:#1f2937; font-weight:900; }
        QPushButton:hover { background:#f8fafc; }
        QPushButton#primaryBtn { background:#1457d9; border-color:#1457d9; color:white; }
        QPushButton#linkBtn { background:transparent; border:0; color:#1457d9; }
        QPushButton#roleTab { background:#ffffff; border:0; border-bottom:3px solid transparent; border-radius:0; padding:12px; }
        QPushButton#roleTab[active='true'] { font-weight:900; }
        QLabel#selectedRoleBox { background:#fbfdff; border:1px dashed #d7dfeb; border-radius:8px; padding:8px 10px; }
        QLineEdit, QComboBox { background:#ffffff; border:1px solid #d7dfeb; border-radius:8px; padding:6px 8px; min-height:24px; }
        QLineEdit:focus, QComboBox:focus { border-color:#1457d9; }
        QTabWidget::pane { border:0; }
        QTabBar::tab { background:transparent; padding:12px 18px; font-weight:900; color:#475569; }
        QTabBar::tab:selected { background:#ffffff; color:#1457d9; border:1px solid #d7dfeb; border-bottom:0; border-top-left-radius:8px; border-top-right-radius:8px; }
        """

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(10)
        header = QHBoxLayout()
        icon = QLabel("🛡")
        icon.setStyleSheet("background:#f2f6ff;border:1px solid #dbe8ff;border-radius:7px;padding:3px 6px;color:#1457d9;")
        title = QLabel("Kullanıcı ve Yetki Yönetimi"); title.setObjectName("mainTitle")
        header.addWidget(icon); header.addWidget(title); header.addStretch(1)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.staff_tab = QWidget(); self.role_tab = QWidget()
        self.tabs.addTab(self.staff_tab, "Personel Rolleri")
        self.tabs.addTab(self.role_tab, "Rol Yetkileri")
        self.tabs.currentChanged.connect(self._sync_footer)
        root.addWidget(self.tabs, 1)
        self._build_staff_tab()
        self._build_role_tab()

        footer = QHBoxLayout()
        self.restore_btn = QPushButton("↺ Varsayılanlara Dön")
        self.restore_btn.clicked.connect(self.restore_selected_role_defaults)
        footer.addWidget(self.restore_btn)
        footer.addStretch(1)
        self.save_message = QLabel("Yetkiler kaydedildi.")
        self.save_message.setStyleSheet("color:#22a447;font-weight:900;")
        self.save_message.hide()
        footer.addWidget(self.save_message)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_role_btn = QPushButton("💾 Kaydet")
        self.save_role_btn.setObjectName("primaryBtn")
        self.save_role_btn.clicked.connect(self.save_selected_role_permissions)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.accept)
        footer.addWidget(self.cancel_btn); footer.addWidget(self.save_role_btn); footer.addWidget(self.close_btn)
        root.addLayout(footer)

    def _build_staff_tab(self) -> None:
        lay = QVBoxLayout(self.staff_tab)
        lay.setContentsMargins(0, 12, 0, 0)
        info = QLabel("ℹ  Bu bölümde personelleri görüntüleyebilir ve hangi kullanıcının hangi role sahip olacağını belirleyebilirsiniz.")
        info.setObjectName("infoBox"); lay.addWidget(info)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)

        left = QFrame(); left.setObjectName("panelCard")
        left_l = QVBoxLayout(left); left_l.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout(); top.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel("Personel Listesi"); lbl.setObjectName("panelTitle")
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Personel veya cihaz ara...")
        self.search_edit.textChanged.connect(self.refresh_staff_table)
        self.new_staff_btn = QPushButton("+ Yeni Personel"); self.new_staff_btn.clicked.connect(self.start_new_staff)
        top.addWidget(lbl); top.addStretch(1); top.addWidget(self.search_edit); top.addWidget(self.new_staff_btn)
        left_l.addLayout(top)
        self.staff_table = QTableWidget(0, 6)
        self.staff_table.setHorizontalHeaderLabels(["Ad Soyad", "Cihaz Adı", "Rol", "Durum", "Son Giriş", "İşlem"])
        self.staff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.staff_table.verticalHeader().hide()
        self.staff_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.staff_table.cellClicked.connect(lambda row, _col: self.select_staff_from_row(row))
        left_l.addWidget(self.staff_table, 1)
        split.addWidget(left)

        right = QFrame(); right.setObjectName("panelCard")
        right_l = QVBoxLayout(right); right_l.setContentsMargins(14, 12, 14, 14)
        ptitle = QLabel("Personel Düzenleme"); ptitle.setObjectName("panelTitle"); right_l.addWidget(ptitle)
        self.form_title = QLabel(""); self.form_title.setObjectName("formTitle"); right_l.addWidget(self.form_title)
        form = QFormLayout(); form.setLabelAlignment(Qt.AlignLeft)
        self.full_name_input = QLineEdit()
        self.device_name_input = QLineEdit()
        self.password_input = QLineEdit(); self.password_input.setEchoMode(QLineEdit.Password); self.password_input.setPlaceholderText("Yeni personel için şifre")
        self.role_select = QComboBox()
        self.status_select = QComboBox(); self.status_select.addItem("Aktif", 1); self.status_select.addItem("Pasif", 0)
        form.addRow("Ad Soyad", self.full_name_input)
        form.addRow("Cihaz Adı", self.device_name_input)
        self.password_label = QLabel("Şifre")
        form.addRow(self.password_label, self.password_input)
        form.addRow("Rol", self.role_select)
        form.addRow("Durum", self.status_select)
        right_l.addLayout(form)
        buttons = QHBoxLayout()
        self.reset_password_btn = QPushButton("Şifre Sıfırla"); self.reset_password_btn.clicked.connect(self.reset_password)
        self.save_staff_btn = QPushButton("💾 Kaydet"); self.save_staff_btn.setObjectName("primaryBtn"); self.save_staff_btn.clicked.connect(self.save_staff)
        buttons.addWidget(self.reset_password_btn); buttons.addWidget(self.save_staff_btn)
        right_l.addLayout(buttons)
        note = QLabel("Rol değişikliği kullanıcının uygulamada görebileceği menüleri ve yapabileceği işlemleri doğrudan etkiler.\nAktif/Pasif durumu bu ekrandaki durum alanından yönetilir.")
        note.setObjectName("noteBox"); note.setWordWrap(True); right_l.addWidget(note)
        right_l.addStretch(1)
        split.addWidget(right)
        split.setSizes([680, 320])

    def _build_role_tab(self) -> None:
        lay = QVBoxLayout(self.role_tab)
        lay.setContentsMargins(0, 12, 0, 0)
        box = QFrame(); box.setObjectName("panelCard")
        box_l = QVBoxLayout(box); box_l.setContentsMargins(0, 0, 0, 0); box_l.setSpacing(0)
        self.role_button_layout = QHBoxLayout(); self.role_button_layout.setContentsMargins(8, 0, 8, 0); self.role_button_layout.setSpacing(0)
        box_l.addLayout(self.role_button_layout)
        inner = QVBoxLayout(); inner.setContentsMargins(14, 12, 14, 14); inner.setSpacing(10)
        info = QLabel("ℹ  Rol seçerek ilgili rolün modül ve işlem yetkilerini düzenleyebilirsiniz.")
        info.setObjectName("infoBox"); inner.addWidget(info)
        self.selected_role_label = QLabel("Seçili rol: Yönetici"); self.selected_role_label.setObjectName("selectedRoleBox")
        inner.addWidget(self.selected_role_label)
        self.permission_table = QTableWidget(0, 3)
        self.permission_table.setHorizontalHeaderLabels(["Yetki / İşlem", "Açıklama", "Durum"])
        self.permission_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.permission_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.permission_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.permission_table.verticalHeader().hide()
        inner.addWidget(self.permission_table, 1)
        box_l.addLayout(inner)
        lay.addWidget(box, 1)

    def _sync_footer(self) -> None:
        role_page = self.tabs.currentWidget() is self.role_tab
        self.restore_btn.setVisible(role_page)
        self.cancel_btn.setVisible(role_page)
        self.save_role_btn.setVisible(role_page)
        self.save_message.setVisible(False)
        self.close_btn.setVisible(not role_page)

    def _has(self, code: str) -> bool:
        return auth.has_permission(self.current_user, code, self.db_or_path)

    def refresh_all(self) -> None:
        self.roles = sorted(auth.list_roles(self.db_or_path), key=lambda r: ROLE_ORDER.index(r["name"]) if r.get("name") in ROLE_ORDER else 99)
        self._populate_role_select()
        self.refresh_staff_table()
        self._populate_role_buttons()
        if self.active_role_id is None and self.roles:
            manager = next((r for r in self.roles if r.get("name") == "manager"), self.roles[0])
            self.set_active_role(int(manager["id"]))
        else:
            self.render_permissions()
        self._apply_staff_permissions_to_form()

    def _populate_role_select(self) -> None:
        current = self.role_select.currentData()
        self.role_select.clear()
        for role in self.roles:
            self.role_select.addItem(str(role["display_name"]), int(role["id"]))
        if current is not None:
            idx = self.role_select.findData(int(current))
            if idx >= 0:
                self.role_select.setCurrentIndex(idx)

    def refresh_staff_table(self) -> None:
        if not self._has("manage_staff"):
            self.staff_rows = []
            self.staff_table.setRowCount(0)
            return
        query = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
        rows = auth.list_staff(self.db_or_path)
        if query:
            rows = [r for r in rows if query in str(r.get("full_name") or "").casefold() or query in str(r.get("device_name") or "").casefold()]
        self.staff_rows = rows
        self.staff_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            role_name = str(row.get("role_name") or row.get("role") or "personnel")
            active = int(row.get("is_active") if row.get("is_active") is not None else 1) == 1
            values = [
                str(row.get("full_name") or ""),
                str(row.get("device_name") or ""),
                str(row.get("role_display_name") or auth.ROLE_LABELS.get(role_name, role_name)),
                "Aktif" if active else "Pasif",
                str(row.get("last_login_at") or ""),
                "Düzenle",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.UserRole, int(row.get("id") or 0))
                if c == 2:
                    item.setForeground(Qt.GlobalColor.darkBlue)
                if c == 5:
                    item.setForeground(Qt.GlobalColor.blue)
                self.staff_table.setItem(r, c, item)
        if self.selected_staff_id is None and rows:
            self.selected_staff_id = int(rows[0]["id"])
        self._select_staff_id(self.selected_staff_id)

    def select_staff_from_row(self, row: int) -> None:
        item = self.staff_table.item(row, 0)
        if item:
            self._select_staff_id(int(item.data(Qt.UserRole)))

    def _select_staff_id(self, staff_id: Optional[int]) -> None:
        self.selected_staff_id = staff_id
        row = next((r for r in auth.list_staff(self.db_or_path) if int(r["id"]) == int(staff_id or 0)), None)
        self._load_staff_form(row)
        for r in range(self.staff_table.rowCount()):
            item = self.staff_table.item(r, 0)
            if item and int(item.data(Qt.UserRole)) == int(staff_id or 0):
                self.staff_table.selectRow(r)
                break

    def _load_staff_form(self, row: Optional[dict[str, Any]]) -> None:
        is_new = row is None
        self.form_title.setText("Yeni Personel" if is_new else str(row.get("full_name") or ""))
        self.full_name_input.setText("" if is_new else str(row.get("full_name") or ""))
        self.device_name_input.setText("" if is_new else str(row.get("device_name") or ""))
        self.password_input.setText("")
        self.password_input.setVisible(is_new)
        self.password_label.setVisible(is_new)
        self.reset_password_btn.setVisible(not is_new)
        if row and row.get("role_id") is not None:
            idx = self.role_select.findData(int(row["role_id"]))
            if idx >= 0:
                self.role_select.setCurrentIndex(idx)
        active_idx = self.status_select.findData(int(row.get("is_active") if row and row.get("is_active") is not None else 1))
        self.status_select.setCurrentIndex(max(0, active_idx))
        self._apply_staff_permissions_to_form()

    def _apply_staff_permissions_to_form(self) -> None:
        can_create = self._has("create_staff") or self._has("manage_staff")
        can_edit = self._has("edit_staff") or self._has("manage_staff")
        can_change_role = self._has("change_staff_roles") or self._has("manage_roles")
        can_change_active = self._has("manage_staff")
        self.new_staff_btn.setEnabled(can_create)
        self.full_name_input.setEnabled(can_edit or self.selected_staff_id is None)
        self.device_name_input.setEnabled(can_edit or self.selected_staff_id is None)
        self.role_select.setEnabled(can_change_role)
        self.status_select.setEnabled(can_change_active)
        self.reset_password_btn.setEnabled(self._has("reset_staff_passwords"))
        self.save_staff_btn.setEnabled(can_edit or can_create or can_change_role or can_change_active)

    def start_new_staff(self) -> None:
        if not (self._has("create_staff") or self._has("manage_staff")):
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
            return
        self.selected_staff_id = None
        self.staff_table.clearSelection()
        self._load_staff_form(None)

    def save_staff(self) -> None:
        full_name = self.full_name_input.text().strip()
        device_name = self.device_name_input.text().strip()
        if not full_name or not device_name:
            QMessageBox.warning(self, "Eksik bilgi", "Ad Soyad ve Cihaz Adı zorunludur.")
            return
        try:
            if self.selected_staff_id is None:
                password = self.password_input.text()
                if not password:
                    QMessageBox.warning(self, "Eksik bilgi", "Yeni personel için şifre zorunludur.")
                    return
                auth.create_staff_by_admin(
                    self.db_or_path,
                    self.current_user,
                    device_name,
                    full_name,
                    password,
                    int(self.role_select.currentData()),
                    int(self.status_select.currentData()),
                )
            else:
                row = next((r for r in auth.list_staff(self.db_or_path) if int(r["id"]) == int(self.selected_staff_id)), None)
                kwargs: dict[str, Any] = {}
                if self._has("edit_staff") or self._has("manage_staff"):
                    kwargs["full_name"] = full_name
                    kwargs["device_name"] = device_name
                if (self._has("change_staff_roles") or self._has("manage_roles")) and row and int(row.get("role_id") or 0) != int(self.role_select.currentData()):
                    kwargs["role_id"] = int(self.role_select.currentData())
                if self._has("manage_staff") and row and int(row.get("is_active") if row.get("is_active") is not None else 1) != int(self.status_select.currentData()):
                    kwargs["is_active"] = int(self.status_select.currentData())
                auth.update_staff_record(self.db_or_path, self.current_user, int(self.selected_staff_id), **kwargs)
            self.refresh_all()
            QMessageBox.information(self, "Kullanıcı ve Yetki Yönetimi", "Personel bilgileri kaydedildi.")
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Personel Kaydet", str(exc))

    def reset_password(self) -> None:
        if self.selected_staff_id is None:
            return
        if not self._has("reset_staff_passwords"):
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
            return
        dlg = QDialog(self); dlg.setWindowTitle("Şifre Sıfırla")
        form = QFormLayout(dlg)
        pwd = QLineEdit(); pwd.setEchoMode(QLineEdit.Password)
        form.addRow("Yeni şifre", pwd)
        row = QHBoxLayout(); cancel = QPushButton("İptal"); save = QPushButton("Kaydet"); save.setObjectName("primaryBtn")
        cancel.clicked.connect(dlg.reject); save.clicked.connect(dlg.accept)
        row.addStretch(1); row.addWidget(cancel); row.addWidget(save); form.addRow(row)
        if dlg.exec() != QDialog.Accepted:
            return
        if not pwd.text():
            QMessageBox.warning(self, "Eksik bilgi", "Şifre boş olamaz.")
            return
        try:
            auth.reset_staff_password(self.db_or_path, self.current_user, int(self.selected_staff_id), pwd.text())
            QMessageBox.information(self, "Şifre Sıfırla", "Şifre güncellendi.")
        except Exception as exc:
            QMessageBox.warning(self, "Şifre Sıfırla", str(exc))

    def _populate_role_buttons(self) -> None:
        while self.role_button_layout.count():
            item = self.role_button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for role in self.roles:
            btn = QPushButton(f"♟  {role['display_name']}")
            btn.setObjectName("roleTab")
            btn.clicked.connect(lambda _=False, rid=int(role["id"]): self.set_active_role(rid))
            self.role_button_layout.addWidget(btn, 1)
        self._update_role_button_styles()

    def set_active_role(self, role_id: int) -> None:
        role = next((r for r in self.roles if int(r["id"]) == int(role_id)), None)
        if not role:
            return
        self.active_role_id = int(role_id)
        self.active_role_name = str(role.get("name") or "")
        self._update_role_button_styles()
        self.render_permissions()

    def _update_role_button_styles(self) -> None:
        for i in range(self.role_button_layout.count()):
            btn = self.role_button_layout.itemAt(i).widget()
            role = self.roles[i] if i < len(self.roles) else None
            if not btn or not role:
                continue
            active = int(role["id"]) == int(self.active_role_id or 0)
            name = str(role.get("name") or "")
            color = ROLE_COLORS.get(name, "#1457d9")
            btn.setProperty("active", "true" if active else "false")
            btn.setStyleSheet(f"QPushButton#roleTab {{ color:{color if active else '#1f2937'}; border-bottom:3px solid {color if active else 'transparent'}; }}")
            btn.style().unpolish(btn); btn.style().polish(btn)

    def _permission_catalog(self) -> dict[str, tuple[str, str, str]]:
        return {code: (category, display, desc) for category, permissions in auth.PERMISSION_GROUPS for code, display, desc in permissions}

    def render_permissions(self) -> None:
        if self.active_role_id is None:
            return
        catalog = self._permission_catalog()
        role_map = auth.get_role_permission_map(self.db_or_path).get(int(self.active_role_id), {})
        role = next((r for r in self.roles if int(r["id"]) == int(self.active_role_id)), None)
        role_display = str(role.get("display_name") if role else "")
        color = ROLE_COLORS.get(str(role.get("name") if role else ""), "#1457d9")
        self.selected_role_label.setText(f"Seçili rol: {role_display}")
        self.selected_role_label.setStyleSheet(f"QLabel#selectedRoleBox {{ background:#fbfdff; border:1px dashed #d7dfeb; border-radius:8px; padding:8px 10px; color:{color}; font-weight:900; }}")
        rows: list[tuple[Optional[str], Optional[str], str, str]] = []
        for group, codes in VISIBLE_PERMISSION_GROUPS:
            rows.append((group, None, "", ""))
            for code in codes:
                _cat, display, desc = catalog.get(code, (group, code, ""))
                rows.append((None, code, display, desc))
        self.permission_checks.clear()
        self.permission_table.setRowCount(len(rows))
        for r, (group, code, display, desc) in enumerate(rows):
            if group is not None:
                item = QTableWidgetItem(f"▼ {group}")
                item.setFlags(Qt.ItemIsEnabled)
                font = item.font(); font.setBold(True); item.setFont(font)
                self.permission_table.setItem(r, 0, item)
                self.permission_table.setSpan(r, 0, 1, 3)
                continue
            name_item = QTableWidgetItem(display)
            desc_item = QTableWidgetItem(desc)
            name_item.setFlags(Qt.ItemIsEnabled); desc_item.setFlags(Qt.ItemIsEnabled)
            self.permission_table.setItem(r, 0, name_item)
            self.permission_table.setItem(r, 1, desc_item)
            box = QCheckBox()
            box.setChecked(bool(role_map.get(str(code), False)))
            wrap = QWidget(); lay = QHBoxLayout(wrap); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(box, 0, Qt.AlignCenter)
            self.permission_table.setCellWidget(r, 2, wrap)
            self.permission_checks[str(code)] = box
        self.permission_table.resizeRowsToContents()

    def _selected_role_permissions(self) -> dict[str, bool]:
        return {code: box.isChecked() for code, box in self.permission_checks.items()}

    def save_selected_role_permissions(self) -> None:
        if self.active_role_id is None:
            return
        try:
            auth.set_role_permissions_bulk(self.db_or_path, self.current_user, {int(self.active_role_id): self._selected_role_permissions()})
            if self.current_user is not None:
                refreshed = auth.enrich_staff_permissions(self.db_or_path, self.current_user)
                if refreshed:
                    self.current_user.update(refreshed)
                    auth.current_staff = self.current_user
            self.permissions_saved.emit()
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
            self.save_message.show()
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))

    def restore_selected_role_defaults(self) -> None:
        if self.active_role_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Varsayılanlara Dön",
            "Seçili rolün yetkileri varsayılan değerlere döndürülecek. Devam edilsin mi?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            role = next((r for r in self.roles if int(r["id"]) == int(self.active_role_id)), None)
            if not role:
                return
            defaults = auth.DEFAULT_ROLE_PERMISSIONS.get(str(role["name"]), set())
            codes = list(self.permission_checks.keys())
            auth.set_role_permissions_bulk(self.db_or_path, self.current_user, {int(self.active_role_id): {code: code in defaults for code in codes}})
            self.render_permissions()
            self.permissions_saved.emit()
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
        except Exception as exc:
            QMessageBox.warning(self, "Varsayılanlara Dön", str(exc))


# Backward-compatible names route old imports/callbacks to the single dialog.
class StaffManagementDialog(StaffPermissionsDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(db_or_path, current_user, parent, initial_tab="staffRoles")


class RolePermissionsDialog(StaffPermissionsDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(db_or_path, current_user, parent, initial_tab="rolePermissions")
