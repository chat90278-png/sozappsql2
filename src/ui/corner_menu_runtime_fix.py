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

import dis
import sys

from PySide6.QtCore import Property, QPoint, Qt, qDebug
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen


def install_corner_menu_runtime_fix() -> None:
    """Install the corner-menu fixes once for the current process."""
    import shiboken6

    from src.ui import main_page_analysis_window as main_page
    from src.ui import main_window as legacy_main
    from src.ui.widgets import corner_menu_layer as layer

    if getattr(layer, "_STS_CORNER_MENU_RUNTIME_FIX_INSTALLED", False):
        return

    original_overlay_init = layer.CornerMenuOverlay.__init__
    original_button_init = layer.CornerMenuButton.__init__
    original_handle_action = layer.CornerMenuOverlay._handle_action
    original_build_top_actions_menu = legacy_main.MainWindow._build_top_actions_menu
    original_analysis_build = main_page.MainWindow.build
    build_call_count = 0

    def emit_debug(message: str) -> None:
        try:
            print(message, flush=True)
        except Exception:
            pass
        try:
            qDebug(message)
        except Exception:
            pass

    def debug_menu_model(label, menu) -> None:
        try:
            menu_valid = shiboken6.isValid(menu)
            file_action = (
                next(
                    (
                        item
                        for item in menu.actions()
                        if str(item.text() or "").replace("&", "") == "Dosya İşlemleri"
                    ),
                    None,
                )
                if menu_valid
                else None
            )
            file_action_valid = (
                shiboken6.isValid(file_action) if file_action is not None else False
            )
            message = (
                f"[DEBUG][corner-menu] {label} "
                f"menu_id={id(menu) if menu is not None else 'N/A'} "
                f"menu_valid={menu_valid} "
                f"menu_parent={menu.parent() if menu_valid else 'N/A'} "
                f"file_action_id={id(file_action) if file_action is not None else 'N/A'} "
                f"file_action_valid={file_action_valid} "
                f"file_action_parent={file_action.parent() if file_action_valid else 'N/A'}"
            )
        except Exception as exc:
            message = f"[DEBUG][corner-menu] {label} inspection failed: {exc}"
        emit_debug(message)

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

    def handle_action(self, action) -> None:
        try:
            valid = shiboken6.isValid(action)
            message = (
                f"[DEBUG][corner-menu] _handle_action action id={id(action)} valid={valid} "
                f"text={action.text() if valid else 'N/A'} "
                f"parent={action.parent() if valid else 'N/A'}"
            )
        except Exception as exc:
            message = f"[DEBUG][corner-menu] _handle_action inspection failed: {exc}"
        emit_debug(message)
        return original_handle_action(self, action)

    def build_top_actions_menu(self, parent):
        nonlocal build_call_count
        menu = original_build_top_actions_menu(self, parent)
        build_call_count += 1
        if build_call_count == 1:
            label = "build-call=legacy"
        elif build_call_count == 2:
            label = "build-call=layered"
        else:
            label = f"build-call={build_call_count}"
        debug_menu_model(label, menu)
        return menu

    analysis_build_code = original_analysis_build.__code__
    delete_later_line = None
    try:
        if "deleteLater" not in analysis_build_code.co_names:
            raise RuntimeError("deleteLater not found in analysis build bytecode names")

        instructions = list(dis.get_instructions(analysis_build_code))
        line_starts = list(dis.findlinestarts(analysis_build_code))
        for index, instruction in enumerate(instructions):
            if (
                instruction.opname not in {"LOAD_METHOD", "LOAD_ATTR"}
                or instruction.argval != "deleteLater"
                or index == 0
            ):
                continue
            previous = instructions[index - 1]
            if (
                previous.opname != "LOAD_FAST"
                or previous.argval != "experimental_menu"
            ):
                continue

            for offset, line_number in line_starts:
                if offset > instruction.offset:
                    break
                if line_number is not None:
                    delete_later_line = line_number
            break

        if delete_later_line is None:
            raise RuntimeError(
                "experimental_menu.deleteLater bytecode site not found"
            )
    except Exception as exc:
        emit_debug(
            f"[DEBUG][corner-menu] deleteLater bytecode discovery failed: {exc}"
        )

    def analysis_build(self, *args, **kwargs):
        previous_trace = sys.gettrace()

        def trace(frame, event, arg):
            if frame.f_code is analysis_build_code:
                if event == "line" and frame.f_lineno == delete_later_line:
                    debug_menu_model(
                        "before experimental_menu.deleteLater",
                        frame.f_locals.get("experimental_menu"),
                    )
                return trace
            return None

        if delete_later_line is not None:
            sys.settrace(trace)
        try:
            return original_analysis_build(self, *args, **kwargs)
        finally:
            if delete_later_line is not None:
                sys.settrace(previous_trace)

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
    layer.CornerMenuOverlay._handle_action = handle_action
    layer.CornerMenuButton.__init__ = button_init
    legacy_main.MainWindow._build_top_actions_menu = build_top_actions_menu
    main_page.MainWindow.build = analysis_build
    layer.CornerMenuButton.set_progress = set_progress
    layer.CornerMenuButton.progress = Property(
        float,
        layer.CornerMenuButton.get_progress,
        layer.CornerMenuButton.set_progress,
    )
    layer.CornerMenuButton.paintEvent = paint_event
    layer._STS_CORNER_MENU_RUNTIME_FIX_INSTALLED = True
