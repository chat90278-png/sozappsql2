from __future__ import annotations

import ast
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASE_HEAD = "80b6f927d0c0f3a89e8b2cb7cef603892c60202d"


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


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def remove_top_level_nodes(
    text: str,
    *,
    function_names: set[str] | None = None,
    if_contains: str | None = None,
) -> str:
    function_names = function_names or set()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    ranges: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in function_names:
            ranges.append((node.lineno - 1, node.end_lineno))
        elif isinstance(node, ast.If) and if_contains:
            segment = ast.get_source_segment(text, node) or ""
            if if_contains in segment:
                ranges.append((node.lineno - 1, node.end_lineno))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


def replace_class_method(text: str, class_name: str, method_name: str, new_source: str) -> str:
    tree = ast.parse(text)
    target = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    target = item
                    break
    if target is None:
        raise AssertionError(f"method not found: {class_name}.{method_name}")
    lines = text.splitlines(keepends=True)
    replacement = textwrap.dedent(new_source).strip("\n") + "\n"
    replacement = textwrap.indent(replacement, "    ")
    lines[target.lineno - 1 : target.end_lineno] = [replacement]
    return "".join(lines)


def replace_top_level_function(text: str, function_name: str, new_source: str) -> str:
    tree = ast.parse(text)
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ),
        None,
    )
    if target is None:
        raise AssertionError(f"function not found: {function_name}")
    lines = text.splitlines(keepends=True)
    replacement = textwrap.dedent(new_source).strip("\n") + "\n"
    lines[target.lineno - 1 : target.end_lineno] = [replacement]
    return "".join(lines)


