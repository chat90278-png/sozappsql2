from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.services.activity_history_policy import ActivityHistoryAccess, resolve_activity_history_access
from src.services.activity_history_query import (
    ActivityHistoryQuery,
    ActivityHistoryQueryError,
    ActivityHistoryQueryService,
)
from src.services.sts_database import CURRENT_SCHEMA_VERSION
from src.services.sts_store import STSStore


NORMAL_ACCESS = ActivityHistoryAccess(
    can_view=True,
    allowed_categories=frozenset({"USER", "MANAGEMENT"}),
    can_view_technical=False,
    can_view_internal_ids=False,
    can_view_raw_payloads=False,
)
TECHNICAL_ACCESS = ActivityHistoryAccess(
    can_view=True,
    allowed_categories=frozenset({"USER", "MANAGEMENT", "TECHNICAL"}),
    can_view_technical=True,
    can_view_internal_ids=True,
    can_view_raw_payloads=True,
)
DENIED_ACCESS = ActivityHistoryAccess(False, frozenset(), False, False, False)


@pytest.fixture
def store(tmp_path):
    value = STSStore(
        tmp_path / "history-query.sts",
        actor_context={"id": 7, "full_name": "Ayşe Personel"},
        session_id="session-7",
    )
    try:
        yield value
    finally:
        value.db.close()


def _event(
    store: STSStore,
    action: str,
    *,
    category: str | None = None,
    occurred: str = "2026-07-13T10:00:00Z",
    operation_id: str | None = None,
    message: str = "",
    payload=None,
    technical_payload=None,
    changed_fields=None,
    platform: str | None = None,
    contract_no: str | None = None,
    entity_type: str | None = "contract",
    entity_id: str | None = "11",
) -> int:
    event_id = store.db.add_log(
        action,
        actor="Ayşe Personel",
        actor_display_name="Ayşe Personel",
        actor_type="STAFF",
        actor_staff_id=7,
        session_id="session-7",
        category=category,
        operation_id=operation_id,
        message=message,
        payload=payload,
        technical_payload=technical_payload,
        changed_fields=changed_fields,
        platform=platform,
        contract_no=contract_no,
        contract_id=22,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    assert event_id is not None
    store.db.conn.execute(
        "UPDATE activity_logs SET occurred_at_utc=?, created_at=? WHERE id=?",
        (occurred, occurred, event_id),
    )
    store.db.conn.commit()
    return int(event_id)


def _query(store: STSStore, query: ActivityHistoryQuery, access=NORMAL_ACCESS, include_technical=False):
    return ActivityHistoryQueryService(store.db.conn).query(
        query, access=access, include_technical=include_technical
    )


def test_denied_access_returns_empty_without_query_side_effect(store):
    _event(store, "contract_created", category="USER")
    before = store.db.conn.total_changes
    page = _query(store, ActivityHistoryQuery(), DENIED_ACCESS)
    assert page.items == ()
    assert page.next_cursor is None
    assert store.db.conn.total_changes == before


def test_user_and_management_scope_excludes_technical(store):
    _event(store, "contract_created", category="USER")
    _event(store, "platform_updated", category="MANAGEMENT")
    _event(store, "sql_query_executed", category="TECHNICAL")
    page = _query(store, ActivityHistoryQuery(limit=20))
    assert {item.category for item in page.items} == {"USER", "MANAGEMENT"}


def test_technical_scope_requires_dual_permission(store):
    _event(store, "sql_query_executed", category="TECHNICAL")
    normal = _query(store, ActivityHistoryQuery(categories=("TECHNICAL",)), NORMAL_ACCESS)
    technical = _query(store, ActivityHistoryQuery(categories=("TECHNICAL",)), TECHNICAL_ACCESS, True)
    assert normal.items == ()
    assert [item.category for item in technical.items] == ["TECHNICAL"]


def test_include_technical_flag_cannot_bypass_policy(store):
    _event(store, "contract_updated", category="USER", payload={"safe": "value"})
    page = _query(store, ActivityHistoryQuery(), NORMAL_ACCESS, include_technical=True)
    assert page.items[0].technical is None


def test_multi_category_query_is_intersected_with_policy_scope(store):
    _event(store, "contract_updated", category="USER")
    _event(store, "platform_updated", category="MANAGEMENT")
    _event(store, "sql_query_executed", category="TECHNICAL")
    page = _query(
        store,
        ActivityHistoryQuery(categories=("USER", "TECHNICAL")),
        NORMAL_ACCESS,
    )
    assert [item.category for item in page.items] == ["USER"]


def test_action_and_search_sql_injection_are_bound_and_harmless(store):
    _event(store, "contract_created", category="USER", message="normal message")
    malicious = "x' OR 1=1 --"
    assert _query(store, ActivityHistoryQuery(actions=(malicious,))).items == ()
    assert _query(store, ActivityHistoryQuery(search_text=malicious)).items == ()
    assert store.db.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='activity_logs'"
    ).fetchone()[0] == 1


