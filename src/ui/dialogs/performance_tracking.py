from __future__ import annotations
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.ui.theme import STYLE


class PerformanceTrackingDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.stats = {}
        self.logs = []
        self.setWindowTitle("Performans Takip")
        self.setMinimumSize(1100, 700)
        self.resize(1160, 720)
        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        self.refresh_all()

    def _local_style(self):
        return """
QFrame#perfHero { background:#10263f; border-radius:14px; }
QLabel#perfHeroTitle { color:#fff; font-size:25px; font-weight:900; }
QLabel#perfHeroDesc { color:#c8d8ea; font-size:12px; }
QLabel#perfBadge { background:#123c24; color:#b9f7ce; border:1px solid rgba(185,247,206,0.3); border-radius:12px; padding:8px 12px; font-weight:800; }
QFrame#perfCard { background:#fff; border:1px solid #d6e2f0; border-radius:14px; }
QLabel#perfCardTitle { color:#12345a; font-size:15px; font-weight:800; }
QLabel#perfMuted { color:#667995; font-size:12px; }
QPushButton#perfPrimary { background:#2563eb; color:white; border:none; border-radius:10px; padding:8px 14px; font-weight:800; }
QPushButton#perfSoft { background:#eef5ff; color:#1d4ed8; border:1px solid #cfe1fb; border-radius:10px; padding:7px 12px; font-weight:800; }
"""

    def _build(self):
        root = QVBoxLayout(self)
        hero = QFrame(); hero.setObjectName("perfHero")
        hl = QHBoxLayout(hero)
        tbox = QVBoxLayout()
        t = QLabel("Performans Takip"); t.setObjectName("perfHeroTitle")
        d = QLabel("STS veri dosyasının hız, veri boyutu ve temel işlem sürelerini izleyin."); d.setObjectName("perfHeroDesc")
        tbox.addWidget(t); tbox.addWidget(d)
        hl.addLayout(tbox, 1)
        self.btn_measure = QPushButton("Ölçüm Yap"); self.btn_measure.setObjectName("perfSoft"); self.btn_measure.clicked.connect(self.refresh_all)
        hl.addWidget(self.btn_measure)
        hl.addWidget(QLabel("• STS performansı izleniyor", objectName="perfBadge"))
        root.addWidget(hero)

        body = QHBoxLayout(); root.addLayout(body, 1)
        left = QVBoxLayout(); right = QVBoxLayout(); body.addLayout(left, 0); body.addLayout(right, 1)

        self.file_card = self._card(left, "Veri Dosyası")
        self.file_info = QLabel(""); self.file_info.setWordWrap(True); self.file_info.setObjectName("perfMuted")
        self.file_card.layout().addWidget(self.file_info)

        self.volume_card = self._card(left, "Veri Hacmi")
        vg = QGridLayout()
        self.v_total = QLabel(); self.v_contract = QLabel(); self.v_system = QLabel(); self.v_delivery = QLabel()
        for i,(k,w) in enumerate([("Toplam Kayıt",self.v_total),("Sözleşme",self.v_contract),("Sistem",self.v_system),("Kabul",self.v_delivery)]):
            f=QFrame(); f.setObjectName("perfCard"); l=QVBoxLayout(f); l.addWidget(QLabel(k, objectName="perfMuted")); l.addWidget(w)
            vg.addWidget(f, i//2, i%2)
        self.volume_card.layout().addLayout(vg)

        self.status_card = self._card(left, "Durum")
        self.status_labels = {}
        for key in ["Dosya açılışı", "Liste yenileme", "Detay açma", "Excel export"]:
            row = QHBoxLayout(); a = QLabel(key); b = QLabel("Ölçülmedi")
            row.addWidget(a); row.addStretch(1); row.addWidget(b)
            self.status_card.layout().addLayout(row); self.status_labels[key]=b

        metric_wrap = QGridLayout(); right.addLayout(metric_wrap)
        self.metric_labels = {}
        for i,(title,desc,key) in enumerate([
            ("Açılış Süresi","STS dosyasının arayüze yüklenme süresi.","sts_opened"),
            ("Platform Seçimi","Platform seçimi sonrası liste yenileme.","platform_refresh"),
            ("Detay Açma","Sözleşme detay verilerinin okunma süresi.","contract_detail_open"),
            ("Excel Export","Tam veri seti için Excel oluşturma süresi.","excel_exported"),
        ]):
            c=QFrame(); c.setObjectName("perfCard"); l=QVBoxLayout(c)
            l.addWidget(QLabel(title, objectName="perfCardTitle")); v=QLabel("-"); v.setStyleSheet("font-size:28px;font-weight:900;color:#102f58;")
            l.addWidget(v); l.addWidget(QLabel(desc, objectName="perfMuted")); self.metric_labels[key]=v
            metric_wrap.addWidget(c,0,i)

        mid = QHBoxLayout(); right.addLayout(mid,1)
        table_card = self._card_layout("Son Ölçülen İşlemler")
        mid.addWidget(table_card[0],1)
        table_l = table_card[1]
        tb = QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("İşlem ara");
        self.range=QComboBox(); self.range.addItems(["Son 50","Son 100","Bugün"]); fb=QPushButton("Filtrele"); fb.setObjectName("perfPrimary"); fb.clicked.connect(self.apply_filter)
        rb=QPushButton("Yenile"); rb.setObjectName("perfSoft"); rb.clicked.connect(self.refresh_all)
        tb.addWidget(self.search,1); tb.addWidget(self.range); tb.addWidget(fb); tb.addWidget(rb); table_l.addLayout(tb)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["İşlem","Süre","Veri","Durum","Zaman"]); self.table.horizontalHeader().setStretchLastSection(True)
        table_l.addWidget(self.table)

        summary = self._card(right, "Veri Özeti")
        self.summary = QLabel(""); self.summary.setWordWrap(True)
        summary.layout().addWidget(self.summary)

        tests = self._card(right, "Hızlı Performans Testleri")
        tr=QHBoxLayout(); tests.layout().addLayout(tr)
        for title,desc,fn in [
            ("Liste Yenileme","Aktif platform listesini ölçer.",self.measure_platform_refresh),
            ("Detay Açma","Örnek sözleşme detayını ölçer.",self.measure_detail_open),
            ("Database Kontrol","Sağlık kontrol süresini ölçer.",self.measure_db_check),
        ]:
            c=QFrame(); c.setObjectName("perfCard"); l=QVBoxLayout(c); l.addWidget(QLabel(title, objectName="perfCardTitle")); l.addWidget(QLabel(desc, objectName="perfMuted")); b=QPushButton("Ölç"); b.setObjectName("perfPrimary"); b.clicked.connect(fn); l.addWidget(b,0,Qt.AlignRight); tr.addWidget(c)

    def _card(self, parent_layout, title):
        f=QFrame(); f.setObjectName("perfCard"); l=QVBoxLayout(f); l.addWidget(QLabel(title, objectName="perfCardTitle")); parent_layout.addWidget(f); return f

    def _card_layout(self, title):
        f=QFrame(); f.setObjectName("perfCard"); l=QVBoxLayout(f); l.addWidget(QLabel(title, objectName="perfCardTitle")); return f,l

    def refresh_all(self):
        self.stats = self.store.performance_stats()
        self.logs = self.store.recent_performance_logs(limit=100)
        p = Path(str(self.stats.get("path") or ""))
        self.file_info.setText(f"{p.name}\n{p}\nBoyut: {self.stats.get('file_size_mb',0):.1f} MB")
        self.file_info.setToolTip(str(p))
        self.v_total.setText(self._format_count(int(self.stats.get("total_records",0))))
        self.v_contract.setText(self._format_count(int(self.stats.get("contract_count",0))))
        self.v_system.setText(self._format_count(int(self.stats.get("system_count",0))))
        self.v_delivery.setText(self._format_count(int(self.stats.get("delivery_count",0))))

        recent = self.stats.get("recent_metrics",{})
        for key, lbl in self.metric_labels.items():
            payload = recent.get(key) or recent.get("excel_exported" if key=="excel_exported" else "") or {}
            lbl.setText(self._format_duration(payload))

        self.status_labels["Dosya açılışı"].setText(self._status_from_metric(recent.get("sts_opened")))
        self.status_labels["Liste yenileme"].setText(self._status_from_metric(recent.get("platform_refresh")))
        self.status_labels["Detay açma"].setText(self._status_from_metric(recent.get("contract_detail_open")))
        self.status_labels["Excel export"].setText(self._status_from_metric(recent.get("excel_exported"), export=True))

        self.apply_filter()
        counts=self.stats.get("table_counts",{})
        biggest = max(counts.items(), key=lambda kv: kv[1])[0] if counts else "-"
        last_maint = "-"
        for it in self.logs:
            if it.get("action") in {"database_optimize_completed", "database_vacuum_completed"}:
                last_maint = str(it.get("created_at") or "-")
                break
        self.summary.setText(
            f"En büyük tablo: {biggest}\n"
            f"Tablo sayısı: {len(counts)}\n"
            f"Platform: {self.stats.get('platform_count',0)}\n"
            f"Bileşen: {self.stats.get('component_count',0)}\n"
            f"Son bakım: {last_maint}"
        )

    def apply_filter(self):
        q=self.search.text().strip().lower()
        rows=self.logs
        if self.range.currentText()=="Son 50": rows=rows[:50]
        elif self.range.currentText()=="Bugün":
            today=time.strftime("%Y-%m-%d")
            rows=[r for r in rows if str(r.get("created_at",""))[:10]==today]
        out=[]
        for it in rows:
            action=str(it.get("action") or "")
            payload={}
            raw=it.get("payload_json")
            if raw:
                try: payload=json.loads(raw)
                except Exception: payload={}
            txt=f"{action} {payload}"
            if q and q not in txt.lower():
                continue
            out.append((action,payload,str(it.get("created_at") or "")))
        self.table.setRowCount(len(out))
        for r,(action,payload,created) in enumerate(out):
            self.table.setItem(r,0,QTableWidgetItem(action))
            self.table.setItem(r,1,QTableWidgetItem(self._format_duration(payload)))
            data = payload.get("platform") or payload.get("contract_count") or payload.get("table_counts") or "-"
            self.table.setItem(r,2,QTableWidgetItem(str(data)))
            self.table.setItem(r,3,QTableWidgetItem(self._status_from_metric(payload)))
            self.table.setItem(r,4,QTableWidgetItem(created))

    def measure_platform_refresh(self):
        t=time.perf_counter(); idx=self.store.build_contract_index(); ms=(time.perf_counter()-t)*1000
        self.store.add_performance_log("platform_refresh", duration_ms=ms, payload={"contract_count": len(idx)})
        self.refresh_all()

    def measure_detail_open(self):
        idx=self.store.build_contract_index()
        if not idx: return
        it=idx[0]
        t=time.perf_counter(); self.store.load_contract_structure(it.get("platform"), it.get("contract_no"), it.get("contract_type")); ms=(time.perf_counter()-t)*1000
        self.store.add_performance_log("contract_detail_open", duration_ms=ms, payload={"platform": it.get("platform"), "contract_count": len(idx)})
        self.refresh_all()

    def measure_db_check(self):
        t=time.perf_counter(); self.store.integrity_check(); ms=(time.perf_counter()-t)*1000
        self.store.add_performance_log("database_check", duration_ms=ms)
        self.refresh_all()

    @staticmethod
    def _format_count(v:int)->str:
        if v>=1_000_000: return f"{v/1_000_000:.2f}M"
        if v>=1_000: return f"{v/1_000:.0f}K"
        return str(v)

    @staticmethod
    def _format_duration(payload)->str:
        if not payload: return "-"
        if "duration_ms" in payload:
            ms=float(payload.get("duration_ms") or 0)
            if ms<1000: return f"{ms:.0f} ms"
            return f"{ms/1000:.1f} sn"
        if "elapsed_ms" in payload:
            ms=float(payload.get("elapsed_ms") or 0)
            if ms<1000: return f"{ms:.0f} ms"
            return f"{ms/1000:.1f} sn"
        if "duration_sec" in payload:
            sec=float(payload.get("duration_sec") or 0)
            if sec>=144: return f"{sec/60:.1f} dk"
            return f"{sec:.1f} sn"
        return "-"

    @staticmethod
    def _status_from_metric(payload, export=False)->str:
        if not payload: return "Ölçülmedi"
        ms=None
        if "duration_ms" in payload: ms=float(payload.get("duration_ms") or 0)
        elif "elapsed_ms" in payload: ms=float(payload.get("elapsed_ms") or 0)
        elif "duration_sec" in payload: ms=float(payload.get("duration_sec") or 0)*1000
        if ms is None: return "Ölçülmedi"
        if export:
            if ms < 5000: return "Çok iyi"
            if ms < 30000: return "İyi"
            return "Ağır"
        if ms < 100: return "Çok iyi"
        if ms < 1000: return "İyi"
        return "Ağır"
