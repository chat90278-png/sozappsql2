from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

BASELINE = "e1ed9a66318e19178f132602d3114a97880fa27f"
CANDIDATE = "b6fe76d06abab31d70e7b129f4efdbe5bbb07472"
FEATURE = "b45d6f2e2b2948d1bbf9dcf1f83c8b04386a5c98"
ORIGINAL_MERGE_BASE = "2931fa267560397d4d849d6365acde504f376775"
BRANCH = "integration/gundemim-current-main-20260713"

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

PROTECTED_PATHS = [
    "app.py",
    "requirements.txt",
    "src/auth.py",
    "src/ui/main_window.py",
    "src/ui/main_page_final_window.py",
    "src/ui/widgets/contract_status_summary.py",
    "src/ui/widgets/corner_menu_layer.py",
    "src/ui/contract/contract_work_window.py",
    "src/workers/sts_load_worker.py",
    "src/services/multiplatform_contract_persistence.py",
    "src/ui/contract/multiplatform_context_refresh.py",
    "src/ui/corner_menu_runtime_fix.py",
    "src/ui/main_page_identity_runtime_fix.py",
    "src/ui/dialogs/contract_edit_timing_runtime_fix.py",
    "src/ui/dialogs/sd_edit_timing_runtime_fix.py",
    "src/services/contract_save_telemetry_runtime_fix.py",
    "src/services/delivery_schedule_slicer_runtime_fix.py",
]

ROOT = Path.cwd()
EVIDENCE = ROOT / "evidence"
VALIDATION = ROOT / "_validation"
BASELINE_DIR = VALIDATION / "baseline"
CANDIDATE_DIR = VALIDATION / "candidate"
FAILURES: list[str] = []