def test_like_percent_and_underscore_are_literal(store):
    _event(store, "contract_created", category="USER", message="oran %_ tamam")
    _event(store, "contract_updated", category="USER", message="oran XX tamam")
    page = _query(store, ActivityHistoryQuery(search_text="%_"))
    assert len(page.items) == 1
    assert page.items[0].action == "contract_created"


@pytest.mark.parametrize("requested,expected", [(0, 1), (-20, 1), (1, 1), (9999, 200)])
def test_limit_is_clamped_between_one_and_two_hundred(store, requested, expected):
    rows = [
        (f"2026-07-13T10:{index // 60:02d}:{index % 60:02d}Z", "contract_updated", "USER", "SUCCESS")
        for index in range(205)
    ]
    store.db.conn.executemany(
        "INSERT INTO activity_logs(created_at,action,category,status) VALUES(?,?,?,?)",
        rows,
    )
    store.db.conn.commit()
    page = _query(store, ActivityHistoryQuery(limit=requested))
    assert len(page.items) == expected


def test_malformed_cursor_raises_safe_validation_error(store):
    _event(store, "contract_created", category="USER")
    with pytest.raises(ActivityHistoryQueryError, match="imleci"):
        _query(store, ActivityHistoryQuery(cursor="not-base64-json"))


def test_cursor_filter_fingerprint_mismatch_is_rejected(store):
    for index in range(3):
        _event(store, "contract_updated", category="USER", occurred=f"2026-07-13T10:00:0{index}Z")
    first = _query(store, ActivityHistoryQuery(limit=1, search_text=""))
    assert first.next_cursor
    with pytest.raises(ActivityHistoryQueryError, match="uyumlu değil"):
        _query(store, ActivityHistoryQuery(limit=1, cursor=first.next_cursor, search_text="other"))


def test_same_timestamp_cursor_has_no_duplicate_or_skip(store):
    ids = [_event(store, "contract_updated", category="USER") for _ in range(5)]
    seen: list[int] = []
    cursor = None
    while True:
        page = _query(store, ActivityHistoryQuery(limit=2, cursor=cursor))
        seen.extend(item.id for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor
    assert seen == sorted(ids, reverse=True)
    assert len(seen) == len(set(seen)) == 5


def test_legacy_null_occurred_at_uses_created_at_fallback(store):
    event_id = _event(store, "contract_created", category="USER")
    store.db.conn.execute(
        "UPDATE activity_logs SET occurred_at_utc=NULL, created_at='2020-01-02T03:04:05Z' WHERE id=?",
        (event_id,),
    )
    store.db.conn.commit()
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert item.occurred_at == "2020-01-02T03:04:05Z"


def test_legacy_null_category_is_inferred_from_action(store):
    event_id = _event(store, "contract_created", category="USER")
    store.db.conn.execute("UPDATE activity_logs SET category=NULL WHERE id=?", (event_id,))
    store.db.conn.commit()
    item = _query(store, ActivityHistoryQuery(categories=("USER",))).items[0]
    assert item.category == "USER"


def test_deterministic_timestamp_then_id_desc_order(store):
    ids = [_event(store, "contract_updated", category="USER") for _ in range(3)]
    assert [item.id for item in _query(store, ActivityHistoryQuery()).items] == sorted(ids, reverse=True)


def test_query_is_read_only_and_preserves_open_transaction(store):
    _event(store, "contract_created", category="USER")
    count_before = store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
    store.db.conn.execute("BEGIN")
    assert store.db.conn.in_transaction
    changes_before = store.db.conn.total_changes
    _query(store, ActivityHistoryQuery())
    assert store.db.conn.in_transaction
    assert store.db.conn.total_changes == changes_before
    assert store.db.conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0] == count_before
    store.db.conn.rollback()


def test_normal_projection_omits_source_device_session_ids_and_raw_json(store):
    _event(store, "contract_updated", category="USER", payload={"safe": "value"})
    item = _query(store, ActivityHistoryQuery(), NORMAL_ACCESS, True).items[0]
    assert item.technical is None
    serialized = json.dumps(asdict(item), ensure_ascii=False)
    assert "session-7" not in serialized
    assert "Main UI" not in serialized
    assert '"entity_id"' not in serialized


