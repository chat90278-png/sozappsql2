from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASE_HEAD = "80b6f927d0c0f3a89e8b2cb7cef603892c60202d"
ORIGINAL_PATCHER = ROOT / "tools/validation/apply_agenda_stage_05b_r1.py"

BOOTSTRAP_PATHS = {
    ".github/workflows/agenda-stage-05b-r1-online-fix.yml",
    "tools/validation/apply_agenda_stage_05b_r1.py",
    "tools/validation/run_agenda_stage_05b_r1_hotfix.py",
}


def run(*args: str) -> str:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"{' '.join(args)} failed:\n{proc.stdout}")
    return proc.stdout.strip()


def load_original_patcher():
    if not ORIGINAL_PATCHER.is_file():
        raise RuntimeError(f"Original patcher missing: {ORIGINAL_PATCHER}")
    spec = importlib.util.spec_from_file_location(
        "agenda_stage_05b_r1_original",
        ORIGINAL_PATCHER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Original patcher could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_bootstrap_boundary() -> None:
    run("git", "cat-file", "-e", f"{EXPECTED_BASE_HEAD}^{{commit}}")
    run("git", "merge-base", "--is-ancestor", EXPECTED_BASE_HEAD, "HEAD")

    changed = {
        item
        for item in run(
            "git",
            "diff",
            "--name-only",
            EXPECTED_BASE_HEAD,
            "HEAD",
        ).splitlines()
        if item
    }
    unexpected = changed - BOOTSTRAP_PATHS
    if unexpected:
        raise RuntimeError(
            f"Bootstrap history contains unexpected paths: {sorted(unexpected)}"
        )
    required = {
        ".github/workflows/agenda-stage-05b-r1-online-fix.yml",
        "tools/validation/apply_agenda_stage_05b_r1.py",
    }
    missing = required - changed
    if missing:
        raise RuntimeError(
            f"Required bootstrap paths are missing: {sorted(missing)}"
        )



def replace_generated_agenda_helper(patcher) -> None:
    path = "src/services/sts_database.py"
    text = patcher.read(path)
    text = patcher.replace_top_level_function(
        text,
        "ensure_staff_agenda_state_schema",
        """
def ensure_staff_agenda_state_schema(
    conn: sqlite3.Connection,
) -> tuple[str, ...]:
    # Caller owns transaction, commit and rollback behavior.
    staff_columns = {
        str(row[1])
        for row in _agenda_table_info(conn, "staff")
    }
    if "id" not in staff_columns:
        raise RuntimeError(
            "staff_agenda_state oluşturulamadı: "
            "staff tablosu veya staff.id eksik."
        )
    if _agenda_table_exists(conn, "agenda_items"):
        raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")

    created: list[str] = []
    table_existed = _agenda_table_exists(conn, "staff_agenda_state")
    conn.execute(
        \"""
        CREATE TABLE IF NOT EXISTS staff_agenda_state(
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
            updated_at TEXT,
            PRIMARY KEY(staff_id, agenda_key),
            FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE
        )
        \"""
    )
    if not table_existed:
        created.append("staff_agenda_state")

    # Fail closed on malformed pre-existing tables before attempting indexes.
    table_info = _agenda_table_info(conn, "staff_agenda_state")
    actual_columns = tuple(str(row[1]) for row in table_info)
    if actual_columns != AGENDA_STATE_COLUMNS:
        raise RuntimeError(
            "staff_agenda_state kolon sözleşmesi geçersiz: "
            f"expected={AGENDA_STATE_COLUMNS}; actual={actual_columns}"
        )

    primary_key = tuple(
        str(row[1])
        for row in sorted(
            (row for row in table_info if int(row[5] or 0) > 0),
            key=lambda row: int(row[5]),
        )
    )
    if primary_key != ("staff_id", "agenda_key"):
        raise RuntimeError(
            "staff_agenda_state primary key sözleşmesi geçersiz: "
            f"expected=('staff_id', 'agenda_key'); actual={primary_key}"
        )

    foreign_keys = [
        (str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
        for row in conn.execute(
            'PRAGMA foreign_key_list("staff_agenda_state")'
        ).fetchall()
    ]
    expected_fk = ("staff_id", "staff", "id", "CASCADE")
    if foreign_keys != [expected_fk]:
        raise RuntimeError(
            "staff_agenda_state foreign key sözleşmesi geçersiz: "
            f"expected={expected_fk}; actual={foreign_keys}"
        )

    existing_indexes = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_staff "
        "ON staff_agenda_state(staff_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_snoozed "
        "ON staff_agenda_state(staff_id,snoozed_until)"
    )
    for index_name, _columns in AGENDA_STATE_INDEXES:
        if index_name not in existing_indexes:
            created.append(index_name)

    current_indexes = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for index_name, expected_columns in AGENDA_STATE_INDEXES:
        if index_name not in current_indexes:
            raise RuntimeError(
                f"staff_agenda_state index eksik: {index_name}"
            )
        actual_index_columns = _agenda_index_columns(conn, index_name)
        if actual_index_columns != expected_columns:
            raise RuntimeError(
                f"{index_name} kolon sırası geçersiz: "
                f"expected={expected_columns}; "
                f"actual={actual_index_columns}"
            )

    if _agenda_table_exists(conn, "agenda_items"):
        raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")
    return tuple(created)
""",
    )
    patcher.write(path, text)


def fix_agenda_schema_test_staff_fixture(patcher) -> None:
    path = "tests/test_agenda_schema_v18_integration.py"
    text = patcher.read(path)
    old = (
        '"INSERT INTO staff(username,password_hash,full_name,is_active,is_admin) "\n'
        '            "VALUES(\'agenda-user\',\'x\',\'Agenda User\',1,0)"'
    )
    new = (
        '"INSERT INTO staff(device_name,full_name,password_hash,role,is_active) "\n'
        '            "VALUES(\'agenda-device\',\'Agenda User\',\'x\',\'personnel\',1)"'
    )
    count = text.count(old)
    if count != 1:
        raise AssertionError(
            "Agenda cascade staff fixture: "
            f"expected exactly one match, got {count}"
        )
    patcher.write(path, text.replace(old, new, 1))

def main() -> None:
    verify_bootstrap_boundary()
    patcher = load_original_patcher()

    original_replace_once = patcher.replace_once

    def safe_replace_once(
        text: str,
        old: str,
        new: str,
        label: str,
    ) -> str:
        # The v14 expected migration suffix also occurs in the dedicated v16
        # test. Only the first occurrence belongs to the v14 chain; the v16
        # block is updated by the following, more specific replacement.
        if label == "v14 chain":
            count = text.count(old)
            if count < 1:
                raise AssertionError(
                    f"{label}: expected at least one match, got {count}"
                )
            return text.replace(old, new, 1)
        return original_replace_once(text, old, new, label)

    patcher.replace_once = safe_replace_once

    patcher.patch_sts_database()
    replace_generated_agenda_helper(patcher)
    patcher.patch_sts_schema_upgrade()
    patcher.patch_main_page()
    patcher.patch_tests()
    fix_agenda_schema_test_staff_fixture(patcher)
    patcher.verify_source_contracts()

    for relative_path in (
        "src/services/sts_database.py",
        "src/services/sts_schema_upgrade.py",
        "src/services/sts_schema_upgrade_gate.py",
        "src/ui/main_page_analysis_window.py",
    ):
        ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))

    print("stage5b_r1_hotfix_patch=PASS")


if __name__ == "__main__":
    main()
