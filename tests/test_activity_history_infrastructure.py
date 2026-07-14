from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.activity_history_infra import (
    ACTIVITY_SCHEMA_VERSION,
    MAX_ACTIVITY_FIELD_LENGTH,
    MAX_ACTIVITY_JSON_BYTES,
    MAX_ACTIVITY_MESSAGE_LENGTH,
    REDACTED_VALUE,
    activity_json,
    sanitize_activity_value,
)
from src.models.app_models import ContractInfo
from src.services.share_merge_apply_service import _insert_audit_log
from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase
from src.services.sts_store import STSStore


LEGACY_ACTIVITY_SCHEMA = """
CREATE TABLE activity_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT,
    source TEXT,
    device_name TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    entity_key TEXT,
    platform_id INTEGER,
    contract_no TEXT,
    message TEXT,
    before_json TEXT,
    after_json TEXT,
    payload_json TEXT
)
"""


def _legacy_sts(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)")
        conn.execute("INSERT INTO meta(key,value) VALUES('schema_version','17')")
        conn.execute(LEGACY_ACTIVITY_SCHEMA)
        conn.execute(
            "INSERT INTO activity_logs(created_at,actor,action,message) VALUES(?,?,?,?)",
            ("2026-01-01 10:00:00", "Eski Kullanıcı", "legacy_event", "Korunmalı"),
        )
        conn.commit()
    finally:
        conn.close()


def _count(db: STSDatabase, action: str | None = None) -> int:
    if action:
        return int(db.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE action=?", (action,)).fetchone()[0])
    return int(db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0])


def test_activity_schema_migration_is_additive_idempotent_and_preserves_rows(tmp_path):
    path = tmp_path / "legacy.sts"
    _legacy_sts(path)

    db = STSDatabase(path)
    try:
        columns = {str(row[1]) for row in db.conn.execute("PRAGMA table_info(activity_logs)")}
        expected = {
            "occurred_at_utc", "category", "status", "operation_id", "actor_type",
            "actor_staff_id", "actor_admin_id", "actor_display_name", "session_id",
            "contract_id", "platform_name_snapshot", "contract_no_snapshot",
            "changed_fields_json", "technical_payload_json", "event_schema_version",
        }
        assert expected <= columns
        assert _count(db) == 1
        assert db.conn.execute("SELECT action FROM activity_logs").fetchone()[0] == "legacy_event"
        assert int(db.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]) == 19
        assert CURRENT_SCHEMA_VERSION == 19
        assert ACTIVITY_SCHEMA_VERSION == 18
        indexes = {str(row[1]) for row in db.conn.execute("PRAGMA index_list(activity_logs)")}
        assert {
            "idx_activity_logs_occurred_id",
            "idx_activity_logs_category_occurred",
            "idx_activity_logs_actor_staff_occurred",
            "idx_activity_logs_operation_id",
            "idx_activity_logs_action_occurred",
            "idx_activity_logs_entity_occurred",
            "idx_activity_logs_contract_occurred",
            "idx_activity_logs_platform_occurred",
        } <= indexes
        assert db.migration_backup_path is not None
        assert db.migration_backup_path.exists()
    finally:
        db.close()

    reopened = STSDatabase(path)
    try:
        assert _count(reopened) == 1
        assert reopened.init_schema() is not None
        assert _count(reopened) == 1
    finally:
        reopened.close()


def test_constructor_open_create_and_migration_do_not_write_activity_rows(tmp_path):
    new_path = tmp_path / "new.sts"
    db = STSDatabase(new_path, source="Main UI")
    try:
        assert _count(db) == 0
    finally:
        db.close()

    reopened = STSDatabase(new_path, source="STS Index Worker")
    try:
        assert _count(reopened) == 0
    finally:
        reopened.close()

    legacy_path = tmp_path / "migration.sts"
    _legacy_sts(legacy_path)
    migrated = STSDatabase(legacy_path, source="STS Load Worker")
    try:
        assert _count(migrated, "database_opened") == 0
        assert _count(migrated, "database_created") == 0
        assert _count(migrated, "schema_migrated") == 0
        assert _count(migrated) == 1
    finally:
        migrated.close()


