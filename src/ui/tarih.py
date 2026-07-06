# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
import logging
import re
import sqlite3
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QObject, QPropertyAnimation, QEasingCurve, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout,
    QHBoxLayout, QLabel, QComboBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from src.config.app_config import APP_TITLE, TR_MONTHS
from src.services.excel_store import ExcelStore
from src.ui.theme import STYLE

_log = logging.getLogger("STS.calendar")


# ---------------------------------------------------------------------------
# CalendarDataWorker — ağır veri hazırlığını arka thread'e taşır
# KURAL: Bu worker hiçbir zaman SQLite connection veya STSStore nesnesi
#        ana thread'e aktarmaz. Yalnızca list[dict] döndürür.
# ---------------------------------------------------------------------------
class CalendarDataWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(list, list, list)  # (contract_events, system_events, volume_rows) - saf veri
    failed   = Signal(str)

    def __init__(self, db_path, year_from: int, year_to: int,
                 platform_filter: str = ""):
        super().__init__()
        self._db_path         = db_path
        self._year_from       = int(year_from)
        self._year_to         = int(year_to)
        self._platform_filter = str(platform_filter or "")

    def run(self) -> None:
        conn = None
        try:
            self.progress.emit(5, "Veritabanı bağlanıyor...")
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA cache_size=-32000")

            yf = str(self._year_from)
            yt = str(self._year_to)
            pf = self._platform_filter
            pc = "AND p.name = ?" if pf else ""

            self.progress.emit(15, "Sozlesme tarihleri okunuyor...")
            c_params = [yf, yt, yf, yt]
            if pf:
                c_params.append(pf)
            c_rows = conn.execute(
                "SELECT c.id AS row_id, p.name AS platform,"
                " c.contract_no AS no, c.contract_type AS type,"
                " c.status, c.completion_date, c.acceptance_date,"
                " c.note AS content"
                " FROM contracts c"
                " JOIN contract_platforms cp ON cp.contract_id = c.id"
                " JOIN platforms p           ON p.id = cp.platform_id"
                " WHERE ("
                "   (c.completion_date IS NOT NULL AND c.completion_date != ''  AND ("
                "       SUBSTR(c.completion_date,1,4) BETWEEN ? AND ?"
                "       OR c.completion_date = 'TBD'"
                "       OR c.completion_date LIKE '%-TBD-TBD'"
                "       OR c.completion_date LIKE '%-TBD'))"
                "   OR"
                "   (c.acceptance_date IS NOT NULL AND c.acceptance_date != '' AND ("
                "       SUBSTR(c.acceptance_date,1,4) BETWEEN ? AND ?"
                "       OR c.acceptance_date = 'TBD'"
                "       OR c.acceptance_date LIKE '%-TBD-TBD'"
                "       OR c.acceptance_date LIKE '%-TBD'))"
                " ) " + pc +
                " ORDER BY p.name, c.contract_no",
                c_params
            ).fetchall()

            contract_events = [
                {
                    "row": int(r["row_id"]),
                    "platform": str(r["platform"] or ""),
                    "no": str(r["no"] or ""),
                    "type": str(r["type"] or ""),
                    "status": str(r["status"] or ""),
                    "completion_date": str(r["completion_date"] or ""),
                    "acceptance_date": str(r["acceptance_date"] or ""),
                    "planned_acceptance_date": "",
                    "content": str(r["content"] or ""),
                    "user": "",
                }
                for r in c_rows
            ]

            self.progress.emit(40, "Sistem termini okunuyor...")
            s_params = [yf, yt]
            if pf:
                s_params.append(pf)
            s_rows = conn.execute(
                "SELECT c.id AS contract_row, p.name AS platform,"
                " c.contract_no AS no, s.name AS system_name,"
                " s.status, s.completion_date, s.acceptance_date"
                " FROM systems s"
                " JOIN contracts c           ON c.id = s.contract_id"
                " JOIN contract_platforms cp ON cp.contract_id = c.id"
                " JOIN platforms p           ON p.id = cp.platform_id"
                " WHERE s.completion_date IS NOT NULL AND s.completion_date != '' AND ("
                "   SUBSTR(s.completion_date,1,4) BETWEEN ? AND ?"
                "   OR s.completion_date = 'TBD'"
                "   OR s.completion_date LIKE '%-TBD-TBD'"
                "   OR s.completion_date LIKE '%-TBD'"
                " ) " + pc +
                " ORDER BY p.name, c.contract_no, s.name",
                s_params
            ).fetchall()

            self.progress.emit(65, "Teslimat tarihleri okunuyor...")
            d_params = [yf, yt, yf, yt]
            if pf:
                d_params.append(pf)
            d_rows = conn.execute(
                "SELECT c.id AS contract_row, d.id AS delivery_id, p.name AS platform,"
                " c.contract_no AS no,"
                " s.name AS system_name, d.name AS delivery_name,"
                " d.status, d.acceptance_date, d.planned_acceptance_date"
                " FROM deliveries d"
                " JOIN systems  s  ON s.id  = d.system_id"
                " JOIN contracts c ON c.id  = d.contract_id"
                " JOIN contract_platforms cp ON cp.contract_id = c.id"
                " JOIN platforms p ON p.id  = cp.platform_id"
                " WHERE ("
                "   (d.acceptance_date IS NOT NULL AND d.acceptance_date != '' AND ("
                "       SUBSTR(d.acceptance_date,1,4) BETWEEN ? AND ?"
                "       OR d.acceptance_date = 'TBD'"
                "       OR d.acceptance_date LIKE '%-TBD-TBD'"
                "       OR d.acceptance_date LIKE '%-TBD'))"
                "   OR"
                "   (d.planned_acceptance_date IS NOT NULL AND d.planned_acceptance_date != '' AND ("
                "       SUBSTR(d.planned_acceptance_date,1,4) BETWEEN ? AND ?"
                "       OR d.planned_acceptance_date = 'TBD'"
                "       OR d.planned_acceptance_date LIKE '%-TBD-TBD'"
                "       OR d.planned_acceptance_date LIKE '%-TBD'))"
                " ) " + pc +
                " ORDER BY p.name, c.contract_no, s.name, d.sort_order, d.id",
                d_params
            ).fetchall()

            system_events: list = []
            for r in s_rows:
                sname = str(r["system_name"] or "")
                no    = str(r["no"] or "")
                system_events.append({
                    "row": int(r["contract_row"]),
                    "platform": str(r["platform"] or ""),
                    "no": no, "type": "Sistem",
                    "system_label": sname,
                    "title": f"{no} · {sname}" if sname else no,
                    "status": str(r["status"] or ""),
                    "completion_date": str(r["completion_date"] or ""),
                    "acceptance_date": str(r["acceptance_date"] or ""),
                    "planned_acceptance_date": "",
                    "user": "",
                })
            for r in d_rows:
                sname = str(r["system_name"] or "")
                dname = str(r["delivery_name"] or "")
                no    = str(r["no"] or "")
                label = f"{no} · {sname} / {dname}" if sname else f"{no} / {dname}"
                system_events.append({
                    "row": int(r["contract_row"]),
                    "delivery_id": int(r["delivery_id"]),
                    "platform": str(r["platform"] or ""),
                    "no": no, "type": "Teslimat",
                    "system_label": sname,
                    "title": label,
                    "status": str(r["status"] or ""),
                    "completion_date": "",
                    "acceptance_date": str(r["acceptance_date"] or ""),
                    "planned_acceptance_date": str(r["planned_acceptance_date"] or ""),
                    "user": "",
                })

            self.progress.emit(90, "Veri hazirlanıyor...")

            # ── Teslimat Hacmi: bileşen bazlı planlanan adet ─────────────
            self.progress.emit(80, "Teslimat hacmi hesaplanıyor...")
            vol_params = [yf, yt, yf, yt]
            if pf:
                vol_params.append(pf)
            vol_rows = conn.execute(
                "SELECT"
                " d.id AS delivery_id,"
                " c.id AS contract_id,"
                " p.name AS platform,"
                " c.contract_no AS contract_no,"
                " s.name AS system_name,"
                " d.name AS delivery_name,"
                " d.status,"
                " d.acceptance_date,"
                " d.planned_acceptance_date,"
                " comp.name AS component,"
                " dc.planned AS planned_qty,"
                " dc.delivered AS delivered_qty"
                " FROM deliveries d"
                " JOIN systems s ON s.id = d.system_id"
                " JOIN contracts c ON c.id = d.contract_id"
                " JOIN contract_platforms cp ON cp.contract_id = c.id"
                " JOIN platforms p ON p.id = cp.platform_id"
                " JOIN delivery_components dc ON dc.delivery_id = d.id"
                " JOIN components comp ON comp.id = dc.component_id"
                " WHERE dc.planned > 0"
                " AND ("
                "   (d.acceptance_date != '' AND d.acceptance_date IS NOT NULL"
                "       AND (SUBSTR(d.acceptance_date,1,4) BETWEEN ? AND ?"
                "           OR d.acceptance_date = 'TBD'))"
                "   OR"
                "   (d.planned_acceptance_date != '' AND d.planned_acceptance_date IS NOT NULL"
                "       AND (SUBSTR(d.planned_acceptance_date,1,4) BETWEEN ? AND ?"
                "           OR d.planned_acceptance_date = 'TBD'))"
                " ) " + pc +
                " ORDER BY p.name, comp.name",
                vol_params
            ).fetchall()

            volume_rows = [
                {
                    "delivery_id":            int(r["delivery_id"]),
                    "contract_id":            int(r["contract_id"]),
                    "platform":               str(r["platform"] or ""),
                    "contract_no":            str(r["contract_no"] or ""),
                    "system_name":            str(r["system_name"] or ""),
                    "delivery_name":          str(r["delivery_name"] or ""),
                    "status":                 str(r["status"] or ""),
                    "acceptance_date":        str(r["acceptance_date"] or ""),
                    "planned_acceptance_date":str(r["planned_acceptance_date"] or ""),
                    "component":              str(r["component"] or ""),
                    "planned_qty":            float(r["planned_qty"] or 0),
                    "delivered_qty":          float(r["delivered_qty"] or 0),
                }
                for r in vol_rows
            ]

            self.progress.emit(95, "Tamamlanıyor...")
            self.finished.emit(contract_events, system_events, volume_rows)

        except Exception as exc:
            _log.exception("CalendarDataWorker hatası")
            self.failed.emit(str(exc))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

_STATUS_ORDER = {"geciken": 0, "kritik": 1, "normal": 2, "tamamlandi": 3, "belirsiz": 4, "bos": 9}
_COLOR  = {"geciken": "#e1473f", "kritik": "#e8b53f", "normal": "#397bd8", "tamamlandi": "#39a96b", "belirsiz": "#8b7cd8", "bos": "#d9e1ea"}
_BG     = {"geciken": "#fef2f2", "kritik": "#fffbeb", "normal":  "#e8f0fe", "tamamlandi": "#ecfdf5", "belirsiz": "#f1edfb"}
_FG     = {"geciken": "#b91c1c", "kritik": "#92400e", "normal":  "#1f5be3", "tamamlandi": "#047857", "belirsiz": "#6d28d9"}
_LABEL  = {"geciken": "Geciken", "kritik": "60 gün içinde", "normal": "Normal",
           "tamamlandi": "Teslim edildi", "belirsiz": "Tarihi belirsiz", "bos": "Kayıt yok"}

_EXTRA_QSS = """
QDialog { background: transparent; }

QToolTip {
    background: #334155;
    color: #f8fafc;
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
    opacity: 230;
}

QFrame#monthCard { border-radius:18px; }
QFrame#monthCard:hover { border-color:#7eb3d8 !important; }
QWidget#calBg { background: transparent; }
QWidget#detailSideBg { background:#f8fafc; border-right:1px solid #e2e8f0; }
QWidget#detailRightBg { background:#ffffff; }
QWidget#detailTopbarBg { background:#ffffff; border-bottom:1px solid #e2e8f0; }
QWidget#dayHeaderBg { background:#ffffff; border-bottom:1px solid #e2e8f0; }
QWidget#calHost { background:#ffffff; }

/* Gün hücreleri: gri kart, beyaz zemin üzerinde. Hover'da hafif koyulaşma +
   kenarlık rengi belirginleşmesi ile "kaldırılmış" his verir; gerçek
   yükselme/gölge animasyonu _build_cell içinde QGraphicsDropShadowEffect +
   QPropertyAnimation ile ayrıca uygulanır (bkz. _DayCellFrame). */
QFrame#dayCellNormal {
    background:#eef1f6; border:1px solid #dde4ec; border-radius:12px; min-height:90px;
}
QFrame#dayCellNormal:hover {
    background:#e4e9f1; border:1px solid #c7d2e0;
}
QFrame#dayCellToday {
    background:#eaf1ff; border:2px solid #1f5be3; border-radius:12px; min-height:90px;
}
QFrame#dayCellToday:hover { background:#e1ecff; }
QFrame#dayCellTodaySelected {
    background:#dbeafe; border:2.5px solid #1f5be3; border-radius:12px; min-height:90px;
    outline: 2px solid #93c5fd;
}
QFrame#dayCellTodaySelected:hover { background:#bfdbfe; }
QFrame#dayCellSelected {
    background:#eef4ff; border:2px solid #5b9bd5; border-radius:12px; min-height:90px;
}
QFrame#dayCellSelected:hover { background:#e6f0ff; }
QFrame#dayCellEmpty  { background:transparent; border:1px solid transparent; border-radius:12px; min-height:90px; }
QFrame#statCard { background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; }
QFrame#recCard  { background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; }

/* Mini takvim hücreleri (_MonthCard) — performans: per-widget setStyleSheet yerine
   tek seferlik QSS kuralı, sadece objectName ile seçiliyor. */
QFrame#miniCellToday {
    background: rgba(232,240,254,200);
    border: 1px solid rgba(57,123,216,.55);
    border-radius: 5px;
}
QFrame#miniCellHasEvent {
    background: rgba(255,255,255,180);
    border: 1px solid rgba(180,200,220,160);
    border-radius: 5px;
}
QFrame#miniCellEmpty {
    background: rgba(255,255,255,90);
    border: 1px solid rgba(200,215,230,120);
    border-radius: 5px;
}
QFrame#miniCellBlank { background: transparent; border: none; }

/* ScrollArea şeffaflık kuralları — BİLEREK hücre/kart kurallarından SONRA
   tanımlanır. Qt QSS'te aynı/yakın specificity'deki kurallarda sonradan
   tanımlanan kazanır (CSS'teki ID-selector önceliğinden farklı bir
   davranış); bu kural üstte olsaydı aşağıdaki dayCellNormal vb. QFrame
   arka planlarını "background:transparent" ile geçersiz kılardı, çünkü
   QScrollArea#plainScroll > QWidget > QWidget selector'ı QFrame'leri de
   kapsar (QFrame, QWidget'ın alt sınıfıdır). Sıra bozulursa gün hücreleri
   beyaz/şeffaf görünür. */
QScrollArea#plainScroll { border:none; background:transparent; }
QScrollArea#plainScroll > QWidget > QWidget { background:transparent; }
QScrollArea#yearGridScroll { border:none; background:transparent; }
QScrollArea#yearGridScroll > QWidget { background:transparent; }
QScrollArea#yearGridScroll QWidget#calBg { background:transparent; }

/* Modern ince scrollbar */
QScrollArea QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 4px 2px;
}
QScrollArea QScrollBar::handle:vertical {
    background: #d1d9e0;
    border-radius: 3px;
    min-height: 30px;
}
QScrollArea QScrollBar::handle:vertical:hover {
    background: #9aabb8;
}
QScrollArea QScrollBar::add-line:vertical,
QScrollArea QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollArea QScrollBar::add-page:vertical,
QScrollArea QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollArea QScrollBar:horizontal { height: 0px; }
"""

# Performans: STYLE + _EXTRA_QSS birleşimi sabit, her ay penceresi açılışında
# yeniden concat edilmesin diye modül yüklenirken bir kez hesaplanır.
_COMBINED_STYLE = STYLE + _EXTRA_QSS

# Ay detay penceresinde sağ taraftaki "Ay adı" başlığı + "PZT SAL ÇAR..."
# gün isimleri satırı birlikte, sol paneldeki "Kayıt Paneli" header'ı ile
# AYNI toplam yükseklikte bitmelidir; aksi halde lacivert header sınırı
# iki panelde farklı hizada görünür (kayık header sorunu). Tek noktadan
# yönetilsin diye sabitler burada tanımlanır.
_DETAIL_TOPBAR_HEIGHT = 70
_DAY_HEADER_HEIGHT = 34
_SIDE_HEADER_HEIGHT = _DETAIL_TOPBAR_HEIGHT + _DAY_HEADER_HEIGHT


_EXACT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_TBD_RE = re.compile(r"^(\d{4})-(\d{2})-TBD$")
_YEAR_TBD_RE = re.compile(r"^(\d{4})-TBD-TBD$")

# Esnek tarih tipleri:
#   exact              -> YYYY-MM-DD, gerçek date objesine çevrilebilir
#   month_unknown_day  -> YYYY-MM-TBD, yıl+ay belli
#   year_only          -> YYYY-TBD-TBD, sadece yıl belli
#   fully_unknown      -> TBD, hiçbir şey belli değil
#   na                 -> "-", boş veya tanınmayan değer (tarih uygulanmıyor)


def _date_kind(text: str) -> str:
    t = (text or "").strip()
    if not t or t == "-":
        return "na"
    if t == "TBD":
        return "fully_unknown"
    if _EXACT_RE.match(t):
        return "exact"
    if _MONTH_TBD_RE.match(t):
        return "month_unknown_day"
    if _YEAR_TBD_RE.match(t):
        return "year_only"
    return "na"


def _parse_date(text: str) -> Optional[date]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        return None


def _month_tbd_parts(text: str) -> Optional[Tuple[int, int]]:
    """'YYYY-MM-TBD' -> (year, month) ; month 1-indexed."""
    m = _MONTH_TBD_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _year_tbd_parts(text: str) -> Optional[int]:
    """'YYYY-TBD-TBD' -> year."""
    m = _YEAR_TBD_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1))


def _effective_date_raw(item: dict) -> str:
    """
    Tarih kaynağı kayıt tipine göre belirlenir:

    Sözleşme kaydı  -> completion_date (termin tarihi)
    Sistem kaydı    -> completion_date (termin tarihi)
    Teslimat kaydı  -> acceptance_date > planned_acceptance_date > ""

    "Teslimat" tip kontrolü: CalendarDataWorker type="Teslimat" olarak set eder.
    Sözleşme ve sistem kayıtları completion_date üzerinden takip edilir.

    ÖNEMLİ: acceptance_date alanı boş DEĞİL ama "-" (tarih uygulanmıyor)
    olabilir — bu, "henüz teslim alınmadı, planlanan tarihe bak" anlamına
    gelir, "uygulanmıyor" anlamına DEĞİL. "-" sadece tek başına, hiçbir
    alanda alternatif yoksa anlamlıdır. Bu yüzden acceptance_date "-" ise
    (gerçek bir tarih/TBD-varyantı taşımıyorsa) planned_acceptance_date'e
    düşülür; "-" hiçbir zaman doğrudan kullanılmaz.
    Ham string döner; format ayrımı _date_kind ile yapılır.
    """
    ctype = str(item.get("type") or "").lower()
    # Sadece "Teslimat" type'ı acceptance_date/planned_acceptance_date kullanır.
    # "Sözleşme", "Ana Sözleşme", "SD-*", "Sistem" → completion_date.
    if "teslimat" in ctype:
        acc = str(item.get("acceptance_date") or "").strip()
        if acc and acc != "-":
            return acc
        return str(item.get("planned_acceptance_date") or "").strip()
    # Sözleşme veya Sistem: completion_date
    return str(item.get("completion_date") or "").strip()


