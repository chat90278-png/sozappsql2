import copy

import pytest

from src.domain.share_merge import (
    DuplicateMergeIdentityError,
    MergeSnapshotIdentityError,
    build_merge_plan,
    classify_value_change,
)
from src.models.share_merge_models import MergeChangeKind, MergeConflictType, MergeEntityKind


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


def change(plan, path):
    return next(c for c in plan.changes if c.field_path == path)


def entity_change(plan, kind, uid):
    return next(c for c in plan.changes if c.entity_kind == kind and c.entity_uid == uid and c.field_name == "__entity__")


def kinds(plan):
    return {c.field_path: c.change_kind for c in plan.changes}


def test_field_classification_rules():
    assert classify_value_change("A", "A", "A") == MergeChangeKind.UNCHANGED
    assert classify_value_change("A", "A", "B") == MergeChangeKind.REMOTE_ONLY
    assert classify_value_change("A", "B", "A") == MergeChangeKind.LOCAL_ONLY
    assert classify_value_change("A", "B", "B") == MergeChangeKind.SAME_CHANGE
    assert classify_value_change("A", "B", "C") == MergeChangeKind.CONFLICT


def test_contract_parallel_non_conflicting_and_field_conflict():
    base = snap()
    local = snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "B", "note": ""})
    remote = snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "A", "note": "x"})
    plan = build_merge_plan(base, local, remote)
    assert change(plan, "contract.status").change_kind == MergeChangeKind.LOCAL_ONLY
    assert change(plan, "contract.note").change_kind == MergeChangeKind.REMOTE_ONLY
    assert not plan.conflicts

    conflict = build_merge_plan(base, snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "B", "note": ""}), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "C", "note": ""}))
    assert change(conflict, "contract.status").change_kind == MergeChangeKind.CONFLICT
    assert conflict.conflicts[0].conflict_type == MergeConflictType.FIELD_CONFLICT


