# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import calendar
import re
import ctypes
import getpass
import os
import base64
import copy
import time
import traceback
import tempfile
import zipfile
import sqlite3
import unicodedata
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Protocol, Tuple
from src.ui.dialogs.auto_accept_dialog import open_auto_accept_dialog
from src.services import perf_tracker


from src.domain.constants import (
    CORE_SHEETS,
    HEADER_ROW,
    SUBHEADER_ROW,
    DATA_START_ROW,
    STATUS_VALUES,
)
from src.config.app_config import (
    APP_TITLE,
    APP_ICON_PATH,
    APP_ICON_ICO_PATH,
    APP_ID,
    DEFAULT_FILE,
    COMP_SHEET,
    USERS_SHEET,
    PLATFORM_LOGO_SHEET,
    TAG_SHEET,
    TAG_KIND_DEF,
    TAG_KIND_ASSIGN,
    LOG_FOLDER_NAME,
    NAVY,
    LIGHT,
    CARD,
    HEAD,
    BLUE,
    GREEN,
    GRID,
    TEXT_MUTED,
    BASE_HEADERS,
    MAIN_TOTAL_LABEL,
    SYSTEM_TOTAL_SUFFIX,
    TR_MONTHS,
    TR_WEEKDAYS,
    LOG_HEADERS,
    TAG_HEADERS,
    EXTRA_SYSTEM_SHEET_NAMES,
    EXCEL_DATA_SOURCE_DISABLED_MESSAGE,
)
from src.models.app_models import ComponentDef, ContractInfo, SystemInfo, DeliveryInfo, TagDef
from src.domain.contract_timing import contract_timing, is_completed_status
from src.domain.delivery_coverage import acceptance_coverage_issues
from src.domain.flexible_date import flexible_or_blank, is_exact_date, is_tbd_contract_no, parse_flexible_date, validate_flexible_date, format_flexible_date
from src.core.crash_logger import install_crash_handlers
from src.ui.widgets import stat_card, set_card_value
from src.ui.theme import STYLE
from src.ui.tarih import ContractCalendarWindow
from src.ui.ozet import ContractSummaryDialog
from src.ui.date_picker import build_date_input as _build_date_input
from src.ui.kullanim_kilavuzu import UsageGuideDialog
from src.ui.dialogs.platform_component_manager import PlatformComponentManagerDialog
from src.ui.dialogs.delivery_schedule_report_dialog import DeliveryScheduleReportDialog
from src.ui.dialogs.platform_delivery_report_dialog import PlatformTeslimatDurumuReportDialog
from src.ui.dialogs.contract_dialog import ContractDialog
from src.ui.dialogs.contract_edit_dialog import ContractEditDialog
from src.ui.dialogs.delivery_dialog import DeliveryDialog
from src.ui.dialogs.tag_manager_dialog import TagManagerDialog
from src.ui.dialogs.system_dialog import SystemDialog
from src.ui.dialogs.multi_system_dialog import MultiSystemDialog
from src.ui.dialogs.styled_dialog import (
    SystemTypeStore,
    StyledDialog,
    UserManagerDialog,
    TagAssignDialog,
)
from src.ui.message_boxes import ask_yes_no
from src.ui.widgets.contract_file_widgets import (
    ContractFileDropButton,
    ContractFileTreeWidget,
    ElidedLabel,
    ElidedValueLabel,
)
from src.ui.widgets.filterable_header import FilterableHeaderView, PlatformListDelegate
from src.ui.widgets.platform_select import _PlatformRowWidget, PlatformSelectWidget
from src.ui.widgets.user_select import (
    _UserRowWidget, _MultiUserDropdown, MultiUserSelectWidget,
    MultiStaffSelectWidget, MultiPlatformSelectWidget,
)
from src.ui.widgets.platform_tabs import (
    PlatformTabsWidget, HeaderUserPopup, FixedContractTypeField,
    BadgeTabButton, ContractActionTabs, ContractSharePopover,
    UnitTrackingSlotCard, UnitTrackingSidePanel,
)
from src.ui.contract.contract_work_window import ContractWorkWindow

from PySide6.QtCore import Qt, QDate, QObject, QThread, Signal, QTimer, QPoint, QSize, QRect, QEvent, QPropertyAnimation, QEasingCurve, QUrl, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QFont, QFontMetrics, QColor, QPixmap, QIcon, QPainter, QAction, QCursor, QCloseEvent, QDesktopServices, QKeySequence, QShortcut, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QDialog, QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
    QMessageBox, QFileDialog, QFrame, QScrollArea, QCheckBox, QHeaderView,
    QSizePolicy, QProgressBar, QProgressDialog, QStyledItemDelegate, QStyleOptionViewItem, QTextEdit,
    QToolButton, QMenu, QInputDialog, QWidgetAction, QStackedWidget, QAbstractItemView, QStyle, QRadioButton, QButtonGroup, QTabWidget, QTabBar, QCalendarWidget
)
from shiboken6 import isValid as _qt_is_valid


def qt_obj_alive(obj) -> bool:
    """PySide/Shiboken objeleri C++ tarafında silindiyse False döner.

    Qt'nin C++ tarafından çağırdığı eventFilter/sizeHint gibi override'larda
    silinmiş objeye dokunmak RuntimeError üretir; PySide bunu yakalayamazsa
    uygulama `Fatal Python error: Aborted` ile kapanabilir.
    """
    if obj is None:
        return False
    try:
        return bool(_qt_is_valid(obj))
    except Exception:
        return True


def normalized_tag_key(value: str) -> str:
    """Return a stable comparison key for tag names, including Turkish case variants."""
    text = str(value or "").strip().replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _share_metadata_from_path(path: Path | str) -> dict:
    """Return share metadata for STS share packages; empty dict for normal files."""
    try:
        p = Path(path)
        if not p.exists() or p.suffix.lower() != ".sts":
            return {}
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='share_metadata'").fetchone()
            if not row:
                return {}
            rows = conn.execute("SELECT key,value FROM share_metadata").fetchall()
            meta = {str(r["key"]): str(r["value"] or "") for r in rows}
            return meta if str(meta.get("share_mode", "")).lower() == "true" else {}
        finally:
            conn.close()
    except Exception:
        return {}


def _write_share_metadata(path: Path | str, metadata: dict) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS share_metadata(key TEXT PRIMARY KEY, value TEXT)")
        for key, value in dict(metadata or {}).items():
            conn.execute(
                "INSERT INTO share_metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )
        conn.commit()
    finally:
        conn.close()





def app_icon_path() -> Path:
    """Return the native Windows icon when available, otherwise the SVG logo."""
    if APP_ICON_ICO_PATH.exists():
        return APP_ICON_ICO_PATH
    return APP_ICON_PATH


def configure_windows_app_identity() -> None:
    """Set a stable Windows AppUserModelID so taskbar icons use the STS icon."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

def normalize_sheet_name(name: str) -> str:
    txt = str(name or "").strip().lower()
    repl = {
        "\u0131": "i",
        "\u0130": "i",
        "\u015f": "s",
        "\u011f": "g",
        "\u00fc": "u",
        "\u00f6": "o",
        "\u00e7": "c",
    }
    for a, b in repl.items():
        txt = txt.replace(a, b)
    return txt


def is_system_sheet_name(name: str) -> bool:
    if not name:
        return True
    n = normalize_sheet_name(name)
    core_norm = {normalize_sheet_name(x) for x in CORE_SHEETS}
    if n in core_norm or n in EXTRA_SYSTEM_SHEET_NAMES:
        return True
    if str(name).startswith("_") or n.startswith("_"):
        return True
    return False


def safe_sheet_name(name: str) -> str:
    n = re.sub(r"[\\/*?:\[\]]", "_", name.strip().upper())
    return n[:31] or "PLATFORM"


def safe_filename_part(value: object, fallback: str = "DOSYA") -> str:
    """Windows dosya adına güvenli, okunabilir parça üretir."""
    text = str(value or "").strip() or str(fallback or "DOSYA")
    replacements = {
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
        "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'[<>:"/\\|?*]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._ ")
    return text or str(fallback or "DOSYA")


def suggested_export_excel_path(sts_path: object, options: Optional[dict] = None) -> Path:
    """Export için varsayılan dosya adı: STSADI__PLATFORM__export__yyyy-MM-dd_HH-mm.xlsx"""
    try:
        source = Path(sts_path) if sts_path else Path.cwd() / "sts_export.sts"
    except Exception:
        source = Path.cwd() / "sts_export.sts"

    base_name = safe_filename_part(source.stem, "STS")
    opts = dict(options or {})
    platforms_raw = opts.get("platforms") or []
    platforms: List[str] = []
    seen: set[str] = set()
    for item in platforms_raw:
        name = str(item or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            platforms.append(name)

    scope = str(opts.get("scope") or "").strip().lower()
    if scope == "selected" and len(platforms) == 1:
        scope_name = safe_filename_part(platforms[0], "PLATFORM")
    elif scope == "selected" and len(platforms) > 1:
        scope_name = "SECILI_PLATFORMLAR"
    else:
        scope_name = "TUM_PLATFORMLAR"

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"{base_name}__{scope_name}__export__{stamp}.xlsx"
    folder = source.parent if str(source.parent) not in {"", "."} else Path.cwd()
    return folder / filename


_STS_VERSIONED_RE = re.compile(
    r"^(?P<code>STS-[A-Z]\d+)__v(?P<ver>\d+)__(?P<stamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2})$",
    re.IGNORECASE,
)


def parse_sts_versioned_stem(stem: str) -> Tuple[str, int]:
    """STS-A1__v004__2026-06-15_10-30 -> (STS-A1, 4)."""
    raw = str(stem or "").strip()
    m = _STS_VERSIONED_RE.match(raw)
    if m:
        code = str(m.group("code") or "STS-A1").upper()
        try:
            ver = int(m.group("ver") or 0)
        except Exception:
            ver = 0
        return code, max(0, ver)
    # Eski/serbest adla açılmış dosyalar ilk kapanışta standart isme taşınır.
    return "STS-A1", 0


def next_sts_versioned_path(current_path: object) -> Path:
    """Tek aktif .sts dosyası için sonraki ad: STS-A1__v004__yyyy-MM-dd_HH-mm.sts"""
    current = Path(current_path)
    folder = current.parent if str(current.parent) not in {"", "."} else Path.cwd()
    code, current_ver = parse_sts_versioned_stem(current.stem)

    max_ver = current_ver
    try:
        for item in folder.glob(f"{code}__v*__*.sts"):
            parsed_code, parsed_ver = parse_sts_versioned_stem(item.stem)
            if parsed_code == code:
                max_ver = max(max_ver, parsed_ver)
    except Exception:
        pass

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    next_ver = max_ver + 1
    while True:
        candidate = folder / f"{code}__v{next_ver:03d}__{stamp}.sts"
        if not candidate.exists() or candidate.resolve() == current.resolve():
            return candidate
        next_ver += 1


def close_store_for_file_rename(store) -> None:
    """Windows'ta SQLite dosyasını yeniden adlandırabilmek için bağlantıyı kapatır."""
    if store is None:
        return
    try:
        if hasattr(store, "save"):
            store.save()
    except Exception:
        pass
    for close_name in ("close", "disconnect"):
        try:
            closer = getattr(store, close_name, None)
            if callable(closer):
                closer()
                return
        except Exception:
            pass
    try:
        db = getattr(store, "db", None)
        conn = getattr(db, "conn", None)
        if conn is not None:
            try:
                conn.commit()
            except Exception:
                pass
            conn.close()
    except Exception:
        pass


def rename_sts_file_to_next_version(store, current_path: object) -> Optional[Path]:
    """Değişiklik varsa kapanışta tek aktif STS dosyasını bir üst versiyon adına taşır."""
    try:
        old_path = Path(current_path)
        if old_path.suffix.lower() != ".sts" or not old_path.exists():
            return None
        new_path = next_sts_versioned_path(old_path)
        if new_path.resolve() == old_path.resolve():
            return old_path
        close_store_for_file_rename(store)
        old_path.replace(new_path)
        try:
            setattr(store, "path", new_path)
            db = getattr(store, "db", None)
            if db is not None:
                setattr(db, "path", new_path)
        except Exception:
            pass
        return new_path
    except Exception:
        return None


def to_iso(qdate: QDate) -> str:
    return f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"


def parse_iso_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + int(months or 0)
    year = d.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(d.day, days[month - 1])
    return date(year, month, day)


def iso_or_blank(text: str) -> str:
    d = parse_iso_date(text)
    return d.isoformat() if d else ""


def contract_date_picker_events(ci: Optional[ContractInfo], systems: Optional[List[SystemInfo]] = None) -> List[dict]:
    events: List[dict] = []
    if ci:
        contract_deadline = parse_iso_date(str(getattr(ci, "completion_date", "") or ""))
        if contract_deadline:
            no = str(getattr(ci, "no", "") or "").strip() or "Sözleşme"
            ctype = str(getattr(ci, "contract_type", "") or "").strip()
            title = f"{no} {ctype}".strip()
            events.append({
                "date": contract_deadline,
                "title": title,
                "lines": [
                    f"Termin tarihi: {contract_deadline.isoformat()}",
                    f"Durum: {str(getattr(ci, 'status', '') or '-')}",
                ],
                "tag": "Sözleşme termini",
                "color": "#f97316",
            })
    for sys_info in list(systems or []):
        system_deadline = parse_iso_date(str(getattr(sys_info, "completion_date", "") or ""))
        if not system_deadline:
            continue
        no = str(getattr(ci, "no", "") or "").strip() if ci else ""
        name = str(getattr(sys_info, "name", "") or "").strip() or "Sistem"
        events.append({
            "date": system_deadline,
            "title": f"{no} {name}".strip(),
            "lines": [
                f"Termin tarihi: {system_deadline.isoformat()}",
                f"Durum: {str(getattr(sys_info, 'status', '') or '-')}",
            ],
            "tag": "Sistem termini",
            "color": "#2563eb",
        })
    return events


def as_number(v):
    try:
        if callable(v):
            return 0.0
        if isinstance(v, (dict, list, tuple, set)):
            return 0.0
        return float(v or 0)
    except RecursionError:
        try:
            sys.__stderr__.write("RecursionError in as_number; returning 0.0\n")
        except Exception:
            pass
        return 0.0
    except Exception:
        return 0.0


def _global_exc_handler(exc_type, exc, tb):
    if issubclass(exc_type, RecursionError):
        try:
            sys.__stderr__.write("".join(traceback.format_exception_only(exc_type, exc)))
        except Exception:
            pass
        return
    try:
        traceback.print_exception(exc_type, exc, tb)
    except Exception:
        pass
    app_instance = QApplication.instance() if "QApplication" in globals() else None
    if app_instance is not None:
        try:
            QMessageBox.critical(None, "Beklenmeyen Hata", f"Uygulamada beklenmeyen bir hata oluştu.\n\n{exc}")
        except Exception:
            pass


def fmt_num(v) -> str:
    try:
        f = float(v or 0)
        return str(int(f)) if f == int(f) else str(round(f, 2))
    except Exception:
        return str(v or "")


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    txt = str(color or "").strip().lstrip("#")
    if len(txt) == 3:
        txt = "".join(ch * 2 for ch in txt)
    if len(txt) != 6:
        return (59, 130, 246)
    try:
        return (int(txt[0:2], 16), int(txt[2:4], 16), int(txt[4:6], 16))
    except Exception:
        return (59, 130, 246)


def _mix_rgb(a: Tuple[int, int, int], b: Tuple[int, int, int], ratio: float) -> Tuple[int, int, int]:
    r = max(0.0, min(1.0, float(ratio)))
    return (
        int(a[0] * (1 - r) + b[0] * r),
        int(a[1] * (1 - r) + b[1] * r),
        int(a[2] * (1 - r) + b[2] * r),
    )


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2]))),
    )


def tag_chip_style(color: str, selected: bool = False) -> str:
    base = _hex_to_rgb(color)
    bg = _mix_rgb(base, (255, 255, 255), 0.78 if not selected else 0.68)
    border = _mix_rgb(base, (255, 255, 255), 0.28 if not selected else 0.12)
    lum = (0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2]) / 255.0
    txt = "#0F172A" if lum > 0.58 else "#FFFFFF"
    if not selected:
        txt = _rgb_to_hex(_mix_rgb(base, (15, 23, 42), 0.22))
    return (
        f"QPushButton {{ background:{_rgb_to_hex(bg)}; color:{txt}; border:1px solid {_rgb_to_hex(border)}; "
        "border-radius:13px; padding:4px 10px; font-weight:800; } "
        f"QPushButton:hover {{ border-color:{_rgb_to_hex(_mix_rgb(base, (15, 23, 42), 0.18))}; }}"
    )





from src.services.excel_store import ExcelStore
from src.services.sts_store import STSStore
from src.services.sts_database import CURRENT_SCHEMA_VERSION, STSMigrationError, read_sts_schema_version
from src import auth
from src.workers import ContractSaveWorker, STSIndexWorker, STSLoadWorker

_log = logging.getLogger("STS")





COL_PLATFORM = 0
COL_TYPE = 1
COL_CONTRACT_NO = 2
COL_USER = 3
COL_STATUS = 4
COL_T_DATE = 5
COL_REMAINING = 6
COL_TAGS = 7
COL_SUMMARY = 8
PLATFORM_SELECTED_ROLE = Qt.UserRole + 100


