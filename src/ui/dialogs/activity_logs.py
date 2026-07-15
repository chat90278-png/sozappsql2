from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QCompleter,
    QLabel,
    QMessageBox,
    QSizePolicy,
)

from src.services.activity_history_query import ActivityHistoryItem, ActivityHistoryQuery

from .activity_logs_legacy import *  # noqa: F401,F403
from .activity_logs_legacy import ActivityLogDialog as _ActivityLogDialogBase


class ActivityPlatformComboBox(QComboBox):
    """Editable platform picker with a modern overlay chevron."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chevron = QLabel("⌄", self)
        self.chevron.setObjectName("activityFilterChevron")
        self.chevron.setAlignment(Qt.AlignCenter)
        self.chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.chevron.setAccessibleName("")
        self.chevron.show()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = 30
        self.chevron.setGeometry(max(0, self.width() - width), 0, width, self.height())
        self.chevron.raise_()

    def text(self) -> str:
        return self.currentText()

    def setText(self, value: str) -> None:
        text = str(value or "").strip()
        index = self.findData(text)
        if index < 0:
            index = self.findText(text, Qt.MatchFixedString)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(text)


class ActivityLogDialog(_ActivityLogDialogBase):
    """Activity History dialog with platform picker and contract navigation."""

    ALL_PLATFORMS_LABEL = "Tüm platformlar"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._replace_platform_filter()
        if hasattr(self.details, "open_contract_requested"):
            self.details.open_contract_requested.connect(
                self._open_contract_from_history
            )

    def _platform_names(self) -> tuple[str, ...]:
        values: list[str] = []
        adapter = getattr(self.store, "platform_names", None)
        if callable(adapter):
            try:
                values.extend(str(value or "").strip() for value in adapter())
            except Exception:
                pass
        values.extend(
            str(item.platform_name or "").strip()
            for item in getattr(self, "items", ())
        )

        unique: dict[str, str] = {}
        for value in values:
            if value:
                unique.setdefault(value.casefold(), value)
        return tuple(sorted(unique.values(), key=str.casefold))

    def _populate_platform_filter(
        self,
        *,
        preserve_text: str = "",
    ) -> None:
        if not isinstance(self.platform, QComboBox):
            return
        selected = str(preserve_text or self._selected_platform_text()).strip()
        self.platform.blockSignals(True)
        self.platform.clear()
        self.platform.addItem(self.ALL_PLATFORMS_LABEL, "")
        for name in self._platform_names():
            self.platform.addItem(name, name)
        index = self.platform.findData(selected)
        if index >= 0:
            self.platform.setCurrentIndex(index)
        elif selected:
            self.platform.setEditText(selected)
        else:
            self.platform.setCurrentIndex(0)
        self.platform.blockSignals(False)

    def _replace_widget_in_layout(self, layout, old_widget, new_widget) -> bool:
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is old_widget:
                stretch = layout.stretch(index) if isinstance(layout, QBoxLayout) else 0
                alignment = item.alignment()
                layout.removeWidget(old_widget)
                if isinstance(layout, QBoxLayout):
                    layout.insertWidget(index, new_widget, stretch, alignment)
                else:
                    layout.addWidget(new_widget)
                return True
            child_layout = item.layout()
            if child_layout is not None and self._replace_widget_in_layout(
                child_layout,
                old_widget,
                new_widget,
            ):
                return True
        return False

    def _replace_platform_filter(self) -> None:
        old_platform = self.platform
        combo = ActivityPlatformComboBox(old_platform.parentWidget())
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMaxVisibleItems(14)
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setAccessibleName("Platform filtresi")
        self._apply_filter_style(combo)

        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("Platform seç veya ara")
            line_edit.setClearButtonEnabled(True)

        completer = combo.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)

        parent_layout = old_platform.parentWidget().layout()
        if parent_layout is None or not self._replace_widget_in_layout(
            parent_layout,
            old_platform,
            combo,
        ):
            raise RuntimeError("Platform filtresi yerleşimde bulunamadı.")

        old_platform.hide()
        old_platform.setParent(None)
        old_platform.deleteLater()
        self.platform = combo
        self._populate_platform_filter()

        combo.currentIndexChanged.connect(
            lambda _=0: self.refresh_logs(reset=True)
        )
        if combo.lineEdit() is not None:
            combo.lineEdit().textEdited.connect(self._schedule_search)

    def _selected_platform_text(self) -> str:
        if not isinstance(self.platform, QComboBox):
            return ""
        data = self.platform.currentData()
        if data:
            return str(data).strip()
        text = str(self.platform.currentText() or "").strip()
        if text.casefold() == self.ALL_PLATFORMS_LABEL.casefold():
            return ""
        return text

    def _accept_page(self, page, *, generation: int, reset: bool) -> bool:
        accepted = super()._accept_page(
            page,
            generation=generation,
            reset=reset,
        )
        if accepted and isinstance(self.platform, QComboBox):
            current = self._selected_platform_text()
            known = {
                str(self.platform.itemData(index) or "").casefold()
                for index in range(self.platform.count())
            }
            discovered = {
                str(item.platform_name or "").strip()
                for item in self.items
                if str(item.platform_name or "").strip()
            }
            if any(value.casefold() not in known for value in discovered):
                self._populate_platform_filter(preserve_text=current)
        return accepted

    def clear_filters(self) -> None:
        for widget in (self.search, self.actor, self.contract_no):
            widget.blockSignals(True)
            widget.clear()
            widget.blockSignals(False)

        self.platform.blockSignals(True)
        self.platform.setCurrentIndex(0)
        self.platform.blockSignals(False)

        for edit in (self.date_from, self.date_to):
            edit.blockSignals(True)
            edit.setDate(edit.minimumDate())
            edit.blockSignals(False)

        self.action.blockSignals(True)
        self.action.setCurrentIndex(0)
        self.action.blockSignals(False)

        self.limit.blockSignals(True)
        self.limit.setCurrentIndex(0)
        self.limit.blockSignals(False)
        self.refresh_logs(reset=True)

    def build_query(self, *, cursor: str | None = None) -> ActivityHistoryQuery:
        start, end = self._validate_dates()
        return ActivityHistoryQuery(
            categories=(self._active_category,),
            actions=(str(self.action.currentData()),)
            if self.action.currentData()
            else (),
            actor_text=self.actor.text().strip(),
            search_text=self.search.text().strip(),
            platform_text=self._selected_platform_text(),
            contract_no=self.contract_no.text().strip(),
            occurred_from_utc=start,
            occurred_to_utc=end,
            limit=int(self.limit.currentData() or 50),
            cursor=cursor,
        )

    def _main_window_host(self):
        host = self.parentWidget()
        while host is not None:
            if callable(getattr(host, "open_contract_item", None)):
                return host
            host = host.parentWidget()
        return None

    def _contract_candidate(self, host, item: ActivityHistoryItem):
        contract_no = str(item.contract_no or "").strip()
        platform_name = str(item.platform_name or "").strip()
        if not contract_no:
            return None

        rows = list(getattr(host, "contract_index", ()) or ())
        if not rows:
            builder = getattr(self.store, "build_contract_index", None)
            if callable(builder):
                try:
                    rows = list(builder() or ())
                except Exception:
                    rows = []

        exact = [
            row
            for row in rows
            if str(row.get("no") or row.get("contract_no") or "").strip()
            == contract_no
            and (
                not platform_name
                or str(row.get("platform") or "").strip() == platform_name
            )
        ]
        if exact:
            return exact[0]

        by_number = [
            row
            for row in rows
            if str(row.get("no") or row.get("contract_no") or "").strip()
            == contract_no
        ]
        return by_number[0] if len(by_number) == 1 else None

    def _open_contract_from_history(self, item: ActivityHistoryItem) -> None:
        host = self._main_window_host()
        candidate = self._contract_candidate(host, item) if host is not None else None
        if host is None or candidate is None:
            QMessageBox.information(
                self,
                "Sözleşme bulunamadı",
                "İlgili sözleşme mevcut sözleşme listesinde bulunamadı.",
            )
            return

        opener = host.open_contract_item
        self.accept()
        QTimer.singleShot(0, lambda: opener(candidate))
