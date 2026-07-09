# -*- coding: utf-8 -*-
"""Current-main Analiz Merkezi integration layer.

The compact MainWindow UI remains the visual source of truth. This subclass adds
Analysis Center routing and replaces the native/experimental popup surface with
the approved animated corner overlay. Existing QAction callbacks and permission
rules remain the source of truth.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QToolButton, QWidget

from src.ui.main_page_final_window import MainWindow as CompactMainWindow
from src.ui.widgets.corner_menu_overlay import CornerMenuOverlay


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center and safe corner-menu overlay."""

    def build(self):
        super().build()

        root = self.centralWidget()
        experimental_btn = getattr(self, "top_actions_btn", None)
        source_menu = experimental_btn.menu() if isinstance(experimental_btn, QToolButton) else None

        if root is not None and isinstance(experimental_btn, QToolButton) and source_menu is not None:
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
                before_open=self._refresh_permission_actions,
                parent=self,
            )
            self.top_actions_btn = self._corner_menu_overlay.button
            self.top_actions_menu = source_menu
            self._corner_menu_overlay.reposition()

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

        source_path = (
            getattr(getattr(self.store, "db", None), "path", None)
            or getattr(self.store, "path", None)
            or self.path
        )
        source_path = Path(source_path)

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
