from datetime import date

import pytest

from analysis_center.analysis_builtin import get_builtin_analysis
from analysis_center.analysis_definitions import (
    AnalysisDefinition, AnalysisValidationError, FilterDefinition, MeasureDefinition, SortDefinition,
)
from analysis_center.analysis_engine import AnalysisEngine
from analysis_center.analysis_sample_data import build_sample_data


@pytest.fixture
def data():
    return build_sample_data(date(2026, 7, 7))


@pytest.fixture
def engine():
    return AnalysisEngine()


def definition(**kwargs):
    base = dict(
        analysis_id="test", title="Test", dataset="contracts", visualization="kpi",
        dimensions=[], measures=[MeasureDefinition("id", "count")], filters=[], sort=[],
    )
    base.update(kwargs)
    return AnalysisDefinition(**base)


def test_kpi_count(engine, data):
    result = engine.execute(definition(), data)
    assert result.value == 3
    assert result.rows == [{"value": 3}]


def test_grouped_count(engine, data):
    result = engine.execute(definition(
        visualization="bar", dimensions=["platform"],
        sort=[SortDefinition("value", "desc")],
    ), data)
    assert {row["platform"]: row["value"] for row in result.rows} == {"AKINCI": 1, "TB2": 1, "KIZILELMA": 1}


def test_filter_count_case_and_turkish_normalized(engine, data):
    result = engine.execute(definition(
        filters=[FilterDefinition("status", "equals", "devam ediyor")]
    ), data)
    assert result.value == 1


def test_contains_filter(engine, data):
    result = engine.execute(definition(
        filters=[FilterDefinition("contract_no", "contains", "2026")]
    ), data)
    assert result.value == 3


@pytest.mark.parametrize(("aggregation", "expected"), [
    ("sum", 16.0), ("avg", 8.0), ("min", 6.0), ("max", 10.0),
])
def test_numeric_aggregations(engine, data, aggregation, expected):
    result = engine.execute(AnalysisDefinition(
        "numeric", "Numeric", "acceptances", "kpi",
        measures=[MeasureDefinition("planned_total", aggregation)],
    ), data)
    assert result.value == expected


def test_sort_descending_and_limit(engine, data):
    custom = build_sample_data(date(2026, 7, 7))
    custom["contracts"].extend([
        {**custom["contracts"][0], "id": 104, "platform": "AKINCI"},
        {**custom["contracts"][0], "id": 105, "platform": "AKINCI"},
        {**custom["contracts"][0], "id": 106, "platform": "TB2"},
    ])
    result = engine.execute(definition(
        visualization="bar", dimensions=["platform"],
        sort=[SortDefinition("value", "desc")], limit=2,
    ), custom)
    assert [row["platform"] for row in result.rows] == ["AKINCI", "TB2"]
    assert len(result.rows) == 2


def test_empty_dataset_controlled_result(engine, data):
    data["contracts"] = []
    result = engine.execute(definition(), data)
    assert result.value == 0
    assert result.rows == [{"value": 0}]
    assert result.meta["source_row_count"] == 0


def test_invalid_dataset(engine, data):
    with pytest.raises(AnalysisValidationError, match="Bilinmeyen dataset"):
        engine.execute(definition(dataset="missing"), data)


def test_invalid_field(engine, data):
    with pytest.raises(AnalysisValidationError, match="Bilinmeyen field"):
        engine.execute(definition(measures=[MeasureDefinition("missing", "count")]), data)


def test_unsupported_aggregation(engine, data):
    with pytest.raises(AnalysisValidationError, match="aggregation desteklenmiyor"):
        engine.execute(definition(measures=[MeasureDefinition("status", "sum")]), data)


def test_multiple_dimensions_validation(engine, data):
    with pytest.raises(AnalysisValidationError, match="en fazla 1 dimension"):
        engine.execute(definition(dimensions=["platform", "status"]), data)


def test_multiple_measures_validation(engine, data):
    with pytest.raises(AnalysisValidationError, match="tam olarak 1 measure"):
        engine.execute(definition(measures=[
            MeasureDefinition("id", "count"), MeasureDefinition("status", "count_distinct")
        ]), data)


@pytest.mark.parametrize("analysis_id", [
    "total_contracts", "total_platforms", "platform_distribution", "contract_status_distribution",
    "total_acceptances", "acceptance_status_distribution", "upcoming_deadline_count", "past_deadline_count",
])
def test_builtin_analysis_execution(engine, data, analysis_id):
    definition_ = get_builtin_analysis(analysis_id, today=date(2026, 7, 7), upcoming_days=60)
    result = engine.execute(definition_, data)
    assert result.analysis_id == analysis_id
    assert result.meta["execution_errors"] == []

from analysis_center.analysis_models import CardType
from analysis_center.analysis_renderer import analysis_result_to_card


def projection_definition(**kwargs):
    base = dict(
        analysis_id="projection", title="Projection", dataset="contracts", visualization="table",
        dimensions=[], measures=[], filters=[], sort=[],
        select_fields=["platform", "contract_no", "status"],
    )
    base.update(kwargs)
    return AnalysisDefinition(**base)


def test_table_basic_projection(engine, data):
    result = engine.execute(projection_definition(), data)
    assert result.rows == [
        {"platform": "AKINCI", "contract_no": "STS-2026-001", "status": "Devam Ediyor"},
        {"platform": "TB2", "contract_no": "STS-2026-002", "status": "Tamamlandı"},
        {"platform": "KIZILELMA", "contract_no": "STS-2026-003", "status": "Başlanmadı"},
    ]
    assert all(set(row) == {"platform", "contract_no", "status"} for row in result.rows)


def test_projection_field_order_is_preserved(engine, data):
    selected = ["status", "platform", "contract_no"]
    result = engine.execute(projection_definition(select_fields=selected), data)
    assert result.columns == selected
    assert list(result.rows[0]) == selected


def test_projection_filter(engine, data):
    result = engine.execute(projection_definition(
        filters=[FilterDefinition("status", "equals", "Devam Ediyor")],
    ), data)
    assert result.rows == [
        {"platform": "AKINCI", "contract_no": "STS-2026-001", "status": "Devam Ediyor"}
    ]
    assert result.meta["filtered_row_count"] == 1


def test_projection_date_sort_ascending(engine, data):
    result = engine.execute(projection_definition(
        select_fields=["id", "completion_date"],
        sort=[SortDefinition("completion_date", "asc")],
    ), data)
    assert [row["id"] for row in result.rows] == [102, 103, 101]