def write_text(name: str, text: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(text, encoding="utf-8")


def write_json(name: str, value: Any) -> None:
    write_text(
        name,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
    )


def run(
    args: list[str | Path],
    *,
    cwd: Path = ROOT,
    log_name: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONUTF8": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    process = subprocess.run(
        [str(item) for item in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        errors="replace",
    )
    output = process.stdout or ""
    if log_name:
        write_text(
            log_name,
            "$ " + " ".join(str(item) for item in args) + "\n" + output,
        )
    if check and process.returncode != 0:
        raise RuntimeError(
            f"command failed ({process.returncode}): "
            f"{' '.join(str(item) for item in args)}\n{output[-5000:]}"
        )
    return process


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    return run(["git", *args], cwd=cwd, check=check).stdout.strip()


def gate(name: str, operation: Callable[[], None]) -> None:
    try:
        operation()
    except Exception as exc:
        FAILURES.append(f"{name}: {exc}")
        print(f"[FAIL] {name}: {exc}")
        traceback.print_exc()
    else:
        print(f"[PASS] {name}")


def preflight() -> None:
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    if branch != BRANCH:
        raise AssertionError(f"wrong branch: {branch}")

    for commit in (BASELINE, CANDIDATE, FEATURE, ORIGINAL_MERGE_BASE):
        git("cat-file", "-e", f"{commit}^{{commit}}")

    if run(
        ["git", "merge-base", "--is-ancestor", CANDIDATE, head],
        check=False,
    ).returncode != 0:
        raise AssertionError("candidate is not an ancestor of validation HEAD")

    changed = git("diff", "--name-only", f"{CANDIDATE}..{head}").splitlines()
    if sorted(changed) != sorted(TEMP_PATHS):
        raise AssertionError(f"unexpected candidate→validation paths: {changed}")

    origin_main = git("rev-parse", "origin/main")
    origin_feature = git(
        "rev-parse",
        "origin/feature/gundemim-agenda-system",
    )
    merge_base = git("merge-base", BASELINE, CANDIDATE)
    ahead = int(git("rev-list", "--count", f"{BASELINE}..{CANDIDATE}"))
    behind = int(git("rev-list", "--count", f"{CANDIDATE}..{BASELINE}"))

    if origin_main != BASELINE:
        raise AssertionError(f"origin/main moved: {origin_main}")
    if origin_feature != FEATURE:
        raise AssertionError(f"accepted feature moved: {origin_feature}")
    if merge_base != BASELINE or ahead != 11 or behind != 0:
        raise AssertionError(
            f"candidate lineage mismatch: merge_base={merge_base}, "
            f"ahead={ahead}, behind={behind}"
        )

    merge_tree = run(
        [
            "git",
            "merge-tree",
            ORIGINAL_MERGE_BASE,
            BASELINE,
            FEATURE,
        ]
    ).stdout
    write_text("merge-tree.txt", merge_tree)
    forbidden = ("<<<<<<<", ">>>>>>>", "CONFLICT (", "changed in both")
    if any(marker in merge_tree for marker in forbidden):
        raise AssertionError("historical merge-tree contains conflict evidence")

    refs = {
        "main": origin_main,
        "candidate": CANDIDATE,
        "feature": origin_feature,
        "original_merge_base": ORIGINAL_MERGE_BASE,
        "merge_base": merge_base,
        "validation_head": head,
        "ahead": ahead,
        "behind": behind,
        "changed_paths": changed,
    }
    write_json("refs.json", refs)
    write_text("preflight.txt", json.dumps(refs, indent=2) + "\n")


def remove_worktree(path: Path) -> None:
    if path.exists():
        run(
            ["git", "worktree", "remove", "--force", str(path)],
            check=False,
        )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def materialize() -> None:
    remove_worktree(BASELINE_DIR)
    remove_worktree(CANDIDATE_DIR)
    run(["git", "worktree", "prune"], check=False)
    VALIDATION.mkdir(parents=True, exist_ok=True)
    run(["git", "worktree", "add", "--detach", str(BASELINE_DIR), BASELINE])
    run(["git", "worktree", "add", "--detach", str(CANDIDATE_DIR), CANDIDATE])

    for path in (BASELINE_DIR, CANDIDATE_DIR):
        dirty = git("status", "--porcelain", cwd=path)
        if dirty:
            raise AssertionError(f"dirty materialized worktree: {path}\n{dirty}")


def environment_and_requirements() -> None:
    baseline_requirements = (BASELINE_DIR / "requirements.txt").read_bytes()
    candidate_requirements = (CANDIDATE_DIR / "requirements.txt").read_bytes()
    parity = {
        "equal": baseline_requirements == candidate_requirements,
        "baseline_sha256": hashlib.sha256(baseline_requirements).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate_requirements).hexdigest(),
    }
    write_json("requirements-parity.json", parity)
    if not parity["equal"]:
        raise AssertionError("baseline/candidate requirements mismatch")

    import PySide6
    import pytest
    from PySide6.QtCore import qVersion

    pip_version = run([sys.executable, "-m", "pip", "--version"]).stdout.strip()
    write_text(
        "environment.txt",
        "\n".join(
            [
                f"platform={platform.platform()}",
                f"architecture={platform.architecture()}",
                f"python={sys.version}",
                f"pip={pip_version}",
                f"pytest={pytest.__version__}",
                f"PySide6={PySide6.__version__}",
                f"Qt={qVersion()}",
                "QT_QPA_PLATFORM=offscreen",
                "PYTHONUTF8=1",
                "PYTHONHASHSEED=0",
            ]
        )
        + "\n",
    )


def source_invariants() -> None:
    database = (
        CANDIDATE_DIR / "src/services/sts_database.py"
    ).read_text(encoding="utf-8")
    upgrade = (
        CANDIDATE_DIR / "src/services/sts_schema_upgrade.py"
    ).read_text(encoding="utf-8")
    fingerprint = (
        CANDIDATE_DIR / "src/services/sts_schema_upgrade_gate.py"
    ).read_text(encoding="utf-8")
    agenda_ui = (
        CANDIDATE_DIR / "src/ui/main_page_analysis_window.py"
    ).read_text(encoding="utf-8")

    checks = {
        "schema_version_18": "CURRENT_SCHEMA_VERSION = 18" in database,
        "single_helper_owner": (
            database.count("def ensure_staff_agenda_state_schema") == 1
            and "def ensure_staff_agenda_state_schema" not in upgrade
        ),
        "runtime_monkey_patch_absent": "_sts_database_module" not in upgrade,
        "migration_step_present": "v17_to_v18_staff_agenda_state" in upgrade,
        "fingerprint_v18": "FINGERPRINT_MAX_VERSION = 18" in fingerprint,
        "registry_key": '"agenda:detail"' in agenda_ui,
        "registry_open": "open_or_raise_tool_window" in agenda_ui,
        "registry_close": 'close_tool_window("agenda:detail")' in agenda_ui,
        "idempotent_widget_guards": agenda_ui.count("qt_obj_alive(widget)") >= 2,
        "idempotent_timer_guard": "qt_obj_alive(timer)" in agenda_ui,
    }
    write_json("source-invariants.json", checks)
    if not all(checks.values()):
        raise AssertionError(f"source invariants failed: {checks}")


def parse_junit(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    nodes: list[str] = []
    failures: list[str] = []
    errors: list[str] = []
    skipped: list[str] = []
    for case in cases:
        node = (
            f"{case.attrib.get('classname', '')}::"
            f"{case.attrib.get('name', '')}"
        )
        nodes.append(node)
        if case.find("failure") is not None:
            failures.append(node)
        if case.find("error") is not None:
            errors.append(node)
        if case.find("skipped") is not None:
            skipped.append(node)
    return {
        "tests": len(cases),
        "nodes": sorted(set(nodes)),
        "failures": sorted(failures),
        "errors": sorted(errors),
        "skipped": sorted(skipped),
    }


def run_pytest(
    tree: Path,
    test_paths: list[str],
    *,
    xml_name: str,
    log_name: str,
) -> dict[str, Any]:
    xml_path = EVIDENCE / xml_name
    process = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *test_paths,
            f"--junitxml={xml_path}",
        ],
        cwd=tree,
        log_name=log_name,
    )
    if process.returncode != 0:
        raise AssertionError(f"pytest failed: {xml_name}")
    result = parse_junit(xml_path)
    if result["failures"] or result["errors"] or result["skipped"]:
        raise AssertionError(f"non-clean JUnit result: {xml_name}: {result}")
    return result


