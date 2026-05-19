# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QHeaderView,
    QSizePolicy,
)

from src.models.app_models import ContractInfo, DeliveryInfo, SystemInfo
from src.services.excel_store import ExcelStore


TR_MONTHS_SHORT = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def parse_iso_date(text: str) -> Optional[date]:
    text = str(text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def as_number(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def fmt_num(value) -> str:
    try:
        number = float(value or 0)
        return str(int(number)) if number == int(number) else str(round(number, 2))
    except Exception:
        return str(value or "")


def norm_tr(text: str) -> str:
    t = str(text or "").strip().lower()
    return t.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")


def status_kind(status: str) -> str:
    norm = norm_tr(status)
    if "teslim edildi" in norm or "tamam" in norm:
        return "done"
    if "hazirlaniyor" in norm or "parcali" in norm or "devam" in norm:
        return "progress"
    return "new"


def status_label(status: str) -> str:
    raw = str(status or "").strip()
    if raw:
        return raw
    return "Başlanmadı"


def display_date(value: str) -> str:
    d = parse_iso_date(value)
    if not d:
        return "—"
    return f"{d.day} {TR_MONTHS_SHORT[d.month - 1]} {d.year}"



def delivery_timing_text(deadline: Optional[date], acceptance: Optional[date]) -> str:
    if not deadline:
        return "—"
    if acceptance:
        diff = (acceptance - deadline).days
        if diff < 0:
            return f"{abs(diff)} gün erken teslim edildi"
        if diff > 0:
            return f"{diff} gün geç teslim edildi"
        return "Zamanında teslim edildi"
    return str((deadline - date.today()).days)

def iso_display(value: str) -> str:
    d = parse_iso_date(value)
    if not d:
        return "—"
    return d.strftime("%d.%m.%Y")


@dataclass
class SummaryContext:
    key: str
    label: str
    button_label: str
    source: str
    item: dict
    ci: Optional[ContractInfo]
    systems: List[SystemInfo]
    deliveries: Dict[str, List[DeliveryInfo]]


class ContractSummaryDialog(QDialog):
    """Ana sayfadaki özet ikonundan açılan sözleşme/sistem özet ekranı."""

    def __init__(self, store: ExcelStore, item: dict, parent=None, detail_handler: Optional[Callable[[dict], bool]] = None):
        super().__init__(parent)
        self.store = store
        self.item = dict(item or {})
        self.detail_handler = detail_handler
        self.contexts: List[SummaryContext] = []
        self.selected_scope = "all"
        self.selected_system_key: Optional[Tuple[str, str]] = None
        self.scope_buttons: Dict[str, QPushButton] = {}
        self.system_buttons: Dict[Tuple[str, str], QFrame] = {}
        self.setWindowTitle("Sözleşme Özeti")
        self.setModal(False)
        # İlk açılışta tablolar yatay kaydırmaya düşmeden okunabilsin.
        self.resize(1220, 850)
        self.setMinimumSize(1120, 790)
        self.setStyleSheet(self._style())
        self.load_data()
        self.selected_scope = self._initial_scope_from_item()
        self.build()
        self.refresh_view()

    def _style(self) -> str:
        return """
            QDialog { background:#eef3f8; }
            QLabel { background:transparent; color:#102033; font-family:'Segoe UI', Arial; }
            QFrame#summaryTop { background:#172f52; border-top-left-radius:12px; border-top-right-radius:12px; }
            QLabel#summaryAppTitle { color:#8fa8c6; font-size:12px; font-weight:700; letter-spacing:2px; }
            QFrame#metaCell { background:#172f52; border:0; }
            QLabel#metaTitle { color:#8fa8c6; font-size:10px; font-weight:900; letter-spacing:1px; }
            QLabel#metaValue { color:#ffffff; font-size:18px; font-weight:900; }
            QLabel#metaValueBig { color:#ffffff; font-size:26px; font-weight:900; }
            QComboBox { background:#ffffff; color:#102033; border:1px solid #c8d7e8; border-radius:8px; padding:0 10px; min-height:34px; font-size:13px; }
            QComboBox::drop-down { border:0; width:22px; }
            QLabel#statusPillDone { background:#e9f9f0; color:#0d8a42; border-radius:14px; padding:8px 13px; font-size:12px; font-weight:900; }
            QLabel#statusPillProgress { background:#fff2e8; color:#ff7a1a; border-radius:14px; padding:8px 13px; font-size:12px; font-weight:900; }
            QLabel#statusPillNew { background:#fff2e8; color:#ff7a1a; border-radius:14px; padding:8px 13px; font-size:12px; font-weight:900; }
            QFrame#summaryCard { background:#ffffff; border:1px solid #dce6f1; border-radius:10px; }
            QFrame#topSummaryCard { background:#e8eef5; border:1px solid #dce6f1; border-radius:10px; }
            QFrame#summaryPart { background:transparent; border:0; }
            QFrame#panelCard { background:#ffffff; border:1px solid #dce6f1; border-radius:13px; }
            QLabel#panelTitle { color:#0d2340; font-size:13px; font-weight:950; letter-spacing:1px; }
            QLabel#scopeChip { background:#eef4fb; color:#365574; border:1px solid #d7e4f2; border-radius:11px; padding:5px 10px; font-size:11px; font-weight:800; }
            QLabel#miniLabel { color:#6b7a90; font-size:8px; font-weight:900; letter-spacing:.7px; }
            QLabel#miniSub { color:#6b7a90; font-size:9px; }
            QLabel#miniValueBlue { color:#2563eb; font-size:20px; font-weight:950; }
            QLabel#miniValueGreen { color:#19b65b; font-size:20px; font-weight:950; }
            QLabel#miniValueOrange { color:#ff7a1a; font-size:20px; font-weight:950; }
            QLabel#miniValueRed { color:#ef3e52; font-size:20px; font-weight:950; }
            QLabel#dateLabel { color:#6b7a90; font-size:8px; font-weight:900; letter-spacing:.8px; }
            QLabel#dateValueRed { color:#ef3e52; font-size:11px; font-weight:950; }
            QLabel#dateValueOrange { color:#ff7a1a; font-size:11px; font-weight:950; }
            QLabel#dateValueGreen { color:#19b65b; font-size:11px; font-weight:950; }
            /* Alternatif 3 - sadece ara özet kutucukları */
            QFrame#alt3Overview { background:transparent; border:0; }
            QFrame#alt3SideCard, QFrame#alt3WideCard {
                background:#ffffff;
                border:1px solid #d8e4f0;
                border-radius:12px;
            }
            QLabel#alt3Title {
                color:#0b2f6b;
                font-size:11px;
                font-weight:950;
                letter-spacing:.5px;
            }
            QFrame#alt3StackMetric {
                background:transparent;
                border-bottom:1px solid #edf2f7;
            }
            QLabel#alt3StackText {
                color:#475569;
                font-size:11px;
                font-weight:850;
            }
            QLabel#alt3ValueBlue { color:#2563eb; font-size:20px; font-weight:950; }
            QLabel#alt3ValueRed { color:#ef3e52; font-size:20px; font-weight:950; }
            QLabel#alt3ValueOrange { color:#ff7a1a; font-size:20px; font-weight:950; }
            QLabel#alt3ValueGreen { color:#19b65b; font-size:20px; font-weight:950; }
            QFrame#alt3DateTileRed, QFrame#alt3DateTileOrange, QFrame#alt3DateTileGreen {
                background:#f8fbff;
                border:1px solid #d8e4f0;
                border-radius:12px;
            }
            QFrame#alt3DateTileRed { border-top:4px solid #ef3e52; }
            QFrame#alt3DateTileOrange { border-top:4px solid #ff7a1a; }
            QFrame#alt3DateTileGreen { border-top:4px solid #19b65b; }
            QLabel#alt3TileTitle {
                color:#536b8e;
                font-size:9px;
                font-weight:950;
                letter-spacing:.4px;
            }
            QLabel#alt3TileValueRed { color:#dc2626; font-size:12px; font-weight:950; }
            QLabel#alt3TileValueOrange { color:#ea580c; font-size:12px; font-weight:950; }
            QLabel#alt3TileValueGreen { color:#16a34a; font-size:12px; font-weight:950; }
            QFrame#alt3AlertBox {
                background:#ffffff;
                border:1px solid #d8e4f0;
                border-radius:12px;
            }
            QLabel#alt3AlertNoOrange {
                background:#fff7ed;
                color:#ff7a1a;
                border-radius:10px;
                font-size:20px;
                font-weight:950;
            }
            QLabel#alt3AlertNoRed {
                background:#fff1f2;
                color:#ef3e52;
                border-radius:10px;
                font-size:20px;
                font-weight:950;
            }
            QLabel#alt3AlertTitle { color:#0f172a; font-size:11px; font-weight:950; }
            QLabel#alt3AlertSub { color:#64748b; font-size:10px; font-weight:750; }
            QFrame#dateChip { background:#ffffff; border:1px solid #dce6f1; border-radius:8px; }
            QFrame#alertBox { background:#fff0f2; border:1px solid #fecaca; border-radius:8px; }
            QLabel#alertText { color:#ef3e52; font-size:11px; font-weight:900; }
            QTableWidget { background:#ffffff; border:0; gridline-color:#edf2f7; selection-background-color:transparent; font-size:12px; color:#102033; }
            QTableWidget::item { padding:8px; border-bottom:1px solid #edf2f7; }
            QHeaderView::section { background:#f5f8fb; color:#5c6c82; border:0; border-bottom:1px solid #edf2f7; padding:10px; font-size:10px; font-weight:900; }
            QFrame#footer { background:#f8fbfe; border-top:1px solid #dbe6f2; }
            QPushButton#secondary { background:#ffffff; color:#0d2340; border:1px solid #cbd8e7; border-radius:9px; padding:0 18px; min-height:38px; font-size:13px; font-weight:900; }
        """

    def load_data(self):
        self.contexts = []
        platform = str(self.item.get("platform", "") or "")
        no = str(self.item.get("no", "") or "")
        if not platform or not no:
            return
        family = [dict(row) for row in self.store.list_main_contracts(platform) if str(row.get("no", "") or "").strip() == no]
        if not family:
            family = [dict(self.item)]
        family.sort(key=lambda row: (0 if self.is_main_type(row.get("type", "")) else 1, self.sd_sort_key(row.get("type", ""))))
        for row in family:
            ci, systems, deliveries = self.safe_load_context(row)
            ctype = str(row.get("type", "") or (ci.contract_type if ci else "") or "")
            key = "main" if self.is_main_type(ctype) else ctype.strip().upper()
            label = "Ana Sözleşme" if self.is_main_type(ctype) else ctype.strip().upper()
            button_label = "Ana Söz." if self.is_main_type(ctype) else ctype.strip().upper()
            self.contexts.append(SummaryContext(key, label, button_label, key, row, ci, list(systems or []), dict(deliveries or {})))

    def safe_load_context(self, row: dict):
        try:
            return self.store.load_contract_structure(
                str(row.get("platform", "") or ""),
                str(row.get("no", "") or ""),
                start_row=int(row.get("row", 0) or 0) or None,
            )
        except Exception:
            return None, [], {}

    def _initial_scope_from_item(self) -> str:
        if len(self.contexts) <= 1:
            return self.contexts[0].key if self.contexts else "all"
        # Özet ilk açıldığında tüm sözleşme ailesi görülsün; kullanıcı isterse Tür alanından daraltır.
        return "all"

    def is_main_type(self, value: str) -> bool:
        return norm_tr(value) == norm_tr("Ana Sözleşme")

    def sd_sort_key(self, value: str):
        m = re.match(r"^SD-(\d+)$", str(value or "").strip().upper())
        return int(m.group(1)) if m else 999

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_topbar(), 0)

        self.body = QWidget()
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(20, 8, 20, 8)
        body_lay.setSpacing(8)

        self.alert = self.build_alert()
        body_lay.addWidget(self.alert, 0)

        # Sadece lacivert üst başlık ile alt tablolar arasındaki özet kutucukları değişti.
        # Üst koyu lacivert alan ve alttaki Sözleşmeler/Bileşen Durumu kartları aynı kalır.
        body_lay.addWidget(self.build_alt3_overview(), 0)

        main_grid = QGridLayout()
        main_grid.setHorizontalSpacing(8)
        main_grid.setVerticalSpacing(8)
        self.systems_card = self.build_systems_card()
        self.components_card = self.build_components_card()
        main_grid.addWidget(self.systems_card, 0, 0)
        main_grid.addWidget(self.components_card, 0, 1)
        main_grid.setColumnMinimumWidth(0, 620)
        main_grid.setColumnMinimumWidth(1, 340)
        main_grid.setColumnStretch(0, 2)
        main_grid.setColumnStretch(1, 1)
        body_lay.addLayout(main_grid, 1)
        root.addWidget(self.body, 1)
        root.addWidget(self.build_footer(), 0)

    def build_alt3_overview(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("alt3Overview")

        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        systems_card = self.alt3_side_card("SİSTEMLER")
        self.system_total_val = self.alt3_stack_metric(systems_card._body_lay, "Genel toplam", "Blue")
        self.system_new_val = self.alt3_stack_metric(systems_card._body_lay, "Başlanmadı", "Red")
        self.system_progress_val = self.alt3_stack_metric(systems_card._body_lay, "Devam", "Orange")
        self.system_done_val = self.alt3_stack_metric(systems_card._body_lay, "Tamamlandı", "Green")

        middle = QFrame()
        middle.setObjectName("alt3WideCard")
        middle_lay = QVBoxLayout(middle)
        middle_lay.setContentsMargins(12, 8, 12, 8)
        middle_lay.setSpacing(6)

        title = QLabel("TARİH VE TESLİM DURUMU")
        title.setObjectName("alt3Title")
        middle_lay.addWidget(title)

        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.setSpacing(8)
        self.termin_value = self.alt3_date_tile(date_row, "TERMİN", "Red")
        self.days_value = self.alt3_date_tile(date_row, "KALAN GÜN", "Orange")
        self.acceptance_value = self.alt3_date_tile(date_row, "KABUL TARİHİ", "Green")
        middle_lay.addLayout(date_row)

        alert_row = QHBoxLayout()
        alert_row.setContentsMargins(0, 0, 0, 0)
        alert_row.setSpacing(8)
        self.critical_value = self.alt3_alert_tile(
            alert_row,
            title="Yaklaşan termin",
            sub="60 gün içinde takip gerektiren kayıt.",
            color="Orange",
        )
        self.overdue_value = self.alt3_alert_tile(
            alert_row,
            title="Geciken termin",
            sub="Süresi geçmiş termin.",
            color="Red",
        )
        middle_lay.addLayout(alert_row)

        accepts_card = self.alt3_side_card("KABULLER")
        self.accept_total_val = self.alt3_stack_metric(accepts_card._body_lay, "Toplam", "Blue")
        self.accept_new_val = self.alt3_stack_metric(accepts_card._body_lay, "Başlanmadı", "Red")
        self.accept_progress_val = self.alt3_stack_metric(accepts_card._body_lay, "Devam", "Orange")
        self.accept_done_val = self.alt3_stack_metric(accepts_card._body_lay, "Tamam", "Green")

        systems_card.setMinimumWidth(205)
        accepts_card.setMinimumWidth(205)
        lay.addWidget(systems_card, 0)
        lay.addWidget(middle, 1)
        lay.addWidget(accepts_card, 0)
        return wrap

    def alt3_side_card(self, title_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("alt3SideCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("alt3Title")
        lay.addWidget(title)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        lay.addLayout(body, 1)

        card._body_lay = body
        return card

    def alt3_stack_metric(self, parent_lay: QVBoxLayout, label: str, color: str) -> QLabel:
        row = QFrame()
        row.setObjectName("alt3StackMetric")

        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)

        t = QLabel(label)
        t.setObjectName("alt3StackText")

        v = QLabel("0")
        v.setObjectName(f"alt3Value{color}")
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay.addWidget(t, 1)
        lay.addWidget(v, 0)
        parent_lay.addWidget(row)
        return v

    def alt3_date_tile(self, parent_lay: QHBoxLayout, title_text: str, color: str) -> QLabel:
        tile = QFrame()
        tile.setObjectName(f"alt3DateTile{color}")
        tile.setMinimumHeight(58)
        tile.setMaximumHeight(66)

        lay = QVBoxLayout(tile)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(3)

        t = QLabel(title_text)
        t.setObjectName("alt3TileTitle")

        v = QLabel("—")
        v.setObjectName(f"alt3TileValue{color}")
        v.setWordWrap(True)

        lay.addWidget(t)
        lay.addWidget(v, 1)
        parent_lay.addWidget(tile, 1)
        return v

    def alt3_alert_tile(self, parent_lay: QHBoxLayout, title: str, sub: str, color: str) -> QLabel:
        box = QFrame()
        box.setObjectName("alt3AlertBox")
        box.setMinimumHeight(46)
        box.setMaximumHeight(54)

        lay = QHBoxLayout(box)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(7)

        num = QLabel("0")
        num.setObjectName("alt3AlertNoRed" if color == "Red" else "alt3AlertNoOrange")
        num.setAlignment(Qt.AlignCenter)
        num.setFixedSize(32, 32)

        text_lay = QVBoxLayout()
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(1)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("alt3AlertTitle")

        sub_lbl = QLabel(sub)
        sub_lbl.setObjectName("alt3AlertSub")
        sub_lbl.setWordWrap(True)

        text_lay.addWidget(title_lbl)
        text_lay.addWidget(sub_lbl)
        lay.addWidget(num, 0)
        lay.addLayout(text_lay, 1)

        parent_lay.addWidget(box, 1)
        return num

    def _shadow(self, widget: QWidget):
        # Qt stylesheets do not provide CSS box-shadow; subtle borders and spacing mirror the supplied mock-up.
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return widget

    def build_topbar(self) -> QFrame:
        top = QFrame()
        top.setObjectName("summaryTop")
        top.setFixedHeight(128)
        lay = QVBoxLayout(top)
        lay.setContentsMargins(24, 16, 24, 14)
        lay.setSpacing(12)
        app_title = QLabel("KONFİGÜRASYON YÖNETİMİ SÖZLEŞME TAKİP SİSTEMİ")
        app_title.setObjectName("summaryAppTitle")
        lay.addWidget(app_title)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        self.no_value = QLabel("—")
        self.platform_value = QLabel("—")
        self.user_value = QLabel("—")
        self.status_value = QLabel("—")
        row.addWidget(self.meta_cell("SÖZLEŞME NO", self.no_value, big=True), 100)
        row.addWidget(self.meta_cell("PLATFORM", self.platform_value), 105)
        row.addWidget(self.type_cell(), 110)
        row.addWidget(self.meta_cell("KULLANICI", self.user_value), 100)
        row.addWidget(self.status_cell(), 105)
        lay.addLayout(row, 1)
        return top

    def meta_cell(self, title: str, value_label: QLabel, big: bool = False) -> QFrame:
        cell = QFrame()
        cell.setObjectName("metaCell")
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("metaTitle")
        value_label.setObjectName("metaValueBig" if big else "metaValue")
        lay.addWidget(t)
        lay.addWidget(value_label)
        lay.addStretch()
        return cell

    def type_cell(self) -> QFrame:
        cell = QFrame()
        cell.setObjectName("metaCell")
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        t = QLabel("TÜR")
        t.setObjectName("metaTitle")
        lay.addWidget(t)
        self.scope_combo = QComboBox()
        self.scope_combo.setFixedWidth(145)
        if len(self.contexts) > 1:
            self.scope_combo.addItem("Tümü", "all")
        for ctx in self.contexts:
            self.scope_combo.addItem(ctx.button_label, ctx.key)
        self.scope_combo.currentIndexChanged.connect(lambda _i: self.set_scope(str(self.scope_combo.currentData() or "all")))
        lay.addWidget(self.scope_combo, 0, Qt.AlignLeft)
        lay.addStretch()
        return cell

    def status_cell(self) -> QFrame:
        cell = QFrame()
        cell.setObjectName("metaCell")
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        t = QLabel("DURUM")
        t.setObjectName("metaTitle")
        self.status_pill = QLabel("—")
        self.status_pill.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(self.status_pill, 0, Qt.AlignLeft)
        lay.addStretch()
        return cell

    def build_alert(self) -> QFrame:
        f = QFrame()
        f.setObjectName("alertBox")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(10, 5, 10, 5)
        icon = QLabel("!")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(17, 17)
        icon.setStyleSheet("QLabel{background:#ef3e52;color:#ffffff;border-radius:8px;font-size:11px;font-weight:900;}")
        self.alert_text = QLabel("")
        self.alert_text.setObjectName("alertText")
        lay.addWidget(icon)
        lay.addWidget(self.alert_text, 1)
        f.hide()
        return f

    def _mini_text_block(self, label: str, sub: str, color: str = "") -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lbl = QLabel(label)
        lbl.setObjectName("miniLabel")
        if color:
            lbl.setStyleSheet(f"color:{self._color_hex(color)};")
        lbl.setAlignment(Qt.AlignCenter)
        s = QLabel(sub)
        s.setObjectName("miniSub")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        lay.addWidget(s)
        return box

    def _color_hex(self, color: str) -> str:
        return {"Blue": "#2563eb", "Green": "#19b65b", "Orange": "#ff7a1a", "Red": "#ef3e52"}.get(color, "#6b7a90")

    def build_split_card(self, parts: List[Tuple[str, str, str]]) -> Tuple[QLabel, QLabel, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("topSummaryCard")
        card.setMinimumHeight(44)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(4, 5, 4, 5)
        lay.setSpacing(0)
        values: List[QLabel] = []
        for idx, (label, sub, color) in enumerate(parts):
            part = QFrame()
            part.setObjectName("summaryPart")
            part.setStyleSheet("QFrame#summaryPart{background:transparent;border-right:1px solid #d5e0ec;}" if idx < len(parts) - 1 else "QFrame#summaryPart{background:transparent;border:0;}")
            pl = QVBoxLayout(part)
            pl.setContentsMargins(4, 0, 4, 0)
            pl.setSpacing(0)
            val = QLabel("0")
            val.setObjectName(f"miniValue{color}")
            val.setAlignment(Qt.AlignCenter)
            pl.addWidget(val)
            pl.addWidget(self._mini_text_block(label, sub, color))
            lay.addWidget(part, 1)
            values.append(val)
        self.system_summary_card = card
        return values[0], values[1], values[2], values[3]

    def build_mini_card(self, label: str, sub: str, color: str, compact: bool = False) -> QLabel:
        card = QFrame()
        card.setObjectName("topSummaryCard")
        card.setMinimumHeight(34 if compact else 44)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(8, 3 if compact else 5, 8, 3 if compact else 5)
        lay.setSpacing(8)
        value = QLabel("0")
        value.setObjectName(f"miniValue{color}")
        if compact:
            value.setStyleSheet(f"font-size:18px;color:{self._color_hex(color)};font-weight:950;")
        lay.addWidget(value)
        lay.addWidget(self._mini_text_block(label, sub), 1)
        self.critical_card = card
        return value

    def build_date_chip(self, row: QHBoxLayout, title: str, color: str, stretch: int) -> QLabel:
        chip = QFrame()
        chip.setObjectName("dateChip")
        chip.setMinimumHeight(34)
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(6)
        bar = QFrame()
        bar.setFixedSize(3, 20)
        bar.setStyleSheet(f"QFrame{{background:{self._color_hex(color)};border-radius:1px;}}")
        text_box = QWidget()
        tl = QVBoxLayout(text_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        lbl = QLabel(title)
        lbl.setObjectName("dateLabel")
        val = QLabel("—")
        val.setObjectName(f"dateValue{color}")
        tl.addWidget(lbl)
        tl.addWidget(val)
        lay.addWidget(bar)
        lay.addWidget(text_box, 1)
        row.addWidget(chip, stretch)
        return val

    def build_count_card(self, kind: str) -> QFrame:
        # Kept for compatibility with older callers; the supplied design now uses compact split cards.
        value = self.build_mini_card("Geciken" if kind == "overdue" else "Yaklaşan", "termin" if kind == "overdue" else "60 gün", "Red" if kind == "overdue" else "Orange")
        if kind == "overdue":
            self.overdue_value = value
        else:
            self.critical_value = value
        return self.critical_card

    def build_date_card(self) -> QFrame:
        f = QFrame()
        return f

    def date_metric(self, row: QHBoxLayout, title: str, value: str, color: str) -> QLabel:
        return self.build_date_chip(row, title, color, 1)

    def build_systems_card(self) -> QFrame:
        f = self.card("SİSTEM BİLGİSİ")
        self.system_card_title = f._title_label
        self.system_count_label = QLabel("0 sistem")
        self.system_count_label.setObjectName("scopeChip")
        f._head.addWidget(self.system_count_label)
        self.system_info_table = QTableWidget(0, 5)
        self.setup_table(self.system_info_table, ["SİSTEM", "DURUM", "TERMİN TARİHİ", "KABUL TARİHİ", "KABUL SAYISI"])
        self.system_info_table.setMinimumHeight(430)
        self.system_info_table.setMinimumWidth(620)
        self.system_info_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._apply_info_table_widths(contract_view=False)
        self.card_body(f).addWidget(self.system_info_table, 1)
        return f

    def status_metric(self, row: QHBoxLayout, title: str, color: str) -> QLabel:
        f = QFrame()
        f.setObjectName(f"statusMetric{color}")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(1)
        v = QLabel("0")
        v.setObjectName(f"statusMetric{color}Num")
        v.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setObjectName("statusMetricText")
        t.setAlignment(Qt.AlignCenter)
        if color == "New":
            t.setStyleSheet("color:#ea580c;")
        elif color == "Progress":
            t.setStyleSheet("color:#0891b2;")
        else:
            t.setStyleSheet("color:#16a34a;")
        lay.addWidget(v)
        lay.addWidget(t)
        row.addWidget(f, 1)
        return v

    def build_components_card(self) -> QFrame:
        f = self.card("BİLEŞEN DURUMU")
        self.component_scope_label = QLabel("—")
        self.component_scope_label.setObjectName("scopeChip")
        f._head.addWidget(self.component_scope_label)
        self.component_table = QTableWidget(0, 4)
        self.setup_table(self.component_table, ["BİLEŞEN", "PLAN", "TESLİM", "KALAN"])
        self.component_table.setMinimumHeight(430)
        self.component_table.setMinimumWidth(340)
        self.component_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.component_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        component_widths = [58, 62, 54]
        for c, width in enumerate(component_widths, start=1):
            self.component_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Fixed)
            self.component_table.setColumnWidth(c, width)
        self.card_body(f).addWidget(self.component_table, 1)
        return f

    def build_deliveries_card(self) -> QFrame:
        f = self.card("TESLİMATLAR / KABULLER")
        self.delivery_scope_label = QLabel("—")
        self.delivery_scope_label.setObjectName("smallMuted")
        f._head.addWidget(self.delivery_scope_label)
        self.delivery_metric_row = QHBoxLayout()
        self.del_new_val = self.status_metric(self.delivery_metric_row, "BAŞLANMADI", "New")
        self.del_progress_val = self.status_metric(self.delivery_metric_row, "HAZIRLANIYOR", "Progress")
        self.del_done_val = self.status_metric(self.delivery_metric_row, "TESLİM EDİLDİ", "Done")
        self.card_body(f).addLayout(self.delivery_metric_row)
        self.delivery_list_host = QWidget()
        self.delivery_list_lay = QVBoxLayout(self.delivery_list_host)
        self.delivery_list_lay.setContentsMargins(0, 0, 0, 0)
        self.delivery_list_lay.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.delivery_list_host)
        self.card_body(f).addWidget(scroll, 1)
        return f

    def card(self, title: str) -> QFrame:
        f = QFrame()
        f.setObjectName("panelCard")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setContentsMargins(14, 12, 14, 0)
        t = QLabel(title)
        t.setObjectName("panelTitle")
        head.addWidget(t)
        head.addStretch()
        lay.addLayout(head)
        body = QVBoxLayout()
        body.setContentsMargins(12, 0, 12, 12)
        body.setSpacing(8)
        lay.addLayout(body, 1)
        f._head = head
        f._title_label = t
        f._body_lay = body
        return f

    def card_body(self, card: QFrame) -> QVBoxLayout:
        return card._body_lay

    def setup_table(self, table: QTableWidget, headers: List[str]):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setAlternatingRowColors(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.horizontalHeader().setMinimumHeight(34)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.NoFocus)
        table.setMinimumHeight(150)
        table.setColumnWidth(0, 108)
        for c in range(1, len(headers)):
            table.setColumnWidth(c, 82)

    def build_footer(self) -> QFrame:
        f = QFrame()
        f.setObjectName("footer")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addStretch()
        close = QPushButton("Kapat")
        close.setObjectName("secondary")
        close.clicked.connect(self.close)
        lay.addWidget(close)
        return f

    def set_scope(self, scope: str):
        self.selected_scope = scope
        self.refresh_view()

    def selected_contexts(self) -> List[SummaryContext]:
        if self.selected_scope == "all":
            return list(self.contexts)
        scoped = [ctx for ctx in self.contexts if ctx.key == self.selected_scope]
        return scoped if scoped else list(self.contexts[:1])

    def primary_context(self) -> Optional[SummaryContext]:
        contexts = self.selected_contexts()
        if contexts:
            return contexts[0]
        return self.contexts[0] if self.contexts else None

    def system_entries(self) -> List[Tuple[SummaryContext, SystemInfo]]:
        rows = []
        for ctx in self.selected_contexts():
            for sys in ctx.systems:
                rows.append((ctx, sys))
        return rows

    def refresh_view(self):
        if hasattr(self, "scope_combo"):
            idx = self.scope_combo.findData(self.selected_scope)
            if idx >= 0 and self.scope_combo.currentIndex() != idx:
                self.scope_combo.blockSignals(True)
                self.scope_combo.setCurrentIndex(idx)
                self.scope_combo.blockSignals(False)
        ctx = self.primary_context()
        ci = ctx.ci if ctx else None
        self.no_value.setText(str((ci.no if ci else self.item.get("no")) or "—"))
        self.platform_value.setText(str((ci.platform if ci else self.item.get("platform")) or "—"))
        self.user_value.setText(str((ci.user if ci else self.item.get("user")) or "—"))
        self.status_pill.setText(status_label(ci.status if ci else self.item.get("status", "")))
        kind = status_kind(ci.status if ci else self.item.get("status", ""))
        obj = "statusPillDone" if kind == "done" else ("statusPillProgress" if kind == "progress" else "statusPillNew")
        self.status_pill.setObjectName(obj)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.refresh_alert(ci)
        self.refresh_dates(ci)
        self.refresh_systems()
        self.refresh_components_all()

    def refresh_contract_info_table(self):
        if not hasattr(self, "contract_info_table"):
            return
        rows = []
        for ctx in self.contexts:
            ci = ctx.ci
            if not ci:
                continue
            deadline = parse_iso_date(ci.completion_date)
            acceptance = str(ci.acceptance_date or "")
            rows.append([
                ctx.button_label.replace("Ana Söz.", "Ana Sözleşme"),
                display_date(ci.completion_date),
                delivery_timing_text(deadline, parse_iso_date(acceptance)),
                display_date(acceptance),
            ])
        self.contract_info_table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsEnabled)
                if c > 0:
                    it.setTextAlignment(Qt.AlignCenter)
                    it.setBackground(QColor("#f8fafc"))
                    it.setForeground(QColor("#183353"))
                else:
                    it.setForeground(QColor("#0f172a"))
                self.contract_info_table.setItem(r, c, it)
            self.contract_info_table.setRowHeight(r, 30)

    def refresh_alert(self, ci: Optional[ContractInfo]):
        d = parse_iso_date(ci.completion_date if ci else self.item.get("completion_date", ""))
        st_kind = status_kind(ci.status if ci else self.item.get("status", ""))
        if d and st_kind != "done":
            delta = (d - date.today()).days
            if delta < 0:
                self.alert.show()
                self.alert_text.setText(f"Termin tarihi {abs(delta)} gün önce geçti — sözleşme gecikmiş durumda")
                return
        self.alert.hide()

    def refresh_dates(self, ci: Optional[ContractInfo]):
        deadline = parse_iso_date(ci.completion_date if ci else self.item.get("completion_date", ""))
        self.termin_value.setText(display_date(ci.completion_date if ci else self.item.get("completion_date", "")))
        acceptance = str((ci.acceptance_date if ci else "") or "")
        if not acceptance:
            for ctx in self.selected_contexts():
                for delivery_list in ctx.deliveries.values():
                    for delivery in delivery_list:
                        if str(delivery.acceptance_date or "").strip():
                            acceptance = str(delivery.acceptance_date or "")
        self.days_value.setText(delivery_timing_text(deadline, parse_iso_date(acceptance)))
        self.acceptance_value.setText(display_date(acceptance))

    def _system_chip(self, text: str, object_name: str = "systemChipNeutral") -> QLabel:
        chip = QLabel(str(text or "—"))
        chip.setObjectName(object_name)
        chip.setAlignment(Qt.AlignCenter)
        chip.setMinimumHeight(20)
        return chip

    def _status_chip_name(self, status: str) -> str:
        kind = status_kind(status)
        if kind == "done":
            return "systemChipDone"
        if kind == "progress":
            return "systemChipProgress"
        return "systemChipNew"

    def _make_system_row(
        self,
        key: Tuple[str, str],
        title: str,
        subtitle: str = "",
        status: str = "",
        deadline: str = "",
        acceptance: str = "",
        count_text: str = "",
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("systemRowFrame")
        row.setProperty("selected", key == self.selected_system_key)
        row.setCursor(Qt.PointingHandCursor)
        row.setToolTip("Tüm sistemlerin toplam bileşen ve kabul durumu" if key == ("__all__", "__all__") else f"{status_label(status)} | Termin: {deadline or '—'} | Kabul: {acceptance or '—'}")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(5)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        name = QLabel(title)
        name.setObjectName("systemName")
        top.addWidget(name, 1)
        if count_text:
            top.addWidget(self._system_chip(count_text, "systemChipNeutral"), 0)
        elif status:
            top.addWidget(self._system_chip(status_label(status), self._status_chip_name(status)), 0)
        lay.addLayout(top)
        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        if subtitle:
            meta = QLabel(subtitle)
            meta.setObjectName("systemMeta")
            chips.addWidget(meta, 1)
        if deadline:
            chips.addWidget(self._system_chip(f"Termin: {deadline}", "systemChipDate"), 0)
        if acceptance:
            chips.addWidget(self._system_chip(f"Kabul: {acceptance}", "systemChipDate"), 0)
        chips.addStretch(1)
        lay.addLayout(chips)
        row.mousePressEvent = lambda event, k=key: self.select_system(k)
        return row

    def refresh_systems(self):
        entries = self.system_entries()
        overdue = critical = 0
        system_counts = {"new": 0, "progress": 0, "done": 0}
        accept_counts = {"new": 0, "progress": 0, "done": 0}
        accept_total = 0

        for ctx, sys in entries:
            kind = status_kind(sys.status)
            system_counts[kind] += 1
            deadline = parse_iso_date(sys.completion_date)
            if deadline and kind != "done":
                delta = (deadline - date.today()).days
                if delta < 0:
                    overdue += 1
                elif delta <= 60:
                    critical += 1
            deliveries = list(ctx.deliveries.get(sys.name, []))
            if deliveries:
                for delivery in deliveries:
                    accept_counts[status_kind(delivery.status)] += 1
                    accept_total += 1
            else:
                # Kabul kaydı yoksa sistemin genel durumunu kabul özetinde temsili göster.
                accept_counts[kind] += 1
                accept_total += 1

        self.overdue_value.setText(str(overdue))
        self.critical_value.setText(str(critical))
        self.system_total_val.setText(str(len(entries)))
        self.system_new_val.setText(str(system_counts["new"]))
        self.system_progress_val.setText(str(system_counts["progress"]))
        self.system_done_val.setText(str(system_counts["done"]))
        self.accept_total_val.setText(str(accept_total))
        self.accept_new_val.setText(str(accept_counts["new"]))
        self.accept_progress_val.setText(str(accept_counts["progress"]))
        self.accept_done_val.setText(str(accept_counts["done"]))

        self.system_info_table.setRowCount(0)
        if self.selected_scope == "all":
            self.system_card_title.setText("SÖZLEŞMELER")
            self.system_count_label.setText(f"{len(self.contexts)} sözleşme")
            self.system_info_table.setColumnCount(5)
            self.system_info_table.setHorizontalHeaderLabels(["TÜR", "DURUM", "TERMİN TARİHİ", "KABUL TARİHİ", "SİSTEM"])
            self._apply_info_table_widths(contract_view=True)
            rows = []
            for ctx in self.contexts:
                ci = ctx.ci
                rows.append([
                    ctx.button_label.replace("Ana Söz.", "Ana Sözleşme"),
                    status_label(ci.status if ci else ctx.item.get("status", "")),
                    iso_display(ci.completion_date if ci else ctx.item.get("completion_date", "")),
                    iso_display(ci.acceptance_date if ci else ""),
                    str(len(ctx.systems)),
                ])
            self._render_info_rows(rows, status_col=1)
            return

        self.system_card_title.setText("SİSTEM BİLGİSİ")
        self.system_count_label.setText(f"{len(entries)} sistem")
        self.system_info_table.setColumnCount(5)
        self.system_info_table.setHorizontalHeaderLabels(["SİSTEM", "DURUM", "TERMİN TARİHİ", "KABUL TARİHİ", "KABUL SAYISI"])
        self._apply_info_table_widths(contract_view=False)
        rows = []
        for ctx, sys in entries:
            acceptance_count = len(ctx.deliveries.get(sys.name, [])) or (1 if getattr(sys, "acceptance_date", "") else 0)
            rows.append([
                sys.name,
                status_label(sys.status),
                iso_display(sys.completion_date),
                iso_display(getattr(sys, "acceptance_date", "")),
                fmt_num(acceptance_count),
            ])
        self._render_info_rows(rows, status_col=1)

    def _apply_info_table_widths(self, contract_view: bool = False):
        # İlk sütun esneyerek kartın kalan alanını doldurur; böylece ilk açılışta
        # tabloda sağda boş gri alan veya yatay kaydırma görünmez.
        widths = [118, 118, 118, 92]
        if contract_view:
            widths = [128, 122, 122, 84]
        header = self.system_info_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in enumerate(widths, start=1):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.system_info_table.setColumnWidth(col, width)

    def _render_info_rows(self, rows: List[List[str]], status_col: int = 1):
        self.system_info_table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, value in enumerate(vals):
                item = QTableWidgetItem(str(value or "—"))
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(QColor("#f8fbfe"))
                item.setForeground(QColor("#405b78"))
                font = item.font()
                font.setWeight(QFont.Bold)
                if c == 0:
                    font.setWeight(QFont.Black)
                    item.setForeground(QColor("#0d2340"))
                if c > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                if c == status_col:
                    kind = status_kind(str(value))
                    item.setForeground(QColor("#0d8a42" if kind == "done" else ("#ff7a1a" if kind == "progress" else "#ef3e52")))
                item.setFont(font)
                self.system_info_table.setItem(r, c, item)
            self.system_info_table.setRowHeight(r, 42)

    def select_system(self, key: Tuple[str, str]):
        # Özet ekranı yalnızca görüntüleme amaçlıdır; sistem satırları arasında seçim yapılmaz.
        return

    def refresh_components_all(self):
        if hasattr(self, "component_scope_label"):
            if self.selected_scope == "all":
                self.component_scope_label.setText("Tümü")
            else:
                ctx = self.primary_context()
                self.component_scope_label.setText(ctx.button_label if ctx else "—")
        planned: Dict[str, float] = {}
        delivered: Dict[str, float] = {}
        for ctx, sys in self.system_entries():
            for comp, qty in (sys.components or {}).items():
                planned[comp] = planned.get(comp, 0) + as_number(qty)
                delivered.setdefault(comp, 0)
            for delivery in ctx.deliveries.get(sys.name, []):
                for comp, qty in (delivery.delivered or {}).items():
                    delivered[comp] = delivered.get(comp, 0) + as_number(qty)
                    planned.setdefault(comp, 0)
        rows = [(comp, planned.get(comp, 0), delivered.get(comp, 0)) for comp in sorted(planned, key=norm_tr)]
        self.render_component_rows(rows)

    def render_component_rows(self, rows: List[Tuple[str, float, float]]):
        self.component_table.setRowCount(len(rows))
        for r, (comp, p, d) in enumerate(rows):
            kalan = max(p - d, 0)
            values = [comp, fmt_num(p), fmt_num(d), fmt_num(kalan)]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemIsEnabled)
                item.setBackground(QColor("#ffffff"))
                font = item.font()
                font.setWeight(QFont.Bold)
                item.setFont(font)
                if c > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                if c == 2:
                    item.setForeground(QColor("#19b65b" if as_number(value) > 0 else "#ff7a1a"))
                elif c == 3:
                    item.setForeground(QColor("#19b65b" if kalan == 0 else "#ff7a1a"))
                else:
                    item.setForeground(QColor("#102033"))
                self.component_table.setItem(r, c, item)
            self.component_table.setRowHeight(r, 38)

    def refresh_components(self, sys: Optional[SystemInfo], ctx: Optional[SummaryContext]):
        if not sys:
            self.component_table.setRowCount(0)
            return
        planned = dict(sys.components or {})
        delivered: Dict[str, float] = {comp: 0 for comp in planned}
        for delivery in (ctx.deliveries.get(sys.name, []) if ctx else []):
            for comp, qty in (delivery.delivered or {}).items():
                delivered[comp] = delivered.get(comp, 0) + as_number(qty)
        rows = [(comp, as_number(planned.get(comp, 0)), as_number(delivered.get(comp, 0))) for comp in planned]
        self.render_component_rows(rows)

    def refresh_deliveries_all(self):
        self.clear_layout(self.delivery_list_lay)
        deliveries: List[DeliveryInfo] = []
        for ctx, sys in self.system_entries():
            deliveries.extend(ctx.deliveries.get(sys.name, []))
        counts = {"new": 0, "progress": 0, "done": 0}
        for delivery in deliveries:
            counts[status_kind(delivery.status)] += 1
        self.del_new_val.setText(str(counts["new"]))
        self.del_progress_val.setText(str(counts["progress"]))
        self.del_done_val.setText(str(counts["done"]))
        for delivery in deliveries:
            self.delivery_list_lay.addWidget(self.delivery_row(delivery))
        self.delivery_list_lay.addStretch()

    def refresh_deliveries(self, sys: Optional[SystemInfo], ctx: Optional[SummaryContext]):
        self.clear_layout(self.delivery_list_lay)
        deliveries = list(ctx.deliveries.get(sys.name, []) if (sys and ctx) else [])
        counts = {"new": 0, "progress": 0, "done": 0}
        for delivery in deliveries:
            counts[status_kind(delivery.status)] += 1
        self.del_new_val.setText(str(counts["new"]))
        self.del_progress_val.setText(str(counts["progress"]))
        self.del_done_val.setText(str(counts["done"]))
        for delivery in deliveries:
            self.delivery_list_lay.addWidget(self.delivery_row(delivery))
        self.delivery_list_lay.addStretch()

    def delivery_row(self, delivery: DeliveryInfo) -> QFrame:
        f = QFrame()
        f.setStyleSheet("QFrame{background:#f8fafc;border:1px solid #d8e2ed;border-radius:6px;}")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(10, 7, 10, 7)
        dot = QLabel("●")
        kind = status_kind(delivery.status)
        dot.setStyleSheet(f"color:{'#16a34a' if kind == 'done' else ('#0891b2' if kind == 'progress' else '#ea580c')};")
        name = QLabel(str(delivery.name or "Kabul"))
        name.setStyleSheet("font-size:12px;color:#0f172a;")
        pill = QLabel(status_label(delivery.status))
        if kind == "done":
            pill.setStyleSheet("background:#ecfdf5;color:#16a34a;border-radius:6px;padding:2px 7px;font-size:9px;font-weight:900;")
        elif kind == "progress":
            pill.setStyleSheet("background:#ecfeff;color:#0891b2;border-radius:6px;padding:2px 7px;font-size:9px;font-weight:900;")
        else:
            pill.setStyleSheet("background:#fff7ed;color:#ea580c;border-radius:6px;padding:2px 7px;font-size:9px;font-weight:900;")
        dt = QLabel(iso_display(delivery.acceptance_date))
        dt.setStyleSheet("font-size:10px;color:#64748b;")
        lay.addWidget(dot)
        lay.addWidget(name, 1)
        lay.addWidget(pill)
        lay.addWidget(dt)
        return f

    def open_detail(self):
        ctx = self.primary_context()
        if not ctx:
            QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayı bulunamadı.")
            return
        if self.detail_handler:
            self.detail_handler(ctx.item)
        self.close()

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
