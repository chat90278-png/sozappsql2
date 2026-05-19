# -*- coding: utf-8 -*-
"""
src/ui/perf_dashboard.py  —  Profesyonel Performans Dashboard
=============================================================

Konumu  : sozappcoklusistem/src/ui/perf_dashboard.py
Çağrısı :
    from src.ui.perf_dashboard import PerfDashboardDialog
    dlg = PerfDashboardDialog(self.path, self)
    dlg.exec()

Bağımlılıklar (hepsi projede zaten mevcut):
    PySide6
    src.services.perf_tracker  (load_records, compute_stats, file_size_mb)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QRectF, QThread, QTimer, Signal, QObject
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QProgressBar,
)

# ────────────────────────────────────────────────────────────────
#  Renk paleti  (dark-navy tema)
# ────────────────────────────────────────────────────────────────
_BG     = "#0f1923"
_PANEL  = "#162030"
_CARD   = "#1c2d3f"
_BORDER = "#243548"
_ACCENT = "#3b82f6"
_CYAN   = "#06b6d4"
_GREEN  = "#22c55e"
_YELLOW = "#f59e0b"
_RED    = "#ef4444"
_PURPLE = "#a855f7"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"
_MID    = "#94a3b8"

# ────────────────────────────────────────────────────────────────
#  StyleSheet
# ────────────────────────────────────────────────────────────────
_STYLE = f"""
QDialog, QWidget {{
    background:{_BG};
    font-family:'Segoe UI', Arial;
    color:{_TEXT};
    font-size:13px;
}}
QScrollArea {{ background:transparent; border:none; }}
QScrollBar:vertical {{
    background:{_PANEL}; width:8px; border-radius:4px;
}}
QScrollBar::handle:vertical {{
    background:{_BORDER}; border-radius:4px; min-height:30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QTableWidget {{
    background:{_CARD}; border:1px solid {_BORDER}; border-radius:8px;
    gridline-color:{_BORDER}; color:{_TEXT}; font-size:12px;
    selection-background-color:rgba(59,130,246,0.28);
}}
QHeaderView::section {{
    background:{_PANEL}; color:{_MID}; font-weight:700; font-size:11px;
    border:none; border-bottom:1px solid {_BORDER};
    padding:6px 10px; text-transform:uppercase; letter-spacing:0.5px;
}}
QTableWidget::item {{
    padding:5px 10px; border-bottom:1px solid {_BORDER};
}}
QPushButton#closeBtn {{
    background:{_ACCENT}; color:white; border:none;
    border-radius:8px; padding:8px 22px; font-weight:700;
}}
QPushButton#closeBtn:hover {{ background:#2563eb; }}
QPushButton#refreshBtn {{
    background:{_CARD}; color:{_TEXT}; border:1px solid {_BORDER};
    border-radius:8px; padding:8px 18px; font-weight:600;
}}
QPushButton#refreshBtn:hover {{ background:#1a3050; border-color:{_ACCENT}; }}
"""


# ────────────────────────────────────────────────────────────────
#  Yardımcı fonksiyonlar
# ────────────────────────────────────────────────────────────────

def _ms(val: float) -> str:
    """Milisaniyeyi okunabilir stringe çevirir."""
    try:
        val = float(val or 0)
    except Exception:
        return "—"
    if val >= 60_000:
        return f"{val / 60000:.1f} dk"
    if val >= 1_000:
        return f"{val / 1000:.2f} s"
    return f"{val:.0f} ms"


def _color_ms(ms: float) -> str:
    if ms < 500:
        return _GREEN
    if ms < 3_000:
        return _YELLOW
    return _RED


def _fatigue(all_vals: List[float], recent: List[float]) -> Tuple[float, str, str]:
    """(skor 0-100, etiket, renk)"""
    if not all_vals:
        return 0.0, "Veri Yok", _MUTED
    all_avg = sum(all_vals) / len(all_vals)
    rec_avg = sum(recent) / len(recent) if recent else all_avg
    ratio   = rec_avg / all_avg if all_avg > 0 else 1.0
    score   = max(0.0, min(100.0, (ratio - 0.5) * 100))
    if ratio > 1.15:
        return score, "▲ Yavaşladı", _RED
    if ratio < 0.85:
        return score, "▼ Hızlandı",  _GREEN
    return score, "● Kararlı", _YELLOW


# ────────────────────────────────────────────────────────────────
#  KPI Kartı
# ────────────────────────────────────────────────────────────────

class _KPICard(QFrame):
    def __init__(self, title: str, icon: str = "", color: str = _ACCENT, parent=None):
        super().__init__(parent)
        self.setFixedHeight(108)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._accent = color
        self.setStyleSheet(f"""
            QFrame {{
                background:{_CARD};
                border:1px solid {_BORDER};
                border-radius:12px;
                border-left:3px solid {color};
            }}
        """)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(18)
        sh.setOffset(0, 3)
        sh.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(sh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        if icon:
            ic = QLabel(icon)
            ic.setStyleSheet(f"font-size:16px; color:{color}; background:transparent;")
            top.addWidget(ic)
        lbl_t = QLabel(title.upper())
        lbl_t.setStyleSheet(
            f"color:{_MUTED}; font-size:10px; font-weight:700;"
            f"letter-spacing:1px; background:transparent;"
        )
        top.addWidget(lbl_t)
        top.addStretch()
        lay.addLayout(top)

        self._val = QLabel("—")
        self._val.setStyleSheet(
            f"color:{_TEXT}; font-size:21px; font-weight:800; background:transparent;"
        )
        lay.addWidget(self._val)

        self._sub = QLabel("")
        self._sub.setStyleSheet(f"color:{_MID}; font-size:11px; background:transparent;")
        lay.addWidget(self._sub)

    def set(self, value: str, sub: str = "", color: str = ""):
        self._val.setText(value)
        self._sub.setText(sub)
        self._val.setStyleSheet(
            f"color:{color or _TEXT}; font-size:21px; font-weight:800; background:transparent;"
        )


# ────────────────────────────────────────────────────────────────
#  Trend Grafiği  (saf QPainter — dış bağımlılık yok)
# ────────────────────────────────────────────────────────────────

class _TrendChart(QWidget):
    _WARN = 3_000.0
    _CRIT = 8_000.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self._points: List[Tuple[str, float]] = []
        self.setStyleSheet(f"background:{_CARD}; border-radius:12px;")

    def set_data(self, points: List[Tuple[str, float]]):
        self._points = points[-40:]
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()

        # Arka plan
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0, QColor(_CARD))
        grad.setColorAt(1, QColor(_PANEL))
        p.fillRect(0, 0, W, H, QBrush(grad))

        if not self._points:
            p.setPen(QColor(_MUTED))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(0, 0, W, H, Qt.AlignCenter, "Henüz veri yok")
            p.end()
            return

        PL, PR, PT, PB = 54, 18, 18, 34
        vals  = [v for _, v in self._points]
        maxv  = max(vals) * 1.18 or 1_000.0

        def tx(i: int) -> float:
            n = len(self._points)
            return PL + i / max(n - 1, 1) * (W - PL - PR)

        def ty(v: float) -> float:
            return PT + (1 - v / maxv) * (H - PT - PB)

        # Eşik çizgileri
        for thr, col in [(self._WARN, _YELLOW), (self._CRIT, _RED)]:
            if thr <= maxv:
                y = ty(thr)
                p.setPen(QPen(QColor(col), 1, Qt.DashLine))
                p.drawLine(int(PL), int(y), int(W - PR), int(y))
                p.setFont(QFont("Segoe UI", 8))
                p.setPen(QColor(col))
                p.drawText(int(PL) + 2, int(y) - 3, _ms(thr))

        # Y ekseni ızgara + etiket
        p.setFont(QFont("Segoe UI", 8))
        for i in range(5):
            v = maxv * i / 4
            y = ty(v)
            p.setPen(QPen(QColor(_BORDER), 1, Qt.DotLine))
            p.drawLine(int(PL), int(y), int(W - PR), int(y))
            p.setPen(QColor(_MUTED))
            p.drawText(2, int(y) - 6, 48, 14, Qt.AlignRight, _ms(v))

        # Alan dolgusu
        fill = QPainterPath()
        fill.moveTo(tx(0), H - PB)
        for i, (_, v) in enumerate(self._points):
            fill.lineTo(tx(i), ty(v))
        fill.lineTo(tx(len(self._points) - 1), H - PB)
        fill.closeSubpath()
        gf = QLinearGradient(0, PT, 0, H - PB)
        gf.setColorAt(0.0, QColor(59, 130, 246, 70))
        gf.setColorAt(1.0, QColor(59, 130, 246, 0))
        p.fillPath(fill, QBrush(gf))

        # Çizgi
        line = QPainterPath()
        for i, (_, v) in enumerate(self._points):
            x, y = tx(i), ty(v)
            if i == 0:
                line.moveTo(x, y)
            else:
                line.lineTo(x, y)
        p.setPen(QPen(QColor(_ACCENT), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(line)

        # Noktalar
        for i, (_, v) in enumerate(self._points):
            x, y = tx(i), ty(v)
            p.setBrush(QBrush(QColor(_color_ms(v))))
            p.setPen(QPen(QColor(_PANEL), 1.5))
            p.drawEllipse(QRectF(x - 3.5, y - 3.5, 7, 7))

        # X ekseni (ilk / orta / son)
        n = len(self._points)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(_MUTED))
        for idx in {0, n // 2, n - 1}:
            ts = self._points[idx][0]
            x  = tx(idx)
            p.drawText(int(x) - 28, H - PB + 4, 56, 20, Qt.AlignCenter, ts)

        p.end()


# ────────────────────────────────────────────────────────────────
#  Yorgunluk Gauge
# ────────────────────────────────────────────────────────────────

class _FatigueGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self._score = 0.0
        self._label = "—"
        self.setStyleSheet("background:transparent;")

    def set_score(self, score: float, label: str):
        self._score = max(0.0, min(100.0, score))
        self._label = label
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2 + 10
        r = min(W, H) / 2 - 14

        # Arka yay
        p.setPen(QPen(QColor(_BORDER), 13, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 210 * 16, -240 * 16)

        # Değer yayı
        clr   = _GREEN if self._score < 30 else (_YELLOW if self._score < 65 else _RED)
        span  = -int(self._score / 100 * 240 * 16)
        p.setPen(QPen(QColor(clr), 13, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 210 * 16, span)

        # Skor metni
        p.setPen(QColor(_TEXT))
        p.setFont(QFont("Segoe UI", 18, QFont.Bold))
        p.drawText(QRectF(cx - 36, cy - 20, 72, 34), Qt.AlignCenter, str(int(self._score)))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(_MUTED))
        p.drawText(QRectF(cx - 36, cy + 14, 72, 16), Qt.AlignCenter, "/ 100")

        # Alt etiket
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(QColor(clr))
        p.drawText(QRectF(cx - 54, cy + r - 2, 108, 18), Qt.AlignCenter, self._label)
        p.end()


# ────────────────────────────────────────────────────────────────
#  Operasyon Satırı
# ────────────────────────────────────────────────────────────────

class _OpRow(QFrame):
    def __init__(self, display: str, stats: dict, max_ms: float, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet(
            f"QFrame{{background:{_CARD};border:1px solid {_BORDER};border-radius:10px;}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(14)

        nm = QLabel(display)
        nm.setFixedWidth(155)
        nm.setStyleSheet(
            f"color:{_TEXT}; font-weight:700; font-size:12px; background:transparent;"
        )
        lay.addWidget(nm)

        # Yatay dolgu barı
        bar_bg = QFrame()
        bar_bg.setFixedSize(188, 8)
        bar_bg.setStyleSheet(f"background:{_BORDER}; border-radius:4px;")
        avg   = stats.get("avg_ms", 0)
        ratio = min(1.0, avg / max(max_ms, 1))
        bar_fg = QFrame(bar_bg)
        bar_fg.setStyleSheet(f"background:{_color_ms(avg)}; border-radius:4px;")
        bar_fg.setGeometry(0, 0, max(4, int(188 * ratio)), 8)
        lay.addWidget(bar_bg)

        # Stat kolonları
        for lbl_txt, key, fmt in [
            ("ORT",  "avg_ms",   _ms),
            ("MIN",  "min_ms",   _ms),
            ("MAX",  "max_ms",   _ms),
            ("ADET", "count",    lambda v: str(int(v))),
            ("HATA", "failures", lambda v: str(int(v))),
        ]:
            val = stats.get(key, 0)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.setContentsMargins(0, 0, 0, 0)
            t = QLabel(lbl_txt)
            t.setStyleSheet(
                f"color:{_MUTED}; font-size:9px; font-weight:700; background:transparent;"
            )
            clr = _RED if (lbl_txt == "HATA" and val > 0) else _TEXT
            v = QLabel(fmt(val))
            v.setStyleSheet(
                f"color:{clr}; font-size:12px; font-weight:800; background:transparent;"
            )
            col.addWidget(t)
            col.addWidget(v)
            w = QWidget()
            w.setLayout(col)
            w.setFixedWidth(60)
            lay.addWidget(w)

        lay.addStretch()


# ────────────────────────────────────────────────────────────────
#  Operasyon adları ve sıralama
# ────────────────────────────────────────────────────────────────

_OP_NAMES: Dict[str, str] = {
    "excel_load":      "Excel Yükleme",
    "cache_build":     "Cache Oluşturma",
    "contract_save":   "Sözleşme Kayıt",
    "contract_delete": "Sözleşme Silme",
    "component_save":  "Bileşen Kayıt",
    "user_save":       "Kullanıcı Kayıt",
}
_OP_ORDER = list(_OP_NAMES.keys())


# ────────────────────────────────────────────────────────────────
#  Arka plan worker  (UI thread'i bloke etmez)
# ────────────────────────────────────────────────────────────────

class _PerfWorker(QObject):
    """perf.jsonl okuma işini arka thread'de yapar."""
    done   = Signal(list, dict, float)   # records, stats, size_mb
    failed = Signal(str)

    def __init__(self, excel_path: Path):
        super().__init__()
        self.excel_path = excel_path

    def run(self):
        try:
            from src.services.perf_tracker import (
                load_records, compute_stats, file_size_mb,
            )
            records = load_records(self.excel_path, last_n=500)
            stats   = compute_stats(records)
            size_mb = file_size_mb(self.excel_path)
            self.done.emit(records, stats, size_mb)
        except Exception as exc:
            self.failed.emit(str(exc))


