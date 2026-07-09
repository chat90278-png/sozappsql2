# -*- coding: utf-8 -*-
"""Current-main adapter for the Tur 21 Analysis Center window.

The Analysis Center subsystem stays application-agnostic.  Current STS permission
policy is injected here so Dashboard Excel export cannot bypass ``export_data``.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import QMessageBox

from analysis_center.analysis_qt_window import AnalysisCenterWindow as _AnalysisCenterWindow


class AnalysisCenterWindow(_AnalysisCenterWindow):
    """Tur 21 Analysis Center with a current-main export permission boundary."""

    def __init__(
        self,
        *args,
        export_guard: Callable[[], bool] | None = None,
        **kwargs,
    ):
        self._integration_export_guard = export_guard
        super().__init__(*args, **kwargs)

    def _export_dashboard_to_excel(self) -> None:
        guard = self._integration_export_guard
        if guard is not None:
            try:
                if not bool(guard()):
                    return
            except Exception:
                logging.getLogger(__name__).exception("Dashboard Excel export guard failed")
                QMessageBox.warning(
                    self,
                    "Dashboard Excel",
                    "Excel aktarım yetkisi doğrulanamadı.",
                )
                return
        super()._export_dashboard_to_excel()
