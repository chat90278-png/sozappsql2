from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ACTIVITY_EVENT_SCHEMA_VERSION = 1
ACTIVITY_SCHEMA_VERSION = 18
MAX_ACTIVITY_JSON_BYTES = 16 * 1024
MAX_ACTIVITY_VALUE_STRING_LENGTH = 2048
MAX_ACTIVITY_FIELD_LENGTH = 512
MAX_ACTIVITY_MESSAGE_LENGTH = 2048
MAX_COLLECTION_ITEMS = 100
REDACTED_VALUE = "[REDACTED]"
OMITTED_BINARY_VALUE = "[BINARY OMITTED]"
UNKNOWN_ACTOR = "Kimliği belirlenemedi"
ALLOWED_CATEGORIES = frozenset({"USER", "MANAGEMENT", "TECHNICAL"})
ALLOWED_ACTOR_TYPES = frozenset({"STAFF", "ADMIN", "SYSTEM", "UNKNOWN"})
ALLOWED_STATUSES = frozenset({"SUCCESS", "FAILED", "PARTIAL"})
ACTION_ALIASES = {
    "platform_order_updated": "platform_order_changed",
    "component_order_updated": "components_updated",
    "database_vacuum_completed": "database_vacuumed",
    "database_optimize_completed": "database_optimized",
    "tag_upserted": "tag_updated",
    "document_folder_created": "document_added",
    "document_folder_deleted": "document_deleted",
    "document_folder_moved": "document_moved",
    "document_folder_renamed": "document_renamed",
}
USER_ACTIONS = frozenset({
    "contract_created", "contract_updated", "contract_deleted", "contract_status_changed",
    "contract_tags_updated", "system_created", "system_updated", "system_deleted",
    "system_component_updated", "delivery_created", "delivery_updated", "delivery_deleted",
    "delivery_status_changed", "document_added", "document_updated", "document_deleted",
    "document_moved", "document_renamed", "documents_locked", "documents_unlocked",
    "share_merge_applied",
})
MANAGEMENT_ACTIONS = frozenset({
    "platform_created", "platform_updated", "platform_deleted", "platform_order_changed",
    "platform_exclusions_updated", "platform_logo_updated", "users_updated", "user_created",
    "user_updated", "user_deleted", "components_updated", "component_created",
    "component_updated", "component_deleted", "tag_created", "tag_updated", "tag_deleted",
    "tag_snapshot_updated",
})
TECHNICAL_ACTIONS = frozenset({
    "sql_query_executed", "database_backup_created", "database_optimized",
    "database_vacuumed", "excel_exported", "excel_export_failed",
})


@dataclass(frozen=True)
class ActivityOperation:
    operation_id: str
    name: str = ""
    actor_context: dict[str, Any] | None = None
    category: str | None = None
    contract_id: int | None = None
    platform: str | None = None
    contract_no: str | None = None
    session_id: str | None = None

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "password_hash",
        "admin_password_hash",
        "invite_code",
        "authorization_code",
        "invite_code_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "private_key",
        "content_blob",
    }
)
PATH_LIKE_KEYS = frozenset(
    {
        "path",
        "file_path",
        "filepath",
        "output_path",
        "backup_path",
        "source_path",
        "target_path",
        "local_path",
        "db_path",
        "database_path",
    }
)


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_activity_text(value: Any, *, max_length: int = MAX_ACTIVITY_FIELD_LENGTH) -> str:
    """Normalize a free-text event field without breaking Unicode characters."""
    text = str(value or "").strip()
    limit = max(1, int(max_length or MAX_ACTIVITY_FIELD_LENGTH))
    return text[:limit]


def safe_positive_int(value: Any) -> int | None:
    """Return a positive integer identifier, otherwise None."""
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_activity_category(value: Any) -> str | None:
    category = normalize_activity_text(value, max_length=32).upper()
    return category if category in ALLOWED_CATEGORIES else None


def normalize_activity_status(value: Any) -> str:
    status = normalize_activity_text(value, max_length=64).upper()
    return status if status in ALLOWED_STATUSES else "SUCCESS"


def canonical_activity_action(value: Any) -> str:
    action = normalize_activity_text(value, max_length=128).casefold()
    return ACTION_ALIASES.get(action, action)


