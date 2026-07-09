# -*- coding: utf-8 -*-
"""Compact main-page contract status widget."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class ContractStatusSummary:
    """Display values produced from Analysis Center contract metrics."""

    total_contracts: int = 0
    completed_contracts: int = 0
    in_progress_contracts: int = 0
    not_started_contracts: int = 0

    @classmethod
    def from_metrics(cls, metrics: Mapping[str, Any]) -> "ContractStatusSummary":
        return cls(
            total_contracts=int(metrics.get("total_contracts", 0) or 0),
            completed_contracts=int(metrics.get("completed_contract_count", 0) or 0),
            in_progress_contracts=int(metrics.get("in_progress_contract_count", 0) or 0),
            not_started_contracts=int(metrics.get("not_started_contract_count", 0) or 0),
        ).normalized()

    def normalized(self) -> "ContractStatusSummary":
        total = max(0, int(self.total_contracts or 0))
        if total <= 0:
            return ContractStatusSummary()
        return ContractStatusSummary(
            total_contracts=total,
            completed_contracts=min(total, max(0, int(self.completed_contracts or 0))),
            in_progress_contracts=min(total, max(0, int(self.in_progress_contracts or 0))),
            not_started_contracts=min(total, max(0, int(self.not_started_contracts or 0))),
        )

    @property
    def completed_percent(self) -> int:
        data = self.normalized()
        if data.total_contracts <= 0:
            return 0
        return round((data.completed_contracts / data.total_contracts) * 100)


class ContractStatusBar(QWidget):
    """Three-segment status distribution bar with a rounded outer clip."""

    _SEGMENTS = (
        ("completed_contracts", "#10b981"),
        ("in_progress_contracts", "#3b82f6"),
        ("not_started_contracts", "#f59e0b"),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._summary = ContractStatusSummary()
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_summary(self, summary: ContractStatusSummary) -> None:
        self._summary = summary.normalized()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        bounds = QRectF(self.rect())
        radius = bounds.height() / 2.0
        clip = QPainterPath()
        clip.addRoundedRect(bounds, radius, radius)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor("#e8eef5"))

        data = self._summary.normalized()
        counts = [int(getattr(data, field_name) or 0) for field_name, _color in self._SEGMENTS]
        denominator = max(data.total_contracts, sum(counts))
        if denominator <= 0:
            return

        x = 0
        for (_field_name, color), count in zip(self._SEGMENTS, counts):
            if count <= 0:
                continue
            width = round(self.width() * (count / denominator))
            width = max(0, min(width, self.width() - x))
            if width <= 0:
                continue
            painter.fillRect(x, 0, width, self.height(), QColor(color))
            x += width


class ContractStatusSummaryWidget(QFrame):
    """112 px main-page box that mirrors Analysis Center contract metrics."""

    open_analysis_requested = Signal()

    _STYLE = r"""
    QFrame#contractStatusSummaryWidget {
        background:#ffffff;
        border:1px solid #d6e0ec;
        border-radius:12px;
    }
    QWidget#contractStatusTotalPanel {
        background:transparent;
        border:none;
        border-right:1px solid #e2e8f0;
    }
    QLabel#contractStatusTotalValue {
        background:transparent;
        color:#0f2b61;
        border:none;
        font-size:29px;
        font-weight:900;
    }
    QLabel#contractStatusTotalLabel {
        background:transparent;
        color:#64748b;
        border:none;
        font-size:8px;
        font-weight:900;
    }
    QLabel#contractStatusTitle {
        background:transparent;
        color:#75849a;
        border:none;
        font-size:9px;
        font-weight:900;
    }
    QLabel#contractStatusPercent {
        background:transparent;
        color:#94a3b8;
        border:none;
        font-size:8px;
    }
    QLabel#contractStatusLegend {
        background:transparent;
        color:#64748b;
        border:none;
        font-size:8px;
        font-weight:800;
    }
    QPushButton#contractStatusOpenButton {
        width:28px;
        height:28px;
        min-width:28px;
        max-width:28px;
        min-height:28px;
        max-height:28px;
        background:#eff6ff;
        color:#1554d1;
        border:1px solid #a9c7ff;
        border-radius:8px;
        padding:0;
        font-size:15px;
        font-weight:900;
    }
    QPushButton#contractStatusOpenButton:hover { background:#dbeafe; }
    QPushButton#contractStatusOpenButton:pressed { background:#bfdbfe; }
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._summary = ContractStatusSummary()
        self.setObjectName("contractStatusSummaryWidget")
        self.setFixedHeight(112)
        self.setMinimumWidth(390)
        self.setMaximumWidth(570)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._STYLE)
        self._build_ui()
        self.set_summary(self._summary)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        total_panel = QWidget(self)
        total_panel.setObjectName("contractStatusTotalPanel")
        total_panel.setFixedWidth(120)
        total_layout = QVBoxLayout(total_panel)
        total_layout.setContentsMargins(6, 0, 10, 0)
        total_layout.setSpacing(0)
        total_layout.addStretch(1)

        self.total_value = QLabel("0", total_panel)
        self.total_value.setObjectName("contractStatusTotalValue")
        self.total_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        total_layout.addWidget(self.total_value)
        total_layout.addSpacing(5)

        total_label = QLabel("TOPLAM SÖZLEŞME", total_panel)
        total_label.setObjectName("contractStatusTotalLabel")
        total_layout.addWidget(total_label)
        total_layout.addStretch(1)
        root.addWidget(total_panel, 0)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 1, 0, 1)
        content_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("SÖZLEŞME DURUMU", content)
        title.setObjectName("contractStatusTitle")
        self.percent_label = QLabel("%0 tamamlandı", content)
        self.percent_label.setObjectName("contractStatusPercent")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.percent_label)
        content_layout.addLayout(title_row)
        content_layout.addSpacing(9)

        self.status_bar = ContractStatusBar(content)
        content_layout.addWidget(self.status_bar)
        content_layout.addSpacing(7)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(4)
        self.completed_label = self._legend_label(content)
        self.in_progress_label = self._legend_label(content)
        self.not_started_label = self._legend_label(content)
        legend_row.addWidget(self.completed_label, 1)
        legend_row.addWidget(self.in_progress_label, 1)
        legend_row.addWidget(self.not_started_label, 1)
        content_layout.addLayout(legend_row)
        content_layout.addStretch(1)
        root.addWidget(content, 1)

        self.open_button = QPushButton(">", self)
        self.open_button.setObjectName("contractStatusOpenButton")
        self.open_button.setToolTip("Analiz Merkezi'ni aç")
        self.open_button.clicked.connect(self.open_analysis_requested.emit)
        root.addWidget(self.open_button, 0, Qt.AlignVCenter)

    @staticmethod
    def _legend_label(parent: QWidget) -> QLabel:
        label = QLabel(parent)
        label.setObjectName("contractStatusLegend")
        label.setTextFormat(Qt.RichText)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return label

    @staticmethod
    def _legend_text(color: str, count: int, label: str) -> str:
        return (
            f'<span style="color:{color};">●</span> '
            f'<b style="color:#334155;">{int(count)}</b> {label}'
        )

    def set_summary(self, summary: ContractStatusSummary) -> None:
        self._summary = summary.normalized()
        data = self._summary
        self.total_value.setText(str(data.total_contracts))
        self.percent_label.setText(f"%{data.completed_percent} tamamlandı")
        self.completed_label.setText(
            self._legend_text("#10b981", data.completed_contracts, "tamamlandı")
        )
        self.in_progress_label.setText(
            self._legend_text("#3b82f6", data.in_progress_contracts, "devam ediyor")
        )
        self.not_started_label.setText(
            self._legend_text("#f59e0b", data.not_started_contracts, "başlanmadı")
        )
        self.status_bar.set_summary(data)

    def clear_summary(self) -> None:
        self.set_summary(ContractStatusSummary())

    def summary(self) -> ContractStatusSummary:
        return self._summary


__all__ = [
    "ContractStatusSummary",
    "ContractStatusBar",
    "ContractStatusSummaryWidget",
]