def test_projection_numeric_sort_descending(engine, data):
    result = engine.execute(projection_definition(
        dataset="acceptances",
        select_fields=["id", "planned_total"],
        sort=[SortDefinition("planned_total", "desc")],
    ), data)
    assert [row["planned_total"] for row in result.rows] == [10.0, 6.0]


def test_projection_numeric_sort_descending_nulls_last(engine, data):
    data["acceptances"] = [
        {"id": 1, "planned_total": 10},
        {"id": 2, "planned_total": None},
        {"id": 3, "planned_total": 6},
        {"id": 4, "planned_total": ""},
    ]
    result = engine.execute(projection_definition(
        dataset="acceptances",
        select_fields=["id", "planned_total"],
        sort=[SortDefinition("planned_total", "desc")],
    ), data)
    values = [row["planned_total"] for row in result.rows]
    assert values[:2] == [10, 6]
    assert all(value in (None, "") for value in values[2:])


def test_projection_date_sort_ascending_nulls_last(engine, data):
    data["contracts"] = [
        {"id": 1, "completion_date": "2026-07-20"},
        {"id": 2, "completion_date": None},
        {"id": 3, "completion_date": "2026-07-10"},
        {"id": 4, "completion_date": ""},
    ]
    result = engine.execute(projection_definition(
        select_fields=["id", "completion_date"],
        sort=[SortDefinition("completion_date", "asc")],
    ), data)
    values = [row["completion_date"] for row in result.rows]
    assert values[:2] == ["2026-07-10", "2026-07-20"]
    assert all(value in (None, "") for value in values[2:])


def test_projection_limit(engine, data):
    result = engine.execute(projection_definition(
        select_fields=["contract_no"],
        sort=[SortDefinition("contract_no", "asc")],
        limit=2,
    ), data)
    assert result.rows == [
        {"contract_no": "STS-2026-001"},
        {"contract_no": "STS-2026-002"},
    ]
    assert result.meta["result_row_count"] == 2


@pytest.mark.parametrize("visualization", ["table", "list"])
def test_projection_without_select_fields_validation(engine, data, visualization):
    with pytest.raises(AnalysisValidationError, match="require select_fields"):
        engine.execute(projection_definition(visualization=visualization, select_fields=[]), data)


def test_projection_with_measure_validation(engine, data):
    with pytest.raises(AnalysisValidationError, match="do not support measures"):
        engine.execute(projection_definition(measures=[MeasureDefinition("id", "count")]), data)


def test_projection_with_dimension_validation(engine, data):
    with pytest.raises(AnalysisValidationError, match="do not support dimensions"):
        engine.execute(projection_definition(dimensions=["platform"]), data)


def test_projection_unknown_select_field_validation(engine, data):
    with pytest.raises(AnalysisValidationError, match="Bilinmeyen field"):
        engine.execute(projection_definition(select_fields=["platform", "missing"]), data)


def test_projection_sort_field_must_be_selected(engine, data):
    with pytest.raises(AnalysisValidationError, match="projection sort field must be present in select_fields"):
        engine.execute(projection_definition(
            select_fields=["platform"],
            sort=[SortDefinition("contract_no", "asc")],
        ), data)


def test_renderer_table_card_uses_projection_columns_and_rows(engine, data):
    definition_ = projection_definition(select_fields=["status", "platform"])
    result = engine.execute(definition_, data)
    card = analysis_result_to_card(definition_, result)
    assert card.card_type == CardType.TABLE
    assert card.columns == ["status", "platform"]
    assert card.data == result.rows


def test_renderer_list_card_uses_projection_rows(engine, data):
    definition_ = projection_definition(
        visualization="list",
        select_fields=["contract_no", "status"],
    )
    result = engine.execute(definition_, data)
    card = analysis_result_to_card(definition_, result)
    assert card.card_type == CardType.LIST
    assert card.data == result.rows


def test_analysis_definition_select_fields_round_trip_and_legacy_default():
    definition_ = projection_definition(select_fields=["status", "platform"])
    restored = AnalysisDefinition.from_dict(definition_.to_dict())
    assert restored.select_fields == ["status", "platform"]

    legacy_payload = definition().to_dict()
    legacy_payload.pop("select_fields")
    restored_legacy = AnalysisDefinition.from_dict(legacy_payload)
    assert restored_legacy.select_fields == []



def count_definition(field: str, aggregation: str, *, dataset: str = "contracts", dimensions=None):
    return AnalysisDefinition(
        analysis_id=f"{aggregation}_test",
        title="Count semantics",
        dataset=dataset,
        visualization="bar" if dimensions else "kpi",
        dimensions=list(dimensions or []),
        measures=[MeasureDefinition(field, aggregation)],
        filters=[],
        sort=[],
    )


def test_count_rows_counts_filtered_rows(engine, data):
    data["contracts"] = [
        {"status": "A"},
        {"status": "B"},
        {"status": None},
        {"status": ""},
        {"status": "A"},
    ]
    result = engine.execute(count_definition("", "count_rows"), data)
    assert result.value == 5


def test_count_ignores_none_and_empty_string(engine, data):
    data["contracts"] = [
        {"status": "A"},
        {"status": "B"},
        {"status": None},
        {"status": ""},
        {"status": "A"},
    ]
    result = engine.execute(count_definition("status", "count"), data)
    assert result.value == 3


def test_count_ignores_whitespace_only_string(engine, data):
    data["contracts"] = [
        {"status": "A"},
        {"status": "   "},
        {"status": None},
    ]
    result = engine.execute(count_definition("status", "count"), data)
    assert result.value == 1


def test_count_includes_numeric_zero(engine, data):
    data["acceptances"] = [
        {"planned_total": 10},
        {"planned_total": 0},
        {"planned_total": None},
        {"planned_total": ""},
    ]
    result = engine.execute(count_definition("planned_total", "count", dataset="acceptances"), data)
    assert result.value == 2


def test_count_includes_boolean_false(engine, data):
    data["contracts"] = [
        {"is_main": True},
        {"is_main": False},
        {"is_main": None},
    ]
    result = engine.execute(count_definition("is_main", "count"), data)
    assert result.value == 2


def test_count_distinct_ignores_empty_values(engine, data):
    data["contracts"] = [
        {"status": "A"},
        {"status": "B"},
        {"status": None},
        {"status": ""},
        {"status": "A"},
    ]
    result = engine.execute(count_definition("status", "count_distinct"), data)
    assert result.value == 2


