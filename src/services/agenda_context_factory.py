from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from typing import Any

from src import auth
from src.domain.agenda.constants import AgendaPresentationProfileCode
from src.domain.agenda.models import AgendaContext, AgendaPresentationProfile


_SENSITIVE_STAFF_FIELDS = {
    "password_hash",
    "password",
    "password_salt",
    "secret",
    "token",
}


class AgendaContextBuildError(ValueError):
    pass


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise AgendaContextBuildError(f"{field_name} must be a positive integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise AgendaContextBuildError(f"{field_name} must be a positive integer.") from exc
    if normalized <= 0:
        raise AgendaContextBuildError(f"{field_name} must be a positive integer.")
    return normalized


def _normalize_now(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise AgendaContextBuildError("now must be a datetime value.")
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.replace(tzinfo=None)
    return value


def _permission_snapshot(raw: object) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        values = (raw,)
    else:
        try:
            values = tuple(raw)  # type: ignore[arg-type]
        except TypeError as exc:
            raise AgendaContextBuildError("permissions must be a collection of permission codes.") from exc
    return frozenset(str(code).strip() for code in values if str(code).strip())


def _contract_id_snapshot(values: Collection[int]) -> frozenset[int]:
    if isinstance(values, (str, bytes, bytearray)) or isinstance(values, Mapping):
        raise AgendaContextBuildError("personal_contract_ids must be a collection of positive integers.")
    result: set[int] = set()
    for value in values:
        result.add(_positive_int(value, "personal_contract_id"))
    return frozenset(result)


class PersonalAgendaContextFactory:
    def __init__(self, *, now_provider: Callable[[], datetime] | None = None):
        self.now_provider = now_provider

    def build(
        self,
        current_staff: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
        personal_contract_ids: Collection[int] = (),
    ) -> AgendaContext:
        if current_staff is None:
            raise AgendaContextBuildError("current_staff is required.")
        if not isinstance(current_staff, Mapping):
            raise AgendaContextBuildError("current_staff must be a mapping.")

        original_snapshot = dict(current_staff)
        staff_id = _positive_int(original_snapshot.get("id"), "current_staff.id")
        try:
            is_active = int(original_snapshot.get("is_active", 1))
        except (TypeError, ValueError) as exc:
            raise AgendaContextBuildError("current_staff.is_active is invalid.") from exc
        if is_active == 0:
            raise AgendaContextBuildError("Inactive staff cannot build an agenda context.")

        enriched_snapshot = dict(original_snapshot)
        if enriched_snapshot.get("permissions") is None:
            db_or_path = enriched_snapshot.get("db_path") or enriched_snapshot.get("_db_path")
            if db_or_path is not None:
                enriched = auth.enrich_staff_permissions(db_or_path, enriched_snapshot)
                if enriched:
                    enriched_snapshot = dict(enriched)

        permissions = _permission_snapshot(enriched_snapshot.get("permissions"))
        safe_staff_snapshot = {
            str(key): value
            for key, value in enriched_snapshot.items()
            if str(key).casefold() not in _SENSITIVE_STAFF_FIELDS
        }
        safe_staff_snapshot["id"] = staff_id
        safe_staff_snapshot["is_active"] = is_active
        safe_staff_snapshot["permissions"] = permissions

        effective_now = now
        if effective_now is None and self.now_provider is not None:
            effective_now = self.now_provider()
        if effective_now is None:
            effective_now = datetime.now()
        normalized_now = _normalize_now(effective_now)

        profile = AgendaPresentationProfile(
            code=AgendaPresentationProfileCode.PERSONAL,
            display_name="Kişisel kapsam",
            description="Sorumlu olduğunuz sözleşmelerde dikkat isteyen maddeler.",
            permissions=permissions,
        )

        return AgendaContext(
            now=normalized_now,
            today=normalized_now.date(),
            presentation_profile=profile,
            current_staff=safe_staff_snapshot,
            staff_id=staff_id,
            permissions=permissions,
            personal_contract_ids=_contract_id_snapshot(personal_contract_ids),
        )
