from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.domain.agenda.source_models import AgendaSourceBundle
from src.models.share_models import (
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
)
from src.services.agenda_source_repository import AgendaSourceRepository
from src.services.sts_database import STSDatabase


@pytest.fixture
def db(tmp_path):
    database = STSDatabase(tmp_path / "agenda-source.sts", source="Agenda Source Tests")
    try:
        yield database
    finally:
        database.close()


def _seed(db: STSDatabase):
    with db.tx():
        p1 = db.conn.execute("INSERT INTO platforms(name,display_name,is_active) VALUES('Zulu','Zulu',1)").lastrowid
        p2 = db.conn.execute("INSERT INTO platforms(name,display_name,is_active) VALUES('alpha','Alpha',1)").lastrowid
        staff1 = db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('d1','S1','x','personnel',1)").lastrowid
        staff2 = db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('d2','S2','x','personnel',1)").lastrowid
        inactive = db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES('d3','S3','x','personnel',0)").lastrowid
        c1 = db.conn.execute(
            "INSERT INTO contracts(platform_id,contract_no,contract_type,status,completion_date,note,merge_uid,revision) VALUES(?,?,?,?,?,?,?,?)",
            (p1, "C-2", "Ana", "Açık", "2026-07-20", "n1", "merge-c1", 4),
        ).lastrowid
        c2 = db.conn.execute(
            "INSERT INTO contracts(platform_id,contract_no,contract_type,status,completion_date,note,merge_uid,revision) VALUES(?,?,?,?,?,?,?,?)",
            (p2, "C-1", "Ana", "Açık", "TBD", "n2", "merge-c2", 2),
        ).lastrowid
        db.conn.execute("INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,0,1)", (c1, p1))
        db.conn.execute("INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,1,0)", (c1, p2))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,1)", (c1, staff1))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,1)", (c2, staff2))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,0)", (c2, inactive))
        s1 = db.conn.execute(
            "INSERT INTO systems(contract_id,platform_id,name,status,completion_date,merge_uid) VALUES(?,?,?,?,?,?)",
            (c1, p2, "System B", "Açık", "2026-07-15", "merge-s1"),
        ).lastrowid
        d1 = db.conn.execute(
            "INSERT INTO deliveries(contract_id,system_id,name,status,planned_acceptance_date,merge_uid) VALUES(?,?,?,?,?,?)",
            (c1, s1, "Delivery A", "Açık", "2026-07-18", "merge-d1"),
        ).lastrowid
    return {
        "staff1": int(staff1), "staff2": int(staff2), "inactive": int(inactive),
        "p1": int(p1), "p2": int(p2),
        "c1": int(c1), "c2": int(c2), "s1": int(s1), "d1": int(d1),
    }