def test_add_log_outside_transaction_is_committed(tmp_path):
    db = STSDatabase(tmp_path / "outside.sts")
    try:
        event_id = db.add_log("outside", actor="Ayşe", category="USER")
        assert isinstance(event_id, int) and event_id > 0
        reader = sqlite3.connect(db.path)
        try:
            assert reader.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0] == 1
        finally:
            reader.close()
    finally:
        db.close()


def test_business_update_and_activity_event_rollback_together(tmp_path):
    db = STSDatabase(tmp_path / "rollback.sts")
    try:
        db.conn.execute("CREATE TABLE phase1_business(id INTEGER PRIMARY KEY,value TEXT)")
        db.conn.commit()
        with pytest.raises(RuntimeError):
            with db.tx():
                db.conn.execute("INSERT INTO phase1_business(value) VALUES('business')")
                db.add_log("inside", actor="Ayşe", category="USER")
                raise RuntimeError("rollback")
        assert db.conn.execute("SELECT COUNT(*) FROM phase1_business").fetchone()[0] == 0
        assert _count(db) == 0
    finally:
        db.close()


def test_nested_transaction_savepoint_keeps_outer_ownership(tmp_path):
    db = STSDatabase(tmp_path / "nested.sts")
    try:
        db.conn.execute("CREATE TABLE phase1_business(id INTEGER PRIMARY KEY,value TEXT)")
        db.conn.commit()
        with pytest.raises(RuntimeError):
            with db.tx():
                db.conn.execute("INSERT INTO phase1_business(value) VALUES('outer')")
                with db.tx():
                    db.add_log("nested", actor="Ayşe")
                raise RuntimeError("outer rollback")
        assert db.conn.execute("SELECT COUNT(*) FROM phase1_business").fetchone()[0] == 0
        assert _count(db) == 0

        with db.tx():
            db.conn.execute("INSERT INTO phase1_business(value) VALUES('committed')")
            db.add_log("committed", actor="Ayşe")
        assert db.conn.execute("SELECT COUNT(*) FROM phase1_business").fetchone()[0] == 1
        assert _count(db) == 1
    finally:
        db.close()


def test_activity_insert_failure_is_visible_and_strict_policy_is_explicit(tmp_path, caplog):
    db = STSDatabase(tmp_path / "failure.sts")
    try:
        db.conn.execute("DROP TABLE activity_logs")
        db.conn.commit()
        with caplog.at_level(logging.ERROR, logger="src.services.activity_history_infra"):
            assert db.add_log("non_strict", strict=False) is None
        assert "Activity event insert failed" in caplog.text
        with pytest.raises(sqlite3.Error):
            db.add_log("strict", strict=True)
    finally:
        db.close()


def test_recursive_redaction_bounded_json_and_input_immutability(tmp_path):
    payload = {
        "password": "secret",
        "nested": {"PASSWORD_HASH": "hash"},
        "items": [{"invite_code": "ABC"}],
        "content_blob": b"secret bytes",
        "binary": b"other bytes",
        "path": Path("/very/private/location/report.xlsx"),
        "title": "Türkçe içerik",
    }
    original_nested = dict(payload["nested"])
    sanitized = sanitize_activity_value(payload)
    assert sanitized["password"] == REDACTED_VALUE
    assert sanitized["nested"]["PASSWORD_HASH"] == REDACTED_VALUE
    assert sanitized["items"][0]["invite_code"] == REDACTED_VALUE
    assert sanitized["content_blob"] == REDACTED_VALUE
    assert sanitized["binary"]["value"] == "[BINARY OMITTED]"
    assert sanitized["path"] == {"name": "report.xlsx", "path_redacted": True}
    assert payload["nested"] == original_nested

    encoded = activity_json({"text": "ş" * (MAX_ACTIVITY_JSON_BYTES * 2)})
    assert encoded is not None
    assert len(encoded.encode("utf-8")) <= MAX_ACTIVITY_JSON_BYTES
    assert "ş" in encoded

    db = STSDatabase(tmp_path / "redaction.sts")
    try:
        event_id = db.add_log(
            "redaction",
            actor="Ayşe",
            payload=payload,
            changed_fields=[{"field": "not", "before": "A", "after": "B"}],
            technical_payload={"access_token": "token", "safe": "değer"},
        )
        row = db.conn.execute(
            "SELECT payload_json,changed_fields_json,technical_payload_json FROM activity_logs WHERE id=?",
            (event_id,),
        ).fetchone()
        assert json.loads(row[0])["password"] == REDACTED_VALUE
        assert json.loads(row[1])[0]["field"] == "not"
        assert json.loads(row[2])["access_token"] == REDACTED_VALUE
    finally:
        db.close()


