from __future__ import annotations

from pathlib import Path

from analysis_center.analysis_data_loader import load_analysis_data
from analysis_center.analysis_dashboard_workspace import source_workspace_key
from analysis_center.analysis_settings import NORMALIZED_DATA_KEYS
from src.services.sts_database import CURRENT_SCHEMA_VERSION, read_sts_schema_version
from tools.create_manual_sts_latest import create_manual_sts


def test_analysis_loader_reads_current_schema_v17_manual_sts_read_only(tmp_path):
    source = create_manual_sts(tmp_path / "manual-analysis-current-main.sts")
    before = source.stat()

    data = load_analysis_data(source=source, use_sample=False)

    assert CURRENT_SCHEMA_VERSION >= 17
    assert read_sts_schema_version(source) == CURRENT_SCHEMA_VERSION
    assert set(NORMALIZED_DATA_KEYS) <= set(data)
    assert "health_items" not in data
    assert data["contracts"]
    assert data["platforms"]
    assert data["acceptances"]
    assert data["systems"]
    assert data["components"]
    assert data["users"]
    assert data["tags"]
    assert data["deadlines"]
    assert all("planned_acceptance_date" in row for row in data["acceptances"])
    assert data["_meta"][0]["source"] == "sqlite_read_only"

    after = source.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_analysis_source_workspace_key_survives_current_versioned_sts_rename(tmp_path):
    first = tmp_path / "STS-A1__v17__2026-07-09_10-00.sts"
    second = tmp_path / "STS-A1__v18__2026-07-09_11-30.sts"
    other = tmp_path / "STS-B1__v18__2026-07-09_11-30.sts"

    assert source_workspace_key(first) == source_workspace_key(second)
    assert source_workspace_key(first) != source_workspace_key(other)
