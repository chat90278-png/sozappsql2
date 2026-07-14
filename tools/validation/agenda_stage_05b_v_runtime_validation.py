#!/usr/bin/env python3
"""Stage 5B-V Windows/PySide6 runtime differential validator.

This validator is intentionally temporary.  It materializes the exact baseline
and exact candidate trees, runs static/runtime/JUnit/provenance checks, writes
all evidence into _validation/artifact, and exits non-zero unless every mandatory
gate passes.  It never mutates product sources in either materialized tree.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

BASELINE = "e1ed9a66318e19178f132602d3114a97880fa27f"
CANDIDATE = "b6fe76d06abab31d70e7b129f4efdbe5bbb07472"
FEATURE = "b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98"
MERGE_BASE = "2931fa267560397d4d849d6365acde504f376775"
BRANCH = "integration/gundemim-current-main-20260713"
ARTIFACT_NAME = "agenda-stage-05b-v-evidence"
TEMP_PATHS = [
    ".github/workflows/agenda-stage-05b-v-runtime-validation.yml",
    "tools/validation/agenda_stage_05b_v_runtime_validation.py",
]
TARGETED_TESTS = [
    "tests/test_activity_agenda_provider.py",
    "tests/test_agenda_compact_widget.py",
    "tests/test_agenda_context_factory.py",
    "tests/test_agenda_current_main_composition.py",
    "tests/test_agenda_deadline_stage.py",
    "tests/test_agenda_detail_window.py",
    "tests/test_agenda_keys.py",
    "tests/test_agenda_lifecycle.py",
    "tests/test_agenda_models.py",
    "tests/test_agenda_presentation.py",
    "tests/test_agenda_schema_v18_integration.py",
    "tests/test_agenda_source_repository.py",
    "tests/test_agenda_startup_upgrade_integration.py",
    "tests/test_agenda_state_repository.py",
    "tests/test_deadline_agenda_provider.py",
    "tests/test_document_lock_agenda_provider.py",
    "tests/test_main_page_agenda_integration.py",
    "tests/test_personal_agenda_facade.py",
    "tests/test_returned_share_agenda_provider.py",
    "tests/test_staff_agenda_service.py",
    "tests/test_sts_database_transactions.py",
    "tests/test_sts_schema_upgrade.py",
    "tests/test_sts_schema_upgrade_gate.py",
    "tests/test_sts_schema_upgrade_orchestration.py",
    "tests/test_unknown_date_agenda_provider.py",
    "tests/test_analysis_qt_integration.py",
    "tests/test_analysis_builder_qt.py",
    "tests/test_contract_edit_timing_runtime_fix.py",
    "tests/test_sd_edit_timing_runtime_fix.py",
    "tests/test_contract_save_telemetry_runtime_fix.py",
    "tests/test_delivery_schedule_slicer_runtime_fix.py",
]
PROTECTED = [
    "app.py",
    "requirements.txt",
    "src/auth.py",
    "src/ui/main_window.py",
    "src/ui/main_page_final_window.py",
    "src/ui/widgets/contract_status_summary.py",
    "src/ui/widgets/corner_menu_layer.py",
    "src/ui/contract/contract_work_window.py",
    "src/workers/sts_load_worker.py",
]

@dataclass
class CmdResult:
    returncode: int
    stdout: str
    stderr: str

class GateFailure(RuntimeError):
    pass

ROOT = Path.cwd()
VALIDATION = ROOT / "_validation"
BASELINE_DIR = VALIDATION / "baseline"
CANDIDATE_DIR = VALIDATION / "candidate"
ARTIFACT = Path(os.environ.get("STAGE05BV_ARTIFACT_DIR", str(VALIDATION / "artifact")))
DECISIONS: list[str] = []


def write(name: str, data: str) -> None:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    (ARTIFACT / name).write_text(data, encoding="utf-8")


def write_json(name: str, data: Any) -> None:
    write(name, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def run(cmd: list[str], cwd: Path = ROOT, check: bool = False, env: dict[str, str] | None = None) -> CmdResult:
    merged_env = os.environ.copy()
    merged_env.update({"QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1", "PYTHONHASHSEED": "0"})
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged_env)
    result = CmdResult(proc.returncode, proc.stdout, proc.stderr)
    if check and proc.returncode != 0:
        raise GateFailure(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    return result


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    result = run(["git", *args], cwd=cwd, check=check)
    return result.stdout.strip()


def preflight() -> None:
    lines = []
    branch = git("branch", "--show-current")
    lines.append(f"branch={branch}")
    if branch != BRANCH:
        raise GateFailure(f"wrong branch: {branch}")
    for obj in [BASELINE, CANDIDATE, FEATURE, MERGE_BASE]:
        git("cat-file", "-e", f"{obj}^{{commit}}")
        lines.append(f"object {obj}=present")
    git("merge-base", "--is-ancestor", CANDIDATE, "HEAD")
    diff = git("diff", "--name-only", CANDIDATE, "HEAD").splitlines()
    lines.append("candidate_to_bootstrap_diff=" + json.dumps(diff))
    if sorted(diff) != sorted(TEMP_PATHS):
        raise GateFailure(f"unexpected bootstrap diff: {diff}")
    actual_merge_base = git("merge-base", BASELINE, CANDIDATE)
    lines.append(f"merge_base={actual_merge_base}")
    if actual_merge_base != BASELINE:
        raise GateFailure(f"unexpected candidate/main merge-base {actual_merge_base}")
    ahead_behind = git("rev-list", "--left-right", "--count", f"{BASELINE}...{CANDIDATE}")
    lines.append(f"ahead_behind={ahead_behind}")
    merge_tree = git("merge-tree", MERGE_BASE, BASELINE, FEATURE, check=True)
    write("merge-tree.txt", merge_tree + "\n")
    lowered = merge_tree.lower()
    if any(marker in merge_tree for marker in ["<<<<<<<", ">>>>>>>", "======="]) or "conflict" in lowered:
        raise GateFailure("historical merge-tree indicates conflict")
    write("preflight.txt", "\n".join(lines) + "\n")
    write_json("refs.json", {"baseline": BASELINE, "candidate": CANDIDATE, "feature": FEATURE, "merge_base": MERGE_BASE, "branch": BRANCH})


def materialize() -> None:
    if VALIDATION.exists():
        shutil.rmtree(VALIDATION)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    git("worktree", "prune")
    git("worktree", "add", "--detach", str(BASELINE_DIR), BASELINE)
    git("worktree", "add", "--detach", str(CANDIDATE_DIR), CANDIDATE)
    for path in [BASELINE_DIR, CANDIDATE_DIR]:
        if git("status", "--porcelain", cwd=path):
            raise GateFailure(f"dirty worktree: {path}")


def install_requirements(tree: Path) -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=tree, check=True)
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=tree, check=True)
    run([sys.executable, "-m", "pip", "install", "pytest"], cwd=tree, check=True)


def environment_and_requirements() -> None:
    install_requirements(CANDIDATE_DIR)
    parity = {
        "baseline_sha256": sha256(BASELINE_DIR / "requirements.txt"),
        "candidate_sha256": sha256(CANDIDATE_DIR / "requirements.txt"),
        "equal": (BASELINE_DIR / "requirements.txt").read_bytes() == (CANDIDATE_DIR / "requirements.txt").read_bytes(),
    }
    write_json("requirements-parity.json", parity)
    if not parity["equal"]:
        raise GateFailure("requirements mismatch")
    versions = [f"platform={platform.platform()}", f"python={sys.version}", f"architecture={platform.architecture()}"]
    for code in ["import pip; print('pip=' + pip.__version__)", "import pytest; print('pytest=' + pytest.__version__)", "from PySide6 import QtCore; print('pyside6=' + QtCore.__version__); print('qt=' + QtCore.qVersion())"]:
        res = run([sys.executable, "-c", code], cwd=CANDIDATE_DIR)
        versions.append(res.stdout.strip() or res.stderr.strip())
    write("environment.txt", "\n".join(versions) + "\n")


def compile_tree(tree: Path, name: str) -> None:
    res = run([sys.executable, "-m", "compileall", "-q", "src", "tests"], cwd=tree)
    write(f"{name}-compile.txt", f"exit={res.returncode}\nSTDOUT\n{res.stdout}\nSTDERR\n{res.stderr}")
    if res.returncode != 0:
        raise GateFailure(f"{name} compile failed")


def assert_source_invariants() -> None:
    db = (CANDIDATE_DIR / "src/services/sts_database.py").read_text(encoding="utf-8")
    up = (CANDIDATE_DIR / "src/services/sts_schema_upgrade.py").read_text(encoding="utf-8")
    gate = (CANDIDATE_DIR / "src/services/sts_schema_upgrade_gate.py").read_text(encoding="utf-8")
    main = (CANDIDATE_DIR / "src/ui/main_window.py").read_text(encoding="utf-8")
    checks = {
        "CURRENT_SCHEMA_VERSION_18": "CURRENT_SCHEMA_VERSION = 18" in db,
        "helper_only_database": "def ensure_staff_agenda_state_schema" in db and "def ensure_staff_agenda_state_schema" not in up,
        "no_database_module_monkey_patch": "_sts_database_module" not in up,
        "migration_step": "v17_to_v18_staff_agenda_state" in up,
        "fingerprint_max_18": "FINGERPRINT_MAX_VERSION = 18" in gate,
        "agenda_detail_key": '"agenda:detail"' in main or "'agenda:detail'" in main,
        "open_or_raise": "open_or_raise_tool_window" in main,
        "close_cleanup": 'close_tool_window("agenda:detail")' in main or "close_tool_window('agenda:detail')" in main,
        "qt_obj_alive": "qt_obj_alive" in main,
        "ensure_after_staff": db.find("ensure_staff_table(self.conn)") < db.find("ensure_staff_agenda_state_schema(self.conn)"),
    }
    write_json("source-invariants.json", checks)
    if not all(checks.values()):
        raise GateFailure(f"source invariant failure: {checks}")


def parse_junit(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = root.findall(".//testcase")
    return {
        "tests": sum(int(s.get("tests", 0)) for s in suites) or len(cases),
        "failures": sum(int(s.get("failures", 0)) for s in suites),
        "errors": sum(int(s.get("errors", 0)) for s in suites),
        "skipped": sum(int(s.get("skipped", 0)) for s in suites),
        "nodes": sorted(f"{c.get('classname','')}::{c.get('name','')}" for c in cases),
        "failure_nodes": sorted(f"{c.get('classname','')}::{c.get('name','')}" for c in cases if c.find("failure") is not None or c.find("error") is not None),
        "skipped_nodes": sorted(f"{c.get('classname','')}::{c.get('name','')}" for c in cases if c.find("skipped") is not None),
    }


def pytest_run(tree: Path, args: list[str], xml_name: str, log_name: str) -> dict[str, Any]:
    xml_path = ARTIFACT / xml_name
    res = run([sys.executable, "-m", "pytest", "-q", *args, f"--junitxml={xml_path}"], cwd=tree)
    write(log_name, f"exit={res.returncode}\nSTDOUT\n{res.stdout}\nSTDERR\n{res.stderr}")
    if res.returncode != 0:
        raise GateFailure(f"pytest failed: {xml_name}")
    parsed = parse_junit(xml_path)
    if parsed["failures"] or parsed["errors"] or parsed["skipped"]:
        raise GateFailure(f"non-clean junit: {xml_name}: {parsed}")
    return parsed


def run_smokes() -> None:
    expectations = [("tests/smoke_sts_agenda_schema.py", "agenda-schema-smoke.txt", ["agenda_schema=PASS", "schema_version=18"]), ("tests/smoke_sts_database.py", "database-smoke.txt", ["ok"])]
    for script, out, expected in expectations:
        res = run([sys.executable, script], cwd=CANDIDATE_DIR)
        text = f"exit={res.returncode}\nSTDOUT\n{res.stdout}\nSTDERR\n{res.stderr}"
        write(out, text)
        if res.returncode != 0 or not all(item in res.stdout for item in expected):
            raise GateFailure(f"smoke failed: {script}")


@contextlib.contextmanager
def candidate_imports():
    old_path = sys.path[:]
    sys.path.insert(0, str(CANDIDATE_DIR))
    try:
        yield
    finally:
        sys.path[:] = old_path
        for name in list(sys.modules):
            if name == "src" or name.startswith("src."):
                sys.modules.pop(name, None)


def schema_runtime() -> None:
    evidence: dict[str, Any] = {}
    with candidate_imports(), tempfile.TemporaryDirectory() as td:
        from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase, ensure_staff_agenda_state_schema, read_sts_schema_version
        from src.services import sts_schema_upgrade as upgrade
        tmp = Path(td)
        fresh = tmp / "fresh.db"
        db = STSDatabase(str(fresh)); db.close()
        conn = sqlite3.connect(fresh)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(staff_agenda_state)")]
        fk = [tuple(r) for r in conn.execute("PRAGMA foreign_key_list(staff_agenda_state)")]
        idx = {r[1]: [c[2] for c in conn.execute(f"PRAGMA index_info({r[1]})")] for r in conn.execute("PRAGMA index_list(staff_agenda_state)")}
        evidence["fresh_v18"] = {"version": read_sts_schema_version(fresh), "columns": cols, "foreign_keys": fk, "indexes": idx, "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0], "fk_check": conn.execute("PRAGMA foreign_key_check").fetchall(), "agenda_items_absent": conn.execute("SELECT name FROM sqlite_master WHERE name='agenda_items'").fetchone() is None}
        conn.close()
        tx = tmp / "tx.db"; conn = sqlite3.connect(tx); conn.execute("PRAGMA foreign_keys=ON"); conn.execute("CREATE TABLE staff(id INTEGER PRIMARY KEY)"); conn.execute("INSERT INTO staff(id) VALUES (1)"); conn.execute("BEGIN")
        ensure_staff_agenda_state_schema(conn); in_tx = conn.in_transaction; second = ensure_staff_agenda_state_schema(conn); conn.rollback(); conn.close()
        evidence["helper_transaction"] = {"in_transaction_after_helper": in_tx, "second_call": second}
        malformed = tmp / "malformed.db"; conn = sqlite3.connect(malformed); conn.execute("CREATE TABLE staff(id INTEGER PRIMARY KEY)"); conn.execute("CREATE TABLE staff_agenda_state(staff_id INTEGER)")
        try:
            ensure_staff_agenda_state_schema(conn); raised = False
        except RuntimeError:
            raised = True
        conn.close(); evidence["malformed"] = {"runtime_error": raised}
        v17 = tmp / "v17.db"; d = STSDatabase(str(v17)); d.close(); conn = sqlite3.connect(v17)
        for name in list(idx): conn.execute(f"DROP INDEX IF EXISTS {name}")
        conn.execute("DROP TABLE IF EXISTS staff_agenda_state"); conn.execute("UPDATE meta SET value='17' WHERE key='schema_version'"); conn.commit(); conn.close()
        result = upgrade.upgrade_database(v17)
        evidence["v17_to_v18"] = {"steps": [getattr(s, "name", str(s)) for s in getattr(result, "applied_migrations", [])], "version": read_sts_schema_version(v17), "current": CURRENT_SCHEMA_VERSION}
        before = sorted(tmp.glob("v17*.bak*")); result2 = upgrade.upgrade_database(v17); after = sorted(tmp.glob("v17*.bak*"))
        evidence["current_noop"] = {"steps": [getattr(s, "name", str(s)) for s in getattr(result2, "applied_migrations", [])], "new_backup": len(after) > len(before)}
        future = tmp / "future.db"; shutil.copy2(v17, future); conn = sqlite3.connect(future); conn.execute("UPDATE meta SET value='19' WHERE key='schema_version'"); conn.commit(); conn.close()
        try:
            upgrade.upgrade_database(future); future_failed = False
        except Exception:
            future_failed = True
        evidence["future_v19"] = {"fail_closed": future_failed, "version": read_sts_schema_version(future)}
        cascade = tmp / "cascade.db"; d = STSDatabase(str(cascade)); c = d.conn; c.execute("INSERT INTO staff(id, name) VALUES (?, ?)", (9001, "Agenda Runtime")); c.execute("INSERT INTO staff_agenda_state(staff_id, agenda_key, is_dismissed) VALUES (?,?,?)", (9001, "x", 1)); c.commit(); d.close()
        c = sqlite3.connect(cascade); c.execute("PRAGMA foreign_keys=ON"); preserved = c.execute("SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=9001").fetchone()[0]; c.execute("DELETE FROM staff WHERE id=9001"); c.commit(); cascaded = c.execute("SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=9001").fetchone()[0]; c.close()
        evidence["cascade_reopen"] = {"preserved": preserved, "after_delete": cascaded}
    write_json("schema-runtime.json", evidence)
    required = evidence["fresh_v18"]["version"] == 18 and evidence["malformed"]["runtime_error"] and evidence["future_v19"]["fail_closed"] and evidence["cascade_reopen"]["after_delete"] == 0
    if not required:
        raise GateFailure("schema runtime matrix failed")


def qt_runtime() -> None:
    evidence: dict[str, Any] = {}
    with candidate_imports():
        from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
        from PySide6.QtCore import QTimer
        app = QApplication.instance() or QApplication([])
        from src.ui.main_page_analysis_window import MainWindow
        h = object.__new__(MainWindow)
        h.contract_status_card = QWidget(); h.contract_status_layout = QVBoxLayout(h.contract_status_card)
        h._cal_widget = QWidget(h.contract_status_card); h.contract_status_layout.addWidget(h._cal_widget)
        h.upcoming_scroll = None
        h.contract_status_widget = None
        h.agenda_compact_widget = None
        h._agenda_refresh_timer = QTimer()
        h.current_staff = {"id": 1}
        h.has_permission = lambda permission: permission == "view_contracts"
        h.is_sts_mode = lambda: True
        h.open_analysis_center = lambda *a: None
        h._open_agenda_details = lambda *a: None
        h._open_agenda_contract = lambda *a: None
        h._agenda_mark_seen = lambda *a: None
        h._agenda_snooze = lambda *a: None
        h.refresh_agenda = lambda *a: None
        MainWindow._install_contract_status_widget(h); status1 = h.contract_status_widget
        MainWindow._install_contract_status_widget(h); status2 = h.contract_status_widget
        MainWindow._install_personal_agenda_widget(h); agenda1 = h.agenda_compact_widget; timer = h._agenda_refresh_timer
        MainWindow._install_personal_agenda_widget(h); agenda2 = h.agenda_compact_widget
        layout_widgets = [h.contract_status_layout.itemAt(i).widget().__class__.__name__ for i in range(h.contract_status_layout.count())]
        evidence["widget_install"] = {"status_reused": status1 is status2, "agenda_reused": agenda1 is agenda2, "timer_unchanged": timer is h._agenda_refresh_timer, "layout": layout_widgets}
        reg = object.__new__(MainWindow); reg._tool_windows = {}; reg._tool_window_chips = {}; reg._agenda_detail_window = None
        calls = {"factory": 0}
        def factory():
            calls["factory"] += 1
            return QWidget()
        first = MainWindow.open_or_raise_tool_window(reg, "agenda:detail", "Agenda", factory)
        second = MainWindow.open_or_raise_tool_window(reg, "agenda:detail", "Agenda", factory)
        MainWindow.close_tool_window(reg, "agenda:detail")
        third = MainWindow.open_or_raise_tool_window(reg, "agenda:detail", "Agenda", factory)
        evidence["registry"] = {"same_on_second_open": first is second, "factory_calls_after_second": calls["factory"], "closed_removed": "agenda:detail" not in reg._tool_windows, "new_after_reopen": third is not first, "key_present": "agenda:detail" in reg._tool_windows}
        app.processEvents()
    write_json("qt-runtime.json", evidence)
    if not (evidence["widget_install"]["status_reused"] and evidence["widget_install"]["agenda_reused"] and evidence["registry"]["same_on_second_open"]):
        raise GateFailure("qt runtime matrix failed")


def junit_differential(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    bnodes, cnodes = set(baseline["nodes"]), set(candidate["nodes"])
    diff = {"baseline_totals": {k: baseline[k] for k in ["tests", "failures", "errors", "skipped"]}, "candidate_totals": {k: candidate[k] for k in ["tests", "failures", "errors", "skipped"]}, "baseline_only": sorted(bnodes - cnodes), "candidate_only": sorted(cnodes - bnodes), "baseline_failure_error_nodes": baseline["failure_nodes"], "candidate_failure_error_nodes": candidate["failure_nodes"], "skipped_nodes": sorted(set(baseline["skipped_nodes"]) | set(candidate["skipped_nodes"]))}
    write_json("junit-differential.json", diff)
    write("junit-differential.txt", textwrap.dedent(f"""\
        baseline totals: {diff['baseline_totals']}
        candidate totals: {diff['candidate_totals']}
        baseline_only: {diff['baseline_only']}
        candidate_only: {diff['candidate_only']}
        skipped_nodes: {diff['skipped_nodes']}
        """))
    if diff["baseline_only"] or diff["baseline_failure_error_nodes"] or diff["candidate_failure_error_nodes"] or diff["skipped_nodes"]:
        raise GateFailure("JUnit differential failed")


def protected_source_parity() -> None:
    rows = {}
    for path in PROTECTED:
        b = git("rev-parse", f"{BASELINE}:{path}", check=False)
        c = git("rev-parse", f"{CANDIDATE}:{path}", check=False)
        rows[path] = {"baseline_blob": b, "candidate_blob": c, "identical": b == c}
    unexpected = [p for p in TEMP_PATHS if run(["git", "cat-file", "-e", f"{CANDIDATE}:{p}"]).returncode == 0]
    rows["unexpected_temp_at_candidate"] = unexpected
    write_json("protected-source-parity.json", rows)
    if unexpected:
        raise GateFailure("temporary validation paths exist at candidate exact SHA")


def pr_state() -> None:
    state = {"title": "TEMP VALIDATION: Agenda Stage 5B-V", "base": "main", "head": BRANCH, "draft": True, "automation": "gh cli if available"}
    gh = shutil.which("gh")
    if gh:
        existing = run([gh, "pr", "list", "--base", "main", "--head", BRANCH, "--state", "open", "--json", "number,title,isDraft"]).stdout
        state["existing_open"] = existing
        try:
            existing_items = json.loads(existing or "[]")
        except json.JSONDecodeError:
            existing_items = []
        if existing_items:
            state["selected_pr"] = existing_items[0]
            state["create_skipped"] = "matching open temporary PR already exists"
        else:
            # Repository policy may disallow creation from GITHUB_TOKEN; record outcome, do not reduce validation scope.
            create = run([gh, "pr", "create", "--title", state["title"], "--base", "main", "--head", BRANCH, "--draft", "--body", "Temporary Stage 5B-V validation PR. Do not merge."])
            state["create_exit"] = create.returncode; state["create_stdout"] = create.stdout; state["create_stderr"] = create.stderr
    else:
        state["policy_note"] = "gh CLI unavailable; create/close draft PR manually per prompt."
    write_json("pr-state.json", state)


def main() -> int:
    try:
        preflight(); materialize(); environment_and_requirements(); pr_state()
        compile_tree(BASELINE_DIR, "baseline"); compile_tree(CANDIDATE_DIR, "candidate"); assert_source_invariants()
        baseline = pytest_run(BASELINE_DIR, [], "baseline-full.xml", "baseline-full.log")
        targeted_existing = [p for p in TARGETED_TESTS if (CANDIDATE_DIR / p).exists()]
        missing = sorted(set(TARGETED_TESTS) - set(targeted_existing))
        if missing:
            raise GateFailure(f"missing targeted tests: {missing}")
        pytest_run(CANDIDATE_DIR, targeted_existing, "candidate-targeted.xml", "candidate-targeted.log")
        run_smokes(); schema_runtime(); qt_runtime()
        candidate = pytest_run(CANDIDATE_DIR, [], "candidate-full.xml", "candidate-full.log")
        junit_differential(baseline, candidate); protected_source_parity()
        decision = "STAGE 5B-V INTEGRATION VALIDATION: ACCEPTED\nFINAL MERGE-READINESS AUDIT GATE: OPEN\nMAIN MERGE GATE: CLOSED\n"
        write("decision.txt", decision)
        return 0
    except Exception as exc:
        write("decision.txt", "STAGE 5B-V INTEGRATION VALIDATION: NOT ACCEPTED\nFINAL MERGE-READINESS AUDIT GATE: BLOCKED\nMAIN MERGE GATE: CLOSED\n\n" + repr(exc) + "\n" + traceback.format_exc())
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
