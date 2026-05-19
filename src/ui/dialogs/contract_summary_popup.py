from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView

from src.ui.theme import STYLE


def _configure_popup_table(table: QTableWidget):
    table.setAlternatingRowColors(False)
    table.setShowGrid(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.setWordWrap(False)


class ContractSummaryPopup(QDialog):
    def __init__(self, store, item: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.item = item
        self._fade_anim = None
        self._drag_pos = None
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setStyleSheet(STYLE + "QDialog{border:2px solid #185FA5;border-radius:4px;}")
        self.resize(360, 320)
        self._build_ui()
        self._load_data()

    def showEvent(self, event):
        super().showEvent(event)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(140)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def closeEvent(self, event):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and self.isVisible():
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()
            if not self.frameGeometry().contains(global_pos):
                self.close()
                return False
        return super().eventFilter(obj, event)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QFrame()
        head.setStyleSheet("QFrame{background:#042C53;}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 10, 10, 10)
        info = QVBoxLayout()
        sub = QLabel(f"{self.item.get('platform','')} · {self.item.get('no','')} · {self.item.get('type_display', self.item.get('type',''))}")
        sub.setStyleSheet("color:#85B7EB;font-size:11px;background:transparent;border:none;")
        title = QLabel("Bileşen Özeti")
        title.setStyleSheet("color:#ffffff;font-size:14px;font-weight:500;background:transparent;border:none;")
        info.addWidget(sub)
        info.addWidget(title)
        hl.addLayout(info, 1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton{border:1.5px solid rgba(255,255,255,0.55);background:rgba(255,255,255,0.0);"
            "color:rgba(255,255,255,0.9);border-radius:11px;font-size:11px;font-weight:600;"
            "padding:0px;text-align:center;}"
            "QPushButton:hover{background:rgba(255,255,255,0.18);border-color:#fff;}"
        )
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        root.addWidget(head)

        stats = QFrame()
        stats.setStyleSheet("QFrame{background:#F8FAFC;border-bottom:0.5px solid #D8E2ED;}")
        sl = QHBoxLayout(stats)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.lbl_toplam = self._stat_card("Toplam", "—")
        self.lbl_teslim = self._stat_card("Teslim Edilen", "—", "#0F6E56")
        self.lbl_kalan = self._stat_card("Kalan", "—", "#185FA5")
        sl.addWidget(self.lbl_toplam, 1)
        sl.addWidget(self.lbl_teslim, 1)
        sl.addWidget(self.lbl_kalan, 1)
        root.addWidget(stats)

        self.table = QTableWidget(0, 4)
        _configure_popup_table(self.table)
        self.table.setHorizontalHeaderLabels(["Bileşen", "Toplam", "Teslim", "Kalan"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for ci in [1, 2, 3]:
            hh.setSectionResizeMode(ci, QHeaderView.Fixed)
            self.table.setColumnWidth(ci, 72)
        root.addWidget(self.table, 1)

        self.footer = QLabel()
        self.footer.setStyleSheet("QLabel{background:#F8FAFC;border-top:0.5px solid #D8E2ED;padding:6px 14px;font-size:11px;color:#64748B;}")
        root.addWidget(self.footer)

    def _stat_card(self, label: str, value: str, color: str = "#1e293b") -> QFrame:
        f = QFrame()
        f.setStyleSheet("QFrame{background:transparent;border-right:0.5px solid #D8E2ED;}")
        vl = QVBoxLayout(f)
        vl.setContentsMargins(12, 8, 12, 8)
        vl.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size:10px;color:#64748B;background:transparent;border:none;")
        val = QLabel(value)
        val.setStyleSheet(f"font-size:18px;font-weight:500;color:{color};background:transparent;border:none;")
        vl.addWidget(lbl)
        vl.addWidget(val)
        f._val_label = val
        return f

    def _load_data(self):
        platform = self.item.get("platform", "")
        no = self.item.get("no", "")
        start_row = self.item.get("row")
        try:
            ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=start_row)
        except Exception:
            self.footer.setText("Veri yüklenemedi.")
            return
        if not ci:
            self.footer.setText("Sözleşme bulunamadı.")
            return
        planned: dict = {}
        delivered: dict = {}
        for sys in systems:
            for comp, qty in sys.components.items():
                planned[comp] = planned.get(comp, 0) + qty
            for d in deliveries.get(sys.name, []):
                for comp, qty in d.delivered.items():
                    delivered[comp] = delivered.get(comp, 0) + qty
        comps = list(planned.keys())
        self.table.setRowCount(len(comps))
        total_p = total_d = 0
        for r, comp in enumerate(comps):
            p = int(planned.get(comp, 0))
            dv = int(delivered.get(comp, 0))
            kalan = p - dv
            total_p += p
            total_d += dv
            for c, v in enumerate([comp, str(p), str(dv), str(kalan)]):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if c > 0:
                    it.setTextAlignment(Qt.AlignCenter)
                if c == 2:
                    it.setForeground(QColor("#0F6E56"))
                elif c == 3:
                    it.setForeground(QColor("#0F6E56" if kalan == 0 else "#185FA5"))
                self.table.setItem(r, c, it)
            self.table.setRowHeight(r, 28)
        self.lbl_toplam._val_label.setText(str(total_p))
        self.lbl_teslim._val_label.setText(str(total_d))
        self.lbl_kalan._val_label.setText(str(total_p - total_d))
        termin = str(ci.completion_date or "").strip()
        t0 = str(ci.t0_date or "").strip()
        self.footer.setText(f"T0: {t0}   Termin: {termin}   Durum: {ci.status}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
