from __future__ import annotations

import logging
from dataclasses import dataclass

from .analysis_dashboard_layout import placement_order
from .analysis_dashboard_workspace import DashboardWorkspace
from .analysis_definitions import AnalysisValidationError
from .analysis_models import AnalysisCard
from .analysis_renderer import analysis_result_to_card
from .analysis_service import CUSTOM_ANALYSIS_ID_PREFIX, AnalysisService


CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID = "custom_analysis"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CustomDashboardResolutionIssue:
    analysis_id: str
    message: str
    kind: str


class CustomAnalysisDashboardController:
    """Resolve stable saved-analysis references for the existing Dashboard workspace."""

    def __init__(self, service: AnalysisService):
        self.service = service

    @staticmethod
    def validate_analysis_id(analysis_id: str) -> str:
        value = str(analysis_id or "").strip()
        if not value.startswith(CUSTOM_ANALYSIS_ID_PREFIX):
            raise AnalysisValidationError(
                "Dashboard'a eklemek için önce analizi kaydedin."
            )
        return value

    def is_pinned(self, workspace: DashboardWorkspace, analysis_id: str) -> bool:
        value = str(analysis_id or "").strip()
        return bool(value) and workspace.contains(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            value,
        )

    def resolve_saved_card(self, analysis_id: str) -> AnalysisCard:
        analysis_id = self.validate_analysis_id(analysis_id)
        load_error = self.service.repository_load_error()
        if load_error is not None:
            raise AnalysisValidationError(
                "Kaydedilmiş analiz deposu yüklenemediği için özel Dashboard kartı çözümlenemiyor."
            )
        definition = self.service.get_saved_analysis(analysis_id)
        if definition is None:
            raise AnalysisValidationError("Kaydedilmiş analiz bulunamadı.")
        self.service.validate_analysis(definition)
        result = self.service.execute_analysis(definition)
        card = analysis_result_to_card(definition, result)
        card.screen_id = CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
        card.card_id = analysis_id
        card.meta = dict(card.meta)
        card.meta.update(
            {
                "custom_analysis": True,
                "custom_analysis_id": analysis_id,
            }
        )
        return card

    def pin(self, workspace: DashboardWorkspace, analysis_id: str) -> bool:
        card = self.resolve_saved_card(analysis_id)
        return workspace.pin(card)

    def unpin(self, workspace: DashboardWorkspace, analysis_id: str) -> bool:
        analysis_id = self.validate_analysis_id(analysis_id)
        return workspace.remove(CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID, analysis_id)

    def resolve_pinned_cards(
        self,
        workspace: DashboardWorkspace,
    ) -> tuple[list[AnalysisCard], list[CustomDashboardResolutionIssue]]:
        analysis_ids: list[str] = []
        seen: set[str] = set()
        for placement in sorted(workspace.placements, key=placement_order):
            if placement.source_screen_id != CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID:
                continue
            if placement.card_id in seen:
                continue
            seen.add(placement.card_id)
            analysis_ids.append(placement.card_id)

        if not analysis_ids:
            return [], []

        load_error = self.service.repository_load_error()
        if load_error is not None:
            return [], [
                CustomDashboardResolutionIssue(
                    analysis_id=analysis_id,
                    message="Kaydedilmiş analiz deposu yüklenemedi; Dashboard yerleşimi korundu.",
                    kind="repository",
                )
                for analysis_id in analysis_ids
            ]

        cards: list[AnalysisCard] = []
        issues: list[CustomDashboardResolutionIssue] = []
        for analysis_id in analysis_ids:
            try:
                definition = self.service.get_saved_analysis(analysis_id)
                if definition is None:
                    issues.append(
                        CustomDashboardResolutionIssue(
                            analysis_id=analysis_id,
                            message="Kaydedilmiş analiz bulunamadı; Dashboard yerleşimi korundu.",
                            kind="missing",
                        )
                    )
                    continue
                cards.append(self.resolve_saved_card(analysis_id))
            except AnalysisValidationError as exc:
                issues.append(
                    CustomDashboardResolutionIssue(
                        analysis_id=analysis_id,
                        message=str(exc),
                        kind="validation",
                    )
                )
            except Exception as exc:
                issues.append(
                    CustomDashboardResolutionIssue(
                        analysis_id=analysis_id,
                        message=str(exc) or "Özel analiz kartı çalıştırılamadı.",
                        kind="execution",
                    )
                )
        return cards, issues

    def workspace_catalog(self) -> tuple[set[str], set[str]]:
        """Return known custom card keys and sources that must not be pruned."""

        if self.service.repository_load_error() is not None:
            return set(), {CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}

        try:
            known_ids = {
                definition.analysis_id for definition in self.service.list_saved_analyses()
            }
        except Exception:
            LOGGER.exception("Saved custom-analysis catalog could not be read for Dashboard pruning")
            return set(), {CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}
        for issue in self.service.repository_load_issues():
            if issue.entry_type == "analysis" and issue.entry_id:
                known_ids.add(issue.entry_id)
        return {
            f"{CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}:{analysis_id}"
            for analysis_id in known_ids
        }, set()


__all__ = [
    "CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID",
    "CustomAnalysisDashboardController",
    "CustomDashboardResolutionIssue",
]