def test_system_lifecycle_matrix():
    system_a = {"merge_uid": "s1", "name": "S", "status": "A", "components": []}
    system_b = {"merge_uid": "s1", "name": "S", "status": "B", "components": []}
    assert entity_change(build_merge_plan(snap(), snap(), snap(systems=[system_a])), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.REMOTE_ADDED
    assert entity_change(build_merge_plan(snap(), snap(systems=[system_a]), snap()), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.LOCAL_ADDED
    assert entity_change(build_merge_plan(snap(), snap(systems=[system_a]), snap(systems=[system_a])), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.SAME_ADDITION
    add_conflict = build_merge_plan(snap(), snap(systems=[system_a]), snap(systems=[system_b]))
    assert entity_change(add_conflict, MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.ADD_ADD_CONFLICT
    assert add_conflict.conflicts[0].conflict_type == MergeConflictType.ADD_ADD_CONFLICT

    base = snap(systems=[system_a])
    assert entity_change(build_merge_plan(base, snap(systems=[system_a]), snap()), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.REMOTE_DELETED
    assert entity_change(build_merge_plan(base, snap(), snap(systems=[system_a])), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.LOCAL_DELETED
    assert entity_change(build_merge_plan(base, snap(), snap()), MergeEntityKind.SYSTEM, "s1").change_kind == MergeChangeKind.BOTH_DELETED
    remote_delete_local_update = build_merge_plan(base, snap(systems=[system_b]), snap())
    assert remote_delete_local_update.conflicts[0].conflict_type == MergeConflictType.REMOTE_DELETE_LOCAL_UPDATE
    local_delete_remote_update = build_merge_plan(base, snap(), snap(systems=[system_b]))
    assert local_delete_remote_update.conflicts[0].conflict_type == MergeConflictType.LOCAL_DELETE_REMOTE_UPDATE


def test_system_field_and_component_granular_merge():
    base_sys = {"merge_uid": "s1", "name": "A", "status": "X", "components": [{"name": "Hava Aracı", "qty": 6, "note": "n"}]}
    local_sys = {"merge_uid": "s1", "name": "A", "status": "Y", "components": [{"name": "Hava Aracı", "qty": 6, "note": "local"}]}
    remote_sys = {"merge_uid": "s1", "name": "B", "status": "X", "components": [{"name": "Hava Aracı", "qty": 8, "note": "remote"}]}
    plan = build_merge_plan(snap(systems=[base_sys]), snap(systems=[local_sys]), snap(systems=[remote_sys]))
    assert change(plan, "systems/s1/name").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "systems/s1/status").change_kind == MergeChangeKind.LOCAL_ONLY
    assert change(plan, "systems/s1/components/Hava Aracı/qty").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "systems/s1/components/Hava Aracı/note").change_kind == MergeChangeKind.CONFLICT


def test_delivery_folder_file_and_relation_merge():
    base = snap(
        deliveries=[{"merge_uid": "d1", "system_merge_uid": "s1", "name": "D", "status": "A", "components": [{"name": "YKI", "planned": 2, "delivered": 0}]}],
        folders=[{"merge_uid": "f1", "parent_merge_uid": "", "name": "Klasör"}],
        files=[{"merge_uid": "file1", "folder_merge_uid": "f1", "filename": "a.pdf", "note": "", "sha256": "abc", "size_bytes": 10}],
        platforms=[{"stable_uid": "p1", "name": "P", "is_primary": 1}],
    )
    local = copy.deepcopy(base)
    remote = copy.deepcopy(base)
    remote["deliveries"][0]["system_merge_uid"] = "s2"
    remote["deliveries"][0]["components"][0]["delivered"] = 1
    remote["folders"][0]["name"] = "Yeni"
    local["files"][0]["filename"] = "local.pdf"
    remote["files"][0]["sha256"] = "def"
    remote["platforms"][0]["is_primary"] = 0
    plan = build_merge_plan(base, local, remote)
    assert change(plan, "deliveries/d1/system_merge_uid").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "deliveries/d1/components/YKI/delivered").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "document_folders/f1/name").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "document_files/file1/filename").change_kind == MergeChangeKind.LOCAL_ONLY
    assert change(plan, "document_files/file1/sha256").change_kind == MergeChangeKind.REMOTE_ONLY
    assert change(plan, "platforms/p1/is_primary").change_kind == MergeChangeKind.REMOTE_ONLY
    assert not plan.conflicts


def test_file_content_and_folder_move_conflicts():
    base = snap(folders=[{"merge_uid": "f1", "parent_merge_uid": "root", "name": "F"}], files=[{"merge_uid": "file1", "folder_merge_uid": "f1", "filename": "a", "sha256": "abc"}])
    local = snap(folders=[{"merge_uid": "f1", "parent_merge_uid": "l", "name": "F"}], files=[{"merge_uid": "file1", "folder_merge_uid": "f1", "filename": "a", "sha256": "def"}])
    remote = snap(folders=[{"merge_uid": "f1", "parent_merge_uid": "r", "name": "F"}], files=[{"merge_uid": "file1", "folder_merge_uid": "f1", "filename": "a", "sha256": "xyz"}])
    plan = build_merge_plan(base, local, remote)
    assert change(plan, "document_folders/f1/parent_merge_uid").change_kind == MergeChangeKind.CONFLICT
    assert change(plan, "document_files/file1/sha256").change_kind == MergeChangeKind.CONFLICT
    assert len(plan.conflicts) == 2



def test_relation_delete_update_conflict():
    base = snap(tags=[{"stable_uid": "tag", "name": "Tag", "color": "red"}])
    local = snap(tags=[{"stable_uid": "tag", "name": "Tag", "color": "blue"}])
    remote = snap(tags=[])
    plan = build_merge_plan(base, local, remote)
    ch = entity_change(plan, MergeEntityKind.TAG_RELATION, "tag")
    assert ch.change_kind == MergeChangeKind.REMOTE_DELETE_LOCAL_UPDATE_CONFLICT
    assert plan.conflicts[0].conflict_type == MergeConflictType.REMOTE_DELETE_LOCAL_UPDATE

def test_identity_validation_duplicates_determinism_and_input_immutability():
    with pytest.raises(MergeSnapshotIdentityError):
        build_merge_plan(snap(), snap(), snap(contract={"merge_uid": "other"}))
    with pytest.raises(DuplicateMergeIdentityError):
        build_merge_plan(snap(systems=[{"merge_uid": "s", "name": "1"}, {"merge_uid": "s", "name": "2"}]), snap(), snap())

    base = snap(systems=[{"merge_uid": "b", "name": "B"}, {"merge_uid": "a", "name": "A"}])
    remote = snap(systems=[{"merge_uid": "a", "name": "A2"}, {"merge_uid": "b", "name": "B2"}])
    local = copy.deepcopy(base)
    originals = (copy.deepcopy(base), copy.deepcopy(local), copy.deepcopy(remote))
    p1 = build_merge_plan(base, local, remote)
    p2 = build_merge_plan(snap(systems=list(reversed(base["systems"]))), snap(systems=list(reversed(local["systems"]))), snap(systems=list(reversed(remote["systems"]))))
    assert [(c.field_path, c.change_kind) for c in p1.changes] == [(c.field_path, c.change_kind) for c in p2.changes]
    assert (base, local, remote) == originals


def test_missing_mapping_key_has_presence_flags():
    remote_sys = {"merge_uid": "s1", "name": "S", "components": [{"name": "B", "qty": 2, "note": ""}]}
    plan = build_merge_plan(snap(systems=[{"merge_uid": "s1", "name": "S", "components": []}]), snap(systems=[{"merge_uid": "s1", "name": "S", "components": []}]), snap(systems=[remote_sys]))
    ch = change(plan, "systems/s1/components/B/qty")
    assert ch.change_kind == MergeChangeKind.REMOTE_ONLY
    assert not ch.base_present
    assert not ch.local_present
    assert ch.remote_present
