# -*- coding: utf-8 -*-
"""Lightweight, file-based performance telemetry for STS.

The tracker is intentionally independent from an open SQLite connection so it can
measure database opening, migrations and worker-thread operations safely.  Every
record is tagged with the source STS path, which prevents metrics from different
STS files in the same folder from being mixed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, Optional

OP_EXCEL_LOAD = "excel_load"
OP_CACHE_BUILD = "cache_build"
OP_CONTRACT_LIST_LOAD = "contract_list_load"
OP_CONTRACT_OPEN = "contract_open"
OP_DB_OPEN = "db_open"
OP_CONTRACT_SAVE = "contract_save"
OP_CONTRACT_DELETE = "contract_delete"
OP_COMPONENT_SAVE = "component_save"
OP_USER_SAVE = "user_save"

LOG_SCHEMA_VERSION = 2
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
DEFAULT_MIN_SAMPLE_COUNT = 3

OPERATION_CATALOG: Dict[str, Dict[str, Any]] = {
    OP_DB_OPEN: {
        "label": "STS bağlantısı",
        "description": "SQLite bağlantısı ve veri yapısı hazırlığı.",
        "warn_ms": 1000.0,
        "critical_ms": 2500.0,
    },
    OP_CONTRACT_LIST_LOAD: {
        "label": "Sözleşme listesi",
        "description": "Ana sözleşme indeksinin hazırlanması.",
        "warn_ms": 700.0,
        "critical_ms": 1500.0,
    },
    OP_CONTRACT_OPEN: {
        "label": "Sözleşme açma",
        "description": "Sözleşme, sistem ve teslimat detaylarının yüklenmesi.",
        "warn_ms": 800.0,
        "critical_ms": 1500.0,
    },
    OP_CONTRACT_SAVE: {
        "label": "Sözleşme kaydetme",
        "description": "Sözleşme yapısının güvenli şekilde kaydedilmesi.",
        "warn_ms": 1200.0,
        "critical_ms": 2500.0,
    },
    OP_CONTRACT_DELETE: {
        "label": "Sözleşme silme",
        "description": "Sözleşme ve bağlı kayıtların silinmesi.",
        "warn_ms": 1000.0,
        "critical_ms": 2200.0,
    },
    OP_COMPONENT_SAVE: {
        "label": "Bileşen kaydetme",
        "description": "Bileşen tanımlarının kaydedilmesi.",
        "warn_ms": 1000.0,
        "critical_ms": 2200.0,
    },
    OP_USER_SAVE: {
        "label": "Kullanıcı kaydetme",
        "description": "Kullanıcı tanımlarının kaydedilmesi.",
        "warn_ms": 1000.0,
        "critical_ms": 2200.0,
    },
    OP_EXCEL_LOAD: {
        "label": "Excel yükleme",
        "description": "Excel veri kaynağının yüklenmesi.",
        "warn_ms": 5000.0,
        "critical_ms": 15000.0,
    },
    OP_CACHE_BUILD: {
        "label": "Önbellek hazırlama",
        "description": "Uygulama önbelleğinin hazırlanması.",
        "warn_ms": 700.0,
        "critical_ms": 1500.0,
    },
}

_DEFAULT_OPERATION = {
    "label": "Diğer işlem",
    "description": "Tanımlı olmayan performans ölçümü.",
    "warn_ms": 1000.0,
    "critical_ms": 3000.0,
}

_write_lock = threading.Lock()
_session_id = uuid.uuid4().hex[:16]


def _log_path(data_path: Path | str) -> Path:
    """Return the shared diagnostics log path for the data-file folder."""
    from src.config.app_config import LOG_FOLDER_NAME

    p = Path(data_path)
    log_dir = p.parent / LOG_FOLDER_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    new_path = log_dir / "perf.jsonl"

    # Preserve the legacy per-file log once.  New records contain a source key,
    # so a shared file remains safe even when multiple STS files share a folder.
    old_path = p.parent / (p.stem + "_perf.jsonl")
    if old_path.exists() and old_path != new_path:
        try:
            old_content = old_path.read_text(encoding="utf-8")
            if old_content.strip():
                with open(new_path, "a", encoding="utf-8") as stream:
                    stream.write(old_content)
                    if not old_content.endswith("\n"):
                        stream.write("\n")
            old_path.unlink()
        except OSError:
            # A legacy migration problem must not break the application.
            pass

    return new_path


def _normalized_path(path: Path | str) -> str:
    p = Path(path).expanduser()
    try:
        text = str(p.resolve())
    except OSError:
        text = str(p.absolute())
    return os.path.normcase(text)


def source_path_key(path: Path | str) -> str:
    return hashlib.sha256(_normalized_path(path).encode("utf-8", errors="replace")).hexdigest()[:20]


def operation_info(operation: str) -> Dict[str, Any]:
    op = str(operation or "unknown")
    info = dict(_DEFAULT_OPERATION)
    info.update(OPERATION_CATALOG.get(op, {}))
    info["operation"] = op
    if op not in OPERATION_CATALOG:
        info["label"] = op.replace("_", " ").strip().title() or _DEFAULT_OPERATION["label"]
    return info


def _finite_duration(value: Any) -> Optional[float]:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(duration) or duration < 0:
        return None
    return duration


def _rotate_if_needed(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
            return
        for index in range(LOG_BACKUP_COUNT, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            target = path.with_name(f"{path.name}.{index + 1}")
            if index == LOG_BACKUP_COUNT and source.exists():
                source.unlink()
            elif source.exists():
                source.replace(target)
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        # Rotation is best effort. Appending to the current file may still work.
        pass


def record(
    op: str,
    data_path: Path | str,
    duration_ms: float,
    success: bool = True,
    meta: Optional[Dict[str, Any]] = None,
) -> bool:
    """Append one normalized measurement.

    Returns ``True`` when the record was persisted.  Callers intentionally do
    not need to react to a telemetry failure, but tests and diagnostics can.
    """
    duration = _finite_duration(duration_ms)
    if duration is None:
        return False

    path = Path(data_path)
    metadata = dict(meta or {})
    # Reserved fields are owned by the tracker and cannot be overwritten by meta.
    for reserved in {
        "schema_version", "ts", "op", "duration_ms", "success",
        "source_path_key", "source_file", "session_id", "pid", "thread",
    }:
        metadata.pop(reserved, None)

    entry: Dict[str, Any] = {
        "schema_version": LOG_SCHEMA_VERSION,
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "op": str(op or "unknown"),
        "duration_ms": round(duration, 3),
        "success": bool(success),
        "source_path_key": source_path_key(path),
        "source_file": path.name,
        "session_id": _session_id,
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        **metadata,
    }

    try:
        with _write_lock:
            log_path = _log_path(path)
            _rotate_if_needed(log_path)
            with open(log_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return True
    except OSError:
        return False


@contextmanager
def measure(
    op: str,
    data_path: Path | str,
    meta: Optional[Dict[str, Any]] = None,
) -> Generator[None, None, None]:
    started = time.perf_counter()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        record(
            op,
            data_path,
            (time.perf_counter() - started) * 1000.0,
            success=success,
            meta=meta,
        )


def _parse_timestamp(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _range_start(range_key: str, now: datetime) -> Optional[datetime]:
    key = str(range_key or "all").strip().lower()
    if key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "24h":
        return now - timedelta(hours=24)
    if key == "7d":
        return now - timedelta(days=7)
    if key == "30d":
        return now - timedelta(days=30)
    return None


def _record_matches_source(
    record_data: Dict[str, Any],
    data_path: Path,
    expected_key: str,
    allow_legacy: bool,
) -> bool:
    record_key = str(record_data.get("source_path_key") or "").strip()
    if record_key:
        return record_key == expected_key

    source_file = str(record_data.get("source_file") or "").strip()
    if source_file:
        return source_file.casefold() == data_path.name.casefold()

    return allow_legacy


def _legacy_records_are_unambiguous(data_path: Path) -> bool:
    try:
        sts_files = [item for item in data_path.parent.glob("*.sts") if item.is_file()]
        return len(sts_files) <= 1
    except OSError:
        return False


def load_records_with_status(
    data_path: Path | str,
    last_n: int = 5000,
    range_key: str = "all",
) -> Dict[str, Any]:
    """Read, validate and source-filter performance records."""
    path = Path(data_path)
    log_path = _log_path(path)
    result: Dict[str, Any] = {
        "records": [],
        "log_path": str(log_path),
        "invalid_lines": 0,
        "read_error": "",
        "legacy_records_included": False,
    }
    if not log_path.exists():
        return result

    expected_key = source_path_key(path)
    allow_legacy = _legacy_records_are_unambiguous(path)
    now = datetime.now().astimezone()
    range_start = _range_start(range_key, now)
    records: list[Dict[str, Any]] = []

    try:
        with open(log_path, encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    result["invalid_lines"] += 1
                    continue
                if not isinstance(item, dict):
                    result["invalid_lines"] += 1
                    continue
                if not _record_matches_source(item, path, expected_key, allow_legacy):
                    continue
                if not item.get("source_path_key"):
                    result["legacy_records_included"] = True
                duration = _finite_duration(item.get("duration_ms"))
                if duration is None:
                    result["invalid_lines"] += 1
                    continue
                item["duration_ms"] = duration
                item["success"] = bool(item.get("success", True))
                timestamp = _parse_timestamp(item.get("ts"))
                if range_start is not None and (timestamp is None or timestamp < range_start):
                    continue
                records.append(item)
    except OSError as exc:
        result["read_error"] = str(exc)
        return result

    if last_n and int(last_n) > 0:
        records = records[-int(last_n):]
    result["records"] = records
    return result


def load_records(data_path: Path | str, last_n: int = 500, range_key: str = "all") -> list:
    return load_records_with_status(data_path, last_n=last_n, range_key=range_key)["records"]


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * max(0.0, min(1.0, quantile))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def classify_duration(operation: str, duration_ms: Any) -> str:
    duration = _finite_duration(duration_ms)
    if duration is None:
        return "unknown"
    info = operation_info(operation)
    if duration >= float(info["critical_ms"]):
        return "critical"
    if duration >= float(info["warn_ms"]):
        return "warning"
    return "ok"


def classify_summary(operation: str, p95_ms: Any, count: int) -> str:
    if int(count or 0) < DEFAULT_MIN_SAMPLE_COUNT:
        return "insufficient"
    return classify_duration(operation, p95_ms)


def compute_stats(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for item in records:
        if not isinstance(item, dict):
            continue
        duration = _finite_duration(item.get("duration_ms"))
        if duration is None:
            continue
        normalized = dict(item)
        normalized["duration_ms"] = duration
        groups[str(item.get("op") or "unknown")].append(normalized)

    stats: Dict[str, Dict[str, Any]] = {}
    for operation, items in groups.items():
        values = sorted(float(item["duration_ms"]) for item in items)
        failures = sum(1 for item in items if not bool(item.get("success", True)))
        successes = len(items) - failures
        last_item = items[-1]
        p50 = _percentile(values, 0.50)
        p95 = _percentile(values, 0.95)
        info = operation_info(operation)
        stats[operation] = {
            **info,
            "count": len(values),
            "successes": successes,
            "failures": failures,
            "failure_rate": round((failures / len(values)) * 100.0, 2) if values else 0.0,
            "avg_ms": round(sum(values) / len(values), 3),
            "min_ms": round(values[0], 3),
            "max_ms": round(values[-1], 3),
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "last_ms": round(float(last_item["duration_ms"]), 3),
            "last_success": bool(last_item.get("success", True)),
            "last_ts": str(last_item.get("ts") or ""),
            "status": classify_summary(operation, p95, len(values)),
        }
    return stats


def sqlite_disk_usage(data_path: Path | str) -> Dict[str, int]:
    path = Path(data_path)

    def size_of(candidate: Path) -> int:
        try:
            return int(candidate.stat().st_size) if candidate.exists() else 0
        except OSError:
            return 0

    main_bytes = size_of(path)
    wal_bytes = size_of(path.with_name(path.name + "-wal"))
    shm_bytes = size_of(path.with_name(path.name + "-shm"))
    return {
        "main_bytes": main_bytes,
        "wal_bytes": wal_bytes,
        "shm_bytes": shm_bytes,
        "total_bytes": main_bytes + wal_bytes + shm_bytes,
    }


def build_report(
    data_path: Path | str,
    range_key: str = "7d",
    last_n: int = 5000,
) -> Dict[str, Any]:
    load_status = load_records_with_status(data_path, last_n=last_n, range_key=range_key)
    records = list(load_status["records"])
    stats = compute_stats(records)
    total = len(records)
    failures = sum(1 for item in records if not bool(item.get("success", True)))

    slowest_operation = ""
    slowest_ratio = -1.0
    for operation, item in stats.items():
        warn_ms = max(1.0, float(item.get("warn_ms") or 1.0))
        ratio = float(item.get("p95_ms") or 0.0) / warn_ms
        if ratio > slowest_ratio:
            slowest_ratio = ratio
            slowest_operation = operation

    return {
        "records": list(reversed(records)),  # newest first for the UI
        "stats": stats,
        "disk_usage": sqlite_disk_usage(data_path),
        "summary": {
            "measurement_count": total,
            "failure_count": failures,
            "failure_rate": round((failures / total) * 100.0, 2) if total else 0.0,
            "slowest_operation": slowest_operation,
        },
        "log_status": {
            key: value
            for key, value in load_status.items()
            if key != "records"
        },
    }


def file_size_mb(data_path: Path | str) -> float:
    return round(sqlite_disk_usage(data_path)["main_bytes"] / 1024 / 1024, 2)
