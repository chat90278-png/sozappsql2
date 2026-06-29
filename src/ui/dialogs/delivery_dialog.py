# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import sys
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from src.domain.constants import STATUS_VALUES
from src.domain.flexible_date import flexible_or_blank, parse_flexible_date, validate_flexible_date
from src.models.app_models import DeliveryInfo, SystemInfo
from src.services.excel_store import as_number, fmt_num, iso_or_blank, normalize_sheet_name
from src.ui.date_picker import build_date_input
from src.ui.delegates import CompactNumberDelegate
from src.ui.dialogs.styled_dialog import StyledDialog
from src.ui.dialogs.system_dialog import SystemDialog, configure_table, form_label
from src.ui.widgets.user_select import MultiUserSelectWidget
from src.ui.widgets.platform_tabs import UnitTrackingSlotCard, UnitTrackingSidePanel

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QMessageBox, QFrame, QHeaderView, QTableWidget,
    QTableWidgetItem, QStackedWidget,
)


class DeliveryDialog(StyledDialog):
    """Teslimat ekleme / düzenleme dialog'u.

    Tüm bileşenlerde kuyruk no / seri no takibi kullanılabilir:
    - Bileşen hücresinde ▶/◀ ok ikonu görünür.
    - Satır/ok seçilince sol panel kuyruk no / seri no listesine dönüşür.
    - Ana tablo 4 sütun kalır; inline detail row oluşturulmaz.
    """

    def __init__(
        self,
        system: SystemInfo,
        default_name: str = "Teslimat 1",
        parent=None,
        component_keys: Optional[List[str]] = None,
        planned_assigned: Optional[Dict[str, float]] = None,
        contract_t0_date: str = "",
        events_provider: Optional[Callable[[], List[dict]]] = None,
        allow_delete: bool = False,
        existing_delivery: Optional["DeliveryInfo"] = None,
    ):
        parent_ci = getattr(parent, "ci", None)
        self._contract_no_text = str(getattr(parent_ci, "no", "") or "")
        self._is_tbd_contract = bool(re.match(r"^\s*.+?\s*-\s*TBD\s*-\s*\d+\s*$", self._contract_no_text, re.IGNORECASE))
        self._uses_acceptance_terms = not self._is_tbd_contract
        self._dialog_term_title = "Teslimat" if self._is_tbd_contract else "Kabul / Teslimat"
        self._single_term = "Teslimat" if self._is_tbd_contract else "Kabul"
        super().__init__(f"{self._dialog_term_title} Düzenle" if existing_delivery else f"{self._dialog_term_title} Ekle", parent)
        self.system = system
        self.store = getattr(parent, "store", None)
        if (not existing_delivery) and self._uses_acceptance_terms and str(default_name or "").strip().lower().startswith("teslimat"):
            default_name = re.sub(r"^\s*Teslimat", "Kabul", str(default_name or ""), flags=re.IGNORECASE)
        self.default_name = default_name
        raw_components = getattr(self.system, "components", {}) or {}
        try:
            component_names = list(raw_components.keys()) if hasattr(raw_components, "keys") else list(dict(raw_components).keys())
        except RecursionError:
            try:
                sys.__stderr__.write("RecursionError while reading system components; using an empty component list.\n")
            except Exception:
                pass
            component_names = []
        except Exception:
            component_names = []
        self.component_keys = list(component_keys or component_names)
        self.planned_assigned = dict(planned_assigned or {})
        self.contract_t0_date = contract_t0_date
        self.events_provider = events_provider
        self.allow_delete = bool(allow_delete)
        self.delete_requested = False
        self.result: Optional[DeliveryInfo] = None
        self._existing_delivery = existing_delivery
        self.resize(1280, 700)
        self.inputs: Dict[str, Tuple[QTableWidgetItem, QTableWidgetItem, QTableWidgetItem]] = {}
        self._updating_qty = False
        self._updating_qty_table = False
        self._status_auto_filling = False
        # Unit tracking state
        self._unit_tracking_map: Dict[str, str] = {}  # {comp_name: label}
        self.left_panel_mode = "assignment"
        self.active_unit_component: Optional[str] = None
        self.unit_filter = "all"
        self.unit_search_text = ""
        self._component_units_state: Dict[str, list] = {}
        # comp_name -> table row index
        self._comp_row: Dict[str, int] = {}
        # Actual qty_table row -> comp_name
        self._row_comp: Dict[int, Optional[str]] = {}
        self._load_unit_tracking_map()
        self.build()

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

    def _safe_system_components(self) -> Dict[str, float]:
        raw = getattr(self.system, "components", {}) or {}
        if isinstance(raw, dict):
            return raw
        try:
            return dict(raw)
        except RecursionError:
            try:
                sys.__stderr__.write("RecursionError while normalizing system components; using empty quantities.\n")
            except Exception:
                pass
            return {}
        except Exception:
            return {}

    def _system_component_qty(self, comp: str) -> float:
        try:
            components = self._safe_system_components()
            return max(as_number(components.get(comp, 0)), 0)
        except RecursionError:
            try:
                sys.__stderr__.write(f"RecursionError while reading component quantity for {comp}; using 0.\n")
            except Exception:
                pass
            return 0.0
        except Exception:
            return 0.0

    # ------------------------------------------------------------------ build
    def build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        left_card = QFrame()
        left_card.setObjectName("contentPanel")
        left_card.setFixedWidth(380)
        left_card.setStyleSheet(
            "QFrame#contentPanel{background:#F8FBFF; border:1px solid #D8E2EE; border-radius:12px;}"
        )
        left_lay = QVBoxLayout(left_card)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(8)
        alloc_title = QLabel("Bileşen Atama Durumu")
        alloc_title.setAlignment(Qt.AlignCenter)
        alloc_title.setStyleSheet("font-weight:900; font-size:14px;")
        left_lay.addWidget(alloc_title)
        alloc_hint = QLabel("Tanımlanabilir değeri 0 olan bileşenler listeden gizlenir.")
        alloc_hint.setObjectName("muted")
        alloc_hint.setWordWrap(True)
        left_lay.addWidget(alloc_hint)
        self.assignment_table = QTableWidget(0, 3)
        self.assignment_table.setObjectName("qtyTable")
        configure_table(self.assignment_table, compact=True)
        self.assignment_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.assignment_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.assignment_table.setHorizontalHeaderLabels(["Bileşen", "Tanımlanmış", "Tanımlanabilir"])
        self.assignment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.assignment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.assignment_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.assignment_table.setColumnWidth(1, 120)
        self.assignment_table.setColumnWidth(2, 132)
        self.assignment_table.setStyleSheet(UnitTrackingSidePanel._modern_scrollbar_qss("QTableWidget"))
        left_lay.addWidget(self.assignment_table, 1)

        self.assignment_panel = QWidget()
        assignment_lay = left_lay
        self.unit_side_panel = UnitTrackingSidePanel()
        self.unit_side_panel.changed.connect(self._on_unit_side_panel_changed)
        self.unit_side_panel.backRequested.connect(self._show_assignment_panel)
        self.unit_side_panel.clearRequested.connect(self._on_unit_side_panel_changed)

        # left_card layout is reused as the assignment page; wrap pages in a stack by moving widgets.
        self.left_stack = QStackedWidget()
        self.left_stack.setStyleSheet("background:transparent;")
        while left_lay.count():
            item = left_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.assignment_panel)
        assignment_page_lay = QVBoxLayout(self.assignment_panel)
        assignment_page_lay.setContentsMargins(0, 0, 0, 0)
        assignment_page_lay.setSpacing(8)
        assignment_page_lay.addWidget(alloc_title)
        assignment_page_lay.addWidget(alloc_hint)
        assignment_page_lay.addWidget(self.assignment_table, 1)
        left_lay.addWidget(self.left_stack, 1)
        self.left_stack.addWidget(self.assignment_panel)
        self.left_stack.addWidget(self.unit_side_panel)
        outer.addWidget(left_card, 0)

        right = QWidget()
        root = QVBoxLayout(right)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        outer.addWidget(right, 1)

        title = QLabel(f"{self.system.name} için {self._dialog_term_title}")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.name = QLineEdit()
        self.name.setPlaceholderText(f"Örn: {self._single_term} 1")
        self.name.setText(self.default_name)
        self.name.selectAll()
        self.status = QComboBox()
        self.status.addItems(STATUS_VALUES)
        self.status.currentTextChanged.connect(self.on_status_changed)
        self._delivery_t0_date = str(getattr(self.system, "t0_date", "") or self.contract_t0_date or "")
        self._delivery_t0_months = int(getattr(self.system, "t0_months", 0) or 0)
        self._delivery_completion_date = str(getattr(self.system, "completion_date", "") or "")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Not")
        self.delivery_user_combo = QComboBox()
        self.delivery_user_combo.addItem("Seçiniz...")
        if self.store is not None:
            for user in self.store.load_users(active_only=True):
                uname = str(user.get("name", "") or "").strip()
                if uname:
                    self.delivery_user_combo.addItem(uname)
        self.planned_acceptance_date, self.planned_acceptance_date_wrap = build_date_input(
            self, events_provider=self.events_provider
        )
        self.acceptance_date, self.acceptance_date_wrap = build_date_input(
            self, max_date=date.today(), events_provider=self.events_provider
        )
        self.planned_acceptance_date_label = form_label(self._planned_date_label_text())
        self.acceptance_date_label = form_label(self._actual_date_label_text())
        grid.addWidget(form_label(f"{self._single_term} Adı"), 0, 0)
        grid.addWidget(self.name, 1, 0)
        grid.addWidget(form_label("Durum"), 0, 1)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(self.planned_acceptance_date_label, 2, 0)
        grid.addWidget(self.planned_acceptance_date_wrap, 3, 0)
        grid.addWidget(self.acceptance_date_label, 4, 0)
        grid.addWidget(self.acceptance_date_wrap, 5, 0)
        grid.addWidget(form_label("Not"), 2, 1)
        grid.addWidget(self.note, 3, 1)
        grid.addWidget(form_label("Teslim Edilecek Kullanıcı"), 4, 1)
        grid.addWidget(self.delivery_user_combo, 5, 1)
        root.addLayout(grid)
        self._sync_actual_date_visibility()

        info_row = QHBoxLayout()
        info = QLabel("Bileşen miktarlarını aşağıdaki tabloda girin. Kalan değeri otomatik hesaplanır.")
        info.setObjectName("muted")
        info_row.addWidget(info, 1)
        self.fill_all_btn = QPushButton("Tüm Sistemi Ekle")
        self.fill_all_btn.setObjectName("secondary")
        self.fill_all_btn.setMinimumHeight(32)
        self.fill_all_btn.clicked.connect(self.fill_all_system_planned)
        info_row.addWidget(self.fill_all_btn, 0)
        self.fill_remaining_btn = QPushButton("Kalan Sistemi Ekle")
        self.fill_remaining_btn.setObjectName("secondary")
        self.fill_remaining_btn.setMinimumHeight(32)
        self.fill_remaining_btn.clicked.connect(self.fill_remaining_system_planned)
        info_row.addWidget(self.fill_remaining_btn, 0)
        root.addLayout(info_row)

        # Main quantity table (4 columns, fixed structure)
        self.qty_table = QTableWidget(0, 4)
        self.qty_table.setObjectName("qtyTable")
        configure_table(self.qty_table, compact=True)
        self.qty_table.setHorizontalHeaderLabels(["Bileşen", "Teslim Edilecek", "Teslim Edilen", "Kalan"])
        self.qty_table.verticalHeader().setVisible(False)
        self.qty_table.setAlternatingRowColors(False)
        self.qty_table.setShowGrid(True)
        self.qty_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.qty_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.qty_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.qty_table.setColumnWidth(3, 110)
        self.qty_table.setMinimumHeight(200)
        self.qty_table.setStyleSheet(
            UnitTrackingSidePanel._modern_scrollbar_qss("QTableWidget")
            + """
            QTableWidget#qtyTable {
                background:#ffffff;
                alternate-background-color:#0f172a;
                gridline-color:#d8e2ed;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
            }
            QTableWidget#qtyTable::item {
                background:#ffffff;
                color:#0f172a;
                padding:4px 6px;
            }
            QTableWidget#qtyTable::item:hover {
                background:#f8fbff;
            }
            QTableWidget#qtyTable::item:selected {
                background:#dbeafe;
                color:#0f172a;
            }
            QTableWidget#qtyTable QWidget {
                background:#ffffff;
            }
            """
        )
        self.qty_table.viewport().setStyleSheet("background:#ffffff;")
        self.qty_table.setItemDelegateForColumn(1, CompactNumberDelegate(self.qty_table))
        self.qty_table.setItemDelegateForColumn(2, CompactNumberDelegate(self.qty_table))
        self.component_search = QLineEdit()
        self.component_search.setPlaceholderText("Bileşen ara...")
        self.component_search.textChanged.connect(self.filter_qty_components)

        self._populate_qty_table()

        root.addWidget(self.component_search, 0)
        root.addWidget(self.qty_table, 1)

        row = QHBoxLayout()
        if self.allow_delete:
            delete_btn = QPushButton(f"{self._single_term} Sil")
            delete_btn.setObjectName("danger")
            delete_btn.clicked.connect(self.request_delete)
            row.addWidget(delete_btn)
        row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Kaydet")
        save.clicked.connect(self.save)
        row.addWidget(cancel)
        row.addWidget(save)
        root.addLayout(row)

    # ------------------------------------------------------------------ table population
    def _populate_qty_table(self):
        """Tüm bileşenler için satırları oluşturur."""
        existing = self._existing_delivery
        self._updating_qty = True
        was_blocked = self.qty_table.blockSignals(True)
        try:
            self.qty_table.setRowCount(0)
            self._comp_row.clear()
            self._row_comp.clear()
            self.inputs.clear()

            current_row = 0
            for comp in self.component_keys:
                self._comp_row[comp] = current_row

                # Component name cell with optional arrow for unit tracking
                if self._is_unit_tracking(comp):
                    comp_widget = self._make_arrow_cell(comp)
                    comp_item = QTableWidgetItem("")
                    comp_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                else:
                    comp_widget = None
                    comp_item = QTableWidgetItem(comp)
                    comp_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

                planned_val = "0"
                delivered_val = "0"
                if existing:
                    planned_val = fmt_num(float((existing.planned or {}).get(comp, 0) or 0))
                    delivered_val = fmt_num(float((existing.delivered or {}).get(comp, 0) or 0))

                planned = QTableWidgetItem(planned_val)
                delivered = QTableWidgetItem(delivered_val)
                remaining = QTableWidgetItem("0")

                planned.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                delivered.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                remaining.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                for it in (planned, delivered, remaining):
                    it.setTextAlignment(Qt.AlignCenter)

                self.qty_table.insertRow(current_row)
                if comp_widget:
                    self.qty_table.setCellWidget(current_row, 0, comp_widget)
                else:
                    self.qty_table.setItem(current_row, 0, comp_item)
                self.qty_table.setItem(current_row, 1, planned)
                self.qty_table.setItem(current_row, 2, delivered)
                self.qty_table.setItem(current_row, 3, remaining)
                self.qty_table.setRowHeight(current_row, 30)
                self._row_comp[current_row] = comp
                self.inputs[comp] = (planned, delivered, remaining)
                self._update_remaining_row(current_row)
                if self._is_unit_tracking(comp):
                    self._ensure_component_units(comp, int(as_number(planned.text())))
                current_row += 1
        finally:
            self.qty_table.blockSignals(was_blocked)
            self._updating_qty = False

        self.qty_table.itemChanged.connect(self.on_qty_item_changed)
        self.qty_table.cellClicked.connect(self._on_cell_clicked)
        self.refresh_assignment_card()

    def _make_arrow_cell(self, comp: str) -> QWidget:
        """Bileşen adının önünde sol paneli açan ok ikonu olan widget döner."""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(0)
        arrow = QPushButton("▶")
        arrow.setObjectName("unitTrackingArrow")
        arrow.setFixedSize(20, 20)
        arrow.clicked.connect(lambda _=False, c=comp: self._toggle_unit_component(c))
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

    def _get_arrow_btn(self, comp: str) -> Optional[QPushButton]:
        data_row = self._comp_row.get(comp)
        if data_row is None:
            return None
        w = self.qty_table.cellWidget(data_row, 0)
        if w:
            return w.property("arrow_btn")
        return None

    def _get_component_label(self, comp: str) -> Optional[QLabel]:
        data_row = self._comp_row.get(comp)
        if data_row is None:
            return None
        w = self.qty_table.cellWidget(data_row, 0)
        if w:
            return w.property("label_widget")
        return None

    def _existing_units_for(self, comp: str) -> list:
        if not self._existing_delivery:
            return []
        return list((getattr(self._existing_delivery, "component_units", None) or {}).get(comp, []) or [])

    def _ensure_component_units(self, comp: str, planned_qty: int) -> list:
        """Component slot state'ini planned adede göre normalize eder; mevcut değerleri korur."""
        planned_qty = max(0, int(planned_qty or 0))
        current = self._component_units_state.get(comp)
        source = current if current is not None else self._existing_units_for(comp)
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
        self._component_units_state[comp] = normalized
        return normalized

    def _current_units_from_panel_if_active(self):
        comp = self.active_unit_component
        if comp and self.left_panel_mode == "unit_tracking" and hasattr(self, "unit_side_panel"):
            self._component_units_state[comp] = self.unit_side_panel.get_units()

    def _activate_unit_component(self, comp: str):
        if not self._is_unit_tracking(comp):
            return
        self._current_units_from_panel_if_active()
        planned_item, delivered_item, _ = self.inputs.get(comp, (None, None, None))
        planned_qty = int(max(as_number(planned_item.text()) if planned_item else 0, as_number(delivered_item.text()) if delivered_item else 0))
        units = self._ensure_component_units(comp, planned_qty)
        self.left_panel_mode = "unit_tracking"
        self.active_unit_component = comp
        self.unit_side_panel.set_component(comp, self._unit_tracking_map.get(comp, "Kuyruk No / Seri No"), units)
        self.left_stack.setCurrentWidget(self.unit_side_panel)
        self._refresh_unit_row_selection()

    def _toggle_unit_component(self, comp: str):
        if not self._is_unit_tracking(comp):
            return
        if self.left_panel_mode == "unit_tracking" and self.active_unit_component == comp:
            self._show_assignment_panel()
            return
        self._activate_unit_component(comp)

    def _show_assignment_panel(self):
        self._current_units_from_panel_if_active()
        self.left_panel_mode = "assignment"
        self.active_unit_component = None
        self.left_stack.setCurrentWidget(self.assignment_panel)
        self._refresh_unit_row_selection()
        self.refresh_assignment_card()

    def _on_unit_side_panel_changed(self):
        comp = self.active_unit_component
        if not comp:
            return
        self._component_units_state[comp] = self.unit_side_panel.get_units()

    def _validate_unit_tracking_qty(self, comp: str, qty: float) -> bool:
        """Unit tracking bileşende ondalıklı adet uyarısı."""
        if not self._is_unit_tracking(comp):
            return True
        if qty != int(qty):
            QMessageBox.warning(
                self, "Ondalıklı Adet",
                f"Bu bileşende teslim edilecek adet tam sayı olmalıdır.\n({comp})"
            )
            return False
        return True

    def _on_cell_clicked(self, row: int, col: int):
        comp = self._row_comp.get(row)
        if comp and col == 0 and self._is_unit_tracking(comp):
            self._toggle_unit_component(comp)

    def _update_panel_slot_count(self, comp: str, new_qty: int):
        if not self._is_unit_tracking(comp):
            return
        if comp == self.active_unit_component and self.left_panel_mode == "unit_tracking":
            self._component_units_state[comp] = self.unit_side_panel.get_units()
        units = self._ensure_component_units(comp, int(new_qty or 0))
        if comp == self.active_unit_component and self.left_panel_mode == "unit_tracking":
            self.unit_side_panel.set_component(comp, self._unit_tracking_map.get(comp, "Kuyruk No / Seri No"), units)
        self._refresh_unit_row_selection()

    def _refresh_unit_row_selection(self):
        selected_bg = QColor("#EAF3FF")
        normal_bg = QColor("#FFFFFF")
        selected_fg = QColor("#0F3B82")
        normal_fg = QColor("#0F172A")
        was_blocked = self.qty_table.blockSignals(True)
        try:
            for comp, row in self._comp_row.items():
                active = comp == self.active_unit_component and self.left_panel_mode == "unit_tracking"
                cell_widget = self.qty_table.cellWidget(row, 0)
                if cell_widget:
                    cell_widget.setStyleSheet(f"background:{'#EAF3FF' if active else 'transparent'};")
                label = self._get_component_label(comp)
                if label:
                    label.setStyleSheet(
                        "background: transparent; "
                        f"color:{'#0F3B82' if active else '#0F172A'}; "
                        f"font-weight:{'900' if active else '500'};"
                    )
                btn = self._get_arrow_btn(comp)
                if btn:
                    btn.setText("◀" if active else "▶")
                    if active:
                        btn.setStyleSheet("QPushButton#unitTrackingArrow{background:#0F3B82;color:#0f172a;border:1px solid #0F3B82;border-radius:5px;font-size:10px;font-weight:900;padding:0;}")
                    else:
                        btn.setStyleSheet("QPushButton#unitTrackingArrow{background:#DBEAFE;color:#1D4ED8;border:1px solid #93C5FD;border-radius:5px;font-size:10px;font-weight:900;padding:0;} QPushButton#unitTrackingArrow:hover{background:#BFDBFE;}")
                for c in range(self.qty_table.columnCount()):
                    item = self.qty_table.item(row, c)
                    if item:
                        item.setBackground(selected_bg if active else normal_bg)
                        item.setForeground(selected_fg if active else normal_fg)
        finally:
            self.qty_table.blockSignals(was_blocked)

    # ------------------------------------------------------------------ term/date UI helpers
    def _planned_date_label_text(self) -> str:
        return "Planlanan Teslimat Tarihi" if self._is_tbd_contract else "Planlanan Kabul Tarihi"

    def _actual_date_label_text(self) -> str:
        return "Gerçekleşen Teslimat Tarihi" if self._is_tbd_contract else "Gerçekleşen Kabul Tarihi"

    def _sync_actual_date_visibility(self):
        if not hasattr(self, "acceptance_date_wrap") or not hasattr(self, "acceptance_date_label"):
            return
        # İlk girişte sadece planlanan tarih istenir. Gerçekleşen tarih yalnızca tamamlandı/teslim edildi durumunda görünür.
        visible = self._is_delivered_status()
        self.acceptance_date_label.setVisible(visible)
        self.acceptance_date_wrap.setVisible(visible)

    # ------------------------------------------------------------------ existing methods
    def request_delete(self):
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle(f"{self._single_term} Sil")
        confirm.setText(
            f"Bu {self._single_term.lower()} silinecek. Bu kayda ait miktarlar artık teslim edilmiş sayılmayacak. "
            "Sistem ana bileşen adetleri değişmeyecek. Devam etmek istiyor musunuz?"
        )
        delete_btn = confirm.addButton("Evet, Sil", QMessageBox.DestructiveRole)
        confirm.addButton("Vazgeç", QMessageBox.RejectRole)
        confirm.exec()
        if confirm.clickedButton() != delete_btn:
            return
        self.delete_requested = True
        self.accept()

    def _is_delivered_status(self) -> bool:
        status = self.status.currentText().strip() if hasattr(self, "status") else ""
        norm = status.lower().replace("ı", "i").replace("İ", "i")
        return norm in {"teslim edildi", "tamamlandi", "tamamlandı"}

    def on_status_changed(self, _text: str = ""):
        self._sync_actual_date_visibility()
        if self._status_auto_filling or not self._is_delivered_status():
            return
        self.fill_delivered_to_planned()

    def fill_delivered_to_planned(self):
        self._status_auto_filling = True
        self._updating_qty = True
        was_blocked = self.qty_table.blockSignals(True)
        try:
            for comp in self.component_keys:
                data_row = self._comp_row.get(comp)
                if data_row is None:
                    continue
                items = self.inputs.get(comp)
                if not items:
                    continue
                planned_item, delivered_item, _ = items
                if not planned_item or not delivered_item:
                    continue
                delivered_item.setText(fmt_num(as_number(planned_item.text())))
                self._update_remaining_row(data_row)
        finally:
            self.qty_table.blockSignals(was_blocked)
            self._updating_qty = False
            self._status_auto_filling = False
        self.refresh_assignment_card()

    def _planned_remaining_state(
        self, planned: Dict[str, float], delivered: Dict[str, float]
    ) -> Tuple[bool, List[str]]:
        active_components = [comp for comp, qty in planned.items() if max(as_number(qty), 0) > 0.0001]
        remaining = [
            comp for comp in active_components
            if max(as_number(planned.get(comp, 0)) - as_number(delivered.get(comp, 0)), 0) > 0.0001
        ]
        return bool(active_components) and not remaining, remaining

    def _recalc_completion(self):
        return

    def _current_planned_for(self, comp: str) -> float:
        items = self.inputs.get(comp)
        if not items:
            return 0.0
        return max(as_number(items[0].text()), 0)

    def assignment_rows(self) -> List[Tuple[str, float, float]]:
        rows = []
        for comp in self.component_keys:
            total = self._system_component_qty(comp)
            assigned = max(as_number(self.planned_assigned.get(comp, 0)), 0) + self._current_planned_for(comp)
            available = total - assigned
            if abs(available) > 0.0001:
                rows.append((comp, assigned, available))
        return rows

    def over_assigned_components(self) -> set:
        return {comp for comp, _assigned, available in self.assignment_rows() if available < -0.0001}

    def filter_qty_components(self, text: str):
        query = normalize_sheet_name(text)
        for comp, data_row in self._comp_row.items():
            hidden = bool(query and query not in normalize_sheet_name(comp))
            self.qty_table.setRowHidden(data_row, hidden)

    def refresh_qty_issue_highlights(self):
        over = self.over_assigned_components()
        issue_bg = QColor("#FEE2E2")
        issue_fg = QColor("#991B1B")
        normal_bg = QColor("#FFFFFF")
        normal_fg = QColor("#0F172A")
        was_blocked = self.qty_table.blockSignals(True)
        try:
            for comp, data_row in self._comp_row.items():
                has_issue = comp in over
                for c in range(self.qty_table.columnCount()):
                    item = self.qty_table.item(data_row, c)
                    if not item:
                        continue
                    item.setBackground(issue_bg if has_issue else normal_bg)
                    item.setForeground(issue_fg if has_issue else normal_fg)
        finally:
            self.qty_table.blockSignals(was_blocked)

    def refresh_assignment_card(self):
        rows = self.assignment_rows()
        was_blocked = self.assignment_table.blockSignals(True)
        try:
            self.assignment_table.setRowCount(len(rows))
            for r, (comp, assigned, available) in enumerate(rows):
                has_issue = available < -0.0001
                bg = QColor("#FEE2E2") if has_issue else QColor("#FFFFFF")
                fg = QColor("#991B1B") if has_issue else QColor("#0F172A")
                values = [comp, assigned, available]
                for c, v in enumerate(values):
                    item = QTableWidgetItem(fmt_num(v) if c else str(v))
                    item.setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
                    item.setBackground(bg)
                    item.setForeground(fg)
                    self.assignment_table.setItem(r, c, item)
                self.assignment_table.setRowHeight(r, 30)
        finally:
            self.assignment_table.blockSignals(was_blocked)
        self.refresh_qty_issue_highlights()
        self._refresh_unit_row_selection()

    def fill_all_system_planned(self):
        self._updating_qty = True
        was_blocked = self.qty_table.blockSignals(True)
        try:
            for comp in self.component_keys:
                data_row = self._comp_row.get(comp)
                if data_row is None:
                    continue
                items = self.inputs.get(comp)
                if not items:
                    continue
                planned_item, delivered_item, _ = items
                if not planned_item:
                    continue
                system_qty = self._system_component_qty(comp)
                assigned_qty = max(as_number(self.planned_assigned.get(comp, 0)), 0)
                allowed_qty = max(system_qty - assigned_qty, 0)
                planned_item.setText(fmt_num(allowed_qty))
                if delivered_item and as_number(delivered_item.text()) > allowed_qty:
                    delivered_item.setText(fmt_num(allowed_qty))
                self._update_remaining_row(data_row)
                if self._is_unit_tracking(comp):
                    self._update_panel_slot_count(comp, int(allowed_qty))
        finally:
            self.qty_table.blockSignals(was_blocked)
            self._updating_qty = False
        self.refresh_assignment_card()

    def fill_remaining_system_planned(self):
        self._updating_qty = True
        was_blocked = self.qty_table.blockSignals(True)
        try:
            for comp in self.component_keys:
                data_row = self._comp_row.get(comp)
                if data_row is None:
                    continue
                items = self.inputs.get(comp)
                if not items:
                    continue
                planned_item, delivered_item, _ = items
                if not planned_item:
                    continue
                system_qty = self._system_component_qty(comp)
                assigned_qty = max(as_number(self.planned_assigned.get(comp, 0)), 0)
                remaining_qty = max(system_qty - assigned_qty, 0)
                planned_item.setText(fmt_num(remaining_qty))
                if delivered_item and as_number(delivered_item.text()) > remaining_qty:
                    delivered_item.setText(fmt_num(remaining_qty))
                self._update_remaining_row(data_row)
                if self._is_unit_tracking(comp):
                    self._update_panel_slot_count(comp, int(remaining_qty))
        finally:
            self.qty_table.blockSignals(was_blocked)
            self._updating_qty = False
        self.refresh_assignment_card()

    def _update_remaining_row(self, row: int):
        p = self.qty_table.item(row, 1)
        d = self.qty_table.item(row, 2)
        r = self.qty_table.item(row, 3)
        if not p or not d or not r:
            return
        pv = as_number(p.text())
        dv = as_number(d.text())
        was_blocked = self.qty_table.blockSignals(True)
        try:
            r.setText(fmt_num(max(pv - dv, 0)))
        finally:
            self.qty_table.blockSignals(was_blocked)

    def on_qty_item_changed(self, item: QTableWidgetItem):
        if self._updating_qty or self._updating_qty_table or not item:
            return
        col = item.column()
        if col not in (1, 2):
            return
        row = item.row()
        comp = self._row_comp.get(row)
        if not comp:
            return
        self._updating_qty_table = True
        self._updating_qty = True
        was_blocked = self.qty_table.blockSignals(True)
        try:
            item.setText(fmt_num(as_number(item.text())))
            if col == 1:
                # Teslim edilecek değişti
                new_qty = as_number(item.text())
                if self._is_unit_tracking(comp):
                    # Ondalıklı değer uyarısı
                    if new_qty != int(new_qty):
                        QMessageBox.warning(
                            self, "Ondalıklı Adet",
                            f"Bu bileşende teslim edilecek adet tam sayı olmalıdır.\n({comp})"
                        )
                        item.setText("0")
                        self._update_remaining_row(row)
                        return
                    delivered_item = self.qty_table.item(row, 2)
                    delivered_qty = as_number(delivered_item.text()) if delivered_item else 0
                    self._update_panel_slot_count(comp, int(max(new_qty, delivered_qty)))
                else:
                    if self._is_delivered_status():
                        delivered_item = self.qty_table.item(row, 2)
                        if delivered_item:
                            delivered_item.setText(fmt_num(new_qty))
            elif col == 2 and self._is_unit_tracking(comp):
                planned_item = self.qty_table.item(row, 1)
                planned_qty = as_number(planned_item.text()) if planned_item else 0
                delivered_qty = as_number(item.text())
                self._update_panel_slot_count(comp, int(max(planned_qty, delivered_qty)))
            self._update_remaining_row(row)
        finally:
            self.qty_table.blockSignals(was_blocked)
            self._updating_qty = False
            self._updating_qty_table = False
        self.refresh_assignment_card()

    # ------------------------------------------------------------------ save
    def save(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Eksik", "Teslimat adı girin.")
            return

        self._current_units_from_panel_if_active()
        planned: Dict[str, float] = {}
        delivered: Dict[str, float] = {}
        component_units: Dict[str, list] = {}

        for comp, (p, d, _r) in self.inputs.items():
            pv = as_number(p.text())
            dv = as_number(d.text())
            assigned_other = max(as_number(self.planned_assigned.get(comp, 0)), 0)
            system_qty = self._system_component_qty(comp)
            if pv + assigned_other > system_qty + 0.0001:
                QMessageBox.warning(self, "Hata", f"{comp}: tanımlanan toplam miktar sistem adedini aşamaz.")
                return
            if dv > pv:
                QMessageBox.warning(self, "Hata", f"{comp}: teslim edilen, teslim edilecekten büyük olamaz.")
                return
            planned[comp] = pv
            delivered[comp] = dv

            # Unit tracking validation
            if self._is_unit_tracking(comp) and pv > 0:
                if pv != int(pv):
                    QMessageBox.warning(
                        self, "Ondalıklı Adet",
                        f"Bu bileşende teslim edilecek adet tam sayı olmalıdır.\n({comp})"
                    )
                    return
                if comp == self.active_unit_component and self.left_panel_mode == "unit_tracking":
                    self._component_units_state[comp] = self.unit_side_panel.get_units()
                units = self._ensure_component_units(comp, int(max(pv, dv)))
                counts: Dict[str, int] = {}
                for unit in units:
                    ident = normalize_sheet_name(unit.get("identifier", ""))
                    if ident:
                        counts[ident] = counts.get(ident, 0) + 1
                if any(v > 1 for v in counts.values()):
                    QMessageBox.warning(
                        self, "Tekrar Var",
                        f"{comp}: Aynı kuyruk no / seri no iki kez girilemez. Lütfen düzeltin."
                    )
                    return
                component_units[comp] = units

        t0_text = str(getattr(self.system, "t0_date", "") or self._delivery_t0_date).strip()
        completion = str(getattr(self.system, "completion_date", "") or self._delivery_completion_date).strip()
        plan_acc_text = self.planned_acceptance_date.text().strip()
        planned_label = self._planned_date_label_text()
        actual_label = self._actual_date_label_text()
        if not plan_acc_text or plan_acc_text == "-":
            QMessageBox.warning(
                self,
                "Tarih gerekli",
                f"{planned_label} zorunludur. Kesin tarih yazabilir veya belirsizse TBD / YYYY-MM-TBD / YYYY-TBD-TBD kullanabilirsiniz.",
            )
            return
        ok, message = validate_flexible_date(plan_acc_text, allow_empty=False)
        if not ok:
            QMessageBox.warning(self, "Tarih hatası", f"{planned_label}: {message}")
            return
        acc_text = self.acceptance_date.text().strip()
        ok, message = validate_flexible_date(acc_text, allow_empty=True)
        if not ok:
            QMessageBox.warning(self, "Tarih hatası", f"{actual_label}: {message}")
            return
        acc_date = parse_flexible_date(acc_text)
        if acc_text and not acc_date and self._is_delivered_status():
            QMessageBox.warning(self, "Tarih hatası", f"Tamamlanan kayıtta {actual_label} kesin YYYY-MM-DD olmalıdır. TBD kabul edilmez.")
            return
        if acc_date and acc_date > date.today():
            QMessageBox.warning(self, "Tarih hatası", f"{actual_label} bugünden ileri olamaz.")
            return

        all_delivered, remaining_components = self._planned_remaining_state(planned, delivered)
        if self._is_delivered_status():
            if not acc_text:
                QMessageBox.warning(self, f"{actual_label} Gerekli", f"Durum tamamlandı/teslim edildi olduğunda {actual_label} zorunludur.")
                return
            if remaining_components:
                QMessageBox.warning(
                    self, "Teslim Edilen Eksik",
                    "Durum 'Teslim Edildi' olduğunda bu teslimattaki tüm bileşenlerin kalan değeri 0 olmalıdır.\n\n"
                    "Eksik kalan bileşenler:\n• " + "\n• ".join(remaining_components),
                )
                return
        elif all_delivered:
            QMessageBox.warning(
                self, "Durum Uyumsuz",
                "Bu teslimatta tüm bileşenlerin kalanı 0. Kaydetmeden önce Durum alanını 'Teslim Edildi' yapın.",
            )
            return

        self.result = DeliveryInfo(
            name=self.name.text().strip(),
            status=self.status.currentText(),
            acceptance_date=flexible_or_blank(acc_text),
            note=self.note.text().strip(),
            planned_acceptance_date=flexible_or_blank(plan_acc_text),
            planned=planned,
            delivered=delivered,
            t0_date=iso_or_blank(t0_text),
            t0_months=int(getattr(self.system, "t0_months", self._delivery_t0_months) or 0),
            completion_date=completion,
            delivery_user="" if self.delivery_user_combo.currentIndex() <= 0 else self.delivery_user_combo.currentText().strip(),
            component_units=component_units,
        )
        self.accept()









