from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
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

from src.ui.theme import STYLE

NAVY = "#0b3679"
GRID = "#cfe0f4"
GREEN = "#10a968"
RED = "#ef4444"


def extract_year_from_date_text(value: object) -> Optional[int]:
    """Return a 4-digit year from mixed delivery-date display strings.

    Supported examples include ``15.07.2026``, ``28-08-2026``,
    ``TBD-07-2026``, ``2026-07-TBD`` and ``2026-TBD-TBD``.
    Invalid or yearless values return ``None`` instead of raising.
    """
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
    """Parse report year input without raising.

    Accepted formats are ``YYYY`` and ``YYYY-YYYY``. Reversed ranges are
    normalized so ``2027-2026`` behaves as ``2026-2027`` instead of crashing.
    """
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


@dataclass(frozen=True)
class DeliveryRow:
    contract: str
    owner: str
    user: str
    domestic: str
    delivery: str
    date_text: str
    level: str
    part: str
    planned: int
    delivered: int
    config_type: str
    note: str
    status: str

    @property
    def remaining(self) -> int:
        return max(int(self.planned) - int(self.delivered), 0)


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
            return Qt.AlignCenter if index.column() in {6, 8, 9, 10} else Qt.AlignVCenter | Qt.AlignLeft
        if role == Qt.BackgroundRole and index.row() % 2:
            return QColor("#f4f9ff")
        if role == Qt.ForegroundRole:
            text = str(value).lower()
            if text == "riskli":
                return QColor(RED)
            if text == "tamamlandı":
                return QColor(GREEN)
        if role == Qt.FontRole and index.column() in {6, 8, 9, 10}:
            from PySide6.QtGui import QFont
            f = QFont(); f.setBold(True); return f
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        if role == Qt.BackgroundRole and orientation == Qt.Horizontal:
            return QColor(NAVY)
        if role == Qt.ForegroundRole and orientation == Qt.Horizontal:
            return QColor("white")
        return None


