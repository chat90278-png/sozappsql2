from __future__ import annotations
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from src.ui.theme import STYLE


class ExcelExportDialog(QDialog):
    def __init__(self, store, parent=None, active_platform=None, contract_index=None):
        super().__init__(parent)
        self.store = store
        self.active_platform = str(active_platform or "").strip()
        self.contract_index = list(contract_index or [])
        self.result_options = None
        self._updating_ui = False

        self._platform_counts = Counter()
        for it in self.contract_index:
            p = str((it or {}).get("platform") or "").strip()
            if p:
                self._platform_counts[p] += 1

        self.setWindowTitle("Excel’e Aktar")
        self.resize(920, 730)
        self.setMinimumSize(860, 680)
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

QFrame#exportScopeOption { background:#ffffff; border:1px solid #edf2f7; border-radius:12px; }
QFrame#exportScopeOptionActive { background:#eff6ff; border:1px solid #3b82f6; border-radius:12px; }
QLabel#exportScopeTitle { color:#163b64; font-size:14px; font-weight:900; background:transparent; }
QLabel#exportScopeBadge { color:#1d4ed8; border:1px solid #cfe1fb; border-radius:10px; padding:2px 7px; font-size:11px; font-weight:800; background:#ffffff; }

QPushButton#exportLinkButton { background:transparent; color:#2563eb; border:none; padding:0; font-size:12px; font-weight:900; }
QPushButton#exportPrimaryButton { background:#2563eb; color:white; border:none; border-radius:12px; padding:11px 16px; font-weight:900; min-width:140px; }
QPushButton#exportSecondaryButton { background:#ffffff; color:#244767; border:1px solid #d6e2f0; border-radius:12px; padding:11px 16px; font-weight:800; min-width:120px; }

