from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis_center.analysis_dashboard_layout import DashboardCardPlacement, LayoutValidationError
from analysis_center.analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspace,
    DashboardWorkspaceCorruptError,
    DashboardWorkspaceError,
    DashboardWorkspaceStore,
    migrate_workspace_payload,
    source_workspace_key,
)
from analysis_center.analysis_models import (
    AnalysisCard,
    AnalysisEntity,
    CardSize,
    CardType,
    ChartType,
    DashboardItem,
)


def _card(
    screen_id: str,
    card_id: str,
    title: str,
    *,
    size: CardSize = CardSize.MEDIUM,
    card_type: CardType = CardType.KPI,
    chart_type: ChartType = ChartType.NONE,
    value=1,
):
    return AnalysisCard(
        card_id=card_id,
        title=title,
        entity=AnalysisEntity.CONTRACT,
        card_type=card_type,
        size=size,
        chart_type=chart_type,
        value=value,
        screen_id=screen_id,
    )


def _legacy_payload(placements):
    return {
        "format_version": 1,
        "source_key": "legacy-source",
        "placements": placements,
    }


def test_workspace_pins_card_references_and_resolves_fresh_card_values():
    workspace = DashboardWorkspace(source_key="test")
    original = _card("executive_summary", "exec_total_contracts", "Toplam Sözleşme", value=3)

    assert workspace.pin(original) is True
    assert workspace.pin(original) is False
    assert workspace.contains("executive_summary", "exec_total_contracts") is True

    fresh = _card("executive_summary", "exec_total_contracts", "Toplam Sözleşme", value=9)
    cards, missing = workspace.resolve_cards([
        DashboardItem("executive_summary", "Yönetici Özeti", cards=[fresh])
    ])

    assert missing == []
    assert len(cards) == 1
    assert cards[0].value == 9
    assert cards[0].screen_id == CUSTOM_DASHBOARD_ID
    assert cards[0].meta["dashboard_source_screen_id"] == "executive_summary"
    assert cards[0].meta["dashboard_source_card_id"] == "exec_total_contracts"
    assert cards[0].meta["dashboard_placement_id"].startswith("placement-")
    assert (cards[0].meta["dashboard_w"], cards[0].meta["dashboard_h"]) == (3, 2)


def test_workspace_pin_uses_first_available_grid_slot_without_moving_existing_cards():
    workspace = DashboardWorkspace(source_key="test")
    for index in range(4):
        assert workspace.pin(_card("screen", f"kpi-{index}", f"KPI {index}")) is True

    assert [(item.x, item.y, item.w, item.h) for item in workspace.placements] == [
        (0, 0, 3, 2),
        (3, 0, 3, 2),
        (6, 0, 3, 2),
        (9, 0, 3, 2),
    ]


def test_workspace_data_model_supports_duplicate_source_card_placements():
    workspace = DashboardWorkspace(source_key="test")
    workspace.add_placement(DashboardCardPlacement("p-1", "screen", "same", 0, 0, 3, 2))
    workspace.add_placement(DashboardCardPlacement("p-2", "screen", "same", 3, 0, 3, 2))

    cards, missing = workspace.resolve_cards([
        DashboardItem("screen", "Screen", cards=[_card("screen", "same", "Same")])
    ])

    assert missing == []
    assert [card.meta["dashboard_placement_id"] for card in cards] == ["p-1", "p-2"]


def test_workspace_legacy_move_resize_and_remove_compatibility_does_not_mutate_source_cards():
    first = _card("platform_analysis", "platform_total", "Platform Sayısı", size=CardSize.SMALL)
    second = _card("acceptance_analysis", "acceptance_total", "Toplam Teslimat", size=CardSize.SMALL)
    workspace = DashboardWorkspace(source_key="test")
    workspace.pin(first)
    workspace.pin(second)

    assert workspace.move("acceptance_analysis", "acceptance_total", -1) is True
    assert workspace.set_size("acceptance_analysis", "acceptance_total", CardSize.WIDE) is True

    cards, missing = workspace.resolve_cards([
        DashboardItem("platform_analysis", "Platform Analizi", cards=[first]),
        DashboardItem("acceptance_analysis", "Teslimat Analizi", cards=[second]),
    ])
    assert missing == []
    assert cards[0].card_id == "acceptance_total"
    assert cards[0].size == CardSize.WIDE
    assert second.size == CardSize.SMALL

    assert workspace.remove("acceptance_analysis", "acceptance_total") is True
    assert workspace.remove("acceptance_analysis", "acceptance_total") is False
    assert [p.card_id for p in workspace.placements] == ["platform_total"]


