from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable

from src.domain.contract_snapshot import normalize_contract_snapshot
from src.models.share_merge_models import MergeChange, MergeChangeKind, MergeEntityKind, MergePlan
from src.models.share_merge_resolution_models import (
    MergeDecision,
    MergeDecisionKind,
    MergeDecisionSource,
    MergeDecisionTarget,
    MergeDecisionTargetType,
    MergeOperation,
    MergeOperationKind,
    MergeResolutionIssue,
    ResolutionItem,
    ResolvedMergePlan,
)


class ShareMergeResolutionError(RuntimeError):
    pass


class MergeDecisionError(ShareMergeResolutionError):
    pass


class UnknownMergeDecisionTargetError(MergeDecisionError):
    pass


class DuplicateMergeDecisionError(MergeDecisionError):
    pass


class InvalidMergeDecisionError(MergeDecisionError):
    pass


class UnresolvedMergeConflictError(MergeDecisionError):
    pass


class MergeOperationBuildError(ShareMergeResolutionError):
    pass


class MergeOperationDependencyError(MergeOperationBuildError):
    pass


class InvalidProjectedMergeGraphError(MergeOperationBuildError):
    pass


_CONFLICT_KINDS = {
    MergeChangeKind.CONFLICT,
    MergeChangeKind.ADD_ADD_CONFLICT,
    MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT,
    MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT,
    MergeChangeKind.UPDATE_UPDATE_CONFLICT,
}
_ENTITY_KINDS = {
    MergeChangeKind.REMOTE_ADDED,
    MergeChangeKind.LOCAL_ADDED,
    MergeChangeKind.SAME_ADDITION,
    MergeChangeKind.ADD_ADD_CONFLICT,
    MergeChangeKind.REMOTE_DELETED,
    MergeChangeKind.LOCAL_DELETED,
    MergeChangeKind.BOTH_DELETED,
    MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT,
    MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT,
}

CONTRACT_FIELDS = {
    "contract_no", "yi_yd", "contract_type", "type_display", "link_type", "status", "signed_date",
    "t0_date", "t0_months", "completion_date", "acceptance_date", "content", "note", "is_main",
}


