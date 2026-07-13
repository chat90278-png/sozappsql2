from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.services import perf_tracker


def test_records_are_isolated_by_sts_source(tmp_path: Path):
    first = tmp_path / "first.sts"
    second = tmp_path / "second.sts"
    first.write_bytes(b"SQLite format 3\x00")
    second.write_bytes(b"SQLite format 3\x00")

    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_OPEN,
        first,
        125.5,
        meta={"contract_no": "A-1"},
    )
    assert perf_tracker.record(
        perf_tracker.OP_CONTRACT_OPEN,
        second,
        930.0,
        meta={"contract_no": "B-1"},
    )

    first_records = perf_tracker.load_records(first, last_n=20)
    second_records = perf_tracker.load_records(second, last_n=20)

    assert len(first_records) == 1
    assert first_records[0]["contract_no"] == "A-1"
    assert first_records[0]["source_path_key"] == perf_tracker.source_path_key(first)

    assert len(second_records) == 1
    assert second_records[0]["contract_no"] == "B-1"
    assert second_records[0]["source_path_key"] == perf_tracker.source_path_key(second)


def test_compute_stats_reports_success_latency_and_failures_separately():
    records = [
        {
            "op": perf_tracker.OP_CONTRACT_SAVE,
            "duration_ms": duration,
            "success": duration != 50,
            "ts": f"2026-07-13T08:00:{index:02d}+03:00",
        }
        for index, duration in enumerate([10, 20, 30, 40, 50])
    ]

    stat = perf_tracker.compute_stats(records)[perf_tracker.OP_CONTRACT_SAVE]

    assert stat["count"] == 5
    assert stat["latency_count"] == 4
    assert stat["successes"] == 4
    assert stat["failures"] == 1
    assert stat["failure_rate"] == 20.0
    assert stat["avg_ms"] == 25.0
    assert stat["p50_ms"] == 25.0
    assert stat["p95_ms"] == 38.5
    assert stat["failed_avg_ms"] == 50.0
    assert stat["last_ms"] == 50.0
    assert stat["last_success"] is False
    assert stat["status"] == "warning"


def test_all_failed_operation_has_failed_status():
    records = [
        {
            "op": perf_tracker.OP_CONTRACT_OPEN,
            "duration_ms": duration,
            "success": False,
            "ts": f"2026-07-13T08:00:{index:02d}+03:00",
        }
        for index, duration in enumerate([900, 1100, 1300])
    ]

    stat = perf_tracker.compute_stats(records)[perf_tracker.OP_CONTRACT_OPEN]

    assert stat["successes"] == 0
    assert stat["failures"] == 3
    assert stat["status"] == "failed"
    assert stat["failed_avg_ms"] == 1100.0


def test_summary_status_requires_enough_samples():
    assert (
        perf_tracker.classify_summary(
            perf_tracker.OP_CONTRACT_OPEN,
            5000,
            2,
        )
        == "insufficient"
    )
    assert (
        perf_tracker.classify_summary(
            perf_tracker.OP_CONTRACT_OPEN,
            900,
            3,
        )
        == "warning"
    )
    assert (
        perf_tracker.classify_summary(
            perf_tracker.OP_CONTRACT_OPEN,
            1600,
            3,
        )
        == "critical"
    )


def test_range_filter_excludes_old_records(tmp_path: Path):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    log_path = perf_tracker._log_path(sts_path)
    now = datetime.now().astimezone()
    old = now - timedelta(days=10)

    rows = [
        {
            "schema_version": 2,
            "ts": old.isoformat(timespec="milliseconds"),
            "op": perf_tracker.OP_DB_OPEN,
            "duration_ms": 100,
            "success": True,
            "source_path_key": perf_tracker.source_path_key(sts_path),
            "source_file": sts_path.name,
        },
        {
            "schema_version": 2,
            "ts": now.isoformat(timespec="milliseconds"),
            "op": perf_tracker.OP_DB_OPEN,
            "duration_ms": 120,
            "success": True,
            "source_path_key": perf_tracker.source_path_key(sts_path),
            "source_file": sts_path.name,
        },
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    records = perf_tracker.load_records(sts_path, last_n=20, range_key="7d")

    assert len(records) == 1
    assert records[0]["duration_ms"] == 120.0


def test_disk_usage_includes_wal_and_shm(tmp_path: Path):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"x" * 100)
    (tmp_path / "sample.sts-wal").write_bytes(b"x" * 50)
    (tmp_path / "sample.sts-shm").write_bytes(b"x" * 25)

    usage = perf_tracker.sqlite_disk_usage(sts_path)

    assert usage == {
        "main_bytes": 100,
        "wal_bytes": 50,
        "shm_bytes": 25,
        "total_bytes": 175,
    }


def test_versioned_sts_files_share_logical_lineage(tmp_path: Path):
    first = tmp_path / "STS-A1__v001__2026-07-13_08-00.sts"
    second = tmp_path / "STS-A1__v002__2026-07-13_09-00.sts"
    first.write_bytes(b"SQLite format 3\x00")
    second.write_bytes(b"SQLite format 3\x00")

    assert perf_tracker.source_path_key(first) != perf_tracker.source_path_key(second)
    assert perf_tracker.source_lineage_key(first) == perf_tracker.source_lineage_key(second)

    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, first, 100)
    records = perf_tracker.load_records(second, last_n=20)

    assert len(records) == 1
    assert records[0]["source_file"] == first.name


def test_loader_reads_rotated_log_backups(tmp_path: Path, monkeypatch):
    sts_path = tmp_path / "sample.sts"
    sts_path.write_bytes(b"SQLite format 3\x00")
    monkeypatch.setattr(perf_tracker, "MAX_LOG_BYTES", 1)

    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, 100)
    assert perf_tracker.record(perf_tracker.OP_DB_OPEN, sts_path, 200)

    status = perf_tracker.load_records_with_status(sts_path, last_n=20)

    assert [row["duration_ms"] for row in status["records"]] == [100.0, 200.0]
    assert status["log_files_read"] == 2