def _insert_share(
    db: STSDatabase,
    *,
    contract_id: int,
    package_id: str,
    status: str = SHARE_STATUS_RETURNED,
    revision: int = 4,
    created_at: str = "2026-07-10 09:00:00",
    staff_id: int | None = None,
    return_count: int = 2,
) -> int:
    with db.tx():
        return int(
            db.conn.execute(
                """
                INSERT INTO share_packages(
                    share_package_id,contract_id,contract_merge_uid,
                    source_contract_revision,permission_mode,share_format_version,
                    snapshot_format_version,base_snapshot_sha256,created_at,
                    created_by_staff_id,created_by_full_name,exported_filename,status,
                    last_imported_at,last_imported_by_staff_id,
                    last_remote_snapshot_sha256,return_count
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    package_id, contract_id, f"merge-{contract_id}", revision, "edit", 2,
                    1, f"base-{package_id}", created_at, staff_id, "Gönderen",
                    f"{package_id}.sts", status, "2026-07-12 10:00:00", staff_id,
                    f"remote-{package_id}", return_count,
                ),
            ).lastrowid
        )


def _insert_lock(
    db: STSDatabase,
    *,
    contract_id: int,
    is_locked: int = 1,
    staff_id: int | None = None,
    device_name: str = "LOCK-DEVICE",
    full_name: str = "Lock Owner",
    locked_at: str | None = "2026-07-13 09:00:00",
    updated_at: str = "2026-07-13 09:05:00",
) -> None:
    with db.tx():
        db.conn.execute(
            """
            INSERT INTO document_locks(
                contract_id,is_locked,locked_by_staff_id,locked_by_device_name,
                locked_by_full_name,locked_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(contract_id) DO UPDATE SET
                is_locked=excluded.is_locked,
                locked_by_staff_id=excluded.locked_by_staff_id,
                locked_by_device_name=excluded.locked_by_device_name,
                locked_by_full_name=excluded.locked_by_full_name,
                locked_at=excluded.locked_at,
                updated_at=excluded.updated_at
            """,
            (
                contract_id,
                is_locked,
                staff_id,
                device_name,
                full_name,
                locked_at,
                updated_at,
            ),
        )


def _insert_activity(
    db: STSDatabase,
    *,
    contract_id: int,
    action: str = "contract_updated",
    created_at: str = "2026-07-13 10:00:00",
    entity_type: str = "contract",
    entity_id: str | None = None,
    actor: str = "Actor",
    source: str = "Unit Test",
    device_name: str = "DEVICE",
    message: str = "message",
    before: object = None,
    after: object = None,
    raw_before_json: str | None = None,
    raw_after_json: str | None = None,
    contract_no: str | None = None,
    payload_json: str | None = None,
) -> int:
    before = {"completion_date": "2026-07-01"} if before is None else before
    after = {"completion_date": "2026-07-02"} if after is None else after
    before_json = raw_before_json if raw_before_json is not None else json.dumps(before, ensure_ascii=False)
    after_json = raw_after_json if raw_after_json is not None else json.dumps(after, ensure_ascii=False)
    with db.tx():
        return int(
            db.conn.execute(
                """
                INSERT INTO activity_logs(
                    created_at,actor,source,device_name,action,entity_type,entity_id,
                    contract_no,message,before_json,after_json,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    created_at,
                    actor,
                    source,
                    device_name,
                    action,
                    entity_type,
                    str(contract_id) if entity_id is None else entity_id,
                    contract_no,
                    message,
                    before_json,
                    after_json,
                    payload_json,
                ),
            ).lastrowid
        )


def test_personal_contract_ids_include_only_selected_staff(db):
    ids = _seed(db)
    repo = AgendaSourceRepository(db)
    assert repo.list_personal_contract_ids(ids["staff1"]) == frozenset({ids["c1"]})
    assert repo.list_personal_contract_ids(ids["staff2"]) == frozenset({ids["c2"]})


def test_inactive_staff_scope_is_empty(db):
    ids = _seed(db)
    assert AgendaSourceRepository(db).list_personal_contract_ids(ids["inactive"]) == frozenset()


def test_calendar_sources_empty_contract_ids_returns_empty(db):
    assert AgendaSourceRepository(db).list_calendar_sources([]) == ()


def test_calendar_sources_exclude_other_contracts(db):
    ids = _seed(db)
    sources = AgendaSourceRepository(db).list_calendar_sources([ids["c1"]])
    assert {source.contract_id for source in sources} == {ids["c1"]}


def test_multiplatform_contract_produces_one_contract_source(db):
    ids = _seed(db)
    sources = AgendaSourceRepository(db).list_calendar_sources([ids["c1"]])
    assert len([source for source in sources if source.entity_type == "contract"]) == 1


def test_multiplatform_contract_platform_names_are_sorted_and_joined(db):
    ids = _seed(db)
    source = next(item for item in AgendaSourceRepository(db).list_calendar_sources([ids["c1"]]) if item.entity_type == "contract")
    assert source.platform == "alpha / Zulu"


def test_system_source_contains_exact_system_id_and_platform(db):
    ids = _seed(db)
    source = next(item for item in AgendaSourceRepository(db).list_calendar_sources([ids["c1"]]) if item.entity_type == "system")
    assert source.system_id == ids["s1"]
    assert source.entity_id == ids["s1"]
    assert source.platform == "alpha"


def test_delivery_source_contains_delivery_and_system_ids(db):
    ids = _seed(db)
    source = next(item for item in AgendaSourceRepository(db).list_calendar_sources([ids["c1"]]) if item.entity_type == "delivery")
    assert source.delivery_id == ids["d1"]
    assert source.system_id == ids["s1"]


def test_calendar_sources_have_stable_order(db):
    ids = _seed(db)
    sources = AgendaSourceRepository(db).list_calendar_sources([ids["c1"], ids["c2"]])
    kinds = [source.entity_type for source in sources]
    assert kinds == sorted(kinds, key={"contract": 0, "system": 1, "delivery": 2}.get)
    assert [source.contract_no for source in sources if source.entity_type == "contract"] == ["C-1", "C-2"]


def test_returned_share_sources_empty_scope(db):
    assert AgendaSourceRepository(db).list_returned_share_sources([]) == ()


def test_returned_share_sources_include_only_returned_status(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="returned", status=SHARE_STATUS_RETURNED)
    _insert_share(db, contract_id=ids["c1"], package_id="open", status=SHARE_STATUS_OPEN)
    sources = AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]])
    assert [source.share_package_id for source in sources] == ["returned"]


