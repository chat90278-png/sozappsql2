from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_INFO_PATH = ROOT / "src" / "_build_info.py"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    build_commit = _git("rev-parse", "HEAD")
    build_commit_short = _git("rev-parse", "--short", "HEAD")
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    BUILD_INFO_PATH.write_text(
        f'BUILD_COMMIT = "{build_commit}"\n'
        f'BUILD_COMMIT_SHORT = "{build_commit_short}"\n'
        f'BUILD_DATE = "{build_date}"\n',
        encoding="utf-8",
    )
    print(f"Wrote {BUILD_INFO_PATH.relative_to(ROOT)} for {build_commit_short} at {build_date}")


if __name__ == "__main__":
    main()
