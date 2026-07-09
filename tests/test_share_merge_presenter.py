from __future__ import annotations

from datetime import date

from src.models.share_merge_models import MergeChangeKind, MergeEntityKind
from src.models.share_merge_resolution_models import (
    MergeDecisionKind,
    MergeDecisionTarget,
    MergeDecisionTargetType,
    MergeResolutionIssue,
    ResolutionItem,
    ResolvedMergePlan,
)
from src.ui.presenters.share_merge_presenter import (
    decision_label,
    entity_group_label,
    field_label,
    format_value,
    present_item,
    structural_validation_message,
)


def resolution_item(**kwargs):
    target = MergeDecisionTarget(
        target_id=kwargs.get("target_id", "FIELD|SYSTEM|sys-1|systems/sys-1/components/KKK/qty"),
        target_type=kwargs.get("target_type", MergeDecisionTargetType.FIELD),
        entity_kind=kwargs.get("entity_kind", MergeEntityKind.SYSTEM),
        entity_uid=kwargs.get("entity_uid", "sys-1"),
        change_kind=kwargs.get("change_kind", MergeChangeKind.REMOTE_ONLY),
        field_path=kwargs.get("field_path", "systems/sys-1/components/KKK/qty"),
        field_name=kwargs.get("field_name", "qty"),
    )
    return ResolutionItem(
        target=target,
        entity_label=kwargs.get("entity_label", "Sistem 1"),
        base_value=kwargs.get("base_value", 1),
        local_value=kwargs.get("local_value", 1),
        remote_value=kwargs.get("remote_value", 2),
        default_decision=MergeDecisionKind.REMOTE_USE,
        allowed_decisions=(MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP),
    )


def test_presenter_group_field_and_decision_labels():
    assert entity_group_label(MergeEntityKind.CONTRACT) == "Sözleşme Bilgileri"
    assert entity_group_label(MergeEntityKind.DOCUMENT_FILE) == "Belgeler"
    assert field_label("note") == "Not"
    assert field_label("qty", "systems/sys-1/components/KKK/qty") == "Miktar"
    assert field_label("planned", "deliveries/d1/components/KKK/planned") == "Planlanan"
    assert decision_label(MergeDecisionKind.LOCAL_KEEP) == "Bu STS'dekini Koru"
    assert decision_label(MergeDecisionKind.DOCUMENT_KEEP_BOTH) == "İki Dosyayı da Koru"


def test_presented_item_uses_entity_label_and_component_field_label():
    presented = present_item(resolution_item())
    assert presented.group_label == "Sistemler"
    assert presented.title == "Sistem 1 > Miktar"
    assert presented.subtitle == "Bileşen: KKK"
    assert presented.remote_display == "2"


def test_value_formatting_and_uid_not_used_as_main_display():
    assert format_value(None) == "Boş"
    assert format_value("") == "Boş"
    assert format_value(True) == "Evet"
    assert format_value(False) == "Hayır"
    assert format_value(date(2026, 7, 7)) == "07.07.2026"
    assert format_value("550e8400-e29b-41d4-a716-446655440000") == "Bağlı kayıt"
    assert format_value("a" * 64) == "Dosya içeriği değişti"
    assert format_value({"merge_uid": "u1", "filename": "rapor.pdf", "sha256": "b" * 64}) == "rapor.pdf"


def test_presenter_falls_back_to_snapshot_name_before_uid():
    item = resolution_item(
        entity_label="550e8400-e29b-41d4-a716-446655440000",
        remote_value={"merge_uid": "550e8400-e29b-41d4-a716-446655440000", "name": "Gerçek Sistem"},
    )
    assert present_item(item).title == "Gerçek Sistem > Miktar"

import time

from src.models.share_merge_models import MergeChange, MergePlan
from src.ui.presenters.share_merge_presenter import ShareMergeDecisionController, grouped_presented_items


def _large_change(kind: MergeEntityKind, idx: int, change_kind=MergeChangeKind.REMOTE_ONLY) -> MergeChange:
    return MergeChange(
        entity_kind=kind,
        entity_uid=f"uid-{kind.value}-{idx:04d}",
        entity_label=f"{kind.value} {idx}",
        field_path=f"{kind.value.lower()}/{idx}/note",
        field_name="note",
        base_value="A",
        local_value="A",
        remote_value=f"R{idx}",
        change_kind=change_kind,
    )


