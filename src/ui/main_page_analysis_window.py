# -*- coding: utf-8 -*-
"""Current-main Analiz Merkezi integration layer.

The compact MainWindow UI remains the visual source of truth. This subclass adds
Analysis Center routing, the compact contract-status summary box, and the approved
animated corner overlay. Existing QAction callbacks and permission rules remain
the source of truth.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolButton, QWidget

from analysis_center.analysis_data_loader import load_analysis_data
from analysis_center.analysis_metrics import compute_metrics
from src.ui.main_page_final_window import MainWindow as CompactMainWindow
from src.ui.widgets.contract_status_summary import (
    ContractStatusSummary,
    ContractStatusSummaryWidget,
)
from src.ui.widgets.corner_menu_overlay import CornerMenuOverlay


_log = logging.getLogger(__name__)


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center and safe corner-menu overlay."""

    def build(self):
        super().build()
        self._install_contract_status_widget()

        root = self.centralWidget()
        experimental_btn = getattr(self, "top_actions_btn", None)
        source_menu = experimental_btn.menu() if isinstance(experimental_btn, QToolButton) else None

        if root is not None and isinstance(experimental_btn, QToolButton) and source_menu is not None:
            # Refresh QAction visibility while the legacy QToolButton/QMenu wiring
            # is still intact. The overlay must not call this legacy refresh path
            # after top_actions_btn is replaced by the custom painted QWidget.
            try:
                self._refresh_permission_actions()
            except Exception:
                _log.exception("Corner-menu permission refresh failed during overlay install")

            # The QMenu tree remains only an action/callback model. It is never
            # shown as a native popup. The overlay renders ordinary child widgets
            # and triggers the existing QAction objects directly.
            experimental_btn.hide()
            experimental_btn.setMenu(None)
            source_menu.setParent(self)
            experimental_btn.deleteLater()

            self._corner_menu_overlay = CornerMenuOverlay(
                host=root,
                source_menu=source_menu,
                before_open=None,
                parent=self,
            )
            self.top_actions_btn = self._corner_menu_overlay.button
            self.top_actions_menu = source_menu
            self._corner_menu_overlay.reposition()

    def _install_contract_status_widget(self) -> None:
        calendar_widget = getattr(self, "_cal_widget", None)
        if calendar_widget is None:
            return
        calendar_card = calendar_widget.parentWidget()
        calendar_layout = calendar_card.layout() if calendar_card is not None else None
        if calendar_layout is None:
            return

        # The compact main page previously gave the middle area to the inherited
        # upcoming-scroll surface. Keep that object alive for legacy callbacks,
        # but replace only its visible slot with the new Analysis Center summary.
        upcoming_scroll = getattr(self, "upcoming_scroll", None)
        if upcoming_scroll is not None:
            calendar_layout.removeWidget(upcoming_scroll)
            upcoming_scroll.hide()

        self.contract_status_widget = ContractStatusSummaryWidget(calendar_card)
        self.contract_status_widget.open_analysis_requested.connect(self.open_analysis_center)

        calendar_index = calendar_layout.indexOf(calendar_widget)
        insert_index = calendar_index if calendar_index >= 0 else 1
        calendar_layout.insertWidget(
            insert_index,
            self.contract_status_widget,
            1,
            Qt.AlignVCenter,
        )

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
            # Use the same normalized loader + metric engine as Analysis Center.
            # We stop at compute_metrics instead of composing the full dashboard,
            # because the main-page box only needs four contract status metrics.
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
