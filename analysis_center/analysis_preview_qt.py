from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from .analysis_models import AnalysisCard, CardType, ChartType


class AnalysisPreviewCardHost(QFrame):
    """Centers a responsive analysis card inside sensible preview-only bounds."""

    def __init__(
        self,
        card: AnalysisCard,
        card_widget: QWidget,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.card = card
        self.card_widget = card_widget
        self.setObjectName("analysisPreviewCardHost")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)
        row.addWidget(card_widget)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    @property
    def preview_maximum_size(self) -> QSize:
        if self.card.card_type == CardType.KPI:
            return QSize(680, 230)
        if self.card.card_type == CardType.TABLE:
            return QSize(1100, 620)
        if self.card.card_type == CardType.CHART and self.card.chart_type == ChartType.DONUT:
            return QSize(760, 460)
        if self.card.card_type == CardType.CHART:
            return QSize(920, 520)
        return QSize(900, 520)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._resize_card()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._resize_card()

    def _resize_card(self) -> None:
        available_width = max(0, self.width() - 24)
        available_height = max(0, self.height() - 24)
        if available_width <= 0 or available_height <= 0:
            return
        maximum = self.preview_maximum_size
        self.card_widget.setFixedSize(
            min(available_width, maximum.width()),
            min(available_height, maximum.height()),
        )


__all__ = ["AnalysisPreviewCardHost"]
