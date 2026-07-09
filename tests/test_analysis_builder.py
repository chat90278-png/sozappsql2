from __future__ import annotations

from copy import deepcopy

import pytest

from analysis_center.analysis_builder import (
    BUILDER_VISUALIZATIONS,
    AnalysisBuilderController,
    BuilderFilterDraft,
)
from analysis_center.analysis_definitions import AnalysisValidationError
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService


@pytest.fixture
def service():
    active = AnalysisService(use_sample=True)
    active.data = build_sample_data()
    return active


@pytest.fixture
def controller(service):
    return AnalysisBuilderController(service)


def _acceptance_controller(controller: AnalysisBuilderController) -> AnalysisBuilderController:
    controller.set_dataset("acceptances")
    return controller


def test_dataset_and_field_capabilities_are_registry_driven(controller):
    datasets = controller.datasets()
    assert [(item.dataset_id, item.title) for item in datasets] == [
        (item.dataset_id, item.title) for item in controller.registry.list_datasets()
    ]
    assert "Teslimatlar / Kabuller" in {item.title for item in datasets}

    controller.set_dataset("contracts")
    registry_fields = controller.registry.list_fields("contracts")
    assert {item.field_id for item in controller.group_fields()} == {
        item.field_id for item in registry_fields
        if item.groupable and item.builder_allows("group")
    }
    assert {item.field_id for item in controller.filter_fields()} == {
        item.field_id for item in registry_fields
        if item.filterable and item.builder_allows("filter")
    }
    assert controller.registry.get_field("contracts", "platform_bucket").title == "Standart Platform"


def test_aggregation_options_and_measure_fields_follow_field_metadata(controller):
    controller.set_dataset("contracts")
    assert "count_rows" in controller.aggregation_options()
    assert "sum" in controller.aggregation_options()
    assert controller.measure_fields("count_rows") == []
    assert "status" not in {item.field_id for item in controller.measure_fields("sum")}
    assert "t0_months" in {item.field_id for item in controller.measure_fields("sum")}
    assert all(
        "sum" in field.allowed_aggregations and field.aggregatable
        for field in controller.measure_fields("sum")
    )


def test_builder_visualization_modes_are_explicit_and_supported(controller):
    modes = {item.visualization_id: item.mode for item in BUILDER_VISUALIZATIONS}
    assert modes == {
        "kpi": "aggregation",
        "bar": "aggregation",
        "horizontal_bar": "aggregation",
        "donut": "aggregation",
        "line": "aggregation",
        "table": "projection",
    }
    with pytest.raises(AnalysisValidationError, match="desteklenmeyen görünüm"):
        controller.set_visualization("status")


def test_builds_kpi_count_rows_definition(controller):
    controller.set_dataset("contracts")
    controller.set_visualization("kpi")
    controller.set_aggregation("count_rows")
    controller.draft.title = "Sözleşme Sayısı"

    definition = controller.build_definition()

    assert definition.title == "Sözleşme Sayısı"
    assert definition.dataset == "contracts"
    assert definition.visualization == "kpi"
    assert definition.dimensions == []
    assert definition.measures[0].field == ""
    assert definition.measures[0].aggregation == "count_rows"
    assert definition.limit is None


def test_builds_kpi_numeric_sum_definition(controller):
    _acceptance_controller(controller)
    controller.set_visualization("kpi")
    controller.set_aggregation("sum")
    controller.draft.measure_field = "delivered_total"

    definition = controller.build_definition()

    assert definition.measures[0].aggregation == "sum"
    assert definition.measures[0].field == "delivered_total"


def test_builds_grouped_count_rows_chart_definition(controller):
    _acceptance_controller(controller)
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    controller.set_aggregation("count_rows")
    controller.draft.limit = 10

    definition = controller.build_definition()

    assert definition.dimensions == ["platform"]
    assert definition.measures[0].aggregation == "count_rows"
    assert definition.limit == 10


