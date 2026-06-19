from __future__ import annotations

from typing import Any, Dict, List

from .analysis_models import AnalysisCard, AnalysisEntity, CardSize, CardType, ChartType, DashboardItem, VisualSettings
from .analysis_settings import DEFAULT_SETTINGS, PHASE_2_SCREEN_IDS


def _limit(rows, settings: VisualSettings):
    return list(rows or [])[: settings.max_table_rows]


def _kpi(card_id: str, title: str, value: Any, entity: AnalysisEntity, screen_id: str, order: int, unit: str = "") -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.KPI, size=CardSize.SMALL, value=value, unit=unit, screen_id=screen_id, sort_order=order)


def _chart(card_id: str, title: str, data: Any, entity: AnalysisEntity, chart_type: ChartType, screen_id: str, order: int, size: CardSize = CardSize.MEDIUM) -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.CHART, chart_type=chart_type, size=size, data=data, screen_id=screen_id, sort_order=order)


def _table(card_id: str, title: str, columns: List[str], data: Any, entity: AnalysisEntity, screen_id: str, order: int, size: CardSize = CardSize.WIDE) -> AnalysisCard:
    return AnalysisCard(card_id=card_id, title=title, entity=entity, card_type=CardType.TABLE, size=size, columns=columns, data=data, screen_id=screen_id, sort_order=order)


def build_dashboard_items(metrics: Dict[str, Any], settings: VisualSettings | None = None) -> List[DashboardItem]:
    settings = (settings or DEFAULT_SETTINGS).normalized()
    items = [_executive_summary(metrics, settings), _platform_analysis(metrics, settings), _contract_analysis(metrics, settings), _acceptance_analysis(metrics, settings), _deadline_analysis(metrics, settings), _mini_data_health(metrics, settings)]
    if settings.show_disabled_sections:
        items.extend(_phase_2_items())
    return sorted(items, key=lambda item: item.sort_order)


def _executive_summary(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
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


def _platform_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
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
        _table("contract_unlabeled_table", "Etiketsiz Kayıtlar", ["platform", "contract_no", "contract_type", "status"], _limit(metrics.get("unlabeled_contracts", []), settings), AnalysisEntity.TAG, screen, 60),
    ]
    return DashboardItem(screen, "Sözleşme Analizi", cards=cards, enabled=True, sort_order=30)


def _acceptance_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "acceptance_analysis"
    cards = [
        _kpi("acceptance_total", "Toplam Teslimat", metrics.get("total_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 10),
        _kpi("acceptance_completed", "Tamamlanan Teslimat", metrics.get("completed_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 20),
        _kpi("acceptance_open", "Açık Teslimat", metrics.get("open_acceptances", 0), AnalysisEntity.ACCEPTANCE, screen, 30),
        _chart("acceptance_status_distribution", "Teslimat Durum Dağılımı", metrics.get("acceptance_status_distribution", []), AnalysisEntity.ACCEPTANCE, ChartType.DONUT, screen, 40),
        _table("acceptance_table", "Teslimat Tablosu", ["platform", "contract_no", "system_name", "name", "status", "acceptance_date", "planned_total", "delivered_total", "completed"], _limit(metrics.get("acceptance_table", []), settings), AnalysisEntity.ACCEPTANCE, screen, 50),
    ]
    return DashboardItem(screen, "Teslimat Analizi", cards=cards, enabled=True, sort_order=40)


def _deadline_analysis(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "deadline_analysis"
    cards = [
        _kpi("deadline_upcoming_count", "Yaklaşan Termin", metrics.get("upcoming_deadline_count", 0), AnalysisEntity.DEADLINE, screen, 10),
        _kpi("deadline_past_count", "Geçmiş Termin", metrics.get("past_deadline_count", 0), AnalysisEntity.DEADLINE, screen, 20),
        _table("deadline_upcoming_table", "Yaklaşan Terminler", ["platform", "contract_no", "entity", "name", "due_date", "days", "status"], _limit(metrics.get("upcoming_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 30),
        _table("deadline_past_table", "Geçmiş Terminler", ["platform", "contract_no", "entity", "name", "due_date", "days", "status"], _limit(metrics.get("past_deadlines", []), settings), AnalysisEntity.DEADLINE, screen, 40),
    ]
    return DashboardItem(screen, "Termin Analizi", cards=cards, enabled=True, sort_order=50)


def _mini_data_health(metrics: Dict[str, Any], settings: VisualSettings) -> DashboardItem:
    screen = "mini_data_health"
    cards = [
        _kpi("health_missing_info", "Eksik Bilgi", metrics.get("missing_info_count", 0), AnalysisEntity.HEALTH, screen, 10),
        _kpi("health_unlabeled", "Etiketsiz Kayıt", metrics.get("unlabeled_contract_count", 0), AnalysisEntity.TAG, screen, 20),
        _table("health_items_table", "Mini Veri Sağlığı Listesi", ["entity", "platform", "contract_no", "field", "label"], _limit(metrics.get("missing_info_items", []), settings), AnalysisEntity.HEALTH, screen, 30),
    ]
    return DashboardItem(screen, "Mini Veri Sağlığı", cards=cards, enabled=True, sort_order=60)


def _phase_2_items() -> List[DashboardItem]:
    titles = {"system_analysis": "Sistem", "component_analysis": "Bileşen", "tag_analysis": "Etiket", "user_analysis": "Kullanıcı", "detailed_data_health": "Detaylı Veri Sağlığı"}
    return [DashboardItem(item_id=item_id, title=titles.get(item_id, item_id), cards=[], enabled=False, sort_order=100 + idx, description="Faz 2", meta={"phase": 2}) for idx, item_id in enumerate(sorted(PHASE_2_SCREEN_IDS), start=1)]
