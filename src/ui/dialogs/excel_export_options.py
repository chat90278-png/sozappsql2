from __future__ import annotations
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.message_boxes import show_warning
from src.ui.theme import STYLE


class PlatformRow(QFrame):
    def __init__(self, platform_name: str, contract_count: int, on_changed):
        super().__init__()
        self.platform_name = platform_name
        self._on_changed = on_changed
        self.setObjectName("platformRow")
        self.setStyleSheet("""
QFrame#platformRow { border:1px solid #dbe5f1; border-radius:8px; background:#ffffff; }
QFrame#platformRow:hover { border:1px solid #93c5fd; background:#f8fbff; }
QFrame#platformRow[checked='true'] { border:1px solid #2563eb; background:#f0f6ff; }
QLabel#platformName { color:#0f172a; font-weight:750; }
QLabel#platformBadge { color:#35506d; background:#eef5ff; border-radius:8px; padding:2px 7px; font-weight:700; }
""")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
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

    def _emit_changed(self):
        self.setProperty("checked", self.checkbox.isChecked())
        self.style().unpolish(self); self.style().polish(self)
        self._on_changed()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.childAt(event.position().toPoint()) is not self.checkbox:
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


class ExcelExportDialog(QDialog):
    DIALOG_ID = "excelExportDialog"

    def __init__(self, store, parent=None, active_platform=None, contract_index=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName(self.DIALOG_ID)
        self.active_platform = str(active_platform or "").strip()
        self.contract_index = list(contract_index or [])
        self.result_options = None
        self.platform_rows = []

        self._platform_counts = Counter()
        for it in self.contract_index:
            p = str((it or {}).get("platform") or "").strip()
            if p:
                self._platform_counts[p] += 1

        self.setWindowTitle("Excel’e Aktar - STS")
        self.resize(480, 420)
        self.setMinimumSize(440, 360)
        self.setStyleSheet(STYLE + self._local_style())
        self.build()

    def _local_style(self):
        return """
QLabel#exportTitle { color:#12345a; font-size:18px; font-weight:900; background:transparent; }
QFrame#exportCard { background:#ffffff; border:1px solid #dbe5f1; border-radius:12px; }
QLabel#exportCardHeader { color:#12345a; font-size:14px; font-weight:850; }
QPushButton#exportPrimaryButton { background:#2563eb; color:white; border:none; border-radius:10px; padding:10px 14px; font-weight:900; min-width:130px; }
QPushButton#exportSecondaryButton { background:#ffffff; color:#244767; border:1px solid #d6e2f0; border-radius:10px; padding:10px 14px; font-weight:800; min-width:90px; }
QPushButton#exportTinyButton { background:#ffffff; color:#244767; border:1px solid #d6e2f0; border-radius:8px; padding:5px 9px; font-weight:800; }
QScrollArea#platformScroll { border:1px solid #dbe5f1; border-radius:10px; background:#ffffff; }
QScrollArea#platformScroll QScrollBar:vertical { width:10px; background:#f5f8fc; margin:8px 2px; border-radius:5px; }
QScrollArea#platformScroll QScrollBar::handle:vertical { background:#b4c6de; border-radius:5px; min-height:28px; }
QScrollArea#platformScroll QScrollBar::add-line:vertical, QScrollArea#platformScroll QScrollBar::sub-line:vertical { height:0; }
QDialog#excelExportDialog QLabel, QDialog#excelExportDialog QCheckBox { background: transparent; }
"""

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("Excel’e aktarılacak platformları seçin")
        title.setObjectName("exportTitle")
        root.addWidget(title)

        platform_card = QFrame(); platform_card.setObjectName("exportCard")
        pl = QVBoxLayout(platform_card)
        pl.setContentsMargins(10, 10, 10, 10)
        ph = QHBoxLayout()
        ph.addWidget(QLabel("Platformlar", objectName="exportCardHeader")); ph.addStretch(1)
        select_all_btn = QPushButton("Tümünü Seç")
        select_all_btn.setObjectName("exportTinyButton")
        select_all_btn.clicked.connect(self.select_all_platforms)
        clear_btn = QPushButton("Seçimi Temizle")
        clear_btn.setObjectName("exportTinyButton")
        clear_btn.clicked.connect(self.clear_platform_selection)
        ph.addWidget(select_all_btn)
        ph.addWidget(clear_btn)
        pl.addLayout(ph)

        self.platform_container = QWidget()
        self.platform_layout = QVBoxLayout(self.platform_container)
        self.platform_layout.setContentsMargins(8, 8, 8, 8)
        self.platform_layout.setSpacing(6)
        platform_names = [str(p) for p in (self.store.platform_names() if hasattr(self.store, "platform_names") else [])]
        use_active_platform = bool(self.active_platform and self.active_platform in platform_names)
        for p in platform_names:
            c = self._platform_counts.get(str(p), 0)
            row = PlatformRow(str(p), c, self._on_platform_item_changed)
            row.set_checked((str(p) == self.active_platform) if use_active_platform else True, silent=True)
            self.platform_rows.append(row)
            self.platform_layout.addWidget(row)
        self.platform_layout.addStretch(1)

        self.platform_scroll = QScrollArea()
        self.platform_scroll.setObjectName("platformScroll")
        self.platform_scroll.setWidgetResizable(True)
        self.platform_scroll.setFrameShape(QFrame.NoFrame)
        self.platform_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.platform_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.platform_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.platform_scroll.setWidget(self.platform_container)
        pl.addWidget(self.platform_scroll, 1)
        root.addWidget(platform_card, 1)

        foot = QHBoxLayout(); root.addLayout(foot)
        foot.addStretch(1)
        cbtn = QPushButton("İptal"); cbtn.setObjectName("exportSecondaryButton"); cbtn.clicked.connect(self.reject)
        obtn = QPushButton("Excel Oluştur"); obtn.setObjectName("exportPrimaryButton"); obtn.clicked.connect(self.accept_options)
        foot.addWidget(cbtn); foot.addWidget(obtn)

    def _selected_platforms(self):
        return [r.platform_name for r in self.platform_rows if r.is_checked()]

    def _on_platform_item_changed(self):
        return

    def select_all_platforms(self):
        for row in self.platform_rows:
            row.set_checked(True, silent=True)

    def clear_platform_selection(self):
        for row in self.platform_rows:
            row.set_checked(False, silent=True)

    def accept_options(self):
        plats = self._selected_platforms()
        if not plats:
            show_warning(self, "Excel’e Aktar", "En az bir platform seçmelisiniz.")
            return

        self.result_options = {
            "scope": "selected",
            "platforms": plats,
            "include_summary": True,
            "include_contract_rows": True,
            "include_system_rows": True,
            "include_delivery_rows": True,
            "include_component_columns": True,
            "include_tags": True,
        }
        self.accept()
