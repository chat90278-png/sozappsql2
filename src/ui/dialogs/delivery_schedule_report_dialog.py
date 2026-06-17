from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import re
import sqlite3
from typing import Any, Iterable, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt
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
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableView,
    QVBoxLayout,
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
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("/", "-").replace(".", "-").upper()
    parts = [p.strip() for p in text.split("-") if p.strip()]
    if len(parts) != 3:
        year = extract_year_from_date_text(text)
        return f"TBD-TBD-{year}" if year else text

    def is_year(part: str) -> bool:
        return bool(re.fullmatch(r"(19\d{2}|20\d{2}|21\d{2})", part))

    def two_digit(part: str) -> str:
        return part.zfill(2) if part.isdigit() and len(part) <= 2 else part

    if is_year(parts[0]):
        year, month, day = parts[0], parts[1], parts[2]
        day = "TBD" if day == "TBD" else two_digit(day)
        month = "TBD" if month == "TBD" else two_digit(month)
        return f"{day}-{month}-{year}"
    if is_year(parts[2]):
        day, month, year = parts[0], parts[1], parts[2]
        day = "TBD" if day == "TBD" else two_digit(day)
        month = "TBD" if month == "TBD" else two_digit(month)
        return f"{day}-{month}-{year}"
    return text


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_amount(value: object) -> str:
    number = _safe_float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


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

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self.data = data[:8]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(16, 16, -16, -16)
        p.setPen(QColor("#002060")); p.drawText(r, Qt.AlignTop | Qt.AlignLeft, "Parça Bazlı Planlanan Miktar")
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

    def set_data(self, data: list[tuple[int, float, float]]) -> None:
        self.data = data
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
        for i in range(6):
            y = chart.bottom() - int(chart.height() * i / 5)
            p.setPen(QPen(QColor("#d8d8d8"))); p.drawLine(chart.left(), y, chart.right(), y)
            p.setPen(QColor("#334155")); p.drawText(chart.left() - 42, y + 4, _fmt_amount(maxv * i / 5))
        group_w = max(self.group_width, chart.width() / max(len(self.users), 1)); bar_w = max(4, min(12, int(group_w / (len(self.parts) + 4))))
        for ui, user in enumerate(self.users):
            base_x = chart.left() + ui * group_w + group_w * .16
            for pi, part in enumerate(self.parts):
                vals = self.values.get(part, [])
                value = vals[ui] if ui < len(vals) else 0
                h = int(chart.height() * value / maxv)
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


