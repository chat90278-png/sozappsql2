# -*- coding: utf-8 -*-
"""
Otomatik kabul oluşturma eklentisi.

app.py içine yalnızca şunlar eklenir:
    from auto_accept import open_auto_accept_dialog

    auto_btn = QPushButton("Otomatik Kabul Oluştur")
    auto_btn.clicked.connect(lambda: open_auto_accept_dialog(self))
    dh.addWidget(auto_btn)
"""
from __future__ import annotations

import calendar
from datetime import datetime, date
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QInputDialog, QLineEdit,
    QComboBox, QSpinBox, QWidget, QFrame, QHeaderView, QStackedWidget,
)
from src.ui.date_picker import build_date_input

try:
    from src.models.app_models import DeliveryInfo
    from src.domain.constants import STATUS_VALUES
except Exception:
    from app_models import DeliveryInfo
    try:
        from constants import STATUS_VALUES
    except Exception:
        STATUS_VALUES = ["Başlanmadı", "Devam Ediyor", "Teslim Edildi"]


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


def parse_iso_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None




def to_iso(qdate: QDate) -> str:
    return f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"


def iso_or_blank(text: str) -> str:
    d = parse_iso_date(text)
    return d.isoformat() if d else ""

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
        self.acc_date_edits: List[QLineEdit] = []
        self.search_edits: List[QLineEdit] = []
        self.current_index = 0
        self._updating = False

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

        self.setWindowTitle("Otomatik Kabul Oluştur")
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

        user_grid = QGridLayout()
        user_grid.setHorizontalSpacing(14)
        user_grid.setVerticalSpacing(8)
        self.delivery_user_combo = QComboBox()
        self.delivery_user_combo.addItem("Seçiniz...")
        store = getattr(self.work, "store", None)
        if store is not None:
            for user in store.load_users(active_only=True):
                name = str(user.get("name", "") or "").strip()
                if name:
                    self.delivery_user_combo.addItem(name)
        user_grid.addWidget(self._form_label("Teslim Edilecek Kullanıcı"), 0, 0)
        user_grid.addWidget(self.delivery_user_combo, 1, 0)
        rv.addLayout(user_grid)

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
        save = QPushButton("Kabulleri Oluştur")
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

    def _legacy_build_acceptance_date_input_unused(self) -> tuple[QLineEdit, QWidget]:
        edit = QLineEdit()
        edit.setPlaceholderText("yyyy-aa-gg")

        btn = QPushButton("📅")
        btn.setObjectName("dateBtn")
        btn.setFixedSize(34, 34)
        btn.setToolTip("Takvimden tarih seç")

        wrap = QWidget(self)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(edit, 1)
        lay.addWidget(btn, 0)

        def choose_date():
            popup = QDialog(self, Qt.Popup | Qt.FramelessWindowHint)
            popup.setObjectName("calendarPopup")
            pop_lay = QVBoxLayout(popup)
            pop_lay.setContentsMargins(6, 6, 6, 6)
            pop_lay.setSpacing(0)
            cal = QCalendarWidget(popup)
            cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
            cal.setGridVisible(True)
            today = date.today()
            cal.setMaximumDate(QDate(today.year, today.month, today.day))
            disabled_fmt = QTextCharFormat()
            disabled_fmt.setBackground(QColor("#EEF2F7"))
            disabled_fmt.setForeground(QColor("#94A3B8"))
            month_days = calendar.monthrange(today.year, today.month)[1]
            for day_num in range(today.day + 1, month_days + 1):
                cal.setDateTextFormat(QDate(today.year, today.month, day_num), disabled_fmt)
            current = parse_iso_date(edit.text())
            if current:
                if current > today:
                    current = today
                cal.setSelectedDate(QDate(current.year, current.month, current.day))

            def on_pick(qd: QDate):
                edit.setText(to_iso(qd))
                popup.accept()

            cal.clicked.connect(on_pick)
            pop_lay.addWidget(cal)
            popup.adjustSize()
            popup.move(btn.mapToGlobal(QPoint(0, btn.height() + 2)))
            popup.exec()

        btn.clicked.connect(choose_date)
        return edit, wrap

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

        title = QLabel(f"{self.system.name} için Kabul / Teslimat")
        title.setObjectName("dialogTitle")
        title.setStyleSheet("font-weight:900; font-size:18px;")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        name = QLineEdit(f"Kabul {idx + 1}")
        status = QComboBox(); status.addItems(list(STATUS_VALUES))
        status.currentTextChanged.connect(lambda _text, i=idx: self.on_status_changed(i))
        t0 = QLineEdit(str(getattr(self.system, "t0_date", "") or getattr(self.work.ci, "t0_date", "") or ""))
        months = QSpinBox(); months.setRange(0, 999); months.setValue(int(getattr(self.system, "t0_months", 0) or 0))
        term = QLineEdit(str(getattr(self.system, "completion_date", "") or ""))
        note = QLineEdit(); note.setPlaceholderText("Not")
        acc, acc_wrap = self._build_acceptance_date_input()
        self.name_edits.append(name); self.status_boxes.append(status); self.t0_edits.append(t0)
        self.month_spins.append(months); self.term_edits.append(term); self.note_edits.append(note); self.acc_date_edits.append(acc)

        grid.addWidget(self._form_label("Kabul Adı"), 0, 0)
        grid.addWidget(name, 1, 0)
        grid.addWidget(self._form_label("Durum"), 0, 1)
        grid.addWidget(status, 1, 1)
        grid.addWidget(self._form_label("Kabul Tarihi"), 2, 0)
        grid.addWidget(acc_wrap, 3, 0)
        grid.addWidget(self._form_label("Not"), 2, 1)
        grid.addWidget(note, 3, 1)
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
            planned = qty / self.accept_count if self.divisible.get(comp) else 0
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
        self.progress_label.setText(f"Kabul {self.current_index + 1} / {self.accept_count}")
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

    def _norm_status_text(self, status: str) -> str:
        txt = str(status or "").strip().lower()
        repl = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
        for a, b in repl.items():
            txt = txt.replace(a, b)
        return " ".join(txt.split())

    def _is_delivered_status(self, status: str) -> bool:
        return self._norm_status_text(status) in {"teslim edildi", "tamamlandi"}

    def _accept_remaining_components(self, i: int) -> List[str]:
        tbl = self.tables[i]
        missing: List[str] = []
        for r, comp in enumerate(self.component_keys):
            planned = max(as_number(tbl.item(r, 1).text()), 0)
            delivered = max(as_number(tbl.item(r, 2).text()), 0)
            if planned > 0.0001 and max(planned - delivered, 0) > 0.0001:
                missing.append(comp)
        return missing

    def validate_accept(self, i: int) -> bool:
        if not self.name_edits[i].text().strip():
            QMessageBox.warning(self, "Eksik", "Kabul adı girin.")
            return False
        acc_text = self.acc_date_edits[i].text().strip()
        acc_date = parse_iso_date(acc_text) if acc_text else None
        if acc_text and not acc_date:
            QMessageBox.warning(self, "Tarih hatası", "Kabul Tarihi yyyy-aa-gg formatında olmalı.")
            return False
        if acc_date and acc_date > date.today():
            QMessageBox.warning(self, "Tarih hatası", "Kabul Tarihi bugünden ileri olamaz.")
            return False
        tbl = self.tables[i]
        active_planned = False
        for r, comp in enumerate(self.component_keys):
            planned = max(as_number(tbl.item(r, 1).text()), 0)
            delivered = max(as_number(tbl.item(r, 2).text()), 0)
            active_planned = active_planned or planned > 0.0001
            if delivered > planned:
                QMessageBox.warning(self, "Hata", f"{comp}: teslim edilen teslim edilecekten büyük olamaz.")
                return False
        remaining_components = self._accept_remaining_components(i)
        delivered_status = self._is_delivered_status(self.status_boxes[i].currentText())
        if delivered_status:
            if not acc_text:
                QMessageBox.warning(self, "Kabul Tarihi Gerekli", "Durum 'Teslim Edildi' olduğunda Kabul Tarihi zorunludur.")
                return False
            if remaining_components:
                QMessageBox.warning(
                    self,
                    "Teslim Edilen Eksik",
                    "Durum 'Teslim Edildi' olduğunda bu kabuldeki tüm bileşenlerin kalan değeri 0 olmalıdır.\n\n"
                    "Eksik kalan bileşenler:\n• " + "\n• ".join(remaining_components),
                )
                return False
        elif active_planned and not remaining_components:
            QMessageBox.warning(
                self,
                "Durum Uyumsuz",
                "Bu kabulde tüm bileşenlerin kalanı 0. Kaydetmeden önce Durum alanını 'Teslim Edildi' yapın.",
            )
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
        table.item(row, 3).setText(fmt_num(max(planned - delivered, 0)))
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
            qty = max(total_available - other_assigned, 0)
            tbl.item(r, 1).setText(fmt_num(qty))
            if as_number(tbl.item(r, 2).text()) > qty:
                tbl.item(r, 2).setText(fmt_num(qty))
            tbl.item(r, 3).setText(fmt_num(max(qty - as_number(tbl.item(r, 2).text()), 0)))
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
            remaining = max(contract_qty - other_assigned, 0)
            tbl.item(r, 1).setText(fmt_num(remaining))
            if as_number(tbl.item(r, 2).text()) > remaining:
                tbl.item(r, 2).setText(fmt_num(remaining))
            tbl.item(r, 3).setText(fmt_num(max(remaining - as_number(tbl.item(r, 2).text()), 0)))
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
                "Kabulleri oluşturmadan önce aşağıdaki bileşenleri kabullere dağıtın:\n\n" + "\n".join(missing),
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
            self.result_deliveries.append(DeliveryInfo(
                name=self.name_edits[i].text().strip(),
                status=self.status_boxes[i].currentText(),
                acceptance_date=iso_or_blank(self.acc_date_edits[i].text().strip()),
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
    count, ok = QInputDialog.getInt(work_window, "Otomatik Kabul", "Kaç kabule bölmek istersiniz?", 2, 1, 100, 1)
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
        QMessageBox.information(work_window, "Tanımlanabilir yok", "Bu sistemde kabullere tanımlanabilecek bileşen miktarı kalmadı.")
        return
    if existing:
        ans = QMessageBox.question(
            work_window,
            "Mevcut kabuller var",
            "Bu sisteme ait mevcut kabuller var. Otomatik kabuller mevcut listenin sonuna eklensin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
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
        QMessageBox.information(work_window, "Tamamlandı", f"{len(dlg.result_deliveries)} kabul oluşturuldu.")
