from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_current_smoke_source import create_analysis_smoke_source
import smoke_analysis_center_release_acceptance as tur21_acceptance
from src.services.sts_database import CURRENT_SCHEMA_VERSION, read_sts_schema_version


def _current_runtime_acceptance() -> None:
    for module_name in (
        "app",
        "analysis_center",
        "analysis_center.analysis_window",
        "analysis_center.analysis_excel_export",
        "src.ui.analysis_center_window",
        "src.ui.main_page_analysis_window",
    ):
        importlib.import_module(module_name)
        print(f"import_{module_name}=PASS")

    spec_path = ROOT / "STS.spec"
    text = spec_path.read_text(encoding="utf-8")
    ast.parse(text)
    assert 'collect_submodules("openpyxl")' in text
    print("spec_STS.spec=openpyxl_hiddenimports:PASS")


def main() -> None:
    source = create_analysis_smoke_source(ROOT)
    assert source == tur21_acceptance.SOURCE
    assert read_sts_schema_version(source) == CURRENT_SCHEMA_VERSION
    print(f"current_schema_version={CURRENT_SCHEMA_VERSION}")
    print(f"current_main_release_source={source}")

    tur21_acceptance._runtime_acceptance = _current_runtime_acceptance
    tur21_acceptance.main()

    print("CURRENT MAIN ANALYSIS CENTER RELEASE ACCEPTANCE: PASS")


if __name__ == "__main__":
    main()
