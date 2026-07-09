from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .analysis_builder import (
    AGGREGATION_TITLES,
    FILTER_OPERATOR_TITLES,
    SORT_DIRECTION_TITLES,
    AnalysisBuilderController,
    BuilderFilterDraft,
)
from .analysis_definitions import AnalysisValidationError
from .analysis_models import AnalysisCard
from .analysis_preview_qt import AnalysisPreviewCardHost
from .analysis_renderer import analysis_result_to_card
from .analysis_visual_settings import LEGEND_POSITION_TITLES, PALETTE_TITLES


LOGGER = logging.getLogger(__name__)
CardFactory = Callable[[AnalysisCard, QWidget], QWidget]
_LIMIT_OPTIONS: tuple[int | None, ...] = (None, 5, 10, 20, 50, 100)


def _set_combo_value(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class AnalysisFilterRowWidget(QFrame):
    def __init__(
        self,
        controller: AnalysisBuilderController,
        filter_draft: BuilderFilterDraft,
        on_changed: Callable[[], None],
        on_remove: Callable[[BuilderFilterDraft], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.filter_draft = filter_draft
        self._on_changed = on_changed
        self._on_remove = on_remove
        self._refreshing = False
        self.setObjectName("analysisBuilderFilterRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        self.field_combo = QComboBox(self)
        self.field_combo.setObjectName("analysisBuilderFilterField")
        self.field_combo.setMinimumWidth(130)
        layout.addWidget(self.field_combo, 2)

        self.operator_combo = QComboBox(self)
        self.operator_combo.setObjectName("analysisBuilderFilterOperator")
        self.operator_combo.setMinimumWidth(130)
        layout.addWidget(self.operator_combo, 2)

        self.value_edit = QLineEdit(self)
        self.value_edit.setObjectName("analysisBuilderFilterValue")
        layout.addWidget(self.value_edit, 2)

        self.value_to_edit = QLineEdit(self)
        self.value_to_edit.setObjectName("analysisBuilderFilterValueTo")
        self.value_to_edit.setPlaceholderText("Bitiş")
        layout.addWidget(self.value_to_edit, 2)

        self.boolean_combo = QComboBox(self)
        self.boolean_combo.setObjectName("analysisBuilderFilterBoolean")
        self.boolean_combo.addItem("Evet", "true")
        self.boolean_combo.addItem("Hayır", "false")
        layout.addWidget(self.boolean_combo, 1)

        remove_button = QPushButton("×", self)
        remove_button.setObjectName("analysisBuilderFilterRemove")
        remove_button.setToolTip("Filtreyi kaldır")
        remove_button.setFixedWidth(30)
        remove_button.clicked.connect(lambda: self._on_remove(self.filter_draft))
        layout.addWidget(remove_button, 0)

        self.field_combo.currentIndexChanged.connect(self._field_changed)
        self.operator_combo.currentIndexChanged.connect(self._operator_changed)
        self.value_edit.textChanged.connect(self._value_changed)
        self.value_to_edit.textChanged.connect(self._value_changed)
        self.boolean_combo.currentIndexChanged.connect(self._value_changed)
        self.refresh()

    def refresh(self) -> None:
        self._refreshing = True
        try:
            self.field_combo.clear()
            for field in self.controller.filter_fields():
                self.field_combo.addItem(field.title, field.field_id)
            _set_combo_value(self.field_combo, self.filter_draft.field_id)
            if self.field_combo.currentIndex() < 0 and self.field_combo.count():
                self.field_combo.setCurrentIndex(0)
            self._sync_field_from_combo()
            self._refresh_operators()
            self.value_edit.setText(self.filter_draft.raw_value)
            self.value_to_edit.setText(self.filter_draft.raw_value_to)
            if self._current_field_type() == "boolean":
                _set_combo_value(self.boolean_combo, self.filter_draft.raw_value or "true")
            self._refresh_value_editor()
        finally:
            self._refreshing = False

    def _field_changed(self) -> None:
        if self._refreshing:
            return
        self._sync_field_from_combo()
        self.filter_draft.raw_value = ""
        self.filter_draft.raw_value_to = ""
        self._refresh_operators()
        self._refresh_value_editor()
        self._on_changed()

    def _operator_changed(self) -> None:
        if self._refreshing:
            return
        self.filter_draft.operator = str(self.operator_combo.currentData() or "")
        self.filter_draft.raw_value_to = ""
        self._refresh_value_editor()
        self._on_changed()

    def _value_changed(self) -> None:
        if self._refreshing:
            return
        if self._current_field_type() == "boolean" and self.boolean_combo.isVisible():
            self.filter_draft.raw_value = str(self.boolean_combo.currentData() or "true")
        else:
            self.filter_draft.raw_value = self.value_edit.text()
        self.filter_draft.raw_value_to = self.value_to_edit.text()
        self._on_changed()

    def _sync_field_from_combo(self) -> None:
        self.filter_draft.field_id = str(self.field_combo.currentData() or "")

    def _refresh_operators(self) -> None:
        current = self.filter_draft.operator
        self.operator_combo.blockSignals(True)
        self.operator_combo.clear()
        if self.filter_draft.field_id:
            for operator in self.controller.filter_operators(self.filter_draft.field_id):
                self.operator_combo.addItem(FILTER_OPERATOR_TITLES.get(operator, operator), operator)
        _set_combo_value(self.operator_combo, current)
        if self.operator_combo.currentIndex() < 0 and self.operator_combo.count():
            self.operator_combo.setCurrentIndex(0)
        self.filter_draft.operator = str(self.operator_combo.currentData() or "")
        self.operator_combo.blockSignals(False)

    def _refresh_value_editor(self) -> None:
        operator = self.filter_draft.operator
        field_type = self._current_field_type()
        no_value = operator in {"is_empty", "is_not_empty"}
        between = operator == "between"
        boolean = field_type == "boolean" and not no_value

        self.value_edit.setVisible(not no_value and not boolean)
        self.value_to_edit.setVisible(between and not boolean)
        self.boolean_combo.setVisible(boolean)

        if field_type == "date":
            self.value_edit.setPlaceholderText("YYYY-AA-GG")
            self.value_to_edit.setPlaceholderText("YYYY-AA-GG")
        elif field_type == "datetime":
            self.value_edit.setPlaceholderText("YYYY-AA-GG SS:DD")
            self.value_to_edit.setPlaceholderText("YYYY-AA-GG SS:DD")
        elif operator in {"in", "not_in"}:
            self.value_edit.setPlaceholderText("Değer 1, Değer 2")
        elif between:
            self.value_edit.setPlaceholderText("Başlangıç")
            self.value_to_edit.setPlaceholderText("Bitiş")
        else:
            self.value_edit.setPlaceholderText("Değer")

        if no_value:
            self.filter_draft.raw_value = ""
            self.filter_draft.raw_value_to = ""
        elif boolean:
            if self.filter_draft.raw_value not in {"true", "false"}:
                self.filter_draft.raw_value = str(self.boolean_combo.currentData() or "true")

    def _current_field_type(self) -> str:
        if not self.filter_draft.field_id:
            return "text"
        return self.controller.registry.get_field(
            self.controller.draft.dataset_id,
            self.filter_draft.field_id,
        ).field_type


class AnalysisBuilderWidget(QWidget):
    """Single-page Qt adapter for ``AnalysisBuilderController``."""

    def __init__(
        self,
        controller: AnalysisBuilderController,
        card_factory: CardFactory,
        max_table_rows: int = 100,
        parent: QWidget | None = None,
        on_saved: Callable[[object], None] | None = None,
        dashboard_is_pinned: Callable[[str], bool] | None = None,
        on_dashboard_toggle: Callable[[str], bool] | None = None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.card_factory = card_factory
        self.max_table_rows = max(1, int(max_table_rows))
        self.on_saved = on_saved
        self.dashboard_is_pinned = dashboard_is_pinned
        self.on_dashboard_toggle = on_dashboard_toggle
        self._refreshing = False
        self._filter_rows: list[AnalysisFilterRowWidget] = []
        self._preview_widget: QWidget | None = None
        self.last_definition = None
        self.last_result = None
        self.last_card: AnalysisCard | None = None
        self._build_ui()
        self.refresh_from_draft()
        self.show_initial_preview()

    def _build_ui(self) -> None:
        self.setObjectName("analysisBuilderScreen")
        self.section_order = (
            "ANALİZ",
            "HESAPLAMA",
            "FİLTRELER",
            "SIRALAMA / LİMİT",
            "GÖRÜNÜM",
            "GÖRÜNÜM AYARLARI",
        )
        self._section_labels: dict[str, QLabel] = {}
        self._visual_settings_expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 8)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.screen_title = QLabel("Analiz Oluştur", self)
        self.screen_title.setObjectName("analysisScreenTitle")
        self.screen_description = QLabel(
            "STS verinizden kendi analizinizi hazırlayın ve gerçek sonucu önizleyin.",
            self,
        )
        self.screen_description.setObjectName("analysisScreenDescription")
        self.screen_description.setWordWrap(True)
        title_box.addWidget(self.screen_title)
        title_box.addWidget(self.screen_description)
        header.addLayout(title_box, 1)
        self.reset_button = QPushButton("Yeni Analiz", self)
        self.reset_button.setObjectName("analysisBuilderSecondaryButton")
        self.reset_button.clicked.connect(self._reset)
        header.addWidget(self.reset_button, 0, Qt.AlignTop)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        outer.addLayout(body, 1)

        self.form_scroll = QScrollArea(self)
        self.form_scroll.setObjectName("analysisBuilderFormScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.form_scroll.setMinimumWidth(400)
        self.form_scroll.setMaximumWidth(460)
        form_host = QFrame(self.form_scroll)
        form_host.setObjectName("analysisBuilderSettingsPanel")
        self.form_layout = QVBoxLayout(form_host)
        self.form_layout.setContentsMargins(18, 18, 18, 18)
        self.form_layout.setSpacing(11)
        self.form_scroll.setWidget(form_host)
        body.addWidget(self.form_scroll, 0)

        self._add_section("ANALİZ")
        self.title_edit = self._line_edit("Analiz Adı")
        self.title_edit.setObjectName("analysisBuilderTitleEdit")
        self.title_edit.textChanged.connect(self._title_changed)
        self.dataset_combo = self._combo("Veri Kaynağı")
        self.dataset_combo.setObjectName("analysisBuilderDatasetCombo")
        self.dataset_combo.currentIndexChanged.connect(self._dataset_changed)

        self._add_section("HESAPLAMA")
        self.group_label, self.group_combo = self._labeled_combo("Gruplama")
        self.group_combo.setObjectName("analysisBuilderGroupCombo")
        self.group_combo.currentIndexChanged.connect(self._group_changed)
        self.aggregation_label, self.aggregation_combo = self._labeled_combo("Hesaplama")
        self.aggregation_combo.setObjectName("analysisBuilderAggregationCombo")
        self.aggregation_combo.currentIndexChanged.connect(self._aggregation_changed)
        self.measure_label, self.measure_combo = self._labeled_combo("Hesaplanacak Alan")
        self.measure_combo.setObjectName("analysisBuilderMeasureCombo")
        self.measure_combo.currentIndexChanged.connect(self._measure_changed)
        self.table_fields_label = self._field_label("Tabloda Gösterilecek Alanlar")
        self.table_fields = QListWidget(form_host)
        self.table_fields.setObjectName("analysisBuilderTableFields")
        self.table_fields.setMinimumHeight(150)
        self.table_fields.itemChanged.connect(self._table_fields_changed)
        self.form_layout.addWidget(self.table_fields_label)
        self.form_layout.addWidget(self.table_fields)

        self._add_section("FİLTRELER")
        self.filter_rows_host = QWidget(form_host)
        self.filter_rows_layout = QVBoxLayout(self.filter_rows_host)
        self.filter_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_rows_layout.setSpacing(6)
        self.form_layout.addWidget(self.filter_rows_host)
        self.add_filter_button = QPushButton("+ Filtre Ekle", form_host)
        self.add_filter_button.setObjectName("analysisBuilderSecondaryButton")
        self.add_filter_button.clicked.connect(self._add_filter)
        self.form_layout.addWidget(self.add_filter_button)

        self._add_section("SIRALAMA / LİMİT")
        self.sort_label, self.sort_combo = self._labeled_combo("Sıralama Alanı")
        self.sort_combo.setObjectName("analysisBuilderSortCombo")
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        self.sort_direction_label, self.sort_direction_combo = self._labeled_combo("Sıra")
        self.sort_direction_combo.setObjectName("analysisBuilderSortDirectionCombo")
        self.sort_direction_combo.currentIndexChanged.connect(self._sort_direction_changed)
        self.limit_label, self.limit_combo = self._labeled_combo("Sonuç Limiti")
        self.limit_combo.setObjectName("analysisBuilderLimitCombo")
        self.limit_combo.currentIndexChanged.connect(self._limit_changed)

        self._add_section("GÖRÜNÜM")
        self.visualization_combo = self._combo("Görünüm")
        self.visualization_combo.setObjectName("analysisBuilderVisualizationCombo")
        self.visualization_combo.currentIndexChanged.connect(self._visualization_changed)

        self._add_section("GÖRÜNÜM AYARLARI")
        self.visual_settings_group = self._build_visual_settings_section(form_host)
        self.form_layout.addWidget(self.visual_settings_group)

        self.form_layout.addStretch(1)
        self.save_status = QLabel("", form_host)
        self.save_status.setObjectName("analysisBuilderSaveStatus")
        self.save_status.setWordWrap(True)
        self.form_layout.addWidget(self.save_status)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.preview_button = QPushButton("Önizle", form_host)
        self.preview_button.setObjectName("analysisBuilderPreviewButton")
        self.preview_button.clicked.connect(self.preview)
        action_row.addWidget(self.preview_button, 1)
        self.dashboard_button = QPushButton("Dashboard'a Ekle", form_host)
        self.dashboard_button.setObjectName("analysisBuilderDashboardButton")
        self.dashboard_button.clicked.connect(self._toggle_dashboard)
        action_row.addWidget(self.dashboard_button, 1)
        self.save_button = QPushButton("Kaydet", form_host)
        self.save_button.setObjectName("analysisBuilderSaveButton")
        self.save_button.clicked.connect(self.save)
        action_row.addWidget(self.save_button, 1)
        self.form_layout.addLayout(action_row)

        preview_panel = QFrame(self)
        preview_panel.setObjectName("analysisBuilderPreviewPanel")
        preview_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)
        preview_title = QLabel("ÖNİZLEME", preview_panel)
        preview_title.setObjectName("analysisBuilderSectionTitle")
        preview_layout.addWidget(preview_title)
        self.preview_guidance = QLabel("", preview_panel)
        self.preview_guidance.setObjectName("analysisBuilderPreviewGuidance")
        self.preview_guidance.setWordWrap(True)
        self.preview_guidance.hide()
        preview_layout.addWidget(self.preview_guidance)
        self.preview_host = QFrame(preview_panel)
        self.preview_host.setObjectName("analysisBuilderPreviewHost")
        self.preview_host_layout = QVBoxLayout(self.preview_host)
        self.preview_host_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_host_layout.setSpacing(0)
        preview_layout.addWidget(self.preview_host, 1)
        body.addWidget(preview_panel, 1)

    def _add_section(self, text: str) -> QLabel:
        self.form_layout.addSpacing(4 if self._section_labels else 0)
        label = self._section_label(text)
        self._section_labels[text] = label
        self.form_layout.addWidget(label)
        return label

    def _build_visual_settings_section(self, parent: QWidget) -> QFrame:
        host = QFrame(parent)
        host.setObjectName("analysisBuilderVisualSettings")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(7)

        self.visual_settings_toggle = QPushButton("Görünüm Ayarlarını Göster  ▸", host)
        self.visual_settings_toggle.setObjectName("analysisBuilderVisualSettingsToggle")
        self.visual_settings_toggle.setCheckable(True)
        self.visual_settings_toggle.setChecked(False)
        self.visual_settings_toggle.clicked.connect(self._toggle_visual_settings)
        layout.addWidget(self.visual_settings_toggle)

        self.visual_settings_content = QFrame(host)
        self.visual_settings_content.setObjectName("analysisBuilderVisualSettingsContent")
        visual_layout = QVBoxLayout(self.visual_settings_content)
        visual_layout.setContentsMargins(0, 4, 0, 0)
        visual_layout.setSpacing(7)

        self.chart_settings_host = QFrame(self.visual_settings_content)
        self.chart_settings_host.setObjectName("analysisBuilderChartSettings")
        chart_settings_layout = QVBoxLayout(self.chart_settings_host)
        chart_settings_layout.setContentsMargins(0, 0, 0, 0)
        chart_settings_layout.setSpacing(6)
        self.chart_show_legend = QCheckBox("Göstergeyi Göster", self.chart_settings_host)
        self.chart_show_legend.setObjectName("analysisBuilderChartShowLegend")
        self.chart_show_legend.stateChanged.connect(self._chart_visual_changed)
        chart_settings_layout.addWidget(self.chart_show_legend)
        legend_row = QHBoxLayout()
        legend_row.addWidget(self._field_label("Gösterge Konumu"), 1)
        self.chart_legend_position = QComboBox(self.chart_settings_host)
        self.chart_legend_position.setObjectName("analysisBuilderChartLegendPosition")
        for value, title in LEGEND_POSITION_TITLES.items():
            self.chart_legend_position.addItem(title, value)
        self.chart_legend_position.currentIndexChanged.connect(self._chart_visual_changed)
        legend_row.addWidget(self.chart_legend_position, 1)
        chart_settings_layout.addLayout(legend_row)
        self.chart_show_values = QCheckBox("Değerleri Göster", self.chart_settings_host)
        self.chart_show_values.setObjectName("analysisBuilderChartShowValues")
        self.chart_show_values.stateChanged.connect(self._chart_visual_changed)
        chart_settings_layout.addWidget(self.chart_show_values)
        palette_row = QHBoxLayout()
        palette_row.addWidget(self._field_label("Renk Paleti"), 1)
        self.chart_palette = QComboBox(self.chart_settings_host)
        self.chart_palette.setObjectName("analysisBuilderChartPalette")
        for value, title in PALETTE_TITLES.items():
            self.chart_palette.addItem(title, value)
        self.chart_palette.currentIndexChanged.connect(self._chart_visual_changed)
        palette_row.addWidget(self.chart_palette, 1)
        chart_settings_layout.addLayout(palette_row)
        max_row = QHBoxLayout()
        max_row.addWidget(self._field_label("Maksimum Kategori"), 1)
        self.chart_max_categories = QSpinBox(self.chart_settings_host)
        self.chart_max_categories.setObjectName("analysisBuilderChartMaxCategories")
        self.chart_max_categories.setRange(0, 1000)
        self.chart_max_categories.setSpecialValueText("Sınırsız")
        self.chart_max_categories.valueChanged.connect(self._chart_visual_changed)
        max_row.addWidget(self.chart_max_categories, 1)
        chart_settings_layout.addLayout(max_row)
        self.chart_group_others = QCheckBox('Kalanları "Diğer" Olarak Grupla', self.chart_settings_host)
        self.chart_group_others.setObjectName("analysisBuilderChartGroupOthers")
        self.chart_group_others.stateChanged.connect(self._chart_visual_changed)
        chart_settings_layout.addWidget(self.chart_group_others)
        visual_layout.addWidget(self.chart_settings_host)

        self.kpi_settings_host = QFrame(self.visual_settings_content)
        self.kpi_settings_host.setObjectName("analysisBuilderKpiSettings")
        kpi_settings_layout = QVBoxLayout(self.kpi_settings_host)
        kpi_settings_layout.setContentsMargins(0, 0, 0, 0)
        kpi_settings_layout.setSpacing(6)
        self.kpi_subtitle = QLineEdit(self.kpi_settings_host)
        self.kpi_subtitle.setObjectName("analysisBuilderKpiSubtitle")
        self.kpi_subtitle.setPlaceholderText("Alt Başlık")
        self.kpi_subtitle.textChanged.connect(self._kpi_visual_changed)
        kpi_settings_layout.addWidget(self._field_label("Alt Başlık"))
        kpi_settings_layout.addWidget(self.kpi_subtitle)
        prefix_suffix_row = QHBoxLayout()
        prefix_box = QVBoxLayout()
        prefix_box.addWidget(self._field_label("Ön Ek"))
        self.kpi_prefix = QLineEdit(self.kpi_settings_host)
        self.kpi_prefix.setObjectName("analysisBuilderKpiPrefix")
        self.kpi_prefix.textChanged.connect(self._kpi_visual_changed)
        prefix_box.addWidget(self.kpi_prefix)
        suffix_box = QVBoxLayout()
        suffix_box.addWidget(self._field_label("Son Ek"))
        self.kpi_suffix = QLineEdit(self.kpi_settings_host)
        self.kpi_suffix.setObjectName("analysisBuilderKpiSuffix")
        self.kpi_suffix.textChanged.connect(self._kpi_visual_changed)
        suffix_box.addWidget(self.kpi_suffix)
        prefix_suffix_row.addLayout(prefix_box, 1)
        prefix_suffix_row.addLayout(suffix_box, 1)
        kpi_settings_layout.addLayout(prefix_suffix_row)
        decimals_row = QHBoxLayout()
        decimals_row.addWidget(self._field_label("Ondalık Basamak"), 1)
        self.kpi_decimal_places = QSpinBox(self.kpi_settings_host)
        self.kpi_decimal_places.setObjectName("analysisBuilderKpiDecimalPlaces")
        self.kpi_decimal_places.setRange(0, 6)
        self.kpi_decimal_places.valueChanged.connect(self._kpi_visual_changed)
        decimals_row.addWidget(self.kpi_decimal_places, 1)
        kpi_settings_layout.addLayout(decimals_row)
        visual_layout.addWidget(self.kpi_settings_host)

        self.table_settings_host = QFrame(self.visual_settings_content)
        self.table_settings_host.setObjectName("analysisBuilderTableSettings")
        table_settings_layout = QVBoxLayout(self.table_settings_host)
        table_settings_layout.setContentsMargins(0, 0, 0, 0)
        table_settings_layout.setSpacing(6)
        table_settings_layout.addWidget(self._field_label("Kolon Sırası"))
        self.table_column_order = QListWidget(self.table_settings_host)
        self.table_column_order.setObjectName("analysisBuilderTableColumnOrder")
        self.table_column_order.setMinimumHeight(110)
        table_settings_layout.addWidget(self.table_column_order)
        table_order_actions = QHBoxLayout()
        self.table_column_up = QPushButton("Yukarı", self.table_settings_host)
        self.table_column_up.setObjectName("analysisBuilderTableColumnUp")
        self.table_column_up.clicked.connect(lambda: self._move_table_column(-1))
        self.table_column_down = QPushButton("Aşağı", self.table_settings_host)
        self.table_column_down.setObjectName("analysisBuilderTableColumnDown")
        self.table_column_down.clicked.connect(lambda: self._move_table_column(1))
        table_order_actions.addWidget(self.table_column_up)
        table_order_actions.addWidget(self.table_column_down)
        table_settings_layout.addLayout(table_order_actions)
        visual_layout.addWidget(self.table_settings_host)

        layout.addWidget(self.visual_settings_content)
        self._set_visual_settings_expanded(False)
        return host

    def _toggle_visual_settings(self) -> None:
        self._set_visual_settings_expanded(self.visual_settings_toggle.isChecked())

    def _set_visual_settings_expanded(self, expanded: bool) -> None:
        self._visual_settings_expanded = bool(expanded)
        if hasattr(self, "visual_settings_content"):
            self.visual_settings_content.setVisible(self._visual_settings_expanded)
        if hasattr(self, "visual_settings_toggle"):
            self.visual_settings_toggle.setChecked(self._visual_settings_expanded)
            self.visual_settings_toggle.setText(
                "Görünüm Ayarlarını Gizle  ▾"
                if self._visual_settings_expanded
                else "Görünüm Ayarlarını Göster  ▸"
            )

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("analysisBuilderSectionTitle")
        return label

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("analysisBuilderFieldLabel")
        return label

    def _line_edit(self, label_text: str) -> QLineEdit:
        label = self._field_label(label_text)
        self.form_layout.addWidget(label)
        line_edit = QLineEdit(self)
        self.form_layout.addWidget(line_edit)
        return line_edit

    def _combo(self, label_text: str) -> QComboBox:
        _label, combo = self._labeled_combo(label_text)
        return combo

    def _labeled_combo(self, label_text: str) -> tuple[QLabel, QComboBox]:
        label = self._field_label(label_text)
        combo = QComboBox(self)
        self.form_layout.addWidget(label)
        self.form_layout.addWidget(combo)
        return label, combo

    def refresh_from_draft(self) -> None:
        self._refreshing = True
        try:
            draft = self.controller.draft
            self.title_edit.setText(draft.title)

            self.dataset_combo.clear()
            for dataset in self.controller.datasets():
                self.dataset_combo.addItem(dataset.title, dataset.dataset_id)
            _set_combo_value(self.dataset_combo, draft.dataset_id)

            self.visualization_combo.clear()
            for option in self.controller.visualization_options():
                self.visualization_combo.addItem(option.title, option.visualization_id)
            _set_combo_value(self.visualization_combo, draft.visualization)

            self._refresh_group_combo()
            self._refresh_aggregation_combo()
            self._refresh_measure_combo()
            self._refresh_table_fields()
            self._refresh_filter_rows()
            self._refresh_sort_controls()
            self._refresh_limit_combo()
            self._refresh_visual_settings()
            self._refresh_mode_visibility()
            self._refresh_document_state()
        finally:
            self._refreshing = False

    def preview(self) -> None:
        try:
            definition, result = self.controller.preview()
            card = analysis_result_to_card(definition, result)
            rendered_card = self.card_factory(card, self.preview_host)
            card_widget = AnalysisPreviewCardHost(card, rendered_card, self.preview_host)
        except AnalysisValidationError as exc:
            self.show_preview_message(str(exc), error=True)
            return
        except Exception:
            LOGGER.exception("Custom analysis preview failed")
            self.show_preview_message("Analiz önizlenirken beklenmeyen bir hata oluştu.", error=True)
            return
        self.last_definition = definition
        self.last_result = result
        self.last_card = card
        self._refresh_preview_guidance(definition, result)
        self._replace_preview_widget(card_widget)

    def _refresh_preview_guidance(self, definition, result) -> None:
        warning = ""
        if definition.visualization == "donut" and len(result.rows) > 12:
            warning = (
                "Donut görünümü çok fazla kategori içeriyor. "
                "Yatay çubuk daha okunabilir olabilir."
            )
        self.preview_guidance.setText(warning)
        self.preview_guidance.setVisible(bool(warning))

    def save(self) -> None:
        editing = self.controller.is_editing
        try:
            saved = self.controller.save_current()
        except AnalysisValidationError as exc:
            self.save_status.setText(str(exc))
            return
        except Exception:
            LOGGER.exception("Custom analysis save failed")
            self.save_status.setText("Analiz kaydedilemedi. Mevcut dosya korunuyor.")
            return
        self.refresh_from_draft()
        self.save_status.setText(
            "Değişiklikler kaydedildi." if editing else "Analiz kaydedildi."
        )
        if self.on_saved is not None:
            self.on_saved(saved)

    def _toggle_dashboard(self) -> None:
        analysis_id = self.controller.current_saved_analysis_id
        if not analysis_id:
            self.save_status.setText("Dashboard'a eklemek için önce analizi kaydedin.")
            return
        if self.on_dashboard_toggle is None:
            self.save_status.setText("Dashboard işlemi bu ekranda kullanılamıyor.")
            return
        if self.on_dashboard_toggle(analysis_id):
            self.save_status.clear()
            self._refresh_document_state()

    def show_initial_preview(self) -> None:
        self.show_preview_message("Analiz ayarlarını seçin ve Önizle'ye basın.")

    def show_data_refreshed_notice(self) -> None:
        self.show_preview_message("Veri yenilendi. Analizi tekrar önizleyin.")

    def show_template_loaded_notice(self) -> None:
        self.show_preview_message(
            "Hazır analiz ayarları yüklendi. Değiştirip Önizle'ye basın."
        )

    @property
    def visual_settings_expanded(self) -> bool:
        return self._visual_settings_expanded

    def focus_visual_settings(self) -> None:
        """Expand and scroll the existing visual-settings section into view."""

        self._set_visual_settings_expanded(True)
        self.visual_settings_toggle.setFocus(Qt.OtherFocusReason)
        self.form_scroll.ensureWidgetVisible(self.visual_settings_group, 0, 24)
        QTimer.singleShot(
            0,
            lambda: self.form_scroll.ensureWidgetVisible(
                self.visual_settings_group,
                0,
                24,
            ),
        )

    def show_preview_message(self, text: str, *, error: bool = False) -> None:
        self.last_definition = None
        self.last_result = None
        self.last_card = None
        self.preview_guidance.clear()
        self.preview_guidance.hide()
        label = QLabel(text, self.preview_host)
        label.setObjectName("analysisBuilderPreviewError" if error else "analysisBuilderPreviewInfo")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        self._replace_preview_widget(label)

    def _replace_preview_widget(self, widget: QWidget) -> None:
        if self._preview_widget is not None:
            self.preview_host_layout.removeWidget(self._preview_widget)
            self._preview_widget.deleteLater()
        self._preview_widget = widget
        self.preview_host_layout.addWidget(widget, 1)

    def _reset(self) -> None:
        self.controller.reset()
        self.refresh_from_draft()
        self.save_status.clear()
        self.show_initial_preview()

    def _on_draft_changed(self) -> None:
        self.controller.mark_changed()
        self.save_status.clear()
        self._refresh_document_state()
        if self.last_definition is not None:
            self.show_preview_message("Analiz ayarları değişti. Tekrar Önizle'ye basın.")

    def _refresh_document_state(self) -> None:
        editing = self.controller.is_editing
        self.screen_title.setText("Analizi Düzenle" if editing else "Analiz Oluştur")
        self.screen_description.setText(
            self.controller.draft.title
            if editing
            else "STS verinizden kendi analizinizi hazırlayın ve gerçek sonucu önizleyin."
        )
        self.save_button.setText("Değişiklikleri Kaydet" if editing else "Kaydet")
        self.save_button.setEnabled(self.controller.dirty)
        analysis_id = self.controller.current_saved_analysis_id
        pinned = bool(
            analysis_id
            and self.dashboard_is_pinned is not None
            and self.dashboard_is_pinned(analysis_id)
        )
        self.dashboard_button.setText(
            "Dashboard'dan Kaldır" if pinned else "Dashboard'a Ekle"
        )
        self.dashboard_button.setProperty("dashboardPinned", pinned)
        self.dashboard_button.style().unpolish(self.dashboard_button)
        self.dashboard_button.style().polish(self.dashboard_button)

    def _title_changed(self, text: str) -> None:
        if not self._refreshing and text != self.controller.draft.title:
            self.controller.draft.title = text
            self._on_draft_changed()

    def _dataset_changed(self) -> None:
        if self._refreshing:
            return
        dataset_id = str(self.dataset_combo.currentData() or "")
        if dataset_id == self.controller.draft.dataset_id:
            return
        self.controller.set_dataset(dataset_id)
        self.refresh_from_draft()
        self._on_draft_changed()

    def _visualization_changed(self) -> None:
        if self._refreshing:
            return
        visualization = str(self.visualization_combo.currentData() or "")
        if visualization == self.controller.draft.visualization:
            return
        self.controller.set_visualization(visualization)
        self.refresh_from_draft()
        self._on_draft_changed()

    def _group_changed(self) -> None:
        if self._refreshing:
            return
        value = str(self.group_combo.currentData() or "")
        if value == self.controller.draft.group_field:
            return
        self.controller.draft.group_field = value
        self._refresh_sort_controls()
        self._on_draft_changed()

    def _aggregation_changed(self) -> None:
        if self._refreshing:
            return
        aggregation = str(self.aggregation_combo.currentData() or "")
        if aggregation == self.controller.draft.aggregation:
            return
        self.controller.set_aggregation(aggregation)
        self._refreshing = True
        try:
            self._refresh_measure_combo()
        finally:
            self._refreshing = False
        self._on_draft_changed()

    def _measure_changed(self) -> None:
        if self._refreshing:
            return
        value = str(self.measure_combo.currentData() or "")
        if value == self.controller.draft.measure_field:
            return
        self.controller.draft.measure_field = value
        self._on_draft_changed()

    def _table_fields_changed(self) -> None:
        if self._refreshing:
            return
        selected = [
            str(self.table_fields.item(index).data(Qt.UserRole))
            for index in range(self.table_fields.count())
            if self.table_fields.item(index).checkState() == Qt.Checked
        ]
        if selected == self.controller.draft.selected_table_fields:
            return
        self.controller.draft.selected_table_fields = selected
        self.controller.sync_table_visual_settings()
        self._refresh_sort_controls()
        self._refresh_visual_settings()
        self._on_draft_changed()

    def _sort_changed(self) -> None:
        if self._refreshing:
            return
        value = str(self.sort_combo.currentData() or "")
        if value == self.controller.draft.sort_field:
            return
        self.controller.draft.sort_field = value
        has_sort = bool(value)
        self.sort_direction_label.setEnabled(has_sort)
        self.sort_direction_combo.setEnabled(has_sort)
        self._on_draft_changed()

    def _sort_direction_changed(self) -> None:
        if self._refreshing:
            return
        value = str(self.sort_direction_combo.currentData() or "desc")
        if value == self.controller.draft.sort_direction:
            return
        self.controller.draft.sort_direction = value
        self._on_draft_changed()

    def _limit_changed(self) -> None:
        if self._refreshing:
            return
        value = self.limit_combo.currentData()
        if value == self.controller.draft.limit:
            return
        self.controller.draft.limit = value
        self._on_draft_changed()

    def _chart_visual_changed(self) -> None:
        if self._refreshing:
            return
        self.controller.update_chart_visual_settings(
            show_legend=self.chart_show_legend.isChecked(),
            legend_position=str(self.chart_legend_position.currentData() or "right"),
            show_values=self.chart_show_values.isChecked(),
            palette=str(self.chart_palette.currentData() or "corporate"),
            max_categories=self.chart_max_categories.value() or None,
            group_others=self.chart_group_others.isChecked(),
        )
        self._refresh_visual_settings_visibility()
        self._on_draft_changed()

    def _kpi_visual_changed(self) -> None:
        if self._refreshing:
            return
        self.controller.update_kpi_visual_settings(
            subtitle=self.kpi_subtitle.text(),
            prefix=self.kpi_prefix.text(),
            suffix=self.kpi_suffix.text(),
            decimal_places=self.kpi_decimal_places.value(),
            decimal_places_explicit=self.sender() is self.kpi_decimal_places,
        )
        self._on_draft_changed()

    def _move_table_column(self, delta: int) -> None:
        if self._refreshing:
            return
        row = self.table_column_order.currentRow()
        target = row + delta
        order = list(self.controller.visual_settings().table.column_order)
        if row < 0 or target < 0 or target >= len(order):
            return
        order[row], order[target] = order[target], order[row]
        self.controller.set_table_column_order(order)
        self._refreshing = True
        try:
            self._refresh_visual_settings()
            self.table_column_order.setCurrentRow(target)
        finally:
            self._refreshing = False
        self._on_draft_changed()

    def _refresh_visual_settings(self) -> None:
        settings = self.controller.visual_settings()
        self.chart_show_legend.setChecked(settings.chart.show_legend)
        _set_combo_value(self.chart_legend_position, settings.chart.legend_position)
        self.chart_show_values.setChecked(settings.chart.show_values)
        _set_combo_value(self.chart_palette, settings.chart.palette)
        self.chart_max_categories.setValue(settings.chart.max_categories or 0)
        self.chart_group_others.setChecked(settings.chart.group_others)

        self.kpi_subtitle.setText(settings.kpi.subtitle)
        self.kpi_prefix.setText(settings.kpi.prefix)
        self.kpi_suffix.setText(settings.kpi.suffix)
        self.kpi_decimal_places.setValue(settings.kpi.decimal_places)

        self.table_column_order.clear()
        for field_id in settings.table.column_order:
            try:
                title = self.controller.registry.get_field(self.controller.draft.dataset_id, field_id).title
            except Exception:
                title = field_id
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, field_id)
            self.table_column_order.addItem(item)
        self._refresh_visual_settings_visibility()

    def _refresh_visual_settings_visibility(self) -> None:
        visualization = self.controller.draft.visualization
        chart_mode = visualization in {"bar", "horizontal_bar", "donut", "line"}
        self.chart_settings_host.setVisible(chart_mode)
        self.kpi_settings_host.setVisible(visualization == "kpi")
        self.table_settings_host.setVisible(visualization == "table")
        line_mode = visualization == "line"
        legend_enabled = self.chart_show_legend.isChecked() and not line_mode
        self.chart_show_legend.setEnabled(not line_mode)
        self.chart_legend_position.setEnabled(legend_enabled)
        self.chart_group_others.setEnabled(not line_mode and bool(self.chart_max_categories.value()))

    def _filters_changed(self) -> None:
        self._on_draft_changed()

    def _add_filter(self) -> None:
        self.controller.add_filter()
        self._refresh_filter_rows()
        self._on_draft_changed()

    def _remove_filter(self, filter_draft: BuilderFilterDraft) -> None:
        self.controller.remove_filter(filter_draft)
        self._refresh_filter_rows()
        self._on_draft_changed()

    def _refresh_group_combo(self) -> None:
        current = self.controller.draft.group_field
        self.group_combo.clear()
        self.group_combo.addItem("— Seçin —", "")
        for field in self.controller.group_fields():
            self.group_combo.addItem(field.title, field.field_id)
        _set_combo_value(self.group_combo, current)

    def _refresh_aggregation_combo(self) -> None:
        current = self.controller.draft.aggregation
        self.aggregation_combo.clear()
        for aggregation in self.controller.aggregation_options():
            self.aggregation_combo.addItem(AGGREGATION_TITLES.get(aggregation, aggregation), aggregation)
        _set_combo_value(self.aggregation_combo, current)

    def _refresh_measure_combo(self) -> None:
        draft = self.controller.draft
        current = draft.measure_field
        self.measure_combo.clear()
        fields = self.controller.measure_fields(draft.aggregation)
        if not fields:
            self.measure_combo.addItem("Gerekli değil", "")
        else:
            self.measure_combo.addItem("— Seçin —", "")
            for field in fields:
                self.measure_combo.addItem(field.title, field.field_id)
        _set_combo_value(self.measure_combo, current)
        draft.measure_field = str(self.measure_combo.currentData() or "")
        requires_field = bool(fields)
        self.measure_label.setEnabled(requires_field)
        self.measure_combo.setEnabled(requires_field)

    def _refresh_table_fields(self) -> None:
        selected = set(self.controller.draft.selected_table_fields)
        self.table_fields.blockSignals(True)
        self.table_fields.clear()
        for field in self.controller.table_fields():
            item = QListWidgetItem(field.title)
            item.setData(Qt.UserRole, field.field_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if field.field_id in selected else Qt.Unchecked)
            self.table_fields.addItem(item)
        self.table_fields.blockSignals(False)

    def _refresh_filter_rows(self) -> None:
        _clear_layout(self.filter_rows_layout)
        self._filter_rows = []
        for filter_draft in self.controller.draft.filters:
            row = AnalysisFilterRowWidget(
                self.controller,
                filter_draft,
                self._filters_changed,
                self._remove_filter,
                self.filter_rows_host,
            )
            self._filter_rows.append(row)
            self.filter_rows_layout.addWidget(row)

    def _refresh_sort_controls(self) -> None:
        draft = self.controller.draft
        current = draft.sort_field
        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        self.sort_combo.addItem("Sıralama Yok", "")
        for field_id, title in self.controller.sort_options():
            self.sort_combo.addItem(title, field_id)
        _set_combo_value(self.sort_combo, current)
        draft.sort_field = str(self.sort_combo.currentData() or "")
        self.sort_combo.blockSignals(False)

        self.sort_direction_combo.blockSignals(True)
        self.sort_direction_combo.clear()
        for direction, title in SORT_DIRECTION_TITLES.items():
            self.sort_direction_combo.addItem(title, direction)
        _set_combo_value(self.sort_direction_combo, draft.sort_direction)
        self.sort_direction_combo.blockSignals(False)
        has_sort = bool(draft.sort_field)
        self.sort_direction_label.setEnabled(has_sort)
        self.sort_direction_combo.setEnabled(has_sort)

    def _refresh_limit_combo(self) -> None:
        current = self.controller.draft.limit
        self.limit_combo.clear()
        values = list(_LIMIT_OPTIONS)
        if self.max_table_rows not in values:
            values.append(self.max_table_rows)
        for value in values:
            self.limit_combo.addItem("Tümü" if value is None else str(value), value)
        if current not in values and current is not None:
            self.limit_combo.addItem(str(current), current)
        index = self.limit_combo.findData(current)
        if index >= 0:
            self.limit_combo.setCurrentIndex(index)

    def _refresh_mode_visibility(self) -> None:
        visualization = self.controller.draft.visualization
        table_mode = visualization == "table"
        aggregation_mode = not table_mode
        chart_mode = aggregation_mode and visualization != "kpi"

        self.group_label.setVisible(chart_mode)
        self.group_combo.setVisible(chart_mode)
        self.aggregation_label.setVisible(aggregation_mode)
        self.aggregation_combo.setVisible(aggregation_mode)
        self.measure_label.setVisible(aggregation_mode)
        self.measure_combo.setVisible(aggregation_mode)
        self.table_fields_label.setVisible(table_mode)
        self.table_fields.setVisible(table_mode)

        sort_visible = visualization != "kpi"
        self.sort_label.setVisible(sort_visible)
        self.sort_combo.setVisible(sort_visible)
        self.sort_direction_label.setVisible(sort_visible)
        self.sort_direction_combo.setVisible(sort_visible)
        self.limit_label.setVisible(sort_visible)
        self.limit_combo.setVisible(sort_visible)
        self._refresh_visual_settings_visibility()


__all__ = ["AnalysisBuilderWidget", "AnalysisFilterRowWidget"]
