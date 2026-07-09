from __future__ import annotations

import pytest

from analysis_center.analysis_custom_dashboard import (
    CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
    CustomAnalysisDashboardController,
)
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace, DashboardWorkspaceStore
from analysis_center.analysis_definitions import AnalysisDefinition, FilterDefinition, MeasureDefinition
from analysis_center.analysis_models import AnalysisCard, AnalysisEntity, CardType, DashboardItem
from analysis_center.analysis_repository import FileAnalysisRepository, MemoryAnalysisRepository
from analysis_center.analysis_service import AnalysisService


def _service(repository=None) -> AnalysisService:
    service = AnalysisService(use_sample=True, repository=repository or MemoryAnalysisRepository())
    service.refresh_data()
    return service


def _definition(analysis_id: str, *, visualization: str = "horizontal_bar", title: str = "Özel"):
    if visualization == "kpi":
        return AnalysisDefinition(
            analysis_id=analysis_id,
            title=title,
            dataset="acceptances",
            visualization="kpi",
            measures=[MeasureDefinition("", "count_rows")],
        )
    if visualization == "table":
        return AnalysisDefinition(
            analysis_id=analysis_id,
            title=title,
            dataset="acceptances",
            visualization="table",
            select_fields=["platform", "name", "status"],
            limit=20,
        )
    return AnalysisDefinition(
        analysis_id=analysis_id,
        title=title,
        dataset="acceptances",
        visualization=visualization,
        dimensions=["platform"],
        measures=[MeasureDefinition("", "count_rows")],
        limit=20,
    )


def _prepared_card() -> AnalysisCard:
    return AnalysisCard(
        card_id="prepared-kpi",
        title="Hazır KPI",
        entity=AnalysisEntity.CONTRACT,
        card_type=CardType.KPI,
        value=3,
        screen_id="prepared_screen",
    )


def test_custom_dashboard_identity_and_preview_id_rejected():
    service = _service()
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")

    with pytest.raises(Exception, match="önce analizi kaydedin"):
        controller.pin(workspace, "preview-123")

    saved = service.create_saved_analysis(_definition("preview-source"))
    assert saved.analysis_id.startswith("custom-")
    assert controller.pin(workspace, saved.analysis_id) is True
    assert controller.pin(workspace, saved.analysis_id) is False
    placement = workspace.placements[0]
    assert placement.source_screen_id == CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
    assert placement.card_id == saved.analysis_id


@pytest.mark.parametrize(
    ("visualization", "card_type"),
    [("kpi", CardType.KPI), ("horizontal_bar", CardType.CHART), ("table", CardType.TABLE)],
)
def test_pinned_custom_definition_executes_real_engine_and_produces_existing_card_types(
    visualization,
    card_type,
):
    service = _service()
    saved = service.create_saved_analysis(_definition("preview", visualization=visualization))
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    assert controller.pin(workspace, saved.analysis_id) is True

    cards, issues = controller.resolve_pinned_cards(workspace)

    assert issues == []
    assert len(cards) == 1
    assert cards[0].card_type == card_type
    assert cards[0].screen_id == CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
    assert cards[0].card_id == saved.analysis_id
    assert cards[0].meta["custom_analysis_id"] == saved.analysis_id


def test_only_pinned_custom_analyses_are_executed():
    service = _service()
    first = service.create_saved_analysis(_definition("preview-a", title="A"))
    second = service.create_saved_analysis(_definition("preview-b", title="B"))
    third = service.create_saved_analysis(_definition("preview-c", title="C"))
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    controller.pin(workspace, first.analysis_id)
    controller.pin(workspace, third.analysis_id)

    executed: list[str] = []
    real_execute = service.execute_analysis

    def spy(definition):
        executed.append(definition.analysis_id)
        return real_execute(definition)

    service.execute_analysis = spy
    cards, issues = controller.resolve_pinned_cards(workspace)

    assert issues == []
    assert {card.card_id for card in cards} == {first.analysis_id, third.analysis_id}
    assert executed == [first.analysis_id, third.analysis_id]
    assert second.analysis_id not in executed


