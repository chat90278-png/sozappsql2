import copy

import pytest

from src.domain.share_merge import build_merge_plan
from src.domain.share_merge_resolution import (
    DuplicateMergeDecisionError,
    InvalidMergeDecisionError,
    UnknownMergeDecisionTargetError,
    UnresolvedMergeConflictError,
    build_resolution_items,
    hash_merge_operations,
    resolve_merge_plan,
    serialize_merge_operations,
)
from src.models.share_merge_models import MergeChangeKind, MergeEntityKind
from src.models.share_merge_resolution_models import MergeDecision, MergeDecisionKind, MergeDecisionSource, MergeOperationKind


def snap(**overrides):
    data = {
        "contract": {"merge_uid": "c1", "contract_no": "C-1", "status": "A", "note": ""},
        "systems": [],
        "deliveries": [],
        "folders": [],
        "files": [],
        "platforms": [],
        "users": [],
        "responsible_engineers": [],
        "tags": [],
    }
    data.update(overrides)
    return data


def item(resolved, path_or_entity):
    return next(i for i in resolved.resolution_items if i.target.field_path == path_or_entity or i.target.target_id == path_or_entity)


def op(resolved, kind):
    return next(o for o in resolved.operations if o.operation_kind == kind)


def test_default_decision_policy_for_field_and_entity_kinds():
    plan = build_merge_plan(
        snap(systems=[{"merge_uid": "s_del", "name": "D"}], files=[{"merge_uid": "f_both", "filename": "a", "sha256": "x"}]),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}, systems=[{"merge_uid": "s_local", "name": "L"}], files=[]),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "A", "note": "remote"}, systems=[{"merge_uid": "s_remote", "name": "R"}], files=[]),
    )
    resolved = resolve_merge_plan(plan)
    assert item(resolved, "contract.note").default_decision == MergeDecisionKind.REMOTE_USE
    assert item(resolved, "contract.status").default_decision == MergeDecisionKind.LOCAL_KEEP
    assert item(resolved, "ENTITY|SYSTEM|s_remote").default_decision == MergeDecisionKind.REMOTE_USE
    assert item(resolved, "ENTITY|SYSTEM|s_local").default_decision == MergeDecisionKind.LOCAL_KEEP
    assert item(resolved, "ENTITY|DOCUMENT_FILE|f_both").default_decision == MergeDecisionKind.NO_ACTION


def test_conflict_default_unresolved_require_all_and_explicit_decisions():
    plan = build_merge_plan(
        snap(),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": ""}),
    )
    target = "FIELD|CONTRACT|c1|contract.status"
    resolved = resolve_merge_plan(plan)
    assert not resolved.fully_resolved
    assert resolved.has_unresolved_conflicts
    assert resolved.operations == []
    assert item(resolved, "contract.status").default_decision == MergeDecisionKind.LOCAL_KEEP
    with pytest.raises(UnresolvedMergeConflictError):
        resolve_merge_plan(plan, require_all_conflicts_resolved=True)

    keep = resolve_merge_plan(plan, {target: MergeDecisionKind.LOCAL_KEEP})
    assert keep.fully_resolved and keep.operations == []
    use = resolve_merge_plan(plan, {target: MergeDecisionKind.REMOTE_USE})
    assert use.fully_resolved
    set_op = op(use, MergeOperationKind.SET_CONTRACT_FIELD)
    assert set_op.value == "REMOTE" and set_op.field_name == "status"
    skipped = resolve_merge_plan(plan, {target: MergeDecisionKind.SKIP})
    assert skipped.fully_resolved and skipped.is_partial and skipped.operations == []


def test_decision_validation_errors():
    plan = build_merge_plan(snap(), snap(), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "A", "note": "r"}))
    target = "FIELD|CONTRACT|c1|contract.note"
    with pytest.raises(UnknownMergeDecisionTargetError):
        resolve_merge_plan(plan, {"FIELD|CONTRACT|c1|contract.missing": MergeDecisionKind.REMOTE_USE})
    with pytest.raises(DuplicateMergeDecisionError):
        resolve_merge_plan(plan, [MergeDecision(target, MergeDecisionKind.REMOTE_USE), MergeDecision(target, MergeDecisionKind.SKIP)])
    with pytest.raises(InvalidMergeDecisionError):
        resolve_merge_plan(plan, {target: MergeDecisionKind.NO_ACTION})
    with pytest.raises(InvalidMergeDecisionError):
        resolve_merge_plan(plan, {target: MergeDecisionKind.DOCUMENT_KEEP_BOTH})