def test_returned_share_sources_exclude_open_and_final_statuses(db):
    ids = _seed(db)
    for status in (
        SHARE_STATUS_OPEN,
        SHARE_STATUS_MERGED,
        SHARE_STATUS_PARTIALLY_MERGED,
        SHARE_STATUS_REJECTED,
        SHARE_STATUS_CANCELLED,
    ):
        _insert_share(db, contract_id=ids["c1"], package_id=status.lower(), status=status)
    assert AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]]) == ()


def test_returned_share_sources_exclude_unassigned_contracts(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c2"], package_id="other", status=SHARE_STATUS_RETURNED)
    personal_ids = AgendaSourceRepository(db).list_personal_contract_ids(ids["staff1"])
    assert AgendaSourceRepository(db).list_returned_share_sources(personal_ids) == ()


def test_returned_share_source_exact_registry_fields(db):
    ids = _seed(db)
    registry_id = _insert_share(
        db,
        contract_id=ids["c1"],
        package_id="pkg-exact",
        staff_id=ids["staff1"],
        revision=7,
        return_count=3,
    )
    source = AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]])[0]
    assert source.registry_id == registry_id
    assert source.share_package_id == "pkg-exact"
    assert source.contract_id == ids["c1"]
    assert source.contract_no == "C-2"
    assert source.contract_type == "Ana"
    assert source.status == SHARE_STATUS_RETURNED
    assert source.source_contract_revision == 7
    assert source.permission_mode == "edit"
    assert source.share_format_version == 2
    assert source.snapshot_format_version == 1
    assert source.base_snapshot_sha256 == "base-pkg-exact"
    assert source.created_by_staff_id == ids["staff1"]
    assert source.last_imported_by_staff_id == ids["staff1"]
    assert source.last_remote_snapshot_sha256 == "remote-pkg-exact"
    assert source.return_count == 3


def test_returned_share_multiplatform_contract_is_not_duplicated(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-multi")
    sources = AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]])
    assert len(sources) == 1


def test_returned_share_platform_names_sorted_and_joined(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-platform")
    source = AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]])[0]
    assert source.platform == "alpha / Zulu"


def test_returned_share_sources_stable_order(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="z-package")
    _insert_share(db, contract_id=ids["c2"], package_id="b-package")
    _insert_share(db, contract_id=ids["c2"], package_id="A-package")
    sources = AgendaSourceRepository(db).list_returned_share_sources([ids["c1"], ids["c2"]])
    assert [source.share_package_id for source in sources] == ["A-package", "b-package", "z-package"]


def test_load_personal_sources_returns_calendar_and_share_sources(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-bundle")
    bundle = AgendaSourceRepository(db).load_personal_sources([ids["c1"]])
    assert isinstance(bundle, AgendaSourceBundle)
    assert bundle.calendar
    assert [source.share_package_id for source in bundle.returned_shares] == ["pkg-bundle"]


def test_returned_share_query_does_not_mutate_database(db):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-read")
    before = db.conn.total_changes
    AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]])
    assert db.conn.total_changes == before


def test_returned_share_query_does_not_read_activity_log_as_source(db):
    ids = _seed(db)
    db.add_log(
        "share_returned",
        entity_type="share_package",
        entity_key="activity-only-package",
        message="RETURNED",
    )
    assert AgendaSourceRepository(db).list_returned_share_sources([ids["c1"]]) == ()


def test_source_repository_does_not_mutate_database(db):
    ids = _seed(db)
    before = db.conn.total_changes
    repo = AgendaSourceRepository(db)
    repo.list_personal_contract_ids(ids["staff1"])
    repo.list_calendar_sources([ids["c1"]])
    repo.list_returned_share_sources([ids["c1"]])
    repo.list_document_lock_sources([ids["c1"]])
    repo.load_personal_sources([ids["c1"]])
    assert db.conn.total_changes == before


def test_list_all_contract_ids_returns_every_contract(db):
    ids = _seed(db)
    assert AgendaSourceRepository(db).list_all_contract_ids() == frozenset({ids["c1"], ids["c2"]})


