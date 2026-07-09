from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from analysis_center.analysis_builder import AnalysisBuilderController
from analysis_center.analysis_builtin import get_builtin_analysis
from analysis_center.analysis_cards import (
    get_builtin_analysis_for_prepared_card,
    get_builtin_analysis_id_for_prepared_card,
)
from analysis_center.analysis_dashboard import build_dashboard_payload
from analysis_center.analysis_definitions import (
    AnalysisDefinition,
    AnalysisValidationError,
    MeasureDefinition,
)
from analysis_center.analysis_models import (
    AnalysisCard,
    AnalysisEntity,
    CardType,
    VisualSettings,
)
from analysis_center.analysis_repository import MemoryAnalysisRepository
from analysis_center.analysis_service import AnalysisService
from analysis_center.analysis_visual_settings import AnalysisVisualSettings


def _sample_payload():
    return build_dashboard_payload(
        settings=VisualSettings(
            show_disabled_sections=False,
            empty_state_uses_sample=True,
            upcoming_days=60,
        ),
        use_sample=True,
    )


def _prepared_card(screen_id: str, card_id: str) -> AnalysisCard:
    payload = _sample_payload()
    for item in payload["dashboard_items"]:
        if item.item_id != screen_id:
            continue
        for card in item.cards:
            if card.card_id == card_id:
                return card
    raise AssertionError(f"Prepared card not found: {screen_id}/{card_id}")


def _controller(repository=None) -> AnalysisBuilderController:
    service = AnalysisService(use_sample=True, repository=repository or MemoryAnalysisRepository())
    service.refresh_data()
    return AnalysisBuilderController(service)


def _without_identity(definition: AnalysisDefinition) -> dict:
    payload = definition.to_dict()
    payload.pop("analysis_id", None)
    return payload


def test_prepared_card_mapping_uses_explicit_identity_catalog_without_title_fallback():
    assert (
        get_builtin_analysis_id_for_prepared_card("executive_summary", "exec_total_contracts")
        == "total_contracts"
    )
    assert (
        get_builtin_analysis_id_for_prepared_card("executive_summary", "exec_status_distribution")
        == "contract_status_distribution"
    )
    assert (
        get_builtin_analysis_id_for_prepared_card("platform_analysis", "platform_total")
        == "total_platforms"
    )
    assert (
        get_builtin_analysis_id_for_prepared_card("platform_analysis", "platform_distribution")
        == "platform_distribution"
    )
    assert get_builtin_analysis_id_for_prepared_card("contract_analysis", "contract_total") is None
    assert get_builtin_analysis_id_for_prepared_card("executive_summary", "Toplam Sözleşme") is None


def test_legacy_card_with_compatible_visible_id_is_not_treated_as_builtin_backed():
    legacy = AnalysisCard(
        card_id="exec_total_contracts",
        title="Toplam Sözleşme",
        entity=AnalysisEntity.CONTRACT,
        card_type=CardType.KPI,
        screen_id="executive_summary",
    )
    assert get_builtin_analysis_for_prepared_card(legacy) is None


def test_real_generic_prepared_card_resolves_the_backing_builtin_definition():
    card = _prepared_card("platform_analysis", "platform_distribution")
    definition = get_builtin_analysis_for_prepared_card(card)
    assert definition is not None
    assert definition.analysis_id == "platform_distribution"
    assert definition.dataset == "contracts"
    assert definition.dimensions == ["platform_bucket"]


def test_date_dependent_prepared_template_uses_injected_today_and_upcoming_window():
    card = _prepared_card("executive_summary", "exec_upcoming_deadlines")
    definition = get_builtin_analysis_for_prepared_card(
        card,
        today=date(2026, 7, 8),
        upcoming_days=14,
    )
    assert definition is not None
    assert definition.analysis_id == "upcoming_deadline_count"
    assert [item.to_dict() for item in definition.filters] == [
        {"field": "due_date", "operator": "greater_than_or_equal", "value": "2026-07-08"},
        {"field": "due_date", "operator": "less_than_or_equal", "value": "2026-07-22"},
        {
            "field": "status",
            "operator": "not_in",
            "value": [
                "closed",
                "completed",
                "done",
                "kabul edildi",
                "kapatildi",
                "kapatıldı",
                "tamam",
                "tamamlandi",
                "tamamlandı",
            ],
        },
    ]