def test_contract_operations_remote_local_and_missing_values():
    remote = snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "B"})
    plan = build_merge_plan(snap(), snap(), remote)
    resolved = resolve_merge_plan(plan)
    note_clear = op(resolved, MergeOperationKind.SET_CONTRACT_FIELD)
    assert note_clear.operation_kind == MergeOperationKind.SET_CONTRACT_FIELD
    assert note_clear.entity_uid == "c1"
    assert note_clear.value_present is False or note_clear.value == "B"

    local_only = build_merge_plan(snap(), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}), snap())
    target = "FIELD|CONTRACT|c1|contract.status"
    rollback = resolve_merge_plan(local_only, {target: MergeDecisionKind.REMOTE_USE})
    assert op(rollback, MergeOperationKind.SET_CONTRACT_FIELD).value == "A"


def test_system_operations_and_component_operations():
    base_sys = {"merge_uid": "s1", "name": "S", "status": "A", "components": [{"name": "C", "qty": 1, "note": "n"}]}
    remote_sys = {"merge_uid": "s1", "name": "S", "status": "B", "components": [{"name": "C", "qty": 2, "note": "r"}, {"name": "D", "qty": 5, "note": ""}]}
    plan = build_merge_plan(snap(systems=[base_sys]), snap(systems=[base_sys]), snap(systems=[remote_sys, {"merge_uid": "s2", "name": "New"}]))
    resolved = resolve_merge_plan(plan)
    assert op(resolved, MergeOperationKind.ADD_SYSTEM).value["merge_uid"] == "s2"
    assert op(resolved, MergeOperationKind.SET_SYSTEM_FIELD).field_name == "status"
    assert any(o.operation_kind == MergeOperationKind.SET_SYSTEM_COMPONENT and o.metadata.get("component_name") == "C" for o in resolved.operations)
    assert any(o.operation_kind == MergeOperationKind.SET_SYSTEM_COMPONENT_NOTE and o.metadata.get("component_name") == "C" for o in resolved.operations)
    missing_component = next(o for o in resolved.operations if o.metadata.get("component_name") == "D" and o.field_name == "qty")
    assert missing_component.value == 5


def test_delivery_folder_file_relation_operations_and_keep_both():
    base = snap(
        systems=[{"merge_uid": "s1", "name": "S"}],
        deliveries=[{"merge_uid": "d1", "system_merge_uid": "s1", "name": "D", "acceptance_date": "", "components": [{"name": "C", "planned": 1, "delivered": 0}]}],
        folders=[{"merge_uid": "fo1", "parent_merge_uid": "", "name": "F"}],
        files=[{"merge_uid": "file1", "folder_merge_uid": "fo1", "filename": "a.pdf", "note": "", "sha256": "abc", "file_ext": ".pdf", "mime_type": "application/pdf"}],
        platforms=[{"stable_uid": "P", "name": "P", "is_primary": 0}],
        users=[{"stable_uid": "U", "name": "U", "yi_yd": "Yİ"}],
        responsible_engineers=[{"stable_uid": "E", "full_name": "E", "is_primary": 0}],
        tags=[{"stable_uid": "t", "name": "T", "color": "red"}],
    )
    remote = copy.deepcopy(base)
    remote["deliveries"][0]["acceptance_date"] = "2026-01-01"
    remote["deliveries"][0]["components"][0]["delivered"] = 1
    remote["folders"][0]["name"] = "F2"
    remote["files"][0]["filename"] = "b.pdf"
    remote["files"][0]["note"] = "rn"
    remote["files"][0]["sha256"] = "remote-sha"
    remote["platforms"][0]["is_primary"] = 1
    remote["users"][0]["yi_yd"] = "YD"
    remote["responsible_engineers"][0]["is_primary"] = 1
    remote["tags"][0]["color"] = "blue"
    plan = build_merge_plan(base, base, remote)
    resolved = resolve_merge_plan(plan)
    kinds = {o.operation_kind for o in resolved.operations}
    assert MergeOperationKind.SET_DELIVERY_FIELD in kinds
    assert MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD in kinds
    assert MergeOperationKind.SET_DOCUMENT_FOLDER_FIELD in kinds
    assert MergeOperationKind.SET_DOCUMENT_FILE_FIELD in kinds
    assert MergeOperationKind.REPLACE_DOCUMENT_FILE_CONTENT in kinds
    assert MergeOperationKind.SET_PLATFORM_RELATION_FIELD in kinds
    assert MergeOperationKind.SET_USER_RELATION_FIELD in kinds
    assert MergeOperationKind.SET_RESPONSIBLE_ENGINEER_RELATION_FIELD in kinds
    assert MergeOperationKind.SET_TAG_RELATION_FIELD in kinds

    conflict = build_merge_plan(base, {**base, "files": [{**base["files"][0], "sha256": "local-sha"}]}, remote)
    target = "FIELD|DOCUMENT_FILE|file1|document_files/file1/sha256"
    keep_both = resolve_merge_plan(conflict, {target: MergeDecisionKind.DOCUMENT_KEEP_BOTH})
    keep_op = op(keep_both, MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE)
    assert keep_op.metadata["source_remote_file_merge_uid"] == "file1"
    assert keep_op.metadata["remote_sha256"] == "remote-sha"


