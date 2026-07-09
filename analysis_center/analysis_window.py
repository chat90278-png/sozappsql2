from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from .analysis_dashboard import build_dashboard_payload
from .analysis_definitions import AnalysisDefinition
from .analysis_models import VisualSettings
from .analysis_repository import AnalysisRepository
from .analysis_service import AnalysisService
from .analysis_settings import DEFAULT_SETTINGS


class AnalysisWindow:
    """Faz-1 için PySide bağımsız pencere/ekran denetleyici iskeleti.

    Bu sınıf büyük UI kurmaz. İleride PySide6 QDialog/QMainWindow sınıfı bu
    denetleyicinin ürettiği payload'ı kullanarak görsel ekranı oluşturabilir.
    """

    def __init__(
        self,
        source: Any = None,
        contract_index: Optional[Iterable[Mapping[str, Any]]] = None,
        settings: VisualSettings | None = None,
        analysis_repository: AnalysisRepository | None = None,
    ):
        self.source = source
        self.contract_index = list(contract_index or [])
        self.settings = (settings or DEFAULT_SETTINGS).normalized()
        self.payload: Dict[str, Any] = {}
        self.analysis_service = AnalysisService(
            source=self.source,
            contract_index=self.contract_index,
            use_sample=self.settings.empty_state_uses_sample,
            repository=analysis_repository,
        )

    def refresh_payload(self) -> Dict[str, Any]:
        self.payload = build_dashboard_payload(
            source=self.source,
            contract_index=self.contract_index,
            settings=self.settings,
            use_sample=self.settings.empty_state_uses_sample,
        )
        self.analysis_service.use_sample = self.settings.empty_state_uses_sample
        self.analysis_service.data = self.payload.get("data", {})
        return self.payload

    def set_settings(self, settings: VisualSettings) -> Dict[str, Any]:
        self.settings = settings.normalized()
        return self.refresh_payload()

    def execute_analysis(self, definition: AnalysisDefinition):
        self.analysis_service.use_sample = self.settings.empty_state_uses_sample
        return self.analysis_service.execute_analysis(definition)

    def list_builtin_analyses(self):
        return self.analysis_service.list_builtin_analyses(upcoming_days=self.settings.upcoming_days)

    def get_analysis_card(self, definition: AnalysisDefinition):
        self.analysis_service.use_sample = self.settings.empty_state_uses_sample
        return self.analysis_service.get_analysis_card(definition)

    def get_analysis_capabilities(self) -> Dict[str, Any]:
        return self.analysis_service.capabilities()