def compile_tests_and_smokes() -> None:
    run(
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
        cwd=BASELINE_DIR,
        log_name="baseline-compile.txt",
    )
    run(
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
        cwd=CANDIDATE_DIR,
        log_name="candidate-compile.txt",
    )

    baseline = run_pytest(
        BASELINE_DIR,
        [],
        xml_name="baseline-full.xml",
        log_name="baseline-full.log",
    )

    missing = [
        path for path in TARGETED_TESTS if not (CANDIDATE_DIR / path).exists()
    ]
    if missing:
        raise AssertionError(f"missing targeted tests: {missing}")

    targeted = run_pytest(
        CANDIDATE_DIR,
        TARGETED_TESTS,
        xml_name="candidate-targeted.xml",
        log_name="candidate-targeted.log",
    )

    agenda_smoke = run(
        [sys.executable, "tests/smoke_sts_agenda_schema.py"],
        cwd=CANDIDATE_DIR,
        log_name="agenda-schema-smoke.txt",
    ).stdout
    if "agenda_schema=PASS" not in agenda_smoke or "schema_version=18" not in agenda_smoke:
        raise AssertionError("Agenda schema smoke semantic output mismatch")

    database_smoke = run(
        [sys.executable, "tests/smoke_sts_database.py"],
        cwd=CANDIDATE_DIR,
        log_name="database-smoke.txt",
    ).stdout
    if not database_smoke.strip().endswith("ok"):
        raise AssertionError("database smoke semantic output mismatch")

    candidate = run_pytest(
        CANDIDATE_DIR,
        [],
        xml_name="candidate-full.xml",
        log_name="candidate-full.log",
    )

    write_json(
        "suite-summary.json",
        {
            "baseline": baseline,
            "targeted": targeted,
            "candidate": candidate,
        },
    )


class CandidateImports:
    def __enter__(self) -> None:
        self.old_path = list(sys.path)
        self.old_cwd = Path.cwd()
        os.chdir(CANDIDATE_DIR)
        sys.path.insert(0, str(CANDIDATE_DIR))
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        os.chdir(self.old_cwd)
        sys.path[:] = self.old_path
        for name in list(sys.modules):
            if name == "src" or name.startswith("src."):
                sys.modules.pop(name, None)


def read_schema_contract(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        table_info = connection.execute(
            'PRAGMA table_info("staff_agenda_state")'
        ).fetchall()
        columns = [str(row[1]) for row in table_info]
        primary_key = [
            str(row[1])
            for row in sorted(
                (row for row in table_info if int(row[5] or 0) > 0),
                key=lambda row: int(row[5]),
            )
        ]
        foreign_keys = [
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
            for row in connection.execute(
                'PRAGMA foreign_key_list("staff_agenda_state")'
            ).fetchall()
        ]
        indexes = {}
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_staff_agenda_state_%'"
        ).fetchall():
            name = str(row[0])
            indexes[name] = [
                str(item[2])
                for item in connection.execute(
                    f'PRAGMA index_info("{name}")'
                ).fetchall()
            ]
        version_row = connection.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        return {
            "version": int(version_row[0]),
            "columns": columns,
            "primary_key": primary_key,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
            "integrity": connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0],
            "foreign_key_check": [
                tuple(row)
                for row in connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            ],
            "agenda_items_absent": connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='agenda_items'"
            ).fetchone()
            is None,
        }
    finally:
        connection.close()


def state_table_ddl(
    *,
    primary_key: str = "PRIMARY KEY(staff_id, agenda_key)",
    foreign_key: str = (
        "FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE"
    ),
) -> str:
    constraints = ",\n".join(
        value for value in (primary_key, foreign_key) if value
    )
    suffix = f",\n{constraints}" if constraints else ""
    return f"""
    CREATE TABLE staff_agenda_state(
        staff_id INTEGER NOT NULL,
        agenda_key TEXT NOT NULL,
        first_presented_at TEXT,
        last_presented_at TEXT,
        seen_at TEXT,
        seen_version TEXT NOT NULL DEFAULT '',
        snoozed_until TEXT,
        snoozed_version TEXT NOT NULL DEFAULT '',
        snoozed_severity TEXT NOT NULL DEFAULT '',
        dismissed_at TEXT,
        dismissed_version TEXT NOT NULL DEFAULT '',
        created_at TEXT,
        updated_at TEXT
        {suffix}
    )
    """


