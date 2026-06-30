# -*- coding: utf-8 -*-
"""src/services/perf_tracker.py — Performans ölçüm modülü."""
from __future__ import annotations
import json, os, threading, time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, Optional

OP_EXCEL_LOAD      = "excel_load"
OP_CACHE_BUILD     = "cache_build"
OP_CONTRACT_LIST_LOAD = "contract_list_load"
OP_CONTRACT_OPEN   = "contract_open"
OP_DB_OPEN         = "db_open"
OP_CONTRACT_SAVE   = "contract_save"
OP_CONTRACT_DELETE = "contract_delete"
OP_COMPONENT_SAVE  = "component_save"
OP_USER_SAVE       = "user_save"

_write_lock = threading.Lock()

def _log_path(excel_path: Path) -> Path:
    from src.config.app_config import LOG_FOLDER_NAME

    p = Path(excel_path)
    log_dir = p.parent / LOG_FOLDER_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    new_path = log_dir / "perf.jsonl"

    # Eski dosyayı bul ve içeriğini yeni dosyaya taşı (bir kez)
    old_path = p.parent / (p.stem + "_perf.jsonl")
    if old_path.exists() and old_path != new_path:
        try:
            old_content = old_path.read_text(encoding="utf-8")
            if old_content.strip():
                with open(new_path, "a", encoding="utf-8") as f:
                    f.write(old_content)
            old_path.unlink()
        except Exception:
            pass

    return new_path

def record(op: str, excel_path: Path, duration_ms: float,
           success: bool = True, meta: Optional[Dict[str, Any]] = None):
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "op": op,
             "duration_ms": round(duration_ms, 1), "success": success, **(meta or {})}
    try:
        with _write_lock:
            with open(_log_path(excel_path), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

@contextmanager
def measure(op: str, excel_path: Path, meta: Optional[Dict[str, Any]] = None) -> Generator:
    t0 = time.perf_counter(); success = True
    try:
        yield
    except Exception:
        success = False; raise
    finally:
        record(op, excel_path, (time.perf_counter() - t0) * 1000, success=success, meta=meta)

def load_records(excel_path: Path, last_n: int = 500) -> list:
    path = _log_path(excel_path)
    if not path.exists(): return []
    records = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: records.append(json.loads(line))
                except Exception: pass
    except Exception:
        return []
    return records[-last_n:]

def compute_stats(records: list) -> Dict[str, dict]:
    from collections import defaultdict
    groups: Dict[str, list] = defaultdict(list)
    failures: Dict[str, int] = defaultdict(int)
    for r in records:
        op = r.get("op", "unknown")
        groups[op].append(r.get("duration_ms", 0))
        if not r.get("success", True): failures[op] += 1
    stats = {}
    for op, values in groups.items():
        stats[op] = {
            "count": len(values), "avg_ms": round(sum(values)/len(values), 1),
            "min_ms": round(min(values), 1), "max_ms": round(max(values), 1),
            "last_ms": round(values[-1], 1), "failures": failures[op],
        }
    return stats

def file_size_mb(excel_path: Path) -> float:
    try: return round(os.path.getsize(excel_path) / 1024 / 1024, 2)
    except Exception: return 0.0
