from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

_LOGGER_NAME = "KY_STS.crash"
_INSTALLED = False
_FAULT_LOG_FILE = None
_PREV_SYS_EXCEPTHOOK = None
_PREV_THREADING_EXCEPTHOOK = None
_PREV_QT_MESSAGE_HANDLER = None


def _log_dir() -> Path:
    base = Path.home() / ".ky-sts" / "logs"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        fallback = Path.cwd() / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def crash_log_path() -> Path:
    return _log_dir() / "sts_crash.log"


def _logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    path = crash_log_path()
    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == path for handler in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger


def _safe_log_exception(prefix: str, exc_type: Type[BaseException], exc_value: BaseException, exc_tb: Optional[TracebackType]) -> None:
    try:
        _logger().critical(prefix, exc_info=(exc_type, exc_value, exc_tb))
    except Exception:
        try:
            traceback.print_exception(exc_type, exc_value, exc_tb)
        except Exception:
            pass


def _sys_excepthook(exc_type: Type[BaseException], exc_value: BaseException, exc_tb: Optional[TracebackType]) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        if _PREV_SYS_EXCEPTHOOK:
            _PREV_SYS_EXCEPTHOOK(exc_type, exc_value, exc_tb)
        return
    _safe_log_exception("Unhandled Python exception", exc_type, exc_value, exc_tb)
    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            QMessageBox.critical(
                None,
                "Beklenmeyen Hata",
                "Uygulamada beklenmeyen bir hata oluştu. İşlem güvenli şekilde durduruldu. "
                "Hata kaydı şu konuma yazıldı:\n\n"
                f"{crash_log_path()}\n\n"
                "Lütfen bu dosyayı destek ekibiyle paylaşın.",
            )
    except Exception:
        pass


def _threading_excepthook(args) -> None:
    exc_type = getattr(args, "exc_type", None)
    exc_value = getattr(args, "exc_value", None)
    exc_tb = getattr(args, "exc_traceback", None)
    thread = getattr(args, "thread", None)
    if exc_type is None or exc_value is None:
        return
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        if _PREV_THREADING_EXCEPTHOOK:
            _PREV_THREADING_EXCEPTHOOK(args)
        return
    name = getattr(thread, "name", "unknown")
    _safe_log_exception(f"Unhandled threading exception in {name}", exc_type, exc_value, exc_tb)


def _install_faulthandler(logger: logging.Logger) -> None:
    global _FAULT_LOG_FILE
    try:
        if _FAULT_LOG_FILE is None or _FAULT_LOG_FILE.closed:
            _FAULT_LOG_FILE = crash_log_path().open("a", encoding="utf-8")
        if not faulthandler.is_enabled():
            faulthandler.enable(file=_FAULT_LOG_FILE, all_threads=True)
        logger.info("faulthandler enabled")
    except Exception:
        logger.exception("faulthandler could not be enabled")


def _install_qt_message_handler(logger: logging.Logger) -> None:
    global _PREV_QT_MESSAGE_HANDLER
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:
        logger.info("PySide6 Qt message handler is not available")
        return

    qt_debug = getattr(QtMsgType, "QtDebugMsg", None)
    qt_info = getattr(QtMsgType, "QtInfoMsg", None)
    qt_warning = getattr(QtMsgType, "QtWarningMsg", None)
    qt_critical = getattr(QtMsgType, "QtCriticalMsg", None)
    qt_fatal = getattr(QtMsgType, "QtFatalMsg", None)

    def _qt_message_handler(mode, context, message):
        try:
            if mode == qt_debug:
                level = logging.DEBUG
            elif mode == qt_info:
                level = logging.INFO
            elif mode == qt_warning:
                level = logging.WARNING
            elif mode == qt_critical:
                level = logging.ERROR
            elif mode == qt_fatal:
                level = logging.CRITICAL
            else:
                level = logging.INFO
            file_name = getattr(context, "file", "") or ""
            line = getattr(context, "line", 0) or 0
            function = getattr(context, "function", "") or ""
            logger.log(level, "Qt message: %s (%s:%s %s)", message, file_name, line, function)
        except Exception:
            pass

    try:
        _PREV_QT_MESSAGE_HANDLER = qInstallMessageHandler(_qt_message_handler)
        logger.info("Qt message handler installed")
    except Exception:
        logger.exception("Qt message handler could not be installed")


def install_crash_handlers(app_name: str = "KY-STS") -> Path:
    """Install low-noise crash diagnostics and return the crash log path."""
    global _INSTALLED, _PREV_SYS_EXCEPTHOOK, _PREV_THREADING_EXCEPTHOOK
    logger = _logger()
    if _INSTALLED:
        return crash_log_path()
    _INSTALLED = True
    logger.info("Installing crash handlers for %s", app_name)

    _PREV_SYS_EXCEPTHOOK = sys.excepthook
    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        _PREV_THREADING_EXCEPTHOOK = threading.excepthook
        threading.excepthook = _threading_excepthook

    _install_faulthandler(logger)
    _install_qt_message_handler(logger)
    logger.info("Crash log path: %s", crash_log_path())
    return crash_log_path()
