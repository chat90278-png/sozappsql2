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
    patcher.patch_sts_schema_upgrade()
    patcher.patch_main_page()
    patcher.patch_tests()
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