def test_workspace_working_copy_separates_working_and_saved_layout_state():
    saved = DashboardWorkspace(source_key="test")
    saved.pin(_card("screen", "card", "Card"))
    working = saved.working_copy()

    placement_id = working.placements[0].placement_id
    working.move_placement(placement_id, x=6, y=4)

    assert working.placements[0].to_dict() != saved.placements[0].to_dict()


def test_empty_v1_workspace_migrates_to_v2():
    workspace = migrate_workspace_payload(_legacy_payload([]), source_key="test")
    assert workspace.schema_version == 2
    assert workspace.placements == []
    assert workspace.to_dict()["layout"] == {
        "columns": 12,
        "row_height": 54,
        "gap": 10,
        "compact_mode": "vertical",
    }


def test_single_small_card_migration_uses_width_mapping_and_kpi_height_hint():
    payload = _legacy_payload([
        {"source_screen_id": "screen", "card_id": "kpi", "sort_order": 0, "size": "small"}
    ])
    items = [DashboardItem("screen", "Screen", cards=[_card("screen", "kpi", "KPI")])]
    hints = {"screen:kpi": items[0].cards[0].resolved_layout_hints()}

    workspace = migrate_workspace_payload(payload, source_key="test", card_hints=hints)

    item = workspace.placements[0]
    assert (item.x, item.y, item.w, item.h) == (0, 0, 3, 2)


def test_mixed_size_migration_preserves_stable_sort_order_and_packs_rows():
    payload = _legacy_payload([
        {"source_screen_id": "screen", "card_id": "full", "sort_order": 40, "size": "wide"},
        {"source_screen_id": "screen", "card_id": "small", "sort_order": 10, "size": "small"},
        {"source_screen_id": "screen", "card_id": "large", "sort_order": 30, "size": "large"},
        {"source_screen_id": "screen", "card_id": "medium", "sort_order": 20, "size": "medium"},
    ])

    workspace = migrate_workspace_payload(payload, source_key="test")

    assert [item.card_id for item in workspace.placements] == ["small", "medium", "large", "full"]
    assert [(item.w, item.x, item.y) for item in workspace.placements] == [
        (3, 0, 0),
        (6, 3, 0),
        (9, 0, 3),
        (12, 0, 6),
    ]


def test_migration_stable_sort_order_uses_original_order_for_ties():
    payload = _legacy_payload([
        {"source_screen_id": "screen", "card_id": "b", "sort_order": 10, "size": "small"},
        {"source_screen_id": "screen", "card_id": "a", "sort_order": 10, "size": "small"},
    ])
    workspace = migrate_workspace_payload(payload, source_key="test")
    assert [item.card_id for item in workspace.placements] == ["b", "a"]


def test_unknown_card_metadata_uses_safe_fallback_height():
    payload = _legacy_payload([
        {"source_screen_id": "unknown", "card_id": "missing", "sort_order": 0, "size": "medium"}
    ])
    workspace = migrate_workspace_payload(payload, source_key="test")
    assert (workspace.placements[0].w, workspace.placements[0].h) == (6, 3)


def test_v2_workspace_migration_is_idempotent_and_unchanged():
    workspace = DashboardWorkspace(source_key="test")
    workspace.add_placement(DashboardCardPlacement("custom-id", "screen", "card", 8, 7, 4, 3))
    payload = workspace.to_dict()

    migrated = migrate_workspace_payload(payload, source_key="test")

    assert migrated.to_dict() == payload


def test_workspace_store_persists_v2_layout_outside_sts_file(tmp_path):
    sts_path = tmp_path / "data" / "sample.sts"
    sts_path.parent.mkdir()
    sts_path.write_bytes(b"do-not-touch")
    before = sts_path.read_bytes()

    store = DashboardWorkspaceStore(tmp_path / "local-dashboard-config")
    workspace = store.load(sts_path)
    workspace.pin(_card("contract_analysis", "contract_total", "Toplam Sözleşme"))
    workspace.set_size("contract_analysis", "contract_total", CardSize.LARGE)
    saved_path = store.save(sts_path, workspace)

    assert saved_path.parent == tmp_path / "local-dashboard-config"
    assert saved_path != sts_path
    assert sts_path.read_bytes() == before
    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["source_key"] == source_workspace_key(sts_path)
    assert payload["placements"][0]["card_id"] == "contract_total"
    assert payload["placements"][0]["w"] == 9
    assert "size" not in payload["placements"][0]
    assert "sort_order" not in payload["placements"][0]

    reloaded = store.load(sts_path)
    assert reloaded.contains("contract_analysis", "contract_total") is True
    assert reloaded.placements[0].w == 9