def test_list_all_contract_ids_is_deterministic(db):
    ids = _seed(db)
    repo = AgendaSourceRepository(db)
    assert repo.list_all_contract_ids() == repo.list_all_contract_ids()
    assert tuple(sorted(repo.list_all_contract_ids())) == tuple(sorted({ids["c1"], ids["c2"]}))


def test_list_all_contract_ids_empty_database(db):
    assert AgendaSourceRepository(db).list_all_contract_ids() == frozenset()


def test_list_all_contract_ids_does_not_mutate_database(db):
    _seed(db)
    before = db.conn.total_changes
    AgendaSourceRepository(db).list_all_contract_ids()
    assert db.conn.total_changes == before


def test_document_lock_source_requires_active_row_and_locked_timestamp(db):
    ids = _seed(db)
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    _insert_lock(db, contract_id=ids["c2"], is_locked=0, staff_id=ids["staff2"])
    sources = AgendaSourceRepository(db).list_document_lock_sources([ids["c1"], ids["c2"]])
    assert [source.contract_id for source in sources] == [ids["c1"]]

    with db.tx():
        db.conn.execute(
            "UPDATE document_locks SET is_locked=1,locked_at=NULL WHERE contract_id=?",
            (ids["c2"],),
        )
    assert AgendaSourceRepository(db).list_document_lock_sources([ids["c2"]]) == ()


def test_document_lock_sources_respect_supplied_contract_scope(db):
    ids = _seed(db)
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    _insert_lock(db, contract_id=ids["c2"], staff_id=ids["staff2"])
    sources = AgendaSourceRepository(db).list_document_lock_sources([ids["c1"]])
    assert {source.contract_id for source in sources} == {ids["c1"]}


def test_document_lock_source_carries_exact_owner_and_contract_metadata(db):
    ids = _seed(db)
    _insert_lock(
        db,
        contract_id=ids["c1"],
        staff_id=ids["staff1"],
        device_name=" DEVICE-1 ",
        full_name=" Owner One ",
        locked_at="2026-07-13 08:00:00",
        updated_at="2026-07-13 08:05:00",
    )
    source = AgendaSourceRepository(db).list_document_lock_sources([ids["c1"]])[0]
    assert source.contract_no == "C-2"
    assert source.contract_type == "Ana"
    assert source.platform == "alpha / Zulu"
    assert source.is_locked is True
    assert source.locked_by_staff_id == ids["staff1"]
    assert source.locked_by_device_name == "DEVICE-1"
    assert source.locked_by_full_name == "Owner One"
    assert source.locked_at == "2026-07-13 08:00:00"
    assert source.updated_at == "2026-07-13 08:05:00"


def test_document_lock_sources_are_deterministic_and_deduplicate_input_ids(db):
    ids = _seed(db)
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    _insert_lock(db, contract_id=ids["c2"], staff_id=ids["staff2"])
    sources = AgendaSourceRepository(db).list_document_lock_sources(
        [ids["c1"], ids["c2"], ids["c1"]]
    )
    assert [source.contract_no for source in sources] == ["C-1", "C-2"]
    assert len(sources) == 2


def test_document_lock_empty_ids_perform_no_query(db):
    repo = AgendaSourceRepository(db)
    trace: list[str] = []
    db.conn.set_trace_callback(trace.append)
    try:
        assert repo.list_document_lock_sources([]) == ()
    finally:
        db.conn.set_trace_callback(None)
    assert trace == []


def test_document_lock_read_path_is_read_only(db):
    ids = _seed(db)
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    repo = AgendaSourceRepository(db)
    before_changes = db.conn.total_changes
    before_transaction = db.conn.in_transaction
    trace: list[str] = []
    db.conn.set_trace_callback(trace.append)
    try:
        sources = repo.list_document_lock_sources([ids["c1"]])
    finally:
        db.conn.set_trace_callback(None)
    assert sources
    assert db.conn.total_changes == before_changes
    assert db.conn.in_transaction == before_transaction
    assert trace
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in trace)


def test_load_personal_sources_contains_all_source_families_with_one_platform_lookup(db, monkeypatch):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-all")
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    repo = AgendaSourceRepository(db)
    original = repo._platform_names_by_contract
    calls: list[tuple[int, ...]] = []

    def counted(contract_ids):
        calls.append(tuple(contract_ids))
        return original(contract_ids)

    monkeypatch.setattr(repo, "_platform_names_by_contract", counted)
    bundle = repo.load_personal_sources([ids["c1"]])
    assert bundle.calendar
    assert bundle.returned_shares
    assert bundle.document_locks
    assert calls == [(ids["c1"],)]


