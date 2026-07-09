from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis_center.analysis_definitions import AnalysisDefinition, MeasureDefinition
from analysis_center.analysis_repository import (
    ANALYSIS_REPOSITORY_SCHEMA_VERSION,
    AnalysisRepositoryCorruptError,
    AnalysisRepositoryError,
    AnalysisRepositorySchemaError,
    FileAnalysisRepository,
)


def definition(analysis_id: str, title: str = "Test") -> AnalysisDefinition:
    return AnalysisDefinition(
        analysis_id=analysis_id,
        title=title,
        dataset="contracts",
        visualization="kpi",
        measures=[MeasureDefinition(field="", aggregation="count_rows")],
    )


def test_empty_repository(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    assert repo.list_analyses() == []
    assert repo.get_analysis("missing") is None
    assert repo.load_issues == ()
    assert repo.load_error is None


def test_save_list_get_update_and_delete(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    repo.save_analysis(definition("a", "Alpha"))
    assert [item.analysis_id for item in repo.list_analyses()] == ["a"]
    assert repo.get_analysis("a").title == "Alpha"

    repo.save_analysis(definition("a", "Updated"))
    assert len(repo.list_analyses()) == 1
    assert repo.get_analysis("a").title == "Updated"
    assert repo.delete_analysis("a") is True
    assert repo.delete_analysis("a") is False
    assert repo.list_analyses() == []


def test_two_analyses_preserved_and_deterministically_sorted(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    repo.save_analysis(definition("z", "Zulu"))
    repo.save_analysis(definition("b", "Alpha"))
    repo.save_analysis(definition("a", "Alpha"))
    assert [(item.title, item.analysis_id) for item in repo.list_analyses()] == [
        ("Alpha", "a"),
        ("Alpha", "b"),
        ("Zulu", "z"),
    ]


def test_repository_reinstantiation_persists_analysis(tmp_path):
    source = "source-a.sts"
    repo = FileAnalysisRepository(source, tmp_path)
    repo.save_analysis(definition("a", "Persisted"))
    reloaded = FileAnalysisRepository(source, tmp_path)
    assert reloaded.get_analysis("a").to_dict() == definition("a", "Persisted").to_dict()


def test_schema_version_and_definition_serialization_written(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    item = definition("a")
    repo.save_analysis(item)
    payload = json.loads(repo.repository_path().read_text(encoding="utf-8"))
    assert payload["schema_version"] == ANALYSIS_REPOSITORY_SCHEMA_VERSION
    assert payload["analyses"] == [item.to_dict()]
    assert payload["dashboards"] == []
    assert AnalysisDefinition.from_dict(payload["analyses"][0]).to_dict() == item.to_dict()


def test_source_scoped_files_are_isolated_and_same_source_key_is_stable(tmp_path):
    repo_a = FileAnalysisRepository("source-a.sts", tmp_path)
    repo_b = FileAnalysisRepository("source-b.sts", tmp_path)
    repo_a_again = FileAnalysisRepository("source-a.sts", tmp_path)
    assert repo_a.repository_path() == repo_a_again.repository_path()
    assert repo_a.repository_path() != repo_b.repository_path()
    repo_a.save_analysis(definition("a"))
    assert repo_b.list_analyses() == []


def test_atomic_write_cleans_temp_file_and_uses_replace(tmp_path, monkeypatch):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    calls: list[tuple[Path, Path]] = []
    import analysis_center.analysis_repository as module

    real_replace = module.os.replace

    def spy_replace(source, target):
        calls.append((Path(source), Path(target)))
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", spy_replace)
    repo.save_analysis(definition("a"))
    assert calls
    assert calls[-1][1] == repo.repository_path()
    assert repo.repository_path().with_suffix(".json.tmp").exists() is False


def test_backup_created_before_overwrite(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    repo.save_analysis(definition("a", "First"))
    first_payload = json.loads(repo.repository_path().read_text(encoding="utf-8"))
    repo.save_analysis(definition("a", "Second"))
    assert json.loads(repo.backup_path().read_text(encoding="utf-8")) == first_payload
    assert repo.get_analysis("a").title == "Second"


def test_invalid_repository_object_rejected(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    with pytest.raises(AnalysisRepositoryError, match="AnalysisDefinition"):
        repo.save_analysis(object())  # type: ignore[arg-type]


def test_corrupt_root_json_is_controlled_and_never_overwritten(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    protected = FileAnalysisRepository("source-a.sts", tmp_path)
    assert isinstance(protected.load_error, AnalysisRepositoryCorruptError)
    with pytest.raises(AnalysisRepositoryCorruptError):
        protected.list_analyses()
    with pytest.raises(AnalysisRepositoryCorruptError):
        protected.save_analysis(definition("a"))
    assert path.read_text(encoding="utf-8") == "{not-json"


def test_invalid_schema_version_is_controlled(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 99, "analyses": [], "dashboards": []}), encoding="utf-8")
    protected = FileAnalysisRepository("source-a.sts", tmp_path)
    assert isinstance(protected.load_error, AnalysisRepositorySchemaError)
    with pytest.raises(AnalysisRepositorySchemaError):
        protected.delete_analysis("a")


def test_invalid_root_shape_is_controlled(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "analyses": {}, "dashboards": []}), encoding="utf-8")
    protected = FileAnalysisRepository("source-a.sts", tmp_path)
    assert isinstance(protected.load_error, AnalysisRepositoryCorruptError)


def test_one_invalid_analysis_entry_does_not_hide_valid_entries_and_issue_has_context(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "analyses": [
            definition("a", "Alpha").to_dict(),
            {"analysis_id": "broken", "title": "Broken"},
            definition("c", "Charlie").to_dict(),
        ],
        "dashboards": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = FileAnalysisRepository("source-a.sts", tmp_path)
    assert [item.analysis_id for item in loaded.list_analyses()] == ["a", "c"]
    assert len(loaded.load_issues) == 1
    issue = loaded.load_issues[0]
    assert issue.entry_type == "analysis"
    assert issue.index == 1
    assert issue.entry_id == "broken"


def test_invalid_entry_is_preserved_on_later_safe_save(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    path = repo.repository_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    broken = {"analysis_id": "broken", "title": "Broken"}
    payload = {
        "schema_version": 1,
        "analyses": [definition("a", "Alpha").to_dict(), broken, definition("c", "Charlie").to_dict()],
        "dashboards": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = FileAnalysisRepository("source-a.sts", tmp_path)
    loaded.save_analysis(definition("a", "Alpha Updated"))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert broken in saved["analyses"]
    reloaded = FileAnalysisRepository("source-a.sts", tmp_path)
    assert {item.analysis_id for item in reloaded.list_analyses()} == {"a", "c"}
    assert len(reloaded.load_issues) == 1
    backup = json.loads(loaded.backup_path().read_text(encoding="utf-8"))
    assert broken in backup["analyses"]


def test_external_corruption_after_load_blocks_overwrite(tmp_path):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    repo.save_analysis(definition("a"))
    path = repo.repository_path()
    path.write_text("broken now", encoding="utf-8")
    with pytest.raises(AnalysisRepositoryCorruptError):
        repo.save_analysis(definition("b"))
    assert path.read_text(encoding="utf-8") == "broken now"


def test_atomic_replace_failure_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    repo = FileAnalysisRepository("source-a.sts", tmp_path)
    repo.save_analysis(definition("a", "Original"))
    path = repo.repository_path()
    original = path.read_text(encoding="utf-8")
    import analysis_center.analysis_repository as module

    real_replace = module.os.replace

    def fail_repository_replace(source, target):
        if Path(target) == path:
            raise OSError("simulated replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_repository_replace)
    with pytest.raises(OSError, match="simulated"):
        repo.save_analysis(definition("b", "Second"))
    assert path.read_text(encoding="utf-8") == original
    assert path.with_suffix(".json.tmp").exists() is False
