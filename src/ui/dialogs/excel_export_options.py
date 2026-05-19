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
    QLineEdit,
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
        self._platform_counts = Counter()
        for it in self.contract_index:
            p = str((it or {}).get("platform") or "").strip()
            if p:
                self._platform_counts[p] += 1

        self.setWindowTitle("Excel’e Aktar")
        self.resize(820, 650)
        self.setStyleSheet(STYLE + self._local_style())
        self.build()

    def _local_style(self):
        return """
QFrame#exportHero { background:#0f2b61; border-radius:12px; }
QLabel#exportHeroTitle { color:#ffffff; font-size:22px; font-weight:900; background:transparent; }
QLabel#exportMuted { color:#dbeafe; font-size:12px; background:transparent; }
QLabel#exportBadge { color:#1e3a8a; background:#dbeafe; border-radius:10px; padding:5px 10px; font-weight:900; }
QFrame#exportCard { background:#ffffff; border:1px solid #d8e2ed; border-radius:12px; }
QLabel#exportCardTitle { color:#1e293b; font-size:14px; font-weight:900; background:transparent; }
QPushButton#exportPrimaryButton { background:#1f5be3; color:white; border:none; border-radius:8px; padding:10px 16px; font-weight:900; }
QPushButton#exportSecondaryButton { background:#ffffff; color:#334155; border:1px solid #cbd5e1; border-radius:8px; padding:10px 16px; font-weight:800; }
QPushButton#exportLinkButton { background:transparent; color:#1d4ed8; border:none; padding:2px 4px; font-weight:800; text-align:left; }
QLabel#exportWarning { background:#fffbeb; color:#92400e; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; }
QFrame#scopeOption { background:#f8fbff; border:1px solid #d8e2ed; border-radius:10px; }
"""

    def build(self):
        root = QVBoxLayout(self)

        hero = QFrame(); hero.setObjectName("exportHero")
        hl = QHBoxLayout(hero); hl.setContentsMargins(14, 12, 14, 12)
        txt = QVBoxLayout()
        t = QLabel("Excel’e Aktar"); t.setObjectName("exportHeroTitle")
        d = QLabel("STS verilerinden Excel raporu oluşturun. Tüm veri yerine belirli platformları seçerek daha hızlı çıktı alabilirsiniz.")
        d.setObjectName("exportMuted"); d.setWordWrap(True)
        txt.addWidget(t); txt.addWidget(d)
        hl.addLayout(txt, 1)
        b = QLabel("STS → XLSX"); b.setObjectName("exportBadge")
        hl.addWidget(b, 0, Qt.AlignTop)
        root.addWidget(hero)

        mid = QHBoxLayout(); root.addLayout(mid, 1)

        left_col = QVBoxLayout(); mid.addLayout(left_col, 1)
        right_col = QVBoxLayout(); mid.addLayout(right_col, 1)

        # Scope card
        scope_card = QFrame(); scope_card.setObjectName("exportCard")
        scl = QVBoxLayout(scope_card)
        tt = QLabel("Aktarım Kapsamı"); tt.setObjectName("exportCardTitle"); scl.addWidget(tt)
        self.rb_active = self._scope_row("Aktif platform", "Yalnızca şu anda seçili platformu aktarır. En hızlı seçenektir.")
        self.rb_selected = self._scope_row("Seçili platformlar", "Bir veya daha fazla platform seçerek özel Excel çıktısı oluşturur.")
        self.rb_all = self._scope_row("Tüm platformlar", "Tüm platformları tek Excel dosyasına aktarır.")
        self.rb_summary = self._scope_row("Sadece özet", "Platform sheetleri olmadan yalnızca özet rapor oluşturur.")
        for w in [self.rb_active, self.rb_selected, self.rb_all, self.rb_summary]:
            scl.addWidget(w)
        g = QButtonGroup(self)
        for rb in [self.rb_active.findChild(QRadioButton), self.rb_selected.findChild(QRadioButton), self.rb_all.findChild(QRadioButton), self.rb_summary.findChild(QRadioButton)]:
            g.addButton(rb)
            rb.toggled.connect(self._update_state)
        left_col.addWidget(scope_card)

        # Platform card
        platform_card = QFrame(); platform_card.setObjectName("exportCard")
        pl = QVBoxLayout(platform_card)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("Platformlar", objectName="exportCardTitle"))
        ph.addStretch(1)
        sel = QPushButton("Tümünü seç"); sel.setObjectName("exportLinkButton"); sel.clicked.connect(lambda: self._check_all(True))
        clr = QPushButton("Seçimi temizle"); clr.setObjectName("exportLinkButton"); clr.clicked.connect(lambda: self._check_all(False))
        ph.addWidget(sel); ph.addWidget(clr)
        pl.addLayout(ph)
        self.platform_list = QListWidget()
        for p in (self.store.platform_names() if hasattr(self.store, "platform_names") else []):
            c = self._platform_counts.get(str(p), 0)
            label = f"{p}    {c} sözleşme"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, str(p))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.platform_list.addItem(it)
        pl.addWidget(self.platform_list)
        left_col.addWidget(platform_card, 1)

        # content card
        content_card = QFrame(); content_card.setObjectName("exportCard")
        cl = QVBoxLayout(content_card)
        cl.addWidget(QLabel("Excel İçeriği", objectName="exportCardTitle"))
        grid = QGridLayout()
        self.cb_summary = self._opt_box("Özet sheet ekle", "Dosya geneli ve platform bazlı sayıları ekler.", True)
        self.cb_contract = self._opt_box("Sözleşme toplam satırları", "Sözleşme seviyesinde toplam satırları ekler.", True)
        self.cb_system = self._opt_box("Sistem toplam satırları", "Sistem bazında toplam satırları ekler.", True)
        self.cb_delivery = self._opt_box("Kabul/Teslimat satırları", "Kabul detay satırlarını ekler.", True)
        self.cb_comp = self._opt_box("Bileşen kolonları", "Her bileşen için sözleşme/teslim/kalan kolonları ekler.", True)
        self.cb_tags = self._opt_box("Etiketleri dahil et", "Sözleşme etiketlerini ayrı kolonda yazar.", True)
        for i,w in enumerate([self.cb_summary,self.cb_contract,self.cb_system,self.cb_delivery,self.cb_comp,self.cb_tags]):
            grid.addWidget(w, i % 3, i // 3)
        cl.addLayout(grid)
        left_col.addWidget(content_card)

        # summary card
        self.summary_card = QFrame(); self.summary_card.setObjectName("exportCard")
        sl = QVBoxLayout(self.summary_card)
        sl.addWidget(QLabel("Seçim Özeti", objectName="exportCardTitle"))
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        sl.addWidget(self.summary_label)
        right_col.addWidget(self.summary_card)

        self.warn = QLabel("")
        self.warn.setObjectName("exportWarning")
        right_col.addWidget(self.warn)
        right_col.addStretch(1)

        foot = QHBoxLayout(); root.addLayout(foot)
        foot.addStretch(1)
        cancel = QPushButton("İptal"); cancel.setObjectName("exportSecondaryButton"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Excel Oluştur"); ok.setObjectName("exportPrimaryButton"); ok.clicked.connect(self.accept_options)
        foot.addWidget(cancel); foot.addWidget(ok)

        if self.active_platform:
            self.rb_active.findChild(QRadioButton).setChecked(True)
        else:
            self.rb_all.findChild(QRadioButton).setChecked(True)

        for cb in [self.cb_summary.findChild(QCheckBox), self.cb_contract.findChild(QCheckBox), self.cb_system.findChild(QCheckBox), self.cb_delivery.findChild(QCheckBox), self.cb_comp.findChild(QCheckBox), self.cb_tags.findChild(QCheckBox)]:
            cb.toggled.connect(self._update_state)
        self._update_state()

    def _scope_row(self, title, desc):
        w = QFrame(); w.setObjectName("scopeOption")
        l = QVBoxLayout(w); l.setContentsMargins(10, 8, 10, 8)
        rb = QRadioButton(title)
        rb.setStyleSheet("font-weight:800;")
        md = QLabel(desc); md.setObjectName("exportMuted"); md.setStyleSheet("color:#64748b;background:transparent;")
        md.setWordWrap(True)
        l.addWidget(rb); l.addWidget(md)
        return w

    def _opt_box(self, title, desc, checked):
        w = QFrame(); w.setObjectName("scopeOption")
        l = QVBoxLayout(w); l.setContentsMargins(8, 8, 8, 8)
        cb = QCheckBox(title); cb.setChecked(checked); cb.setStyleSheet("font-weight:800;")
        md = QLabel(desc); md.setObjectName("exportMuted"); md.setStyleSheet("color:#64748b;background:transparent;")
        md.setWordWrap(True)
        l.addWidget(cb); l.addWidget(md)
        return w

    def _selected_platforms(self):
        out = []
        for i in range(self.platform_list.count()):
            it = self.platform_list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(str(it.data(Qt.UserRole) or ""))
        return out

    def _check_all(self, val):
        for i in range(self.platform_list.count()):
            self.platform_list.item(i).setCheckState(Qt.Checked if val else Qt.Unchecked)
        self._update_state()

    def _update_state(self):
        rb_active = self.rb_active.findChild(QRadioButton).isChecked()
        rb_selected = self.rb_selected.findChild(QRadioButton).isChecked()
        rb_all = self.rb_all.findChild(QRadioButton).isChecked()
        rb_summary = self.rb_summary.findChild(QRadioButton).isChecked()

        if rb_all:
            self._check_all(True)
            self.platform_list.setEnabled(False)
        elif rb_active:
            self._check_all(False)
            for i in range(self.platform_list.count()):
                it = self.platform_list.item(i)
                if str(it.data(Qt.UserRole) or "") == self.active_platform:
                    it.setCheckState(Qt.Checked)
            self.platform_list.setEnabled(False)
        elif rb_summary:
            self.platform_list.setEnabled(False)
        else:
            self.platform_list.setEnabled(True)

        summary_only = rb_summary
        csum = self.cb_summary.findChild(QCheckBox)
        if summary_only:
            csum.setChecked(True)
        csum.setEnabled(not summary_only)
        for box in [self.cb_contract, self.cb_system, self.cb_delivery, self.cb_comp, self.cb_tags]:
            box.findChild(QCheckBox).setEnabled(not summary_only)

        scope_name = "Aktif platform" if rb_active else "Seçili platformlar" if rb_selected else "Tüm platformlar" if rb_all else "Sadece özet"
        plats = self._selected_platforms() if (rb_selected or rb_active) else (self.store.platform_names() if rb_all else [])
        est = sum(self._platform_counts.get(p, 0) for p in plats) if plats else sum(self._platform_counts.values())
        self.summary_label.setText(
            f"Kapsam: {scope_name}\n"
            f"Platform sayısı: {len(plats) if plats else (0 if rb_summary else len(self.store.platform_names()))}\n"
            f"Tahmini sözleşme: {est}\n"
            f"Satırlar: Sözleşme({'Açık' if self.cb_contract.findChild(QCheckBox).isChecked() else 'Kapalı'}), "
            f"Sistem({'Açık' if self.cb_system.findChild(QCheckBox).isChecked() else 'Kapalı'}), "
            f"Kabul({'Açık' if self.cb_delivery.findChild(QCheckBox).isChecked() else 'Kapalı'})\n"
            f"Bileşen kolonları: {'Açık' if self.cb_comp.findChild(QCheckBox).isChecked() else 'Kapalı'}"
        )

        if rb_all and self.cb_delivery.findChild(QCheckBox).isChecked() and self.cb_comp.findChild(QCheckBox).isChecked():
            self.warn.setText("Bu seçim en kapsamlı ve en yavaş çıktıdır.")
        else:
            self.warn.setText("Büyük veri setlerinde tüm platformlar ve kabul satırlarıyla export işlemi birkaç dakika sürebilir.")

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
