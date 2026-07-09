from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .analysis_models import AnalysisCard, CardType


def card_to_widget_payload(card: AnalysisCard) -> Dict[str, Any]:
    """UI katmanının kullanabileceği sade, PySide bağımsız payload üretir."""

    payload = card.to_dict()
    if card.card_type == CardType.KPI:
        payload["render_hint"] = "kpi_card"
    elif card.card_type == CardType.CHART:
        payload["render_hint"] = "chart_card"
        payload["series"] = chart_series(card.data)
    elif card.card_type == CardType.TABLE:
        payload["render_hint"] = "table_card"
        payload["rows"] = table_rows(card.data, card.columns)
    elif card.card_type == CardType.LIST:
        payload["render_hint"] = "list_card"
    else:
        payload["render_hint"] = "status_card"
    return payload


def cards_to_widget_payload(cards: Iterable[AnalysisCard]) -> List[Dict[str, Any]]:
    return [card_to_widget_payload(card) for card in cards]


def chart_series(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, Mapping):
        return [{"label": str(key), "value": value} for key, value in data.items()]
    out: List[Dict[str, Any]] = []
    for item in list(data or []):
        if isinstance(item, Mapping):
            label = item.get("label") or item.get("name") or item.get("platform") or item.get("status") or ""
            value = item.get("value")
            if value is None:
                value = item.get("count") or item.get("contract_count") or 0
            out.append({"label": str(label), "value": value})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append({"label": str(item[0]), "value": item[1]})
    return out


def table_rows(data: Any, columns: Iterable[str]) -> List[Dict[str, Any]]:
    cols = list(columns or [])
    rows: List[Dict[str, Any]] = []
    for item in list(data or []):
        if isinstance(item, Mapping):
            rows.append({col: item.get(col, "") for col in cols})
        elif isinstance(item, (list, tuple)):
            rows.append({col: item[idx] if idx < len(item) else "" for idx, col in enumerate(cols)})
        else:
            rows.append({cols[0] if cols else "value": item})
    return rows
