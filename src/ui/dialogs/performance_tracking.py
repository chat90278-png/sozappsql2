from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from src.services import perf_tracker
from src.ui.theme import STYLE


STATUS = {
    "ok": ("Normal", "#15803d", "#ecfdf3", "#bbf7d0"),
    "warning": ("Dikkat", "#b45309", "#fff7ed", "#fed7aa"),
    "critical": ("Kritik", "#b91c1c", "#fef2f2", "#fecaca"),
    "failed": ("Başarısız", "#b91c1c", "#fef2f2", "#fecaca"),
    "insufficient": ("Yetersiz veri", "#64748b", "#f1f5f9", "#cbd5e1"),
    "unknown": ("Belirsiz", "#64748b", "#f1f5f9", "#cbd5e1"),
}

PRIMARY_METRICS = (
    perf_tracker.OP_DB_OPEN,
    perf_tracker.OP_CONTRACT_LIST_LOAD,
    perf_tracker.OP_CONTRACT_OPEN,
    perf_tracker.OP_CONTRACT_SAVE,
)

TABLE_LABELS = {
    "contracts": "Sözleşme",
    "systems": "Sistem",
    "deliveries": "Teslimat",
    "components": "Bileşen",
    "activity_logs": "İşlem geçmişi",
}


class MetricCard(QFrame):
    def __init__(self, operation: str, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.setObjectName("perfMetricCard")
        info = perf_tracker.operation_info(operation)

        root = QVBoxLayout(self)
        root.setContentsMargins(13, 11, 13, 11)
        root.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(str(info["label"]))
        title.setObjectName("perfCardTitle")
        self.badge = QLabel("Ölçüm yok")
        self.badge.setAlignment(Qt.AlignCenter)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.badge)
        root.addLayout(top)

        self.value = QLabel("-")
        self.value.setObjectName("perfMetricValue")
        root.addWidget(self.value)

        hint = QLabel("p95 · yavaş uç kullanıcı deneyimi")
        hint.setObjectName("perfMuted")
        root.addWidget(hint)

        self.detail = QLabel("Son - · Ortalama -")
        self.detail.setObjectName("perfMuted")
        root.addWidget(self.detail)

        self.samples = QLabel("Bu dönem için ölçüm yok")
        self.samples.setObjectName("perfMuted")
        root.addWidget(self.samples)
        self.update_value(None)

    def update_value(self, stat: dict | None) -> None:
        if not stat:
            self.value.setText("-")
            self.detail.setText("Son - · Ortalama -")
            self.samples.setText("Bu dönem için ölçüm yok")
            self._set_badge("unknown", "Ölçüm yok")
            return

        self.value.setText(format_duration(stat.get("p95_ms")))
        self.detail.setText(
            f"Son {format_duration(stat.get('last_ms'))} · "
            f"Ortalama {format_duration(stat.get('avg_ms'))}"
        )
        self.samples.setText(
            f"{int(stat.get('count') or 0)} ölçüm · "
            f"{int(stat.get('failures') or 0)} başarısız"
        )
        state = str(stat.get("status") or "unknown")
        self._set_badge(state, STATUS.get(state, STATUS["unknown"])[0])

    def _set_badge(self, state: str, text: str) -> None:
        _label, foreground, background, border = STATUS.get(state, STATUS["unknown"])
        self.badge.setText(text)
        self.badge.setStyleSheet(
            f"color:{foreground};background:{background};border:1px solid {border};"
            "border-radius:8px;padding:2px 7px;font-size:10px;font-weight:800;"
        )


