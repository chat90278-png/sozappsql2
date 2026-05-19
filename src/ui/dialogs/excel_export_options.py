from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QRadioButton, QButtonGroup, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QCheckBox
from src.ui.theme import STYLE


class ExcelExportDialog(QDialog):
    def __init__(self, store, parent=None, active_platform: str = ""):
        super().__init__(parent)
        self.store = store
        self.active_platform = str(active_platform or "").strip()
        self.result_options = None
        self.setWindowTitle("Excel’e Aktar")
        self.resize(760, 620)
        self.setStyleSheet(STYLE)
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Excel’e Aktar"); title.setObjectName("mainTitle"); root.addWidget(title)
        root.addWidget(QLabel("STS verilerinden Excel raporu oluşturun. Tüm veri yerine belirli platformları seçerek daha hızlı çıktı alabilirsiniz."))

        self.rb_all = QRadioButton("Tüm platformlar")
        self.rb_selected = QRadioButton("Seçili platformlar")
        self.rb_active = QRadioButton("Aktif platform")
        self.rb_summary = QRadioButton("Sadece özet")
        g = QButtonGroup(self); [g.addButton(b) for b in [self.rb_all, self.rb_selected, self.rb_active, self.rb_summary]]
        for b in [self.rb_all, self.rb_selected, self.rb_active, self.rb_summary]:
            b.toggled.connect(self._update_state); root.addWidget(b)

        self.platform_list = QListWidget()
        for p in (self.store.platform_names() if hasattr(self.store, 'platform_names') else []):
            it = QListWidgetItem(str(p)); it.setFlags(it.flags() | Qt.ItemIsUserCheckable); it.setCheckState(Qt.Unchecked); self.platform_list.addItem(it)
        root.addWidget(self.platform_list)
        btns = QHBoxLayout()
        bsel = QPushButton("Tümünü Seç"); bsel.clicked.connect(lambda: self._check_all(True))
        bclr = QPushButton("Temizle"); bclr.clicked.connect(lambda: self._check_all(False))
        btns.addWidget(bsel); btns.addWidget(bclr); root.addLayout(btns)

        self.cb_summary = QCheckBox("Özet sheet ekle"); self.cb_summary.setChecked(True)
        self.cb_contract = QCheckBox("Sözleşme toplam satırları"); self.cb_contract.setChecked(True)
        self.cb_system = QCheckBox("Sistem toplam satırları"); self.cb_system.setChecked(True)
        self.cb_delivery = QCheckBox("Kabul/Teslimat satırları"); self.cb_delivery.setChecked(True)
        self.cb_comp = QCheckBox("Bileşen kolonları"); self.cb_comp.setChecked(True)
        self.cb_tags = QCheckBox("Etiketleri dahil et"); self.cb_tags.setChecked(True)
        for c in [self.cb_summary,self.cb_contract,self.cb_system,self.cb_delivery,self.cb_comp,self.cb_tags]: root.addWidget(c)
        root.addWidget(QLabel("Büyük veri setlerinde tüm platformları ve kabul satırlarını dışa aktarmak birkaç dakika sürebilir."))

        row = QHBoxLayout(); ok = QPushButton("Excel Oluştur"); ok.clicked.connect(self.accept_options); can = QPushButton("İptal"); can.clicked.connect(self.reject)
        row.addWidget(ok); row.addWidget(can); root.addLayout(row)

        if self.active_platform:
            self.rb_active.setChecked(True)
        else:
            self.rb_all.setChecked(True)
        self._update_state()

    def _check_all(self, val: bool):
        for i in range(self.platform_list.count()):
            self.platform_list.item(i).setCheckState(Qt.Checked if val else Qt.Unchecked)

    def _update_state(self):
        self.platform_list.setEnabled(self.rb_selected.isChecked())

    def accept_options(self):
        scope = 'all'
        if self.rb_selected.isChecked(): scope = 'selected'
        elif self.rb_active.isChecked(): scope = 'active'
        elif self.rb_summary.isChecked(): scope = 'summary_only'
        plats = [self.platform_list.item(i).text() for i in range(self.platform_list.count()) if self.platform_list.item(i).checkState() == Qt.Checked]
        if scope == 'active' and self.active_platform:
            plats = [self.active_platform]
        self.result_options = {
            'scope': scope,
            'platforms': plats,
            'include_summary': self.cb_summary.isChecked() or scope == 'summary_only',
            'include_contract_rows': self.cb_contract.isChecked(),
            'include_system_rows': self.cb_system.isChecked(),
            'include_delivery_rows': self.cb_delivery.isChecked(),
            'include_component_columns': self.cb_comp.isChecked(),
            'include_tags': self.cb_tags.isChecked(),
        }
        self.accept()
