from __future__ import annotations

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
