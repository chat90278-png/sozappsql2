from __future__ import annotations
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit
from src.services.sts_database import format_log_timestamp
from src.ui.theme import STYLE


class ActivityLogDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.logs = []
        self.setWindowTitle("İşlem Geçmişi")
        self.resize(1200, 680)
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_logs()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("İşlem Geçmişi"); title.setObjectName("mainTitle")
        root.addWidget(title)
        root.addWidget(QLabel("STS veri dosyasında kayıtlı değişiklik geçmişini görüntüleyin."))
        filt = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Ara..."); self.search.returnPressed.connect(self.refresh_logs)
        self.platform = QComboBox(); self.platform.addItem("Tümü", "")
        for p in (self.store.platform_names() if hasattr(self.store, 'platform_names') else []): self.platform.addItem(str(p), str(p))
        self.action = QComboBox(); self.action.addItem("Tümü", "")
        self.limit = QComboBox();
        for t,v in [("100",100),("500",500),("1000",1000),("Tümü",0)]: self.limit.addItem(t,v)
        self.limit.setCurrentIndex(1)
        btn = QPushButton("Yenile"); btn.clicked.connect(self.refresh_logs)
        for w in [self.search, self.platform, self.action, self.limit, btn]: filt.addWidget(w)
        root.addLayout(filt)
        self.table = QTableWidget(0, 15)
        self.table.setHorizontalHeaderLabels([
            "ID", "Tarih", "İşlem Yapan", "İşlem Kaynağı", "Bilgisayar", "İşlem", "Kayıt Türü",
            "Kayıt ID", "Kayıt Anahtarı", "Platform ID", "Sözleşme No", "Mesaj", "Önce", "Sonra", "Detay",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.open_detail)
        root.addWidget(self.table)

    def refresh_logs(self):
        lim = self.limit.currentData()
        self.logs = self.store.list_logs(limit=int(lim or 0), action=self.action.currentData() or None, platform=self.platform.currentData() or None, search=self.search.text().strip() or None)
        actions = sorted({str(x.get('action') or '') for x in self.logs if str(x.get('action') or '')})
        cur = self.action.currentData() or ""
        self.action.blockSignals(True); self.action.clear(); self.action.addItem("Tümü", "")
        for a in actions: self.action.addItem(a, a)
        i = self.action.findData(cur); self.action.setCurrentIndex(i if i>=0 else 0); self.action.blockSignals(False)
        self.table.setRowCount(len(self.logs))
        for r,log in enumerate(self.logs):
            vals = [
                log.get("id", ""), format_log_timestamp(log.get("created_at", "")), log.get("actor") or "-",
                log.get("source") or "-", log.get("device_name") or "-", log.get("action") or "-",
                log.get("entity_type") or "-", log.get("entity_id") or "-", log.get("entity_key") or "-",
                log.get("platform_id") or "-", log.get("contract_no") or "-", log.get("message") or "-",
                log.get("before_json") or "-", log.get("after_json") or "-", log.get("payload_json") or "-",
            ]
            for c,v in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(v or '-')))

    def _detail_summary(self, log):
        parts = []
        for key in ("before_json", "after_json", "payload_json"):
            value = log.get(key)
            if value not in (None, "", "null"):
                parts.append(f"{key}: {str(value)[:120]}")
        return " | ".join(parts) or "-"

    def _pretty(self, txt):
        if txt in (None, "", "null"): return ""
        try: return json.dumps(json.loads(txt), ensure_ascii=False, indent=2)
        except Exception: return str(txt)

    def open_detail(self, row, _col):
        if row < 0 or row >= len(self.logs): return
        log = self.logs[row]
        d = QDialog(self); d.setWindowTitle("Log Detayı"); d.resize(900,650); d.setStyleSheet(STYLE)
        lay = QVBoxLayout(d)
        keys=["id","created_at","actor","source","device_name","action","entity_type","entity_id","entity_key","platform","contract_no","message"]
        for k in keys:
            value = format_log_timestamp(log.get(k, "")) if k == "created_at" else (log.get(k, "") or "-")
            lay.addWidget(QLabel(f"{k}: {value}"))
        for k in ["before_json","after_json","payload_json"]:
            lay.addWidget(QLabel(k))
            t=QPlainTextEdit(); t.setReadOnly(True); t.setPlainText(self._pretty(log.get(k))); lay.addWidget(t)
        d.exec()
