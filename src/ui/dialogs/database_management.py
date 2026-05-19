from __future__ import annotations
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from src.ui.theme import STYLE

TABLE_INFO = {
    "platforms": "Platform adları, dışlama durumu ve platform logoları",
    "users": "Sözleşme girişinde seçilen kullanıcılar",
    "components": "Tanımlı bileşenler",
    "component_platforms": "Bileşenlerin hangi platformlarda kullanılacağını belirleyen yetkiler",
    "tags": "Etiket tanımları",
    "contracts": "Ana sözleşme ve SD kayıtlarının ana kart bilgileri",
    "systems": "Sözleşmelere bağlı sistemler",
    "system_components": "Her sistemdeki bileşen sözleşme adetleri",
    "deliveries": "Sistemlere bağlı kabul/teslimat kayıtları",
    "delivery_components": "Kabul bazında planlanan ve teslim edilen bileşen adetleri",
    "contract_tags": "Sözleşme-etiket bağlantıları",
    "activity_logs": "Kullanıcı işlemleri, export, bakım ve değişiklik geçmişi",
}


class DatabaseManagementDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.stats = {}
        self._last_maintenance = "-"

        self.setWindowTitle("Database Yönetimi")
        self.setMinimumSize(1180, 720)
        self.resize(1220, 780)
        self.setStyleSheet(STYLE + self._local_style())

        self.build()
        self.refresh_all()

    def _local_style(self) -> str:
        return """
QFrame#dbHero { background:#0f2742; border-radius:16px; }
QLabel#dbHeroTitle { color:#ffffff; font-size:24px; font-weight:900; background:transparent; }
QLabel#dbHeroDesc { color:#c8d8ea; font-size:12px; background:transparent; }
QLabel#dbBadgeOk { background:#123c24; color:#b9f7ce; border:1px solid rgba(185,247,206,0.35); border-radius:12px; padding:7px 12px; font-weight:800; }

QFrame#dbCard { background:#ffffff; border:1px solid #d6e2f0; border-radius:14px; }
QLabel#dbCardTitle { color:#12345a; font-size:14px; font-weight:800; background:transparent; }
QLabel#dbMuted { color:#667995; font-size:12px; background:transparent; }
QLabel#dbFileName { color:#0f2742; font-size:13px; font-weight:900; background:transparent; }

QFrame#dbMetric { background:#e8f1ff; border:1px solid #cfe1fb; border-radius:12px; }
QLabel#dbMetricLabel { color:#527093; font-size:10px; font-weight:800; background:transparent; }
QLabel#dbMetricValue { color:#0f2f58; font-size:17px; font-weight:900; background:transparent; }

QFrame#dbHealthRow { background:#fbfdff; border:1px solid #d6e2f0; border-radius:10px; }
QLabel#dbHealthLabel { color:#1e3a5f; font-size:12px; background:transparent; }
QLabel#dbBadgeWarn { background:#fef3c7; color:#92400e; border-radius:10px; padding:3px 9px; font-size:11px; font-weight:800; }
QLabel#dbBadgeErr { background:#fee2e2; color:#991b1b; border-radius:10px; padding:3px 9px; font-size:11px; font-weight:800; }

QPushButton#dbPrimaryButton { background:#2563eb; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:800; }
QPushButton#dbSoftButton { background:#e8f1ff; color:#1d4ed8; border:1px solid #cfe1fb; border-radius:10px; padding:7px 12px; font-weight:800; }
QPushButton#dbPreviewButton { background:#2563eb; color:#ffffff; border:1px solid #1d4ed8; border-radius:8px; padding:4px 10px; font-weight:800; min-width:118px; min-height:30px; }

QPlainTextEdit#dbResultBox { background:#0b1727; color:#d7e8ff; border:1px solid #1f3759; border-radius:10px; }
QTabWidget::pane { border:1px solid #d6e2f0; border-radius:12px; background:#ffffff; top:-1px; }
QTabBar::tab { background:#f3f7fc; color:#37526f; border:1px solid #d6e2f0; border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; padding:8px 14px; font-weight:800; }
QTabBar::tab:selected { background:#2563eb; color:white; }
"""

    def build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("dbHero")
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(18, 14, 18, 14)
        hero_text = QVBoxLayout()
        t = QLabel("Database Yönetimi")
        t.setObjectName("dbHeroTitle")
        d = QLabel("STS veri dosyasının durumunu görüntüleyin, tabloları inceleyin ve güvenli bakım işlemlerini çalıştırın.")
        d.setObjectName("dbHeroDesc")
        d.setWordWrap(True)
        hero_text.addWidget(t)
        hero_text.addWidget(d)
        hero_l.addLayout(hero_text, 1)
        badge = QLabel("• SQLite bağlantısı aktif")
        badge.setObjectName("dbBadgeOk")
        hero_l.addWidget(badge, 0, Qt.AlignTop)
        root.addWidget(hero)

        content = QHBoxLayout()
        content.setSpacing(12)
        root.addLayout(content, 1)

        # Left panel
        left_wrap = QVBoxLayout()
        left_wrap.setSpacing(10)
        content.addLayout(left_wrap, 0)

        self.file_card = self._make_card("Veri Dosyası")
        self.file_name = QLabel("-")
        self.file_name.setObjectName("dbFileName")
        self.file_path = QLabel("-")
        self.file_path.setObjectName("dbMuted")
        self.file_path.setWordWrap(True)
        self.file_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_card.layout().addWidget(self.file_name)
        self.file_card.layout().addWidget(self.file_path)
        self.file_card.setFixedWidth(330)
        left_wrap.addWidget(self.file_card)

        summary_card = self._make_card("Özet")
        mg = QGridLayout()
        mg.setSpacing(8)
        self.m_file_size = self._metric("Dosya Boyutu", "-")
        self.m_journal = self._metric("Journal", "-")
        self.m_tables = self._metric("Tablo", "-")
        self.m_total = self._metric("Toplam Kayıt", "-")
        mg.addWidget(self.m_file_size, 0, 0)
        mg.addWidget(self.m_journal, 0, 1)
        mg.addWidget(self.m_tables, 1, 0)
        mg.addWidget(self.m_total, 1, 1)
        summary_card.layout().addLayout(mg)
        summary_card.setFixedWidth(330)
        left_wrap.addWidget(summary_card)

        health_card = self._make_card("Sağlık Durumu")
        self.row_integrity = self._health_row("Veritabanı Bütünlüğü", "Hazır")
        self.row_fk = self._health_row("İlişki Kontrolü", "Sorun Yok")
        self.row_free = self._health_row("Boş Sayfa / Freelist", "0")
        self.row_maint = self._health_row("Son Bakım", "-")
        health_card.layout().addWidget(self.row_integrity)
        health_card.layout().addWidget(self.row_fk)
        health_card.layout().addWidget(self.row_free)
        health_card.layout().addWidget(self.row_maint)
        health_card.setFixedWidth(330)
        left_wrap.addWidget(health_card)
        left_wrap.addStretch(1)

        # Right panel tabs
        tabs = QTabWidget()
        content.addWidget(tabs, 1)

        t1 = QFrame(); l1 = QVBoxLayout(t1)
        frow = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Tablo ara... örn. contracts, systems"); self.search.textChanged.connect(self.refresh_tables)
        self.cat = QComboBox(); self.cat.addItems(["Tüm tablolar", "Ana veri", "İlişkili veri", "Log / Sistem"]); self.cat.currentIndexChanged.connect(self.refresh_tables)
        rbtn = QPushButton("Yenile"); rbtn.setObjectName("dbPrimaryButton"); rbtn.clicked.connect(self.refresh_all)
        frow.addWidget(self.search, 1); frow.addWidget(self.cat); frow.addWidget(rbtn)
        l1.addLayout(frow)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Tablo", "Ne İşe Yarar?", "Kayıt Sayısı", "Durum", "İşlem"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 140)
        l1.addWidget(self.table)
        tabs.addTab(t1, "Tablolar")

        t2 = QFrame(); l2 = QVBoxLayout(t2)
        grid = QGridLayout(); grid.setSpacing(10)
        ops = [
            ("Sağlık Kontrolü Yap", "SQLite bütünlük kontrolü yapar. Dosyanın bozuk olup olmadığını anlamak için kullanılır.", self.run_integrity, "dbSoftButton"),
            ("İlişkileri Kontrol Et", "Sözleşme, sistem, kabul ve bileşen bağlantılarında kopuk kayıt var mı kontrol eder.", self.run_fk, "dbSoftButton"),
            ("STS Yedeği Oluştur", "Açık STS dosyasının güvenli bir kopyasını oluşturur. Bakım öncesi önerilir.", self.run_backup, "dbPrimaryButton"),
            ("Optimize Et", "Boş alanları temizler ve dosyayı toparlar. Büyük dosyalarda biraz sürebilir.", self.run_vacuum, "dbSoftButton"),
            ("Hızlı Bakım / Analiz", "SQLite sorgu planlarını günceller. Genellikle kısa sürer.", self.run_optimize, "dbSoftButton"),
        ]
        for idx, (title, desc, fn, btn_style) in enumerate(ops):
            c = QFrame(); c.setObjectName("dbCard")
            cl = QVBoxLayout(c)
            tt = QLabel(title); tt.setObjectName("dbCardTitle")
            dd = QLabel(desc); dd.setWordWrap(True); dd.setObjectName("dbMuted")
            b = QPushButton(title); b.setObjectName(btn_style); b.clicked.connect(fn)
            cl.addWidget(tt); cl.addWidget(dd); cl.addWidget(b, 0, Qt.AlignLeft)
            grid.addWidget(c, idx // 2, idx % 2)
        l2.addLayout(grid)

        self.result = QPlainTextEdit()
        self.result.setObjectName("dbResultBox")
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("Sonuç alanı\n> İşlem çıktılarını burada göreceksiniz.")
        l2.addWidget(self.result, 1)
        tabs.addTab(t2, "Bakım İşlemleri")

        t3 = QFrame(); l3 = QVBoxLayout(t3)
        top = QHBoxLayout(); top.addStretch(1)
        b = QPushButton("İşlem Geçmişini Aç"); b.setObjectName("dbSoftButton"); b.clicked.connect(self.open_activity_logs)
        top.addWidget(b); l3.addLayout(top)
        self.logs = QTableWidget(0, 4)
        self.logs.setHorizontalHeaderLabels(["Tarih", "Kullanıcı", "İşlem", "Açıklama"])
        self.logs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.logs.verticalHeader().setVisible(False)
        self.logs.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.logs.setColumnWidth(0, 170)
        self.logs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.logs.setColumnWidth(1, 140)
        self.logs.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.logs.setColumnWidth(2, 200)
        self.logs.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        l3.addWidget(self.logs)
        tabs.addTab(t3, "Son Loglar")

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("dbCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 12, 12, 12)
        h = QLabel(title)
        h.setObjectName("dbCardTitle")
        l.addWidget(h)
        return card

    def _metric(self, label: str, value: str) -> QFrame:
        f = QFrame(); f.setObjectName("dbMetric")
        l = QVBoxLayout(f)
        l.setContentsMargins(10, 8, 10, 8)
        a = QLabel(label); a.setObjectName("dbMetricLabel")
        b = QLabel(value); b.setObjectName("dbMetricValue")
        l.addWidget(a); l.addWidget(b)
        f._value_label = b
        return f

    def _health_row(self, label: str, badge: str) -> QFrame:
        r = QFrame(); r.setObjectName("dbHealthRow")
        l = QHBoxLayout(r)
        l.setContentsMargins(9, 7, 9, 7)
        a = QLabel(label); a.setObjectName("dbHealthLabel")
        b = QLabel(badge); b.setObjectName("dbBadgeOk")
        l.addWidget(a); l.addStretch(1); l.addWidget(b)
        r._badge = b
        return r

    def refresh_all(self):
        self.stats = self.store.database_stats()
        p = str(self.stats.get("path", ""))
        counts = self.stats.get("table_counts", {})
        total = sum(int(v or 0) for v in counts.values())
        page_count = int(self.stats.get("page_count", 0) or 0)
        page_size = int(self.stats.get("page_size", 0) or 0)

        fp = Path(p) if p else Path("database.sts")
        self.file_name.setText(fp.name)
        self.file_path.setText(str(fp))
        self.file_path.setToolTip(str(fp))

        self.m_file_size._value_label.setText(f"{self.stats.get('file_size_mb', 0):.1f} MB")
        self.m_journal._value_label.setText(str(self.stats.get("journal_mode", "-") or "-"))
        self.m_tables._value_label.setText(str(len(counts)))
        self.m_total._value_label.setText(self._format_count(total))

        self.row_integrity._badge.setText("Hazır")
        self.row_fk._badge.setText("Sorun Yok")
        self.row_free._badge.setText(str(self.stats.get("freelist_count", 0)))
        self.row_maint._badge.setText(self._last_maintenance)

        self.refresh_tables()
        if hasattr(self.store, "list_logs"):
            logs = self.store.list_logs(limit=20)
            self.logs.setRowCount(len(logs))
            for r, it in enumerate(logs):
                for c, k in enumerate(("created_at", "actor", "action", "message")):
                    tx = str(it.get(k, ""))
                    item = QTableWidgetItem(tx)
                    item.setToolTip(tx)
                    self.logs.setItem(r, c, item)

    def refresh_tables(self):
        counts = self.stats.get("table_counts", {})
        q = self.search.text().strip().lower()
        cat = self.cat.currentText()
        rows = []
        for t, desc in TABLE_INFO.items():
            if q and q not in t.lower() and q not in desc.lower():
                continue
            if cat == "Ana veri" and t not in {"platforms", "users", "components", "tags", "contracts"}:
                continue
            if cat == "İlişkili veri" and t not in {"component_platforms", "systems", "system_components", "deliveries", "delivery_components", "contract_tags"}:
                continue
            if cat == "Log / Sistem" and t != "activity_logs":
                continue
            cnt = int(counts.get(t, 0))
            rows.append((t, desc, cnt))

        self.table.setRowCount(len(rows))
        for r, (t, d, c) in enumerate(rows):
            name_item = QTableWidgetItem(t)
            name_item.setToolTip(t)
            self.table.setItem(r, 0, name_item)

            desc_item = QTableWidgetItem(d)
            desc_item.setToolTip(d)
            self.table.setItem(r, 1, desc_item)

            self.table.setItem(r, 2, QTableWidgetItem(self._format_count(c)))

            st = "Normal" if c < 1_000_000 else "Büyük Tablo" if c < 3_000_000 else "Çok Büyük"
            st_item = QTableWidgetItem(st)
            self.table.setItem(r, 3, st_item)

            btn = QPushButton("Önizle (100)" if c >= 1_000_000 else "Önizle")
            btn.setObjectName("dbPreviewButton")
            btn.clicked.connect(lambda _=False, tt=t: self.preview_table(tt))
            w = QFrame()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(4, 2, 4, 2)
            wl.addWidget(btn, 0, Qt.AlignCenter)
            self.table.setCellWidget(r, 4, w)

    def preview_table(self, table_name: str):
        rows = self.store.preview_table(table_name, 100)
        d = QDialog(self)
        d.setWindowTitle(f"{table_name} önizleme")
        d.resize(1100, 700)
        d.setStyleSheet(STYLE)
        l = QVBoxLayout(d)
        info = QLabel("İlk 100 kayıt read-only gösteriliyor.")
        info.setWordWrap(True)
        l.addWidget(info)
        t = QTableWidget()
        cols = list(rows[0].keys()) if rows else []
        t.setColumnCount(len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.setRowCount(len(rows))
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for r, item in enumerate(rows):
            for c, k in enumerate(cols):
                val = str(item.get(k, ""))
                cell = QTableWidgetItem(val)
                cell.setToolTip(val)
                t.setItem(r, c, cell)
        l.addWidget(t)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(d.accept)
        l.addWidget(close_btn, 0, Qt.AlignRight)
        d.exec()

    def _append_result(self, text: str):
        self.result.appendPlainText(text)

    def run_integrity(self):
        self.result.setPlainText("İşlem başladı: integrity_check")
        rows = self.store.integrity_check()
        ok = any(str(x).lower() == "ok" for x in rows)
        self._append_result("İşlem tamamlandı")
        self._append_result("\n".join(rows) if rows else "ok")
        self.row_integrity._badge.setText("OK" if ok else "Uyarı")
        self.row_integrity._badge.setObjectName("dbBadgeOk" if ok else "dbBadgeWarn")
        self.row_integrity._badge.style().unpolish(self.row_integrity._badge); self.row_integrity._badge.style().polish(self.row_integrity._badge)
        self._last_maintenance = datetime.now().strftime("%Y-%m-%d %H:%M")

    def run_fk(self):
        self.result.setPlainText("İşlem başladı: foreign_key_check")
        rows = self.store.foreign_key_check()
        self._append_result("İşlem tamamlandı")
        self._append_result("Foreign key sorunu bulunamadı." if not rows else "\n".join(str(x) for x in rows))
        ok = not rows
        self.row_fk._badge.setText("Sorun Yok" if ok else "Uyarı")
        self.row_fk._badge.setObjectName("dbBadgeOk" if ok else "dbBadgeWarn")
        self.row_fk._badge.style().unpolish(self.row_fk._badge); self.row_fk._badge.style().polish(self.row_fk._badge)
        self._last_maintenance = datetime.now().strftime("%Y-%m-%d %H:%M")

    def run_backup(self):
        base = Path(getattr(self.store, "path", "database.sts"))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p, _ = QFileDialog.getSaveFileName(self, "Yedek Al", str(base.with_name(f"{base.stem}_backup_{ts}.sts")), "STS (*.sts)")
        if not p:
            return
        self.result.setPlainText("İşlem başladı: backup")
        res = self.store.backup_database(p)
        self._append_result(f"İşlem tamamlandı\n{res}")
        QMessageBox.information(self, "Yedek", f"Yedek oluşturuldu:\n{res.get('target_path')}")
        self._last_maintenance = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.refresh_all()

    def run_vacuum(self):
        if QMessageBox.question(self, "Onay", "Bu işlem veritabanını optimize eder. Büyük dosyalarda biraz sürebilir. Devam edilsin mi?") != QMessageBox.Yes:
            return
        self.result.setPlainText("İşlem başladı: vacuum")
        res = self.store.vacuum()
        self._append_result(f"İşlem tamamlandı\nÖnce: {res.get('before_bytes')}\nSonra: {res.get('after_bytes')}")
        self._last_maintenance = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.refresh_all()

    def run_optimize(self):
        self.result.setPlainText("İşlem başladı: pragma optimize")
        res = self.store.optimize()
        self._append_result(f"İşlem tamamlandı\n{res}")
        self._last_maintenance = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.refresh_all()

    def open_activity_logs(self):
        from src.ui.dialogs.activity_logs import ActivityLogDialog

        dlg = ActivityLogDialog(self.store, self)
        dlg.exec()

    @staticmethod
    def _format_count(value: int) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        return f"{value:,}".replace(",", ".")
