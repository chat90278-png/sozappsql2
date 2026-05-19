from __future__ import annotations
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QHBoxLayout, QPushButton, QPlainTextEdit, QFileDialog, QMessageBox
)
from src.ui.theme import STYLE


class DatabaseManagementDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Database Yönetimi")
        self.resize(980, 760)
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_all()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Database Yönetimi"); title.setObjectName("mainTitle")
        root.addWidget(title)
        root.addWidget(QLabel("STS veri dosyasının durumunu görüntüleyin ve güvenli bakım işlemlerini çalıştırın."))

        self.info = QLabel("")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        self.counts = QTableWidget(0, 2)
        self.counts.setHorizontalHeaderLabels(["Tablo", "Kayıt Sayısı"])
        self.counts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.counts.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.counts)

        row = QHBoxLayout()
        b1 = QPushButton("Integrity Check"); b1.clicked.connect(self.run_integrity)
        b2 = QPushButton("Foreign Key Check"); b2.clicked.connect(self.run_fk)
        b3 = QPushButton("Yedek Al"); b3.clicked.connect(self.run_backup)
        b4 = QPushButton("Optimize / VACUUM"); b4.clicked.connect(self.run_vacuum)
        b5 = QPushButton("Analiz / PRAGMA optimize"); b5.clicked.connect(self.run_optimize)
        for b in [b1,b2,b3,b4,b5]: row.addWidget(b)
        root.addLayout(row)

        self.result = QPlainTextEdit(); self.result.setReadOnly(True)
        root.addWidget(self.result)

        self.logs = QTableWidget(0, 4)
        self.logs.setHorizontalHeaderLabels(["Tarih", "Kullanıcı", "İşlem", "Açıklama"])
        self.logs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.logs.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.logs)

    def refresh_all(self):
        st = self.store.database_stats()
        self.info.setText(
            f"Dosya: {st.get('path')}\n"
            f"Boyut: {st.get('file_size_mb')} MB ({st.get('file_size_bytes')} bytes)\n"
            f"journal_mode: {st.get('journal_mode')} | page_count: {st.get('page_count')} | page_size: {st.get('page_size')} | freelist: {st.get('freelist_count')}"
        )
        counts = st.get("table_counts", {})
        self.counts.setRowCount(len(counts))
        for r, (k, v) in enumerate(counts.items()):
            self.counts.setItem(r, 0, QTableWidgetItem(str(k)))
            self.counts.setItem(r, 1, QTableWidgetItem(str(v)))

        if hasattr(self.store, "list_logs"):
            logs = self.store.list_logs(limit=10)
            self.logs.setRowCount(len(logs))
            for r, it in enumerate(logs):
                self.logs.setItem(r, 0, QTableWidgetItem(str(it.get("created_at", ""))))
                self.logs.setItem(r, 1, QTableWidgetItem(str(it.get("actor", ""))))
                self.logs.setItem(r, 2, QTableWidgetItem(str(it.get("action", ""))))
                self.logs.setItem(r, 3, QTableWidgetItem(str(it.get("message", ""))))

    def run_integrity(self):
        rows = self.store.integrity_check()
        self.result.setPlainText("\n".join(rows) if rows else "ok")

    def run_fk(self):
        rows = self.store.foreign_key_check()
        if not rows:
            self.result.setPlainText("Foreign key sorunu bulunamadı.")
        else:
            self.result.setPlainText("\n".join(str(x) for x in rows))

    def run_backup(self):
        base = Path(getattr(self.store, 'path', 'database.sts'))
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_default = base.with_name(f"{base.stem}_backup_{ts}.sts")
        p, _ = QFileDialog.getSaveFileName(self, "Yedek Al", str(target_default), "STS (*.sts)")
        if not p:
            return
        res = self.store.backup_database(p)
        QMessageBox.information(self, "Yedek", f"Yedek oluşturuldu:\n{res.get('target_path')}")
        self.refresh_all()

    def run_vacuum(self):
        ans = QMessageBox.question(self, "Onay", "Bu işlem veritabanını optimize eder. Büyük dosyalarda biraz sürebilir. Devam edilsin mi?")
        if ans != QMessageBox.Yes:
            return
        res = self.store.vacuum()
        self.result.setPlainText(f"VACUUM tamamlandı\nÖnce: {res.get('before_bytes')}\nSonra: {res.get('after_bytes')}")
        self.refresh_all()

    def run_optimize(self):
        self.store.optimize()
        QMessageBox.information(self, "Optimize", "PRAGMA optimize tamamlandı.")
        self.refresh_all()
