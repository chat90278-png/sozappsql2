from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PySide6.QtCore import QPointF, QRectF, QThread, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .analysis_builder import ANALYSIS_BUILDER_ID, AnalysisBuilderController
from .analysis_builder_qt import AnalysisBuilderWidget
from .analysis_cards import get_builtin_analysis_for_prepared_card
from .analysis_custom_library import MY_ANALYSES_ID, CustomAnalysisLibraryController
from .analysis_custom_dashboard import (
    CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
    CustomAnalysisDashboardController,
)
from .analysis_library_qt import AnalysisLibraryWidget
from .analysis_dashboard_canvas import DashboardCanvas, DashboardQuickAction
from .analysis_excel_export import (
    DashboardExcelExportError,
    DashboardExportCollector,
    export_dashboard_collection_excel,
    suggested_dashboard_excel_path,
)
from .analysis_excel_export_qt import DashboardExcelExportWorker
from .analysis_dashboard_edit import DashboardEditSession
from .analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspace,
    DashboardWorkspaceError,
    DashboardWorkspaceStore,
    source_workspace_key,
)
from .analysis_definitions import AnalysisDefinition
from .analysis_models import AnalysisCard, CardSize, CardType, ChartType, DashboardItem, VisualSettings
from .analysis_repository import AnalysisRepository, FileAnalysisRepository
from .analysis_settings import DEFAULT_SETTINGS
from .analysis_utils import parse_date
from .analysis_widgets import chart_series, table_rows
from .analysis_visual_settings import (
    AnalysisVisualSettings,
    ChartVisualSettings,
    format_kpi_value,
    palette_colors,
)
from .analysis_window import AnalysisWindow


_COLUMN_TITLES = {
    "platform": "Platform",
    "contract_no": "Sözleşme No",
    "contract_type": "Sözleşme Tipi",
    "entity": "Varlık",
    "name": "Ad",
    "system_name": "Sistem",
    "due_date": "Termin",
    "days": "Gün",
    "status": "Durum",
    "contract_count": "Sözleşme",
    "completed_contract_count": "Tamamlanan Sözleşme",
    "acceptance_count": "Teslimat",
    "completed_acceptance_count": "Tamamlanan Teslimat",
    "planned_acceptance_date": "Planlanan Kabul",
    "acceptance_date": "Teslimat Tarihi",
    "planned_total": "Planlanan",
    "delivered_total": "Teslim Edilen",
    "completed": "Tamamlandı",
    "severity": "Seviye",
    "field": "Alan",
    "issue": "Sorun",
    "message": "Açıklama",
    "date_field": "Termin Alanı",
    "raw_date_value": "Ham Tarih",
    "date_status": "Tarih Durumu",
    "source_type": "Kaynak Türü",
}

_CHART_PALETTE = palette_colors("corporate")

