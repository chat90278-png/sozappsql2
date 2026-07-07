"""
calendar_widget.py
Ana sayfa alertStrip'inin sağ tarafında yer alan mini takvim önizleme widget'ı.

Tıklanınca open_fn() çağrılır (MainWindow.open_calendar_tracking).
Veriler MainWindow.update_alert_strip() tarafından refresh() ile güncellenir.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date
from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)


class CalendarWidget(QFrame):
    """
    Mini takvim önizleme widget'ı.

    Layout (yatay):
      [mini grid 7x5] | [ayırıcı] | [4 sayaç] | [ok butonu]

    Renk sabitleri theme.py ile uyumludur.
    """

    _C: Dict[str, tuple] = {
        "geciken":    ("#fef2f2", "#b91c1c", "#e1473f"),
        "kritik":     ("#fffbeb", "#92400e", "#e8b53f"),
        "tamamlandi": ("#ecfdf5", "#047857", "#39a96b"),
        "belirsiz":   ("#f1edfb", "#6d28d9", "#8b7cd8"),
        "normal":     ("#e8f0fe", "#1f5be3", "#397bd8"),
    }

    _TR_SHORT = [
        "Oca", "Sub", "Mar", "Nis", "May", "Haz",
        "Tem", "Agu", "Eyl", "Eki", "Kas", "Ara",
    ]

    def __init__(self, open_fn: Callable, parent=None):
        super().__init__(parent)
        self._open_fn = open_fn
        self._counts: Dict[str, int] = {
            "geciken": 0, "kritik": 0, "tamamlandi": 0, "belirsiz": 0,
        }
        self._events_by_day: Dict[int, str] = {}
        self._today = date.today()
        self._year  = self._today.year
        self._month = self._today.month

        self.setObjectName("calWidget")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#calWidget{"
            "background:#ffffff;"
            "border:1.5px solid #d8e2ed;"
            "border-radius:12px;"
            "}"
            "QFrame#calWidget:hover{"
            "border-color:#397bd8;"
            "background:#fafcff;"
            "}"
        )
        self._build()

    # ── Yapı ──────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 10, 8)
        root.setSpacing(10)

        # ── Mini takvim grid ─────────────────────────────────────────────
        cal_w = QWidget()
        cal_w.setStyleSheet("background:transparent;")
        cal_lay = QVBoxLayout(cal_w)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(2)

        # Üst: etiket + ay rozeti
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("TAKVIM")
        lbl.setStyleSheet(
            "font-size:9px; font-weight:900; color:#94a3b8;"
            "letter-spacing:.1em; background:transparent;"
        )
        top_row.addWidget(lbl)
        self._month_badge = QLabel()
        self._month_badge.setStyleSheet(
            "font-size:9px; font-weight:900; color:#1f5be3;"
            "background:#e8f0fe; border-radius:6px; padding:1px 6px;"
        )
        top_row.addWidget(self._month_badge)
        top_row.addStretch()
        cal_lay.addLayout(top_row)

        # Gün harfleri
        days_row = QHBoxLayout()
        days_row.setSpacing(2)
        days_row.setContentsMargins(0, 0, 0, 0)
        for d in ["P", "S", "C", "P", "C", "C", "P"]:
            dl = QLabel(d)
            dl.setFixedWidth(15)
            dl.setAlignment(Qt.AlignCenter)
            dl.setStyleSheet(
                "font-size:7px; font-weight:800; color:#cbd5e1; background:transparent;"
            )
            days_row.addWidget(dl)
        cal_lay.addLayout(days_row)

        # 5 satir x 7 sutun gün hücreleri
        self._grid_rows = []
        for _ in range(5):
            row_lay = QHBoxLayout()
            row_lay.setSpacing(2)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_cells = []
            for _ in range(7):
                cell = QLabel()
                cell.setFixedSize(15, 15)
                cell.setAlignment(Qt.AlignCenter)
                cell.setStyleSheet(
                    "font-size:7px; font-weight:700; color:#94a3b8;"
                    "background:transparent; border-radius:3px;"
                )
                row_lay.addWidget(cell)
                row_cells.append(cell)
            self._grid_rows.append(row_cells)
            cal_lay.addLayout(row_lay)

        root.addWidget(cal_w)

        # ── Dikey ayirici ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#e2e8f0; max-width:1px;")
        root.addWidget(sep)

        # ── Sayaçlar ──────────────────────────────────────────────────────
        stats_w = QWidget()
        stats_w.setStyleSheet("background:transparent;")
        stats_lay = QVBoxLayout(stats_w)
        stats_lay.setContentsMargins(0, 0, 0, 0)
        stats_lay.setSpacing(3)

        self._stat_labels: Dict[str, QLabel] = {}
        for key, txt in [
            ("geciken",    "Geciken"),
            ("kritik",     "60 gun"),
            ("tamamlandi", "Teslim"),
            ("belirsiz",   "Belirsiz"),
        ]:
            _, fg, dot_color = self._C[key]
            row = QHBoxLayout()
            row.setSpacing(5)
            row.setContentsMargins(0, 0, 0, 0)
            dot_l = QLabel("*")
            dot_l.setStyleSheet(
                f"font-size:8px; color:{dot_color}; background:transparent;"
            )
            num_l = QLabel("0")
            num_l.setFixedWidth(18)
            num_l.setStyleSheet(
                f"font-size:13px; font-weight:900; color:{fg}; background:transparent;"
            )
            lbl_l = QLabel(txt)
            lbl_l.setStyleSheet(
                "font-size:8.5px; font-weight:700; color:#94a3b8; background:transparent;"
            )
            row.addWidget(dot_l)
            row.addWidget(num_l)
            row.addWidget(lbl_l)
            row.addStretch()
            stats_lay.addLayout(row)
            self._stat_labels[key] = num_l

        root.addWidget(stats_w)

        # ── Ok butonu ─────────────────────────────────────────────────────
        arrow = QLabel(">")
        arrow.setFixedSize(30, 30)
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setStyleSheet(
            "font-size:16px; font-weight:900; color:#1f5be3;"
            "background:#e8f0fe; border-radius:8px; border:1px solid rgba(57,123,216,.3);"
        )
        root.addWidget(arrow)

        self._refresh_grid()

    # ── Dis API ───────────────────────────────────────────────────────────
    def refresh(
        self,
        counts: Dict[str, int],
        events_by_day: Dict[int, str],
        year: int,
        month: int,
    ) -> None:
        """
        MainWindow.update_alert_strip() tarafindan cagirilir.

        counts:
            {"geciken": int, "kritik": int, "tamamlandi": int, "belirsiz": int}
        events_by_day:
            {day: cls_str}  cls: "geciken" | "kritik" | "tamamlandi" | "normal"
        """
        self._counts        = counts
        self._events_by_day = events_by_day
        self._year  = year
        self._month = month
        for key, lbl in self._stat_labels.items():
            lbl.setText(str(counts.get(key, 0)))
        self._refresh_grid()

    # ── ic ───────────────────────────────────────────────────────────────
    def _refresh_grid(self) -> None:
        self._month_badge.setText(
            f"{self._TR_SHORT[self._month - 1]} {self._year}"
        )
        first_wd = _cal.monthrange(self._year, self._month)[0]  # 0=Pzt
        days_in  = _cal.monthrange(self._year, self._month)[1]

        for row in self._grid_rows:
            for cell in row:
                cell.setText("")
                cell.setStyleSheet(
                    "font-size:7px; font-weight:700; color:#94a3b8;"
                    "background:transparent; border-radius:3px;"
                )

        today = date.today()
        idx = first_wd
        for day in range(1, days_in + 1):
            r, c = idx // 7, idx % 7
            if r >= 5:
                break
            cell = self._grid_rows[r][c]
            cell.setText(str(day))
            is_today = (
                day         == today.day   and
                self._month == today.month and
                self._year  == today.year
            )
            cls = self._events_by_day.get(day)
            if is_today:
                cell.setStyleSheet(
                    "font-size:7px; font-weight:900; color:#ffffff;"
                    "background:#397bd8; border-radius:3px;"
                )
            elif cls and cls in self._C:
                bg, fg, _ = self._C[cls]
                cell.setStyleSheet(
                    f"font-size:7px; font-weight:800; color:{fg};"
                    f"background:{bg}; border-radius:3px;"
                )
            else:
                cell.setStyleSheet(
                    "font-size:7px; font-weight:700; color:#94a3b8;"
                    "background:transparent; border-radius:3px;"
                )
            idx += 1

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._open_fn()
        super().mousePressEvent(event)