def test_count_distinct_normalizes_text_and_turkish_case(engine, data):
    data["contracts"] = [
        {"status": "Devam Ediyor"},
        {"status": "devam ediyor"},
        {"status": "DEVAM EDİYOR"},
    ]
    result = engine.execute(count_definition("status", "count_distinct"), data)
    assert result.value == 1


def test_grouped_count_rows(engine, data):
    data["contracts"] = [
        {"platform": "Platform A"},
        {"platform": "Platform A"},
        {"platform": "Platform A"},
        {"platform": "Platform B"},
        {"platform": "Platform B"},
    ]
    result = engine.execute(count_definition("", "count_rows", dimensions=["platform"]), data)
    assert {row["platform"]: row["value"] for row in result.rows} == {
        "Platform A": 3,
        "Platform B": 2,
    }


def test_count_rows_rejects_field(engine, data):
    with pytest.raises(AnalysisValidationError, match="count_rows does not accept a field"):
        engine.execute(count_definition("id", "count_rows"), data)


def test_count_requires_field(engine, data):
    with pytest.raises(AnalysisValidationError, match="count requires a field"):
        engine.execute(count_definition("", "count"), data)


def test_count_distinct_requires_field(engine, data):
    with pytest.raises(AnalysisValidationError, match="count_distinct requires a field"):
        engine.execute(count_definition("", "count_distinct"), data)


def test_count_rows_measure_round_trip_without_field():
    measure = MeasureDefinition.from_dict({"field": "", "aggregation": "count_rows", "alias": "Kayıt Sayısı"})
    assert measure == MeasureDefinition(field="", aggregation="count_rows", alias="Kayıt Sayısı")
    assert measure.to_dict()["field"] == ""


def test_count_rows_capability_is_global_not_field_level():
    from analysis_center.analysis_registry import DEFAULT_REGISTRY, get_analysis_capabilities

    capabilities = get_analysis_capabilities()
    assert "count_rows" in capabilities["aggregations"]
    assert capabilities["row_aggregations"] == ["count_rows"]
    assert "count_rows" not in DEFAULT_REGISTRY.get_field("contracts", "status").allowed_aggregations
    assert "count_distinct" in DEFAULT_REGISTRY.get_field("contracts", "completion_date").allowed_aggregations


@pytest.mark.parametrize(
    ("analysis_id", "expected"),
    [
        ("total_contracts", 3),
        ("total_acceptances", 2),
        ("upcoming_deadline_count", 2),
        ("past_deadline_count", 1),
    ],
)
def test_row_count_builtins_use_count_rows_and_preserve_results(engine, data, analysis_id, expected):
    definition_ = get_builtin_analysis(analysis_id, today=date(2026, 7, 7), upcoming_days=60)
    assert definition_.measures == [MeasureDefinition(field="", aggregation="count_rows", alias="value")]
    assert engine.execute(definition_, data).value == expected


def test_grouped_row_count_builtins_use_count_rows(engine, data):
    for analysis_id in ("platform_distribution", "contract_status_distribution", "acceptance_status_distribution"):
        definition_ = get_builtin_analysis(analysis_id, today=date(2026, 7, 7), upcoming_days=60)
        assert definition_.measures[0].field == ""
        assert definition_.measures[0].aggregation == "count_rows"
        result = engine.execute(definition_, data)
        assert sum(row["value"] for row in result.rows) == result.meta["filtered_row_count"]


from analysis_center.analysis_metrics import compute_metrics
from analysis_center.analysis_registry import DEFAULT_REGISTRY
from analysis_center.analysis_utils import normalize_status_bucket


@pytest.mark.parametrize("dataset_id", ["contracts", "acceptances"])
def test_status_bucket_registry_metadata(dataset_id):
    field = DEFAULT_REGISTRY.get_field(dataset_id, "status_bucket")
    assert field.derived is True
    assert field.field_type == "category"
    assert field.groupable is True
    assert field.filterable is True
    assert field.aggregatable is True
    assert field.sortable is True
    assert field.allowed_aggregations == ("count", "count_distinct")
    assert DEFAULT_REGISTRY.resolve_value(dataset_id, "status_bucket", {"status": "Completed"}) == "Tamamlanan"


@pytest.mark.parametrize("status", ["Tamamlandı", "Completed", "Closed", "Done"])
def test_status_bucket_known_completed_statuses(status):
    assert normalize_status_bucket(status) == "Tamamlanan"


@pytest.mark.parametrize("status", ["Başlanmadı", "Plan", "Planlandı", "Not Started"])
def test_status_bucket_known_not_started_statuses(status):
    assert normalize_status_bucket(status) == "Başlanmadı"


@pytest.mark.parametrize("status", ["Devam Ediyor", "Açık", "Aktif", "Open", "In Progress"])
def test_status_bucket_known_in_progress_statuses(status):
    assert normalize_status_bucket(status) == "Devam ediyor"


@pytest.mark.parametrize("status", [None, "", "   "])
def test_status_bucket_missing_status(status):
    assert normalize_status_bucket(status) == "Eksik durum"


def test_status_bucket_unknown_status_preserves_legacy_text_behavior():
    assert normalize_status_bucket("  Beklemede  ") == "Beklemede"


def test_filter_by_derived_status_bucket(engine, data):
    data["contracts"] = [
        {"id": 1, "status": "Tamamlandı"},
        {"id": 2, "status": "Completed"},
        {"id": 3, "status": "Closed"},
        {"id": 4, "status": "Done"},
        {"id": 5, "status": "Devam Ediyor"},
    ]
    result = engine.execute(AnalysisDefinition(
        analysis_id="completed_contracts",
        title="Tamamlanan Sözleşmeler",
        dataset="contracts",
        visualization="kpi",
        filters=[FilterDefinition("status_bucket", "equals", "Tamamlanan")],
        measures=[MeasureDefinition("", "count_rows")],
    ), data)
    assert result.value == 4
    assert result.meta["filtered_row_count"] == 4


def test_group_by_derived_status_bucket(engine, data):
    data["contracts"] = [
        {"status": "Tamamlandı"},
        {"status": "Completed"},
        {"status": "Closed"},
        {"status": "Başlanmadı"},
        {"status": "Planlandı"},
        {"status": "Açık"},
        {"status": "In Progress"},
    ]
    result = engine.execute(AnalysisDefinition(
        analysis_id="status_groups",
        title="Durum Grupları",
        dataset="contracts",
        visualization="bar",
        dimensions=["status_bucket"],
        measures=[MeasureDefinition("", "count_rows")],
    ), data)
    assert {row["status_bucket"]: row["value"] for row in result.rows} == {
        "Tamamlanan": 3,
        "Başlanmadı": 2,
        "Devam ediyor": 2,
    }


