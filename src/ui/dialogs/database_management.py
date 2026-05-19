from __future__ import annotations
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QFileDialog, QMessageBox, QTabWidget
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
        self.setWindowTitle("Database Yönetimi")
        self.resize(1280, 820)
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_all()

    def build(self):
        root = QVBoxLayout(self)
        hdr = QLabel("Database Yönetimi"); hdr.setObjectName("mainTitle")
        root.addWidget(hdr)
        root.addWidget(QLabel("STS veri dosyasının durumunu görüntüleyin ve güvenli bakım işlemlerini çalıştırın."))

        content = QHBoxLayout(); root.addLayout(content, 1)

        left = QVBoxLayout(); content.addLayout(left, 0)
        self.card_file = QLabel(); self.card_file.setObjectName("panelTitle"); self.card_file.setMinimumWidth(360); self.card_file.setWordWrap(True)
        left.addWidget(self.card_file)
        self.card_health = QLabel(); self.card_health.setObjectName("panelTitle"); self.card_health.setWordWrap(True)
        left.addWidget(self.card_health)
        left.addStretch(1)

        tabs = QTabWidget(); content.addWidget(tabs, 1)

        # Tables tab
        t1 = QFrame(); l1 = QVBoxLayout(t1)
        frow = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Tablo ara..."); self.search.textChanged.connect(self.refresh_tables)
        self.cat = QComboBox(); self.cat.addItems(["Tümü", "Temel", "İlişki", "Log"]); self.cat.currentIndexChanged.connect(self.refresh_tables)
        rbtn = QPushButton("Yenile"); rbtn.clicked.connect(self.refresh_all)
        frow.addWidget(self.search); frow.addWidget(self.cat); frow.addWidget(rbtn)
        l1.addLayout(frow)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Tablo", "Ne İşe Yarar?", "Kayıt Sayısı", "Durum", "İşlem"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        l1.addWidget(self.table)
        tabs.addTab(t1, "Tablolar")

        # Maintenance tab
        t2 = QFrame(); l2 = QVBoxLayout(t2)
        self.result = QPlainTextEdit(); self.result.setReadOnly(True)
        for text,desc,fn in [
            ("Sağlık Kontrolü Yap","SQLite bütünlük kontrolü yapar. Dosyanın bozuk olup olmadığını anlamak için kullanılır.", self.run_integrity),
            ("İlişkileri Kontrol Et","Sözleşme, sistem, kabul ve bileşen bağlantılarında kopuk kayıt var mı kontrol eder.", self.run_fk),
            ("STS Yedeği Oluştur","Açık STS dosyasının güvenli bir kopyasını oluşturur. Bakım öncesi önerilir.", self.run_backup),
            ("Optimize Et","Boş alanları temizler ve dosyayı toparlar. Büyük dosyalarda biraz sürebilir.", self.run_vacuum),
            ("Hızlı Bakım / Analiz","SQLite sorgu planlarını günceller. Genellikle kısa sürer.", self.run_optimize),
        ]:
            c = QFrame(); cl = QVBoxLayout(c)
            b = QPushButton(text); b.clicked.connect(fn)
            cl.addWidget(b); cl.addWidget(QLabel(desc))
            l2.addWidget(c)
        l2.addWidget(self.result, 1)
        tabs.addTab(t2, "Bakım İşlemleri")

        # Logs tab
        t3 = QFrame(); l3 = QVBoxLayout(t3)
        top = QHBoxLayout(); top.addStretch(1)
        b = QPushButton("İşlem Geçmişini Aç")
        b.clicked.connect(self.open_activity_logs)
        top.addWidget(b); l3.addLayout(top)
        self.logs = QTableWidget(0,4)
        self.logs.setHorizontalHeaderLabels(["Tarih", "Kullanıcı", "İşlem", "Açıklama"])
        self.logs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.logs.setEditTriggers(QTableWidget.NoEditTriggers)
        l3.addWidget(self.logs)
        tabs.addTab(t3, "Son Loglar")

    def refresh_all(self):
        self.stats = self.store.database_stats()
        p = self.stats.get("path", "")
        counts = self.stats.get("table_counts", {})
        total = sum(int(v or 0) for v in counts.values())
        self.card_file.setText(
            f"Veri Dosyası\n\nDosya yolu:\n{p}\n\nDosya boyutu: {self.stats.get('file_size_mb')} MB\n"
            f"Journal mode: {self.stats.get('journal_mode')}\nToplam tablo: {len(counts)}\nToplam kayıt: {total}"
        )
        self.card_health.setText(
            f"Sağlık Durumu\n\nVeritabanı Bütünlüğü: hazır\nİlişki Kontrolü: hazır\n"
            f"Boş Alan / Freelist: {self.stats.get('freelist_count',0)}\nSon Bakım: -"
        )
        self.refresh_tables()
        if hasattr(self.store, "list_logs"):
            logs = self.store.list_logs(limit=20)
            self.logs.setRowCount(len(logs))
            for r, it in enumerate(logs):
                self.logs.setItem(r,0,QTableWidgetItem(str(it.get("created_at", ""))))
                self.logs.setItem(r,1,QTableWidgetItem(str(it.get("actor", ""))))
                self.logs.setItem(r,2,QTableWidgetItem(str(it.get("action", ""))))
                self.logs.setItem(r,3,QTableWidgetItem(str(it.get("message", ""))))

    def refresh_tables(self):
        counts = self.stats.get("table_counts", {})
        q = self.search.text().strip().lower()
        cat = self.cat.currentText()
        rows = []
        for t, desc in TABLE_INFO.items():
            if q and q not in t.lower() and q not in desc.lower():
                continue
            if cat == "Temel" and t not in {"platforms","users","components","tags","contracts"}:
                continue
            if cat == "İlişki" and t not in {"component_platforms","systems","system_components","deliveries","delivery_components","contract_tags"}:
                continue
            if cat == "Log" and t != "activity_logs":
                continue
            cnt = int(counts.get(t, 0))
            rows.append((t, desc, cnt, "Hazır" if cnt >= 0 else "-"))
        self.table.setRowCount(len(rows))
        for r, (t, d, c, st) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(t))
            self.table.setItem(r, 1, QTableWidgetItem(d))
            self.table.setItem(r, 2, QTableWidgetItem(str(c)))
            self.table.setItem(r, 3, QTableWidgetItem(st))
            btn = QPushButton("Önizle")
            btn.clicked.connect(lambda _=False, tt=t: self.preview_table(tt))
            self.table.setCellWidget(r, 4, btn)

    def preview_table(self, table_name: str):
        rows = self.store.preview_table(table_name, 100)
        d = QDialog(self); d.setWindowTitle(f"{table_name} - İlk 100 Satır"); d.resize(1100, 700); d.setStyleSheet(STYLE)
        l = QVBoxLayout(d)
        l.addWidget(QLabel("İlk 100 Satır (Read-only)"))
        t = QTableWidget()
        cols = list(rows[0].keys()) if rows else []
        t.setColumnCount(len(cols)); t.setHorizontalHeaderLabels(cols)
        t.setRowCount(len(rows)); t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, item in enumerate(rows):
            for c, k in enumerate(cols):
                t.setItem(r, c, QTableWidgetItem(str(item.get(k, ""))))
        l.addWidget(t)
        d.exec()

    def run_integrity(self):
        self.result.setPlainText("İşlem başladı: integrity_check")
        rows = self.store.integrity_check()
        self.result.appendPlainText("İşlem tamamlandı")
        self.result.appendPlainText("\n".join(rows) if rows else "ok")

    def run_fk(self):
        self.result.setPlainText("İşlem başladı: foreign_key_check")
        rows = self.store.foreign_key_check()
        self.result.appendPlainText("İşlem tamamlandı")
        self.result.appendPlainText("Foreign key sorunu bulunamadı." if not rows else "\n".join(str(x) for x in rows))

    def run_backup(self):
        base = Path(getattr(self.store, 'path', 'database.sts'))
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        p, _ = QFileDialog.getSaveFileName(self, "Yedek Al", str(base.with_name(f"{base.stem}_backup_{ts}.sts")), "STS (*.sts)")
        if not p:
            return
        self.result.setPlainText("İşlem başladı: backup")
        res = self.store.backup_database(p)
        self.result.appendPlainText(f"İşlem tamamlandı\n{res}")
        QMessageBox.information(self, "Yedek", f"Yedek oluşturuldu:\n{res.get('target_path')}")
        self.refresh_all()

    def run_vacuum(self):
        if QMessageBox.question(self, "Onay", "Bu işlem veritabanını optimize eder. Büyük dosyalarda biraz sürebilir. Devam edilsin mi?") != QMessageBox.Yes:
            return
        self.result.setPlainText("İşlem başladı: vacuum")
        res = self.store.vacuum()
        self.result.appendPlainText(f"İşlem tamamlandı\nÖnce: {res.get('before_bytes')}\nSonra: {res.get('after_bytes')}")
        self.refresh_all()

    def run_optimize(self):
        self.result.setPlainText("İşlem başladı: pragma optimize")
        res = self.store.optimize()
        self.result.appendPlainText(f"İşlem tamamlandı\n{res}")
        self.refresh_all()

    def open_activity_logs(self):
        from src.ui.dialogs.activity_logs import ActivityLogDialog
        dlg = ActivityLogDialog(self.store, self)
        dlg.exec()
