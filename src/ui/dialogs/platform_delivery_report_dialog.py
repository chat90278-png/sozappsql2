from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
    QStackedWidget, QScrollArea, QHeaderView, QLineEdit)

from src.services.platform_delivery_report import STATUSES, export_report_to_excel, load_report_data, save_report_data

class PlatformTeslimatDurumuReportDialog(QDialog):
    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store
        self.data = None
        self.detail_tables = OrderedDict()
        self.summary_table = None
        self._dirty = False
        self._refreshing = False
        self.setWindowTitle("Platform Teslimat Durumu")
        self.resize(1500, 820)
        self._build_ui(); self._load_filters(); self.refresh_preview()

    def _build_ui(self):
        root = QHBoxLayout(self); root.setContentsMargins(16,16,16,16); root.setSpacing(16)
        left = QFrame(); left.setObjectName("filterPanel"); left.setFixedWidth(300); ll=QVBoxLayout(left); ll.setContentsMargins(16,16,16,16); ll.setSpacing(10)
        title=QLabel("Rapor Ayarları"); title.setObjectName("panelTitle"); ll.addWidget(title)
        self.platform_cb = self._combo(ll,"PLATFORM"); self.scope_cb = self._combo(ll,"KAPSAM", ["Tüm Kullanıcılar"])
        self.user_cb = self._combo(ll,"KULLANICI / ÜLKE", ["Tümü"]); self.contract_cb = self._combo(ll,"SÖZLEŞME", ["Tüm Sözleşmeler"])
        ll.addSpacing(10); self.stats=QLabel("Toplam Sayfa\n-"); self.stats.setObjectName("statBox"); ll.addWidget(self.stats); ll.addStretch(); root.addWidget(left)
        right=QFrame(); right.setObjectName("reportCard"); rl=QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)
        top=QHBoxLayout(); top.setContentsMargins(18,12,18,12); self.title_label=QLabel("Platform Teslimat Durumu"); self.title_label.setObjectName("mainTitle"); top.addWidget(self.title_label)
        self.badge=QLabel("Sayfa 1 / 1"); self.badge.setObjectName("badge"); top.addWidget(self.badge); top.addStretch()
        b=QPushButton("Önizlemeyi Yenile"); b.setObjectName("reportSecondaryButton"); b.clicked.connect(self.refresh_preview); top.addWidget(b)
        e=QPushButton("Excel Oluştur"); e.setObjectName("reportSecondaryButton"); e.clicked.connect(self.export_excel); top.addWidget(e)
        s=QPushButton("Raporu Kaydet"); s.setObjectName("reportPrimaryButton"); s.clicked.connect(self.save_report); top.addWidget(s); rl.addLayout(top)
        self.stack=QStackedWidget(); rl.addWidget(self.stack,1)
        self.tabs=QHBoxLayout(); self.tabs.setContentsMargins(16,8,16,8); self.tabs.setSpacing(4); rl.addLayout(self.tabs); root.addWidget(right,1)
        self.setStyleSheet(STYLE)

    def _combo(self, lay, label, items=None):
        l=QLabel(label); l.setObjectName("filterLabel"); lay.addWidget(l); cb=QComboBox(); cb.addItems(items or []); lay.addWidget(cb); cb.currentIndexChanged.connect(self.refresh_preview); return cb

    def _load_filters(self):
        if not self.store: return
        self.platform_cb.blockSignals(True); self.platform_cb.clear(); self.platform_cb.addItems(self.store.platform_names()); self.platform_cb.blockSignals(False)
        self._reload_dependent_filters()

    def _reload_dependent_filters(self):
        if not self.store: return
        platform=self.platform_cb.currentText(); data=load_report_data(self.store, platform)
        self.user_cb.blockSignals(True); self.contract_cb.blockSignals(True)
        self.user_cb.clear(); self.user_cb.addItem("Tümü", None)
        self.contract_cb.clear(); self.contract_cb.addItem("Tüm Sözleşmeler", None)
        seen_u=set(); seen_c=set()
        for r in data.summary:
            if r.user_id not in seen_u: seen_u.add(r.user_id); self.user_cb.addItem(r.user, r.user_id)
            if r.contract_id not in seen_c: seen_c.add(r.contract_id); self.contract_cb.addItem(r.contract, r.contract_id)
        self.user_cb.blockSignals(False); self.contract_cb.blockSignals(False)

    def refresh_preview(self):
        if not self.store or self.platform_cb.count()==0: return
        if self._dirty:
            result = QMessageBox.question(self, "Kaydedilmemiş değişiklikler", "Önizleme yenilenirse kaydedilmemiş değişiklikler kaybolur. Devam edilsin mi?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result != QMessageBox.Yes:
                return
        self._refreshing = True
        platform=self.platform_cb.currentText(); uid=self.user_cb.currentData(); cid=self.contract_cb.currentData()
        self.data=load_report_data(self.store, platform, uid, cid)
        self._clear_stack(); self.detail_tables.clear(); self._clear_tabs()
        self.title_label.setText(f"{self.data.platform} Teslimat Durumu")
        self.summary_table=self._summary_table(); self._add_page(self.summary_table, f"{self.data.platform} Teslimat Durumu")
        for key, lines in self.data.details.items():
            if lines: self.detail_tables[key]=self._detail_table(lines); self._add_page(self.detail_tables[key], f"{lines[0].user} Teslimat Durumu")
        self.stats.setText(f"TOPLAM SAYFA\n{self.stack.count()}\n\nKULLANICI\n{len(self.data.details)}\n\nSÖZLEŞME\n{len({r.contract_id for r in self.data.summary})}")
        self._set_page(0)
        self._dirty = False
        self._refreshing = False

    def _summary_table(self):
        t=QTableWidget(len(self.data.summary),5); t.setHorizontalHeaderLabels(["Kullanıcı","Sözleşme Adı veya Numarası","Teslimat Tarihi","Durum","Açıklama"]); t.verticalHeader().hide(); t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i,r in enumerate(self.data.summary):
            item=QTableWidgetItem(f"{r.user} ↗"); item.setData(Qt.UserRole,(r.user_id,r.contract_id)); item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable); t.setItem(i,0,item)
            for c,v in [(1,r.contract),(2,r.delivery_date)]: it=QTableWidgetItem(v); it.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable); t.setItem(i,c,it)
            cb=QComboBox(); cb.addItems(STATUSES); cb.setCurrentText(r.status if r.status in STATUSES else r.status); cb.currentTextChanged.connect(self._mark_dirty); t.setCellWidget(i,3,cb)
            txt=QTextEdit(r.description); txt.setFixedHeight(52); txt.textChanged.connect(self._mark_dirty); t.setCellWidget(i,4,txt); t.setRowHeight(i,64)
        t.cellClicked.connect(lambda row,col: self._set_page(row+1) if col==0 and row+1<self.stack.count() else None); return t

    def _detail_table(self, lines):
        t=QTableWidget(len(lines),6); t.setHorizontalHeaderLabels(["Ana Sistem","Miktar","Kuyruk No / Seri No","Lokasyon","Not","Teslim Edilecek Lokasyon"]); t.verticalHeader().hide(); t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        colors=["#f2df92","#26a9cf","#d8d8d8","#f6c7d8","#f4a261","#b7e4b2"]; comp_colors={}
        for i,line in enumerate(lines):
            comp_colors.setdefault(line.component, colors[len(comp_colors)%len(colors)]); bg=comp_colors[line.component]
            for c,v in [(0,line.component),(1,str(int(line.quantity) if line.quantity.is_integer() else line.quantity)),(2,line.serial_no)]:
                it=QTableWidgetItem(v); it.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable); it.setBackground(QColor(bg)); t.setItem(i,c,it)
            cb=QComboBox(); cb.addItems([""]+self.data.locations); cb.setCurrentText(line.internal_location); cb.currentTextChanged.connect(self._mark_dirty); t.setCellWidget(i,3,cb)
            for c,v in [(4,line.note),(5,line.delivery_location)]: le=QLineEdit(v); le.textChanged.connect(self._mark_dirty); t.setCellWidget(i,c,le)
            t.setRowHeight(i,42)
        t.setProperty("lines", lines); return t

    def _add_page(self, widget, name):
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget); self.stack.addWidget(scroll)
        btn=QPushButton(name); btn.setCheckable(True); btn.clicked.connect(lambda _=False, idx=self.stack.count()-1: self._set_page(idx)); self.tabs.addWidget(btn)

    def _clear_stack(self):
        while self.stack.count():
            w=self.stack.widget(0); self.stack.removeWidget(w); w.deleteLater()

    def _clear_tabs(self):
        while self.tabs.count():
            item=self.tabs.takeAt(0); w=item.widget(); w.deleteLater() if w else None

    def _set_page(self, idx):
        self.stack.setCurrentIndex(idx); total=self.stack.count(); self.badge.setText(f"Sayfa {idx+1} / {total} · {'Genel Sayfa' if idx==0 else 'Detay Sayfa'}")
        for i in range(self.tabs.count()): self.tabs.itemAt(i).widget().setChecked(i==idx)

    def _collect(self):
        summary=[]; lines=[]
        for i,r in enumerate(self.data.summary): summary.append({"user_id":r.user_id,"contract_id":r.contract_id,"status":self.summary_table.cellWidget(i,3).currentText(),"description":self.summary_table.cellWidget(i,4).toPlainText()})
        for key,t in self.detail_tables.items():
            for i,line in enumerate(t.property("lines")):
                lines.append({"user_id":line.user_id,"contract_id":line.contract_id,"component_id":line.component_id,"serial_no":line.serial_no,"serial_key":line.serial_key,"internal_location":t.cellWidget(i,3).currentText(),"note":t.cellWidget(i,4).text(),"delivery_location":t.cellWidget(i,5).text()})
        return summary, lines

    def _mark_dirty(self, *args):
        if not self._refreshing:
            self._dirty = True

    def _save_current(self, show_message: bool = True):
        s,l=self._collect(); save_report_data(self.store,self.data,s,l); self._dirty = False
        if show_message: QMessageBox.information(self,"Platform Teslimat Durumu","Rapor kaydedildi.")
        self.refresh_preview()

    def save_report(self):
        self._save_current(show_message=True)

    def export_excel(self):
        if self._dirty:
            self._save_current(show_message=False)
        path,_=QFileDialog.getSaveFileName(self,"Platform Teslimat Durumu Excel Kaydet",f"{self.data.platform}_teslimat_durumu.xlsx","Excel (*.xlsx)")
        if path: export_report_to_excel(load_report_data(self.store,self.data.platform,self.user_cb.currentData(),self.contract_cb.currentData()), Path(path)); QMessageBox.information(self,"Excel",f"Excel oluşturuldu:\n{path}")

    def closeEvent(self, event):
        if self._dirty:
            result = QMessageBox.question(self, "Kaydedilmemiş değişiklikler", "Platform Teslimat Durumu raporunda kaydedilmemiş değişiklikler var. Kaydetmeden çıkmak istiyor musunuz?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result != QMessageBox.Yes:
                event.ignore(); return
        super().closeEvent(event)

STYLE='''
QDialog{background:#eaf2fb;color:#002b68;font-weight:600} QFrame#filterPanel,QFrame#reportCard{background:#fbfdff;border:1px solid #c7dcf4;border-radius:16px} QLabel#panelTitle,QLabel#mainTitle{font-size:16px;font-weight:800;color:#002b68} QLabel#filterLabel{font-size:11px;color:#3b5f96} QLabel#badge{background:#dff3e8;color:#087a2f;border-radius:11px;padding:5px 10px} QLabel#statBox{border:1px solid #c7dcf4;border-radius:12px;padding:12px;background:#fff} QComboBox,QLineEdit{border:1px solid #bed5ef;border-radius:8px;padding:7px;background:white} QPushButton{border:1px solid #bdd5f2;border-radius:9px;padding:8px 14px;background:#f7fbff;color:#002b68;font-weight:800} QPushButton#reportPrimaryButton{background:#075bcc;color:white;border-color:#075bcc} QPushButton:checked{background:#e9fff0;color:#18803b;border-color:#57c784} QHeaderView::section{background:#123e7c;color:white;font-weight:800;padding:8px;border:1px solid #18305d} QTableWidget{gridline-color:#111;background:#dceaf8;border:1px solid #123e7c} QTextEdit{border:1px solid #bed5ef;border-radius:8px;background:white}
'''