def test_decision_change_only_invokes_resolver_and_keeps_merge_plan_immutable():
    from src.domain.share_merge_resolution import resolve_merge_plan

    plan = MergePlan("contract-uid", "base", "local", "remote", changes=[_large_change(MergeEntityKind.CONTRACT, 1, MergeChangeKind.CONFLICT)], conflicts=[])
    calls = {"resolve": 0}
    seen_decisions = []

    def resolver(merge_plan, decisions):
        calls["resolve"] += 1
        seen_decisions.append(list(decisions))
        return resolve_merge_plan(merge_plan, decisions)

    before = repr(plan)
    controller = ShareMergeDecisionController(plan, resolver=resolver)
    target_id = controller.resolved_plan.resolution_items[0].target.target_id
    controller.set_decision(target_id, MergeDecisionKind.LOCAL_KEEP)
    controller.set_decision(target_id, MergeDecisionKind.REMOTE_USE)

    assert calls["resolve"] == 3
    assert repr(plan) == before
    assert controller.explicit_decisions == {target_id: MergeDecisionKind.REMOTE_USE}
    assert seen_decisions[-1][0].target_id == target_id


def test_large_presenter_grouping_and_lookup_scale_without_quadratic_thresholds():
    changes = []
    for i in range(100):
        changes.append(_large_change(MergeEntityKind.SYSTEM, i))
    for i in range(1000):
        changes.append(_large_change(MergeEntityKind.DELIVERY, i))
    for i in range(500):
        changes.append(_large_change(MergeEntityKind.DOCUMENT_FILE, i))
    for i in range(100):
        changes.append(_large_change(MergeEntityKind.PLATFORM_RELATION, i))
        changes.append(_large_change(MergeEntityKind.USER_RELATION, i))
        changes.append(_large_change(MergeEntityKind.TAG_RELATION, i))
    plan = MergePlan("contract-uid", "base", "local", "remote", changes=changes, conflicts=[])
    controller = ShareMergeDecisionController(plan)
    started = time.perf_counter()
    grouped = grouped_presented_items(controller.resolved_plan.resolution_items)
    elapsed = time.perf_counter() - started

    assert len(controller.resolved_plan.resolution_items) == 1900
    assert sum(len(items) for _group, items in grouped) == 1900
    assert {group for group, _items in grouped} >= {"Sistemler", "Teslimatlar", "Belgeler", "Platformlar", "Kullanıcılar", "Etiketler"}
    assert elapsed < 5.0


def test_value_formatter_long_text_preview_is_bounded():
    long_text = format_value("x" * 300)
    assert long_text.endswith("…") and len(long_text) <= 160


def test_detail_formatter_hides_raw_json_and_presents_delivery_semantics():
    from src.ui.presenters.share_merge_presenter import format_detail_value

    detail = format_detail_value({
        "merge_uid": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Teslimat 1",
        "status": "Başlanmadı",
        "planned_acceptance_date": "TBD",
        "payload_json": '{"raw": true}',
        "components": [
            {"name": "Hava Aracı", "planned": 3, "delivered": 0},
            {"name": "YKİ", "planned": 1, "delivered": 0},
            {"name": "YVT", "planned": 1, "delivered": 0},
        ],
        "note": "",
    })
    assert "Teslimat 1" in detail
    assert "Durum" in detail
    assert "Hava Aracı" in detail
    assert "Planlanan: 3" in detail
    assert "merge_uid" not in detail
    assert "payload_json" not in detail
    assert "{" not in detail and "}" not in detail


def test_detail_formatter_presents_unit_slots_without_dict_repr():
    from src.ui.presenters.share_merge_presenter import format_detail_value

    detail = format_detail_value([
        {"slot_no": 1, "identifier": "SER-1", "is_delivered": 0, "note": "QUEUE-1"},
        {"slot_no": 2, "identifier": "SER-2", "is_delivered": 0, "note": ""},
    ])
    assert "Kuyruk No / Seri No" in detail
    assert "#001" in detail and "SER-1" in detail
    assert "{'" not in detail and '"slot_no"' not in detail


def test_structural_validation_message_is_safe_and_actionable():
    resolved = ResolvedMergePlan(
        contract_merge_uid="contract-secret",
        base_snapshot_hash="a" * 64,
        local_snapshot_hash="b" * 64,
        remote_snapshot_hash="c" * 64,
        issues=[
  MergeResolutionIssue(
      "ABSENT_DELIVERY_PARENT_SYSTEM",
      "raw uid-secret deadbeef {'payload_json': true}",
      ("uid-secret",),
  ),
  MergeResolutionIssue(
      "ABSENT_FILE_PARENT_FOLDER",
      "raw file graph payload",
      ("file-secret",),
  ),
        ],
        summary={"structural_issue_count": 2},
    )
    message = structural_validation_message(resolved)
    assert "Teslimatın bağlı olduğu sistem doğrulanamadı" in message
    assert "(+1 sorun)" in message
    assert "uid-secret" not in message
    assert "deadbeef" not in message
    assert "payload_json" not in message
    assert "{" not in message and "}" not in message
