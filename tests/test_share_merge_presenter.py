from __future__ import annotations

from datetime import date

from src.models.share_merge_models import MergeChangeKind, MergeEntityKind
from src.models.share_merge_resolution_models import (
    MergeDecisionKind,
    MergeDecisionTarget,
    MergeDecisionTargetType,
    ResolutionItem,
)
from src.ui.presenters.share_merge_presenter import (
    decision_label,
    entity_group_label,
    field_label,
    format_value,
    present_item,
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
