# -*- coding: utf-8 -*-
"""Safe animated corner-menu overlay for the compact STS main window.

Existing QAction/QMenu trees remain the source of truth for callbacks,
submenus and permission visibility, but no QMenu is ever displayed.  The
approved quarter-circle control and attached panel are ordinary child widgets.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, QEasingCurve, QObject, QPoint, Property, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


_ROOT_CAPTION = "STS MENÜ"

_OVERLAY_STYLE = r"""
QFrame#cornerMenuPanel {
    background:#FFFFFF;
    border:1px solid #CAD6E3;
    border-radius:16px;
    border-top-right-radius:0px;
}
QWidget#cornerMenuCaptionRow {
    background:transparent;
    border:0;
}
QLabel#cornerMenuCaption {
    background:transparent;
    color:#8B98A9;
    border:0;
    padding:0;
    font-size:10px;
    font-weight:700;
}
QPushButton#cornerMenuBack {
    background:transparent;
    color:#60758D;
    border:0;
    border-radius:8px;
    font-size:20px;
    font-weight:800;
}
QPushButton#cornerMenuBack:hover {
    background:#EDF4FF;
    color:#1849A2;
}
QPushButton#cornerMenuRow {
    background:transparent;
    border:0;
    border-radius:10px;
    padding:0;
}
QPushButton#cornerMenuRow[hovered="true"] {
    background:#EDF4FF;
}
QPushButton#cornerMenuRow:pressed {
    background:#E2ECFC;
}
QPushButton#cornerMenuRow:disabled {
    background:transparent;
}
QLabel#cornerMenuRowTitle,
QLabel#cornerMenuRowArrow {
    background:transparent;
    border:0;
    color:#0F172A;
    font-size:13px;
    font-weight:800;
}
QLabel#cornerMenuRowArrow {
    color:#6F8299;
    font-size:16px;
}
QLabel#cornerMenuRowTitle[hovered="true"],
QLabel#cornerMenuRowArrow[hovered="true"] {
    color:#1849A2;
}
QLabel#cornerMenuRowTitle[disabled="true"],
QLabel#cornerMenuRowArrow[disabled="true"] {
    color:#94A3B8;
}
QFrame#cornerMenuSeparator {
    background:#E3EAF2;
    border:0;
}
"""


def _repolish(widget: QWidget) -> None:
    try:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    except Exception:
        pass
    widget.update()


class CornerMenuButton(QWidget):
    """One painted quarter-circle surface; no inner button and no popup API."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("cornerMenuSurface")
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedSize(80, 80)

        self._hovered = False
        self._menu_open = False
        self._progress = 0.0
        self._icon_progress = 0.0

        self._progress_anim = QPropertyAnimation(self, b"progress", self)
        self._progress_anim.setDuration(180)
        self._progress_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._icon_anim = QPropertyAnimation(self, b"iconProgress", self)
        self._icon_anim.setDuration(180)
        self._icon_anim.setEasingCurve(QEasingCurve.OutCubic)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(-3, 7)
        shadow.setColor(QColor(17, 38, 58, 80))
        self.setGraphicsEffect(shadow)
        self._shadow = shadow

    def get_progress(self) -> float:
        return float(self._progress)

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self._shadow.setBlurRadius(22.0 + 8.0 * self._progress)
        self._shadow.setOffset(-3.0 - self._progress, 7.0 + self._progress)
        self.update()

    progress = Property(float, get_progress, set_progress)

    def get_icon_progress(self) -> float:
        return float(self._icon_progress)

    def set_icon_progress(self, value: float) -> None:
        self._icon_progress = max(0.0, min(1.0, float(value)))
        self.update()

    iconProgress = Property(float, get_icon_progress, set_icon_progress)

    def set_menu_open(self, is_open: bool) -> None:
        self._menu_open = bool(is_open)
        self._animate_progress(1.0 if self._menu_open or self._hovered else 0.0)
        self._icon_anim.stop()
        self._icon_anim.setStartValue(self._icon_progress)
        self._icon_anim.setEndValue(1.0 if self._menu_open else 0.0)
        self._icon_anim.start()

    def _animate_progress(self, target: float) -> None:
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._progress)
        self._progress_anim.setEndValue(float(target))
        self._progress_anim.start()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._animate_progress(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if not self._menu_open:
            self._animate_progress(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @staticmethod
    def _mix(a: QColor, b: QColor, amount: float) -> QColor:
        t = max(0.0, min(1.0, float(amount)))
        return QColor(
            round(a.red() * (1.0 - t) + b.red() * t),
            round(a.green() * (1.0 - t) + b.green() * t),
            round(a.blue() * (1.0 - t) + b.blue() * t),
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        p = self._progress
        visual_size = 72.0 + 8.0 * p
        left = self.width() - visual_size

        path = QPainterPath()
        path.moveTo(self.width(), 0)
        path.lineTo(left, 0)
        path.quadTo(left, visual_size, self.width(), visual_size)
        path.closeSubpath()

        idle_start = QColor("#2A4056")
        idle_end = QColor("#172A3B")
        hover_start = QColor("#355169")
        hover_end = QColor("#1C3145")
        gradient = QLinearGradient(left, 0, self.width(), visual_size)
        gradient.setColorAt(0.0, self._mix(idle_start, hover_start, p))
        gradient.setColorAt(1.0, self._mix(idle_end, hover_end, p))
        painter.fillPath(path, gradient)

        cx = self.width() - 28.0 - 2.0 * p
        cy = 35.0 + p
        half = 10.5
        gap = 6.0
        t = self._icon_progress

        pen = QPen(QColor("#FFFFFF"))
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        def lerp_point(ax: float, ay: float, bx: float, by: float) -> QPoint:
            return QPoint(round(ax * (1.0 - t) + bx * t), round(ay * (1.0 - t) + by * t))

        painter.drawLine(
            lerp_point(cx - half, cy - gap, cx - 8, cy - 8),
            lerp_point(cx + half, cy - gap, cx + 8, cy + 8),
        )
        if t < 0.62:
            middle_half = half * max(0.0, 1.0 - (t / 0.62))
            painter.drawLine(QPoint(round(cx - middle_half), round(cy)), QPoint(round(cx + middle_half), round(cy)))
        painter.drawLine(
            lerp_point(cx - half, cy + gap, cx - 8, cy + 8),
            lerp_point(cx + half, cy + gap, cx + 8, cy - 8),
        )


class CornerMenuRow(QPushButton):
    requested = Signal(object)

    def __init__(self, action, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.action_ref = action
        self.setObjectName("cornerMenuRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setEnabled(bool(action.isEnabled()))
        self.setProperty("hovered", "false")
        self.clicked.connect(lambda: self.requested.emit(self.action_ref))

        row = QHBoxLayout(self)
        row.setContentsMargins(13, 0, 10, 0)
        row.setSpacing(8)

        self.title_label = QLabel(str(action.text() or "").replace("&", ""), self)
        self.title_label.setObjectName("cornerMenuRowTitle")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setProperty("hovered", "false")
        self.title_label.setProperty("disabled", "true" if not action.isEnabled() else "false")
        row.addWidget(self.title_label, 1)

        self.arrow_label = QLabel("›" if action.menu() is not None else "", self)
        self.arrow_label.setObjectName("cornerMenuRowArrow")
        self.arrow_label.setAlignment(Qt.AlignCenter)
        self.arrow_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.arrow_label.setProperty("hovered", "false")
        self.arrow_label.setProperty("disabled", "true" if not action.isEnabled() else "false")
        self.arrow_label.setFixedWidth(14)
        row.addWidget(self.arrow_label, 0)

    def _set_hovered(self, hovered: bool) -> None:
        value = "true" if hovered else "false"
        self.setProperty("hovered", value)
        self.title_label.setProperty("hovered", value)
        self.arrow_label.setProperty("hovered", value)
        _repolish(self)
        _repolish(self.title_label)
        _repolish(self.arrow_label)

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered(False)
        super().leaveEvent(event)


class CornerMenuPanel(QFrame):
    actionRequested = Signal(object)
    backRequested = Signal()
    hiddenAfterClose = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("cornerMenuPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(238)
        self.setStyleSheet(_OVERLAY_STYLE)

        self._open_progress = 0.0
        self._target_rect = QRect()
        self._closing = False

        self._animation = QPropertyAnimation(self, b"openProgress", self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(20, 43, 68, 70))
        self.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(2)
        self.hide()

    def get_open_progress(self) -> float:
        return float(self._open_progress)

    def set_open_progress(self, value: float) -> None:
        self._open_progress = max(0.0, min(1.0, float(value)))
        if not self._target_rect.isValid():
            return
        p = self._open_progress
        scale = 0.97 + 0.03 * p
        width = max(1, round(self._target_rect.width() * scale))
        height = max(1, round(self._target_rect.height() * scale))
        x = self._target_rect.right() - width + 1
        y = self._target_rect.top() - round((1.0 - p) * 10.0)
        self.setGeometry(x, y, width, height)
        self.update()

    openProgress = Property(float, get_open_progress, set_open_progress)

    def set_target_rect(self, rect: QRect) -> None:
        self._target_rect = QRect(rect)
        if self.isVisible() and self._open_progress >= 0.999:
            self.setGeometry(self._target_rect)

    def _clear_rows(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def show_menu(self, menu: QMenu, caption: str = _ROOT_CAPTION, allow_back: bool = False) -> None:
        self._clear_rows()

        caption_row = QWidget(self)
        caption_row.setObjectName("cornerMenuCaptionRow")
        caption_layout = QHBoxLayout(caption_row)
        caption_layout.setContentsMargins(7, 0, 8, 3)
        caption_layout.setSpacing(5)

        if allow_back:
            back = QPushButton("‹", caption_row)
            back.setObjectName("cornerMenuBack")
            back.setCursor(Qt.PointingHandCursor)
            back.setFixedSize(24, 24)
            back.clicked.connect(self.backRequested)
            caption_layout.addWidget(back, 0)

        caption_label = QLabel(caption, caption_row)
        caption_label.setObjectName("cornerMenuCaption")
        caption_layout.addWidget(caption_label, 1)
        self._layout.addWidget(caption_row)

        pending_separator = False
        for action in [item for item in menu.actions() if item.isVisible()]:
            if action.isSeparator():
                pending_separator = True
                continue
            if pending_separator:
                separator = QFrame(self)
                separator.setObjectName("cornerMenuSeparator")
                separator.setFixedHeight(1)
                self._layout.addSpacing(3)
                self._layout.addWidget(separator)
                self._layout.addSpacing(3)
                pending_separator = False
            row = CornerMenuRow(action, self)
            row.requested.connect(self.actionRequested)
            self._layout.addWidget(row)

        self.adjustSize()
        self.setFixedWidth(238)

    def open_animated(self) -> None:
        if not self._target_rect.isValid():
            return
        self._closing = False
        self._animation.stop()
        self.set_open_progress(0.0)
        self.show()
        self.raise_()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()

    def close_animated(self) -> None:
        if not self.isVisible():
            self.hiddenAfterClose.emit()
            return
        self._closing = True
        self._animation.stop()
        self._animation.setStartValue(self._open_progress)
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self._closing and self._open_progress <= 0.001:
            self.hide()
            self._closing = False
            self.hiddenAfterClose.emit()


class CornerMenuOverlay(QObject):
    """Adapts an existing QMenu action tree to the non-popup overlay widgets."""

    def __init__(
        self,
        host: QWidget,
        source_menu: QMenu,
        before_open: Optional[Callable[[], None]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent or host)
        self.host = host
        self.source_menu = source_menu
        self.before_open = before_open
        self.button = CornerMenuButton(host)
        self.panel = CornerMenuPanel(host)
        self._open = False
        self._menu_stack: list[QMenu] = []

        self.button.clicked.connect(self.toggle)
        self.panel.actionRequested.connect(self._handle_action)
        self.panel.backRequested.connect(self._go_back)
        self.panel.hiddenAfterClose.connect(self._finish_close)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.reposition()

    def dispose(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.button.deleteLater()
        self.panel.deleteLater()

    def reposition(self) -> None:
        self.button.move(max(self.host.width() - self.button.width(), 0), 0)
        self.button.raise_()
        panel_height = max(1, self.panel.sizeHint().height())
        target = QRect(
            max(self.host.width() - self.panel.width() - 18, 0),
            56,
            self.panel.width(),
            panel_height,
        )
        self.panel.set_target_rect(target)
        if self.panel.isVisible():
            self.panel.raise_()
            self.button.raise_()

    def toggle(self) -> None:
        self.set_open(not self._open)

    def set_open(self, is_open: bool) -> None:
        target = bool(is_open)
        if target == self._open:
            return
        self._open = target
        self.button.set_menu_open(target)
        if target:
            if callable(self.before_open):
                self.before_open()
            self._menu_stack = [self.source_menu]
            self._show_current_menu(animated=True)
        else:
            self.panel.close_animated()

    def close(self) -> None:
        self.set_open(False)

    def _finish_close(self) -> None:
        self._open = False
        self._menu_stack = []
        self.button.set_menu_open(False)

    def _show_current_menu(self, animated: bool = False) -> None:
        if not self._menu_stack:
            return
        menu = self._menu_stack[-1]
        caption = _ROOT_CAPTION if len(self._menu_stack) == 1 else str(menu.title() or "MENÜ").replace("&", "").upper()
        self.panel.show_menu(menu, caption=caption, allow_back=len(self._menu_stack) > 1)
        self.reposition()
        if animated:
            self.panel.open_animated()
        else:
            self.panel.set_open_progress(1.0)
            self.panel.show()
            self.panel.raise_()
            self.button.raise_()

    def _handle_action(self, action) -> None:
        submenu = action.menu()
        if submenu is not None:
            self._menu_stack.append(submenu)
            self._show_current_menu(animated=False)
            return
        if action.isEnabled():
            self.close()
            action.trigger()

    def _go_back(self) -> None:
        if len(self._menu_stack) <= 1:
            return
        self._menu_stack.pop()
        self._show_current_menu(animated=False)

    def eventFilter(self, _obj, event) -> bool:
        etype = event.type()
        if etype == QEvent.KeyPress and self._open and event.key() == Qt.Key_Escape:
            self.close()
            return True
        if etype == QEvent.MouseButtonPress and self._open:
            try:
                global_pos = event.globalPosition().toPoint()
            except Exception:
                return False
            button_rect = QRect(self.button.mapToGlobal(QPoint(0, 0)), self.button.size())
            panel_rect = QRect(self.panel.mapToGlobal(QPoint(0, 0)), self.panel.size())
            if not button_rect.contains(global_pos) and not panel_rect.contains(global_pos):
                self.close()
        return False
