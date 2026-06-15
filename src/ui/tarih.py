# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from src.config.app_config import APP_TITLE, TR_MONTHS
from src.services.excel_store import ExcelStore
from src.ui.theme import STYLE

_STATUS_ORDER = {"geciken": 0, "kritik": 1, "normal": 2, "tamamlandi": 3, "bos": 9}
_COLOR  = {"geciken": "#e1473f", "kritik": "#e8b53f", "normal": "#397bd8", "tamamlandi": "#39a96b", "bos": "#d9e1ea"}
_BG     = {"geciken": "#fef2f2", "kritik": "#fffbeb", "normal":  "#e8f0fe", "tamamlandi": "#ecfdf5"}
_FG     = {"geciken": "#b91c1c", "kritik": "#92400e", "normal":  "#1f5be3", "tamamlandi": "#047857"}
_LABEL  = {"geciken": "Geciken", "kritik": "60 gün içinde", "normal": "Normal",
           "tamamlandi": "Teslim edildi", "bos": "Kayıt yok"}

_EXTRA_QSS = """
QDialog { background: transparent; }

QFrame#monthCard { border-radius:18px; }
QFrame#monthCard:hover { border-color:#7eb3d8 !important; }
QScrollArea#plainScroll { border:none; background:transparent; }
QScrollArea#plainScroll > QWidget > QWidget { background:transparent; }
QScrollArea#yearGridScroll { border:none; background:transparent; }
QScrollArea#yearGridScroll > QWidget { background:transparent; }
QScrollArea#yearGridScroll QWidget#calBg { background:transparent; }
QWidget#calBg { background: transparent; }
QWidget#detailSideBg { background:#f8fafc; border-right:1px solid #e2e8f0; }
QWidget#detailRightBg { background:#f0f4fc; }
QWidget#detailTopbarBg { background:#ffffff; border-bottom:1px solid #e2e8f0; }
QWidget#dayHeaderBg { background:#f0f4fc; border-bottom:1px solid #e2e8f0; }
QFrame#dayCellNormal { background:#ffffff; border:1px solid #d8e2ed; border-radius:10px; min-height:90px; }
QFrame#dayCellToday  { background:#ffffff; border:2px solid #1f5be3; border-radius:10px; min-height:90px; }
QFrame#dayCellSelected { background:#ffffff; border:2px solid #5b9bd5; border-radius:10px; min-height:90px; }
QFrame#dayCellEmpty  { background:transparent; border:1px solid transparent; border-radius:10px; min-height:90px; }
QFrame#statCard { background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; }
QFrame#recCard  { background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; }

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


def _parse_date(text: str) -> Optional[date]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, "%Y-%m-%d").date()
    except ValueError:
        return None


def _effective_date(item: dict) -> Optional[date]:
    """
    Sistem kaydı  → completion_date (termin)
    Kabul kaydı   → acceptance_date > planned_acceptance_date > None
    """
    ctype = str(item.get("type") or "").lower()
    if "sistem" in ctype:
        return _parse_date(str(item.get("completion_date") or ""))
    d = _parse_date(str(item.get("acceptance_date") or ""))
    if d:
        return d
    return _parse_date(str(item.get("planned_acceptance_date") or ""))


def _classify(item: dict, eff: date, today: date) -> str:
    s = str(item.get("status") or "").lower()
    # Gerçek kabul tarihi varsa → tamamlandı
    if item.get("acceptance_date") or "tamam" in s or "teslim" in s:
        return "tamamlandi"
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
class _ClickFrame(QFrame):
    clicked = Signal()
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


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
}
_STATUS_LABEL = {
    "geciken": "Geciken", "kritik": "60 gün",
    "normal": "Normal", "tamamlandi": "Teslim",
}
_WORST_ORDER = ["geciken", "kritik", "normal", "tamamlandi"]


def _worst_cls(classes):
    for c in _WORST_ORDER:
        if c in classes:
            return c
    return "normal"


def _date_label(ev: dict) -> str:
    """Tarihin ne olduğunu etiketle."""
    if ev.get("acceptance_date"):
        return "Kabul"
    if ev.get("planned_acceptance_date") and "sistem" not in str(ev.get("type","")).lower():
        return "Planlanan"
    return "Termin"


def _date_display(ev: dict) -> tuple:
    """(etiket, tarih_str, renk) döndür."""
    ctype = str(ev.get("type") or "").lower()
    acc = str(ev.get("acceptance_date") or "")
    plan = str(ev.get("planned_acceptance_date") or "")
    comp = str(ev.get("completion_date") or "")

    if "sistem" in ctype:
        d = _parse_date(comp)
        return ("Termin", d.strftime("%d.%m.%Y") if d else "—", "#64748b")

    if acc:
        d = _parse_date(acc)
        ds = d.strftime("%d.%m.%Y") if d else acc
        # Erken mi geç mi?
        if plan and d:
            pd = _parse_date(plan)
            if pd:
                diff = (d - pd).days
                if diff < 0:
                    return ("Kabul ✓", f"{ds} ({abs(diff)}g erken)", "#047857")
                elif diff > 0:
                    return ("Kabul ⚠", f"{ds} ({diff}g geç)", "#854f0b")
        return ("Kabul", ds, "#047857")
    if plan:
        d = _parse_date(plan)
        return ("Planlanan", d.strftime("%d.%m.%Y") if d else plan, "#185fa5")
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
        hdr = QWidget()
        hdr.setStyleSheet(
            "QWidget{"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1e293b, stop:1 #0f172a);"
            "}"
        )
        hdr.setFixedHeight(70)
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(1)
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
            (None,         "Toplam",  "#f8fafc", "#475569", "#94a3b8"),
        ]
        for i, (key, lbl, bg, fg, border) in enumerate(items):
            card = QFrame()
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
        """Platform > Sözleşme No > Sistem adı"""
        # Gruplama: platform → no → sistem kayıtları
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
                # Sözleşme no — ok yok, sadece etiket (indent)
                no_lbl = QLabel(f"  📄 {no}")
                no_lbl.setStyleSheet(
                    f"background:transparent; font-size:11px; font-weight:600;"
                    f"color:#374151; padding:4px 6px 2px 24px; border:none;"
                )
                pl_sec.add(no_lbl)

                for ev in sorted(no_evs, key=lambda x: x["_eff_date"]):
                    _, dval, dcol = _date_display(ev)
                    raw = str(ev.get("title") or "")
                    no_str = str(ev.get("no") or "")
                    label = raw[len(no_str)+3:] if raw.startswith(no_str+" · ") else (raw or no_str)
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
                earliest = min(no_evs, key=lambda e: e["_eff_date"])
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
        c = {"geciken": 0, "kritik": 0, "tamamlandi": 0}
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
# Ay Detay Dialog
# ─────────────────────────────────────────────────────────────────────────────
# Ay Detay Dialog
# ─────────────────────────────────────────────────────────────────────────────
class _MonthDetailDialog(QWidget):
    """
    Yıl takviminin üzerinde overlay olarak açılan ay detay paneli.
    Arka plan blur efekti için ana pencereye overlay layer olarak eklenir.
    """
    closed = Signal()

    def __init__(self, events: List[dict], year: int, month: int,
                 detail_handler: Optional[Callable], parent=None):
        super().__init__(parent)
        self._events = events
        self._year = year
        self._month = month
        self._month1 = month + 1
        self._detail_handler = detail_handler
        self._today = date.today()
        self._sel_day: Optional[int] = None
        # Tam ebeveyn üzerinde yay
        self.setGeometry(parent.rect() if parent else self.geometry())
        self.setStyleSheet(STYLE + _EXTRA_QSS)
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

    def _position_card(self):
        if self.parent():
            pr = self.parent().rect()
            w = int(pr.width() * 0.88)
            h = int(pr.height() * 0.90)
            x = (pr.width() - w) // 2
            y = (pr.height() - h) // 2
        else:
            w, h, x, y = 1300, 780, 40, 40
        self._card.setGeometry(x, y, w, h)
        if hasattr(self, '_backdrop'):
            self._backdrop.setGeometry(self.rect())

    def _build_overlay(self):
        """Backdrop + merkezi içerik."""
        # Backdrop — tıklanınca kapat
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("QWidget{background:rgba(10,16,26,0.60);}")
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

        # Kart içi layout: sol panel + sağ panel yan yana
        card_lay = QHBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # Sol panel
        self._side_panel = _SideTreePanel(
            self._events, self._year, self._month,
            detail_handler=self._detail_handler,
            parent=self._card
        )
        self._side_panel.setFixedWidth(320)
        card_lay.addWidget(self._side_panel)

        # Sağ panel
        right = QWidget(self._card)
        right.setObjectName("calRight")
        right.setStyleSheet(
            "QWidget#calRight{background:#f0f4fc;"
            "border-top-right-radius:16px;"
            "border-bottom-right-radius:16px;}"
        )
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        card_lay.addWidget(right, 1)

        # ── Topbar ──────────────────────────────────────────────────────
        topbar = QWidget(right)
        topbar.setStyleSheet(
            "QWidget{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e293b,stop:1 #0f172a);"
            "border-top-right-radius:16px;"
            "}"
        )
        topbar.setFixedHeight(70)
        tb_lay = QHBoxLayout(topbar)
        tb_lay.setContentsMargins(22, 0, 22, 0)
        tb_lay.setSpacing(14)
        month_title = QLabel(f"{TR_MONTHS[self._month]} {self._year}")
        month_title.setStyleSheet(
            "font-size:26px; font-weight:900; color:#ffffff; background:transparent;"
        )
        tb_lay.addWidget(month_title, 1)
        hint_lbl = QLabel("Gün hücresine tıkla → sol panel filtreler")
        hint_lbl.setStyleSheet(
            "color:rgba(148,163,184,0.8); font-size:11px; background:transparent;"
        )
        tb_lay.addWidget(hint_lbl)
        back_btn = QPushButton("← Yıla dön")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.12); color:#ffffff;"
            "border:1px solid rgba(255,255,255,0.25); border-radius:8px;"
            "font-size:12px; font-weight:600; padding:6px 14px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.22);}"
        )
        back_btn.clicked.connect(self.close)
        tb_lay.addWidget(back_btn)
        right_lay.addWidget(topbar)

        # ── Gün başlıkları ──────────────────────────────────────────────
        dh = QWidget(right)
        dh.setStyleSheet("QWidget{background:#1e293b;}")
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
        self._cal_host.setStyleSheet("QWidget{background:#f0f4fc;}")
        self._cal_grid = QGridLayout(self._cal_host)
        self._cal_grid.setContentsMargins(16, 10, 16, 16)
        self._cal_grid.setHorizontalSpacing(6)
        self._cal_grid.setVerticalSpacing(6)
        cal_scroll.setWidget(self._cal_host)
        right_lay.addWidget(cal_scroll, 1)

        self._render_cal()

    def _build(self, container=None):
        """Compat — artık _build_overlay kullanıyoruz."""
        pass


    # ── Veri ──────────────────────────────────────────────────────────────
    def _for_day(self, day: int) -> List[dict]:
        return [e for e in self._events if e["_eff_date"].day == day]

    def _counts(self) -> Dict[str, int]:
        c = {"geciken": 0, "kritik": 0, "tamamlandi": 0}
        for e in self._events:
            if e["_cls"] in c:
                c[e["_cls"]] += 1
        return c

    # ── Render ────────────────────────────────────────────────────────────
    def _render_all(self):
        self._render_cal()

    def _update_side_for_day(self, day: Optional[int]):
        """Gün seçilince sol paneli güncelle."""
        if day:
            evs = self._for_day(day)
        else:
            evs = self._events
        self._side_panel.update_events(evs)

    def _render_cal(self):
        while self._cal_grid.count():
            item = self._cal_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        days_in_month = calendar.monthrange(self._year, self._month1)[1]
        first_col = _first_col(self._year, self._month1)
        idx = 0

        for _ in range(first_col):
            b = QFrame()
            b.setObjectName("dayCellEmpty")
            b.setMinimumHeight(90)
            self._cal_grid.addWidget(b, idx // 7, idx % 7)
            idx += 1

        for day in range(1, days_in_month + 1):
            is_today = (
                self._today.year == self._year
                and self._today.month == self._month1
                and self._today.day == day
            )
            selected = self._sel_day == day
            day_evs = self._for_day(day)
            cell = self._build_cell(day, day_evs, is_today, selected)
            self._cal_grid.addWidget(cell, idx // 7, idx % 7)
            idx += 1

        while idx % 7 != 0:
            b = QFrame()
            b.setObjectName("dayCellEmpty")
            b.setMinimumHeight(90)
            self._cal_grid.addWidget(b, idx // 7, idx % 7)
            idx += 1

        for c in range(7):
            self._cal_grid.setColumnStretch(c, 1)

    def _build_cell(self, day: int, evs: List[dict],
                    is_today: bool, selected: bool) -> QFrame:
        if is_today:
            obj = "dayCellToday"
        elif selected:
            obj = "dayCellSelected"
        else:
            obj = "dayCellNormal"
        frame = QFrame()
        frame.setObjectName(obj)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setCursor(Qt.PointingHandCursor)

        # Click via event filter trick
        def _press(ev, d=day):
            if ev.button() == Qt.LeftButton:
                self._on_day_click(d)
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
    def _on_day_click(self, day: int):
        self._sel_day = None if self._sel_day == day else day
        self._update_side_for_day(self._sel_day)
        self._render_cal()

    def _clear_filter(self):
        self._sel_day = None
        self._update_side_for_day(None)
        self._render_cal()

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
                 today: date, parent=None):
        super().__init__(parent)
        self.setObjectName("monthCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build(year, month, events, today)

    def _build(self, year: int, month: int, events: List[dict], today: date):
        month1 = month + 1

        # En kötü durum rengi → üst şerit
        best_cls = "bos"
        if events:
            best_cls = min(events, key=lambda e: _STATUS_ORDER.get(e["_cls"], 9))["_cls"]
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
        if events:
            cnt = QLabel(f"{len(events)} kayıt")
            cnt.setStyleSheet(
                "background:#f1f5f9; color:#64748b; border-radius:8px;"
                "padding:2px 8px; font-size:10px; font-weight:700; border:none;"
            )
            head.addWidget(cnt)
        outer.addLayout(head)

        # ── Mini takvim ızgarası ─────────────────────────────────────────
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
            ev_by_day.setdefault(e["_eff_date"].day, []).append(e)

        idx = 0
        for _ in range(fc):
            mg.addWidget(QLabel(""), 1, idx)
            idx += 1

        for day in range(1, days_in_month + 1):
            row = 1 + idx // 7
            col = idx % 7
            is_today = (today.year == year and today.month == month1 and today.day == day)
            day_evs = ev_by_day.get(day, [])

            # Gün hücresi — kutu içinde (HTML .cell gibi)
            if is_today:
                cell_style = (
                    "QFrame{background:rgba(232,240,254,200);"
                    "border:1px solid rgba(57,123,216,.55); border-radius:5px;}"
                )
            elif day_evs:
                cell_style = (
                    "QFrame{background:rgba(255,255,255,180);"
                    "border:1px solid rgba(180,200,220,160); border-radius:5px;}"
                )
            else:
                cell_style = (
                    "QFrame{background:rgba(255,255,255,90);"
                    "border:1px solid rgba(200,215,230,120); border-radius:5px;}"
                )
            cell_w = QFrame()
            cell_w.setStyleSheet(cell_style)
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


# ─────────────────────────────────────────────────────────────────────────────
# Ana Pencere
# ─────────────────────────────────────────────────────────────────────────────
class ContractCalendarWindow(QDialog):
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
        self._build()
        self.refresh_data(rebuild_index=not bool(self.contract_index))

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
        kicker = QLabel("KY-STS / TERMİN & KABUL TAKVİMİ")
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
        tb.addStretch()

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
    def _build_events(self) -> List[dict]:
        today = self.today
        events: List[dict] = []

        for item in self.contract_index:
            eff = _effective_date(item)
            if not eff:
                continue
            cls = _classify(item, eff, today)
            no = str(item.get("no") or "")
            ctype = str(item.get("type") or item.get("contract_type") or "")
            title = str(item.get("content") or item.get("note") or "")
            if not title:
                title = f"{no} · {ctype}" if ctype else no
            events.append({
                "_eff_date": eff, "_cls": cls,
                "row": int(item.get("row") or 0),
                "platform": str(item.get("platform") or ""),
                "no": no, "user": str(item.get("user") or ""),
                "type": ctype, "title": title,
                "status": str(item.get("status") or ""),
                "acceptance_date": str(item.get("acceptance_date") or ""),
                "planned_acceptance_date": str(item.get("planned_acceptance_date") or ""),
                "completion_date": str(item.get("completion_date") or ""),
            })

        # Sistem olayları (lazy, hata tolere edilir)
        try:
            for item in self.contract_index:
                platform = str(item.get("platform") or "")
                no = str(item.get("no") or "")
                row = int(item.get("row") or 0)
                if not platform or not no:
                    continue
                try:
                    _ci, systems, _ = self.store.load_contract_structure(
                        platform, no, start_row=row if row > 0 else None
                    )
                except Exception:
                    continue
                for sys_info in systems or []:
                    acc = _parse_date(str(sys_info.acceptance_date or ""))
                    comp = _parse_date(str(sys_info.completion_date or ""))
                    eff_d = acc or comp
                    if not eff_d:
                        continue
                    sys_item = {
                        "status": str(sys_info.status or ""),
                        "acceptance_date": sys_info.acceptance_date or "",
                        "completion_date": sys_info.completion_date or "",
                    }
                    cls = _classify(sys_item, eff_d, today)
                    sys_name = str(sys_info.name or "")
                    title = f"{no} · {sys_name}" if sys_name else no
                    events.append({
                        "_eff_date": eff_d, "_cls": cls,
                        "row": row, "platform": platform, "no": no,
                        "user": str(item.get("user") or ""),
                        "type": "Sistem", "title": title,
                        "system_label": sys_name,
                        "status": sys_item["status"],
                        "acceptance_date": sys_item["acceptance_date"],
                        "completion_date": sys_item["completion_date"],
                    })
        except Exception:
            pass

        return events

    def _visible(self) -> List[dict]:
        pf = self.platform_filter_value
        if not pf:
            return list(self._all_events)
        return [e for e in self._all_events if e.get("platform") == pf]

    def _for_month(self, year: int, month: int) -> List[dict]:
        """month 0-indexed"""
        return [
            e for e in self._visible()
            if e["_eff_date"].year == year and e["_eff_date"].month == month + 1
        ]

    # ── Render ────────────────────────────────────────────────────────────
    def _render_year(self):
        while self._year_grid.count():
            item = self._year_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._yr_lbl.setText(str(self.current_year))

        for month in range(12):
            evs = self._for_month(self.current_year, month)
            card = _MonthCard(self.current_year, month, evs, self.today)
            card.clicked.connect(lambda m=month: self._open_month(m))
            self._year_grid.addWidget(card, month // 4, month % 4)

        for c in range(4):
            self._year_grid.setColumnStretch(c, 1)
        for r in range(3):
            self._year_grid.setRowStretch(r, 1)

    # ── Yıl geçişi ────────────────────────────────────────────────────────
    def _change_year(self, d: int):
        if self._nav_locked:
            return
        self._nav_locked = True
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        QTimer.singleShot(60, lambda: self._do_change(d))

    def _do_change(self, d: int):
        self.current_year += d
        self._render_year()
        self._nav_locked = False
        self._btn_prev.setEnabled(True)
        self._btn_next.setEnabled(True)

    # ── Ay detay ──────────────────────────────────────────────────────────
    def _open_month(self, month: int):
        evs = self._for_month(self.current_year, month)
        self._active_detail = _MonthDetailDialog(
            evs, self.current_year, month,
            self._on_detail, self
        )
        self._active_detail.closed.connect(self._on_detail_closed)

    def _on_detail_closed(self):
        self._active_detail = None
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
        if rebuild_index:
            try:
                self.contract_index = self.store.build_contract_index()
            except Exception:
                pass
        self._all_events = self._build_events()
        self._refresh_pf()
        self._render_year()

    def refresh_from_index(
        self,
        store: Optional[ExcelStore] = None,
        contract_index: Optional[List[dict]] = None,
    ):
        if store is not None:
            self.store = store
        if contract_index is not None:
            self.contract_index = list(contract_index or [])
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
        self._render_year()
