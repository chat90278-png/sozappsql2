# -*- coding: utf-8 -*-
"""Current-main Analiz Merkezi integration layer.

The compact MainWindow UI remains the visual source of truth. This subclass only
adds the Tur 21 Analysis Center report route/current permission boundary and the
main-entry compatibility hotfixes required by the current compact UI.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QToolButton, QWidget

from src.ui.main_page_final_window import MainWindow as CompactMainWindow


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center wiring."""

    def build(self):
        super().build()

        # Hotfix: the animated corner button had been switched to DelayedPopup
        # and its clicked(bool) signal was wired to a manually positioned popup
        # handler. On the packaged Windows/PySide6 runtime that click path can
        # escape through sys.excepthook before the menu is shown. Keep the same
        # animated button, QMenu instance, actions, permission refresh callbacks
        # and aboutToShow/aboutToHide visual state; delegate popup opening back
        # to QToolButton's proven native InstantPopup path.
        btn = getattr(self, "top_actions_btn", None)
        if isinstance(btn, QToolButton):
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            btn.setPopupMode(QToolButton.InstantPopup)

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
