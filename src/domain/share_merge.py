from __future__ import annotations

from typing import Any, Iterable

from src.domain.contract_snapshot import hash_contract_snapshot, normalize_contract_snapshot
from src.models.share_merge_models import (
    SUMMARY_KEYS,
    MergeChange,
    MergeChangeKind,
    MergeConflict,
    MergeConflictType,
    MergeEntityKind,
    MergePlan,
)


class ShareMergeError(RuntimeError):
    pass


class MergeSnapshotError(ShareMergeError):
    pass


class MergeSnapshotIdentityError(MergeSnapshotError):
    pass


class DuplicateMergeIdentityError(MergeSnapshotError):
    pass


_MISSING = object()


def values_equal(a: Any, b: Any) -> bool:
    return a == b


def classify_value_change(base: Any, local: Any, remote: Any) -> MergeChangeKind:
    if values_equal(local, base) and values_equal(remote, base):
        return MergeChangeKind.UNCHANGED
    if values_equal(local, base) and not values_equal(remote, base):
        return MergeChangeKind.REMOTE_ONLY
    if not values_equal(local, base) and values_equal(remote, base):
        return MergeChangeKind.LOCAL_ONLY
    if values_equal(local, remote):
        return MergeChangeKind.SAME_CHANGE
    return MergeChangeKind.CONFLICT


def _clean_value(value: Any) -> Any:
    return None if value is _MISSING else value


def _present(value: Any) -> bool:
    return value is not _MISSING


def _summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_KEYS}


def _bump(summary: dict[str, int], kind: MergeChangeKind) -> None:
    mapping = {
        MergeChangeKind.UNCHANGED: "unchanged_count",
        MergeChangeKind.REMOTE_ONLY: "remote_only_count",
        MergeChangeKind.LOCAL_ONLY: "local_only_count",
        MergeChangeKind.SAME_CHANGE: "same_change_count",
        MergeChangeKind.CONFLICT: "conflict_count",
        MergeChangeKind.REMOTE_ADDED: "remote_added_count",
        MergeChangeKind.LOCAL_ADDED: "local_added_count",
        MergeChangeKind.REMOTE_DELETED: "remote_deleted_count",
        MergeChangeKind.LOCAL_DELETED: "local_deleted_count",
        MergeChangeKind.SAME_ADDITION: "same_addition_count",
        MergeChangeKind.BOTH_DELETED: "both_deleted_count",
        MergeChangeKind.ADD_ADD_CONFLICT: "add_add_conflict_count",
        MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT: "delete_update_conflict_count",
        MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT: "delete_update_conflict_count",
        MergeChangeKind.UPDATE_UPDATE_CONFLICT: "update_update_conflict_count",
    }
    summary[mapping.get(kind, "unchanged_count")] += 1


def _validate_snapshot(snapshot: Any, label: str) -> dict:
    if not isinstance(snapshot, dict):
        raise MergeSnapshotError(f"{label} snapshot dict olmalı.")
    contract = snapshot.get("contract")
    if not isinstance(contract, dict):
        raise MergeSnapshotError(f"{label} snapshot contract section içermeli.")
    uid = str(contract.get("merge_uid") or "").strip()
    if not uid:
        raise MergeSnapshotIdentityError(f"{label} contract merge_uid eksik.")
    return snapshot


def _contract_uid(snapshot: dict) -> str:
    return str((snapshot.get("contract") or {}).get("merge_uid") or "")


def _label(entity: dict | None, fallback: str) -> str:
    if not isinstance(entity, dict):
        return fallback
    for key in ("name", "filename", "contract_no", "stable_uid", "full_name"):
        value = str(entity.get(key) or "").strip()
        if value:
            return value
    return fallback


def _change(entity_kind: MergeEntityKind, entity_uid: str, entity_label: str, field_path: str, field_name: str,
            base: Any, local: Any, remote: Any, kind: MergeChangeKind) -> MergeChange:
    return MergeChange(
        entity_kind=entity_kind,
        entity_uid=entity_uid,
        entity_label=entity_label,
        field_path=field_path,
        field_name=field_name,
        base_value=_clean_value(base),
        local_value=_clean_value(local),
        remote_value=_clean_value(remote),
        base_present=_present(base),
        local_present=_present(local),
        remote_present=_present(remote),
        change_kind=kind,
    )