def patch_sts_database() -> None:
    path = "src/services/sts_database.py"
    text = read(path)
    if "def ensure_staff_agenda_state_schema(" in text:
        raise AssertionError("canonical Agenda helper unexpectedly already exists")

    marker = 'CURRENT_SCHEMA_VERSION = 18\n\n\nclass STSMigrationError'
    helper = '''CURRENT_SCHEMA_VERSION = 18

AGENDA_STATE_COLUMNS: tuple[str, ...] = (
    "staff_id", "agenda_key", "first_presented_at", "last_presented_at",
    "seen_at", "seen_version", "snoozed_until", "snoozed_version",
    "snoozed_severity", "dismissed_at", "dismissed_version",
    "created_at", "updated_at",
)

AGENDA_STATE_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_staff_agenda_state_staff", ("staff_id",)),
    ("idx_staff_agenda_state_snoozed", ("staff_id", "snoozed_until")),
)


def _agenda_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (str(table or ""),),
    ).fetchone() is not None


def _agenda_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row | tuple]:
    if not _agenda_table_exists(conn, table):
        return []
    return list(conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall())


def _agenda_index_columns(conn: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    return tuple(
        str(row[2])
        for row in conn.execute(
            f"PRAGMA index_info({quote_identifier(index_name)})"
        ).fetchall()
    )


def ensure_staff_agenda_state_schema(conn: sqlite3.Connection) -> tuple[str, ...]:
    # Caller owns transaction, commit and rollback behavior.
    staff_columns = {str(row[1]) for row in _agenda_table_info(conn, "staff")}
    if "id" not in staff_columns:
        raise RuntimeError(
            "staff_agenda_state oluşturulamadı: staff tablosu veya staff.id eksik."
        )
    if _agenda_table_exists(conn, "agenda_items"):
        raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")

    created: list[str] = []
    table_existed = _agenda_table_exists(conn, "staff_agenda_state")
    conn.execute(
        """
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
        """
    )
    if not table_existed:
        created.append("staff_agenda_state")

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
        for row in conn.execute('PRAGMA foreign_key_list("staff_agenda_state")').fetchall()
    ]
    expected_fk = ("staff_id", "staff", "id", "CASCADE")
    if foreign_keys != [expected_fk]:
        raise RuntimeError(
            "staff_agenda_state foreign key sözleşmesi geçersiz: "
            f"expected={expected_fk}; actual={foreign_keys}"
        )

    current_indexes = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for index_name, expected_columns in AGENDA_STATE_INDEXES:
        if index_name not in current_indexes:
            raise RuntimeError(f"staff_agenda_state index eksik: {index_name}")
        actual_index_columns = _agenda_index_columns(conn, index_name)
        if actual_index_columns != expected_columns:
            raise RuntimeError(
                f"{index_name} kolon sırası geçersiz: "
                f"expected={expected_columns}; actual={actual_index_columns}"
            )

    if _agenda_table_exists(conn, "agenda_items"):
        raise RuntimeError("Yasak agenda_items tablosu tespit edildi.")
    return tuple(created)


class STSMigrationError'''
    text = replace_once(text, marker, helper, "insert canonical Agenda helper")

    table_ddl = (
        "CREATE TABLE IF NOT EXISTS staff_agenda_state(staff_id INTEGER NOT NULL,"
        "agenda_key TEXT NOT NULL,first_presented_at TEXT,last_presented_at TEXT,"
        "seen_at TEXT,seen_version TEXT NOT NULL DEFAULT '',snoozed_until TEXT,"
        "snoozed_version TEXT NOT NULL DEFAULT '',snoozed_severity TEXT NOT NULL DEFAULT '',"
        "dismissed_at TEXT,dismissed_version TEXT NOT NULL DEFAULT '',created_at TEXT,"
        "updated_at TEXT,PRIMARY KEY(staff_id,agenda_key),FOREIGN KEY(staff_id) "
        "REFERENCES staff(id) ON DELETE CASCADE);\n"
    )
    text = replace_once(text, table_ddl, "", "remove duplicate Agenda table DDL")
    text = replace_once(
        text,
        '        create_if("staff_agenda_state", ("staff_id",), "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_staff ON staff_agenda_state(staff_id)")\n',
        "",
        "remove duplicate Agenda staff index owner",
    )
    text = replace_once(
        text,
        '        create_if("staff_agenda_state", ("staff_id", "snoozed_until"), "CREATE INDEX IF NOT EXISTS idx_staff_agenda_state_snoozed ON staff_agenda_state(staff_id,snoozed_until)")\n',
        "",
        "remove duplicate Agenda snoozed index owner",
    )
    text = replace_once(
        text,
        '        ensure_staff_table(self.conn)\n        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_staff_role_id ON staff(role_id)")',
        '        ensure_staff_table(self.conn)\n        migrated.extend(ensure_staff_agenda_state_schema(self.conn))\n        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_staff_role_id ON staff(role_id)")',
        "wire canonical helper into init_schema",
    )
    write(path, text)


def patch_sts_schema_upgrade() -> None:
    path = "src/services/sts_schema_upgrade.py"
    text = read(path)
    text = text.replace("import src.services.sts_database as _sts_database_module\n", "", 1)
    text = replace_once(
        text,
        "    STSMigrationError,\n    make_migration_backup_path,",
        "    STSMigrationError,\n    ensure_staff_agenda_state_schema,\n    make_migration_backup_path,",
        "import canonical helper",
    )
    start = text.find("AGENDA_STATE_COLUMNS:")
    end = text.find("@dataclass(frozen=True)\nclass MigrationStep")
    if start < 0 or end < 0 or end <= start:
        raise AssertionError("Agenda constants block not found in upgrade module")
    text = text[:start] + text[end:]
    text = remove_top_level_nodes(
        text,
        function_names={"_table_column_info", "_index_columns", "ensure_staff_agenda_state_schema"},
        if_contains="_sts_database_module",
    )
    if "_sts_database_module" in text:
        raise AssertionError("upgrade monkey-patch reference remains")
    write(path, text)