class GroupedBarPreview(QWidget):
    parts = ["Televizyon", "Bilgisayar", "Telefon", "Koltuk", "Buzdolabı", "Tablet"]
    countries = ["Ülke-1", "Ülke-2", "Ülke-3"]
    colors = ["#5b9bd5", "#ed7d31", "#a5a5a5", "#ffc000", "#4472c4", "#70ad47"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = {"Televizyon": [10, 10, 6], "Bilgisayar": [1, 1, 2], "Telefon": [1, 1, 1], "Koltuk": [1, 1, 2], "Buzdolabı": [1, 1, 1], "Tablet": [1, 1, 3]}
        self.setMinimumHeight(520)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(18, 18, -18, -18)
        p.fillRect(r, QColor("white")); p.setPen(QPen(QColor(GRID))); p.drawRect(r)
        p.setPen(QColor("#002060")); p.drawText(r.adjusted(0, 4, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "YURTİÇİ/YURTDIŞI ve YILLARA GÖRE SİPARİŞ DURUMU")
        chart = r.adjusted(70, 55, -210, -185)
        maxv = 10
        p.setPen(QPen(QColor("#d8d8d8")))
        for i in range(6):
            y = chart.bottom() - int(chart.height() * i / 5)
            p.drawLine(chart.left(), y, chart.right(), y)
            p.setPen(QColor("#334155")); p.drawText(chart.left() - 30, y + 4, str(i * 2)); p.setPen(QPen(QColor("#d8d8d8")))
        group_w = chart.width() / len(self.countries); bar_w = 18
        for ci, country in enumerate(self.countries):
            base_x = chart.left() + ci * group_w + group_w * .25
            for pi, part in enumerate(self.parts):
                v = self.values[part][ci]
                h = int(chart.height() * v / maxv)
                x = int(base_x + pi * (bar_w + 5)); y = chart.bottom() - h
                p.fillRect(x, y, bar_w, h, QColor(self.colors[pi]))
                p.setPen(QColor("#111827")); p.drawText(x - 2, y - 5, str(v))
            p.drawText(int(chart.left() + ci * group_w), chart.bottom() + 24, int(group_w), 20, Qt.AlignCenter, country)
        lx = r.right() - 175; ly = chart.top() + 80
        p.setPen(QColor("#111827")); p.drawText(lx, ly - 25, "PARÇA ADI ▾")
        for i, part in enumerate(self.parts):
            p.fillRect(lx, ly + i * 28, 10, 10, QColor(self.colors[i])); p.drawText(lx + 18, ly + 10 + i * 28, part)
        table = r.adjusted(105, r.height() - 150, -220, -25)
        cols = [""] + self.countries; row_h = 25; col_w = table.width() / len(cols)
        p.setPen(QPen(QColor("#d8d8d8")))
        for ri, part in enumerate([""] + self.parts):
            for ci, col in enumerate(cols):
                cell_x = int(table.left() + ci * col_w); cell_y = table.top() + ri * row_h
                p.drawRect(cell_x, cell_y, int(col_w), row_h)
                if ri == 0 and ci > 0: p.drawText(cell_x, cell_y, int(col_w), row_h, Qt.AlignCenter, col)
                elif ri > 0 and ci == 0:
                    p.fillRect(cell_x + 8, cell_y + 8, 10, 10, QColor(self.colors[ri - 1])); p.drawText(cell_x + 24, cell_y, int(col_w), row_h, Qt.AlignVCenter, part)
                elif ri > 0 and ci > 0: p.drawText(cell_x, cell_y, int(col_w), row_h, Qt.AlignCenter, str(self.values[part][ci - 1]))


class DeliveryScheduleReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tahmini Teslimat Takvimi")
        self.resize(1500, 860); self.setMinimumSize(1180, 720)
        self.setStyleSheet(STYLE + self._extra_style())
        self.rows = self._sample_rows()
        self.build_ui(); self.refresh_preview()

    def build_ui(self):
        root = QHBoxLayout(self); root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(self._build_filters())
        main = QFrame(); main.setObjectName("reportCard"); ml = QVBoxLayout(main); ml.setContentsMargins(18, 12, 18, 18)
        top = QHBoxLayout(); title = QLabel("Tahmini Teslimat Takvimi"); title.setObjectName("mainTitle"); top.addWidget(title); top.addStretch()
        self.refresh_btn = QPushButton("Önizlemeyi Yenile"); self.refresh_btn.setObjectName("secondary"); self.refresh_btn.clicked.connect(self.refresh_preview); top.addWidget(self.refresh_btn)
        self.export_btn = QPushButton("Excel Oluştur"); self.export_btn.clicked.connect(self.on_export_excel_clicked); top.addWidget(self.export_btn); ml.addLayout(top)
        self.tabs = QTabWidget(); self.tabs.addTab(self._dashboard_tab(), "Dashboard"); self.tabs.addTab(self._delivery_tab(), "Teslimat Verisi"); self.tabs.addTab(self._matrix_tab(), "Takvim Matrisi"); self.tabs.addTab(self._rev_tab(), "REV Takip")
        ml.addWidget(self.tabs, 1); root.addWidget(main, 1)

    def _build_filters(self):
        frame = QFrame(); frame.setObjectName("filterPanel"); frame.setFixedWidth(300); lay = QVBoxLayout(frame)
        h = QLabel("Rapor Ayarları"); h.setObjectName("panelTitle"); lay.addWidget(h); lay.addWidget(QLabel("Önizleme uygulama içinden üretilir."))
        self.platform = self._combo(["Örnek Platform Sistemi"]); self.year_range = QLineEdit("2026-2027"); self.domestic = self._combo(["Tümü", "Yİ", "YD"]); self.user = self._combo(["Tümü", "Ülke-1", "Ülke-2", "Ülke-3", "Ülke-4"]); self.contract = self._combo(["Tüm seçili sözleşmeler", "SÖZ-001", "SÖZ-002", "SÖZ-003", "SÖZ-004"]); self.status = self._combo(["Tümü", "Planlandı", "Tamamlandı", "Riskli"])
        for label, widget in [("PLATFORM", self.platform), ("YIL / ARALIK", self.year_range), ("Yİ / YD", self.domestic), ("TESLİM KULLANICISI", self.user), ("SÖZLEŞME", self.contract), ("DURUM", self.status)]:
            l = QLabel(label); l.setObjectName("fieldLabel"); lay.addWidget(l); lay.addWidget(widget)
            if label == "YIL / ARALIK": lay.addWidget(QLabel("Tek yıl: 2026 veya aralık: 2026-2027"))
        btn = QPushButton("Önizlemeyi Yenile"); btn.clicked.connect(self.refresh_preview); lay.addWidget(btn); lay.addStretch(); return frame

    def _combo(self, items):
        c = QComboBox(); c.addItems(items); return c

    def _dashboard_tab(self):
        w = QScrollArea(); w.setWidgetResizable(True); host = QWidget(); lay = QVBoxLayout(host)
        self.kpi_grid = QGridLayout(); lay.addLayout(self.kpi_grid)
        self.chart = GroupedBarPreview(); card = QFrame(); card.setObjectName("reportCard"); cl = QVBoxLayout(card); cl.addWidget(self.chart); lay.addWidget(card)
        w.setWidget(host); return w

    def _delivery_tab(self):
        self.delivery_view = self._table(); return self.delivery_view

    def _matrix_tab(self):
        self.matrix_view = self._table(); return self.matrix_view

    def _rev_tab(self):
        self.rev_view = self._table(); return self.rev_view

    def _table(self):
        v = QTableView(); v.setAlternatingRowColors(True); v.setSortingEnabled(False); v.setEditTriggers(QAbstractItemView.NoEditTriggers); v.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); v.horizontalHeader().setStretchLastSection(True); return v

    def collect_filters(self) -> dict[str, str]:
        text = self.year_range.text().strip()
        start_year, end_year = parse_year_range(text)
        ok = start_year is not None and end_year is not None
        self.year_range.setProperty("invalid", not ok)
        self.year_range.style().unpolish(self.year_range)
        self.year_range.style().polish(self.year_range)
        return {
            "platform": self.platform.currentText(),
            "year_range": text,
            "year_range_valid": str(ok),
            "yi_yd": self.domestic.currentText(),
            "user": self.user.currentText(),
            "contract": self.contract.currentText(),
            "status": self.status.currentText(),
        }

    def build_report_payload(self) -> dict[str, Any]:
        return {"filters": self.collect_filters(), "deliveries": [row.__dict__ | {"remaining": row.remaining} for row in self.rows], "source": "delivery_schedule_preview"}

    def refresh_preview(self):
        filters = self.collect_filters()
        if filters["year_range_valid"] != "True": return
        rows = self.rows
        start_year, end_year = parse_year_range(filters["year_range"])
        if start_year is None or end_year is None:
            return

        filtered_rows = []
        for row in rows:
            row_year = extract_year_from_date_text(getattr(row, "date_text", ""))
            if row_year is None:
                continue
            if start_year <= row_year <= end_year:
                filtered_rows.append(row)
        rows = filtered_rows
        if filters["yi_yd"] != "Tümü": rows = [r for r in rows if r.domestic == filters["yi_yd"]]
        if filters["user"] != "Tümü": rows = [r for r in rows if r.user == filters["user"]]
        if filters["status"] != "Tümü": rows = [r for r in rows if r.status == filters["status"]]
        if filters["contract"] != "Tüm seçili sözleşmeler": rows = [r for r in rows if r.contract == filters["contract"]]
        self._refresh_kpis(rows)
        headers = ["Sözleşme", "Sözleşme Sahibi", "Teslim Kullanıcısı", "Yİ/YD", "Teslimat", "Tarih", "Seviye", "Parça", "Plan", "Teslim", "Kalan", "Konfigürasyon Tipi", "Opsiyon / Not", "Durum"]
        self.delivery_view.setModel(SimpleTableModel(headers, [[r.contract, r.owner, r.user, r.domestic, r.delivery, r.date_text, r.level, r.part, r.planned, r.delivered, r.remaining, r.config_type, r.note, r.status] for r in rows], self))
        parts = ["Televizyon", "Bilgisayar", "Telefon", "Koltuk", "Buzdolabı", "Tablet", "Kamera", "Radar Modülü", "Kontrol Ünitesi"]
        matrix = [["1", p, p, *(sum(r.planned for r in rows if r.part == p and r.user == u) for u in ["Ülke-1", "Ülke-2", "Ülke-3"]), sum(r.planned for r in rows if r.part == p)] for p in parts]
        self.matrix_view.setModel(SimpleTableModel(["Seviye", "Parça Numarası / Parça Adı", "Teslimat Zamanı", "Ülke-1", "Ülke-2", "Ülke-3", "TOPLAM"], matrix, self))
        self.rev_view.setModel(SimpleTableModel(["Tarih", "Kullanıcı", "Sözleşme", "Teslimat", "Alan", "Eski Değer", "Yeni Değer", "Açıklama"], self.load_activity_log_preview(filters), self))

    def _refresh_kpis(self, rows):
        while self.kpi_grid.count(): self.kpi_grid.takeAt(0).widget().deleteLater()
        vals = [("Planlanan", sum(r.planned for r in rows)), ("Teslim Edilen", sum(r.delivered for r in rows)), ("Kalan", sum(r.remaining for r in rows)), ("Kullanıcı", len({r.user for r in rows})), ("Sözleşme", len({r.contract for r in rows})), ("Riskli Satır", sum(1 for r in rows if r.status == "Riskli"))]
        for i, (name, val) in enumerate(vals):
            card = QFrame(); card.setObjectName("kpiCard"); l = QVBoxLayout(card); a = QLabel(name.upper()); a.setObjectName("fieldLabel"); b = QLabel(str(val)); b.setObjectName("kpiValue"); l.addWidget(a); l.addWidget(b); self.kpi_grid.addWidget(card, 0, i)

    def load_activity_log_preview(self, filters: dict[str, str]) -> list[list[str]]:
        return [["2026-02-14 10:22", "Ali Yılmaz", "SÖZ-001", "Ülke-1 Temmuz Teslimatı", "Tahmini Teslimat Tarihi", "TBD", "2026-07-TBD", "Ay bazlı teslimat planı girildi."], ["2026-03-01 11:05", "Ali Yılmaz", "SÖZ-001", "Ülke-1 Temmuz Teslimatı", "Tarih", "2026-07-TBD", "15.07.2026", "Gün bilgisi netleşti."], ["2026-06-03 09:12", "Mehmet Demir", "SÖZ-003", "Ülke-3 Ekim Teslimatı", "Durum", "Planlandı", "Riskli", "Termin riski işaretlendi."]]

    def on_export_excel_clicked(self):
        self.build_report_payload()
        QMessageBox.information(self, "Excel Oluştur", "Excel üretim modülü sonraki aşamada bağlanacak.")

    def _sample_rows(self):
        return [DeliveryRow("SÖZ-001", "Ali Yılmaz", "Ülke-1", "YD", "Ülke-1 Temmuz Teslimatı", "15.07.2026", "1", "Televizyon", 10, 0, "C Tipi", "Standart Paket / Temmuz teslimat planı.", "Planlandı"), DeliveryRow("SÖZ-001", "Ali Yılmaz", "Ülke-1", "YD", "Ülke-1 Temmuz Teslimatı", "TBD-07-2026", "1", "Bilgisayar", 1, 0, "C Tipi", "Standart Paket / Temmuz teslimat planı.", "Planlandı"), DeliveryRow("SÖZ-002", "Zeynep Kaya", "Ülke-2", "Yİ", "Ülke-2 Ağustos Teslimatı", "28-08-2026", "1", "Televizyon", 10, 2, "A Tipi", "Opsiyon-1 / Ağustos revizyonu sonrası teslim miktarı güncellendi.", "Planlandı"), DeliveryRow("SÖZ-002", "Zeynep Kaya", "Ülke-2", "Yİ", "Ülke-2 Ağustos Teslimatı", "28.08.2026", "1", "Tablet", 1, 1, "A Tipi", "Tablet teslim tamamlandı.", "Tamamlandı"), DeliveryRow("SÖZ-003", "Mehmet Demir", "Ülke-3", "YD", "Ülke-3 Ekim Teslimatı", "2026-10-TBD", "1", "Kamera", 4, 0, "B Tipi", "Kritik parça tedarik riski.", "Riskli"), DeliveryRow("SÖZ-003", "Mehmet Demir", "Ülke-3", "YD", "Ülke-3 Ekim Teslimatı", "2026-10-TBD", "1", "Kontrol Ünitesi", 1, 1, "B Tipi", "Kontrol ünitesi teslim edildi.", "Tamamlandı"), DeliveryRow("SÖZ-004", "Ayşe Aydın", "Ülke-4", "Yİ", "Ülke-4 Ocak Teslimatı", "2026-TBD-TBD", "1", "Radar Modülü", 1, 0, "D Tipi", "2027 modernizasyon teslimatı.", "Planlandı")]

    def _extra_style(self):
        return f"""
        QFrame#filterPanel, QFrame#reportCard, QFrame#kpiCard {{ background:#ffffff; border:1px solid {GRID}; border-radius:14px; }}
        QLabel#panelTitle {{ color:#002060; font-size:18px; font-weight:900; background:transparent; }}
        QLabel#mainTitle {{ color:#002060; font-size:22px; font-weight:900; background:transparent; }}
        QLabel#fieldLabel {{ color:#415a86; font-size:11px; font-weight:900; background:transparent; }}
        QLabel#kpiValue {{ color:#075bd8; font-size:28px; font-weight:900; background:transparent; }}
        QTabWidget::pane {{ border:1px solid {GRID}; border-radius:10px; background:#ffffff; }}
        QTabBar::tab {{ padding:10px 18px; margin:3px; color:#415a86; font-weight:900; }}
        QTabBar::tab:selected {{ background:{NAVY}; color:white; border-radius:9px; }}
        QHeaderView::section {{ background:{NAVY}; color:white; font-weight:900; padding:8px; border:1px solid #31548b; }}
        QTableView {{ background:#ffffff; gridline-color:{GRID}; alternate-background-color:#f4f9ff; selection-background-color:#dbeafe; }}
        QLineEdit[invalid="true"] {{ border:2px solid {RED}; background:#fff1f2; }}
        """
