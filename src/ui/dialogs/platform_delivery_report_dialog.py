from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QStackedWidget, QScrollArea, QHeaderView, QLineEdit,
)

from src.services.platform_delivery_report import STATUSES, export_report_to_excel, load_report_data, save_report_data

# Row height for the detail table. Kept compact and constant so input widgets
# never force the table to grow taller than necessary.
DETAIL_ROW_HEIGHT = 46
SUMMARY_ROW_HEIGHT = 72
# Standard width for a sub-page tab button. Tabs never stretch to fill the
# available width — new tabs are simply appended after the last one and a
# horizontal scroll area takes over once they overflow.
TAB_MIN_WIDTH = 220
TAB_MAX_WIDTH = 260

# Exact colors from the approved mockup. Component group colors cycle in
# this order and repeat once exhausted (Hava Aracı -> sarı, YKİ -> mavi,
# next -> gri, next -> açık pembe, next -> turuncu, next -> açık yeşil,
# then back to sarı).
DETAIL_ROW_COLORS = ["#ead58c", "#1ba9da", "#cbcbcb", "#e8d5c8", "#e7bf9d", "#b7cfa5"]
COLOR_PAGE_BG = "#f8fbff"
COLOR_PANEL_BG = "#ffffff"
COLOR_PANEL_BORDER = "#cfe0f5"
COLOR_DIVIDER = "#000000"
COLOR_TEXT = "#001f54"
COLOR_TEXT_MUTED = "#65789a"
COLOR_HEADER_MAIN = "#082f6f"
COLOR_HEADER_COL = "#103c80"
COLOR_HEADER_TEXT = "#ffffff"
COLOR_GRID_BORDER = "#000000"
COLOR_SUMMARY_ROW = "#dbe8f6"
COLOR_INPUT_BORDER = "#bfd4ee"
COLOR_INPUT_TEXT = "#062b66"
ARROW_ICON_PATH = (Path(__file__).resolve().parents[1] / "assets" / "chevron_down.svg").as_posix()


