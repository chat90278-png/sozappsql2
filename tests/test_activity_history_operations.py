from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.activity_history_infra import (
    UNKNOWN_ACTOR,
    activity_values_equal,
    build_changed_fields,
    infer_activity_category,
)
from src.services.share_merge_apply_service import _insert_audit_log
from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase
from src.services.sts_store import STSStore
from src.workers.contract_save_worker import ContractSaveWorker


def _count(store: STSStore, action: str | None = None) -> int:
    if action:
        return int(store.db.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE action=?", (action,)).fetchone()[0])
    return int(store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0])


def _rows(store: STSStore, action: str | None = None):
    if action:
        return store.db.conn.execute("SELECT * FROM activity_logs WHERE action=? ORDER BY id", (action,)).fetchall()
    return store.db.conn.execute("SELECT * FROM activity_logs ORDER BY id").fetchall()


def _contract(no: str = "C-1") -> ContractInfo:
    return ContractInfo(
        no=no,
        platform="AKINCI",
        user="",
        yi_yd="Yİ",
        contract_type="Ana Sözleşme",
        signature_date="",
        t0_date="",
        t0_months=0,
        completion_date="",
        status="PLAN",
        note="",
        acceptance_date="",
    )


def test_operation_context_unique_nested_override_and_exception_cleanup(tmp_path):
    store = STSStore(tmp_path / "operations.sts", actor="Ayşe")
    try:
        with store.activity_operation(name="first") as first:
            first_id = first.operation_id
            store._log("contract_updated")
            with store.activity_operation(name="nested") as nested:
                assert nested.operation_id == first_id
                store._log("system_updated")
            with store.activity_operation(name="separate", new_operation=True) as separate:
                assert separate.operation_id != first_id
                store._log("delivery_updated")
            store._log("document_added", operation_id="explicit-op")
        with store.activity_operation(name="second") as second:
            assert second.operation_id != first_id
        with pytest.raises(RuntimeError):
            with store.activity_operation(name="failure"):
                raise RuntimeError("boom")
        assert store._active_activity_operation() is None
        rows = _rows(store)
        assert rows[0]["operation_id"] == first_id
        assert rows[1]["operation_id"] == first_id
        assert rows[2]["operation_id"] == separate.operation_id
        assert rows[3]["operation_id"] == "explicit-op"
    finally:
        store.db.close()


def test_grouped_events_rollback_with_business_transaction(tmp_path):
    store = STSStore(tmp_path / "rollback.sts", actor="Ayşe")
    try:
        store.db.conn.execute("CREATE TABLE phase2_business(id INTEGER PRIMARY KEY,value TEXT)")
        store.db.conn.commit()
        with pytest.raises(RuntimeError):
            with store.activity_operation(name="rollback") as operation:
                with store.db.tx():
                    store.db.conn.execute("INSERT INTO phase2_business(value) VALUES('x')")
                    store._log("contract_updated")
                    assert _rows(store)[0]["operation_id"] == operation.operation_id
                    raise RuntimeError("rollback")
        assert store.db.conn.execute("SELECT COUNT(*) FROM phase2_business").fetchone()[0] == 0
        assert _count(store) == 0
    finally:
        store.db.close()


