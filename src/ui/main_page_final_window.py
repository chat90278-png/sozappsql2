# -*- coding: utf-8 -*-
"""Approved compact MainWindow workspace layout.

The UI is isolated in a subclass so parallel feature branches can port the
layout without replacing MainWindow business logic.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from src.ui.main_window import MainWindow as LegacyMainWindow, qt_obj_alive


_FINAL_MAIN_STYLE = r"""
QWidget#mainWorkspace, QWidget#leftMainColumn, QWidget#rightMainColumn {
    background:#e8eef5;
}
QFrame#appIdentityCard, QFrame#calendarHeaderCard {
    background:#ffffff;
    border:1px solid #d7e0ea;
    border-radius:15px;
}
QLabel#appIdentityLogo {
    background:#0f2b61;
    border:1px solid #5fb7ff;
    border-radius:15px;
    padding:4px;
}
QLabel#appBrandTitle {
    background:transparent;
    color:#0f172a;
    font-size:17px;
    font-weight:900;
}
QLabel#appBrandSubtitle {
    background:transparent;
    color:#75849a;
    font-size:12px;
}
QToolButton#cornerMenuBtn {
    background:#243548;
    color:#ffffff;
    border:none;
    border-top-left-radius:0px;
    border-top-right-radius:0px;
    border-bottom-right-radius:0px;
    border-bottom-left-radius:72px;
    padding:0 0 14px 14px;
    font-size:22px;
    font-weight:900;
}
QToolButton#cornerMenuBtn:hover { background:#2b4055; }
QToolButton#cornerMenuBtn:pressed { background:#1b2c3d; }
QToolButton#cornerMenuBtn::menu-indicator { image:none; width:0; }
QFrame#openWindowsStrip {
    background:#f6f9fc;
    border:1px solid #d7e0ea;
    border-radius:0px;
    border-top-left-radius:10px;
    border-top-right-radius:10px;
}
QLabel#openWindowsLabel {
    background:transparent;
    color:#40536c;
    font-size:11px;
    font-weight:900;
}
QScrollArea#openWindowsScroll, QWidget#openWindowsHost {
    background:transparent;
    border:0;
}
QFrame#calendarHeaderCard QScrollArea#upcomingScroll,
QFrame#calendarHeaderCard QScrollArea#upcomingScroll QWidget {
    background:transparent;
    border:0;
}
"""


class MainWindow(LegacyMainWindow):
    """MainWindow with the approved compact workspace composition."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(self.styleSheet() + _FINAL_MAIN_STYLE)
        self.position_corner_menu()

    def build(self):
        # Build all original widgets/signals first; then only recompose the UI.
        super().build()
        root = self.centralWidget()
        root.setObjectName("mainWorkspace")
        main = root.layout()

        topbar = self.connection_label.parentWidget()
        alert_strip = self.today_num.parentWidget().parentWidget()
        today_box = self.today_num.parentWidget()
        left_panel = self.platform_list.parentWidget()
        right_panel = self.right_panel

        # Find and reuse the original body layout. It keeps all panel behavior.
        body = None
        for index in range(main.count()):
            candidate = main.itemAt(index).layout()
            if isinstance(candidate, QHBoxLayout):
                body = candidate
                break
        if body is None:
            raise RuntimeError("MainWindow body layout bulunamadı")

        body.removeWidget(left_panel)
        body.removeWidget(right_panel)
        body.setSpacing(12)

        left_column = QWidget(root)
        left_column.setObjectName("leftMainColumn")
        left_column.setFixedWidth(300)
        left_lay = QVBoxLayout(left_column)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(12)

        right_column = QWidget(root)
        right_column.setObjectName("rightMainColumn")
        right_lay = QVBoxLayout(right_column)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(12)

        body.addWidget(left_column, 0)
        body.addWidget(right_column, 1)

        # Identity card reuses the real logo and the same connection_label.
        identity = QFrame(left_column)
        identity.setObjectName("appIdentityCard")
        identity.setFixedHeight(146)
        identity_lay = QHBoxLayout(identity)
        identity_lay.setContentsMargins(16, 14, 16, 14)
        identity_lay.setSpacing(14)

        logo = topbar.findChild(QLabel, "appLogo")
        if logo is not None:
            logo.setObjectName("appIdentityLogo")
            logo.setFixedSize(58, 58)
            identity_lay.addWidget(logo, 0, Qt.AlignVCenter)

        brand_wrap = QWidget(identity)
        brand_lay = QVBoxLayout(brand_wrap)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(2)
        brand_lay.addStretch(1)
        title = QLabel("STS Sözleşme Takip", brand_wrap)
        title.setObjectName("appBrandTitle")
        subtitle = QLabel("Konfigürasyon Yönetimi", brand_wrap)
        subtitle.setObjectName("appBrandSubtitle")
        brand_lay.addWidget(title)
        brand_lay.addWidget(subtitle)
        brand_lay.addSpacing(6)
        self.connection_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        brand_lay.addWidget(self.connection_label, 0, Qt.AlignLeft)
        brand_lay.addStretch(1)
        identity_lay.addWidget(brand_wrap, 1)

        left_lay.addWidget(identity, 0)
        left_lay.addWidget(left_panel, 1)

        # Calendar header uses the exact existing date/upcoming/calendar widgets.
        calendar_card = QFrame(right_column)
        calendar_card.setObjectName("calendarHeaderCard")
        calendar_card.setFixedHeight(146)
        calendar_lay = QHBoxLayout(calendar_card)
        calendar_lay.setContentsMargins(16, 7, 94, 7)
        calendar_lay.setSpacing(14)

        today_box.setFixedSize(68, 112)
        calendar_lay.addWidget(today_box, 0, Qt.AlignVCenter)
        self.upcoming_label.hide()
        self.upcoming_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        calendar_lay.addWidget(self.upcoming_scroll, 1)
        calendar_lay.addWidget(self._cal_widget, 0, Qt.AlignVCenter)

        right_lay.addWidget(calendar_card, 0)
        right_lay.addWidget(right_panel, 1)

        # Old full-width containers remain hidden compatibility parents for the
        # inherited KPI refs; hidden widgets consume no layout height.
        topbar.hide()
        alert_strip.hide()

        # Re-skin the existing tool-window strip as true tabs at the very top.
        self.open_windows_strip.setFixedHeight(46)
        strip_lay = self.open_windows_strip.layout()
        strip_lay.setContentsMargins(12, 6, 84, 0)
        strip_lay.setSpacing(6)
        strip_label = self.open_windows_strip.findChild(QLabel, "openWindowsLabel")
        if strip_label is not None:
            strip_label.setText("·  Pencereler:")
            strip_label.setFixedHeight(34)
        self.open_windows_scroll.setFixedHeight(40)
        self.open_windows_layout.setSpacing(6)
        self.open_windows_layout.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

        # Same QToolButton/menu/callbacks, now detached as a root corner overlay.
        self.top_actions_btn.setParent(root)
        self.top_actions_btn.setObjectName("cornerMenuBtn")
        self.top_actions_btn.setText("☰")
        self.top_actions_btn.setFixedSize(72, 72)
        self.top_actions_btn.show()
        self.position_corner_menu()

    def _tool_chip_frame_style(self, active: bool = False, stale: bool = False) -> str:
        accent = "#f59e0b" if stale else ("#2563eb" if active else "#b8c8dc")
        if active:
            return (
                "QFrame#toolWindowChip{background:#ffffff;"
                f"border:1px solid {accent};border-bottom:1px solid #ffffff;"
                "border-top-left-radius:10px;border-top-right-radius:10px;"
                "border-bottom-left-radius:0;border-bottom-right-radius:0;}"
            )
        return (
            "QFrame#toolWindowChip{background:#f7faff;"
            f"border:1px solid {accent};"
            "border-top-left-radius:10px;border-top-right-radius:10px;"
            "border-bottom-left-radius:4px;border-bottom-right-radius:4px;}"
        )

    def _tool_chip_title_style(self, active: bool = False, stale: bool = False) -> str:
        color = "#92400e" if stale else ("#1849a2" if active else "#263b55")
        return (
            "QPushButton#toolChipTitle{background:transparent;border:0;"
            f"color:{color};font-size:12px;font-weight:800;padding:0 2px;"
            "text-align:left;min-height:22px;max-height:24px;}"
            "QPushButton#toolChipTitle:hover{color:#1d4ed8;}"
        )

    def _tool_chip_close_style(self, active: bool = False) -> str:
        return (
            "QPushButton#toolChipClose{background:transparent;border:0;"
            "color:#6b7c91;font-size:12px;font-weight:900;padding:0 2px;"
            "min-width:18px;max-width:18px;border-radius:8px;}"
            "QPushButton#toolChipClose:hover{background:#fee2e2;color:#dc2626;}"
        )

    def _sync_tool_chip_style(self, key: str) -> None:
        chip = getattr(self, "_tool_window_chip_by_key", {}).get(key)
        if not qt_obj_alive(chip):
            return
        self._apply_tool_chip_visual(chip, str(chip.property("active") or "false") == "true")

    def _apply_tool_chip_visual(self, chip: QWidget, active: bool = False) -> None:
        if not qt_obj_alive(chip):
            return
        stale = str(chip.property("stale") or "false") == "true"
        chip.setProperty("active", "true" if active else "false")
        chip.setStyleSheet(self._tool_chip_frame_style(active, stale))
        title_btn = chip.findChild(QPushButton, "toolChipTitle")
        close_btn = chip.findChild(QPushButton, "toolChipClose")
        full_title = str(chip.property("fullTitle") or "")
        if title_btn is not None:
            title_btn.setStyleSheet(self._tool_chip_title_style(active, stale))
            shown = self._tool_chip_display_text(full_title or title_btn.text(), max(110, title_btn.width() or 170))
            title_btn.setText(("● " if stale else "") + shown)
            title_btn.setToolTip(full_title or shown)
        if close_btn is not None:
            close_btn.setStyleSheet(self._tool_chip_close_style(active))
        try:
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        except Exception:
            pass
        chip.update()

    def _create_tool_window_chip(self, key: str, title: str) -> QWidget:
        chip = super()._create_tool_window_chip(key, title)
        chip.setMinimumHeight(36)
        chip.setMaximumHeight(40)
        lay = chip.layout()
        lay.setContentsMargins(12, 6, 7, 4)
        lay.setSpacing(6)
        self.open_windows_layout.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self._apply_tool_chip_visual(chip, key == getattr(self, "_active_tool_window_key", ""))
        return chip

    def _refresh_tool_window_strip_visibility(self) -> None:
        super()._refresh_tool_window_strip_visibility()
        QTimer.singleShot(0, self.position_corner_menu)

    def update_alert_strip(self):
        super().update_alert_strip()
        # The calculations and upcoming-pill click behavior remain unchanged.
        self.alert_overdue_group.hide()
        self.alert_critical_group.hide()
        self.alert_divider1.hide()
        self.alert_divider2.hide()

    def position_corner_menu(self):
        btn = getattr(self, "top_actions_btn", None)
        parent = self.centralWidget()
        if not qt_obj_alive(btn) or parent is None:
            return
        btn.move(max(parent.width() - btn.width(), 0), 0)
        btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_corner_menu()

    def showEvent(self, event):
        super().showEvent(event)
        self.position_corner_menu()
