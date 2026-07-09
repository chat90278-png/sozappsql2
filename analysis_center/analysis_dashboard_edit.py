from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .analysis_dashboard_geometry import GridGeometry
from .analysis_dashboard_layout import (
    DashboardLayoutError,
    LockedPlacementError,
    PlacementNotFoundError,
)
from .analysis_dashboard_workspace import DashboardWorkspace
from .analysis_models import CardLayoutHints, ResizePolicy


class InteractionMode(str, Enum):
    IDLE = "idle"
    DRAGGING = "dragging"
    RESIZING = "resizing"


class HistoryOperation(str, Enum):
    MOVE = "move"
    RESIZE = "resize"
    REMOVE = "remove"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class DashboardHistoryEntry:
    operation: HistoryOperation
    placement_id: str | None
    before: DashboardWorkspace
    after: DashboardWorkspace


@dataclass(slots=True)
class _Interaction:
    mode: InteractionMode
    placement_id: str
    start_mouse_x: float
    start_mouse_y: float
    viewport_width: int
    before: DashboardWorkspace
    origin_x: int
    origin_y: int
    origin_w: int
    origin_h: int
    last_candidate: tuple[int, int]


def _round_half_away_from_zero(value: float) -> int:
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def logical_grid_delta(
    delta_x: float,
    delta_y: float,
    geometry: GridGeometry,
) -> tuple[int, int]:
    """Snap a pixel delta to the nearest logical dashboard grid units."""

    return (
        _round_half_away_from_zero(float(delta_x) / geometry.column_pitch),
        _round_half_away_from_zero(float(delta_y) / geometry.row_pitch),
    )


def drag_candidate(
    *,
    origin_x: int,
    origin_y: int,
    placement_w: int,
    delta_x: float,
    delta_y: float,
    geometry: GridGeometry,
) -> tuple[int, int]:
    dx, dy = logical_grid_delta(delta_x, delta_y, geometry)
    max_x = max(0, geometry.layout.columns - placement_w)
    return max(0, min(max_x, origin_x + dx)), max(0, origin_y + dy)


def resize_axes(policy: ResizePolicy) -> tuple[bool, bool]:
    if policy == ResizePolicy.NONE:
        return False, False
    if policy in {ResizePolicy.FIXED_HEIGHT, ResizePolicy.HORIZONTAL}:
        return True, False
    if policy in {ResizePolicy.FIXED_WIDTH, ResizePolicy.VERTICAL}:
        return False, True
    return True, True


def resize_candidate(
    *,
    origin_w: int,
    origin_h: int,
    placement_x: int,
    delta_x: float,
    delta_y: float,
    geometry: GridGeometry,
    hints: CardLayoutHints,
) -> tuple[int, int]:
    dw, dh = logical_grid_delta(delta_x, delta_y, geometry)
    allow_w, allow_h = resize_axes(hints.resize_policy)

    width = origin_w + dw if allow_w else origin_w
    height = origin_h + dh if allow_h else origin_h
    max_width = geometry.layout.columns - placement_x
    width = max(hints.min_w, min(max_width, width))
    height = max(hints.min_h, height)
    if hints.max_w is not None:
        width = min(width, hints.max_w)
    if hints.max_h is not None:
        height = min(height, hints.max_h)
    return width, height


