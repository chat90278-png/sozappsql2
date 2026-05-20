from __future__ import annotations

import json
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.ui.theme import STYLE


class PerformanceTrackingDialog(QDialog):
    DIALOG_ID = "performanceTrackingDialog"

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName(self.DIALOG_ID)
        self.stats = {}
        self.logs = []
        self.setWindowTitle("Performans Takip - STS")
        self.setMinimumSize(1000, 620)
        self.resize(1180, 680)
        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        self.refresh_all()

    def _local_style(self):
        return """
QFrame#perfHero { background:#10263f; border-radius:14px; }
QLabel#perfHeroTitle { color:#fff; font-size:24px; font-weight:900; }
QLabel#perfHeroDesc { color:#c8d8ea; font-size:12px; }
QFrame#perfCard { background:#fff; border:1px solid #d6e2f0; border-radius:14px; }
QLabel#perfCardTitle { color:#12345a; font-size:15px; font-weight:800; }
QLabel#perfMuted { color:#667995; font-size:12px; }
QDialog#performanceTrackingDialog QLabel, QDialog#performanceTrackingDialog QCheckBox, QDialog#performanceTrackingDialog QRadioButton { background: transparent; }
QLineEdit, QComboBox { background:#fff; border:1px solid #d6e2f0; border-radius:8px; padding:6px 8px; }
QTableWidget { background:#fff; border:1px solid #d6e2f0; border-radius:10px; gridline-color:#e5edf8; }
QHeaderView::section { background:#edf3ff; border:none; padding:6px; color:#264463; font-weight:700; }
"""

    def _build(self):
        root = QVBoxLayout(self)

        hero = QFrame(); hero.setObjectName("perfHero")
        hl = QHBoxLayout(hero)
        tbox = QVBoxLayout()
        t = QLabel("Performans Takip"); t.setObjectName("perfHeroTitle")
        d = QLabel("Uygulama açılışı, kayıt, cevap ve sorgu sürelerini sade şekilde izleyin.")
        d.setObjectName("perfHeroDesc")
        tbox.addWidget(t); tbox.addWidget(d)
        hl.addLayout(tbox, 1)
        root.addWidget(hero)

        body = QHBoxLayout(); root.addLayout(body, 1)
        left = QVBoxLayout(); right = QVBoxLayout()
        body.addLayout(left, 0); body.addLayout(right, 1)

        # Left - Veri Hacmi
        vcard = QFrame(); vcard.setObjectName("perfCard")
        vl = QVBoxLayout(vcard)
        head = QHBoxLayout()
        head.addWidget(QLabel("Veri Hacmi", objectName="perfCardTitle"))
        head.addStretch(1)
        head.addWidget(QLabel("son okuma", objectName="perfMuted"))
        vl.addLayout(head)

        vg = QGridLayout()
        self.v_size = QLabel(); self.v_total = QLabel(); self.v_contract = QLabel(); self.v_system = QLabel(); self.v_delivery = QLabel(); self.v_big = QLabel()
        items = [
            ("Dosya Boyutu", self.v_size),
            ("Toplam Kayıt", self.v_total),
            ("Sözleşme", self.v_contract),
            ("Sistem", self.v_system),
            ("Kabul", self.v_delivery),
            ("En Büyük Tablo", self.v_big),
        ]
        for i, (k, w) in enumerate(items):
            f = QFrame(); f.setObjectName("perfCard")
            l = QVBoxLayout(f)
            l.addWidget(QLabel(k, objectName="perfMuted"))
            w.setStyleSheet("font-size:26px;font-weight:900;color:#0f2f58;")
            l.addWidget(w)
            vg.addWidget(f, i, 0)
        vl.addLayout(vg)
        left.addWidget(vcard)
        left.addStretch(1)

        # Right - KPI cards
        metric_wrap = QGridLayout(); right.addLayout(metric_wrap)
        self.metric_labels = {}
        for i, (title, desc, key) in enumerate([
            ("Uygulama Açılışı", "Ana ekranın hazır olma süresi.", "sts_opened"),
            ("Kayıt Süresi", "SQLite kayıt işlemi ortalaması.", "contract_saved"),
            ("Cevap Süresi", "Arayüz tepki süresi.", "platform_refresh"),
            ("Sorgu Süresi", "Filtre ve özet sorguları ortalaması.", "contract_detail_open"),
        ]):
            c = QFrame(); c.setObjectName("perfCard")
            l = QVBoxLayout(c)
            l.addWidget(QLabel(title, objectName="perfCardTitle"))
            v = QLabel("-")
            v.setStyleSheet("font-size:36px;font-weight:900;color:#102f58;")
            l.addWidget(v)
            l.addWidget(QLabel(desc, objectName="perfMuted"))
            self.metric_labels[key] = v
            metric_wrap.addWidget(c, 0, i)

        # Son Ölçümler
        list_card = QFrame(); list_card.setObjectName("perfCard")
        ll = QVBoxLayout(list_card)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Son Ölçümler", objectName="perfCardTitle"))
        title_row.addStretch(1)
        self.search = QLineEdit(); self.search.setPlaceholderText("İşlem ara..."); self.search.textChanged.connect(self.apply_filter)
        self.range = QComboBox(); self.range.addItems(["Son 20", "Son 50", "Bugün"]); self.range.currentIndexChanged.connect(self.apply_filter)
        title_row.addWidget(self.search); title_row.addWidget(self.range)
        ll.addLayout(title_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Saat", "İşlem", "Detay", "Süre"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().Stretch)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(3, 110)
        ll.addWidget(self.table)
        right.addWidget(list_card, 1)

    def refresh_all(self):
        self.stats = self.store.performance_stats()
        self.logs = self.store.recent_performance_logs(limit=100)

        self.v_size.setText(f"{self.stats.get('file_size_mb', 0):.1f} MB")
        self.v_total.setText(self._format_count(int(self.stats.get("total_records", 0))))
        self.v_contract.setText(self._format_count(int(self.stats.get("contract_count", 0))))
        self.v_system.setText(self._format_count(int(self.stats.get("system_count", 0))))
        self.v_delivery.setText(self._format_count(int(self.stats.get("delivery_count", 0))))
        counts = self.stats.get("table_counts", {})
        self.v_big.setText(max(counts.items(), key=lambda kv: kv[1])[0] if counts else "-")

        recent = self.stats.get("recent_metrics", {})
        for key, lbl in self.metric_labels.items():
            lbl.setText(self._format_duration(recent.get(key) or {}))
            lbl.setStyleSheet(f"font-size:36px;font-weight:900;color:{self._duration_color(recent.get(key) or {})};")

        self.apply_filter()

    def apply_filter(self):
        q = self.search.text().strip().lower()
        rows = self.logs
        if self.range.currentText() == "Son 20":
            rows = rows[:20]
        elif self.range.currentText() == "Son 50":
            rows = rows[:50]
        elif self.range.currentText() == "Bugün":
            today = time.strftime("%Y-%m-%d")
            rows = [r for r in rows if str(r.get("created_at", ""))[:10] == today]

        out = []
        for it in rows:
            action = str(it.get("action") or "")
            payload = {}
            raw = it.get("payload_json")
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {}
            txt = f"{action} {payload}"
            if q and q not in txt.lower():
                continue
            out.append((str(it.get("created_at") or ""), action, payload))

        self.table.setRowCount(len(out))
        for r, (created, action, payload) in enumerate(out):
            hhmmss = created.split(" ")[-1] if " " in created else created
            op = self._pretty_action(action, payload)
            detail = self._detail_text(payload)
            dur = self._format_duration(payload)
            self.table.setItem(r, 0, QTableWidgetItem(hhmmss))
            self.table.setItem(r, 1, QTableWidgetItem(op))
            self.table.setItem(r, 2, QTableWidgetItem(detail))
            d_it = QTableWidgetItem(dur)
            d_it.setForeground(Qt.darkGreen if self._is_good_duration(payload) else Qt.darkYellow)
            self.table.setItem(r, 3, d_it)

    @staticmethod
    def _format_count(v: int) -> str:
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return str(v)

    @staticmethod
    def _format_duration(payload) -> str:
        if not payload:
            return "-"
        if "duration_ms" in payload:
            ms = float(payload.get("duration_ms") or 0)
            if ms < 1000:
                return f"{ms:.0f} ms"
            return f"{ms / 1000:.1f} sn"
        if "elapsed_ms" in payload:
            ms = float(payload.get("elapsed_ms") or 0)
            if ms < 1000:
                return f"{ms:.0f} ms"
            return f"{ms / 1000:.1f} sn"
        if "duration_sec" in payload:
            sec = float(payload.get("duration_sec") or 0)
            if sec >= 144:
                return f"{sec / 60:.1f} dk"
            return f"{sec:.1f} sn"
        return "-"

    @staticmethod
    def _duration_ms(payload) -> float | None:
        if not payload:
            return None
        if "duration_ms" in payload:
            return float(payload.get("duration_ms") or 0)
        if "elapsed_ms" in payload:
            return float(payload.get("elapsed_ms") or 0)
        if "duration_sec" in payload:
            return float(payload.get("duration_sec") or 0) * 1000
        return None

    @classmethod
    def _duration_color(cls, payload) -> str:
        ms = cls._duration_ms(payload)
        if ms is None:
            return "#64748b"
        if ms < 100:
            return "#16a34a"
        if ms < 1000:
            return "#0f766e"
        return "#d97706"

    @classmethod
    def _is_good_duration(cls, payload) -> bool:
        ms = cls._duration_ms(payload)
        return ms is not None and ms < 1000

    @staticmethod
    def _pretty_action(action: str, payload: dict) -> str:
        mapping = {
            "sts_opened": "Uygulama açıldı",
            "platform_refresh": "Platform listesi yenilendi",
            "contract_detail_open": "Sözleşme detayı açıldı",
            "contract_saved": "Kayıt tamamlandı",
            "excel_exported": "Excel export tamamlandı",
            "database_optimize_completed": "Database optimize",
            "database_vacuum_completed": "Database vacuum",
            "performance_measurement": "Arama cevabı",
        }
        op = str(payload.get("operation") or payload.get("metric") or "").strip()
        if op == "query":
            return "Büyük tablo sorgusu"
        return mapping.get(action, action)

    @staticmethod
    def _detail_text(payload: dict) -> str:
        parts = []
        if payload.get("platform"):
            parts.append(str(payload.get("platform")))
        if payload.get("context"):
            parts.append(str(payload.get("context")))
        if payload.get("row_count"):
            parts.append(f"{payload.get('row_count')} satır")
        if payload.get("contract_count"):
            parts.append(f"{payload.get('contract_count')} sözleşme")
        if payload.get("table_counts"):
            parts.append("tablo sayımları")
        return " · ".join(parts) if parts else "-"
