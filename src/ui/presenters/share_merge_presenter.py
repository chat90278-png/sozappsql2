from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from src.domain.share_merge_resolution import resolve_merge_plan
from src.models.share_merge_models import MergeEntityKind, MergePlan
from src.models.share_merge_resolution_models import (
    MergeDecision,
    MergeDecisionKind,
    MergeDecisionSource,
    ResolutionItem,
    ResolvedMergePlan,
)


ENTITY_GROUP_LABELS = {
    MergeEntityKind.CONTRACT: "Sözleşme Bilgileri",
    MergeEntityKind.SYSTEM: "Sistemler",
    MergeEntityKind.DELIVERY: "Teslimatlar",
    MergeEntityKind.DOCUMENT_FOLDER: "Belgeler",
    MergeEntityKind.DOCUMENT_FILE: "Belgeler",
    MergeEntityKind.PLATFORM_RELATION: "Platformlar",
    MergeEntityKind.USER_RELATION: "Kullanıcılar",
    MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION: "Sorumlu Mühendisler",
    MergeEntityKind.TAG_RELATION: "Etiketler",
}

FIELD_LABELS = {
    "contract_no": "Sözleşme No",
    "yi_yd": "Yİ/YD",
    "contract_type": "Sözleşme Türü",
    "type_display": "Tür",
    "link_type": "Bağlantı Türü",
    "status": "Durum",
    "signed_date": "İmza Tarihi",
    "t0_date": "T0 Tarihi",
    "t0_months": "T0 Süresi",
    "completion_date": "Termin Tarihi",
    "planned_acceptance_date": "Planlanan Kabul Tarihi",
    "acceptance_date": "Kabul Tarihi",
    "content": "İçerik",
    "note": "Not",
    "is_main": "Ana Sözleşme",
    "name": "Ad",
    "filename": "Dosya Adı",
    "file_ext": "Uzantı",
    "mime_type": "Dosya Türü",
    "size_bytes": "Boyut",
    "folder_merge_uid": "Klasör",
    "parent_merge_uid": "Üst Klasör",
    "system_merge_uid": "Bağlı Sistem",
    "platform_id": "Platform",
    "sort_order": "Sıra",
    "payload_json": "Ek Bilgi",
    "delivery_user_id": "Teslimat Kullanıcısı",
    "sha256": "Dosya İçeriği",
    "color": "Renk",
    "is_primary": "Birincil",
    "full_name": "Ad Soyad",
}

DECISION_LABELS = {
    MergeDecisionKind.LOCAL_KEEP: "Bu STS'dekini Koru",
    MergeDecisionKind.REMOTE_USE: "Paylaşım Dosyasındakini Kullan",
    MergeDecisionKind.NO_ACTION: "Değişiklik Yok",
    MergeDecisionKind.SKIP: "Şimdilik Atla",
    MergeDecisionKind.DOCUMENT_KEEP_BOTH: "İki Dosyayı da Koru",
}

CHANGE_LABELS = {
    "REMOTE_ONLY": "Paylaşım dosyasında değişti",
    "LOCAL_ONLY": "Bu STS'de değişti",
    "SAME_CHANGE": "İki tarafta aynı değişiklik",
    "CONFLICT": "Çakışma",
    "REMOTE_ADDED": "Paylaşım dosyasında eklendi",
    "LOCAL_ADDED": "Bu STS'de eklendi",
    "SAME_ADDITION": "İki tarafta aynı eklendi",
    "ADD_ADD_CONFLICT": "İki tarafta farklı eklendi",
    "REMOTE_DELETED": "Paylaşım dosyasında silindi",
    "LOCAL_DELETED": "Bu STS'de silindi",
    "BOTH_DELETED": "İki tarafta silindi",
    "REMOTE_DELETE_LOCAL_UPDATE_CONFLICT": "Paylaşımda silindi, bu STS'de güncellendi",
    "LOCAL_DELETE_REMOTE_UPDATE_CONFLICT": "Bu STS'de silindi, paylaşımda güncellendi",
    "UPDATE_UPDATE_CONFLICT": "İki tarafta farklı güncellendi",
}

