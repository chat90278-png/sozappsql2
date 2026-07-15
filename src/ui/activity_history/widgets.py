from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.services.activity_history_infra import (
    PATH_LIKE_KEYS,
    SENSITIVE_KEYS,
    redact_path_value,
    sanitize_activity_value,
)
from src.services.activity_history_query import ActivityHistoryItem
from src.ui.activity_history.labels import visible_action_label


def parse_activity_datetime(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, tz=timezone.utc).astimezone()
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.fromtimestamp(0, tz=timezone.utc).astimezone()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def format_activity_time(value: str) -> str:
    return parse_activity_datetime(value).strftime("%H:%M")


def format_activity_datetime(value: str) -> str:
    return parse_activity_datetime(value).strftime("%d.%m.%Y · %H:%M")


def activity_day_label(value: str, now: datetime | None = None) -> str:
    local = parse_activity_datetime(value)
    reference = (now or datetime.now().astimezone()).astimezone()
    delta = (reference.date() - local.date()).days
    if delta == 0:
        return f"Bugün · {local.strftime('%d.%m.%Y')}"
    if delta == 1:
        return f"Dün · {local.strftime('%d.%m.%Y')}"
    return local.strftime("%d.%m.%Y")


def bounded_display(value: Any, *, max_chars: int = 320) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        text = "Evet" if value else "Hayır"
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    else:
        text = str(value)
    text = text.replace("\x00", "")
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def safe_ui_payload(value: Any, *, key: str = "") -> Any:
    normalized_key = str(key or "").strip().casefold()
    if normalized_key in SENSITIVE_KEYS:
        return "[REDACTED]"
    if normalized_key in PATH_LIKE_KEYS:
        return redact_path_value(value)
    if isinstance(value, dict):
        return {str(k): safe_ui_payload(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_ui_payload(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if (":\\" in text or text.startswith("/") or text.startswith("\\\\")) and (
            "/" in text or "\\" in text
        ):
            return redact_path_value(text)
    return sanitize_activity_value(value)


def status_text(status: str) -> str:
    return {"SUCCESS": "Başarılı", "FAILED": "Başarısız", "PARTIAL": "Kısmi"}.get(
        str(status or "").upper(), str(status or "—")
    )


class TimelineCard(QFrame):
    selected = Signal(object)

    def __init__(self, item: ActivityHistoryItem, parent: QWidget | None = None):
        super().__init__(parent)
        self.item = item
        self.display_action_label = visible_action_label(item.action, item.action_label)
        self.setObjectName("activityTimelineCard")
        self.setProperty("selected", False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{self.display_action_label}: {item.summary}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(76)
        self.setMaximumHeight(92)
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(9)

        self.icon = QLabel(self._icon_text())
        self.icon.setObjectName("activityCardIcon")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(32, 32)
        self.icon.setStyleSheet(self._icon_style())
        root.addWidget(self.icon, 0, Qt.AlignTop)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        title = QLabel(self.display_action_label)
        title.setObjectName("activityCardTitle")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title.setToolTip(self.display_action_label)
        top.addWidget(title, 1)
        time_label = QLabel(format_activity_time(self.item.occurred_at))
        time_label.setObjectName("activityCardTime")
        top.addWidget(time_label, 0, Qt.AlignRight | Qt.AlignTop)
        content.addLayout(top)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(8)
        actor = QLabel(self.item.actor_display_name)
        actor.setObjectName("activityCardActor")
        actor.setMinimumWidth(0)
        actor.setToolTip(self.item.actor_display_name)
        middle.addWidget(actor, 0)

        summary = QLabel(self.item.summary)
        summary.setObjectName("activityCardSummary")
        summary.setWordWrap(False)
        summary.setMinimumWidth(0)
        summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        summary.setToolTip(self.item.summary)
        middle.addWidget(summary, 1)
        content.addLayout(middle)

        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(4)
        for text in self._chips():
            chip = QLabel(text)
            chip.setObjectName("activityChip")
            chip.setToolTip(text)
            chips.addWidget(chip)
        status = QLabel(status_text(self.item.status))
        status.setObjectName(
            "activityStatusFailed"
            if self.item.status == "FAILED"
            else "activityStatusPartial"
            if self.item.status == "PARTIAL"
            else "activityStatusSuccess"
        )
        chips.addWidget(status)
        chips.addStretch(1)
        content.addLayout(chips)

        root.addLayout(content, 1)

    def _chips(self) -> list[str]:
        values: list[str] = []
        if self.item.platform_name:
            values.append(self.item.platform_name)
        if self.item.contract_no:
            values.append(self.item.contract_no)
        if self.item.entity_label or self.item.entity_type:
            values.append(self.item.entity_label or self.item.entity_type or "")
        if self.item.operation_group_key:
            values.append("Gruplu işlem")
        return [value for value in values if value][:4]

    def _icon_text(self) -> str:
        if self.item.category == "MANAGEMENT":
            return "Y"
        if self.item.category == "TECHNICAL":
            return "⚙"
        entity = str(self.item.entity_type or "").casefold()
        return {"contract": "S", "document": "D", "delivery": "T", "system": "B"}.get(entity, "İ")

    def _icon_style(self) -> str:
        if self.item.category == "MANAGEMENT":
            return "background:#f3efff;color:#6c48c7;border-radius:9px;font-weight:900;"
        if self.item.category == "TECHNICAL":
            return "background:#f1f3f6;color:#64748b;border-radius:9px;font-weight:900;"
        return "background:#eaf1ff;color:#1f5fe0;border-radius:9px;font-weight:900;"

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.item)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.selected.emit(self.item)
            event.accept()
            return
        super().keyPressEvent(event)


class ActivityTimelineView(QScrollArea):
    item_selected = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("activityTimelineScroll")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._now_provider = now_provider or (lambda: datetime.now().astimezone())
        self._items: list[ActivityHistoryItem] = []
        self._cards: dict[int, TimelineCard] = {}
        self._selected_id: int | None = None

        self._content = QWidget()
        self._content.setObjectName("activityTimelineContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(7)
        self._layout.addStretch(1)
        self.setWidget(self._content)

    @property
    def items(self) -> tuple[ActivityHistoryItem, ...]:
        return tuple(self._items)

    @property
    def group_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        for index in range(self._layout.count() - 1):
            widget = self._layout.itemAt(index).widget()
            if widget is not None:
                labels.append(str(widget.property("dayLabel") or ""))
        return tuple(labels)

    def set_items(self, items: Iterable[ActivityHistoryItem]) -> None:
        self._items = list(items)
        self._selected_id = None
        self._rebuild()

    def append_items(self, items: Iterable[ActivityHistoryItem]) -> None:
        known = {item.id for item in self._items}
        self._items.extend(item for item in items if item.id not in known)
        self._rebuild()

    def clear_selection(self) -> None:
        self._selected_id = None
        for card in self._cards.values():
            card.set_selected(False)

    def select_item(self, item_id: int) -> None:
        self._selected_id = item_id
        for key, card in self._cards.items():
            card.set_selected(key == item_id)

    def _rebuild(self) -> None:
        while self._layout.count():
            child = self._layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        self._cards.clear()
        grouped: OrderedDict[str, list[ActivityHistoryItem]] = OrderedDict()
        for item in self._items:
            grouped.setdefault(
                activity_day_label(item.occurred_at, self._now_provider()), []
            ).append(item)

        for label, day_items in grouped.items():
            day = QFrame()
            day.setObjectName("activityTimelineDay")
            day.setProperty("dayLabel", label)
            layout = QVBoxLayout(day)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(5)

            header = QHBoxLayout()
            header.setContentsMargins(2, 0, 2, 1)
            title = QLabel(label)
            title.setObjectName("activityDayTitle")
            count = QLabel(f"{len(day_items)} işlem")
            count.setObjectName("activityDayCount")
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(count)
            layout.addLayout(header)

            for item in day_items:
                card = TimelineCard(item)
                card.selected.connect(self._on_selected)
                card.set_selected(item.id == self._selected_id)
                self._cards[item.id] = card
                layout.addWidget(card)

            self._layout.addWidget(day)

        self._layout.addStretch(1)

    def _on_selected(self, item: ActivityHistoryItem) -> None:
        self.select_item(item.id)
        self.item_selected.emit(item)


class ActivityHistoryTableModel(QAbstractTableModel):
    HEADERS = (
        "Tarih / Saat",
        "İşlem",
        "Kullanıcı",
        "Varlık / Kayıt",
        "Platform",
        "Sözleşme",
        "Durum",
    )

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._items: list[ActivityHistoryItem] = []

    @property
    def items(self) -> tuple[ActivityHistoryItem, ...]:
        return tuple(self._items)

    def set_items(self, items: Iterable[ActivityHistoryItem]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: N802
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        values = (
            format_activity_datetime(item.occurred_at),
            visible_action_label(item.action, item.action_label),
            item.actor_display_name,
            item.entity_label or item.entity_type or "—",
            item.platform_name or "—",
            item.contract_no or "—",
            status_text(item.status),
        )
        value = values[index.column()]
        if role == Qt.DisplayRole:
            return value
        if role == Qt.ToolTipRole:
            return bounded_display(value, max_chars=700)
        if role == Qt.UserRole:
            return item
        if role == Qt.TextAlignmentRole and index.column() in (0, 6):
            return int(Qt.AlignCenter)
        return None

    def item_at(self, row: int) -> ActivityHistoryItem | None:
        return self._items[row] if 0 <= row < len(self._items) else None


class ActivityDetailsPanel(QFrame):
    copy_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("activityDetailsPanel")
        self.setMinimumWidth(300)
        self._item: ActivityHistoryItem | None = None
        self._build()
        self.clear()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(7)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        self.heading = QLabel("İşlem Ayrıntısı")
        self.heading.setObjectName("activityDetailsTitle")
        root.addWidget(self.heading)

        self.subtitle = QLabel("Seçilen kaydın özeti ve değişen alanları")
        self.subtitle.setObjectName("activityMuted")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)

        self.title = QLabel()
        self.title.setObjectName("activityDetailRecordTitle")
        self.title.setWordWrap(True)
        root.addWidget(self.title)

        self.summary = QLabel()
        self.summary.setObjectName("activityDetailSummary")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.meta = QLabel()
        self.meta.setObjectName("activityDetailMeta")
        self.meta.setWordWrap(True)
        root.addWidget(self.meta)

        changed_title = QLabel("DEĞİŞEN ALANLAR")
        changed_title.setObjectName("activitySectionTitle")
        root.addWidget(changed_title)

        self.changed = QTreeWidget()
        self.changed.setObjectName("activityChanges")
        self.changed.setHeaderLabels(["Alan", "Önce", "Sonra"])
        self.changed.setRootIsDecorated(False)
        self.changed.setAlternatingRowColors(True)
        self.changed.setMinimumHeight(112)
        self.changed.header().setStretchLastSection(True)
        self.changed.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.changed.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.changed.header().setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.changed, 1)

        operation_title = QLabel("AYNI İŞLEMDEKİ HAREKETLER")
        operation_title.setObjectName("activitySectionTitle")
        root.addWidget(operation_title)

        self.operation_events = QListWidget()
        self.operation_events.setObjectName("activityOperationEvents")
        self.operation_events.setMinimumHeight(72)
        root.addWidget(self.operation_events)

        self.technical_toggle = QToolButton()
        self.technical_toggle.setObjectName("activityTechnicalToggle")
        self.technical_toggle.setText("Teknik ayrıntılar")
        self.technical_toggle.setCheckable(True)
        self.technical_toggle.setChecked(False)
        self.technical_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.technical_toggle.setArrowType(Qt.RightArrow)
        self.technical_toggle.toggled.connect(self._toggle_technical)
        root.addWidget(self.technical_toggle)

        self.technical_text = QPlainTextEdit()
        self.technical_text.setObjectName("activityTechnicalText")
        self.technical_text.setReadOnly(True)
        self.technical_text.setVisible(False)
        self.technical_text.setMaximumHeight(180)
        root.addWidget(self.technical_text)

        self.copy_button = QPushButton("Gösterilen teknik metni kopyala")
        self.copy_button.setObjectName("activitySecondary")
        self.copy_button.setVisible(False)
        self.copy_button.clicked.connect(
            lambda: self.copy_requested.emit(self.technical_text.toPlainText())
        )
        root.addWidget(self.copy_button)

    def _toggle_technical(self, visible: bool) -> None:
        self.technical_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)
        self.technical_text.setVisible(visible)
        self.copy_button.setVisible(visible and bool(self.technical_text.toPlainText()))

    def clear(self) -> None:
        self._item = None
        self.title.setText("Bir işlem seçin")
        self.summary.setText(
            "Zaman akışından veya özet tablodan bir kayıt seçildiğinde ayrıntılar burada görünür."
        )
        self.meta.setText("")
        self.changed.clear()
        self.operation_events.clear()
        self.technical_toggle.setVisible(False)
        self.technical_text.clear()
        self.technical_text.setVisible(False)
        self.copy_button.setVisible(False)

    def set_item(
        self,
        item: ActivityHistoryItem,
        operation_events: Iterable[ActivityHistoryItem] = (),
    ) -> None:
        self._item = item
        action_label = visible_action_label(item.action, item.action_label)
        self.title.setText(item.title or action_label)
        self.summary.setText(item.summary)

        first_line = " · ".join(
            [
                format_activity_datetime(item.occurred_at),
                item.actor_display_name,
                status_text(item.status),
            ]
        )
        second_line = " · ".join(
            value
            for value in (
                item.entity_label or item.entity_type or "—",
                item.platform_name or "—",
                item.contract_no or "—",
            )
            if value and value != "—"
        )
        self.meta.setText(first_line + (f"\n{second_line}" if second_line else ""))

        self.changed.clear()
        if item.changed_fields:
            for change in item.changed_fields:
                row = QTreeWidgetItem(
                    [
                        change.field,
                        bounded_display(change.before),
                        bounded_display(change.after),
                    ]
                )
                for column in range(3):
                    row.setToolTip(
                        column,
                        bounded_display(
                            (change.field, change.before, change.after)[column],
                            max_chars=700,
                        ),
                    )
                self.changed.addTopLevelItem(row)
        else:
            note = "Alan bazlı değişiklik bilgisi bulunmuyor"
            if item.changed_fields_parse_error:
                note += "; kayıt güvenli biçimde gösterildi."
            self.changed.addTopLevelItem(QTreeWidgetItem([note, "", ""]))

        self.operation_events.clear()
        for event in operation_events:
            event_label = visible_action_label(event.action, event.action_label)
            QListWidgetItem(
                f"{format_activity_time(event.occurred_at)} · {event_label} · {event.summary}",
                self.operation_events,
            )
        if not self.operation_events.count():
            QListWidgetItem(
                "Bu işlem için başka izinli hareket bulunmuyor.",
                self.operation_events,
            )

        technical = item.technical
        self.technical_toggle.setVisible(technical is not None)
        self.technical_toggle.setChecked(False)
        self.technical_text.clear()
        if technical is not None:
            payload = {
                "source": technical.source,
                "device_name": technical.device_name,
                "session_id": technical.session_id,
                "entity_id": technical.entity_id,
                "contract_id": technical.contract_id,
                "platform_id": technical.platform_id,
                "event_schema_version": technical.event_schema_version,
                "operation_id": technical.operation_id,
                "before": technical.before,
                "after": technical.after,
                "payload": technical.payload,
                "technical_payload": technical.technical_payload,
            }
            self.technical_text.setPlainText(
                bounded_display(safe_ui_payload(payload), max_chars=8000)
            )
        self.technical_text.setVisible(False)
        self.copy_button.setVisible(False)
