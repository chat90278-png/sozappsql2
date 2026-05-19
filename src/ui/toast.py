from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel


class ToastNotification(QWidget):
    _COLORS = {
        "success": ("#166534", "#dcfce7", "#16a34a"),
        "error": ("#991b1b", "#fee2e2", "#dc2626"),
        "info": ("#1e3a8a", "#dbeafe", "#2563eb"),
    }

    def __init__(self, parent: QWidget, message: str, kind: str = "success", duration: int = 2600):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        fg, bg, border = self._COLORS.get(kind, self._COLORS["success"])
        self.setStyleSheet(
            f"ToastNotification{{background:{bg};border:2px solid {border};"
            f"border-radius:8px;padding:0px;}}"
            f"QLabel{{color:{fg};font-size:12px;font-weight:700;"
            f"background:transparent;border:none;padding:0px;}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 16, 8)
        lay.setSpacing(8)
        icons = {"success": "✓", "error": "✕", "info": "ℹ"}
        icon_lbl = QLabel(icons.get(kind, "✓"))
        icon_lbl.setStyleSheet(
            f"font-size:16px;color:{border};font-weight:900;"
            "background:transparent;border:none;"
        )
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(False)
        lay.addWidget(icon_lbl, 0)
        lay.addWidget(msg_lbl, 1)
        self.adjustSize()
        self._place()
        self.raise_()
        self.show()

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(500)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)
        QTimer.singleShot(duration, self._anim.start)

    def _place(self):
        p = self.parent()
        if not p:
            return
        w = max(self.sizeHint().width(), 240)
        h = max(self.sizeHint().height(), 38)
        self.setFixedSize(w, h)
        bottom_offset = 52 + 8
        self.move(12, p.height() - h - bottom_offset)

    @staticmethod
    def show_in(parent: QWidget, message: str, kind: str = "success", duration: int = 2600):
        t = ToastNotification(parent, message, kind=kind, duration=duration)
        t._place()
        t.raise_()
        return t
