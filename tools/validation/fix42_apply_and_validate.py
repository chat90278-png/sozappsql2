from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "_validation" / "fix42"
EVIDENCE.mkdir(parents=True, exist_ok=True)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def summarize_junit(path: Path, exit_code: int) -> dict:
    root = ET.parse(path).getroot()
    if root.tag == "testsuites":
        tests = int(root.attrib.get("tests", 0))
        failures = int(root.attrib.get("failures", 0))
        errors = int(root.attrib.get("errors", 0))
        skipped = int(root.attrib.get("skipped", 0))
    else:
        tests = int(root.attrib.get("tests", 0))
        failures = int(root.attrib.get("failures", 0))
        errors = int(root.attrib.get("errors", 0))
        skipped = int(root.attrib.get("skipped", 0))
    nodes: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        nodes.append(f"{classname}::{name}" if classname else name)
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "failing_nodes": sorted(nodes),
        "exit_code": exit_code,
    }


def run_pytest(name: str, paths: list[str]) -> dict:
    xml_path = EVIDENCE / f"{name}.xml"
    command = [sys.executable, "-m", "pytest", "-q", *paths, f"--junitxml={xml_path}"]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    summary = summarize_junit(xml_path, completed.returncode)
    (EVIDENCE / f"{name}-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({name: summary}, ensure_ascii=False, indent=2), flush=True)
    if completed.returncode != 0:
        raise SystemExit(f"{name} failed with exit code {completed.returncode}")
    return summary


def patch_step1() -> None:
    path = "tests/test_share_merge_window_orchestration.py"
    text = read(path)
    old = '''    window.show_share_history = lambda: calls.append(("history",))
    return window, calls
'''
    new = '''    window.show_share_history = lambda: calls.append(("history",))
    window._confirm_active_share_creation = (
        lambda: ContractWorkWindow._confirm_active_share_creation(window)
    )
    return window, calls
'''
    write(path, replace_once(text, old, new, label="step1 fake binding"))


def patch_step2() -> None:
    path = "tests/test_share_merge_dialog.py"
    text = read(path)
    old_helper = '''def _conflict_combo(dialog: ShareMergeDialog) -> QComboBox:
    for target_id, combo in dialog._decision_combos.items():
        item = dialog.controller.item_by_target(target_id)
        if item and item.is_conflict:
            return combo
    raise AssertionError("conflict combo not found")
'''
    new_helper = '''def _conflict_combos(dialog: ShareMergeDialog) -> list[QComboBox]:
    combos = [
        combo
        for target_id, combo in dialog._decision_combos.items()
        if (dialog.controller.item_by_target(target_id) and dialog.controller.item_by_target(target_id).is_conflict)
    ]
    if not combos:
        raise AssertionError("conflict combo not found")
    return combos


def _conflict_combo(dialog: ShareMergeDialog) -> QComboBox:
    return _conflict_combos(dialog)[0]
'''
    text = replace_once(text, old_helper, new_helper, label="step2 conflict helper")

    old_first = '''        combo = _conflict_combo(dialog)
        assert combo.currentData() is None
        _choose(combo, MergeDecisionKind.LOCAL_KEEP)

        assert dialog.controller.explicit_decisions
        assert next(iter(dialog.controller.explicit_decisions.values())) == MergeDecisionKind.LOCAL_KEEP
        assert dialog.controller.resolved_plan.summary["unresolved_conflict_count"] == 0
        assert dialog.apply_btn.isEnabled()
'''
    new_first = '''        combos = _conflict_combos(dialog)
        assert len(combos) > 1
        initial_unresolved = dialog.controller.resolved_plan.summary["unresolved_conflict_count"]
        assert all(combo.currentData() is None for combo in combos)

        _choose(combos[0], MergeDecisionKind.LOCAL_KEEP)
        assert dialog.controller.resolved_plan.summary["unresolved_conflict_count"] == initial_unresolved - 1
        assert not dialog.apply_btn.isEnabled()

        for combo in combos[1:]:
            _choose(combo, MergeDecisionKind.LOCAL_KEEP)
        assert set(dialog.controller.explicit_decisions.values()) == {MergeDecisionKind.LOCAL_KEEP}
        assert dialog.controller.resolved_plan.summary["unresolved_conflict_count"] == 0
        assert dialog.controller.resolved_plan.summary["structural_issue_count"] == 0
        assert dialog.apply_btn.isEnabled()
'''
    text = replace_once(text, old_first, new_first, label="step2 explicit decisions")

    old_skip = '''        combo = _conflict_combo(dialog)
        _choose(combo, MergeDecisionKind.SKIP)
        assert dialog.controller.resolved_plan.is_partial
        assert dialog.apply_btn.isEnabled()
        assert dialog.partial_warning.isVisible()
'''
    new_skip = '''        combos = _conflict_combos(dialog)
        _choose(combos[0], MergeDecisionKind.SKIP)
        for combo in combos[1:]:
            _choose(combo, MergeDecisionKind.LOCAL_KEEP)
        assert dialog.controller.resolved_plan.is_partial
        assert dialog.controller.resolved_plan.summary["unresolved_conflict_count"] == 0
        assert dialog.controller.resolved_plan.summary["structural_issue_count"] == 0
        assert dialog.apply_btn.isEnabled()
        assert dialog.partial_warning.isVisible()
'''
    text = replace_once(text, old_skip, new_skip, label="step2 skip decisions")

    old_submit = '''        _choose(_conflict_combo(dialog), MergeDecisionKind.LOCAL_KEEP)
        dialog._set_busy(True, "busy")
'''
    new_submit = '''        for combo in _conflict_combos(dialog):
            _choose(combo, MergeDecisionKind.LOCAL_KEEP)
        dialog._set_busy(True, "busy")
'''
    text = replace_once(text, old_submit, new_submit, label="step2 submit decisions")
    write(path, text)


def add_wait_after_window_constructors(text: str, *, path: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    inserted = 0
    while index < len(lines):
        line = lines[index]
        output.append(line)
        if "window = AnalysisCenterWindow(" not in line:
            index += 1
            continue
        balance = line.count("(") - line.count(")")
        while balance > 0:
            index += 1
            if index >= len(lines):
                raise RuntimeError(f"{path}: unterminated AnalysisCenterWindow constructor")
            line = lines[index]
            output.append(line)
            balance += line.count("(") - line.count(")")
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines) or "wait_until_ready(window, qt_app)" not in lines[next_index]:
            indent = output[-1][: len(output[-1]) - len(output[-1].lstrip())]
            output.append(f"{indent}wait_until_ready(window, qt_app)\n")
            inserted += 1
        index += 1
    if inserted == 0 and "wait_until_ready(window, qt_app)" not in text:
        raise RuntimeError(f"{path}: no AnalysisCenterWindow constructor patched")
    return "".join(output)


def patch_step3() -> None:
    helper_path = ROOT / "tests" / "qt_wait_helpers.py"
    helper_path.write_text(
        '''from __future__ import annotations

import time

import pytest
from PySide6.QtTest import QTest


def wait_until_ready(window, qt_app, timeout_ms: int = 10_000) -> None:
    """Boundedly drain the Qt event loop until AnalysisCenterWindow is rendered."""
    if not window.isVisible():
        window.show()
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_state: dict[str, object] = {}
    while time.monotonic() < deadline:
        qt_app.processEvents()
        item_ids = list(getattr(window, "_item_ids", []) or [])
        navigation = getattr(window, "navigation", None)
        stack = getattr(window, "stack", None)
        payload = getattr(window, "_payload", None)
        nav_count = navigation.count() if navigation is not None else -1
        stack_count = stack.count() if stack is not None else -1
        last_state = {
            "item_ids": item_ids,
            "navigation_count": nav_count,
            "stack_count": stack_count,
            "payload_ready": bool(payload),
        }
        if item_ids and nav_count == len(item_ids) and stack_count == len(item_ids) and payload:
            return
        QTest.qWait(10)
    pytest.fail(
        f"AnalysisCenterWindow did not become ready within {timeout_ms} ms; last_state={last_state}"
    )
''',
        encoding="utf-8",
    )

    paths = [
        "tests/test_analysis_builder_qt.py",
        "tests/test_analysis_excel_export_qt.py",
        "tests/test_analysis_qt_integration.py",
        "tests/test_analysis_tur17_builder_ux_qt.py",
        "tests/test_analysis_visual_settings_qt.py",
    ]
    import_line = "from tests.qt_wait_helpers import wait_until_ready\n"
    for path in paths:
        text = read(path)
        if import_line not in text:
            marker = "from analysis_center.analysis_qt_window import"
            lines = text.splitlines(keepends=True)
            matching = [i for i, line in enumerate(lines) if line.startswith(marker)]
            if len(matching) != 1:
                raise RuntimeError(f"{path}: expected one analysis_qt_window import, found {len(matching)}")
            lines.insert(matching[0] + 1, import_line)
            text = "".join(lines)
        text = add_wait_after_window_constructors(text, path=path)
        write(path, text)


def patch_step4() -> None:
    path = "src/ui/widgets/contract_status_summary.py"
    text = read(path)
    text = replace_once(
        text,
        '''        self.setFixedHeight(112)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
''',
        '''        self.setFixedSize(460, 112)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
''',
        label="step4 fixed size",
    )
    text = replace_once(
        text,
        '''        "QFrame#contractStatusSummaryWidget:hover{"
        "border-color:#397bd8; background:#ffffff;}"
''',
        '''        "QFrame#contractStatusSummaryWidget:hover{"
        "border-color:#397bd8; background:#fafcff;}"
''',
        label="step4 outer hover",
    )
    hover_old = '''        "QFrame#contractStatusSummaryWidget:hover QWidget#contractStatusContent{"
        "background:#ffffff;}"
'''
    hover_new = '''        "QFrame#contractStatusSummaryWidget:hover QWidget#contractStatusContent{"
        "background:#fafcff;}"
'''
    if hover_new not in text:
        count = text.count(hover_old)
        if count < 1:
            raise RuntimeError("step4 content hover: no matches")
        text = text.replace(hover_old, hover_new)
    text = replace_once(
        text,
        "        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)\n",
        "        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)\n",
        label="step4 legend policy",
    )
    write(path, text)

    usages: list[str] = []
    for source in sorted((ROOT / "src").rglob("*.py")):
        for line_no, line in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if "contract_status_widget" in line:
                usages.append(f"{source.relative_to(ROOT)}:{line_no}: {line.strip()}")
    note = {
        "fixed_contract": "460x112, horizontal and vertical QSizePolicy.Fixed",
        "hover_background": "#fafcff on the card and content surface",
        "legend_policy": "QSizePolicy.Ignored horizontally for three equal cells",
        "usage_lines": usages,
        "layout_verification": "tests/test_contract_status_summary_widget.py validates the main-page slot, fixed width, calendar ordering, and fixed calendar width.",
    }
    (EVIDENCE / "step4-layout-note.json").write_text(
        json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    patch_step1()
    run_pytest("step1", ["tests/test_share_merge_window_orchestration.py"])

    patch_step2()
    run_pytest("step2", ["tests/test_share_merge_dialog.py"])

    patch_step3()
    run_pytest(
        "step3",
        [
            "tests/test_analysis_builder_qt.py",
            "tests/test_analysis_excel_export_qt.py",
            "tests/test_analysis_qt_integration.py",
            "tests/test_analysis_tur17_builder_ux_qt.py",
            "tests/test_analysis_visual_settings_qt.py",
        ],
    )

    patch_step4()
    run_pytest("step4", ["tests/test_contract_status_summary_widget.py"])

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "app.py", "src", "analysis_center", "tests"],
        cwd=ROOT,
        check=False,
    )
    if compile_result.returncode != 0:
        raise SystemExit(f"compileall failed with exit code {compile_result.returncode}")

    final = run_pytest("final-full", [])
    changed = [
        "tests/test_share_merge_window_orchestration.py",
        "tests/test_share_merge_dialog.py",
        "tests/qt_wait_helpers.py",
        "tests/test_analysis_builder_qt.py",
        "tests/test_analysis_excel_export_qt.py",
        "tests/test_analysis_qt_integration.py",
        "tests/test_analysis_tur17_builder_ux_qt.py",
        "tests/test_analysis_visual_settings_qt.py",
        "src/ui/widgets/contract_status_summary.py",
    ]
    (EVIDENCE / "validated-files.json").write_text(
        json.dumps({"files": changed, "final": final}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
