from __future__ import annotations

from copy import deepcopy
from datetime import date

from .analysis_definitions import AnalysisDefinition, FilterDefinition, MeasureDefinition, SortDefinition
from .analysis_settings import COMPLETED_STATUS_KEYS


def _measure(field: str = "", aggregation: str = "count_rows", alias: str = "value") -> list[MeasureDefinition]:
    return [MeasureDefinition(field=field, aggregation=aggregation, alias=alias)]


def _upcoming_deadline_filters(current: date, upcoming_days: int) -> list[FilterDefinition]:
    return [
        FilterDefinition("due_date", "greater_than_or_equal", current.isoformat()),
        FilterDefinition("due_date", "less_than_or_equal", date.fromordinal(current.toordinal() + max(1, int(upcoming_days))).isoformat()),
        FilterDefinition("status", "not_in", sorted(COMPLETED_STATUS_KEYS)),
    ]


def _past_deadline_filters(current: date) -> list[FilterDefinition]:
    return [
        FilterDefinition("due_date", "less_than", current.isoformat()),
        FilterDefinition("status", "not_in", sorted(COMPLETED_STATUS_KEYS)),
    ]


def build_builtin_analyses(today: date | None = None, upcoming_days: int = 60) -> dict[str, AnalysisDefinition]:
    current = today or date.today()
    return {
        "total_contracts": AnalysisDefinition(
            "total_contracts", "Toplam Sözleşme", "contracts", "kpi", measures=_measure(),
            options={"size": "small"},
        ),
        "total_platforms": AnalysisDefinition(
            "total_platforms", "Toplam Platform", "platforms", "kpi", measures=_measure(),
            options={"size": "small"},
        ),
        "platform_distribution": AnalysisDefinition(
            "platform_distribution", "Platform Dağılımı", "contracts", "horizontal_bar",
            dimensions=["platform_bucket"], measures=_measure(), sort=[SortDefinition("value", "desc")],
            options={"size": "large"},
        ),
        "contract_status_distribution": AnalysisDefinition(
            "contract_status_distribution", "Sözleşme Durum Dağılımı", "contracts", "bar",
            dimensions=["status_bucket"], measures=_measure(), sort=[SortDefinition("value", "desc")],
        ),
        "total_acceptances": AnalysisDefinition(
            "total_acceptances", "Toplam Teslimat", "acceptances", "kpi", measures=_measure(),
            options={"size": "small"},
        ),
        "acceptance_status_distribution": AnalysisDefinition(
            "acceptance_status_distribution", "Teslimat Durum Dağılımı", "acceptances", "donut",
            dimensions=["status_bucket"], measures=_measure(), sort=[SortDefinition("value", "desc")],
        ),
        "completed_acceptances": AnalysisDefinition(
            "completed_acceptances", "Tamamlanan Teslimat", "acceptances", "kpi",
            measures=_measure(alias="Tamamlanan Teslimat"),
            filters=[FilterDefinition("completed", "equals", True)],
            options={"size": "small"},
        ),
        "upcoming_deadline_count": AnalysisDefinition(
            "upcoming_deadline_count", "Yaklaşan Termin", "deadlines", "kpi",
            measures=_measure(),
            filters=_upcoming_deadline_filters(current, upcoming_days),
            options={"size": "small"},
        ),
        "past_deadline_count": AnalysisDefinition(
            "past_deadline_count", "Geçmiş Termin", "deadlines", "kpi",
            measures=_measure(),
            filters=_past_deadline_filters(current),
            options={"size": "small"},
        ),
        "upcoming_deadlines_table": AnalysisDefinition(
            "upcoming_deadlines_table", "Yaklaşan Termin Listesi", "deadlines", "table",
            select_fields=["platform", "contract_no", "entity", "name", "due_date", "days", "status"],
            filters=_upcoming_deadline_filters(current, upcoming_days),
            sort=[
                SortDefinition("due_date", "asc"),
                SortDefinition("platform", "asc"),
                SortDefinition("contract_no", "asc"),
            ],
            options={"size": "wide"},
        ),
    }


BUILTIN_ANALYSES = build_builtin_analyses()


def list_builtin_analyses(today: date | None = None, upcoming_days: int = 60) -> list[AnalysisDefinition]:
    return [deepcopy(item) for item in build_builtin_analyses(today, upcoming_days).values()]


def get_builtin_analysis(analysis_id: str, today: date | None = None, upcoming_days: int = 60) -> AnalysisDefinition:
    definitions = build_builtin_analyses(today, upcoming_days)
    try:
        return deepcopy(definitions[analysis_id])
    except KeyError as exc:
        raise KeyError(f"Bilinmeyen built-in analysis: {analysis_id}") from exc