_ANALYSIS_STYLE = """
QMainWindow#analysisCenterWindow, QWidget#analysisCenterRoot {
    background:#e8eef5;
    color:#0f172a;
    font-family:'Segoe UI', Arial;
    font-size:13px;
}
QFrame#analysisTopBar {
    background:#263341;
    border-radius:10px;
}
QLabel#analysisTitle {
    color:#ffffff;
    background:transparent;
    font-size:20px;
    font-weight:900;
}
QLabel#analysisSubtitle {
    color:#d7e3ff;
    background:transparent;
    font-size:11px;
    font-weight:700;
}
QLabel#analysisSourcePill {
    color:#047857;
    background:#dcfce7;
    border-radius:8px;
    padding:6px 10px;
    font-weight:800;
}
QPushButton#analysisRefreshButton {
    background:#1f5be3;
    color:#ffffff;
    border:0;
    border-radius:7px;
    padding:8px 14px;
    font-weight:800;
}
QPushButton#analysisRefreshButton:hover { background:#174bc4; }
QPushButton#analysisPinButton, QPushButton#analysisCardAction {
    background:#f8fafc;
    color:#334155;
    border:1px solid #cbd5e1;
    border-radius:6px;
    padding:5px 8px;
    font-size:10px;
    font-weight:800;
}
QPushButton#analysisPinButton:hover, QPushButton#analysisCardAction:hover {
    background:#eff6ff;
    color:#1d4ed8;
    border-color:#93c5fd;
}
QPushButton#analysisPinButton[dashboardPinned="true"] {
    background:#dbeafe;
    color:#1d4ed8;
    border-color:#93c5fd;
}
QPushButton#analysisRemoveAction {
    background:#fff7ed;
    color:#c2410c;
    border:1px solid #fdba74;
    border-radius:6px;
    padding:5px 8px;
    font-size:10px;
    font-weight:800;
}
QFrame#analysisDashboardCardFrame {
    background:transparent;
    border:0;
}
QFrame#analysisDashboardCardFrame[dashboardEditing="true"] {
    background:#f8fafc;
    border:1px solid #cbd5e1;
    border-radius:10px;
}
QFrame#analysisDashboardCardFrame[dashboardEditing="true"][dashboardActive="true"] {
    background:#f8fbff;
    border:2px solid #60a5fa;
}
QFrame#analysisDashboardEditBar {
    background:#f1f5f9;
    border:0;
    border-bottom:1px solid #e2e8f0;
}
QLabel#analysisDashboardDragHandle {
    color:#64748b;
    background:transparent;
    border-radius:6px;
    font-size:15px;
    font-weight:900;
}
QLabel#analysisDashboardDragHandle:hover {
    color:#1d4ed8;
    background:#e2e8f0;
}
QLabel#analysisDashboardEditTitle {
    color:#334155;
    background:transparent;
    font-size:10px;
    font-weight:800;
}
QPushButton#analysisDashboardRemoveButton {
    color:#64748b;
    background:transparent;
    border:0;
    border-radius:7px;
    font-weight:900;
}
QPushButton#analysisDashboardRemoveButton:hover {
    color:#b91c1c;
    background:#fee2e2;
}
QLabel#analysisDashboardResizeHandle {
    color:#64748b;
    background:transparent;
    border:0;
    font-size:12px;
    font-weight:900;
    padding:0 2px 2px 0;
}
QLabel#analysisDashboardResizeHandle:hover {
    color:#1d4ed8;
    background:#e2e8f0;
    border-radius:8px;
}
QToolButton#analysisDashboardQuickActionButton {
    color:#475569;
    background:rgba(248, 250, 252, 220);
    border:1px solid #d8e2ed;
    border-radius:8px;
    padding:0;
    font-size:17px;
    font-weight:900;
}
QToolButton#analysisDashboardQuickActionButton:hover,
QToolButton#analysisDashboardQuickActionButton:pressed {
    color:#1d4ed8;
    background:#eff6ff;
    border-color:#93c5fd;
}
QMenu#analysisDashboardQuickActionMenu {
    color:#334155;
    background:#ffffff;
    border:1px solid #cbd5e1;
    padding:5px;
}
QMenu#analysisDashboardQuickActionMenu::item {
    border-radius:6px;
    padding:7px 22px 7px 10px;
}
QMenu#analysisDashboardQuickActionMenu::item:selected {
    color:#1d4ed8;
    background:#eff6ff;
}
QFrame#analysisDashboardDragPlaceholder {
    background:rgba(96,165,250,24);
    border:2px dashed #93c5fd;
    border-radius:10px;
}
QPushButton#analysisDashboardEditButton, QPushButton#analysisDashboardExportButton, QPushButton#analysisDashboardSaveButton,
QPushButton#analysisDashboardCancelButton, QPushButton#analysisDashboardUtilityButton {
    border-radius:7px;
    padding:7px 11px;
    font-size:11px;
    font-weight:800;
}
QPushButton#analysisDashboardEditButton, QPushButton#analysisDashboardSaveButton {
    background:#1f5be3;
    color:#ffffff;
    border:1px solid #1f5be3;
}
QPushButton#analysisDashboardExportButton {
    background:#ffffff;
    color:#166534;
    border:1px solid #86efac;
}
QPushButton#analysisDashboardExportButton:hover {
    background:#f0fdf4;
    border-color:#4ade80;
}
QPushButton#analysisDashboardCancelButton, QPushButton#analysisDashboardUtilityButton {
    background:#ffffff;
    color:#334155;
    border:1px solid #cbd5e1;
}
QPushButton#analysisDashboardCancelButton:hover, QPushButton#analysisDashboardUtilityButton:hover {
    background:#f8fafc;
    border-color:#94a3b8;
}
QPushButton#analysisDashboardUtilityButton:disabled {
    color:#94a3b8;
    background:#f8fafc;
    border-color:#e2e8f0;
}
QFrame#analysisDashboardHint {
    background:#eff6ff;
    border:1px solid #bfdbfe;
    border-radius:10px;
}
QLabel#analysisDashboardHintText {
    color:#1e40af;
    background:transparent;
    font-size:11px;
    font-weight:700;
}
QFrame#analysisNavPanel, QFrame#analysisCard {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:12px;
}
QLabel#analysisNavTitle {
    color:#64748b;
    background:transparent;
    font-size:10px;
    font-weight:900;
    letter-spacing:.5px;
}
QListWidget#analysisNavigation {
    background:transparent;
    border:0;
    outline:0;
}
QListWidget#analysisNavigation::item {
    color:#334155;
    background:transparent;
    border-radius:7px;
    padding:9px 10px;
    margin:2px 0;
    font-weight:700;
}
QListWidget#analysisNavigation::item:selected {
    color:#1d4ed8;
    background:#dbeafe;
    font-weight:900;
}
QLabel#analysisScreenTitle {
    color:#0f172a;
    background:transparent;
    font-size:22px;
    font-weight:900;
}
QLabel#analysisScreenDescription, QLabel#analysisCardSubtitle {
    color:#64748b;
    background:transparent;
    font-size:11px;
}
QLabel#analysisCardTitle {
    color:#334155;
    background:transparent;
    font-size:12px;
    font-weight:800;
}
QLabel#analysisKpiValue {
    color:#0f172a;
    background:transparent;
    font-size:31px;
    font-weight:900;
}
QLabel#analysisKpiUnit {
    color:#64748b;
    background:transparent;
    font-size:12px;
    font-weight:800;
}
QTableWidget#analysisTable {
    background:#ffffff;
    alternate-background-color:#f8fbff;
    border:0;
    gridline-color:#e2e8f0;
    selection-background-color:#dbeafe;
    selection-color:#0f172a;
}
QHeaderView::section {
    background:#eef2f6;
    color:#334155;
    border:0;
    border-right:1px solid #d8e2ed;
    border-bottom:1px solid #d8e2ed;
    padding:7px 8px;
    font-weight:800;
}
QScrollArea#analysisScreenScroll {
    background:transparent;
    border:0;
}
QScrollArea#analysisScreenScroll > QWidget > QWidget { background:transparent; }
QLabel#analysisEmpty {
    color:#64748b;
    background:#f8fbff;
    border:1px dashed #cbd5e1;
    border-radius:8px;
    padding:18px;
}
QLabel#analysisStatusText {
    color:#64748b;
    background:transparent;
    font-size:10px;
}

QFrame#analysisBuilderSettingsPanel, QFrame#analysisBuilderPreviewPanel {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:12px;
}
QScrollArea#analysisBuilderFormScroll {
    background:transparent;
    border:0;
}
QLabel#analysisBuilderSectionTitle {
    color:#64748b;
    background:transparent;
    font-size:10px;
    font-weight:900;
    letter-spacing:.4px;
}
QLabel#analysisBuilderFieldLabel {
    color:#334155;
    background:transparent;
    font-size:11px;
    font-weight:800;
}
QLineEdit#analysisBuilderTitleEdit,
QComboBox#analysisBuilderDatasetCombo,
QComboBox#analysisBuilderVisualizationCombo,
QComboBox#analysisBuilderGroupCombo,
QComboBox#analysisBuilderAggregationCombo,
QComboBox#analysisBuilderMeasureCombo,
QComboBox#analysisBuilderSortCombo,
QComboBox#analysisBuilderSortDirectionCombo,
QComboBox#analysisBuilderLimitCombo,
QComboBox#analysisBuilderFilterField,
QComboBox#analysisBuilderFilterOperator,
QComboBox#analysisBuilderFilterBoolean,
QComboBox#analysisBuilderChartLegendPosition,
QComboBox#analysisBuilderChartPalette,
QLineEdit#analysisBuilderFilterValue,
QLineEdit#analysisBuilderFilterValueTo,
QLineEdit#analysisBuilderKpiSubtitle,
QLineEdit#analysisBuilderKpiPrefix,
QLineEdit#analysisBuilderKpiSuffix,
QSpinBox#analysisBuilderChartMaxCategories,
QSpinBox#analysisBuilderKpiDecimalPlaces,
QListWidget#analysisBuilderTableFields,
QListWidget#analysisBuilderTableColumnOrder {
    background:#ffffff;
    color:#0f172a;
    border:1px solid #cbd5e1;
    border-radius:7px;
    padding:6px 8px;
    min-height:18px;
}
QFrame#analysisBuilderVisualSettings {
    background:#f8fafc;
    color:#334155;
    border:1px solid #d8e2ed;
    border-radius:9px;
}
QPushButton#analysisBuilderVisualSettingsToggle {
    background:transparent;
    color:#334155;
    border:0;
    padding:5px 4px;
    text-align:left;
    font-size:11px;
    font-weight:900;
}
QPushButton#analysisBuilderVisualSettingsToggle:hover { color:#1d4ed8; }
QFrame#analysisBuilderVisualSettingsContent { background:transparent; border:0; }
QCheckBox#analysisBuilderChartShowLegend,
QCheckBox#analysisBuilderChartShowValues,
QCheckBox#analysisBuilderChartGroupOthers {
    color:#334155;
    spacing:7px;
    font-size:11px;
}
QPushButton#analysisBuilderTableColumnUp,
QPushButton#analysisBuilderTableColumnDown {
    background:#ffffff;
    color:#475569;
    border:1px solid #cbd5e1;
    border-radius:6px;
    padding:5px 8px;
    font-size:10px;
    font-weight:800;
}
QPushButton#analysisBuilderTableColumnUp:hover,
QPushButton#analysisBuilderTableColumnDown:hover { background:#eff6ff; color:#1d4ed8; border-color:#93c5fd; }
QComboBox:disabled, QLineEdit:disabled {
    background:#f8fafc;
    color:#94a3b8;
    border-color:#e2e8f0;
}
QFrame#analysisBuilderFilterRow {
    background:#f8fafc;
    border:1px solid #e2e8f0;
    border-radius:8px;
}
QPushButton#analysisBuilderSecondaryButton {
    background:#ffffff;
    color:#334155;
    border:1px solid #cbd5e1;
    border-radius:7px;
    padding:7px 10px;
    font-size:11px;
    font-weight:800;
}
QPushButton#analysisBuilderSecondaryButton:hover {
    background:#f8fafc;
    border-color:#94a3b8;
}
QPushButton#analysisBuilderPreviewButton, QPushButton#analysisBuilderSaveButton,
QPushButton#analysisBuilderDashboardButton {
    border-radius:8px;
    padding:10px 14px;
    font-size:12px;
    font-weight:900;
}
QPushButton#analysisBuilderPreviewButton {
    background:#ffffff;
    color:#334155;
    border:1px solid #cbd5e1;
}
QPushButton#analysisBuilderPreviewButton:hover { background:#f8fafc; border-color:#94a3b8; }
QPushButton#analysisBuilderDashboardButton {
    background:#eff6ff;
    color:#1d4ed8;
    border-color:#93c5fd;
}
QPushButton#analysisBuilderDashboardButton[dashboardPinned="true"] {
    background:#dbeafe;
    color:#1d4ed8;
    border-color:#60a5fa;
}
QPushButton#analysisBuilderSaveButton {
    background:#1f5be3;
    color:#ffffff;
    border:1px solid #1f5be3;
}
QPushButton#analysisBuilderSaveButton:hover { background:#174bc4; }
QPushButton#analysisBuilderSaveButton:disabled { background:#94a3b8; border-color:#94a3b8; }
QLabel#analysisBuilderSaveStatus {
    color:#047857;
    background:transparent;
    font-size:11px;
    font-weight:700;
}
QPushButton#analysisBuilderFilterRemove {
    background:transparent;
    color:#64748b;
    border:0;
    border-radius:6px;
    font-size:16px;
    font-weight:900;
}
QPushButton#analysisBuilderFilterRemove:hover { background:#fee2e2; color:#b91c1c; }
QFrame#analysisBuilderPreviewHost {
    background:#f8fafc;
    border:1px dashed #cbd5e1;
    border-radius:10px;
}
QLabel#analysisBuilderPreviewGuidance {
    color:#92400e;
    background:#fffbeb;
    border:1px solid #fde68a;
    border-radius:7px;
    padding:7px 9px;
    font-size:11px;
    font-weight:700;
}
QFrame#analysisPreviewCardHost { background:transparent; border:0; }
QLabel#analysisBuilderPreviewInfo, QLabel#analysisBuilderPreviewError {
    color:#64748b;
    background:transparent;
    padding:24px;
    font-size:12px;
    font-weight:700;
}
QLabel#analysisBuilderPreviewError { color:#b91c1c; }

QFrame#analysisLibraryItem, QFrame#analysisLibraryEmptyState {
    background:#ffffff;
    border:1px solid #d8e2ed;
    border-radius:10px;
}
QLabel#analysisLibraryItemTitle {
    color:#0f172a;
    background:transparent;
    font-size:13px;
    font-weight:900;
}
QLabel#analysisLibraryItemMeta, QLabel#analysisLibraryItemSummary {
    color:#64748b;
    background:transparent;
    font-size:11px;
}
QLabel#analysisLibraryItemWarning, QLabel#analysisLibraryWarning {
    color:#b45309;
    background:#fffbeb;
    border:1px solid #fde68a;
    border-radius:7px;
    padding:7px 9px;
    font-size:10px;
    font-weight:700;
}
QLabel#analysisCustomDashboardWarning {
    color:#92400e;
    background:#fffbeb;
    border:1px solid #fde68a;
    border-radius:7px;
    padding:8px 10px;
    font-weight:700;
}
QPushButton#analysisLibraryOpenButton, QPushButton#analysisLibraryEditButton,
QPushButton#analysisLibraryCopyButton, QPushButton#analysisLibraryDeleteButton,
QPushButton#analysisLibraryDashboardButton {
    background:#ffffff;
    color:#334155;
    border:1px solid #cbd5e1;
    border-radius:6px;
    padding:5px 8px;
    font-size:10px;
    font-weight:800;
}
QPushButton#analysisLibraryOpenButton:hover, QPushButton#analysisLibraryEditButton:hover,
QPushButton#analysisLibraryCopyButton:hover, QPushButton#analysisLibraryDashboardButton:hover {
    background:#eff6ff; color:#1d4ed8; border-color:#93c5fd;
}
QPushButton#analysisLibraryDashboardButton[dashboardPinned="true"] {
    background:#dbeafe; color:#1d4ed8; border-color:#60a5fa;
}
QPushButton#analysisLibraryDeleteButton:hover { background:#fee2e2; color:#b91c1c; border-color:#fecaca; }
QPushButton#analysisLibraryCopyButton:disabled { color:#94a3b8; background:#f8fafc; border-color:#e2e8f0; }
QPushButton#analysisLibraryDashboardButton:disabled { color:#94a3b8; background:#f8fafc; border-color:#e2e8f0; }
QScrollArea#analysisLibraryListScroll { background:transparent; border:0; }

"""


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return f"{int(value):,}".replace(",", ".")
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def _source_name(source: Any) -> str:
    if isinstance(source, (str, Path)):
        try:
            return Path(source).name
        except Exception:
            return str(source)
    for attr in ("path", "db_path", "database_path"):
        value = getattr(source, attr, None)
        if value:
            try:
                return Path(value).name
            except Exception:
                return str(value)
    return "STS veri kaynağı"


