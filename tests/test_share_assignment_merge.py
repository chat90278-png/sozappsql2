from __future__ import annotations

from src.domain.contract_snapshot import build_contract_snapshot
from src.domain.share_merge_resolution import hash_merge_operations, resolve_merge_plan
from src.models.app_models import DeliveryInfo
from src.models.share_merge_models import MergeChangeKind
from src.models.share_merge_resolution_models import MergeDecision, MergeDecisionKind, MergeOperationKind
from src.services.share_merge_apply_service import apply_resolved_share_merge
from src.services.share_merge_service import prepare_share_merge_plan
from src.services.share_package_service import build_base_snapshot_from_source, write_share_base_snapshot, write_share_metadata
from src.services.sts_store import STSStore
from src.ui.presenters.share_merge_presenter import ShareMergeDecisionController
from tests.test_share_merge_end_to_end import make_registered_share


def _save_units(store: STSStore, *, identifier="SN-001", note="", slot_no=1, is_delivered=0):
    ci, systems, deliveries = store.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    delivery = deliveries["SYS"][0]
    delivery.component_units = {
        "C": [{"slot_no": slot_no, "identifier": identifier, "is_delivered": is_delivered, "note": note}]
    }
    store.write_contract(ci, systems, deliveries)


def _units(store: STSStore):
    rows = store.db.conn.execute(
        """
        SELECT c.name,dcu.slot_no,dcu.identifier,dcu.is_delivered,dcu.note
        FROM delivery_component_units dcu
        JOIN delivery_components dc ON dc.id=dcu.delivery_component_id
        JOIN components c ON c.id=dc.component_id
        JOIN deliveries d ON d.id=dc.delivery_id
        WHERE d.name='DEL'
        ORDER BY c.name,dcu.slot_no
        """
    ).fetchall()
    return [dict(r) for r in rows]



def _reset_package_base_to_current_source(source: STSStore, share: STSStore, cid: int, metadata: dict):
    base = build_base_snapshot_from_source(source.db.conn, cid, created_at="2026-07-07T00:00:01")
    metadata["base_snapshot_sha256"] = base.snapshot_sha256
    write_share_metadata(share.path, metadata)
    share.db.conn.execute("DELETE FROM share_base_snapshot")
    share.db.conn.commit()
    write_share_base_snapshot(share.path, base)
    source.db.conn.execute(
        "UPDATE share_packages SET base_snapshot_sha256=? WHERE share_package_id=?",
        (base.snapshot_sha256, metadata["share_package_id"]),
    )
    source.db.conn.commit()


def _registered_share_with_base_units(tmp_path):
    source, share, ci, cid, metadata = make_registered_share(tmp_path)
    _save_units(source, identifier="BASE-SER", note="BASE-Q")
    _save_units(share, identifier="BASE-SER", note="BASE-Q")
    _reset_package_base_to_current_source(source, share, cid, metadata)
    return source, share, ci, cid, metadata

def _merge(source: STSStore, share: STSStore, decisions=None):
    plan = prepare_share_merge_plan(source, share.path)
    resolved = resolve_merge_plan(plan, decisions)
    result = apply_resolved_share_merge(source, share.path, resolved, allow_partial=resolved.is_partial)
    return plan, resolved, result


def test_edit_share_serial_and_queue_units_persist_after_reopen(tmp_path):
    _source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _save_units(share, identifier="SER-100", note="QUEUE-7")
    share.db.close()
    reopened = STSStore(share.path)
    try:
        rows = _units(reopened)
        assert rows[0]["identifier"] == "SER-100"
        assert rows[0]["note"] == "QUEUE-7"
        snapshot = build_contract_snapshot(reopened.db.conn, int(reopened.db.conn.execute("SELECT id FROM contracts").fetchone()[0]))
        comp = snapshot["deliveries"][0]["components"][0]
        assert comp["units"][0]["identifier"] == "SER-100"
        assert comp["units"][0]["note"] == "QUEUE-7"
    finally:
        reopened.db.close(); _source.db.close()


