from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


FILTER_OPERATORS = (
    "equals", "not_equals", "contains", "not_contains",
    "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal",
    "between", "is_empty", "is_not_empty", "in", "not_in",
)
AGGREGATIONS = ("count_rows", "count", "count_distinct", "sum", "avg", "min", "max")
SORT_DIRECTIONS = ("asc", "desc")
VISUALIZATIONS = ("kpi", "bar", "horizontal_bar", "donut", "line", "table", "list", "status")
AGGREGATION_VISUALIZATIONS = frozenset({"kpi", "bar", "horizontal_bar", "donut", "line"})
PROJECTION_VISUALIZATIONS = frozenset({"table", "list"})


class AnalysisValidationError(ValueError):
    """Raised when an untrusted analysis definition is invalid."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalysisValidationError(f"{name} bir object/dict olmalıdır.")
    return value


def _required_text(data: Mapping[str, Any], key: str, owner: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AnalysisValidationError(f"{owner}.{key} boş olmayan bir metin olmalıdır.")
    return value.strip()


@dataclass(slots=True)
class MeasureDefinition:
    field: str
    aggregation: str
    alias: str = "value"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "aggregation": self.aggregation, "alias": self.alias}

    @classmethod
    def from_dict(cls, value: Any) -> "MeasureDefinition":
        data = _mapping(value, "measure")
        aggregation = _required_text(data, "aggregation", "measure")
        if aggregation not in AGGREGATIONS:
            raise AnalysisValidationError(f"Desteklenmeyen aggregation: {aggregation}")
        raw_field = data.get("field", "")
        if not isinstance(raw_field, str):
            raise AnalysisValidationError("measure.field bir metin olmalıdır.")
        field = raw_field.strip()
        if aggregation == "count_rows":
            if field:
                raise AnalysisValidationError("count_rows does not accept a field")
        elif not field:
            raise AnalysisValidationError(f"{aggregation} requires a field")
        return cls(
            field=field,
            aggregation=aggregation,
            alias=str(data.get("alias") or "value").strip() or "value",
        )


@dataclass(slots=True)
class FilterDefinition:
    field: str
    operator: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "operator": self.operator, "value": self.value}

    @classmethod
    def from_dict(cls, value: Any) -> "FilterDefinition":
        data = _mapping(value, "filter")
        operator = _required_text(data, "operator", "filter")
        if operator not in FILTER_OPERATORS:
            raise AnalysisValidationError(f"Desteklenmeyen filter operator: {operator}")
        if operator == "between":
            between_value = data.get("value")
            if not isinstance(between_value, (list, tuple)) or len(between_value) != 2:
                raise AnalysisValidationError("between filter value tam iki elemanlı bir liste olmalıdır.")
        if operator in {"in", "not_in"} and not isinstance(data.get("value"), (list, tuple, set)):
            raise AnalysisValidationError(f"{operator} filter value bir liste olmalıdır.")
        return cls(field=_required_text(data, "field", "filter"), operator=operator, value=data.get("value"))


@dataclass(slots=True)
class SortDefinition:
    field: str
    direction: str = "asc"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(cls, value: Any) -> "SortDefinition":
        data = _mapping(value, "sort")
        direction = str(data.get("direction") or "asc").strip().lower()
        if direction not in SORT_DIRECTIONS:
            raise AnalysisValidationError(f"Sort direction asc veya desc olmalıdır: {direction}")
        return cls(field=_required_text(data, "field", "sort"), direction=direction)


@dataclass(slots=True)
class AnalysisDefinition:
    analysis_id: str
    title: str
    dataset: str
    visualization: str
    dimensions: list[str] = field(default_factory=list)
    measures: list[MeasureDefinition] = field(default_factory=list)
    filters: list[FilterDefinition] = field(default_factory=list)
    sort: list[SortDefinition] = field(default_factory=list)
    select_fields: list[str] = field(default_factory=list)
    limit: int | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "title": self.title,
            "dataset": self.dataset,
            "visualization": self.visualization,
            "dimensions": list(self.dimensions),
            "measures": [item.to_dict() for item in self.measures],
            "filters": [item.to_dict() for item in self.filters],
            "sort": [item.to_dict() for item in self.sort],
            "select_fields": list(self.select_fields),
            "limit": self.limit,
            "options": dict(self.options),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AnalysisDefinition":
        data = _mapping(value, "analysis")
        visualization = _required_text(data, "visualization", "analysis")
        if visualization not in VISUALIZATIONS:
            raise AnalysisValidationError(f"Desteklenmeyen visualization: {visualization}")
        dimensions = data.get("dimensions", [])
        measures = data.get("measures", [])
        filters = data.get("filters", [])
        sort = data.get("sort", [])
        select_fields = data.get("select_fields", [])
        options = data.get("options", {})
        if not isinstance(dimensions, list) or not all(isinstance(item, str) and item.strip() for item in dimensions):
            raise AnalysisValidationError("analysis.dimensions metin listesi olmalıdır.")
        if not isinstance(measures, list) or not isinstance(filters, list) or not isinstance(sort, list):
            raise AnalysisValidationError("analysis measures/filters/sort alanları liste olmalıdır.")
        if not isinstance(select_fields, list) or not all(isinstance(item, str) and item.strip() for item in select_fields):
            raise AnalysisValidationError("analysis.select_fields metin listesi olmalıdır.")
        if not isinstance(options, Mapping):
            raise AnalysisValidationError("analysis.options bir object/dict olmalıdır.")
        limit = data.get("limit")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise AnalysisValidationError("analysis.limit pozitif integer veya null olmalıdır.")
        return cls(
            analysis_id=_required_text(data, "analysis_id", "analysis"),
            title=_required_text(data, "title", "analysis"),
            dataset=_required_text(data, "dataset", "analysis"),
            visualization=visualization,
            dimensions=[item.strip() for item in dimensions],
            measures=[MeasureDefinition.from_dict(item) for item in measures],
            filters=[FilterDefinition.from_dict(item) for item in filters],
            sort=[SortDefinition.from_dict(item) for item in sort],
            select_fields=[item.strip() for item in select_fields],
            limit=limit,
            options=dict(options),
        )


@dataclass(slots=True)
class AnalysisResult:
    analysis_id: str
    dataset: str
    rows: list[dict[str, Any]]
    columns: list[str]
    value: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "dataset": self.dataset,
            "rows": [dict(row) for row in self.rows],
            "columns": list(self.columns),
            "value": self.value,
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class DashboardDefinition:
    dashboard_id: str
    title: str
    analysis_ids: list[str] = field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0
    layout: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "analysis_ids": list(self.analysis_ids),
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "layout": dict(self.layout),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "DashboardDefinition":
        data = _mapping(value, "dashboard")
        analysis_ids = data.get("analysis_ids", [])
        if not isinstance(analysis_ids, list) or not all(isinstance(item, str) and item.strip() for item in analysis_ids):
            raise AnalysisValidationError("dashboard.analysis_ids metin listesi olmalıdır.")
        return cls(
            dashboard_id=_required_text(data, "dashboard_id", "dashboard"),
            title=_required_text(data, "title", "dashboard"),
            analysis_ids=[item.strip() for item in analysis_ids],
            enabled=bool(data.get("enabled", True)),
            sort_order=int(data.get("sort_order") or 0),
            layout=dict(_mapping(data.get("layout", {}), "dashboard.layout")),
            meta=dict(_mapping(data.get("meta", {}), "dashboard.meta")),
        )
