from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.agenda.constants import AgendaLifecycleType, AgendaPresentationProfileCode, AgendaSeverity
from src.domain.agenda.models import AgendaContext, AgendaItem, AgendaItemState, AgendaPresentationProfile
from src.domain.agenda.source_models import AgendaCalendarSource
from src.services.staff_agenda_service import AgendaBuildError, StaffAgendaService


NOW = datetime(2026, 7, 11, 12, 0, 0)


def _profile():
    return AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset({"view_contracts"}),
    )


def _context(*, permissions=frozenset({"view_contracts"}), ids=frozenset()):
    return AgendaContext(
        now=NOW,
        today=date(2026, 7, 11),
        presentation_profile=_profile(),
        staff_id=1,
        permissions=permissions,
        personal_contract_ids=ids,
    )


def _source(contract_id=1, raw="2026-07-12"):
    return AgendaCalendarSource(
        entity_type="contract",
        entity_id=contract_id,
        contract_id=contract_id,
        contract_no=f"C-{contract_id}",
        contract_type="Ana",
        completion_date=raw,
        status="Açık",
    )


def _item(key="p:contract:1", *, kind="test", priority=100, severity=AgendaSeverity.ATTENTION, version="V1", payload=None):
    return AgendaItem(
        key=key,
        provider_code="p",
        kind=kind,
        lifecycle_type=AgendaLifecycleType.CONDITION,
        title=key,
        description=key,
        priority=priority,
        severity=severity,
        version=version,
        contract_id=1,
        detail_payload=payload or {},
        supports_snooze=True,
    )


class FakeSourceRepository:
    def __init__(self, ids=frozenset({1}), sources=(_source(),)):
        self.ids = ids
        self.sources = tuple(sources)
        self.personal_calls = 0
        self.source_calls = 0
        self.last_contract_ids = None

    def list_personal_contract_ids(self, staff_id):
        self.personal_calls += 1
        return self.ids

    def list_calendar_sources(self, contract_ids):
        self.source_calls += 1
        self.last_contract_ids = frozenset(contract_ids)
        return tuple(source for source in self.sources if source.contract_id in contract_ids)


class FakeStateRepository:
    def __init__(self, states=None):
        self.states = dict(states or {})
        self.get_calls = []
        self.touch_calls = []
        self.mark_seen_calls = []

    def get_states(self, staff_id, keys):
        self.get_calls.append((staff_id, tuple(keys)))
        return {key: self.states[key] for key in keys if key in self.states}

    def touch_presented(self, staff_id, keys, presented_at=None):
        self.touch_calls.append((staff_id, tuple(keys), presented_at))

    def mark_seen(self, *args, **kwargs):
        self.mark_seen_calls.append((args, kwargs))


class StaticProvider:
    code = "static"

    def __init__(self, items):
        self.items = tuple(items)

    def build(self, context, sources):
        return self.items


def _service(*, source=None, state=None, providers=None):
    return StaffAgendaService(
        object(),
        state_repository=state or FakeStateRepository(),
        source_repository=source or FakeSourceRepository(),
        providers=providers if providers is not None else [StaticProvider([_item()])],
    )


def test_missing_view_contracts_permission_returns_empty_without_source_query():
    source = FakeSourceRepository()
    state = FakeStateRepository()
    result = _service(source=source, state=state).build(_context(permissions=frozenset()))
    assert result.items == ()
    assert source.personal_calls == source.source_calls == 0
    assert state.get_calls == [] and state.touch_calls == []


def test_personal_scope_excludes_unassigned_contracts():
    source = FakeSourceRepository(ids=frozenset({1}), sources=(_source(1), _source(2)))
    result = _service(source=source).build(_context())
    assert source.last_contract_ids == frozenset({1})
    assert result.active_count == 1


def test_context_personal_contract_ids_override_repository_scope():
    source = FakeSourceRepository(ids=frozenset({1}), sources=(_source(2),))
    _service(source=source).build(_context(ids=frozenset({2})))
    assert source.personal_calls == 0
    assert source.last_contract_ids == frozenset({2})


def test_service_builds_deadline_and_unknown_items():
    source = FakeSourceRepository(ids=frozenset({1, 2}), sources=(_source(1, "2026-07-12"), _source(2, "TBD")))
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert {item.kind for item in result.items} == {"deadline", "unknown_date"}


