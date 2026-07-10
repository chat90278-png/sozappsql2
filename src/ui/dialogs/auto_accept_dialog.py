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
from src.domain.delivery_core import (
    ACTUAL_DATE_LABEL,
    build_delivery_info,
    distributable_target,
    is_delivered_status,
    planned_remaining_state,
    remaining_qty,
    split_evenly,
    validate_quantities,
    validate_status_rules,
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
        super().__init__(parent)
        self.work = work_window
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
        self.acc_date_edits: List[QLineEdit] = []
        self.search_edits: List[QLineEdit] = []
        self.current_index = 0
        self._updating = False
        self._syncing_delivery_user = False

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
            divisible = float(available).is_integer() and self.accept_count > 0 and int(available) % self.accept_count == 0
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
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        left = QFrame()
        left.setObjectName("contentPanel")
        left.setFixedWidth(360)
        left.setStyleSheet("QFrame#contentPanel{background:#F8FBFF; border:1px solid #D8E2EE; border-radius:12px;}")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(8)
        title = QLabel("Bileşen Atama Durumu")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:900; font-size:14px;")
        lv.addWidget(title)
        hint = QLabel("Tanımlanabilir değeri 0 olan bileşenler listeden gizlenir.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        lv.addWidget(hint)
        self.unassigned_table = QTableWidget(0, 3)
        self.unassigned_table.setObjectName("qtyTable")
        self.unassigned_table.setHorizontalHeaderLabels(["Bileşen", "Tanımlanmış", "Tanımlanabilir"])
        self.unassigned_table.verticalHeader().setVisible(False)
        self.unassigned_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.unassigned_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.unassigned_table.setShowGrid(True)
        self.unassigned_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.unassigned_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.unassigned_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.unassigned_table.setColumnWidth(1, 112)
        self.unassigned_table.setColumnWidth(2, 124)
        lv.addWidget(self.unassigned_table, 1)
        root.addWidget(left, 0)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(10)
        root.addWidget(right, 1)

        self.delivery_user_names = self._load_delivery_user_names()

        self.stack = QStackedWidget()
        for idx in range(self.accept_count):
            self.stack.addWidget(self._build_accept_card(idx))
        rv.addWidget(self.stack, 1)

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
        rv.addLayout(footer)
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

    def _build_accept_card(self, idx: int) -> QWidget:
        card = QFrame()
        card.setObjectName("contentPanel")
        card.setStyleSheet("QFrame#contentPanel{background:#EAF2FB; border:1px solid #D8E2EE; border-radius:12px;}")
        root = QVBoxLayout(card)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        title = QLabel(f"{self.system.name} için Teslimat")
        title.setObjectName("dialogTitle")
        title.setStyleSheet("font-weight:900; font-size:18px;")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        name = QLineEdit(f"Teslimat {idx + 1}")
        status = QComboBox(); status.addItems(list(STATUS_VALUES))
        status.currentTextChanged.connect(lambda _text, i=idx: self.on_status_changed(i))
        t0 = QLineEdit(str(getattr(self.system, "t0_date", "") or getattr(self.work.ci, "t0_date", "") or ""))
        months = QSpinBox(); months.setRange(0, 999); months.setValue(int(getattr(self.system, "t0_months", 0) or 0))
        term = QLineEdit(str(getattr(self.system, "completion_date", "") or ""))
        note = QLineEdit(); note.setPlaceholderText("Not")
        acc, acc_wrap = self._build_acceptance_date_input()
        self.name_edits.append(name); self.status_boxes.append(status); self.t0_edits.append(t0)
        self.month_spins.append(months); self.term_edits.append(term); self.note_edits.append(note); self.acc_date_edits.append(acc)

        grid.addWidget(self._form_label("Teslimat Adı"), 0, 0)
        grid.addWidget(name, 1, 0)
        grid.addWidget(self._form_label("Durum"), 0, 1)
        grid.addWidget(status, 1, 1)
        delivery_user_combo = self._build_delivery_user_combo()

        grid.addWidget(self._form_label("Gerçek Teslimat Tarihi"), 2, 0)
        grid.addWidget(acc_wrap, 3, 0)
        grid.addWidget(self._form_label("Not"), 2, 1)
        grid.addWidget(note, 3, 1)
        grid.addWidget(self._form_label("Teslim Edilecek Kullanıcı"), 4, 0)
        grid.addWidget(delivery_user_combo, 5, 0)
        root.addLayout(grid)

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
        tbl.itemChanged.connect(lambda item, t=tbl: self.on_table_changed(t, item))
        self.tables.append(tbl)
        search.textChanged.connect(lambda text, i=idx: self.filter_components(i, text))

        self._updating = True
        for r, comp in enumerate(self.component_keys):
            qty = max(as_number(self.unassigned_total.get(comp, 0)), 0)
            planned_values = split_evenly(qty, self.accept_count)
            planned = planned_values[idx] if planned_values else 0.0
            values = [comp, planned, 0, planned]
            for c, v in enumerate(values):
                item = QTableWidgetItem(fmt_num(v) if c else str(v))
                if c in (0, 3):
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                else:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
                if not self.divisible.get(comp):
                    item.setBackground(QColor("#FEF3C7"))
                tbl.setItem(r, c, item)
            tbl.setRowHeight(r, 30)
        self._updating = False
        root.addWidget(tbl, 1)
        return card

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

    def _status_validation_warning(self, error: str) -> tuple[str, str, str]:
        actual_label = "Gerçek Teslimat Tarihi"
        message = str(error or "").replace(ACTUAL_DATE_LABEL, actual_label)
        exact_core_message = (
            f"Tamamlanan kayıtta {actual_label} kesin YYYY-MM-DD olmalıdır. TBD kabul edilmez."
        )
        required_core_message = (
            f"Durum tamamlandı/teslim edildi olduğunda {actual_label} zorunludur."
        )
        if message == exact_core_message:
            return (
                "date",
                "Tarih hatası",
                "Teslim Edildi durumunda Gerçek Teslimat Tarihi kesin YYYY-MM-DD olmalı.",
            )
        if message == required_core_message:
            return (
                "status",
                "Gerçek Teslimat Tarihi Gerekli",
                "Durum 'Teslim Edildi' olduğunda Gerçek Teslimat Tarihi zorunludur.",
            )
        if message.startswith("Durum 'Teslim Edildi' olduğunda"):
            return "status", "Teslim Edilen Eksik", message
        if message.startswith("Bu teslimatta tüm bileşenlerin kalanı 0."):
            return "status", "Durum Uyumsuz", message
        return "date", "Tarih hatası", message

    def validate_accept(self, i: int) -> bool:
        if not self.name_edits[i].text().strip():
            QMessageBox.warning(self, "Eksik", "Teslimat adı girin.")
            return False
        acc_text = self.acc_date_edits[i].text().strip()
        planned, delivered = self._accept_quantity_maps(i)
        status_errors = validate_status_rules(
            self.status_boxes[i].currentText(),
            acc_text,
            "TBD",
            planned,
            delivered,
        )
        mapped_status_errors = [self._status_validation_warning(error) for error in status_errors]
        for phase, title, message in mapped_status_errors:
            if phase == "date":
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

        for phase, title, message in mapped_status_errors:
            if phase == "status":
                QMessageBox.warning(self, title, message)
                return False
        return True

    def on_status_changed(self, idx: int):
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
        if idx >= 0 and item.column() == 1 and self._is_delivered_status(self.status_boxes[idx].currentText()):
            delivered = planned
            table.item(row, 2).setText(fmt_num(delivered))
        if delivered > planned:
            delivered = planned
            table.item(row, 2).setText(fmt_num(delivered))
        table.item(row, 1).setText(fmt_num(planned))
        table.item(row, 3).setText(fmt_num(remaining_qty(planned, delivered)))
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
            tbl.item(r, 3).setText(fmt_num(remaining_qty(qty, as_number(tbl.item(r, 2).text()))))
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
            tbl.item(r, 3).setText(fmt_num(remaining_qty(remaining, as_number(tbl.item(r, 2).text()))))
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
            item = tbl.item(r, 0)
            name = self._norm_search(item.text() if item else "")
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

    def refresh_unassigned_panel(self):
        rows = []
        for comp in self.unassigned_total.keys():
            current_assigned = self._sum_planned(comp)
            assigned = max(as_number(self.existing_assigned.get(comp, 0)), 0) + current_assigned
            remaining = self.unassigned_total[comp] - current_assigned
            if abs(remaining) > 0.0001:
                rows.append((comp, assigned, remaining))
        self.unassigned_table.setRowCount(len(rows))
        for r, (comp, assigned, remaining) in enumerate(rows):
            has_issue = remaining < -0.0001
            bg = QColor("#FEE2E2") if has_issue else QColor("#FFFFFF")
            fg = QColor("#991B1B") if has_issue else QColor("#0F172A")
            for c, v in enumerate([comp, assigned, remaining]):
                item = QTableWidgetItem(fmt_num(v) if c else str(v))
                item.setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
                item.setBackground(bg)
                item.setForeground(fg)
                self.unassigned_table.setItem(r, c, item)
            self.unassigned_table.setRowHeight(r, 30)
        self.refresh_table_issue_highlights()

    def _sum_planned(self, comp: str) -> float:
        total = 0.0
        comp_idx = self.component_keys.index(comp)
        for tbl in self.tables:
            total += as_number(tbl.item(comp_idx, 1).text())
        return total

    def save(self):
        for i in range(self.accept_count):
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
                p = max(as_number(tbl.item(r, 1).text()), 0)
                d = max(as_number(tbl.item(r, 2).text()), 0)
                planned[comp] = p
                delivered[comp] = d
            self.result_deliveries.append(build_delivery_info(
                name=self.name_edits[i].text().strip(),
                status=self.status_boxes[i].currentText(),
                acceptance_date=flexible_or_blank(self.acc_date_edits[i].text().strip()),
                note=self.note_edits[i].text().strip(),
                planned=planned,
                delivered=delivered,
                t0_date=str(getattr(self.system, "t0_date", "") or self.t0_edits[i].text()).strip(),
                t0_months=int(getattr(self.system, "t0_months", self.month_spins[i].value()) or 0),
                completion_date=str(getattr(self.system, "completion_date", "") or self.term_edits[i].text()).strip(),
                delivery_user=delivery_user,
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