class ContractTableModel(QAbstractTableModel):
    HEADERS = [
        "Platform",
        "Sözleşme Türü",
        "Sözleşme No",
        "Kullanıcı",
        "Durum",
        "Termin Tarihi",
        "Kalan Gün",
        "Etiketler",
        "Özet",
    ]

    def __init__(
        self,
        parent=None,
        *,
        status_display_fn: Optional[Callable[[dict], tuple[str, str]]] = None,
        remaining_display_fn: Optional[Callable[[dict], tuple[str, str]]] = None,
        tags_fn: Optional[Callable[[dict], list]] = None,
        row_height_fn: Optional[Callable[[int], int]] = None,
    ):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._status_display_fn = status_display_fn
        self._remaining_display_fn = remaining_display_fn
        self._tags_fn = tags_fn
        self._row_height_fn = row_height_fn

    def setRows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return COL_SUMMARY + 1

    def _status_display(self, it: dict) -> tuple[str, str]:
        if callable(self._status_display_fn):
            return self._status_display_fn(it)
        return "", ""

    def _remaining_display(self, it: dict) -> tuple[str, str]:
        if callable(self._remaining_display_fn):
            return self._remaining_display_fn(it)
        return "", ""

    def _tags_for_row(self, it: dict) -> list:
        if callable(self._tags_fn):
            return list(self._tags_fn(it) or [])
        return []

    def _row_height_for_tags(self, tag_count: int) -> int:
        if callable(self._row_height_fn):
            return int(self._row_height_fn(tag_count))
        return 36

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._rows):
            return None
        it = self._rows[row]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == COL_PLATFORM:
                return it.get("platform", "")
            if col == COL_TYPE:
                return it.get("type_display") or it.get("type", "")
            if col == COL_CONTRACT_NO:
                return it.get("no", "")
            if col == COL_USER:
                return it.get("user", "")
            if col == COL_STATUS:
                status_text, _color = self._status_display(it)
                return status_text
            if col == COL_T_DATE:
                completion_date = str(it.get("completion_date") or "").strip()
                if completion_date in {"-", "Belirsiz", "—"} or not parse_flexible_date(completion_date):
                    return ""
                return completion_date
            if col == COL_REMAINING:
                remaining_text, _color = self._remaining_display(it)
                return remaining_text
            if col == COL_TAGS:
                return ", ".join(str(tag) for tag in self._tags_for_row(it))
            if col == COL_SUMMARY:
                return ""

        if role == Qt.ForegroundRole:
            if col == COL_STATUS:
                _status_text, color = self._status_display(it)
                return QColor(color) if color else None
            if col == COL_REMAINING:
                _remaining_text, color = self._remaining_display(it)
                return QColor(color) if color else None

        if role == Qt.UserRole:
            return it

        if role == Qt.ToolTipRole:
            if col == COL_SUMMARY:
                return "Bileşen özetini gör"
            if col == COL_TAGS:
                return ", ".join(str(tag) for tag in self._tags_for_row(it))

        if role == Qt.TextAlignmentRole:
            if col == COL_SUMMARY:
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.SizeHintRole and col == COL_TAGS:
            height = self._row_height_for_tags(len(self._tags_for_row(it)))
            return QSize(-1, height)

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None


class ContractTagsDelegate(QStyledItemDelegate):
    def __init__(self, tags_fn, tag_color_fn, row_height_fn=None, parent=None):
        super().__init__(parent)
        self._tags_fn = tags_fn
        self._tag_color_fn = tag_color_fn
        self._row_height_fn = row_height_fn

    def _tags_for_index(self, index) -> tuple[Optional[dict], list]:
        it = index.data(Qt.UserRole)
        if not isinstance(it, dict):
            return None, []
        tags_list = list(self._tags_fn(it) or []) if callable(self._tags_fn) else []
        return it, tags_list

    def _row_height_for_tags(self, tag_count: int) -> int:
        if callable(self._row_height_fn):
            return int(self._row_height_fn(tag_count))
        n = int(tag_count or 0)
        return max(36, n * 22 + max(0, n - 1) * 3 + 8) if n > 0 else 36

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        _it, tags_list = self._tags_for_index(index)
        if _it is None:
            super().paint(painter, option, index)
            return
        if not tags_list:
            return

        painter.save()
        try:
            margin_x = 5
            margin_y = 4
            chip_sp = 3
            chip_h = 22
            chip_pad_x = 8
            radius = 9

            font = QFont(option.font)
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetrics(font)

            x = option.rect.left() + margin_x
            y = option.rect.top() + margin_y
            for tag_name in tags_list:
                tag_text = str(tag_name)
                color = self._tag_color_fn(tag_text) if callable(self._tag_color_fn) else "#3B82F6"
                base_rgb = _hex_to_rgb(color)
                bg = _mix_rgb(base_rgb, (255, 255, 255), 0.78)
                border_c = _mix_rgb(base_rgb, (255, 255, 255), 0.28)
                txt_c = _mix_rgb(base_rgb, (15, 23, 42), 0.22)

                chip_w = fm.horizontalAdvance(tag_text) + 2 * chip_pad_x
                chip_rect = QRect(x, y, chip_w, chip_h)
                painter.setBrush(QColor(_rgb_to_hex(bg)))
                painter.setPen(QColor(_rgb_to_hex(border_c)))
                painter.drawRoundedRect(chip_rect, radius, radius)
                painter.setPen(QColor(_rgb_to_hex(txt_c)))
                painter.drawText(chip_rect.adjusted(chip_pad_x, 0, -chip_pad_x, 0), Qt.AlignCenter, tag_text)
                y += chip_h + chip_sp
        finally:
            painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        it = index.data(Qt.UserRole)
        if not isinstance(it, dict):
            return super().sizeHint(option, index)
        tags_list = list(self._tags_fn(it) or []) if callable(self._tags_fn) else []
        return QSize(option.rect.width(), self._row_height_for_tags(len(tags_list)))


class ContractSummaryDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        try:
            font = QFont(option.font)
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QColor("#185FA5"))
            painter.drawText(option.rect, Qt.AlignCenter, "\U0001F50D")
        finally:
            painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return super().sizeHint(option, index)










def form_label(txt):
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l


def _legacy_build_date_input_unused(
    parent: QWidget,
    placeholder: str = "yyyy-aa-gg",
    max_date: Optional[date] = None,
) -> Tuple[QLineEdit, QWidget]:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)

    btn = QPushButton("📅")
    btn.setObjectName("dateBtn")
    btn.setFixedSize(34, 34)
    btn.setToolTip("Takvimden tarih seç")

    wrap = QWidget(parent)
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(edit, 1)
    lay.addWidget(btn, 0)

    def choose_date():
        popup = QDialog(parent, Qt.Popup | Qt.FramelessWindowHint)
        popup.setObjectName("calendarPopup")
        pop_lay = QVBoxLayout(popup)
        pop_lay.setContentsMargins(6, 6, 6, 6)
        pop_lay.setSpacing(0)
        cal = QCalendarWidget(popup)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setGridVisible(True)
        if max_date:
            cal.setMaximumDate(QDate(max_date.year, max_date.month, max_date.day))
            disabled_fmt = QTextCharFormat()
            disabled_fmt.setBackground(QColor("#EEF2F7"))
            disabled_fmt.setForeground(QColor("#94A3B8"))
            month_days = calendar.monthrange(max_date.year, max_date.month)[1]
            for day_num in range(max_date.day + 1, month_days + 1):
                cal.setDateTextFormat(QDate(max_date.year, max_date.month, day_num), disabled_fmt)
        current = parse_iso_date(edit.text())
        if current:
            if max_date and current > max_date:
                current = max_date
            cal.setSelectedDate(QDate(current.year, current.month, current.day))

        def on_pick(qd: QDate):
            edit.setText(to_iso(qd))
            popup.accept()

        cal.clicked.connect(on_pick)
        pop_lay.addWidget(cal)
        popup.adjustSize()
        popup.move(btn.mapToGlobal(QPoint(0, btn.height() + 2)))
        popup.exec()

    btn.clicked.connect(choose_date)
    return edit, wrap


def build_date_input(
    parent: QWidget,
    placeholder: str = "yyyy-aa-gg",
    max_date: Optional[date] = None,
    events_provider: Optional[Callable[[], List[dict]]] = None,
) -> Tuple[QLineEdit, QWidget]:
    return _build_date_input(parent, placeholder=placeholder, max_date=max_date, events_provider=events_provider)


from src.ui.delegates import CompactNumberDelegate, CenterTableDelegate, DropdownDelegate

from src.ui.toast import ToastNotification
















def is_tbd_contract_no(contract_no: str) -> bool:
    """Platform - TBD - N formatındaki geçici sözleşme numaralarını algılar."""
    return bool(re.match(r"^\s*.+?\s*-\s*TBD\s*-\s*\d+\s*$", str(contract_no or ""), re.IGNORECASE))


def _is_sts_store(store) -> bool:
    return bool(
        store is not None
        and hasattr(store, "db")
        and hasattr(store, "write_users")
        and hasattr(store, "write_components")
    )

def section_label(text):
    l = QLabel(text)
    l.setObjectName("sectionTitle")
    return l

def configure_table(table: QTableWidget, compact: bool = False):
    table.setItemDelegate(CenterTableDelegate(table))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.horizontalHeader().setMinimumHeight(42 if not compact else 34)
    table.verticalHeader().setDefaultSectionSize(34 if not compact else 28)
    table.setWordWrap(False)