def test_valid_save_creates_backup_of_previous_workspace(tmp_path):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    workspace = DashboardWorkspace(source_key=source_workspace_key(sts_path))
    workspace.pin(_card("screen", "a", "A"))
    path = store.save(sts_path, workspace)
    first_payload = path.read_bytes()

    workspace.pin(_card("screen", "b", "B"))
    store.save(sts_path, workspace)

    assert store.backup_path(sts_path).read_bytes() == first_payload
    assert json.loads(path.read_text(encoding="utf-8"))["placements"][-1]["card_id"] == "b"


def test_save_rejects_invalid_workspace_before_writing(tmp_path):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    workspace = DashboardWorkspace(source_key=source_workspace_key(sts_path))
    workspace.placements.append(DashboardCardPlacement("bad", "screen", "bad", -1, 0, 3, 2))

    with pytest.raises(DashboardWorkspaceError, match="Geçersiz"):
        store.save(sts_path, workspace)
    assert not store.workspace_path(sts_path).exists()


def test_atomic_save_replaces_target_and_leaves_no_temp_file(tmp_path, monkeypatch):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    workspace = DashboardWorkspace(source_key=source_workspace_key(sts_path))
    workspace.pin(_card("screen", "a", "A"))
    calls = []

    import analysis_center.analysis_dashboard_workspace as workspace_module

    real_replace = workspace_module.os.replace

    def recording_replace(source, target):
        calls.append((Path(source), Path(target)))
        real_replace(source, target)

    monkeypatch.setattr(workspace_module.os, "replace", recording_replace)
    path = store.save(sts_path, workspace)

    assert any(target == path for _, target in calls)
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_legacy_load_backs_up_original_then_atomically_migrates(tmp_path):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    path = store.workspace_path(sts_path)
    path.parent.mkdir(parents=True)
    legacy = _legacy_payload([
        {"source_screen_id": "screen", "card_id": "chart", "sort_order": 0, "size": "medium"}
    ])
    raw = json.dumps(legacy, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(raw)
    chart = _card("screen", "chart", "Chart", card_type=CardType.CHART, chart_type=ChartType.BAR)

    workspace = store.load(sts_path, dashboard_items=[DashboardItem("screen", "Screen", cards=[chart])])

    assert store.backup_path(sts_path).read_bytes() == raw
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 2
    assert (workspace.placements[0].w, workspace.placements[0].h) == (6, 4)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "workspace_id": "default", "source_key": "x", "layout": [], "placements": []},
        {"schema_version": 2, "workspace_id": "default", "source_key": "x", "layout": {}, "placements": ["bad"]},
        _legacy_payload(["bad"]),
        _legacy_payload([{"source_screen_id": "", "card_id": "missing", "sort_order": 0, "size": "small"}]),
    ],
)
def test_malformed_workspace_records_are_rejected_without_silent_data_loss(tmp_path, payload):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    path = store.workspace_path(sts_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(DashboardWorkspaceError):
        store.load(sts_path)

    assert path.read_bytes() == before


def test_corrupt_json_load_raises_and_preserves_file(tmp_path):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    path = store.workspace_path(sts_path)
    path.parent.mkdir(parents=True)
    path.write_text("{broken-json", encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(DashboardWorkspaceCorruptError, match="JSON bozuk"):
        store.load(sts_path)

    assert path.read_bytes() == before
    assert not store.backup_path(sts_path).exists()


def test_corrupt_existing_workspace_is_not_overwritten_by_save(tmp_path):
    sts_path = tmp_path / "sample.sts"
    store = DashboardWorkspaceStore(tmp_path / "dashboards")
    path = store.workspace_path(sts_path)
    path.parent.mkdir(parents=True)
    path.write_text("{broken-json", encoding="utf-8")
    workspace = DashboardWorkspace(source_key=source_workspace_key(sts_path))
    workspace.pin(_card("screen", "a", "A"))

    with pytest.raises(DashboardWorkspaceCorruptError):
        store.save(sts_path, workspace)

    assert path.read_text(encoding="utf-8") == "{broken-json"


def test_workspace_reports_missing_source_cards_without_deleting_saved_placement():
    workspace = DashboardWorkspace(source_key="test")
    workspace.pin(_card("deadline_analysis", "deadline_upcoming", "Yaklaşan Termin"))

    cards, missing = workspace.resolve_cards([])

    assert cards == []
    assert missing == ["deadline_analysis:deadline_upcoming"]
    assert workspace.contains("deadline_analysis", "deadline_upcoming") is True


def test_versioned_sts_files_share_the_same_dashboard_workspace_key(tmp_path):
    v2 = tmp_path / "STS-A1__v002__2026-07-07_13-59.sts"
    v3 = tmp_path / "STS-A1__v003__2026-07-08_09-10.sts"
    other_folder_v3 = tmp_path / "other" / v3.name

    assert source_workspace_key(v2) == source_workspace_key(v3)
    assert source_workspace_key(v2) != source_workspace_key(other_folder_v3)
