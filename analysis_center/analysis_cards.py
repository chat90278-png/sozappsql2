from __future__ import annotations

import logging
from copy import deepcopy
from datetime import date
from typing import Any, Dict, List

from .analysis_builtin import get_builtin_analysis
from .analysis_dashboard_service import DashboardCompositionError
from .analysis_definitions import AnalysisDefinition, AnalysisResult, AnalysisValidationError, DashboardDefinition
from .analysis_models import AnalysisCard, AnalysisEntity, CardSize, CardType, ChartType, DashboardItem, NormalizedAnalysisData, VisualSettings
from .analysis_repository import MemoryAnalysisRepository
from .analysis_service import AnalysisService
from .analysis_settings import DEFAULT_SETTINGS, PHASE_2_SCREEN_IDS
from .analysis_utils import parse_date


logger = logging.getLogger(__name__)


_EXECUTIVE_SUMMARY_GENERIC_DASHBOARD = DashboardDefinition(
    dashboard_id="executive_summary_generic",
    title="Yönetici Özeti",
    analysis_ids=[
        "total_contracts",
        "upcoming_deadline_count",
        "past_deadline_count",
        "completed_acceptances",
        "contract_status_distribution",
        "upcoming_deadlines_table",
    ],
)

_EXECUTIVE_SUMMARY_GENERIC_CARD_COMPAT = {
    "total_contracts": {
        "card_id": "exec_total_contracts",
        "title": "Toplam Sözleşme",
        "size": CardSize.SMALL,
        "sort_order": 10,
    },
    "upcoming_deadline_count": {
        "card_id": "exec_upcoming_deadlines",
        "title": "Yaklaşan Termin",
        "size": CardSize.SMALL,
        "sort_order": 20,
    },
    "past_deadline_count": {
        "card_id": "exec_past_deadlines",
        "title": "Geçmiş Termin",
        "size": CardSize.SMALL,
        "sort_order": 30,
    },
    "completed_acceptances": {
        "card_id": "exec_completed_acceptances",
        "title": "Tamamlanan Teslimat",
        "size": CardSize.SMALL,
        "sort_order": 40,
    },
    "contract_status_distribution": {
        "card_id": "exec_status_distribution",
        "title": "Durum Dağılımı",
        "size": CardSize.MEDIUM,
        "sort_order": 50,
        "chart_type": ChartType.DONUT,
    },
    "upcoming_deadlines_table": {
        "card_id": "exec_upcoming_table",
        "title": "Yaklaşan Termin Listesi",
        "size": CardSize.WIDE,
        "sort_order": 60,
    },
}


_PLATFORM_ANALYSIS_GENERIC_DASHBOARD = DashboardDefinition(
    dashboard_id="platform_analysis_generic",
    title="Platform Analizi",
    analysis_ids=[
        "total_platforms",
        "platform_distribution",
    ],
)

_PLATFORM_ANALYSIS_GENERIC_CARD_COMPAT = {
    "total_platforms": {
        "card_id": "platform_total",
        "title": "Platform Sayısı",
        "size": CardSize.SMALL,
        "sort_order": 10,
    },
    "platform_distribution": {
        "card_id": "platform_distribution",
        "title": "Platform Dağılımı",
        "size": CardSize.LARGE,
        "sort_order": 20,
        "chart_type": ChartType.HORIZONTAL_BAR,
    },
}


def _prepared_builtin_card_catalog() -> dict[tuple[str, str], str]:
    catalog: dict[tuple[str, str], str] = {}
    for screen_id, compatibility in (
        ("executive_summary", _EXECUTIVE_SUMMARY_GENERIC_CARD_COMPAT),
        ("platform_analysis", _PLATFORM_ANALYSIS_GENERIC_CARD_COMPAT),
    ):
        for analysis_id, metadata in compatibility.items():
            key = (screen_id, str(metadata["card_id"]))
            if key in catalog:
                raise RuntimeError(f"Duplicate prepared card template mapping: {key!r}")
            catalog[key] = analysis_id
    return catalog


_PREPARED_BUILTIN_CARD_CATALOG = _prepared_builtin_card_catalog()


def get_builtin_analysis_id_for_prepared_card(screen_id: str, card_id: str) -> str | None:
    """Return the builtin analysis id explicitly backing a prepared card identity."""

    key = (str(screen_id or "").strip(), str(card_id or "").strip())
    return _PREPARED_BUILTIN_CARD_CATALOG.get(key)


