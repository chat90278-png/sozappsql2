from __future__ import annotations

import re
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem, QWidget, QVBoxLayout, QLabel, QTableWidget, QFrame, QHBoxLayout, QPushButton

from src.ui.contract.delivery_user_display import delivery_user_text


def _use_acceptance_terms(owner) -> bool:
    no = str(getattr(getattr(owner, "ci", None), "no", "") or "")
    return not bool(re.match(r"^\s*.+?\s*-\s*TBD\s*-\s*\d+\s*$", no, re.IGNORECASE))


def refresh_delivery_table(self):
    sys_info = self.current_system()
    if not sys_info:
        self.pinned_delivery.setRowCount(0)
        self.pinned_delivery.clearContents()
        self.del_table.setRowCount(0)
        return
    if _use_acceptance_terms(self):
        headers = ["", "Kabul Adı", "Durum", "Plan. Kabul", "Gerçekleşen Kabul", "Teslim Kullanıcısı", "Not"]
    else:
        headers = ["", "Teslimat Adı", "Durum", "Plan. Teslimat", "Gerçekleşen Teslimat", "Teslim Kullanıcısı", "Not"]
    self.del_table.clear()
    self.del_table.setColumnCount(len(headers))
    self.del_table.setHorizontalHeaderLabels(headers)
    self.del_table.horizontalHeader().setVisible(True)
    self.del_table.setRowCount(0)
    self._delivery_row_map = {}
    deliveries = self.deliveries.get(sys_info.name, [])
    for idx, d in enumerate(deliveries):
        r = self.del_table.rowCount()
        self.del_table.insertRow(r)
        self._delivery_row_map[r] = idx
        note = str(getattr(d, "note", "") or "").strip()
        note_display = note if note else "-"
        if len(note_display) > 80:
            note_display = f"{note_display[:77]}..."
        vals = ["▶", d.name, d.status, getattr(d, "planned_acceptance_date", "") or "-", d.acceptance_date or "-", delivery_user_text(d), note_display]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignCenter if c == 0 else Qt.AlignLeft | Qt.AlignVCenter)
            if c == 6 and note:
                it.setToolTip(note)
            self.del_table.setItem(r, c, it)
    self.del_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    if self.del_table.columnCount() > 0:
        self.del_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.del_table.setColumnWidth(0, 44)
    header_h = self.del_table.horizontalHeader().height() or 42
    row_h = self.del_table.verticalHeader().defaultSectionSize() or 34
    visible_rows = max(1, min(self.del_table.rowCount(), 4))
    target_h = header_h + (visible_rows * row_h) + 18
    self.del_table.setMinimumHeight(min(max(target_h, 118), 180))
    self.del_table.setMaximumHeight(min(max(target_h, 118), 180))


def delivery_detail_widget(self, d, comps, idx: int):
    panel = QWidget(); panel.setObjectName("detailPanel")
    lay = QVBoxLayout(panel); lay.setContentsMargins(16, 8, 16, 8); lay.setSpacing(6)
    title = QLabel(f"{d.name} Detayı"); title.setObjectName("detailTitle"); lay.addWidget(title)
    tbl = QTableWidget(len(comps), 4)
    self._configure_table(tbl, compact=True)
    tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    tbl.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
    tbl.setHorizontalHeaderLabels(["Bileşen", "Teslim Edilecek", "Teslim Edilen", "Kalan"])
    for r, comp in enumerate(comps):
        p = d.planned.get(comp, 0); dv = d.delivered.get(comp, 0)
        for c, v in enumerate([comp, p, dv, p-dv]):
            it = QTableWidgetItem(self._fmt_num(v) if c else str(v))
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            tbl.setItem(r, c, it)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.setMinimumHeight(140)
    tbl.setMaximumHeight(260)
    lay.addWidget(tbl, 1)

    footer = QFrame(); footer.setObjectName("detailFooter")
    frow = QHBoxLayout(footer); frow.setContentsMargins(0, 8, 0, 0); frow.setSpacing(8)
    frow.addStretch()
    edit = QPushButton("✎ Kabulü Düzenle" if _use_acceptance_terms(self) else "✎ Teslimatı Düzenle")
    edit.clicked.connect(lambda _=False, i=idx: self.edit_delivery(i))
    frow.addWidget(edit)
    lay.addWidget(footer, 0)
    return panel


