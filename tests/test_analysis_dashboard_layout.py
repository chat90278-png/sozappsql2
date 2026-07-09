from __future__ import annotations

import json
import random

import pytest

from analysis_center.analysis_dashboard_layout import (
    DashboardCardPlacement,
    DashboardLayoutEngine,
    DashboardLayoutSettings,
    LayoutValidationError,
    LockedPlacementError,
    ResizePolicyError,
    placements_overlap,
)
from analysis_center.analysis_models import CardLayoutHints, ResizePolicy


def placement(
    placement_id: str,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    locked: bool = False,
) -> DashboardCardPlacement:
    return DashboardCardPlacement(
        placement_id=placement_id,
        source_screen_id="screen",
        card_id=placement_id,
        x=x,
        y=y,
        w=w,
        h=h,
        locked=locked,
    )


def by_id(layout, placement_id):
    return next(item for item in layout if item.placement_id == placement_id)


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (placement("a", -1, 0, 2, 2), "x negatif"),
        (placement("a", 0, -1, 2, 2), "y negatif"),
        (placement("a", 0, 0, 0, 2), "genişliği pozitif"),
        (placement("a", 0, 0, 2, 0), "yüksekliği pozitif"),
        (placement("a", 11, 0, 2, 2), "kolon sınırını"),
    ],
)
def test_placement_validation_rejects_invalid_geometry(item, message):
    with pytest.raises(LayoutValidationError, match=message):
        DashboardLayoutEngine().validate([item])


def test_placement_validation_applies_min_width_and_height_constraints():
    engine = DashboardLayoutEngine()
    hints = {"a": CardLayoutHints(min_w=3, min_h=4, default_w=3, default_h=4)}

    with pytest.raises(LayoutValidationError, match="min_w"):
        engine.validate([placement("a", 0, 0, 2, 4)], hints)
    with pytest.raises(LayoutValidationError, match="min_h"):
        engine.validate([placement("a", 0, 0, 3, 3)], hints)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (placement("a", 0, 0, 3, 2), placement("b", 2, 1, 4, 3), True),
        (placement("a", 0, 0, 6, 5), placement("b", 1, 1, 2, 2), True),
        (placement("a", 0, 0, 3, 3), placement("b", 2, 2, 3, 3), True),
        (placement("a", 0, 0, 3, 2), placement("b", 3, 0, 2, 2), False),
        (placement("a", 0, 0, 3, 2), placement("b", 0, 2, 3, 2), False),
        (placement("a", 0, 0, 3, 2), placement("b", 3, 2, 3, 2), False),
    ],
)
def test_collision_detection_handles_overlap_and_touching_edges(a, b, expected):
    assert placements_overlap(a, b) is expected
    assert placements_overlap(b, a) is expected


def test_validate_rejects_overlap():
    engine = DashboardLayoutEngine()
    with pytest.raises(LayoutValidationError, match="overlap"):
        engine.validate([placement("a", 0, 0, 3, 2), placement("b", 2, 1, 4, 3)])


def test_move_to_empty_area_preserves_other_cards():
    engine = DashboardLayoutEngine()
    layout = [placement("a", 0, 0, 3, 2), placement("b", 6, 0, 3, 2)]

    result = engine.move(layout, placement_id="a", x=3, y=3, compact=False)

    assert (by_id(result, "a").x, by_id(result, "a").y) == (3, 3)
    assert (by_id(result, "b").x, by_id(result, "b").y) == (6, 0)
    engine.validate(result)


def test_move_into_one_card_pushes_collision_down():
    engine = DashboardLayoutEngine()
    layout = [placement("a", 0, 0, 3, 2), placement("b", 3, 0, 3, 2)]

    result = engine.move(layout, placement_id="a", x=3, y=0, compact=False)

    assert by_id(result, "a").y == 0
    assert by_id(result, "b").y == 2
    engine.validate(result)


def test_move_into_multiple_cards_pushes_all_deterministically():
    engine = DashboardLayoutEngine()
    layout = [
        placement("a", 8, 6, 4, 3),
        placement("b", 0, 0, 3, 2),
        placement("c", 3, 0, 3, 4),
    ]

    result = engine.move(layout, placement_id="a", x=0, y=0, compact=False)

    assert by_id(result, "a").y == 0
    assert by_id(result, "b").y == 3
    assert by_id(result, "c").y == 3
    engine.validate(result)


