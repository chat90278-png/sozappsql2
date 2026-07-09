from __future__ import annotations

import pytest

from analysis_center.analysis_builder import AnalysisBuilderController, BuilderFilterDraft
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService


@pytest.fixture
def controller():
    service = AnalysisService(use_sample=True)
    service.data = build_sample_data()
    return AnalysisBuilderController(service)


def test_real_engine_preview_contracts_count_kpi(controller):
    controller.set_dataset("contracts")
    controller.set_visualization("kpi")
    controller.set_aggregation("count_rows")
    definition, result = controller.preview()
    assert definition.dataset == "contracts"
    assert result.value == 3
    assert result.columns == ["value"]
    assert result.meta == {
        "source_row_count": 3,
        "filtered_row_count": 3,
        "result_row_count": 1,
        "execution_errors": [],
        "warnings": [],
    }


def test_real_engine_preview_acceptances_grouped_by_platform_count(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    controller.set_aggregation("count_rows")
    _, result = controller.preview()
    assert result.columns == ["platform", "value"]
    assert result.rows == [
        {"platform": "AKINCI", "value": 1},
        {"platform": "TB2", "value": 1},
    ]
    assert result.meta["filtered_row_count"] == 2
    assert result.meta["result_row_count"] == 2


def test_real_engine_preview_status_bucket_donut(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("donut")
    controller.draft.group_field = "status_bucket"
    controller.set_aggregation("count_rows")
    _, result = controller.preview()
    assert {row["status_bucket"] for row in result.rows} == {"Devam ediyor", "Tamamlanan"}
    assert sum(row["value"] for row in result.rows) == 2


def test_real_engine_preview_numeric_sum(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("kpi")
    controller.set_aggregation("sum")
    controller.draft.measure_field = "delivered_total"
    _, result = controller.preview()
    assert result.value == 10
    assert result.rows == [{"value": 10}]


def test_real_engine_preview_filtered_real_platform(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("kpi")
    controller.set_aggregation("count_rows")
    controller.draft.filters = [BuilderFilterDraft("platform", "equals", "AKINCI")]
    _, result = controller.preview()
    assert result.value == 1
    assert result.meta["filtered_row_count"] == 1


def test_real_engine_preview_two_filters_use_and_semantics(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("kpi")
    controller.set_aggregation("count_rows")
    controller.draft.filters = [
        BuilderFilterDraft("platform", "equals", "AKINCI"),
        BuilderFilterDraft("planned_total", "greater_than", "8"),
    ]
    _, result = controller.preview()
    assert result.value == 1
    assert result.meta["filtered_row_count"] == 1


def test_real_engine_preview_table_projection(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("table")
    controller.draft.selected_table_fields = ["platform", "name", "planned_total"]
    _, result = controller.preview()
    assert result.columns == ["platform", "name", "planned_total"]
    assert result.rows[0] == {
        "platform": "AKINCI",
        "name": "Teslimat-1",
        "planned_total": 10.0,
    }
    assert result.meta["result_row_count"] == 2


def test_real_engine_preview_table_sort_and_limit(controller):
    controller.set_dataset("acceptances")
    controller.set_visualization("table")
    controller.draft.selected_table_fields = ["platform", "planned_total"]
    controller.draft.sort_field = "planned_total"
    controller.draft.sort_direction = "desc"
    controller.draft.limit = 1
    _, result = controller.preview()
    assert result.rows == [{"platform": "AKINCI", "planned_total": 10.0}]
    assert result.meta["filtered_row_count"] == 2
    assert result.meta["result_row_count"] == 1


def test_real_engine_preview_chart_result_sort_and_limit(controller):
    data = build_sample_data()
    data["acceptances"].append({
        "id": 403,
        "contract_id": 101,
        "system_id": 201,
        "platform": "AKINCI",
        "contract_no": "STS-2026-001",
        "system_name": "Görev Bilgisayarı",
        "name": "Teslimat-2",
        "status": "Devam Ediyor",
        "acceptance_date": "",
        "planned_acceptance_date": "2026-08-01",
        "planned_delivery_date": "",
        "completion_date": "2026-08-01",
        "planned_total": 3.0,
        "delivered_total": 1.0,
    })
    controller.service.data = data
    controller.set_dataset("acceptances")
    controller.set_visualization("bar")
    controller.draft.group_field = "platform"
    controller.set_aggregation("count_rows")
    controller.draft.sort_field = "value"
    controller.draft.sort_direction = "desc"
    controller.draft.limit = 1
    _, result = controller.preview()
    assert result.rows == [{"platform": "AKINCI", "value": 2}]
    assert result.meta["filtered_row_count"] == 3
    assert result.meta["result_row_count"] == 1
