from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QBrush, QPainter, QPen, QPalette
from PySide6.QtWidgets import (
    QAbstractButton,
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
    "admin":     "#1457d9",
    "manager":   "#22a447",
    "personnel": "#f59e0b",
    "viewer":    "#7c3aed",
}
ROLE_BG_COLORS = {
    "admin":     "#eaf1ff",
    "manager":   "#eaf8ef",
    "personnel": "#fff7e8",
    "viewer":    "#f3eaff",
}
VISIBLE_PERMISSION_GROUPS = [
    ("Sözleşme İşlemleri", ["view_contracts", "create_contracts", "edit_contracts", "delete_contracts", "export_data"]),
    ("SQL / Terminal",     ["open_sql_panel", "sql_read", "sql_write", "terminal_full_access"]),
    ("Personel Yönetimi",  ["manage_staff", "create_staff", "edit_staff", "manage_roles", "change_staff_roles", "reset_staff_passwords"]),
    ("Diğer",              ["view_action_history", "access_settings", "access_database_tools", "lock_documents", "unlock_own_documents", "unlock_all_documents"]),
]


# ── Toggle Switch ─────────────────────────────────────────────────────────────
class ToggleSwitch(QAbstractButton):
    def __init__(self, color: str = "#22a447", parent=None):
        super().__init__(parent)
        self._color = color
        self.setCheckable(True)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color if self.isChecked() else "#cbd5e1"))
        p.drawRoundedRect(0, 0, w, h, r, r)
        kd = h - 4
        kx = w - kd - 2 if self.isChecked() else 2
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#00000015"), 1))
        p.drawEllipse(int(kx), 2, int(kd), int(kd))
        p.end()

    def sizeHint(self): return QSize(40, 22)


# ── Badge Label ───────────────────────────────────────────────────────────────
class BadgeLabel(QLabel):
    def __init__(self, text: str, fg: str, bg: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"QLabel {{ color:{fg}; background:{bg}; border-radius:10px; "
            f"padding:2px 10px; font-size:11px; font-weight:900; border:none; }}"
        )
        self.setFixedHeight(22)