def test_store_actor_fallback_populates_legacy_and_structured_names(tmp_path):
    store = STSStore(tmp_path / "actor.sts", actor="Mehmet")
    try:
        event_id = store._log("current_actor")
        row = store.db.conn.execute(
            "SELECT actor,actor_display_name FROM activity_logs WHERE id=?", (event_id,)
        ).fetchone()
        assert tuple(row) == ("Mehmet", "Mehmet")
    finally:
        store.db.close()

    unknown = STSStore(tmp_path / "unknown.sts")
    try:
        event_id = unknown._log("unknown_actor")
        row = unknown.db.conn.execute(
            "SELECT actor,actor_display_name FROM activity_logs WHERE id=?", (event_id,)
        ).fetchone()
        assert tuple(row) == ("Kimliği belirlenemedi", "Kimliği belirlenemedi")
    finally:
        unknown.db.close()


def test_list_logs_uses_stable_order_and_new_filters_with_legacy_fallback(tmp_path):
    db = STSDatabase(tmp_path / "list.sts")
    try:
        first = db.add_log("one", actor="Ayşe", category="USER", operation_id="op-a")
        db.add_log("two", actor="Ayşe", category="TECHNICAL", operation_id="op-b")
        third = db.add_log("three", actor="Ayşe", category="USER", operation_id="op-a")
        db.conn.execute(
            "UPDATE activity_logs SET occurred_at_utc='2026-07-13T06:00:00Z' WHERE id IN (?,?)",
            (first, third),
        )
        db.conn.execute(
            "INSERT INTO activity_logs(created_at,actor,action,message) VALUES(?,?,?,?)",
            ("2025-01-01 00:00:00", "Legacy", "legacy", "legacy fallback"),
        )
        db.conn.commit()
        rows = db.list_logs(category="USER", operation_id="op-a")
        assert [row["action"] for row in rows] == ["three", "one"]
        all_rows = db.list_logs(limit=0)
        assert any(row["action"] == "legacy" for row in all_rows)
    finally:
        db.close()


def test_share_merge_audit_insert_remains_inside_caller_transaction(tmp_path):
    db = STSDatabase(tmp_path / "share.sts")
    try:
        ctx = SimpleNamespace(
            source=db.conn,
            actor="Merge Kullanıcısı",
            share_package_id="package-1",
            contract_merge_uid="contract-uid",
            operations_hash="operations-hash",
            contract_no="C-1",
        )
        db.conn.execute("BEGIN IMMEDIATE")
        _insert_audit_log(
            ctx,
            "MERGED",
            1,
            2,
            "pre-hash",
            "remote-hash",
            "post-hash",
            3,
            3,
            "backup.sts",
        )
        assert _count(db, "share_merge_applied") == 1
        db.conn.rollback()
        assert _count(db, "share_merge_applied") == 0
    finally:
        db.close()



