from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.agenda.constants import AgendaPresentationProfileCode
from src.services.agenda_context_factory import (
    AgendaContextBuildError,
    PersonalAgendaContextFactory,
)


def _staff(**overrides):
    value = {
        "id": 7,
        "full_name": "Test Personel",
        "role": "personnel",
        "is_active": 1,
        "permissions": {"view_contracts", "export_data"},
    }
    value.update(overrides)
    return value


def test_missing_staff_and_invalid_id_are_rejected():
    factory = PersonalAgendaContextFactory()
    with pytest.raises(AgendaContextBuildError):
        factory.build(None)
    for invalid in (None, 0, -1, True, "x"):
        with pytest.raises(AgendaContextBuildError):
            factory.build(_staff(id=invalid))


def test_inactive_staff_is_rejected():
    with pytest.raises(AgendaContextBuildError):
        PersonalAgendaContextFactory().build(_staff(is_active=0))


def test_permissions_are_snapshotted_as_frozenset():
    permissions = {"view_contracts"}
    context = PersonalAgendaContextFactory().build(_staff(permissions=permissions))
    permissions.add("edit_contracts")
    assert context.permissions == frozenset({"view_contracts"})
    assert context.presentation_profile.permissions == frozenset({"view_contracts"})
    assert context.current_staff["permissions"] == frozenset({"view_contracts"})


def test_role_name_does_not_grant_permission():
    context = PersonalAgendaContextFactory().build(
        _staff(role="manager", role_name="manager", permissions=set())
    )
    assert "view_contracts" not in context.permissions


def test_personal_profile_is_stable():
    context = PersonalAgendaContextFactory().build(_staff())
    profile = context.presentation_profile
    assert profile.code == AgendaPresentationProfileCode.PERSONAL
    assert profile.display_name == "Kişisel kapsam"
    assert profile.description == "Sorumlu olduğunuz sözleşmelerde dikkat isteyen maddeler."


def test_provided_time_and_today_are_normalized_to_naive():
    aware = datetime(2026, 7, 11, 10, 30, tzinfo=timezone(timedelta(hours=3)))
    context = PersonalAgendaContextFactory().build(_staff(), now=aware)
    assert context.now == datetime(2026, 7, 11, 10, 30)
    assert context.now.tzinfo is None
    assert context.today.isoformat() == "2026-07-11"


def test_now_provider_is_used_when_now_is_not_given():
    fixed = datetime(2026, 7, 12, 8, 45)
    context = PersonalAgendaContextFactory(now_provider=lambda: fixed).build(_staff())
    assert context.now == fixed
    assert context.today == fixed.date()


def test_contract_ids_are_deduplicated_and_validated():
    context = PersonalAgendaContextFactory().build(
        _staff(),
        personal_contract_ids=[3, "2", 3, 1],
    )
    assert context.personal_contract_ids == frozenset({1, 2, 3})
    for invalid in ([0], [-1], [True], ["x"], "123"):
        with pytest.raises(AgendaContextBuildError):
            PersonalAgendaContextFactory().build(
                _staff(),
                personal_contract_ids=invalid,
            )


def test_sensitive_fields_are_removed_and_input_is_not_mutated():
    source = _staff(
        password_hash="hash",
        password="plain",
        password_salt="salt",
        secret="secret",
        token="token",
    )
    original = dict(source)
    context = PersonalAgendaContextFactory().build(source)
    assert source == original
    for field_name in ("password_hash", "password", "password_salt", "secret", "token"):
        assert field_name not in context.current_staff


def test_missing_permissions_can_use_real_enrichment_signature(monkeypatch):
    calls = []

    def fake_enrich(db_or_path, staff):
        calls.append((db_or_path, dict(staff)))
        enriched = dict(staff)
        enriched["permissions"] = {"view_contracts"}
        return enriched

    monkeypatch.setattr(
        "src.services.agenda_context_factory.auth.enrich_staff_permissions",
        fake_enrich,
    )
    context = PersonalAgendaContextFactory().build(
        _staff(permissions=None, db_path="sample.sts")
    )
    assert calls[0][0] == "sample.sts"
    assert context.permissions == frozenset({"view_contracts"})


def test_missing_permissions_without_db_path_remains_empty():
    context = PersonalAgendaContextFactory().build(_staff(permissions=None))
    assert context.permissions == frozenset()