def test_dependency_order_and_structural_validation():
    base = snap(
        systems=[{"merge_uid": "s1", "name": "S"}],
        deliveries=[{"merge_uid": "d1", "system_merge_uid": "s1", "name": "D"}],
        folders=[{"merge_uid": "parent", "parent_merge_uid": "", "name": "P"}, {"merge_uid": "child", "parent_merge_uid": "parent", "name": "C"}],
        files=[{"merge_uid": "file1", "folder_merge_uid": "child", "filename": "a", "sha256": "x"}],
    )
    remote_add = snap(
        systems=[{"merge_uid": "s1", "name": "S"}, {"merge_uid": "s2", "name": "S2"}],
        deliveries=[{"merge_uid": "d1", "system_merge_uid": "s1", "name": "D"}, {"merge_uid": "d2", "system_merge_uid": "s2", "name": "D2"}],
        folders=[{"merge_uid": "parent", "parent_merge_uid": "", "name": "P"}, {"merge_uid": "child", "parent_merge_uid": "parent", "name": "C"}, {"merge_uid": "newp", "parent_merge_uid": "", "name": "NP"}, {"merge_uid": "newc", "parent_merge_uid": "newp", "name": "NC"}],
        files=[{"merge_uid": "file1", "folder_merge_uid": "child", "filename": "a", "sha256": "x"}, {"merge_uid": "file2", "folder_merge_uid": "newc", "filename": "b", "sha256": "y"}],
    )
    resolved = resolve_merge_plan(build_merge_plan(base, base, remote_add), base_snapshot=base, local_snapshot=base, remote_snapshot=remote_add)
    order = [o.operation_kind for o in resolved.operations]
    assert order.index(MergeOperationKind.ADD_SYSTEM) < order.index(MergeOperationKind.ADD_DELIVERY)
    assert order.index(MergeOperationKind.ADD_DOCUMENT_FOLDER) < order.index(MergeOperationKind.ADD_DOCUMENT_FILE)

    local_keep_child = copy.deepcopy(base)
    local_keep_child["deliveries"][0]["name"] = "D-local"
    remote_delete = snap(systems=[], deliveries=[], folders=[], files=[])
    plan = build_merge_plan(base, local_keep_child, remote_delete)
    invalid = resolve_merge_plan(
        plan,
        {"ENTITY|SYSTEM|s1": MergeDecisionKind.REMOTE_USE, "ENTITY|DELIVERY|d1": MergeDecisionKind.LOCAL_KEEP},
        base_snapshot=base,
        local_snapshot=local_keep_child,
        remote_snapshot=remote_delete,
    )
    assert any(i.code == "PARENT_DELETE_CHILD_KEEP_CONFLICT" for i in invalid.issues)

    absent_parent = snap(systems=[], deliveries=[{"merge_uid": "d_new", "system_merge_uid": "missing", "name": "D"}])
    absent = resolve_merge_plan(build_merge_plan(snap(), snap(), absent_parent), base_snapshot=snap(), local_snapshot=snap(), remote_snapshot=absent_parent)
    assert any(i.code == "ABSENT_DELIVERY_PARENT_SYSTEM" for i in absent.issues)

    cycle_remote = snap(folders=[{"merge_uid": "a", "parent_merge_uid": "b", "name": "A"}, {"merge_uid": "b", "parent_merge_uid": "a", "name": "B"}])
    cycle = resolve_merge_plan(build_merge_plan(snap(), snap(), cycle_remote), base_snapshot=snap(), local_snapshot=snap(), remote_snapshot=cycle_remote)
    assert any(i.code == "FOLDER_PARENT_CYCLE" for i in cycle.issues)


def test_partial_safe_remote_plan_serialization_hash_and_input_immutability():
    plan = build_merge_plan(
        snap(),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": "r"}),
    )
    before_plan = copy.deepcopy(plan)
    decisions = []
    before_decisions = copy.deepcopy(decisions)
    resolved = resolve_merge_plan(plan, decisions)
    assert resolved.has_unresolved_conflicts
    assert resolved.is_partial
    assert any(o.operation_kind == MergeOperationKind.SET_CONTRACT_FIELD and o.field_name == "note" for o in resolved.operations)
    serialized = serialize_merge_operations(resolved.operations)
    assert hash_merge_operations(resolved.operations) == resolved.operations_hash
    assert isinstance(serialized, str) and serialized.startswith("[")
    assert plan == before_plan
    assert decisions == before_decisions

    shuffled = build_merge_plan(snap(), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": "r"}))
    resolved2 = resolve_merge_plan(shuffled, [])
    assert [i.target.target_id for i in resolved.resolution_items] == [i.target.target_id for i in resolved2.resolution_items]
    assert [o.operation_id for o in resolved.operations] == [o.operation_id for o in resolved2.operations]
    assert resolved.operations_hash == resolved2.operations_hash