def test_service_batches_state_lookup():
    state = FakeStateRepository()
    service = _service(state=state, providers=[StaticProvider([_item("p:contract:1"), _item("p:contract:2")])])
    service.build(_context(), touch_presented=False)
    assert len(state.get_calls) == 1
    assert set(state.get_calls[0][1]) == {"p:contract:1", "p:contract:2"}


def test_duplicate_provider_key_raises_agenda_build_error():
    service = _service(providers=[StaticProvider([_item("same")]), StaticProvider([_item("same")])])
    with pytest.raises(AgendaBuildError, match="Duplicate agenda key"):
        service.build(_context())


def test_seen_condition_remains_active_and_not_new():
    item = _item()
    state = FakeStateRepository({item.key: AgendaItemState(staff_id=1, agenda_key=item.key, seen_version="V1")})
    result = _service(state=state, providers=[StaticProvider([item])]).build(_context(), touch_presented=False)
    assert result.active_count == 1
    assert result.new_count == 0


def test_snoozed_condition_is_filtered_and_counted():
    item = _item()
    state = FakeStateRepository({
        item.key: AgendaItemState(
            staff_id=1,
            agenda_key=item.key,
            snoozed_until="2026-07-12 12:00:00",
            snoozed_version="V1",
            snoozed_severity="ATTENTION",
        )
    })
    result = _service(state=state, providers=[StaticProvider([item])]).build(_context(), touch_presented=False)
    assert result.items == ()
    assert result.filtered_count == 1 and result.snoozed_count == 1


def test_unknown_item_resurfaces_after_cadence():
    item = _item(version="UNKNOWN:TBD", payload={"resurface_interval_days": 7})
    state = FakeStateRepository({
        item.key: AgendaItemState(
            staff_id=1,
            agenda_key=item.key,
            first_presented_at="2026-07-04 12:00:00",
            seen_version="UNKNOWN:TBD|R7:0",
        )
    })
    result = _service(state=state, providers=[StaticProvider([item])]).build(_context(), touch_presented=False)
    assert result.items[0].version == "UNKNOWN:TBD|R7:1"
    assert item.key in result.new_keys


def test_new_items_sort_before_seen_items():
    seen = _item("seen", priority=1000)
    new = _item("new", priority=1)
    state = FakeStateRepository({seen.key: AgendaItemState(staff_id=1, agenda_key=seen.key, seen_version="V1")})
    result = _service(state=state, providers=[StaticProvider([seen, new])]).build(_context(), touch_presented=False)
    assert [item.key for item in result.items] == ["new", "seen"]


def test_higher_priority_sorts_first():
    low = _item("low", priority=1)
    high = _item("high", priority=100)
    result = _service(providers=[StaticProvider([low, high])]).build(_context(), touch_presented=False)
    assert [item.key for item in result.items] == ["high", "low"]


def test_counts_by_kind_include_visible_items_only():
    visible = _item("visible", kind="deadline")
    hidden = _item("hidden", kind="unknown_date")
    state = FakeStateRepository({
        hidden.key: AgendaItemState(
            staff_id=1,
            agenda_key=hidden.key,
            snoozed_until="2026-07-12 12:00:00",
            snoozed_version="V1",
            snoozed_severity="ATTENTION",
        )
    })
    result = _service(state=state, providers=[StaticProvider([visible, hidden])]).build(_context(), touch_presented=False)
    assert dict(result.counts_by_kind) == {"deadline": 1}


def test_touch_presented_records_visible_items():
    state = FakeStateRepository()
    item = _item()
    _service(state=state, providers=[StaticProvider([item])]).build(_context())
    assert state.touch_calls == [(1, (item.key,), NOW)]


def test_touch_presented_false_is_pure_read():
    state = FakeStateRepository()
    _service(state=state).build(_context(), touch_presented=False)
    assert state.touch_calls == []


def test_build_does_not_mark_items_seen():
    state = FakeStateRepository()
    _service(state=state).build(_context())
    assert state.mark_seen_calls == []


def test_empty_scope_returns_empty_result():
    source = FakeSourceRepository(ids=frozenset(), sources=())
    state = FakeStateRepository()
    result = _service(source=source, state=state).build(_context())
    assert result.items == ()
    assert source.source_calls == 0
    assert state.get_calls == []
