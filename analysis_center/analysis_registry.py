from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .analysis_definitions import AGGREGATIONS, FILTER_OPERATORS, VISUALIZATIONS, AnalysisValidationError
from .analysis_utils import is_acceptance_completed, normalize_status_bucket


FIELD_TYPES = ("text", "category", "number", "integer", "boolean", "date", "datetime")
BUILDER_FIELD_ROLES = ("group", "measure", "filter", "table")

TYPE_AGGREGATIONS = {
    "text": ("count", "count_distinct"),
    "category": ("count", "count_distinct"),
    "number": ("count", "count_distinct", "sum", "avg", "min", "max"),
    "integer": ("count", "count_distinct", "sum", "avg", "min", "max"),
    "boolean": ("count", "count_distinct"),
    "date": ("count", "count_distinct", "min", "max"),
    "datetime": ("count", "count_distinct", "min", "max"),
}

TYPE_FILTER_OPERATORS = {
    "text": ("equals", "not_equals", "contains", "not_contains", "is_empty", "is_not_empty", "in", "not_in"),
    "category": ("equals", "not_equals", "contains", "not_contains", "is_empty", "is_not_empty", "in", "not_in"),
    "number": ("equals", "not_equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "between", "is_empty", "is_not_empty", "in", "not_in"),
    "integer": ("equals", "not_equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "between", "is_empty", "is_not_empty", "in", "not_in"),
    "boolean": ("equals", "not_equals", "is_empty", "is_not_empty"),
    "date": ("equals", "not_equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "between", "is_empty", "is_not_empty", "in", "not_in"),
    "datetime": ("equals", "not_equals", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "between", "is_empty", "is_not_empty", "in", "not_in"),
}


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    field_id: str
    title: str
    field_type: str
    filterable: bool = True
    groupable: bool = True
    aggregatable: bool = True
    sortable: bool = True
    allowed_aggregations: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    derived: bool = False
    resolver: str = ""
    builder_roles: tuple[str, ...] = BUILDER_FIELD_ROLES
    builder_priority: int = 100

    def __post_init__(self) -> None:
        if self.field_type not in FIELD_TYPES:
            raise ValueError(f"Unsupported field type: {self.field_type}")
        if not self.allowed_aggregations:
            object.__setattr__(self, "allowed_aggregations", TYPE_AGGREGATIONS[self.field_type])
        if self.derived and not self.resolver:
            raise ValueError(f"Derived field resolver eksik: {self.field_id}")
        if self.resolver and not self.derived:
            raise ValueError(f"Normal field resolver tanımlayamaz: {self.field_id}")
        unknown_builder_roles = set(self.builder_roles) - set(BUILDER_FIELD_ROLES)
        if unknown_builder_roles:
            raise ValueError(
                f"Bilinmeyen builder field role: {self.field_id}: {sorted(unknown_builder_roles)}"
            )

    @property
    def filter_operators(self) -> tuple[str, ...]:
        return TYPE_FILTER_OPERATORS[self.field_type] if self.filterable else ()

    def builder_allows(self, role: str) -> bool:
        return role in self.builder_roles

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "title": self.title,
            "field_type": self.field_type,
            "filterable": self.filterable,
            "groupable": self.groupable,
            "aggregatable": self.aggregatable,
            "sortable": self.sortable,
            "allowed_aggregations": list(self.allowed_aggregations),
            "filter_operators": list(self.filter_operators),
            "description": self.description,
            "derived": self.derived,
            "builder_roles": list(self.builder_roles),
            "builder_priority": self.builder_priority,
        }


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    dataset_id: str
    title: str
    fields: dict[str, FieldDefinition]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "title": self.title,
            "description": self.description,
            "fields": [item.to_dict() for item in self.fields.values()],
        }


def _f(field_id: str, title: str, field_type: str, **kwargs: Any) -> FieldDefinition:
    return FieldDefinition(field_id=field_id, title=title, field_type=field_type, **kwargs)


DerivedFieldResolver = Callable[[Mapping[str, Any]], Any]


def _status_bucket_resolver(row: Mapping[str, Any]) -> str:
    return normalize_status_bucket(row.get("status"))


def _acceptance_completed_resolver(row: Mapping[str, Any]) -> bool:
    return is_acceptance_completed(row)


def _platform_bucket_resolver(row: Mapping[str, Any]) -> str:
    return str(row.get("platform") or "").strip() or "Eksik platform"


DERIVED_FIELD_RESOLVERS: dict[str, DerivedFieldResolver] = {
    "status_bucket": _status_bucket_resolver,
    "acceptance_completed": _acceptance_completed_resolver,
    "platform_bucket": _platform_bucket_resolver,
}


DATASETS: dict[str, DatasetDefinition] = {
    "contracts": DatasetDefinition("contracts", "Sözleşmeler", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "platform": _f("platform", "Platform", "category", builder_priority=20),
        "platform_bucket": _f("platform_bucket", "Standart Platform", "category", derived=True, resolver="platform_bucket", builder_priority=10),
        "contract_no": _f("contract_no", "Sözleşme No", "text", builder_priority=30),
        "contract_type": _f("contract_type", "Sözleşme Tipi", "category", builder_priority=40),
        "type_display": _f("type_display", "Sözleşme Türü", "text", builder_priority=45),
        "status": _f("status", "Durum", "category", builder_priority=15),
        "status_bucket": _f("status_bucket", "Standart Durum", "category", derived=True, resolver="status_bucket", builder_priority=0),
        "signed_date": _f("signed_date", "İmza Tarihi", "date", builder_priority=60),
        "t0_date": _f("t0_date", "T0 Tarihi", "date", builder_priority=61),
        "t0_months": _f("t0_months", "T0 Ay", "integer", builder_priority=70),
        "completion_date": _f("completion_date", "Termin Tarihi", "date", builder_priority=62),
        "acceptance_date": _f("acceptance_date", "Kabul Tarihi", "date", builder_priority=63),
        "content": _f("content", "İçerik", "text", builder_priority=90),
        "is_main": _f("is_main", "Ana Sözleşme", "boolean", builder_priority=50),
        "user": _f("user", "Kullanıcı", "category", builder_priority=80),
        "users": _f("users", "Kullanıcılar", "category", aggregatable=False, builder_roles=("group", "filter", "table"), builder_priority=81),
        "tags": _f("tags", "Etiketler", "category", aggregatable=False, builder_roles=("group", "filter", "table"), builder_priority=82),
    }),
    "platforms": DatasetDefinition("platforms", "Platformlar", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "display_name": _f("display_name", "Görünen Ad", "text", builder_priority=0),
        "name": _f("name", "Ad", "text", builder_priority=10),
        "is_active": _f("is_active", "Aktif", "boolean", builder_priority=20),
    }),
    "acceptances": DatasetDefinition("acceptances", "Teslimatlar / Kabuller", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "contract_id": _f("contract_id", "Sözleşme ID", "integer", builder_roles=("filter", "table"), builder_priority=95),
        "system_id": _f("system_id", "Sistem ID", "integer", builder_roles=("filter", "table"), builder_priority=96),
        "platform": _f("platform", "Platform", "category", builder_priority=10),
        "contract_no": _f("contract_no", "Sözleşme No", "text", builder_priority=20),
        "system_name": _f("system_name", "Sistem", "category", builder_priority=30),
        "name": _f("name", "Teslimat Adı", "text", builder_priority=40),
        "status": _f("status", "Durum", "category", builder_priority=15),
        "status_bucket": _f("status_bucket", "Standart Durum", "category", derived=True, resolver="status_bucket", builder_priority=0),
        "completed": _f("completed", "Tamamlandı", "boolean", derived=True, resolver="acceptance_completed", builder_priority=50),
        "acceptance_date": _f("acceptance_date", "Kabul Tarihi", "date", builder_priority=62),
        "planned_acceptance_date": _f("planned_acceptance_date", "Planlanan Kabul Tarihi", "date", builder_priority=60),
        "planned_delivery_date": _f("planned_delivery_date", "Planlanan Teslimat Tarihi", "date", builder_priority=61),
        "completion_date": _f("completion_date", "Termin Tarihi", "date", builder_priority=63),
        "planned_total": _f("planned_total", "Planlanan Toplam", "number", builder_priority=70),
        "delivered_total": _f("delivered_total", "Teslim Edilen Toplam", "number", builder_priority=71),
    }),
    "deadlines": DatasetDefinition("deadlines", "Terminler", {
        "event_id": _f("event_id", "Termin Olayı", "text", builder_roles=("filter", "table"), builder_priority=98),
        "source_type": _f("source_type", "Kaynak Türü", "category", builder_priority=30),
        "source_id": _f("source_id", "Kaynak ID", "integer", builder_roles=("filter", "table"), builder_priority=99),
        "entity": _f("entity", "Kayıt Türü", "category", builder_priority=25),
        "platform": _f("platform", "Platform", "category", builder_priority=10),
        "contract_no": _f("contract_no", "Sözleşme No", "text", builder_priority=20),
        "name": _f("name", "Kayıt", "text", builder_priority=40),
        "date_field": _f("date_field", "Termin Alanı", "category", builder_roles=("filter", "table"), builder_priority=80),
        "raw_date_value": _f("raw_date_value", "Ham Tarih", "text", builder_roles=("filter", "table"), builder_priority=90),
        "date_status": _f("date_status", "Tarih Durumu", "category", builder_priority=0),
        "due_date": _f("due_date", "Termin Tarihi", "date", builder_priority=50),
        "days": _f("days", "Kalan Gün", "integer", builder_priority=60),
        "completed": _f("completed", "Tamamlandı", "boolean", builder_priority=65),
        "status": _f("status", "Durum", "category", builder_priority=15),
    }),
    "systems": DatasetDefinition("systems", "Sistemler", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "contract_id": _f("contract_id", "Sözleşme ID", "integer", builder_roles=("filter", "table"), builder_priority=95),
        "platform": _f("platform", "Platform", "category", builder_priority=10),
        "contract_no": _f("contract_no", "Sözleşme No", "text", builder_priority=20),
        "name": _f("name", "Sistem Adı", "text", builder_priority=30),
        "status": _f("status", "Durum", "category", builder_priority=0),
        "completion_date": _f("completion_date", "Termin Tarihi", "date", builder_priority=60),
        "acceptance_date": _f("acceptance_date", "Kabul Tarihi", "date", builder_priority=61),
        "t0_date": _f("t0_date", "T0 Tarihi", "date", builder_priority=62),
        "t0_months": _f("t0_months", "T0 Ay", "integer", builder_priority=70),
    }),
    "components": DatasetDefinition("components", "Bileşenler", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "unit": _f("unit", "Birim", "category", builder_priority=0),
        "active": _f("active", "Aktif", "boolean", builder_priority=10),
        "name": _f("name", "Bileşen Adı", "text", builder_priority=20),
        "version": _f("version", "Versiyon", "text", builder_priority=30),
    }),
    "users": DatasetDefinition("users", "Kullanıcılar", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "yi_yd": _f("yi_yd", "Yİ / YD", "category", builder_priority=0),
        "active": _f("active", "Aktif", "boolean", builder_priority=10),
        "name": _f("name", "Kullanıcı Adı", "text", builder_priority=20),
    }),
    "tags": DatasetDefinition("tags", "Etiketler", {
        "id": _f("id", "ID", "integer", builder_roles=("filter",), builder_priority=1000),
        "name": _f("name", "Etiket Adı", "text", builder_priority=0),
        "contract_count": _f("contract_count", "Sözleşme Sayısı", "integer", builder_priority=10),
        "color": _f("color", "Renk", "text", builder_roles=("filter", "table"), builder_priority=80),
    }),
}