def get_builtin_analysis_for_prepared_card(
    card: AnalysisCard,
    *,
    today: date | None = None,
    upcoming_days: int = 60,
) -> AnalysisDefinition | None:
    """Resolve a prepared card to its real builtin definition when it is truly backed by one.

    Legacy fallback cards intentionally return ``None`` even if they reuse a compatible
    visible card id. The generic renderer marks real builtin-backed cards with
    ``meta["analysis_id"]`` and that marker must match the central identity catalog.
    """

    analysis_id = get_builtin_analysis_id_for_prepared_card(card.screen_id, card.card_id)
    if analysis_id is None:
        return None
    backing_analysis_id = str(card.meta.get("analysis_id") or "").strip()
    if backing_analysis_id != analysis_id:
        return None
    return get_builtin_analysis(
        analysis_id,
        today=today,
        upcoming_days=upcoming_days,
    )


def _limit(rows, settings: VisualSettings):
    return list(rows or [])[: settings.max_table_rows]


def _kpi(card_id: str, title: str, value: Any, entity: AnalysisEntity, screen_id: str, order: int, unit: str = "") -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.KPI, size=CardSize.SMALL, value=value, unit=unit, screen_id=screen_id, sort_order=order)


def _chart(card_id: str, title: str, data: Any, entity: AnalysisEntity, chart_type: ChartType, screen_id: str, order: int, size: CardSize = CardSize.MEDIUM) -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.CHART, chart_type=chart_type, size=size, data=data, screen_id=screen_id, sort_order=order)


def _table(card_id: str, title: str, columns: List[str], data: Any, entity: AnalysisEntity, screen_id: str, order: int, size: CardSize = CardSize.WIDE) -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.TABLE, size=size, columns=columns, data=data, screen_id=screen_id, sort_order=order)


def build_dashboard_items(
    metrics: Dict[str, Any],
    settings: VisualSettings | None = None,
    data: NormalizedAnalysisData | None = None,
    *,
    generic_results_out: dict[str, AnalysisResult] | None = None,
    generic_cards_out: dict[str, AnalysisCard] | None = None,
) -> List[DashboardItem]:
    settings = (settings or DEFAULT_SETTINGS).normalized()
    items = [
        _executive_summary(
            metrics,
            settings,
            data,
            generic_results_out=generic_results_out,
            generic_cards_out=generic_cards_out,
        ),
        _platform_analysis(
            metrics,
            settings,
            data,
            generic_results_out=generic_results_out,
            generic_cards_out=generic_cards_out,
        ),
        _contract_analysis(metrics, settings),
        _acceptance_analysis(metrics, settings),
        _deadline_analysis(metrics, settings),
    ]
    if settings.show_disabled_sections:
        items.extend(_phase_2_items())
    return sorted(items, key=lambda item: item.sort_order)


def _executive_summary(
    metrics: Dict[str, Any],
    settings: VisualSettings,
    data: NormalizedAnalysisData | None = None,
    *,
    generic_results_out: dict[str, AnalysisResult] | None = None,
    generic_cards_out: dict[str, AnalysisCard] | None = None,
) -> DashboardItem:
    if data is None:
        return _legacy_executive_summary(metrics, settings)
    try:
        return _hybrid_executive_summary(
            metrics,
            settings,
            data,
            generic_results_out=generic_results_out,
            generic_cards_out=generic_cards_out,
        )
    except (DashboardCompositionError, AnalysisValidationError) as exc:
        logger.warning(
            "Yönetici Özeti generic composition başarısız; legacy fallback kullanılacak: %s",
            exc,
        )
        return _legacy_executive_summary(metrics, settings)


