from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton

from .widgets_legacy import *  # noqa: F401,F403
from .widgets_legacy import ActivityDetailsPanel as _ActivityDetailsPanelBase


class ActivityDetailsPanel(_ActivityDetailsPanelBase):
    """Detail panel that hides empty sections and exposes contract navigation."""

    open_contract_requested = Signal(object)

    def _build(self) -> None:
        super()._build()
        self.subtitle.setText("Seçilen kaydın özeti ve ilgili bilgiler")

        labels = {
            str(label.text() or "").strip(): label
            for label in self.findChildren(QLabel)
        }
        self.changed_title = labels.get("DEĞİŞEN ALANLAR")
        self.operation_title = labels.get("AYNI İŞLEMDEKİ HAREKETLER")

        self.open_contract_button = QPushButton("Sözleşmeye Git")
        self.open_contract_button.setObjectName("activityPrimary")
        self.open_contract_button.setAccessibleName("İlgili sözleşmeye git")
        self.open_contract_button.setVisible(False)
        self.open_contract_button.setStyleSheet(
            "QPushButton { min-height:34px; padding:0 13px; border:none; "
            "border-radius:9px; background:#1f5fe0; color:#ffffff; "
            "font-weight:800; } "
            "QPushButton:hover { background:#174fc1; } "
            "QPushButton:pressed { background:#123f9c; }"
        )
        self.open_contract_button.clicked.connect(self._request_contract_open)

        content = self.scroll.widget()
        layout = content.layout() if content is not None else None
        if layout is not None:
            # Heading, subtitle, title, summary and meta come first in the base panel.
            layout.insertWidget(5, self.open_contract_button)

    def _request_contract_open(self) -> None:
        if self._item is not None and str(self._item.contract_no or "").strip():
            self.open_contract_requested.emit(self._item)

    def _set_section_visible(self, title, widget, visible: bool) -> None:
        if title is not None:
            title.setVisible(bool(visible))
        widget.setVisible(bool(visible))

    def clear(self) -> None:
        super().clear()
        self._set_section_visible(
            getattr(self, "changed_title", None),
            self.changed,
            False,
        )
        self._set_section_visible(
            getattr(self, "operation_title", None),
            self.operation_events,
            False,
        )
        if hasattr(self, "open_contract_button"):
            self.open_contract_button.setVisible(False)

    def set_item(
        self,
        item: ActivityHistoryItem,
        operation_events: Iterable[ActivityHistoryItem] = (),
    ) -> None:
        events = tuple(operation_events)
        super().set_item(item, events)

        has_changes = bool(item.changed_fields or item.changed_fields_parse_error)
        if not has_changes:
            self.changed.clear()
        self._set_section_visible(
            getattr(self, "changed_title", None),
            self.changed,
            has_changes,
        )

        has_events = bool(events)
        if not has_events:
            self.operation_events.clear()
        self._set_section_visible(
            getattr(self, "operation_title", None),
            self.operation_events,
            has_events,
        )

        has_contract = bool(str(item.contract_no or "").strip())
        self.open_contract_button.setVisible(has_contract)
        self.open_contract_button.setEnabled(has_contract)
        self.open_contract_button.setToolTip(
            f"{item.contract_no} sözleşmesini aç" if has_contract else ""
        )