def _effective_date(item: dict) -> Optional[date]:
    """Geriye dönük uyumluluk: sadece exact tarihlerde date döner."""
    raw = _effective_date_raw(item)
    if _date_kind(raw) != "exact":
        return None
    return _parse_date(raw)


def _classify(item: dict, eff: Optional[date], today: date, date_kind: str = "exact") -> str:
    s = str(item.get("status") or "").lower()
    # Gerçek teslimat tarihi varsa → tamamlandı (gerçekleşen tarih her zaman
    # exact olmak zorunda). "-" placeholder'ı "henüz teslim edilmedi" demektir,
    # acceptance_date dolu sayılmaz — aksi halde her "-" kayıt yanlışlıkla
    # "tamamlandı/teslim edildi" sınıfına düşerdi.
    acc_raw = str(item.get("acceptance_date") or "").strip()
    if (acc_raw and acc_raw != "-") or "tamam" in s or "teslim" in s:
        return "tamamlandi"
    if date_kind != "exact" or eff is None:
        return "belirsiz"
    # planned_acceptance_date kullanılıyorsa normal sınıflandırma
    delta = (eff - today).days
    if delta < 0:  return "geciken"
    if delta <= 60: return "kritik"
    return "normal"


def _first_col(year: int, month1: int) -> int:
    """Pazartesi=0 … Pazar=6 (month1 is 1-indexed)."""
    return date(year, month1, 1).weekday()


def _elide(text: str, n: int = 16) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[:n - 1] + "…"


# ─────────────────────────────────────────────────────────────────────────────
class _HoverLiftFrame(QFrame):
    """
    Tıklanabilir kartlar için hover efekti.

    Performans notu: QGraphicsDropShadowEffect + QPropertyAnimation
    özellikle Windows'ta ağır GPU/CPU yüküne yol açıyordu (~42 eşzamanlı
    efekt: 12 ay kartı + 30 gün hücresi). Kaldırıldı; hover görünümü
    artık tamamen QSS ile sağlanıyor. Render maliyeti neredeyse sıfır.
    """
    clicked = Signal()

    def __init__(self, parent=None, shadow_color=(15, 23, 42, 35),
                 hover_color=(31, 91, 227, 55), blur_normal=10, blur_hover=18):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


# _ClickFrame: geriye dönük uyumluluk için ad korunuyor (tüm davranışı
# _HoverLiftFrame'den miras alır — artık gölge + hover animasyonu da içerir).
_ClickFrame = _HoverLiftFrame


# ─────────────────────────────────────────────────────────────────────────────
# Kayıt kartı (sol panel)
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Sol Panel — Ağaç yapısı (Platform → Sözleşme → SD → Sistem)
# ─────────────────────────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "geciken":    ("#fef2f2", "#a32d2d", "#e1473f"),
    "kritik":     ("#fffbeb", "#854f0b", "#e8b53f"),
    "normal":     ("#e6f1fb", "#185fa5", "#397bd8"),
    "tamamlandi": ("#eaf3de", "#047857", "#39a96b"),
    "belirsiz":   ("#f1edfb", "#6d28d9", "#8b7cd8"),
}
_STATUS_LABEL = {
    "geciken": "Geciken", "kritik": "60 gün",
    "normal": "Normal", "tamamlandi": "Teslim", "belirsiz": "Belirsiz",
}
_WORST_ORDER = ["geciken", "kritik", "normal", "tamamlandi", "belirsiz"]


def _worst_cls(classes):
    for c in _WORST_ORDER:
        if c in classes:
            return c
    return "normal"


def _sort_key(ev: dict):
    """
    Event sıralama anahtarı: exact tarihler gerçek tarihe göre önce gelir,
    esnek/belirsiz tarihler (None _eff_date) en sona, kendi aralarında ise
    bilinen kısma göre sıralanır (yıl-ay-TBD < sadece-yıl < tamamen-belirsiz).
    None ile date karşılaştırılamadığı için (TypeError) bu fonksiyon
    sorted()/min() çağrılarında her zaman kullanılmalı.
    """
    kind = ev.get("_date_kind", "exact")
    if kind == "exact" and ev.get("_eff_date"):
        return (0, ev["_eff_date"])
    if kind == "month_unknown_day":
        return (1, date(ev.get("_eff_year") or 9999, ev.get("_eff_month") or 12, 1))
    if kind == "year_only":
        return (2, date(ev.get("_eff_year") or 9999, 12, 31))
    return (3, date(9999, 12, 31))


_TR_MONTH_SHORT = [
    "", "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
]


# ─────────────────────────────────────────────────────────────────────────────
# Teslimat Hacmi yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def _volume_date_value(row: dict) -> str:
    """Bir volume satırı için efektif tarih raw string'ini döner.

    Gerçekleşmiş teslimat varsa acceptance_date, yoksa planned_acceptance_date.
    '-' değeri her durumda "tarih yok" anlamına gelir.
    """
    acc = str(row.get("acceptance_date") or "").strip()
    if acc and acc != "-":
        return acc
    return str(row.get("planned_acceptance_date") or "").strip()


def _format_qty(value: float) -> str:
    """12.0 → '12', 12.5 → '12,5'"""
    if value == int(value):
        return str(int(value))
    return str(value).replace(".", ",")


def _aggregate_volume_for_year(
    rows: list,
    year: int,
    platform_filter: str = "",
) -> dict:
    """Verilen yıl için bileşen bazında toplam hacim hesaplar.

    Dönüş:
        {
            "by_component": {
                "Kablo Seti": {
                    "total": 86.0,
                    "monthly": {1: 7.0, 2: 5.0, ...},
                    "delivery_ids": {1, 2, ...},
                }
            },
            "total_delivery_count": 20,
            "total_planned_qty": 251.0,
        }
    """
    by_comp: Dict[str, dict] = {}
    seen_delivery_ids: set = set()

    for row in rows:
        if platform_filter and row.get("platform") != platform_filter:
            continue
        qty = float(row.get("planned_qty") or 0)
        if qty <= 0:
            continue
        raw = _volume_date_value(row)
        kind = _date_kind(raw)
        if kind == "na":
            continue

        # Yıl kontrolü
        row_year = None
        if kind == "exact":
            d = _parse_date(raw)
            if d:
                row_year = d.year
        elif kind in ("month_unknown_day", "year_only"):
            if kind == "year_only":
                row_year = _year_tbd_parts(raw)
            else:  # month_unknown_day
                pm = _month_tbd_parts(raw)
                row_year = pm[0] if pm else None
        elif kind == "fully_unknown":
            row_year = None  # TBD → yıldan bağımsız, yıl panelinde "Tarihi belirsiz" grubu
        
        # TBD olanları yıl paneline dahil et (yıl belirli olanlar için yıl kontrolü yap)
        if kind != "fully_unknown" and row_year != year:
            continue

        comp = str(row.get("component") or "Bilinmiyor")
        if comp not in by_comp:
            by_comp[comp] = {"total": 0.0, "monthly": {}, "delivery_ids": set()}

        by_comp[comp]["total"] += qty
        by_comp[comp]["delivery_ids"].add(row.get("delivery_id"))
        seen_delivery_ids.add(row.get("delivery_id"))

        # Aylık dağılım (sadece ay belli olanlar)
        month_num = None
        if kind == "exact":
            d = _parse_date(raw)
            if d:
                month_num = d.month
        elif kind == "month_unknown_day":
            parts_m = _month_tbd_parts(raw)
            if parts_m:
                month_num = parts_m[1]

        if month_num is not None:
            by_comp[comp]["monthly"][month_num] = (
                by_comp[comp]["monthly"].get(month_num, 0.0) + qty
            )

    total_qty = sum(v["total"] for v in by_comp.values())
    return {
        "by_component": by_comp,
        "total_delivery_count": len(seen_delivery_ids),
        "total_planned_qty": total_qty,
    }


def _aggregate_volume_for_days(
    rows: list,
    year: int,
    month: int,  # 1-indexed
    selected_days: list,           # list[int | "unknown"]
    include_unknown_day: bool = False,
    platform_filter: str = "",
) -> dict:
    """Seçili günler için bileşen bazında toplam hacim hesaplar.

    selected_days içinde int günler ve "unknown" string'i olabilir.
    "unknown" → ay içindeki YYYY-MM-TBD kayıtları dahil edilir.

    Dönüş:
        {
            "by_component": {"Kablo Seti": 30.0, ...},
            "total_delivery_count": int,
            "total_planned_qty": float,
        }
    """
    by_comp: Dict[str, float] = {}
    seen_delivery_ids: set = set()
    exact_days = {d for d in selected_days if isinstance(d, int)}
    include_unk = include_unknown_day or ("unknown" in selected_days)

    for row in rows:
        if platform_filter and row.get("platform") != platform_filter:
            continue
        qty = float(row.get("planned_qty") or 0)
        if qty <= 0:
            continue
        raw = _volume_date_value(row)
        kind = _date_kind(raw)
        if kind == "na":
            continue

        matched = False
        if kind == "exact":
            d = _parse_date(raw)
            if d and d.year == year and d.month == month and d.day in exact_days:
                matched = True
        elif kind == "month_unknown_day" and include_unk:
            parts_m = _month_tbd_parts(raw)
            if parts_m and parts_m[0] == year and parts_m[1] == month:
                matched = True

        if not matched:
            continue

        comp = str(row.get("component") or "Bilinmiyor")
        by_comp[comp] = by_comp.get(comp, 0.0) + qty
        seen_delivery_ids.add(row.get("delivery_id"))

    total_qty = sum(by_comp.values())
    return {
        "by_component": by_comp,
        "total_delivery_count": len(seen_delivery_ids),
        "total_planned_qty": total_qty,
    }


def _volume_rows_for_deliveries(rows: list, delivery_ids: set) -> Dict[int, list]:
    """Verilen delivery_id'lere ait volume satırlarını delivery_id bazında gruplar.

    Dönüş: {delivery_id: [{"component": str, "planned_qty": float}, ...]}
    Akordeon kartlarının her birinin kendi bileşen listesini göstermesi için.
    """
    grouped: Dict[int, list] = {}
    for row in rows:
        did = row.get("delivery_id")
        if did not in delivery_ids:
            continue
        qty = float(row.get("planned_qty") or 0)
        if qty <= 0:
            continue
        grouped.setdefault(did, []).append({
            "component": str(row.get("component") or "Bilinmiyor"),
            "planned_qty": qty,
        })
    return grouped


def _fmt_flexible(raw: str) -> str:
    """Esnek tarih string'ini kullanıcıya gösterilecek okunabilir metne çevirir."""
    kind = _date_kind(raw)
    if kind == "exact":
        d = _parse_date(raw)
        return d.strftime("%d.%m.%Y") if d else raw
    if kind == "month_unknown_day":
        parts = _month_tbd_parts(raw)
        if parts:
            y, m = parts
            return f"{_TR_MONTH_SHORT[m]} {y} · gün belirsiz"
        return raw
    if kind == "year_only":
        y = _year_tbd_parts(raw)
        return f"{y} · ay/gün belirsiz" if y else raw
    if kind == "fully_unknown":
        return "Tarih belirlenecek"
    return "—"


def _date_label(ev: dict) -> str:
    """Tarihin ne olduğunu etiketle."""
    if ev.get("acceptance_date"):
        return "Teslimat"
    if ev.get("planned_acceptance_date") and "sistem" not in str(ev.get("type","")).lower():
        return "Planlanan"
    return "Termin"


def _date_display(ev: dict) -> tuple:
    """(etiket, tarih_str, renk) döndür. Esnek tarih formatlarını da okunabilir gösterir."""
    ctype = str(ev.get("type") or "").lower()
    acc = str(ev.get("acceptance_date") or "").strip()
    plan = str(ev.get("planned_acceptance_date") or "").strip()
    comp = str(ev.get("completion_date") or "").strip()

    if "sistem" in ctype:
        kind = _date_kind(comp)
        color = "#64748b" if kind == "exact" else _FG["belirsiz"]
        return ("Termin", _fmt_flexible(comp) if comp else "—", color)

    # "-" placeholder'ı "henüz teslim edilmedi" demektir (gerçekleşen
    # tarih yok); bu durumda planned_acceptance_date'e (TBD dahil) bakılır.
    if acc and acc != "-":
        # Gerçekleşen tarih kuralı: acceptance_date her zaman exact olmak
        # zorunda (kural: "Gerçekleşen tarih bugünden ileri bir tarih olamaz,
        # sadece YYYY-MM-DD kabul edilir"). Yine de savunmacı kalalım.
        d = _parse_date(acc)
        ds = d.strftime("%d.%m.%Y") if d else _fmt_flexible(acc)
        # Erken mi geç mi?
        if plan and d:
            pd = _parse_date(plan)
            if pd:
                diff = (d - pd).days
                if diff < 0:
                    return ("Teslimat ✓", f"{ds} ({abs(diff)}g erken)", "#047857")
                elif diff > 0:
                    return ("Teslimat ⚠", f"{ds} ({diff}g geç)", "#854f0b")
        return ("Teslimat", ds, "#047857")
    if plan:
        kind = _date_kind(plan)
        color = "#185fa5" if kind == "exact" else _FG["belirsiz"]
        return ("Planlanan", _fmt_flexible(plan), color)
    return ("—", "—", "#94a3b8")


class _BadgeLabel(QLabel):
    """Renkli durum etiketi."""
    def __init__(self, cls: str, parent=None):
        super().__init__(parent)
        bg, fg, _ = _STATUS_COLORS.get(cls, ("#f1f5f9", "#475569", "#94a3b8"))
        txt = _STATUS_LABEL.get(cls, cls)
        self.setText(txt)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:4px;"
            "padding:1px 6px; font-size:9px; font-weight:700; border:none;"
        )
        self.setFixedHeight(16)


class _TreeRow(QFrame):
    """Tıklanabilir ağaç satırı."""
    clicked = Signal()

    def __init__(self, indent: int, icon: str, label: str,
                 cls: str = "", has_children: bool = False,
                 date_lbl: str = "", date_val: str = "", date_color: str = "",
                 dimmed: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("treeRow")
        self._has_children = has_children
        self._expanded = True
        self.setStyleSheet("QFrame#treeRow{background:transparent; border:none;}")
        if has_children:
            self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(indent, 4, 8, 4)
        lay.setSpacing(6)

        if has_children:
            self._chev = QLabel("▶")
            self._chev.setStyleSheet(
                "background:transparent; color:#94a3b8; font-size:9px; border:none;"
            )
            self._chev.setFixedWidth(10)
            lay.addWidget(self._chev)
        else:
            spacer = QLabel()
            spacer.setFixedWidth(10)
            spacer.setStyleSheet("background:transparent; border:none;")
            lay.addWidget(spacer)

        if icon:
            ic = QLabel(icon)
            ic.setStyleSheet("background:transparent; color:#94a3b8; font-size:11px; border:none;")
            ic.setFixedWidth(14)
            lay.addWidget(ic)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"background:transparent; font-size:11px; font-weight:500;"
            f"color:{'#94a3b8' if dimmed else '#1e293b'}; border:none;"
        )
        name_lbl.setWordWrap(False)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(name_lbl, 1)

        if date_val and date_val != "—":
            dl = QLabel(date_val)
            dl.setStyleSheet(
                f"background:transparent; font-size:9px; color:{date_color}; border:none;"
                "white-space:nowrap;"
            )
            lay.addWidget(dl)

        if cls:
            lay.addWidget(_BadgeLabel(cls))

        if dimmed:
            self.setStyleSheet(
                "QFrame#treeRow{background:transparent; border:none; opacity:0.3;}"
            )

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        if hasattr(self, "_chev"):
            self._chev.setText("▼" if expanded else "▶")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._has_children:
            self.clicked.emit()
        super().mousePressEvent(ev)

    def enterEvent(self, ev):
        if self._has_children:
            self.setStyleSheet(
                "QFrame#treeRow{background:rgba(0,0,0,0.04); border:none; border-radius:6px;}"
            )
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.setStyleSheet("QFrame#treeRow{background:transparent; border:none;}")
        super().leaveEvent(ev)


