from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QRect, Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

NAVY = "#0F1F3D"
GRID = "#E2E8F0"
MUTED = "#7A8AA3"
GREEN = "#22C55E"
PALE_GREEN = "#D7FBE8"
CELL_OFF = "#EAF0F7"
ROW_ALT = "#F6F9FD"


class ComponentCellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(Qt.UserRole) or {}
        painter.save()
        rect = option.rect
        bg = QColor(ROW_ALT if index.row() % 2 else "#FFFFFF")
        if option.state & QStyle.State_Selected:
            bg = QColor("#EAF2FF")
        painter.fillRect(rect, bg)
        painter.setPen(QPen(QColor(GRID)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomRight())

        active = bool(data.get("active", True))
        dot_color = QColor("#16A34A" if active else "#94A3B8")
        painter.setBrush(dot_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect.left() + 10, rect.top() + 21, 6, 6)

        painter.setPen(QColor("#081426"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRect(rect.left() + 24, rect.top() + 8, rect.width() - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, str(data.get("name") or ""))

        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        meta = str(data.get("unit") or "Adet")
        note = str(data.get("note") or "").strip()
        if note:
            meta = f"{meta} · {note}"
        painter.drawText(QRect(rect.left() + 24, rect.top() + 27, rect.width() - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, meta)
        painter.restore()


class AssignmentDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        checked = bool(index.data(Qt.UserRole))
        painter.save()
        rect = option.rect
        painter.fillRect(rect, QColor(ROW_ALT if index.row() % 2 else "#FFFFFF"))
        painter.setPen(QPen(QColor(GRID)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomRight())
        size = 20
        box = QRect(rect.center().x() - size // 2, rect.center().y() - size // 2, size, size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PALE_GREEN if checked else CELL_OFF))
        painter.drawRoundedRect(box, 6, 6)
        if checked:
            painter.setPen(QColor("#16A34A"))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(box, Qt.AlignCenter, "✓")
        painter.restore()


class PlatformHeader(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.platforms: list[dict[str, Any]] = []
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(True)
        self.setFixedHeight(72)

    def set_platforms(self, platforms: list[dict[str, Any]]):
        self.platforms = list(platforms or [])
        self.viewport().update()

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        s.setHeight(72)
        return s

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if not rect.isValid():
            return
        platform = self.platforms[logicalIndex] if 0 <= logicalIndex < len(self.platforms) else {}
        name = str(platform.get("name") or "")
        count = int(platform.get("comp_count") or 0)
        active = bool(platform.get("is_active", True))
        excluded = bool(platform.get("is_excluded", False))
        colors = ["#DBEAFE", "#DCFCE7", "#FFEDD5", "#F3E8FF", "#CCFBF1", "#FCE7F3"]
        avatar_color = colors[logicalIndex % len(colors)]
        painter.save()
        painter.fillRect(rect, QColor(NAVY))
        painter.setPen(QPen(QColor("#B7C6DC")))
        painter.drawLine(rect.topRight(), rect.bottomRight())

        av = QRect(rect.center().x() - 10, rect.top() + 8, 20, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(avatar_color))
        painter.drawRoundedRect(av, 5, 5)
        painter.setPen(QColor("#0B2344"))
        f = painter.font()
        f.setBold(True)
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(av, Qt.AlignCenter, (name[:1] or "?").upper())

        painter.setPen(QColor("#FFFFFF" if active else "#AAB6C7"))
        f.setPointSize(7)
        painter.setFont(f)
        painter.drawText(QRect(rect.left() + 4, rect.top() + 29, rect.width() - 8, 15), Qt.AlignCenter, name.upper())
        painter.setPen(QColor("#89A2C0"))
        f.setBold(False)
        f.setPointSize(6)
        painter.setFont(f)
        suffix = " · hariç" if excluded else ""
        painter.drawText(QRect(rect.left() + 4, rect.top() + 46, rect.width() - 8, 14), Qt.AlignCenter, f"{count} bileşen{suffix}")
        painter.restore()


class PlatformComponentManagerDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, store, parent=None, initial_tab=0):
        super().__init__(parent)
        self.store = store
        self.initial_tab = initial_tab  # accepted for compatibility; intentionally unused
        self.platforms: list[dict[str, Any]] = []
        self.components: list[dict[str, Any]] = []
        self.changed = False
        self.change_count = 0
        self._logo_path = ""
        self._syncing_scroll = False
        self.setWindowTitle("Platform & Bileşen")
        self.resize(980, 620)
        self.setMinimumSize(780, 500)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self._build()
        self._load_data()

    def _build(self):
        outer = QStackedLayout(self)
        outer.setStackingMode(QStackedLayout.StackAll)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addWidget(page)

        self.topbar = QFrame(objectName="pcTopbar")
        self.topbar.setFixedHeight(52)
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(14, 0, 10, 0)
        brand = QLabel("STS", objectName="pcBrand")
        file_name = QLabel(Path(str(getattr(self.store, "path", ""))).name or str(getattr(self.store, "path", "")), objectName="pcFile")
        add_component = QPushButton("+ Bileşen", objectName="pcTopButton")
        add_component.clicked.connect(lambda: self._open_component_popover(None))
        add_platform = QPushButton("+ Platform", objectName="pcTopButton")
        add_platform.clicked.connect(lambda: self._open_platform_popover(None))
        close = QPushButton("✕", objectName="pcCloseButton")
        close.clicked.connect(self.reject)
        top.addWidget(brand)
        top.addWidget(file_name, 1)
        top.addWidget(add_component)
        top.addWidget(add_platform)
        top.addWidget(close)
        root.addWidget(self.topbar)

        self.toolbar = QFrame(objectName="pcToolbar")
        self.toolbar.setFixedHeight(38)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(14, 0, 14, 0)
        hint = QLabel("Hücreye tıkla → ata / kaldır · Başlığa çift tık veya sağ tık → düzenle / aktifle al / sil", objectName="pcHint")
        self.change_badge = QLabel("Değişiklik yok", objectName="pcBadge")
        tb.addWidget(hint, 1)
        tb.addWidget(self.change_badge)
        root.addWidget(self.toolbar)

        self.matrix_area = QFrame(objectName="pcMatrixArea")
        matrix_lay = QHBoxLayout(self.matrix_area)
        matrix_lay.setContentsMargins(0, 0, 0, 0)
        matrix_lay.setSpacing(0)

        self.frozen = QTableWidget()
        self.frozen.setObjectName("pcFrozen")
        self.frozen.setFixedWidth(220)
        self.frozen.setColumnCount(1)
        self.frozen.setHorizontalHeaderLabels(["BİLEŞEN ↓"])
        self.frozen.horizontalHeader().setFixedHeight(72)
        self.frozen.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.frozen.verticalHeader().setVisible(False)
        self.frozen.setShowGrid(False)
        self.frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen.setSelectionMode(QAbstractItemView.NoSelection)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setItemDelegate(ComponentCellDelegate(self.frozen))
        self.frozen.setContextMenuPolicy(Qt.CustomContextMenu)
        self.frozen.customContextMenuRequested.connect(self._component_context_menu)
        self.frozen.cellDoubleClicked.connect(lambda r, _c: self._open_component_popover(self.components[r] if 0 <= r < len(self.components) else None))
        matrix_lay.addWidget(self.frozen)

        self.matrix = QTableWidget()
        self.matrix.setObjectName("pcMatrix")
        self.matrix.setShowGrid(False)
        self.matrix.verticalHeader().setVisible(False)
        self.matrix.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.matrix.setSelectionMode(QAbstractItemView.NoSelection)
        self.matrix.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.matrix.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.matrix.setItemDelegate(AssignmentDelegate(self.matrix))
        header = PlatformHeader(Qt.Horizontal, self.matrix)
        self.matrix.setHorizontalHeader(header)
        self.matrix.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.matrix.horizontalHeader().customContextMenuRequested.connect(self._platform_context_menu)
        self.matrix.horizontalHeader().sectionDoubleClicked.connect(self._open_platform_by_index)
        self.matrix.cellClicked.connect(self._toggle_assignment)
        matrix_lay.addWidget(self.matrix, 1)
        root.addWidget(self.matrix_area, 1)

        self.frozen.verticalScrollBar().valueChanged.connect(self.matrix.verticalScrollBar().setValue)
        self.matrix.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue)

        self.footer = QFrame(objectName="pcFooter")
        self.footer.setFixedHeight(46)
        ft = QHBoxLayout(self.footer)
        ft.setContentsMargins(14, 0, 14, 0)
        self.footer_msg = QLabel("Değişiklik yok", objectName="pcFooterMsg")
        cancel = QPushButton("Vazgeç", objectName="pcFooterButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        save.clicked.connect(self._save_and_close)
        ft.addWidget(self.footer_msg, 1)
        ft.addWidget(cancel)
        ft.addWidget(save)
        root.addWidget(self.footer)

        self.overlay = QWidget(self)
        self.overlay.setObjectName("pcOverlay")
        self.overlay.hide()
        overlay_lay = QVBoxLayout(self.overlay)
        overlay_lay.setContentsMargins(0, 0, 0, 0)
        overlay_lay.addStretch(1)
        self.popover = QFrame(objectName="pcPopover")
        self.popover.hide()
        overlay_lay.addWidget(self.popover, 0, Qt.AlignCenter)
        overlay_lay.addStretch(1)
        outer.addWidget(self.overlay)
        outer.setCurrentWidget(page)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
QDialog {{ background:#DCE4EF; }}
QFrame#pcTopbar {{ background:{NAVY}; border-top-left-radius:10px; border-top-right-radius:10px; }}
QLabel#pcBrand {{ color:white; background:#23385F; border-radius:5px; padding:3px 9px; font-weight:900; }}
QLabel#pcFile {{ color:#8EA3C3; background:#1B2E51; border-radius:5px; padding:3px 9px; font-size:10px; }}
QPushButton#pcTopButton {{ background:#243B63; color:white; border:1px solid #647795; border-radius:5px; padding:5px 12px; font-weight:800; font-size:11px; }}
QPushButton#pcCloseButton {{ background:#203453; color:#B9C5D8; border:none; border-radius:8px; min-width:24px; min-height:24px; font-weight:900; }}
QFrame#pcToolbar {{ background:#F8FAFC; border-bottom:1px solid {GRID}; }}
QLabel#pcHint, QLabel#pcFooterMsg {{ color:{MUTED}; font-size:10px; }}
QLabel#pcBadge {{ color:#91A0B8; background:#F0F4FA; border:1px solid #E2E8F0; border-radius:6px; padding:4px 9px; font-size:10px; }}
QFrame#pcMatrixArea {{ background:white; }}
QTableWidget#pcFrozen, QTableWidget#pcMatrix {{ background:white; border:none; gridline-color:{GRID}; alternate-background-color:{ROW_ALT}; }}
QTableWidget#pcFrozen QHeaderView::section {{ background:{NAVY}; color:#84A0C2; border-right:1px solid #B7C6DC; border-bottom:1px solid #B7C6DC; font-weight:900; font-size:9px; padding-left:8px; }}
QScrollBar:vertical {{ background:#F1F5F9; width:10px; }}
QScrollBar::handle:vertical {{ background:#CBD5E1; border-radius:5px; min-height:24px; }}
QScrollBar:horizontal {{ background:#F1F5F9; height:10px; }}
QScrollBar::handle:horizontal {{ background:#CBD5E1; border-radius:5px; min-width:24px; }}
QFrame#pcFooter {{ background:#F8FAFC; border-top:1px solid {GRID}; border-bottom-left-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#pcFooterButton {{ background:white; color:#0F1F3D; border:1px solid #D5DEEA; border-radius:7px; padding:7px 14px; font-weight:800; }}
QPushButton#pcPrimaryButton {{ background:#3769E8; color:white; border:none; border-radius:7px; padding:7px 16px; font-weight:900; }}
QWidget#pcOverlay {{ background:rgba(15,31,61,90); }}
QFrame#pcPopover {{ background:white; border:1px solid #D8E2EF; border-radius:12px; }}
QLabel#popTitle {{ color:#12223D; font-size:14px; font-weight:900; }}
QLabel#popSub {{ color:#94A3B8; font-size:10px; }}
QLabel#popField {{ color:#53657E; font-size:10px; font-weight:900; }}
QLineEdit, QComboBox {{ border:1px solid #CBD7E7; border-radius:6px; padding:7px; background:white; }}
QPushButton#dangerButton {{ background:#FFF5F5; color:#DC2626; border:1px solid #FCA5A5; border-radius:7px; padding:7px 14px; font-weight:800; }}
""")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.rect())

    def _load_data(self):
        self.platforms = self._read_platforms()
        self.components = self._read_components()
        self._refresh_matrix()

    def _read_platforms(self) -> list[dict[str, Any]]:
        if hasattr(self.store, "load_platforms"):
            return [dict(x) for x in self.store.load_platforms()]
        names = list(self.store.platform_names() if hasattr(self.store, "platform_names") else [])
        excluded = set(self.store.load_excluded_platforms() if hasattr(self.store, "load_excluded_platforms") else [])
        comps = self._read_components()
        return [{"id": i + 1, "name": n, "is_active": n not in excluded, "is_excluded": n in excluded, "sort_order": i, "comp_count": sum(1 for c in comps if (c.get("platforms") or {}).get(n))} for i, n in enumerate(names)]

    def _read_components(self) -> list[dict[str, Any]]:
        if hasattr(self.store, "load_components_full"):
            return [dict(x) for x in self.store.load_components_full()]
        out = []
        for i, comp in enumerate(self.store.load_components() if hasattr(self.store, "load_components") else []):
            out.append({
                "id": i + 1,
                "name": str(getattr(comp, "name", "")),
                "unit": str(getattr(comp, "unit", "Adet") or "Adet"),
                "active": bool(getattr(comp, "active", True)),
                "note": str(getattr(comp, "note", "") or ""),
                "platforms": dict(getattr(comp, "platforms", {}) or {}),
            })
        return out

    def _refresh_matrix(self):
        self.frozen.blockSignals(True)
        self.matrix.blockSignals(True)
        rows = len(self.components)
        cols = len(self.platforms)
        self.frozen.setRowCount(rows)
        self.matrix.setRowCount(rows)
        self.matrix.setColumnCount(cols)
        self.matrix.horizontalHeader().set_platforms(self.platforms)
        self.matrix.setHorizontalHeaderLabels([str(p.get("name") or "") for p in self.platforms])
        for c in range(cols):
            self.matrix.setColumnWidth(c, 104)
        for r, comp in enumerate(self.components):
            self.frozen.setRowHeight(r, 38)
            self.matrix.setRowHeight(r, 38)
            item = QTableWidgetItem(str(comp.get("name") or ""))
            item.setData(Qt.UserRole, comp)
            self.frozen.setItem(r, 0, item)
            platforms = comp.get("platforms") or {}
            for c, platform in enumerate(self.platforms):
                assigned = bool(platforms.get(str(platform.get("name") or ""), False))
                cell = QTableWidgetItem("✓" if assigned else "")
                cell.setData(Qt.UserRole, assigned)
                self.matrix.setItem(r, c, cell)
        self.frozen.blockSignals(False)
        self.matrix.blockSignals(False)
        self._update_change_text()

    def _update_change_text(self):
        text = "Değişiklik yok" if self.change_count <= 0 else f"{self.change_count} değişiklik kaydedildi"
        self.change_badge.setText(text)
        self.footer_msg.setText(text)

    def _mark_saved(self, message: str):
        self.changed = True
        self.change_count += 1
        self.footer_msg.setText(message)
        self.change_badge.setText(f"{self.change_count} değişiklik kaydedildi")
        self.settings_saved.emit()

    def _component_context_menu(self, pos):
        row = self.frozen.rowAt(pos.y())
        if row < 0 or row >= len(self.components):
            return
        comp = self.components[row]
        menu = QMenu(self)
        edit = menu.addAction("✏️ Düzenle")
        active_action = menu.addAction("▶ Aktife Al" if not comp.get("active", True) else "⏸ Pasife Al")
        delete = menu.addAction("🗑 Sil")
        chosen = menu.exec(self.frozen.viewport().mapToGlobal(pos))
        if chosen == edit:
            self._open_component_popover(comp)
        elif chosen == active_action:
            updated = dict(comp)
            updated["active"] = not bool(comp.get("active", True))
            self._write_component(updated)
            self._mark_saved("Bileşen durumu güncellendi")
            self._load_data()
        elif chosen == delete:
            if QMessageBox.question(self, "Bileşen Sil", f"{comp.get('name')} silinsin mi?") == QMessageBox.Yes:
                self.store.delete_component(str(comp.get("name") or ""))
                self._mark_saved("Bileşen silindi")
                self._load_data()

    def _platform_context_menu(self, pos):
        col = self.matrix.horizontalHeader().logicalIndexAt(pos)
        if col < 0 or col >= len(self.platforms):
            return
        platform = self.platforms[col]
        menu = QMenu(self)
        edit = menu.addAction("✏️ Düzenle")
        active_action = menu.addAction("▶ Aktife Al" if not platform.get("is_active", True) else "⏸ Pasife Al")
        delete = menu.addAction("🗑 Sil")
        chosen = menu.exec(self.matrix.horizontalHeader().mapToGlobal(pos))
        if chosen == edit:
            self._open_platform_popover(platform)
        elif chosen == active_action:
            name = str(platform.get("name") or "")
            self.store.update_platform(name, name, not bool(platform.get("is_active", True)), bool(platform.get("is_excluded", False)), sort_order=platform.get("sort_order"))
            self._mark_saved("Platform durumu güncellendi")
            self._load_data()
        elif chosen == delete:
            if QMessageBox.question(self, "Platform Sil", f"{platform.get('name')} silinsin mi?") == QMessageBox.Yes:
                self.store.delete_platform(str(platform.get("name") or ""))
                self._mark_saved("Platform silindi")
                self._load_data()

    def _open_platform_by_index(self, index: int):
        if 0 <= index < len(self.platforms):
            self._open_platform_popover(self.platforms[index])

    def _toggle_assignment(self, row: int, col: int):
        if row < 0 or col < 0 or row >= len(self.components) or col >= len(self.platforms):
            return
        comp = dict(self.components[row])
        platform = str(self.platforms[col].get("name") or "")
        platforms = dict(comp.get("platforms") or {})
        platforms[platform] = not bool(platforms.get(platform, False))
        comp["platforms"] = platforms
        self._write_component(comp)
        self._mark_saved("Atama güncellendi")
        self._load_data()

    def _write_component(self, comp: dict[str, Any]):
        if hasattr(self.store, "write_component"):
            self.store.write_component(comp)
            return
        items = self._read_components()
        name = str(comp.get("name") or "")
        replaced = False
        for i, item in enumerate(items):
            if str(item.get("name") or "") == name:
                items[i] = comp
                replaced = True
                break
        if not replaced:
            items.append(comp)
        self.store.write_components(items, actor=self.store.current_actor() if hasattr(self.store, "current_actor") else "Sistem")

    def _open_component_popover(self, comp: dict[str, Any] | None):
        is_new = comp is None
        self._clear_popover()
        self.popover.setFixedWidth(330)
        lay = QVBoxLayout(self.popover)
        lay.setContentsMargins(14, 12, 14, 12)
        title_row = QHBoxLayout()
        icon = QLabel("+", objectName="pcBrand")
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("Yeni Bileşen" if is_new else str(comp.get("name") or "Bileşen"), objectName="popTitle"))
        title_box.addWidget(QLabel("Bileşen bilgilerini girin", objectName="popSub"))
        x = QPushButton("×", objectName="pcFooterButton")
        x.clicked.connect(self._hide_popover)
        title_row.addWidget(icon)
        title_row.addLayout(title_box, 1)
        title_row.addWidget(x)
        lay.addLayout(title_row)

        grid = QGridLayout()
        name = QLineEdit(str((comp or {}).get("name") or ""))
        name.setPlaceholderText("Bileşen adı")
        unit = QComboBox()
        unit.addItems(["Adet", "Takım", "Set", "Metre", "Kg", "Litre"])
        current_unit = str((comp or {}).get("unit") or "Adet")
        if current_unit not in [unit.itemText(i) for i in range(unit.count())]:
            unit.addItem(current_unit)
        unit.setCurrentText(current_unit)
        note = QLineEdit(str((comp or {}).get("note") or ""))
        note.setPlaceholderText("İsteğe bağlı kısa not...")
        active = QCheckBox("Aktif")
        active.setChecked(bool((comp or {}).get("active", True)))
        grid.addWidget(QLabel("BİLEŞEN ADI", objectName="popField"), 0, 0)
        grid.addWidget(QLabel("BİRİM", objectName="popField"), 0, 1)
        grid.addWidget(name, 1, 0)
        grid.addWidget(unit, 1, 1)
        grid.addWidget(QLabel("NOT", objectName="popField"), 2, 0, 1, 2)
        grid.addWidget(note, 3, 0, 1, 2)
        grid.addWidget(QLabel("DURUM", objectName="popField"), 4, 0, 1, 2)
        grid.addWidget(active, 5, 0, 1, 2)
        lay.addLayout(grid)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("İptal", objectName="dangerButton")
        cancel.clicked.connect(self._hide_popover)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

        def do_save():
            clean = name.text().strip()
            if not clean:
                QMessageBox.warning(self, "Eksik", "Bileşen adı girin.")
                return
            old_platforms = dict((comp or {}).get("platforms") or {})
            payload = {
                "id": (comp or {}).get("id"),
                "old_name": str((comp or {}).get("name") or clean),
                "name": clean,
                "unit": unit.currentText().strip() or "Adet",
                "note": note.text().strip(),
                "active": active.isChecked(),
                "platforms": old_platforms,
            }
            self._write_component(payload)
            self._hide_popover()
            self._mark_saved("Bileşen kaydedildi")
            self._load_data()

        save.clicked.connect(do_save)
        self._show_popover()

    def _open_platform_popover(self, platform: dict[str, Any] | None):
        is_new = platform is None
        self._logo_path = ""
        self._clear_popover()
        self.popover.setFixedWidth(330)
        lay = QVBoxLayout(self.popover)
        lay.setContentsMargins(14, 12, 14, 12)
        title_row = QHBoxLayout()
        icon = QLabel("+", objectName="pcBrand")
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("Yeni Platform" if is_new else str(platform.get("name") or "Platform"), objectName="popTitle"))
        title_box.addWidget(QLabel("Platform adı girin", objectName="popSub"))
        x = QPushButton("×", objectName="pcFooterButton")
        x.clicked.connect(self._hide_popover)
        title_row.addWidget(icon)
        title_row.addLayout(title_box, 1)
        title_row.addWidget(x)
        lay.addLayout(title_row)

        name = QLineEdit(str((platform or {}).get("name") or ""))
        name.setPlaceholderText("ÖRN: AKINCI")
        name.textEdited.connect(lambda txt: name.setText(txt.upper()))
        active = QCheckBox("Aktif")
        active.setChecked(bool((platform or {}).get("is_active", True)))
        excluded = QCheckBox("Hariç tut")
        excluded.setChecked(bool((platform or {}).get("is_excluded", False)))
        logo_btn = QPushButton("📷  Logo ekle (opsiyonel)\nPNG, JPG, WEBP · Maks 2 MB", objectName="pcFooterButton")
        logo_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        logo_btn.clicked.connect(lambda: self._pick_logo(logo_btn))
        lay.addWidget(QLabel("PLATFORM ADI (BÜYÜK HARF)", objectName="popField"))
        lay.addWidget(name)
        lay.addWidget(active)
        lay.addWidget(excluded)
        lay.addWidget(logo_btn)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("İptal", objectName="dangerButton")
        cancel.clicked.connect(self._hide_popover)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

        def do_save():
            clean = name.text().strip().upper()
            if not clean:
                QMessageBox.warning(self, "Eksik", "Platform adı girin.")
                return
            old_name = str((platform or {}).get("name") or clean)
            if is_new:
                self.store.create_platform(clean)
                old_name = clean
            self.store.update_platform(old_name, clean, active.isChecked(), excluded.isChecked(), sort_order=(platform or {}).get("sort_order"))
            if self._logo_path:
                raw = Path(self._logo_path).read_bytes()
                ext = Path(self._logo_path).suffix.lower().lstrip(".")
                self.store.set_platform_logo_bytes(clean, raw, ext=ext)
            self._hide_popover()
            self._mark_saved("Platform kaydedildi")
            self._load_data()

        save.clicked.connect(do_save)
        self._show_popover()

    def _pick_logo(self, button: QPushButton):
        p, _ = QFileDialog.getOpenFileName(self, "Logo seç", str(Path(getattr(self.store, "path", ".")).parent), "Resim Dosyaları (*.png *.jpg *.jpeg *.webp)")
        if p:
            self._logo_path = p
            button.setText(Path(p).name)

    def _clear_popover(self):
        self.popover.hide()
        old = self.popover.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            QWidget().setLayout(old)

    def _show_popover(self):
        self.overlay.setGeometry(self.rect())
        self.overlay.show()
        self.popover.show()
        self.overlay.raise_()

    def _hide_popover(self):
        self.popover.hide()
        self.overlay.hide()

    def _save_and_close(self):
        if hasattr(self.store, "save"):
            self.store.save()
        if self.changed:
            self.settings_saved.emit()
        self.accept()
