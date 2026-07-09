from __future__ import annotations

from copy import deepcopy

import pytest

from analysis_center.analysis_builder import AnalysisBuilderController
from analysis_center.analysis_definitions import AnalysisDefinition, AnalysisResult, AnalysisValidationError, MeasureDefinition
from analysis_center.analysis_renderer import analysis_result_to_card
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService
from analysis_center.analysis_visual_settings import (
    AnalysisVisualSettings,
    CHART_PALETTES,
    ChartVisualSettings,
    KpiVisualSettings,
    TableVisualSettings,
    format_kpi_value,
    normalize_column_order,
    palette_colors,
    transform_chart_rows,
)


def _service() -> AnalysisService:
    service = AnalysisService(use_sample=True)
    service.data = build_sample_data()
    return service


def test_default_chart_settings_are_explicit():
    settings = AnalysisVisualSettings.defaults()
    assert settings.chart == ChartVisualSettings(
        show_legend=True,
        legend_position="right",
        show_values=False,
        palette="corporate",
        max_categories=None,
        group_others=False,
    )


def test_visual_settings_options_round_trip_preserves_unknown_options_and_nested_keys():
    options = {
        "size": "large",
        "future_root": {"x": 1},
        "visual_settings": {
            "chart": {"palette": "pastel", "future_chart": "keep"},
            "future_visual": {"y": 2},
        },
    }
    settings = AnalysisVisualSettings.from_options(options, strict=True)
    settings.replace_chart(show_values=True, legend_position="bottom", max_categories=3)

    result = settings.to_options(options)

    assert result["size"] == "large"
    assert result["future_root"] == {"x": 1}
    assert result["visual_settings"]["future_visual"] == {"y": 2}
    assert result["visual_settings"]["chart"]["future_chart"] == "keep"
    assert result["visual_settings"]["chart"]["palette"] == "pastel"
    assert result["visual_settings"]["chart"]["show_values"] is True
    assert result["visual_settings"]["chart"]["legend_position"] == "bottom"
    assert result["visual_settings"]["chart"]["max_categories"] == 3


def test_invalid_palette_and_max_categories_strict_reject_tolerant_fallback():
    with pytest.raises(AnalysisValidationError, match="renk paleti"):
        AnalysisVisualSettings.from_options(
            {"visual_settings": {"chart": {"palette": "neon"}}}, strict=True
        )
    with pytest.raises(AnalysisValidationError, match="Maksimum kategori"):
        AnalysisVisualSettings.from_options(
            {"visual_settings": {"chart": {"max_categories": 0}}}, strict=True
        )

    settings = AnalysisVisualSettings.from_options(
        {"visual_settings": {"chart": {"palette": "neon", "max_categories": -5}}},
        strict=False,
    )
    assert settings.chart.palette == "corporate"
    assert settings.chart.max_categories is None


def test_kpi_decimal_validation_and_formatting():
    with pytest.raises(AnalysisValidationError, match="Ondalık basamak"):
        AnalysisVisualSettings.from_options(
            {"visual_settings": {"kpi": {"decimal_places": -1}}}, strict=True
        )
    settings = KpiVisualSettings(prefix="₺ ", suffix=" TL", decimal_places=0)
    assert format_kpi_value(1250000, settings) == "₺ 1.250.000 TL"
    assert format_kpi_value(86.42, KpiVisualSettings(decimal_places=1, suffix="%")) == "86,4%"
    assert format_kpi_value(86.42, KpiVisualSettings(decimal_places=2)) == "86,42"
    assert format_kpi_value("TBD", KpiVisualSettings(prefix="[", suffix="]", decimal_places=2)) == "[TBD]"


def test_column_order_normalization_ignores_unknown_and_appends_missing():
    assert normalize_column_order(
        ["platform", "name", "status", "planned_total"],
        ["status", "unknown", "status", "platform"],
    ) == ["status", "platform", "name", "planned_total"]

    with pytest.raises(AnalysisValidationError, match="aynı alan"):
        AnalysisVisualSettings.from_options(
            {"visual_settings": {"table": {"column_order": ["a", "a"]}}},
            strict=True,
        )


def test_palette_resolution_is_centralized():
    assert palette_colors("pastel") == CHART_PALETTES["pastel"]
    assert palette_colors("missing") == CHART_PALETTES["corporate"]


def test_chart_category_limit_and_group_others_do_not_mutate_source():
    rows = [
        {"label": "A", "value": 50},
        {"label": "B", "value": 30},
        {"label": "C", "value": 20},
        {"label": "D", "value": 10},
        {"label": "E", "value": 5},
    ]
    original = deepcopy(rows)
    grouped = transform_chart_rows(
        rows,
        ChartVisualSettings(max_categories=3, group_others=True),
        visualization="bar",
    )
    truncated = transform_chart_rows(
        rows,
        ChartVisualSettings(max_categories=3, group_others=False),
        visualization="horizontal_bar",
    )
    line = transform_chart_rows(
        rows,
        ChartVisualSettings(max_categories=3, group_others=True),
        visualization="line",
    )

    assert grouped == [
        {"label": "A", "value": 50},
        {"label": "B", "value": 30},
        {"label": "C", "value": 20},
        {"label": "Diğer", "value": 15.0},
    ]
    assert truncated == original[:3]
    assert line == original[:3]  # line ignores group_others but still honors the visual category cap
    assert rows == original


