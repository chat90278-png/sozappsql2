# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QComboBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config.app_config import APP_TITLE, TR_MONTHS, TR_WEEKDAYS
from src.models.app_models import SystemInfo
from src.services.excel_store import ExcelStore
from src.ui.theme import STYLE


def parse_calendar_iso_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


class CalendarEventChip(QLabel):
    doubleClicked = Signal(object)

    def __init__(self, text: str, event_data: dict, parent=None):
        super().__init__(text, parent)
        self.event_data = dict(event_data or {})
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit(self.event_data)
        super().mouseDoubleClickEvent(event)


class CalendarEventCard(QFrame):
    clicked = Signal(object)

    def __init__(self, event_data: dict, parent=None):
        super().__init__(parent)
        self.event_data = dict(event_data or {})
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.event_data)
        super().mousePressEvent(event)


class CalendarMorePopup(QFrame):
    """Açılan gün kutusu: sığmayan sözleşme/sistemleri hücrenin altında listeler."""

    def __init__(self, events: List[dict], chip_style: Callable[[str], str], detail_cb: Callable[[dict], None], parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.events = list(events or [])
        self.chip_style = chip_style
        self.detail_cb = detail_cb
        self.setObjectName("calendarMorePopup")
        self.setStyleSheet(STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)
        arrow = QLabel("▲")
        arrow.setObjectName("calendarPopupArrow")
        arrow.setAlignment(Qt.AlignCenter)
        root.addWidget(arrow)
        title = QLabel(f"Bu günde {len(self.events)} kayıt")
        title.setObjectName("calendarPopupTitle")
        root.addWidget(title)
        for ev in self.events:
            chip = CalendarEventChip(self._event_label(ev), ev, self)
            chip.setStyleSheet(self.chip_style(ev.get("status_class", "normal")))
            chip.setToolTip(self._tooltip(ev))
            chip.doubleClicked.connect(self.detail_cb)
            root.addWidget(chip)

    def _event_label(self, ev: dict) -> str:
        if ev.get("mode") == "system":
            return f"• {ev.get('no', '')} · {ev.get('system_label', '')}"
        return f"• {ev.get('no', '')} · {ev.get('platform', '')}"

    def _tooltip(self, ev: dict) -> str:
        parts = [
            f"Sözleşme: {ev.get('no', '')}",
            f"Platform: {ev.get('platform', '')}",
        ]
        if ev.get("mode") == "system":
            parts.append(f"Sistem: {ev.get('system_label', '')}")
        parts.extend([
            f"Kullanıcı: {ev.get('user', '')}",
            f"Tür: {ev.get('type', '')}",
            f"Bitiş: {ev.get('deadline').isoformat() if ev.get('deadline') else ''}",
            f"Durum: {ev.get('status', '')}",
        ])
        return "\n".join(parts)


class ContractCalendarWindow(QDialog):
    MODE_CONTRACT = "contract"
    MODE_SYSTEM = "system"

    def __init__(self, store: ExcelStore, contract_index: Optional[List[dict]] = None, parent=None, detail_handler: Optional[Callable[[dict], bool]] = None):
        super().__init__(parent)
        self.store = store
        self.contract_index = list(contract_index or [])
        self.detail_handler = detail_handler
        self.today = date.today()
        self.current_year = self.today.year
        self.current_month = self.today.month
        self.view_mode = self.MODE_CONTRACT
        self.events: List[dict] = []
        self.contract_events: List[dict] = []
        self.system_events: Optional[List[dict]] = None
        self.platform_filter_value = ""
        self._refreshing_platform_filter = False
        self.last_updated_at: Optional[datetime] = None
        self._more_popup: Optional[CalendarMorePopup] = None
        self.setWindowTitle(f"{APP_TITLE} - Tarih Takip")
        self.resize(1680, 940)
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_data(rebuild_index=not bool(self.contract_index))

    def build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("calendarSidebar")
        self.sidebar.setFixedWidth(300)
        side_lay = QVBoxLayout(self.sidebar)
        side_lay.setContentsMargins(16, 14, 16, 14)
        side_lay.setSpacing(12)

        self.side_title = QLabel("ÖZET")
        self.side_title.setObjectName("calendarSection")
        side_lay.addWidget(self.side_title)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        self.stat_overdue = self._make_stat_card("0", "GECİKEN")
        self.stat_critical = self._make_stat_card("0", "60 GÜN İÇİNDE")
        self.stat_active = self._make_stat_card("0", "AKTİF")
        self.stat_done = self._make_stat_card("0", "TAMAMLANDI")
        stats_grid.addWidget(self.stat_overdue, 0, 0)
        stats_grid.addWidget(self.stat_critical, 0, 1)
        stats_grid.addWidget(self.stat_active, 1, 0)
        stats_grid.addWidget(self.stat_done, 1, 1)
        side_lay.addLayout(stats_grid)

        self.overdue_title = QLabel("🔴 GECİKEN SÖZLEŞMELER")
        self.overdue_title.setObjectName("calendarSection")
        side_lay.addWidget(self.overdue_title)
        self.overdue_box = QVBoxLayout()
        self.overdue_box.setSpacing(6)
        side_lay.addLayout(self.overdue_box)

        self.critical_title = QLabel("🟡 60 GÜN İÇİNDE DOLACAK")
        self.critical_title.setObjectName("calendarSection")
        side_lay.addWidget(self.critical_title)
        self.critical_box = QVBoxLayout()
        self.critical_box.setSpacing(6)
        side_lay.addLayout(self.critical_box)
        side_lay.addStretch()
        root.addWidget(self.sidebar, 0)

        self.main = QFrame()
        self.main.setObjectName("calendarMain")
        main_lay = QVBoxLayout(self.main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        top = QFrame()
        top.setObjectName("calendarTopbar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(18, 10, 18, 10)
        top_lay.setSpacing(12)
        tleft = QVBoxLayout()
        tleft.setContentsMargins(0, 0, 0, 0)
        tleft.setSpacing(2)
        t1 = QLabel("KONFİGÜRASYON YÖNETİMİ — TARİH TAKİP")
        t1.setObjectName("calendarTopTitle")
        self.top_sub = QLabel("Son güncelleme: —")
        self.top_sub.setObjectName("calendarTopSub")
        tleft.addWidget(t1)
        tleft.addWidget(self.top_sub)
        top_lay.addLayout(tleft, 1)

        self.platform_filter = QComboBox()
        self.platform_filter.setObjectName("calendarPlatformFilter")
        self.platform_filter.setMinimumWidth(180)
        self.platform_filter.currentIndexChanged.connect(self.on_platform_filter_changed)
        top_lay.addWidget(self.platform_filter, 0)

        mode_box = QFrame()
        mode_box.setObjectName("calendarModeSwitch")
        mode_lay = QHBoxLayout(mode_box)
        mode_lay.setContentsMargins(4, 4, 4, 4)
        mode_lay.setSpacing(2)
        self.btn_contract_mode = QPushButton("Sözleşme")
        self.btn_system_mode = QPushButton("Sistem")
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for btn, mode in ((self.btn_contract_mode, self.MODE_CONTRACT), (self.btn_system_mode, self.MODE_SYSTEM)):
            btn.setObjectName("calendarModeButton")
            btn.setCheckable(True)
            btn.setProperty("mode", mode)
            btn.setMinimumHeight(30)
            self.mode_group.addButton(btn)
            mode_lay.addWidget(btn)
        self.btn_contract_mode.setChecked(True)
        self.btn_contract_mode.clicked.connect(lambda: self.set_view_mode(self.MODE_CONTRACT))
        self.btn_system_mode.clicked.connect(lambda: self.set_view_mode(self.MODE_SYSTEM))
        top_lay.addWidget(mode_box, 0)
        main_lay.addWidget(top, 0)

        nav = QFrame()
        nav.setObjectName("calendarNav")
        nav_lay = QHBoxLayout(nav)
        nav_lay.setContentsMargins(20, 10, 20, 10)
        nav_lay.setSpacing(8)
        self.month_title = QLabel("")
        self.month_title.setObjectName("calendarMonth")
        nav_lay.addWidget(self.month_title, 1)
        self.btn_today = QPushButton("Bugün")
        self.btn_today.setObjectName("secondary")
        self.btn_prev = QPushButton("‹")
        self.btn_prev.setObjectName("secondary")
        self.btn_next = QPushButton("›")
        self.btn_next.setObjectName("secondary")
        for b in (self.btn_today, self.btn_prev, self.btn_next):
            b.setMinimumHeight(30)
        nav_lay.addWidget(self.btn_today)
        nav_lay.addWidget(self.btn_prev)
        nav_lay.addWidget(self.btn_next)
        self.btn_today.clicked.connect(self.go_today)
        self.btn_prev.clicked.connect(self.go_prev_month)
        self.btn_next.clicked.connect(self.go_next_month)
        main_lay.addWidget(nav, 0)

        days_row = QFrame()
        days_row.setObjectName("calendarDaysRow")
        days_lay = QGridLayout(days_row)
        days_lay.setContentsMargins(20, 8, 20, 8)
        days_lay.setHorizontalSpacing(6)
        days_lay.setVerticalSpacing(0)
        for i, dname in enumerate(TR_WEEKDAYS):
            lab = QLabel(dname)
            lab.setObjectName("calendarDayHeader")
            lab.setAlignment(Qt.AlignCenter)
            days_lay.addWidget(lab, 0, i)
        main_lay.addWidget(days_row, 0)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setObjectName("plainScroll")
        self.grid_host = QWidget()
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(20, 8, 20, 14)
        self.grid_layout.setHorizontalSpacing(6)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_scroll.setWidget(self.grid_host)
        main_lay.addWidget(self.grid_scroll, 1)

        foot = QFrame()
        foot.setObjectName("calendarFooter")
        foot_lay = QHBoxLayout(foot)
        foot_lay.setContentsMargins(20, 6, 20, 8)
        foot_lay.setSpacing(14)
        for txt, obj in [("● Geciken", "legendRed"), ("● 60 Gün İçinde", "legendAmber"), ("● Normal", "legendBlue"), ("● Tamamlandı", "legendGreen")]:
            l = QLabel(txt)
            l.setObjectName(obj)
            foot_lay.addWidget(l)
        foot_lay.addStretch()
        self.footer_note = QLabel("")
        self.footer_note.setObjectName("calendarFooterNote")
        foot_lay.addWidget(self.footer_note)
        main_lay.addWidget(foot, 0)
        root.addWidget(self.main, 1)

    def _norm(self, s: str) -> str:
        txt = str(s or "").strip().lower()
        return txt.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")

    def _classify(self, item: dict, deadline: date) -> str:
        status = self._norm(str(item.get("status", "")))
        if "tamam" in status or "teslim edildi" in status:
            return "tamamlandi"
        delta = (deadline - self.today).days
        if delta < 0:
            return "geciken"
        if delta <= 60:
            return "kritik"
        return "normal"

    def refresh_data(self, rebuild_index: bool = True):
        if rebuild_index:
            self.contract_index = self.store.build_contract_index()
        self.system_events = None
        self.contract_events = self._build_contract_events()
        if self.view_mode == self.MODE_SYSTEM:
            self.events = self._build_system_events()
        else:
            self.events = list(self.contract_events)
        self.events.sort(key=lambda x: x["deadline"])
        self.last_updated_at = datetime.now()
        self.refresh_platform_filter()
        self.update_sidebar()
        self.render_month()

    def refresh_from_index(self, store: Optional[ExcelStore] = None, contract_index: Optional[List[dict]] = None):
        if store is not None:
            self.store = store
        if contract_index is not None:
            self.contract_index = list(contract_index or [])
        self.refresh_data(rebuild_index=False)

    def refresh_platform_filter(self):
        if not hasattr(self, "platform_filter"):
            return
        current = str(self.platform_filter_value or "")
        try:
            platforms = [str(p or "") for p in self.store.platform_names()] if self.store else []
        except Exception:
            platforms = []
        if not platforms:
            platforms = sorted({str(it.get("platform", "") or "") for it in self.contract_index if str(it.get("platform", "") or "")})
        platforms = [p for p in platforms if p]
        self._refreshing_platform_filter = True
        try:
            self.platform_filter.blockSignals(True)
            self.platform_filter.clear()
            self.platform_filter.addItem("Tümü", "")
            for platform in platforms:
                self.platform_filter.addItem(platform, platform)
            idx = self.platform_filter.findData(current)
            if idx < 0:
                current = ""
                idx = 0
            self.platform_filter.setCurrentIndex(idx)
            self.platform_filter_value = current
        finally:
            self.platform_filter.blockSignals(False)
            self._refreshing_platform_filter = False

    def on_platform_filter_changed(self):
        if self._refreshing_platform_filter:
            return
        self.platform_filter_value = str(self.platform_filter.currentData() or "")
        self.update_sidebar()
        self.render_month()

    def visible_events(self) -> List[dict]:
        selected = str(self.platform_filter_value or "")
        if not selected:
            return list(self.events)
        return [ev for ev in self.events if str(ev.get("platform", "") or "") == selected]

    def update_last_refresh_label(self):
        if not hasattr(self, "top_sub"):
            return
        if self.last_updated_at:
            self.top_sub.setText(f"Son güncelleme: {self.last_updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            self.top_sub.setText("Son güncelleme: —")

    def _build_contract_events(self) -> List[dict]:
        events: List[dict] = []
        for it in self.contract_index:
            d = parse_calendar_iso_date(str(it.get("completion_date", "") or ""))
            if not d:
                continue
            cls = self._classify(it, d)
            events.append({
                "mode": self.MODE_CONTRACT,
                "row": int(it.get("row", 0) or 0),
                "platform": str(it.get("platform", "") or ""),
                "no": str(it.get("no", "") or ""),
                "user": str(it.get("user", "") or ""),
                "type": str(it.get("type", "") or ""),
                "status": str(it.get("status", "") or ""),
                "status_class": cls,
                "deadline": d,
                "content": str(it.get("content", "") or ""),
            })
        return events

    def _system_event(self, base: dict, system: SystemInfo) -> Optional[dict]:
        deadline = parse_calendar_iso_date(str(system.completion_date or "")) or parse_calendar_iso_date(str(base.get("completion_date", "") or ""))
        if not deadline:
            return None
        status = str(system.status or base.get("status", "") or "")
        item = dict(base)
        item["status"] = status
        cls = self._classify(item, deadline)
        return {
            "mode": self.MODE_SYSTEM,
            "row": int(base.get("row", 0) or 0),
            "platform": str(base.get("platform", "") or ""),
            "no": str(base.get("no", "") or ""),
            "user": str(base.get("user", "") or ""),
            "type": str(base.get("type", "") or ""),
            "status": status,
            "status_class": cls,
            "deadline": deadline,
            "content": str(base.get("content", "") or ""),
            "system_label": str(system.name or ""),
        }

    def _build_system_events(self) -> List[dict]:
        if self.system_events is not None:
            return list(self.system_events)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            events: List[dict] = []
            for base in self.contract_index:
                platform = str(base.get("platform", "") or "")
                no = str(base.get("no", "") or "")
                row = int(base.get("row", 0) or 0)
                if not platform or not no:
                    continue
                try:
                    _ci, systems, _deliveries = self.store.load_contract_structure(platform, no, start_row=row if row > 0 else None)
                except Exception:
                    continue
                for system in systems or []:
                    ev = self._system_event(base, system)
                    if ev:
                        events.append(ev)
            self.system_events = sorted(events, key=lambda x: x["deadline"])
            return list(self.system_events)
        finally:
            QApplication.restoreOverrideCursor()

    def set_view_mode(self, mode: str):
        if mode not in {self.MODE_CONTRACT, self.MODE_SYSTEM} or self.view_mode == mode:
            return
        self.view_mode = mode
        if self.view_mode == self.MODE_SYSTEM:
            self.btn_system_mode.setChecked(True)
            self.events = self._build_system_events()
        else:
            self.btn_contract_mode.setChecked(True)
            self.events = list(self.contract_events)
        self.events.sort(key=lambda x: x["deadline"])
        self.update_sidebar()
        self.render_month()

    def _clear_layout(self, lay: QVBoxLayout):
        while lay.count():
            child = lay.takeAt(0)
            w = child.widget()
            if w:
                w.deleteLater()

    def _make_stat_card(self, num: str, lbl: str) -> QFrame:
        card = QFrame()
        card.setObjectName("calendarStatCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 10, 10, 8)
        l.setSpacing(2)
        n = QLabel(str(num))
        n.setObjectName("calendarStatNum")
        n.setAlignment(Qt.AlignCenter)
        t = QLabel(lbl)
        t.setObjectName("calendarStatLbl")
        t.setAlignment(Qt.AlignCenter)
        l.addWidget(n)
        l.addWidget(t)
        return card

    def _set_stat_value(self, card: QFrame, value: int):
        labels = card.findChildren(QLabel)
        if labels:
            labels[0].setText(str(value))

    def _event_card(self, ev: dict, delta_days: int) -> QFrame:
        f = CalendarEventCard(ev)
        cls = ev["status_class"]
        f.setObjectName("eventCardOverdue" if cls == "geciken" else "eventCardWarn")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        no_text = f"#{ev['no']}"
        if ev.get("mode") == self.MODE_SYSTEM and ev.get("system_label"):
            no_text += f" · {ev['system_label']}"
        no = QLabel(no_text)
        no.setObjectName("eventCardNo")
        sub_bits = [ev.get("platform", ""), ev.get("user", "")]
        pl = QLabel(" · ".join([x for x in sub_bits if x]))
        pl.setObjectName("eventCardSub")
        if delta_days < 0:
            dtxt = f"Son: {ev['deadline'].isoformat()} · {abs(delta_days)} gün geçti"
        else:
            dtxt = f"Son: {ev['deadline'].isoformat()} · {delta_days} gün kaldı"
        dd = QLabel(dtxt)
        dd.setObjectName("eventCardDate")
        lay.addWidget(no)
        lay.addWidget(pl)
        lay.addWidget(dd)
        f.setToolTip(self._tooltip(ev))
        f.clicked.connect(self.open_event_detail)
        return f

    def update_sidebar(self):
        visible = self.visible_events()
        overdue = [e for e in visible if e["status_class"] == "geciken"]
        critical = [e for e in visible if e["status_class"] == "kritik"]
        done = [e for e in visible if e["status_class"] == "tamamlandi"]
        active = [e for e in visible if e["status_class"] != "tamamlandi"]
        entity = "SİSTEM" if self.view_mode == self.MODE_SYSTEM else "SÖZLEŞME"
        entity_lower = "sistem" if self.view_mode == self.MODE_SYSTEM else "sözleşme"

        self.side_title.setText(f"ÖZET · {entity}")
        self.overdue_title.setText(f"🔴 GECİKEN {entity}LER")
        self.critical_title.setText(f"🟡 60 GÜN İÇİNDE DOLACAK {entity}LER")
        self._set_stat_value(self.stat_overdue, len(overdue))
        self._set_stat_value(self.stat_critical, len(critical))
        self._set_stat_value(self.stat_active, len(active))
        self._set_stat_value(self.stat_done, len(done))

        self._clear_layout(self.overdue_box)
        self._clear_layout(self.critical_box)
        for ev in overdue[:8]:
            delta = (ev["deadline"] - self.today).days
            self.overdue_box.addWidget(self._event_card(ev, delta))
        for ev in critical[:8]:
            delta = (ev["deadline"] - self.today).days
            self.critical_box.addWidget(self._event_card(ev, delta))
        if self.overdue_box.count() == 0:
            info = QLabel(f"Geciken {entity_lower} yok.")
            info.setObjectName("muted")
            self.overdue_box.addWidget(info)
        if self.critical_box.count() == 0:
            info = QLabel(f"60 gün içinde dolacak {entity_lower} yok.")
            info.setObjectName("muted")
            self.critical_box.addWidget(info)

    def go_today(self):
        self.current_year = self.today.year
        self.current_month = self.today.month
        self.render_month()

    def go_prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.render_month()

    def go_next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.render_month()

    def _clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _chip_style(self, status_class: str) -> str:
        if status_class == "geciken":
            return "background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:6px;padding:2px 6px;"
        if status_class == "kritik":
            return "background:#fffbeb;color:#b45309;border:1px solid #fde68a;border-radius:6px;padding:2px 6px;"
        if status_class == "tamamlandi":
            return "background:#ecfdf5;color:#047857;border:1px solid #86efac;border-radius:6px;padding:2px 6px;"
        return "background:#e8f0fe;color:#1f5be3;border:1px solid #bfdbfe;border-radius:6px;padding:2px 6px;"

    def _event_label(self, ev: dict) -> str:
        if ev.get("mode") == self.MODE_SYSTEM:
            return f"• {ev.get('no', '')} · {ev.get('system_label', '')}"
        return f"• {ev.get('no', '')} · {ev.get('platform', '')}"

    def _tooltip(self, ev: dict) -> str:
        parts = [f"Sözleşme: {ev.get('no', '')}", f"Platform: {ev.get('platform', '')}"]
        if ev.get("mode") == self.MODE_SYSTEM:
            parts.append(f"Sistem: {ev.get('system_label', '')}")
        parts.extend([
            f"Kullanıcı: {ev.get('user', '')}",
            f"Tür: {ev.get('type', '')}",
            f"Bitiş: {ev.get('deadline').isoformat() if ev.get('deadline') else ''}",
            f"Durum: {ev.get('status', '')}",
        ])
        return "\n".join(parts)

    def _build_day_cell(self, day: int, day_events: List[dict], is_today: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("calendarCellToday" if is_today else "calendarCell")
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        top = QHBoxLayout()
        lbl_day = QLabel(str(day))
        lbl_day.setObjectName("calendarCellDay")
        top.addWidget(lbl_day)
        top.addStretch()
        if is_today:
            badge = QLabel("BUGÜN")
            badge.setObjectName("todayPill")
            top.addWidget(badge)
        v.addLayout(top)
        visible_count = 3
        for ev in day_events[:visible_count]:
            chip = CalendarEventChip(self._event_label(ev), ev, frame)
            chip.setStyleSheet(self._chip_style(ev["status_class"]))
            chip.setToolTip(self._tooltip(ev))
            chip.doubleClicked.connect(self.open_event_detail)
            v.addWidget(chip)
        if len(day_events) > visible_count:
            more_btn = QPushButton(f"⌄ +{len(day_events) - visible_count} daha")
            more_btn.setObjectName("calendarMoreButton")
            more_btn.setCursor(Qt.PointingHandCursor)
            more_btn.clicked.connect(lambda _=False, btn=more_btn, events=list(day_events): self.show_more_popup(btn, events))
            v.addWidget(more_btn)
        v.addStretch()
        return frame

    def show_more_popup(self, anchor: QWidget, events: List[dict]):
        if self._more_popup:
            self._more_popup.close()
        self._more_popup = CalendarMorePopup(events, self._chip_style, self.open_event_detail, self)
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        self._more_popup.move(pos)
        self._more_popup.show()

    def render_month(self):
        month_name = TR_MONTHS[self.current_month - 1]
        self.month_title.setText(f"{month_name} {self.current_year}")
        self.update_last_refresh_label()
        self.footer_note.setText(f"Bugün: {self.today.isoformat()}")

        self._clear_grid()
        events_by_day: Dict[int, List[dict]] = {}
        for ev in self.visible_events():
            d = ev["deadline"]
            if d.year == self.current_year and d.month == self.current_month:
                events_by_day.setdefault(d.day, []).append(ev)

        first_weekday, days_in_month = calendar.monthrange(self.current_year, self.current_month)
        first_col = (first_weekday + 1) % 7
        cell_index = 0

        for _ in range(first_col):
            blank = QFrame()
            blank.setObjectName("calendarCellEmpty")
            self.grid_layout.addWidget(blank, cell_index // 7, cell_index % 7)
            cell_index += 1

        for day in range(1, days_in_month + 1):
            is_today = self.current_year == self.today.year and self.current_month == self.today.month and day == self.today.day
            cell = self._build_day_cell(day, events_by_day.get(day, []), is_today)
            self.grid_layout.addWidget(cell, cell_index // 7, cell_index % 7)
            cell_index += 1

        while cell_index % 7 != 0:
            blank = QFrame()
            blank.setObjectName("calendarCellEmpty")
            self.grid_layout.addWidget(blank, cell_index // 7, cell_index % 7)
            cell_index += 1

    def open_event_detail(self, ev: dict):
        if self._more_popup:
            self._more_popup.close()
        if self.detail_handler and self.detail_handler(ev):
            self.refresh_data(rebuild_index=True)
            p = self.parent()
            if p and hasattr(p, "refresh"):
                try:
                    p.refresh()
                except Exception:
                    pass
            return
        platform = str(ev.get("platform", "") or "")
        no = str(ev.get("no", "") or "")
        if not platform or not no:
            QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayları okunamadı.")
