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

class SystemDialog(StyledDialog):
    def __init__(
        self,
        store: SystemTypeStore,
        platform: str,
        default_name: str = "Sistem 1",
        parent=None,
        existing_system: Optional[SystemInfo] = None,
        edit_mode: bool = False,
        pre_selected: Optional[List[str]] = None,
        default_t0_date: str = "",
        events_provider: Optional[Callable[[], List[dict]]] = None,
    ):
        super().__init__("Sistemi Düzenle" if edit_mode else "Sistem Ekle", parent)
        self.store = store
        self.platform = platform
        self.default_name = default_name
        self.existing_system = existing_system
        self.edit_mode = edit_mode
        self.default_t0_date = str(default_t0_date or "")
        self.external_events_provider = events_provider
        # pre_selected: edit modunda hangi bilesenlerin secili gosterilecegi
        self.pre_selected: Optional[set] = set(pre_selected) if pre_selected is not None else None
        initial_keys = pre_selected if pre_selected is not None else (getattr(existing_system, "components", {}) or {}).keys()
        self.initial_component_keys = set(initial_keys or [])
        self.result: Optional[SystemInfo] = None
        try:
            self.system_types = list(self.store.list_system_type_names(self.platform))
        except Exception:
            self.system_types = []
        self.resize(560, 720)
        self.inputs: Dict[str, QCheckBox] = {}
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 10, 22, 16)
        root.setSpacing(10)

        root.addWidget(form_label("Sistem Adı"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Örn: Sistem 1")
        self.name.setText(self.default_name)
        self.name.selectAll()
        root.addWidget(self.name)

        # Sistem seviyesinde tarih widget oluşturulmaz; tarih bilgisi teslimatlarda tutulur.

        # ── Sistem Tipi / Bileşen Paketi: sadece hızlı seçim sağlar ──
        type_card = QFrame()
        type_card.setObjectName("systemFormCard")
        type_lay = QGridLayout(type_card)
        type_lay.setContentsMargins(10, 8, 10, 8)
        type_lay.setHorizontalSpacing(8)
        type_lay.setVerticalSpacing(6)
        type_lay.setColumnStretch(0, 1)

        type_lay.addWidget(form_label("Sistem Tipi"), 0, 0)
        self.system_type_combo = QComboBox()
        self.system_type_combo.setMinimumHeight(34)
        self.system_type_combo.addItem("Tip seçiniz...")
        for t in self.system_types:
            self.system_type_combo.addItem(t)
        type_lay.addWidget(self.system_type_combo, 1, 0)

        self.apply_type_btn = QPushButton("Tipi Uygula")
        self.apply_type_btn.setObjectName("secondary")
        self.apply_type_btn.setMinimumHeight(34)
        self.apply_type_btn.clicked.connect(self.apply_selected_system_type)
        type_lay.addWidget(self.apply_type_btn, 1, 1)
        root.addWidget(type_card)

        comp_head = QHBoxLayout()
        comp_head.addWidget(form_label("Bileşenler"), 0)
        self.selected_count_lbl = QLabel("0 seçili")
        self.selected_count_lbl.setObjectName("selectionPill")
        comp_head.addWidget(self.selected_count_lbl, 0)
        comp_head.addStretch(1)
        self.select_all_btn = QPushButton("Tümünü Seç")
        self.select_all_btn.setObjectName("secondary")
        self.select_all_btn.setMinimumHeight(32)
        self.clear_all_btn = QPushButton("Hiçbiri")
        self.clear_all_btn.setObjectName("secondary")
        self.clear_all_btn.setMinimumHeight(32)
        comp_head.addWidget(self.select_all_btn)
        comp_head.addWidget(self.clear_all_btn)
        root.addLayout(comp_head)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Bileşen ara...")
        root.addWidget(self.search_input)

        assigned = self.store.assigned_components(self.platform)
        existing_keys = list((self.existing_system.components if self.existing_system else {}).keys())
        extras = [c for c in existing_keys if c not in assigned]
        comps = assigned + extras
        if not comps:
            warn = QLabel("Bu platforma atanmış bileşen yok. Önce Bileşen Yönetimi ekranından platforma bileşen atayın.")
            warn.setObjectName("warning")
            warn.setWordWrap(True)
            root.addWidget(warn)

        self.comp_table = QTableWidget(len(comps), 2)
        self.comp_table.setObjectName("systemCompTable")
        configure_table(self.comp_table, compact=True)
        self.comp_table.setHorizontalHeaderLabels(["", "Bileşen"])
        self.comp_table.setSelectionMode(QTableWidget.NoSelection)
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.horizontalHeader().setVisible(False)
        self.comp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.comp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comp_table.setColumnWidth(0, 38)
        self.comp_table.setMinimumHeight(230)

        for r, comp in enumerate(comps):
            cell_wrap = QWidget()
            cell_layout = QHBoxLayout(cell_wrap)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            if self.edit_mode and self.existing_system:
                if self.pre_selected is not None:
                    is_checked = comp in self.pre_selected
                else:
                    # Sadece qty > 0 olan bilesenleri secili goster
                    is_checked = comp in existing_keys and self.existing_system.components.get(comp, 0) > 0
            else:
                is_checked = False
            cb.setChecked(is_checked)
            cb.stateChanged.connect(lambda _state, row=r: self._sync_component_row_style(row))
            cb.stateChanged.connect(lambda _state: self.update_selected_count())
            cell_layout.addWidget(cb)
            self.comp_table.setCellWidget(r, 0, cell_wrap)

            name_item = QTableWidgetItem(comp)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.comp_table.setItem(r, 1, name_item)
            self.comp_table.setRowHeight(r, 31)
            self.inputs[comp] = cb
            self._sync_component_row_style(r)

        root.addWidget(self.comp_table, 1)
        self.update_selected_count()
        self.search_input.textChanged.connect(self.filter_components)
        self.comp_table.cellClicked.connect(self.on_component_cell_clicked)
        self.select_all_btn.clicked.connect(self.select_all_components)
        self.clear_all_btn.clicked.connect(self.clear_all_components)

        row = QHBoxLayout()
        self.save_type_btn = QPushButton("Seçimi Tip Olarak Kaydet")
        self.save_type_btn.setObjectName("secondary")
        self.save_type_btn.clicked.connect(self.save_selection_as_system_type)
        row.addWidget(self.save_type_btn)
        row.addStretch()
        save = QPushButton("Güncelle" if self.edit_mode else "Sistemi Ekle")
        save.clicked.connect(self.save)
        row.addWidget(save)
        root.addLayout(row)

    def update_selected_count(self):
        if hasattr(self, "selected_count_lbl"):
            self.selected_count_lbl.setText(f"{len(self.selected_components())} seçili")

    def _sync_component_row_style(self, row: int):
        cb = self._row_checkbox(row) if hasattr(self, "comp_table") else None
        checked = bool(cb and cb.isChecked())

        bg = QColor("#dcecff") if checked else QColor("#ffffff")
        fg = QColor("#1f5be3") if checked else QColor("#0f172a")

        cell_wrap = self.comp_table.cellWidget(row, 0)
        if cell_wrap:
            cell_wrap.setStyleSheet(f"background:{bg.name()};")

        for c in range(self.comp_table.columnCount()):
            item = self.comp_table.item(row, c)
            if item:
                item.setBackground(bg)
                item.setForeground(fg)

        name_item = self.comp_table.item(row, 1)
        if name_item:
            # Eski tik varsa temizle, ismi saf haliyle tut.
            raw = str(
                name_item.data(Qt.UserRole)
                or name_item.text().replace("✓", "").strip()
            )

            name_item.setData(Qt.UserRole, raw)
            name_item.setText(raw)
            name_item.setForeground(fg)

    def selected_components(self) -> List[str]:
        return [comp for comp, cb in self.inputs.items() if cb.isChecked()]

    def apply_selected_system_type(self):
        type_name = self.system_type_combo.currentText().strip()
        if not type_name or type_name == "Tip seçiniz...":
            QMessageBox.information(self, "Sistem Tipi", "Uygulamak için bir sistem tipi seçin.")
            return
        try:
            comps = self.store.get_system_type_components(type_name, self.platform)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Sistem tipi okunamadı:\n{exc}")
            return
        if not comps:
            QMessageBox.information(self, "Sistem Tipi", "Bu sistem tipinde kayıtlı bileşen bulunamadı.")
            return
        comp_set = set(comps)
        for comp, cb in self.inputs.items():
            cb.setChecked(comp in comp_set)

    def save_selection_as_system_type(self):
        comps = self.selected_components()
        if not comps:
            QMessageBox.warning(self, "Eksik", "Tip olarak kaydetmek için en az bir bileşen seçin.")
            return
        default_name = ""
        current = self.system_type_combo.currentText().strip()
        if current and current != "Tip seçiniz...":
            default_name = current
        type_name, ok = QInputDialog.getText(
            self,
            "Sistem Tipi Kaydet",
            "Tip adı:",
            QLineEdit.Normal,
            default_name,
        )
        if not ok:
            return
        type_name = type_name.strip()
        if not type_name:
            QMessageBox.warning(self, "Eksik", "Tip adı girin.")
            return
        try:
            saved_count = self.store.save_system_type(type_name, self.platform, comps)
        except Exception as exc:
            QMessageBox.warning(self, "Sistem Tipi", f"Tip kaydedilemedi:\n{exc}")
            return

        # Kaydedilen tip sözleşme kaydı beklemeden hemen dropdown'a gelsin.
        current = self.system_type_combo.currentText().strip()
        self.system_type_combo.blockSignals(True)
        self.system_type_combo.clear()
        self.system_type_combo.addItem("Tip seçiniz...")
        try:
            for t in self.store.list_system_type_names(self.platform):
                self.system_type_combo.addItem(t)
        except Exception:
            if self.system_type_combo.findText(type_name) < 0:
                self.system_type_combo.addItem(type_name)
        self.system_type_combo.blockSignals(False)
        idx = self.system_type_combo.findText(type_name)
        if idx >= 0:
            self.system_type_combo.setCurrentIndex(idx)
        elif current:
            self.system_type_combo.setCurrentText(current)

        QMessageBox.information(self, "Sistem Tipi", f"'{type_name}' sistem tipi kaydedildi. ({saved_count} bileşen)")

    def _row_checkbox(self, row: int) -> Optional[QCheckBox]:
        cell = self.comp_table.cellWidget(row, 0)
        if not cell:
            return None
        cb = cell.findChild(QCheckBox)
        return cb

    def on_component_cell_clicked(self, row: int, col: int):
        if col not in (0, 1):
            return
        cb = self._row_checkbox(row)
        if cb:
            cb.setChecked(not cb.isChecked())

    def select_all_components(self):
        for r in range(self.comp_table.rowCount()):
            cb = self._row_checkbox(r)
            if cb:
                cb.setChecked(True)

    def clear_all_components(self):
        for r in range(self.comp_table.rowCount()):
            cb = self._row_checkbox(r)
            if cb:
                cb.setChecked(False)

    def filter_components(self, text: str):
        def norm(s: str) -> str:
            return str(s or "").strip().lower().replace("ı", "i").replace("İ", "i")
        q = norm(text)
        for r in range(self.comp_table.rowCount()):
            item = self.comp_table.item(r, 1)
            name = norm(item.text() if item else "")
            self.comp_table.setRowHidden(r, bool(q and q not in name))

    def _recalc_completion(self):
        return

    def date_picker_events(self) -> List[dict]:
        if callable(self.external_events_provider):
            try:
                return list(self.external_events_provider() or [])
            except Exception:
                return []
        return []

    def save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik", "Sistem adı girin.")
            return
        t0_text = ""
        old = self.existing_system.components if (self.edit_mode and self.existing_system) else {}
        selected = set(self.selected_components())
        removed = []
        if self.edit_mode and self.existing_system:
            removed = sorted(self.initial_component_keys - selected, key=lambda x: str(x).lower())
            if removed:
                shown = "\n".join(f"• {name}" for name in removed[:12])
                if len(removed) > 12:
                    shown += f"\n• ... ve {len(removed) - 12} bileşen daha"
                if not ask_yes_no(
                    self,
                    "Bileşenler Silinecek",
                    "Aşağıdaki bileşenlerin onay kutusunu kaldırdınız. Güncelleme sonrası bu bileşenler "
                    "sistemden ve bu sisteme ait teslimatlardan silinecek; ilgili değer hücreleri sıfırlanacak.\n\n"
                    f"{shown}\n\nOnaylıyor musunuz?",
                ):
                    return
        comps = {comp: old.get(comp, 0.0) for comp in self.inputs.keys() if comp in selected}
        if not comps:
            QMessageBox.warning(self, "Eksik", "En az bir bileşen seçin.")
            return
        self.result = SystemInfo(
            name=name,
            components=comps,
            t0_date="",
            t0_months=0,
            completion_date="",
            status=getattr(self.existing_system, "status", "Başlanmadı") or "Başlanmadı",
            acceptance_date=getattr(self.existing_system, "acceptance_date", "") or "",
        )
        self.result.removed_components = set(removed)
        self.accept()


