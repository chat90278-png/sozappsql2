from __future__ import annotations

import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .analysis_dashboard_workspace import source_workspace_key
from .analysis_definitions import (
    AnalysisDefinition,
    AnalysisValidationError,
    DashboardDefinition,
)


ANALYSIS_REPOSITORY_SCHEMA_VERSION = 1
LOGGER = logging.getLogger(__name__)


class AnalysisRepositoryError(RuntimeError):
    """Base error for saved-analysis repository failures."""


class AnalysisRepositoryCorruptError(AnalysisRepositoryError):
    """Raised when the repository JSON cannot be trusted safely."""


class AnalysisRepositorySchemaError(AnalysisRepositoryError):
    """Raised when the repository schema version/root shape is unsupported."""


@dataclass(frozen=True, slots=True)
class AnalysisRepositoryIssue:
    entry_type: str
    index: int
    entry_id: str
    message: str


class AnalysisRepository(ABC):
    @abstractmethod
    def list_analyses(self) -> list[AnalysisDefinition]: ...

    @abstractmethod
    def get_analysis(self, analysis_id: str) -> AnalysisDefinition | None: ...

    @abstractmethod
    def save_analysis(self, definition: AnalysisDefinition) -> None: ...

    @abstractmethod
    def delete_analysis(self, analysis_id: str) -> bool: ...

    @abstractmethod
    def list_dashboards(self) -> list[DashboardDefinition]: ...

    @abstractmethod
    def get_dashboard(self, dashboard_id: str) -> DashboardDefinition | None: ...

    @abstractmethod
    def save_dashboard(self, definition: DashboardDefinition) -> None: ...

    @abstractmethod
    def delete_dashboard(self, dashboard_id: str) -> bool: ...


class MemoryAnalysisRepository(AnalysisRepository):
    def __init__(self) -> None:
        self._analyses: dict[str, AnalysisDefinition] = {}
        self._dashboards: dict[str, DashboardDefinition] = {}

    @staticmethod
    def _analysis_order(definition: AnalysisDefinition) -> tuple[str, str]:
        return (definition.title.casefold(), definition.analysis_id)

    @staticmethod
    def _dashboard_order(definition: DashboardDefinition) -> tuple[int, str, str]:
        return (definition.sort_order, definition.title.casefold(), definition.dashboard_id)

    def list_analyses(self) -> list[AnalysisDefinition]:
        return deepcopy(sorted(self._analyses.values(), key=self._analysis_order))

    def get_analysis(self, analysis_id: str) -> AnalysisDefinition | None:
        value = self._analyses.get(analysis_id)
        return deepcopy(value) if value is not None else None

    def save_analysis(self, definition: AnalysisDefinition) -> None:
        self._analyses[definition.analysis_id] = deepcopy(definition)

    def delete_analysis(self, analysis_id: str) -> bool:
        return self._analyses.pop(analysis_id, None) is not None

    def list_dashboards(self) -> list[DashboardDefinition]:
        return deepcopy(sorted(self._dashboards.values(), key=self._dashboard_order))

    def get_dashboard(self, dashboard_id: str) -> DashboardDefinition | None:
        value = self._dashboards.get(dashboard_id)
        return deepcopy(value) if value is not None else None

    def save_dashboard(self, definition: DashboardDefinition) -> None:
        self._dashboards[definition.dashboard_id] = deepcopy(definition)

    def delete_dashboard(self, dashboard_id: str) -> bool:
        return self._dashboards.pop(dashboard_id, None) is not None