def patch_main_page() -> None:
    path = "src/ui/main_page_analysis_window.py"
    text = read(path)
    text = replace_once(
        text,
        "from src.ui.main_window import app_icon_path",
        "from src.ui.main_window import app_icon_path, qt_obj_alive",
        "import qt_obj_alive",
    )
    text = replace_class_method(text, "MainWindow", "_install_contract_status_widget", '''
def _install_contract_status_widget(self) -> None:
    calendar_widget = getattr(self, "_cal_widget", None)
    if not qt_obj_alive(calendar_widget):
        return
    calendar_card = calendar_widget.parentWidget()
    calendar_layout = calendar_card.layout() if calendar_card is not None else None
    if calendar_layout is None:
        return
    upcoming_scroll = getattr(self, "upcoming_scroll", None)
    if qt_obj_alive(upcoming_scroll):
        calendar_layout.removeWidget(upcoming_scroll)
        upcoming_scroll.hide()
    try:
        calendar_widget.ensurePolished()
        calendar_width = max(
            int(calendar_widget.sizeHint().width()),
            int(calendar_widget.minimumSizeHint().width()),
        )
        if calendar_width > 0:
            calendar_widget.setFixedWidth(calendar_width)
        calendar_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    except Exception:
        _log.exception("Calendar size could not be locked while installing status widget")
    widget = getattr(self, "contract_status_widget", None)
    if not qt_obj_alive(widget):
        widget = ContractStatusSummaryWidget(calendar_card)
        widget.open_analysis_requested.connect(self.open_analysis_center)
        self.contract_status_widget = widget
    elif widget.parentWidget() is not calendar_card:
        widget.setParent(calendar_card)
    if calendar_layout.indexOf(widget) >= 0:
        calendar_layout.removeWidget(widget)
    agenda = getattr(self, "agenda_compact_widget", None)
    agenda_index = calendar_layout.indexOf(agenda) if qt_obj_alive(agenda) else -1
    calendar_index = calendar_layout.indexOf(calendar_widget)
    insert_index = agenda_index if agenda_index >= 0 else calendar_index if calendar_index >= 0 else calendar_layout.count()
    calendar_layout.insertWidget(insert_index, widget, 0, Qt.AlignVCenter)
''')
    text = replace_class_method(text, "MainWindow", "_install_personal_agenda_widget", '''
def _install_personal_agenda_widget(self) -> None:
    calendar_widget = getattr(self, "_cal_widget", None)
    if not qt_obj_alive(calendar_widget):
        return
    calendar_card = calendar_widget.parentWidget()
    calendar_layout = calendar_card.layout() if calendar_card is not None else None
    if calendar_layout is None:
        return
    widget = getattr(self, "agenda_compact_widget", None)
    if not qt_obj_alive(widget):
        widget = AgendaCompactWidget(calendar_card)
        widget.open_details_requested.connect(self._open_agenda_details)
        widget.open_contract_requested.connect(self._open_agenda_contract)
        widget.item_dwell_seen_requested.connect(self._agenda_mark_seen)
        widget.snooze_requested.connect(self._agenda_snooze)
        self.agenda_compact_widget = widget
    elif widget.parentWidget() is not calendar_card:
        widget.setParent(calendar_card)
    if calendar_layout.indexOf(widget) >= 0:
        calendar_layout.removeWidget(widget)
    calendar_index = calendar_layout.indexOf(calendar_widget)
    insert_index = calendar_index if calendar_index >= 0 else calendar_layout.count()
    calendar_layout.insertWidget(insert_index, widget, 1, Qt.AlignVCenter)
    timer = getattr(self, "_agenda_refresh_timer", None)
    if not qt_obj_alive(timer):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(200)
        timer.timeout.connect(self.refresh_agenda)
        self._agenda_refresh_timer = timer
    self._sync_agenda_permission_visibility()
''')
    text = replace_class_method(text, "MainWindow", "_sync_agenda_permission_visibility", '''
def _sync_agenda_permission_visibility(self) -> bool:
    widget = getattr(self, "agenda_compact_widget", None)
    try:
        allowed = bool(
            self.current_staff
            and self.is_sts_mode()
            and self.has_permission("view_contracts")
        )
    except Exception:
        allowed = False
    if qt_obj_alive(widget):
        widget.setVisible(allowed)
    if not allowed:
        try:
            self.close_tool_window("agenda:detail")
        finally:
            self._agenda_detail_window = None
        self._agenda_snapshot = None
    return allowed
''')
    text = replace_class_method(text, "MainWindow", "_ensure_agenda_facade", '''
def _ensure_agenda_facade(self) -> PersonalAgendaFacade | None:
    if not self.store or not self.is_sts_mode():
        return None
    db = getattr(self.store, "db", None)
    if db is None:
        return None
    if self._agenda_facade is None or self._agenda_bound_db is not db:
        try:
            self.close_tool_window("agenda:detail")
        finally:
            self._agenda_detail_window = None
        self._agenda_snapshot = None
        self._agenda_bound_db = db
        self._agenda_facade = PersonalAgendaFacade(db)
    return self._agenda_facade
''')
    text = replace_class_method(text, "MainWindow", "_open_agenda_details", '''
def _clear_agenda_detail_reference(self, expected) -> None:
    if getattr(self, "_agenda_detail_window", None) is expected:
        self._agenda_detail_window = None

def _create_agenda_detail_window(self) -> AgendaDetailWindow:
    detail = AgendaDetailWindow(self)
    detail.open_contract_requested.connect(self._open_agenda_contract)
    detail.item_dwell_seen_requested.connect(self._agenda_mark_seen)
    detail.snooze_requested.connect(self._agenda_snooze)
    detail.refresh_requested.connect(lambda: self.refresh_agenda(touch_presented=True))
    detail.destroyed.connect(
        lambda *_args, expected=detail: self._clear_agenda_detail_reference(expected)
    )
    self._agenda_detail_window = detail
    return detail

def _open_agenda_details(self) -> None:
    if not self._sync_agenda_permission_visibility():
        return
    detail = self.open_or_raise_tool_window(
        "agenda:detail",
        "Gündemim",
        self._create_agenda_detail_window,
    )
    self._agenda_detail_window = detail
    snapshot = getattr(self, "_agenda_snapshot", None)
    if snapshot is not None:
        detail.set_snapshot(snapshot)
    else:
        detail.set_loading(True)
        self.refresh_agenda(touch_presented=True)
    detail.focus_item()
''')
    text = replace_class_method(text, "MainWindow", "_reset_agenda_binding", '''
def _reset_agenda_binding(self) -> None:
    timer = getattr(self, "_agenda_refresh_timer", None)
    if qt_obj_alive(timer):
        timer.stop()
    try:
        self.close_tool_window("agenda:detail")
    finally:
        self._agenda_detail_window = None
    self._agenda_snapshot = None
    self._agenda_facade = None
    self._agenda_bound_db = None
    widget = getattr(self, "agenda_compact_widget", None)
    if qt_obj_alive(widget):
        widget.clear()
        widget.hide()
''')
    text = replace_class_method(text, "MainWindow", "closeEvent", '''
def closeEvent(self, event):
    timer = getattr(self, "_agenda_refresh_timer", None)
    if qt_obj_alive(timer):
        timer.stop()
    try:
        self.close_tool_window("agenda:detail")
    finally:
        self._agenda_detail_window = None
    super().closeEvent(event)
''')
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_sts_schema_upgrade.py"
    text = read(path)
    if "from src.auth import ensure_staff_table" not in text:
        text = replace_once(text, "import pytest\n\n", "import pytest\n\nfrom src.auth import ensure_staff_table\n", "import staff helper")
    text = replace_once(text, "    try:\n        _set_version(conn, version)", "    try:\n        ensure_staff_table(conn)\n        _set_version(conn, version)", "add staff parent")
    text = replace_once(text, "assert result.to_version == CURRENT_SCHEMA_VERSION == 17", "assert result.to_version == CURRENT_SCHEMA_VERSION == 18", "target v18")
    text = replace_once(text, '        "v16_to_v17_share_cancellation_audit",\n    )', '        "v16_to_v17_share_cancellation_audit",\n        "v17_to_v18_staff_agenda_state",\n    )', "v14 chain")
    text = text.replace("def test_v16_runs_only_v16_to_v17", "def test_v16_runs_v16_to_v17_and_v17_to_v18", 1)
    text = replace_once(text, '    assert result.applied_migrations == (\n        "v16_to_v17_share_cancellation_audit",\n    )\n    assert read_sts_schema_version(path) == 17', '    assert result.applied_migrations == (\n        "v16_to_v17_share_cancellation_audit",\n        "v17_to_v18_staff_agenda_state",\n    )\n    assert read_sts_schema_version(path) == 18', "v16 chain")
    write(path, text)

    path = "tests/test_sts_schema_upgrade_gate.py"
    text = read(path)
    text = replace_once(text, '        _drop_share_package_indexes(conn)\n        conn.execute("DROP TABLE IF EXISTS share_packages")', '        _drop_share_package_indexes(conn)\n        if version <= 17:\n            conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_staff")\n            conn.execute("DROP INDEX IF EXISTS idx_staff_agenda_state_snoozed")\n            conn.execute("DROP TABLE IF EXISTS staff_agenda_state")\n        conn.execute("DROP TABLE IF EXISTS share_packages")', "historical v17")
    text = text.replace("def test_current_v17_with_v16_shape_is_rejected_instead_of_silent_noop", "def test_current_v18_with_v16_shape_is_rejected_instead_of_silent_noop", 1)
    text = text.replace('"schema_fingerprint_mismatch=v17"', '"schema_fingerprint_mismatch=v18"', 1)
    text = replace_once(text, '    assert result.applied_migrations == (\n        "v16_to_v17_share_cancellation_audit",\n    )', '    assert result.applied_migrations == (\n        "v16_to_v17_share_cancellation_audit",\n        "v17_to_v18_staff_agenda_state",\n    )', "gate v16 chain")
    text = text.replace('"schema_fingerprint_not_registered=v17"', '"schema_fingerprint_not_registered=v18"', 1)
    write(path, text)

    path = "tests/test_agenda_schema_v18_integration.py"
    text = read(path)
    text = replace_once(text, "from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase, read_sts_schema_version", "from src.services.sts_database import (\n    CURRENT_SCHEMA_VERSION,\n    STSDatabase,\n    ensure_staff_agenda_state_schema,\n    read_sts_schema_version,\n)", "canonical helper import")
    text = text.replace("upgrade.ensure_staff_agenda_state_schema(conn)", "ensure_staff_agenda_state_schema(conn)")
    write(path, text)

    path = "tests/smoke_sts_database.py"
    text = read(path)
    text = replace_once(text, "        'share_packages': {'share_package_id', 'contract_id', 'contract_merge_uid', 'source_contract_revision', 'permission_mode', 'share_format_version', 'snapshot_format_version', 'base_snapshot_sha256', 'status'},", "        'share_packages': {'share_package_id', 'contract_id', 'contract_merge_uid', 'source_contract_revision', 'permission_mode', 'share_format_version', 'snapshot_format_version', 'base_snapshot_sha256', 'status'},\n        'staff_agenda_state': {'staff_id', 'agenda_key', 'first_presented_at', 'last_presented_at', 'seen_at', 'seen_version', 'snoozed_until', 'snoozed_version', 'snoozed_severity', 'dismissed_at', 'dismissed_version', 'created_at', 'updated_at'},", "smoke columns")
    text = replace_once(text, "'ux_contract_file_folders_merge_uid', 'ux_contract_files_merge_uid',", "'ux_contract_file_folders_merge_uid', 'ux_contract_files_merge_uid', 'idx_staff_agenda_state_staff', 'idx_staff_agenda_state_snoozed',", "smoke indexes")
    write(path, text)

    path = "tests/test_main_page_agenda_integration.py"
    text = read(path)
    text = replace_top_level_function(text, "test_detail_window_reused_or_single_instance", '''
def test_detail_window_uses_stable_current_main_registry():
    source = ast.get_source_segment(_source(), _method("_open_agenda_details"))
    assert "open_or_raise_tool_window" in source
    assert '"agenda:detail"' in source
    assert "self._create_agenda_detail_window" in source
''')
    text += '''\n\ndef test_widget_and_timer_installation_are_idempotent_by_construction():\n    status = ast.get_source_segment(_source(), _method("_install_contract_status_widget"))\n    agenda = ast.get_source_segment(_source(), _method("_install_personal_agenda_widget"))\n    assert "qt_obj_alive(widget)" in status\n    assert "qt_obj_alive(widget)" in agenda\n    assert "qt_obj_alive(timer)" in agenda\n'''
    write(path, text)

    path = "tests/test_agenda_current_main_composition.py"
    text = read(path)
    text += '''\n\ndef test_agenda_detail_registry_contract_is_present():\n    source = _text()\n    detail = ast.get_source_segment(source, _method("_open_agenda_details"))\n    assert '"agenda:detail"' in detail\n    assert "open_or_raise_tool_window" in detail\n\n\ndef test_status_agenda_and_timer_installs_are_idempotent():\n    source = _text()\n    status = ast.get_source_segment(source, _method("_install_contract_status_widget"))\n    agenda = ast.get_source_segment(source, _method("_install_personal_agenda_widget"))\n    assert "qt_obj_alive(widget)" in status\n    assert "qt_obj_alive(widget)" in agenda\n    assert "qt_obj_alive(timer)" in agenda\n'''
    write(path, text)


