from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from .analysis_definitions import (
    AnalysisDefinition,
    AnalysisValidationError,
    FilterDefinition,
    MeasureDefinition,
    SortDefinition,
)
from .analysis_registry import AnalysisRegistry, DatasetDefinition, FieldDefinition
from .analysis_service import AnalysisService
from .analysis_visual_settings import AnalysisVisualSettings, has_visual_settings
from .analysis_utils import normalize_text, parse_date, parse_datetime


ANALYSIS_BUILDER_ID = "analysis_builder"


@dataclass(frozen=True, slots=True)
class BuilderVisualizationOption:
    visualization_id: str
    title: str
    mode: str


BUILDER_VISUALIZATIONS: tuple[BuilderVisualizationOption, ...] = (
    BuilderVisualizationOption("kpi", "KPI", "aggregation"),
    BuilderVisualizationOption("bar", "Dikey Çubuk", "aggregation"),
    BuilderVisualizationOption("horizontal_bar", "Yatay Çubuk", "aggregation"),
    BuilderVisualizationOption("donut", "Donut", "aggregation"),
    BuilderVisualizationOption("line", "Çizgi", "aggregation"),
    BuilderVisualizationOption("table", "Tablo", "projection"),
)

AGGREGATION_TITLES: dict[str, str] = {
    "count_rows": "Kayıt Sayısı",
    "count": "Dolu Değer Sayısı",
    "count_distinct": "Benzersiz Değer Sayısı",
    "sum": "Toplam",
    "avg": "Ortalama",
    "min": "En Küçük",
    "max": "En Büyük",
}

FILTER_OPERATOR_TITLES: dict[str, str] = {
    "equals": "Eşittir",
    "not_equals": "Eşit Değil",
    "contains": "İçerir",
    "not_contains": "İçermez",
    "greater_than": "Büyüktür",
    "greater_than_or_equal": "Büyük veya Eşit",
    "less_than": "Küçüktür",
    "less_than_or_equal": "Küçük veya Eşit",
    "between": "Arasında",
    "is_empty": "Boş",
    "is_not_empty": "Boş Değil",
    "in": "Listede",
    "not_in": "Listede Değil",
}

SORT_DIRECTION_TITLES: dict[str, str] = {
    "asc": "Artan",
    "desc": "Azalan",
}

_NO_VALUE_FILTERS = frozenset({"is_empty", "is_not_empty"})
_LIST_FILTERS = frozenset({"in", "not_in"})
_COUNT_LIKE_AGGREGATIONS = frozenset({"count_rows", "count", "count_distinct"})


def _has_explicit_kpi_decimal(options: Mapping[str, Any] | None) -> bool:
    visual = (options or {}).get("visual_settings")
    if not isinstance(visual, Mapping):
        return False
    kpi = visual.get("kpi")
    if not isinstance(kpi, Mapping):
        return False
    marker = kpi.get("decimal_places_explicit")
    if isinstance(marker, bool):
        return marker
    # Tur 16 did not persist explicitness. Non-default values are the safest legacy signal.
    try:
        return int(kpi.get("decimal_places", 2)) != 2
    except (TypeError, ValueError):
        return False


def _new_preview_id() -> str:
    return f"preview-{uuid4().hex[:12]}"


def _raw_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def builder_filter_draft_from_definition(definition: FilterDefinition) -> "BuilderFilterDraft":
    if definition.operator in _NO_VALUE_FILTERS:
        raw_value = ""
        raw_value_to = ""
    elif definition.operator == "between":
        values = list(definition.value or [])
        if len(values) != 2:
            raise AnalysisValidationError("Arasında filtresi iki değer taşımalıdır.")
        raw_value = _raw_scalar(values[0])
        raw_value_to = _raw_scalar(values[1])
    elif definition.operator in _LIST_FILTERS:
        if not isinstance(definition.value, (list, tuple, set)):
            raise AnalysisValidationError("Liste filtresi liste değeri taşımalıdır.")
        raw_value = ", ".join(_raw_scalar(item) for item in definition.value)
        raw_value_to = ""
    else:
        raw_value = _raw_scalar(definition.value)
        raw_value_to = ""
    return BuilderFilterDraft(
        field_id=definition.field,
        operator=definition.operator,
        raw_value=raw_value,
        raw_value_to=raw_value_to,
    )


@dataclass(slots=True)
class BuilderFilterDraft:
    field_id: str = ""
    operator: str = ""
    raw_value: str = ""
    raw_value_to: str = ""


