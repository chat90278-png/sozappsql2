# -*- coding: utf-8 -*-
"""Non-modal personal agenda detail tool window."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.domain.agenda.constants import AgendaLifecycleType
from src.domain.agenda.models import AgendaItem
from src.domain.agenda.presentation import AgendaPresentationSnapshot
from src.ui.agenda_compact_widget import (
    _ElidedLabel,
    _severity_color,
    agenda_date_label,
    agenda_kind_label,
)


class _AgendaDetailRow(QFrame):
    selected = Signal(object)
    open_contract_requested = Signal(int)
    snooze_requested = Signal(object, str)

    def __init__(
        self,
        item: AgendaItem,
        *,
        is_new: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.item = item
        self.setObjectName("agendaDetailRow")
        self.setProperty("agendaKey", item.key)
        self.setProperty("selected", "false")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(82)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(8)

        dot = QLabel("●", self)
        dot.setObjectName("agendaDetailSeverityDot")
        dot.setFixedWidth(12)
        dot.setStyleSheet(
            f"color:{_severity_color(item)}; background:transparent; border:none;"
        )
        root.addWidget(dot, 0, Qt.AlignTop)

        center = QWidget(self)
        center.setObjectName("agendaDetailText")
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = _ElidedLabel(item.title, center)
        title.setObjectName("agendaDetailItemTitle")
        title_row.addWidget(title, 1)
        if is_new:
            badge = QLabel("YENİ", center)
            badge.setObjectName("agendaDetailNewBadge")
            title_row.addWidget(badge, 0)
        center_lay.addLayout(title_row)

        description = _ElidedLabel(item.description, center)
        description.setObjectName("agendaDetailDescription")
        center_lay.addWidget(description)

        reason_text = str(item.reason_text or "").strip()
        if reason_text:
            reason = QLabel(reason_text, center)
            reason.setObjectName("agendaDetailReason")
            reason.setWordWrap(True)
            center_lay.addWidget(reason)

        context_parts = [
            str(item.contract_no or "").strip(),
            str(item.platform or "").strip(),
        ]
        if item.system_id:
            context_parts.append(f"Sistem #{int(item.system_id)}")
        if item.delivery_id:
            context_parts.append(f"Teslimat #{int(item.delivery_id)}")
        context = QLabel(
            " · ".join(part for part in context_parts if part),
            center,
        )
        context.setObjectName("agendaDetailContext")
        center_lay.addWidget(context)
        root.addWidget(center, 1)

        right = QWidget(self)
        right.setObjectName("agendaDetailActions")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(5)
        date_label = QLabel(agenda_date_label(item), right)
        date_label.setObjectName("agendaDetailDate")
        date_label.setAlignment(Qt.AlignRight)
        right_lay.addWidget(date_label)

        if item.contract_id:
            open_btn = QPushButton("Sözleşmeyi Aç", right)
            open_btn.setObjectName("agendaDetailOpenContract")
            open_btn.clicked.connect(
                lambda _checked=False, cid=int(item.contract_id): (
                    self.open_contract_requested.emit(cid)
                )
            )
            right_lay.addWidget(open_btn)

        if (
            item.lifecycle_type == AgendaLifecycleType.CONDITION
            and item.supports_snooze
        ):
            snooze_btn = QToolButton(right)
            snooze_btn.setObjectName("agendaDetailSnooze")
            snooze_btn.setText("Ertele")
            snooze_btn.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(snooze_btn)
            menu.addAction(
                "Yarın",
                lambda: self.snooze_requested.emit(self.item, "tomorrow"),
            )
            menu.addAction(
                "3 Gün",
                lambda: self.snooze_requested.emit(self.item, "three_days"),
            )
            menu.addAction(
                "1 Hafta",
                lambda: self.snooze_requested.emit(self.item, "one_week"),
            )
            snooze_btn.setMenu(menu)
            right_lay.addWidget(snooze_btn)
        right_lay.addStretch(1)
        root.addWidget(right, 0)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.selected.emit(self.item)
        super().mousePressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.selected.emit(self.item)


class AgendaDetailWindow(QWidget):
    open_contract_requested = Signal(int)
    item_dwell_seen_requested = Signal(object)
    snooze_requested = Signal(object, str)
    refresh_requested = Signal()

    DWELL_MS = 650

    _QSS = """
    QWidget#AgendaDetailWindow { background:#e8eef5; }
    QFrame#agendaDetailHeader, QFrame#agendaDetailPanel {
        background:#ffffff;
        border:1px solid #d7e0ea;
        border-radius:15px;
    }
    QLabel#agendaDetailTitle {
        color:#0f172a;
        font-size:18px;
        font-weight:900;
    }
    QLabel#agendaDetailSummary, QLabel#agendaDetailProfile {
        color:#64748b;
        font-size:10px;
        font-weight:800;
    }
    QPushButton#agendaDetailRefresh {
        background:#eff6ff;
        color:#1554d1;
        border:1px solid #bfdbfe;
        border-radius:8px;
        padding:5px 10px;
        font-weight:800;
    }
    QWidget#agendaDetailFilters {
        background:transparent;
    }
    QPushButton#agendaDetailFilter {
        background:#ffffff;
        color:#475569;
        border:1px solid #d7e0ea;
        border-radius:8px;
        padding:4px 9px;
        font-size:10px;
        font-weight:800;
    }
    QPushButton#agendaDetailFilter:hover {
        border-color:#93c5fd;
        color:#1554d1;
    }
    QPushButton#agendaDetailFilter:checked {
        background:#dbeafe;
        color:#1d4ed8;
        border-color:#93c5fd;
    }
    QFrame#agendaDetailRow {
        background:#ffffff;
        border:1px solid #e2e8f0;
        border-radius:10px;
    }
    QFrame#agendaDetailRow:hover, QFrame#agendaDetailRow[selected="true"] {
        background:#f8fbff;
        border-color:#93c5fd;
    }
    QFrame#agendaDetailRow QLabel,
    QWidget#agendaDetailText,
    QWidget#agendaDetailActions {
        background:transparent;
        border:none;
    }
    QLabel#agendaDetailItemTitle {
        color:#203047;
        font-size:12px;
        font-weight:900;
    }
    QLabel#agendaDetailDescription, QLabel#agendaDetailContext,
    QLabel#agendaDetailReason {
        color:#64748b;
        font-size:10px;
    }
    QLabel#agendaDetailReason {
        color:#7c8ca1;
    }
    QLabel#agendaDetailDate {
        color:#52647a;
        font-size:10px;
        font-weight:900;
    }
    QLabel#agendaDetailNewBadge {
        background:#dbeafe;
        color:#1d4ed8;
        border:1px solid #93c5fd;
        border-radius:7px;
        padding:1px 6px;
        font-size:9px;
        font-weight:900;
    }
    QPushButton#agendaDetailOpenContract, QToolButton#agendaDetailSnooze {
        background:#eff6ff;
        color:#1554d1;
        border:1px solid #bfdbfe;
        border-radius:7px;
        padding:4px 8px;
        font-size:10px;
        font-weight:800;
    }
    QLabel#agendaDetailState {
        color:#64748b;
        font-size:12px;
        font-weight:700;
    }
    QScrollArea#agendaDetailScroll {
        background:transparent;
        border:none;
    }
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Tool)
        self._snapshot: AgendaPresentationSnapshot | None = None
        self._loading = False
        self._error_message: str | None = None
        self._rows: list[_AgendaDetailRow] = []
        self._filter_buttons: dict[str | None, QPushButton] = {}
        self._filter_group: QButtonGroup | None = None
        self._active_kind: str | None = None
        self._selected_item: AgendaItem | None = None
        self._emitted_seen_identities: set[tuple[str, str]] = set()

        self.setObjectName("AgendaDetailWindow")
        self.setWindowTitle("Gündemim")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(620, 420)
        self.resize(760, 560)
        self.setStyleSheet(self._QSS)

        self._dwell_timer = QTimer(self)
        self._dwell_timer.setSingleShot(True)
        self._dwell_timer.setInterval(self.DWELL_MS)
        self._dwell_timer.timeout.connect(self._emit_dwell_seen)

        self._build()
        self.set_snapshot(None)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame(self)
        header.setObjectName("agendaDetailHeader")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(14, 10, 12, 10)
        title_wrap = QWidget(header)
        title_lay = QVBoxLayout(title_wrap)
        title_lay.setContentsMargins(0, 0, 0, 0)
        title_lay.setSpacing(2)
        title = QLabel("Gündemim", title_wrap)
        title.setObjectName("agendaDetailTitle")
        self.summary_label = QLabel("", title_wrap)
        self.summary_label.setObjectName("agendaDetailSummary")
        self.profile_label = QLabel("", title_wrap)
        self.profile_label.setObjectName("agendaDetailProfile")
        title_lay.addWidget(title)
        title_lay.addWidget(self.summary_label)
        title_lay.addWidget(self.profile_label)
        header_lay.addWidget(title_wrap, 1)
        refresh = QPushButton("Yenile", header)
        refresh.setObjectName("agendaDetailRefresh")
        refresh.clicked.connect(self.refresh_requested.emit)
        header_lay.addWidget(refresh, 0, Qt.AlignVCenter)
        root.addWidget(header)

        self.filter_host = QWidget(self)
        self.filter_host.setObjectName("agendaDetailFilters")
        self.filter_layout = QHBoxLayout(self.filter_host)
        self.filter_layout.setContentsMargins(2, 0, 2, 0)
        self.filter_layout.setSpacing(6)
        root.addWidget(self.filter_host)

        panel = QFrame(self)
        panel.setObjectName("agendaDetailPanel")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(10, 10, 10, 10)
        panel_lay.setSpacing(6)

        self.state_label = QLabel("", panel)
        self.state_label.setObjectName("agendaDetailState")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setWordWrap(True)
        panel_lay.addWidget(self.state_label)

        self.scroll = QScrollArea(panel)
        self.scroll.setObjectName("agendaDetailScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll_host = QWidget(self.scroll)
        self.scroll_host.setObjectName("agendaDetailScrollHost")
        self.rows_layout = QVBoxLayout(self.scroll_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(7)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        panel_lay.addWidget(self.scroll, 1)
        root.addWidget(panel, 1)

    def set_snapshot(
        self,
        snapshot: AgendaPresentationSnapshot | None,
    ) -> None:
        self._snapshot = snapshot
        self._loading = False
        self._error_message = None
        self._active_kind = None
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

    def focus_item(self, agenda_key: str | None = None) -> None:
        key = str(agenda_key or "")
        target = next(
            (row for row in self._rows if str(row.item.key) == key),
            None,
        )
        if target is None and self._rows:
            target = self._rows[0]
        if target is not None:
            target.setFocus(Qt.OtherFocusReason)
            self.scroll.ensureWidgetVisible(target)

    def _clear_filter_buttons(self) -> None:
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._filter_buttons.clear()
        if self._filter_group is not None:
            self._filter_group.deleteLater()
        self._filter_group = QButtonGroup(self.filter_host)
        self._filter_group.setExclusive(True)

    def _render_filter_buttons(self, snapshot: AgendaPresentationSnapshot) -> None:
        self._clear_filter_buttons()
        entries: list[tuple[str | None, str]] = [(None, "Tümü")]
        for kind, raw_count in snapshot.counts_by_kind.items():
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            normalized_kind = str(kind)
            entries.append((normalized_kind, f"{agenda_kind_label(normalized_kind)} ({count})"))

        for kind, text in entries:
            button = QPushButton(text, self.filter_host)
            button.setObjectName("agendaDetailFilter")
            button.setProperty("agendaKind", "" if kind is None else kind)
            button.setCheckable(True)
            button.setChecked(kind == self._active_kind)
            button.clicked.connect(
                lambda _checked=False, selected_kind=kind: self._apply_filter(selected_kind)
            )
            self._filter_group.addButton(button)
            self.filter_layout.addWidget(button)
            self._filter_buttons[kind] = button
        self.filter_layout.addStretch(1)
        self.filter_host.show()

    def _clear_rows(self) -> None:
        self._dwell_timer.stop()
        self._selected_item = None
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()

    def _items_for_active_filter(self, snapshot: AgendaPresentationSnapshot) -> tuple[AgendaItem, ...]:
        if self._active_kind is None:
            return tuple(snapshot.detail_items)
        return tuple(
            item for item in snapshot.all_items if str(item.kind) == self._active_kind
        )

    def _render_rows(self, snapshot: AgendaPresentationSnapshot) -> None:
        self._clear_rows()
        self.state_label.hide()
        self.scroll.show()
        for agenda_item in self._items_for_active_filter(snapshot):
            row = _AgendaDetailRow(
                agenda_item,
                is_new=agenda_item.key in snapshot.new_keys,
                parent=self.scroll_host,
            )
            row.selected.connect(self._select_row)
            row.open_contract_requested.connect(self.open_contract_requested.emit)
            row.snooze_requested.connect(self.snooze_requested.emit)
            self.rows_layout.addWidget(row)
            self._rows.append(row)
        self.rows_layout.addStretch(1)

    def _apply_filter(self, kind: str | None) -> None:
        self._active_kind = kind
        for button_kind, button in self._filter_buttons.items():
            button.setChecked(button_kind == kind)
        snapshot = self._snapshot
        if snapshot is not None:
            self._render_rows(snapshot)

    def _render(self) -> None:
        self._clear_rows()
        self._clear_filter_buttons()
        snapshot = self._snapshot
        if self._loading:
            self._set_state("Yükleniyor…")
            return
        if self._error_message:
            self._set_state("Gündem yüklenemedi", tooltip=self._error_message)
            return
        if snapshot is None or not snapshot.detail_items:
            self._set_state("Şu anda gündeminiz temiz.")
            return

        summary_parts = [
            f"{snapshot.active_count} aktif",
            f"{snapshot.new_count} yeni",
        ]
        if snapshot.snoozed_count > 0:
            summary_parts.append(f"{snapshot.snoozed_count} ertelendi")
        self.summary_label.setText(" · ".join(summary_parts))
        self.profile_label.setText(str(snapshot.profile.display_name or ""))
        self._render_filter_buttons(snapshot)
        self._render_rows(snapshot)

    def _set_state(self, text: str, *, tooltip: str = "") -> None:
        self.summary_label.clear()
        self.profile_label.clear()
        self.filter_host.hide()
        self.state_label.setText(text)
        self.state_label.setToolTip(tooltip)
        self.state_label.show()
        self.scroll.hide()

    def _select_row(self, item: AgendaItem) -> None:
        self._selected_item = item
        for row in self._rows:
            row.set_selected(row.item.key == item.key)
        identity = (str(item.key or ""), str(item.version or ""))
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            frame = self.frameGeometry()
            if not available.contains(frame):
                frame.moveCenter(available.center())
                self.move(frame.topLeft())

    def hideEvent(self, event) -> None:
        self._dwell_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._dwell_timer.stop()
        super().closeEvent(event)


__all__ = ["AgendaDetailWindow"]