def infer_activity_category(action: Any, explicit: Any = None) -> str | None:
    explicit_category = normalize_activity_category(explicit)
    if explicit_category is not None:
        return explicit_category
    canonical = canonical_activity_action(action)
    if canonical in USER_ACTIONS:
        return "USER"
    if canonical in MANAGEMENT_ACTIONS:
        return "MANAGEMENT"
    if canonical in TECHNICAL_ACTIONS or canonical.startswith("performance_"):
        return "TECHNICAL"
    return None


def normalize_actor_type(value: Any, *, default: str | None = None) -> str | None:
    actor_type = normalize_activity_text(value, max_length=32).upper()
    if actor_type in ALLOWED_ACTOR_TYPES:
        return actor_type
    fallback = normalize_activity_text(default, max_length=32).upper()
    return fallback if fallback in ALLOWED_ACTOR_TYPES else None


def normalize_event_schema_version(value: Any) -> int:
    parsed = safe_positive_int(value)
    return parsed or ACTIVITY_EVENT_SCHEMA_VERSION


def _normalized_key(key: Any) -> str:
    return str(key or "").strip().casefold()


def _is_sensitive_key(key: Any) -> bool:
    return _normalized_key(key) in SENSITIVE_KEYS


def _is_path_like_key(key: Any) -> bool:
    return _normalized_key(key) in PATH_LIKE_KEYS


def _safe_path_name(value: Any) -> str:
    if isinstance(value, Path):
        return value.name
    text = str(value or "").strip().rstrip("/\\")
    if not text:
        return ""
    return re.split(r"[/\\]+", text)[-1]


def redact_path_value(value: Any) -> Any:
    if isinstance(value, (str, Path)):
        return {"name": _safe_path_name(value), "path_redacted": True}
    return sanitize_activity_value(value)


def _normalize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > MAX_ACTIVITY_VALUE_STRING_LENGTH:
            omitted = len(value) - MAX_ACTIVITY_VALUE_STRING_LENGTH
            return value[:MAX_ACTIVITY_VALUE_STRING_LENGTH] + f"… [truncated {omitted} chars]"
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return redact_path_value(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"value": OMITTED_BINARY_VALUE, "size_bytes": len(value)}
    return None


