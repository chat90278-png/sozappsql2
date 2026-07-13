from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

TARGETED_TESTS = [
    "tests/test_returned_share_agenda_provider.py",
    "tests/test_agenda_source_repository.py",
    "tests/test_deadline_agenda_provider.py",
    "tests/test_unknown_date_agenda_provider.py",
    "tests/test_staff_agenda_service.py",
    "tests/test_agenda_models.py",
    "tests/test_agenda_lifecycle.py",
    "tests/test_agenda_state_repository.py",
    "tests/test_personal_agenda_facade.py",
    "tests/test_agenda_context_factory.py",
    "tests/test_agenda_presentation.py",
    "tests/test_agenda_compact_widget.py",
    "tests/test_agenda_detail_window.py",
    "tests/test_main_page_agenda_integration.py",
    "tests/test_sts_database_transactions.py",
    "tests/test_agenda_keys.py",
    "tests/test_agenda_deadline_stage.py",
]

SMOKE_CODE = r'''
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_RETURNED
from src.services.agenda_source_repository import AgendaSourceRepository
from src.services.personal_agenda_facade import PersonalAgendaFacade
from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase

NOW = datetime(2026, 7, 13, 12, 0, 0)
PACKAGE_ID = "stage3b-runtime-package"
BASE_HASH = "stage3b-base-hash"
REVISION = 4
EXPECTED_KEY = f"returned_share:share_package:{PACKAGE_ID}"
EXPECTED_VERSION = f"RETURNED:{REVISION}:{BASE_HASH}"

print("RETURNED_SHARE_SMOKE_BEGIN")
with tempfile.TemporaryDirectory(prefix="stage3b-smoke-") as td:
    db = STSDatabase(Path(td) / "returned-share-smoke.sts", source="Stage 3B Runtime Validation")
    try:
        with db.tx():
            platform_id = db.conn.execute(
                "INSERT INTO platforms(name,display_name,is_active) VALUES(?,?,1)",
                ("Stage3B Platform", "Stage3B Platform"),
            ).lastrowid
            staff_id = db.conn.execute(
                "INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES(?,?,?,?,1)",
                ("stage3b-device", "Stage 3B Personel", "x", "personnel"),
            ).lastrowid
            contract_id = db.conn.execute(
                """
                INSERT INTO contracts(
                    platform_id,contract_no,contract_type,status,completion_date,
                    merge_uid,revision
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    platform_id,
                    "STAGE3B-C-1",
                    "Ana",
                    "Açık",
                    "2027-12-31",
                    "stage3b-contract-merge-uid",
                    REVISION,
                ),
            ).lastrowid
            db.conn.execute(
                "INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,0,1)",
                (contract_id, platform_id),
            )
            db.conn.execute(
                "INSERT INTO contract_responsible_engineers(contract_id,staff_id,sort_order,is_primary) VALUES(?,?,0,1)",
                (contract_id, staff_id),
            )
            registry_id = db.conn.execute(
                """
                INSERT INTO share_packages(
                    share_package_id,contract_id,contract_merge_uid,
                    source_contract_revision,permission_mode,share_format_version,
                    snapshot_format_version,base_snapshot_sha256,created_at,
                    created_by_staff_id,created_by_username,created_by_full_name,
                    exported_filename,status,last_imported_at,
                    last_imported_by_staff_id,last_remote_snapshot_sha256,
                    return_count
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    PACKAGE_ID,
                    contract_id,
                    "stage3b-contract-merge-uid",
                    REVISION,
                    "edit",
                    2,
                    1,
                    BASE_HASH,
                    "2026-07-10 09:00:00",
                    staff_id,
                    "stage3b-device",
                    "Stage 3B Personel",
                    "stage3b-share.sts",
                    SHARE_STATUS_RETURNED,
                    "2026-07-13 10:00:00",
                    staff_id,
                    "stage3b-remote-hash",
                    1,
                ),
            ).lastrowid

        current_staff = {
            "id": int(staff_id),
            "is_active": 1,
            "full_name": "Stage 3B Personel",
            "device_name": "stage3b-device",
            "permissions": {"view_contracts"},
        }
        facade = PersonalAgendaFacade(db)
        repository = AgendaSourceRepository(db)
        before_changes = db.conn.total_changes
        source_rows = repository.list_returned_share_sources([int(contract_id)])
        after_changes = db.conn.total_changes
        assert before_changes == after_changes
        assert len(source_rows) == 1
        assert source_rows[0].share_package_id == PACKAGE_ID

        snapshot = facade.load(current_staff, now=NOW, compact_limit=2, detail_limit=20, touch_presented=False)
        returned = [item for item in snapshot.all_items if item.kind == "returned_share"]
        assert len(returned) == 1
        item = returned[0]
        assert item.key == EXPECTED_KEY
        assert item.version == EXPECTED_VERSION
        assert item.priority == 850
        assert item.severity == AgendaSeverity.ATTENTION
        assert item.lifecycle_type == AgendaLifecycleType.CONDITION
        assert item.supports_snooze is True
        assert item.action_hints == ("open_contract",)
        assert int(item.contract_id) == int(contract_id)
        assert "merge_share" not in item.action_hints
        assert snapshot.counts_by_kind.get("returned_share") == 1

        facade.mark_seen(current_staff, item, seen_at=NOW)
        seen_snapshot = facade.load(current_staff, now=NOW, compact_limit=2, detail_limit=20, touch_presented=False)
        assert any(value.key == EXPECTED_KEY for value in seen_snapshot.all_items)
        assert EXPECTED_KEY not in seen_snapshot.new_keys

        facade.snooze(current_staff, item, until=NOW + timedelta(days=1), now=NOW)
        snoozed_snapshot = facade.load(current_staff, now=NOW, compact_limit=2, detail_limit=20, touch_presented=False)
        assert not any(value.key == EXPECTED_KEY for value in snoozed_snapshot.all_items)
        assert snoozed_snapshot.snoozed_count == 1

        facade.clear_snooze(current_staff, item)
        restored_snapshot = facade.load(current_staff, now=NOW, compact_limit=2, detail_limit=20, touch_presented=False)
        assert any(value.key == EXPECTED_KEY for value in restored_snapshot.all_items)

        with db.tx():
            db.conn.execute("UPDATE share_packages SET status=? WHERE id=?", (SHARE_STATUS_MERGED, int(registry_id)))
        final_snapshot = facade.load(current_staff, now=NOW, compact_limit=2, detail_limit=20, touch_presented=False)
        assert not any(value.kind == "returned_share" for value in final_snapshot.all_items)

        print(f"SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}")
        print("RETURNED_COUNT=1")
        print(f"KEY={EXPECTED_KEY}")
        print(f"VERSION={EXPECTED_VERSION}")
        print("SEEN_REMAINS_ACTIVE=1")
        print("SNOOZE_HIDES=1")
        print("CLEAR_RESTORES=1")
        print("FINAL_STATUS_REMOVES=1")
        print("READ_ONLY_SOURCE=1")
        print("MERGE_ACTION_PRESENT=0")
        print("RETURNED_SHARE_SMOKE=PASS")
    finally:
        db.close()
print("RETURNED_SHARE_SMOKE_END")
'''


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None, output_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(completed.stdout or "", encoding="utf-8")
    return completed


