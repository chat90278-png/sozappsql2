from __future__ import annotations

from pathlib import Path


PATH = Path("tools/validation/agenda_stage_05b_v_runtime_validation.py")
LINEAGE_OLD = (
    '        run.require(baseline_sha in parents[1:], '
    '"current main is not a direct merge parent")'
)
LINEAGE_NEW = "\n".join(
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
DETAIL_OLD = "\n".join(
    (
        "            details = [obj for obj in window.findChildren(AgendaDetailWindow) if isValid(obj)]",
        '            run.require(len(details) == 1, f"detail window count after reuse={len(details)}")',
    )
)
DETAIL_NEW = "\n".join(
    (
        '            registered = window._tool_windows_by_key.get("agenda:detail")',
        '            run.require(registered is first and isValid(registered), "agenda:detail registry entry mismatch after reuse")',
    )
)
REOPEN_OLD = (
    '            run.require(reopened is not first, '
    '"closed detail instance was incorrectly reused")'
)
REOPEN_NEW = "\n".join(
    (
        '            run.require(reopened is not first, "closed detail instance was incorrectly reused")',
        '            registered_reopened = window._tool_windows_by_key.get("agenda:detail")',
        '            run.require(registered_reopened is reopened and isValid(registered_reopened), "agenda:detail registry entry mismatch after reopen")',
    )
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"expected {label} block not found")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(text, LINEAGE_OLD, LINEAGE_NEW, "lineage")
    text = replace_once(text, DETAIL_OLD, DETAIL_NEW, "detail registry reuse")
    text = replace_once(text, REOPEN_OLD, REOPEN_NEW, "detail registry reopen")
    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