def _json_safe(value: Any) -> Any:
    value = normalize_contract_snapshot(copy.deepcopy(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _target_type(change: MergeChange) -> MergeDecisionTargetType:
    return MergeDecisionTargetType.ENTITY if change.field_name == "__entity__" or change.change_kind in _ENTITY_KINDS else MergeDecisionTargetType.FIELD


def target_id_for_change(change: MergeChange) -> str:
    if _target_type(change) == MergeDecisionTargetType.ENTITY:
        return f"ENTITY|{change.entity_kind.value}|{change.entity_uid}"
    return f"FIELD|{change.entity_kind.value}|{change.entity_uid}|{change.field_path}"


def _conflict_type_for_change(plan: MergePlan, change: MergeChange):
    for conflict in plan.conflicts:
        if conflict.entity_kind == change.entity_kind and conflict.entity_uid == change.entity_uid and conflict.field_path == change.field_path:
            return conflict.conflict_type
    return None


def default_decision_for(change_kind: MergeChangeKind) -> tuple[MergeDecisionKind, bool]:
    if change_kind in {MergeChangeKind.REMOTE_ONLY, MergeChangeKind.REMOTE_ADDED, MergeChangeKind.REMOTE_DELETED}:
        return MergeDecisionKind.REMOTE_USE, False
    if change_kind in {MergeChangeKind.LOCAL_ONLY, MergeChangeKind.LOCAL_ADDED, MergeChangeKind.LOCAL_DELETED}:
        return MergeDecisionKind.LOCAL_KEEP, False
    if change_kind in {MergeChangeKind.SAME_CHANGE, MergeChangeKind.SAME_ADDITION, MergeChangeKind.BOTH_DELETED}:
        return MergeDecisionKind.NO_ACTION, False
    if change_kind in _CONFLICT_KINDS:
        return MergeDecisionKind.LOCAL_KEEP, True
    return MergeDecisionKind.NO_ACTION, False


def _is_document_content_target(change: MergeChange) -> bool:
    return change.entity_kind == MergeEntityKind.DOCUMENT_FILE and change.field_name == "sha256" and bool(change.remote_present)


def allowed_decisions_for(change: MergeChange) -> tuple[MergeDecisionKind, ...]:
    kind = change.change_kind
    if kind == MergeChangeKind.REMOTE_ONLY:
        allowed = [MergeDecisionKind.REMOTE_USE, MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.LOCAL_ONLY:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.SAME_CHANGE:
        allowed = [MergeDecisionKind.NO_ACTION]
    elif kind == MergeChangeKind.CONFLICT:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.REMOTE_ADDED:
        allowed = [MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.LOCAL_ADDED:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.SAME_ADDITION:
        allowed = [MergeDecisionKind.NO_ACTION]
    elif kind == MergeChangeKind.ADD_ADD_CONFLICT:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
        if change.entity_kind == MergeEntityKind.DOCUMENT_FILE and change.remote_present:
            allowed.append(MergeDecisionKind.DOCUMENT_KEEP_BOTH)
    elif kind == MergeChangeKind.REMOTE_DELETED:
        allowed = [MergeDecisionKind.REMOTE_USE, MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.LOCAL_DELETED:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
    elif kind == MergeChangeKind.BOTH_DELETED:
        allowed = [MergeDecisionKind.NO_ACTION]
    elif kind in {MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT, MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT}:
        allowed = [MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.REMOTE_USE, MergeDecisionKind.SKIP]
    else:
        allowed = [MergeDecisionKind.NO_ACTION]
    if kind == MergeChangeKind.CONFLICT and _is_document_content_target(change):
        allowed.append(MergeDecisionKind.DOCUMENT_KEEP_BOTH)
    return tuple(dict.fromkeys(allowed))


def build_resolution_items(merge_plan: MergePlan) -> list[ResolutionItem]:
    items: list[ResolutionItem] = []
    seen: set[str] = set()
    for change in sorted(merge_plan.changes, key=lambda c: (target_id_for_change(c), c.change_kind.value)):
        target_id = target_id_for_change(change)
        if target_id in seen:
            continue
        seen.add(target_id)
        default_decision, requires_user = default_decision_for(change.change_kind)
        target = MergeDecisionTarget(
            target_id=target_id,
            target_type=_target_type(change),
            entity_kind=change.entity_kind,
            entity_uid=change.entity_uid,
            field_path=change.field_path,
            field_name=change.field_name,
            change_kind=change.change_kind,
            conflict_type=_conflict_type_for_change(merge_plan, change),
        )
        items.append(ResolutionItem(
            target=target,
            entity_label=change.entity_label,
            base_value=_json_safe(change.base_value),
            local_value=_json_safe(change.local_value),
            remote_value=_json_safe(change.remote_value),
            base_present=change.base_present,
            local_present=change.local_present,
            remote_present=change.remote_present,
            default_decision=default_decision,
            allowed_decisions=allowed_decisions_for(change),
            requires_user_decision=requires_user,
            is_conflict=change.change_kind in _CONFLICT_KINDS,
            reason_code=(change.change_kind.value if change.change_kind in _CONFLICT_KINDS else ""),
        ))
    return items


def _parse_decisions(decisions: Any) -> list[MergeDecision]:
    if decisions is None:
        return []
    parsed: list[MergeDecision] = []
    if isinstance(decisions, dict):
        for target_id, decision in decisions.items():
            parsed.append(MergeDecision(str(target_id), decision if isinstance(decision, MergeDecisionKind) else MergeDecisionKind(str(decision))))
        return parsed
    for item in decisions:
        if isinstance(item, MergeDecision):
            parsed.append(item)
        elif isinstance(item, dict):
            parsed.append(MergeDecision.from_dict(item))
        else:
            raise InvalidMergeDecisionError("Decision listesi MergeDecision veya dict içermeli.")
    return parsed


def _decision_map(decisions: Any, item_map: dict[str, ResolutionItem]) -> dict[str, MergeDecision]:
    out: dict[str, MergeDecision] = {}
    for decision in _parse_decisions(decisions):
        if decision.target_id not in item_map:
            raise UnknownMergeDecisionTargetError(f"Bilinmeyen merge decision target: {decision.target_id}")
        if decision.target_id in out:
            raise DuplicateMergeDecisionError(f"Duplicate merge decision target: {decision.target_id}")
        item = item_map[decision.target_id]
        if decision.decision not in item.allowed_decisions:
            raise InvalidMergeDecisionError(f"{decision.decision.value} kararı {decision.target_id} için geçerli değil.")
        if decision.decision == MergeDecisionKind.DOCUMENT_KEEP_BOTH and not _keep_both_allowed(item):
            raise InvalidMergeDecisionError("DOCUMENT_KEEP_BOTH yalnızca uygun document file content conflict/add-add context'inde geçerlidir.")
        out[decision.target_id] = decision
    return out


def _keep_both_allowed(item: ResolutionItem) -> bool:
    return item.target.entity_kind == MergeEntityKind.DOCUMENT_FILE and item.remote_present and (
        item.target.change_kind == MergeChangeKind.ADD_ADD_CONFLICT or
        (item.target.change_kind == MergeChangeKind.CONFLICT and item.target.field_name == "sha256")
    )


def _selected_decision(item: ResolutionItem, explicit: dict[str, MergeDecision]) -> tuple[MergeDecision, bool]:
    if item.target.target_id in explicit:
        return explicit[item.target.target_id], True
    return MergeDecision(item.target.target_id, item.default_decision, MergeDecisionSource.DEFAULT), False


def _op_id(kind: MergeOperationKind, target_id: str, extra: str = "") -> str:
    raw = f"{kind.value}|{target_id}|{extra}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entity_op_kind(entity_kind: MergeEntityKind, action: str) -> MergeOperationKind:
    table = {
        (MergeEntityKind.SYSTEM, "ADD"): MergeOperationKind.ADD_SYSTEM,
        (MergeEntityKind.SYSTEM, "DELETE"): MergeOperationKind.DELETE_SYSTEM,
        (MergeEntityKind.DELIVERY, "ADD"): MergeOperationKind.ADD_DELIVERY,
        (MergeEntityKind.DELIVERY, "DELETE"): MergeOperationKind.DELETE_DELIVERY,
        (MergeEntityKind.DOCUMENT_FOLDER, "ADD"): MergeOperationKind.ADD_DOCUMENT_FOLDER,
        (MergeEntityKind.DOCUMENT_FOLDER, "DELETE"): MergeOperationKind.DELETE_DOCUMENT_FOLDER,
        (MergeEntityKind.DOCUMENT_FILE, "ADD"): MergeOperationKind.ADD_DOCUMENT_FILE,
        (MergeEntityKind.DOCUMENT_FILE, "DELETE"): MergeOperationKind.DELETE_DOCUMENT_FILE,
        (MergeEntityKind.PLATFORM_RELATION, "ADD"): MergeOperationKind.ADD_PLATFORM_RELATION,
        (MergeEntityKind.PLATFORM_RELATION, "DELETE"): MergeOperationKind.DELETE_PLATFORM_RELATION,
        (MergeEntityKind.USER_RELATION, "ADD"): MergeOperationKind.ADD_USER_RELATION,
        (MergeEntityKind.USER_RELATION, "DELETE"): MergeOperationKind.DELETE_USER_RELATION,
        (MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION, "ADD"): MergeOperationKind.ADD_RESPONSIBLE_ENGINEER_RELATION,
        (MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION, "DELETE"): MergeOperationKind.DELETE_RESPONSIBLE_ENGINEER_RELATION,
        (MergeEntityKind.TAG_RELATION, "ADD"): MergeOperationKind.ADD_TAG_RELATION,
        (MergeEntityKind.TAG_RELATION, "DELETE"): MergeOperationKind.DELETE_TAG_RELATION,
    }
    return table[(entity_kind, action)]


def _field_operation_kind(item: ResolutionItem) -> MergeOperationKind:
    kind = item.target.entity_kind
    field = item.target.field_name
    path = item.target.field_path
    if kind == MergeEntityKind.CONTRACT:
        if field not in CONTRACT_FIELDS:
            raise MergeOperationBuildError(f"Bilinmeyen contract field operation: {field}")
        return MergeOperationKind.SET_CONTRACT_FIELD
    if kind == MergeEntityKind.SYSTEM:
        if "/components/" in path:
            return MergeOperationKind.SET_SYSTEM_COMPONENT_NOTE if field == "note" else MergeOperationKind.SET_SYSTEM_COMPONENT
        return MergeOperationKind.SET_SYSTEM_FIELD
    if kind == MergeEntityKind.DELIVERY:
        if "/components/" in path:
            return MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD
        return MergeOperationKind.SET_DELIVERY_FIELD
    if kind == MergeEntityKind.DOCUMENT_FOLDER:
        return MergeOperationKind.SET_DOCUMENT_FOLDER_FIELD
    if kind == MergeEntityKind.DOCUMENT_FILE:
        if field == "sha256":
            return MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT
        return MergeOperationKind.SET_DOCUMENT_FILE_FIELD
    if kind == MergeEntityKind.PLATFORM_RELATION:
        return MergeOperationKind.SET_PLATFORM_RELATION_FIELD
    if kind == MergeEntityKind.USER_RELATION:
        return MergeOperationKind.SET_USER_RELATION_FIELD
    if kind == MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION:
        return MergeOperationKind.SET_RESPONSIBLE_ENGINEER_RELATION_FIELD
    if kind == MergeEntityKind.TAG_RELATION:
        return MergeOperationKind.SET_TAG_RELATION_FIELD
    raise MergeOperationBuildError(f"Unsupported field operation entity kind: {kind.value}")


def _component_metadata(item: ResolutionItem) -> dict[str, Any]:
    parts = item.target.field_path.split("/")
    if "components" in parts:
        idx = parts.index("components")
        if len(parts) > idx + 2:
            return {"component_name": parts[idx + 1], "component_field": parts[idx + 2]}
    return {}


def _field_operation(item: ResolutionItem, decision: MergeDecision) -> MergeOperation | None:
    if decision.decision == MergeDecisionKind.SKIP:
        return None
    if decision.decision in {MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.NO_ACTION}:
        return None
    if decision.decision == MergeDecisionKind.DOCUMENT_KEEP_BOTH:
        return _keep_both_operation(item, decision)
    if decision.decision != MergeDecisionKind.REMOTE_USE:
        return None
    op_kind = _field_operation_kind(item)
    metadata = _component_metadata(item)
    if op_kind == MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT:
        metadata["expected_remote_sha256"] = item.remote_value
    return MergeOperation(
        operation_id=_op_id(op_kind, item.target.target_id),
        operation_kind=op_kind,
        entity_kind=item.target.entity_kind,
        entity_uid=item.target.entity_uid,
        entity_label=item.entity_label,
        field_path=item.target.field_path,
        field_name=item.target.field_name,
        value=_json_safe(item.remote_value),
        value_present=item.remote_present,
        source_target_id=item.target.target_id,
        metadata=metadata,
    )


def _entity_operation(item: ResolutionItem, decision: MergeDecision) -> MergeOperation | None:
    if decision.decision in {MergeDecisionKind.SKIP, MergeDecisionKind.LOCAL_KEEP, MergeDecisionKind.NO_ACTION}:
        return None
    if decision.decision == MergeDecisionKind.DOCUMENT_KEEP_BOTH:
        return _keep_both_operation(item, decision)
    if decision.decision != MergeDecisionKind.REMOTE_USE:
        return None
    ck = item.target.change_kind
    if ck in {MergeChangeKind.REMOTE_ADDED, MergeChangeKind.ADD_ADD_CONFLICT, MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT}:
        op_kind = _entity_op_kind(item.target.entity_kind, "ADD")
        value = item.remote_value
        value_present = item.remote_present
    elif ck in {MergeChangeKind.REMOTE_DELETED, MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT}:
        op_kind = _entity_op_kind(item.target.entity_kind, "DELETE")
        value = None
        value_present = False
    elif ck == MergeChangeKind.LOCAL_DELETED:
        op_kind = _entity_op_kind(item.target.entity_kind, "ADD")
        value = item.remote_value
        value_present = item.remote_present
    elif ck == MergeChangeKind.LOCAL_ADDED:
        op_kind = _entity_op_kind(item.target.entity_kind, "DELETE")
        value = None
        value_present = False
    else:
        return None
    return MergeOperation(
        operation_id=_op_id(op_kind, item.target.target_id),
        operation_kind=op_kind,
        entity_kind=item.target.entity_kind,
        entity_uid=item.target.entity_uid,
        entity_label=item.entity_label,
        value=_json_safe(value),
        value_present=value_present,
        source_target_id=item.target.target_id,
        metadata={"entity_snapshot": _json_safe(value)} if value_present else {},
    )


def _keep_both_operation(item: ResolutionItem, decision: MergeDecision) -> MergeOperation:
    if not _keep_both_allowed(item):
        raise InvalidMergeDecisionError("DOCUMENT_KEEP_BOTH sadece document file content conflict veya add/add conflict için kullanılabilir.")
    remote = item.remote_value if isinstance(item.remote_value, dict) else {}
    if item.target.target_type == MergeDecisionTargetType.FIELD:
        remote = {
            "merge_uid": item.target.entity_uid,
            "sha256": item.remote_value,
        }
    metadata = {
        "source_remote_file_merge_uid": item.target.entity_uid,
        "remote_sha256": remote.get("sha256", item.remote_value),
        "remote_filename": remote.get("filename", ""),
        "remote_folder_merge_uid": remote.get("folder_merge_uid", ""),
        "remote_note": remote.get("note", ""),
        "remote_file_ext": remote.get("file_ext", ""),
        "remote_mime_type": remote.get("mime_type", ""),
    }
    return MergeOperation(
        operation_id=_op_id(MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE, item.target.target_id),
        operation_kind=MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE,
        entity_kind=item.target.entity_kind,
        entity_uid=item.target.entity_uid,
        entity_label=item.entity_label,
        value=_json_safe(remote),
        value_present=True,
        source_target_id=item.target.target_id,
        metadata=_json_safe(metadata),
    )


def _compile_operations(items: list[ResolutionItem], decisions: list[MergeDecision]) -> list[MergeOperation]:
    decision_by_target = {d.target_id: d for d in decisions}
    operations: list[MergeOperation] = []
    for item in items:
        decision = decision_by_target[item.target.target_id]
        if item.requires_user_decision and decision.source == MergeDecisionSource.DEFAULT:
            continue
        if item.target.target_type == MergeDecisionTargetType.ENTITY:
            op = _entity_operation(item, decision)
        else:
            op = _field_operation(item, decision)
        if op is not None:
            operations.append(op)
    return _sort_operations(operations)


def _entity_snapshot_from_item(item: ResolutionItem, decision: MergeDecision) -> dict[str, Any] | None:
    if decision.decision == MergeDecisionKind.REMOTE_USE and item.remote_present and isinstance(item.remote_value, dict):
        return item.remote_value
    if item.local_present and isinstance(item.local_value, dict):
        return item.local_value
    if item.base_present and isinstance(item.base_value, dict):
        return item.base_value
    return None


def _items_by_target(items: Iterable[ResolutionItem]) -> dict[str, ResolutionItem]:
    return {i.target.target_id: i for i in items}


def _snapshot_maps(snapshot: dict | None) -> dict[MergeEntityKind, dict[str, dict]]:
    snapshot = normalize_contract_snapshot(snapshot or {}) if snapshot else {}
    def by_uid(key):
        return {str(x.get("merge_uid") or x.get("stable_uid") or x.get("name") or ""): x for x in snapshot.get(key, []) if isinstance(x, dict)}
    return {
        MergeEntityKind.SYSTEM: by_uid("systems"),
        MergeEntityKind.DELIVERY: by_uid("deliveries"),
        MergeEntityKind.DOCUMENT_FOLDER: by_uid("folders"),
        MergeEntityKind.DOCUMENT_FILE: by_uid("files"),
    }


def _projected_graph_issues(items: list[ResolutionItem], decisions: list[MergeDecision], operations: list[MergeOperation],
                            base_snapshot: dict | None, local_snapshot: dict | None, remote_snapshot: dict | None) -> list[MergeResolutionIssue]:
    decision_by_target = {d.target_id: d for d in decisions}
    item_by_target = _items_by_target(items)
    local_maps = _snapshot_maps(local_snapshot)
    remote_maps = _snapshot_maps(remote_snapshot)
    final_sets = {kind: set(local_maps.get(kind, {})) for kind in (MergeEntityKind.SYSTEM, MergeEntityKind.DELIVERY, MergeEntityKind.DOCUMENT_FOLDER, MergeEntityKind.DOCUMENT_FILE)}
    entity_data: dict[tuple[MergeEntityKind, str], dict] = {}
    for kind, mapping in local_maps.items():
        for uid, data in mapping.items():
            entity_data[(kind, uid)] = data
    for op in operations:
        if op.operation_kind in {MergeOperationKind.ADD_SYSTEM, MergeOperationKind.ADD_DELIVERY, MergeOperationKind.ADD_DOCUMENT_FOLDER, MergeOperationKind.ADD_DOCUMENT_FILE}:
            final_sets[op.entity_kind].add(op.entity_uid)
            if isinstance(op.value, dict):
                entity_data[(op.entity_kind, op.entity_uid)] = op.value
        elif op.operation_kind in {MergeOperationKind.DELETE_SYSTEM, MergeOperationKind.DELETE_DELIVERY, MergeOperationKind.DELETE_DOCUMENT_FOLDER, MergeOperationKind.DELETE_DOCUMENT_FILE}:
            final_sets[op.entity_kind].discard(op.entity_uid)
    for kind, mapping in remote_maps.items():
        for uid, data in mapping.items():
            entity_data.setdefault((kind, uid), data)
    for op in operations:
        if op.operation_kind == MergeOperationKind.SET_DELIVERY_FIELD and op.field_name == "system_merge_uid":
            entity_data.setdefault((MergeEntityKind.DELIVERY, op.entity_uid), {})["system_merge_uid"] = op.value if op.value_present else ""
        if op.operation_kind == MergeOperationKind.SET_DOCUMENT_FOLDER_FIELD and op.field_name == "parent_merge_uid":
            entity_data.setdefault((MergeEntityKind.DOCUMENT_FOLDER, op.entity_uid), {})["parent_merge_uid"] = op.value if op.value_present else ""
        if op.operation_kind == MergeOperationKind.SET_DOCUMENT_FILE_FIELD and op.field_name == "folder_merge_uid":
            entity_data.setdefault((MergeEntityKind.DOCUMENT_FILE, op.entity_uid), {})["folder_merge_uid"] = op.value if op.value_present else ""

    issues: list[MergeResolutionIssue] = []
    deleted_systems = {op.entity_uid for op in operations if op.operation_kind == MergeOperationKind.DELETE_SYSTEM}
    for uid in sorted(final_sets[MergeEntityKind.DELIVERY]):
        data = entity_data.get((MergeEntityKind.DELIVERY, uid), {})
        parent = str(data.get("system_merge_uid") or "")
        if parent and parent not in final_sets[MergeEntityKind.SYSTEM]:
            issues.append(MergeResolutionIssue("ABSENT_DELIVERY_PARENT_SYSTEM", "Delivery target system final graph içinde yok.", (uid,)))
    for system_uid in sorted(deleted_systems):
        retained = [uid for uid in final_sets[MergeEntityKind.DELIVERY] if str(entity_data.get((MergeEntityKind.DELIVERY, uid), {}).get("system_merge_uid") or "") == system_uid]
        if retained:
            issues.append(MergeResolutionIssue("PARENT_DELETE_CHILD_KEEP_CONFLICT", "System delete seçilmiş ancak child delivery korunuyor.", tuple(retained)))

    for uid in sorted(final_sets[MergeEntityKind.DOCUMENT_FOLDER]):
        data = entity_data.get((MergeEntityKind.DOCUMENT_FOLDER, uid), {})
        parent = str(data.get("parent_merge_uid") or "")
        if parent and parent not in final_sets[MergeEntityKind.DOCUMENT_FOLDER]:
            issues.append(MergeResolutionIssue("ABSENT_FOLDER_PARENT", "Folder target parent final graph içinde yok.", (uid,)))
    for uid in sorted(final_sets[MergeEntityKind.DOCUMENT_FILE]):
        data = entity_data.get((MergeEntityKind.DOCUMENT_FILE, uid), {})
        parent = str(data.get("folder_merge_uid") or "")
        if parent and parent not in final_sets[MergeEntityKind.DOCUMENT_FOLDER]:
            issues.append(MergeResolutionIssue("ABSENT_FILE_PARENT_FOLDER", "File target folder final graph içinde yok.", (uid,)))
    deleted_folders = {op.entity_uid for op in operations if op.operation_kind == MergeOperationKind.DELETE_DOCUMENT_FOLDER}
    for folder_uid in sorted(deleted_folders):
        child_folders = [uid for uid in final_sets[MergeEntityKind.DOCUMENT_FOLDER] if str(entity_data.get((MergeEntityKind.DOCUMENT_FOLDER, uid), {}).get("parent_merge_uid") or "") == folder_uid]
        child_files = [uid for uid in final_sets[MergeEntityKind.DOCUMENT_FILE] if str(entity_data.get((MergeEntityKind.DOCUMENT_FILE, uid), {}).get("folder_merge_uid") or "") == folder_uid]
        if child_folders or child_files:
            issues.append(MergeResolutionIssue("FOLDER_DELETE_CHILD_KEEP_CONFLICT", "Folder delete seçilmiş ancak child folder/file korunuyor.", tuple(child_folders + child_files)))
    cycle = _folder_cycle(final_sets[MergeEntityKind.DOCUMENT_FOLDER], entity_data)
    if cycle:
        issues.append(MergeResolutionIssue("FOLDER_PARENT_CYCLE", "Folder parent graph cycle içeriyor.", tuple(cycle)))
    return issues


def _folder_cycle(folder_ids: set[str], entity_data: dict[tuple[MergeEntityKind, str], dict]) -> list[str]:
    parents = {uid: str(entity_data.get((MergeEntityKind.DOCUMENT_FOLDER, uid), {}).get("parent_merge_uid") or "") for uid in folder_ids}
    for uid in sorted(folder_ids):
        seen: list[str] = []
        cur = uid
        while cur:
            if cur in seen:
                return seen[seen.index(cur):] + [cur]
            seen.append(cur)
            cur = parents.get(cur, "")
    return []


def _priority(op: MergeOperation) -> tuple[int, int, str, str]:
    folder_depth = int(op.metadata.get("folder_depth", 0) or 0)
    delete_folder_depth = -folder_depth
    table = {
        MergeOperationKind.SET_CONTRACT_FIELD: 10,
        MergeOperationKind.ADD_PLATFORM_RELATION: 20,
        MergeOperationKind.ADD_USER_RELATION: 20,
        MergeOperationKind.ADD_RESPONSIBLE_ENGINEER_RELATION: 20,
        MergeOperationKind.ADD_TAG_RELATION: 20,
        MergeOperationKind.SET_PLATFORM_RELATION_FIELD: 25,
        MergeOperationKind.SET_USER_RELATION_FIELD: 25,
        MergeOperationKind.SET_RESPONSIBLE_ENGINEER_RELATION_FIELD: 25,
        MergeOperationKind.SET_TAG_RELATION_FIELD: 25,
        MergeOperationKind.ADD_SYSTEM: 30,
        MergeOperationKind.SET_SYSTEM_FIELD: 40,
        MergeOperationKind.SET_SYSTEM_COMPONENT: 41,
        MergeOperationKind.SET_SYSTEM_COMPONENT_NOTE: 42,
        MergeOperationKind.ADD_DELIVERY: 50,
        MergeOperationKind.SET_DELIVERY_FIELD: 60,
        MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD: 61,
        MergeOperationKind.ADD_DOCUMENT_FOLDER: 70,
        MergeOperationKind.SET_DOCUMENT_FOLDER_FIELD: 80,
        MergeOperationKind.ADD_DOCUMENT_FILE: 90,
        MergeOperationKind.SET_DOCUMENT_FILE_FIELD: 100,
        MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT: 101,
        MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE: 102,
        MergeOperationKind.DELETE_PLATFORM_RELATION: 110,
        MergeOperationKind.DELETE_USER_RELATION: 110,
        MergeOperationKind.DELETE_RESPONSIBLE_ENGINEER_RELATION: 110,
        MergeOperationKind.DELETE_TAG_RELATION: 110,
        MergeOperationKind.DELETE_DOCUMENT_FILE: 120,
        MergeOperationKind.DELETE_DOCUMENT_FOLDER: 130,
        MergeOperationKind.DELETE_DELIVERY: 140,
        MergeOperationKind.DELETE_SYSTEM: 150,
    }
    depth = folder_depth if op.operation_kind == MergeOperationKind.ADD_DOCUMENT_FOLDER else delete_folder_depth if op.operation_kind == MergeOperationKind.DELETE_DOCUMENT_FOLDER else 0
    return (table.get(op.operation_kind, 999), depth, op.entity_kind.value, op.entity_uid)


def _with_folder_depths(operations: list[MergeOperation]) -> list[MergeOperation]:
    add_values = {op.entity_uid: op.value for op in operations if op.operation_kind == MergeOperationKind.ADD_DOCUMENT_FOLDER and isinstance(op.value, dict)}
    delete_values = {op.entity_uid: op.value for op in operations if op.operation_kind == MergeOperationKind.DELETE_DOCUMENT_FOLDER and isinstance(op.value, dict)}
    all_values = {**add_values, **delete_values}

    def depth(uid: str, stack: tuple[str, ...] = ()) -> int:
        if uid in stack:
            return 0
        parent = str((all_values.get(uid) or {}).get("parent_merge_uid") or "")
        if not parent or parent not in all_values:
            return 0
        return 1 + depth(parent, stack + (uid,))

    out = []
    for op in operations:
        if op.operation_kind in {MergeOperationKind.ADD_DOCUMENT_FOLDER, MergeOperationKind.DELETE_DOCUMENT_FOLDER}:
            meta = dict(op.metadata)
            meta["folder_depth"] = depth(op.entity_uid)
            out.append(MergeOperation(**{**op.__dict__, "metadata": meta}))
        else:
            out.append(op)
    return out


def _sort_operations(operations: list[MergeOperation]) -> list[MergeOperation]:
    operations = _with_folder_depths(operations)
    return sorted(operations, key=_priority)


def serialize_merge_operations(operations: Iterable[MergeOperation]) -> str:
    payload = []
    for op in operations:
        payload.append({
            "operation_id": op.operation_id,
            "operation_kind": op.operation_kind.value,
            "entity_kind": op.entity_kind.value,
            "entity_uid": op.entity_uid,
            "entity_label": op.entity_label,
            "field_path": op.field_path,
            "field_name": op.field_name,
            "value": _json_safe(op.value),
            "value_present": op.value_present,
            "source_target_id": op.source_target_id,
            "metadata": _json_safe(op.metadata),
        })
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_merge_operations(operations: Iterable[MergeOperation]) -> str:
    return hashlib.sha256(serialize_merge_operations(operations).encode("utf-8")).hexdigest()


def resolve_merge_plan(merge_plan: MergePlan, decisions: Any = None, *, require_all_conflicts_resolved: bool = False,
                       base_snapshot: dict | None = None, local_snapshot: dict | None = None,
                       remote_snapshot: dict | None = None) -> ResolvedMergePlan:
    items = build_resolution_items(merge_plan)
    item_map = {item.target.target_id: item for item in items}
    explicit = _decision_map(decisions, item_map)
    effective: list[MergeDecision] = []
    issues: list[MergeResolutionIssue] = []
    for item in items:
        decision, is_explicit = _selected_decision(item, explicit)
        if item.requires_user_decision and not is_explicit:
            issues.append(MergeResolutionIssue("UNRESOLVED_CONFLICT", "Conflict için explicit decision verilmedi.", (item.target.target_id,)))
        effective.append(decision)
    if require_all_conflicts_resolved and any(i.code == "UNRESOLVED_CONFLICT" for i in issues):
        raise UnresolvedMergeConflictError("Çözümlenmemiş conflict var.")
    operations = _compile_operations(items, effective)
    issues.extend(_projected_graph_issues(items, effective, operations, base_snapshot, local_snapshot, remote_snapshot))
    return ResolvedMergePlan(
        contract_merge_uid=merge_plan.contract_merge_uid,
        base_snapshot_hash=merge_plan.base_snapshot_hash,
        local_snapshot_hash=merge_plan.local_snapshot_hash,
        remote_snapshot_hash=merge_plan.remote_snapshot_hash,
        resolution_items=items,
        decisions=effective,
        operations=operations,
        issues=issues,
        summary={
            "resolution_item_count": len(items),
            "operation_count": len(operations),
            "unresolved_conflict_count": sum(1 for i in issues if i.code == "UNRESOLVED_CONFLICT"),
            "structural_issue_count": sum(1 for i in issues if i.code != "UNRESOLVED_CONFLICT" and i.severity == "ERROR"),
            "skip_count": sum(1 for d in effective if d.decision == MergeDecisionKind.SKIP),
        },
        operations_hash=hash_merge_operations(operations),
    )


def resolve_safe_remote_changes(merge_plan: MergePlan, **kwargs: Any) -> ResolvedMergePlan:
    return resolve_merge_plan(merge_plan, decisions=None, **kwargs)
