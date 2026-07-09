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

        # Stability hotfix for packaged Windows/PySide6 builds.
        # The animated corner button introduced a custom clicked -> popup path
        # plus geometry/shadow animation while the QMenu was being shown. The
        # crash dialog appears only on this interaction path. Replace only that
        # surface with a plain native QToolButton and keep the exact same QMenu,
        # actions, submenus and permission callbacks. Menu-open visual property
        # handling remains connected through the existing QMenu signals.
        animated_btn = getattr(self, "top_actions_btn", None)
        menu = animated_btn.menu() if isinstance(animated_btn, QToolButton) else None
        root = self.centralWidget()

        if isinstance(animated_btn, QToolButton) and menu is not None and root is not None:
            safe_btn = QToolButton(root)
            safe_btn.setObjectName("cornerMenuBtn")
            safe_btn.setText("☰")
            safe_btn.setToolTip("Menü")
            safe_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            safe_btn.setPopupMode(QToolButton.InstantPopup)
            safe_btn.setFixedSize(72, 72)
            safe_btn.setProperty("menuOpen", "false")

            menu.setParent(safe_btn)
            safe_btn.setMenu(menu)

            animated_btn.hide()
            animated_btn.setMenu(None)
            animated_btn.deleteLater()

            self.top_actions_btn = safe_btn
            self.top_actions_menu = menu
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
