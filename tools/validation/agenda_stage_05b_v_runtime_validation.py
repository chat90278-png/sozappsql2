from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


class ValidationFailure(RuntimeError):
    pass


class ValidationRun:
    def __init__(self) -> None:
        self.checks: list[CheckResult] = []

    def check(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            value = fn()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.checks.append(CheckResult(name=name, status="FAIL", detail=detail))
            raise
        detail = "PASS" if value is None else str(value)
        self.checks.append(CheckResult(name=name, status="PASS", detail=detail))
        return value

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValidationFailure(message)


def _run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValidationFailure(
            f"command failed ({completed.returncode}): {' '.join(args)}\n"
            f"stdout={completed.stdout[-2000:]}\n"
            f"stderr={completed.stderr[-2000:]}"
        )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(root: Path) -> str:
    return _run("git", "rev-parse", "HEAD", cwd=root)


def _assert_exact_heads(
    run: ValidationRun,
    baseline_root: Path,
    candidate_root: Path,
    baseline_sha: str,
    candidate_sha: str,
) -> None:
    def check() -> str:
        baseline_head = _git_head(baseline_root)
        candidate_head = _git_head(candidate_root)
        run.require(baseline_head == baseline_sha, f"baseline head mismatch: {baseline_head}")
        run.require(candidate_head == candidate_sha, f"candidate head mismatch: {candidate_head}")
        return f"baseline={baseline_head}; candidate={candidate_head}"

    run.check("exact_git_heads", check)


def _assert_lineage(
    run: ValidationRun,
    candidate_root: Path,
    baseline_sha: str,
    candidate_sha: str,
) -> None:
    def check() -> str:
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", baseline_sha, candidate_sha],
            cwd=candidate_root,
            check=False,
        )
        run.require(completed.returncode == 0, "current main is not an ancestor of candidate")
        parents = _run("git", "rev-list", "--parents", "-n", "1", candidate_sha, cwd=candidate_root).split()
        run.require(len(parents) == 3, f"candidate is not a two-parent merge commit: {parents}")
        run.require(baseline_sha in parents[1:], "current main is not a direct merge parent")
        return f"parents={parents[1:]}"

    run.check("candidate_lineage_and_merge_shape", check)


def _assert_preserved_current_main_files(
    run: ValidationRun,
    baseline_root: Path,
    candidate_root: Path,
) -> None:
    paths = (
        "requirements.txt",
        "analysis_center/analysis_excel_export_qt.py",
        "analysis_center/analysis_qt_window.py",
        "src/ui/widgets/corner_menu_layer.py",
        "src/ui/main_page_final_window.py",
        "src/workers/sts_load_worker.py",
    )

    def check() -> str:
        mismatches: list[str] = []
        for relative in paths:
            baseline = baseline_root / relative
            candidate = candidate_root / relative
            if not baseline.is_file() or not candidate.is_file():
                mismatches.append(f"missing:{relative}")
                continue
            if _sha256(baseline) != _sha256(candidate):
                mismatches.append(relative)
        run.require(not mismatches, f"current-main preservation mismatch: {mismatches}")
        return f"identical={len(paths)} files"

    run.check("current_main_critical_file_preservation", check)