def sanitize_activity_value(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Recursively normalize and redact activity payloads without mutating input."""
    scalar = _normalize_scalar(value)
    if scalar is not None or value is None:
        return scalar

    seen = _seen if _seen is not None else set()
    marker = id(value)
    if marker in seen:
        return "[RECURSIVE VALUE OMITTED]"

    if isinstance(value, dict):
        seen.add(marker)
        try:
            out: dict[str, Any] = {}
            items = sorted(value.items(), key=lambda item: str(item[0]).casefold())
            for index, (raw_key, raw_value) in enumerate(items):
                if index >= MAX_COLLECTION_ITEMS:
                    out["_truncated_items"] = len(items) - MAX_COLLECTION_ITEMS
                    break
                key = str(raw_key)
                if _is_sensitive_key(key):
                    out[key] = REDACTED_VALUE
                elif _is_path_like_key(key) and isinstance(raw_value, (str, Path)):
                    out[key] = redact_path_value(raw_value)
                else:
                    out[key] = sanitize_activity_value(raw_value, _seen=seen)
            return out
        finally:
            seen.remove(marker)

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(marker)
        try:
            items = list(value)
            if isinstance(value, (set, frozenset)):
                items = sorted(items, key=lambda item: repr(item))
            out = [sanitize_activity_value(item, _seen=seen) for item in items[:MAX_COLLECTION_ITEMS]]
            if len(items) > MAX_COLLECTION_ITEMS:
                out.append({"_truncated_items": len(items) - MAX_COLLECTION_ITEMS})
            return out
        finally:
            seen.remove(marker)

    if hasattr(value, "__dict__"):
        return {
            "_type": type(value).__name__,
            "value": sanitize_activity_value(vars(value), _seen=seen),
        }

    return {
        "_type": type(value).__name__,
        "value": str(value)[:MAX_ACTIVITY_VALUE_STRING_LENGTH],
    }


def activity_json(value: Any) -> str | None:
    if value is None:
        return None
    sanitized = sanitize_activity_value(value)
    encoded = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encoded_size = len(encoded.encode("utf-8"))
    if encoded_size <= MAX_ACTIVITY_JSON_BYTES:
        return encoded

    preview_budget = max(256, MAX_ACTIVITY_JSON_BYTES - 256)
    preview = encoded.encode("utf-8")[:preview_budget].decode("utf-8", errors="ignore")
    bounded = {
        "_truncated": True,
        "_original_size_bytes": encoded_size,
        "_preview": preview,
    }
    result = json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return result[:MAX_ACTIVITY_JSON_BYTES]


def actor_context_from_principal(
    principal: Mapping[str, Any] | None,
    *,
    fallback_actor: Any = None,
    session_id: Any = None,
    system: bool = False,
) -> dict[str, Any]:
    """Build a redaction-safe structured actor context from the real session principal."""
    data = dict(principal or {})
    if system:
        actor_type = "SYSTEM"
    elif bool(data.get("is_admin")):
        actor_type = "ADMIN"
    elif safe_positive_int(data.get("id") or data.get("staff_id")):
        actor_type = "STAFF"
    else:
        actor_type = "UNKNOWN"
    display_name = normalize_activity_text(
        data.get("full_name")
        or data.get("admin_name")
        or data.get("username")
        or data.get("device_name")
        or fallback_actor,
        max_length=MAX_ACTIVITY_FIELD_LENGTH,
    ) or UNKNOWN_ACTOR
    return {
        "actor_type": actor_type,
        "actor_staff_id": (
            safe_positive_int(data.get("staff_id") or data.get("id"))
            if actor_type == "STAFF"
            else None
        ),
        "actor_admin_id": (
            safe_positive_int(data.get("admin_id") or data.get("id"))
            if actor_type == "ADMIN"
            else None
        ),
        "actor_display_name": display_name,
        "session_id": normalize_activity_text(
            data.get("session_id") or session_id, max_length=MAX_ACTIVITY_FIELD_LENGTH
        ) or None,
    }


def normalize_actor_context(
    value: Mapping[str, Any] | None,
    *,
    fallback_actor: Any = None,
    session_id: Any = None,
) -> dict[str, Any]:
    data = dict(value or {})
    actor_type = normalize_actor_type(data.get("actor_type"), default="UNKNOWN") or "UNKNOWN"
    display_name = normalize_activity_text(
        data.get("actor_display_name") or data.get("actor") or fallback_actor,
        max_length=MAX_ACTIVITY_FIELD_LENGTH,
    ) or UNKNOWN_ACTOR
    return {
        "actor_type": actor_type,
        "actor_staff_id": safe_positive_int(data.get("actor_staff_id")) if actor_type == "STAFF" else None,
        "actor_admin_id": safe_positive_int(data.get("actor_admin_id")) if actor_type == "ADMIN" else None,
        "actor_display_name": display_name,
        "session_id": normalize_activity_text(
            data.get("session_id") or session_id, max_length=MAX_ACTIVITY_FIELD_LENGTH
        ) or None,
    }


def stable_activity_value(value: Any, *, unordered: bool = False) -> Any:
    """Return a deterministic, redacted comparison value without mutating input."""
    normalized = sanitize_activity_value(value)
    if unordered and isinstance(normalized, list):
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    return normalized


def activity_values_equal(left: Any, right: Any, *, unordered: bool = False) -> bool:
    return stable_activity_value(left, unordered=unordered) == stable_activity_value(right, unordered=unordered)


def build_changed_fields(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    set_like_fields: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the stable changed_fields_json contract for only genuinely changed values."""
    before_map = dict(before or {})
    after_map = dict(after or {})
    unordered_fields = {str(item) for item in (set_like_fields or set())}
    changes: list[dict[str, Any]] = []
    for field in sorted(set(before_map) | set(after_map), key=lambda item: str(item).casefold()):
        key = str(field)
        unordered = key in unordered_fields
        raw_before = before_map.get(field)
        raw_after = after_map.get(field)
        if _is_sensitive_key(key):
            if field in before_map and field in after_map and raw_before == raw_after:
                continue
            before_value = REDACTED_VALUE if field in before_map else None
            after_value = REDACTED_VALUE if field in after_map else None
        elif _is_path_like_key(key):
            if field in before_map and field in after_map and str(raw_before) == str(raw_after):
                continue
            before_value = redact_path_value(raw_before) if field in before_map else None
            after_value = redact_path_value(raw_after) if field in after_map else None
        else:
            before_value = stable_activity_value(raw_before, unordered=unordered)
            after_value = stable_activity_value(raw_after, unordered=unordered)
            if before_value == after_value:
                continue
        changes.append({"field": key, "before": before_value, "after": after_value})
    return changes
