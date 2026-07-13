from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


_LOG = logging.getLogger(__name__)
ACTIVITY_EVENT_SCHEMA_VERSION = 1
ACTIVITY_SCHEMA_VERSION = 18
MAX_ACTIVITY_JSON_BYTES = 16 * 1024
MAX_STRING_LENGTH = 2048
MAX_COLLECTION_ITEMS = 100
REDACTED_VALUE = "[REDACTED]"
OMITTED_BINARY_VALUE = "[BINARY OMITTED]"
UNKNOWN_ACTOR = "Kimliği belirlenemedi"
CONSTRUCTOR_ACTIVITY_ACTIONS = frozenset({"database_opened", "database_created", "schema_migrated"})
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

_ACTIVITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("occurred_at_utc", "TEXT"),
    ("category", "TEXT"),
    ("status", "TEXT"),
    ("operation_id", "TEXT"),
    ("actor_type", "TEXT"),
    ("actor_staff_id", "INTEGER"),
    ("actor_admin_id", "INTEGER"),
    ("actor_display_name", "TEXT"),
    ("session_id", "TEXT"),
    ("contract_id", "INTEGER"),
    ("platform_name_snapshot", "TEXT"),
    ("contract_no_snapshot", "TEXT"),
    ("changed_fields_json", "TEXT"),
    ("technical_payload_json", "TEXT"),
    ("event_schema_version", "INTEGER DEFAULT 1"),
)