def test_structured_staff_admin_system_unknown_and_session_wiring(tmp_path):
    staff = STSStore(
        tmp_path / "staff.sts",
        actor="fallback",
        actor_context={
            "id": 7, "full_name": "Ayşe Personel", "device_name": "PC-7",
            "password": "never-log", "access_token": "never-log-token", "invite_code": "never-log-code",
        },
        session_id="session-staff",
    )
    try:
        first = staff._log("contract_updated")
        second = staff._log("system_updated")
        row = staff.db.conn.execute("SELECT * FROM activity_logs WHERE id=?", (first,)).fetchone()
        assert row["actor_type"] == "STAFF"
        assert row["actor_staff_id"] == 7
        assert row["actor_admin_id"] is None
        assert row["actor_display_name"] == "Ayşe Personel"
        assert row["session_id"] == "session-staff"
        serialized_row = json.dumps(dict(row), ensure_ascii=False)
        assert "never-log" not in serialized_row
        assert "never-log-token" not in serialized_row
        assert "never-log-code" not in serialized_row
        assert staff.db.conn.execute("SELECT session_id FROM activity_logs WHERE id=?", (second,)).fetchone()[0] == "session-staff"

        explicit = staff._log(
            "platform_updated",
            actor="Admin Override",
            actor_display_name="Admin Override",
            actor_type="ADMIN",
            actor_admin_id=9,
            actor_staff_id=None,
            session_id="explicit-session",
        )
        row = staff.db.conn.execute("SELECT * FROM activity_logs WHERE id=?", (explicit,)).fetchone()
        assert row["actor_type"] == "ADMIN"
        assert row["actor_admin_id"] == 9
        assert row["actor_display_name"] == "Admin Override"
        assert row["session_id"] == "explicit-session"
    finally:
        staff.db.close()

    admin = STSStore(
        tmp_path / "admin.sts",
        actor_context={"is_admin": True, "admin_id": 3, "full_name": "Sistem Yöneticisi"},
    )
    try:
        event_id = admin._log("platform_updated")
        row = admin.db.conn.execute("SELECT actor_type,actor_admin_id FROM activity_logs WHERE id=?", (event_id,)).fetchone()
        assert tuple(row) == ("ADMIN", 3)
    finally:
        admin.db.close()

    system = STSStore(
        tmp_path / "system.sts",
        actor="Index Worker",
        actor_context={"actor_type": "SYSTEM", "actor_display_name": "Index Worker"},
    )
    try:
        event_id = system._log("performance_index")
        row = system.db.conn.execute("SELECT actor_type,actor_display_name FROM activity_logs WHERE id=?", (event_id,)).fetchone()
        assert tuple(row) == ("SYSTEM", "Index Worker")
    finally:
        system.db.close()

    unknown = STSStore(tmp_path / "unknown.sts")
    try:
        event_id = unknown._log("contract_updated")
        row = unknown.db.conn.execute("SELECT actor_type,actor_display_name FROM activity_logs WHERE id=?", (event_id,)).fetchone()
        assert tuple(row) == ("UNKNOWN", UNKNOWN_ACTOR)
    finally:
        unknown.db.close()


def test_worker_propagates_actor_and_session_without_reusing_connection(tmp_path):
    path = tmp_path / "worker.sts"
    main_store = STSStore(
        path,
        actor_context={"id": 14, "full_name": "Worker Personeli"},
        session_id="worker-session",
    )
    worker_store = None
    try:
        worker = ContractSaveWorker(
            path,
            "write",
            "AKINCI",
            "C-1",
            store=main_store,
        )
        worker_store, opened_new = worker._open_store()
        assert opened_new is True
        assert worker_store.db.conn is not main_store.db.conn
        assert worker_store.current_actor_context() == main_store.current_actor_context()
        event_id = worker_store._log("contract_updated")
        row = worker_store.db.conn.execute(
            "SELECT actor_type,actor_staff_id,actor_display_name,session_id FROM activity_logs WHERE id=?",
            (event_id,),
        ).fetchone()
        assert tuple(row) == ("STAFF", 14, "Worker Personeli", "worker-session")
    finally:
        if worker_store is not None:
            worker_store.db.close()
        main_store.db.close()


def test_category_contract_explicit_priority_alias_and_status_normalization(tmp_path):
    assert infer_activity_category("contract_created") == "USER"
    assert infer_activity_category("platform_order_updated") == "MANAGEMENT"
    assert infer_activity_category("performance_refresh") == "TECHNICAL"
    assert infer_activity_category("contract_created", "TECHNICAL") == "TECHNICAL"
    db = STSDatabase(tmp_path / "category.sts")
    try:
        ids = [
            db.add_log("contract_created"),
            db.add_log("platform_updated"),
            db.add_log("performance_refresh"),
            db.add_log("contract_updated", category="TECHNICAL"),
            db.add_log("unknown_action", category="invalid", status="invalid", actor_type="invalid"),
        ]
        rows = [db.conn.execute("SELECT category,status,actor_type FROM activity_logs WHERE id=?", (event_id,)).fetchone() for event_id in ids]
        assert [row["category"] for row in rows] == ["USER", "MANAGEMENT", "TECHNICAL", "TECHNICAL", None]
        assert rows[-1]["status"] == "SUCCESS"
        assert rows[-1]["actor_type"] == "UNKNOWN"
        db.conn.execute(
            "INSERT INTO activity_logs(created_at,actor,action,category) VALUES(?,?,?,NULL)",
            ("2026-01-01 00:00:00", "Legacy", "legacy_null_category"),
        )
        db.conn.commit()
        legacy = next(row for row in db.list_logs(limit=0) if row["action"] == "legacy_null_category")
        assert legacy["category"] is None
    finally:
        db.close()


