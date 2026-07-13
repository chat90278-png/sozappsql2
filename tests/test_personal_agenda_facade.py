from __future__ import annotations

import inspect
import sqlite3
from datetime import datetime, timedelta

import pytest

from src import auth
from src.domain.agenda.constants import (
    AgendaLifecycleType,
    AgendaPresentationProfileCode,
    AgendaSeverity,
)
from src.domain.agenda.models import AgendaItem, AgendaItemState, AgendaResult
from src.services.agenda_context_factory import PersonalAgendaContextFactory
from src.services.personal_agenda_facade import (
    AgendaInteractionError,
    PersonalAgendaFacade,
    snooze_until_for_preset,
)


class _FakeDB:
    def __init__(self):
        self.conn = object()


class _FakeStateRepository:
    def __init__(self):
        self.mark_seen_calls = []
        self.snooze_calls = []
        self.clear_calls = []
        self.get_calls = []
        self.persisted = {}
        self.mark_seen_returns_none = False

    def mark_seen(self, staff_id, agenda_key, version, seen_at=None):
        self.mark_seen_calls.append((staff_id, agenda_key, version, seen_at))
        state = AgendaItemState(
            staff_id=staff_id,
            agenda_key=agenda_key,
            seen_at="2026-07-11 10:00:00",
            seen_version=version,
        )
        self.persisted[agenda_key] = state
        return None if self.mark_seen_returns_none else state

    def get_states(self, staff_id, agenda_keys):
        self.get_calls.append((staff_id, tuple(agenda_keys)))
        return {
            key: self.persisted[key]
            for key in agenda_keys
            if key in self.persisted and self.persisted[key].staff_id == staff_id
        }

    def snooze(self, staff_id, agenda_key, version, severity, until):
        self.snooze_calls.append((staff_id, agenda_key, version, severity, until))
        state = AgendaItemState(
            staff_id=staff_id,
            agenda_key=agenda_key,
            snoozed_until=until.strftime("%Y-%m-%d %H:%M:%S"),
            snoozed_version=version,
            snoozed_severity=severity,
        )
        self.persisted[agenda_key] = state
        return state

    def clear_snooze(self, staff_id, agenda_key):
        self.clear_calls.append((staff_id, agenda_key))
        state = self.persisted.get(agenda_key)
        if state is None or state.staff_id != staff_id:
            return None
        cleared = AgendaItemState(
            staff_id=state.staff_id,
            agenda_key=state.agenda_key,
            first_presented_at=state.first_presented_at,
            last_presented_at=state.last_presented_at,
            seen_at=state.seen_at,
            seen_version=state.seen_version,
            dismissed_at=state.dismissed_at,
            dismissed_version=state.dismissed_version,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )
        self.persisted[agenda_key] = cleared
        return cleared


class _FakeAgendaService:
    def __init__(self, state_repository, items=()):
        self.state_repository = state_repository
        self.items = tuple(items)
        self.calls = []

    def build(self, context, *, touch_presented=True):
        self.calls.append((context, touch_presented))
        return AgendaResult(
            profile=context.presentation_profile,
            items=self.items,
            new_count=len(self.items),
            active_count=len(self.items),
            counts_by_kind={"test": len(self.items)},
            new_keys=frozenset(item.key for item in self.items),
            states_by_key={},
        )


class _PermissionAwareAgendaService(_FakeAgendaService):
    def build(self, context, *, touch_presented=True):
        self.calls.append((context, touch_presented))
        items = self.items if "view_contracts" in context.permissions else ()
        return AgendaResult(
            profile=context.presentation_profile,
            items=items,
            new_count=len(items),
            active_count=len(items),
            counts_by_kind={"test": len(items)} if items else {},
            new_keys=frozenset(item.key for item in items),
            states_by_key={},
        )