def test_remote_only_assignment_add_merge_reaches_source(tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _save_units(share, identifier="SER-ADD", note="QUEUE-ADD")
    plan, resolved, result = _merge(source, share)
    assert any(c.change_kind == MergeChangeKind.REMOTE_ONLY and c.field_name == "units" for c in plan.changes)
    assert any(op.operation_kind == MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD and op.field_name == "units" for op in resolved.operations)
    assert result.success
    assert _units(source)[0]["identifier"] == "SER-ADD"
    assert _units(source)[0]["note"] == "QUEUE-ADD"


def test_remote_only_serial_update_merge_reaches_source(tmp_path):
    source, share, _ci, _cid, _metadata = _registered_share_with_base_units(tmp_path)
    share.db.conn.execute("UPDATE delivery_component_units SET identifier='SER-NEW'")
    share.db.conn.commit()
    plan, _resolved, result = _merge(source, share)
    assert result.success
    assert _units(source)[0]["identifier"] == "SER-NEW"


def test_remote_only_queue_update_merge_reaches_source(tmp_path):
    source, share, _ci, _cid, _metadata = _registered_share_with_base_units(tmp_path)
    share.db.conn.execute("UPDATE delivery_component_units SET note='NEW-Q'")
    share.db.conn.commit()
    _plan, _resolved, result = _merge(source, share)
    assert result.success
    assert _units(source)[0]["note"] == "NEW-Q"


def test_remote_only_assignment_delete_merge_removes_source_units(tmp_path):
    source, share, _ci, _cid, _metadata = _registered_share_with_base_units(tmp_path)
    share.db.conn.execute("DELETE FROM delivery_component_units")
    share.db.conn.commit()
    _plan, _resolved, result = _merge(source, share)
    assert result.success
    assert _units(source) == []


def test_assignment_conflict_local_keep_remote_take_and_skip(tmp_path):
    for decision, expected, applied in [
        (MergeDecisionKind.LOCAL_KEEP, "LOCAL-SER", 0),
        (MergeDecisionKind.REMOTE_USE, "REMOTE-SER", 1),
        (MergeDecisionKind.SKIP, "LOCAL-SER", 0),
    ]:
        source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
        _save_units(source, identifier="LOCAL-SER", note="LOCAL-Q")
        _save_units(share, identifier="REMOTE-SER", note="REMOTE-Q")
        plan = prepare_share_merge_plan(source, share.path)
        conflict = next(c for c in plan.changes if c.change_kind == MergeChangeKind.CONFLICT and c.field_name == "units")
        resolved = resolve_merge_plan(plan, [MergeDecision(f"FIELD|{conflict.entity_kind.value}|{conflict.entity_uid}|{conflict.field_path}", decision)])
        result = apply_resolved_share_merge(source, share.path, resolved, allow_partial=resolved.is_partial)
        assert result.operations_applied == applied
        assert _units(source)[0]["identifier"] == expected
        source.db.close(); share.db.close()


def test_assignment_operation_hash_is_deterministic(tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _save_units(share, identifier="SER-HASH", note="Q-HASH")
    plan = prepare_share_merge_plan(source, share.path)
    one = resolve_merge_plan(plan)
    two = resolve_merge_plan(plan)
    assert hash_merge_operations(one.operations) == hash_merge_operations(two.operations)


def test_prepared_plan_context_keeps_mixed_assignment_and_delivery_conflicts_valid(tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _save_units(source, identifier="LOCAL-SER", note="LOCAL-Q")
    _save_units(share, identifier="REMOTE-SER", note="REMOTE-Q")
    source.db.conn.execute("UPDATE contracts SET note='LOCAL-NOTE'")
    share.db.conn.execute("UPDATE contracts SET note='REMOTE-NOTE'")
    source.db.conn.commit()
    share.db.conn.commit()

    ci, systems, deliveries = share.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    remote_delivery = DeliveryInfo("DEL-REMOTE", "PLAN", "", "", {"C": 1}, {"C": 0})
    remote_delivery.component_units = {
        "C": [{"slot_no": 1, "identifier": "REMOTE-NEW", "is_delivered": 0, "note": "REMOTE-QUEUE"}]
    }
    deliveries["SYS"].append(remote_delivery)
    share.write_contract(ci, systems, deliveries)

    plan = prepare_share_merge_plan(source, share.path)
    assert getattr(plan, "resolution_base_snapshot", None)
    assert getattr(plan, "resolution_local_snapshot", None)
    assert getattr(plan, "resolution_remote_snapshot", None)

    controller = ShareMergeDecisionController(plan)
    initial = controller.live_summary()
    assert initial["unresolved_conflict_count"] >= 2
    assert initial["structural_issue_count"] == 0

    for item in list(controller.resolved_plan.resolution_items):
        if item.is_conflict:
            controller.set_decision(item.target.target_id, MergeDecisionKind.REMOTE_USE)

    summary = controller.live_summary()
    assert summary["unresolved_conflict_count"] == 0
    assert summary["structural_issue_count"] == 0
    assert controller.can_apply()

    add_delivery = next(
        op for op in controller.resolved_plan.operations
        if op.operation_kind == MergeOperationKind.ADD_DELIVERY and op.entity_label == "DEL-REMOTE"
    )
    assert not any(
        op.operation_kind == MergeOperationKind.SET_DELIVERY_COMPONENT_FIELD
        and op.entity_uid == add_delivery.entity_uid
        for op in controller.resolved_plan.operations
    )
    assert add_delivery.value["components"][0]["units"][0]["identifier"] == "REMOTE-NEW"

    result = apply_resolved_share_merge(source, share.path, controller.resolved_plan)
    assert result.success
    rows = source.db.conn.execute(
        """
        SELECT dcu.identifier,dcu.note
        FROM delivery_component_units dcu
        JOIN delivery_components dc ON dc.id=dcu.delivery_component_id
        JOIN deliveries d ON d.id=dc.delivery_id
        WHERE d.name='DEL-REMOTE'
        ORDER BY dcu.slot_no
        """
    ).fetchall()
    assert [(row["identifier"], row["note"]) for row in rows] == [("REMOTE-NEW", "REMOTE-QUEUE")]
    source.db.close(); share.db.close()