def edit_delivery(self, idx: int):
    sys_info = self.current_system()
    if not sys_info:
        return
    deliveries = self.deliveries.get(sys_info.name, [])
    if idx < 0 or idx >= len(deliveries):
        return
    current = deliveries[idx]

    comp_keys = self._component_display_keys(sys_info)
    other_deliveries = [d for i, d in enumerate(deliveries) if i != idx]
    planned_assigned = {comp: sum(self._as_number(d.planned.get(comp, 0)) for d in other_deliveries) for comp in comp_keys}
    # Pass existing_delivery so DeliveryDialog can restore unit tracking data
    dlg = self._DeliveryDialog(
        sys_info,
        default_name=current.name,
        parent=self,
        component_keys=comp_keys,
        planned_assigned=planned_assigned,
        contract_t0_date=str(getattr(self.ci, "t0_date", "") or ""),
        events_provider=getattr(self, "date_picker_events", None),
        allow_delete=True,
        existing_delivery=current,
    )
    dlg.name.setText(current.name)
    dlg.status.setCurrentText(current.status or "PLAN")
    dlg.planned_acceptance_date.setText(getattr(current, "planned_acceptance_date", "") or "")
    dlg.acceptance_date.setText(current.acceptance_date or "")
    if hasattr(dlg, "_sync_actual_date_visibility"):
        dlg._sync_actual_date_visibility()
    dlg.note.setText(current.note or "")
    delivery_user = str(getattr(current, "delivery_user", "") or "").strip()
    if delivery_user:
        idx_user = dlg.delivery_user_combo.findText(delivery_user, Qt.MatchExactly)
        if idx_user < 0:
            dlg.delivery_user_combo.addItem(delivery_user)
            idx_user = dlg.delivery_user_combo.findText(delivery_user, Qt.MatchExactly)
        dlg.delivery_user_combo.setCurrentIndex(max(0, idx_user))

    # Restore planned/delivered values; _comp_row maps visible rows in the fixed 4-column table.
    dlg._updating_qty = True
    for comp in dlg.component_keys:
        data_row = dlg._comp_row.get(comp)
        if data_row is None:
            continue
        p_item = dlg.qty_table.item(data_row, 1)
        d_item = dlg.qty_table.item(data_row, 2)
        if p_item:
            p_item.setText(self._fmt_num(current.planned.get(comp, 0)))
        if d_item:
            d_item.setText(self._fmt_num(current.delivered.get(comp, 0)))
        dlg._update_remaining_row(data_row)
    dlg._updating_qty = False
    dlg.refresh_assignment_card()

    overlay = QWidget(self)
    overlay.setObjectName("dimOverlay")
    overlay.setStyleSheet("background: rgba(0,0,0,140);")
    overlay.setGeometry(self.rect())
    overlay.show()
    overlay.raise_()
    dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    dlg.setWindowModality(Qt.WindowModal)

    def _center_dlg():
        pw = self.geometry()
        dlg.move(pw.x() + (pw.width() - dlg.width()) // 2, pw.y() + (pw.height() - dlg.height()) // 2)

    QTimer.singleShot(0, _center_dlg)
    _orig_move = self.moveEvent

    def _move_hook(ev):
        _orig_move(ev)
        _center_dlg()

    self.moveEvent = _move_hook
    try:
        result = dlg.exec()
    finally:
        self.moveEvent = _orig_move
        overlay.hide()
        overlay.deleteLater()
    if result and dlg.delete_requested:
        del self.deliveries[sys_info.name][idx]
        self._deleted_delivery_systems.add(sys_info.name)
        self._set_dirty()
        self.expanded_delivery_index = None
        self.refresh_live_statuses()
        self.refresh_right()
    elif result and dlg.result:
        self.deliveries[sys_info.name][idx] = dlg.result
        self._set_dirty()
        self.expanded_delivery_index = None
        self.refresh_live_statuses()
        self.refresh_right()


def add_delivery(self):
    sys_info = self.current_system()
    if not sys_info:
        self._show_warning("Sistem yok", "Önce sistem ekleyin.")
        return
    self.sync_summary_to_system()
    if not any(v > 0 for v in sys_info.components.values()):
        self._show_warning("Adet yok", "Önce Bileşen Özeti tablosunda sözleşme adetlerini girin.")
        return
    comp_keys = self._component_display_keys(sys_info)
    existing_deliveries = self.deliveries.get(sys_info.name, [])
    planned_assigned = {comp: sum(self._as_number(d.planned.get(comp, 0)) for d in existing_deliveries) for comp in comp_keys}
    dlg = self._DeliveryDialog(
        sys_info,
        f"{'Kabul' if _use_acceptance_terms(self) else 'Teslimat'} {len(existing_deliveries) + 1}",
        self,
        component_keys=comp_keys,
        planned_assigned=planned_assigned,
        contract_t0_date=str(getattr(self.ci, "t0_date", "") or ""),
        events_provider=getattr(self, "date_picker_events", None),
    )
    overlay = QWidget(self)
    overlay.setObjectName("dimOverlay")
    overlay.setStyleSheet("background: rgba(0,0,0,140);")
    overlay.setGeometry(self.rect())
    overlay.show()
    overlay.raise_()
    dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    dlg.setWindowModality(Qt.WindowModal)

    def _center_add():
        pw = self.geometry()
        dlg.move(pw.x() + (pw.width() - dlg.width()) // 2, pw.y() + (pw.height() - dlg.height()) // 2)

    QTimer.singleShot(0, _center_add)
    _orig_move2 = self.moveEvent

    def _move_hook2(ev):
        _orig_move2(ev)
        _center_add()

    self.moveEvent = _move_hook2
    try:
        result = dlg.exec()
    finally:
        self.moveEvent = _orig_move2
        overlay.hide()
        overlay.deleteLater()
    if result and dlg.result:
        self.deliveries.setdefault(sys_info.name, []).append(dlg.result)
        self._deleted_delivery_systems.discard(sys_info.name)
        self._set_dirty()
        self.expanded_delivery_index = None
        self.refresh_live_statuses()
        self.refresh_right()
