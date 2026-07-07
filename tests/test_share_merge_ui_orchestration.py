from __future__ import annotations

from src.domain.share_merge import build_merge_plan
from src.models.share_merge_resolution_models import MergeDecisionKind, MergeDecisionSource, MergeOperationKind
from src.ui.presenters.share_merge_presenter import ShareMergeDecisionController


def snap(**overrides):
    data = {
        "contract": {"merge_uid": "c1", "contract_no": "C-1", "status": "BASE", "note": ""},
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


def target_ids(controller):
    return [item.target.target_id for item in controller.resolved_plan.resolution_items]


def test_safe_remote_plan_is_ready_without_user_decision():
    plan = build_merge_plan(snap(), snap(), snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "BASE", "note": "remote"}))
    controller = ShareMergeDecisionController(plan)
    assert controller.can_apply()
    assert controller.live_summary()["operation_count"] == 1
    assert controller.live_summary()["unresolved_conflict_count"] == 0


def test_unresolved_conflict_blocks_apply_until_explicit_decision():
    plan = build_merge_plan(
        snap(),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": ""}),
    )
    controller = ShareMergeDecisionController(plan)
    target = "FIELD|CONTRACT|c1|contract.status"
    assert target in target_ids(controller)
    assert not controller.can_apply()
    assert controller.live_summary()["unresolved_conflict_count"] == 1

    controller.set_decision(target, MergeDecisionKind.LOCAL_KEEP)
    assert controller.can_apply()
    assert controller.resolved_plan.operations == []
    decision = next(d for d in controller.resolved_plan.decisions if d.target_id == target)
    assert decision.source == MergeDecisionSource.USER

    controller.set_decision(target, MergeDecisionKind.REMOTE_USE)
    assert controller.can_apply()
    assert any(op.operation_kind == MergeOperationKind.SET_CONTRACT_FIELD for op in controller.resolved_plan.operations)


def test_skip_creates_explicit_partial_plan():
    plan = build_merge_plan(
        snap(),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}),
        snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": ""}),
    )
    controller = ShareMergeDecisionController(plan)
    target = "FIELD|CONTRACT|c1|contract.status"
    controller.set_decision(target, MergeDecisionKind.SKIP)
    assert controller.can_apply()
    assert controller.resolved_plan.is_partial
    assert controller.live_summary()["skip_count"] == 1


def test_document_keep_both_only_appears_when_engine_allows_it_and_uses_canonical_target_id():
    base = snap(files=[{"merge_uid": "file1", "folder_merge_uid": "folder1", "filename": "a.pdf", "sha256": "base"}])
    local = snap(files=[{"merge_uid": "file1", "folder_merge_uid": "folder1", "filename": "a.pdf", "sha256": "local"}])
    remote = snap(files=[{"merge_uid": "file1", "folder_merge_uid": "folder1", "filename": "a.pdf", "sha256": "remote"}])
    controller = ShareMergeDecisionController(build_merge_plan(base, local, remote))
    target = "FIELD|DOCUMENT_FILE|file1|document_files/file1/sha256"
    item = controller.item_by_target(target)
    assert item is not None
    assert MergeDecisionKind.DOCUMENT_KEEP_BOTH in item.allowed_decisions
    controller.set_decision(target, MergeDecisionKind.DOCUMENT_KEEP_BOTH)
    assert controller.can_apply()
    assert controller.explicit_decisions == {target: MergeDecisionKind.DOCUMENT_KEEP_BOTH}
    assert any(op.operation_kind == MergeOperationKind.KEEP_BOTH_DOCUMENT_FILE for op in controller.resolved_plan.operations)

    field_conflict = ShareMergeDecisionController(
        build_merge_plan(
            snap(),
            snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "LOCAL", "note": ""}),
            snap(contract={"merge_uid": "c1", "contract_no": "C-1", "status": "REMOTE", "note": ""}),
        )
    )
    contract_item = field_conflict.item_by_target("FIELD|CONTRACT|c1|contract.status")
    assert contract_item is not None
    assert MergeDecisionKind.DOCUMENT_KEEP_BOTH not in contract_item.allowed_decisions
