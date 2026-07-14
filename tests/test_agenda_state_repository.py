from __future__ import annotations

import pytest

from src.services.agenda_state_repository import AgendaStateRepository
from src.services.sts_database import STSDatabase


@pytest.fixture
def agenda_db(tmp_path):
    db = STSDatabase(tmp_path / "agenda-state.sts", source="Agenda State Tests")
    try:
        yield db
    finally:
        db.close()


def _create_staff(db: STSDatabase, suffix: str) -> int:
    with db.tx():
        cursor = db.conn.execute(
            """
            INSERT INTO staff(device_name,full_name,password_hash,role,is_active,created_at,updated_at)
            VALUES(?,?,?,?,1,'2026-07-10 12:00:00','2026-07-10 12:00:00')
            """,
            (f"agenda-device-{suffix}", f"Agenda Staff {suffix}", "test-hash", "personnel"),
        )
    return int(cursor.lastrowid)


def test_get_states_empty_keys_returns_empty_dict(agenda_db):
    staff_id = _create_staff(agenda_db, "empty")
    repo = AgendaStateRepository(agenda_db)

    assert repo.get_states(staff_id, []) == {}


def test_mark_seen_creates_state_row(agenda_db):
    staff_id = _create_staff(agenda_db, "seen-create")
    repo = AgendaStateRepository(agenda_db)

    state = repo.mark_seen(
        staff_id,
        "deadline:contract:42",
        "UPCOMING_30",
        seen_at="2026-07-10 12:00:00",
    )

    assert state.staff_id == staff_id
    assert state.agenda_key == "deadline:contract:42"
    assert state.seen_at == "2026-07-10 12:00:00"
    assert state.seen_version == "UPCOMING_30"
    assert state.created_at == "2026-07-10 12:00:00"
    assert state.updated_at == "2026-07-10 12:00:00"


def test_get_states_batches_multiple_keys(agenda_db):
    staff_id = _create_staff(agenda_db, "batch")
    repo = AgendaStateRepository(agenda_db)
    repo.mark_seen(staff_id, "agenda:key:one", "V1", seen_at="2026-07-10 12:00:00")
    repo.mark_seen(staff_id, "agenda:key:two", "V2", seen_at="2026-07-10 12:01:00")

    states = repo.get_states(staff_id, ["agenda:key:one", "agenda:key:two", "agenda:key:one"])

    assert set(states) == {"agenda:key:one", "agenda:key:two"}
    assert states["agenda:key:one"].seen_version == "V1"
    assert states["agenda:key:two"].seen_version == "V2"


def test_get_states_isolates_staff(agenda_db):
    first_staff_id = _create_staff(agenda_db, "isolation-1")
    second_staff_id = _create_staff(agenda_db, "isolation-2")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.mark_seen(first_staff_id, key, "FIRST", seen_at="2026-07-10 12:00:00")
    repo.mark_seen(second_staff_id, key, "SECOND", seen_at="2026-07-10 12:01:00")

    first = repo.get_states(first_staff_id, [key])
    second = repo.get_states(second_staff_id, [key])

    assert first[key].seen_version == "FIRST"
    assert second[key].seen_version == "SECOND"


def test_mark_seen_updates_seen_version(agenda_db):
    staff_id = _create_staff(agenda_db, "seen-update")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.mark_seen(staff_id, key, "UPCOMING_60", seen_at="2026-07-10 12:00:00")

    updated = repo.mark_seen(staff_id, key, "UPCOMING_30", seen_at="2026-07-10 13:00:00")

    assert updated.seen_at == "2026-07-10 13:00:00"
    assert updated.seen_version == "UPCOMING_30"


def test_mark_seen_preserves_snooze_and_dismiss_fields(agenda_db):
    staff_id = _create_staff(agenda_db, "seen-preserve")
    repo = AgendaStateRepository(agenda_db)
    key = "activity:contract:42:status"
    repo.snooze(staff_id, key, "V1", "ATTENTION", "2026-07-11 12:00:00")
    repo.dismiss_event(staff_id, key, "V1", dismissed_at="2026-07-10 12:05:00")

    state = repo.mark_seen(staff_id, key, "V2", seen_at="2026-07-10 12:10:00")

    assert state.snoozed_until == "2026-07-11 12:00:00"
    assert state.snoozed_version == "V1"
    assert state.snoozed_severity == "ATTENTION"
    assert state.dismissed_at == "2026-07-10 12:05:00"
    assert state.dismissed_version == "V1"
    assert state.seen_version == "V2"


def test_snooze_creates_state_and_sets_version_severity_until(agenda_db):
    staff_id = _create_staff(agenda_db, "snooze")
    repo = AgendaStateRepository(agenda_db)

    state = repo.snooze(
        staff_id,
        "deadline:contract:42",
        "CRITICAL_7",
        "CRITICAL",
        "2026-07-11 09:30:00",
    )

    assert state.snoozed_until == "2026-07-11 09:30:00"
    assert state.snoozed_version == "CRITICAL_7"
    assert state.snoozed_severity == "CRITICAL"
    assert state.created_at is not None
    assert state.updated_at is not None