class _UserFilterRow(QWidget):
    """Single row inside the user multi-select popup.

    This mirrors the app-wide multi-user dropdown style: a soft avatar,
    user name, and modern checkbox instead of the native checkbox row that
    was staying open in the wrong situations.
    """
    toggled = Signal(int, bool)

    _AVATAR_PALETTES = [
        ("#e8f0fe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#ecfdf5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#e0f2fe", "#075985"),
        ("#d1fae5", "#065f46"),
    ]

    def __init__(self, label: str, user_id: int, palette_index: int, checked: bool = False, parent=None):
        super().__init__(parent)
        self._label = str(label or "")
        self._user_id = int(user_id or 0)
        self._checked = bool(checked)
        bg, fg = self._AVATAR_PALETTES[palette_index % len(self._AVATAR_PALETTES)]
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(10)

        avatar = QLabel(self._initials(self._label))
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:13px;"
            "font-size:10px;font-weight:800;border:none;"
        )
        lay.addWidget(avatar)

        text = QLabel(self._label)
        text.setStyleSheet("font-size:13px;color:#0f172a;background:transparent;border:none;")
        lay.addWidget(text, 1)

        self._check = QLabel()
        self._check.setFixedSize(18, 18)
        self._check.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._check)
        self._refresh_style()

    @staticmethod
    def _initials(name: str) -> str:
        parts = [p for p in str(name or "").strip().split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return (parts[0][:2] if parts else "?").upper()

    def _refresh_style(self):
        if self._checked:
            self.setStyleSheet("QWidget{background:#f0f7ff;} QWidget:hover{background:#e8f3ff;}")
            self._check.setText("✓")
            self._check.setStyleSheet(
                "background:#2563eb;border:1.5px solid #2563eb;border-radius:4px;"
                "color:white;font-size:11px;font-weight:900;"
            )
        else:
            self.setStyleSheet("QWidget{background:#ffffff;} QWidget:hover{background:#f8fafc;}")
            self._check.setText("")
            self._check.setStyleSheet(
                "background:#ffffff;border:1.5px solid #cbd5e1;border-radius:4px;"
            )

    def set_checked(self, checked: bool):
        self._checked = bool(checked)
        self._refresh_style()

    def matches_filter(self, query: str) -> bool:
        return str(query or "").casefold() in self._label.casefold()

    def mousePressEvent(self, event):
        self.set_checked(not self._checked)
        self.toggled.emit(self._user_id, self._checked)
        event.accept()


class _UserFilterDropdown(QFrame):
    """Popup panel used by UserMultiSelectWidget.

    It is a real Qt.Popup window, so clicking anywhere outside it closes the
    popup automatically. This fixes the old QComboBox override that could
    remain stuck open after a user was selected.
    """
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("userFilterDropdown")
        self._items: list[tuple[str, int]] = []
        self._selected: list[int] = []
        self._rows: list[_UserFilterRow] = []
        self.setStyleSheet("""
            QFrame#userFilterDropdown {
                background: #ffffff;
                border: 1.5px solid #d7e6f8;
                border-radius: 12px;
            }
            QLineEdit#userFilterSearch {
                background: transparent;
                border: none;
                color: #0f172a;
                font-size: 13px;
                font-weight: 700;
                padding: 0;
                min-height: 24px;
            }
            QLabel#userFilterFooter {
                color: #64748b;
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: 800;
            }
            QPushButton#userFilterClear, QPushButton#userFilterSelectAll {
                background: transparent;
                border: none;
                color: #2563eb;
                padding: 0;
                font-size: 11px;
                font-weight: 900;
            }
            QPushButton#userFilterClear:hover, QPushButton#userFilterSelectAll:hover { color: #1d4ed8; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        search_host = QWidget(self)
        search_host.setStyleSheet("background:#ffffff;border-bottom:1px solid #eef4fb;")
        sr = QHBoxLayout(search_host)
        sr.setContentsMargins(10, 7, 10, 7)
        sr.setSpacing(7)
        icon = QLabel("⌕")
        icon.setStyleSheet("color:#94a3b8;font-size:16px;background:transparent;border:none;")
        sr.addWidget(icon)
        self._search = QLineEdit()
        self._search.setObjectName("userFilterSearch")
        self._search.setPlaceholderText("Ara...")
        self._search.textChanged.connect(self._apply_filter)
        sr.addWidget(self._search, 1)
        root.addWidget(search_host)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFixedHeight(210)
        self._scroll.setStyleSheet("QScrollArea{background:#ffffff;border:none;}")
        self._list_host = QWidget()
        self._list_host.setStyleSheet("background:#ffffff;border:none;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(0)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll)

        footer = QWidget(self)
        footer.setStyleSheet("background:#ffffff;border-top:1px solid #eef4fb;")
        fr = QHBoxLayout(footer)
        fr.setContentsMargins(12, 7, 12, 7)
        self._count = QLabel("Seçim yok")
        self._count.setObjectName("userFilterFooter")
        fr.addWidget(self._count)
        fr.addStretch(1)
        select_all = QPushButton("Tümünü Seç")
        select_all.setObjectName("userFilterSelectAll")
        select_all.setCursor(Qt.PointingHandCursor)
        select_all.clicked.connect(self._select_all)
        fr.addWidget(select_all)
        clear = QPushButton("Temizle")
        clear.setObjectName("userFilterClear")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_all)
        fr.addWidget(clear)
        root.addWidget(footer)

    def populate(self, items: list[tuple[str, int]], selected: list[int]):
        self._items = [(str(label), int(uid or 0)) for label, uid in items if int(uid or 0) > 0]
        self._selected = [int(uid) for uid in selected if int(uid or 0) > 0]
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()
        selected_set = set(self._selected)
        for idx, (label, uid) in enumerate(self._items):
            row = _UserFilterRow(label, uid, idx, uid in selected_set, self)
            row.toggled.connect(self._on_row_toggled)
            self._list_lay.addWidget(row)
            self._rows.append(row)
        self._list_lay.addStretch(1)
        self._search.clear()
        self._update_count()

    def _on_row_toggled(self, uid: int, checked: bool):
        uid = int(uid or 0)
        if uid <= 0:
            return
        if checked and uid not in self._selected:
            self._selected.append(uid)
        elif not checked:
            self._selected = [x for x in self._selected if x != uid]
        self._update_count()
        self.selectionChanged.emit(list(self._selected))

    def _select_all(self):
        self._selected = [uid for _label, uid in self._items]
        selected_set = set(self._selected)
        for row in self._rows:
            row.set_checked(getattr(row, "_user_id", 0) in selected_set)
        self._update_count()
        self.selectionChanged.emit(list(self._selected))

    def _clear_all(self):
        self._selected = []
        for row in self._rows:
            row.set_checked(False)
        self._update_count()
        self.selectionChanged.emit([])

    def _apply_filter(self, query: str):
        for row in self._rows:
            row.setVisible(row.matches_filter(query))

    def _update_count(self):
        n = len(self._selected)
        self._count.setText(f"{n} seçili" if n else "Seçim yok")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)


class UserMultiSelectWidget(QWidget):
    """App-theme multi-select widget for the Kullanıcı / Ülke filter."""
    selectionChanged = Signal()

    def __init__(self, parent=None, placeholder: str = "Kullanıcı seçin"):
        super().__init__(parent)
        self._placeholder = placeholder
        self._items: list[tuple[str, int]] = []
        self._selected: list[int] = []
        self._dropdown: Optional[_UserFilterDropdown] = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._display = QFrame(self)
        self._display.setObjectName("userMultiSelectDisplay")
        self._display.setCursor(Qt.PointingHandCursor)
        self._display.setMinimumHeight(40)
        dl = QHBoxLayout(self._display)
        dl.setContentsMargins(11, 6, 11, 6)
        dl.setSpacing(8)
        self._text = QLabel(self._placeholder)
        self._text.setObjectName("userMultiSelectText")
        dl.addWidget(self._text, 1)
        self._chevron = QLabel("⌄")
        self._chevron.setObjectName("userMultiSelectChevron")
        self._chevron.setAlignment(Qt.AlignCenter)
        self._chevron.setFixedWidth(18)
        dl.addWidget(self._chevron)
        root.addWidget(self._display)
        self._display.mousePressEvent = self._toggle_dropdown
        self._refresh_display()

    def set_items(self, items: list[tuple[str, object]]):
        clean: list[tuple[str, int]] = []
        seen: set[int] = set()
        for label, raw_uid in list(items or []):
            try:
                uid = int(raw_uid or 0)
            except (TypeError, ValueError):
                continue
            text = str(label or "").strip()
            if uid > 0 and text and uid not in seen:
                seen.add(uid)
                clean.append((text, uid))
        self._items = clean
        valid = {uid for _label, uid in self._items}
        self._selected = [uid for uid in self._selected if uid in valid]
        self._refresh_display()

    def checked_data(self) -> list[int]:
        return list(self._selected)

    def clear_checked(self):
        self.set_checked_data([])

    def set_checked_data(self, values: list):
        wanted: list[int] = []
        valid = {uid for _label, uid in self._items}
        seen: set[int] = set()
        for raw in list(values or []):
            try:
                uid = int(raw or 0)
            except (TypeError, ValueError):
                continue
            if uid > 0 and uid in valid and uid not in seen:
                seen.add(uid)
                wanted.append(uid)
        if wanted == self._selected:
            self._refresh_display()
            return
        self._selected = wanted
        self._refresh_display()
        self.selectionChanged.emit()

    def _label_by_id(self) -> dict[int, str]:
        return {uid: label for label, uid in self._items}

    def _refresh_display(self):
        labels = [self._label_by_id().get(uid, "") for uid in self._selected]
        labels = [x for x in labels if x]
        if not labels:
            text = self._placeholder
            self.setProperty("placeholder", True)
            self._text.setProperty("placeholder", True)
        elif len(labels) == len(self._items) and len(self._items) > 1:
            text = "Tümü"
            self.setProperty("placeholder", False)
            self._text.setProperty("placeholder", False)
        elif len(labels) == 1:
            text = labels[0]
            self.setProperty("placeholder", False)
            self._text.setProperty("placeholder", False)
        else:
            text = f"{len(labels)} kullanıcı seçili"
            self.setProperty("placeholder", False)
            self._text.setProperty("placeholder", False)
        self._text.setText(text)
        self.setToolTip(", ".join(labels))
        for widget in (self, self._text, self._display):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _toggle_dropdown(self, event=None):
        if self._dropdown is None:
            self._dropdown = _UserFilterDropdown(self)
            self._dropdown.selectionChanged.connect(self._on_dropdown_changed)
        if self._dropdown.isVisible():
            self._dropdown.hide()
            return
        self._dropdown.setFixedWidth(max(self.width(), 240))
        self._dropdown.populate(self._items, self._selected)
        pos = self.mapToGlobal(self._display.rect().bottomLeft())
        self._dropdown.move(pos.x(), pos.y() + 3)
        self._dropdown.show()
        self._dropdown.raise_()

    def _on_dropdown_changed(self, values: list):
        self._selected = [int(v) for v in values if int(v or 0) > 0]
        self._refresh_display()
        self.selectionChanged.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.setFixedWidth(max(self.width(), 240))


class PlatformTeslimatDurumuReportDialog(QDialog):
    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store
        self.data = None
        self.detail_tables = OrderedDict()
        self.summary_table = None
        self._dirty = False
        self._refreshing = False
        self.setWindowTitle("Platform Teslimat Özeti")

        # Give the window normal min/max/close controls and let it actually
        # be resized by the user instead of behaving like a fixed dialog.
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowSystemMenuHint
        )
        self.setSizeGripEnabled(True)
        self.resize(1500, 820)
        self.setMinimumSize(1100, 680)

        self._build_ui()
        self._load_filters()
        self._show_empty_preview("Filtreleri seçip Önizlemeyi Yenile butonuna basın.")

    # ─── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        root.addWidget(self._build_filter_panel())

        right = QFrame()
        right.setObjectName("reportCard")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(18, 12, 18, 12)
        self.title_label = QLabel("Platform Teslimat Özeti")
        self.title_label.setObjectName("mainTitle")
        top.addWidget(self.title_label)
        self.badge = QLabel("Sayfa 1 / 1")
        self.badge.setObjectName("badge")
        top.addWidget(self.badge)
        top.addStretch()
        e = QPushButton("Excel Oluştur")
        e.setObjectName("reportSecondaryButton")
        e.clicked.connect(self.export_excel)
        top.addWidget(e)
        s = QPushButton("Raporu Kaydet")
        s.setObjectName("reportPrimaryButton")
        s.clicked.connect(self.save_report)
        top.addWidget(s)
        rl.addLayout(top)

        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)

        rl.addWidget(self._build_tab_bar())
        root.addWidget(right, 1)

        self.setStyleSheet(STYLE)

    def _build_filter_panel(self):
        frame = QFrame()
        frame.setObjectName("filterPanel")
        frame.setFixedWidth(310)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Rapor Ayarları")
        title.setObjectName("panelTitle")
        lay.addWidget(title)

        self.platform_cb = self._combo(lay, "PLATFORM", placeholder="Platform seçin")
        self.platform_cb.currentIndexChanged.connect(self._on_platform_changed)

        self.user_cb = self._user_multi_combo(lay, "KULLANICI / ÜLKE")
        self.user_cb.selectionChanged.connect(self._on_user_filter_changed)

        self.contract_cb = self._combo(lay, "SÖZLEŞME", placeholder="Sözleşme seçin / tümü")

        self.left_refresh_btn = QPushButton("Önizlemeyi Yenile")
        self.left_refresh_btn.setObjectName("reportPrimaryButton")
        self.left_refresh_btn.clicked.connect(self.refresh_preview)
        lay.addSpacing(6)
        lay.addWidget(self.left_refresh_btn)

        lay.addSpacing(14)
        lay.addWidget(self._build_stat_cards())
        lay.addStretch()
        return frame

    def _build_stat_cards(self):
        """Modern KPI cards shown in the filter panel."""
        host = QWidget()
        host.setObjectName("statHost")
        grid = QVBoxLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        self.stat_pages = self._stat_card(grid, "TOPLAM SAYFA")
        self.stat_users = self._stat_card(grid, "KULLANICI")
        self.stat_contracts = self._stat_card(grid, "SÖZLEŞME")
        return host

    def _stat_card(self, parent_layout, label_text: str) -> QLabel:
        card = QFrame()
        card.setObjectName("statCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(2)
        label = QLabel(label_text)
        label.setObjectName("statCardLabel")
        value = QLabel("0")
        value.setObjectName("statCardValue")
        cl.addWidget(label)
        cl.addWidget(value)
        parent_layout.addWidget(card)
        return value

    def _build_tab_bar(self):
        """Horizontal strip of fixed-width sub-page tab buttons."""
        self.tabs_scroll = QScrollArea()
        self.tabs_scroll.setObjectName("tabsScroll")
        self.tabs_scroll.setWidgetResizable(True)
        self.tabs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tabs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tabs_scroll.setFixedHeight(56)
        self.tabs_scroll.setFrameShape(QFrame.NoFrame)

        tabs_host = QWidget()
        tabs_host.setObjectName("tabsHost")
        self.tabs = QHBoxLayout(tabs_host)
        self.tabs.setContentsMargins(16, 8, 16, 8)
        self.tabs.setSpacing(6)
        self.tabs.addStretch(1)

        self.tabs_scroll.setWidget(tabs_host)
        return self.tabs_scroll

    def _combo(self, lay, label, items=None, placeholder: str | None = None):
        l = QLabel(label)
        l.setObjectName("filterLabel")
        lay.addWidget(l)
        cb = QComboBox()
        cb.setObjectName("filterCombo")
        if placeholder is not None:
            cb.addItem(placeholder, None)
            cb.setProperty("placeholder", True)
        for item in items or []:
            if isinstance(item, tuple):
                cb.addItem(str(item[0]), item[1])
            else:
                cb.addItem(str(item), item)
        cb.currentIndexChanged.connect(lambda *_: self._refresh_combo_placeholder_state(cb))
        lay.addWidget(cb)
        return cb

    def _user_multi_combo(self, lay, label):
        l = QLabel(label)
        l.setObjectName("filterLabel")
        lay.addWidget(l)
        cb = UserMultiSelectWidget(placeholder="Kullanıcı seçin")
        cb.setObjectName("filterCombo")
        lay.addWidget(cb)
        return cb

    # ─── Filters ──────────────────────────────────────────────────────

    def _refresh_combo_placeholder_state(self, combo: QComboBox):
        combo.setProperty("placeholder", combo.currentData() is None and combo.currentIndex() == 0)
        combo.style().unpolish(combo)
        combo.style().polish(combo)

    def _load_filters(self):
        if not self.store:
            return
        self.platform_cb.blockSignals(True)
        self.platform_cb.clear()
        self.platform_cb.addItem("Platform seçin", None)
        for name in self.store.platform_names():
            self.platform_cb.addItem(str(name), str(name))
        self.platform_cb.setCurrentIndex(0)
        self.platform_cb.blockSignals(False)
        self._refresh_combo_placeholder_state(self.platform_cb)

        self.user_cb.blockSignals(True)
        self.user_cb.set_items(self._load_all_users())
        self.user_cb.clear_checked()
        self.user_cb.blockSignals(False)

        self._reload_dependent_filters()

    def _load_all_users(self) -> list[tuple[str, int]]:
        """Load real database users for the multi-select filter."""
        if not self.store:
            return []
        try:
            rows = self.store.db.conn.execute(
                """
                SELECT id, name
                FROM users
                WHERE COALESCE(active, 1)=1
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        except Exception:
            return []
        result: list[tuple[str, int]] = []
        for row in rows:
            keys = row.keys() if hasattr(row, "keys") else []
            name = str(row["name"] if "name" in keys else row[1] or "").strip()
            uid = int(row["id"] if "id" in keys else row[0] or 0)
            if uid > 0 and name:
                result.append((name, uid))
        return result

    def _on_platform_changed(self, *_args):
        self._refresh_combo_placeholder_state(self.platform_cb)
        self.user_cb.clear_checked()
        self._reload_dependent_filters()
        self._show_empty_preview("Kullanıcı seçip Önizlemeyi Yenile butonuna basın.")

    def _on_user_filter_changed(self, *_args):
        self._reload_dependent_filters()

    def _current_platform(self) -> str:
        data = self.platform_cb.currentData()
        return str(data or "").strip()

    def _selected_user_ids(self) -> list[int]:
        result: list[int] = []
        for value in self.user_cb.checked_data():
            try:
                uid = int(value or 0)
            except (TypeError, ValueError):
                continue
            if uid > 0:
                result.append(uid)
        return result

    def _current_contract_id(self) -> Optional[int]:
        value = self.contract_cb.currentData()
        try:
            cid = int(value or 0)
        except (TypeError, ValueError):
            return None
        return cid if cid > 0 else None

    def _reload_dependent_filters(self):
        """Refresh the contract dropdown from the current platform/users only.

        This does not rebuild the report preview; it only keeps filter choices
        consistent. The actual report updates only when Önizlemeyi Yenile is
        pressed.
        """
        self.contract_cb.blockSignals(True)
        self.contract_cb.clear()
        self.contract_cb.addItem("Sözleşme seçin / tümü", None)

        platform = self._current_platform()
        if platform and self.store:
            try:
                data = load_report_data(self.store, platform, self._selected_user_ids() or None, None)
                seen_c = set()
                for r in data.summary:
                    if r.contract_id and r.contract_id not in seen_c:
                        seen_c.add(r.contract_id)
                        self.contract_cb.addItem(str(r.contract), int(r.contract_id))
            except Exception:
                pass

        self.contract_cb.setCurrentIndex(0)
        self.contract_cb.blockSignals(False)
        self._refresh_combo_placeholder_state(self.contract_cb)

    def _show_empty_preview(self, message: str = ""):
        self._refreshing = True
        self._clear_stack()
        self.detail_tables.clear()
        self._clear_tabs()
        self.summary_table = None
        self.data = None
        self.title_label.setText("Platform Teslimat Özeti")
        self.badge.setText("Sayfa 0 / 0")
        self._update_stats(0, 0, 0)

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(24, 24, 24, 24)
        label = QLabel(message or "Filtreleri seçip Önizlemeyi Yenile butonuna basın.")
        label.setObjectName("emptyState")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        lay.addWidget(label, 1)
        self._add_page(host, "Önizleme")
        self.stack.setCurrentIndex(0)
        self._refreshing = False

    def _update_stats(self, pages: int, users: int, contracts: int):
        self.stat_pages.setText(str(pages))
        self.stat_users.setText(str(users))
        self.stat_contracts.setText(str(contracts))

    # ─── Preview / pages ──────────────────────────────────────────────

    def refresh_preview(self):
        if not self.store:
            return
        platform = self._current_platform()
        user_ids = self._selected_user_ids()
        if not platform:
            self._show_empty_preview("Önce platform seçin.")
            return
        if not user_ids:
            self._show_empty_preview("Önce en az bir kullanıcı seçin.")
            return
        if self._dirty:
            result = QMessageBox.question(
                self, "Kaydedilmemiş değişiklikler",
                "Önizleme yenilenirse kaydedilmemiş değişiklikler kaybolur. Devam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return
        self._refreshing = True
        cid = self._current_contract_id()
        self.data = load_report_data(self.store, platform, user_ids, cid)
        self._clear_stack()
        self.detail_tables.clear()
        self._clear_tabs()
        self.title_label.setText(f"{self.data.platform} Teslimat Özeti")
        self.summary_table = self._summary_table()
        self._add_page(self.summary_table, f"{self.data.platform} Teslimat Özeti")
        for key, lines in self.data.details.items():
            if lines:
                self.detail_tables[key] = self._detail_table(lines)
                self._add_page(self.detail_tables[key], f"{lines[0].user} Teslimat Özeti")

        self._update_stats(
            self.stack.count(),
            len({r.user_id for r in self.data.summary if int(r.user_id or 0) > 0}),
            len({r.contract_id for r in self.data.summary}),
        )

        self._set_page(0)
        self._dirty = False
        self._refreshing = False

    def _summary_table(self):
        t = QTableWidget(len(self.data.summary), 5)
        t.setHorizontalHeaderLabels(["Kullanıcı", "Sözleşme Adı veya Numarası", "Teslimat Tarihi", "Durum", "Açıklama"])
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setShowGrid(True)
        t.setGridStyle(Qt.SolidLine)
        t.verticalHeader().setDefaultSectionSize(SUMMARY_ROW_HEIGHT)
        t._editable_columns = [3, 4]
        for i, r in enumerate(self.data.summary):
            # Keep real QTableWidgetItem objects for selection/data, but paint
            # the visible content with cell widgets so the summary row is
            # consistently light-blue on every Qt/platform style.
            nav_item = QTableWidgetItem(f"{r.user} ↗")
            nav_item.setData(Qt.UserRole, (r.user_id, r.contract_id))
            nav_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            nav_item.setBackground(QColor(COLOR_SUMMARY_ROW))
            t.setItem(i, 0, nav_item)
            t.setCellWidget(i, 0, self._summary_display_cell(
                f"{r.user} ↗", COLOR_SUMMARY_ROW,
                on_click=lambda _event=None, row=i: self._set_page(row + 1) if row + 1 < self.stack.count() else None,
            ))

            for c, v in [(1, r.contract), (2, r.delivery_date)]:
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setBackground(QColor(COLOR_SUMMARY_ROW))
                it.setForeground(QColor(COLOR_TEXT))
                it.setTextAlignment(Qt.AlignCenter)
                t.setItem(i, c, it)
                t.setCellWidget(i, c, self._summary_display_cell(str(v), COLOR_SUMMARY_ROW))

            cb = QComboBox()
            cb.addItems(STATUSES)
            cb.setCurrentText(r.status if r.status in STATUSES else r.status)
            cb.currentTextChanged.connect(self._mark_dirty)
            self._attach_cell_navigation(cb, t, i, 3)
            t.setCellWidget(i, 3, self._inset_input(cb, COLOR_SUMMARY_ROW, compact=False))

            txt = QTextEdit(r.description)
            txt.setFixedHeight(52)
            txt.textChanged.connect(self._mark_dirty)
            self._attach_cell_navigation(txt, t, i, 4)
            t.setCellWidget(i, 4, self._inset_input(txt, COLOR_SUMMARY_ROW, compact=False))
            t.setRowHeight(i, SUMMARY_ROW_HEIGHT)
        t.cellClicked.connect(lambda row, col: self._set_page(row + 1) if col == 0 and row + 1 < self.stack.count() else None)
        return t

    @staticmethod
    def _summary_display_cell(text: str, bg_hex: str, on_click=None) -> QWidget:
        """Readonly summary cell with guaranteed light-blue row background."""
        cell = QFrame()
        cell.setObjectName("summaryDisplayCell")
        cell.setStyleSheet(f"""
            QFrame#summaryDisplayCell {{
                background: {bg_hex};
                border: none;
                margin: 0px;
                padding: 0px;
            }}
            QFrame#summaryDisplayCell QLabel {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT};
                font-weight: 700;
            }}
        """)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        label = QLabel(str(text or ""))
        label.setAlignment(Qt.AlignCenter)
        lay.addWidget(label, 1)
        if on_click is not None:
            cell.setCursor(Qt.PointingHandCursor)
            label.setCursor(Qt.PointingHandCursor)
            cell.mousePressEvent = on_click
            label.mousePressEvent = on_click
        return cell

    def _attach_cell_navigation(self, widget: QWidget, table: QTableWidget, row: int, col: int) -> None:
        """Allow spreadsheet-like arrow-key movement between editable cells."""
        try:
            widget._report_nav_table = table
            widget._report_nav_row = int(row)
            widget._report_nav_col = int(col)
            widget.installEventFilter(self)
            # QTextEdit may deliver key events through its viewport on some styles.
            viewport = widget.viewport() if hasattr(widget, "viewport") else None
            if viewport is not None:
                viewport._report_nav_table = table
                viewport._report_nav_row = int(row)
                viewport._report_nav_col = int(col)
                viewport._report_nav_owner = widget
                viewport.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and hasattr(obj, "_report_nav_table"):
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                owner = getattr(obj, "_report_nav_owner", obj)
                if isinstance(owner, QComboBox):
                    try:
                        if owner.view().isVisible():
                            return False
                    except Exception:
                        pass
                table = getattr(obj, "_report_nav_table", None)
                row = int(getattr(obj, "_report_nav_row", 0))
                col = int(getattr(obj, "_report_nav_col", 0))
                if table is not None and self._move_to_editable_cell(table, row, col, key):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _move_to_editable_cell(self, table: QTableWidget, row: int, col: int, key: int) -> bool:
        editable_cols = list(getattr(table, "_editable_columns", []) or [])
        if not editable_cols:
            editable_cols = [c for c in range(table.columnCount()) if table.cellWidget(row, c) is not None]
        if col not in editable_cols:
            editable_cols.append(col)
            editable_cols = sorted(set(editable_cols))
        target_row, target_col = int(row), int(col)
        if key == Qt.Key_Up:
            target_row = max(0, row - 1)
        elif key == Qt.Key_Down:
            target_row = min(table.rowCount() - 1, row + 1)
        elif key in (Qt.Key_Left, Qt.Key_Right):
            idx = editable_cols.index(col)
            if key == Qt.Key_Left:
                target_col = editable_cols[max(0, idx - 1)]
            else:
                target_col = editable_cols[min(len(editable_cols) - 1, idx + 1)]
        if target_row == row and target_col == col:
            return False
        target = self._unwrap_input(table.cellWidget(target_row, target_col))
        if target is None:
            return False
        table.setCurrentCell(target_row, target_col)
        target.setFocus(Qt.TabFocusReason)
        if isinstance(target, QLineEdit):
            target.selectAll()
        return True

    def _detail_table(self, lines):
        """Build the detail page table.

        Same component/system rows are merged into one visual block. The
        amount shown in Miktar is the total number of visible rows in that
        merged block, so repeated delivery rows of the same system are not
        displayed as separate duplicate system blocks.
        """
        t = QTableWidget(len(lines), 6)
        t.setHorizontalHeaderLabels([
            "Ana Sistem", "Miktar", "Kuyruk No / Seri No",
            "Lokasyon", "Not", "Teslim Edilecek Lokasyon",
        ])
        t.verticalHeader().hide()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setWordWrap(False)
        t.setShowGrid(True)
        t.setGridStyle(Qt.SolidLine)
        t.verticalHeader().setDefaultSectionSize(DETAIL_ROW_HEIGHT)
        t._editable_columns = [3, 4, 5]

        comp_colors: dict[str, str] = {}

        def line_group_key(line) -> tuple:
            explicit = getattr(line, "component_group_key", "") or ""
            if explicit:
                return (line.user_id, line.contract_id, explicit)
            return (line.user_id, line.contract_id, line.component_id, line.component)

        group_sizes: dict[int, int] = {}
        group_start_rows: set[int] = set()
        scan_start = 0
        for scan_idx, scan_line in enumerate(lines + [None]):
            if scan_line is None:
                if lines:
                    group_sizes[scan_start] = scan_idx - scan_start
                    group_start_rows.add(scan_start)
                break
            if scan_idx == 0:
                group_start_rows.add(0)
                continue
            prev_line = lines[scan_idx - 1]
            if line_group_key(scan_line) != line_group_key(prev_line):
                group_sizes[scan_start] = scan_idx - scan_start
                scan_start = scan_idx
                group_start_rows.add(scan_start)

        for i, line in enumerate(lines):
            comp_colors.setdefault(line.component, DETAIL_ROW_COLORS[len(comp_colors) % len(DETAIL_ROW_COLORS)])
            bg = comp_colors[line.component]
            is_group_start = i in group_start_rows
            group_span = int(group_sizes.get(i, 1)) if is_group_start else 1

            if is_group_start:
                if group_span > 1:
                    t.setSpan(i, 0, group_span, 1)
                    t.setSpan(i, 1, group_span, 1)
                t.setCellWidget(i, 0, self._merged_display_cell(line.component, bg))
                t.setCellWidget(i, 1, self._merged_display_cell(str(group_span), bg))
            else:
                # Covered by the real span above. Keep invisible items only so
                # Qt still has a colored fallback if a style/platform ignores
                # the spanned cell widget background.
                for c in (0, 1):
                    it = QTableWidgetItem("")
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setBackground(QColor(bg))
                    t.setItem(i, c, it)

            t.setCellWidget(i, 2, self._readonly_display_cell(line.serial_no, bg, bold=False, wrap=False))

            location_combo = QComboBox()
            location_combo.addItems([""] + self.data.locations)
            location_combo.setCurrentText(line.internal_location)
            location_combo.currentTextChanged.connect(self._mark_dirty)
            self._attach_cell_navigation(location_combo, t, i, 3)
            t.setCellWidget(i, 3, self._inset_input(location_combo, bg, compact=True))

            note_edit = QLineEdit(line.note)
            note_edit.textChanged.connect(self._mark_dirty)
            self._attach_cell_navigation(note_edit, t, i, 4)
            t.setCellWidget(i, 4, self._inset_input(note_edit, bg, compact=True))

            delivery_loc_edit = QLineEdit(line.delivery_location)
            delivery_loc_edit.textChanged.connect(self._mark_dirty)
            self._attach_cell_navigation(delivery_loc_edit, t, i, 5)
            t.setCellWidget(i, 5, self._inset_input(delivery_loc_edit, bg, compact=True))

            t.setRowHeight(i, DETAIL_ROW_HEIGHT)

        t.setProperty("lines", lines)
        return t

    @staticmethod
    def _merged_display_cell(text: str, bg_hex: str) -> QWidget:
        return PlatformTeslimatDurumuReportDialog._readonly_display_cell(text, bg_hex, bold=True, wrap=True)

    @staticmethod
    def _readonly_display_cell(text: str, bg_hex: str, bold: bool = False, wrap: bool = False) -> QWidget:
        cell = QFrame()
        cell.setObjectName("readonlyDetailCell")
        cell.setStyleSheet(f"""
            QFrame#readonlyDetailCell {{
                background: {bg_hex};
                border: none;
                margin: 0px;
                padding: 0px;
            }}
            QFrame#readonlyDetailCell QLabel {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT};
                font-weight: {'900' if bold else '700'};
            }}
        """)
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        label = QLabel(str(text or ""))
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(bool(wrap))
        lay.addWidget(label, 1)
        return cell

    @staticmethod
    def _inset_input(input_widget: QWidget, bg_hex: str, compact: bool = True) -> QWidget:
        """Wrap an input widget in a small colored-margin container.

        The container itself carries the row's group color and is set as
        the cell widget; the input inside it stays plain white with a thin
        border, inset by a few pixels on every side so it never fills the
        cell edge-to-edge. The result is a white data-entry field that
        visually sits "in" a colored row band, matching the mockup.
        """
        is_text_edit = isinstance(input_widget, QTextEdit)
        container = QWidget()
        container.setStyleSheet(f"background: {bg_hex}; border: none;")
        layout = QHBoxLayout(container)
        if compact:
            layout.setContentsMargins(12, 7, 12, 7)
            height_rule = "" if is_text_edit else "min-height: 26px; max-height: 26px;"
        else:
            layout.setContentsMargins(12, 8, 12, 8)
            height_rule = "" if is_text_edit else "min-height: 30px; max-height: 30px;"
        layout.setSpacing(0)
        input_widget.setStyleSheet(f"""
            QComboBox, QLineEdit, QTextEdit {{
                background: #ffffff;
                border: 1px solid {COLOR_INPUT_BORDER};
                border-radius: 8px;
                padding: 0 9px;
                color: {COLOR_INPUT_TEXT};
                font-weight: 800;
                {height_rule}
            }}
            QComboBox:hover, QLineEdit:hover, QTextEdit:hover {{
                border: 1px solid #8fb3de;
            }}
            QComboBox:focus, QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid #1f6fd6;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left: 1px solid #d7e6f8;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background: #ffffff;
            }}
            QComboBox::down-arrow {{
                image: url("{ARROW_ICON_PATH}");
                width: 10px;
                height: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: #ffffff;
                color: {COLOR_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER};
                border-radius: 8px;
                padding: 4px;
                outline: 0;
                selection-background-color: #dbeafe;
                selection-color: {COLOR_TEXT};
            }}
        """)
        layout.addWidget(input_widget)
        return container

    @staticmethod
    def _unwrap_input(cell_widget: Optional[QWidget]) -> Optional[QWidget]:
        """Given the colored-margin wrapper container set via setCellWidget,
        return the actual QComboBox/QLineEdit inside it. Falls back to the
        widget itself if it isn't wrapped (keeps this safe to call on any
        cell widget, wrapped or not)."""
        if cell_widget is None:
            return None
        layout = cell_widget.layout()
        if layout is not None and layout.count() > 0:
            inner = layout.itemAt(0).widget()
            if inner is not None:
                return inner
        return cell_widget

    # ─── Tab / page management ───────────────────────────────────────

    def _add_page(self, widget, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        self.stack.addWidget(scroll)

        btn = QPushButton(name)
        btn.setObjectName("subPageTab")
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setMinimumWidth(TAB_MIN_WIDTH)
        btn.setMaximumWidth(TAB_MAX_WIDTH)
        btn.setToolTip(name)
        # Elide long page names instead of letting the button grow.
        metrics = btn.fontMetrics()
        elided = metrics.elidedText(name, Qt.ElideRight, TAB_MAX_WIDTH - 24)
        btn.setText(elided)
        idx = self.stack.count() - 1
        btn.clicked.connect(lambda _=False, i=idx: self._set_page(i))
        # Insert before the trailing stretch so new tabs append to the right.
        self.tabs.insertWidget(self.tabs.count() - 1, btn)

    def _clear_stack(self):
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

    def _clear_tabs(self):
        # Remove every tab button but keep the trailing stretch item.
        while self.tabs.count() > 1:
            item = self.tabs.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _set_page(self, idx):
        self.stack.setCurrentIndex(idx)
        total = self.stack.count()
        self.badge.setText(f"Sayfa {idx + 1} / {total} · {'Genel Sayfa' if idx == 0 else 'Detay Sayfa'}")
        for i in range(self.tabs.count() - 1):  # skip trailing stretch
            item = self.tabs.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.setChecked(i == idx)
        # Keep the active tab visible when there's a horizontal scrollbar.
        if 0 <= idx < self.tabs.count() - 1:
            item = self.tabs.itemAt(idx)
            w = item.widget() if item else None
            if w:
                self.tabs_scroll.ensureWidgetVisible(w)

    # ─── Save / export ────────────────────────────────────────────────

    def _collect(self):
        summary = []
        lines = []
        for i, r in enumerate(self.data.summary):
            status_input = self._unwrap_input(self.summary_table.cellWidget(i, 3))
            description_input = self._unwrap_input(self.summary_table.cellWidget(i, 4))
            summary.append({
                "user_id": r.user_id, "contract_id": r.contract_id,
                "status": status_input.currentText() if status_input else "",
                "description": description_input.toPlainText() if description_input else "",
            })
        for key, t in self.detail_tables.items():
            for i, line in enumerate(t.property("lines")):
                location_input = self._unwrap_input(t.cellWidget(i, 3))
                note_input = self._unwrap_input(t.cellWidget(i, 4))
                delivery_loc_input = self._unwrap_input(t.cellWidget(i, 5))
                lines.append({
                    "user_id": line.user_id, "contract_id": line.contract_id,
                    "component_id": line.component_id, "serial_no": line.serial_no,
                    "serial_key": line.serial_key,
                    "internal_location": location_input.currentText() if location_input else "",
                    "note": note_input.text() if note_input else "",
                    "delivery_location": delivery_loc_input.text() if delivery_loc_input else "",
                })
        return summary, lines

    def _mark_dirty(self, *args):
        if not self._refreshing:
            self._dirty = True

    def _save_current(self, show_message: bool = True):
        s, l = self._collect()
        unassigned_count = sum(1 for r in s if int(r.get("user_id") or 0) <= 0)
        save_report_data(self.store, self.data, s, l)
        self._dirty = False
        if show_message:
            if unassigned_count:
                QMessageBox.information(
                    self, "Platform Teslimat Özeti",
                    "Rapor kaydedildi.\n\n"
                    f"Not: Kullanıcısı tanımsız olan {unassigned_count} sayfadaki değişiklikler "
                    "kaydedilmedi (önizlemede görünmeye devam edecek). Bu satırların kaydedilebilmesi "
                    "için ilgili teslimata bir kullanıcı atanmalı.",
                )
            else:
                QMessageBox.information(self, "Platform Teslimat Özeti", "Rapor kaydedildi.")
        self.refresh_preview()

    def save_report(self):
        if not self.data:
            QMessageBox.warning(self, "Platform Teslimat Özeti", "Önce raporu önizleyin.")
            return
        self._save_current(show_message=True)

    def export_excel(self):
        if not self.data:
            QMessageBox.warning(self, "Excel", "Önce raporu önizleyin.")
            return
        if self._dirty:
            self._save_current(show_message=False)
        path, _ = QFileDialog.getSaveFileName(
            self, "Platform Teslimat Özeti Excel Kaydet",
            f"{self.data.platform}_teslimat_ozeti.xlsx", "Excel (*.xlsx)",
        )
        if path:
            export_report_to_excel(
                load_report_data(self.store, self.data.platform, self._selected_user_ids(), self._current_contract_id()),
                Path(path),
            )
            QMessageBox.information(self, "Excel", f"Excel oluşturuldu:\n{path}")

    def closeEvent(self, event):
        if self._dirty:
            result = QMessageBox.question(
                self, "Kaydedilmemiş değişiklikler",
                "Platform Teslimat Özeti raporunda kaydedilmemiş değişiklikler var. Kaydetmeden çıkmak istiyor musunuz?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                event.ignore()
                return
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Table columns re-flow automatically (Stretch resize mode); nothing
        # extra to do here beyond letting Qt's layouts handle the growth.


STYLE = f'''
QDialog {{
    background: {COLOR_PAGE_BG};
    color: {COLOR_TEXT};
    font-weight: 600;
}}
QFrame#filterPanel, QFrame#reportCard {{
    background: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_PANEL_BORDER};
    border-radius: 16px;
}}

/* Section headings and filter labels must never carry a default Qt
   background — this is what produced the gray "blocks" behind titles like
   "Rapor Ayarları", "PLATFORM", etc. */
QLabel#panelTitle, QLabel#mainTitle, QLabel#filterLabel {{
    background: transparent;
    border: none;
    padding: 0;
}}
QLabel#panelTitle {{
    font-size: 16px;
    font-weight: 800;
    color: {COLOR_TEXT};
}}
QLabel#mainTitle {{
    font-size: 16px;
    font-weight: 800;
    color: {COLOR_TEXT};
}}
QLabel#filterLabel {{
    font-size: 11px;
    color: {COLOR_TEXT_MUTED};
    font-weight: 800;
    padding-top: 6px;
}}

QLabel#badge {{
    background: #dff3e8;
    color: #087a2f;
    border-radius: 11px;
    padding: 5px 10px;
}}

/* Summary info cards (Toplam Sayfa / Kullanıcı / Sözleşme) */

QWidget#statHost {{
    background: transparent;
    border: none;
}}
QFrame#statCard {{
    background: #ffffff;
    border: 1px solid #bfd5f2;
    border-radius: 14px;
}}
QLabel#statCardLabel {{
    background: transparent;
    border: none;
    font-size: 10px;
    font-weight: 800;
    color: {COLOR_TEXT_MUTED};
    letter-spacing: 0.4px;
}}
QLabel#statCardValue {{
    background: transparent;
    border: none;
    font-size: 22px;
    font-weight: 900;
    color: {COLOR_HEADER_COL};
}}

QComboBox, QLineEdit {{
    background: #f8fbff;
    color: {COLOR_TEXT};
    border: 1px solid #bfd5f2;
    border-radius: 10px;
    padding: 7px 11px;
    min-height: 22px;
    font-weight: 800;
}}
QComboBox:hover, QLineEdit:hover {{
    border-color: #7fb2f0;
    background: #ffffff;
}}
QComboBox:focus, QLineEdit:focus {{
    border: 2px solid #2b7ddd;
    background: #ffffff;
}}
QComboBox[placeholder="true"], UserMultiSelectWidget[placeholder="true"], QLabel#userMultiSelectText[placeholder="true"] {{
    color: {COLOR_TEXT_MUTED};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left: 1px solid #d7e6f8;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
    background: #ffffff;
}}
QComboBox::down-arrow {{
    image: url("{ARROW_ICON_PATH}");
    width: 10px;
    height: 6px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    color: {COLOR_TEXT};
    border: 1px solid #bfd5f2;
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: #dbeafe;
    selection-color: {COLOR_TEXT};
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 6px 8px;
}}

QFrame#userMultiSelectDisplay {{
    background: #f8fbff;
    border: 1px solid #bfd5f2;
    border-radius: 10px;
}}
QFrame#userMultiSelectDisplay:hover {{
    border-color: #7fb2f0;
    background: #ffffff;
}}
QLabel#userMultiSelectText {{
    color: {COLOR_TEXT};
    background: transparent;
    border: none;
    font-weight: 900;
    font-size: 13px;
}}
QLabel#userMultiSelectText[placeholder="true"] {{
    color: {COLOR_TEXT_MUTED};
}}
QLabel#userMultiSelectChevron {{
    color: #0b4aa2;
    background: transparent;
    border: none;
    font-size: 17px;
    font-weight: 900;
}}

QPushButton {{
    border: 1px solid #bfd5f2;
    border-radius: 10px;
    padding: 9px 16px;
    min-height: 18px;
    background: #ffffff;
    color: #003b83;
    font-weight: 900;
}}
QPushButton:hover {{
    background: #eaf4ff;
    border-color: #7fb2f0;
}}
QPushButton#reportPrimaryButton {{
    background: #0b4aa2;
    color: white;
    border-color: #0b4aa2;
}}
QPushButton#reportPrimaryButton:hover {{
    background: #075bd8;
    border-color: #075bd8;
}}
QPushButton#reportSecondaryButton {{
    background: #ffffff;
}}
QPushButton#reportSecondaryButton:hover {{
    background: #eaf4ff;
}}

/* Sub-page tab strip: fixed-width, never stretched, left-aligned */
QPushButton#subPageTab {{
    background: #ffffff;
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_PANEL_BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 800;
    text-align: center;
}}
QPushButton#subPageTab:hover {{
    background: #eaf4ff;
    border-color: #7fb2f0;
}}
QPushButton#subPageTab:checked {{
    background: {COLOR_HEADER_COL};
    color: white;
    border-color: {COLOR_HEADER_COL};
}}

QScrollArea#tabsScroll, QScrollArea#tabsScroll QWidget, QWidget#tabsHost {{
    background: transparent;
    border: none;
}}
QScrollArea#tabsScroll QScrollBar:horizontal {{
    background: #eef4fb;
    height: 8px;
    margin: 0 2px;
    border-radius: 4px;
}}
QScrollArea#tabsScroll QScrollBar::handle:horizontal {{
    background: #9fb6d4;
    min-width: 30px;
    border-radius: 4px;
}}
QScrollArea#tabsScroll QScrollBar::handle:horizontal:hover {{
    background: #6f8fb8;
}}
QScrollArea#tabsScroll QScrollBar::add-line:horizontal,
QScrollArea#tabsScroll QScrollBar::sub-line:horizontal {{
    width: 1px;
    border: none;
    background: transparent;
}}

QHeaderView::section {{
    background: {COLOR_HEADER_COL};
    color: {COLOR_HEADER_TEXT};
    font-weight: 800;
    padding: 8px;
    border: 1px solid {COLOR_GRID_BORDER};
}}
QTableWidget {{
    gridline-color: {COLOR_GRID_BORDER};
    background: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_GRID_BORDER};
    selection-background-color: #dbeafe;
    selection-color: {COLOR_TEXT};
}}
QTableWidget::item {{
    border: 0;
    padding: 0px;
}}

QScrollBar:vertical {{
    background: #eef4fb;
    border: none;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: #9fb6d4;
    min-height: 34px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: #6f8fb8;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 1px;
    border: none;
    background: transparent;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: #eef4fb;
    border: none;
    height: 10px;
    margin: 2px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: #9fb6d4;
    min-width: 34px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #6f8fb8;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 1px;
    border: none;
    background: transparent;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QLabel#emptyState {{
    background: transparent;
    border: none;
    color: {COLOR_TEXT_MUTED};
    font-size: 16px;
    font-weight: 800;
}}
QTextEdit {{
    border: 1px solid {COLOR_INPUT_BORDER};
    border-radius: 8px;
    background: white;
}}
'''
