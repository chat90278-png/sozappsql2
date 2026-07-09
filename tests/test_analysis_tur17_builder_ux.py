from __future__ import annotations

import json

from analysis_center.analysis_builder import AnalysisBuilderController
from analysis_center.analysis_cards import build_dashboard_items
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace, DashboardWorkspaceStore
from analysis_center.analysis_metrics import compute_metrics
from analysis_center.analysis_registry import DEFAULT_REGISTRY
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_service import AnalysisService


def _controller() -> AnalysisBuilderController:
    service = AnalysisService(use_sample=True)
    service.data = build_sample_data()
    return AnalysisBuilderController(service)


def test_builder_metadata_hides_technical_ids_and_orders_semantic_fields_deterministically():
    controller = _controller()
    controller.set_dataset("components")

    assert "id" in {field.field_id for field in controller.fields()}
    assert "id" not in {field.field_id for field in controller.group_fields()}
    assert [field.field_id for field in controller.group_fields()] == [
        "unit",
        "active",
        "name",
        "version",
    ]
    assert controller.draft.group_field == "unit"

    controller.set_dataset("acceptances")
    assert [field.field_id for field in controller.group_fields()[:5]] == [
        "status_bucket",
        "platform",
        "status",
        "contract_no",
        "system_name",
    ]
    assert "contract_id" not in {field.field_id for field in controller.group_fields()}
    assert "contract_id" in {field.field_id for field in controller.filter_fields()}


def test_table_defaults_use_first_meaningful_user_visible_fields():
    controller = _controller()
    controller.set_dataset("components")
    controller.set_visualization("table")

    assert controller.draft.selected_table_fields == ["unit", "active", "name", "version"]
    assert "id" not in controller.draft.selected_table_fields
    definition = controller.build_definition()
    assert definition.select_fields == ["unit", "active", "name", "version"]


def test_builder_visibility_metadata_does_not_change_engine_field_access():
    controller = _controller()
    id_field = DEFAULT_REGISTRY.get_field("components", "id")
    assert id_field.builder_roles == ("filter",)
    assert DEFAULT_REGISTRY.resolve_value("components", "id", {"id": 41}) == 41


def test_count_like_kpi_defaults_to_zero_decimals_and_numeric_average_keeps_two():
    controller = _controller()
    controller.set_dataset("acceptances")
    controller.set_visualization("kpi")

    for aggregation in ("count_rows", "count", "count_distinct"):
        controller.draft.kpi_decimal_explicit = False
        controller.set_aggregation(aggregation)
        assert controller.visual_settings().kpi.decimal_places == 0

    controller.draft.kpi_decimal_explicit = False
    controller.set_aggregation("avg")
    assert controller.visual_settings().kpi.decimal_places == 2


def test_explicit_kpi_decimal_setting_survives_aggregation_change():
    controller = _controller()
    controller.set_dataset("acceptances")
    controller.set_visualization("kpi")
    controller.update_kpi_visual_settings(decimal_places=1)
    assert controller.draft.kpi_decimal_explicit is True

    controller.set_aggregation("count_rows")
    assert controller.visual_settings().kpi.decimal_places == 1
    definition = controller.build_definition()
    assert definition.options["visual_settings"]["kpi"]["decimal_places_explicit"] is True


def test_contract_unlabeled_card_and_health_only_metrics_are_removed():
    metrics = compute_metrics(build_sample_data())
    items = build_dashboard_items(metrics)
    contracts = next(item for item in items if item.item_id == "contract_analysis")

    assert "unlabeled_contracts" not in metrics
    assert "unlabeled_contract_count" not in metrics
    assert "contract_unlabeled_table" not in {card.card_id for card in contracts.cards}
    assert "Etiketsiz Kayıtlar" not in {card.title for card in contracts.cards}


def test_old_unlabeled_dashboard_placement_is_pruned_without_moving_other_cards(tmp_path):
    source = tmp_path / "source.sts"
    source.touch()
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    workspace = DashboardWorkspace(
        source_key="placeholder",
        placements=[
            DashboardCardPlacement("keep", "contract_analysis", "contract_total", 6, 6, 3, 2),
            DashboardCardPlacement("removed", "contract_analysis", "contract_unlabeled_table", 0, 0, 12, 5),
        ],
    )
    path = store.workspace_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workspace.to_dict()), encoding="utf-8")

    items = build_dashboard_items(compute_metrics(build_sample_data()))
    loaded = store.load(source, dashboard_items=items)

    assert [(item.placement_id, item.card_id) for item in loaded.placements] == [
        ("keep", "contract_total")
    ]
    kept = loaded.placements[0]
    assert (kept.x, kept.y, kept.w, kept.h) == (6, 6, 3, 2)
    loaded.validate()
    backup = json.loads(store.backup_path(source).read_text(encoding="utf-8"))
    assert {item["placement_id"] for item in backup["placements"]} == {"keep", "removed"}