def _hybrid_executive_summary(
    metrics: Dict[str, Any],
    settings: VisualSettings,
    data: NormalizedAnalysisData,
    *,
    generic_results_out: dict[str, AnalysisResult] | None = None,
    generic_cards_out: dict[str, AnalysisCard] | None = None,
) -> DashboardItem:
    screen = "executive_summary"
    today = parse_date(metrics.get("generated_at"))
    repository = MemoryAnalysisRepository()
    table_definition = get_builtin_analysis(
        "upcoming_deadlines_table",
        today=today,
        upcoming_days=settings.upcoming_days,
    )
    table_definition.limit = settings.max_table_rows
    repository.save_analysis(table_definition)
    service = AnalysisService(use_sample=False, repository=repository)
    service.data = _executive_composition_data(data, metrics)
    composition = service.compose_dashboard(
        _EXECUTIVE_SUMMARY_GENERIC_DASHBOARD,
        today=today,
        upcoming_days=settings.upcoming_days,
    )
    if composition.warnings or composition.errors:
        raise DashboardCompositionError(
            "Executive summary generic subset composition incomplete: "
            f"warnings={composition.warnings!r}, errors={composition.errors!r}"
        )

    analysis_sources = composition.meta.get("analysis_sources", {})
    if generic_results_out is not None:
        generic_results_out.update({
            result.analysis_id: deepcopy(result)
            for result in composition.analysis_results
            if analysis_sources.get(result.analysis_id) == "builtin"
        })
    if generic_cards_out is not None:
        generic_cards_out.update({
            analysis_id: deepcopy(card)
            for card in composition.cards
            if (analysis_id := str(card.meta.get("analysis_id") or card.card_id))
            and analysis_sources.get(analysis_id) == "builtin"
        })

    generic_cards = [_adapt_executive_generic_card(deepcopy(card)) for card in composition.cards]
    expected_ids = set(_EXECUTIVE_SUMMARY_GENERIC_CARD_COMPAT)
    actual_ids = {str(card.meta.get("analysis_id") or "") for card in generic_cards}
    if actual_ids != expected_ids or len(generic_cards) != len(expected_ids):
        raise DashboardCompositionError(
            "Executive summary generic subset card set mismatch: "
            f"expected={sorted(expected_ids)!r}, actual={sorted(actual_ids)!r}"
        )

    cards = sorted(generic_cards, key=lambda card: card.sort_order)
    return DashboardItem(screen, "Yönetici Özeti", cards=cards, enabled=True, sort_order=10)


def _executive_composition_data(
    data: NormalizedAnalysisData,
    metrics: Dict[str, Any],
) -> NormalizedAnalysisData:
    composition_data: NormalizedAnalysisData = {
        key: [dict(row) for row in list(rows or [])]
        for key, rows in data.items()
    }
    all_deadlines = metrics.get("all_deadlines")
    if isinstance(all_deadlines, list):
        composition_data["deadlines"] = [dict(row) for row in all_deadlines]
    return composition_data


def _adapt_executive_generic_card(card: AnalysisCard) -> AnalysisCard:
    analysis_id = str(card.meta.get("analysis_id") or card.card_id)
    try:
        compat = _EXECUTIVE_SUMMARY_GENERIC_CARD_COMPAT[analysis_id]
    except KeyError as exc:
        raise DashboardCompositionError(
            f"Unexpected executive summary generic analysis card: {analysis_id}"
        ) from exc
    card.card_id = str(compat["card_id"])
    card.title = str(compat["title"])
    card.size = compat["size"]
    card.screen_id = "executive_summary"
    card.sort_order = int(compat["sort_order"])
    if "chart_type" in compat:
        card.chart_type = compat["chart_type"]
    return card


