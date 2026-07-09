from __future__ import annotations

from dataclasses import dataclass

from .analysis_builder import AGGREGATION_TITLES, BUILDER_VISUALIZATIONS
from .analysis_definitions import AnalysisDefinition, AnalysisResult, AnalysisValidationError
from .analysis_service import AnalysisService


MY_ANALYSES_ID = "my_analyses"

_VISUALIZATION_TITLES = {
    option.visualization_id: option.title for option in BUILDER_VISUALIZATIONS
}


@dataclass(frozen=True, slots=True)
class SavedAnalysisListItem:
    analysis_id: str
    title: str
    dataset_title: str
    visualization_title: str
    summary: str
    validation_error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.validation_error is None


class CustomAnalysisLibraryController:
    """Presentation-oriented facade over saved-analysis CRUD and execution."""

    def __init__(self, service: AnalysisService):
        self.service = service
        self.registry = service.registry

    def list_items(self) -> list[SavedAnalysisListItem]:
        return [self._list_item(definition) for definition in self.service.list_saved_analyses()]

    def get_definition(self, analysis_id: str) -> AnalysisDefinition:
        definition = self.service.get_saved_analysis(analysis_id)
        if definition is None:
            raise AnalysisValidationError("Analiz bulunamadı.")
        return definition

    def preview(self, analysis_id: str) -> tuple[AnalysisDefinition, AnalysisResult]:
        definition = self.get_definition(analysis_id)
        self.service.validate_analysis(definition)
        return definition, self.service.execute_analysis(definition)

    def copy(self, analysis_id: str) -> AnalysisDefinition:
        return self.service.copy_saved_analysis(analysis_id)

    def delete(self, analysis_id: str) -> bool:
        return self.service.delete_saved_analysis(analysis_id)

    def load_issues_count(self) -> int:
        return len(self.service.repository_load_issues())

    def load_error(self) -> Exception | None:
        return self.service.repository_load_error()

    def _list_item(self, definition: AnalysisDefinition) -> SavedAnalysisListItem:
        validation_error = self.service.saved_analysis_validation_error(definition)
        return SavedAnalysisListItem(
            analysis_id=definition.analysis_id,
            title=definition.title,
            dataset_title=self._dataset_title(definition.dataset),
            visualization_title=_VISUALIZATION_TITLES.get(
                definition.visualization,
                "Desteklenmeyen Görünüm",
            ),
            summary=self._summary(definition),
            validation_error=validation_error,
        )

    def _dataset_title(self, dataset_id: str) -> str:
        try:
            return self.registry.get_dataset(dataset_id).title
        except AnalysisValidationError:
            return "Bilinmeyen Veri Kaynağı"

    def _field_title(self, dataset_id: str, field_id: str) -> str:
        try:
            return self.registry.get_field(dataset_id, field_id).title
        except AnalysisValidationError:
            return "Bilinmeyen Alan"

    def _summary(self, definition: AnalysisDefinition) -> str:
        if definition.visualization == "table":
            return f"{len(definition.select_fields)} alan • {len(definition.filters)} filtre"
        if not definition.measures:
            return "Hesaplama bilgisi bulunamadı"
        measure = definition.measures[0]
        aggregation = AGGREGATION_TITLES.get(measure.aggregation, measure.aggregation)
        measure_title = (
            "Kayıt Sayısı"
            if measure.aggregation == "count_rows"
            else f"{self._field_title(definition.dataset, measure.field)} • {aggregation}"
        )
        if definition.visualization == "kpi":
            return measure_title
        group_title = (
            self._field_title(definition.dataset, definition.dimensions[0])
            if definition.dimensions
            else "Gruplama yok"
        )
        return f"{group_title} göre • {measure_title}"


__all__ = [
    "MY_ANALYSES_ID",
    "CustomAnalysisLibraryController",
    "SavedAnalysisListItem",
]
