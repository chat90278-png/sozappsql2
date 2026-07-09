from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from .analysis_definitions import AnalysisValidationError, FilterDefinition
from .analysis_registry import FieldDefinition
from .analysis_utils import normalize_text, parse_date, parse_datetime, text_value


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == ()


def _coerce(value: Any, field: FieldDefinition, *, strict: bool = True) -> Any:
    if _empty(value):
        return None
    if field.field_type in {"text", "category"}:
        return normalize_text(value)
    if field.field_type == "integer":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            if not strict:
                return None
            raise AnalysisValidationError(f"{field.field_id} için geçersiz integer değer: {value!r}") from exc
    if field.field_type == "number":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            if not strict:
                return None
            raise AnalysisValidationError(f"{field.field_id} için geçersiz numeric değer: {value!r}") from exc
    if field.field_type == "boolean":
        if isinstance(value, bool):
            return value
        normalized = normalize_text(value)
        if normalized in {"1", "true", "evet", "yes"}:
            return True
        if normalized in {"0", "false", "hayir", "no"}:
            return False
        if not strict:
            return None
        raise AnalysisValidationError(f"{field.field_id} için geçersiz boolean değer: {value!r}")
    if field.field_type == "date":
        parsed = parse_date(value)
        if parsed is None:
            if not strict:
                return None
            raise AnalysisValidationError(f"{field.field_id} için geçersiz tarih değeri: {value!r}")
        return parsed
    if field.field_type == "datetime":
        parsed = parse_datetime(value)
        if parsed is None:
            if not strict:
                return None
            raise AnalysisValidationError(f"{field.field_id} için geçersiz datetime değeri: {value!r}")
        return parsed
    return value


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple, set)):
        normalized_expected = normalize_text(expected)
        return any(normalized_expected in normalize_text(item) for item in actual)
    return normalize_text(expected) in normalize_text(actual)


FieldValueResolver = Callable[[str, Mapping[str, Any]], Any]


def matches_filter(
    row: Mapping[str, Any],
    definition: FilterDefinition,
    field: FieldDefinition,
    value_resolver: FieldValueResolver | None = None,
) -> bool:
    operator = definition.operator
    actual_raw = value_resolver(definition.field, row) if value_resolver else row.get(definition.field)
    expected_raw = definition.value

    if operator == "is_empty":
        return _empty(actual_raw)
    if operator == "is_not_empty":
        return not _empty(actual_raw)
    if operator == "contains":
        return _contains(actual_raw, expected_raw)
    if operator == "not_contains":
        return not _contains(actual_raw, expected_raw)

    # STS satırlarında TBD / YYYY-MM-TBD gibi esnek alanlar bulunabilir.
    # Bunlar filter tanım hatası değildir; karşılaştırılamayan gerçek satır değeri
    # olarak None kabul edilip ilgili tarih/numeric filtresinden elenir.
    actual = _coerce(actual_raw, field, strict=False)
    if operator in {"in", "not_in"}:
        expected = [_coerce(item, field) for item in list(expected_raw)]
        result = actual in expected
        return result if operator == "in" else not result
    if operator == "between":
        lower, upper = [_coerce(item, field) for item in list(expected_raw)]
        if actual is None:
            return False
        return lower <= actual <= upper

    expected = _coerce(expected_raw, field)
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if actual is None or expected is None:
        return False
    if operator == "greater_than":
        return actual > expected
    if operator == "greater_than_or_equal":
        return actual >= expected
    if operator == "less_than":
        return actual < expected
    if operator == "less_than_or_equal":
        return actual <= expected
    raise AnalysisValidationError(f"Desteklenmeyen filter operator: {operator}")


def apply_filters(
    rows: Iterable[Mapping[str, Any]],
    filters: list[FilterDefinition],
    field_lookup: Mapping[str, FieldDefinition],
    value_resolver: FieldValueResolver | None = None,
) -> list[dict[str, Any]]:
    result = [dict(row) for row in rows]
    for definition in filters:
        field = field_lookup[definition.field]
        result = [
            row for row in result
            if matches_filter(row, definition, field, value_resolver=value_resolver)
        ]
    return result