def test_technical_projection_is_sanitized_and_never_exposes_secrets_sql_or_full_path(store):
    _event(
        store,
        "sql_query_executed",
        category="TECHNICAL",
        payload={
            "password": "plain-secret",
            "access_token": "token-secret",
            "query_preview": "DELETE FROM contracts WHERE contract_no='A'",
            "database_path": "C:/private/folder/secret.sts",
            "safe": "ok",
        },
        technical_payload={"private_key": "key-secret", "affected_rows": 1},
    )
    item = _query(
        store,
        ActivityHistoryQuery(categories=("TECHNICAL",)),
        TECHNICAL_ACCESS,
        True,
    ).items[0]
    assert item.technical is not None
    serialized = json.dumps(asdict(item.technical), ensure_ascii=False, sort_keys=True)
    for secret in ("plain-secret", "token-secret", "DELETE FROM", "key-secret", "C:/private"):
        assert secret not in serialized
    assert "secret.sts" in serialized
    assert '"safe": "ok"' in serialized


def test_corrupt_changed_fields_json_does_not_drop_item(store):
    event_id = _event(store, "contract_updated", category="USER")
    store.db.conn.execute(
        "UPDATE activity_logs SET changed_fields_json='{not-json' WHERE id=?", (event_id,)
    )
    store.db.conn.commit()
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert item.changed_fields == ()
    assert item.changed_fields_parse_error is True


def test_changed_fields_projection_is_stable_and_excludes_secret_fields(store):
    _event(
        store,
        "contract_updated",
        category="USER",
        changed_fields=[
            {"field": "zeta", "before": 1, "after": 2},
            {"field": "password", "before": "a", "after": "b"},
            {"field": "alpha", "before": "x", "after": "y"},
        ],
    )
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert [change.field for change in item.changed_fields] == ["zeta", "alpha"]
    assert "password" not in json.dumps(asdict(item), ensure_ascii=False)


def test_deleted_platform_uses_snapshot_name(store):
    store.db.conn.execute("INSERT INTO platforms(name) VALUES('AKINCI')")
    store.db.conn.commit()
    _event(store, "platform_updated", category="MANAGEMENT", platform="AKINCI")
    store.db.conn.execute("DELETE FROM platforms WHERE name='AKINCI'")
    store.db.conn.commit()
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert item.platform_name == "AKINCI"


def test_deleted_contract_history_uses_contract_snapshot(store):
    _event(store, "contract_deleted", category="USER", contract_no="CN-77")
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert item.contract_no == "CN-77"


def test_unknown_action_has_safe_fallback_label(store):
    _event(store, "legacy_custom_action", category="USER")
    item = _query(store, ActivityHistoryQuery()).items[0]
    assert item.action_label == "Legacy custom action"
    assert item.title


def test_unknown_actor_falls_back_safely(store):
    event_id = _event(store, "contract_created", category="USER")
    store.db.conn.execute(
        "UPDATE activity_logs SET actor=NULL, actor_display_name=NULL WHERE id=?", (event_id,)
    )
    store.db.conn.commit()
    assert _query(store, ActivityHistoryQuery()).items[0].actor_display_name == "Kimliği belirlenemedi"


def test_operation_group_key_is_opaque_for_normal_and_full_id_only_technical(store):
    operation_id = "550e8400-e29b-41d4-a716-446655440000"
    _event(store, "contract_updated", category="USER", operation_id=operation_id)
    normal = _query(store, ActivityHistoryQuery(), NORMAL_ACCESS, True).items[0]
    technical = _query(store, ActivityHistoryQuery(), TECHNICAL_ACCESS, True).items[0]
    assert normal.operation_group_key.startswith("op_")
    assert operation_id not in json.dumps(asdict(normal), ensure_ascii=False)
    assert technical.technical.operation_id == operation_id


def test_internal_id_filters_require_technical_access(store):
    _event(store, "contract_updated", category="USER")
    with pytest.raises(ActivityHistoryQueryError, match="teknik erişim"):
        _query(store, ActivityHistoryQuery(contract_id=22), NORMAL_ACCESS)
    assert len(_query(store, ActivityHistoryQuery(contract_id=22), TECHNICAL_ACCESS).items) == 1


def test_full_operation_id_filter_requires_technical_access(store):
    _event(store, "contract_updated", category="USER", operation_id="operation-1")
    with pytest.raises(ActivityHistoryQueryError, match="teknik erişim"):
        _query(store, ActivityHistoryQuery(operation_id="operation-1"), NORMAL_ACCESS)


def test_operation_detail_scopes_categories_and_prevents_technical_leakage(store):
    op = "operation-shared"
    _event(store, "contract_updated", category="USER", operation_id=op, occurred="2026-07-13T10:00:01Z")
    _event(store, "sql_query_executed", category="TECHNICAL", operation_id=op, occurred="2026-07-13T10:00:02Z")
    service = ActivityHistoryQueryService(store.db.conn)
    normal = service.get_operation_events(op, access=NORMAL_ACCESS)
    technical = service.get_operation_events(op, access=TECHNICAL_ACCESS)
    assert [item.category for item in normal] == ["USER"]
    assert {item.category for item in technical} == {"USER", "TECHNICAL"}


