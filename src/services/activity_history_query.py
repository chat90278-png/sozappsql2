from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from src.services.activity_history_infra import (
    ACTION_ALIASES,
    ALLOWED_CATEGORIES,
    UNKNOWN_ACTOR,
    canonical_activity_action,
    infer_activity_category,
    normalize_activity_category,
    normalize_activity_status,
    normalize_activity_text,
    sanitize_activity_value,
    safe_positive_int,
)
from src.services.activity_history_policy import ActivityHistoryAccess


MAX_QUERY_LIMIT = 200
DEFAULT_QUERY_LIMIT = 50
_CURSOR_VERSION = 1
_EFFECTIVE_TIME_SQL = "COALESCE(NULLIF(l.occurred_at_utc,''),l.created_at)"


class ActivityHistoryQueryError(ValueError):
    """Safe validation error for malformed or unauthorized history queries."""


@dataclass(frozen=True)
class ActivityHistoryQuery:
    categories: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    actor_text: str = ""
    search_text: str = ""
    platform_id: int | None = None
    platform_text: str = ""
    contract_id: int | None = None
    contract_no: str = ""
    operation_id: str = ""
    occurred_from_utc: str | None = None
    occurred_to_utc: str | None = None
    limit: int = DEFAULT_QUERY_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class ActivityFieldChange:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True)
class ActivityTechnicalDetails:
    source: str | None
    device_name: str | None
    actor_staff_id: int | None
    actor_admin_id: int | None
    session_id: str | None
    entity_id: str | None
    contract_id: int | None
    platform_id: int | None
    before: Any
    after: Any
    payload: Any
    technical_payload: Any
    event_schema_version: int | None
    operation_id: str | None


@dataclass(frozen=True)
class ActivityHistoryItem:
    id: int
    occurred_at: str
    category: str
    action: str
    action_label: str
    status: str
    actor_display_name: str
    title: str
    summary: str
    entity_type: str | None
    entity_label: str | None
    platform_name: str | None
    contract_no: str | None
    changed_fields: tuple[ActivityFieldChange, ...]
    changed_fields_parse_error: bool
    operation_group_key: str | None
    technical: ActivityTechnicalDetails | None


@dataclass(frozen=True)
class ActivityHistoryPage:
    items: tuple[ActivityHistoryItem, ...]
    next_cursor: str | None
    has_more: bool


_ACTION_LABELS = {
    "contract_created": "Sözleşme oluşturuldu",
    "contract_updated": "Sözleşme güncellendi",
    "contract_deleted": "Sözleşme silindi",
    "system_created": "Sistem oluşturuldu",
    "system_updated": "Sistem güncellendi",
    "system_deleted": "Sistem silindi",
    "delivery_created": "Teslimat oluşturuldu",
    "delivery_updated": "Teslimat güncellendi",
    "delivery_deleted": "Teslimat silindi",
    "document_added": "Belge eklendi",
    "document_updated": "Belge güncellendi",
    "document_deleted": "Belge silindi",
    "document_moved": "Belge taşındı",
    "document_renamed": "Belge yeniden adlandırıldı",
    "documents_locked": "Belgeler kilitlendi",
    "documents_unlocked": "Belge kilidi açıldı",
    "share_merge_applied": "Paylaşım değişiklikleri birleştirildi",
    "platform_created": "Platform oluşturuldu",
    "platform_updated": "Platform güncellendi",
    "platform_deleted": "Platform silindi",
    "platform_order_changed": "Platform sırası değiştirildi",
    "platform_exclusions_updated": "Platform hariç tutma ayarları güncellendi",
    "platform_logo_updated": "Platform logosu güncellendi",
    "users_updated": "Kullanıcı listesi güncellendi",
    "components_updated": "Bileşen listesi güncellendi",
    "tag_created": "Etiket oluşturuldu",
    "tag_updated": "Etiket güncellendi",
    "tag_deleted": "Etiket silindi",
    "tag_snapshot_updated": "Etiket görünümü güncellendi",
    "sql_query_executed": "Veri değiştiren SQL sorgusu çalıştırıldı",
    "database_backup_created": "Veritabanı yedeği oluşturuldu",
    "database_optimized": "Veritabanı optimize edildi",
    "database_vacuumed": "Veritabanı bakımı tamamlandı",
}

_ENTITY_LABELS = {
    "contract": "Sözleşme",
    "system": "Sistem",
    "delivery": "Teslimat",
    "document": "Belge",
    "folder": "Klasör",
    "platform": "Platform",
    "user": "Kullanıcı",
    "component": "Bileşen",
    "tag": "Etiket",
    "database": "Veritabanı",
}

