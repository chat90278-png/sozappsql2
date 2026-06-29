# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional, Tuple

from src.models.app_models import SystemInfo, TagDef
from src.services.excel_store import ExcelStore
from src.ui.delegates import CenterTableDelegate
from src.ui.dialogs.styled_dialog import StyledDialog, SystemTypeStore
from src.ui.widgets.user_select import MultiUserSelectWidget
from src.ui.widgets.platform_select import PlatformSelectWidget

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QMessageBox, QFrame, QCheckBox,
    QHeaderView, QTextEdit, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QInputDialog,
)


def form_label(txt):
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l


def section_label(text):
    l = QLabel(text)
    l.setObjectName("sectionTitle")
    return l


def configure_table(table: QTableWidget, compact: bool = False):
    table.setItemDelegate(CenterTableDelegate(table))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.horizontalHeader().setMinimumHeight(42 if not compact else 34)
    table.verticalHeader().setDefaultSectionSize(34 if not compact else 28)
    table.setWordWrap(False)

class MultiSystemDialog(StyledDialog):
    def __init__(
        self,
        store: SystemTypeStore,
        platform: str,
        contract_t0_date: str = "",
        existing_names: Optional[List[str]] = None,
        parent=None,
        events_provider: Optional[Callable[[], List[dict]]] = None,
    ):
        super().__init__("Çoklu Sistem Ekle", parent)
        self.store = store
        self.platform = str(platform or "")
        self.contract_t0_date = str(contract_t0_date or "")
        self.existing_names = set(existing_names or [])
        self.external_events_provider = events_provider
        self.result: List[SystemInfo] = []
        self.drafts: List[dict] = []
        self.current_index = 0
        self._loading = False
        self.component_rows: Dict[str, QCheckBox] = {}
        self.components = list(self.store.assigned_components(self.platform))
        try:
            self.system_types = list(self.store.list_system_type_names(self.platform))
        except Exception:
            self.system_types = []
        self.resize(1120, 760)
        self.build()
        self.add_blank_system(select=True)

    def build(self):
        self.setStyleSheet(self.styleSheet() + """
        QFrame#multiShell { background:#eef3f8; border:1px solid #cbd8e8; border-radius:14px; }
        QFrame#multiLeft, QFrame#multiMiddle { background:#ffffff; border:1px solid #d8e4f0; border-radius:14px; }
        QLabel#multiTitle { background:transparent; color:#102033; font-weight:950; font-size:14px; }
        QLabel#miniPill { background:#dbeafe; color:#1f5be3; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#miniPillGreen { background:#dcfce7; color:#16a34a; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#miniPillOrange { background:#fff7ed; color:#ea580c; border-radius:10px; padding:3px 8px; font-size:11px; font-weight:950; }
        QLabel#typeHint { background:transparent; color:#64748b; font-size:11px; font-weight:750; }
        QFrame#dateStrip { background:#f8fbff; border:1px solid #d8e4f0; border-radius:12px; }
        QFrame#saveTypeStrip { background:#f8fbff; border:1px dashed #93c5fd; border-radius:10px; }
        QListWidget#multiSystemList { background:transparent; border:0; outline:0; }
        QListWidget#multiSystemList::item { border:0; padding:0; margin:0; }
        QTableWidget#multiComponentTable { background:#ffffff; border:1px solid #d8e4f0; border-radius:10px; gridline-color:#edf2f7; }
        QTableWidget#multiComponentTable::item { border-bottom:1px solid #edf2f7; padding:6px 8px; }
        QLineEdit#qtyCellInput { padding:3px; border-radius:7px; font-weight:950; qproperty-alignment: AlignCenter; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(14)
        root.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("multiLeft")
        left.setFixedWidth(300)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(10)

        left_head = QHBoxLayout()
        systems_title = QLabel("Sistemler")
        systems_title.setObjectName("multiTitle")
        left_head.addWidget(systems_title, 1)
        add_btn = QPushButton("+ Sistem")
        add_btn.clicked.connect(lambda: self.add_blank_system(select=True))
        left_head.addWidget(add_btn, 0)
        left_lay.addLayout(left_head)

        self.system_list = QListWidget()
        self.system_list.setObjectName("multiSystemList")
        self.system_list.currentRowChanged.connect(self.select_draft)
        left_lay.addWidget(self.system_list, 1)

        duplicate_btn = QPushButton("Bu sistemi çoğalt")
        duplicate_btn.setObjectName("secondary")
        duplicate_btn.clicked.connect(self.duplicate_current)
        left_lay.addWidget(duplicate_btn)
        delete_btn = QPushButton("Seçili sistemi sil")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self.delete_current)
        left_lay.addWidget(delete_btn)
        body.addWidget(left, 0)

        middle = QFrame()
        middle.setObjectName("multiMiddle")
        mid = QVBoxLayout(middle)
        mid.setContentsMargins(12, 12, 12, 12)
        mid.setSpacing(10)
        body.addWidget(middle, 1)

        mid.addWidget(form_label("Sistem Adı"))
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self.on_name_changed)
        mid.addWidget(self.name_edit)

        # Çoklu sistemde tarih widget oluşturulmaz; tarih bilgisi teslimatlarda tutulur.

        type_row = QGridLayout()
        type_row.setHorizontalSpacing(10)
        type_row.setVerticalSpacing(6)
        type_row.addWidget(form_label("Sistem Tipi / opsiyonel"), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.type_combo.addItem(t)
        type_row.addWidget(self.type_combo, 1, 0)
        apply_btn = QPushButton("Tipi Uygula")
        apply_btn.setObjectName("secondary")
        apply_btn.clicked.connect(self.apply_selected_type)
        type_row.addWidget(apply_btn, 1, 1)
        hint = QLabel("Tip seçmek zorunlu değil. Tip seçilmezse bileşenleri aşağıdan manuel seçip adet girebilirsin.")
        hint.setObjectName("typeHint")
        type_row.addWidget(hint, 2, 0, 1, 2)
        type_row.setColumnStretch(0, 1)
        mid.addLayout(type_row)

        comp_head = QHBoxLayout()
        comp_title = QLabel("Bileşenler")
        comp_title.setObjectName("multiTitle")
        comp_head.addWidget(comp_title, 0)
        self.selected_count_lbl = QLabel("0 seçili")
        self.selected_count_lbl.setObjectName("miniPill")
        comp_head.addWidget(self.selected_count_lbl, 0)
        comp_head.addStretch()
        select_all = QPushButton("Tümünü Seç")
        select_all.setObjectName("secondary")
        select_all.clicked.connect(self.select_all_components)
        clear_all = QPushButton("Hiçbiri")
        clear_all.setObjectName("secondary")
        clear_all.clicked.connect(self.clear_components)
        comp_head.addWidget(select_all)
        comp_head.addWidget(clear_all)
        mid.addLayout(comp_head)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Bileşen ara...")
        self.search_input.textChanged.connect(self.filter_components)
        mid.addWidget(self.search_input)

        self.comp_table = QTableWidget(0, 3)
        self.comp_table.setObjectName("multiComponentTable")
        configure_table(self.comp_table, compact=True)
        self.comp_table.setHorizontalHeaderLabels(["", "Bileşen", "Adet"])
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.setSelectionMode(QTableWidget.NoSelection)
        self.comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.comp_table.setColumnWidth(0, 34)
        self.comp_table.setColumnWidth(2, 96)
        self.comp_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.comp_table.itemChanged.connect(self.on_component_table_item_changed)
        self.comp_table.setMinimumHeight(330)
        mid.addWidget(self.comp_table, 1)

        save_type = QFrame()
        save_type.setObjectName("saveTypeStrip")
        st_lay = QHBoxLayout(save_type)
        st_lay.setContentsMargins(10, 8, 10, 8)
        st_lay.setSpacing(10)
        st_hint = QLabel("Bu sistemde seçtiğin bileşen/adet kombinasyonunu daha sonra tekrar kullanmak için tip olarak kaydet.")
        st_hint.setObjectName("typeHint")
        st_hint.setWordWrap(True)
        st_lay.addWidget(st_hint, 1)
        save_type_btn = QPushButton("Bunu Tip Olarak Kaydet")
        save_type_btn.setObjectName("secondary")
        save_type_btn.clicked.connect(self.save_current_as_type)
        st_lay.addWidget(save_type_btn, 0)
        mid.addWidget(save_type)

        footer = QHBoxLayout()
        footer.setContentsMargins(16, 10, 16, 12)
        self.system_count_badge = QLabel("")
        self.system_count_badge.setObjectName("miniPill")
        self.total_qty_badge = QLabel("")
        self.total_qty_badge.setObjectName("miniPill")
        self.warning_badge = QLabel("")
        self.warning_badge.setObjectName("miniPillOrange")
        footer.addWidget(self.system_count_badge, 0)
        footer.addWidget(self.total_qty_badge, 0)
        footer.addWidget(self.warning_badge, 0)
        footer.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        self.submit_btn = QPushButton("Sistemleri Ekle")
        self.submit_btn.clicked.connect(self.accept_drafts)
        footer.addWidget(cancel)
        footer.addWidget(self.submit_btn)
        root.addLayout(footer)

    def date_picker_events(self) -> List[dict]:
        if callable(self.external_events_provider):
            try:
                return list(self.external_events_provider() or [])
            except Exception:
                return []
        return []

    def _draft_components(self, draft: dict) -> Dict[str, int]:
        return {str(k): int(v) for k, v in (draft.get("components") or {}).items() if int(v or 0) > 0}

    def make_unique_system_name(self) -> str:
        used = {normalize_sheet_name(n) for n in self.existing_names}
        used.update(normalize_sheet_name(str(d.get("name", ""))) for d in self.drafts)
        i = 1
        while True:
            name = f"Sistem {i}"
            if normalize_sheet_name(name) not in used:
                return name
            i += 1

    def make_blank_draft(self) -> dict:
        return {
            "name": self.make_unique_system_name(),
            "t0_date": "",
            "t0_months": 0,
            "completion_date": "",
            "system_type": "",
            "components": {},
        }

    def add_blank_system(self, select: bool = True):
        self.drafts.append(self.make_blank_draft())
        self.refresh_system_list(keep_row=len(self.drafts) - 1 if select else self.current_index)

    def duplicate_current(self):
        if not self.drafts:
            return
        src = copy.deepcopy(self.drafts[self.current_index])
        src["name"] = self.make_unique_system_name()
        self.drafts.append(src)
        self.refresh_system_list(keep_row=len(self.drafts) - 1)

    def delete_current(self):
        if len(self.drafts) <= 1:
            QMessageBox.information(self, "Sistem silinemez", "En az 1 sistem kalmalı.")
            return
        self.drafts.pop(self.current_index)
        self.refresh_system_list(keep_row=min(self.current_index, len(self.drafts) - 1))

    def refresh_system_list(self, keep_row: Optional[int] = None, reload_form: bool = True):
        target = self.current_index if keep_row is None else int(keep_row)
        self.system_list.blockSignals(True)
        self.system_list.clear()
        for idx, draft in enumerate(self.drafts):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 72))
            self.system_list.addItem(item)
            self.system_list.setItemWidget(item, self.build_system_card(draft, idx == target))
        if self.drafts:
            target = max(0, min(target, len(self.drafts) - 1))
            self.current_index = target
            self.system_list.setCurrentRow(target)
        self.system_list.blockSignals(False)
        if self.drafts and reload_form:
            self.load_current_draft()
        self.update_footer()

    def build_system_card(self, draft: dict, selected: bool) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background:%s; border:1px solid %s; border-radius:13px; } QLabel { background:transparent; color:%s; }"
            % ("#0b2f6b" if selected else "#ffffff", "#061f49" if selected else "#cbdff4", "#ffffff" if selected else "#0f172a")
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        top = QHBoxLayout()
        name = QLabel(str(draft.get("name") or "Sistem"))
        name.setStyleSheet("font-weight:950; font-size:13px;")
        top.addWidget(name, 1)
        count = QLabel(f"{len(self._draft_components(draft))} bileşen")
        count.setObjectName("miniPillGreen")
        top.addWidget(count, 0)
        lay.addLayout(top)
        meta = QHBoxLayout()
        meta.setSpacing(6)
        typ = str(draft.get("system_type") or "").strip() or "Özel seçim"
        typ_lbl = QLabel(typ)
        typ_lbl.setObjectName("miniPill")
        meta.addWidget(typ_lbl, 0)
        meta.addStretch()
        lay.addLayout(meta)
        return card

    def select_draft(self, row: int):
        if self._loading or row < 0 or row >= len(self.drafts):
            return
        self.current_index = row
        self.refresh_system_list(keep_row=row)

    def current_draft(self) -> dict:
        return self.drafts[self.current_index]

    def load_current_draft(self):
        if not self.drafts:
            return
        draft = self.current_draft()
        self._loading = True
        try:
            self.name_edit.setText(str(draft.get("name") or ""))
            typ = str(draft.get("system_type") or "")
            idx = self.type_combo.findText(typ) if typ else 0
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.refresh_component_table()
        finally:
            self._loading = False
        self.update_selected_count()

    def recalc_current_completion(self):
        draft = self.current_draft()
        draft["t0_date"] = ""
        draft["t0_months"] = 0
        draft["completion_date"] = ""

    def on_name_changed(self, text: str):
        if self._loading:
            return
        self.current_draft()["name"] = text.strip()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_t0_changed(self, text: str):
        if self._loading:
            return
        self.current_draft()["t0_date"] = text.strip()
        self.recalc_current_completion()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_months_changed(self, value: int):
        if self._loading:
            return
        self.current_draft()["t0_months"] = int(value)
        self.recalc_current_completion()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def set_custom_type(self):
        draft = self.current_draft()
        draft["system_type"] = ""
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentIndex(0)
        self.type_combo.blockSignals(False)

    def refresh_component_table(self):
        self.component_rows.clear()
        self.comp_table.blockSignals(True)
        self.comp_table.setRowCount(len(self.components))
        draft = self.current_draft()
        components = self._draft_components(draft)
        self.comp_table.setUpdatesEnabled(False)
        for r, comp in enumerate(self.components):
            qty = int(components.get(comp, 0))
            cb_wrap = QWidget()
            cb_lay = QHBoxLayout(cb_wrap)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            cb_lay.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(qty > 0)
            cb.toggled.connect(lambda checked, c=comp: self.on_component_checked(c, checked))
            cb_lay.addWidget(cb)
            self.comp_table.setCellWidget(r, 0, cb_wrap)

            name_item = QTableWidgetItem(comp)
            name_item.setFlags(Qt.ItemIsEnabled)
            self.comp_table.setItem(r, 1, name_item)

            qty_item = QTableWidgetItem(str(qty))
            qty_item.setData(Qt.UserRole, comp)
            qty_item.setTextAlignment(Qt.AlignCenter)
            qty_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.comp_table.setItem(r, 2, qty_item)
            self.component_rows[comp] = cb
            self.comp_table.setRowHeight(r, 36)
            self.apply_component_row_style(r, qty > 0)
        self.comp_table.setUpdatesEnabled(True)
        self.comp_table.blockSignals(False)
        self.filter_components(self.search_input.text())

    def apply_component_row_style(self, row: int, selected: bool):
        bg = QColor("#f8fbff") if selected else QColor("#ffffff")
        fg = QColor("#1f5be3") if selected else QColor("#0f172a")
        for col in range(self.comp_table.columnCount()):
            item = self.comp_table.item(row, col)
            if item:
                item.setBackground(bg)
                item.setForeground(fg)
        for col in (0, 2):
            widget = self.comp_table.cellWidget(row, col)
            if widget:
                widget.setStyleSheet(f"background:{bg.name()};")

    def component_row_index(self, comp: str) -> int:
        try:
            return self.components.index(comp)
        except ValueError:
            return -1

    def update_component_qty(self, comp: str, qty: int, manual: bool = True):
        qty = max(0, int(qty or 0))
        draft = self.current_draft()
        if qty > 0:
            draft.setdefault("components", {})[comp] = qty
        else:
            draft.setdefault("components", {}).pop(comp, None)
        cb = self.component_rows.get(comp)
        if cb:
            cb.blockSignals(True)
            cb.setChecked(qty > 0)
            cb.blockSignals(False)
        row = self.component_row_index(comp)
        if row >= 0:
            item = self.comp_table.item(row, 2)
            if item:
                self.comp_table.blockSignals(True)
                item.setText(str(qty))
                self.comp_table.blockSignals(False)
        row = self.component_row_index(comp)
        if row >= 0:
            self.apply_component_row_style(row, qty > 0)
        if manual and not self._loading:
            self.set_custom_type()
        self.update_selected_count()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def on_component_checked(self, comp: str, checked: bool):
        if self._loading:
            return
        current = int(self.current_draft().setdefault("components", {}).get(comp, 0) or 0)
        self.update_component_qty(comp, 1 if checked and current <= 0 else (current if checked else 0))

    def on_component_table_item_changed(self, item: QTableWidgetItem):
        if self._loading or not item or item.column() != 2:
            return
        comp_item = self.comp_table.item(item.row(), 1)
        comp = str((comp_item.text() if comp_item else item.data(Qt.UserRole)) or "").strip()
        if not comp:
            return
        text = str(item.text() or "").strip()
        qty = int(text) if text.isdigit() else 0
        if text != str(qty):
            self.comp_table.blockSignals(True)
            item.setText(str(qty))
            self.comp_table.blockSignals(False)
        self.update_component_qty(comp, qty)

    def on_qty_changed(self, comp: str, text: str):
        if self._loading:
            return
        qty = int(text) if str(text or "").isdigit() else 0
        self.update_component_qty(comp, qty)

    def normalize_qty_input(self, comp: str):
        row = self.component_row_index(comp)
        item = self.comp_table.item(row, 2) if row >= 0 else None
        text = item.text().strip() if item else ""
        qty = int(text) if text.isdigit() else 0
        self.update_component_qty(comp, qty)

    def update_selected_count(self):
        selected = len(self._draft_components(self.current_draft())) if self.drafts else 0
        self.selected_count_lbl.setText(f"{selected} seçili")
        self.update_footer()

    def filter_components(self, text: str):
        q = normalize_sheet_name(text)
        for r, comp in enumerate(self.components):
            self.comp_table.setRowHidden(r, bool(q and q not in normalize_sheet_name(comp)))

    def select_all_components(self):
        for comp in self.components:
            if int(self.current_draft().setdefault("components", {}).get(comp, 0) or 0) <= 0:
                self.update_component_qty(comp, 1, manual=False)
        self.set_custom_type()

    def clear_components(self):
        for comp in list(self.components):
            self.update_component_qty(comp, 0, manual=False)
        self.set_custom_type()

    def apply_selected_type(self):
        type_name = self.type_combo.currentText().strip()
        if not type_name or type_name == "Tip seçiniz...":
            QMessageBox.information(self, "Sistem Tipi", "Uygulamak için bir sistem tipi seçin.")
            return
        try:
            qty_map = self.store.get_system_type_component_quantities(type_name, self.platform)
        except Exception:
            qty_map = {}
        if not qty_map:
            try:
                qty_map = {comp: 1 for comp in self.store.get_system_type_components(type_name, self.platform)}
            except Exception as exc:
                QMessageBox.warning(self, "Sistem Tipi", f"Sistem tipi okunamadı:\n{exc}")
                return
        if not qty_map:
            QMessageBox.information(self, "Sistem Tipi", "Bu sistem tipinde kayıtlı bileşen bulunamadı.")
            return
        self.current_draft()["system_type"] = type_name
        self.current_draft()["components"] = {c: int(max(as_number(v), 0)) for c, v in qty_map.items() if c in self.components and as_number(v) > 0}
        self.refresh_component_table()
        self.update_selected_count()
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)

    def save_current_as_type(self):
        components = self._draft_components(self.current_draft())
        if not components:
            QMessageBox.warning(self, "Eksik", "Tip olarak kaydetmek için en az bir bileşen adedi girin.")
            return
        type_name, ok = QInputDialog.getText(self, "Sistem Tipi Kaydet", "Tip adı:", QLineEdit.Normal, "")
        if not ok:
            return
        type_name = type_name.strip()
        if not type_name:
            QMessageBox.warning(self, "Eksik", "Tip adı boş olamaz.")
            return
        existing = {normalize_sheet_name(n) for n in self.store.list_system_type_names(self.platform)}
        if normalize_sheet_name(type_name) in existing:
            QMessageBox.warning(self, "Çakışma", "Aynı isimde bir sistem tipi zaten var.")
            return
        try:
            saved_count = self.store.save_system_type(type_name, self.platform, components)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Tip kaydedilemedi:\n{exc}")
            return
        self.system_types = list(self.store.list_system_type_names(self.platform))
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.type_combo.addItem(t)
        idx = self.type_combo.findText(type_name)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_combo.blockSignals(False)
        self.current_draft()["system_type"] = type_name
        self.refresh_system_list(keep_row=self.current_index, reload_form=False)
        QMessageBox.information(self, "Sistem Tipi", f"'{type_name}' sistem tipi kaydedildi. ({saved_count} bileşen)")

    def warning_count(self) -> int:
        count = 0
        names = []
        existing_norm = {normalize_sheet_name(n) for n in self.existing_names}
        for draft in self.drafts:
            name_norm = normalize_sheet_name(str(draft.get("name", "")))
            if not name_norm or name_norm in existing_norm or name_norm in names:
                count += 1
            names.append(name_norm)
            if not self._draft_components(draft):
                count += 1
        return count

    def update_footer(self):
        total_qty = sum(sum(self._draft_components(d).values()) for d in self.drafts)
        self.system_count_badge.setText(f"{len(self.drafts)} sistem hazır")
        self.total_qty_badge.setText(f"{total_qty} toplam bileşen adedi")
        warnings = self.warning_count()
        self.warning_badge.setText(f"{warnings} uyarı")
        self.warning_badge.setVisible(warnings > 0)
        self.submit_btn.setText(f"{len(self.drafts)} Sistemi Ekle")

    def accept_drafts(self):
        existing_norm = {normalize_sheet_name(n) for n in self.existing_names}
        seen = set()
        out: List[SystemInfo] = []
        for draft in self.drafts:
            name = str(draft.get("name", "") or "").strip()
            norm = normalize_sheet_name(name)
            if not name:
                QMessageBox.warning(self, "Eksik", "Sistem adı boş olamaz.")
                return
            if norm in existing_norm or norm in seen:
                QMessageBox.warning(self, "Çakışma", f"'{name}' sistem adı zaten kullanılıyor.")
                return
            seen.add(norm)
            t0 = ""
            comps = self._draft_components(draft)
            if not comps:
                QMessageBox.warning(self, "Bileşen yok", f"{name}: bileşen adedi toplamı 0 olamaz.")
                return
            months = 0
            completion = ""
            out.append(SystemInfo(
                name=name,
                components={k: float(v) for k, v in comps.items()},
                t0_date="",
                t0_months=0,
                completion_date="",
                status="Başlanmadı",
                acceptance_date="",
            ))
        self.result = out
        self.accept()



# ─────────────────────────────────────────────────────────────────────────────
# UNIT TRACKING — Kuyruk no / seri no takibi için sol panel yardımcı sınıfları
# ─────────────────────────────────────────────────────────────────────────────





