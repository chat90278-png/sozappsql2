from __future__ import annotations

import pytest

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
            "INSERT INTO contracts(platform_id,contract_no,contract_type,status,completion_date,note) VALUES(?,?,?,?,?,?)",
            (p1, "C-2", "Ana", "Açık", "2026-07-20", "n1"),
        ).lastrowid
        c2 = db.conn.execute(
            "INSERT INTO contracts(platform_id,contract_no,contract_type,status,completion_date,note) VALUES(?,?,?,?,?,?)",
            (p2, "C-1", "Ana", "Açık", "TBD", "n2"),
        ).lastrowid
        db.conn.execute("INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,0,1)", (c1, p1))
        db.conn.execute("INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,1,0)", (c1, p2))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,1)", (c1, staff1))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,1)", (c2, staff2))
        db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,is_primary) VALUES(?,?,0)", (c2, inactive))
        s1 = db.conn.execute(
            "INSERT INTO systems(contract_id,platform_id,name,status,completion_date) VALUES(?,?,?,?,?)",
            (c1, p2, "System B", "Açık", "2026-07-15"),
        ).lastrowid
        d1 = db.conn.execute(
            "INSERT INTO deliveries(contract_id,system_id,name,status,planned_acceptance_date) VALUES(?,?,?,?,?)",
            (c1, s1, "Delivery A", "Açık", "2026-07-18"),
        ).lastrowid
    return {
        "staff1": int(staff1), "staff2": int(staff2), "inactive": int(inactive),
        "c1": int(c1), "c2": int(c2), "s1": int(s1), "d1": int(d1),
    }


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


def test_source_repository_does_not_mutate_database(db):
    ids = _seed(db)
    before = db.conn.total_changes
    repo = AgendaSourceRepository(db)
    repo.list_personal_contract_ids(ids["staff1"])
    repo.list_calendar_sources([ids["c1"]])
    assert db.conn.total_changes == before
