from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


OUTPUT_DIR = Path("validation-out")
JUNIT_PATH = OUTPUT_DIR / "full-pytest.xml"
RAW_OUTPUT_PATH = OUTPUT_DIR / "full-pytest.txt"
MAX_FAILURES = 20
MAX_MESSAGE_CHARS = 1200
RAW_TAIL_CHARS = 4000


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _raw_output_tail() -> str:
    try:
        content = RAW_OUTPUT_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return _normalize_text(f"raw output unavailable: {type(exc).__name__}: {exc}")
    return _normalize_text(content[-RAW_TAIL_CHARS:])


def _attr_int(element: ET.Element, name: str) -> int:
    raw = str(element.attrib.get(name, "0") or "0").strip()
    return int(float(raw))


def _attr_float_text(element: ET.Element, name: str) -> str:
    return str(element.attrib.get(name, "0") or "0").strip()


def _junit_totals(root: ET.Element) -> tuple[int, int, int, int, str]:
    if root.tag == "testsuite" or "tests" in root.attrib:
        return (
            _attr_int(root, "tests"),
            _attr_int(root, "failures"),
            _attr_int(root, "errors"),
            _attr_int(root, "skipped"),
            _attr_float_text(root, "time"),
        )

    suites = list(root.findall("./testsuite"))
    tests = sum(_attr_int(suite, "tests") for suite in suites)
    failures = sum(_attr_int(suite, "failures") for suite in suites)
    errors = sum(_attr_int(suite, "errors") for suite in suites)
    skipped = sum(_attr_int(suite, "skipped") for suite in suites)
    total_time = sum(float(_attr_float_text(suite, "time")) for suite in suites)
    return tests, failures, errors, skipped, str(total_time)


def _failure_cases(root: ET.Element) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for testcase in root.iter("testcase"):
        failure_node = testcase.find("failure")
        error_node = testcase.find("error")
        node = failure_node if failure_node is not None else error_node
        if node is None:
            continue
        kind = "failure" if failure_node is not None else "error"
        classname = str(testcase.attrib.get("classname", "") or "")
        name = str(testcase.attrib.get("name", "") or "")
        node_id = f"{classname}::{name}"
        message_source = node.attrib.get("message") or node.text or ""
        message = _normalize_text(message_source)[:MAX_MESSAGE_CHARS]
        result.append((node_id, kind, message))
        if len(result) >= MAX_FAILURES:
            break
    return result


def _print_missing_summary(pytest_returncode: int) -> None:
    print("GUNDEMIM_PYTEST_DIAG_BEGIN")
    print(f"PYTEST_EXIT_CODE={pytest_returncode}")
    print("JUNIT_XML_MISSING=1")
    print(f"RAW_OUTPUT_TAIL={_raw_output_tail()}")
    print("GUNDEMIM_PYTEST_DIAG_END")


def _print_parse_error(pytest_returncode: int, exc: BaseException) -> None:
    print("GUNDEMIM_PYTEST_DIAG_BEGIN")
    print(f"PYTEST_EXIT_CODE={pytest_returncode}")
    print(f"JUNIT_PARSE_ERROR={_normalize_text(f'{type(exc).__name__}: {exc}')}")
    print(f"RAW_OUTPUT_TAIL={_raw_output_tail()}")
    print("GUNDEMIM_PYTEST_DIAG_END")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "--junitxml=validation-out/full-pytest.xml",
    ]

    with RAW_OUTPUT_PATH.open("w", encoding="utf-8", errors="replace") as output_file:
        completed = subprocess.run(
            command,
            stdout=output_file,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    pytest_returncode = int(completed.returncode)
    if not JUNIT_PATH.is_file():
        _print_missing_summary(pytest_returncode)
        return pytest_returncode if pytest_returncode != 0 else 1

    try:
        root = ET.parse(JUNIT_PATH).getroot()
        tests, failures, errors, skipped, total_time = _junit_totals(root)
        failure_cases = _failure_cases(root)
    except Exception as exc:
        _print_parse_error(pytest_returncode, exc)
        return pytest_returncode if pytest_returncode != 0 else 1

    print("GUNDEMIM_PYTEST_DIAG_BEGIN")
    print(f"PYTEST_EXIT_CODE={pytest_returncode}")
    print(f"PYTEST_TOTAL={tests}")
    print(f"PYTEST_FAILURES={failures}")
    print(f"PYTEST_ERRORS={errors}")
    print(f"PYTEST_SKIPPED={skipped}")
    print(f"PYTEST_TIME={total_time}")
    for index, (node_id, kind, message) in enumerate(failure_cases, start=1):
        prefix = f"FAIL_{index:02d}"
        print(f"{prefix}_NODE={node_id}")
        print(f"{prefix}_KIND={kind}")
        print(f"{prefix}_MESSAGE={message}")
    print("GUNDEMIM_PYTEST_DIAG_END")
    return pytest_returncode


if __name__ == "__main__":
    sys.exit(main())