# ────────────────────────────────────────────────────────────────
#  Ana Dialog
# ────────────────────────────────────────────────────────────────

class PerfDashboardDialog(QDialog):
    """
    Profesyonel Performans Dashboard.

    Kullanım (app.py içinde):
        dlg = PerfDashboardDialog(self.path, self)
        dlg.exec()
    """

    def __init__(self, excel_path, parent=None):
        super().__init__(parent)
        self.excel_path = Path(excel_path)
        self.setWindowTitle("Sistem Performans Raporu")
        self.setModal(True)
        self.resize(1200, 820)
        self.setMinimumSize(900, 640)
        self.setStyleSheet(_STYLE)
        self._thread: QThread | None = None
        self._worker: _PerfWorker | None = None
        self._build_ui()
        QTimer.singleShot(60, self._load)

    # ────────────── UI İnşası ──────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        # Gövde
        body_w = QWidget()
        body_w.setStyleSheet(f"background:{_BG};")
        body_lay = QVBoxLayout(body_w)
        body_lay.setContentsMargins(22, 18, 22, 22)
        body_lay.setSpacing(14)

        # ── KPI satırı
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        self._kpi_size  = _KPICard("Excel Boyutu",    "💾", _ACCENT)
        self._kpi_rows  = _KPICard("Toplam Satır",    "📋", _CYAN)
        self._kpi_plat  = _KPICard("Platform Sayısı", "🗂",  _PURPLE)
        self._kpi_speed = _KPICard("Okuma Hızı",      "⚡", _GREEN)
        self._kpi_avg   = _KPICard("Ort. Yükleme",    "⏱", _YELLOW)
        self._kpi_ops   = _KPICard("Toplam İşlem",    "📊", _ACCENT)
        for k in [self._kpi_size, self._kpi_rows, self._kpi_plat,
                  self._kpi_speed, self._kpi_avg, self._kpi_ops]:
            kpi_row.addWidget(k)
        body_lay.addLayout(kpi_row)

        # ── Orta satır: Trend + Sağ Kolon
        mid = QHBoxLayout()
        mid.setSpacing(14)

        # Trend
        tf = QFrame()
        tf.setStyleSheet(
            f"background:{_CARD}; border:1px solid {_BORDER}; border-radius:12px;"
        )
        tfl = QVBoxLayout(tf)
        tfl.setContentsMargins(14, 10, 14, 10)
        tfl.setSpacing(6)
        tfl.addWidget(self._section("📈  Yükleme Süresi Trendi"))
        sub = QLabel("Son 40 yükleme  ·  Sarı = 3 sn  ·  Kırmızı = 8 sn eşiği")
        sub.setStyleSheet(f"color:{_MUTED}; font-size:10px; background:transparent;")
        tfl.addWidget(sub)
        self._trend = _TrendChart()
        tfl.addWidget(self._trend)
        mid.addWidget(tf, 3)

        # Sağ kolon
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        # Yorgunluk
        ff = QFrame()
        ff.setStyleSheet(
            f"background:{_CARD}; border:1px solid {_BORDER}; border-radius:12px;"
        )
        ffl = QVBoxLayout(ff)
        ffl.setContentsMargins(14, 10, 14, 10)
        ffl.setSpacing(6)
        ffl.addWidget(self._section("🔋  Sistem Yorgunluğu"))
        sub2 = QLabel("Son 5 yükleme / Genel ortalama")
        sub2.setStyleSheet(f"color:{_MUTED}; font-size:10px; background:transparent;")
        ffl.addWidget(sub2)
        gr = QHBoxLayout()
        gr.setContentsMargins(0, 0, 0, 0)
        self._gauge = _FatigueGauge()
        gr.addWidget(self._gauge, 0, Qt.AlignCenter)
        dc = QVBoxLayout()
        dc.setSpacing(5)
        self._fat_all  = self._detail_row("Genel ort.")
        self._fat_rec  = self._detail_row("Son 5 ort.")
        self._fat_diff = self._detail_row("Değişim")
        self._fat_stat = self._detail_row("Durum")
        for w in [self._fat_all, self._fat_rec, self._fat_diff, self._fat_stat]:
            dc.addWidget(w)
        gr.addLayout(dc)
        ffl.addLayout(gr)
        right_col.addWidget(ff)

        # Dosya bilgileri
        file_frame = QFrame()
        file_frame.setStyleSheet(
            f"background:{_CARD}; border:1px solid {_BORDER}; border-radius:12px;"
        )
        self._file_lay = QVBoxLayout(file_frame)
        self._file_lay.setContentsMargins(14, 10, 14, 10)
        self._file_lay.setSpacing(4)
        self._file_lay.addWidget(self._section("📁  Dosya Bilgileri"))
        right_col.addWidget(file_frame)

        mid.addLayout(right_col, 2)
        body_lay.addLayout(mid)

        # ── Operasyon barları
        body_lay.addWidget(self._section("⚙️  Operasyon Performansı"))
        self._ops_lay = QVBoxLayout()
        self._ops_lay.setSpacing(7)
        body_lay.addLayout(self._ops_lay)

        # ── Log tablosu
        body_lay.addWidget(self._section("🗒  Son 100 İşlem Kaydı"))
        self._log_tbl = self._build_log_table()
        body_lay.addWidget(self._log_tbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body_w)
        root.addWidget(scroll, 1)

        root.addWidget(self._make_footer())

    # ── Header / Footer ────────────────────────────────────────

    def _make_header(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background:{_PANEL}; border-bottom:1px solid {_BORDER};")
        f.setFixedHeight(62)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(22, 0, 22, 0)
        ic = QLabel("📊")
        ic.setStyleSheet("font-size:20px; background:transparent;")
        lay.addWidget(ic)
        title = QLabel("Sistem Performans Raporu")
        title.setStyleSheet(
            f"color:{_TEXT}; font-size:15px; font-weight:800; background:transparent;"
        )
        lay.addWidget(title)
        lay.addStretch()
        self._hdr_meta = QLabel("")
        self._hdr_meta.setStyleSheet(
            f"color:{_MUTED}; font-size:11px; background:transparent;"
        )
        lay.addWidget(self._hdr_meta)
        return f

    def _make_footer(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background:{_PANEL}; border-top:1px solid {_BORDER};")
        f.setFixedHeight(54)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(22, 0, 22, 0)
        self._status_lbl = QLabel("Yükleniyor…")
        self._status_lbl.setStyleSheet(
            f"color:{_MUTED}; font-size:11px; background:transparent;"
        )
        lay.addWidget(self._status_lbl)

        # Yükleme göstergesi (sadece veri okunurken görünür)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # belirsiz dönen animasyon
        self._progress.setFixedWidth(120)
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{_BORDER};border-radius:4px;border:none;}}"
            f"QProgressBar::chunk{{background:{_ACCENT};border-radius:4px;}}"
        )
        self._progress.hide()
        lay.addWidget(self._progress)

        lay.addStretch()
        btn_ref = QPushButton("↻  Yenile")
        btn_ref.setObjectName("refreshBtn")
        btn_ref.clicked.connect(self._load)
        lay.addWidget(btn_ref)
        btn_cls = QPushButton("Kapat")
        btn_cls.setObjectName("closeBtn")
        btn_cls.clicked.connect(self.accept)
        lay.addWidget(btn_cls)
        return f

    # ── Widget yardımcıları ────────────────────────────────────

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{_TEXT}; font-size:13px; font-weight:800; background:transparent;"
        )
        return lbl

    def _detail_row(self, label: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("background:transparent; border:none;")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(76)
        lbl.setStyleSheet(f"color:{_MUTED}; font-size:11px; background:transparent;")
        val = QLabel("—")
        val.setObjectName("_v")
        val.setStyleSheet(
            f"color:{_TEXT}; font-size:11px; font-weight:700; background:transparent;"
        )
        lay.addWidget(lbl)
        lay.addWidget(val)
        lay.addStretch()
        return frame

    def _set_detail(self, frame: QFrame, text: str, color: str = _TEXT):
        v = frame.findChild(QLabel, "_v")
        if v:
            v.setText(text)
            v.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:700; background:transparent;"
            )

    def _build_log_table(self) -> QTableWidget:
        cols = [
            "Zaman", "Operasyon", "Süre", "Durum",
            "Platform", "Sözleşme", "Boyut (MB)", "RO Açılış", "Full Açılış",
        ]
        tbl = QTableWidget()
        tbl.setColumnCount(len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            tbl.styleSheet() +
            f" QTableWidget {{ alternate-background-color:{_PANEL}; }}"
        )
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setMinimumHeight(200)
        return tbl

    # ── Veri yükleme (arka thread) ─────────────────────────────

    def _load(self):
        """perf.jsonl'i arka thread'de okur — UI donmaz."""
        # Önceki thread çalışıyorsa başlatma
        if self._thread and self._thread.isRunning():
            return

        self._status_lbl.setText("Veri okunuyor…")
        self._progress.show()

        self._thread = QThread(self)
        self._worker = _PerfWorker(self.excel_path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_load_done)
        self._worker.failed.connect(self._on_load_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread_refs)

        self._thread.start()

    def _clear_thread_refs(self):
        self._worker = None
        self._thread = None

    def _on_load_done(self, records: list, stats: dict, size_mb: float):
        self._progress.hide()
        self._populate(records, stats, size_mb)

    def _on_load_failed(self, err: str):
        self._progress.hide()
        self._status_lbl.setText(f"Okuma hatası: {err}")
        # Hata durumunda boş veriyle ekranı doldur
        self._populate([], {}, 0.0)

    def _populate(self, records: list, stats: dict, size_mb: float):
        load_recs = [r for r in records if r.get("op") == "excel_load"]

        # ── KPI: Dosya boyutu
        self._kpi_size.set(
            f"{size_mb:.2f}" if size_mb else "—", "MB"
        )

        # ── KPI: Toplam satır (son yüklemeden)
        last_contracts = load_recs[-1].get("contracts", 0) if load_recs else 0
        self._kpi_rows.set(str(last_contracts) if last_contracts else "—", "sözleşme")

        # ── KPI: Platform (son yüklemeden)
        last_platforms = load_recs[-1].get("platforms", 0) if load_recs else 0
        self._kpi_plat.set(str(last_platforms) if last_platforms else "—", "platform")

        # ── KPI: Okuma hızı  satır/sn
        if load_recs and last_contracts:
            last_ms = load_recs[-1].get("duration_ms", 0)
            if last_ms > 0:
                spd = round(last_contracts / (last_ms / 1000), 1)
                self._kpi_speed.set(f"{spd:.1f}", "satır/sn", _GREEN)
            else:
                self._kpi_speed.set("—")
        else:
            self._kpi_speed.set("—")

        # ── KPI: Ortalama yükleme
        el = stats.get("excel_load", {})
        if el:
            avg = el["avg_ms"]
            self._kpi_avg.set(_ms(avg), "", _color_ms(avg))
        else:
            self._kpi_avg.set("—")

        # ── KPI: Toplam işlem sayısı
        total_ops = sum(s.get("count", 0) for s in stats.values())
        self._kpi_ops.set(str(total_ops), "işlem")

        # ── Header meta bilgisi
        self._hdr_meta.setText(
            f"{self.excel_path.name}  ·  {size_mb} MB  ·  "
            f"{len(records)} kayıt  ·  {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        # ── Trend grafiği
        trend_pts: List[Tuple[str, float]] = []
        for r in load_recs:
            ts = str(r.get("ts", ""))
            label = ts[5:16].replace("T", " ") if "T" in ts else ts[:10]
            trend_pts.append((label, r.get("duration_ms", 0)))
        self._trend.set_data(trend_pts)

        # ── Yorgunluk gauge
        all_ms = [r.get("duration_ms", 0) for r in load_recs]
        rec5   = all_ms[-5:] if len(all_ms) >= 5 else all_ms
        score, label, clr = _fatigue(all_ms, rec5)
        self._gauge.set_score(score, label)

        all_avg = sum(all_ms) / len(all_ms) if all_ms else 0.0
        rec_avg = sum(rec5) / len(rec5) if rec5 else 0.0
        delta   = (rec_avg - all_avg) / all_avg * 100 if all_avg > 0 else 0.0
        sign    = "+" if delta >= 0 else ""
        self._set_detail(self._fat_all,  _ms(all_avg))
        self._set_detail(self._fat_rec,  _ms(rec_avg), _color_ms(rec_avg))
        self._set_detail(
            self._fat_diff,
            f"{sign}{delta:.1f}%",
            _RED if delta > 15 else (_GREEN if delta < -15 else _YELLOW),
        )
        self._set_detail(self._fat_stat, label, clr)

        # ── Dosya bilgileri
        self._refresh_file_details(size_mb, load_recs, last_contracts, last_platforms)

        # ── Operasyon barları
        self._refresh_op_bars(stats)

        # ── Log tablosu
        self._refresh_log(records)

        # ── Footer
        self._status_lbl.setText(
            f"Son güncelleme: {datetime.now().strftime('%H:%M:%S')}  ·  {len(records)} kayıt"
        )

    # ── Alt bölüm yenileyicileri ───────────────────────────────

    def _refresh_file_details(
        self, size_mb: float, load_recs: list, contracts: int, platforms: int
    ):
        # Başlık QLabel'i (index 0) dışındaki widget'ları temizle
        while self._file_lay.count() > 1:
            item = self._file_lay.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        try:
            mtime = os.path.getmtime(self.excel_path)
            mod = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
        except Exception:
            mod = "—"

        rows = [
            ("Dosya adı",      self.excel_path.name,                   _TEXT),
            ("Boyut",          f"{size_mb:.3f} MB",                     _TEXT),
            ("Son değişiklik", mod,                                     _MID),
            ("Sözleşme",       str(contracts) if contracts else "—",    _CYAN),
            ("Platform",       str(platforms) if platforms else "—",    _PURPLE),
        ]
        if load_recs:
            lr = load_recs[-1]
            rows += [
                ("RO Açılış",   _ms(lr.get("ro_open_ms",   0)), _MID),
                ("Full Açılış", _ms(lr.get("full_open_ms", 0)), _MID),
            ]

        for lbl_txt, val_txt, color in rows:
            row_f = QFrame()
            row_f.setStyleSheet("background:transparent; border:none;")
            rl = QHBoxLayout(row_f)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)
            l1 = QLabel(lbl_txt)
            l1.setStyleSheet(f"color:{_MUTED}; font-size:11px; background:transparent;")
            l1.setFixedWidth(96)
            l2 = QLabel(val_txt)
            l2.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:700; background:transparent;"
            )
            l2.setWordWrap(True)
            rl.addWidget(l1)
            rl.addWidget(l2, 1)
            self._file_lay.addWidget(row_f)

    def _refresh_op_bars(self, stats: dict):
        while self._ops_lay.count():
            item = self._ops_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not stats:
            lbl = QLabel("Henüz performans kaydı bulunamadı.")
            lbl.setStyleSheet(f"color:{_MUTED}; font-size:12px;")
            self._ops_lay.addWidget(lbl)
            return

        max_ms = max((s.get("avg_ms", 0) for s in stats.values()), default=1.0)
        sorted_ops = sorted(
            stats.keys(),
            key=lambda o: (_OP_ORDER.index(o) if o in _OP_ORDER else 99, o),
        )
        for op in sorted_ops:
            name = _OP_NAMES.get(op, op)
            self._ops_lay.addWidget(_OpRow(name, stats[op], max_ms))

    def _refresh_log(self, records: list):
        rows = list(reversed(records))[:100]
        tbl  = self._log_tbl
        tbl.setRowCount(len(rows))

        for row, r in enumerate(rows):
            op     = r.get("op", "")
            dur_ms = r.get("duration_ms", 0)
            ok     = r.get("success", True)

            cells = [
                (str(r.get("ts", ""))[:19].replace("T", " "), _MID),
                (_OP_NAMES.get(op, op),                        _TEXT),
                (_ms(dur_ms),                                   _color_ms(dur_ms)),
                ("✓ OK" if ok else "✗ HATA",                   _GREEN if ok else _RED),
                (str(r.get("platforms", "—")),                  _MID),
                (str(r.get("contracts", "—")),                  _MID),
                (str(r.get("file_mb",   "—")),                  _MID),
                (_ms(r["ro_open_ms"])   if "ro_open_ms"   in r else "—", _MUTED),
                (_ms(r["full_open_ms"]) if "full_open_ms" in r else "—", _MUTED),
            ]

            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setForeground(QColor(color))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                tbl.setItem(row, col, item)

        tbl.resizeColumnsToContents()
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        tbl.setColumnWidth(0, 142)
        tbl.setColumnWidth(1, 148)
