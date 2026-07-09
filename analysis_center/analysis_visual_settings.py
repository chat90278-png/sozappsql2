from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .analysis_definitions import AnalysisValidationError


VISUAL_SETTINGS_OPTION_KEY = "visual_settings"
PALETTE_IDS = ("corporate", "blue", "green", "warm", "pastel", "monochrome")
LEGEND_POSITIONS = ("right", "bottom")
MAX_DECIMAL_PLACES = 6
MAX_CATEGORY_LIMIT = 1000

CHART_PALETTES: dict[str, tuple[str, ...]] = {
    "corporate": (
        "#1f5be3", "#0f766e", "#7c3aed", "#d97706", "#dc2626", "#0891b2", "#4f46e5", "#65a30d",
    ),
    "blue": ("#1d4ed8", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe"),
    "green": ("#166534", "#15803d", "#16a34a", "#22c55e", "#4ade80", "#86efac"),
    "warm": ("#9a3412", "#c2410c", "#ea580c", "#f97316", "#f59e0b", "#facc15"),
    "pastel": ("#93c5fd", "#a7f3d0", "#c4b5fd", "#fdba74", "#fda4af", "#a5f3fc"),
    "monochrome": ("#0f172a", "#334155", "#475569", "#64748b", "#94a3b8", "#cbd5e1"),
}

PALETTE_TITLES: dict[str, str] = {
    "corporate": "Kurumsal",
    "blue": "Mavi",
    "green": "Yeşil",
    "warm": "Sıcak",
    "pastel": "Pastel",
    "monochrome": "Monokrom",
}

LEGEND_POSITION_TITLES: dict[str, str] = {
    "right": "Sağ",
    "bottom": "Alt",
}


@dataclass(frozen=True, slots=True)
class ChartVisualSettings:
    show_legend: bool = True
    legend_position: str = "right"
    show_values: bool = False
    palette: str = "corporate"
    max_categories: int | None = None
    group_others: bool = False


@dataclass(frozen=True, slots=True)
class KpiVisualSettings:
    subtitle: str = ""
    prefix: str = ""
    suffix: str = ""
    decimal_places: int = 2


@dataclass(frozen=True, slots=True)
class TableVisualSettings:
    column_order: tuple[str, ...] = ()


@dataclass(slots=True)
class AnalysisVisualSettings:
    chart: ChartVisualSettings = field(default_factory=ChartVisualSettings)
    kpi: KpiVisualSettings = field(default_factory=KpiVisualSettings)
    table: TableVisualSettings = field(default_factory=TableVisualSettings)
    _unknown_visual: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def defaults(cls, *, selected_table_fields: Sequence[str] = ()) -> "AnalysisVisualSettings":
        return cls(table=TableVisualSettings(tuple(_unique_text(selected_table_fields))))

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any] | None,
        *,
        selected_table_fields: Sequence[str] = (),
        strict: bool = True,
    ) -> "AnalysisVisualSettings":
        source = dict(options or {})
        raw_visual = source.get(VISUAL_SETTINGS_OPTION_KEY, {})
        if not isinstance(raw_visual, Mapping):
            if strict:
                raise AnalysisValidationError("Görünüm ayarları bir object/dict olmalıdır.")
            raw_visual = {}
        visual = dict(raw_visual)
        unknown = {
            key: deepcopy(value)
            for key, value in visual.items()
            if key not in {"chart", "kpi", "table"}
        }
        return cls(
            chart=_chart_settings(visual.get("chart"), strict=strict),
            kpi=_kpi_settings(visual.get("kpi"), strict=strict),
            table=_table_settings(
                visual.get("table"),
                selected_table_fields=selected_table_fields,
                strict=strict,
            ),
            _unknown_visual=unknown,
        )

    def to_options(self, base_options: Mapping[str, Any] | None = None) -> dict[str, Any]:
        options = deepcopy(dict(base_options or {}))
        raw_visual = options.get(VISUAL_SETTINGS_OPTION_KEY, {})
        preserved = dict(raw_visual) if isinstance(raw_visual, Mapping) else {}
        preserved.update(deepcopy(self._unknown_visual))
        chart_payload = dict(preserved.get("chart", {})) if isinstance(preserved.get("chart"), Mapping) else {}
        chart_payload.update({
            "show_legend": self.chart.show_legend,
            "legend_position": self.chart.legend_position,
            "show_values": self.chart.show_values,
            "palette": self.chart.palette,
            "max_categories": self.chart.max_categories,
            "group_others": self.chart.group_others,
        })
        kpi_payload = dict(preserved.get("kpi", {})) if isinstance(preserved.get("kpi"), Mapping) else {}
        kpi_payload.update({
            "subtitle": self.kpi.subtitle,
            "prefix": self.kpi.prefix,
            "suffix": self.kpi.suffix,
            "decimal_places": self.kpi.decimal_places,
        })
        table_payload = dict(preserved.get("table", {})) if isinstance(preserved.get("table"), Mapping) else {}
        table_payload.update({"column_order": list(self.table.column_order)})
        preserved["chart"] = chart_payload
        preserved["kpi"] = kpi_payload
        preserved["table"] = table_payload
        options[VISUAL_SETTINGS_OPTION_KEY] = preserved
        return options

    def replace_chart(self, **changes: Any) -> None:
        value = replace(self.chart, **changes)
        self.chart = _validate_chart(value, strict=True)

    def replace_kpi(self, **changes: Any) -> None:
        value = replace(self.kpi, **changes)
        self.kpi = _validate_kpi(value, strict=True)

    def replace_table(self, **changes: Any) -> None:
        value = replace(self.table, **changes)
        self.table = _validate_table(value, strict=True)

    def sync_table_columns(self, selected_fields: Sequence[str]) -> None:
        selected = _unique_text(selected_fields)
        selected_set = set(selected)
        ordered = [field_id for field_id in self.table.column_order if field_id in selected_set]
        ordered.extend(field_id for field_id in selected if field_id not in ordered)
        self.table = TableVisualSettings(tuple(ordered))