class _AnalysisChartWidget(QWidget):
    """Bağımlılıksız, salt gösterim amaçlı küçük dashboard grafik yüzeyi."""

    def __init__(
        self,
        data: Any,
        chart_type: ChartType,
        parent: QWidget | None = None,
        *,
        dashboard_mode: bool = False,
        visual_settings: ChartVisualSettings | None = None,
    ):
        super().__init__(parent)
        self._series = chart_series(data)
        self._chart_type = chart_type
        self._visual_settings = visual_settings
        self._palette = palette_colors(visual_settings.palette) if visual_settings is not None else _CHART_PALETTE
        self.setMinimumHeight(80 if dashboard_mode else 230)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    @property
    def visual_settings(self) -> ChartVisualSettings | None:
        return self._visual_settings

    @property
    def palette(self) -> tuple[str, ...]:
        return tuple(self._palette)

    @property
    def legend_visible(self) -> bool:
        if self._visual_settings is None:
            return self._chart_type == ChartType.DONUT
        return self._visual_settings.show_legend and self._chart_type != ChartType.LINE

    @property
    def legend_position(self) -> str:
        return self._visual_settings.legend_position if self._visual_settings is not None else "right"

    @property
    def show_values(self) -> bool:
        if self._visual_settings is None:
            return self._chart_type in {ChartType.BAR, ChartType.HORIZONTAL_BAR, ChartType.DONUT}
        return self._visual_settings.show_values

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        rows = [
            {"label": str(row.get("label") or "Eksik"), "value": self._number(row.get("value"))}
            for row in self._series
        ]
        if not rows:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Gösterilecek veri yok")
            return

        if self._visual_settings is None:
            if self._chart_type == ChartType.DONUT:
                self._paint_legacy_donut(painter, rows)
            elif self._chart_type == ChartType.LINE:
                self._paint_legacy_line(painter, rows)
            elif self._chart_type == ChartType.HORIZONTAL_BAR:
                self._paint_legacy_horizontal_bars(painter, rows)
            else:
                self._paint_legacy_bars(painter, rows)
            return

        chart_area = self._chart_area(rows)
        if self._chart_type == ChartType.DONUT:
            self._paint_donut(painter, rows, chart_area)
        elif self._chart_type == ChartType.LINE:
            self._paint_line(painter, rows, chart_area)
        elif self._chart_type == ChartType.HORIZONTAL_BAR:
            self._paint_horizontal_bars(painter, rows, chart_area)
        else:
            self._paint_bars(painter, rows, chart_area)
        if self.legend_visible:
            self._paint_legend(painter, rows, chart_area)

    def _paint_legacy_horizontal_bars(self, painter: QPainter, rows: Sequence[Mapping[str, Any]]) -> None:
        max_value = max((float(row["value"]) for row in rows), default=0.0) or 1.0
        left = 132
        right = 54
        top = 12
        bottom = 12
        available_h = max(1, self.height() - top - bottom)
        step = max(28.0, available_h / max(len(rows), 1))
        bar_h = min(22.0, step * 0.58)
        available_w = max(20.0, self.width() - left - right)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        for index, row in enumerate(rows):
            y = top + index * step + (step - bar_h) / 2
            label_rect = QRectF(0, y - 2, left - 10, bar_h + 4)
            painter.setPen(QColor("#475569"))
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, str(row["label"]))
            value = float(row["value"])
            width = available_w * max(value, 0.0) / max_value
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_CHART_PALETTE[index % len(_CHART_PALETTE)]))
            painter.drawRoundedRect(QRectF(left, y, max(2.0, width), bar_h), 4, 4)
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(left + min(width + 7, available_w - 4), y - 2, right, bar_h + 4),
                Qt.AlignLeft | Qt.AlignVCenter,
                _display_value(value),
            )

    def _paint_legacy_bars(self, painter: QPainter, rows: Sequence[Mapping[str, Any]]) -> None:
        rows = list(rows)[:12]
        max_value = max((float(row["value"]) for row in rows), default=0.0) or 1.0
        left, right, top, bottom = 34, 18, 14, 52
        area_w = max(20.0, self.width() - left - right)
        area_h = max(20.0, self.height() - top - bottom)
        slot = area_w / max(len(rows), 1)
        bar_w = max(8.0, min(44.0, slot * 0.58))

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(left, top + area_h), QPointF(left + area_w, top + area_h))

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for index, row in enumerate(rows):
            value = max(float(row["value"]), 0.0)
            height = area_h * value / max_value
            x = left + index * slot + (slot - bar_w) / 2
            y = top + area_h - height
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_CHART_PALETTE[index % len(_CHART_PALETTE)]))
            painter.drawRoundedRect(QRectF(x, y, bar_w, max(2.0, height)), 4, 4)
            painter.setPen(QColor("#334155"))
            painter.drawText(QRectF(x - 12, y - 20, bar_w + 24, 18), Qt.AlignCenter, _display_value(value))
            label = str(row["label"])
            if len(label) > 14:
                label = label[:12] + "…"
            painter.drawText(QRectF(x - slot * 0.2, top + area_h + 5, slot * 1.4, 38), Qt.AlignHCenter | Qt.AlignTop, label)

    def _paint_legacy_donut(self, painter: QPainter, rows: Sequence[Mapping[str, Any]]) -> None:
        values = [max(float(row["value"]), 0.0) for row in rows]
        total = sum(values)
        if total <= 0:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Gösterilecek veri yok")
            return

        diameter = min(self.height() - 36, max(110, int(self.width() * 0.40)))
        diameter = max(80, diameter)
        donut = QRectF(24, (self.height() - diameter) / 2, diameter, diameter)
        start_angle = 90 * 16
        painter.setPen(Qt.NoPen)
        for index, value in enumerate(values):
            span = -int(round(value / total * 360 * 16))
            painter.setBrush(QColor(_CHART_PALETTE[index % len(_CHART_PALETTE)]))
            painter.drawPie(donut, start_angle, span)
            start_angle += span
        inner = donut.adjusted(diameter * 0.29, diameter * 0.29, -diameter * 0.29, -diameter * 0.29)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(inner)
        painter.setPen(QColor("#0f172a"))
        font = QFont(painter.font())
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(inner, Qt.AlignCenter, _display_value(total))

        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        legend_x = donut.right() + 28
        legend_y = max(16.0, (self.height() - len(rows) * 25) / 2)
        for index, row in enumerate(rows):
            y = legend_y + index * 25
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_CHART_PALETTE[index % len(_CHART_PALETTE)]))
            painter.drawRoundedRect(QRectF(legend_x, y + 3, 12, 12), 3, 3)
            painter.setPen(QColor("#334155"))
            label = f"{row['label']}  ·  {_display_value(row['value'])}"
            painter.drawText(QRectF(legend_x + 20, y, max(30, self.width() - legend_x - 24), 20), Qt.AlignLeft | Qt.AlignVCenter, label)

    def _paint_legacy_line(self, painter: QPainter, rows: Sequence[Mapping[str, Any]]) -> None:
        rows = list(rows)[:20]
        values = [float(row["value"]) for row in rows]
        max_value = max(values, default=0.0)
        min_value = min(values, default=0.0)
        value_range = max(max_value - min_value, 1.0)
        left, right, top, bottom = 38, 18, 18, 44
        area_w = max(20.0, self.width() - left - right)
        area_h = max(20.0, self.height() - top - bottom)
        points: list[QPointF] = []
        for index, value in enumerate(values):
            x = left + (area_w * index / max(len(values) - 1, 1))
            y = top + area_h - ((value - min_value) / value_range * area_h)
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(left, top + area_h), QPointF(left + area_w, top + area_h))
        painter.setPen(QPen(QColor("#1f5be3"), 3))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)
        painter.setBrush(QColor("#1f5be3"))
        painter.setPen(Qt.NoPen)
        for point in points:
            painter.drawEllipse(point, 4, 4)

        painter.setPen(QColor("#475569"))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for index, (row, point) in enumerate(zip(rows, points)):
            if len(rows) > 8 and index % 2:
                continue
            label = str(row["label"])
            if len(label) > 12:
                label = label[:10] + "…"
            painter.drawText(QRectF(point.x() - 42, top + area_h + 6, 84, 30), Qt.AlignHCenter | Qt.AlignTop, label)

    def _chart_area(self, rows: Sequence[Mapping[str, Any]]) -> QRectF:
        area = QRectF(0, 0, self.width(), self.height())
        if not self.legend_visible:
            return area
        if self.legend_position == "bottom":
            rows_per_line = 3
            lines = max(1, math.ceil(len(rows) / rows_per_line))
            legend_h = min(max(48.0, lines * 22.0 + 12.0), max(48.0, self.height() * 0.38))
            return area.adjusted(0, 0, 0, -legend_h)
        legend_w = min(210.0, max(150.0, self.width() * 0.34))
        return area.adjusted(0, 0, -legend_w, 0)

    def _paint_horizontal_bars(
        self,
        painter: QPainter,
        rows: Sequence[Mapping[str, Any]],
        area: QRectF,
    ) -> None:
        max_value = max((float(row["value"]) for row in rows), default=0.0) or 1.0
        left = area.left() + min(132.0, max(80.0, area.width() * 0.28))
        right = 22.0
        top = area.top() + 12.0
        bottom = 12.0
        available_h = max(1.0, area.height() - 24.0)
        step = max(28.0, available_h / max(len(rows), 1))
        bar_h = min(22.0, step * 0.58)
        available_w = max(20.0, area.right() - left - right)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        for index, row in enumerate(rows):
            y = top + index * step + (step - bar_h) / 2
            label_rect = QRectF(area.left(), y - 2, left - area.left() - 10, bar_h + 4)
            painter.setPen(QColor("#475569"))
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, str(row["label"]))
            value = float(row["value"])
            width = available_w * max(value, 0.0) / max_value
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._palette[index % len(self._palette)]))
            painter.drawRoundedRect(QRectF(left, y, max(2.0, width), bar_h), 4, 4)
            if self.show_values:
                painter.setPen(QColor("#334155"))
                painter.drawText(
                    QRectF(left + min(width + 7, available_w - 4), y - 2, right + 36, bar_h + 4),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    _display_value(value),
                )

    def _paint_bars(
        self,
        painter: QPainter,
        rows: Sequence[Mapping[str, Any]],
        area: QRectF,
    ) -> None:
        rows = list(rows)
        max_value = max((float(row["value"]) for row in rows), default=0.0) or 1.0
        left, right, top, bottom = area.left() + 34, 18, area.top() + 14, 52
        area_w = max(20.0, area.right() - left - right)
        area_h = max(20.0, area.bottom() - top - bottom)
        slot = area_w / max(len(rows), 1)
        bar_w = max(8.0, min(44.0, slot * 0.58))

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(left, top + area_h), QPointF(left + area_w, top + area_h))

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for index, row in enumerate(rows):
            value = max(float(row["value"]), 0.0)
            height = area_h * value / max_value
            x = left + index * slot + (slot - bar_w) / 2
            y = top + area_h - height
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._palette[index % len(self._palette)]))
            painter.drawRoundedRect(QRectF(x, y, bar_w, max(2.0, height)), 4, 4)
            if self.show_values:
                painter.setPen(QColor("#334155"))
                painter.drawText(QRectF(x - 12, y - 20, bar_w + 24, 18), Qt.AlignCenter, _display_value(value))
            painter.setPen(QColor("#334155"))
            label = str(row["label"])
            if len(label) > 14:
                label = label[:12] + "…"
            painter.drawText(QRectF(x - slot * 0.2, top + area_h + 5, slot * 1.4, 38), Qt.AlignHCenter | Qt.AlignTop, label)

    def _paint_donut(
        self,
        painter: QPainter,
        rows: Sequence[Mapping[str, Any]],
        area: QRectF,
    ) -> None:
        values = [max(float(row["value"]), 0.0) for row in rows]
        total = sum(values)
        if total <= 0:
            painter.setPen(QColor("#64748b"))
            painter.drawText(area, Qt.AlignCenter, "Gösterilecek veri yok")
            return

        diameter = min(area.height() - 36, max(90, int(area.width() * 0.68)))
        diameter = max(70, diameter)
        donut = QRectF(
            area.left() + (area.width() - diameter) / 2,
            area.top() + (area.height() - diameter) / 2,
            diameter,
            diameter,
        )
        start_angle = 90 * 16
        current_degrees = 90.0
        painter.setPen(Qt.NoPen)
        for index, value in enumerate(values):
            degrees = value / total * 360.0
            span = -int(round(degrees * 16))
            painter.setBrush(QColor(self._palette[index % len(self._palette)]))
            painter.drawPie(donut, start_angle, span)
            if self.show_values and not self.legend_visible and degrees >= 12:
                midpoint = math.radians(current_degrees - degrees / 2)
                radius = diameter * 0.38
                point = QPointF(
                    donut.center().x() + math.cos(midpoint) * radius,
                    donut.center().y() - math.sin(midpoint) * radius,
                )
                painter.setPen(QColor("#0f172a"))
                painter.drawText(QRectF(point.x() - 34, point.y() - 10, 68, 20), Qt.AlignCenter, _display_value(value))
                painter.setPen(Qt.NoPen)
            start_angle += span
            current_degrees -= degrees
        inner = donut.adjusted(diameter * 0.29, diameter * 0.29, -diameter * 0.29, -diameter * 0.29)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(inner)
        painter.setPen(QColor("#0f172a"))
        font = QFont(painter.font())
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(inner, Qt.AlignCenter, _display_value(total))

    def _paint_line(
        self,
        painter: QPainter,
        rows: Sequence[Mapping[str, Any]],
        area: QRectF,
    ) -> None:
        rows = list(rows)
        values = [float(row["value"]) for row in rows]
        max_value = max(values, default=0.0)
        min_value = min(values, default=0.0)
        value_range = max(max_value - min_value, 1.0)
        left, right, top, bottom = area.left() + 38, 18, area.top() + 18, 44
        area_w = max(20.0, area.right() - left - right)
        area_h = max(20.0, area.bottom() - top - bottom)
        points: list[QPointF] = []
        for index, value in enumerate(values):
            x = left + (area_w * index / max(len(values) - 1, 1))
            y = top + area_h - ((value - min_value) / value_range * area_h)
            points.append(QPointF(x, y))

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(left, top + area_h), QPointF(left + area_w, top + area_h))
        line_color = QColor(self._palette[0])
        painter.setPen(QPen(line_color, 3))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)
        painter.setBrush(line_color)
        painter.setPen(Qt.NoPen)
        for point in points:
            painter.drawEllipse(point, 4, 4)

        painter.setPen(QColor("#475569"))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for index, (row, point) in enumerate(zip(rows, points)):
            if self.show_values:
                painter.drawText(QRectF(point.x() - 35, point.y() - 24, 70, 18), Qt.AlignCenter, _display_value(row["value"]))
            if len(rows) > 8 and index % 2:
                continue
            label = str(row["label"])
            if len(label) > 12:
                label = label[:10] + "…"
            painter.drawText(QRectF(point.x() - 42, top + area_h + 6, 84, 30), Qt.AlignHCenter | Qt.AlignTop, label)

    def _paint_legend(
        self,
        painter: QPainter,
        rows: Sequence[Mapping[str, Any]],
        chart_area: QRectF,
    ) -> None:
        font = painter.font()
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        if self.legend_position == "bottom":
            legend_top = chart_area.bottom() + 8
            available_w = max(1.0, self.width() - 24.0)
            columns = min(3, max(1, len(rows)))
            cell_w = available_w / columns
            for index, row in enumerate(rows):
                col = index % columns
                line = index // columns
                x = 12 + col * cell_w
                y = legend_top + line * 22
                self._paint_legend_item(painter, row, index, QRectF(x, y, cell_w - 8, 20))
            return
        legend_left = chart_area.right() + 14
        legend_width = max(30.0, self.width() - legend_left - 10)
        legend_y = max(12.0, (self.height() - len(rows) * 24.0) / 2)
        for index, row in enumerate(rows):
            self._paint_legend_item(
                painter,
                row,
                index,
                QRectF(legend_left, legend_y + index * 24, legend_width, 20),
            )

    def _paint_legend_item(
        self,
        painter: QPainter,
        row: Mapping[str, Any],
        index: int,
        rect: QRectF,
    ) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._palette[index % len(self._palette)]))
        painter.drawRoundedRect(QRectF(rect.left(), rect.top() + 4, 11, 11), 3, 3)
        painter.setPen(QColor("#334155"))
        label = str(row["label"])
        if self.show_values:
            label = f"{label}  ·  {_display_value(row['value'])}"
        painter.drawText(
            QRectF(rect.left() + 18, rect.top(), max(20.0, rect.width() - 18), rect.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            label,
        )


class AnalysisCenterWindow(QMainWindow):
    """Tur 9 analiz payload'ını gerçek, salt-okunur PySide penceresinde gösterir.

    Analytics engine Qt'den bağımsız kalır. Bu sınıf yalnızca UI adapter'ıdır ve
    ``AnalysisWindow`` denetleyicisinin ürettiği dashboard payload'ını render eder.
    """

    def __init__(
        self,
        source: Any = None,
        contract_index: Iterable[Mapping[str, Any]] | None = None,
        settings: VisualSettings | None = None,
        parent: QWidget | None = None,
        workspace_store: DashboardWorkspaceStore | None = None,
        analysis_repository: AnalysisRepository | None = None,
    ):
        super().__init__(parent)
        self.source = source
        self.contract_index = list(contract_index or [])
        self.settings = (settings or VisualSettings(
            compact_mode=DEFAULT_SETTINGS.compact_mode,
            upcoming_days=DEFAULT_SETTINGS.upcoming_days,
            max_table_rows=DEFAULT_SETTINGS.max_table_rows,
            show_disabled_sections=False,
            empty_state_uses_sample=False,
        )).normalized()
        self.analysis_repository = analysis_repository or FileAnalysisRepository(self.source)
        self.controller = AnalysisWindow(
            source=self.source,
            contract_index=self.contract_index,
            settings=self.settings,
            analysis_repository=self.analysis_repository,
        )
        self.workspace_store = workspace_store or DashboardWorkspaceStore()
        self.workspace = DashboardWorkspace(source_key=source_workspace_key(self.source))
        self._workspace_loaded = False
        self._workspace_persistence_enabled = True
        self._item_ids: list[str] = []
        self._payload: dict[str, Any] = {}
        self._dashboard_items: list[DashboardItem] = []
        self._dashboard_edit_session: DashboardEditSession | None = None
        self._dashboard_canvas: DashboardCanvas | None = None
        self._dashboard_undo_button: QPushButton | None = None
        self._dashboard_redo_button: QPushButton | None = None
        self._analysis_builder_controller = AnalysisBuilderController(self.controller.analysis_service)
        self._analysis_builder_widget: AnalysisBuilderWidget | None = None
        self._analysis_library_controller = CustomAnalysisLibraryController(self.controller.analysis_service)
        self._custom_dashboard_controller = CustomAnalysisDashboardController(
            self.controller.analysis_service
        )
        self._dashboard_excel_exporter = export_dashboard_collection_excel
        self._dashboard_excel_thread: QThread | None = None
        self._dashboard_excel_worker: DashboardExcelExportWorker | None = None
        self._dashboard_export_button: QPushButton | None = None
        self._last_dashboard_excel_export_result = None
        self._analysis_library_widget: AnalysisLibraryWidget | None = None
        self._builder_refresh_notice = False
        self._library_refresh_notice = False

        self.setObjectName("analysisCenterWindow")
        self.setWindowTitle("Analiz Merkezi")
        self.resize(1240, 780)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(_ANALYSIS_STYLE)
        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("analysisCenterRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        top = QFrame(root)
        top.setObjectName("analysisTopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
        title = QLabel("Analiz Merkezi", top)
        title.setObjectName("analysisTitle")
        subtitle = QLabel("İstediğiniz analiz kartlarını seçin ve kendi dashboard alanınızda takip edin", top)
        subtitle.setObjectName("analysisSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top_layout.addLayout(title_box, 1)

        self.source_label = QLabel(_source_name(self.source), top)
        self.source_label.setObjectName("analysisSourcePill")
        self.source_label.setToolTip(str(self.source or ""))
        top_layout.addWidget(self.source_label, 0, Qt.AlignVCenter)

        self.refresh_button = QPushButton("Yenile", top)
        self.refresh_button.setObjectName("analysisRefreshButton")
        self.refresh_button.clicked.connect(self.refresh_data)
        top_layout.addWidget(self.refresh_button, 0, Qt.AlignVCenter)
        outer.addWidget(top, 0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        nav_panel = QFrame(root)
        nav_panel.setObjectName("analysisNavPanel")
        nav_panel.setMinimumWidth(220)
        nav_panel.setMaximumWidth(280)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(12, 14, 12, 12)
        nav_layout.setSpacing(8)
        nav_title = QLabel("DASHBOARD & ANALİZLER", nav_panel)
        nav_title.setObjectName("analysisNavTitle")
        nav_layout.addWidget(nav_title)
        self.navigation = QListWidget(nav_panel)
        self.navigation.setObjectName("analysisNavigation")
        self.navigation.setSelectionMode(QAbstractItemView.SingleSelection)
        self.navigation.currentRowChanged.connect(self._activate_screen)
        nav_layout.addWidget(self.navigation, 1)
        self.status_text = QLabel("", nav_panel)
        self.status_text.setObjectName("analysisStatusText")
        self.status_text.setWordWrap(True)
        nav_layout.addWidget(self.status_text)
        body.addWidget(nav_panel, 0)

        self.stack = QStackedWidget(root)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        self._dashboard_undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._dashboard_undo_shortcut.setContext(Qt.ApplicationShortcut)
        self._dashboard_undo_shortcut.activated.connect(self._undo_dashboard_edit)
        self._dashboard_redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._dashboard_redo_shortcut.setContext(Qt.ApplicationShortcut)
        self._dashboard_redo_shortcut.activated.connect(self._redo_dashboard_edit)

    def refresh_after_data_change(self, _scope: str = "all") -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        current_id = self.current_item_id() or CUSTOM_DASHBOARD_ID
        builder_was_visible = current_id == ANALYSIS_BUILDER_ID and bool(self._payload)
        library_preview_was_visible = (
            current_id == MY_ANALYSES_ID
            and self._analysis_library_widget is not None
            and self._analysis_library_widget.last_definition is not None
        )
        if self._dashboard_edit_session is not None:
            self._dashboard_edit_session.cancel_interaction()
        try:
            payload = self.controller.refresh_payload()
            items = [
                item
                for item in payload.get("dashboard_items", [])
                if isinstance(item, DashboardItem) and getattr(item, "enabled", True)
            ]
        except Exception as exc:
            QMessageBox.warning(self, "Analiz Merkezi", f"Analiz verisi yenilenemedi.\n\n{exc}")
            return

        self._payload = payload
        self._dashboard_items = items
        self._builder_refresh_notice = builder_was_visible
        self._library_refresh_notice = library_preview_was_visible
        if not self._workspace_loaded:
            try:
                custom_card_keys, protected_custom_sources = (
                    self._custom_dashboard_controller.workspace_catalog()
                )
                self.workspace = self.workspace_store.load(
                    self.source,
                    dashboard_items=self._dashboard_items,
                    additional_card_keys=custom_card_keys,
                    protected_source_ids=protected_custom_sources,
                )
                self._workspace_persistence_enabled = True
            except DashboardWorkspaceError as exc:
                self._workspace_persistence_enabled = False
                QMessageBox.warning(
                    self,
                    "Dashboard",
                    "Dashboard düzeni yüklenemedi. Mevcut workspace dosyası korunacak ve "
                    f"bu oturumda üzerine yazılmayacak.\n\n{exc}",
                )
            self._workspace_loaded = True
        self._render_items(current_id)
        self._update_status(payload)

    def _render_items(self, current_id: str | None = None) -> None:
        current_id = current_id or self.current_item_id() or CUSTOM_DASHBOARD_ID
        self._dashboard_canvas = None
        self._dashboard_undo_button = None
        self._dashboard_redo_button = None
        self._dashboard_export_button = None
        self._analysis_builder_widget = None
        self._analysis_library_widget = None
        self._clear_stack()
        self.navigation.blockSignals(True)
        self.navigation.clear()
        self._item_ids = []

        self._item_ids.append(CUSTOM_DASHBOARD_ID)
        dashboard_nav = QListWidgetItem("Dashboard")
        dashboard_nav.setData(Qt.UserRole, CUSTOM_DASHBOARD_ID)
        self.navigation.addItem(dashboard_nav)
        self.stack.addWidget(self._build_custom_dashboard_screen())

        for item in self._dashboard_items:
            self._item_ids.append(item.item_id)
            nav_item = QListWidgetItem(item.title)
            nav_item.setData(Qt.UserRole, item.item_id)
            self.navigation.addItem(nav_item)
            self.stack.addWidget(self._build_screen(item))

        self._item_ids.append(ANALYSIS_BUILDER_ID)
        builder_nav = QListWidgetItem("Analiz Oluştur")
        builder_nav.setData(Qt.UserRole, ANALYSIS_BUILDER_ID)
        self.navigation.addItem(builder_nav)
        self.stack.addWidget(self._build_analysis_builder_screen())

        self._item_ids.append(MY_ANALYSES_ID)
        library_nav = QListWidgetItem("Analizlerim")
        library_nav.setData(Qt.UserRole, MY_ANALYSES_ID)
        self.navigation.addItem(library_nav)
        self.stack.addWidget(self._build_analysis_library_screen())
        self.navigation.blockSignals(False)

        target_row = 0
        if current_id in self._item_ids:
            target_row = self._item_ids.index(current_id)
        if self.navigation.count():
            self.navigation.setCurrentRow(target_row)
            self.stack.setCurrentIndex(target_row)
        self.navigation.setEnabled(self._dashboard_edit_session is None)
        self.refresh_button.setEnabled(self._dashboard_edit_session is None)
        if not self.navigation.count():
            self.stack.addWidget(self._empty_widget("Analiz ekranı üretilemedi."))
            self.stack.setCurrentIndex(0)

    def _save_workspace(self, workspace: DashboardWorkspace | None = None) -> bool:
        if not self._workspace_persistence_enabled:
            QMessageBox.warning(
                self,
                "Dashboard",
                "Workspace dosyası daha önce güvenli şekilde yüklenemediği için üzerine yazılmadı.",
            )
            return False
        try:
            self.workspace_store.save(self.source, workspace or self.workspace)
            return True
        except (OSError, DashboardWorkspaceError) as exc:
            QMessageBox.warning(
                self,
                "Dashboard",
                f"Dashboard düzeni kaydedilemedi. Bu oturumdaki görünüm korunacak.\n\n{exc}",
            )
            return False

    def _toggle_dashboard_card(self, card: AnalysisCard) -> None:
        source_screen_id = str(card.screen_id or "").strip()
        card_id = str(card.card_id or "").strip()
        candidate = self.workspace.working_copy()
        if candidate.contains(source_screen_id, card_id):
            changed = candidate.remove(source_screen_id, card_id)
        else:
            changed = candidate.pin(card)
        if not changed:
            return
        if not self._save_workspace(candidate):
            return
        self.workspace = candidate
        self._render_items(self.current_item_id())

    def _custom_analysis_is_pinned(self, analysis_id: str) -> bool:
        return self._custom_dashboard_controller.is_pinned(self.workspace, analysis_id)

    def _toggle_custom_analysis_dashboard(self, analysis_id: str) -> bool:
        pinned = self._custom_dashboard_controller.is_pinned(self.workspace, analysis_id)
        return self._set_custom_analysis_dashboard_pinned(analysis_id, not pinned)

    def _set_custom_analysis_dashboard_pinned(
        self,
        analysis_id: str,
        pinned: bool,
    ) -> bool:
        candidate = self.workspace.working_copy()
        try:
            currently_pinned = self._custom_dashboard_controller.is_pinned(
                candidate,
                analysis_id,
            )
            if currently_pinned == bool(pinned):
                return True
            changed = (
                self._custom_dashboard_controller.pin(candidate, analysis_id)
                if pinned
                else self._custom_dashboard_controller.unpin(candidate, analysis_id)
            )
        except Exception as exc:
            QMessageBox.warning(self, "Dashboard", str(exc))
            return False
        if not changed:
            return True
        if not self._save_workspace(candidate):
            return False
        self.workspace = candidate
        self._refresh_dashboard_screen()
        if self._analysis_library_widget is not None:
            self._analysis_library_widget.refresh_items()
        if self._analysis_builder_widget is not None:
            self._analysis_builder_widget.refresh_from_draft()
        return True

    def _dashboard_quick_action(
        self,
        placement_id: str,
        action_id: DashboardQuickAction,
    ) -> None:
        placement = next(
            (
                item
                for item in self.workspace.placements
                if item.placement_id == placement_id
            ),
            None,
        )
        if (
            placement is None
            or placement.source_screen_id != CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID
        ):
            return
        analysis_id = placement.card_id
        if action_id == DashboardQuickAction.EDIT_ANALYSIS:
            self._edit_saved_analysis(analysis_id)
        elif action_id == DashboardQuickAction.EDIT_VISUAL:
            self._edit_saved_analysis(analysis_id, focus_visual_settings=True)
        elif action_id == DashboardQuickAction.UNPIN:
            self._set_custom_analysis_dashboard_pinned(analysis_id, False)

    def _refresh_dashboard_screen(self) -> None:
        if CUSTOM_DASHBOARD_ID not in self._item_ids:
            return
        index = self._item_ids.index(CUSTOM_DASHBOARD_ID)
        if index >= self.stack.count():
            return
        was_current = self.stack.currentIndex() == index
        old_widget = self.stack.widget(index)
        replacement = self._build_custom_dashboard_screen()
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()
        self.stack.insertWidget(index, replacement)
        if was_current:
            self.stack.setCurrentIndex(index)

    def _enter_dashboard_edit(self) -> None:
        if self._dashboard_edit_session is not None or not self.workspace.placements:
            return
        self._dashboard_edit_session = DashboardEditSession(self.workspace)
        self._render_items(CUSTOM_DASHBOARD_ID)

    def _save_dashboard_edit(self) -> None:
        session = self._dashboard_edit_session
        if session is None:
            return
        session.cancel_interaction()
        working = session.working_workspace
        try:
            working.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Dashboard", f"Dashboard yerleşimi geçersiz.\n\n{exc}")
            return
        if not self._save_workspace(working):
            return
        self.workspace = session.mark_saved()
        self._dashboard_edit_session = None
        self._render_items(CUSTOM_DASHBOARD_ID)

    def _cancel_dashboard_edit(self) -> None:
        session = self._dashboard_edit_session
        if session is None:
            return
        if self._dashboard_canvas is not None:
            self._dashboard_canvas.cancel_active_interaction()
        session.discard()
        self._dashboard_edit_session = None
        self._render_items(CUSTOM_DASHBOARD_ID)

    def _reset_dashboard_edit(self) -> None:
        if self._dashboard_canvas is not None:
            self._dashboard_canvas.reset_layout()

    def _undo_dashboard_edit(self) -> None:
        if self._dashboard_canvas is not None and self._dashboard_edit_session is not None:
            self._dashboard_canvas.undo()

    def _redo_dashboard_edit(self) -> None:
        if self._dashboard_canvas is not None and self._dashboard_edit_session is not None:
            self._dashboard_canvas.redo()

    def _update_dashboard_history_actions(self) -> None:
        session = self._dashboard_edit_session
        if self._dashboard_undo_button is not None:
            self._dashboard_undo_button.setEnabled(bool(session and session.can_undo))
        if self._dashboard_redo_button is not None:
            self._dashboard_redo_button.setEnabled(bool(session and session.can_redo))

    def current_item_id(self) -> str:
        row = self.navigation.currentRow() if hasattr(self, "navigation") else -1
        if 0 <= row < len(self._item_ids):
            return self._item_ids[row]
        return ""

    def _update_status(self, payload: Mapping[str, Any]) -> None:
        data = payload.get("data") or {}
        meta_rows = data.get("_meta") or [] if isinstance(data, Mapping) else []
        meta = meta_rows[0] if meta_rows and isinstance(meta_rows[0], Mapping) else {}
        source_label = str(meta.get("source") or "unknown")
        errors = list(meta.get("errors") or [])
        source_names = {
            "sqlite_read_only": "Salt-okunur STS bağlantısı",
            "contract_index": "Sözleşme indeksi",
            "sample": "Örnek veri",
            "empty": "Boş veri",
        }
        text = source_names.get(source_label, source_label)
        if errors:
            text += f"\n{len(errors)} veri yükleme uyarısı"
            self.status_text.setToolTip("\n".join(str(error) for error in errors))
        else:
            self.status_text.setToolTip("")
        self.status_text.setText(text)

    def _activate_screen(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _clear_stack(self) -> None:
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()

    def _export_dashboard_to_excel(self) -> None:
        if self._dashboard_excel_thread is not None:
            return
        suggested = suggested_dashboard_excel_path(self.source)
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Dashboard Excel Dosyası",
            str(suggested),
            "Excel Dosyası (*.xlsx)",
        )
        if not selected_path:
            return
        try:
            collection = DashboardExportCollector(self._custom_dashboard_controller).collect(
                self.workspace,
                self._dashboard_items,
            )
            if not collection.items:
                raise DashboardExcelExportError("Dashboard'da aktarılabilir kart bulunamadı.")
        except DashboardExcelExportError as exc:
            QMessageBox.warning(self, "Dashboard Excel", str(exc))
            return
        except Exception:
            logging.getLogger(__name__).exception("Dashboard Excel collection failed")
            QMessageBox.warning(
                self,
                "Dashboard Excel",
                "Dashboard kartları Excel aktarımı için hazırlanamadı.",
            )
            return

        thread = QThread(self)
        worker = DashboardExcelExportWorker(
            output_path=selected_path,
            collection=collection,
            registry=self.controller.analysis_service.registry,
            source=self.source,
            workspace_card_count=len(self.workspace.placements),
            exporter=self._dashboard_excel_exporter,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._dashboard_excel_export_finished)
        worker.failed.connect(self._dashboard_excel_export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._dashboard_excel_export_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._dashboard_excel_thread = thread
        self._dashboard_excel_worker = worker
        self._last_dashboard_excel_export_result = None
        if self._dashboard_export_button is not None:
            self._dashboard_export_button.setEnabled(False)
        self.status_text.setText("Dashboard Excel dosyası oluşturuluyor…")
        thread.start()

    def _dashboard_excel_export_finished(self, result: object) -> None:
        self._last_dashboard_excel_export_result = result
        warning_count = int(getattr(result, "warning_count", 0) or 0)
        output_path = getattr(result, "output_path", "")
        warning_text = (
            f"\n\n{warning_count} kart aktarılamadı; uyarılar Dashboard Özeti sayfasına yazıldı."
            if warning_count
            else ""
        )
        QMessageBox.information(
            self,
            "Dashboard Excel",
            f"Dashboard Excel dosyası oluşturuldu.\n\n{output_path}{warning_text}",
        )

    def _dashboard_excel_export_failed(self, exc: object, traceback_text: str) -> None:
        logging.getLogger(__name__).error(
            "Dashboard Excel export failed: %s\n%s",
            exc,
            traceback_text,
        )
        if isinstance(exc, DashboardExcelExportError):
            message = str(exc)
        else:
            message = "Dashboard Excel dosyası oluşturulamadı."
        QMessageBox.warning(self, "Dashboard Excel", message)

    def _dashboard_excel_export_thread_finished(self) -> None:
        self._dashboard_excel_thread = None
        self._dashboard_excel_worker = None
        if self._dashboard_export_button is not None:
            self._dashboard_export_button.setEnabled(bool(self.workspace.placements))
        if self._payload:
            self._update_status(self._payload)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        thread = self._dashboard_excel_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()
        super().closeEvent(event)

    def _build_custom_dashboard_screen(self) -> QWidget:
        scroll = QScrollArea(self.stack)
        scroll.setObjectName("analysisScreenScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        host = QWidget(scroll)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(10)

        editing = self._dashboard_edit_session is not None
        active_workspace = (
            self._dashboard_edit_session.working_workspace
            if self._dashboard_edit_session is not None
            else self.workspace
        )
        render_workspace = active_workspace if editing else active_workspace.working_copy()

        title_row = QHBoxLayout()
        title = QLabel("Dashboard", host)
        title.setObjectName("analysisScreenTitle")
        title_row.addWidget(title, 1)
        if editing:
            self._dashboard_undo_button = QPushButton("Geri Al", host)
            self._dashboard_undo_button.setObjectName("analysisDashboardUtilityButton")
            self._dashboard_undo_button.clicked.connect(self._undo_dashboard_edit)
            title_row.addWidget(self._dashboard_undo_button, 0)
            self._dashboard_redo_button = QPushButton("Yinele", host)
            self._dashboard_redo_button.setObjectName("analysisDashboardUtilityButton")
            self._dashboard_redo_button.clicked.connect(self._redo_dashboard_edit)
            title_row.addWidget(self._dashboard_redo_button, 0)
            reset_button = QPushButton("Yerleşimi Sıfırla", host)
            reset_button.setObjectName("analysisDashboardUtilityButton")
            reset_button.clicked.connect(self._reset_dashboard_edit)
            title_row.addWidget(reset_button, 0)
            title_row.addSpacing(8)
            cancel_button = QPushButton("Vazgeç", host)
            cancel_button.setObjectName("analysisDashboardCancelButton")
            cancel_button.clicked.connect(self._cancel_dashboard_edit)
            title_row.addWidget(cancel_button, 0)
            save_button = QPushButton("Kaydet", host)
            save_button.setObjectName("analysisDashboardSaveButton")
            save_button.clicked.connect(self._save_dashboard_edit)
            title_row.addWidget(save_button, 0)
        else:
            export_button = QPushButton("Excel'e Aktar", host)
            export_button.setObjectName("analysisDashboardExportButton")
            export_button.setEnabled(
                bool(self.workspace.placements) and self._dashboard_excel_thread is None
            )
            export_button.clicked.connect(self._export_dashboard_to_excel)
            self._dashboard_export_button = export_button
            title_row.addWidget(export_button, 0)
            edit_button = QPushButton("Dashboard'u Düzenle", host)
            edit_button.setObjectName("analysisDashboardEditButton")
            edit_button.setEnabled(bool(self.workspace.placements))
            edit_button.clicked.connect(self._enter_dashboard_edit)
            title_row.addWidget(edit_button, 0)
        layout.addLayout(title_row)

        hint = QFrame(host)
        hint.setObjectName("analysisDashboardHint")
        hint_layout = QHBoxLayout(hint)
        hint_layout.setContentsMargins(12, 9, 12, 9)
        hint_text = QLabel(
            (
                "Düzenleme modu: ⠿ tutamacından kartı sürükleyin, sağ-alt ◢ alanından "
                "yeniden boyutlandırın. Değişiklikler yalnız Kaydet ile yazılır."
                if editing
                else "Analiz ekranlarındaki + Dashboard düğmesiyle takip etmek istediğiniz kartları ekleyin. "
                "Kartların konumunu ve boyutunu Dashboard'u Düzenle ile değiştirebilirsiniz."
            ),
            hint,
        )
        hint_text.setObjectName("analysisDashboardHintText")
        hint_text.setWordWrap(True)
        hint_layout.addWidget(hint_text, 1)
        layout.addWidget(hint)

        custom_cards, custom_issues = self._custom_dashboard_controller.resolve_pinned_cards(
            render_workspace
        )
        cards, missing = render_workspace.resolve_cards(
            self._dashboard_items,
            additional_cards=custom_cards,
        )
        custom_missing_keys = {
            f"{CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID}:{issue.analysis_id}"
            for issue in custom_issues
        }
        prepared_missing = [key for key in missing if key not in custom_missing_keys]
        if prepared_missing:
            missing_label = QLabel(
                f"{len(prepared_missing)} dashboard kartı mevcut analiz setinde bulunamadığı için gizlendi.",
                host,
            )
            missing_label.setObjectName("analysisScreenDescription")
            missing_label.setToolTip("\n".join(prepared_missing))
            layout.addWidget(missing_label)
        if custom_issues:
            custom_warning = QLabel(
                f"{len(custom_issues)} özel analiz kartı şu anda çözümlenemedi. Dashboard yerleşimi korunuyor.",
                host,
            )
            custom_warning.setObjectName("analysisCustomDashboardWarning")
            custom_warning.setWordWrap(True)
            custom_warning.setToolTip(
                "\n".join(
                    f"{issue.analysis_id}: {issue.message}" for issue in custom_issues
                )
            )
            layout.addWidget(custom_warning)

        if not cards:
            empty = self._empty_widget(
                "Dashboard henüz boş.\n\nSol menüden bir analiz ekranı açın ve istediğiniz kartta + Dashboard düğmesine basın.",
                host,
            )
            empty.setMinimumHeight(260)
            layout.addWidget(empty)
            layout.addStretch(1)
            scroll.setWidget(host)
            self._update_dashboard_history_actions()
            return scroll

        canvas_session = self._dashboard_edit_session or DashboardEditSession(render_workspace)
        self._dashboard_canvas = DashboardCanvas(
            canvas_session,
            cards,
            lambda card, parent: self._build_card(card, dashboard_mode=True, parent=parent),
            host,
            edit_mode=editing,
            history_changed=self._update_dashboard_history_actions,
            quick_action=self._dashboard_quick_action,
        )
        layout.addWidget(self._dashboard_canvas, 1)
        scroll.setWidget(host)
        self._update_dashboard_history_actions()
        return scroll


    def _build_analysis_builder_screen(self) -> QWidget:
        self._analysis_builder_widget = AnalysisBuilderWidget(
            self._analysis_builder_controller,
            lambda card, parent: self._build_card(card, dashboard_mode=True, parent=parent),
            max_table_rows=self.settings.max_table_rows,
            parent=self.stack,
            on_saved=self._saved_analysis_changed,
            dashboard_is_pinned=self._custom_analysis_is_pinned,
            on_dashboard_toggle=self._toggle_custom_analysis_dashboard,
        )
        if self._builder_refresh_notice:
            self._analysis_builder_widget.show_data_refreshed_notice()
            self._builder_refresh_notice = False
        return self._analysis_builder_widget

    def _build_analysis_library_screen(self) -> QWidget:
        self._analysis_library_widget = AnalysisLibraryWidget(
            self._analysis_library_controller,
            lambda card, parent: self._build_card(card, dashboard_mode=True, parent=parent),
            self._open_new_analysis,
            self._edit_saved_analysis,
            on_deleted=self._saved_analysis_deleted,
            dashboard_is_pinned=self._custom_analysis_is_pinned,
            on_dashboard_toggle=self._toggle_custom_analysis_dashboard,
            on_delete=self._delete_saved_analysis,
            parent=self.stack,
        )
        if self._library_refresh_notice:
            self._analysis_library_widget.show_data_refreshed_notice()
            self._library_refresh_notice = False
        return self._analysis_library_widget

    def _open_new_analysis(self) -> None:
        self._analysis_builder_controller.reset()
        self._render_items(ANALYSIS_BUILDER_ID)

    def _edit_saved_analysis(
        self,
        analysis_id: str,
        *,
        focus_visual_settings: bool = False,
    ) -> None:
        if self.controller.analysis_service.repository_load_error() is not None:
            QMessageBox.warning(
                self,
                "Analizlerim",
                "Kaydedilmiş analizler yüklenemedi. Mevcut dosya korunuyor.",
            )
            return
        try:
            definition = self._analysis_library_controller.get_definition(analysis_id)
            self._analysis_builder_controller.load_definition(definition)
        except Exception as exc:
            message = str(exc).strip()
            QMessageBox.warning(
                self,
                "Analizlerim",
                (
                    "Kaydedilmiş analiz bulunamadı."
                    if message == "Analiz bulunamadı."
                    else f"Bu analiz mevcut veri şemasıyla düzenlenemiyor.\n\n{exc}"
                ),
            )
            return
        self._render_items(ANALYSIS_BUILDER_ID)
        if focus_visual_settings and self._analysis_builder_widget is not None:
            self._analysis_builder_widget.focus_visual_settings()

    def _saved_analysis_changed(self, _definition: object) -> None:
        analysis_id = str(getattr(_definition, "analysis_id", "") or "")
        if analysis_id and self._custom_analysis_is_pinned(analysis_id):
            self._refresh_dashboard_screen()
        if self._analysis_library_widget is not None:
            self._analysis_library_widget.refresh_items()

    def _delete_saved_analysis(self, analysis_id: str) -> bool:
        original_workspace = self.workspace.working_copy()
        candidate = self.workspace.working_copy()
        placement_removed = candidate.remove(
            CUSTOM_ANALYSIS_DASHBOARD_SOURCE_ID,
            analysis_id,
        )
        if placement_removed and not self._save_workspace(candidate):
            return False
        try:
            deleted = self._analysis_library_controller.delete(analysis_id)
        except Exception:
            if placement_removed:
                try:
                    self.workspace_store.save(self.source, original_workspace)
                except Exception:
                    self.workspace = candidate
            raise
        if not deleted:
            if placement_removed:
                try:
                    self.workspace_store.save(self.source, original_workspace)
                except Exception:
                    self.workspace = candidate
            return False
        if placement_removed:
            self.workspace = candidate
        return True

    def _saved_analysis_deleted(self, analysis_id: str) -> None:
        if self._analysis_builder_controller.current_saved_analysis_id == analysis_id:
            self._analysis_builder_controller.reset()
        self._refresh_dashboard_screen()

    def _prepared_template_definition(self, card: AnalysisCard) -> AnalysisDefinition | None:
        metrics = self._payload.get("metrics", {})
        today = parse_date(metrics.get("generated_at")) if isinstance(metrics, Mapping) else None
        definition = get_builtin_analysis_for_prepared_card(
            card,
            today=today,
            upcoming_days=self.settings.upcoming_days,
        )
        if definition is None:
            return None
        if not self._analysis_builder_controller.supports_template(definition):
            return None
        return definition

    def _copy_prepared_analysis_to_builder(self, card: AnalysisCard) -> None:
        try:
            definition = self._prepared_template_definition(card)
            if definition is None:
                raise ValueError("Bu hazır kart Analiz Oluştur ile düzenlenemiyor.")
            self._analysis_builder_controller.load_template(definition)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Analiz Oluştur",
                f"Bu hazır analiz kopyalanamadı.\n\n{exc}",
            )
            return
        self._render_items(ANALYSIS_BUILDER_ID)
        if self._analysis_builder_widget is not None:
            self._analysis_builder_widget.show_template_loaded_notice()

    def _build_screen(self, item: DashboardItem) -> QWidget:
        scroll = QScrollArea(self.stack)
        scroll.setObjectName("analysisScreenScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        host = QWidget(scroll)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(10)
        title = QLabel(item.title, host)
        title.setObjectName("analysisScreenTitle")
        layout.addWidget(title)
        if item.description:
            description = QLabel(item.description, host)
            description.setObjectName("analysisScreenDescription")
            description.setWordWrap(True)
            layout.addWidget(description)

        cards = [card for card in sorted(item.cards, key=lambda card: card.sort_order) if card.enabled]
        if not cards:
            layout.addWidget(self._empty_widget("Bu ekran için aktif analiz kartı yok."))
            layout.addStretch(1)
            scroll.setWidget(host)
            return scroll

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for column in range(4):
            grid.setColumnStretch(column, 1)

        row = 0
        column = 0
        for card in cards:
            span = self._card_span(card.size)
            if column + span > 4:
                row += 1
                column = 0
            grid.addWidget(self._build_card(card, dashboard_mode=False), row, column, 1, span)
            column += span
            if column >= 4:
                row += 1
                column = 0
        layout.addLayout(grid)
        layout.addStretch(1)
        scroll.setWidget(host)
        return scroll

    @staticmethod
    def _card_span(size: CardSize) -> int:
        if size == CardSize.SMALL:
            return 1
        if size in {CardSize.MEDIUM, CardSize.LARGE}:
            return 2
        return 4

    def _build_card(
        self,
        card: AnalysisCard,
        *,
        dashboard_mode: bool = False,
        parent: QWidget | None = None,
    ) -> QFrame:
        frame = QFrame(parent or self.stack)
        frame.setObjectName("analysisCard")
        layout = QVBoxLayout(frame)
        if dashboard_mode:
            layout.setContentsMargins(10, 8, 10, 10)
        else:
            layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6 if dashboard_mode else 8)
        frame.setMinimumSize(0, 0)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title = QLabel(card.title, frame)
        title.setObjectName("analysisCardTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        if not dashboard_mode:
            source_screen_id = str(card.screen_id or "")
            pinned = self.workspace.contains(source_screen_id, card.card_id)
            pin_button = QPushButton("✓ Dashboard'da" if pinned else "+ Dashboard", frame)
            pin_button.setObjectName("analysisPinButton")
            pin_button.setProperty("dashboardPinned", "true" if pinned else "false")
            pin_button.setToolTip("Kartı kişisel Dashboard alanına ekle veya kaldır")
            pin_button.clicked.connect(lambda _checked=False, c=card: self._toggle_dashboard_card(c))
            header.addWidget(pin_button, 0)
            if self._prepared_template_definition(card) is not None:
                template_button = QPushButton("Kopyala ve Düzenle", frame)
                template_button.setObjectName("analysisCardAction")
                template_button.setToolTip(
                    "Hazır analiz ayarlarını yeni bir özel analiz taslağına aktar"
                )
                template_button.clicked.connect(
                    lambda _checked=False, c=card: self._copy_prepared_analysis_to_builder(c)
                )
                header.addWidget(template_button, 0)
        layout.addLayout(header)
        if card.subtitle:
            subtitle = QLabel(card.subtitle, frame)
            subtitle.setObjectName("analysisCardSubtitle")
            subtitle.setWordWrap(True)
            layout.addWidget(subtitle)

        visual_settings = card.meta.get("visual_settings")
        visual_enabled = bool(card.meta.get("visual_settings_enabled")) and isinstance(visual_settings, AnalysisVisualSettings)

        if card.card_type == CardType.KPI:
            value_row = QHBoxLayout()
            value_text = format_kpi_value(card.value, visual_settings.kpi) if visual_enabled else _display_value(card.value)
            value = QLabel(value_text, frame)
            value.setObjectName("analysisKpiValue")
            value_row.addWidget(value, 0, Qt.AlignBottom)
            if card.unit:
                unit = QLabel(card.unit, frame)
                unit.setObjectName("analysisKpiUnit")
                value_row.addWidget(unit, 0, Qt.AlignBottom)
            value_row.addStretch(1)
            layout.addLayout(value_row)
            layout.addStretch(1)
            frame.setMinimumHeight(0 if dashboard_mode else 128)
        elif card.card_type == CardType.CHART:
            layout.addWidget(
                _AnalysisChartWidget(
                    card.data,
                    card.chart_type,
                    frame,
                    dashboard_mode=dashboard_mode,
                    visual_settings=visual_settings.chart if visual_enabled else None,
                ),
                1,
            )
            frame.setMinimumHeight(0 if dashboard_mode else 300)
        elif card.card_type == CardType.TABLE:
            layout.addWidget(self._build_table(card, frame), 1)
            frame.setMinimumHeight(0 if dashboard_mode else 300)
        else:
            rows = list(card.data or [])
            text = "\n".join(_display_value(item) for item in rows[:20]) if rows else "Gösterilecek veri yok"
            label = QLabel(text, frame)
            label.setObjectName("analysisEmpty")
            label.setWordWrap(True)
            layout.addWidget(label, 1)
        return frame

    def _build_table(self, card: AnalysisCard, parent: QWidget) -> QWidget:
        columns = list(card.columns or [])
        rows = table_rows(card.data, columns)
        if not columns:
            return self._empty_widget("Tablo kolonları tanımlı değil.", parent)
        if not rows:
            return self._empty_widget("Gösterilecek kayıt yok.", parent)

        table = QTableWidget(len(rows), len(columns), parent)
        table.setObjectName("analysisTable")
        table.setMinimumSize(0, 0)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setHorizontalHeaderLabels([_COLUMN_TITLES.get(column, column) for column in columns])
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(_display_value(row.get(column, "")))
                item.setToolTip(str(row.get(column, "") or ""))
                table.setItem(row_index, column_index, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        if columns:
            header.setStretchLastSection(True)
        table.resizeRowsToContents()
        return table

    @staticmethod
    def _empty_widget(text: str, parent: QWidget | None = None) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("analysisEmpty")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        return label