_ACTIVITY_INDEX_SQL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_occurred_id ON activity_logs(occurred_at_utc DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_category_occurred ON activity_logs(category, occurred_at_utc DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_actor_staff_occurred ON activity_logs(actor_staff_id, occurred_at_utc DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_operation_id ON activity_logs(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_action_occurred ON activity_logs(action, occurred_at_utc DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_entity_occurred ON activity_logs(entity_type, entity_id, occurred_at_utc DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_contract_occurred ON activity_logs(contract_id, occurred_at_utc DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_platform_occurred ON activity_logs(platform_id, occurred_at_utc DESC)",
)


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_sensitive_key(key: Any) -> bool:
    return str(key or "").strip().casefold() in SENSITIVE_KEYS


def _normalize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            return value[:MAX_STRING_LENGTH] + f"… [truncated {len(value) - MAX_STRING_LENGTH} chars]"
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return {"name": value.name, "path_redacted": True}
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
                out[key] = REDACTED_VALUE if _is_sensitive_key(key) else sanitize_activity_value(raw_value, _seen=seen)
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

    return {"_type": type(value).__name__, "value": str(value)[:MAX_STRING_LENGTH]}


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
    return json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_category(value: Any) -> str | None:
    category = _clean_text(value).upper()
    return category if category in ALLOWED_CATEGORIES else None


def _patch_schema(sts_database_module: Any, database_cls: type) -> None:
    if getattr(database_cls, "_activity_schema_patch_installed", False):
        return

    original_init_schema = database_cls.init_schema

    def init_schema(self):
        migrated = list(original_init_schema(self) or [])
        for name, ddl in _ACTIVITY_COLUMNS:
            if self._ensure_column("activity_logs", name, ddl):
                migrated.append(f"activity_logs.{name}")
        for sql in _ACTIVITY_INDEX_SQL:
            self.conn.execute(sql)
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
            (str(ACTIVITY_SCHEMA_VERSION),),
        )
        self.conn.commit()
        return migrated

    original_backup_path = sts_database_module.make_migration_backup_path

    def make_migration_backup_path(path, from_version, to_version=None):
        target_version = ACTIVITY_SCHEMA_VERSION if to_version is None else int(to_version)
        return original_backup_path(path, from_version, target_version)

    database_cls.init_schema = init_schema
    database_cls._activity_schema_patch_installed = True
    sts_database_module.make_migration_backup_path = make_migration_backup_path
    sts_database_module.CURRENT_SCHEMA_VERSION = ACTIVITY_SCHEMA_VERSION


def _patch_constructor(database_cls: type) -> None:
    if getattr(database_cls, "_activity_constructor_patch_installed", False):
        return

    original_init = database_cls.__init__

    def __init__(self, *args, **kwargs):
        self._activity_tx_depth = 0
        self._activity_savepoint_counter = 0
        self._suppress_constructor_activity = True
        try:
            original_init(self, *args, **kwargs)
        finally:
            self._suppress_constructor_activity = False
        _LOG.info(
            "STS database initialized file=%s migrated=%s source=%s",
            getattr(getattr(self, "path", None), "name", ""),
            bool(getattr(self, "migration_performed", False)),
            getattr(self, "source", ""),
        )

    database_cls.__init__ = __init__
    database_cls._activity_constructor_patch_installed = True


def _patch_transactions(database_cls: type) -> None:
    if getattr(database_cls, "_activity_tx_patch_installed", False):
        return

    @contextmanager
    def tx(self):
        owns_transaction = not self.conn.in_transaction
        savepoint = None
        self._activity_tx_depth = int(getattr(self, "_activity_tx_depth", 0)) + 1
        try:
            if owns_transaction:
                self.conn.execute("BEGIN")
            else:
                self._activity_savepoint_counter = int(getattr(self, "_activity_savepoint_counter", 0)) + 1
                savepoint = f"_activity_tx_{id(self):x}_{self._activity_savepoint_counter}"
                self.conn.execute(f"SAVEPOINT {savepoint}")
            yield
            if savepoint:
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            elif owns_transaction:
                self.conn.commit()
        except Exception:
            if savepoint:
                try:
                    self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                finally:
                    self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            elif owns_transaction:
                self.conn.rollback()
            raise
        finally:
            self._activity_tx_depth = max(0, int(getattr(self, "_activity_tx_depth", 1)) - 1)

    database_cls.tx = tx
    database_cls._activity_tx_patch_installed = True


def _patch_add_log(database_cls: type) -> None:
    if getattr(database_cls, "_activity_add_log_patch_installed", False):
        return

    def add_log(
        self,
        action: str,
        entity_type: str = "",
        entity_key: str = "",
        message: str = "",
        payload: dict | None = None,
        actor: str | None = None,
        source: str | None = None,
        device: str | None = None,
        entity_id: str | int | None = None,
        platform: str | None = None,
        contract_no: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
        *,
        category: str | None = None,
        status: str | None = "SUCCESS",
        operation_id: str | None = None,
        actor_type: str | None = None,
        actor_staff_id: int | None = None,
        actor_admin_id: int | None = None,
        actor_display_name: str | None = None,
        session_id: str | None = None,
        contract_id: int | None = None,
        platform_name_snapshot: str | None = None,
        contract_no_snapshot: str | None = None,
        changed_fields: Any = None,
        technical_payload: Any = None,
        event_schema_version: int = ACTIVITY_EVENT_SCHEMA_VERSION,
        strict: bool | None = None,
    ) -> int | None:
        action_text = _clean_text(action)
        if bool(getattr(self, "_suppress_constructor_activity", False)) and action_text in CONSTRUCTOR_ACTIVITY_ACTIONS:
            _LOG.debug("Suppressed constructor activity event action=%s", action_text)
            return None

        transaction_active = bool(self.conn.in_transaction or int(getattr(self, "_activity_tx_depth", 0)) > 0)
        effective_strict = transaction_active if strict is None else bool(strict)
        actor_name = _clean_text(actor_display_name or actor) or UNKNOWN_ACTOR
        legacy_created_at = self.__class__._activity_now_iso()
        occurred_at = utc_now_iso()
        platform_text = _clean_text(platform_name_snapshot or platform)
        contract_text = _clean_text(contract_no_snapshot or contract_no)

        try:
            cur = self.conn.execute(
                """
                INSERT INTO activity_logs(
                    created_at,actor,source,device_name,action,entity_type,entity_id,entity_key,
                    platform_id,contract_no,message,before_json,after_json,payload_json,
                    occurred_at_utc,category,status,operation_id,actor_type,actor_staff_id,
                    actor_admin_id,actor_display_name,session_id,contract_id,
                    platform_name_snapshot,contract_no_snapshot,changed_fields_json,
                    technical_payload_json,event_schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    legacy_created_at,
                    actor_name,
                    _clean_text(source) or _clean_text(getattr(self, "source", "")) or "Main UI",
                    _clean_text(device) or self.__class__._activity_device_name(),
                    action_text,
                    _clean_text(entity_type),
                    "" if entity_id is None else str(entity_id),
                    _clean_text(entity_key),
                    self._platform_id(platform_text),
                    contract_text,
                    _clean_text(message),
                    activity_json(before),
                    activity_json(after),
                    activity_json(payload),
                    occurred_at,
                    _normalized_category(category),
                    _clean_text(status).upper() or "SUCCESS",
                    _clean_text(operation_id) or None,
                    _clean_text(actor_type) or None,
                    _safe_int(actor_staff_id),
                    _safe_int(actor_admin_id),
                    actor_name,
                    _clean_text(session_id) or None,
                    _safe_int(contract_id),
                    platform_text or None,
                    contract_text or None,
                    activity_json(changed_fields),
                    activity_json(technical_payload),
                    int(event_schema_version or ACTIVITY_EVENT_SCHEMA_VERSION),
                ),
            )
            event_id = int(cur.lastrowid)
            if not transaction_active:
                self.conn.commit()
            return event_id
        except Exception:
            _LOG.exception(
                "Activity event insert failed action=%s source=%s transaction_active=%s",
                action_text,
                source or getattr(self, "source", ""),
                transaction_active,
            )
            if not transaction_active:
                try:
                    self.conn.rollback()
                except Exception:
                    _LOG.exception("Activity event rollback failed")
            if effective_strict:
                raise
            return None

    database_cls.add_log = add_log
    database_cls._activity_add_log_patch_installed = True


def _patch_list_logs(database_cls: type) -> None:
    if getattr(database_cls, "_activity_list_patch_installed", False):
        return

    def list_logs(
        self,
        limit: int = 500,
        action: str | None = None,
        entity_type: str | None = None,
        platform: str | None = None,
        contract_no: str | None = None,
        search: str | None = None,
        category: str | None = None,
        operation_id: str | None = None,
    ):
        q = "SELECT l.*, p.name AS platform FROM activity_logs l LEFT JOIN platforms p ON p.id=l.platform_id WHERE 1=1"
        params: list[Any] = []
        if action:
            q += " AND l.action=?"
            params.append(action)
        if entity_type:
            q += " AND l.entity_type=?"
            params.append(entity_type)
        if platform:
            q += " AND (p.name=? OR l.platform_name_snapshot=?)"
            params.extend([platform, platform])
        if contract_no:
            q += " AND COALESCE(NULLIF(l.contract_no_snapshot,''),l.contract_no)=?"
            params.append(contract_no)
        if category:
            q += " AND l.category=?"
            params.append(_normalized_category(category))
        if operation_id:
            q += " AND l.operation_id=?"
            params.append(operation_id)
        if search:
            q += (
                " AND (l.message LIKE ? OR l.entity_key LIKE ? OR "
                "COALESCE(NULLIF(l.actor_display_name,''),l.actor) LIKE ? OR l.source LIKE ? OR "
                "l.device_name LIKE ? OR l.action LIKE ? OR "
                "COALESCE(p.name,l.platform_name_snapshot,'') LIKE ? OR "
                "COALESCE(NULLIF(l.contract_no_snapshot,''),l.contract_no) LIKE ?)"
            )
            value = f"%{search}%"
            params.extend([value] * 8)
        q += " ORDER BY COALESCE(NULLIF(l.occurred_at_utc,''),l.created_at) DESC, l.id DESC"
        if limit and int(limit) > 0:
            q += " LIMIT ?"
            params.append(int(limit))
        return [dict(row) for row in self.conn.execute(q, params).fetchall()]

    database_cls.list_logs = list_logs
    database_cls._activity_list_patch_installed = True


def _patch_store(store_cls: type) -> None:
    if getattr(store_cls, "_activity_store_patch_installed", False):
        return

    def _log(self, action: str, **kwargs):
        explicit_actor = _clean_text(kwargs.get("actor"))
        current_actor = ""
        if not explicit_actor:
            try:
                current_actor = _clean_text(self.current_actor())
            except Exception:
                _LOG.exception("STSStore.current_actor failed while preparing activity event")
        actor_name = explicit_actor or current_actor
        if not explicit_actor and actor_name.casefold() == "kullanıcı":
            actor_name = ""
        actor_name = actor_name or UNKNOWN_ACTOR
        kwargs["actor"] = actor_name
        kwargs.setdefault("actor_display_name", actor_name)
        return self.db.add_log(action=action, **kwargs)

    original_list_logs = store_cls.list_logs

    def list_logs(self, *args, **kwargs):
        return self.db.list_logs(*args, **kwargs)

    store_cls._log = _log
    store_cls.list_logs = list_logs
    store_cls._activity_original_list_logs = original_list_logs
    store_cls._activity_store_patch_installed = True


def install_activity_history_infrastructure(sts_database_module: Any, store_cls: type) -> None:
    """Install the Phase 1 infrastructure once, before any STSDatabase instance exists."""
    database_cls = sts_database_module.STSDatabase
    sts_database_module.CURRENT_SCHEMA_VERSION = ACTIVITY_SCHEMA_VERSION
    database_cls._activity_now_iso = staticmethod(sts_database_module.now_iso)
    database_cls._activity_device_name = staticmethod(sts_database_module.device_name)
    _patch_schema(sts_database_module, database_cls)
    _patch_transactions(database_cls)
    _patch_add_log(database_cls)
    _patch_list_logs(database_cls)
    _patch_constructor(database_cls)
    _patch_store(store_cls)
