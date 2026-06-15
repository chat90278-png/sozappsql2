"""Deprecated: platform/component management now lives in platform_component_manager.py."""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView

from src.ui.message_boxes import show_information, show_warning
from src.services.excel_store import ExcelStore
from src.ui.theme import STYLE


def safe_sheet_name(name: str) -> str:
    n = re.sub(r"[\\/*?:\[\]]", "_", name.strip().upper())
    return n[:31] or "PLATFORM"


def form_label(txt: str) -> QLabel:
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l


class PlatformDialog(QDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Platform Oluştur")
        self.setStyleSheet(STYLE)
        self.store = store
        self.logo_path = ""
        self.resize(520, 260)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Platform adı"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Örn: AKINCI, TB3")
        root.addWidget(self.name)
        root.addWidget(form_label("Logo (opsiyonel)"))
        logo_row = QHBoxLayout()
        self.logo_input = QLineEdit()
        self.logo_input.setReadOnly(True)
        self.logo_input.setPlaceholderText("Logo yüklemek için dosya seçin (.png, .jpg, .jpeg, .bmp, .webp)")
        logo_row.addWidget(self.logo_input, 1)
        pick = QPushButton("Logo Seç")
        pick.setObjectName("secondary")
        pick.clicked.connect(self.pick_logo)
        logo_row.addWidget(pick)
        root.addLayout(logo_row)
        note = QLabel("Platform oluşturulduktan sonra Bileşen Yönetimi ekranından bileşen atayın. Seçilen logo Excel içinde saklanır.")
        note.setObjectName("muted")
        root.addWidget(note)
        row = QHBoxLayout()
        row.addStretch()
        b = QPushButton("Oluştur")
        b.clicked.connect(self.save)
        row.addWidget(b)
        root.addLayout(row)

    def pick_logo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Platform logosu seç", str(self.store.path.parent), "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not p:
            return
        self.logo_path = str(p)
        self.logo_input.setText(self.logo_path)

    def save(self):
        n = safe_sheet_name(self.name.text())
        if not n:
            show_warning(self, "Eksik", "Platform adı girin.")
            return
        self.store.create_platform(n, logo_source=self.logo_path or None)
        self.accept()


class PlatformManagerDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, store: ExcelStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Platform Yönetimi")
        self.setStyleSheet(STYLE)
        self.store = store
        self.changed = False
        self.resize(680, 520)
        self.build()
        self.load_table()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)
        title = QLabel("Platform Yönetimi")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        desc = QLabel("Mevcut platformları buradan yönetin. Excel'de yeni bir sayfa açıldığında sistem onu platform olarak tanıyabilir. \"Platform Değil\" işaretleyerek bunu engelleyin.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        btns = QHBoxLayout()
        add_btn = QPushButton("+ Platform Ekle")
        add_btn.clicked.connect(self.add_platform)
        btns.addWidget(add_btn)
        btns.addStretch()
        root.addLayout(btns)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Platform Adı", "Durum", "Platform Değil"])
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 120)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 120)
        root.addWidget(self.table, 1)

        foot = QHBoxLayout()
        foot.addStretch()
        save_btn = QPushButton("Kaydet")
        save_btn.clicked.connect(self.save)
        close_btn = QPushButton("Kapat")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.reject)
        foot.addWidget(save_btn)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def load_table(self):
        all_sheets = self.store.all_sheet_names()
        excluded = set(self.store.load_excluded_platforms())
        self.table.setRowCount(len(all_sheets))
        for r, name in enumerate(all_sheets):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            status = "Platform Değil" if name in excluded else "Aktif Platform"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor("#DC2626") if name in excluded else QColor("#16A34A"))
            self.table.setItem(r, 1, status_item)
            cb_wrap = QWidget()
            cb_lay = QHBoxLayout(cb_wrap)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            cb_lay.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(name in excluded)
            cb.stateChanged.connect(lambda state, row=r: self._on_check_changed(row, state))
            cb_lay.addWidget(cb)
            self.table.setCellWidget(r, 2, cb_wrap)
            self.table.setRowHeight(r, 32)

    def _on_check_changed(self, row: int, state: int):
        status_item = self.table.item(row, 1)
        if not status_item:
            return
        excluded = bool(state)
        status_item.setText("Platform Değil" if excluded else "Aktif Platform")
        status_item.setForeground(QColor("#DC2626") if excluded else QColor("#16A34A"))

    def _get_checkbox(self, row: int) -> Optional[QCheckBox]:
        w = self.table.cellWidget(row, 2)
        if not w:
            return None
        return w.findChild(QCheckBox)

    def add_platform(self):
        dlg = PlatformDialog(self.store, self)
        if dlg.exec():
            self.changed = True
            self.store.reload_from_disk()
            self.load_table()
            self.settings_saved.emit()

    def save(self):
        excluded = []
        for r in range(self.table.rowCount()):
            cb = self._get_checkbox(r)
            name_item = self.table.item(r, 0)
            if cb and cb.isChecked() and name_item:
                excluded.append(name_item.text())
        self.store.save_excluded_platforms(excluded)
        self.store.reload_from_disk()
        self.changed = True
        self.settings_saved.emit()
        show_information(self, "Bilgi", "Platform ayarları kaydedildi")
