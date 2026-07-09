from __future__ import annotations

import pytest

from analysis_center.analysis_dashboard_edit import (
    DashboardEditSession,
    HistoryOperation,
    InteractionMode,
    drag_candidate,
    logical_grid_delta,
    resize_axes,
    resize_candidate,
)
from analysis_center.analysis_dashboard_geometry import GridGeometry
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement, LockedPlacementError
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace
from analysis_center.analysis_models import (
    AnalysisCard,
    AnalysisEntity,
    CardLayoutHints,
    CardType,
    ResizePolicy,
)


def _card(card_id: str, *, card_type: CardType = CardType.KPI) -> AnalysisCard:
    return AnalysisCard(
        card_id=card_id,
        title=card_id,
        entity=AnalysisEntity.CONTRACT,
        card_type=card_type,
        screen_id="screen",
    )


def _workspace() -> DashboardWorkspace:
    workspace = DashboardWorkspace(source_key="test")
    workspace.pin(_card("a"))
    workspace.pin(_card("b"))
    return workspace


def _placement(workspace: DashboardWorkspace, card_id: str):
    return next(item for item in workspace.placements if item.card_id == card_id)


def test_edit_session_creates_independent_working_copy_and_saved_state_stays_unchanged():
    saved = _workspace()
    session = DashboardEditSession(saved)
    placement_id = _placement(session.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, saved.layout)

    session.begin_drag(placement_id, mouse_x=100, mouse_y=100, viewport_width=1200)
    assert session.preview_drag(mouse_x=100 + geometry.column_pitch * 4, mouse_y=100) is True
    session.finish_interaction()

    assert _placement(saved, "a").x == 0
    assert _placement(session.saved_workspace, "a").x == 0
    assert _placement(session.working_workspace, "a").x == 4


def test_discard_restores_saved_layout_and_clears_history():
    session = DashboardEditSession(_workspace())
    placement_id = _placement(session.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, session.working_workspace.layout)
    session.begin_drag(placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)
    session.preview_drag(mouse_x=geometry.column_pitch * 5, mouse_y=geometry.row_pitch * 3)
    session.finish_interaction()
    assert session.can_undo is True

    restored = session.discard()

    assert _placement(restored, "a").x == 0
    assert session.can_undo is False
    assert session.can_redo is False
    assert session.interaction_mode == InteractionMode.IDLE


def test_mark_saved_promotes_working_layout_and_clears_history():
    session = DashboardEditSession(_workspace())
    placement_id = _placement(session.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, session.working_workspace.layout)
    session.begin_drag(placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)
    session.preview_drag(mouse_x=geometry.column_pitch * 6, mouse_y=0)
    session.finish_interaction()

    saved = session.mark_saved()

    assert _placement(saved, "a").x == 6
    assert _placement(session.saved_workspace, "a").x == 6
    assert session.can_undo is False
    assert session.can_redo is False


def test_pixel_delta_snaps_to_nearest_logical_grid_unit():
    geometry = GridGeometry(1200)
    assert logical_grid_delta(geometry.column_pitch * 0.49, geometry.row_pitch * 0.49, geometry) == (0, 0)
    assert logical_grid_delta(geometry.column_pitch * 0.51, geometry.row_pitch * 0.51, geometry) == (1, 1)
    assert logical_grid_delta(-geometry.column_pitch * 0.51, -geometry.row_pitch * 0.51, geometry) == (-1, -1)


def test_drag_candidate_clamps_left_and_right_boundaries():
    geometry = GridGeometry(1200)
    assert drag_candidate(
        origin_x=2,
        origin_y=3,
        placement_w=3,
        delta_x=-9999,
        delta_y=-9999,
        geometry=geometry,
    ) == (0, 0)
    assert drag_candidate(
        origin_x=2,
        origin_y=3,
        placement_w=3,
        delta_x=9999,
        delta_y=0,
        geometry=geometry,
    ) == (9, 3)


def test_drag_anchor_press_point_is_preserved_and_does_not_jump_on_press():
    session = DashboardEditSession(_workspace())
    placement = _placement(session.working_workspace, "a")
    before = (placement.x, placement.y, placement.w, placement.h)

    session.begin_drag(
        placement.placement_id,
        mouse_x=437.25,
        mouse_y=219.75,
        viewport_width=1200,
    )

    assert session.preview_drag(mouse_x=437.25, mouse_y=219.75) is False
    current = _placement(session.working_workspace, "a")
    assert (current.x, current.y, current.w, current.h) == before


