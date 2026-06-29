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
from src.ui.message_boxes import ask_yes_no

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

class TagManagerDialog(StyledDialog):
    def __init__(self, store: ExcelStore, contract_index: Optional[List[dict]] = None, parent=None):
        super().__init__("Etiket Yönetimi", parent)
        self.store = store
        self.contract_index = list(contract_index or [])
        self.changed = False
        self.tags: List[TagDef] = []
        self.usage: Dict[str, int] = {}
        self.assignments_by_key: Dict[str, List[dict]] = {}
        self._contract_map: Dict[Tuple[str, str, str], dict] = {}
        self.selected_tag_key: Optional[str] = None
        self.selected_color = "#3B82F6"
        self._color_buttons: List[QPushButton] = []
        self._draft_tags: Dict[str, TagDef] = {}
        self._draft_order: List[str] = []
        self._draft_seq = 1
        self.resize(1240, 700)
        self.build()
        self._rebuild_contract_map()
        self.reload_data(keep_selection=False)

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Etiket Yönetimi")
        title.setObjectName("dialogTitle")
        top.addWidget(title, 1)
        new_btn = QPushButton("+ Yeni Etiket")
        new_btn.clicked.connect(self.new_tag)
        top.addWidget(new_btn, 0)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(310)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)
        ll.addWidget(form_label("Etiketler"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Etiket ara...")
        self.search.textChanged.connect(self.refresh_tag_list)
        ll.addWidget(self.search)
        self.tag_list = QListWidget()
        self.tag_list.setObjectName("tagList")
        self.tag_list.currentRowChanged.connect(self.on_tag_selected)
        self.tag_list.setAlternatingRowColors(False)
        ll.addWidget(self.tag_list, 1)
        body.addWidget(left, 0)

        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(10)
        body.addWidget(right, 1)

        detail_row = QHBoxLayout()
        detail_row.addWidget(section_label("ETİKET DETAYI"), 1)
        self.contract_count = QLabel("0 bağlı sözleşme")
        self.contract_count.setObjectName("ctxPill")
        detail_row.addWidget(self.contract_count, 0)
        rl.addLayout(detail_row)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        self.note_edit = QTextEdit()
        self.note_edit.setMinimumHeight(86)
        form.addWidget(form_label("Etiket Adı"), 0, 0)
        form.addWidget(self.name_edit, 1, 0)
        form.addWidget(form_label("Açıklama / Not"), 2, 0)
        form.addWidget(self.note_edit, 3, 0)

        color_box = QVBoxLayout()
        color_box.setContentsMargins(0, 0, 0, 0)
        color_box.setSpacing(6)
        color_box.addWidget(form_label("Renk Seçimi"))
        colors = ["#EF4444", "#F59E0B", "#22C55E", "#3B82F6", "#8B5CF6", "#EC4899", "#14B8A6", "#94A3B8"]
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        for c in colors:
            b = QPushButton("")
            b.setObjectName("colorDotBtn")
            b.setCheckable(True)
            b.setFixedSize(28, 28)
            b.setProperty("tag_color", c)
            b.setStyleSheet(
                "QPushButton { border-radius:14px; border:2px solid #e2e8f0; background:%s; } "
                "QPushButton:checked { border:3px solid #0f172a; }" % c
            )
            b.clicked.connect(lambda _=False, color=c: self.select_color(color))
            self._color_buttons.append(b)
            color_row.addWidget(b)
        color_row.addStretch()
        color_box.addLayout(color_row)
        self.active_check = QCheckBox("Etiket Aktif")
        self.active_check.setChecked(True)
        color_box.addWidget(self.active_check)
        form.addLayout(color_box, 0, 1, 4, 1)

        rl.addLayout(form)

        btn_row = QHBoxLayout()
        self.op_hint = QLabel("")
        self.op_hint.setObjectName("muted")
        btn_row.addWidget(self.op_hint, 1)
        btn_row.addStretch()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self.save_tag)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.reject)
        self.del_btn = QPushButton("Etiketi Sil")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self.delete_tag)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.del_btn)
        rl.addLayout(btn_row)

        rl.addWidget(section_label("Bu Etikete Bağlı Sözleşmeler"))
        self.contracts_table = QTableWidget(0, 6)
        configure_table(self.contracts_table, compact=True)
        self.contracts_table.setHorizontalHeaderLabels(["Platform", "Sözleşme No", "Kullanıcı", "Tür", "Durum", "Atama Tarihi"])
        self.contracts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rl.addWidget(self.contracts_table, 1)

    def _tag_key(self, name: str) -> str:
        return self.store._normalize_label(name)

    def _rebuild_contract_map(self):
        out: Dict[Tuple[str, str, str], dict] = {}
        for it in self.contract_index:
            key = (
                str(it.get("platform", "") or "").strip(),
                str(it.get("no", "") or "").strip(),
                str(it.get("type", "") or "").strip(),
            )
            out[key] = it
        self._contract_map = out

    def select_color(self, color: str):
        self.selected_color = str(color or "#3B82F6")
        for b in self._color_buttons:
            is_this = str(b.property("tag_color") or "").upper() == self.selected_color.upper()
            b.blockSignals(True)
            b.setChecked(is_this)
            b.blockSignals(False)

    def reload_data(self, keep_selection: bool = True):
        prev = self.selected_tag_key if keep_selection else None
        self.tags, self.assignments_by_key = self.store.load_tag_snapshot()
        self.usage = {}
        for k, vals in self.assignments_by_key.items():
            if vals:
                self.usage[k] = len(vals)
        self.refresh_tag_list()
        if prev:
            for i in range(self.tag_list.count()):
                it = self.tag_list.item(i)
                if str(it.data(Qt.UserRole) or "") == prev:
                    self.tag_list.setCurrentRow(i)
                    return
        if self.tag_list.count():
            self.tag_list.setCurrentRow(0)
        else:
            self.clear_detail_form()

    def _build_tag_row(self, color: str, name: str, count: int, active: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("tagListRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        dot = QLabel("●")
        dot.setObjectName("tagDot")
        dot.setStyleSheet(f"color:{color};")
        lay.addWidget(dot, 0)

        txt_col = QVBoxLayout()
        txt_col.setContentsMargins(0, 0, 0, 0)
        txt_col.setSpacing(1)
        name_lbl = QLabel(name)
        name_lbl.setObjectName("tagName")
        count_lbl = QLabel(f"{count} sözleşme")
        count_lbl.setObjectName("tagCount")
        txt_col.addWidget(name_lbl)
        txt_col.addWidget(count_lbl)
        lay.addLayout(txt_col, 1)

        st_lbl = QLabel("Aktif" if active else "Pasif")
        st_lbl.setObjectName("tagStateOn" if active else "tagStateOff")
        lay.addWidget(st_lbl, 0, Qt.AlignVCenter)
        return row

    def _apply_tag_row_state(self, row: Optional[QFrame], selected: bool):
        if row is None:
            return
        if selected:
            row.setStyleSheet(
                "QFrame#tagListRow { background:#dcecff; border-left:4px solid #1f5be3; border-radius:8px; }"
            )
        else:
            row.setStyleSheet(
                "QFrame#tagListRow { background:transparent; border-left:4px solid transparent; border-radius:8px; }"
            )

    def _refresh_tag_row_visuals(self):
        current = self.tag_list.currentRow()
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            roww = self.tag_list.itemWidget(item)
            self._apply_tag_row_state(roww, i == current)

    def _all_ui_tags(self) -> List[Tuple[str, TagDef, bool]]:
        out: List[Tuple[str, TagDef, bool]] = []
        for dk in self._draft_order:
            dt = self._draft_tags.get(dk)
            if dt is not None:
                out.append((dk, dt, True))
        for t in self.tags:
            out.append((self._tag_key(t.name), t, False))
        return out

    def _is_draft_key(self, key: str) -> bool:
        return str(key or "").startswith("__draft__:")

    def _make_unique_draft_name(self, base: str = "Yeni Etiket") -> str:
        used = {self._tag_key(t.name) for t in self.tags}
        used.update(self._tag_key(v.name) for v in self._draft_tags.values())
        name = base
        if self._tag_key(name) not in used:
            return name
        i = 2
        while True:
            candidate = f"{base} {i}"
            if self._tag_key(candidate) not in used:
                return candidate
            i += 1

    def refresh_tag_list(self):
        q = self._tag_key(self.search.text())
        current = self.selected_tag_key
        self.tag_list.clear()
        for key, t, _is_draft in self._all_ui_tags():
            if q and q not in self._tag_key(t.name):
                continue
            cnt = int(self.usage.get(key, 0))
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, key)
            item.setData(Qt.UserRole + 1, t.name)
            item.setSizeHint(QSize(0, 60))
            self.tag_list.addItem(item)
            roww = self._build_tag_row(t.color, t.name, cnt, bool(t.active))
            self._apply_tag_row_state(roww, key == current)
            self.tag_list.setItemWidget(item, roww)
        if current:
            for i in range(self.tag_list.count()):
                it = self.tag_list.item(i)
                if str(it.data(Qt.UserRole) or "") == current:
                    self.tag_list.setCurrentRow(i)
                    break
        if self.tag_list.count() and self.tag_list.currentRow() < 0:
            self.tag_list.setCurrentRow(0)
        if not self.tag_list.count():
            self.clear_detail_form()

    def clear_detail_form(self):
        self.selected_tag_key = None
        self.name_edit.clear()
        self.note_edit.clear()
        self.active_check.setChecked(True)
        self.select_color("#3B82F6")
        self.contract_count.setText("0 bağlı sözleşme")
        self.contracts_table.setRowCount(0)

    def on_tag_selected(self, row: int):
        if row < 0:
            self.clear_detail_form()
            return
        item = self.tag_list.item(row)
        if not item:
            self.clear_detail_form()
            return
        name = str(item.data(Qt.UserRole + 1) or "").strip()
        key = str(item.data(Qt.UserRole) or "")
        if self._is_draft_key(key):
            tag = self._draft_tags.get(key)
        else:
            tag = next((t for t in self.tags if self._tag_key(t.name) == key), None)
        if not tag:
            self.clear_detail_form()
            return
        self.selected_tag_key = key
        self.name_edit.setText(tag.name)
        self.note_edit.setPlainText(tag.note)
        self.active_check.setChecked(bool(tag.active))
        self.select_color(tag.color)
        self.refresh_assignments(tag.name if not self._is_draft_key(key) else "")
        self._refresh_tag_row_visuals()

    def refresh_assignments(self, tag_name: str):
        key = self._tag_key(tag_name)
        assigns = list(self.assignments_by_key.get(key, []))
        self.contract_count.setText(f"{len(assigns)} bağlı sözleşme")
        self.contracts_table.setUpdatesEnabled(False)
        self.contracts_table.setRowCount(len(assigns))
        for r, a in enumerate(assigns):
            key = (str(a.get("platform", "")), str(a.get("no", "")), str(a.get("type", "")))
            it = self._contract_map.get(key, {})
            vals = [
                key[0],
                key[1],
                str(it.get("user", "") or "-"),
                key[2],
                str(it.get("status", "") or "-"),
                str(a.get("assigned_at", "") or "-"),
            ]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(str(v))
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.contracts_table.setItem(r, c, cell)
        self.contracts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.contracts_table.setUpdatesEnabled(True)

    def new_tag(self):
        key = f"__draft__:{self._draft_seq}"
        self._draft_seq += 1
        draft = TagDef(name=self._make_unique_draft_name(), color="#3B82F6", note="", active=True)
        self._draft_tags[key] = draft
        self._draft_order.insert(0, key)
        self.selected_tag_key = key
        self.refresh_tag_list()
        for i in range(self.tag_list.count()):
            it = self.tag_list.item(i)
            if str(it.data(Qt.UserRole) or "") == key:
                self.tag_list.setCurrentRow(i)
                break
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def save_tag(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik", "Etiket adı boş olamaz.")
            return
        key = self._tag_key(name)
        same = next((t for t in self.tags if self._tag_key(t.name) == key), None)
        is_draft = self._is_draft_key(self.selected_tag_key or "")
        if self.selected_tag_key and (not is_draft) and same and self._tag_key(same.name) != self.selected_tag_key:
            QMessageBox.warning(self, "Çakışma", "Aynı isimde başka etiket var.")
            return
        if (not self.selected_tag_key or is_draft) and same:
            QMessageBox.warning(self, "Çakışma", "Bu etiket zaten var.")
            return

        old_name = ""
        if self.selected_tag_key and not is_draft:
            old = next((t for t in self.tags if self._tag_key(t.name) == self.selected_tag_key), None)
            old_name = str(old.name if old else "")

        tag = TagDef(
            name=name,
            color=self.selected_color,
            note=self.note_edit.toPlainText().strip(),
            active=bool(self.active_check.isChecked()),
        )
        # processEvents öncesi tüm işlem butonlarını kapat — reentrancy önleme
        self.save_btn.setEnabled(False)
        self.del_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        try:
            self.op_hint.setText("Etiket kaydediliyor...")
            QApplication.processEvents()
            self.store.upsert_tag_def(tag)
            if old_name and self._tag_key(old_name) != self._tag_key(name):
                self.store.rename_tag_assignments(old_name, name, tag.color)
                self.store.delete_tag_def(old_name)
            if is_draft and self.selected_tag_key:
                self._draft_tags.pop(self.selected_tag_key, None)
                self._draft_order = [k for k in self._draft_order if k != self.selected_tag_key]
            self.changed = True
            self.reload_data(keep_selection=False)
            self.op_hint.setText("")
            for i in range(self.tag_list.count()):
                it = self.tag_list.item(i)
                if str(it.data(Qt.UserRole) or "") == self._tag_key(name):
                    self.tag_list.setCurrentRow(i)
                    break
        finally:
            self.save_btn.setEnabled(True)
            self.del_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)

    def delete_tag(self):
        if not self.selected_tag_key:
            QMessageBox.warning(self, "Seçim", "Silmek için bir etiket seçin.")
            return
        if self._is_draft_key(self.selected_tag_key):
            self._draft_tags.pop(self.selected_tag_key, None)
            self._draft_order = [k for k in self._draft_order if k != self.selected_tag_key]
            self.refresh_tag_list()
            if self.tag_list.count():
                self.tag_list.setCurrentRow(0)
            else:
                self.clear_detail_form()
            return
        tag = next((t for t in self.tags if self._tag_key(t.name) == self.selected_tag_key), None)
        if not tag:
            return
        if not ask_yes_no(
            self,
            "Etiketi Sil",
            f"'{tag.name}' etiketi silinecek.\nBu etikete ait tüm atamalar da kaldırılır.\n\nDevam edilsin mi?",
        ):
            return
        # processEvents öncesi tüm işlem butonlarını kapat — reentrancy önleme
        self.save_btn.setEnabled(False)
        self.del_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        try:
            self.op_hint.setText("Etiket siliniyor...")
            QApplication.processEvents()
            self.store.delete_tag_def(tag.name)
            self.changed = True
            self.reload_data(keep_selection=False)
            self.op_hint.setText("")
        finally:
            self.save_btn.setEnabled(True)
            self.del_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)


