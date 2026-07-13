from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "_validation" / "fix42-final"
SELFTEST = ROOT / "_validation" / "selftest"
ORIGINAL = ROOT / "_validation" / "original-agenda"
SUMMARY_TOOL = ROOT / "tools" / "validation" / "junit_summary.py"

ORIGINAL_ARTIFACT_ID = 8271212551
ORIGINAL_BASELINE_SHA = "bc5feca2aa755b4e12c98b9932810778ec08d6cb"
ORIGINAL_FEATURE_SHA = "9de74e04c33479e652b15ecff625751b8f68c46b"
CURRENT_MAIN_BASE_SHA = "f3279e4d546dbf2e22963298ebc90f4eaaea9494"
FIX_FILES_BASE_SHA = "85be5d4976db9ca9334cc85653e6306c6244ef2c"

FIX_FILES = [
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


class ValidationError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    printable = subprocess.list2cmdline(command)
    print(f"\n>>> ({cwd}) {printable}", flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
        env=env,
    )
    if capture:
        if completed.stdout:
            print(completed.stdout, end="", flush=True)
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr, flush=True)
    if check and completed.returncode != 0:
        raise ValidationError(
            f"command failed with exit code {completed.returncode}: {printable}"
        )
    return completed


def output(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def assert_fix_files_untouched() -> None:
    completed = run(
        ["git", "diff", "--exit-code", FIX_FILES_BASE_SHA, "HEAD", "--", *FIX_FILES],
        check=False,
    )
    if completed.returncode != 0:
        raise ValidationError("one or more previously validated fix files changed")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def leaf_suites(element: ET.Element) -> list[ET.Element]:
    name = local_name(element.tag)
    children = [child for child in element if local_name(child.tag) == "testsuite"]
    if name == "testsuite" and not children:
        return [element]
    leaves: list[ET.Element] = []
    for child in children:
        leaves.extend(leaf_suites(child))
    return leaves


def xml_totals(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = leaf_suites(root)
    if not suites:
        raise ValidationError(f"no leaf testsuite found in {path}")
    totals = {field: 0 for field in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for field in totals:
            totals[field] += int(suite.attrib.get(field, "0"))
    return totals


def testcase_nodes(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    nodes: list[str] = []
    for case in root.iter():
        if local_name(case.tag) != "testcase":
            continue
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        nodes.append(f"{classname}::{name}" if classname else name)
    return sorted(nodes)


def failing_nodes(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    nodes: set[str] = set()
    for case in root.iter():
        if local_name(case.tag) != "testcase":
            continue
        children = {local_name(child.tag) for child in case}
        if not ({"failure", "error"} & children):
            continue
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        nodes.add(f"{classname}::{name}" if classname else name)
    return nodes


def invoke_summary(
    xml_path: Path,
    json_path: Path,
    *,
    exit_code: int,
    expected_tests: int,
    expected_failures: int = 0,
    expected_errors: int = 0,
    expected_skipped: int = 0,
    tool: Path = SUMMARY_TOOL,
    cwd: Path = ROOT,
) -> dict[str, object]:
    completed = run(
        [
            sys.executable,
            str(tool),
            str(xml_path),
            str(json_path),
            "--exit-code",
            str(exit_code),
            "--expect-tests",
            str(expected_tests),
            "--expect-failures",
            str(expected_failures),
            "--expect-errors",
            str(expected_errors),
            "--expect-skipped",
            str(expected_skipped),
        ],
        cwd=cwd,
        check=False,
        capture=True,
    )
    if completed.returncode != 0:
        raise ValidationError(f"JUnit summary validation failed for {xml_path}")
    summary = json.loads(json_path.read_text(encoding="utf-8-sig"))
    totals = xml_totals(xml_path)
    for field, value in totals.items():
        if summary[field] != value:
            raise ValidationError(
                f"summary/XML mismatch for {xml_path}: {field}={summary[field]} vs {value}"
            )
    return summary


def parser_selftest() -> None:
    SELFTEST.mkdir(parents=True, exist_ok=True)
    single = SELFTEST / "single.xml"
    single.write_text(
        '<testsuite name="single" tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="selftest" name="pass" />'</n        '</testsuite>',
        encoding="utf-8",
    )
    invoke_summary(
        single,
        SELFTEST / "single.json",
        exit_code=0,
        expected_tests=1,
    )

    nested = SELFTEST / "nested.xml"
    nested.write_text(
        '<testsuites><testsuite name="outer">'
        '<testsuite name="first" tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="selftest" name="first" /></testsuite>'
        '<testsuite name="second" tests="1" failures="1" errors="0" skipped="0">'
        '<testcase classname="selftest" name="second"><failure message="expected" />'</n        '</testcase></testsuite></testsuite></testsuites>',
        encoding="utf-8",
    )
    invoke_summary(
        nested,
        SELFTEST / "nested.json",
        exit_code=1,
        expected_tests=2,
        expected_failures=1,
    )

    zero = SELFTEST / "zero.xml"
    zero_json = SELFTEST / "zero.json"
    zero.write_text(
        '<testsuites><testsuite name="empty" tests="0" failures="0" errors="0" skipped="0" />'</n        '</testsuites>',
        encoding="utf-8",
    )
    zero_json.unlink(missing_ok=True)
    completed = run(
        [
            sys.executable,
            str(SUMMARY_TOOL),
            str(zero),
            str(zero_json),
            "--exit-code",
            "0",
        ],
        check=False,
        capture=True,
    )
    if completed.returncode == 0:
        raise ValidationError("zero-test XML unexpectedly produced a passing summary")
    if zero_json.exists():
        raise ValidationError("fail-loud parser left a zero-test JSON output")


def run_pytest_summary(name: str, paths: list[str], expected_tests: int) -> dict[str, object]:
    xml_path = EVIDENCE / f"{name}.xml"
    json_path = EVIDENCE / f"{name}-summary.json"
    completed = run(
        [sys.executable, "-m", "pytest", "-q", *paths, f"--junitxml={xml_path}"],
        check=False,
    )
    summary = invoke_summary(
        xml_path,
        json_path,
        exit_code=completed.returncode,
        expected_tests=expected_tests,
    )
    if completed.returncode != 0:
        raise ValidationError(f"{name} pytest failed with exit code {completed.returncode}")
    return summary


def download_original_artifact() -> tuple[Path, Path]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "chat90278-png/sozappsql2")
    if not token:
        raise ValidationError("GITHUB_TOKEN is required to download original evidence")
    ORIGINAL.mkdir(parents=True, exist_ok=True)
    archive = ROOT / "_validation" / "original-agenda.zip"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/artifacts/{ORIGINAL_ARTIFACT_ID}/zip",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "fix42-final-scope-validator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            archive.write_bytes(response.read())
    except Exception as exc:
        raise ValidationError(f"cannot download original Agenda artifact: {exc}") from exc
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(ORIGINAL)
    baseline = next(iter(ORIGINAL.rglob("baseline-full.xml")), None)
    feature = next(iter(ORIGINAL.rglob("feature-full.xml")), None)
    if baseline is None or feature is None:
        raise ValidationError("original artifact does not contain baseline-full.xml and feature-full.xml")
    return baseline, feature


def config_snapshot(ref: str) -> dict[str, object]:
    candidates = [
        "pytest.ini",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        "conftest.py",
        "tests/conftest.py",
    ]
    result: dict[str, object] = {}
    for path in candidates:
        completed = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        if completed.returncode == 0:
            result[path] = {
                "present": True,
                "sha256": hashlib.sha256(completed.stdout).hexdigest(),
                "bytes": len(completed.stdout),
            }
        else:
            result[path] = {"present": False}
    return result


def analyze_scope(original_baseline_xml: Path, original_feature_xml: Path) -> dict[str, object]:
    current_xml = EVIDENCE / "final-full.xml"
    old_baseline = set(testcase_nodes(original_baseline_xml))
    old_feature = set(testcase_nodes(original_feature_xml))
    current = set(testcase_nodes(current_xml))
    baseline_only = sorted(old_baseline - current)
    current_only = sorted(current - old_baseline)
    feature_only_current = sorted(old_feature - current)

    (EVIDENCE / "baseline923-only-vs-current721.txt").write_text(
        "\n".join(baseline_only) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "current721-only-vs-baseline923.txt").write_text(
        "\n".join(current_only) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "feature982-only-vs-current721.txt").write_text(
        "\n".join(feature_only_current) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "net-202-is-not-a-node-list.txt").write_text(
        "923 - 721 = 202 is a net count difference, not a set-difference node list.\n"
        "Exact set delta: 263 nodes exist only in the 923-test Stage-3B/Agenda lineage, "
        "while 61 nodes exist only in the later 721-test main lineage.\n",
        encoding="utf-8",
    )

    merge_base = output(["git", "merge-base", ORIGINAL_BASELINE_SHA, CURRENT_MAIN_BASE_SHA])
    left, right = output(
        ["git", "rev-list", "--left-right", "--count", f"{ORIGINAL_BASELINE_SHA}...{CURRENT_MAIN_BASE_SHA}"]
    ).split()
    collection = {
        "original_baseline": len(old_baseline),
        "original_feature": len(old_feature),
        "current_fix": len(current),
        "baseline923_only_count": len(baseline_only),
        "current721_only_count": len(current_only),
        "net_count_difference": len(old_baseline) - len(current),
        "feature982_only_vs_current_count": len(feature_only_current),
    }
    expected = {
        "original_baseline": 923,
        "original_feature": 982,
        "current_fix": 721,
        "baseline923_only_count": 263,
        "current721_only_count": 61,
        "net_count_difference": 202,
        "feature982_only_vs_current_count": 322,
    }
    if collection != expected:
        raise ValidationError(f"unexpected collection delta: {collection}")

    report = {
        "commands": {
            "original_baseline": "python -m pytest -q --junitxml=<evidence>/baseline-full.xml",
            "original_feature": "python -m pytest -q --junitxml=<evidence>/feature-full.xml",
            "current_fix": "python -m pytest -q --junitxml=<evidence>/final-full.xml",
            "filters_or_ignores": [],
        },
        "refs": {
            "original_baseline": ORIGINAL_BASELINE_SHA,
            "original_feature": ORIGINAL_FEATURE_SHA,
            "current_main_base": CURRENT_MAIN_BASE_SHA,
            "fix_branch_head": output(["git", "rev-parse", "HEAD"]),
            "merge_base_original_baseline_vs_current_main": merge_base,
            "original_baseline_only_commits": int(left),
            "current_main_only_commits": int(right),
        },
        "collection": collection,
        "pytest_configuration": {
            "original_baseline": config_snapshot(ORIGINAL_BASELINE_SHA),
            "current_main": config_snapshot(CURRENT_MAIN_BASE_SHA),
            "original_feature": config_snapshot(ORIGINAL_FEATURE_SHA),
        },
        "root_cause": (
            "The 923 and 721 runs used identical unfiltered pytest commands but different, "
            "divergent source trees. The 923 ref belongs to the Stage-3B/Agenda lineage; "
            "PR #329 was based on later main. Their exact node-set delta is 263 Agenda-lineage-only "
            "nodes and 61 later-main-only nodes, producing the net count difference of 202."
        ),
        "intentional_or_bug": "bug",
        "resolution": (
            "Treat the 721 run only as validation against PR #329's later-main base, and run the "
            "same nine-file patch independently on the exact 982-test Agenda feature ref."
        ),
        "baseline_only_nodes": baseline_only,
        "current_only_nodes": current_only,
    }
    (EVIDENCE / "scope-discrepancy.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def materialize_feature_scope() -> tuple[Path, dict[str, object]]:
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    feature_dir = temp_root / "agenda-feature-full-scope"
    patch_path = temp_root / "fix42-nine-files.patch"
    if feature_dir.exists():
        run(["git", "worktree", "remove", "--force", str(feature_dir)], check=False)
        shutil.rmtree(feature_dir, ignore_errors=True)
    run(["git", "worktree", "add", "--detach", str(feature_dir), ORIGINAL_FEATURE_SHA])

    patch = subprocess.check_output(
        ["git", "diff", "--binary", CURRENT_MAIN_BASE_SHA, "HEAD", "--", *FIX_FILES],
        cwd=ROOT,
    )
    if not patch:
        raise ValidationError("nine-file fix patch is empty")
    patch_path.write_bytes(patch)
    run(["git", "apply", "--3way", str(patch_path)], cwd=feature_dir)
    run(["git", "diff", "--check", "HEAD"], cwd=feature_dir)

    changed = sorted(
        line.strip()
        for line in output(["git", "diff", "--name-only", "HEAD"], cwd=feature_dir).splitlines()
        if line.strip()
    )
    expected = sorted(FIX_FILES)
    if changed != expected:
        raise ValidationError(
            f"unexpected full-scope changed paths: expected={expected}, actual={changed}"
        )

    feature_tool = feature_dir / "tools" / "validation" / "junit_summary.py"
    feature_tool.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SUMMARY_TOOL, feature_tool)
    materialization = {
        "feature_ref": ORIGINAL_FEATURE_SHA,
        "fix_branch_head": output(["git", "rev-parse", "HEAD"]),
        "patch_base": CURRENT_MAIN_BASE_SHA,
        "changed_paths": changed,
    }
    (EVIDENCE / "full-scope-materialization.json").write_text(
        json.dumps(materialization, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return feature_dir, materialization


def run_full_feature_scope(feature_dir: Path, original_feature_xml: Path) -> dict[str, object]:
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=feature_dir)
    run([sys.executable, "-m", "compileall", "-q", "src", "tests"], cwd=feature_dir)
    xml_path = feature_dir / "full-scope-final.xml"
    json_path = feature_dir / "full-scope-final-summary.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    completed = run(
        [sys.executable, "-m", "pytest", "-q", f"--junitxml={xml_path}"],
        cwd=feature_dir,
        check=False,
        env=env,
    )
    summary = invoke_summary(
        xml_path,
        json_path,
        exit_code=completed.returncode,
        expected_tests=982,
        tool=feature_dir / "tools" / "validation" / "junit_summary.py",
        cwd=feature_dir,
    )
    if completed.returncode != 0:
        raise ValidationError(
            f"full Agenda scope pytest failed with exit code {completed.returncode}"
        )
    shutil.copy2(xml_path, EVIDENCE / "full-scope-final.xml")
    shutil.copy2(json_path, EVIDENCE / "full-scope-final-summary.json")

    original_failures = failing_nodes(original_feature_xml)
    final_failures = set(summary["failing_nodes"])
    new_failures = sorted(final_failures - original_failures)
    fixed = sorted(original_failures - final_failures)
    differential = {
        "full_scope_final_run": summary,
        "original_feature_failure_count": len(original_failures),
        "new_failures_vs_original_baseline": new_failures,
        "fixed_nodes": fixed,
        "ready_to_merge": (
            summary["tests"] == 982
            and summary["failures"] == 0
            and summary["errors"] == 0
            and not new_failures
        ),
    }
    if len(original_failures) != 42:
        raise ValidationError(f"expected 42 original feature failures, got {len(original_failures)}")
    if len(fixed) != 42 or new_failures or not differential["ready_to_merge"]:
        raise ValidationError(f"unexpected full-scope differential: {differential}")
    (EVIDENCE / "full-scope-differential.json").write_text(
        json.dumps(differential, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return differential


def build_final_report(
    scope: dict[str, object],
    differential: dict[str, object],
) -> dict[str, object]:
    summaries = {
        name: json.loads((EVIDENCE / f"{name}-summary.json").read_text(encoding="utf-8-sig"))
        for name in ("step1", "step2", "step3", "step4", "final-full")
    }
    regenerated_ok = (
        [summaries[name]["tests"] for name in ("step1", "step2", "step3", "step4", "final-full")]
        == [8, 6, 32, 3, 721]
        and all(summaries[name]["failures"] == 0 for name in summaries)
        and all(summaries[name]["errors"] == 0 for name in summaries)
    )
    baseline_only = scope["baseline_only_nodes"]
    final_summary = differential["full_scope_final_run"]
    report = {
        "summary_script_fix": {
            "bug_found": (
                "The removed temporary fix42 validator read tests/failures/errors/skipped from "
                "the root <testsuites> element. Pytest stores those attributes on child "
                "<testsuite> elements, so missing root attributes defaulted silently to zero."
            ),
            "fix_applied": (
                "Added tools/validation/junit_summary.py. It supports single <testsuite> and "
                "nested <testsuites>, sums leaf-suite attributes, cross-checks testcase outcomes, "
                "rejects zero tests and inconsistent counts, removes stale output, and exits non-zero."
            ),
            "regenerated_summaries_match_xml": regenerated_ok,
        },
        "scope_discrepancy": {
            "root_cause": scope["root_cause"],
            "missing_202_tests_sample": baseline_only[:15],
            "intentional_or_bug": scope["intentional_or_bug"],
            "resolution": scope["resolution"],
            "exact_set_delta": {
                "stage3b_agenda_only": scope["collection"]["baseline923_only_count"],
                "later_main_only": scope["collection"]["current721_only_count"],
                "net_difference": scope["collection"]["net_count_difference"],
            },
        },
        "full_scope_final_run": {
            "collection_size": final_summary["tests"],
            "tests": final_summary["tests"],
            "failures": final_summary["failures"],
            "errors": final_summary["errors"],
            "skipped": final_summary["skipped"],
            "failing_nodes": final_summary["failing_nodes"],
            "new_failures_vs_original_baseline": differential[
                "new_failures_vs_original_baseline"
            ],
        },
        "ready_to_merge": bool(regenerated_ok and differential["ready_to_merge"]),
        "remaining_concerns": [
            (
                "The requested 'exact 202 missing tests' list does not exist as a valid set "
                "difference: the exact sets are 263 old-lineage-only and 61 later-main-only nodes. "
                "Both complete lists are included in the evidence artifact."
            )
        ],
    }
    (EVIDENCE / "final-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not report["ready_to_merge"]:
        raise ValidationError("final report is not merge-ready")
    return report


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    try:
        assert_fix_files_untouched()
        parser_selftest()
        run_pytest_summary("step1", ["tests/test_share_merge_window_orchestration.py"], 8)
        run_pytest_summary("step2", ["tests/test_share_merge_dialog.py"], 6)
        run_pytest_summary(
            "step3",
            [
                "tests/test_analysis_builder_qt.py",
                "tests/test_analysis_excel_export_qt.py",
                "tests/test_analysis_qt_integration.py",
                "tests/test_analysis_tur17_builder_ux_qt.py",
                "tests/test_analysis_visual_settings_qt.py",
            ],
            32,
        )
        run_pytest_summary("step4", ["tests/test_contract_status_summary_widget.py"], 3)
        run_pytest_summary("final-full", [], 721)
        baseline_xml, feature_xml = download_original_artifact()
        scope = analyze_scope(baseline_xml, feature_xml)
        feature_dir, _materialization = materialize_feature_scope()
        differential = run_full_feature_scope(feature_dir, feature_xml)
        assert_fix_files_untouched()
        report = build_final_report(scope, differential)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 0
    except Exception as exc:
        failure = {
            "error": type(exc).__name__,
            "message": str(exc),
            "ready_to_merge": False,
        }
        (EVIDENCE / "validation-failure.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