def verify_source_contracts() -> None:
    database = read("src/services/sts_database.py")
    upgrade = read("src/services/sts_schema_upgrade.py")
    ui = read("src/ui/main_page_analysis_window.py")
    assert database.count("def ensure_staff_agenda_state_schema(") == 1
    assert database.count("CREATE TABLE IF NOT EXISTS staff_agenda_state") == 1
    assert "migrated.extend(ensure_staff_agenda_state_schema(self.conn))" in database
    assert "def ensure_staff_agenda_state_schema(" not in upgrade
    assert "_sts_database_module" not in upgrade
    assert "v17_to_v18_staff_agenda_state" in upgrade
    assert '"agenda:detail"' in ui
    assert "open_or_raise_tool_window(" in ui
    assert "qt_obj_alive(widget)" in ui
    assert "qt_obj_alive(timer)" in ui


def main() -> None:
    parent = run("git", "rev-parse", "HEAD^")
    if parent != EXPECTED_BASE_HEAD:
        raise RuntimeError(f"bootstrap parent mismatch: expected={EXPECTED_BASE_HEAD} actual={parent}")
    changed = set(run("git", "diff", "--name-only", "HEAD^", "HEAD").splitlines())
    allowed = {
        ".github/workflows/agenda-stage-05b-r1-online-fix.yml",
        "tools/validation/apply_agenda_stage_05b_r1.py",
    }
    if changed != allowed:
        raise RuntimeError(f"bootstrap commit contains unexpected paths: {sorted(changed)}")
    patch_sts_database()
    patch_sts_schema_upgrade()
    patch_main_page()
    patch_tests()
    verify_source_contracts()
    for path in (
        "src/services/sts_database.py",
        "src/services/sts_schema_upgrade.py",
        "src/services/sts_schema_upgrade_gate.py",
        "src/ui/main_page_analysis_window.py",
    ):
        ast.parse(read(path))
    print("stage5b_r1_patch=PASS")


if __name__ == "__main__":
    main()
