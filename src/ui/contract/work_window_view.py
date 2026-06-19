from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from src.domain.contract_timing import contract_timing
from src.domain.flexible_date import is_tbd_contract_no, parse_flexible_date
from src.ui.contract.delivery_user_display import delivery_users_text


def update_system_metric_cards(self, sys_info):
    if not hasattr(self, "system_metric_labels"):
        return
    contract_no = getattr(getattr(self, "ci", None), "no", "")
    hide_date_cards = is_tbd_contract_no(contract_no)
    for key, card in getattr(self, "system_metric_cards", {}).items():
        card.setVisible(not (hide_date_cards and key in {"completion", "days", "acceptance"}))
    deliveries = self.deliveries.get(sys_info.name, []) if sys_info else []
    exact_plans = [parse_flexible_date(getattr(d, "planned_acceptance_date", "")) for d in deliveries]
    exact_plans = [d for d in exact_plans if d]
    near = min(exact_plans).isoformat() if exact_plans else ""
    has_flexible_plan = any(str(getattr(d, "planned_acceptance_date", "") or "").strip() for d in deliveries) and not near
    real_dates = [parse_flexible_date(getattr(d, "acceptance_date", "")) for d in deliveries]
    real_dates = [d for d in real_dates if d]
    acceptance = max(real_dates).isoformat() if real_dates else ""
    days = "-"
    if near:
        from datetime import date
        diff = (parse_flexible_date(near) - date.today()).days
        days = f"{diff} gün" if diff >= 0 else f"{abs(diff)} gün gecikti"
    values = {
        "completion": near or ("Belirsiz" if has_flexible_plan else "-"),
        "days": days,
        "acceptance": acceptance or "-",
        "user": delivery_users_text(deliveries),
    }
    for key, label in self.system_metric_labels.items():
        label.setText(values.get(key, "-"))


def refresh_summary_only(self):
    sys_info = self.current_system()
    if not sys_info:
        return
    self._updating_summary = True
    for r in range(self.summary.rowCount()):
        comp = self.summary.item(r, 0).text()
        qty = sys_info.components.get(comp, 0)
        delivered = sum(d.delivered.get(comp, 0) for d in self.deliveries.get(sys_info.name, []))
        note = str((getattr(sys_info, "component_notes", {}) or {}).get(comp, "") or "")
        vals = [comp, qty, delivered, qty - delivered, note]
        for c, v in enumerate(vals):
            it = self.summary.item(r, c)
            if it is None:
                it = QTableWidgetItem()
                self.summary.setItem(r, c, it)
            it.setText(self._fmt_num(v) if c in (1, 2, 3) else str(v))
            if c not in (1, 4):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    self._updating_summary = False


def refresh_right(self):
    sys_info = self.current_system()
    if not sys_info:
        self.title.setText("Sistem seçilmedi")
        self.update_system_metric_cards(None)
        self.summary.setRowCount(0)
        self.del_table.setRowCount(0)
        return
    self.title.setText(sys_info.name)
    self.update_system_metric_cards(sys_info)
    display_comps = self._component_display_keys(sys_info)

    self._updating_summary = True
    self.summary.setRowCount(len(display_comps))
    self.summary.setColumnCount(5)
    self.summary.setHorizontalHeaderLabels(["Bileşen", "Sözleşme Adedi", "Teslim Edilen", "Kalan", "Not"])
    if hasattr(self, "configure_summary_columns"):
        self.configure_summary_columns()
    for r, comp in enumerate(display_comps):
        qty = self._as_number(sys_info.components.get(comp, 0))
        delivered = sum(d.delivered.get(comp, 0) for d in self.deliveries.get(sys_info.name, []))
        note = str((getattr(sys_info, "component_notes", {}) or {}).get(comp, "") or "")
        vals = [comp, qty, delivered, qty - delivered, note]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(self._fmt_num(v) if c in (1, 2, 3) else str(v))
            if c in (1, 4):
                it.setFlags(it.flags() | Qt.ItemIsEditable)
            else:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if c in (1, 2, 3):
                it.setTextAlignment(Qt.AlignCenter)
            self.summary.setItem(r, c, it)
    self._updating_summary = False
    self.refresh_delivery_table()
