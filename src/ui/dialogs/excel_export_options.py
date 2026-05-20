from __future__ import annotations
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from src.ui.theme import STYLE


class ExcelExportDialog(QDialog):
    DIALOG_ID = "excelExportDialog"
    def __init__(self, store, parent=None, active_platform=None, contract_index=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName(self.DIALOG_ID)
        self.active_platform = str(active_platform or "").strip()
        self.contract_index = list(contract_index or [])
        self.result_options = None
        self._updating_ui = False

        self._platform_counts = Counter()
        for it in self.contract_index:
            p = str((it or {}).get("platform") or "").strip()
            if p:
                self._platform_counts[p] += 1

        self.setWindowTitle("Excel’e Aktar - STS")
        self.resize(920, 560)
        self.setMinimumSize(820, 500)
        self.setStyleSheet(STYLE + self._local_style())
        self.build()

    def _local_style(self):
        return """
QFrame#exportHero { background:#10263f; border-radius:14px; }
QLabel#exportHeroTitle { color:#ffffff; font-size:24px; font-weight:900; background:transparent; }
QLabel#exportHeroDesc { color:#c8d8ea; font-size:12px; background:transparent; }
QLabel#exportBadge { color:#173b73; background:#eaf1ff; border-radius:12px; padding:8px 12px; font-weight:900; }

QFrame#exportCard { background:#ffffff; border:1px solid #dbe5f1; border-radius:14px; }
QLabel#exportCardHeader { color:#12345a; font-size:15px; font-weight:800; }
QLabel#exportMuted { color:#64748b; font-size:11px; background:transparent; }

QLabel#exportSectionTitle { color:#163b64; font-size:14px; font-weight:900; background:transparent; }
QComboBox#exportCombo { background:#ffffff; border:1px solid #d6e2f0; border-radius:10px; padding:8px; min-height:36px; }

QPushButton#exportLinkButton { background:transparent; color:#2563eb; border:none; padding:0; font-size:12px; font-weight:900; }
QPushButton#exportPrimaryButton { background:#2563eb; color:white; border:none; border-radius:12px; padding:11px 16px; font-weight:900; min-width:140px; }
QPushButton#exportSecondaryButton { background:#ffffff; color:#244767; border:1px solid #d6e2f0; border-radius:12px; padding:11px 16px; font-weight:800; min-width:120px; }

QFrame#summaryStatCard { background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:8px 10px; }
QLabel#summaryStatTitle { color:#64748b; font-size:11px; }
QLabel#summaryStatValue { color:#12345a; font-size:16px; font-weight:900; }
QLabel#exportWarning { background:#fff7df; color:#7c4a03; border:1px solid #f7d48a; border-radius:12px; padding:10px 12px; font-weight:700; }
QDialog#excelExportDialog QLabel, QDialog#excelExportDialog QCheckBox, QDialog#excelExportDialog QRadioButton { background: transparent; }
"""

    def build(self):
        root = QVBoxLayout(self)

        hero = QFrame(); hero.setObjectName("exportHero")
        hl = QHBoxLayout(hero); hl.setContentsMargins(18, 16, 18, 16)
        txt = QVBoxLayout()
        t = QLabel("Excel’e Aktar"); t.setObjectName("exportHeroTitle")
        d = QLabel("STS verilerinden sade ve kontrollü Excel çıktısı oluşturun.")
        d.setObjectName("exportHeroDesc"); d.setWordWrap(True)
        txt.addWidget(t); txt.addWidget(d)
        hl.addLayout(txt, 1)
        hl.addWidget(QLabel("STS → XLSX", objectName="exportBadge"), 0, Qt.AlignTop)
        root.addWidget(hero)

        mid = QHBoxLayout(); root.addLayout(mid, 1)
        left_col = QVBoxLayout(); mid.addLayout(left_col, 3)
        right_col = QVBoxLayout(); mid.addLayout(right_col, 2)

        settings_card = QFrame(); settings_card.setObjectName("exportCard")
        scl = QVBoxLayout(settings_card)
        h = QHBoxLayout()
        h.addWidget(QLabel("Aktarım Ayarları", objectName="exportCardHeader"))
        h.addStretch(1)
        h.addWidget(QLabel("zorunlu", objectName="exportMuted"))
        scl.addLayout(h)

        combo_row = QHBoxLayout()
        scope_wrap = QVBoxLayout()
        scope_wrap.addWidget(QLabel("Aktarım Kapsamı", objectName="exportSectionTitle"))
        self.scope_combo = QComboBox(); self.scope_combo.setObjectName("exportCombo")
        self.scope_combo.addItems(["Aktif platform", "Seçili platformlar", "Tüm platformlar", "Sadece özet"])
        self.scope_combo.currentTextChanged.connect(self._update_state)
        scope_wrap.addWidget(self.scope_combo)
        combo_row.addLayout(scope_wrap, 1)

        content_wrap = QVBoxLayout()
        content_wrap.addWidget(QLabel("Excel İçeriği", objectName="exportSectionTitle"))
        self.content_combo = QComboBox(); self.content_combo.setObjectName("exportCombo")
        self.content_combo.addItems(["Standart rapor", "Özet + sözleşme toplamı", "Sistem + kabul detaylı", "Tüm kolonlar", "Özel seçim"])
        self.content_combo.currentTextChanged.connect(self._update_state)
        content_wrap.addWidget(self.content_combo)
        combo_row.addLayout(content_wrap, 1)
        scl.addLayout(combo_row)

        self.custom_wrap = QFrame(); self.custom_wrap.setObjectName("exportCard")
        cwl = QVBoxLayout(self.custom_wrap)
        cwl.addWidget(QLabel("İçerik Seçenekleri", objectName="exportSectionTitle"))
        self.cb_summary = QCheckBox("Özet sheet"); self.cb_tags = QCheckBox("Etiketler")
        self.cb_contract = QCheckBox("Sözleşme toplamı"); self.cb_system = QCheckBox("Sistem toplamı")
        self.cb_delivery = QCheckBox("Kabul/Teslimat"); self.cb_comp = QCheckBox("Bileşen kolonları")
        for cb in [self.cb_summary, self.cb_tags, self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp]:
            cb.setChecked(True); cb.toggled.connect(self._update_state)
            cwl.addWidget(cb)
        self.custom_wrap.setVisible(False)
        scl.addWidget(self.custom_wrap)
        left_col.addWidget(settings_card)

        platform_card = QFrame(); platform_card.setObjectName("exportCard")
        pl = QVBoxLayout(platform_card)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("Platformlar", objectName="exportCardHeader")); ph.addStretch(1)
        pl.addLayout(ph)
        self.platform_list = QListWidget()
        self.platform_list.setMaximumHeight(230)

        self.platform_list.setStyleSheet("""
QListWidget { border:1px solid #dbe5f1; border-radius:10px; background:#ffffff; padding:4px; }
QListWidget::item { border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; margin:4px 2px; background:#ffffff; color:#0f172a; font-weight:800; }
QListWidget::item:selected { background:#eff6ff; border:1px solid #93c5fd; color:#0f172a; }
QListWidget::indicator { width:16px; height:16px; }
QListWidget::indicator:unchecked { border:1px solid #94a3b8; border-radius:4px; background:#ffffff; }
QListWidget::indicator:checked { border:1px solid #2563eb; border-radius:4px; background:#2563eb; }
""")
        for p in (self.store.platform_names() if hasattr(self.store, "platform_names") else []):
            c = self._platform_counts.get(str(p), 0)
            it = QListWidgetItem(f"{p}    {c} sözleşme")
            it.setData(Qt.UserRole, str(p))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.platform_list.addItem(it)
        self.platform_list.itemChanged.connect(self._on_platform_item_changed)
        pl.addWidget(self.platform_list)
        left_col.addWidget(platform_card, 1)

        summary_card = QFrame(); summary_card.setObjectName("exportCard")
        sl = QVBoxLayout(summary_card)
        sh = QHBoxLayout()
        sh.addWidget(QLabel("Seçim Özeti", objectName="exportCardHeader"))
        sh.addStretch(1)
        sh.addWidget(QLabel("canlı", objectName="exportMuted"))
        sl.addLayout(sh)
        self.summary_scope = self._summary_stat(sl, "Kapsam")
        self.summary_platform_count = self._summary_stat(sl, "Platform Sayısı")
        self.summary_contract_est = self._summary_stat(sl, "Tahmini Sözleşme")
        self.summary_rows = self._summary_stat(sl, "Satır Kapsamı")
        right_col.addWidget(summary_card)

        self.warn = QLabel(""); self.warn.setObjectName("exportWarning"); self.warn.setWordWrap(True)
        right_col.addWidget(self.warn)

        foot = QHBoxLayout(); root.addLayout(foot)
        foot.addStretch(1)
        cbtn = QPushButton("İptal"); cbtn.setObjectName("exportSecondaryButton"); cbtn.clicked.connect(self.reject)
        obtn = QPushButton("Excel Oluştur"); obtn.setObjectName("exportPrimaryButton"); obtn.clicked.connect(self.accept_options)
        foot.addWidget(cbtn); foot.addWidget(obtn)

        if self.active_platform:
            self.scope_combo.setCurrentText("Aktif platform")
        else:
            self.scope_combo.setCurrentText("Tüm platformlar")
        self._update_state()
    def _summary_stat(self, parent_layout, title):
        card = QFrame(); card.setObjectName("summaryStatCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(QLabel(title, objectName="summaryStatTitle"))
        val = QLabel("-"); val.setObjectName("summaryStatValue")
        val.setWordWrap(True); val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay.addWidget(val)
        parent_layout.addWidget(card)
        return val

    def _selected_platforms(self):
        out = []
        for i in range(self.platform_list.count()):
            it = self.platform_list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(str(it.data(Qt.UserRole) or ""))
        return out

    def _set_platform_checks(self, checked: bool):
        self.platform_list.blockSignals(True)
        try:
            for i in range(self.platform_list.count()):
                self.platform_list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self.platform_list.blockSignals(False)

    def _on_platform_item_changed(self, _item):
        if self._updating_ui:
            return
        self._refresh_summary()

    def _update_state(self):
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            scope = self._scope_value()

            self.platform_list.blockSignals(True)
            try:
                if scope == "all":
                    self._set_platform_checks(True)
                    self.platform_list.setEnabled(False)
                elif scope == "active":
                    self._set_platform_checks(False)
                    for i in range(self.platform_list.count()):
                        it = self.platform_list.item(i)
                        if str(it.data(Qt.UserRole) or "") == self.active_platform:
                            it.setCheckState(Qt.Checked)
                    self.platform_list.setEnabled(False)
                elif scope == "summary_only":
                    self._set_platform_checks(False)
                    self.platform_list.setEnabled(False)
                else:
                    self.platform_list.setEnabled(True)
            finally:
                self.platform_list.blockSignals(False)

            self.custom_wrap.setVisible(self.content_combo.currentText() == "Özel seçim")
            self._apply_content_preset()
        finally:
            self._updating_ui = False

        self._refresh_summary()

    def _refresh_summary(self):
        scope = self._scope_value()
        scope_name = self.scope_combo.currentText()
        if scope in {"selected", "active"}:
            plats = self._selected_platforms()
        elif scope == "all":
            plats = list(self.store.platform_names() if hasattr(self.store, "platform_names") else [])
        else:
            plats = []

        est = "-"
        if self._platform_counts:
            est_val = sum(self._platform_counts.get(p, 0) for p in plats) if plats else (sum(self._platform_counts.values()) if scope == "all" else 0)
            est = str(est_val)

        rows = []
        if self.cb_contract.isChecked(): rows.append("Sözleşme")
        if self.cb_system.isChecked(): rows.append("Sistem")
        if self.cb_delivery.isChecked(): rows.append("Kabul")
        rows_txt = " + ".join(rows) if rows else "-"
        self.summary_scope.setText(scope_name)
        self.summary_platform_count.setText(str(len(plats) if scope != "summary_only" else 0))
        self.summary_contract_est.setText(est)
        self.summary_rows.setText(rows_txt)

        if scope == "all" and self.cb_delivery.isChecked() and self.cb_comp.isChecked():
            self.warn.setText("Büyük veri setlerinde tüm platformlar, kabul satırları ve bileşen kolonlarıyla export işlemi birkaç dakika sürebilir.")
        else:
            self.warn.setText("")

    def _scope_value(self):
        return {
            "Aktif platform": "active",
            "Seçili platformlar": "selected",
            "Tüm platformlar": "all",
            "Sadece özet": "summary_only",
        }.get(self.scope_combo.currentText(), "all")

    def _apply_content_preset(self):
        if self.content_combo.currentText() == "Özel seçim":
            return
        presets = {
            "Standart rapor": (True, True, True, True, True, True),
            "Özet + sözleşme toplamı": (True, True, True, False, False, False),
            "Sistem + kabul detaylı": (True, True, True, True, True, False),
            "Tüm kolonlar": (True, True, True, True, True, True),
        }
        vals = presets.get(self.content_combo.currentText(), presets["Standart rapor"])
        for cb, v in zip([self.cb_summary, self.cb_tags, self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp], vals):
            cb.blockSignals(True); cb.setChecked(v); cb.blockSignals(False)

    def accept_options(self):
        scope = self._scope_value()

        plats = self._selected_platforms()
        if scope == "selected" and not plats:
            QMessageBox.warning(self, "Excel’e Aktar", "En az bir platform seçmelisiniz.")
            return
        if scope == "active" and not self.active_platform:
            QMessageBox.warning(self, "Excel’e Aktar", "Aktif platform bulunamadı. Lütfen platform seçin veya farklı kapsam kullanın.")
            return

        self.result_options = {
            "scope": scope,
            "platforms": [self.active_platform] if scope == "active" else plats,
            "include_summary": self.cb_summary.isChecked() or scope == "summary_only",
            "include_contract_rows": self.cb_contract.isChecked(),
            "include_system_rows": self.cb_system.isChecked(),
            "include_delivery_rows": self.cb_delivery.isChecked(),
            "include_component_columns": self.cb_comp.isChecked(),
            "include_tags": self.cb_tags.isChecked(),
        }
        self.accept()