def _legacy_executive_summary(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "executive_summary"
    cards = [
        _kpi("exec_total_contracts", "Toplam Sözleşme", metrics.get("total_contracts", 0), AnalysisEntity.CONTRACT, screen, 10),
        _kpi("exec_upcoming_deadlines", "Yaklaşan Termin", metrics.get("upcoming_deadline_count", 0), AnalysisEntity.DEADLINE, screen, 20),
        _kpi("exec_past_deadlines", "Geçmiş Termin", metrics.get("past_deadline_count", 0), AnalysisEntity.DEADLINE, screen, 30),
        _kpi("exec_completed_acceptances", "Tamamlanan Teslimat", metrics.get("completed_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 40),
        _chart("exec_status_distribution", "Durum Dağılımı", metrics.get("status_distribution", []), AnalysisEntity.CONTRACT, ChartType.DONUT, screen, 50),
        _table("exec_upcoming_table", "Yaklaşan Termin Listesi", ["platform", "contract_no", "entity", "name", "due_date", "days", "status"], _limit(metrics.get("upcoming_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 60),
    ]
    return DashboardItem(screen, "Yönetici Özeti", cards=cards, enabled=True, sort_order=10)


def _platform_analysis(
    metrics: Dict[str, Any],
    settings: VisualSettings,
    data: NormalizedAnalysisData | None = None,
    *,
    generic_results_out: dict[str, AnalysisResult] | None = None,
    generic_cards_out: dict[str, AnalysisCard] | None = None,
) -> DashboardItem:
    if data is None:
        return _legacy_platform_analysis(metrics, settings)
    try:
        return _hybrid_platform_analysis(
            metrics,
            settings,
            data,
            generic_results_out=generic_results_out,
            generic_cards_out=generic_cards_out,
        )
    except (DashboardCompositionError, AnalysisValidationError) as exc:
        logger.warning(
            "Platform Analizi generic composition başarısız; legacy fallback kullanılacak: %s",
            exc,
        )
        return _legacy_platform_analysis(metrics, settings)


def _hybrid_platform_analysis(
    metrics: Dict[str, Any],
    settings: VisualSettings,
    data: NormalizedAnalysisData,
    *,
    generic_results_out: dict[str, AnalysisResult] | None = None,
    generic_cards_out: dict[str, AnalysisCard] | None = None,
) -> DashboardItem:
    screen = "platform_analysis"
    today = parse_date(metrics.get("generated_at"))
    service = AnalysisService(use_sample=False, repository=MemoryAnalysisRepository())
    service.data = data
    composition = service.compose_dashboard(
        _PLATFORM_ANALYSIS_GENERIC_DASHBOARD,
        today=today,
        upcoming_days=settings.upcoming_days,
    )
    if composition.warnings or composition.errors:
        raise DashboardCompositionError(
            "Platform analysis generic subset composition incomplete: "
            f"warnings={composition.warnings!r}, errors={composition.errors!r}"
        )

    generic_cards = [_adapt_platform_generic_card(deepcopy(card)) for card in composition.cards]
    expected_ids = set(_PLATFORM_ANALYSIS_GENERIC_CARD_COMPAT)
    actual_ids = {str(card.meta.get("analysis_id") or "") for card in generic_cards}
    if actual_ids != expected_ids or len(generic_cards) != len(expected_ids):
        raise DashboardCompositionError(
            "Platform analysis generic subset card set mismatch: "
            f"expected={sorted(expected_ids)!r}, actual={sorted(actual_ids)!r}"
        )

    analysis_sources = composition.meta.get("analysis_sources", {})
    if generic_results_out is not None:
        generic_results_out.update({
            result.analysis_id: deepcopy(result)
            for result in composition.analysis_results
            if analysis_sources.get(result.analysis_id) == "builtin"
        })
    if generic_cards_out is not None:
        generic_cards_out.update({
            analysis_id: deepcopy(card)
            for card in composition.cards
            if (analysis_id := str(card.meta.get("analysis_id") or card.card_id))
            and analysis_sources.get(analysis_id) == "builtin"
        })

    legacy_table = _table(
        "platform_table",
        "Platform Tablosu",
        ["platform", "contract_count", "completed_contract_count", "acceptance_count", "completed_acceptance_count"],
        _limit(metrics.get("platform_table", []), settings),
        AnalysisEntity.PLATFORM,
        screen,
        30,
    )
    cards = sorted([*generic_cards, legacy_table], key=lambda card: card.sort_order)
    return DashboardItem(screen, "Platform Analizi", cards=cards, enabled=True, sort_order=20)


def _adapt_platform_generic_card(card: AnalysisCard) -> AnalysisCard:
    analysis_id = str(card.meta.get("analysis_id") or card.card_id)
    try:
        compat = _PLATFORM_ANALYSIS_GENERIC_CARD_COMPAT[analysis_id]
    except KeyError as exc:
        raise DashboardCompositionError(
            f"Unexpected platform analysis generic analysis card: {analysis_id}"
        ) from exc
    card.card_id = str(compat["card_id"])
    card.title = str(compat["title"])
    card.size = compat["size"]
    card.screen_id = "platform_analysis"
    card.sort_order = int(compat["sort_order"])
    if "chart_type" in compat:
        card.chart_type = compat["chart_type"]
    return card


def _legacy_platform_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "platform_analysis"
    cards = [
        _kpi("platform_total", "Platform Sayısı", metrics.get("total_platforms", 0), AnalysisEntity.PLATFORM, screen, 10),
        _chart("platform_distribution", "Platform Dağılımı", metrics.get("platform_distribution", []), AnalysisEntity.PLATFORM, ChartType.HORIZONTAL_BAR, screen, 20, CardSize.LARGE),
        _table("platform_table", "Platform Tablosu", ["platform", "contract_count", "completed_contract_count", "acceptance_count", "completed_acceptance_count"], _limit(metrics.get("platform_table", []), settings), AnalysisEntity.PLATFORM, screen, 30),
    ]
    return DashboardItem(screen, "Platform Analizi", cards=cards, enabled=True, sort_order=20)


def _contract_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "contract_analysis"
    cards = [
        _kpi("contract_total", "Toplam Sözleşme", metrics.get("total_contracts", 0), AnalysisEntity.CONTRACT, screen, 10),
        _kpi("contract_completed", "Tamamlanan", metrics.get("completed_contract_count", 0), AnalysisEntity.CONTRACT, screen, 20),
        _kpi("contract_not_started", "Başlanmadı", metrics.get("not_started_contract_count", 0), AnalysisEntity.CONTRACT, screen, 30),
        _kpi("contract_in_progress", "Devam Ediyor", metrics.get("in_progress_contract_count", 0), AnalysisEntity.CONTRACT, screen, 40),
        _chart("contract_status_distribution", "Sözleşme Durum Dağılımı", metrics.get("status_distribution", []), AnalysisEntity.CONTRACT, ChartType.BAR, screen, 50),
    ]
    return DashboardItem(screen, "Sözleşme Analizi", cards=cards, enabled=True, sort_order=30)


def _acceptance_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "acceptance_analysis"
    cards = [
        _kpi("acceptance_total", "Toplam Teslimat", metrics.get("total_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 10),
        _kpi("acceptance_completed", "Tamamlanan Teslimat", metrics.get("completed_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 20),
        _kpi("acceptance_open", "Açık Teslimat", metrics.get("open_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 30),
        _chart("acceptance_status_distribution", "Teslimat Durum Dağılımı", metrics.get("acceptance_status_distribution", []), AnalysisEntity.ACCEPTANCE, ChartType.DONUT, screen, 40),
        _table("acceptance_table", "Teslimat Tablosu", ["platform", "contract_no", "system_name", "name", "status", "planned_acceptance_date", "acceptance_date", "planned_total", "delivered_total", "completed"], _limit(metrics.get("acceptance_table", []), settings), AnalysisEntity.ACCEPTANCE, screen, 50),
    ]
    return DashboardItem(screen, "Teslimat Analizi", cards=cards, enabled=True, sort_order=40)


def _deadline_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "deadline_analysis"
    upcoming_count = int(metrics.get("upcoming_deadline_count", 0) or 0)
    past_count = int(metrics.get("past_deadline_count", 0) or 0)
    unknown_count = int(metrics.get("unknown_deadline_count", 0) or 0)
    if upcoming_count == 0 and past_count == 0 and unknown_count == 0:
        description = "Bu STS dosyasında analiz edilebilir aktif termin kaydı bulunamadı."
    elif upcoming_count == 0 and past_count == 0 and unknown_count > 0:
        description = "Tarihi belirlenmemiş termin kayıtları bulundu."
    else:
        description = ""
    cards = [
        _kpi("deadline_upcoming_count", "Yaklaşan Termin", upcoming_count, AnalysisEntity.DEADLINE, screen, 10),
        _kpi("deadline_past_count", "Geçmiş Termin", past_count, AnalysisEntity.DEADLINE, screen, 20),
        _kpi("deadline_unknown_count", "Tarihi Belirsiz", unknown_count, AnalysisEntity.DEADLINE, screen, 30),
        _table("deadline_upcoming_table", "Yaklaşan Terminler", ["platform", "contract_no", "entity", "name", "due_date", "days", "status"], _limit(metrics.get("upcoming_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 40),
        _table("deadline_past_table", "Geçmiş Terminler", ["platform", "contract_no", "entity", "name", "due_date", "days", "status"], _limit(metrics.get("past_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 50),
        _table("deadline_unknown_table", "Tarihi Belirsiz Terminler", ["entity", "name", "platform", "contract_no", "date_field", "raw_date_value", "status"], _limit(metrics.get("unknown_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 60),
    ]
    return DashboardItem(screen, "Termin Analizi", cards=cards, enabled=True, sort_order=50, description=description)


def _phase_2_items() -> List[DashboardItem]:
    titles = {"system_analysis": "Sistem", "component_analysis": "Bileşen", "tag_analysis": "Etiket", "user_analysis": "Kullanıcı"}
    return [DashboardItem(item_id=item_id, title=titles.get(item_id, item_id), cards=[], enabled=False, sort_order=100 + idx, description="Faz 2", meta={"phase": 2}) for idx, item_id in enumerate(sorted(PHASE_2_SCREEN_IDS), start=1)]
