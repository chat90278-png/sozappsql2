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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import STYLE


class PlatformRow(QFrame):
    def __init__(self, platform_name: str, contract_count: int, on_changed):
        super().__init__()
        self.platform_name = platform_name
        self._on_changed = on_changed
        self.setObjectName("platformRow")
        self.setStyleSheet("""
QFrame#platformRow { border:1px solid #e2e8f0; border-radius:10px; background:#ffffff; }
QFrame#platformRow:hover { border:1px solid #93c5fd; background:#f7fbff; }
QFrame#platformRow[checked='true'] { border:1px solid #3b82f6; background:#f0f6ff; }
QFrame#platformRow[disabled='true'] { border:1px solid #dbe5f1; background:#f8fafc; }
QLabel#platformName { color:#0f172a; font-weight:800; }
QLabel#platformBadge { color:#35506d; background:#eaf1ff; border-radius:9px; padding:3px 8px; font-weight:700; }
""")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(self._emit_changed)
        name = QLabel(platform_name)
        name.setObjectName("platformName")
        badge = QLabel(f"{contract_count} sözleşme")
        badge.setObjectName("platformBadge")
        lay.addWidget(self.checkbox)
        lay.addWidget(name, 1)
        lay.addWidget(badge)
        self.set_interactive(True)

    def _emit_changed(self):
        self.setProperty("checked", self.checkbox.isChecked())
        self.style().unpolish(self); self.style().polish(self)
        self._on_changed()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.checkbox.isEnabled():
            if self.childAt(event.position().toPoint()) is not self.checkbox:
                self.checkbox.toggle()
                event.accept()
                return
        super().mousePressEvent(event)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool, silent: bool = False):
        if silent:
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(checked)
            self.checkbox.blockSignals(False)
            self.setProperty("checked", self.checkbox.isChecked())
            self.style().unpolish(self); self.style().polish(self)
        else:
            self.checkbox.setChecked(checked)

    def set_interactive(self, enabled: bool):
        self.checkbox.setEnabled(enabled)
        self.setProperty("disabled", not enabled)
        self.style().unpolish(self); self.style().polish(self)


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
        self.platform_rows = []

        self._platform_counts = Counter()
        for it in self.contract_index:
            p = str((it or {}).get("platform") or "").strip()
            if p:
                self._platform_counts[p] += 1

        self.setWindowTitle("Excel’e Aktar - STS")
        self.resize(920, 560)
        self.setMinimumSize(820, 520)
        self.setStyleSheet(STYLE + self._local_style())
        self.build()

    def _local_style(self):
        return """
QFrame#exportHero { background:#10263f; border-radius:14px; }
QLabel#exportHeroTitle { color:#ffffff; font-size:24px; font-weight:900; background:transparent; }
QLabel#exportHeroDesc { color:#c8d8ea; font-size:12px; background:transparent; }
QLabel#exportBadge { color:#f8fbff; background:rgba(255,255,255,0.14); border:1px solid rgba(255,255,255,0.28); border-radius:12px; padding:8px 12px; font-weight:950; }

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
QLabel#exportWarning { background:#fff7e6; color:#92400e; border:1px solid #f3c37b; border-radius:12px; padding:10px 12px; font-weight:800; }
QScrollArea#platformScroll { border:1px solid #dbe5f1; border-radius:10px; background:#ffffff; }
QScrollArea#platformScroll QScrollBar:vertical { width:10px; background:#f5f8fc; margin:8px 2px; border-radius:5px; }
QScrollArea#platformScroll QScrollBar::handle:vertical { background:#b4c6de; border-radius:5px; min-height:28px; }
QScrollArea#platformScroll QScrollBar::add-line:vertical, QScrollArea#platformScroll QScrollBar::sub-line:vertical { height:0; }
QDialog#excelExportDialog QLabel, QDialog#excelExportDialog QCheckBox, QDialog#excelExportDialog QRadioButton { background: transparent; }
"""

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

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

        mid = QHBoxLayout(); mid.setSpacing(10); root.addLayout(mid, 1)
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
        self.platform_container = QWidget()
        self.platform_layout = QVBoxLayout(self.platform_container)
        self.platform_layout.setContentsMargins(8, 8, 8, 8)
        self.platform_layout.setSpacing(6)
        for p in (self.store.platform_names() if hasattr(self.store, "platform_names") else []):
            c = self._platform_counts.get(str(p), 0)
            row = PlatformRow(str(p), c, self._on_platform_item_changed)
            self.platform_rows.append(row)
            self.platform_layout.addWidget(row)
        self.platform_layout.addStretch(1)
        self.platform_scroll = QScrollArea()
        self.platform_scroll.setObjectName("platformScroll")
        self.platform_scroll.setWidgetResizable(True)
        self.platform_scroll.setFrameShape(QFrame.NoFrame)
        self.platform_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.platform_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.platform_scroll.setMinimumHeight(180)
        self.platform_scroll.setMaximumHeight(260)
        self.platform_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.platform_scroll.setWidget(self.platform_container)
        pl.addWidget(self.platform_scroll, 1)
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
        return [r.platform_name for r in self.platform_rows if r.is_checked()]

    def _set_platform_checks(self, checked: bool):
        for row in self.platform_rows:
            row.set_checked(checked, silent=True)

    def _on_platform_item_changed(self):
        if self._updating_ui:
            return
        self._refresh_summary()

    def _update_state(self):
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            scope = self._scope_value()

            if scope == "all":
                self._set_platform_checks(True)
                for row in self.platform_rows:
                    row.set_interactive(False)
            elif scope == "active":
                self._set_platform_checks(False)
                for row in self.platform_rows:
                    row.set_checked(row.platform_name == self.active_platform, silent=True)
                    row.set_interactive(False)
            elif scope == "summary_only":
                self._set_platform_checks(False)
                for row in self.platform_rows:
                    row.set_interactive(False)
            else:
                for row in self.platform_rows:
                    row.set_interactive(True)

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
            self.warn.setVisible(True)
        else:
            self.warn.setText("Seçili kapsama göre export süresi kısa olacaktır.")
            self.warn.setVisible(True)

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
