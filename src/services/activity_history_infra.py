from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


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
    return normalize_activity_text(value, max_length=64).upper() or "SUCCESS"


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