class _StateAwareAgendaService(_PermissionAwareAgendaService):
    def build(self, context, *, touch_presented=True):
        self.calls.append((context, touch_presented))
        items = self.items if "view_contracts" in context.permissions else ()
        states = self.state_repository.get_states(
            context.staff_id,
            [item.key for item in items],
        ) if context.staff_id is not None else {}
        new_keys = frozenset(
            item.key
            for item in items
            if item.key not in states or states[item.key].seen_version != item.version
        )
        return AgendaResult(
            profile=context.presentation_profile,
            items=items,
            new_count=len(new_keys),
            active_count=len(items),
            counts_by_kind={item.kind: len(items)} if items else {},
            new_keys=new_keys,
            states_by_key=states,
        )


def _staff(**overrides):
    value = {
        "id": 5,
        "full_name": "Test Personel",
        "role": "personnel",
        "is_active": 1,
        "permissions": {"view_contracts"},
    }
    value.update(overrides)
    return value


def _item(
    *,
    lifecycle_type=AgendaLifecycleType.CONDITION,
    supports_snooze=True,
    version="effective-v2",
    severity=AgendaSeverity.ATTENTION,
):
    return AgendaItem(
        key="agenda-key",
        provider_code="test",
        kind="test",
        lifecycle_type=lifecycle_type,
        title="Test item",
        description="Description",
        priority=500,
        severity=severity,
        version=version,
        actor_staff_id=999,
        supports_snooze=supports_snooze,
    )


def _activity_item(
    *,
    key="activity:activity_log:42:status",
    version="ACTIVITY:42:status:2026-07-11 09:00:00",
    actor_name="Test Personel",
):
    return AgendaItem(
        key=key,
        provider_code="activity",
        kind="activity",
        lifecycle_type=AgendaLifecycleType.EVENT,
        title="C-1 durumu değişti",
        description="Açık → Kapalı",
        priority=450,
        severity=AgendaSeverity.INFO,
        version=version,
        contract_id=1,
        actor_staff_id=None,
        actor_name=actor_name,
        event_at="2026-07-11 09:00:00",
        effective_date="2026-07-11 09:00:00",
        supports_snooze=False,
        action_hints=("open_contract",),
    )


def _facade(item=None, *, service_class=_FakeAgendaService):
    repo = _FakeStateRepository()
    service = service_class(repo, items=(() if item is None else (item,)))
    facade = PersonalAgendaFacade(
        _FakeDB(),
        context_factory=PersonalAgendaContextFactory(
            now_provider=lambda: datetime(2026, 7, 11, 10, 0)
        ),
        agenda_service=service,
        state_repository=repo,
    )
    return facade, repo, service


def test_load_builds_context_service_result_and_projection():
    item = _item()
    facade, repo, service = _facade(item)
    snapshot = facade.load(
        _staff(),
        now=datetime(2026, 7, 11, 12, 0),
        personal_contract_ids=[3, 3, 2],
        compact_limit=1,
        detail_limit=1,
    )
    context, touch_presented = service.calls[0]
    assert context.staff_id == 5
    assert context.personal_contract_ids == frozenset({2, 3})
    assert touch_presented is True
    assert snapshot.all_items == (item,)
    assert snapshot.compact_items == (item,)
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []


def test_load_can_disable_touch_presented():
    facade, _repo, service = _facade(_item())
    facade.load(_staff(), touch_presented=False)
    assert service.calls[0][1] is False


def test_default_facade_and_service_share_state_repository_without_new_connection(monkeypatch):
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: pytest.fail("unexpected sqlite connection"))
    db = _FakeDB()
    facade = PersonalAgendaFacade(db)
    assert facade.agenda_service.state_repository is facade.state_repository
    assert facade.state_repository.conn is db.conn


def test_mark_seen_uses_current_staff_and_exact_effective_version():
    facade, repo, _service = _facade()
    seen_at = datetime(2026, 7, 11, 11, 30)
    state = facade.mark_seen(_staff(), _item(version="stage|R7:3"), seen_at=seen_at)
    assert repo.mark_seen_calls == [(5, "agenda-key", "stage|R7:3", seen_at)]
    assert state.staff_id == 5
    assert state.seen_version == "stage|R7:3"


