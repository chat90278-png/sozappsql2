from __future__ import annotations

from datetime import datetime
from typing import Sequence

from src.domain.agenda.models import AgendaItemState
from src.services.sts_database import STSDatabase, now_iso


_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _normalize_staff_id(value: object) -> int:
    try:
        staff_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("staff_id geçerli bir pozitif tamsayı olmalıdır.") from exc
    if staff_id <= 0:
        raise ValueError("staff_id geçerli bir pozitif tamsayı olmalıdır.")
    return staff_id


def _normalize_agenda_key(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("agenda_key boş olamaz.")
    return normalized


def _normalize_keys(values: Sequence[str]) -> list[str]:
    raw_values = (values,) if isinstance(values, str) else values
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        key = _normalize_agenda_key(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _normalize_optional_now(value: datetime | str | None) -> str:
    if value is None:
        return now_iso()
    if isinstance(value, datetime):
        return value.strftime(_TIMESTAMP_FORMAT)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or now_iso()
    raise TypeError("Zaman değeri datetime, str veya None olmalıdır.")


def _normalize_required_until(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.strftime(_TIMESTAMP_FORMAT)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
        raise ValueError("until boş olamaz.")
    raise TypeError("until datetime veya str olmalıdır.")


def _normalize_snapshot(value: object) -> str:
    return str(value or "").strip()


def _normalize_required_snapshot(value: object, field_name: str) -> str:
    normalized = _normalize_snapshot(value)
    if not normalized:
        raise ValueError(f"{field_name} boş olamaz.")
    return normalized


def _row_to_state(row) -> AgendaItemState:
    return AgendaItemState(
        staff_id=int(row["staff_id"]),
        agenda_key=str(row["agenda_key"] or ""),
        first_presented_at=row["first_presented_at"],
        last_presented_at=row["last_presented_at"],
        seen_at=row["seen_at"],
        seen_version=str(row["seen_version"] or ""),
        snoozed_until=row["snoozed_until"],
        snoozed_version=str(row["snoozed_version"] or ""),
        snoozed_severity=str(row["snoozed_severity"] or ""),
        dismissed_at=row["dismissed_at"],
        dismissed_version=str(row["dismissed_version"] or ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AgendaStateRepository:
    def __init__(self, db: STSDatabase):
        self.db = db
        self.conn = db.conn

    def _get_state(self, staff_id: int, agenda_key: str) -> AgendaItemState | None:
        row = self.conn.execute(
            "SELECT * FROM staff_agenda_state WHERE staff_id=? AND agenda_key=?",
            (staff_id, agenda_key),
        ).fetchone()
        return _row_to_state(row) if row is not None else None

    def get_states(
        self,
        staff_id: int,
        agenda_keys: Sequence[str],
    ) -> dict[str, AgendaItemState]:
        normalized_staff_id = _normalize_staff_id(staff_id)
        keys = _normalize_keys(agenda_keys)
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        rows = self.conn.execute(
            f"SELECT * FROM staff_agenda_state WHERE staff_id=? AND agenda_key IN ({placeholders})",
            [normalized_staff_id, *keys],
        ).fetchall()
        return {str(row["agenda_key"]): _row_to_state(row) for row in rows}

    def mark_seen(
        self,
        staff_id: int,
        agenda_key: str,
        version: str,
        seen_at: datetime | str | None = None,
    ) -> AgendaItemState:
        normalized_staff_id = _normalize_staff_id(staff_id)
        key = _normalize_agenda_key(agenda_key)
        normalized_version = _normalize_snapshot(version)
        timestamp = _normalize_optional_now(seen_at)
        with self.db.tx():
            self.conn.execute(
                """
                INSERT INTO staff_agenda_state(
                    staff_id,agenda_key,seen_at,seen_version,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(staff_id,agenda_key) DO UPDATE SET
                    seen_at=excluded.seen_at,
                    seen_version=excluded.seen_version,
                    updated_at=excluded.updated_at
                """,
                (normalized_staff_id, key, timestamp, normalized_version, timestamp, timestamp),
            )
            state = self._get_state(normalized_staff_id, key)
        if state is None:
            raise RuntimeError("Agenda state kaydedilemedi.")
        return state

    def snooze(
        self,
        staff_id: int,
        agenda_key: str,
        version: str,
        severity: str,
        until: datetime | str,
    ) -> AgendaItemState:
        normalized_staff_id = _normalize_staff_id(staff_id)
        key = _normalize_agenda_key(agenda_key)
        normalized_version = _normalize_snapshot(version)
        normalized_severity = _normalize_required_snapshot(severity, "severity")
        snoozed_until = _normalize_required_until(until)
        timestamp = now_iso()
        with self.db.tx():
            self.conn.execute(
                """
                INSERT INTO staff_agenda_state(
                    staff_id,agenda_key,snoozed_until,snoozed_version,snoozed_severity,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(staff_id,agenda_key) DO UPDATE SET
                    snoozed_until=excluded.snoozed_until,
                    snoozed_version=excluded.snoozed_version,
                    snoozed_severity=excluded.snoozed_severity,
                    updated_at=excluded.updated_at
                """,
                (
                    normalized_staff_id,
                    key,
                    snoozed_until,
                    normalized_version,
                    normalized_severity,
                    timestamp,
                    timestamp,
                ),
            )
            state = self._get_state(normalized_staff_id, key)
        if state is None:
            raise RuntimeError("Agenda state kaydedilemedi.")
        return state

    def clear_snooze(
        self,
        staff_id: int,
        agenda_key: str,
    ) -> AgendaItemState | None:
        normalized_staff_id = _normalize_staff_id(staff_id)
        key = _normalize_agenda_key(agenda_key)
        timestamp = now_iso()
        with self.db.tx():
            cursor = self.conn.execute(
                """
                UPDATE staff_agenda_state
                SET snoozed_until=NULL,
                    snoozed_version='',
                    snoozed_severity='',
                    updated_at=?
                WHERE staff_id=? AND agenda_key=?
                """,
                (timestamp, normalized_staff_id, key),
            )
            if cursor.rowcount == 0:
                return None
            return self._get_state(normalized_staff_id, key)

    def dismiss_event(
        self,
        staff_id: int,
        agenda_key: str,
        version: str,
        dismissed_at: datetime | str | None = None,
    ) -> AgendaItemState:
        normalized_staff_id = _normalize_staff_id(staff_id)
        key = _normalize_agenda_key(agenda_key)
        normalized_version = _normalize_snapshot(version)
        timestamp = _normalize_optional_now(dismissed_at)
        with self.db.tx():
            self.conn.execute(
                """
                INSERT INTO staff_agenda_state(
                    staff_id,agenda_key,dismissed_at,dismissed_version,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(staff_id,agenda_key) DO UPDATE SET
                    dismissed_at=excluded.dismissed_at,
                    dismissed_version=excluded.dismissed_version,
                    updated_at=excluded.updated_at
                """,
                (normalized_staff_id, key, timestamp, normalized_version, timestamp, timestamp),
            )
            state = self._get_state(normalized_staff_id, key)
        if state is None:
            raise RuntimeError("Agenda state kaydedilemedi.")
        return state

    def touch_presented(
        self,
        staff_id: int,
        agenda_keys: Sequence[str],
        presented_at: datetime | str | None = None,
    ) -> None:
        normalized_staff_id = _normalize_staff_id(staff_id)
        keys = _normalize_keys(agenda_keys)
        if not keys:
            return
        timestamp = _normalize_optional_now(presented_at)
        rows = [
            (normalized_staff_id, key, timestamp, timestamp, timestamp, timestamp)
            for key in keys
        ]
        with self.db.tx():
            self.conn.executemany(
                """
                INSERT INTO staff_agenda_state(
                    staff_id,agenda_key,first_presented_at,last_presented_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(staff_id,agenda_key) DO UPDATE SET
                    first_presented_at=COALESCE(
                        staff_agenda_state.first_presented_at,
                        excluded.first_presented_at
                    ),
                    last_presented_at=excluded.last_presented_at,
                    updated_at=excluded.updated_at
                """,
                rows,
            )
