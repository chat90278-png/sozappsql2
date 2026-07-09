from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from analysis_center.analysis_cards import build_dashboard_items
from analysis_center.analysis_dashboard_workspace import DashboardWorkspace
from analysis_center.analysis_data_loader import load_analysis_data
from analysis_center.analysis_deadlines import (
    DeadlineDateStatus,
    build_deadline_rows,
    classify_deadline_date,
    classify_deadline_rows,
)
from analysis_center.analysis_metrics import compute_metrics
from analysis_center.analysis_registry import DEFAULT_REGISTRY


@pytest.mark.parametrize(
    ("value", "status", "parsed"),
    [
        ("2026-07-09", DeadlineDateStatus.KNOWN, date(2026, 7, 9)),
        (datetime(2026, 7, 9, 12, 30), DeadlineDateStatus.KNOWN, date(2026, 7, 9)),
        ("TBD", DeadlineDateStatus.UNKNOWN, None),
        ("T.B.D.", DeadlineDateStatus.UNKNOWN, None),
        ("2026-TBD-TBD", DeadlineDateStatus.UNKNOWN, None),
        ("Tarih belirlenecek", DeadlineDateStatus.UNKNOWN, None),
        ("Belirsiz", DeadlineDateStatus.UNKNOWN, None),
        ("Unknown", DeadlineDateStatus.UNKNOWN, None),
        ("not-a-date", DeadlineDateStatus.UNKNOWN, None),
        ("", DeadlineDateStatus.MISSING, None),
        (None, DeadlineDateStatus.MISSING, None),
        ("-", DeadlineDateStatus.MISSING, None),
    ],
)
def test_deadline_date_classification(value, status, parsed):
    result = classify_deadline_date(value)
    assert result.status == status
    assert result.parsed_date == parsed


def _canonical_data():
    return {
        "contracts": [
            {
                "id": 1,
                "platform": "AKINCI",
                "contract_no": "C-1",
                "contract_type": "Ana Sözleşme",
                "status": "Devam Ediyor",
                "completion_date": "2026-07-20",
                "acceptance_date": "",
            }
        ],
        "systems": [
            {
                "id": 2,
                "contract_id": 1,
                "platform": "AKINCI",
                "contract_no": "C-1",
                "name": "Sistem 1",
                "status": "Başlanmadı",
                "completion_date": "2026-07-01",
                "acceptance_date": "",
            }
        ],
        "acceptances": [
            {
                "id": 3,
                "contract_id": 1,
                "system_id": 2,
                "platform": "AKINCI",
                "contract_no": "C-1",
                "system_name": "Sistem 1",
                "name": "Teslimat 1",
                "status": "Başlanmadı",
                "planned_acceptance_date": "TBD",
                "planned_delivery_date": "2026-08-15",
                "completion_date": "2026-09-01",
                "acceptance_date": "",
                "planned_total": 10,
                "delivered_total": 0,
            },
            {
                "id": 4,
                "contract_id": 1,
                "system_id": 2,
                "platform": "AKINCI",
                "contract_no": "C-1",
                "system_name": "Sistem 1",
                "name": "Teslimat 2",
                "status": "Başlanmadı",
                "planned_acceptance_date": "",
                "planned_delivery_date": "2026-07-25",
                "completion_date": "2026-09-10",
                "acceptance_date": "",
                "planned_total": 5,
                "delivered_total": 0,
            },
        ],
        "platforms": [],
        "components": [],
        "users": [],
        "tags": [],
        "deadlines": [],
    }


def test_canonical_deadline_builder_covers_contract_system_and_planned_acceptance_sources_once():
    rows = build_deadline_rows(_canonical_data())
    by_id = {row["event_id"]: row for row in rows}

    assert set(by_id) == {"contract:1", "system:2", "acceptance:3", "acceptance:4"}
    assert by_id["contract:1"]["date_field"] == "completion_date"
    assert by_id["system:2"]["date_field"] == "completion_date"
    assert by_id["acceptance:3"]["date_field"] == "planned_acceptance_date"
    assert by_id["acceptance:3"]["raw_date_value"] == "TBD"
    assert by_id["acceptance:4"]["date_field"] == "planned_delivery_date"
    assert by_id["acceptance:4"]["raw_date_value"] == "2026-07-25"
    assert len([row for row in rows if row["event_id"] == "acceptance:3"]) == 1