def test_activity_behavior_is_defined_directly_in_source_files():
    database_source = Path("src/services/sts_database.py").read_text(encoding="utf-8")
    helper_source = Path("src/services/activity_history_infra.py").read_text(encoding="utf-8")
    package_source = Path("src/services/__init__.py").read_text(encoding="utf-8")
    store_source = Path("src/services/sts_store.py").read_text(encoding="utf-8")

    assert "CURRENT_SCHEMA_VERSION = 19" in database_source
    assert STSDatabase.add_log.__module__ == "src.services.sts_database"
    assert STSDatabase.tx.__module__ == "src.services.sts_database"
    assert STSDatabase.list_logs.__module__ == "src.services.sts_database"
    assert STSStore._log.__module__ == "src.services.sts_store"
    assert "install_activity_history_infrastructure" not in helper_source
    assert "_install_activity_history_infrastructure" not in package_source
    assert "_patch_add_log" not in helper_source
    assert "def add_log(" in database_source
    assert "def _log(" in store_source

    constructor_source = database_source[
        database_source.index("class STSDatabase:") : database_source.index("    def close(")
    ]
    assert "database_opened" not in constructor_source
    assert "database_created" not in constructor_source
    assert "schema_migrated" not in constructor_source


def test_externally_opened_transaction_is_not_committed_by_add_log(tmp_path):
    db = STSDatabase(tmp_path / "external.sts")
    try:
        db.conn.execute("BEGIN IMMEDIATE")
        event_id = db.add_log("external_transaction", actor="Ayşe")
        assert isinstance(event_id, int)
        assert _count(db) == 1

        reader = sqlite3.connect(db.path)
        try:
            assert reader.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0] == 0
        finally:
            reader.close()

        db.conn.rollback()
        assert _count(db) == 0
    finally:
        db.close()


