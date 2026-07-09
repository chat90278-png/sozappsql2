from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class AnalysisEntity(str, Enum):
    CONTRACT = "contract"
    PLATFORM = "platform"
    ACCEPTANCE = "acceptance"
    DEADLINE = "deadline"
    SYSTEM = "system"
    COMPONENT = "component"
    USER = "user"
    TAG = "tag"


class CardType(str, Enum):
    KPI = "kpi"
    CHART = "chart"
    TABLE = "table"
    LIST = "list"
    STATUS = "status"


class ChartType(str, Enum):
    NONE = "none"
    BAR = "bar"
    HORIZONTAL_BAR = "horizontal_bar"
    DONUT = "donut"
    LINE = "line"


class CardSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    WIDE = "wide"


class ResizePolicy(str, Enum):
    FREE = "free"
    FIXED_HEIGHT = "fixed_height"
    FIXED_WIDTH = "fixed_width"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class CardLayoutHints:
    min_w: int = 1
    min_h: int = 1
    default_w: int = 6
    default_h: int = 3
    resize_policy: ResizePolicy = ResizePolicy.FREE
    max_w: int | None = None
    max_h: int | None = None

    def __post_init__(self) -> None:
        values = (self.min_w, self.min_h, self.default_w, self.default_h)
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values):
            raise ValueError("Kart layout ölçüleri pozitif tam sayı olmalıdır.")
        if self.max_w is not None and self.max_w < self.min_w:
            raise ValueError("max_w min_w değerinden küçük olamaz.")
        if self.max_h is not None and self.max_h < self.min_h:
            raise ValueError("max_h min_h değerinden küçük olamaz.")
        if self.default_w < self.min_w or (self.max_w is not None and self.default_w > self.max_w):
            raise ValueError("default_w kart genişlik sınırları içinde olmalıdır.")
        if self.default_h < self.min_h or (self.max_h is not None and self.default_h > self.max_h):
            raise ValueError("default_h kart yükseklik sınırları içinde olmalıdır.")

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "min_w": self.min_w,
            "min_h": self.min_h,
            "default_w": self.default_w,
            "default_h": self.default_h,
            "resize_policy": self.resize_policy.value,
        }
        if self.max_w is not None:
            payload["max_w"] = self.max_w
        if self.max_h is not None:
            payload["max_h"] = self.max_h
        return payload


_FALLBACK_LAYOUT_HINTS = CardLayoutHints()


def default_card_layout_hints(card_type: CardType, chart_type: ChartType = ChartType.NONE) -> CardLayoutHints:
    if card_type == CardType.KPI:
        return CardLayoutHints(
            min_w=2,
            min_h=2,
            default_w=3,
            default_h=2,
            resize_policy=ResizePolicy.FIXED_HEIGHT,
        )
    if card_type == CardType.TABLE:
        return CardLayoutHints(min_w=6, min_h=4, default_w=12, default_h=5)
    if card_type == CardType.CHART and chart_type == ChartType.DONUT:
        return CardLayoutHints(min_w=3, min_h=3, default_w=4, default_h=4)
    if card_type == CardType.CHART:
        return CardLayoutHints(min_w=4, min_h=3, default_w=6, default_h=4)
    if card_type in {CardType.LIST, CardType.STATUS}:
        return CardLayoutHints(min_w=3, min_h=2, default_w=6, default_h=3)
    return _FALLBACK_LAYOUT_HINTS


@dataclass(slots=True)
class VisualSettings:
    compact_mode: bool = False
    upcoming_days: int = 60
    max_table_rows: int = 100
    show_disabled_sections: bool = True
    empty_state_uses_sample: bool = True

    def normalized(self) -> "VisualSettings":
        return VisualSettings(
            compact_mode=bool(self.compact_mode),
            upcoming_days=max(1, int(self.upcoming_days or 60)),
            max_table_rows=max(1, int(self.max_table_rows or 100)),
            show_disabled_sections=bool(self.show_disabled_sections),
            empty_state_uses_sample=bool(self.empty_state_uses_sample),
        )


@dataclass(slots=True)
class AnalysisCard:
    card_id: str
    title: str
    entity: AnalysisEntity
    card_type: CardType
    size: CardSize = CardSize.MEDIUM
    chart_type: ChartType = ChartType.NONE
    value: Any = None
    unit: str = ""
    subtitle: str = ""
    columns: List[str] = field(default_factory=list)
    data: Any = field(default_factory=list)
    enabled: bool = True
    screen_id: str = ""
    sort_order: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
    layout_hints: CardLayoutHints | None = None

    def resolved_layout_hints(self) -> CardLayoutHints:
        return self.layout_hints or default_card_layout_hints(self.card_type, self.chart_type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "title": self.title,
            "entity": self.entity.value,
            "card_type": self.card_type.value,
            "size": self.size.value,
            "chart_type": self.chart_type.value,
            "value": self.value,
            "unit": self.unit,
            "subtitle": self.subtitle,
            "columns": list(self.columns),
            "data": self.data,
            "enabled": self.enabled,
            "screen_id": self.screen_id,
            "sort_order": self.sort_order,
            "meta": dict(self.meta),
            "layout_hints": self.resolved_layout_hints().to_dict(),
        }


@dataclass(slots=True)
class DashboardItem:
    item_id: str
    title: str
    cards: List[AnalysisCard] = field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0
    description: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "description": self.description,
            "cards": [card.to_dict() for card in sorted(self.cards, key=lambda c: c.sort_order)],
            "meta": dict(self.meta),
        }


NormalizedAnalysisData = Dict[str, List[Dict[str, Any]]]