def test_drag_candidate_depends_on_pointer_delta_not_absolute_press_anchor():
    first = DashboardEditSession(_workspace())
    second = DashboardEditSession(_workspace())
    first_id = _placement(first.working_workspace, "a").placement_id
    second_id = _placement(second.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, first.working_workspace.layout)
    delta_x = geometry.column_pitch * 3.1
    delta_y = geometry.row_pitch * 1.2

    first.begin_drag(first_id, mouse_x=10, mouse_y=12, viewport_width=1200)
    second.begin_drag(second_id, mouse_x=733, mouse_y=411, viewport_width=1200)
    assert first.preview_drag(mouse_x=10 + delta_x, mouse_y=12 + delta_y) is True
    assert second.preview_drag(mouse_x=733 + delta_x, mouse_y=411 + delta_y) is True

    first_placement = _placement(first.working_workspace, "a")
    second_placement = _placement(second.working_workspace, "a")
    assert (first_placement.x, first_placement.y) == (second_placement.x, second_placement.y)


def test_same_drag_candidate_does_not_reapply_preview_operation():
    session = DashboardEditSession(_workspace())
    placement_id = _placement(session.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, session.working_workspace.layout)
    session.begin_drag(placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)

    assert session.preview_drag(mouse_x=geometry.column_pitch * 2, mouse_y=0) is True
    snapshot = [(item.placement_id, item.x, item.y) for item in session.working_workspace.placements]
    assert session.preview_drag(mouse_x=geometry.column_pitch * 2 + 1, mouse_y=1) is False
    assert [(item.placement_id, item.x, item.y) for item in session.working_workspace.placements] == snapshot


def test_one_drag_session_is_one_undo_step_even_with_many_previews():
    session = DashboardEditSession(_workspace())
    placement_id = _placement(session.working_workspace, "a").placement_id
    geometry = GridGeometry(1200, session.working_workspace.layout)
    session.begin_drag(placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)
    for column in range(1, 7):
        session.preview_drag(mouse_x=geometry.column_pitch * column, mouse_y=0)

    assert session.undo_depth == 0
    assert session.finish_interaction() is True
    assert session.undo_depth == 1
    assert session._undo_stack[-1].operation == HistoryOperation.MOVE


def test_resize_candidate_respects_minimum_and_policy_axes():
    geometry = GridGeometry(1200)
    fixed_height = CardLayoutHints(
        min_w=2,
        min_h=2,
        default_w=3,
        default_h=2,
        resize_policy=ResizePolicy.FIXED_HEIGHT,
    )
    assert resize_candidate(
        origin_w=3,
        origin_h=2,
        placement_x=0,
        delta_x=-9999,
        delta_y=9999,
        geometry=geometry,
        hints=fixed_height,
    ) == (2, 2)

    fixed_width = CardLayoutHints(
        min_w=3,
        min_h=2,
        default_w=3,
        default_h=2,
        resize_policy=ResizePolicy.FIXED_WIDTH,
    )
    assert resize_candidate(
        origin_w=3,
        origin_h=2,
        placement_x=0,
        delta_x=9999,
        delta_y=geometry.row_pitch * 3,
        geometry=geometry,
        hints=fixed_width,
    ) == (3, 5)


def test_resize_axes_cover_free_horizontal_vertical_and_none_policies():
    assert resize_axes(ResizePolicy.FREE) == (True, True)
    assert resize_axes(ResizePolicy.FIXED_HEIGHT) == (True, False)
    assert resize_axes(ResizePolicy.HORIZONTAL) == (True, False)
    assert resize_axes(ResizePolicy.FIXED_WIDTH) == (False, True)
    assert resize_axes(ResizePolicy.VERTICAL) == (False, True)
    assert resize_axes(ResizePolicy.NONE) == (False, False)


