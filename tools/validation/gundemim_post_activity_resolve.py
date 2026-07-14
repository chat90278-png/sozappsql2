from __future__ import annotations

from pathlib import Path
from typing import Callable


ConflictHandler = Callable[[int, list[str], list[str]], list[str]]


def resolve_conflicts(path: str, handler: ConflictHandler) -> str:
    file_path = Path(path)
    lines = file_path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    index = 0
    conflict_no = 0

    while index < len(lines):
        if not lines[index].startswith("<<<<<<< "):
            output.append(lines[index])
            index += 1
            continue

        conflict_no += 1
        index += 1
        ours: list[str] = []
        while index < len(lines) and lines[index] != "=======":
            ours.append(lines[index])
            index += 1
        if index >= len(lines):
            raise RuntimeError(f"{path}: missing conflict separator")

        index += 1
        theirs: list[str] = []
        while index < len(lines) and not lines[index].startswith(">>>>>>> "):
            theirs.append(lines[index])
            index += 1
        if index >= len(lines):
            raise RuntimeError(f"{path}: missing conflict end")

        index += 1
        output.extend(handler(conflict_no, ours, theirs))

    resolved = "\n".join(output) + "\n"
    if "<<<<<<< " in resolved or ">>>>>>> " in resolved:
        raise RuntimeError(f"{path}: unresolved conflict marker")
    file_path.write_text(resolved, encoding="utf-8")
    return resolved


def database_handler(_number: int, ours: list[str], theirs: list[str]) -> list[str]:
    ours_text = "\n".join(ours)
    theirs_text = "\n".join(theirs)
    if "ACTIVITY_LOG_COLUMNS" in ours_text and "AGENDA_STATE_COLUMNS" in theirs_text:
        return ours + [""] + theirs
    if "Own the outer transaction and use unique savepoints" in ours_text:
        return ours
    raise RuntimeError("Unexpected sts_database conflict")


def upgrade_handler(_number: int, ours: list[str], theirs: list[str]) -> list[str]:
    ours_text = "\n".join(ours)
    theirs_text = "\n".join(theirs)
    if "ACTIVITY_LOG_COLUMNS" in ours_text and "ensure_staff_agenda_state_schema" in theirs_text:
        return ours + [
            "",
            "",
            "def _migrate_18_to_19(conn: sqlite3.Connection) -> None:",
            "    ensure_staff_agenda_state_schema(conn)",
        ]
    if "v17_to_v18_activity_history_infrastructure" in ours_text:
        return ours + [
            '    MigrationStep(18, 19, "v18_to_v19_staff_agenda_state", _migrate_18_to_19),'
        ]
    raise RuntimeError("Unexpected sts_schema_upgrade conflict")


def gate_handler(number: int, ours: list[str], theirs: list[str]) -> list[str]:
    if number == 1:
        activity: list[str] = []
        for line in ours:
            if line.startswith("FINGERPRINT_MIN_VERSION"):
                break
            activity.append(line)

        agenda: list[str] = []
        for line in theirs:
            if line.startswith("FINGERPRINT_MIN_VERSION"):
                break
            agenda.append(
                line.replace("_V18_AGENDA_STATE_COLUMNS", "_V19_AGENDA_STATE_COLUMNS")
                .replace("_V18_INDEXES", "_V19_AGENDA_INDEXES")
            )
        return activity + [""] + agenda + [
            "",
            "FINGERPRINT_MIN_VERSION = VERSIONED_MIGRATION_FLOOR",
            "FINGERPRINT_MAX_VERSION = CURRENT_SCHEMA_VERSION",
        ]

    if number == 2:
        agenda_body = [
            line.replace("_V18_AGENDA_STATE_COLUMNS", "_V19_AGENDA_STATE_COLUMNS")
            .replace("_V18_INDEXES", "_V19_AGENDA_INDEXES")
            for line in theirs
        ]
        return ours + ["    if version >= 19:"] + agenda_body

    raise RuntimeError("Unexpected sts_schema_upgrade_gate conflict")


def keep_activity_side(_number: int, ours: list[str], _theirs: list[str]) -> list[str]:
    return ours


def add_v19_after_activity_migrations(text: str) -> str:
    activity_line = '        "v17_to_v18_activity_history_infrastructure",\n'
    agenda_line = '        "v18_to_v19_staff_agenda_state",\n'
    text = text.replace(activity_line + agenda_line, activity_line)
    return text.replace(activity_line, activity_line + agenda_line)


