from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


class JUnitSummaryError(RuntimeError):
    """Raised when a JUnit document cannot be summarized safely."""


@dataclass(frozen=True)
class JUnitSummary:
    tests: int
    failures: int
    errors: int
    skipped: int
    failing_nodes: list[str]
    exit_code: int


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _leaf_suites(element: ET.Element) -> list[ET.Element]:
    name = _local_name(element.tag)
    if name not in {"testsuite", "testsuites"}:
        raise JUnitSummaryError(
            f"unsupported JUnit root <{name}>; expected <testsuite> or <testsuites>"
        )

    child_suites = _direct_children(element, "testsuite")
    if name == "testsuite" and not child_suites:
        return [element]

    leaves: list[ET.Element] = []
    for child in child_suites:
        leaves.extend(_leaf_suites(child))
    if not leaves:
        raise JUnitSummaryError("JUnit document contains no <testsuite> elements")
    return leaves


def _count_attribute(element: ET.Element, field: str, *, required: bool) -> int:
    raw = element.attrib.get(field)
    if raw is None:
        if required:
            suite_name = element.attrib.get("name", "<unnamed>")
            raise JUnitSummaryError(
                f"testsuite {suite_name!r} is missing required {field!r} attribute"
            )
        return 0
    try:
        value = int(raw)
    except ValueError as exc:
        raise JUnitSummaryError(
            f"invalid integer {field}={raw!r} on testsuite "
            f"{element.attrib.get('name', '<unnamed>')!r}"
        ) from exc
    if value < 0:
        raise JUnitSummaryError(f"negative JUnit count {field}={value}")
    return value


def _suite_totals(suites: Iterable[ET.Element]) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        totals["tests"] += _count_attribute(suite, "tests", required=True)
        totals["failures"] += _count_attribute(suite, "failures", required=False)
        totals["errors"] += _count_attribute(suite, "errors", required=False)
        totals["skipped"] += _count_attribute(suite, "skipped", required=False)
    return totals


def _testcases(root: ET.Element) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == "testcase"]


def _has_direct_child(case: ET.Element, name: str) -> bool:
    return any(_local_name(child.tag) == name for child in case)


def _node_id(case: ET.Element) -> str:
    classname = case.attrib.get("classname", "").strip()
    name = case.attrib.get("name", "").strip()
    if not name:
        raise JUnitSummaryError("testcase is missing a non-empty name attribute")
    return f"{classname}::{name}" if classname else name


def summarize_junit(xml_path: Path, *, test_exit_code: int | None = None) -> JUnitSummary:
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise JUnitSummaryError(f"cannot parse JUnit XML {xml_path}: {exc}") from exc

    leaves = _leaf_suites(root)
    totals = _suite_totals(leaves)
    if totals["tests"] <= 0:
        raise JUnitSummaryError(
            f"JUnit XML {xml_path} reports zero tests; refusing to emit a passing 0/0 summary"
        )

    cases = _testcases(root)
    if len(cases) != totals["tests"]:
        raise JUnitSummaryError(
            f"JUnit testcase count mismatch: suite attributes report {totals['tests']} "
            f"but the XML contains {len(cases)} testcase elements"
        )

    derived = {"failures": 0, "errors": 0, "skipped": 0}
    failing_nodes: list[str] = []
    for case in cases:
        has_failure = _has_direct_child(case, "failure")
        has_error = _has_direct_child(case, "error")
        has_skipped = _has_direct_child(case, "skipped")
        outcome_count = int(has_failure) + int(has_error) + int(has_skipped)
        if outcome_count > 1:
            raise JUnitSummaryError(
                f"testcase {_node_id(case)!r} has multiple terminal outcome elements"
            )
        if has_failure:
            derived["failures"] += 1
            failing_nodes.append(_node_id(case))
        elif has_error:
            derived["errors"] += 1
            failing_nodes.append(_node_id(case))
        elif has_skipped:
            derived["skipped"] += 1

    for field in ("failures", "errors", "skipped"):
        if derived[field] != totals[field]:
            raise JUnitSummaryError(
                f"JUnit {field} mismatch: suite attributes report {totals[field]} "
                f"but testcase elements report {derived[field]}"
            )

    root_name = _local_name(root.tag)
    if root_name == "testsuites":
        for field in ("tests", "failures", "errors", "skipped"):
            if field in root.attrib:
                aggregate = _count_attribute(root, field, required=False)
                if aggregate != totals[field]:
                    raise JUnitSummaryError(
                        f"root <testsuites> {field}={aggregate} disagrees with "
                        f"leaf-suite total {totals[field]}"
                    )

    inferred_exit_code = 1 if totals["failures"] or totals["errors"] else 0
    exit_code = inferred_exit_code if test_exit_code is None else test_exit_code
    if exit_code == 0 and (totals["failures"] or totals["errors"]):
        raise JUnitSummaryError(
            "test process exit code is 0 although JUnit contains failures/errors"
        )

    return JUnitSummary(
        tests=totals["tests"],
        failures=totals["failures"],
        errors=totals["errors"],
        skipped=totals["skipped"],
        failing_nodes=sorted(failing_nodes),
        exit_code=exit_code,
    )


def _assert_expected(summary: JUnitSummary, args: argparse.Namespace) -> None:
    for field in ("tests", "failures", "errors", "skipped"):
        expected = getattr(args, f"expect_{field}")
        if expected is not None and getattr(summary, field) != expected:
            raise JUnitSummaryError(
                f"expected {field}={expected}, got {getattr(summary, field)}"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a validated, fail-loud JSON summary from JUnit XML."
    )
    parser.add_argument("xml", type=Path, help="input JUnit XML path")
    parser.add_argument("json", type=Path, help="output JSON path")
    parser.add_argument("--exit-code", type=int, default=None, help="pytest exit code")
    parser.add_argument("--expect-tests", type=int, default=None)
    parser.add_argument("--expect-failures", type=int, default=None)
    parser.add_argument("--expect-errors", type=int, default=None)
    parser.add_argument("--expect-skipped", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = summarize_junit(args.xml, test_exit_code=args.exit_code)
        _assert_expected(summary, args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except JUnitSummaryError as exc:
        try:
            args.json.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"JUnit summary error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(summary), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