def test_move_near_grid_boundary_clamps_x():
    result = DashboardLayoutEngine().move(
        [placement("a", 0, 0, 4, 2)],
        placement_id="a",
        x=99,
        y=0,
        compact=False,
    )
    assert by_id(result, "a").x == 8


def test_move_locked_card_is_rejected():
    with pytest.raises(LockedPlacementError):
        DashboardLayoutEngine().move(
            [placement("a", 0, 0, 3, 2, locked=True)],
            placement_id="a",
            x=3,
            y=0,
        )


def test_moving_card_into_locked_card_moves_active_below_barrier():
    engine = DashboardLayoutEngine()
    layout = [placement("locked", 0, 0, 6, 3, locked=True), placement("a", 6, 0, 3, 2)]

    result = engine.move(layout, placement_id="a", x=0, y=0, compact=False)

    assert by_id(result, "locked").y == 0
    assert by_id(result, "a").y == 3
    engine.validate(result)


def test_resize_grow_without_collision_and_shrink():
    engine = DashboardLayoutEngine()
    layout = [placement("a", 0, 0, 3, 3)]

    grown = engine.resize(layout, placement_id="a", w=6, h=4, compact=False)
    shrunk = engine.resize(grown, placement_id="a", w=2, h=2, compact=False)

    assert (by_id(grown, "a").w, by_id(grown, "a").h) == (6, 4)
    assert (by_id(shrunk, "a").w, by_id(shrunk, "a").h) == (2, 2)


def test_resize_grow_into_card_pushes_card_down():
    engine = DashboardLayoutEngine()
    layout = [placement("a", 0, 0, 3, 2), placement("b", 3, 0, 3, 3)]

    result = engine.resize(layout, placement_id="a", w=6, h=4, compact=False)

    assert by_id(result, "b").y == 4
    engine.validate(result)


def test_resize_min_constraint_is_rejected():
    engine = DashboardLayoutEngine()
    hints = {"a": CardLayoutHints(min_w=3, min_h=2, default_w=3, default_h=2)}
    with pytest.raises(LayoutValidationError, match="min_w"):
        engine.resize(
            [placement("a", 0, 0, 3, 2)],
            placement_id="a",
            w=2,
            h=2,
            hints_by_placement=hints,
        )


@pytest.mark.parametrize(
    ("policy", "w", "h"),
    [
        (ResizePolicy.FIXED_HEIGHT, 4, 3),
        (ResizePolicy.FIXED_WIDTH, 4, 2),
        (ResizePolicy.HORIZONTAL, 4, 3),
        (ResizePolicy.VERTICAL, 4, 2),
        (ResizePolicy.NONE, 4, 2),
    ],
)
def test_resize_policy_rejects_disallowed_dimension_changes(policy, w, h):
    hints = {"a": CardLayoutHints(min_w=1, min_h=1, default_w=3, default_h=2, resize_policy=policy)}
    with pytest.raises(ResizePolicyError):
        DashboardLayoutEngine().resize(
            [placement("a", 0, 0, 3, 2)],
            placement_id="a",
            w=w,
            h=h,
            hints_by_placement=hints,
        )


def test_resize_locked_card_is_rejected():
    with pytest.raises(LockedPlacementError):
        DashboardLayoutEngine().resize(
            [placement("a", 0, 0, 3, 2, locked=True)],
            placement_id="a",
            w=6,
            h=2,
        )


def test_single_push_and_chain_push_support_different_heights():
    engine = DashboardLayoutEngine()
    layout = [
        placement("a", 9, 10, 3, 2),
        placement("b", 0, 0, 6, 4),
        placement("c", 0, 4, 3, 2),
        placement("d", 0, 6, 12, 5),
    ]

    result = engine.move(layout, placement_id="a", x=0, y=0, compact=False)

    assert by_id(result, "b").y == 2
    assert by_id(result, "c").y == 6
    assert by_id(result, "d").y == 8
    engine.validate(result)


def test_multiple_collision_chain_with_different_widths_remains_valid():
    engine = DashboardLayoutEngine()
    layout = [
        placement("a", 8, 12, 4, 4),
        placement("b", 0, 0, 6, 4),
        placement("c", 4, 3, 3, 2),
        placement("d", 0, 5, 12, 5),
        placement("e", 8, 10, 4, 3),
    ]

    result = engine.move(layout, placement_id="a", x=2, y=1, compact=False)

    engine.validate(result)
    assert by_id(result, "b").y > 0
    assert by_id(result, "d").y >= by_id(result, "c").y + by_id(result, "c").h


