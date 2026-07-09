from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analysis_builtin import get_builtin_analysis
from .analysis_definitions import (
    AnalysisDefinition,
    AnalysisResult,
    AnalysisValidationError,
    DashboardDefinition,
)
from .analysis_engine import AnalysisEngine
from .analysis_models import AnalysisCard, DashboardItem, NormalizedAnalysisData
from .analysis_renderer import analysis_result_to_card
from .analysis_repository import AnalysisRepository


class DashboardCompositionError(ValueError):
    """Raised for controlled dashboard composition request errors."""


@dataclass(slots=True)
class DashboardCompositionResult:
    dashboard: DashboardDefinition
    item: DashboardItem
    analysis_results: list[AnalysisResult]
    cards: list[AnalysisCard]
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class DashboardComposer:
    """Resolve dashboard analysis references and compose generic analysis cards."""

    def __init__(self, engine: AnalysisEngine, repository: AnalysisRepository):
        self.engine = engine
        self.repository = repository

    def resolve_analysis(
        self,
        analysis_id: str,
        today: date | None = None,
        upcoming_days: int = 60,
    ) -> tuple[AnalysisDefinition | None, str | None]:
        repository_definition = self.repository.get_analysis(analysis_id)
        if repository_definition is not None:
            return repository_definition, "repository"
        try:
            return get_builtin_analysis(analysis_id, today=today, upcoming_days=upcoming_days), "builtin"
        except KeyError:
            return None, None

    def compose(
        self,
        dashboard: DashboardDefinition,
        data: NormalizedAnalysisData,
        today: date | None = None,
        upcoming_days: int = 60,
    ) -> DashboardCompositionResult:
        if not isinstance(dashboard, DashboardDefinition):
            raise DashboardCompositionError("dashboard DashboardDefinition olmalıdır.")

        warnings: list[str] = []
        errors: list[dict[str, Any]] = []
        analysis_results: list[AnalysisResult] = []
        cards: list[AnalysisCard] = []
        analysis_sources: dict[str, str] = {}
        seen: set[str] = set()

        for reference_index, analysis_id in enumerate(dashboard.analysis_ids, start=1):
            if analysis_id in seen:
                warnings.append(f"duplicate dashboard analysis reference: {analysis_id}")
                continue
            seen.add(analysis_id)

            definition, source = self.resolve_analysis(
                analysis_id,
                today=today,
                upcoming_days=upcoming_days,
            )
            if definition is None or source is None:
                warnings.append(f"dashboard analysis not found: {analysis_id}")
                continue

            try:
                result = self.engine.execute(definition, data)
                card = analysis_result_to_card(definition, result)
            except AnalysisValidationError as exc:
                errors.append({"analysis_id": analysis_id, "error": str(exc)})
                continue

            # Dashboard composition order follows analysis_ids, not definition/card options.
            card.sort_order = reference_index * 10
            analysis_results.append(result)
            cards.append(card)
            analysis_sources[analysis_id] = source

        composition_meta = {
            "requested_analysis_count": len(dashboard.analysis_ids),
            "executed_analysis_count": len(analysis_results),
            "card_count": len(cards),
            "analysis_sources": analysis_sources,
            "warnings": list(warnings),
            "errors": deepcopy(errors),
        }
        item = DashboardItem(
            item_id=dashboard.dashboard_id,
            title=dashboard.title,
            cards=cards,
            enabled=dashboard.enabled,
            sort_order=dashboard.sort_order,
            meta={
                "layout": deepcopy(dashboard.layout),
                "dashboard_meta": deepcopy(dashboard.meta),
                "composition": deepcopy(composition_meta),
            },
        )
        return DashboardCompositionResult(
            dashboard=deepcopy(dashboard),
            item=item,
            analysis_results=analysis_results,
            cards=cards,
            warnings=warnings,
            errors=errors,
            meta=composition_meta,
        )