@dataclass(slots=True)
class CustomAnalysisDraft:
    analysis_id: str = field(default_factory=_new_preview_id)
    title: str = "Yeni Analiz"
    dataset_id: str = ""
    visualization: str = "horizontal_bar"
    group_field: str = ""
    aggregation: str = "count_rows"
    measure_field: str = ""
    filters: list[BuilderFilterDraft] = field(default_factory=list)
    sort_field: str = ""
    sort_direction: str = "desc"
    limit: int | None = 20
    selected_table_fields: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    visual_settings: AnalysisVisualSettings = field(default_factory=AnalysisVisualSettings)
    visual_settings_explicit: bool = True
    kpi_decimal_explicit: bool = False


class AnalysisBuilderController:
    """Registry-driven custom-analysis draft and persistence lifecycle controller."""

    def __init__(self, service: AnalysisService, draft: CustomAnalysisDraft | None = None):
        self.service = service
        self.registry: AnalysisRegistry = service.registry
        capabilities = service.capabilities()
        self._row_aggregations = tuple(str(item) for item in capabilities.get("row_aggregations", []))
        self._visualization_lookup = {
            item.visualization_id: item for item in BUILDER_VISUALIZATIONS
        }
        self.current_saved_analysis_id: str | None = None
        self.dirty = True
        self.draft = deepcopy(draft) if draft is not None else self._default_draft()
        self._normalize_draft()

    @property
    def is_editing(self) -> bool:
        return self.current_saved_analysis_id is not None

    def mark_changed(self) -> None:
        self.dirty = True

    def _default_draft(self) -> CustomAnalysisDraft:
        datasets = self.datasets()
        dataset_id = datasets[0].dataset_id if datasets else ""
        draft = CustomAnalysisDraft(dataset_id=dataset_id)
        group_fields = self.group_fields(dataset_id) if dataset_id else []
        draft.group_field = group_fields[0].field_id if group_fields else ""
        return draft

    def reset(self) -> CustomAnalysisDraft:
        self.draft = self._default_draft()
        self.current_saved_analysis_id = None
        self.dirty = True
        return self.draft

    def load_definition(self, definition: AnalysisDefinition) -> CustomAnalysisDraft:
        self._validate_template_definition(definition)
        self.draft = self._draft_from_definition(
            definition,
            analysis_id=definition.analysis_id,
        )
        self.current_saved_analysis_id = definition.analysis_id
        self.dirty = False
        return self.draft

    def load_template(self, definition: AnalysisDefinition) -> CustomAnalysisDraft:
        """Hydrate a builtin definition as a new unsaved custom-analysis draft."""

        self._validate_template_definition(definition)
        self.draft = self._draft_from_definition(
            definition,
            analysis_id=_new_preview_id(),
        )
        self.current_saved_analysis_id = None
        self.dirty = True
        return self.draft

    def supports_template(self, definition: AnalysisDefinition) -> bool:
        try:
            self._validate_template_definition(definition)
        except AnalysisValidationError:
            return False
        return True

    def _validate_template_definition(self, definition: AnalysisDefinition) -> None:
        self._validate_builder_supported_definition(definition)
        self.service.validate_analysis(definition)

    def _draft_from_definition(
        self,
        definition: AnalysisDefinition,
        *,
        analysis_id: str,
    ) -> CustomAnalysisDraft:
        measure = definition.measures[0] if definition.measures else None
        sort = definition.sort[0] if definition.sort else None
        draft = CustomAnalysisDraft(
            analysis_id=analysis_id,
            title=definition.title,
            dataset_id=definition.dataset,
            visualization=definition.visualization,
            group_field=definition.dimensions[0] if definition.dimensions else "",
            aggregation=measure.aggregation if measure is not None else "count_rows",
            measure_field=measure.field if measure is not None else "",
            filters=[builder_filter_draft_from_definition(item) for item in definition.filters],
            sort_field=sort.field if sort is not None else "",
            sort_direction=sort.direction if sort is not None else "desc",
            limit=definition.limit,
            selected_table_fields=list(definition.select_fields),
            options=deepcopy(definition.options),
            visual_settings=AnalysisVisualSettings.from_options(
                definition.options,
                selected_table_fields=definition.select_fields,
                strict=True,
            ),
            visual_settings_explicit=has_visual_settings(definition.options),
            kpi_decimal_explicit=_has_explicit_kpi_decimal(definition.options),
        )
        self.draft = draft
        self._normalize_draft()
        if definition.visualization != "kpi" and definition.limit is None:
            self.draft.limit = None
        return self.draft

    def save_current(self) -> AnalysisDefinition:
        definition = self.build_definition()
        if self.current_saved_analysis_id is None:
            saved = self.service.create_saved_analysis(definition)
        else:
            saved = self.service.update_saved_analysis(
                definition,
                self.current_saved_analysis_id,
            )
        self.load_definition(saved)
        return saved

    def datasets(self) -> list[DatasetDefinition]:
        return self.registry.list_datasets()

    def fields(self, dataset_id: str | None = None) -> list[FieldDefinition]:
        return self.registry.list_fields(dataset_id or self.draft.dataset_id)

    def _builder_fields(self, role: str, dataset_id: str | None = None) -> list[FieldDefinition]:
        return sorted(
            [field for field in self.fields(dataset_id) if field.builder_allows(role)],
            key=lambda field: (field.builder_priority, field.title.casefold(), field.field_id),
        )

    def group_fields(self, dataset_id: str | None = None) -> list[FieldDefinition]:
        return [field for field in self._builder_fields("group", dataset_id) if field.groupable]

    def filter_fields(self, dataset_id: str | None = None) -> list[FieldDefinition]:
        return [field for field in self._builder_fields("filter", dataset_id) if field.filterable]

    def table_fields(self, dataset_id: str | None = None) -> list[FieldDefinition]:
        return self._builder_fields("table", dataset_id)

    def visualization_options(self) -> tuple[BuilderVisualizationOption, ...]:
        return BUILDER_VISUALIZATIONS

    def visualization_mode(self, visualization: str | None = None) -> str:
        visualization_id = visualization or self.draft.visualization
        try:
            return self._visualization_lookup[visualization_id].mode
        except KeyError as exc:
            raise AnalysisValidationError(
                f"Analiz Oluştur ekranında desteklenmeyen görünüm: {visualization_id}"
            ) from exc

    def aggregation_options(self, dataset_id: str | None = None) -> list[str]:
        aggregation_ids: set[str] = set(self._row_aggregations)
        for field in self._builder_fields("measure", dataset_id):
            if field.aggregatable:
                aggregation_ids.update(field.allowed_aggregations)
        return [
            aggregation_id
            for aggregation_id in AGGREGATION_TITLES
            if aggregation_id in aggregation_ids
        ]

    def measure_fields(
        self,
        aggregation: str | None = None,
        dataset_id: str | None = None,
    ) -> list[FieldDefinition]:
        aggregation_id = aggregation or self.draft.aggregation
        if aggregation_id in self._row_aggregations:
            return []
        return [
            field
            for field in self._builder_fields("measure", dataset_id)
            if field.aggregatable and aggregation_id in field.allowed_aggregations
        ]

    def filter_operators(self, field_id: str, dataset_id: str | None = None) -> tuple[str, ...]:
        field = self.registry.get_field(dataset_id or self.draft.dataset_id, field_id)
        return field.filter_operators

    def set_dataset(self, dataset_id: str) -> None:
        self.registry.get_dataset(dataset_id)
        if dataset_id == self.draft.dataset_id:
            return
        self.draft.dataset_id = dataset_id
        self.draft.group_field = ""
        self.draft.measure_field = ""
        self.draft.filters.clear()
        self.draft.sort_field = ""
        self.draft.selected_table_fields.clear()
        self.draft.visual_settings.sync_table_columns(())
        group_fields = self.group_fields(dataset_id)
        if group_fields:
            self.draft.group_field = group_fields[0].field_id
        self._normalize_measure()
        if self.draft.visualization == "table":
            self.draft.selected_table_fields = self._default_table_fields()
            self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)
        self._apply_kpi_decimal_default()
        self._normalize_limit()
        if self.draft.visualization in {"kpi", "table"}:
            self.draft.group_field = ""
        self.mark_changed()

    def set_visualization(self, visualization: str) -> None:
        self.visualization_mode(visualization)
        if visualization == self.draft.visualization:
            return
        self.draft.visualization = visualization
        if visualization == "kpi":
            self.draft.group_field = ""
            self.draft.sort_field = ""
            self._apply_kpi_decimal_default()
        elif visualization == "table":
            self.draft.group_field = ""
            self.draft.measure_field = ""
            self.draft.sort_field = ""
            if not self.draft.selected_table_fields:
                self.draft.selected_table_fields = self._default_table_fields()
                self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)
        else:
            if not self._is_valid_group_field(self.draft.group_field):
                groups = self.group_fields()
                self.draft.group_field = groups[0].field_id if groups else ""
            if self.draft.sort_field not in {self.draft.group_field, "value"}:
                self.draft.sort_field = ""
        self._normalize_limit()
        self.mark_changed()

    def set_aggregation(self, aggregation: str) -> None:
        if aggregation not in self.aggregation_options():
            raise AnalysisValidationError(f"Desteklenmeyen hesaplama: {aggregation}")
        if aggregation == self.draft.aggregation:
            return
        self.draft.aggregation = aggregation
        self._normalize_measure()
        self._apply_kpi_decimal_default()
        self.mark_changed()

    def visual_settings(self) -> AnalysisVisualSettings:
        return self.draft.visual_settings

    def update_chart_visual_settings(self, **changes: Any) -> None:
        self.draft.visual_settings.replace_chart(**changes)
        self.draft.visual_settings_explicit = True
        self.mark_changed()

    def update_kpi_visual_settings(
        self,
        *,
        decimal_places_explicit: bool | None = None,
        **changes: Any,
    ) -> None:
        self.draft.visual_settings.replace_kpi(**changes)
        if "decimal_places" in changes and decimal_places_explicit is not False:
            self.draft.kpi_decimal_explicit = True
        self.draft.visual_settings_explicit = True
        self.mark_changed()

    def set_table_column_order(self, order: list[str]) -> None:
        self.draft.visual_settings.replace_table(column_order=tuple(order))
        self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)
        self.draft.visual_settings_explicit = True
        self.mark_changed()

    def sync_table_visual_settings(self) -> None:
        self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)

    def _default_table_fields(self, limit: int = 5) -> list[str]:
        return [field.field_id for field in self.table_fields()[: max(1, int(limit))]]

    def _apply_kpi_decimal_default(self) -> None:
        if self.draft.visualization != "kpi" or self.draft.kpi_decimal_explicit:
            return
        places = 0 if self.draft.aggregation in _COUNT_LIKE_AGGREGATIONS else 2
        self.draft.visual_settings.replace_kpi(decimal_places=places)

    def sort_options(self) -> list[tuple[str, str]]:
        if self.draft.visualization == "kpi":
            return []
        if self.draft.visualization == "table":
            options: list[tuple[str, str]] = []
            selected = set(self.draft.selected_table_fields)
            for field in self.table_fields():
                if field.field_id in selected and field.sortable:
                    options.append((field.field_id, field.title))
            return options
        options = []
        if self.draft.group_field:
            field = self.registry.get_field(self.draft.dataset_id, self.draft.group_field)
            options.append((field.field_id, "Kategori"))
        options.append(("value", "Değer"))
        return options

    def add_filter(self) -> BuilderFilterDraft:
        fields = self.filter_fields()
        draft = BuilderFilterDraft()
        if fields:
            draft.field_id = fields[0].field_id
            operators = fields[0].filter_operators
            draft.operator = operators[0] if operators else ""
        self.draft.filters.append(draft)
        self.mark_changed()
        return draft

    def remove_filter(self, filter_draft: BuilderFilterDraft) -> None:
        before = len(self.draft.filters)
        self.draft.filters = [item for item in self.draft.filters if item is not filter_draft]
        if len(self.draft.filters) != before:
            self.mark_changed()

    def convert_filter(self, filter_draft: BuilderFilterDraft) -> FilterDefinition:
        if not filter_draft.field_id:
            raise AnalysisValidationError("Filtre için bir alan seçin.")
        field = self.registry.get_field(self.draft.dataset_id, filter_draft.field_id)
        if not field.filterable:
            raise AnalysisValidationError(f"{field.title} alanı filtrelenemez.")
        operator = str(filter_draft.operator or "").strip()
        if operator not in field.filter_operators:
            raise AnalysisValidationError(f"{field.title} alanı için seçilen koşul desteklenmiyor.")

        if operator in _NO_VALUE_FILTERS:
            value: Any = None
        elif operator == "between":
            value = [
                self._convert_scalar(field, filter_draft.raw_value),
                self._convert_scalar(field, filter_draft.raw_value_to),
            ]
        elif operator in _LIST_FILTERS:
            parts = [item.strip() for item in str(filter_draft.raw_value or "").split(",") if item.strip()]
            if not parts:
                raise AnalysisValidationError(f"{field.title} filtresi için en az bir değer girin.")
            value = [self._convert_scalar(field, item) for item in parts]
        else:
            value = self._convert_scalar(field, filter_draft.raw_value)
        return FilterDefinition(field=field.field_id, operator=operator, value=value)

    def build_definition(self) -> AnalysisDefinition:
        title = str(self.draft.title or "").strip()
        if not title:
            raise AnalysisValidationError("Analiz adı boş bırakılamaz.")
        self.registry.get_dataset(self.draft.dataset_id)
        mode = self.visualization_mode()
        filters = [self.convert_filter(item) for item in self.draft.filters]
        sort = self._build_sort()
        self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)
        options = (
            self.draft.visual_settings.to_options(self.draft.options)
            if self.draft.visual_settings_explicit
            else deepcopy(self.draft.options)
        )
        if self.draft.visual_settings_explicit:
            visual_payload = options.get("visual_settings")
            if isinstance(visual_payload, dict):
                kpi_payload = visual_payload.get("kpi")
                if isinstance(kpi_payload, dict):
                    kpi_payload["decimal_places_explicit"] = self.draft.kpi_decimal_explicit

        if mode == "projection":
            selected = self._valid_selected_table_fields()
            if not selected:
                raise AnalysisValidationError("Tablo için en az bir alan seçin.")
            definition = AnalysisDefinition(
                analysis_id=self.draft.analysis_id,
                title=title,
                dataset=self.draft.dataset_id,
                visualization=self.draft.visualization,
                filters=filters,
                sort=sort,
                select_fields=selected,
                limit=self.draft.limit,
                options=deepcopy(options),
            )
        else:
            dimensions: list[str] = []
            if self.draft.visualization != "kpi":
                if not self._is_valid_group_field(self.draft.group_field):
                    raise AnalysisValidationError(
                        f"{self._visualization_lookup[self.draft.visualization].title} için bir gruplama alanı seçin."
                    )
                dimensions = [self.draft.group_field]
            measure = self._build_measure()
            definition = AnalysisDefinition(
                analysis_id=self.draft.analysis_id,
                title=title,
                dataset=self.draft.dataset_id,
                visualization=self.draft.visualization,
                dimensions=dimensions,
                measures=[measure],
                filters=filters,
                sort=sort,
                limit=None if self.draft.visualization == "kpi" else self.draft.limit,
                options=deepcopy(options),
            )

        return definition

    def preview(self):
        definition = self.build_definition()
        result = self.service.execute_analysis(definition)
        return definition, result

    def _validate_builder_supported_definition(self, definition: AnalysisDefinition) -> None:
        mode = self.visualization_mode(definition.visualization)
        if len(definition.sort) > 1:
            raise AnalysisValidationError("Analiz Oluştur en fazla bir sıralama kuralını düzenleyebilir.")
        if mode == "projection":
            if definition.dimensions or definition.measures:
                raise AnalysisValidationError("Bu tablo tanımı Analiz Oluştur tarafından düzenlenemiyor.")
            return
        expected_dimensions = 0 if definition.visualization == "kpi" else 1
        if len(definition.dimensions) != expected_dimensions:
            raise AnalysisValidationError("Bu analiz gruplama yapısı Analiz Oluştur tarafından desteklenmiyor.")
        if len(definition.measures) != 1:
            raise AnalysisValidationError("Bu analiz hesaplama yapısı Analiz Oluştur tarafından desteklenmiyor.")
        if (definition.measures[0].alias or "value") != "value":
            raise AnalysisValidationError("Bu analiz sonuç alanı Analiz Oluştur tarafından desteklenmiyor.")

    def _build_measure(self) -> MeasureDefinition:
        aggregation = self.draft.aggregation
        if aggregation not in self.aggregation_options():
            raise AnalysisValidationError("Geçerli bir hesaplama seçin.")
        if aggregation in self._row_aggregations:
            return MeasureDefinition(field="", aggregation=aggregation, alias="value")
        allowed_fields = {field.field_id: field for field in self.measure_fields(aggregation)}
        field = allowed_fields.get(self.draft.measure_field)
        if field is None:
            title = AGGREGATION_TITLES.get(aggregation, aggregation)
            raise AnalysisValidationError(f"{title} hesaplaması için uygun bir alan seçin.")
        return MeasureDefinition(field=field.field_id, aggregation=aggregation, alias="value")

    def _build_sort(self) -> list[SortDefinition]:
        sort_field = str(self.draft.sort_field or "").strip()
        if not sort_field:
            return []
        allowed = {field_id for field_id, _title in self.sort_options()}
        if sort_field not in allowed:
            raise AnalysisValidationError("Seçilen sıralama alanı artık geçerli değil.")
        return [SortDefinition(field=sort_field, direction=self.draft.sort_direction)]

    def _convert_scalar(self, field: FieldDefinition, raw_value: Any) -> Any:
        text = str(raw_value or "").strip()
        if not text:
            raise AnalysisValidationError(f"{field.title} filtresi için bir değer girin.")
        try:
            if field.field_type == "integer":
                numeric = float(text.replace(",", "."))
                if not numeric.is_integer():
                    raise ValueError
                return int(numeric)
            if field.field_type == "number":
                return float(text.replace(",", "."))
            if field.field_type == "boolean":
                normalized = normalize_text(text)
                if normalized in {"1", "true", "evet", "yes"}:
                    return True
                if normalized in {"0", "false", "hayir", "no"}:
                    return False
                raise ValueError
            if field.field_type == "date":
                parsed = parse_date(text)
                if parsed is None:
                    raise ValueError
                return parsed.isoformat()
            if field.field_type == "datetime":
                parsed = parse_datetime(text)
                if parsed is None:
                    raise ValueError
                return parsed.isoformat()
            return text
        except (TypeError, ValueError) as exc:
            type_labels = {
                "integer": "tam sayı",
                "number": "sayı",
                "boolean": "Evet veya Hayır",
                "date": "geçerli tarih (YYYY-AA-GG)",
                "datetime": "geçerli tarih/saat",
            }
            expected = type_labels.get(field.field_type, "geçerli değer")
            raise AnalysisValidationError(
                f"{field.title} filtresi için {expected} girin."
            ) from exc

    def _normalize_draft(self) -> None:
        datasets = [dataset.dataset_id for dataset in self.datasets()]
        if self.draft.dataset_id not in datasets:
            self.draft.dataset_id = datasets[0] if datasets else ""
            self.draft.filters.clear()
            self.draft.selected_table_fields.clear()
        if self.draft.visualization not in self._visualization_lookup:
            self.draft.visualization = "horizontal_bar"
        aggregation_options = self.aggregation_options()
        if self.draft.aggregation not in aggregation_options:
            self.draft.aggregation = aggregation_options[0] if aggregation_options else "count_rows"
        if not self._is_valid_group_field(self.draft.group_field):
            groups = self.group_fields()
            self.draft.group_field = groups[0].field_id if groups and self.draft.visualization not in {"kpi", "table"} else ""
        self._normalize_measure()
        self._apply_kpi_decimal_default()
        self.draft.selected_table_fields = self._valid_selected_table_fields()
        if self.draft.visualization == "table" and not self.draft.selected_table_fields:
            self.draft.selected_table_fields = self._default_table_fields()
        self.draft.visual_settings.sync_table_columns(self.draft.selected_table_fields)
        self.draft.filters = [
            item for item in self.draft.filters if self._is_valid_filter_field(item.field_id)
        ]
        if self.draft.sort_direction not in SORT_DIRECTION_TITLES:
            self.draft.sort_direction = "desc"
        if self.draft.sort_field and self.draft.sort_field not in {item[0] for item in self.sort_options()}:
            self.draft.sort_field = ""
        self._normalize_limit()

    def _normalize_measure(self) -> None:
        fields = self.measure_fields(self.draft.aggregation)
        allowed = {field.field_id for field in fields}
        if self.draft.measure_field not in allowed:
            self.draft.measure_field = fields[0].field_id if fields else ""

    def _normalize_limit(self) -> None:
        if self.draft.visualization == "kpi":
            self.draft.limit = None
            return
        if self.draft.limit is None or self.draft.limit < 1:
            self.draft.limit = 100 if self.draft.visualization == "table" else 20

    def _valid_selected_table_fields(self) -> list[str]:
        available = {field.field_id for field in self.table_fields()}
        return [field_id for field_id in self.draft.selected_table_fields if field_id in available]

    def _is_valid_group_field(self, field_id: str) -> bool:
        return field_id in {field.field_id for field in self.group_fields()}

    def _is_valid_filter_field(self, field_id: str) -> bool:
        return field_id in {field.field_id for field in self.filter_fields()}


__all__ = [
    "ANALYSIS_BUILDER_ID",
    "AGGREGATION_TITLES",
    "BUILDER_VISUALIZATIONS",
    "FILTER_OPERATOR_TITLES",
    "SORT_DIRECTION_TITLES",
    "AnalysisBuilderController",
    "BuilderFilterDraft",
    "BuilderVisualizationOption",
    "CustomAnalysisDraft",
    "builder_filter_draft_from_definition",
]
