# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QSizePolicy, QProgressBar,
)

from src.services.excel_store import normalize_sheet_name
from src.ui.widgets.user_select import MultiUserSelectWidget, MultiStaffSelectWidget
from src.ui.widgets.platform_select import PlatformSelectWidget

class PlatformTabsWidget(QWidget):
    """Header içinde gömülü premium/neon platform sekme rayı.

    Not: Önceki sürümde QScrollArea yüksekliği, host yüksekliği ve buton
    yüksekliği birbirine çok yakın hesaplandığı için aktif mavi chip rail
    çerçevesine tam oturmuyor gibi görünüyordu. Bu sürümde ölçüler sabit ve
    simetriktir: rail 32px, iç boşluk 0px, buton 30px; sağ uçta 2px güvenlik payı vardır.
    """

    activePlatformChanged = Signal(int)

    DEFAULT_RAIL_HEIGHT = 32
    INNER_PAD = 0
    BUTTON_HEIGHT = 30
    BUTTON_SPACING = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._platforms: List[dict] = []
        self._active = 0
        self._content_width = 76
        self._min_scroll_width = 300
        self._max_width = 420
        self._buttons: Dict[int, QPushButton] = {}
        self._rail_height = self.DEFAULT_RAIL_HEIGHT
        self.setFixedHeight(self._rail_height)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._rail = QFrame(self)
        self._rail.setObjectName("PlatformTabRail")
        self._rail.setFixedHeight(self._rail_height)
        self._rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        rail_lay = QHBoxLayout(self._rail)
        rail_lay.setContentsMargins(self.INNER_PAD, self.INNER_PAD, self.INNER_PAD, self.INNER_PAD)
        rail_lay.setSpacing(0)

        self._scroll = QScrollArea(self._rail)
        self._scroll.setObjectName("PlatformTabScroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setFixedHeight(self.BUTTON_HEIGHT)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._scroll.viewport().setStyleSheet("background:transparent;border:0;")
        rail_lay.addWidget(self._scroll, 0, Qt.AlignCenter)
        outer.addWidget(self._rail, 0, Qt.AlignCenter)

        self._host = QWidget()
        self._host.setObjectName("PlatformTabScrollContent")
        self._host.setStyleSheet("QWidget#PlatformTabScrollContent{background:transparent;border:0;}")
        self._host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._host.setFixedHeight(self.BUTTON_HEIGHT)
        self._lay = QHBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(self.BUTTON_SPACING)
        self._lay.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._scroll.setWidget(self._host)
        self._apply_rail_style()

    def _rail_padding_width(self) -> int:
        return self.INNER_PAD * 2 + 2

    def _button_height(self) -> int:
        return self.BUTTON_HEIGHT

    def _apply_rail_style(self):
        self._rail.setStyleSheet("""
            QFrame#PlatformTabRail {
                background: rgba(5, 18, 43, 0.64);
                border: 1px solid rgba(96, 165, 250, 0.44);
                border-radius: 16px;
                padding: 0px;
                margin: 0px;
            }
        """)
        self._scroll.setStyleSheet("""
            QScrollArea#PlatformTabScroll {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QScrollArea#PlatformTabScroll > QWidget > QWidget { background:transparent; }
            QScrollBar:horizontal { height:0px; background:transparent; }
        """)

    def set_platforms(self, platforms: List[object], active_platform_id: int = 0):
        vals = []
        seen = set()
        for p in platforms or []:
            if isinstance(p, dict):
                pid = int(p.get("platform_id") or p.get("id") or 0)
                name = str(p.get("platform_name") or p.get("name") or "").strip()
                is_primary = bool(p.get("is_primary"))
            else:
                name = str(p or "").strip()
                pid = 0
                is_primary = False
            key = pid if pid else name.casefold()
            if name and key not in seen:
                seen.add(key)
                vals.append({"platform_id": pid, "platform_name": name, "is_primary": is_primary})
        self._platforms = vals
        active_id = int(active_platform_id or 0)
        valid_ids = {int(p.get("platform_id") or 0) for p in self._platforms}
        if active_id not in valid_ids:
            primary = next((p for p in self._platforms if p.get("is_primary")), None)
            active_id = int((primary or (self._platforms[0] if self._platforms else {})).get("platform_id") or 0)
        self._active = active_id
        self._render()

    def _render(self):
        self._buttons.clear()
        while self._lay.count():
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        metrics = QFontMetrics(self.font())
        total_width = 0
        single = len(self._platforms) <= 1
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(self.BUTTON_SPACING)

        for platform in self._platforms:
            name = str(platform.get("platform_name") or "")
            pid = int(platform.get("platform_id") or 0)
            btn = QPushButton(name)
            btn.setObjectName("PlatformTabButton")
            btn.setProperty("platform_id", pid)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            chip_width = min(168, max(92 if single else 84, metrics.horizontalAdvance(name) + (32 if single else 34)))
            btn.setFixedSize(chip_width, self._button_height())
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setToolTip(name)
            # Dış çerçeveyi taşırdığı için drop shadow kullanılmıyor; neon etki border/gradient ile veriliyor.
            btn.setGraphicsEffect(None)
            btn.setStyleSheet("""
                QPushButton#PlatformTabButton {
                    background: rgba(9, 31, 68, 0.72);
                    border: 1px solid rgba(96, 165, 250, 0.30);
                    color: rgba(226, 239, 255, 0.88);
                    font-weight: 900;
                    font-size: 11px;
                    letter-spacing: 0.45px;
                    padding: 0px 10px;
                    min-height: 30px;
                    max-height: 30px;
                    border-radius: 15px;
                    text-align: center;
                }
                QPushButton#PlatformTabButton[active="true"] {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(37, 99, 235, 235),
                        stop:0.55 rgba(59, 130, 246, 245),
                        stop:1 rgba(14, 74, 160, 238));
                    border: 1px solid rgba(191, 226, 255, 0.98);
                    color: #FFFFFF;
                }
                QPushButton#PlatformTabButton[active="false"] {
                    background: rgba(8, 30, 64, 0.62);
                    border: 1px solid rgba(96, 165, 250, 0.26);
                    color: rgba(219, 234, 254, 0.88);
                }
                QPushButton#PlatformTabButton[active="false"]:hover {
                    background: rgba(30, 83, 170, 0.42);
                    border-color: rgba(147, 197, 253, 0.60);
                    color: #FFFFFF;
                }
                QPushButton#PlatformTabButton[active="true"]:hover {
                    border-color: rgba(224, 242, 254, 1.0);
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(37, 99, 235, 245),
                        stop:0.55 rgba(59, 130, 246, 255),
                        stop:1 rgba(14, 74, 160, 245));
                }
            """)
            btn.clicked.connect(lambda _=False, platform_id=pid: self._set_active(platform_id))
            btn.ensurePolished()
            self._lay.addWidget(btn, 0, Qt.AlignVCenter)
            self._buttons[pid] = btn
            total_width += chip_width

        if self._platforms:
            total_width += self._lay.spacing() * max(0, len(self._platforms) - 1)

        content_width = max(1, total_width)
        self._host.setFixedSize(content_width, self._button_height())
        self._content_width = max(70, content_width)

        rail_width = self._content_width + self._rail_padding_width()
        if len(self._platforms) >= 4:
            rail_width = min(self._max_width, max(self._min_scroll_width, rail_width))
        else:
            rail_width = min(rail_width, self._max_width)
        rail_width = max(80, rail_width)
        scroll_width = max(1, rail_width - self._rail_padding_width() + 2)

        self.setMinimumWidth(rail_width)
        self.setMaximumWidth(self._max_width)
        self.setFixedWidth(rail_width)
        self._rail.setFixedWidth(rail_width)
        self._scroll.setFixedWidth(scroll_width)
        self._sync_measured_heights()
        self._refresh_button_states()
        self.updateGeometry()
        self._ensure_active_visible()
        self.setToolTip(", ".join(str(p.get("platform_name") or "") for p in self._platforms))

    def _ensure_active_visible(self):
        active_btn = self._buttons.get(int(self._active or 0))
        if active_btn is not None:
            self._scroll.ensureWidgetVisible(active_btn, 0, 0)

    def _refresh_button_states(self):
        active_id = int(self._active or 0)
        for pid, btn in self._buttons.items():
            active = bool(pid) and int(pid) == active_id
            btn.setProperty("active", "true" if active else "false")
            btn.setChecked(active)
            btn.setGraphicsEffect(None)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        self._ensure_active_visible()

    def wheelEvent(self, event):
        delta = event.angleDelta().x() or event.angleDelta().y()
        if delta:
            bar = self._scroll.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
            event.accept()
            return
        super().wheelEvent(event)

    def sizeHint(self) -> QSize:
        width = min(max(80, self._content_width + self._rail_padding_width()), self._max_width)
        if len(self._platforms) >= 4:
            width = max(self._min_scroll_width, width)
        return QSize(width, self._rail_height)

    def minimumSizeHint(self) -> QSize:
        width = min(max(80, self._content_width + self._rail_padding_width()), self._max_width)
        if len(self._platforms) >= 4:
            width = min(width, self._min_scroll_width)
        return QSize(width, self._rail_height)

    def _host_height(self) -> int:
        return self._button_height()

    def _sync_measured_heights(self) -> None:
        self._rail_height = self.DEFAULT_RAIL_HEIGHT
        self._host.setFixedHeight(self._button_height())
        self._scroll.setFixedHeight(self._button_height())
        self._rail.setFixedHeight(self._rail_height)
        self.setFixedHeight(self._rail_height)

    def _set_active(self, platform_id: int):
        platform_id = int(platform_id or 0)
        if platform_id == int(self._active or 0):
            return
        self._active = platform_id
        self._refresh_button_states()
        self.activePlatformChanged.emit(platform_id)


class FixedContractTypeField(QLineEdit):
    """Dropdown olmayan, ComboBox benzeri minimal API sağlayan salt-okunur sözleşme tipi alanı."""

    currentTextChanged = Signal(str)
    currentIndexChanged = Signal(int)

    def __init__(self, text: str = "Ana Sözleşme", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText(text)
        self.setStyleSheet(
            "QLineEdit{background:#ffffff; color:#0f172a; border:1px solid #cbd5e1; "
            "border-radius:6px; padding:7px 10px; font-weight:800;}"
        )

    def currentText(self) -> str:
        return self.text()

    def setCurrentText(self, text: str):
        self.setText(str(text or ""))

    def setText(self, text: str):
        old = self.text() if hasattr(self, "text") else ""
        super().setText(str(text or ""))
        if old != str(text or ""):
            try:
                self.currentTextChanged.emit(self.text())
                self.currentIndexChanged.emit(0)
            except Exception:
                pass


class UnitTrackingSlotCard(QFrame):
    """Sol panelde tek bir kuyruk no / seri no slotunu gösteren kompakt kart."""

    changed = Signal()

    def __init__(self, slot_no: int, comp_name: str, label: str = "Kuyruk No / Seri No", identifier: str = "", parent=None):
        super().__init__(parent)
        self._slot_no = int(slot_no or 0)
        self._comp_name = str(comp_name or "")
        self._label = str(label or "Kuyruk No / Seri No")
        self._is_duplicate = False
        self.setObjectName("unitSlotCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build(identifier)
        self._apply_state_style()

    def _build(self, identifier: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._slot_lbl = QLabel(f"#{self._slot_no:03d}")
        self._slot_lbl.setObjectName("unitSlotNo")
        self._slot_lbl.setFixedWidth(44)
        self._slot_lbl.setAlignment(Qt.AlignCenter)
        top.addWidget(self._slot_lbl, 0)

        self._comp_lbl = QLabel(self._comp_name.upper())
        self._comp_lbl.setObjectName("unitSlotComp")
        top.addWidget(self._comp_lbl, 1)

        self._status_lbl = QLabel("Eksik")
        self._status_lbl.setObjectName("unitSlotBadge")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        top.addWidget(self._status_lbl, 0)
        lay.addLayout(top)

        self._edit = QLineEdit()
        self._edit.setObjectName("unitSlotInput")
        self._edit.setPlaceholderText(self._label)
        self._edit.setText(str(identifier or ""))
        self._edit.textChanged.connect(self._on_changed)
        lay.addWidget(self._edit)

    def _on_changed(self, _text: str = ""):
        self._apply_state_style()
        self.changed.emit()

    def _status(self) -> str:
        if self.identifier() and self._is_duplicate:
            return "duplicate"
        if self.identifier():
            return "defined"
        return "missing"

    def _apply_state_style(self):
        status = self._status()
        if status == "duplicate":
            text = "Tekrar Var"; border = "#FCA5A5"; bg = "#FFF1F2"; badge_bg = "#FEE2E2"; badge_fg = "#B91C1C"
        elif status == "defined":
            text = "Tanımlandı"; border = "#86EFAC"; bg = "#F0FDF4"; badge_bg = "#DCFCE7"; badge_fg = "#15803D"
        else:
            text = "Eksik"; border = "#D8E2EE"; bg = "#FFFFFF"; badge_bg = "#F1F5F9"; badge_fg = "#64748B"
        self._status_lbl.setText(text)
        self.setStyleSheet(f"""
            QFrame#unitSlotCard {{ background:{bg}; border:1px solid {border}; border-radius:10px; }}
            QLabel#unitSlotNo {{ background:#EFF6FF; border:1px solid #BFDBFE; border-radius:7px; color:#0F3B82; font-weight:900; font-size:12px; padding:5px 0; }}
            QLabel#unitSlotComp {{ color:#64748B; font-size:10px; font-weight:900; background:transparent; }}
            QLabel#unitSlotBadge {{ background:{badge_bg}; color:{badge_fg}; border:1px solid {border}; border-radius:8px; font-size:10px; font-weight:900; padding:2px 8px; }}
            QLineEdit#unitSlotInput {{ background:#FFFFFF; border:1px solid #CBD5E1; border-radius:7px; padding:5px 8px; color:#0F172A; font-weight:700; }}
            QLineEdit#unitSlotInput:focus {{ border-color:#2563EB; }}
        """)

    def slot_no(self) -> int:
        return self._slot_no

    def identifier(self) -> str:
        return self._edit.text().strip()

    def set_identifier(self, value: str):
        self._edit.blockSignals(True)
        self._edit.setText(str(value or ""))
        self._edit.blockSignals(False)
        self._apply_state_style()

    def set_duplicate(self, duplicate: bool):
        if self._is_duplicate == bool(duplicate):
            return
        self._is_duplicate = bool(duplicate)
        self._apply_state_style()

    def matches(self, query: str, filter_key: str) -> bool:
        ident = self.identifier()
        status = self._status()
        if filter_key == "missing" and status != "missing":
            return False
        if filter_key == "defined" and status != "defined":
            return False
        if filter_key == "duplicate" and status != "duplicate":
            return False
        q = normalize_sheet_name(query)
        if not q:
            return True
        slot_text = f"{self._slot_no} {self._slot_no:03d} #{self._slot_no:03d}"
        return q in normalize_sheet_name(slot_text) or q in normalize_sheet_name(ident)

    def to_dict(self) -> dict:
        return {"slot_no": self._slot_no, "identifier": self.identifier(), "is_delivered": 0, "note": ""}


class UnitTrackingSidePanel(QFrame):
    """DeliveryDialog sol panelinde kuyruk no / seri no listesini yönetir."""

    changed = Signal()
    backRequested = Signal()
    clearRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._comp_name = ""
        self._label = "Kuyruk No / Seri No"
        self._filter = "all"
        self._cards: List[UnitTrackingSlotCard] = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._back_btn = QPushButton("← Bileşen Atama Durumu")
        self._back_btn.setObjectName("secondary")
        self._back_btn.setFlat(True)
        self._back_btn.setStyleSheet("text-align:left; color:#1D4ED8; font-weight:900; border:0; background:transparent;")
        self._back_btn.clicked.connect(self.backRequested.emit)
        top.addWidget(self._back_btn, 1)
        self._clear_btn = QPushButton("Temizle")
        self._clear_btn.setObjectName("danger")
        self._clear_btn.setMinimumHeight(32)
        self._clear_btn.clicked.connect(self._on_clear)
        top.addWidget(self._clear_btn, 0)
        outer.addLayout(top)

        self._title = QLabel("")
        self._title.setStyleSheet("font-weight:900; font-size:14px; color:#0F172A; background:transparent;")
        outer.addWidget(self._title)

        stats = QHBoxLayout(); stats.setSpacing(8)
        self._defined_card = self._stat_card("0/0", "Tanımlı", "#ECFDF5", "#86EFAC", "#047857")
        self._missing_card = self._stat_card("0", "Eksik", "#FFF7ED", "#FDBA74", "#C2410C")
        stats.addWidget(self._defined_card[0], 1)
        stats.addWidget(self._missing_card[0], 1)
        outer.addLayout(stats)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setStyleSheet("QProgressBar{border:0;background:#E2E8F0;border-radius:4px;} QProgressBar::chunk{background:#1D9A8A;border-radius:4px;}")
        outer.addWidget(self._progress)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Kuyruk No / Seri No veya slot ara...")
        self._search.textChanged.connect(self._apply_visibility)
        outer.addWidget(self._search)

        chips = QHBoxLayout(); chips.setSpacing(5)
        self._filter_buttons: Dict[str, QPushButton] = {}
        for key, label in (("all", "Tümü"), ("missing", "Eksik"), ("defined", "Tanımlı"), ("duplicate", "Tekrar")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._filter_buttons[key] = btn
            chips.addWidget(btn)
        chips.addStretch()
        outer.addLayout(chips)

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(self._modern_scrollbar_qss("QScrollArea"))
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 4, 4, 4)
        self._list.setSpacing(8)
        self._list.addStretch()
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)
        self._set_filter("all")


    @staticmethod
    def _modern_scrollbar_qss(root_selector: str = "QScrollArea") -> str:
        return f"""
{root_selector}{{background:transparent;border:0;}}
{root_selector} > QWidget > QWidget{{background:transparent;}}
{root_selector} QScrollBar:vertical{{
    width:11px;
    background:#F1F5F9;
    margin:4px 2px 4px 2px;
    border-radius:5px;
}}
{root_selector} QScrollBar::handle:vertical{{
    background:#B8C7D9;
    border-radius:5px;
    min-height:28px;
}}
{root_selector} QScrollBar::handle:vertical:hover{{background:#8FA8C6;}}
{root_selector} QScrollBar::add-line:vertical,
{root_selector} QScrollBar::sub-line:vertical{{height:0px; background:transparent; border:0;}}
{root_selector} QScrollBar::add-page:vertical,
{root_selector} QScrollBar::sub-page:vertical{{background:transparent;}}
{root_selector} QScrollBar:horizontal{{
    height:11px;
    background:#F1F5F9;
    margin:2px 4px 2px 4px;
    border-radius:5px;
}}
{root_selector} QScrollBar::handle:horizontal{{
    background:#B8C7D9;
    border-radius:5px;
    min-width:28px;
}}
{root_selector} QScrollBar::handle:horizontal:hover{{background:#8FA8C6;}}
{root_selector} QScrollBar::add-line:horizontal,
{root_selector} QScrollBar::sub-line:horizontal{{width:0px; background:transparent; border:0;}}
{root_selector} QScrollBar::add-page:horizontal,
{root_selector} QScrollBar::sub-page:horizontal{{background:transparent;}}
"""

    def _stat_card(self, value: str, caption: str, bg: str, border: str, fg: str):
        frame = QFrame(); frame.setObjectName("unitStatCard")
        frame.setStyleSheet(f"QFrame#unitStatCard{{background:{bg}; border:1px solid {border}; border-radius:9px;}}")
        lay = QVBoxLayout(frame); lay.setContentsMargins(8, 7, 8, 7); lay.setSpacing(1)
        val = QLabel(value); val.setAlignment(Qt.AlignCenter); val.setStyleSheet(f"font-weight:900; color:{fg}; font-size:13px; background:transparent;")
        cap = QLabel(caption); cap.setAlignment(Qt.AlignCenter); cap.setStyleSheet("font-weight:800; color:#64748B; font-size:10px; background:transparent;")
        lay.addWidget(val); lay.addWidget(cap)
        return frame, val, cap

    def _on_clear(self):
        for card in self._cards:
            card.set_identifier("")
        self._refresh_all()
        self.clearRequested.emit()
        self.changed.emit()

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
        self._style_filter_buttons()
        self._apply_visibility()

    def _style_filter_buttons(self):
        for key, btn in self._filter_buttons.items():
            if btn.isChecked():
                btn.setStyleSheet("QPushButton{background:#0F3B82;color:#0f172a;border:1px solid #0F3B82;border-radius:12px;padding:3px 9px;font-weight:900;font-size:11px;}")
            else:
                btn.setStyleSheet("QPushButton{background:white;color:#334155;border:1px solid #CBD5E1;border-radius:12px;padding:3px 9px;font-weight:800;font-size:11px;}")

    def set_component(self, comp_name: str, label: str, units: list):
        self._comp_name = str(comp_name or "")
        self._label = str(label or "Kuyruk No / Seri No")
        self._title.setText(f"{self._comp_name} {self._label} Listesi")
        self._search.setPlaceholderText(f"{self._label} veya slot ara...")
        self._rebuild_cards(units or [])

    def _rebuild_cards(self, units: list):
        while self._cards:
            card = self._cards.pop()
            self._list.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        for unit in sorted(units or [], key=lambda u: int(u.get("slot_no", 0) or 0)):
            card = UnitTrackingSlotCard(
                int(unit.get("slot_no", 0) or 0),
                self._comp_name,
                self._label,
                str(unit.get("identifier") or ""),
            )
            card.changed.connect(self._on_card_changed)
            self._list.insertWidget(self._list.count() - 1, card)
            self._cards.append(card)
        self._refresh_all()

    def _on_card_changed(self):
        self._refresh_all()
        self.changed.emit()

    def _refresh_all(self):
        self._check_duplicates()
        self._update_stats()
        self._apply_visibility()

    def _check_duplicates(self):
        counts: Dict[str, int] = {}
        for card in self._cards:
            ident = card.identifier()
            if ident:
                counts[normalize_sheet_name(ident)] = counts.get(normalize_sheet_name(ident), 0) + 1
        for card in self._cards:
            ident = card.identifier()
            card.set_duplicate(bool(ident and counts.get(normalize_sheet_name(ident), 0) > 1))

    def _counts(self) -> Tuple[int, int, int, int]:
        total = len(self._cards)
        defined = sum(1 for c in self._cards if c.identifier())
        duplicate = sum(1 for c in self._cards if c.identifier() and c._status() == "duplicate")
        missing = total - defined
        return total, defined, missing, duplicate

    def _update_stats(self):
        total, defined, missing, duplicate = self._counts()
        self._defined_card[1].setText(f"{defined}/{total}")
        self._missing_card[1].setText(str(missing))
        self._progress.setValue(int((defined / total) * 100) if total else 0)
        labels = {"all": f"Tümü {total}", "missing": f"Eksik {missing}", "defined": f"Tanımlı {defined}", "duplicate": f"Tekrar {duplicate}"}
        for key, text in labels.items():
            self._filter_buttons[key].setText(text)

    def _apply_visibility(self, *_args):
        query = self._search.text().strip()
        for card in self._cards:
            card.setVisible(card.matches(query, self._filter))

    def get_units(self) -> list:
        return [card.to_dict() for card in self._cards]

    def has_duplicates(self) -> bool:
        return any(card.identifier() and card._status() == "duplicate" for card in self._cards)

    def all_defined(self) -> bool:
        return all(card.identifier() for card in self._cards)


class ContractSharePopover(QFrame):
    """Compact contract-scoped sharing panel used inside ContractActionTabs popover."""

    _CARD_BASE = (
        "QPushButton#sharePermCard{"
        "background:#ffffff; color:#0b2b54; border:1px solid #D8E5F5;"
        "border-radius:12px; padding:8px 12px; font-size:12px; font-weight:700;"
        "text-align:left; min-height:54px;"
        "}"
        "QPushButton#sharePermCard:hover{"
        "background:#F4F8FF; border-color:#93C5FD;"
        "}"
    )
    _CARD_ACTIVE = (
        "QPushButton#sharePermCard{"
        "background:#EFF6FF; color:#1D4ED8; border:1px solid #60A5FA;"
        "border-radius:12px; padding:8px 12px; font-size:12px; font-weight:800;"
        "text-align:left; min-height:54px;"
        "}"
    )

    def __init__(self, owner: "ContractWorkWindow", parent=None):
        super().__init__(parent)
        self.owner = owner
        self._share_mode_value = "goruntule"
        self.setObjectName("contractSharePanel")
        self.setMinimumWidth(336)
        self.setStyleSheet(
            "QFrame#contractSharePanel{background:#F8FBFF;border:1px solid #BFDBFE;border-radius:14px;}"
            "QLabel{background:transparent;border:0;}"
            "QPushButton#shareCloseButton{background:transparent;color:#64748B;border:0;border-radius:8px;font-size:16px;font-weight:900;min-width:28px;min-height:28px;}"
            "QPushButton#shareCloseButton:hover{background:#EAF3FF;color:#1D4ED8;}"
            "QPushButton#shareCreateButton{background:#2563eb;color:#fff;border:0;border-radius:10px;"
            "padding:7px 16px;font-size:12px;font-weight:800;min-height:34px;}"
            "QPushButton#shareCreateButton:hover{background:#1d4ed8;}"
            "QLabel#sharePreview{background:#ffffff;color:#1e3a8a;border:1px solid #bfdbfe;"
            "border-radius:9px;padding:8px 10px;font-family:Consolas,monospace;font-size:11px;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Sözleşme Paylaşımı")
        title.setStyleSheet("color:#10233d;font-size:14px;font-weight:900;")
        close_btn = QPushButton("×")
        close_btn.setObjectName("shareCloseButton")
        close_btn.clicked.connect(self.owner.close_side_meta_popover)
        header.addWidget(title, 1)
        header.addWidget(close_btn, 0, Qt.AlignRight | Qt.AlignVCenter)
        lay.addLayout(header)

        info = QLabel("Sadece bu sözleşmeyi içeren bağımsız STS dosyası oluştur.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#475569;font-size:11px;")
        lay.addWidget(info)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        cards_row.setContentsMargins(0, 2, 0, 2)

        self._btn_view = QPushButton("👁  Görüntüle\nSadece okuma")
        self._btn_view.setObjectName("sharePermCard")
        self._btn_view.setCursor(Qt.PointingHandCursor)

        self._btn_edit = QPushButton("✏  Düzenle\nDüzenleme izni")
        self._btn_edit.setObjectName("sharePermCard")
        self._btn_edit.setCursor(Qt.PointingHandCursor)

        self._btn_view.clicked.connect(lambda: self._set_mode("goruntule"))
        self._btn_edit.clicked.connect(lambda: self._set_mode("duzenle"))

        cards_row.addWidget(self._btn_view, 1)
        cards_row.addWidget(self._btn_edit, 1)
        lay.addLayout(cards_row)

        self.preview = QLabel("")
        self.preview.setObjectName("sharePreview")
        lay.addWidget(self.preview)

        btn = QPushButton("Paylaşım Dosyası Oluştur")
        btn.setObjectName("shareCreateButton")
        btn.clicked.connect(self.create_share_file)
        lay.addWidget(btn, 0, Qt.AlignRight)

        self._merge_btn = QPushButton("Paylaşım Değişikliklerini Birleştir")
        self._merge_btn.setObjectName("shareCreateButton")
        self._merge_btn.setToolTip("Geri gelen V2 paylaşım .sts dosyasındaki değişiklikleri bu STS ile birleştir.")
        self._merge_btn.clicked.connect(self.merge_share_file)
        lay.addWidget(self._merge_btn, 0, Qt.AlignRight)

        self._set_mode("goruntule")
        self.refresh_actions()

    def _set_mode(self, mode: str):
        self._share_mode_value = mode
        self._btn_view.setStyleSheet(
            self._CARD_ACTIVE if mode == "goruntule" else self._CARD_BASE
        )
        self._btn_edit.setStyleSheet(
            self._CARD_ACTIVE if mode == "duzenle" else self._CARD_BASE
        )
        self.update_preview()

    def share_mode(self) -> str:
        return self._share_mode_value

    def filename(self) -> str:
        no = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(getattr(self.owner.ci, "no", "") or "sozlesme")).strip("-._") or "sozlesme"
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        mode = "edit" if self.share_mode() == "duzenle" else "view"
        return f"STS-{no}__share-{mode}__{stamp}.sts"

    def update_preview(self):
        self.preview.setText(self.filename())

    def create_share_file(self):
        self.owner.create_contract_share_file(self.share_mode(), self.filename())

    def refresh_actions(self):
        checker = getattr(self.owner, "can_show_share_merge_action", None)
        can_show = bool(checker()) if callable(checker) else True
        self._merge_btn.setVisible(can_show)
        self._merge_btn.setEnabled(can_show)

    def merge_share_file(self):
        handler = getattr(self.owner, "merge_returned_share_file", None)
        if callable(handler):
            handler()


class BadgeTabButton(QFrame):
    """Contract meta tab with a fixed top-right badge anchor.

    Badge geometry is intentionally independent from the text layout.  Only the
    text changes when the count changes, so active/passive state and 0/1/9/10/99
    counts cannot push the badge or the button content around.
    """

    clicked = Signal(bool)

    BADGE_W = 28
    BADGE_H = 20

    def __init__(self, icon: str, text: str, count: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._checked = False
        self._text = str(text or "")
        self._has_badge = count is not None
        self.setObjectName("badgeTabButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(42)
        self.setMinimumWidth(128)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        # Reserve a stable right-side anchor area for the absolute badge.
        lay.setContentsMargins(14, 7, 38 if self._has_badge else 14, 7)
        lay.setSpacing(8)

        self.icon_lbl = QLabel(str(icon or ""), self)
        self.icon_lbl.setObjectName("badgeTabIcon")
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setFixedWidth(18)
        lay.addWidget(self.icon_lbl, 0, Qt.AlignVCenter)

        self.text_lbl = QLabel(self._text, self)
        self.text_lbl.setObjectName("badgeTabText")
        self.text_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.text_lbl.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        lay.addWidget(self.text_lbl, 1, Qt.AlignVCenter)

        self.badge = QLabel("0" if count is None else str(count), self)
        self.badge.setObjectName("badgeTabCount")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(self.BADGE_W, self.BADGE_H)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.badge.setVisible(self._has_badge)
        self._apply_style()
        self._position_badge()

    def setChecked(self, checked: bool):
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self._apply_style()
        self._position_badge()

    def isChecked(self) -> bool:
        return self._checked

    def setCount(self, count: int):
        self._has_badge = True
        self.badge.setVisible(True)
        self.badge.setText(str(count))
        # Fixed badge width keeps 0/1/9/10/99 visually anchored.
        self._position_badge()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_badge()

    def _position_badge(self):
        if not hasattr(self, "badge"):
            return
        x = max(4, self.width() - self.BADGE_W - 8)
        y = 5
        self.badge.setGeometry(x, y, self.BADGE_W, self.BADGE_H)
        self.badge.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(False)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def _apply_style(self):
        if self._checked:
            bg = "#EFF6FF"; border = "#60A5FA"; fg = "#1D4ED8"
        else:
            bg = "#FFFFFF"; border = "#D8E5F5"; fg = "#0F2747"
        self.setStyleSheet(f"""
            QFrame#badgeTabButton {{
                background:{bg};
                border:1px solid {border};
                border-top-left-radius:0px;
                border-top-right-radius:0px;
                border-bottom-left-radius:12px;
                border-bottom-right-radius:12px;
            }}
            QFrame#badgeTabButton:hover {{ background:#F4F8FF; border-color:#93C5FD; }}
            QLabel#badgeTabIcon {{ background:transparent; color:{fg}; border:0; font-size:15px; }}
            QLabel#badgeTabText {{ background:transparent; color:{fg}; border:0; font-size:12px; font-weight:700; }}
            QLabel#badgeTabCount {{
                background:#DBEAFE;
                color:#2563EB;
                border:1px solid #93C5FD;
                border-radius:10px;
                padding:0px;
                font-size:10px;
                font-weight:900;
            }}
        """)


class ContractActionTabs(QFrame):
    """Contract-level hanging tabs anchored under the header bar."""

    def __init__(self, owner: "ContractWorkWindow", parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setObjectName("contractActionTabs")

    def open_tags(self):
        self.owner.toggle_side_meta_popover("tags")

    def open_files(self):
        self.owner.toggle_side_meta_popover("files")

    def open_share(self):
        self.owner.toggle_side_meta_popover("share")
