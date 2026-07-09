# -*- coding: utf-8 -*-
"""Current-main Analiz Merkezi integration layer.

The compact MainWindow UI remains the visual source of truth. This subclass only
adds the Tur 21 Analysis Center report route/current permission boundary and the
main-entry compatibility hotfixes required by the current compact UI.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QToolButton, QWidget

from src.ui.main_page_final_window import MainWindow as CompactMainWindow


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center wiring."""

    def build(self):
        super().build()

        # Hard rollback of the experimental animated/popup integration on the
        # actual application entry class. Do NOT reuse the menu created by the
        # animated layer: that QMenu already owns animation-state signal
        # connections and custom popup styling. Build a completely fresh native
        # menu from the existing action factory so the click path is the same as
        # the original stable MainWindow implementation.
        experimental_btn = getattr(self, "top_actions_btn", None)
        root = self.centralWidget()

        if isinstance(experimental_btn, QToolButton) and root is not None:
            experimental_menu = experimental_btn.menu()
            experimental_btn.hide()
            experimental_btn.setMenu(None)
            if experimental_menu is not None:
                experimental_menu.hide()
                experimental_menu.deleteLater()
            experimental_btn.deleteLater()

            safe_btn = QToolButton(root)
            safe_btn.setObjectName("cornerMenuBtn")
            safe_btn.setText("☰")
            safe_btn.setToolTip("Menü")
            safe_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            safe_btn.setPopupMode(QToolButton.InstantPopup)
            safe_btn.setFixedSize(72, 72)

            # Fresh QMenu: _build_top_actions_menu recreates the original menu
            # hierarchy/callbacks/permission refresh and this subclass adds
            # Analiz Merkezi through its override below.
            safe_menu = self._build_top_actions_menu(safe_btn)
            safe_btn.setMenu(safe_menu)

            self.top_actions_btn = safe_btn
            self.top_actions_menu = safe_menu
            safe_btn.show()
            self.position_corner_menu()

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