def test_projection_includes_derived_status_bucket_without_mutating_source(engine, data):
    source_row = {"contract_no": "STS-001", "status": "Completed"}
    data["contracts"] = [source_row]
    result = engine.execute(projection_definition(
        select_fields=["contract_no", "status", "status_bucket"],
    ), data)
    assert result.rows == [{
        "contract_no": "STS-001",
        "status": "Completed",
        "status_bucket": "Tamamlanan",
    }]
    assert "status_bucket" not in source_row
    assert "status_bucket" not in data["contracts"][0]


def test_projection_sort_by_derived_status_bucket(engine, data):
    data["contracts"] = [
        {"contract_no": "3", "status": "Completed"},
        {"contract_no": "1", "status": "Open"},
        {"contract_no": "2", "status": "Planlandı"},
    ]
    result = engine.execute(projection_definition(
        select_fields=["contract_no", "status_bucket"],
        sort=[SortDefinition("status_bucket", "asc")],
    ), data)
    assert [row["status_bucket"] for row in result.rows] == [
        "Başlanmadı",
        "Devam ediyor",
        "Tamamlanan",
    ]


def test_count_distinct_can_aggregate_derived_status_bucket(engine, data):
    data["contracts"] = [
        {"status": "Tamamlandı"},
        {"status": "Completed"},
        {"status": "Open"},
        {"status": "Planlandı"},
    ]
    result = engine.execute(count_definition("status_bucket", "count_distinct"), data)
    assert result.value == 3


def _distribution_map(rows):
    return {row["label"]: row["value"] for row in rows}


def _generic_distribution_map(rows, dimension):
    return {row[dimension]: row["value"] for row in rows}


def test_contract_status_distribution_builtin_matches_legacy_metrics(engine, data):
    legacy = compute_metrics(data, today=date(2026, 7, 7))["status_distribution"]
    definition_ = get_builtin_analysis(
        "contract_status_distribution", today=date(2026, 7, 7), upcoming_days=60
    )
    assert definition_.dimensions == ["status_bucket"]
    generic = engine.execute(definition_, data)
    assert _generic_distribution_map(generic.rows, "status_bucket") == _distribution_map(legacy)


def test_acceptance_status_distribution_builtin_matches_legacy_metrics(engine, data):
    legacy = compute_metrics(data, today=date(2026, 7, 7))["acceptance_status_distribution"]
    definition_ = get_builtin_analysis(
        "acceptance_status_distribution", today=date(2026, 7, 7), upcoming_days=60
    )
    assert definition_.dimensions == ["status_bucket"]
    generic = engine.execute(definition_, data)
    assert _generic_distribution_map(generic.rows, "status_bucket") == _distribution_map(legacy)

from copy import deepcopy

from analysis_center.analysis_dashboard_service import DashboardCompositionError
from analysis_center.analysis_definitions import DashboardDefinition
from analysis_center.analysis_repository import MemoryAnalysisRepository
from analysis_center.analysis_service import AnalysisService


def dashboard_service(data):
    repository = MemoryAnalysisRepository()
    service = AnalysisService(use_sample=False, repository=repository)
    service.data = data
    return service, repository


def test_basic_dashboard_composition(data):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        dashboard_id="demo_dashboard",
        title="Demo Dashboard",
        analysis_ids=["total_contracts", "platform_distribution"],
        enabled=True,
        sort_order=10,
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7), upcoming_days=60)

    assert len(composition.analysis_results) == 2
    assert len(composition.cards) == 2
    assert composition.item.item_id == "demo_dashboard"
    assert composition.item.title == "Demo Dashboard"
    assert composition.item.enabled is True
    assert composition.item.sort_order == 10
    assert composition.item.cards == composition.cards


def test_dashboard_card_order_follows_analysis_ids(data):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        "ordered_dashboard",
        "Ordered Dashboard",
        analysis_ids=["platform_distribution", "total_contracts"],
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert [card.card_id for card in composition.cards] == ["platform_distribution", "total_contracts"]
    assert [card.sort_order for card in composition.cards] == [10, 20]
    assert [card["card_id"] for card in composition.item.to_dict()["cards"]] == [
        "platform_distribution",
        "total_contracts",
    ]


def test_repository_analysis_resolves_in_dashboard(data):
    service, repository = dashboard_service(data)
    repository.save_analysis(AnalysisDefinition(
        analysis_id="my_contract_count",
        title="Benim Sözleşme Sayım",
        dataset="contracts",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
    ))
    dashboard = DashboardDefinition(
        "custom_dashboard", "Custom Dashboard", analysis_ids=["my_contract_count"]
    )

    composition = service.compose_dashboard(dashboard)

    assert [card.card_id for card in composition.cards] == ["my_contract_count"]
    assert composition.cards[0].title == "Benim Sözleşme Sayım"
    assert composition.analysis_results[0].value == 3
    assert composition.meta["analysis_sources"] == {"my_contract_count": "repository"}