def test_missing_termin_does_not_create_event():
    data = _canonical_data()
    data["contracts"][0]["completion_date"] = ""
    data["systems"][0]["completion_date"] = None
    data["acceptances"] = []
    assert build_deadline_rows(data) == []


def test_deadline_classification_is_deterministic_and_excludes_completed_records_from_active_buckets():
    today = date(2026, 7, 8)
    rows = [
        {"event_id": "future", "entity": "contract", "due_date": "2026-07-20", "status": "Open", "completed": False},
        {"event_id": "past", "entity": "system", "due_date": "2026-07-01", "status": "Open", "completed": False},
        {"event_id": "today", "entity": "contract", "due_date": "2026-07-08", "status": "Open", "completed": False},
        {"event_id": "unknown", "entity": "acceptance", "due_date": "TBD", "status": "Open", "completed": False},
        {"event_id": "done-future", "entity": "contract", "due_date": "2026-07-30", "status": "Tamamlandı", "completed": True},
        {"event_id": "done-past", "entity": "contract", "due_date": "2026-06-30", "status": "Tamamlandı", "completed": True},
        {"event_id": "done-unknown", "entity": "acceptance", "due_date": "TBD", "status": "Tamamlandı", "completed": True},
        {"event_id": "missing", "entity": "contract", "due_date": "", "status": "Open", "completed": False},
    ]

    first = classify_deadline_rows(rows, today=today, upcoming_days=60)
    second = classify_deadline_rows(rows, today=today, upcoming_days=60)

    assert first == second
    assert [row["event_id"] for row in first["all"]] == [
        "done-past",
        "past",
        "today",
        "future",
        "done-future",
        "done-unknown",
        "unknown",
    ]
    assert [row["due_date"] for row in first["upcoming"]] == ["2026-07-08", "2026-07-20"]
    assert [row["due_date"] for row in first["past"]] == ["2026-07-01"]
    assert [row["event_id"] for row in first["unknown"]] == ["unknown"]


def test_metrics_and_deadline_cards_expose_unknown_count_rows_and_raw_value():
    data = _canonical_data()
    data["deadlines"] = build_deadline_rows(data)
    metrics = compute_metrics(data, today=date(2026, 7, 8), upcoming_days=60)

    assert metrics["upcoming_deadline_count"] == 2
    assert metrics["past_deadline_count"] == 1
    assert metrics["unknown_deadline_count"] == 1
    assert metrics["unknown_deadlines"][0]["raw_date_value"] == "TBD"
    assert metrics["unknown_deadlines"][0]["date_field"] == "planned_acceptance_date"

    deadline_item = next(item for item in build_dashboard_items(metrics) if item.item_id == "deadline_analysis")
    cards = {card.card_id: card for card in deadline_item.cards}
    assert cards["deadline_upcoming_count"].value == 2
    assert cards["deadline_past_count"].value == 1
    assert cards["deadline_unknown_count"].value == 1
    assert cards["deadline_unknown_table"].data[0]["raw_date_value"] == "TBD"
    assert cards["deadline_unknown_table"].columns == [
        "entity",
        "name",
        "platform",
        "contract_no",
        "date_field",
        "raw_date_value",
        "status",
    ]

    workspace = DashboardWorkspace(source_key="test")
    assert workspace.pin(cards["deadline_unknown_count"]) is True
    assert workspace.pin(cards["deadline_unknown_table"]) is True
    resolved, missing = workspace.resolve_cards([deadline_item])
    assert missing == []
    resolved_by_id = {card.card_id: card for card in resolved}
    assert resolved_by_id["deadline_unknown_count"].resolved_layout_hints().default_h == 2
    assert resolved_by_id["deadline_unknown_table"].resolved_layout_hints().default_h == 5