def _conflict(conflict_type: MergeConflictType, change: MergeChange, reason: str) -> MergeConflict:
    return MergeConflict(
        conflict_type=conflict_type,
        entity_kind=change.entity_kind,
        entity_uid=change.entity_uid,
        entity_label=change.entity_label,
        field_path=change.field_path,
        field_name=change.field_name,
        base_value=change.base_value,
        local_value=change.local_value,
        remote_value=change.remote_value,
        base_present=change.base_present,
        local_present=change.local_present,
        remote_present=change.remote_present,
        reason_code=reason,
    )


def _add_field_change(changes: list[MergeChange], conflicts: list[MergeConflict], summary: dict[str, int],
                      entity_kind: MergeEntityKind, uid: str, label: str, field_path: str, field_name: str,
                      base: Any, local: Any, remote: Any) -> None:
    kind = classify_value_change(base, local, remote)
    _bump(summary, kind)
    if kind == MergeChangeKind.UNCHANGED:
        return
    ch = _change(entity_kind, uid, label, field_path, field_name, base, local, remote, kind)
    changes.append(ch)
    if kind == MergeChangeKind.CONFLICT:
        conflicts.append(_conflict(MergeConflictType.FIELD_CONFLICT, ch, "FIELD_CONFLICT"))


def _entity_map(items: Iterable[dict], key_name: str, entity_kind: MergeEntityKind) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items or []:
        if not isinstance(item, dict):
            raise MergeSnapshotError(f"{entity_kind.value} entity dict olmalı.")
        uid = str(item.get(key_name) or "").strip()
        if not uid:
            raise MergeSnapshotIdentityError(f"{entity_kind.value} identity eksik: {key_name}")
        if uid in out:
            raise DuplicateMergeIdentityError(f"Duplicate {entity_kind.value} identity: {uid}")
        out[uid] = item
    return out


def _relation_key(item: dict, preferred: tuple[str, ...]) -> str:
    for key in preferred:
        value = str(item.get(key) or "").strip()
        if value:
            return value.casefold()
    return ""