class _CollapsibleSection(QWidget):
    """Açılır/kapanır içerik."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(1)
        self._visible = True

    def add(self, w: QWidget):
        self._lay.addWidget(w)

    def set_visible(self, v: bool):
        self._visible = v
        self.setVisible(v)


class _SideTreePanel(QWidget):
    """
    Sol panel — Platform > Sözleşme > Sistem (veya sadece Sözleşme).
    Mod: 'sistem' veya 'sozlesme'
    """

    def __init__(self, events: List[dict], year: int, month: int,
                 detail_handler=None, parent=None):
        super().__init__(parent)
        self._events = events
        self._year = year
        self._month = month
        self._month1 = month + 1
        self._detail_handler = detail_handler
        self._active_filter: Optional[str] = None
        self._view_mode = "sistem"  # "sistem" veya "sozlesme"
        self.setFixedWidth(320)
        self.setAutoFillBackground(True)
        self.setStyleSheet("QWidget{background:#f8fafc;}")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Üst kısım: gradient header ───────────────────────────────────
        # Sağ taraftaki "Ay adı" başlığı (_DETAIL_TOPBAR_HEIGHT) + gün
        # isimleri satırı (_DAY_HEADER_HEIGHT) ile aynı toplam yükseklikte
        # bitsin diye _SIDE_HEADER_HEIGHT kullanılır (bkz. tanım yukarıda).
        hdr = QWidget()
        hdr.setStyleSheet(
            "QWidget{"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1e293b, stop:1 #0f172a);"
            "}"
        )
        hdr.setFixedHeight(_SIDE_HEADER_HEIGHT)
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(2)
        hl.setAlignment(Qt.AlignVCenter)
        kicker = QLabel(f"{TR_MONTHS[self._month].upper()} {self._year}")
        kicker.setStyleSheet(
            "color:rgba(148,163,184,0.9); font-size:10px; font-weight:700;"
            "letter-spacing:.1em; background:transparent;"
        )
        hl.addWidget(kicker)
        title = QLabel("Kayıt Paneli")
        title.setStyleSheet(
            "color:#ffffff; font-size:17px; font-weight:900; background:transparent;"
        )
        hl.addWidget(title)
        subtitle = QLabel("Tıklanan güne göre filtrelenir")
        subtitle.setStyleSheet(
            "color:rgba(148,163,184,0.75); font-size:10.5px; font-weight:600;"
            "background:transparent;"
        )
        hl.addWidget(subtitle)
        outer.addWidget(hdr)

        # ── Stat kartları ─────────────────────────────────────────────────
        stats_w = QWidget()
        stats_w.setStyleSheet("QWidget{background:#f8fafc;}")
        sg = QGridLayout(stats_w)
        sg.setContentsMargins(10, 10, 10, 6)
        sg.setSpacing(6)
        self._stat_btns: Dict[str, tuple] = {}
        self._stat_nums: Dict[str, QLabel] = {}
        items = [
            ("geciken",    "Geciken", "#fef2f2", "#dc2626", "#e1473f"),
            ("kritik",     "60 gün",  "#fffbeb", "#d97706", "#e8b53f"),
            ("tamamlandi", "Teslim",  "#f0fdf4", "#16a34a", "#39a96b"),
            ("belirsiz",   "Belirsiz","#f1edfb", "#6d28d9", "#8b7cd8"),
            (None,         "Toplam",  "#f8fafc", "#475569", "#94a3b8"),
        ]
        for i, (key, lbl, bg, fg, border) in enumerate(items):
            card = QFrame()
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(
                f"QFrame{{background:{bg}; border:1.5px solid transparent;"
                f"border-radius:10px;}}"
            )
            if key:
                card.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 8, 8, 8)
            cl.setSpacing(1)
            num = QLabel("0")
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                f"background:transparent; font-size:22px; font-weight:900;"
                f"color:{fg}; border:none;"
            )
            sub = QLabel(lbl)
            sub.setAlignment(Qt.AlignCenter)
            sub.setStyleSheet(
                f"background:transparent; font-size:10px; font-weight:600;"
                f"color:{fg}; border:none;"
            )
            cl.addWidget(num)
            cl.addWidget(sub)
            sg.addWidget(card, i // 2, i % 2)
            self._stat_nums[key or "_total"] = num
            self._stat_btns[key or "_total"] = (card, border, bg)
            if key:
                card.mousePressEvent = (lambda e, k=key: self._on_stat_click(k))
            else:
                card.mousePressEvent = lambda e: self._on_stat_click(None)
        outer.addWidget(stats_w)

        # ── Filtre bar ────────────────────────────────────────────────────
        self._filter_bar = QWidget()
        self._filter_bar.setStyleSheet("QWidget{background:#f8fafc;}")
        fb_lay = QHBoxLayout(self._filter_bar)
        fb_lay.setContentsMargins(12, 0, 12, 4)
        fb_lay.setSpacing(6)
        self._filter_lbl = QLabel("")
        self._filter_lbl.setStyleSheet(
            "font-size:10px; font-weight:700; background:transparent; border:none;"
        )
        self._filter_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        fb_lay.addWidget(self._filter_lbl, 1)
        clear_btn = QPushButton("✕ temizle")
        clear_btn.setStyleSheet(
            "QPushButton{background:transparent; color:#94a3b8; border:0.5px solid #d1d9e0;"
            "border-radius:3px; padding:1px 5px; font-size:9px;}"
            "QPushButton:hover{color:#475569; background:#f1f5f9;}"
        )
        clear_btn.setFixedHeight(18)
        clear_btn.clicked.connect(lambda: self._on_stat_click(None))
        fb_lay.addWidget(clear_btn)
        self._filter_bar.setVisible(False)
        outer.addWidget(self._filter_bar)

        # ── Segmented control: Sistem / Sözleşme ─────────────────────────
        seg_w = QWidget()
        seg_w.setStyleSheet("QWidget{background:#f8fafc;}")
        seg_lay = QHBoxLayout(seg_w)
        seg_lay.setContentsMargins(12, 8, 12, 10)
        seg_lay.setSpacing(0)

        # Tek bir pill container
        pill_container = QFrame()
        pill_container.setAttribute(Qt.WA_StyledBackground, True)
        pill_container.setStyleSheet(
            "QFrame{background:#e2e8f0; border-radius:10px;}"
        )
        pill_container.setFixedHeight(40)
        pill_lay = QHBoxLayout(pill_container)
        pill_lay.setContentsMargins(4, 4, 4, 4)
        pill_lay.setSpacing(2)

        self._btn_sistem = QPushButton("🔧  Sistem")
        self._btn_sozlesme = QPushButton("📄  Sözleşme")
        for btn in [self._btn_sistem, self._btn_sozlesme]:
            btn.setFixedHeight(32)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(
                "QPushButton{background:transparent; color:#64748b; border:none;"
                "border-radius:7px; font-size:12px; font-weight:600; padding:0 12px;}"
                "QPushButton:hover{background:rgba(255,255,255,200); color:#1e293b;}"
            )
        self._btn_sistem.clicked.connect(lambda: self._set_mode("sistem"))
        self._btn_sozlesme.clicked.connect(lambda: self._set_mode("sozlesme"))
        pill_lay.addWidget(self._btn_sistem)
        pill_lay.addWidget(self._btn_sozlesme)
        seg_lay.addWidget(pill_container)
        outer.addWidget(seg_w)
        self._update_mode_buttons()

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#e2e8f0; max-height:1px;")
        outer.addWidget(sep)

        # ── Ağaç scroll ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("plainScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._tree_host = QWidget()
        self._tree_host.setStyleSheet("QWidget{background:#f8fafc;}")
        self._tree_lay = QVBoxLayout(self._tree_host)
        self._tree_lay.setContentsMargins(8, 6, 8, 10)
        self._tree_lay.setSpacing(1)
        self._tree_lay.addStretch()
        scroll.setWidget(self._tree_host)
        outer.addWidget(scroll, 1)

        self._refresh_tree()

    def _set_mode(self, mode: str):
        self._view_mode = mode
        self._update_mode_buttons()
        self._refresh_tree()

    def _update_mode_buttons(self):
        active = (
            "QPushButton{background:#ffffff; color:#1e293b; border:none;"
            "border-radius:6px; font-size:11px; font-weight:700; padding:0 10px;}"
        )
        inactive = (
            "QPushButton{background:transparent; color:#64748b; border:none;"
            "border-radius:6px; font-size:11px; font-weight:600; padding:0 10px;}"
            "QPushButton:hover{background:rgba(255,255,255,180); color:#1e293b;}"
        )
        self._btn_sistem.setStyleSheet(
            active if self._view_mode == "sistem" else inactive
        )
        self._btn_sozlesme.setStyleSheet(
            active if self._view_mode == "sozlesme" else inactive
        )

    def _refresh_tree(self):
        # Temizle
        while self._tree_lay.count() > 1:
            item = self._tree_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Stats güncelle
        c = self._counts()
        for k, num in self._stat_nums.items():
            num.setText(str(len(self._events) if k == "_total" else c.get(k, 0)))

        # Stat kartı vurgusu
        for k, (card, border_color, bg) in self._stat_btns.items():
            active = (k == self._active_filter) or (k == "_total" and not self._active_filter)
            if active and k != "_total":
                card.setStyleSheet(
                    f"QFrame{{background:{bg}; border:1.5px solid {border_color}; border-radius:8px;}}"
                )
            else:
                card.setStyleSheet(
                    f"QFrame{{background:{bg}; border:1.5px solid transparent; border-radius:8px;}}"
                )

        events = self._filtered_events()
        if not events:
            empty = QLabel("Bu filtrede kayıt yok.")
            empty.setStyleSheet(
                "color:#94a3b8; font-size:11px; background:transparent; padding:12px;"
            )
            empty.setAlignment(Qt.AlignCenter)
            self._tree_lay.insertWidget(0, empty)
            return

        if self._view_mode == "sistem":
            self._render_sistem_tree(events)
        else:
            self._render_sozlesme_tree(events)

    def _render_sistem_tree(self, events: List[dict]):
        """Platform > Sözleşme No > Sistem adı  (lazy: alt kayıtlar açılınca render)"""
        grouped: Dict[str, Dict[str, List[dict]]] = {}
        for ev in events:
            pl = str(ev.get("platform") or "?")
            no = str(ev.get("no") or "?")
            grouped.setdefault(pl, {}).setdefault(no, []).append(ev)

        insert_idx = 0
        for platform in sorted(grouped):
            pl_evs = grouped[platform]
            all_pl = [e for evs in pl_evs.values() for e in evs]
            pl_cls = _worst_cls([e["_cls"] for e in all_pl])

            pl_row = _TreeRow(
                indent=6, icon="●", label=platform,
                cls=pl_cls, has_children=True,
                parent=self._tree_host
            )
            self._tree_lay.insertWidget(insert_idx, pl_row); insert_idx += 1
            pl_sec = _CollapsibleSection(self._tree_host)
            pl_sec.set_visible(False)   # başlangıçta kapalı — lazy
            self._tree_lay.insertWidget(insert_idx, pl_sec); insert_idx += 1

            # Lazy render: section ilk kez açılınca içini doldur
            _loaded = [False]
            def _on_toggle(chk=pl_row, sec=pl_sec,
                           no_map=pl_evs, loaded=_loaded):
                if not loaded[0]:
                    loaded[0] = True
                    self._fill_sistem_section(sec, no_map)
                self._toggle(chk, sec)

            pl_row.clicked.connect(_on_toggle)

    def _fill_sistem_section(self, pl_sec: "_CollapsibleSection",
                              no_map: Dict[str, List[dict]]) -> None:
        """Platform section'ının içini sözleşme+sistem satırlarıyla doldurur."""
        for no in sorted(no_map):
            no_evs = no_map[no]
            no_lbl = QLabel(f"  📄 {no}")
            no_lbl.setStyleSheet(
                "background:transparent; font-size:11px; font-weight:600;"
                "color:#374151; padding:4px 6px 2px 24px; border:none;"
            )
            pl_sec.add(no_lbl)
            for ev in sorted(no_evs, key=_sort_key):
                _, dval, dcol = _date_display(ev)
                raw    = str(ev.get("title") or "")
                no_str = str(ev.get("no") or "")
                label  = raw[len(no_str)+3:] if raw.startswith(no_str + " · ") else (raw or no_str)
                if not label or label == no_str:
                    label = str(ev.get("type") or "")
                dimmed = self._active_filter is not None and ev["_cls"] != self._active_filter
                sys_row = _TreeRow(
                    indent=38, icon="·", label=label,
                    cls=ev["_cls"], has_children=False,
                    date_val=dval, date_color=dcol,
                    dimmed=dimmed, parent=self._tree_host
                )
                sys_row.setCursor(Qt.PointingHandCursor)
                ev_ref = ev
                sys_row.mousePressEvent = lambda e, ev_=ev_ref: self._on_item_click(ev_)
                pl_sec.add(sys_row)

    def _render_sozlesme_tree(self, events: List[dict]):
        """Platform > Sözleşme No (sadece)"""
        # Gruplama: platform → no → en kötü durum
        grouped: Dict[str, Dict[str, List[dict]]] = {}
        for ev in events:
            pl = str(ev.get("platform") or "?")
            no = str(ev.get("no") or "?")
            grouped.setdefault(pl, {}).setdefault(no, []).append(ev)

        insert_idx = 0
        for platform in sorted(grouped):
            pl_evs = grouped[platform]
            all_pl = [e for evs in pl_evs.values() for e in evs]
            pl_cls = _worst_cls([e["_cls"] for e in all_pl])

            pl_row = _TreeRow(
                indent=6, icon="●", label=platform,
                cls=pl_cls, has_children=True,
                parent=self._tree_host
            )
            self._tree_lay.insertWidget(insert_idx, pl_row); insert_idx += 1
            pl_sec = _CollapsibleSection(self._tree_host)
            self._tree_lay.insertWidget(insert_idx, pl_sec); insert_idx += 1
            pl_row.clicked.connect(lambda chk=pl_row, sec=pl_sec: self._toggle(chk, sec))

            for no in sorted(pl_evs):
                no_evs = pl_evs[no]
                no_cls = _worst_cls([e["_cls"] for e in no_evs])
                # En erken effective date
                earliest = min(no_evs, key=_sort_key)
                _, dval, dcol = _date_display(earliest)
                # Sözleşme no satırı — tıklanabilir, ok yok
                soz_w = QFrame()
                soz_w.setStyleSheet(
                    f"QFrame{{background:transparent; border:none; border-radius:6px;}}"
                )
                soz_w.setCursor(Qt.PointingHandCursor)
                soz_lay = QHBoxLayout(soz_w)
                soz_lay.setContentsMargins(28, 3, 8, 3)
                soz_lay.setSpacing(6)
                soz_icon = QLabel("📄")
                soz_icon.setStyleSheet("background:transparent; font-size:11px; border:none;")
                soz_lbl = QLabel(no)
                soz_lbl.setStyleSheet(
                    "background:transparent; font-size:11px; font-weight:600;"
                    "color:#374151; border:none;"
                )
                soz_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                soz_date = QLabel(dval)
                soz_date.setStyleSheet(
                    f"background:transparent; font-size:9px; color:{dcol}; border:none;"
                )
                soz_badge = _BadgeLabel(no_cls)
                soz_lay.addWidget(soz_icon)
                soz_lay.addWidget(soz_lbl, 1)
                soz_lay.addWidget(soz_date)
                soz_lay.addWidget(soz_badge)
                ev_ref = earliest
                soz_w.mousePressEvent = lambda e, ev_=ev_ref: self._on_item_click(ev_)
                pl_sec.add(soz_w)

    def _on_item_click(self, ev: dict):
        if self._detail_handler:
            self._detail_handler(ev)

    def _toggle(self, row: _TreeRow, section: _CollapsibleSection):
        expanded = not section._visible
        section.set_visible(expanded)
        row.set_expanded(expanded)

    def _on_stat_click(self, key: Optional[str]):
        if key is None or key == self._active_filter:
            self._active_filter = None
        else:
            self._active_filter = key

        # Filtre bar
        if self._active_filter:
            bg, fg, _ = _STATUS_COLORS.get(self._active_filter, ("", "#374151", ""))
            self._filter_lbl.setText(
                f"● {_STATUS_LABEL.get(self._active_filter, '')} filtresi aktif"
            )
            self._filter_lbl.setStyleSheet(
                f"font-size:10px; font-weight:700; color:{fg}; background:transparent; border:none;"
            )
            self._filter_bar.setVisible(True)
        else:
            self._filter_bar.setVisible(False)

        self._refresh_tree()

    def update_events(self, events: List[dict]):
        self._events = events
        self._refresh_tree()

    # ── Veri yardımcıları ────────────────────────────────────────────────
    def _counts(self) -> Dict[str, int]:
        c = {"geciken": 0, "kritik": 0, "tamamlandi": 0, "belirsiz": 0}
        for e in self._events:
            if e["_cls"] in c:
                c[e["_cls"]] += 1
        return c

    def _filtered_events(self) -> List[dict]:
        f = self._active_filter
        if not f:
            return list(self._events)
        return [e for e in self._events if e["_cls"] == f]

    def _group_by_platform(self, events: List[dict]) -> Dict[str, Dict[str, List[dict]]]:
        result: Dict[str, Dict[str, List[dict]]] = {}
        for ev in events:
            pl = str(ev.get("platform") or "?")
            no = str(ev.get("no") or "?")
            result.setdefault(pl, {}).setdefault(no, []).append(ev)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Teslimat Hacmi — Yıl Modal Penceresi
