# -*- coding: utf-8 -*-
"""
Otomatik teslimat oluşturma eklentisi.

app.py içine yalnızca şunlar eklenir:
    from auto_accept import open_auto_accept_dialog

    auto_btn = QPushButton("Otomatik Teslimat Oluştur")
    auto_btn.clicked.connect(lambda: open_auto_accept_dialog(self))
    dh.addWidget(auto_btn)
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QInputDialog, QLineEdit,
    QComboBox, QSpinBox, QWidget, QFrame, QHeaderView, QStackedWidget,
)
from src.ui.date_picker import build_date_input
from src.ui.message_boxes import ask_yes_no
from src.ui.dialogs.system_dialog import form_label
from src.ui.widgets.platform_tabs import UnitTrackingSidePanel
from src.domain.delivery_core import (
    ACTUAL_DATE_LABEL,
    PLANNED_DATE_LABEL,
    build_delivery_info,
    distributable_target,
    is_delivered_status,
    planned_remaining_state,
    remaining_qty,
    split_evenly,
    validate_quantities,
    validate_status_rules,
    validate_unit_tracking,
)
from src.domain.flexible_date import flexible_or_blank

from src.models.app_models import DeliveryInfo
from src.domain.constants import STATUS_VALUES


def as_number(v) -> float:
    try:
        return float(str(v).replace(",", ".") or 0)
    except Exception:
        return 0.0


def fmt_num(v) -> str:
    try:
        f = float(v or 0)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except Exception:
        return str(v or "")


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + int(months or 0)
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class AutoAcceptDialog(QDialog):
    def __init__(self, work_window, system, accept_count: int, parent=None):
        parent_ci = getattr(work_window, "ci", None)
        self._contract_no_text = str(getattr(parent_ci, "no", "") or "")
        self._is_tbd_contract = bool(
            re.match(r"^\s*.+?\s*-\s*TBD\s*-\s*\d+\s*$", self._contract_no_text, re.IGNORECASE)
        )
        self._uses_acceptance_terms = not self._is_tbd_contract
        self._dialog_term_title = "Teslimat" if self._is_tbd_contract else "Kabul / Teslimat"
        self._single_term = "Teslimat" if self._is_tbd_contract else "Kabul"
        super().__init__(parent)
        self.work = work_window
        self.store = getattr(work_window, "store", None)
        self.system = system
        self.accept_count = int(accept_count)
        self.component_keys = list(system.components.keys())
        self.result_deliveries: List[DeliveryInfo] = []
        self.tables: List[QTableWidget] = []
        self.name_edits: List[QLineEdit] = []
        self.status_boxes: List[QComboBox] = []
        self.t0_edits: List[QLineEdit] = []
        self.month_spins: List[QSpinBox] = []
        self.term_edits: List[QLineEdit] = []
        self.note_edits: List[QLineEdit] = []
        self.delivery_user_combo: Optional[QComboBox] = None
        self.delivery_user_combos: List[QComboBox] = []
        self.delivery_user_names: List[str] = []
        self.planned_acc_date_edits: List[QLineEdit] = []
        self.planned_acc_date_wraps: List[QWidget] = []
        self.planned_acceptance_date_labels: List[QLabel] = []
        self.acc_date_edits: List[QLineEdit] = []
        self.acc_date_wraps: List[QWidget] = []
        self.acceptance_date_labels: List[QLabel] = []
        self.search_edits: List[QLineEdit] = []
        self.card_states: List[dict] = []
        self.unassigned_tables: List[QTableWidget] = []
        self.unassigned_table: Optional[QTableWidget] = None
        self.current_index = 0
        self._updating = False
        self._syncing_delivery_user = False
        self._unit_tracking_map: Dict[str, str] = {}
        self._load_unit_tracking_map()

        existing_deliveries = list(getattr(work_window, "deliveries", {}).get(system.name, []))
        self.existing_assigned: Dict[str, float] = {
            comp: sum(as_number(d.planned.get(comp, 0)) for d in existing_deliveries)
            for comp in self.component_keys
        }
        self.divisible: Dict[str, bool] = {}
        self.unassigned_total: Dict[str, float] = {}
        for comp in self.component_keys:
            qty = max(as_number(system.components.get(comp, 0)), 0)
            available = max(qty - self.existing_assigned.get(comp, 0), 0)
            divisible = (
                float(available).is_integer()
                and self.accept_count > 0
                and int(available) % self.accept_count == 0
            )
            self.divisible[comp] = divisible
            self.unassigned_total[comp] = available

        self.setWindowTitle("Otomatik Teslimat Oluştur")
        self.resize(1280, 720)
        try:
            self.setStyleSheet(work_window.styleSheet())
        except Exception:
            pass
        self.build()
        self.refresh_unassigned_panel()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.delivery_user_names = self._load_delivery_user_names()

        self.stack = QStackedWidget()
        for idx in range(self.accept_count):
            self.stack.addWidget(self._build_accept_card(idx))
        root.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("font-weight:800; color:#334155;")
        self.prev_btn = QPushButton("← Önceki")
        self.prev_btn.setObjectName("secondary")
        self.prev_btn.clicked.connect(self.go_prev)
        self.next_btn = QPushButton("Sonraki →")
        self.next_btn.setObjectName("secondary")
        self.next_btn.clicked.connect(self.go_next)
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Teslimatları Oluştur")
        save.clicked.connect(self.save)
        footer.addWidget(self.progress_label)
        footer.addWidget(self.prev_btn)
        footer.addWidget(self.next_btn)
        footer.addStretch()
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)
        self.update_nav_state()

    def _form_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("formLabel")
        l.setStyleSheet("font-weight:800; color:#64748B;")
        return l

    def _load_delivery_user_names(self) -> List[str]:
        names: List[str] = []
        seen = set()
        store = getattr(self.work, "store", None)
        if store is not None:
            for user in store.load_users(active_only=True):
                name = str(user.get("name", "") or "").strip()
                key = name.casefold()
                if name and key not in seen:
                    seen.add(key)
                    names.append(name)
        return names

    def _build_delivery_user_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Seçiniz...")
        for name in self.delivery_user_names:
            combo.addItem(name)
        combo.currentIndexChanged.connect(lambda _idx, c=combo: self._sync_delivery_user_combo(c))
        self.delivery_user_combos.append(combo)
        if self.delivery_user_combo is None:
            self.delivery_user_combo = combo
        return combo

    def _sync_delivery_user_combo(self, source: QComboBox):
        if self._syncing_delivery_user:
            return
        self._syncing_delivery_user = True
        try:
            text = source.currentText().strip() if source.currentIndex() > 0 else ""
            for combo in self.delivery_user_combos:
                if combo is source:
                    continue
                idx = combo.findText(text) if text else 0
                combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._syncing_delivery_user = False

    def _build_acceptance_date_input(self) -> tuple[QLineEdit, QWidget]:
        return build_date_input(self, max_date=date.today(), events_provider=self.date_picker_events)

    def date_picker_events(self) -> List[dict]:
        provider = getattr(self.work, "date_picker_events", None)
        if callable(provider):
            try:
                return list(provider() or [])
            except Exception:
                return []
        return []

    def _build_planned_acceptance_date_input(self) -> tuple[QLineEdit, QWidget]:
        return build_date_input(self, events_provider=self.date_picker_events)

    def _planned_date_label_text(self) -> str:
        return "Planlanan Teslimat Tarihi" if self._is_tbd_contract else "Planlanan Kabul Tarihi"

    def _actual_date_label_text(self) -> str:
        return "Gerçekleşen Teslimat Tarihi" if self._is_tbd_contract else "Gerçekleşen Kabul Tarihi"

    def _sync_actual_date_visibility(self, idx: int):
        if idx < 0 or idx >= len(self.acc_date_wraps) or idx >= len(self.acceptance_date_labels):
            return
        visible = idx < len(self.status_boxes) and self._is_delivered_status(self.status_boxes[idx].currentText())
        self.acceptance_date_labels[idx].setVisible(visible)
        self.acc_date_wraps[idx].setVisible(visible)

    def _build_accept_card(self, idx: int) -> QWidget:
        card = QFrame()
        card.setObjectName("contentPanel")
        card.setStyleSheet("QFrame#contentPanel{background:#EAF2FB; border:1px solid #D8E2EE; border-radius:12px;}")
        outer = QHBoxLayout(card)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        left_card = QFrame()
        left_card.setObjectName("autoAcceptLeftPanel")
        left_card.setFixedWidth(360)
        left_card.setStyleSheet(
            "QFrame#autoAcceptLeftPanel{background:#F8FBFF; border:1px solid #D8E2EE; border-radius:12px;}"
        )
        left_lay = QVBoxLayout(left_card)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(8)

        assignment_panel = QWidget()
        assignment_lay = QVBoxLayout(assignment_panel)
        assignment_lay.setContentsMargins(0, 0, 0, 0)
        assignment_lay.setSpacing(8)
        alloc_title = QLabel("Bileşen Atama Durumu")
        alloc_title.setAlignment(Qt.AlignCenter)
        alloc_title.setStyleSheet("font-weight:900; font-size:14px;")
        assignment_lay.addWidget(alloc_title)
        alloc_hint = QLabel("Tanımlanabilir değeri 0 olan bileşenler listeden gizlenir.")
        alloc_hint.setObjectName("muted")
        alloc_hint.setWordWrap(True)
        assignment_lay.addWidget(alloc_hint)
        assignment_table = QTableWidget(0, 3)
        assignment_table.setObjectName("qtyTable")
        assignment_table.setHorizontalHeaderLabels(["Bileşen", "Tanımlanmış", "Tanımlanabilir"])
        assignment_table.verticalHeader().setVisible(False)
        assignment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        assignment_table.setSelectionBehavior(QTableWidget.SelectRows)
        assignment_table.setShowGrid(True)
        assignment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        assignment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        assignment_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        assignment_table.setColumnWidth(1, 112)
        assignment_table.setColumnWidth(2, 124)
        assignment_table.setStyleSheet(UnitTrackingSidePanel._modern_scrollbar_qss("QTableWidget"))
        assignment_lay.addWidget(assignment_table, 1)

        unit_side_panel = UnitTrackingSidePanel()
        left_stack = QStackedWidget()
        left_stack.setStyleSheet("background:transparent;")
        left_stack.addWidget(assignment_panel)
        left_stack.addWidget(unit_side_panel)
        left_lay.addWidget(left_stack, 1)
        outer.addWidget(left_card, 0)

        state = {
            "left_panel_mode": "assignment",
            "active_unit_component": None,
            "unit_filter": "all",
            "unit_search_text": "",
            "component_units_state": {},
            "comp_row": {},
            "row_comp": {},
            "assignment_panel": assignment_panel,
            "assignment_table": assignment_table,
            "left_stack": left_stack,
            "unit_side_panel": unit_side_panel,
            "table": None,
        }
        self.card_states.append(state)
        self.unassigned_tables.append(assignment_table)
        if self.unassigned_table is None:
            self.unassigned_table = assignment_table
        unit_side_panel.changed.connect(lambda i=idx: self._on_unit_side_panel_changed(i))
        unit_side_panel.backRequested.connect(lambda i=idx: self._show_assignment_panel(i))
        unit_side_panel.clearRequested.connect(lambda i=idx: self._on_unit_side_panel_changed(i))

        right = QWidget()
        root = QVBoxLayout(right)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        outer.addWidget(right, 1)

        title = QLabel(f"{self.system.name} için Teslimat")
        title.setObjectName("dialogTitle")
        title.setStyleSheet("font-weight:900; font-size:18px;")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        name = QLineEdit(f"Teslimat {idx + 1}")
        status = QComboBox()
        status.addItems(list(STATUS_VALUES))
        status.currentTextChanged.connect(lambda _text, i=idx: self.on_status_changed(i))
        t0 = QLineEdit(str(getattr(self.system, "t0_date", "") or getattr(self.work.ci, "t0_date", "") or ""))
        months = QSpinBox()
        months.setRange(0, 999)
        months.setValue(int(getattr(self.system, "t0_months", 0) or 0))
        term = QLineEdit(str(getattr(self.system, "completion_date", "") or ""))
        note = QLineEdit()
        note.setPlaceholderText("Not")
        planned_acc, planned_acc_wrap = self._build_planned_acceptance_date_input()
        acc, acc_wrap = self._build_acceptance_date_input()
        planned_acc_label = form_label(self._planned_date_label_text())
        acc_label = form_label(self._actual_date_label_text())

        self.name_edits.append(name)
        self.status_boxes.append(status)
        self.t0_edits.append(t0)
        self.month_spins.append(months)
        self.term_edits.append(term)
        self.note_edits.append(note)
        self.planned_acc_date_edits.append(planned_acc)
        self.planned_acc_date_wraps.append(planned_acc_wrap)
        self.planned_acceptance_date_labels.append(planned_acc_label)
        self.acc_date_edits.append(acc)
        self.acc_date_wraps.append(acc_wrap)
        self.acceptance_date_labels.append(acc_label)

        grid.addWidget(self._form_label("Teslimat Adı"), 0, 0)
        grid.addWidget(name, 1, 0)
        grid.addWidget(self._form_label("Durum"), 0, 1)
        grid.addWidget(status, 1, 1)
        delivery_user_combo = self._build_delivery_user_combo()

        grid.addWidget(planned_acc_label, 2, 0)
        grid.addWidget(planned_acc_wrap, 3, 0)
        grid.addWidget(acc_label, 4, 0)
        grid.addWidget(acc_wrap, 5, 0)
        grid.addWidget(self._form_label("Not"), 2, 1)
        grid.addWidget(note, 3, 1)
        grid.addWidget(self._form_label("Teslim Edilecek Kullanıcı"), 4, 1)
        grid.addWidget(delivery_user_combo, 5, 1)
        root.addLayout(grid)
        self._sync_actual_date_visibility(idx)

        info_row = QHBoxLayout()
        info = QLabel("Bileşen miktarlarını aşağıdaki tabloda girin. Kalan değeri otomatik hesaplanır.")
        info.setObjectName("muted")
        info_row.addWidget(info, 1)
        fill_all = QPushButton("Tüm Sistemi Ekle")
        fill_all.setObjectName("secondary")
        fill_all.clicked.connect(lambda _=False, i=idx: self.fill_all_system(i))
        info_row.addWidget(fill_all)
        fill_remaining = QPushButton("Kalan Sistemi Ekle")
        fill_remaining.setObjectName("secondary")
        fill_remaining.clicked.connect(lambda _=False, i=idx: self.fill_remaining_system(i))
        info_row.addWidget(fill_remaining)
        root.addLayout(info_row)

        search = QLineEdit()
        search.setPlaceholderText("Bileşen ara...")
        self.search_edits.append(search)
        root.addWidget(search, 0)

        tbl = QTableWidget(len(self.component_keys), 4)
        state["table"] = tbl
        tbl.setObjectName("qtyTable")
        tbl.setHorizontalHeaderLabels(["Bileşen", "Teslim Edilecek", "Teslim Edilen", "Kalan"])
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(False)
        tbl.setShowGrid(True)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        tbl.setColumnWidth(3, 110)
        tbl.setMinimumHeight(200)
        tbl.setStyleSheet(UnitTrackingSidePanel._modern_scrollbar_qss("QTableWidget"))
        tbl.itemChanged.connect(lambda item, t=tbl: self.on_table_changed(t, item))
        tbl.cellClicked.connect(lambda row, col, i=idx: self._on_cell_clicked(i, row, col))
        self.tables.append(tbl)
        search.textChanged.connect(lambda text, i=idx: self.filter_components(i, text))

        self._updating = True
        for r, comp in enumerate(self.component_keys):
            state["comp_row"][comp] = r
            state["row_comp"][r] = comp
            qty = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            planned_values = split_evenly(qty, self.accept_count)
            planned = planned_values[idx] if planned_values else 0.0

            comp_item = QTableWidgetItem("")
            comp_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tbl.setItem(r, 0, comp_item)
            tbl.setCellWidget(r, 0, self._make_arrow_cell(idx, comp))

            for c, value in enumerate((planned, 0, planned), start=1):
                item = QTableWidgetItem(fmt_num(value))
                if c == 3:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                else:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter)
                if not self.divisible.get(comp):
                    item.setBackground(QColor("#FEF3C7"))
                tbl.setItem(r, c, item)
            tbl.setRowHeight(r, 30)
            self._ensure_component_units(idx, comp, int(max(planned, 0)))
        self._updating = False
        root.addWidget(tbl, 1)
        self._refresh_unit_row_selection(idx)
        return card

    def _load_unit_tracking_map(self):
        self._unit_tracking_map = {comp: "Kuyruk No / Seri No" for comp in self.component_keys}
        if self.store is not None:
            try:
                stored_labels = self.store.get_unit_tracking_components()
            except Exception:
                stored_labels = {}
            for comp, label in (stored_labels or {}).items():
                if comp in self._unit_tracking_map and str(label or "").strip():
                    self._unit_tracking_map[comp] = str(label).strip()

    def _is_unit_tracking(self, comp: str) -> bool:
        return bool(comp)

    def _make_arrow_cell(self, card_idx: int, comp: str) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(0)
        arrow = QPushButton("▶")
        arrow.setObjectName("unitTrackingArrow")
        arrow.setFixedSize(20, 20)
        arrow.clicked.connect(lambda _=False, i=card_idx, c=comp: self._toggle_unit_component(i, c))
        arrow.setProperty("comp", comp)
        lbl = QLabel(comp)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("background: transparent; color:#0F172A; font-weight: 500;")
        spacer = QWidget()
        spacer.setFixedWidth(20)
        lay.addWidget(arrow, 0, Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(lbl, 1)
        lay.addWidget(spacer, 0)
        widget.setProperty("arrow_btn", arrow)
        widget.setProperty("label_widget", lbl)
        return widget

    def _get_arrow_btn(self, card_idx: int, comp: str) -> Optional[QPushButton]:
        state = self.card_states[card_idx]
        row = state["comp_row"].get(comp)
        if row is None:
            return None
        widget = self.tables[card_idx].cellWidget(row, 0)
        return widget.property("arrow_btn") if widget else None

    def _get_component_label(self, card_idx: int, comp: str) -> Optional[QLabel]:
        state = self.card_states[card_idx]
        row = state["comp_row"].get(comp)
        if row is None:
            return None
        widget = self.tables[card_idx].cellWidget(row, 0)
        return widget.property("label_widget") if widget else None

    def _existing_units_for(self, card_idx: int, comp: str) -> list:
        return []

    def _ensure_component_units(self, card_idx: int, comp: str, planned_qty: int) -> list:
        state = self.card_states[card_idx]
        component_units_state = state["component_units_state"]
        planned_qty = max(0, int(planned_qty or 0))
        current = component_units_state.get(comp)
        source = current if current is not None else self._existing_units_for(card_idx, comp)
        by_slot = {}
        for unit in source or []:
            try:
                slot_no = int(unit.get("slot_no", 0) or 0)
            except Exception:
                slot_no = 0
            if slot_no > 0:
                by_slot[slot_no] = {
                    "slot_no": slot_no,
                    "identifier": str(unit.get("identifier") or "").strip(),
                    "is_delivered": int(unit.get("is_delivered", 0) or 0),
                    "note": str(unit.get("note") or ""),
                }
        normalized = []
        keep_slots = set(range(1, planned_qty + 1))
        for slot_no, unit in by_slot.items():
            has_data = bool(
                str(unit.get("identifier") or "").strip()
                or str(unit.get("note") or "").strip()
                or int(unit.get("is_delivered", 0) or 0)
            )
            if slot_no > planned_qty and has_data:
                keep_slots.add(slot_no)
        for slot_no in sorted(keep_slots):
            unit = dict(by_slot.get(slot_no, {}))
            unit["slot_no"] = slot_no
            unit["identifier"] = str(unit.get("identifier") or "").strip()
            unit["is_delivered"] = int(unit.get("is_delivered", 0) or 0)
            unit["note"] = str(unit.get("note") or "")
            normalized.append(unit)
        component_units_state[comp] = normalized
        return normalized

    def _current_units_from_panel_if_active(self, card_idx: int):
        state = self.card_states[card_idx]
        comp = state["active_unit_component"]
        if comp and state["left_panel_mode"] == "unit_tracking":
            state["component_units_state"][comp] = state["unit_side_panel"].get_units()

    def _activate_unit_component(self, card_idx: int, comp: str):
        if not self._is_unit_tracking(comp):
            return
        state = self.card_states[card_idx]
        self._current_units_from_panel_if_active(card_idx)
        row = state["comp_row"].get(comp)
        tbl = self.tables[card_idx]
        planned = as_number(tbl.item(row, 1).text()) if row is not None and tbl.item(row, 1) else 0
        delivered = as_number(tbl.item(row, 2).text()) if row is not None and tbl.item(row, 2) else 0
        units = self._ensure_component_units(card_idx, comp, int(max(planned, delivered)))
        state["left_panel_mode"] = "unit_tracking"
        state["active_unit_component"] = comp
        state["unit_side_panel"].set_component(
            comp,
            self._unit_tracking_map.get(comp, "Kuyruk No / Seri No"),
            units,
        )
        state["left_stack"].setCurrentWidget(state["unit_side_panel"])
        self._refresh_unit_row_selection(card_idx)

    def _toggle_unit_component(self, card_idx: int, comp: str):
        if not self._is_unit_tracking(comp):
            return
        state = self.card_states[card_idx]
        if state["left_panel_mode"] == "unit_tracking" and state["active_unit_component"] == comp:
            self._show_assignment_panel(card_idx)
            return
        self._activate_unit_component(card_idx, comp)

    def _show_assignment_panel(self, card_idx: int):
        state = self.card_states[card_idx]
        self._current_units_from_panel_if_active(card_idx)
        state["left_panel_mode"] = "assignment"
        state["active_unit_component"] = None
        state["left_stack"].setCurrentWidget(state["assignment_panel"])
        self._refresh_unit_row_selection(card_idx)
        self.refresh_unassigned_panel()

    def _on_unit_side_panel_changed(self, card_idx: int):
        state = self.card_states[card_idx]
        comp = state["active_unit_component"]
        if not comp:
            return
        state["component_units_state"][comp] = state["unit_side_panel"].get_units()

    def _validate_unit_tracking_qty(self, card_idx: int, comp: str, qty: float) -> bool:
        if not self._is_unit_tracking(comp):
            return True
        validation_error = validate_unit_tracking(comp, qty, [])
        if validation_error:
            QMessageBox.warning(self, "Ondalıklı Adet", validation_error)
            return False
        return True

    def _on_cell_clicked(self, card_idx: int, row: int, col: int):
        state = self.card_states[card_idx]
        comp = state["row_comp"].get(row)
        if comp and col == 0 and self._is_unit_tracking(comp):
            self._toggle_unit_component(card_idx, comp)

    def _update_panel_slot_count(self, card_idx: int, comp: str, new_qty: int):
        if not self._is_unit_tracking(comp):
            return
        state = self.card_states[card_idx]
        if comp == state["active_unit_component"] and state["left_panel_mode"] == "unit_tracking":
            state["component_units_state"][comp] = state["unit_side_panel"].get_units()
        units = self._ensure_component_units(card_idx, comp, int(new_qty or 0))
        if comp == state["active_unit_component"] and state["left_panel_mode"] == "unit_tracking":
            state["unit_side_panel"].set_component(
                comp,
                self._unit_tracking_map.get(comp, "Kuyruk No / Seri No"),
                units,
            )
        self._refresh_unit_row_selection(card_idx)

    def _refresh_unit_row_selection(self, card_idx: int):
        state = self.card_states[card_idx]
        tbl = self.tables[card_idx]
        selected_bg = QColor("#EAF3FF")
        selected_fg = QColor("#0F3B82")
        was_blocked = tbl.blockSignals(True)
        try:
            for comp, row in state["comp_row"].items():
                active = comp == state["active_unit_component"] and state["left_panel_mode"] == "unit_tracking"
                cell_widget = tbl.cellWidget(row, 0)
                if cell_widget:
                    cell_widget.setStyleSheet(f"background:{'#EAF3FF' if active else 'transparent'};")
                label = self._get_component_label(card_idx, comp)
                if label:
                    label.setStyleSheet(
                        "background: transparent; "
                        f"color:{'#0F3B82' if active else '#0F172A'}; "
                        f"font-weight:{'900' if active else '500'};"
                    )
                btn = self._get_arrow_btn(card_idx, comp)
                if btn:
                    btn.setText("◀" if active else "▶")
                    if active:
                        btn.setStyleSheet(
                            "QPushButton#unitTrackingArrow{background:#0F3B82;color:#0f172a;"
                            "border:1px solid #0F3B82;border-radius:5px;font-size:10px;font-weight:900;padding:0;}"
                        )
                    else:
                        btn.setStyleSheet(
                            "QPushButton#unitTrackingArrow{background:#DBEAFE;color:#1D4ED8;"
                            "border:1px solid #93C5FD;border-radius:5px;font-size:10px;font-weight:900;padding:0;} "
                            "QPushButton#unitTrackingArrow:hover{background:#BFDBFE;}"
                        )
                if active:
                    for c in range(tbl.columnCount()):
                        item = tbl.item(row, c)
                        if item:
                            item.setBackground(selected_bg)
                            item.setForeground(selected_fg)
        finally:
            tbl.blockSignals(was_blocked)

    def update_nav_state(self):
        self.stack.setCurrentIndex(self.current_index)
        self.progress_label.setText(f"Teslimat {self.current_index + 1} / {self.accept_count}")
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < self.accept_count - 1)

    def go_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_nav_state()

    def go_next(self):
        if self.current_index < self.accept_count - 1:
            self.current_index += 1
            self.update_nav_state()

    def _is_delivered_status(self, status: str) -> bool:
        return is_delivered_status(status)

    def _accept_quantity_maps(self, i: int) -> tuple[Dict[str, float], Dict[str, float]]:
        tbl = self.tables[i]
        planned: Dict[str, float] = {}
        delivered: Dict[str, float] = {}
        for r, comp in enumerate(self.component_keys):
            planned[comp] = max(as_number(tbl.item(r, 1).text()), 0)
            delivered[comp] = max(as_number(tbl.item(r, 2).text()), 0)
        return planned, delivered

    def _accept_remaining_components(self, i: int) -> List[str]:
        planned, delivered = self._accept_quantity_maps(i)
        _all_delivered, remaining_components = planned_remaining_state(planned, delivered)
        return remaining_components

    def _status_validation_warning(self, error: str) -> tuple[str, str]:
        planned_label = self._planned_date_label_text()
        actual_label = self._actual_date_label_text()
        message = (
            str(error or "")
            .replace(PLANNED_DATE_LABEL, planned_label)
            .replace(ACTUAL_DATE_LABEL, actual_label)
        )
        if message.startswith(f"{planned_label} zorunludur."):
            title = "Tarih gerekli"
        elif message.startswith(f"Durum tamamlandı/teslim edildi olduğunda {actual_label} zorunludur."):
            title = f"{actual_label} Gerekli"
        elif message.startswith("Durum 'Teslim Edildi' olduğunda"):
            title = "Teslim Edilen Eksik"
        elif message.startswith("Bu teslimatta tüm bileşenlerin kalanı 0."):
            title = "Durum Uyumsuz"
        else:
            title = "Tarih hatası"
        return title, message

    def validate_accept(self, i: int) -> bool:
        if not self.name_edits[i].text().strip():
            QMessageBox.warning(self, "Eksik", "Teslimat adı girin.")
            return False
        plan_acc_text = self.planned_acc_date_edits[i].text().strip()
        acc_text = self.acc_date_edits[i].text().strip()
        planned, delivered = self._accept_quantity_maps(i)
        status_errors = validate_status_rules(
            self.status_boxes[i].currentText(),
            acc_text,
            plan_acc_text,
            planned,
            delivered,
        )
        if status_errors:
            title, message = self._status_validation_warning(status_errors[0])
            QMessageBox.warning(self, title, message)
            return False

        for comp in self.component_keys:
            quantity_errors = validate_quantities(
                [comp],
                planned,
                delivered,
                lambda key: planned.get(key, 0),
                lambda _key: 0,
            )
            if quantity_errors:
                message = quantity_errors[0].replace(
                    "teslim edilen, teslim edilecekten büyük olamaz.",
                    "teslim edilen teslim edilecekten büyük olamaz.",
                )
                QMessageBox.warning(self, "Hata", message)
                return False
        return True

    def on_status_changed(self, idx: int):
        self._sync_actual_date_visibility(idx)
        if self._updating or idx < 0 or idx >= len(self.tables):
            return
        if not self._is_delivered_status(self.status_boxes[idx].currentText()):
            return
        self.fill_delivered_to_planned(idx)

    def fill_delivered_to_planned(self, accept_idx: int):
        tbl = self.tables[accept_idx]
        self._updating = True
        try:
            for r in range(tbl.rowCount()):
                planned = max(as_number(tbl.item(r, 1).text()), 0)
                tbl.item(r, 2).setText(fmt_num(planned))
                tbl.item(r, 3).setText(fmt_num(0))
        finally:
            self._updating = False
        self.refresh_unassigned_panel()

    def on_table_changed(self, table: QTableWidget, item: QTableWidgetItem):
        if self._updating or not item or item.column() not in (1, 2):
            return
        self._updating = True
        row = item.row()
        planned = max(as_number(table.item(row, 1).text()), 0)
        delivered = max(as_number(table.item(row, 2).text()), 0)
        try:
            idx = self.tables.index(table)
        except ValueError:
            idx = -1
        comp = self.component_keys[row] if 0 <= row < len(self.component_keys) else ""
        if idx >= 0 and item.column() == 1 and self._is_unit_tracking(comp):
            if not self._validate_unit_tracking_qty(idx, comp, planned):
                planned = 0.0
                table.item(row, 1).setText("0")
        if idx >= 0 and item.column() == 1 and self._is_delivered_status(self.status_boxes[idx].currentText()):
            delivered = planned
            table.item(row, 2).setText(fmt_num(delivered))
        if delivered > planned:
            delivered = planned
            table.item(row, 2).setText(fmt_num(delivered))
        table.item(row, 1).setText(fmt_num(planned))
        table.item(row, 3).setText(fmt_num(remaining_qty(planned, delivered)))
        if idx >= 0 and comp and self._is_unit_tracking(comp):
            self._update_panel_slot_count(idx, comp, int(max(planned, delivered)))
        self._updating = False
        self.refresh_unassigned_panel()

    def fill_all_system(self, accept_idx: int):
        tbl = self.tables[accept_idx]
        self._updating = True
        for r, comp in enumerate(self.component_keys):
            total_available = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            other_assigned = 0.0
            for j, other_tbl in enumerate(self.tables):
                if j != accept_idx:
                    other_assigned += as_number(other_tbl.item(r, 1).text())
            qty = distributable_target(total_available, other_assigned)
            tbl.item(r, 1).setText(fmt_num(qty))
            if as_number(tbl.item(r, 2).text()) > qty:
                tbl.item(r, 2).setText(fmt_num(qty))
            delivered = as_number(tbl.item(r, 2).text())
            tbl.item(r, 3).setText(fmt_num(remaining_qty(qty, delivered)))
            self._update_panel_slot_count(accept_idx, comp, int(max(qty, delivered)))
        self._updating = False
        self.refresh_unassigned_panel()

    def fill_remaining_system(self, accept_idx: int):
        tbl = self.tables[accept_idx]
        self._updating = True
        for r, comp in enumerate(self.component_keys):
            contract_qty = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            other_assigned = 0.0
            for j, other_tbl in enumerate(self.tables):
                if j != accept_idx:
                    other_assigned += as_number(other_tbl.item(r, 1).text())
            remaining = distributable_target(contract_qty, other_assigned)
            tbl.item(r, 1).setText(fmt_num(remaining))
            if as_number(tbl.item(r, 2).text()) > remaining:
                tbl.item(r, 2).setText(fmt_num(remaining))
            delivered = as_number(tbl.item(r, 2).text())
            tbl.item(r, 3).setText(fmt_num(remaining_qty(remaining, delivered)))
            self._update_panel_slot_count(accept_idx, comp, int(max(remaining, delivered)))
        self._updating = False
        self.refresh_unassigned_panel()

    def _norm_search(self, text: str) -> str:
        txt = str(text or "").strip().lower()
        repl = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
        for a, b in repl.items():
            txt = txt.replace(a, b)
        return " ".join(txt.split())

    def filter_components(self, accept_idx: int, text: str):
        if accept_idx < 0 or accept_idx >= len(self.tables):
            return
        query = self._norm_search(text)
        tbl = self.tables[accept_idx]
        for r in range(tbl.rowCount()):
            comp = self.component_keys[r] if r < len(self.component_keys) else ""
            name = self._norm_search(comp)
            tbl.setRowHidden(r, bool(query and query not in name))

    def _over_assigned_components(self) -> set[str]:
        over = set()
        for comp in self.unassigned_total.keys():
            remaining = self.unassigned_total[comp] - self._sum_planned(comp)
            if remaining < -0.0001:
                over.add(comp)
        return over

    def refresh_table_issue_highlights(self):
        over = self._over_assigned_components()
        issue_bg = QColor("#FEE2E2")
        issue_fg = QColor("#991B1B")
        warn_bg = QColor("#FEF3C7")
        normal_bg = QColor("#FFFFFF")
        normal_fg = QColor("#0F172A")
        for tbl in self.tables:
            for r, comp in enumerate(self.component_keys):
                has_issue = comp in over
                bg = issue_bg if has_issue else (warn_bg if not self.divisible.get(comp) else normal_bg)
                fg = issue_fg if has_issue else normal_fg
                for c in range(tbl.columnCount()):
                    item = tbl.item(r, c)
                    if not item:
                        continue
                    item.setBackground(bg)
                    item.setForeground(fg)
        for card_idx in range(len(self.card_states)):
            self._refresh_unit_row_selection(card_idx)

    def refresh_unassigned_panel(self):
        rows = []
        for comp in self.unassigned_total.keys():
            current_assigned = self._sum_planned(comp)
            assigned = max(as_number(self.existing_assigned.get(comp, 0)), 0) + current_assigned
            remaining = self.unassigned_total[comp] - current_assigned
            if abs(remaining) > 0.0001:
                rows.append((comp, assigned, remaining))
        for assignment_table in self.unassigned_tables:
            assignment_table.setRowCount(len(rows))
            for r, (comp, assigned, remaining) in enumerate(rows):
                has_issue = remaining < -0.0001
                bg = QColor("#FEE2E2") if has_issue else QColor("#FFFFFF")
                fg = QColor("#991B1B") if has_issue else QColor("#0F172A")
                for c, value in enumerate([comp, assigned, remaining]):
                    item = QTableWidgetItem(fmt_num(value) if c else str(value))
                    item.setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
                    item.setBackground(bg)
                    item.setForeground(fg)
                    assignment_table.setItem(r, c, item)
                assignment_table.setRowHeight(r, 30)
        self.refresh_table_issue_highlights()

    def _sum_planned(self, comp: str) -> float:
        total = 0.0
        comp_idx = self.component_keys.index(comp)
        for tbl in self.tables:
            total += as_number(tbl.item(comp_idx, 1).text())
        return total

    def _validated_component_units_for_card(self, card_idx: int) -> Optional[Dict[str, list]]:
        self._current_units_from_panel_if_active(card_idx)
        tbl = self.tables[card_idx]
        state = self.card_states[card_idx]
        component_units: Dict[str, list] = {}
        for row, comp in enumerate(self.component_keys):
            planned = max(as_number(tbl.item(row, 1).text()), 0)
            delivered = max(as_number(tbl.item(row, 2).text()), 0)
            if not self._is_unit_tracking(comp) or planned <= 0:
                continue
            validation_error = validate_unit_tracking(comp, planned, [])
            if validation_error:
                QMessageBox.warning(self, "Ondalıklı Adet", validation_error)
                return None
            if comp == state["active_unit_component"] and state["left_panel_mode"] == "unit_tracking":
                state["component_units_state"][comp] = state["unit_side_panel"].get_units()
            units = self._ensure_component_units(card_idx, comp, int(max(planned, delivered)))
            validation_error = validate_unit_tracking(comp, planned, units)
            if validation_error:
                QMessageBox.warning(self, "Tekrar Var", validation_error)
                return None
            component_units[comp] = units
        return component_units

    def save(self):
        validated_component_units: List[Dict[str, list]] = []
        for i in range(self.accept_count):
            if not self.name_edits[i].text().strip():
                QMessageBox.warning(self, "Eksik", "Teslimat adı girin.")
                self.current_index = i
                self.update_nav_state()
                return
            component_units = self._validated_component_units_for_card(i)
            if component_units is None:
                self.current_index = i
                self.update_nav_state()
                return
            validated_component_units.append(component_units)
            if not self.validate_accept(i):
                self.current_index = i
                self.update_nav_state()
                return

        for comp in self.component_keys:
            total_planned = self._sum_planned(comp)
            contract_qty = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            if total_planned > contract_qty + 0.0001:
                QMessageBox.warning(self, "Fazla dağıtım", f"{comp}: toplam dağıtım sözleşme adedini aşıyor.")
                return

        missing = []
        for comp in self.component_keys:
            contract_qty = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            remaining = max(contract_qty - self._sum_planned(comp), 0)
            if remaining > 0.0001:
                missing.append(f"{comp}: {fmt_num(remaining)}")
        if missing:
            QMessageBox.warning(
                self,
                "Atanmayan bileşen var",
                "Teslimatları oluşturmadan önce aşağıdaki bileşenleri teslimatlara dağıtın:\n\n" + "\n".join(missing),
            )
            self.refresh_unassigned_panel()
            return

        self.result_deliveries = []
        delivery_user = ""
        if self.delivery_user_combo is not None and self.delivery_user_combo.currentIndex() > 0:
            delivery_user = self.delivery_user_combo.currentText().strip()
        for i, tbl in enumerate(self.tables):
            planned: Dict[str, float] = {}
            delivered: Dict[str, float] = {}
            for r, comp in enumerate(self.component_keys):
                planned[comp] = max(as_number(tbl.item(r, 1).text()), 0)
                delivered[comp] = max(as_number(tbl.item(r, 2).text()), 0)
            plan_acc_text = self.planned_acc_date_edits[i].text().strip()
            self.result_deliveries.append(build_delivery_info(
                name=self.name_edits[i].text().strip(),
                status=self.status_boxes[i].currentText(),
                acceptance_date=flexible_or_blank(self.acc_date_edits[i].text().strip()),
                note=self.note_edits[i].text().strip(),
                planned_acceptance_date=flexible_or_blank(plan_acc_text),
                planned=planned,
                delivered=delivered,
                t0_date=str(getattr(self.system, "t0_date", "") or self.t0_edits[i].text()).strip(),
                t0_months=int(getattr(self.system, "t0_months", self.month_spins[i].value()) or 0),
                completion_date=str(getattr(self.system, "completion_date", "") or self.term_edits[i].text()).strip(),
                delivery_user=delivery_user,
                component_units=validated_component_units[i],
            ))
        self.accept()


def open_auto_accept_dialog(work_window):
    """ContractWorkWindow içinden çağrılır."""
    sys_info = work_window.current_system()
    if not sys_info:
        QMessageBox.warning(work_window, "Sistem yok", "Önce sistem seçin.")
        return
    work_window.sync_summary_to_system()
    if not any(as_number(v) > 0 for v in sys_info.components.values()):
        QMessageBox.warning(work_window, "Adet yok", "Önce Bileşen Özeti tablosunda sözleşme adetlerini girin.")
        return
    count, ok = QInputDialog.getInt(work_window, "Otomatik Teslimat", "Kaç teslimata bölmek istersiniz?", 2, 1, 100, 1)
    if not ok:
        return
    existing = work_window.deliveries.get(sys_info.name, [])
    available = []
    for comp, qty in sys_info.components.items():
        assigned = sum(as_number(d.planned.get(comp, 0)) for d in existing)
        remaining = max(as_number(qty) - assigned, 0)
        if remaining > 0.0001:
            available.append((comp, remaining))
    if not available:
        QMessageBox.information(work_window, "Tanımlanabilir yok", "Bu sistemde teslimatlara tanımlanabilecek bileşen miktarı kalmadı.")
        return
    if existing:
        if not ask_yes_no(
            work_window,
            "Mevcut teslimatlar var",
            "Bu sisteme ait mevcut teslimatlar var. Otomatik teslimatlar mevcut listenin sonuna eklensin mi?",
            default_yes=True,
        ):
            return
    dlg = AutoAcceptDialog(work_window, sys_info, count, work_window)
    overlay = QWidget(work_window)
    overlay.setObjectName("dimOverlay")
    overlay.setStyleSheet("background: rgba(0,0,0,140);")
    overlay.setGeometry(work_window.rect())
    overlay.show()
    overlay.raise_()
    dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    dlg.setWindowModality(Qt.WindowModal)

    def _center_auto():
        pw = work_window.geometry()
        dlg.move(pw.x() + (pw.width() - dlg.width()) // 2, pw.y() + (pw.height() - dlg.height()) // 2)

    QTimer.singleShot(0, _center_auto)
    _orig_move = work_window.moveEvent

    def _move_hook(ev):
        _orig_move(ev)
        _center_auto()

    work_window.moveEvent = _move_hook
    try:
        result = dlg.exec()
    finally:
        work_window.moveEvent = _orig_move
        overlay.hide()
        overlay.deleteLater()
    if result and dlg.result_deliveries:
        work_window.deliveries.setdefault(sys_info.name, []).extend(dlg.result_deliveries)
        work_window._deleted_delivery_systems.discard(sys_info.name)
        work_window._set_dirty()
        work_window.expanded_delivery_index = None
        work_window.refresh_live_statuses()
        work_window.refresh_right()
        QMessageBox.information(work_window, "Tamamlandı", f"{len(dlg.result_deliveries)} teslimat oluşturuldu.")