# ── Main Dialog ───────────────────────────────────────────────────────────────
class StaffPermissionsDialog(QDialog):
    permissions_saved = Signal()

    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]],
                 parent=None, initial_tab: str = "staffRoles"):
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
        self.permission_toggles: dict[str, ToggleSwitch] = {}
        self._group_collapsed: dict[int, bool] = {}
        self._perm_rows: list[tuple] = []

        self.setWindowTitle("Kullanıcı ve Yetki Yönetimi - STS")
        self.resize(980, 760)
        self.setStyleSheet(self._local_style())
        self._build()
        self.refresh_all()
        if initial_tab == "rolePermissions":
            self.tabs.setCurrentWidget(self.role_tab)
        self._sync_footer()

    def _local_style(self) -> str:
        return """
        /* ── Dialog base ── */
        QDialog { background: #eef2f7; font-family: 'Segoe UI', Arial, sans-serif; }

        /* ── Tab widget ── */
        QTabWidget::pane  { border: none; margin-top: -1px; }
        QTabBar::tab {
            background: transparent; padding: 10px 20px;
            font-weight: 900; color: #64748b; font-size: 13px;
            border: 1px solid transparent; border-bottom: none;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #ffffff; color: #1457d9;
            border-color: #d7dfeb; border-bottom: none;
        }
        QTabBar::tab:hover:!selected { background: #f1f5f9; color: #374151; }

        /* ── Panel cards ── */
        QFrame#panelCard {
            background: #ffffff; border: 1px solid #d7dfeb; border-radius: 10px;
        }

        /* ── Info box ── */
        QLabel#infoBox {
            background: #f4f8ff; border: 1px solid #dce9ff; border-radius: 8px;
            color: #244a84; padding: 8px 12px; font-size: 12px;
        }

        /* ── Table — critical: force white background everywhere ── */
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #ffffff;
            border: 1px solid #d7dfeb; border-radius: 8px;
            gridline-color: transparent;
            selection-background-color: #dbeafe;
            selection-color: #1e40af;
            outline: none;
        }
        QTableWidget::item {
            background: #ffffff;
            border-bottom: 1px solid #f1f5f9;
            padding: 4px 8px;
        }
        QTableWidget::item:selected {
            background: #dbeafe;
            color: #1e40af;
        }
        QTableWidget::item:hover {
            background: #f0f7ff;
        }
        QHeaderView::section {
            background: #f8fafc; color: #374151;
            border: none; border-bottom: 1px solid #d7dfeb;
            padding: 8px 10px; font-weight: 900; font-size: 12px;
        }
        QHeaderView { background: #f8fafc; }

        /* ── Buttons ── */
        QPushButton {
            background: #ffffff; border: 1px solid #d0d9ea; border-radius: 8px;
            padding: 8px 16px; color: #1f2937; font-weight: 700; font-size: 12px;
            min-height: 32px;
        }
        QPushButton:hover   { background: #f1f5f9; border-color: #b8c5d9; }
        QPushButton:pressed { background: #e5eaf2; }
        QPushButton#primaryBtn {
            background: #1457d9; border-color: #1457d9; color: #ffffff;
        }
        QPushButton#primaryBtn:hover   { background: #1248b8; }
        QPushButton#primaryBtn:pressed { background: #0f3d9e; }
        QPushButton#primaryBtn:disabled { background: #93b3f0; border-color: #93b3f0; }
        QPushButton#linkBtn {
            background: transparent; border: none; color: #1457d9;
            font-weight: 900; padding: 2px 6px; min-height: 0;
        }
        QPushButton#linkBtn:hover { color: #0f3d9e; text-decoration: underline; }
        QPushButton#roleTab {
            background: #ffffff; border: none;
            border-bottom: 3px solid transparent;
            border-right: 1px solid #e5eaf2;
            border-radius: 0; padding: 14px 12px;
            font-size: 13px; font-weight: 900; min-height: 0;
        }
        QPushButton#roleTab:hover { background: #f8fafc; }

        /* ── Form inputs — VISIBLE borders ── */
        QLineEdit {
            background: #ffffff;
            border: 1.5px solid #c8d4e8;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            color: #111827;
            min-height: 34px;
            selection-background-color: #dbeafe;
        }
        QLineEdit:focus   { border-color: #1457d9; background: #fafcff; }
        QLineEdit:hover   { border-color: #a0b4ce; }
        QLineEdit:disabled { background: #f8fafc; color: #94a3b8; border-color: #e2e8f0; }

        QComboBox {
            background: #ffffff;
            border: 1.5px solid #c8d4e8;
            border-radius: 8px;
            padding: 8px 36px 8px 12px;
            font-size: 13px;
            color: #111827;
            min-height: 34px;
        }
        QComboBox:focus   { border-color: #1457d9; }
        QComboBox:hover   { border-color: #a0b4ce; }
        QComboBox:disabled { background: #f8fafc; color: #94a3b8; }
        QComboBox::drop-down {
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 28px; border: none;
        }
        QComboBox::down-arrow {
            width: 10px; height: 10px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff; border: 1px solid #d0d9ea; border-radius: 6px;
            selection-background-color: #dbeafe; selection-color: #1e40af;
            outline: none; padding: 4px;
        }

        /* ── Role/selected label ── */
        QLabel#selectedRoleBox {
            background: #f8fbff; border: 1px dashed #c8d9f5;
            border-radius: 8px; padding: 8px 14px;
            font-size: 12px; font-weight: 700; color: #475569;
        }

        /* ── Splitter ── */
        QSplitter::handle { background: transparent; width: 10px; }
        """

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # Tabs — NO header title above them
        self.tabs = QTabWidget()
        self.staff_tab = QWidget()
        self.role_tab  = QWidget()
        self.tabs.addTab(self.staff_tab, "Personel Rolleri")
        self.tabs.addTab(self.role_tab,  "Rol Yetkileri")
        self.tabs.currentChanged.connect(self._sync_footer)
        root.addWidget(self.tabs, 1)

        self._build_staff_tab()
        self._build_role_tab()

        # Footer
        ftr = QHBoxLayout()
        self.restore_btn = QPushButton("↺  Varsayılanlara Dön")
        self.restore_btn.clicked.connect(self.restore_selected_role_defaults)
        ftr.addWidget(self.restore_btn)
        ftr.addStretch(1)
        self.save_message = QLabel("✓  Değişiklikler kaydedildi.")
        self.save_message.setStyleSheet("color:#22a447; font-weight:900; font-size:12px;")
        self.save_message.hide()
        ftr.addWidget(self.save_message)
        self.cancel_btn    = QPushButton("İptal")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_role_btn = QPushButton("💾  Kaydet")
        self.save_role_btn.setObjectName("primaryBtn")
        self.save_role_btn.clicked.connect(self.save_selected_role_permissions)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.accept)
        ftr.addWidget(self.cancel_btn)
        ftr.addWidget(self.save_role_btn)
        ftr.addWidget(self.close_btn)
        root.addLayout(ftr)

    # ── Personel Rolleri tab ──────────────────────────────────────────────────
    def _build_staff_tab(self) -> None:
        lay = QVBoxLayout(self.staff_tab)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        info = QLabel("ℹ  Bu bölümde personelleri görüntüleyebilir ve hangi kullanıcının "
                      "hangi role sahip olacağını belirleyebilirsiniz.")
        info.setObjectName("infoBox")
        lay.addWidget(info)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QFrame(); left.setObjectName("panelCard")
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0)

        # Toolbar
        tb_w = QWidget()
        tb_w.setStyleSheet(
            "background: #f8fafc; border-bottom: 1px solid #e5eaf2; "
            "border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        tb = QHBoxLayout(tb_w)
        tb.setContentsMargins(14, 10, 14, 10)
        tb.setSpacing(12)

        lbl = QLabel("Personel Listesi")
        lbl.setStyleSheet(
            "font-size: 13px; font-weight: 900; color: #111827; "
            "background: transparent; border: none;"
        )
        tb.addWidget(lbl)
        tb.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Personel veya cihaz ara...")
        self.search_edit.setFixedSize(190, 34)
        self.search_edit.textChanged.connect(self.refresh_staff_table)
        tb.addWidget(self.search_edit)

        self.new_staff_btn = QPushButton("+ Yeni Personel")
        self.new_staff_btn.setObjectName("primaryBtn")
        self.new_staff_btn.setFixedHeight(34)
        self.new_staff_btn.setCursor(Qt.PointingHandCursor)
        self.new_staff_btn.clicked.connect(self.start_new_staff)
        tb.addWidget(self.new_staff_btn)

        ll.addWidget(tb_w)

        self.staff_table = QTableWidget(0, 6)
        self.staff_table.setHorizontalHeaderLabels(
            ["Ad Soyad", "Cihaz Adı", "Rol", "Durum", "Son Giriş", "İşlem"])
        hdr = self.staff_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setHighlightSections(False)
        self.staff_table.verticalHeader().hide()
        self.staff_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.staff_table.setSelectionMode(QTableWidget.SingleSelection)
        self.staff_table.setShowGrid(False)
        self.staff_table.setAlternatingRowColors(False)
        self.staff_table.setSelectionMode(QTableWidget.NoSelection)
        self.staff_table.setFocusPolicy(Qt.StrongFocus)
        self.staff_table.cellClicked.connect(self._on_staff_cell_clicked)
        ll.addWidget(self.staff_table, 1)
        split.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QFrame(); right.setObjectName("panelCard")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        # Header bar
        rh = QWidget()
        rh.setStyleSheet(
            "background: #f8fafc; border-bottom: 1px solid #e5eaf2; "
            "border-top-left-radius: 10px; border-top-right-radius: 10px;"
        )
        rhl = QHBoxLayout(rh); rhl.setContentsMargins(16, 11, 16, 11)
        rh_lbl = QLabel("Personel Düzenleme")
        rh_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 900; color: #111827; "
            "background: transparent; border: none;"
        )
        rhl.addWidget(rh_lbl)
        rl.addWidget(rh)

        # Form body
        fb = QWidget(); fb.setStyleSheet("background: #ffffff; border: none;")
        fc = QVBoxLayout(fb); fc.setContentsMargins(16, 16, 16, 16); fc.setSpacing(14)

        # Person name
        self.form_title = QLabel("")
        self.form_title.setStyleSheet(
            "font-size: 15px; font-weight: 900; color: #0f172a; "
            "background: transparent; border: none;"
        )
        fc.addWidget(self.form_title)

        # Field builder: small label above input
        def _field(label_text: str, widget: QWidget) -> None:
            vb = QVBoxLayout(); vb.setSpacing(5)
            lb = QLabel(label_text)
            lb.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #64748b; "
                "background: transparent; border: none;"
            )
            vb.addWidget(lb)
            vb.addWidget(widget)
            fc.addLayout(vb)

        self.full_name_input   = QLineEdit()
        self.device_name_input = QLineEdit()
        self.password_input    = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Yeni personel için şifre")
        self.role_select   = QComboBox()
        self.status_select = QComboBox()
        self.status_select.addItem("Aktif", 1)
        self.status_select.addItem("Pasif", 0)

        _field("Ad Soyad",  self.full_name_input)
        _field("Cihaz Adı", self.device_name_input)
        _field("Rol",       self.role_select)
        _field("Durum",     self.status_select)

        # Password (hidden until new staff)
        self.password_label = QLabel("Şifre")
        self.password_label.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #64748b; "
            "background: transparent; border: none;"
        )
        pw_vb = QVBoxLayout(); pw_vb.setSpacing(5)
        pw_vb.addWidget(self.password_label)
        pw_vb.addWidget(self.password_input)
        fc.addLayout(pw_vb)

        # Buttons row
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.reset_password_btn = QPushButton("Şifre Sıfırla")
        self.reset_password_btn.setFixedHeight(36)
        self.reset_password_btn.clicked.connect(self.reset_password)
        self.save_staff_btn = QPushButton("🔒  Kaydet")
        self.save_staff_btn.setObjectName("primaryBtn")
        self.save_staff_btn.setFixedHeight(36)
        self.save_staff_btn.clicked.connect(self.save_staff)
        btn_row.addWidget(self.reset_password_btn)
        btn_row.addWidget(self.save_staff_btn)
        fc.addLayout(btn_row)
        fc.addStretch(1)

        rl.addWidget(fb, 1)
        split.addWidget(right)
        split.setSizes([570, 330])

    # ── Rol Yetkileri tab ─────────────────────────────────────────────────────
    def _build_role_tab(self) -> None:
        lay = QVBoxLayout(self.role_tab)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        box = QFrame(); box.setObjectName("panelCard")
        bl  = QVBoxLayout(box); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)

        self.role_button_layout = QHBoxLayout()
        self.role_button_layout.setContentsMargins(0, 0, 0, 0)
        self.role_button_layout.setSpacing(0)
        bl.addLayout(self.role_button_layout)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #e5eaf2;"); bl.addWidget(sep)

        inner = QVBoxLayout(); inner.setContentsMargins(14, 10, 14, 12); inner.setSpacing(8)

        info = QLabel("ℹ  Rol seçerek ilgili rolün modül ve işlem yetkilerini düzenleyebilirsiniz.")
        info.setObjectName("infoBox"); inner.addWidget(info)

        self.selected_role_label = QLabel("Seçili rol: Yönetici")
        self.selected_role_label.setObjectName("selectedRoleBox")
        inner.addWidget(self.selected_role_label)

        self.permission_table = QTableWidget(0, 3)
        self.permission_table.setHorizontalHeaderLabels(["Yetki / İşlem", "Açıklama", "Durum"])
        ph = self.permission_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        ph.setSectionResizeMode(1, QHeaderView.Stretch)
        ph.setSectionResizeMode(2, QHeaderView.Fixed)
        ph.resizeSection(2, 72)
        ph.setHighlightSections(False)
        self.permission_table.verticalHeader().hide()
        self.permission_table.setShowGrid(False)
        self.permission_table.setAlternatingRowColors(False)
        self.permission_table.setSelectionMode(QTableWidget.NoSelection)
        self.permission_table.cellClicked.connect(self._on_perm_cell_clicked)
        inner.addWidget(self.permission_table, 1)

        bl.addLayout(inner)
        lay.addWidget(box, 1)

    # ── Footer sync ───────────────────────────────────────────────────────────
    def _sync_footer(self) -> None:
        on_role = self.tabs.currentWidget() is self.role_tab
        self.restore_btn.setVisible(on_role)
        self.cancel_btn.setVisible(on_role)
        self.save_role_btn.setVisible(on_role)
        self.save_message.setVisible(False)
        self.close_btn.setVisible(not on_role)

    def _has(self, code: str) -> bool:
        return auth.has_permission(self.current_user, code, self.db_or_path)

    # ── Data ──────────────────────────────────────────────────────────────────
    def refresh_all(self) -> None:
        self.roles = sorted(
            auth.list_roles(self.db_or_path),
            key=lambda r: ROLE_ORDER.index(r["name"]) if r.get("name") in ROLE_ORDER else 99,
        )
        self._populate_role_select()
        self.refresh_staff_table()
        self._populate_role_buttons()
        if self.active_role_id is None and self.roles:
            mgr = next((r for r in self.roles if r.get("name") == "manager"), self.roles[0])
            self.set_active_role(int(mgr["id"]))
        else:
            self.render_permissions()
        self._apply_staff_permissions_to_form()

    def _populate_role_select(self) -> None:
        cur = self.role_select.currentData()
        self.role_select.clear()
        for role in self.roles:
            self.role_select.addItem(str(role["display_name"]), int(role["id"]))
        if cur is not None:
            idx = self.role_select.findData(int(cur))
            if idx >= 0:
                self.role_select.setCurrentIndex(idx)

    # ── Staff table ───────────────────────────────────────────────────────────
    def _paint_table_row(self, row_idx: int, selected: bool) -> None:
        """Paint all cells in a row — including widget cells — with correct bg color."""
        bg_sel   = "#dbeafe"   # mavi seçili
        bg_white = "#ffffff"   # normal beyaz
        bg_hover = "#f0f7ff"   # hover
        bg = bg_sel if selected else bg_white

        for c in range(self.staff_table.columnCount()):
            item = self.staff_table.item(row_idx, c)
            if item:
                item.setBackground(QBrush(QColor(bg)))
                if selected:
                    item.setForeground(QBrush(QColor("#1e40af")))
                else:
                    item.setForeground(QBrush(QColor("#111827")))
            w = self.staff_table.cellWidget(row_idx, c)
            if w:
                w.setStyleSheet(f"background: {bg};")
                # also update children
                for child in w.findChildren(QWidget):
                    if not isinstance(child, (QPushButton, QLabel)):
                        child.setStyleSheet(f"background: {bg};")

    def refresh_staff_table(self) -> None:
        if not self._has("manage_staff"):
            self.staff_rows = []
            self.staff_table.setRowCount(0)
            return
        query = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
        rows = auth.list_staff(self.db_or_path)
        if query:
            rows = [r for r in rows if
                    query in str(r.get("full_name") or "").casefold() or
                    query in str(r.get("device_name") or "").casefold()]
        self.staff_rows = rows
        # Disable built-in selection painting — we do it manually
        self.staff_table.setSelectionMode(QTableWidget.NoSelection)
        self.staff_table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            role_name    = str(row.get("role_name") or row.get("role") or "personnel")
            active       = int(row.get("is_active") if row.get("is_active") is not None else 1) == 1
            role_display = str(row.get("role_display_name") or auth.ROLE_LABELS.get(role_name, role_name))
            last_login   = str(row.get("last_login_at") or "")

            def plain_item(text: str, uid: Optional[int] = None) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setBackground(QBrush(QColor("#ffffff")))
                it.setForeground(QBrush(QColor("#111827")))
                if uid is not None:
                    it.setData(Qt.UserRole, uid)
                return it

            # Col 0: Ad Soyad
            self.staff_table.setItem(r, 0, plain_item(str(row.get("full_name") or ""), int(row.get("id") or 0)))
            # Col 1: Cihaz Adı
            self.staff_table.setItem(r, 1, plain_item(str(row.get("device_name") or "")))

            # Col 2: Rol badge
            rc = ROLE_COLORS.get(role_name, "#1457d9")
            rb = ROLE_BG_COLORS.get(role_name, "#eaf1ff")
            rw = QWidget(); rw.setStyleSheet("background: #ffffff;")
            rl2 = QHBoxLayout(rw); rl2.setContentsMargins(6, 4, 6, 4); rl2.setSpacing(0)
            rl2.addWidget(BadgeLabel(role_display, rc, rb))
            rl2.addStretch(1)
            self.staff_table.setCellWidget(r, 2, rw)

            # Col 3: Durum badge
            sw = QWidget(); sw.setStyleSheet("background: #ffffff;")
            sl2 = QHBoxLayout(sw); sl2.setContentsMargins(6, 4, 6, 4); sl2.setSpacing(0)
            sl2.addWidget(BadgeLabel(
                "Aktif" if active else "Pasif",
                "#22a447" if active else "#dc2626",
                "#eaf8ef" if active else "#fee2e2"
            ))
            sl2.addStretch(1)
            self.staff_table.setCellWidget(r, 3, sw)

            # Col 4: Son Giriş
            self.staff_table.setItem(r, 4, plain_item(last_login))

            # Col 5: Düzenle link
            ew = QWidget(); ew.setStyleSheet("background: #ffffff;")
            el2 = QHBoxLayout(ew); el2.setContentsMargins(6, 2, 6, 2)
            eb = QPushButton("Düzenle"); eb.setObjectName("linkBtn")
            eb.setCursor(Qt.PointingHandCursor)
            rid = int(row.get("id") or 0)
            eb.clicked.connect(lambda _=False, _rid=rid: self._select_staff_id(_rid))
            el2.addWidget(eb)
            self.staff_table.setCellWidget(r, 5, ew)

            self.staff_table.setRowHeight(r, 44)

        if self.selected_staff_id is None and rows:
            self.selected_staff_id = int(rows[0]["id"])
        # Paint rows correctly — selected row highlighted, others white
        self._refresh_row_colors()
        # Load form for selected staff
        if self.selected_staff_id is not None:
            row_data = next((r for r in rows if int(r["id"]) == int(self.selected_staff_id)), None)
            self._load_staff_form(row_data)

    def _refresh_row_colors(self) -> None:
        """Repaint every row: selected=blue, others=white."""
        for r in range(self.staff_table.rowCount()):
            item = self.staff_table.item(r, 0)
            if item:
                is_sel = (item.data(Qt.UserRole) == self.selected_staff_id)
                self._paint_table_row(r, is_sel)

    def _on_staff_cell_clicked(self, row: int, col: int) -> None:
        """Handle click on any cell — find staff id from row."""
        item = self.staff_table.item(row, 0)
        if item and item.data(Qt.UserRole) is not None:
            self._select_staff_id(int(item.data(Qt.UserRole)))

    def select_staff_from_row(self, row: int) -> None:
        item = self.staff_table.item(row, 0)
        if item:
            self._select_staff_id(int(item.data(Qt.UserRole)))

    def _select_staff_id(self, staff_id: Optional[int]) -> None:
        self.selected_staff_id = staff_id
        self._refresh_row_colors()
        row_data = next((r for r in auth.list_staff(self.db_or_path)
                         if int(r["id"]) == int(staff_id or 0)), None)
        self._load_staff_form(row_data)

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
        ai = self.status_select.findData(
            int(row.get("is_active") if row and row.get("is_active") is not None else 1))
        self.status_select.setCurrentIndex(max(0, ai))
        self._apply_staff_permissions_to_form()

    def _apply_staff_permissions_to_form(self) -> None:
        can_create = self._has("create_staff") or self._has("manage_staff")
        can_edit   = self._has("edit_staff")   or self._has("manage_staff")
        can_role   = self._has("change_staff_roles") or self._has("manage_roles")
        can_active = self._has("manage_staff")
        self.new_staff_btn.setEnabled(can_create)
        self.full_name_input.setEnabled(can_edit or self.selected_staff_id is None)
        self.device_name_input.setEnabled(can_edit or self.selected_staff_id is None)
        self.role_select.setEnabled(can_role)
        self.status_select.setEnabled(can_active)
        self.reset_password_btn.setEnabled(self._has("reset_staff_passwords"))
        self.save_staff_btn.setEnabled(can_edit or can_create or can_role or can_active)

    def start_new_staff(self) -> None:
        if not (self._has("create_staff") or self._has("manage_staff")):
            QMessageBox.warning(self, "Yetkisiz İşlem",
                                "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
            return
        self.selected_staff_id = None
        self.staff_table.clearSelection()
        self._load_staff_form(None)

    def save_staff(self) -> None:
        full_name   = self.full_name_input.text().strip()
        device_name = self.device_name_input.text().strip()
        if not full_name or not device_name:
            QMessageBox.warning(self, "Eksik bilgi", "Ad Soyad ve Cihaz Adı zorunludur.")
            return
        try:
            if self.selected_staff_id is None:
                pwd = self.password_input.text()
                if not pwd:
                    QMessageBox.warning(self, "Eksik bilgi", "Yeni personel için şifre zorunludur.")
                    return
                auth.create_staff_by_admin(
                    self.db_or_path, self.current_user, device_name, full_name, pwd,
                    int(self.role_select.currentData()), int(self.status_select.currentData()))
            else:
                row = next((r for r in auth.list_staff(self.db_or_path)
                            if int(r["id"]) == int(self.selected_staff_id)), None)
                kw: dict[str, Any] = {}
                if self._has("edit_staff") or self._has("manage_staff"):
                    kw["full_name"] = full_name; kw["device_name"] = device_name
                if (self._has("change_staff_roles") or self._has("manage_roles")) and row \
                        and int(row.get("role_id") or 0) != int(self.role_select.currentData()):
                    kw["role_id"] = int(self.role_select.currentData())
                if self._has("manage_staff") and row \
                        and int(row.get("is_active") if row.get("is_active") is not None else 1) \
                        != int(self.status_select.currentData()):
                    kw["is_active"] = int(self.status_select.currentData())
                auth.update_staff_record(self.db_or_path, self.current_user,
                                         int(self.selected_staff_id), **kw)
            self.refresh_all()
            QMessageBox.information(self, "Kullanıcı ve Yetki Yönetimi",
                                    "Personel bilgileri kaydedildi.")
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem",
                                "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Personel Kaydet", str(exc))

    def reset_password(self) -> None:
        if self.selected_staff_id is None: return
        if not self._has("reset_staff_passwords"):
            QMessageBox.warning(self, "Yetkisiz İşlem",
                                "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
            return
        dlg = QDialog(self); dlg.setWindowTitle("Şifre Sıfırla")
        form = QFormLayout(dlg)
        pwd = QLineEdit(); pwd.setEchoMode(QLineEdit.Password)
        form.addRow("Yeni şifre", pwd)
        brow = QHBoxLayout()
        c = QPushButton("İptal"); s = QPushButton("Kaydet"); s.setObjectName("primaryBtn")
        c.clicked.connect(dlg.reject); s.clicked.connect(dlg.accept)
        brow.addStretch(1); brow.addWidget(c); brow.addWidget(s)
        form.addRow(brow)
        if dlg.exec() != QDialog.Accepted: return
        if not pwd.text():
            QMessageBox.warning(self, "Eksik bilgi", "Şifre boş olamaz."); return
        try:
            auth.reset_staff_password(self.db_or_path, self.current_user,
                                       int(self.selected_staff_id), pwd.text())
            QMessageBox.information(self, "Şifre Sıfırla", "Şifre güncellendi.")
        except Exception as exc:
            QMessageBox.warning(self, "Şifre Sıfırla", str(exc))

    # ── Role buttons ──────────────────────────────────────────────────────────
    def _populate_role_buttons(self) -> None:
        while self.role_button_layout.count():
            it = self.role_button_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for role in self.roles:
            btn = QPushButton(f"👤  {role['display_name']}")
            btn.setObjectName("roleTab")
            btn.clicked.connect(lambda _=False, rid=int(role["id"]): self.set_active_role(rid))
            self.role_button_layout.addWidget(btn, 1)
        self._update_role_button_styles()

    def set_active_role(self, role_id: int) -> None:
        role = next((r for r in self.roles if int(r["id"]) == int(role_id)), None)
        if not role: return
        self.active_role_id   = int(role_id)
        self.active_role_name = str(role.get("name") or "")
        self._group_collapsed.clear()
        self._update_role_button_styles()
        self.render_permissions()

    def _update_role_button_styles(self) -> None:
        n = self.role_button_layout.count()
        for i in range(n):
            btn  = self.role_button_layout.itemAt(i).widget()
            role = self.roles[i] if i < len(self.roles) else None
            if not btn or not role: continue
            active = int(role["id"]) == int(self.active_role_id or 0)
            color  = ROLE_COLORS.get(str(role.get("name") or ""), "#1457d9")
            br     = "none" if i == n - 1 else "1px solid #e5eaf2"
            btn.setStyleSheet(
                f"QPushButton#roleTab {{ color: {color if active else '#374151'};"
                f" border-bottom: 3px solid {color if active else 'transparent'};"
                f" border-right: {br}; font-size: 13px; font-weight: 900; }}"
            )
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ── Permission table ──────────────────────────────────────────────────────
    def _permission_catalog(self) -> dict[str, tuple[str, str, str]]:
        return {code: (cat, disp, desc)
                for cat, perms in auth.PERMISSION_GROUPS
                for code, disp, desc in perms}

    def _on_perm_cell_clicked(self, row: int, _col: int) -> None:
        if row >= len(self._perm_rows): return
        grp, code, _, _ = self._perm_rows[row]
        if grp is None: return
        gi = sum(1 for rr in self._perm_rows[:row] if rr[0] is not None)
        self._group_collapsed[gi] = not self._group_collapsed.get(gi, False)
        self._apply_row_visibility()

    def _apply_row_visibility(self) -> None:
        gi = -1; collapsed = False
        for r, (grp, _, _, _) in enumerate(self._perm_rows):
            if grp is not None:
                gi += 1
                collapsed = self._group_collapsed.get(gi, False)
                arrow = "▶" if collapsed else "▼"
                item = self.permission_table.item(r, 0)
                if item: item.setText(f"  {arrow}  {grp}")
                self.permission_table.setRowHidden(r, False)
            else:
                self.permission_table.setRowHidden(r, collapsed)

    def render_permissions(self) -> None:
        if self.active_role_id is None: return
        catalog  = self._permission_catalog()
        role_map = auth.get_role_permission_map(self.db_or_path).get(int(self.active_role_id), {})
        role     = next((r for r in self.roles if int(r["id"]) == int(self.active_role_id)), None)
        role_display = str(role.get("display_name") if role else "")
        color        = ROLE_COLORS.get(str(role.get("name") if role else ""), "#1457d9")

        self.selected_role_label.setText(f"Seçili rol:   {role_display}")
        self.selected_role_label.setStyleSheet(
            f"QLabel#selectedRoleBox {{ background: #f8fbff; border: 1px dashed #c8d9f5;"
            f" border-radius: 8px; padding: 7px 14px; font-size: 12px;"
            f" color: {color}; font-weight: 900; }}"
        )

        self._perm_rows = []
        for grp, codes in VISIBLE_PERMISSION_GROUPS:
            self._perm_rows.append((grp, None, "", ""))
            for code in codes:
                _cat, disp, desc = catalog.get(code, (grp, code, ""))
                self._perm_rows.append((None, code, disp, desc))

        self.permission_toggles.clear()
        self.permission_table.setRowCount(len(self._perm_rows))
        self.permission_table.clearSpans()

        WHITE = QBrush(QColor("#ffffff"))
        GREY  = QBrush(QColor("#f8fafc"))

        for r, (grp, code, disp, desc) in enumerate(self._perm_rows):
            if grp is not None:
                item = QTableWidgetItem(f"  ▼  {grp}")
                item.setFlags(Qt.ItemIsEnabled)
                f = item.font(); f.setBold(True); f.setPointSize(10); item.setFont(f)
                item.setBackground(GREY)
                item.setForeground(QBrush(QColor("#374151")))
                self.permission_table.setItem(r, 0, item)
                self.permission_table.setSpan(r, 0, 1, 3)
                self.permission_table.setRowHeight(r, 36)
                continue

            ni = QTableWidgetItem(f"   {disp}")
            ni.setFlags(Qt.ItemIsEnabled); ni.setBackground(WHITE)
            f2 = ni.font(); f2.setPointSize(10); ni.setFont(f2)
            self.permission_table.setItem(r, 0, ni)

            di = QTableWidgetItem(desc)
            di.setFlags(Qt.ItemIsEnabled)
            di.setForeground(QBrush(QColor("#64748b"))); di.setBackground(WHITE)
            f3 = di.font(); f3.setPointSize(10); di.setFont(f3)
            self.permission_table.setItem(r, 1, di)

            tog = ToggleSwitch(color=color)
            tog.setChecked(bool(role_map.get(str(code), False)))
            wrap = QWidget(); wrap.setStyleSheet("background: #ffffff;")
            tl = QHBoxLayout(wrap); tl.setContentsMargins(0, 0, 8, 0)
            tl.addWidget(tog, 0, Qt.AlignCenter)
            self.permission_table.setCellWidget(r, 2, wrap)
            self.permission_table.setRowHeight(r, 42)
            self.permission_toggles[str(code)] = tog

        self._apply_row_visibility()

    def _selected_role_permissions(self) -> dict[str, bool]:
        return {code: tog.isChecked() for code, tog in self.permission_toggles.items()}

    def save_selected_role_permissions(self) -> None:
        if self.active_role_id is None: return
        try:
            auth.set_role_permissions_bulk(
                self.db_or_path, self.current_user,
                {int(self.active_role_id): self._selected_role_permissions()})
            if self.current_user is not None:
                ref = auth.enrich_staff_permissions(self.db_or_path, self.current_user)
                if ref:
                    self.current_user.update(ref)
                    auth.current_staff = self.current_user
            self.permissions_saved.emit()
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
            self.save_message.show()
        except PermissionError:
            QMessageBox.warning(self, "Yetkisiz İşlem",
                                "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        except Exception as exc:
            QMessageBox.warning(self, "Yetki Yönetimi", str(exc))

    def restore_selected_role_defaults(self) -> None:
        if self.active_role_id is None: return
        ans = QMessageBox.question(
            self, "Varsayılanlara Dön",
            "Seçili rolün yetkileri varsayılan değerlere döndürülecek. Devam edilsin mi?")
        if ans != QMessageBox.Yes: return
        try:
            role = next((r for r in self.roles if int(r["id"]) == int(self.active_role_id)), None)
            if not role: return
            defaults = auth.DEFAULT_ROLE_PERMISSIONS.get(str(role["name"]), set())
            codes = list(self.permission_toggles.keys())
            auth.set_role_permissions_bulk(
                self.db_or_path, self.current_user,
                {int(self.active_role_id): {c: c in defaults for c in codes}})
            self.render_permissions()
            self.permissions_saved.emit()
            if self.parent() is not None and hasattr(self.parent(), "_refresh_permission_actions"):
                self.parent()._refresh_permission_actions()
        except Exception as exc:
            QMessageBox.warning(self, "Varsayılanlara Dön", str(exc))


# ── Aliases ───────────────────────────────────────────────────────────────────
class StaffManagementDialog(StaffPermissionsDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(db_or_path, current_user, parent, initial_tab="staffRoles")

class RolePermissionsDialog(StaffPermissionsDialog):
    def __init__(self, db_or_path, current_user: Optional[dict[str, Any]], parent=None):
        super().__init__(db_or_path, current_user, parent, initial_tab="rolePermissions")
