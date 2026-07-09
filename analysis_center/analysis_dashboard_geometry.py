from __future__ import annotations

from dataclasses import dataclass

from .analysis_dashboard_layout import DashboardCardPlacement, DashboardLayoutSettings


@dataclass(frozen=True, slots=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int


class GridGeometry:
    """Convert logical dashboard grid units to pixel rectangles without Qt."""

    def __init__(
        self,
        viewport_width: int,
        layout: DashboardLayoutSettings | None = None,
        *,
        origin_x: int = 0,
        origin_y: int = 0,
    ):
        self.viewport_width = int(viewport_width)
        self.layout = layout or DashboardLayoutSettings()
        self.origin_x = int(origin_x)
        self.origin_y = int(origin_y)
        usable_width = self.viewport_width - (self.layout.columns - 1) * self.layout.gap
        if self.viewport_width <= 0 or usable_width <= 0:
            raise ValueError("Viewport genişliği dashboard grid için yetersiz.")
        self._column_width = usable_width / self.layout.columns

    @property
    def column_width(self) -> float:
        return self._column_width

    @property
    def column_pitch(self) -> float:
        return self._column_width + self.layout.gap

    @property
    def row_pitch(self) -> int:
        return self.layout.row_height + self.layout.gap

    def placement_rect(self, placement: DashboardCardPlacement) -> PixelRect:
        x = self.origin_x + round(placement.x * (self._column_width + self.layout.gap))
        y = self.origin_y + placement.y * (self.layout.row_height + self.layout.gap)
        width = round(placement.w * self._column_width + (placement.w - 1) * self.layout.gap)
        height = placement.h * self.layout.row_height + (placement.h - 1) * self.layout.gap
        return PixelRect(x=x, y=y, width=width, height=height)