def test_one_resize_session_is_one_undo_step_and_uses_engine_constraints():
    workspace = DashboardWorkspace(source_key="test")
    workspace.pin(_card("chart", card_type=CardType.CHART))
    session = DashboardEditSession(workspace)
    placement = _placement(session.working_workspace, "chart")
    geometry = GridGeometry(1200, workspace.layout)

    session.begin_resize(placement.placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)
    for units in range(1, 4):
        session.preview_resize(
            mouse_x=geometry.column_pitch * units,
            mouse_y=geometry.row_pitch * units,
        )
    session.finish_interaction()

    resized = _placement(session.working_workspace, "chart")
    assert (resized.w, resized.h) == (9, 7)
    assert session.undo_depth == 1
    assert session._undo_stack[-1].operation == HistoryOperation.RESIZE


def test_fixed_height_kpi_resize_keeps_height_unchanged():
    session = DashboardEditSession(_workspace())
    placement = _placement(session.working_workspace, "a")
    geometry = GridGeometry(1200, session.working_workspace.layout)
    session.begin_resize(placement.placement_id, mouse_x=0, mouse_y=0, viewport_width=1200)
    session.preview_resize(mouse_x=geometry.column_pitch * 3, mouse_y=geometry.row_pitch * 8)
    session.finish_interaction()

    resized = _placement(session.working_workspace, "a")
    assert resized.w == 6
    assert resized.h == 2


def test_remove_undo_redo_and_new_operation_clears_redo_stack():
    session = DashboardEditSession(_workspace())
    a_id = _placement(session.working_workspace, "a").placement_id
    b_id = _placement(session.working_workspace, "b").placement_id

    assert session.remove_placement(b_id) is True
    assert len(session.working_workspace.placements) == 1
    assert session.undo() is True
    assert len(session.working_workspace.placements) == 2
    assert session.can_redo is True
    assert session.redo() is True
    assert len(session.working_workspace.placements) == 1
    assert session.undo() is True

    assert session.remove_placement(a_id) is True
    assert session.can_redo is False


def test_reset_layout_preserves_placement_identity_and_uses_default_hints():
    workspace = DashboardWorkspace(source_key="test")
    workspace.pin(_card("kpi"))
    workspace.pin(_card("table", card_type=CardType.TABLE))
    kpi = _placement(workspace, "kpi")
    table = _placement(workspace, "table")
    workspace.move_placement(kpi.placement_id, x=8, y=8)
    workspace.resize_placement(table.placement_id, w=6, h=7)
    original_ids = {item.placement_id for item in workspace.placements}
    session = DashboardEditSession(workspace)

    assert session.reset_layout() is True
    reset = session.working_workspace

    assert {item.placement_id for item in reset.placements} == original_ids
    assert (_placement(reset, "kpi").w, _placement(reset, "kpi").h) == (3, 2)
    assert (_placement(reset, "table").w, _placement(reset, "table").h) == (12, 5)
    reset.validate()


def test_reset_then_discard_restores_pre_reset_saved_layout():
    workspace = _workspace()
    a_id = _placement(workspace, "a").placement_id
    workspace.move_placement(a_id, x=8, y=5)
    saved_signature = [(item.placement_id, item.x, item.y, item.w, item.h) for item in workspace.placements]
    session = DashboardEditSession(workspace)

    session.reset_layout()
    restored = session.discard()

    assert [(item.placement_id, item.x, item.y, item.w, item.h) for item in restored.placements] == saved_signature


def test_locked_card_cannot_begin_drag_or_resize():
    workspace = DashboardWorkspace(
        source_key="test",
        placements=[DashboardCardPlacement("locked", "screen", "locked", 0, 0, 3, 2, locked=True)],
    )
    session = DashboardEditSession(workspace)

    with pytest.raises(LockedPlacementError):
        session.begin_drag("locked", mouse_x=0, mouse_y=0, viewport_width=1200)
    with pytest.raises(LockedPlacementError):
        session.begin_resize("locked", mouse_x=0, mouse_y=0, viewport_width=1200)
    assert session.interaction_mode == InteractionMode.IDLE


def test_viewport_geometry_change_does_not_mutate_logical_working_layout():
    session = DashboardEditSession(_workspace())
    before = [(item.placement_id, item.x, item.y, item.w, item.h) for item in session.working_workspace.placements]
    placement = session.working_workspace.placements[0]

    rect_1366 = GridGeometry(1366, session.working_workspace.layout).placement_rect(placement)
    rect_1920 = GridGeometry(1920, session.working_workspace.layout).placement_rect(placement)

    assert rect_1366.width != rect_1920.width
    assert [(item.placement_id, item.x, item.y, item.w, item.h) for item in session.working_workspace.placements] == before
