# -*- coding: utf-8 -*-
"""Compact main-page identity-card sizing polish."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QLabel

from src.ui.main_window import app_icon_path


def install_main_page_identity_runtime_fix() -> None:
    """Keep the identity title inside its card and enlarge only the icon artwork."""
    from src.ui import main_page_analysis_window as main_page

    if getattr(main_page, "_STS_IDENTITY_RUNTIME_FIX_INSTALLED", False):
        return

    original_polish = main_page.MainWindow._polish_identity_logo

    def polish_identity(self) -> None:
        original_polish(self)

        root = self.centralWidget()
        if root is None:
            return

        logo = root.findChild(QLabel, "appIdentityLogo")
        if logo is not None:
            logo.setFixedSize(72, 72)
            logo.setStyleSheet(
                "QLabel#appIdentityLogo{background:#0f2b61;border:1px solid #5fb7ff;"
                "border-radius:18px;padding:0;}"
            )
            source = app_icon_path()
            if source and source.exists():
                pixmap = QPixmap(str(source))
                if not pixmap.isNull():
                    logo.setPixmap(
                        pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )

        title = root.findChild(QLabel, "appBrandTitle")
        if title is None:
            return

        title.setWordWrap(False)
        title.setMinimumWidth(0)
        title.setMaximumWidth(163)
        font = title.font()
        point_size = max(10, int(font.pointSize() or 10))
        while point_size > 10:
            font.setPointSize(point_size)
            if QFontMetrics(font).horizontalAdvance(title.text()) <= title.maximumWidth():
                break
            point_size -= 1
        font.setPointSize(point_size)
        title.setFont(font)
        title.setToolTip(title.text())

    main_page.MainWindow._polish_identity_logo = polish_identity
    main_page._STS_IDENTITY_RUNTIME_FIX_INSTALLED = True