def recreate_state_table(
    connection: sqlite3.Connection,
    *,
    primary_key: str = "PRIMARY KEY(staff_id, agenda_key)",
    foreign_key: str = (
        "FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE"
    ),
) -> None:
    connection.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_staff")
    connection.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_snoozed")
    connection.execute("DROP TABLE IF EXISTS staff_agenda_state")
    connection.execute(
        state_table_ddl(primary_key=primary_key, foreign_key=foreign_key)
    )
    connection.execute(
        "CREATE INDEX idx_staff_agenda_state_staff "
        "ON staff_agenda_state(staff_id)"
    )
    connection.execute(
        "CREATE INDEX idx_staff_agenda_state_snoozed "
        "ON staff_agenda_state(staff_id, snoozed_until)"
    )


def schema_runtime() -> None:
    with CandidateImports(), tempfile.TemporaryDirectory(
        dir=VALIDATION
    ) as temp_dir:
        from src.services.sts_database import (
            AGENDA_STATE_COLUMNS,
            AGENDA_STATE_INDEXES,
            STSDatabase,
            STSMigrationError,
            ensure_staff_agenda_state_schema,
        )
        from src.services.sts_schema_upgrade import upgrade_sts_file
        from src.services.sts_schema_upgrade_gate import (
            validate_versioned_schema_fingerprint,
        )

        temp = Path(temp_dir)
        fresh = temp / "fresh.sts"
        database = STSDatabase(fresh)
        database.close()

        expected_indexes = {
            name: list(columns) for name, columns in AGENDA_STATE_INDEXES
        }
        fresh_contract = read_schema_contract(fresh)
        assert fresh_contract["version"] == 18
        assert fresh_contract["columns"] == list(AGENDA_STATE_COLUMNS)
        assert fresh_contract["primary_key"] == ["staff_id", "agenda_key"]
        assert fresh_contract["foreign_keys"] == [
            ("staff_id", "staff", "id", "CASCADE")
        ]
        assert fresh_contract["indexes"] == expected_indexes
        assert fresh_contract["integrity"] == "ok"
        assert not fresh_contract["foreign_key_check"]
        assert fresh_contract["agenda_items_absent"]
        validate_versioned_schema_fingerprint(fresh, 18)

        transaction_connection = sqlite3.connect(":memory:")
        transaction_connection.execute(
            "CREATE TABLE staff(id INTEGER PRIMARY KEY)"
        )
        transaction_connection.execute("BEGIN")
        first_created = ensure_staff_agenda_state_schema(
            transaction_connection
        )
        assert transaction_connection.in_transaction
        second_created = ensure_staff_agenda_state_schema(
            transaction_connection
        )
        assert second_created == ()
        assert transaction_connection.in_transaction
        transaction_connection.rollback()
        table_after_rollback = transaction_connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='staff_agenda_state'"
        ).fetchone()
        assert table_after_rollback is None
        transaction_connection.close()

        missing_parent = sqlite3.connect(":memory:")
        try:
            ensure_staff_agenda_state_schema(missing_parent)
        except RuntimeError as exc:
            missing_parent_error = str(exc)
        else:
            raise AssertionError("missing parent schema was accepted")
        finally:
            missing_parent.close()

        malformed = sqlite3.connect(":memory:")
        malformed.execute("CREATE TABLE staff(id INTEGER PRIMARY KEY)")
        malformed.execute(
            "CREATE TABLE staff_agenda_state("
            "staff_id INTEGER, agenda_key TEXT)"
        )
        try:
            ensure_staff_agenda_state_schema(malformed)
        except RuntimeError as exc:
            malformed_error = str(exc)
        else:
            raise AssertionError("malformed pre-existing schema was accepted")
        malformed_indexes = malformed.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_staff_agenda_state_%'"
        ).fetchall()
        assert not malformed_indexes
        malformed.close()

        version_17 = temp / "version17.sts"
        shutil.copy2(fresh, version_17)
        connection = sqlite3.connect(version_17)
        connection.execute("DROP INDEX idx_staff_agenda_state_staff")
        connection.execute("DROP INDEX idx_staff_agenda_state_snoozed")
        connection.execute("DROP TABLE staff_agenda_state")
        connection.execute(
            "UPDATE meta SET value='17' WHERE key='schema_version'"
        )
        connection.commit()
        connection.close()
        validate_versioned_schema_fingerprint(version_17, 17)

        upgrade_result = upgrade_sts_file(version_17)
        assert upgrade_result.applied_migrations == (
            "v17_to_v18_staff_agenda_state",
        )
        assert upgrade_result.backup_path is not None
        backup_connection = sqlite3.connect(upgrade_result.backup_path)
        try:
            backup_version = int(
                backup_connection.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0]
            )
            backup_state_table = backup_connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='staff_agenda_state'"
            ).fetchone()
        finally:
            backup_connection.close()
        assert backup_version == 17
        assert backup_state_table is None
        validate_versioned_schema_fingerprint(version_17, 18)
        upgraded_contract = read_schema_contract(version_17)
        assert upgraded_contract["columns"] == list(AGENDA_STATE_COLUMNS)
        assert upgraded_contract["foreign_keys"] == [
            ("staff_id", "staff", "id", "CASCADE")
        ]
        assert upgraded_contract["indexes"] == expected_indexes

        fresh_hash = hashlib.sha256(fresh.read_bytes()).hexdigest()
        current_result = upgrade_sts_file(fresh)
        assert current_result.status == "current"
        assert current_result.applied_migrations == ()
        assert current_result.backup_path is None
        assert hashlib.sha256(fresh.read_bytes()).hexdigest() == fresh_hash

        future = temp / "future19.sts"
        shutil.copy2(fresh, future)
        connection = sqlite3.connect(future)
        connection.execute(
            "UPDATE meta SET value='19' WHERE key='schema_version'"
        )
        connection.commit()
        connection.close()
        future_hash = hashlib.sha256(future.read_bytes()).hexdigest()
        try:
            upgrade_sts_file(future)
        except STSMigrationError as exc:
            future_error = str(exc)
        else:
            raise AssertionError("future schema was accepted")
        assert hashlib.sha256(future.read_bytes()).hexdigest() == future_hash

        drift_results: dict[str, str] = {}
        drift_cases = [
            "missing_table",
            "wrong_primary_key",
            "missing_foreign_key",
            "wrong_on_delete",
            "missing_index",
            "wrong_index_order",
            "forbidden_table",
        ]
        for case in drift_cases:
            drift_file = temp / f"{case}.sts"
            shutil.copy2(fresh, drift_file)
            connection = sqlite3.connect(drift_file)
            if case == "missing_table":
                connection.execute(
                    "DROP INDEX idx_staff_agenda_state_staff"
                )
                connection.execute(
                    "DROP INDEX idx_staff_agenda_state_snoozed"
                )
                connection.execute("DROP TABLE staff_agenda_state")
            elif case == "wrong_primary_key":
                recreate_state_table(
                    connection,
                    primary_key="PRIMARY KEY(agenda_key, staff_id)",
                )
            elif case == "missing_foreign_key":
                recreate_state_table(connection, foreign_key="")
            elif case == "wrong_on_delete":
                recreate_state_table(
                    connection,
                    foreign_key=(
                        "FOREIGN KEY(staff_id) REFERENCES staff(id) "
                        "ON DELETE SET NULL"
                    ),
                )
            elif case == "missing_index":
                connection.execute(
                    "DROP INDEX idx_staff_agenda_state_staff"
                )
            elif case == "wrong_index_order":
                connection.execute(
                    "DROP INDEX idx_staff_agenda_state_snoozed"
                )
                connection.execute(
                    "CREATE INDEX idx_staff_agenda_state_snoozed "
                    "ON staff_agenda_state(snoozed_until, staff_id)"
                )
            elif case == "forbidden_table":
                connection.execute(
                    "CREATE TABLE agenda_items(id INTEGER PRIMARY KEY)"
                )
            connection.commit()
            connection.close()

            try:
                validate_versioned_schema_fingerprint(drift_file, 18)
            except Exception as exc:
                drift_results[case] = f"{type(exc).__name__}: {exc}"
            else:
                raise AssertionError(f"structural drift accepted: {case}")

        cascade = temp / "cascade.sts"
        shutil.copy2(fresh, cascade)
        connection = sqlite3.connect(cascade)
        connection.execute("PRAGMA foreign_keys=ON")
        cursor = connection.execute(
            "INSERT INTO staff("
            "device_name, full_name, password_hash, role, is_active"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                "agenda-runtime-device",
                "Agenda Runtime",
                "runtime-hash",
                "personnel",
                1,
            ),
        )
        staff_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO staff_agenda_state("
            "staff_id, agenda_key, seen_version"
            ") VALUES (?, ?, ?)",
            (staff_id, "runtime-key", "runtime-version"),
        )
        connection.commit()
        connection.close()

        reopened = sqlite3.connect(cascade)
        reopened.execute("PRAGMA foreign_keys=ON")
        preserved = int(
            reopened.execute(
                "SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=?",
                (staff_id,),
            ).fetchone()[0]
        )
        reopened.execute("DELETE FROM staff WHERE id=?", (staff_id,))
        reopened.commit()
        after_delete = int(
            reopened.execute(
                "SELECT COUNT(*) FROM staff_agenda_state WHERE staff_id=?",
                (staff_id,),
            ).fetchone()[0]
        )
        reopened.close()
        assert preserved == 1
        assert after_delete == 0

        write_json(
            "schema-runtime.json",
            {
                "fresh_v18": fresh_contract,
                "helper_transaction": {
                    "first_created": first_created,
                    "second_created": second_created,
                    "caller_transaction_preserved": True,
                    "caller_rollback_removed_schema": True,
                },
                "missing_parent": missing_parent_error,
                "malformed_preexisting": {
                    "error": malformed_error,
                    "indexes_created": False,
                },
                "v17_to_v18": {
                    "applied_migrations": upgrade_result.applied_migrations,
                    "backup_path": upgrade_result.backup_path,
                    "backup_version": backup_version,
                    "backup_state_table_absent": backup_state_table is None,
                    "final": upgraded_contract,
                },
                "current_v18_noop": {
                    "status": current_result.status,
                    "applied_migrations": current_result.applied_migrations,
                    "backup_path": current_result.backup_path,
                    "file_unchanged": True,
                },
                "future_v19": {
                    "fail_closed": True,
                    "file_unchanged": True,
                    "error": future_error,
                },
                "structural_drift": drift_results,
                "cascade_reopen": {
                    "state_preserved_after_reopen": preserved,
                    "state_after_staff_delete": after_delete,
                },
            },
        )


