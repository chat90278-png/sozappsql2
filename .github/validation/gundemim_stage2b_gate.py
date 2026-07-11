from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("validation-out").resolve()
WORK_ROOT = OUTPUT_ROOT / "work"
MAX_MESSAGE_CHARS = 1200
MAX_SENTINEL_FAILURES = 20


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _run_capture(command: list[str], *, cwd: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", errors="replace") as output_file:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
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
        ["git", "-c", "protocol.version=2", "fetch", "--quiet", "--depth=1", "origin", expected_sha],
        cwd=target,
    )
    _run_git(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=target)
    actual_sha = _run_git(["git", "rev-parse", "HEAD"], cwd=target)
    if actual_sha != expected_sha:
        raise RuntimeError(f"materialized SHA mismatch: expected {expected_sha}, actual {actual_sha}")
    return actual_sha


def _attr_int(element: ET.Element, name: str) -> int:
    raw = str(element.attrib.get(name, "0") or "0").strip()
    return int(float(raw))


def _attr_time(element: ET.Element) -> str:
    return str(element.attrib.get("time", "0") or "0").strip()


def _parse_junit(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JUnit XML missing: {path}")
    root = ET.parse(path).getroot()
    root_tag = root.tag.rsplit("}", 1)[-1]
    if root_tag == "testsuite" or "tests" in root.attrib:
        totals = {
            "tests": _attr_int(root, "tests"),
            "failures": _attr_int(root, "failures"),
            "errors": _attr_int(root, "errors"),
            "skipped": _attr_int(root, "skipped"),
            "time": _attr_time(root),
        }
    else:
        suites = [child for child in list(root) if child.tag.rsplit("}", 1)[-1] == "testsuite"]
        totals = {
            "tests": sum(_attr_int(suite, "tests") for suite in suites),
            "failures": sum(_attr_int(suite, "failures") for suite in suites),
            "errors": sum(_attr_int(suite, "errors") for suite in suites),
            "skipped": sum(_attr_int(suite, "skipped") for suite in suites),
            "time": str(sum(float(_attr_time(suite)) for suite in suites)),
        }

    details: list[dict[str, str]] = []
    for testcase in root.iter():
        if testcase.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        failure_node = None
        error_node = None
        for child in list(testcase):
            child_tag = child.tag.rsplit("}", 1)[-1]
            if child_tag == "failure":
                failure_node = child
                break
            if child_tag == "error" and error_node is None:
                error_node = child
        child = failure_node if failure_node is not None else error_node
        if child is None:
            continue
        kind = "failure" if failure_node is not None else "error"
        classname = str(testcase.attrib.get("classname", "") or "")
        name = str(testcase.attrib.get("name", "") or "")
        message_source = child.attrib.get("message") or child.text or ""
        details.append(
            {
                "node": f"{classname}::{name}",
                "kind": kind,
                "message": _normalize_text(message_source)[:MAX_MESSAGE_CHARS],
            }
        )
    nodes = sorted({detail["node"] for detail in details})
    return {"totals": totals, "failure_nodes": nodes, "failure_details": details}


def _detail_by_node(details: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for detail in details:
        result.setdefault(detail["node"], detail)
    return result


def _read_output(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _final_summary(path: Path) -> str:
    lines = [line.strip() for line in _read_output(path).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _write_summary(summary: dict[str, Any]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "stage2b-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _print_sentinel(summary: dict[str, Any]) -> None:
    baseline_totals = summary.get("baseline_totals") or {}
    feature_totals = summary.get("feature_totals") or {}
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
    print("GUNDEMIM_STAGE2B_GATE_BEGIN")
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
    print("GUNDEMIM_STAGE2B_GATE_END")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--feature-sha", required=True)
    parser.add_argument("--repo-url", required=True)
    args = parser.parse_args()

    summary: dict[str, Any] = {
        "baseline_sha": str(args.baseline_sha),
        "feature_sha": str(args.feature_sha),
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
        "gate_reason": "Stage 2B differential validation did not complete.",
    }

    baseline_dir = WORK_ROOT / "baseline"
    feature_dir = WORK_ROOT / "feature"
    try:
        summary["baseline_actual_sha"] = _materialize_exact(
            target=baseline_dir,
            repo_url=str(args.repo_url),
            expected_sha=str(args.baseline_sha),
        )
        summary["feature_actual_sha"] = _materialize_exact(
            target=feature_dir,
            repo_url=str(args.repo_url),
            expected_sha=str(args.feature_sha),
        )

        summary["requirements_match"] = (
            (baseline_dir / "requirements.txt").read_bytes()
            == (feature_dir / "requirements.txt").read_bytes()
        )
        if not summary["requirements_match"]:
            summary["gate_reason"] = "Baseline and feature requirements.txt bytes differ."
            _write_summary(summary)
            _print_sentinel(summary)
            return 1

        compile_path = OUTPUT_ROOT / "feature-compile.txt"
        targeted_path = OUTPUT_ROOT / "stage2b-targeted.txt"
        agenda_smoke_path = OUTPUT_ROOT / "agenda-schema-smoke.txt"
        sts_smoke_path = OUTPUT_ROOT / "sts-db-smoke.txt"

        summary["compile_exit"] = _run_capture(
            [sys.executable, "-m", "compileall", "-q", "src", "tests"],
            cwd=feature_dir,
            output_path=compile_path,
        )
        summary["targeted_exit"] = _run_capture(
            [
                sys.executable, "-m", "pytest", "-q",
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
            ],
            cwd=feature_dir,
            output_path=targeted_path,
        )
        summary["targeted_summary"] = _final_summary(targeted_path)
        summary["agenda_schema_smoke_exit"] = _run_capture(
            [sys.executable, "tests/smoke_sts_agenda_schema.py"],
            cwd=feature_dir,
            output_path=agenda_smoke_path,
        )
        summary["agenda_schema_smoke_output"] = _read_output(agenda_smoke_path)
        summary["sts_db_smoke_exit"] = _run_capture(
            [sys.executable, "tests/smoke_sts_database.py"],
            cwd=feature_dir,
            output_path=sts_smoke_path,
        )
        summary["sts_db_smoke_output"] = _read_output(sts_smoke_path)

        baseline_xml = OUTPUT_ROOT / "baseline.xml"
        feature_xml = OUTPUT_ROOT / "feature.xml"
        summary["baseline_pytest_exit"] = _run_capture(
            [
                sys.executable, "-m", "pytest", "-q", "--tb=short",
                f"--junitxml={baseline_xml}",
            ],
            cwd=baseline_dir,
            output_path=OUTPUT_ROOT / "baseline.txt",
        )
        summary["feature_pytest_exit"] = _run_capture(
            [
                sys.executable, "-m", "pytest", "-q", "--tb=short",
                f"--junitxml={feature_xml}",
            ],
            cwd=feature_dir,
            output_path=OUTPUT_ROOT / "feature.txt",
        )

        baseline_junit = _parse_junit(baseline_xml)
        feature_junit = _parse_junit(feature_xml)
        summary["baseline_totals"] = baseline_junit["totals"]
        summary["feature_totals"] = feature_junit["totals"]

        baseline_nodes = set(baseline_junit["failure_nodes"])
        feature_nodes = set(feature_junit["failure_nodes"])
        feature_only_nodes = sorted(feature_nodes - baseline_nodes)
        feature_detail_map = _detail_by_node(feature_junit["failure_details"])
        summary["baseline_failure_nodes"] = sorted(baseline_nodes)
        summary["feature_failure_nodes"] = sorted(feature_nodes)
        summary["shared_failure_nodes"] = sorted(feature_nodes & baseline_nodes)
        summary["baseline_only_failure_nodes"] = sorted(baseline_nodes - feature_nodes)
        summary["feature_only_failure_nodes"] = feature_only_nodes
        summary["feature_only_failure_details"] = [
            feature_detail_map[node] for node in feature_only_nodes
        ]

        failed_feature_prerequisites = [
            name
            for name, value in (
                ("compile", summary["compile_exit"]),
                ("targeted", summary["targeted_exit"]),
                ("agenda_schema_smoke", summary["agenda_schema_smoke_exit"]),
                ("sts_db_smoke", summary["sts_db_smoke_exit"]),
            )
            if value != 0
        ]
        if failed_feature_prerequisites:
            summary["gate"] = "FAIL"
            summary["gate_reason"] = (
                "Feature prerequisite command failure: "
                + ", ".join(failed_feature_prerequisites)
            )
        elif feature_only_nodes:
            summary["gate"] = "FAIL"
            summary["gate_reason"] = (
                f"Stage 2B introduced {len(feature_only_nodes)} feature-only failing test node(s)."
            )
        else:
            summary["gate"] = "PASS"
            summary["gate_reason"] = (
                "Exact accepted Stage 2A and Stage 2B JUnit failure-node sets contain no "
                "feature-only failing node; all targeted prerequisites passed."
            )
    except Exception as exc:
        summary["gate"] = "INCOMPLETE"
        summary["gate_reason"] = _normalize_text(
            f"{type(exc).__name__}: {exc}"
        )[:MAX_MESSAGE_CHARS]

    _write_summary(summary)
    _print_sentinel(summary)
    return 0 if summary["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