QLabel#exportSummaryRow { background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:8px 10px; }
QLabel#exportWarning { background:#fff7df; color:#7c4a03; border:1px solid #f7d48a; border-radius:12px; padding:10px 12px; font-weight:700; }
"""

    def build(self):
        root = QVBoxLayout(self)

        hero = QFrame(); hero.setObjectName("exportHero")
        hl = QHBoxLayout(hero); hl.setContentsMargins(18, 16, 18, 16)
        txt = QVBoxLayout()
        t = QLabel("Excel’e Aktar"); t.setObjectName("exportHeroTitle")
        d = QLabel("STS verilerinden Excel raporu oluşturun. Tüm veri yerine belirli platformları seçerek daha hızlı ve daha sade çıktı alabilirsiniz.")
        d.setObjectName("exportHeroDesc"); d.setWordWrap(True)
        txt.addWidget(t); txt.addWidget(d)
        hl.addLayout(txt, 1)
        hl.addWidget(QLabel("STS → XLSX", objectName="exportBadge"), 0, Qt.AlignTop)
        root.addWidget(hero)

        mid = QHBoxLayout(); root.addLayout(mid, 1)
        left_col = QVBoxLayout(); mid.addLayout(left_col, 1)
        right_col = QVBoxLayout(); mid.addLayout(right_col, 1)

        scope_card = QFrame(); scope_card.setObjectName("exportCard")
        scl = QVBoxLayout(scope_card)
        scl.addWidget(QLabel("Aktarım Kapsamı", objectName="exportCardHeader"))
        self.rb_active = self._scope_row("Aktif platform", "Yalnızca şu anda seçili platformu aktarır.", "En hızlı")
        self.rb_selected = self._scope_row("Seçili platformlar", "Bir veya daha fazla platform seçerek özel Excel çıktısı oluşturur.")
        self.rb_all = self._scope_row("Tüm platformlar", "Tüm platformları tek Excel dosyasına aktarır.", "Kapsamlı")
        self.rb_summary = self._scope_row("Sadece özet", "Platform sheetleri olmadan yalnızca özet rapor oluşturur.")
        self.scope_rows = [self.rb_active, self.rb_selected, self.rb_all, self.rb_summary]
        for w in self.scope_rows:
            scl.addWidget(w)
        g = QButtonGroup(self)
        for row in self.scope_rows:
            rb = row.findChild(QRadioButton)
            g.addButton(rb)
            rb.toggled.connect(self._update_state)
        left_col.addWidget(scope_card)

        content_card = QFrame(); content_card.setObjectName("exportCard")
        cl = QVBoxLayout(content_card)
        cl.addWidget(QLabel("Excel İçeriği", objectName="exportCardHeader"))
        grid = QGridLayout()
        self.cb_summary = self._opt_box("Özet sheet ekle", "Dosya geneli ve platform bazlı sayıları ekler.", True)
        self.cb_tags = self._opt_box("Etiketleri dahil et", "Sözleşme etiketlerini Excel’e ekler.", True)
        self.cb_contract = self._opt_box("Sözleşme toplamı", "Her sözleşme için genel toplam satırı oluşturur.", True)
        self.cb_system = self._opt_box("Sistem toplamı", "Sistem bazlı toplam satırları ekler.", True)
        self.cb_delivery = self._opt_box("Kabul/Teslimat", "Kabul bazlı planlanan/teslim edilen satırları ekler.", True)
        self.cb_comp = self._opt_box("Bileşen kolonları", "Adet, teslim edilen ve kalan kolonlarını ekler.", True)
        opts = [self.cb_summary, self.cb_tags, self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp]
        for i, w in enumerate(opts):
            grid.addWidget(w, i // 2, i % 2)
        cl.addLayout(grid)
        left_col.addWidget(content_card)

        platform_card = QFrame(); platform_card.setObjectName("exportCard")
        pl = QVBoxLayout(platform_card)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("Platformlar", objectName="exportCardHeader")); ph.addStretch(1)
        sel = QPushButton("Tümünü seç"); sel.setObjectName("exportLinkButton"); sel.clicked.connect(lambda: self._check_all(True))
        clr = QPushButton("Seçimi temizle"); clr.setObjectName("exportLinkButton"); clr.clicked.connect(lambda: self._check_all(False))
        ph.addWidget(sel); ph.addWidget(clr)
        pl.addLayout(ph)
        self.platform_list = QListWidget()

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
        right_col.addWidget(platform_card, 1)

        summary_card = QFrame(); summary_card.setObjectName("exportCard")
        sl = QVBoxLayout(summary_card)
        sl.addWidget(QLabel("Seçim Özeti", objectName="exportCardHeader"))
        self.summary_label = QLabel(""); self.summary_label.setWordWrap(True); self.summary_label.setObjectName("exportSummaryRow"); self.summary_label.setTextFormat(Qt.RichText)
        sl.addWidget(self.summary_label)
        right_col.addWidget(summary_card)

        self.warn = QLabel(""); self.warn.setObjectName("exportWarning"); self.warn.setWordWrap(True)
        right_col.addWidget(self.warn)

        foot = QHBoxLayout(); root.addLayout(foot)
        foot.addStretch(1)
        cbtn = QPushButton("İptal"); cbtn.setObjectName("exportSecondaryButton"); cbtn.clicked.connect(self.reject)
        obtn = QPushButton("Excel Oluştur"); obtn.setObjectName("exportPrimaryButton"); obtn.clicked.connect(self.accept_options)
        foot.addWidget(cbtn); foot.addWidget(obtn)

        for box in [self.cb_summary, self.cb_tags, self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp]:
            box.findChild(QCheckBox).toggled.connect(self._update_state)

        if self.active_platform:
            self.rb_active.findChild(QRadioButton).setChecked(True)
        else:
            self.rb_all.findChild(QRadioButton).setChecked(True)
        self._update_state()

    def _scope_row(self, title, desc, badge=None):
        w = QFrame(); w.setObjectName("exportScopeOption")
        l = QVBoxLayout(w); l.setContentsMargins(10, 8, 10, 8)
        top = QHBoxLayout()
        rb = QRadioButton(title); rb.setObjectName("exportScopeTitle")
        top.addWidget(rb)
        top.addStretch(1)
        if badge:
            top.addWidget(QLabel(badge, objectName="exportScopeBadge"))
        md = QLabel(desc); md.setObjectName("exportMuted"); md.setWordWrap(True)
        l.addLayout(top); l.addWidget(md)
        return w

    def _opt_box(self, title, desc, checked):
        w = QFrame(); w.setObjectName("exportScopeOption")
        l = QVBoxLayout(w); l.setContentsMargins(8, 6, 8, 6)
        cb = QCheckBox(title); cb.setChecked(checked); cb.setStyleSheet("font-weight:800; background:transparent;")
        md = QLabel(desc); md.setObjectName("exportMuted"); md.setWordWrap(True)
        l.addWidget(cb); l.addWidget(md)
        return w

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

    def _check_all(self, checked: bool):
        if self._updating_ui:
            return
        self._set_platform_checks(checked)
        self._refresh_summary()

    def _on_platform_item_changed(self, _item):
        if self._updating_ui:
            return
        self._refresh_summary()

    def _update_state(self):
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            rb_active = self.rb_active.findChild(QRadioButton).isChecked()
            rb_selected = self.rb_selected.findChild(QRadioButton).isChecked()
            rb_all = self.rb_all.findChild(QRadioButton).isChecked()
            rb_summary = self.rb_summary.findChild(QRadioButton).isChecked()

            for row in self.scope_rows:
                row.setObjectName("exportScopeOptionActive" if row.findChild(QRadioButton).isChecked() else "exportScopeOption")
                row.style().unpolish(row); row.style().polish(row)

            self.platform_list.blockSignals(True)
            try:
                if rb_all:
                    self._set_platform_checks(True)
                    self.platform_list.setEnabled(False)
                elif rb_active:
                    self._set_platform_checks(False)
                    for i in range(self.platform_list.count()):
                        it = self.platform_list.item(i)
                        if str(it.data(Qt.UserRole) or "") == self.active_platform:
                            it.setCheckState(Qt.Checked)
                    self.platform_list.setEnabled(False)
                elif rb_summary:
                    self.platform_list.setEnabled(False)
                else:
                    self.platform_list.setEnabled(True)
            finally:
                self.platform_list.blockSignals(False)

            summary_only = rb_summary
            csum = self.cb_summary.findChild(QCheckBox)
            if summary_only:
                csum.setChecked(True)
            csum.setEnabled(not summary_only)
            for box in [self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp, self.cb_tags]:
                box.findChild(QCheckBox).setEnabled(not summary_only)
        finally:
            self._updating_ui = False

        self._refresh_summary()

    def _refresh_summary(self):
        rb_active = self.rb_active.findChild(QRadioButton).isChecked()
        rb_selected = self.rb_selected.findChild(QRadioButton).isChecked()
        rb_all = self.rb_all.findChild(QRadioButton).isChecked()
        rb_summary = self.rb_summary.findChild(QRadioButton).isChecked()

        scope_name = "Aktif platform" if rb_active else "Seçili platformlar" if rb_selected else "Tüm platformlar" if rb_all else "Sadece özet"
        if rb_selected or rb_active:
            plats = self._selected_platforms()
        elif rb_all:
            plats = list(self.store.platform_names() if hasattr(self.store, "platform_names") else [])
        else:
            plats = []

        est = "-"
        if self._platform_counts:
            est_val = sum(self._platform_counts.get(p, 0) for p in plats) if plats else (sum(self._platform_counts.values()) if rb_all else 0)
            est = str(est_val)

        rows = []
        if self.cb_contract.findChild(QCheckBox).isChecked(): rows.append("Sözleşme")
        if self.cb_system.findChild(QCheckBox).isChecked(): rows.append("Sistem")
        if self.cb_delivery.findChild(QCheckBox).isChecked(): rows.append("Kabul")
        rows_txt = " + ".join(rows) if rows else "-"

        self.summary_label.setText(
            ""
            f"<div style='line-height:1.55'>"
            f"<div><span style='color:#64748b'>Kapsam</span> <b style='float:right'>{scope_name}</b></div>"
            f"<div><span style='color:#64748b'>Platform sayısı</span> <b style='float:right'>{len(plats) if not rb_summary else 0}</b></div>"
            f"<div><span style='color:#64748b'>Tahmini sözleşme</span> <b style='float:right'>{est}</b></div>"
            f"<div><span style='color:#64748b'>Satır kapsamı</span> <b style='float:right'>{rows_txt}</b></div>"
            f"<div><span style='color:#64748b'>Bileşen kolonları</span> <b style='float:right'>{'Açık' if self.cb_comp.findChild(QCheckBox).isChecked() else 'Kapalı'}</b></div>"
            f"</div>"
        )

        if rb_all and self.cb_delivery.findChild(QCheckBox).isChecked() and self.cb_comp.findChild(QCheckBox).isChecked():
            self.warn.setText("Bu seçim en kapsamlı ve en yavaş çıktıdır.")
        else:
            self.warn.setText("Büyük veri setlerinde tüm platformlar, kabul satırları ve bileşen kolonlarıyla export işlemi birkaç dakika sürebilir.")

    def accept_options(self):
        rb_active = self.rb_active.findChild(QRadioButton).isChecked()
        rb_selected = self.rb_selected.findChild(QRadioButton).isChecked()
        rb_all = self.rb_all.findChild(QRadioButton).isChecked()

        scope = "summary_only"
        if rb_selected:
            scope = "selected"
        elif rb_active:
            scope = "active"
        elif rb_all:
            scope = "all"

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
            "include_summary": self.cb_summary.findChild(QCheckBox).isChecked() or scope == "summary_only",
            "include_contract_rows": self.cb_contract.findChild(QCheckBox).isChecked(),
            "include_system_rows": self.cb_system.findChild(QCheckBox).isChecked(),
            "include_delivery_rows": self.cb_delivery.findChild(QCheckBox).isChecked(),
            "include_component_columns": self.cb_comp.findChild(QCheckBox).isChecked(),
            "include_tags": self.cb_tags.findChild(QCheckBox).isChecked(),
        }
        self.accept()