def process_deferred_deletes(app) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def qt_runtime() -> None:
    with CandidateImports():
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import (
            QApplication,
            QFrame,
            QHBoxLayout,
            QMainWindow,
            QScrollArea,
            QSizePolicy,
            QWidget,
        )

        from src.ui.main_page_analysis_window import MainWindow
        from src.ui.main_window import qt_obj_alive

        app = QApplication.instance() or QApplication([])

        class Harness(MainWindow):
            def __init__(self) -> None:
                QMainWindow.__init__(self)
                self._agenda_facade = None
                self._agenda_bound_db = None
                self._agenda_snapshot = None
                self._agenda_detail_window = None
                self._agenda_refresh_timer = None
                self.current_staff = {"id": 1}
                self.contract_index: list[dict[str, Any]] = []
                self.allowed = True
                self.refresh_count = 0
                self.analysis_open_count = 0
                self.detail_factory_count = 0
                self.opened_contracts: list[dict[str, Any]] = []

                root = QWidget(self)
                layout = QHBoxLayout(root)
                calendar = QWidget(root)
                layout.addWidget(calendar)
                self.setCentralWidget(root)
                self._cal_widget = calendar
                self.upcoming_scroll = None
                self.contract_status_widget = None
                self.agenda_compact_widget = None

                self._tool_windows_by_key: dict[str, QWidget] = {}
                self._tool_window_chip_by_key: dict[str, QWidget] = {}
                self._active_tool_window_key = ""
                self.open_windows_strip = QFrame(self)
                self.open_windows_scroll = QScrollArea(
                    self.open_windows_strip
                )
                self.open_windows_host = QWidget()
                self.open_windows_layout = QHBoxLayout(
                    self.open_windows_host
                )
                self.open_windows_scroll.setWidget(self.open_windows_host)

            def is_sts_mode(self) -> bool:
                return True

            def has_permission(self, permission: str) -> bool:
                return self.allowed and permission == "view_contracts"

            def refresh_agenda(self, *args, **kwargs) -> None:
                self.refresh_count += 1

            def open_analysis_center(self, *args, **kwargs) -> None:
                self.analysis_open_count += 1

            def open_contract_item(self, item: dict[str, Any]) -> None:
                self.opened_contracts.append(item)

            def _agenda_mark_seen(self, *args, **kwargs) -> None:
                return None

            def _agenda_snooze(self, *args, **kwargs) -> None:
                return None

            def _create_agenda_detail_window(self):
                self.detail_factory_count += 1
                return super()._create_agenda_detail_window()

            def _refresh_stale_tool_window(self, key: str) -> None:
                return None

            def eventFilter(self, watched, event):
                return QMainWindow.eventFilter(self, watched, event)

        harness = Harness()

        harness._install_contract_status_widget()
        status_widget = harness.contract_status_widget
        harness._install_contract_status_widget()
        assert harness.contract_status_widget is status_widget
        status_widget.open_analysis_requested.emit()
        assert harness.analysis_open_count == 1

        harness._install_personal_agenda_widget()
        agenda_widget = harness.agenda_compact_widget
        timer = harness._agenda_refresh_timer
        harness._install_personal_agenda_widget()
        assert harness.agenda_compact_widget is agenda_widget
        assert harness._agenda_refresh_timer is timer

        layout = harness._cal_widget.parentWidget().layout()
        widgets = [
            layout.itemAt(index).widget()
            for index in range(layout.count())
            if layout.itemAt(index).widget() is not None
        ]
        assert widgets.count(status_widget) == 1
        assert widgets.count(agenda_widget) == 1
        assert widgets.count(harness._cal_widget) == 1
        assert widgets.index(status_widget) < widgets.index(agenda_widget)
        assert widgets.index(agenda_widget) < widgets.index(
            harness._cal_widget
        )
        assert (
            harness._cal_widget.sizePolicy().horizontalPolicy()
            == QSizePolicy.Fixed
        )
        assert (
            harness._cal_widget.sizePolicy().verticalPolicy()
            == QSizePolicy.Fixed
        )

        timer.timeout.emit()
        assert harness.refresh_count == 1

        refresh_before_open_signal = harness.refresh_count
        agenda_widget.open_details_requested.emit()
        assert harness.refresh_count == refresh_before_open_signal + 1
        first_detail = harness._agenda_detail_window
        first_chip = harness._tool_window_chip_by_key["agenda:detail"]
        assert qt_obj_alive(first_detail)
        assert qt_obj_alive(first_chip)
        assert harness.detail_factory_count == 1
        assert len(harness._tool_windows_by_key) == 1
        assert len(harness._tool_window_chip_by_key) == 1

        harness._open_agenda_details()
        assert harness._agenda_detail_window is first_detail
        assert harness.detail_factory_count == 1
        assert harness._tool_window_chip_by_key["agenda:detail"] is first_chip

        before_detail_refresh = harness.refresh_count
        first_detail.refresh_requested.emit()
        assert harness.refresh_count == before_detail_refresh + 1

        assert harness.close_tool_window("agenda:detail")
        process_deferred_deletes(app)
        assert "agenda:detail" not in harness._tool_windows_by_key
        assert "agenda:detail" not in harness._tool_window_chip_by_key

        harness._open_agenda_details()
        second_detail = harness._agenda_detail_window
        assert second_detail is not first_detail
        assert harness.detail_factory_count == 2
        assert "agenda:detail" in harness._tool_windows_by_key

        harness.allowed = False
        assert harness._sync_agenda_permission_visibility() is False
        process_deferred_deletes(app)
        assert "agenda:detail" not in harness._tool_windows_by_key
        assert harness._agenda_detail_window is None

        harness.allowed = True
        harness._open_agenda_details()
        harness._agenda_facade = object()
        harness._agenda_bound_db = object()
        harness._agenda_snapshot = object()
        timer.start(1000)
        assert timer.isActive()
        harness._reset_agenda_binding()
        process_deferred_deletes(app)
        assert not timer.isActive()
        assert "agenda:detail" not in harness._tool_windows_by_key
        assert harness._agenda_detail_window is None
        assert harness._agenda_facade is None
        assert harness._agenda_bound_db is None
        assert harness._agenda_snapshot is None
        assert not agenda_widget.isVisible()

        harness.contract_index = [
            {"id": 1, "contract_no": "DUP"},
            {"id": 2, "contract_no": "DUP"},
        ]
        harness._open_agenda_contract(2)
        assert harness.opened_contracts[-1]["id"] == 2

        harness.allowed = True
        harness._open_agenda_details()
        timer.start(1000)
        parent_class = MainWindow.__mro__[1]
        original_parent_close = parent_class.closeEvent
        parent_class.closeEvent = lambda self, event: event.accept()
        try:
            close_event = QCloseEvent()
            MainWindow.closeEvent(harness, close_event)
        finally:
            parent_class.closeEvent = original_parent_close
        process_deferred_deletes(app)
        assert close_event.isAccepted()
        assert not timer.isActive()
        assert "agenda:detail" not in harness._tool_windows_by_key
        assert harness._agenda_detail_window is None

        write_json(
            "qt-runtime.json",
            {
                "initialized_qmainwindow_harness": True,
                "production_widget_install_methods": True,
                "production_tool_window_registry_methods": True,
                "widget_install": {
                    "status_reused": True,
                    "agenda_reused": True,
                    "timer_reused": True,
                    "status_signal_single_effect": harness.analysis_open_count,
                    "timer_signal_single_effect": 1,
                    "order": [
                        type(widget).__name__ for widget in widgets
                    ],
                    "calendar_policy_fixed": True,
                },
                "agenda_detail_registry": {
                    "key": "agenda:detail",
                    "first_open_factory_count": 1,
                    "second_open_reused": True,
                    "single_chip": True,
                    "detail_refresh_single_effect": 1,
                    "close_unregistered": True,
                    "reopen_created_new_instance": True,
                    "permission_loss_closed": True,
                    "file_reset_closed": True,
                    "close_event_closed": True,
                },
                "navigation": {
                    "requested_contract_id": 2,
                    "opened_contract_id": harness.opened_contracts[-1]["id"],
                    "duplicate_contract_number_safe": True,
                },
            },
        )

        harness.deleteLater()
        process_deferred_deletes(app)