def test_deadline_empty_state_description_distinguishes_unknown_from_no_active_termin():
    unknown_metrics = compute_metrics(
        {"contracts": [], "systems": [], "acceptances": [], "platforms": [], "components": [], "users": [], "tags": [], "deadlines": [{"event_id": "u", "entity": "contract", "due_date": "TBD", "status": "Open"}]},
        today=date(2026, 7, 8),
    )
    unknown_item = next(item for item in build_dashboard_items(unknown_metrics) if item.item_id == "deadline_analysis")
    assert unknown_item.description == "Tarihi belirlenmemiş termin kayıtları bulundu."

    empty_metrics = compute_metrics(
        {"contracts": [], "systems": [], "acceptances": [], "platforms": [], "components": [], "users": [], "tags": [], "deadlines": []},
        today=date(2026, 7, 8),
    )
    empty_item = next(item for item in build_dashboard_items(empty_metrics) if item.item_id == "deadline_analysis")
    assert empty_item.description == "Bu STS dosyasında analiz edilebilir aktif termin kaydı bulunamadı."


def test_sqlite_loader_reads_planned_acceptance_date_into_canonical_acceptances_and_deadlines(tmp_path):
    db = tmp_path / "termin.sts"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE platforms(id INTEGER PRIMARY KEY, name TEXT, display_name TEXT, is_active INTEGER, sort_order INTEGER);
        CREATE TABLE contracts(id INTEGER PRIMARY KEY, platform_id INTEGER, contract_no TEXT, contract_type TEXT, type_display TEXT, status TEXT, signed_date TEXT, t0_date TEXT, t0_months INTEGER, completion_date TEXT, acceptance_date TEXT, content TEXT, is_main INTEGER);
        CREATE TABLE systems(id INTEGER PRIMARY KEY, contract_id INTEGER, name TEXT, status TEXT, completion_date TEXT, acceptance_date TEXT, sort_order INTEGER, payload_json TEXT);
        CREATE TABLE deliveries(id INTEGER PRIMARY KEY, contract_id INTEGER, system_id INTEGER, name TEXT, status TEXT, planned_acceptance_date TEXT, acceptance_date TEXT, sort_order INTEGER, payload_json TEXT);
        CREATE TABLE delivery_components(delivery_id INTEGER, planned REAL, delivered REAL);
        """
    )
    conn.execute("INSERT INTO platforms VALUES(1,'AKINCI','AKINCI',1,1)")
    conn.execute("INSERT INTO contracts VALUES(1,1,'C-1','Ana','Ana','Başlanmadı','','',0,'TBD','','',1)")
    conn.execute("INSERT INTO systems VALUES(1,1,'Sistem 1','Başlanmadı','','',1,'{}')")
    conn.execute("INSERT INTO deliveries VALUES(1,1,1,'Teslimat 1','Başlanmadı','2026-07-09','',1,'{}')")
    conn.execute("INSERT INTO deliveries VALUES(2,1,1,'Teslimat 2','Başlanmadı','TBD','',2,'{}')")
    conn.execute("INSERT INTO delivery_components VALUES(1,5,0)")
    conn.execute("INSERT INTO delivery_components VALUES(2,5,0)")
    conn.commit()
    conn.close()

    data = load_analysis_data(db, use_sample=False)
    assert [item["planned_acceptance_date"] for item in data["acceptances"]] == ["2026-07-09", "TBD"]
    by_id = {row["event_id"]: row for row in data["deadlines"]}
    assert by_id["acceptance:1"]["date_field"] == "planned_acceptance_date"
    assert by_id["acceptance:1"]["due_date"] == "2026-07-09"
    assert by_id["acceptance:2"]["date_status"] == "unknown"

    metrics = compute_metrics(data, today=date(2026, 7, 8), upcoming_days=60)
    assert metrics["upcoming_deadline_count"] == 1
    assert metrics["unknown_deadline_count"] == 2


def test_registry_exposes_planned_acceptance_and_deadline_classification_fields():
    assert DEFAULT_REGISTRY.get_field("acceptances", "planned_acceptance_date").field_type == "date"
    assert DEFAULT_REGISTRY.get_field("deadlines", "date_status").field_type == "category"
    assert DEFAULT_REGISTRY.get_field("deadlines", "raw_date_value").field_type == "text"
