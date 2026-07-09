# -*- coding: utf-8 -*-
"""Current-main Analiz Merkezi integration layer.

The compact MainWindow UI remains the visual source of truth. This subclass adds
Analysis Center routing, the compact contract-status summary box, the approved
layered corner menu, and small main-page density fixes without changing business
callbacks or permission rules.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from analysis_center.analysis_data_loader import load_analysis_data
from analysis_center.analysis_metrics import compute_metrics
from src.ui.main_page_final_window import MainWindow as CompactMainWindow
from src.ui.main_window import app_icon_path
from src.ui.widgets.contract_status_summary import (
    ContractStatusSummary,
    ContractStatusSummaryWidget,
)
from src.ui.widgets.corner_menu_layer import CornerMenuOverlay
from src.ui.widgets.filterable_header import PLATFORM_SELECTED_ROLE, PlatformListDelegate


_log = logging.getLogger(__name__)


class CompactPlatformListDelegate(PlatformListDelegate):
    """Same platform semantics with tighter horizontal rhythm for the 275 px rail."""

    def paint(self, painter, option, index):
        painter.save()
        try:
            state = option.state
            is_selected = bool(index.data(PLATFORM_SELECTED_ROLE))
            is_hover = bool(state & QStyle.State_MouseOver)

            if is_selected:
                painter.fillRect(option.rect, QColor("#eff6ff"))
                painter.fillRect(
                    QRect(option.rect.left(), option.rect.top(), 3, option.rect.height()),
                    QColor("#2563eb"),
                )
            elif is_hover:
                painter.fillRect(option.rect, QColor("#f0f7ff"))
            else:
                painter.fillRect(option.rect, QColor("#ffffff"))

            row = index.row()
            pal_bg, pal_fg = self._PALETTES[row % len(self._PALETTES)]
            platform_name = str(index.data(Qt.UserRole) or index.data(Qt.DisplayRole) or "").strip()
            abbr = platform_name[:3].upper() if platform_name else "?"
            rect = option.rect

            abbr_rect = QRect(
                rect.left() + 8,
                rect.top() + (rect.height() - 24) // 2,
                30,
                24,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(pal_bg))
            painter.drawRoundedRect(abbr_rect, 5, 5)

            abbr_font = painter.font()
            abbr_font.setPointSize(8)
            abbr_font.setBold(True)
            painter.setFont(abbr_font)
            painter.setPen(QColor(pal_fg))
            painter.drawText(abbr_rect, Qt.AlignCenter, abbr)

            name_x = abbr_rect.right() + 7
            count_str = self._counts.get(row, "")
            count_w = 24 if count_str else 0
            name_rect = QRect(
                name_x,
                rect.top(),
                max(0, rect.width() - name_x - count_w - 6),
                rect.height(),
            )

            name_font = painter.font()
            name_font.setPointSize(9)
            name_font.setBold(is_selected)
            painter.setFont(name_font)
            painter.setPen(QColor("#1e40af") if is_selected else QColor("#374151"))
            painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, platform_name)

            if count_str:
                count_rect = QRect(rect.right() - count_w - 5, rect.top(), count_w, rect.height())
                count_font = painter.font()
                count_font.setPointSize(8)
                count_font.setBold(False)
                painter.setFont(count_font)
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(count_rect, Qt.AlignVCenter | Qt.AlignRight, count_str)
        finally:
            painter.restore()

    def sizeHint(self, option, index):
        try:
            width = int(option.rect.width()) if option is not None else 275
            return QSize(width if width > 0 else 275, 40)
        except Exception:
            return QSize(275, 40)


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center and safe layered corner menu."""

    def build(self):
        super().build()
        self._polish_compact_main_page()
        self._install_contract_status_widget()

        root = self.centralWidget()
        experimental_btn = getattr(self, "top_actions_btn", None)
        experimental_menu = experimental_btn.menu() if isinstance(experimental_btn, QToolButton) else None

        if root is not None and isinstance(experimental_btn, QToolButton):
            # Never reuse the compact experimental menu ownership tree. Build a
            # fresh hidden QAction/QMenu model, then render it through the layered
            # overlay. This keeps permission/action callbacks as source of truth.
            if experimental_menu is not None:
                try:
                    experimental_menu.hide()
                except Exception:
                    pass

            experimental_btn.hide()
            experimental_btn.setMenu(None)
            experimental_btn.deleteLater()

            self._corner_menu_model_host = QWidget(root)
            self._corner_menu_model_host.setObjectName("cornerMenuModelHost")
            self._corner_menu_model_host.setFixedSize(0, 0)
            self._corner_menu_model_host.hide()

            source_menu = self._build_top_actions_menu(self._corner_menu_model_host)
            source_menu.hide()

            self._corner_menu_overlay = CornerMenuOverlay(
                host=root,
                source_menu=source_menu,
                before_open=self._refresh_permission_actions,
                parent=self,
            )
            self.top_actions_btn = self._corner_menu_overlay.button
            self.top_actions_menu = source_menu
            self._corner_menu_overlay.reposition()

            if experimental_menu is not None:
                experimental_menu.deleteLater()

    def _polish_compact_main_page(self) -> None:
        self._polish_left_platform_rail()
        self._polish_identity_logo()
        self._fix_today_badge_text_width()

    def _polish_left_platform_rail(self) -> None:
        platform_list = getattr(self, "platform_list", None)
        if platform_list is None:
            return

        left_panel = platform_list.parentWidget()
        left_column = left_panel.parentWidget() if left_panel is not None else None
        if left_column is not None:
            left_column.setFixedWidth(275)
        if left_panel is not None:
            left_panel.setFixedWidth(275)

        self._platform_list_delegate = CompactPlatformListDelegate(platform_list)
        platform_list.setItemDelegate(self._platform_list_delegate)

        title_label = None
        if left_panel is not None:
            for label in left_panel.findChildren(QLabel, "panelTitle"):
                if str(label.text() or "").strip() == "Platformlar":
                    title_label = label
                    break
        if title_label is not None:
            header = title_label.parentWidget()
            if header is not None:
                header.setObjectName("platformPanelHeader")
                header.setAutoFillBackground(False)
                header_layout = header.layout()
                if header_layout is not None:
                    header_layout.setContentsMargins(10, 7, 10, 7)
                    header_layout.setSpacing(5)
                header.setStyleSheet(
                    "QWidget#platformPanelHeader{background:transparent;border:none;}"
                    "QLabel#platformPanelTitle{background:transparent;border:none;padding:0;margin:0;}"
                )
            title_label.setObjectName("platformPanelTitle")
            title_label.setAutoFillBackground(False)
            title_label.setStyleSheet(
                "QLabel#platformPanelTitle{background:transparent;border:none;padding:0;margin:0;}"
            )

        new_button = left_panel.findChild(QWidget, "newContractBtn") if left_panel is not None else None
        if new_button is not None:
            new_button.setMinimumHeight(42)
            new_button.setMaximumHeight(42)

        info_bar = getattr(self, "platform_info_bar", None)
        if info_bar is not None and info_bar.layout() is not None:
            info_bar.layout().setContentsMargins(8, 3, 6, 3)
            info_bar.layout().setSpacing(3)

    def _polish_identity_logo(self) -> None:
        root = self.centralWidget()
        logo = root.findChild(QLabel, "appIdentityLogo") if root is not None else None
        if logo is None:
            return
        logo.setFixedSize(72, 72)
        logo.setStyleSheet(
            "QLabel#appIdentityLogo{background:#0f2b61;border:1px solid #5fb7ff;"
            "border-radius:18px;padding:1px;}"
        )
        source = app_icon_path()
        if source and source.exists():
            pixmap = QPixmap(str(source))
            if not pixmap.isNull():
                logo.setPixmap(
                    pixmap.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

    def _fix_today_badge_text_width(self) -> None:
        today_num = getattr(self, "today_num", None)
        today_info = getattr(self, "today_info", None)
        if today_num is None or today_info is None:
            return
        today_box = today_num.parentWidget()
        today_layout = today_box.layout() if today_box is not None else None
        if today_box is not None:
            today_box.setFixedSize(68, 112)
        if today_layout is not None:
            # Legacy 12 px horizontal margins left only 44 px for "TEMMUZ".
            today_layout.setContentsMargins(4, 8, 4, 8)
            today_layout.setSpacing(1)
        today_info.setMinimumWidth(58)
        today_info.setMaximumWidth(58)
        today_info.setAlignment(Qt.AlignCenter)
        today_info.setWordWrap(False)
        today_info.setStyleSheet("background:transparent;border:none;padding:0;margin:0;")

    def _install_contract_status_widget(self) -> None:
        calendar_widget = getattr(self, "_cal_widget", None)
        if calendar_widget is None:
            return
        calendar_card = calendar_widget.parentWidget()
        calendar_layout = calendar_card.layout() if calendar_card is not None else None
        if calendar_layout is None:
            return

        upcoming_scroll = getattr(self, "upcoming_scroll", None)
        if upcoming_scroll is not None:
            calendar_layout.removeWidget(upcoming_scroll)
            upcoming_scroll.hide()

        try:
            calendar_widget.ensurePolished()
            calendar_width = max(
                int(calendar_widget.sizeHint().width()),
                int(calendar_widget.minimumSizeHint().width()),
            )
            if calendar_width > 0:
                calendar_widget.setFixedWidth(calendar_width)
            calendar_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        except Exception:
            _log.exception("Calendar size could not be locked while installing status widget")

        self.contract_status_widget = ContractStatusSummaryWidget(calendar_card)
        self.contract_status_widget.open_analysis_requested.connect(self.open_analysis_center)

        calendar_index = calendar_layout.indexOf(calendar_widget)
        insert_index = calendar_index if calendar_index >= 0 else 1
        calendar_layout.insertWidget(
            insert_index,
            self.contract_status_widget,
            0,
            Qt.AlignVCenter,
        )

        calendar_index = calendar_layout.indexOf(calendar_widget)
        if calendar_index >= 0:
            calendar_layout.insertStretch(calendar_index, 1)

    def _analysis_source_path(self) -> Path | None:
        if not self.store:
            return None
        source_path = (
            getattr(getattr(self.store, "db", None), "path", None)
            or getattr(self.store, "path", None)
            or self.path
        )
        try:
            return Path(source_path) if source_path else None
        except Exception:
            return None

    def _refresh_contract_status_widget(self) -> None:
        widget = getattr(self, "contract_status_widget", None)
        if widget is None:
            return
        if not self.store or not self.is_sts_mode():
            widget.clear_summary()
            return

        source_path = self._analysis_source_path()
        if source_path is None:
            widget.clear_summary()
            return

        try:
            data = load_analysis_data(
                source=source_path,
                contract_index=list(self.contract_index or []),
                use_sample=False,
            )
            metrics = compute_metrics(data)
            widget.set_summary(ContractStatusSummary.from_metrics(metrics))
        except Exception:
            _log.exception("Main-page contract status summary could not be refreshed")
            widget.clear_summary()

    def update_alert_strip(self):
        super().update_alert_strip()
        self._refresh_contract_status_widget()

    def set_empty_state(self):
        super().set_empty_state()
        widget = getattr(self, "contract_status_widget", None)
        if widget is not None:
            widget.clear_summary()

    def position_corner_menu(self):
        overlay = getattr(self, "_corner_menu_overlay", None)
        if overlay is not None:
            overlay.reposition()
            return
        super().position_corner_menu()

    def _build_top_actions_menu(self, parent) -> object:
        menu = super()._build_top_actions_menu(parent)
        for action in menu.actions():
            submenu = action.menu()
            if submenu is None or str(action.text() or "").replace("&", "") != "Raporlar":
                continue
            if not any(str(item.text() or "").replace("&", "") == "Analiz Merkezi" for item in submenu.actions()):
                submenu.addAction("Analiz Merkezi", self.open_analysis_center)
            break
        return menu

    def _analysis_export_guard(self) -> bool:
        return self.require_permission_ui("export_data", "Dashboard Excel")

    def open_analysis_center(self) -> QWidget | None:
        if not self.store or not self.is_sts_mode():
            QMessageBox.information(
                self,
                "Veri dosyası gerekli",
                "Analiz Merkezi için önce bir STS veri dosyası açın.",
            )
            return None

        from src.ui.analysis_center_window import AnalysisCenterWindow

        source_path = self._analysis_source_path()
        if source_path is None:
            QMessageBox.information(
                self,
                "Veri dosyası gerekli",
                "Analiz Merkezi veri kaynağı belirlenemedi.",
            )
            return None

        return self.open_or_raise_tool_window(
            "report:analysis_center",
            "Analiz Merkezi",
            lambda: AnalysisCenterWindow(
                source=source_path,
                contract_index=list(self.contract_index or []),
                parent=self,
                export_guard=self._analysis_export_guard,
            ),
        )