def test_vertical_compact_closes_simple_gap():
    engine = DashboardLayoutEngine()
    result = engine.compact([placement("a", 0, 0, 3, 2), placement("b", 0, 8, 3, 2)])
    assert by_id(result, "b").y == 2


def test_vertical_compact_respects_blocking_card():
    engine = DashboardLayoutEngine()
    layout = [
        placement("a", 0, 0, 3, 2),
        placement("block", 0, 2, 3, 4),
        placement("b", 0, 10, 3, 2),
    ]
    result = engine.compact(layout)
    assert by_id(result, "b").y == 6


def test_vertical_compact_handles_multiple_cards_in_same_x_range():
    engine = DashboardLayoutEngine()
    layout = [
        placement("a", 0, 0, 6, 2),
        placement("b", 2, 7, 4, 3),
        placement("c", 1, 12, 2, 2),
    ]
    result = engine.compact(layout)
    assert by_id(result, "b").y == 2
    assert by_id(result, "c").y == 5
    engine.validate(result)


def test_vertical_compact_preserves_horizontal_position():
    result = DashboardLayoutEngine().compact([placement("a", 8, 9, 3, 2)])
    assert (by_id(result, "a").x, by_id(result, "a").y) == (8, 0)


def test_vertical_compact_does_not_move_locked_card():
    result = DashboardLayoutEngine().compact([placement("a", 0, 8, 3, 2, locked=True)])
    assert by_id(result, "a").y == 8


def test_same_layout_and_operation_are_byte_for_byte_deterministic():
    engine = DashboardLayoutEngine()
    initial = [
        placement("c", 3, 0, 3, 2),
        placement("a", 9, 8, 3, 4),
        placement("b", 0, 0, 3, 3),
        placement("d", 0, 3, 12, 5),
    ]

    serialized = []
    for _ in range(30):
        result = engine.move(initial, placement_id="a", x=0, y=0)
        serialized.append(json.dumps([item.to_dict() for item in result], sort_keys=True))

    assert len(set(serialized)) == 1


def test_randomized_layout_stress_is_reproducible_and_always_valid():
    engine = DashboardLayoutEngine(DashboardLayoutSettings(columns=12))
    for seed in range(40):
        rng = random.Random(seed)
        layout: list[DashboardCardPlacement] = []
        hints: dict[str, CardLayoutHints] = {}
        next_id = 1
        try:
            for _ in range(80):
                operations = ["compact"]
                if len(layout) < 15:
                    operations.append("add")
                if layout:
                    operations.extend(["move", "resize", "remove"])
                operation = rng.choice(operations)

                if operation == "add":
                    placement_id = f"p-{next_id}"
                    next_id += 1
                    hint = CardLayoutHints(min_w=1, min_h=1, default_w=3, default_h=2)
                    item = placement(
                        placement_id,
                        rng.randrange(0, 12),
                        rng.randrange(0, 20),
                        rng.randint(1, 6),
                        rng.randint(1, 5),
                    )
                    hints[placement_id] = hint
                    layout = engine.add(layout, item, hints_by_placement=hints)
                elif operation == "move":
                    item = rng.choice(layout)
                    layout = engine.move(
                        layout,
                        placement_id=item.placement_id,
                        x=rng.randrange(-3, 18),
                        y=rng.randrange(-3, 25),
                        hints_by_placement=hints,
                    )
                elif operation == "resize":
                    item = rng.choice(layout)
                    layout = engine.resize(
                        layout,
                        placement_id=item.placement_id,
                        w=rng.randint(1, 12),
                        h=rng.randint(1, 6),
                        hints_by_placement=hints,
                    )
                elif operation == "remove":
                    item = rng.choice(layout)
                    layout = engine.remove(
                        layout,
                        placement_id=item.placement_id,
                        hints_by_placement={key: value for key, value in hints.items() if key != item.placement_id},
                    )
                    hints.pop(item.placement_id)
                else:
                    layout = engine.compact(layout, hints_by_placement=hints)

                engine.validate(layout, hints)
                assert len({item.placement_id for item in layout}) == len(layout)
        except Exception as exc:
            pytest.fail(f"Layout stress test failed with seed={seed}: {exc!r}")