def has_visual_settings(options: Mapping[str, Any] | None) -> bool:
    return isinstance(options, Mapping) and VISUAL_SETTINGS_OPTION_KEY in options


def palette_colors(palette: str) -> tuple[str, ...]:
    return CHART_PALETTES.get(palette, CHART_PALETTES["corporate"])


def transform_chart_rows(
    rows: Sequence[Mapping[str, Any]],
    settings: ChartVisualSettings,
    *,
    visualization: str,
) -> list[dict[str, Any]]:
    transformed = [dict(row) for row in rows]
    limit = settings.max_categories
    if limit is None or len(transformed) <= limit:
        return transformed
    head = transformed[:limit]
    tail = transformed[limit:]
    if settings.group_others and visualization != "line":
        other_total = 0.0
        for row in tail:
            try:
                other_total += float(row.get("value") or 0)
            except (TypeError, ValueError):
                continue
        head.append({"label": "Diğer", "value": other_total})
    return head


def normalize_column_order(columns: Sequence[str], order: Sequence[str]) -> list[str]:
    available = [str(column) for column in columns]
    available_set = set(available)
    result = [field_id for field_id in _unique_text(order) if field_id in available_set]
    result.extend(column for column in available if column not in result)
    return result


def format_kpi_value(value: Any, settings: KpiVisualSettings) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        rendered = "-" if value is None or value == "" else str(value)
    else:
        places = settings.decimal_places
        rendered = f"{float(value):,.{places}f}"
        rendered = rendered.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{settings.prefix}{rendered}{settings.suffix}"


def _boolean_setting(
    raw: Mapping[str, Any],
    key: str,
    default: bool,
    *,
    strict: bool,
) -> bool:
    if key not in raw:
        return default
    value = raw.get(key)
    if isinstance(value, bool):
        return value
    if strict:
        raise AnalysisValidationError(f"{key} görünüm ayarı boolean olmalıdır.")
    return default


def _chart_settings(value: Any, *, strict: bool) -> ChartVisualSettings:
    if value is None:
        return ChartVisualSettings()
    if not isinstance(value, Mapping):
        if strict:
            raise AnalysisValidationError("Grafik görünüm ayarları bir object/dict olmalıdır.")
        return ChartVisualSettings()
    raw = dict(value)
    settings = ChartVisualSettings(
        show_legend=_boolean_setting(raw, "show_legend", True, strict=strict),
        legend_position=str(raw.get("legend_position", "right") or "right"),
        show_values=_boolean_setting(raw, "show_values", False, strict=strict),
        palette=str(raw.get("palette", "corporate") or "corporate"),
        max_categories=raw.get("max_categories"),
        group_others=_boolean_setting(raw, "group_others", False, strict=strict),
    )
    return _validate_chart(settings, strict=strict)