def test_load_template_hydrates_supported_builtin_as_new_dirty_preview_draft():
    controller = _controller()
    builtin = get_builtin_analysis("platform_distribution")
    before = deepcopy(builtin.to_dict())

    draft = controller.load_template(builtin)

    assert draft.analysis_id.startswith("preview-")
    assert draft.analysis_id != builtin.analysis_id
    assert controller.current_saved_analysis_id is None
    assert controller.dirty is True
    assert draft.title == builtin.title
    assert draft.dataset_id == builtin.dataset
    assert draft.visualization == builtin.visualization
    assert draft.group_field == builtin.dimensions[0]
    assert draft.aggregation == builtin.measures[0].aggregation
    assert draft.measure_field == builtin.measures[0].field
    assert draft.sort_field == builtin.sort[0].field
    assert draft.sort_direction == builtin.sort[0].direction
    assert draft.limit == builtin.limit
    assert draft.options == builtin.options
    assert builtin.to_dict() == before
    assert _without_identity(controller.build_definition()) == _without_identity(builtin)


def test_load_template_preserves_filters_and_visual_settings_without_mutating_source():
    controller = _controller()
    visual = AnalysisVisualSettings.defaults()
    visual.replace_chart(palette="pastel", legend_position="bottom", show_values=True)
    options = visual.to_options({"size": "large", "future_option": {"keep": True}})
    chart_template = replace(get_builtin_analysis("platform_distribution"), options=options)
    chart_before = deepcopy(chart_template.to_dict())

    controller.load_template(chart_template)
    rebuilt_chart = controller.build_definition()

    assert controller.draft.analysis_id.startswith("preview-")
    rebuilt_visual = AnalysisVisualSettings.from_options(rebuilt_chart.options, strict=True)
    template_visual = AnalysisVisualSettings.from_options(chart_template.options, strict=True)
    assert rebuilt_visual.chart == template_visual.chart
    assert rebuilt_visual.table == template_visual.table
    assert rebuilt_chart.options["future_option"] == {"keep": True}
    assert chart_template.to_dict() == chart_before

    deadline_template = get_builtin_analysis(
        "upcoming_deadline_count",
        today=date(2026, 7, 8),
        upcoming_days=21,
    )
    deadline_before = deepcopy(deadline_template.to_dict())
    controller.load_template(deadline_template)
    rebuilt_deadline = controller.build_definition()
    assert [item.to_dict() for item in rebuilt_deadline.filters] == [
        item.to_dict() for item in deadline_template.filters
    ]
    assert deadline_template.to_dict() == deadline_before


def test_template_load_rejects_builder_unsupported_definitions():
    controller = _controller()
    two_dimensions = AnalysisDefinition(
        "builtin-two-dim",
        "İki Gruplama",
        "contracts",
        "bar",
        dimensions=["platform_bucket", "status_bucket"],
        measures=[MeasureDefinition("", "count_rows")],
    )
    two_measures = AnalysisDefinition(
        "builtin-two-measure",
        "İki Hesap",
        "contracts",
        "bar",
        dimensions=["platform_bucket"],
        measures=[
            MeasureDefinition("", "count_rows"),
            MeasureDefinition("id", "count_distinct", alias="second"),
        ],
    )
    unsupported_visual = AnalysisDefinition(
        "builtin-list",
        "Liste",
        "contracts",
        "list",
        select_fields=["platform"],
    )

    for definition in (two_dimensions, two_measures, unsupported_visual):
        assert controller.supports_template(definition) is False
        with pytest.raises(AnalysisValidationError):
            controller.load_template(definition)


def test_loading_template_while_editing_saved_custom_analysis_never_overwrites_the_saved_analysis():
    repository = MemoryAnalysisRepository()
    controller = _controller(repository)
    controller.draft.title = "Mevcut Özel Analiz"
    controller.draft.visualization = "kpi"
    controller.draft.group_field = ""
    controller.draft.aggregation = "count_rows"
    saved = controller.save_current()
    original_payload = deepcopy(repository.get_analysis(saved.analysis_id).to_dict())

    controller.load_definition(saved)
    template = get_builtin_analysis("platform_distribution")
    controller.load_template(template)
    assert controller.current_saved_analysis_id is None
    assert controller.draft.analysis_id.startswith("preview-")

    controller.draft.title = "Hazır Analizden Yeni Özel Analiz"
    created = controller.save_current()

    assert created.analysis_id.startswith("custom-")
    assert created.analysis_id != saved.analysis_id
    assert repository.get_analysis(saved.analysis_id).to_dict() == original_payload
    assert repository.get_analysis(created.analysis_id) is not None
    assert len(repository.list_analyses()) == 2


def test_supported_projection_template_preserves_selected_table_fields_and_limit():
    controller = _controller()
    template = AnalysisDefinition(
        "builtin-table-template",
        "Teslimat Detayı",
        "acceptances",
        "table",
        select_fields=["platform", "name", "status"],
        limit=5,
        options={"size": "wide"},
    )

    controller.load_template(template)
    rebuilt = controller.build_definition()

    assert controller.current_saved_analysis_id is None
    assert controller.dirty is True
    assert controller.draft.selected_table_fields == ["platform", "name", "status"]
    assert rebuilt.select_fields == ["platform", "name", "status"]
    assert rebuilt.limit == 5
    assert rebuilt.options == {"size": "wide"}