def test_activity_valid_rows_and_exact_metadata(db):
    ids = _seed(db)
    update_id = _insert_activity(
        db,
        contract_id=ids["c1"],
        action="contract_updated",
        created_at="2026-07-13 10:00:00",
        actor=" Actor Name ",
        source=" Save Contract ",
        device_name=" DEVICE-1 ",
        message=" Changed dates ",
        before={"completion_date": "2026-07-01", "acceptance_date": None},
        after={"completion_date": "2026-07-02", "acceptance_date": "2026-07-03"},
    )
    status_id = _insert_activity(
        db,
        contract_id=ids["c1"],
        action="contract_status_changed",
        created_at="2026-07-13 11:00:00",
        before={"status": "Açık"},
        after={"status": "Kapalı"},
    )

    sources = AgendaSourceRepository(db).list_activity_sources([ids["c1"]])
    assert [source.log_id for source in sources] == [status_id, update_id]
    status, update = sources
    assert status.action == "contract_status_changed"
    assert update.action == "contract_updated"
    assert update.contract_id == ids["c1"]
    assert update.created_at == "2026-07-13 10:00:00"
    assert update.actor_name == "Actor Name"
    assert update.device_name == "DEVICE-1"
    assert update.log_source == "Save Contract"
    assert update.message == "Changed dates"
    assert dict(update.before_values) == {"completion_date": "2026-07-01", "acceptance_date": None}
    assert dict(update.after_values) == {"completion_date": "2026-07-02", "acceptance_date": "2026-07-03"}
    assert update.contract_no == "C-2"
    assert update.contract_type == "Ana"
    assert update.platform == "alpha / Zulu"


@pytest.mark.parametrize(
    "action",
    ["contract_created", "system_updated", "delivery_updated", "documents_locked", "unsupported_action"],
)
def test_activity_action_whitelist_excludes_unsupported_rows(db, action):
    ids = _seed(db)
    _insert_activity(db, contract_id=ids["c1"], action=action)
    assert AgendaSourceRepository(db).list_activity_sources([ids["c1"]]) == ()


@pytest.mark.parametrize(
    ("entity_type", "entity_id"),
    [
        ("system", None),
        ("contract", ""),
        ("contract", "abc"),
        ("contract", "1x"),
        ("contract", "01"),
    ],
)
def test_activity_requires_exact_contract_entity_identity(db, entity_type, entity_id):
    ids = _seed(db)
    value = entity_id
    if value == "1x":
        value = f"{ids['c1']}x"
    elif value == "01":
        value = f"0{ids['c1']}"
    _insert_activity(
        db,
        contract_id=ids["c1"],
        entity_type=entity_type,
        entity_id=value,
        contract_no="C-2",
    )
    assert AgendaSourceRepository(db).list_activity_sources([ids["c1"]]) == ()


def test_activity_contract_no_never_resolves_identity_and_duplicate_numbers_stay_exact(db):
    ids = _seed(db)
    with db.tx():
        db.conn.execute("UPDATE contracts SET contract_no='C-2' WHERE id=?", (ids["c2"],))
    _insert_activity(db, contract_id=ids["c1"], entity_id="", contract_no="C-2")
    first = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-13 12:00:00")
    second = _insert_activity(db, contract_id=ids["c2"], created_at="2026-07-13 13:00:00")

    scoped = AgendaSourceRepository(db).list_activity_sources([ids["c1"]])
    assert [source.log_id for source in scoped] == [first]
    all_sources = AgendaSourceRepository(db).list_activity_sources([ids["c1"], ids["c2"]])
    assert [source.log_id for source in all_sources] == [second, first]
    assert [source.contract_id for source in all_sources] == [ids["c2"], ids["c1"]]


@pytest.mark.parametrize(
    ("raw_before", "raw_after"),
    [
        ("", "{}"),
        ("{}", ""),
        ("{broken", "{}"),
        ("{}", "{broken"),
        ("[]", "{}"),
        ("{}", "[]"),
        ("1", "{}"),
        ("{}", "true"),
    ],
)
def test_activity_json_policy_skips_empty_invalid_array_and_scalar(db, raw_before, raw_after):
    ids = _seed(db)
    _insert_activity(
        db,
        contract_id=ids["c1"],
        raw_before_json=raw_before,
        raw_after_json=raw_after,
    )
    assert AgendaSourceRepository(db).list_activity_sources([ids["c1"]]) == ()