def patch_tests() -> None:
    migration_path = Path("tests/test_sts_schema_upgrade.py")
    migration_text = add_v19_after_activity_migrations(
        migration_path.read_text(encoding="utf-8")
    )
    migration_text = (
        migration_text.replace("CURRENT_SCHEMA_VERSION == 18", "CURRENT_SCHEMA_VERSION == 19")
        .replace("read_sts_schema_version(path) == 18", "read_sts_schema_version(path) == 19")
        .replace("def test_v16_runs_only_v16_to_v17", "def test_v16_runs_full_v16_to_v19_chain")
        .replace(
            "def test_v16_runs_v16_to_v17_and_v17_to_v18",
            "def test_v16_runs_full_v16_to_v19_chain",
        )
    )
    migration_path.write_text(migration_text, encoding="utf-8")

    gate_test_path = Path("tests/test_sts_schema_upgrade_gate.py")
    gate_test_text = add_v19_after_activity_migrations(
        gate_test_path.read_text(encoding="utf-8")
    )
    gate_test_text = (
        gate_test_text.replace("test_current_v18_with_v16_shape", "test_current_v19_with_v16_shape")
        .replace("schema_fingerprint_mismatch=v18", "schema_fingerprint_mismatch=v19")
        .replace(
            "schema_fingerprint_not_registered=v18",
            "schema_fingerprint_not_registered=v19",
        )
    )
    gate_test_path.write_text(gate_test_text, encoding="utf-8")

    agenda_schema = Path("tests/test_agenda_schema_v18_integration.py")
    agenda_text = agenda_schema.read_text(encoding="utf-8")
    agenda_text = (
        agenda_text.replace(
            "def test_real_v17_without_agenda_state_upgrades_to_v18",
            "def test_real_v18_without_agenda_state_upgrades_to_v19",
        )
        .replace(
            "conn.execute(\"UPDATE meta SET value='17' WHERE key='schema_version'\")",
            "conn.execute(\"UPDATE meta SET value='18' WHERE key='schema_version'\")",
        )
        .replace(
            '("v17_to_v18_staff_agenda_state",)',
            '("v18_to_v19_staff_agenda_state",)',
        )
        .replace("CURRENT_SCHEMA_VERSION == 18", "CURRENT_SCHEMA_VERSION == 19")
        .replace(
            "validate_versioned_schema_fingerprint(path, 18)",
            "validate_versioned_schema_fingerprint(path, 19)",
        )
    )
    agenda_schema.write_text(agenda_text, encoding="utf-8")
    agenda_schema.rename("tests/test_agenda_schema_v19_integration.py")

    smoke = Path("tests/smoke_sts_agenda_schema.py")
    smoke.write_text(
        smoke.read_text(encoding="utf-8")
        .replace("CURRENT_SCHEMA_VERSION == 18", "CURRENT_SCHEMA_VERSION == 19")
        .replace(
            'schema_version_after_second_init == "18"',
            'schema_version_after_second_init == "19"',
        )
        .replace('print("schema_version=18")', 'print("schema_version=19")'),
        encoding="utf-8",
    )


def verify_contract() -> None:
    required = {
        "src/services/sts_database.py": (
            "CURRENT_SCHEMA_VERSION = 19",
            "ACTIVITY_LOG_COLUMNS",
            "AGENDA_STATE_COLUMNS",
            "def ensure_staff_agenda_state_schema",
            "Own the outer transaction and use unique savepoints",
        ),
        "src/services/sts_schema_upgrade.py": (
            "v17_to_v18_activity_history_infrastructure",
            "v18_to_v19_staff_agenda_state",
            "def _migrate_18_to_19",
        ),
        "src/services/sts_schema_upgrade_gate.py": (
            "_V18_ACTIVITY_COLUMNS",
            "_V19_AGENDA_STATE_COLUMNS",
            "if version >= 18:",
            "if version >= 19:",
            "required_primary_keys",
            "forbidden_tables",
            "FINGERPRINT_MAX_VERSION = CURRENT_SCHEMA_VERSION",
        ),
    }
    for path, tokens in required.items():
        text = Path(path).read_text(encoding="utf-8")
        missing = [token for token in tokens if token not in text]
        if missing:
            raise RuntimeError(f"{path}: missing tokens {missing}")

    stale_patterns = (
        "v17_to_v18_staff_agenda_state",
        "CURRENT_SCHEMA_VERSION == 18",
        "schema_fingerprint_mismatch=v18",
        "schema_fingerprint_not_registered=v18",
        'schema_version_after_second_init == "18"',
        "schema_version=18",
    )
    stale_hits: list[str] = []
    for path in Path("tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in stale_patterns:
            if pattern in text:
                stale_hits.append(f"{path}:{pattern}")
    if stale_hits:
        raise RuntimeError("Stale Agenda v18 expectations:\n" + "\n".join(stale_hits))


def main() -> None:
    database = resolve_conflicts("src/services/sts_database.py", database_handler)
    database = database.replace(
        "CURRENT_SCHEMA_VERSION = 18",
        "CURRENT_SCHEMA_VERSION = 19",
        1,
    )
    Path("src/services/sts_database.py").write_text(database, encoding="utf-8")

    upgrade = resolve_conflicts("src/services/sts_schema_upgrade.py", upgrade_handler)
    if "    ensure_staff_agenda_state_schema,\n" not in upgrade:
        upgrade = upgrade.replace(
            "    STSMigrationError,\n",
            "    STSMigrationError,\n    ensure_staff_agenda_state_schema,\n",
            1,
        )
    Path("src/services/sts_schema_upgrade.py").write_text(upgrade, encoding="utf-8")

    resolve_conflicts("src/services/sts_schema_upgrade_gate.py", gate_handler)
    resolve_conflicts("tests/test_sts_schema_upgrade.py", keep_activity_side)
    resolve_conflicts("tests/test_sts_schema_upgrade_gate.py", keep_activity_side)
    patch_tests()
    verify_contract()


if __name__ == "__main__":
    main()