def _materialize(repo_url: str, sha: str, target: Path) -> str:
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"Materialization target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    for command in (
        ["git", "init", "-q"],
        ["git", "remote", "add", "origin", repo_url],
        ["git", "fetch", "--depth=1", "origin", sha],
        ["git", "checkout", "--detach", "FETCH_HEAD"],
    ):
        result = _run(command, cwd=target)
        if result.returncode != 0:
            raise RuntimeError(f"Materialization failed for {sha}: {' '.join(command)}\n{result.stdout}")
    actual = _run(["git", "rev-parse", "HEAD"], cwd=target)
    if actual.returncode != 0:
        raise RuntimeError(f"rev-parse failed for {sha}: {actual.stdout}")
    actual_sha = str(actual.stdout or "").strip()
    if actual_sha != sha:
        raise RuntimeError(f"Expected {sha}, materialized {actual_sha}")
    return actual_sha


def _pytest_summary(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if " in " in line and any(token in line for token in (" passed", " failed", " error", " skipped", " xfailed", " xpassed")):
            return line.lstrip("= ").rstrip("= ").strip()
    return lines[-1] if lines else ""


def _normalize_message(value: str) -> str:
    return " ".join(str(value or "").split())[:1200]


def _parse_junit(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"JUnit file missing or empty: {path}")
    root = ET.parse(path).getroot()
    direct_suites = [root] if root.tag == "testsuite" else list(root.findall("./testsuite"))
    if root.tag == "testsuites" and root.attrib.get("tests") is not None:
        totals = {
            "tests": int(float(root.attrib.get("tests", "0") or 0)),
            "failures": int(float(root.attrib.get("failures", "0") or 0)),
            "errors": int(float(root.attrib.get("errors", "0") or 0)),
            "skipped": int(float(root.attrib.get("skipped", "0") or 0)),
            "time": float(root.attrib.get("time", "0") or 0),
        }
    else:
        totals = {
            "tests": sum(int(float(s.attrib.get("tests", "0") or 0)) for s in direct_suites),
            "failures": sum(int(float(s.attrib.get("failures", "0") or 0)) for s in direct_suites),
            "errors": sum(int(float(s.attrib.get("errors", "0") or 0)) for s in direct_suites),
            "skipped": sum(int(float(s.attrib.get("skipped", "0") or 0)) for s in direct_suites),
            "time": sum(float(s.attrib.get("time", "0") or 0) for s in direct_suites),
        }
    failures: dict[str, dict[str, str]] = {}
    for case in root.iter("testcase"):
        classname = str(case.attrib.get("classname", "") or "")
        name = str(case.attrib.get("name", "") or "")
        node = f"{classname}::{name}"
        for kind in ("failure", "error"):
            child = case.find(kind)
            if child is not None:
                failures[node] = {"node": node, "kind": kind, "message": _normalize_message(child.attrib.get("message", "") or child.text or "")}
                break
    return {
        "totals": totals,
        "failure_nodes": sorted(failures),
        "failure_details": [failures[node] for node in sorted(failures)],
    }


def _png_metadata(path: Path) -> dict[str, Any]:
    return {"path": str(path).replace("\\", "/"), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}


def _qt_probe(scale: str, output_dir: Path) -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    result: dict[str, Any] = {"bootstrap": False, "scale": scale, "result": "INCOMPLETE", "reason": "", "qapplication_constructed": False}
    token = "100" if scale == "1.00" else "150"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"scale-{token}.json"

    try:
        root_text = str(repo_root)
        cleaned = []
        for entry in sys.path:
            try:
                if str(Path(entry or ".").resolve()) == root_text:
                    continue
            except Exception:
                pass
            cleaned.append(entry)
        sys.path[:] = [root_text, *cleaned]
        os.chdir(repo_root)
        for required_path in (
            repo_root / "src",
            repo_root / "src/services/personal_agenda_facade.py",
            repo_root / "src/ui/agenda_compact_widget.py",
            repo_root / "src/ui/agenda_detail_window.py",
        ):
            if not required_path.exists():
                raise RuntimeError(f"Required bootstrap path missing: {required_path}")
        result.update({"bootstrap": True, "repo_root": root_text, "cwd": str(Path.cwd()), "sys_path_0": sys.path[0]})
        print("QT_RENDER_BOOTSTRAP_BEGIN")
        print(f"REPO_ROOT={repo_root}")
        print(f"CWD={Path.cwd()}")
        print(f"SYS_PATH_0={sys.path[0]}")
        print("QT_RENDER_BOOTSTRAP=PASS")
        print("QT_RENDER_BOOTSTRAP_END")
    except Exception as exc:
        result["reason"] = f"bootstrap: {type(exc).__name__}: {exc}"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    try:
        from datetime import datetime
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QToolButton, QWidget
        from src.models.share_models import SHARE_STATUS_RETURNED
        from src.services.personal_agenda_facade import PersonalAgendaFacade
        from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSDatabase
        from src.ui.agenda_compact_widget import AgendaCompactWidget
        from src.ui.agenda_detail_window import AgendaDetailWindow
    except Exception as exc:
        result["reason"] = f"imports: {type(exc).__name__}: {exc}"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    app = QApplication.instance() or QApplication([])
    result["qapplication_constructed"] = True
    db = None
    try:
        now = datetime(2026, 7, 13, 12, 0, 0)
        package_id = "stage3b-render-package"
        base_hash = "stage3b-render-base"
        revision = 4
        expected_key = f"returned_share:share_package:{package_id}"
        expected_version = f"RETURNED:{revision}:{base_hash}"
        temp_dir = tempfile.TemporaryDirectory(prefix=f"stage3b-render-{token}-")
        try:
            db = STSDatabase(Path(temp_dir.name) / "returned-render.sts", source="Stage 3B Qt Render Validation")
            with db.tx():
                platform_id = db.conn.execute("INSERT INTO platforms(name,display_name,is_active) VALUES(?,?,1)", ("Render Platform", "Render Platform")).lastrowid
                staff_id = db.conn.execute("INSERT INTO staff(device_name,full_name,password_hash,role,is_active) VALUES(?,?,?,?,1)", ("render-device", "Render Personel", "x", "personnel")).lastrowid
                contract_id = db.conn.execute(
                    """
                    INSERT INTO contracts(platform_id,contract_no,contract_type,status,completion_date,merge_uid,revision)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (platform_id, "RENDER-C-1", "Ana", "Açık", "2027-12-31", "render-contract-merge-uid", revision),
                ).lastrowid
                db.conn.execute("INSERT OR IGNORE INTO contract_platforms(contract_id,platform_id,sort_order,is_primary) VALUES(?,?,0,1)", (contract_id, platform_id))
                db.conn.execute("INSERT INTO contract_responsible_engineers(contract_id,staff_id,sort_order,is_primary) VALUES(?,?,0,1)", (contract_id, staff_id))
                db.conn.execute(
                    """
                    INSERT INTO share_packages(
                        share_package_id,contract_id,contract_merge_uid,source_contract_revision,
                        permission_mode,share_format_version,snapshot_format_version,base_snapshot_sha256,
                        created_at,created_by_staff_id,created_by_username,created_by_full_name,
                        exported_filename,status,last_imported_at,last_imported_by_staff_id,
                        last_remote_snapshot_sha256,return_count
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (package_id, contract_id, "render-contract-merge-uid", revision, "edit", 2, 1, base_hash, "2026-07-10 09:00:00", staff_id, "render-device", "Render Personel", "render-share.sts", SHARE_STATUS_RETURNED, "2026-07-13 10:00:00", staff_id, "render-remote-hash", 1),
                )

            current_staff = {"id": int(staff_id), "is_active": 1, "full_name": "Render Personel", "device_name": "render-device", "permissions": {"view_contracts"}}
            snapshot = PersonalAgendaFacade(db).load(current_staff, now=now, compact_limit=2, detail_limit=20, touch_presented=False)
            returned = [item for item in snapshot.all_items if item.kind == "returned_share"]
            assert len(returned) == 1
            returned_item = returned[0]
            assert returned_item.key == expected_key
            assert returned_item.version == expected_version

            compact = AgendaCompactWidget()
            compact.resize(420, 112)
            compact.set_snapshot(snapshot)
            compact_contract_ids: list[int] = []
            compact_seen: list[str] = []
            compact.open_contract_requested.connect(compact_contract_ids.append)
            compact.item_dwell_seen_requested.connect(lambda item: compact_seen.append(item.key))
            compact.show()
            app.processEvents()
            QTest.qWait(100)
            app.processEvents()
            compact_rows = compact.findChildren(QFrame, "agendaCompactRow")
            assert 1 <= len(compact_rows) <= 2
            compact_returned_rows = [row for row in compact_rows if getattr(getattr(row, "item", None), "key", "") == expected_key]
            assert len(compact_returned_rows) == 1
            compact_row = compact_returned_rows[0]
            assert compact_row.isVisible() and compact_row.width() > 0 and compact_row.height() > 0
            assert "geri döndü" in compact_row.item.title
            compact_offenders = []
            body = compact.body
            for row in compact_rows:
                geo = row.geometry()
                if geo.x() < -2 or geo.y() < -2 or geo.right() > body.width() + 2 or geo.bottom() > body.height() + 2:
                    compact_offenders.append({"key": row.property("agendaKey"), "geometry": [geo.x(), geo.y(), geo.width(), geo.height()], "body": [body.width(), body.height()]})
            assert not compact_offenders
            compact_open = compact_row.findChild(QToolButton, "agendaCompactOpenContract")
            assert compact_open is not None and compact_open.isVisible()
            QTest.mouseClick(compact_open, Qt.LeftButton)
            app.processEvents()
            assert compact_contract_ids == [int(contract_id)]
            QTest.mouseClick(compact_row, Qt.LeftButton)
            QTest.qWait(450)
            app.processEvents()
            dwell_before = len(compact_seen)
            assert dwell_before == 0
            QTest.qWait(300)
            app.processEvents()
            dwell_after = len(compact_seen)
            assert dwell_after == 1 and compact_seen == [expected_key]
            compact_png = output_dir / f"compact-returned-share-{token}.png"
            assert compact.grab().save(str(compact_png))

            detail = AgendaDetailWindow()
            detail.resize(760, 560)
            detail.set_snapshot(snapshot)
            detail_contract_ids: list[int] = []
            snooze_codes: list[str] = []
            detail.open_contract_requested.connect(detail_contract_ids.append)
            detail.snooze_requested.connect(lambda _item, preset: snooze_codes.append(preset))
            detail.show()
            app.processEvents()
            QTest.qWait(100)
            app.processEvents()
            detail_rows = detail.findChildren(QFrame, "agendaDetailRow")
            returned_detail_rows = [row for row in detail_rows if getattr(getattr(row, "item", None), "key", "") == expected_key]
            assert len(returned_detail_rows) == 1
            detail_row = returned_detail_rows[0]
            assert detail_row.isVisible() and detail_row.width() > 0 and detail_row.height() > 0
            assert "geri döndü" in detail_row.item.title
            detail_open = detail_row.findChild(QPushButton, "agendaDetailOpenContract")
            assert detail_open is not None and detail_open.isVisible()
            QTest.mouseClick(detail_open, Qt.LeftButton)
            app.processEvents()
            assert detail_contract_ids == [int(contract_id)]
            snooze_button = detail_row.findChild(QToolButton, "agendaDetailSnooze")
            assert snooze_button is not None and snooze_button.isVisible()
            menu = snooze_button.menu()
            assert menu is not None
            actions = menu.actions()
            assert [action.text() for action in actions] == ["Yarın", "3 Gün", "1 Hafta"]
            for action in actions:
                action.trigger()
                app.processEvents()
            assert snooze_codes == ["tomorrow", "three_days", "one_week"]
            zero_size_actions = [widget.objectName() for widget in detail_row.findChildren(QWidget) if widget.isVisible() and widget.objectName() in {"agendaDetailOpenContract", "agendaDetailSnooze"} and (widget.width() <= 0 or widget.height() <= 0)]
            assert not zero_size_actions
            assert bool(detail.windowFlags() & Qt.Tool)
            assert detail.windowModality() == Qt.NonModal
            detail_png = output_dir / f"detail-returned-share-{token}.png"
            assert detail.grab().save(str(detail_png))

            def inspect_image(path: Path) -> dict[str, Any]:
                assert path.exists() and path.stat().st_size > 500
                image = QImage(str(path))
                assert not image.isNull() and image.width() > 0 and image.height() > 0
                first = None
                non_uniform = False
                alpha_present = False
                step_x = max(1, image.width() // 200)
                step_y = max(1, image.height() // 200)
                for y in range(0, image.height(), step_y):
                    for x in range(0, image.width(), step_x):
                        color = image.pixelColor(x, y)
                        rgba = color.rgba()
                        if first is None:
                            first = rgba
                        elif rgba != first:
                            non_uniform = True
                        if color.alpha() > 0:
                            alpha_present = True
                        if non_uniform and alpha_present:
                            break
                    if non_uniform and alpha_present:
                        break
                assert non_uniform and alpha_present
                return {"path": str(path).replace("\\", "/"), "width": image.width(), "height": image.height(), "size_bytes": path.stat().st_size, "non_uniform": non_uniform, "alpha_present": alpha_present}

            compact_meta = inspect_image(compact_png)
            detail_meta = inspect_image(detail_png)
            screen = app.primaryScreen()
            result.update({
                "PySide6": pyside_version,
                "schema_version": CURRENT_SCHEMA_VERSION,
                "DPR": float(screen.devicePixelRatio()) if screen else None,
                "logical_DPI": float(screen.logicalDotsPerInch()) if screen else None,
                "returned_item_rendered": True,
                "returned_key": returned_item.key,
                "returned_version": returned_item.version,
                "compact_size": [compact.width(), compact.height()],
                "compact_rows": len(compact_rows),
                "compact_offenders": compact_offenders,
                "compact_contract_signal": compact_contract_ids,
                "dwell_before_500ms": dwell_before,
                "dwell_after_total_750ms": dwell_after,
                "detail_size": [detail.width(), detail.height()],
                "detail_rows": len(detail_rows),
                "snooze_control": True,
                "snooze_codes": snooze_codes,
                "detail_contract_signal": detail_contract_ids,
                "tool_window": True,
                "non_modal": True,
                "pngs": [compact_meta, detail_meta],
                "result": "PASS",
                "reason": "real facade returned-share compact/detail render passed",
            })
            compact.close()
            detail.close()
            app.processEvents()
            QTest.qWait(50)
            app.processEvents()
        finally:
            if db is not None:
                db.close()
                db = None
            temp_dir.cleanup()
    except Exception as exc:
        result["result"] = "FAIL"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("QT_RENDER_RESULT=FAIL")
        print(f"QT_RENDER_REASON={result['reason']}")
        return 1

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("QT_RENDER_RESULT=PASS")
    print(f"QT_RENDER_SCALE={scale}")
    print(f"RETURNED_KEY={result['returned_key']}")
    print(f"RETURNED_VERSION={result['returned_version']}")
    return 0


def _parent(args: argparse.Namespace) -> int:
    root = Path.cwd()
    out = root / "validation-out"
    baseline_dir = out / "work" / "baseline"
    feature_dir = out / "work" / "feature"
    visual_dir = out / "visual"
    out.mkdir(parents=True, exist_ok=True)
    visual_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "baseline_expected_sha": args.baseline_sha,
        "feature_expected_sha": args.feature_sha,
        "baseline_actual_sha": "",
        "feature_actual_sha": "",
        "requirements_match": False,
        "compile_exit": None,
        "targeted_exit": None,
        "targeted_summary": "",
        "returned_share_smoke_exit": None,
        "returned_share_smoke_output": "",
        "agenda_schema_smoke_exit": None,
        "agenda_schema_smoke_output": "",
        "sts_db_smoke_exit": None,
        "sts_db_smoke_output": "",
        "scales": {},
        "visual_all_pass": False,
        "pngs": [],
        "baseline_pytest_exit": None,
        "feature_pytest_exit": None,
        "baseline_junit": None,
        "feature_junit": None,
        "feature_only_failure_nodes": [],
        "feature_only_failure_details": [],
        "gate": "INCOMPLETE",
        "gate_reason": "",
    }
    infrastructure_errors: list[str] = []
    product_failures: list[str] = []

    try:
        summary["baseline_actual_sha"] = _materialize(args.repo_url, args.baseline_sha, baseline_dir)
        summary["feature_actual_sha"] = _materialize(args.repo_url, args.feature_sha, feature_dir)
    except Exception as exc:
        infrastructure_errors.append(f"materialization: {type(exc).__name__}: {exc}")

    if not infrastructure_errors:
        try:
            summary["requirements_match"] = (baseline_dir / "requirements.txt").read_bytes() == (feature_dir / "requirements.txt").read_bytes()
            if not summary["requirements_match"]:
                infrastructure_errors.append("requirements.txt byte mismatch")
        except Exception as exc:
            infrastructure_errors.append(f"requirements parity: {type(exc).__name__}: {exc}")

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUNBUFFERED"] = "1"

    if not infrastructure_errors:
        compile_run = _run([sys.executable, "-m", "compileall", "-q", "src", "tests"], cwd=feature_dir, env=env, output_path=out / "feature-compile.txt")
        summary["compile_exit"] = compile_run.returncode
        if compile_run.returncode != 0:
            product_failures.append("feature compile failed")

        targeted_run = _run([sys.executable, "-m", "pytest", "-q", *TARGETED_TESTS], cwd=feature_dir, env=env, output_path=out / "stage3b-targeted.txt")
        summary["targeted_exit"] = targeted_run.returncode
        summary["targeted_summary"] = _pytest_summary(targeted_run.stdout)
        if targeted_run.returncode != 0:
            product_failures.append("targeted pytest failed")

        smoke_run = _run([sys.executable, "-c", SMOKE_CODE], cwd=feature_dir, env=env, output_path=out / "returned-share-smoke.txt")
        summary["returned_share_smoke_exit"] = smoke_run.returncode
        summary["returned_share_smoke_output"] = smoke_run.stdout
        if smoke_run.returncode != 0 or "RETURNED_SHARE_SMOKE=PASS" not in smoke_run.stdout:
            product_failures.append("returned-share registry/facade smoke failed")

        agenda_smoke = _run([sys.executable, "tests/smoke_sts_agenda_schema.py"], cwd=feature_dir, env=env, output_path=out / "agenda-schema-smoke.txt")
        summary["agenda_schema_smoke_exit"] = agenda_smoke.returncode
        summary["agenda_schema_smoke_output"] = agenda_smoke.stdout
        if agenda_smoke.returncode != 0 or "agenda_schema=PASS" not in agenda_smoke.stdout or "schema_version=18" not in agenda_smoke.stdout:
            product_failures.append("Agenda schema smoke failed")

        sts_smoke = _run([sys.executable, "tests/smoke_sts_database.py"], cwd=feature_dir, env=env, output_path=out / "sts-db-smoke.txt")
        summary["sts_db_smoke_exit"] = sts_smoke.returncode
        summary["sts_db_smoke_output"] = sts_smoke.stdout
        if sts_smoke.returncode != 0:
            product_failures.append("existing STS database smoke failed")

        child_script = feature_dir / ".github/validation/gundemim_stage3b_gate.py"
        if not child_script.exists():
            infrastructure_errors.append("materialized feature gate script missing")
        else:
            for scale, token in (("1.00", "100"), ("1.50", "150")):
                child_env = dict(env)
                child_env["QT_SCALE_FACTOR"] = scale
                child_env["QT_ENABLE_HIGHDPI_SCALING"] = "1"
                feature_root = str(feature_dir.resolve())
                existing_pythonpath = child_env.get("PYTHONPATH", "")
                child_env["PYTHONPATH"] = feature_root if not existing_pythonpath else feature_root + os.pathsep + existing_pythonpath
                child_run = _run(
                    [sys.executable, str(child_script), "--qt-render-probe", "--scale", scale, "--output-dir", str(visual_dir.resolve())],
                    cwd=feature_dir,
                    env=child_env,
                    output_path=visual_dir / f"render-scale-{token}.txt",
                )
                scale_json = visual_dir / f"scale-{token}.json"
                scale_data: dict[str, Any] = {"exit": child_run.returncode, "result": "INCOMPLETE", "reason": "scale JSON missing"}
                if scale_json.exists():
                    try:
                        scale_data.update(json.loads(scale_json.read_text(encoding="utf-8")))
                    except Exception as exc:
                        scale_data["reason"] = f"scale JSON parse: {exc}"
                summary["scales"][token] = scale_data
                if child_run.returncode == 2 or scale_data.get("result") == "INCOMPLETE":
                    infrastructure_errors.append(f"Qt scale {scale} infrastructure incomplete: {scale_data.get('reason')}")
                elif child_run.returncode != 0 or scale_data.get("result") != "PASS":
                    product_failures.append(f"Qt scale {scale} render failed: {scale_data.get('reason')}")

        expected_pngs = [
            visual_dir / "compact-returned-share-100.png",
            visual_dir / "detail-returned-share-100.png",
            visual_dir / "compact-returned-share-150.png",
            visual_dir / "detail-returned-share-150.png",
        ]
        summary["pngs"] = [_png_metadata(path) for path in expected_pngs]
        if not infrastructure_errors:
            for meta in summary["pngs"]:
                if not meta["exists"] or int(meta["size_bytes"]) <= 500:
                    product_failures.append(f"PNG evidence invalid: {meta['path']}")
        summary["visual_all_pass"] = (
            not any("Qt scale" in reason for reason in infrastructure_errors)
            and not any("Qt scale" in reason or "PNG" in reason for reason in product_failures)
            and len(summary["pngs"]) == 4
        )

        baseline_xml = out / "baseline.xml"
        feature_xml = out / "feature.xml"
        baseline_full = _run([sys.executable, "-m", "pytest", "-q", "--tb=short", f"--junitxml={baseline_xml.resolve()}"], cwd=baseline_dir, env=env, output_path=out / "baseline.txt")
        feature_full = _run([sys.executable, "-m", "pytest", "-q", "--tb=short", f"--junitxml={feature_xml.resolve()}"], cwd=feature_dir, env=env, output_path=out / "feature.txt")
        summary["baseline_pytest_exit"] = baseline_full.returncode
        summary["feature_pytest_exit"] = feature_full.returncode
        try:
            baseline_junit = _parse_junit(baseline_xml)
            feature_junit = _parse_junit(feature_xml)
            summary["baseline_junit"] = baseline_junit
            summary["feature_junit"] = feature_junit
            baseline_nodes = set(baseline_junit["failure_nodes"])
            feature_nodes = set(feature_junit["failure_nodes"])
            feature_only = sorted(feature_nodes - baseline_nodes)
            summary["feature_only_failure_nodes"] = feature_only
            detail_map = {value["node"]: value for value in feature_junit["failure_details"]}
            summary["feature_only_failure_details"] = [detail_map[node] for node in feature_only]
            if feature_only:
                product_failures.append(f"feature-only failure nodes: {len(feature_only)}")
        except Exception as exc:
            infrastructure_errors.append(f"JUnit parse: {type(exc).__name__}: {exc}")

    if infrastructure_errors:
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = "; ".join(infrastructure_errors)
        exit_code = 2
    elif product_failures:
        summary["gate"] = "FAIL"
        summary["gate_reason"] = "; ".join(product_failures)
        exit_code = 1
    else:
        summary["gate"] = "PASS"
        summary["gate_reason"] = "Exact refs, requirements parity, targeted runtime, RETURNED registry/facade lifecycle, both generic Qt render probes, four PNGs, Agenda/STS smokes and JUnit differential passed with zero feature-only failure nodes."
        exit_code = 0

    (out / "stage3b-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline_junit = summary.get("baseline_junit") or {"totals": {}, "failure_nodes": []}
    feature_junit = summary.get("feature_junit") or {"totals": {}, "failure_nodes": []}
    baseline_totals = baseline_junit.get("totals") or {}
    feature_totals = feature_junit.get("totals") or {}
    baseline_nodes = set(baseline_junit.get("failure_nodes") or [])
    feature_nodes = set(feature_junit.get("failure_nodes") or [])
    shared_nodes = baseline_nodes & feature_nodes
    baseline_only = baseline_nodes - feature_nodes
    feature_only = feature_nodes - baseline_nodes
    smoke_pass = "PASS" if summary.get("returned_share_smoke_exit") == 0 and "RETURNED_SHARE_SMOKE=PASS" in str(summary.get("returned_share_smoke_output") or "") else "FAIL"

    print("GUNDEMIM_STAGE3B_GATE_BEGIN")
    print(f"BASELINE_SHA={summary['baseline_expected_sha']}")
    print(f"BASELINE_ACTUAL_SHA={summary['baseline_actual_sha']}")
    print(f"FEATURE_SHA={summary['feature_expected_sha']}")
    print(f"FEATURE_ACTUAL_SHA={summary['feature_actual_sha']}")
    print(f"REQUIREMENTS_MATCH={1 if summary['requirements_match'] else 0}")
    print(f"COMPILE_EXIT={summary['compile_exit']}")
    print(f"TARGETED_EXIT={summary['targeted_exit']}")
    print(f"TARGETED_SUMMARY={summary['targeted_summary']}")
    print(f"RETURNED_SHARE_SMOKE_EXIT={summary['returned_share_smoke_exit']}")
    print(f"RETURNED_SHARE_SMOKE={smoke_pass}")
    print(f"AGENDA_SCHEMA_SMOKE_EXIT={summary['agenda_schema_smoke_exit']}")
    print(f"STS_DB_SMOKE_EXIT={summary['sts_db_smoke_exit']}")
    for token in ("100", "150"):
        scale_data = summary["scales"].get(token, {})
        print(f"QT_SCALE_{token}={scale_data.get('result', 'INCOMPLETE')}")
    print(f"QT_ALL_PASS={1 if summary['visual_all_pass'] else 0}")
    for token in ("100", "150"):
        scale_data = summary["scales"].get(token, {})
        print(f"RETURNED_ITEM_RENDERED_{token}={1 if scale_data.get('returned_item_rendered') else 0}")
    scale100 = summary["scales"].get("100", {})
    print(f"SNOOZE_CONTROL_100={1 if scale100.get('snooze_control') else 0}")
    print(f"DWELL_100_BEFORE={scale100.get('dwell_before_500ms')}")
    print(f"DWELL_100_AFTER={scale100.get('dwell_after_total_750ms')}")
    print(f"VISUAL_PNG_COUNT={sum(1 for p in summary['pngs'] if p.get('exists'))}")
    print(f"BASELINE_PYTEST_EXIT={summary['baseline_pytest_exit']}")
    print(f"FEATURE_PYTEST_EXIT={summary['feature_pytest_exit']}")
    print(f"BASELINE_TOTAL={baseline_totals.get('tests')}")
    print(f"BASELINE_FAILURES={baseline_totals.get('failures')}")
    print(f"BASELINE_ERRORS={baseline_totals.get('errors')}")
    print(f"FEATURE_TOTAL={feature_totals.get('tests')}")
    print(f"FEATURE_FAILURES={feature_totals.get('failures')}")
    print(f"FEATURE_ERRORS={feature_totals.get('errors')}")
    print(f"BASELINE_FAILURE_NODE_COUNT={len(baseline_nodes)}")
    print(f"FEATURE_FAILURE_NODE_COUNT={len(feature_nodes)}")
    print(f"SHARED_FAILURE_NODE_COUNT={len(shared_nodes)}")
    print(f"BASELINE_ONLY_FAILURE_NODE_COUNT={len(baseline_only)}")
    print(f"FEATURE_ONLY_FAILURE_NODE_COUNT={len(feature_only)}")
    for node in sorted(feature_only)[:20]:
        print(f"FEATURE_ONLY_NODE={node}")
    print(f"GATE={summary['gate']}")
    print(f"GATE_REASON={summary['gate_reason']}")
    print("GUNDEMIM_STAGE3B_GATE_END")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha")
    parser.add_argument("--feature-sha")
    parser.add_argument("--repo-url")
    parser.add_argument("--qt-render-probe", action="store_true")
    parser.add_argument("--scale")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    if args.qt_render_probe:
        if not args.scale or not args.output_dir:
            parser.error("--qt-render-probe requires --scale and --output-dir")
        return _qt_probe(str(args.scale), Path(args.output_dir))
    if not args.baseline_sha or not args.feature_sha or not args.repo_url:
        parser.error("parent mode requires --baseline-sha, --feature-sha and --repo-url")
    return _parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
