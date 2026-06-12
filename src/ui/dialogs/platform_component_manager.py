from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QDrag, QPainter, QPen, QPixmap
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
        painter.drawEllipse(rect.left() + 10, rect.top() + 23, 6, 6)

        painter.setPen(QColor("#081426"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRect(rect.left() + 24, rect.top() + 10, rect.width() - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, str(data.get("name") or ""))

        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        meta = str(data.get("unit") or "Adet")
        note = str(data.get("note") or "").strip()
        if note:
            meta = f"{meta} · {note}"
        painter.drawText(QRect(rect.left() + 24, rect.top() + 30, rect.width() - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, meta)
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
        painter.setBrush(QColor("#DCFCE7" if checked else "#EEF2F8"))
        painter.drawRoundedRect(box, 6, 6)
        if checked:
            painter.setPen(QColor("#16A34A"))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(box, Qt.AlignCenter, "✓")
        painter.restore()



class ToggleSwitch(QWidget):
    """HTML sw benzeri kayan toggle switch."""
    toggled = __import__('PySide6.QtCore', fromlist=['Signal']).Signal(bool)

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 24)
        self._checked = checked
        self.setCursor(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool):
        self._checked = bool(v)
        self.update()

    def mousePressEvent(self, e):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QPainterPath
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track_color = QColor('#3B6FE8') if self._checked else QColor('#CBD5E1')
        p.setBrush(track_color)
        p.setPen(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 2, 42, 20), 10, 10)
        thumb_x = 20.0 if self._checked else 2.0
        p.setBrush(QColor('#FFFFFF'))
        p.drawEllipse(QRectF(thumb_x, 4, 16, 16))
        p.end()


class PlatformHeader(QHeaderView):
    columnDropped = Signal(int, int)
    columnDragMoved = Signal(int)
    columnDragEnded = Signal()

    _MIME_TYPE = "application/x-sts-platform-column"

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.platforms: list[dict[str, Any]] = []
        self._drag_enabled = True
        self._drag_start_pos = None
        self._drag_start_logical = -1
        self._preview_provider = None
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(True)
        self.setFixedHeight(80)

    def set_order_drag_enabled(self, enabled: bool):
        self._drag_enabled = bool(enabled)
        self.setAcceptDrops(self._drag_enabled)
        self.viewport().setAcceptDrops(self._drag_enabled)

    def set_preview_provider(self, provider):
        self._preview_provider = provider

    def _target_index_at(self, pos: QPoint) -> int:
        if self.count() <= 0:
            return 0
        x = pos.x()
        for visual in range(self.count()):
            logical = self.logicalIndex(visual)
            left = self.sectionViewportPosition(logical)
            right = left + self.sectionSize(logical)
            if x < left + max(1, (right - left) // 2):
                return visual
        return self.count()

    def mousePressEvent(self, event):
        if self._drag_enabled and event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_logical = self.logicalIndexAt(self._drag_start_pos)
        else:
            self._drag_start_pos = None
            self._drag_start_logical = -1
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_enabled
            and self._drag_start_pos is not None
            and self._drag_start_logical >= 0
            and event.buttons() & Qt.LeftButton
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength() >= 8
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(self._MIME_TYPE, str(self._drag_start_logical).encode("utf-8"))
            drag.setMimeData(mime)
            if self._preview_provider is not None:
                pix = self._preview_provider(self._drag_start_logical)
                if pix is not None and not pix.isNull():
                    drag.setPixmap(pix)
                    drag.setHotSpot(QPoint(min(pix.width() // 2, max(8, event.position().toPoint().x() - self.sectionViewportPosition(self._drag_start_logical) + 6)), 22))
            drag.exec(Qt.MoveAction)
            self.columnDragEnded.emit()
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            self.columnDragMoved.emit(self._target_index_at(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.columnDragEnded.emit()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not (self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE)):
            super().dropEvent(event)
            return
        try:
            source = int(bytes(event.mimeData().data(self._MIME_TYPE)).decode("utf-8"))
        except Exception:
            event.ignore()
            return
        self.columnDropped.emit(source, self._target_index_at(event.position().toPoint()))
        self.columnDragEnded.emit()
        event.acceptProposedAction()

    def set_platforms(self, platforms: list[dict[str, Any]]):
        self.platforms = list(platforms or [])
        self.viewport().update()

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        s.setHeight(80)
        return s

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if not rect.isValid():
            return
        platform = self.platforms[logicalIndex] if 0 <= logicalIndex < len(self.platforms) else {}
        name = str(platform.get("name") or "")
        count = int(platform.get("comp_count") or 0)
        excluded = bool(platform.get("is_excluded", False))

        # HTML'deki _PLAT_COLORS ile birebir aynı
        bg_colors = ["#EFF6FF","#F0FDF4","#FFF7ED","#FDF4FF","#F0FDFA","#FEF3C7","#FEE2E2","#E0F2FE"]
        fg_colors = ["#1D4ED8","#15803D","#C2410C","#7E22CE","#0D9488","#92400E","#991B1B","#075985"]
        av_bg = bg_colors[logicalIndex % len(bg_colors)]
        av_fg = fg_colors[logicalIndex % len(fg_colors)]

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # lacivert arka plan
        painter.fillRect(rect, QColor(NAVY))

        # sağ ayırıcı çizgi
        painter.setPen(QPen(QColor("rgba(255,255,255,0.08)")))
        painter.drawLine(rect.topRight(), rect.bottomRight())

        cx = rect.center().x()

        # avatar daire (HTML: 30x30, border-radius:8px)
        av_size = 30
        av_x = cx - av_size // 2
        av_y = rect.top() + 10
        av_rect = QRect(av_x, av_y, av_size, av_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(av_bg))
        painter.drawRoundedRect(av_rect, 8, 8)

        # avatar harf
        painter.setPen(QColor(av_fg))
        f = painter.font()
        f.setBold(True)
        f.setPointSize(11)
        painter.setFont(f)
        painter.drawText(av_rect, Qt.AlignCenter, (name[:1] or "?").upper())

        # platform adı (beyaz, bold, 10pt, letter-spacing)
        painter.setPen(QColor("#FFFFFF"))
        f.setPointSize(10)
        f.setBold(True)
        painter.setFont(f)
        name_rect = QRect(rect.left() + 4, av_y + av_size + 5, rect.width() - 8, 16)
        painter.drawText(name_rect, Qt.AlignCenter, name.upper())

        # bileşen sayısı (soluk, 9pt)
        painter.setPen(QColor("#FFFFFF"))
        f.setPointSize(8)
        f.setBold(False)
        painter.setFont(f)
        suffix = " · hariç" if excluded else ""
        cnt_rect = QRect(rect.left() + 4, name_rect.bottom() + 1, rect.width() - 8, 14)
        painter.drawText(cnt_rect, Qt.AlignCenter, f"{count} bileşen{suffix}")

        painter.restore()


class DraggableComponentTable(QTableWidget):
    rowMoved = Signal(int, int)
    rowDragMoved = Signal(int)
    rowDragEnded = Signal()

    _MIME_TYPE = "application/x-sts-component-row"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_enabled = True
        self._drag_start_pos = None
        self._drag_start_row = -1
        self._preview_provider = None
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)

    def set_preview_provider(self, provider):
        self._preview_provider = provider

    def set_order_drag_enabled(self, enabled: bool):
        self._drag_enabled = bool(enabled)
        self.setDragEnabled(self._drag_enabled)
        self.setAcceptDrops(self._drag_enabled)
        self.viewport().setAcceptDrops(self._drag_enabled)

    def mousePressEvent(self, event):
        if self._drag_enabled and event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_row = self.rowAt(self._drag_start_pos.y())
        else:
            self._drag_start_pos = None
            self._drag_start_row = -1
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_enabled
            and self._drag_start_pos is not None
            and self._drag_start_row >= 0
            and event.buttons() & Qt.LeftButton
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength() >= 8
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(self._MIME_TYPE, str(self._drag_start_row).encode("utf-8"))
            drag.setMimeData(mime)
            if self._preview_provider is not None:
                pix = self._preview_provider(self._drag_start_row)
                if pix is not None and not pix.isNull():
                    drag.setPixmap(pix)
                    row_y = self.rowViewportPosition(self._drag_start_row)
                    drag.setHotSpot(QPoint(28, max(12, self._drag_start_pos.y() - row_y + 6)))
            drag.exec(Qt.MoveAction)
            self.rowDragEnded.emit()
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            target_row = self.rowAt(event.position().toPoint().y())
            self.rowDragMoved.emit(self.rowCount() if target_row < 0 else target_row)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.rowDragEnded.emit()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not (self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE)):
            super().dropEvent(event)
            return
        try:
            source_row = int(bytes(event.mimeData().data(self._MIME_TYPE)).decode("utf-8"))
        except Exception:
            event.ignore()
            return
        target_row = self.rowAt(event.position().toPoint().y())
        if target_row < 0:
            target_row = self.rowCount()
        self.rowMoved.emit(source_row, target_row)
        self.rowDragEnded.emit()
        event.acceptProposedAction()


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
        self._syncing_platform_header = False
        self._component_order_changed = False
        self._platform_order_changed = False
        self.setWindowTitle("Platform ve Bileşen Yönetimi")
        self.setMinimumSize(600, 460)
        self.setWindowFlags(self.windowFlags() | Qt.Window | Qt.WindowMaximizeButtonHint)
        self._build()
        self._load_data()
        self._auto_size()

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
        top.addWidget(brand)
        top.addWidget(file_name, 1)
        top.addWidget(add_component)
        top.addWidget(add_platform)
        root.addWidget(self.topbar)

        self.toolbar = QFrame(objectName="pcToolbar")
        self.toolbar.setFixedHeight(38)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(14, 0, 14, 0)
        hint = QLabel("Hücreye tıkla → ata / kaldır · Sol bileşen alanı ve platform başlığı sürükle → sırala", objectName="pcHint")
        # Arama çubuğu
        self.search_box = QLineEdit()
        self.search_box.setObjectName("pcSearch")
        self.search_box.setPlaceholderText("🔍  Bileşen ara...")
        self.search_box.setFixedWidth(200)
        self.search_box.setFixedHeight(26)
        self.search_box.textChanged.connect(self._filter_components)
        self.change_badge = QLabel("Değişiklik yok", objectName="pcBadge")
        tb.addWidget(hint, 1)
        tb.addWidget(self.search_box)
        tb.addSpacing(8)
        tb.addWidget(self.change_badge)
        root.addWidget(self.toolbar)

        self.matrix_area = QFrame(objectName="pcMatrixArea")
        matrix_lay = QHBoxLayout(self.matrix_area)
        matrix_lay.setContentsMargins(0, 0, 0, 0)
        matrix_lay.setSpacing(0)

        self.frozen = DraggableComponentTable()
        self.frozen.setObjectName("pcFrozen")
        self.frozen.setFixedWidth(220)
        self.frozen.setColumnCount(1)
        self.frozen.setHorizontalHeaderLabels(["BİLEŞEN ↓"])
        self.frozen.horizontalHeader().setMinimumHeight(80)
        self.frozen.horizontalHeader().setMaximumHeight(80)
        self.frozen.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.frozen.verticalHeader().setVisible(False)
        self.frozen.setShowGrid(True)
        self.frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen.setSelectionMode(QAbstractItemView.NoSelection)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setItemDelegate(ComponentCellDelegate(self.frozen))
        self.frozen.setContextMenuPolicy(Qt.CustomContextMenu)
        self.frozen.customContextMenuRequested.connect(self._component_context_menu)
        self.frozen.cellDoubleClicked.connect(lambda r, _c: self._open_component_popover(self.components[r] if 0 <= r < len(self.components) else None))
        self.frozen.set_preview_provider(self._row_drag_preview)
        self.frozen.rowMoved.connect(self._move_component_row)
        self.frozen.rowDragMoved.connect(self._show_row_drop_indicator)
        self.frozen.rowDragEnded.connect(self._hide_drop_indicators)
        matrix_lay.addWidget(self.frozen)

        self.matrix = QTableWidget()
        self.matrix.setObjectName("pcMatrix")
        self.matrix.setShowGrid(True)
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
        self.matrix.horizontalHeader().set_preview_provider(self._column_drag_preview)
        self.matrix.horizontalHeader().setSectionsMovable(False)
        self.matrix.horizontalHeader().set_order_drag_enabled(True)
        self.matrix.horizontalHeader().sectionMoved.connect(self._platform_section_moved)
        self.matrix.horizontalHeader().columnDropped.connect(self._move_platform_column)
        self.matrix.horizontalHeader().columnDragMoved.connect(self._show_column_drop_indicator)
        self.matrix.horizontalHeader().columnDragEnded.connect(self._hide_drop_indicators)
        self.matrix.cellClicked.connect(self._toggle_assignment)
        matrix_lay.addWidget(self.matrix, 1)

        self.row_drop_indicator = QFrame(self.matrix_area)
        self.row_drop_indicator.setObjectName("pcRowDropIndicator")
        self.row_drop_indicator.setStyleSheet("background:#2563EB;border-radius:1px;")
        self.row_drop_indicator.hide()
        self.column_drop_indicator = QFrame(self.matrix_area)
        self.column_drop_indicator.setObjectName("pcColumnDropIndicator")
        self.column_drop_indicator.setStyleSheet("background:#2563EB;border-radius:1px;")
        self.column_drop_indicator.hide()

        root.addWidget(self.matrix_area, 1)

        def _frozen_scrolled(val):
            if self._syncing_scroll: return
            self._syncing_scroll = True
            self.matrix.verticalScrollBar().setValue(val)
            self._syncing_scroll = False

        def _matrix_scrolled(val):
            if self._syncing_scroll: return
            self._syncing_scroll = True
            self.frozen.verticalScrollBar().setValue(val)
            self._syncing_scroll = False

        self.frozen.verticalScrollBar().valueChanged.connect(_frozen_scrolled)
        self.matrix.verticalScrollBar().valueChanged.connect(_matrix_scrolled)

        self.footer = QFrame(objectName="pcFooter")
        self.footer.setFixedHeight(52)
        ft = QHBoxLayout(self.footer)
        ft.setContentsMargins(14, 0, 14, 0)
        self.footer_msg = QLabel("", objectName="pcFooterMsg")
        cancel = QPushButton("Vazgeç", objectName="pcFooterButton")
        cancel.setFixedSize(110, 36)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        save.setFixedSize(110, 36)
        save.clicked.connect(self._save_and_close)
        self.footer_msg.hide()
        ft.addWidget(self.footer_msg, 1)
        ft.addStretch(1)
        ft.addWidget(cancel)
        ft.addSpacing(8)
        ft.addWidget(save)
        root.addWidget(self.footer)

        # Overlay sadece karartma katmanı — içinde widget yok
        self.overlay = QWidget(self)
        self.overlay.setObjectName("pcOverlay")
        self.overlay.hide()
        # Popover: her açılışta _clear_popover ile yeniden oluşturulur
        self.popover = None
        outer.addWidget(self.overlay)
        outer.setCurrentWidget(page)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
QDialog {{ background:#DCE4EF; }}
QFrame#pcTopbar {{ background:{NAVY}; border-top-left-radius:10px; border-top-right-radius:10px; }}
QLabel#pcBrand {{ color:white; background:transparent; padding:3px 9px; font-weight:900; font-size:13px; letter-spacing:.06em; }}
QLabel#pcFile {{ color:rgba(255,255,255,.45); background:rgba(255,255,255,.08); border-radius:20px; padding:3px 11px; font-size:11px; }}
QPushButton#pcTopButton {{ background:rgba(255,255,255,.13); color:white; border:1.5px solid rgba(255,255,255,.2); border-radius:7px; padding:5px 13px; font-weight:700; font-size:12px; }}
QPushButton#pcTopButton:hover {{ background:rgba(255,255,255,.22); }}
QFrame#pcToolbar {{ background:#F0F4F9; border-bottom:1px solid {GRID}; }}
QLabel#pcHint, QLabel#pcFooterMsg {{ color:{MUTED}; font-size:10px; background:transparent; }}
QLabel#pcBadge {{ color:#91A0B8; background:#F0F4FA; border:1px solid #E2E8F0; border-radius:6px; padding:4px 9px; font-size:10px; }}
QLineEdit#pcSearch {{ border:1.5px solid #DDE3EE; border-radius:6px; padding:3px 10px; background:#FFFFFF; color:#334155; font-size:12px; }}
QLineEdit#pcSearch:focus {{ border-color:#3B6FE8; }}
QFrame#pcMatrixArea {{ background:white; }}
QTableWidget#pcFrozen, QTableWidget#pcMatrix {{ background:white; border:none; gridline-color:{GRID}; alternate-background-color:{ROW_ALT}; }}
QTableWidget#pcFrozen QHeaderView::section {{ background:{NAVY}; color:#84A0C2; border-right:1px solid #B7C6DC; border-bottom:1px solid #B7C6DC; font-weight:900; font-size:9px; padding-left:8px; }}
QScrollBar:vertical {{ background:#F1F5F9; width:10px; }}
QScrollBar::handle:vertical {{ background:#CBD5E1; border-radius:5px; min-height:24px; }}
QScrollBar:horizontal {{ background:#F1F5F9; height:10px; }}
QScrollBar::handle:horizontal {{ background:#CBD5E1; border-radius:5px; min-width:24px; }}
QFrame#pcFooter {{ background:#FFFFFF; border-top:1px solid {GRID}; border-bottom-left-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#pcFooterButton {{ background:white; color:#334155; border:1.5px solid #DDE3EE; border-radius:7px; font-size:12px; font-weight:500; }}
QPushButton#pcPrimaryButton {{ background:#3769E8; color:white; border:none; border-radius:7px; font-size:12px; font-weight:700; }}
QWidget#pcOverlay {{ background:rgba(15,31,61,90); }}
QFrame#pcPopover {{ background:white; border:1.5px solid #DDE3EE; border-radius:14px; }}
QFrame#popHead {{ background:white; border-radius:14px 14px 0 0; }}
QFrame#popFoot {{ background:#F8FAFC; border-radius:0 0 14px 14px; }}
QFrame#popSep  {{ color:#E8EFF8; max-height:1px; border:none; border-top:1px solid #E8EFF8; }}
QWidget#popBody {{ background:white; }}
QLabel#popIconComp {{ background:#F0FDFA; color:#0D9488; border-radius:10px; font-size:18px; font-weight:900; }}
QLabel#popIconPlat {{ background:#EFF6FF; color:#1D4ED8; border-radius:10px; font-size:18px; font-weight:900; }}
QPushButton#popXBtn {{ background:#F1F5F9; color:#64748B; border:none; border-radius:7px; font-size:13px; font-weight:700; }}
QPushButton#popXBtn:hover {{ background:#E2E8F0; }}
QPushButton#logoPickBtn {{ background:#F5F8FF; color:#3B6FE8; border:1.5px dashed #BFDBFE; border-radius:8px; padding:10px 14px; font-size:12px; font-weight:700; text-align:left; }}
QLabel#popTitle {{ color:#12223D; font-size:14px; font-weight:900; }}
QLabel#popSub {{ color:#94A3B8; font-size:10px; }}
QLabel#popField {{ color:#53657E; font-size:10px; font-weight:900; }}
QFrame#pcPopover QLineEdit {{
    border:1.5px solid #DDE3EE; border-radius:7px;
    padding:7px 10px; background:#FFFFFF; color:#0D1117;
    font-size:13px; selection-background-color:#BFDBFE;
}}
QFrame#pcPopover QLineEdit:focus {{
    border-color:#3B6FE8; background:#FFFFFF;
}}
QFrame#pcPopover QComboBox {{
    border:1.5px solid #DDE3EE; border-radius:7px;
    padding:6px 10px; background:#FFFFFF; color:#0D1117;
    font-size:13px;
}}
QFrame#pcPopover QComboBox:focus {{
    border-color:#3B6FE8;
}}
QFrame#pcPopover QComboBox::drop-down {{
    border:none; background:transparent; width:20px;
}}
QFrame#pcPopover QComboBox QAbstractItemView {{
    background:#FFFFFF; border:1.5px solid #DDE3EE;
    selection-background-color:#EBF1FD; color:#0D1117;
    outline:none;
}}
QFrame#pcPopover QCheckBox {{
    font-size:12px; color:#334155; spacing:7px;
}}
QFrame#pcPopover QCheckBox::indicator {{
    width:18px; height:18px; border-radius:5px;
    border:1.5px solid #CBD7E7; background:#FFFFFF;
}}
QFrame#pcPopover QCheckBox::indicator:checked {{
    background:#3B6FE8; border-color:#3B6FE8;
}}
QPushButton#dangerButton {{ background:#FFF5F5; color:#DC2626; border:1px solid #FCA5A5; border-radius:7px; padding:7px 14px; font-weight:800; }}
""")

    def _auto_size(self):
        """Dialog genişliğine göre sütun genişliğini dinamik ayarla."""
        frozen_w  = 220
        n_plat    = max(1, len(self.platforms))
        avail_w   = self.width() - frozen_w - 20  # scrollbar payı
        # Mevcut genişliğe göre sütun hesapla — min 90, max 140
        col_w = max(90, min(140, avail_w // n_plat))
        mh = self.matrix.horizontalHeader()
        for ci in range(n_plat):
            mh.setSectionResizeMode(ci, QHeaderView.Fixed)
            self.matrix.setColumnWidth(ci, col_w)
        # İlk açılışta boyutu ayarla (sadece bir kez)
        if not getattr(self, "_sized_once", False):
            self._sized_once = True
            default_col = 104
            content_w = frozen_w + n_plat * default_col + 20
            target_w = max(640, min(content_w, 1200))
            target_h = max(460, min(200 + len(self.components) * 52 + 52 + 38 + 46, 760))
            self.resize(target_w, target_h)

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key_Escape:
            if self.popover and self.popover.isVisible():
                self._hide_popover()
                return
            # Popover kapalı — değişiklik varsa uyar
            if self.changed and self.change_count > 0:
                from PySide6.QtWidgets import QMessageBox as _MB
                mb = _MB(self)
                mb.setWindowTitle("Çıkmak istiyor musunuz?")
                mb.setText(f"{self.change_count} kaydedilmemiş değişiklik var. Çıkmak istiyor musunuz?")
                mb.setIcon(_MB.Question)
                mb.setStandardButtons(_MB.Yes | _MB.No)
                mb.setDefaultButton(_MB.No)
                mb.setStyleSheet("QLabel { background: transparent; color: #334155; selection-background-color: transparent; }")
                if mb.exec() == _MB.Yes:
                    self.reject()
            else:
                self.reject()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.rect())
        if hasattr(self, "platforms") and self.platforms:
            self._auto_size()
        if getattr(self, "popover", None) and self.popover and self.popover.isVisible():
            pw, ph = self.popover.width(), self.popover.height()
            self.popover.move((self.width()-pw)//2, (self.height()-ph)//2)

    def _filter_components(self, text: str):
        """Arama kutusuna göre bileşen satırlarını göster/gizle."""
        q = text.strip().lower()
        self._update_drag_enabled()
        for row in range(self.frozen.rowCount()):
            widget = self.frozen.cellWidget(row, 0)
            if widget:
                # İsim labelini bul
                name_lbl = widget.findChild(QLabel)
                if name_lbl:
                    visible = q == "" or q in name_lbl.text().lower()
                else:
                    visible = True
            else:
                item = self.frozen.item(row, 0)
                visible = q == "" or (item and q in item.text().lower())
            self.frozen.setRowHidden(row, not visible)
            self.matrix.setRowHidden(row, not visible)

    def _load_data(self):
        self.platforms = self._read_platforms()
        self.components = self._read_components()
        self._refresh_matrix()
        if not hasattr(self, "_snapshot") or not self._snapshot:
            self._take_snapshot()

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
                "display_order": i,
                "platforms": dict(getattr(comp, "platforms", {}) or {}),
            })
        return out

    def _refresh_matrix(self):
        self.frozen.blockSignals(True)
        self.matrix.blockSignals(True)
        header = self.matrix.horizontalHeader()
        header.blockSignals(True)
        rows = len(self.components)
        cols = len(self.platforms)
        self.frozen.setRowCount(rows)
        self.matrix.setRowCount(rows)
        self.matrix.setColumnCount(cols)
        header.set_platforms(self.platforms)
        self.matrix.setHorizontalHeaderLabels([str(p.get("name") or "") for p in self.platforms])
        header.setSectionsMovable(False)
        header.set_order_drag_enabled(self._ordering_enabled())
        for logical in range(cols):
            visual = header.visualIndex(logical)
            if visual >= 0 and visual != logical:
                header.moveSection(visual, logical)
        for c in range(cols):
            self.matrix.setColumnWidth(c, 104)
        for r, comp in enumerate(self.components):
            self.frozen.setRowHeight(r, 52)
            self.matrix.setRowHeight(r, 52)
            item = QTableWidgetItem(str(comp.get("name") or ""))
            item.setData(Qt.UserRole, comp)
            self.frozen.setItem(r, 0, item)
            platforms = comp.get("platforms") or {}
            for c, platform in enumerate(self.platforms):
                assigned = bool(platforms.get(str(platform.get("name") or ""), False))
                cell = QTableWidgetItem("✓" if assigned else "")
                cell.setData(Qt.UserRole, assigned)
                self.matrix.setItem(r, c, cell)
        header.blockSignals(False)
        self.frozen.blockSignals(False)
        self.matrix.blockSignals(False)
        self._update_change_text()
        self._auto_size()
        self._update_drag_enabled()

    def _ordering_enabled(self) -> bool:
        return not bool(self.search_box.text().strip()) if hasattr(self, "search_box") else True

    def _update_drag_enabled(self):
        enabled = self._ordering_enabled()
        if hasattr(self, "frozen") and hasattr(self.frozen, "set_order_drag_enabled"):
            self.frozen.set_order_drag_enabled(enabled)
        if hasattr(self, "matrix"):
            self.matrix.horizontalHeader().setSectionsMovable(False)
            if hasattr(self.matrix.horizontalHeader(), "set_order_drag_enabled"):
                self.matrix.horizontalHeader().set_order_drag_enabled(enabled)
        if not enabled:
            self._hide_drop_indicators()
        msg = "" if enabled else "Sıralama yapmak için aramayı temizleyin."
        if hasattr(self, "footer_msg"):
            self.footer_msg.setText(msg)
            self.footer_msg.setVisible(bool(msg))
        tip = msg or "Bileşen satırlarını sol alandan, platformları başlıktan sürükleyerek sıralayın."
        if hasattr(self, "frozen"):
            self.frozen.setToolTip(tip)
        if hasattr(self, "matrix"):
            self.matrix.horizontalHeader().setToolTip(tip)

    def _soft_drag_pixmap(self, content: QPixmap) -> QPixmap:
        if content is None or content.isNull():
            return QPixmap()
        pad = 8
        out = QPixmap(content.width() + pad * 2, content.height() + pad * 2)
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 31, 61, 38))
        painter.drawRoundedRect(5, 6, content.width() + 6, content.height() + 6, 10, 10)
        painter.setOpacity(0.88)
        painter.drawPixmap(pad, pad, content)
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(59, 111, 232, 190), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(pad, pad, max(1, content.width() - 1), max(1, content.height() - 1), 8, 8)
        painter.end()
        return out

    def _row_drag_preview(self, row: int) -> QPixmap:
        if row < 0 or row >= self.frozen.rowCount():
            return QPixmap()
        frozen_rect = QRect(0, self.frozen.rowViewportPosition(row), self.frozen.viewport().width(), self.frozen.rowHeight(row))
        matrix_rect = QRect(0, self.matrix.rowViewportPosition(row), self.matrix.viewport().width(), self.matrix.rowHeight(row))
        frozen_pix = self.frozen.viewport().grab(frozen_rect)
        matrix_pix = self.matrix.viewport().grab(matrix_rect)
        content = QPixmap(frozen_pix.width() + matrix_pix.width(), max(frozen_pix.height(), matrix_pix.height()))
        content.fill(QColor("#FFFFFF"))
        painter = QPainter(content)
        painter.drawPixmap(0, 0, frozen_pix)
        painter.drawPixmap(frozen_pix.width(), 0, matrix_pix)
        painter.end()
        return self._soft_drag_pixmap(content)

    def _column_drag_preview(self, col: int) -> QPixmap:
        if col < 0 or col >= self.matrix.columnCount():
            return QPixmap()
        width = self.matrix.columnWidth(col)
        header_x = self.matrix.horizontalHeader().sectionViewportPosition(col)
        body_x = self.matrix.columnViewportPosition(col)
        header_rect = QRect(header_x, 0, width, self.matrix.horizontalHeader().height())
        body_rect = QRect(body_x, 0, width, self.matrix.viewport().height())
        header_pix = self.matrix.horizontalHeader().viewport().grab(header_rect)
        body_pix = self.matrix.viewport().grab(body_rect)
        content = QPixmap(width, header_pix.height() + body_pix.height())
        content.fill(QColor("#FFFFFF"))
        painter = QPainter(content)
        painter.drawPixmap(0, 0, header_pix)
        painter.drawPixmap(0, header_pix.height(), body_pix)
        painter.end()
        return self._soft_drag_pixmap(content)

    def _show_row_drop_indicator(self, target_row: int):
        if not hasattr(self, "row_drop_indicator") or self.frozen.rowCount() <= 0:
            return
        target_row = max(0, min(int(target_row), self.frozen.rowCount()))
        if target_row >= self.frozen.rowCount():
            y = self.frozen.rowViewportPosition(self.frozen.rowCount() - 1) + self.frozen.rowHeight(self.frozen.rowCount() - 1)
        else:
            y = self.frozen.rowViewportPosition(target_row)
        pos = self.frozen.viewport().mapTo(self.matrix_area, QPoint(0, y))
        self.row_drop_indicator.setGeometry(0, max(0, pos.y() - 1), self.matrix_area.width(), 3)
        self.row_drop_indicator.raise_()
        self.row_drop_indicator.show()
        self.column_drop_indicator.hide()

    def _show_column_drop_indicator(self, target_col: int):
        if not hasattr(self, "column_drop_indicator") or self.matrix.columnCount() <= 0:
            return
        target_col = max(0, min(int(target_col), self.matrix.columnCount()))
        if target_col >= self.matrix.columnCount():
            last = self.matrix.columnCount() - 1
            x = self.matrix.columnViewportPosition(last) + self.matrix.columnWidth(last)
        else:
            x = self.matrix.columnViewportPosition(target_col)
        top = self.matrix.horizontalHeader().mapTo(self.matrix_area, QPoint(x, 0))
        body_bottom = self.matrix.viewport().mapTo(self.matrix_area, QPoint(x, self.matrix.viewport().height()))
        self.column_drop_indicator.setGeometry(max(0, top.x() - 1), max(0, top.y()), 3, max(20, body_bottom.y() - top.y()))
        self.column_drop_indicator.raise_()
        self.column_drop_indicator.show()
        self.row_drop_indicator.hide()

    def _hide_drop_indicators(self):
        if hasattr(self, "row_drop_indicator"):
            self.row_drop_indicator.hide()
        if hasattr(self, "column_drop_indicator"):
            self.column_drop_indicator.hide()

    def _renumber_component_orders(self):
        for idx, comp in enumerate(self.components):
            comp["display_order"] = idx

    def _renumber_platform_orders(self):
        for idx, platform in enumerate(self.platforms):
            platform["sort_order"] = idx

    def _component_order(self) -> list[int]:
        return [int(c.get("id") or 0) for c in self.components if int(c.get("id") or 0) > 0]

    def _platform_order(self) -> list[int]:
        return [int(p.get("id") or 0) for p in self.platforms if int(p.get("id") or 0) > 0]

    def _move_component_row(self, source_row: int, target_row: int):
        if not self._ordering_enabled():
            return
        if source_row < 0 or source_row >= len(self.components):
            return
        target_row = max(0, min(int(target_row), len(self.components)))
        if target_row > source_row:
            target_row -= 1
        if target_row == source_row:
            return
        item = self.components.pop(source_row)
        self.components.insert(target_row, item)
        self._renumber_component_orders()
        self._component_order_changed = self._component_order() != getattr(self, "_snapshot_component_order", [])
        self.changed = True
        self._refresh_matrix()

    def _move_platform_column(self, source_col: int, target_col: int):
        if not self._ordering_enabled():
            return
        if source_col < 0 or source_col >= len(self.platforms):
            return
        target_col = max(0, min(int(target_col), len(self.platforms)))
        if target_col > source_col:
            target_col -= 1
        if target_col == source_col:
            return
        item = self.platforms.pop(source_col)
        self.platforms.insert(target_col, item)
        self._renumber_platform_orders()
        self._platform_order_changed = self._platform_order() != getattr(self, "_snapshot_platform_order", [])
        self.changed = True
        self._refresh_matrix()

    def _platform_section_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        if self._syncing_platform_header or not self._ordering_enabled():
            return
        header = self.matrix.horizontalHeader()
        visual_order = []
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if 0 <= logical < len(self.platforms):
                visual_order.append(self.platforms[logical])
        if len(visual_order) != len(self.platforms):
            return
        self._syncing_platform_header = True
        try:
            self.platforms = list(visual_order)
            self._renumber_platform_orders()
            self._platform_order_changed = self._platform_order() != getattr(self, "_snapshot_platform_order", [])
            self.changed = True
            self._refresh_matrix()
        finally:
            self._syncing_platform_header = False

    def _update_change_text(self):
        self._update_dirty_count()

    def _update_dirty_count(self):
        """Bellekteki bileşen durumunu snapshot ile karşılaştırıp badge güncelle."""
        snap = getattr(self, "_snapshot", {})
        diff = sum(
            1 for c in self.components
            if c.get("name") in snap
            and dict(c.get("platforms") or {}) != snap[c.get("name")]
        )
        if self._component_order() != getattr(self, "_snapshot_component_order", []):
            diff += 1
        if self._platform_order() != getattr(self, "_snapshot_platform_order", []):
            diff += 1
        self._component_order_changed = self._component_order() != getattr(self, "_snapshot_component_order", [])
        self._platform_order_changed = self._platform_order() != getattr(self, "_snapshot_platform_order", [])
        if diff > 0:
            self.changed = True
        self.change_count = diff
        if diff > 0:
            self.change_badge.setText(f"{diff} değişiklik")
            self.change_badge.setStyleSheet(
                "color:#B45309;background:#FFF7E6;border:1px solid #FDE68A;"
                "border-radius:6px;padding:4px 9px;font-size:11px;font-weight:700;"
            )
        else:
            self.change_badge.setText("Değişiklik yok")
            self.change_badge.setStyleSheet(
                "color:#91A0B8;background:#F0F4FA;border:1px solid #E2E8F0;"
                "border-radius:6px;padding:4px 9px;font-size:11px;"
            )

    def _take_snapshot(self):
        """Mevcut platform ataması durumunu kaydet."""
        self._snapshot = {
            c.get("name", ""): dict(c.get("platforms") or {})
            for c in (self.components or [])
        }
        self._snapshot_component_order = self._component_order()
        self._snapshot_platform_order = self._platform_order()
        self._component_order_changed = False
        self._platform_order_changed = False

    def _mark_saved(self, message: str = ""):
        self.changed = True
        self.settings_saved.emit()
        self._update_dirty_count()

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
        platform_name = str(self.platforms[col].get("name") or "")
        # Bellekteki komponenti güncelle
        comp = self.components[row]
        plats = dict(comp.get("platforms") or {})
        was = bool(plats.get(platform_name, False))
        plats[platform_name] = not was
        comp["platforms"] = plats
        # Sadece bu hücreyi güncelle
        item = self.matrix.item(row, col)
        if item:
            now = plats[platform_name]
            item.setText("✓" if now else "")
            from PySide6.QtGui import QColor, QBrush
            row_bg = "#FAFBFD" if row % 2 == 0 else "#FFFFFF"
            item.setBackground(QBrush(QColor("#DCFCE7" if now else row_bg)))
            item.setForeground(QBrush(QColor("#15803D" if now else "#E5E7EB")))
            item.setData(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.UserRole, now)
            f = item.font(); f.setBold(now); f.setPointSize(14 if now else 12); item.setFont(f)
        # DB'ye yaz
        self._write_component(comp)
        # Platform başlığındaki bileşen sayacını anlık güncelle
        plat_data = self.platforms[col] if col < len(self.platforms) else {}
        new_count = sum(
            1 for c in self.components
            if bool((c.get("platforms") or {}).get(platform_name, False))
        )
        plat_data["comp_count"] = new_count
        self.matrix.horizontalHeader().viewport().update()
        # Değişiklik sayacı
        self.changed = True
        self.settings_saved.emit()
        self._update_dirty_count()

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
        self.popover.setMinimumWidth(380)
        self.popover.setMaximumWidth(420)
        lay = QVBoxLayout(self.popover)
        lay.setContentsMargins(14, 12, 14, 12)
        # ── Başlık (HTML referansı: pop-head) ──
        head_frame = QFrame()
        head_frame.setObjectName("popHead")
        head_lay = QHBoxLayout(head_frame)
        head_lay.setContentsMargins(16, 12, 16, 12)
        head_lay.setSpacing(12)

        icon_lbl = QLabel("＋")
        icon_lbl.setObjectName("popIconComp")
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "background:#F0FDFA;color:#0D9488;border-radius:10px;"
            "font-size:18px;font-weight:900;border:1.5px solid #CCFBF1;"
        )

        meta_lay = QVBoxLayout()
        meta_lay.setSpacing(1)
        meta_lay.addWidget(QLabel("Yeni Bileşen" if is_new else str(comp.get("name") or "Bileşen"), objectName="popTitle"))
        meta_lay.addWidget(QLabel("Bileşen bilgilerini girin", objectName="popSub"))

        x_btn = QPushButton("✕")
        x_btn.setObjectName("popXBtn")
        x_btn.setFixedSize(26, 26)
        x_btn.clicked.connect(self._hide_popover)

        head_lay.addWidget(icon_lbl)
        head_lay.addLayout(meta_lay, 1)
        head_lay.addWidget(x_btn)

        # Alt çizgi
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("popSep")

        lay.addWidget(head_frame)
        lay.addWidget(sep)

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
        active = ToggleSwitch(bool((comp or {}).get("active", True)))
        grid.setContentsMargins(0, 8, 0, 4)
        grid.setSpacing(6)
        grid.addWidget(QLabel("BİLEŞEN ADI", objectName="popField"), 0, 0)
        grid.addWidget(QLabel("BİRİM", objectName="popField"), 0, 1)
        grid.addWidget(name, 1, 0)
        grid.addWidget(unit, 1, 1)
        grid.addWidget(QLabel("NOT", objectName="popField"), 2, 0, 1, 2)
        grid.addWidget(note, 3, 0, 1, 2)
        grid.addWidget(QLabel("DURUM", objectName="popField"), 4, 0, 1, 2)
        # Toggle + label yan yana
        durum_row = QHBoxLayout()
        durum_row.setContentsMargins(0, 2, 0, 2)
        durum_row.setSpacing(10)
        durum_row.addWidget(active)
        active_lbl = QLabel("Aktif" if active.isChecked() else "Pasif")
        active_lbl.setStyleSheet("font-size:13px;color:#334155;background:transparent;")
        active.toggled.connect(lambda v, l=active_lbl: l.setText("Aktif" if v else "Pasif"))
        durum_row.addWidget(active_lbl)
        durum_row.addStretch(1)
        grid.addLayout(durum_row, 5, 0, 1, 2)
        body_w = QWidget(); body_w.setObjectName("popBody")
        body_lay = QVBoxLayout(body_w)
        body_lay.setContentsMargins(16, 12, 16, 4)
        body_lay.setSpacing(0)
        body_lay.addLayout(grid)
        lay.addWidget(body_w, 1)

        # Footer çizgi + butonlar
        foot_sep = QFrame(); foot_sep.setFrameShape(QFrame.HLine); foot_sep.setObjectName("popSep")
        foot_frame = QFrame(); foot_frame.setObjectName("popFoot")
        foot_lay = QHBoxLayout(foot_frame)
        foot_lay.setContentsMargins(16, 10, 16, 14)
        foot_lay.setSpacing(8)
        foot_lay.addStretch()
        cancel = QPushButton("İptal", objectName="dangerButton")
        cancel.clicked.connect(self._hide_popover)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        foot_lay.addWidget(cancel)
        foot_lay.addWidget(save)
        lay.addWidget(foot_sep)
        lay.addWidget(foot_frame)

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
        self.popover.setMinimumWidth(380)
        self.popover.setMaximumWidth(420)
        lay = QVBoxLayout(self.popover)
        lay.setContentsMargins(14, 12, 14, 12)
        head_frame = QFrame()
        head_frame.setObjectName("popHead")
        head_lay = QHBoxLayout(head_frame)
        head_lay.setContentsMargins(16, 12, 16, 12)
        head_lay.setSpacing(12)

        icon_lbl = QLabel("＋")
        icon_lbl.setObjectName("popIconPlat")
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "background:#EFF6FF;color:#1D4ED8;border-radius:10px;"
            "font-size:18px;font-weight:900;border:1.5px solid #BFDBFE;"
        )

        meta_lay = QVBoxLayout()
        meta_lay.setSpacing(1)
        meta_lay.addWidget(QLabel("Yeni Platform" if is_new else str(platform.get("name") or "Platform"), objectName="popTitle"))
        meta_lay.addWidget(QLabel("Platform adı girin", objectName="popSub"))

        x_btn = QPushButton("✕")
        x_btn.setObjectName("popXBtn")
        x_btn.setFixedSize(26, 26)
        x_btn.clicked.connect(self._hide_popover)

        head_lay.addWidget(icon_lbl)
        head_lay.addLayout(meta_lay, 1)
        head_lay.addWidget(x_btn)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("popSep")

        lay.addWidget(head_frame)
        lay.addWidget(sep)

        name = QLineEdit(str((platform or {}).get("name") or ""))
        name.setPlaceholderText("ÖRN: AKINCI")
        name.textEdited.connect(lambda txt: name.setText(txt.upper()))
        active = ToggleSwitch(bool((platform or {}).get("is_active", True)))

        def _sw_row(sw, on_txt, off_txt):
            row = QHBoxLayout(); row.setContentsMargins(0,2,0,2); row.setSpacing(10)
            row.addWidget(sw)
            lbl = QLabel(on_txt if sw.isChecked() else off_txt)
            lbl.setStyleSheet("font-size:13px;color:#334155;background:transparent;")
            sw.toggled.connect(lambda v, l=lbl, a=on_txt, b=off_txt: l.setText(a if v else b))
            row.addWidget(lbl); row.addStretch(1)
            return row

        logo_btn = QPushButton("📷  Logo ekle (opsiyonel)", objectName="logoPickBtn")
        logo_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        logo_btn.clicked.connect(lambda: self._pick_logo(logo_btn))


        body_w = QWidget(); body_w.setObjectName("popBody")
        body_lay = QVBoxLayout(body_w)
        body_lay.setContentsMargins(16, 12, 16, 4)
        body_lay.setSpacing(8)
        body_lay.addWidget(QLabel("PLATFORM ADI (BÜYÜK HARF)", objectName="popField"))
        body_lay.addWidget(name)
        body_lay.addSpacing(4)
        body_lay.addLayout(_sw_row(active, "Aktif", "Pasif"))
        body_lay.addSpacing(4)
        body_lay.addWidget(logo_btn)
        lay.addWidget(body_w, 1)

        foot_sep = QFrame(); foot_sep.setFrameShape(QFrame.HLine); foot_sep.setObjectName("popSep")
        foot_frame = QFrame(); foot_frame.setObjectName("popFoot")
        foot_lay = QHBoxLayout(foot_frame)
        foot_lay.setContentsMargins(16, 10, 16, 14)
        foot_lay.setSpacing(8)
        foot_lay.addStretch()
        cancel = QPushButton("İptal", objectName="dangerButton")
        cancel.clicked.connect(self._hide_popover)
        save = QPushButton("Kaydet", objectName="pcPrimaryButton")
        foot_lay.addWidget(cancel)
        foot_lay.addWidget(save)
        lay.addWidget(foot_sep)
        lay.addWidget(foot_frame)

        def do_save():
            clean = name.text().strip().upper()
            if not clean:
                QMessageBox.warning(self, "Eksik", "Platform adı girin.")
                return
            old_name = str((platform or {}).get("name") or clean)
            if is_new:
                self.store.create_platform(clean)
                old_name = clean
            self.store.update_platform(old_name, clean, active.isChecked(), False, sort_order=(platform or {}).get("sort_order"))
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

    def _pop_local_style(self) -> str:
        return """
        QFrame#pcPopover, QWidget { background: #FFFFFF; }
        QLabel { background: transparent; color: #334155; }
        QLabel[objectName="popTitle"] { font-size:14px; font-weight:900; color:#0D1117; }
        QLabel[objectName="popSub"]   { font-size:10px; color:#94A3B8; }
        QLabel[objectName="popField"] { font-size:10px; font-weight:900; color:#53657E; letter-spacing:.04em; }
        QLineEdit {
            border:1.5px solid #DDE3EE; border-radius:7px;
            padding:7px 10px; background:#FFFFFF; color:#0D1117;
            font-size:13px;
        }
        QLineEdit:focus { border-color:#3B6FE8; background:#FFFFFF; }
        QComboBox {
            border:1.5px solid #DDE3EE; border-radius:7px;
            padding:6px 10px; background:#FFFFFF; color:#0D1117;
            font-size:13px;
        }
        QComboBox:focus { border-color:#3B6FE8; }
        QComboBox::drop-down { border:none; background:transparent; width:22px; }
        QComboBox QAbstractItemView {
            background:#FFFFFF; border:1.5px solid #DDE3EE;
            selection-background-color:#EBF1FD; color:#0D1117; outline:none;
        }
        QCheckBox { font-size:13px; color:#334155; spacing:8px; background:transparent; }
        QCheckBox::indicator {
            width:20px; height:20px; border-radius:6px;
            border:1.5px solid #CBD7E7; background:#FFFFFF;
        }
        QCheckBox::indicator:checked { background:#3B6FE8; border-color:#3B6FE8; }
        QPushButton[objectName="pcPrimaryButton"] {
            background: #3B6FE8 !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 8px 18px !important;
            font-size: 13px !important;
            font-weight: 700 !important;
        }
        QPushButton[objectName="pcPrimaryButton"]:hover {
            background: #2954CC !important;
        }
        QPushButton[objectName="dangerButton"] {
            background: #FEF2F2 !important;
            color: #DC2626 !important;
            border: 1.5px solid #FCA5A5 !important;
            border-radius: 8px !important;
            padding: 8px 18px !important;
            font-size: 13px !important;
            font-weight: 700 !important;
        }
        QPushButton[objectName="dangerButton"]:hover {
            background: #FEE2E2 !important;
        }
        QFrame[objectName="popFoot"] {
            background: #FFFFFF;
            border-radius: 0 0 14px 14px;
        }
        """

    def _clear_popover(self):
        """Önceki popover'ı tamamen sil, temiz yenisini oluştur."""
        if self.popover is not None:
            self.popover.hide()
            self.popover.setParent(None)
            self.popover.deleteLater()
            self.popover = None
        from PySide6.QtWidgets import QFrame as _F
        self.popover = _F(self)
        self.popover.setObjectName("pcPopover")
        self.popover.setStyleSheet(self._pop_local_style())
        self.popover.hide()

    def _show_popover(self):
        self.overlay.setGeometry(self.rect())
        self.overlay.show()
        self.overlay.raise_()
        if self.popover:
            # 1. Önce göster — layout hesaplanabilsin
            self.popover.show()
            self.popover.raise_()
            # 2. sizeHint ile gerçek boyutu al (adjustSize'dan güvenilir)
            sh = self.popover.sizeHint()
            pw = max(380, sh.width())
            ph = max(200, sh.height())
            # 3. Ortala
            x = max(20, (self.width()  - pw) // 2)
            y = max(20, (self.height() - ph) // 2)
            self.popover.setGeometry(x, y, pw, ph)

    def _hide_popover(self):
        if self.popover:
            self.popover.hide()
        self.overlay.hide()

    def closeEvent(self, event):
        if self.popover and self.popover.isVisible():
            self._hide_popover()
            event.ignore()
            return
        if self.changed and self.change_count > 0:
            from PySide6.QtWidgets import QMessageBox as _MB
            mb = _MB(self)
            mb.setWindowTitle("Çıkmak istiyor musunuz?")
            mb.setText(f"{self.change_count} kaydedilmemiş değişiklik var. Çıkmak istiyor musunuz?")
            mb.setIcon(_MB.Question)
            mb.setStandardButtons(_MB.Yes | _MB.No)
            mb.setDefaultButton(_MB.No)
            mb.setStyleSheet("QLabel { background: transparent; color: #334155; selection-background-color: transparent; }")
            if mb.exec() == _MB.No:
                event.ignore()
                return
        event.accept()

    def _save_and_close(self):
        if self._component_order_changed and hasattr(self.store, "update_component_order"):
            self.store.update_component_order(self._component_order())
        if self._platform_order_changed and hasattr(self.store, "update_platform_order"):
            self.store.update_platform_order(self._platform_order())
        if hasattr(self.store, "save"):
            self.store.save()
        if self.changed:
            self.settings_saved.emit()
        self._take_snapshot()
        self.accept()