def test_mark_seen_reads_persisted_state_when_repository_returns_none():
    facade, repo, _service = _facade()
    repo.mark_seen_returns_none = True
    state = facade.mark_seen(_staff(), _item())
    assert state.seen_version == "effective-v2"


def test_interactions_require_view_contracts_permission():
    facade, repo, _service = _facade()
    with pytest.raises(AgendaInteractionError, match="view_contracts"):
        facade.mark_seen(_staff(permissions=set()), _item())
    with pytest.raises(AgendaInteractionError, match="view_contracts"):
        facade.snooze(
            _staff(permissions=set()),
            _item(),
            until=datetime(2026, 7, 12, 10, 0),
            now=datetime(2026, 7, 11, 10, 0),
        )
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []


def test_event_and_non_snoozable_condition_are_rejected():
    facade, repo, _service = _facade()
    future = datetime(2026, 7, 12, 10, 0)
    now = datetime(2026, 7, 11, 10, 0)
    with pytest.raises(AgendaInteractionError, match="condition"):
        facade.snooze(_staff(), _item(lifecycle_type=AgendaLifecycleType.EVENT), until=future, now=now)
    with pytest.raises(AgendaInteractionError, match="does not support"):
        facade.snooze(_staff(), _item(supports_snooze=False), until=future, now=now)
    assert repo.snooze_calls == []


def test_past_or_equal_snooze_until_is_rejected():
    facade, repo, _service = _facade()
    now = datetime(2026, 7, 11, 10, 0)
    for until in (now, now - timedelta(seconds=1)):
        with pytest.raises(AgendaInteractionError, match="future"):
            facade.snooze(_staff(), _item(), until=until, now=now)
    assert repo.snooze_calls == []


def test_snooze_persists_exact_version_and_severity():
    facade, repo, _service = _facade()
    until = datetime(2026, 7, 14, 12, 15, 45)
    state = facade.snooze(
        _staff(),
        _item(version="UNKNOWN:year_only:2026", severity=AgendaSeverity.CRITICAL),
        until=until,
        now=datetime(2026, 7, 11, 10, 0),
    )
    assert repo.snooze_calls == [
        (5, "agenda-key", "UNKNOWN:year_only:2026", "CRITICAL", until)
    ]
    assert state.snoozed_version == "UNKNOWN:year_only:2026"
    assert state.snoozed_severity == "CRITICAL"


def test_clear_snooze_preserves_seen_state():
    facade, repo, _service = _facade()
    repo.persisted["agenda-key"] = AgendaItemState(
        staff_id=5,
        agenda_key="agenda-key",
        seen_at="2026-07-11 09:00:00",
        seen_version="effective-v2",
        snoozed_until="2026-07-12 09:00:00",
        snoozed_version="effective-v2",
        snoozed_severity="ATTENTION",
    )
    state = facade.clear_snooze(_staff(), _item())
    assert state.seen_at == "2026-07-11 09:00:00"
    assert state.seen_version == "effective-v2"
    assert state.snoozed_until is None
    assert repo.clear_calls == [(5, "agenda-key")]


def test_clear_snooze_returns_none_without_creating_row():
    facade, repo, _service = _facade()
    assert facade.clear_snooze(_staff(), _item()) is None
    assert repo.persisted == {}


def test_snooze_presets_are_deterministic():
    now = datetime(2026, 7, 11, 16, 25, 44, 123456)
    assert snooze_until_for_preset("tomorrow", now=now) == datetime(2026, 7, 12, 9, 0)
    assert snooze_until_for_preset("three_days", now=now) == datetime(2026, 7, 14, 16, 25)
    assert snooze_until_for_preset("one_week", now=now) == datetime(2026, 7, 18, 16, 25)
    assert PersonalAgendaFacade.snooze_until_for_preset("tomorrow", now=now) == datetime(2026, 7, 12, 9, 0)


