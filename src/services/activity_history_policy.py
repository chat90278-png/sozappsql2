from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from src.services.activity_history_infra import ALLOWED_CATEGORIES


PermissionChecker = Callable[[Mapping[str, Any], str], bool]


@dataclass(frozen=True)
class ActivityHistoryAccess:
    """Immutable authorization result shared by UI, query and projection layers."""

    can_view: bool
    allowed_categories: frozenset[str]
    can_view_technical: bool
    can_view_internal_ids: bool
    can_view_raw_payloads: bool


_DENIED_ACCESS = ActivityHistoryAccess(
    can_view=False,
    allowed_categories=frozenset(),
    can_view_technical=False,
    can_view_internal_ids=False,
    can_view_raw_payloads=False,
)


def _is_active_system_admin(principal: Mapping[str, Any] | None) -> bool:
    if not principal or not bool(principal.get("is_admin")):
        return False
    try:
        return int(principal.get("is_active", 1) if principal.get("is_active") is not None else 1) != 0
    except (TypeError, ValueError):
        return False


def resolve_activity_history_access(
    principal: Mapping[str, Any] | None,
    permission_checker: PermissionChecker,
) -> ActivityHistoryAccess:
    """Resolve activity visibility exclusively from permission codes and system-admin state.

    Any invalid principal or checker failure is denied. Role names are deliberately ignored.
    """

    if principal is None:
        return _DENIED_ACCESS

    principal_map = dict(principal)
    if _is_active_system_admin(principal_map):
        return ActivityHistoryAccess(
            can_view=True,
            allowed_categories=frozenset(ALLOWED_CATEGORIES),
            can_view_technical=True,
            can_view_internal_ids=True,
            can_view_raw_payloads=True,
        )

    try:
        can_view = bool(permission_checker(principal_map, "view_action_history"))
        can_use_db_tools = bool(permission_checker(principal_map, "access_database_tools"))
    except Exception:
        return _DENIED_ACCESS

    if not can_view:
        return _DENIED_ACCESS

    can_technical = can_view and can_use_db_tools
    categories = {"USER", "MANAGEMENT"}
    if can_technical:
        categories.add("TECHNICAL")
    return ActivityHistoryAccess(
        can_view=True,
        allowed_categories=frozenset(categories),
        can_view_technical=can_technical,
        can_view_internal_ids=can_technical,
        can_view_raw_payloads=can_technical,
    )


__all__ = [
    "ActivityHistoryAccess",
    "PermissionChecker",
    "resolve_activity_history_access",
]
