from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path.cwd()
MAIN_PATH = ROOT / "src" / "ui" / "main_window.py"
README_PATH = ROOT / "README.md"
CHANGED_PATHS = (
    "src/_build_info.py",
    "scripts/write_build_info.py",
    "src/ui/main_window.py",
    "README.md",
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, got {count}")
    return text.replace(old, new, 1)


def apply_main_window_changes() -> None:
    text = MAIN_PATH.read_text(encoding="utf-8")

    import_anchor = "from src.services import perf_tracker\n"
    text = replace_once(
        text,
        import_anchor,
        import_anchor + "from src._build_info import BUILD_COMMIT, BUILD_COMMIT_SHORT, BUILD_DATE\n",
        "main import",
    )

    method_anchor = (
        '            QMessageBox.warning(self, "Kullanım Kılavuzu", '
        'f"Kullanım kılavuzu açılamadı:\\n{exc}")\n\n'
        '    def build(self):\n'
    )
    method_replacement = (
        '            QMessageBox.warning(self, "Kullanım Kılavuzu", '
        'f"Kullanım kılavuzu açılamadı:\\n{exc}")\n\n'
        '    def show_build_info(self):\n'
        '        QMessageBox.information(\n'
        '            self,\n'
        '            "Sürüm / Build",\n'
        '            f"Commit: {BUILD_COMMIT}\\n"\n'
        '            f"Kısa commit: {BUILD_COMMIT_SHORT}\\n"\n'
        '            f"Build tarihi (UTC): {BUILD_DATE}",\n'
        '        )\n\n'
        '    def build(self):\n'
    )
    text = replace_once(text, method_anchor, method_replacement, "show_build_info method")

    menu_anchor = '        self._add_menu_action(help_menu, "Kullanım Kılavuzu", self.open_usage_guide)\n'
    text = replace_once(
        text,
        menu_anchor,
        menu_anchor + '        self._add_menu_action(help_menu, "Sürüm / Build", self.show_build_info)\n',
        "help menu action",
    )
    MAIN_PATH.write_text(text, encoding="utf-8")


def create_build_info_files() -> None:
    (ROOT / "src" / "_build_info.py").write_text(
        'BUILD_COMMIT = "unknown"\n'
        'BUILD_COMMIT_SHORT = "unknown"\n'
        'BUILD_DATE = "unknown"\n',
        encoding="utf-8",
    )

    scripts_dir = ROOT / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "write_build_info.py").write_text(
        '''from __future__ import annotations\n\nimport subprocess\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nBUILD_INFO_PATH = ROOT / "src" / "_build_info.py"\n\n\ndef _git(*args: str) -> str:\n    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()\n\n\ndef main() -> None:\n    build_commit = _git("rev-parse", "HEAD")\n    build_commit_short = _git("rev-parse", "--short", "HEAD")\n    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")\n    BUILD_INFO_PATH.write_text(\n        f'BUILD_COMMIT = "{build_commit}"\\n'\n        f'BUILD_COMMIT_SHORT = "{build_commit_short}"\\n'\n        f'BUILD_DATE = "{build_date}"\\n',\n        encoding="utf-8",\n    )\n    print(f"Wrote {BUILD_INFO_PATH.relative_to(ROOT)} for {build_commit_short} at {build_date}")\n\n\nif __name__ == "__main__":\n    main()\n''',
        encoding="utf-8",
    )


def update_readme() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    anchor = "STS.exe is built from the checked-in PyInstaller spec:\n\n"
    addition = (
        anchor
        + "Before running PyInstaller, refresh the embedded build metadata:\n\n"
        + "```bash\npython scripts/write_build_info.py\n```\n\n"
        + "`src/_build_info.py` keeps `unknown` placeholders in source control; "
        + "the script replaces them with the current HEAD commit, short commit, and UTC build timestamp.\n\n"
    )
    README_PATH.write_text(replace_once(text, anchor, addition, "README build step"), encoding="utf-8")


def verify_and_stage_artifact() -> None:
    subprocess.run(["git", "add", "-N", "src/_build_info.py", "scripts/write_build_info.py"], check=True)
    output = subprocess.check_output(["git", "diff", "--numstat", "--", *CHANGED_PATHS], text=True)
    stats: dict[str, tuple[int, int]] = {}
    for line in output.splitlines():
        added, deleted, path = line.split("\t", 2)
        stats[path] = (int(added), int(deleted))

    if set(stats) != set(CHANGED_PATHS):
        raise SystemExit(f"unexpected changed paths: {stats}")
    if stats["src/ui/main_window.py"][1] != 0:
        raise SystemExit(f"main_window.py has deletions: {stats['src/ui/main_window.py']}")
    if stats["README.md"][1] != 0:
        raise SystemExit(f"README.md has deletions: {stats['README.md']}")

    artifact = ROOT / "build-info-candidate-artifact"
    if artifact.exists():
        shutil.rmtree(artifact)
    for relative in CHANGED_PATHS:
        source = ROOT / relative
        target = artifact / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (artifact / "diff-numstat.txt").write_text(output, encoding="utf-8")
    print(output, end="")


def main() -> None:
    apply_main_window_changes()
    create_build_info_files()
    update_readme()
    verify_and_stage_artifact()


if __name__ == "__main__":
    main()