def test_builds_grouped_sum_chart_definition(controller):
    _acceptance_controller(controller)
    controller.set_visualization("bar")
    controller.draft.group_field = "platform"
    controller.set_aggregation("sum")
    controller.draft.measure_field = "planned_total"

    definition = controller.build_definition()

    assert definition.dimensions == ["platform"]
    assert definition.measures[0].field == "planned_total"
    assert definition.measures[0].aggregation == "sum"


def test_builds_table_projection_sort_limit_and_title(controller):
    _acceptance_controller(controller)
    controller.set_visualization("table")
    controller.draft.title = "Teslimat Tablosu"
    controller.draft.selected_table_fields = ["platform", "name", "planned_total"]
    controller.draft.sort_field = "planned_total"
    controller.draft.sort_direction = "desc"
    controller.draft.limit = 5

    definition = controller.build_definition()

    assert definition.title == "Teslimat Tablosu"
    assert definition.dimensions == []
    assert definition.measures == []
    assert definition.select_fields == ["platform", "name", "planned_total"]
    assert definition.sort[0].to_dict() == {"field": "planned_total", "direction": "desc"}
    assert definition.limit == 5


def test_multiple_and_filters_sort_limit_are_in_definition(controller):
    _acceptance_controller(controller)
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    controller.set_aggregation("count_rows")
    controller.draft.filters = [
        BuilderFilterDraft("platform", "equals", "AKINCI"),
        BuilderFilterDraft("planned_total", "greater_than", "5"),
    ]
    controller.draft.sort_field = "value"
    controller.draft.sort_direction = "desc"
    controller.draft.limit = 20

    definition = controller.build_definition()

    assert [item.to_dict() for item in definition.filters] == [
        {"field": "platform", "operator": "equals", "value": "AKINCI"},
        {"field": "planned_total", "operator": "greater_than", "value": 5.0},
    ]
    assert definition.sort[0].field == "value"
    assert definition.limit == 20


def test_preview_analysis_id_is_stable_for_draft_and_reset_creates_new_id(controller):
    first_id = controller.draft.analysis_id
    definition_one = controller.build_definition()
    definition_two = controller.build_definition()
    assert definition_one.analysis_id == definition_two.analysis_id == first_id

    controller.reset()
    assert controller.draft.analysis_id != first_id


def test_chart_without_group_is_rejected(controller):
    controller.set_visualization("bar")
    controller.draft.group_field = ""
    with pytest.raises(AnalysisValidationError, match="gruplama alanı"):
        controller.build_definition()


def test_field_aggregation_without_measure_is_rejected(controller):
    _acceptance_controller(controller)
    controller.set_visualization("kpi")
    controller.set_aggregation("sum")
    controller.draft.measure_field = ""
    with pytest.raises(AnalysisValidationError, match="uygun bir alan seçin"):
        controller.build_definition()


def test_sum_on_text_field_is_unavailable_and_rejected(controller):
    _acceptance_controller(controller)
    assert "name" not in {item.field_id for item in controller.measure_fields("sum")}
    controller.set_visualization("kpi")
    controller.set_aggregation("sum")
    controller.draft.measure_field = "name"
    with pytest.raises(AnalysisValidationError, match="uygun bir alan seçin"):
        controller.build_definition()


def test_table_without_selected_field_is_rejected(controller):
    controller.set_visualization("table")
    controller.draft.selected_table_fields = []
    with pytest.raises(AnalysisValidationError, match="en az bir alan"):
        controller.build_definition()


def test_dataset_change_clears_stale_field_state_and_filters(controller):
    _acceptance_controller(controller)
    controller.draft.group_field = "system_name"
    controller.draft.measure_field = "delivered_total"
    controller.draft.filters = [BuilderFilterDraft("planned_total", "greater_than", "1")]
    controller.draft.selected_table_fields = ["system_name", "delivered_total"]
    controller.draft.sort_field = "value"

    controller.set_dataset("platforms")

    platform_fields = {item.field_id for item in controller.fields()}
    assert controller.draft.filters == []
    assert controller.draft.selected_table_fields == []
    assert controller.draft.measure_field in platform_fields or controller.draft.measure_field == ""
    assert controller.draft.group_field in {item.field_id for item in controller.group_fields()} | {""}
    assert controller.draft.sort_field == ""


