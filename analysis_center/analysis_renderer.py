from __future__ import annotations

from .analysis_definitions import AnalysisDefinition, AnalysisResult, AnalysisValidationError
from .analysis_models import AnalysisCard, AnalysisEntity, CardSize, CardType, ChartType
from .analysis_visual_settings import (
    AnalysisVisualSettings,
    has_visual_settings,
    normalize_column_order,
    transform_chart_rows,
)


_VISUALIZATION_MAP = {
    "kpi": (CardType.KPI, ChartType.NONE),
    "bar": (CardType.CHART, ChartType.BAR),
    "horizontal_bar": (CardType.CHART, ChartType.HORIZONTAL_BAR),
    "donut": (CardType.CHART, ChartType.DONUT),
    "line": (CardType.CHART, ChartType.LINE),
    "table": (CardType.TABLE, ChartType.NONE),
    "list": (CardType.LIST, ChartType.NONE),
    "status": (CardType.STATUS, ChartType.NONE),
}

_DATASET_ENTITY = {
    "contracts": AnalysisEntity.CONTRACT, "platforms": AnalysisEntity.PLATFORM,
    "acceptances": AnalysisEntity.ACCEPTANCE, "deadlines": AnalysisEntity.DEADLINE,
    "systems": AnalysisEntity.SYSTEM, "components": AnalysisEntity.COMPONENT,
    "users": AnalysisEntity.USER, "tags": AnalysisEntity.TAG,
}


def analysis_result_to_card(definition: AnalysisDefinition, result: AnalysisResult) -> AnalysisCard:
    try:
        card_type, chart_type = _VISUALIZATION_MAP[definition.visualization]
    except KeyError as exc:
        raise AnalysisValidationError(f"Desteklenmeyen visualization: {definition.visualization}") from exc
    entity = _DATASET_ENTITY.get(definition.dataset, AnalysisEntity.CONTRACT)
    options = definition.options
    visual_enabled = has_visual_settings(options)
    visual_settings = AnalysisVisualSettings.from_options(
        options,
        selected_table_fields=definition.select_fields,
        strict=False,
    )
    data = result.rows
    columns = list(result.columns)
    if card_type == CardType.CHART and definition.dimensions:
        dimension = definition.dimensions[0]
        alias = definition.measures[0].alias or "value"
        data = [{"label": row.get(dimension, ""), "value": row.get(alias)} for row in result.rows]
        if visual_enabled:
            data = transform_chart_rows(
                data,
                visual_settings.chart,
                visualization=definition.visualization,
            )
    if card_type == CardType.TABLE and visual_enabled:
        columns = normalize_column_order(result.columns, visual_settings.table.column_order)
    subtitle = str(options.get("subtitle", ""))
    if card_type == CardType.KPI and visual_enabled:
        subtitle = visual_settings.kpi.subtitle
    return AnalysisCard(
        card_id=definition.analysis_id,
        title=definition.title,
        entity=entity,
        card_type=card_type,
        size=CardSize(str(options.get("size", CardSize.MEDIUM.value))),
        chart_type=chart_type,
        value=result.value if card_type == CardType.KPI else None,
        unit=str(options.get("unit", "")),
        subtitle=subtitle,
        columns=columns,
        data=data,
        enabled=bool(options.get("enabled", True)),
        screen_id=str(options.get("screen_id", "")),
        sort_order=int(options.get("sort_order", 0)),
        meta={
            "analysis_id": definition.analysis_id,
            "dataset": definition.dataset,
            "visual_settings_enabled": visual_enabled,
            "visual_settings": visual_settings,
            **result.meta,
        },
    )
