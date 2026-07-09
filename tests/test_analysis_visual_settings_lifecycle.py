from __future__ import annotations

from copy import deepcopy

from analysis_center.analysis_builder import AnalysisBuilderController
from analysis_center.analysis_custom_dashboard import CustomAnalysisDashboardController
from analysis_center.analysis_custom_library import CustomAnalysisLibraryController
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace
from analysis_center.analysis_definitions import AnalysisDefinition, MeasureDefinition
from analysis_center.analysis_repository import FileAnalysisRepository, MemoryAnalysisRepository
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService
from analysis_center.analysis_visual_settings import AnalysisVisualSettings, ChartVisualSettings, KpiVisualSettings


def _service(repository) -> AnalysisService:
    service = AnalysisService(use_sample=True, repository=repository)
    service.data = build_sample_data()
    return service


def _chart_definition(*, analysis_id: str = "preview-visual", title: str = "Visual") -> AnalysisDefinition:
    settings = AnalysisVisualSettings(
        chart=ChartVisualSettings(
            show_legend=True,
            legend_position="bottom",
            show_values=True,
            palette="pastel",
            max_categories=1,
            group_others=True,
        )
    )
    return AnalysisDefinition(
        analysis_id=analysis_id,
        title=title,
        dataset="acceptances",
        visualization="horizontal_bar",
        dimensions=["platform"],
        measures=[MeasureDefinition("", "count_rows")],
        limit=20,
        options=settings.to_options({"future": "keep"}),
    )


def test_copy_preserves_visual_settings_and_original_is_not_mutated():
    service = _service(MemoryAnalysisRepository())
    original = service.create_saved_analysis(_chart_definition())
    before = deepcopy(original.options)

    copied = service.copy_saved_analysis(original.analysis_id)

    assert copied.analysis_id != original.analysis_id
    assert copied.options == before
    assert service.get_saved_analysis(original.analysis_id).options == before


def test_edit_same_id_updates_visual_settings_and_library_preview_uses_them():
    service = _service(MemoryAnalysisRepository())
    saved = service.create_saved_analysis(_chart_definition())
    edited = deepcopy(saved)
    visual = AnalysisVisualSettings.from_options(edited.options, strict=True)
    visual.replace_chart(palette="green", legend_position="right", show_values=False)
    edited.options = visual.to_options(edited.options)

    updated = service.update_saved_analysis(edited, saved.analysis_id)
    definition, result = CustomAnalysisLibraryController(service).preview(saved.analysis_id)
    card = service.get_analysis_card(definition)

    assert updated.analysis_id == saved.analysis_id
    assert AnalysisVisualSettings.from_options(updated.options, strict=True).chart.palette == "green"
    assert card.meta["visual_settings"].chart.palette == "green"
    assert result.meta["result_row_count"] >= 1


def test_pinned_dashboard_same_placement_reference_uses_edited_visual_settings():
    service = _service(MemoryAnalysisRepository())
    saved = service.create_saved_analysis(_chart_definition(title="Before"))
    custom = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    assert custom.pin(workspace, saved.analysis_id) is True
    placement = workspace.placements[0]

    cards, issues = custom.resolve_pinned_cards(workspace)
    assert issues == []
    assert cards[0].title == "Before"
    assert cards[0].meta["visual_settings"].chart.palette == "pastel"

    edited = deepcopy(saved)
    edited.title = "After"
    settings = AnalysisVisualSettings.from_options(edited.options, strict=True)
    settings.replace_chart(palette="monochrome", show_legend=False)
    edited.options = settings.to_options(edited.options)
    service.update_saved_analysis(edited, saved.analysis_id)

    cards, issues = custom.resolve_pinned_cards(workspace)
    assert issues == []
    assert workspace.placements[0].placement_id == placement.placement_id
    assert workspace.placements[0].card_id == saved.analysis_id
    assert cards[0].title == "After"
    assert cards[0].meta["visual_settings"].chart.palette == "monochrome"
    assert cards[0].meta["visual_settings"].chart.show_legend is False


def test_file_repository_restart_preserves_chart_kpi_and_unknown_options(tmp_path):
    source = tmp_path / "sample.sts"
    source.write_text("fixture", encoding="utf-8")
    root = tmp_path / "analyses"
    first_repo = FileAnalysisRepository(source, root=root)
    first_service = _service(first_repo)
    chart = first_service.create_saved_analysis(_chart_definition())

    kpi_settings = AnalysisVisualSettings(
        kpi=KpiVisualSettings(subtitle="Oran", prefix="₺ ", suffix="", decimal_places=0)
    )
    kpi = first_service.create_saved_analysis(
        AnalysisDefinition(
            analysis_id="preview-kpi",
            title="KPI",
            dataset="acceptances",
            visualization="kpi",
            measures=[MeasureDefinition("planned_total", "sum")],
            options=kpi_settings.to_options({"future_root": {"v": 1}}),
        )
    )

    second_service = _service(FileAnalysisRepository(source, root=root))
    loaded_chart = second_service.get_saved_analysis(chart.analysis_id)
    loaded_kpi = second_service.get_saved_analysis(kpi.analysis_id)

    assert AnalysisVisualSettings.from_options(loaded_chart.options, strict=True).chart.palette == "pastel"
    loaded_kpi_settings = AnalysisVisualSettings.from_options(loaded_kpi.options, strict=True)
    assert loaded_kpi_settings.kpi.prefix == "₺ "
    assert loaded_kpi_settings.kpi.decimal_places == 0
    assert loaded_kpi.options["future_root"] == {"v": 1}


def test_builder_load_and_save_visual_settings_keeps_saved_id_and_dirty_contract():
    service = _service(MemoryAnalysisRepository())
    controller = AnalysisBuilderController(service)
    controller.set_dataset("acceptances")
    controller.set_visualization("horizontal_bar")
    controller.draft.group_field = "platform"
    controller.draft.title = "Builder Visual"
    controller.update_chart_visual_settings(palette="blue", show_values=True)
    saved = controller.save_current()

    assert controller.current_saved_analysis_id == saved.analysis_id
    assert controller.dirty is False
    controller.update_chart_visual_settings(palette="warm")
    assert controller.dirty is True
    controller.preview()
    assert controller.dirty is True
    updated = controller.save_current()
    assert updated.analysis_id == saved.analysis_id
    assert controller.dirty is False
    assert AnalysisVisualSettings.from_options(updated.options, strict=True).chart.palette == "warm"