def test_unknown_preset_is_rejected():
    with pytest.raises(AgendaInteractionError, match="Unknown"):
        snooze_until_for_preset("later", now=datetime(2026, 7, 11, 10, 0))


def test_item_actor_id_cannot_redirect_cross_staff_state_write():
    facade, repo, _service = _facade()
    facade.mark_seen(_staff(id=8), _item())
    assert repo.mark_seen_calls[0][0] == 8
    assert repo.mark_seen_calls[0][0] != 999


def test_sensitive_fields_do_not_reach_service_context():
    facade, _repo, service = _facade(_item())
    facade.load(
        _staff(password_hash="hash", password="plain", token="token", secret="secret")
    )
    context = service.calls[0][0]
    for field_name in ("password_hash", "password", "token", "secret"):
        assert field_name not in context.current_staff


def test_facade_manager_load_uses_management_profile():
    facade, _repo, service = _facade(_item())
    snapshot = facade.load(
        _staff(role="manager", role_name="manager", permissions={"view_contracts", "edit_contracts"})
    )
    context = service.calls[0][0]
    assert snapshot.profile.code == AgendaPresentationProfileCode.MANAGEMENT
    assert context.presentation_profile.code == AgendaPresentationProfileCode.MANAGEMENT


def test_facade_viewer_load_uses_view_only_profile():
    facade, _repo, service = _facade(_item())
    snapshot = facade.load(
        _staff(role="viewer", role_name="viewer", permissions={"view_contracts"})
    )
    assert snapshot.profile.code == AgendaPresentationProfileCode.VIEW_ONLY
    assert service.calls[0][0].presentation_profile.code == AgendaPresentationProfileCode.VIEW_ONLY


def test_real_system_admin_session_load_is_safe_empty():
    facade, repo, service = _facade(_item(), service_class=_PermissionAwareAgendaService)
    session = auth.build_system_admin_session(
        {"id": 9, "admin_name": "root", "is_active": 1},
        "admin-device",
    )

    snapshot = facade.load(session)
    context = service.calls[0][0]
    assert snapshot.profile.code == AgendaPresentationProfileCode.SYSTEM
    assert snapshot.all_items == ()
    assert context.staff_id is None
    assert context.permissions == frozenset()
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def _system_admin_session_with_view_permission():
    session = auth.build_system_admin_session(
        {"id": 9, "admin_name": "root", "is_active": 1},
        "admin-device",
    )
    session["permissions"] = {"view_contracts"}
    return session


def test_system_admin_mark_seen_is_rejected_without_state_write():
    facade, repo, _service = _facade()
    with pytest.raises(AgendaInteractionError, match="valid current staff identity"):
        facade.mark_seen(_system_admin_session_with_view_permission(), _item())
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def test_system_admin_snooze_is_rejected_without_state_write():
    facade, repo, _service = _facade()
    with pytest.raises(AgendaInteractionError, match="valid current staff identity"):
        facade.snooze(
            _system_admin_session_with_view_permission(),
            _item(),
            until=datetime(2026, 7, 12, 10, 0),
            now=datetime(2026, 7, 11, 10, 0),
        )
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def test_system_admin_clear_snooze_is_rejected_without_state_write():
    facade, repo, _service = _facade()
    with pytest.raises(AgendaInteractionError, match="valid current staff identity"):
        facade.clear_snooze(_system_admin_session_with_view_permission(), _item())
    assert repo.mark_seen_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def test_facade_keeps_legacy_class_and_load_signature():
    assert PersonalAgendaFacade.__name__ == "PersonalAgendaFacade"
    signature = inspect.signature(PersonalAgendaFacade.load)
    assert "personal_contract_ids" in signature.parameters
    assert signature.parameters["personal_contract_ids"].default == ()


def test_facade_explicit_contract_override():
    facade, _repo, service = _facade(_item())
    facade.load(
        _staff(role="manager", role_name="manager"),
        personal_contract_ids=[11, 11, 4],
    )
    context = service.calls[0][0]
    assert context.personal_contract_ids == frozenset({4, 11})