def fill_table(table, rows):
    table.setRowCount(len(rows)); table.setColumnCount(len(rows[0]) if rows else table.columnCount())
    for r,row in enumerate(rows):
        for c,v in enumerate(row): table.setItem(r,c,QTableWidgetItem(str(int(v) if isinstance(v,float) and v==int(v) else v)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)



from src.ui.dialogs.contract_summary_popup import ContractSummaryPopup

from src.ui.dialogs.workbook_start import WorkbookStartDialog
from src.ui.contract import work_window_view as cw_view

class MainWindow(QMainWindow):
    def __init__(self, store: Optional[STSStore] = None, contract_index: Optional[List[dict]] = None, initial_path: Optional[Path] = None, current_staff: Optional[dict] = None):
        super().__init__()
        self.path = Path(initial_path) if initial_path else (store.path if store else Path(DEFAULT_FILE))
        self.store = store
        self.current_staff = current_staff or auth.current_staff
        self.contract_index = contract_index if contract_index is not None else []
        self._tag_color_map_cache: Optional[Dict[str, str]] = None
        self._loading = False
        self._sts_loader_thread: Optional[QThread] = None
        self._sts_loader_worker: Optional[STSLoadWorker] = None
        self._sts_index_thread: Optional[QThread] = None
        self._sts_index_worker: Optional[STSIndexWorker] = None
        self._sts_warned_legacy_migration = False
        self._export_thread: Optional[QThread] = None
        self._export_worker = None
        self._store_loading = False
        self._export_sts_to_excel_running = False
        self._opening_contract = False
        self._refreshing_platform_index = False
        self._index_ready_for_use = False
        self._version_baseline_signature = None
        self.calendar_window: Optional[ContractCalendarWindow] = None
        self.selected_platforms: set[str] = set()
        self.multi_platform_mode: bool = False
        self._updating_platform_list = False
        self._platform_checkbox_changed: Optional[str] = None
        self.setWindowTitle(APP_TITLE)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1360, 820)
        self.setStyleSheet(STYLE)
        self.all_contract_rows = []
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.timeout.connect(self.apply_contract_filter)
        self.build()
        self._install_system_admin_shortcut()
        if self.store:
            if not self.contract_index:
                # UI thread'i bloklamamak için hazır store olsa bile indeksleme yükünü worker'a bırak.
                if str(self.store.path).lower().endswith(".sts"):
                    self.start_sts_load(self.store.path)
                else:
                    QMessageBox.warning(self, "STS dosyası gerekli", EXCEL_DATA_SOURCE_DISABLED_MESSAGE)
                    self.set_empty_state()
            else:
                self.refresh(rebuild_index=False)
                self._remember_version_baseline()
        else:
            self.set_empty_state()
            self.connection_label.setText("STS bağlı değil")


    def export_sts_to_excel(self):
        if getattr(self, "_export_sts_to_excel_running", False):
            return
        self._export_sts_to_excel_running = True
        try:
            if self._export_thread and self._export_thread.isRunning():
                QMessageBox.information(self, "Excel’e Aktar",
                                        "İşlem devam ediyor, lütfen bekleyin.")
                return
            if not self.require_permission_ui("export_data", "Excel’e Aktar"):
                return
            if not self.store:
                QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
                return
            if not hasattr(self.store, "export_to_excel"):
                QMessageBox.information(self, "Excel’e Aktar", "Excel’e aktarım yalnızca STS veri dosyalarında desteklenir.")
                return
            active_platform = ""
            selected = set(getattr(self, "selected_platforms", set()))
            if len(selected) == 1:
                active_platform = next(iter(selected))
            from src.ui.dialogs.excel_export_options import ExcelExportDialog
            dlg = ExcelExportDialog(self.store, self, active_platform=active_platform, contract_index=getattr(self, "contract_index", None))
            if not dlg.exec() or not dlg.result_options:
                return
            opts = dict(dlg.result_options)
            try:
                suggested_out = suggested_export_excel_path(getattr(self, "path", None), opts)
            except Exception:
                suggested_out = Path(self.path).with_suffix(".xlsx")
            try:
                out, _ = QFileDialog.getSaveFileName(self, "Excel’e Aktar", str(suggested_out), "Excel (*.xlsx)")
            except Exception as exc:
                QMessageBox.critical(self, "Excel’e Aktar", f"Kayıt penceresi açılamadı:\n{exc}")
                return
            if not out:
                return
            if not str(out).lower().endswith(".xlsx"):
                out = str(out) + ".xlsx"
            from src.workers.export_workers import ExcelExportWorker
            self._export_progress = QProgressDialog("Excel dosyası hazırlanıyor...", "", 0, 100, self)
            self._export_progress.setWindowTitle("Excel’e Aktar")
            self._export_progress.setLabelText("Excel dosyası hazırlanıyor...")
            self._export_progress.setCancelButton(None)
            self._export_progress.setMinimumDuration(0)
            self._export_progress.setAutoClose(False)
            self._export_progress.setAutoReset(False)
            self._export_progress.setValue(0)
            self._export_progress.show()
            QApplication.processEvents()

            db_path = getattr(getattr(self.store, "db", None), "path", None)
            if not db_path:
                self._export_progress.close()
                QMessageBox.critical(self, "Excel’e Aktar", "Veritabanı yolu belirlenemedi.")
                return

            self._export_thread = QThread(self)
            # Worker'a canlı store/bağlantı DEĞİL, dosya yolu verilir; worker kendi
            # salt-okunur sqlite bağlantısını kendi thread'inde açar (thread-safe).
            self._export_worker = ExcelExportWorker(db_path, out, opts)
            self._export_worker.moveToThread(self._export_thread)
            self._export_thread.started.connect(self._export_worker.run)
            # KRİTİK: Sinyaller lambda/yerel fonksiyona DEĞİL, ana penceredeki
            # gerçek metotlara bağlanır. Lambda bağlanırsa Qt onu sinyali yayan
            # thread'de (worker) çalıştırır ve GUI'ye worker thread'inden dokunmak
            # uygulamayı çökertir. Alıcı self (ana thread'de yaşayan QObject)
            # olduğunda Qt bağlantıyı otomatik QueuedConnection yapar; tüm GUI
            # işleri güvenle ana thread'de çalışır.
            self._export_out_path = str(out)
            self._export_opts = dict(opts)
            self._export_worker.progress.connect(self._on_export_progress)
            self._export_worker.finished.connect(self._on_export_finished)
            self._export_worker.failed.connect(self._on_export_failed)
            self._export_worker.finished.connect(self._export_thread.quit)
            self._export_worker.failed.connect(self._export_thread.quit)
            self._export_thread.finished.connect(self._export_worker.deleteLater)
            self._export_thread.finished.connect(self._export_thread.deleteLater)
            self._export_thread.finished.connect(self._clear_export_refs)
            self._export_thread.start()

        finally:
            self._export_sts_to_excel_running = False

    # --- Excel export slot'ları: sinyaller worker thread'inden gelir ama bu
    # metotlar ana pencerenin (ana thread) metodu olduğu için Qt bunları
    # QueuedConnection ile ana thread'de çalıştırır. GUI burada güvendedir. ---

    def _clear_export_refs(self):
        self._export_thread = None
        self._export_worker = None

    def _on_export_progress(self, p, m):
        dlg = getattr(self, "_export_progress", None)
        if dlg is not None:
            try:
                dlg.setLabelText(str(m))
                dlg.setValue(int(max(0, min(100, int(p)))))
            except Exception:
                pass

    def _on_export_finished(self, res):
        dlg = getattr(self, "_export_progress", None)
        if dlg is not None:
            try:
                dlg.setValue(100)
                dlg.close()
            except Exception:
                pass
        out = getattr(self, "_export_out_path", "")
        opts = getattr(self, "_export_opts", {})
        # Export işlemi artık uygulama işlem geçmişine ekstra log yazmaz.
        # Sadece kullanıcıya başarı mesajı gösterilir; teşhis/debug log dosyası
        # da worker tarafında kapatıldı.
        box = QMessageBox(self)
        box.setWindowTitle("Excel’e Aktar")
        box.setIcon(QMessageBox.Information)
        box.setText("Excel dosyası oluşturuldu.")
        open_btn = box.addButton("Dosyayı Aç", QMessageBox.AcceptRole)
        box.addButton("Kapat", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            try:
                import os
                os.startfile(str(out))
            except Exception:
                QMessageBox.information(self, "Excel’e Aktar", f"Dosya konumu:\n{out}")

    def _on_export_failed(self, msg):
        dlg = getattr(self, "_export_progress", None)
        if dlg is not None:
            try:
                dlg.close()
            except Exception:
                pass
        # Export işlemi için debug/işlem geçmişi logu oluşturulmaz.
        QMessageBox.critical(self, "Excel’e Aktar", str(msg))

    def open_database_management(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return
        if not hasattr(self.store, "database_stats"):
            QMessageBox.information(self, "Veritabanı Yönetimi", "Veritabanı yönetimi yalnızca STS veri dosyalarında desteklenir.")
            return
        from src.ui.dialogs.database_management import DatabaseManagementDialog
        self.open_or_raise_tool_window(
            "manager:database",
            "Veri Yönetimi",
            lambda: DatabaseManagementDialog(self.store, self, current_staff=self.current_staff),
        )

    def open_performance_tracking(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return

        if not hasattr(self.store, "performance_stats"):
            QMessageBox.information(
                self,
                "Performans İzleme",
                "Performans izleme ekranı yalnızca STS veri dosyalarında desteklenir."
            )
            return

        from src.ui.dialogs.performance_tracking import PerformanceTrackingDialog
        self.open_or_raise_tool_window(
            "report:performance",
            "Performans İzleme",
            lambda: PerformanceTrackingDialog(self.store, self),
        )

    def open_activity_logs(self):
        if not self.require_permission_ui("view_action_history", "İşlem Geçmişi"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası açın.")
            return
        if not hasattr(self.store, "list_logs"):
            QMessageBox.information(self, "İşlem Geçmişi", "İşlem geçmişi yalnızca STS veri dosyalarında desteklenir.")
            return
        from src.ui.dialogs.activity_logs import ActivityLogDialog
        self.open_or_raise_tool_window(
            "report:activity_logs",
            "İşlem Geçmişi",
            lambda: ActivityLogDialog(self.store, self),
        )

    def _permission_db(self):
        if self.store is not None and getattr(self.store, "db", None) is not None:
            return self.store.db.conn
        return self.path

    def has_permission(self, permission_code: str) -> bool:
        return auth.has_permission(self.current_staff, permission_code, self._permission_db())

    def require_permission_ui(self, permission_code: str, title: str = "Yetki gerekli") -> bool:
        if self.has_permission(permission_code):
            return True
        QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        return False

    def _install_system_admin_shortcut(self) -> None:
        self.system_admin_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Shift+A"), self)
        self.system_admin_shortcut.setContext(Qt.ApplicationShortcut)
        self.system_admin_shortcut.activated.connect(self.open_system_admin_login_from_shortcut)

    def open_system_admin_login_from_shortcut(self) -> None:
        if not self.store or not self.is_sts_mode():
            return
        if self.current_staff and bool((self.current_staff or {}).get("is_admin")):
            QMessageBox.information(self, "Sistem Yöneticisi", "Zaten sistem yöneticisi oturumundasınız.")
            return

        previous_staff = self.current_staff
        admin_staff = auth.show_system_admin_login_dialog(self._permission_db(), self)
        if not admin_staff:
            self.current_staff = previous_staff
            auth.current_staff = previous_staff
            return

        self.current_staff = admin_staff
        auth.current_staff = admin_staff
        actor_name = str(admin_staff.get("full_name") or admin_staff.get("admin_name") or "Sistem Yöneticisi")
        if self.store is not None and hasattr(self.store, "actor"):
            self.store.actor = actor_name
        self._propagate_current_staff_to_open_windows(admin_staff)
        self._refresh_permission_actions()
        QMessageBox.information(self, "Sistem Yöneticisi", "Sistem yöneticisi oturumu açıldı.")

    def _propagate_current_staff_to_open_windows(self, staff: dict) -> None:
        for widget in QApplication.topLevelWidgets():
            if widget is self or not isinstance(widget, ContractWorkWindow):
                continue
            try:
                widget.current_staff = staff
                if getattr(widget, "store", None) is self.store and hasattr(widget.store, "actor"):
                    widget.store.actor = str(staff.get("full_name") or "Sistem Yöneticisi")
            except Exception:
                pass

    def open_staff_permissions_dialog(self, initial_tab: str = "staffRoles"):
        if not self.store or not self.is_sts_mode():
            QMessageBox.information(self, "Veri dosyası gerekli", "Yetki yönetimi için önce bir STS veri dosyası açın.")
            return
        required_permission = "manage_roles" if initial_tab == "rolePermissions" else "manage_staff"
        if not self.require_permission_ui(required_permission, "Yetki Yönetimi"):
            return
        from src.ui.dialogs.staff_permissions import StaffPermissionsDialog

        def factory():
            dlg = StaffPermissionsDialog(self._permission_db(), self.current_staff, self, initial_tab=initial_tab)
            try:
                dlg.permissions_saved.connect(self._refresh_permission_actions)
            except Exception:
                pass
            return dlg

        self.open_or_raise_tool_window(
            "manager:staff_permissions",
            "Yetki Yönetimi",
            factory,
        )

    def open_user_management(self):
        if not self.require_permission_ui("manage_staff", "Kullanıcı Yönetimi"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return

        def factory():
            dlg = UserManagerDialog(self.store, self)

            def refresh_if_changed(*_args, d=dlg):
                try:
                    if getattr(d, "changed", False):
                        self.request_refresh(scope="users")
                except Exception:
                    pass

            try:
                dlg.finished.connect(refresh_if_changed)
            except Exception:
                try:
                    dlg.destroyed.connect(refresh_if_changed)
                except Exception:
                    pass
            return dlg

        self.open_or_raise_tool_window(
            "manager:users",
            "Kullanıcı Yönetimi",
            factory,
        )

    def open_staff_management(self):
        self.open_staff_permissions_dialog("staffRoles")

    def open_personnel_permissions(self):
        initial_tab = "staffRoles" if self.has_permission("manage_staff") else "rolePermissions"
        self.open_staff_permissions_dialog(initial_tab)

    def open_role_permissions(self):
        self.open_staff_permissions_dialog("rolePermissions")

    def open_delivery_schedule_report(self):
        from src.ui.dialogs.delivery_schedule_report_dialog import DeliveryScheduleReportDialog

        self.open_or_raise_tool_window(
            "report:delivery_schedule",
            "Tahmini Teslimat Takvimi",
            lambda: DeliveryScheduleReportDialog(self, store=self.store),
        )

    def open_platform_delivery_report(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Raporu açmak için önce bir STS veri dosyası açın.")
            return
        self.open_or_raise_tool_window(
            "report:platform_delivery",
            "Platform Teslimat Özeti",
            lambda: PlatformTeslimatDurumuReportDialog(self, store=self.store),
        )

    def open_usage_guide(self):
        try:
            self.open_or_raise_tool_window(
                "help:usage_guide",
                "Kullanım Kılavuzu",
                lambda: UsageGuideDialog(self),
            )
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.warning(self, "Kullanım Kılavuzu", f"Kullanım kılavuzu açılamadı:\n{exc}")

    def build(self):
        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        top=QFrame(); top.setObjectName("topbar"); tl=QHBoxLayout(top); tl.setContentsMargins(12, 8, 12, 8); tl.setSpacing(10)
        # Logo: önce SVG, yoksa ico dene
        _svg_logo = Path(__file__).parent / "src" / "ui" / "assets" / "sts_logo.svg"
        _ico_logo = app_icon_path()
        _logo_src = _svg_logo if _svg_logo.exists() else (_ico_logo if _ico_logo.exists() else None)
        if _logo_src:
            logo = QLabel(); logo.setObjectName("appLogo")
            _pix = QPixmap(str(_logo_src))
            if not _pix.isNull():
                logo.setPixmap(_pix.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setFixedSize(48, 48)
            logo.setAlignment(Qt.AlignCenter)
            tl.addWidget(logo)
        title=QLabel(APP_TITLE); title.setObjectName("appTitle"); tl.addWidget(title)
        self.connection_label=QLabel("STS bağlı değil"); self.connection_label.setObjectName("okPill"); tl.addWidget(self.connection_label)
        tl.addStretch()
        self.top_actions_btn = QToolButton()
        self.top_actions_btn.setObjectName("topMenuBtn")
        self.top_actions_btn.setText("☰")
        self.top_actions_btn.setToolTip("Menü")
        self.top_actions_btn.setPopupMode(QToolButton.InstantPopup)
        self.top_actions_menu = self._build_top_actions_menu(self.top_actions_btn)
        self.top_actions_btn.setMenu(self.top_actions_menu)
        tl.addWidget(self.top_actions_btn)
        main.addWidget(top, 0)

        self._tool_windows_by_key: Dict[str, QWidget] = {}
        self._tool_window_chip_by_key: Dict[str, QWidget] = {}
        self._active_tool_window_key = ""
        self.open_windows_strip = QFrame()
        self.open_windows_strip.setObjectName("openWindowsStrip")
        self.open_windows_strip.setFixedHeight(34)
        self.open_windows_strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.open_windows_strip.setStyleSheet("""
            QFrame#openWindowsStrip {
                background: #eef5fc;
                border: 1px solid #d7e4f2;
                border-radius: 8px;
                min-height: 30px;
                max-height: 36px;
            }
            QLabel#openWindowsLabel {
                color: #334155;
                font-weight: 800;
                font-size: 10px;
                background: transparent;
                padding-left: 2px;
                padding-right: 2px;
            }
            QScrollArea#openWindowsScroll,
            QWidget#openWindowsHost {
                background: transparent;
                border: 0;
            }
            QFrame[toolChip="true"] {
                background: #f8fbff;
                border: 1px solid #c7d7ea;
                border-radius: 8px;
                min-height: 24px;
                max-height: 28px;
            }
            QFrame[toolChip="true"][active="true"] {
                background: #dbeafe;
                border: 1px solid #2563eb;
            }
            QFrame[toolChip="true"][stale="true"] {
                background: #fff7ed;
                border: 1px solid #f59e0b;
            }
            QFrame[toolChip="true"][active="true"][stale="true"] {
                background: #ffedd5;
                border: 1px solid #ea580c;
            }
            QPushButton#toolChipTitle {
                background: transparent;
                border: 0;
                color: #0f172a;
                font-weight: 900;
                font-size: 10px;
                padding: 3px 7px;
                text-align: left;
            }
            QPushButton#toolChipTitle:hover {
                color: #003b83;
            }
            QFrame[toolChip="true"][active="true"] QPushButton#toolChipTitle {
                color: #002060;
            }
            QFrame[toolChip="true"][stale="true"] QPushButton#toolChipTitle {
                color: #92400e;
            }
            QPushButton#toolChipClose {
                background: transparent;
                border: 0;
                color: #475569;
                font-weight: 900;
                font-size: 11px;
                padding: 2px 5px;
                border-radius: 6px;
            }
            QPushButton#toolChipClose:hover {
                background: #dbeafe;
                color: #b91c1c;
            }
        """)
        open_strip_lay = QHBoxLayout(self.open_windows_strip)
        open_strip_lay.setContentsMargins(8, 3, 8, 3)
        open_strip_lay.setSpacing(5)
        label = QLabel("▣ Pencereler:")
        label.setObjectName("openWindowsLabel")
        label.setFixedHeight(24)
        open_strip_lay.addWidget(label, 0, Qt.AlignVCenter)
        self.open_windows_scroll = QScrollArea()
        self.open_windows_scroll.setObjectName("openWindowsScroll")
        self.open_windows_scroll.setWidgetResizable(True)
        self.open_windows_scroll.setFrameShape(QFrame.NoFrame)
        self.open_windows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.open_windows_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.open_windows_scroll.setFixedHeight(26)
        self.open_windows_scroll.viewport().setStyleSheet("background:transparent;border:0;")
        self.open_windows_host = QWidget()
        self.open_windows_host.setObjectName("openWindowsHost")
        self.open_windows_host.setStyleSheet("QWidget#openWindowsHost{background:transparent;border:0;}")
        self.open_windows_layout = QHBoxLayout(self.open_windows_host)
        self.open_windows_layout.setContentsMargins(0, 0, 0, 0)
        self.open_windows_layout.setSpacing(5)
        self.open_windows_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.open_windows_scroll.setWidget(self.open_windows_host)
        open_strip_lay.addWidget(self.open_windows_scroll, 1, Qt.AlignVCenter)
        self.open_windows_strip.hide()
        main.addWidget(self.open_windows_strip, 0)

        strip=QFrame(); strip.setObjectName("alertStrip"); sl=QHBoxLayout(strip); sl.setContentsMargins(12, 10, 12, 10); sl.setSpacing(10)
        today_box = QFrame(); today_box.setObjectName("todayBadge")
        today_l = QVBoxLayout(today_box); today_l.setContentsMargins(12, 8, 12, 8); today_l.setSpacing(1)
        self.today_num = QLabel(str(date.today().day)); self.today_num.setObjectName("todayDay"); self.today_num.setAlignment(Qt.AlignCenter)
        self.today_info = QLabel(""); self.today_info.setObjectName("todayInfo"); self.today_info.setAlignment(Qt.AlignCenter)
        today_l.addWidget(self.today_num); today_l.addWidget(self.today_info)
        sl.addWidget(today_box, 0)

        self.alert_divider1 = QFrame(); self.alert_divider1.setObjectName("stripDivider"); sl.addWidget(self.alert_divider1, 0)

        self.alert_overdue_group = QFrame(); self.alert_overdue_group.setObjectName("alertGroup")
        g1l = QHBoxLayout(self.alert_overdue_group); g1l.setContentsMargins(8, 6, 8, 6); g1l.setSpacing(8)
        i1 = QLabel("⚠"); i1.setObjectName("alertIconRed"); g1l.addWidget(i1)
        t1 = QVBoxLayout(); t1.setContentsMargins(0, 0, 0, 0); t1.setSpacing(0)
        self.overdue_count = QLabel("0"); self.overdue_count.setObjectName("alertCountRed")
        l1 = QLabel("GECİKEN"); l1.setObjectName("alertLabel")
        t1.addWidget(self.overdue_count); t1.addWidget(l1); g1l.addLayout(t1)
        sl.addWidget(self.alert_overdue_group, 0)

        self.alert_critical_group = QFrame(); self.alert_critical_group.setObjectName("alertGroup")
        g2l = QHBoxLayout(self.alert_critical_group); g2l.setContentsMargins(8, 6, 8, 6); g2l.setSpacing(8)
        i2 = QLabel("⏳"); i2.setObjectName("alertIconAmber"); g2l.addWidget(i2)
        t2 = QVBoxLayout(); t2.setContentsMargins(0, 0, 0, 0); t2.setSpacing(0)
        self.critical_count = QLabel("0"); self.critical_count.setObjectName("alertCountAmber")
        l2 = QLabel("60 GÜN İÇİNDE"); l2.setObjectName("alertLabel")
        t2.addWidget(self.critical_count); t2.addWidget(l2); g2l.addLayout(t2)
        sl.addWidget(self.alert_critical_group, 0)

        self.alert_divider2 = QFrame(); self.alert_divider2.setObjectName("stripDivider"); sl.addWidget(self.alert_divider2, 0)
        self.upcoming_label = QLabel("Yaklaşan:"); self.upcoming_label.setObjectName("upcomingLabel")
        sl.addWidget(self.upcoming_label, 0)
        self.upcoming_scroll = QScrollArea(); self.upcoming_scroll.setObjectName("upcomingScroll")
        self.upcoming_scroll.setWidgetResizable(True)
        self.upcoming_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.upcoming_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.upcoming_host = QWidget()
        self.upcoming_layout = QHBoxLayout(self.upcoming_host)
        self.upcoming_layout.setContentsMargins(0, 0, 0, 0)
        self.upcoming_layout.setSpacing(6)
        self.upcoming_layout.addStretch()
        self.upcoming_scroll.setWidget(self.upcoming_host)
        sl.addWidget(self.upcoming_scroll, 1)

        calb=QPushButton("🗓 Takvim Görünümü"); calb.clicked.connect(self.open_calendar_tracking); sl.addWidget(calb, 0)
        # The alert strip belongs to the real main layout; there is no embedded workspace container here.
        main.addWidget(strip, 0)

        # The main contract query body also stays on the real main layout.
        body=QHBoxLayout(); body.setSpacing(8); main.addLayout(body,1)
        left=QFrame(); left.setObjectName("panel"); left.setFixedWidth(350); lv=QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)
        platform_head = QWidget(); ph = QHBoxLayout(platform_head); ph.setContentsMargins(12, 8, 12, 8); ph.setSpacing(6)
        h=QLabel("Platformlar"); h.setObjectName("panelTitle"); ph.addWidget(h); ph.addStretch(1)
        self.platform_selection_badge = QLabel(""); self.platform_selection_badge.setObjectName("platformSelectionBadge")
        self.platform_selection_badge.setStyleSheet("QLabel{background:#dbeafe;color:#1d4ed8;border-radius:9px;padding:2px 7px;font-size:11px;font-weight:800;}")
        self.platform_selection_badge.hide(); ph.addWidget(self.platform_selection_badge)
        lv.addWidget(platform_head)
        self.platform_list=QListWidget(); self.platform_list.setObjectName("mainPlatformList"); self.platform_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.platform_list.itemClicked.connect(self.on_platform_clicked)
        self.platform_list.itemChanged.connect(self._on_platform_item_changed)
        self.platform_list.customContextMenuRequested.connect(self._on_platform_context_menu_requested)
        self._platform_list_delegate = PlatformListDelegate(self.platform_list)
        self.platform_list.setItemDelegate(self._platform_list_delegate)
        lv.addWidget(self.platform_list,1)
        self.platform_info_bar = QFrame(); self.platform_info_bar.setObjectName("platformInfoBar")
        self.platform_info_bar.setStyleSheet("QFrame#platformInfoBar{background:#f8fbff;border-top:1px solid #dbe7f5;} QLabel{color:#64748b;font-size:11px;} QPushButton{background:transparent;border:0;color:#1d4ed8;font-size:11px;font-weight:800;padding:2px 4px;}")
        pi = QHBoxLayout(self.platform_info_bar); pi.setContentsMargins(10, 4, 8, 4); pi.setSpacing(4)
        self.platform_info_label = QLabel(""); pi.addWidget(self.platform_info_label); pi.addStretch(1)
        clear_platforms = QPushButton("temizle"); clear_platforms.clicked.connect(self.clear_platform_selection); pi.addWidget(clear_platforms)
        self.platform_info_bar.hide(); lv.addWidget(self.platform_info_bar)
        new=QPushButton("+ Yeni Sözleşme"); new.setObjectName("newContractBtn"); new.clicked.connect(self.new_contract); new.setMinimumHeight(46); lv.addWidget(new)
        body.addWidget(left, 0)

        right=QFrame(); right.setObjectName("panel"); rv=QVBoxLayout(right); rv.setContentsMargins(12, 10, 12, 10); rv.setSpacing(8)
        self.right_panel = right
        head_row = QHBoxLayout()
        self.right_title=QLabel("Sözleşme Sorgulama"); self.right_title.setObjectName("queryTitle")
        head_row.addWidget(self.right_title)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Sözleşme no, kullanıcı veya durum ara..."); self.search_input.textChanged.connect(self.schedule_apply_contract_filter)
        head_row.addWidget(self.search_input, 1)
        self.clear_col_filters_btn = QPushButton("Filtreleri Temizle")
        self.clear_col_filters_btn.setObjectName("secondary")
        self.clear_col_filters_btn.clicked.connect(self.clear_query_filters)
        head_row.addWidget(self.clear_col_filters_btn, 0)
        hint = QLabel("Sözleşmeye çift tıklayınca detay ekranı açılır."); hint.setObjectName("muted"); head_row.addWidget(hint)
        rv.addLayout(head_row)

        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filterBar")
        fb = QHBoxLayout(self.filter_bar)
        fb.setContentsMargins(8, 6, 8, 6)
        fb.setSpacing(8)
        self.filter_type = QComboBox()
        self.filter_type.addItem("Tüm Türler", "")
        self.filter_type.currentIndexChanged.connect(self.schedule_apply_contract_filter)
        fb.addWidget(self.filter_type, 0)
        self._date_from_active = False
        self._date_to_active = False
        fb.addWidget(QLabel("Sıralama:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Varsayılan", "default")
        self.sort_combo.addItem("Sözleşme No (Artan)", "no_asc")
        self.sort_combo.addItem("Sözleşme No (Azalan)", "no_desc")
        self.sort_combo.addItem("Termin Tarihi (Erken)", "date_asc")
        self.sort_combo.addItem("Termin Tarihi (Geç)", "date_desc")
        self.sort_combo.addItem("Kalan Gün (Artan)", "days_asc")
        self.sort_combo.addItem("Kalan Gün (Azalan)", "days_desc")
        self.sort_combo.addItem("Kullanıcı (A-Z)", "user_asc")
        self.sort_combo.addItem("Kullanıcı (Z-A)", "user_desc")
        self.sort_combo.currentIndexChanged.connect(self.schedule_apply_contract_filter)
        fb.addWidget(self.sort_combo, 0)
        self.clear_filters_btn = QPushButton("Temizle")
        self.clear_filters_btn.setObjectName("secondary")
        self.clear_filters_btn.clicked.connect(self.clear_query_filters)
        fb.addWidget(self.clear_filters_btn, 0)
        fb.addStretch()
        self.filter_bar.setVisible(False)
        self.contract_table=QTableWidget(0,9)
        self.contract_table.setObjectName("contractTable")
        # Yatay scroll yok — sütunlar her zaman tablo içinde kalır
        self.contract_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Excel gibi sutun filtresi
        self._filter_header = FilterableHeaderView(Qt.Horizontal, self.contract_table)
        self._filter_header.filterChanged.connect(self.schedule_apply_contract_filter)
        self.contract_table.setHorizontalHeader(self._filter_header)
        self.contract_table.setHorizontalHeaderLabels(["Platform", "Sözleşme Türü", "Sözleşme No", "Kullanıcı", "Durum", "Termin Tarihi", "Kalan Gün", "Etiketler", "Özet"])
        self.contract_table._filter_col_keys = ["platform", "type", "no", "user", "status", "date", "days", "tags", "summary"]
        self.contract_table._sort_mode = 'default'  # siralama modu
        # Tüm sütunlar Stretch — her zaman ekranı doldurur, yatay kaymaz.
        # Özet sabit 72px sağ kenarda.
        _hh = self.contract_table.horizontalHeader()
        _hh.setSectionResizeMode(QHeaderView.Stretch)    # hepsi orantılı dolar
        _hh.setSectionResizeMode(COL_SUMMARY, QHeaderView.Fixed)   # Özet sabit
        self.contract_table.setColumnWidth(COL_SUMMARY, 72)
        self.contract_table.verticalHeader().setVisible(False)
        self.contract_table.cellDoubleClicked.connect(self.open_selected_contract)
        self.contract_table.cellClicked.connect(self._on_contract_cell_clicked)
        self.contract_table.viewport().installEventFilter(self)
        rv.addWidget(self.contract_table,1)
        self.query_logo_bg = QLabel(self.contract_table)
        self.query_logo_bg.setObjectName("logoWatermark")
        self.query_logo_bg.setStyleSheet("background: transparent;")
        self.query_logo_bg.setAlignment(Qt.AlignCenter)
        # Dekoratif logo sadece arka plan davranışı göstermeli; tablo etkileşimini
        # ve hücrelerin okunabilirliğini hiçbir durumda engellememeli.
        self.query_logo_bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.query_logo_bg.hide()

        logo_opacity = QGraphicsOpacityEffect(self.query_logo_bg)
        logo_opacity.setOpacity(0.55)
        self.query_logo_bg.setGraphicsEffect(logo_opacity)
        self._query_logo_source: Optional[QPixmap] = None
        self.contract_table.verticalScrollBar().valueChanged.connect(lambda _v: self.position_query_logo_background())
        self.contract_table.horizontalScrollBar().valueChanged.connect(lambda _v: self.position_query_logo_background())
        body.addWidget(right,1)
        self.build_loading_overlay()
        self.index_progress_badge = QLabel(self.centralWidget())
        self.index_progress_badge.setObjectName("miniProgressPill")
        self.index_progress_badge.setAlignment(Qt.AlignCenter)
        self.index_progress_badge.setText("STS %0")
        self.index_progress_badge.hide()
        self.index_progress_badge.raise_()
        self._send_query_logo_to_back()

    def update_connection_badge(self, mode: str):
        m = str(mode or "").strip().lower()
        if m == "ok":
            self.connection_label.setText("✓ STS bağlı")
            self.connection_label.setProperty("status", "ok")
        elif m == "loading":
            self.connection_label.setText("STS yükleniyor")
            self.connection_label.setProperty("status", "loading")
        else:
            self.connection_label.setText("STS bağlı değil")
            self.connection_label.setProperty("status", "bad")
        st = self.connection_label.style()
        st.unpolish(self.connection_label)
        st.polish(self.connection_label)
        self.connection_label.update()

    def _tool_window_alive(self, widget: Optional[QWidget]) -> bool:
        return bool(widget is not None and qt_obj_alive(widget))

    def _refresh_tool_window_strip_visibility(self) -> None:
        if hasattr(self, "open_windows_strip"):
            self.open_windows_strip.setVisible(bool(getattr(self, "_tool_windows_by_key", {})))


    def _sync_tool_chip_style(self, key: str) -> None:
        chip = getattr(self, "_tool_window_chip_by_key", {}).get(key)
        if not qt_obj_alive(chip):
            return
        active = str(chip.property("active") or "false") == "true"
        stale = str(chip.property("stale") or "false") == "true"
        title_btn = getattr(chip, "_title_btn", None)
        if qt_obj_alive(title_btn):
            base_title = str(getattr(chip, "_base_title", "") or title_btn.toolTip() or title_btn.text() or "")
            prefix = "● " if stale else ""
            title_btn.setText(prefix + base_title)
            title_btn.setProperty("active", "true" if active else "false")
            title_btn.setProperty("stale", "true" if stale else "false")
            color = "#002060" if active else "#0f172a"
            if stale:
                color = "#92400e"
            # Direct widget stylesheet wins over broader/global QPushButton rules.
            title_btn.setStyleSheet(
                "QPushButton#toolChipTitle {"
                " background: transparent; border: 0;"
                f" color: {color};"
                " font-weight: 900; font-size: 10px;"
                " padding: 3px 7px; text-align: left;"
                "}"
                "QPushButton#toolChipTitle:hover { color: #003b83; }"
            )
            title_btn.style().unpolish(title_btn)
            title_btn.style().polish(title_btn)
            title_btn.update()
        chip.style().unpolish(chip)
        chip.style().polish(chip)
        chip.update()

    def _mark_tool_window_stale(self, key: str, stale: bool = True) -> None:
        chip = getattr(self, "_tool_window_chip_by_key", {}).get(key)
        if not qt_obj_alive(chip):
            return
        chip.setProperty("stale", "true" if stale else "false")
        self._sync_tool_chip_style(key)

    def _notify_tool_windows_data_changed(self, scope: str = "all") -> None:
        """Mark open tool windows as stale after contract/user/tag/platform data changes.

        Reports are refreshed lazily when activated if they expose a safe refresh method.
        Manager windows are only marked stale so unsaved edits are not overwritten.
        """
        for key in list(getattr(self, "_tool_windows_by_key", {}).keys()):
            self._mark_tool_window_stale(key, True)

    def _call_tool_window_refresh(self, widget: QWidget, scope: str = "all") -> bool:
        # Keep this intentionally conservative. Only no-arg/optional refresh hooks are used.
        method_names = (
            "refresh_after_data_change",
            "refresh_data",
            "refresh_preview",
            "refresh_report",
            "reload_data",
            "reload_preview",
            "reload",
            "refresh",
            "update_preview",
            "build_preview",
            "load_data",
        )
        for name in method_names:
            fn = getattr(widget, name, None)
            if not callable(fn):
                continue
            try:
                fn()
                return True
            except TypeError:
                try:
                    fn(scope)
                    return True
                except Exception:
                    continue
            except Exception:
                # Do not crash the main app because a report failed to refresh.
                traceback.print_exc()
                continue
        return False

    def _refresh_stale_tool_window(self, key: str) -> bool:
        chip = getattr(self, "_tool_window_chip_by_key", {}).get(key)
        if not qt_obj_alive(chip) or str(chip.property("stale") or "false") != "true":
            return False
        # Manager/edit-heavy windows should not auto-refresh because they may have unsaved edits.
        if str(key or "").startswith("manager:"):
            return False
        widget = getattr(self, "_tool_windows_by_key", {}).get(key)
        if not self._tool_window_alive(widget):
            self._unregister_tool_window(key)
            return False
        if self._call_tool_window_refresh(widget):
            self._mark_tool_window_stale(key, False)
            return True
        return False

    def _position_minimized_tool_windows(self) -> None:
        """Eski davranış: minimize edilen tool window başlıklarını ana pencere altına diziyordu.

        Bu davranış Windows'ta pencere geri çağrılınca pencerenin ekranın altında açılmasına
        sebep oluyordu. Tool window'lar artık gerçek ayrı pencere gibi davranır; minimize
        konumu elle taşınmaz.
        """
        return

    def _center_tool_window(self, widget: QWidget) -> None:
        """Tool window'u ana pencereye/screen'e göre güvenli şekilde ortala."""
        if not self._tool_window_alive(widget):
            return
        try:
            screen = None
            try:
                screen = widget.screen() or self.screen()
            except Exception:
                screen = None
            if screen is None:
                screen = QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()

            frame = widget.frameGeometry()
            if not frame.isValid() or frame.width() <= 80 or frame.height() <= 60:
                hint = widget.sizeHint()
                w = max(widget.width(), hint.width(), 640)
                h = max(widget.height(), hint.height(), 420)
            else:
                w = frame.width()
                h = frame.height()

            # Ana pencere görünürse onun merkezini kullan; aksi halde ekran merkezine düş.
            try:
                base_center = self.frameGeometry().center()
                if not available.contains(base_center):
                    base_center = available.center()
            except Exception:
                base_center = available.center()

            x = base_center.x() - w // 2
            y = base_center.y() - h // 2
            x = max(available.left(), min(x, available.right() - w + 1))
            y = max(available.top(), min(y, available.bottom() - h + 1))
            widget.move(x, y)
        except Exception:
            pass

    def _set_active_tool_window(self, key: str) -> None:
        self._active_tool_window_key = str(key or "")
        for item_key, chip in list(getattr(self, "_tool_window_chip_by_key", {}).items()):
            if chip is None:
                continue
            active = item_key == self._active_tool_window_key
            self._apply_tool_chip_visual(chip, active)

    def _tool_chip_frame_style(self, active: bool = False) -> str:
        if active:
            return "QFrame#toolWindowChip{background:#dbeafe;border:1px solid #2563eb;border-radius:8px;}"
        return "QFrame#toolWindowChip{background:#f8fbff;border:1px solid #c7d7ea;border-radius:8px;}"

    def _tool_chip_title_style(self, active: bool = False) -> str:
        color = "#0f172a"  # her zaman koyu/siyah okunaklı metin
        hover = "#1d4ed8"
        return (
            "QPushButton#toolChipTitle{background:transparent;border:0;color:" + color + ";"
            "font-size:12px;font-weight:800;padding:0 2px;text-align:left;min-height:22px;max-height:24px;}"
            "QPushButton#toolChipTitle:hover{color:" + hover + ";}"
            "QPushButton#toolChipTitle:pressed{color:#0f172a;}"
            "QPushButton#toolChipTitle:disabled{color:#0f172a;}"
        )

    def _tool_chip_close_style(self, active: bool = False) -> str:
        return (
            "QPushButton{background:transparent;border:0;color:#475569;font-size:12px;font-weight:900;"
            "padding:0 2px;min-width:18px;max-width:18px;}"
            "QPushButton:hover{color:#dc2626;}"
        )

    def _tool_chip_display_text(self, title: str, max_px: int = 170) -> str:
        fm = self.fontMetrics()
        try:
            return fm.elidedText(str(title or ""), Qt.ElideRight, max_px)
        except Exception:
            t = str(title or "")
            return t if len(t) <= 24 else (t[:21] + "...")

    def _apply_tool_chip_visual(self, chip: QWidget, active: bool = False) -> None:
        if chip is None:
            return
        try:
            chip.setProperty("active", "true" if active else "false")
        except Exception:
            pass
        try:
            chip.setStyleSheet(self._tool_chip_frame_style(active))
        except Exception:
            pass
        title_btn = chip.findChild(QPushButton, "toolChipTitle")
        close_btn = chip.findChild(QPushButton, "toolChipClose")
        full_title = chip.property("fullTitle") if hasattr(chip, 'property') else None
        full_title = str(full_title or "")
        if title_btn is not None:
            title_btn.setStyleSheet(self._tool_chip_title_style(active))
            max_px = max(110, title_btn.width() or 170)
            shown = self._tool_chip_display_text(full_title or title_btn.text(), max_px)
            title_btn.setText(shown)
            title_btn.setToolTip(full_title or shown)
        if close_btn is not None:
            close_btn.setStyleSheet(self._tool_chip_close_style(active))
        st = chip.style()
        if st is not None:
            try:
                st.unpolish(chip)
                st.polish(chip)
            except Exception:
                pass
        chip.update()

    def _prepare_tool_window(self, widget: QWidget) -> QWidget:
        try:
            # Tool window'lar ana pencereye gömülü/minimize başlığı gibi davranmasın;
            # gerçek bağımsız top-level pencere olsun. Referansı MainWindow registry tutuyor.
            try:
                widget.setParent(None)
            except Exception:
                pass
            if isinstance(widget, QDialog):
                widget.setModal(False)
                widget.setWindowModality(Qt.NonModal)
                try:
                    widget.setSizeGripEnabled(True)
                except Exception:
                    pass
            flags = (
                Qt.Window
                | Qt.WindowTitleHint
                | Qt.WindowSystemMenuHint
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
                | Qt.WindowCloseButtonHint
            )
            widget.setWindowFlags(flags)
            widget.setAttribute(Qt.WA_DeleteOnClose, True)
            widget.installEventFilter(self)
        except Exception:
            pass
        return widget
    def _create_tool_window_chip(self, key: str, title: str) -> QWidget:
        chip = QFrame()
        chip.setProperty("toolChip", "true")
        chip.setProperty("active", "false")
        chip.setProperty("stale", "false")
        chip.setProperty("fullTitle", str(title or ""))
        chip.setObjectName("toolWindowChip")
        chip.setMinimumHeight(26)
        chip.setMaximumHeight(30)
        chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        chip.setStyleSheet(self._tool_chip_frame_style(False))

        lay = QHBoxLayout(chip)
        lay.setContentsMargins(10, 3, 7, 3)
        lay.setSpacing(6)

        full_title = str(title or "")
        metrics = QFontMetrics(self.font())
        title_px = max(118, min(metrics.horizontalAdvance(full_title) + 18, 240))
        chip_px = title_px + 32
        chip.setMinimumWidth(chip_px)
        chip.setMaximumWidth(chip_px)

        title_btn = QPushButton(self._tool_chip_display_text(full_title, title_px))
        title_btn.setObjectName("toolChipTitle")
        title_btn.setFlat(True)
        title_btn.setCursor(Qt.PointingHandCursor)
        title_btn.setToolTip(full_title)
        title_btn.setMinimumWidth(title_px)
        title_btn.setMaximumWidth(title_px)
        title_btn.setMinimumHeight(22)
        title_btn.setMaximumHeight(24)
        title_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title_btn.setStyleSheet(self._tool_chip_title_style(False))
        title_btn.clicked.connect(lambda _checked=False, k=key: self.raise_tool_window(k))

        close_btn = QPushButton("×")
        close_btn.setObjectName("toolChipClose")
        close_btn.setFlat(True)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Pencereyi kapat")
        close_btn.setMinimumSize(18, 20)
        close_btn.setMaximumSize(20, 22)
        close_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        close_btn.setStyleSheet(self._tool_chip_close_style(False))
        close_btn.clicked.connect(lambda _checked=False, k=key: self.close_tool_window(k))

        lay.addWidget(title_btn, 1, Qt.AlignVCenter)
        lay.addWidget(close_btn, 0, Qt.AlignVCenter)

        # ÖNEMLİ: Görünen layout self.open_windows_layout'tır.
        # open_windows_row_layout diye bir alan yoksa chip kayıtlı kalıp ekranda görünmez.
        target_layout = getattr(self, "open_windows_layout", None)
        if target_layout is not None:
            target_layout.addWidget(chip, 0, Qt.AlignVCenter)
            try:
                self.open_windows_host.adjustSize()
                self.open_windows_host.updateGeometry()
                self.open_windows_scroll.updateGeometry()
            except Exception:
                pass

        self._tool_window_chip_by_key[key] = chip
        self._refresh_tool_window_strip_visibility()
        self._apply_tool_chip_visual(chip, key == getattr(self, "_active_tool_window_key", ""))
        return chip

    def _unregister_tool_window(self, key: str) -> None:
        widget = getattr(self, "_tool_windows_by_key", {}).pop(key, None)
        chip = getattr(self, "_tool_window_chip_by_key", {}).pop(key, None)
        if self._active_tool_window_key == key:
            self._active_tool_window_key = ""
        if self._tool_window_alive(widget):
            try:
                widget.removeEventFilter(self)
            except Exception:
                pass
        if qt_obj_alive(chip):
            try:
                self.open_windows_layout.removeWidget(chip)
                chip.deleteLater()
            except Exception:
                pass
        self._refresh_tool_window_strip_visibility()
        if self._active_tool_window_key:
            self._set_active_tool_window(self._active_tool_window_key)

    def raise_tool_window(self, key: str) -> Optional[QWidget]:
        widget = getattr(self, "_tool_windows_by_key", {}).get(key)
        if not self._tool_window_alive(widget):
            self._unregister_tool_window(key)
            return None
        try:
            was_minimized = bool(widget.isMinimized())
            was_hidden = not bool(widget.isVisible())
            if was_minimized:
                widget.showNormal()
            elif was_hidden:
                widget.show()
            self._refresh_stale_tool_window(key)

            def _finish_raise(w=widget, center=(was_minimized or was_hidden)):
                if not self._tool_window_alive(w):
                    return
                if center:
                    self._center_tool_window(w)
                w.raise_()
                w.activateWindow()

            QTimer.singleShot(0, _finish_raise)
        except Exception:
            pass
        self._set_active_tool_window(key)
        return widget

    def open_or_raise_tool_window(self, key: str, title: str, factory: Callable[[], QWidget]) -> QWidget:
        existing = getattr(self, "_tool_windows_by_key", {}).get(key)
        if self._tool_window_alive(existing):
            return self.raise_tool_window(key) or existing
        if existing is not None:
            self._unregister_tool_window(key)

        widget = self._prepare_tool_window(factory())
        self._tool_windows_by_key[key] = widget
        self._create_tool_window_chip(key, title)
        try:
            widget.destroyed.connect(lambda *_args, k=key: self._unregister_tool_window(k))
        except Exception:
            pass
        try:
            widget.show()

            def _finish_open(w=widget):
                if not self._tool_window_alive(w):
                    return
                self._center_tool_window(w)
                w.raise_()
                w.activateWindow()

            QTimer.singleShot(0, _finish_open)
        except Exception:
            pass
        self._set_active_tool_window(key)
        return widget

    def close_tool_window(self, key: str) -> bool:
        widget = getattr(self, "_tool_windows_by_key", {}).get(key)
        if not self._tool_window_alive(widget):
            self._unregister_tool_window(key)
            return True
        try:
            closed = bool(widget.close())
        except Exception:
            return False
        if closed:
            self._unregister_tool_window(key)
        return closed

    def close_all_tool_windows(self) -> bool:
        for key in list(getattr(self, "_tool_windows_by_key", {}).keys()):
            if not self.close_tool_window(key):
                return False
        return True

    def _excel_file_signature(self):
        try:
            path = Path(getattr(self.store, "path", self.path))
            st = path.stat()
            return (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))
        except Exception:
            return None

    def _remember_version_baseline(self) -> None:
        self._version_baseline_signature = self._excel_file_signature()

    def _workbook_changed_since_load(self) -> bool:
        baseline = getattr(self, "_version_baseline_signature", None)
        current = self._excel_file_signature()
        return bool(baseline and current and current != baseline)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Kapanışta değişiklik varsa dosya adını standart versiyon formatına taşır."""
        if self._sts_operation_running():
            QMessageBox.information(self, "Yükleme sürüyor", "STS dosyası açılırken lütfen işlemin tamamlanmasını bekleyin.")
            event.ignore()
            return
        if hasattr(self, "open_windows_strip") and not self.close_all_tool_windows():
            event.ignore()
            return
        if getattr(self, "store", None) and self._workbook_changed_since_load():
            try:
                # STS dosyalarında tek aktif dosya korunur: mevcut dosya yeniden adlandırılır.
                if self.is_sts_mode():
                    new_path = rename_sts_file_to_next_version(self.store, getattr(self.store, "path", self.path))
                    if new_path:
                        self.path = Path(new_path)
                        self._remember_version_baseline()
            except Exception:
                pass
        super().closeEvent(event)

    def build_loading_overlay(self):
        self.loading_overlay = QFrame(self.centralWidget())
        self.loading_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.82); }")
        self.loading_overlay.hide()
        self.loading_overlay.raise_()

        self.loading_card = QFrame(self.loading_overlay)
        self.loading_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.96); border: 1px solid #d8e2ed; border-radius: 12px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(self.loading_card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)
        self.loading_label = QLabel("Analiz ediliyor...")
        self.loading_label.setObjectName("mainTitle")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 100)
        self.loading_progress.setValue(0)
        self.loading_progress.setTextVisible(True)
        self.loading_progress.setFormat("%p%")
        lay.addWidget(self.loading_label)
        lay.addWidget(self.loading_progress)

    def position_loading_overlay(self):
        if not hasattr(self, "loading_overlay"):
            return
        parent = self.centralWidget()
        if not parent:
            return
        self.loading_overlay.setGeometry(parent.rect())
        w, h = 460, 150
        x = max((self.loading_overlay.width() - w) // 2, 0)
        y = max((self.loading_overlay.height() - h) // 2, 0)
        self.loading_card.setGeometry(x, y, w, h)
        self.loading_overlay.raise_()

    def position_query_logo_background(self):
        """Sorgulama tablosunda sadece seçili platform logolarını watermark olarak konumlandırır.

        Platform seçimi yoksa varsayılan/Baykar logosu gösterilmez.
        """
        try:
            if not hasattr(self, "query_logo_bg") or not hasattr(self, "contract_table"):
                return

            if not getattr(self, "_query_logo_source", None) or self._query_logo_source.isNull():
                self.query_logo_bg.clear()
                self.query_logo_bg.hide()
                return

            vp = self.contract_table.viewport()
            rect = vp.geometry()

            if rect.width() <= 0 or rect.height() <= 0:
                self.query_logo_bg.hide()
                return

            max_w = int(rect.width() * 0.82)
            max_h = int(rect.height() * 0.62)
            source = self._query_logo_source

            # Logo tablo alanından büyükse küçült; küçükse olduğu gibi bırak.
            if source.width() > max_w or source.height() > max_h:
                scaled = source.scaled(
                    QSize(max_w, max_h),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            else:
                scaled = source

            x = max(rect.x() + (rect.width() - scaled.width()) // 2, 0)
            y = max(rect.y() + (rect.height() - scaled.height()) // 2, 0)

            self.query_logo_bg.setGeometry(x, y, scaled.width(), scaled.height())
            self.query_logo_bg.setPixmap(scaled)
            self.query_logo_bg.show()
            self._send_query_logo_to_back()
        except Exception:
            try:
                if hasattr(self, "query_logo_bg"):
                    self.query_logo_bg.clear()
                    self.query_logo_bg.hide()
            except Exception:
                pass

    def _scale_logo_smart(
        self,
        px: QPixmap,
        max_size: QSize,
        max_upscale: float = 3.0
    ) -> QPixmap:
        """
        Küçük logoları en fazla max_upscale kadar büyütür.
        Büyük logoları max_size içine sığacak şekilde küçültür.
        Oranı her zaman korur.
        """
        if not px or px.isNull():
            return px

        ow = max(px.width(), 1)
        oh = max(px.height(), 1)

        fit_scale = min(
            max_size.width() / ow,
            max_size.height() / oh
        )

        if fit_scale < 1:
            # Logo zaten büyükse küçült.
            scale = fit_scale
        else:
            # Logo küçükse en fazla 3 kat büyüt.
            scale = min(fit_scale, max_upscale)

        nw = max(1, int(ow * scale))
        nh = max(1, int(oh * scale))

        if nw == ow and nh == oh:
            return px

        return px.scaled(
            QSize(nw, nh),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

    def _has_permission_context(self) -> bool:
        return bool(self.current_staff and self.is_sts_mode())

    def _permission_action_visible(self, permission_code: str) -> bool:
        # Excel/başlangıç modunda personel oturumu yoktur; menü öğelerini saklamak
        # kullanıcıda "menüden silinmiş" hissi yaratır. Gerçek STS oturumu varsa
        # görünürlük merkezi has_permission kontrolüyle belirlenir.
        if not self._has_permission_context():
            return True
        return self.has_permission(permission_code)

    def _is_admin_staff(self) -> bool:
        return bool(self.current_staff and (self.current_staff or {}).get("is_admin"))

    def _refresh_permission_actions(self):
        is_admin = self._is_admin_staff()
        if hasattr(self, "user_management_action"):
            self.user_management_action.setVisible(
                is_admin or self._permission_action_visible("manage_staff")
            )
        if hasattr(self, "platform_component_action"):
            self.platform_component_action.setVisible(
                is_admin or self._permission_action_visible("manage_platforms")
            )
        if hasattr(self, "tag_management_action"):
            self.tag_management_action.setVisible(
                is_admin or self._permission_action_visible("manage_labels")
            )
        if hasattr(self, "role_permissions_action"):
            self.role_permissions_action.setVisible(
                is_admin
                and (
                    self._permission_action_visible("manage_staff")
                    or self._permission_action_visible("manage_roles")
                )
            )
        if hasattr(self, "activity_logs_action"):
            self.activity_logs_action.setVisible(
                is_admin and self._permission_action_visible("view_action_history")
            )
        if hasattr(self, "system_menu_action"):
            self.system_menu_action.setVisible(is_admin)

    def _add_menu_action(self, menu: QMenu, title: str, callback):
        return menu.addAction(title, callback)

    def _build_top_actions_menu(self, parent) -> QMenu:
        menu = QMenu(parent)
        menu.setObjectName("topActionsMenu")

        file_menu = menu.addMenu("Dosya İşlemleri")
        self._add_menu_action(file_menu, "STS Dosyasını Değiştir", self.open_file)
        self._add_menu_action(file_menu, "Excel’e Aktar", self.export_sts_to_excel)

        reports_menu = menu.addMenu("Raporlar")
        self._add_menu_action(reports_menu, "Tahmini Teslimat Takvimi", self.open_delivery_schedule_report)
        self._add_menu_action(reports_menu, "Platform Teslimat Özeti", self.open_platform_delivery_report)

        management_menu = menu.addMenu("Yönetim")
        self.platform_component_action = self._add_menu_action(management_menu, "Platform / Bileşen Yönetimi", self.manage_platforms)
        self.user_management_action = self._add_menu_action(management_menu, "Kullanıcı Yönetimi", self.open_user_management)
        self.role_permissions_action = self._add_menu_action(management_menu, "Yetki Yönetimi", self.open_personnel_permissions)
        self.tag_management_action = self._add_menu_action(management_menu, "Etiket Yönetimi", self.manage_tags)

        self.system_menu = menu.addMenu("Sistem")
        self.system_menu_action = self.system_menu.menuAction()
        self._add_menu_action(self.system_menu, "Veritabanı Yönetimi", self.open_database_management)
        self._add_menu_action(self.system_menu, "Performans İzleme", self.open_performance_tracking)
        self.activity_logs_action = self._add_menu_action(self.system_menu, "İşlem Geçmişi", self.open_activity_logs)

        help_menu = menu.addMenu("Yardım")
        self._add_menu_action(help_menu, "Kullanım Kılavuzu", self.open_usage_guide)

        menu.aboutToShow.connect(self._refresh_permission_actions)
        self._refresh_permission_actions()
        return menu

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_loading_overlay()
        self.position_query_logo_background()
        self.position_index_progress_badge()

    def position_index_progress_badge(self):
        if not hasattr(self, "index_progress_badge"):
            return
        parent = self.centralWidget()
        if not parent:
            return
        w, h = 138, 30
        margin = 12
        x = max(parent.width() - w - margin, 0)
        y = max(parent.height() - h - margin, 0)
        self.index_progress_badge.setGeometry(x, y, w, h)
        self.index_progress_badge.raise_()

    def set_index_progress_badge(self, visible: bool, percent: int = 0):
        if not hasattr(self, "index_progress_badge"):
            return
        p = int(max(0, min(100, int(percent or 0))))
        self.index_progress_badge.setText(f"STS indeks %{p}")
        self.position_index_progress_badge()
        self.index_progress_badge.setVisible(bool(visible))

    def eventFilter(self, obj, event):
        # PySide6: Qt'nin C++ tarafından çağırdığı Python override'larında
        # yakalanmamış hata uygulamayı doğrudan abort ettirebilir. Bu filtre
        # QApplication seviyesine kurulu olduğu için export sırasında açılan/kapanan
        # dialoglar dahil tüm objelerin event'leri buradan geçer. Bu yüzden burada
        # silinmiş C++ objelere ve tüm yardımcı çağrılara karşı savunmalı davranıyoruz.
        try:
            if not qt_obj_alive(obj) or event is None:
                return False

            try:
                etype = event.type()
            except Exception:
                return False

            if etype == QEvent.WindowActivate:
                for key, widget in list(getattr(self, "_tool_windows_by_key", {}).items()):
                    if obj is widget:
                        self._set_active_tool_window(key)
                        self._refresh_stale_tool_window(key)
                        break

            if etype == QEvent.WindowStateChange:
                # Minimize edilen tool window'ların konumunu elle alta taşımıyoruz.
                # Böylece chip'ten geri çağrıldığında pencere ekran altında açılmaz.
                pass

            contract_viewport = None
            try:
                table = getattr(self, "contract_table", None)
                if qt_obj_alive(table):
                    contract_viewport = table.viewport()
            except Exception:
                contract_viewport = None

            if obj is contract_viewport and etype in (QEvent.Resize, QEvent.Move, QEvent.Show):
                QTimer.singleShot(0, self.position_query_logo_background)

            side_host = getattr(self, "side_meta_host", None)
            if obj is side_host and etype in (QEvent.Resize, QEvent.Show):
                self.position_side_meta_popover()

            _editing = (
                getattr(self, "_tree_editing", False)
                or getattr(self, "_file_dialog_open", False)
                or getattr(self, "_side_meta_modal_open", False)
            )
            panel_open = bool(getattr(self, "_side_meta_open_panel", None))

            if etype in (QEvent.WindowDeactivate, QEvent.ApplicationDeactivate) and panel_open and not _editing:
                self.close_side_meta_popover()

            if etype == QEvent.MouseButtonPress and panel_open:
                if not _editing and not self._is_side_meta_inside_click(obj, event):
                    self.close_side_meta_popover()

            if etype == QEvent.MouseButtonDblClick:
                file_id = None
                try:
                    if hasattr(obj, "property"):
                        file_id = obj.property("contractFileId")
                except Exception:
                    file_id = None
                if file_id:
                    self.open_contract_file(int(file_id))
                    return True

        except Exception:
            # Event filter içinde hata dışarı kaçarsa PySide6 abort edebilir.
            # Log görünür kalsın ama uygulama kapanmasın.
            try:
                traceback.print_exc()
            except Exception:
                pass
            return False

        return False

    def _norm_tr(self, s: str) -> str:
        t = str(s or "").strip().lower()
        return t.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")

    def _contract_health(self, it: dict) -> tuple[str, str, str, str]:
        """(cls, status_label, days_text, date_txt)
        status_label = Excel'deki gercek durum.
        cls = renk siniflandirmasi icin.
        """
        status_txt = str(it.get("status", "") or "").strip()
        if "_near_delivery_txt" in it:
            date_txt = str(it.get("_near_delivery_txt") or "")
        else:
            date_txt = ""
        days_text = str(it.get("_near_delivery_days") or "")
        today_iso = date.today().isoformat()
        cache_key = (status_txt, date_txt, days_text, today_iso)
        if it.get("_health_cache_key") == cache_key and "_health_cache_value" in it:
            return it["_health_cache_value"]
        day_num = it.get("_day_num")
        timing_kind = ""
        # Siniflandirma (renk ve uyari listeleri icin). Tamamlanmis gec
        # teslimatlar kirmizi gorunur ancak aktif gecikme uyarilarina girmez.
        if timing_kind == "gecikmeli_teslim":
            cls = "gecikmeli_teslim"
        elif is_completed_status(status_txt):
            cls = "tamamlandi"
        elif day_num is not None:
            cls = "geciken" if day_num < 0 else ("kritik" if day_num <= 60 else "normal")
        else:
            cls = "normal"
        # Gosterilecek etiket: Excel'deki gercek durum degeri
        st_label = status_txt if status_txt else "—"
        result = (cls, st_label, days_text, date_txt)
        it["_health_cache_key"] = cache_key
        it["_health_cache_value"] = result
        return result

    def _platform_logo_pixmap(self, platform: str, size: Optional[QSize] = None) -> Optional[QPixmap]:
        if not self.store:
            return None

        raw = self.store.get_platform_logo_bytes(platform)
        if not raw:
            return None

        px = QPixmap()
        if not px.loadFromData(raw):
            return None

        if size:
            return self._scale_logo_smart(px, size, max_upscale=3.0)

        return px

    def _send_query_logo_to_back(self) -> None:
        """Keep the decorative platform logo behind the contract table viewport."""
        try:
            if not hasattr(self, "query_logo_bg") or not hasattr(self, "contract_table"):
                return
            self.query_logo_bg.lower()
            viewport = self.contract_table.viewport()
            if viewport is not None:
                self.query_logo_bg.stackUnder(viewport)
            self.query_logo_bg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass

    def _build_query_logo_strip(self, platforms: List[str]) -> Optional[QPixmap]:
        logos: List[QPixmap] = []

        for p in platforms:
            raw = self._platform_logo_pixmap(p)

            if not raw or raw.isNull():
                continue

            # Küçük logo en fazla 3 kat büyür.
            # Büyük logo bu kutuya sığacak kadar küçülür.
            px = self._scale_logo_smart(
                raw,
                QSize(900, 300),
                max_upscale=3.0
            )

            if px and not px.isNull():
                logos.append(px)

        if not logos:
            return None

        spacing = 36
        padding_x = 30
        padding_y = 20

        width = sum(px.width() for px in logos) + spacing * (len(logos) - 1) + padding_x * 2
        height = max(px.height() for px in logos) + padding_y * 2

        canvas = QPixmap(width, height)
        canvas.fill(Qt.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        x = padding_x
        for px in logos:
            y = (height - px.height()) // 2
            painter.drawPixmap(x, y, px)
            x += px.width() + spacing

        painter.end()
        return canvas

    def update_query_logo_background(self, selected_platform: Optional[str] = None):
        """Sorgulama tablosu watermark kontrolü.

        - Platform seçiliyse: o platformun / seçili platformların gömülü logosu gösterilir.
        - Platform seçimi yoksa: varsayılan Baykar/STS logosu gösterilmez.
        """
        try:
            if not hasattr(self, "query_logo_bg"):
                return

            if not self.store:
                self._query_logo_source = None
                self.query_logo_bg.hide()
                self.query_logo_bg.clear()
                return

            targets: List[str] = []

            if isinstance(selected_platform, (list, tuple, set)):
                targets = [str(p).strip() for p in selected_platform if str(p or "").strip()]
            elif selected_platform:
                targets = [str(selected_platform).strip()]
            else:
                # _apply_platform_selection çoklu seçimde None gönderebilir.
                # Bu durumda seçili platform seti varsa onların logolarını göster;
                # gerçekten hiç seçim yoksa varsayılan logo gösterme.
                current_selected = list(getattr(self, "selected_platforms", set()) or [])
                targets = [str(p).strip() for p in current_selected if str(p or "").strip()]

            # Dekoratif logo yalnızca tek platform seçiliyken gösterilir. Çoklu seçim,
            # tüm platformlar veya genel görünümde tabloyu kapatabilecek watermark yoktur.
            if len(set(targets)) != 1:
                self._query_logo_source = None
                self.query_logo_bg.hide()
                self.query_logo_bg.clear()
                return

            # Sıralama sabit kalsın; soldaki platform listesi sırası varsa onu kullan.
            try:
                order = {name: i for i, name in enumerate(self._all_platform_names())}
                targets = sorted(set(targets), key=lambda x: order.get(x, 9999))
            except Exception:
                targets = sorted(set(targets))

            strip = self._build_query_logo_strip(targets)
            if not strip or strip.isNull():
                self._query_logo_source = None
                self.query_logo_bg.hide()
                self.query_logo_bg.clear()
                return

            self._query_logo_source = strip
            self.position_query_logo_background()
        except Exception:
            try:
                self._query_logo_source = None
                if hasattr(self, "query_logo_bg"):
                    self.query_logo_bg.hide()
                    self.query_logo_bg.clear()
            except Exception:
                pass

    def _set_platform_items(self, platforms: List[str]):
        available = {str(p) for p in platforms}
        self.selected_platforms.intersection_update(available)
        if not self.selected_platforms:
            self.multi_platform_mode = False
        self._updating_platform_list = True
        try:
            self.platform_list.clear()
            counts: Dict[str, int] = {}
            for it in self.contract_index:
                p = str(it.get("platform", ""))
                counts[p] = counts.get(p, 0) + 1
            for i, p in enumerate(platforms):
                platform = str(p)
                row = QListWidgetItem(platform)
                row.setData(Qt.UserRole, platform)
                row.setSizeHint(QSize(0, 46))
                self.platform_list.addItem(row)
                if hasattr(self, "_platform_list_delegate"):
                    self._platform_list_delegate.set_count(i, counts.get(platform, 0))
        finally:
            self._updating_platform_list = False
        self.refresh_platform_list_ui()

    def _all_platform_names(self) -> List[str]:
        return [
            str(self.platform_list.item(i).data(Qt.UserRole) or "")
            for i in range(self.platform_list.count())
            if str(self.platform_list.item(i).data(Qt.UserRole) or "")
        ]

    def normalize_platform_selection_state(self):
        if not self.selected_platforms:
            self.multi_platform_mode = False

    def refresh_platform_list_ui(self):
        self.normalize_platform_selection_state()
        self._updating_platform_list = True
        try:
            for i in range(self.platform_list.count()):
                item = self.platform_list.item(i)
                platform = str(item.data(Qt.UserRole) or "")
                flags = item.flags()
                if self.multi_platform_mode:
                    item.setFlags(flags | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if platform in self.selected_platforms else Qt.Unchecked)
                else:
                    item.setData(Qt.CheckStateRole, None)
                    item.setFlags(flags & ~Qt.ItemIsUserCheckable)
                is_selected = platform in self.selected_platforms
                item.setData(PLATFORM_SELECTED_ROLE, is_selected)
                item.setSelected(is_selected)
        finally:
            self._updating_platform_list = False
        count = len(self.selected_platforms)
        self.platform_list.viewport().update()
        self.platform_selection_badge.setText(f"{count} seçili")
        self.platform_selection_badge.setVisible(count > 0)
        self.platform_info_label.setText(f"{count} platform · sağ tık ile düzenle")
        self.platform_info_bar.setVisible(count > 0)

    def _apply_platform_selection(self):
        self.normalize_platform_selection_state()
        selected = set(self.selected_platforms)
        self.all_contract_rows = [
            dict(it) for it in self.contract_index
            if not selected or str(it.get("platform", "")) in selected
        ]
        self._prepare_contract_row_cache(self.all_contract_rows)
        self._refresh_query_filters()
        if not selected:
            self.right_title.setText("Sözleşme Sorgulama")
            self.update_query_logo_background(None)
        elif len(selected) == 1:
            platform = next(iter(selected))
            self.right_title.setText(f"{platform} - Sözleşmeler")
            self.update_query_logo_background(platform)
        else:
            self.right_title.setText(f"{len(selected)} Platform - Sözleşmeler")
            self.update_query_logo_background(None)
        self.refresh_platform_list_ui()
        self.schedule_apply_contract_filter()

    def on_platform_clicked(self, item: QListWidgetItem):
        platform = str(item.data(Qt.UserRole) or "")
        if not platform:
            return
        if self.multi_platform_mode:
            if self._platform_checkbox_changed == platform:
                self._platform_checkbox_changed = None
            else:
                self.toggle_platform_multi(platform)
        elif self.selected_platforms == {platform}:
            self.clear_platform_selection()
        else:
            self.selected_platforms = {platform}
            self._apply_platform_selection()

    def _on_platform_item_changed(self, item: QListWidgetItem):
        if self._updating_platform_list or not self.multi_platform_mode:
            return
        platform = str(item.data(Qt.UserRole) or "")
        checked = item.checkState() == Qt.Checked
        if checked != (platform in self.selected_platforms):
            self._platform_checkbox_changed = platform
            QTimer.singleShot(0, lambda p=platform: self._clear_platform_checkbox_marker(p))
            self.toggle_platform_multi(platform)

    def _clear_platform_checkbox_marker(self, platform: str):
        if self._platform_checkbox_changed == platform:
            self._platform_checkbox_changed = None

    def _on_platform_context_menu_requested(self, pos: QPoint):
        item = self.platform_list.itemAt(pos)
        if item:
            self.show_platform_context_menu(str(item.data(Qt.UserRole) or ""), self.platform_list.viewport().mapToGlobal(pos))

    def show_platform_context_menu(self, platform: str, global_pos: QPoint):
        if not platform:
            return
        menu = QMenu(self)
        label = "− Seçimden çıkar" if platform in self.selected_platforms else "+ Çoklu seçime ekle"
        menu.addAction(label, lambda: self.toggle_platform_multi(platform))
        menu.addAction("☑ Tümünü seç", self.select_all_platforms)
        menu.addAction("× Seçimi temizle", self.clear_platform_selection)
        menu.exec(global_pos)

    def toggle_platform_multi(self, platform: str):
        self.multi_platform_mode = True
        if platform in self.selected_platforms:
            self.selected_platforms.remove(platform)
        else:
            self.selected_platforms.add(platform)
        self.normalize_platform_selection_state()
        self._apply_platform_selection()

    def select_all_platforms(self):
        self.selected_platforms = set(self._all_platform_names())
        self.multi_platform_mode = bool(self.selected_platforms)
        self._apply_platform_selection()

    def clear_platform_selection(self):
        self.selected_platforms.clear()
        self.multi_platform_mode = False
        self._updating_platform_list = True
        try:
            for i in range(self.platform_list.count()):
                item = self.platform_list.item(i)
                item.setCheckState(Qt.Unchecked)
                item.setData(PLATFORM_SELECTED_ROLE, False)
                item.setSelected(False)
        finally:
            self._updating_platform_list = False
        self._apply_platform_selection()

    def _clear_upcoming_layout(self):
        while self.upcoming_layout.count():
            item = self.upcoming_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def update_alert_strip(self):
        today = date.today()
        self.today_num.setText(str(today.day))
        self.today_info.setText(f"{TR_MONTHS[today.month - 1].upper()}\n{today.year}")

        overdue = []
        critical = []
        for it in self.contract_index:
            ctype = self._norm_tr(str(it.get("type", "") or ""))
            if ctype != self._norm_tr("Ana Sözleşme"):
                continue
            cls, _st, kgun, _dt = self._contract_health(it)
            if cls == "geciken":
                overdue.append((it, kgun))
            elif cls == "kritik":
                critical.append((it, kgun))
        self.overdue_count.setText(str(len(overdue)))
        self.critical_count.setText(str(len(critical)))

        show_overdue = len(overdue) > 0
        show_critical = len(critical) > 0
        self.alert_overdue_group.setVisible(show_overdue)
        self.alert_critical_group.setVisible(show_critical)
        self.alert_divider1.setVisible(show_overdue or show_critical)
        self.alert_divider2.setVisible(show_overdue or show_critical)

        self._clear_upcoming_layout()
        upcoming = overdue[:5] + critical[:10]
        for it, kgun in upcoming:
            p = str(it.get("platform", "") or "")
            no = str(it.get("no", "") or "")
            cls, _st, _kg, _dt = self._contract_health(it)
            b = QPushButton(f"• #{no} · {p} · {kgun}")
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("kind", "red" if cls == "geciken" else "amber")
            b.setObjectName("upcomingPill")
            b.clicked.connect(lambda _=False, item=dict(it): self.open_contract_item(item))
            self.upcoming_layout.addWidget(b)
        self.upcoming_layout.addStretch()

    def set_empty_state(self):
        self.platform_list.clear()
        self.selected_platforms.clear()
        self.multi_platform_mode = False
        if hasattr(self, "platform_selection_badge"):
            self.refresh_platform_list_ui()
        self.all_contract_rows = []
        self.contract_table.setRowCount(0)
        self.set_index_progress_badge(False, 0)
        self.overdue_count.setText("0")
        self.critical_count.setText("0")
        self.alert_overdue_group.hide()
        self.alert_critical_group.hide()
        self.alert_divider1.hide()
        self.alert_divider2.hide()
        self._clear_upcoming_layout()
        self.upcoming_layout.addStretch()
        self.right_title.setText("Sözleşme Sorgulama")
        self.update_query_logo_background(None)
        self.update_connection_badge("bad")

    def set_loading_state(self, loading: bool, message: str = "Analiz ediliyor..."):
        self._loading = loading
        if loading:
            self.loading_label.setText(message)
            self.loading_progress.setRange(0, 100)
            self.loading_progress.setValue(0)
            self.position_loading_overlay()
            self.loading_overlay.show()
            self.update_connection_badge("loading")
        else:
            self.loading_progress.setValue(100)
            self.loading_overlay.hide()
            self.update_connection_badge("ok" if self.store else "bad")

    def set_busy_overlay(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if getattr(self, "_set_busy_overlay_running", False):
            return
        self._set_busy_overlay_running = True
        try:
            # Excel worker yüklemesi yokken kısa/orta süreli senkron işlemlerde kullan.
            if not hasattr(self, "_busy_cursor_on"):
                self._busy_cursor_on = False
            if visible:
                self.loading_label.setText(message)
                self.loading_progress.setRange(0, 100)
                self.loading_progress.setValue(int(max(0, min(100, percent))))
                self.position_loading_overlay()
                self.loading_overlay.show()
                if not self._busy_cursor_on:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    self._busy_cursor_on = True
                QApplication.processEvents()
            else:
                self.loading_overlay.hide()
                if self._busy_cursor_on:
                    QApplication.restoreOverrideCursor()
                    self._busy_cursor_on = False
                QApplication.processEvents()

        finally:
            self._set_busy_overlay_running = False

    def start_sts_load(self, path: Path):
        """STS dosyasını yükler.

        Adımlar:
        1. STSLoadWorker arka planda dosya doğrulaması ve migration hazırlığı yapar.
        2. finished() sinyali gelince _on_sts_load_finished() ana thread'de
           STSStore bağlantısını yeniden açar.
        3. Sözleşme indeksi STSIndexWorker içinde ayrı/geçici connection ile
           hazırlanır ve ana thread'e yalnızca list[dict] olarak döner.

        Ana thread'de oluşturulan SQLite connection worker'a taşınmaz.
        """
        if self._sts_loader_thread and self._sts_loader_thread.isRunning():
            return
        self.path = Path(path)
        self.store = None
        self.contract_index = []
        self._tag_color_map_cache = None
        self._store_loading = True
        self._index_ready_for_use = False
        self._sts_warned_legacy_migration = False
        self.set_loading_state(True, "STS dosyası kontrol ediliyor...")

        thread = QThread(self)
        worker = STSLoadWorker(self.path)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_sts_load_progress)
        worker.finished.connect(self._on_sts_load_finished)
        worker.failed.connect(self._on_sts_load_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_sts_loader_refs)

        self._sts_loader_thread = thread
        self._sts_loader_worker = worker
        thread.start()

    def _clear_sts_loader_refs(self):
        self._sts_loader_thread = None
        self._sts_loader_worker = None

    def _clear_sts_index_refs(self):
        self._sts_index_thread = None
        self._sts_index_worker = None

    def _sts_operation_running(self) -> bool:
        for thread in (self._sts_loader_thread, self._sts_index_thread):
            if thread is not None:
                try:
                    if thread.isRunning():
                        return True
                except RuntimeError:
                    pass
        return False

    def _on_sts_load_progress(self, percent: int, message: str):
        self.set_loading_state(True, f"{message}  %{percent}")

    def _on_sts_load_finished(self):
        """Worker doğrulamayı geçti; ana store ana thread'de açılır, index ayrı worker'da hazırlanır."""
        actor = str((self.current_staff or {}).get("full_name") or "Personel")
        try:
            self.set_loading_state(True, "STS dosyası açılıyor...")
            schema_version = read_sts_schema_version(self.path)
            if schema_version is None or schema_version < CURRENT_SCHEMA_VERSION:
                self._sts_warned_legacy_migration = True
                QMessageBox.information(
                    self,
                    "STS dosyası güncellenecek",
                    "Bu STS dosyası eski sürümde oluşturulmuş. Uygulama dosyayı yeni sürüme uyarlayacak.\n\n"
                    "İşlem öncesi aynı klasöre otomatik yedek alınacaktır. "
                    "Güncellenen dosya eski uygulamalarda açılmayabilir.",
                )
            self.store = STSStore(self.path, actor=actor)
        except STSMigrationError as exc:
            _log.exception("STS migration hatası: %s", getattr(exc, "technical_detail", ""))
            backup_text = f"\n\nYedek dosya: {exc.backup_path}" if getattr(exc, "backup_path", None) else ""
            self._fail_sts_open_after_index_error(
                "STS güncelleme hatası",
                f"{exc.user_message}{backup_text}\n\nTeknik detaylar loga yazıldı.",
            )
            return
        except Exception as exc:
            _log.exception("STSStore ana-thread açılış hatası")
            self._fail_sts_open_after_index_error("STS yükleme hatası", f"STS dosyası açılamadı.\n\n{exc}")
            return
        self._start_sts_index_build()

    def _start_sts_index_build(self):
        if self._sts_index_thread and self._sts_index_thread.isRunning():
            return
        self.set_loading_state(True, "Sözleşme indeksi hazırlanıyor...")
        thread = QThread(self)
        worker = STSIndexWorker(self.path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_sts_index_progress)
        worker.finished.connect(self._on_sts_index_finished)
        worker.failed.connect(self._on_sts_index_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_sts_index_refs)
        self._sts_index_thread = thread
        self._sts_index_worker = worker
        thread.start()

    def _on_sts_index_progress(self, message: str):
        self.set_loading_state(True, str(message or "Sözleşme indeksi hazırlanıyor..."))

    def _on_sts_index_finished(self, index_rows):
        if not self.store:
            self._fail_sts_open_after_index_error(
                "STS yükleme hatası",
                "STS dosyası açıldı ancak ana bağlantı hazır olmadığı için sözleşme indeksi uygulanamadı.",
            )
            return
        self.contract_index = [dict(row) for row in list(index_rows or [])]
        self._tag_color_map_cache = None
        self._store_loading = False
        self._index_ready_for_use = True
        self.set_loading_state(False)
        self._set_platform_items(self.store.platform_names())
        self.update_alert_strip()
        self._apply_platform_selection()
        self.connection_label.setText("✓ STS veri dosyası bağlı")
        if self._sts_warned_legacy_migration and getattr(getattr(self.store, "db", None), "migration_performed", False):
            backup_path = getattr(self.store.db, "migration_backup_path", None)
            QMessageBox.information(
                self,
                "STS dosyası güncellendi",
                f"STS dosyası yeni sürüme uyumlu hale getirildi.\n\nYedek dosya: {backup_path}\n\nNot: Güncellenen dosya eski uygulamalarda açılmayabilir.",
            )
        self._remember_version_baseline()

    def _on_sts_index_failed(self, message: str, traceback_text: str):
        _log.error("STS index hazırlama hatası: %s\n%s", message, traceback_text)
        self._fail_sts_open_after_index_error(
            "STS indeks hatası",
            "STS dosyası açıldı ancak sözleşme indeksi hazırlanırken hata oluştu. "
            "Dosya kapatıldı. Lütfen dosyayı tekrar açmayı deneyin.",
        )

    def _fail_sts_open_after_index_error(self, title: str, message: str):
        store = self.store
        self.store = None
        self.contract_index = []
        self._tag_color_map_cache = None
        self._store_loading = False
        self._index_ready_for_use = False
        try:
            if store is not None and getattr(store, "db", None) is not None:
                store.db.close()
        except Exception:
            pass
        self.set_loading_state(False)
        self.set_empty_state()
        QMessageBox.critical(self, title, message)

    def _on_sts_load_failed(self, error_text: str):
        self._store_loading = False
        self.set_loading_state(False)
        self.set_empty_state()
        _log.error("STS doğrulama hatası: %s", error_text)
        QMessageBox.critical(self, "STS yükleme hatası",
                             f"STS dosyası okunamadı.\n\n{error_text}")

    def is_sts_mode(self) -> bool:
        return (
            self.store is not None
            and self.path is not None
            and str(self.path).lower().endswith(".sts")
        )

    def _refresh_index_tags_only(self):
        if not self.store:
            return
        tags_map = self.store.all_contract_tags_map()
        for it in self.contract_index:
            p = str(it.get("platform", "") or "").strip()
            no = str(it.get("no", "") or "").strip()
            ctype = str(it.get("type", "") or "").strip()
            tags = tags_map.get((p, no, ctype), [])
            it["tags"] = list(tags)
            search = " ".join(
                str(it.get(k, "") or "")
                for k in ["platform", "no", "user", "type", "link", "status", "completion_date", "content"]
            ).lower()
            if tags:
                search = (search + " " + " ".join(tags).lower()).strip()
            it["search"] = search

    def _rebuild_index_in_platform_order(self, platform_rows: Dict[str, List[dict]]):
        if not self.store:
            self.contract_index = []
            return
        ordered: List[dict] = []
        for p in self.store.platform_names():
            ordered.extend([dict(it) for it in platform_rows.get(p, [])])
        self.contract_index = ordered

    def _refresh_single_platform_index(self, platform: str, select_platform: Optional[str] = None):
        if getattr(self, "_refreshing_platform_index", False):
            return
        self._refreshing_platform_index = True
        self.platform_list.setEnabled(False)
        self.contract_table.setEnabled(False)
        try:
            if not self.store:
                self.set_empty_state()
                return
            p = safe_sheet_name(str(platform or ""))
            if not p:
                self.request_refresh(select_platform=select_platform, scope="all")
                return
            current_rows: Dict[str, List[dict]] = {}
            for it in self.contract_index:
                pp = str(it.get("platform", "") or "")
                current_rows.setdefault(pp, []).append(dict(it))
            self.set_busy_overlay(True, f"{p} güncelleniyor...", 25)
            try:
                QApplication.processEvents()
                tags_map = self.store.all_contract_tags_map()
                self.set_busy_overlay(True, "Sözleşme satırları okunuyor...", 62)
                QApplication.processEvents()
                current_rows[p] = self.store.list_main_contracts(p, tags_map=tags_map)
                self._rebuild_index_in_platform_order(current_rows)
                self.set_busy_overlay(True, "Arayüz yenileniyor...", 92)
                QApplication.processEvents()
                platforms = self.store.platform_names()
                self._set_platform_items(platforms)
                self.update_alert_strip()
                self.refresh_open_calendar()
                target = str(select_platform or p)
                if target:
                    self.select_platform(target)
                elif self.platform_list.count():
                    self._apply_platform_selection()
                else:
                    self.set_empty_state()
            finally:
                self.set_busy_overlay(False)
        finally:
            self.platform_list.setEnabled(True)
            self.contract_table.setEnabled(True)
            self._refreshing_platform_index = False

    def refresh_open_calendar(self):
        cal = getattr(self, "calendar_window", None)
        if not cal or not cal.isVisible():
            return
        try:
            cal.refresh_from_index(self.store, self.contract_index)
        except RuntimeError:
            self.calendar_window = None

    def request_refresh(self, select_platform: Optional[str] = None, scope: str = "all", platform: Optional[str] = None):
        try:
            self._notify_tool_windows_data_changed(locals().get("scope", "all"))
        except Exception:
            pass
        if not self.store:
            self.set_empty_state()
            return
        kind = str(scope or "all").strip().lower()
        if kind == "all":
            if self.is_sts_mode():
                self.contract_index = self.store.build_contract_index()
                self._set_platform_items(self.store.platform_names())
                self.update_alert_strip()
                self.refresh_open_calendar()
                if select_platform:
                    self.select_platform(select_platform)
                else:
                    self._apply_platform_selection()
                self.connection_label.setText("✓ STS veri dosyası bağlı")
                return
            QMessageBox.warning(self, "STS dosyası gerekli", EXCEL_DATA_SOURCE_DISABLED_MESSAGE)
            return
        if kind == "tags":
            self.set_busy_overlay(True, "Etiketler güncelleniyor...", 35)
            try:
                self._refresh_index_tags_only()
                self.set_busy_overlay(True, "Arayüz yenileniyor...", 90)
                self._set_platform_items(self.store.platform_names())
                self.update_alert_strip()
                self.refresh_open_calendar()
                if select_platform:
                    self.select_platform(select_platform)
                else:
                    self._apply_platform_selection()
            finally:
                self.set_busy_overlay(False)
            return
        if kind == "platform":
            self._refresh_single_platform_index(str(platform or select_platform or ""), select_platform=select_platform or platform)
            return
        # UI-only yenileme: tekrar excel indeks okumadan görünümü tazeler.
        self._set_platform_items(self.store.platform_names())
        self.update_alert_strip()
        self.refresh_open_calendar()
        if self.platform_list.count():
            self._apply_platform_selection()
        else:
            self.set_empty_state()

    def on_contract_save_progress(self, percent: int, message: str):
        self.set_busy_overlay(True, message, percent)

    def open_file(self):
        dlg = WorkbookStartDialog(self)
        if dlg.exec() and dlg.selected_path:
            sel = Path(dlg.selected_path)
            if sel.suffix.lower() != ".sts":
                QMessageBox.warning(self, "STS dosyası gerekli", EXCEL_DATA_SOURCE_DISABLED_MESSAGE)
                return
            if not self.close_all_tool_windows():
                return
            if _share_metadata_from_path(sel):
                try:
                    win = open_share_contract_window(sel)
                    if win:
                        if not hasattr(self, "_share_windows"):
                            self._share_windows = []
                        self._share_windows.append(win)
                        win.destroyed.connect(lambda *_args, w=win: self._share_windows.remove(w) if hasattr(self, "_share_windows") and w in self._share_windows else None)
                        win.show()
                except Exception as exc:
                    QMessageBox.critical(self, "Paylaşım açılamadı", f"Paylaşım dosyası açılamadı.\n\n{exc}")
                return
            if not auth.ensure_system_admin_setup(sel, self):
                return
            staff = auth.require_staff_login(sel, self)
            if not staff:
                return
            self.current_staff = staff
            auth.current_staff = staff
            self.start_sts_load(sel)

    def show_contract_summary(self, row: int, item: dict):
        if not self.store:
            return
        old_popup = getattr(self, "_summary_popup", None)
        if old_popup and old_popup.isVisible():
            old_popup.close()

        dialog = ContractSummaryDialog(
            self.store,
            item,
            self,
            detail_handler=self.open_summary_event_detail,
        )
        self._summary_popup = dialog
        dialog.destroyed.connect(lambda *_: setattr(self, "_summary_popup", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_summary_event_detail(self, item: dict) -> bool:
        self.open_contract_item(item)
        return True

    def _on_contract_cell_clicked(self, row: int, col: int):
        """Ozet hucresine tiklayinca popup ac.
        Col disi tiklama open_selected_contract ile cakismasin.
        """
        if col != COL_SUMMARY:
            return
        rows = getattr(self.contract_table, "_visible_rows", [])
        if row < 0 or row >= len(rows):
            return
        self.show_contract_summary(row, rows[row])

    def manage_platforms(self):
        if not self.require_permission_ui("manage_platforms", "Platform / Bileşen Yönetimi"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return

        def factory():
            dlg = PlatformComponentManagerDialog(self.store, self, initial_tab=0)
            saved_state = {"via_signal": False}

            def refresh_after_platform_save(*_args):
                saved_state["via_signal"] = True
                current = self.platform_list.currentItem() if hasattr(self, "platform_list") else None
                current_platform = str(current.data(Qt.UserRole) or "") if current else None
                self.request_refresh(select_platform=current_platform, scope="all")

            def refresh_on_close(*_args, d=dlg):
                try:
                    if getattr(d, "changed", False) and not saved_state.get("via_signal"):
                        refresh_after_platform_save()
                except Exception:
                    pass

            try:
                dlg.settings_saved.connect(refresh_after_platform_save)
            except Exception:
                pass
            try:
                dlg.finished.connect(refresh_on_close)
            except Exception:
                pass
            return dlg

        self.open_or_raise_tool_window(
            "manager:platform_components",
            "Platform / Bileşen Yönetimi",
            factory,
        )

    def create_platform(self):
        """Eski uyumluluk - manage_platforms'u cagirir."""
        self.manage_platforms()

    def manage_users(self):
        self.open_user_management()

    def manage_tags(self):
        if not self.require_permission_ui("manage_labels", "Etiket Yönetimi"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return

        def factory():
            dlg = TagManagerDialog(self.store, self.contract_index, self)

            def refresh_if_changed(*_args, d=dlg):
                try:
                    if getattr(d, "changed", False):
                        self._tag_color_map_cache = None
                        current_platform = ""
                        cur = self.platform_list.currentItem() if hasattr(self, "platform_list") else None
                        if cur:
                            current_platform = str(cur.data(Qt.UserRole) or "")
                        self.request_refresh(select_platform=current_platform, scope="tags")
                except Exception:
                    pass

            try:
                dlg.finished.connect(refresh_if_changed)
            except Exception:
                pass
            return dlg

        self.open_or_raise_tool_window(
            "manager:tags",
            "Etiket Yönetimi",
            factory,
        )

    def manage_components(self):
        if not self.require_permission_ui("manage_components", "Bileşen Yönetimi"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return

        def factory():
            dlg = PlatformComponentManagerDialog(self.store, self, initial_tab=1)

            def refresh_if_changed(*_args, d=dlg):
                try:
                    if getattr(d, "changed", False):
                        self.request_refresh(scope="ui")
                except Exception:
                    pass

            try:
                dlg.settings_saved.connect(lambda *_args: self.request_refresh(scope="ui"))
            except Exception:
                pass
            try:
                dlg.finished.connect(refresh_if_changed)
            except Exception:
                pass
            return dlg

        self.open_or_raise_tool_window(
            "manager:platform_components",
            "Platform / Bileşen Yönetimi",
            factory,
        )

    def open_calendar_tracking(self):
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return

        def factory():
            self.set_busy_overlay(True, "Takvim hazırlanıyor...")
            try:
                win = ContractCalendarWindow(
                    self.store, self.contract_index, self, detail_handler=self.open_calendar_event_detail
                )
                try:
                    self.calendar_window = win
                    win.destroyed.connect(lambda *_args: setattr(self, "calendar_window", None))
                except Exception:
                    pass
                try:
                    win.setWindowState(win.windowState() | Qt.WindowMaximized)
                except Exception:
                    pass
                return win
            finally:
                self.set_busy_overlay(False)

        self.open_or_raise_tool_window(
            "report:calendar",
            "Takvim Görünümü",
            factory,
        )

    def open_calendar_event_detail(self, ev: dict) -> bool:
        platform = str(ev.get("platform", "") or "")
        no = str(ev.get("no", "") or "")
        row = int(ev.get("row", 0) or 0)
        ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=row if row > 0 else None)
        if not ci:
            QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayları okunamadı.")
            return False
        work = ContractWorkWindow(self.store, ci, self, systems=systems, deliveries=deliveries)
        return bool(work.exec())

    def new_contract(self):
        if not self.require_permission_ui("create_contracts", "Sözleşme Ekleme"):
            return
        if not self.store:
            QMessageBox.information(self, "Veri dosyası gerekli", "Önce bir STS veri dosyası bağlayın.")
            return
        if not self.store.load_users():
            QMessageBox.information(self, "Kullanıcı gerekli", "Sözleşme girmeden önce kullanıcı tanımlayın.")
            udlg = UserManagerDialog(self.store, self)
            if not udlg.exec() or not self.store.load_users():
                return
        dlg=ContractDialog(self.store,self)
        if dlg.exec() and dlg.result:
            try:
                new_contract_id = self.store.write_contract(dlg.result, [], {})
                dlg.result.entry_start_row = int(new_contract_id or 0)
                setattr(dlg.result, "id", int(new_contract_id or 0))
                setattr(dlg.result, "contract_id", int(new_contract_id or 0))
                active_pid = int((getattr(dlg.result, "platform_ids", []) or [0])[0] or getattr(dlg.result, "platform_id", 0) or 0)
                ci, systems, deliveries = self.store.load_contract_structure(
                    dlg.result.platform,
                    dlg.result.no,
                    start_row=new_contract_id,
                    contract_type=dlg.result.contract_type,
                    platform_id=active_pid,
                )
            except Exception as exc:
                traceback.print_exc()
                QMessageBox.critical(self, "Sözleşme Kaydedilemedi", f"Yeni sözleşme kaydedilemedi:\n{exc}")
                return
            work=ContractWorkWindow(self.store,ci,self,systems=systems,deliveries=deliveries)
            if work.exec():
                self.request_refresh(
                    select_platform=ci.platform,
                    scope="platform",
                    platform=ci.platform,
                )

    def refresh(self, rebuild_index: bool = True):
        if not self.store:
            self.set_empty_state()
            return
        # Kayıttan sonra indeks tek seferde yenilenir; arama bu indeks üzerinden yapılır.
        if rebuild_index:
            self.contract_index = self.store.build_contract_index()
        if self.is_sts_mode():
            self.connection_label.setText("✓ STS veri dosyası bağlı")
        platforms = self.store.platform_names()
        self._set_platform_items(platforms)
        self.update_query_logo_background(None)
        self.update_alert_strip()
        self.refresh_open_calendar()
        self._apply_platform_selection()

    def select_platform(self, p):
        platform = str(p or "")
        if platform and platform in self._all_platform_names():
            self.selected_platforms = {platform}
            self.multi_platform_mode = False
            self._apply_platform_selection()

    def load_platform_contracts(self, platform):
        self.select_platform(platform)

    def toggle_filter_bar(self):
        visible = not self.filter_bar.isVisible()
        self.filter_bar.setVisible(visible)
        sender = self.sender()
        if visible:
            if sender is self.sort_btn:
                self.sort_combo.setFocus()
            else:
                self.filter_type.setFocus()

    def clear_query_filters(self):
        self.search_input.clear()
        if hasattr(self, "date_from_filter"):
            self._date_from_active = False
            self.date_from_filter.setDate(QDate.currentDate())
        if hasattr(self, "date_to_filter"):
            self._date_to_active = False
            self.date_to_filter.setDate(QDate.currentDate())
        if hasattr(self, "days_min_filter"):
            self.days_min_filter.clear()
        if hasattr(self, "days_max_filter"):
            self.days_max_filter.clear()
        if hasattr(self, 'filter_type'):
            self.filter_type.setCurrentIndex(0)
        if hasattr(self, 'filter_status'):
            self.filter_status.setCurrentIndex(0)
        if hasattr(self, 'sort_combo'):
            self.sort_combo.setCurrentIndex(0)
        # Sutun filtrelerini temizle
        if hasattr(self, '_filter_header'):
            self._filter_header.clear_all_filters()
        self.schedule_apply_contract_filter()

    def _on_date_filter_changed(self, which: str):
        if which == "from":
            self._date_from_active = True
        else:
            self._date_to_active = True
        self.schedule_apply_contract_filter()

    def _refresh_query_filters(self):
        type_vals = sorted(
            {str(it.get("type_display", it.get("type", "")) or "").strip() for it in self.all_contract_rows if str(it.get("type_display", it.get("type", "")) or "").strip()},
            key=self._norm_tr,
        )
        self.filter_type.blockSignals(True)
        self.filter_type.clear()
        self.filter_type.addItem("Tüm Türler", "")
        for tv in type_vals:
            self.filter_type.addItem(tv, tv)
        self.filter_type.blockSignals(False)

    def _contract_no_sort_key(self, no_text: str):
        txt = str(no_text or "").strip()
        if txt.isdigit():
            return (0, int(txt), txt.lower())
        parts = re.split(r"(\d+)", txt.lower())
        key = []
        for p in parts:
            if p.isdigit():
                key.append((0, int(p)))
            else:
                key.append((1, p))
        return (1, key)

    def _completion_date_sort_key(self, it: dict):
        d = it.get("_completion_obj")
        if d:
            return (0, d.toordinal())
        return (1, 99999999)

    def _days_sort_key(self, it: dict):
        day_num = it.get("_day_num")
        if day_num is not None:
            return (0, int(day_num))
        return (1, 99999999)

    def _contract_delivery_dates(self, it: dict) -> tuple[str, str, Optional[int]]:
        exact_plans = []
        has_flexible = False
        try:
            _ci, _systems, deliveries = self.store.load_contract_structure(
                it.get("platform", ""), it.get("no", ""), it.get("row", None) or it.get("entry_start_row", None), it.get("type", None)
            )
            for items in (deliveries or {}).values():
                for delivery in items or []:
                    raw = str(getattr(delivery, "planned_acceptance_date", "") or "").strip()
                    if not raw:
                        continue
                    parsed = parse_flexible_date(raw)
                    if parsed:
                        exact_plans.append(parsed)
                    else:
                        has_flexible = True
        except Exception:
            return "", "", None
        if exact_plans:
            near = min(exact_plans)
            diff = (near - date.today()).days
            return near.isoformat(), (f"{diff} gün" if diff >= 0 else f"{abs(diff)} gün gecikti"), diff
        if has_flexible:
            return "", "", None
        return "", "", None

    def _delivery_summary_map(self, rows: List[dict]) -> Dict[int, tuple[str, str, Optional[int]]]:
        ids = [int(r.get("row") or r.get("entry_start_row") or 0) for r in rows if int(r.get("row") or r.get("entry_start_row") or 0)]
        if not ids or not getattr(getattr(self.store, "db", None), "conn", None):
            return {}
        summary: Dict[int, tuple[list, bool]] = {cid: ([], False) for cid in ids}
        try:
            dates_map = self.store.get_delivery_planned_dates(ids)
            for cid, date_list in dates_map.items():
                exacts = []
                has_flexible = False
                for text in date_list:
                    if not text:
                        continue
                    parsed = parse_flexible_date(text)
                    if parsed:
                        exacts.append(parsed)
                    else:
                        has_flexible = True
                summary[int(cid)] = (exacts, has_flexible)
        except Exception:
            return {}
        out: Dict[int, tuple[str, str, Optional[int]]] = {}
        today = date.today()
        for cid, (exacts, has_flexible) in summary.items():
            if exacts:
                near = min(exacts)
                diff = (near - today).days
                out[cid] = (near.isoformat(), f"{diff} gün" if diff >= 0 else f"{abs(diff)} gün gecikti", diff)
            elif has_flexible:
                out[cid] = ("", "", None)
            else:
                out[cid] = ("", "", None)
        return out

    def _prepare_contract_row_cache(self, rows: List[dict]):
        today = date.today()
        delivery_summary = self._delivery_summary_map(rows)
        for it in rows:
            cid = int(it.get("row") or it.get("entry_start_row") or 0)
            delivery_txt, delivery_days, day_num = delivery_summary.get(cid) or self._contract_delivery_dates(it)
            if str(delivery_txt or "").strip().lower() in {"belirsiz", "-"}:
                delivery_txt = ""
                delivery_days = ""
                day_num = None
            if not str(delivery_txt or "").strip():
                delivery_days = ""
                day_num = None
            completion = parse_flexible_date(delivery_txt)
            it["_completion_obj"] = completion
            it["_completion_ord"] = completion.toordinal() if completion else None
            it["_near_delivery_txt"] = delivery_txt
            it["_near_delivery_days"] = delivery_days
            it["_day_num"] = day_num
            tags_list = list(it.get("tags", []) or [])
            it["_tags_str"] = ", ".join(tags_list) if tags_list else ""
            hay = it.get("search") or " ".join(str(it.get(k, "")) for k in ["platform", "no", "user", "status", "completion_date", "content"]).lower()
            it["_search_norm"] = str(hay or "").lower()

    def schedule_apply_contract_filter(self):
        if not hasattr(self, "_filter_apply_timer"):
            self.apply_contract_filter()
            return
        self._filter_apply_timer.start(180)

    def _contract_status_display(self, it: dict) -> tuple[str, str]:
        cls, st_label, _days_text, _tdate = self._contract_health(it)
        if cls in {"geciken", "gecikmeli_teslim"}:
            color = "#dc2626"
        elif cls == "kritik":
            color = "#b45309"
        elif cls == "tamamlandi":
            color = "#047857"
        else:
            color = "#1f5be3"
        return st_label, color

    def _contract_remaining_display(self, it: dict) -> tuple[str, str]:
        cls, _st_label, days_text, tdate = self._contract_health(it)
        tdate_display = str(tdate or "").strip()
        if tdate_display in {"-", "Belirsiz", "—"} or not parse_flexible_date(tdate_display):
            tdate_display = ""
        remaining_text = str(days_text or "").strip() if tdate_display else ""
        if remaining_text in {"-", "Belirsiz", "—"}:
            remaining_text = ""

        if cls in {"geciken", "gecikmeli_teslim"}:
            color = "#dc2626"
        elif "erken teslim edildi" in str(remaining_text):
            color = "#047857"
        elif str(remaining_text) in {"Termin gününde teslim edildi", "Teslim tarihi yok", "—"}:
            color = "#64748b"
        elif str(remaining_text).endswith("gün"):
            days_num = as_number(str(remaining_text).replace(" gün", ""))
            if days_num <= 60:
                color = "#b45309"
            else:
                color = "#1f5be3"
        else:
            color = "#047857"
        return remaining_text, color

    def _contract_tags_for_row(self, it: dict, tags_map=None) -> list:
        return list(it.get("tags", []) or [])

    def _contract_row_height_for_tags(self, tag_count: int) -> int:
        n = int(tag_count or 0)
        return max(36, n * 22 + max(0, n - 1) * 3 + 8) if n > 0 else 36


    def apply_contract_filter(self):
        q = (self.search_input.text() if hasattr(self, "search_input") else "").strip().lower()
        selected_type = str(self.filter_type.currentData() or "").strip() if hasattr(self, "filter_type") else ""
        selected_status = str(self.filter_status.currentData() or "").strip() if hasattr(self, "filter_status") else ""
        sort_mode = str(self.sort_combo.currentData() or "default")
        # Kalan Gun kolonundan gelen siralama sort_combo'yu ezer
        tbl_sort = getattr(getattr(self, 'contract_table', None), '_sort_mode', 'default')
        if tbl_sort != 'default':
            sort_mode = tbl_sort
        rows = []
        date_from = None
        date_to = None
        if hasattr(self, "date_from_filter") and getattr(self, "_date_from_active", False):
            date_from = self.date_from_filter.date().toPython()
        if hasattr(self, "date_to_filter") and getattr(self, "_date_to_active", False):
            date_to = self.date_to_filter.date().toPython()
        days_min = None
        days_max = None
        if hasattr(self, "days_min_filter"):
            txt = self.days_min_filter.text().strip()
            if txt:
                try:
                    days_min = int(txt)
                except ValueError:
                    days_min = None
        if hasattr(self, "days_max_filter"):
            txt = self.days_max_filter.text().strip()
            if txt:
                try:
                    days_max = int(txt)
                except ValueError:
                    days_max = None
        if hasattr(self, "contract_table"):
            self.contract_table._all_rows_for_filter = list(getattr(self, "all_contract_rows", []))
        # Sutun filtreleri
        col_filters = {}
        date_ranges = {}
        day_ranges = {}
        if hasattr(self, '_filter_header'):
            col_filters = dict(self._filter_header._col_filters)
            date_ranges = dict(getattr(self._filter_header, "_date_ranges", {}))
            day_ranges = dict(getattr(self._filter_header, "_day_ranges", {}))
        selected_platforms = set(getattr(self, "selected_platforms", set()))
        for it in getattr(self, "all_contract_rows", []):
            if selected_platforms and str(it.get("platform", "")) not in selected_platforms:
                continue
            hay = str(it.get("_search_norm") or "")
            if q and q not in hay:
                continue
            tval = str(it.get("type_display", it.get("type", "")) or "").strip()
            if selected_type and tval != selected_type:
                continue
            cls, st_label, _days, _dt = self._contract_health(it)
            if selected_status and cls != selected_status:
                continue
            completion = it.get("_completion_obj")
            if date_from and (not completion or completion < date_from):
                continue
            if date_to and (not completion or completion > date_to):
                continue
            day_num = it.get("_day_num")
            if days_min is not None and (day_num is None or day_num < days_min):
                continue
            if days_max is not None and (day_num is None or day_num > days_max):
                continue
            if COL_T_DATE in date_ranges:
                start_date, end_date = date_ranges.get(COL_T_DATE, (None, None))
                if start_date and (not completion or completion < start_date):
                    continue
                if end_date and (not completion or completion > end_date):
                    continue
            if COL_REMAINING in day_ranges:
                min_day, max_day = day_ranges.get(COL_REMAINING, (None, None))
                if min_day is not None and (day_num is None or day_num < min_day):
                    continue
                if max_day is not None and (day_num is None or day_num > max_day):
                    continue
            # Sutun bazli filtreler (0=Platform,1=Tur,2=No,3=User,4=Durum,5=Tarih,6=Gun,7=Etiketler,8=Ozet)
            tags_str = str(it.get("_tags_str") or "")
            col_vals = [
                str(it.get("platform", "") or ""),
                str(it.get("type_display", it.get("type", "")) or ""),
                str(it.get("no", "") or ""),
                str(it.get("user", "") or ""),
                st_label,
                _dt,
                _days,
                tags_str,
                "Özet",
            ]
            skip = False
            for ci, fset in col_filters.items():
                if fset is None:
                    continue

                # Etiketler kolonu için özel kontrol:
                # seçilen etiketlerden en az biri satırdaki etiketlerde varsa geçir.
                if ci == COL_TAGS:
                    row_tags = [str(t or "").strip() for t in list(it.get("tags", []) or []) if str(t or "").strip()]
                    if not any(tag in fset for tag in row_tags):
                        skip = True
                        break
                    continue

                if ci < len(col_vals):
                    if col_vals[ci] not in fset:
                        skip = True
                        break

            if skip:
                continue
            rows.append(it)

        if sort_mode == "no_asc":
            rows.sort(key=lambda x: self._contract_no_sort_key(x.get("no", "")))
        elif sort_mode == "no_desc":
            rows.sort(key=lambda x: self._contract_no_sort_key(x.get("no", "")), reverse=True)
        elif sort_mode == "date_asc":
            rows.sort(key=self._completion_date_sort_key)
        elif sort_mode == "date_desc":
            rows.sort(key=lambda x: (0, -x["_completion_obj"].toordinal()) if x.get("_completion_obj") else (1, 99999999))
        elif sort_mode == "days_asc":
            rows.sort(key=self._days_sort_key)
        elif sort_mode == "days_desc":
            rows.sort(key=self._days_sort_key, reverse=True)
        elif sort_mode == "user_asc":
            rows.sort(key=lambda x: self._norm_tr(str(x.get("user", ""))))
        elif sort_mode == "user_desc":
            rows.sort(key=lambda x: self._norm_tr(str(x.get("user", ""))), reverse=True)

        # Etiket renk haritası (performans için bir kez yükle)
        if self._tag_color_map_cache is None:
            tag_color_map: Dict[str, str] = {}
            if self.store:
                try:
                    for td in self.store.load_tag_defs():
                        tag_color_map[self.store._normalize_label(td.name)] = td.color or "#3B82F6"
                except Exception:
                    pass
            self._tag_color_map_cache = tag_color_map
        _tag_color_map = self._tag_color_map_cache

        self.contract_table.setUpdatesEnabled(False)
        self.contract_table.blockSignals(True)
        try:
            self.contract_table.clearContents()
            self.contract_table.setRowCount(len(rows))
            self.contract_table._visible_rows = rows
            for r,it in enumerate(rows):
                for c in range(self.contract_table.columnCount()):
                    self.contract_table.removeCellWidget(r, c)
                self.contract_table.setRowHeight(r, 36)
                cls, _st_label, _days_text, tdate = self._contract_health(it)
                st_label, status_color = self._contract_status_display(it)
                days_display, remaining_color = self._contract_remaining_display(it)
                payload = {
                    "platform": str(it.get("platform", "") or ""),
                    "contract_no": str(it.get("no", "") or ""),
                    "contract_type": str(it.get("type_display", it.get("type", "")) or ""),
                    "contract_item": it,
                }
                tdate_display = str(tdate or "").strip()
                if tdate_display in {"-", "Belirsiz", "—"} or not parse_flexible_date(tdate_display):
                    tdate_display = ""
                vals=[
                    it.get("platform", ""),
                    it.get("type_display", it.get("type", "")) or "",
                    it.get("no", ""),
                    it.get("user", ""),
                    st_label,
                    tdate_display,
                    days_display,
                    None,  # col 7: Etiketler widget
                    None,  # col 8: Ozet butonu
                ]
                for c,v in enumerate(vals):
                    if c == COL_TAGS:
                        # Etiketler: dikey sıralı renkli chip'ler
                        tags_list = self._contract_tags_for_row(it, _tag_color_map)
                        if not tags_list:
                            empty = QTableWidgetItem("")
                            empty.setFlags(empty.flags() & ~Qt.ItemIsEditable)
                            empty.setData(Qt.UserRole, payload)
                            self.contract_table.setItem(r, COL_TAGS, empty)
                            self.contract_table.setRowHeight(r, max(self.contract_table.rowHeight(r), 36))
                            continue
                        wrap = QWidget()
                        wrap.setStyleSheet("QWidget{background:transparent;border:0px;}")
                        wl = QVBoxLayout(wrap)
                        wl.setContentsMargins(5, 4, 5, 4)
                        wl.setSpacing(3)
                        wl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                        for tag_name in tags_list:
                            color = _tag_color_map.get(self.store._normalize_label(tag_name) if self.store else tag_name, "#3B82F6")
                            base_rgb = _hex_to_rgb(color)
                            bg = _mix_rgb(base_rgb, (255, 255, 255), 0.78)
                            border_c = _mix_rgb(base_rgb, (255, 255, 255), 0.28)
                            txt_c = _rgb_to_hex(_mix_rgb(base_rgb, (15, 23, 42), 0.22))
                            chip = QLabel(tag_name)
                            chip.setStyleSheet(
                                f"QLabel{{background:{_rgb_to_hex(bg)};color:{txt_c};"
                                f"border:1px solid {_rgb_to_hex(border_c)};border-radius:9px;"
                                f"padding:2px 8px;font-size:11px;font-weight:700;}}"
                            )
                            wl.addWidget(chip)
                        placeholder = QTableWidgetItem("")
                        placeholder.setData(Qt.UserRole, payload)
                        self.contract_table.setItem(r, COL_TAGS, placeholder)
                        self.contract_table.setCellWidget(r, COL_TAGS, wrap)
                        # Satır yüksekliğini etiket sayısına göre ayarla
                        row_h = self._contract_row_height_for_tags(len(tags_list))
                        self.contract_table.setRowHeight(r, max(self.contract_table.rowHeight(r), row_h))
                        continue
                    if c == COL_SUMMARY:
                        lbl = QLabel("\U0001F50D")
                        lbl.setAlignment(Qt.AlignCenter)
                        lbl.setToolTip("Bileşen özetini gör")
                        lbl.setStyleSheet(
                            "QLabel{font-size:16px;color:#185FA5;background:transparent;border:0px;}"
                            "QLabel:hover{color:#042C53;}"
                        )
                        wrap = QWidget()
                        wrap.setStyleSheet("QWidget{background:transparent;border:0px;}")
                        wl = QHBoxLayout(wrap)
                        wl.setContentsMargins(0,0,0,0)
                        wl.setSpacing(0)
                        wl.setAlignment(Qt.AlignCenter)
                        wl.addWidget(lbl)
                        placeholder = QTableWidgetItem("")
                        placeholder.setData(Qt.UserRole, payload)
                        self.contract_table.setItem(r, COL_SUMMARY, placeholder)
                        self.contract_table.setCellWidget(r, COL_SUMMARY, wrap)
                        continue
                    cell = QTableWidgetItem(str(v or ""))
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                    cell.setData(Qt.UserRole, payload)
                    if c == COL_STATUS:
                        cell.setForeground(QColor(status_color))
                    if c == COL_REMAINING:
                        cell.setForeground(QColor(remaining_color))
                    self.contract_table.setItem(r,c,cell)
        finally:
            self.contract_table.blockSignals(False)
            self.contract_table.setUpdatesEnabled(True)
        self.position_query_logo_background()

    def open_contract_item(self, item: dict):
        if getattr(self, "_opening_contract", False):
            return
        self._opening_contract = True
        self.contract_table.setEnabled(False)
        try:
            if not self.store:
                if getattr(self, "_store_loading", False):
                    QMessageBox.information(
                        self,
                        "STS yükleniyor",
                        "Liste hazır. Sözleşme detayı birkaç saniye içinde hazır olacak.",
                    )
                return
            platform = item.get("platform")
            no = item.get("no")
            start_row = item.get("row")
            self.set_busy_overlay(True, "Sözleşme detayı yükleniyor...")
            try:
                with perf_tracker.measure(
                    perf_tracker.OP_CONTRACT_OPEN,
                    self.store.path,
                    meta={"platform": platform, "contract_no": no, "row": start_row},
                ):
                    ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=start_row)
            finally:
                self.set_busy_overlay(False)
            if not ci:
                QMessageBox.warning(self, "Bulunamadı", "Sözleşme detayları okunamadı.")
                return
            try:
                work = ContractWorkWindow(self.store, ci, self, systems=systems, deliveries=deliveries)
            except Exception as exc:
                traceback.print_exc()
                _log.exception("ContractWorkWindow açılamadı")
                QMessageBox.critical(
                    self,
                    "Sözleşme detayı açılamadı",
                    f"Sözleşme detay ekranı açılırken hata oluştu:\n\n{exc}",
                )
                return
            if work.exec():
                deleted_info = getattr(work, "deleted_contract_info", None)
                if deleted_info:
                    # Silme sonrası tam excel indeksini yeniden kurmak (binlerce satırda)
                    # gereksiz uzun sürüyor. Mevcut indeksi yerinde güncelleriz.
                    self.set_busy_overlay(True, "Liste güncelleniyor...", 82)
                    try:
                        self._apply_deleted_contract_to_index(deleted_info)
                        self.set_busy_overlay(True, "Arayüz yenileniyor...", 96)
                        platforms = self.store.platform_names()
                        self._set_platform_items(platforms)
                        self.update_alert_strip()
                        if str(platform or "") in platforms:
                            self.select_platform(platform)
                        elif self.platform_list.count():
                            self._apply_platform_selection()
                        else:
                            self.set_empty_state()
                    finally:
                        self.set_busy_overlay(False)
                else:
                    old_platform = str(platform or "")
                    work_ci = getattr(work, "ci", None)
                    new_platform = str(getattr(work_ci, "platform", "") or old_platform)
                    if old_platform and new_platform and old_platform != new_platform:
                        self.request_refresh(select_platform=old_platform, scope="platform", platform=old_platform)
                        self.request_refresh(select_platform=new_platform, scope="platform", platform=new_platform)
                        self.select_platform(new_platform)
                    else:
                        target = new_platform or old_platform
                        self.request_refresh(select_platform=target, scope="platform", platform=target)
        finally:
            self.contract_table.setEnabled(True)
            self._opening_contract = False

    def _extract_contract_item_from_cell(self, row: int, col: int) -> dict | None:
        rows = getattr(self.contract_table, "_visible_rows", [])
        if row < 0 or row >= self.contract_table.rowCount():
            return None
        payload = None
        for column in range(self.contract_table.columnCount()):
            cell = self.contract_table.item(row, column)
            candidate = cell.data(Qt.UserRole) if cell else None
            if isinstance(candidate, dict) and candidate.get("contract_no"):
                payload = candidate
                break
        if payload and isinstance(payload.get("contract_item"), dict):
            return payload["contract_item"]
        if row < len(rows):
            return rows[row]
        platform_item = self.contract_table.item(row, COL_PLATFORM)
        type_item = self.contract_table.item(row, COL_TYPE)
        no_item = self.contract_table.item(row, COL_CONTRACT_NO)
        return {
            "platform": platform_item.text() if platform_item else "",
            "type": type_item.text() if type_item else "",
            "no": no_item.text() if no_item else "",
        }

    def open_selected_contract(self, row, col):
        rows = getattr(self.contract_table, "_visible_rows", [])
        if row < 0 or row >= self.contract_table.rowCount():
            return
        if col == COL_SUMMARY:
            if row < len(rows):
                self.show_contract_summary(row, rows[row])
            return
        item = self._extract_contract_item_from_cell(row, col)
        if item:
            self.open_contract_item(item)

    def _apply_deleted_contract_to_index(self, deleted_info: dict):
        p = str((deleted_info or {}).get("platform") or "")
        no = str((deleted_info or {}).get("contract_no") or "").strip()
        start = int((deleted_info or {}).get("start_row") or 0)
        end = int((deleted_info or {}).get("end_row") or 0)
        deleted_rows = int((deleted_info or {}).get("deleted_rows") or max(0, end - start + 1))
        if not p or start <= 0 or deleted_rows <= 0:
            return

        updated = []
        removed = False
        for it in getattr(self, "contract_index", []):
            ip = str(it.get("platform", "") or "")
            irow = int(it.get("row", 0) or 0)
            ino = str(it.get("no", "") or "").strip()

            if ip == p and irow == start and ino == no and not removed:
                removed = True
                continue

            rec = dict(it)
            if ip == p and irow > end:
                rec["row"] = irow - deleted_rows
            updated.append(rec)

        # Güvenli fallback: row eşleşmesi bozulduysa ilk aynı no'yu düş.
        if not removed:
            for idx, it in enumerate(updated):
                if str(it.get("platform", "") or "") == p and str(it.get("no", "") or "").strip() == no:
                    del updated[idx]
                    removed = True
                    break

        self.contract_index = updated


def open_share_contract_window(path: Path | str) -> Optional[ContractWorkWindow]:
    """Open a share-mode STS directly in ContractWorkWindow without main list/login."""
    meta = _share_metadata_from_path(path)
    if not meta:
        return None
    store = STSStore(Path(path), actor="Paylaşım")
    rows = store.build_contract_index()
    if not rows:
        raise ValueError("Paylaşım dosyasında sözleşme bulunamadı.")
    source_no = str(meta.get("source_contract_no") or "").strip()
    selected = None
    if source_no:
        selected = next((r for r in rows if str(r.get("no") or "").strip() == source_no), None)
    if selected is None:
        contract_id = int(meta.get("contract_id") or 0)
        selected = next((r for r in rows if int(r.get("row") or 0) == contract_id), None) if contract_id else None
    selected = selected or rows[0]
    contract_id = int(selected.get("row") or meta.get("contract_id") or 0)
    if contract_id <= 0:
        raise ValueError("Paylaşım sözleşmesi bulunamadı.")
    row = store.db.conn.execute("SELECT c.contract_no,c.contract_type,p.name AS platform,c.platform_id FROM contracts c JOIN platforms p ON p.id=c.platform_id WHERE c.id=?", (contract_id,)).fetchone()
    if not row:
        raise ValueError("Paylaşım sözleşmesi bulunamadı.")
    ci, systems, deliveries = store.load_contract_structure(
        str(row["platform"] or ""),
        contract_no=str(row["contract_no"] or ""),
        start_row=contract_id,
        contract_type=str(row["contract_type"] or ""),
        platform_id=int(row["platform_id"] or 0),
    )
    auth.current_staff = {
        "id": 0,
        "full_name": "Paylaşım Kullanıcısı",
        "username": "share",
        "is_active": 1,
        "is_admin": True,
        "permissions": {"view_contracts", "edit_contracts", "export_data", "manage_labels"},
    }
    win = ContractWorkWindow(store, ci, systems=systems, deliveries=deliveries)
    win.set_share_mode(str(meta.get("permission_mode") or "view"))
    return win