def test_changed_fields_deterministic_redacted_and_does_not_mutate_input():
    before = {"b": 2, "a": "önce", "token": "secret", "users": ["B", "A"]}
    after = {"a": "sonra", "b": 2, "token": "new-secret", "users": ["A", "B"]}
    original_before = dict(before)
    changes = build_changed_fields(before, after, set_like_fields={"users"})
    assert [item["field"] for item in changes] == ["a", "token"]
    assert changes[1]["before"] == "[REDACTED]"
    assert changes[1]["after"] == "[REDACTED]"
    assert before == original_before
    assert activity_values_equal({"x": 1, "y": 2}, {"y": 2, "x": 1})


def test_platform_noop_suppression_and_real_change(tmp_path):
    store = STSStore(tmp_path / "platform.sts", actor="Ayşe")
    try:
        store.create_platform("AKINCI")
        created = _count(store)
        store.create_platform("AKINCI")
        store.update_platform("AKINCI", "AKINCI", True, False, sort_order=0)
        store.save_excluded_platforms([])
        platform_id = store.get_platform_id("AKINCI")
        store.update_platform_order([platform_id])
        assert _count(store) == created

        assert store.set_platform_logo_bytes("AKINCI", b"logo", ext="png") is True
        logo_count = _count(store, "platform_logo_updated")
        assert store.set_platform_logo_bytes("AKINCI", b"logo", ext="png") is False
        assert _count(store, "platform_logo_updated") == logo_count

        store.update_platform("AKINCI", "AKINCI", False, False, sort_order=0)
        assert _count(store, "platform_updated") == 1
    finally:
        store.db.close()


def test_users_components_and_tags_noop_suppression(tmp_path):
    store = STSStore(tmp_path / "management.sts", actor="Ayşe")
    try:
        store.create_platform("AKINCI")
        users = [{"name": "Kullanıcı A", "yi_yd": "Yİ", "active": True, "note": ""}]
        assert store.write_users(users) is True
        assert _count(store, "users_updated") == 1
        assert all(row["action"] not in {"user_created", "user_updated", "user_deleted"} for row in _rows(store))
        user_events = _count(store)
        assert store.write_users(list(reversed(users))) is False
        assert _count(store) == user_events

        components = [{
            "name": "GÖVDE", "version": "1", "unit": "Adet", "active": True,
            "usage": 1, "note": "", "display_order": 0, "platforms": {"AKINCI": True},
        }]
        assert store.write_components(components) is True
        assert _count(store, "components_updated") == 1
        assert all(row["action"] not in {"component_created", "component_updated"} for row in _rows(store))
        component_events = _count(store)
        assert store.write_components(components) is False
        assert _count(store) == component_events

        tags = [{"name": "Kritik", "color": "#ff0000", "kind": "contract"}]
        assert store.write_tag_snapshot(tags, {}) is True
        tag_events = _count(store)
        assert store.write_tag_snapshot(tags, {}) is False
        assert _count(store) == tag_events
        assert store.upsert_tag_def(tags[0]) is False
        assert _count(store) == tag_events
    finally:
        store.db.close()


