from __future__ import annotations

from pathlib import Path


PATH = Path("tools/validation/agenda_stage_05b_v_runtime_validation.py")
OLD = (
    '        run.require(baseline_sha in parents[1:], '
    '"current main is not a direct merge parent")'
)
NEW = "\n".join(
    (
        '        agenda_source_sha = "66681d51877ad09db7379b6bbd7049a7436af1fc"',
        '        run.require(agenda_source_sha in parents[1:], '
        'f"Agenda source is not a direct merge parent: {parents[1:]}")',
        '        target_parent = next(parent for parent in parents[1:] '
        'if parent != agenda_source_sha)',
        "        target_lineage = subprocess.run(",
        '            ["git", "merge-base", "--is-ancestor", '
        "baseline_sha, target_parent],",
        "            cwd=candidate_root,",
        "            check=False,",
        "        )",
        '        run.require(target_lineage.returncode == 0, '
        '"current main is not an ancestor of target merge parent")',
    )
)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit("expected lineage assertion not found")
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