class DeliveryScheduleReportDialog(QDialog):
    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store or getattr(parent, "store", None)
        self.conn = _conn_from_store(self.store)
        self.all_rows: list[DeliveryRow] = []
        self.filtered_rows: list[DeliveryRow] = []
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
        h = QLabel("Rapor Ayarları"); h.setObjectName("panelTitle"); lay.addWidget(h)
        self.platform = self._combo(["Tümü"]); self.year_range = QLineEdit(str(date.today().year)); self.domestic = self._combo(["Tümü", "Yİ", "YD"]); self.owner = self._combo(["Tümü"]); self.contract = self._combo(["Tüm seçili sözleşmeler"]); self.status = self._combo(["Tümü"] + list(STATUS_VALUES))
        for label, widget in [("PLATFORM", self.platform), ("YIL / ARALIK", self.year_range), ("Yİ / YD", self.domestic), ("SÖZLEŞME SAHİBİ", self.owner), ("SÖZLEŞME", self.contract), ("DURUM", self.status)]:
            l = QLabel(label); l.setObjectName("fieldLabel"); lay.addWidget(l); lay.addWidget(widget)
        btn = QPushButton("Önizlemeyi Yenile"); btn.clicked.connect(self.refresh_preview); lay.addWidget(btn); lay.addStretch(); return frame

    def _combo(self, items):
        c = QComboBox(); c.addItems(items); return c

    def _dashboard_tab(self):
        w = QScrollArea(); w.setWidgetResizable(True); host = QWidget(); lay = QVBoxLayout(host)
        self.kpi_grid = QGridLayout(); lay.addLayout(self.kpi_grid)
        upper = QHBoxLayout()
        self.part_bar = PartBarWidget(); self.donut = DonutDistributionWidget(); self.trend = TrendLineWidget()
        for widget in (self.part_bar, self.donut, self.trend):
            card = QFrame(); card.setObjectName("reportCard"); cl = QVBoxLayout(card); cl.addWidget(widget); upper.addWidget(card, 1)
        lay.addLayout(upper)
        self.chart = GroupedBarPreview()
        self.chart_scroll = QScrollArea()
        self.chart_scroll.setWidgetResizable(False)
        self.chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chart_scroll.setWidget(self.chart)
        card = QFrame(); card.setObjectName("reportCard"); cl = QVBoxLayout(card); cl.addWidget(self.chart_scroll); lay.addWidget(card)
        w.setWidget(host); return w

    def _delivery_tab(self): self.delivery_view = self._table(); return self.delivery_view
    def _matrix_tab(self): self.matrix_view = self._table(); return self.matrix_view
    def _rev_tab(self): self.rev_view = self._table(); return self.rev_view

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
        self.clear_preview()

    def _set_combo_items(self, combo: QComboBox, items: list[str], first: str) -> None:
        current = combo.currentText()
        combo.blockSignals(True); combo.clear(); combo.addItem(first)
        for item in items:
            if item and item != first:
                combo.addItem(item)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def populate_filters_from_rows(self, rows: list[DeliveryRow]) -> None:
        self._set_combo_items(self.platform, sorted({r.platform for r in rows if r.platform}), "Tümü")
        owners = sorted({owner.strip() for r in rows for owner in str(r.owner or "").split(",") if owner.strip() and owner.strip() != "-"})
        self._set_combo_items(self.owner, owners, "Tümü")
        self._set_combo_items(self.contract, sorted({r.contract for r in rows if r.contract}), "Tüm seçili sözleşmeler")
        self._set_combo_items(self.status, list(STATUS_VALUES), "Tümü")
        years = sorted({r.year for r in rows if r.year})
        if years and self.year_range.text().strip() in {"", str(date.today().year)}:
            self.year_range.setText(str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}")

    def collect_filters(self) -> dict[str, Any]:
        text = self.year_range.text().strip()
        start_year, end_year = parse_year_range(text)
        ok = start_year is not None and end_year is not None
        self.year_range.setProperty("invalid", not ok)
        self.year_range.style().unpolish(self.year_range); self.year_range.style().polish(self.year_range)
        return {"platform": self.platform.currentText(), "year_range": text, "start_year": start_year, "end_year": end_year, "year_range_valid": ok, "yi_yd": self.domestic.currentText(), "owner": self.owner.currentText(), "contract": self.contract.currentText(), "status": self.status.currentText()}

    def build_report_payload(self) -> dict[str, Any]:
        return {"filters": self.collect_filters(), "generated_at": date.today().isoformat(), "deliveries": [self._row_payload(row) for row in self.filtered_rows], "matrix": self._matrix_rows(self.filtered_rows)[1], "activity_logs": self.load_activity_log_preview(self.collect_filters())}

    def _row_payload(self, row: DeliveryRow) -> dict[str, Any]:
        return {"contract_id": row.contract_id, "delivery_id": row.delivery_id, "platform": row.platform, "contract": row.contract, "owner": row.owner, "delivery_user": row.user, "yi_yd": row.domestic, "delivery": row.delivery, "date": row.date_text, "level": row.level, "part": row.part, "planned": row.planned, "delivered": row.delivered, "remaining": row.remaining, "config_type": row.config_type, "note": row.note, "status": row.status}

    def clear_preview(self) -> None:
        self.filtered_rows = []
        if not hasattr(self, "delivery_view"):
            return
        self.info_label.setText("" if self.conn else "Açık STS veri dosyası bulunamadı; rapor boş gösteriliyor.")
        self._refresh_kpis([])
        self._refresh_dashboard_charts([])
        self._refresh_delivery_table([])
        self._refresh_matrix_table([])
        self.rev_view.setModel(SimpleTableModel(["Tarih", "Kullanıcı", "Sözleşme", "Teslimat", "Alan", "Eski Değer", "Yeni Değer", "Açıklama"], [], self))

    def refresh_preview(self, *_args):
        if not hasattr(self, "delivery_view"):
            return
        filters = self.collect_filters()
        if not filters["year_range_valid"]:
            self.info_label.setText("Yıl / aralık formatı hatalı. Örnek: 2026 veya 2026-2027")
            return
        rows = list(self.all_rows)
        rows = [r for r in rows if r.year is not None and filters["start_year"] <= r.year <= filters["end_year"]]
        if filters["platform"] != "Tümü": rows = [r for r in rows if r.platform == filters["platform"]]
        if filters["yi_yd"] != "Tümü": rows = [r for r in rows if r.domestic == filters["yi_yd"]]
        if filters["owner"] != "Tümü": rows = [r for r in rows if filters["owner"] in [owner.strip() for owner in str(r.owner or "").split(",")]]
        if filters["status"] != "Tümü": rows = [r for r in rows if r.status == filters["status"]]
        if filters["contract"] != "Tüm seçili sözleşmeler": rows = [r for r in rows if r.contract == filters["contract"]]
        self.filtered_rows = rows
        self.info_label.setText("" if self.conn else "Açık STS veri dosyası bulunamadı; rapor boş gösteriliyor.")
        self._refresh_kpis(rows)
        self._refresh_dashboard_charts(rows)
        self._refresh_delivery_table(rows)
        self._refresh_matrix_table(rows)
        self.rev_view.setModel(SimpleTableModel(["Tarih", "Kullanıcı", "Sözleşme", "Teslimat", "Alan", "Eski Değer", "Yeni Değer", "Açıklama"], self.load_activity_log_preview(filters), self))

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
                       du.name AS delivery_user_name, du.yi_yd AS delivery_user_yi_yd, comp.name AS component_name,
                       dc.planned, dc.delivered
                FROM deliveries d
                JOIN contracts c ON c.id = d.contract_id
                LEFT JOIN platforms p ON p.id = c.platform_id
                LEFT JOIN users du ON du.id = d.delivery_user_id
                JOIN delivery_components dc ON dc.delivery_id = d.id
                JOIN components comp ON comp.id = dc.component_id
                ORDER BY p.name, c.contract_no, d.sort_order, d.id, comp.name
                """
            ).fetchall()
        except Exception as exc:
            self.info_label.setText(f"Rapor verisi okunamadı: {exc}")
            return []
        result: list[DeliveryRow] = []
        owner_cache: dict[int, str] = {}
        for row in rows:
            contract_id = int(row["contract_id"] or 0)
            if contract_id not in owner_cache:
                owner_cache[contract_id] = contract_owner_text(self.conn, contract_id)
            delivery_payload = row["delivery_payload_json"] if "delivery_payload_json" in row.keys() else ""
            contract_payload = row["contract_payload_json"] if "contract_payload_json" in row.keys() else ""
            config = _payload_value(delivery_payload, "configuration_type", "config_type", "konfigurasyon_tipi") or _payload_value(contract_payload, "configuration_type", "config_type", "konfigurasyon_tipi")
            date_text = normalize_report_date_display(row["planned_acceptance_date"] or row["acceptance_date"] or "")
            result.append(DeliveryRow(contract_id=contract_id, delivery_id=int(row["delivery_id"] or 0), platform=str(row["platform_name"] or "Tanımsız"), contract=str(row["contract_no"] or "-"), owner=owner_cache.get(contract_id) or "-", user=str(row["delivery_user_name"] or "Tanımsız"), domestic=str(row["delivery_user_yi_yd"] or row["contract_yi_yd"] or "-"), delivery=str(row["delivery_name"] or "-"), date_text=date_text, level="1", part=str(row["component_name"] or "-"), planned=_safe_float(row["planned"]), delivered=_safe_float(row["delivered"]), config_type=config, note=str(row["delivery_note"] or row["contract_note"] or ""), status=str(row["delivery_status"] or row["contract_status"] or "-")))
        return result

    def _refresh_delivery_table(self, rows: list[DeliveryRow]) -> None:
        headers = ["Sözleşme", "Sözleşme Sahibi", "Teslim Kullanıcısı", "Yİ/YD", "Teslimat", "Tarih", "Seviye", "Parça", "Plan", "Teslim", "Kalan", "Konfigürasyon Tipi", "Opsiyon / Not", "Durum"]
        table_rows = [[r.contract, r.owner, r.user, r.domestic, r.delivery, r.date_text, r.level, r.part, _fmt_amount(r.planned), _fmt_amount(r.delivered), _fmt_amount(r.remaining), r.config_type, r.note, r.status] for r in rows]
        self.delivery_view.setModel(SimpleTableModel(headers, table_rows, self))

    def _matrix_rows(self, rows: list[DeliveryRow]) -> tuple[list[str], list[list[Any]]]:
        users = sorted({r.user for r in rows})
        user_dates = {u: sorted({r.date_text for r in rows if r.user == u and r.date_text}) for u in users}
        headers = ["Seviye", "Parça Numarası", "Teslimat Zamanı"] + [f"{u}\n{', '.join(user_dates.get(u, [])[:2])}" for u in users] + ["TOPLAM"]
        by_part: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        part_dates: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            by_part[row.part][row.user] += row.planned
            if row.date_text:
                part_dates[row.part].add(row.date_text)
        matrix_rows = []
        for part in sorted(by_part):
            values = [_fmt_amount(by_part[part].get(user, 0)) for user in users]
            total = sum(by_part[part].values())
            matrix_rows.append(["1", part, ", ".join(sorted(part_dates[part])[:3]), *values, _fmt_amount(total)])
        return headers, matrix_rows

    def _refresh_matrix_table(self, rows: list[DeliveryRow]) -> None:
        headers, matrix_rows = self._matrix_rows(rows)
        self.matrix_view.setModel(SimpleTableModel(headers, matrix_rows, self))

    def _refresh_kpis(self, rows: list[DeliveryRow]) -> None:
        while self.kpi_grid.count():
            item = self.kpi_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        risk_count = sum(1 for r in rows if r.remaining > 0 and "tamam" not in r.status.lower())
        vals = [("Planlanan", sum(r.planned for r in rows)), ("Teslim Edilen", sum(r.delivered for r in rows)), ("Kalan", sum(r.remaining for r in rows)), ("Kullanıcı", len({r.user for r in rows})), ("Sözleşme", len({r.contract for r in rows})), ("Riskli Satır", risk_count)]
        for i, (name, val) in enumerate(vals):
            card = QFrame(); card.setObjectName("kpiCard"); l = QVBoxLayout(card); a = QLabel(name.upper()); a.setObjectName("fieldLabel"); b = QLabel(_fmt_amount(val)); b.setObjectName("kpiValue"); l.addWidget(a); l.addWidget(b); self.kpi_grid.addWidget(card, 0, i)

    def _refresh_dashboard_charts(self, rows: list[DeliveryRow]) -> None:
        part_totals: dict[str, float] = defaultdict(float)
        yi_yd_totals: dict[str, float] = defaultdict(float)
        yearly: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        user_part: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in rows:
            part_totals[row.part] += row.planned
            yi_yd_totals[row.domestic] += row.planned
            if row.year:
                yearly[row.year][0] += row.planned; yearly[row.year][1] += row.delivered
            user_part[row.user][row.part] += row.planned
        part_data = sorted(part_totals.items(), key=lambda item: item[1], reverse=True)
        self.part_bar.set_data(part_data)
        self.donut.set_data(yi_yd_totals.get("Yİ", 0), yi_yd_totals.get("YD", 0))
        self.trend.set_data([(year, values[0], values[1]) for year, values in sorted(yearly.items())])
        users = sorted(user_part)
        parts = [name for name, _ in part_data[:8]]
        values = {part: [user_part[user].get(part, 0) for user in users] for part in parts}
        self.chart.set_data(users, parts, values)

    def load_activity_log_preview(self, filters: dict[str, Any]) -> list[list[str]]:
        if not self.conn:
            return []
        try:
            logs = self.conn.execute(
                """
                SELECT l.*, p.name AS platform
                FROM activity_logs l
                LEFT JOIN platforms p ON p.id = l.platform_id
                WHERE lower(COALESCE(l.action,'')) LIKE '%delivery%'
                   OR lower(COALESCE(l.action,'')) LIKE '%contract%'
                   OR lower(COALESCE(l.action,'')) LIKE '%acceptance%'
                   OR lower(COALESCE(l.action,'')) LIKE '%teslim%'
                   OR lower(COALESCE(l.action,'')) LIKE '%sözleşme%'
                   OR lower(COALESCE(l.entity_type,'')) IN ('delivery','contract')
                ORDER BY l.created_at DESC
                LIMIT 200
                """
            ).fetchall()
        except Exception:
            return []
        rows = []
        for log in logs:
            before = _json_summary(log["before_json"] or "")
            after = _json_summary(log["after_json"] or "")
            payload = _json_summary(log["payload_json"] or "")
            field = payload or str(log["action"] or "")
            rows.append([str(log["created_at"] or ""), str(log["actor"] or "-"), str(log["contract_no"] or "-"), str(log["entity_key"] or "-"), field, before, after, str(log["message"] or "")])
        return rows

    def on_export_excel_clicked(self):
        from src.services.delivery_schedule_excel_exporter import (
            EXCEL_REQUIRED_MESSAGE,
            ExcelComUnavailableError,
            export_delivery_schedule_report,
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
        try:
            result = export_delivery_schedule_report(self.store, output_path, filters=filters)
        except ExcelComUnavailableError:
            QMessageBox.warning(self, "Microsoft Excel gerekli", EXCEL_REQUIRED_MESSAGE)
            return
        except Exception as exc:
            QMessageBox.critical(self, "Excel Oluştur", f"Excel raporu oluşturulamadı:\n{exc}")
            return
        QMessageBox.information(
            self,
            "Excel Oluştur",
            f"Excel raporu oluşturuldu.\n\nDosya: {result.get('output_path')}\nSatır sayısı: {result.get('row_count')}",
        )

    def _extra_style(self):
        return f"""
        QFrame#filterPanel, QFrame#reportCard, QFrame#kpiCard {{
            background:#ffffff;
            border:1px solid {GRID};
            border-radius:16px;
        }}
        QFrame#filterPanel {{ padding:4px; }}
        QLabel#panelTitle {{ color:#002060; font-size:18px; font-weight:900; background:transparent; }}
        QLabel#mainTitle {{ color:#002060; font-size:22px; font-weight:900; background:transparent; }}
        QLabel#fieldLabel {{ color:#415a86; font-size:11px; font-weight:900; background:transparent; padding-top:8px; }}
        QLabel#kpiValue {{ color:#075bd8; font-size:28px; font-weight:900; background:transparent; }}
        QLabel#infoLabel {{ color:#b45309; background:transparent; font-weight:800; }}

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
