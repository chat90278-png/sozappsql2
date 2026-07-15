# -*- coding: utf-8 -*-
"""Compact personal agenda card for the STS main-page header."""
from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.domain.agenda.models import AgendaItem
from src.domain.agenda.presentation import AgendaPresentationSnapshot


_SEVERITY_COLORS = {
    "CRITICAL": "#DC2626",
    "ATTENTION": "#F59E0B",
    "INFO": "#2563EB",
    "SUCCESS": "#16A34A",
}

AGENDA_KIND_LABELS = {
    "deadline": "Yaklaşan",
    "unknown_date": "Belirsiz",
    "returned_share": "Paylaşım",
    "document_lock": "Kilit",
    "activity": "Değişiklik",
}


def agenda_kind_label(kind: str) -> str:
    normalized = str(kind or "").strip()
    return AGENDA_KIND_LABELS.get(normalized, normalized)


def _top_kind_counts(snapshot: AgendaPresentationSnapshot, limit: int = 3) -> tuple[tuple[str, int], ...]:
    indexed_counts = []
    for index, (kind, raw_count) in enumerate(snapshot.counts_by_kind.items()):
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        indexed_counts.append((str(kind), count, index))
    indexed_counts.sort(key=lambda entry: (-entry[1], entry[2]))
    return tuple((kind, count) for kind, count, _index in indexed_counts[:limit])


def _severity_color(item: AgendaItem) -> str:
    return _SEVERITY_COLORS.get(
        str(getattr(item.severity, "value", item.severity) or "").upper(),
        "#2563EB",
    )


def agenda_date_label(item: AgendaItem) -> str:
    remaining = item.remaining_days
    if remaining is not None:
        value = int(remaining)
        if value < 0:
            return f"{abs(value)} gün gecikti"
        if value == 0:
            return "Bugün"
        return f"{value} gün"
    value = item.effective_date
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y")
    except Exception:
        return text[:16]


class _ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._source_text = ""
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._source_text = str(text or "")
        self._refresh_elide()

    def sourceText(self) -> str:
        return self._source_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_elide()

    def _refresh_elide(self) -> None:
        width = max(0, self.contentsRect().width())
        shown = QFontMetrics(self.font()).elidedText(
            self._source_text,
            Qt.ElideRight,
            width,
        )
        QLabel.setText(self, shown)
        self.setToolTip(self._source_text if shown != self._source_text else "")


