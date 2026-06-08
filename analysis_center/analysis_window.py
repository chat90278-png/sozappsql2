from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from .analysis_dashboard import build_dashboard_payload
from .analysis_models import VisualSettings
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
    ):
        self.source = source
        self.contract_index = list(contract_index or [])
        self.settings = (settings or DEFAULT_SETTINGS).normalized()
        self.payload: Dict[str, Any] = {}

    def refresh_payload(self) -> Dict[str, Any]:
        self.payload = build_dashboard_payload(
            source=self.source,
            contract_index=self.contract_index,
            settings=self.settings,
            use_sample=self.settings.empty_state_uses_sample,
        )
        return self.payload

    def set_settings(self, settings: VisualSettings) -> Dict[str, Any]:
        self.settings = settings.normalized()
        return self.refresh_payload()
