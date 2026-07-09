from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .analysis_custom_dashboard import CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
from .analysis_dashboard_edit import DashboardEditSession, InteractionMode
from .analysis_dashboard_geometry import GridGeometry
from .analysis_dashboard_layout import DashboardLayoutError
from .analysis_models import AnalysisCard, ResizePolicy


DRAG_HANDLE_HIT_WIDTH = 32
EDIT_BAR_HEIGHT = 28
RESIZE_HANDLE_HIT_SIZE = 28
QUICK_ACTION_BUTTON_SIZE = 28


class DashboardQuickAction(str, Enum):
    EDIT_ANALYSIS = "edit_analysis"
    EDIT_VISUAL = "edit_visual"
    UNPIN = "unpin"


def auto_scroll_delta(
    pointer_y: int,
    viewport_height: int,
    *,
    edge_margin: int = 52,
    max_step: int = 18,
) -> int:
    """Return a bounded vertical scroll step for a drag near viewport edges."""

    height = max(0, int(viewport_height))
    margin = max(1, min(int(edge_margin), max(1, height // 2)))
    step = max(1, int(max_step))
    y = int(pointer_y)
    if y < margin:
        ratio = min(1.0, max(0.0, (margin - y) / margin))
        return -max(1, round(step * ratio))
    if y > height - margin:
        ratio = min(1.0, max(0.0, (y - (height - margin)) / margin))
        return max(1, round(step * ratio))
    return 0


class _PointerHandle(QLabel):
    def __init__(
        self,
        text: str,
        parent: QWidget,
        *,
        on_press: Callable[[QPointF], bool],
        on_move: Callable[[QPointF], None],
        on_release: Callable[[QPointF], None],
    ) -> None:
        super().__init__(text, parent)
        self._on_press = on_press
        self._on_move = on_move
        self._on_release = on_release
        self._active = False
        self._idle_cursor = Qt.OpenHandCursor
        self._active_cursor = Qt.ClosedHandCursor
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(self._idle_cursor)

    @property
    def active(self) -> bool:
        return self._active

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton and self._on_press(event.globalPosition()):
            self._active = True
            self.setCursor(self._active_cursor)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._active:
            self._on_move(event.globalPosition())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._active and event.button() == Qt.LeftButton:
            self._active = False
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
            self.setCursor(self._idle_cursor)
            self._on_release(event.globalPosition())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def set_cursors(self, idle_cursor, active_cursor=None) -> None:
        self._idle_cursor = idle_cursor
        self._active_cursor = active_cursor if active_cursor is not None else idle_cursor
        if not self._active:
            self.setCursor(self._idle_cursor)

    def cancel(self) -> None:
        if self._active and QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self._active = False
        self.setCursor(self._idle_cursor)


class DashboardCardFrame(QFrame):
    """Dashboard-only edit chrome around an existing analysis card widget."""

    def __init__(
        self,
        card: AnalysisCard,
        placement_id: str,
        session: DashboardEditSession,
        content_builder: Callable[[AnalysisCard, QWidget], QWidget],
        parent: QWidget,
        *,
        on_drag_press: Callable[[str, QPointF], bool],
        on_drag_move: Callable[[QPointF], None],
        on_drag_release: Callable[[QPointF], None],
        on_resize_press: Callable[[str, QPointF], bool],
        on_resize_move: Callable[[QPointF], None],
        on_resize_release: Callable[[QPointF], None],
        on_remove: Callable[[str], None],
        on_quick_action: Callable[[str, DashboardQuickAction], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.card = card
        self.placement_id = placement_id
        self.session = session
        self._on_quick_action = on_quick_action
        self._quick_actions_enabled = bool(
            card.meta.get("custom_analysis")
            and str(card.meta.get("custom_analysis_id") or "").strip()
            and str(card.meta.get("dashboard_source_screen_id") or "").strip()
            == CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
        )
        self.setObjectName("analysisDashboardCardFrame")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)
        self.setAttribute(Qt.WA_Hover, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.edit_bar = QFrame(self)
        self.edit_bar.setObjectName("analysisDashboardEditBar")
        self.edit_bar.setFixedHeight(EDIT_BAR_HEIGHT)
        edit_layout = QHBoxLayout(self.edit_bar)
        edit_layout.setContentsMargins(4, 1, 4, 1)
        edit_layout.setSpacing(4)
        self.drag_handle = _PointerHandle(
            "⠿",
            self.edit_bar,
            on_press=lambda point: on_drag_press(self.placement_id, point),
            on_move=on_drag_move,
            on_release=on_drag_release,
        )
        self.drag_handle.setObjectName("analysisDashboardDragHandle")
        self.drag_handle.setToolTip("Kartı sürükleyerek taşı")
        self.drag_handle.setFixedSize(DRAG_HANDLE_HIT_WIDTH, EDIT_BAR_HEIGHT - 2)
        edit_layout.addWidget(self.drag_handle, 0)
        self.edit_title = QLabel(card.title, self.edit_bar)
        self.edit_title.setObjectName("analysisDashboardEditTitle")
        self.edit_title.setToolTip(card.title)
        self.edit_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        edit_layout.addWidget(self.edit_title, 1)
        self.remove_button = QPushButton("×", self.edit_bar)
        self.remove_button.setObjectName("analysisDashboardRemoveButton")
        self.remove_button.setToolTip("Dashboard'dan kaldır")
        self.remove_button.setFixedSize(24, 24)
        self.remove_button.clicked.connect(lambda _checked=False: on_remove(self.placement_id))
        edit_layout.addWidget(self.remove_button, 0)
        layout.addWidget(self.edit_bar, 0)

        self.content = content_builder(card, self)
        self.content.setMinimumSize(0, 0)
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if self._quick_actions_enabled:
            for title in self.content.findChildren(QLabel, "analysisCardTitle"):
                title.setContentsMargins(0, 0, QUICK_ACTION_BUTTON_SIZE + 6, 0)
        layout.addWidget(self.content, 1)

        self.quick_button = QToolButton(self)
        self.quick_button.setObjectName("analysisDashboardQuickActionButton")
        self.quick_button.setText("⋯")
        self.quick_button.setToolTip("Özel analiz işlemleri")
        self.quick_button.setPopupMode(QToolButton.InstantPopup)
        self.quick_button.setFixedSize(QUICK_ACTION_BUTTON_SIZE, QUICK_ACTION_BUTTON_SIZE)
        self.quick_menu = QMenu(self.quick_button)
        self.quick_menu.setObjectName("analysisDashboardQuickActionMenu")
        for text, action_id in (
            ("Analizi Düzenle", DashboardQuickAction.EDIT_ANALYSIS),
            ("Görünümü Düzenle", DashboardQuickAction.EDIT_VISUAL),
            ("Dashboard'dan Kaldır", DashboardQuickAction.UNPIN),
        ):
            action = QAction(text, self.quick_menu)
            action.setData(action_id.value)
            self.quick_menu.addAction(action)
        self.quick_menu.triggered.connect(self._quick_menu_triggered)
        self.quick_button.setMenu(self.quick_menu)
        self.quick_button.raise_()

        self.resize_handle = _PointerHandle(
            "◢",
            self,
            on_press=lambda point: on_resize_press(self.placement_id, point),
            on_move=on_resize_move,
            on_release=on_resize_release,
        )
        self.resize_handle.setObjectName("analysisDashboardResizeHandle")
        self.resize_handle.set_cursors(Qt.SizeFDiagCursor)
        self.resize_handle.setToolTip("Kartı yeniden boyutlandır")
        self.resize_handle.raise_()
        self._edit_mode_state: bool | None = None
        self._active_interaction = False
        self.set_edit_mode(False)

    def set_edit_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._edit_mode_state == enabled:
            return
        self._edit_mode_state = enabled
        placement = next(
            (item for item in self.session.working_workspace.placements if item.placement_id == self.placement_id),
            None,
        )
        locked = bool(placement.locked) if placement is not None else False
        hints = self.session.working_workspace.layout_hints_for(self.placement_id)
        self.edit_bar.setVisible(enabled)
        self.drag_handle.setVisible(enabled and not locked)
        self.resize_handle.setVisible(
            enabled and not locked and hints.resize_policy != ResizePolicy.NONE
        )
        if hints.resize_policy in {ResizePolicy.FIXED_HEIGHT, ResizePolicy.HORIZONTAL}:
            self.resize_handle.set_cursors(Qt.SizeHorCursor)
        elif hints.resize_policy in {ResizePolicy.FIXED_WIDTH, ResizePolicy.VERTICAL}:
            self.resize_handle.set_cursors(Qt.SizeVerCursor)
        else:
            self.resize_handle.set_cursors(Qt.SizeFDiagCursor)
        self.remove_button.setVisible(enabled)
        self.quick_button.setVisible(not enabled and self._quick_actions_enabled)
        for title in self.content.findChildren(QLabel, "analysisCardTitle"):
            title.setVisible(not enabled)
        self.setProperty("dashboardEditing", "true" if enabled else "false")
        self._refresh_style()
        self.resize_handle.raise_()
        self.quick_button.raise_()

    def set_active_interaction(self, active: bool) -> None:
        active = bool(active)
        if self._active_interaction == active:
            return
        self._active_interaction = active
        self.setProperty("dashboardActive", "true" if active else "false")
        self._refresh_style()

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        size = RESIZE_HANDLE_HIT_SIZE
        self.resize_handle.setGeometry(
            max(0, self.width() - size),
            max(0, self.height() - size),
            size,
            size,
        )
        quick_size = QUICK_ACTION_BUTTON_SIZE
        self.quick_button.setGeometry(
            max(0, self.width() - quick_size - 4),
            4,
            quick_size,
            quick_size,
        )
        self.resize_handle.raise_()
        self.quick_button.raise_()

    def _quick_menu_triggered(self, action: QAction) -> None:
        if not self._quick_actions_enabled or self._edit_mode_state:
            return
        try:
            action_id = DashboardQuickAction(str(action.data() or ""))
        except ValueError:
            return
        if self._on_quick_action is not None:
            self._on_quick_action(self.placement_id, action_id)

    def cancel_pointer_state(self) -> None:
        self.drag_handle.cancel()
        self.resize_handle.cancel()
        self.set_active_interaction(False)


class DashboardCanvas(QWidget):
    """Qt adapter that renders logical placements and forwards pointer input to the edit session."""

    def __init__(
        self,
        session: DashboardEditSession,
        cards: Iterable[AnalysisCard],
        content_builder: Callable[[AnalysisCard, QWidget], QWidget],
        parent: QWidget | None = None,
        *,
        edit_mode: bool = False,
        history_changed: Callable[[], None] | None = None,
        quick_action: Callable[[str, DashboardQuickAction], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self._frames: dict[str, DashboardCardFrame] = {}
        self._edit_mode = bool(edit_mode)
        self._history_changed = history_changed
        self._quick_action_callback = quick_action
        self.setObjectName("analysisDashboardCanvas")
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        self._drag_placeholder = QFrame(self)
        self._drag_placeholder.setObjectName("analysisDashboardDragPlaceholder")
        self._drag_placeholder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._drag_placeholder.hide()

        for card in cards:
            placement_id = str(card.meta.get("dashboard_placement_id") or "")
            if not placement_id:
                continue
            frame = DashboardCardFrame(
                card,
                placement_id,
                session,
                content_builder,
                self,
                on_drag_press=self._begin_drag,
                on_drag_move=self._preview_drag,
                on_drag_release=self._finish_pointer_interaction,
                on_resize_press=self._begin_resize,
                on_resize_move=self._preview_resize,
                on_resize_release=self._finish_pointer_interaction,
                on_remove=self.remove_placement,
                on_quick_action=self._emit_quick_action,
            )
            self._frames[placement_id] = frame
        self.set_edit_mode(self._edit_mode)
        self._apply_workspace_geometry()

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def drag_placeholder_geometry(self):
        return self._drag_placeholder.geometry()

    @property
    def drag_placeholder_visible(self) -> bool:
        return self._drag_placeholder.isVisible()

    def set_edit_mode(self, enabled: bool) -> None:
        if not enabled:
            self.cancel_active_interaction()
        self._edit_mode = bool(enabled)
        for frame in self._frames.values():
            frame.set_edit_mode(self._edit_mode)
        if not self._edit_mode:
            self._hide_drag_placeholder()
        self.update()

    def refresh_geometry(self) -> None:
        self._apply_workspace_geometry()

    def remove_placement(self, placement_id: str) -> None:
        if not self._edit_mode:
            return
        self._hide_drag_placeholder()
        if self.session.remove_placement(placement_id):
            self._apply_workspace_geometry()
            self._notify_history_changed()

    def reset_layout(self) -> None:
        self._hide_drag_placeholder()
        if self._edit_mode and self.session.reset_layout():
            self._apply_workspace_geometry()
            self._notify_history_changed()

    def undo(self) -> None:
        self._hide_drag_placeholder()
        if self._edit_mode and self.session.undo():
            self._apply_workspace_geometry()
            self._notify_history_changed()

    def redo(self) -> None:
        self._hide_drag_placeholder()
        if self._edit_mode and self.session.redo():
            self._apply_workspace_geometry()
            self._notify_history_changed()

    def cancel_active_interaction(self) -> None:
        if self.session.cancel_interaction():
            self._apply_workspace_geometry()
        self._hide_drag_placeholder()
        for frame in self._frames.values():
            frame.cancel_pointer_state()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_workspace_geometry()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if not self._edit_mode or self.width() <= 110:
            return
        try:
            geometry = GridGeometry(self.width(), self.session.working_workspace.layout)
        except ValueError:
            return
        painter = QPainter(self)
        grid_color = QColor(148, 163, 184, 42)
        painter.setPen(QPen(grid_color, 1, Qt.DotLine))
        for column in range(self.session.working_workspace.layout.columns + 1):
            x = column * geometry.column_pitch
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        row = 0
        while row * geometry.row_pitch <= self.height():
            y = row * geometry.row_pitch
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))
            row += 1

    def _begin_drag(self, placement_id: str, point: QPointF) -> bool:
        if not self._edit_mode:
            return False
        try:
            self.session.begin_drag(
                placement_id,
                mouse_x=point.x(),
                mouse_y=point.y(),
                viewport_width=max(1, self.width()),
            )
        except DashboardLayoutError:
            return False
        self._set_active_frame(placement_id)
        self._update_drag_placeholder()
        return True

    def _preview_drag(self, point: QPointF) -> None:
        try:
            changed = self.session.preview_drag(mouse_x=point.x(), mouse_y=point.y())
        except DashboardLayoutError:
            changed = False
        if changed:
            self._apply_workspace_geometry()
            self._update_drag_placeholder()
        self._auto_scroll_drag(point)

    def _begin_resize(self, placement_id: str, point: QPointF) -> bool:
        if not self._edit_mode:
            return False
        try:
            self.session.begin_resize(
                placement_id,
                mouse_x=point.x(),
                mouse_y=point.y(),
                viewport_width=max(1, self.width()),
            )
        except DashboardLayoutError:
            return False
        self._set_active_frame(placement_id)
        self._hide_drag_placeholder()
        return True

    def _preview_resize(self, point: QPointF) -> None:
        try:
            changed = self.session.preview_resize(mouse_x=point.x(), mouse_y=point.y())
        except DashboardLayoutError:
            changed = False
        if changed:
            self._apply_workspace_geometry()

    def _finish_pointer_interaction(self, _point: QPointF) -> None:
        changed = self.session.finish_interaction()
        self._hide_drag_placeholder()
        self._set_active_frame(None)
        self._apply_workspace_geometry()
        if changed:
            self._notify_history_changed()

    def _set_active_frame(self, placement_id: str | None) -> None:
        for current_id, frame in self._frames.items():
            frame.set_active_interaction(current_id == placement_id)

    def _update_drag_placeholder(self) -> None:
        placement_id = self.session.active_placement_id
        if self.session.interaction_mode != InteractionMode.DRAGGING or not placement_id:
            self._hide_drag_placeholder()
            return
        placement = next(
            (item for item in self.session.working_workspace.placements if item.placement_id == placement_id),
            None,
        )
        if placement is None or self.width() <= 110:
            self._hide_drag_placeholder()
            return
        geometry = GridGeometry(self.width(), self.session.working_workspace.layout)
        rect = geometry.placement_rect(placement)
        self._drag_placeholder.setGeometry(rect.x, rect.y, rect.width, rect.height)
        self._drag_placeholder.show()
        self._drag_placeholder.raise_()

    def _hide_drag_placeholder(self) -> None:
        self._drag_placeholder.hide()

    def _scroll_area(self) -> QScrollArea | None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def _auto_scroll_drag(self, point: QPointF) -> None:
        if self.session.interaction_mode != InteractionMode.DRAGGING:
            return
        scroll = self._scroll_area()
        if scroll is None:
            return
        viewport = scroll.viewport()
        viewport_point = viewport.mapFromGlobal(point.toPoint())
        delta = auto_scroll_delta(viewport_point.y(), viewport.height())
        if delta == 0:
            return
        bar = scroll.verticalScrollBar()
        bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() + delta)))

    def _apply_workspace_geometry(self) -> None:
        if self.width() <= 110:
            return
        workspace = self.session.working_workspace
        try:
            geometry = GridGeometry(self.width(), workspace.layout)
        except ValueError:
            return
        active_ids = {placement.placement_id for placement in workspace.placements}
        max_bottom = 0
        for placement in workspace.placements:
            rect = geometry.placement_rect(placement)
            max_bottom = max(max_bottom, rect.y + rect.height)
            frame = self._frames.get(placement.placement_id)
            if frame is None:
                continue
            frame.setGeometry(rect.x, rect.y, rect.width, rect.height)
            frame.set_edit_mode(self._edit_mode)
            frame.show()
            frame.raise_()
        for placement_id, frame in self._frames.items():
            if placement_id not in active_ids:
                frame.hide()
        target_height = max(160, max_bottom)
        if self.minimumHeight() != target_height:
            self.setMinimumHeight(target_height)
        if self._drag_placeholder.isVisible():
            self._drag_placeholder.raise_()
        self.updateGeometry()
        self.update()

    def _notify_history_changed(self) -> None:
        if self._history_changed is not None:
            self._history_changed()

    def _emit_quick_action(
        self,
        placement_id: str,
        action_id: DashboardQuickAction,
    ) -> None:
        if self._edit_mode or self._quick_action_callback is None:
            return
        self._quick_action_callback(placement_id, action_id)


__all__ = [
    "DashboardCanvas",
    "DashboardCardFrame",
    "DashboardQuickAction",
    "auto_scroll_delta",
]
