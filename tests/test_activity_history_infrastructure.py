from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.activity_history_infra import (
    ACTIVITY_SCHEMA_VERSION,
    MAX_ACTIVITY_JSON_BYTES,
    REDACTED_VALUE,
    activity_json,
    sanitize_activity_value,
)
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
        assert int(db.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]) == 18
        assert CURRENT_SCHEMA_VERSION == ACTIVITY_SCHEMA_VERSION == 18
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
