from __future__ import annotations

import pytest

from analysis_center.analysis_dashboard_geometry import GridGeometry, PixelRect
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement, DashboardLayoutSettings


def placement() -> DashboardCardPlacement:
    return DashboardCardPlacement("card-1", "screen", "card", 3, 2, 6, 4)


@pytest.mark.parametrize("viewport_width", [1366, 1920, 2560])
def test_grid_geometry_changes_pixels_without_mutating_logical_layout(viewport_width):
    item = placement()
    before = item.to_dict()

    rect = GridGeometry(viewport_width, DashboardLayoutSettings()).placement_rect(item)

    assert isinstance(rect, PixelRect)
    assert rect.x >= 0
    assert rect.y > 0
    assert rect.width > 0
    assert rect.height > 0
    assert item.to_dict() == before


def test_grid_geometry_exact_vertical_units_and_gap():
    layout = DashboardLayoutSettings(columns=12, row_height=54, gap=10)
    item = DashboardCardPlacement("a", "screen", "card", 0, 2, 3, 4)

    rect = GridGeometry(1200, layout).placement_rect(item)

    assert rect.y == 2 * (54 + 10)
    assert rect.height == 4 * 54 + 3 * 10


def test_grid_geometry_preserves_column_boundaries_for_full_width_card():
    layout = DashboardLayoutSettings(columns=12, row_height=54, gap=10)
    item = DashboardCardPlacement("a", "screen", "card", 0, 0, 12, 2)

    rect = GridGeometry(1920, layout).placement_rect(item)

    assert rect == PixelRect(x=0, y=0, width=1920, height=118)


def test_grid_geometry_rejects_viewport_too_small_for_grid_gaps():
    with pytest.raises(ValueError, match="yetersiz"):
        GridGeometry(100, DashboardLayoutSettings(columns=12, gap=10))