def test_empty_action_and_structured_field_validation(tmp_path, caplog):
    db = STSDatabase(tmp_path / "validation.sts")
    try:
        with caplog.at_level(logging.ERROR, logger="src.services.sts_database"):
            assert db.add_log("", strict=False) is None
        assert "action is empty" in caplog.text
        with pytest.raises(ValueError):
            db.add_log("", strict=True)

        event_id = db.add_log(
            "x" * 500,
            source="s" * 1000,
            device="d" * 1000,
            entity_type="e" * 500,
            entity_key="k" * 1000,
            message="m" * 5000,
            platform_name_snapshot="p" * 1000,
            contract_no_snapshot="c" * 1000,
            operation_id="o" * 1000,
            session_id="i" * 1000,
            category="INVALID",
            status=" success ",
            actor_staff_id=0,
            actor_admin_id="invalid",
            contract_id=-1,
            event_schema_version=0,
        )
        row = db.conn.execute("SELECT * FROM activity_logs WHERE id=?", (event_id,)).fetchone()
        assert len(row["action"]) == 128
        assert len(row["source"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["device_name"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["entity_type"]) == 128
        assert len(row["entity_key"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["message"]) == MAX_ACTIVITY_MESSAGE_LENGTH
        assert len(row["platform_name_snapshot"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["contract_no_snapshot"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["operation_id"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert len(row["session_id"]) == MAX_ACTIVITY_FIELD_LENGTH
        assert row["category"] is None
        assert row["status"] == "SUCCESS"
        assert row["actor_staff_id"] is None
        assert row["actor_admin_id"] is None
        assert row["contract_id"] is None
        assert row["event_schema_version"] == 1
    finally:
        db.close()


def test_string_paths_are_redacted_and_sql_literals_are_not_persisted(tmp_path):
    payload = {
        "backup_path": "/home/private/user/yedekler/backup.sts",
        "source_path": r"C:\\Users\\Private\\source.xlsx",
        "nested": {"output_path": "/tmp/secret/report.xlsx"},
    }
    sanitized = sanitize_activity_value(payload)
    assert sanitized["backup_path"] == {"name": "backup.sts", "path_redacted": True}
    assert sanitized["source_path"] == {"name": "source.xlsx", "path_redacted": True}
    assert sanitized["nested"]["output_path"] == {"name": "report.xlsx", "path_redacted": True}

    db = STSDatabase(tmp_path / "sql.sts")
    try:
        secret_sql = (
            "UPDATE staff SET password_hash='HASH-SECRET', token='TOKEN-SECRET', "
            "invite_code='INVITE-SECRET', full_name='Kişisel Ad', payload=X'ABCD' WHERE id=1"
        )
        assert db.add_sql_query_log(secret_sql, duration_ms=7, affected_rows=1)
        row = db.conn.execute(
            "SELECT actor,payload_json FROM activity_logs WHERE action='sql_query_executed'"
        ).fetchone()
        payload_data = json.loads(row["payload_json"])
        assert payload_data == {
            "affected_rows": 1,
            "changed": True,
            "duration_ms": 7,
            "operation": "UPDATE",
        }
        serialized = json.dumps(dict(row), ensure_ascii=False)
        for secret in ("HASH-SECRET", "TOKEN-SECRET", "INVITE-SECRET", "Kişisel Ad", "ABCD"):
            assert secret not in serialized
        assert "query_preview" not in payload_data
    finally:
        db.close()


def test_representative_production_mutations_persist_business_and_audit(tmp_path):
    path = tmp_path / "representative.sts"
    store = STSStore(path, actor="Test Kullanıcısı")
    try:
        store.create_platform("AKINCI")
        assert store.db.conn.in_transaction is False
        store.write_users(
            [{"name": "Kullanıcı A", "yi_yd": "Yİ", "active": True, "note": ""}]
        )
        assert store.db.conn.in_transaction is False
        store.write_components(
            [{
                "name": "GÖVDE",
                "version": "1",
                "unit": "Adet",
                "active": True,
                "usage": 1,
                "note": "",
                "platforms": {"AKINCI": True},
            }]
        )
        assert store.db.conn.in_transaction is False
        contract = ContractInfo(
            no="AKN-AUDIT-001",
            platform="AKINCI",
            user="Kullanıcı A",
            yi_yd="Yİ",
            contract_type="Ana Sözleşme",
            signature_date="",
            t0_date="",
            t0_months=0,
            completion_date="",
        )
        store.write_contract(contract, [], {})
        assert store.db.conn.in_transaction is False
        source_file = tmp_path / "belge.txt"
        source_file.write_text("audit", encoding="utf-8")
        document_id = store.add_contract_file(
            "AKINCI", contract.no, source_file, contract.contract_type
        )
        assert document_id
        assert store.db.conn.in_transaction is False
        store.delete_contract("AKINCI", contract.no)
        assert store.db.conn.in_transaction is False
    finally:
        store.db.close()

    reopened = STSDatabase(path)
    try:
        assert reopened.conn.execute("SELECT COUNT(*) FROM platforms").fetchone()[0] == 1
        assert reopened.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert reopened.conn.execute("SELECT COUNT(*) FROM components").fetchone()[0] == 1
        actions = {
            row[0]
            for row in reopened.conn.execute("SELECT action FROM activity_logs").fetchall()
        }
        assert {
            "platform_created",
            "users_updated",
            "components_updated",
            "contract_created",
            "document_added",
            "contract_deleted",
        } <= actions
        assert {"user_created", "user_updated", "user_deleted", "component_created", "component_updated"}.isdisjoint(actions)
    finally:
        reopened.close()


def test_contract_update_does_not_leave_hidden_transaction_or_database_lock(tmp_path):
    path = tmp_path / "contract-lock.sts"
    store = STSStore(path, actor="Test Kullanıcısı")
    try:
        store.create_platform("AKINCI")
        contract = ContractInfo(
            no="AKN-LOCK-001",
            platform="AKINCI",
            user="",
            yi_yd="Yİ",
            contract_type="Ana Sözleşme",
            signature_date="",
            t0_date="",
            t0_months=0,
            completion_date="",
        )
        store.write_contract(contract, [], {})
        contract.note = "Revision değişikliği"
        store.write_contract(contract, [], {})
        assert store.db.conn.in_transaction is False

        second_writer = sqlite3.connect(path, timeout=1)
        try:
            second_writer.execute(
                "INSERT INTO activity_logs(created_at,actor,action) VALUES(?,?,?)",
                ("2026-07-13 10:00:00", "İkinci Bağlantı", "second_writer"),
            )
            second_writer.commit()
        finally:
            second_writer.close()
    finally:
        store.db.close()
