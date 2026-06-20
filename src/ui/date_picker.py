# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from html import escape
from datetime import date, datetime
from typing import Callable, Iterable, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config.app_config import TR_MONTHS


WEEKDAY_LABELS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def parse_iso_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


class DatePickerDay(QLabel):
    clicked = Signal(object)

    def __init__(self, picked_date: date, disabled: bool, events: list[dict], parent: QWidget):
        super().__init__(str(picked_date.day), parent)
        self.picked_date = picked_date
        self.is_disabled = disabled
        self.events = list(events or [])
        self.setObjectName("datePickerDay")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(30, 30)
        self.setAttribute(Qt.WA_Hover, True)
        tooltip = self._build_tooltip()
        if tooltip:
            self.setToolTip(tooltip)
        if not disabled:
            self.setCursor(Qt.PointingHandCursor)

    def apply_visual(self, muted: bool, weekend: bool, today: bool, selected: bool):
        background = "transparent"
        color = "#0f172a"

        if muted:
            color = "#94a3b8"
        if weekend:
            color = "#ef4444"
        if self.is_disabled:
            background = "#eef2f7"
            color = "#94a3b8"
        elif today:
            background = "#1f5be3"
            color = "#ffffff"
        if selected:
            background = "#0b2f6b"
            color = "#ffffff"

        hover_background = background if self.is_disabled or selected or today else "#eff6ff"
        self.setStyleSheet(
            f"""
            QLabel#datePickerDay {{
                background: {background};
                border: 0;
                border-radius: 9px;
                color: {color};
                font-size: 12px;
                font-weight: 800;
            }}
            QLabel#datePickerDay:hover {{
                background: {hover_background};
            }}
            """
        )

    def mousePressEvent(self, event):
        if not self.is_disabled and event.button() == Qt.LeftButton:
            self.clicked.emit(self.picked_date)
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.events:
            return
        colors = [QColor(str(ev.get("color") or "#f97316")) for ev in self.events[:3]]
        if not colors:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        radius = 2
        spacing = 7
        total_width = (len(colors) - 1) * spacing
        start_x = (self.width() - total_width) / 2
        y = self.height() - 5
        for idx, color in enumerate(colors):
            painter.setBrush(color)
            painter.drawEllipse(int(start_x + idx * spacing - radius), int(y - radius), radius * 2, radius * 2)

    def _build_tooltip(self) -> str:
        if not self.events:
            return ""
        blocks = []
        for ev in self.events[:6]:
            title = escape(str(ev.get("title") or "Termin"))
            lines = ev.get("lines") or []
            if isinstance(lines, str):
                lines = [lines]
            body = "<br>".join(escape(str(line)) for line in lines if str(line).strip())
            tag = escape(str(ev.get("tag") or "Termin"))
            block = f"<div><b>{title}</b>"
            if body:
                block += f"<br>{body}"
            block += f"<br><span style='color:#f97316; font-weight:800;'>{tag}</span></div>"
            blocks.append(block)
        if len(self.events) > 6:
            blocks.append(f"<div>+{len(self.events) - 6} kayıt daha</div>")
        return "<div style='white-space:nowrap;'>" + "<br><br>".join(blocks) + "</div>"