def test_activity_valid_json_object_is_accepted_without_parsing_payload_or_message(db):
    ids = _seed(db)
    log_id = _insert_activity(
        db,
        contract_id=ids["c1"],
        before={"completion_date": "old"},
        after={"completion_date": "new"},
        message='{"status":"fake"}',
        payload_json='{"completion_date":"fake"}',
    )
    source = AgendaSourceRepository(db).list_activity_sources([ids["c1"]])[0]
    assert source.log_id == log_id
    assert dict(source.before_values) == {"completion_date": "old"}
    assert dict(source.after_values) == {"completion_date": "new"}
    assert source.message == '{"status":"fake"}'


def test_activity_cutoff_and_order_are_strict_and_deterministic(db):
    ids = _seed(db)
    old_id = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-05 11:59:59")
    equal_id = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-05 12:00:00")
    first_new = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-06 12:00:00")
    second_new = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-06 12:00:00")
    latest = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-07 12:00:00")
    repo = AgendaSourceRepository(db)

    expected = [latest, second_new, first_new]
    assert [source.log_id for source in repo.list_activity_sources(
        [ids["c1"]], activity_since=datetime(2026, 7, 5, 12, 0, 0)
    )] == expected
    assert [source.log_id for source in repo.list_activity_sources(
        [ids["c1"]], activity_since=" 2026-07-05 12:00:00 "
    )] == expected
    assert old_id not in expected and equal_id not in expected


def test_activity_empty_ids_duplicate_input_and_read_only_contract(db):
    ids = _seed(db)
    log_id = _insert_activity(db, contract_id=ids["c1"])
    repo = AgendaSourceRepository(db)
    trace: list[str] = []
    db.conn.set_trace_callback(trace.append)
    try:
        assert repo.list_activity_sources([]) == ()
    finally:
        db.conn.set_trace_callback(None)
    assert trace == []

    before_changes = db.conn.total_changes
    before_transaction = db.conn.in_transaction
    trace = []
    db.conn.set_trace_callback(trace.append)
    try:
        sources = repo.list_activity_sources([ids["c1"], ids["c1"]])
    finally:
        db.conn.set_trace_callback(None)
    assert [source.log_id for source in sources] == [log_id]
    assert db.conn.total_changes == before_changes
    assert db.conn.in_transaction == before_transaction
    assert trace
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in trace)
    activity_selects = [statement for statement in trace if "FROM activity_logs AS l" in statement]
    assert len(activity_selects) == 1
    assert all(" staff " not in statement.lower() for statement in activity_selects)


def test_activity_bundle_preserves_all_families_and_forwards_cutoff_once(db, monkeypatch):
    ids = _seed(db)
    _insert_share(db, contract_id=ids["c1"], package_id="pkg-activity-bundle")
    _insert_lock(db, contract_id=ids["c1"], staff_id=ids["staff1"])
    log_id = _insert_activity(db, contract_id=ids["c1"], created_at="2026-07-13 10:00:00")
    repo = AgendaSourceRepository(db)
    platform_calls: list[tuple[int, ...]] = []
    activity_calls: list[object] = []
    original_platform = repo._platform_names_by_contract
    original_activity = repo._list_activity_sources

    def counted_platform(contract_ids):
        platform_calls.append(tuple(contract_ids))
        return original_platform(contract_ids)

    def counted_activity(contract_ids, platforms, *, activity_since=None):
        activity_calls.append(activity_since)
        return original_activity(contract_ids, platforms, activity_since=activity_since)

    monkeypatch.setattr(repo, "_platform_names_by_contract", counted_platform)
    monkeypatch.setattr(repo, "_list_activity_sources", counted_activity)
    cutoff = datetime(2026, 7, 5, 12, 0, 0)
    bundle = repo.load_personal_sources([ids["c1"]], activity_since=cutoff)
    assert bundle.calendar
    assert bundle.returned_shares
    assert bundle.document_locks
    assert [source.log_id for source in bundle.activities] == [log_id]
    assert platform_calls == [(ids["c1"],)]
    assert activity_calls == [cutoff]


def test_load_personal_sources_empty_contract_ids_is_query_free(db):
    repo = AgendaSourceRepository(db)
    trace: list[str] = []
    db.conn.set_trace_callback(trace.append)
    try:
        assert repo.load_personal_sources([], activity_since=datetime(2026, 7, 5)) == AgendaSourceBundle()
    finally:
        db.conn.set_trace_callback(None)
    assert trace == []