def test_prepared_and_custom_placements_resolve_together_and_use_card_hints():
    service = _service()
    saved = service.create_saved_analysis(_definition("preview", visualization="table"))
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    prepared = _prepared_card()
    assert workspace.pin(prepared) is True
    assert controller.pin(workspace, saved.analysis_id) is True

    custom_cards, issues = controller.resolve_pinned_cards(workspace)
    cards, missing = workspace.resolve_cards(
        [DashboardItem("prepared_screen", "Hazır", cards=[prepared])],
        additional_cards=custom_cards,
    )

    assert issues == []
    assert missing == []
    assert {card.card_id for card in cards} == {"prepared-kpi", saved.analysis_id}
    custom_placement = workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        saved.analysis_id,
    )
    hints = workspace.layout_hints_for(custom_placement.placement_id)
    assert (hints.min_w, hints.min_h, hints.default_w, hints.default_h) == (6, 4, 12, 5)


def test_deleted_custom_id_is_orphan_but_execution_failure_custom_placement_is_preserved():
    service = _service()
    saved = service.create_saved_analysis(_definition("preview"))
    stale = AnalysisDefinition(
        analysis_id="custom-stale",
        title="Stale",
        dataset="missing_dataset",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
    )
    service.repository.save_analysis(stale)
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    controller.pin(workspace, saved.analysis_id)
    workspace.add_placement(
        DashboardCardPlacement(
            "stale-placement",
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            stale.analysis_id,
            6,
            0,
            3,
            2,
        )
    )
    workspace.add_placement(
        DashboardCardPlacement(
            "deleted-placement",
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            "custom-deleted",
            9,
            0,
            3,
            2,
        )
    )

    known_keys, protected = controller.workspace_catalog()
    removed = workspace.prune_orphaned_placements(
        [DashboardItem("prepared_screen", "Hazır", cards=[_prepared_card()])],
        additional_card_keys=known_keys,
        protected_source_ids=protected,
    )

    assert removed == [f"{CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}:custom-deleted"]
    assert workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, stale.analysis_id)
    cards, issues = controller.resolve_pinned_cards(workspace)
    assert [card.card_id for card in cards] == [saved.analysis_id]
    assert any(issue.analysis_id == stale.analysis_id and issue.kind == "validation" for issue in issues)
    assert workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, stale.analysis_id)


def test_repository_load_error_protects_custom_placement_from_workspace_pruning(tmp_path):
    source = tmp_path / "source.sts"
    source.write_bytes(b"source")
    repository = FileAnalysisRepository(source, tmp_path / "analyses")
    repository.repository_path().parent.mkdir(parents=True, exist_ok=True)
    repository.repository_path().write_text("{broken", encoding="utf-8")
    repository = FileAnalysisRepository(source, tmp_path / "analyses")
    service = _service(repository)
    controller = CustomAnalysisDashboardController(service)
    workspace_store = DashboardWorkspaceStore(tmp_path / "dashboards")
    workspace = DashboardWorkspace(source_key=workspace_store.load(source).source_key)
    workspace.add_placement(
        DashboardCardPlacement(
            "custom-placement",
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            "custom-preserve",
            0,
            0,
            3,
            2,
        )
    )
    workspace_store.save(source, workspace)

    keys, protected = controller.workspace_catalog()
    loaded = workspace_store.load(
        source,
        dashboard_items=[DashboardItem("prepared_screen", "Hazır", cards=[_prepared_card()])],
        additional_card_keys=keys,
        protected_source_ids=protected,
    )

    assert keys == set()
    assert protected == {CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}
    assert loaded.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, "custom-preserve")
    cards, issues = controller.resolve_pinned_cards(loaded)
    assert cards == []
    assert issues[0].kind == "repository"


