from __future__ import annotations

import sys
import traceback
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon

from src.ui.main_page_final_window import MainWindow
from src.ui.main_window import (
    app_icon_path,
    configure_windows_app_identity,
    open_share_contract_window,
    _share_metadata_from_path,
)
from src.services.share_package_service import validate_share_package

from src.ui.dialogs.workbook_start import WorkbookStartDialog
from src.config.app_config import DEFAULT_FILE, EXCEL_DATA_SOURCE_DISABLED_MESSAGE, APP_ID
from src.core.crash_logger import install_crash_handlers
import src.auth as auth

_log = logging.getLogger(__name__)

if __name__ == "__main__":
    install_crash_handlers()
    configure_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("STS")
    app.setApplicationDisplayName("STS")
    app.setDesktopFileName(APP_ID)
    app.setFont(QFont("Segoe UI", 10))
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Startup uses modal dialogs before the main window exists.  Keep Qt from
    # treating an accepted file/staff dialog as the last-window-close event;
    # otherwise the first successful registration/login can request app quit
    # before the real MainWindow event loop starts.
    app.setQuitOnLastWindowClosed(False)

    cli_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 and str(sys.argv[1]).strip() else None
    if cli_path and _share_metadata_from_path(cli_path):
        result = validate_share_package(cli_path)
        if result.is_share_package and (not result.is_supported or not result.is_valid):
            QMessageBox.critical(None, "Paylaşım paketi açılamadı", "\n".join(result.errors or ["Paylaşım paketi açılamadı."]))
            sys.exit(1)
        try:
            win = open_share_contract_window(cli_path)
            if win is None:
                raise ValueError("Paylaşım metadata bulunamadı.")
            app.setQuitOnLastWindowClosed(True)
            win.show()
            sys.exit(app.exec())
        except Exception as exc:
            _log.exception("Paylaşım STS açılış hatası")
            QMessageBox.critical(None, "Paylaşım açılamadı", f"Paylaşım dosyası açılamadı.\n\n{exc}")
            sys.exit(1)

    selected_path = None
    while selected_path is None:
        start_dialog = WorkbookStartDialog()
        if not start_dialog.exec() or not start_dialog.selected_path:
            sys.exit(0)
        candidate_path = Path(start_dialog.selected_path)
        if candidate_path.suffix.lower() != ".sts":
            QMessageBox.warning(None, "STS dosyası gerekli", EXCEL_DATA_SOURCE_DISABLED_MESSAGE)
            continue
        selected_path = candidate_path
    if _share_metadata_from_path(selected_path):
        result = validate_share_package(selected_path)
        if result.is_share_package and (not result.is_supported or not result.is_valid):
            QMessageBox.critical(None, "Paylaşım paketi açılamadı", "\n".join(result.errors or ["Paylaşım paketi açılamadı."]))
            sys.exit(1)
        try:
            win = open_share_contract_window(selected_path)
            if win is None:
                raise ValueError("Paylaşım metadata bulunamadı.")
            app.setQuitOnLastWindowClosed(True)
            win.show()
            sys.exit(app.exec())
        except Exception as exc:
            _log.exception("Paylaşım STS açılış hatası")
            QMessageBox.critical(None, "Paylaşım açılamadı", f"Paylaşım dosyası açılamadı.\n\n{exc}")
            sys.exit(1)

    staff = None
    if not auth.ensure_system_admin_setup(selected_path):
        sys.exit(0)
    staff = auth.require_staff_login(selected_path)
    if not staff:
        sys.exit(0)

    win = MainWindow(initial_path=selected_path, current_staff=staff)
    win.show()

    def _start_initial_load():
        app.setQuitOnLastWindowClosed(True)
        try:
            win.start_sts_load(selected_path)
        except Exception as exc:
            _log.exception("Başlangıç yükleme hatası")
            traceback.print_exc()
            QMessageBox.critical(win, "Açılış hatası", f"Uygulama başlatılırken hata oluştu.\n\n{exc}")
            app.quit()

    QTimer.singleShot(0, _start_initial_load)
    sys.exit(app.exec())