def test_snooze_rejects_empty_severity(agenda_db):
    staff_id = _create_staff(agenda_db, "snooze-severity")
    repo = AgendaStateRepository(agenda_db)

    with pytest.raises(ValueError):
        repo.snooze(staff_id, "deadline:contract:42", "V1", "   ", "2026-07-11 09:30:00")


def test_snooze_rejects_empty_until(agenda_db):
    staff_id = _create_staff(agenda_db, "snooze-until")
    repo = AgendaStateRepository(agenda_db)

    with pytest.raises(ValueError):
        repo.snooze(staff_id, "deadline:contract:42", "V1", "ATTENTION", "   ")


def test_clear_snooze_preserves_seen_state(agenda_db):
    staff_id = _create_staff(agenda_db, "clear")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.mark_seen(staff_id, key, "V1", seen_at="2026-07-10 12:00:00")
    repo.snooze(staff_id, key, "V1", "ATTENTION", "2026-07-11 09:30:00")

    state = repo.clear_snooze(staff_id, key)

    assert state is not None
    assert state.seen_at == "2026-07-10 12:00:00"
    assert state.seen_version == "V1"
    assert state.snoozed_until is None
    assert state.snoozed_version == ""
    assert state.snoozed_severity == ""


def test_clear_snooze_missing_row_does_not_create_state(agenda_db):
    staff_id = _create_staff(agenda_db, "clear-missing")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:404"

    assert repo.clear_snooze(staff_id, key) is None
    assert repo.get_states(staff_id, [key]) == {}


def test_dismiss_event_sets_dismissed_fields(agenda_db):
    staff_id = _create_staff(agenda_db, "dismiss")
    repo = AgendaStateRepository(agenda_db)

    state = repo.dismiss_event(
        staff_id,
        "activity:contract:42:status",
        "V3",
        dismissed_at="2026-07-10 12:30:00",
    )

    assert state.dismissed_at == "2026-07-10 12:30:00"
    assert state.dismissed_version == "V3"


def test_touch_presented_sets_first_and_last_on_first_touch(agenda_db):
    staff_id = _create_staff(agenda_db, "touch-first")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"

    repo.touch_presented(staff_id, [key], presented_at="2026-07-10 12:00:00")
    state = repo.get_states(staff_id, [key])[key]

    assert state.first_presented_at == "2026-07-10 12:00:00"
    assert state.last_presented_at == "2026-07-10 12:00:00"


def test_touch_presented_preserves_first_and_updates_last(agenda_db):
    staff_id = _create_staff(agenda_db, "touch-update")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.touch_presented(staff_id, [key], presented_at="2026-07-10 12:00:00")

    repo.touch_presented(staff_id, [key], presented_at="2026-07-10 13:00:00")
    state = repo.get_states(staff_id, [key])[key]

    assert state.first_presented_at == "2026-07-10 12:00:00"
    assert state.last_presented_at == "2026-07-10 13:00:00"


def test_touch_presented_preserves_seen_and_snooze_state(agenda_db):
    staff_id = _create_staff(agenda_db, "touch-preserve")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.mark_seen(staff_id, key, "V1", seen_at="2026-07-10 11:00:00")
    repo.snooze(staff_id, key, "V1", "ATTENTION", "2026-07-11 09:30:00")

    repo.touch_presented(staff_id, [key], presented_at="2026-07-10 12:00:00")
    state = repo.get_states(staff_id, [key])[key]

    assert state.seen_at == "2026-07-10 11:00:00"
    assert state.seen_version == "V1"
    assert state.snoozed_until == "2026-07-11 09:30:00"
    assert state.snoozed_version == "V1"
    assert state.snoozed_severity == "ATTENTION"


def test_touch_presented_deduplicates_input_keys(agenda_db):
    staff_id = _create_staff(agenda_db, "touch-dedupe")
    repo = AgendaStateRepository(agenda_db)
    first = "agenda:key:first"
    second = "agenda:key:second"

    repo.touch_presented(
        staff_id,
        [first, first, " agenda:key:second ", second],
        presented_at="2026-07-10 12:00:00",
    )

    states = repo.get_states(staff_id, [first, second])
    row_count = agenda_db.conn.execute(
        "SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=?",
        (staff_id,),
    ).fetchone()[0]
    assert set(states) == {first, second}
    assert int(row_count) == 2


def test_staff_delete_cascades_agenda_state(agenda_db):
    staff_id = _create_staff(agenda_db, "cascade")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"
    repo.mark_seen(staff_id, key, "V1", seen_at="2026-07-10 12:00:00")

    with agenda_db.tx():
        agenda_db.conn.execute("DELETE FROM staff WHERE id=?", (staff_id,))

    row = agenda_db.conn.execute(
        "SELECT 1 FROM staff_agenda_state WHERE staff_id=? AND agenda_key=?",
        (staff_id, key),
    ).fetchone()
    assert row is None


def test_repository_mutation_rolls_back_with_outer_db_transaction(agenda_db):
    staff_id = _create_staff(agenda_db, "rollback")
    repo = AgendaStateRepository(agenda_db)
    key = "deadline:contract:42"

    with pytest.raises(RuntimeError):
        with agenda_db.tx():
            repo.mark_seen(
                staff_id,
                key,
                "V1",
                seen_at="2026-07-10 12:00:00",
            )
            raise RuntimeError("rollback")

    assert repo.get_states(staff_id, [key]) == {}
