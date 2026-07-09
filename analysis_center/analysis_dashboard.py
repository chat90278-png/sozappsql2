from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from .analysis_cards import build_dashboard_items
from .analysis_builtin import list_builtin_analyses
from .analysis_engine import AnalysisEngine
from .analysis_renderer import analysis_result_to_card
from .analysis_data_loader import load_analysis_data
from .analysis_metrics import compute_metrics
from .analysis_models import AnalysisCard, VisualSettings
from .analysis_settings import DEFAULT_SETTINGS
from .analysis_utils import parse_date


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
    generic_results = {}
    generic_cards: dict[str, AnalysisCard] = {}
    dashboard_items = build_dashboard_items(
        metrics,
        settings=visual_settings,
        data=data,
        generic_results_out=generic_results,
        generic_cards_out=generic_cards,
    )
    engine = AnalysisEngine()
    today = parse_date(metrics.get("generated_at"))
    builtin_definitions = list_builtin_analyses(
        today=today,
        upcoming_days=visual_settings.upcoming_days,
    )
    for definition in builtin_definitions:
        if definition.analysis_id in generic_results:
            continue
        result = engine.execute(definition, data)
        generic_results[definition.analysis_id] = result
        generic_cards[definition.analysis_id] = analysis_result_to_card(definition, result)
    return {
        "settings": visual_settings,
        "data": data,
        "metrics": metrics,
        "dashboard_items": dashboard_items,
        "dashboard": [item.to_dict() for item in dashboard_items],
        "generic_analysis_results": {key: value.to_dict() for key, value in generic_results.items()},
        "generic_analysis_cards": {key: value.to_dict() for key, value in generic_cards.items()},
    }