def test_operation_detail_is_ascending_and_limited(store):
    op = "operation-order"
    ids = [
        _event(store, "contract_updated", category="USER", operation_id=op, occurred=f"2026-07-13T10:00:0{i}Z")
        for i in (3, 1, 2)
    ]
    items = ActivityHistoryQueryService(store.db.conn).get_operation_events(
        op, access=NORMAL_ACCESS, limit=2
    )
    assert len(items) == 2
    assert [item.occurred_at for item in items] == sorted(item.occurred_at for item in items)
    assert {item.id for item in items}.issubset(set(ids))


def test_empty_operation_id_does_not_query(store):
    _event(store, "contract_updated", category="USER", operation_id="operation")
    service = ActivityHistoryQueryService(store.db.conn)
    assert service.get_operation_events("", access=NORMAL_ACCESS) == ()
    assert service.get_operation_events("   ", access=NORMAL_ACCESS) == ()


def test_operation_query_never_returns_other_operation(store):
    _event(store, "contract_updated", category="USER", operation_id="wanted")
    _event(store, "system_updated", category="USER", operation_id="other")
    items = ActivityHistoryQueryService(store.db.conn).get_operation_events(
        "wanted", access=NORMAL_ACCESS
    )
    assert len(items) == 1
    assert items[0].action == "contract_updated"


def test_legacy_list_logs_compatibility_is_preserved(store):
    _event(store, "contract_updated", category="USER")
    rows = store.list_logs(limit=0, category="USER")
    assert len(rows) == 1
    assert rows[0]["action"] == "contract_updated"


def test_schema_version_remains_eighteen():
    assert CURRENT_SCHEMA_VERSION == 19


def test_policy_can_be_resolved_with_real_permission_codes_only():
    principal = {"permissions": {"view_action_history", "access_database_tools"}, "role": "viewer"}
    access = resolve_activity_history_access(
        principal, lambda user, code: code in user["permissions"]
    )
    assert access.can_view_technical is True


def test_dialog_constructor_fails_closed_without_access(store):
    from src.ui.dialogs.activity_logs import ActivityLogDialog

    with pytest.raises(PermissionError):
        ActivityLogDialog(store, access=None)
    with pytest.raises(PermissionError):
        ActivityLogDialog(store, access=DENIED_ACCESS)


def test_main_window_direct_open_is_denied_before_dialog_creation(monkeypatch):
    from src.ui.main_window import MainWindow

    warnings = []
    monkeypatch.setattr(
        "src.ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    dummy = SimpleNamespace(
        activity_history_access=lambda: DENIED_ACCESS,
        store=SimpleNamespace(query_activity_history=lambda *args, **kwargs: None),
        open_or_raise_tool_window=lambda *args, **kwargs: pytest.fail("dialog should not open"),
    )
    MainWindow.open_activity_logs(dummy)
    assert warnings


def test_main_window_system_admin_can_open_via_policy(monkeypatch):
    from src.ui.main_window import MainWindow

    opened = []
    admin_access = resolve_activity_history_access(
        {"is_admin": True, "is_active": 1}, lambda _principal, _code: False
    )
    dummy = SimpleNamespace(
        activity_history_access=lambda: admin_access,
        store=SimpleNamespace(query_activity_history=lambda *args, **kwargs: None),
        open_or_raise_tool_window=lambda *args, **kwargs: opened.append((args, kwargs)),
    )
    MainWindow.open_activity_logs(dummy)
    assert opened and opened[0][0][0] == "report:activity_logs"


def test_permission_refresh_updates_activity_menu_visibility():
    from src.ui.main_window import MainWindow

    class FakeAction:
        def __init__(self):
            self.visible = None

        def setVisible(self, value):
            self.visible = bool(value)

    state = {"access": NORMAL_ACCESS}
    dummy = SimpleNamespace(
        current_staff={"is_admin": False},
        activity_logs_action=FakeAction(),
        system_menu_action=FakeAction(),
        _is_admin_staff=lambda: False,
        _has_permission_context=lambda: True,
        activity_history_access=lambda: state["access"],
        _permission_action_visible=lambda _code: False,
    )
    MainWindow._refresh_permission_actions(dummy)
    assert dummy.activity_logs_action.visible is True
    assert dummy.system_menu_action.visible is True
    state["access"] = DENIED_ACCESS
    MainWindow._refresh_permission_actions(dummy)
    assert dummy.activity_logs_action.visible is False
    assert dummy.system_menu_action.visible is False
