# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import re
import ctypes
import getpass
import os
import base64
import copy
import time
import traceback
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple
from auto_accept import open_auto_accept_dialog

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.domain.constants import (
    CORE_SHEETS,
    HEADER_ROW,
    SUBHEADER_ROW,
    DATA_START_ROW,
    STATUS_VALUES,
)
from src.config.app_config import (
    APP_TITLE,
    APP_ICON_PATH,
    APP_ICON_ICO_PATH,
    APP_ID,
    DEFAULT_FILE,
    COMP_SHEET,
    USERS_SHEET,
    PLATFORM_LOGO_SHEET,
    TAG_SHEET,
    TAG_KIND_DEF,
    TAG_KIND_ASSIGN,
    LOG_FOLDER_NAME,
    NAVY,
    LIGHT,
    CARD,
    HEAD,
    BLUE,
    GREEN,
    GRID,
    TEXT_MUTED,
    BASE_HEADERS,
    MAIN_TOTAL_LABEL,
    SYSTEM_TOTAL_SUFFIX,
    TR_MONTHS,
    TR_WEEKDAYS,
    LOG_HEADERS,
    TAG_HEADERS,
    EXTRA_SYSTEM_SHEET_NAMES,
)
from src.models.app_models import ComponentDef, ContractInfo, SystemInfo, DeliveryInfo, TagDef
from src.domain.contract_timing import contract_timing, is_completed_status
from src.domain.delivery_coverage import acceptance_coverage_issues
from src.ui.widgets import stat_card, set_card_value
from src.ui.theme import STYLE
from src.ui.tarih import ContractCalendarWindow
from src.ui.ozet import ContractSummaryDialog
from src.ui.date_picker import build_date_input as _build_date_input
from src.ui.kullanim_kilavuzu import UsageGuideDialog

from PySide6.QtCore import Qt, QDate, QObject, QThread, Signal, QTimer, QPoint, QSize, QEvent, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QFont, QColor, QPixmap, QIcon, QPainter, QAction, QCursor, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QDialog, QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
    QMessageBox, QFileDialog, QFrame, QScrollArea, QCheckBox, QHeaderView,
    QSizePolicy, QProgressBar, QProgressDialog, QStyledItemDelegate, QTextEdit,
    QToolButton, QMenu, QInputDialog, QWidgetAction, QStackedWidget, QAbstractItemView, QStyle
)



class ContractFileDropButton(QPushButton):
    """Clickable upload target that also accepts local file drops."""

    filesDropped = Signal(list)
    invalidDrop = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._default_text = text
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
            self.setText("  ↓    Dosyaları buraya bırakın")
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setText(self._default_text)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setText(self._default_text)
        mime = event.mimeData()
        if not mime.hasUrls():
            self.invalidDrop.emit("Yalnızca yerel dosyalar yüklenebilir.")
            event.ignore()
            return
        file_paths = []
        folder_dropped = False
        unsupported_url = False
        for url in mime.urls():
            if not url.isLocalFile():
                unsupported_url = True
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                folder_dropped = True
                continue
            file_paths.append(str(path))
        if folder_dropped:
            self.invalidDrop.emit("Klasör yüklenemez, lütfen dosya seçin.")
        if unsupported_url:
            self.invalidDrop.emit("Web bağlantısı yüklenemez, lütfen yerel dosya seçin.")
        if file_paths:
            self.filesDropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()

def app_icon_path() -> Path:
    """Return the native Windows icon when available, otherwise the SVG logo."""
    if APP_ICON_ICO_PATH.exists():
        return APP_ICON_ICO_PATH
    return APP_ICON_PATH


def configure_windows_app_identity() -> None:
    """Set a stable Windows AppUserModelID so taskbar icons use the STS icon."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

def normalize_sheet_name(name: str) -> str:
    txt = str(name or "").strip().lower()
    repl = {
        "\u0131": "i",
        "\u0130": "i",
        "\u015f": "s",
        "\u011f": "g",
        "\u00fc": "u",
        "\u00f6": "o",
        "\u00e7": "c",
    }
    for a, b in repl.items():
        txt = txt.replace(a, b)
    return txt


def is_system_sheet_name(name: str) -> bool:
    if not name:
        return True
    n = normalize_sheet_name(name)
    core_norm = {normalize_sheet_name(x) for x in CORE_SHEETS}
    if n in core_norm or n in EXTRA_SYSTEM_SHEET_NAMES:
        return True
    if str(name).startswith("_") or n.startswith("_"):
        return True
    return False


def safe_sheet_name(name: str) -> str:
    n = re.sub(r"[\\/*?:\[\]]", "_", name.strip().upper())
    return n[:31] or "PLATFORM"


def to_iso(qdate: QDate) -> str:
    return f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"


def parse_iso_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + int(months or 0)
    year = d.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(d.day, days[month - 1])
    return date(year, month, day)


def iso_or_blank(text: str) -> str:
    d = parse_iso_date(text)
    return d.isoformat() if d else ""


def contract_date_picker_events(ci: Optional[ContractInfo], systems: Optional[List[SystemInfo]] = None) -> List[dict]:
    events: List[dict] = []
    if ci:
        contract_deadline = parse_iso_date(str(getattr(ci, "completion_date", "") or ""))
        if contract_deadline:
            no = str(getattr(ci, "no", "") or "").strip() or "Sözleşme"
            ctype = str(getattr(ci, "contract_type", "") or "").strip()
            title = f"{no} {ctype}".strip()
            events.append({
                "date": contract_deadline,
                "title": title,
                "lines": [
                    f"Termin tarihi: {contract_deadline.isoformat()}",
                    f"Durum: {str(getattr(ci, 'status', '') or '-')}",
                ],
                "tag": "Sözleşme termini",
                "color": "#f97316",
            })
    for sys_info in list(systems or []):
        system_deadline = parse_iso_date(str(getattr(sys_info, "completion_date", "") or ""))
        if not system_deadline:
            continue
        no = str(getattr(ci, "no", "") or "").strip() if ci else ""
        name = str(getattr(sys_info, "name", "") or "").strip() or "Sistem"
        events.append({
            "date": system_deadline,
            "title": f"{no} {name}".strip(),
            "lines": [
                f"Termin tarihi: {system_deadline.isoformat()}",
                f"Durum: {str(getattr(sys_info, 'status', '') or '-')}",
            ],
            "tag": "Sistem termini",
            "color": "#2563eb",
        })
    return events


def as_number(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def fmt_num(v) -> str:
    try:
        f = float(v or 0)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except Exception:
        return str(v or "")


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    txt = str(color or "").strip().lstrip("#")
    if len(txt) == 3:
        txt = "".join(ch * 2 for ch in txt)
    if len(txt) != 6:
        return (59, 130, 246)
    try:
        return (int(txt[0:2], 16), int(txt[2:4], 16), int(txt[4:6], 16))
    except Exception:
        return (59, 130, 246)


def _mix_rgb(a: Tuple[int, int, int], b: Tuple[int, int, int], ratio: float) -> Tuple[int, int, int]:
    r = max(0.0, min(1.0, float(ratio)))
    return (
        int(a[0] * (1 - r) + b[0] * r),
        int(a[1] * (1 - r) + b[1] * r),
        int(a[2] * (1 - r) + b[2] * r),
    )


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2]))),
    )


def tag_chip_style(color: str, selected: bool = False) -> str:
    base = _hex_to_rgb(color)
    bg = _mix_rgb(base, (255, 255, 255), 0.78 if not selected else 0.68)
    border = _mix_rgb(base, (255, 255, 255), 0.28 if not selected else 0.12)
    lum = (0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2]) / 255.0
    txt = "#0F172A" if lum > 0.58 else "#FFFFFF"
    if not selected:
        txt = _rgb_to_hex(_mix_rgb(base, (15, 23, 42), 0.22))
    return (
        f"QPushButton {{ background:{_rgb_to_hex(bg)}; color:{txt}; border:1px solid {_rgb_to_hex(border)}; "
        "border-radius:13px; padding:4px 10px; font-weight:800; } "
        f"QPushButton:hover {{ border-color:{_rgb_to_hex(_mix_rgb(base, (15, 23, 42), 0.18))}; }}"
    )


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self._full_text = ""
        self.setText(text)

    def setText(self, text: str):  # type: ignore[override]
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elide()

    def _refresh_elide(self):
        width = max(12, self.width())
        super().setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width))



from src.services.excel_store import ExcelStore
from src.services.sts_store import STSStore
from src.workers import ExcelLoadWorker, ComponentSaveWorker, UserSaveWorker, ContractSaveWorker, AnalyzeDialog


COL_PLATFORM = 0
COL_TYPE = 1
COL_CONTRACT_NO = 2
COL_USER = 3
COL_STATUS = 4
COL_T_DATE = 5
COL_REMAINING = 6
COL_TAGS = 7
COL_SUMMARY = 8


class FilterableHeaderView(QHeaderView):
    """Excel gibi sutun filtresi destekleyen header.
    Her sutun basliginda kucuk bir filtre ikonu gosterir.
    Tiklayinca o sutunun benzersiz degerlerini checkbox listesi olarak acar.
    """
    filterChanged = Signal()

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        # col_index -> set of selected values (None = tumu secili)
        self._col_filters: Dict[int, Optional[set]] = {}
        self._date_ranges: Dict[int, Tuple[Optional[date], Optional[date]]] = {}
        self._day_ranges: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
        self.sectionClicked.connect(self._on_section_clicked)

    def has_active_filter(self, col: int) -> bool:
        return (
            (col in self._col_filters and self._col_filters[col] is not None)
            or col in self._date_ranges
            or col in self._day_ranges
        )

    def get_filter(self, col: int) -> Optional[set]:
        return self._col_filters.get(col)

    def clear_filter(self, col: int):
        self._col_filters.pop(col, None)
        self._date_ranges.pop(col, None)
        self._day_ranges.pop(col, None)
        self.filterChanged.emit()
        self.viewport().update()

    def clear_all_filters(self):
        self._col_filters.clear()
        self._date_ranges.clear()
        self._day_ranges.clear()
        self.filterChanged.emit()
        self.viewport().update()

    def _get_column_values(self, col: int) -> List[str]:
        table = self.parent()
        if not isinstance(table, QTableWidget):
            return []
        vals = set()
        # Tum satirlari tara (visible_rows varsa onu kullan)
        source = getattr(table, '_all_rows_for_filter', None)
        if source is not None:
            col_keys = getattr(table, "_filter_col_keys", ["platform", "type", "no", "user", "status", "date", "days", "tags", "summary"])
            if col < len(col_keys):
                window = table.window()
                for row_index, it in enumerate(source, start=1):
                    key = col_keys[col]
                    if key == "type":
                        v = str(it.get("type_display", it.get("type", "")) or "").strip()
                    elif key in {"status", "date", "days"} and hasattr(window, "_contract_health"):
                        _cls, st, days, dt = window._contract_health(it)
                        v = {"status": st, "date": dt, "days": days}.get(key, "")
                    elif key == "tags":
                        for tg in list(it.get("tags", []) or []):
                            tg = str(tg or "").strip()
                            if tg:
                                vals.add(tg)
                        continue
                    elif key == "summary":
                        v = "Özet"
                    else:
                        v = str(it.get(key, "") or "").strip()
                    if v:
                        vals.add(v)
        else:
            for r in range(table.rowCount()):
                item = table.item(r, col)
                v = str(item.text() if item else "").strip()
                if v:
                    vals.add(v)
        return sorted(vals, key=lambda x: x.lower())

    def _on_section_clicked(self, col: int):
        values = self._get_column_values(col)
        if not values and col not in (COL_T_DATE, COL_REMAINING):
            return
        current_filter = self._col_filters.get(col)  # None = tumu

        popup = QMenu(self.viewport())
        popup.setObjectName("filterPopup")
        popup.setStyleSheet(
            "QMenu { background:#fff; border:1px solid #d8e2ed; border-radius:6px; padding:4px; }"
            "QMenu::item { padding:4px 14px; border-radius:4px; }"
            "QMenu::item:selected { background:#EEF2F6; }"
        )

        # Tumunu sec / temizle
        select_all_action = popup.addAction("✔ Tümünü Seç")
        clear_action = popup.addAction("✕ Filtreyi Temizle")
        clear_action.setEnabled(current_filter is not None or col in self._date_ranges or col in self._day_ranges)
        popup.addSeparator()
        # Kalan Gun sutunu - siralama secenekleri ekle
        sort_asc_action = None
        sort_desc_action = None
        if col == COL_REMAINING:  # Kalan Gun sutunu
            sort_asc_action = popup.addAction("↑ Artan Sırala (Az → Çok)")
            sort_desc_action = popup.addAction("↓ Azalan Sırala (Çok → Az)")
            popup.addSeparator()


        if col == COL_T_DATE:
            self._add_date_range_controls(popup, col)
            popup.addSeparator()
        elif col == COL_REMAINING:
            self._add_day_range_controls(popup, col)
            popup.addSeparator()
        # Her deger icin checkbox action
        check_actions: List[Tuple[QAction, str]] = []
        if col not in (COL_T_DATE, COL_REMAINING):
            for val in values:
                icon_txt = "✔" if (current_filter is None or val in current_filter) else "□"
                a = popup.addAction(f"{icon_txt}  {val}")
                a.setCheckable(False)
                check_actions.append((a, val))

        # Sutun basliginin ekran koordinati
        x = self.sectionViewportPosition(col)
        y = self.height()
        global_pos = self.viewport().mapToGlobal(QPoint(x, y))

        chosen = popup.exec(global_pos)
        if not chosen:
            return
        if chosen is select_all_action:
            self._col_filters.pop(col, None)
            self._date_ranges.pop(col, None)
            self._day_ranges.pop(col, None)
        elif chosen is clear_action:
            self._col_filters.pop(col, None)
            self._date_ranges.pop(col, None)
            self._day_ranges.pop(col, None)
        elif sort_asc_action is not None and chosen is sort_asc_action:
            # Kalan gun artan siralama - table parent'ina sort_mode set et
            table = self.parent()
            if hasattr(table, '_sort_mode'):
                table._sort_mode = 'days_asc'
            self.filterChanged.emit()
            return
        elif sort_desc_action is not None and chosen is sort_desc_action:
            table = self.parent()
            if hasattr(table, '_sort_mode'):
                table._sort_mode = 'days_desc'
            self.filterChanged.emit()
            return
        else:
            # Tiklanana gore toggle
            clicked_val = next((v for a, v in check_actions if a is chosen), None)
            if clicked_val is not None:
                if current_filter is None:
                    # Ilk tiklamada sadece o degeri sec
                    self._col_filters[col] = {clicked_val}
                elif clicked_val in current_filter:
                    current_filter.discard(clicked_val)
                    if not current_filter:
                        self._col_filters.pop(col, None)
                    else:
                        self._col_filters[col] = current_filter
                else:
                    current_filter.add(clicked_val)
                    self._col_filters[col] = current_filter
        self.filterChanged.emit()
        self.viewport().update()

    def _add_date_range_controls(self, popup: QMenu, col: int):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(5)
        title = QLabel("Tarih aralığı")
        title.setStyleSheet("font-weight:800;color:#1b3150;")
        lay.addWidget(title)
        current_from, current_to = self._date_ranges.get(col, (None, None))
        start = QDateEdit()
        start.setCalendarPopup(True)
        start.setDisplayFormat("dd.MM.yyyy")
        start.setSpecialValueText("Başlangıç")
        start.setMinimumDate(QDate(2000, 1, 1))
        start.setMaximumDate(QDate(2100, 12, 31))
        start.setDate(QDate(current_from.year, current_from.month, current_from.day) if current_from else QDate.currentDate())
        if not current_from:
            start.lineEdit().clear()
        end = QDateEdit()
        end.setCalendarPopup(True)
        end.setDisplayFormat("dd.MM.yyyy")
        end.setSpecialValueText("Bitiş")
        end.setMinimumDate(QDate(2000, 1, 1))
        end.setMaximumDate(QDate(2100, 12, 31))
        end.setDate(QDate(current_to.year, current_to.month, current_to.day) if current_to else QDate.currentDate())
        if not current_to:
            end.lineEdit().clear()
        lay.addWidget(start)
        lay.addWidget(end)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Uygula")
        clear_btn = QPushButton("Aralığı Temizle")
        buttons.addWidget(apply_btn)
        buttons.addWidget(clear_btn)
        lay.addLayout(buttons)

        def apply_range():
            start_date = start.date().toPython() if start.lineEdit().text().strip() else None
            end_date = end.date().toPython() if end.lineEdit().text().strip() else None
            if start_date or end_date:
                self._date_ranges[col] = (start_date, end_date)
            else:
                self._date_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        def clear_range():
            self._date_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        apply_btn.clicked.connect(apply_range)
        clear_btn.clicked.connect(clear_range)
        action = QWidgetAction(popup)
        action.setDefaultWidget(box)
        popup.addAction(action)

    def _add_day_range_controls(self, popup: QMenu, col: int):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(5)
        title = QLabel("Kalan gün aralığı")
        title.setStyleSheet("font-weight:800;color:#1b3150;")
        lay.addWidget(title)
        current_min, current_max = self._day_ranges.get(col, (None, None))
        min_edit = QLineEdit()
        min_edit.setPlaceholderText("Min / tek gün")
        min_edit.setText("" if current_min is None else str(current_min))
        max_edit = QLineEdit()
        max_edit.setPlaceholderText("Maks")
        max_edit.setText("" if current_max is None else str(current_max))
        lay.addWidget(min_edit)
        lay.addWidget(max_edit)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Uygula")
        clear_btn = QPushButton("Aralığı Temizle")
        buttons.addWidget(apply_btn)
        buttons.addWidget(clear_btn)
        lay.addLayout(buttons)

        def parse_int(widget: QLineEdit):
            txt = widget.text().strip()
            if not txt:
                return None
            try:
                return int(txt)
            except ValueError:
                return None

        def apply_range():
            min_val = parse_int(min_edit)
            max_val = parse_int(max_edit)
            if min_val is not None or max_val is not None:
                if min_val is not None and max_val is None:
                    max_val = min_val
                self._day_ranges[col] = (min_val, max_val)
            else:
                self._day_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        def clear_range():
            self._day_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        apply_btn.clicked.connect(apply_range)
        clear_btn.clicked.connect(clear_range)
        action = QWidgetAction(popup)
        action.setDefaultWidget(box)
        popup.addAction(action)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        # Filtre aktifse ikonu farkli goster
        active = self.has_active_filter(logical_index)
        icon = "▼" if active else "▾"  # solid down vs outline down
        painter.save()
        painter.setPen(QColor("#1F5BE3" if active else "#94A3B8"))
        f = painter.font()
        f.setPointSize(9)  # daha buyuk
        f.setBold(active)
        painter.setFont(f)
        painter.drawText(rect.adjusted(0, 0, -6, 0), Qt.AlignRight | Qt.AlignVCenter, icon)
        painter.restore()


class StyledDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(STYLE)

    def make_footer_status_label(self) -> QLabel:
        label = QLabel("")
        label.setObjectName("footerStatus")
        label.setMinimumWidth(0)
        label.setMinimumHeight(34)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.hide()
        return label

    def show_footer_status(self, message: str, kind: str = "success", duration: int = 2600):
        label = getattr(self, "footer_status", None)
        if label is None:
            ToastNotification.show_in(self, message, kind=kind, duration=duration)
            return

        colors = {
            "success": ("#166534", "#dcfce7", "#16a34a"),
            "error": ("#991b1b", "#fee2e2", "#dc2626"),
            "info": ("#1e3a8a", "#dbeafe", "#2563eb"),
        }
        icons = {"success": "\u2713", "error": "\u2715", "info": "i"}
        fg, bg, border = colors.get(kind, colors["success"])
        text = str(message or "")
        visible_text = text if len(text) <= 96 else f"{text[:93]}..."
        label.setText(f"{icons.get(kind, 'i')}  {visible_text}")
        label.setToolTip(text)
        label.setStyleSheet(
            f"QLabel#footerStatus{{color:{fg};background:{bg};border:1px solid {border};"
            "border-radius:7px;padding:6px 10px;font-size:12px;font-weight:700;}}"
        )
        label.show()

        token = getattr(self, "_footer_status_token", 0) + 1
        self._footer_status_token = token
        QTimer.singleShot(duration, lambda: self.clear_footer_status(token))

    def clear_footer_status(self, token: Optional[int] = None):
        if token is not None and token != getattr(self, "_footer_status_token", None):
            return
        label = getattr(self, "footer_status", None)
        if label is not None:
            label.hide()


def form_label(txt):
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l


def _legacy_build_date_input_unused(
    parent: QWidget,
    placeholder: str = "yyyy-aa-gg",
    max_date: Optional[date] = None,
) -> Tuple[QLineEdit, QWidget]:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)

    btn = QPushButton("📅")
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
        popup = QDialog(parent, Qt.Popup | Qt.FramelessWindowHint)
        popup.setObjectName("calendarPopup")
        pop_lay = QVBoxLayout(popup)
        pop_lay.setContentsMargins(6, 6, 6, 6)
        pop_lay.setSpacing(0)
        cal = QCalendarWidget(popup)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setGridVisible(True)
        if max_date:
            cal.setMaximumDate(QDate(max_date.year, max_date.month, max_date.day))
            disabled_fmt = QTextCharFormat()
            disabled_fmt.setBackground(QColor("#EEF2F7"))
            disabled_fmt.setForeground(QColor("#94A3B8"))
            month_days = calendar.monthrange(max_date.year, max_date.month)[1]
            for day_num in range(max_date.day + 1, month_days + 1):
                cal.setDateTextFormat(QDate(max_date.year, max_date.month, day_num), disabled_fmt)
        current = parse_iso_date(edit.text())
        if current:
            if max_date and current > max_date:
                current = max_date
            cal.setSelectedDate(QDate(current.year, current.month, current.day))

        def on_pick(qd: QDate):
            edit.setText(to_iso(qd))
            popup.accept()

        cal.clicked.connect(on_pick)
        pop_lay.addWidget(cal)
        popup.adjustSize()
        popup.move(btn.mapToGlobal(QPoint(0, btn.height() + 2)))
        popup.exec()

    btn.clicked.connect(choose_date)
    return edit, wrap


def build_date_input(
    parent: QWidget,
    placeholder: str = "yyyy-aa-gg",
    max_date: Optional[date] = None,
    events_provider: Optional[Callable[[], List[dict]]] = None,
) -> Tuple[QLineEdit, QWidget]:
    return _build_date_input(parent, placeholder=placeholder, max_date=max_date, events_provider=events_provider)


from src.ui.delegates import CompactNumberDelegate, CenterTableDelegate, DropdownDelegate

from src.ui.toast import ToastNotification

class UserManagerDialog(StyledDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__("Kullanıcı Yönetimi", parent)
        self.store = store
        self.users = store.load_users(active_only=False)
        self.changed = False
        self._save_thread: Optional[QThread] = None
        self._save_worker: Optional[UserSaveWorker] = None
        self._save_payload: List[dict] = []
        self._saving = False
        self._busy_cursor_on = False
        self.resize(760, 500)
        self.build()
        self.load_table()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Kullanıcı Yönetimi")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        desc = QLabel("Sözleşme girişinde seçilecek kullanıcıları burada tanımlayın. Aktif olmayanlar yeni sözleşme ekranında görünmez.")
        desc.setObjectName("muted")
        root.addWidget(desc)

        btns = QHBoxLayout()
        add = QPushButton("+ Kullanıcı Ekle")
        add.clicked.connect(self.add_user)
        delete = QPushButton("Seçili Kullanıcıyı Sil")
        delete.setObjectName("danger")
        delete.clicked.connect(self.delete_selected)
        btns.addWidget(add)
        btns.addWidget(delete)
        btns.addStretch()
        root.addLayout(btns)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Kullanıcı Adı", "Yİ/YD", "Aktif", "Not"])
        root.addWidget(self.table, 1)

        foot = QHBoxLayout()
        self.footer_status = self.make_footer_status_label()
        foot.addWidget(self.footer_status, 1, Qt.AlignVCenter)
        foot.addStretch()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self.save)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.setObjectName("secondary")
        self.close_btn.clicked.connect(self.reject)
        foot.addWidget(self.save_btn)
        foot.addWidget(self.close_btn)
        root.addLayout(foot)

        self.busy_overlay = QFrame(self)
        self.busy_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.86); }")
        self.busy_overlay.hide()
        self.busy_card = QFrame(self.busy_overlay)
        self.busy_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.97); border: 1px solid #d8e2ed; border-radius: 10px; }"
        )
        bl = QVBoxLayout(self.busy_card)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(8)
        self.busy_label = QLabel("İşlem yapılıyor...")
        self.busy_label.setObjectName("mainTitle")
        self.busy_label.setAlignment(Qt.AlignCenter)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setTextVisible(True)
        self.busy_progress.setFormat("%p%")
        bl.addWidget(self.busy_label)
        bl.addWidget(self.busy_progress)
        self.position_busy_overlay()

    def load_table(self):
        self.table.setRowCount(len(self.users))
        for r, u in enumerate(self.users):
            vals = [u.get("name", ""), u.get("yi_yd", "Yİ"), "Evet" if u.get("active", True) else "Hayır", u.get("note", "")]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Sütun 1: Yİ / YD dropdown
        self.table.setItemDelegateForColumn(1, DropdownDelegate(["Yİ", "YD"], self.table))
        # Sütun 2: Evet / Hayır dropdown
        self.table.setItemDelegateForColumn(2, DropdownDelegate(["Evet", "Hayır"], self.table))

    def position_busy_overlay(self):
        if not hasattr(self, "busy_overlay"):
            return
        self.busy_overlay.setGeometry(self.rect())
        w, h = 420, 130
        x = max((self.busy_overlay.width() - w) // 2, 0)
        y = max((self.busy_overlay.height() - h) // 2, 0)
        self.busy_card.setGeometry(x, y, w, h)
        self.busy_overlay.raise_()

    def set_busy(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if not hasattr(self, "busy_overlay"):
            return
        self._saving = bool(visible)
        if visible:
            self.busy_label.setText(str(message or "İşlem yapılıyor..."))
            self.busy_progress.setValue(int(max(0, min(100, percent))))
            self.position_busy_overlay()
            self.save_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.table.setEnabled(False)
            if hasattr(self, "frozen_table"): self.frozen_table.setEnabled(False)
            self.busy_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.busy_overlay.hide()
            self.save_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            self.table.setEnabled(True)
            if hasattr(self, "frozen_table"): self.frozen_table.setEnabled(True)
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()

    def closeEvent(self, event):
        if self._saving:
            event.ignore()
            return
        super().closeEvent(event)

    def _sync_table_to_users(self):
        """Tablodaki hücre değerlerini self.users listesine yansıt."""
        for r in range(min(self.table.rowCount(), len(self.users))):
            u = self.users[r]
            if self.table.item(r, 0):
                u["name"] = self.table.item(r, 0).text().strip() or u.get("name", "")
            if self.table.item(r, 1):
                u["yi_yd"] = self.table.item(r, 1).text().strip() or "Yİ"
            if self.table.item(r, 2):
                u["active"] = self.table.item(r, 2).text().strip().lower() in ["evet", "true", "1", "aktif"]
            if self.table.item(r, 3):
                u["note"] = self.table.item(r, 3).text().strip()

    def add_user(self):
        self._sync_table_to_users()   # ← önce mevcut değerleri koru
        self.users.append({"name": "Yeni Kullanıcı", "yi_yd": "Yİ", "active": True, "note": ""})
        self.load_table()
        last = self.table.rowCount() - 1
        self.table.setCurrentCell(last, 0)
        self.table.editItem(self.table.item(last, 0))

    def delete_selected(self):
        r = self.table.currentRow()
        if r >= 0:
            self._sync_table_to_users()   # ← önce mevcut değerleri koru
            self.users.pop(r)
            self.load_table()

    def save(self):
        result = []
        seen = set()
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not name:
                continue
            if name.lower() in seen:
                QMessageBox.warning(self, "Uyarı", f"Tekrarlanan kullanıcı: {name}")
                return
            seen.add(name.lower())
            yi_yd_txt = (self.table.item(r, 1).text() if self.table.item(r, 1) else "Yİ").strip().upper()
            yi_yd = "YD" if yi_yd_txt == "YD" else "Yİ"
            active_txt = (self.table.item(r, 2).text() if self.table.item(r, 2) else "Evet").strip().lower()
            result.append({
                "name": name,
                "yi_yd": yi_yd,
                "active": active_txt in ["evet", "true", "1", "aktif", "yes"],
                "note": (self.table.item(r, 3).text() if self.table.item(r, 3) else ""),
            })
        self._save_payload = list(result)
        if _is_sts_store(self.store):
            try:
                self.set_busy(True, "Kullanıcılar kaydediliyor...", 25)
                self.store.write_users(self._save_payload, actor=self.store.current_actor())
                self.store.save()
                self.on_save_finished()
            except Exception as exc:
                self.on_save_failed(str(exc))
            return
        self._start_async_save()

    def _start_async_save(self):
        if self._save_thread and self._save_thread.isRunning():
            return
        self.set_busy(True, "Kullanıcı güncellemesi başlatılıyor...", 6)
        self._save_thread = QThread(self)
        self._save_worker = UserSaveWorker(self.store.path, self._save_payload, self.store.current_actor())
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.progress.connect(self.on_save_progress)
        self._save_worker.finished.connect(self.on_save_finished)
        self._save_worker.failed.connect(self.on_save_failed)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.failed.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._save_worker.deleteLater)
        self._save_thread.finished.connect(self._save_thread.deleteLater)
        self._save_thread.finished.connect(self._clear_save_refs)
        self._save_thread.start()

    def _clear_save_refs(self):
        self._save_worker = None
        self._save_thread = None

    def on_save_progress(self, percent: int, message: str):
        self.set_busy(True, str(message or "İşlem yapılıyor..."), int(max(0, min(100, int(percent or 0)))))

    def on_save_finished(self):
        try:
            self.set_busy(True, "Yerel önbellek yenileniyor...", 98)
            self.store.reload_from_disk()
            self.users = self.store.load_users(active_only=False)
            self.changed = True
            self.set_busy(False)
            self.show_footer_status("Kullanıcılar kaydedildi", kind="success")
        except Exception as exc:
            self.set_busy(False)
            self.show_footer_status(f"Yenileme hatası: {exc}", kind="error", duration=4000)

    def on_save_failed(self, error_text: str):
        self.set_busy(False)
        self.show_footer_status("Kaydetme hatası! Detay için loga bakın.", kind="error", duration=4000)
        QMessageBox.critical(self, "Kullanıcı kaydetme hatası", f"Kaydetme sırasında hata oluştu:\n\n{error_text}")


class ComponentManagerDialog(StyledDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__("Bileşen Yönetimi", parent)
        self.store = store
        self.components = store.load_components()
        self.changed = False
        self._save_thread: Optional[QThread] = None
        self._save_worker: Optional[ComponentSaveWorker] = None
        self._save_payload: List[dict] = []
        self._saving = False
        self._syncing_selection = False
        self.resize(860, 560)
        self.build()
        self.load_table()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        hero = QFrame()
        hero.setObjectName("componentHero")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(16, 12, 16, 12)
        hero_lay.setSpacing(6)
        title = QLabel("Bileşen Yönetimi")
        title.setObjectName("dialogTitle")
        hero_lay.addWidget(title)
        root.addWidget(hero)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        add = QPushButton("+ Bileşen Ekle")
        add.clicked.connect(self.add_component)
        delb = QPushButton("Seçili Bileşeni Sil")
        delb.setObjectName("danger")
        delb.clicked.connect(self.delete_selected)
        btns.addWidget(add)
        btns.addWidget(delb)
        btns.addStretch()
        root.addLayout(btns)

        tbl_row = QHBoxLayout()
        tbl_row.setSpacing(10)
        tbl_row.setContentsMargins(0, 0, 0, 0)

        left_panel = QFrame()
        left_panel.setObjectName("componentPanel")
        left_panel.setFixedWidth(360)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_head = QFrame()
        left_head.setObjectName("componentPanelHead")
        lh = QHBoxLayout(left_head)
        lh.setContentsMargins(12, 0, 12, 0)
        lh.addWidget(QLabel("Bileşen Bilgileri"))
        lh.addStretch()
        left_layout.addWidget(left_head)

        self.frozen_table = QTableWidget()
        self.frozen_table.setAlternatingRowColors(True)
        self.frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.verticalHeader().setVisible(False)
        self.frozen_table.setColumnCount(4)
        self.frozen_table.setHorizontalHeaderLabels(["#", "Bileşen Adı", "Birim", "Aktif Mi"])
        self.frozen_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.frozen_table.setSelectionMode(QTableWidget.SingleSelection)
        self.frozen_table.itemSelectionChanged.connect(self.sync_selection_from_left)
        self.frozen_table.cellClicked.connect(lambda r, c: self.select_row(r))
        self.frozen_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.frozen_table.setColumnWidth(0, 36)
        self.frozen_table.setColumnWidth(1, 160)
        self.frozen_table.setColumnWidth(2, 72)
        self.frozen_table.setColumnWidth(3, 84)
        self.frozen_table.horizontalHeader().setStretchLastSection(True)
        self.frozen_table.setStyleSheet("""
            QTableWidget { border:0; gridline-color:#d8e4f0; background:#ffffff; alternate-background-color:#f6faff; }
            QHeaderView::section { background:#eaf0f6; color:#405a7d; font-weight:800; border:1px solid #d8e4f0; height:34px; }
            QTableWidget::item { border-color:#d8e4f0; padding:4px; }
            QTableWidget::item:selected { background:#eef6ff; color:#002b5c; }
        """)
        left_layout.addWidget(self.frozen_table, 1)
        tbl_row.addWidget(left_panel, 0)

        right_panel = QFrame()
        right_panel.setObjectName("componentPanel")
        self.right_panel = right_panel
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_head = QFrame()
        right_head.setObjectName("componentPanelHead")
        rh = QHBoxLayout(right_head)
        rh.setContentsMargins(12, 0, 8, 0)
        rh.addWidget(QLabel("Platform Yetkilendirmeleri"))
        rh.addStretch()
        self.platform_search = QLineEdit()
        self.platform_search.setPlaceholderText("Platform ara...")
        self.platform_search.setFixedWidth(180)
        self.platform_search.textChanged.connect(self.apply_platform_filter)
        show_all = QPushButton("Tümünü Göster")
        show_all.setObjectName("secondary")
        show_all.clicked.connect(lambda: self.platform_search.clear())
        rh.addWidget(self.platform_search)
        rh.addWidget(show_all)
        right_layout.addWidget(right_head)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.cellClicked.connect(self.on_component_cell_clicked)
        self.table.itemSelectionChanged.connect(self.sync_selection_from_right)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet("""
            QTableWidget { border:0; gridline-color:#d8e4f0; background:#ffffff; alternate-background-color:#f6faff; }
            QHeaderView::section { background:#eaf0f6; color:#405a7d; font-weight:800; border:1px solid #d8e4f0; height:34px; }
            QTableWidget::item { border-color:#d8e4f0; padding:4px; }
            QTableWidget::item:selected { background:#eef6ff; color:#002b5c; }
        """)
        right_layout.addWidget(self.table, 1)
        tbl_row.addWidget(right_panel, 1)
        root.addLayout(tbl_row, 1)

        self.frozen_table.verticalScrollBar().valueChanged.connect(self.table.verticalScrollBar().setValue)
        self.table.verticalScrollBar().valueChanged.connect(self.frozen_table.verticalScrollBar().setValue)

        foot = QHBoxLayout()
        self.footer_status = self.make_footer_status_label()
        foot.addWidget(self.footer_status, 1, Qt.AlignVCenter)
        foot.addStretch()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self.save)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.setObjectName("secondary")
        self.close_btn.clicked.connect(self.reject)
        foot.addWidget(self.save_btn)
        foot.addWidget(self.close_btn)
        root.addLayout(foot)

        self.setStyleSheet(self.styleSheet() + """
            QFrame#componentHero { background:#eef4fa; border-radius:6px; }
            QFrame#componentPanel { background:#ffffff; border:1px solid #d8e4f0; border-radius:8px; }
            QFrame#componentPanelHead { background:#eef3f8; border-bottom:1px solid #d8e4f0; min-height:40px; max-height:40px; }
            QFrame#componentPanelHead QLabel { color:#314d72; font-weight:800; }
        """)

        self.busy_overlay = QFrame(self)
        self.busy_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.86); }")
        self.busy_overlay.hide()
        self.busy_card = QFrame(self.busy_overlay)
        self.busy_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.97); border: 1px solid #d8e2ed; border-radius: 10px; }"
        )
        bl = QVBoxLayout(self.busy_card)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(8)
        self.busy_label = QLabel("İşlem yapılıyor...")
        self.busy_label.setObjectName("mainTitle")
        self.busy_label.setAlignment(Qt.AlignCenter)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setTextVisible(True)
        self.busy_progress.setFormat("%p%")
        bl.addWidget(self.busy_label)
        bl.addWidget(self.busy_progress)
        self._busy_cursor_on = False
        self.position_busy_overlay()

    def _make_platform_item(self, checked: bool) -> QTableWidgetItem:
        it = QTableWidgetItem("✓" if checked else "")
        it.setTextAlignment(Qt.AlignCenter)
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it.setData(Qt.UserRole, bool(checked))
        it.setForeground(QColor("#0f7a31") if checked else QColor("#64748b"))
        if checked:
            it.setBackground(QColor("#e9fff1"))
        return it

    def select_row(self, row: int):
        if row < 0:
            return
        self._syncing_selection = True
        try:
            self.frozen_table.selectRow(row)
            self.table.selectRow(row)
            self.frozen_table.setCurrentCell(row, max(0, self.frozen_table.currentColumn()))
            self.table.setCurrentCell(row, max(0, self.table.currentColumn()))
        finally:
            self._syncing_selection = False

    def sync_selection_from_left(self):
        if self._syncing_selection:
            return
        self.select_row(self.frozen_table.currentRow())

    def sync_selection_from_right(self):
        if self._syncing_selection:
            return
        self.select_row(self.table.currentRow())

    def apply_platform_filter(self):
        text = (self.platform_search.text() if hasattr(self, 'platform_search') else '').strip().lower()
        for c in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(c)
            name = (header.text() if header else '').lower()
            self.table.setColumnHidden(c, bool(text) and text not in name)

    def position_busy_overlay(self):
        if not hasattr(self, "busy_overlay"):
            return
        self.busy_overlay.setGeometry(self.rect())
        w, h = 420, 130
        x = max((self.busy_overlay.width() - w) // 2, 0)
        y = max((self.busy_overlay.height() - h) // 2, 0)
        self.busy_card.setGeometry(x, y, w, h)
        self.busy_overlay.raise_()

    def set_busy(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if not hasattr(self, "busy_overlay"):
            return
        self._saving = bool(visible)
        if visible:
            self.busy_label.setText(str(message or "İşlem yapılıyor..."))
            self.busy_progress.setValue(int(max(0, min(100, percent))))
            self.position_busy_overlay()
            self.save_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.table.setEnabled(False)
            self.frozen_table.setEnabled(False)
            self.busy_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.busy_overlay.hide()
            self.save_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            self.table.setEnabled(True)
            self.frozen_table.setEnabled(True)
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()

    def closeEvent(self, event):
        if self._saving:
            event.ignore()
            return
        super().closeEvent(event)

    def load_table(self):
        platforms = self.store.platform_names()
        n = len(self.components)

        self.frozen_table.blockSignals(True)
        self.table.blockSignals(True)
        self.frozen_table.setRowCount(n)
        self.table.setRowCount(n)
        self.table.setColumnCount(len(platforms))
        self.table.setHorizontalHeaderLabels(platforms)

        for r, comp in enumerate(self.components):
            vals = [str(r + 1), comp.name, comp.unit or "Adet", "Evet" if comp.active else "Hayır"]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter if c in (0, 2, 3) else Qt.AlignVCenter | Qt.AlignLeft)
                if c == 0:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setForeground(QColor("#245ce7"))
                    item.setBackground(QColor("#e8f0f8"))
                    font = item.font(); font.setBold(True); item.setFont(font)
                self.frozen_table.setItem(r, c, item)
            self.frozen_table.setRowHeight(r, 36)

            for i, p in enumerate(platforms):
                checked = bool(comp.platforms.get(p, False))
                self.table.setItem(r, i, self._make_platform_item(checked))
            self.table.setRowHeight(r, 36)

        for i in range(len(platforms)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 86)

        # Platform az olduğunda son sütun panelin sonuna kadar uzasın;
        # platform çok olduğunda sabit genişlikler korunur ve yatay scroll çalışır.
        self.table.horizontalHeader().setStretchLastSection(True)
        if hasattr(self, "right_panel"):
            platform_area = max(300, min(560, len(platforms) * 86 + 18))
            self.right_panel.setMaximumWidth(platform_area)

        self.frozen_table.blockSignals(False)
        self.table.blockSignals(False)
        # Aktif Mi sütununa (col 3) dropdown delegate
        self.frozen_table.setItemDelegateForColumn(3, DropdownDelegate(["Evet", "Hayır"], self.frozen_table))
        if n:
            self.select_row(0)
        self.apply_platform_filter()

    def on_component_cell_clicked(self, row: int, col: int):
        self.select_row(row)
        it = self.table.item(row, col)
        if not it:
            return
        checked = not bool(it.data(Qt.UserRole))
        new_item = self._make_platform_item(checked)
        self.table.setItem(row, col, new_item)
        self.table.setCurrentCell(row, col)

    def _sync_table_to_components(self):
        """Tablodaki hücre değerlerini self.components listesine yansıt."""
        platforms = self.store.platform_names()
        for r in range(min(self.frozen_table.rowCount(), len(self.components))):
            comp = self.components[r]
            if self.frozen_table.item(r, 1):
                comp.name = self.frozen_table.item(r, 1).text().strip() or comp.name
            if self.frozen_table.item(r, 2):
                comp.unit = self.frozen_table.item(r, 2).text().strip() or comp.unit
            if self.frozen_table.item(r, 3):
                comp.active = self.frozen_table.item(r, 3).text().strip().lower() in ["evet", "true", "1", "aktif"]
            for i, p in enumerate(platforms):
                it = self.table.item(r, i)
                if it is not None:
                    comp.platforms[p] = bool(it.data(Qt.UserRole))

    def add_component(self):
        self._sync_table_to_components()   # ← önce mevcut değerleri koru
        self.components.append(ComponentDef(name="Yeni Bileşen", unit="Adet", active=True, usage=1))
        self.load_table()
        new_row = len(self.components) - 1
        self.select_row(new_row)
        self.frozen_table.editItem(self.frozen_table.item(new_row, 1))

    def delete_selected(self):
        r = self.frozen_table.currentRow()
        if r < 0:
            r = self.table.currentRow()
        if r >= 0:
            self._sync_table_to_components()   # ← önce mevcut değerleri koru
            self.components.pop(r)
            self.load_table()

    def save(self):
        platforms = self.store.platform_names()
        old_usage = {str(c.name or "").strip().lower(): int(c.usage or 1) for c in self.components}
        result = []
        seen = set()
        for r in range(self.frozen_table.rowCount()):
            name = (self.frozen_table.item(r, 1).text() if self.frozen_table.item(r, 1) else "").strip()
            if not name:
                continue
            if name.lower() in seen:
                QMessageBox.warning(self, "Uyarı", f"Tekrarlanan bileşen: {name}")
                return
            seen.add(name.lower())
            comp = ComponentDef(
                name=name,
                version="",
                unit=(self.frozen_table.item(r, 2).text() if self.frozen_table.item(r, 2) else "Adet"),
                active=(self.frozen_table.item(r, 3).text() if self.frozen_table.item(r, 3) else "Evet").strip().lower() in ["evet", "true", "1", "aktif"],
                usage=old_usage.get(name.lower(), 1),
                platforms={}
            )
            for i, p in enumerate(platforms):
                it = self.table.item(r, i)
                comp.platforms[p] = bool(it and it.data(Qt.UserRole))
            result.append(comp)
        payload: List[dict] = []
        for comp in result:
            payload.append({
                "name": str(comp.name or "").strip(),
                "version": str(comp.version or ""),
                "unit": str(comp.unit or "Adet"),
                "active": bool(comp.active),
                "usage": int(comp.usage or 1),
                "platforms": dict(comp.platforms or {}),
            })
        self._save_payload = payload
        if _is_sts_store(self.store):
            try:
                self.set_busy(True, "Bileşenler kaydediliyor...", 25)
                self.store.write_components(result, actor=self.store.current_actor())
                self.store.save()
                self.on_save_finished({})
            except Exception as exc:
                self.on_save_failed(str(exc))
            return
        self._start_async_save()

    def _start_async_save(self):
        if self._save_thread and self._save_thread.isRunning():
            return
        self.set_busy(True, "Bileşen güncellemesi başlatılıyor...", 5)
        self._save_thread = QThread(self)
        self._save_worker = ComponentSaveWorker(self.store.path, self._save_payload, self.store.current_actor())
        self._save_worker.moveToThread(self._save_thread)
        self._save_thread.started.connect(self._save_worker.run)
        self._save_worker.progress.connect(self.on_save_progress)
        self._save_worker.finished.connect(self.on_save_finished)
        self._save_worker.failed.connect(self.on_save_failed)
        self._save_worker.finished.connect(self._save_thread.quit)
        self._save_worker.failed.connect(self._save_thread.quit)
        self._save_thread.finished.connect(self._save_worker.deleteLater)
        self._save_thread.finished.connect(self._save_thread.deleteLater)
        self._save_thread.finished.connect(self._clear_save_refs)
        self._save_thread.start()

    def _clear_save_refs(self):
        self._save_worker = None
        self._save_thread = None

    def on_save_progress(self, percent: int, message: str):
        self.set_busy(True, str(message or "İşlem yapılıyor..."), int(max(0, min(100, int(percent or 0)))))

    def on_save_finished(self, _result: object):
        try:
            self.set_busy(True, "Yerel önbellek yenileniyor...", 98)
            self.store.reload_from_disk()
            self.components = self.store.load_components()
            self.changed = True
            self.set_busy(False)
            self.load_table()
            self.show_footer_status("Bileşenler kaydedildi", kind="success")
        except Exception as exc:
            self.set_busy(False)
            self.show_footer_status("Bileşenler kaydedildi, yenileme hatası oluştu.", kind="error", duration=4000)
            QMessageBox.critical(self, "Hata", f"Bileşenler kaydedildi ancak yenileme sırasında hata oluştu:\n\n{exc}")

    def on_save_failed(self, error_text: str):
        self.set_busy(False)
        self.show_footer_status("Kaydetme hatası! Detay için loga bakın.", kind="error", duration=4000)
        QMessageBox.critical(self, "Bileşen kaydetme hatası", f"Kaydetme sırasında hata oluştu:\n\n{error_text}")



from src.ui.dialogs.platforms import PlatformManagerDialog, PlatformDialog

class MultiUserSelectWidget(QWidget):
    changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._available: List[str] = []
        self._selected: List[str] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox(self)
        self.combo.setEditable(True)
        self.combo.lineEdit().setReadOnly(True)
        self.combo.lineEdit().setPlaceholderText("Kullanıcı seçiniz...")
        self.combo.view().pressed.connect(self._on_item_pressed)
        lay.addWidget(self.combo, 1)
        self._sync()

    def set_available_users(self, user_names: List[str]):
        seen = set()
        vals = []
        for u in list(user_names or []):
            n = str(u or "").strip()
            if not n:
                continue
            k = n.casefold()
            if k in seen:
                continue
            seen.add(k)
            vals.append(n)
        self._available = vals
        self._selected = [x for x in self._selected if x in self._available]
        self._rebuild_items()
        self._sync()

    def set_users(self, user_names: List[str]):
        seen = set()
        vals = []
        for u in list(user_names or []):
            n = str(u or "").strip()
            if not n:
                continue
            k = n.casefold()
            if k in seen:
                continue
            seen.add(k)
            vals.append(n)
        self._selected = vals
        self._rebuild_items()
        self._sync()
        self.changed.emit()

    def selected_users(self) -> List[str]:
        return list(self._selected)

    def _sync(self):
        txt = ", ".join(self._selected)
        self.combo.lineEdit().setText(txt)
        self.combo.setToolTip(txt)

    def _rebuild_items(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        for name in self._available:
            self.combo.addItem(name)
            it = self.combo.model().item(self.combo.count() - 1, 0)
            if it is None:
                continue
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setData(Qt.Checked if name in self._selected else Qt.Unchecked, Qt.CheckStateRole)
        self.combo.blockSignals(False)

    def _on_item_pressed(self, idx):
        it = self.combo.model().itemFromIndex(idx)
        if it is None:
            return
        checked = it.data(Qt.CheckStateRole) == Qt.Checked
        it.setData(Qt.Unchecked if checked else Qt.Checked, Qt.CheckStateRole)
        name = str(it.text() or "").strip()
        if not name:
            return
        if checked:
            self._selected = [x for x in self._selected if x != name]
        elif name not in self._selected:
            self._selected.append(name)
        self._sync()
        self.changed.emit()

class ContractDialog(StyledDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__("Yeni Sözleşme", parent)
        self.store = store
        self.user_records = store.load_users()
        self.user_to_yi_yd = {u.get("name", ""): u.get("yi_yd", "Yİ") for u in self.user_records}
        self.result: Optional[ContractInfo] = None
        self._sd_verified_info: Optional[dict] = None
        self._sd_anchor_start_row: int = 0
        self._sd_anchor_end_row: int = 0
        self._sd_anchor_platform: str = ""
        self._sd_anchor_no: str = ""
        self.resize(720, 390)
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Yeni Sözleşme")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        desc = QLabel("Ana sözleşme bilgilerini girin. SD kayıtları ana sözleşme detay ekranından eklenecek.")
        desc.setObjectName("muted")
        root.addWidget(desc)

        grid = QGridLayout()
        self.no = QLineEdit(); self.no.setPlaceholderText("Örn: SZL-2026-001")

        # Sözleşme No satırı: input + Doğrula butonu + hata etiketi alt alta
        no_container = QWidget(self)
        no_container_lay = QVBoxLayout(no_container)
        no_container_lay.setContentsMargins(0, 0, 0, 0)
        no_container_lay.setSpacing(2)
        no_row = QWidget()
        no_lay = QHBoxLayout(no_row)
        no_lay.setContentsMargins(0, 0, 0, 0)
        no_lay.setSpacing(6)
        no_lay.addWidget(self.no, 1)
        self.verify_btn = QPushButton("Doğrula")
        self.verify_btn.setObjectName("secondary")
        self.verify_btn.setMinimumHeight(34)
        no_lay.addWidget(self.verify_btn, 0)
        self.no_dup_warn = QLabel("")
        self.no_dup_warn.setStyleSheet(
            "color:#dc2626; font-size:11px; font-weight:700; padding:0px;"
        )
        self.no_dup_warn.setVisible(False)
        no_container_lay.addWidget(no_row)
        no_container_lay.addWidget(self.no_dup_warn)

        self.platform = QComboBox(); self.platform.addItems(self.store.platform_names())
        self.user = MultiUserSelectWidget(self)
        self.user.set_available_users([u.get("name", "") for u in self.user_records])
        if self.user_records:
            self.user.set_users([self.user_records[0].get("name", "")])
        self.yi_yd = QLineEdit(); self.yi_yd.setReadOnly(True); self.yi_yd.setText("Yİ")
        self.ctype = QComboBox(); self.ctype.addItems(["Ana Sözleşme"])
        self.sd_code = QLineEdit(); self.sd_code.setPlaceholderText("SD-1"); self.sd_code.setEnabled(False)
        self.sig, self.sig_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.t0, self.t0_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.months = QSpinBox(); self.months.setRange(0, 240); self.months.setValue(0); self.months.setSuffix(" ay")
        self.completion = QLineEdit(); self.completion.setPlaceholderText("T0 + Ay ile otomatik hesaplanır (Termin)")
        self.completion.setReadOnly(True)
        self.note = QLineEdit(); self.note.setPlaceholderText("Not")

        self.t0.textChanged.connect(self.update_completion_date)
        self.months.valueChanged.connect(self.update_completion_date)
        self.user.changed.connect(self.update_user_yi_yd)
        self.ctype.currentTextChanged.connect(self.on_contract_type_changed)
        self.verify_btn.clicked.connect(lambda: self.verify_sd_reference(show_message=False))
        self.platform.currentTextChanged.connect(self.on_sd_ref_changed)
        self.no.textChanged.connect(self.on_sd_ref_changed)
        # Anlık duplikasyon kontrolü: no veya platform veya tip değişince tekrar kontrol
        self.no.editingFinished.connect(self._check_no_duplicate)
        self.platform.currentIndexChanged.connect(lambda _: self._check_no_duplicate())
        self.ctype.currentIndexChanged.connect(lambda _: self._check_no_duplicate())

        def add_field(label: str, widget, row: int, col: int):
            grid.addWidget(form_label(label), row * 2, col)
            grid.addWidget(widget, row * 2 + 1, col)

        add_field("Sözleşme No", no_container, 0, 0)
        add_field("Platform", self.platform, 0, 1)
        add_field("Kullanıcı", self.user, 1, 0)
        add_field("Yİ/YD", self.yi_yd, 1, 1)
        add_field("Sözleşme Tipi", self.ctype, 2, 0)
        add_field("İmza Tarihi", self.sig_wrap, 2, 1)
        root.addLayout(grid)

        timeline_card = QFrame()
        timeline_card.setObjectName("systemFormCard")
        timeline = QGridLayout(timeline_card)
        timeline.setContentsMargins(10, 8, 10, 8)
        timeline.setHorizontalSpacing(8)
        timeline.setVerticalSpacing(6)
        timeline.addWidget(form_label("T0 Başlangıç"), 0, 0)
        timeline.addWidget(form_label("T0+Ay"), 0, 2)
        timeline.addWidget(form_label("Termin Tarihi"), 0, 4)
        timeline.addWidget(self.t0_wrap, 1, 0)
        plus_lbl = QLabel("+"); plus_lbl.setObjectName("muted"); plus_lbl.setAlignment(Qt.AlignCenter)
        eq_lbl = QLabel("="); eq_lbl.setObjectName("muted"); eq_lbl.setAlignment(Qt.AlignCenter)
        timeline.addWidget(plus_lbl, 1, 1)
        timeline.addWidget(self.months, 1, 2)
        timeline.addWidget(eq_lbl, 1, 3)
        timeline.addWidget(self.completion, 1, 4)
        timeline.setColumnStretch(0, 2)
        timeline.setColumnStretch(2, 1)
        timeline.setColumnStretch(4, 2)
        root.addWidget(timeline_card)

        root.addWidget(form_label("Not"))
        root.addWidget(self.note)

        self.sd_verify_hint = QLabel("")
        self.sd_verify_hint.setObjectName("muted")
        self.sd_verify_hint.setVisible(False)
        root.addWidget(self.sd_verify_hint)

        self.update_user_yi_yd()
        self.on_contract_type_changed()

        row = QHBoxLayout(); row.addStretch()
        save = QPushButton("Devam Et")
        save.clicked.connect(self.save)
        row.addWidget(save)
        root.addLayout(row)

    def is_sd_mode(self) -> bool:
        return self.ctype.currentText().strip() == "Sözleşme Değişikliği"

    def on_sd_ref_changed(self):
        self._sd_verified_info = None
        self._sd_anchor_start_row = 0
        self._sd_anchor_end_row = 0
        self._sd_anchor_platform = ""
        self._sd_anchor_no = ""
        if self.is_sd_mode():
            suggested = self.store.next_sd_code(self.platform.currentText(), self.no.text().strip())
            if not self.sd_code.text().strip():
                self.sd_code.setText(suggested)
            self.sd_verify_hint.setText("Doğrulama bekleniyor.")
            self.sd_verify_hint.setStyleSheet("color:#64748b; font-weight:700;")

    def on_contract_type_changed(self):
        sd = self.is_sd_mode()
        self.sd_code.setEnabled(sd)
        self.verify_btn.setVisible(sd)
        if hasattr(self, "sd_label"):
            self.sd_label.setVisible(sd)
        self.sd_code.setVisible(sd)
        self.sd_verify_hint.setVisible(sd)
        if sd:
            self.no.setPlaceholderText("Mevcut kontrat no")
            if not self.sd_code.text().strip():
                self.sd_code.setText(self.store.next_sd_code(self.platform.currentText(), self.no.text().strip()))
            self.sd_verify_hint.setText("Doğrulama bekleniyor.")
            self.sd_verify_hint.setStyleSheet("color:#64748b; font-weight:700;")
            self.user.setEnabled(False)
            self.yi_yd.setReadOnly(True)
        else:
            self.no.setPlaceholderText("Örn: SZL-2026-001")
            self.sd_code.clear()
            self.sd_verify_hint.clear()
            self.sd_verify_hint.setStyleSheet("")
            self._sd_verified_info = None
            self._sd_anchor_start_row = 0
            self._sd_anchor_end_row = 0
            self._sd_anchor_platform = ""
            self._sd_anchor_no = ""
            self.user.setEnabled(True)
            self.update_user_yi_yd()

    def _set_user_from_main_contract(self, info: dict):
        target_user = str(info.get("user", "") or "").strip()
        if target_user:
            cur = self.user.selected_users()
            if target_user not in cur:
                cur = [target_user]
            self.user.set_users(cur)
        yi_yd = str(info.get("yi_yd", "Yİ") or "Yİ").strip().upper()
        self.yi_yd.setText("YD" if yi_yd == "YD" else "Yİ")

    def verify_sd_reference(self, show_message: bool = True) -> bool:
        if not self.is_sd_mode():
            return True
        no = self.no.text().strip()
        platform = self.platform.currentText().strip()
        if not no or not platform:
            if show_message:
                QMessageBox.warning(self, "Eksik", "Önce platform ve kontrat no girin.")
            self.sd_verify_hint.setText("Önce platform ve kontrat no girin.")
            self.sd_verify_hint.setStyleSheet("color:#b91c1c; font-weight:700;")
            return False
        info = self.store.find_main_contract_info(platform, no)
        if not info:
            if show_message:
                QMessageBox.warning(self, "Bulunamadı", "Bu platformda girilen kontrat no için Ana Sözleşme bulunamadı.")
            self._sd_verified_info = None
            self._sd_anchor_start_row = 0
            self._sd_anchor_end_row = 0
            self._sd_anchor_platform = ""
            self._sd_anchor_no = ""
            self.sd_verify_hint.setText("✗ Ana sözleşme bulunamadı.")
            self.sd_verify_hint.setStyleSheet("color:#b91c1c; font-weight:700;")
            return False
        self._sd_verified_info = info
        self._sd_anchor_start_row = int(info.get("block_start") or info.get("row") or 0)
        self._sd_anchor_end_row = int(info.get("block_end") or self._sd_anchor_start_row or 0)
        self._sd_anchor_platform = str(platform or "")
        self._sd_anchor_no = str(no or "")
        self._set_user_from_main_contract(info)
        # Her doğrulamada ilgili kontrat için bir sonraki SD kodunu otomatik getir.
        self.sd_code.setText(self.store.next_sd_code(platform, no))
        self.sd_verify_hint.setText(f"✓ Ana sözleşme bulundu: {no}")
        self.sd_verify_hint.setStyleSheet("color:#047857; font-weight:800;")
        if show_message:
            QMessageBox.information(self, "Doğrulandı", f"Ana sözleşme bulundu. SD kaydı {no} kontrat no altında eklenecek.")
        return True

    def update_completion_date(self):
        d = parse_iso_date(self.t0.text())
        if not d:
            self.completion.clear()
            return
        self.completion.setText(add_months(d, self.months.value()).isoformat())

    def date_picker_events(self) -> List[dict]:
        deadline = parse_iso_date(self.completion.text() if hasattr(self, "completion") else "")
        if not deadline and hasattr(self, "t0") and hasattr(self, "months"):
            t0 = parse_iso_date(self.t0.text())
            if t0:
                deadline = add_months(t0, self.months.value())
        if not deadline:
            return []
        no = self.no.text().strip() if hasattr(self, "no") else ""
        ctype = self.ctype.currentText().strip() if hasattr(self, "ctype") else "Sözleşme"
        return [{
            "date": deadline,
            "title": f"{no or 'Yeni Sözleşme'} {ctype}".strip(),
            "lines": [f"Termin tarihi: {deadline.isoformat()}"],
            "tag": "Sözleşme termini",
            "color": "#f97316",
        }]

    def update_user_yi_yd(self):
        if self.is_sd_mode() and self._sd_verified_info:
            self._set_user_from_main_contract(self._sd_verified_info)
            return
        selected = (self.user.selected_users() or [""])[0].strip()
        yi_yd = self.user_to_yi_yd.get(selected, "Yİ")
        self.yi_yd.setText("YD" if str(yi_yd).upper() == "YD" else "Yİ")

    def _normalized_sd_code(self) -> str:
        raw = str(self.sd_code.text() or "").strip().upper().replace(" ", "")
        if not raw:
            return ""
        m = re.match(r"^SD[-_]?(\d+)$", raw)
        if m:
            return f"SD-{int(m.group(1))}"
        return ""

    def _check_no_duplicate(self):
        """Sözleşme no + platform + tip kombinasyonu zaten varsa kırmızı uyarı göster."""
        if not hasattr(self, 'no_dup_warn'):
            return
        no = self.no.text().strip()
        platform = self.platform.currentText().strip()
        if not no or not platform:
            self.no_dup_warn.setVisible(False)
            self.no.setStyleSheet("")
            return
        contract_type = "Ana Sözleşme"
        if self.is_sd_mode():
            sd = self._normalized_sd_code()
            contract_type = sd if sd else self.sd_code.text().strip()
        try:
            existing = self.store.list_main_contracts(platform)
            for ex in existing:
                ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                if (ex_no == self.store._normalize_label(no) and
                        ex_type == self.store._normalize_label(contract_type)):
                    self.no_dup_warn.setText(
                        f"⚠  '{platform}' platformunda bu sözleşme no zaten mevcut!"
                    )
                    self.no_dup_warn.setVisible(True)
                    self.no.setStyleSheet(
                        "QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                    )
                    return
        except Exception:
            pass
        self.no_dup_warn.setVisible(False)
        self.no.setStyleSheet("")

    def _highlight_required(self, widget, error: bool):
        """Zorunlu alan boşsa kırmızı çerçeve, doluysa normal."""
        if error:
            widget.setStyleSheet("QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                                 "QSpinBox{border:1.5px solid #dc2626; background:#fff5f5;}")
        else:
            widget.setStyleSheet("")

    def save(self):
        if not self.no.text().strip():
            QMessageBox.warning(self, "Eksik", "Sözleşme no girin.")
            return
        if not self.platform.currentText():
            QMessageBox.warning(self, "Eksik", "Önce platform oluşturun.")
            return
        if self.is_sd_mode() and not self.verify_sd_reference(show_message=False):
            QMessageBox.warning(self, "Doğrulama", "Sözleşme Değişikliği için önce geçerli kontrat no doğrulaması gerekir.")
            return
        sel_users = self.user.selected_users()
        if not sel_users:
            QMessageBox.warning(self, "Eksik", "Önce Kullanıcı Yönetimi ekranından kullanıcı tanımlayın.")
            return
        # Zorunlu tarih ve ay alanları
        sig_ok = bool(self.sig.text().strip())
        t0_ok = bool(self.t0.text().strip())
        months_ok = self.months.value() > 0
        self._highlight_required(self.sig, not sig_ok)
        self._highlight_required(self.t0, not t0_ok)
        self._highlight_required(self.months, not months_ok)
        if not sig_ok or not t0_ok or not months_ok:
            missing = []
            if not sig_ok:   missing.append("İmza Tarihi")
            if not t0_ok:    missing.append("T0 Tarihi")
            if not months_ok: missing.append("T0+Ay (en az 1)")
            QMessageBox.warning(self, "Zorunlu Alanlar",
                                "Aşağıdaki alanlar doldurulmadan devam edilemez:\n• " +
                                "\n• ".join(missing))
            return
        if self.sig.text().strip() and not parse_iso_date(self.sig.text()):
            QMessageBox.warning(self, "Tarih hatası", "İmza tarihi yyyy-aa-gg formatında olmalı. Örn: 2026-05-02")
            return
        if self.t0.text().strip() and not parse_iso_date(self.t0.text()):
            QMessageBox.warning(self, "Tarih hatası", "T0 tarihi yyyy-aa-gg formatında olmalı. Örn: 2026-05-02")
            return

        contract_type = "Ana Sözleşme"
        if self.is_sd_mode():
            sd_code = self._normalized_sd_code()
            if not sd_code:
                QMessageBox.warning(self, "Format", "SD kodu SD-1, SD-2 gibi sayısal formatta olmalı.")
                return
            self.sd_code.setText(sd_code)
            contract_type = sd_code

        # Aynı platform + sözleşme no + tip kombinasyonuna izin verme
        platform_check = self.platform.currentText()
        no_check = self.no.text().strip()
        try:
            existing_contracts = self.store.list_main_contracts(platform_check)
            for ex in existing_contracts:
                ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                if (ex_no == self.store._normalize_label(no_check) and
                        ex_type == self.store._normalize_label(contract_type)):
                    QMessageBox.warning(
                        self, "Tekrar Eden Kayıt",
                        f"'{platform_check}' platformunda '{no_check}' sözleşme numarası ve "
                        f"'{contract_type}' tipi için zaten bir kayıt mevcut.\n\n"
                        "Aynı platform + no + tip kombinasyonu kullanılamaz."
                    )
                    return
        except Exception:
            pass  # Kontrol başarısız olursa devam et

        self.update_completion_date()
        users = self.user.selected_users()
        user_display = ", ".join(users)
        self.result = ContractInfo(
            no=self.no.text().strip(),
            platform=self.platform.currentText(),
            user=user_display,
            yi_yd=self.yi_yd.text().strip() or "Yİ",
            contract_type=contract_type,
            signature_date=iso_or_blank(self.sig.text()),
            t0_date=iso_or_blank(self.t0.text()),
            t0_months=self.months.value(),
            completion_date=self.completion.text().strip(),
            status="Başlanmadı",
            note=self.note.text().strip(),
            acceptance_date="",
            sd_anchor_start_row=self._sd_anchor_start_row if self.is_sd_mode() else 0,
            sd_anchor_end_row=self._sd_anchor_end_row if self.is_sd_mode() else 0,
            sd_anchor_platform=self._sd_anchor_platform if self.is_sd_mode() else "",
            sd_anchor_no=self._sd_anchor_no if self.is_sd_mode() else "",
            users=users,
        )
        self.accept()


class ContractEditDialog(StyledDialog):
    """Mevcut sözleşmenin ANA BİLGİLERİNİ güncelleme ekranı.

    - Sözleşme No düzenlenebilir; Platform ve Sözleşme Tipi salt okunur.
    - Diğer temel alanlar düzenlenebilir; sistemler ve kabuller değişmez.
    - Güncellemede platform + sözleşme tipi + sözleşme no kombinasyonu tekil kalır.
    """

    def __init__(
        self,
        store: ExcelStore,
        ci: ContractInfo,
        parent=None,
        title_text: str = "Ana Bilgileri Düzenle",
        save_text: str = "Güncelle",
        info_text: Optional[str] = None,
    ):
        super().__init__(title_text, parent)
        self.store = store
        self.ci = ci
        self.title_text = title_text
        self.save_text = save_text
        self.info_text = info_text
        self.external_events_provider = getattr(parent, "date_picker_events", None)
        self.user_records = self.store.load_users()
        self.user_to_yi_yd = {u.get("name", ""): u.get("yi_yd", "Yİ") for u in self.user_records}
        self.result: Optional[ContractInfo] = None
        self.resize(700, 430)
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)

        title = QLabel(self.title_text)
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        info = QLabel(
            self.info_text or
            "Yalnızca sözleşmenin temel bilgileri güncellenir. "
            "Sistemler ve kabuller değişmez."
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        root.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        def readonly(text: str) -> QLineEdit:
            w = QLineEdit(str(text or ""))
            w.setReadOnly(True)
            w.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
            return w

        # ── Salt okunur alanlar ──────────────────────────────────────
        ctype_text = str(self.ci.contract_type or "").strip()
        self._is_sd_contract = bool(
            re.match(r"^SD-\d+$", ctype_text.upper()) or
            self.store._normalize_label(ctype_text) == self.store._normalize_label("Sözleşme Değişikliği")
        )
        self._no_lbl       = QLineEdit(str(self.ci.no or ""))
        self._plat_lbl     = readonly(self.ci.platform)
        self._type_lbl     = readonly(self.ci.contract_type)
        if self._is_sd_contract:
            self._no_lbl.setReadOnly(True)
            self._no_lbl.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
            no_warn_text = "SD kayıtlarının sözleşme no alanı ana sözleşmeye bağlıdır; doğrudan değiştirilemez."
        else:
            no_warn_text = "Aynı platform + sözleşme tipi + sözleşme no kombinasyonu kullanılamaz."
            self._no_lbl.textChanged.connect(self._check_duplicate_contract_key)
        self._no_dup_warn = QLabel(no_warn_text)
        self._no_dup_warn.setObjectName("warning")
        self._no_dup_warn.setWordWrap(True)
        self._no_dup_warn.setVisible(self._is_sd_contract)

        # ── Düzenlenebilir alanlar ────────────────────────────────────
        self.user = MultiUserSelectWidget(self)
        self.user.set_available_users([u.get("name", "") for u in self.user_records])
        init_users = list(getattr(self.ci, "users", []) or [])
        if not init_users and str(self.ci.user or "").strip():
            init_users = [x.strip() for x in str(self.ci.user or "").split(",") if x.strip()]
        self.user.set_users(init_users)

        self.yi_yd = QLineEdit()
        self.yi_yd.setReadOnly(True)
        self.yi_yd.setText(str(self.ci.yi_yd or "Yİ"))
        self.yi_yd.setMinimumHeight(34)

        self.sig, self.sig_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.sig.setText(str(self.ci.signature_date or ""))

        self.t0, self.t0_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.t0.setText(str(self.ci.t0_date or ""))

        self.months = QSpinBox()
        self.months.setRange(0, 240)
        self.months.setValue(int(self.ci.t0_months or 0))
        self.months.setSuffix(" ay")
        self.months.setMinimumHeight(34)

        self.completion = QLineEdit()
        self.completion.setReadOnly(True)
        self.completion.setPlaceholderText("T0 + Ay ile otomatik")
        self.completion.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
        self.completion.setText(str(self.ci.completion_date or ""))

        self.note = QLineEdit()
        self.note.setPlaceholderText("Not")
        self.note.setText(str(self.ci.note or ""))

        self.t0.textChanged.connect(self._recalc)
        self.months.valueChanged.connect(self._recalc)
        self.user.changed.connect(self.update_user_yi_yd)
        self.update_user_yi_yd()
        self._recalc()

        def add_field(label: str, widget, row: int, col: int):
            grid.addWidget(form_label(label), row * 2, col)
            grid.addWidget(widget, row * 2 + 1, col)

        add_field("Sözleşme No", self._no_lbl, 0, 0)
        add_field("Platform", self._plat_lbl, 0, 1)
        add_field("Sözleşme Tipi", self._type_lbl, 1, 0)
        add_field("İmza Tarihi", self.sig_wrap, 1, 1)
        add_field("Kullanıcı", self.user, 2, 0)
        add_field("Yİ/YD", self.yi_yd, 2, 1)
        root.addLayout(grid)

        timeline_card = QFrame()
        timeline_card.setObjectName("systemFormCard")
        timeline = QGridLayout(timeline_card)
        timeline.setContentsMargins(10, 8, 10, 8)
        timeline.setHorizontalSpacing(8)
        timeline.setVerticalSpacing(6)
        timeline.addWidget(form_label("T0 Başlangıç"), 0, 0)
        timeline.addWidget(form_label("T0+Ay"), 0, 2)
        timeline.addWidget(form_label("Termin Tarihi"), 0, 4)
        timeline.addWidget(self.t0_wrap, 1, 0)
        plus_lbl = QLabel("+"); plus_lbl.setObjectName("muted"); plus_lbl.setAlignment(Qt.AlignCenter)
        eq_lbl = QLabel("="); eq_lbl.setObjectName("muted"); eq_lbl.setAlignment(Qt.AlignCenter)
        timeline.addWidget(plus_lbl, 1, 1)
        timeline.addWidget(self.months, 1, 2)
        timeline.addWidget(eq_lbl, 1, 3)
        timeline.addWidget(self.completion, 1, 4)
        timeline.setColumnStretch(0, 2)
        timeline.setColumnStretch(2, 1)
        timeline.setColumnStretch(4, 2)
        root.addWidget(timeline_card)

        root.addWidget(form_label("Not"))
        root.addWidget(self.note)
        root.addWidget(self._no_dup_warn)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save_btn = QPushButton(self.save_text)
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def update_user_yi_yd(self):
        selected = (self.user.selected_users() or [""])[0].strip()
        yi_yd = self.user_to_yi_yd.get(selected, "Yİ")
        self.yi_yd.setText("YD" if str(yi_yd).upper() == "YD" else "Yİ")


    def _recalc(self):
        d = parse_iso_date(self.t0.text())
        if d:
            self.completion.setText(add_months(d, self.months.value()).isoformat())
        else:
            self.completion.clear()

    def date_picker_events(self) -> List[dict]:
        events: List[dict] = []
        if callable(self.external_events_provider):
            try:
                events.extend(self.external_events_provider() or [])
            except Exception:
                pass
        deadline = parse_iso_date(self.completion.text() if hasattr(self, "completion") else "")
        if not deadline and hasattr(self, "t0") and hasattr(self, "months"):
            t0 = parse_iso_date(self.t0.text())
            if t0:
                deadline = add_months(t0, self.months.value())
        if deadline:
            events.append({
                "date": deadline,
                "title": f"{str(self.ci.no or '').strip() or 'Sözleşme'} {str(self.ci.contract_type or '').strip()}".strip(),
                "lines": [
                    f"Termin tarihi: {deadline.isoformat()}",
                    f"Durum: {str(getattr(self.ci, 'status', '') or '-')}",
                ],
                "tag": "Sözleşme termini",
                "color": "#f97316",
            })
        return events

    def _check_duplicate_contract_key(self) -> bool:
        """Başka bir kayıtta aynı platform + tip + no varsa uyarı gösterir."""
        no_text = self._no_lbl.text().strip()
        platform = str(self.ci.platform or "").strip()
        contract_type = str(self.ci.contract_type or "").strip()
        if not no_text or not platform or not contract_type:
            self._no_dup_warn.setVisible(self._is_sd_contract)
            if not self._is_sd_contract:
                self._no_lbl.setStyleSheet("")
            return False

        norm_no = self.store._normalize_label(no_text)
        norm_type = self.store._normalize_label(contract_type)
        current_row = int(getattr(self.ci, "entry_start_row", 0) or 0)
        try:
            existing_contracts = self.store.list_main_contracts(platform)
        except Exception:
            existing_contracts = []

        def mark_duplicate(message: str) -> bool:
            self._no_dup_warn.setText(message)
            self._no_dup_warn.setVisible(True)
            if not self._is_sd_contract:
                self._no_lbl.setStyleSheet(
                    "QLineEdit{border:1.5px solid #dc2626; background:#fff5f5;}"
                )
            return True

        for ex in existing_contracts:
            ex_row = int(ex.get("row") or 0)
            if current_row > 0 and ex_row == current_row:
                continue
            ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
            ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
            if ex_no == norm_no and ex_type == norm_type:
                return mark_duplicate(
                    f"⚠ '{platform}' platformunda '{contract_type}' tipi için "
                    f"'{no_text}' sözleşme numarası zaten mevcut. "
                    "Aynı platform + tip + no kombinasyonu kullanılamaz."
                )

        # Ana sözleşme no değişirken aynı no'ya bağlı SD kayıtları da taşınacak.
        # Bu yüzden taşınacak her SD tipi için hedef no altında çakışma var mı önceden kontrol edilir.
        old_no = str(self.ci.no or "").strip()
        if (not self._is_sd_contract and
                self.store._normalize_label(contract_type) == self.store._normalize_label("Ana Sözleşme") and
                self.store._normalize_label(old_no) != norm_no):
            linked_sd_rows = set()
            linked_sd_types = []
            for ex in existing_contracts:
                ex_type_raw = str(ex.get("type", "") or "").strip()
                is_sd_type = bool(
                    re.match(r"^SD-\d+$", ex_type_raw.upper()) or
                    self.store._normalize_label(ex_type_raw) == self.store._normalize_label("Sözleşme Değişikliği")
                )
                if not is_sd_type:
                    continue
                if self.store._normalize_label(str(ex.get("no", "") or "").strip()) != self.store._normalize_label(old_no):
                    continue
                linked_sd_rows.add(int(ex.get("row") or 0))
                linked_sd_types.append(ex_type_raw)
            for sd_type in linked_sd_types:
                norm_sd_type = self.store._normalize_label(sd_type)
                for ex in existing_contracts:
                    if int(ex.get("row") or 0) in linked_sd_rows:
                        continue
                    ex_no = self.store._normalize_label(str(ex.get("no", "") or "").strip())
                    ex_type = self.store._normalize_label(str(ex.get("type", "") or "").strip())
                    if ex_no == norm_no and ex_type == norm_sd_type:
                        return mark_duplicate(
                            f"⚠ Ana sözleşme no güncellenirse bağlı '{sd_type}' kaydı da "
                            f"'{no_text}' no'ya taşınacak; ancak bu platformda aynı no ve SD tipi zaten var."
                        )

        self._no_dup_warn.setVisible(self._is_sd_contract)
        if self._is_sd_contract:
            self._no_dup_warn.setText(
                "SD kayıtlarının sözleşme no alanı ana sözleşmeye bağlıdır; doğrudan değiştirilemez."
            )
        else:
            self._no_lbl.setStyleSheet("")
        return False

    def save(self):
        new_no_text = self._no_lbl.text().strip()
        if not new_no_text:
            QMessageBox.warning(self, "Zorunlu Alan", "Sözleşme No girilmelidir.")
            return
        if self._check_duplicate_contract_key():
            QMessageBox.warning(
                self,
                "Tekrar Eden Kayıt",
                "Aynı platform, sözleşme tipi ve sözleşme no ile başka bir kayıt bulundu. "
                "Lütfen farklı bir sözleşme no girin."
            )
            return
        sig_text = self.sig.text().strip()
        t0_text  = self.t0.text().strip()
        if not sig_text:
            QMessageBox.warning(self, "Zorunlu Alan", "İmza Tarihi girilmelidir.")
            return
        if not t0_text:
            QMessageBox.warning(self, "Zorunlu Alan", "T0 Tarihi girilmelidir.")
            return
        if self.months.value() <= 0:
            QMessageBox.warning(self, "Zorunlu Alan", "T0+Ay en az 1 olmalıdır.")
            return
        if not parse_iso_date(sig_text):
            QMessageBox.warning(self, "Tarih hatası", "İmza tarihi yyyy-aa-gg formatında olmalı.")
            return
        if not parse_iso_date(t0_text):
            QMessageBox.warning(self, "Tarih hatası", "T0 tarihi yyyy-aa-gg formatında olmalı.")
            return
        self._recalc()
        new_ci = copy.copy(self.ci)
        new_ci.no              = new_no_text
        selected_users = self.user.selected_users()
        if not selected_users:
            QMessageBox.warning(self, "Zorunlu Alan", "En az bir kullanıcı seçmelisiniz.")
            return
        new_ci.users           = selected_users
        new_ci.user            = ", ".join(selected_users)
        new_ci.yi_yd           = self.yi_yd.text().strip() or "Yİ"
        new_ci.signature_date  = iso_or_blank(sig_text)
        new_ci.t0_date         = iso_or_blank(t0_text)
        new_ci.t0_months       = self.months.value()
        new_ci.completion_date = self.completion.text().strip()
        new_ci.status          = str(self.ci.status or "Başlanmadı")
        new_ci.note            = self.note.text().strip()
        self.result = new_ci
        self.accept()


class TagAssignDialog(StyledDialog):
    def __init__(self, store: ExcelStore, already_assigned: Optional[List[dict]] = None, parent=None):
        super().__init__("Etiket Ekle", parent)
        self.store = store
        self.all_tags = list(store.load_tag_defs(active_only=True) or [])
        assigned = list(already_assigned or [])
        self.already_ids = {
            int((t or {}).get("id") or 0)
            for t in assigned
            if isinstance(t, dict) and int((t or {}).get("id") or 0) > 0
        }
        self.already_keys = {
            self.store._normalize_label(str((t or {}).get("name") or ""))
            for t in assigned
            if isinstance(t, dict) and str((t or {}).get("name") or "").strip()
        }
        self.available_tags = [tag for tag in self.all_tags if not self._is_tag_already_assigned(tag)]
        self.selected: Dict[str, TagDef] = {}
        self.result: List[dict] = []
        self.resize(520, 380)
        self.build()

    def _is_tag_already_assigned(self, tag: TagDef) -> bool:
        tag_id = int(getattr(tag, "id", 0) or 0)
        if tag_id and tag_id in self.already_ids:
            return True
        return self.store._normalize_label(str(tag.name or "")) in self.already_keys

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        title = QLabel("Etiket Ekle")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        root.addWidget(form_label("Etiket Seç"))
        self.tags_wrap = QFrame()
        self.tags_wrap.setObjectName("tagPanel")
        tags_lay = QGridLayout(self.tags_wrap)
        tags_lay.setContentsMargins(10, 10, 10, 10)
        tags_lay.setHorizontalSpacing(8)
        tags_lay.setVerticalSpacing(8)
        if not self.available_tags:
            message = "Atanabilecek etiket bulunmuyor." if self.all_tags else "Aktif etiket yok. Önce Etiket Yönetimi ekranından etiket oluşturun."
            warn = QLabel(message)
            warn.setObjectName("warning")
            warn.setWordWrap(True)
            tags_lay.addWidget(warn, 0, 0, 1, 3)
        else:
            for i, t in enumerate(self.available_tags):
                b = QPushButton(f"● {t.name}")
                b.setCheckable(True)
                b.setObjectName("tagChipBtn")
                b.setStyleSheet(tag_chip_style(t.color, selected=False))
                b.clicked.connect(lambda checked, tag=t, btn=b: self.toggle_tag(tag, btn, checked))
                tags_lay.addWidget(b, i // 3, i % 3)
        root.addWidget(self.tags_wrap)

        root.addWidget(form_label("Sözleşmeye Özel Not (Opsiyonel)"))
        self.note = QTextEdit()
        self.note.setPlaceholderText("Bu atama için özel bir not ekleyin...")
        self.note.setMinimumHeight(72)
        root.addWidget(self.note)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Ekle")
        self.save_btn.setEnabled(bool(self.available_tags))
        self.save_btn.clicked.connect(self.save)
        row.addWidget(cancel)
        row.addWidget(self.save_btn)
        root.addLayout(row)

    def toggle_tag(self, tag: TagDef, btn: QPushButton, checked: bool):
        key = self.store._normalize_label(tag.name)
        if checked:
            self.selected[key] = tag
        else:
            self.selected.pop(key, None)
        btn.setStyleSheet(tag_chip_style(tag.color, selected=bool(checked)))

    def save(self):
        if not self.available_tags:
            QMessageBox.information(self, "Seçim", "Atanabilecek etiket bulunmuyor.")
            return
        if not self.selected:
            QMessageBox.warning(self, "Seçim", "En az bir etiket seçin.")
            return
        note = self.note.toPlainText().strip()
        out: List[dict] = []
        for tag in self.selected.values():
            out.append({
                "name": str(tag.name or "").strip(),
                "color": str(tag.color or "#3B82F6"),
                "note": note or str(tag.note or "").strip(),
            })
        self.result = out
        self.accept()


class TagManagerDialog(StyledDialog):
    def __init__(self, store: ExcelStore, contract_index: Optional[List[dict]] = None, parent=None):
        super().__init__("Etiket Yönetimi", parent)
        self.store = store
        self.contract_index = list(contract_index or [])
        self.changed = False
        self.tags: List[TagDef] = []
        self.usage: Dict[str, int] = {}
        self.assignments_by_key: Dict[str, List[dict]] = {}
        self._contract_map: Dict[Tuple[str, str, str], dict] = {}
        self.selected_tag_key: Optional[str] = None
        self.selected_color = "#3B82F6"
        self._color_buttons: List[QPushButton] = []
        self._draft_tags: Dict[str, TagDef] = {}
        self._draft_order: List[str] = []
        self._draft_seq = 1
        self.resize(1240, 700)
        self.build()
        self._rebuild_contract_map()
        self.reload_data(keep_selection=False)

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Etiket Yönetimi")
        title.setObjectName("dialogTitle")
        top.addWidget(title, 1)
        new_btn = QPushButton("+ Yeni Etiket")
        new_btn.clicked.connect(self.new_tag)
        top.addWidget(new_btn, 0)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(310)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)
        ll.addWidget(form_label("Etiketler"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Etiket ara...")
        self.search.textChanged.connect(self.refresh_tag_list)
        ll.addWidget(self.search)
        self.tag_list = QListWidget()
        self.tag_list.setObjectName("tagList")
        self.tag_list.currentRowChanged.connect(self.on_tag_selected)
        self.tag_list.setAlternatingRowColors(False)
        ll.addWidget(self.tag_list, 1)
        body.addWidget(left, 0)

        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(10)
        body.addWidget(right, 1)

        detail_row = QHBoxLayout()
        detail_row.addWidget(section_label("ETİKET DETAYI"), 1)
        self.contract_count = QLabel("0 bağlı sözleşme")
        self.contract_count.setObjectName("ctxPill")
        detail_row.addWidget(self.contract_count, 0)
        rl.addLayout(detail_row)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        self.note_edit = QTextEdit()
        self.note_edit.setMinimumHeight(86)
        form.addWidget(form_label("Etiket Adı"), 0, 0)
        form.addWidget(self.name_edit, 1, 0)
        form.addWidget(form_label("Açıklama / Not"), 2, 0)
        form.addWidget(self.note_edit, 3, 0)

        color_box = QVBoxLayout()
        color_box.setContentsMargins(0, 0, 0, 0)
        color_box.setSpacing(6)
        color_box.addWidget(form_label("Renk Seçimi"))
        colors = ["#EF4444", "#F59E0B", "#22C55E", "#3B82F6", "#8B5CF6", "#EC4899", "#14B8A6", "#94A3B8"]
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        for c in colors:
            b = QPushButton("")
            b.setObjectName("colorDotBtn")
            b.setCheckable(True)
            b.setFixedSize(28, 28)
            b.setProperty("tag_color", c)
            b.setStyleSheet(
                "QPushButton { border-radius:14px; border:2px solid #e2e8f0; background:%s; } "
                "QPushButton:checked { border:3px solid #0f172a; }" % c
            )
            b.clicked.connect(lambda _=False, color=c: self.select_color(color))
            self._color_buttons.append(b)
            color_row.addWidget(b)
        color_row.addStretch()
        color_box.addLayout(color_row)
        self.active_check = QCheckBox("Etiket Aktif")
        self.active_check.setChecked(True)
        color_box.addWidget(self.active_check)
        form.addLayout(color_box, 0, 1, 4, 1)

        rl.addLayout(form)

        btn_row = QHBoxLayout()
        self.op_hint = QLabel("")
        self.op_hint.setObjectName("muted")
        btn_row.addWidget(self.op_hint, 1)
        btn_row.addStretch()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self.save_tag)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.reject)
        self.del_btn = QPushButton("Etiketi Sil")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self.delete_tag)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.del_btn)
        rl.addLayout(btn_row)

        rl.addWidget(section_label("Bu Etikete Bağlı Sözleşmeler"))
        self.contracts_table = QTableWidget(0, 6)
        configure_table(self.contracts_table, compact=True)
        self.contracts_table.setHorizontalHeaderLabels(["Platform", "Sözleşme No", "Kullanıcı", "Tür", "Durum", "Atama Tarihi"])
        self.contracts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rl.addWidget(self.contracts_table, 1)

    def _tag_key(self, name: str) -> str:
        return self.store._normalize_label(name)

    def _rebuild_contract_map(self):
        out: Dict[Tuple[str, str, str], dict] = {}
        for it in self.contract_index:
            key = (
                str(it.get("platform", "") or "").strip(),
                str(it.get("no", "") or "").strip(),
                str(it.get("type", "") or "").strip(),
            )
            out[key] = it
        self._contract_map = out

    def select_color(self, color: str):
        self.selected_color = str(color or "#3B82F6")
        for b in self._color_buttons:
            is_this = str(b.property("tag_color") or "").upper() == self.selected_color.upper()
            b.blockSignals(True)
            b.setChecked(is_this)
            b.blockSignals(False)

    def reload_data(self, keep_selection: bool = True):
        prev = self.selected_tag_key if keep_selection else None
        self.tags, self.assignments_by_key = self.store.load_tag_snapshot()
        self.usage = {}
        for k, vals in self.assignments_by_key.items():
            if vals:
                self.usage[k] = len(vals)
        self.refresh_tag_list()
        if prev:
            for i in range(self.tag_list.count()):
                it = self.tag_list.item(i)
                if str(it.data(Qt.UserRole) or "") == prev:
                    self.tag_list.setCurrentRow(i)
                    return
        if self.tag_list.count():
            self.tag_list.setCurrentRow(0)
        else:
            self.clear_detail_form()

    def _build_tag_row(self, color: str, name: str, count: int, active: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("tagListRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        dot = QLabel("●")
        dot.setObjectName("tagDot")
        dot.setStyleSheet(f"color:{color};")
        lay.addWidget(dot, 0)

        txt_col = QVBoxLayout()
        txt_col.setContentsMargins(0, 0, 0, 0)
        txt_col.setSpacing(1)
        name_lbl = QLabel(name)
        name_lbl.setObjectName("tagName")
        count_lbl = QLabel(f"{count} sözleşme")
        count_lbl.setObjectName("tagCount")
        txt_col.addWidget(name_lbl)
        txt_col.addWidget(count_lbl)
        lay.addLayout(txt_col, 1)

        st_lbl = QLabel("Aktif" if active else "Pasif")
        st_lbl.setObjectName("tagStateOn" if active else "tagStateOff")
        lay.addWidget(st_lbl, 0, Qt.AlignVCenter)
        return row

    def _apply_tag_row_state(self, row: Optional[QFrame], selected: bool):
        if row is None:
            return
        if selected:
            row.setStyleSheet(
                "QFrame#tagListRow { background:#dcecff; border-left:4px solid #1f5be3; border-radius:8px; }"
            )
        else:
            row.setStyleSheet(
                "QFrame#tagListRow { background:transparent; border-left:4px solid transparent; border-radius:8px; }"
            )

    def _refresh_tag_row_visuals(self):
        current = self.tag_list.currentRow()
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            roww = self.tag_list.itemWidget(item)
            self._apply_tag_row_state(roww, i == current)

    def _all_ui_tags(self) -> List[Tuple[str, TagDef, bool]]:
        out: List[Tuple[str, TagDef, bool]] = []
        for dk in self._draft_order:
            dt = self._draft_tags.get(dk)
            if dt is not None:
                out.append((dk, dt, True))
        for t in self.tags:
            out.append((self._tag_key(t.name), t, False))
        return out

    def _is_draft_key(self, key: str) -> bool:
        return str(key or "").startswith("__draft__:")

    def _make_unique_draft_name(self, base: str = "Yeni Etiket") -> str:
        used = {self._tag_key(t.name) for t in self.tags}
        used.update(self._tag_key(v.name) for v in self._draft_tags.values())
        name = base
        if self._tag_key(name) not in used:
            return name
        i = 2
        while True:
            candidate = f"{base} {i}"
            if self._tag_key(candidate) not in used:
                return candidate
            i += 1

    def refresh_tag_list(self):
        q = self._tag_key(self.search.text())
        current = self.selected_tag_key
        self.tag_list.clear()
        for key, t, _is_draft in self._all_ui_tags():
            if q and q not in self._tag_key(t.name):
                continue
            cnt = int(self.usage.get(key, 0))
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, key)
            item.setData(Qt.UserRole + 1, t.name)
            item.setSizeHint(QSize(0, 60))
            self.tag_list.addItem(item)
            roww = self._build_tag_row(t.color, t.name, cnt, bool(t.active))
            self._apply_tag_row_state(roww, key == current)
            self.tag_list.setItemWidget(item, roww)
        if current:
            for i in range(self.tag_list.count()):
                it = self.tag_list.item(i)
                if str(it.data(Qt.UserRole) or "") == current:
                    self.tag_list.setCurrentRow(i)
                    break
        if self.tag_list.count() and self.tag_list.currentRow() < 0:
            self.tag_list.setCurrentRow(0)
        if not self.tag_list.count():
            self.clear_detail_form()

    def clear_detail_form(self):
        self.selected_tag_key = None
        self.name_edit.clear()
        self.note_edit.clear()
        self.active_check.setChecked(True)
        self.select_color("#3B82F6")
        self.contract_count.setText("0 bağlı sözleşme")
        self.contracts_table.setRowCount(0)

    def on_tag_selected(self, row: int):
        if row < 0:
            self.clear_detail_form()
            return
        item = self.tag_list.item(row)
        if not item:
            self.clear_detail_form()
            return
        name = str(item.data(Qt.UserRole + 1) or "").strip()
        key = str(item.data(Qt.UserRole) or "")
        if self._is_draft_key(key):
            tag = self._draft_tags.get(key)
        else:
            tag = next((t for t in self.tags if self._tag_key(t.name) == key), None)
        if not tag:
            self.clear_detail_form()
            return
        self.selected_tag_key = key
        self.name_edit.setText(tag.name)
        self.note_edit.setPlainText(tag.note)
        self.active_check.setChecked(bool(tag.active))
        self.select_color(tag.color)
        self.refresh_assignments(tag.name if not self._is_draft_key(key) else "")
        self._refresh_tag_row_visuals()

    def refresh_assignments(self, tag_name: str):
        key = self._tag_key(tag_name)
        assigns = list(self.assignments_by_key.get(key, []))
        self.contract_count.setText(f"{len(assigns)} bağlı sözleşme")
        self.contracts_table.setUpdatesEnabled(False)
        self.contracts_table.setRowCount(len(assigns))
        for r, a in enumerate(assigns):
            key = (str(a.get("platform", "")), str(a.get("no", "")), str(a.get("type", "")))
            it = self._contract_map.get(key, {})
            vals = [
                key[0],
                key[1],
                str(it.get("user", "") or "-"),
                key[2],
                str(it.get("status", "") or "-"),
                str(a.get("assigned_at", "") or "-"),
            ]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(str(v))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.contracts_table.setItem(r, c, cell)
        self.contracts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.contracts_table.setUpdatesEnabled(True)

    def new_tag(self):
        key = f"__draft__:{self._draft_seq}"
        self._draft_seq += 1
        draft = TagDef(name=self._make_unique_draft_name(), color="#3B82F6", note="", active=True)
        self._draft_tags[key] = draft
        self._draft_order.insert(0, key)
        self.selected_tag_key = key
        self.refresh_tag_list()
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            if str(it.data(Qt.UserRole) or "") == key:
                self.tag_list.setCurrentRow(i)
                break
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def save_tag(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik", "Etiket adı boş olamaz.")
            return
        key = self._tag_key(name)
        same = next((t for t in self.tags if self._tag_key(t.name) == key), None)
        is_draft = self._is_draft_key(self.selected_tag_key or "")
        if self.selected_tag_key and (not is_draft) and same and self._tag_key(same.name) != self.selected_tag_key:
            QMessageBox.warning(self, "Çakışma", "Aynı isimde başka etiket var.")
            return
        if (not self.selected_tag_key or is_draft) and same:
            QMessageBox.warning(self, "Çakışma", "Bu etiket zaten var.")
            return

        old_name = ""
        if self.selected_tag_key and not is_draft:
            old = next((t for t in self.tags if self._tag_key(t.name) == self.selected_tag_key), None)
            old_name = str(old.name if old else "")

        tag = TagDef(
            name=name,
            color=self.selected_color,
            note=self.note_edit.toPlainText().strip(),
            active=bool(self.active_check.isChecked()),
        )
        self.op_hint.setText("Etiket kaydediliyor...")
        QApplication.processEvents()
        self.store.upsert_tag_def(tag)
        if old_name and self._tag_key(old_name) != self._tag_key(name):
            self.store.rename_tag_assignments(old_name, name, tag.color)
            self.store.delete_tag_def(old_name)
        if is_draft and self.selected_tag_key:
            self._draft_tags.pop(self.selected_tag_key, None)
            self._draft_order = [k for k in self._draft_order if k != self.selected_tag_key]
        self.changed = True
        self.reload_data(keep_selection=False)
        self.op_hint.setText("")
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            if str(it.data(Qt.UserRole) or "") == self._tag_key(name):
                self.tag_list.setCurrentRow(i)
                break

    def delete_tag(self):
        if not self.selected_tag_key:
            QMessageBox.warning(self, "Seçim", "Silmek için bir etiket seçin.")
            return
        if self._is_draft_key(self.selected_tag_key):
            self._draft_tags.pop(self.selected_tag_key, None)
            self._draft_order = [k for k in self._draft_order if k != self.selected_tag_key]
            self.refresh_tag_list()
            if self.tag_list.count():
                self.tag_list.setCurrentRow(0)
            else:
                self.clear_detail_form()
            return
        tag = next((t for t in self.tags if self._tag_key(t.name) == self.selected_tag_key), None)
        if not tag:
            return
        ans = QMessageBox.question(
            self,
            "Etiketi Sil",
            f"'{tag.name}' etiketi silinecek.\nBu etikete ait tüm atamalar da kaldırılır.\n\nDevam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        self.op_hint.setText("Etiket siliniyor...")
        QApplication.processEvents()
        self.store.delete_tag_def(tag.name)
        self.changed = True
        self.reload_data(keep_selection=False)
        self.op_hint.setText("")


class SystemDialog(StyledDialog):
    def __init__(
        self,
        store: ExcelStore,
        platform: str,
        default_name: str = "Sistem 1",
        parent=None,
        existing_system: Optional[SystemInfo] = None,
        edit_mode: bool = False,
        pre_selected: Optional[List[str]] = None,
        default_t0_date: str = "",
        events_provider: Optional[Callable[[], List[dict]]] = None,
    ):
        super().__init__("Sistemi Düzenle" if edit_mode else "Sistem Ekle", parent)
        self.store = store
        self.platform = platform
        self.default_name = default_name
        self.existing_system = existing_system
        self.edit_mode = edit_mode
        self.default_t0_date = str(default_t0_date or "")
        self.external_events_provider = events_provider
        # pre_selected: edit modunda hangi bilesenlerin secili gosterilecegi
        self.pre_selected: Optional[set] = set(pre_selected) if pre_selected is not None else None
        initial_keys = pre_selected if pre_selected is not None else (getattr(existing_system, "components", {}) or {}).keys()
        self.initial_component_keys = set(initial_keys or [])
        self.result: Optional[SystemInfo] = None
        try:
            self.system_types = list(self.store.list_system_type_names(self.platform))
        except Exception:
            self.system_types = []
        self.resize(560, 720)
        self.inputs: Dict[str, QCheckBox] = {}
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 10, 22, 16)
        root.setSpacing(10)

        root.addWidget(form_label("Sistem Adı"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Örn: Sistem 1")
        self.name.setText(self.default_name)
        self.name.selectAll()
        root.addWidget(self.name)

        date_card = QFrame()
        date_card.setObjectName("systemFormCard")
        date_lay = QGridLayout(date_card)
        date_lay.setContentsMargins(10, 8, 10, 8)
        date_lay.setHorizontalSpacing(8)
        date_lay.setVerticalSpacing(6)
        self.t0_date, self.t0_date_wrap = build_date_input(self, events_provider=self.date_picker_events)

        # Yeni sistem eklerken ilgili sözleşme/SD T0 tarihi default gelsin.
        # Düzenleme modunda sistemde kayıtlı T0 varsa korunur; yoksa yine ilgili
        # sözleşme/SD T0 tarihi önerilir ve kullanıcı değiştirebilir.
        initial_t0_date = str(getattr(self.existing_system, "t0_date", "") or "").strip()
        if not initial_t0_date:
            initial_t0_date = self.default_t0_date

        self.t0_date.setText(initial_t0_date)
        self.t0_months_spin = QSpinBox()
        self.t0_months_spin.setRange(0, 999)
        self.t0_months_spin.setValue(int(getattr(self.existing_system, "t0_months", 0) or 0))
        self.t0_months_spin.setSuffix(" ay")
        self.t0_months_spin.setMinimumHeight(34)
        self.completion_date = QLineEdit()
        self.completion_date.setReadOnly(True)
        self.completion_date.setPlaceholderText("T0 + T0+Ay ile otomatik")
        self.completion_date.setStyleSheet("background:#f1f5f9; color:#64748B; border:1px solid #e2e8f0;")
        date_lay.addWidget(form_label("T0 Başlangıç"), 0, 0)
        date_lay.addWidget(form_label("T0+Ay"), 0, 2)
        date_lay.addWidget(form_label("Termin Tarihi"), 0, 4)
        date_lay.addWidget(self.t0_date_wrap, 1, 0)
        plus_lbl = QLabel("+"); plus_lbl.setObjectName("muted"); plus_lbl.setAlignment(Qt.AlignCenter)
        eq_lbl = QLabel("="); eq_lbl.setObjectName("muted"); eq_lbl.setAlignment(Qt.AlignCenter)
        date_lay.addWidget(plus_lbl, 1, 1)
        date_lay.addWidget(self.t0_months_spin, 1, 2)
        date_lay.addWidget(eq_lbl, 1, 3)
        date_lay.addWidget(self.completion_date, 1, 4)
        date_lay.setColumnStretch(0, 2)
        date_lay.setColumnStretch(2, 1)
        date_lay.setColumnStretch(4, 2)
        self.t0_date.textChanged.connect(self._recalc_completion)
        self.t0_months_spin.valueChanged.connect(self._recalc_completion)
        self._recalc_completion()
        root.addWidget(date_card)

        # ── Sistem Tipi / Bileşen Paketi: sadece hızlı seçim sağlar ──
        type_card = QFrame()
        type_card.setObjectName("systemFormCard")
        type_lay = QGridLayout(type_card)
        type_lay.setContentsMargins(10, 8, 10, 8)
        type_lay.setHorizontalSpacing(8)
        type_lay.setVerticalSpacing(6)
        type_lay.setColumnStretch(0, 1)

        type_lay.addWidget(form_label("Sistem Tipi"), 0, 0)
        self.system_type_combo = QComboBox()
        self.system_type_combo.setMinimumHeight(34)
        self.system_type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.system_type_combo.addItem(t)
        type_lay.addWidget(self.system_type_combo, 1, 0)

        self.apply_type_btn = QPushButton("Tipi Uygula")
        self.apply_type_btn.setObjectName("secondary")
        self.apply_type_btn.setMinimumHeight(34)
        self.apply_type_btn.clicked.connect(self.apply_selected_system_type)
        type_lay.addWidget(self.apply_type_btn, 1, 1)
        root.addWidget(type_card)

        comp_head = QHBoxLayout()
        comp_head.addWidget(form_label("Bileşenler"), 0)
        self.selected_count_lbl = QLabel("0 seçili")
        self.selected_count_lbl.setObjectName("selectionPill")
        comp_head.addWidget(self.selected_count_lbl, 0)
        comp_head.addStretch(1)
        self.select_all_btn = QPushButton("Tümünü Seç")
        self.select_all_btn.setObjectName("secondary")
        self.select_all_btn.setMinimumHeight(32)
        self.clear_all_btn = QPushButton("Hiçbiri")
        self.clear_all_btn.setObjectName("secondary")
        self.clear_all_btn.setMinimumHeight(32)
        comp_head.addWidget(self.select_all_btn)
        comp_head.addWidget(self.clear_all_btn)
        root.addLayout(comp_head)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Bileşen ara...")
        root.addWidget(self.search_input)

        assigned = self.store.assigned_components(self.platform)
        existing_keys = list((self.existing_system.components if self.existing_system else {}).keys())
        extras = [c for c in existing_keys if c not in assigned]
        comps = assigned + extras
        if not comps:
            warn = QLabel("Bu platforma atanmış bileşen yok. Önce Bileşen Yönetimi ekranından platforma bileşen atayın.")
            warn.setObjectName("warning")
            warn.setWordWrap(True)
            root.addWidget(warn)

        self.comp_table = QTableWidget(len(comps), 2)
        self.comp_table.setObjectName("systemCompTable")
        configure_table(self.comp_table, compact=True)
        self.comp_table.setHorizontalHeaderLabels(["", "Bileşen"])
        self.comp_table.setSelectionMode(QTableWidget.NoSelection)
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.horizontalHeader().setVisible(False)
        self.comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comp_table.setColumnWidth(0, 38)
        self.comp_table.setMinimumHeight(230)

        for r, comp in enumerate(comps):
            cell_wrap = QWidget()
            cell_layout = QHBoxLayout(cell_wrap)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            if self.edit_mode and self.existing_system:
                if self.pre_selected is not None:
                    is_checked = comp in self.pre_selected
                else:
                    # Sadece qty > 0 olan bilesenleri secili goster
                    is_checked = comp in existing_keys and self.existing_system.components.get(comp, 0) > 0
            else:
                is_checked = False
            cb.setChecked(is_checked)
            cb.stateChanged.connect(lambda _state, row=r: self._sync_component_row_style(row))
            cb.stateChanged.connect(lambda _state: self.update_selected_count())
            cell_layout.addWidget(cb)
            self.comp_table.setCellWidget(r, 0, cell_wrap)

            name_item = QTableWidgetItem(comp)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.comp_table.setItem(r, 1, name_item)
            self.comp_table.setRowHeight(r, 31)
            self.inputs[comp] = cb
            self._sync_component_row_style(r)

        root.addWidget(self.comp_table, 1)
        self.update_selected_count()
        self.search_input.textChanged.connect(self.filter_components)
        self.comp_table.cellClicked.connect(self.on_component_cell_clicked)
        self.select_all_btn.clicked.connect(self.select_all_components)
        self.clear_all_btn.clicked.connect(self.clear_all_components)

        row = QHBoxLayout()
        self.save_type_btn = QPushButton("Seçimi Tip Olarak Kaydet")
        self.save_type_btn.setObjectName("secondary")
        self.save_type_btn.clicked.connect(self.save_selection_as_system_type)
        row.addWidget(self.save_type_btn)
        row.addStretch()
        save = QPushButton("Güncelle" if self.edit_mode else "Sistemi Ekle")
        save.clicked.connect(self.save)
        row.addWidget(save)
        root.addLayout(row)

    def update_selected_count(self):
        if hasattr(self, "selected_count_lbl"):
            self.selected_count_lbl.setText(f"{len(self.selected_components())} seçili")

    def _sync_component_row_style(self, row: int):
        cb = self._row_checkbox(row) if hasattr(self, "comp_table") else None
        checked = bool(cb and cb.isChecked())

        bg = QColor("#dcecff") if checked else QColor("#ffffff")
        fg = QColor("#1f5be3") if checked else QColor("#0f172a")

        cell_wrap = self.comp_table.cellWidget(row, 0)
        if cell_wrap:
            cell_wrap.setStyleSheet(f"background:{bg.name()};")

        for c in range(self.comp_table.columnCount()):
            item = self.comp_table.item(row, c)
            if item:
                item.setBackground(bg)
                item.setForeground(fg)

        name_item = self.comp_table.item(row, 1)
        if name_item:
            # Eski tik varsa temizle, ismi saf haliyle tut.
            raw = str(
                name_item.data(Qt.UserRole)
                or name_item.text().replace("✓", "").strip()
            )

            name_item.setData(Qt.UserRole, raw)
            name_item.setText(raw)
            name_item.setForeground(fg)

    def selected_components(self) -> List[str]:
        return [comp for comp, cb in self.inputs.items() if cb.isChecked()]

    def apply_selected_system_type(self):
        type_name = self.system_type_combo.currentText().strip()
        if not type_name or type_name == "Tip seçiniz...":
            QMessageBox.information(self, "Sistem Tipi", "Uygulamak için bir sistem tipi seçin.")
            return
        try:
            comps = self.store.get_system_type_components(type_name, self.platform)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Sistem tipi okunamadı:\n{exc}")
            return
        if not comps:
            QMessageBox.information(self, "Sistem Tipi", "Bu sistem tipinde kayıtlı bileşen bulunamadı.")
            return
        comp_set = set(comps)
        for comp, cb in self.inputs.items():
            cb.setChecked(comp in comp_set)

    def save_selection_as_system_type(self):
        comps = self.selected_components()
        if not comps:
            QMessageBox.warning(self, "Eksik", "Tip olarak kaydetmek için en az bir bileşen seçin.")
            return
        default_name = ""
        current = self.system_type_combo.currentText().strip()
        if current and current != "Tip seçiniz...":
            default_name = current
        type_name, ok = QInputDialog.getText(
            self,
            "Sistem Tipi Kaydet",
            "Tip adı:",
            QLineEdit.Normal,
            default_name,
        )
        if not ok:
            return
        type_name = type_name.strip()
        if not type_name:
            QMessageBox.warning(self, "Eksik", "Tip adı girin.")
            return
        try:
            saved_count = self.store.save_system_type(type_name, self.platform, comps)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Tip kaydedilemedi:\n{exc}")
            return

        # Kaydedilen tip sözleşme kaydı beklemeden hemen dropdown'a gelsin.
        current = self.system_type_combo.currentText().strip()
        self.system_type_combo.blockSignals(True)
        self.system_type_combo.clear()
        self.system_type_combo.addItem("Tip seçiniz...")
        try:
            for t in self.store.list_system_type_names(self.platform):
                self.system_type_combo.addItem(t)
        except Exception:
            if self.system_type_combo.findText(type_name) < 0:
                self.system_type_combo.addItem(type_name)
        self.system_type_combo.blockSignals(False)
        idx = self.system_type_combo.findText(type_name)
        if idx >= 0:
            self.system_type_combo.setCurrentIndex(idx)
        elif current:
            self.system_type_combo.setCurrentText(current)

        QMessageBox.information(self, "Sistem Tipi", f"'{type_name}' sistem tipi kaydedildi. ({saved_count} bileşen)")

    def _row_checkbox(self, row: int) -> Optional[QCheckBox]:
        cell = self.comp_table.cellWidget(row, 0)
        if not cell:
            return None
        cb = cell.findChild(QCheckBox)
        return cb

    def on_component_cell_clicked(self, row: int, col: int):
        if col not in (0, 1):
            return
        cb = self._row_checkbox(row)
        if cb:
            cb.setChecked(not cb.isChecked())

    def select_all_components(self):
        for r in range(self.comp_table.rowCount()):
            cb = self._row_checkbox(r)
            if cb:
                cb.setChecked(True)

    def clear_all_components(self):
        for r in range(self.comp_table.rowCount()):
            cb = self._row_checkbox(r)
            if cb:
                cb.setChecked(False)

    def filter_components(self, text: str):
        def norm(s: str) -> str:
            return str(s or "").strip().lower().replace("ı", "i").replace("İ", "i")
        q = norm(text)
        for r in range(self.comp_table.rowCount()):
            item = self.comp_table.item(r, 1)
            name = norm(item.text() if item else "")
            self.comp_table.setRowHidden(r, bool(q and q not in name))

    def _recalc_completion(self):
        d = parse_iso_date(self.t0_date.text())
        self.completion_date.setText(add_months(d, self.t0_months_spin.value()).isoformat() if d else "")

    def date_picker_events(self) -> List[dict]:
        events: List[dict] = []
        if callable(self.external_events_provider):
            try:
                events.extend(self.external_events_provider() or [])
            except Exception:
                pass
        deadline = parse_iso_date(self.completion_date.text() if hasattr(self, "completion_date") else "")
        if not deadline and hasattr(self, "t0_date") and hasattr(self, "t0_months_spin"):
            t0 = parse_iso_date(self.t0_date.text())
            if t0:
                deadline = add_months(t0, self.t0_months_spin.value())
        if deadline:
            events.append({
                "date": deadline,
                "title": self.name.text().strip() if hasattr(self, "name") and self.name.text().strip() else "Sistem",
                "lines": [f"Termin tarihi: {deadline.isoformat()}"],
                "tag": "Sistem termini",
                "color": "#2563eb",
            })
        return events

    def save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik", "Sistem adı girin.")
            return
        t0_text = self.t0_date.text().strip()
        if not t0_text:
            QMessageBox.warning(self, "Eksik", "T0 Başlangıç Tarihi girin.")
            return
        if not parse_iso_date(t0_text):
            QMessageBox.warning(self, "Tarih hatası", "T0 Başlangıç Tarihi yyyy-aa-gg formatında olmalı. Örn: 2026-05-02")
            return
        old = self.existing_system.components if (self.edit_mode and self.existing_system) else {}
        selected = set(self.selected_components())
        removed = []
        if self.edit_mode and self.existing_system:
            removed = sorted(self.initial_component_keys - selected, key=lambda x: str(x).lower())
            if removed:
                shown = "\n".join(f"• {name}" for name in removed[:12])
                if len(removed) > 12:
                    shown += f"\n• ... ve {len(removed) - 12} bileşen daha"
                answer = QMessageBox.question(
                    self,
                    "Bileşenler Silinecek",
                    "Aşağıdaki bileşenlerin onay kutusunu kaldırdınız. Güncelleme sonrası bu bileşenler "
                    "sistemden ve bu sisteme ait kabullerden silinecek; Excel'deki ilgili değer hücreleri boşaltılacak.\n\n"
                    f"{shown}\n\nOnaylıyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
        comps = {comp: old.get(comp, 0.0) for comp in self.inputs.keys() if comp in selected}
        if not comps:
            QMessageBox.warning(self, "Eksik", "En az bir bileşen seçin.")
            return
        self._recalc_completion()
        self.result = SystemInfo(
            name=name,
            components=comps,
            t0_date=iso_or_blank(t0_text),
            t0_months=self.t0_months_spin.value(),
            completion_date=self.completion_date.text().strip(),
            status=getattr(self.existing_system, "status", "Başlanmadı") or "Başlanmadı",
            acceptance_date=getattr(self.existing_system, "acceptance_date", "") or "",
        )
        self.result.removed_components = set(removed)
        self.accept()


class MultiSystemDialog(StyledDialog):
    def __init__(
        self,
        store: ExcelStore,
        platform: str,
        contract_t0_date: str = "",
        existing_names: Optional[List[str]] = None,
        parent=None,
        events_provider: Optional[Callable[[], List[dict]]] = None,
    ):
        super().__init__("Çoklu Sistem Ekle", parent)
        self.store = store
        self.platform = str(platform or "")
        self.contract_t0_date = str(contract_t0_date or "")
        self.existing_names = set(existing_names or [])
        self.external_events_provider = events_provider
        self.result: List[SystemInfo] = []
        self.drafts: List[dict] = []
        self.current_index = 0
        self._loading = False
        self.component_rows: Dict[str, QCheckBox] = {}
        self.components = list(self.store.assigned_components(self.platform))
        try:
            self.system_types = list(self.store.list_system_type_names(self.platform))
        except Exception:
            self.system_types = []
        self.resize(1120, 760)
        self.build()
        self.add_blank_system(select=True)

    def build(self):
        self.setStyleSheet(self.styleSheet() + """
        QFrame#multiShell { background:#eef3f8; border:1px solid #cbd8e8; border-radius:14px; }
        QFrame#multiLeft, QFrame#multiMiddle { background:#ffffff; border:1px solid #d8e4f0; border-radius:14px; }
        QLabel#multiTitle { background:transparent; color:#102033; font-weight:950; font-size:14px; }
        QLabel#miniPill { background:#dbeafe; color:#1f5be3; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#miniPillGreen { background:#dcfce7; color:#16a34a; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#miniPillOrange { background:#fff7ed; color:#ea580c; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#typeHint { background:transparent; color:#64748b; font-size:11px; font-weight:750; }
        QFrame#dateStrip { background:#f8fbff; border:1px solid #d8e4f0; border-radius:12px; }
        QFrame#saveTypeStrip { background:#f8fbff; border:1px dashed #93c5fd; border-radius:10px; }
        QListWidget#multiSystemList { background:transparent; border:0; outline:0; }
        QListWidget#multiSystemList::item { border:0; padding:0; margin:0; }
        QTableWidget#multiComponentTable { background:#ffffff; border:1px solid #d8e4f0; border-radius:10px; gridline-color:#edf2f7; }
        QTableWidget#multiComponentTable::item { border-bottom:1px solid #edf2f7; padding:6px 8px; }
        QLineEdit#qtyCellInput { padding:3px; border-radius:7px; font-weight:950; qproperty-alignment: AlignCenter; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(16, 12, 16, 10)
        title = QLabel("Çoklu Sistem Ekle")
        title.setObjectName("multiTitle")
        title_row.addWidget(title, 1)
        close_btn = QPushButton("×")
        close_btn.setObjectName("secondary")
        close_btn.setFixedSize(30, 28)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn, 0)
        root.addLayout(title_row)

        body = QHBoxLayout()
        body.setContentsMargins(16, 10, 16, 12)
        body.setSpacing(14)
        root.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("multiLeft")
        left.setFixedWidth(300)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(10)

        left_head = QHBoxLayout()
        systems_title = QLabel("Sistemler")
        systems_title.setObjectName("multiTitle")
        left_head.addWidget(systems_title, 1)
        add_btn = QPushButton("+ Sistem")
        add_btn.clicked.connect(lambda: self.add_blank_system(select=True))
        left_head.addWidget(add_btn, 0)
        left_lay.addLayout(left_head)

        self.system_list = QListWidget()
        self.system_list.setObjectName("multiSystemList")
        self.system_list.currentRowChanged.connect(self.select_draft)
        left_lay.addWidget(self.system_list, 1)

        duplicate_btn = QPushButton("Bu sistemi çoğalt")
        duplicate_btn.setObjectName("secondary")
        duplicate_btn.clicked.connect(self.duplicate_current)
        left_lay.addWidget(duplicate_btn)
        delete_btn = QPushButton("Seçili sistemi sil")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self.delete_current)
        left_lay.addWidget(delete_btn)
        body.addWidget(left, 0)

        middle = QFrame()
        middle.setObjectName("multiMiddle")
        mid = QVBoxLayout(middle)
        mid.setContentsMargins(12, 12, 12, 12)
        mid.setSpacing(10)
        body.addWidget(middle, 1)

        mid.addWidget(form_label("Sistem Adı"))
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self.on_name_changed)
        mid.addWidget(self.name_edit)

        date_strip = QFrame()
        date_strip.setObjectName("dateStrip")
        date_lay = QGridLayout(date_strip)
        date_lay.setContentsMargins(10, 8, 10, 8)
        date_lay.setHorizontalSpacing(8)
        date_lay.setVerticalSpacing(6)
        self.t0_date_edit, self.t0_date_wrap = build_date_input(self, events_provider=self.date_picker_events)
        self.months_spin = QSpinBox()
        self.months_spin.setRange(0, 999)
        self.months_spin.setSuffix(" ay")
        self.months_spin.setMinimumHeight(34)
        self.completion_edit = QLineEdit()
        self.completion_edit.setReadOnly(True)
        self.completion_edit.setStyleSheet("background:#eef3f8; color:#64748b; border:1px solid #d8e4f0;")
        date_lay.addWidget(form_label("T0 Başlangıç"), 0, 0)
        date_lay.addWidget(form_label("T0+Ay"), 0, 2)
        date_lay.addWidget(form_label("Termin Tarihi"), 0, 4)
        date_lay.addWidget(self.t0_date_wrap, 1, 0)
        plus = QLabel("+"); plus.setObjectName("muted"); plus.setAlignment(Qt.AlignCenter)
        eq = QLabel("="); eq.setObjectName("muted"); eq.setAlignment(Qt.AlignCenter)
        date_lay.addWidget(plus, 1, 1)
        date_lay.addWidget(self.months_spin, 1, 2)
        date_lay.addWidget(eq, 1, 3)
        date_lay.addWidget(self.completion_edit, 1, 4)
        date_lay.setColumnStretch(0, 2)
        date_lay.setColumnStretch(2, 1)
        date_lay.setColumnStretch(4, 2)
        self.t0_date_edit.textChanged.connect(self.on_t0_changed)
        self.months_spin.valueChanged.connect(self.on_months_changed)
        mid.addWidget(date_strip)

        type_row = QGridLayout()
        type_row.setHorizontalSpacing(10)
        type_row.setVerticalSpacing(6)
        type_row.addWidget(form_label("Sistem Tipi / opsiyonel"), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.type_combo.addItem(t)
        type_row.addWidget(self.type_combo, 1, 0)
        apply_btn = QPushButton("Tipi Uygula")
        apply_btn.setObjectName("secondary")
        apply_btn.clicked.connect(self.apply_selected_type)
        type_row.addWidget(apply_btn, 1, 1)
        hint = QLabel("Tip seçmek zorunlu değil. Tip seçilmezse bileşenleri aşağıdan manuel seçip adet girebilirsin.")
        hint.setObjectName("typeHint")
        type_row.addWidget(hint, 2, 0, 1, 2)
        type_row.setColumnStretch(0, 1)
        mid.addLayout(type_row)

        comp_head = QHBoxLayout()
        comp_title = QLabel("Bileşenler")
        comp_title.setObjectName("multiTitle")
        comp_head.addWidget(comp_title, 0)
        self.selected_count_lbl = QLabel("0 seçili")
        self.selected_count_lbl.setObjectName("miniPill")
        comp_head.addWidget(self.selected_count_lbl, 0)
        comp_head.addStretch()
        select_all = QPushButton("Tümünü Seç")
        select_all.setObjectName("secondary")
        select_all.clicked.connect(self.select_all_components)
        clear_all = QPushButton("Hiçbiri")
        clear_all.setObjectName("secondary")
        clear_all.clicked.connect(self.clear_components)
        comp_head.addWidget(select_all)
        comp_head.addWidget(clear_all)
        mid.addLayout(comp_head)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Bileşen ara...")
        self.search_input.textChanged.connect(self.filter_components)
        mid.addWidget(self.search_input)

        self.comp_table = QTableWidget(0, 3)
        self.comp_table.setObjectName("multiComponentTable")
        configure_table(self.comp_table, compact=True)
        self.comp_table.setHorizontalHeaderLabels(["", "Bileşen", "Adet"])
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.setSelectionMode(QTableWidget.NoSelection)
        self.comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.comp_table.setColumnWidth(0, 34)
        self.comp_table.setColumnWidth(2, 96)
        self.comp_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.comp_table.itemChanged.connect(self.on_component_table_item_changed)
        self.comp_table.setMinimumHeight(330)
        mid.addWidget(self.comp_table, 1)

        save_type = QFrame()
        save_type.setObjectName("saveTypeStrip")
        st_lay = QHBoxLayout(save_type)
        st_lay.setContentsMargins(10, 8, 10, 8)
        st_lay.setSpacing(10)
        st_hint = QLabel("Bu sistemde seçtiğin bileşen/adet kombinasyonunu daha sonra tekrar kullanmak için tip olarak kaydet.")
        st_hint.setObjectName("typeHint")
        st_hint.setWordWrap(True)
        st_lay.addWidget(st_hint, 1)
        save_type_btn = QPushButton("Bunu Tip Olarak Kaydet")
        save_type_btn.setObjectName("secondary")
        save_type_btn.clicked.connect(self.save_current_as_type)
        st_lay.addWidget(save_type_btn, 0)
        mid.addWidget(save_type)

        footer = QHBoxLayout()
        footer.setContentsMargins(16, 10, 16, 12)
        self.system_count_badge = QLabel("")
        self.system_count_badge.setObjectName("miniPill")
        self.total_qty_badge = QLabel("")
        self.total_qty_badge.setObjectName("miniPill")
        self.warning_badge = QLabel("")
        self.warning_badge.setObjectName("miniPillOrange")
        footer.addWidget(self.system_count_badge, 0)
        footer.addWidget(self.total_qty_badge, 0)
        footer.addWidget(self.warning_badge, 0)
        footer.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        self.submit_btn = QPushButton("Sistemleri Ekle")
        self.submit_btn.clicked.connect(self.accept_drafts)
        footer.addWidget(cancel)
        footer.addWidget(self.submit_btn)
        root.addLayout(footer)

    def date_picker_events(self) -> List[dict]:
        if callable(self.external_events_provider):
            try:
                return list(self.external_events_provider() or [])
            except Exception:
                return []
        return []

    def _draft_components(self, draft: dict) -> Dict[str, int]:
        return {str(k): int(v) for k, v in (draft.get("components") or {}).items() if int(v or 0) > 0}

    def make_unique_system_name(self) -> str:
        used = {normalize_sheet_name(n) for n in self.existing_names}
        used.update(normalize_sheet_name(str(d.get("name", ""))) for d in self.drafts)
        i = 1
        while True:
            name = f"Sistem {i}"
            if normalize_sheet_name(name) not in used:
                return name
            i += 1

    def make_blank_draft(self) -> dict:
        t0 = self.contract_t0_date
        months = 0
        d = parse_iso_date(t0)
        completion = add_months(d, months).isoformat() if d else ""
        return {
            "name": self.make_unique_system_name(),
            "t0_date": t0,
            "t0_months": months,
            "completion_date": completion,
            "system_type": "",
            "components": {},
        }

    def add_blank_system(self, select: bool = True):
        self.drafts.append(self.make_blank_draft())
        self.refresh_system_list(keep_row=len(self.drafts) - 1 if select else self.current_index)

    def duplicate_current(self):
        if not self.drafts:
            return
        src = copy.deepcopy(self.drafts[self.current_index])
        src["name"] = self.make_unique_system_name()
        self.drafts.append(src)
        self.refresh_system_list(keep_row=len(self.drafts) - 1)

    def delete_current(self):
        if len(self.drafts) <= 1:
            QMessageBox.information(self, "Sistem silinemez", "En az 1 sistem kalmalı.")
            return
        self.drafts.pop(self.current_index)
        self.refresh_system_list(keep_row=min(self.current_index, len(self.drafts) - 1))

    def refresh_system_list(self, keep_row: Optional[int] = None, reload_form: bool = True):
        target = self.current_index if keep_row is None else int(keep_row)
        self.system_list.blockSignals(True)
        self.system_list.clear()
        for idx, draft in enumerate(self.drafts):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 72))
            self.system_list.addItem(item)
            self.system_list.setItemWidget(item, self.build_system_card(draft, idx == target))
        if self.drafts:
            target = max(0, min(target, len(self.drafts) - 1))
            self.current_index = target
            self.system_list.setCurrentRow(target)
        self.system_list.blockSignals(False)
        if self.drafts and reload_form:
            self.load_current_draft()
        self.update_footer()

    def build_system_card(self, draft: dict, selected: bool) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background:%s; border:1px solid %s; border-radius:13px; } QLabel { background:transparent; color:%s; }"
            % ("#0b2f6b" if selected else "#ffffff", "#061f49" if selected else "#cbdff4", "#ffffff" if selected else "#0f172a")
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        top = QHBoxLayout()
        name = QLabel(str(draft.get("name") or "Sistem"))
        name.setStyleSheet("font-weight:950; font-size:13px;")
        top.addWidget(name, 1)
        count = QLabel(f"{len(self._draft_components(draft))} bileşen")
        count.setObjectName("miniPillGreen")
        top.addWidget(count, 0)
        lay.addLayout(top)
        meta = QHBoxLayout()
        meta.setSpacing(6)
        typ = str(draft.get("system_type") or "").strip() or "Özel seçim"
        typ_lbl = QLabel(typ)
        typ_lbl.setObjectName("miniPill")
        month_lbl = QLabel(f"{int(draft.get('t0_months') or 0)} ay")
        month_lbl.setObjectName("miniPillOrange")
        meta.addWidget(typ_lbl, 0)
        meta.addWidget(month_lbl, 0)
        meta.addStretch()
        lay.addLayout(meta)
        return card

    def select_draft(self, row: int):
        if self._loading or row < 0 or row >= len(self.drafts):
            return
        self.current_index = row
        self.refresh_system_list(keep_row=row)

    def current_draft(self) -> dict:
        return self.drafts[self.current_index]

    def load_current_draft(self):
        if not self.drafts:
            return
        draft = self.current_draft()
        self._loading = True
        try:
            self.name_edit.setText(str(draft.get("name") or ""))
            self.t0_date_edit.setText(str(draft.get("t0_date") or ""))
            self.months_spin.setValue(int(draft.get("t0_months") or 0))
            self.completion_edit.setText(str(draft.get("completion_date") or ""))
            typ = str(draft.get("system_type") or "")
            idx = self.type_combo.findText(typ) if typ else 0
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.refresh_component_table()
        finally:
            self._loading = False
        self.update_selected_count()

    def recalc_current_completion(self):
        draft = self.current_draft()
        d = parse_iso_date(str(draft.get("t0_date") or ""))
        months = int(draft.get("t0_months") or 0)
        draft["completion_date"] = add_months(d, months).isoformat() if d else ""
        self.completion_edit.setText(str(draft.get("completion_date") or ""))

    def on_name_changed(self, text: str):
        if self._loading:
            return
        self.current_draft()["name"] = text.strip()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_t0_changed(self, text: str):
        if self._loading:
            return
        self.current_draft()["t0_date"] = text.strip()
        self.recalc_current_completion()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_months_changed(self, value: int):
        if self._loading:
            return
        self.current_draft()["t0_months"] = int(value)
        self.recalc_current_completion()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def set_custom_type(self):
        draft = self.current_draft()
        draft["system_type"] = ""
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentIndex(0)
        self.type_combo.blockSignals(False)

    def refresh_component_table(self):
        self.component_rows.clear()
        self.comp_table.blockSignals(True)
        self.comp_table.setRowCount(len(self.components))
        draft = self.current_draft()
        components = self._draft_components(draft)
        self.comp_table.setUpdatesEnabled(False)
        for r, comp in enumerate(self.components):
            qty = int(components.get(comp, 0))
            cb_wrap = QWidget()
            cb_lay = QHBoxLayout(cb_wrap)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            cb_lay.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(qty > 0)
            cb.toggled.connect(lambda checked, c=comp: self.on_component_checked(c, checked))
            cb_lay.addWidget(cb)
            self.comp_table.setCellWidget(r, 0, cb_wrap)

            name_item = QTableWidgetItem(comp)
            name_item.setFlags(Qt.ItemIsEnabled)
            self.comp_table.setItem(r, 1, name_item)

            qty_item = QTableWidgetItem(str(qty))
            qty_item.setData(Qt.UserRole, comp)
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.comp_table.setItem(r, 2, qty_item)
            self.component_rows[comp] = cb
            self.comp_table.setRowHeight(r, 36)
            self.apply_component_row_style(r, qty > 0)
        self.comp_table.setUpdatesEnabled(True)
        self.comp_table.blockSignals(False)
        self.filter_components(self.search_input.text())

    def apply_component_row_style(self, row: int, selected: bool):
        bg = QColor("#f8fbff") if selected else QColor("#ffffff")
        fg = QColor("#1f5be3") if selected else QColor("#0f172a")
        for col in range(self.comp_table.columnCount()):
            item = self.comp_table.item(row, col)
            if item:
                item.setBackground(bg)
                item.setForeground(fg)
        for col in (0, 2):
            widget = self.comp_table.cellWidget(row, col)
            if widget:
                widget.setStyleSheet(f"background:{bg.name()};")

    def component_row_index(self, comp: str) -> int:
        try:
            return self.components.index(comp)
        except ValueError:
            return -1

    def update_component_qty(self, comp: str, qty: int, manual: bool = True):
        qty = max(0, int(qty or 0))
        draft = self.current_draft()
        if qty > 0:
            draft.setdefault("components", {})[comp] = qty
        else:
            draft.setdefault("components", {}).pop(comp, None)
        cb = self.component_rows.get(comp)
        if cb:
            cb.blockSignals(True)
            cb.setChecked(qty > 0)
            cb.blockSignals(False)
        row = self.component_row_index(comp)
        if row >= 0:
            item = self.comp_table.item(row, 2)
            if item:
                self.comp_table.blockSignals(True)
                item.setText(str(qty))
                self.comp_table.blockSignals(False)
        row = self.component_row_index(comp)
        if row >= 0:
            self.apply_component_row_style(row, qty > 0)
        if manual and not self._loading:
            self.set_custom_type()
        self.update_selected_count()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_component_checked(self, comp: str, checked: bool):
        if self._loading:
            return
        current = int(self.current_draft().setdefault("components", {}).get(comp, 0) or 0)
        self.update_component_qty(comp, 1 if checked and current <= 0 else (current if checked else 0))

    def on_component_table_item_changed(self, item: QTableWidgetItem):
        if self._loading or not item or item.column() != 2:
            return
        comp_item = self.comp_table.item(item.row(), 1)
        comp = str((comp_item.text() if comp_item else item.data(Qt.UserRole)) or "").strip()
        if not comp:
            return
        text = str(item.text() or "").strip()
        qty = int(text) if text.isdigit() else 0
        if text != str(qty):
            self.comp_table.blockSignals(True)
            item.setText(str(qty))
            self.comp_table.blockSignals(False)
        self.update_component_qty(comp, qty)

    def on_qty_changed(self, comp: str, text: str):
        if self._loading:
            return
        qty = int(text) if str(text or "").isdigit() else 0
        self.update_component_qty(comp, qty)

    def normalize_qty_input(self, comp: str):
        row = self.component_row_index(comp)
        item = self.comp_table.item(row, 2) if row >= 0 else None
        text = item.text().strip() if item else ""
        qty = int(text) if text.isdigit() else 0
        self.update_component_qty(comp, qty)

    def update_selected_count(self):
        selected = len(self._draft_components(self.current_draft())) if self.drafts else 0
        self.selected_count_lbl.setText(f"{selected} seçili")
        self.update_footer()

    def filter_components(self, text: str):
        q = normalize_sheet_name(text)
        for r, comp in enumerate(self.components):
            self.comp_table.setRowHidden(r, bool(q and q not in normalize_sheet_name(comp)))

    def select_all_components(self):
        for comp in self.components:
            if int(self.current_draft().setdefault("components", {}).get(comp, 0) or 0) <= 0:
                self.update_component_qty(comp, 1, manual=False)
        self.set_custom_type()

    def clear_components(self):
        for comp in list(self.components):
            self.update_component_qty(comp, 0, manual=False)
        self.set_custom_type()

    def apply_selected_type(self):
        type_name = self.type_combo.currentText().strip()
        if not type_name or type_name == "Tip seçiniz...":
            QMessageBox.information(self, "Sistem Tipi", "Uygulamak için bir sistem tipi seçin.")
            return
        try:
            qty_map = self.store.get_system_type_component_quantities(type_name, self.platform)
        except Exception:
            qty_map = {}
        if not qty_map:
            try:
                qty_map = {comp: 1 for comp in self.store.get_system_type_components(type_name, self.platform)}
            except Exception as exc:
                QMessageBox.warning(self, "Sistem Tipi", f"Sistem tipi okunamadı:\n{exc}")
                return
        if not qty_map:
            QMessageBox.information(self, "Sistem Tipi", "Bu sistem tipinde kayıtlı bileşen bulunamadı.")
            return
        self.current_draft()["system_type"] = type_name
        self.current_draft()["components"] = {c: int(max(as_number(v), 0)) for c, v in qty_map.items() if c in self.components and as_number(v) > 0}
        self.refresh_component_table()
        self.update_selected_count()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def save_current_as_type(self):
        components = self._draft_components(self.current_draft())
        if not components:
            QMessageBox.warning(self, "Eksik", "Tip olarak kaydetmek için en az bir bileşen adedi girin.")
            return
        type_name, ok = QInputDialog.getText(self, "Sistem Tipi Kaydet", "Tip adı:", QLineEdit.Normal, "")
        if not ok:
            return
        type_name = type_name.strip()
        if not type_name:
            QMessageBox.warning(self, "Eksik", "Tip adı boş olamaz.")
            return
        existing = {normalize_sheet_name(n) for n in self.store.list_system_type_names(self.platform)}
        if normalize_sheet_name(type_name) in existing:
            QMessageBox.warning(self, "Çakışma", "Aynı isimde bir sistem tipi zaten var.")
            return
        try:
            saved_count = self.store.save_system_type(type_name, self.platform, components)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Tip kaydedilemedi:\n{exc}")
            return
        self.system_types = list(self.store.list_system_type_names(self.platform))
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.type_combo.addItem(t)
        idx = self.type_combo.findText(type_name)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_combo.blockSignals(False)
        self.current_draft()["system_type"] = type_name
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)
        QMessageBox.information(self, "Sistem Tipi", f"'{type_name}' sistem tipi kaydedildi. ({saved_count} bileşen)")

    def warning_count(self) -> int:
        count = 0
        names = []
        existing_norm = {normalize_sheet_name(n) for n in self.existing_names}
        for draft in self.drafts:
            name_norm = normalize_sheet_name(str(draft.get("name", "")))
            if not name_norm or name_norm in existing_norm or name_norm in names:
                count += 1
            names.append(name_norm)
            if not self._draft_components(draft):
                count += 1
            if not parse_iso_date(str(draft.get("t0_date", "") or "")):
                count += 1
        return count

    def update_footer(self):
        total_qty = sum(sum(self._draft_components(d).values()) for d in self.drafts)
        self.system_count_badge.setText(f"{len(self.drafts)} sistem hazır")
        self.total_qty_badge.setText(f"{total_qty} toplam bileşen adedi")
        warnings = self.warning_count()
        self.warning_badge.setText(f"{warnings} uyarı")
        self.warning_badge.setVisible(warnings > 0)
        self.submit_btn.setText(f"{len(self.drafts)} Sistemi Ekle")

    def accept_drafts(self):
        existing_norm = {normalize_sheet_name(n) for n in self.existing_names}
        seen = set()
        out: List[SystemInfo] = []
        for draft in self.drafts:
            name = str(draft.get("name", "") or "").strip()
            norm = normalize_sheet_name(name)
            if not name:
                QMessageBox.warning(self, "Eksik", "Sistem adı boş olamaz.")
                return
            if norm in existing_norm or norm in seen:
                QMessageBox.warning(self, "Çakışma", f"'{name}' sistem adı zaten kullanılıyor.")
                return
            seen.add(norm)
            t0 = str(draft.get("t0_date", "") or "").strip()
            if not parse_iso_date(t0):
                QMessageBox.warning(self, "Tarih hatası", f"{name}: T0 Başlangıç yyyy-aa-gg formatında olmalı.")
                return
            comps = self._draft_components(draft)
            if not comps:
                QMessageBox.warning(self, "Bileşen yok", f"{name}: bileşen adedi toplamı 0 olamaz.")
                return
            months = int(draft.get("t0_months") or 0)
            completion = str(draft.get("completion_date") or "")
            if not completion:
                completion = add_months(parse_iso_date(t0), months).isoformat()
            out.append(SystemInfo(
                name=name,
                components={k: float(v) for k, v in comps.items()},
                t0_date=iso_or_blank(t0),
                t0_months=months,
                completion_date=completion,
                status="Başlanmadı",
                acceptance_date="",
            ))
        self.result = out
        self.accept()


class DeliveryDialog(StyledDialog):
    def __init__(
        self,
        system: SystemInfo,
        default_name: str = "Kabul 1",
        parent=None,
        component_keys: Optional[List[str]] = None,
        planned_assigned: Optional[Dict[str, float]] = None,
        contract_t0_date: str = "",
        events_provider: Optional[Callable[[], List[dict]]] = None,
        allow_delete: bool = False,
    ):
        super().__init__("Teslimat / Kabul Ekle", parent)
        self.system = system
        self.store = getattr(parent, "store", None)
        self.default_name = default_name
        self.component_keys = list(component_keys or list(self.system.components.keys()))
        self.planned_assigned = dict(planned_assigned or {})
        self.contract_t0_date = contract_t0_date
        self.events_provider = events_provider
        self.allow_delete = bool(allow_delete)
        self.delete_requested = False
        self.result: Optional[DeliveryInfo] = None
        self.resize(1280, 700)
        self.inputs: Dict[str, Tuple[QTableWidgetItem, QTableWidgetItem, QTableWidgetItem]] = {}
        self._updating_qty = False
        self._status_auto_filling = False
        self.build()

    def build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        left_card = QFrame()
        left_card.setObjectName("contentPanel")
        left_card.setFixedWidth(380)
        left_card.setStyleSheet("QFrame#contentPanel{background:#F8FBFF; border:1px solid #D8E2EE; border-radius:12px;}")
        left_lay = QVBoxLayout(left_card)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(8)
        alloc_title = QLabel("Bileşen Atama Durumu")
        alloc_title.setAlignment(Qt.AlignCenter)
        alloc_title.setStyleSheet("font-weight:900; font-size:14px;")
        left_lay.addWidget(alloc_title)
        alloc_hint = QLabel("Tanımlanabilir değeri 0 olan bileşenler listeden gizlenir.")
        alloc_hint.setObjectName("muted")
        alloc_hint.setWordWrap(True)
        left_lay.addWidget(alloc_hint)
        self.assignment_table = QTableWidget(0, 3)
        self.assignment_table.setObjectName("qtyTable")
        configure_table(self.assignment_table, compact=True)
        self.assignment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.assignment_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.assignment_table.setHorizontalHeaderLabels(["Bileşen", "Tanımlanmış", "Tanımlanabilir"])
        self.assignment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.assignment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.assignment_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.assignment_table.setColumnWidth(1, 120)
        self.assignment_table.setColumnWidth(2, 132)
        left_lay.addWidget(self.assignment_table, 1)
        outer.addWidget(left_card, 0)

        right = QWidget()
        root = QVBoxLayout(right)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        outer.addWidget(right, 1)

        title = QLabel(f"{self.system.name} için Kabul / Teslimat")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Örn: Kabul 1")
        self.name.setText(self.default_name)
        self.name.selectAll()
        self.status = QComboBox(); self.status.addItems(STATUS_VALUES)
        self.status.currentTextChanged.connect(self.on_status_changed)
        self.t0_date = QLineEdit(str(getattr(self.system, "t0_date", "") or self.contract_t0_date or ""))
        self.t0_months_spin = QSpinBox()
        self.t0_months_spin.setRange(0, 999)
        self.t0_months_spin.setValue(int(getattr(self.system, "t0_months", 0) or 0))
        self.completion_date_edit = QLineEdit(str(getattr(self.system, "completion_date", "") or ""))
        self.note = QLineEdit(); self.note.setPlaceholderText("Not")
        self.delivery_user_combo = QComboBox()
        self.delivery_user_combo.addItem("Seçiniz...")
        if self.store is not None:
            for user in self.store.load_users(active_only=True):
                name = str(user.get("name", "") or "").strip()
                if name:
                    self.delivery_user_combo.addItem(name)
        self.acceptance_date, self.acceptance_date_wrap = build_date_input(self, max_date=date.today(), events_provider=self.events_provider)
        grid.addWidget(form_label("Kabul Adı"), 0, 0)
        grid.addWidget(self.name, 1, 0)
        grid.addWidget(form_label("Durum"), 0, 1)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(form_label("Kabul Tarihi"), 2, 0)
        grid.addWidget(self.acceptance_date_wrap, 3, 0)
        grid.addWidget(form_label("Not"), 2, 1)
        grid.addWidget(self.note, 3, 1)
        grid.addWidget(form_label("Teslim Edilecek Kullanıcı"), 4, 0)
        grid.addWidget(self.delivery_user_combo, 5, 0)
        root.addLayout(grid)

        info_row = QHBoxLayout()
        info = QLabel("Bileşen miktarlarını aşağıdaki tabloda girin. Kalan değeri otomatik hesaplanır.")
        info.setObjectName("muted")
        info_row.addWidget(info, 1)
        self.fill_all_btn = QPushButton("Tüm Sistemi Ekle")
        self.fill_all_btn.setObjectName("secondary")
        self.fill_all_btn.setMinimumHeight(32)
        self.fill_all_btn.clicked.connect(self.fill_all_system_planned)
        info_row.addWidget(self.fill_all_btn, 0)
        self.fill_remaining_btn = QPushButton("Kalan Sistemi Ekle")
        self.fill_remaining_btn.setObjectName("secondary")
        self.fill_remaining_btn.setMinimumHeight(32)
        self.fill_remaining_btn.clicked.connect(self.fill_remaining_system_planned)
        info_row.addWidget(self.fill_remaining_btn, 0)
        root.addLayout(info_row)

        self.qty_table = QTableWidget(len(self.component_keys), 4)
        self.qty_table.setObjectName("qtyTable")
        configure_table(self.qty_table, compact=True)
        self.qty_table.setHorizontalHeaderLabels(["Bileşen", "Teslim Edilecek", "Teslim Edilen", "Kalan"])
        self.qty_table.verticalHeader().setVisible(False)
        self.qty_table.setAlternatingRowColors(False)
        self.qty_table.setShowGrid(True)
        self.qty_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.qty_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.qty_table.setColumnWidth(3, 110)
        self.qty_table.setMinimumHeight(200)
        self.qty_table.setItemDelegateForColumn(1, CompactNumberDelegate(self.qty_table))
        self.qty_table.setItemDelegateForColumn(2, CompactNumberDelegate(self.qty_table))
        self.component_search = QLineEdit()
        self.component_search.setPlaceholderText("Bileşen ara...")
        self.component_search.textChanged.connect(self.filter_qty_components)
        self._updating_qty = True
        for r, comp in enumerate(self.component_keys):
            comp_item = QTableWidgetItem(comp)
            comp_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.qty_table.setItem(r, 0, comp_item)

            planned = QTableWidgetItem("0")
            delivered = QTableWidgetItem("0")
            remaining = QTableWidgetItem("0")
            planned.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            delivered.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            remaining.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            planned.setTextAlignment(Qt.AlignCenter)
            delivered.setTextAlignment(Qt.AlignCenter)
            remaining.setTextAlignment(Qt.AlignCenter)

            self.qty_table.setItem(r, 1, planned)
            self.qty_table.setItem(r, 2, delivered)
            self.qty_table.setItem(r, 3, remaining)
            self.qty_table.setRowHeight(r, 30)
            self.inputs[comp] = (planned, delivered, remaining)
            self._update_remaining_row(r)
        self._updating_qty = False
        self.qty_table.itemChanged.connect(self.on_qty_item_changed)
        self.refresh_assignment_card()

        root.addWidget(self.component_search, 0)
        root.addWidget(self.qty_table, 1)

        row = QHBoxLayout()
        if self.allow_delete:
            delete_btn = QPushButton("Kabul Sil")
            delete_btn.setObjectName("danger")
            delete_btn.clicked.connect(self.request_delete)
            row.addWidget(delete_btn)
        row.addStretch()
        cancel = QPushButton("İptal"); cancel.setObjectName("secondary"); cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet")
        save.clicked.connect(self.save)
        row.addWidget(cancel); row.addWidget(save)
        root.addLayout(row)

    def request_delete(self):
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle("Kabul Sil")
        confirm.setText(
            "Bu kabul silinecek. Bu kabule ait teslim miktarları artık teslim edilmiş sayılmayacak. "
            "Sistem ana bileşen adetleri değişmeyecek. Devam etmek istiyor musunuz?"
        )
        delete_btn = confirm.addButton("Evet, Sil", QMessageBox.DestructiveRole)
        confirm.addButton("Vazgeç", QMessageBox.RejectRole)
        confirm.exec()
        if confirm.clickedButton() != delete_btn:
            return
        self.delete_requested = True
        self.accept()

    def _is_delivered_status(self) -> bool:
        status = self.status.currentText().strip() if hasattr(self, "status") else ""
        norm = status.lower().replace("ı", "i").replace("İ", "i")
        return norm in {"teslim edildi", "tamamlandi", "tamamlandı"}

    def on_status_changed(self, _text: str = ""):
        if self._status_auto_filling or not self._is_delivered_status():
            return
        self.fill_delivered_to_planned()

    def fill_delivered_to_planned(self):
        self._status_auto_filling = True
        self._updating_qty = True
        try:
            for r in range(self.qty_table.rowCount()):
                planned_item = self.qty_table.item(r, 1)
                delivered_item = self.qty_table.item(r, 2)
                if not planned_item or not delivered_item:
                    continue
                delivered_item.setText(fmt_num(as_number(planned_item.text())))
                self._update_remaining_row(r)
        finally:
            self._updating_qty = False
            self._status_auto_filling = False
        self.refresh_assignment_card()

    def _planned_remaining_state(self, planned: Dict[str, float], delivered: Dict[str, float]) -> Tuple[bool, List[str]]:
        active_components = [comp for comp, qty in planned.items() if max(as_number(qty), 0) > 0.0001]
        remaining = [
            comp for comp in active_components
            if max(as_number(planned.get(comp, 0)) - as_number(delivered.get(comp, 0)), 0) > 0.0001
        ]
        return bool(active_components) and not remaining, remaining

    def _recalc_completion(self):
        """T0 + T0+Ay hesaplayarak Termin Tarihi'ni gunceller."""
        t0_text = self.t0_date.text().strip()
        months = self.t0_months_spin.value()
        d = None
        try:
            from datetime import date as _date, datetime as _dt
            if t0_text:
                d = _dt.strptime(t0_text, "%Y-%m-%d").date()
        except Exception:
            pass
        if d is not None:
            result = add_months(d, months)
            self.completion_date_edit.setText(result.isoformat())
        else:
            self.completion_date_edit.setText("")

    def _current_planned_for(self, comp: str) -> float:
        items = self.inputs.get(comp)
        if not items:
            return 0.0
        return max(as_number(items[0].text()), 0)

    def assignment_rows(self) -> List[Tuple[str, float, float]]:
        rows = []
        for comp in self.component_keys:
            total = max(as_number(self.system.components.get(comp, 0)), 0)
            assigned = max(as_number(self.planned_assigned.get(comp, 0)), 0) + self._current_planned_for(comp)
            available = total - assigned
            if abs(available) > 0.0001:
                rows.append((comp, assigned, available))
        return rows

    def over_assigned_components(self) -> set[str]:
        return {comp for comp, _assigned, available in self.assignment_rows() if available < -0.0001}

    def filter_qty_components(self, text: str):
        query = normalize_sheet_name(text)
        for r in range(self.qty_table.rowCount()):
            item = self.qty_table.item(r, 0)
            name = normalize_sheet_name(item.text() if item else "")
            self.qty_table.setRowHidden(r, bool(query and query not in name))

    def refresh_qty_issue_highlights(self):
        over = self.over_assigned_components()
        issue_bg = QColor("#FEE2E2")
        issue_fg = QColor("#991B1B")
        normal_bg = QColor("#FFFFFF")
        normal_fg = QColor("#0F172A")
        for r, comp in enumerate(self.component_keys):
            has_issue = comp in over
            for c in range(self.qty_table.columnCount()):
                item = self.qty_table.item(r, c)
                if not item:
                    continue
                item.setBackground(issue_bg if has_issue else normal_bg)
                item.setForeground(issue_fg if has_issue else normal_fg)

    def refresh_assignment_card(self):
        rows = self.assignment_rows()
        self.assignment_table.setRowCount(len(rows))
        for r, (comp, assigned, available) in enumerate(rows):
            has_issue = available < -0.0001
            bg = QColor("#FEE2E2") if has_issue else QColor("#FFFFFF")
            fg = QColor("#991B1B") if has_issue else QColor("#0F172A")
            values = [comp, assigned, available]
            for c, v in enumerate(values):
                item = QTableWidgetItem(fmt_num(v) if c else str(v))
                item.setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
                item.setBackground(bg)
                item.setForeground(fg)
                self.assignment_table.setItem(r, c, item)
            self.assignment_table.setRowHeight(r, 30)
        self.refresh_qty_issue_highlights()

    def fill_all_system_planned(self):
        self._updating_qty = True
        for r, comp in enumerate(self.component_keys):
            planned_item = self.qty_table.item(r, 1)
            delivered_item = self.qty_table.item(r, 2)
            if not planned_item:
                continue
            system_qty = max(as_number(self.system.components.get(comp, 0)), 0)
            assigned_qty = max(as_number(self.planned_assigned.get(comp, 0)), 0)
            allowed_qty = max(system_qty - assigned_qty, 0)
            planned_item.setText(fmt_num(allowed_qty))
            if delivered_item and as_number(delivered_item.text()) > allowed_qty:
                delivered_item.setText(fmt_num(allowed_qty))
            self._update_remaining_row(r)
        self._updating_qty = False
        self.refresh_assignment_card()

    def fill_remaining_system_planned(self):
        self._updating_qty = True
        for r, comp in enumerate(self.component_keys):
            planned_item = self.qty_table.item(r, 1)
            delivered_item = self.qty_table.item(r, 2)
            if not planned_item:
                continue
            system_qty = max(as_number(self.system.components.get(comp, 0)), 0)
            assigned_qty = max(as_number(self.planned_assigned.get(comp, 0)), 0)
            remaining_qty = max(system_qty - assigned_qty, 0)
            planned_item.setText(fmt_num(remaining_qty))
            if delivered_item and as_number(delivered_item.text()) > remaining_qty:
                delivered_item.setText(fmt_num(remaining_qty))
            self._update_remaining_row(r)
        self._updating_qty = False
        self.refresh_assignment_card()

    def _update_remaining_row(self, row: int):
        p = self.qty_table.item(row, 1)
        d = self.qty_table.item(row, 2)
        r = self.qty_table.item(row, 3)
        if not p or not d or not r:
            return
        pv = as_number(p.text())
        dv = as_number(d.text())
        r.setText(fmt_num(max(pv - dv, 0)))

    def on_qty_item_changed(self, item: QTableWidgetItem):
        if self._updating_qty or not item:
            return
        if item.column() not in (1, 2):
            return
        self._updating_qty = True
        item.setText(fmt_num(as_number(item.text())))
        if self._is_delivered_status() and item.column() == 1:
            delivered_item = self.qty_table.item(item.row(), 2)
            if delivered_item:
                delivered_item.setText(fmt_num(as_number(item.text())))
        self._update_remaining_row(item.row())
        self._updating_qty = False
        self.refresh_assignment_card()

    def save(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Eksik", "Kabul adı girin.")
            return
        planned: Dict[str, float] = {}
        delivered: Dict[str, float] = {}
        for comp, (p, d, _r) in self.inputs.items():
            pv = as_number(p.text())
            dv = as_number(d.text())
            assigned_other = max(as_number(self.planned_assigned.get(comp, 0)), 0)
            system_qty = max(as_number(self.system.components.get(comp, 0)), 0)
            if pv + assigned_other > system_qty + 0.0001:
                QMessageBox.warning(self, "Hata", f"{comp}: tanımlanan toplam miktar sistem adedini aşamaz.")
                return
            if dv > pv:
                QMessageBox.warning(self, "Hata", f"{comp}: teslim edilen, teslim edilecekten büyük olamaz.")
                return
            planned[comp] = pv
            delivered[comp] = dv
        t0_text = str(getattr(self.system, "t0_date", "") or self.t0_date.text()).strip()
        completion = str(getattr(self.system, "completion_date", "") or self.completion_date_edit.text()).strip()
        acc_text = self.acceptance_date.text().strip()
        acc_date = parse_iso_date(acc_text) if acc_text else None
        if acc_text and not acc_date:
            QMessageBox.warning(self, "Tarih hatası", "Kabul Tarihi yyyy-aa-gg formatında olmalı. Örn: 2026-05-02")
            return
        if acc_date and acc_date > date.today():
            QMessageBox.warning(self, "Tarih hatası", "Kabul Tarihi bugünden ileri olamaz.")
            return

        all_delivered, remaining_components = self._planned_remaining_state(planned, delivered)
        if self._is_delivered_status():
            if not acc_text:
                QMessageBox.warning(self, "Kabul Tarihi Gerekli", "Durum 'Teslim Edildi' olduğunda Kabul Tarihi zorunludur.")
                return
            if remaining_components:
                QMessageBox.warning(
                    self,
                    "Teslim Edilen Eksik",
                    "Durum 'Teslim Edildi' olduğunda bu kabuldeki tüm bileşenlerin kalan değeri 0 olmalıdır.\n\n"
                    "Eksik kalan bileşenler:\n• " + "\n• ".join(remaining_components),
                )
                return
        elif all_delivered:
            QMessageBox.warning(
                self,
                "Durum Uyumsuz",
                "Bu kabulde tüm bileşenlerin kalanı 0. Kaydetmeden önce Durum alanını 'Teslim Edildi' yapın.",
            )
            return
        self.result = DeliveryInfo(
            name=self.name.text().strip(),
            status=self.status.currentText(),
            acceptance_date=iso_or_blank(acc_text),
            note=self.note.text().strip(),
            planned=planned,
            delivered=delivered,
            t0_date=iso_or_blank(t0_text),
            t0_months=int(getattr(self.system, "t0_months", self.t0_months_spin.value()) or 0),
            completion_date=completion,
            delivery_user="" if self.delivery_user_combo.currentIndex() <= 0 else self.delivery_user_combo.currentText().strip(),
        )
        self.accept()


class ContractWorkWindow(QDialog):
    def __init__(self, store: ExcelStore, ci: ContractInfo, parent=None, systems: Optional[List[SystemInfo]] = None, deliveries: Optional[Dict[str, List[DeliveryInfo]]] = None):
        super().__init__(parent)
        self.store = store
        # Yeni sozlesme mi (systems/deliveries verilmemis) yoksa mevcut mu
        self.is_new_contract = (systems is None and deliveries is None)
        self.ci = ci
        self.original_platform = str(ci.platform or "")
        self.original_contract_no = str(ci.no or "")
        self.original_contract_type = str(ci.contract_type or "")
        self.original_entry_start_row = int(getattr(ci, "entry_start_row", 0) or 0)
        self.systems: List[SystemInfo] = systems or []
        self.deliveries: Dict[str, List[DeliveryInfo]] = deliveries or {}
        self.contract_tags: List[dict] = self.store.load_contract_tags(
            self.original_platform,
            self.original_contract_no,
            self.original_contract_type,
        )
        dedup: Dict[str, dict] = {}
        for t in self.contract_tags:
            k = self.store._normalize_label(str((t or {}).get("name") or ""))
            if not k:
                continue
            dedup[k] = dict(t)
        self.contract_tags = list(dedup.values())
        self.selected_system: Optional[str] = None
        self.expanded_delivery_index: Optional[int] = None
        self._delivery_row_map: Dict[int, int] = {}
        self._updating_summary = False
        self.deleted_contract_info: Optional[dict] = None
        self._context_cache: Dict[Tuple[str, str, str], dict] = {}
        self._deleted_delivery_systems: set[str] = set()
        self._refreshing_contract_context = False
        self._contract_save_thread = None
        self._contract_save_worker = None
        self._pending_contract_save_context = None
        self._file_dialog_open: bool = False
        self._is_dirty: bool = False   # Kullanıcı henüz değişiklik yapmadı
        self.setWindowTitle(APP_TITLE)
        # QDialog varsayılan olarak ? butonu gösterir — standart pencere butonları ekle
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowSystemMenuHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.resize(1450, 860)
        self.setWindowState(Qt.WindowMaximized)  # Varsayılan tam ekran
        self.setStyleSheet(STYLE)
        self.build()
        self.build_busy_overlay()
        # Mevcut sozlesmede 'Secili Sistemi Sil' butonunu gizle
        self.delete_system_btn.setVisible(self.is_new_contract)
        self.refresh()
        # Değişiklik tespiti için başlangıç snapshot'ı al
        if not self.is_new_contract:
            self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self._initial_snapshot = self._make_data_snapshot()

    def _set_dirty(self) -> None:
        """Kullanıcı bir değişiklik yaptığında çağrılır."""
        self._is_dirty = True

    def _make_data_snapshot(self) -> str:
        """ci + systems + deliveries + tags verilerinin JSON özeti."""
        import json as _json
        ci = self.ci
        data = {
            "no":              str(ci.no or ""),
            "user":            str(ci.user or ""),
            "yi_yd":           str(ci.yi_yd or ""),
            "contract_type":   str(ci.contract_type or ""),
            "signature_date":  str(ci.signature_date or ""),
            "t0_date":         str(ci.t0_date or ""),
            "t0_months":       int(ci.t0_months or 0),
            "completion_date": str(ci.completion_date or ""),
            "status":          str(ci.status or ""),
            "note":            str(ci.note or ""),
            "acceptance_date": str(ci.acceptance_date or ""),
            "systems": sorted([
                {
                    "name":            str(s.name or ""),
                    "components":      {k: float(v) for k, v in sorted((s.components or {}).items())},
                    "component_notes": {k: str(v or "") for k, v in sorted((getattr(s, "component_notes", {}) or {}).items()) if str(v or "")},
                    "t0_date":         str(s.t0_date or ""),
                    "t0_months":       int(s.t0_months or 0),
                    "completion_date": str(s.completion_date or ""),
                    "status":          str(s.status or ""),
                    "acceptance_date": str(s.acceptance_date or ""),
                    "deliveries": sorted([
                        {
                            "name":            str(d.name or ""),
                            "status":          str(d.status or ""),
                            "acceptance_date": str(d.acceptance_date or ""),
                            "note":            str(d.note or ""),
                            "delivery_user":   str(getattr(d, "delivery_user", "") or ""),
                            "planned":  {k: float(v) for k, v in sorted((d.planned or {}).items())},
                            "delivered":{k: float(v) for k, v in sorted((d.delivered or {}).items())},
                        }
                        for d in self.deliveries.get(s.name, [])
                    ], key=lambda x: x["name"]),
                }
                for s in self.systems
            ], key=lambda x: x["name"]),
            "tags": sorted(str((t or {}).get("name", "") or "") for t in self.contract_tags),
        }
        return _json.dumps(data, sort_keys=True, ensure_ascii=False)

    def date_picker_events(self) -> List[dict]:
        return contract_date_picker_events(self.ci, self.systems)

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(6)

        header = QFrame(); header.setObjectName("contractHeader")
        header.setFixedHeight(70)
        h = QHBoxLayout(header); h.setContentsMargins(16, 8, 12, 8); h.setSpacing(0)

        self.meta_values: Dict[str, QLabel] = {}

        def meta_cell(key, label_text, value_text):
            cell = QWidget(); cell.setObjectName("metaCell")
            cl = QVBoxLayout(cell); cl.setContentsMargins(10, 0, 10, 0); cl.setSpacing(1)
            lbl = QLabel(label_text.upper()); lbl.setObjectName("metaHeaderLabel")
            val = QLabel(value_text if value_text else "-"); val.setObjectName("metaHeaderValue")
            self.meta_values[key] = val
            cl.addWidget(lbl); cl.addWidget(val)
            div = QFrame(); div.setObjectName("metaHeaderDiv")
            div.setFixedSize(1, 32)
            return cell, div

        fields = [
            ("no",       "Sözleşme No",  self.ci.no),
            ("platform", "Platform",     self.ci.platform),
            ("type",     "Tür",          self.ci.contract_type),
            ("user",     "Kullanıcı",    self.ci.user),
            ("status",   "Durum",        self.ci.status or "Başlanmadı"),
        ]
        for i, (key, lbl, val) in enumerate(fields):
            cell, div = meta_cell(key, lbl, val)
            h.addWidget(cell, 1)
            if i < len(fields) - 1:
                h.addWidget(div)
                h.addSpacing(4)

        h.addStretch()
        e = QPushButton("✎ Ana Bilgileri Düzenle"); e.setObjectName("headerEditBtn")
        e.setFixedHeight(36)
        e.clicked.connect(self.edit_contract_info)
        h.addWidget(e)
        h.addSpacing(8)
        self.delete_contract_btn = QPushButton("Sözleşmeyi Sil")
        self.delete_contract_btn.setObjectName("danger")
        self.delete_contract_btn.setFixedHeight(36)
        self.delete_contract_btn.clicked.connect(self.delete_contract)
        h.addWidget(self.delete_contract_btn)
        root.addWidget(header)

        body = QHBoxLayout(); body.setSpacing(10); root.addLayout(body, 1)

        left_block_width = 404
        left_block = QWidget()
        left_block.setFixedWidth(left_block_width)
        left_block_lay = QVBoxLayout(left_block)
        left_block_lay.setContentsMargins(0, 0, 0, 0)
        left_block_lay.setSpacing(10)

        left_row = QHBoxLayout()
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(10)

        version_bar = QFrame(); version_bar.setObjectName("contractVersionBar"); version_bar.setFixedWidth(94)
        vb = QVBoxLayout(version_bar); vb.setContentsMargins(8, 10, 8, 10); vb.setSpacing(8)
        self.sd_list = QListWidget()
        self.sd_list.setObjectName("sdList")
        self.sd_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sd_list.currentRowChanged.connect(self.on_sd_nav_changed)
        vb.addWidget(self.sd_list, 1)
        self.add_sd_btn = QPushButton("+")
        self.add_sd_btn.setToolTip("Bu ana sözleşmeye SD ekle")
        self.add_sd_btn.clicked.connect(self.add_sd_contract)
        vb.addWidget(self.add_sd_btn, 0)
        left_row.addWidget(version_bar, 0)

        self.side_meta_host = QWidget()
        self.side_meta_host.setObjectName("sideMetaHost")
        self.side_meta_host.setFixedWidth(300)
        self.side_meta_host.installEventFilter(self)
        left_content_layout = QVBoxLayout(self.side_meta_host)
        left_content_layout.setContentsMargins(0, 0, 0, 0)
        left_content_layout.setSpacing(10)
        self.build_side_meta_popover_bar(300)
        left_content_layout.addWidget(self.side_meta_bar, 0)

        self.systems_panel = QFrame(); self.systems_panel.setObjectName("sidebar")
        lv = QVBoxLayout(self.systems_panel); lv.setContentsMargins(10, 12, 10, 12); lv.setSpacing(10)
        top = QHBoxLayout(); lbl = QLabel("SİSTEMLER"); lbl.setObjectName("sideTitle"); top.addWidget(lbl); top.addStretch()
        add = QPushButton("+"); add.clicked.connect(self.add_system); add.setMinimumHeight(30); add.setMaximumWidth(34); top.addWidget(add); lv.addLayout(top)
        self.system_list = QListWidget(); self.system_list.setObjectName("systemList"); self.system_list.currentRowChanged.connect(self.select_system); lv.addWidget(self.system_list, 1)
        delsys = QPushButton("Seçili Sistemi Sil")
        delsys.setObjectName("secondary")
        delsys.clicked.connect(self.delete_system)
        delsys.setMinimumHeight(38)
        self.delete_system_btn = delsys
        lv.addWidget(delsys)
        left_content_layout.addWidget(self.systems_panel, 1)
        left_row.addWidget(self.side_meta_host, 1)
        left_block_lay.addLayout(left_row, 1)
        body.addWidget(left_block, 0)

        right = QFrame(); right.setObjectName("contentPanel"); rv = QVBoxLayout(right); rv.setContentsMargins(16, 12, 16, 12); rv.setSpacing(8); body.addWidget(right, 1)
        self.render_contract_tags()

        # ── Üst satır: SİSTEM BİLEŞENLERİ etiketi + Sistemi Düzenle butonu aynı hizada ──
        self.title = QLabel("")  # refresh_right'ta güncellenir ama görünmez
        self.title.setVisible(False)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        self.system_metric_labels: Dict[str, QLabel] = {}

        def system_metric_card(key: str, title: str) -> QFrame:
            card = QFrame()
            card.setObjectName("systemMetricCard")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 7, 12, 7)
            lay.setSpacing(2)
            t = QLabel(title.upper())
            t.setObjectName("systemMetricTitle")
            v = QLabel("-")
            v.setObjectName("systemMetricValue")
            v.setWordWrap(True)
            if key == "days":
                card.setMinimumWidth(240)
            else:
                card.setMinimumWidth(130)
            self.system_metric_labels[key] = v
            lay.addWidget(t)
            lay.addWidget(v)
            return card

        top_row.addWidget(system_metric_card("completion", "Termin Tarihi"), 0)
        top_row.addWidget(system_metric_card("days", "Kalan Gün"), 0)
        top_row.addWidget(system_metric_card("acceptance", "Kabul Tarihi"), 0)
        top_row.addWidget(system_metric_card("user", "Kullanıcı"), 0)
        top_row.addStretch(1)
        self.edit_system_btn = QPushButton("✎ Sistemi Düzenle")
        self.edit_system_btn.setObjectName("secondary")
        top_row.addWidget(self.edit_system_btn, 0)
        rv.addLayout(top_row)
        self.edit_system_btn.clicked.connect(self.edit_system)

        self.summary = QTableWidget(0, 5)
        configure_table(self.summary)
        self.summary.verticalHeader().setDefaultSectionSize(38)
        self.summary.setHorizontalHeaderLabels(["Bileşen", "Sözleşme Adedi", "Teslim Edilen", "Kalan", "Not"])
        self.configure_summary_columns()
        self.summary.itemChanged.connect(self.on_summary_changed)
        self.summary.setMinimumHeight(340)
        self.summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rv.addWidget(self.summary, 1)  # Kalan dikey alanın ana bölümü sistem bileşenlerine ayrılsın

        # ── Boşluk + TESLİMATLAR / KABULLER ──────────────────────────
        rv.addSpacing(18)
        dh = QHBoxLayout()
        dh.addWidget(section_label("TESLİMATLAR / KABULLER"))
        dh.addStretch()

        ad = QPushButton("+ Teslimat Ekle")
        ad.clicked.connect(self.add_delivery)
        dh.addWidget(ad)

        auto_btn = QPushButton("Otomatik Kabul Oluştur")
        auto_btn.clicked.connect(lambda: open_auto_accept_dialog(self))
        dh.addWidget(auto_btn)

        rv.addLayout(dh)

        self.del_table = QTableWidget(0, 0)
        configure_table(self.del_table)
        self.del_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.del_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.del_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.del_table.setMinimumHeight(118)
        self.del_table.setMaximumHeight(180)
        self.del_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.del_table.cellClicked.connect(self.on_delivery_clicked)
        self.del_table.horizontalHeader().setVisible(True)
        self.pinned_delivery = QTableWidget(0, 0)
        self.pinned_delivery.setObjectName("pinnedDelivery")
        self.pinned_delivery.setVisible(False)
        self.pinned_delivery.setMaximumHeight(0)

        rv.addWidget(self.del_table, 0)

        foot = QHBoxLayout(); foot.addStretch()
        save = QPushButton("Kaydet"); save.clicked.connect(self.save_all)
        close = QPushButton("• Kapat"); close.setObjectName("secondary"); close.clicked.connect(self.reject)
        foot.addWidget(save); foot.addWidget(close); root.addLayout(foot)

    def build_busy_overlay(self):
        self.busy_overlay = QFrame(self)
        self.busy_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.82); }")
        self.busy_overlay.hide()
        self.busy_overlay.raise_()

        self.busy_card = QFrame(self.busy_overlay)
        self.busy_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.97); border: 1px solid #d8e2ed; border-radius: 12px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(self.busy_card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        self.busy_label = QLabel("İşlem yapılıyor...")
        self.busy_label.setObjectName("mainTitle")
        self.busy_label.setAlignment(Qt.AlignCenter)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setFormat("%p%")
        self.busy_progress.setTextVisible(True)
        lay.addWidget(self.busy_label)
        lay.addWidget(self.busy_progress)
        self.position_busy_overlay()

    def position_busy_overlay(self):
        if not hasattr(self, "busy_overlay"):
            return
        self.busy_overlay.setGeometry(self.rect())
        w, h = 420, 130
        x = max((self.busy_overlay.width() - w) // 2, 0)
        y = max((self.busy_overlay.height() - h) // 2, 0)
        self.busy_card.setGeometry(x, y, w, h)
        self.busy_overlay.raise_()

    def set_busy_overlay(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if not hasattr(self, "busy_overlay"):
            return
        if not hasattr(self, "_busy_cursor_on"):
            self._busy_cursor_on = False
        if visible:
            self.busy_label.setText(message)
            self.busy_progress.setRange(0, 100)
            self.busy_progress.setValue(int(max(0, min(100, percent))))
            self.position_busy_overlay()
            self.busy_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.busy_overlay.hide()
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()

    @staticmethod
    def _is_widget_inside(widget, parent_widget) -> bool:
        if widget is None or parent_widget is None:
            return False
        return widget is parent_widget or parent_widget.isAncestorOf(widget)

    def _side_meta_event_widget(self, obj, event):
        if isinstance(obj, QWidget):
            return obj
        global_pos = None
        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
        elif hasattr(event, "globalPos"):
            global_pos = event.globalPos()
        return QApplication.widgetAt(global_pos) if global_pos is not None else None

    def _is_side_meta_inside_click(self, obj, event) -> bool:
        widget = self._side_meta_event_widget(obj, event)
        popover = getattr(self, "side_meta_popover", None)
        bar = getattr(self, "side_meta_bar", None)
        return self._is_widget_inside(widget, popover) or self._is_widget_inside(widget, bar)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "side_meta_host", None) and event.type() in (QEvent.Resize, QEvent.Show):
            self.position_side_meta_popover()
        if (
            event.type() in (QEvent.WindowDeactivate, QEvent.ApplicationDeactivate)
            and getattr(self, "_side_meta_open_panel", None)
            and not getattr(self, "_file_dialog_open", False)
        ):
            self.close_side_meta_popover()
        if event.type() == QEvent.MouseButtonPress and getattr(self, "_side_meta_open_panel", None):
            if not self._is_side_meta_inside_click(obj, event):
                self.close_side_meta_popover()
        file_id = obj.property("contractFileId") if hasattr(obj, "property") else None
        if file_id and event.type() == QEvent.MouseButtonDblClick:
            self.open_contract_file(int(file_id))
            return True
        return super().eventFilter(obj, event)

    def configure_summary_columns(self):
        header = self.summary.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setStretchLastSection(True)
        self.summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def update_timeline_bar(self):
        """Compact timeline bar varsa güncelle; yoksa sessizce geç."""
        if hasattr(self, '_tl_prog'):
            from datetime import date as _d
            today = _d.today()
            t0 = parse_iso_date(str(self.ci.t0_date or ""))
            comp = parse_iso_date(str(self.ci.completion_date or ""))
            pct = 0
            if t0 and comp and comp > t0:
                pct = max(0, min(100, int((today - t0).days * 100 / (comp - t0).days)))
            self._tl_prog.setValue(pct)
            self._tl_name_lbl.setText(str(self.ci.no or "—"))

    def refresh_contract_header(self):
        if not hasattr(self, "meta_values"):
            return
        mapping = {
            "no": self.ci.no,
            "platform": self.ci.platform,
            "type": self.ci.contract_type,
            "user": self.ci.user,
            "status": self.ci.status or "Başlanmadı",
        }
        for k, v in mapping.items():
            lab = self.meta_values.get(k)
            if lab:
                lab.setText(str(v or "-"))

    def _notify_parent_contract_updated(self, old_platform: str, new_platform: str) -> None:
        """Ana bilgi güncellemesi sonrası ana listeyi ve açık takvimi tazeler."""
        parent = self.parent()
        if not parent:
            return
        try:
            if hasattr(parent, "request_refresh"):
                old_p = str(old_platform or "").strip()
                new_p = str(new_platform or "").strip()
                if old_p and new_p and old_p != new_p:
                    parent.request_refresh(select_platform=old_p, scope="platform", platform=old_p)
                    parent.request_refresh(select_platform=new_p, scope="platform", platform=new_p)
                else:
                    target = new_p or old_p
                    parent.request_refresh(select_platform=target, scope="platform", platform=target)
            elif hasattr(parent, "refresh_open_calendar"):
                parent.refresh_open_calendar()
        except Exception:
            pass

    def edit_contract_info(self):
        dlg = ContractEditDialog(self.store, self.ci, self)
        if not dlg.exec() or not dlg.result:
            return

        new_ci = dlg.result
        old_platform = str(self.ci.platform or "").strip()
        old_no       = str(self.ci.no or "").strip()
        old_type     = str(self.ci.contract_type or "").strip()

        # SD bağlantı bilgilerini koru
        if re.match(r"^SD-\d+$", str(new_ci.contract_type or "").strip().upper()):
            for attr in ("sd_anchor_start_row", "sd_anchor_end_row",
                         "sd_anchor_platform", "sd_anchor_no"):
                if not getattr(new_ci, attr, None):
                    setattr(new_ci, attr, getattr(self.ci, attr, None))

        new_ci.entry_start_row = self.original_entry_start_row
        self.ci = new_ci
        self._set_dirty()

        # Excel'e yaz
        try:
            self.sync_summary_to_system()
            self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
            with self.store.batch_save():
                written_start = self.store.write_contract(
                    self.ci,
                    self.systems,
                    self.deliveries,
                    old_contract_no=old_no,
                    old_start_row=self.original_entry_start_row,
                )
                # Etiket anahtarı değişmişse taşı
                new_platform = str(self.ci.platform or "").strip()
                new_no       = str(self.ci.no or "").strip()
                new_type     = str(self.ci.contract_type or "").strip()
                actor = self.store.current_actor()
                if (self.store._normalize_label(old_type) == self.store._normalize_label("Ana Sözleşme") and
                        old_platform == new_platform and old_no != new_no):
                    self.store.update_linked_sd_contract_numbers(
                        new_platform, old_no, new_no, actor=actor
                    )
                if (old_platform, old_no, old_type) != (new_platform, new_no, new_type):
                    self.store.save_contract_tags(old_platform, old_no, old_type, [], actor=actor)
                self.store.save_contract_tags(
                    new_platform, new_no, new_type, self.contract_tags, actor=actor)

            self.original_entry_start_row = int(written_start or 0)
            self.original_platform        = new_platform
            self.original_contract_no     = new_no
            self.original_contract_type   = new_type
            self.ci.entry_start_row       = self.original_entry_start_row

            self.refresh_contract_header()
            self.update_timeline_bar()
            self._initial_snapshot = self._make_data_snapshot()
            self._is_dirty = False
            self._notify_parent_contract_updated(old_platform, new_platform)
            QMessageBox.information(self, "Güncellendi", "Ana bilgiler başarıyla güncellendi.")
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Güncelleme sırasında hata:\n{exc}")

    def _start_contract_save_worker(self, worker: ContractSaveWorker, message: str):
        if self._contract_save_thread and self._contract_save_thread.isRunning():
            return False
        self.set_busy_overlay(True, message, 0)
        thread = QThread(self)
        self._contract_save_thread = thread
        self._contract_save_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_contract_save_progress)
        worker.finished.connect(self.on_contract_save_finished)
        worker.failed.connect(self.on_contract_save_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_contract_save_refs)
        parent = self.parent()
        if parent and hasattr(parent, "on_contract_save_progress"):
            worker.progress.connect(parent.on_contract_save_progress)
        thread.start()
        return True

    def _clear_contract_save_refs(self):
        self._contract_save_thread = None
        self._contract_save_worker = None

    def on_contract_save_progress(self, percent: int, message: str):
        self.set_busy_overlay(True, message, percent)

    def on_contract_save_finished(self, payload: dict):
        self.set_busy_overlay(False)
        parent = self.parent()
        if parent and hasattr(parent, "set_busy_overlay"):
            parent.set_busy_overlay(False)
        action = str((payload or {}).get("action") or "")
        try:
            self.store.reload_from_disk()
            if action == "delete":
                info = dict((payload or {}).get("result") or {})
                if not info:
                    QMessageBox.warning(self, "Hata", "Sözleşme Excel'de bulunamadı veya silinemedi.")
                    return
                self.deleted_contract_info = info
                QMessageBox.information(self, "Silindi", "Sözleşme Excel'den silindi.")
                self.accept()
                return

            ctx = self._pending_contract_save_context or {}
            old_key = ctx.get("old_key") or ("", "", "")
            new_key = ctx.get("new_key") or ("", "", "")
            actor = ctx.get("actor") or self.store.current_actor()
            with self.store.batch_save():
                if old_key != new_key and all(old_key):
                    self.store.save_contract_tags(old_key[0], old_key[1], old_key[2], [], actor=actor)
                self.store.save_contract_tags(new_key[0], new_key[1], new_key[2], ctx.get("tags") or [], actor=actor)
            written_start = int((payload or {}).get("start_row") or 0)
            self.original_entry_start_row = written_start
            self.original_platform = new_key[0]
            self.ci.entry_start_row = self.original_entry_start_row
            self.original_contract_no = new_key[1]
            self.original_contract_type = new_key[2]
            self.refresh_sd_sidebar()
            QMessageBox.information(self, "Kaydedildi", "Sözleşme Excel'e yazıldı.")
            self._is_dirty = False
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"İşlem tamamlandıktan sonra arayüz güncellenirken hata:\n{exc}")
        finally:
            self._pending_contract_save_context = None

    def on_contract_save_failed(self, message: str):
        self.set_busy_overlay(False)
        parent = self.parent()
        if parent and hasattr(parent, "set_busy_overlay"):
            parent.set_busy_overlay(False)
        self._pending_contract_save_context = None
        QMessageBox.critical(self, "Hata", f"Excel işlemi sırasında hata:\n{message}")

    def delete_contract(self):
        no = str(self.ci.no or "").strip()
        platform = str(self.ci.platform or "").strip()
        if not no or not platform:
            QMessageBox.warning(self, "Eksik", "Silinecek sözleşme bilgisi bulunamadı.")
            return
        msg = (
            f"{platform} platformundaki '{no}' sözleşmesi silinecek.\n\n"
            "Bu işlem tüm sistemler ve kabuller ile birlikte Excel'den kalıcı olarak kaldırır.\n"
            "Devam etmek istiyor musunuz?"
        )
        ans = QMessageBox.question(
            self,
            "Sözleşmeyi Sil",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        worker = ContractSaveWorker(
            self.store.path,
            "delete",
            platform,
            no,
            start_row=self.original_entry_start_row if self.original_entry_start_row > 0 else 0,
            actor=self.store.current_actor(),
            store=self.store,
        )
        self._start_contract_save_worker(worker, "Sözleşme siliniyor...")

    def _tag_key(self, name: str) -> str:
        return self.store._normalize_label(name)

    def build_side_meta_popover_bar(self, parent_width: int):
        """Build the compact meta bar and its layout-independent floating popover."""
        self._side_meta_open_panel = None
        self._side_meta_last_panel = "files"
        self._side_meta_files: List[dict] = []
        self.side_meta_bar = QFrame()
        self.side_meta_bar.setObjectName("sideMetaBar")
        self.side_meta_bar.setFixedHeight(40)
        self.side_meta_bar.setStyleSheet(
            "QFrame#sideMetaBar{"
            "  background:#ffffff;"
            "  border:1px solid #d0dcea;"
            "  border-radius:10px;"
            "}"
            "QPushButton#sideMetaPill{"
            "  background:transparent;"
            "  border:0;"
            "  border-radius:8px;"
            "  padding:4px 8px;"
            "  color:#334e6b;"
            "  font-size:12px;"
            "  font-weight:700;"
            "  text-align:left;"
            "}"
            "QPushButton#sideMetaPill:hover{"
            "  background:#f0f5fc;"
            "}"
            "QPushButton#sideMetaPill:checked{"
            "  background:#eef4ff;"
            "  color:#1d4ed8;"
            "}"
            "QLabel#sideMetaBadge{"
            "  background:#dbeafe;"
            "  color:#1d4ed8;"
            "  border:0;"
            "  border-radius:9px;"
            "  padding:1px 7px;"
            "  font-size:11px;"
            "  font-weight:800;"
            "}"
            "QFrame#sideMetaDivider{"
            "  background:#d0dcea;"
            "  min-width:1px;"
            "  max-width:1px;"
            "}"
            "QPushButton#sideMetaChevron{"
            "  background:transparent;"
            "  border:0;"
            "  border-radius:7px;"
            "  color:#5b7fa6;"
            "  font-weight:900;"
            "  font-size:13px;"
            "}"
            "QPushButton#sideMetaChevron:hover{"
            "  background:#f0f5fc;"
            "  color:#1d4ed8;"
            "}"
        )
        bar_layout = QHBoxLayout(self.side_meta_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(0)

        # Tags pill: icon + label inline, then badge outside
        self.side_btn_tags = QPushButton("🏷  Etiketler")
        self.side_btn_files = QPushButton("📎  Belgeler")
        for panel, button in (("tags", self.side_btn_tags), ("files", self.side_btn_files)):
            button.setObjectName("sideMetaPill")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, name=panel: self.toggle_side_meta_popover(name))
            bar_layout.addWidget(button, 0)
            badge = QLabel("0")
            badge.setObjectName("sideMetaBadge")
            badge.setAlignment(Qt.AlignCenter)
            badge.setMinimumWidth(22)
            bar_layout.addWidget(badge, 0)
            if panel == "tags":
                self.side_badge_tags = badge
                # divider between tags and files
                div = QFrame(); div.setObjectName("sideMetaDivider"); div.setFixedHeight(20)
                bar_layout.addSpacing(6)
                bar_layout.addWidget(div, 0)
                bar_layout.addSpacing(6)
            else:
                self.side_badge_files = badge

        bar_layout.addStretch(1)
        self.side_chevron = QPushButton("∨")
        self.side_chevron.setObjectName("sideMetaChevron")
        self.side_chevron.setFixedSize(26, 26)
        self.side_chevron.clicked.connect(self._toggle_side_meta_chevron)
        bar_layout.addWidget(self.side_chevron, 0)

        self.side_meta_popover = QFrame(self.side_meta_host)
        self.side_meta_popover.setObjectName("sideMetaPopover")
        self.side_meta_popover.setStyleSheet(
            "QFrame#sideMetaPopover{background:#ffffff; border:1px solid #cbd9eb; border-radius:15px;}"
            "QPushButton#sidePanelAdd{background:#2563eb; color:#ffffff; border:0; border-radius:11px; font-size:20px; font-weight:900; padding:0;}"
            "QPushButton#sidePanelAdd:hover{background:#1d4ed8;}"
            "QPushButton#fileDropZone{background:#f1f7ff; color:#1e3a5f; border:1px dashed #a8bdd6; border-radius:11px; padding:7px 10px; text-align:left; font-size:11px; font-weight:700;}"
            "QPushButton#fileDropZone:hover{background:#e8f2ff; border-color:#7ca4d8;}"
            "QLabel#sidePanelEmpty{background:#f8fbff; color:#64748b; border:1px dashed #c7d6e8; border-radius:11px; padding:13px; font-size:12px;}"
            "QLabel#fileTotal{background:transparent; color:#64748b; border:0; font-size:11px;}"
            "QPushButton#sidePanelAddInline{background:#eef4ff; color:#1d4ed8; border:1px solid #bcd1f2; border-radius:7px; padding:2px 10px; font-size:11px; font-weight:700;}"
            "QPushButton#sidePanelAddInline:hover{background:#dbeafe;}"
        )
        shadow = QGraphicsDropShadowEffect(self.side_meta_popover)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(15, 45, 74, 55))
        self.side_meta_popover.setGraphicsEffect(shadow)
        popover_layout = QVBoxLayout(self.side_meta_popover)
        popover_layout.setContentsMargins(10, 6, 10, 8)
        popover_layout.setSpacing(6)
        self.side_meta_popover_body = QWidget()
        self.side_meta_popover_body.setStyleSheet("background:transparent;")
        self.side_meta_popover_body_layout = QVBoxLayout(self.side_meta_popover_body)
        self.side_meta_popover_body_layout.setContentsMargins(0, 0, 0, 0)
        self.side_meta_popover_body_layout.setSpacing(6)
        popover_layout.addWidget(self.side_meta_popover_body, 1)
        self.side_meta_popover.hide()
        QApplication.instance().installEventFilter(self)
        self.position_side_meta_popover()

    def position_side_meta_popover(self):
        if not hasattr(self, "side_meta_popover") or not hasattr(self, "side_meta_host"):
            return
        w = max(180, self.side_meta_host.width())
        self.side_meta_popover.setFixedWidth(w)
        self.side_meta_popover.adjustSize()
        hint_h = self.side_meta_popover.sizeHint().height()
        h = max(80, min(hint_h, 300))
        top = self.side_meta_bar.height() + 3
        self.side_meta_popover.setGeometry(0, top, w, h)
        if self.side_meta_popover.isVisible():
            self.side_meta_popover.raise_()

    def _toggle_side_meta_chevron(self):
        if self._side_meta_open_panel:
            self.close_side_meta_popover()
        else:
            self.toggle_side_meta_popover(self._side_meta_last_panel or "files")

    def toggle_side_meta_popover(self, panel: str):
        if panel not in {"tags", "files"}:
            return
        if self._side_meta_open_panel == panel and self.side_meta_popover.isVisible():
            self.close_side_meta_popover()
            return
        self._side_meta_open_panel = panel
        self._side_meta_last_panel = panel
        self.update_side_meta_badges()
        self.render_side_meta_popover_content(panel)
        self._sync_side_meta_controls()
        self.side_meta_popover.show()
        self.side_meta_popover.raise_()
        QApplication.processEvents()
        self.position_side_meta_popover()

    def close_side_meta_popover(self):
        self._side_meta_open_panel = None
        if hasattr(self, "side_meta_popover"):
            self.side_meta_popover.hide()
        self._sync_side_meta_controls()

    def _sync_side_meta_controls(self):
        panel = self._side_meta_open_panel
        for name, button in (("tags", self.side_btn_tags), ("files", self.side_btn_files)):
            button.setChecked(name == panel)
        self.side_chevron.setText("∧" if panel else "∨")

    def _load_contract_files(self) -> List[dict]:
        try:
            return list(self.store.list_contract_files(self.ci.platform, self.ci.no, self.ci.contract_type))
        except Exception:
            return []

    def _load_contract_file_folders(self) -> List[dict]:
        try:
            return list(self.store.list_contract_file_folders(self.ci.platform, self.ci.no, self.ci.contract_type))
        except Exception:
            return []

    def _set_side_meta_badge_counts(self, tag_count: int, file_count: int):
        self.side_badge_tags.setText(str(tag_count))
        self.side_badge_files.setText(str(file_count))

    def update_side_meta_badges(self):
        self._side_meta_files = self._load_contract_files()
        self._side_meta_folders = self._load_contract_file_folders()
        self._set_side_meta_badge_counts(len(self._ordered_contract_tags()), len(self._side_meta_files))

    def _clear_side_meta_popover_body(self):
        layout = self.side_meta_popover_body_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()

    def render_side_meta_popover_content(self, panel: str):
        self._clear_side_meta_popover_body()
        body = self.side_meta_popover_body_layout
        if panel == "tags":
            # + butonu scroll'dan önce değil, kart listesinin en üstünde kompakt satır
            add_row = QHBoxLayout(); add_row.setContentsMargins(0, 0, 0, 2); add_row.addStretch(1)
            add_btn = QPushButton("+ Etiket Ekle"); add_btn.setObjectName("sidePanelAddInline")
            add_btn.setFixedHeight(26); add_btn.clicked.connect(self.open_tag_assign_dialog)
            add_row.addWidget(add_btn); body.addLayout(add_row)
            scroll, cards = self._make_card_scroll(); body.addWidget(scroll, 1)
            ordered = self._ordered_contract_tags()
            if ordered:
                for tag in ordered:
                    cards.insertWidget(cards.count() - 1, self.create_tag_card(tag))
            else:
                empty = QLabel("Henüz etiket atanmadı."); empty.setObjectName("sidePanelEmpty"); empty.setAlignment(Qt.AlignCenter); cards.insertWidget(0, empty)
        else:
            drop = ContractFileDropButton("  ↑    Dosya ekle     PDF, Word, Excel, PowerPoint, görsel veya TXT", self)
            drop.setObjectName("fileDropZone")
            drop.setCursor(Qt.PointingHandCursor)
            drop.clicked.connect(self._pick_contract_files)
            drop.filesDropped.connect(self._handle_contract_files_drop)
            drop.invalidDrop.connect(lambda message: QMessageBox.warning(self, "Dosya yüklenemedi", message))
            body.addWidget(drop, 0)
            scroll, cards = self._make_card_scroll(); body.addWidget(scroll, 1)
            files = list(self._side_meta_files)
            folders = list(getattr(self, "_side_meta_folders", []))
            tree = self.create_contract_files_tree(folders, files)
            self.contract_files_tree = tree
            body.addWidget(tree, 1)
            if not files and not folders:
                empty = QLabel("Henüz belge eklenmedi.")
                empty.setObjectName("sidePanelEmpty")
                empty.setAlignment(Qt.AlignCenter)
                body.addWidget(empty, 0)
            total = QLabel(f"Toplam {self.format_file_size(sum(int(item.get('size_bytes', 0) or 0) for item in files))}")
            total.setObjectName("fileTotal"); total.setAlignment(Qt.AlignRight | Qt.AlignVCenter); body.addWidget(total, 0)

    def _make_card_scroll(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea{background:transparent; border:0;} QScrollArea > QWidget > QWidget{background:transparent;} QScrollBar:vertical{width:8px; background:transparent;} QScrollBar::handle:vertical{background:#94a3b8; border-radius:4px; min-height:22px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        host = QWidget(); host.setMinimumWidth(0); host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); host.setStyleSheet("background:transparent;")
        cards = QVBoxLayout(host); cards.setContentsMargins(0, 0, 2, 0); cards.setSpacing(6); cards.addStretch()
        scroll.setWidget(host)
        return scroll, cards

    def _ordered_contract_tags(self) -> List[dict]:
        return sorted(
            [dict(t) for t in self.contract_tags if str((t or {}).get("name") or "").strip()],
            key=lambda x: self._tag_key(str(x.get("name", ""))),
        )

    def create_tag_card(self, tag: dict) -> QFrame:
        name = str((tag or {}).get("name") or "").strip()
        color = str((tag or {}).get("color") or "#3B82F6")
        card = QFrame(); card.setObjectName("sideTagCard"); card.setMinimumWidth(0); card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); card.setFixedHeight(52)
        card.setStyleSheet("QFrame#sideTagCard{background:#f8fbff; border:1px solid #dbe7f5; border-radius:11px;} QFrame#sideTagCard:hover{background:#eef6ff; border-color:#b8cef0;} QLabel{background:transparent; border:0;} QPushButton#tagRemoveButton{background:#f1f5fb; color:#64748b; border:1.5px solid #c8d8ee; border-radius:8px; font-size:16px; font-weight:900; padding:0;} QPushButton#tagRemoveButton:hover{background:#fee2e2; color:#b91c1c; border-color:#fca5a5;}")
        row = QHBoxLayout(card); row.setContentsMargins(9, 5, 9, 5); row.setSpacing(8)
        dot = QLabel("●"); dot.setFixedWidth(10); dot.setStyleSheet(f"color:{color}; font-size:12px;")
        middle = QWidget(); middle.setMinimumWidth(0); middle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); middle.setStyleSheet("background:transparent;"); column = QVBoxLayout(middle); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(1)
        title = ElidedLabel(name); title.setMinimumWidth(0); title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); title.setToolTip(name); title.setStyleSheet("color:#10233d; font-size:12px; font-weight:900;")
        meta = QLabel("Sözleşmeye atanmış etiket"); meta.setStyleSheet("color:#64748b; font-size:10px;")
        column.addWidget(title); column.addWidget(meta)
        remove = QPushButton("×"); remove.setObjectName("tagRemoveButton"); remove.setFixedSize(29, 29); remove.setToolTip("Etiketi kaldır"); remove.clicked.connect(lambda _=False, nm=name: self.remove_contract_tag(nm))
        row.addWidget(dot); row.addWidget(middle, 1); row.addWidget(remove)
        return card


    def create_contract_files_tree(self, folders: List[dict], files: List[dict]) -> ContractFileTreeWidget:
        tree = ContractFileTreeWidget(self)
        tree.setMinimumHeight(120)
        tree.setStyleSheet(
            "QTreeWidget{background:#f8fbff; border:1px solid #dbe7f5; border-radius:11px; padding:4px; color:#10233d; font-size:12px;}"
            "QTreeWidget::item{height:24px; border-radius:5px; padding:1px;}"
            "QTreeWidget::item:selected{background:#dbeafe; color:#0f172a;}"
            "QTreeWidget::item:hover{background:#eef6ff;}"
        )
        tree.filesDropped.connect(lambda paths, folder_id: self._add_contract_files(paths, folder_id))
        tree.invalidDrop.connect(lambda message: QMessageBox.warning(self, "Dosya yüklenemedi", message))
        tree.itemDoubleClicked.connect(self.on_contract_file_tree_double_clicked)
        tree.itemChanged.connect(self.on_contract_file_tree_item_changed)
        tree.customContextMenuRequested.connect(self.show_contract_file_tree_menu)
        self._building_file_tree = True
        try:
            folder_items = {}
            children_by_parent: Dict[object, List[dict]] = {}
            for folder in folders:
                children_by_parent.setdefault(folder.get("parent_id"), []).append(folder)

            def add_folder_items(parent_item, parent_id):
                for folder in sorted(children_by_parent.get(parent_id, []), key=lambda x: str(x.get("name") or "").casefold()):
                    item = QTreeWidgetItem([str(folder.get("name") or "")])
                    item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                    item.setData(0, Qt.UserRole, "folder")
                    item.setData(0, Qt.UserRole + 1, int(folder.get("id")))
                    item.setData(0, Qt.UserRole + 2, folder.get("parent_id"))
                    item.setData(0, Qt.UserRole + 3, str(folder.get("name") or ""))
                    item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDropEnabled)
                    if parent_item is None:
                        tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    folder_items[int(folder.get("id"))] = item
                    add_folder_items(item, int(folder.get("id")))

            add_folder_items(None, None)
            for metadata in sorted(files, key=lambda x: (str(x.get("filename") or "").casefold(), int(x.get("id") or 0))):
                parent_item = folder_items.get(int(metadata.get("folder_id") or 0))
                ext = str(metadata.get("file_ext") or "").upper() or "DOSYA"
                item = QTreeWidgetItem([str(metadata.get("filename") or "")])
                item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
                item.setToolTip(0, f"{ext} · {self.format_file_size(metadata.get('size_bytes', 0))} · {self.format_file_date(metadata.get('created_at', ''))}")
                item.setData(0, Qt.UserRole, "file")
                item.setData(0, Qt.UserRole + 1, int(metadata.get("id")))
                item.setData(0, Qt.UserRole + 2, metadata.get("folder_id"))
                item.setFlags((item.flags() | Qt.ItemIsDragEnabled) & ~Qt.ItemIsEditable)
                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
            tree.expandAll()
        finally:
            self._building_file_tree = False
        return tree

    def _selected_document_folder_id(self):
        tree = getattr(self, "contract_files_tree", None)
        item = tree.currentItem() if tree else None
        if item is None:
            return None
        kind = item.data(0, Qt.UserRole)
        if kind == "folder":
            return item.data(0, Qt.UserRole + 1)
        if kind == "file":
            return item.data(0, Qt.UserRole + 2)
        return None

    def add_contract_file_folder(self):
        try:
            created = self.store.create_contract_file_folder(
                self.ci.platform, self.ci.no, self.ci.contract_type, parent_id=self._selected_document_folder_id()
            )
            self.render_contract_files()
            tree = getattr(self, "contract_files_tree", None)
            if tree:
                matches = tree.findItems(str(created.get("name") or ""), Qt.MatchRecursive | Qt.MatchExactly)
                for item in matches:
                    if item.data(0, Qt.UserRole) == "folder" and int(item.data(0, Qt.UserRole + 1)) == int(created.get("id")):
                        tree.setCurrentItem(item)
                        tree.editItem(item, 0)
                        break
        except Exception as exc:
            QMessageBox.warning(self, "Klasör eklenemedi", str(exc))

    def on_contract_file_tree_double_clicked(self, item, column):
        if item and item.data(0, Qt.UserRole) == "file":
            self.open_contract_file(int(item.data(0, Qt.UserRole + 1)))

    def on_contract_file_tree_item_changed(self, item, column):
        if getattr(self, "_building_file_tree", False) or not item or item.data(0, Qt.UserRole) != "folder":
            return
        folder_id = int(item.data(0, Qt.UserRole + 1))
        old_name = str(item.data(0, Qt.UserRole + 3) or "")
        new_name = str(item.text(0) or "").strip()
        if new_name == old_name:
            return
        try:
            renamed = self.store.rename_contract_file_folder(folder_id, new_name)
            item.setData(0, Qt.UserRole + 3, str(renamed.get("name") or new_name))
            self.render_contract_files()
        except Exception as exc:
            self._building_file_tree = True
            try:
                item.setText(0, old_name)
            finally:
                self._building_file_tree = False
            QMessageBox.warning(self, "Klasör adı değiştirilemedi", str(exc))

    def show_contract_file_tree_menu(self, pos):
        tree = getattr(self, "contract_files_tree", None)
        item = tree.itemAt(pos) if tree else None
        if not item:
            return
        kind = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        if kind == "file":
            file_id = int(item.data(0, Qt.UserRole + 1))
            menu.addAction("Aç", lambda: self.open_contract_file(file_id))
            menu.addAction("Dışa Aktar", lambda: self.export_contract_file(file_id))
            menu.addSeparator()
            menu.addAction("Sil", lambda: self.delete_contract_file(file_id))
        elif kind == "folder":
            menu.addAction("Yeniden Adlandır", lambda: tree.editItem(item, 0))
            menu.addAction("Klasör silme bu sürümde desteklenmiyor", lambda: QMessageBox.information(self, "Klasör Silme", "Klasör silme bu sürümde desteklenmiyor."))
        menu.exec(tree.viewport().mapToGlobal(pos))

    def refresh_contract_tags_panel(self):
        self.update_side_meta_badges()
        if self._side_meta_open_panel == "tags":
            self.render_side_meta_popover_content("tags")

    def render_contract_tags(self):
        self.refresh_contract_tags_panel()

    def render_contract_files(self):
        self.refresh_contract_files_panel()

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        size = float(size_bytes or 0)
        if size < 1024: return f"{int(size)} B"
        if size < 1024 * 1024: return f"{size / 1024:.0f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def format_file_date(created_at: str) -> str:
        raw = str(created_at or "").strip()
        if not raw: return "-"
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return "Bugün" if parsed.date() == date.today() else parsed.strftime("%d.%m.%Y")
        except ValueError:
            return raw[:10]

    @staticmethod
    def file_type_style(ext: str) -> Tuple[str, str]:
        extension = str(ext or "").strip().lower()
        if extension == "pdf": return "PDF", "#ef4444"
        if extension in {"doc", "docx"}: return "DOC", "#2563eb"
        if extension in {"xls", "xlsx", "xlsm"}: return "XLS", "#16a34a"
        if extension in {"ppt", "pptx"}: return "PPT", "#f97316"
        if extension in {"png", "jpg", "jpeg"}: return "IMG", "#7c3aed"
        return "TXT", "#64748b"

    def create_file_card(self, metadata: dict) -> QFrame:
        file_id = int(metadata["id"]); filename = str(metadata.get("filename") or "")
        ext = str(metadata.get("file_ext") or "").upper() or "DOSYA"
        icon_text, icon_color = self.file_type_style(ext)
        card = QFrame(); card.setObjectName("sideFileCard"); card.setMinimumWidth(0); card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); card.setFixedHeight(56); card.setProperty("contractFileId", file_id); card.installEventFilter(self)
        card.setStyleSheet("QFrame#sideFileCard{background:#f8fbff; border:1px solid #dbe7f5; border-radius:12px;} QFrame#sideFileCard:hover{background:#eef6ff; border-color:#b8cef0;} QLabel{background:transparent; border:0;} QToolButton{background:#ffffff; color:#334155; border:1px solid #d8e4f2; border-radius:8px; font-size:16px; font-weight:900;} QToolButton:hover{background:#eff6ff; border-color:#b8cef0;}")
        row = QHBoxLayout(card); row.setContentsMargins(9, 7, 9, 7); row.setSpacing(8)
        icon = QLabel(icon_text); icon.setFixedSize(36, 36); icon.setAlignment(Qt.AlignCenter); icon.setStyleSheet(f"background:{icon_color}; color:#ffffff; border-radius:11px; font-size:13px; font-weight:900;")
        middle = QWidget(); middle.setMinimumWidth(0); middle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); middle.setStyleSheet("background:transparent;"); column = QVBoxLayout(middle); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(2)
        title = ElidedLabel(filename); title.setMinimumWidth(0); title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); title.setToolTip(filename); title.setStyleSheet("color:#10233d; font-size:12px; font-weight:900;")
        meta = QLabel(f"{ext}  ·  {self.format_file_size(metadata.get('size_bytes', 0))}  ·  {self.format_file_date(metadata.get('created_at', ''))}"); meta.setMinimumWidth(0); meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); meta.setStyleSheet("color:#64748b; font-size:10px;")
        column.addWidget(title); column.addWidget(meta)
        menu_btn = QToolButton(); menu_btn.setText("⋯"); menu_btn.setFixedSize(30, 30); menu_btn.setToolTip("Menü"); menu_btn.clicked.connect(lambda _=False, fid=file_id, btn=menu_btn: self.show_contract_file_button_menu(fid, btn))
        row.addWidget(icon); row.addWidget(middle, 1); row.addWidget(menu_btn)
        return card

    def refresh_contract_files_panel(self):
        self.update_side_meta_badges()
        if self._side_meta_open_panel == "files":
            self.render_side_meta_popover_content("files")

    def _pick_contract_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sözleşmeye Dosya Ekle",
            "",
            "Documents (*.pdf *.doc *.docx *.xls *.xlsx *.xlsm *.ppt *.pptx *.txt *.png *.jpg *.jpeg);;All Files (*.*)",
        )
        if not paths:
            return
        self._add_contract_files(paths)

    def _add_contract_files(self, file_paths):
        paths = [str(path or "").strip() for path in (file_paths or []) if str(path or "").strip()]
        if not paths:
            return
        added = 0
        duplicates = 0
        failures = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                if not path.exists():
                    raise ValueError("Dosya seçilemedi veya bulunamadı.")
                if path.is_dir():
                    raise ValueError("Klasör yüklenemez, lütfen dosya seçin.")
                if not path.is_file():
                    raise ValueError("Lütfen geçerli bir dosya seçin.")
                if not os.access(path, os.R_OK):
                    raise ValueError("Dosya okunamıyor.")
                self.store.add_contract_file(self.ci.platform, self.ci.no, path, self.ci.contract_type)
                added += 1
            except Exception as exc:
                message = str(exc)
                if "zaten ekli" in message.lower():
                    duplicates += 1
                else:
                    failures.append(f"{path.name or raw_path}: {message}")
        if added:
            self.render_contract_files()
        if failures:
            QMessageBox.warning(self, "Bazı dosyalar eklenemedi", "\n".join(failures[:8]))
        if added or duplicates:
            if added and duplicates:
                QMessageBox.information(self, "Belgeler güncellendi", f"{added} dosya eklendi, {duplicates} dosya zaten ekli olduğu için atlandı.")
            elif duplicates and not failures:
                QMessageBox.information(self, "Bu belge zaten ekli", "Seçilen belge zaten ekli.")
            elif added > 1:
                QMessageBox.information(self, "Belgeler eklendi", f"{added} dosya eklendi.")

    def _handle_contract_files_drop(self, file_paths):
        self._add_contract_files(file_paths)

    def add_contract_file(self):
        self._pick_contract_files()

    def open_contract_file(self, file_id: int):
        try:
            filename, _mime, content = self.store.get_contract_file_bytes(file_id)
            suffix = Path(filename).suffix
            temp = tempfile.NamedTemporaryFile(prefix="sts_contract_", suffix=suffix, delete=False)
            try:
                temp.write(content)
            finally:
                temp.close()
            QDesktopServices.openUrl(QUrl.fromLocalFile(temp.name))
        except Exception as exc:
            QMessageBox.warning(self, "Belge açılamadı", str(exc))

    def export_contract_file(self, file_id: int):
        try:
            filename, _mime, _content = self.store.get_contract_file_bytes(file_id)
            target, _ = QFileDialog.getSaveFileName(self, "Belgeyi Dışa Aktar", filename)
            if not target:
                return
            self.store.export_contract_file(file_id, target)
            QMessageBox.information(self, "Belge dışa aktarıldı", "Belge başarıyla dışa aktarıldı.")
        except Exception as exc:
            QMessageBox.warning(self, "Belge dışa aktarılamadı", str(exc))

    def delete_contract_file(self, file_id: int):
        if QMessageBox.question(self, "Belgeyi Sil", "Belge STS dosyasından silinsin mi? Orijinal dosyaya dokunulmaz.") != QMessageBox.Yes:
            return
        try:
            self.store.delete_contract_file(file_id)
            self.render_contract_files()
        except Exception as exc:
            QMessageBox.warning(self, "Belge silinemedi", str(exc))

    def show_contract_file_button_menu(self, file_id: int, button):
        menu = QMenu(self)
        menu.addAction("Aç", lambda: self.open_contract_file(file_id))
        menu.addAction("Dışa Aktar", lambda: self.export_contract_file(file_id))
        menu.addSeparator()
        menu.addAction("Sil", lambda: self.delete_contract_file(file_id))
        menu.exec(button.mapToGlobal(QPoint(0, button.height())))

    def open_tag_assign_dialog(self):
        dlg = TagAssignDialog(self.store, self.contract_tags, self)
        if not dlg.exec() or not dlg.result:
            return
        existing_map = {self._tag_key(str(t.get("name", ""))): dict(t) for t in self.contract_tags}
        for t in dlg.result:
            key = self._tag_key(str(t.get("name", "")))
            if not key:
                continue
            existing_map[key] = {
                "name": str(t.get("name", "")).strip(),
                "color": str(t.get("color", "#3B82F6")),
                "note": str(t.get("note", "")).strip(),
            }
        self.contract_tags = list(existing_map.values())
        self._set_dirty()
        self.render_contract_tags()

    def remove_contract_tag(self, tag_name: str):
        key = self._tag_key(tag_name)
        self.contract_tags = [t for t in self.contract_tags if self._tag_key(str((t or {}).get("name", ""))) != key]
        self._set_dirty()
        self.render_contract_tags()

    def add_system(self):
        dlg = MultiSystemDialog(
            self.store,
            self.ci.platform,
            contract_t0_date=str(self.ci.t0_date or ""),
            existing_names=[s.name for s in self.systems],
            parent=self,
            events_provider=self.date_picker_events,
        )
        if dlg.exec() and dlg.result:
            first_name = ""
            for sys_info in dlg.result:
                if not first_name:
                    first_name = sys_info.name
                self.systems.append(sys_info)
                self._set_dirty()
                self.deliveries[sys_info.name] = []
            self.selected_system = first_name or self.selected_system
            self.expanded_delivery_index = None
            self.refresh()

    def edit_system(self):
        r = self.system_list.currentRow()
        if r < 0 or r >= len(self.systems):
            QMessageBox.warning(self, "Sistem yok", "Düzenlemek için bir sistem seçin.")
            return
        self.sync_summary_to_system()
        current = self.systems[r]
        old_name = current.name

        # pre_selected: gercekten kullanilan bilesenleri sec (qty>0 veya teslimatta gecen)
        pre_selected = self._component_display_keys(current)
        dlg = SystemDialog(
            self.store,
            self.ci.platform,
            default_name=current.name,
            parent=self,
            existing_system=current,
            edit_mode=True,
            pre_selected=pre_selected,
            default_t0_date=str(self.ci.t0_date or ""),
            events_provider=self.date_picker_events,
        )
        if not dlg.exec() or not dlg.result:
            return

        updated = dlg.result
        new_name = updated.name
        for i, s in enumerate(self.systems):
            if i != r and s.name.strip().lower() == new_name.strip().lower():
                QMessageBox.warning(self, "Çakışma", f"'{new_name}' adında başka bir sistem var.")
                return

        current.name = new_name
        removed_components = set(getattr(updated, "removed_components", set()) or set())
        current.components = {k: v for k, v in dict(updated.components).items() if k not in removed_components}
        current.component_notes = {k: v for k, v in (getattr(current, "component_notes", {}) or {}).items() if k in current.components}
        current.t0_date = updated.t0_date
        current.t0_months = updated.t0_months
        current.completion_date = updated.completion_date
        current.status = updated.status
        current.acceptance_date = updated.acceptance_date

        # Sistem adı değiştiyse teslimat anahtarını da taşı.
        if old_name != new_name:
            old_deliveries = self.deliveries.pop(old_name, [])
            self.deliveries[new_name] = old_deliveries

        # Bileşen seti değiştiyse teslimat satırlarını yeni sete hizala.
        # Kaldırılan bileşenler kabullerin planned/delivered sözlüklerinden tamamen çıkarılır;
        # böylece arayüzde görünmez ve Excel'e 0 yerine boş hücre olarak yazılır.
        comps = list(current.components.keys())
        comp_set = set(comps)
        self.deliveries.setdefault(new_name, [])
        for d in self.deliveries.get(new_name, []):
            d.planned = {k: max(as_number((d.planned or {}).get(k, 0)), 0) for k in comps}
            d.delivered = {k: max(as_number((d.delivered or {}).get(k, 0)), 0) for k in comps}
            for k in comps:
                if d.delivered[k] > d.planned[k]:
                    d.delivered[k] = d.planned[k]
                if d.planned[k] > current.components.get(k, 0):
                    d.planned[k] = current.components.get(k, 0)
                    d.delivered[k] = min(d.delivered[k], d.planned[k])
            for removed_key in set((d.planned or {}).keys()) - comp_set:
                d.planned.pop(removed_key, None)
            for removed_key in set((d.delivered or {}).keys()) - comp_set:
                d.delivered.pop(removed_key, None)

        self.selected_system = new_name
        self.expanded_delivery_index = None
        self.refresh()
        self.system_list.setCurrentRow(r)
        self.refresh_right()
        self._set_dirty()

    def delete_system(self):
        r = self.system_list.currentRow()
        if r >= 0:
            name = self.systems[r].name
            self.systems.pop(r)
            self._set_dirty()
            self.deliveries.pop(name, None)
            self.expanded_delivery_index = None
            self.refresh()

    def add_delivery(self):
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.add_delivery(self)

    def current_system(self) -> Optional[SystemInfo]:
        r = self.system_list.currentRow()
        if 0 <= r < len(self.systems):
            return self.systems[r]
        return None

    def select_system(self, idx):
        self.expanded_delivery_index = None

        if 0 <= idx < len(self.systems):
            self.selected_system = self.systems[idx].name

        self._populate_system_list(keep_row=idx)
        self.refresh_right()

    def _is_sd_type(self, contract_type: str) -> bool:
        return bool(re.match(r"^SD-\d+$", str(contract_type or "").strip().upper()))

    def _sd_sort_key(self, text: str):
        raw = str(text or "").strip().upper()
        m = re.match(r"^SD[-_ ]?(\d+)$", raw)
        if m:
            return (0, int(m.group(1)))
        parts = re.split(r"(\d+)", raw.lower())
        return (1, [int(p) if p.isdigit() else p for p in parts])

    def _context_key(self, ci: Optional[ContractInfo] = None) -> Tuple[str, str, str]:
        c = ci or self.ci
        return (
            str(getattr(c, "platform", "") or "").strip(),
            str(getattr(c, "no", "") or "").strip(),
            str(getattr(c, "contract_type", "") or "").strip(),
        )

    def _cache_current_context(self):
        if getattr(self, "_refreshing_contract_context", False):
            return
        key = self._context_key()
        if not all(key):
            return
        self.sync_summary_to_system()
        self._context_cache[key] = {
            "ci": copy.deepcopy(self.ci),
            "systems": copy.deepcopy(self.systems),
            "deliveries": copy.deepcopy(self.deliveries),
            "deleted_delivery_systems": set(self._deleted_delivery_systems),
            "tags": copy.deepcopy(self.contract_tags),
            "original_platform": str(self.original_platform or ""),
            "original_contract_no": str(self.original_contract_no or ""),
            "original_contract_type": str(self.original_contract_type or ""),
            "original_entry_start_row": int(self.original_entry_start_row or 0),
        }

    def _load_cached_context(self, key: Tuple[str, str, str]) -> bool:
        ctx = self._context_cache.get(key)
        if not ctx:
            return False
        self.ci = copy.deepcopy(ctx["ci"])
        self.systems = copy.deepcopy(ctx.get("systems") or [])
        self.deliveries = copy.deepcopy(ctx.get("deliveries") or {})
        self._deleted_delivery_systems = set(ctx.get("deleted_delivery_systems") or set())
        self.contract_tags = copy.deepcopy(ctx.get("tags") or [])
        self.original_platform = str(ctx.get("original_platform") or self.ci.platform or "")
        self.original_contract_no = str(ctx.get("original_contract_no") or self.ci.no or "")
        self.original_contract_type = str(ctx.get("original_contract_type") or self.ci.contract_type or "")
        self.original_entry_start_row = int(ctx.get("original_entry_start_row") or getattr(self.ci, "entry_start_row", 0) or 0)
        return True

    def _family_context_rows(self) -> List[dict]:
        platform = str(self.ci.platform or "").strip()
        no = str(self.ci.no or "").strip()
        rows = []
        try:
            rows = [
                dict(it) for it in self.store.list_main_contracts(platform)
                if str(it.get("no", "") or "").strip() == no
            ]
        except Exception:
            rows = []
        seen = {
            (str(it.get("platform", "") or "").strip(), str(it.get("no", "") or "").strip(), str(it.get("type", "") or "").strip())
            for it in rows
        }
        for key, ctx in self._context_cache.items():
            p, n, t = key
            if p != platform or n != no or key in seen:
                continue
            ci = ctx.get("ci")
            if not ci:
                continue
            rows.append({
                "platform": p,
                "no": n,
                "type": t,
                "type_display": t,
                "row": int(getattr(ci, "entry_start_row", 0) or ctx.get("original_entry_start_row") or 0),
                "is_main": not self._is_sd_type(t),
                "_cache_key": key,
            })
        return rows

    def _next_sd_code_for_family(self, platform: str, no: str) -> str:
        try:
            base_next = self.store.next_sd_code(platform, no)
            max_n = int(re.match(r"^SD-(\d+)$", base_next).group(1)) - 1
        except Exception:
            max_n = 0
        for key in self._context_cache.keys():
            p, n, t = key
            if p == platform and n == no:
                m = re.match(r"^SD-(\d+)$", str(t or "").strip().upper())
                if m:
                    max_n = max(max_n, int(m.group(1)))
        return f"SD-{max_n + 1}"

    def refresh_sd_sidebar(self):
        if not hasattr(self, "sd_list"):
            return
        if not getattr(self, "_refreshing_contract_context", False):
            self._cache_current_context()
        current_key = self._context_key()
        current_row = int(getattr(self.ci, "entry_start_row", 0) or 0)
        current_type = str(getattr(self.ci, "contract_type", "") or "").strip()
        self.sd_list.blockSignals(True)
        self.sd_list.clear()
        family = self._family_context_rows()
        main_rows = [it for it in family if bool(it.get("is_main"))]
        sd_rows = [it for it in family if not bool(it.get("is_main"))]
        sd_rows.sort(key=lambda it: self._sd_sort_key(str(it.get("type", "") or "")))

        def add_item(label: str, row_data: dict, active: bool = False):
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, dict(row_data or {}))
            self.sd_list.addItem(item)
            if active:
                self.sd_list.setCurrentItem(item)

        if main_rows:
            main = dict(main_rows[0])
            main_key = tuple(main.get("_cache_key") or (main.get("platform"), main.get("no"), main.get("type")))
            add_item("SÖZ\nANA", main, main_key == current_key or (current_row and int(main.get("row") or 0) == current_row))
        else:
            platform, no, _t = current_key
            add_item("SÖZ\nANA", {
                "platform": platform, "no": no, "row": 0, "type": "Ana Sözleşme", "is_main": True,
                "_cache_key": (platform, no, "Ana Sözleşme"),
            }, not self._is_sd_type(current_type))
        for sd in sd_rows:
            label = str(sd.get("type", "SD") or "SD")
            sd_key = tuple(sd.get("_cache_key") or (sd.get("platform"), sd.get("no"), sd.get("type")))
            add_item(label, sd, sd_key == current_key or (current_row and int(sd.get("row") or 0) == current_row))
        self.sd_list.blockSignals(False)
        self.add_sd_btn.setEnabled(bool(current_key[0] and current_key[1]))

    def on_sd_nav_changed(self, row: int):
        if getattr(self, "_refreshing_contract_context", False):
            return
        if row < 0 or not hasattr(self, "sd_list"):
            return
        item = self.sd_list.item(row)
        data = dict(item.data(Qt.UserRole) or {}) if item else {}
        key = tuple(data.get("_cache_key") or (data.get("platform"), data.get("no"), data.get("type")))
        if key == self._context_key():
            return
        self.switch_contract_context(data)

    def switch_contract_context(self, item: dict):
        self._cache_current_context()
        key = tuple(item.get("_cache_key") or (item.get("platform"), item.get("no"), item.get("type")))
        start_row = int(item.get("row") or 0)
        self._refreshing_contract_context = True
        try:
            if key in self._context_cache and self._load_cached_context(key):
                pass
            else:
                platform = str(item.get("platform") or self.ci.platform or "").strip()
                no = str(item.get("no") or self.ci.no or "").strip()
                if not platform or not no or start_row <= 0:
                    return
                self.set_busy_overlay(True, "Sözleşme detayı yükleniyor...", 25)
                try:
                    ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=start_row)
                finally:
                    self.set_busy_overlay(False)
                if not ci:
                    QMessageBox.warning(self, "Bulunamadı", "Seçilen sözleşme/SD detayı okunamadı.")
                    return
                self.ci = ci
                self.original_platform = str(ci.platform or "")
                self.original_contract_no = str(ci.no or "")
                self.original_contract_type = str(ci.contract_type or "")
                self.original_entry_start_row = int(getattr(ci, "entry_start_row", 0) or 0)
                self.systems = systems or []
                self.deliveries = deliveries or {}
                self.contract_tags = self.store.load_contract_tags(
                    self.original_platform, self.original_contract_no, self.original_contract_type
                )
            self.expanded_delivery_index = None
            self.refresh_contract_header()
            self.render_contract_tags()
            self.refresh()
        finally:
            self._refreshing_contract_context = False

    def add_sd_contract(self):
        self._cache_current_context()
        platform = str(self.ci.platform or "").strip()
        no = str(self.ci.no or "").strip()
        if not platform or not no:
            QMessageBox.warning(self, "Eksik", "SD eklemek için önce ana sözleşme bilgisi bulunmalı.")
            return
        main_info = None
        try:
            main_info = self.store.find_main_contract_info(platform, no)
        except Exception:
            main_info = None
        main_key = (platform, no, "Ana Sözleşme")
        main_ctx = self._context_cache.get(main_key)
        if not main_info and not main_ctx:
            QMessageBox.warning(self, "Ana sözleşme bulunamadı", "SD eklemek için önce ana sözleşme detayında kalıp sistem bilgilerini girin.")
            return
        sd_code = self._next_sd_code_for_family(platform, no)
        sd_key = (platform, no, sd_code)
        if sd_key in self._context_cache:
            self.switch_contract_context({"_cache_key": sd_key, "platform": platform, "no": no, "type": sd_code})
            return
        source_ci = main_ctx.get("ci") if main_ctx else self.ci
        sd_ci = ContractInfo(
            no=no,
            platform=platform,
            user=str((main_info or {}).get("user") or getattr(source_ci, "user", "") or ""),
            users=list(getattr(source_ci, "users", []) or []),
            yi_yd=str((main_info or {}).get("yi_yd") or getattr(source_ci, "yi_yd", "Yİ") or "Yİ"),
            contract_type=sd_code,
            signature_date="",
            t0_date="",
            t0_months=0,
            completion_date="",
            status="Başlanmadı",
            note="",
            entry_start_row=0,
            sd_anchor_start_row=int((main_info or {}).get("block_start") or (main_info or {}).get("row") or 0),
            sd_anchor_end_row=int((main_info or {}).get("block_end") or (main_info or {}).get("row") or 0),
            sd_anchor_platform=platform if main_info else "",
            sd_anchor_no=no if main_info else "",
        )
        dlg = ContractEditDialog(
            self.store,
            sd_ci,
            self,
            title_text="SD Ekleme Tablosu",
            save_text="SD Ekle",
            info_text="SD temel bilgilerini girin. Platform, sözleşme no ve SD kodu ana sözleşmeye bağlıdır; değiştirilemez.",
        )
        if not dlg.exec() or not dlg.result:
            return
        sd_ci = dlg.result
        self._context_cache[sd_key] = {
            "ci": sd_ci,
            "systems": [],
            "deliveries": {},
            "deleted_delivery_systems": set(),
            "tags": [],
            "original_platform": platform,
            "original_contract_no": no,
            "original_contract_type": sd_code,
            "original_entry_start_row": 0,
        }
        self.switch_contract_context({"_cache_key": sd_key, "platform": platform, "no": no, "type": sd_code})
        QMessageBox.information(self, "SD hazır", f"{sd_code} oluşturuldu. Sistem ve kabulleri ekleyip Kaydet'e basın.")

    def _default_acceptance_for(self, sys_info: SystemInfo) -> Optional[DeliveryInfo]:
        planned = {comp: max(as_number(qty), 0) for comp, qty in (sys_info.components or {}).items()}
        planned = {comp: qty for comp, qty in planned.items() if qty > 0.0001}
        if not planned:
            return None
        return DeliveryInfo(
            name="Kabul 1",
            status="Başlanmadı",
            acceptance_date="",
            note="Sistem kaydedilirken otomatik oluşturuldu.",
            planned=planned,
            delivered={comp: 0 for comp in planned.keys()},
            t0_date=str(getattr(sys_info, "t0_date", "") or ""),
            t0_months=int(getattr(sys_info, "t0_months", 0) or 0),
            completion_date=str(getattr(sys_info, "completion_date", "") or ""),
        )

    def _norm_status_text(self, status: str) -> str:
        txt = str(status or "").strip().lower()
        repl = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
        for a, b in repl.items():
            txt = txt.replace(a, b)
        return re.sub(r"\s+", " ", txt)

    def _delivery_is_delivered(self, delivery: DeliveryInfo) -> bool:
        return self._norm_status_text(getattr(delivery, "status", "")) in {"teslim edildi", "tamamlandi"}

    def _delivery_is_preparing(self, delivery: DeliveryInfo) -> bool:
        return self._norm_status_text(getattr(delivery, "status", "")) == "teslimata hazirlaniyor"

    def _derive_system_status(self, sys_info: SystemInfo, deliveries: List[DeliveryInfo]) -> str:
        if not deliveries:
            return "Başlanmadı"
        component_qty = {name: max(as_number(qty), 0) for name, qty in (sys_info.components or {}).items()}
        delivered_qty = {name: sum(max(as_number((delivery.delivered or {}).get(name, 0)), 0) for delivery in deliveries) for name in component_qty}
        active_components = [name for name, qty in component_qty.items() if qty > 0.0001]
        if active_components and all(delivered_qty.get(name, 0) >= component_qty[name] - 0.0001 for name in active_components):
            return "Teslim Edildi"
        if any(qty > 0.0001 for qty in delivered_qty.values()):
            return "Parçalı Teslimat"
        if any(self._delivery_is_preparing(d) for d in deliveries):
            return "Teslimata Hazırlanıyor"
        return "Başlanmadı"

    def _latest_acceptance_date(self, items: List[object]) -> str:
        latest = None
        for item in items:
            parsed = parse_iso_date(str(getattr(item, "acceptance_date", "") or ""))
            if parsed and (latest is None or parsed > latest):
                latest = parsed
        return latest.isoformat() if latest else ""

    def _system_acceptance_date(self, sys_info: SystemInfo, sys_deliveries: List[DeliveryInfo]) -> str:
        if self._norm_status_text(getattr(sys_info, "status", "")) != "teslim edildi":
            return ""
        return self._latest_acceptance_date(sys_deliveries)

    def _contract_acceptance_date(self, systems: List[SystemInfo]) -> str:
        if not systems:
            return ""
        completed = [
            sys_info for sys_info in systems
            if self._norm_status_text(getattr(sys_info, "status", "")) in {"teslim edildi", "tamamlandi"}
        ]
        if len(completed) != len(systems):
            return ""
        return self._latest_acceptance_date(completed)

    def _apply_derived_statuses(self, ci: ContractInfo, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]):
        for sys_info in systems:
            sys_deliveries = list(deliveries.get(sys_info.name, []) or [])
            sys_info.status = self._derive_system_status(sys_info, sys_deliveries)
            sys_info.acceptance_date = self._system_acceptance_date(sys_info, sys_deliveries)

        ci.acceptance_date = self._contract_acceptance_date(systems)

        system_statuses = [self._norm_status_text(getattr(sys_info, "status", "")) for sys_info in systems]
        if not system_statuses or all(st == "baslanmadi" for st in system_statuses):
            ci.status = "Başlanmadı"
        elif all(st in {"teslim edildi", "tamamlandi"} for st in system_statuses):
            ci.status = "Tamamlandı"
        else:
            ci.status = "Devam ediyor"

    def _prepare_context_for_save(self, ctx: dict) -> Tuple[bool, str]:
        ci = ctx.get("ci")
        systems = ctx.get("systems") or []
        deliveries = ctx.get("deliveries") or {}
        if not ci:
            return False, "Sözleşme bilgisi eksik."
        if not systems:
            return False, f"{ci.contract_type}: en az bir sistem ekleyin."
        created_defaults = []
        deleted_delivery_systems = set(ctx.get("deleted_delivery_systems") or set())
        for sys_info in systems:
            if self._system_has_component_quantity(sys_info) and not deliveries.get(sys_info.name) and sys_info.name not in deleted_delivery_systems:
                d = self._default_acceptance_for(sys_info)
                if d:
                    deliveries.setdefault(sys_info.name, []).append(d)
                    created_defaults.append(sys_info.name)
        if created_defaults:
            ctx["deliveries"] = deliveries
            ctx["systems"] = systems
            ctx["_created_default_systems"] = created_defaults
            return False, (
                f"{ci.contract_type}: otomatik Kabul 1 ekranda oluşturuldu. "
                "Lütfen açılan kabul ekranını kontrol edip onaylayın; ardından tekrar Kaydet'e basın."
            )
        issues = self._acceptance_coverage_issues(systems, deliveries)
        if issues:
            title, message = self._acceptance_validation_message(issues)
            ctx["_acceptance_validation_title"] = title
            ctx["_acceptance_validation_issues"] = issues
            return False, f"{ci.contract_type}: {message}"
        self._apply_derived_statuses(ci, systems, deliveries)
        ctx["deliveries"] = deliveries
        ctx["systems"] = systems
        return True, ""

    def _save_context_family(self) -> bool:
        self._cache_current_context()
        family = self._family_context_rows()
        keys = []
        for it in family:
            key = tuple(it.get("_cache_key") or (it.get("platform"), it.get("no"), it.get("type")))
            if key in self._context_cache and key not in keys:
                keys.append(key)
        if not keys:
            return False
        keys.sort(key=lambda k: (1 if self._is_sd_type(k[2]) else 0, self._sd_sort_key(k[2])))
        for key in keys:
            ok, msg = self._prepare_context_for_save(self._context_cache[key])
            if not ok:
                ctx = self._context_cache[key]
                created_defaults = list(ctx.pop("_created_default_systems", []) or [])
                validation_title = str(ctx.pop("_acceptance_validation_title", "") or "")
                validation_issues = list(ctx.pop("_acceptance_validation_issues", []) or [])
                self._load_cached_context(key)
                if created_defaults:
                    self.selected_system = created_defaults[0]
                elif validation_issues:
                    self._focus_acceptance_issue(validation_issues)
                self.expanded_delivery_index = None
                self.refresh_contract_header()
                self.render_contract_tags()
                self.refresh()
                QMessageBox.information(
                    self,
                    "Kabul oluşturuldu" if created_defaults else (validation_title or "Eksik"),
                    msg,
                )
                if created_defaults:
                    QTimer.singleShot(0, lambda name=created_defaults[0]: self._open_first_delivery_for_system(name))
                return True
        main_start = 0
        main_end = 0
        actor = self.store.current_actor()
        with self.store.batch_save():
            for key in keys:
                ctx = self._context_cache[key]
                ci = ctx["ci"]
                if self._is_sd_type(ci.contract_type) and main_start:
                    ci.sd_anchor_start_row = main_start
                    ci.sd_anchor_end_row = main_end or main_start
                    ci.sd_anchor_platform = ci.platform
                    ci.sd_anchor_no = ci.no
                written_start = self.store.write_contract(
                    ci,
                    ctx.get("systems") or [],
                    ctx.get("deliveries") or {},
                    old_contract_no=ctx.get("original_contract_no") or ci.no,
                    old_start_row=ctx.get("original_entry_start_row") or 0,
                )
                ci.entry_start_row = int(written_start or 0)
                if not self._is_sd_type(ci.contract_type):
                    try:
                        info = self.store.find_main_contract_info(ci.platform, ci.no)
                        main_start = int((info or {}).get("block_start") or written_start or 0)
                        main_end = int((info or {}).get("block_end") or main_start or 0)
                    except Exception:
                        main_start = int(written_start or 0)
                        main_end = main_start
                old_key = (
                    str(ctx.get("original_platform") or "").strip(),
                    str(ctx.get("original_contract_no") or "").strip(),
                    str(ctx.get("original_contract_type") or "").strip(),
                )
                new_key = (str(ci.platform or "").strip(), str(ci.no or "").strip(), str(ci.contract_type or "").strip())
                if old_key != new_key and all(old_key):
                    self.store.save_contract_tags(old_key[0], old_key[1], old_key[2], [], actor=actor)
                self.store.save_contract_tags(new_key[0], new_key[1], new_key[2], ctx.get("tags") or [], actor=actor)
                ctx["original_platform"] = new_key[0]
                ctx["original_contract_no"] = new_key[1]
                ctx["original_contract_type"] = new_key[2]
                ctx["original_entry_start_row"] = int(written_start or 0)
        current_key = self._context_key()
        if current_key in self._context_cache:
            self._load_cached_context(current_key)
        QMessageBox.information(self, "Kaydedildi", "Ana sözleşme ve bağlı SD kayıtları Excel'e yazıldı.")
        self._is_dirty = False
        self.accept()
        return True

    def _system_status_kind(self, status: str) -> str:
        norm = self._norm_status_text(status)
        if norm in {"teslim edildi", "tamamlandi"}:
            return "done"
        if norm in {"teslimata hazirlaniyor", "parcali teslimat"}:
            return "progress"
        return "notstarted"

    def _make_system_item_widget(self, sys_info: SystemInfo, selected: bool = False) -> QWidget:
        status = str(getattr(sys_info, "status", "") or "Başlanmadı")
        kind = self._system_status_kind(status)

        card = QFrame()
        card.setObjectName("systemListCard")
        card.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        name = QLabel(str(sys_info.name or "Sistem"))
        name.setObjectName("systemItemName")
        name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name.setMinimumWidth(0)
        name.setWordWrap(False)

        # Seçili değilse siyah, seçiliyse beyaz.
        name.setStyleSheet(
            "background: transparent; color: #ffffff; font-weight: 900; font-size: 12px;"
            if selected else
            "background: transparent; color: #0f172a; font-weight: 900; font-size: 12px;"
        )

        pill = QLabel(status)
        pill.setObjectName("systemStatusPill")
        pill.setProperty("kind", kind)
        pill.setAlignment(Qt.AlignCenter)
        pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pill.setMinimumWidth(108)
        pill.setMaximumWidth(138)
        pill.setFixedHeight(22)
        pill.setWordWrap(False)

        row.addWidget(name, 1)
        row.addWidget(pill, 0, Qt.AlignRight | Qt.AlignVCenter)
        lay.addLayout(row)

        return card

    def _populate_system_list(self, keep_row: Optional[int] = None):
        current = self.system_list.currentRow() if keep_row is None else keep_row

        target = 0
        if self.systems:
            target = max(0, min(current, len(self.systems) - 1))
            if self.selected_system:
                for idx, sys_info in enumerate(self.systems):
                    if sys_info.name == self.selected_system:
                        target = idx
                        break

        self.system_list.blockSignals(True)
        self.system_list.clear()

        for idx, sys_info in enumerate(self.systems):
            item = self._make_system_list_item(sys_info)
            item.setSizeHint(QSize(0, 58))
            self.system_list.addItem(item)

            is_selected = idx == target
            self.system_list.setItemWidget(
                item,
                self._make_system_item_widget(sys_info, selected=is_selected)
            )

        if self.systems:
            self.system_list.setCurrentRow(target)

        self.system_list.blockSignals(False)

    def refresh_live_statuses(self):
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self.refresh_contract_header()
        self._populate_system_list()

    def _make_system_list_item(self, sys_info: SystemInfo) -> QListWidgetItem:
        status = str(getattr(sys_info, "status", "") or "Başlanmadı")
        item = QListWidgetItem()
        item.setData(Qt.UserRole, status)
        return item

    def refresh(self):
        self.refresh_sd_sidebar()
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self.refresh_contract_header()
        self._populate_system_list()
        self.refresh_right()
        if hasattr(self, 'update_timeline_bar'):
            self.update_timeline_bar()

    def _component_display_keys(self, sys_info: Optional[SystemInfo]) -> List[str]:
        """Sistemin tum secili bilesenleri dondur.
        excel_store artik sadece qty > 0 bilesenleri yukledigi icin
        sys_info.components'ta ne varsa kullanici secmis veya deger girmistir.
        qty=0 olsa bile (yeni eklenmis bilesenler) goster ki kullanici deger girebilsin.
        """
        if not sys_info:
            return []
        return list(sys_info.components.keys())

    def sync_summary_to_system(self):
        sys_info = self.current_system()
        if not sys_info:
            return
        for r in range(self.summary.rowCount()):
            comp_item = self.summary.item(r, 0)
            qty_item = self.summary.item(r, 1)
            if not comp_item or not qty_item:
                continue
            comp = comp_item.text()
            sys_info.components[comp] = as_number(qty_item.text())
            note_item = self.summary.item(r, 4)
            note = note_item.text() if note_item else ""
            if not hasattr(sys_info, "component_notes"):
                sys_info.component_notes = {}
            if note:
                sys_info.component_notes[comp] = note
            else:
                sys_info.component_notes.pop(comp, None)

    def on_summary_changed(self, item):
        if self._updating_summary or item.column() not in (1, 4):
            return
        self._set_dirty()
        self.sync_summary_to_system()
        if item.column() == 1:
            self.refresh_system_card_text()
            self.refresh_summary_only()

    def refresh_system_card_text(self):
        r = self.system_list.currentRow()
        if 0 <= r < len(self.systems):
            s = self.systems[r]
            self._populate_system_list(keep_row=r)

    def _parse_iso_date(self, text: str):
        return parse_iso_date(text)

    def _fmt_num(self, v):
        return fmt_num(v)

    def _as_number(self, v):
        return as_number(v)

    def _configure_table(self, table, compact: bool = False):
        return configure_table(table, compact=compact)

    @property
    def _DeliveryDialog(self):
        return DeliveryDialog

    def _show_warning(self, title: str, text: str):
        return QMessageBox.warning(self, title, text)

    def refresh_summary_only(self):
        cw_view.refresh_summary_only(self)

    def update_system_metric_cards(self, sys_info: Optional[SystemInfo]):
        cw_view.update_system_metric_cards(self, sys_info)

    def refresh_right(self):
        cw_view.refresh_right(self)

    def refresh_delivery_table(self):
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.refresh_delivery_table(self)

    def update_pinned_delivery(self, d: Optional[DeliveryInfo], headers: List[str], comps: List[str]):
        self.pinned_delivery.clear()
        self.pinned_delivery.setColumnCount(len(headers))
        self.pinned_delivery.setHorizontalHeaderLabels(headers)
        if d:
            self.pinned_delivery.setRowCount(1)
            vals = ["▼", d.name, d.status, d.acceptance_date] + [d.planned.get(c, 0) for c in comps]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(fmt_num(v) if isinstance(v, (int, float)) else str(v))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.pinned_delivery.setItem(0, c, it)
        else:
            self.pinned_delivery.setRowCount(0)
        self.pinned_delivery.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self.pinned_delivery.columnCount() > 0:
            self.pinned_delivery.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.pinned_delivery.setColumnWidth(0, 44)

        header_h = self.pinned_delivery.horizontalHeader().height()
        row_h = self.pinned_delivery.rowHeight(0) if self.pinned_delivery.rowCount() else 0
        frame = 2 * self.pinned_delivery.frameWidth()
        total_h = header_h + row_h + frame + (2 if row_h else 0)
        self.pinned_delivery.setMinimumHeight(total_h)
        self.pinned_delivery.setMaximumHeight(total_h)

    def delivery_detail_widget(self, d: DeliveryInfo, comps: List[str], idx: int) -> QWidget:
        from src.ui.contract import work_window_deliveries as cw_deliveries
        return cw_deliveries.delivery_detail_widget(self, d, comps, idx)

    def edit_delivery(self, idx: int):
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.edit_delivery(self, idx)

    def on_delivery_clicked(self, row, col):
        if col != 0 or row not in self._delivery_row_map:
            return
        idx = self._delivery_row_map[row]
        self.edit_delivery(idx)

    def on_pinned_delivery_clicked(self, row, col):
        pass  # pinned panel kaldirildi

    def _system_has_component_quantity(self, sys_info: SystemInfo) -> bool:
        return any(as_number(v) > 0.0001 for v in (sys_info.components or {}).values())

    def _create_default_acceptance_for_system(self, sys_info: SystemInfo):
        d = self._default_acceptance_for(sys_info)
        if d:
            self.deliveries.setdefault(sys_info.name, []).append(d)
            self._deleted_delivery_systems.discard(sys_info.name)
            self._set_dirty()

    def _open_first_delivery_for_system(self, system_name: str):
        if not system_name:
            return
        self.selected_system = system_name
        self._populate_system_list()
        for idx, sys_info in enumerate(self.systems):
            if sys_info.name == system_name:
                self.system_list.setCurrentRow(idx)
                break
        self.refresh_right()
        if self.deliveries.get(system_name):
            self.edit_delivery(0)

    def _acceptance_coverage_issues(self, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]) -> List[dict]:
        return acceptance_coverage_issues(systems, deliveries)

    def _acceptance_validation_message(self, issues: List[dict]) -> Tuple[str, str]:
        unassigned = [issue for issue in issues if issue.get("kind") == "unassigned"]
        over_delivered = [issue for issue in issues if issue.get("kind") == "over_delivered"]
        delivery_over_planned = [issue for issue in issues if issue.get("kind") == "delivery_over_planned"]
        over_assigned = [issue for issue in issues if issue.get("kind") == "over_assigned"]
        if over_delivered:
            title = "Teslim edilen miktar sözleşme adedini aşıyor"
            intro = "Bazı bileşenlerde teslim edilen miktar sözleşme adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['component']}: sözleşme {fmt_num(issue['contract_qty'])}, teslim edilen {fmt_num(issue['delivered_qty'])}" for issue in over_delivered]
        elif delivery_over_planned:
            title = "Teslim edilen miktar kabul adedini aşıyor"
            intro = "Bazı kabullerde teslim edilen miktar kabul adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['delivery']} / {issue['component']}: kabul {fmt_num(issue['planned_qty'])}, teslim edilen {fmt_num(issue['delivered_qty'])}" for issue in delivery_over_planned]
        elif over_assigned:
            title = "Kabul miktarı sistem adedini aşıyor"
            intro = "Bazı bileşenlerde kabullere atanan miktar sistem adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['component']}: sistem {fmt_num(issue['contract_qty'])}, kabuller {fmt_num(issue['planned_qty'])}" for issue in over_assigned]
        else:
            title = "Atanmamış bileşenler var"
            intro = "Bu sözleşmede teslimata/kabule atanmamış bileşenler bulunuyor. Kaydetmeden önce kalan bileşenleri bir kabule atayın."
            details = [f"• {issue['system']} / {issue['component']}: {fmt_num(issue['qty'])} adet atanmadı" for issue in unassigned]
        shown = details[:10]
        if len(details) > len(shown):
            shown.append(f"... ve {len(details) - len(shown)} kalem daha")
        return title, intro + "\n\n" + "\n".join(shown)

    def _focus_acceptance_issue(self, issues: List[dict]):
        if not issues:
            return
        system_name = str(issues[0].get("system") or "")
        if not system_name:
            return
        self.selected_system = system_name
        self._populate_system_list()
        for index, sys_info in enumerate(self.systems):
            if sys_info.name == system_name:
                self.system_list.setCurrentRow(index)
                break
        self.refresh_right()

    def _validate_acceptance_totals(self, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]) -> List[str]:
        errors = []
        for sys_info in systems:
            sys_deliveries = deliveries.get(sys_info.name, []) or []
            components = self._component_display_keys(sys_info)
            for comp in components:
                total = max(as_number((sys_info.components or {}).get(comp, 0)), 0)
                planned_sum = sum(max(as_number((d.planned or {}).get(comp, 0)), 0) for d in sys_deliveries)
                delivered_sum = sum(max(as_number((d.delivered or {}).get(comp, 0)), 0) for d in sys_deliveries)
                if planned_sum - total > 0.0001:
                    errors.append(f"{sys_info.name} / {comp}: sistem {fmt_num(total)}, kabuller {fmt_num(planned_sum)}")
                if delivered_sum - planned_sum > 0.0001:
                    errors.append(f"{sys_info.name} / {comp}: teslim edilen {fmt_num(delivered_sum)}, kabul adedi {fmt_num(planned_sum)}")
            for delivery in sys_deliveries:
                for comp, qty in (delivery.delivered or {}).items():
                    planned_qty = max(as_number((delivery.planned or {}).get(comp, 0)), 0)
                    delivered_qty = max(as_number(qty), 0)
                    if delivered_qty - planned_qty > 0.0001:
                        errors.append(f"{sys_info.name} / {delivery.name} / {comp}: teslim edilen, kabul adedini aşıyor")
        return errors

    def ensure_systems_have_acceptances(self) -> bool:
        missing_systems = [
            sys_info for sys_info in self.systems
            if self._system_has_component_quantity(sys_info)
            and not self.deliveries.get(sys_info.name)
            and sys_info.name not in self._deleted_delivery_systems
        ]
        if not missing_systems:
            return True

        names = "\n".join(f"• {sys_info.name}" for sys_info in missing_systems)
        answer = QMessageBox.question(
            self,
            "Kabul eklenmemiş sistem var",
            "Aşağıdaki sistemlere kabul eklemediniz:\n\n"
            f"{names}\n\n"
            "Onaylarsanız bu sistemlerin içine Kabul 1 otomatik oluşturulacak ve "
            "sistemdeki tüm bileşen adetleri Kabul 1'e atanacaktır.\n\n"
            "Onaylamazsanız kabul eklemeden kaydetmeye izin verilmeyecektir.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            QMessageBox.warning(
                self,
                "Kabul gerekli",
                "Kabul eklenmemiş sistemler için kabul oluşturmadan kaydetme yapılamaz.",
            )
            return False

        first_missing_name = missing_systems[0].name
        for sys_info in missing_systems:
            self._create_default_acceptance_for_system(sys_info)
        self.expanded_delivery_index = None
        if first_missing_name:
            self.selected_system = first_missing_name
        self._populate_system_list()
        self.refresh_right()
        QMessageBox.information(
            self,
            "Kabul oluşturuldu",
            "Otomatik Kabul 1 kayıtları ekranda oluşturuldu. "
            "Lütfen açılan kabul ekranını kontrol edip onaylayın; ardından tekrar Kaydet'e basın.",
        )
        QTimer.singleShot(0, lambda name=first_missing_name: self._open_first_delivery_for_system(name))
        return False

    def reject(self) -> None:
        """Kapat butonuna basıldığında değişiklik varsa onay ister."""
        if self._is_dirty:
            answer = QMessageBox.question(
                self,
                "Değişiklikler Kaydedilmedi",
                "Yaptığınız değişiklikler kaydedilmeyecektir.\n\n"
                "Onaylıyor musunuz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        super().reject()

    def save_all(self):
        # Değişiklik yoksa kaydetme
        if not self._is_dirty and not self.is_new_contract:
            QMessageBox.information(
                self,
                "Değişiklik Yok",
                "Herhangi bir değişiklik uygulamadınız.\n\n"
                "Excel'de herhangi bir değişiklik uygulanmayacak,\n"
                "versiyon ayrımı yapılmayacaktır.",
            )
            return

        if self._save_context_family():
            return
        if not self.systems:
            QMessageBox.warning(self, "Eksik", "En az bir sistem ekleyin.")
            return
        self.sync_summary_to_system()
        if not self.ensure_systems_have_acceptances():
            return
        issues = self._acceptance_coverage_issues(self.systems, self.deliveries)
        if issues:
            title, message = self._acceptance_validation_message(issues)
            self._focus_acceptance_issue(issues)
            QMessageBox.warning(self, title, message)
            return
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        # ── Değişiklik tespiti ──────────────────────────────────────────────
        if not self.is_new_contract:
            if self._make_data_snapshot() == self._initial_snapshot:
                QMessageBox.information(
                    self,
                    "Değişiklik Yok",
                    "Herhangi bir değişiklik uygulamadınız.\n\n"
                    "Excel'de herhangi bir değişiklik uygulanmayacak,\n"
                    "versiyon ayrımı yapılmayacaktır.",
                )
                return
        # ───────────────────────────────────────────────────────────────────
        old_key = (
            str(self.original_platform or "").strip(),
            str(self.original_contract_no or "").strip(),
            str(self.original_contract_type or "").strip(),
        )
        new_key = (
            str(self.ci.platform or "").strip(),
            str(self.ci.no or "").strip(),
            str(self.ci.contract_type or "").strip(),
        )
        actor = self.store.current_actor()
        self._pending_contract_save_context = {
            "old_key": old_key,
            "new_key": new_key,
            "actor": actor,
            "tags": [dict(t or {}) for t in self.contract_tags],
        }
        worker = ContractSaveWorker(
            self.store.path,
            "write",
            str(self.ci.platform or ""),
            str(self.ci.no or ""),
            ci=copy.deepcopy(self.ci),
            systems=copy.deepcopy(self.systems),
            deliveries=copy.deepcopy(self.deliveries),
            old_contract_no=self.original_contract_no,
            old_start_row=self.original_entry_start_row,
            actor=actor,
            store=self.store,
        )
        self._start_contract_save_worker(worker, "Sözleşme kaydediliyor...")





def _is_sts_store(store) -> bool:
    return bool(
        store is not None
        and hasattr(store, "db")
        and hasattr(store, "write_users")
        and hasattr(store, "write_components")
    )

def section_label(text):
    l = QLabel(text)
    l.setObjectName("sectionTitle")
    return l

def configure_table(table: QTableWidget, compact: bool = False):
    table.setItemDelegate(CenterTableDelegate(table))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.horizontalHeader().setMinimumHeight(42 if not compact else 34)
    table.verticalHeader().setDefaultSectionSize(34 if not compact else 28)
    table.setWordWrap(False)

def fill_table(table, rows):
    table.setRowCount(len(rows)); table.setColumnCount(len(rows[0]) if rows else table.columnCount())
    for r,row in enumerate(rows):
        for c,v in enumerate(row): table.setItem(r,c,QTableWidgetItem(str(int(v) if isinstance(v,float) and v==int(v) else v)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)



from src.ui.dialogs.contract_summary_popup import ContractSummaryPopup

from src.ui.dialogs.workbook_start import WorkbookStartDialog
from src.ui.contract import work_window_view as cw_view

class MainWindow(QMainWindow):
    def __init__(self, store: Optional[ExcelStore] = None, contract_index: Optional[List[dict]] = None, initial_path: Optional[Path] = None):
        super().__init__()
        self.path = Path(initial_path) if initial_path else (store.path if store else Path(DEFAULT_FILE))
        self.store = store
        self.contract_index = contract_index if contract_index is not None else []
        self._tag_color_map_cache: Optional[Dict[str, str]] = None
        self._loading = False
        self._loader_thread: Optional[QThread] = None
        self._loader_worker: Optional[ExcelLoadWorker] = None
        self._streaming_index = False
        self._store_loading = False
        self._last_load_timings: Dict[str, float] = {}
        self._index_ready_for_use = False
        self._version_baseline_signature = None
        self.calendar_window: Optional[ContractCalendarWindow] = None
        self._pending_select_platform: Optional[str] = None
        self.selected_platforms: set[str] = set()
        self.multi_platform_mode: bool = False
        self._updating_platform_list = False
        self._platform_checkbox_changed: Optional[str] = None
        self.setWindowTitle(APP_TITLE)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1360, 820)
        self.setStyleSheet(STYLE)
        self.all_contract_rows = []
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.timeout.connect(self.apply_contract_filter)
        self.build()
        if self.store:
            if not self.contract_index:
                # UI thread'i bloklamamak için hazır store olsa bile indeksleme yükünü worker'a bırak.
                self.start_sts_load(self.store.path) if str(self.store.path).lower().endswith(".sts") else self.start_excel_load(self.store.path)
            else:
                self.refresh(rebuild_index=False)
                self._apply_version_to_ui()
                self._remember_version_baseline()
        else:
            self.set_empty_state()
            self.connection_label.setText("Excel bağlı değil")


    def export_sts_to_excel(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return
        if not hasattr(self.store, "export_to_excel"):
            QMessageBox.information(self, "Excel’e Aktar", "Excel’e aktarım yalnızca STS veri dosyalarında desteklenir.")
            return
        active_platform = ""
        selected = set(getattr(self, "selected_platforms", set()))
        if len(selected) == 1:
            active_platform = next(iter(selected))
        from src.ui.dialogs.excel_export_options import ExcelExportDialog
        dlg = ExcelExportDialog(self.store, self, active_platform=active_platform, contract_index=getattr(self, "contract_index", None))
        if not dlg.exec() or not dlg.result_options:
            return
        opts = dict(dlg.result_options)
        out, _ = QFileDialog.getSaveFileName(self, "Excel’e Aktar", str(Path(self.path).with_suffix('.xlsx')), "Excel (*.xlsx)")
        if not out:
            return
        from src.workers.export_workers import ExcelExportWorker
        self._export_progress = QProgressDialog("Excel dosyası hazırlanıyor...", "", 0, 100, self)
        self._export_progress.setWindowTitle("Excel’e Aktar")
        self._export_progress.setLabelText("Excel dosyası hazırlanıyor...")
        self._export_progress.setCancelButton(None)
        self._export_progress.setMinimumDuration(0)
        self._export_progress.setAutoClose(False)
        self._export_progress.setAutoReset(False)
        self._export_progress.setValue(0)
        self._export_progress.show()

        self._export_thread = QThread(self)
        self._export_worker = ExcelExportWorker(self.store, out, opts)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(lambda p, m: (self._export_progress.setLabelText(str(m)), self._export_progress.setValue(int(max(0,min(100,p))))))
        def _done(_res):
            self._export_progress.setValue(100)
            self._export_progress.close()
            QMessageBox.information(self, "Excel’e Aktar", "Excel dosyası oluşturuldu.")
        def _fail(msg):
            self._export_progress.close()
            QMessageBox.critical(self, "Excel’e Aktar", str(msg))
        self._export_worker.finished.connect(_done)
        self._export_worker.failed.connect(_fail)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._export_thread.deleteLater)
        self._export_thread.start()

    def open_database_management(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return
        if not hasattr(self.store, "database_stats"):
            QMessageBox.information(self, "Database Yönetimi", "Database yönetimi yalnızca STS veri dosyalarında desteklenir.")
            return
        from src.ui.dialogs.database_management import DatabaseManagementDialog
        dlg = DatabaseManagementDialog(self.store, self)
        dlg.exec()


    def open_performance_tracking(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return

        if not hasattr(self.store, "performance_stats"):
            QMessageBox.information(
                self,
                "Performans Takip",
                "Performans takip ekranı yalnızca STS veri dosyalarında desteklenir."
            )
            return

        from src.ui.dialogs.performance_tracking import PerformanceTrackingDialog
        dlg = PerformanceTrackingDialog(self.store, self)
        dlg.exec()

    def open_activity_logs(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return
        if not hasattr(self.store, "list_logs"):
            QMessageBox.information(self, "İşlem Geçmişi", "İşlem geçmişi yalnızca STS veri dosyalarında desteklenir.")
            return
        from src.ui.dialogs.activity_logs import ActivityLogDialog
        dlg = ActivityLogDialog(self.store, self)
        dlg.exec()

    def open_usage_guide(self):
        try:
            dlg = UsageGuideDialog(self)
            dlg.exec()
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.warning(self, "Kullanım Kılavuzu", f"Kullanım kılavuzu açılamadı:\n{exc}")


    def build(self):
        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        top=QFrame(); top.setObjectName("topbar"); tl=QHBoxLayout(top); tl.setContentsMargins(12, 8, 12, 8); tl.setSpacing(10)
        logo_path = app_icon_path()
        if logo_path.exists():
            logo = QLabel(); logo.setObjectName("appLogo")
            logo.setPixmap(QPixmap(str(logo_path)).scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setFixedSize(52, 52)
            logo.setAlignment(Qt.AlignCenter)
            tl.addWidget(logo)
        title=QLabel(APP_TITLE); title.setObjectName("appTitle"); tl.addWidget(title)
        self.connection_label=QLabel("✓ Excel bağlı"); self.connection_label.setObjectName("okPill"); tl.addWidget(self.connection_label)
        tl.addStretch()
        self.top_actions_btn = QToolButton()
        self.top_actions_btn.setObjectName("topMenuBtn")
        self.top_actions_btn.setText("☰")
        self.top_actions_btn.setToolTip("Menü")
        self.top_actions_btn.setPopupMode(QToolButton.InstantPopup)
        self.top_actions_menu = QMenu(self.top_actions_btn)
        self.top_actions_menu.setObjectName("topActionsMenu")
        self.top_actions_menu.addAction("Veri Dosyası Değiştir", self.open_file)
        self.top_actions_menu.addAction("Excel’e Aktar", self.export_sts_to_excel)
        self.top_actions_menu.addAction("Database Yönetimi", self.open_database_management)
        self.top_actions_menu.addAction("Performans Takip", self.open_performance_tracking)
        self.top_actions_menu.addAction("Platform Yönetimi", self.manage_platforms)
        self.top_actions_menu.addSeparator()
        self.top_actions_menu.addAction("Kullanıcı Yönetimi", self.manage_users)
        self.top_actions_menu.addAction("Etiket Yönetimi", self.manage_tags)
        self.top_actions_menu.addAction("Bileşen Yönetimi", self.manage_components)
        self.top_actions_menu.addAction("İşlem Geçmişi", self.open_activity_logs)
        self.top_actions_menu.addSeparator()
        self.top_actions_menu.addAction("📘 Kullanım Kılavuzu", self.open_usage_guide)
        self.top_actions_btn.setMenu(self.top_actions_menu)
        tl.addWidget(self.top_actions_btn)
        main.addWidget(top, 0)

        strip=QFrame(); strip.setObjectName("alertStrip"); sl=QHBoxLayout(strip); sl.setContentsMargins(12, 10, 12, 10); sl.setSpacing(10)
        today_box = QFrame(); today_box.setObjectName("todayBadge")
        today_l = QVBoxLayout(today_box); today_l.setContentsMargins(12, 8, 12, 8); today_l.setSpacing(1)
        self.today_num = QLabel(str(date.today().day)); self.today_num.setObjectName("todayDay"); self.today_num.setAlignment(Qt.AlignCenter)
        self.today_info = QLabel(""); self.today_info.setObjectName("todayInfo"); self.today_info.setAlignment(Qt.AlignCenter)
        today_l.addWidget(self.today_num); today_l.addWidget(self.today_info)
        sl.addWidget(today_box, 0)

        self.alert_divider1 = QFrame(); self.alert_divider1.setObjectName("stripDivider"); sl.addWidget(self.alert_divider1, 0)

        self.alert_overdue_group = QFrame(); self.alert_overdue_group.setObjectName("alertGroup")
        g1l = QHBoxLayout(self.alert_overdue_group); g1l.setContentsMargins(8, 6, 8, 6); g1l.setSpacing(8)
        i1 = QLabel("⚠"); i1.setObjectName("alertIconRed"); g1l.addWidget(i1)
        t1 = QVBoxLayout(); t1.setContentsMargins(0, 0, 0, 0); t1.setSpacing(0)
        self.overdue_count = QLabel("0"); self.overdue_count.setObjectName("alertCountRed")
        l1 = QLabel("GECİKEN"); l1.setObjectName("alertLabel")
        t1.addWidget(self.overdue_count); t1.addWidget(l1); g1l.addLayout(t1)
        sl.addWidget(self.alert_overdue_group, 0)

        self.alert_critical_group = QFrame(); self.alert_critical_group.setObjectName("alertGroup")
        g2l = QHBoxLayout(self.alert_critical_group); g2l.setContentsMargins(8, 6, 8, 6); g2l.setSpacing(8)
        i2 = QLabel("⏳"); i2.setObjectName("alertIconAmber"); g2l.addWidget(i2)
        t2 = QVBoxLayout(); t2.setContentsMargins(0, 0, 0, 0); t2.setSpacing(0)
        self.critical_count = QLabel("0"); self.critical_count.setObjectName("alertCountAmber")
        l2 = QLabel("60 GÜN İÇİNDE"); l2.setObjectName("alertLabel")
        t2.addWidget(self.critical_count); t2.addWidget(l2); g2l.addLayout(t2)
        sl.addWidget(self.alert_critical_group, 0)

        self.alert_divider2 = QFrame(); self.alert_divider2.setObjectName("stripDivider"); sl.addWidget(self.alert_divider2, 0)
        self.upcoming_label = QLabel("Yaklaşan:"); self.upcoming_label.setObjectName("upcomingLabel")
        sl.addWidget(self.upcoming_label, 0)
        self.upcoming_scroll = QScrollArea(); self.upcoming_scroll.setObjectName("upcomingScroll")
        self.upcoming_scroll.setWidgetResizable(True)
        self.upcoming_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.upcoming_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.upcoming_host = QWidget()
        self.upcoming_layout = QHBoxLayout(self.upcoming_host)
        self.upcoming_layout.setContentsMargins(0, 0, 0, 0)
        self.upcoming_layout.setSpacing(6)
        self.upcoming_layout.addStretch()
        self.upcoming_scroll.setWidget(self.upcoming_host)
        sl.addWidget(self.upcoming_scroll, 1)

        calb=QPushButton("🗓 Takvim Görünümü"); calb.clicked.connect(self.open_calendar_tracking); sl.addWidget(calb, 0)
        main.addWidget(strip, 0)

        body=QHBoxLayout(); body.setSpacing(8); main.addLayout(body,1)
        left=QFrame(); left.setObjectName("panel"); left.setFixedWidth(350); lv=QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)
        platform_head = QWidget(); ph = QHBoxLayout(platform_head); ph.setContentsMargins(12, 8, 12, 8); ph.setSpacing(6)
        h=QLabel("Platformlar"); h.setObjectName("panelTitle"); ph.addWidget(h); ph.addStretch(1)
        self.platform_selection_badge = QLabel(""); self.platform_selection_badge.setObjectName("platformSelectionBadge")
        self.platform_selection_badge.setStyleSheet("QLabel{background:#dbeafe;color:#1d4ed8;border-radius:9px;padding:2px 7px;font-size:11px;font-weight:800;}")
        self.platform_selection_badge.hide(); ph.addWidget(self.platform_selection_badge)
        lv.addWidget(platform_head)
        self.platform_list=QListWidget(); self.platform_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.platform_list.itemClicked.connect(self.on_platform_clicked)
        self.platform_list.itemChanged.connect(self._on_platform_item_changed)
        self.platform_list.customContextMenuRequested.connect(self._on_platform_context_menu_requested)
        lv.addWidget(self.platform_list,1)
        self.platform_info_bar = QFrame(); self.platform_info_bar.setObjectName("platformInfoBar")
        self.platform_info_bar.setStyleSheet("QFrame#platformInfoBar{background:#f8fbff;border-top:1px solid #dbe7f5;} QLabel{color:#64748b;font-size:11px;} QPushButton{background:transparent;border:0;color:#1d4ed8;font-size:11px;font-weight:800;padding:2px 4px;}")
        pi = QHBoxLayout(self.platform_info_bar); pi.setContentsMargins(10, 4, 8, 4); pi.setSpacing(4)
        self.platform_info_label = QLabel(""); pi.addWidget(self.platform_info_label); pi.addStretch(1)
        clear_platforms = QPushButton("temizle"); clear_platforms.clicked.connect(self.clear_platform_selection); pi.addWidget(clear_platforms)
        self.platform_info_bar.hide(); lv.addWidget(self.platform_info_bar)
        new=QPushButton("+ Yeni Sözleşme"); new.clicked.connect(self.new_contract); new.setMinimumHeight(46); lv.addWidget(new)
        body.addWidget(left, 0)

        right=QFrame(); right.setObjectName("panel"); rv=QVBoxLayout(right); rv.setContentsMargins(12, 10, 12, 10); rv.setSpacing(8)
        self.right_panel = right
        head_row = QHBoxLayout()
        self.right_title=QLabel("Sözleşme Sorgulama"); self.right_title.setObjectName("queryTitle")
        head_row.addWidget(self.right_title)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Sözleşme no, kullanıcı veya durum ara..."); self.search_input.textChanged.connect(self.schedule_apply_contract_filter)
        head_row.addWidget(self.search_input, 1)
        self.clear_col_filters_btn = QPushButton("Filtreleri Temizle")
        self.clear_col_filters_btn.setObjectName("secondary")
        self.clear_col_filters_btn.clicked.connect(self.clear_query_filters)
        head_row.addWidget(self.clear_col_filters_btn, 0)
        hint = QLabel("Sözleşmeye çift tıklayınca detay ekranı açılır."); hint.setObjectName("muted"); head_row.addWidget(hint)
        rv.addLayout(head_row)

        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filterBar")
        fb = QHBoxLayout(self.filter_bar)
        fb.setContentsMargins(8, 6, 8, 6)
        fb.setSpacing(8)
        self.filter_type = QComboBox()
        self.filter_type.addItem("Tüm Türler", "")
        self.filter_type.currentIndexChanged.connect(self.schedule_apply_contract_filter)
        fb.addWidget(self.filter_type, 0)
        self._date_from_active = False
        self._date_to_active = False
        fb.addWidget(QLabel("Sıralama:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Varsayılan", "default")
        self.sort_combo.addItem("Sözleşme No (Artan)", "no_asc")
        self.sort_combo.addItem("Sözleşme No (Azalan)", "no_desc")
        self.sort_combo.addItem("T. Tarihi (Yakın)", "date_asc")
        self.sort_combo.addItem("T. Tarihi (Uzak)", "date_desc")
        self.sort_combo.addItem("Kalan Gün (Artan)", "days_asc")
        self.sort_combo.addItem("Kalan Gün (Azalan)", "days_desc")
        self.sort_combo.addItem("Kullanıcı (A-Z)", "user_asc")
        self.sort_combo.addItem("Kullanıcı (Z-A)", "user_desc")
        self.sort_combo.currentIndexChanged.connect(self.schedule_apply_contract_filter)
        fb.addWidget(self.sort_combo, 0)
        self.clear_filters_btn = QPushButton("Temizle")
        self.clear_filters_btn.setObjectName("secondary")
        self.clear_filters_btn.clicked.connect(self.clear_query_filters)
        fb.addWidget(self.clear_filters_btn, 0)
        fb.addStretch()
        self.filter_bar.setVisible(False)
        self.contract_table=QTableWidget(0,9)
        self.contract_table.setObjectName("contractTable")
        # Yatay scroll yok — sütunlar her zaman tablo içinde kalır
        self.contract_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Excel gibi sutun filtresi
        self._filter_header = FilterableHeaderView(Qt.Horizontal, self.contract_table)
        self._filter_header.filterChanged.connect(self.schedule_apply_contract_filter)
        self.contract_table.setHorizontalHeader(self._filter_header)
        self.contract_table.setHorizontalHeaderLabels(["Platform", "Sözleşme Türü", "Sözleşme No", "Kullanıcı", "Durum", "T. Tarihi", "Kalan Gün", "Etiketler", "Özet"])
        self.contract_table._filter_col_keys = ["platform", "type", "no", "user", "status", "date", "days", "tags", "summary"]
        self.contract_table._sort_mode = 'default'  # siralama modu
        # Tüm sütunlar Stretch — her zaman ekranı doldurur, yatay kaymaz.
        # Özet sabit 72px sağ kenarda.
        _hh = self.contract_table.horizontalHeader()
        _hh.setSectionResizeMode(QHeaderView.Stretch)    # hepsi orantılı dolar
        _hh.setSectionResizeMode(COL_SUMMARY, QHeaderView.Fixed)   # Özet sabit
        self.contract_table.setColumnWidth(COL_SUMMARY, 72)
        self.contract_table.verticalHeader().setVisible(False)
        self.contract_table.cellDoubleClicked.connect(self.open_selected_contract)
        self.contract_table.cellClicked.connect(self._on_contract_cell_clicked)
        self.contract_table.viewport().installEventFilter(self)
        rv.addWidget(self.contract_table,1)
        self.query_logo_bg = QLabel(self.contract_table)
        self.query_logo_bg.setObjectName("logoWatermark")
        self.query_logo_bg.setStyleSheet("background: transparent;")
        self.query_logo_bg.setAlignment(Qt.AlignCenter)
        self.query_logo_bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.query_logo_bg.hide()
        self.query_logo_bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        logo_opacity = QGraphicsOpacityEffect(self.query_logo_bg)
        logo_opacity.setOpacity(0.22)  # 0.15 çok silik, 0.30 daha belirgin
        self.query_logo_bg.setGraphicsEffect(logo_opacity)
        self._query_logo_source: Optional[QPixmap] = None
        self.contract_table.verticalScrollBar().valueChanged.connect(lambda _v: self.position_query_logo_background())
        self.contract_table.horizontalScrollBar().valueChanged.connect(lambda _v: self.position_query_logo_background())
        body.addWidget(right,1)
        self.build_loading_overlay()
        self.index_progress_badge = QLabel(self.centralWidget())
        self.index_progress_badge.setObjectName("miniProgressPill")
        self.index_progress_badge.setAlignment(Qt.AlignCenter)
        self.index_progress_badge.setText("Excel %0")
        self.index_progress_badge.hide()
        self.index_progress_badge.raise_()
        self.query_logo_bg.raise_()

    def update_connection_badge(self, mode: str):
        m = str(mode or "").strip().lower()
        if m == "ok":
            self.connection_label.setText("✓ Excel bağlı")
            self.connection_label.setProperty("status", "ok")
        elif m == "loading":
            self.connection_label.setText("Excel analiz ediliyor")
            self.connection_label.setProperty("status", "loading")
        else:
            self.connection_label.setText("Excel bağlı değil")
            self.connection_label.setProperty("status", "bad")
        st = self.connection_label.style()
        st.unpolish(self.connection_label)
        st.polish(self.connection_label)
        self.connection_label.update()

    def _apply_version_to_ui(self):
        try:
            from src.services.version_manager import read_version
            ver = read_version(self.store)
            if ver:
                workbook_name = Path(getattr(self.store, "path", self.path)).stem
                label_parts = [part for part in [workbook_name] if part]
                if ver.lower() not in workbook_name.lower():
                    label_parts.append(f"[{ver}]")
                self.setWindowTitle(f"{APP_TITLE}  [{ver}]")
                self.connection_label.setText(f"✓ Excel bağlı  {' '.join(label_parts) or ver}")
                self.connection_label.setProperty("status", "ok")
                st = self.connection_label.style()
                st.unpolish(self.connection_label)
                st.polish(self.connection_label)
                self.connection_label.update()
        except Exception:
            pass

    def _excel_file_signature(self):
        try:
            path = Path(getattr(self.store, "path", self.path))
            st = path.stat()
            return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))
        except Exception:
            return None

    def _remember_version_baseline(self) -> None:
        self._version_baseline_signature = self._excel_file_signature()

    def _workbook_changed_since_load(self) -> bool:
        baseline = getattr(self, "_version_baseline_signature", None)
        current = self._excel_file_signature()
        return bool(baseline and current and current != baseline)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Uygulama kapanırken değişiklik varsa Excel'e versiyon damgası vurur ve dosya adını günceller."""
        if (getattr(self, "store", None) and getattr(self.store, "wb", None)
                and self._workbook_changed_since_load()):
            try:
                from src.services.version_manager import bump_version, save_store_as_versioned_file
                new_ver = bump_version(self.store)
                self.path = save_store_as_versioned_file(self.store, new_ver)
                self._remember_version_baseline()
            except Exception:
                pass
        super().closeEvent(event)

    def build_loading_overlay(self):
        self.loading_overlay = QFrame(self.centralWidget())
        self.loading_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.82); }")
        self.loading_overlay.hide()
        self.loading_overlay.raise_()

        self.loading_card = QFrame(self.loading_overlay)
        self.loading_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.96); border: 1px solid #d8e2ed; border-radius: 12px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(self.loading_card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)
        self.loading_label = QLabel("Analiz ediliyor...")
        self.loading_label.setObjectName("mainTitle")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 100)
        self.loading_progress.setValue(0)
        self.loading_progress.setTextVisible(True)
        self.loading_progress.setFormat("%p%")
        lay.addWidget(self.loading_label)
        lay.addWidget(self.loading_progress)

    def position_loading_overlay(self):
        if not hasattr(self, "loading_overlay"):
            return
        parent = self.centralWidget()
        if not parent:
            return
        self.loading_overlay.setGeometry(parent.rect())
        w, h = 460, 150
        x = max((self.loading_overlay.width() - w) // 2, 0)
        y = max((self.loading_overlay.height() - h) // 2, 0)
        self.loading_card.setGeometry(x, y, w, h)
        self.loading_overlay.raise_()

    def position_query_logo_background(self):
        if not hasattr(self, "query_logo_bg") or not hasattr(self, "contract_table"):
            return

        vp = self.contract_table.viewport()
        rect = vp.geometry()

        if rect.width() <= 0 or rect.height() <= 0:
            self.query_logo_bg.hide()
            return

        if self._query_logo_source and not self._query_logo_source.isNull():
            max_w = int(rect.width() * 0.82)
            max_h = int(rect.height() * 0.62)

            source = self._query_logo_source

            # Burada büyütme yapmıyoruz.
            # Logo strip tablo alanından büyükse küçültüyoruz,
            # küçükse olduğu gibi bırakıyoruz.
            if source.width() > max_w or source.height() > max_h:
                scaled = source.scaled(
                    QSize(max_w, max_h),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            else:
                scaled = source

            x = max(rect.x() + (rect.width() - scaled.width()) // 2, 0)
            y = max(rect.y() + (rect.height() - scaled.height()) // 2, 0)

            self.query_logo_bg.setGeometry(x, y, scaled.width(), scaled.height())
            self.query_logo_bg.setPixmap(scaled)
            self.query_logo_bg.show()
        else:
            self.query_logo_bg.clear()
            self.query_logo_bg.hide()

        self.query_logo_bg.lower()
        self.contract_table.raise_()
    
    def _scale_logo_smart(
        self,
        px: QPixmap,
        max_size: QSize,
        max_upscale: float = 3.0
    ) -> QPixmap:
        """
        Küçük logoları en fazla max_upscale kadar büyütür.
        Büyük logoları max_size içine sığacak şekilde küçültür.
        Oranı her zaman korur.
        """
        if not px or px.isNull():
            return px

        ow = max(px.width(), 1)
        oh = max(px.height(), 1)

        fit_scale = min(
            max_size.width() / ow,
            max_size.height() / oh
        )

        if fit_scale < 1:
            # Logo zaten büyükse küçült.
            scale = fit_scale
        else:
            # Logo küçükse en fazla 3 kat büyüt.
            scale = min(fit_scale, max_upscale)

        nw = max(1, int(ow * scale))
        nh = max(1, int(oh * scale))

        if nw == ow and nh == oh:
            return px

        return px.scaled(
            QSize(nw, nh),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_loading_overlay()
        self.position_query_logo_background()
        self.position_index_progress_badge()

    def position_index_progress_badge(self):
        if not hasattr(self, "index_progress_badge"):
            return
        parent = self.centralWidget()
        if not parent:
            return
        w, h = 138, 30
        margin = 12
        x = max(parent.width() - w - margin, 0)
        y = max(parent.height() - h - margin, 0)
        self.index_progress_badge.setGeometry(x, y, w, h)
        self.index_progress_badge.raise_()

    def set_index_progress_badge(self, visible: bool, percent: int = 0):
        if not hasattr(self, "index_progress_badge"):
            return
        p = int(max(0, min(100, int(percent or 0))))
        self.index_progress_badge.setText(f"Excel okuma %{p}")
        self.position_index_progress_badge()
        self.index_progress_badge.setVisible(bool(visible))

    def eventFilter(self, obj, event):
        if hasattr(self, "contract_table") and obj is self.contract_table.viewport():
            if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
                QTimer.singleShot(0, self.position_query_logo_background)
        return super().eventFilter(obj, event)

    def _norm_tr(self, s: str) -> str:
        t = str(s or "").strip().lower()
        return t.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")

    def _contract_health(self, it: dict) -> tuple[str, str, str, str]:
        """(cls, status_label, days_text, date_txt)
        status_label = Excel'deki gercek durum.
        cls = renk siniflandirmasi icin.
        """
        status_txt = str(it.get("status", "") or "").strip()
        completion_txt = str(it.get("completion_date", "") or "")
        acceptance_txt = str(it.get("acceptance_date", "") or "")
        today_iso = date.today().isoformat()
        cache_key = (status_txt, completion_txt, acceptance_txt, today_iso)
        if it.get("_health_cache_key") == cache_key and "_health_cache_value" in it:
            return it["_health_cache_value"]
        d = parse_iso_date(completion_txt)
        date_txt = d.strftime("%d.%m.%Y") if d else "-"
        days_text, day_num, timing_kind = contract_timing(completion_txt, acceptance_txt, status_txt)
        # Siniflandirma (renk ve uyari listeleri icin). Tamamlanmis gec
        # teslimatlar kirmizi gorunur ancak aktif gecikme uyarilarina girmez.
        if timing_kind == "gecikmeli_teslim":
            cls = "gecikmeli_teslim"
        elif is_completed_status(status_txt):
            cls = "tamamlandi"
        elif day_num is not None:
            cls = "geciken" if day_num < 0 else ("kritik" if day_num <= 60 else "normal")
        else:
            cls = "normal"
        # Gosterilecek etiket: Excel'deki gercek durum degeri
        st_label = status_txt if status_txt else "—"
        result = (cls, st_label, days_text, date_txt)
        it["_health_cache_key"] = cache_key
        it["_health_cache_value"] = result
        return result

    def _platform_logo_pixmap(self, platform: str, size: Optional[QSize] = None) -> Optional[QPixmap]:
        if not self.store:
            return None

        raw = self.store.get_platform_logo_bytes(platform)
        if not raw:
            return None

        px = QPixmap()
        if not px.loadFromData(raw):
            return None

        if size:
            return self._scale_logo_smart(px, size, max_upscale=3.0)

        return px

    def _build_query_logo_strip(self, platforms: List[str]) -> Optional[QPixmap]:
        logos: List[QPixmap] = []

        for p in platforms:
            raw = self._platform_logo_pixmap(p)

            if not raw or raw.isNull():
                continue

            # Küçük logo en fazla 3 kat büyür.
            # Büyük logo bu kutuya sığacak kadar küçülür.
            px = self._scale_logo_smart(
                raw,
                QSize(900, 300),
                max_upscale=3.0
            )

            if px and not px.isNull():
                logos.append(px)

        if not logos:
            return None

        spacing = 36
        padding_x = 30
        padding_y = 20

        width = sum(px.width() for px in logos) + spacing * (len(logos) - 1) + padding_x * 2
        height = max(px.height() for px in logos) + padding_y * 2

        canvas = QPixmap(width, height)
        canvas.fill(Qt.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        x = padding_x
        for px in logos:
            y = (height - px.height()) // 2
            painter.drawPixmap(x, y, px)
            x += px.width() + spacing

        painter.end()
        return canvas

    def update_query_logo_background(self, selected_platform: Optional[str] = None):
        if not hasattr(self, "query_logo_bg"):
            return
        if not self.store:
            self._query_logo_source = None
            self.query_logo_bg.hide()
            self.query_logo_bg.clear()
            return
        if selected_platform:
            targets = [str(selected_platform)]
        else:
            targets = self.store.platform_names()
        strip = self._build_query_logo_strip(targets)
        if not strip:
            self._query_logo_source = None
            self.query_logo_bg.hide()
            self.query_logo_bg.clear()
            return
        self._query_logo_source = strip
        self.position_query_logo_background()

    def _set_platform_items(self, platforms: List[str]):
        available = {str(p) for p in platforms}
        self.selected_platforms.intersection_update(available)
        if not self.selected_platforms:
            self.multi_platform_mode = False
        self._updating_platform_list = True
        try:
            self.platform_list.clear()
            counts: Dict[str, int] = {}
            for it in self.contract_index:
                p = str(it.get("platform", ""))
                counts[p] = counts.get(p, 0) + 1
            for p in platforms:
                platform = str(p)
                row = QListWidgetItem(f"{platform}   ({counts.get(platform, 0)})")
                row.setData(Qt.UserRole, platform)
                row.setSizeHint(QSize(0, 54))
                self.platform_list.addItem(row)
        finally:
            self._updating_platform_list = False
        self.refresh_platform_list_ui()

    def _all_platform_names(self) -> List[str]:
        return [
            str(self.platform_list.item(i).data(Qt.UserRole) or "")
            for i in range(self.platform_list.count())
            if str(self.platform_list.item(i).data(Qt.UserRole) or "")
        ]

    def normalize_platform_selection_state(self):
        if not self.selected_platforms:
            self.multi_platform_mode = False

    def refresh_platform_list_ui(self):
        self.normalize_platform_selection_state()
        self._updating_platform_list = True
        try:
            for i in range(self.platform_list.count()):
                item = self.platform_list.item(i)
                platform = str(item.data(Qt.UserRole) or "")
                flags = item.flags()
                if self.multi_platform_mode:
                    item.setFlags(flags | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if platform in self.selected_platforms else Qt.Unchecked)
                else:
                    item.setData(Qt.CheckStateRole, None)
                    item.setFlags(flags & ~Qt.ItemIsUserCheckable)
                item.setSelected(platform in self.selected_platforms)
        finally:
            self._updating_platform_list = False
        count = len(self.selected_platforms)
        self.platform_selection_badge.setText(f"{count} seçili")
        self.platform_selection_badge.setVisible(count > 0)
        self.platform_info_label.setText(f"{count} platform · sağ tık ile düzenle")
        self.platform_info_bar.setVisible(count > 0)

    def _apply_platform_selection(self):
        self.normalize_platform_selection_state()
        selected = set(self.selected_platforms)
        self.all_contract_rows = [
            dict(it) for it in self.contract_index
            if not selected or str(it.get("platform", "")) in selected
        ]
        self._prepare_contract_row_cache(self.all_contract_rows)
        self._refresh_query_filters()
        if not selected:
            self.right_title.setText("Sözleşme Sorgulama")
            self.update_query_logo_background(None)
        elif len(selected) == 1:
            platform = next(iter(selected))
            self.right_title.setText(f"{platform} - Sözleşmeler")
            self.update_query_logo_background(platform)
        else:
            self.right_title.setText(f"{len(selected)} Platform - Sözleşmeler")
            self.update_query_logo_background(None)
        self.refresh_platform_list_ui()
        self.schedule_apply_contract_filter()

    def on_platform_clicked(self, item: QListWidgetItem):
        platform = str(item.data(Qt.UserRole) or "")
        if not platform:
            return
        if self.multi_platform_mode:
            if self._platform_checkbox_changed == platform:
                self._platform_checkbox_changed = None
            else:
                self.toggle_platform_multi(platform)
        elif self.selected_platforms == {platform}:
            self.clear_platform_selection()
        else:
            self.selected_platforms = {platform}
            self._apply_platform_selection()

    def _on_platform_item_changed(self, item: QListWidgetItem):
        if self._updating_platform_list or not self.multi_platform_mode:
            return
        platform = str(item.data(Qt.UserRole) or "")
        checked = item.checkState() == Qt.Checked
        if checked != (platform in self.selected_platforms):
            self._platform_checkbox_changed = platform
            QTimer.singleShot(0, lambda p=platform: self._clear_platform_checkbox_marker(p))
            self.toggle_platform_multi(platform)

    def _clear_platform_checkbox_marker(self, platform: str):
        if self._platform_checkbox_changed == platform:
            self._platform_checkbox_changed = None

    def _on_platform_context_menu_requested(self, pos: QPoint):
        item = self.platform_list.itemAt(pos)
        if item:
            self.show_platform_context_menu(str(item.data(Qt.UserRole) or ""), self.platform_list.viewport().mapToGlobal(pos))

    def show_platform_context_menu(self, platform: str, global_pos: QPoint):
        if not platform:
            return
        menu = QMenu(self)
        label = "− Seçimden çıkar" if platform in self.selected_platforms else "+ Çoklu seçime ekle"
        menu.addAction(label, lambda: self.toggle_platform_multi(platform))
        menu.addAction("☑ Tümünü seç", self.select_all_platforms)
        menu.addAction("× Seçimi temizle", self.clear_platform_selection)
        menu.exec(global_pos)

    def toggle_platform_multi(self, platform: str):
        self.multi_platform_mode = True
        if platform in self.selected_platforms:
            self.selected_platforms.remove(platform)
        else:
            self.selected_platforms.add(platform)
        self.normalize_platform_selection_state()
        self._apply_platform_selection()

    def select_all_platforms(self):
        self.selected_platforms = set(self._all_platform_names())
        self.multi_platform_mode = bool(self.selected_platforms)
        self._apply_platform_selection()

    def clear_platform_selection(self):
        self.selected_platforms.clear()
        self.multi_platform_mode = False
        self._updating_platform_list = True
        try:
            for i in range(self.platform_list.count()):
                item = self.platform_list.item(i)
                item.setCheckState(Qt.Unchecked)
                item.setSelected(False)
        finally:
            self._updating_platform_list = False
        self._apply_platform_selection()

    def _clear_upcoming_layout(self):
        while self.upcoming_layout.count():
            item = self.upcoming_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def update_alert_strip(self):
        today = date.today()
        self.today_num.setText(str(today.day))
        self.today_info.setText(f"{TR_MONTHS[today.month - 1].upper()}\n{today.year}")

        overdue = []
        critical = []
        for it in self.contract_index:
            ctype = self._norm_tr(str(it.get("type", "") or ""))
            if ctype != self._norm_tr("Ana Sözleşme"):
                continue
            cls, _st, kgun, _dt = self._contract_health(it)
            if cls == "geciken":
                overdue.append((it, kgun))
            elif cls == "kritik":
                critical.append((it, kgun))
        self.overdue_count.setText(str(len(overdue)))
        self.critical_count.setText(str(len(critical)))

        show_overdue = len(overdue) > 0
        show_critical = len(critical) > 0
        self.alert_overdue_group.setVisible(show_overdue)
        self.alert_critical_group.setVisible(show_critical)
        self.alert_divider1.setVisible(show_overdue or show_critical)
        self.alert_divider2.setVisible(show_overdue or show_critical)

        self._clear_upcoming_layout()
        upcoming = overdue[:5] + critical[:10]
        for it, kgun in upcoming:
            p = str(it.get("platform", "") or "")
            no = str(it.get("no", "") or "")
            cls, _st, _kg, _dt = self._contract_health(it)
            b = QPushButton(f"• #{no} · {p} · {kgun}")
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("kind", "red" if cls == "geciken" else "amber")
            b.setObjectName("upcomingPill")
            b.clicked.connect(lambda _=False, item=dict(it): self.open_contract_item(item))
            self.upcoming_layout.addWidget(b)
        self.upcoming_layout.addStretch()

    def set_empty_state(self):
        self.platform_list.clear()
        self.selected_platforms.clear()
        self.multi_platform_mode = False
        if hasattr(self, "platform_selection_badge"):
            self.refresh_platform_list_ui()
        self.all_contract_rows = []
        self.contract_table.setRowCount(0)
        self.set_index_progress_badge(False, 0)
        self.overdue_count.setText("0")
        self.critical_count.setText("0")
        self.alert_overdue_group.hide()
        self.alert_critical_group.hide()
        self.alert_divider1.hide()
        self.alert_divider2.hide()
        self._clear_upcoming_layout()
        self.upcoming_layout.addStretch()
        self.right_title.setText("Sözleşme Sorgulama")
        self.update_query_logo_background(None)
        self.update_connection_badge("bad")

    def set_loading_state(self, loading: bool, message: str = "Analiz ediliyor..."):
        self._loading = loading
        if loading:
            self.loading_label.setText(message)
            self.loading_progress.setRange(0, 100)
            self.loading_progress.setValue(0)
            self.position_loading_overlay()
            self.loading_overlay.show()
            self.update_connection_badge("loading")
        else:
            self.loading_progress.setValue(100)
            self.loading_overlay.hide()
            self.update_connection_badge("ok" if self.store else "bad")

    def set_busy_overlay(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        # Excel worker yüklemesi yokken kısa/orta süreli senkron işlemlerde kullan.
        if not hasattr(self, "_busy_cursor_on"):
            self._busy_cursor_on = False
        if visible:
            self.loading_label.setText(message)
            self.loading_progress.setRange(0, 100)
            self.loading_progress.setValue(int(max(0, min(100, percent))))
            self.position_loading_overlay()
            self.loading_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.loading_overlay.hide()
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    def start_excel_load(self, path: Path):
        if self._loader_thread and self._loader_thread.isRunning():
            return
        self.path = Path(path)
        self.store = None
        self.contract_index = []
        self.all_contract_rows = []
        self.selected_platforms.clear()
        self.multi_platform_mode = False
        self._store_loading = True
        self._index_ready_for_use = False
        self._last_load_timings = {}
        self._version_baseline_signature = None
        if hasattr(self, "platform_list"):
            self.platform_list.clear()
            self.refresh_platform_list_ui()
        if hasattr(self, "contract_table"):
            self.contract_table.setRowCount(0)
        self._streaming_index = False
        self.set_index_progress_badge(True, 0)
        self.set_loading_state(True, "Analiz ediliyor...")
        self._loader_thread = QThread(self)
        self._loader_worker = ExcelLoadWorker(self.path)
        self._loader_worker.moveToThread(self._loader_thread)
        self._loader_thread.started.connect(self._loader_worker.run)
        self._loader_worker.store_ready.connect(self.on_excel_store_ready)
        self._loader_worker.batch_ready.connect(self.on_excel_index_batch)
        self._loader_worker.index_ready.connect(self.on_excel_index_ready)
        self._loader_worker.finished.connect(self.on_excel_loaded)
        self._loader_worker.failed.connect(self.on_excel_load_failed)
        self._loader_worker.progress.connect(self.on_excel_load_progress)
        self._loader_worker.finished.connect(self._loader_thread.quit)
        self._loader_worker.failed.connect(self._loader_thread.quit)
        self._loader_thread.finished.connect(self._loader_worker.deleteLater)
        self._loader_thread.finished.connect(self._loader_thread.deleteLater)
        self._loader_thread.finished.connect(self._clear_loader_refs)
        self._loader_thread.start()


    def start_sts_load(self, path: Path):
        self.path = Path(path)
        self.store = STSStore(self.path)
        self.contract_index = self.store.build_contract_index()
        self._tag_color_map_cache = None
        self._set_platform_items(self.store.platform_names())
        self.update_alert_strip()
        self._apply_platform_selection()
        self.connection_label.setText("✓ STS veri dosyası bağlı")

    def is_sts_mode(self) -> bool:
        return (
            self.store is not None
            and self.path is not None
            and str(self.path).lower().endswith(".sts")
        )

    def _clear_loader_refs(self):
        self._loader_worker = None
        self._loader_thread = None

    def _refresh_index_tags_only(self):
        if not self.store:
            return
        tags_map = self.store.all_contract_tags_map()
        for it in self.contract_index:
            p = str(it.get("platform", "") or "").strip()
            no = str(it.get("no", "") or "").strip()
            ctype = str(it.get("type", "") or "").strip()
            tags = tags_map.get((p, no, ctype), [])
            it["tags"] = list(tags)
            search = " ".join(
                str(it.get(k, "") or "")
                for k in ["platform", "no", "user", "type", "link", "status", "completion_date", "content"]
            ).lower()
            if tags:
                search = (search + " " + " ".join(tags).lower()).strip()
            it["search"] = search

    def _rebuild_index_in_platform_order(self, platform_rows: Dict[str, List[dict]]):
        if not self.store:
            self.contract_index = []
            return
        ordered: List[dict] = []
        for p in self.store.platform_names():
            ordered.extend([dict(it) for it in platform_rows.get(p, [])])
        self.contract_index = ordered

    def _refresh_single_platform_index(self, platform: str, select_platform: Optional[str] = None):
        if not self.store:
            self.set_empty_state()
            return
        p = safe_sheet_name(str(platform or ""))
        if not p:
            self.request_refresh(select_platform=select_platform, scope="all")
            return
        current_rows: Dict[str, List[dict]] = {}
        for it in self.contract_index:
            pp = str(it.get("platform", "") or "")
            current_rows.setdefault(pp, []).append(dict(it))
        self.set_busy_overlay(True, f"{p} güncelleniyor...", 25)
        try:
            QApplication.processEvents()
            tags_map = self.store.all_contract_tags_map()
            self.set_busy_overlay(True, "Sözleşme satırları okunuyor...", 62)
            QApplication.processEvents()
            current_rows[p] = self.store.list_main_contracts(p, tags_map=tags_map)
            self._rebuild_index_in_platform_order(current_rows)
            self.set_busy_overlay(True, "Arayüz yenileniyor...", 92)
            QApplication.processEvents()
            platforms = self.store.platform_names()
            self._set_platform_items(platforms)
            self.update_alert_strip()
            self.refresh_open_calendar()
            target = str(select_platform or p)
            if target:
                self.select_platform(target)
            elif self.platform_list.count():
                self._apply_platform_selection()
            else:
                self.set_empty_state()
        finally:
            self.set_busy_overlay(False)


    def refresh_open_calendar(self):
        cal = getattr(self, "calendar_window", None)
        if not cal or not cal.isVisible():
            return
        try:
            cal.refresh_from_index(self.store, self.contract_index)
        except RuntimeError:
            self.calendar_window = None

    def request_refresh(self, select_platform: Optional[str] = None, scope: str = "all", platform: Optional[str] = None):
        if not self.store:
            self.set_empty_state()
            return
        kind = str(scope or "all").strip().lower()
        if kind == "all":
            if self.is_sts_mode():
                self.contract_index = self.store.build_contract_index()
                self._set_platform_items(self.store.platform_names())
                self.update_alert_strip()
                self.refresh_open_calendar()
                if select_platform:
                    self.select_platform(select_platform)
                else:
                    self._apply_platform_selection()
                self.connection_label.setText("✓ STS veri dosyası bağlı")
                return
            self._pending_select_platform = select_platform
            self.start_excel_load(self.path)
            return
        if kind == "tags":
            self.set_busy_overlay(True, "Etiketler güncelleniyor...", 35)
            try:
                self._refresh_index_tags_only()
                self.set_busy_overlay(True, "Arayüz yenileniyor...", 90)
                self._set_platform_items(self.store.platform_names())
                self.update_alert_strip()
                self.refresh_open_calendar()
                if select_platform:
                    self.select_platform(select_platform)
                else:
                    self._apply_platform_selection()
            finally:
                self.set_busy_overlay(False)
            return
        if kind == "platform":
            self._refresh_single_platform_index(str(platform or select_platform or ""), select_platform=select_platform or platform)
            return
        # UI-only yenileme: tekrar excel indeks okumadan görünümü tazeler.
        self._set_platform_items(self.store.platform_names())
        self.update_alert_strip()
        self.refresh_open_calendar()
        if self.platform_list.count():
            self._apply_platform_selection()
        else:
            self.set_empty_state()

    def on_excel_store_ready(self, store):
        self.store = store
        self.path = self.store.path
        self.contract_index = []
        self._tag_color_map_cache = None
        self._streaming_index = True
        self.loading_overlay.hide()
        self._loading = False
        self.update_connection_badge("loading")
        self.connection_label.setText("Excel indeksleniyor %0")
        self.set_index_progress_badge(True, 0)
        platforms = self.store.platform_names()
        self._set_platform_items(platforms)
        self.update_alert_strip()
        self._apply_platform_selection()

    def on_excel_index_batch(self, platform: str, rows, mapped_percent: int, message: str):
        new_rows = [dict(it) for it in list(rows or [])]
        self.set_index_progress_badge(True, int(mapped_percent or 0))
        if not new_rows:
            self.connection_label.setText(f"Excel indeksleniyor %{int(mapped_percent or 0)}")
            return
        self.contract_index.extend(new_rows)
        self.connection_label.setText(f"Excel indeksleniyor %{int(mapped_percent or 0)}")
        if self.store:
            self._apply_platform_selection()

    def on_excel_index_ready(self, platforms, index, timings):
        self.contract_index = list(index or [])
        self._last_load_timings = dict(timings or {})
        self._tag_color_map_cache = None
        self._streaming_index = False
        self._loading = False
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.hide()
        self._index_ready_for_use = True
        self.update_connection_badge("ok")
        self.connection_label.setText("Liste hazır (detay düzenleme arka planda hazırlanıyor)")
        self.set_index_progress_badge(False, 100)
        platform_list = list(platforms or [])
        self._set_platform_items(platform_list)
        self.update_alert_strip()
        self.refresh_open_calendar()
        if self._pending_select_platform:
            self.select_platform(self._pending_select_platform)
        elif self.platform_list.count():
            self._apply_platform_selection()
        else:
            self.contract_table.setRowCount(0)

    def on_excel_loaded(self, store, index):
        selected_platform = next(iter(self.selected_platforms)) if len(self.selected_platforms) == 1 else ""
        self.store = store
        self.contract_index = list(index or [])
        self.path = self.store.path
        self._tag_color_map_cache = None
        self._store_loading = False
        self._index_ready_for_use = False
        self.set_loading_state(False)
        self.set_index_progress_badge(False, 100)
        self._streaming_index = False
        self.refresh(rebuild_index=False)
        self.refresh_open_calendar()
        if self._pending_select_platform:
            self.select_platform(self._pending_select_platform)
        elif selected_platform:
            self.select_platform(selected_platform)
        self._pending_select_platform = None
        self._apply_version_to_ui()
        self._remember_version_baseline()

    def on_excel_load_failed(self, error_text: str):
        self._store_loading = False
        self._index_ready_for_use = False
        self.set_loading_state(False)
        self.set_index_progress_badge(False, 0)
        self.set_empty_state()
        self._pending_select_platform = None
        QMessageBox.critical(self, "Excel yükleme hatası", f"Excel dosyası okunamadı.\n\n{error_text}")

    def on_excel_load_progress(self, percent: int, message: str):
        p = int(max(0, min(100, int(percent or 0))))
        msg = str(message or "Analiz ediliyor...")
        self.set_index_progress_badge(True, p)
        if self._loading and hasattr(self, "loading_progress"):
            self.loading_progress.setRange(0, 100)
            self.loading_progress.setValue(p)
        if self._loading and hasattr(self, "loading_label"):
            self.loading_label.setText(f"{msg}  %{p}")
        elif getattr(self, "_store_loading", False):
            if self._index_ready_for_use:
                self.update_connection_badge("ok")
                self.connection_label.setText("Liste hazır (detay düzenleme arka planda hazırlanıyor)")
            else:
                self.update_connection_badge("loading")
                self.connection_label.setText(f"{msg} %{p}")
        elif self.store:
            self.update_connection_badge("loading")
            self.connection_label.setText(f"Excel indeksleniyor %{p}")

    def on_contract_save_progress(self, percent: int, message: str):
        self.set_busy_overlay(True, message, percent)

    def open_file(self):
        dlg = WorkbookStartDialog(self)
        if dlg.exec() and dlg.selected_path:
            sel = Path(dlg.selected_path)
            if sel.suffix.lower() == ".sts":
                self.start_sts_load(sel)
            else:
                self.start_excel_load(sel)

    def show_contract_summary(self, row: int, item: dict):
        if not self.store:
            return
        old_popup = getattr(self, "_summary_popup", None)
        if old_popup and old_popup.isVisible():
            old_popup.close()

        dialog = ContractSummaryDialog(
            self.store,
            item,
            self,
            detail_handler=self.open_summary_event_detail,
        )
        self._summary_popup = dialog
        dialog.destroyed.connect(lambda *_: setattr(self, "_summary_popup", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_summary_event_detail(self, item: dict) -> bool:
        self.open_contract_item(item)
        return True

    def _on_contract_cell_clicked(self, row: int, col: int):
        """Ozet hucresine tiklayinca popup ac.
        Col disi tiklama open_selected_contract ile cakismasin.
        """
        if col != COL_SUMMARY:
            return
        rows = getattr(self.contract_table, "_visible_rows", [])
        if row < 0 or row >= len(rows):
            return
        self.show_contract_summary(row, rows[row])

    def manage_platforms(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        dlg = PlatformManagerDialog(self.store, self)
        saved_via_signal = False

        def refresh_after_platform_save():
            nonlocal saved_via_signal
            saved_via_signal = True
            current = self.platform_list.currentItem() if hasattr(self, "platform_list") else None
            current_platform = str(current.data(Qt.UserRole) or "") if current else None
            self.request_refresh(select_platform=current_platform, scope="all")

        dlg.settings_saved.connect(refresh_after_platform_save)
        dlg.exec()
        if dlg.changed and not saved_via_signal:
            refresh_after_platform_save()

    def create_platform(self):
        """Eski uyumluluk - manage_platforms'u cagirir."""
        self.manage_platforms()

    def manage_users(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        dlg=UserManagerDialog(self.store,self)
        if dlg.exec():
            self.request_refresh(scope="ui")

    def manage_tags(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        dlg = TagManagerDialog(self.store, self.contract_index, self)
        dlg.exec()
        if dlg.changed:
            self._tag_color_map_cache = None
            current_platform = ""
            cur = self.platform_list.currentItem()
            if cur:
                current_platform = str(cur.data(Qt.UserRole) or "")
            self.request_refresh(select_platform=current_platform, scope="tags")

    def manage_components(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        dlg=ComponentManagerDialog(self.store,self)
        if dlg.exec():
            self.request_refresh(scope="ui")


    def open_calendar_tracking(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        self.set_busy_overlay(True, "Takvim hazırlanıyor...")
        try:
            self.calendar_window = ContractCalendarWindow(
                self.store, self.contract_index, self, detail_handler=self.open_calendar_event_detail
            )
        finally:
            self.set_busy_overlay(False)
        self.calendar_window.showMaximized()
        self.calendar_window.show()
        self.calendar_window.raise_()
        self.calendar_window.activateWindow()


    def open_calendar_event_detail(self, ev: dict) -> bool:
        platform = str(ev.get("platform", "") or "")
        no = str(ev.get("no", "") or "")
        row = int(ev.get("row", 0) or 0)
        ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=row if row > 0 else None)
        if not ci:
            QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayları okunamadı.")
            return False
        work = ContractWorkWindow(self.store, ci, self, systems=systems, deliveries=deliveries)
        return bool(work.exec())

    def new_contract(self):
        if not self.store:
            QMessageBox.information(self, "Excel gerekli", "Önce bir Excel dosyası bağlayın.")
            return
        if not self.store.load_users():
            QMessageBox.information(self, "Kullanıcı gerekli", "Sözleşme girmeden önce kullanıcı tanımlayın.")
            udlg = UserManagerDialog(self.store, self)
            if not udlg.exec() or not self.store.load_users():
                return
        dlg=ContractDialog(self.store,self)
        if dlg.exec() and dlg.result:
            work=ContractWorkWindow(self.store,dlg.result,self)
            if work.exec():
                self.request_refresh(
                    select_platform=dlg.result.platform,
                    scope="platform",
                    platform=dlg.result.platform,
                )

    def refresh(self, rebuild_index: bool = True):
        if not self.store:
            self.set_empty_state()
            return
        # Kayıttan sonra indeks tek seferde yenilenir; arama bu indeks üzerinden yapılır.
        if rebuild_index:
            self.contract_index = self.store.build_contract_index()
        if self.is_sts_mode():
            self.connection_label.setText("✓ STS veri dosyası bağlı")
        platforms = self.store.platform_names()
        self._set_platform_items(platforms)
        self.update_query_logo_background(None)
        self.update_alert_strip()
        self.refresh_open_calendar()
        self._apply_platform_selection()

    def select_platform(self, p):
        platform = str(p or "")
        if platform and platform in self._all_platform_names():
            self.selected_platforms = {platform}
            self.multi_platform_mode = False
            self._apply_platform_selection()

    def load_platform_contracts(self, platform):
        self.select_platform(platform)

    def toggle_filter_bar(self):
        visible = not self.filter_bar.isVisible()
        self.filter_bar.setVisible(visible)
        sender = self.sender()
        if visible:
            if sender is self.sort_btn:
                self.sort_combo.setFocus()
            else:
                self.filter_type.setFocus()

    def clear_query_filters(self):
        self.search_input.clear()
        if hasattr(self, "date_from_filter"):
            self._date_from_active = False
            self.date_from_filter.setDate(QDate.currentDate())
        if hasattr(self, "date_to_filter"):
            self._date_to_active = False
            self.date_to_filter.setDate(QDate.currentDate())
        if hasattr(self, "days_min_filter"):
            self.days_min_filter.clear()
        if hasattr(self, "days_max_filter"):
            self.days_max_filter.clear()
        if hasattr(self, 'filter_type'):
            self.filter_type.setCurrentIndex(0)
        if hasattr(self, 'filter_status'):
            self.filter_status.setCurrentIndex(0)
        if hasattr(self, 'sort_combo'):
            self.sort_combo.setCurrentIndex(0)
        # Sutun filtrelerini temizle
        if hasattr(self, '_filter_header'):
            self._filter_header.clear_all_filters()
        self.schedule_apply_contract_filter()

    def _on_date_filter_changed(self, which: str):
        if which == "from":
            self._date_from_active = True
        else:
            self._date_to_active = True
        self.schedule_apply_contract_filter()

    def _refresh_query_filters(self):
        type_vals = sorted(
            {str(it.get("type_display", it.get("type", "")) or "").strip() for it in self.all_contract_rows if str(it.get("type_display", it.get("type", "")) or "").strip()},
            key=self._norm_tr,
        )
        self.filter_type.blockSignals(True)
        self.filter_type.clear()
        self.filter_type.addItem("Tüm Türler", "")
        for tv in type_vals:
            self.filter_type.addItem(tv, tv)
        self.filter_type.blockSignals(False)

    def _contract_no_sort_key(self, no_text: str):
        txt = str(no_text or "").strip()
        if txt.isdigit():
            return (0, int(txt), txt.lower())
        parts = re.split(r"(\d+)", txt.lower())
        key = []
        for p in parts:
            if p.isdigit():
                key.append((0, int(p)))
            else:
                key.append((1, p))
        return (1, key)

    def _completion_date_sort_key(self, it: dict):
        d = parse_iso_date(str(it.get("completion_date", "") or ""))
        if d:
            return (0, d.toordinal())
        return (1, 99999999)

    def _days_sort_key(self, it: dict):
        day_num = it.get("_day_num")
        if day_num is not None:
            return (0, int(day_num))
        return (1, 99999999)

    def _prepare_contract_row_cache(self, rows: List[dict]):
        today = date.today()
        for it in rows:
            completion_txt = str(it.get("completion_date", "") or "")
            completion = parse_iso_date(completion_txt)
            it["_completion_obj"] = completion
            it["_completion_ord"] = completion.toordinal() if completion else None
            _days_text, day_num, _timing_kind = contract_timing(
                completion_txt,
                str(it.get("acceptance_date", "") or ""),
                str(it.get("status", "") or ""),
                today=today,
            )
            it["_day_num"] = day_num
            tags_list = list(it.get("tags", []) or [])
            it["_tags_str"] = ", ".join(tags_list) if tags_list else ""
            hay = it.get("search") or " ".join(str(it.get(k, "")) for k in ["platform", "no", "user", "status", "completion_date", "content"]).lower()
            it["_search_norm"] = str(hay or "").lower()

    def schedule_apply_contract_filter(self):
        if not hasattr(self, "_filter_apply_timer"):
            self.apply_contract_filter()
            return
        self._filter_apply_timer.start(180)

    def apply_contract_filter(self):
        q = (self.search_input.text() if hasattr(self, "search_input") else "").strip().lower()
        selected_type = str(self.filter_type.currentData() or "").strip() if hasattr(self, "filter_type") else ""
        selected_status = str(self.filter_status.currentData() or "").strip() if hasattr(self, "filter_status") else ""
        sort_mode = str(self.sort_combo.currentData() or "default")
        # Kalan Gun kolonundan gelen siralama sort_combo'yu ezer
        tbl_sort = getattr(getattr(self, 'contract_table', None), '_sort_mode', 'default')
        if tbl_sort != 'default':
            sort_mode = tbl_sort
        rows = []
        date_from = None
        date_to = None
        if hasattr(self, "date_from_filter") and getattr(self, "_date_from_active", False):
            date_from = self.date_from_filter.date().toPython()
        if hasattr(self, "date_to_filter") and getattr(self, "_date_to_active", False):
            date_to = self.date_to_filter.date().toPython()
        days_min = None
        days_max = None
        if hasattr(self, "days_min_filter"):
            txt = self.days_min_filter.text().strip()
            if txt:
                try:
                    days_min = int(txt)
                except ValueError:
                    days_min = None
        if hasattr(self, "days_max_filter"):
            txt = self.days_max_filter.text().strip()
            if txt:
                try:
                    days_max = int(txt)
                except ValueError:
                    days_max = None
        if hasattr(self, "contract_table"):
            self.contract_table._all_rows_for_filter = list(getattr(self, "all_contract_rows", []))
        # Sutun filtreleri
        col_filters = {}
        date_ranges = {}
        day_ranges = {}
        if hasattr(self, '_filter_header'):
            col_filters = dict(self._filter_header._col_filters)
            date_ranges = dict(getattr(self._filter_header, "_date_ranges", {}))
            day_ranges = dict(getattr(self._filter_header, "_day_ranges", {}))
        selected_platforms = set(getattr(self, "selected_platforms", set()))
        for it in getattr(self, "all_contract_rows", []):
            if selected_platforms and str(it.get("platform", "")) not in selected_platforms:
                continue
            hay = str(it.get("_search_norm") or "")
            if q and q not in hay:
                continue
            tval = str(it.get("type_display", it.get("type", "")) or "").strip()
            if selected_type and tval != selected_type:
                continue
            cls, st_label, _days, _dt = self._contract_health(it)
            if selected_status and cls != selected_status:
                continue
            completion = it.get("_completion_obj")
            if date_from and (not completion or completion < date_from):
                continue
            if date_to and (not completion or completion > date_to):
                continue
            day_num = it.get("_day_num")
            if days_min is not None and (day_num is None or day_num < days_min):
                continue
            if days_max is not None and (day_num is None or day_num > days_max):
                continue
            if COL_T_DATE in date_ranges:
                start_date, end_date = date_ranges.get(COL_T_DATE, (None, None))
                if start_date and (not completion or completion < start_date):
                    continue
                if end_date and (not completion or completion > end_date):
                    continue
            if COL_REMAINING in day_ranges:
                min_day, max_day = day_ranges.get(COL_REMAINING, (None, None))
                if min_day is not None and (day_num is None or day_num < min_day):
                    continue
                if max_day is not None and (day_num is None or day_num > max_day):
                    continue
            # Sutun bazli filtreler (0=Platform,1=Tur,2=No,3=User,4=Durum,5=Tarih,6=Gun,7=Etiketler,8=Ozet)
            tags_str = str(it.get("_tags_str") or "")
            col_vals = [
                str(it.get("platform", "") or ""),
                str(it.get("type_display", it.get("type", "")) or ""),
                str(it.get("no", "") or ""),
                str(it.get("user", "") or ""),
                st_label,
                _dt,
                _days,
                tags_str,
                "Özet",
            ]
            skip = False
            for ci, fset in col_filters.items():
                if fset is None:
                    continue

                # Etiketler kolonu için özel kontrol:
                # seçilen etiketlerden en az biri satırdaki etiketlerde varsa geçir.
                if ci == COL_TAGS:
                    row_tags = [str(t or "").strip() for t in list(it.get("tags", []) or []) if str(t or "").strip()]
                    if not any(tag in fset for tag in row_tags):
                        skip = True
                        break
                    continue

                if ci < len(col_vals):
                    if col_vals[ci] not in fset:
                        skip = True
                        break

            if skip:
                continue
            rows.append(it)

        if sort_mode == "no_asc":
            rows.sort(key=lambda x: self._contract_no_sort_key(x.get("no", "")))
        elif sort_mode == "no_desc":
            rows.sort(key=lambda x: self._contract_no_sort_key(x.get("no", "")), reverse=True)
        elif sort_mode == "date_asc":
            rows.sort(key=self._completion_date_sort_key)
        elif sort_mode == "date_desc":
            rows.sort(key=self._completion_date_sort_key, reverse=True)
        elif sort_mode == "days_asc":
            rows.sort(key=self._days_sort_key)
        elif sort_mode == "days_desc":
            rows.sort(key=self._days_sort_key, reverse=True)
        elif sort_mode == "user_asc":
            rows.sort(key=lambda x: self._norm_tr(str(x.get("user", ""))))
        elif sort_mode == "user_desc":
            rows.sort(key=lambda x: self._norm_tr(str(x.get("user", ""))), reverse=True)

        # Etiket renk haritası (performans için bir kez yükle)
        if self._tag_color_map_cache is None:
            tag_color_map: Dict[str, str] = {}
            if self.store:
                try:
                    for td in self.store.load_tag_defs():
                        tag_color_map[self.store._normalize_label(td.name)] = td.color or "#3B82F6"
                except Exception:
                    pass
            self._tag_color_map_cache = tag_color_map
        _tag_color_map = self._tag_color_map_cache

        self.contract_table.setUpdatesEnabled(False)
        self.contract_table.blockSignals(True)
        try:
            self.contract_table.clearContents()
            self.contract_table.setRowCount(len(rows))
            self.contract_table._visible_rows = rows
            for r,it in enumerate(rows):
                for c in range(self.contract_table.columnCount()):
                    self.contract_table.removeCellWidget(r, c)
                self.contract_table.setRowHeight(r, 36)
                cls, st_label, days_text, tdate = self._contract_health(it)
                payload = {
                    "platform": str(it.get("platform", "") or ""),
                    "contract_no": str(it.get("no", "") or ""),
                    "contract_type": str(it.get("type_display", it.get("type", "")) or ""),
                    "contract_item": it,
                }
                vals=[
                    it.get("platform", ""),
                    it.get("type_display", it.get("type", "")) or "",
                    it.get("no", ""),
                    it.get("user", ""),
                    st_label,
                    tdate,
                    days_text,
                    None,  # col 7: Etiketler widget
                    None,  # col 8: Ozet butonu
                ]
                for c,v in enumerate(vals):
                    if c == COL_TAGS:
                        # Etiketler: dikey sıralı renkli chip'ler
                        tags_list = list(it.get("tags", []) or [])
                        if not tags_list:
                            empty = QTableWidgetItem("")
                            empty.setFlags(empty.flags() & ~Qt.ItemIsEditable)
                            empty.setData(Qt.UserRole, payload)
                            self.contract_table.setItem(r, COL_TAGS, empty)
                            self.contract_table.setRowHeight(r, max(self.contract_table.rowHeight(r), 36))
                            continue
                        wrap = QWidget()
                        wrap.setStyleSheet("QWidget{background:transparent;border:0px;}")
                        wl = QVBoxLayout(wrap)
                        wl.setContentsMargins(5, 4, 5, 4)
                        wl.setSpacing(3)
                        wl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                        for tag_name in tags_list:
                            color = _tag_color_map.get(self.store._normalize_label(tag_name) if self.store else tag_name, "#3B82F6")
                            base_rgb = _hex_to_rgb(color)
                            bg = _mix_rgb(base_rgb, (255, 255, 255), 0.78)
                            border_c = _mix_rgb(base_rgb, (255, 255, 255), 0.28)
                            txt_c = _rgb_to_hex(_mix_rgb(base_rgb, (15, 23, 42), 0.22))
                            chip = QLabel(tag_name)
                            chip.setStyleSheet(
                                f"QLabel{{background:{_rgb_to_hex(bg)};color:{txt_c};"
                                f"border:1px solid {_rgb_to_hex(border_c)};border-radius:9px;"
                                f"padding:2px 8px;font-size:11px;font-weight:700;}}"
                            )
                            wl.addWidget(chip)
                        placeholder = QTableWidgetItem("")
                        placeholder.setData(Qt.UserRole, payload)
                        self.contract_table.setItem(r, COL_TAGS, placeholder)
                        self.contract_table.setCellWidget(r, COL_TAGS, wrap)
                        # Satır yüksekliğini etiket sayısına göre ayarla
                        CHIP_H, CHIP_SP, PAD = 22, 3, 8
                        n = len(tags_list)
                        row_h = max(36, n * CHIP_H + max(0, n - 1) * CHIP_SP + PAD) if n > 0 else 36
                        self.contract_table.setRowHeight(r, max(self.contract_table.rowHeight(r), row_h))
                        continue
                    if c == COL_SUMMARY:
                        lbl = QLabel("\U0001F50D")
                        lbl.setAlignment(Qt.AlignCenter)
                        lbl.setToolTip("Bileşen özetini gör")
                        lbl.setStyleSheet(
                            "QLabel{font-size:16px;color:#185FA5;background:transparent;border:0px;}"
                            "QLabel:hover{color:#042C53;}"
                        )
                        wrap = QWidget()
                        wrap.setStyleSheet("QWidget{background:transparent;border:0px;}")
                        wl = QHBoxLayout(wrap)
                        wl.setContentsMargins(0,0,0,0)
                        wl.setSpacing(0)
                        wl.setAlignment(Qt.AlignCenter)
                        wl.addWidget(lbl)
                        placeholder = QTableWidgetItem("")
                        placeholder.setData(Qt.UserRole, payload)
                        self.contract_table.setItem(r, COL_SUMMARY, placeholder)
                        self.contract_table.setCellWidget(r, COL_SUMMARY, wrap)
                        continue
                    cell = QTableWidgetItem(str(v or ""))
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                    cell.setData(Qt.UserRole, payload)
                    if c == COL_STATUS:
                        if cls in {"geciken", "gecikmeli_teslim"}:
                            cell.setForeground(QColor("#dc2626"))
                        elif cls == "kritik":
                            cell.setForeground(QColor("#b45309"))
                        elif cls == "tamamlandi":
                            cell.setForeground(QColor("#047857"))
                        else:
                            cell.setForeground(QColor("#1f5be3"))
                    if c == COL_REMAINING:
                        if cls in {"geciken", "gecikmeli_teslim"}:
                            cell.setForeground(QColor("#dc2626"))
                        elif "erken teslim edildi" in str(v):
                            cell.setForeground(QColor("#047857"))
                        elif str(v) in {"Termin gününde teslim edildi", "Teslim tarihi yok", "—"}:
                            cell.setForeground(QColor("#64748b"))
                        elif str(v).endswith("gün"):
                            days_num = as_number(str(v).replace(" gün", ""))
                            if days_num <= 60:
                                cell.setForeground(QColor("#b45309"))
                            else:
                                cell.setForeground(QColor("#1f5be3"))
                        else:
                            cell.setForeground(QColor("#047857"))
                    self.contract_table.setItem(r,c,cell)
        finally:
            self.contract_table.blockSignals(False)
            self.contract_table.setUpdatesEnabled(True)
        self.position_query_logo_background()

    def open_contract_item(self, item: dict):
        if not self.store:
            if getattr(self, "_store_loading", False):
                QMessageBox.information(
                    self,
                    "Excel hazırlanıyor",
                    "Liste hazır. Sözleşme detayı için Excel düzenleme modu birkaç saniye içinde hazır olacak.",
                )
            return
        platform = item.get("platform")
        no = item.get("no")
        start_row = item.get("row")
        self.set_busy_overlay(True, "Sözleşme detayı yükleniyor...")
        try:
            ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=start_row)
        finally:
            self.set_busy_overlay(False)
        if not ci:
            QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayları okunamadı.")
            return
        work = ContractWorkWindow(self.store, ci, self, systems=systems, deliveries=deliveries)
        if work.exec():
            deleted_info = getattr(work, "deleted_contract_info", None)
            if deleted_info:
                # Silme sonrası tam excel indeksini yeniden kurmak (binlerce satırda)
                # gereksiz uzun sürüyor. Mevcut indeksi yerinde güncelleriz.
                self.set_busy_overlay(True, "Liste güncelleniyor...", 82)
                try:
                    self._apply_deleted_contract_to_index(deleted_info)
                    self.set_busy_overlay(True, "Arayüz yenileniyor...", 96)
                    platforms = self.store.platform_names()
                    self._set_platform_items(platforms)
                    self.update_alert_strip()
                    if str(platform or "") in platforms:
                        self.select_platform(platform)
                    elif self.platform_list.count():
                        self._apply_platform_selection()
                    else:
                        self.set_empty_state()
                finally:
                    self.set_busy_overlay(False)
            else:
                old_platform = str(platform or "")
                work_ci = getattr(work, "ci", None)
                new_platform = str(getattr(work_ci, "platform", "") or old_platform)
                if old_platform and new_platform and old_platform != new_platform:
                    self.request_refresh(select_platform=old_platform, scope="platform", platform=old_platform)
                    self.request_refresh(select_platform=new_platform, scope="platform", platform=new_platform)
                    self.select_platform(new_platform)
                else:
                    target = new_platform or old_platform
                    self.request_refresh(select_platform=target, scope="platform", platform=target)

    def open_selected_contract(self, row, col):
        rows = getattr(self.contract_table, "_visible_rows", [])
        if row < 0 or row >= self.contract_table.rowCount():
            return
        if col == COL_SUMMARY:
            if row < len(rows):
                self.show_contract_summary(row, rows[row])
            return
        payload = None
        for column in range(self.contract_table.columnCount()):
            cell = self.contract_table.item(row, column)
            candidate = cell.data(Qt.UserRole) if cell else None
            if isinstance(candidate, dict) and candidate.get("contract_no"):
                payload = candidate
                break
        if payload and isinstance(payload.get("contract_item"), dict):
            self.open_contract_item(payload["contract_item"])
            return
        if row < len(rows):
            self.open_contract_item(rows[row])
            return
        platform_item = self.contract_table.item(row, COL_PLATFORM)
        type_item = self.contract_table.item(row, COL_TYPE)
        no_item = self.contract_table.item(row, COL_CONTRACT_NO)
        self.open_contract_item({
            "platform": platform_item.text() if platform_item else "",
            "type": type_item.text() if type_item else "",
            "no": no_item.text() if no_item else "",
        })

    def _apply_deleted_contract_to_index(self, deleted_info: dict):
        p = str((deleted_info or {}).get("platform") or "")
        no = str((deleted_info or {}).get("contract_no") or "").strip()
        start = int((deleted_info or {}).get("start_row") or 0)
        end = int((deleted_info or {}).get("end_row") or 0)
        deleted_rows = int((deleted_info or {}).get("deleted_rows") or max(0, end - start + 1))
        if not p or start <= 0 or deleted_rows <= 0:
            return

        updated = []
        removed = False
        for it in getattr(self, "contract_index", []):
            ip = str(it.get("platform", "") or "")
            irow = int(it.get("row", 0) or 0)
            ino = str(it.get("no", "") or "").strip()

            if ip == p and irow == start and ino == no and not removed:
                removed = True
                continue

            rec = dict(it)
            if ip == p and irow > end:
                rec["row"] = irow - deleted_rows
            updated.append(rec)

        # Güvenli fallback: row eşleşmesi bozulduysa ilk aynı no'yu düş.
        if not removed:
            for idx, it in enumerate(updated):
                if str(it.get("platform", "") or "") == p and str(it.get("no", "") or "").strip() == no:
                    del updated[idx]
                    removed = True
                    break

        self.contract_index = updated


if __name__ == "__main__":
    configure_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("STS")
    app.setApplicationDisplayName("STS")
    app.setDesktopFileName(APP_ID)
    app.setFont(QFont("Segoe UI", 10))
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    win = MainWindow()
    win.show()
    QTimer.singleShot(0, win.open_file)
    sys.exit(app.exec())
