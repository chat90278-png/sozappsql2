# -*- coding: utf-8 -*-
"""Compact main-page identity-card and rail-header sizing polish."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QLabel

from src.ui.main_window import app_icon_path


def install_main_page_identity_runtime_fix() -> None:
    """Keep compact identity and platform-header geometry inside the approved layout."""
    from src.ui import main_page_analysis_window as main_page

    if getattr(main_page, "_STS_IDENTITY_RUNTIME_FIX_INSTALLED", False):
        return

    original_polish_identity = main_page.MainWindow._polish_identity_logo
    original_polish_platform_rail = main_page.MainWindow._polish_left_platform_rail

    def apply_identity_fit(self) -> None:
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
        title.setStyleSheet(
            "QLabel#appBrandTitle{background:transparent;color:#0f172a;border:none;"
            + f"padding:0;margin:0;font-size:{point_size}pt;font-weight:900;"
            + "}"
        )
        title.setToolTip(title.text())

    def apply_platform_header_alignment(self) -> None:
        platform_list = getattr(self, "platform_list", None)
        contract_table = getattr(self, "contract_table", None)
        right_panel = getattr(self, "right_panel", None)
        right_title = getattr(self, "right_title", None)
        if platform_list is None or contract_table is None or right_panel is None:
            return

        left_panel = platform_list.parentWidget()
        if left_panel is None:
            return

        title_label = None
        for label in left_panel.findChildren(QLabel):
            if str(label.text() or "").strip() == "Platformlar":
                title_label = label
                break
        if title_label is None:
            return

        header = title_label.parentWidget()
        if header is None:
            return

        # Make the left section heading use the same visual rule as the query heading.
        title_label.setObjectName("queryTitle")
        title_label.setStyleSheet("")
        if right_title is not None:
            title_label.setFont(right_title.font())
        title_label.style().unpolish(title_label)
        title_label.style().polish(title_label)
        title_label.update()

        # Align the platform-list top separator with the contract-table top edge.
        table_top = contract_table.mapTo(right_panel, QPoint(0, 0)).y()
        panel_top = left_panel.mapTo(left_panel, QPoint(0, 0)).y()
        target_header_height = max(40, int(table_top - panel_top))
        header.setMinimumHeight(target_header_height)
        header.setMaximumHeight(target_header_height)
        header_layout = header.layout()
        if header_layout is not None:
            header_layout.setContentsMargins(12, 0, 12, 0)
            header_layout.setSpacing(6)
        header.updateGeometry()
        left_panel.layout().invalidate() if left_panel.layout() is not None else None

    def polish_identity(self) -> None:
        original_polish_identity(self)
        # main_page_final_window appends its final stylesheet only after build()
        # returns. Defer one event-loop turn so these geometry/font overrides win.
        QTimer.singleShot(0, lambda: apply_identity_fit(self))

    def polish_platform_rail(self) -> None:
        original_polish_platform_rail(self)
        # Layout coordinates are reliable after the compact columns have settled.
        QTimer.singleShot(0, lambda: apply_platform_header_alignment(self))

    main_page.MainWindow._polish_identity_logo = polish_identity
    main_page.MainWindow._polish_left_platform_rail = polish_platform_rail
    main_page._STS_IDENTITY_RUNTIME_FIX_INSTALLED = True