class PerformanceTrackingDialog(QDialog):
    DIALOG_ID = "performanceTrackingDialog"

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.report: dict = {}
        self.db_stats: dict = {}
        self.setObjectName(self.DIALOG_ID)
        self.setWindowTitle("Performans İzleme - STS")
        self.setMinimumSize(1050, 650)
        self.resize(1240, 760)
        self.setStyleSheet(STYLE + self._style())
        self._build()
        self.refresh_all()

    @staticmethod
    def _style() -> str:
        return """
QDialog#performanceTrackingDialog { background:#eef3f9; }
QFrame#perfHero { background:#10263f; border-radius:15px; }
QLabel#perfHeroTitle { color:#fff; font-size:25px; font-weight:900; }
QLabel#perfHeroText { color:#c8d8ea; font-size:12px; }
QLabel#perfHeroMeta { color:#dce8f5; font-size:11px; }
QFrame#perfPanel, QFrame#perfMetricCard {
    background:#fff; border:1px solid #d6e2f0; border-radius:13px;
}
QLabel#perfCardTitle, QLabel#perfSectionTitle {
    color:#12345a; font-size:14px; font-weight:900;
}
QLabel#perfMetricValue { color:#102f58; font-size:29px; font-weight:900; }
QLabel#perfMuted { color:#667995; font-size:11px; }
QLabel#perfSummaryValue { color:#102f58; font-size:18px; font-weight:900; }
QLabel#perfEmpty {
    color:#64748b;background:#f8fafc;border:1px dashed #cbd5e1;
    border-radius:9px;padding:12px;
}
QDialog#performanceTrackingDialog QLineEdit,
QDialog#performanceTrackingDialog QComboBox {
    background:#fff;border:1px solid #cfdceb;border-radius:8px;
    padding:6px 8px;min-height:20px;
}
QPushButton#perfRefresh {
    background:#fff;color:#12345a;border:none;border-radius:9px;
    padding:8px 14px;font-weight:800;
}
QPushButton#perfRefresh:hover { background:#eaf2fb; }
QDialog#performanceTrackingDialog QTableWidget {
    background:#fff;alternate-background-color:#f8fbff;
    border:1px solid #d6e2f0;border-radius:10px;
    gridline-color:#e6edf6;selection-background-color:#dbeafe;
    selection-color:#10263f;
}
QDialog#performanceTrackingDialog QHeaderView::section {
    background:#edf3ff;border:none;border-right:1px solid #dfe8f3;
    padding:8px;color:#264463;font-weight:800;
}
"""

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)
        root.addWidget(self._hero())
        root.addWidget(self._filters())

        cards = QGridLayout()
        cards.setHorizontalSpacing(8)
        self.metric_cards = {}
        for index, operation in enumerate(PRIMARY_METRICS):
            card = MetricCard(operation, self)
            self.metric_cards[operation] = card
            cards.addWidget(card, 0, index)
            cards.setColumnStretch(index, 1)
        root.addLayout(cards)

        root.addWidget(self._summary_panel())
        root.addWidget(self._measurement_panel(), 1)

    def _hero(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("perfHero")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 14, 12)

        text = QVBoxLayout()
        title = QLabel("Performans İzleme")
        title.setObjectName("perfHeroTitle")
        description = QLabel(
            "Gerçek STS işlemlerini p95, son değer, ortalama, örnek sayısı ve hata oranıyla izleyin."
        )
        description.setObjectName("perfHeroText")
        self.hero_meta = QLabel("Veriler hazırlanıyor...")
        self.hero_meta.setObjectName("perfHeroMeta")
        text.addWidget(title)
        text.addWidget(description)
        text.addWidget(self.hero_meta)
        layout.addLayout(text, 1)

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setObjectName("perfRefresh")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_all)
        layout.addWidget(self.refresh_button, 0, Qt.AlignTop)
        return frame

    def _filters(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("perfPanel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(7)

        layout.addWidget(muted_label("Dönem"))
        self.range_combo = QComboBox()
        for label, key in (
            ("Bugün", "today"), ("Son 24 saat", "24h"), ("Son 7 gün", "7d"),
            ("Son 30 gün", "30d"), ("Tümü", "all"),
        ):
            self.range_combo.addItem(label, key)
        self.range_combo.setCurrentIndex(2)
        self.range_combo.currentIndexChanged.connect(self.refresh_all)
        layout.addWidget(self.range_combo)

        layout.addWidget(muted_label("İşlem"))
        self.operation_combo = QComboBox()
        self.operation_combo.addItem("Tüm işlemler", "")
        for operation, info in perf_tracker.OPERATION_CATALOG.items():
            self.operation_combo.addItem(str(info["label"]), operation)
        self.operation_combo.currentIndexChanged.connect(self.apply_filter)
        layout.addWidget(self.operation_combo)

        layout.addWidget(muted_label("Durum"))
        self.status_combo = QComboBox()
        for label, key in (
            ("Tüm durumlar", ""), ("Normal", "ok"), ("Dikkat", "warning"),
            ("Kritik", "critical"), ("Başarısız", "failed"),
        ):
            self.status_combo.addItem(label, key)
        self.status_combo.currentIndexChanged.connect(self.apply_filter)
        layout.addWidget(self.status_combo)

        layout.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("İşlem, sözleşme veya platform ara...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self.apply_filter)
        layout.addWidget(self.search)
        return frame

    def _summary_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("perfPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(6)
        layout.addWidget(section_label("Veri, Disk ve Ölçüm Sağlığı"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.summary_values = {}
        definitions = (
            ("contracts", "Sözleşme"), ("systems", "Sistem"),
            ("deliveries", "Teslimat"), ("components", "Bileşen"),
            ("main_size", "Ana STS"), ("wal_size", "WAL"),
            ("total_size", "Toplam disk"), ("largest", "En fazla satır"),
            ("measurements", "Ölçüm"), ("failure_rate", "Başarısızlık"),
            ("attention", "Dikkat gereken"), ("slowest", "En zorlanan"),
        )
        for index, (key, title) in enumerate(definitions):
            box = QVBoxLayout()
            box.setSpacing(1)
            box.addWidget(muted_label(title))
            value = QLabel("-")
            value.setObjectName("perfSummaryValue")
            value.setWordWrap(True)
            self.summary_values[key] = value
            box.addWidget(value)
            grid.addLayout(box, index // 6, index % 6)
            grid.setColumnStretch(index % 6, 1)
        layout.addLayout(grid)
        return frame

    def _measurement_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("perfPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(section_label("Ölçüm Geçmişi"))
        header.addStretch(1)
        self.result_count = muted_label("0 kayıt")
        header.addWidget(self.result_count)
        layout.addLayout(header)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("perfEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Tarih / Saat", "İşlem", "Durum", "Süre", "Detay", "Kaynak"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 165)
        self.table.setColumnWidth(1, 185)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(5, 140)
        layout.addWidget(self.table, 1)
        return frame

    def refresh_all(self) -> None:
        self.refresh_button.setEnabled(False)
        try:
            data_path = Path(getattr(self.store, "path", ""))
            self.report = perf_tracker.build_report(
                data_path,
                range_key=str(self.range_combo.currentData() or "7d"),
                last_n=10000,
            )
            try:
                self.db_stats = (
                    dict(self.store.database_stats())
                    if hasattr(self.store, "database_stats") else {}
                )
            except Exception as exc:
                self.db_stats = {"error": str(exc)}
            self._update_cards()
            self._update_summary()
            self._update_hero(data_path)
            self.apply_filter()
        except Exception as exc:
            self.report = {}
            self.db_stats = {}
            self._show_empty(f"Performans verileri okunamadı. Teknik ayrıntı: {exc}")
        finally:
            self.refresh_button.setEnabled(True)

    def _update_cards(self) -> None:
        stats = dict(self.report.get("stats") or {})
        for operation, card in self.metric_cards.items():
            card.update_value(stats.get(operation))

    def _update_summary(self) -> None:
        counts = dict(self.db_stats.get("table_counts") or {})
        for key in ("contracts", "systems", "deliveries", "components"):
            self.summary_values[key].setText(format_count(counts.get(key, 0)))

        disk = dict(self.report.get("disk_usage") or {})
        self.summary_values["main_size"].setText(format_bytes(disk.get("main_bytes")))
        self.summary_values["wal_size"].setText(format_bytes(disk.get("wal_bytes")))
        self.summary_values["total_size"].setText(format_bytes(disk.get("total_bytes")))

        if counts:
            name, count = max(counts.items(), key=lambda item: int(item[1] or 0))
            self.summary_values["largest"].setText(
                f"{TABLE_LABELS.get(str(name), str(name))} · {format_count(count)}"
            )
        else:
            self.summary_values["largest"].setText("-")

        summary = dict(self.report.get("summary") or {})
        stats = dict(self.report.get("stats") or {})
        self.summary_values["measurements"].setText(
            format_count(summary.get("measurement_count"))
        )
        self.summary_values["failure_rate"].setText(
            f"%{float(summary.get('failure_rate') or 0):.1f}"
        )
        attention = sum(
            str(item.get("status")) in {"warning", "critical"}
            for item in stats.values()
        )
        self.summary_values["attention"].setText(str(attention))
        slowest = str(summary.get("slowest_operation") or "")
        self.summary_values["slowest"].setText(
            str(perf_tracker.operation_info(slowest)["label"]) if slowest else "-"
        )

    def _update_hero(self, data_path: Path) -> None:
        status = dict(self.report.get("log_status") or {})
        if status.get("read_error"):
            text = "ölçüm dosyası okunamadı"
        elif not self.report.get("records"):
            text = "bu dönem için ölçüm yok"
        else:
            text = "ölçüm kaynağı hazır"
        self.hero_meta.setText(
            f"{data_path.name or '-'} · {text} · "
            f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        self.hero_meta.setToolTip(str(status.get("log_path") or ""))

    def apply_filter(self) -> None:
        records = list(self.report.get("records") or [])
        operation_filter = str(self.operation_combo.currentData() or "")
        status_filter = str(self.status_combo.currentData() or "")
        query = self.search.text().strip().casefold()
        rows = []

        for item in records:
            operation = str(item.get("op") or "unknown")
            if operation_filter and operation != operation_filter:
                continue
            state = (
                "failed" if not bool(item.get("success", True))
                else perf_tracker.classify_duration(operation, item.get("duration_ms"))
            )
            if status_filter and state != status_filter:
                continue
            detail = detail_text(item)
            searchable = " ".join(
                (
                    operation,
                    str(perf_tracker.operation_info(operation)["label"]),
                    detail,
                    str(item.get("source_file") or ""),
                    str(item.get("thread") or ""),
                )
            ).casefold()
            if query and query not in searchable:
                continue
            rows.append((item, operation, state, detail))

        self.table.setRowCount(len(rows))
        for row_index, (item, operation, state, detail) in enumerate(rows):
            label, foreground, _background, _border = STATUS.get(state, STATUS["unknown"])
            values = (
                display_timestamp(item.get("ts")),
                str(perf_tracker.operation_info(operation)["label"]),
                label,
                format_duration(item.get("duration_ms")),
                detail,
                source_text(item),
            )
            tooltip = safe_json(item)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(tooltip)
                if column in {2, 3}:
                    cell.setForeground(QColor(foreground))
                if column == 3:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_index, column, cell)

        self.result_count.setText(f"{format_count(len(rows))} kayıt")
        if rows:
            self.empty_label.hide()
            self.table.show()
            return

        log_status = dict(self.report.get("log_status") or {})
        if log_status.get("read_error"):
            message = f"Ölçüm dosyası okunamadı: {log_status.get('read_error')}"
        elif not records:
            message = (
                "Seçilen dönemde bu STS dosyasına ait performans ölçümü yok. "
                "Sözleşme açma, kaydetme veya liste yenileme işlemlerinden sonra "
                "ölçümler burada görünecektir."
            )
        else:
            message = "Seçili arama ve filtrelerle eşleşen ölçüm bulunamadı."
        self._show_empty(message)

    def _show_empty(self, message: str) -> None:
        self.table.setRowCount(0)
        self.table.hide()
        self.empty_label.setText(message)
        self.empty_label.show()
        self.result_count.setText("0 kayıt")


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("perfMuted")
    return label


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("perfSectionTitle")
    return label


def format_duration(value: Any) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "-"
    if milliseconds < 1000:
        return f"{milliseconds:.0f} ms"
    seconds = milliseconds / 1000
    if seconds < 60:
        return f"{seconds:.1f} sn"
    minutes = int(seconds // 60)
    remaining = int(round(seconds % 60))
    if minutes < 60:
        return f"{minutes} dk {remaining} sn"
    return f"{minutes // 60} sa {minutes % 60} dk"


def format_count(value: Any) -> str:
    try:
        return f"{int(value or 0):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def format_bytes(value: Any) -> str:
    try:
        size = max(0, int(value or 0))
    except (TypeError, ValueError):
        size = 0
    if size < 1024:
        return f"{size} B"
    if size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    if size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024 ** 3:.2f} GB"


def display_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%d.%m.%Y %H:%M:%S")
    except ValueError:
        return text.replace("T", " ") or "-"


def detail_text(item: dict) -> str:
    parts = []
    if item.get("platform"):
        parts.append(str(item["platform"]))
    if item.get("contract_no"):
        parts.append(f"Sözleşme {item['contract_no']}")
    if item.get("row_count") is not None:
        parts.append(f"{format_count(item['row_count'])} satır")
    if item.get("affected_rows") is not None:
        parts.append(f"{format_count(item['affected_rows'])} etkilenen")
    if item.get("database_existed"):
        parts.append("Mevcut STS")
    if item.get("error"):
        parts.append(f"Hata: {item['error']}")
    return " · ".join(parts) if parts else "-"


def source_text(item: dict) -> str:
    if item.get("source"):
        return str(item["source"])
    thread = str(item.get("thread") or "")
    return thread if thread and thread != "MainThread" else "Ana uygulama"


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)
