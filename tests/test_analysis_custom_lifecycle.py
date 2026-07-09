from __future__ import annotations

from copy import deepcopy

import pytest

from analysis_center.analysis_builder import AnalysisBuilderController, builder_filter_draft_from_definition
from analysis_center.analysis_custom_library import CustomAnalysisLibraryController
from analysis_center.analysis_definitions import (
    AnalysisDefinition,
    AnalysisValidationError,
    FilterDefinition,
    MeasureDefinition,
    SortDefinition,
)
from analysis_center.analysis_repository import MemoryAnalysisRepository
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService, new_custom_analysis_id


@pytest.fixture
def service():
    active = AnalysisService(use_sample=True, repository=MemoryAnalysisRepository())
    active.data = build_sample_data()
    return active


def kpi(analysis_id="preview-test", title="KPI"):
    return AnalysisDefinition(
        analysis_id=analysis_id,
        title=title,
        dataset="contracts",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
    )


def test_new_custom_ids_have_prefix_and_are_unique():
    first = new_custom_analysis_id()
    second = new_custom_analysis_id()
    assert first.startswith("custom-")
    assert second.startswith("custom-")
    assert first != second


def test_create_update_copy_delete_lifecycle(service):
    created = service.create_saved_analysis(kpi(title="Original"))
    assert created.analysis_id.startswith("custom-")
    assert service.get_saved_analysis(created.analysis_id).title == "Original"

    edited = deepcopy(created)
    edited.title = "Edited"
    updated = service.update_saved_analysis(edited, created.analysis_id)
    assert updated.analysis_id == created.analysis_id
    assert service.get_saved_analysis(created.analysis_id).title == "Edited"
    assert len(service.list_saved_analyses()) == 1

    copied = service.copy_saved_analysis(created.analysis_id)
    assert copied.analysis_id != created.analysis_id
    assert copied.title == "Edited Kopya"
    assert copied.dataset == updated.dataset
    assert copied.visualization == updated.visualization
    assert copied.measures == updated.measures
    assert len(service.list_saved_analyses()) == 2

    assert service.delete_saved_analysis(copied.analysis_id) is True
    assert service.get_saved_analysis(created.analysis_id) is not None
    assert service.get_saved_analysis(copied.analysis_id) is None


def test_copy_title_suffix_collisions_are_deterministic(service):
    created = service.create_saved_analysis(kpi(title="Analiz"))
    first = service.copy_saved_analysis(created.analysis_id)
    second = service.copy_saved_analysis(created.analysis_id)
    third = service.copy_saved_analysis(created.analysis_id)
    assert [first.title, second.title, third.title] == [
        "Analiz Kopya",
        "Analiz Kopya (2)",
        "Analiz Kopya (3)",
    ]


def test_update_missing_saved_analysis_is_controlled(service):
    with pytest.raises(AnalysisValidationError, match="artık mevcut değil"):
        service.update_saved_analysis(kpi(), "custom-missing")


def test_registry_invalid_saved_analysis_validation_status_and_preview_reject(service):
    invalid = AnalysisDefinition(
        analysis_id="custom-invalid",
        title="Stale",
        dataset="missing_dataset",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
    )
    service.repository.save_analysis(invalid)
    assert service.saved_analysis_validation_error(invalid) is not None
    library = CustomAnalysisLibraryController(service)
    item = library.list_items()[0]
    assert item.is_valid is False
    assert item.dataset_title == "Bilinmeyen Veri Kaynağı"
    with pytest.raises(AnalysisValidationError):
        library.preview(invalid.analysis_id)
    with pytest.raises(AnalysisValidationError):
        library.copy(invalid.analysis_id)
    assert library.delete(invalid.analysis_id) is True


