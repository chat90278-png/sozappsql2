from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import json
import re
import sqlite3
from typing import Any, Iterable, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRectF, Qt, QThread, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableView,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

from src.domain.constants import STATUS_VALUES
from src.ui.theme import STYLE

NAVY = "#0b3679"
GRID = "#cfe0f4"
GREEN = "#10a968"
RED = "#ef4444"
BLUE = "#1f7ed6"
AMBER = "#f59e0b"
MUTED = "#64748b"
CHART_COLORS = ["#5b9bd5", "#ed7d31", "#a5a5a5", "#ffc000", "#4472c4", "#70ad47", "#00a6a6", "#8064a2"]
ARROW_ICON_PATH = (Path(__file__).resolve().parents[1] / "assets" / "chevron_down.svg").as_posix()

DELIVERY_TREE_STYLE = """
QTreeWidget {
    background: white;
    alternate-background-color: #f4f9ff;
    border: 1px solid #cfe0f4;
    color: #002060;
    selection-background-color: #dbeafe;
    selection-color: #002060;
}
QTreeWidget::item {
    min-height: 34px;
    border-bottom: 1px solid #d7e6f8;
    padding: 4px 6px;
}
QTreeWidget::item:selected {
    background: #dbeafe;
}
QHeaderView::section {
    background-color: #0b3679;
    color: white;
    font-weight: bold;
    padding: 8px;
    border: 1px solid #2e5b9a;
}
QScrollBar:vertical {
    background: #eef4fb;
    border: none;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #9ebde0;
    border-radius: 4px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover {
    background: #6f9dcc;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    width: 0px;
    height: 0px;
}
QScrollBar:horizontal {
    background: #eef4fb;
    border: none;
    height: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #9ebde0;
    border-radius: 4px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover {
    background: #6f9dcc;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
}
"""



def _norm_text(value: object) -> str:
    text = str(value or "").strip().casefold()
    repl = {"ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def normalize_yi_yd(value: object) -> str:
    key = _norm_text(value).replace(" ", "")
    if key in {"yi", "yici", "yurtici", "yurtici", "yurtiçi", "yurtici"} or "yurtici" in key:
        return "Yİ"
    if key in {"yd", "yddisi", "yurtdisi", "yurtdisi", "yurtdışı", "yurtdisi"} or "yurtdisi" in key:
        return "YD"
    text = str(value or "").strip().upper()
    return text or "-"


def _is_all_filter_value(value: object, all_text: str = "Tümü") -> bool:
    return _norm_text(value) == _norm_text(all_text)


def normalize_yi_yd_filter(value: object) -> str:
    # Filter placeholder/meaning must stay as "Tümü". If we run it through
    # normalize_yi_yd(), it becomes "TÜMÜ" and the later comparison
    # filters every row out because it no longer equals the canonical "Tümü".
    return "Tümü" if _is_all_filter_value(value, "Tümü") else normalize_yi_yd(value)


def is_completed_status(value: object) -> bool:
    key = _norm_text(value)
    if not key:
        return False
    completed_keys = {
        "tamamlandi", "tamamlandı", "tamam", "bitti", "kapandi", "kapandı",
        "completed", "complete", "closed", "teslim edildi", "teslimedildi",
    }
    return key in completed_keys or key.startswith("tamamlan") or key.startswith("completed")


def report_status_values() -> list[str]:
    values = []
    for value in list(STATUS_VALUES):
        text = str(value or "").strip()
        if text and not is_completed_status(text):
            values.append(text)
    return values

def extract_year_from_date_text(value: object) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(?<!\d)(19\d{2}|20\d{2}|21\d{2})(?!\d)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_year_range(value: object) -> tuple[Optional[int], Optional[int]]:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})(?:-(\d{4}))?", text)
    if not match:
        return None, None
    try:
        start_year = int(match.group(1))
        end_year = int(match.group(2) or match.group(1))
    except (TypeError, ValueError):
        return None, None
    if start_year > end_year:
        start_year, end_year = end_year, start_year
    return start_year, end_year


def normalize_report_date_display(value: object) -> str:
    """Return a visible report date, preserving uncertain/TBD dates.

    Supported examples:
    - empty / None / TBD       -> TBD-TBD-TBD
    - 2026                    -> TBD-TBD-2026
    - 06-2026 / 2026-06       -> TBD-06-2026
    - TBD-06-2026             -> TBD-06-2026
    - 2026-TBD-TBD            -> TBD-TBD-2026
    - 15-06-2026 / 2026-06-15 -> 15-06-2026
    """
    raw = str(value or "").strip()
    if not raw:
        return "TBD-TBD-TBD"

    text = raw.replace("/", "-").replace(".", "-").strip().upper()
    compact_unknown = re.sub(r"[^A-Z0-9]+", "", text)
    if compact_unknown in {"", "TBD", "TBDBELIRLENECEK", "BELIRSIZ", "BILINMIYOR", "UNKNOWN", "N/A", "NA", "NONE", "NULL"}:
        return "TBD-TBD-TBD"

    def is_year(part: str) -> bool:
        return bool(re.fullmatch(r"(19\d{2}|20\d{2}|21\d{2})", str(part or "").strip()))

    def is_unknown(part: str) -> bool:
        token = re.sub(r"[^A-Z0-9]+", "", str(part or "").strip().upper())
        return token in {"", "0", "00", "TBD", "BELIRSIZ", "BILINMIYOR", "UNKNOWN", "NA", "NONE", "NULL"}

    def two_digit(part: str) -> str:
        part = str(part or "").strip().upper()
        if is_unknown(part):
            return "TBD"
        return part.zfill(2) if part.isdigit() and len(part) <= 2 else part

    parts = [p.strip() for p in text.split("-") if p.strip()]

    year = next((p for p in parts if is_year(p)), None)
    if year is None:
        extracted = extract_year_from_date_text(text)
        if extracted:
            return f"TBD-TBD-{extracted}"
        return "TBD-TBD-TBD" if any(is_unknown(p) for p in parts) else text

    if len(parts) == 1:
        return f"TBD-TBD-{year}"

    if len(parts) == 2:
        other = parts[1] if is_year(parts[0]) else parts[0]
        # With two-part dates, treat the non-year token as month.
        return f"TBD-{two_digit(other)}-{year}"

    if is_year(parts[0]):
        year, month, day = parts[0], parts[1], parts[2]
        return f"{two_digit(day)}-{two_digit(month)}-{year}"
    if is_year(parts[2]):
        day, month, year = parts[0], parts[1], parts[2]
        return f"{two_digit(day)}-{two_digit(month)}-{year}"

    return f"TBD-TBD-{year}"


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_amount(value: object) -> str:
    number = _safe_float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def _short_join(values: Iterable[object], limit: int = 2, empty: str = "") -> str:
    """Return a compact comma separated summary for group rows."""
    clean: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text == "-" or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        clean.append(text)
    if not clean:
        return empty
    return ", ".join(clean[:limit]) + (f" +{len(clean) - limit}" if len(clean) > limit else "")


def _payload_value(text: str, *keys: str) -> str:
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _json_summary(text: str) -> str:
    if not text:
        return ""
    try:
        value = json.loads(text)
    except Exception:
        return str(text)[:80]
    if isinstance(value, dict):
        for key in ("field", "name", "column", "value", "old", "new", "message"):
            if value.get(key) not in (None, ""):
                return str(value.get(key))[:80]
        return ", ".join(str(k) for k in list(value.keys())[:3])
    return str(value)[:80]


def _conn_from_store(store: object) -> Optional[sqlite3.Connection]:
    db = getattr(store, "db", None)
    conn = getattr(db, "conn", None)
    return conn if conn is not None else getattr(store, "conn", None)


def contract_owner_text(conn: sqlite3.Connection, contract_id: int) -> str:
    rows = conn.execute(
        """
        SELECT u.name
        FROM contract_users cu
        JOIN users u ON u.id = cu.user_id
        WHERE cu.contract_id=?
        ORDER BY u.name
        """,
        (int(contract_id),),
    ).fetchall()
    return ", ".join(str(row[0] or "").strip() for row in rows if str(row[0] or "").strip())


@dataclass(frozen=True)
class DeliveryRow:
    contract_id: int
    delivery_id: int
    platform: str
    contract: str
    system: str
    owner: str
    user: str
    domestic: str
    delivery: str
    date_text: str
    level: str
    part: str
    planned: float
    delivered: float
    config_type: str
    note: str
    status: str

    @property
    def remaining(self) -> float:
        return max(_safe_float(self.planned) - _safe_float(self.delivered), 0.0)

    @property
    def year(self) -> Optional[int]:
        return extract_year_from_date_text(self.date_text)


class SimpleTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], rows: list[Iterable[Any]], parent=None):
        super().__init__(parent)
        self.headers = headers
        self.rows = [list(row) for row in rows]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.DisplayRole:
            return str(value)
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter if index.column() in {0, 6, 8, 9, 10} else Qt.AlignVCenter | Qt.AlignLeft
        if role == Qt.BackgroundRole and index.row() % 2:
            return QColor("#f4f9ff")
        if role == Qt.ForegroundRole:
            text = str(value).lower()
            if "risk" in text:
                return QColor(RED)
            if "tamam" in text:
                return QColor(GREEN)
        if role == Qt.FontRole and index.column() in {6, 8, 9, 10}:
            font = QFont(); font.setBold(True); return font
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        if role == Qt.BackgroundRole and orientation == Qt.Horizontal:
            return QColor(NAVY)
        if role == Qt.ForegroundRole and orientation == Qt.Horizontal:
            return QColor("white")
        return None


class PartBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[tuple[str, float]] = []
        self.setMinimumHeight(250)
        self.setMinimumWidth(320)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        # Show ALL items, not just first 8
        self.data = data
        self.setMinimumHeight(max(250, 48 + len(self.data) * 28))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 16, -16, -16)
        p.setPen(QColor("#002060")); p.drawText(r, Qt.AlignTop | Qt.AlignLeft, "Parça Bazlı Sözleşme Adeti")
        if not self.data:
            p.setPen(QColor(MUTED)); p.drawText(r, Qt.AlignCenter, "Veri bulunamadı")
            return
        max_value = max(v for _, v in self.data) or 1
        top = r.top() + 42; row_h = 26; label_w = 150; value_w = 45
        for i, (name, value) in enumerate(self.data):
            y = top + i * row_h
            p.setPen(QColor("#002060")); p.drawText(r.left(), y + 17, name[:24])
            bar_x = r.left() + label_w; bar_w = max(1, r.width() - label_w - value_w)
            p.setPen(Qt.NoPen); p.setBrush(QColor("#e7eef8")); p.drawRoundedRect(bar_x, y + 5, bar_w, 15, 7, 7)
            p.setBrush(QColor(BLUE)); p.drawRoundedRect(bar_x, y + 5, int(bar_w * value / max_value), 15, 7, 7)
            p.setPen(QColor("#002060")); p.drawText(bar_x + bar_w + 8, y + 17, _fmt_amount(value))


class DonutDistributionWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.yi = 0.0
        self.yd = 0.0
        self.setMinimumHeight(250)

    def set_data(self, yi: float, yd: float) -> None:
        self.yi = _safe_float(yi); self.yd = _safe_float(yd); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 16, -16, -16)
        p.setPen(QColor("#002060")); p.drawText(r, Qt.AlignTop | Qt.AlignLeft, "Yİ / YD Dağılımı")
        total = self.yi + self.yd
        center = QRectF(r.left() + 40, r.top() + 58, 120, 120)
        p.setPen(Qt.NoPen)
        if total <= 0:
            p.setBrush(QColor("#e7eef8")); p.drawEllipse(center)
        else:
            yi_span = int(360 * 16 * self.yi / total)
            p.setBrush(QColor(GREEN)); p.drawPie(center, 90 * 16, yi_span)
            p.setBrush(QColor(BLUE)); p.drawPie(center, 90 * 16 + yi_span, 360 * 16 - yi_span)
        p.setBrush(QColor("white")); p.drawEllipse(center.adjusted(32, 32, -32, -32))
        lx = r.left() + 190; ly = r.top() + 75
        for i, (label, value, color) in enumerate((("Yİ", self.yi, GREEN), ("YD", self.yd, BLUE))):
            p.setBrush(QColor(color)); p.drawEllipse(lx, ly + i * 28, 10, 10)
            p.setPen(QColor("#002060")); p.drawText(lx + 18, ly + 10 + i * 28, f"{label}: {_fmt_amount(value)} adet")
        p.setPen(QColor(MUTED)); p.drawText(lx, ly + 70, f"Toplam: {_fmt_amount(total)} adet")


class TrendLineWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[tuple[int, float, float]] = []
        self.setMinimumHeight(250)
        self.setMinimumWidth(520)

    def set_data(self, data: list[tuple[int, float, float]]) -> None:
        self.data = data
        # Keep a comfortable base width so the chart is not squeezed,
        # but still grow wider when many years exist.
        self.setMinimumWidth(max(520, len(self.data) * 110))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 16, -16, -16)
        p.setPen(QColor("#002060")); p.drawText(r, Qt.AlignTop | Qt.AlignLeft, "Yıllara Göre Plan / Teslim")
        chart = r.adjusted(45, 50, -25, -35)
        p.setPen(QPen(QColor("#d8e2ed"))); p.drawRect(chart)
        if not self.data:
            p.setPen(QColor(MUTED)); p.drawText(chart, Qt.AlignCenter, "Veri bulunamadı")
            return
        max_value = max(max(plan, delivered) for _, plan, delivered in self.data) or 1
        for i in range(4):
            y = chart.bottom() - int(chart.height() * i / 3)
            p.setPen(QPen(QColor("#e5e7eb"))); p.drawLine(chart.left(), y, chart.right(), y)
        def points(kind_index: int) -> list:
            pts = []
            count = max(len(self.data) - 1, 1)
            for idx, (year, plan, delivered) in enumerate(self.data):
                value = plan if kind_index == 1 else delivered
                x = chart.left() + int(chart.width() * idx / count)
                y = chart.bottom() - int(chart.height() * value / max_value)
                pts.append((x, y, year, value))
            return pts
        for kind, color in ((1, BLUE), (2, GREEN)):
            pts = points(kind)
            p.setPen(QPen(QColor(color), 2))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a[0], a[1], b[0], b[1])
            p.setBrush(QColor(color))
            for x, y, year, value in pts:
                p.drawEllipse(x - 4, y - 4, 8, 8)
        p.setPen(QColor("#002060"))
        for x, y, year, value in points(1):
            p.drawText(x - 20, chart.bottom() + 22, str(year))
        p.setPen(QColor(BLUE)); p.drawText(chart.left(), r.bottom() - 2, "Plan")
        p.setPen(QColor(GREEN)); p.drawText(chart.left() + 60, r.bottom() - 2, "Teslim")


class GroupedBarPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.users: list[str] = []
        self.parts: list[str] = []
        self.values: dict[str, list[float]] = {}
        self.group_width = 150
        self.setMinimumHeight(620)

    def set_data(self, users: list[str], parts: list[str], values: dict[str, list[float]]) -> None:
        self.users = users
        self.parts = parts[:8]
        self.values = {part: values.get(part, [])[:len(self.users)] for part in self.parts}
        longest_user = max([len(user) for user in self.users] or [12])
        self.group_width = max(150, longest_user * 8 + 28)
        self.setMinimumWidth(max(900, self.group_width * max(len(self.users), 1) + 300))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(18, 18, -18, -18)
        p.fillRect(r, QColor("white")); p.setPen(QPen(QColor(GRID))); p.drawRect(r)
        p.setPen(QColor("#002060")); p.drawText(r.adjusted(0, 4, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "YURTİÇİ/YURTDIŞI ve YILLARA GÖRE SİPARİŞ DURUMU")
        if not self.users or not self.parts:
            p.setPen(QColor(MUTED)); p.drawText(r, Qt.AlignCenter, "Veri bulunamadı")
            return
        chart = r.adjusted(70, 48, -215, -245)
        maxv = max([max(v or [0]) for v in self.values.values()] or [1]) or 1
        # Kılavuz değerleri küsuratlı göstermemek için ekseni tam sayılı adımlara taşı.
        axis_step = max(1, int((maxv + 4) // 5))
        axis_max = max(axis_step * 5, 1)
        for i in range(6):
            guide_value = axis_step * i
            y = chart.bottom() - int(chart.height() * guide_value / axis_max)
            p.setPen(QPen(QColor("#d8d8d8"))); p.drawLine(chart.left(), y, chart.right(), y)
            p.setPen(QColor("#334155")); p.drawText(chart.left() - 42, y + 4, str(int(guide_value)))
        group_w = max(self.group_width, chart.width() / max(len(self.users), 1)); bar_w = max(4, min(12, int(group_w / (len(self.parts) + 4))))
        for ui, user in enumerate(self.users):
            base_x = chart.left() + ui * group_w + group_w * .16
            for pi, part in enumerate(self.parts):
                vals = self.values.get(part, [])
                value = vals[ui] if ui < len(vals) else 0
                h = int(chart.height() * value / axis_max)
                x = int(base_x + pi * (bar_w + 4)); y = chart.bottom() - h
                p.setPen(Qt.NoPen); p.setBrush(QColor(CHART_COLORS[pi % len(CHART_COLORS)])); p.drawRect(x, y, bar_w, h)
                if value:
                    p.setPen(QColor("#111827")); p.drawText(x - 2, y - 5, _fmt_amount(value))
            p.setPen(QColor("#111827")); p.drawText(int(chart.left() + ui * group_w), chart.bottom() + 22, int(group_w), 22, Qt.AlignCenter, user)
        lx = r.right() - 175; ly = chart.top() + 80
        p.setPen(QColor("#111827")); p.drawText(lx, ly - 25, "PARÇA ADI ▾")
        for i, part in enumerate(self.parts):
            p.fillRect(lx, ly + i * 28, 10, 10, QColor(CHART_COLORS[i % len(CHART_COLORS)])); p.drawText(lx + 18, ly + 10 + i * 28, part[:22])
        table_top = chart.bottom() + 54
        table = r.adjusted(105, table_top - r.top(), -215, -20)
        cols = [""] + self.users; row_h = 22; col_w = max(125, table.width() / max(len(cols), 1))
        p.setPen(QPen(QColor("#d8d8d8")))
        for ri, part in enumerate([""] + self.parts):
            for ci, col in enumerate(cols):
                cell_x = int(table.left() + ci * col_w); cell_y = table.top() + ri * row_h
                p.drawRect(cell_x, cell_y, int(col_w), row_h)
                if ri == 0 and ci > 0:
                    p.drawText(cell_x, cell_y, int(col_w), row_h, Qt.AlignCenter, col)
                elif ri > 0 and ci == 0:
                    p.fillRect(cell_x + 8, cell_y + 8, 10, 10, QColor(CHART_COLORS[(ri - 1) % len(CHART_COLORS)])); p.drawText(cell_x + 24, cell_y, int(col_w), row_h, Qt.AlignVCenter, part[:24])
                elif ri > 0 and ci > 0:
                    vals = self.values.get(part, [])
                    p.drawText(cell_x, cell_y, int(col_w), row_h, Qt.AlignCenter, _fmt_amount(vals[ci - 1] if ci - 1 < len(vals) else 0))


# ─── Excel Export Worker ──────────────────────────────────────────────────────

class ExcelExportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, store_path: str, output_path: str, filters: dict):
        super().__init__()
        self.store_path = store_path
        self.output_path = output_path
        self.filters = filters

    def run(self):
        from src.services.delivery_schedule_excel_exporter import (
            export_delivery_schedule_report,
        )
        import sqlite3

        # Open a fresh SQLite connection in the worker thread
        try:
            conn = sqlite3.connect(self.store_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")

            class _FakeStore:
                def __init__(self, c):
                    self.conn = c

            store = _FakeStore(conn)
            result = export_delivery_schedule_report(
                store,
                self.output_path,
                filters=self.filters,
                progress_cb=lambda value, message: self.progress.emit(value, message),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ─── Loading Overlay ──────────────────────────────────────────────────────────

class ExcelLoadingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("excelLoadingOverlay")
        self.setStyleSheet("""
            QWidget#excelLoadingOverlay {
                background: rgba(0, 10, 40, 160);
            }
            QWidget#excelLoadingOverlay QLabel,
            QFrame#loadingCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        self._spinner_angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._spin)
        self._timer.start(50)

        # Card
        card = QFrame(self)
        card.setObjectName("loadingCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setFixedWidth(380)
        card.setStyleSheet("""
            QFrame#loadingCard {
                background-color: #ffffff;
                border-radius: 18px;
                border: 2px solid #cfe0f4;
            }
            QFrame#loadingCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(32, 28, 32, 28)
        card_lay.setSpacing(14)

        title = QLabel("Excel raporu hazırlanıyor")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #002060; font-size: 16px; font-weight: 900; background: transparent; border: none;")
        card_lay.addWidget(title)

        self.spinner_label = QLabel("⠋")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        self.spinner_label.setStyleSheet("color: #0b3679; font-size: 28px; background: transparent; border: none;")
        card_lay.addWidget(self.spinner_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #e7eef8;
                border-radius: 5px;
                border: none;
            }
            QProgressBar::chunk {
                background: #0b3679;
                border-radius: 5px;
            }
        """)
        card_lay.addWidget(self.progress_bar)

        self.status_label = QLabel("Microsoft Excel başlatılıyor")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #415a86; font-size: 12px; background: transparent; border: none;")
        card_lay.addWidget(self.status_label)

        self._card = card
        self._position_card()

    def _spin(self):
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_angle = (self._spinner_angle + 1) % len(frames)
        self.spinner_label.setText(frames[self._spinner_angle])

    def _position_card(self):
        if self.parent():
            pw = self.parent().size()
            cw = self._card.width()
            ch = self._card.sizeHint().height()
            self._card.move((pw.width() - cw) // 2, (pw.height() - ch) // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_card()

    def update_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def close(self):
        self._timer.stop()
        super().close()
        self.deleteLater()



class RevisionRowDialog(QDialog):
    def __init__(self, parent=None, defaults: Optional[dict[str, Any]] = None, title: str = "REV Kaydı Ekle"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.result: Optional[dict[str, Any]] = None
        defaults = dict(defaults or {})
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        header = QLabel(title)
        header.setObjectName("mainTitle")
        root.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.revision_edit = QLineEdit(str(defaults.get("revision_info") or defaults.get("field_name") or defaults.get("revision") or ""))
        self.revision_edit.setPlaceholderText("Örn: R001 / İlk yayın / Revizyon notu")

        self.date_edit = QLineEdit(str(defaults.get("revision_date") if defaults.get("revision_date") is not None else (defaults.get("date") or "")))
        self.date_edit.setPlaceholderText("Örn: 20-06-2026 / TBD / kullanıcı belirler")

        self.desc_edit = QTextEdit(str(defaults.get("description") or ""))
        self.desc_edit.setPlaceholderText("Açıklama")
        self.desc_edit.setFixedHeight(96)

        fields = [
            ("Revizyon Bilgisi", self.revision_edit),
            ("Tarih", self.date_edit),
            ("Açıklama", self.desc_edit),
        ]
        for row, (label, widget) in enumerate(fields):
            lab = QLabel(label)
            lab.setObjectName("fieldLabel")
            grid.addWidget(lab, row, 0)
            grid.addWidget(widget, row, 1)
        root.addLayout(grid)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("İptal")
        cancel.setObjectName("reportSecondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet")
        save.setObjectName("reportPrimaryButton")
        save.clicked.connect(self._accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def _accept(self):
        revision_info = self.revision_edit.text().strip()
        date_text = self.date_edit.text().strip()
        description = self.desc_edit.toPlainText().strip()
        if not any((revision_info, date_text, description)):
            QMessageBox.warning(self, "Eksik", "En az bir alan doldurulmalı.")
            return
        self.result = {
            "revision_info": revision_info,
            "revision_date": date_text,
            "description": description,
            # Eski tablo şemasıyla uyumluluk: Revizyon Bilgisi field_name alanında saklanır.
            "field_name": revision_info,
        }
        self.accept()

# ─── Main Dialog ─────────────────────────────────────────────────────────────

class DeliveryScheduleReportDialog(QDialog):
    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store or getattr(parent, "store", None)
        # NOT: self.conn ana thread connection'ını tutar — doğrudan sorgu için.
        # ExcelExportWorker'a asla geçirilmemeli; worker kendi bağlantısını
        # kendi açıyor (store_path STRING alıyor). Bu yapı korunmalı.
        self.conn = _conn_from_store(self.store)
        self.all_rows: list[DeliveryRow] = []
        self.filtered_rows: list[DeliveryRow] = []
        self._export_thread: Optional[QThread] = None
        self._export_worker: Optional[ExcelExportWorker] = None
        self._loading_overlay: Optional[ExcelLoadingOverlay] = None
        self._rev_rows: list[dict[str, Any]] = []
        self.setWindowTitle("Tahmini Teslimat Takvimi")
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(1450, 850); self.setMinimumSize(1180, 720)
        self.setStyleSheet(STYLE + self._extra_style())
        self.build_ui()
        self.reload_from_db()

    def build_ui(self):
        root = QHBoxLayout(self); root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(self._build_filters())
        main = QFrame(); main.setObjectName("reportCard"); ml = QVBoxLayout(main); ml.setContentsMargins(18, 12, 18, 18)
        top = QHBoxLayout(); title = QLabel("Tahmini Teslimat Takvimi"); title.setObjectName("mainTitle"); top.addWidget(title); top.addStretch()
        self.refresh_btn = QPushButton("Önizlemeyi Yenile"); self.refresh_btn.setObjectName("reportSecondaryButton"); self.refresh_btn.clicked.connect(self.refresh_preview); top.addWidget(self.refresh_btn)
        self.export_btn = QPushButton("Excel Oluştur"); self.export_btn.setObjectName("reportPrimaryButton"); self.export_btn.clicked.connect(self.on_export_excel_clicked); top.addWidget(self.export_btn); ml.addLayout(top)
        self.info_label = QLabel(""); self.info_label.setObjectName("infoLabel"); ml.addWidget(self.info_label)
        self.tabs = QTabWidget(); self.tabs.addTab(self._dashboard_tab(), "Dashboard"); self.tabs.addTab(self._delivery_tab(), "Teslimat Verisi"); self.tabs.addTab(self._matrix_tab(), "Takvim Matrisi"); self.tabs.addTab(self._rev_tab(), "REV Takip")
        ml.addWidget(self.tabs, 1); root.addWidget(main, 1)

    def _build_filters(self):
        frame = QFrame(); frame.setObjectName("filterPanel"); frame.setFixedWidth(300); lay = QVBoxLayout(frame)
        lay.setSpacing(6)
        h = QLabel("Rapor Ayarları"); h.setObjectName("panelTitle"); lay.addWidget(h)

        self._filter_rows: dict[str, QFrame] = {}
        self._filter_animations: list[QPropertyAnimation] = []
        self._filter_updating = False
        self._refresh_pending = False
        # Progressive filtre mantığı:
        # "Tümü" gerçek bir filtre değeridir; anlamı "bu alanda kısıtlama uygulama,
        # mevcut üst filtrelere göre geçerli olanların hepsi" demektir.
        # Ancak pencere ilk açıldığında otomatik seçim sayılmaz. Kullanıcı dropdown'da
        # Tümü'nü bilerek seçerse bu alan "seçilmiş" kabul edilir ve sonraki filtre açılır.
        self._filter_touched: set[str] = set()
        self._filter_order = ["platform", "domestic", "owner", "contract", "status"]

        self.platform = self._combo(["Tümü"])
        self.year_range = QLineEdit(str(date.today().year))
        self.year_range.editingFinished.connect(self._schedule_filter_refresh)
        self.domestic = self._combo(["Tümü", "Yİ", "YD"])
        self.owner = self._combo(["Tümü"])
        self.contract = self._combo(["Tüm seçili sözleşmeler"])
        self.status = self._combo(["Tümü"] + report_status_values())
        for _key, _combo in (("platform", self.platform), ("domestic", self.domestic), ("owner", self.owner), ("contract", self.contract), ("status", self.status)):
            _combo.setProperty("filter_key", _key)
            _combo.activated.connect(lambda _index, key=_key: self._on_filter_activated(key))

        self._add_filter_row(lay, "PLATFORM", self.platform, "platform", visible=True)
        self._add_filter_row(lay, "YIL / ARALIK", self.year_range, "year", visible=True)
        self._add_filter_row(lay, "Yİ / YD", self.domestic, "domestic", visible=False)
        self._add_filter_row(lay, "KULLANICI / ÜLKE", self.owner, "owner", visible=False)
        self._add_filter_row(lay, "SÖZLEŞME", self.contract, "contract", visible=False)
        self._add_filter_row(lay, "DURUM", self.status, "status", visible=False)

        btn = QPushButton("Önizlemeyi Yenile")
        btn.setObjectName("reportPrimaryButton")
        btn.clicked.connect(self.refresh_preview)
        lay.addWidget(btn)

        # Kompakt sol panel özeti. Dashboard üst KPI kutuları kaldırıldı;
        # burada sadece doğru sayılan sözleşme ve kullanıcı adetleri gösterilir.
        self.filter_stats = QFrame()
        self.filter_stats.setObjectName("filterStats")
        stats_lay = QHBoxLayout(self.filter_stats)
        stats_lay.setContentsMargins(8, 7, 8, 7)
        stats_lay.setSpacing(8)
        self.contract_count_value = self._make_filter_stat(stats_lay, "Sözleşme", "0")
        self.user_count_value = self._make_filter_stat(stats_lay, "Kullanıcı", "0")
        lay.addWidget(self.filter_stats)
        lay.addStretch()
        QTimer.singleShot(180, self._update_filter_visibility)
        return frame

    def _make_filter_stat(self, parent_layout: QHBoxLayout, title: str, value: str) -> QLabel:
        box = QFrame()
        box.setObjectName("filterStatBox")
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(6, 4, 6, 4)
        box_lay.setSpacing(1)
        t = QLabel(str(title or ""))
        t.setObjectName("filterStatTitle")
        t.setAlignment(Qt.AlignCenter)
        v = QLabel(str(value or "0"))
        v.setObjectName("filterStatValue")
        v.setAlignment(Qt.AlignCenter)
        box_lay.addWidget(t)
        box_lay.addWidget(v)
        parent_layout.addWidget(box, 1)
        return v

    def _add_filter_row(self, parent_layout: QVBoxLayout, label: str, widget: QWidget, key: str, visible: bool = True) -> None:
        row = QFrame()
        row.setObjectName("filterRow")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_lay = QVBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)
        l = QLabel(label)
        l.setObjectName("fieldLabel")
        row_lay.addWidget(l)
        row_lay.addWidget(widget)
        parent_layout.addWidget(row)
        self._filter_rows[key] = row
        if visible:
            row.setMaximumHeight(16777215)
            row.setVisible(True)
        else:
            row.setMaximumHeight(0)
            row.setVisible(False)

    def _combo(self, items):
        c = QComboBox()
        c.addItems(items)
        c.currentIndexChanged.connect(self._schedule_filter_refresh)
        return c

    def _schedule_filter_refresh(self, *_args) -> None:
        if getattr(self, "_filter_updating", False):
            return
        if getattr(self, "_refresh_pending", False):
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._run_scheduled_filter_refresh)

    def _run_scheduled_filter_refresh(self) -> None:
        self._refresh_pending = False
        if not hasattr(self, "delivery_tree"):
            return
        self._update_filter_options()
        self._update_filter_visibility()
        self.refresh_preview()

    def _animate_filter_row(self, key: str, show: bool) -> None:
        row = getattr(self, "_filter_rows", {}).get(key)
        if row is None:
            return
        target = row.sizeHint().height() if show else 0
        if show:
            row.setVisible(True)
        current = row.maximumHeight()
        if (show and current == target) or ((not show) and current == 0):
            if not show:
                row.setVisible(False)
            return
        anim = QPropertyAnimation(row, b"maximumHeight", self)
        anim.setDuration(180)
        anim.setStartValue(max(0, current if current < 16000 else row.sizeHint().height()))
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if not show:
            anim.finished.connect(lambda r=row: r.setVisible(False))
        anim.finished.connect(lambda a=anim: self._filter_animations.remove(a) if a in self._filter_animations else None)
        self._filter_animations.append(anim)
        anim.start()

    def _on_filter_activated(self, key: str) -> None:
        """Mark a filter as deliberately selected by the user.

        "Tümü" is not a placeholder here. It means "all valid values under the
        current upper filters". Therefore, if the user explicitly chooses Tümü,
        it must unlock the next progressive filter row even though it does not
        restrict the SQL/data result.
        """
        if getattr(self, "_filter_updating", False):
            return
        key = str(key or "")
        self._filter_touched.add(key)
        self._reset_lower_filter_steps(key)
        self._schedule_filter_refresh()

    def _reset_lower_filter_steps(self, key: str) -> None:
        order = list(getattr(self, "_filter_order", []))
        if key not in order:
            return
        lower = order[order.index(key) + 1:]
        for lower_key in lower:
            self._filter_touched.discard(lower_key)
            combo = getattr(self, {
                "domestic": "domestic",
                "owner": "owner",
                "contract": "contract",
                "status": "status",
            }.get(lower_key, ""), None)
            if isinstance(combo, QComboBox) and combo.currentIndex() != 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

    def _is_combo_step_selected(self, key: str, combo: QComboBox, default_text: str = "Tümü") -> bool:
        """Return True if this progressive step should unlock the next row.

        Non-default values always count. The default value also counts only if
        the user explicitly activated that combo. This separates two meanings:
        initial default Tümü = no user choice yet; activated Tümü = all valid.
        """
        text = str(combo.currentText() or "").strip()
        if text and text != default_text:
            return True
        return key in getattr(self, "_filter_touched", set())

    def _update_filter_visibility(self) -> None:
        if not hasattr(self, "_filter_rows"):
            return

        year_ok = bool(parse_year_range(self.year_range.text().strip())[0])
        platform_selected = self._is_combo_step_selected("platform", self.platform, "Tümü")
        domestic_selected = self._is_combo_step_selected("domestic", self.domestic, "Tümü")
        owner_selected = self._is_combo_step_selected("owner", self.owner, "Tümü")
        contract_selected = self._is_combo_step_selected("contract", self.contract, "Tüm seçili sözleşmeler")

        reveal_domestic = year_ok and platform_selected
        reveal_owner = reveal_domestic and domestic_selected
        reveal_contract = reveal_owner and owner_selected
        reveal_status = reveal_contract and contract_selected

        for key, show in (
            ("domestic", reveal_domestic),
            ("owner", reveal_owner),
            ("contract", reveal_contract),
            ("status", reveal_status),
        ):
            self._animate_filter_row(key, show)
    def _dashboard_tab(self):
        w = QScrollArea(); w.setWidgetResizable(True); host = QWidget(); lay = QVBoxLayout(host)
        lay.setSpacing(8)
        upper = QHBoxLayout()
        upper.setSpacing(8)

        # PartBarWidget wrapped in vertical QScrollArea
        self.part_bar = PartBarWidget()
        self.part_bar_scroll = QScrollArea()
        # Vertical scrolling only; keep the inner chart stretched to card width.
        self.part_bar_scroll.setWidgetResizable(True)
        self.part_bar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.part_bar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.part_bar_scroll.setWidget(self.part_bar)
        part_card = QFrame(); part_card.setObjectName("reportCard"); cl = QVBoxLayout(part_card); cl.addWidget(self.part_bar_scroll)
        upper.addWidget(part_card, 1)

        self.donut = DonutDistributionWidget()
        donut_card = QFrame(); donut_card.setObjectName("reportCard"); cl2 = QVBoxLayout(donut_card); cl2.addWidget(self.donut)
        upper.addWidget(donut_card, 1)

        # TrendLineWidget wrapped in horizontal QScrollArea
        self.trend = TrendLineWidget()
        self.trend_scroll = QScrollArea()
        self.trend_scroll.setWidgetResizable(False)
        self.trend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.trend_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.trend_scroll.setWidget(self.trend)
        trend_card = QFrame(); trend_card.setObjectName("reportCard"); cl3 = QVBoxLayout(trend_card); cl3.addWidget(self.trend_scroll)
        upper.addWidget(trend_card, 1)

        lay.addLayout(upper)
        self.chart = GroupedBarPreview()
        self.chart_scroll = QScrollArea()
        self.chart_scroll.setWidgetResizable(False)
        self.chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chart_scroll.setWidget(self.chart)
        card = QFrame(); card.setObjectName("reportCard"); cl = QVBoxLayout(card); cl.addWidget(self.chart_scroll); lay.addWidget(card)
        w.setWidget(host); return w

    def _delivery_tab(self):
        """Build the Teslimat Verisi tab as a grouped QTreeWidget."""
        DELIVERY_COLS = [
            "Sözleşme No", "Sistem / Paket", "Teslimat", "Tarih",
            "Sözleşme Sahibi", "Teslim Kullanıcısı", "Yİ/YD", "Seviye",
            "Parça", "Sözleşme Adeti", "Teslim", "Kalan",
            "Konfigürasyon Tipi", "Opsiyon / Not", "Durum",
        ]
        self.delivery_tree = QTreeWidget()
        self.delivery_tree.setColumnCount(len(DELIVERY_COLS))
        self.delivery_tree.setHeaderLabels(DELIVERY_COLS)
        self.delivery_tree.setAlternatingRowColors(True)
        self.delivery_tree.setRootIsDecorated(True)
        self.delivery_tree.setItemsExpandable(True)
        self.delivery_tree.setExpandsOnDoubleClick(True)
        self.delivery_tree.setIndentation(24)
        self.delivery_tree.setUniformRowHeights(False)
        self.delivery_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.delivery_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.delivery_tree.setWordWrap(False)
        self.delivery_tree.header().setMinimumSectionSize(80)
        self.delivery_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.delivery_tree.header().setStretchLastSection(True)
        self.delivery_tree.setStyleSheet(DELIVERY_TREE_STYLE)
        # Keep delivery_view alias for any backward-compat checks
        self.delivery_view = self.delivery_tree
        return self.delivery_tree

    def _matrix_tab(self): self.matrix_view = self._table(); return self.matrix_view
    def _rev_tab(self):
        self.rev_view = self._table()
        self.rev_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rev_view.customContextMenuRequested.connect(self._show_rev_context_menu)
        return self.rev_view

    def _table(self):
        v = QTableView()
        v.setAlternatingRowColors(True)
        v.setSortingEnabled(False)
        v.setWordWrap(False)
        v.setShowGrid(True)
        v.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.verticalHeader().setVisible(False)
        v.verticalHeader().setDefaultSectionSize(42)
        v.horizontalHeader().setMinimumSectionSize(90)
        v.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        v.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        v.horizontalHeader().setStretchLastSection(True)
        return v

    def reload_from_db(self) -> None:
        self.conn = _conn_from_store(self.store)
        self.all_rows = self.load_delivery_rows_from_db()
        self.populate_filters_from_rows(self.all_rows)
        self.refresh_preview()

    def _set_combo_items(self, combo: QComboBox, items: list[str], first: str, fallback_to_first: bool = True) -> None:
        current = combo.currentText()
        self._filter_updating = True
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(first)
        seen = {first.casefold()}
        for item in items:
            text = str(item or "").strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                combo.addItem(text)
        index = combo.findText(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif fallback_to_first:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
        self._filter_updating = False

    def _base_rows(self) -> list[DeliveryRow]:
        return [r for r in self.all_rows if r.remaining > 0 and not is_completed_status(r.status)]

    def _rows_matching(self, rows: list[DeliveryRow], filters: dict[str, Any], skip: set[str] | None = None) -> list[DeliveryRow]:
        skip = set(skip or set())
        out = list(rows)
        if "year" not in skip and filters.get("year_range_valid"):
            # Keep uncertain dates visible. If a row has no extractable year
            # (TBD-TBD-TBD / fully unknown), it should not disappear from the
            # report just because the year filter is active. Rows with a known
            # year still obey the selected year range.
            out = [
                r for r in out
                if r.year is None or filters["start_year"] <= r.year <= filters["end_year"]
            ]
        if "platform" not in skip and filters.get("platform") != "Tümü":
            out = [r for r in out if r.platform == filters.get("platform")]
        if "yi_yd" not in skip and not _is_all_filter_value(filters.get("yi_yd"), "Tümü"):
            target = normalize_yi_yd(filters.get("yi_yd"))
            out = [r for r in out if normalize_yi_yd(r.domestic) == target]
        if "owner" not in skip and filters.get("owner") != "Tümü":
            target = str(filters.get("owner") or "").strip()
            out = [r for r in out if target in [owner.strip() for owner in str(r.owner or "").split(",")]]
        if "contract" not in skip and filters.get("contract") != "Tüm seçili sözleşmeler":
            out = [r for r in out if r.contract == filters.get("contract")]
        if "status" not in skip and filters.get("status") != "Tümü":
            target = _norm_text(filters.get("status"))
            out = [r for r in out if _norm_text(r.status) == target]
        return out

    def populate_filters_from_rows(self, rows: list[DeliveryRow]) -> None:
        rows = [r for r in rows if r.remaining > 0 and not is_completed_status(r.status)]
        self._set_combo_items(self.platform, sorted({r.platform for r in rows if r.platform}), "Tümü")
        self._set_combo_items(self.domestic, sorted({normalize_yi_yd(r.domestic) for r in rows if normalize_yi_yd(r.domestic) in {"Yİ", "YD"}}), "Tümü")
        owners = sorted({owner.strip() for r in rows for owner in str(r.owner or "").split(",") if owner.strip() and owner.strip() != "-"})
        self._set_combo_items(self.owner, owners, "Tümü")
        self._set_combo_items(self.contract, sorted({r.contract for r in rows if r.contract}), "Tüm seçili sözleşmeler")
        self._set_combo_items(self.status, report_status_values(), "Tümü")
        years = sorted({r.year for r in rows if r.year})
        if years and self.year_range.text().strip() in {"", str(date.today().year)}:
            self.year_range.setText(str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}")

    def _update_filter_options(self) -> None:
        if getattr(self, "_filter_updating", False):
            return
        filters = self.collect_filters()
        rows = self._base_rows()
        if filters.get("year_range_valid"):
            year_rows = self._rows_matching(rows, filters, skip={"platform", "yi_yd", "owner", "contract", "status"})
        else:
            year_rows = rows
        self._set_combo_items(self.platform, sorted({r.platform for r in self._rows_matching(year_rows, filters, skip={"platform"}) if r.platform}), "Tümü")
        yi_values = sorted({normalize_yi_yd(r.domestic) for r in self._rows_matching(year_rows, filters, skip={"yi_yd"}) if normalize_yi_yd(r.domestic) in {"Yİ", "YD"}})
        self._set_combo_items(self.domestic, yi_values, "Tümü")
        owner_values = sorted({owner.strip() for r in self._rows_matching(year_rows, filters, skip={"owner"}) for owner in str(r.owner or "").split(",") if owner.strip() and owner.strip() != "-"})
        self._set_combo_items(self.owner, owner_values, "Tümü")
        contract_values = sorted({r.contract for r in self._rows_matching(year_rows, filters, skip={"contract"}) if r.contract})
        self._set_combo_items(self.contract, contract_values, "Tüm seçili sözleşmeler")
        self._set_combo_items(self.status, report_status_values(), "Tümü")

    def collect_filters(self) -> dict[str, Any]:
        text = self.year_range.text().strip()
        start_year, end_year = parse_year_range(text)
        ok = start_year is not None and end_year is not None
        self.year_range.setProperty("invalid", not ok)
        self.year_range.style().unpolish(self.year_range); self.year_range.style().polish(self.year_range)
        return {"platform": self.platform.currentText(), "year_range": text, "start_year": start_year, "end_year": end_year, "year_range_valid": ok, "yi_yd": normalize_yi_yd_filter(self.domestic.currentText()), "owner": self.owner.currentText(), "contract": self.contract.currentText(), "status": self.status.currentText()}

    def build_report_payload(self) -> dict[str, Any]:
        return {"filters": self.collect_filters(), "generated_at": date.today().isoformat(), "deliveries": [self._row_payload(row) for row in self.filtered_rows], "matrix": self._matrix_rows(self.filtered_rows)[1], "activity_logs": self.load_activity_log_preview(self.collect_filters())}

    def _row_payload(self, row: DeliveryRow) -> dict[str, Any]:
        return {"contract_id": row.contract_id, "delivery_id": row.delivery_id, "platform": row.platform, "contract": row.contract, "system": row.system, "owner": row.owner, "delivery_user": row.user, "yi_yd": row.domestic, "delivery": row.delivery, "date": row.date_text, "level": row.level, "part": row.part, "planned": row.planned, "delivered": row.delivered, "remaining": row.remaining, "config_type": row.config_type, "note": row.note, "status": row.status}

    def clear_preview(self) -> None:
        self.filtered_rows = []
        if not hasattr(self, "delivery_tree"):
            return
        self.info_label.setText("" if self.conn else "Açık STS veri dosyası bulunamadı; rapor boş gösteriliyor.")
        self._refresh_kpis([])
        self._refresh_dashboard_charts([])
        self._refresh_delivery_table([])
        self._refresh_matrix_table([])
        self._rev_rows = []
        self.rev_view.setModel(SimpleTableModel(["Tarih", "Kullanıcı", "Sözleşme", "Teslimat", "Alan", "Eski Değer", "Yeni Değer", "Açıklama"], [], self))

    def refresh_preview(self, *_args):
        if not hasattr(self, "delivery_tree"):
            return
        filters = self.collect_filters()
        if not filters["year_range_valid"]:
            self.info_label.setText("Yıl / aralık formatı hatalı. Örnek: 2026 veya 2026-2027")
            return
        rows = self._rows_matching(self._base_rows(), filters)
        self.filtered_rows = rows
        self.info_label.setText("" if self.conn else "Açık STS veri dosyası bulunamadı; rapor boş gösteriliyor.")
        self._refresh_kpis(rows)
        self._refresh_dashboard_charts(rows)
        self._refresh_delivery_table(rows)
        self._refresh_matrix_table(rows)
        self._refresh_rev_table(filters)

    def load_delivery_rows_from_db(self) -> list[DeliveryRow]:
        if not self.conn:
            return []
        try:
            rows = self.conn.execute(
                """
                SELECT c.id AS contract_id, c.contract_no, c.yi_yd AS contract_yi_yd, c.status AS contract_status,
                       c.note AS contract_note, c.payload_json AS contract_payload_json, p.name AS platform_name,
                       d.id AS delivery_id, d.name AS delivery_name, d.status AS delivery_status,
                       d.planned_acceptance_date, d.acceptance_date, d.note AS delivery_note, d.payload_json AS delivery_payload_json,
                       du.name AS delivery_user_name, du.yi_yd AS delivery_user_yi_yd, s.name AS system_name,
                       comp.name AS component_name, dc.planned, dc.delivered
                FROM deliveries d
                JOIN contracts c ON c.id = d.contract_id
                LEFT JOIN platforms p ON p.id = c.platform_id
                LEFT JOIN systems s ON s.id = d.system_id
                LEFT JOIN users du ON du.id = d.delivery_user_id
                JOIN delivery_components dc ON dc.delivery_id = d.id
                JOIN components comp ON comp.id = dc.component_id
                ORDER BY p.name, c.contract_no, COALESCE(s.name, ''), d.sort_order, d.id, comp.name
                """
            ).fetchall()
        except Exception as exc:
            self.info_label.setText(f"Rapor verisi okunamadı: {exc}")
            return []
        result: list[DeliveryRow] = []
        owner_cache: dict[int, str] = {}
        for row in rows:
            if is_completed_status(row["contract_status"]):
                continue
            planned = _safe_float(row["planned"])
            delivered = _safe_float(row["delivered"])
            if max(planned - delivered, 0.0) <= 0:
                continue
            contract_id = int(row["contract_id"] or 0)
            if contract_id not in owner_cache:
                owner_cache[contract_id] = contract_owner_text(self.conn, contract_id)
            delivery_payload = row["delivery_payload_json"] if "delivery_payload_json" in row.keys() else ""
            contract_payload = row["contract_payload_json"] if "contract_payload_json" in row.keys() else ""
            config = _payload_value(delivery_payload, "configuration_type", "config_type", "konfigurasyon_tipi") or _payload_value(contract_payload, "configuration_type", "config_type", "konfigurasyon_tipi")
            date_text = normalize_report_date_display(row["planned_acceptance_date"] or row["acceptance_date"] or "")
            result.append(DeliveryRow(contract_id=contract_id, delivery_id=int(row["delivery_id"] or 0), platform=str(row["platform_name"] or "Tanımsız"), contract=str(row["contract_no"] or "-"), system=str(row["system_name"] or "Tanımsız Sistem"), owner=owner_cache.get(contract_id) or "-", user=str(row["delivery_user_name"] or "Tanımsız"), domestic=normalize_yi_yd(row["delivery_user_yi_yd"] or row["contract_yi_yd"] or "-"), delivery=str(row["delivery_name"] or "-"), date_text=date_text, level="1", part=str(row["component_name"] or "-"), planned=planned, delivered=delivered, config_type=config, note=str(row["delivery_note"] or row["contract_note"] or ""), status=str(row["delivery_status"] or row["contract_status"] or "-")))
        return result

    def _refresh_delivery_table(self, rows: list[DeliveryRow]) -> None:
        """Populate the tree as Contract + System/Paket groups.

        Sözleşme için ayrı bir üst grup açılmaz. Ana satır her zaman
        ``Sözleşme No + Sistem / Paket`` bloğudur; parça satırlarında
        tekrar eden sözleşme/sistem bilgileri boş bırakılarak Excel'deki
        hücre birleştirme görünümü uygulamada da okunur hale getirilir.
        """
        self.delivery_tree.clear()
        header = self.delivery_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.resizeSection(0, 180)

        if not rows:
            return

        bold_font = QFont()
        bold_font.setBold(True)

        grouped: dict[tuple[str, str], list[DeliveryRow]] = defaultdict(list)
        for row in rows:
            grouped[(row.contract, row.system or "Tanımsız Sistem")].append(row)

        for contract_no, system_name in sorted(grouped.keys(), key=lambda item: (item[0], item[1])):
            group_rows = sorted(
                grouped[(contract_no, system_name)],
                key=lambda r: (str(r.delivery), str(r.date_text), str(r.user), str(r.part)),
            )

            deliveries = sorted({r.delivery for r in group_rows if r.delivery and r.delivery != "-"})
            dates = sorted({str(r.date_text or "").strip() for r in group_rows if str(r.date_text or "").strip()})
            owners = [owner.strip() for r in group_rows for owner in str(r.owner or "").split(",") if owner.strip()]
            users = [r.user for r in group_rows if r.user]
            yi_yd_values = [normalize_yi_yd(r.domestic) for r in group_rows if normalize_yi_yd(r.domestic) in {"Yİ", "YD"}]
            statuses = [r.status for r in group_rows if r.status and r.status != "-"]
            parts = sorted({r.part for r in group_rows if r.part and r.part != "-"})

            planned_total = sum(_safe_float(r.planned) for r in group_rows)
            delivered_total = sum(_safe_float(r.delivered) for r in group_rows)
            remaining_total = sum(_safe_float(r.remaining) for r in group_rows)

            display_no = contract_no
            if len(contract_no) > 22:
                display_no = contract_no[:19] + "..."

            parent = QTreeWidgetItem(self.delivery_tree)
            parent.setText(0, display_no)
            parent.setData(0, Qt.ToolTipRole, contract_no)
            parent.setText(1, system_name)
            parent.setText(2, f"{len(deliveries)} teslimat · {len(group_rows)} satır" if deliveries else f"{len(group_rows)} satır")
            parent.setText(3, _short_join(dates, limit=2))
            parent.setText(4, _short_join(owners, limit=2, empty="-"))
            parent.setText(5, _short_join(users, limit=2, empty="Tanımsız"))
            parent.setText(6, _short_join(yi_yd_values, limit=2, empty="-"))
            parent.setText(8, f"{len(parts)} parça")
            parent.setText(9, _fmt_amount(planned_total))
            parent.setText(10, _fmt_amount(delivered_total))
            parent.setText(11, _fmt_amount(remaining_total))
            parent.setText(14, _short_join(statuses, limit=2))
            parent.setExpanded(False)

            for col in range(self.delivery_tree.columnCount()):
                parent.setBackground(col, QColor("#dceafa"))
                parent.setForeground(col, QColor("#002060"))
                parent.setFont(col, bold_font)
                if col != 0:
                    parent.setToolTip(col, parent.text(col))

            previous_merge_key: tuple[str, str, str, str, str] | None = None
            for i, row in enumerate(group_rows):
                child = QTreeWidgetItem(parent)
                merge_key = (row.delivery, row.date_text, row.owner, row.user, row.domestic)
                repeated = merge_key == previous_merge_key
                previous_merge_key = merge_key

                child.setText(0, "")
                child.setText(1, "")
                child.setText(2, "" if repeated else row.delivery)
                child.setText(3, "" if repeated else row.date_text)
                child.setText(4, "" if repeated else row.owner)
                child.setText(5, "" if repeated else row.user)
                child.setText(6, "" if repeated else row.domestic)
                child.setText(7, row.level)
                child.setText(8, row.part)
                child.setText(9, _fmt_amount(row.planned))
                child.setText(10, _fmt_amount(row.delivered))
                child.setText(11, _fmt_amount(row.remaining))
                child.setText(12, row.config_type)
                child.setText(13, row.note)
                child.setText(14, row.status)

                bg_color = QColor("#ffffff") if i % 2 == 0 else QColor("#f4f9ff")
                for col in range(self.delivery_tree.columnCount()):
                    child.setBackground(col, bg_color)
                    child.setToolTip(col, child.text(col))

                status_lower = row.status.lower()
                if "risk" in status_lower or "gecik" in status_lower:
                    child.setForeground(14, QColor(RED))
                elif "tamam" in status_lower or "teslim" in status_lower:
                    child.setForeground(14, QColor(GREEN))

    def _matrix_rows(self, rows: list[DeliveryRow]) -> tuple[list[str], list[list[Any]]]:
        users = sorted({r.user for r in rows})
        user_dates = {u: sorted({r.date_text for r in rows if r.user == u and r.date_text}) for u in users}
        headers = [
            "Sözleşme No", "Sistem / Paket", "Seviye", "Parça Numarası",
            "Parça", "Teslimat Zamanı",
        ] + [f"{u}\n{', '.join(user_dates.get(u, [])[:2])}" for u in users] + ["TOPLAM"]

        by_system_part: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        system_dates: dict[tuple[str, str], set[str]] = defaultdict(set)
        part_dates: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        system_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for row in rows:
            system_key = (row.contract, row.system or "Tanımsız Sistem")
            part_key = (row.contract, row.system or "Tanımsız Sistem", row.part)
            by_system_part[part_key][row.user] += row.remaining
            system_totals[system_key][row.user] += row.remaining
            if row.date_text:
                system_dates[system_key].add(row.date_text)
                part_dates[part_key].add(row.date_text)

        matrix_rows: list[list[Any]] = []
        for contract_no, system_name in sorted(system_totals.keys(), key=lambda item: (item[0], item[1])):
            totals_by_user = system_totals[(contract_no, system_name)]
            total_values = [_fmt_amount(totals_by_user.get(user, 0)) for user in users]
            total = sum(totals_by_user.values())
            matrix_rows.append([
                contract_no, system_name, "", "", "Sistem Toplamı",
                ", ".join(sorted(system_dates[(contract_no, system_name)])[:3]),
                *total_values, _fmt_amount(total),
            ])

            for _c, _s, part in sorted(k for k in by_system_part if k[0] == contract_no and k[1] == system_name):
                values_by_user = by_system_part[(contract_no, system_name, part)]
                values = [_fmt_amount(values_by_user.get(user, 0)) for user in users]
                part_total = sum(values_by_user.values())
                matrix_rows.append([
                    "", "", "1", "", part,
                    ", ".join(sorted(part_dates[(contract_no, system_name, part)])[:3]),
                    *values, _fmt_amount(part_total),
                ])

        return headers, matrix_rows

    def _refresh_matrix_table(self, rows: list[DeliveryRow]) -> None:
        headers, matrix_rows = self._matrix_rows(rows)
        self.matrix_view.setModel(SimpleTableModel(headers, matrix_rows, self))

    def _refresh_kpis(self, rows: list[DeliveryRow]) -> None:
        # Sözleşme adedi bileşen/adet toplamı değildir; filtre sonrası benzersiz
        # sözleşme sayısıdır. Kullanıcı da filtre sonrası benzersiz teslim kullanıcısıdır.
        contract_count = len({
            str(r.contract or "").strip()
            for r in rows
            if str(r.contract or "").strip() and str(r.contract or "").strip() != "-"
        })
        user_count = len({
            str(r.user or "").strip()
            for r in rows
            if str(r.user or "").strip() and str(r.user or "").strip() != "Tanımsız"
        })
        if hasattr(self, "contract_count_value"):
            self.contract_count_value.setText(_fmt_amount(contract_count))
        if hasattr(self, "user_count_value"):
            self.user_count_value.setText(_fmt_amount(user_count))

    def _refresh_dashboard_charts(self, rows: list[DeliveryRow]) -> None:
        part_totals: dict[str, float] = defaultdict(float)
        yi_yd_totals: dict[str, float] = defaultdict(float)
        yearly: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        user_part: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in rows:
            part_totals[row.part] += row.remaining
            yi_yd_totals[row.domestic] += row.remaining
            if row.year:
                yearly[row.year][0] += row.remaining; yearly[row.year][1] += row.delivered
            user_part[row.user][row.part] += row.remaining
        part_data = sorted(part_totals.items(), key=lambda item: item[1], reverse=True)
        self.part_bar.set_data(part_data)
        self.donut.set_data(yi_yd_totals.get("Yİ", 0), yi_yd_totals.get("YD", 0))
        self.trend.set_data([(year, values[0], values[1]) for year, values in sorted(yearly.items())])
        users = sorted(user_part)
        parts = [name for name, _ in part_data[:8]]
        values = {part: [user_part[user].get(part, 0) for user in users] for part in parts}
        self.chart.set_data(users, parts, values)

    def _current_actor_name(self) -> str:
        try:
            actor = self.store.current_actor() if hasattr(self.store, "current_actor") else None
        except Exception:
            actor = None
        if isinstance(actor, dict):
            return str(actor.get("full_name") or actor.get("name") or actor.get("username") or "Kullanıcı")
        return str(actor or "Kullanıcı")

    def _selected_contracts_for_rev(self, filters: dict[str, Any]) -> list[str]:
        selected_contracts = sorted({str(row.contract) for row in self.filtered_rows if str(row.contract or "").strip()})
        if selected_contracts:
            return selected_contracts
        if filters.get("contract") and filters.get("contract") != "Tüm seçili sözleşmeler":
            return [str(filters.get("contract"))]
        return ["__NO_MATCH__"] if not self.filtered_rows else []

    def _rev_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        log_filters = dict(filters or {})
        log_filters["_selected_contracts"] = self._selected_contracts_for_rev(filters)
        return log_filters

    def _refresh_rev_table(self, filters: dict[str, Any]) -> None:
        from src.services.delivery_schedule_excel_exporter import build_delivery_schedule_revision_rows

        # REV Takip şu an sadece kullanıcı tarafından girilen manuel satırları gösterir.
        # Uygulama activity_logs kayıtları bilerek rapora alınmaz.
        self._rev_rows = build_delivery_schedule_revision_rows(self.store, limit=200, filters=None)
        rows = [
            [
                str(log.get("revision_info") or log.get("field") or log.get("revision") or ""),
                str(log.get("date") or ""),
                str(log.get("description") or ""),
            ]
            for log in self._rev_rows
        ]
        self.rev_view.setModel(SimpleTableModel(["Revizyon Bilgisi", "Tarih", "Açıklama"], rows, self))

    def load_activity_log_preview(self, filters: dict[str, Any]) -> list[list[str]]:
        self._refresh_rev_table(filters)
        model = self.rev_view.model()
        return [list(getattr(model, "rows", [])[i]) for i in range(len(getattr(model, "rows", [])))]

    def _show_rev_context_menu(self, pos):
        index = self.rev_view.indexAt(pos)
        if index.isValid() and not self.rev_view.selectionModel().isRowSelected(index.row(), QModelIndex()):
            self.rev_view.selectRow(index.row())
        selected_rows = sorted({idx.row() for idx in self.rev_view.selectionModel().selectedRows()}) if self.rev_view.selectionModel() else []
        has_real_selection = any(0 <= row < len(self._rev_rows) for row in selected_rows)
        single_row = selected_rows[0] if len(selected_rows) == 1 else -1
        single_data = self._rev_rows[single_row] if 0 <= single_row < len(self._rev_rows) else None

        menu = QMenu(self)
        add_action = menu.addAction("Satır Ekle")
        edit_action = menu.addAction("Satırı Düzenle")
        delete_action = menu.addAction("Seçili Satırı Sil")
        menu.addSeparator()
        refresh_action = menu.addAction("Yenile")

        edit_action.setEnabled(bool(single_data))
        delete_action.setEnabled(has_real_selection)

        action = menu.exec(self.rev_view.viewport().mapToGlobal(pos))
        if action == add_action:
            self._add_rev_row()
        elif action == edit_action and single_data:
            self._edit_rev_row(single_data)
        elif action == delete_action:
            self._delete_selected_rev_rows(selected_rows)
        elif action == refresh_action:
            self.refresh_preview()

    def _default_rev_values(self) -> dict[str, Any]:
        return {
            "revision_info": "",
            "revision_date": "",
            "description": "",
        }

    def _add_rev_row(self):
        from src.services.delivery_schedule_excel_exporter import save_manual_revision_row

        dlg = RevisionRowDialog(self, self._default_rev_values(), "REV Satırı Ekle")
        if dlg.exec() and dlg.result:
            values = dict(dlg.result)
            values["created_by"] = self._current_actor_name()
            save_manual_revision_row(self.store, values)
            self.refresh_preview()

    def _edit_rev_row(self, row: dict[str, Any]):
        from src.services.delivery_schedule_excel_exporter import save_manual_revision_row

        manual_id = int(row.get("manual_id") or 0)
        if manual_id <= 0:
            return
        defaults = {
            "revision_info": row.get("revision_info") or row.get("field") or row.get("revision") or "",
            "revision_date": row.get("date") or "",
            "description": row.get("description") or "",
        }
        dlg = RevisionRowDialog(self, defaults, "REV Satırını Düzenle")
        if dlg.exec() and dlg.result:
            values = dict(dlg.result)
            values["updated_by"] = self._current_actor_name()
            save_manual_revision_row(self.store, values, row_id=manual_id)
            self.refresh_preview()

    def _delete_selected_rev_rows(self, selected_rows: list[int]):
        from src.services.delivery_schedule_excel_exporter import hide_revision_row

        rows = [self._rev_rows[i] for i in selected_rows if 0 <= i < len(self._rev_rows)]
        if not rows:
            return
        msg = "Bu REV satırı silinecek. Devam edilsin mi?"
        if len(rows) > 1:
            msg = f"{len(rows)} REV satırı silinecek. Devam edilsin mi?"
        if QMessageBox.question(self, "REV satırı sil", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        actor = self._current_actor_name()
        for row in rows:
            hide_revision_row(self.store, row, actor=actor)
        self.refresh_preview()

    # ── Export with threading & loading overlay ──────────────────────────────

    def _get_store_path(self) -> Optional[str]:
        """Return the .sts file path for worker-thread SQLite access."""
        store = self.store
        if store is None:
            return None
        db = getattr(store, "db", None)
        path = getattr(db, "path", None) or getattr(store, "path", None)
        return str(path) if path else None

    def _set_ui_enabled(self, enabled: bool) -> None:
        for widget in (self.export_btn, self.refresh_btn, self.tabs,
                       self.platform, self.domestic, self.owner, self.contract, self.status, self.year_range):
            widget.setEnabled(enabled)

    def on_export_excel_clicked(self):
        from src.services.delivery_schedule_excel_exporter import (
            EXCEL_REQUIRED_MESSAGE,
            ExcelComUnavailableError,
            load_delivery_schedule_rows,
            suggested_output_filename,
        )

        filters = self.collect_filters()
        if not filters.get("year_range_valid"):
            QMessageBox.warning(self, "Excel Oluştur", "Yıl / aralık formatı hatalı. Örnek: 2026 veya 2026-2027")
            return

        preview_rows = load_delivery_schedule_rows(self.store, filters=filters)
        suggested_name = suggested_output_filename(preview_rows)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Tahmini Teslimat Takvimi Excel Kaydet",
            suggested_name,
            "Excel Dosyası (*.xlsx)",
        )
        if not output_path:
            return

        store_path = self._get_store_path()
        if not store_path:
            # Fallback: run synchronously if no path available
            try:
                from src.services.delivery_schedule_excel_exporter import export_delivery_schedule_report
                result = export_delivery_schedule_report(self.store, output_path, filters=filters)
                QMessageBox.information(self, "Excel Oluştur", f"Excel raporu oluşturuldu.\n\nDosya: {result.get('output_path')}\nSatır sayısı: {result.get('row_count')}")
            except Exception as exc:
                from src.services.delivery_schedule_excel_exporter import ExcelComUnavailableError as ECUE
                if isinstance(exc, ECUE):
                    QMessageBox.warning(self, "Microsoft Excel gerekli", EXCEL_REQUIRED_MESSAGE)
                else:
                    QMessageBox.critical(self, "Excel Oluştur", f"Excel raporu oluşturulamadı:\n{exc}")
            return

        # Save store before export
        if hasattr(self.store, "save"):
            try:
                self.store.save()
            except Exception:
                pass

        # Show loading overlay
        self._loading_overlay = ExcelLoadingOverlay(self)
        self._loading_overlay.setGeometry(self.rect())
        self._loading_overlay.show()
        self._loading_overlay.raise_()
        self._set_ui_enabled(False)

        # Start worker thread
        self._export_thread = QThread(self)
        self._export_worker = ExcelExportWorker(store_path, output_path, filters)
        self._export_worker.moveToThread(self._export_thread)

        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._on_export_thread_finished)

        self._export_thread.start()

    def _on_export_progress(self, value: int, message: str):
        if self._loading_overlay:
            self._loading_overlay.update_progress(value, message)

    def _on_export_finished(self, result: dict):
        self._close_loading()
        self._set_ui_enabled(True)
        QMessageBox.information(
            self,
            "Excel Oluştur",
            f"Excel raporu oluşturuldu.\n\nDosya: {result.get('output_path')}\nSatır sayısı: {result.get('row_count')}",
        )

    def _on_export_failed(self, error: str):
        from src.services.delivery_schedule_excel_exporter import EXCEL_REQUIRED_MESSAGE, ExcelComUnavailableError
        self._close_loading()
        self._set_ui_enabled(True)
        if "excel" in error.lower() or "com" in error.lower() or "win32" in error.lower():
            QMessageBox.warning(self, "Microsoft Excel gerekli", EXCEL_REQUIRED_MESSAGE)
        else:
            QMessageBox.critical(self, "Excel Oluştur", f"Excel raporu oluşturulamadı:\n{error}")

    def _close_loading(self):
        overlay = self._loading_overlay
        self._loading_overlay = None
        if overlay:
            try:
                overlay.close()
            except RuntimeError:
                pass

    def _on_export_thread_finished(self):
        thread = self.sender()
        self._export_thread = None
        self._export_worker = None
        if thread is not None:
            try:
                thread.deleteLater()
            except RuntimeError:
                pass

    def _is_export_running(self) -> bool:
        thread = self._export_thread
        if thread is None:
            return False
        try:
            return bool(thread.isRunning())
        except RuntimeError:
            # PySide wrapper can outlive the C++ QThread after deleteLater().
            self._export_thread = None
            self._export_worker = None
            return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        overlay = self._loading_overlay
        if overlay:
            try:
                overlay.setGeometry(self.rect())
            except RuntimeError:
                self._loading_overlay = None

    def closeEvent(self, event):
        if self._is_export_running():
            QMessageBox.warning(self, "Export Devam Ediyor", "Excel export işlemi devam ediyor. Lütfen bekleyin.")
            event.ignore()
            return
        super().closeEvent(event)

    def _extra_style(self):
        return f"""
        QFrame#filterPanel, QFrame#reportCard, QFrame#kpiCard {{
            background:#ffffff;
            border:1px solid {GRID};
            border-radius:16px;
        }}
        QFrame#filterPanel {{ padding:4px; }}
        QFrame#filterRow {{
            background: transparent;
            border: none;
            margin: 0px;
            padding: 0px;
        }}
        QFrame#filterRow QLabel,
        QFrame#filterRow QLabel#fieldLabel {{
            background: transparent;
            background-color: transparent;
            border: none;
            margin: 0px;
        }}
        QLabel#panelTitle {{ color:#002060; font-size:18px; font-weight:900; background:transparent; }}
        QLabel#mainTitle {{ color:#002060; font-size:22px; font-weight:900; background:transparent; }}
        QLabel#fieldLabel {{ color:#415a86; font-size:11px; font-weight:900; background:transparent; padding-top:8px; }}
        QLabel#kpiValue {{ color:#075bd8; font-size:28px; font-weight:900; background:transparent; }}
        QLabel#infoLabel {{ color:transparent; background:transparent; font-size:1px; min-height:0px; max-height:0px; padding:0px; margin:0px; border:0px; }}
        QFrame#filterStats {{
            background:#f8fbff;
            border:1px solid #cfe0f4;
            border-radius:12px;
            margin-top:6px;
        }}
        QFrame#filterStatBox {{
            background:transparent;
            border:none;
        }}
        QLabel#filterStatTitle {{
            color:#415a86;
            background:transparent;
            border:none;
            font-size:10px;
            font-weight:900;
        }}
        QLabel#filterStatValue {{
            color:#075bd8;
            background:transparent;
            border:none;
            font-size:20px;
            font-weight:950;
        }}

        QPushButton#reportPrimaryButton {{
            background:#0b4aa2;
            color:#ffffff;
            border:1px solid #0b4aa2;
            border-radius:10px;
            padding:9px 18px;
            min-height:18px;
            font-weight:900;
        }}
        QPushButton#reportPrimaryButton:hover {{ background:#075bd8; border-color:#075bd8; }}
        QPushButton#reportPrimaryButton:disabled {{ background:#a0aec0; border-color:#a0aec0; }}
        QPushButton#reportSecondaryButton {{
            background:#f8fbff;
            color:#003b83;
            border:1px solid #bfd5f2;
            border-radius:10px;
            padding:9px 18px;
            min-height:18px;
            font-weight:900;
        }}
        QPushButton#reportSecondaryButton:hover {{ background:#eaf4ff; border-color:#7fb2f0; }}
        QPushButton#reportSecondaryButton:disabled {{ background:#f0f0f0; color:#a0aec0; }}

        QTabWidget::pane {{
            border:1px solid {GRID};
            border-radius:12px;
            background:#ffffff;
            top:-1px;
        }}
        QTabBar {{ background:transparent; }}
        QTabBar::tab {{
            background:#f8fbff;
            color:#415a86;
            border:1px solid transparent;
            border-radius:11px;
            padding:10px 20px;
            margin:0 5px 7px 0;
            font-weight:900;
            min-width:105px;
        }}
        QTabBar::tab:hover {{ background:#eaf4ff; color:#003b83; border-color:#bfd5f2; }}
        QTabBar::tab:selected {{
            background:{NAVY};
            color:white;
            border:1px solid {NAVY};
            border-radius:11px;
        }}

        QComboBox, QLineEdit {{
            background:#f8fbff;
            color:#002060;
            border:1px solid #bfd5f2;
            border-radius:10px;
            padding:7px 11px;
            min-height:20px;
            font-weight:800;
        }}
        QComboBox:hover, QLineEdit:hover {{ border-color:#7fb2f0; background:#ffffff; }}
        QComboBox:focus, QLineEdit:focus {{ border:2px solid #2b7ddd; background:#ffffff; }}
        QComboBox::drop-down {{
            subcontrol-origin:padding;
            subcontrol-position:top right;
            width:30px;
            border-left:1px solid #d7e6f8;
            border-top-right-radius:10px;
            border-bottom-right-radius:10px;
        }}
        QComboBox::down-arrow {{ image:url("{ARROW_ICON_PATH}"); width:10px; height:6px; }}
        QComboBox QAbstractItemView {{
            background:#ffffff;
            color:#002060;
            border:1px solid #bfd5f2;
            border-radius:8px;
            padding:4px;
            outline:0;
            selection-background-color:#dbeafe;
            selection-color:#002060;
        }}

        QHeaderView::section {{
            background:{NAVY};
            color:white;
            font-weight:900;
            padding:10px 8px;
            border:1px solid #31548b;
        }}
        QTableView {{
            background:#ffffff;
            gridline-color:{GRID};
            alternate-background-color:#f4f9ff;
            selection-background-color:#dbeafe;
            selection-color:#002060;
            border:1px solid {GRID};
            border-radius:12px;
        }}
        QTableView::item {{ padding:8px 7px; border:0; }}
        QTableView::item:selected {{ background:#dbeafe; color:#002060; }}

        QScrollBar:vertical {{
            background:#eef4fb;
            width:10px;
            margin:2px;
            border-radius:5px;
        }}
        QScrollBar::handle:vertical {{ background:#9fb6d4; min-height:34px; border-radius:5px; }}
        QScrollBar::handle:vertical:hover {{ background:#6f8fb8; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; border:0; background:transparent; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        QScrollBar:horizontal {{
            background:#eef4fb;
            height:10px;
            margin:2px;
            border-radius:5px;
        }}
        QScrollBar::handle:horizontal {{ background:#9fb6d4; min-width:34px; border-radius:5px; }}
        QScrollBar::handle:horizontal:hover {{ background:#6f8fb8; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; border:0; background:transparent; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:transparent; }}
        QAbstractScrollArea {{ background:#ffffff; border:none; }}
        QLineEdit[invalid="true"] {{ border:2px solid {RED}; background:#fff1f2; }}
        """
