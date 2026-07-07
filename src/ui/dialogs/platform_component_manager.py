from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QMimeData, QRect, Qt, Signal, QSize
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
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.message_boxes import ask_yes_no, show_warning
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
    platformMoved = Signal(int, int)

    _MIME_TYPE = "application/x-sts-platform-column"

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.platforms: list[dict[str, Any]] = []
        self._drag_enabled = True
        self._drag_start_pos = None
        self._drag_start_logical = -1
        self._dragging_logical = -1
        self._drop_index = -1
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setSectionsClickable(True)
        self.setFixedHeight(80)

    def setSectionsMovable(self, movable: bool):
        self._drag_enabled = bool(movable)
        # Native header moving only drags the title.  Keep the functional reorder
        # custom so the pixmap can represent the full platform column.
        super().setSectionsMovable(False)

    def set_platforms(self, platforms: list[dict[str, Any]]):
        self.platforms = list(platforms or [])
        self.viewport().update()

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        s.setHeight(80)
        return s

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_index >= 0:
            painter = QPainter(self.viewport())
            self._paint_column_indicator(painter)
            painter.end()

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        if not rect.isValid():
            return
        platform = self.platforms[logicalIndex] if 0 <= logicalIndex < len(self.platforms) else {}
        name = str(platform.get("name") or "")
        count = int(platform.get("comp_count") or 0)
        excluded = bool(platform.get("is_excluded", False))

        av_bg, av_fg = self._platform_avatar_colors(platform)

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

        if logicalIndex == self._dragging_logical:
            painter.setPen(QPen(QColor("#60A5FA"), 2))
            painter.setBrush(QColor(255, 255, 255, 46))
            painter.drawRoundedRect(rect.adjusted(3, 4, -3, -4), 10, 10)

        painter.restore()


    @staticmethod
    def _platform_color_key(platform: dict[str, Any]) -> str:
        key = platform.get("id")
        if key is None or key == "":
            key = platform.get("name") or ""
        return str(key)

    @classmethod
    def _platform_avatar_colors(cls, platform: dict[str, Any]) -> tuple[str, str]:
        # HTML'deki _PLAT_COLORS ile birebir aynı palet korunur.
        # Renk seçimi sütun sırasına göre değil platform id/name anahtarına
        # göre yapılır; böylece drag/drop ve yeniden çizimde renk sabit kalır.
        bg_colors = ["#EFF6FF", "#F0FDF4", "#FFF7ED", "#FDF4FF", "#F0FDFA", "#FEF3C7", "#FEE2E2", "#E0F2FE"]
        fg_colors = ["#1D4ED8", "#15803D", "#C2410C", "#7E22CE", "#0D9488", "#92400E", "#991B1B", "#075985"]
        stable_key = cls._platform_color_key(platform)
        digest = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()
        color_index = int(digest[:8], 16) % len(bg_colors)
        return bg_colors[color_index], fg_colors[color_index]

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
            self._start_column_drag(self._drag_start_logical, self._drag_start_pos)
            self._drag_start_pos = None
            self._drag_start_logical = -1
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            self._set_drop_index(self._drop_index_at(event.position().toPoint().x()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_drop_index(-1)
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
        target = self._drop_index_at(event.position().toPoint().x())
        self._set_drop_index(-1)
        self.platformMoved.emit(source, target)
        event.acceptProposedAction()

    def _start_column_drag(self, logical_index: int, start_pos: QPoint):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self._MIME_TYPE, str(logical_index).encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = self._column_drag_pixmap(logical_index)
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            section_x = self.sectionViewportPosition(logical_index)
            drag.setHotSpot(QPoint(max(0, start_pos.x() - section_x) + 10, min(start_pos.y() + 10, pixmap.height() - 1)))
        self._dragging_logical = logical_index
        table = self.parent()
        if hasattr(table, "set_dragging_column"):
            table.set_dragging_column(logical_index)
        self.viewport().update()
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._dragging_logical = -1
            self._set_drop_index(-1)
            if hasattr(table, "set_dragging_column"):
                table.set_dragging_column(-1)
            self.viewport().update()

    def _column_drag_pixmap(self, logical_index: int) -> QPixmap:
        table = self.parent()
        if not table or logical_index < 0:
            return QPixmap()
        x = self.sectionViewportPosition(logical_index)
        w = self.sectionSize(logical_index)
        if w <= 0:
            return QPixmap()
        header_h = self.viewport().height()
        body_h = table.viewport().height() if hasattr(table, "viewport") else 0
        margin = 10
        base = QPixmap(w, header_h + body_h)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        self.viewport().render(painter, QPoint(0, 0), QRect(x, 0, w, header_h))
        if body_h > 0:
            table.viewport().render(painter, QPoint(0, header_h), QRect(x, 0, w, body_h))
        painter.end()
        preview = QPixmap(base.width() + margin * 2, base.height() + margin * 2)
        preview.fill(Qt.transparent)
        painter = QPainter(preview)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 31, 61, 38))
        painter.drawRoundedRect(QRect(margin + 4, margin + 5, base.width(), base.height()), 12, 12)
        painter.setOpacity(0.88)
        painter.drawPixmap(margin, margin, base)
        painter.setOpacity(1)
        painter.setPen(QPen(QColor("#3B82F6"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRect(margin, margin, base.width(), base.height()).adjusted(1, 1, -1, -1), 10, 10)
        painter.end()
        return preview

    def _drop_index_at(self, x: int) -> int:
        if self.count() <= 0:
            return 0
        for visual in range(self.count()):
            logical = self.logicalIndex(visual)
            left = self.sectionViewportPosition(logical)
            width = self.sectionSize(logical)
            if x < left + width // 2:
                return visual
        return self.count()

    def _set_drop_index(self, index: int):
        if self._drop_index == index:
            return
        self._drop_index = index
        table = self.parent()
        if hasattr(table, "set_column_drop_index"):
            table.set_column_drop_index(index)
        self.viewport().update()

    def _indicator_x(self) -> int:
        if self._drop_index <= 0:
            return self.sectionViewportPosition(self.logicalIndex(0)) if self.count() else 0
        if self._drop_index >= self.count():
            logical = self.logicalIndex(self.count() - 1)
            return self.sectionViewportPosition(logical) + self.sectionSize(logical)
        return self.sectionViewportPosition(self.logicalIndex(self._drop_index))

    def _paint_column_indicator(self, painter: QPainter):
        x = self._indicator_x()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#2563EB"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(x, 8, x, self.viewport().height() - 8)


class MatrixAssignmentTable(QTableWidget):
    rowMoved = Signal(int, int)

    _ROW_MIME_TYPE = "application/x-sts-component-row"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_drag_enabled = True
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self._column_drop_index = -1
        self._dragging_column = -1
        self._row_drop_index = -1
        self._dragging_row = -1

    def set_order_drag_enabled(self, enabled: bool):
        self._row_drag_enabled = bool(enabled)
        self.setAcceptDrops(self._row_drag_enabled)
        self.viewport().setAcceptDrops(self._row_drag_enabled)

    def set_column_drop_index(self, index: int):
        self._column_drop_index = index
        self.viewport().update()

    def set_dragging_column(self, logical_index: int):
        self._dragging_column = logical_index
        self.viewport().update()

    def set_row_drop_index(self, index: int):
        self._row_drop_index = index
        self.viewport().update()

    def set_dragging_row(self, row: int):
        self._dragging_row = row
        self.viewport().update()

    def dragEnterEvent(self, event):
        if self._row_drag_enabled and event.mimeData().hasFormat(self._ROW_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._row_drag_enabled and event.mimeData().hasFormat(self._ROW_MIME_TYPE):
            self.set_row_drop_index(self._target_row_at(event.position().toPoint().y()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.set_row_drop_index(-1)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not (self._row_drag_enabled and event.mimeData().hasFormat(self._ROW_MIME_TYPE)):
            super().dropEvent(event)
            return
        try:
            source_row = int(bytes(event.mimeData().data(self._ROW_MIME_TYPE)).decode("utf-8"))
        except Exception:
            event.ignore()
            return
        target_row = self._target_row_at(event.position().toPoint().y())
        self.set_row_drop_index(-1)
        self.rowMoved.emit(source_row, target_row)
        event.acceptProposedAction()

    def _target_row_at(self, y: int) -> int:
        target_row = self.rowAt(y)
        if target_row < 0:
            target_row = self.rowCount()
        return target_row

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        if self._dragging_column >= 0 and self._dragging_column < self.columnCount():
            x = self.columnViewportPosition(self._dragging_column)
            w = self.columnWidth(self._dragging_column)
            painter.fillRect(QRect(x, 0, w, self.viewport().height()), QColor(59, 130, 246, 24))
        if self._dragging_row >= 0 and self._dragging_row < self.rowCount():
            y = self.rowViewportPosition(self._dragging_row)
            h = self.rowHeight(self._dragging_row)
            painter.fillRect(QRect(0, y, self.viewport().width(), h), QColor(59, 130, 246, 24))
        if self._column_drop_index >= 0:
            self._paint_column_indicator(painter)
        if self._row_drop_index >= 0:
            self._paint_row_indicator(painter)
        painter.end()

    def _paint_column_indicator(self, painter: QPainter):
        if self.columnCount() <= 0:
            x = 0
        elif self._column_drop_index <= 0:
            x = self.columnViewportPosition(0)
        elif self._column_drop_index >= self.columnCount():
            last = self.columnCount() - 1
            x = self.columnViewportPosition(last) + self.columnWidth(last)
        else:
            x = self.columnViewportPosition(self._column_drop_index)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#2563EB"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(x, 0, x, self.viewport().height())

    def _paint_row_indicator(self, painter: QPainter):
        if self.rowCount() <= 0:
            y = 0
        elif self._row_drop_index <= 0:
            y = self.rowViewportPosition(0)
        elif self._row_drop_index >= self.rowCount():
            last = self.rowCount() - 1
            y = self.rowViewportPosition(last) + self.rowHeight(last)
        else:
            y = self.rowViewportPosition(self._row_drop_index)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#2563EB"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(0, y, self.viewport().width(), y)


class DraggableComponentTable(QTableWidget):
    rowMoved = Signal(int, int)

    _MIME_TYPE = "application/x-sts-component-row"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_enabled = True
        self._drag_start_pos = None
        self._drag_start_row = -1
        self._drop_row = -1
        self._dragging_row = -1
        self._drag_peer = None
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)

    def set_order_drag_enabled(self, enabled: bool):
        self._drag_enabled = bool(enabled)
        self.setDragEnabled(self._drag_enabled)
        self.setAcceptDrops(self._drag_enabled)
        self.viewport().setAcceptDrops(self._drag_enabled)

    def set_drag_peer(self, peer):
        self._drag_peer = peer

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        if 0 <= self._dragging_row < self.rowCount():
            y = self.rowViewportPosition(self._dragging_row)
            h = self.rowHeight(self._dragging_row)
            painter.fillRect(QRect(0, y, self.viewport().width(), h), QColor(59, 130, 246, 24))
        if self._drop_row >= 0:
            self._paint_row_indicator(painter)
        painter.end()

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
            self._start_row_drag(self._drag_start_row, self._drag_start_pos)
            self._drag_start_pos = None
            self._drag_start_row = -1
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_enabled and event.mimeData().hasFormat(self._MIME_TYPE):
            self._set_drop_row(self._target_row_at(event.position().toPoint().y()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_drop_row(-1)
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
        target_row = self._target_row_at(event.position().toPoint().y())
        self._set_drop_row(-1)
        self.rowMoved.emit(source_row, target_row)
        event.acceptProposedAction()

    def _target_row_at(self, y: int) -> int:
        target_row = self.rowAt(y)
        if target_row < 0:
            target_row = self.rowCount()
        return target_row

    def _set_drop_row(self, row: int):
        if self._drop_row == row:
            return
        self._drop_row = row
        if self._drag_peer and hasattr(self._drag_peer, "set_row_drop_index"):
            self._drag_peer.set_row_drop_index(row)
        self.viewport().update()

    def _start_row_drag(self, row: int, start_pos: QPoint):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self._MIME_TYPE, str(row).encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = self._row_drag_pixmap(row)
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(min(start_pos.x() + 10, pixmap.width() - 1), max(0, start_pos.y() - self.rowViewportPosition(row)) + 10))
        self._dragging_row = row
        if self._drag_peer and hasattr(self._drag_peer, "set_dragging_row"):
            self._drag_peer.set_dragging_row(row)
        self.viewport().update()
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._dragging_row = -1
            self._set_drop_row(-1)
            if self._drag_peer and hasattr(self._drag_peer, "set_dragging_row"):
                self._drag_peer.set_dragging_row(-1)
            self.viewport().update()

    def _row_drag_pixmap(self, row: int) -> QPixmap:
        if row < 0 or row >= self.rowCount():
            return QPixmap()
        y = self.rowViewportPosition(row)
        h = self.rowHeight(row)
        if h <= 0:
            return QPixmap()
        left_w = self.viewport().width()
        peer_w = self._drag_peer.viewport().width() if self._drag_peer and hasattr(self._drag_peer, "viewport") else 0
        margin = 10
        base = QPixmap(left_w + peer_w, h)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        self.viewport().render(painter, QPoint(0, 0), QRect(0, y, left_w, h))
        if peer_w > 0:
            self._drag_peer.viewport().render(painter, QPoint(left_w, 0), QRect(0, y, peer_w, h))
        painter.end()
        preview = QPixmap(base.width() + margin * 2, base.height() + margin * 2)
        preview.fill(Qt.transparent)
        painter = QPainter(preview)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 31, 61, 38))
        painter.drawRoundedRect(QRect(margin + 4, margin + 5, base.width(), base.height()), 12, 12)
        painter.setOpacity(0.88)
        painter.drawPixmap(margin, margin, base)
        painter.setOpacity(1)
        painter.setPen(QPen(QColor("#3B82F6"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRect(margin, margin, base.width(), base.height()).adjusted(1, 1, -1, -1), 10, 10)
        painter.end()
        return preview

    def _paint_row_indicator(self, painter: QPainter):
        if self.rowCount() <= 0:
            y = 0
        elif self._drop_row <= 0:
            y = self.rowViewportPosition(0)
        elif self._drop_row >= self.rowCount():
            last = self.rowCount() - 1
            y = self.rowViewportPosition(last) + self.rowHeight(last)
        else:
            y = self.rowViewportPosition(self._drop_row)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#2563EB"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(0, y, self.viewport().width(), y)


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
        self.setWindowTitle("Platform / Bileşen Yönetimi")
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
        add_component.setDefault(False)
        add_component.setAutoDefault(False)
        add_component.clicked.connect(lambda: self._open_component_popover(None))
        add_platform = QPushButton("+ Platform", objectName="pcTopButton")
        add_platform.setDefault(False)
        add_platform.setAutoDefault(False)
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
        self.frozen.rowMoved.connect(self._move_component_row)
        matrix_lay.addWidget(self.frozen)

        self.matrix = MatrixAssignmentTable()
        self.matrix.setObjectName("pcMatrix")
        self.matrix.setShowGrid(True)
        self.matrix.verticalHeader().setVisible(False)
        self.matrix.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.matrix.setSelectionMode(QAbstractItemView.NoSelection)
        self.matrix.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.matrix.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.matrix.setItemDelegate(AssignmentDelegate(self.matrix))
        self.frozen.set_drag_peer(self.matrix)
        header = PlatformHeader(Qt.Horizontal, self.matrix)
        self.matrix.setHorizontalHeader(header)
        self.matrix.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.matrix.horizontalHeader().customContextMenuRequested.connect(self._platform_context_menu)
        self.matrix.horizontalHeader().sectionDoubleClicked.connect(self._open_platform_by_index)
        self.matrix.horizontalHeader().setSectionsMovable(True)
        self.matrix.horizontalHeader().platformMoved.connect(self._move_platform_column)
        self.matrix.horizontalHeader().sectionMoved.connect(self._platform_section_moved)
        self.matrix.cellClicked.connect(self._toggle_assignment)
        self.matrix.rowMoved.connect(self._move_component_row)
        matrix_lay.addWidget(self.matrix, 1)
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

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.KeyPress
            and self.popover
            and self.popover.isVisible()
            and bool(obj.property("componentPopoverSaveOnReturn"))
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        ):
            save = getattr(self, "_component_popover_save", None)
            if callable(save):
                save()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.popover and self.popover.isVisible():
                if isinstance(self.focusWidget(), QTextEdit):
                    super().keyPressEvent(event)
                    return
                save = getattr(self, "_component_popover_save", None)
                if callable(save):
                    save()
                    return
        if event.key() == Qt.Key_Escape:
            if self.popover and self.popover.isVisible():
                self._hide_popover()
                return
            # Popover kapalı — değişiklik varsa uyar
            if self.changed and self.change_count > 0:
                if ask_yes_no(
                    self,
                    "Çıkmak istiyor musunuz?",
                    f"{self.change_count} kaydedilmemiş değişiklik var. Çıkmak istiyor musunuz?",
                ):
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
        header.setSectionsMovable(self._ordering_enabled())
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
            self.matrix.horizontalHeader().setSectionsMovable(enabled)
            if hasattr(self.matrix, "set_order_drag_enabled"):
                self.matrix.set_order_drag_enabled(enabled)
        msg = "" if enabled else "Sıralama yapmak için aramayı temizleyin."
        if hasattr(self, "footer_msg"):
            self.footer_msg.setText(msg)
            self.footer_msg.setVisible(bool(msg))
        tip = msg or "Bileşen satırlarını sol alandan, platformları başlıktan sürükleyerek sıralayın."
        if hasattr(self, "frozen"):
            self.frozen.setToolTip(tip)
        if hasattr(self, "matrix"):
            self.matrix.horizontalHeader().setToolTip(tip)

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

    def _move_platform_column(self, source_index: int, target_index: int):
        if self._syncing_platform_header or not self._ordering_enabled():
            return
        if source_index < 0 or source_index >= len(self.platforms):
            return
        target_index = max(0, min(int(target_index), len(self.platforms)))
        if target_index > source_index:
            target_index -= 1
        if target_index == source_index:
            return
        item = self.platforms.pop(source_index)
        self.platforms.insert(target_index, item)
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
            if ask_yes_no(self, "Bileşen Sil", f"{comp.get('name')} silinsin mi?"):
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
            if ask_yes_no(self, "Platform Sil", f"{platform.get('name')} silinsin mi?"):
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
        save.setDefault(True)
        save.setAutoDefault(True)
        foot_lay.addWidget(cancel)
        foot_lay.addWidget(save)
        lay.addWidget(foot_sep)
        lay.addWidget(foot_frame)

        self._component_popover_saving = False

        def do_save():
            if getattr(self, "_component_popover_saving", False):
                return
            self._component_popover_saving = True
            clean = name.text().strip()
            if not clean:
                self._component_popover_saving = False
                show_warning(self, "Eksik", "Bileşen adı girin.")
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
            self._component_popover_saving = False

        self._component_popover_save = do_save
        for return_widget in (name, unit, note):
            return_widget.setProperty("componentPopoverSaveOnReturn", True)
            return_widget.installEventFilter(self)
        name.returnPressed.connect(do_save)
        note.returnPressed.connect(do_save)
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
                show_warning(self, "Eksik", "Platform adı girin.")
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
            if not ask_yes_no(
                self,
                "Çıkmak istiyor musunuz?",
                f"{self.change_count} kaydedilmemiş değişiklik var. Çıkmak istiyor musunuz?",
            ):
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