def test_custom_remove_preserves_other_placements_and_restart_resolves_pinned_card(tmp_path):
    source = tmp_path / "source.sts"
    source.write_bytes(b"source")
    repo_root = tmp_path / "analyses"
    workspace_root = tmp_path / "dashboards"
    repository = FileAnalysisRepository(source, repo_root)
    service = _service(repository)
    saved = service.create_saved_analysis(_definition("preview", visualization="kpi"))
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace(source_key=DashboardWorkspaceStore(workspace_root).load(source).source_key)
    prepared = _prepared_card()
    workspace.pin(prepared)
    controller.pin(workspace, saved.analysis_id)
    store = DashboardWorkspaceStore(workspace_root)
    store.save(source, workspace)

    reloaded_repo = FileAnalysisRepository(source, repo_root)
    reloaded_service = _service(reloaded_repo)
    reloaded_controller = CustomAnalysisDashboardController(reloaded_service)
    keys, protected = reloaded_controller.workspace_catalog()
    reloaded = store.load(
        source,
        dashboard_items=[DashboardItem("prepared_screen", "Hazır", cards=[prepared])],
        additional_card_keys=keys,
        protected_source_ids=protected,
    )
    custom_cards, issues = reloaded_controller.resolve_pinned_cards(reloaded)
    cards, missing = reloaded.resolve_cards(
        [DashboardItem("prepared_screen", "Hazır", cards=[prepared])],
        additional_cards=custom_cards,
    )
    assert issues == []
    assert missing == []
    assert {card.card_id for card in cards} == {prepared.card_id, saved.analysis_id}

    assert reloaded_controller.unpin(reloaded, saved.analysis_id) is True
    assert reloaded.contains("prepared_screen", prepared.card_id)
    assert not reloaded.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, saved.analysis_id)


def test_edit_same_id_refreshes_pinned_card_and_copy_is_not_pinned():
    service = _service()
    original = service.create_saved_analysis(_definition("preview", title="İlk Başlık"))
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    controller.pin(workspace, original.analysis_id)

    edited = AnalysisDefinition(
        analysis_id=original.analysis_id,
        title="Yeni Başlık",
        dataset="acceptances",
        visualization="kpi",
        measures=[MeasureDefinition("", "count_rows")],
        filters=[FilterDefinition("platform", "equals", "AKINCI")],
    )
    service.update_saved_analysis(edited, original.analysis_id)
    cards, issues = controller.resolve_pinned_cards(workspace)
    copied = service.copy_saved_analysis(original.analysis_id)

    assert issues == []
    assert cards[0].title == "Yeni Başlık"
    assert cards[0].card_type == CardType.KPI
    assert cards[0].value == 1
    assert workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, original.analysis_id)
    assert not workspace.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, copied.analysis_id)


def test_pinned_visualization_change_reuses_same_reference_and_reflows_to_new_card_hints():
    service = _service()
    original = service.create_saved_analysis(
        _definition("preview", visualization="kpi", title="KPI")
    )
    controller = CustomAnalysisDashboardController(service)
    workspace = DashboardWorkspace("test")
    controller.pin(workspace, original.analysis_id)
    placement = workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        original.analysis_id,
    )
    placement_id = placement.placement_id
    assert (placement.w, placement.h) == (3, 2)

    table = _definition(
        original.analysis_id,
        visualization="table",
        title="Tabloya Dönüştü",
    )
    service.update_saved_analysis(table, original.analysis_id)
    custom_cards, issues = controller.resolve_pinned_cards(workspace)
    cards, missing = workspace.resolve_cards([], additional_cards=custom_cards)

    assert issues == []
    assert missing == []
    assert cards[0].card_type == CardType.TABLE
    placement = workspace.placement_for_source(
        CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
        original.analysis_id,
    )
    assert placement.placement_id == placement_id
    assert placement.w >= 6
    assert placement.h >= 4


def test_workspace_store_prunes_missing_deleted_custom_id_but_keeps_prepared_card(tmp_path):
    source = tmp_path / "source.sts"
    source.write_bytes(b"source")
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    prepared = _prepared_card()
    workspace = DashboardWorkspace(source_key=store.load(source).source_key)
    workspace.pin(prepared)
    workspace.add_placement(
        DashboardCardPlacement(
            "deleted-custom",
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            "custom-gone",
            3,
            0,
            3,
            2,
        )
    )
    store.save(source, workspace)

    service = _service(FileAnalysisRepository(source, tmp_path / "analyses"))
    controller = CustomAnalysisDashboardController(service)
    keys, protected = controller.workspace_catalog()
    loaded = store.load(
        source,
        dashboard_items=[DashboardItem("prepared_screen", "Hazır", cards=[prepared])],
        additional_card_keys=keys,
        protected_source_ids=protected,
    )

    assert loaded.contains("prepared_screen", prepared.card_id)
    assert not loaded.contains(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, "custom-gone")
    assert [placement.card_id for placement in loaded.placements] == [prepared.card_id]