def _kpi_settings(value: Any, *, strict: bool) -> KpiVisualSettings:
    if value is None:
        return KpiVisualSettings()
    if not isinstance(value, Mapping):
        if strict:
            raise AnalysisValidationError("KPI görünüm ayarları bir object/dict olmalıdır.")
        return KpiVisualSettings()
    raw = dict(value)
    try:
        decimal_places = int(raw.get("decimal_places", 2))
    except (TypeError, ValueError):
        if strict:
            raise AnalysisValidationError("Ondalık basamak geçerli bir tam sayı olmalıdır.")
        decimal_places = 2
    settings = KpiVisualSettings(
        subtitle=str(raw.get("subtitle", "") or ""),
        prefix=str(raw.get("prefix", "") or ""),
        suffix=str(raw.get("suffix", "") or ""),
        decimal_places=decimal_places,
    )
    return _validate_kpi(settings, strict=strict)


def _table_settings(
    value: Any,
    *,
    selected_table_fields: Sequence[str],
    strict: bool,
) -> TableVisualSettings:
    if value is None:
        return TableVisualSettings(tuple(_unique_text(selected_table_fields)))
    if not isinstance(value, Mapping):
        if strict:
            raise AnalysisValidationError("Tablo görünüm ayarları bir object/dict olmalıdır.")
        return TableVisualSettings(tuple(_unique_text(selected_table_fields)))
    raw_order = value.get("column_order", list(selected_table_fields))
    if not isinstance(raw_order, (list, tuple)) or not all(isinstance(item, str) for item in raw_order):
        if strict:
            raise AnalysisValidationError("Kolon sırası alan kimliklerinden oluşan bir liste olmalıdır.")
        raw_order = list(selected_table_fields)
    text_order = [item.strip() for item in raw_order if item.strip()]
    if len(text_order) != len(set(text_order)):
        if strict:
            raise AnalysisValidationError("Kolon sırasında aynı alan birden fazla kez bulunamaz.")
        text_order = _unique_text(text_order)
    selected = _unique_text(selected_table_fields)
    if selected:
        selected_set = set(selected)
        text_order = [item for item in text_order if item in selected_set]
        text_order.extend(item for item in selected if item not in text_order)
    return _validate_table(TableVisualSettings(tuple(text_order)), strict=strict)


def _validate_chart(settings: ChartVisualSettings, *, strict: bool) -> ChartVisualSettings:
    palette = settings.palette
    if palette not in PALETTE_IDS:
        if strict:
            raise AnalysisValidationError(f"Desteklenmeyen renk paleti: {palette}")
        palette = "corporate"
    legend_position = settings.legend_position
    if legend_position not in LEGEND_POSITIONS:
        if strict:
            raise AnalysisValidationError(f"Desteklenmeyen gösterge konumu: {legend_position}")
        legend_position = "right"
    maximum = settings.max_categories
    if maximum is not None:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0 or maximum > MAX_CATEGORY_LIMIT:
            if strict:
                raise AnalysisValidationError(
                    f"Maksimum kategori 1-{MAX_CATEGORY_LIMIT} arasında veya boş olmalıdır."
                )
            maximum = None
    return replace(settings, palette=palette, legend_position=legend_position, max_categories=maximum)


def _validate_kpi(settings: KpiVisualSettings, *, strict: bool) -> KpiVisualSettings:
    places = settings.decimal_places
    if places < 0 or places > MAX_DECIMAL_PLACES:
        if strict:
            raise AnalysisValidationError(
                f"Ondalık basamak 0-{MAX_DECIMAL_PLACES} arasında olmalıdır."
            )
        places = 2
    return replace(settings, decimal_places=places)


def _validate_table(settings: TableVisualSettings, *, strict: bool) -> TableVisualSettings:
    order = list(settings.column_order)
    if len(order) != len(set(order)):
        if strict:
            raise AnalysisValidationError("Kolon sırasında aynı alan birden fazla kez bulunamaz.")
        order = _unique_text(order)
    return TableVisualSettings(tuple(order))


def _unique_text(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


__all__ = [
    "AnalysisVisualSettings",
    "CHART_PALETTES",
    "ChartVisualSettings",
    "KpiVisualSettings",
    "LEGEND_POSITION_TITLES",
    "MAX_CATEGORY_LIMIT",
    "MAX_DECIMAL_PLACES",
    "PALETTE_TITLES",
    "TableVisualSettings",
    "VISUAL_SETTINGS_OPTION_KEY",
    "format_kpi_value",
    "has_visual_settings",
    "normalize_column_order",
    "palette_colors",
    "transform_chart_rows",
]
