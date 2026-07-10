# -*- coding: utf-8 -*-
"""Runtime hardening for the compact corner menu.

This module isolates three regressions introduced by the layered corner-menu
integration:

* the legacy permission refresh callback can raise before the custom panel is
  rendered;
* QGraphicsDropShadowEffect renders the full rectangular widget buffer and
  leaves a visible square around the painted quarter-circle surface;
* submenu navigation can measure the panel while deleteLater() rows are still
  alive, collapsing the layer and clipping the newly rendered submenu.

The QAction/QMenu tree remains the source of truth. Only the visual adapter and
its pre-open/layout hooks are patched here so business callbacks and permission
gates are not redefined.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QPoint, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen


def install_corner_menu_runtime_fix() -> None:
    """Install the corner-menu fixes once for the current process."""
    from src.ui.widgets import corner_menu_layer as layer

    if getattr(layer, "_STS_CORNER_MENU_RUNTIME_FIX_INSTALLED", False):
        return

    original_overlay_init = layer.CornerMenuOverlay.__init__
    original_button_init = layer.CornerMenuButton.__init__

    def overlay_init(self, host, source_menu, before_open=None, parent=None):
        # Permission visibility is already refreshed when the fresh hidden menu
        # model is built. Re-entering the legacy refresh path from the painted
        # QWidget adapter caused the pre-panel crash seen on Windows/PySide6.
        original_overlay_init(
            self,
            host=host,
            source_menu=source_menu,
            before_open=None,
            parent=parent,
        )

    def button_init(self, parent=None):
        original_button_init(self, parent)
        # QGraphicsDropShadowEffect composites the QWidget's rectangular backing
        # store. The control itself is a painted quarter-circle, so the effect
        # exposes a square halo. Draw the shadow from the same path instead.
        self.setGraphicsEffect(None)
        self._shadow = None

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def paint_event(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        p = self._progress
        visual_size = 72.0 + (8.0 * p)
        left = self.width() - visual_size

        path = QPainterPath()
        path.moveTo(self.width(), 0)
        path.lineTo(left, 0)
        path.quadTo(left, visual_size, self.width(), visual_size)
        path.closeSubpath()

        # Path-based soft shadow. Every pass follows the actual quarter-circle;
        # no rectangular graphics-effect buffer is visible.
        shadow_steps = 7
        for step in range(shadow_steps, 0, -1):
            spread = float(step)
            shadow_path = QPainterPath(path)
            shadow_path.translate(-0.35 * spread, 0.8 * spread)
            alpha = round((7 + (3 * p)) * (shadow_steps - step + 1) / shadow_steps)
            painter.fillPath(shadow_path, QColor(17, 38, 58, alpha))

        gradient = QLinearGradient(left, 0, self.width(), visual_size)
        gradient.setColorAt(0.0, self._mix(QColor("#2a4056"), QColor("#355169"), p))
        gradient.setColorAt(1.0, self._mix(QColor("#172a3b"), QColor("#1c3145"), p))
        painter.fillPath(path, gradient)

        cx = self.width() - 28.0 - (2.0 * p)
        cy = 35.0 + p
        half = 10.5
        gap = 6.0
        t = self._icon_progress

        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        def lerp(ax: float, ay: float, bx: float, by: float) -> QPoint:
            return QPoint(
                round(ax * (1.0 - t) + bx * t),
                round(ay * (1.0 - t) + by * t),
            )

        painter.drawLine(
            lerp(cx - half, cy - gap, cx - 8, cy - 8),
            lerp(cx + half, cy - gap, cx + 8, cy + 8),
        )
        if t < 0.62:
            middle_half = half * max(0.0, 1.0 - (t / 0.62))
            painter.drawLine(
                QPoint(round(cx - middle_half), round(cy)),
                QPoint(round(cx + middle_half), round(cy)),
            )
        painter.drawLine(
            lerp(cx - half, cy + gap, cx - 8, cy + 8),
            lerp(cx + half, cy + gap, cx + 8, cy - 8),
        )

    layer.CornerMenuOverlay.__init__ = overlay_init
    layer.CornerMenuButton.__init__ = button_init
    layer.CornerMenuButton.set_progress = set_progress
    layer.CornerMenuButton.progress = Property(
        float,
        layer.CornerMenuButton.get_progress,
        layer.CornerMenuButton.set_progress,
    )
    layer.CornerMenuButton.paintEvent = paint_event
    layer._STS_CORNER_MENU_RUNTIME_FIX_INSTALLED = True