def _assert_static_runtime_contract(run: ValidationRun, candidate_root: Path) -> None:
    def schema_contract() -> str:
        database = (candidate_root / "src/services/sts_database.py").read_text(encoding="utf-8")
        upgrade = (candidate_root / "src/services/sts_schema_upgrade.py").read_text(encoding="utf-8")
        gate = (candidate_root / "src/services/sts_schema_upgrade_gate.py").read_text(encoding="utf-8")
        required_database = (
            "CURRENT_SCHEMA_VERSION = 19",
            "ACTIVITY_LOG_COLUMNS",
            "AGENDA_STATE_COLUMNS",
            "PRIMARY KEY(staff_id, agenda_key)",
            "ON DELETE CASCADE",
            'if _agenda_table_exists(conn, "agenda_items")',
        )
        required_upgrade = (
            "v17_to_v18_activity_history_infrastructure",
            "v18_to_v19_staff_agenda_state",
            "def _migrate_18_to_19",
        )
        required_gate = (
            "_V18_ACTIVITY_COLUMNS",
            "_V19_AGENDA_STATE_COLUMNS",
            "required_primary_keys",
            "required_foreign_keys",
            "required_index_columns",
            'forbidden_tables = ("agenda_items",)',
            "if version >= 18:",
            "if version >= 19:",
        )
        missing = [token for token in required_database if token not in database]
        missing += [token for token in required_upgrade if token not in upgrade]
        missing += [token for token in required_gate if token not in gate]
        run.require(not missing, f"missing schema contract tokens: {missing}")
        return "schema v18 Activity + v19 Agenda contract present"

    def worker_order() -> str:
        source = (candidate_root / "src/workers/sts_load_worker.py").read_text(encoding="utf-8")
        gate_import = "from src.services.sts_schema_upgrade_gate import upgrade_sts_file"
        direct_import = "from src.services.sts_schema_upgrade import upgrade_sts_file"
        run.require(gate_import in source, "startup worker does not import schema gate")
        run.require(direct_import not in source, "startup worker bypasses schema gate")
        upgrade_pos = source.index("upgrade_result = upgrade_sts_file(")
        store_pos = source.index("store = STSStore(")
        finished_pos = source.index("self.finished.emit()")
        run.require(upgrade_pos < store_pos < finished_pos, "startup upgrade/store/finished order changed")
        return "upgrade gate → STSStore verification → finished"

    def ui_contract() -> str:
        source = (candidate_root / "src/ui/main_page_analysis_window.py").read_text(encoding="utf-8")
        required = (
            "self._install_contract_status_widget()",
            "self._install_personal_agenda_widget()",
            '"agenda:detail"',
            "open_or_raise_tool_window",
            "self._reset_agenda_binding()",
            '"report:analysis_center"',
            "CornerMenuOverlay",
            "timer.setSingleShot(True)",
            "timer.setInterval(200)",
        )
        missing = [token for token in required if token not in source]
        run.require(not missing, f"missing UI runtime tokens: {missing}")
        run.require(
            source.index("self._install_contract_status_widget()")
            < source.index("self._install_personal_agenda_widget()"),
            "status/Agenda installation order changed",
        )
        return "status → Agenda → calendar composition and registry hooks present"

    run.check("static_schema_contract", schema_contract)
    run.check("startup_worker_gate_order", worker_order)
    run.check("static_qt_runtime_contract", ui_contract)


def _fresh_database(path: Path) -> None:
    from src.services.sts_database import STSDatabase

    db = STSDatabase(path)
    db.close()


def _downgrade_fresh_v19_to_real_v18(path: Path) -> None:
    _fresh_database(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TABLE IF EXISTS staff_agenda_state")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','18')"
        )
        conn.commit()
    finally:
        conn.close()