# These keys stay hidden even for technical users. The Phase 1 sanitizer remains
# the final defense, while this set also removes legacy raw SQL fields.
_ALWAYS_HIDDEN_KEYS = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "password_hash",
        "admin_password_hash",
        "invite_code",
        "invite_code_hash",
        "authorization_code",
        "access_token",
        "refresh_token",
        "private_key",
        "content_blob",
        "raw_sql",
        "sql_literal",
        "sql_text",
        "query_preview",
    }
)


def _clamp_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_QUERY_LIMIT
    return max(1, min(MAX_QUERY_LIMIT, parsed))


def _normalize_iso(value: str | None, *, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ActivityHistoryQueryError(f"Geçersiz {field} değeri.") from exc
    return text


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _b64encode_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode_json(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text or len(text) > 2048:
        raise ActivityHistoryQueryError("Geçersiz sayfalama imleci.")
    try:
        padded = text + "=" * (-len(text) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ActivityHistoryQueryError("Geçersiz sayfalama imleci.") from exc
    if not isinstance(data, dict):
        raise ActivityHistoryQueryError("Geçersiz sayfalama imleci.")
    return data


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _operation_group_key(operation_id: str | None) -> str | None:
    text = str(operation_id or "").strip()
    if not text:
        return None
    return "op_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _action_label(action: str) -> str:
    if action in _ACTION_LABELS:
        return _ACTION_LABELS[action]
    words = [part for part in action.replace("-", "_").split("_") if part]
    return " ".join(words).capitalize() if words else "Bilinmeyen işlem"


def activity_action_label(action: str) -> str:
    """Public, UI-safe label resolver for canonical and legacy actions."""
    return _action_label(canonical_activity_action(action))


def _deep_hide_forbidden(value: Any) -> Any:
    sanitized = sanitize_activity_value(value)
    if isinstance(sanitized, dict):
        out: dict[str, Any] = {}
        for key, item in sanitized.items():
            if str(key).strip().casefold() in _ALWAYS_HIDDEN_KEYS:
                continue
            out[str(key)] = _deep_hide_forbidden(item)
        return out
    if isinstance(sanitized, list):
        return [_deep_hide_forbidden(item) for item in sanitized]
    return sanitized


def _parse_json(value: Any) -> tuple[Any, bool]:
    if value in (None, "", "null"):
        return None, False
    try:
        parsed = json.loads(str(value))
    except Exception:
        return None, True
    return _deep_hide_forbidden(parsed), False


def _parse_changed_fields(value: Any) -> tuple[tuple[ActivityFieldChange, ...], bool]:
    parsed, failed = _parse_json(value)
    if failed:
        return (), True
    if not isinstance(parsed, list):
        return (), bool(parsed is not None)
    changes: list[ActivityFieldChange] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        field = normalize_activity_text(item.get("field"), max_length=256)
        if not field or field.casefold() in _ALWAYS_HIDDEN_KEYS:
            continue
        changes.append(
            ActivityFieldChange(
                field=field,
                before=_deep_hide_forbidden(item.get("before")),
                after=_deep_hide_forbidden(item.get("after")),
            )
        )
    return tuple(changes), False


def _canonical_db_actions(actions: Iterable[str]) -> tuple[str, ...]:
    canonical = {canonical_activity_action(action) for action in actions if canonical_activity_action(action)}
    accepted = set(canonical)
    for alias, target in ACTION_ALIASES.items():
        if target in canonical:
            accepted.add(alias)
    return tuple(sorted(accepted))


class ActivityHistoryQueryService:
    """Read-only, policy-scoped activity query and projection service."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection
        self._conn.row_factory = sqlite3.Row

    def query(
        self,
        query: ActivityHistoryQuery,
        *,
        access: ActivityHistoryAccess,
        include_technical: bool = False,
    ) -> ActivityHistoryPage:
        if not access.can_view:
            return ActivityHistoryPage(items=(), next_cursor=None, has_more=False)

        requested_categories = {
            normalized
            for value in query.categories
            if (normalized := normalize_activity_category(value)) is not None
        }
        allowed_categories = set(access.allowed_categories) & set(ALLOWED_CATEGORIES)
        scope = allowed_categories if not requested_categories else allowed_categories & requested_categories
        if not scope:
            return ActivityHistoryPage(items=(), next_cursor=None, has_more=False)

        if (query.platform_id is not None or query.contract_id is not None) and not access.can_view_internal_ids:
            raise ActivityHistoryQueryError("İç kimlik filtreleri için teknik erişim gereklidir.")
        if query.operation_id and not access.can_view_technical:
            raise ActivityHistoryQueryError("Tam işlem kimliği filtresi için teknik erişim gereklidir.")

        limit = _clamp_limit(query.limit)
        from_utc = _normalize_iso(query.occurred_from_utc, field="başlangıç zamanı")
        to_utc = _normalize_iso(query.occurred_to_utc, field="bitiş zamanı")
        actions = _canonical_db_actions(query.actions)
        normalized_contract_no = normalize_activity_text(query.contract_no, max_length=512)
        normalized_platform_text = normalize_activity_text(query.platform_text, max_length=512)
        normalized_operation_id = normalize_activity_text(query.operation_id, max_length=512)
        actor_text = normalize_activity_text(query.actor_text, max_length=512)
        search_text = normalize_activity_text(query.search_text, max_length=2048)

        fp_payload = {
            "v": _CURSOR_VERSION,
            "categories": sorted(scope),
            "actions": list(actions),
            "actor_text": actor_text,
            "search_text": search_text,
            "platform_id": safe_positive_int(query.platform_id),
            "platform_text": normalized_platform_text,
            "contract_id": safe_positive_int(query.contract_id),
            "contract_no": normalized_contract_no,
            "operation_id": normalized_operation_id,
            "from": from_utc,
            "to": to_utc,
        }
        fingerprint = _fingerprint(fp_payload)
        cursor_time: str | None = None
        cursor_id: int | None = None
        if query.cursor:
            cursor_data = _b64decode_json(query.cursor)
            if cursor_data.get("v") != _CURSOR_VERSION or cursor_data.get("fp") != fingerprint:
                raise ActivityHistoryQueryError("Sayfalama imleci bu filtrelerle uyumlu değil.")
            cursor_time = normalize_activity_text(cursor_data.get("t"), max_length=128)
            cursor_id = safe_positive_int(cursor_data.get("id"))
            if not cursor_time or cursor_id is None:
                raise ActivityHistoryQueryError("Geçersiz sayfalama imleci.")

        items: list[ActivityHistoryItem] = []
        scan_time, scan_id = cursor_time, cursor_id
        exhausted = False
        while len(items) < limit + 1 and not exhausted:
            rows = self._fetch_rows(
                categories=scope,
                actions=actions,
                actor_text=actor_text,
                search_text=search_text,
                platform_id=safe_positive_int(query.platform_id),
                platform_text=normalized_platform_text,
                contract_id=safe_positive_int(query.contract_id),
                contract_no=normalized_contract_no,
                operation_id=normalized_operation_id,
                from_utc=from_utc,
                to_utc=to_utc,
                cursor_time=scan_time,
                cursor_id=scan_id,
                fetch_limit=max(100, min(1000, (limit + 1) * 4)),
                ascending=False,
            )
            if not rows:
                exhausted = True
                break
            for row in rows:
                item = self._project_row(row, access=access, include_technical=include_technical)
                if item is not None and item.category in scope:
                    items.append(item)
                    if len(items) >= limit + 1:
                        break
            last = rows[-1]
            scan_time = str(last["effective_occurred_at"] or "")
            scan_id = int(last["id"])
            exhausted = len(rows) < max(100, min(1000, (limit + 1) * 4))

        has_more = len(items) > limit
        page_items = items[:limit]
        next_cursor = None
        if has_more and page_items:
            last_item = page_items[-1]
            next_cursor = _b64encode_json(
                {"v": _CURSOR_VERSION, "t": last_item.occurred_at, "id": last_item.id, "fp": fingerprint}
            )
        return ActivityHistoryPage(items=tuple(page_items), next_cursor=next_cursor, has_more=has_more)

    def get_operation_events(
        self,
        operation_id: str,
        *,
        access: ActivityHistoryAccess,
        limit: int = MAX_QUERY_LIMIT,
    ) -> tuple[ActivityHistoryItem, ...]:
        if not access.can_view:
            return ()
        operation = normalize_activity_text(operation_id, max_length=512)
        if not operation:
            return ()
        capped = _clamp_limit(limit)
        rows = self._fetch_rows(
            categories=set(access.allowed_categories),
            actions=(),
            actor_text="",
            search_text="",
            platform_id=None,
            platform_text="",
            contract_id=None,
            contract_no="",
            operation_id=operation,
            from_utc=None,
            to_utc=None,
            cursor_time=None,
            cursor_id=None,
            fetch_limit=min(1000, max(capped * 4, 200)),
            ascending=True,
        )
        items: list[ActivityHistoryItem] = []
        for row in rows:
            item = self._project_row(row, access=access, include_technical=access.can_view_technical)
            if item is not None and item.category in access.allowed_categories:
                items.append(item)
                if len(items) >= capped:
                    break
        return tuple(items)

    def get_operation_events_by_group_key(
        self,
        operation_group_key: str,
        *,
        access: ActivityHistoryAccess,
        limit: int = MAX_QUERY_LIMIT,
    ) -> tuple[ActivityHistoryItem, ...]:
        """Resolve an opaque group key without exposing the full operation id."""
        key = normalize_activity_text(operation_group_key, max_length=128)
        if not access.can_view or not key.startswith("op_") or len(key) != 15:
            return ()
        categories = tuple(sorted(set(access.allowed_categories) & set(ALLOWED_CATEGORIES)))
        if not categories:
            return ()
        placeholders = ",".join("?" for _ in categories)
        rows = self._conn.execute(
            f"SELECT DISTINCT operation_id FROM activity_logs "
            f"WHERE operation_id IS NOT NULL AND operation_id<>'' "
            f"AND (category IN ({placeholders}) OR category IS NULL OR category='') "
            "ORDER BY id DESC LIMIT 1000",
            list(categories),
        ).fetchall()
        for row in rows:
            operation_id = str(row[0] or "")
            if _operation_group_key(operation_id) == key:
                return self.get_operation_events(operation_id, access=access, limit=limit)
        return ()

    def _fetch_rows(
        self,
        *,
        categories: set[str],
        actions: Sequence[str],
        actor_text: str,
        search_text: str,
        platform_id: int | None,
        platform_text: str,
        contract_id: int | None,
        contract_no: str,
        operation_id: str,
        from_utc: str | None,
        to_utc: str | None,
        cursor_time: str | None,
        cursor_id: int | None,
        fetch_limit: int,
        ascending: bool,
    ) -> list[sqlite3.Row]:
        sql = (
            "SELECT l.*, p.name AS current_platform_name, "
            f"{_EFFECTIVE_TIME_SQL} AS effective_occurred_at "
            "FROM activity_logs l LEFT JOIN platforms p ON p.id=l.platform_id WHERE 1=1"
        )
        params: list[Any] = []
        normalized_categories = tuple(sorted(set(categories) & set(ALLOWED_CATEGORIES)))
        if normalized_categories:
            placeholders = ",".join("?" for _ in normalized_categories)
            sql += f" AND (l.category IN ({placeholders}) OR l.category IS NULL OR l.category='')"
            params.extend(normalized_categories)
        if actions:
            placeholders = ",".join("?" for _ in actions)
            sql += f" AND LOWER(l.action) IN ({placeholders})"
            params.extend(actions)
        if actor_text:
            sql += " AND COALESCE(NULLIF(l.actor_display_name,''),l.actor,'') LIKE ? ESCAPE '\\'"
            params.append(f"%{_escape_like(actor_text)}%")
        if search_text:
            like = f"%{_escape_like(search_text)}%"
            sql += (
                " AND (COALESCE(l.message,'') LIKE ? ESCAPE '\\' OR "
                "COALESCE(l.entity_key,'') LIKE ? ESCAPE '\\' OR "
                "COALESCE(NULLIF(l.actor_display_name,''),l.actor,'') LIKE ? ESCAPE '\\' OR "
                "COALESCE(l.action,'') LIKE ? ESCAPE '\\' OR "
                "COALESCE(NULLIF(l.platform_name_snapshot,''),p.name,'') LIKE ? ESCAPE '\\' OR "
                "COALESCE(NULLIF(l.contract_no_snapshot,''),l.contract_no,'') LIKE ? ESCAPE '\\')"
            )
            params.extend([like] * 6)
        if platform_id is not None:
            sql += " AND l.platform_id=?"
            params.append(platform_id)
        if platform_text:
            sql += " AND COALESCE(NULLIF(l.platform_name_snapshot,''),p.name,'') LIKE ? ESCAPE '\\'"
            params.append(f"%{_escape_like(platform_text)}%")
        if contract_id is not None:
            sql += " AND l.contract_id=?"
            params.append(contract_id)
        if contract_no:
            sql += " AND COALESCE(NULLIF(l.contract_no_snapshot,''),l.contract_no,'')=?"
            params.append(contract_no)
        if operation_id:
            sql += " AND l.operation_id=?"
            params.append(operation_id)
        if from_utc:
            sql += f" AND {_EFFECTIVE_TIME_SQL}>=?"
            params.append(from_utc)
        if to_utc:
            sql += f" AND {_EFFECTIVE_TIME_SQL}<=?"
            params.append(to_utc)
        if cursor_time is not None and cursor_id is not None:
            if ascending:
                sql += f" AND ({_EFFECTIVE_TIME_SQL}>? OR ({_EFFECTIVE_TIME_SQL}=? AND l.id>?))"
            else:
                sql += f" AND ({_EFFECTIVE_TIME_SQL}<? OR ({_EFFECTIVE_TIME_SQL}=? AND l.id<?))"
            params.extend([cursor_time, cursor_time, cursor_id])
        direction = "ASC" if ascending else "DESC"
        sql += f" ORDER BY {_EFFECTIVE_TIME_SQL} {direction}, l.id {direction} LIMIT ?"
        params.append(_clamp_limit(fetch_limit) if fetch_limit <= MAX_QUERY_LIMIT else min(1000, fetch_limit))
        return list(self._conn.execute(sql, params).fetchall())

    def _project_row(
        self,
        row: sqlite3.Row,
        *,
        access: ActivityHistoryAccess,
        include_technical: bool,
    ) -> ActivityHistoryItem | None:
        raw = dict(row)
        action = canonical_activity_action(raw.get("action"))
        category = normalize_activity_category(raw.get("category")) or infer_activity_category(action)
        if category is None or category not in access.allowed_categories:
            return None
        occurred_at = normalize_activity_text(
            raw.get("effective_occurred_at") or raw.get("occurred_at_utc") or raw.get("created_at"),
            max_length=128,
        )
        actor_name = normalize_activity_text(
            raw.get("actor_display_name") or raw.get("actor"), max_length=512
        ) or UNKNOWN_ACTOR
        entity_type = normalize_activity_text(raw.get("entity_type"), max_length=128) or None
        entity_label = _ENTITY_LABELS.get(str(entity_type or "").casefold())
        platform_name = normalize_activity_text(
            raw.get("platform_name_snapshot") or raw.get("current_platform_name"), max_length=512
        ) or None
        contract_no = normalize_activity_text(
            raw.get("contract_no_snapshot") or raw.get("contract_no"), max_length=512
        ) or None
        action_label = _action_label(action)
        message = normalize_activity_text(raw.get("message"), max_length=2048)
        summary = message or " — ".join(part for part in (action_label, entity_label, contract_no or platform_name) if part)
        changed_fields, changed_error = _parse_changed_fields(raw.get("changed_fields_json"))
        operation_id = normalize_activity_text(raw.get("operation_id"), max_length=512) or None

        technical: ActivityTechnicalDetails | None = None
        # Caller preference can only reduce output; it can never grant permission.
        if access.can_view_technical and access.can_view_internal_ids and access.can_view_raw_payloads and include_technical:
            before, _ = _parse_json(raw.get("before_json"))
            after, _ = _parse_json(raw.get("after_json"))
            payload, _ = _parse_json(raw.get("payload_json"))
            technical_payload, _ = _parse_json(raw.get("technical_payload_json"))
            technical = ActivityTechnicalDetails(
                source=normalize_activity_text(raw.get("source"), max_length=512) or None,
                device_name=normalize_activity_text(raw.get("device_name"), max_length=512) or None,
                actor_staff_id=safe_positive_int(raw.get("actor_staff_id")),
                actor_admin_id=safe_positive_int(raw.get("actor_admin_id")),
                session_id=normalize_activity_text(raw.get("session_id"), max_length=512) or None,
                entity_id=normalize_activity_text(raw.get("entity_id"), max_length=512) or None,
                contract_id=safe_positive_int(raw.get("contract_id")),
                platform_id=safe_positive_int(raw.get("platform_id")),
                before=before,
                after=after,
                payload=payload,
                technical_payload=technical_payload,
                event_schema_version=safe_positive_int(raw.get("event_schema_version")),
                operation_id=operation_id,
            )

        return ActivityHistoryItem(
            id=int(raw.get("id") or 0),
            occurred_at=occurred_at,
            category=category,
            action=action,
            action_label=action_label,
            status=normalize_activity_status(raw.get("status")),
            actor_display_name=actor_name,
            title=action_label,
            summary=summary or action_label,
            entity_type=entity_type,
            entity_label=entity_label,
            platform_name=platform_name,
            contract_no=contract_no,
            changed_fields=changed_fields,
            changed_fields_parse_error=changed_error,
            operation_group_key=_operation_group_key(operation_id),
            technical=technical,
        )


__all__ = [
    "ActivityFieldChange",
    "ActivityHistoryAccess",
    "ActivityHistoryItem",
    "ActivityHistoryPage",
    "ActivityHistoryQuery",
    "ActivityHistoryQueryError",
    "ActivityHistoryQueryService",
    "ActivityTechnicalDetails",
    "MAX_QUERY_LIMIT",
]
