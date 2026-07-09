from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from typing import Any, Iterable, Mapping, Optional
from uuid import uuid4

from .analysis_builtin import get_builtin_analysis, list_builtin_analyses
from .analysis_dashboard_service import DashboardComposer, DashboardCompositionError, DashboardCompositionResult
from .analysis_data_loader import load_analysis_data
from .analysis_definitions import AnalysisDefinition, AnalysisResult, AnalysisValidationError, DashboardDefinition
from .analysis_engine import AnalysisEngine
from .analysis_models import AnalysisCard, NormalizedAnalysisData
from .analysis_registry import AnalysisRegistry, DEFAULT_REGISTRY, get_analysis_capabilities
from .analysis_renderer import analysis_result_to_card
from .analysis_repository import AnalysisRepository, AnalysisRepositoryIssue, MemoryAnalysisRepository


CUSTOM_ANALYSIS_ID_PREFIX = "custom-"


def new_custom_analysis_id() -> str:
    return f"{CUSTOM_ANALYSIS_ID_PREFIX}{uuid4().hex}"


class AnalysisService:
    def __init__(
        self,
        source: Any = None,
        contract_index: Optional[Iterable[Mapping[str, Any]]] = None,
        use_sample: bool = True,
        registry: AnalysisRegistry | None = None,
        repository: AnalysisRepository | None = None,
    ):
        self.source = source
        self.contract_index = list(contract_index or [])
        self.use_sample = bool(use_sample)
        self.registry = registry or DEFAULT_REGISTRY
        self.repository = repository or MemoryAnalysisRepository()
        self.engine = AnalysisEngine(self.registry)
        self.dashboard_composer = DashboardComposer(self.engine, self.repository)
        self.data: NormalizedAnalysisData = {}

    def refresh_data(self) -> NormalizedAnalysisData:
        self.data = load_analysis_data(self.source, self.contract_index, self.use_sample)
        return self.data

    def execute_analysis(self, definition: AnalysisDefinition) -> AnalysisResult:
        if not self.data:
            self.refresh_data()
        return self.engine.execute(definition, self.data)

    def validate_analysis(self, definition: AnalysisDefinition) -> None:
        self.engine.validate(definition)

    def get_analysis_card(self, definition: AnalysisDefinition) -> AnalysisCard:
        return analysis_result_to_card(definition, self.execute_analysis(definition))

    def list_saved_analyses(self) -> list[AnalysisDefinition]:
        return self.repository.list_analyses()

    def get_saved_analysis(self, analysis_id: str) -> AnalysisDefinition | None:
        return self.repository.get_analysis(analysis_id)

    def create_saved_analysis(self, definition: AnalysisDefinition) -> AnalysisDefinition:
        candidate = replace(deepcopy(definition), analysis_id=new_custom_analysis_id())
        self.validate_analysis(candidate)
        self.repository.save_analysis(candidate)
        return candidate

    def update_saved_analysis(
        self,
        definition: AnalysisDefinition,
        analysis_id: str,
    ) -> AnalysisDefinition:
        current = self.repository.get_analysis(analysis_id)
        if current is None:
            raise AnalysisValidationError(
                "Bu analiz artık mevcut değil. Yeni analiz olarak kaydedin."
            )
        candidate = replace(deepcopy(definition), analysis_id=analysis_id)
        self.validate_analysis(candidate)
        self.repository.save_analysis(candidate)
        return candidate

    def save_analysis(self, definition: AnalysisDefinition) -> AnalysisDefinition:
        """Save a definition using its current id after engine validation."""

        candidate = deepcopy(definition)
        self.validate_analysis(candidate)
        self.repository.save_analysis(candidate)
        return candidate

    def copy_saved_analysis(self, analysis_id: str) -> AnalysisDefinition:
        source = self.repository.get_analysis(analysis_id)
        if source is None:
            raise AnalysisValidationError("Kopyalanacak analiz bulunamadı.")
        self.validate_analysis(source)
        title = self._copy_title(source.title)
        copied = replace(
            deepcopy(source),
            analysis_id=new_custom_analysis_id(),
            title=title,
        )
        self.repository.save_analysis(copied)
        return copied

    def delete_saved_analysis(self, analysis_id: str) -> bool:
        return self.repository.delete_analysis(analysis_id)

    def saved_analysis_validation_error(self, definition: AnalysisDefinition) -> str | None:
        try:
            self.validate_analysis(definition)
        except AnalysisValidationError as exc:
            return str(exc)
        return None

    def repository_load_issues(self) -> tuple[AnalysisRepositoryIssue, ...]:
        issues = getattr(self.repository, "load_issues", ())
        return tuple(issues)

    def repository_load_error(self) -> Exception | None:
        return getattr(self.repository, "load_error", None)

    def _copy_title(self, source_title: str) -> str:
        existing_titles = {item.title.casefold() for item in self.repository.list_analyses()}
        base = f"{source_title} Kopya"
        if base.casefold() not in existing_titles:
            return base
        suffix = 2
        while f"{base} ({suffix})".casefold() in existing_titles:
            suffix += 1
        return f"{base} ({suffix})"

    def list_builtin_analyses(self, today: date | None = None, upcoming_days: int = 60) -> list[AnalysisDefinition]:
        return list_builtin_analyses(today=today, upcoming_days=upcoming_days)

    def get_builtin_card(self, analysis_id: str, today: date | None = None, upcoming_days: int = 60) -> AnalysisCard:
        definition = get_builtin_analysis(analysis_id, today=today, upcoming_days=upcoming_days)
        return self.get_analysis_card(definition)

    def compose_dashboard(
        self,
        dashboard: DashboardDefinition,
        today: date | None = None,
        upcoming_days: int = 60,
    ) -> DashboardCompositionResult:
        if not self.data:
            self.refresh_data()
        return self.dashboard_composer.compose(
            dashboard,
            self.data,
            today=today,
            upcoming_days=upcoming_days,
        )

    def compose_dashboard_by_id(
        self,
        dashboard_id: str,
        today: date | None = None,
        upcoming_days: int = 60,
    ) -> DashboardCompositionResult:
        dashboard = self.repository.get_dashboard(dashboard_id)
        if dashboard is None:
            raise DashboardCompositionError(f"Dashboard not found: {dashboard_id}")
        return self.compose_dashboard(
            dashboard,
            today=today,
            upcoming_days=upcoming_days,
        )

    def capabilities(self) -> dict[str, Any]:
        return get_analysis_capabilities(self.registry)


__all__ = ["AnalysisService", "CUSTOM_ANALYSIS_ID_PREFIX", "new_custom_analysis_id"]