class FileAnalysisRepository(AnalysisRepository):
    """Source-scoped JSON repository for persisted custom analyses.

    Root JSON failures put the repository into a protected state. Entry-level
    failures are isolated and the original raw entries are preserved on later
    safe writes so unrelated CRUD does not silently discard user data.
    """

    def __init__(self, source: Any = None, root: Path | str | None = None) -> None:
        self.source = source
        self.root = Path(root) if root is not None else default_analysis_repository_root()
        self._analyses: dict[str, AnalysisDefinition] = {}
        self._dashboards: dict[str, DashboardDefinition] = {}
        self._invalid_analysis_entries: list[Any] = []
        self._invalid_dashboard_entries: list[Any] = []
        self._load_issues: list[AnalysisRepositoryIssue] = []
        self._load_error: AnalysisRepositoryError | None = None
        self._load()

    @property
    def load_issues(self) -> tuple[AnalysisRepositoryIssue, ...]:
        return tuple(self._load_issues)

    @property
    def load_error(self) -> AnalysisRepositoryError | None:
        return self._load_error

    def repository_path(self) -> Path:
        return self.root / f"{source_workspace_key(self.source)}.json"

    def backup_path(self) -> Path:
        path = self.repository_path()
        return path.with_name(f"{path.stem}.backup{path.suffix}")

    @staticmethod
    def _analysis_order(definition: AnalysisDefinition) -> tuple[str, str]:
        return (definition.title.casefold(), definition.analysis_id)

    @staticmethod
    def _dashboard_order(definition: DashboardDefinition) -> tuple[int, str, str]:
        return (definition.sort_order, definition.title.casefold(), definition.dashboard_id)

    def list_analyses(self) -> list[AnalysisDefinition]:
        self._ensure_available()
        return deepcopy(sorted(self._analyses.values(), key=self._analysis_order))

    def get_analysis(self, analysis_id: str) -> AnalysisDefinition | None:
        self._ensure_available()
        value = self._analyses.get(analysis_id)
        return deepcopy(value) if value is not None else None

    def save_analysis(self, definition: AnalysisDefinition) -> None:
        self._ensure_available()
        validated = self._validated_analysis(definition)
        candidate = dict(self._analyses)
        candidate[validated.analysis_id] = validated
        self._persist(analyses=candidate, dashboards=self._dashboards)
        self._analyses = candidate

    def delete_analysis(self, analysis_id: str) -> bool:
        self._ensure_available()
        if analysis_id not in self._analyses:
            return False
        candidate = dict(self._analyses)
        del candidate[analysis_id]
        self._persist(analyses=candidate, dashboards=self._dashboards)
        self._analyses = candidate
        return True

    def list_dashboards(self) -> list[DashboardDefinition]:
        self._ensure_available()
        return deepcopy(sorted(self._dashboards.values(), key=self._dashboard_order))

    def get_dashboard(self, dashboard_id: str) -> DashboardDefinition | None:
        self._ensure_available()
        value = self._dashboards.get(dashboard_id)
        return deepcopy(value) if value is not None else None

    def save_dashboard(self, definition: DashboardDefinition) -> None:
        self._ensure_available()
        validated = self._validated_dashboard(definition)
        candidate = dict(self._dashboards)
        candidate[validated.dashboard_id] = validated
        self._persist(analyses=self._analyses, dashboards=candidate)
        self._dashboards = candidate

    def delete_dashboard(self, dashboard_id: str) -> bool:
        self._ensure_available()
        if dashboard_id not in self._dashboards:
            return False
        candidate = dict(self._dashboards)
        del candidate[dashboard_id]
        self._persist(analyses=self._analyses, dashboards=candidate)
        self._dashboards = candidate
        return True

    def _load(self) -> None:
        path = self.repository_path()
        if not path.exists():
            return
        try:
            payload = self._read_payload(path)
            self._validate_root(payload, path)
            self._load_entries(payload)
        except AnalysisRepositoryError as exc:
            self._load_error = exc

    def _load_entries(self, payload: Mapping[str, Any]) -> None:
        raw_analyses = payload.get("analyses", [])
        raw_dashboards = payload.get("dashboards", [])
        assert isinstance(raw_analyses, list)
        assert isinstance(raw_dashboards, list)

        for index, raw in enumerate(raw_analyses):
            try:
                definition = AnalysisDefinition.from_dict(raw)
            except (AnalysisValidationError, TypeError, ValueError) as exc:
                self._invalid_analysis_entries.append(deepcopy(raw))
                issue = AnalysisRepositoryIssue(
                    entry_type="analysis",
                    index=index,
                    entry_id=self._entry_id(raw, "analysis_id"),
                    message=str(exc),
                )
                self._load_issues.append(issue)
                LOGGER.warning("Saved analysis entry could not be loaded: %s", issue)
                continue
            if definition.analysis_id in self._analyses:
                self._invalid_analysis_entries.append(deepcopy(raw))
                issue = AnalysisRepositoryIssue(
                    entry_type="analysis",
                    index=index,
                    entry_id=definition.analysis_id,
                    message="Duplicate analysis_id",
                )
                self._load_issues.append(issue)
                LOGGER.warning("Saved analysis entry could not be loaded: %s", issue)
                continue
            self._analyses[definition.analysis_id] = definition

        for index, raw in enumerate(raw_dashboards):
            try:
                definition = DashboardDefinition.from_dict(raw)
            except (AnalysisValidationError, TypeError, ValueError) as exc:
                self._invalid_dashboard_entries.append(deepcopy(raw))
                issue = AnalysisRepositoryIssue(
                    entry_type="dashboard",
                    index=index,
                    entry_id=self._entry_id(raw, "dashboard_id"),
                    message=str(exc),
                )
                self._load_issues.append(issue)
                LOGGER.warning("Saved dashboard entry could not be loaded: %s", issue)
                continue
            if definition.dashboard_id in self._dashboards:
                self._invalid_dashboard_entries.append(deepcopy(raw))
                issue = AnalysisRepositoryIssue(
                    entry_type="dashboard",
                    index=index,
                    entry_id=definition.dashboard_id,
                    message="Duplicate dashboard_id",
                )
                self._load_issues.append(issue)
                LOGGER.warning("Saved dashboard entry could not be loaded: %s", issue)
                continue
            self._dashboards[definition.dashboard_id] = definition

    def _persist(
        self,
        *,
        analyses: Mapping[str, AnalysisDefinition],
        dashboards: Mapping[str, DashboardDefinition],
    ) -> None:
        path = self.repository_path()
        payload: dict[str, Any] = {
            "schema_version": ANALYSIS_REPOSITORY_SCHEMA_VERSION,
            "analyses": [
                definition.to_dict()
                for definition in sorted(analyses.values(), key=self._analysis_order)
            ]
            + deepcopy(self._invalid_analysis_entries),
            "dashboards": [
                definition.to_dict()
                for definition in sorted(dashboards.values(), key=self._dashboard_order)
            ]
            + deepcopy(self._invalid_dashboard_entries),
        }

        if path.exists():
            existing = self._read_payload(path)
            self._validate_root(existing, path)
            self._write_backup(path, self.backup_path())
        self._write_atomic(path, payload)

    def _ensure_available(self) -> None:
        if self._load_error is not None:
            raise self._load_error

    @staticmethod
    def _validated_analysis(definition: AnalysisDefinition) -> AnalysisDefinition:
        if not isinstance(definition, AnalysisDefinition):
            raise AnalysisRepositoryError("AnalysisDefinition olmayan kayıt kaydedilemez.")
        try:
            return AnalysisDefinition.from_dict(definition.to_dict())
        except AnalysisValidationError as exc:
            raise AnalysisRepositoryError("Geçersiz analiz tanımı kaydedilemez.") from exc

    @staticmethod
    def _validated_dashboard(definition: DashboardDefinition) -> DashboardDefinition:
        if not isinstance(definition, DashboardDefinition):
            raise AnalysisRepositoryError("DashboardDefinition olmayan kayıt kaydedilemez.")
        try:
            return DashboardDefinition.from_dict(definition.to_dict())
        except AnalysisValidationError as exc:
            raise AnalysisRepositoryError("Geçersiz dashboard tanımı kaydedilemez.") from exc

    @staticmethod
    def _entry_id(raw: Any, key: str) -> str:
        if isinstance(raw, Mapping):
            return str(raw.get(key) or "").strip()
        return ""

    @staticmethod
    def _read_payload(path: Path) -> Mapping[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise AnalysisRepositoryError(f"Analiz repository okunamadı: {path}") from exc
        except json.JSONDecodeError as exc:
            raise AnalysisRepositoryCorruptError(
                f"Analiz repository JSON bozuk; dosya korunuyor: {path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise AnalysisRepositoryCorruptError(
                f"Analiz repository JSON object olmalıdır: {path}"
            )
        return payload

    @staticmethod
    def _validate_root(payload: Mapping[str, Any], path: Path) -> None:
        schema_version = payload.get("schema_version")
        if schema_version != ANALYSIS_REPOSITORY_SCHEMA_VERSION:
            raise AnalysisRepositorySchemaError(
                f"Desteklenmeyen analiz repository schema_version={schema_version!r}: {path}"
            )
        if not isinstance(payload.get("analyses"), list):
            raise AnalysisRepositoryCorruptError(
                f"Analiz repository analyses list olmalıdır: {path}"
            )
        if not isinstance(payload.get("dashboards"), list):
            raise AnalysisRepositoryCorruptError(
                f"Analiz repository dashboards list olmalıdır: {path}"
            )

    @staticmethod
    def _write_backup(source_path: Path, backup_path: Path) -> None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = backup_path.with_suffix(backup_path.suffix + ".tmp")
        try:
            with source_path.open("rb") as source_handle, temp_path.open("wb") as backup_handle:
                shutil.copyfileobj(source_handle, backup_handle)
                backup_handle.flush()
                os.fsync(backup_handle.fileno())
            os.replace(temp_path, backup_path)
            FileAnalysisRepository._fsync_directory(backup_path.parent)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            FileAnalysisRepository._fsync_directory(path.parent)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def default_analysis_repository_root() -> Path:
    local_app_data = str(os.getenv("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return Path(local_app_data) / "STS" / "analysis_center" / "analyses"
    return Path.home() / ".sts" / "analysis_center" / "analyses"


__all__ = [
    "ANALYSIS_REPOSITORY_SCHEMA_VERSION",
    "AnalysisRepository",
    "AnalysisRepositoryCorruptError",
    "AnalysisRepositoryError",
    "AnalysisRepositoryIssue",
    "AnalysisRepositorySchemaError",
    "FileAnalysisRepository",
    "MemoryAnalysisRepository",
    "default_analysis_repository_root",
]