def test_facade_role_without_permission_returns_empty():
    facade, _repo, service = _facade(_item(), service_class=_PermissionAwareAgendaService)
    snapshot = facade.load(
        _staff(role="manager", role_name="manager", permissions={"edit_contracts"})
    )
    assert snapshot.all_items == ()
    assert snapshot.profile.code == AgendaPresentationProfileCode.MANAGEMENT
    assert service.calls[0][0].permissions == frozenset({"edit_contracts"})


def test_facade_does_not_grant_permissions_from_role():
    facade, _repo, service = _facade(_item(), service_class=_PermissionAwareAgendaService)
    facade.load(
        _staff(role="manager", role_name="manager", permissions=set())
    )
    context = service.calls[0][0]
    assert context.permissions == frozenset()
    assert context.presentation_profile.permissions == frozenset()


def test_activity_event_mark_seen_uses_exact_staff_key_and_version():
    item = _activity_item()
    facade, repo, _service = _facade(item)
    seen_at = datetime(2026, 7, 11, 10, 30)
    state = facade.mark_seen(_staff(id=7), item, seen_at=seen_at)
    assert repo.mark_seen_calls == [(7, item.key, item.version, seen_at)]
    assert state.staff_id == 7
    assert state.agenda_key == item.key
    assert state.seen_version == item.version


def test_activity_mark_seen_then_load_is_visible_and_not_new():
    item = _activity_item()
    facade, repo, _service = _facade(item, service_class=_StateAwareAgendaService)
    facade.mark_seen(_staff(), item, seen_at=datetime(2026, 7, 11, 10, 0))
    snapshot = facade.load(_staff(), now=datetime(2026, 7, 11, 10, 30))
    assert snapshot.all_items == (item,)
    assert snapshot.result.active_count == 1
    assert snapshot.result.new_count == 0
    assert item.key not in snapshot.result.new_keys
    assert snapshot.result.states_by_key[item.key].seen_version == item.version


def test_activity_event_snooze_is_rejected_without_state_mutation():
    item = _activity_item()
    facade, repo, _service = _facade(item)
    with pytest.raises(AgendaInteractionError, match="condition"):
        facade.snooze(
            _staff(),
            item,
            until=datetime(2026, 7, 12, 10, 0),
            now=datetime(2026, 7, 11, 10, 0),
        )
    assert repo.snooze_calls == []
    assert repo.persisted == {}


def test_activity_no_view_mark_seen_rejected_before_state_access():
    item = _activity_item()
    facade, repo, _service = _facade(item)
    with pytest.raises(AgendaInteractionError, match="view_contracts"):
        facade.mark_seen(_staff(permissions=set()), item)
    assert repo.mark_seen_calls == []
    assert repo.get_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def test_activity_system_admin_interactions_rejected_before_state_access():
    item = _activity_item()
    facade, repo, _service = _facade(item)
    session = _system_admin_session_with_view_permission()
    assert session["admin_id"] == 9
    with pytest.raises(AgendaInteractionError, match="valid current staff identity"):
        facade.mark_seen(session, item)
    with pytest.raises(AgendaInteractionError, match="valid current staff identity"):
        facade.snooze(
            session,
            item,
            until=datetime(2026, 7, 12, 10, 0),
            now=datetime(2026, 7, 11, 10, 0),
        )
    assert repo.mark_seen_calls == []
    assert repo.get_calls == []
    assert repo.snooze_calls == []
    assert repo.clear_calls == []


def test_activity_actor_display_name_cannot_redirect_interaction_identity():
    item = _activity_item(actor_name="Test Personel")
    facade, repo, _service = _facade(item)
    facade.mark_seen(_staff(id=12, full_name="Test Personel"), item)
    assert item.actor_staff_id is None
    assert item.actor_name == "Test Personel"
    assert repo.mark_seen_calls[0][0] == 12
    assert repo.mark_seen_calls[0][1:3] == (item.key, item.version)