def _insert_runtime_staff(conn: sqlite3.Connection, staff_id: int = 101) -> None:
    conn.execute(
        """
        INSERT INTO staff(
            id, device_name, full_name, password_hash, role, is_active
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            staff_id,
            f"stage-05b-v-device-{staff_id}",
            "Stage 5B-V Runtime User",
            "stage-05b-v-hash",
            "personnel",
            1,
        ),
    )


def _assert_schema_runtime(run: ValidationRun, output_dir: Path) -> None:
    from src.services.sts_database import (
        CURRENT_SCHEMA_VERSION,
        STSDatabase,
        STSMigrationError,
        read_sts_schema_version,
    )
    from src.services.sts_schema_upgrade_gate import (
        upgrade_sts_file,
        validate_versioned_schema_fingerprint,
    )

    schema_root = output_dir / "schema-runtime"
    if schema_root.exists():
        shutil.rmtree(schema_root)
    schema_root.mkdir(parents=True)

    def fresh_v19() -> str:
        path = schema_root / "fresh" / "fresh-v19.sts"
        path.parent.mkdir(parents=True)
        _fresh_database(path)
        run.require(CURRENT_SCHEMA_VERSION == 19, f"unexpected current schema: {CURRENT_SCHEMA_VERSION}")
        run.require(read_sts_schema_version(path) == 19, "fresh STS is not v19")
        fingerprint = validate_versioned_schema_fingerprint(path, 19)
        run.require(fingerprint.version == 19, "fresh v19 fingerprint failed")
        conn = sqlite3.connect(path)
        try:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            run.require("staff_agenda_state" in tables, "fresh v19 missing Agenda state")
            run.require("agenda_items" not in tables, "forbidden agenda_items exists")
        finally:
            conn.close()
        return str(path)

    def v18_to_v19() -> str:
        path = schema_root / "upgrade" / "real-v18.sts"
        path.parent.mkdir(parents=True)
        _downgrade_fresh_v19_to_real_v18(path)
        validate_versioned_schema_fingerprint(path, 18)
        result = upgrade_sts_file(path)
        run.require(result.status == "upgraded", f"unexpected status: {result}")
        run.require(result.from_version == 18 and result.to_version == 19, str(result))
        run.require(
            result.applied_migrations == ("v18_to_v19_staff_agenda_state",),
            f"unexpected migrations: {result.applied_migrations}",
        )
        run.require(result.backup_path is not None and result.backup_path.exists(), "migration backup missing")
        run.require(read_sts_schema_version(path) == 19, "upgraded file not v19")
        validate_versioned_schema_fingerprint(path, 19)
        return f"backup={result.backup_path.name}"

    def persistence_and_cascade() -> str:
        path = schema_root / "persistence" / "state.sts"
        path.parent.mkdir(parents=True)
        _fresh_database(path)
        db = STSDatabase(path)
        try:
            db.conn.execute("PRAGMA foreign_keys=ON")
            _insert_runtime_staff(db.conn, 101)
            db.conn.execute(
                """
                INSERT INTO staff_agenda_state(
                    staff_id, agenda_key, seen_at, seen_version, created_at, updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (101, "runtime:key", "2026-07-14 12:00:00", "v1", "2026-07-14 12:00:00", "2026-07-14 12:00:00"),
            )
            db.conn.commit()
        finally:
            db.close()

        reopened = STSDatabase(path)
        try:
            row = reopened.conn.execute(
                "SELECT agenda_key,seen_version FROM staff_agenda_state WHERE staff_id=101"
            ).fetchone()
            run.require(row is not None and tuple(row) == ("runtime:key", "v1"), f"state not persisted: {row}")
            reopened.conn.execute("PRAGMA foreign_keys=ON")
            reopened.conn.execute("DELETE FROM staff WHERE id=101")
            reopened.conn.commit()
            count = int(
                reopened.conn.execute(
                    "SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=101"
                ).fetchone()[0]
            )
            run.require(count == 0, f"cascade did not delete state: {count}")
        finally:
            reopened.close()
        return "persistence=PASS; cascade=PASS"

    def rollback_malformed_v18() -> str:
        path = schema_root / "rollback" / "malformed-v18.sts"
        path.parent.mkdir(parents=True)
        _downgrade_fresh_v19_to_real_v18(path)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE staff_agenda_state(staff_id INTEGER, agenda_key TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
        try:
            upgrade_sts_file(path)
        except STSMigrationError:
            pass
        else:
            raise ValidationFailure("malformed v18 migration unexpectedly succeeded")
        run.require(read_sts_schema_version(path) == 18, "failed migration advanced schema version")
        conn = sqlite3.connect(path)
        try:
            columns = tuple(
                str(row[1])
                for row in conn.execute("PRAGMA table_info(staff_agenda_state)").fetchall()
            )
            indexes = {
                str(row[1])
                for row in conn.execute("PRAGMA index_list(staff_agenda_state)").fetchall()
            }
        finally:
            conn.close()
        run.require(columns == ("staff_id", "agenda_key"), f"malformed table mutated: {columns}")
        run.require("idx_staff_agenda_state_staff" not in indexes, "partial Agenda index survived rollback")
        return "schema_version=18; malformed shape preserved; partial indexes absent"

    def fail_closed_current_and_future() -> str:
        malformed_dir = schema_root / "fail-closed-current"
        malformed_dir.mkdir(parents=True)
        malformed = malformed_dir / "malformed-v19.sts"
        _fresh_database(malformed)
        conn = sqlite3.connect(malformed)
        try:
            conn.execute("DROP TABLE staff_agenda_state")
            conn.execute("CREATE TABLE staff_agenda_state(staff_id INTEGER, agenda_key TEXT)")
            conn.commit()
        finally:
            conn.close()
        try:
            upgrade_sts_file(malformed)
        except STSMigrationError:
            pass
        else:
            raise ValidationFailure("malformed current v19 unexpectedly accepted")
        run.require(read_sts_schema_version(malformed) == 19, "malformed current version changed")
        run.require(not (malformed_dir / "yedekler").exists(), "current malformed file was mutated/backed up")

        future_dir = schema_root / "future"
        future_dir.mkdir(parents=True)
        future = future_dir / "future-v20.sts"
        _fresh_database(future)
        conn = sqlite3.connect(future)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','20')"
            )
            conn.commit()
        finally:
            conn.close()
        try:
            upgrade_sts_file(future)
        except STSMigrationError:
            pass
        else:
            raise ValidationFailure("future v20 unexpectedly accepted")
        run.require(read_sts_schema_version(future) == 20, "future file version changed")
        run.require(not (future_dir / "yedekler").exists(), "future file was backed up or mutated")
        return "malformed current and future schema rejected before mutation"

    run.check("schema_fresh_v19", fresh_v19)
    run.check("schema_real_v18_to_v19_upgrade", v18_to_v19)
    run.check("schema_state_persistence_and_staff_cascade", persistence_and_cascade)
    run.check("schema_migration_rollback_on_malformed_v18", rollback_malformed_v18)
    run.check("schema_fail_closed_current_and_future", fail_closed_current_and_future)


def _process_events(app: Any, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _assert_qt_runtime(run: ValidationRun, output_dir: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from shiboken6 import isValid

    from src.services.sts_store import STSStore
    from src.ui.agenda_compact_widget import AgendaCompactWidget
    from src.ui.agenda_detail_window import AgendaDetailWindow
    from src.ui.main_page_analysis_window import MainWindow

    app = QApplication.instance() or QApplication([])
    runtime_dir = output_dir / "qt-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    database_path = runtime_dir / "runtime.sts"
    if database_path.exists():
        database_path.unlink()

    staff = {
        "id": 501,
        "device_name": "stage-05b-v-qt-device",
        "full_name": "Stage 5B-V Qt User",
        "role": "personnel",
        "is_active": 1,
        "permissions": {"view_contracts"},
    }
    store = STSStore(
        database_path,
        actor_context=staff,
        session_id="stage-05b-v-runtime",
    )
    store.db.conn.execute("PRAGMA foreign_keys=ON")
    _insert_runtime_staff(store.db.conn, 501)
    store.db.conn.commit()

    original_refresh = MainWindow.refresh_agenda
    original_details = MainWindow._open_agenda_details
    calls = {"refresh": 0, "details": 0}

    def counted_refresh(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["refresh"] += 1
        return original_refresh(self, *args, **kwargs)

    def counted_details(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["details"] += 1
        return original_details(self, *args, **kwargs)

    MainWindow.refresh_agenda = counted_refresh
    MainWindow._open_agenda_details = counted_details
    window = None
    try:
        window = MainWindow(
            store=None,
            contract_index=[],
            initial_path=database_path,
            current_staff=staff,
        )
        window.store = store
        window.path = database_path
        window.current_staff = staff
        window.contract_index = []
        window.is_sts_mode = lambda: True
        window.has_permission = lambda _code: True
        _process_events(app)

        def composition_and_idempotency() -> str:
            status = window.contract_status_widget
            agenda = window.agenda_compact_widget
            calendar = window._cal_widget
            timer = window._agenda_refresh_timer
            run.require(all(isValid(obj) for obj in (status, agenda, calendar, timer)), "runtime Qt object invalid")

            for _ in range(3):
                window._install_contract_status_widget()
                window._install_personal_agenda_widget()
            _process_events(app)

            run.require(window.agenda_compact_widget is agenda, "Agenda compact widget was duplicated/replaced")
            run.require(window._agenda_refresh_timer is timer, "Agenda timer was duplicated/replaced")
            compact_widgets = [obj for obj in window.findChildren(AgendaCompactWidget) if isValid(obj)]
            run.require(len(compact_widgets) == 1, f"compact widget count={len(compact_widgets)}")
            agenda_timers = [
                obj
                for obj in window.findChildren(QTimer)
                if isValid(obj)
                and obj.parent() is window
                and obj.isSingleShot()
                and obj.interval() == 200
            ]
            run.require(len(agenda_timers) == 1 and agenda_timers[0] is timer, f"Agenda timer count={len(agenda_timers)}")

            layout = calendar.parentWidget().layout()
            status_index = layout.indexOf(status)
            agenda_index = layout.indexOf(agenda)
            calendar_index = layout.indexOf(calendar)
            run.require(
                0 <= status_index < agenda_index < calendar_index,
                f"header order invalid: status={status_index}, agenda={agenda_index}, calendar={calendar_index}",
            )
            return f"order={status_index}<{agenda_index}<{calendar_index}; compact=1; timer=1"

        def signal_connection_counts() -> str:
            timer = window._agenda_refresh_timer
            agenda = window.agenda_compact_widget
            calls["refresh"] = 0
            timer.timeout.emit()
            _process_events(app)
            run.require(calls["refresh"] == 1, f"timer timeout receiver count={calls['refresh']}")

            calls["details"] = 0
            agenda.open_details_requested.emit()
            _process_events(app)
            run.require(calls["details"] == 1, f"open_details receiver count={calls['details']}")
            detail = window._agenda_detail_window
            run.require(detail is not None and isValid(detail), "detail window did not open from signal")
            return "timer timeout=1 receiver; open_details=1 receiver"

        def detail_registry_reuse_and_reopen() -> str:
            first = window._agenda_detail_window
            run.require(first is not None and isValid(first), "first detail window missing")
            window._open_agenda_details()
            _process_events(app)
            second = window._agenda_detail_window
            run.require(second is first, "agenda:detail registry did not reuse existing window")
            details = [obj for obj in window.findChildren(AgendaDetailWindow) if isValid(obj)]
            run.require(len(details) == 1, f"detail window count after reuse={len(details)}")

            window.close_tool_window("agenda:detail")
            _process_events(app, 8)
            window._agenda_detail_window = None
            window._open_agenda_details()
            _process_events(app)
            reopened = window._agenda_detail_window
            run.require(reopened is not None and isValid(reopened), "detail did not reopen")
            run.require(reopened is not first, "closed detail instance was incorrectly reused")
            return "stable registry reuse=PASS; close/reopen=PASS"

        def file_switch_reset_cleanup() -> str:
            timer = window._agenda_refresh_timer
            timer.start()
            run.require(timer.isActive(), "Agenda timer did not start")
            run.require(window._agenda_detail_window is not None, "detail missing before reset")
            window._reset_agenda_binding()
            _process_events(app, 8)
            run.require(not timer.isActive(), "Agenda timer remained active after reset")
            run.require(window._agenda_detail_window is None, "detail reference survived reset")
            run.require(window._agenda_facade is None, "facade survived reset")
            run.require(window._agenda_bound_db is None, "bound DB survived reset")
            run.require(window._agenda_snapshot is None, "snapshot survived reset")
            run.require(not window.agenda_compact_widget.isVisible(), "compact widget visible after reset")
            return "timer/detail/facade/db/snapshot/widget cleanup=PASS"

        def real_facade_refresh() -> str:
            window.agenda_compact_widget.show()
            calls["refresh"] = 0
            window.refresh_agenda(touch_presented=False)
            _process_events(app)
            run.require(calls["refresh"] == 1, "real facade refresh wrapper count mismatch")
            run.require(window._agenda_facade is not None, "real facade was not bound")
            run.require(window._agenda_bound_db is store.db, "facade bound to wrong database")
            run.require(window._agenda_snapshot is not None, "real facade did not produce snapshot")
            return "real PersonalAgendaFacade load=PASS"

        run.check("qt_status_agenda_calendar_and_idempotency", composition_and_idempotency)
        run.check("qt_single_signal_connections", signal_connection_counts)
        run.check("qt_agenda_detail_registry_reuse_and_reopen", detail_registry_reuse_and_reopen)
        run.check("qt_file_switch_reset_cleanup", file_switch_reset_cleanup)
        run.check("qt_real_facade_refresh", real_facade_refresh)

        def close_cleanup() -> str:
            window._open_agenda_details()
            window._agenda_refresh_timer.start()
            window.close()
            _process_events(app, 10)
            run.require(not window._agenda_refresh_timer.isActive(), "Agenda timer active after MainWindow close")
            run.require(window._agenda_detail_window is None, "detail reference survived MainWindow close")
            return "MainWindow close timer/detail cleanup=PASS"

        run.check("qt_main_window_close_cleanup", close_cleanup)
    finally:
        MainWindow.refresh_agenda = original_refresh
        MainWindow._open_agenda_details = original_details
        if window is not None:
            try:
                window.close()
                window.deleteLater()
                _process_events(app, 10)
            except Exception:
                pass
        try:
            store.db.close()
        except Exception:
            pass


def _write_outputs(
    run: ValidationRun,
    output_dir: Path,
    *,
    baseline_sha: str,
    candidate_sha: str,
    main_sha: str,
    success: bool,
    error: str = "",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": "Agenda Stage 5B-V",
        "success": success,
        "baseline_sha": baseline_sha,
        "candidate_sha": candidate_sha,
        "main_sha": main_sha,
        "checks": [asdict(item) for item in run.checks],
        "error": error,
    }
    (output_dir / "agenda-stage-05b-v.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Agenda Stage 5B-V Runtime Differential Evidence",
        "",
        f"- baseline_main: `{baseline_sha}`",
        f"- product_candidate: `{candidate_sha}`",
        f"- observed_main: `{main_sha}`",
        f"- validator_result: `{'PASS' if success else 'FAIL'}`",
        "",
        "## Runtime checks",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for item in run.checks:
        detail = item.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{item.name}` | **{item.status}** | {detail} |")
    if error:
        lines.extend(["", "## Error", "", "```text", error, "```"])
    (output_dir / "agenda-stage-05b-v.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--main-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_root = args.baseline_root.resolve()
    candidate_root = args.candidate_root.resolve()
    output_dir = args.output_dir.resolve()
    run = ValidationRun()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.chdir(candidate_root)
    sys.path.insert(0, str(candidate_root))

    try:
        _assert_exact_heads(
            run,
            baseline_root,
            candidate_root,
            args.baseline_sha,
            args.candidate_sha,
        )
        _assert_lineage(
            run,
            candidate_root,
            args.baseline_sha,
            args.candidate_sha,
        )
        _assert_preserved_current_main_files(run, baseline_root, candidate_root)
        _assert_static_runtime_contract(run, candidate_root)
        _assert_schema_runtime(run, output_dir)
        _assert_qt_runtime(run, output_dir)
    except Exception:
        error = traceback.format_exc()
        _write_outputs(
            run,
            output_dir,
            baseline_sha=args.baseline_sha,
            candidate_sha=args.candidate_sha,
            main_sha=args.main_sha,
            success=False,
            error=error,
        )
        print(error, file=sys.stderr)
        return 1

    _write_outputs(
        run,
        output_dir,
        baseline_sha=args.baseline_sha,
        candidate_sha=args.candidate_sha,
        main_sha=args.main_sha,
        success=True,
    )
    print(f"Agenda Stage 5B-V PASS: {len(run.checks)} runtime checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
