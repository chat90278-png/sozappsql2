from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.services.activity_history_policy import resolve_activity_history_access


def _checker(principal, code):
    return code in set(principal.get("permissions") or ())


def test_none_principal_is_denied():
    access = resolve_activity_history_access(None, _checker)
    assert access.can_view is False
    assert access.allowed_categories == frozenset()


def test_missing_view_permission_is_denied():
    access = resolve_activity_history_access({"permissions": {"access_database_tools"}}, _checker)
    assert access.can_view is False
    assert access.can_view_technical is False


def test_view_permission_allows_user_and_management_only():
    access = resolve_activity_history_access({"permissions": {"view_action_history"}}, _checker)
    assert access.can_view is True
    assert access.allowed_categories == frozenset({"USER", "MANAGEMENT"})
    assert access.can_view_technical is False


def test_dual_permission_allows_technical_and_internal_projection():
    access = resolve_activity_history_access(
        {"permissions": {"view_action_history", "access_database_tools"}}, _checker
    )
    assert access.allowed_categories == frozenset({"USER", "MANAGEMENT", "TECHNICAL"})
    assert access.can_view_technical is True
    assert access.can_view_internal_ids is True
    assert access.can_view_raw_payloads is True


def test_active_system_admin_has_full_scope_without_role_name_checks():
    access = resolve_activity_history_access(
        {"is_admin": True, "is_active": 1, "role": "viewer", "permissions": set()},
        lambda _principal, _code: False,
    )
    assert access.can_view is True
    assert access.allowed_categories == frozenset({"USER", "MANAGEMENT", "TECHNICAL"})


def test_inactive_system_admin_is_denied_without_permissions():
    access = resolve_activity_history_access(
        {"is_admin": True, "is_active": 0, "permissions": set()}, _checker
    )
    assert access.can_view is False


def test_role_name_never_replaces_permission_code():
    access = resolve_activity_history_access(
        {"role": "admin", "role_display_name": "Sistem Yöneticisi", "permissions": set()},
        _checker,
    )
    assert access.can_view is False


def test_permission_checker_exception_fails_closed():
    def broken(_principal, _code):
        raise RuntimeError("permission database unavailable")

    access = resolve_activity_history_access({"permissions": {"view_action_history"}}, broken)
    assert access.can_view is False
    assert access.allowed_categories == frozenset()


def test_database_tools_without_view_permission_cannot_enable_technical_scope():
    access = resolve_activity_history_access(
        {"permissions": {"access_database_tools"}}, _checker
    )
    assert access.can_view_technical is False
    assert "TECHNICAL" not in access.allowed_categories


def test_policy_result_is_immutable():
    access = resolve_activity_history_access({"permissions": {"view_action_history"}}, _checker)
    with pytest.raises(FrozenInstanceError):
        access.can_view = False  # type: ignore[misc]