def test_repository_analysis_overrides_builtin(data):
    service, repository = dashboard_service(data)
    repository.save_analysis(AnalysisDefinition(
        analysis_id="total_contracts",
        title="Override Toplam",
        dataset="acceptances",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
    ))
    dashboard = DashboardDefinition(
        "override_dashboard", "Override Dashboard", analysis_ids=["total_contracts"]
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert composition.cards[0].title == "Override Toplam"
    assert composition.analysis_results[0].dataset == "acceptances"
    assert composition.analysis_results[0].value == 2
    assert composition.meta["analysis_sources"]["total_contracts"] == "repository"


def test_builtin_analysis_is_fallback_when_repository_has_no_match(data):
    service, repository = dashboard_service(data)
    assert repository.get_analysis("total_contracts") is None
    dashboard = DashboardDefinition(
        "builtin_dashboard", "Builtin Dashboard", analysis_ids=["total_contracts"]
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert composition.cards[0].card_id == "total_contracts"
    assert composition.analysis_results[0].value == 3
    assert composition.meta["analysis_sources"]["total_contracts"] == "builtin"


def test_missing_analysis_adds_warning_and_composition_continues(data):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        "warning_dashboard",
        "Warning Dashboard",
        analysis_ids=["total_contracts", "missing_analysis"],
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert [card.card_id for card in composition.cards] == ["total_contracts"]
    assert composition.warnings == ["dashboard analysis not found: missing_analysis"]
    assert composition.meta["warnings"] == composition.warnings
    assert composition.item.meta["composition"]["warnings"] == composition.warnings


def test_invalid_analysis_records_error_and_composition_continues(data):
    service, repository = dashboard_service(data)
    repository.save_analysis(AnalysisDefinition(
        analysis_id="invalid_analysis",
        title="Invalid Analysis",
        dataset="contracts",
        visualization="kpi",
        measures=[],
    ))
    dashboard = DashboardDefinition(
        "error_dashboard",
        "Error Dashboard",
        analysis_ids=["total_contracts", "invalid_analysis", "total_acceptances"],
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert [card.card_id for card in composition.cards] == ["total_contracts", "total_acceptances"]
    assert composition.errors == [{
        "analysis_id": "invalid_analysis",
        "error": "AnalysisEngine v1 tam olarak 1 measure destekler.",
    }]
    assert composition.meta["errors"] == composition.errors
    assert composition.item.meta["composition"]["errors"] == composition.errors


def test_duplicate_dashboard_analysis_reference_warns_and_uses_first_occurrence(data):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        "duplicate_dashboard",
        "Duplicate Dashboard",
        analysis_ids=["total_contracts", "total_contracts"],
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert [card.card_id for card in composition.cards] == ["total_contracts"]
    assert composition.warnings == ["duplicate dashboard analysis reference: total_contracts"]
    assert len(composition.analysis_results) == 1


def test_dashboard_item_preserves_layout_and_meta_as_safe_metadata(data):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        "metadata_dashboard",
        "Metadata Dashboard",
        analysis_ids=["total_contracts"],
        layout={"columns": 3, "gap": 12},
        meta={"owner": "analysis-team", "scope": "demo"},
    )

    composition = service.compose_dashboard(dashboard, today=date(2026, 7, 7))
    dashboard.layout["columns"] = 99
    dashboard.meta["owner"] = "changed"

    assert composition.item.meta["layout"] == {"columns": 3, "gap": 12}
    assert composition.item.meta["dashboard_meta"] == {"owner": "analysis-team", "scope": "demo"}
    assert composition.dashboard.layout == {"columns": 3, "gap": 12}
    assert composition.dashboard.meta == {"owner": "analysis-team", "scope": "demo"}


def test_compose_dashboard_by_repository_id(data):
    service, repository = dashboard_service(data)
    repository.save_dashboard(DashboardDefinition(
        "stored_dashboard",
        "Stored Dashboard",
        analysis_ids=["total_contracts", "total_acceptances"],
    ))

    composition = service.compose_dashboard_by_id("stored_dashboard", today=date(2026, 7, 7))

    assert composition.dashboard.dashboard_id == "stored_dashboard"
    assert [card.card_id for card in composition.cards] == ["total_contracts", "total_acceptances"]


def test_missing_dashboard_id_raises_controlled_error(data):
    service, _ = dashboard_service(data)

    with pytest.raises(DashboardCompositionError, match="Dashboard not found: missing_dashboard"):
        service.compose_dashboard_by_id("missing_dashboard")


def test_dashboard_composition_does_not_mutate_source_data(data):
    service, _ = dashboard_service(data)
    before = deepcopy(data)
    dashboard = DashboardDefinition(
        "immutable_source_dashboard",
        "Immutable Source Dashboard",
        analysis_ids=["contract_status_distribution", "platform_distribution"],
    )

    service.compose_dashboard(dashboard, today=date(2026, 7, 7))

    assert data == before


def test_unexpected_composition_exception_is_not_swallowed(data, monkeypatch):
    service, _ = dashboard_service(data)
    dashboard = DashboardDefinition(
        "unexpected_error_dashboard",
        "Unexpected Error Dashboard",
        analysis_ids=["total_contracts"],
    )

    def broken_execute(*args, **kwargs):
        raise RuntimeError("programmer bug")

    monkeypatch.setattr(service.engine, "execute", broken_execute)

    with pytest.raises(RuntimeError, match="programmer bug"):
        service.compose_dashboard(dashboard, today=date(2026, 7, 7))

from analysis_center.analysis_cards import build_dashboard_items
from analysis_center.analysis_dashboard import build_dashboard_payload
from analysis_center.analysis_metrics import compute_metrics
from analysis_center.analysis_models import CardSize, ChartType, VisualSettings
import analysis_center.analysis_cards as analysis_cards_module
from analysis_center.analysis_registry import DEFAULT_REGISTRY
from analysis_center.analysis_utils import is_acceptance_completed


_EXECUTIVE_CARD_IDS = [
    "exec_total_contracts",
    "exec_upcoming_deadlines",
    "exec_past_deadlines",
    "exec_completed_acceptances",
    "exec_status_distribution",
    "exec_upcoming_table",
]

_PLATFORM_CARD_IDS = [
    "platform_total",
    "platform_distribution",
    "platform_table",
]


def _item_by_id(items, item_id):
    return next(item for item in items if item.item_id == item_id)


def _card_by_id(item, card_id):
    return next(card for card in item.cards if card.card_id == card_id)


def _series_map(rows):
    return {str(row["label"]): row["value"] for row in rows}


def test_production_payload_executive_summary_is_hybrid():
    payload = build_dashboard_payload(use_sample=True)
    item = _item_by_id(payload["dashboard_items"], "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert [card.meta.get("analysis_id") for card in item.cards] == [
        "total_contracts",
        "upcoming_deadline_count",
        "past_deadline_count",
        "completed_acceptances",
        "contract_status_distribution",
        "upcoming_deadlines_table",
    ]


def test_executive_summary_exact_legacy_card_order(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert [card.sort_order for card in item.cards] == [10, 20, 30, 40, 50, 60]
    assert [card["card_id"] for card in item.to_dict()["cards"]] == _EXECUTIVE_CARD_IDS


def test_generic_executive_total_contracts_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_total_contracts")

    assert card.value == metrics["total_contracts"]
    assert card.meta["analysis_id"] == "total_contracts"


def test_generic_executive_upcoming_deadline_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_upcoming_deadlines")

    assert card.value == metrics["upcoming_deadline_count"]
    assert card.meta["analysis_id"] == "upcoming_deadline_count"


def test_generic_executive_past_deadline_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_past_deadlines")

    assert card.value == metrics["past_deadline_count"]
    assert card.meta["analysis_id"] == "past_deadline_count"


def test_generic_executive_status_distribution_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_status_distribution")

    assert _series_map(card.data) == _series_map(metrics["status_distribution"])
    assert card.meta["analysis_id"] == "contract_status_distribution"


def test_generic_completed_acceptance_card_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_completed_acceptances")

    assert card.value == metrics["completed_acceptances"]
    assert card.title == "Tamamlanan Teslimat"
    assert card.size == CardSize.SMALL
    assert card.meta["analysis_id"] == "completed_acceptances"


def test_generic_upcoming_table_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_upcoming_table")

    assert card.columns == ["platform", "contract_no", "entity", "name", "due_date", "days", "status"]
    assert card.data == metrics["upcoming_deadlines"]
    assert card.size == CardSize.WIDE
    assert card.title == "Yaklaşan Termin Listesi"
    assert card.meta["analysis_id"] == "upcoming_deadlines_table"


def test_executive_summary_preserves_legacy_ids_titles_sizes_and_chart_type(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert [card.title for card in item.cards] == [
        "Toplam Sözleşme",
        "Yaklaşan Termin",
        "Geçmiş Termin",
        "Tamamlanan Teslimat",
        "Durum Dağılımı",
        "Yaklaşan Termin Listesi",
    ]
    assert [card.size for card in item.cards] == [
        CardSize.SMALL,
        CardSize.SMALL,
        CardSize.SMALL,
        CardSize.SMALL,
        CardSize.MEDIUM,
        CardSize.WIDE,
    ]
    assert _card_by_id(item, "exec_status_distribution").chart_type == ChartType.DONUT
    assert all(card.card_id not in {
        "total_contracts",
        "upcoming_deadline_count",
        "past_deadline_count",
        "contract_status_distribution",
        "completed_acceptances",
        "upcoming_deadlines_table",
    } for card in item.cards)


def test_build_dashboard_items_without_data_keeps_legacy_executive_fallback(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics), "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert all("analysis_id" not in card.meta for card in item.cards)
    assert _card_by_id(item, "exec_total_contracts").value == metrics["total_contracts"]


def test_hybrid_falls_back_to_legacy_on_controlled_composition_error(data, monkeypatch, caplog):
    metrics = compute_metrics(data, today=date(2026, 7, 7))

    def controlled_failure(*args, **kwargs):
        raise DashboardCompositionError("controlled composition failure")

    monkeypatch.setattr(analysis_cards_module.AnalysisService, "compose_dashboard", controlled_failure)
    with caplog.at_level("WARNING", logger="analysis_center.analysis_cards"):
        item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert all("analysis_id" not in card.meta for card in item.cards)
    assert "legacy fallback kullanılacak" in caplog.text
    assert "controlled composition failure" in caplog.text


def test_hybrid_does_not_swallow_unexpected_programmer_error(data, monkeypatch):
    metrics = compute_metrics(data, today=date(2026, 7, 7))

    def programmer_bug(*args, **kwargs):
        raise RuntimeError("programmer bug")

    monkeypatch.setattr(analysis_cards_module.AnalysisService, "compose_dashboard", programmer_bug)

    with pytest.raises(RuntimeError, match="programmer bug"):
        build_dashboard_items(metrics, data=data)


def test_other_dashboard_items_are_unchanged_by_executive_hybrid_migration(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    legacy_items = build_dashboard_items(metrics)
    hybrid_items = build_dashboard_items(metrics, data=data)
    untouched_ids = [
        "platform_analysis",
        "contract_analysis",
        "acceptance_analysis",
        "deadline_analysis",
    ]

    legacy_snapshot = {
        item_id: (
            _item_by_id(legacy_items, item_id).title,
            [card.card_id for card in _item_by_id(legacy_items, item_id).cards],
        )
        for item_id in untouched_ids
    }
    hybrid_snapshot = {
        item_id: (
            _item_by_id(hybrid_items, item_id).title,
            [card.card_id for card in _item_by_id(hybrid_items, item_id).cards],
        )
        for item_id in untouched_ids
    }

    assert hybrid_snapshot == legacy_snapshot


def test_platform_generic_subset_dashboard_definition_is_scoped():
    dashboard = analysis_cards_module._PLATFORM_ANALYSIS_GENERIC_DASHBOARD

    assert dashboard.dashboard_id == "platform_analysis_generic"
    assert dashboard.title == "Platform Analizi"
    assert dashboard.analysis_ids == ["total_platforms", "platform_distribution"]


def test_total_platforms_builtin_uses_platform_row_count(engine):
    definition_ = get_builtin_analysis("total_platforms")
    custom = {"platforms": [{"id": 1}, {"id": 2}, {"id": 3}]}

    assert definition_.dataset == "platforms"
    assert definition_.visualization == "kpi"
    assert definition_.measures == [MeasureDefinition(field="", aggregation="count_rows", alias="value")]
    assert engine.execute(definition_, custom).value == 3
    assert engine.execute(definition_, {"platforms": []}).value == 0


def test_platform_distribution_builtin_matches_legacy_metrics_including_missing_bucket(engine):
    custom = {
        "contracts": [
            {"id": 1, "platform": "AKINCI"},
            {"id": 2, "platform": ""},
            {"id": 3, "platform": None},
            {"id": 4, "platform": " AKINCI "},
        ]
    }
    legacy = compute_metrics(custom, today=date(2026, 7, 7))["platform_distribution"]
    definition_ = get_builtin_analysis("platform_distribution")
    generic = engine.execute(definition_, custom)

    assert definition_.dimensions == ["platform_bucket"]
    assert _generic_distribution_map(generic.rows, "platform_bucket") == _distribution_map(legacy)
    assert _generic_distribution_map(generic.rows, "platform_bucket") == {
        "AKINCI": 2,
        "Eksik platform": 2,
    }


def test_production_platform_analysis_is_hybrid():
    payload = build_dashboard_payload(use_sample=True)
    item = _item_by_id(payload["dashboard_items"], "platform_analysis")
    serialized_item = next(row for row in payload["dashboard"] if row["item_id"] == "platform_analysis")

    assert [card.card_id for card in item.cards] == _PLATFORM_CARD_IDS
    assert [card.sort_order for card in item.cards] == [10, 20, 30]
    assert [card["card_id"] for card in serialized_item["cards"]] == _PLATFORM_CARD_IDS
    assert _card_by_id(item, "platform_total").meta["analysis_id"] == "total_platforms"
    assert _card_by_id(item, "platform_distribution").meta["analysis_id"] == "platform_distribution"
    assert "analysis_id" not in _card_by_id(item, "platform_table").meta


def test_platform_generic_cards_preserve_legacy_visible_behavior(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics, data=data), "platform_analysis")
    total = _card_by_id(item, "platform_total")
    distribution = _card_by_id(item, "platform_distribution")

    assert total.title == "Platform Sayısı"
    assert total.card_type == CardType.KPI
    assert total.size == CardSize.SMALL
    assert total.value == metrics["total_platforms"]
    assert total.meta["analysis_id"] == "total_platforms"

    assert distribution.title == "Platform Dağılımı"
    assert distribution.card_type == CardType.CHART
    assert distribution.chart_type == ChartType.HORIZONTAL_BAR
    assert distribution.size == CardSize.LARGE
    assert _series_map(distribution.data) == _series_map(metrics["platform_distribution"])
    assert distribution.meta["analysis_id"] == "platform_distribution"


def test_platform_table_remains_exact_legacy_card(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    settings = VisualSettings(max_table_rows=1, show_disabled_sections=False)
    item = _item_by_id(build_dashboard_items(metrics, settings=settings, data=data), "platform_analysis")
    card = _card_by_id(item, "platform_table")

    assert card.title == "Platform Tablosu"
    assert card.card_type == CardType.TABLE
    assert card.size == CardSize.WIDE
    assert card.sort_order == 30
    assert card.columns == [
        "platform",
        "contract_count",
        "completed_contract_count",
        "acceptance_count",
        "completed_acceptance_count",
    ]
    assert card.data == metrics["platform_table"][:1]
    assert "analysis_id" not in card.meta


def test_build_dashboard_items_without_data_keeps_legacy_platform_fallback(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    item = _item_by_id(build_dashboard_items(metrics), "platform_analysis")

    assert [card.card_id for card in item.cards] == _PLATFORM_CARD_IDS
    assert all("analysis_id" not in card.meta for card in item.cards)
    assert _card_by_id(item, "platform_total").value == metrics["total_platforms"]
    assert _series_map(_card_by_id(item, "platform_distribution").data) == _series_map(metrics["platform_distribution"])


def test_platform_hybrid_falls_back_fully_on_controlled_composition_error(data, monkeypatch, caplog):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    original_compose = analysis_cards_module.AnalysisService.compose_dashboard

    def controlled_platform_failure(self, dashboard, *args, **kwargs):
        if dashboard.dashboard_id == "platform_analysis_generic":
            raise DashboardCompositionError("platform controlled composition failure")
        return original_compose(self, dashboard, *args, **kwargs)

    monkeypatch.setattr(analysis_cards_module.AnalysisService, "compose_dashboard", controlled_platform_failure)
    with caplog.at_level("WARNING", logger="analysis_center.analysis_cards"):
        item = _item_by_id(build_dashboard_items(metrics, data=data), "platform_analysis")

    assert [card.card_id for card in item.cards] == _PLATFORM_CARD_IDS
    assert all("analysis_id" not in card.meta for card in item.cards)
    assert "Platform Analizi generic composition başarısız" in caplog.text
    assert "platform controlled composition failure" in caplog.text


def test_platform_hybrid_does_not_swallow_unexpected_programmer_error(data, monkeypatch):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    original_compose = analysis_cards_module.AnalysisService.compose_dashboard

    def platform_programmer_bug(self, dashboard, *args, **kwargs):
        if dashboard.dashboard_id == "platform_analysis_generic":
            raise RuntimeError("platform programmer bug")
        return original_compose(self, dashboard, *args, **kwargs)

    monkeypatch.setattr(analysis_cards_module.AnalysisService, "compose_dashboard", platform_programmer_bug)

    with pytest.raises(RuntimeError, match="platform programmer bug"):
        build_dashboard_items(metrics, data=data)


def test_platform_hybrid_does_not_mutate_normalized_data(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    before = deepcopy(data)

    build_dashboard_items(metrics, data=data)

    assert data == before


def test_non_platform_dashboard_snapshots_are_unchanged_by_platform_migration(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    legacy_items = build_dashboard_items(metrics)
    hybrid_items = build_dashboard_items(metrics, data=data)
    untouched_ids = [
        "contract_analysis",
        "acceptance_analysis",
        "deadline_analysis",
    ]

    for item_id in untouched_ids:
        legacy = _item_by_id(legacy_items, item_id)
        hybrid = _item_by_id(hybrid_items, item_id)
        assert (hybrid.title, [card.card_id for card in hybrid.cards]) == (
            legacy.title,
            [card.card_id for card in legacy.cards],
        )

    executive = _item_by_id(hybrid_items, "executive_summary")
    assert [card.card_id for card in executive.cards] == _EXECUTIVE_CARD_IDS
    assert all(card.meta.get("analysis_id") for card in executive.cards)


def test_acceptances_completed_registry_metadata():
    field = DEFAULT_REGISTRY.get_field("acceptances", "completed")

    assert field.derived is True
    assert field.field_type == "boolean"
    assert field.filterable is True
    assert field.groupable is True
    assert field.aggregatable is True
    assert field.sortable is True
    assert field.allowed_aggregations == ("count", "count_distinct")


def test_completed_acceptance_domain_cases_match_shared_helper(engine):
    rows = [
        {"id": 1, "status": "Completed", "acceptance_date": "", "planned_total": 10, "delivered_total": 0},
        {"id": 2, "status": "Open", "acceptance_date": "2026-01-01", "planned_total": 10, "delivered_total": 0},
        {"id": 3, "status": "Open", "acceptance_date": "", "planned_total": 10, "delivered_total": 10},
        {"id": 4, "status": "Open", "acceptance_date": "", "planned_total": 10, "delivered_total": 12},
        {"id": 5, "status": "Open", "acceptance_date": "", "planned_total": 10, "delivered_total": 9},
        {"id": 6, "status": "Open", "acceptance_date": "", "planned_total": 0, "delivered_total": 0},
    ]
    custom = {"acceptances": rows}

    resolved = [DEFAULT_REGISTRY.resolve_value("acceptances", "completed", row) for row in rows]

    assert resolved == [is_acceptance_completed(row) for row in rows]
    assert resolved == [True, True, True, True, False, False]

    result = engine.execute(get_builtin_analysis("completed_acceptances"), custom)
    assert result.value == 4
    assert result.value == compute_metrics(custom, today=date(2026, 7, 7))["completed_acceptances"]


def test_completed_acceptances_builtin_matches_legacy_metric(engine, data):
    metrics = compute_metrics(data, today=date(2026, 7, 7))
    result = engine.execute(get_builtin_analysis("completed_acceptances"), data)

    assert result.value == metrics["completed_acceptances"]


def test_upcoming_deadlines_table_builtin_projection_matches_legacy_metric(engine, data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    definition = get_builtin_analysis("upcoming_deadlines_table", today=date(2026, 7, 7), upcoming_days=60)
    composition_data = {key: [dict(row) for row in rows] for key, rows in data.items()}
    composition_data["deadlines"] = [dict(row) for row in metrics["all_deadlines"]]

    assert definition.visualization == "table"
    assert definition.measures == []
    assert definition.dimensions == []
    assert definition.select_fields == ["platform", "contract_no", "entity", "name", "due_date", "days", "status"]

    result = engine.execute(definition, composition_data)

    assert result.columns == ["platform", "contract_no", "entity", "name", "due_date", "days", "status"]
    assert result.rows == metrics["upcoming_deadlines"]


def test_executive_summary_six_cards_are_generic(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert [card.meta.get("analysis_id") for card in item.cards] == [
        "total_contracts",
        "upcoming_deadline_count",
        "past_deadline_count",
        "completed_acceptances",
        "contract_status_distribution",
        "upcoming_deadlines_table",
    ]


def test_upcoming_table_projection_contains_only_expected_fields(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")
    card = _card_by_id(item, "exec_upcoming_table")

    assert card.columns == ["platform", "contract_no", "entity", "name", "due_date", "days", "status"]
    assert all(list(row.keys()) == card.columns for row in card.data)


def test_upcoming_table_order_matches_legacy_metric(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert _card_by_id(item, "exec_upcoming_table").data == metrics["upcoming_deadlines"]


def test_executive_upcoming_table_respects_max_table_rows(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    settings = VisualSettings(max_table_rows=1, show_disabled_sections=False)
    item = _item_by_id(build_dashboard_items(metrics, settings=settings, data=data), "executive_summary")
    card = _card_by_id(item, "exec_upcoming_table")

    assert len(card.data) == 1
    assert card.data == metrics["upcoming_deadlines"][:1]


def test_executive_kpi_and_table_count_consistency_without_limit(data):
    metrics = compute_metrics(data, today=date(2026, 7, 7), upcoming_days=60)
    settings = VisualSettings(max_table_rows=100, show_disabled_sections=False)
    item = _item_by_id(build_dashboard_items(metrics, settings=settings, data=data), "executive_summary")

    assert _card_by_id(item, "exec_upcoming_deadlines").value == len(_card_by_id(item, "exec_upcoming_table").data)


def test_fallback_still_uses_legacy_cards_without_generic_metadata(data, monkeypatch, caplog):
    metrics = compute_metrics(data, today=date(2026, 7, 7))

    def controlled_failure(*args, **kwargs):
        raise DashboardCompositionError("controlled composition failure")

    monkeypatch.setattr(analysis_cards_module.AnalysisService, "compose_dashboard", controlled_failure)
    with caplog.at_level("WARNING", logger="analysis_center.analysis_cards"):
        item = _item_by_id(build_dashboard_items(metrics, data=data), "executive_summary")

    assert [card.card_id for card in item.cards] == _EXECUTIVE_CARD_IDS
    assert all("analysis_id" not in card.meta for card in item.cards)
    assert "legacy fallback kullanılacak" in caplog.text


def test_payload_reuses_executive_builtin_results_for_generic_sidecar(monkeypatch):
    from collections import Counter

    original_execute = AnalysisEngine.execute
    execution_counts = Counter()

    def counted_execute(self, definition, execution_data):
        execution_counts[definition.analysis_id] += 1
        return original_execute(self, definition, execution_data)

    monkeypatch.setattr(AnalysisEngine, "execute", counted_execute)

    payload = build_dashboard_payload(use_sample=True)

    reused_builtin_ids = {
        "total_contracts",
        "upcoming_deadline_count",
        "past_deadline_count",
        "completed_acceptances",
        "contract_status_distribution",
        "total_platforms",
        "platform_distribution",
    }
    for analysis_id in reused_builtin_ids:
        assert execution_counts[analysis_id] == 1

    # Executive table uses a repository override with limit/enriched deadline rows;
    # canonical sidecar execution remains separate because it is not the same request.
    assert execution_counts["upcoming_deadlines_table"] == 2
    assert sum(execution_counts.values()) == 11
    assert set(execution_counts) == set(payload["generic_analysis_results"])


def test_generic_sidecar_cards_keep_generic_identity_after_executive_reuse():
    payload = build_dashboard_payload(use_sample=True)
    executive = _item_by_id(payload["dashboard_items"], "executive_summary")

    assert _card_by_id(executive, "exec_total_contracts").meta["analysis_id"] == "total_contracts"
    assert payload["generic_analysis_cards"]["total_contracts"]["card_id"] == "total_contracts"
    assert payload["generic_analysis_cards"]["contract_status_distribution"]["card_id"] == "contract_status_distribution"


def test_canonical_table_sidecar_is_not_replaced_by_limited_executive_override():
    settings = VisualSettings(max_table_rows=1, show_disabled_sections=False)
    payload = build_dashboard_payload(settings=settings, use_sample=True)
    executive = _item_by_id(payload["dashboard_items"], "executive_summary")
    executive_rows = _card_by_id(executive, "exec_upcoming_table").data
    sidecar_rows = payload["generic_analysis_results"]["upcoming_deadlines_table"]["rows"]

    assert len(executive_rows) == 1
    assert len(sidecar_rows) > len(executive_rows)


def test_builtin_deadline_filters_ignore_flexible_tbd_dates(engine, data):
    data["deadlines"].append({
        "entity": "acceptance",
        "platform": "AKINCI",
        "contract_no": "TBD-1",
        "name": "Esnek Termin",
        "due_date": "2026-07-TBD",
        "status": "Plan",
    })
    definition_ = get_builtin_analysis(
        "upcoming_deadlines_table",
        today=date(2026, 7, 7),
        upcoming_days=60,
    )

    result = engine.execute(definition_, data)

    assert all(row["contract_no"] != "TBD-1" for row in result.rows)


def test_invalid_expected_date_filter_still_raises(engine, data):
    definition_ = projection_definition(
        filters=[FilterDefinition("completion_date", "greater_than", "TBD")],
    )
    with pytest.raises(AnalysisValidationError, match="geçersiz tarih değeri"):
        engine.execute(definition_, data)