def _relation_map(items: Iterable[dict], entity_kind: MergeEntityKind, preferred: tuple[str, ...]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items or []:
        if not isinstance(item, dict):
            raise MergeSnapshotError(f"{entity_kind.value} relation dict olmalı.")
        uid = _relation_key(item, preferred)
        if not uid:
            raise MergeSnapshotIdentityError(f"{entity_kind.value} relation identity eksik.")
        if uid in out:
            raise DuplicateMergeIdentityError(f"Duplicate {entity_kind.value} relation identity: {uid}")
        out[uid] = item
    return out


def _component_maps(entity: dict, collection: str) -> dict[str, dict]:
    out = {}
    raw = entity.get(collection) if isinstance(entity, dict) else None
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    out[name] = item
    elif isinstance(raw, dict):
        for name, value in raw.items():
            out[str(name)] = {"name": str(name), "value": value}
    return out


def _compare_mapping_items(changes, conflicts, summary, entity_kind, uid, label, prefix, field_name, bmap, lmap, rmap, subfields: tuple[str, ...]) -> None:
    for key in sorted(set(bmap) | set(lmap) | set(rmap), key=lambda x: str(x).casefold()):
        b_item, l_item, r_item = bmap.get(key, {}), lmap.get(key, {}), rmap.get(key, {})
        for sub in subfields:
            b = b_item.get(sub, _MISSING) if key in bmap else _MISSING
            l = l_item.get(sub, _MISSING) if key in lmap else _MISSING
            r = r_item.get(sub, _MISSING) if key in rmap else _MISSING
            _add_field_change(changes, conflicts, summary, entity_kind, uid, label, f"{prefix}/{uid}/{field_name}/{key}/{sub}", sub, b, l, r)


def _compare_fields(changes, conflicts, summary, entity_kind, uid, label, path_prefix, base, local, remote,
                    skip: set[str], mapping_specs: dict[str, tuple[str, ...]] | None = None) -> None:
    mapping_specs = mapping_specs or {}
    keys = sorted((set(base or {}) | set(local or {}) | set(remote or {})) - skip - set(mapping_specs), key=str)
    for field in keys:
        _add_field_change(
            changes, conflicts, summary, entity_kind, uid, label, f"{path_prefix}/{uid}/{field}" if path_prefix else f"contract.{field}", field,
            (base or {}).get(field, _MISSING), (local or {}).get(field, _MISSING), (remote or {}).get(field, _MISSING),
        )
    for field, subfields in mapping_specs.items():
        _compare_mapping_items(
            changes, conflicts, summary, entity_kind, uid, label, path_prefix or entity_kind.value.lower(), field,
            _component_maps(base or {}, field), _component_maps(local or {}, field), _component_maps(remote or {}, field), subfields,
        )


def _entity_equal(a: dict | None, b: dict | None) -> bool:
    return values_equal(normalize_contract_snapshot(a or {}), normalize_contract_snapshot(b or {}))


def _entity_lifecycle_change(changes, conflicts, summary, entity_kind, uid, label, base, local, remote) -> bool:
    b, l, r = base is not None, local is not None, remote is not None
    kind = None
    conflict_type = None
    if not b and not l and r:
        kind = MergeChangeKind.REMOTE_ADDED
    elif not b and l and not r:
        kind = MergeChangeKind.LOCAL_ADDED
    elif not b and l and r:
        if _entity_equal(local, remote):
            kind = MergeChangeKind.SAME_ADDITION
        else:
            kind = MergeChangeKind.ADD_ADD_CONFLICT; conflict_type = MergeConflictType.ADD_ADD_CONFLICT
    elif b and l and not r:
        if _entity_equal(local, base):
            kind = MergeChangeKind.REMOTE_DELETED
        else:
            kind = MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT; conflict_type = MergeConflictType.REMOTE_DELETE_LOCAL_UPDATE
    elif b and not l and r:
        if _entity_equal(remote, base):
            kind = MergeChangeKind.LOCAL_DELETED
        else:
            kind = MergeChangeKind.LOCAL_DELETE_REMOTE_UPDATE_CONFLICT; conflict_type = MergeConflictType.LOCAL_DELETE_REMOTE_UPDATE
    elif b and not l and not r:
        kind = MergeChangeKind.BOTH_DELETED
    if kind is None:
        return False
    _bump(summary, kind)
    ch = _change(entity_kind, uid, label, f"{entity_kind.value.lower()}/{uid}", "__entity__", base, local, remote, kind)
    changes.append(ch)
    if conflict_type:
        conflicts.append(_conflict(conflict_type, ch, kind.value))
    return True


def _compare_collection(changes, conflicts, summary, snapshot_key, entity_kind, path_prefix, base_items, local_items, remote_items,
                        mapping_key="merge_uid", skip=None, mapping_specs=None) -> None:
    skip = set(skip or {"id", "merge_uid"})
    bmap = _entity_map(base_items, mapping_key, entity_kind)
    lmap = _entity_map(local_items, mapping_key, entity_kind)
    rmap = _entity_map(remote_items, mapping_key, entity_kind)
    for uid in sorted(set(bmap) | set(lmap) | set(rmap), key=str):
        base, local, remote = bmap.get(uid), lmap.get(uid), rmap.get(uid)
        label = _label(local or remote or base, uid)
        if _entity_lifecycle_change(changes, conflicts, summary, entity_kind, uid, label, base, local, remote):
            continue
        _compare_fields(changes, conflicts, summary, entity_kind, uid, label, path_prefix, base, local, remote, skip, mapping_specs)


def _compare_relation_collection(changes, conflicts, summary, snapshot_key, entity_kind, path_prefix, base_items, local_items, remote_items,
                                 preferred_keys: tuple[str, ...]) -> None:
    bmap = _relation_map(base_items, entity_kind, preferred_keys)
    lmap = _relation_map(local_items, entity_kind, preferred_keys)
    rmap = _relation_map(remote_items, entity_kind, preferred_keys)
    for uid in sorted(set(bmap) | set(lmap) | set(rmap), key=str):
        base, local, remote = bmap.get(uid), lmap.get(uid), rmap.get(uid)
        label = _label(local or remote or base, uid)
        if _entity_lifecycle_change(changes, conflicts, summary, entity_kind, uid, label, base, local, remote):
            continue
        _compare_fields(changes, conflicts, summary, entity_kind, uid, label, path_prefix, base, local, remote, {"id"})


def _sort_changes(changes: list[MergeChange]) -> list[MergeChange]:
    return sorted(changes, key=lambda c: (c.entity_kind.value, c.entity_uid, c.field_path, c.change_kind.value))


def _sort_conflicts(conflicts: list[MergeConflict]) -> list[MergeConflict]:
    return sorted(conflicts, key=lambda c: (c.entity_kind.value, c.entity_uid, c.field_path, c.conflict_type.value))


def build_merge_plan(base_snapshot: dict, local_snapshot: dict, remote_snapshot: dict) -> MergePlan:
    """Build a deterministic three-way merge analysis plan from normalized snapshot dicts.

    Inputs are treated as read-only. The function defensively runs the shared snapshot
    normalizer and never reads DB/filesystem or mutates the provided dictionaries.
    """
    base = normalize_contract_snapshot(_validate_snapshot(base_snapshot, "BASE"))
    local = normalize_contract_snapshot(_validate_snapshot(local_snapshot, "LOCAL"))
    remote = normalize_contract_snapshot(_validate_snapshot(remote_snapshot, "REMOTE"))
    uid = _contract_uid(base)
    if _contract_uid(local) != uid or _contract_uid(remote) != uid:
        raise MergeSnapshotIdentityError("BASE/LOCAL/REMOTE contract merge_uid değerleri uyuşmuyor.")

    changes: list[MergeChange] = []
    conflicts: list[MergeConflict] = []
    summary = _summary()
    label = _label(base.get("contract"), uid)
    _compare_fields(changes, conflicts, summary, MergeEntityKind.CONTRACT, uid, label, "", base.get("contract") or {}, local.get("contract") or {}, remote.get("contract") or {}, {"merge_uid", "id", "contract_id", "revision"})

    _compare_collection(changes, conflicts, summary, "systems", MergeEntityKind.SYSTEM, "systems", base.get("systems") or [], local.get("systems") or [], remote.get("systems") or [], mapping_specs={"components": ("qty", "note")})
    _compare_collection(changes, conflicts, summary, "deliveries", MergeEntityKind.DELIVERY, "deliveries", base.get("deliveries") or [], local.get("deliveries") or [], remote.get("deliveries") or [], mapping_specs={"components": ("planned", "delivered", "units")})
    _compare_collection(changes, conflicts, summary, "folders", MergeEntityKind.DOCUMENT_FOLDER, "document_folders", base.get("folders") or [], local.get("folders") or [], remote.get("folders") or [])
    _compare_collection(changes, conflicts, summary, "files", MergeEntityKind.DOCUMENT_FILE, "document_files", base.get("files") or [], local.get("files") or [], remote.get("files") or [])

    _compare_relation_collection(changes, conflicts, summary, "platforms", MergeEntityKind.PLATFORM_RELATION, "platforms", base.get("platforms") or [], local.get("platforms") or [], remote.get("platforms") or [], ("stable_uid", "name", "platform_name"))
    _compare_relation_collection(changes, conflicts, summary, "users", MergeEntityKind.USER_RELATION, "users", base.get("users") or [], local.get("users") or [], remote.get("users") or [], ("stable_uid", "name"))
    _compare_relation_collection(changes, conflicts, summary, "responsible_engineers", MergeEntityKind.RESPONSIBLE_ENGINEER_RELATION, "responsible_engineers", base.get("responsible_engineers") or [], local.get("responsible_engineers") or [], remote.get("responsible_engineers") or [], ("stable_uid", "full_name"))
    _compare_relation_collection(changes, conflicts, summary, "tags", MergeEntityKind.TAG_RELATION, "tags", base.get("tags") or [], local.get("tags") or [], remote.get("tags") or [], ("stable_uid", "name", "key"))

    return MergePlan(
        contract_merge_uid=uid,
        base_snapshot_hash=hash_contract_snapshot(base),
        local_snapshot_hash=hash_contract_snapshot(local),
        remote_snapshot_hash=hash_contract_snapshot(remote),
        changes=_sort_changes(changes),
        conflicts=_sort_conflicts(conflicts),
        warnings=[],
        summary=summary,
    )
