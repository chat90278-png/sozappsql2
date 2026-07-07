import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.calendar_timing import (
    annotate_calendar_events,
    build_calendar_summary_from_sources,
    calendar_event_counts,
)


def _delivery(delivery_id, planned, acceptance="", status="PLAN", platform="AKINCI"):
    return {
        "row": 100 + delivery_id,
        "delivery_id": delivery_id,
        "platform": platform,
        "no": f"S-{delivery_id}",
        "type": "Teslimat",
        "system_label": "SYS",
        "title": f"S-{delivery_id} · SYS / D-{delivery_id}",
        "status": status,
        "completion_date": "",
        "acceptance_date": acceptance,
        "planned_acceptance_date": planned,
        "user": "",
    }


def main():
    today = date(2026, 7, 7)
    system_events = [
        _delivery(1, "TBD"),
        _delivery(2, "2026-07-TBD"),
        _delivery(3, "TBD", platform="BAYRAKTAR"),
        _delivery(4, "2026-07-09"),
        _delivery(5, "2026-07-01"),
        _delivery(6, "2026-07-01", acceptance="2026-07-05"),
        _delivery(7, "2026-07-01", status="Teslim edildi"),
        _delivery(8, "2026-09-07"),
        _delivery(9, "-"),
    ]

    annotated = annotate_calendar_events(system_events, today)
    counts = calendar_event_counts(annotated, year=2026)
    assert counts == {
        "geciken": 1,
        "kritik": 1,
        "tamamlandi": 2,
        "belirsiz": 3,
    }, counts

    # Same helper path used by the mini widget after the DB event-source query.
    mini_counts, events_by_day, summary_events = build_calendar_summary_from_sources([], system_events, today, 2026)
    assert mini_counts == counts
    assert events_by_day == {1: "geciken", 5: "tamamlandi", 9: "kritik"}, events_by_day
    assert len([e for e in summary_events if e["_cls"] == "belirsiz"]) == 3
    assert all(e["platform"] for e in summary_events)
    print("ok")


if __name__ == "__main__":
    main()