class DashboardEditSession:
    """In-memory working layout, live preview and edit-session history controller."""

    def __init__(self, saved_workspace: DashboardWorkspace):
        saved_workspace.validate()
        self.saved_workspace = saved_workspace.working_copy()
        self.working_workspace = saved_workspace.working_copy()
        self._undo_stack: list[DashboardHistoryEntry] = []
        self._redo_stack: list[DashboardHistoryEntry] = []
        self._interaction: _Interaction | None = None

    @property
    def interaction_mode(self) -> InteractionMode:
        return self._interaction.mode if self._interaction is not None else InteractionMode.IDLE

    @property
    def active_placement_id(self) -> str | None:
        return self._interaction.placement_id if self._interaction is not None else None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_depth(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_depth(self) -> int:
        return len(self._redo_stack)

    def begin_drag(
        self,
        placement_id: str,
        *,
        mouse_x: float,
        mouse_y: float,
        viewport_width: int,
    ) -> None:
        self._ensure_idle()
        placement = self._placement(placement_id)
        if placement.locked:
            raise LockedPlacementError(f"Locked placement taşınamaz: {placement_id}")
        self._interaction = _Interaction(
            mode=InteractionMode.DRAGGING,
            placement_id=placement_id,
            start_mouse_x=float(mouse_x),
            start_mouse_y=float(mouse_y),
            viewport_width=int(viewport_width),
            before=self.working_workspace.working_copy(),
            origin_x=placement.x,
            origin_y=placement.y,
            origin_w=placement.w,
            origin_h=placement.h,
            last_candidate=(placement.x, placement.y),
        )

    def preview_drag(self, *, mouse_x: float, mouse_y: float) -> bool:
        interaction = self._require_interaction(InteractionMode.DRAGGING)
        geometry = GridGeometry(interaction.viewport_width, interaction.before.layout)
        candidate = drag_candidate(
            origin_x=interaction.origin_x,
            origin_y=interaction.origin_y,
            placement_w=interaction.origin_w,
            delta_x=float(mouse_x) - interaction.start_mouse_x,
            delta_y=float(mouse_y) - interaction.start_mouse_y,
            geometry=geometry,
        )
        if candidate == interaction.last_candidate:
            return False
        try:
            result = interaction.before.engine.move(
                interaction.before.placements,
                placement_id=interaction.placement_id,
                x=candidate[0],
                y=candidate[1],
                hints_by_placement=interaction.before.layout_hints_by_placement,
            )
        except DashboardLayoutError:
            return False
        interaction.last_candidate = candidate
        self.working_workspace.apply_placements(result)
        return True

    def begin_resize(
        self,
        placement_id: str,
        *,
        mouse_x: float,
        mouse_y: float,
        viewport_width: int,
    ) -> None:
        self._ensure_idle()
        placement = self._placement(placement_id)
        if placement.locked:
            raise LockedPlacementError(f"Locked placement resize edilemez: {placement_id}")
        hints = self.working_workspace.layout_hints_for(placement_id)
        if hints.resize_policy == ResizePolicy.NONE:
            raise DashboardLayoutError(f"Placement resize kapalı: {placement_id}")
        self._interaction = _Interaction(
            mode=InteractionMode.RESIZING,
            placement_id=placement_id,
            start_mouse_x=float(mouse_x),
            start_mouse_y=float(mouse_y),
            viewport_width=int(viewport_width),
            before=self.working_workspace.working_copy(),
            origin_x=placement.x,
            origin_y=placement.y,
            origin_w=placement.w,
            origin_h=placement.h,
            last_candidate=(placement.w, placement.h),
        )

    def preview_resize(self, *, mouse_x: float, mouse_y: float) -> bool:
        interaction = self._require_interaction(InteractionMode.RESIZING)
        geometry = GridGeometry(interaction.viewport_width, interaction.before.layout)
        hints = interaction.before.layout_hints_for(interaction.placement_id)
        candidate = resize_candidate(
            origin_w=interaction.origin_w,
            origin_h=interaction.origin_h,
            placement_x=interaction.origin_x,
            delta_x=float(mouse_x) - interaction.start_mouse_x,
            delta_y=float(mouse_y) - interaction.start_mouse_y,
            geometry=geometry,
            hints=hints,
        )
        if candidate == interaction.last_candidate:
            return False
        try:
            result = interaction.before.engine.resize(
                interaction.before.placements,
                placement_id=interaction.placement_id,
                w=candidate[0],
                h=candidate[1],
                hints_by_placement=interaction.before.layout_hints_by_placement,
            )
        except DashboardLayoutError:
            return False
        interaction.last_candidate = candidate
        self.working_workspace.apply_placements(result)
        return True

    def finish_interaction(self) -> bool:
        interaction = self._interaction
        if interaction is None:
            return False
        operation = (
            HistoryOperation.MOVE
            if interaction.mode == InteractionMode.DRAGGING
            else HistoryOperation.RESIZE
        )
        self._interaction = None
        return self._record_change(operation, interaction.placement_id, interaction.before)

    def cancel_interaction(self) -> bool:
        if self._interaction is None:
            return False
        self.working_workspace = self._interaction.before.working_copy()
        self._interaction = None
        return True

    def remove_placement(self, placement_id: str) -> bool:
        self.cancel_interaction()
        before = self.working_workspace.working_copy()
        try:
            self.working_workspace.remove_placement(placement_id)
        except DashboardLayoutError:
            return False
        return self._record_change(HistoryOperation.REMOVE, placement_id, before)

    def reset_layout(self) -> bool:
        self.cancel_interaction()
        before = self.working_workspace.working_copy()
        self.working_workspace.reset_layout()
        return self._record_change(HistoryOperation.RESET, None, before)

    def undo(self) -> bool:
        self.cancel_interaction()
        if not self._undo_stack:
            return False
        entry = self._undo_stack.pop()
        self.working_workspace = entry.before.working_copy()
        self._redo_stack.append(entry)
        return True

    def redo(self) -> bool:
        self.cancel_interaction()
        if not self._redo_stack:
            return False
        entry = self._redo_stack.pop()
        self.working_workspace = entry.after.working_copy()
        self._undo_stack.append(entry)
        return True

    def discard(self) -> DashboardWorkspace:
        self.cancel_interaction()
        self.working_workspace = self.saved_workspace.working_copy()
        self.clear_history()
        return self.working_workspace.working_copy()

    def mark_saved(self) -> DashboardWorkspace:
        self.cancel_interaction()
        self.working_workspace.validate()
        self.saved_workspace = self.working_workspace.working_copy()
        self.clear_history()
        return self.saved_workspace.working_copy()

    def clear_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _record_change(
        self,
        operation: HistoryOperation,
        placement_id: str | None,
        before: DashboardWorkspace,
    ) -> bool:
        if self._layout_signature(before) == self._layout_signature(self.working_workspace):
            return False
        self._undo_stack.append(
            DashboardHistoryEntry(
                operation=operation,
                placement_id=placement_id,
                before=before.working_copy(),
                after=self.working_workspace.working_copy(),
            )
        )
        self._redo_stack.clear()
        return True

    def _placement(self, placement_id: str):
        for placement in self.working_workspace.placements:
            if placement.placement_id == placement_id:
                return placement
        raise PlacementNotFoundError(f"Placement bulunamadı: {placement_id}")

    def _ensure_idle(self) -> None:
        if self._interaction is not None:
            raise DashboardLayoutError("Başka bir Dashboard interaction zaten aktif.")

    def _require_interaction(self, mode: InteractionMode) -> _Interaction:
        if self._interaction is None or self._interaction.mode != mode:
            raise DashboardLayoutError(f"Aktif Dashboard interaction bekleniyor: {mode.value}")
        return self._interaction

    @staticmethod
    def _layout_signature(workspace: DashboardWorkspace) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                placement.placement_id,
                placement.source_screen_id,
                placement.card_id,
                placement.x,
                placement.y,
                placement.w,
                placement.h,
                placement.locked,
                repr(sorted(placement.settings.items())),
            )
            for placement in workspace.placements
        )
