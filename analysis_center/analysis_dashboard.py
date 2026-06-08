from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from .analysis_cards import build_dashboard_items
from .analysis_data_loader import load_analysis_data
from .analysis_metrics import compute_metrics
from .analysis_models import VisualSettings
from .analysis_settings import DEFAULT_SETTINGS


def build_dashboard_payload(
    source: Any = None,
    contract_index: Optional[Iterable[Mapping[str, Any]]] = None,
    settings: VisualSettings | None = None,
    use_sample: bool | None = None,
) -> Dict[str, Any]:
    """Veri, metrik ve kart tanımlarını tek payload halinde üretir."""

    visual_settings = (settings or DEFAULT_SETTINGS).normalized()
    sample_enabled = visual_settings.empty_state_uses_sample if use_sample is None else bool(use_sample)
    data = load_analysis_data(source=source, contract_index=contract_index, use_sample=sample_enabled)
    metrics = compute_metrics(data, upcoming_days=visual_settings.upcoming_days)
    dashboard_items = build_dashboard_items(metrics, settings=visual_settings)
    return {
        "settings": visual_settings,
        "data": data,
        "metrics": metrics,
        "dashboard_items": dashboard_items,
        "dashboard": [item.to_dict() for item in dashboard_items],
    }
