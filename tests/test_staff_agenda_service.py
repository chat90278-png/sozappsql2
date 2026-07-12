from __future__ import annotations

from datetime import date, datetime

import pytest

from src.domain.agenda.constants import AgendaLifecycleType, AgendaPresentationProfileCode, AgendaSeverity
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem, AgendaItemState, AgendaPresentationProfile
from src.domain.agenda.source_models import (
    AgendaCalendarSource,
    AgendaSourceBundle,
    ReturnedShareAgendaSource,
)
from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_RETURNED
from src.services.staff_agenda_service import AgendaBuildError, StaffAgendaService
from src.services.sts_database import STSDatabase


NOW = datetime(2026, 7, 11, 12, 0, 0)


def _profile():
    return AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Personal",
        description="Personal",
        permissions=frozenset({"view_contracts"}),
    )


def _context(*, permissions=frozenset({"view_contracts"}), ids=frozenset(), staff_id=1):
    return AgendaContext(
        now=NOW,
        today=date(2026, 7, 11),
        presentation_profile=_profile(),
        staff_id=staff_id,
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


def _returned(
    package_id="pkg-1",
    *,
    contract_id=1,
    status=SHARE_STATUS_RETURNED,
    revision=1,
    registry_id=1,
):
    return ReturnedShareAgendaSource(
        registry_id=registry_id,
        share_package_id=package_id,
        contract_id=contract_id,
        contract_merge_uid=f"merge-{contract_id}",
        contract_no=f"C-{contract_id}",
        contract_type="Ana",
        status=status,
        source_contract_revision=revision,
        permission_mode="edit",
        share_format_version=2,
        snapshot_format_version=1,
        base_snapshot_sha256=f"hash-{package_id}",
        created_at="2026-07-10 09:00:00",
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
    def __init__(self, ids=frozenset({1}), bundle=None):
        self.ids = ids
        self.bundle = bundle or AgendaSourceBundle(calendar=(_source(),))
        self.personal_calls = 0
        self.load_calls = 0
        self.last_contract_ids = None

    def list_personal_contract_ids(self, staff_id):
        self.personal_calls += 1
        return self.ids

    def load_personal_sources(self, contract_ids):
        self.load_calls += 1
        selected = frozenset(contract_ids)
        self.last_contract_ids = selected
        return AgendaSourceBundle(
            calendar=tuple(source for source in self.bundle.calendar if source.contract_id in selected),
            returned_shares=tuple(
                source for source in self.bundle.returned_shares if source.contract_id in selected
            ),
        )


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
    assert source.personal_calls == source.load_calls == 0
    assert state.get_calls == [] and state.touch_calls == []


def test_personal_scope_excludes_unassigned_contracts():
    source = FakeSourceRepository(
        ids=frozenset({1}),
        bundle=AgendaSourceBundle(calendar=(_source(1), _source(2))),
    )
    result = _service(source=source).build(_context())
    assert source.last_contract_ids == frozenset({1})
    assert result.active_count == 1


def test_context_personal_contract_ids_override_repository_scope():
    source = FakeSourceRepository(
        ids=frozenset({1}),
        bundle=AgendaSourceBundle(calendar=(_source(2),)),
    )
    _service(source=source).build(_context(ids=frozenset({2})))
    assert source.personal_calls == 0
    assert source.last_contract_ids == frozenset({2})


def test_service_builds_deadline_and_unknown_items():
    source = FakeSourceRepository(
        ids=frozenset({1, 2}),
        bundle=AgendaSourceBundle(calendar=(_source(1, "2026-07-12"), _source(2, "TBD"))),
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert {item.kind for item in result.items} == {"deadline", "unknown_date"}


def test_default_service_builds_returned_share_item():
    source = FakeSourceRepository(
        bundle=AgendaSourceBundle(returned_shares=(_returned(),)),
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert len(result.items) == 1
    assert result.items[0].kind == "returned_share"


def test_service_personal_scope_excludes_unassigned_returned_share():
    source = FakeSourceRepository(
        ids=frozenset({1}),
        bundle=AgendaSourceBundle(returned_shares=(_returned(contract_id=2),)),
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    assert service.build(_context(), touch_presented=False).items == ()


def test_returned_share_and_deadline_coexist():
    source = FakeSourceRepository(
        bundle=AgendaSourceBundle(calendar=(_source(),), returned_shares=(_returned(),)),
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert {item.kind for item in result.items} == {"deadline", "returned_share"}


def test_returned_share_sorts_between_critical_and_upcoming_deadline_by_priority():
    source = FakeSourceRepository(
        ids=frozenset({1, 2, 3}),
        bundle=AgendaSourceBundle(
            calendar=(
                _source(1, "2026-07-26"),
                _source(3, "2026-07-27"),
            ),
            returned_shares=(_returned(contract_id=2),),
        ),
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert [item.priority for item in result.items] == [900, 850, 700]
    assert [item.kind for item in result.items] == ["deadline", "returned_share", "deadline"]


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


def test_duplicate_share_key_raises():
    source = FakeSourceRepository(
        bundle=AgendaSourceBundle(
            returned_shares=(
                _returned("same", registry_id=1),
                _returned("same", registry_id=2),
            )
        )
    )
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    with pytest.raises(AgendaBuildError, match="Duplicate agenda key"):
        service.build(_context(), touch_presented=False)


def test_seen_condition_remains_active_and_not_new():
    item = _item()
    state = FakeStateRepository({item.key: AgendaItemState(staff_id=1, agenda_key=item.key, seen_version="V1")})
    result = _service(state=state, providers=[StaticProvider([item])]).build(_context(), touch_presented=False)
    assert result.active_count == 1
    assert result.new_count == 0


def test_returned_share_seen_remains_active_not_new():
    returned = _returned()
    key = build_agenda_key(provider_code="returned_share", entity_type="share_package", entity_id=returned.share_package_id)
    version = "RETURNED:1:hash-pkg-1"
    state = FakeStateRepository({key: AgendaItemState(staff_id=1, agenda_key=key, seen_version=version)})
    source = FakeSourceRepository(bundle=AgendaSourceBundle(returned_shares=(returned,)))
    service = StaffAgendaService(object(), state_repository=state, source_repository=source)
    result = service.build(_context(), touch_presented=False)
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


def test_returned_share_snooze_is_filtered_and_counted():
    returned = _returned()
    key = build_agenda_key(provider_code="returned_share", entity_type="share_package", entity_id=returned.share_package_id)
    version = "RETURNED:1:hash-pkg-1"
    state = FakeStateRepository({
        key: AgendaItemState(
            staff_id=1,
            agenda_key=key,
            snoozed_until="2026-07-12 12:00:00",
            snoozed_version=version,
            snoozed_severity="ATTENTION",
        )
    })
    source = FakeSourceRepository(bundle=AgendaSourceBundle(returned_shares=(returned,)))
    service = StaffAgendaService(object(), state_repository=state, source_repository=source)
    result = service.build(_context(), touch_presented=False)
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


def test_returned_share_counts_by_kind():
    source = FakeSourceRepository(bundle=AgendaSourceBundle(returned_shares=(_returned(),)))
    service = StaffAgendaService(object(), state_repository=FakeStateRepository(), source_repository=source)
    result = service.build(_context(), touch_presented=False)
    assert dict(result.counts_by_kind) == {"returned_share": 1}


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


def test_service_uses_one_source_bundle_load():
    source = FakeSourceRepository()
    _service(source=source).build(_context(), touch_presented=False)
    assert source.load_calls == 1


def test_empty_scope_does_not_query_share_sources():
    source = FakeSourceRepository(ids=frozenset(), bundle=AgendaSourceBundle())
    state = FakeStateRepository()
    result = _service(source=source, state=state).build(_context())
    assert result.items == ()
    assert source.load_calls == 0
    assert state.get_calls == []


def test_empty_scope_returns_empty_result():
    source = FakeSourceRepository(ids=frozenset(), bundle=AgendaSourceBundle())
    state = FakeStateRepository()
    result = _service(source=source, state=state).build(_context())
    assert result.items == ()
    assert source.load_calls == 0
    assert state.get_calls == []


def test_returned_share_status_transition_removes_condition(tmp_path):
    db = STSDatabase(tmp_path / "returned-transition.sts", source="Stage 3B Test")
    try:
        with db.tx():
            platform_id = db.conn.execute(
                "INSERT INTO platforms(name,display_name,is_active) VALUES('P1','P1',1)"
            ).lastrowid
            staff_id = db.conn.execute(
                "INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('d1','S1','x','personnel',1)"
            ).lastrowid
            contract_id = db.conn.execute(
                "INSERT INTO contracts(platform_id,contract_no,contract_type,status,merge_uid,revision) VALUES(?,?,?,?,?,?)",
                (platform_id, "C-1", "Ana", "Açık", "merge-c1", 1),
            ).lastrowid
            db.conn.execute(
                "INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,1)",
                (contract_id, staff_id),
            )
            db.conn.execute(
                """
                INSERT INTO share_packages(
                    share_package_id,contract_id,contract_merge_uid,source_contract_revision,
                    permission_mode,share_format_version,snapshot_format_version,
                    base_snapshot_sha256,created_at,status
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "pkg-transition", contract_id, "merge-c1", 1, "edit", 2, 1,
                    "base-transition", "2026-07-10 09:00:00", SHARE_STATUS_RETURNED,
                ),
            )
        service = StaffAgendaService(db)
        context = _context(staff_id=int(staff_id))
        first = service.build(context, touch_presented=False)
        assert [item.kind for item in first.items] == ["returned_share"]
        with db.tx():
            db.conn.execute(
                "UPDATE share_packages SET status=? WHERE share_package_id=?",
                (SHARE_STATUS_MERGED, "pkg-transition"),
            )
        second = service.build(context, touch_presented=False)
        assert all(item.kind != "returned_share" for item in second.items)
    finally:
        db.close()