@pytest.mark.parametrize(
    ("field_id", "operator", "raw", "raw_to", "expected"),
    [
        ("platform", "equals", "AKINCI", "", "AKINCI"),
        ("contract_id", "greater_than", "100", "", 100),
        ("planned_total", "between", "5,5", "12.5", [5.5, 12.5]),
        ("completed", "equals", "Evet", "", True),
        ("platform", "is_empty", "ignored", "", None),
        ("platform", "in", "AKINCI, TB2", "", ["AKINCI", "TB2"]),
        ("planned_acceptance_date", "equals", "2026-07-09", "", "2026-07-09"),
    ],
)
def test_filter_value_conversion(controller, field_id, operator, raw, raw_to, expected):
    _acceptance_controller(controller)
    converted = controller.convert_filter(BuilderFilterDraft(field_id, operator, raw, raw_to))
    assert converted.value == expected


def test_not_in_comma_separated_values_convert_to_list(controller):
    _acceptance_controller(controller)
    converted = controller.convert_filter(
        BuilderFilterDraft("status", "not_in", "Tamamlandı, Başlanmadı")
    )
    assert converted.value == ["Tamamlandı", "Başlanmadı"]


def test_invalid_numeric_filter_value_is_user_friendly(controller):
    _acceptance_controller(controller)
    with pytest.raises(AnalysisValidationError, match="sayı girin"):
        controller.convert_filter(BuilderFilterDraft("planned_total", "greater_than", "abc"))


def test_invalid_between_value_is_rejected(controller):
    _acceptance_controller(controller)
    with pytest.raises(AnalysisValidationError, match="sayı girin"):
        controller.convert_filter(BuilderFilterDraft("planned_total", "between", "5", "abc"))


def test_invalid_date_filter_is_rejected(controller):
    _acceptance_controller(controller)
    with pytest.raises(AnalysisValidationError, match="geçerli tarih"):
        controller.convert_filter(
            BuilderFilterDraft("planned_acceptance_date", "equals", "not-a-date")
        )


def test_filter_operator_not_allowed_for_field_is_rejected(controller):
    _acceptance_controller(controller)
    with pytest.raises(AnalysisValidationError, match="koşul desteklenmiyor"):
        controller.convert_filter(BuilderFilterDraft("platform", "greater_than", "AKINCI"))


def test_stale_filter_field_after_dataset_change_is_rejected_if_injected(controller):
    controller.set_dataset("platforms")
    controller.draft.filters = [BuilderFilterDraft("planned_total", "greater_than", "1")]
    with pytest.raises(AnalysisValidationError, match="Bilinmeyen field"):
        controller.build_definition()


def test_sort_options_match_visualization_mode(controller):
    _acceptance_controller(controller)
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    assert controller.sort_options() == [("platform", "Kategori"), ("value", "Değer")]

    controller.set_visualization("table")
    controller.draft.selected_table_fields = ["name", "planned_total"]
    assert controller.sort_options() == [("name", "Teslimat Adı"), ("planned_total", "Planlanan Toplam")]

    controller.set_visualization("kpi")
    assert controller.sort_options() == []


def test_reset_returns_sensible_new_draft(controller):
    old_id = controller.draft.analysis_id
    controller.draft.title = "Değişti"
    controller.draft.filters.append(BuilderFilterDraft("status", "equals", "Tamamlandı"))
    draft = controller.reset()
    assert draft.analysis_id != old_id
    assert draft.title == "Yeni Analiz"
    assert draft.dataset_id == controller.datasets()[0].dataset_id
    assert draft.visualization == "horizontal_bar"
    assert draft.filters == []
    assert draft.sort_field == ""
    assert draft.limit == 20