# ─────────────────────────────────────────────────────────────────────────────
_VOL_COMPONENT_STYLE = """
QFrame#volCompRow {
    background:#ffffff;
    border:1px solid #e5e9f0;
    border-radius:10px;
}
QFrame#volCompRow:hover {
    background:#f5f8ff;
    border:1px solid #c7d5ef;
}
QFrame#volCompRowOpen {
    background:#eef4ff;
    border:1.5px solid #397bd8;
    border-radius:10px;
}
QFrame#volExpandPanel {
    background:#f8fafc;
    border:1px solid #e5e9f0;
    border-left:3px solid #397bd8;
    border-radius:0px 0px 10px 10px;
}
QScrollBar:vertical {
    width:6px; background:transparent;
}
QScrollBar::handle:vertical {
    background:rgba(100,120,160,0.25);
    border-radius:3px; min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""


class _ComponentVolumeRow(QWidget):
    """Tek bileşen satırı: isim + toplam + expand bölümü."""

    def __init__(self, comp_name: str, data: dict, max_qty: float, parent=None):
        super().__init__(parent)
        self._comp_name = comp_name
        self._data = data
        self._max_qty = max_qty
        self._expanded = False
        self._expand_panel: Optional[QWidget] = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._build_row()

    def _build_row(self):
        self._row_frame = QFrame()
        self._row_frame.setObjectName("volCompRow")
        self._row_frame.setCursor(Qt.PointingHandCursor)
        rl = QHBoxLayout(self._row_frame)
        rl.setContentsMargins(18, 14, 14, 14)
        rl.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(2)
        name_lbl = QLabel(self._comp_name)
        name_lbl.setStyleSheet(
            "font-size:14px; font-weight:700; color:#1e293b; background:transparent;"
        )
        sub_lbl = QLabel("Yıl toplamı · aylık dağılım için tıkla")
        sub_lbl.setStyleSheet(
            "font-size:11px; color:#397bd8; background:transparent;"
        )
        left.addWidget(name_lbl)
        left.addWidget(sub_lbl)
        rl.addLayout(left, 1)

        qty_lbl = QLabel(
            f'<span style="font-size:22px;font-weight:900;color:#1e293b;">'
            f'{_format_qty(self._data["total"])}</span>'
            f'<span style="font-size:12px;color:#6b7280;"> adet</span>'
        )
        qty_lbl.setTextFormat(Qt.RichText)
        rl.addWidget(qty_lbl)

        self._chevron = QLabel("▾")
        self._chevron.setStyleSheet(
            "font-size:14px; color:#397bd8; background:transparent; padding:0 4px;"
        )
        rl.addWidget(self._chevron)

        self._row_frame.mousePressEvent = lambda e: self._toggle()
        self._layout.addWidget(self._row_frame)

    def _toggle(self):
        self._expanded = not self._expanded
        self._row_frame.setObjectName(
            "volCompRowOpen" if self._expanded else "volCompRow"
        )
        self._row_frame.style().unpolish(self._row_frame)
        self._row_frame.style().polish(self._row_frame)
        self._chevron.setText("▴" if self._expanded else "▾")

        if self._expanded:
            self._expand_panel = self._build_expand()
            self._layout.addWidget(self._expand_panel)
        else:
            if self._expand_panel:
                self._expand_panel.setParent(None)
                self._expand_panel = None

    def _build_expand(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("volExpandPanel")
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(18, 14, 18, 14)
        vl.setSpacing(0)

        title = QLabel(f"{self._comp_name} · Aylık dağılım")
        title.setStyleSheet(
            "font-size:12px; font-weight:700; color:#374151; background:transparent;"
            "margin-bottom:10px;"
        )
        vl.addWidget(title)

        monthly = self._data.get("monthly", {})
        if not monthly:
            empty = QLabel("Bu bileşen için aylık dağılım verisi yok.")
            empty.setStyleSheet("font-size:12px; color:#94a3b8; background:transparent;")
            vl.addWidget(empty)
            return panel

        max_m = max(monthly.values(), default=1) or 1
        for month_num in sorted(monthly.keys()):
            qty = monthly[month_num]
            row_w = QWidget()
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 5, 0, 5)
            rl.setSpacing(12)

            month_lbl = QLabel(TR_MONTHS[month_num - 1])
            month_lbl.setFixedWidth(60)
            month_lbl.setStyleSheet(
                "font-size:12px; color:#374151; background:transparent;"
            )
            rl.addWidget(month_lbl)

            qty_lbl = QLabel(f"{_format_qty(qty)} adet")
            qty_lbl.setFixedWidth(70)
            qty_lbl.setStyleSheet(
                "font-size:12px; font-weight:600; color:#1e293b; background:transparent;"
            )
            rl.addWidget(qty_lbl)

            # Gradyan bar
            bar_bg = QFrame()
            bar_bg.setFixedHeight(10)
            bar_bg.setStyleSheet(
                "background:#e8edf3; border-radius:5px;"
            )
            bar_fill = QFrame(bar_bg)
            bar_fill.setFixedHeight(10)
            pct = min(qty / max_m, 1.0)
            bar_fill.setStyleSheet(
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #4ade80,stop:0.5 #f59e0b,stop:1 #ef4444);"
                "border-radius:5px;"
            )
            bar_fill.setFixedWidth(max(6, int(pct * 260)))
            rl.addWidget(bar_bg, 1)
            vl.addWidget(row_w)

        return panel


class _YearVolumeDialog(QWidget):
    """
    Yıl Teslimat Hacmi modal penceresi.
    Ana takvim penceresi üzerinde dim overlay + merkezi beyaz kart.
    _MonthDetailDialog ile aynı backdrop/animasyon yapısını kullanır.
    """
    closed = Signal()

    def __init__(self, volume_rows: list, year: int,
                 platform_filter: str = "", parent=None):
        super().__init__(parent)
        self._volume_rows = volume_rows
        self._year = year
        self._pf = platform_filter

        self.setGeometry(parent.rect() if parent else self.geometry())
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet(_VOL_COMPONENT_STYLE)
        self._build()
        # Fade-in — _MonthDetailDialog ile aynı süre ve easing
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim
        self.show()
        self.raise_()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        if hasattr(self, "_backdrop"):
            self._backdrop.setGeometry(self.rect())
        if hasattr(self, "_card"):
            self._position_card()
        super().resizeEvent(event)

    def _build(self):
        # Backdrop — _MonthDetailDialog ile aynı: tıklanınca kapat, takvim arkada görünür
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("QWidget{background:rgba(10,16,26,0.38);}")
        self._backdrop.setGeometry(self.rect())
        self._backdrop.lower()
        self._backdrop.mousePressEvent = lambda e: self.close()

        agg = _aggregate_volume_for_year(
            self._volume_rows, self._year, self._pf
        )
        by_comp = agg["by_component"]
        total_count = agg["total_delivery_count"]
        total_qty = agg["total_planned_qty"]

        # Kart
        card = QFrame(self)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame{"
            "background:#ffffff; border-radius:16px;"
            "}"
        )
        card.setFixedWidth(680)
        card.setMaximumHeight(int(self.height() * 0.88))

        # Kart konumlandırma: merkez
        self._card = card
        self._position_card()

        vl = QVBoxLayout(card)
        vl.setContentsMargins(32, 28, 32, 28)
        vl.setSpacing(0)

        # Başlık
        sub_lbl = QLabel("TESLİMAT HACMİ")
        sub_lbl.setStyleSheet(
            "font-size:11px; font-weight:700; color:#397bd8;"
            "letter-spacing:1.5px; background:transparent;"
        )
        vl.addWidget(sub_lbl)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 4, 0, 20)
        title_lbl = QLabel(f"{self._year} Yılı Teslimat Hacmi")
        title_lbl.setStyleSheet(
            "font-size:22px; font-weight:900; color:#1e293b; background:transparent;"
        )
        title_row.addWidget(title_lbl, 1)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:#f1f5f9; border:none; border-radius:18px;"
            "font-size:18px; font-weight:600; color:#64748b;}"
            "QPushButton:hover{background:#e2e8f0; color:#1e293b;}"
        )
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)
        vl.addLayout(title_row)

        # Bölüm başlığı
        sec_lbl = QLabel("Bileşen Bazında Planlanan Teslimat")
        sec_lbl.setStyleSheet(
            "font-size:13px; font-weight:700; color:#374151; background:transparent;"
            "margin-bottom:10px;"
        )
        vl.addWidget(sec_lbl)

        # Scroll alan
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setAttribute(Qt.WA_StyledBackground, True)
        scroll.setStyleSheet(
            "QScrollArea{background:#ffffff; border:none;}"
            "QScrollArea > QWidget > QWidget{background:#ffffff;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:rgba(100,120,160,0.25);"
            "border-radius:3px;min-height:20px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        comp_host = QWidget()
        comp_host.setAttribute(Qt.WA_StyledBackground, True)
        comp_host.setStyleSheet("background:#ffffff;")
        comp_lay = QVBoxLayout(comp_host)
        comp_lay.setContentsMargins(0, 0, 0, 0)
        comp_lay.setSpacing(8)

        if not by_comp:
            empty_lbl = QLabel("Bu dönem için teslimat hacmi verisi bulunamadı.")
            empty_lbl.setStyleSheet(
                "font-size:13px; color:#94a3b8; background:#f8fafc;"
                "border-radius:10px; padding:18px 20px;"
            )
            comp_lay.addWidget(empty_lbl)
        else:
            sorted_comps = sorted(
                by_comp.items(), key=lambda x: x[1]["total"], reverse=True
            )
            max_qty = sorted_comps[0][1]["total"] if sorted_comps else 1
            for i, (comp_name, data) in enumerate(sorted_comps):
                row_w = _ComponentVolumeRow(comp_name, data, max_qty)
                if i == 0:
                    row_w._toggle()  # İlk bileşen açık gelsin
                comp_lay.addWidget(row_w)

        comp_lay.addStretch()
        scroll.setWidget(comp_host)
        vl.addWidget(scroll, 1)

        # Ayırıcı
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e5e9f0; margin:16px 0 8px 0;")
        vl.addWidget(sep)

        # Toplamlar
        totals_host = QWidget()
        totals_host.setAttribute(Qt.WA_StyledBackground, True)
        totals_host.setStyleSheet("background:transparent;")
        totals_lay = QVBoxLayout(totals_host)
        totals_lay.setContentsMargins(0, 0, 0, 0)
        totals_lay.setSpacing(0)
        for label_txt, val_txt in [
            ("Toplam teslimat kaydı", str(total_count)),
            ("Toplam planlanan adet",
             f"{_format_qty(total_qty)} adet" if total_qty > 0 else "0 adet"),
        ]:
            row_w = QWidget()
            row_w.setAttribute(Qt.WA_StyledBackground, True)
            row_w.setStyleSheet("background:transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 8, 0, 2)
            lbl = QLabel(label_txt)
            lbl.setStyleSheet(
                "font-size:13px; font-weight:700; color:#374151; background:transparent;"
            )
            val = QLabel(val_txt)
            val.setStyleSheet(
                "font-size:13px; font-weight:700; color:#1e293b; background:transparent;"
            )
            row_l.addWidget(lbl, 1)
            row_l.addWidget(val)
            totals_lay.addWidget(row_w)
        vl.addWidget(totals_host)

    def _position_card(self):
        pw = self.width()
        ph = self.height()
        cw = self._card.width() if self._card.width() > 10 else 680
        ch = min(int(ph * 0.88), max(self._card.sizeHint().height() + 20, 420))
        x = (pw - cw) // 2
        y = (ph - ch) // 2
        self._card.setFixedSize(cw, ch)
        self._card.move(max(0, x), max(0, y))

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        if hasattr(self, "_card"):
            self._position_card()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """Kart dışına tıklanınca kapat."""
        if hasattr(self, "_card"):
            if not self._card.geometry().contains(event.pos()):
                self.close()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Teslimat Hacmi — Ay Detay Sağ Panel
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Birleşik Sağ Panel — Ay Özeti + Seçili Kayıtlar (akordeon) + Teslimat Hacmi
# ─────────────────────────────────────────────────────────────────────────────
class _RecordAccordionCard(QFrame):
    """
    Tek bir teslimat/kabul kaydı için akordeon kart.
    Varsayılan KAPALI — başlığa tıklayınca bileşen listesi açılır/kapanır.
    Sağdaki ↗ ikonu akordeonu etkilemeden kaydın asıl detay ekranını açar.
    """

    def __init__(self, ev: dict, components: list,
                 open_handler: Optional[Callable[[dict], None]] = None,
                 parent=None):
        super().__init__(parent)
        self._ev = ev
        self._components = components
        self._open_handler = open_handler
        self._expanded = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("recAccordion")
        self._apply_frame_style()
        self._build()

    def _apply_frame_style(self):
        self.setStyleSheet(
            "QFrame#recAccordion{background:#ffffff; border:1px solid #e2e8f0;"
            "border-radius:9px;}"
        )

    def _build(self):
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── Başlık satırı ────────────────────────────────────────────────
        head = QWidget()
        head.setCursor(Qt.PointingHandCursor)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(11, 9, 8, 9)
        hl.setSpacing(8)

        cls = self._ev.get("_cls", "normal")
        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setMinimumHeight(16)
        bar.setStyleSheet(
            f"background:{_COLOR.get(cls, _COLOR['normal'])}; border-radius:2px;"
        )
        hl.addWidget(bar)

        info = QVBoxLayout()
        info.setSpacing(1)
        title = str(self._ev.get("title") or self._ev.get("no") or "")
        name_lbl = QLabel(_elide(title, 30))
        name_lbl.setStyleSheet(
            "font-size:12px; font-weight:900; color:#1e293b; background:transparent;"
        )
        name_lbl.setMaximumWidth(220)
        if len(title) > 30:
            # Tam adı tooltip (sohbet baloncuğu) olarak göster
            name_lbl.setToolTip(title)
        sysname = str(self._ev.get("system_label") or "")
        status_lbl = _status_label_for(self._ev)
        meta_txt = f"{sysname} · {status_lbl}" if sysname else status_lbl
        meta_lbl = QLabel(_elide(meta_txt, 36))
        meta_lbl.setStyleSheet(
            "font-size:10px; font-weight:700; color:#64748b; background:transparent;"
        )
        if len(meta_txt) > 36:
            meta_lbl.setToolTip(meta_txt)
        info.addWidget(name_lbl)
        info.addWidget(meta_lbl)
        hl.addLayout(info, 1)

        # Detay-aç ikonu — akordeonu etkilemez
        open_btn = QPushButton("↗")
        open_btn.setFixedSize(28, 26)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setToolTip("Kaydı aç")
        open_btn.setStyleSheet(
            "QPushButton{background:#f1f5f9; border:1px solid #dbe6f0;"
            "border-radius:7px; color:#475569; font-size:14px; font-weight:900;"
            "padding:0px; letter-spacing:0px;}"
            "QPushButton:hover{border-color:#397bd8; color:#1f5be3; background:#dbeafe;}"
        )
        if self._open_handler:
            open_btn.clicked.connect(lambda: self._open_handler(self._ev))
        hl.addWidget(open_btn)

        self._chevron = QLabel("▾")
        self._chevron.setStyleSheet(
            "font-size:10px; color:#94a3b8; background:transparent;"
        )
        hl.addWidget(self._chevron)

        head.mousePressEvent = lambda e: self._toggle()
        vl.addWidget(head)

        # ── Gövde (bileşen listesi) — varsayılan gizli ────────────────────
        self._body = QWidget()
        self._body.setVisible(False)
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(23, 0, 11, 10)
        bl.setSpacing(4)
        if self._components:
            for comp in self._components:
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 2, 0, 2)
                cname = QLabel(str(comp.get("component") or ""))
                cname.setStyleSheet(
                    "font-size:11px; font-weight:700; color:#475569; background:transparent;"
                )
                cqty = QLabel(f"{_format_qty(comp.get('planned_qty', 0))} adet")
                cqty.setStyleSheet(
                    "font-size:11px; font-weight:900; color:#1e293b; background:transparent;"
                )
                rl.addWidget(cname, 1)
                rl.addWidget(cqty)
                bl.addWidget(row)
        else:
            empty = QLabel("Bu kayıt için bileşen bilgisi yok.")
            empty.setStyleSheet(
                "font-size:10.5px; color:#94a3b8; background:transparent;"
            )
            bl.addWidget(empty)
        vl.addWidget(self._body)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._chevron.setText("▴" if self._expanded else "▾")


def _status_label_for(ev: dict) -> str:
    cls = ev.get("_cls", "")
    return {
        "geciken": "Geciken",
        "kritik": "60 gün içinde",
        "normal": "Normal",
        "tamamlandi": "Teslim edildi",
        "belirsiz": "Tarih belirsiz",
    }.get(cls, "Normal")


class _UnifiedSidePanel(QWidget):
    """
    Ay detay ekranının TEK sağ paneli.

    Eskiden sol "Kayıt Paneli" (_SideTreePanel) ile sağ "Teslimat Hacmi"
    paneli (_MonthVolumePanel) ayrı ayrı duruyordu. Bu sınıf ikisini
    birleştirir:

      1) Ay özeti  — kompakt 4'lü durum şeridi (geciken/60gün/teslim/belirsiz)
      2) Seçim alanı — duruma göre 3 farklı görünüm:
           a) Hiçbir şey seçili değil  → "Ayın tamamı" bilgi metni
           b) Bir/birden fazla GÜN seçili → o günlerin teslimat kayıtları,
              her biri akordeon kart (varsayılan kapalı)
           c) Bir TBD kapsülü seçili → o tek kaydın akordeon kartı
           Not: gün seçimi ile TBD kapsül seçimi birbirini dışlar; ikisi
           aynı anda aktif olamaz (_MonthDetailDialog seçim setini buna
           göre yönetir).
      3) Bileşen bazında planlanan adet · toplam — seçimdeki TÜM kayıtların
         bileşenlerinin toplamı
      4) Toplamlar — teslimat kaydı sayısı + planlanan adet
    """

    def __init__(self, events: List[dict], unknown_day_events: List[dict],
                 volume_rows: list, year: int, month: int,
                 fully_unknown_events: Optional[List[dict]] = None,
                 detail_handler: Optional[Callable[[dict], bool]] = None,
                 parent=None):
        super().__init__(parent)
        self._events = events                      # ayın TÜM (exact) event'leri
        self._unknown_day_events = unknown_day_events  # YYYY-MM-TBD event'leri
        # TBD + YYYY-TBD-TBD teslimatlar — takvimde gün hücresine girmezler
        # ama bileşen toplamı hesabına dahil edilirler
        self._fully_unknown_events = fully_unknown_events or []
        self._volume_rows = volume_rows
        self._year = year
        self._month = month  # 1-indexed
        self._detail_handler = detail_handler

        self.setMinimumWidth(340)
        self.setMaximumWidth(380)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget{background:#ffffff;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:rgba(100,120,160,0.25);"
            "border-radius:3px;min-height:20px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        self._build()

    # ── Skeleton ─────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Başlık
        head = QWidget()
        head.setStyleSheet("background:transparent;")
        hl = QVBoxLayout(head)
        hl.setContentsMargins(20, 18, 20, 14)
        hl.setSpacing(2)
        kicker = QLabel(f"{TR_MONTHS[self._month - 1].upper()} {self._year}")
        kicker.setStyleSheet(
            "font-size:10px; font-weight:900; color:#1f5be3;"
            "letter-spacing:1.2px; background:transparent;"
        )
        hl.addWidget(kicker)
        title = QLabel("Kayıt & Teslimat Hacmi")
        title.setStyleSheet(
            "font-size:17px; font-weight:900; color:#1e293b; background:transparent;"
        )
        hl.addWidget(title)
        sub = QLabel("Teslimat / kabul kaydı bazlı")
        sub.setStyleSheet(
            "font-size:10.5px; font-weight:700; color:#94a3b8; background:transparent;"
        )
        hl.addWidget(sub)
        outer.addWidget(head)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e2e8f0; max-height:1px;")
        outer.addWidget(sep)

        # Scroll alanı — tüm bölümler bunun içinde
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setAttribute(Qt.WA_StyledBackground, True)
        scroll.setStyleSheet(
            "QScrollArea{background:#ffffff; border:none;}"
            "QScrollArea > QWidget > QWidget{background:#ffffff;}"
        )
        self._scroll_host = QWidget()
        self._scroll_host.setAttribute(Qt.WA_StyledBackground, True)
        self._scroll_host.setStyleSheet("background:#ffffff;")
        self._host_lay = QVBoxLayout(self._scroll_host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        self._host_lay.setSpacing(0)
        scroll.setWidget(self._scroll_host)
        outer.addWidget(scroll, 1)

        # 1) Ay özeti
        self._stat_section = self._build_stat_section()
        self._host_lay.addWidget(self._stat_section)

        # 2) Seçim alanı (dinamik — refresh_selection ile yeniden çizilir)
        self._sel_section = QWidget()
        self._sel_section.setStyleSheet("background:transparent;")
        self._sel_lay = QVBoxLayout(self._sel_section)
        self._sel_lay.setContentsMargins(20, 14, 20, 14)
        self._sel_lay.setSpacing(8)
        self._host_lay.addWidget(self._sel_section)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#e2e8f0; max-height:1px;")
        self._host_lay.addWidget(sep2)

        # 3) Bileşen bazında planlanan adet
        self._comp_section = QWidget()
        self._comp_section.setStyleSheet("background:transparent;")
        self._comp_lay = QVBoxLayout(self._comp_section)
        self._comp_lay.setContentsMargins(20, 14, 20, 14)
        self._comp_lay.setSpacing(6)
        self._host_lay.addWidget(self._comp_section)
        self._host_lay.addStretch()

        # Başlangıç durumu: hiçbir seçim yok → tüm ay
        self.refresh_selection([])

    # ── 1) Ay özeti şeridi ───────────────────────────────────────────────
    def _build_stat_section(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(20, 14, 20, 14)
        vl.setSpacing(8)

        sec_title = QLabel("Ay özeti")
        sec_title.setStyleSheet(
            "font-size:10.5px; font-weight:900; color:#475569;"
            "letter-spacing:.4px; background:transparent;"
        )
        vl.addWidget(sec_title)

        strip = QHBoxLayout()
        strip.setSpacing(6)
        c = self._counts()
        items = [
            ("geciken", "Geciken", c.get("geciken", 0)),
            ("kritik", "60 gün", c.get("kritik", 0)),
            ("tamamlandi", "Teslim", c.get("tamamlandi", 0)),
            ("belirsiz", "Belirsiz", c.get("belirsiz", 0)),
        ]
        for key, label, num in items:
            chip = QFrame()
            chip.setAttribute(Qt.WA_StyledBackground, True)
            chip.setStyleSheet(
                f"QFrame{{background:{_BG[key]}; border-radius:9px;}}"
            )
            cl = QVBoxLayout(chip)
            cl.setContentsMargins(4, 7, 4, 7)
            cl.setSpacing(1)
            num_lbl = QLabel(str(num))
            num_lbl.setAlignment(Qt.AlignCenter)
            num_lbl.setStyleSheet(
                f"font-size:16px; font-weight:900; color:{_FG[key]}; background:transparent;"
            )
            txt_lbl = QLabel(label)
            txt_lbl.setAlignment(Qt.AlignCenter)
            txt_lbl.setStyleSheet(
                f"font-size:8.5px; font-weight:800; color:{_FG[key]}; background:transparent;"
            )
            cl.addWidget(num_lbl)
            cl.addWidget(txt_lbl)
            strip.addWidget(chip, 1)
        vl.addLayout(strip)
        return w

    def _counts(self) -> Dict[str, int]:
        c = {"geciken": 0, "kritik": 0, "tamamlandi": 0, "belirsiz": 0}
        for e in self._events:
            if e.get("_cls") in c:
                c[e["_cls"]] += 1
        for e in self._unknown_day_events:
            c["belirsiz"] += 1
        return c

    # ── Yardımcı: event listesinden delivery_id'leri ve bileşen toplamını çıkar ──
    def _components_for_events(self, evs: List[dict]) -> dict:
        """Verilen event listesindeki Teslimat tipli kayıtların delivery_id'lerini
        toplar, volume_rows üzerinden bileşen bazında toplamı + kayıt sayısını
        hesaplar. Sözleşme/Sistem tipi event'lerin delivery_id'si olmadığından
        otomatik olarak dışarıda kalır (panel artık yalnızca teslimat/kabul
        kayıtlarını gösteriyor)."""
        delivery_ids = {
            e.get("delivery_id") for e in evs
            if e.get("delivery_id") is not None
        }
        grouped = _volume_rows_for_deliveries(self._volume_rows, delivery_ids)
        by_comp: Dict[str, float] = {}
        for did, comps in grouped.items():
            for c in comps:
                by_comp[c["component"]] = by_comp.get(c["component"], 0.0) + c["planned_qty"]
        return {
            "by_component": by_comp,
            "grouped": grouped,
            "delivery_count": len(grouped),
            "total_qty": sum(by_comp.values()),
        }

    # ── Dış API: seçim değiştiğinde çağrılır ────────────────────────────
    def refresh_selection(self, sel_days: list):
        """
        sel_days:
          []                      → hiçbir seçim yok, tüm ay
          [int, int, ...]         → bir veya birden fazla gün (Ctrl+tık)
          ["unknown:<index>"]     → tek bir TBD kapsülü (bkz. not aşağıda)

        Not: TBD kapsülü seçimi tek elemanlı ve "unknown:" önekiyle taşınır
        (örn. "unknown:2" = unknown_day_events listesindeki 3. kayıt).
        Bu, normal gün seçimiyle (sade int) karışmasını engeller; ikisi
        zaten _MonthDetailDialog tarafında birbirini temizleyecek şekilde
        yönetilir (bkz. _on_day_click / _on_unknown_pill_click).
        """
        self._clear_layout(self._sel_lay)
        self._clear_layout(self._comp_lay)

        only_unknown = (
            len(sel_days) == 1
            and isinstance(sel_days[0], str)
            and sel_days[0].startswith("unknown:")
        )
        only_fu = (
            len(sel_days) == 1
            and isinstance(sel_days[0], str)
            and sel_days[0].startswith("fully_unknown:")
        )

        if not sel_days:
            evs = self._all_for_components()
            self._render_empty_selection_default(evs)
        elif only_fu:
            idx = int(sel_days[0].split(":", 1)[1])
            if 0 <= idx < len(self._fully_unknown_events):
                ev = self._fully_unknown_events[idx]
                self._render_single_record_selection(ev)
                evs = [ev]
            else:
                evs = []
                self._render_empty_day()
        elif only_unknown:
            idx = int(sel_days[0].split(":", 1)[1])
            if 0 <= idx < len(self._unknown_day_events):
                ev = self._unknown_day_events[idx]
                self._render_single_record_selection(ev)
                evs = [ev]
            else:
                evs = []
                self._render_empty_day()
        else:
            day_evs: List[dict] = []
            for d in sel_days:
                if isinstance(d, int):
                    day_evs.extend(e for e in self._events if e.get("_eff_date") and e["_eff_date"].day == d)
            evs = day_evs
            self._render_day_selection(sel_days, day_evs)

        self._render_components(evs)

    def _clear_layout(self, lay: QVBoxLayout):
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── 2a) Hiçbir şey seçili değil → tüm ay ────────────────────────────
    def _render_empty_selection_default(self, evs: List[dict]):
        title = QLabel(f"{TR_MONTHS[self._month - 1]} {self._year} · tüm ay")
        title.setStyleSheet(
            "font-size:11px; font-weight:900; color:#475569; background:transparent;"
        )
        self._sel_lay.addWidget(title)

        info = QLabel(
            "Bir güne tıklayarak o günün kayıtlarını, ya da bir "
            "\"Gün belirsiz\" kapsülüne tıklayarak o kaydı görüntüleyebilirsiniz."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-size:11px; color:#94a3b8; font-weight:700; background:transparent;"
        )
        self._sel_lay.addWidget(info)

    def _all_for_components(self) -> List[dict]:
        """Bileşen toplamı hesabı için tüm event listesi:
        exact + month_unknown_day + fully_unknown + year_only."""
        return self._events + self._unknown_day_events + self._fully_unknown_events

    # ── 2b) Boş gün ──────────────────────────────────────────────────────
    def _render_empty_day(self, day_label: str = ""):
        title = QLabel(day_label or "Seçili gün")
        title.setStyleSheet(
            "font-size:11px; font-weight:900; color:#475569; background:transparent;"
        )
        self._sel_lay.addWidget(title)
        empty = QLabel("Bu günde kayıt yok.")
        empty.setStyleSheet(
            "border:1px dashed #dbe6f0; border-radius:10px; padding:16px;"
            "color:#94a3b8; font-size:11.5px; font-weight:700; background:transparent;"
        )
        empty.setAlignment(Qt.AlignCenter)
        self._sel_lay.addWidget(empty)

    # ── 2c) Gün seçimi (tek veya çoklu) ─────────────────────────────────
    def _render_day_selection(self, sel_days: list, evs: List[dict]):
        days_sorted = sorted(d for d in sel_days if isinstance(d, int))
        if len(days_sorted) == 1:
            day_label = f"{days_sorted[0]} {TR_MONTHS[self._month - 1]} · {len(evs)} kayıt"
        else:
            gun_txt = ", ".join(str(d) for d in days_sorted)
            day_label = f"{gun_txt} {TR_MONTHS[self._month - 1]} · {len(evs)} kayıt"

        title = QLabel(day_label)
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:11px; font-weight:900; color:#475569; background:transparent;"
        )
        self._sel_lay.addWidget(title)

        if not evs:
            self._render_empty_day(
                f"{days_sorted[0]} {TR_MONTHS[self._month - 1]}" if len(days_sorted) == 1 else day_label
            )
            return

        delivery_ids_seen = set()
        for ev in evs:
            did = ev.get("delivery_id")
            if did is not None and did in delivery_ids_seen:
                continue  # aynı kayıt iki kez listelenmesin (çoklu gün seçiminde olabilir)
            if did is not None:
                delivery_ids_seen.add(did)
            comps = []
            if did is not None:
                grouped = _volume_rows_for_deliveries(self._volume_rows, {did})
                comps = grouped.get(did, [])
            card = _RecordAccordionCard(
                ev, comps, open_handler=self._on_open_record
            )
            self._sel_lay.addWidget(card)

    # ── 2d) Tek TBD kaydı seçimi ─────────────────────────────────────────
    def _render_single_record_selection(self, ev: dict):
        title = QLabel(f"{ev.get('title') or ev.get('no')} · Gün belirsiz")
        title.setWordWrap(True)
        title.setStyleSheet(
            "font-size:11px; font-weight:900; color:#6d28d9; background:transparent;"
        )
        self._sel_lay.addWidget(title)

        did = ev.get("delivery_id")
        comps = []
        if did is not None:
            grouped = _volume_rows_for_deliveries(self._volume_rows, {did})
            comps = grouped.get(did, [])
        card = _RecordAccordionCard(ev, comps, open_handler=self._on_open_record)
        self._sel_lay.addWidget(card)

    def _on_open_record(self, ev: dict):
        if self._detail_handler:
            self._detail_handler(ev)

    # ── 3) Bileşen bazında planlanan adet · toplam ──────────────────────
    def _render_components(self, evs: List[dict]):
        title = QLabel("Bileşen bazında planlanan adet · toplam")
        title.setStyleSheet(
            "font-size:10.5px; font-weight:900; color:#475569;"
            "letter-spacing:.3px; background:transparent;"
        )
        self._comp_lay.addWidget(title)

        agg = self._components_for_events(evs)
        by_comp = agg["by_component"]

        if not by_comp:
            empty = QLabel("Bu seçimde planlanan teslimat bileşeni bulunamıyor.")
            empty.setWordWrap(True)
            empty.setStyleSheet(
                "border-radius:9px; background:#eff6ff; color:#1d4ed8;"
                "font-size:11px; font-weight:700; padding:11px;"
            )
            self._comp_lay.addWidget(empty)
        else:
            for comp_name, qty in sorted(by_comp.items(), key=lambda x: -x[1]):
                row = QFrame()
                row.setAttribute(Qt.WA_StyledBackground, True)
                row.setStyleSheet("background:transparent;")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 5, 4, 5)
                name_lbl = QLabel(comp_name)
                name_lbl.setStyleSheet(
                    "font-size:12px; font-weight:800; color:#1e293b; background:transparent;"
                )
                qty_lbl = QLabel(
                    f'<span style="font-size:14.5px;font-weight:900;color:#1e293b;">'
                    f'{_format_qty(qty)}</span>'
                    f'<span style="font-size:10.5px;color:#6b7280;"> adet</span>'
                )
                qty_lbl.setTextFormat(Qt.RichText)
                rl.addWidget(name_lbl, 1)
                rl.addWidget(qty_lbl)
                self._comp_lay.addWidget(row)



# ─────────────────────────────────────────────────────────────────────────────
# Tarihi Belirsiz Kayıtlar Paneli (year_only + fully_unknown)
# ─────────────────────────────────────────────────────────────────────────────
class _UnknownDatesDialog(QWidget):
    """
    'YYYY-TBD-TBD' (sadece yıl belli) ve 'TBD' (hiçbir şey belli değil)
    kayıtları için ayrı özet panel. Bu kayıtlar hiçbir ay kartına
    yerleştirilemez; üst bardaki 'Tarihi belirsiz' pill'inden açılır.
    """
    closed = Signal()

    def __init__(self, year_only_events: List[dict], fully_unknown_events: List[dict],
                 year: int, detail_handler: Optional[Callable], parent=None):
        super().__init__(parent)
        self._year_only = year_only_events
        self._fully_unknown = fully_unknown_events
        self._year = year
        self._detail_handler = detail_handler
        self.setGeometry(parent.rect() if parent else self.geometry())
        self.setStyleSheet(_COMBINED_STYLE)
        self._build()
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim
        self.show()
        self.raise_()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def _position_card(self):
        if self.parent():
            pr = self.parent().rect()
            w = min(720, int(pr.width() * 0.6))
            h = min(640, int(pr.height() * 0.8))
            x = (pr.width() - w) // 2
            y = (pr.height() - h) // 2
        else:
            w, h, x, y = 720, 640, 80, 80
        if hasattr(self, "_card"):
            self._card.setGeometry(x, y, w, h)
        if hasattr(self, "_backdrop"):
            self._backdrop.setGeometry(self.rect())

    def close(self):
        self.closed.emit()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(60)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._close_anim = anim

    def _build(self):
        backdrop = QWidget(self)
        backdrop.setStyleSheet("QWidget{background:rgba(10,16,26,0.60);}")
        backdrop.setGeometry(self.rect())
        backdrop.mousePressEvent = lambda e: self.close()
        self._backdrop = backdrop

        if self.parent():
            pr = self.parent().rect()
            w = min(720, int(pr.width() * 0.6))
            h = min(640, int(pr.height() * 0.8))
            x = (pr.width() - w) // 2
            y = (pr.height() - h) // 2
        else:
            w, h, x, y = 720, 640, 80, 80

        card = QWidget(self)
        card.setObjectName("overlayCard")
        card.setStyleSheet("QWidget#overlayCard{background:#ffffff; border-radius:18px;}")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setGeometry(x, y, w, h)
        self._card = card

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet(
            "QWidget{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e293b, stop:1 #0f172a); border-top-left-radius:18px;"
            "border-top-right-radius:18px;}"
        )
        hdr.setFixedHeight(64)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 16, 0)
        title = QLabel("Tarihi belirsiz kayıtlar")
        title.setStyleSheet("color:#ffffff; font-size:18px; font-weight:900; background:transparent;")
        hl.addWidget(title, 1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.12); color:#ffffff;"
            "border:none; border-radius:16px; font-size:13px; font-weight:700;}"
            "QPushButton:hover{background:rgba(255,255,255,0.22);}"
        )
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        lay.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("plainScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setStyleSheet("QWidget{background:#ffffff;}")
        vlay = QVBoxLayout(host)
        vlay.setContentsMargins(18, 14, 18, 18)
        vlay.setSpacing(8)

        total = len(self._year_only) + len(self._fully_unknown)
        sub = QLabel(f"{total} kayıt · tarih netleşince ilgili sözleşme/sistem kaydından güncellenmeli")
        sub.setStyleSheet("color:#64748b; font-size:11.5px; font-weight:700; background:transparent;")
        vlay.addWidget(sub)

        if self._year_only:
            vlay.addWidget(self._group_title(f"{self._year} · ay ve gün belirsiz ({len(self._year_only)})"))
            for ev in sorted(self._year_only, key=lambda e: e.get("title", "")):
                vlay.addWidget(self._rec_card(ev))

        if self._fully_unknown:
            vlay.addWidget(self._group_title(f"Tamamen belirsiz, yıldan bağımsız ({len(self._fully_unknown)})"))
            for ev in sorted(self._fully_unknown, key=lambda e: e.get("title", "")):
                vlay.addWidget(self._rec_card(ev))

        if not total:
            empty = QLabel("Bu kategoride kayıt yok.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:#94a3b8; font-size:12px; background:transparent; padding:20px;")
            vlay.addWidget(empty)

        vlay.addStretch()
        scroll.setWidget(host)
        lay.addWidget(scroll, 1)

    def _group_title(self, text: str) -> QLabel:
        l = QLabel(text.upper())
        l.setStyleSheet(
            "color:#94a3b8; font-size:10.5px; font-weight:900; letter-spacing:.08em;"
            "background:transparent; margin-top:10px;"
        )
        return l

    def _rec_card(self, ev: dict) -> QFrame:
        card = QFrame()
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setObjectName("recCard")
        card.setStyleSheet(
            f"QFrame#recCard{{background:#ffffff; border:1px solid #e2e8f0;"
            f"border-left:4px solid {_COLOR['belirsiz']}; border-radius:8px;}}"
        )
        card.setCursor(Qt.PointingHandCursor)
        card.mousePressEvent = lambda e, ev_=ev: self._on_click(ev_)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(5)

        title = QLabel(str(ev.get("title") or ev.get("no") or ""))
        title.setWordWrap(True)
        title.setStyleSheet(
            "background:transparent; font-size:12px; font-weight:800; color:#17202d; border:none;"
        )
        lay.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        type_l = QLabel(str(ev.get("type") or ""))
        type_l.setStyleSheet(
            "background:#f1f5f9; color:#64748b; border-radius:999px;"
            "padding:2px 8px; font-size:9.5px; font-weight:800; border:none;"
        )
        meta.addWidget(type_l)
        date_l = QLabel(_fmt_flexible(ev.get("_eff_raw", "")))
        date_l.setStyleSheet(
            f"background:transparent; color:{_FG['belirsiz']};"
            "font-size:10.5px; font-weight:700; border:none;"
        )
        meta.addWidget(date_l)
        meta.addStretch()
        lay.addLayout(meta)
        return card

    def _on_click(self, ev: dict):
        if self._detail_handler and self._detail_handler(ev):
            self.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ay Detay Dialog
# ─────────────────────────────────────────────────────────────────────────────
class _MonthDetailDialog(QWidget):
    """
    Yıl takviminin üzerinde overlay olarak açılan ay detay paneli.
    Arka plan blur efekti için ana pencereye overlay layer olarak eklenir.
    """
    closed = Signal(bool)  # True: dialog açıkken bir kayıt düzenlendi (veri değişti)

    def __init__(self, events: List[dict], year: int, month: int,
                 detail_handler: Optional[Callable], parent=None,
                 unknown_day_events: Optional[List[dict]] = None,
                 fully_unknown_events: Optional[List[dict]] = None,
                 volume_rows: Optional[list] = None,
                 platform_filter: str = ""):
        super().__init__(parent)
        self._events = events
        self._unknown_day_events = unknown_day_events or []
        # fully_unknown (TBD) + year_only (YYYY-TBD-TBD) teslimatlar —
        # takvimde gün hücresine girmezler ama bileşen toplamı için
        # _UnifiedSidePanel'e geçirilirler.
        self._fully_unknown_events = fully_unknown_events or []
        self._volume_rows = volume_rows or []
        self._platform_filter = platform_filter
        self._year = year
        self._month = month
        self._month1 = month + 1
        self._detail_handler = detail_handler
        # Performans: "Yıla dön" ile kapatıldığında, dialog açıkken hiçbir
        # kayıt düzenlenmediyse (veri değişmediyse) çağıran taraf gereksiz
        # yere tüm yıl grid'ini (12 ay kartı, ~370 mini hücre widget'ı)
        # yeniden inşa etmesin diye bu flag closed sinyaliyle taşınır.
        self._data_changed = False
        self._today = date.today()
        # Multi-select: set of (int günler | "unknown")
        self._sel_days: List = []
        # Performans: gün hücrelerine event dağıtımı _render_cal her
        # çağrıldığında tek tek taranmasın diye bir kez gruplanıp cache'lenir.
        self._events_by_day: Dict[int, List[dict]] = {}
        for e in self._events:
            d = e.get("_eff_date")
            if d is not None:
                self._events_by_day.setdefault(d.day, []).append(e)
        # Hücre widget referansları: tıklamada tüm grid yerine sadece
        # etkilenen hücreler güncellensin diye saklanır.
        self._day_cells: Dict[object, QFrame] = {}
        # Tam ebeveyn üzerinde yay
        self.setGeometry(parent.rect() if parent else self.geometry())
        self.setStyleSheet(_COMBINED_STYLE)
        self._build_overlay()
        # Fade-in
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim
        self.show()
        self.raise_()

    def resizeEvent(self, event):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def _wrapped_detail_handler(self, ev: dict) -> bool:
        """_detail_handler'ı sarmalar: True dönerse (kayıt gerçekten
        düzenlendiyse) _data_changed işaretlenir, böylece close() bunu
        closed sinyaliyle taşıyıp gereksiz _render_year() çağrısını
        önleyebilir (bkz. _on_detail_closed)."""
        if not self._detail_handler:
            return False
        result = self._detail_handler(ev)
        if result:
            self._data_changed = True
        return bool(result)

    def close(self):
        # Performans: closed sinyali eskiden burada senkron emit ediliyordu,
        # bu da _on_detail_closed -> _render_year() (12 ay kartı + ~370
        # mini hücre widget'ının sıfırdan yeniden inşası) işlemini fade-out
        # animasyonuyla AYNI ANDA UI thread'inde çalıştırıyordu — "Yıla dön"
        # tıklamasının donuk/yavaş hissetmesinin asıl nedeni buydu.
        # Artık closed sinyali animasyon bittikten sonra emit edilir; ayrıca
        # _on_detail_closed artık veri değişmediyse _render_year() çağırmaz
        # (bkz. _on_detail_closed).
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(60)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        anim.finished.connect(lambda: self.closed.emit(self._data_changed))
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._close_anim = anim

    def _position_card(self):
        if self.parent():
            pr = self.parent().rect()
            w = max(1280, int(pr.width() * 0.94))
            h = int(pr.height() * 0.90)
            x = (pr.width() - w) // 2
            y = (pr.height() - h) // 2
        else:
            w, h, x, y = 1440, 820, 20, 20
        self._card.setGeometry(x, y, w, h)
        if hasattr(self, '_backdrop'):
            self._backdrop.setGeometry(self.rect())

    def _build_overlay(self):
        """Backdrop + merkezi içerik."""
        # Backdrop — tıklanınca kapat
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("QWidget{background:rgba(10,16,26,0.38);}")
        self._backdrop.setGeometry(self.rect())
        self._backdrop.lower()
        self._backdrop.mousePressEvent = lambda e: self.close()

        # Ana kart widget — backdrop üzerinde
        self._card = QWidget(self)
        self._card.setObjectName("overlayCard")
        self._card.setStyleSheet(
            "QWidget#overlayCard{background:#f0f4fc; border-radius:16px;}"
        )
        # border-radius görünmesi için
        self._card.setAttribute(Qt.WA_StyledBackground, True)
        self._position_card()

        # Kart içi layout: takvim (geniş) + birleşik sağ panel
        card_lay = QHBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # ── SOL/ORTA: takvim alanı (artık tek panel kalktığı için genişledi) ──
        cal_side = QWidget(self._card)
        cal_side.setObjectName("calLeft")
        cal_side.setStyleSheet(
            "QWidget#calLeft{background:#ffffff;"
            "border-top-left-radius:16px;"
            "border-bottom-left-radius:16px;}"
        )
        right_lay = QVBoxLayout(cal_side)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        card_lay.addWidget(cal_side, 1)

        # ── Topbar ──────────────────────────────────────────────────────
        topbar = QWidget(cal_side)
        topbar.setStyleSheet(
            "QWidget{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e293b,stop:1 #0f172a);"
            "border-top-left-radius:16px;"
            "}"
        )
        topbar.setFixedHeight(_DETAIL_TOPBAR_HEIGHT)
        tb_lay = QHBoxLayout(topbar)
        tb_lay.setContentsMargins(22, 0, 22, 0)
        tb_lay.setSpacing(14)
        back_btn = QPushButton("← Yıla dön")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.12); color:#ffffff;"
            "border:1px solid rgba(255,255,255,0.25); border-radius:8px;"
            "font-size:12px; font-weight:600; padding:6px 14px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.22);}"
        )
        back_btn.clicked.connect(self.close)
        tb_lay.addWidget(back_btn)
        month_title = QLabel(f"{TR_MONTHS[self._month]} {self._year}")
        month_title.setStyleSheet(
            "font-size:22px; font-weight:900; color:#ffffff; background:transparent;"
        )
        tb_lay.addWidget(month_title)
        tb_lay.addStretch()
        hint_lbl = QLabel("Ctrl + tık → birden fazla gün seç")
        hint_lbl.setStyleSheet(
            "color:rgba(159,178,204,0.95); font-size:11.5px; font-weight:700; background:transparent;"
        )
        tb_lay.addWidget(hint_lbl)
        right_lay.addWidget(topbar)

        # ── Gün başlıkları ──────────────────────────────────────────────
        dh = QWidget(cal_side)
        dh.setObjectName("dayHeaderBg")
        dh.setStyleSheet("QWidget#dayHeaderBg{background:#1e293b;}")
        dh.setFixedHeight(_DAY_HEADER_HEIGHT)
        dh_lay = QGridLayout(dh)
        dh_lay.setContentsMargins(16, 6, 16, 6)
        dh_lay.setHorizontalSpacing(6)
        dh_lay.setVerticalSpacing(0)
        for i, dn in enumerate(["PZT","SAL","ÇAR","PER","CUM","CMT","PAZ"]):
            l = QLabel(dn)
            l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet(
                "background:transparent; color:rgba(148,163,184,0.9);"
                "font-size:11px; font-weight:900; letter-spacing:.6px;"
            )
            dh_lay.addWidget(l, 0, i)
        right_lay.addWidget(dh)

        # ── Takvim grid ─────────────────────────────────────────────────
        cal_scroll = QScrollArea()
        cal_scroll.setWidgetResizable(True)
        cal_scroll.setObjectName("plainScroll")
        cal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cal_host = QWidget()
        self._cal_host.setObjectName("calHost")
        self._cal_grid = QGridLayout(self._cal_host)
        self._cal_grid.setContentsMargins(16, 14, 16, 16)
        self._cal_grid.setHorizontalSpacing(8)
        self._cal_grid.setVerticalSpacing(10)
        cal_scroll.setWidget(self._cal_host)

        # Ctrl+tık ipucu (alt bant)
        hint_bar = QWidget(cal_side)
        hint_bar.setStyleSheet("background:#eff6ff; border-top:1px solid #bfdbfe;")
        hint_bar.setFixedHeight(32)
        hbl = QHBoxLayout(hint_bar)
        hbl.setContentsMargins(16, 0, 16, 0)
        hint_txt = QLabel("⌘ / Ctrl + tık ile birden fazla gün seçebilirsiniz. "
                          "Normal tık tek günü seçer; seçili günlerin bileşen adetleri sağda toplanır.")
        hint_txt.setStyleSheet(
            "font-size:11px; color:#1d4ed8; background:transparent;"
        )
        hbl.addWidget(hint_txt, 1)

        right_lay.addWidget(cal_scroll, 1)
        right_lay.addWidget(hint_bar)

        # ── SAĞ: Birleşik panel (Ay özeti + Seçim + Bileşen + Toplam) ─────
        self._unified_panel = _UnifiedSidePanel(
            events=self._events,
            unknown_day_events=self._unknown_day_events,
            fully_unknown_events=self._fully_unknown_events,
            volume_rows=self._volume_rows,
            year=self._year,
            month=self._month1,
            detail_handler=self._wrapped_detail_handler,
            parent=self._card,
        )
        card_lay.addWidget(self._unified_panel)

        self._render_cal()

    def _build(self, container=None):
        """Compat — artık _build_overlay kullanıyoruz."""
        pass


    # ── Veri ──────────────────────────────────────────────────────────────
    def _for_day(self, day: int) -> List[dict]:
        return self._events_by_day.get(day, [])

    def _counts(self) -> Dict[str, int]:
        c = {"geciken": 0, "kritik": 0, "tamamlandi": 0, "belirsiz": 0}
        for e in self._events:
            if e["_cls"] in c:
                c[e["_cls"]] += 1
        for e in self._unknown_day_events:
            c["belirsiz"] += 1
        return c

    # ── Render ────────────────────────────────────────────────────────────
    def _render_all(self):
        self._render_cal()

    def _render_cal(self):
        """Tam grid kurulumu — sadece ay değişiminde / ilk açılışta çağrılmalı.
        Sadece seçim değişimi için _update_selection_styles kullanılır."""
        while self._cal_grid.count():
            item = self._cal_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._day_cells.clear()

        days_in_month = calendar.monthrange(self._year, self._month1)[1]
        first_col = _first_col(self._year, self._month1)
        idx = 0

        for _ in range(first_col):
            b = QFrame()
            b.setAttribute(Qt.WA_StyledBackground, True)
            b.setObjectName("dayCellEmpty")
            b.setMinimumHeight(90)
            self._cal_grid.addWidget(b, idx // 7, idx % 7)
            idx += 1

        # ── "Gün belirsiz" bandı — varsa, ızgaranın hemen başında tam
        # genişlikte. month_unknown_day formatındaki kayıtlar bir güne
        # ait olmadığı için gün hücrelerine karışmaz, ayrı bir satırda
        # toplanır. ──────────────────────────────────────────────────
        row_after_band = 0
        if self._unknown_day_events:
            band = self._build_unknown_band()
            self._cal_grid.addWidget(band, 0, 0, 1, 7)
            row_after_band += 1

        # TBD / YYYY-TBD-TBD tarihli teslimatlar için ikinci bant
        if self._fully_unknown_events:
            fu_band = self._build_fully_unknown_band()
            self._cal_grid.addWidget(fu_band, row_after_band, 0, 1, 7)
            row_after_band += 1

        if row_after_band:
            # Gün hücrelerini bant(lar) kadar aşağı kaydır
            idx = first_col + row_after_band * 7

        for day in range(1, days_in_month + 1):
            is_today = (
                self._today.year == self._year
                and self._today.month == self._month1
                and self._today.day == day
            )
            selected = day in self._sel_days
            day_evs = self._for_day(day)
            cell = self._build_cell(day, day_evs, is_today, selected)
            self._cal_grid.addWidget(cell, idx // 7, idx % 7)
            self._day_cells[day] = cell
            idx += 1

        while idx % 7 != 0:
            b = QFrame()
            b.setAttribute(Qt.WA_StyledBackground, True)
            b.setObjectName("dayCellEmpty")
            b.setMinimumHeight(90)
            self._cal_grid.addWidget(b, idx // 7, idx % 7)
            idx += 1

        for c in range(7):
            self._cal_grid.setColumnStretch(c, 1)

    def _build_unknown_band(self) -> QFrame:
        """'YYYY-MM-TBD' kayıtları için, gün ızgarasının üstünde tam genişlikte
        bant. İçinde HER kayıt için ayrı tıklanabilir kapsül var — tek satır
        özet değil, her teslimat/kabul kaydı kendi kapsülünde listelenir.
        Bir kapsüle tıklamak o tek kaydı seçer (bkz. _on_unknown_pill_click);
        bu seçim normal gün seçimiyle aynı anda var olamaz."""
        band = QFrame()
        band.setObjectName("unknownDayBand")
        band.setStyleSheet(
            f"QFrame#unknownDayBand{{border:1.5px dashed {_COLOR['belirsiz']};"
            f"background:{_BG['belirsiz']}; border-radius:12px;}}"
        )

        outer = QVBoxLayout(band)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{_COLOR['belirsiz']}; font-size:9px; background:transparent; border:none;"
        )
        head.addWidget(dot)
        lbl = QLabel(f"Gün belirsiz kayıtlar · {len(self._unknown_day_events)}")
        lbl.setStyleSheet(
            f"background:transparent; color:{_FG['belirsiz']};"
            "font-size:12.5px; font-weight:900; border:none;"
        )
        head.addWidget(lbl)
        info = QLabel(f"{TR_MONTHS[self._month]} {self._year} içinde, gün henüz bilinmiyor")
        info.setStyleSheet(
            "background:transparent; color:#7c6fb0; font-size:10.5px;"
            "font-weight:700; border:none;"
        )
        head.addWidget(info)
        head.addStretch()
        outer.addLayout(head)

        pill_row = QHBoxLayout()
        pill_row.setSpacing(8)
        self._unknown_pills: Dict[int, QWidget] = {}
        for idx, ev in enumerate(self._unknown_day_events):
            pill = self._build_unknown_pill(idx, ev)
            pill_row.addWidget(pill)
            self._unknown_pills[idx] = pill
        pill_row.addStretch()
        outer.addLayout(pill_row)

        return band

    def _build_unknown_pill(self, idx: int, ev: dict) -> QWidget:
        sel_key = f"unknown:{idx}"
        is_selected = self._sel_days == [sel_key]

        pill = QFrame()
        pill.setCursor(Qt.PointingHandCursor)
        pill.setFixedHeight(40)
        self._style_unknown_pill(pill, is_selected)

        lay = QHBoxLayout(pill)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)
        title = str(ev.get("title") or ev.get("no") or "")
        name_lbl = QLabel(_elide(title, 22))
        name_lbl.setStyleSheet(
            f"font-size:12px; font-weight:800; background:transparent;"
            f"color:{'#ffffff' if is_selected else '#1e293b'}; border:none;"
        )
        lay.addWidget(name_lbl)
        kind_lbl = QLabel(str(ev.get("type") or ""))
        kind_lbl.setStyleSheet(
            f"font-size:9.5px; font-weight:700; background:transparent;"
            f"color:{'rgba(255,255,255,0.75)' if is_selected else '#94a3b8'}; border:none;"
        )
        lay.addWidget(kind_lbl)

        def _press(e, i=idx):
            if e.button() == Qt.LeftButton:
                self._on_unknown_pill_click(i)
        pill.mousePressEvent = _press
        return pill

    def _style_unknown_pill(self, pill: QFrame, selected: bool):
        if selected:
            pill.setStyleSheet(
                "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #a78bfa, stop:1 #6d28d9); border:1.5px solid transparent;"
                "border-radius:10px;}"
            )
        else:
            pill.setStyleSheet(
                "QFrame{background:#ffffff; border:1.5px solid rgba(139,124,213,0.35);"
                "border-radius:10px;}"
                "QFrame:hover{border-color:#8b7cd8; background:#faf8ff;}"
            )

    def _build_fully_unknown_band(self) -> QFrame:
        """TBD (tamamen belirsiz) ve YYYY-TBD-TBD tarihli teslimatlar için bant.
        Her kayıt ayrı kapsül olarak listelenir; tıklanınca sağ panelde
        'fully_unknown:<idx>' seçimi tetiklenir."""
        band = QFrame()
        band.setObjectName("fullyUnknownBand")
        band.setStyleSheet(
            f"QFrame#fullyUnknownBand{{border:1.5px dashed {_COLOR['belirsiz']};"
            f"background:#fdf8ff; border-radius:12px;}}"
        )

        outer = QVBoxLayout(band)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{_COLOR['belirsiz']}; font-size:9px; background:transparent; border:none;"
        )
        head.addWidget(dot)
        lbl = QLabel(f"Tarihi belirsiz · {len(self._fully_unknown_events)}")
        lbl.setStyleSheet(
            f"background:transparent; color:{_FG['belirsiz']};"
            "font-size:12.5px; font-weight:900; border:none;"
        )
        head.addWidget(lbl)
        info = QLabel("TBD veya yıl/ay/gün belirsiz tarihli teslimatlar")
        info.setStyleSheet(
            "background:transparent; color:#7c6fb0; font-size:10.5px; font-weight:700; border:none;"
        )
        head.addWidget(info)
        head.addStretch()
        outer.addLayout(head)

        pill_row = QHBoxLayout()
        pill_row.setSpacing(8)
        if not hasattr(self, "_fu_pills"):
            self._fu_pills: Dict[int, QWidget] = {}
        else:
            self._fu_pills.clear()

        for idx, ev in enumerate(self._fully_unknown_events):
            pill = self._build_fu_pill(idx, ev)
            pill_row.addWidget(pill)
            self._fu_pills[idx] = pill
        pill_row.addStretch()
        outer.addLayout(pill_row)

        return band

    def _build_fu_pill(self, idx: int, ev: dict) -> QWidget:
        sel_key = f"fully_unknown:{idx}"
        is_selected = self._sel_days == [sel_key]

        pill = QFrame()
        pill.setCursor(Qt.PointingHandCursor)
        pill.setFixedHeight(40)
        self._style_fu_pill(pill, is_selected)

        lay = QHBoxLayout(pill)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)
        title = str(ev.get("title") or ev.get("no") or "")
        name_lbl = QLabel(_elide(title, 22))
        name_lbl.setStyleSheet(
            f"font-size:12px; font-weight:800; background:transparent;"
            f"color:{'#ffffff' if is_selected else '#1e293b'}; border:none;"
        )
        if len(title) > 22:
            name_lbl.setToolTip(title)
        lay.addWidget(name_lbl)
        raw_lbl = QLabel(str(ev.get("_eff_raw") or "TBD"))
        raw_lbl.setStyleSheet(
            f"font-size:9.5px; font-weight:700; background:transparent;"
            f"color:{'rgba(255,255,255,0.75)' if is_selected else '#94a3b8'}; border:none;"
        )
        lay.addWidget(raw_lbl)

        def _press(e, i=idx):
            if e.button() == Qt.LeftButton:
                self._on_fu_pill_click(i)
        pill.mousePressEvent = _press
        return pill

    def _style_fu_pill(self, pill: QFrame, selected: bool):
        if selected:
            pill.setStyleSheet(
                "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #a78bfa,stop:1 #6d28d9); border:1.5px solid transparent;"
                "border-radius:10px;}"
            )
        else:
            pill.setStyleSheet(
                "QFrame{background:#ffffff; border:1.5px solid rgba(139,124,213,0.35);"
                "border-radius:10px;}"
                "QFrame:hover{border-color:#8b7cd8; background:#faf8ff;}"
            )

    def _on_fu_pill_click(self, idx: int):
        """TBD/YYYY-TBD-TBD kapsülü seçimi — gün seçimini temizler."""
        sel_key = f"fully_unknown:{idx}"
        if self._sel_days == [sel_key]:
            self._sel_days = []
        else:
            old_days = [d for d in self._sel_days if isinstance(d, int)]
            self._update_cells_style(old_days)
            self._clear_unknown_pill_selection()
            self._sel_days = [sel_key]
        self._refresh_fu_pill_styles()
        self._unified_panel.refresh_selection(self._sel_days)

    def _refresh_fu_pill_styles(self, force_none: bool = False):
        if not hasattr(self, "_fu_pills"):
            return
        active_idx = None
        if not force_none and len(self._sel_days) == 1:
            d = self._sel_days[0]
            if isinstance(d, str) and d.startswith("fully_unknown:"):
                active_idx = int(d.split(":", 1)[1])
        for idx, pill in self._fu_pills.items():
            self._style_fu_pill(pill, idx == active_idx)

    def _build_cell(self, day: int, evs: List[dict],
                    is_today: bool, selected: bool) -> QFrame:
        if is_today:
            obj = "dayCellToday"
        elif selected:
            obj = "dayCellSelected"
        else:
            obj = "dayCellNormal"
        frame = _HoverLiftFrame()
        frame.setObjectName(obj)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setCursor(Qt.PointingHandCursor)

        # Click via event filter trick
        def _press(ev, d=day):
            if ev.button() == Qt.LeftButton:
                ctrl = bool(ev.modifiers() & Qt.ControlModifier)
                self._on_day_click(d, ctrl_held=ctrl)
        frame.mousePressEvent = _press

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(7, 5, 7, 5)
        lay.setSpacing(3)

        # Üst satır: gün no + noktalar + bugün badge
        top = QHBoxLayout()
        top.setSpacing(3)
        num_l = QLabel(str(day))
        num_l.setStyleSheet(
            "background:transparent; font-size:12px; font-weight:900;"
            "color:#64748b; border:none;"
        )
        top.addWidget(num_l)
        top.addStretch()
        for ev in evs[:4]:
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{_COLOR.get(ev['_cls'], '#d9e1ea')};"
                "font-size:7px; background:transparent; border:none;"
            )
            top.addWidget(dot)
        if is_today:
            tb = QLabel("bugün")
            tb.setStyleSheet(
                "background:#e8f0fe; color:#1f5be3; border-radius:6px;"
                "padding:1px 5px; font-size:8px; font-weight:900; border:none;"
            )
            top.addWidget(tb)
        lay.addLayout(top)

        # Chip'ler max 2
        for ev in evs[:2]:
            cls = ev["_cls"]
            txt = _elide(str(ev.get("title") or ev.get("no") or ""), 16)
            chip = QLabel(txt)
            chip.setStyleSheet(
                f"background:{_BG.get(cls, '#f8fafc')};"
                f"color:{_FG.get(cls, '#475569')};"
                f"border:none; border-left:3px solid {_COLOR.get(cls, '#d9e1ea')};"
                "border-radius:4px; padding:2px 5px;"
                "font-size:10px; font-weight:700;"
            )
            chip.setToolTip(str(ev.get("title") or ev.get("no") or ""))
            lay.addWidget(chip)

        extra = len(evs) - 2
        if extra > 0:
            more = QLabel(f"+{extra}")
            more.setStyleSheet(
                "background:#f1f5f9; color:#64748b; border-radius:4px;"
                "padding:1px 5px; font-size:9px; font-weight:700; border:none;"
            )
            lay.addWidget(more)

        lay.addStretch()
        return frame

    # ── Handlers ──────────────────────────────────────────────────────────
    def _on_day_click(self, day, ctrl_held: bool = False):
        """
        Normal tık: sadece o günü seç (toggle).
        Ctrl+tık: birden fazla gün seç veya seçimden kaldır.

        Bir güne tıklamak, varsa seçili TBD kapsülünü otomatik temizler —
        gün seçimi ile TBD kapsül seçimi aynı anda var olamaz (bkz. sınıf
        docstring'i / _UnifiedSidePanel.refresh_selection).

        Performans: tüm ay ızgarasını yeniden çizmek yerine sadece
        etkilenen hücrelerin stili güncellenir.
        """
        had_unknown_selection = any(
            isinstance(d, str) and (d.startswith("unknown:") or d.startswith("fully_unknown:"))
            for d in self._sel_days
        )
        if had_unknown_selection:
            self._clear_unknown_pill_selection()
            self._refresh_fu_pill_styles(force_none=True)
            self._sel_days = []

        if ctrl_held:
            if day in self._sel_days:
                self._sel_days.remove(day)
                changed = [day]
            else:
                self._sel_days.append(day)
                changed = [day]
            self._update_cells_style(changed)
        else:
            old_days = list(self._sel_days)
            if self._sel_days == [day]:
                self._sel_days = []
            else:
                self._sel_days = [day]
            changed = list(set(old_days + self._sel_days))
            self._update_cells_style(changed)

        self._unified_panel.refresh_selection(self._sel_days)

    def _on_unknown_pill_click(self, idx: int):
        """Bir TBD kapsülüne tıklamak o TEK kaydı seçer; her zaman tekildir
        (çoklu TBD seçimi yok) ve varsa mevcut gün seçimini temizler."""
        sel_key = f"unknown:{idx}"
        if self._sel_days == [sel_key]:
            # Aynı kapsüle tekrar tıklamak seçimi kaldırır
            self._sel_days = []
        else:
            old_days = [d for d in self._sel_days if isinstance(d, int)]
            self._update_cells_style(old_days)  # önceki gün seçimlerini sıfırla
            self._sel_days = [sel_key]
        self._refresh_unknown_pill_styles()
        self._unified_panel.refresh_selection(self._sel_days)

    def _clear_unknown_pill_selection(self):
        self._refresh_unknown_pill_styles(force_none=True)

    def _refresh_unknown_pill_styles(self, force_none: bool = False):
        if not hasattr(self, "_unknown_pills"):
            return
        active_idx = None
        if not force_none and len(self._sel_days) == 1:
            d = self._sel_days[0]
            if isinstance(d, str) and d.startswith("unknown:"):
                active_idx = int(d.split(":", 1)[1])
        for idx, pill in self._unknown_pills.items():
            self._style_unknown_pill(pill, idx == active_idx)

    def _update_cells_style(self, keys: list) -> None:
        for key in keys:
            if key is None or not isinstance(key, int):
                continue
            cell = self._day_cells.get(key)
            if cell is None:
                continue
            is_sel = key in self._sel_days
            is_today = (
                self._today.year == self._year
                and self._today.month == self._month1
                and self._today.day == key
            )
            if is_today:
                cell.setObjectName("dayCellToday" if not is_sel else "dayCellTodaySelected")
            else:
                cell.setObjectName("dayCellSelected" if is_sel else "dayCellNormal")
            cell.style().unpolish(cell)
            cell.style().polish(cell)
            cell.update()

    # Eski tek-seçim güncellemesi — geriye dönük uyumluluk için tutuldu
    def _update_selection_styles(self, old_sel, new_sel) -> None:
        self._update_cells_style([old_sel, new_sel])

    def _clear_filter(self):
        old_days = [d for d in self._sel_days if isinstance(d, int)]
        self._sel_days = []
        self._update_cells_style(old_days)
        self._clear_unknown_pill_selection()
        self._refresh_fu_pill_styles(force_none=True)
        self._unified_panel.refresh_selection([])

    def _on_rec_click(self, ev: dict):
        if self._detail_handler and self._detail_handler(ev):
            self.close()

    def exec(self):
        """Compat shim — overlay olduğu için exec çağrısı show'a düşer."""
        self.show()


# ─────────────────────────────────────────────────────────────────────────────
# Ay kartı — yıl grid'indeki küçük kart
# ─────────────────────────────────────────────────────────────────────────────
class _MonthCard(_ClickFrame):
    def __init__(self, year: int, month: int, events: List[dict],
                 today: date, unknown_day_events: Optional[List[dict]] = None,
                 fully_unknown_events: Optional[List[dict]] = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("monthCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build(year, month, events, today,
                    unknown_day_events or [], fully_unknown_events or [])

    def _build(self, year: int, month: int, events: List[dict], today: date,
               unknown_day_events: List[dict], fully_unknown_events: List[dict]):
        month1 = month + 1
        total_count = len(events) + len(unknown_day_events) + len(fully_unknown_events)

        # En kötü durum rengi → üst şerit
        best_cls = "bos"
        all_for_bar = events + unknown_day_events + fully_unknown_events
        if all_for_bar:
            best_cls = min(all_for_bar, key=lambda e: _STATUS_ORDER.get(e["_cls"], 9))["_cls"]
        bar = _COLOR.get(best_cls, _COLOR["bos"])

        self.setStyleSheet(
            f"QFrame#monthCard{{background:rgba(255,253,248,230);"
            f"border:1px solid rgba(210,225,240,180);"
            f"border-top:5px solid {bar}; border-radius:20px;}}"
            "QFrame#monthCard:hover{"
            f"border-color:rgba(180,200,220,220); border-top:5px solid {bar};"
            "}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 8)
        outer.setSpacing(4)

        # Başlık
        head = QHBoxLayout()
        head.setSpacing(4)
        name_l = QLabel(TR_MONTHS[month])
        name_l.setStyleSheet(
            "background:transparent; font-size:13px; font-weight:900;"
            "color:#0f172a; border:none;"
        )
        head.addWidget(name_l)
        head.addStretch()
        if total_count:
            cnt = QLabel(f"{total_count} kayıt")
            cnt.setStyleSheet(
                "background:#f1f5f9; color:#64748b; border-radius:8px;"
                "padding:2px 8px; font-size:10px; font-weight:700; border:none;"
            )
            head.addWidget(cnt)
        outer.addLayout(head)

        # ── Mini takvim ızgarası ─────────────────────────────────────────
        # Performans: hücre stilleri per-widget setStyleSheet yerine
        # objectName ile _EXTRA_QSS'teki #miniCellToday/#miniCellHasEvent/
        # #miniCellEmpty kurallarından miras alınır (bkz. yukarıdaki QSS bloğu).
        mini_w = QWidget()
        mini_w.setStyleSheet("background:transparent;")
        mg = QGridLayout(mini_w)
        mg.setContentsMargins(0, 2, 0, 2)
        mg.setHorizontalSpacing(2)
        mg.setVerticalSpacing(2)

        for i, dn in enumerate(["Pt", "Sa", "Ça", "Pe", "Cu", "Ct", "Pz"]):
            l = QLabel(dn)
            l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet(
                "background:transparent; color:#94a3b8;"
                "font-size:7px; font-weight:700; border:none;"
            )
            mg.addWidget(l, 0, i)

        days_in_month = calendar.monthrange(year, month1)[1]
        fc = _first_col(year, month1)

        ev_by_day: Dict[int, List[dict]] = {}
        for e in events:
            d = e.get("_eff_date")
            if d is not None:
                ev_by_day.setdefault(d.day, []).append(e)

        idx = 0
        for _ in range(fc):
            blank = QFrame()
            blank.setAttribute(Qt.WA_StyledBackground, True)
            blank.setObjectName("miniCellBlank")
            mg.addWidget(blank, 1, idx)
            idx += 1

        for day in range(1, days_in_month + 1):
            row = 1 + idx // 7
            col = idx % 7
            is_today = (today.year == year and today.month == month1 and today.day == day)
            day_evs = ev_by_day.get(day, [])

            cell_w = QFrame()
            cell_w.setAttribute(Qt.WA_StyledBackground, True)
            if is_today:
                cell_w.setObjectName("miniCellToday")
            elif day_evs:
                cell_w.setObjectName("miniCellHasEvent")
            else:
                cell_w.setObjectName("miniCellEmpty")
            cell_lay = QVBoxLayout(cell_w)
            cell_lay.setContentsMargins(2, 1, 2, 1)
            cell_lay.setSpacing(0)

            num_l = QLabel(str(day))
            num_l.setAlignment(Qt.AlignCenter)
            num_color = "#1f5be3" if is_today else "#475569"
            num_l.setStyleSheet(
                f"background:transparent; color:{num_color};"
                "font-size:8px; font-weight:800; border:none;"
            )
            cell_lay.addWidget(num_l)

            if day_evs:
                best_ev = min(day_evs, key=lambda e: _STATUS_ORDER.get(e["_cls"], 9))
                dot = QLabel("●")
                dot.setAlignment(Qt.AlignCenter)
                dot.setStyleSheet(
                    f"color:{_COLOR.get(best_ev['_cls'], '#d9e1ea')};"
                    "font-size:5px; background:transparent; border:none;"
                )
                cell_lay.addWidget(dot)

            mg.addWidget(cell_w, row, col)
            idx += 1

        outer.addWidget(mini_w, 1)

        # ── Alt chip listesi ─────────────────────────────────────────────
        chip_row = QHBoxLayout()
        chip_row.setSpacing(4)
        for ev in events[:3]:
            cls = ev["_cls"]
            d = ev["_eff_date"]
            txt = f"{d.day} · {_elide(str(ev.get('type') or ''), 9)}"
            chip = QLabel(txt)
            chip.setStyleSheet(
                f"background:{_BG.get(cls, '#f8fafc')};"
                f"color:{_FG.get(cls, '#475569')};"
                "border-radius:6px; padding:2px 6px; font-size:9px;"
                "font-weight:700; border:none;"
            )
            chip.setToolTip(str(ev.get("title") or ev.get("no") or ""))
            chip_row.addWidget(chip)
        if len(events) > 3:
            more = QLabel(f"+{len(events)-3} daha")
            more.setStyleSheet(
                "background:#f1f5f9; color:#64748b; border-radius:6px;"
                "padding:2px 5px; font-size:9px; border:none;"
            )
            chip_row.addWidget(more)
        chip_row.addStretch()
        outer.addLayout(chip_row)

        # ── Gün belirsiz şeridi ────────────────────────────────────────────
        # "YYYY-MM-TBD" formatındaki kayıtlar gün hücresine yerleştirilemez
        # (hangi güne ait olduğu bilinmiyor); bunun yerine kartın altında
        # ayrı, kesikli çizgiyle ayrılmış bir şerit olarak gösterilir.
        if unknown_day_events:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(
                f"background:transparent; border-top:1px dashed {_COLOR['belirsiz']};"
                "max-height:1px; margin-top:2px;"
            )
            outer.addWidget(sep)

            strip = QHBoxLayout()
            strip.setSpacing(5)
            strip.setContentsMargins(0, 3, 0, 0)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{_COLOR['belirsiz']}; font-size:8px; background:transparent; border:none;"
            )
            strip.addWidget(dot)
            txt = QLabel(f"Gün belirsiz · {len(unknown_day_events)} kayıt")
            txt.setStyleSheet(
                f"background:transparent; color:{_FG['belirsiz']};"
                "font-size:10px; font-weight:800; border:none;"
            )
            txt.setToolTip(", ".join(str(e.get("title") or "") for e in unknown_day_events))
            strip.addWidget(txt)
            strip.addStretch()
            outer.addLayout(strip)

        if fully_unknown_events:
            sep2 = QFrame()
            sep2.setFrameShape(QFrame.HLine)
            sep2.setStyleSheet(
                f"background:transparent; border-top:1px dashed {_COLOR['belirsiz']};"
                "max-height:1px; margin-top:2px;"
            )
            outer.addWidget(sep2)

            strip2 = QHBoxLayout()
            strip2.setSpacing(5)
            strip2.setContentsMargins(0, 3, 0, 0)
            dot2 = QLabel("●")
            dot2.setStyleSheet(
                f"color:{_COLOR['belirsiz']}; font-size:8px; background:transparent; border:none;"
            )
            strip2.addWidget(dot2)
            txt2 = QLabel(f"Tarihi belirsiz · {len(fully_unknown_events)} kayıt")
            txt2.setStyleSheet(
                f"background:transparent; color:{_FG['belirsiz']};"
                "font-size:10px; font-weight:800; border:none;"
            )
            txt2.setToolTip(", ".join(str(e.get("title") or "") for e in fully_unknown_events))
            strip2.addWidget(txt2)
            strip2.addStretch()
            outer.addLayout(strip2)


# ─────────────────────────────────────────────────────────────────────────────
# Ana Pencere
# ─────────────────────────────────────────────────────────────────────────────
class ContractCalendarWindow(QDialog):
    _data_loaded_main = Signal(list, list, list, int)
    _data_failed_main = Signal(str)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_active_detail') and self._active_detail:
            try:
                self._active_detail.setGeometry(self.rect())
                self._active_detail._position_card()
            except RuntimeError:
                self._active_detail = None

    def paintEvent(self, event):
        """Gökyüzü tonu radial gradient arka plan."""
        from PySide6.QtGui import QPainter, QRadialGradient, QLinearGradient, QColor, QBrush
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # Base: açık gökyüzü mavi
        painter.fillRect(0, 0, w, h, QColor("#d6e8f8"))
        # Sol üst: derin mavi radial
        grad1 = QRadialGradient(0, 0, w * 0.45)
        grad1.setColorAt(0, QColor(56, 130, 210, 80))
        grad1.setColorAt(0.5, QColor(56, 130, 210, 30))
        grad1.setColorAt(1, QColor(56, 130, 210, 0))
        painter.fillRect(0, 0, w, h, QBrush(grad1))
        # Sağ üst: amber/amber-mavi
        grad2 = QRadialGradient(w, 0, w * 0.35)
        grad2.setColorAt(0, QColor(232, 181, 63, 55))
        grad2.setColorAt(1, QColor(232, 181, 63, 0))
        painter.fillRect(0, 0, w, h, QBrush(grad2))
        # Alt: hafif daha koyu mavi geçiş
        grad3 = QLinearGradient(0, h * 0.6, 0, h)
        grad3.setColorAt(0, QColor(180, 210, 240, 0))
        grad3.setColorAt(1, QColor(160, 200, 235, 40))
        painter.fillRect(0, 0, w, h, QBrush(grad3))
        painter.end()

    def __init__(
        self,
        store: ExcelStore,
        contract_index: Optional[List[dict]] = None,
        parent=None,
        detail_handler: Optional[Callable[[dict], bool]] = None,
    ):
        super().__init__(parent)
        self.store = store
        self.contract_index = list(contract_index or [])
        self.detail_handler = detail_handler
        self.today = date.today()
        self.current_year = self.today.year
        self.platform_filter_value = ""
        self._refreshing_pf = False
        self._all_events: List[dict] = []
        self._month_index: Dict[Tuple[int, int], List[dict]] = {}
        self._month_unknown_index: Dict[Tuple[int, int], List[dict]] = {}
        self._year_only_index: Dict[int, List[dict]] = {}
        self._fully_unknown_events: List[dict] = []
        self._nav_locked = False
        self.setWindowTitle(f"{APP_TITLE} - Tarih Takip")
        self.resize(1680, 940)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )
        self.setStyleSheet(
            STYLE
            + _EXTRA_QSS
            + "QFrame#calendarTopbar{background:transparent; border-bottom:none;}"
        )
        self._active_detail = None
        # Worker/thread refs for async data loading
        self._cal_thread: Optional[QThread] = None
        self._cal_worker = None
        # year -> (contract_events, system_events) cache
        self._event_cache: Dict[int, Tuple[list, list, list]] = {}
        self._volume_rows: list = []
        self._data_loaded_main.connect(self._on_data_loaded)
        self._data_failed_main.connect(self._on_data_failed)
        self._build()
        self.refresh_data(rebuild_index=False)

    # ── UI ────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ────────────────────────────────────────────────────────
        topbar = QFrame()
        topbar.setObjectName("calendarTopbar")
        topbar.setMinimumHeight(76)
        # Şeffaf arka plan — body gradient'i görünsün
        topbar.setStyleSheet(
            "QFrame#calendarTopbar{"
            "background:transparent;"
            "border-bottom:none;"
            "}"
        )
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(22, 10, 22, 10)
        tb.setSpacing(18)

        # ── Sol: ‹ [kicker / yıl] › — HTML tasarımı birebir ──────────────
        nav_btn_style = (
            "QPushButton{"
            "background:rgba(255,255,255,220);"
            "border:1px solid rgba(200,218,235,200);"
            "border-radius:21px;"
            "font-size:22px; font-weight:900;"
            "color:#17202d; padding:0px;}"
            "QPushButton:hover{"
            "background:rgba(255,255,255,255);"
            "border-color:#94a3b8;}"
            "QPushButton:disabled{"
            "color:#94a3b8;"
            "background:rgba(255,255,255,100);}"
        )
        self._btn_prev = QPushButton("‹")
        self._btn_prev.setStyleSheet(nav_btn_style)
        self._btn_prev.setFixedSize(42, 42)
        self._btn_prev.setCursor(Qt.PointingHandCursor)
        self._btn_prev.clicked.connect(lambda: self._change_year(-1))

        yr_title = QVBoxLayout()
        yr_title.setSpacing(0)
        yr_title.setContentsMargins(0, 0, 0, 0)
        kicker = QLabel("KY-STS / TESLİMAT TAKVİMİ")
        kicker.setStyleSheet(
            "color:#6b7280; background:transparent; font-size:10px; font-weight:900;"
            "letter-spacing:.13em;"
        )
        self._yr_lbl = QLabel(str(self.current_year))
        self._yr_lbl.setStyleSheet(
            "color:#17202d; background:transparent;"
            "font-size:38px; font-weight:950; letter-spacing:-.04em;"
        )
        yr_title.addWidget(kicker)
        yr_title.addWidget(self._yr_lbl)

        self._btn_next = QPushButton("›")
        self._btn_next.setStyleSheet(nav_btn_style)
        self._btn_next.setFixedSize(42, 42)
        self._btn_next.setCursor(Qt.PointingHandCursor)
        self._btn_next.clicked.connect(lambda: self._change_year(1))

        year_nav = QHBoxLayout()
        year_nav.setSpacing(12)
        year_nav.setContentsMargins(0, 0, 0, 0)
        year_nav.addWidget(self._btn_prev)
        year_nav.addLayout(yr_title)
        year_nav.addWidget(self._btn_next)
        tb.addLayout(year_nav)

        # ── Orta: legend — pill kutular HTML gibi ────────────────────────
        tb.addStretch()
        legend_items = [
            ("Geciken",      "#e1473f"),
            ("60 gün içinde","#e8b53f"),
            ("Normal",       "#397bd8"),
            ("Teslim edildi","#39a96b"),
        ]
        for txt, color in legend_items:
            pill = QPushButton()
            pill.setEnabled(False)
            pill.setStyleSheet(
                "QPushButton{"
                "background:rgba(255,255,255,220);"
                "border:1px solid rgba(200,218,235,200);"
                "border-radius:18px;"
                "padding:7px 13px 7px 10px;"
                "font-size:12px; font-weight:800; color:#6b7280;"
                "text-align:left;"
                "}"
                "QPushButton:disabled{"
                "background:rgba(255,255,255,220);"
                "border:1px solid rgba(200,218,235,200);"
                "color:#6b7280;"
                "}"
            )
            pill.setText(f"⬤  {txt}")
            pill.setStyleSheet(
                pill.styleSheet()
                + f"QPushButton{{color:#6b7280;}}"
            )
            # Dot renkli, metin gri — QLabel ile daha kolay
            # Pill: QLabel kullan, stylesheet ile tam yuvarlak
            pill_w = QLabel()
            pill_w.setFixedHeight(34)
            pill_w.setTextFormat(Qt.RichText)
            pill_w.setText(
                f'<span style="color:{color};font-size:11px;">⬤</span>'
                f'<span style="color:#374151;font-size:12px;font-weight:800;">&nbsp;&nbsp;{txt}</span>'
            )
            pill_w.setStyleSheet(
                "QLabel{"
                "background:rgba(255,255,255,220);"
                "border:1px solid rgba(200,218,235,200);"
                "border-radius:17px;"
                "padding:0px 14px 0px 10px;"
                "}"
            )
            tb.addWidget(pill_w)

        # "Tarihi belirsiz" — diğerlerinden farklı olarak tıklanabilir:
        # year_only ("YYYY-TBD-TBD") ve fully_unknown ("TBD") kayıtları
        # hiçbir ay kartına yerleştirilemez, bu yüzden ayrı bir özet
        # panelde toplanır.
        self._tbd_pill = QPushButton()
        self._tbd_pill.setCursor(Qt.PointingHandCursor)
        self._tbd_pill.setFixedHeight(34)
        self._tbd_pill.clicked.connect(self._open_unknown_panel)
        self._update_tbd_pill_text()
        self._tbd_pill.setStyleSheet(
            "QPushButton{"
            "background:rgba(255,255,255,220);"
            f"border:1.5px dashed {_COLOR['belirsiz']};"
            "border-radius:17px;"
            "padding:0px 14px 0px 10px;"
            f"color:{_FG['belirsiz']}; font-size:12px; font-weight:800;"
            "text-align:left;"
            "}"
            "QPushButton:hover{background:rgba(255,255,255,255);}"
        )
        tb.addWidget(self._tbd_pill)
        tb.addStretch()

        # ── Teslimat Hacmi butonu ─────────────────────────────────────────
        self._vol_btn = QPushButton("📦  Teslimat Hacmi")
        self._vol_btn.setCursor(Qt.PointingHandCursor)
        self._vol_btn.setFixedHeight(34)
        self._vol_btn.setStyleSheet(
            "QPushButton{"
            "background:rgba(57,123,216,0.12);"
            "border:1.5px solid rgba(57,123,216,0.45);"
            "border-radius:17px;"
            "padding:0px 16px 0px 12px;"
            "color:#1d4ed8; font-size:12px; font-weight:800;"
            "text-align:left;"
            "}"
            "QPushButton:hover{"
            "background:rgba(57,123,216,0.22);"
            "border:1.5px solid rgba(57,123,216,0.7);"
            "}"
        )
        self._vol_btn.clicked.connect(self._open_year_volume)
        tb.addWidget(self._vol_btn)

        # ── Sağ: platform filtresi ────────────────────────────────────────
        self.platform_filter = QComboBox()
        self.platform_filter.setObjectName("calendarPlatformFilter")
        self.platform_filter.setMinimumWidth(160)
        self.platform_filter.setStyleSheet(
            "QComboBox{background:rgba(255,255,255,220); color:#374151;"
            "border:1px solid rgba(200,218,235,200); border-radius:17px;"
            "padding:7px 14px; font-size:12px; font-weight:800;}"
            "QComboBox::drop-down{border:none; width:24px;}"
            "QComboBox::down-arrow{width:10px; height:10px;}"
            "QComboBox:hover{background:rgba(255,255,255,255); border-color:#94a3b8;}"
        )
        self.platform_filter.setFixedHeight(34)
        self.platform_filter.currentIndexChanged.connect(self._on_pf_changed)
        tb.addWidget(self.platform_filter)

        root.addWidget(topbar)

        # ── Yıl grid ──────────────────────────────────────────────────────
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setObjectName("yearGridScroll")
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._grid_scroll.setStyleSheet(
            "QScrollArea#yearGridScroll{background:transparent; border:none;}"
            "QScrollArea#yearGridScroll > QWidget{background:transparent;}"
        )
        self._grid_host = QWidget()
        self._grid_host.setObjectName("calBg")
        # Şeffaf — paintEvent'teki gradient görünsün
        self._grid_host.setAttribute(Qt.WA_TranslucentBackground, False)
        self._grid_host.setStyleSheet("QWidget#calBg{background:transparent;}")
        self._year_grid = QGridLayout(self._grid_host)
        self._year_grid.setContentsMargins(20, 16, 20, 20)
        self._year_grid.setHorizontalSpacing(12)
        self._year_grid.setVerticalSpacing(12)
        self._grid_scroll.setWidget(self._grid_host)
        root.addWidget(self._grid_scroll, 1)

    # ── Veri ──────────────────────────────────────────────────────────────
    def _annotate_events(self, raw_items: list) -> List[dict]:
        """
        Ham DB satırlarını takvim event dict'e çevirir (saf hesaplama).

        Tarih formatı esnek tarih standardına göre değerlendirilir:
          YYYY-MM-DD      -> exact              (_eff_date dolu, hesaplamaya girer)
          YYYY-MM-TBD     -> month_unknown_day  (_eff_year/_eff_month dolu, gün yok)
          YYYY-TBD-TBD    -> year_only          (_eff_year dolu)
          TBD             -> fully_unknown      (hiçbir zaman bilgisi yok)
          "-" / boş       -> na                 (tarih uygulanmıyor, kayıt atlanır)

        "-" / boş dışındaki tüm formatlar event listesinde kalır; sadece
        hesaplama (kalan gün, takvim yerleşimi) "exact" olanlarda yapılır.
        """
        today = self.today
        out: List[dict] = []
        for item in raw_items:
            raw = _effective_date_raw(item)
            kind = _date_kind(raw)
            if kind == "na":
                continue

            eff: Optional[date] = None
            eff_year: Optional[int] = None
            eff_month: Optional[int] = None  # 1-indexed

            if kind == "exact":
                eff = _parse_date(raw)
                if eff is None:
                    continue
                eff_year, eff_month = eff.year, eff.month
            elif kind == "month_unknown_day":
                parts = _month_tbd_parts(raw)
                if parts is None:
                    continue
                eff_year, eff_month = parts
            elif kind == "year_only":
                eff_year = _year_tbd_parts(raw)
                if eff_year is None:
                    continue
            # fully_unknown: eff_year/eff_month None kalır

            cls = _classify(item, eff, today, kind)
            no    = str(item.get("no") or "")
            ctype = str(item.get("type") or item.get("contract_type") or "")
            title = str(item.get("title") or item.get("content") or item.get("note") or "")
            if not title:
                title = f"{no} · {ctype}" if ctype else no
            out.append({
                "_eff_date": eff, "_cls": cls,
                "_date_kind": kind,
                "_eff_year": eff_year, "_eff_month": eff_month,
                "_eff_raw": raw,
                "row":       int(item.get("row") or 0),
                "delivery_id": item.get("delivery_id"),  # sadece Teslimat tipinde dolu
                "platform":  str(item.get("platform") or ""),
                "no": no,    "user": str(item.get("user") or ""),
                "type": ctype, "title": title,
                "system_label": str(item.get("system_label") or ""),
                "status":           str(item.get("status") or ""),
                "acceptance_date":  str(item.get("acceptance_date") or ""),
                "planned_acceptance_date": str(item.get("planned_acceptance_date") or ""),
                "completion_date":  str(item.get("completion_date") or ""),
            })
        return out

    def _db_path(self):
        """STSStore'un db dosya yolunu döndürür; ExcelStore ise None."""
        try:
            return getattr(getattr(self.store, "db", None), "path", None)
        except Exception:
            return None

    def _start_data_load(self, year: int, invalidate_cache: bool = False):
        """Verilen yıl için CalendarDataWorker başlatır.

        Cache'de varsa ve invalidate_cache=False ise worker başlatmaz.
        """
        if invalidate_cache:
            self._event_cache.pop(year, None)

        if year in self._event_cache:
            c_evs, s_evs, v_rows = self._event_cache[year]
            self._apply_events(c_evs, s_evs, v_rows)
            return

        db_path = self._db_path()
        if db_path is None:
            # ExcelStore fallback — contract_index'ten build et (senkron, hızlı)
            raw = list(self.contract_index)
            self._volume_rows = []
            self._all_events = self._annotate_events(raw)
            self._rebuild_month_index()
            self._refresh_pf()
            self._render_year()
            self._update_tbd_pill_text()
            return

        # Zaten yükleme varsa iptal et
        if self._cal_thread and self._cal_thread.isRunning():
            return

        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)

        pf = self.platform_filter_value
        thread = QThread(self)
        worker = CalendarDataWorker(db_path, year, year, pf)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        # Do not connect the worker signal directly to UI rendering code via a
        # Python lambda. In PySide, a bare callable has no QObject receiver
        # affinity, so it can run in the worker thread and then create/parent
        # widgets from there. Relay through signals owned by this dialog; their
        # slots are delivered on the dialog/main GUI thread.
        worker.finished.connect(lambda c, s, v, y=year: self._data_loaded_main.emit(c, s, v, y))
        worker.failed.connect(lambda err: self._data_failed_main.emit(err))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_cal_refs)

        self._cal_thread = thread
        self._cal_worker = worker
        thread.start()

    def _clear_cal_refs(self):
        self._cal_thread = None
        self._cal_worker = None

    def _is_gui_thread(self) -> bool:
        app = QApplication.instance()
        return bool(app and QThread.currentThread() == app.thread())

    def _on_data_loaded(self, contract_events: list, system_events: list,
                        volume_rows: list, year: int):
        if not self._is_gui_thread():
            self._data_loaded_main.emit(contract_events, system_events, volume_rows, year)
            return
        self._event_cache[year] = (list(contract_events), list(system_events), list(volume_rows))
        self._apply_events(contract_events, system_events, volume_rows)

    def _on_data_failed(self, error_text: str):
        if not self._is_gui_thread():
            self._data_failed_main.emit(error_text)
            return
        _log.error("Takvim veri yuklenemedi: %s", error_text)
        self._btn_prev.setEnabled(True)
        self._btn_next.setEnabled(True)
        self._clear_cal_refs()

    def _apply_events(self, contract_events: list, system_events: list,
                      volume_rows: Optional[list] = None):
        if not self._is_gui_thread():
            self._data_loaded_main.emit(
                contract_events, system_events, volume_rows or [], self.current_year
            )
            return
        self._volume_rows = list(volume_rows or [])
        # Takvimde yalnızca Teslimat (kabul) kayıtları gösterilir.
        # Sözleşme ve Sistem kayıtlarının termin tarihleri fazladan gürültü
        # oluşturuyor; bileşen bilgisi de yalnızca teslimatlar üzerinden geliyor.
        all_raw = list(contract_events) + list(system_events)
        delivery_only = [r for r in all_raw if str(r.get("type") or "").lower() == "teslimat"]
        self._all_events = self._annotate_events(delivery_only)
        self._rebuild_month_index()
        self._refresh_pf()
        self._render_year()
        self._update_tbd_pill_text()
        self._btn_prev.setEnabled(True)
        self._btn_next.setEnabled(True)

    def _visible(self) -> List[dict]:
        pf = self.platform_filter_value
        if not pf:
            return list(self._all_events)
        return [e for e in self._all_events if e.get("platform") == pf]

    def _rebuild_month_index(self) -> None:
        """
        Performans: yıl render'ı her ay için _visible() üzerinde ayrı ayrı
        tarama yapmasın diye, görünür event'ler TEK geçişte (year, month)
        anahtarlı sözlüklere gruplanır ve cache'lenir. Platform filtresi
        veya _all_events değiştiğinde çağrılmalı.

        - _month_index: sadece "exact" tarihli event'ler, (year, month1) -> list
        - _month_unknown_index: "month_unknown_day" event'leri, (year, month1) -> list
        - _year_only_index: "year_only" event'leri, year -> list
        - _fully_unknown: "fully_unknown" event'ler (yıldan bağımsız), tek liste
        """
        month_idx: Dict[Tuple[int, int], List[dict]] = {}
        month_unknown_idx: Dict[Tuple[int, int], List[dict]] = {}
        year_only_idx: Dict[int, List[dict]] = {}
        fully_unknown: List[dict] = []

        for e in self._visible():
            kind = e.get("_date_kind", "exact")
            if kind == "exact":
                d = e["_eff_date"]
                if d is None:
                    continue
                month_idx.setdefault((d.year, d.month), []).append(e)
            elif kind == "month_unknown_day":
                y, m = e.get("_eff_year"), e.get("_eff_month")
                if y is None or m is None:
                    continue
                month_unknown_idx.setdefault((y, m), []).append(e)
            elif kind == "year_only":
                y = e.get("_eff_year")
                if y is None:
                    continue
                year_only_idx.setdefault(y, []).append(e)
            elif kind == "fully_unknown":
                fully_unknown.append(e)

        self._month_index = month_idx
        self._month_unknown_index = month_unknown_idx
        self._year_only_index = year_only_idx
        self._fully_unknown_events = fully_unknown

    def _for_month(self, year: int, month: int) -> List[dict]:
        """month 0-indexed. Sadece exact (kesin) tarihli event'leri döner."""
        return self._month_index.get((year, month + 1), [])

    def _for_month_unknown_day(self, year: int, month: int) -> List[dict]:
        """month 0-indexed. 'YYYY-MM-TBD' formatındaki event'leri döner."""
        return self._month_unknown_index.get((year, month + 1), [])

    def _for_year_only(self, year: int) -> List[dict]:
        """'YYYY-TBD-TBD' formatındaki, sadece yılı bilinen event'leri döner."""
        return self._year_only_index.get(year, [])

    def _for_fully_unknown(self) -> List[dict]:
        """'TBD' formatındaki, yıldan bağımsız hiçbir tarih bilgisi olmayan event'ler."""
        return self._fully_unknown_events

    # ── Render ────────────────────────────────────────────────────────────
    def _render_year(self):
        if not self._is_gui_thread():
            _log.error("Takvim render isteği GUI thread dışında engellendi.")
            return
        while self._year_grid.count():
            item = self._year_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._yr_lbl.setText(str(self.current_year))

        for month in range(12):
            evs     = self._for_month(self.current_year, month)
            unk_evs = self._for_month_unknown_day(self.current_year, month)
            # fully_unknown (TBD) kayıtlar ayı bilinmiyor → hiçbir ay kartına eklenmez,
            # sadece "Tarihi belirsiz" butonunun açtığı _UnknownDatesDialog'da gösterilir.
            card = _MonthCard(
                self.current_year, month, evs, self.today,
                unknown_day_events=unk_evs,
            )
            card.clicked.connect(lambda m=month: self._open_month(m))
            self._year_grid.addWidget(card, month // 4, month % 4)

        for c in range(4):
            self._year_grid.setColumnStretch(c, 1)
        for r in range(3):
            self._year_grid.setRowStretch(r, 1)

    # ── Tarihi belirsiz kayıtlar (year_only + fully_unknown) ───────────────
    def _update_tbd_pill_text(self) -> None:
        """Üst bardaki 'Tarihi belirsiz' pill'inin sayısını günceller.
        year_only -> mevcut yıla ait ('YYYY-TBD-TBD'); fully_unknown ->
        yıldan bağımsız ('TBD'). İkisi toplanır."""
        n = len(self._for_year_only(self.current_year)) + len(self._for_fully_unknown())
        txt = f"Tarihi belirsiz · {n}" if n else "Tarihi belirsiz"
        self._tbd_pill.setText(f"⬤  {txt}")
        self._tbd_pill.setStyleSheet(self._tbd_pill.styleSheet())  # repaint tetikle

    def _open_unknown_panel(self) -> None:
        yo = self._for_year_only(self.current_year)
        fu = self._for_fully_unknown()
        dlg = _UnknownDatesDialog(yo, fu, self.current_year, self._on_detail, self)
        dlg.closed.connect(lambda: setattr(self, "_active_detail", None))
        self._active_detail = dlg

    def _open_year_volume(self) -> None:
        """Yıllık Teslimat Hacmi modal penceresini açar."""
        if not self._volume_rows and not self._event_cache.get(self.current_year):
            return  # Veri henüz yüklenmedi
        vol = _YearVolumeDialog(
            volume_rows=self._volume_rows,
            year=self.current_year,
            platform_filter=self.platform_filter_value,
            parent=self,
        )
        vol.closed.connect(lambda: setattr(self, "_active_detail", None))
        self._active_detail = vol

    # ── Yıl geçişi ────────────────────────────────────────────────────────
    def _change_year(self, d: int):
        if self._cal_thread and self._cal_thread.isRunning():
            return  # yükleme sürerken geçiş engelle
        self.current_year += d
        self._yr_lbl.setText(str(self.current_year))
        # Cache'de varsa anında render, yoksa worker başlat
        self._start_data_load(self.current_year)

    # ── Ay detay ──────────────────────────────────────────────────────────
    def _open_month(self, month: int):
        evs     = self._for_month(self.current_year, month)
        unk_evs = self._for_month_unknown_day(self.current_year, month)
        # fully_unknown (TBD) ve year_only (YYYY-TBD-TBD) teslimatlar da
        # _UnifiedSidePanel'e geçirilmeli ki bileşen eşleştirmesi yapılabilsin.
        # Bunlar takvimde gün hücresine yerleşmiyor ama sağ panelde
        # "bileşen toplamı" hesabına katılmaları için all_events'e dahil ediliyor.
        extra_evs = (
            self._for_year_only(self.current_year)
            + self._for_fully_unknown()
        )
        self._active_detail = _MonthDetailDialog(
            evs, self.current_year, month,
            self._on_detail, self,
            unknown_day_events=unk_evs,
            fully_unknown_events=extra_evs,
            volume_rows=self._volume_rows,
            platform_filter=self.platform_filter_value,
        )
        self._active_detail.closed.connect(self._on_detail_closed)

    def _on_detail_closed(self, data_changed: bool = False):
        self._active_detail = None
        # Performans: "Yıla dön" / Esc / dışarı tıklama ile kapatıldığında
        # (dialog açıkken hiçbir kayıt düzenlenmediyse) ekrandaki 12 ay
        # kartı zaten güncel — yeniden inşa etmeye gerek yok. Bir kayıt
        # gerçekten düzenlendiyse (_on_detail True döndüyse, bkz.
        # _wrapped_detail_handler) _render_year() orada zaten
        # refresh_data() üzerinden tetiklenmiş olur; burada tekrar
        # çağırmak yalnızca data_changed=True iken anlamlıdır (örn. ekstra
        # bir garanti için), data_changed=False iken tamamen atlanır.
        if data_changed:
            self._render_year()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if hasattr(self, '_active_detail') and self._active_detail:
                self._active_detail.close()
                return
            self.close()
        super().keyPressEvent(event)

    def _on_detail(self, ev: dict) -> bool:
        if not self.detail_handler:
            return False
        result = self.detail_handler(ev)
        if result:
            self.refresh_data(rebuild_index=True)
            p = self.parent()
            if p and hasattr(p, "refresh"):
                try:
                    p.refresh()
                except Exception:
                    pass
        return bool(result)

    # ── Public API ────────────────────────────────────────────────────────
    def refresh_data(self, rebuild_index: bool = True):
        """Takvim verilerini yeniden yükle.

        rebuild_index=True olduğunda event cache'i temizle ve
        mevcut yıl için yeni worker başlat.
        """
        if rebuild_index:
            self._event_cache.clear()
        self._start_data_load(self.current_year, invalidate_cache=rebuild_index)

    def refresh_from_index(
        self,
        store: Optional[ExcelStore] = None,
        contract_index: Optional[List[dict]] = None,
    ):
        if store is not None:
            self.store = store
        if contract_index is not None:
            self.contract_index = list(contract_index or [])
        # Store degisince cache gecersiz
        self._event_cache.clear()
        self.refresh_data(rebuild_index=False)

    # ── Platform filtresi ─────────────────────────────────────────────────
    def _refresh_pf(self):
        if not hasattr(self, "platform_filter"):
            return
        current = self.platform_filter_value
        try:
            platforms = [str(p) for p in self.store.platform_names() if p]
        except Exception:
            platforms = sorted({
                str(e.get("platform") or "")
                for e in self._all_events if e.get("platform")
            })
        self._refreshing_pf = True
        try:
            self.platform_filter.blockSignals(True)
            self.platform_filter.clear()
            self.platform_filter.addItem("Tümü", "")
            for p in platforms:
                self.platform_filter.addItem(p, p)
            idx = self.platform_filter.findData(current)
            self.platform_filter.setCurrentIndex(max(idx, 0))
            self.platform_filter_value = current if idx >= 0 else ""
        finally:
            self.platform_filter.blockSignals(False)
            self._refreshing_pf = False

    def _on_pf_changed(self):
        if self._refreshing_pf:
            return
        self.platform_filter_value = str(self.platform_filter.currentData() or "")
        # Platform degisti: cache temizle, index'i yeniden kur ve yeniden yukle
        self._event_cache.clear()
        self._volume_rows = []
        self._rebuild_month_index()
        self._start_data_load(self.current_year)