def junit_differential() -> None:
    baseline = parse_junit(EVIDENCE / "baseline-full.xml")
    candidate = parse_junit(EVIDENCE / "candidate-full.xml")
    targeted = parse_junit(EVIDENCE / "candidate-targeted.xml")

    baseline_nodes = set(baseline["nodes"])
    candidate_nodes = set(candidate["nodes"])
    baseline_only = sorted(baseline_nodes - candidate_nodes)
    candidate_only = sorted(candidate_nodes - baseline_nodes)

    allowed_tokens = (
        "agenda",
        "schema_v18",
        "v17_to_v18",
        "startup_upgrade",
        "current_main_composition",
    )
    unexpected_candidate_only = [
        node
        for node in candidate_only
        if not any(token in node.lower() for token in allowed_tokens)
    ]

    result = {
        "baseline": baseline,
        "candidate": candidate,
        "targeted": targeted,
        "baseline_only": baseline_only,
        "candidate_only": candidate_only,
        "unexpected_candidate_only": unexpected_candidate_only,
    }
    write_json("junit-differential.json", result)
    write_text(
        "junit-differential.txt",
        "\n".join(
            [
                f"baseline={baseline['tests']}",
                f"candidate={candidate['tests']}",
                f"targeted={targeted['tests']}",
                f"baseline_only={baseline_only}",
                f"candidate_only={candidate_only}",
                f"unexpected_candidate_only={unexpected_candidate_only}",
            ]
        )
        + "\n",
    )

    dirty_results = (
        baseline["failures"]
        + baseline["errors"]
        + baseline["skipped"]
        + candidate["failures"]
        + candidate["errors"]
        + candidate["skipped"]
        + targeted["failures"]
        + targeted["errors"]
        + targeted["skipped"]
    )
    if dirty_results:
        raise AssertionError(f"JUnit failures/errors/skips: {dirty_results}")
    if baseline_only:
        raise AssertionError(f"baseline test nodes disappeared: {baseline_only}")
    if unexpected_candidate_only:
        raise AssertionError(
            f"unexpected candidate-only test nodes: "
            f"{unexpected_candidate_only}"
        )


