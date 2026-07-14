from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import ActivityHistoryQuery
from src.services.sts_database import format_log_timestamp
from src.ui.theme import STYLE


class ActivityLogDialog(QDialog):
    """Existing Activity History dialog backed by the Phase 3 safe read model."""

    def __init__(self, store, parent=None, *, access: ActivityHistoryAccess | None = None):
        if access is None or not access.can_view:
            raise PermissionError("İşlem geçmişi erişimi reddedildi.")
        super().__init__(parent)
        self.store = store
        self.access = access
        self.items = []
        self.setWindowTitle("İşlem Geçmişi")
        self.resize(1200, 680)
        self.setStyleSheet(STYLE)
        self.build()
        self.refresh_logs()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("İşlem Geçmişi")
        title.setObjectName("mainTitle")
        root.addWidget(title)
        root.addWidget(QLabel("STS veri dosyasında kayıtlı değişiklik geçmişini görüntüleyin."))

        filt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara...")
        self.search.returnPressed.connect(self.refresh_logs)
        self.category = QComboBox()
        self.category.addItem("Tümü", "")
        self.category.addItem("Kullanıcı İşlemleri", "USER")
        self.category.addItem("Yönetim İşlemleri", "MANAGEMENT")
        if self.access.can_view_technical:
            self.category.addItem("Teknik Kayıtlar", "TECHNICAL")
        self.action = QComboBox()
        self.action.addItem("Tümü", "")
        self.limit = QComboBox()
        for text, value in [("50", 50), ("100", 100), ("200", 200)]:
            self.limit.addItem(text, value)
        self.limit.setCurrentIndex(1)
        btn = QPushButton("Yenile")
        btn.clicked.connect(self.refresh_logs)
        for widget in (self.search, self.category, self.action, self.limit, btn):
            filt.addWidget(widget)
        root.addLayout(filt)

        headers = [
            "Tarih",
            "Kategori",
            "İşlem Yapan",
            "İşlem",
            "Durum",
            "Kayıt Türü",
            "Platform",
            "Sözleşme No",
            "Özet",
            "Değişen Alanlar",
        ]
        if self.access.can_view_technical:
            headers.extend(["Kaynak", "Bilgisayar", "Oturum", "İşlem Kimliği"])
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.open_detail)
        root.addWidget(self.table)

    def refresh_logs(self):
        category = self.category.currentData() or ""
        action = self.action.currentData() or ""
        page = self.store.query_activity_history(
            ActivityHistoryQuery(
                categories=(category,) if category else (),
                actions=(action,) if action else (),
                search_text=self.search.text().strip(),
                limit=int(self.limit.currentData() or 100),
            ),
            access=self.access,
            include_technical=self.access.can_view_technical,
        )
        self.items = list(page.items)
        actions = sorted({item.action for item in self.items if item.action})
        current = self.action.currentData() or ""
        self.action.blockSignals(True)
        self.action.clear()
        self.action.addItem("Tümü", "")
        for action_name in actions:
            self.action.addItem(action_name, action_name)
        index = self.action.findData(current)
        self.action.setCurrentIndex(index if index >= 0 else 0)
        self.action.blockSignals(False)

        self.table.setRowCount(len(self.items))
        for row_index, item in enumerate(self.items):
            changes = ", ".join(change.field for change in item.changed_fields) or "-"
            values = [
                format_log_timestamp(item.occurred_at),
                item.category,
                item.actor_display_name,
                item.action_label,
                item.status,
                item.entity_label or item.entity_type or "-",
                item.platform_name or "-",
                item.contract_no or "-",
                item.summary,
                changes,
            ]
            if self.access.can_view_technical:
                technical = item.technical
                values.extend(
                    [
                        technical.source if technical else "-",
                        technical.device_name if technical else "-",
                        technical.session_id if technical else "-",
                        technical.operation_id if technical else "-",
                    ]
                )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value or "-")))

    @staticmethod
    def _pretty(value):
        if value in (None, "", "null"):
            return ""
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            return str(value)

    def open_detail(self, row, _column):
        if row < 0 or row >= len(self.items):
            return
        item = self.items[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("İşlem Detayı")
        dialog.resize(900, 650)
        dialog.setStyleSheet(STYLE)
        layout = QVBoxLayout(dialog)
        for label, value in (
            ("Tarih", item.occurred_at),
            ("Kategori", item.category),
            ("İşlem Yapan", item.actor_display_name),
            ("İşlem", item.action_label),
            ("Durum", item.status),
            ("Özet", item.summary),
        ):
            layout.addWidget(QLabel(f"{label}: {value or '-'}"))
        layout.addWidget(QLabel("Değişen Alanlar"))
        changed = QPlainTextEdit()
        changed.setReadOnly(True)
        changed.setPlainText(
            self._pretty(
                [
                    {"field": change.field, "before": change.before, "after": change.after}
                    for change in item.changed_fields
                ]
            )
        )
        layout.addWidget(changed)
        if self.access.can_view_technical and item.technical is not None:
            layout.addWidget(QLabel("Teknik Ayrıntılar"))
            technical = QPlainTextEdit()
            technical.setReadOnly(True)
            technical.setPlainText(self._pretty(item.technical.__dict__))
            layout.addWidget(technical)
        dialog.exec()