class _CompactAgendaRow(QFrame):
    selected = Signal(object)
    open_contract_requested = Signal(int)

    def __init__(
        self,
        item: AgendaItem,
        *,
        is_new: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.item = item
        self.setObjectName("agendaCompactRow")
        self.setProperty("agendaKey", item.key)
        self.setProperty("isNew", "true" if is_new else "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedHeight(31)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 1, 3, 1)
        layout.setSpacing(6)

        dot = QLabel("●", self)
        dot.setObjectName("agendaSeverityDot")
        dot.setFixedWidth(10)
        dot.setStyleSheet(
            f"color:{_severity_color(item)}; background:transparent; border:none;"
        )
        layout.addWidget(dot, 0, Qt.AlignVCenter)

        text_wrap = QWidget(self)
        text_wrap.setObjectName("agendaCompactText")
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        title = _ElidedLabel(item.title, text_wrap)
        title.setObjectName("agendaCompactItemTitle")
        desc = _ElidedLabel(item.description, text_wrap)
        desc.setObjectName("agendaCompactItemDescription")
        text_layout.addWidget(title)
        text_layout.addWidget(desc)
        layout.addWidget(text_wrap, 1)

        date_label = QLabel(agenda_date_label(item), self)
        date_label.setObjectName("agendaCompactDate")
        date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        date_label.setMinimumWidth(64)
        layout.addWidget(date_label, 0)

        if item.contract_id:
            open_btn = QToolButton(self)
            open_btn.setObjectName("agendaCompactOpenContract")
            open_btn.setText("↗")
            open_btn.setToolTip("Sözleşmeyi aç")
            open_btn.setAccessibleName("Sözleşmeyi aç")
            open_btn.setFixedSize(22, 22)
            open_btn.clicked.connect(
                lambda _checked=False, cid=int(item.contract_id): (
                    self.open_contract_requested.emit(cid)
                )
            )
            layout.addWidget(open_btn, 0, Qt.AlignVCenter)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.selected.emit(self.item)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.item.contract_id:
            self.open_contract_requested.emit(int(self.item.contract_id))
        super().mouseDoubleClickEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.selected.emit(self.item)


class AgendaCompactWidget(QWidget):
    open_details_requested = Signal()
    open_contract_requested = Signal(int)
    item_dwell_seen_requested = Signal(object)
    snooze_requested = Signal(object, str)

    DWELL_MS = 650

    _QSS = """
    QWidget#AgendaCompactWidget {
        background:#ffffff;
        border:1.5px solid #d8e2ed;
        border-radius:12px;
    }
    QWidget#AgendaCompactWidget QLabel {
        background:transparent;
        border:none;
    }
    QLabel#agendaCompactTitle {
        color:#61738b;
        font-size:10px;
        font-weight:900;
    }
    QLabel#agendaCompactCount {
        color:#64748b;
        font-size:9px;
        font-weight:800;
    }
    QLabel#agendaCompactKindChip {
        background:#f1f5f9;
        color:#475569;
        border:1px solid #d8e2ed;
        border-radius:6px;
        padding:1px 5px;
        font-size:8px;
        font-weight:800;
    }
    QLabel#agendaCompactNewBadge {
        background:#dbeafe;
        color:#1d4ed8;
        border:1px solid #93c5fd;
        border-radius:7px;
        padding:1px 6px;
        font-size:9px;
        font-weight:900;
    }
    QFrame#agendaCompactRow {
        background:#ffffff;
        border:1px solid transparent;
        border-radius:7px;
    }
    QFrame#agendaCompactRow:hover, QFrame#agendaCompactRow:focus {
        background:#f8fbff;
        border-color:#bfdbfe;
    }
    QWidget#agendaCompactText {
        background:transparent;
        border:none;
    }
    QLabel#agendaCompactItemTitle {
        color:#203047;
        font-size:10px;
        font-weight:900;
    }
    QLabel#agendaCompactItemDescription {
        color:#6b7c91;
        font-size:9px;
    }
    QLabel#agendaCompactDate {
        color:#52647a;
        font-size:9px;
        font-weight:800;
    }
    QToolButton#agendaCompactOpenContract {
        background:#eff6ff;
        color:#1554d1;
        border:1px solid #bfdbfe;
        border-radius:6px;
        font-weight:900;
    }
    QToolButton#agendaCompactOpenContract:hover {
        background:#dbeafe;
    }
    QPushButton#agendaCompactDetails {
        background:transparent;
        color:#1554d1;
        border:none;
        padding:0;
        font-size:9px;
        font-weight:900;
        text-align:right;
    }
    QPushButton#agendaCompactDetails:hover {
        text-decoration:underline;
    }
    QLabel#agendaCompactState {
        color:#6b7c91;
        font-size:10px;
        font-weight:700;
    }
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._snapshot: AgendaPresentationSnapshot | None = None
        self._loading = False
        self._error_message: str | None = None
        self._rows: list[_CompactAgendaRow] = []
        self._kind_chips: list[QLabel] = []
        self._selected_item: AgendaItem | None = None
        self._emitted_seen_identities: set[tuple[str, str]] = set()

        self.setObjectName("AgendaCompactWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(112)
        self.setMinimumWidth(250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._QSS)

        self._dwell_timer = QTimer(self)
        self._dwell_timer.setSingleShot(True)
        self._dwell_timer.setInterval(self.DWELL_MS)
        self._dwell_timer.timeout.connect(self._emit_dwell_seen)

        self._build()
        self.clear()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 9, 6)
        root.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        title = QLabel("GÜNDEMİM", self)
        title.setObjectName("agendaCompactTitle")
        self.kind_chip_host = QWidget(self)
        self.kind_chip_host.setObjectName("agendaCompactKindChipHost")
        self.kind_chip_layout = QHBoxLayout(self.kind_chip_host)
        self.kind_chip_layout.setContentsMargins(0, 0, 0, 0)
        self.kind_chip_layout.setSpacing(3)
        self.count_label = QLabel("", self)
        self.count_label.setObjectName("agendaCompactCount")
        self.new_badge = QLabel("", self)
        self.new_badge.setObjectName("agendaCompactNewBadge")
        header.addWidget(title)
        header.addWidget(self.kind_chip_host, 0)
        header.addStretch(1)
        header.addWidget(self.count_label)
        header.addWidget(self.new_badge)
        root.addLayout(header)

        self.body = QWidget(self)
        self.body.setObjectName("agendaCompactBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(1)
        root.addWidget(self.body, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self.state_label = QLabel("", self)
        self.state_label.setObjectName("agendaCompactState")
        self.details_button = QPushButton("Tümünü Gör", self)
        self.details_button.setObjectName("agendaCompactDetails")
        self.details_button.clicked.connect(self.open_details_requested.emit)
        footer.addWidget(self.state_label, 1)
        footer.addWidget(self.details_button, 0)
        root.addLayout(footer)

    def set_snapshot(self, snapshot: AgendaPresentationSnapshot) -> None:
        self._snapshot = snapshot
        self._loading = False
        self._error_message = None
        self._selected_item = None
        self._dwell_timer.stop()
        self._render()

    def set_loading(self, loading: bool) -> None:
        self._loading = bool(loading)
        if self._loading:
            self._error_message = None
            self._dwell_timer.stop()
        self._render()

    def set_error(self, message: str | None) -> None:
        self._error_message = str(message or "").strip() or None
        self._loading = False
        self._dwell_timer.stop()
        self._render()

    def clear(self) -> None:
        self._snapshot = None
        self._loading = False
        self._error_message = None
        self._selected_item = None
        self._dwell_timer.stop()
        self._emitted_seen_identities.clear()
        self._render()

    def _clear_kind_chips(self) -> None:
        while self.kind_chip_layout.count():
            item = self.kind_chip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._kind_chips.clear()
        self.kind_chip_host.hide()

    def _render_kind_chips(self, snapshot: AgendaPresentationSnapshot) -> None:
        self._clear_kind_chips()
        for kind, count in _top_kind_counts(snapshot):
            chip = QLabel(f"{count} {agenda_kind_label(kind)}", self.kind_chip_host)
            chip.setObjectName("agendaCompactKindChip")
            chip.setProperty("agendaKind", kind)
            self.kind_chip_layout.addWidget(chip)
            self._kind_chips.append(chip)
        self.kind_chip_host.setVisible(bool(self._kind_chips))

    def _clear_rows(self) -> None:
        self._dwell_timer.stop()
        self._selected_item = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()

    def _render(self) -> None:
        self._clear_rows()
        self._clear_kind_chips()
        snapshot = self._snapshot

        if self._loading:
            self._set_state("Yükleniyor…")
            return
        if self._error_message:
            self._set_state("Gündem yüklenemedi", tooltip=self._error_message)
            return
        if snapshot is None or snapshot.active_count <= 0 or not snapshot.compact_items:
            self._set_state("Şu anda gündeminiz temiz.")
            return

        self._render_kind_chips(snapshot)
        self.state_label.clear()
        self.state_label.setToolTip("")
        self.new_badge.setVisible(snapshot.new_count > 0)
        self.new_badge.setText(
            f"{snapshot.new_count} yeni" if snapshot.new_count > 0 else ""
        )
        self.count_label.setText(
            "" if snapshot.new_count > 0 else f"{snapshot.active_count} madde"
        )
        self.details_button.setVisible(snapshot.active_count > 0)
        if snapshot.has_more:
            self.details_button.setText(f"Tümünü Gör · {snapshot.active_count}")
        else:
            self.details_button.setText("Tümünü Gör")

        for agenda_item in tuple(snapshot.compact_items)[:2]:
            row = _CompactAgendaRow(
                agenda_item,
                is_new=agenda_item.key in snapshot.new_keys,
                parent=self.body,
            )
            row.selected.connect(self._begin_dwell)
            row.open_contract_requested.connect(self.open_contract_requested.emit)
            self.body_layout.addWidget(row)
            self._rows.append(row)
        self.body_layout.addStretch(1)

    def _set_state(self, text: str, *, tooltip: str = "") -> None:
        snapshot = self._snapshot
        self.state_label.setText(text)
        self.state_label.setToolTip(tooltip)
        self.body_layout.addStretch(1)
        self.new_badge.hide()
        self.new_badge.clear()
        self.count_label.clear()
        self.details_button.setVisible(bool(snapshot and snapshot.active_count > 0))

    def _begin_dwell(self, item: AgendaItem) -> None:
        identity = (str(item.key or ""), str(item.version or ""))
        self._selected_item = item
        self._dwell_timer.stop()
        if identity in self._emitted_seen_identities:
            return
        self._dwell_timer.start(self.DWELL_MS)

    def _emit_dwell_seen(self) -> None:
        item = self._selected_item
        if item is None:
            return
        identity = (str(item.key or ""), str(item.version or ""))
        if not all(identity) or identity in self._emitted_seen_identities:
            return
        self._emitted_seen_identities.add(identity)
        self.item_dwell_seen_requested.emit(item)

    def hideEvent(self, event) -> None:
        self._dwell_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._dwell_timer.stop()
        super().closeEvent(event)


__all__ = [
    "AGENDA_KIND_LABELS",
    "AgendaCompactWidget",
    "agenda_date_label",
    "agenda_kind_label",
]