def test_library_summary_uses_registry_titles_not_technical_ids(service):
    definition = AnalysisDefinition(
        analysis_id="custom-chart",
        title="Teslimatlar",
        dataset="acceptances",
        visualization="horizontal_bar",
        dimensions=["platform"],
        measures=[MeasureDefinition("", "count_rows")],
    )
    service.repository.save_analysis(definition)
    item = CustomAnalysisLibraryController(service).list_items()[0]
    assert item.dataset_title == "Teslimatlar / Kabuller"
    assert item.visualization_title == "Yatay Çubuk"
    assert "Platform" in item.summary
    assert "Kayıt Sayısı" in item.summary
    assert "acceptances" not in item.dataset_title
    assert "horizontal_bar" not in item.visualization_title


def _round_trip(service, definition: AnalysisDefinition):
    controller = AnalysisBuilderController(service)
    controller.load_definition(definition)
    assert controller.current_saved_analysis_id == definition.analysis_id
    assert controller.dirty is False
    rebuilt = controller.build_definition()
    assert rebuilt.to_dict() == definition.to_dict()
    return controller


@pytest.mark.parametrize(
    "definition",
    [
        AnalysisDefinition(
            "custom-kpi-count", "Count", "contracts", "kpi",
            measures=[MeasureDefinition("", "count_rows")], options={"x": 1},
        ),
        AnalysisDefinition(
            "custom-kpi-sum", "Sum", "acceptances", "kpi",
            measures=[MeasureDefinition("planned_total", "sum")],
        ),
        AnalysisDefinition(
            "custom-chart-count", "Chart", "acceptances", "bar",
            dimensions=["platform"], measures=[MeasureDefinition("", "count_rows")],
            sort=[SortDefinition("value", "desc")], limit=20,
        ),
        AnalysisDefinition(
            "custom-chart-sum", "Chart Sum", "acceptances", "horizontal_bar",
            dimensions=["platform"], measures=[MeasureDefinition("planned_total", "sum")],
            sort=[SortDefinition("platform", "asc")], limit=10,
        ),
        AnalysisDefinition(
            "custom-table", "Table", "acceptances", "table",
            select_fields=["platform", "name", "planned_total"],
            sort=[SortDefinition("planned_total", "desc")], limit=5,
        ),
    ],
)
def test_definition_to_draft_round_trip_core_shapes(service, definition):
    _round_trip(service, definition)


@pytest.mark.parametrize(
    "filter_definition",
    [
        FilterDefinition("platform", "equals", "AKINCI"),
        FilterDefinition("id", "greater_than", 10),
        FilterDefinition("planned_total", "between", [5.5, 12.5]),
        FilterDefinition("completed", "equals", True),
        FilterDefinition("planned_acceptance_date", "equals", "2026-07-09"),
        FilterDefinition("platform", "in", ["AKINCI", "TB2"]),
        FilterDefinition("platform", "not_in", ["AKINCI", "TB2"]),
        FilterDefinition("platform", "is_empty", None),
    ],
)
def test_filter_hydration_round_trip(service, filter_definition):
    definition = AnalysisDefinition(
        analysis_id="custom-filter",
        title="Filter",
        dataset="acceptances",
        visualization="table",
        filters=[filter_definition],
        select_fields=["platform", "name"],
        limit=20,
    )
    controller = _round_trip(service, definition)
    raw = controller.draft.filters[0]
    hydrated = builder_filter_draft_from_definition(filter_definition)
    assert raw == hydrated


def test_unsupported_builder_visualization_rejected(service):
    controller = AnalysisBuilderController(service)
    with pytest.raises(AnalysisValidationError, match="desteklenmeyen görünüm"):
        controller.load_definition(
            AnalysisDefinition(
                "custom-status", "Status", "contracts", "status",
                measures=[MeasureDefinition("", "count_rows")],
            )
        )


def test_two_dimensions_and_two_measures_rejected_for_edit_hydration(service):
    controller = AnalysisBuilderController(service)
    with pytest.raises(AnalysisValidationError, match="gruplama yapısı"):
        controller.load_definition(
            AnalysisDefinition(
                "custom-2d", "Two D", "contracts", "bar",
                dimensions=["platform", "status"],
                measures=[MeasureDefinition("", "count_rows")],
            )
        )
    with pytest.raises(AnalysisValidationError, match="hesaplama yapısı"):
        controller.load_definition(
            AnalysisDefinition(
                "custom-2m", "Two M", "contracts", "bar",
                dimensions=["platform"],
                measures=[
                    MeasureDefinition("", "count_rows"),
                    MeasureDefinition("id", "count"),
                ],
            )
        )