GROUP_ORDER = {
    "Sözleşme Bilgileri": 0,
    "Sistemler": 1,
    "Teslimatlar": 2,
    "Belgeler": 3,
    "Platformlar": 4,
    "Kullanıcılar": 5,
    "Sorumlu Mühendisler": 6,
    "Etiketler": 7,
}
ENTITY_FALLBACK_LABELS = {
    MergeEntityKind.CONTRACT: "Sözleşme",
    MergeEntityKind.SYSTEM: "Sistem",
    MergeEntityKind.DELIVERY: "Teslimat",
    MergeEntityKind.DOCUMENT_FOLDER: "Klasör",
    MergeEntityKind.DOCUMENT_FILE: "Dosya",
    MergeEntityKind.PLATFORM_RELATION: "Platform",
    MergeEntityKind.USER_RELATION: "Kullanıcı",
    MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION: "Sorumlu Mühendis",
    MergeEntityKind.TAG_RELATION: "Etiket",
}

UID_RE = re.compile(r"^[0-9a-fA-F]{8,}(?:-[0-9a-fA-F]{4,}){0,4}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class PresentedResolutionItem:
    item: ResolutionItem
    group_label: str
    title: str
    subtitle: str
    change_label: str
    base_display: str
    local_display: str
    remote_display: str
    base_detail: str
    local_detail: str
    remote_detail: str
    decision_labels: dict[MergeDecisionKind, str]


class ShareMergeDecisionController:
    def __init__(
        self,
        merge_plan: MergePlan,
        *,
        resolver: Callable[..., ResolvedMergePlan] = resolve_merge_plan,
    ):
        self.merge_plan = merge_plan
        self._resolver = resolver
        self._explicit: dict[str, MergeDecisionKind] = {}
        self.resolved_plan = self._resolve()

    def _resolve(self) -> ResolvedMergePlan:
        decisions = [
            MergeDecision(target_id, decision, MergeDecisionSource.USER)
            for target_id, decision in sorted(self._explicit.items())
        ]
        return self._resolver(self.merge_plan, decisions)

    @property
    def explicit_decisions(self) -> dict[str, MergeDecisionKind]:
        return dict(self._explicit)

    def set_decision(self, target_id: str, decision: MergeDecisionKind | str) -> ResolvedMergePlan:
        target = str(target_id or "")
        kind = decision if isinstance(decision, MergeDecisionKind) else MergeDecisionKind(str(decision))
        self._explicit[target] = kind
        self.resolved_plan = self._resolve()
        return self.resolved_plan

    def clear_decision(self, target_id: str) -> ResolvedMergePlan:
        self._explicit.pop(str(target_id or ""), None)
        self.resolved_plan = self._resolve()
        return self.resolved_plan

    def item_by_target(self, target_id: str) -> ResolutionItem | None:
        for item in self.resolved_plan.resolution_items:
            if item.target.target_id == target_id:
                return item
        return None

    def can_apply(self) -> bool:
        return self.resolved_plan.fully_resolved

    def live_summary(self) -> dict[str, int]:
        resolved = self.resolved_plan
        decisions = resolved.decisions
        return {
            "operation_count": int(resolved.summary.get("operation_count", 0)),
            "unresolved_conflict_count": int(resolved.summary.get("unresolved_conflict_count", 0)),
            "skip_count": int(resolved.summary.get("skip_count", 0)),
            "local_keep_count": sum(1 for d in decisions if d.decision == MergeDecisionKind.LOCAL_KEEP),
            "remote_use_count": sum(1 for d in decisions if d.decision == MergeDecisionKind.REMOTE_USE),
            "structural_issue_count": int(resolved.summary.get("structural_issue_count", 0)),
        }


def entity_group_label(kind: MergeEntityKind) -> str:
    return ENTITY_GROUP_LABELS.get(kind, "Diğer")


def decision_label(decision: MergeDecisionKind | str) -> str:
    try:
        kind = decision if isinstance(decision, MergeDecisionKind) else MergeDecisionKind(str(decision))
    except Exception:
        return str(decision or "")
    return DECISION_LABELS.get(kind, kind.value)


def field_label(field_name: str, field_path: str = "") -> str:
    field = str(field_name or "").strip()
    path = str(field_path or "")
    parts = path.split("/")
    if "components" in parts:
        if field == "qty":
            return "Miktar"
        if field == "note":
            return "Bileşen Notu"
        if field == "planned":
            return "Planlanan"
        if field == "delivered":
            return "Teslim Edilen"
    return FIELD_LABELS.get(field, _humanize_token(field))


def item_title(item: ResolutionItem) -> str:
    entity = _display_entity_label(item)
    field = item.target.field_name
    if item.target.target_type.value == "ENTITY" or field == "__entity__":
        return entity
    return f"{entity} > {field_label(field, item.target.field_path)}"


def item_subtitle(item: ResolutionItem) -> str:
    path = str(item.target.field_path or "")
    parts = path.split("/")
    if "components" in parts:
        idx = parts.index("components")
        if len(parts) > idx + 1:
            return f"Bileşen: {parts[idx + 1]}"
    if item.target.entity_kind == MergeEntityKind.DOCUMENT_FILE:
        filename = _filename_from_values(item)
        if filename:
            return filename
    if item.target.target_id:
        return f"Hedef: {item.target.target_id}"
    return ""


def present_item(item: ResolutionItem) -> PresentedResolutionItem:
    return PresentedResolutionItem(
        item=item,
        group_label=entity_group_label(item.target.entity_kind),
        title=item_title(item),
        subtitle=item_subtitle(item),
        change_label=CHANGE_LABELS.get(item.target.change_kind.value, item.target.change_kind.value),
        base_display=format_value(item.base_value, present=item.base_present),
        local_display=format_value(item.local_value, present=item.local_present),
        remote_display=format_value(item.remote_value, present=item.remote_present),
        base_detail=_detail_value(item.base_value),
        local_detail=_detail_value(item.local_value),
        remote_detail=_detail_value(item.remote_value),
        decision_labels={decision: decision_label(decision) for decision in item.allowed_decisions},
    )


def grouped_presented_items(items: list[ResolutionItem]) -> list[tuple[str, list[PresentedResolutionItem]]]:
    groups: dict[str, list[PresentedResolutionItem]] = {}
    for item in items:
        presented = present_item(item)
        groups.setdefault(presented.group_label, []).append(presented)
    return [
        (group, sorted(values, key=lambda x: (not x.item.is_conflict, x.title, x.item.target.target_id)))
        for group, values in sorted(groups.items(), key=lambda pair: (GROUP_ORDER.get(pair[0], 99), pair[0]))
    ]


def format_value(value: Any, *, present: bool = True, max_len: int = 160) -> str:
    if not present:
        return "Yok"
    if value is None:
        return "Boş"
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "Boş"
        if SHA_RE.match(text):
            return "Dosya içeriği değişti"
        if _looks_like_uid(text):
            return "Bağlı kayıt"
        return _ellipsize(text, max_len)
    if isinstance(value, dict):
        return _dict_summary(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "Boş liste"
        return f"{len(value)} kayıt"
    return _ellipsize(str(value), max_len)


def plan_summary_text(merge_plan: MergePlan) -> dict[str, int]:
    summary = dict(merge_plan.summary or {})
    return {
        "total": len(merge_plan.changes),
        "remote": int(summary.get("remote_only_count", 0)) + int(summary.get("remote_added_count", 0)) + int(summary.get("remote_deleted_count", 0)),
        "local": int(summary.get("local_only_count", 0)) + int(summary.get("local_added_count", 0)) + int(summary.get("local_deleted_count", 0)),
        "conflict": len(merge_plan.conflicts),
        "safe_remote": merge_plan.safe_remote_change_count,
    }


def _display_entity_label(item: ResolutionItem) -> str:
    label = str(item.entity_label or "").strip()
    if label and not _looks_like_uid(label):
        return label
    for value in (item.remote_value, item.local_value, item.base_value):
        if isinstance(value, dict):
            for key in ("name", "filename", "contract_no", "full_name"):
                text = str(value.get(key) or "").strip()
                if text and not _looks_like_uid(text):
                    return text
    fallback = ENTITY_FALLBACK_LABELS.get(item.target.entity_kind, "Kayıt")
    return f"{fallback} ({item.target.entity_uid[:8]})"


def _filename_from_values(item: ResolutionItem) -> str:
    for value in (item.remote_value, item.local_value, item.base_value):
        if isinstance(value, dict):
            text = str(value.get("filename") or "").strip()
            if text:
                return text
    return ""


def _dict_summary(value: dict[str, Any]) -> str:
    for key in ("name", "filename", "contract_no", "full_name"):
        text = str(value.get(key) or "").strip()
        if text and not _looks_like_uid(text):
            return _ellipsize(text, 120)
    if "sha256" in value:
        return "Dosya içeriği"
    keys = [FIELD_LABELS.get(str(k), _humanize_token(str(k))) for k in value.keys() if not SHA_RE.match(str(value.get(k) or ""))]
    return ", ".join(keys[:4]) + (f" +{len(keys) - 4}" if len(keys) > 4 else "")


def _detail_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _humanize_token(value: str) -> str:
    text = str(value or "").strip("_ ")
    if not text:
        return "Alan"
    return " ".join(part.capitalize() for part in text.split("_"))


def _ellipsize(text: str, max_len: int) -> str:
    text = str(text or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _looks_like_uid(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text and (UID_RE.match(text) or SHA_RE.match(text)))
