from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .analysis_definitions import (
    AGGREGATION_VISUALIZATIONS,
    PROJECTION_VISUALIZATIONS,
    AnalysisDefinition,
    AnalysisResult,
    AnalysisValidationError,
)
from .analysis_filters import apply_filters
from .analysis_models import NormalizedAnalysisData
from .analysis_registry import AnalysisRegistry, DEFAULT_REGISTRY, FieldDefinition
from .analysis_utils import normalize_text, parse_date, parse_datetime


class AnalysisEngine:
    def __init__(self, registry: AnalysisRegistry | None = None):
        self.registry = registry or DEFAULT_REGISTRY

    def _resolve_value(self, dataset_id: str, field_id: str, row: Mapping[str, Any]) -> Any:
        return self.registry.resolve_value(dataset_id, field_id, row)

    def execute(self, definition: AnalysisDefinition, data: NormalizedAnalysisData) -> AnalysisResult:
        self.validate(definition)
        dataset = self.registry.get_dataset(definition.dataset)
        source_rows = [dict(row) for row in data.get(definition.dataset, [])]
        field_lookup = dataset.fields
        filtered_rows = apply_filters(
            source_rows,
            definition.filters,
            field_lookup,
            value_resolver=lambda field_id, row: self._resolve_value(definition.dataset, field_id, row),
        )

        if definition.visualization in AGGREGATION_VISUALIZATIONS:
            rows, columns, value = self._execute_aggregation(definition, filtered_rows, field_lookup)
        elif definition.visualization in PROJECTION_VISUALIZATIONS:
            rows, columns, value = self._execute_projection(definition, filtered_rows, field_lookup)
        else:
            # Preserve the pre-existing status path. This turn only separates table/list projection.
            rows, columns, value = self._execute_aggregation(definition, filtered_rows, field_lookup)

        return AnalysisResult(
            analysis_id=definition.analysis_id,
            dataset=definition.dataset,
            rows=rows,
            columns=columns,
            value=value,
            meta={
                "source_row_count": len(source_rows),
                "filtered_row_count": len(filtered_rows),
                "result_row_count": len(rows),
                "execution_errors": [],
                "warnings": [],
            },
        )

    def validate(self, definition: AnalysisDefinition) -> None:
        """Validate a definition against current registry and engine v1 capabilities."""

        self._validate(definition)

    def _validate(self, definition: AnalysisDefinition) -> None:
        if not isinstance(definition, AnalysisDefinition):
            raise AnalysisValidationError("definition AnalysisDefinition olmalıdır.")
        self.registry.get_dataset(definition.dataset)
        self._validate_filters(definition)

        if definition.visualization in AGGREGATION_VISUALIZATIONS:
            self._validate_aggregation(definition)
            return
        if definition.visualization in PROJECTION_VISUALIZATIONS:
            self._validate_projection(definition)
            return

        # Preserve the pre-existing status validation path.
        self._validate_aggregation(definition)

    def _validate_filters(self, definition: AnalysisDefinition) -> None:
        for filter_definition in definition.filters:
            field = self.registry.get_field(definition.dataset, filter_definition.field)
            if not field.filterable:
                raise AnalysisValidationError(f"Field filterable değil: {definition.dataset}.{filter_definition.field}")
            if filter_definition.operator not in field.filter_operators:
                raise AnalysisValidationError(
                    f"{definition.dataset}.{filter_definition.field} için filter desteklenmiyor: "
                    f"{filter_definition.operator}"
                )

    def _validate_aggregation(self, definition: AnalysisDefinition) -> None:
        dataset = self.registry.get_dataset(definition.dataset)
        if len(definition.dimensions) > 1:
            raise AnalysisValidationError("AnalysisEngine v1 en fazla 1 dimension destekler.")
        if len(definition.measures) != 1:
            raise AnalysisValidationError("AnalysisEngine v1 tam olarak 1 measure destekler.")
        for dimension in definition.dimensions:
            field = self.registry.get_field(definition.dataset, dimension)
            if not field.groupable:
                raise AnalysisValidationError(f"Field groupable değil: {definition.dataset}.{dimension}")
        measure = definition.measures[0]
        if not isinstance(measure.field, str):
            raise AnalysisValidationError("measure.field bir metin olmalıdır.")
        measure_field_id = measure.field.strip()
        if measure.aggregation == "count_rows":
            if measure_field_id:
                raise AnalysisValidationError("count_rows does not accept a field")
        else:
            if not measure_field_id:
                raise AnalysisValidationError(f"{measure.aggregation} requires a field")
            measure_field = self.registry.get_field(definition.dataset, measure_field_id)
            if not measure_field.aggregatable:
                raise AnalysisValidationError(f"Field aggregatable değil: {definition.dataset}.{measure_field_id}")
            if measure.aggregation not in measure_field.allowed_aggregations:
                raise AnalysisValidationError(
                    f"{definition.dataset}.{measure_field_id} için aggregation desteklenmiyor: {measure.aggregation}"
                )
        measure_alias = measure.alias or "value"
        sortable_result_fields = set(definition.dimensions) | {measure_alias, "value"}
        for sort_definition in definition.sort:
            if sort_definition.field in sortable_result_fields:
                continue
            field = dataset.fields.get(sort_definition.field)
            if field is None:
                raise AnalysisValidationError(f"Bilinmeyen sort field: {definition.dataset}.{sort_definition.field}")
            if not field.sortable:
                raise AnalysisValidationError(f"Field sortable değil: {definition.dataset}.{sort_definition.field}")

    def _validate_projection(self, definition: AnalysisDefinition) -> None:
        if definition.measures:
            raise AnalysisValidationError("table/list projection analyses do not support measures")
        if definition.dimensions:
            raise AnalysisValidationError("table/list projection analyses do not support dimensions")
        if not definition.select_fields:
            raise AnalysisValidationError("table/list projection analyses require select_fields")

        for field_id in definition.select_fields:
            self.registry.get_field(definition.dataset, field_id)

        selected = set(definition.select_fields)
        for sort_definition in definition.sort:
            if sort_definition.field not in selected:
                raise AnalysisValidationError("projection sort field must be present in select_fields")
            field = self.registry.get_field(definition.dataset, sort_definition.field)
            if not field.sortable:
                raise AnalysisValidationError(f"Field sortable değil: {definition.dataset}.{sort_definition.field}")

    def _execute_aggregation(
        self,
        definition: AnalysisDefinition,
        rows: list[dict[str, Any]],
        field_lookup: Mapping[str, FieldDefinition],
    ) -> tuple[list[dict[str, Any]], list[str], Any]:
        result_rows, columns, value = self._aggregate(definition, rows, field_lookup)
        result_rows = self._sort_aggregation(result_rows, definition)
        if definition.limit is not None:
            result_rows = result_rows[: definition.limit]
        return result_rows, columns, value

    def _execute_projection(
        self,
        definition: AnalysisDefinition,
        rows: list[dict[str, Any]],
        field_lookup: Mapping[str, FieldDefinition],
    ) -> tuple[list[dict[str, Any]], list[str], Any]:
        columns = list(definition.select_fields)
        projected_rows = [
            {
                field_id: self._resolve_value(definition.dataset, field_id, row)
                for field_id in columns
            }
            for row in rows
        ]
        projected_rows = self._sort_projection(projected_rows, definition, field_lookup)
        if definition.limit is not None:
            projected_rows = projected_rows[: definition.limit]
        return projected_rows, columns, None

    def _aggregate(
        self,
        definition: AnalysisDefinition,
        rows: list[dict[str, Any]],
        field_lookup: Mapping[str, FieldDefinition],
    ) -> tuple[list[dict[str, Any]], list[str], Any]:
        measure = definition.measures[0]
        alias = measure.alias or "value"
        measure_field = field_lookup.get(measure.field) if measure.aggregation != "count_rows" else None
        if not definition.dimensions:
            value = self._aggregate_values(
                rows, definition.dataset, measure.field, measure.aggregation, measure_field
            )
            return [{alias: value}], [alias], value

        dimension = definition.dimensions[0]
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[self._resolve_value(definition.dataset, dimension, row)].append(row)
        result = []
        for group_value, group_rows in grouped.items():
            aggregated = self._aggregate_values(
                group_rows, definition.dataset, measure.field, measure.aggregation, measure_field
            )
            result.append({dimension: group_value, alias: aggregated, "value": aggregated})
        columns = [dimension, alias]
        return result, columns, None

    @staticmethod
    def _is_empty_aggregate_value(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _distinct_marker(value: Any, field: FieldDefinition) -> Any:
        if field.field_type in {"text", "category"}:
            return normalize_text(value)
        if field.field_type == "number":
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise AnalysisValidationError(f"{field.field_id} alanında numeric olmayan veri bulundu.") from exc
        if field.field_type == "integer":
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise AnalysisValidationError(f"{field.field_id} alanında integer olmayan veri bulundu.") from exc
            if not numeric.is_integer():
                raise AnalysisValidationError(f"{field.field_id} alanında integer olmayan veri bulundu.")
            return int(numeric)
        if field.field_type == "date":
            parsed = parse_date(value)
            if parsed is None:
                raise AnalysisValidationError(f"{field.field_id} alanında geçersiz date değeri bulundu: {value!r}")
            return parsed
        if field.field_type == "datetime":
            parsed = parse_datetime(value)
            if parsed is None:
                raise AnalysisValidationError(f"{field.field_id} alanında geçersiz datetime değeri bulundu: {value!r}")
            return parsed
        if field.field_type == "boolean":
            if isinstance(value, bool):
                return value
            normalized = normalize_text(value)
            if normalized in {"1", "true", "evet", "yes"}:
                return True
            if normalized in {"0", "false", "hayir", "no"}:
                return False
            raise AnalysisValidationError(f"{field.field_id} alanında geçersiz boolean değeri bulundu: {value!r}")
        try:
            hash(value)
            return value
        except TypeError:
            return repr(value)

    def _aggregate_values(
        self,
        rows: Iterable[Mapping[str, Any]],
        dataset_id: str,
        field_id: str,
        aggregation: str,
        field: FieldDefinition | None,
    ) -> Any:
        row_list = list(rows)
        if aggregation == "count_rows":
            return len(row_list)
        if field is None:
            raise AnalysisValidationError(f"{aggregation} requires a field")

        raw_values = [self._resolve_value(dataset_id, field_id, row) for row in row_list]
        non_empty = [value for value in raw_values if not self._is_empty_aggregate_value(value)]

        if aggregation == "count":
            return len(non_empty)
        if aggregation == "count_distinct":
            return len({self._distinct_marker(value, field) for value in non_empty})

        if not non_empty:
            return None

        if field.field_type in {"number", "integer"}:
            try:
                values = [float(value) for value in non_empty]
            except (TypeError, ValueError) as exc:
                raise AnalysisValidationError(f"{field.field_id} alanında numeric olmayan veri bulundu.") from exc
        else:
            values = non_empty

        if aggregation == "sum":
            result = sum(values)
            return int(result) if field.field_type == "integer" and float(result).is_integer() else result
        if aggregation == "avg":
            return sum(values) / len(values)
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        raise AnalysisValidationError(f"Desteklenmeyen aggregation: {aggregation}")

    @staticmethod
    def _sort_aggregation(rows: list[dict[str, Any]], definition: AnalysisDefinition) -> list[dict[str, Any]]:
        result = list(rows)
        for sort_definition in reversed(definition.sort):
            def key(row: dict[str, Any]) -> tuple[bool, Any]:
                value = row.get(sort_definition.field)
                return value is None, value
            result.sort(key=key, reverse=sort_definition.direction == "desc")
        return result

    def _sort_projection(
        self,
        rows: list[dict[str, Any]],
        definition: AnalysisDefinition,
        field_lookup: Mapping[str, FieldDefinition],
    ) -> list[dict[str, Any]]:
        result = list(rows)
        for sort_definition in reversed(definition.sort):
            field = field_lookup[sort_definition.field]
            field_id = sort_definition.field
            valued_rows = [row for row in result if not self._is_empty_projection_sort_value(row.get(field_id))]
            empty_rows = [row for row in result if self._is_empty_projection_sort_value(row.get(field_id))]
            valued_rows.sort(
                key=lambda row, field_id=field_id, field=field: self._projection_sort_key(
                    row.get(field_id), field
                ),
                reverse=sort_definition.direction == "desc",
            )
            result = valued_rows + empty_rows
        return result

    @staticmethod
    def _is_empty_projection_sort_value(value: Any) -> bool:
        return value is None or value == ""

    @staticmethod
    def _projection_sort_key(value: Any, field: FieldDefinition) -> tuple[bool, Any]:
        if value is None or value == "":
            return True, None
        try:
            if field.field_type == "number":
                return False, float(value)
            if field.field_type == "integer":
                return False, int(value)
            if field.field_type == "date":
                parsed = parse_date(value)
                if parsed is None:
                    raise AnalysisValidationError(f"{field.field_id} alanında geçersiz date değeri bulundu: {value!r}")
                return False, parsed
            if field.field_type == "datetime":
                parsed = parse_datetime(value)
                if parsed is None:
                    raise AnalysisValidationError(f"{field.field_id} alanında geçersiz datetime değeri bulundu: {value!r}")
                return False, parsed
            if field.field_type == "boolean":
                return False, bool(value)
            return False, normalize_text(value)
        except (TypeError, ValueError) as exc:
            raise AnalysisValidationError(
                f"{field.field_id} alanında sıralanabilir {field.field_type} olmayan veri bulundu: {value!r}"
            ) from exc