class AnalysisRegistry:
    def __init__(
        self,
        datasets: dict[str, DatasetDefinition] | None = None,
        derived_field_resolvers: Mapping[str, DerivedFieldResolver] | None = None,
    ):
        self._datasets = dict(datasets or DATASETS)
        self._derived_field_resolvers = dict(derived_field_resolvers or DERIVED_FIELD_RESOLVERS)

    def get_dataset(self, dataset_id: str) -> DatasetDefinition:
        try:
            return self._datasets[dataset_id]
        except KeyError as exc:
            raise AnalysisValidationError(f"Bilinmeyen dataset: {dataset_id}") from exc

    def get_field(self, dataset_id: str, field_id: str) -> FieldDefinition:
        dataset = self.get_dataset(dataset_id)
        try:
            return dataset.fields[field_id]
        except KeyError as exc:
            raise AnalysisValidationError(f"Bilinmeyen field: {dataset_id}.{field_id}") from exc

    def list_datasets(self) -> list[DatasetDefinition]:
        return list(self._datasets.values())

    def list_fields(self, dataset_id: str) -> list[FieldDefinition]:
        return list(self.get_dataset(dataset_id).fields.values())

    def resolve_value(self, dataset_id: str, field_id: str, row: Mapping[str, Any]) -> Any:
        field = self.get_field(dataset_id, field_id)
        if not field.derived:
            return row.get(field_id)
        try:
            resolver = self._derived_field_resolvers[field.resolver]
        except KeyError as exc:
            raise AnalysisValidationError(
                f"Derived field resolver bulunamadı: {dataset_id}.{field_id}"
            ) from exc
        return resolver(row)


DEFAULT_REGISTRY = AnalysisRegistry()


def get_analysis_capabilities(registry: AnalysisRegistry | None = None) -> dict[str, Any]:
    active_registry = registry or DEFAULT_REGISTRY
    return {
        "datasets": [dataset.to_dict() for dataset in active_registry.list_datasets()],
        "visualizations": list(VISUALIZATIONS),
        "filter_operators": list(FILTER_OPERATORS),
        "aggregations": list(AGGREGATIONS),
        "row_aggregations": ["count_rows"],
    }