def test_contract_grouping_exact_noop_and_child_only_duplicate_suppression(tmp_path):
    store = STSStore(tmp_path / "contract.sts", actor="Ayşe")
    try:
        store.create_platform("AKINCI")
        ci = _contract()
        system = SystemInfo(name="SYS", components={"C": 1}, status="PLAN")
        delivery = DeliveryInfo(name="DEL", status="PLAN", acceptance_date="", note="", planned={"C": 1}, delivered={"C": 0})
        store.write_contract(ci, [system], {"SYS": [delivery]})
        creation_rows = store.db.conn.execute(
            "SELECT action,operation_id FROM activity_logs WHERE action IN ('contract_created','system_created','delivery_created') ORDER BY id"
        ).fetchall()
        assert {row["action"] for row in creation_rows} == {"contract_created", "system_created", "delivery_created"}
        assert len({row["operation_id"] for row in creation_rows}) == 1
        first_operation = creation_rows[0]["operation_id"]

        before_noop = _count(store)
        before_noop_id = int(store.db.conn.execute("SELECT COALESCE(MAX(id),0) FROM activity_logs").fetchone()[0])
        store.write_contract(ci, [system], {"SYS": [delivery]})
        assert _count(store) == before_noop

        changed_system = SystemInfo(name="SYS", components={"C": 2}, status="PLAN")
        store.write_contract(ci, [changed_system], {"SYS": [delivery]})
        new_rows = store.db.conn.execute("SELECT action,operation_id FROM activity_logs WHERE id>? ORDER BY id", (before_noop_id,)).fetchall()
        assert [row["action"] for row in new_rows] == ["system_updated"]
        assert new_rows[0]["operation_id"] != first_operation
        assert _count(store, "system_component_updated") == 0
        assert _count(store, "contract_updated") == 0

        ci.note = "Ana bilgi değişti"
        store.write_contract(ci, [changed_system], {"SYS": [delivery]})
        assert _count(store, "contract_updated") == 1
        assert _count(store, "contract_status_changed") == 0
    finally:
        store.db.close()


def test_document_and_lock_noop_suppression(tmp_path):
    store = STSStore(tmp_path / "documents.sts", actor="Ayşe")
    try:
        store.create_platform("AKINCI")
        ci = _contract("DOC-1")
        store.write_contract(ci, [], {})
        folder = store.create_contract_file_folder("AKINCI", ci.no, ci.contract_type, name="Belgeler")
        count = _count(store)
        store.rename_contract_file_folder(folder["id"], "Belgeler")
        assert _count(store) == count
        store.move_contract_file_folder(folder["id"], None)
        assert _count(store) == count

        source = tmp_path / "file.txt"
        source.write_text("content", encoding="utf-8")
        file_id = store.add_contract_file("AKINCI", ci.no, source, ci.contract_type, folder_id=folder["id"])
        moved_count = _count(store)
        store.move_contract_file(file_id, folder["id"])
        assert _count(store) == moved_count

        staff = {"id": None, "full_name": "Ayşe", "device_name": "PC-1"}
        store.lock_documents("AKINCI", ci.no, staff, ci.contract_type)
        lock_count = _count(store, "documents_locked")
        store.lock_documents("AKINCI", ci.no, staff, ci.contract_type)
        assert _count(store, "documents_locked") == lock_count
        store.unlock_documents("AKINCI", ci.no, contract_type=ci.contract_type)
        unlock_count = _count(store, "documents_unlocked")
        store.unlock_documents("AKINCI", ci.no, contract_type=ci.contract_type)
        assert _count(store, "documents_unlocked") == unlock_count
    finally:
        store.db.close()


def test_share_merge_audit_operation_and_rollback_remain_atomic(tmp_path):
    db = STSDatabase(tmp_path / "share.sts")
    try:
        ctx = SimpleNamespace(
            source=db.conn,
            actor="Merge Kullanıcısı",
            actor_type="STAFF",
            current_staff_id=4,
            current_admin_id=0,
            session_id="merge-session",
            operation_id="merge-operation",
            contract_id=0,
            share_package_id="package-1",
            contract_merge_uid="contract-uid",
            operations_hash="operations-hash",
            contract_no="C-1",
        )
        db.conn.execute("BEGIN IMMEDIATE")
        _insert_audit_log(ctx, "MERGED", 1, 2, "pre", "remote", "post", 2, 2, "/private/backup.sts")
        row = db.conn.execute("SELECT * FROM activity_logs WHERE action='share_merge_applied'").fetchone()
        assert row["operation_id"] == "merge-operation"
        assert row["actor_type"] == "STAFF"
        assert row["actor_staff_id"] == 4
        assert row["session_id"] == "merge-session"
        assert json.loads(row["payload_json"])["backup_path"] == {"name": "backup.sts", "path_redacted": True}
        db.conn.rollback()
        assert db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0] == 0
    finally:
        db.close()


def test_schema_version_remains_18():
    assert CURRENT_SCHEMA_VERSION == 18