def test_analysis_result_to_card_applies_chart_settings_without_mutating_result():
    definition = AnalysisDefinition(
        analysis_id="custom-chart",
        title="Chart",
        dataset="acceptances",
        visualization="bar",
        dimensions=["platform"],
        measures=[MeasureDefinition(field="", aggregation="count_rows", alias="value")],
        options=AnalysisVisualSettings(
            chart=ChartVisualSettings(
                show_legend=False,
                legend_position="bottom",
                show_values=True,
                palette="pastel",
                max_categories=2,
                group_others=True,
            )
        ).to_options(),
    )
    result = AnalysisResult(
        analysis_id=definition.analysis_id,
        dataset="acceptances",
        columns=["platform", "value"],
        rows=[
            {"platform": "A", "value": 4},
            {"platform": "B", "value": 3},
            {"platform": "C", "value": 2},
            {"platform": "D", "value": 1},
        ],
    )
    before = deepcopy(result.rows)

    card = analysis_result_to_card(definition, result)

    assert card.data == [
        {"label": "A", "value": 4},
        {"label": "B", "value": 3},
        {"label": "Diğer", "value": 3.0},
    ]
    assert card.meta["visual_settings_enabled"] is True
    assert card.meta["visual_settings"].chart.palette == "pastel"
    assert result.rows == before


def test_analysis_result_to_card_applies_kpi_and_table_settings():
    kpi_settings = AnalysisVisualSettings(
        kpi=KpiVisualSettings(subtitle="Planlanan oran", prefix="", suffix="%", decimal_places=1)
    )
    kpi_definition = AnalysisDefinition(
        analysis_id="custom-kpi",
        title="Oran",
        dataset="contracts",
        visualization="kpi",
        measures=[MeasureDefinition(field="t0_months", aggregation="avg", alias="value")],
        options=kpi_settings.to_options(),
    )
    kpi_card = analysis_result_to_card(
        kpi_definition,
        AnalysisResult("custom-kpi", "contracts", [], [], value=86.42),
    )
    assert kpi_card.subtitle == "Planlanan oran"
    assert kpi_card.meta["visual_settings"].kpi.suffix == "%"

    table_settings = AnalysisVisualSettings(
        table=TableVisualSettings(("status", "platform"))
    )
    table_definition = AnalysisDefinition(
        analysis_id="custom-table",
        title="Table",
        dataset="acceptances",
        visualization="table",
        select_fields=["platform", "name", "status"],
        options=table_settings.to_options(),
    )
    table_card = analysis_result_to_card(
        table_definition,
        AnalysisResult(
            "custom-table",
            "acceptances",
            [{"platform": "A", "name": "N", "status": "S"}],
            ["platform", "name", "status"],
        ),
    )
    assert table_card.columns == ["status", "platform", "name"]


def test_builder_visual_settings_round_trip_and_saved_reload_preserve_unknown_options():
    service = _service()
    controller = AnalysisBuilderController(service)
    controller.set_dataset("acceptances")
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    controller.draft.title = "Visual"
    controller.draft.options = {"future_option": "keep"}
    controller.update_chart_visual_settings(
        palette="pastel",
        legend_position="bottom",
        show_values=True,
        max_categories=4,
        group_others=True,
    )

    first = controller.build_definition()
    controller.load_definition(first)
    second = controller.build_definition()

    assert second.options == first.options
    assert second.options["future_option"] == "keep"
    assert controller.visual_settings().chart == first_options_chart(first)


def first_options_chart(definition: AnalysisDefinition) -> ChartVisualSettings:
    return AnalysisVisualSettings.from_options(definition.options, strict=True).chart


def test_invalid_persisted_visual_options_fallback_in_renderer_without_crash():
    definition = AnalysisDefinition(
        analysis_id="custom-invalid-visual",
        title="Fallback",
        dataset="acceptances",
        visualization="horizontal_bar",
        dimensions=["platform"],
        measures=[MeasureDefinition("", "count_rows")],
        options={
            "visual_settings": {
                "chart": {
                    "palette": "not-real",
                    "legend_position": "left",
                    "max_categories": -4,
                }
            }
        },
    )
    result = AnalysisResult(
        definition.analysis_id,
        "acceptances",
        [{"platform": "A", "value": 2}],
        ["platform", "value"],
    )

    card = analysis_result_to_card(definition, result)

    settings = card.meta["visual_settings"].chart
    assert settings.palette == "corporate"
    assert settings.legend_position == "right"
    assert settings.max_categories is None


def test_prepared_definition_without_visual_settings_keeps_legacy_adapter_branch():
    definition = AnalysisDefinition(
        analysis_id="prepared-like",
        title="Prepared",
        dataset="acceptances",
        visualization="bar",
        dimensions=["platform"],
        measures=[MeasureDefinition("", "count_rows")],
        options={},
    )
    result = AnalysisResult(
        definition.analysis_id,
        "acceptances",
        [{"platform": "A", "value": 2}],
        ["platform", "value"],
    )

    card = analysis_result_to_card(definition, result)

    assert card.meta["visual_settings_enabled"] is False
    assert card.data == [{"label": "A", "value": 2}]
