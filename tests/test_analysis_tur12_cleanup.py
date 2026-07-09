from __future__ import annotations

import json
from pathlib import Path

from analysis_center.analysis_cards import build_dashboard_items
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace, DashboardWorkspaceStore
from analysis_center.analysis_metrics import compute_metrics
from analysis_center.analysis_models import AnalysisCard, AnalysisEntity, CardType, DashboardItem
from analysis_center.analysis_registry import DEFAULT_REGISTRY
from analysis_center.analysis_sample_data import build_sample_data
from analysis_center.analysis_settings import ACTIVE_SCREEN_IDS, NORMALIZED_DATA_KEYS, PHASE_2_SCREEN_IDS


def _card(screen_id: str, card_id: str) -> AnalysisCard:
    return AnalysisCard(
        card_id=card_id,
        title=card_id,
        entity=AnalysisEntity.CONTRACT,
        card_type=CardType.KPI,
        screen_id=screen_id,
    )


def test_removed_data_health_feature_is_absent_from_navigation_registry_and_normalized_model():
    assert "mini_data_health" not in ACTIVE_SCREEN_IDS
    assert "detailed_data_health" not in PHASE_2_SCREEN_IDS
    assert "health_items" not in NORMALIZED_DATA_KEYS
    assert "health_items" not in {item.dataset_id for item in DEFAULT_REGISTRY.list_datasets()}
    assert not hasattr(AnalysisEntity, "HEALTH")

    items = build_dashboard_items(compute_metrics(build_sample_data()))
    assert "mini_data_health" not in {item.item_id for item in items}
    assert all(not card.card_id.startswith("health_") for item in items for card in item.cards)
    assert DEFAULT_REGISTRY.get_dataset("contracts").dataset_id == "contracts"
    assert DEFAULT_REGISTRY.get_dataset("deadlines").dataset_id == "deadlines"


def test_old_workspace_orphan_is_pruned_on_load_without_moving_other_placements(tmp_path):
    source = tmp_path / "source.sts"
    source.touch()
    store = DashboardWorkspaceStore(tmp_path / "workspaces")
    workspace = DashboardWorkspace(
        source_key="placeholder",
        placements=[
            DashboardCardPlacement("keep", "contract_analysis", "contract_total", 6, 4, 3, 2),
            DashboardCardPlacement("health", "mini_data_health", "health_missing_info", 0, 0, 3, 2),
        ],
    )
    payload = workspace.to_dict()
    payload["source_key"] = "legacy-ignored"
    path = store.workspace_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    valid_item = DashboardItem(
        item_id="contract_analysis",
        title="Sözleşme Analizi",
        cards=[_card("contract_analysis", "contract_total")],
    )
    loaded = store.load(source, dashboard_items=[valid_item])

    assert [(item.placement_id, item.source_screen_id, item.card_id) for item in loaded.placements] == [
        ("keep", "contract_analysis", "contract_total")
    ]
    kept = loaded.placements[0]
    assert (kept.x, kept.y, kept.w, kept.h) == (6, 4, 3, 2)
    loaded.validate()

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert [item["placement_id"] for item in persisted["placements"]] == ["keep"]
    backup = json.loads(store.backup_path(source).read_text(encoding="utf-8"))
    assert {item["placement_id"] for item in backup["placements"]} == {"keep", "health"}


def test_prune_orphaned_placements_is_safe_when_card_catalog_is_empty():
    workspace = DashboardWorkspace(
        source_key="test",
        placements=[DashboardCardPlacement("keep", "screen", "card", 0, 0, 3, 2)],
    )
    before = workspace.to_dict()
    assert workspace.prune_orphaned_placements([]) == []
    assert workspace.to_dict() == before


def test_analysis_center_source_has_no_removed_health_feature_symbols():
    root = Path(__file__).resolve().parents[1] / "analysis_center"
    needles = (
        "mini_data_health",
        "health_items",
        "missing_info_count",
        "missing_info_items",
        "AnalysisEntity.HEALTH",
        'HEALTH = "health"',
        "Mini Veri Sağlığı",
    )
    matches = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                matches.append((path.name, needle))
    assert matches == []
