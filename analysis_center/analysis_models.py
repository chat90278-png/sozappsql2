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
    HEALTH = "health"


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