class DatePickerPopup(QDialog):
    def __init__(
        self,
        parent: QWidget,
        selected_date: Optional[date] = None,
        max_date: Optional[date] = None,
        events_provider: Optional[Callable[[], Iterable[dict]]] = None,
    ):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("calendarPopupAlt")
        self.max_date = max_date
        self.events_provider = events_provider
        self.events_by_date: dict[date, list[dict]] = {}
        self.today = date.today()
        if selected_date and max_date and selected_date > max_date:
            selected_date = max_date
        self.selected_date = selected_date
        self.selected_text: Optional[str] = None
        seed = selected_date or max_date or self.today
        self.current_year = seed.year
        self.current_month = seed.month
        self.day_buttons: list[DatePickerDay] = []
        self.setStyleSheet(self._style_sheet())
        self._build()
        self._render()

    def _style_sheet(self) -> str:
        return """
        QDialog#calendarPopupAlt {
            background: transparent;
            border: 0;
        }
        QFrame#datePickerShell {
            background: #ffffff;
            border-radius: 16px;
            border: 1px solid #d8e2ed;
        }
        QFrame#datePickerHeader {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0b2f6b, stop:1 #1d4ed8);
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
        }
        QToolTip {
            background: #102033;
            color: #ffffff;
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 10px;
            padding: 8px;
            font-weight: 700;
        }
        QWidget#datePickerHeaderCenter {
            background: transparent;
        }
        QPushButton#datePickerNav {
            background: rgba(255,255,255,.13);
            color: #ffffff;
            border: 0;
            border-radius: 10px;
            font-size: 22px;
            font-weight: 900;
        }
        QPushButton#datePickerNav:hover {
            background: rgba(255,255,255,.23);
        }
        QPushButton#datePickerNav:disabled {
            background: rgba(255,255,255,.07);
            color: rgba(255,255,255,.35);
        }
        QComboBox#datePickerMonth {
            background: rgba(255,255,255,.10);
            color: #ffffff;
            border: 0;
            border-radius: 8px;
            padding: 0px 16px 0px 8px;
            font-size: 14px;
            font-weight: 950;
        }
        QComboBox#datePickerMonth::drop-down {
            border: 0;
            width: 14px;
        }
        QComboBox#datePickerYear {
            background: rgba(255,255,255,.10);
            color: rgba(255,255,255,.78);
            border: 0;
            border-radius: 8px;
            padding: 0px 16px 0px 8px;
            font-size: 14px;
            font-weight: 900;
        }
        QComboBox#datePickerYear::drop-down {
            border: 0;
            width: 14px;
        }
        QComboBox#datePickerMonth QAbstractItemView,
        QComboBox#datePickerYear QAbstractItemView {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            selection-background-color: #eff6ff;
        }
        QFrame#datePickerWeekdays {
            background: #f8fbff;
        }
        QLabel#datePickerWeekday {
            background: transparent;
            color: #475569;
            font-size: 11px;
            font-weight: 850;
        }
        QLabel#datePickerWeekdayWeekend {
            background: transparent;
            color: #ef4444;
            font-size: 11px;
            font-weight: 850;
        }
        QFrame#datePickerDays {
            background: #ffffff;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        }
        QFrame#datePickerFlexible {
            background: #f8fbff;
            border-top: 1px solid #d8e2ed;
            border-bottom-left-radius: 16px;
            border-bottom-right-radius: 16px;
        }
        QPushButton#datePickerFlexibleOption {
            background: #ffffff;
            color: #0b2f6b;
            border: 1px solid #bfdbfe;
            border-radius: 10px;
            padding: 6px 7px;
            text-align: left;
            font-size: 11px;
            font-weight: 850;
            min-height: 48px;
        }
        QPushButton#datePickerFlexibleOption:hover {
            background: #eff6ff;
            border-color: #60a5fa;
        }
        QPushButton#datePickerFlexibleOption:pressed {
            background: #dbeafe;
            border-color: #2563eb;
        }
        QLabel#datePickerDay {
            background: transparent;
            border: 0;
            border-radius: 9px;
            color: #0f172a;
            font-size: 12px;
            font-weight: 800;
        }
        QLabel#datePickerDay:hover {
            background: #eff6ff;
        }
        QLabel#datePickerDay[muted="true"] {
            color: #94a3b8;
        }
        QLabel#datePickerDay[weekend="true"] {
            color: #ef4444;
        }
        QLabel#datePickerDay[today="true"] {
            background: #1f5be3;
            color: #ffffff;
        }
        QLabel#datePickerDay[selected="true"] {
            background: #0b2f6b;
            color: #ffffff;
        }
        QLabel#datePickerDay[disabledDay="true"] {
            background: #eef2f7;
            color: #94a3b8;
        }
        """

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        shell = QFrame(self)
        shell.setObjectName("datePickerShell")
        shell.setFixedWidth(340)
        shell_lay = QVBoxLayout(shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)
        root.addWidget(shell)

        header = QFrame(shell)
        header.setObjectName("datePickerHeader")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(8, 7, 8, 7)
        header_lay.setSpacing(7)

        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("datePickerNav")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.clicked.connect(self._prev_month)

        center = QWidget(header)
        center.setObjectName("datePickerHeaderCenter")
        center_lay = QHBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(6)
        self.month_combo = QComboBox()
        self.month_combo.setObjectName("datePickerMonth")
        self.month_combo.currentIndexChanged.connect(self._on_month_changed)
        self.year_combo = QComboBox()
        self.year_combo.setObjectName("datePickerYear")
        self.year_combo.currentIndexChanged.connect(self._on_year_changed)
        center_lay.addWidget(self.month_combo, 1)
        center_lay.addWidget(self.year_combo, 0)

        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("datePickerNav")
        self.next_btn.setFixedSize(32, 32)
        self.next_btn.clicked.connect(self._next_month)

        header_lay.addWidget(self.prev_btn, 0)
        header_lay.addWidget(center, 1)
        header_lay.addWidget(self.next_btn, 0)
        shell_lay.addWidget(header, 0)

        weekdays = QFrame(shell)
        weekdays.setObjectName("datePickerWeekdays")
        week_lay = QGridLayout(weekdays)
        week_lay.setContentsMargins(10, 6, 10, 6)
        week_lay.setHorizontalSpacing(0)
        week_lay.setVerticalSpacing(0)
        for i, name in enumerate(WEEKDAY_LABELS):
            label = QLabel(name)
            label.setObjectName("datePickerWeekdayWeekend" if i >= 5 else "datePickerWeekday")
            label.setAlignment(Qt.AlignCenter)
            week_lay.addWidget(label, 0, i)
        shell_lay.addWidget(weekdays, 0)

        days = QFrame(shell)
        days.setObjectName("datePickerDays")
        self.days_lay = QGridLayout(days)
        self.days_lay.setContentsMargins(12, 8, 12, 10)
        self.days_lay.setHorizontalSpacing(4)
        self.days_lay.setVerticalSpacing(3)
        shell_lay.addWidget(days, 0)

        flexible = QFrame(shell)
        flexible.setObjectName("datePickerFlexible")
        flexible_lay = QGridLayout(flexible)
        flexible_lay.setContentsMargins(10, 9, 10, 10)
        flexible_lay.setHorizontalSpacing(6)
        flexible_lay.setVerticalSpacing(6)
        for column in range(3):
            flexible_lay.setColumnStretch(column, 1)

        self.day_unknown_btn = QPushButton(flexible)
        self.day_unknown_btn.setObjectName("datePickerFlexibleOption")
        self.day_unknown_btn.clicked.connect(lambda: self._pick_flexible("day_unknown"))
        self.month_day_unknown_btn = QPushButton(flexible)
        self.month_day_unknown_btn.setObjectName("datePickerFlexibleOption")
        self.month_day_unknown_btn.clicked.connect(lambda: self._pick_flexible("month_day_unknown"))
        self.tbd_btn = QPushButton(flexible)
        self.tbd_btn.setObjectName("datePickerFlexibleOption")
        self.tbd_btn.clicked.connect(lambda: self._pick_flexible("unknown"))

        flexible_lay.addWidget(self.day_unknown_btn, 0, 0)
        flexible_lay.addWidget(self.month_day_unknown_btn, 0, 1)
        flexible_lay.addWidget(self.tbd_btn, 0, 2)
        shell_lay.addWidget(flexible, 0)

    def _year_bounds(self) -> tuple[int, int]:
        start = min(1990, self.current_year - 20, self.today.year - 20)
        end = max(2100, self.current_year + 20, self.today.year + 20)
        if self.max_date:
            end = max(start, self.max_date.year)
        return start, end

    def _populate_years(self):
        start, end = self._year_bounds()
        current = self.current_year
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in range(start, end + 1):
            self.year_combo.addItem(str(year), year)
        idx = self.year_combo.findData(current)
        if idx >= 0:
            self.year_combo.setCurrentIndex(idx)
        self.year_combo.blockSignals(False)

    def _populate_months(self):
        max_month = 12
        if self.max_date and self.current_year == self.max_date.year:
            max_month = self.max_date.month
        self.current_month = max(1, min(self.current_month, max_month))
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        for month in range(1, max_month + 1):
            self.month_combo.addItem(TR_MONTHS[month - 1], month)
        idx = self.month_combo.findData(self.current_month)
        if idx >= 0:
            self.month_combo.setCurrentIndex(idx)
        self.month_combo.blockSignals(False)

    def _refresh_events(self):
        self.events_by_date = {}
        if not self.events_provider:
            return
        try:
            raw_events = list(self.events_provider() or [])
        except Exception:
            raw_events = []
        for raw in raw_events:
            ev = dict(raw or {})
            value = ev.get("date") or ev.get("deadline")
            parsed = value if isinstance(value, date) else parse_iso_date(str(value or ""))
            if not parsed:
                continue
            ev["date"] = parsed
            self.events_by_date.setdefault(parsed, []).append(ev)

    def _next_month_value(self) -> tuple[int, int]:
        if self.current_month == 12:
            return self.current_year + 1, 1
        return self.current_year, self.current_month + 1

    def _prev_month_value(self) -> tuple[int, int]:
        if self.current_month == 1:
            return self.current_year - 1, 12
        return self.current_year, self.current_month - 1

    def _next_allowed(self) -> bool:
        if not self.max_date:
            return True
        year, month = self._next_month_value()
        return (year, month) <= (self.max_date.year, self.max_date.month)

    def _render(self):
        self._refresh_events()
        self._populate_years()
        self._populate_months()
        self.next_btn.setEnabled(self._next_allowed())

        while self.days_lay.count():
            item = self.days_lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.day_buttons.clear()

        first_weekday, days_in_month = calendar.monthrange(self.current_year, self.current_month)
        prev_year, prev_month = self._prev_month_value()
        prev_days = calendar.monthrange(prev_year, prev_month)[1]

        cells: list[tuple[date, bool]] = []
        for i in range(first_weekday):
            day_num = prev_days - first_weekday + i + 1
            cells.append((date(prev_year, prev_month, day_num), True))
        for day_num in range(1, days_in_month + 1):
            cells.append((date(self.current_year, self.current_month, day_num), False))
        next_year, next_month = self._next_month_value()
        next_day = 1
        while len(cells) < 42:
            cells.append((date(next_year, next_month, next_day), True))
            next_day += 1

        for idx, (cell_date, muted) in enumerate(cells):
            disabled = bool(self.max_date and cell_date > self.max_date)
            weekend = cell_date.weekday() >= 5
            is_today = cell_date == self.today
            selected = bool(self.selected_date and cell_date == self.selected_date)
            events = self.events_by_date.get(cell_date, [])
            btn = DatePickerDay(cell_date, disabled, events, self)
            btn.setProperty("muted", muted)
            btn.setProperty("weekend", weekend)
            btn.setProperty("today", is_today)
            btn.setProperty("selected", selected)
            btn.setProperty("disabledDay", disabled)
            btn.apply_visual(muted, weekend, is_today, selected)
            if not disabled:
                btn.clicked.connect(self._pick)
            self.days_lay.addWidget(btn, idx // 7, idx % 7, Qt.AlignCenter)
            self.day_buttons.append(btn)

        self._refresh_flexible_options()
        self.adjustSize()

    def _refresh_flexible_options(self):
        if not hasattr(self, "day_unknown_btn"):
            return
        day_unknown = f"{self.current_year:04d}-{self.current_month:02d}-TBD"
        month_day_unknown = f"{self.current_year:04d}-TBD-TBD"
        self.day_unknown_btn.setText(f"Gün bilinmiyor\n{day_unknown}")
        self.month_day_unknown_btn.setText(f"Ay/Gün bilinmiyor\n{month_day_unknown}")
        self.tbd_btn.setText("Belirsiz\nTBD")

    def _pick(self, picked: date):
        self.selected_date = picked
        self.selected_text = picked.isoformat()
        self.accept()

    def _pick_flexible(self, mode: str):
        if mode == "day_unknown":
            self.selected_text = f"{self.current_year:04d}-{self.current_month:02d}-TBD"
        elif mode == "month_day_unknown":
            self.selected_text = f"{self.current_year:04d}-TBD-TBD"
        elif mode == "unknown":
            self.selected_text = "TBD"
        else:
            return
        self.selected_date = None
        self.accept()

    def _prev_month(self):
        self.current_year, self.current_month = self._prev_month_value()
        self._render()

    def _next_month(self):
        if not self._next_allowed():
            return
        self.current_year, self.current_month = self._next_month_value()
        self._render()

    def _on_year_changed(self, *_args):
        year = int(self.year_combo.currentData() or self.current_year)
        self.current_year = year
        if self.max_date and self.current_year == self.max_date.year and self.current_month > self.max_date.month:
            self.current_month = self.max_date.month
        self._render()

    def _on_month_changed(self, *_args):
        month = int(self.month_combo.currentData() or self.current_month)
        self.current_month = month
        self._render()


def build_date_input(
    parent: QWidget,
    placeholder: str = "yyyy-aa-gg",
    max_date: Optional[date] = None,
    events_provider: Optional[Callable[[], Iterable[dict]]] = None,
) -> Tuple[QLineEdit, QWidget]:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)

    btn = QPushButton("\U0001f4c5")
    btn.setObjectName("dateBtn")
    btn.setFixedSize(34, 34)
    btn.setToolTip("Takvimden tarih seç")

    wrap = QWidget(parent)
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(edit, 1)
    lay.addWidget(btn, 0)

    def choose_date():
        current = parse_iso_date(edit.text()) or date.today()
        if max_date and current > max_date:
            current = max_date
        popup = DatePickerPopup(parent, current, max_date=max_date, events_provider=events_provider)
        popup.move(btn.mapToGlobal(btn.rect().bottomLeft()))
        if popup.exec():
            selected_text = str(getattr(popup, "selected_text", "") or "").strip()
            if selected_text:
                edit.setText(selected_text)
            elif popup.selected_date:
                edit.setText(popup.selected_date.isoformat())

    btn.clicked.connect(choose_date)
    return edit, wrap
