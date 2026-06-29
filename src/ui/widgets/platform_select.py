from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class _PlatformRowWidget(QWidget):
    """Platform dropdown satırı: renkli kısaltma + isim."""

    clicked = Signal(str)

    _PALETTES = [
        ("#e8f0fe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#ecfdf5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#d1fae5", "#065f46"),
        ("#e0f2fe", "#075985"),
    ]

    def __init__(self, name: str, index: int, selected: bool = False, parent=None):
        super().__init__(parent)
        self._name = name
        self._selected = selected
        bg, fg = self._PALETTES[index % len(self._PALETTES)]
        self._bg, self._fg = bg, fg
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(10)

        abbr = QLabel(name[:3].upper())
        abbr.setFixedSize(30, 26)
        abbr.setAlignment(Qt.AlignCenter)
        abbr.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:5px;"
            "font-size:9px;font-weight:800;letter-spacing:0.5px;"
        )
        lay.addWidget(abbr)

        lbl = QLabel(name)
        lbl.setStyleSheet("font-size:13px;color:#0f172a;background:transparent;")
        lay.addWidget(lbl, 1)

        if selected:
            tick = QLabel("✓")
            tick.setStyleSheet("color:#2563eb;font-size:13px;font-weight:700;background:transparent;")
            lay.addWidget(tick)

        self._update_bg()

    def _update_bg(self):
        if self._selected:
            self.setStyleSheet("QWidget{background:#f0f7ff;}QWidget:hover{background:#e8f3ff;}")
        else:
            self.setStyleSheet("QWidget{background:white;}QWidget:hover{background:#f8fafc;}")

    def mousePressEvent(self, event):
        self.clicked.emit(self._name)


class PlatformSelectWidget(QWidget):
    """
    Tek seçimli platform dropdown.
    platform_names listesinden seçim yapar, renkli kısaltma + isim gösterir.

    Public API:
        set_platforms(names: List[str])
        set_current(name: str)
        current_text() -> str
        currentTextChanged Signal(str)
    """

    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._platforms: List[str] = []
        self._current: str = ""
        self._dropdown: Optional[QFrame] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._display = QFrame()
        self._display.setObjectName("platformSelectDisplay")
        self._display.setCursor(Qt.PointingHandCursor)
        self._display.setMinimumHeight(34)
        self._display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._display.setStyleSheet(
            "QFrame#platformSelectDisplay{"
            "background:white;border:1.5px solid #d8e2ed;border-radius:6px;"
            "}"
            "QFrame#platformSelectDisplay:hover{border-color:#93c5fd;}"
        )
        dl = QHBoxLayout(self._display)
        dl.setContentsMargins(8, 4, 8, 4)
        dl.setSpacing(8)

        self._abbr_lbl = QLabel("")
        self._abbr_lbl.setFixedSize(30, 24)
        self._abbr_lbl.setAlignment(Qt.AlignCenter)
        self._abbr_lbl.setStyleSheet(
            "background:#e8f0fe;color:#1e40af;border-radius:4px;"
            "font-size:9px;font-weight:800;letter-spacing:0.5px;"
        )
        self._abbr_lbl.hide()
        dl.addWidget(self._abbr_lbl)

        self._name_lbl = QLabel("Platform seçiniz...")
        self._name_lbl.setStyleSheet("font-size:13px;color:#94a3b8;background:transparent;")
        dl.addWidget(self._name_lbl, 1)

        self._chev = QLabel("▾")
        self._chev.setStyleSheet("color:#94a3b8;font-size:13px;background:transparent;")
        dl.addWidget(self._chev)

        lay.addWidget(self._display)
        self._display.mousePressEvent = self._toggle_dropdown

        # currentIndex ve currentText compat shims for QComboBox drop-in replacement
        self._current_index: int = -1

    # ── QComboBox compat ────────────────────────────────────────────────

    def addItems(self, names):
        self.set_platforms(list(names))

    def addItem(self, name):
        self._platforms.append(str(name))
        self._rebuild_dropdown()

    def currentText(self) -> str:
        return self._current

    def currentIndex(self) -> int:
        try:
            return self._platforms.index(self._current)
        except ValueError:
            return -1

    def setCurrentIndex(self, idx: int):
        if 0 <= idx < len(self._platforms):
            self._set_current(self._platforms[idx])

    def setCurrentText(self, text: str):
        self._set_current(str(text or ""))

    # currentIndexChanged shim — bağlamalar için
    @property
    def currentIndexChanged(self):
        return self.currentTextChanged

    # ── Public API ──────────────────────────────────────────────────────

    def set_platforms(self, names: List[str]):
        self._platforms = [str(n) for n in names if n]
        if self._current not in self._platforms:
            self._current = self._platforms[0] if self._platforms else ""
        self._update_display()

    def set_current(self, name: str):
        self._set_current(str(name or ""))

    # ── İç metodlar ────────────────────────────────────────────────────

    _PALETTES = [
        ("#e8f0fe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#ecfdf5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#d1fae5", "#065f46"),
        ("#e0f2fe", "#075985"),
    ]

    def _palette(self, name: str):
        idx = self._platforms.index(name) if name in self._platforms else 0
        return self._PALETTES[idx % len(self._PALETTES)]

    def _set_current(self, name: str):
        if name == self._current:
            return
        self._current = name
        self._update_display()
        self.currentTextChanged.emit(name)

    def _update_display(self):
        if self._current and self._current in self._platforms:
            bg, fg = self._palette(self._current)
            self._abbr_lbl.setText(self._current[:3].upper())
            self._abbr_lbl.setStyleSheet(
                f"background:{bg};color:{fg};border-radius:4px;"
                "font-size:9px;font-weight:800;letter-spacing:0.5px;"
            )
            self._abbr_lbl.show()
            self._name_lbl.setText(self._current)
            self._name_lbl.setStyleSheet(
                "font-size:13px;color:#0f172a;background:transparent;"
            )
        else:
            self._abbr_lbl.hide()
            self._name_lbl.setText("Platform seçiniz...")
            self._name_lbl.setStyleSheet(
                "font-size:13px;color:#94a3b8;background:transparent;"
            )

    def _toggle_dropdown(self, event=None):
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.hide()
            return
        self._open_dropdown()

    def _open_dropdown(self):
        if self._dropdown is None:
            self._dropdown = QFrame(None)
            self._dropdown.setObjectName("platformDropdown")
            self._dropdown.setStyleSheet(
                "QFrame#platformDropdown{"
                "background:white;border:1.5px solid #e2e8f0;border-radius:10px;"
                "}"
            )
            self._dropdown.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)

        # Mevcut satırları temizle
        if self._dropdown.layout():
            while self._dropdown.layout().count():
                item = self._dropdown.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QFrame().setLayout(self._dropdown.layout())

        root = QVBoxLayout(self._dropdown)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(0)

        for i, name in enumerate(self._platforms):
            row = _PlatformRowWidget(name, i, name == self._current)
            row.clicked.connect(self._on_platform_clicked)
            root.addWidget(row)

        self._dropdown.setFixedWidth(max(self.width(), 200))
        self._dropdown.adjustSize()

        pos = self.mapToGlobal(self._display.rect().bottomLeft())
        self._dropdown.move(pos.x(), pos.y() + 2)
        self._dropdown.show()
        self._dropdown.raise_()

    def _on_platform_clicked(self, name: str):
        self._dropdown.hide()
        self._set_current(name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.setFixedWidth(max(self.width(), 200))