def protected_source_parity() -> None:
    rows: dict[str, Any] = {}
    mismatches: list[str] = []
    for path in PROTECTED_PATHS:
        baseline_blob = git("rev-parse", f"{BASELINE}:{path}", check=False)
        candidate_blob = git("rev-parse", f"{CANDIDATE}:{path}", check=False)
        equal = bool(baseline_blob) and baseline_blob == candidate_blob
        rows[path] = {
            "baseline_blob": baseline_blob,
            "candidate_blob": candidate_blob,
            "equal": equal,
        }
        if not equal:
            mismatches.append(path)

    temporary_at_candidate = [
        path
        for path in TEMP_PATHS
        if run(
            ["git", "cat-file", "-e", f"{CANDIDATE}:{path}"],
            check=False,
        ).returncode
        == 0
    ]
    result = {
        "paths": rows,
        "mismatches": mismatches,
        "temporary_paths_at_candidate": temporary_at_candidate,
    }
    write_json("protected-source-parity.json", result)
    if mismatches:
        raise AssertionError(f"protected source mismatches: {mismatches}")
    if temporary_at_candidate:
        raise AssertionError(
            f"temporary paths exist at candidate: {temporary_at_candidate}"
        )


def main() -> int:
    gates = [
        ("preflight", preflight),
        ("materialization", materialize),
        ("environment/requirements", environment_and_requirements),
        ("source invariants", source_invariants),
        ("compile/tests/smokes", compile_tests_and_smokes),
        ("schema runtime", schema_runtime),
        ("Qt runtime", qt_runtime),
        ("JUnit differential", junit_differential),
        ("protected source parity", protected_source_parity),
    ]
    for name, operation in gates:
        gate(name, operation)

    decision = "PASS" if not FAILURES else "FAIL"
    write_text(
        "decision.txt",
        decision + "\n" + "\n".join(FAILURES) + "\n",
    )
    write_json(
        "pr-state.json",
        {
            "number": os.getenv("PR_NUMBER", "334"),
            "title": "TEMP VALIDATION: Agenda Stage 5B-V",
            "base": "main",
            "head": BRANCH,
            "draft": True,
            "run_id": os.getenv("GITHUB_RUN_ID", ""),
            "job_name": os.getenv("GITHUB_JOB", ""),
        },
    )
    return 0 if decision == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