def test_projection_sort_not_selected_keeps_engine_validation_source_of_truth(service):
    controller = AnalysisBuilderController(service)
    definition = AnalysisDefinition(
        "custom-table-invalid", "Invalid Table", "acceptances", "table",
        select_fields=["platform", "name"],
        sort=[SortDefinition("planned_total", "desc")],
    )
    with pytest.raises(AnalysisValidationError, match="projection sort field"):
        controller.load_definition(definition)


def test_builder_new_saved_clean_dirty_and_preview_state(service):
    controller = AnalysisBuilderController(service)
    assert controller.current_saved_analysis_id is None
    assert controller.dirty is True
    definition, _result = controller.preview()
    assert definition.analysis_id.startswith("preview-")
    assert controller.dirty is True

    saved = controller.save_current()
    assert saved.analysis_id.startswith("custom-")
    assert controller.current_saved_analysis_id == saved.analysis_id
    assert controller.draft.analysis_id == saved.analysis_id
    assert controller.dirty is False

    controller.mark_changed()
    assert controller.dirty is True
    controller.save_current()
    assert controller.current_saved_analysis_id == saved.analysis_id
    assert controller.dirty is False


def test_load_saved_definition_is_clean_and_all_controller_mutations_mark_dirty(service):
    saved = service.create_saved_analysis(kpi(title="Saved"))
    controller = AnalysisBuilderController(service)
    controller.load_definition(saved)
    assert controller.dirty is False
    controller.set_dataset("acceptances")
    assert controller.dirty is True

    controller.load_definition(saved)
    controller.set_visualization("bar")
    assert controller.dirty is True

    chart = AnalysisDefinition(
        saved.analysis_id, "Chart", "acceptances", "bar",
        dimensions=["platform"], measures=[MeasureDefinition("", "count_rows")],
    )
    controller.load_definition(chart)
    controller.set_aggregation("sum")
    assert controller.dirty is True

    controller.load_definition(chart)
    controller.add_filter()
    assert controller.dirty is True

    controller.load_definition(chart)
    filter_draft = controller.add_filter()
    controller.dirty = False
    controller.remove_filter(filter_draft)
    assert controller.dirty is True


def test_copy_preserves_filters_sort_limit_and_options(service):
    source = AnalysisDefinition(
        analysis_id="custom-rich",
        title="Rich",
        dataset="acceptances",
        visualization="horizontal_bar",
        dimensions=["platform"],
        measures=[MeasureDefinition("planned_total", "sum")],
        filters=[FilterDefinition("platform", "in", ["AKINCI", "TB2"])],
        sort=[SortDefinition("value", "desc")],
        limit=10,
        options={"note": "kept"},
    )
    service.repository.save_analysis(source)
    copied = service.copy_saved_analysis(source.analysis_id)
    expected = source.to_dict()
    actual = copied.to_dict()
    expected.pop("analysis_id")
    expected.pop("title")
    actual.pop("analysis_id")
    actual.pop("title")
    assert actual == expected


def test_repository_error_propagates_from_service_and_builder_draft_is_preserved(tmp_path):
    from analysis_center.analysis_repository import AnalysisRepositoryCorruptError, FileAnalysisRepository

    repo = FileAnalysisRepository("source.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("broken", encoding="utf-8")
    protected = FileAnalysisRepository("source.sts", tmp_path)
    active = AnalysisService(use_sample=True, repository=protected)
    active.data = build_sample_data()
    controller = AnalysisBuilderController(active)
    draft_id = controller.draft.analysis_id
    draft_title = controller.draft.title
    with pytest.raises(AnalysisRepositoryCorruptError):
        controller.save_current()
    assert controller.draft.analysis_id == draft_id
    assert controller.draft.title == draft_title
    assert controller.current_saved_analysis_id is None
    assert controller.dirty is True
