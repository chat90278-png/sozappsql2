from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("validation-out").resolve()
WORK_ROOT = OUTPUT_ROOT / "work"
VISUAL_ROOT = OUTPUT_ROOT / "visual"
MAX_MESSAGE_CHARS = 1600
MAX_SENTINEL_FAILURES = 20
TARGETED_TESTS = [
    "tests/test_agenda_compact_widget.py",
    "tests/test_agenda_detail_window.py",
    "tests/test_main_page_agenda_integration.py",
    "tests/test_agenda_context_factory.py",
    "tests/test_agenda_presentation.py",
    "tests/test_personal_agenda_facade.py",
    "tests/test_agenda_lifecycle.py",
    "tests/test_agenda_source_repository.py",
    "tests/test_deadline_agenda_provider.py",
    "tests/test_unknown_date_agenda_provider.py",
    "tests/test_staff_agenda_service.py",
    "tests/test_agenda_state_repository.py",
    "tests/test_sts_database_transactions.py",
    "tests/test_agenda_keys.py",
    "tests/test_agenda_deadline_stage.py",
    "tests/test_agenda_models.py",
]


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _run_capture(
    command: list[str],
    *,
    cwd: Path,
    output_path: Path,
    env: dict[str, str] | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", errors="replace") as output_file:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=output_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return int(completed.returncode)


def _run_git(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = _normalize_text(completed.stderr or completed.stdout)[:MAX_MESSAGE_CHARS]
        raise RuntimeError(f"git command failed ({completed.returncode}): {detail}")
    return str(completed.stdout or "").strip()


def _materialize_exact(*, target: Path, repo_url: str, expected_sha: str) -> str:
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"materialization target is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "init", "-q", "."], cwd=target)
    _run_git(["git", "remote", "add", "origin", repo_url], cwd=target)
    _run_git(
        [
            "git",
            "-c",
            "protocol.version=2",
            "fetch",
            "--quiet",
            "--depth=1",
            "origin",
            expected_sha,
        ],
        cwd=target,
    )
    _run_git(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=target)
    actual_sha = _run_git(["git", "rev-parse", "HEAD"], cwd=target)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"materialized SHA mismatch: expected {expected_sha}, actual {actual_sha}"
        )
    return actual_sha


def _read_output(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _final_summary(path: Path) -> str:
    lines = [line.strip() for line in _read_output(path).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _attr_int(element: ET.Element, name: str) -> int:
    raw = str(element.attrib.get(name, "0") or "0").strip()
    return int(float(raw))


def _attr_float(element: ET.Element, name: str) -> float:
    raw = str(element.attrib.get(name, "0") or "0").strip()
    return float(raw)


def _parse_junit(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JUnit XML missing: {path}")
    root = ET.parse(path).getroot()
    root_tag = root.tag.rsplit("}", 1)[-1]
    if root_tag == "testsuite":
        suites = [root]
    else:
        suites = [
            child
            for child in list(root)
            if child.tag.rsplit("}", 1)[-1] == "testsuite"
        ]
    if not suites and "tests" in root.attrib:
        suites = [root]
    totals = {
        "tests": sum(_attr_int(suite, "tests") for suite in suites),
        "failures": sum(_attr_int(suite, "failures") for suite in suites),
        "errors": sum(_attr_int(suite, "errors") for suite in suites),
        "skipped": sum(_attr_int(suite, "skipped") for suite in suites),
        "time": sum(_attr_float(suite, "time") for suite in suites),
    }

    details: list[dict[str, str]] = []
    for testcase in root.iter():
        if testcase.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        for child in list(testcase):
            child_tag = child.tag.rsplit("}", 1)[-1]
            if child_tag not in {"failure", "error"}:
                continue
            classname = str(testcase.attrib.get("classname", "") or "")
            name = str(testcase.attrib.get("name", "") or "")
            message_source = child.attrib.get("message") or child.text or ""
            details.append(
                {
                    "node": f"{classname}::{name}",
                    "kind": child_tag,
                    "message": _normalize_text(message_source)[:MAX_MESSAGE_CHARS],
                }
            )
    nodes = sorted({detail["node"] for detail in details})
    return {
        "totals": totals,
        "failure_nodes": nodes,
        "failure_details": details,
    }


def _detail_by_node(details: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for detail in details:
        result.setdefault(detail["node"], detail)
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _png_evidence(path: Path) -> dict[str, Any]:
    from PySide6.QtGui import QImage

    if not path.is_file():
        raise RuntimeError(f"PNG was not created: {path.name}")
    size_bytes = path.stat().st_size
    image = QImage(str(path))
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise RuntimeError(f"PNG is empty or unreadable: {path.name}")
    if size_bytes <= 500:
        raise RuntimeError(f"PNG is unexpectedly small: {path.name} ({size_bytes} bytes)")

    colors: set[int] = set()
    step_x = max(1, image.width() // 32)
    step_y = max(1, image.height() // 24)
    for y in range(0, image.height(), step_y):
        for x in range(0, image.width(), step_x):
            colors.add(int(image.pixel(x, y)))
            if len(colors) > 1:
                break
        if len(colors) > 1:
            break
    if len(colors) <= 1:
        raise RuntimeError(f"PNG contains only one sampled color: {path.name}")
    return {
        "name": path.name,
        "size_bytes": size_bytes,
        "width": image.width(),
        "height": image.height(),
        "non_uniform": True,
    }


def _widget_rect_record(widget, root) -> dict[str, Any]:
    from PySide6.QtCore import QPoint

    top_left = widget.mapTo(root, QPoint(0, 0))
    bottom_right = widget.mapTo(
        root,
        QPoint(max(0, widget.width() - 1), max(0, widget.height() - 1)),
    )
    return {
        "object_name": str(widget.objectName() or ""),
        "class_name": widget.metaObject().className(),
        "x": top_left.x(),
        "y": top_left.y(),
        "right": bottom_right.x(),
        "bottom": bottom_right.y(),
        "width": widget.width(),
        "height": widget.height(),
    }


def _compact_geometry_offenders(root) -> list[dict[str, Any]]:
    from PySide6.QtWidgets import QMenu, QWidget

    offenders: list[dict[str, Any]] = []
    tolerance = 2
    for child in root.findChildren(QWidget):
        if child is root or not child.isVisible() or child.isWindow():
            continue
        if isinstance(child, QMenu) or child.window() is not root.window():
            continue
        record = _widget_rect_record(child, root)
        if (
            record["width"] <= 0
            or record["height"] <= 0
            or record["x"] < -tolerance
            or record["y"] < -tolerance
            or record["right"] > root.width() - 1 + tolerance
            or record["bottom"] > root.height() - 1 + tolerance
        ):
            offenders.append(record)
    return offenders


def _detail_geometry_offenders(detail) -> list[dict[str, Any]]:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QFrame, QPushButton, QToolButton, QWidget

    offenders: list[dict[str, Any]] = []
    tolerance = 2
    candidates: list[QWidget] = []
    header = detail.findChild(QFrame, "agendaDetailHeader")
    panel = detail.findChild(QFrame, "agendaDetailPanel")
    if header is not None:
        candidates.append(header)
    if panel is not None:
        candidates.append(panel)
    viewport = detail.scroll.viewport()
    if viewport is not None:
        candidates.append(viewport)

    viewport_rect = QRect()
    if viewport is not None:
        vp_top_left = viewport.mapTo(detail, QPoint(0, 0))
        viewport_rect = QRect(
            vp_top_left.x(),
            vp_top_left.y(),
            viewport.width(),
            viewport.height(),
        )

    for child in detail.findChildren(QWidget):
        if not child.isVisible() or child.isWindow():
            continue
        if not isinstance(child, (QPushButton, QToolButton)):
            continue
        record = _widget_rect_record(child, detail)
        child_rect = QRect(
            record["x"],
            record["y"],
            record["width"],
            record["height"],
        )
        if viewport_rect.isValid() and not viewport_rect.intersects(child_rect):
            parent = child.parentWidget()
            inside_scroll_host = False
            while parent is not None:
                if parent is detail.scroll_host:
                    inside_scroll_host = True
                    break
                parent = parent.parentWidget()
            if inside_scroll_host:
                continue
        candidates.append(child)

    seen_ids: set[int] = set()
    for widget in candidates:
        marker = id(widget)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)
        record = _widget_rect_record(widget, detail)
        if (
            record["width"] <= 0
            or record["height"] <= 0
            or record["x"] < -tolerance
            or record["y"] < -tolerance
            or record["right"] > detail.width() - 1 + tolerance
            or record["bottom"] > detail.height() - 1 + tolerance
        ):
            offenders.append(record)
    return offenders


def _build_snapshot():
    from datetime import date, datetime, timedelta

    from src.domain.agenda.constants import (
        AgendaLifecycleType,
        AgendaPresentationProfileCode,
        AgendaSeverity,
    )
    from src.domain.agenda.models import AgendaItem, AgendaPresentationProfile
    from src.domain.agenda.presentation import AgendaPresentationSnapshot

    profile = AgendaPresentationProfile(
        code=AgendaPresentationProfileCode.PERSONAL,
        display_name="Kişisel Gündem",
        description="Runtime görsel doğrulama profili",
        permissions=frozenset({"view_contracts"}),
    )
    today = date.today()
    items = []
    severities = [
        AgendaSeverity.CRITICAL,
        AgendaSeverity.ATTENTION,
        AgendaSeverity.INFO,
    ]
    for index in range(25):
        lifecycle = (
            AgendaLifecycleType.EVENT if index == 5 else AgendaLifecycleType.CONDITION
        )
        remaining = [-12, 0, 3, 18, None][index % 5]
        effective = None if remaining is None else today + timedelta(days=int(remaining))
        items.append(
            AgendaItem(
                key=f"visual:agenda:{index:02d}",
                provider_code="visual_probe",
                kind="deadline" if lifecycle == AgendaLifecycleType.CONDITION else "event",
                lifecycle_type=lifecycle,
                title=(
                    f"Uzun Türkçe gündem başlığı {index + 1}: "
                    "Sözleşme, sistem ve teslimat takibi"
                ),
                description=(
                    "Bu açıklama ölçekleme, metin kısaltma ve satır yerleşimini "
                    "gerçek Qt çalışma zamanında doğrulamak için özellikle uzundur."
                ),
                priority=1000 - index,
                severity=severities[index % len(severities)],
                version=f"visual-v{index + 1}",
                presentation_scope=AgendaPresentationProfileCode.PERSONAL,
                contract_id=1000 + index,
                platform=f"Platform {index % 4 + 1}",
                contract_no=f"STS-{index + 1:03d}",
                contract_type="Ana Sözleşme",
                system_id=2000 + index if index % 2 == 0 else None,
                delivery_id=3000 + index if index % 3 == 0 else None,
                event_at=datetime.now() if lifecycle == AgendaLifecycleType.EVENT else None,
                effective_date=effective,
                remaining_days=remaining,
                reason_code="VISUAL_PROBE",
                reason_text="Programmatic validation",
                supports_snooze=(
                    lifecycle == AgendaLifecycleType.CONDITION and index % 4 != 3
                ),
            )
        )
    items_tuple = tuple(items)
    return AgendaPresentationSnapshot(
        profile=profile,
        all_items=items_tuple,
        compact_items=items_tuple[:2],
        detail_items=items_tuple[:20],
        active_count=len(items_tuple),
        new_count=7,
        snoozed_count=3,
        filtered_count=0,
        counts_by_kind={"deadline": 24, "event": 1},
        counts_by_severity={"CRITICAL": 9, "ATTENTION": 8, "INFO": 8},
        new_keys=frozenset(item.key for item in items_tuple[:7]),
        states_by_key={},
        compact_limit=2,
        detail_limit=20,
        has_more=True,
    )


def _visual_probe(scale: float, output_dir: Path) -> int:
    token = int(round(float(scale) * 100))
    result: dict[str, Any] = {
        "scale": float(scale),
        "token": token,
        "result": "FAIL",
        "reason": "Visual probe did not complete.",
        "device_pixel_ratio": None,
        "logical_dpi": None,
        "compact_logical_size": None,
        "compact_rows": 0,
        "compact_order": [],
        "compact_geometry_offenders": [],
        "compact_min_width_offenders": [],
        "compact_dwell_before_500": None,
        "compact_dwell_after_650": None,
        "compact_duplicate_seen_count": None,
        "compact_cancel_seen_keys": [],
        "compact_details_signal_count": 0,
        "compact_contract_ids": [],
        "detail_logical_size": None,
        "detail_rows": 0,
        "detail_order": [],
        "detail_geometry_offenders": [],
        "detail_is_tool": False,
        "detail_is_nonmodal": False,
        "detail_delete_on_close": False,
        "detail_snooze_codes": [],
        "detail_contract_ids": [],
        "detail_dwell_before_500": None,
        "detail_dwell_after_650": None,
        "detail_close_late_seen_count": None,
        "main_window_constructed": False,
        "header_order_pass": False,
        "header_indices": {},
        "header_height": None,
        "agenda_instance_count": 0,
        "png_files": [],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"scale-{token}.json"

    try:
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QWidget

        from src.services.sts_database import STSDatabase
        from src.ui.agenda_compact_widget import AgendaCompactWidget
        from src.ui.agenda_detail_window import AgendaDetailWindow
        from src.ui.main_page_analysis_window import MainWindow
        from src.ui.widgets.contract_status_summary import ContractStatusSummaryWidget

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        snapshot = _build_snapshot()

        compact = AgendaCompactWidget()
        compact.resize(420, 112)
        compact.set_snapshot(snapshot)
        compact.show()
        app.processEvents()
        QTest.qWait(60)
        app.processEvents()

        result["device_pixel_ratio"] = float(compact.devicePixelRatioF())
        screen = compact.screen() or app.primaryScreen()
        result["logical_dpi"] = float(screen.logicalDotsPerInch()) if screen else None
        result["compact_logical_size"] = [compact.width(), compact.height()]
        if compact.height() != 112:
            raise AssertionError(f"compact logical height is {compact.height()}, expected 112")
        if compact.minimumHeight() != 112 or compact.maximumHeight() != 112:
            raise AssertionError("compact minimum/maximum height contract is not 112")
        if len(compact._rows) != 2:
            raise AssertionError(f"compact rendered {len(compact._rows)} rows, expected 2")
        compact_order = [row.item.key for row in compact._rows]
        expected_compact_order = [item.key for item in snapshot.compact_items]
        if compact_order != expected_compact_order:
            raise AssertionError("compact row order differs from snapshot.compact_items")
        result["compact_rows"] = len(compact._rows)
        result["compact_order"] = compact_order
        result["compact_geometry_offenders"] = _compact_geometry_offenders(compact)
        if result["compact_geometry_offenders"]:
            raise AssertionError(
                f"compact 420px geometry offenders: {result['compact_geometry_offenders']}"
            )
        if not compact.details_button.isVisible():
            raise AssertionError("compact details button is not visible")

        compact.resize(250, 112)
        app.processEvents()
        QTest.qWait(30)
        result["compact_min_width_offenders"] = _compact_geometry_offenders(compact)
        if result["compact_min_width_offenders"]:
            raise AssertionError(
                f"compact 250px geometry offenders: {result['compact_min_width_offenders']}"
            )
        for row in compact._rows:
            if row.width() <= 0 or row.height() <= 0:
                raise AssertionError("compact row has non-positive geometry")
            for name in ("agendaCompactItemTitle", "agendaCompactItemDescription"):
                label = row.findChild(QWidget, name)
                if label is None or label.contentsRect().width() < 0:
                    raise AssertionError(f"compact label geometry invalid: {name}")

        compact.resize(420, 112)
        app.processEvents()
        seen_items: list[Any] = []
        details_hits: list[int] = []
        contract_ids: list[int] = []
        compact.item_dwell_seen_requested.connect(seen_items.append)
        compact.open_details_requested.connect(lambda: details_hits.append(1))
        compact.open_contract_requested.connect(contract_ids.append)
        QTest.mouseClick(compact._rows[0], Qt.LeftButton)
        QTest.qWait(450)
        app.processEvents()
        result["compact_dwell_before_500"] = len(seen_items)
        if seen_items:
            raise AssertionError("compact dwell emitted before 500 ms")
        QTest.qWait(300)
        app.processEvents()
        result["compact_dwell_after_650"] = len(seen_items)
        if len(seen_items) != 1:
            raise AssertionError("compact dwell did not emit exactly once after 650 ms")
        QTest.mouseClick(compact._rows[0], Qt.LeftButton)
        QTest.qWait(720)
        app.processEvents()
        result["compact_duplicate_seen_count"] = len(seen_items)
        if len(seen_items) != 1:
            raise AssertionError("compact duplicate click emitted another seen request")
        QTest.mouseClick(compact.details_button, Qt.LeftButton)
        open_button = compact._rows[0].findChild(QToolButton, "agendaCompactOpenContract")
        if open_button is None:
            raise AssertionError("compact contract button is missing")
        QTest.mouseClick(open_button, Qt.LeftButton)
        app.processEvents()
        result["compact_details_signal_count"] = len(details_hits)
        result["compact_contract_ids"] = list(contract_ids)
        if len(details_hits) != 1:
            raise AssertionError("compact details signal count is not one")
        if contract_ids != [snapshot.compact_items[0].contract_id]:
            raise AssertionError("compact contract signal did not carry exact contract ID")

        cancel_widget = AgendaCompactWidget()
        cancel_widget.resize(420, 112)
        cancel_widget.set_snapshot(snapshot)
        cancel_widget.show()
        app.processEvents()
        cancel_seen: list[Any] = []
        cancel_widget.item_dwell_seen_requested.connect(cancel_seen.append)
        QTest.mouseClick(cancel_widget._rows[0], Qt.LeftButton)
        QTest.qWait(300)
        QTest.mouseClick(cancel_widget._rows[1], Qt.LeftButton)
        QTest.qWait(450)
        app.processEvents()
        if cancel_seen:
            raise AssertionError("compact previous selection emitted during cancellation window")
        QTest.qWait(300)
        app.processEvents()
        result["compact_cancel_seen_keys"] = [item.key for item in cancel_seen]
        if result["compact_cancel_seen_keys"] != [snapshot.compact_items[1].key]:
            raise AssertionError("compact cancellation did not emit exactly the second row")
        cancel_widget.close()
        app.processEvents()

        compact_png = output_dir / f"compact-scale-{token}.png"
        if not compact.grab().save(str(compact_png), "PNG"):
            raise RuntimeError("compact screenshot save returned false")
        result["png_files"].append(_png_evidence(compact_png))

        detail = AgendaDetailWindow()
        detail.resize(760, 560)
        detail.set_snapshot(snapshot)
        detail.show()
        app.processEvents()
        QTest.qWait(80)
        app.processEvents()
        result["detail_logical_size"] = [detail.width(), detail.height()]
        result["detail_is_tool"] = bool(detail.windowFlags() & Qt.Tool)
        result["detail_is_nonmodal"] = detail.windowModality() == Qt.NonModal
        result["detail_delete_on_close"] = detail.testAttribute(Qt.WA_DeleteOnClose)
        if not result["detail_is_tool"]:
            raise AssertionError("detail window is not Qt.Tool")
        if not result["detail_is_nonmodal"]:
            raise AssertionError("detail window is not non-modal")
        if not result["detail_delete_on_close"]:
            raise AssertionError("detail window does not use WA_DeleteOnClose")
        if len(detail._rows) != 20:
            raise AssertionError(f"detail rendered {len(detail._rows)} rows, expected 20")
        detail_order = [row.item.key for row in detail._rows]
        expected_detail_order = [item.key for item in snapshot.detail_items]
        if detail_order != expected_detail_order:
            raise AssertionError("detail row order differs from snapshot.detail_items")
        result["detail_rows"] = len(detail._rows)
        result["detail_order"] = detail_order
        result["detail_geometry_offenders"] = _detail_geometry_offenders(detail)
        if result["detail_geometry_offenders"]:
            raise AssertionError(
                f"detail geometry offenders: {result['detail_geometry_offenders']}"
            )

        condition_row = next(row for row in detail._rows if row.item.supports_snooze)
        event_row = next(
            row
            for row in detail._rows
            if str(getattr(row.item.lifecycle_type, "value", row.item.lifecycle_type))
            == "EVENT"
        )
        snooze_button = condition_row.findChild(QToolButton, "agendaDetailSnooze")
        if snooze_button is None or snooze_button.menu() is None:
            raise AssertionError("condition detail row has no snooze control")
        if event_row.findChild(QToolButton, "agendaDetailSnooze") is not None:
            raise AssertionError("event detail row exposes a snooze control")
        snooze_codes: list[str] = []
        detail.snooze_requested.connect(lambda _item, code: snooze_codes.append(str(code)))
        for action in snooze_button.menu().actions():
            action.trigger()
            app.processEvents()
        result["detail_snooze_codes"] = list(snooze_codes)
        if snooze_codes != ["tomorrow", "three_days", "one_week"]:
            raise AssertionError(f"detail snooze codes/order mismatch: {snooze_codes}")

        detail_contract_ids: list[int] = []
        detail.open_contract_requested.connect(detail_contract_ids.append)
        detail_open_button = detail._rows[0].findChild(
            QPushButton, "agendaDetailOpenContract"
        )
        if detail_open_button is None:
            raise AssertionError("detail contract button is missing")
        QTest.mouseClick(detail_open_button, Qt.LeftButton)
        app.processEvents()
        result["detail_contract_ids"] = list(detail_contract_ids)
        if detail_contract_ids != [snapshot.detail_items[0].contract_id]:
            raise AssertionError("detail contract signal did not carry exact contract ID")

        detail_seen: list[Any] = []
        detail.item_dwell_seen_requested.connect(detail_seen.append)
        QTest.mouseClick(detail._rows[0], Qt.LeftButton)
        QTest.qWait(450)
        app.processEvents()
        result["detail_dwell_before_500"] = len(detail_seen)
        if detail_seen:
            raise AssertionError("detail dwell emitted before 500 ms")
        QTest.qWait(300)
        app.processEvents()
        result["detail_dwell_after_650"] = len(detail_seen)
        if len(detail_seen) != 1:
            raise AssertionError("detail dwell did not emit exactly once after 650 ms")

        detail_png = output_dir / f"detail-scale-{token}.png"
        if not detail.grab().save(str(detail_png), "PNG"):
            raise RuntimeError("detail screenshot save returned false")
        result["png_files"].append(_png_evidence(detail_png))

        pending = AgendaDetailWindow()
        pending.resize(760, 560)
        pending.set_snapshot(snapshot)
        pending.show()
        app.processEvents()
        pending_seen: list[Any] = []
        pending.item_dwell_seen_requested.connect(pending_seen.append)
        QTest.mouseClick(pending._rows[1], Qt.LeftButton)
        QTest.qWait(180)
        pending.close()
        app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        QTest.qWait(650)
        app.processEvents()
        result["detail_close_late_seen_count"] = len(pending_seen)
        if pending_seen:
            raise AssertionError("detail close allowed a late seen emission")

        with tempfile.TemporaryDirectory(prefix="stage3a-main-") as temp_root:
            temp_path = Path(temp_root) / "stage3a_visual_probe.sts"
            temp_db = STSDatabase(temp_path, source="Stage 3A Visual Probe")
            temp_db.close()
            staff = {
                "id": 9001,
                "staff_id": 9001,
                "is_active": 1,
                "permissions": {"view_contracts"},
                "full_name": "Görsel Doğrulama Personeli",
                "username": "visual.probe",
                "device_name": "GITHUB-ACTIONS",
                "role": "Personel",
                "role_name": "Personel",
            }
            main_window = MainWindow(initial_path=temp_path, current_staff=staff)
            result["main_window_constructed"] = True
            main_window.resize(1440, 900)
            agenda = main_window.findChild(AgendaCompactWidget)
            status = main_window.findChild(ContractStatusSummaryWidget)
            calendar = getattr(main_window, "_cal_widget", None)
            if agenda is None or status is None or calendar is None:
                raise AssertionError("main header widgets could not be resolved")
            header = calendar.parentWidget()
            if header is None or header.objectName() != "calendarHeaderCard":
                raise AssertionError("calendarHeaderCard could not be resolved")
            layout = header.layout()
            if layout is None:
                raise AssertionError("calendarHeaderCard has no layout")
            status_index = layout.indexOf(status)
            agenda_index = layout.indexOf(agenda)
            calendar_index = layout.indexOf(calendar)
            result["header_indices"] = {
                "status": status_index,
                "agenda": agenda_index,
                "calendar": calendar_index,
            }
            result["header_order_pass"] = (
                status_index >= 0
                and agenda_index >= 0
                and calendar_index >= 0
                and status_index < agenda_index < calendar_index
            )
            if not result["header_order_pass"]:
                raise AssertionError(
                    f"main header order mismatch: {result['header_indices']}"
                )
            result["header_height"] = header.height()
            if header.minimumHeight() != 146 or header.maximumHeight() != 146:
                raise AssertionError(
                    "main header fixed-height contract is not 146 logical px"
                )
            if agenda.minimumHeight() != 112 or agenda.maximumHeight() != 112:
                raise AssertionError("main agenda card is not fixed at 112 logical px")
            agenda_instances = header.findChildren(AgendaCompactWidget)
            result["agenda_instance_count"] = len(agenda_instances)
            if len(agenda_instances) != 1:
                raise AssertionError(
                    f"main header contains {len(agenda_instances)} agenda widgets"
                )
            agenda.set_snapshot(snapshot)
            agenda.show()
            status.show()
            calendar.show()
            main_window.show()
            app.processEvents()
            QTest.qWait(120)
            app.processEvents()
            header_png = output_dir / f"main-header-scale-{token}.png"
            if not header.grab().save(str(header_png), "PNG"):
                raise RuntimeError("main-header screenshot save returned false")
            result["png_files"].append(_png_evidence(header_png))
            main_window.close()
            app.processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()

        detail.close()
        compact.close()
        app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

        if len(result["png_files"]) != 3:
            raise AssertionError("visual probe did not produce exactly three PNG files")
        result["result"] = "PASS"
        result["reason"] = "All Qt runtime, geometry, interaction and PNG checks passed."
        _write_json(result_path, result)
        print(f"VISUAL_PROBE_SCALE_{token}=PASS")
        return 0
    except BaseException as exc:
        result["result"] = "FAIL"
        result["reason"] = f"{type(exc).__name__}: {_normalize_text(exc)}"
        _write_json(result_path, result)
        print(f"VISUAL_PROBE_SCALE_{token}=FAIL")
        print(f"VISUAL_PROBE_REASON={result['reason'][:MAX_MESSAGE_CHARS]}")
        return 1


def _base_summary(baseline_sha: str, feature_sha: str) -> dict[str, Any]:
    return {
        "baseline_sha": baseline_sha,
        "feature_sha": feature_sha,
        "baseline_actual_sha": "",
        "feature_actual_sha": "",
        "requirements_match": False,
        "compile_exit": None,
        "targeted_exit": None,
        "targeted_summary": "",
        "agenda_schema_smoke_exit": None,
        "agenda_schema_smoke_output": "",
        "sts_db_smoke_exit": None,
        "sts_db_smoke_output": "",
        "visual_probe_results": {},
        "visual_all_pass": False,
        "visual_png_files": [],
        "main_window_constructed": False,
        "header_order_pass": False,
        "baseline_pytest_exit": None,
        "feature_pytest_exit": None,
        "baseline_totals": None,
        "feature_totals": None,
        "baseline_failure_nodes": [],
        "feature_failure_nodes": [],
        "shared_failure_nodes": [],
        "baseline_only_failure_nodes": [],
        "feature_only_failure_nodes": [],
        "feature_only_failure_details": [],
        "gate": "INCOMPLETE",
        "gate_reason": "Stage 3A runtime/visual differential validation did not complete.",
    }


def _print_sentinel(summary: dict[str, Any]) -> None:
    baseline_totals = summary.get("baseline_totals") or {}
    feature_totals = summary.get("feature_totals") or {}
    visual = summary.get("visual_probe_results") or {}

    def visual_value(token: str, key: str, default: object = "") -> object:
        payload = visual.get(token) or {}
        return payload.get(key, default)

    size_100 = visual_value("100", "compact_logical_size", [None, None]) or [None, None]
    pairs = [
        ("BASELINE_SHA", summary.get("baseline_sha", "")),
        ("BASELINE_ACTUAL_SHA", summary.get("baseline_actual_sha", "")),
        ("FEATURE_SHA", summary.get("feature_sha", "")),
        ("FEATURE_ACTUAL_SHA", summary.get("feature_actual_sha", "")),
        ("REQUIREMENTS_MATCH", 1 if summary.get("requirements_match") else 0),
        ("COMPILE_EXIT", summary.get("compile_exit", "NOT_AVAILABLE")),
        ("TARGETED_EXIT", summary.get("targeted_exit", "NOT_AVAILABLE")),
        ("TARGETED_SUMMARY", summary.get("targeted_summary", "")),
        ("AGENDA_SCHEMA_SMOKE_EXIT", summary.get("agenda_schema_smoke_exit", "NOT_AVAILABLE")),
        ("AGENDA_SCHEMA_SMOKE_OUTPUT", _normalize_text(summary.get("agenda_schema_smoke_output", ""))),
        ("STS_DB_SMOKE_EXIT", summary.get("sts_db_smoke_exit", "NOT_AVAILABLE")),
        ("STS_DB_SMOKE_OUTPUT", _normalize_text(summary.get("sts_db_smoke_output", ""))),
        ("VISUAL_SCALE_100", visual_value("100", "result", "NOT_AVAILABLE")),
        ("VISUAL_SCALE_125", visual_value("125", "result", "NOT_AVAILABLE")),
        ("VISUAL_SCALE_150", visual_value("150", "result", "NOT_AVAILABLE")),
        ("VISUAL_ALL_PASS", 1 if summary.get("visual_all_pass") else 0),
        ("MAIN_WINDOW_CONSTRUCTED", 1 if summary.get("main_window_constructed") else 0),
        ("HEADER_ORDER_PASS", 1 if summary.get("header_order_pass") else 0),
        ("COMPACT_HEIGHT_100", size_100[1]),
        ("COMPACT_ROWS_100", visual_value("100", "compact_rows", "NOT_AVAILABLE")),
        ("DETAIL_ROWS_100", visual_value("100", "detail_rows", "NOT_AVAILABLE")),
        ("VISUAL_PNG_COUNT", len(summary.get("visual_png_files") or [])),
        ("BASELINE_PYTEST_EXIT", summary.get("baseline_pytest_exit", "NOT_AVAILABLE")),
        ("FEATURE_PYTEST_EXIT", summary.get("feature_pytest_exit", "NOT_AVAILABLE")),
        ("BASELINE_TOTAL", baseline_totals.get("tests", "NOT_AVAILABLE")),
        ("BASELINE_FAILURES", baseline_totals.get("failures", "NOT_AVAILABLE")),
        ("BASELINE_ERRORS", baseline_totals.get("errors", "NOT_AVAILABLE")),
        ("BASELINE_SKIPPED", baseline_totals.get("skipped", "NOT_AVAILABLE")),
        ("FEATURE_TOTAL", feature_totals.get("tests", "NOT_AVAILABLE")),
        ("FEATURE_FAILURES", feature_totals.get("failures", "NOT_AVAILABLE")),
        ("FEATURE_ERRORS", feature_totals.get("errors", "NOT_AVAILABLE")),
        ("FEATURE_SKIPPED", feature_totals.get("skipped", "NOT_AVAILABLE")),
        ("BASELINE_FAILURE_NODE_COUNT", len(summary.get("baseline_failure_nodes") or [])),
        ("FEATURE_FAILURE_NODE_COUNT", len(summary.get("feature_failure_nodes") or [])),
        ("SHARED_FAILURE_NODE_COUNT", len(summary.get("shared_failure_nodes") or [])),
        ("BASELINE_ONLY_FAILURE_NODE_COUNT", len(summary.get("baseline_only_failure_nodes") or [])),
        ("FEATURE_ONLY_FAILURE_NODE_COUNT", len(summary.get("feature_only_failure_nodes") or [])),
    ]
    print("GUNDEMIM_STAGE3A_GATE_BEGIN")
    for key, value in pairs:
        print(f"{key}={_normalize_text(value)[:MAX_MESSAGE_CHARS]}")
    for index, detail in enumerate(
        (summary.get("feature_only_failure_details") or [])[:MAX_SENTINEL_FAILURES],
        start=1,
    ):
        prefix = f"FEATURE_ONLY_{index:02d}"
        print(f"{prefix}_NODE={detail['node']}")
        print(f"{prefix}_KIND={detail['kind']}")
        print(f"{prefix}_MESSAGE={detail['message']}")
    print(f"GATE={summary.get('gate', 'INCOMPLETE')}")
    print(f"GATE_REASON={_normalize_text(summary.get('gate_reason', ''))[:MAX_MESSAGE_CHARS]}")
    print("GUNDEMIM_STAGE3A_GATE_END")


def _parent_gate(baseline_sha: str, feature_sha: str, repo_url: str) -> int:
    summary = _base_summary(baseline_sha, feature_sha)
    baseline_dir = WORK_ROOT / "baseline"
    feature_dir = WORK_ROOT / "feature"
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    VISUAL_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        summary["baseline_actual_sha"] = _materialize_exact(
            target=baseline_dir,
            repo_url=repo_url,
            expected_sha=baseline_sha,
        )
        summary["feature_actual_sha"] = _materialize_exact(
            target=feature_dir,
            repo_url=repo_url,
            expected_sha=feature_sha,
        )
    except Exception as exc:
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = f"Exact materialization failed: {_normalize_text(exc)}"
        _write_json(OUTPUT_ROOT / "stage3a-summary.json", summary)
        _print_sentinel(summary)
        return 1

    try:
        summary["requirements_match"] = (
            (baseline_dir / "requirements.txt").read_bytes()
            == (feature_dir / "requirements.txt").read_bytes()
        )
    except Exception as exc:
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = f"requirements.txt parity unavailable: {_normalize_text(exc)}"
        _write_json(OUTPUT_ROOT / "stage3a-summary.json", summary)
        _print_sentinel(summary)
        return 1
    if not summary["requirements_match"]:
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = "Baseline and feature requirements.txt bytes differ."
        _write_json(OUTPUT_ROOT / "stage3a-summary.json", summary)
        _print_sentinel(summary)
        return 1

    qt_env = dict(os.environ)
    qt_env["QT_QPA_PLATFORM"] = "offscreen"
    qt_env["PYTHONUNBUFFERED"] = "1"

    compile_path = OUTPUT_ROOT / "feature-compile.txt"
    targeted_path = OUTPUT_ROOT / "stage3a-targeted.txt"
    agenda_smoke_path = OUTPUT_ROOT / "agenda-schema-smoke.txt"
    sts_smoke_path = OUTPUT_ROOT / "sts-db-smoke.txt"

    summary["compile_exit"] = _run_capture(
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
        cwd=feature_dir,
        output_path=compile_path,
        env=qt_env,
    )
    summary["targeted_exit"] = _run_capture(
        [sys.executable, "-m", "pytest", "-q", *TARGETED_TESTS],
        cwd=feature_dir,
        output_path=targeted_path,
        env=qt_env,
    )
    summary["targeted_summary"] = _final_summary(targeted_path)
    summary["agenda_schema_smoke_exit"] = _run_capture(
        [sys.executable, "tests/smoke_sts_agenda_schema.py"],
        cwd=feature_dir,
        output_path=agenda_smoke_path,
        env=qt_env,
    )
    summary["agenda_schema_smoke_output"] = _read_output(agenda_smoke_path)
    summary["sts_db_smoke_exit"] = _run_capture(
        [sys.executable, "tests/smoke_sts_database.py"],
        cwd=feature_dir,
        output_path=sts_smoke_path,
        env=qt_env,
    )
    summary["sts_db_smoke_output"] = _read_output(sts_smoke_path)

    visual_results: dict[str, Any] = {}
    png_files: list[dict[str, Any]] = []
    visual_child_failed = False
    for scale, token in ((1.00, "100"), (1.25, "125"), (1.50, "150")):
        output_path = VISUAL_ROOT / f"visual-probe-scale-{token}.txt"
        child_env = dict(qt_env)
        child_env["QT_SCALE_FACTOR"] = str(scale)
        child_env["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        child_script = feature_dir / ".github" / "validation" / "gundemim_stage3a_gate.py"
        exit_code = _run_capture(
            [
                sys.executable,
                str(child_script),
                "--visual-probe",
                "--scale",
                str(scale),
                "--output-dir",
                str(VISUAL_ROOT),
            ],
            cwd=feature_dir,
            output_path=output_path,
            env=child_env,
        )
        result_path = VISUAL_ROOT / f"scale-{token}.json"
        if result_path.is_file():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as exc:
                payload = {
                    "scale": scale,
                    "token": int(token),
                    "result": "FAIL",
                    "reason": f"Scale JSON parse failed: {_normalize_text(exc)}",
                }
        else:
            payload = {
                "scale": scale,
                "token": int(token),
                "result": "FAIL",
                "reason": (
                    f"Visual child exit {exit_code}; scale JSON missing. "
                    f"Output: {_normalize_text(_read_output(output_path))[:MAX_MESSAGE_CHARS]}"
                ),
            }
        payload["child_exit"] = exit_code
        visual_results[token] = payload
        if exit_code != 0 or payload.get("result") != "PASS":
            visual_child_failed = True
        for evidence in payload.get("png_files") or []:
            png_files.append(dict(evidence))

    summary["visual_probe_results"] = visual_results
    summary["visual_png_files"] = png_files
    summary["visual_all_pass"] = (
        not visual_child_failed
        and all(
            (visual_results.get(token) or {}).get("result") == "PASS"
            for token in ("100", "125", "150")
        )
        and len(png_files) == 9
    )
    summary["main_window_constructed"] = all(
        bool((visual_results.get(token) or {}).get("main_window_constructed"))
        for token in ("100", "125", "150")
    )
    summary["header_order_pass"] = all(
        bool((visual_results.get(token) or {}).get("header_order_pass"))
        for token in ("100", "125", "150")
    )

    baseline_xml = OUTPUT_ROOT / "baseline.xml"
    feature_xml = OUTPUT_ROOT / "feature.xml"
    baseline_txt = OUTPUT_ROOT / "baseline.txt"
    feature_txt = OUTPUT_ROOT / "feature.txt"
    summary["baseline_pytest_exit"] = _run_capture(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            f"--junitxml={baseline_xml}",
        ],
        cwd=baseline_dir,
        output_path=baseline_txt,
        env=qt_env,
    )
    summary["feature_pytest_exit"] = _run_capture(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            f"--junitxml={feature_xml}",
        ],
        cwd=feature_dir,
        output_path=feature_txt,
        env=qt_env,
    )

    junit_complete = True
    try:
        baseline_junit = _parse_junit(baseline_xml)
        feature_junit = _parse_junit(feature_xml)
        summary["baseline_totals"] = baseline_junit["totals"]
        summary["feature_totals"] = feature_junit["totals"]
        baseline_nodes = set(baseline_junit["failure_nodes"])
        feature_nodes = set(feature_junit["failure_nodes"])
        summary["baseline_failure_nodes"] = sorted(baseline_nodes)
        summary["feature_failure_nodes"] = sorted(feature_nodes)
        summary["shared_failure_nodes"] = sorted(baseline_nodes & feature_nodes)
        summary["baseline_only_failure_nodes"] = sorted(baseline_nodes - feature_nodes)
        summary["feature_only_failure_nodes"] = sorted(feature_nodes - baseline_nodes)
        feature_detail_map = _detail_by_node(feature_junit["failure_details"])
        summary["feature_only_failure_details"] = [
            feature_detail_map[node]
            for node in summary["feature_only_failure_nodes"]
            if node in feature_detail_map
        ]
    except Exception as exc:
        junit_complete = False
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = f"JUnit evidence unavailable: {_normalize_text(exc)}"

    compile_ok = summary["compile_exit"] == 0
    targeted_ok = summary["targeted_exit"] == 0
    agenda_smoke_ok = (
        summary["agenda_schema_smoke_exit"] == 0
        and "agenda_schema=PASS" in summary["agenda_schema_smoke_output"]
        and "schema_version=18" in summary["agenda_schema_smoke_output"]
    )
    sts_smoke_ok = (
        summary["sts_db_smoke_exit"] == 0
        and "ok" in summary["sts_db_smoke_output"].casefold()
    )

    if not junit_complete:
        pass
    elif not all(
        (
            compile_ok,
            targeted_ok,
            agenda_smoke_ok,
            sts_smoke_ok,
            summary["visual_all_pass"],
            summary["main_window_constructed"],
            summary["header_order_pass"],
        )
    ):
        failed = []
        if not compile_ok:
            failed.append("feature compile")
        if not targeted_ok:
            failed.append("targeted Qt/runtime suite")
        if not agenda_smoke_ok:
            failed.append("Agenda schema smoke")
        if not sts_smoke_ok:
            failed.append("STS database smoke")
        if not summary["visual_all_pass"]:
            failed.append("scale visual probes")
        if not summary["main_window_constructed"]:
            failed.append("MainWindow construction")
        if not summary["header_order_pass"]:
            failed.append("main header order")
        summary["gate"] = "FAIL"
        summary["gate_reason"] = "Failed validation prerequisite(s): " + ", ".join(failed)
    elif summary["feature_only_failure_nodes"]:
        summary["gate"] = "FAIL"
        summary["gate_reason"] = (
            "Feature introduced "
            f"{len(summary['feature_only_failure_nodes'])} new failure/error node(s)."
        )
    else:
        summary["gate"] = "PASS"
        summary["gate_reason"] = (
            "Exact refs and requirements matched; compile, targeted runtime, "
            "Agenda/STS smokes and all three Qt visual probes passed; "
            "feature-only JUnit failure-node count is zero."
        )

    _write_json(OUTPUT_ROOT / "stage3a-summary.json", summary)
    _print_sentinel(summary)
    return 0 if summary["gate"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha")
    parser.add_argument("--feature-sha")
    parser.add_argument("--repo-url")
    parser.add_argument("--visual-probe", action="store_true")
    parser.add_argument("--scale", type=float)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.visual_probe:
        if args.scale is None or not args.output_dir:
            parser.error("--visual-probe requires --scale and --output-dir")
        return _visual_probe(float(args.scale), Path(args.output_dir).resolve())

    if not args.baseline_sha or not args.feature_sha or not args.repo_url:
        parser.error(
            "parent mode requires --baseline-sha, --feature-sha and --repo-url"
        )
    return _parent_gate(
        str(args.baseline_sha),
        str(args.feature_sha),
        str(args.repo_url),
    )


if __name__ == "__main__":
    raise SystemExit(main())
