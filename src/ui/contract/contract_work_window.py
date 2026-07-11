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
import uuid
import unicodedata
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Protocol, Tuple
from src.ui.dialogs.auto_accept_dialog import open_auto_accept_dialog
from src.services.share_package_service import parse_share_metadata, read_share_metadata, write_share_metadata
from src.share_permissions import can_mutate_current_contract
from src.contract_projection import component_display_keys


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
    APP_ID,
    materialized_app_icon_ico_path,
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
from src.ui.dialogs.share_merge_dialog import ShareMergeDialog
from src.ui.dialogs.share_history_dialog import ShareHistoryDialog
from src.ui.presenters.share_merge_error_presenter import present_share_merge_error
from src.services.share_history_service import list_contract_share_history
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
    PlatformTabsWidget, FixedContractTypeField,
    BadgeTabButton, ContractActionTabs, ContractSharePopover,
    UnitTrackingSlotCard, UnitTrackingSidePanel,
)

from PySide6.QtCore import Qt, QDate, QObject, QThread, Signal, QTimer, QPoint, QSize, QRect, QEvent, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QFont, QFontMetrics, QColor, QPixmap, QIcon, QPainter, QAction, QCloseEvent, QDesktopServices, QKeySequence, QShortcut, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QDialog, QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
    QMessageBox, QFileDialog, QFrame, QScrollArea, QCheckBox, QHeaderView,
    QSizePolicy, QProgressBar, QProgressDialog, QStyledItemDelegate, QTextEdit,
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
    """Compatibility wrapper; share package implementation lives in share_package_service."""
    return read_share_metadata(path)


def _write_share_metadata(path: Path | str, metadata: dict) -> None:
    """Compatibility wrapper; share package implementation lives in share_package_service."""
    write_share_metadata(path, metadata)


def app_icon_path() -> Path:
    """Return a materialized native icon when available, otherwise the SVG logo."""
    icon_path = materialized_app_icon_ico_path()
    if icon_path is not None and icon_path.exists():
        return icon_path
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
from src.services.share_package_service import (
    build_base_snapshot_from_source, make_v2_metadata, read_share_metadata, validate_share_package,
    write_share_base_snapshot, write_share_metadata, utcish_now,
)
from src.services.share_merge_service import (
    PackageRegistryMismatchError,
    ShareMergePreparationError,
    SharePackageStatusError,
    ShareSourceMismatchError,
    UnknownSharePackageError,
    UnsupportedShareMergePackageError,
    prepare_share_merge_plan,
)
from src.services.share_merge_apply_service import (
    apply_resolved_share_merge,
    preflight_resolved_share_merge,
)
from src.models.share_models import SHARE_FORMAT_V1, SHARE_FORMAT_V2, SHARE_STATUS_OPEN, SharePackageRegistryEntry
from src.services.share_lifecycle_service import cancel_share_package, list_active_share_packages
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










def section_label(text):
    l = QLabel(text)
    l.setObjectName("sectionTitle")
    return l


def configure_table(table, compact: bool = False):
    """Tablo görünümünü standart şekilde yapılandırır."""
    from src.ui.delegates import CenterTableDelegate
    table.setItemDelegate(CenterTableDelegate(table))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setMinimumHeight(42 if not compact else 34)
    table.verticalHeader().setDefaultSectionSize(34 if not compact else 28)
    table.setWordWrap(False)


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

class ContractWorkWindow(QDialog):
    def __init__(self, store: ExcelStore, ci: ContractInfo, parent=None, systems: Optional[List[SystemInfo]] = None, deliveries: Optional[Dict[str, List[DeliveryInfo]]] = None):
        super().__init__(parent)
        self.store = store
        parent_staff = getattr(parent, "current_staff", None) if parent is not None else None
        self.current_staff = parent_staff or auth.current_staff
        self._document_lock_state: dict = {}
        # Yeni sozlesme mi (systems/deliveries verilmemis) yoksa mevcut mu
        self.is_new_contract = (systems is None and deliveries is None)
        self.ci = ci
        self.original_platform = str(ci.platform or "")
        self.original_contract_no = str(ci.no or "")
        self.original_contract_type = str(ci.contract_type or "")
        self.original_entry_start_row = int(getattr(ci, "entry_start_row", 0) or 0)
        self.systems: List[SystemInfo] = systems or []
        self.deliveries: Dict[str, List[DeliveryInfo]] = deliveries or {}
        self.contract_tags: List[dict] = self.store.load_contract_tags(
            self.original_platform,
            self.original_contract_no,
            self.original_contract_type,
        )
        dedup: Dict[str, dict] = {}
        for t in self.contract_tags:
            k = normalized_tag_key(str((t or {}).get("name") or ""))
            if not k:
                continue
            dedup[k] = dict(t)
        self.contract_tags = list(dedup.values())
        self.selected_system: Optional[str] = None
        self.expanded_delivery_index: Optional[int] = None
        self._delivery_row_map: Dict[int, int] = {}
        self._updating_summary = False
        self.deleted_contract_info: Optional[dict] = None
        self._context_cache: Dict[Tuple[str, str, str], dict] = {}
        self._deleted_delivery_systems: set[str] = set()
        self._refreshing_contract_context = False
        self._contract_save_thread = None
        self._contract_save_worker = None
        self._pending_contract_save_context = None
        self._file_dialog_open: bool = False
        self._documents_changed: bool = False
        self._import_contract_folders_running: bool = False
        self._is_dirty: bool = False   # Kullanıcı henüz değişiklik yapmadı
        # Yeni sözleşme modunda belgeler için in-memory bekleme yapısı
        self._pending_doc_folders: list = []   # [{id, parent_id, name}]
        self._pending_doc_files: list = []     # [{id, folder_id, filename, content_blob, file_ext, mime_type, size_bytes, note, created_at}]
        self._pending_doc_next_id: int = -1    # Negatif id'ler pending anlamına gelir
        self.share_mode_enabled = False
        self.share_permission_mode = "edit"
        self.setWindowTitle(APP_TITLE)
        # QDialog varsayılan olarak ? butonu gösterir — standart pencere butonları ekle
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowSystemMenuHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.resize(1450, 860)
        self.setWindowState(Qt.WindowMaximized)  # Varsayılan tam ekran
        self.setStyleSheet(STYLE)
        _log.debug("ContractWorkWindow.build başlangıç")
        self.build()
        _log.debug("ContractWorkWindow.build tamamlandı")
        _log.debug("ContractWorkWindow.build_busy_overlay başlangıç")
        self.build_busy_overlay()
        _log.debug("ContractWorkWindow.build_busy_overlay tamamlandı")
        # Mevcut sozlesmede 'Secili Sistemi Sil' butonunu gizle
        self.delete_system_btn.setVisible(self.is_new_contract)
        _log.debug("ContractWorkWindow.refresh başlangıç")
        self.refresh()
        _log.debug("ContractWorkWindow.refresh tamamlandı")
        # Değişiklik tespiti için başlangıç snapshot'ı al
        if not self.is_new_contract:
            self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self._initial_snapshot = self._make_data_snapshot()

    def set_share_mode(self, permission_mode: str = "view"):
        self.share_mode_enabled = True
        self.share_permission_mode = "edit" if str(permission_mode or "").lower() == "edit" else "view"
        self.share_metadata = parse_share_metadata(read_share_metadata(getattr(self.store, "path", "")))
        self._apply_share_permissions()

    def _share_is_view_only(self) -> bool:
        return bool(getattr(self, "share_mode_enabled", False)) and str(getattr(self, "share_permission_mode", "view")) != "edit"

    def _share_labels_disabled(self) -> bool:
        return bool(getattr(self, "share_mode_enabled", False))

    def _share_label_policy_message(self) -> str:
        return "Etiket işlemleri paylaşım dosyasında desteklenmez. Ana STS dosyasında yapılmalıdır."

    def _apply_share_permissions(self):
        if not getattr(self, "share_mode_enabled", False):
            return
        view_only = self._share_is_view_only()
        self.setWindowTitle(f"{APP_TITLE} - Paylaşım ({'Görüntüleme' if view_only else 'Düzenleme'})")
        band = getattr(self, "share_info_band", None)
        if band is not None:
            band.setText("Paylaşım Modu: Görüntüleme — Bu dosyada düzenleme kapalıdır." if view_only else "Paylaşım Modu: Düzenleme — Yalnızca bu sözleşme düzenlenebilir.")
            band.setVisible(True)
        for attr in ("save_btn", "edit_system_btn", "add_system_btn", "add_delivery_btn", "auto_accept_btn", "delete_system_btn"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setEnabled(not view_only)
                if view_only:
                    widget.setToolTip("Paylaşım görüntüleme modunda bu işlem kapalıdır.")
        if hasattr(self, "delete_contract_btn"):
            self.delete_contract_btn.setVisible(False)
            self.delete_contract_btn.setEnabled(False)
            self.delete_contract_btn.setToolTip("Paylaşım paketinde sözleşme silme Aşama 2'de kapalıdır.")
        header_edit = getattr(self, "header_edit_btn", None)
        if header_edit is not None:
            header_edit.setEnabled(not view_only)
            if view_only:
                header_edit.setToolTip("Paylaşım görüntüleme modunda bu işlem kapalıdır.")
        for table_name in ("summary", "del_table"):
            table = getattr(self, table_name, None)
            if table is not None:
                table.setEditTriggers(QAbstractItemView.NoEditTriggers if view_only else QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)

    def _ensure_share_can_edit(self, title: str = "Paylaşım") -> bool:
        if self._share_is_view_only():
            QMessageBox.information(self, title, "Bu paylaşım dosyası görüntüleme yetkisiyle açıldı; düzenleme yapılamaz.")
            return False
        return True

    def has_permission(self, permission_code: str) -> bool:
        if can_mutate_current_contract(
            share_mode=bool(getattr(self, "share_mode_enabled", False)),
            permission_mode=str(getattr(self, "share_permission_mode", "view")),
            metadata=getattr(self, "share_metadata", None),
            target_contract=getattr(self, "ci", None),
            operation=permission_code,
        ):
            return True
        db_conn = getattr(getattr(self.store, "db", None), "conn", None)
        return auth.has_permission(self.current_staff, permission_code, db_conn)

    def require_permission_ui(self, permission_code: str, title: str = "Yetki gerekli") -> bool:
        if self.has_permission(permission_code):
            return True
        QMessageBox.warning(self, "Yetkisiz İşlem", "Bu işlemi yapmak için gerekli yetkiye sahip değilsiniz.")
        return False

    def _set_dirty(self) -> None:
        """Kullanıcı bir değişiklik yaptığında çağrılır."""
        self._is_dirty = True

    def _mark_documents_changed(self) -> None:
        """Belge/klasör işlemleri STS veritabanına anında yazılır; Kaydet uyarısını bastırmak için izlenir."""
        self._documents_changed = True

    def _finish_persisted_side_meta_only_save(self) -> None:
        self._documents_changed = False
        self._is_dirty = False
        self.accept()

    def _make_data_snapshot(self) -> str:
        """ci + systems + deliveries + tags verilerinin JSON özeti."""
        import json as _json
        ci = self.ci
        data = {
            "no":              str(ci.no or ""),
            "user":            str(ci.user or ""),
            "yi_yd":           str(ci.yi_yd or ""),
            "contract_type":   str(ci.contract_type or ""),
            "signature_date":  str(ci.signature_date or ""),
            "t0_date":         str(ci.t0_date or ""),
            "t0_months":       int(ci.t0_months or 0),
            "completion_date": str(ci.completion_date or ""),
            "status":          str(ci.status or ""),
            "note":            str(ci.note or ""),
            "acceptance_date": str(ci.acceptance_date or ""),
            "systems": sorted([
                {
                    "name":            str(s.name or ""),
                    "components":      {k: float(v) for k, v in sorted((s.components or {}).items())},
                    "component_notes": {k: str(v or "") for k, v in sorted((getattr(s, "component_notes", {}) or {}).items()) if str(v or "")},
                    "t0_date":         str(s.t0_date or ""),
                    "t0_months":       int(s.t0_months or 0),
                    "completion_date": str(s.completion_date or ""),
                    "status":          str(s.status or ""),
                    "acceptance_date": str(s.acceptance_date or ""),
                    "deliveries": sorted([
                        {
                            "name":            str(d.name or ""),
                            "status":          str(d.status or ""),
                            "planned_acceptance_date": str(getattr(d, "planned_acceptance_date", "") or ""),
                            "acceptance_date": str(d.acceptance_date or ""),
                            "note":            str(d.note or ""),
                            "delivery_user":   str(getattr(d, "delivery_user", "") or ""),
                            "planned":  {k: float(v) for k, v in sorted((d.planned or {}).items())},
                            "delivered":{k: float(v) for k, v in sorted((d.delivered or {}).items())},
                            "component_units": {
                                k: sorted([{kk: vv for kk, vv in u.items()} for u in v], key=lambda x: x.get("slot_no", 0))
                                for k, v in sorted((getattr(d, "component_units", {}) or {}).items())
                            },
                        }
                        for d in self.deliveries.get(s.name, [])
                    ], key=lambda x: x["name"]),
                }
                for s in self.systems
            ], key=lambda x: x["name"]),
            "tags": sorted(str((t or {}).get("name", "") or "") for t in self.contract_tags),
        }
        return _json.dumps(data, sort_keys=True, ensure_ascii=False)

    def date_picker_events(self) -> List[dict]:
        return contract_date_picker_events(self.ci, self.systems)

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(6)

        header = QFrame(); header.setObjectName("contractHeader")
        header.setFixedHeight(68)
        self.contract_header = header  # sekme konumlandırması için referans
        h = QHBoxLayout(header); h.setContentsMargins(18, 7, 16, 7); h.setSpacing(14)

        info_row = QWidget(); info_row.setObjectName("contractHeaderInfoRow")
        info_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        info = QHBoxLayout(info_row); info.setContentsMargins(0, 0, 0, 0); info.setSpacing(0)

        actions = QWidget(); actions.setObjectName("contractHeaderActions")
        actions.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        actions_lay = QHBoxLayout(actions); actions_lay.setContentsMargins(0, 0, 0, 0); actions_lay.setSpacing(8)

        self.meta_values: Dict[str, QLabel] = {}
        self.user_tooltip_text = ""
        self.platform_tabs_widget: Optional[PlatformTabsWidget] = None

        def meta_cell(key, label_text, value_text, *, min_w=70, max_w=None, value_widget=None, tooltip: str = ""):
            cell = QWidget(); cell.setObjectName("metaCell")
            cell.setMinimumWidth(min_w)
            if max_w:
                cell.setMaximumWidth(max_w)
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if tooltip:
                cell.setToolTip(tooltip)
            cl = QVBoxLayout(cell); cl.setContentsMargins(10, 0, 10, 0); cl.setSpacing(2)
            lbl = QLabel(label_text.upper()); lbl.setObjectName("metaHeaderLabel")
            if value_widget is None:
                val = ElidedValueLabel(value_text if value_text else "-"); val.setObjectName("metaHeaderValue")
                self.meta_values[key] = val
            else:
                val = value_widget
            if tooltip and hasattr(val, "setToolTip"):
                val.setToolTip(tooltip)
            cl.addWidget(lbl); cl.addWidget(val)
            div = QFrame(); div.setObjectName("metaHeaderDiv")
            div.setFixedSize(1, 32)
            return cell, div

        def compact_users(value: str, user_list: Optional[List[str]] = None) -> Tuple[str, str]:
            users = [str(x).strip() for x in (user_list or []) if str(x).strip()]
            if not users:
                users = [x.strip() for x in re.split(r"[,;]+", str(value or "")) if x.strip()]
            if not users:
                return "-", ""
            shown = users[0] if len(users) == 1 else f"{users[0]} +{len(users) - 1}"
            return shown, "\n".join(users)

        def inline_icon_text(text: str, icon_svg: bytes, object_name: str, tooltip: str = "") -> QWidget:
            wrap = QWidget(); wrap.setObjectName(object_name)
            row = QHBoxLayout(wrap); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(6)
            pix = QPixmap(); pix.loadFromData(icon_svg, "SVG")
            icon = QLabel(); icon.setObjectName("headerUserIcon"); icon.setPixmap(pix); icon.setFixedSize(16, 16)
            icon.setStyleSheet("QLabel#headerUserIcon{background:transparent;border:0;padding:0;margin:0;}")
            val = ElidedValueLabel(text if text else "-"); val.setObjectName("metaHeaderValue")
            if tooltip:
                for widget in (wrap, icon, val):
                    widget.setToolTip(tooltip)
            self.meta_values[object_name] = val
            row.addWidget(icon, 0, Qt.AlignVCenter)
            row.addWidget(val, 1, Qt.AlignVCenter)
            return wrap

        def status_widget(text: str) -> QWidget:
            wrap = QWidget(); wrap.setObjectName("headerStatusWrap")
            row = QHBoxLayout(wrap); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(7)
            dot = QLabel(); dot.setObjectName("headerStatusDot"); dot.setFixedSize(10, 10)
            val = ElidedValueLabel(text if text else "Başlanmadı"); val.setObjectName("metaHeaderValue")
            self.meta_values["status"] = val
            row.addWidget(dot, 0, Qt.AlignVCenter)
            row.addWidget(val, 1, Qt.AlignVCenter)
            return wrap

        user_text, user_tip = compact_users(self.ci.user, list(getattr(self.ci, "users", []) or []))
        responsible_name = str(getattr(self.ci, "responsible_engineer_name", "") or "").strip()
        if not responsible_name:
            responsible_items = list(getattr(self.ci, "responsible_engineers", []) or [])
            if responsible_items:
                responsible_name = str(responsible_items[0].get("full_name") or responsible_items[0].get("name") or "").strip()
        responsible_text = responsible_name or "-"
        self.user_tooltip_text = user_tip
        user_svg = b"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' width='16' height='16'>
          <circle cx='8' cy='5.35' r='2.45' fill='none' stroke='#c8e2ff' stroke-width='1.35'/>
          <path d='M3.15 13.35c.48-2.75 2.18-4.15 4.85-4.15s4.37 1.4 4.85 4.15'
                fill='none' stroke='#9fc7f2' stroke-width='1.35' stroke-linecap='round' stroke-linejoin='round'/>
          <path d='M4.55 12.55c.7-1.45 1.86-2.16 3.45-2.16s2.75.71 3.45 2.16'
                fill='none' stroke='#4e93ff' stroke-opacity='.55' stroke-width='.85' stroke-linecap='round'/>
        </svg>"""
        self.platform_tabs_widget = PlatformTabsWidget(self)
        self.active_platform_id = int(getattr(self.ci, "platform_id", 0) or getattr(self.ci, "primary_platform_id", 0) or 0)
        self.platform_tabs_widget.set_platforms(self._linked_contract_platforms(), self.active_platform_id)
        self.platform_tabs_widget.activePlatformChanged.connect(self.set_active_platform)

        cells = [
            (*meta_cell("no", "Sözleşme No", self.ci.no, min_w=122, max_w=210), 17),
            (*meta_cell("platform", "Platform", "", min_w=260, max_w=340, value_widget=self.platform_tabs_widget), 0),
            (*meta_cell("type", "Tür", self.ci.contract_type, min_w=96, max_w=160), 13),
            (*meta_cell("responsible_engineer", "Sorumlu Mühendis", responsible_text, min_w=138, max_w=220, tooltip=responsible_name), 17),
            (*meta_cell("user", "Kullanıcı", user_text, min_w=140, max_w=230, value_widget=inline_icon_text(user_text, user_svg, "user", user_tip), tooltip=user_tip), 18),
            (*meta_cell("status", "Durum", "", min_w=112, max_w=170, value_widget=status_widget(self.ci.status or "Başlanmadı")), 13),
        ]
        if user_tip and self.meta_values.get("user"):
            self.meta_values["user"].setToolTip(user_tip)
        for i, (cell, div, stretch) in enumerate(cells):
            info.addWidget(cell, stretch)
            if i < len(cells) - 1:
                info.addWidget(div)
                info.addSpacing(2)

        h.addWidget(info_row, 1)
        e = QPushButton("  Ana Bilgileri Düzenle"); e.setObjectName("headerEditBtn")
        e.setFixedHeight(36)
        _svg = b"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' width='15' height='15'>
          <path d='M11.5 1.5a1.5 1.5 0 0 1 2.12 2.12l-9 9a1 1 0 0 1-.4.24l-3 1a.5.5 0 0 1-.63-.63l1-3a1 1 0 0 1 .24-.4z'
                fill='none' stroke='#d8eaff' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/>
        </svg>"""
        _pix = QPixmap()
        _pix.loadFromData(_svg, "SVG")
        e.setIcon(QIcon(_pix))
        e.setIconSize(QSize(15, 15))
        e.clicked.connect(self.edit_contract_info)
        self.header_edit_btn = e
        actions_lay.addWidget(e)
        self.delete_contract_btn = QPushButton("Sözleşmeyi Sil")
        self.delete_contract_btn.setObjectName("danger")
        self.delete_contract_btn.setFixedHeight(36)
        trash_svg = b"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' width='15' height='15'>
          <path d='M2.8 4.2h10.4M6.2 4.2V2.7h3.6v1.5M4.2 5.8l.45 7.1c.05.75.48 1.1 1.2 1.1h4.3c.72 0 1.15-.35 1.2-1.1l.45-7.1M6.8 7.4v4.1M9.2 7.4v4.1'
                fill='none' stroke='#dc2626' stroke-width='1.25' stroke-linecap='round' stroke-linejoin='round'/>
        </svg>"""
        trash_pix = QPixmap(); trash_pix.loadFromData(trash_svg, "SVG")
        self.delete_contract_btn.setIcon(QIcon(trash_pix))
        self.delete_contract_btn.setIconSize(QSize(15, 15))
        self.delete_contract_btn.clicked.connect(self.delete_contract)
        actions_lay.addWidget(self.delete_contract_btn)
        h.addWidget(actions, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(header)

        body = QHBoxLayout(); body.setSpacing(10); root.addLayout(body, 1)

        left_block_width = 404
        left_block = QWidget()
        left_block.setFixedWidth(left_block_width)
        left_block_lay = QVBoxLayout(left_block)
        left_block_lay.setContentsMargins(0, 0, 0, 0)
        left_block_lay.setSpacing(10)

        left_row = QHBoxLayout()
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(10)

        version_bar = QFrame(); version_bar.setObjectName("contractVersionBar"); version_bar.setFixedWidth(94)
        vb = QVBoxLayout(version_bar); vb.setContentsMargins(8, 10, 8, 10); vb.setSpacing(8)
        self.sd_list = QListWidget()
        self.sd_list.setObjectName("sdList")
        self.sd_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sd_list.currentRowChanged.connect(self.on_sd_nav_changed)
        vb.addWidget(self.sd_list, 1)
        self.add_sd_btn = QPushButton("+")
        self.add_sd_btn.setToolTip("Bu ana sözleşmeye SD ekle")
        self.add_sd_btn.clicked.connect(self.add_sd_contract)
        vb.addWidget(self.add_sd_btn, 0)
        left_row.addWidget(version_bar, 0)

        left_content_host = QWidget()
        left_content_host.setObjectName("sideMetaHost")
        left_content_host.setFixedWidth(300)
        left_content_layout = QVBoxLayout(left_content_host)
        left_content_layout.setContentsMargins(0, 0, 0, 0)
        left_content_layout.setSpacing(10)

        self.systems_panel = QFrame(); self.systems_panel.setObjectName("sidebar")
        lv = QVBoxLayout(self.systems_panel); lv.setContentsMargins(10, 12, 10, 12); lv.setSpacing(10)
        top = QHBoxLayout(); lbl = QLabel("SİSTEMLER"); lbl.setObjectName("sideTitle"); top.addWidget(lbl); top.addStretch()
        add = QPushButton("+"); add.clicked.connect(self.add_system); add.setMinimumHeight(30); add.setMaximumWidth(34); self.add_system_btn = add; top.addWidget(add); lv.addLayout(top)
        self.system_list = QListWidget(); self.system_list.setObjectName("systemList"); self.system_list.currentRowChanged.connect(self.select_system); lv.addWidget(self.system_list, 1)
        delsys = QPushButton("Seçili Sistemi Sil")
        delsys.setObjectName("secondary")
        delsys.clicked.connect(self.delete_system)
        delsys.setMinimumHeight(38)
        self.delete_system_btn = delsys
        lv.addWidget(delsys)
        left_content_layout.addWidget(self.systems_panel, 1)
        left_row.addWidget(left_content_host, 1)
        left_block_lay.addLayout(left_row, 1)
        body.addWidget(left_block, 0)

        right = QFrame(); right.setObjectName("contentPanel"); rv = QVBoxLayout(right); rv.setContentsMargins(16, 10, 16, 12); rv.setSpacing(8); body.addWidget(right, 1)

        self.share_info_band = QLabel("")
        self.share_info_band.setObjectName("shareInfoBand")
        self.share_info_band.setWordWrap(True)
        self.share_info_band.setVisible(False)
        self.share_info_band.setStyleSheet("QLabel#shareInfoBand{background:#eff6ff;color:#1e3a8a;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:12px;font-weight:700;}")
        rv.addWidget(self.share_info_band, 0)

        self.side_meta_host = QWidget(self)
        self.side_meta_host.setObjectName("contractTabsHost")
        self.side_meta_host.setStyleSheet("QWidget#contractTabsHost{background:transparent;border:0;}")
        self.side_meta_host.setAttribute(Qt.WA_NoSystemBackground, True)
        self.side_meta_host.setAttribute(Qt.WA_TranslucentBackground, True)
        self.side_meta_host.setAutoFillBackground(False)
        self.side_meta_host.installEventFilter(self)
        tabs_host_lay = QVBoxLayout(self.side_meta_host)
        tabs_host_lay.setContentsMargins(0, 0, 0, 0)
        tabs_host_lay.setSpacing(0)
        self.contract_action_tabs = ContractActionTabs(self, self.side_meta_host)
        self.build_side_meta_popover_bar(0)
        tabs_host_lay.addWidget(self.side_meta_bar, 0, Qt.AlignRight)
        # side_meta_host layout'a değil, header altına overlay olarak konumlanır.
        # Doğru konum hesaplanana kadar (header/edit butonu henüz layout'ta yerleşmemişken)
        # varsayılan/tahmini konumda görünüp sonradan "zıplamasını" önlemek için,
        # ilk doğru konumlama tamamlanana kadar barı gizli tutuyoruz.
        self.side_meta_host.setVisible(False)
        QTimer.singleShot(0, self._place_tab_bar)
        self.render_contract_tags()

        # ── Üst satır: SİSTEM BİLEŞENLERİ etiketi + Sistemi Düzenle butonu aynı hizada ──
        self.title = QLabel("")  # refresh_right'ta güncellenir ama görünmez
        self.title.setVisible(False)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        self.system_metric_labels: Dict[str, QLabel] = {}
        self.system_metric_cards: Dict[str, QFrame] = {}

        def system_metric_card(key: str, title: str) -> QFrame:
            card = QFrame()
            card.setObjectName("systemMetricCard")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 7, 12, 7)
            lay.setSpacing(2)
            t = QLabel(title.upper())
            t.setObjectName("systemMetricTitle")
            v = QLabel("-")
            v.setObjectName("systemMetricValue")
            v.setWordWrap(True)
            card.setMinimumWidth(130)
            self.system_metric_labels[key] = v
            self.system_metric_cards[key] = card
            lay.addWidget(t)
            lay.addWidget(v)
            return card

        top_row.addWidget(system_metric_card("completion", "Termin Tarihi"), 0)
        top_row.addWidget(system_metric_card("days", "Kalan Gün"), 0)
        top_row.addWidget(system_metric_card("acceptance", "Gerçek Teslimat"), 0)
        top_row.addWidget(system_metric_card("user", "Kullanıcı"), 0)
        top_row.addStretch(1)
        self.edit_system_btn = QPushButton("✎ Sistemi Düzenle")
        self.edit_system_btn.setObjectName("secondary")
        top_row.addWidget(self.edit_system_btn, 0)
        rv.addLayout(top_row)
        self.edit_system_btn.clicked.connect(self.edit_system)

        self.summary = QTableWidget(0, 5)
        configure_table(self.summary)
        self.summary.verticalHeader().setDefaultSectionSize(38)
        self.summary.setHorizontalHeaderLabels(["Bileşen", "Sözleşme Adedi", "Teslim Edilen", "Kalan", "Not"])
        self.configure_summary_columns()
        self.summary.itemChanged.connect(self.on_summary_changed)
        self.summary.setMinimumHeight(340)
        self.summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rv.addWidget(self.summary, 1)  # Kalan dikey alanın ana bölümü sistem bileşenlerine ayrılsın

        # ── Boşluk + TESLİMATLAR ──────────────────────────
        rv.addSpacing(18)
        dh = QHBoxLayout()
        dh.addWidget(section_label("TESLİMATLAR"))
        dh.addStretch()

        ad = QPushButton("+ Teslimat Ekle")
        self.add_delivery_btn = ad
        ad.clicked.connect(self.add_delivery)
        dh.addWidget(ad)

        auto_btn = QPushButton("Otomatik Teslimat Oluştur")
        self.auto_accept_btn = auto_btn
        auto_btn.clicked.connect(lambda: open_auto_accept_dialog(self))
        dh.addWidget(auto_btn)

        rv.addLayout(dh)

        self.del_table = QTableWidget(0, 0)
        configure_table(self.del_table)
        self.del_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.del_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.del_table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.del_table.setMinimumHeight(118)
        self.del_table.setMaximumHeight(180)
        self.del_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.del_table.cellClicked.connect(self.on_delivery_clicked)
        self.del_table.horizontalHeader().setVisible(True)
        self.pinned_delivery = QTableWidget(0, 0)
        self.pinned_delivery.setObjectName("pinnedDelivery")
        self.pinned_delivery.setVisible(False)
        self.pinned_delivery.setMaximumHeight(0)

        rv.addWidget(self.del_table, 0)

        foot = QHBoxLayout(); foot.addStretch()
        save = QPushButton("Kaydet"); self.save_btn = save; save.clicked.connect(self.save_all)
        close = QPushButton("• Kapat"); close.setObjectName("secondary"); close.clicked.connect(self.reject)
        foot.addWidget(save); foot.addWidget(close); root.addLayout(foot)

    def build_busy_overlay(self):
        self.busy_overlay = QFrame(self)
        self.busy_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.82); }")
        self.busy_overlay.hide()
        self.busy_overlay.raise_()

        self.busy_card = QFrame(self.busy_overlay)
        self.busy_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.97); border: 1px solid #d8e2ed; border-radius: 12px; }"
            "QLabel { background: transparent; }"
        )
        lay = QVBoxLayout(self.busy_card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        self.busy_label = QLabel("İşlem yapılıyor...")
        self.busy_label.setObjectName("mainTitle")
        self.busy_label.setAlignment(Qt.AlignCenter)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setFormat("%p%")
        self.busy_progress.setTextVisible(True)
        lay.addWidget(self.busy_label)
        lay.addWidget(self.busy_progress)
        self.position_busy_overlay()

    def position_busy_overlay(self):
        if not hasattr(self, "busy_overlay"):
            return
        self.busy_overlay.setGeometry(self.rect())
        w, h = 420, 130
        x = max((self.busy_overlay.width() - w) // 2, 0)
        y = max((self.busy_overlay.height() - h) // 2, 0)
        self.busy_card.setGeometry(x, y, w, h)
        self.busy_overlay.raise_()

    def set_busy_overlay(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if not hasattr(self, "busy_overlay"):
            return
        if not hasattr(self, "_busy_cursor_on"):
            self._busy_cursor_on = False
        if visible:
            self.busy_label.setText(message)
            self.busy_progress.setRange(0, 100)
            self.busy_progress.setValue(int(max(0, min(100, percent))))
            self.position_busy_overlay()
            self.busy_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.busy_overlay.hide()
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    @staticmethod
    def _is_widget_inside(widget, parent_widget) -> bool:
        if widget is None or parent_widget is None:
            return False
        return widget is parent_widget or parent_widget.isAncestorOf(widget)

    def _side_meta_event_widget(self, obj, event):
        if isinstance(obj, QWidget):
            return obj
        global_pos = None
        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
        elif hasattr(event, "globalPos"):
            global_pos = event.globalPos()
        return QApplication.widgetAt(global_pos) if global_pos is not None else None

    def _is_side_meta_inside_click(self, obj, event) -> bool:
        widget = self._side_meta_event_widget(obj, event)
        popover = getattr(self, "side_meta_popover", None)
        bar = getattr(self, "side_meta_bar", None)
        return self._is_widget_inside(widget, popover) or self._is_widget_inside(widget, bar)

    def eventFilter(self, obj, event):
        # Bu dialogda da dosya kartları/event filter kullanılıyor. Silinmiş Qt
        # objelerine dokunmak PySide6'da uygulamayı abort ettirebildiği için
        # eventFilter içinde hiçbir hatanın dışarı kaçmasına izin vermiyoruz.
        try:
            if not qt_obj_alive(obj) or event is None:
                return False
            try:
                etype = event.type()
            except Exception:
                return False

            side_host = getattr(self, "side_meta_host", None)
            if obj is side_host and etype in (QEvent.Resize, QEvent.Show):
                self.position_side_meta_popover()
                self._place_tab_bar()

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
            try:
                traceback.print_exc()
            except Exception:
                pass
            return False

        return False


    def configure_summary_columns(self):
        header = self.summary.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setStretchLastSection(True)
        self.summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def update_timeline_bar(self):
        """Compact timeline bar varsa güncelle; yoksa sessizce geç."""
        if hasattr(self, '_tl_prog'):
            from datetime import date as _d
            today = _d.today()
            t0 = parse_iso_date(str(self.ci.t0_date or ""))
            comp = parse_iso_date(str(self.ci.completion_date or ""))
            pct = 0
            if t0 and comp and comp > t0:
                pct = max(0, min(100, int((today - t0).days * 100 / (comp - t0).days)))
            self._tl_prog.setValue(pct)
            self._tl_name_lbl.setText(str(self.ci.no or "—"))

    def _linked_contract_platforms(self) -> List[dict]:
        explicit = list(getattr(self.ci, "platforms", []) or [])
        if not explicit:
            names = list(getattr(self.ci, "platform_names", []) or [])
            ids = list(getattr(self.ci, "platform_ids", []) or [])
            explicit = [{"platform_id": int(ids[i]) if i < len(ids) else 0, "platform_name": name} for i, name in enumerate(names)]
        if getattr(self.ci, "entry_start_row", 0):
            try:
                rows = self.store.get_contract_platforms(int(getattr(self.ci, "entry_start_row", 0) or 0))
                if rows:
                    explicit = rows
            except Exception:
                pass
        base = str(self.ci.platform or "").strip()
        base_id = int(getattr(self.ci, "platform_id", 0) or getattr(self.ci, "primary_platform_id", 0) or 0)
        found: List[dict] = []
        seen = set()
        for item in explicit + ([{"platform_id": base_id, "platform_name": base}] if base else []):
            if isinstance(item, dict):
                pid = int(item.get("platform_id") or item.get("id") or 0)
                name = str(item.get("platform_name") or item.get("name") or "").strip()
                is_primary = bool(item.get("is_primary"))
            else:
                name = str(item or "").strip()
                pid = self.store.get_platform_id(name, create=False) or 0
                is_primary = False
            key = pid if pid else name.casefold()
            if name and key not in seen:
                seen.add(key)
                found.append({"platform_id": int(pid or 0), "platform_name": name, "is_primary": is_primary})
        return found



    def set_active_platform(self, platform_id: int):
        try:
            platform_id = int(platform_id or 0)
        except Exception:
            platform_id = 0
        linked = self._linked_contract_platforms()
        valid = {int(p.get("platform_id") or 0): str(p.get("platform_name") or "") for p in linked if int(p.get("platform_id") or 0)}
        if not platform_id or platform_id not in valid:
            primary = self.store.get_primary_contract_platform(int(getattr(self.ci, "entry_start_row", 0) or 0)) if getattr(self.ci, "entry_start_row", 0) else None
            platform_id = int((primary or {}).get("platform_id") or self.active_platform_id or 0)
            if not platform_id or platform_id not in valid:
                return
        if platform_id == int(getattr(self, "active_platform_id", 0) or 0):
            return
        self._cache_current_context()
        try:
            ci, systems, deliveries = self.store.load_contract_structure(
                self.ci.no,
                contract_no=self.ci.no,
                start_row=self.ci.entry_start_row,
                contract_type=self.ci.contract_type,
                platform_id=platform_id,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Platform yüklenemedi", f"Seçilen platform verisi yüklenemedi:\n{exc}")
            return
        self.active_platform_id = platform_id
        self.ci.platform = valid.get(platform_id, str(getattr(ci, "platform", "") or ""))
        self.ci.platform_id = platform_id
        setattr(self.ci, "platforms", linked)
        setattr(self.ci, "platform_names", [p.get("platform_name") for p in linked])
        setattr(self.ci, "platform_ids", [int(p.get("platform_id") or 0) for p in linked if int(p.get("platform_id") or 0)])
        self.systems = systems or []
        self.deliveries = deliveries or {}
        self.selected_system = self.systems[0].name if self.systems else None
        self.expanded_delivery_index = None
        self.refresh_contract_header()
        self.refresh()

    def refresh_contract_header(self):
        if not hasattr(self, "meta_values"):
            return
        users = [str(x).strip() for x in (list(getattr(self.ci, "users", []) or [])) if str(x).strip()]
        if not users:
            users = [x.strip() for x in re.split(r"[,;]+", str(self.ci.user or "")) if x.strip()]
        user_text = "-" if not users else (users[0] if len(users) == 1 else f"{users[0]} +{len(users) - 1}")
        mapping = {
            "no": self.ci.no,
            "type": self.ci.contract_type,
            "responsible_engineer": str(getattr(self.ci, "responsible_engineer_name", "") or "-").strip() or "-",
            "user": user_text,
            "status": self.ci.status or "Başlanmadı",
        }
        for k, v in mapping.items():
            lab = self.meta_values.get(k)
            if lab:
                lab.setText(str(v or "-"))
                if k == "user":
                    lab.setToolTip("\n".join(users))
        tabs = getattr(self, "platform_tabs_widget", None)
        if tabs:
            tabs.set_platforms(self._linked_contract_platforms(), self.active_platform_id)

    def _notify_parent_contract_updated(self, old_platform: str, new_platform: str) -> None:
        """Ana bilgi güncellemesi sonrası ana listeyi ve açık takvimi tazeler."""
        parent = self.parent()
        if not parent:
            return
        try:
            if hasattr(parent, "request_refresh"):
                old_p = str(old_platform or "").strip()
                new_p = str(new_platform or "").strip()
                if old_p and new_p and old_p != new_p:
                    parent.request_refresh(select_platform=old_p, scope="platform", platform=old_p)
                    parent.request_refresh(select_platform=new_p, scope="platform", platform=new_p)
                else:
                    target = new_p or old_p
                    parent.request_refresh(select_platform=target, scope="platform", platform=target)
            elif hasattr(parent, "refresh_open_calendar"):
                parent.refresh_open_calendar()
        except Exception:
            pass

    def edit_contract_info(self):
        if not self._ensure_share_can_edit("Ana Bilgileri Düzenle"):
            return
        setattr(self.ci, "platforms", self._linked_contract_platforms())
        dlg = ContractEditDialog(self.store, self.ci, self)
        if not dlg.exec() or not dlg.result:
            return

        new_ci = dlg.result
        previous_platforms = self._linked_contract_platforms()
        previous_platform_names = [str(p.get("platform_name") or "").strip() if isinstance(p, dict) else str(p or "").strip() for p in previous_platforms]
        previous_platform_keys = {p.casefold() for p in previous_platform_names if p}
        candidate_platforms = list(getattr(new_ci, "platforms", []) or getattr(new_ci, "platform_names", []) or [])
        added_platforms = []
        for item in candidate_platforms:
            name = str(item.get("platform_name") or item.get("name") or "").strip() if isinstance(item, dict) else str(item or "").strip()
            if name and name.casefold() not in previous_platform_keys:
                added_platforms.append(name)
        old_platform = str(self.ci.platform or "").strip()
        old_no       = str(self.ci.no or "").strip()
        old_type     = str(self.ci.contract_type or "").strip()

        # SD bağlantı bilgilerini koru
        if re.match(r"^SD-\d+$", str(new_ci.contract_type or "").strip().upper()):
            for attr in ("sd_anchor_start_row", "sd_anchor_end_row",
                         "sd_anchor_platform", "sd_anchor_no"):
                if not getattr(new_ci, attr, None):
                    setattr(new_ci, attr, getattr(self.ci, attr, None))

        new_ci.entry_start_row = self.original_entry_start_row
        self.ci = new_ci
        self._set_dirty()

        # Excel'e yaz
        try:
            self.sync_summary_to_system()
            self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
            with self.store.batch_save():
                written_start = self.store.write_contract(
                    self.ci,
                    self.systems,
                    self.deliveries,
                    old_contract_no=old_no,
                    old_start_row=self.original_entry_start_row,
                )
                # Etiket anahtarı değişmişse taşı
                new_platform = str(self.ci.platform or "").strip()
                new_no       = str(self.ci.no or "").strip()
                new_type     = str(self.ci.contract_type or "").strip()
                actor = self.store.current_actor()
                if (self.store._normalize_label(old_type) == self.store._normalize_label("Ana Sözleşme") and
                        old_platform == new_platform and old_no != new_no):
                    self.store.update_linked_sd_contract_numbers(
                        new_platform, old_no, new_no, actor=actor
                    )
                if (old_platform, old_no, old_type) != (new_platform, new_no, new_type):
                    self.store.save_contract_tags(old_platform, old_no, old_type, [], actor=actor)
                self.store.save_contract_tags(
                    new_platform, new_no, new_type, self.contract_tags, actor=actor)
                existing_keys = {p.casefold() for p in previous_platform_names}
                existing_keys.add(new_platform.casefold())
                for platform_name in added_platforms:
                    platform_name = str(platform_name or "").strip()
                    if not platform_name or platform_name.casefold() in existing_keys or platform_name == new_platform:
                        continue
                    extra_ci = copy.copy(self.ci)
                    extra_ci.platform = platform_name
                    extra_ci.entry_start_row = 0
                    extra_ci.sd_anchor_platform = ""
                    extra_ci.sd_anchor_no = ""
                    self.store.write_contract(extra_ci, self.systems, self.deliveries)
                    self.store.save_contract_tags(platform_name, new_no, new_type, self.contract_tags, actor=actor)
                    existing_keys.add(platform_name.casefold())

            self.original_entry_start_row = int(written_start or 0)
            self.original_platform        = new_platform
            self.original_contract_no     = new_no
            self.original_contract_type   = new_type
            self.ci.entry_start_row       = self.original_entry_start_row

            self.refresh_contract_header()
            self.update_timeline_bar()
            self._initial_snapshot = self._make_data_snapshot()
            self._is_dirty = False
            self._notify_parent_contract_updated(old_platform, new_platform)
            QMessageBox.information(self, "Güncellendi", "Ana bilgiler başarıyla güncellendi.")
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Güncelleme sırasında hata:\n{exc}")

    def _start_contract_save_worker(self, worker: ContractSaveWorker, message: str):
        if self._contract_save_thread and self._contract_save_thread.isRunning():
            return False
        self.set_busy_overlay(True, message, 0)
        thread = QThread(self)
        self._contract_save_thread = thread
        self._contract_save_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_contract_save_progress)
        worker.finished.connect(self.on_contract_save_finished)
        worker.failed.connect(self.on_contract_save_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_contract_save_refs)
        parent = self.parent()
        if parent and hasattr(parent, "on_contract_save_progress"):
            worker.progress.connect(parent.on_contract_save_progress)
        thread.start()
        return True

    def _clear_contract_save_refs(self):
        self._contract_save_thread = None
        self._contract_save_worker = None

    def on_contract_save_progress(self, percent: int, message: str):
        self.set_busy_overlay(True, message, percent)

    def on_contract_save_finished(self, payload: dict):
        self.set_busy_overlay(False)
        parent = self.parent()
        if parent and hasattr(parent, "set_busy_overlay"):
            parent.set_busy_overlay(False)
        action = str((payload or {}).get("action") or "")
        try:
            self.store.reload_from_disk()
            if action == "delete":
                info = dict((payload or {}).get("result") or {})
                if not info:
                    QMessageBox.warning(self, "Hata", "Sözleşme bulunamadı veya silinemedi.")
                    return
                self._drop_deleted_context_cache(info)
                self.deleted_contract_info = info
                QMessageBox.information(self, "Silindi", "Sözleşme silindi.")
                self.accept()
                return

            ctx = self._pending_contract_save_context or {}
            old_key = ctx.get("old_key") or ("", "", "")
            new_key = ctx.get("new_key") or ("", "", "")
            actor = ctx.get("actor") or self.store.current_actor()
            with self.store.batch_save():
                if old_key != new_key and all(old_key):
                    self.store.save_contract_tags(old_key[0], old_key[1], old_key[2], [], actor=actor)
                self.store.save_contract_tags(new_key[0], new_key[1], new_key[2], ctx.get("tags") or [], actor=actor)
            written_start = int((payload or {}).get("start_row") or 0)
            self.original_entry_start_row = written_start
            self.original_platform = new_key[0]
            self.ci.entry_start_row = self.original_entry_start_row
            self.original_contract_no = new_key[1]
            self.original_contract_type = new_key[2]
            # Yeni sözleşme kaydedildikten sonra pending belgeleri DB'ye aktar
            if getattr(self, "is_new_contract", False) and (self._pending_doc_folders or self._pending_doc_files):
                try:
                    self._flush_pending_documents_to_db()
                except Exception as flush_exc:
                    QMessageBox.warning(self, "Belge aktarma hatası",
                        f"Sözleşme kaydedildi ancak belgeler aktarılırken hata oluştu:\n{flush_exc}")
            self.is_new_contract = False
            self.refresh_sd_sidebar()
            QMessageBox.information(self, "Kaydedildi", "Sözleşme kaydedildi.")
            self._is_dirty = False
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"İşlem tamamlandıktan sonra arayüz güncellenirken hata:\n{exc}")
        finally:
            self._pending_contract_save_context = None

    def on_contract_save_failed(self, message: str):
        self.set_busy_overlay(False)
        parent = self.parent()
        if parent and hasattr(parent, "set_busy_overlay"):
            parent.set_busy_overlay(False)
        self._pending_contract_save_context = None
        QMessageBox.critical(self, "Hata", f"Kaydetme işlemi sırasında hata:\n{message}")

    def delete_contract(self):
        if not self._ensure_share_can_edit("Sözleşmeyi Sil"):
            return
        if not self.require_permission_ui("delete_contracts", "Sözleşmeyi Sil"):
            return
        no = str(self.ci.no or "").strip()
        platform = str(self.ci.platform or "").strip()
        if not no or not platform:
            QMessageBox.warning(self, "Eksik", "Silinecek sözleşme bilgisi bulunamadı.")
            return
        msg = (
            f"{platform} platformundaki '{no}' sözleşmesi silinecek.\n\n"
            "Bu işlem tüm sistemler ve teslimatlar ile birlikte kalıcı olarak kaldırır.\n"
            "Devam etmek istiyor musunuz?"
        )
        if not ask_yes_no(self, "Sözleşmeyi Sil", msg):
            return
        worker = ContractSaveWorker(
            self.store.path,
            "delete",
            platform,
            no,
            start_row=self.original_entry_start_row if self.original_entry_start_row > 0 else 0,
            actor=self.store.current_actor(),
            store=self.store,
        )
        self._start_contract_save_worker(worker, "Sözleşme siliniyor...")

    def _tag_key(self, name: str) -> str:
        return normalized_tag_key(name)

    def build_side_meta_popover_bar(self, parent_width: int):
        """Build the compact meta bar and its layout-independent floating popover."""
        self._side_meta_open_panel = None
        self._side_meta_last_panel = "files"
        self._side_meta_manual_height = None
        self._side_meta_files: List[dict] = []
        self.side_meta_bar = QFrame()
        self.side_meta_bar.setObjectName("sideMetaBar")
        self.side_meta_bar.setAutoFillBackground(False)
        self.side_meta_bar.setAttribute(Qt.WA_TranslucentBackground, True)
        self.side_meta_bar.setStyleSheet("QFrame#sideMetaBar { background:transparent; border:0; }")
        bar_layout = QHBoxLayout(self.side_meta_bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(10)

        self.side_btn_tags = BadgeTabButton("🏷", "Etiketler", 0)
        self.side_btn_files = BadgeTabButton("📎", "Belgeler", 0)
        self.side_btn_share = BadgeTabButton("↗", "Paylaşım", None)
        self.side_btn_share.badge.hide()

        tabs_controller = getattr(self, "contract_action_tabs", None)
        for panel, button in (("tags", self.side_btn_tags), ("files", self.side_btn_files), ("share", self.side_btn_share)):
            if panel == "tags" and tabs_controller is not None:
                button.clicked.connect(lambda _checked=False, ctl=tabs_controller: ctl.open_tags())
            elif panel == "files" and tabs_controller is not None:
                button.clicked.connect(lambda _checked=False, ctl=tabs_controller: ctl.open_files())
            elif panel == "share" and tabs_controller is not None:
                button.clicked.connect(lambda _checked=False, ctl=tabs_controller: ctl.open_share())
            else:
                button.clicked.connect(lambda _checked=False, name=panel: self.toggle_side_meta_popover(name))
            # Keep the tab body flush with the overlay host's top edge.  The host
            # is a transparent sibling overlay (not a child of the header), so any
            # vertical slack above the first tab is painted by the dialog/root
            # background rather than by the navy header underneath.
            bar_layout.addWidget(button, 0, Qt.AlignTop)

        bar_layout.addStretch(1)

        # Eski sağdaki küçük chevron hücresi görsel olarak boş/işlevsiz bir kutu gibi
        # duruyordu. Popover aç/kapatma zaten sekme butonlarından yapıldığı için layout'a
        # ekstra buton eklemiyoruz.
        self.side_chevron = None

        self.side_meta_popover = QFrame(self)
        self.side_meta_popover.setObjectName("sideMetaPopover")
        self.side_meta_popover.setStyleSheet(
            "QFrame#sideMetaPopover{background:#ffffff; border:1px solid #c8d9ed; border-radius:12px;}"
            "QPushButton#sidePanelAdd{background:#2563eb; color:#0f172a; border:0; border-radius:8px; font-size:20px; font-weight:900; padding:0;}"
            "QPushButton#sidePanelAdd:hover{background:#1d4ed8;}"
            "QPushButton#documentActionPrimary{background:#2563eb; color:#0f172a; border:1px solid #2563eb; border-radius:9px; padding:0 12px; font-size:11px; font-weight:700; min-height:28px; max-height:32px;}"
            "QPushButton#documentActionPrimary:hover{background:#1d4ed8; border-color:#1d4ed8;}"
            "QPushButton#documentAction{background:#f8fbff; color:#102a43; border:1px solid #cfe0f3; border-radius:9px; padding:0 12px; font-size:11px; font-weight:700; min-height:28px; max-height:32px;}"
            "QPushButton#documentAction:hover{background:#edf5ff; border-color:#9ec5f8;}"
            "QPushButton#documentLockButton{background:#f8fbff; color:#0f172a; border:1px solid #cfe0f3; border-radius:9px; padding:0; font-size:15px; font-weight:700; min-width:30px; max-width:30px; min-height:28px; max-height:30px;}"
            "QPushButton#documentLockButton:hover{background:#edf5ff; border-color:#9ec5f8;}"
            "QPushButton#documentLockButton[locked=\"true\"]{background:#fff7ed; color:#9a3412; border-color:#fed7aa;}"
            "QLabel#documentLockInfo{background:#fff7ed; color:#9a3412; border:1px solid #fed7aa; border-radius:8px; padding:4px 8px; font-size:10px; font-weight:700;}"
            "QLabel#documentHint{background:transparent; color:#94a3b8; border:0; font-size:10px; padding:0;}"
            "QFrame#docDropZone{background:#f8fbff; border:1px dashed #c7d7ea; border-radius:8px;}"
            "QFrame#docDropZone[dragOver=\"true\"]{background:#eef6ff; border-color:#2563eb;}"
            "QLabel#sidePanelEmpty{background:transparent; color:#7b8da5; border:0; font-size:12px;}"
            "QLabel#sidePanelEmptySub{background:transparent; color:#94a3b8; border:0; font-size:10px;}"
            "QFrame#docFooterBar{background:#f8fbff; border-top:1px solid #e6eef8; border-bottom-left-radius:10px; border-bottom-right-radius:10px;}"
            "QLabel#documentsFooterLeft{background:transparent; color:#94a3b8; border:0; font-size:10px;}"
            "QLabel#documentsFooterRight{background:transparent; color:#334155; border:0; font-size:10px; font-weight:700;}"
            "QLabel#sidePanelEmptyTag{background:#f8fbff; color:#64748b; border:1px dashed #c7d6e8; border-radius:8px; padding:13px; font-size:12px;}"
            "QPushButton#sidePanelAddInline{background:#eef4ff; color:#1d4ed8; border:1px solid #bcd1f2; border-radius:8px; padding:2px 10px; font-size:11px; font-weight:700;}"
            "QPushButton#sidePanelAddInline:hover{background:#dbeafe;}"
        )
        shadow = QGraphicsDropShadowEffect(self.side_meta_popover)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(15, 45, 74, 45))
        self.side_meta_popover.setGraphicsEffect(shadow)
        popover_layout = QVBoxLayout(self.side_meta_popover)
        popover_layout.setContentsMargins(12, 6, 12, 4)
        popover_layout.setSpacing(6)
        self.side_meta_arrow = QLabel("▲")
        self.side_meta_arrow.setObjectName("sideMetaArrow")
        self.side_meta_arrow.setStyleSheet("QLabel#sideMetaArrow{background:transparent;color:#c8d9ed;border:0;font-size:14px;margin:0;padding:0;}")
        popover_layout.addWidget(self.side_meta_arrow, 0, Qt.AlignLeft)
        self.side_meta_popover_body = QWidget()
        self.side_meta_popover_body.setStyleSheet("background:transparent;")
        self.side_meta_popover_body_layout = QVBoxLayout(self.side_meta_popover_body)
        self.side_meta_popover_body_layout.setContentsMargins(0, 0, 0, 0)
        self.side_meta_popover_body_layout.setSpacing(6)
        from PySide6.QtWidgets import QSizePolicy as _QSP
        self.side_meta_popover_body.setSizePolicy(_QSP.Expanding, _QSP.Minimum)
        popover_layout.addWidget(self.side_meta_popover_body, 0)
        popover_layout.addStretch(1)

        _rh = QFrame()
        _rh.setFixedHeight(7)
        _rh.setCursor(Qt.SizeVerCursor)
        _rh.setObjectName("popoverResizeHandle")
        _rh.setStyleSheet(
            "QFrame#popoverResizeHandle{background:transparent;border:0;border-top:2px solid transparent;}"
            "QFrame#popoverResizeHandle:hover{background:#e8f0fe;border-top:2px solid #93c5fd;border-radius:3px;}"
        )
        _rh.setToolTip("Paneli yeniden boyutlandır")
        _rh_drag = [None, None]

        def _rh_press(event, _s=self):
            if event.button() == Qt.LeftButton:
                try:
                    _rh_drag[0] = event.globalPosition().toPoint().y()
                except AttributeError:
                    _rh_drag[0] = event.globalPos().y()
                _rh_drag[1] = _s.side_meta_popover.height()

        def _rh_move(event, _s=self):
            if _rh_drag[0] is None:
                return
            try:
                cur_y = event.globalPosition().toPoint().y()
            except AttributeError:
                cur_y = event.globalPos().y()
            delta = cur_y - _rh_drag[0]
            new_h = max(190, _rh_drag[1] + delta)
            screen = _s.screen()
            avail_h = screen.availableGeometry().height() if screen else 900
            new_h = min(new_h, avail_h - 120)
            _s._side_meta_manual_height = new_h
            _s.position_side_meta_popover()

        def _rh_release(event):
            _rh_drag[0] = None
            _rh_drag[1] = None

        _rh.mousePressEvent = _rh_press
        _rh.mouseMoveEvent = _rh_move
        _rh.mouseReleaseEvent = _rh_release
        popover_layout.addWidget(_rh, 0)

        self.side_meta_popover.hide()
        QApplication.instance().installEventFilter(self)
        self.position_side_meta_popover()

    def _place_tab_bar(self):
        """Sekme barını Durum hücresinin altına, header altından sarkacak şekilde konumlandır."""
        header = getattr(self, "contract_header", None)
        bar = getattr(self, "side_meta_bar", None)
        host = getattr(self, "side_meta_host", None)
        if not header or not bar or not host:
            return
        try:
            bar_h = 46

            # Header'ın dialog içindeki kesin konumu
            header_global = header.mapTo(self, QPoint(0, 0))
            hy = header_global.y()
            hh = header.height()

            # X: Durum hücresinin (metaCell) tam sol kenarı
            status_val = (getattr(self, "meta_values", {}) or {}).get("status")
            sx = None
            if status_val is not None:
                # status_val → headerStatusWrap → metaCell zincirini çık
                w = status_val
                for _ in range(4):  # en fazla 4 seviye üste çık
                    if w is None:
                        break
                    if w.objectName() == "metaCell":
                        sx = w.mapTo(self, QPoint(0, 0)).x()
                        break
                    w = w.parent()

            edit_btn = getattr(self, "header_edit_btn", None)
            if sx is None or edit_btn is None or edit_btn.width() <= 0 or header.width() <= 0:
                # Header/edit butonu henüz layout'a yerleşmemiş (örn. pencere hâlâ
                # maksimize animasyonu sürüyor — özellikle uzak masaüstü/VM
                # ortamlarında bu birkaç saniye sürebilir). Tahmini/yanlış bir
                # konuma göre barı göstermek yerine kısa aralıklarla, cömert bir
                # süre boyunca tekrar dene. Bar bu sırada gizli kalır.
                retries = getattr(self, "_place_tab_bar_retries", 0)
                if retries < 400:  # 15ms * 400 ≈ 6 sn — yavaş maksimize animasyonlarını kapsar
                    self._place_tab_bar_retries = retries + 1
                    QTimer.singleShot(15, self._place_tab_bar)
                return

            self._place_tab_bar_retries = 0

            # Sağ sınır: "Ana Bilgileri Düzenle" butonunun tam sol kenarı - 10px boşluk
            right_edge = edit_btn.mapTo(self, QPoint(0, 0)).x() - 10

            available_w = max(280, self.width() - 24)
            desired_w = min(available_w, max(470, right_edge - sx))
            x = max(12, min(sx, right_edge - desired_w))
            host_w = desired_w

            # Y: header'ın tam altından başlasın — biraz içeri girmez
            y = hy + hh - 2  # 2px header'a yapışık

            host.setGeometry(x, y, host_w, bar_h)
            bar.setFixedWidth(host_w)
            bar.setFixedHeight(bar_h)
            host.setVisible(True)
            host.raise_()
        except Exception:
            import traceback; traceback.print_exc()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()
        QTimer.singleShot(30, self._place_tab_bar)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._place_tab_bar)

    def position_side_meta_popover(self):
        if not hasattr(self, "side_meta_popover") or not hasattr(self, "side_meta_host"):
            return
        host = self.side_meta_host
        if getattr(self, "_side_meta_open_panel", None) == "share":
            w = 360
        else:
            w = max(320, min(470, host.width() if host.width() > 0 else 380))
        self.side_meta_popover.setFixedWidth(w)
        self.side_meta_popover.adjustSize()
        hint_h = self.side_meta_popover.sizeHint().height()
        # Popover self içinde: host konumundan itibaren bar altına yap
        bar_h = self.side_meta_bar.height() if hasattr(self, "side_meta_bar") else 38
        pop_x = host.x() + host.width() - w
        pop_y = host.y() + bar_h + 8
        pop_x = max(8, min(pop_x, max(8, self.width() - w - 8)))
        # Ekranın kullanılabilir yüksekliğini hesaba kat
        screen = self.screen()
        if screen:
            avail_h = screen.availableGeometry().height()
        else:
            avail_h = 900
        max_h = max(190, min(avail_h - 120, self.height() - pop_y - 8))
        # Manuel yükseklik kullanıcı tarafından ayarlandıysa öncelikli kullan
        manual_h = getattr(self, "_side_meta_manual_height", None)
        if getattr(self, "_side_meta_open_panel", None) == "files":
            files = list(getattr(self, "_side_meta_files", []))
            folders = list(getattr(self, "_side_meta_folders", []))
            tree_h = self.document_tree_height(folders, files)
            auto_min_h = max(190, tree_h + 94)
            if manual_h is not None:
                min_h = max(190, min(manual_h, max_h))
            else:
                min_h = auto_min_h
        elif getattr(self, "_side_meta_open_panel", None) == "share":
            min_h = 250
            manual_h = None
        else:
            min_h = 110
            manual_h = None
        h = max(min_h, min(hint_h if manual_h is None else manual_h, max_h))
        self.side_meta_popover.setGeometry(pop_x, pop_y, w, h)
        self._position_side_meta_arrow()
        if self.side_meta_popover.isVisible():
            self.side_meta_popover.raise_()

    def _position_side_meta_arrow(self):
        arrow = getattr(self, "side_meta_arrow", None)
        if arrow is None:
            return
        panel = getattr(self, "_side_meta_open_panel", None)
        button = {
            "tags": getattr(self, "side_btn_tags", None),
            "files": getattr(self, "side_btn_files", None),
            "share": getattr(self, "side_btn_share", None),
        }.get(panel)
        if button is None:
            arrow.setStyleSheet("QLabel#sideMetaArrow{background:transparent;color:#c8d9ed;border:0;font-size:14px;margin-left:12px;padding:0;}")
            return
        try:
            center = button.mapTo(self, QPoint(button.width() // 2, 0)).x() - self.side_meta_popover.x()
        except Exception:
            center = 18
        left = max(8, min(center - 7, max(8, self.side_meta_popover.width() - 24)))
        arrow.setStyleSheet(f"QLabel#sideMetaArrow{{background:transparent;color:#c8d9ed;border:0;font-size:14px;margin-left:{left}px;padding:0;}}")

    def _toggle_side_meta_chevron(self):
        if self._side_meta_open_panel:
            self.close_side_meta_popover()
        else:
            self.toggle_side_meta_popover(self._side_meta_last_panel or "files")

    def toggle_side_meta_popover(self, panel: str):
        if panel not in {"tags", "files", "share"}:
            return
        if self._side_meta_open_panel == panel and self.side_meta_popover.isVisible():
            self.close_side_meta_popover()
            return
        self._side_meta_open_panel = panel
        self._side_meta_last_panel = panel
        self.update_side_meta_badges()
        self.render_side_meta_popover_content(panel)
        self._sync_side_meta_controls()
        self.side_meta_popover.show()
        self.side_meta_popover.raise_()
        QApplication.processEvents()
        self.position_side_meta_popover()
        # Kısa opacity fade — konum/boyut değişmez
        _eff = QGraphicsOpacityEffect(self.side_meta_popover)
        self.side_meta_popover.setGraphicsEffect(_eff)
        _anim = QPropertyAnimation(_eff, b"opacity", self.side_meta_popover)
        _anim.setDuration(130)
        _anim.setStartValue(0.0)
        _anim.setEndValue(1.0)
        _anim.finished.connect(lambda: self.side_meta_popover.setGraphicsEffect(None))
        _anim.start(QPropertyAnimation.DeleteWhenStopped)

    def close_side_meta_popover(self):
        self._side_meta_open_panel = None
        if hasattr(self, "side_meta_popover"):
            self.side_meta_popover.hide()
        self._sync_side_meta_controls()

    def _sync_side_meta_controls(self):
        panel = self._side_meta_open_panel
        for name, button in (("tags", self.side_btn_tags), ("files", self.side_btn_files), ("share", self.side_btn_share)):
            button.setChecked(name == panel)
        chevron = getattr(self, "side_chevron", None)
        if chevron is not None:
            chevron.setText("∧" if panel else "∨")

    def _load_contract_files(self) -> List[dict]:
        if self.is_new_contract:
            # Pending modda: in-memory listeden oku
            folders_by_id = {f["id"]: f for f in self._pending_doc_folders}
            out = []
            for f in self._pending_doc_files:
                item = dict(f)
                fid = f.get("folder_id")
                folder = folders_by_id.get(fid) if fid else None
                item["folder_path"] = folder.get("name", "") if folder else ""
                out.append(item)
            return out
        try:
            return list(self.store.list_contract_files(self.ci.platform, self.ci.no, self.ci.contract_type))
        except Exception:
            return []

    def _load_contract_file_folders(self) -> List[dict]:
        if self.is_new_contract:
            return list(self._pending_doc_folders)
        try:
            return list(self.store.list_contract_file_folders(self.ci.platform, self.ci.no, self.ci.contract_type))
        except Exception:
            return []

    def _set_side_meta_badge_counts(self, tag_count: int, file_count: int):
        self.side_btn_tags.setCount(tag_count)
        self.side_btn_files.setCount(file_count)

    def update_side_meta_badges(self):
        self._side_meta_files = self._load_contract_files()
        self._side_meta_folders = self._load_contract_file_folders()
        self._set_side_meta_badge_counts(len(self._ordered_contract_tags()), len(self._side_meta_files))

    def _clear_side_meta_popover_body(self):
        layout = self.side_meta_popover_body_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()

    def _document_db_conn(self):
        return getattr(getattr(self.store, "db", None), "conn", None)

    def _document_db_contract_id(self) -> int | None:
        """Açık sözleşmenin DB contract_id'sini döner. STS dışında None."""
        if not hasattr(self.store, "_resolve_contract_id"):
            return None
        ci = getattr(self, "ci", None)
        if ci is None:
            return None
        return self.store._resolve_contract_id(
            str(ci.platform or ""),
            str(ci.no or ""),
            str(ci.contract_type or "Ana Sözleşme"),
        )

    def _default_document_lock_state(self) -> dict:
        return {
            "contract_id": None,
            "is_locked": 0,
            "locked_by_staff_id": None,
            "locked_by_device_name": None,
            "locked_by_full_name": None,
            "locked_at": None,
            "updated_at": None,
        }

    def _load_document_lock_state(self) -> dict:
        try:
            conn = self._document_db_conn()
            if conn is None:
                self._document_lock_state = self._default_document_lock_state()
                return dict(self._document_lock_state)
            if hasattr(self.store, "document_lock_state"):
                ci = getattr(self, "ci", None)
                if ci is not None:
                    self._document_lock_state = self.store.document_lock_state(
                        str(ci.platform or ""),
                        str(ci.no or ""),
                        str(ci.contract_type or "Ana Sözleşme"),
                    )
                    return dict(self._document_lock_state)
            cid = self._document_db_contract_id()
            if cid is None:
                self._document_lock_state = self._default_document_lock_state()
                return dict(self._document_lock_state)
            getter = getattr(auth, "get_document_lock_state", None)
            if not callable(getter):
                self._document_lock_state = self._default_document_lock_state()
                return dict(self._document_lock_state)
            self._document_lock_state = getter(conn, cid)
            return dict(self._document_lock_state)
        except Exception:
            traceback.print_exc()
            # Belgeler paneli, lock state okunamadığında beyaz kalmasın;
            # güvenli varsayılan olarak kilit açık kabul edilir.
            self._document_lock_state = self._default_document_lock_state()
            return dict(self._document_lock_state)

    def _current_document_lock_state(self) -> dict:
        return dict(getattr(self, "_document_lock_state", {}) or self._load_document_lock_state())

    def _documents_access_allowed(self, lock_state: Optional[dict] = None) -> bool:
        state = lock_state or self._current_document_lock_state()
        checker = getattr(auth, "can_current_staff_access_documents", None)
        if callable(checker):
            return checker(state, self.current_staff)
        if int((state or {}).get("is_locked") or 0) == 0:
            return True
        return bool(
            self.current_staff
            and str((self.current_staff or {}).get("device_name") or "") == str((state or {}).get("locked_by_device_name") or "")
        )

    def _document_lock_same_device(self, lock_state: Optional[dict] = None) -> bool:
        state = lock_state or self._current_document_lock_state()
        return bool(
            int(state.get("is_locked") or 0) == 1
            and self.current_staff
            and str((self.current_staff or {}).get("device_name") or "") == str(state.get("locked_by_device_name") or "")
        )

    def _document_unlock_with_password(self, lock_state: Optional[dict] = None) -> bool:
        conn = self._document_db_conn()
        if conn is None:
            return False
        unlock_dialog = getattr(auth, "require_document_unlock_password", None)
        if not callable(unlock_dialog):
            QMessageBox.warning(
                self,
                "Belgeler Kilitli",
                "Belge kilidi doğrulama fonksiyonu yüklenemedi. Lütfen uygulamayı güncel kodla yeniden başlatın.",
            )
            return False
        if unlock_dialog(self, conn, lock_state or self._current_document_lock_state()):
            self._load_document_lock_state()
            self.render_contract_files()
            return True
        return False

    def _ensure_document_access(self, interactive: bool = True) -> bool:
        state = self._load_document_lock_state()
        if self._documents_access_allowed(state):
            return True
        if interactive:
            return self._document_unlock_with_password(state)
        return False

    def _animate_document_lock_button(self):
        btn = getattr(self, "document_lock_btn", None)
        if not btn:
            return
        rect = btn.geometry()
        grow = rect.adjusted(-2, -2, 2, 2)
        anim = QPropertyAnimation(btn, b"geometry", btn)
        anim.setDuration(160)
        anim.setStartValue(rect)
        anim.setKeyValueAt(0.5, grow)
        anim.setEndValue(rect)
        anim.start()
        self._document_lock_anim = anim

    def _toggle_document_lock(self):
        if not self._ensure_share_can_edit("Belge Kilidi"):
            return
        state = self._load_document_lock_state()
        if int(state.get("is_locked") or 0) == 0:
            if not self.require_permission_ui("lock_documents", "Belge Kilitleme"):
                return
        elif self._document_lock_same_device(state):
            if not self.require_permission_ui("unlock_own_documents", "Belge Kilidi"):
                return
        elif not self.require_permission_ui("unlock_all_documents", "Belge Kilidi"):
            return
        conn = self._document_db_conn()
        if conn is None:
            QMessageBox.information(self, "Belgeler", "Belge kilidi yalnızca STS veri dosyalarında desteklenir.")
            return
        state = self._load_document_lock_state()
        if int(state.get("is_locked") or 0) == 0:
            if not self.current_staff:
                QMessageBox.warning(self, "Personel gerekli", "Belgeleri kilitlemek için personel girişi gereklidir.")
                return
            if hasattr(self.store, "lock_documents"):
                ci = getattr(self, "ci", None)
                self._document_lock_state = self.store.lock_documents(
                    str(ci.platform or "") if ci else "",
                    str(ci.no or "") if ci else "",
                    self.current_staff,
                    str(ci.contract_type or "Ana Sözleşme") if ci else "Ana Sözleşme",
                )
            else:
                lock_fn = getattr(auth, "lock_documents", None)
                if not callable(lock_fn):
                    QMessageBox.warning(self, "Belgeler", "Belge kilidi fonksiyonu yüklenemedi. Lütfen uygulamayı güncel kodla yeniden başlatın.")
                    return
                cid = self._document_db_contract_id()
                if cid is None:
                    QMessageBox.warning(self, "Belgeler", "Sözleşme ID'si bulunamadı.")
                    return
                self._document_lock_state = lock_fn(conn, cid, self.current_staff)
            self._animate_document_lock_button()
            self.render_contract_files()
            return
        if self._document_lock_same_device(state):
            actor = str((self.current_staff or {}).get("full_name") or "Personel")
            if hasattr(self.store, "unlock_documents"):
                ci = getattr(self, "ci", None)
                self._document_lock_state = self.store.unlock_documents(
                    str(ci.platform or "") if ci else "",
                    str(ci.no or "") if ci else "",
                    actor=actor,
                    contract_type=str(ci.contract_type or "Ana Sözleşme") if ci else "Ana Sözleşme",
                )
            else:
                unlock_fn = getattr(auth, "unlock_documents", None)
                if not callable(unlock_fn):
                    QMessageBox.warning(self, "Belgeler", "Belge kilidi açma fonksiyonu yüklenemedi. Lütfen uygulamayı güncel kodla yeniden başlatın.")
                    return
                cid = self._document_db_contract_id()
                if cid is None:
                    return
                self._document_lock_state = unlock_fn(conn, cid)
            self._animate_document_lock_button()
            self.render_contract_files()
            return
        if self._document_unlock_with_password(state):
            self._animate_document_lock_button()

    def _document_lock_summary_text(self, lock_state: Optional[dict] = None) -> str:
        state = lock_state or self._current_document_lock_state()
        if int(state.get("is_locked") or 0) == 0:
            return ""
        if self._document_lock_same_device(state):
            return "🔒 Belgeler bu cihaz tarafından kilitlendi."
        locked_by = str(state.get("locked_by_full_name") or "Personel")
        return f"🔒 Belgeler kilitli · Kilitleyen: {locked_by}"

    def render_side_meta_popover_content(self, panel: str):
        self._clear_side_meta_popover_body()
        body = self.side_meta_popover_body_layout
        if panel == "share":
            body.addWidget(ContractSharePopover(self, self.side_meta_popover_body), 0)
            return
        if panel == "tags":
            # + butonu scroll'dan önce değil, kart listesinin en üstünde kompakt satır
            add_row = QHBoxLayout(); add_row.setContentsMargins(0, 0, 0, 2); add_row.addStretch(1)
            add_btn = QPushButton("+ Etiket Ekle"); add_btn.setObjectName("sidePanelAddInline")
            add_btn.setFixedHeight(26); add_btn.setEnabled(not self._share_labels_disabled()); add_btn.clicked.connect(self.open_tag_assign_dialog)
            if self._share_labels_disabled():
                add_btn.setToolTip(self._share_label_policy_message())
            add_row.addWidget(add_btn); body.addLayout(add_row)
            scroll, cards = self._make_card_scroll(); body.addWidget(scroll, 1)
            ordered = self._ordered_contract_tags()
            if ordered:
                for tag in ordered:
                    cards.insertWidget(cards.count() - 1, self.create_tag_card(tag))
            else:
                empty = QLabel("Henüz etiket atanmadı."); empty.setObjectName("sidePanelEmptyTag"); empty.setAlignment(Qt.AlignCenter); cards.insertWidget(0, empty)
        else:
            lock_state = self._load_document_lock_state()
            documents_accessible = self._documents_access_allowed(lock_state)
            documents_locked = int(lock_state.get("is_locked") or 0) == 1
            # ── Toolbar: + Dosya Ekle | + Klasör Ekle | Kilit ───────────────
            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(0, 0, 0, 0)
            toolbar.setSpacing(6)
            btn_file = QPushButton("+ Dosya Ekle")
            btn_file.setObjectName("documentActionPrimary")
            btn_file.setFixedHeight(30)
            btn_file.setCursor(Qt.PointingHandCursor)
            btn_file.setStyleSheet(
                "QPushButton{background:#2563eb;color:#0f172a;border:1px solid #2563eb;"
                "border-radius:9px;padding:0 12px;font-size:11px;font-weight:800;}"
                "QPushButton:hover{background:#1d4ed8;border-color:#1d4ed8;}"
            )
            btn_file.clicked.connect(self._pick_contract_files)
            btn_folder = QPushButton("+ Klasör Ekle")
            btn_folder.setObjectName("documentAction")
            btn_folder.setFixedHeight(30)
            btn_folder.setMinimumWidth(100)
            btn_folder.setCursor(Qt.PointingHandCursor)
            btn_folder.setStyleSheet(
                "QPushButton{background:#f8fbff;color:#102a43;border:1px solid #cfe0f3;"
                "border-radius:9px;padding:0 14px;font-size:11px;font-weight:800;}"
                "QPushButton:hover{background:#edf5ff;border-color:#9ec5f8;}"
            )
            btn_folder.clicked.connect(self.add_contract_file_folder)
            btn_file.setEnabled(documents_accessible and not self._share_is_view_only())
            btn_folder.setEnabled(documents_accessible and not self._share_is_view_only())

            lock_btn = QPushButton("🔒" if documents_locked else "🔓")
            lock_btn.setObjectName("documentLockButton")
            lock_btn.setProperty("locked", "true" if documents_locked else "false")
            lock_btn.setFixedSize(30, 30)
            lock_btn.setCursor(Qt.PointingHandCursor)
            lock_btn.setToolTip("Belgeler kilitli" if documents_locked else "Belgeleri kilitle")
            lock_btn.setEnabled(not self._share_is_view_only())
            lock_btn.clicked.connect(self._toggle_document_lock)
            self.document_lock_btn = lock_btn

            toolbar.addWidget(btn_file)
            toolbar.addWidget(btn_folder)
            toolbar.addWidget(lock_btn)
            toolbar.addStretch(1)
            body.addLayout(toolbar)

            lock_text = self._document_lock_summary_text(lock_state)
            if lock_text:
                lock_info = QLabel(lock_text)
                lock_info.setObjectName("documentLockInfo")
                lock_info.setWordWrap(True)
                body.addWidget(lock_info, 0)

            files = list(self._side_meta_files)
            folders = list(getattr(self, "_side_meta_folders", []))

            # ── Drop zone frame containing tree (or empty state) ─────────────
            drop_frame = QFrame()
            drop_frame.setObjectName("docDropZone")
            drop_frame.setAcceptDrops(True)

            # forward drag-drop events from frame to tree
            def _frame_drag_enter(event):
                if not documents_accessible:
                    event.ignore()
                    return
                if event.mimeData().hasUrls():
                    drop_frame.setProperty("dragOver", "true")
                    drop_frame.style().unpolish(drop_frame)
                    drop_frame.style().polish(drop_frame)
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def _frame_drag_leave(event):
                drop_frame.setProperty("dragOver", "false")
                drop_frame.style().unpolish(drop_frame)
                drop_frame.style().polish(drop_frame)
                super(QFrame, drop_frame).dragLeaveEvent(event)

            def _frame_drop(event):
                drop_frame.setProperty("dragOver", "false")
                drop_frame.style().unpolish(drop_frame)
                drop_frame.style().polish(drop_frame)
                if not documents_accessible:
                    self._ensure_document_access(interactive=True)
                    event.ignore()
                    return
                tree_w = getattr(self, "contract_files_tree", None)
                if tree_w:
                    tree_w.dropEvent(event)
                else:
                    event.ignore()

            drop_frame.dragEnterEvent = _frame_drag_enter
            drop_frame.dragLeaveEvent = _frame_drag_leave
            drop_frame.dropEvent = _frame_drop
            drop_frame.dragMoveEvent = lambda e: (e.acceptProposedAction() if documents_accessible and e.mimeData().hasUrls() else e.ignore())
            if not documents_accessible:
                drop_frame.mousePressEvent = lambda event: self._ensure_document_access(interactive=True)


            drop_frame_layout = QVBoxLayout(drop_frame)
            drop_frame_layout.setContentsMargins(0, 0, 0, 0)
            drop_frame_layout.setSpacing(0)

            try:
                if not documents_accessible:
                    self.contract_files_tree = None
                    locked_host = QWidget()
                    locked_host.setStyleSheet("background:transparent;")
                    lv = QVBoxLayout(locked_host)
                    lv.setContentsMargins(12, 28, 12, 28)
                    lv.setSpacing(6)
                    lv.setAlignment(Qt.AlignCenter)
                    l1 = QLabel("🔒 Belgeler kilitli")
                    l1.setObjectName("sidePanelEmpty")
                    l1.setAlignment(Qt.AlignCenter)
                    l2 = QLabel(f"Kilitleyen: {str(lock_state.get('locked_by_full_name') or 'Personel')}")
                    l2.setObjectName("sidePanelEmptySub")
                    l2.setAlignment(Qt.AlignCenter)
                    l3 = QLabel("Erişmek için tıklayın ve kilitleyen personelin şifresini girin.")
                    l3.setObjectName("sidePanelEmptySub")
                    l3.setAlignment(Qt.AlignCenter)
                    l3.setWordWrap(True)
                    lv.addWidget(l1)
                    lv.addWidget(l2)
                    lv.addWidget(l3)
                    drop_frame_layout.addWidget(locked_host)
                else:
                    tree = self.create_contract_files_tree(folders, files)
                    self.contract_files_tree = tree
                    tree_h = self.document_tree_height(folders, files)
                    # Tree'yi direkt ekle, yükseklik min+max ile sınırla
                    # Max = aynı değer → sabit kutu, ama QTreeWidget kendi
                    # internal scroll'u zaten yönetiyor (editör de içinde kalır)
                    tree.setMinimumHeight(tree_h)
                    tree.setMaximumHeight(tree_h)
                    drop_frame_layout.addWidget(tree)

                    if not files and not folders:
                        # empty state overlay
                        empty_host = QWidget()
                        empty_host.setStyleSheet("background:transparent;")
                        ev = QVBoxLayout(empty_host)
                        ev.setContentsMargins(12, 20, 12, 20)
                        ev.setSpacing(4)
                        ev.setAlignment(Qt.AlignCenter)
                        e1 = QLabel("Henüz belge eklenmedi.")
                        e1.setObjectName("sidePanelEmpty")
                        e1.setAlignment(Qt.AlignCenter)
                        e2 = QLabel("Dosya ekleyin veya buraya sürükleyin.")
                        e2.setObjectName("sidePanelEmptySub")
                        e2.setAlignment(Qt.AlignCenter)
                        ev.addWidget(e1)
                        ev.addWidget(e2)
                        drop_frame_layout.addWidget(empty_host)

            except Exception as exc:
                self.contract_files_tree = None
                message = QLabel(f"Belgeler yüklenemedi: {exc}")
                message.setObjectName("sidePanelEmpty")
                message.setWordWrap(True)
                message.setAlignment(Qt.AlignCenter)
                drop_frame_layout.addWidget(message)

            body.addWidget(drop_frame, 1)

            # ── Footer ──────────────────────────────────────────────────────
            footer_bar = QFrame()
            footer_bar.setObjectName("docFooterBar")
            footer_vlay = QVBoxLayout(footer_bar)
            footer_vlay.setContentsMargins(8, 6, 8, 6)
            footer_vlay.setSpacing(4)

            # ── Satır 1: Seçim bilgisi + butonlar (seçim varken) ────────────
            sel_row = QWidget()
            sel_row.setStyleSheet("background:transparent;")
            sel_row_lay = QHBoxLayout(sel_row)
            sel_row_lay.setContentsMargins(0, 0, 0, 0)
            sel_row_lay.setSpacing(6)

            lbl_sel = QLabel("")
            lbl_sel.setStyleSheet("background:transparent;color:#1d4ed8;font-size:11px;font-weight:700;border:0;")

            btn_bulk_dl = QPushButton("⬇  İndir")
            btn_bulk_zip = QPushButton("  ZIP İndir")
            btn_bulk_zip.setIcon(self._make_file_icon("zip"))
            btn_bulk_zip.setIconSize(__import__('PySide6.QtCore', fromlist=['QSize']).QSize(16, 16))
            for _b in (btn_bulk_dl, btn_bulk_zip):
                _b.setFixedHeight(26)
                _b.setMinimumWidth(80)
                _b.setStyleSheet(
                    "QPushButton{background:#2563eb;color:#fff;border:0;"
                    "border-radius:7px;padding:0 12px;font-size:11px;font-weight:700;}"
                    "QPushButton:hover{background:#1d4ed8;}"
                )

            sel_row_lay.addWidget(lbl_sel, 1)
            sel_row_lay.addWidget(btn_bulk_dl)
            sel_row_lay.addWidget(btn_bulk_zip)
            sel_row.hide()
            footer_vlay.addWidget(sel_row)

            # ── Satır 2: Sürükle-bırak + Toplam boyut (her zaman) ───────────
            info_row = QWidget()
            info_row.setStyleSheet("background:transparent;")
            info_row_lay = QHBoxLayout(info_row)
            info_row_lay.setContentsMargins(0, 0, 0, 0)
            info_row_lay.setSpacing(0)

            lbl_drag = QLabel("⇅  Sürükle-bırak desteklenir")
            lbl_drag.setObjectName("documentsFooterLeft")

            total_bytes = sum(int(item.get("size_bytes", 0) or 0) for item in files)
            lbl_right = QLabel(f"Toplam {self.format_file_size(total_bytes)}")
            lbl_right.setObjectName("documentsFooterRight")

            info_row_lay.addWidget(lbl_drag)
            info_row_lay.addStretch(1)
            info_row_lay.addWidget(lbl_right)
            footer_vlay.addWidget(info_row)

            body.addWidget(footer_bar, 0)

            # Seçim değişince footer güncelle
            def _on_selection_changed():
                tree_w = getattr(self, "contract_files_tree", None)
                if not tree_w:
                    return
                sel_files = [
                    it for it in tree_w.selectedItems()
                    if it.data(0, Qt.UserRole) == "file"
                ]
                if sel_files:
                    lbl_sel.setText(f"{len(sel_files)} dosya seçildi")
                    sel_row.show()
                else:
                    sel_row.hide()

            if hasattr(self, "contract_files_tree") and self.contract_files_tree:
                self.contract_files_tree.itemSelectionChanged.connect(_on_selection_changed)

            def _get_selected_file_ids():
                tree_w = getattr(self, "contract_files_tree", None)
                if not tree_w:
                    return []
                return [
                    int(it.data(0, Qt.UserRole + 1))
                    for it in tree_w.selectedItems()
                    if it.data(0, Qt.UserRole) == "file"
                ]

            btn_bulk_dl.clicked.connect(lambda: self._bulk_download_files(_get_selected_file_ids()))
            btn_bulk_zip.clicked.connect(lambda: self._bulk_zip_files(_get_selected_file_ids()))

    def _contract_document_share_stats(self) -> tuple[int, int]:
        try:
            files = list(self._load_contract_files())
            return len(files), sum(int(item.get("size_bytes", 0) or 0) for item in files)
        except Exception:
            return 0, 0

    def _copy_contract_documents_to_share(self, share_store, share_ci) -> tuple[int, int]:
        folders = list(self._load_contract_file_folders())
        files = list(self._load_contract_files())
        if not folders and not files:
            return 0, 0
        folder_id_map = {}
        pending = [dict(f) for f in folders]
        while pending:
            progressed = False
            for folder in pending[:]:
                old_parent = folder.get("parent_id")
                if old_parent not in (None, "", 0) and int(old_parent) not in folder_id_map:
                    continue
                created = share_store.create_contract_file_folder(
                    str(share_ci.platform or ""),
                    str(share_ci.no or ""),
                    str(share_ci.contract_type or "Ana Sözleşme"),
                    parent_id=folder_id_map.get(int(old_parent)) if old_parent not in (None, "", 0) else None,
                    name=str(folder.get("name") or "Klasör"),
                )
                folder_id_map[int(folder.get("id"))] = int(created.get("id") or 0)
                if str(folder.get("merge_uid") or "").strip():
                    share_store.db.conn.execute("UPDATE contract_file_folders SET merge_uid=? WHERE id=?", (str(folder.get("merge_uid") or ""), int(created.get("id") or 0)))
                pending.remove(folder)
                progressed = True
            if not progressed:
                break
        copied = 0
        total = 0
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            for item in files:
                file_id = int(item.get("id") or 0)
                if not file_id:
                    continue
                filename, _mime, content = self.store.get_contract_file_bytes(file_id)
                safe_name = Path(str(filename or f"belge-{file_id}")).name
                tmp_file = tmpdir_path / safe_name
                suffix = 1
                while tmp_file.exists():
                    tmp_file = tmpdir_path / f"{tmp_file.stem}-{suffix}{tmp_file.suffix}"
                    suffix += 1
                tmp_file.write_bytes(content)
                old_folder_id = item.get("folder_id")
                new_folder_id = folder_id_map.get(int(old_folder_id)) if old_folder_id not in (None, "", 0) else None
                new_file_id = share_store.add_contract_file(
                    str(share_ci.platform or ""),
                    str(share_ci.no or ""),
                    tmp_file,
                    str(share_ci.contract_type or "Ana Sözleşme"),
                    note=str(item.get("note") or ""),
                    folder_id=new_folder_id,
                )
                if str(item.get("merge_uid") or "").strip():
                    share_store.db.conn.execute("UPDATE contract_files SET merge_uid=? WHERE id=?", (str(item.get("merge_uid") or ""), int(new_file_id or 0)))
                copied += 1
                total += len(content)
        return copied, total


    def _confirm_active_share_creation(self) -> bool:
        try:
            active = list_active_share_packages(self.store, self._current_contract_merge_uid())
        except Exception:
            QMessageBox.warning(
                self,
                "Aktif Paylaşım Kontrolü",
                "Aktif paylaşım durumu kontrol edilemedi. Paylaşım oluşturma işlemi başlatılmadı.",
            )
            return False
        if not active:
            return True
        count = len(active)
        message = (
            f"Bu sözleşme için {count} aktif paylaşım bulunuyor.\n\n"
            "Yeni paylaşım oluşturabilirsiniz. Eski açık paylaşımlar geri döndüğünde ayrı paketler olarak işlenecektir."
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Aktif Paylaşım Var")
        box.setText(message)
        continue_button = box.addButton("Yine de Paylaşım Oluştur", QMessageBox.AcceptRole)
        history_button = box.addButton("Paylaşım Geçmişini Aç", QMessageBox.ActionRole)
        box.addButton("Vazgeç", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == continue_button:
            return True
        if clicked == history_button:
            self.show_share_history()
        return False

    def create_contract_share_file(self, permission: str, default_filename: str):
        """Create a V2 single-contract STS share file with immutable base snapshot metadata."""
        if bool(getattr(self, "share_mode_enabled", False)):
            return
        if not self.require_permission_ui("export_data", "Sözleşme Paylaşımı"):
            return
        if not self._confirm_active_share_creation():
            return
        doc_count, doc_bytes = self._contract_document_share_stats()
        if doc_count > 0:
            QMessageBox.information(
                self,
                "Paylaşım Belgeleri",
                "Bu sözleşmeye bağlı belgeler paylaşım dosyasına dahil edilir. Dosya boyutu artabilir.",
            )
        target, _ = QFileDialog.getSaveFileName(self, "Paylaşım Dosyası Oluştur", default_filename, "STS Dosyası (*.sts)")
        if not target:
            return
        if not str(target).lower().endswith(".sts"):
            target += ".sts"
        target_path = Path(target)
        temp_path = target_path.with_name(f".{target_path.name}.creating-{uuid.uuid4().hex}.sts")
        backup_path = None
        replaced_existing = False
        try:
            source_contract_id = int(getattr(self.ci, "contract_id", 0) or getattr(self.ci, "id", 0) or getattr(self.ci, "entry_start_row", 0) or 0)
            if source_contract_id <= 0:
                raise ValueError("Paylaşım için kaynak sözleşme kimliği bulunamadı.")
            created_at = utcish_now()
            base_snapshot = build_base_snapshot_from_source(self.store.db.conn, source_contract_id, created_at=created_at)
            if not base_snapshot.contract_merge_uid:
                raise ValueError("Paylaşım için kaynak sözleşme merge UID değeri bulunamadı.")
            share_package_id = str(uuid.uuid4())
            staff = self.current_staff or {}
            created_by_staff_id = int(staff.get("id") or 0) if not bool(staff.get("is_admin")) else 0
            created_by_username = str(staff.get("username") or staff.get("device_name") or "")
            created_by_full_name = str(staff.get("full_name") or staff.get("admin_name") or "")

            if temp_path.exists():
                temp_path.unlink()
            share_store = STSStore(temp_path, actor="Sözleşme Paylaşımı")
            share_ci = copy.deepcopy(self.ci)
            share_ci.entry_start_row = 0
            setattr(share_ci, "id", 0)
            setattr(share_ci, "contract_id", 0)
            # Ana DB platform/staff ID'leri yeni boş DB'de geçersiz — sıfırla
            share_ci.platform_ids = []
            share_ci.platforms = []
            share_ci.platform_id = 0
            share_ci.primary_platform_id = 0
            share_ci.responsible_engineer_id = 0
            share_ci.responsible_engineer_ids = []
            contract_id = int(share_store.write_contract(share_ci, copy.deepcopy(self.systems), copy.deepcopy(self.deliveries)) or 0)
            share_store.save_contract_tags(
                str(share_ci.platform or ""),
                str(share_ci.no or ""),
                str(share_ci.contract_type or "Ana Sözleşme"),
                [dict(t or {}) for t in self.contract_tags],
                actor="Sözleşme Paylaşımı",
            )
            copied_docs, copied_doc_bytes = self._copy_contract_documents_to_share(share_store, share_ci)
            share_store.save()
            try:
                share_store.db.close()
            except Exception:
                pass

            metadata = make_v2_metadata(
                share_package_id=share_package_id,
                permission_mode="edit" if permission == "duzenle" else "view",
                source_sts_instance_id=self.store.sts_instance_id(),
                source_schema_version=CURRENT_SCHEMA_VERSION,
                source_contract_id=source_contract_id,
                source_contract_merge_uid=base_snapshot.contract_merge_uid,
                source_contract_no=str(getattr(self.ci, "no", "") or ""),
                base_revision=int(getattr(self.ci, "revision", 1) or 1),
                base_snapshot_sha256=base_snapshot.snapshot_sha256,
                created_at=created_at,
                created_by_staff_id=created_by_staff_id,
                created_by_username=created_by_username,
                created_by_full_name=created_by_full_name,
                document_count=copied_docs,
                document_bytes=copied_doc_bytes,
            )
            metadata["contract_id"] = str(contract_id)  # package-local legacy/open fallback
            write_share_metadata(temp_path, metadata)
            write_share_base_snapshot(temp_path, base_snapshot)
            validation = validate_share_package(temp_path)
            if not validation.is_valid:
                raise ValueError("Paylaşım paketi doğrulanamadı: " + "; ".join(validation.errors))

            if target_path.exists():
                backup_path = target_path.with_name(f".{target_path.name}.backup-{uuid.uuid4().hex}.sts")
                target_path.replace(backup_path)
                replaced_existing = True
            temp_path.replace(target_path)
            registry_entry = SharePackageRegistryEntry(
                share_package_id=share_package_id,
                contract_id=source_contract_id,
                contract_merge_uid=base_snapshot.contract_merge_uid,
                source_contract_revision=int(getattr(self.ci, "revision", 1) or 1),
                permission_mode="edit" if permission == "duzenle" else "view",
                share_format_version=SHARE_FORMAT_V2,
                snapshot_format_version=base_snapshot.snapshot_format_version,
                base_snapshot_sha256=base_snapshot.snapshot_sha256,
                created_at=created_at,
                created_by_staff_id=created_by_staff_id,
                created_by_username=created_by_username,
                created_by_full_name=created_by_full_name,
                exported_filename=target_path.name,
                status=SHARE_STATUS_OPEN,
            )
            try:
                self.store.register_share_package(registry_entry)
            except Exception:
                if target_path.exists():
                    target_path.unlink()
                if replaced_existing and backup_path and backup_path.exists():
                    backup_path.replace(target_path)
                raise
            if backup_path and backup_path.exists():
                backup_path.unlink()
            QMessageBox.information(self, "Paylaşım", "Paylaşım STS dosyası oluşturuldu.")
        except Exception as exc:
            try:
                if temp_path.exists():
                    temp_path.unlink()
                if replaced_existing and backup_path and backup_path.exists() and not target_path.exists():
                    backup_path.replace(target_path)
            except Exception:
                pass
            QMessageBox.warning(self, "Paylaşım dosyası oluşturulamadı.", str(exc))

    def can_show_share_history_action(self) -> bool:
        return (
            not bool(getattr(self, "share_mode_enabled", False))
            and not bool(getattr(self, "is_new_contract", False))
            and hasattr(getattr(self.store, "db", None), "conn")
        )

    def _current_contract_merge_uid(self) -> str:
        return str(getattr(self.ci, "merge_uid", "") or "").strip()

    def _load_share_history_records(self):
        return list_contract_share_history(self.store, self._current_contract_merge_uid())

    def _cancel_share_history_record(self, record):
        cancel_share_package(self.store, self._current_contract_merge_uid(), record.share_package_id, current_staff=self.current_staff)

    def show_share_history(self):
        if not self.can_show_share_history_action():
            return
        contract_title = str(getattr(self.ci, "no", "") or "Sözleşme")
        dialog = ShareHistoryDialog(
            contract_title=contract_title,
            records=self._load_share_history_records(),
            refresh_callback=self._load_share_history_records,
            cancel_callback=self._cancel_share_history_record,
            can_cancel=self.has_permission("edit_contracts"),
            parent=self,
        )
        dialog.exec()

    def can_show_share_merge_action(self) -> bool:
        return (
            not bool(getattr(self, "share_mode_enabled", False))
            and not bool(getattr(self, "is_new_contract", False))
            and hasattr(getattr(self.store, "db", None), "conn")
            and self.has_permission("edit_contracts")
        )

    def merge_returned_share_file(self):
        if getattr(self, "share_mode_enabled", False):
            return
        if not self.require_permission_ui("edit_contracts", "Paylaşım Birleştirme"):
            return
        self._file_dialog_open = True
        try:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Paylaşım Dosyasını Geri Al",
                str(Path(getattr(self.store, "path", "") or ".").parent),
                "STS Dosyası (*.sts)",
            )
        finally:
            self._file_dialog_open = False
        if not selected:
            return
        share_path = Path(selected)
        validation = validate_share_package(share_path)
        if not validation.is_share_package:
            self._show_share_merge_error(
                "Paylaşım dosyası birleştirilemedi",
                "Seçilen dosya bir paylaşım STS dosyası değil.",
                "Normal STS dosyaları bu akışta birleştirilemez.",
            )
            return
        if validation.format_version == SHARE_FORMAT_V1:
            self._show_share_merge_error(
                "Paylaşım dosyası birleştirilemedi",
                "Bu paylaşım dosyası eski formatta oluşturulmuş. Otomatik değişiklik birleştirme yalnızca V2 paylaşım dosyalarında destekleniyor.",
                "",
            )
            return
        if not validation.is_supported or not validation.is_valid or not validation.supports_merge or not validation.metadata:
            self._show_share_merge_error(
                "Paylaşım dosyası birleştirilemedi",
                "Seçilen paylaşım dosyası otomatik birleştirme için uygun değil.",
                "; ".join(validation.errors or validation.warnings or []),
            )
            return
        current_merge_uid = str(getattr(self.ci, "merge_uid", "") or "").strip()
        if current_merge_uid and validation.metadata.source_contract_merge_uid != current_merge_uid:
            self._show_share_merge_error(
                "Paylaşım dosyası birleştirilemedi",
                "Seçilen paylaşım dosyası bu sözleşmeye ait değil.",
                f"Beklenen: {current_merge_uid} / Dosya: {validation.metadata.source_contract_merge_uid}",
            )
            return
        try:
            self.set_busy_overlay(True, "Paylaşım dosyası analiz ediliyor...", 30)
            plan = prepare_share_merge_plan(self.store, share_path)
        except Exception as exc:
            self._show_share_merge_exception(exc)
            return
        finally:
            self.set_busy_overlay(False)

        dialog = ShareMergeDialog(
            merge_plan=plan,
            share_path=share_path,
            metadata=validation.metadata,
            preflight_callback=lambda resolved, allow_partial: preflight_resolved_share_merge(
                self.store,
                share_path,
                resolved,
                allow_partial=allow_partial,
            ),
            apply_callback=lambda resolved, allow_partial: apply_resolved_share_merge(
                self.store,
                share_path,
                resolved,
                current_staff=self.current_staff,
                allow_partial=allow_partial,
            ),
            success_callback=self._after_share_merge_success,
            parent=self,
        )
        dialog.exec()

    def _after_share_merge_success(self, result) -> None:
        try:
            self._reload_current_contract_from_db()
            parent = self.parent()
            if parent is not None and hasattr(parent, "request_refresh"):
                parent.request_refresh(select_platform=str(self.ci.platform or ""), scope="all")
        except Exception as exc:
            _log.exception("Share merge sonrası sözleşme yenilenemedi")
            QMessageBox.warning(
                self,
                "Birleştirme tamamlandı",
                "Değişiklikler birleştirildi ancak ekran otomatik yenilenemedi. Sözleşmeyi yeniden açmanız gerekebilir.\n\n"
                f"Teknik detay: {exc}",
            )

    def _reload_current_contract_from_db(self) -> None:
        contract_id = int(getattr(self.ci, "entry_start_row", 0) or getattr(self.ci, "contract_id", 0) or getattr(self.ci, "id", 0) or 0)
        if contract_id <= 0:
            raise ValueError("Açık sözleşme ID'si bulunamadı.")
        ci, systems, deliveries = self.store.load_contract_structure(
            str(getattr(self.ci, "platform", "") or ""),
            str(getattr(self.ci, "no", "") or ""),
            start_row=contract_id,
            contract_type=str(getattr(self.ci, "contract_type", "") or ""),
            platform_id=int(getattr(self, "active_platform_id", 0) or getattr(self.ci, "platform_id", 0) or 0),
        )
        self.ci = ci
        self.original_platform = str(ci.platform or "")
        self.original_contract_no = str(ci.no or "")
        self.original_contract_type = str(ci.contract_type or "")
        self.original_entry_start_row = int(getattr(ci, "entry_start_row", 0) or 0)
        self.active_platform_id = int(getattr(ci, "platform_id", 0) or getattr(ci, "primary_platform_id", 0) or 0)
        self.systems = systems or []
        self.deliveries = deliveries or {}
        self.contract_tags = self.store.load_contract_tags(
            self.original_platform,
            self.original_contract_no,
            self.original_contract_type,
        )
        self._context_cache.clear()
        self.selected_system = self.systems[0].name if self.systems else None
        self.expanded_delivery_index = None
        self.refresh_contract_header()
        self.render_contract_tags()
        self.refresh()
        self.update_side_meta_badges()
        self._initial_snapshot = self._make_data_snapshot()
        self._is_dirty = False
        self._documents_changed = False

    def _show_share_merge_exception(self, exc: Exception) -> None:
        _log.exception("Share merge prepare failed")
        presentation = present_share_merge_error(exc)
        self._show_share_merge_error(presentation.title, presentation.message, presentation.detail)

    def _show_share_merge_error(self, title: str, message: str, detail: str = "") -> None:
        text = str(message or "Paylaşım dosyası birleştirilemedi.")
        if detail:
            text = f"{text}\n\nTeknik detay: {detail}"
        QMessageBox.warning(self, title, text)

    @staticmethod
    def _share_merge_error_message(exc: Exception) -> str:
        if isinstance(exc, ShareSourceMismatchError):
            return "Seçilen paylaşım dosyası bu STS dosyasına ait değil."
        if isinstance(exc, UnknownSharePackageError):
            return "Bu paylaşım paketi ana STS kayıtlarında bulunamadı."
        if isinstance(exc, PackageRegistryMismatchError):
            return "Paylaşım paketi kayıt bilgileri ana STS ile uyuşmuyor."
        if isinstance(exc, SharePackageStatusError):
            return "Bu paylaşım paketinin durumu birleştirmeye kapalı."
        if isinstance(exc, UnsupportedShareMergePackageError):
            return "Seçilen dosya geçerli bir V2 paylaşım paketi değil."
        if isinstance(exc, ShareMergePreparationError):
            return "Paylaşım dosyası merge için hazırlanamadı."
        return "Beklenmeyen bir hata nedeniyle paylaşım dosyası birleştirilemedi."

    def _make_card_scroll(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea{background:transparent; border:0;} QScrollArea > QWidget > QWidget{background:transparent;} QScrollBar:vertical{width:8px; background:transparent;} QScrollBar::handle:vertical{background:#94a3b8; border-radius:4px; min-height:22px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        host = QWidget(); host.setMinimumWidth(0); host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); host.setStyleSheet("background:transparent;")
        cards = QVBoxLayout(host); cards.setContentsMargins(0, 0, 2, 0); cards.setSpacing(6); cards.addStretch()
        scroll.setWidget(host)
        return scroll, cards

    def _ordered_contract_tags(self) -> List[dict]:
        return sorted(
            [dict(t) for t in self.contract_tags if str((t or {}).get("name") or "").strip()],
            key=lambda x: self._tag_key(str(x.get("name", ""))),
        )

    def create_tag_card(self, tag: dict) -> QFrame:
        name = str((tag or {}).get("name") or "").strip()
        color = str((tag or {}).get("color") or "#3B82F6")
        card = QFrame(); card.setObjectName("sideTagCard"); card.setMinimumWidth(0); card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); card.setFixedHeight(52)
        card.setStyleSheet("QFrame#sideTagCard{background:#f8fbff; border:1px solid #dbe7f5; border-radius:5px;} QFrame#sideTagCard:hover{background:#eef6ff; border-color:#b8cef0;} QLabel{background:transparent; border:0;} QPushButton#tagRemoveButton{background:#f1f5fb; color:#64748b; border:1.5px solid #c8d8ee; border-radius:4px; font-size:16px; font-weight:700; padding:0;} QPushButton#tagRemoveButton:hover{background:#fee2e2; color:#b91c1c; border-color:#fca5a5;}")
        row = QHBoxLayout(card); row.setContentsMargins(9, 5, 9, 5); row.setSpacing(8)
        dot = QLabel("●"); dot.setFixedWidth(10); dot.setStyleSheet(f"color:{color}; font-size:12px;")
        middle = QWidget(); middle.setMinimumWidth(0); middle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); middle.setStyleSheet("background:transparent;"); column = QVBoxLayout(middle); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(1)
        title = ElidedLabel(name); title.setMinimumWidth(0); title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); title.setToolTip(name); title.setStyleSheet("color:#10233d; font-size:12px; font-weight:900;")
        meta = QLabel("Sözleşmeye atanmış etiket"); meta.setStyleSheet("color:#64748b; font-size:10px;")
        column.addWidget(title); column.addWidget(meta)
        remove = QPushButton("×"); remove.setObjectName("tagRemoveButton"); remove.setFixedSize(29, 29); remove.setToolTip("Etiketi kaldır"); remove.setEnabled(not self._share_labels_disabled());
        if self._share_labels_disabled():
            remove.setToolTip(self._share_label_policy_message())
        remove.clicked.connect(lambda _=False, nm=name: self.remove_contract_tag(nm))
        row.addWidget(dot); row.addWidget(middle, 1); row.addWidget(remove)
        return card


    @staticmethod
    @staticmethod
    def _make_folder_icon() -> "QIcon":
        """Renkli klasör ikonu üretir."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush, QPen
        px = QPixmap(32, 32)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        # Klasör gövdesi
        painter.setBrush(QBrush(QColor("#f59e0b")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(1, 10, 30, 20), 4, 4)
        # Klasör sekmesi (üst sol)
        painter.drawRoundedRect(QRectF(1, 6, 13, 8), 3, 3)
        painter.end()
        return QIcon(px)

    @staticmethod
    def _make_file_icon(ext: str) -> "QIcon":
        """Ext'e göre renkli küçük dosya ikonu üretir."""
        ext_map = {
            "pdf":  ("#ef4444", "PDF"),
            "doc":  ("#2563eb", "DOC"), "docx": ("#2563eb", "DOC"),
            "xls":  ("#16a34a", "XLS"), "xlsx": ("#16a34a", "XLS"), "xlsm": ("#16a34a", "XLS"),
            "ppt":  ("#f97316", "PPT"), "pptx": ("#f97316", "PPT"),
            "png":  ("#7c3aed", "IMG"), "jpg":  ("#7c3aed", "IMG"), "jpeg": ("#7c3aed", "IMG"),
            "txt":  ("#64748b", "TXT"),
            "zip":  ("#b45309", "ZIP"),
        }
        color_hex, label = ext_map.get(str(ext).lower(), ("#64748b", str(ext).upper()[:3] or "???"))
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush, QPen
        px = QPixmap(32, 32)
        px.fill(Qt.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = QColor(color_hex)
        bg.setAlpha(220)
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(1, 1, 30, 30), 6, 6)
        painter.setPen(QPen(QColor("#ffffff")))
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(px.rect(), Qt.AlignCenter, label)
        painter.end()
        return QIcon(px)

    @staticmethod
    def document_tree_height(folders: List[dict], files: List[dict]) -> int:
        """Dinamik ağaç yüksekliği: satır sayısına göre küçük→orta→büyük+scroll."""
        # Açık klasörlerdeki dosyaları da say (görünür satır tahmini)
        folder_ids = {int(f.get("id") or 0) for f in (folders or [])}
        visible = len(folders or [])
        for fi in (files or []):
            fid = fi.get("folder_id")
            if not fid or int(fid or 0) not in folder_ids:
                visible += 1  # kökteki dosya
            else:
                visible += 1  # klasör içi dosya (açık varsayımı)
        if visible <= 0:
            return 110
        if visible <= 6:
            return max(120, visible * 30 + 24)
        if visible <= 15:
            return max(210, visible * 30 + 24)
        return 420   # çok kayıt → internal scroll


    def create_contract_files_tree(self, folders: List[dict], files: List[dict]) -> ContractFileTreeWidget:
        # Expand/collapse ok ikonlarını temp dosyaya yaz
        import tempfile, os

        def _write_arrow_png(expanded: bool) -> str:
            from PySide6.QtCore import QBuffer, QIODevice
            px = QPixmap(16, 16)
            px.fill(Qt.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#94a3b8"))
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            if expanded:
                pts = [QPointF(3, 5), QPointF(13, 5), QPointF(8, 12)]
            else:
                pts = [QPointF(5, 3), QPointF(12, 8), QPointF(5, 13)]
            p.drawPolygon(QPolygonF(pts))
            p.end()
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            px.save(tmp.name, "PNG")
            return tmp.name.replace("\\", "/")

        arrow_closed = _write_arrow_png(False)
        arrow_open   = _write_arrow_png(True)

        tree = ContractFileTreeWidget(self)
        tree.setMinimumHeight(110)
        tree.setColumnCount(1)
        tree.setHeaderHidden(True)
        tree.setIndentation(20)
        tree.setIconSize(__import__('PySide6.QtCore', fromlist=['QSize']).QSize(18, 18))
        tree.setStyleSheet(
            "QTreeWidget{background:#f8fbff; border:0; border-radius:0; padding:4px 2px; color:#0f172a; font-size:11px; outline:0;}"
            "QTreeWidget::item{height:28px; border-radius:7px; padding:0 6px 0 2px;}"
            "QTreeWidget::item:selected{background:#dbeafe; color:#0f3f8f;}"
            "QTreeWidget::item:hover:!selected{background:#edf5ff;}"
            "QTreeWidget::branch{background:transparent; width:16px;}"
            f"QTreeWidget::branch:has-children:!has-siblings:closed,"
            f"QTreeWidget::branch:closed:has-children:has-siblings{{"
            f"  border:0; image:url({arrow_closed}); width:16px;"
            f"}}"
            f"QTreeWidget::branch:open:has-children:!has-siblings,"
            f"QTreeWidget::branch:open:has-children:has-siblings{{"
            f"  border:0; image:url({arrow_open}); width:16px;"
            f"}}"
            "QScrollBar:vertical{width:7px; background:transparent; margin:3px 1px 3px 0;}"
            "QScrollBar::handle:vertical{background:#c7d7ea; border-radius:3px; min-height:20px;}"
            "QScrollBar::handle:vertical:hover{background:#9eb8d7;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        if self._share_is_view_only():
            tree.setAcceptDrops(False)
            tree.setDragEnabled(False)
            tree.setDragDropMode(QAbstractItemView.NoDragDrop)
            tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tree.filesDropped.connect(lambda paths, folder_id: self._add_contract_files(paths, folder_id))
        tree.invalidDrop.connect(lambda message: QMessageBox.warning(self, "Dosya yüklenemedi", message))
        tree.itemMoved.connect(self._handle_tree_item_move)
        tree.itemDoubleClicked.connect(self.on_contract_file_tree_double_clicked)
        tree.itemChanged.connect(self.on_contract_file_tree_item_changed)
        tree.customContextMenuRequested.connect(self.show_contract_file_tree_menu)
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        # Sağ tıklamada item seçilsin (önceki seçimi korumaz, tek item)
        _orig_mpe = tree.mousePressEvent
        def _mpe(event, _orig=_orig_mpe):
            if event.button() == Qt.RightButton:
                try:
                    pos = event.position().toPoint()
                except AttributeError:
                    pos = event.pos()
                item_at = tree.itemAt(pos)
                if item_at and item_at not in tree.selectedItems():
                    tree.clearSelection()
                    tree.setCurrentItem(item_at)
            _orig(event)
        tree.mousePressEvent = _mpe
        _folder_icon = self._make_folder_icon()
        self._building_file_tree = True
        try:
            folder_items = {}
            children_by_parent: Dict[object, List[dict]] = {}
            folder_ids = {int(folder.get("id")) for folder in folders if folder.get("id") not in (None, "")}

            def folder_file_count(fid):
                """Klasörün doğrudan dosya sayısını döner."""
                return sum(1 for f in files if int(f.get("folder_id") or 0) == fid)
            for folder in folders:
                parent_id = folder.get("parent_id")
                try:
                    parent_id = int(parent_id) if parent_id not in (None, "", 0) else None
                except (TypeError, ValueError):
                    parent_id = None
                if parent_id not in folder_ids:
                    parent_id = None
                children_by_parent.setdefault(parent_id, []).append(folder)

            def add_folder_items(parent_item, parent_id):
                for folder in sorted(children_by_parent.get(parent_id, []), key=lambda x: str(x.get("name") or "").casefold()):
                    folder_id = int(folder.get("id"))
                    count = folder_file_count(folder_id)
                    item = QTreeWidgetItem([str(folder.get("name") or "")])
                    item.setIcon(0, _folder_icon)
                    item.setToolTip(0, f"{folder.get('name', '')}  ·  {count} dosya")
                    item.setData(0, Qt.UserRole, "folder")
                    item.setData(0, Qt.UserRole + 1, folder_id)
                    item.setData(0, Qt.UserRole + 2, folder.get("_tree_parent_id"))
                    item.setData(0, Qt.UserRole + 3, str(folder.get("name") or ""))
                    item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDropEnabled)
                    if parent_item is None:
                        tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    folder_items[folder_id] = item
                    add_folder_items(item, folder_id)

            add_folder_items(None, None)
            for metadata in sorted(files, key=lambda x: (str(x.get("filename") or "").casefold(), int(x.get("id") or 0))):
                try:
                    file_folder_id = int(metadata.get("folder_id") or 0)
                except (TypeError, ValueError):
                    file_folder_id = 0
                parent_item = folder_items.get(file_folder_id)
                ext = str(metadata.get("file_ext") or "").lower() or "dosya"
                size_text = self.format_file_size(metadata.get("size_bytes", 0))
                item = QTreeWidgetItem([str(metadata.get("filename") or "")])
                item.setIcon(0, self._make_file_icon(ext))
                item.setToolTip(0, f"{ext.upper()} · {size_text} · {self.format_file_date(metadata.get('created_at', ''))}")
                item.setData(0, Qt.UserRole, "file")
                item.setData(0, Qt.UserRole + 1, int(metadata.get("id")))
                item.setData(0, Qt.UserRole + 2, file_folder_id if parent_item is not None else None)
                item.setFlags((item.flags() | Qt.ItemIsDragEnabled) & ~Qt.ItemIsEditable)
                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
            # Sadece kök klasörler açık, alt klasörler kapalı başlar
            for i in range(tree.topLevelItemCount()):
                top = tree.topLevelItem(i)
                if top and top.data(0, Qt.UserRole) == "folder":
                    top.setExpanded(True)
        finally:
            self._building_file_tree = False
        return tree

    def _selected_document_folder_id(self):
        tree = getattr(self, "contract_files_tree", None)
        item = tree.currentItem() if tree else None
        if item is None:
            return None
        kind = item.data(0, Qt.UserRole)
        if kind == "folder":
            return item.data(0, Qt.UserRole + 1)
        if kind == "file":
            return item.data(0, Qt.UserRole + 2)
        return None

    def _start_rename_item(self, item):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        """Klasör rename editörünü aç ve metni seçili göster."""
        tree = getattr(self, "contract_files_tree", None)
        if not tree or not item:
            return
        self._tree_editing = True
        tree.setCurrentItem(item)
        # Delegate: editör açıldığında arka plan tamamen kapatılsın (overlay bug önlemi)
        # Her tree nesnesi için delegate kur (render sonrası yeni tree oluşur)
        if not getattr(tree, "_rename_delegate_set", False):
            from PySide6.QtWidgets import QStyledItemDelegate
            from PySide6.QtGui import QColor
            class _SolidBgDelegate(QStyledItemDelegate):
                def createEditor(self, parent, option, index):
                    editor = super().createEditor(parent, option, index)
                    if editor:
                        editor.setStyleSheet(
                            "QLineEdit{"
                            "  background:#ffffff;"
                            "  color:#0f172a;"
                            "  border:2px solid #1f5be3;"
                            "  border-radius:5px;"
                            "  padding:1px 4px;"
                            "  font-size:11px;"
                            "  min-width:120px;"
                            "}"
                        )
                    return editor
                def paint(self, painter, option, index):
                    # PySide6'da option.state bir StateFlag enum'u – int'e cast ederek kontrol et
                    from PySide6.QtWidgets import QStyle
                    try:
                        is_editing = bool(int(option.state) & int(QStyle.State_Editing))
                    except Exception:
                        is_editing = False
                    if is_editing:
                        from PySide6.QtGui import QColor
                        painter.fillRect(option.rect, QColor("#ffffff"))
                        return
                    super().paint(painter, option, index)
            tree.setItemDelegate(_SolidBgDelegate(tree))
            tree._rename_delegate_set = True
        tree.scrollToItem(item)
        tree.editItem(item, 0)
        def _select_all():
            editor = tree.focusWidget()
            if editor and hasattr(editor, "selectAll"):
                editor.selectAll()
        QTimer.singleShot(30, _select_all)

    def add_contract_file_folder(self):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        try:
            parent_id = self._selected_document_folder_id()
            if self.is_new_contract:
                # Pending modda in-memory oluştur
                base_name = "Yeni Klasör"
                existing = {f["name"] for f in self._pending_doc_folders if f.get("parent_id") == parent_id}
                name = base_name
                idx = 2
                while name in existing:
                    name = f"{base_name} ({idx})"
                    idx += 1
                new_id = self._pending_doc_next_id
                self._pending_doc_next_id -= 1
                folder = {"id": new_id, "parent_id": parent_id, "name": name, "created_at": "", "updated_at": ""}
                self._pending_doc_folders.append(folder)
                created = folder
            else:
                created = self.store.create_contract_file_folder(
                    self.ci.platform, self.ci.no, self.ci.contract_type, parent_id=parent_id
                )
            self._mark_documents_changed()
            # render_contract_files() tüm tree'yi yıkıp yeniden kurar →
            # editör yanlış konuma açılıyor. Bunun yerine tree'ye direkt item ekle.
            tree = getattr(self, "contract_files_tree", None)
            if tree:
                # Yeni klasör item'ını direkt tree'ye ekle
                _folder_icon = self._make_folder_icon()
                new_item = QTreeWidgetItem([str(created.get("name") or "Yeni Klasör")])
                new_item.setIcon(0, _folder_icon)
                new_item.setData(0, Qt.UserRole, "folder")
                new_item.setData(0, Qt.UserRole + 1, int(created.get("id") or 0))
                new_item.setData(0, Qt.UserRole + 2, created.get("parent_id"))
                new_item.setData(0, Qt.UserRole + 3, str(created.get("name") or "Yeni Klasör"))
                new_item.setFlags(new_item.flags() | Qt.ItemIsEditable | Qt.ItemIsDropEnabled)
                # Parent klasör varsa ona, yoksa köke ekle
                _parent_folder_id = created.get("parent_id")
                _parent_item = None
                if _parent_folder_id:
                    def _find_parent(n_top):
                        for _i in range(n_top):
                            _top = tree.topLevelItem(_i)
                            if _top and _top.data(0, Qt.UserRole) == "folder":
                                try:
                                    if int(_top.data(0, Qt.UserRole + 1)) == int(_parent_folder_id):
                                        return _top
                                except Exception:
                                    pass
                                for _j in range(_top.childCount()):
                                    _ch = _top.child(_j)
                                    if _ch and _ch.data(0, Qt.UserRole) == "folder":
                                        try:
                                            if int(_ch.data(0, Qt.UserRole + 1)) == int(_parent_folder_id):
                                                return _ch
                                        except Exception:
                                            pass
                        return None
                    _parent_item = _find_parent(tree.topLevelItemCount())
                if _parent_item:
                    _parent_item.addChild(new_item)
                    _parent_item.setExpanded(True)
                else:
                    tree.addTopLevelItem(new_item)
                tree.scrollToItem(new_item)
                self._start_rename_item(new_item)
                # Yüksekliği güncelle (1 item arttı)
                all_f = list(getattr(self, "_side_meta_folders", []))
                all_files = list(getattr(self, "_side_meta_files", []))
                new_h = self.document_tree_height(all_f, all_files)
                tree.setMinimumHeight(new_h)
                tree.setMaximumHeight(new_h)
            else:
                # Tree henüz yok, tam render yap
                self.render_contract_files()
                _created_id = int(created.get("id") or 0)
                def _open_rename_editor():
                    _tree = getattr(self, "contract_files_tree", None)
                    if not _tree:
                        return
                    def _find(_p, _n):
                        for _i in range(_n):
                            _c = _p.child(_i) if _p else _tree.topLevelItem(_i)
                            if _c and _c.data(0, Qt.UserRole) == "folder":
                                try:
                                    if int(_c.data(0, Qt.UserRole + 1)) == _created_id:
                                        _tree.scrollToItem(_c)
                                        self._start_rename_item(_c)
                                        return True
                                except Exception:
                                    pass
                                if _find(_c, _c.childCount()):
                                    return True
                        return False
                    _find(None, _tree.topLevelItemCount())
                QTimer.singleShot(60, _open_rename_editor)
            self.update_side_meta_badges()
        except Exception as exc:
            QMessageBox.warning(self, "Klasör eklenemedi", str(exc))

    def on_contract_file_tree_double_clicked(self, item, column):
        if not self._ensure_document_access(interactive=True):
            return
        if not item:
            return
        if item.data(0, Qt.UserRole) == "file":
            self.open_contract_file(int(item.data(0, Qt.UserRole + 1)))
        elif item.data(0, Qt.UserRole) == "folder":
            self._start_rename_item(item)

    def on_contract_file_tree_item_changed(self, item, column):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        if getattr(self, "_building_file_tree", False) or not item or item.data(0, Qt.UserRole) != "folder":
            return
        self._tree_editing = False
        folder_id = int(item.data(0, Qt.UserRole + 1))
        old_name = str(item.data(0, Qt.UserRole + 3) or "")
        new_name = str(item.text(0) or "").strip()
        if new_name == old_name:
            return
        try:
            if self.is_new_contract:
                # Pending modda: in-memory güncelle
                for f in self._pending_doc_folders:
                    if f["id"] == folder_id:
                        parent_id = f.get("parent_id")
                        existing = {pf["name"] for pf in self._pending_doc_folders if pf.get("parent_id") == parent_id and pf["id"] != folder_id}
                        if new_name in existing:
                            raise ValueError("Aynı seviyede bu klasör adı zaten var.")
                        f["name"] = new_name
                        break
                item.setData(0, Qt.UserRole + 3, new_name)
            else:
                renamed = self.store.rename_contract_file_folder(folder_id, new_name)
                item.setData(0, Qt.UserRole + 3, str(renamed.get("name") or new_name))
            self._mark_documents_changed()
            # Ağacı yeniden render ETME – sadece badge güncelle.
            # render_contract_files() tüm tree'yi silip yeniden kurar,
            # bu da expand state'i sıfırlayıp dosyaları "kaybeder" görüntüsü verir.
            self.update_side_meta_badges()
        except Exception as exc:
            self._building_file_tree = True
            try:
                item.setText(0, old_name)
            finally:
                self._building_file_tree = False
            QMessageBox.warning(self, "Klasör adı değiştirilemedi", str(exc))

    def _begin_side_meta_modal_action(self):
        self._side_meta_modal_open = True
        self._tree_editing = True

    def _end_side_meta_modal_action(self):
        self._side_meta_modal_open = False
        self._tree_editing = False
        if getattr(self, "_side_meta_last_panel", None) == "files":
            QTimer.singleShot(0, self._restore_documents_popover_if_needed)

    def _restore_documents_popover_if_needed(self):
        popover = getattr(self, "side_meta_popover", None)
        if popover is None or getattr(self, "_side_meta_last_panel", None) != "files":
            return
        self._side_meta_open_panel = "files"
        self._sync_side_meta_controls()
        self.position_side_meta_popover()
        popover.show()
        popover.raise_()

    def delete_contract_file_folder(self, folder_id, folder_name):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        self._begin_side_meta_modal_action()
        try:
            msg = (
                f'"{folder_name}" klasörü, alt klasörleri ve içindeki tüm belgeler STS dosyasından silinecek.\n'
                "Bu işlem geri alınamaz."
            )
            if not ask_yes_no(self, "Klasörü Sil", msg):
                return
            try:
                if self.is_new_contract:
                    # Pending modda recursive sil
                    def _collect_pending_folder_ids(fid):
                        ids = [fid]
                        for f in self._pending_doc_folders:
                            if f.get("parent_id") == fid:
                                ids.extend(_collect_pending_folder_ids(f["id"]))
                        return ids
                    all_ids = set(_collect_pending_folder_ids(folder_id))
                    self._pending_doc_folders = [f for f in self._pending_doc_folders if f["id"] not in all_ids]
                    self._pending_doc_files = [f for f in self._pending_doc_files if f.get("folder_id") not in all_ids]
                else:
                    self.store.delete_contract_file_folder(folder_id)
                self._mark_documents_changed()
                self.render_contract_files()
            except Exception as exc:
                QMessageBox.warning(self, "Klasör silinemedi", str(exc))
        finally:
            self._end_side_meta_modal_action()

    def show_contract_file_tree_menu(self, pos):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        tree = getattr(self, "contract_files_tree", None)
        item = tree.itemAt(pos) if tree else None
        if not item:
            return
        kind = item.data(0, Qt.UserRole)
        # Seçili dosyalar
        sel_file_ids = [
            int(it.data(0, Qt.UserRole + 1))
            for it in tree.selectedItems()
            if it.data(0, Qt.UserRole) == "file"
        ]
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#ffffff;border:1px solid #d5e0ee;border-radius:10px;padding:4px;}"
            "QMenu::item{padding:7px 18px 7px 12px;border-radius:7px;font-size:12px;color:#0f172a;}"
            "QMenu::item:selected{background:#eef5ff;color:#1d4ed8;}"
            "QMenu::separator{height:1px;background:#e8eff8;margin:4px 8px;}"
        )
        # Menü açıkken popup kapanmasın
        self._tree_editing = True
        menu.aboutToHide.connect(lambda: setattr(self, "_tree_editing", False))

        _zip_icon = self._make_file_icon("zip")

        if kind == "file":
            file_id = int(item.data(0, Qt.UserRole + 1))
            if len(sel_file_ids) > 1:
                menu.addAction(f"📄  {len(sel_file_ids)} dosya seçili")
                a = menu.actions()[-1]; a.setEnabled(False)
                menu.addSeparator()
                menu.addAction("⬇  Tümünü İndir", lambda ids=sel_file_ids: self._bulk_download_files(ids))
                act = menu.addAction("  ZIP Olarak İndir", lambda ids=sel_file_ids: self._bulk_zip_files(ids))
                act.setIcon(_zip_icon)
                menu.addSeparator()
                menu.addAction("🗑  Seçilenleri Sil", lambda ids=sel_file_ids: self._bulk_delete_files(ids))
            else:
                menu.addAction("📂  Aç", lambda: self.open_contract_file(file_id))
                menu.addAction("⬇  İndir", lambda fid=file_id: self._bulk_download_files([fid]))
                act = menu.addAction("  ZIP Olarak İndir", lambda fid=file_id: self._bulk_zip_files([fid]))
                act.setIcon(_zip_icon)
                menu.addSeparator()
                menu.addAction("🗑  Sil", lambda: self.delete_contract_file(file_id))

        elif kind == "folder":
            folder_id = int(item.data(0, Qt.UserRole + 1))
            folder_name = str(item.data(0, Qt.UserRole + 3) or item.text(0))
            # Seçili klasörün parent_id'sini al (üst klasör eklemek için)
            _folder_parent_id = item.data(0, Qt.UserRole + 2)
            menu.addAction("➕  Dosya Ekle", lambda: self._add_files_to_folder(folder_id))
            menu.addAction("📁  Alt Klasör Ekle", lambda: self._add_subfolder(folder_id))
            menu.addAction("📂  Üst Klasör Ekle", lambda pid=_folder_parent_id: self._add_subfolder(pid))
            menu.addSeparator()
            menu.addAction("⬇  Klasörü İndir (Klasör Olarak)", lambda fid=folder_id, fname=folder_name: self._download_folder(fid, fname, as_zip=False))
            act = menu.addAction("  Klasörü İndir (ZIP)", lambda fid=folder_id, fname=folder_name: self._download_folder(fid, fname, as_zip=True))
            act.setIcon(_zip_icon)
            menu.addSeparator()
            menu.addAction("✏  Yeniden Adlandır", lambda i=item: self._start_rename_item(i))
            menu.addSeparator()
            menu.addAction("🗑  Sil", lambda: self.delete_contract_file_folder(folder_id, folder_name))

        menu.exec(tree.viewport().mapToGlobal(pos))

    def _add_files_to_folder(self, folder_id):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        """Belirli bir klasöre dosya ekle."""
        if not self._ensure_document_access(interactive=True):
            return
        self._file_dialog_open = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Klasöre Dosya Ekle",
                "",
                "Documents (*.pdf *.doc *.docx *.xls *.xlsx *.xlsm *.ppt *.pptx *.txt *.png *.jpg *.jpeg);;All Files (*.*)",
            )
        finally:
            self._file_dialog_open = False
        if paths:
            self._add_contract_files(paths, folder_id)

    def _add_subfolder(self, parent_folder_id):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        """Mevcut klasörün altına alt klasör ekle."""
        if not self._ensure_document_access(interactive=True):
            return
        try:
            if self.is_new_contract:
                base_name = "Yeni Klasör"
                existing = {f["name"] for f in self._pending_doc_folders if f.get("parent_id") == parent_folder_id}
                name = base_name
                idx = 2
                while name in existing:
                    name = f"{base_name} ({idx})"
                    idx += 1
                new_id = self._pending_doc_next_id
                self._pending_doc_next_id -= 1
                folder = {"id": new_id, "parent_id": parent_folder_id, "name": name, "created_at": "", "updated_at": ""}
                self._pending_doc_folders.append(folder)
                created = folder
            else:
                created = self.store.create_contract_file_folder(
                    self.ci.platform, self.ci.no, self.ci.contract_type, parent_id=parent_folder_id
                )
            self._mark_documents_changed()
            tree = getattr(self, "contract_files_tree", None)
            if tree:
                _folder_icon = self._make_folder_icon()
                new_item = QTreeWidgetItem([str(created.get("name") or "Yeni Klasör")])
                new_item.setIcon(0, _folder_icon)
                new_item.setData(0, Qt.UserRole, "folder")
                new_item.setData(0, Qt.UserRole + 1, int(created.get("id") or 0))
                new_item.setData(0, Qt.UserRole + 2, created.get("parent_id"))
                new_item.setData(0, Qt.UserRole + 3, str(created.get("name") or "Yeni Klasör"))
                new_item.setFlags(new_item.flags() | Qt.ItemIsEditable | Qt.ItemIsDropEnabled)
                # parent_folder_id'ye sahip tree item'ı bul
                _pid = parent_folder_id
                _par = None
                if _pid:
                    def _fp(n):
                        for _i in range(n):
                            _t = tree.topLevelItem(_i)
                            if _t and _t.data(0, Qt.UserRole) == "folder":
                                try:
                                    if int(_t.data(0, Qt.UserRole + 1)) == int(_pid):
                                        return _t
                                except Exception:
                                    pass
                                for _j in range(_t.childCount()):
                                    _c = _t.child(_j)
                                    if _c and _c.data(0, Qt.UserRole) == "folder":
                                        try:
                                            if int(_c.data(0, Qt.UserRole + 1)) == int(_pid):
                                                return _c
                                        except Exception:
                                            pass
                        return None
                    _par = _fp(tree.topLevelItemCount())
                if _par:
                    _par.addChild(new_item)
                    _par.setExpanded(True)
                else:
                    tree.addTopLevelItem(new_item)
                tree.scrollToItem(new_item)
                self._start_rename_item(new_item)
                all_f = list(getattr(self, "_side_meta_folders", []))
                all_files = list(getattr(self, "_side_meta_files", []))
                new_h = self.document_tree_height(all_f, all_files)
                tree.setMinimumHeight(new_h)
                tree.setMaximumHeight(new_h)
            else:
                self.render_contract_files()
            self.update_side_meta_badges()
        except Exception as exc:
            QMessageBox.warning(self, "Alt klasör eklenemedi", str(exc))

    def _bulk_download_files(self, file_ids: list):
        """Seçili dosyaları klasöre indir."""
        if not self.require_permission_ui("export_data", "Belge Dışa Aktar"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        if not file_ids:
            return
        folder = QFileDialog.getExistingDirectory(self, "İndirme Klasörü Seç")
        if not folder:
            return
        errors = []
        for fid in file_ids:
            try:
                filename, _mime, content = self.store.get_contract_file_bytes(fid)
                target = Path(folder) / filename
                counter = 1
                while target.exists():
                    target = Path(folder) / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
                    counter += 1
                target.write_bytes(content)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            QMessageBox.warning(self, "Bazı dosyalar indirilemedi", "\n".join(errors[:5]))
        else:
            QMessageBox.information(self, "İndirme tamamlandı", f"{len(file_ids)} dosya indirildi.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _bulk_zip_files(self, file_ids: list):
        """Seçili dosyaları ZIP olarak indir."""
        if not self.require_permission_ui("export_data", "Belge Dışa Aktar"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        if not file_ids:
            return
        default_name = f"{self.ci.no}_belgeler.zip" if hasattr(self, "ci") else "belgeler.zip"
        target, _ = QFileDialog.getSaveFileName(self, "ZIP Kaydet", default_name, "ZIP (*.zip)")
        if not target:
            return
        try:
            added_count = 0
            errors = []
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                seen: dict = {}
                for fid in file_ids:
                    try:
                        filename, _mime, file_content = self.store.get_contract_file_bytes(fid)
                        arc_name = filename
                        if arc_name in seen:
                            seen[arc_name] += 1
                            stem = Path(arc_name).stem
                            ext = Path(arc_name).suffix
                            arc_name = f"{stem}_{seen[filename]}{ext}"
                        else:
                            seen[arc_name] = 0
                        zf.writestr(arc_name, file_content)
                        added_count += 1
                    except Exception as exc:
                        errors.append(str(exc))
            if added_count == 0:
                import os
                try:
                    os.unlink(target)
                except Exception:
                    pass
                msg = "Hiçbir dosya ZIP'e eklenemedi."
                if errors:
                    msg += "\n\nHatalar:\n" + "\n".join(errors[:5])
                QMessageBox.warning(self, "ZIP oluşturulamadı", msg)
                return
            if errors:
                msg = f"{added_count} dosya ZIP'e eklendi, {len(errors)} dosya eklenemedi.\n\nİlk hatalar:\n" + "\n".join(errors[:5])
                QMessageBox.warning(self, "ZIP kısmen oluşturuldu", msg)
            else:
                QMessageBox.information(self, "ZIP oluşturuldu", f"{added_count} dosya ZIP'e eklendi.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).parent)))
        except Exception as exc:
            QMessageBox.warning(self, "ZIP oluşturulamadı", str(exc))

    def _bulk_delete_files(self, file_ids: list):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        """Seçili dosyaları sil."""
        if not self._ensure_document_access(interactive=True):
            return
        if not file_ids:
            return
        self._begin_side_meta_modal_action()
        try:
            if not ask_yes_no(
                self, "Dosyaları Sil",
                f"{len(file_ids)} dosyayı silmek istediğinize emin misiniz?\nBu işlem geri alınamaz.",
            ):
                return
            for fid in file_ids:
                try:
                    self.store.delete_contract_file(fid)
                except Exception:
                    pass
            self._mark_documents_changed()
            self.render_contract_files()
        finally:
            self._end_side_meta_modal_action()

    def _download_folder(self, folder_id: int, folder_name: str, as_zip: bool = True):
        """Klasör ve tüm alt klasörlerini/dosyalarını recursive indir."""
        if not self.require_permission_ui("export_data", "Belge Dışa Aktar"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        # Tüm dosya ve klasör verisini yükle
        all_files = list(self._side_meta_files)
        all_folders = list(getattr(self, "_side_meta_folders", []))

        # Klasör hiyerarşisini kur: folder_id → children
        folders_by_id = {int(f["id"]): f for f in all_folders if f.get("id")}
        children_by_parent: dict = {}
        for f in all_folders:
            pid = f.get("parent_id")
            try:
                pid = int(pid) if pid not in (None, "", 0) else None
            except (TypeError, ValueError):
                pid = None
            children_by_parent.setdefault(pid, []).append(f)

        def collect_folder_file_ids(fid, path_prefix=""):
            """Klasör altındaki tüm dosyaları (recursive) (file_id, arc_path) olarak döner."""
            fname = folders_by_id.get(fid, {}).get("name", str(fid))
            cur_path = f"{path_prefix}{fname}/" if path_prefix else f"{fname}/"
            result = []
            # Bu klasördeki dosyalar
            for f in all_files:
                try:
                    ffid = int(f.get("folder_id") or 0)
                except (TypeError, ValueError):
                    ffid = 0
                if ffid == fid:
                    result.append((int(f["id"]), f.get("filename", "dosya"), cur_path))
            # Alt klasörler recursive
            for child in children_by_parent.get(fid, []):
                result.extend(collect_folder_file_ids(int(child["id"]), cur_path))
            return result

        entries = collect_folder_file_ids(folder_id)

        if not entries:
            QMessageBox.information(self, "Boş Klasör", f'"{folder_name}" klasöründe indirilecek dosya yok.')
            return

        if as_zip:
            # ZIP olarak indir
            default_name = f"{folder_name}.zip"
            target, _ = QFileDialog.getSaveFileName(self, "ZIP Kaydet", default_name, "ZIP (*.zip)")
            if not target:
                return
            try:
                dl_added_count = 0
                dl_errors = []
                seen: dict = {}
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file_id, filename, arc_prefix in entries:
                        arc_name = arc_prefix + filename
                        # Çakışma önle
                        if arc_name in seen:
                            seen[arc_name] += 1
                            stem = Path(filename).stem
                            ext = Path(filename).suffix
                            arc_name = arc_prefix + f"{stem}_{seen[arc_name]}{ext}"
                        else:
                            seen[arc_name] = 0
                        try:
                            _, _mime, dl_content = self.store.get_contract_file_bytes(file_id)
                            zf.writestr(arc_name, dl_content)
                            dl_added_count += 1
                        except Exception as exc:
                            dl_errors.append(f"{filename}: {exc}")
                if dl_added_count == 0:
                    import os as _os
                    try:
                        _os.unlink(target)
                    except Exception:
                        pass
                    msg = "Hiçbir dosya ZIP'e eklenemedi."
                    if dl_errors:
                        msg += "\n\nHatalar:\n" + "\n".join(dl_errors[:5])
                    QMessageBox.warning(self, "ZIP oluşturulamadı", msg)
                    return
                if dl_errors:
                    msg = f"{dl_added_count} dosya ZIP'e eklendi, {len(dl_errors)} dosya eklenemedi.\n\nİlk hatalar:\n" + "\n".join(dl_errors[:5])
                    QMessageBox.warning(self, "ZIP kısmen oluşturuldu", msg)
                else:
                    QMessageBox.information(self, "ZIP oluşturuldu", f"{dl_added_count} dosya ZIP'e eklendi.\n{target}")
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).parent)))
            except Exception as exc:
                QMessageBox.warning(self, "ZIP oluşturulamadı", str(exc))
        else:
            # Klasör yapısıyla indir
            base_dir = QFileDialog.getExistingDirectory(self, f'"{folder_name}" için hedef klasör seç')
            if not base_dir:
                return
            errors = []
            for file_id, filename, arc_prefix in entries:
                try:
                    _, _mime, content = self.store.get_contract_file_bytes(file_id)
                    dest_dir = Path(base_dir) / arc_prefix
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / filename
                    counter = 1
                    while dest_file.exists():
                        dest_file = dest_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
                        counter += 1
                    dest_file.write_bytes(content)
                except Exception as exc:
                    errors.append(f"{filename}: {exc}")
            if errors:
                QMessageBox.warning(self, "Bazı dosyalar indirilemedi", "\n".join(errors[:5]))
            else:
                QMessageBox.information(self, "İndirme tamamlandı",
                    f"{len(entries)} dosya indirildi.\nHedef: {base_dir}/{folder_name}/")
                QDesktopServices.openUrl(QUrl.fromLocalFile(base_dir))

    def refresh_contract_tags_panel(self):
        self.update_side_meta_badges()
        if self._side_meta_open_panel == "tags":
            self.render_side_meta_popover_content("tags")

    def render_contract_tags(self):
        self.refresh_contract_tags_panel()

    def render_contract_files(self):
        self.refresh_contract_files_panel()

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        size = float(size_bytes or 0)
        if size < 1024: return f"{int(size)} B"
        if size < 1024 * 1024: return f"{size / 1024:.0f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def format_file_date(created_at: str) -> str:
        raw = str(created_at or "").strip()
        if not raw: return "-"
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return "Bugün" if parsed.date() == date.today() else parsed.strftime("%d.%m.%Y")
        except ValueError:
            return raw[:10]

    @staticmethod
    def file_type_style(ext: str) -> Tuple[str, str]:
        extension = str(ext or "").strip().lower()
        if extension == "pdf": return "PDF", "#ef4444"
        if extension in {"doc", "docx"}: return "DOC", "#2563eb"
        if extension in {"xls", "xlsx", "xlsm"}: return "XLS", "#16a34a"
        if extension in {"ppt", "pptx"}: return "PPT", "#f97316"
        if extension in {"png", "jpg", "jpeg"}: return "IMG", "#7c3aed"
        return "TXT", "#64748b"

    def create_file_card(self, metadata: dict) -> QFrame:
        file_id = int(metadata["id"]); filename = str(metadata.get("filename") or "")
        ext = str(metadata.get("file_ext") or "").upper() or "DOSYA"
        icon_text, icon_color = self.file_type_style(ext)
        card = QFrame(); card.setObjectName("sideFileCard"); card.setMinimumWidth(0); card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); card.setFixedHeight(56); card.setProperty("contractFileId", file_id); card.installEventFilter(self)
        card.setStyleSheet("QFrame#sideFileCard{background:#f8fbff; border:1px solid #dbe7f5; border-radius:12px;} QFrame#sideFileCard:hover{background:#eef6ff; border-color:#b8cef0;} QLabel{background:transparent; border:0;} QToolButton{background:#ffffff; color:#334155; border:1px solid #d8e4f2; border-radius:8px; font-size:16px; font-weight:900;} QToolButton:hover{background:#eff6ff; border-color:#b8cef0;}")
        row = QHBoxLayout(card); row.setContentsMargins(9, 7, 9, 7); row.setSpacing(8)
        icon = QLabel(icon_text); icon.setFixedSize(36, 36); icon.setAlignment(Qt.AlignCenter); icon.setStyleSheet(f"background:{icon_color}; color:#0f172a; border-radius:11px; font-size:13px; font-weight:900;")
        middle = QWidget(); middle.setMinimumWidth(0); middle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); middle.setStyleSheet("background:transparent;"); column = QVBoxLayout(middle); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(2)
        title = ElidedLabel(filename); title.setMinimumWidth(0); title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); title.setToolTip(filename); title.setStyleSheet("color:#10233d; font-size:12px; font-weight:900;")
        meta = QLabel(f"{ext}  ·  {self.format_file_size(metadata.get('size_bytes', 0))}  ·  {self.format_file_date(metadata.get('created_at', ''))}"); meta.setMinimumWidth(0); meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); meta.setStyleSheet("color:#64748b; font-size:10px;")
        column.addWidget(title); column.addWidget(meta)
        menu_btn = QToolButton(); menu_btn.setText("⋯"); menu_btn.setFixedSize(30, 30); menu_btn.setToolTip("Menü"); menu_btn.clicked.connect(lambda _=False, fid=file_id, btn=menu_btn: self.show_contract_file_button_menu(fid, btn))
        row.addWidget(icon); row.addWidget(middle, 1); row.addWidget(menu_btn)
        return card

    def refresh_contract_files_panel(self):
        self.update_side_meta_badges()
        if self._side_meta_open_panel == "files":
            self.render_side_meta_popover_content("files")

    def _pick_contract_files(self):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        self._file_dialog_open = True
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Sözleşmeye Dosya Ekle",
                "",
                "Documents (*.pdf *.doc *.docx *.xls *.xlsx *.xlsm *.ppt *.pptx *.txt *.png *.jpg *.jpeg);;All Files (*.*)",
            )
        finally:
            self._file_dialog_open = False
        if not paths:
            return
        self._add_contract_files(paths, self._selected_document_folder_id())

    def _handle_tree_item_move(self, kind: str, item_id: int, target_folder_id):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        """Tree içinde sürükle-bırak taşıma işlemini yönet."""
        if not self._ensure_document_access(interactive=True):
            return
        try:
            if self.is_new_contract:
                # Pending modda in-memory taşıma
                if kind == "file":
                    for f in self._pending_doc_files:
                        if f["id"] == item_id:
                            f["folder_id"] = target_folder_id
                            break
                elif kind == "folder":
                    # Kendi altına taşınamaz
                    def is_descendant_pending(fid, anc_id):
                        for ff in self._pending_doc_folders:
                            if ff["id"] == fid:
                                pid = ff.get("parent_id")
                                if pid is None:
                                    return False
                                if pid == anc_id:
                                    return True
                                return is_descendant_pending(pid, anc_id)
                        return False
                    if target_folder_id == item_id:
                        QMessageBox.warning(self, "Taşınamaz", "Klasör kendi içine taşınamaz.")
                        return
                    if target_folder_id is not None and is_descendant_pending(target_folder_id, item_id):
                        QMessageBox.warning(self, "Taşınamaz", "Klasör kendi alt klasörüne taşınamaz.")
                        return
                    for f in self._pending_doc_folders:
                        if f["id"] == item_id:
                            f["parent_id"] = target_folder_id
                            break
            else:
                if kind == "file":
                    self.store.move_contract_file(item_id, target_folder_id)
                elif kind == "folder":
                    self.store.move_contract_file_folder(item_id, target_folder_id)
            self._mark_documents_changed()
            self.render_contract_files()
        except Exception as exc:
            QMessageBox.warning(self, "Taşıma hatası", str(exc))

    def _add_contract_files(self, file_paths, folder_id=None):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        paths = [str(path or "").strip() for path in (file_paths or []) if str(path or "").strip()]
        if not paths:
            return
        added = 0
        duplicates = 0
        failures = []
        ALLOWED = {"pdf", "doc", "docx", "xls", "xlsx", "xlsm", "ppt", "pptx", "png", "jpg", "jpeg", "txt"}
        BLOCKED = {"exe", "bat", "cmd", "ps1", "sh", "msi", "dll", "com", "scr", "vbs", "js"}
        for raw_path in paths:
            path = Path(raw_path)
            try:
                if not path.exists():
                    raise ValueError("Dosya seçilemedi veya bulunamadı.")
                if path.is_dir():
                    raise ValueError("Klasör yüklenemez, lütfen dosya seçin.")
                if not path.is_file():
                    raise ValueError("Lütfen geçerli bir dosya seçin.")
                if not os.access(path, os.R_OK):
                    raise ValueError("Dosya okunamıyor.")
                if self.is_new_contract:
                    # Pending modda: bytes olarak in-memory sakla
                    import mimetypes as _mt
                    ext = path.suffix.lower().lstrip(".")
                    if ext in BLOCKED or ext not in ALLOWED:
                        raise ValueError("Bu dosya türü desteklenmiyor.")
                    from src.config.app_config import MAX_CONTRACT_FILE_SIZE_BYTES
                    size = path.stat().st_size
                    if size > MAX_CONTRACT_FILE_SIZE_BYTES:
                        raise ValueError("Dosya boyutu 120 MB üstünde olamaz.")
                    # Duplicate kontrolü
                    is_dup = any(
                        f["filename"] == path.name and f.get("size_bytes") == size
                        for f in self._pending_doc_files
                    )
                    if is_dup:
                        duplicates += 1
                        continue
                    content_bytes = path.read_bytes()
                    mime = _mt.guess_type(path.name)[0] or "application/octet-stream"
                    new_id = self._pending_doc_next_id
                    self._pending_doc_next_id -= 1
                    self._pending_doc_files.append({
                        "id": new_id,
                        "folder_id": folder_id,
                        "filename": path.name,
                        "file_ext": ext,
                        "mime_type": mime,
                        "size_bytes": size,
                        "content_blob": content_bytes,
                        "note": "",
                        "created_at": "",
                        "updated_at": "",
                        "_source_path": str(path),
                    })
                    added += 1
                else:
                    self.store.add_contract_file(self.ci.platform, self.ci.no, path, self.ci.contract_type, folder_id=folder_id)
                    added += 1
            except Exception as exc:
                message = str(exc)
                if "zaten ekli" in message.lower():
                    duplicates += 1
                else:
                    failures.append(f"{path.name or raw_path}: {message}")
        if added:
            self._mark_documents_changed()
            self.render_contract_files()
        if failures:
            QMessageBox.warning(self, "Bazı dosyalar eklenemedi", "\n".join(failures[:8]))
        if added or duplicates:
            if added and duplicates:
                QMessageBox.information(self, "Belgeler güncellendi", f"{added} dosya eklendi, {duplicates} dosya zaten ekli olduğu için atlandı.")
            elif duplicates and not failures:
                QMessageBox.information(self, "Bu belge zaten ekli", "Seçilen belge zaten ekli.")
            elif added > 1:
                QMessageBox.information(self, "Belgeler eklendi", f"{added} dosya eklendi.")

    def _handle_contract_files_drop(self, file_paths):
        self._add_contract_files(file_paths)

    def _flush_pending_documents_to_db(self):
        """Yeni sözleşme kaydedildikten sonra pending belge ve klasörleri DB'ye yaz."""
        if not self._pending_doc_folders and not self._pending_doc_files:
            return
        # Klasör id eşleme: pending (negatif) id → gerçek DB id
        id_map: dict = {}  # pending_id → real_db_id

        def flush_folder_tree(pending_parent_id, real_parent_id):
            """Pending klasörleri hiyerarşiyle DB'ye yaz."""
            children = [f for f in self._pending_doc_folders if f.get("parent_id") == pending_parent_id]
            for folder in children:
                created = self.store.create_contract_file_folder(
                    self.ci.platform, self.ci.no, self.ci.contract_type,
                    parent_id=real_parent_id, name=folder["name"]
                )
                real_id = int(created.get("id") or 0)
                id_map[folder["id"]] = real_id
                flush_folder_tree(folder["id"], real_id)

        flush_folder_tree(None, None)

        # Dosyaları DB'ye yaz
        for f in self._pending_doc_files:
            pending_folder_id = f.get("folder_id")
            real_folder_id = id_map.get(pending_folder_id) if pending_folder_id else None
            try:
                src = f.get("_source_path")
                if src and Path(src).is_file():
                    self.store.add_contract_file(
                        self.ci.platform, self.ci.no, Path(src),
                        self.ci.contract_type, folder_id=real_folder_id, note=f.get("note", "")
                    )
                else:
                    # Dosya path'i yoksa bytes'tan geçici dosya oluştur
                    import tempfile
                    suffix = f".{f.get('file_ext', 'bin')}"
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(f.get("content_blob", b""))
                        tmp_path = tmp.name
                    try:
                        # Orijinal dosya adını koruyarak ekle
                        original_name = f.get("filename", "dosya")
                        target_tmp = Path(tmp_path).parent / original_name
                        Path(tmp_path).rename(target_tmp)
                        self.store.add_contract_file(
                            self.ci.platform, self.ci.no, target_tmp,
                            self.ci.contract_type, folder_id=real_folder_id, note=f.get("note", "")
                        )
                    finally:
                        try:
                            import os
                            if Path(tmp_path).exists():
                                os.unlink(tmp_path)
                        except Exception:
                            pass
            except Exception:
                pass  # Tek dosya hatasını yutma ama devam et (duplicate vs)

        # Pending yapıyı temizle
        self._pending_doc_folders.clear()
        self._pending_doc_files.clear()

    def _import_contract_folders(self, folder_paths, parent_folder_id=None):
        if getattr(self, "_import_contract_folders_running", False):
            return
        self._import_contract_folders_running = True
        try:
            if not self._ensure_share_can_edit("Belgeler"):
                return
            """Windows'tan sürüklenen klasörleri recursive olarak STS içine aktarır."""
            if not self._ensure_document_access(interactive=True):
                return
            ALLOWED_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "xlsm", "ppt", "pptx", "png", "jpg", "jpeg", "txt"}

            added_files = 0
            skipped_files = 0
            errors = []

            def import_folder(fs_path, db_parent_id):
                """Tek klasörü recursive içe aktar. Klasörü DB'de oluştur, dosyalarını ekle."""
                nonlocal added_files, skipped_files
                fs_path = Path(fs_path)
                folder_name = fs_path.name or "Klasör"
                # Klasörü DB'ye oluştur
                try:
                    created = self.store.create_contract_file_folder(
                        self.ci.platform, self.ci.no, self.ci.contract_type,
                        parent_id=db_parent_id, name=folder_name
                    )
                    db_folder_id = int(created.get("id") or 0)
                except Exception as exc:
                    errors.append(f"Klasör oluşturulamadı ({folder_name}): {exc}")
                    return

                # Dosyaları ekle
                try:
                    children = sorted(fs_path.iterdir(), key=lambda p: (p.is_dir(), p.name.casefold()))
                except Exception as exc:
                    errors.append(f"Klasör okunamadı ({folder_name}): {exc}")
                    return

                for child in children:
                    QApplication.processEvents()
                    if child.is_dir():
                        import_folder(child, db_folder_id)
                    elif child.is_file():
                        ext = child.suffix.lower().lstrip(".")
                        if ext not in ALLOWED_EXTS:
                            skipped_files += 1
                            continue
                        try:
                            self.store.add_contract_file(
                                self.ci.platform, self.ci.no, child,
                                self.ci.contract_type, folder_id=db_folder_id
                            )
                            added_files += 1
                        except Exception as exc:
                            msg = str(exc)
                            if "zaten ekli" in msg.lower():
                                skipped_files += 1
                            else:
                                errors.append(f"{child.name}: {msg}")

            for fp in (folder_paths or []):
                import_folder(fp, parent_folder_id)
                QApplication.processEvents()

            self._mark_documents_changed()
            self.render_contract_files()

            # Özet mesajı
            parts = []
            if added_files:
                parts.append(f"{added_files} dosya eklendi")
            if skipped_files:
                parts.append(f"{skipped_files} desteklenmeyen/zaten ekli dosya atlandı")
            summary = ", ".join(parts) if parts else "Eklenecek dosya bulunamadı."
            if errors:
                summary += f"\n\nHatalar ({len(errors)}):\n" + "\n".join(errors[:5])
                QMessageBox.warning(self, "Klasör İçe Aktarma", summary)
            elif added_files or skipped_files:
                QMessageBox.information(self, "Klasör İçe Aktarıldı", summary)
        finally:
            self._import_contract_folders_running = False

    def add_contract_file(self):
        self._pick_contract_files()

    def open_contract_file(self, file_id: int):
        if not self._ensure_document_access(interactive=True):
            return
        try:
            filename, _mime, content = self.store.get_contract_file_bytes(file_id)
            suffix = Path(filename).suffix
            temp = tempfile.NamedTemporaryFile(prefix="sts_contract_", suffix=suffix, delete=False)
            try:
                temp.write(content)
            finally:
                temp.close()
            QDesktopServices.openUrl(QUrl.fromLocalFile(temp.name))
        except Exception as exc:
            QMessageBox.warning(self, "Belge açılamadı", str(exc))

    def export_contract_file(self, file_id: int):
        if not self.require_permission_ui("export_data", "Belge Dışa Aktar"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        try:
            filename, _mime, _content = self.store.get_contract_file_bytes(file_id)
            target, _ = QFileDialog.getSaveFileName(self, "Belgeyi Dışa Aktar", filename)
            if not target:
                return
            self.store.export_contract_file(file_id, target)
            QMessageBox.information(self, "Belge dışa aktarıldı", "Belge başarıyla dışa aktarıldı.")
        except Exception as exc:
            QMessageBox.warning(self, "Belge dışa aktarılamadı", str(exc))

    def delete_contract_file(self, file_id: int):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        self._begin_side_meta_modal_action()
        try:
            if not ask_yes_no(self, "Belgeyi Sil", "Belge STS dosyasından silinsin mi? Orijinal dosyaya dokunulmaz."):
                return
            try:
                if self.is_new_contract:
                    self._pending_doc_files = [f for f in self._pending_doc_files if f["id"] != file_id]
                else:
                    self.store.delete_contract_file(file_id)
                self._mark_documents_changed()
                self.render_contract_files()
            except Exception as exc:
                QMessageBox.warning(self, "Belge silinemedi", str(exc))
        finally:
            self._end_side_meta_modal_action()

    def show_contract_file_button_menu(self, file_id: int, button):
        if not self._ensure_share_can_edit("Belgeler"):
            return
        if not self._ensure_document_access(interactive=True):
            return
        menu = QMenu(self)
        menu.addAction("Aç", lambda: self.open_contract_file(file_id))
        menu.addAction("Dışa Aktar", lambda: self.export_contract_file(file_id))
        menu.addSeparator()
        menu.addAction("Sil", lambda: self.delete_contract_file(file_id))
        menu.exec(button.mapToGlobal(QPoint(0, button.height())))

    def open_tag_assign_dialog(self):
        if self._share_labels_disabled():
            QMessageBox.information(self, "Etiketler", self._share_label_policy_message())
            return
        if not self._ensure_share_can_edit("Etiketler"):
            return
        dlg = TagAssignDialog(self.store, self.contract_tags, self)
        if not dlg.exec() or not dlg.result:
            return
        existing_map = {self._tag_key(str(t.get("name", ""))): dict(t) for t in self.contract_tags}
        for t in dlg.result:
            key = self._tag_key(str(t.get("name", "")))
            if not key:
                continue
            existing_map[key] = {
                "name": str(t.get("name", "")).strip(),
                "color": str(t.get("color", "#3B82F6")),
                "note": str(t.get("note", "")).strip(),
            }
        self.contract_tags = list(existing_map.values())
        self._set_dirty()
        self.render_contract_tags()

    def remove_contract_tag(self, tag_name: str):
        if self._share_labels_disabled():
            QMessageBox.information(self, "Etiketler", self._share_label_policy_message())
            return
        if not self._ensure_share_can_edit("Etiketler"):
            return
        key = self._tag_key(tag_name)
        self.contract_tags = [t for t in self.contract_tags if self._tag_key(str((t or {}).get("name", ""))) != key]
        self._set_dirty()
        self.render_contract_tags()

    def add_system(self):
        if not self._ensure_share_can_edit():
            return
        dlg = MultiSystemDialog(
            self.store,
            self.ci.platform,
            contract_t0_date=str(self.ci.t0_date or ""),
            existing_names=[s.name for s in self.systems],
            parent=self,
            events_provider=self.date_picker_events,
        )
        if dlg.exec() and dlg.result:
            first_name = ""
            for sys_info in dlg.result:
                if not first_name:
                    first_name = sys_info.name
                self.systems.append(sys_info)
                self._set_dirty()
                self.deliveries[sys_info.name] = []
            self.selected_system = first_name or self.selected_system
            self.expanded_delivery_index = None
            self.refresh()

    def edit_system(self):
        if not self._ensure_share_can_edit():
            return
        r = self.system_list.currentRow()
        if r < 0 or r >= len(self.systems):
            QMessageBox.warning(self, "Sistem yok", "Düzenlemek için bir sistem seçin.")
            return
        self.sync_summary_to_system()
        current = self.systems[r]
        old_name = current.name

        # pre_selected: gercekten kullanilan bilesenleri sec (qty>0 veya teslimatta gecen)
        pre_selected = self._component_display_keys(current)
        dlg = SystemDialog(
            self.store,
            self.ci.platform,
            default_name=current.name,
            parent=self,
            existing_system=current,
            edit_mode=True,
            pre_selected=pre_selected,
            default_t0_date=str(self.ci.t0_date or ""),
            events_provider=self.date_picker_events,
        )
        if not dlg.exec() or not dlg.result:
            return

        updated = dlg.result
        new_name = updated.name
        for i, s in enumerate(self.systems):
            if i != r and s.name.strip().lower() == new_name.strip().lower():
                QMessageBox.warning(self, "Çakışma", f"'{new_name}' adında başka bir sistem var.")
                return

        current.name = new_name
        removed_components = set(getattr(updated, "removed_components", set()) or set())
        current.components = {k: v for k, v in dict(updated.components).items() if k not in removed_components}
        current.component_notes = {k: v for k, v in (getattr(current, "component_notes", {}) or {}).items() if k in current.components}
        current.t0_date = updated.t0_date
        current.t0_months = updated.t0_months
        current.completion_date = updated.completion_date
        current.status = updated.status
        current.acceptance_date = updated.acceptance_date

        # Sistem adı değiştiyse teslimat anahtarını da taşı.
        if old_name != new_name:
            old_deliveries = self.deliveries.pop(old_name, [])
            self.deliveries[new_name] = old_deliveries

        # Bileşen seti değiştiyse teslimat satırlarını yeni sete hizala.
        # Kaldırılan bileşenler kabullerin planned/delivered sözlüklerinden tamamen çıkarılır;
        # böylece arayüzde görünmez ve Excel'e 0 yerine boş hücre olarak yazılır.
        comps = list(current.components.keys())
        comp_set = set(comps)
        self.deliveries.setdefault(new_name, [])
        for d in self.deliveries.get(new_name, []):
            d.planned = {k: max(as_number((d.planned or {}).get(k, 0)), 0) for k in comps}
            d.delivered = {k: max(as_number((d.delivered or {}).get(k, 0)), 0) for k in comps}
            for k in comps:
                if d.delivered[k] > d.planned[k]:
                    d.delivered[k] = d.planned[k]
                if d.planned[k] > current.components.get(k, 0):
                    d.planned[k] = current.components.get(k, 0)
                    d.delivered[k] = min(d.delivered[k], d.planned[k])
            for removed_key in set((d.planned or {}).keys()) - comp_set:
                d.planned.pop(removed_key, None)
            for removed_key in set((d.delivered or {}).keys()) - comp_set:
                d.delivered.pop(removed_key, None)

        self.selected_system = new_name
        self.expanded_delivery_index = None
        self.refresh()
        self.system_list.setCurrentRow(r)
        self.refresh_right()
        self._set_dirty()

    def delete_system(self):
        if not self._ensure_share_can_edit():
            return
        r = self.system_list.currentRow()
        if r >= 0:
            name = self.systems[r].name
            self.systems.pop(r)
            self._set_dirty()
            self.deliveries.pop(name, None)
            self.expanded_delivery_index = None
            self.refresh()

    def add_delivery(self):
        if not self._ensure_share_can_edit():
            return
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.add_delivery(self)

    def current_system(self) -> Optional[SystemInfo]:
        r = self.system_list.currentRow()
        if 0 <= r < len(self.systems):
            return self.systems[r]
        return None

    def select_system(self, idx):
        self.expanded_delivery_index = None

        if 0 <= idx < len(self.systems):
            self.selected_system = self.systems[idx].name

        self._populate_system_list(keep_row=idx)
        self.refresh_right()

    def _is_sd_type(self, contract_type: str) -> bool:
        return bool(re.match(r"^SD-\d+$", str(contract_type or "").strip().upper()))

    def _sd_sort_key(self, text: str):
        raw = str(text or "").strip().upper()
        m = re.match(r"^SD[-_ ]?(\d+)$", raw)
        if m:
            return (0, int(m.group(1)))
        parts = re.split(r"(\d+)", raw.lower())
        return (1, [int(p) if p.isdigit() else p for p in parts])

    def _context_key(self, ci: Optional[ContractInfo] = None) -> Tuple[str, str, str]:
        c = ci or self.ci
        return (
            str(getattr(c, "platform", "") or "").strip(),
            str(getattr(c, "no", "") or "").strip(),
            str(getattr(c, "contract_type", "") or "").strip(),
        )

    def _cache_current_context(self):
        if getattr(self, "_refreshing_contract_context", False):
            return
        key = self._context_key()
        if not all(key):
            return
        self.sync_summary_to_system()
        self._context_cache[key] = {
            "ci": copy.deepcopy(self.ci),
            "systems": copy.deepcopy(self.systems),
            "deliveries": copy.deepcopy(self.deliveries),
            "deleted_delivery_systems": set(self._deleted_delivery_systems),
            "tags": copy.deepcopy(self.contract_tags),
            "original_platform": str(self.original_platform or ""),
            "original_contract_no": str(self.original_contract_no or ""),
            "original_contract_type": str(self.original_contract_type or ""),
            "original_entry_start_row": int(self.original_entry_start_row or 0),
        }

    def _load_cached_context(self, key: Tuple[str, str, str]) -> bool:
        ctx = self._context_cache.get(key)
        if not ctx:
            return False
        self.ci = copy.deepcopy(ctx["ci"])
        self.systems = copy.deepcopy(ctx.get("systems") or [])
        self.deliveries = copy.deepcopy(ctx.get("deliveries") or {})
        self._deleted_delivery_systems = set(ctx.get("deleted_delivery_systems") or set())
        self.contract_tags = copy.deepcopy(ctx.get("tags") or [])
        self.original_platform = str(ctx.get("original_platform") or self.ci.platform or "")
        self.original_contract_no = str(ctx.get("original_contract_no") or self.ci.no or "")
        self.original_contract_type = str(ctx.get("original_contract_type") or self.ci.contract_type or "")
        self.original_entry_start_row = int(ctx.get("original_entry_start_row") or getattr(self.ci, "entry_start_row", 0) or 0)
        return True

    def _family_context_rows(self) -> List[dict]:
        platform = str(self.ci.platform or "").strip()
        no = str(self.ci.no or "").strip()
        rows = []
        try:
            rows = [
                dict(it) for it in self.store.list_main_contracts(platform)
                if str(it.get("no", "") or "").strip() == no
            ]
        except Exception:
            rows = []
        seen = {
            (str(it.get("platform", "") or "").strip(), str(it.get("no", "") or "").strip(), str(it.get("type", "") or "").strip())
            for it in rows
        }
        for key, ctx in self._context_cache.items():
            p, n, t = key
            if p != platform or n != no or key in seen:
                continue
            ci = ctx.get("ci")
            if not ci:
                continue
            rows.append({
                "platform": p,
                "no": n,
                "type": t,
                "type_display": t,
                "row": int(getattr(ci, "entry_start_row", 0) or ctx.get("original_entry_start_row") or 0),
                "is_main": not self._is_sd_type(t),
                "_cache_key": key,
            })
        return rows

    def _next_sd_code_for_family(self, platform: str, no: str) -> str:
        used: set[int] = set()
        try:
            for item in self.store.list_main_contracts(platform):
                if str(item.get("no", "") or "").strip() != no:
                    continue
                m = re.match(r"^SD-(\d+)$", str(item.get("type", "") or "").strip().upper())
                if m:
                    used.add(int(m.group(1)))
        except Exception:
            try:
                base_next = self.store.next_sd_code(platform, no)
                m = re.match(r"^SD-(\d+)$", str(base_next or "").strip().upper())
                if m and int(m.group(1)) > 1:
                    used.update(range(1, int(m.group(1))))
            except Exception:
                pass
        for key in self._context_cache.keys():
            p, n, t = key
            if p == platform and n == no:
                m = re.match(r"^SD-(\d+)$", str(t or "").strip().upper())
                if m:
                    used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        return f"SD-{n}"

    def _drop_context_cache_key(self, key: Tuple[str, str, str]):
        if key and all(key):
            self._context_cache.pop(key, None)

    def _drop_deleted_context_cache(self, info: dict):
        deleted = list((info or {}).get("deleted_contracts") or [])
        if not deleted and info:
            deleted = [{
                "platform": info.get("platform"),
                "contract_no": info.get("contract_no"),
                "contract_type": info.get("contract_type") or self.original_contract_type,
            }]
        for item in deleted:
            key = (
                str(item.get("platform", "") or "").strip(),
                str(item.get("contract_no", "") or "").strip(),
                str(item.get("contract_type", "") or "").strip(),
            )
            self._drop_context_cache_key(key)

    def refresh_sd_sidebar(self):
        if not hasattr(self, "sd_list"):
            return
        if not getattr(self, "_refreshing_contract_context", False):
            self._cache_current_context()
        current_key = self._context_key()
        current_row = int(getattr(self.ci, "entry_start_row", 0) or 0)
        current_type = str(getattr(self.ci, "contract_type", "") or "").strip()

        # Sözleşme Yok / geçici TBD sözleşmelerde sol SD/Ana sözleşme barı boş kalır.
        # Bu kayıtların gerçek ana sözleşme/SD ailesi yoktur; bu yüzden
        # "SÖZ\nANA", "-" veya alttaki "+" butonu kullanıcıya gösterilmez.
        try:
            is_unknown_contract = is_tbd_contract_no(str(getattr(self.ci, "no", "") or current_key[1] or ""))
        except Exception:
            is_unknown_contract = False
        if is_unknown_contract:
            self.sd_list.blockSignals(True)
            self.sd_list.clear()
            self.sd_list.blockSignals(False)
            if hasattr(self, "add_sd_btn"):
                self.add_sd_btn.setEnabled(False)
                self.add_sd_btn.setVisible(False)
            return

        if hasattr(self, "add_sd_btn"):
            self.add_sd_btn.setVisible(True)
        self.sd_list.blockSignals(True)
        self.sd_list.clear()
        family = self._family_context_rows()
        main_rows = [it for it in family if bool(it.get("is_main"))]
        sd_rows = [it for it in family if not bool(it.get("is_main"))]
        sd_rows.sort(key=lambda it: self._sd_sort_key(str(it.get("type", "") or "")))

        def add_item(label: str, row_data: dict, active: bool = False):
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            item.setData(Qt.UserRole, dict(row_data or {}))
            self.sd_list.addItem(item)
            if active:
                self.sd_list.setCurrentItem(item)

        if main_rows:
            main = dict(main_rows[0])
            main_key = tuple(main.get("_cache_key") or (main.get("platform"), main.get("no"), main.get("type")))
            add_item("SÖZ\nANA", main, main_key == current_key or (current_row and int(main.get("row") or 0) == current_row))
        else:
            platform, no, _t = current_key
            add_item("SÖZ\nANA", {
                "platform": platform, "no": no, "row": 0, "type": "Ana Sözleşme", "is_main": True,
                "_cache_key": (platform, no, "Ana Sözleşme"),
            }, not self._is_sd_type(current_type))
        for sd in sd_rows:
            label = str(sd.get("type", "SD") or "SD")
            sd_key = tuple(sd.get("_cache_key") or (sd.get("platform"), sd.get("no"), sd.get("type")))
            add_item(label, sd, sd_key == current_key or (current_row and int(sd.get("row") or 0) == current_row))
        self.sd_list.blockSignals(False)
        if hasattr(self, "add_sd_btn"):
            self.add_sd_btn.setVisible(True)
            self.add_sd_btn.setEnabled(bool(current_key[0] and current_key[1]))

    def on_sd_nav_changed(self, row: int):
        if getattr(self, "_refreshing_contract_context", False):
            return
        if row < 0 or not hasattr(self, "sd_list"):
            return
        item = self.sd_list.item(row)
        data = dict(item.data(Qt.UserRole) or {}) if item else {}
        key = tuple(data.get("_cache_key") or (data.get("platform"), data.get("no"), data.get("type")))
        if key == self._context_key():
            return
        self.switch_contract_context(data)

    def switch_contract_context(self, item: dict):
        self._cache_current_context()
        key = tuple(item.get("_cache_key") or (item.get("platform"), item.get("no"), item.get("type")))
        start_row = int(item.get("row") or 0)
        self._refreshing_contract_context = True
        try:
            if key in self._context_cache and self._load_cached_context(key):
                pass
            else:
                platform = str(item.get("platform") or self.ci.platform or "").strip()
                no = str(item.get("no") or self.ci.no or "").strip()
                if not platform or not no or start_row <= 0:
                    return
                self.set_busy_overlay(True, "Sözleşme detayı yükleniyor...", 25)
                try:
                    ci, systems, deliveries = self.store.load_contract_structure(platform, no, start_row=start_row)
                finally:
                    self.set_busy_overlay(False)
                if not ci:
                    QMessageBox.warning(self, "Bulunamadı", "Seçilen sözleşme/SD detayı okunamadı.")
                    return
                self.ci = ci
                self.original_platform = str(ci.platform or "")
                self.original_contract_no = str(ci.no or "")
                self.original_contract_type = str(ci.contract_type or "")
                self.original_entry_start_row = int(getattr(ci, "entry_start_row", 0) or 0)
                self.systems = systems or []
                self.deliveries = deliveries or {}
                self.contract_tags = self.store.load_contract_tags(
                    self.original_platform, self.original_contract_no, self.original_contract_type
                )
            self.expanded_delivery_index = None
            self.refresh_contract_header()
            self.render_contract_tags()
            self.refresh()
        finally:
            self._refreshing_contract_context = False

    def add_sd_contract(self):
        try:
            if is_tbd_contract_no(str(getattr(self.ci, "no", "") or "")):
                return
        except Exception:
            pass
        self._cache_current_context()
        platform = str(self.ci.platform or "").strip()
        no = str(self.ci.no or "").strip()
        if not platform or not no:
            QMessageBox.warning(self, "Eksik", "SD eklemek için önce ana sözleşme bilgisi bulunmalı.")
            return
        main_info = None
        try:
            main_info = self.store.find_main_contract_info(platform, no)
        except Exception:
            main_info = None
        main_key = (platform, no, "Ana Sözleşme")
        main_ctx = self._context_cache.get(main_key)
        if not main_info and not main_ctx:
            QMessageBox.warning(self, "Ana sözleşme bulunamadı", "SD eklemek için önce ana sözleşme detayında kalıp sistem bilgilerini girin.")
            return
        sd_code = self._next_sd_code_for_family(platform, no)
        sd_key = (platform, no, sd_code)
        if sd_key in self._context_cache:
            self.switch_contract_context({"_cache_key": sd_key, "platform": platform, "no": no, "type": sd_code})
            return
        source_ci = main_ctx.get("ci") if main_ctx else self.ci
        sd_ci = ContractInfo(
            no=no,
            platform=platform,
            user=str((main_info or {}).get("user") or getattr(source_ci, "user", "") or ""),
            users=list(getattr(source_ci, "users", []) or []),
            yi_yd=str((main_info or {}).get("yi_yd") or getattr(source_ci, "yi_yd", "Yİ") or "Yİ"),
            contract_type=sd_code,
            signature_date="",
            t0_date="",
            t0_months=0,
            completion_date="",
            status="Başlanmadı",
            note="",
            entry_start_row=0,
            sd_anchor_start_row=int((main_info or {}).get("block_start") or (main_info or {}).get("row") or 0),
            sd_anchor_end_row=int((main_info or {}).get("block_end") or (main_info or {}).get("row") or 0),
            sd_anchor_platform=platform if main_info else "",
            sd_anchor_no=no if main_info else "",
            responsible_engineer_id=int(getattr(source_ci, "responsible_engineer_id", 0) or 0),
            responsible_engineer_name=str(getattr(source_ci, "responsible_engineer_name", "") or ""),
        )
        dlg = ContractEditDialog(
            self.store,
            sd_ci,
            self,
            title_text="SD Ekleme Tablosu",
            save_text="SD Ekle",
            info_text="SD temel bilgilerini girin. Platform ve sözleşme no ana sözleşmeye bağlıdır; değiştirilemez.",
        )
        if not dlg.exec() or not dlg.result:
            return
        sd_ci = dlg.result
        self._context_cache[sd_key] = {
            "ci": sd_ci,
            "systems": [],
            "deliveries": {},
            "deleted_delivery_systems": set(),
            "tags": [],
            "original_platform": platform,
            "original_contract_no": no,
            "original_contract_type": sd_code,
            "original_entry_start_row": 0,
        }
        self.switch_contract_context({"_cache_key": sd_key, "platform": platform, "no": no, "type": sd_code})
        QMessageBox.information(self, "SD hazır", f"{sd_code} oluşturuldu. Sistem ve teslimatları ekleyip Kaydet'e basın.")

    def _default_acceptance_for(self, sys_info: SystemInfo) -> Optional[DeliveryInfo]:
        planned = {comp: max(as_number(qty), 0) for comp, qty in (sys_info.components or {}).items()}
        planned = {comp: qty for comp, qty in planned.items() if qty > 0.0001}
        if not planned:
            return None
        return DeliveryInfo(
            name="Teslimat 1",
            status="Başlanmadı",
            acceptance_date="",
            note="Sistem kaydedilirken otomatik oluşturuldu.",
            planned_acceptance_date="",
            planned=planned,
            delivered={comp: 0 for comp in planned.keys()},
            t0_date=str(getattr(sys_info, "t0_date", "") or ""),
            t0_months=int(getattr(sys_info, "t0_months", 0) or 0),
            completion_date=str(getattr(sys_info, "completion_date", "") or ""),
        )

    def _norm_status_text(self, status: str) -> str:
        txt = str(status or "").strip().lower()
        repl = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"}
        for a, b in repl.items():
            txt = txt.replace(a, b)
        return re.sub(r"\s+", " ", txt)

    def _delivery_is_delivered(self, delivery: DeliveryInfo) -> bool:
        return self._norm_status_text(getattr(delivery, "status", "")) in {"teslim edildi", "tamamlandi"}

    def _delivery_is_preparing(self, delivery: DeliveryInfo) -> bool:
        return self._norm_status_text(getattr(delivery, "status", "")) == "teslimata hazirlaniyor"

    def _derive_system_status(self, sys_info: SystemInfo, deliveries: List[DeliveryInfo]) -> str:
        if not deliveries:
            return "Başlanmadı"
        component_qty = {name: max(as_number(qty), 0) for name, qty in (sys_info.components or {}).items()}
        delivered_qty = {name: sum(max(as_number((delivery.delivered or {}).get(name, 0)), 0) for delivery in deliveries) for name in component_qty}
        active_components = [name for name, qty in component_qty.items() if qty > 0.0001]
        if active_components and all(delivered_qty.get(name, 0) >= component_qty[name] - 0.0001 for name in active_components):
            return "Teslim Edildi"
        if any(qty > 0.0001 for qty in delivered_qty.values()):
            return "Parçalı Teslimat"
        if any(self._delivery_is_preparing(d) for d in deliveries):
            return "Teslimata Hazırlanıyor"
        return "Başlanmadı"

    def _latest_acceptance_date(self, items: List[object]) -> str:
        latest = None
        for item in items:
            parsed = parse_iso_date(str(getattr(item, "acceptance_date", "") or ""))
            if parsed and (latest is None or parsed > latest):
                latest = parsed
        return latest.isoformat() if latest else ""

    def _system_acceptance_date(self, sys_info: SystemInfo, sys_deliveries: List[DeliveryInfo]) -> str:
        if self._norm_status_text(getattr(sys_info, "status", "")) != "teslim edildi":
            return ""
        return self._latest_acceptance_date(sys_deliveries)

    def _contract_acceptance_date(self, systems: List[SystemInfo]) -> str:
        if not systems:
            return ""
        completed = [
            sys_info for sys_info in systems
            if self._norm_status_text(getattr(sys_info, "status", "")) in {"teslim edildi", "tamamlandi"}
        ]
        if len(completed) != len(systems):
            return ""
        return self._latest_acceptance_date(completed)

    def _apply_derived_statuses(self, ci: ContractInfo, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]):
        for sys_info in systems:
            sys_deliveries = list(deliveries.get(sys_info.name, []) or [])
            sys_info.status = self._derive_system_status(sys_info, sys_deliveries)
            sys_info.acceptance_date = self._system_acceptance_date(sys_info, sys_deliveries)

        ci.acceptance_date = self._contract_acceptance_date(systems)

        system_statuses = [self._norm_status_text(getattr(sys_info, "status", "")) for sys_info in systems]
        if not system_statuses or all(st == "baslanmadi" for st in system_statuses):
            ci.status = "Başlanmadı"
        elif all(st in {"teslim edildi", "tamamlandi"} for st in system_statuses):
            ci.status = "Tamamlandı"
        else:
            ci.status = "Devam ediyor"

    def _prepare_context_for_save(self, ctx: dict) -> Tuple[bool, str]:
        ci = ctx.get("ci")
        systems = ctx.get("systems") or []
        deliveries = ctx.get("deliveries") or {}
        if not ci:
            return False, "Sözleşme bilgisi eksik."
        if not systems:
            self._apply_derived_statuses(ci, systems, deliveries)
            ctx["deliveries"] = deliveries
            ctx["systems"] = systems
            return True, ""
        created_defaults = []
        deleted_delivery_systems = set(ctx.get("deleted_delivery_systems") or set())
        for sys_info in systems:
            if self._system_has_component_quantity(sys_info) and not deliveries.get(sys_info.name) and sys_info.name not in deleted_delivery_systems:
                d = self._default_acceptance_for(sys_info)
                if d:
                    deliveries.setdefault(sys_info.name, []).append(d)
                    created_defaults.append(sys_info.name)
        if created_defaults:
            ctx["deliveries"] = deliveries
            ctx["systems"] = systems
            ctx["_created_default_systems"] = created_defaults
            return False, (
                f"{ci.contract_type}: otomatik Teslimat 1 ekranda oluşturuldu. "
                "Lütfen açılan teslimat ekranını kontrol edip onaylayın; ardından tekrar Kaydet'e basın."
            )
        issues = self._acceptance_coverage_issues(systems, deliveries)
        if issues:
            title, message = self._acceptance_validation_message(issues)
            ctx["_acceptance_validation_title"] = title
            ctx["_acceptance_validation_issues"] = issues
            return False, f"{ci.contract_type}: {message}"
        self._apply_derived_statuses(ci, systems, deliveries)
        ctx["deliveries"] = deliveries
        ctx["systems"] = systems
        return True, ""

    def _save_context_family(self) -> bool:
        self._cache_current_context()
        family = self._family_context_rows()
        keys = []
        for it in family:
            key = tuple(it.get("_cache_key") or (it.get("platform"), it.get("no"), it.get("type")))
            if key in self._context_cache and key not in keys:
                keys.append(key)
        if not keys:
            return False
        keys.sort(key=lambda k: (1 if self._is_sd_type(k[2]) else 0, self._sd_sort_key(k[2])))
        for key in keys:
            ok, msg = self._prepare_context_for_save(self._context_cache[key])
            if not ok:
                ctx = self._context_cache[key]
                created_defaults = list(ctx.pop("_created_default_systems", []) or [])
                validation_title = str(ctx.pop("_acceptance_validation_title", "") or "")
                validation_issues = list(ctx.pop("_acceptance_validation_issues", []) or [])
                self._load_cached_context(key)
                if created_defaults:
                    self.selected_system = created_defaults[0]
                elif validation_issues:
                    self._focus_acceptance_issue(validation_issues)
                self.expanded_delivery_index = None
                self.refresh_contract_header()
                self.render_contract_tags()
                self.refresh()
                QMessageBox.information(
                    self,
                    "Teslimat oluşturuldu" if created_defaults else (validation_title or "Eksik"),
                    msg,
                )
                if created_defaults:
                    QTimer.singleShot(0, lambda name=created_defaults[0]: self._open_first_delivery_for_system(name))
                return True
        main_start = 0
        main_end = 0
        actor = self.store.current_actor()
        with self.store.batch_save():
            for key in keys:
                ctx = self._context_cache[key]
                ci = ctx["ci"]
                if self._is_sd_type(ci.contract_type) and main_start:
                    ci.sd_anchor_start_row = main_start
                    ci.sd_anchor_end_row = main_end or main_start
                    ci.sd_anchor_platform = ci.platform
                    ci.sd_anchor_no = ci.no
                written_start = self.store.write_contract(
                    ci,
                    ctx.get("systems") or [],
                    ctx.get("deliveries") or {},
                    old_contract_no=ctx.get("original_contract_no") or ci.no,
                    old_start_row=ctx.get("original_entry_start_row") or 0,
                )
                ci.entry_start_row = int(written_start or 0)
                if not self._is_sd_type(ci.contract_type):
                    try:
                        info = self.store.find_main_contract_info(ci.platform, ci.no)
                        main_start = int((info or {}).get("block_start") or written_start or 0)
                        main_end = int((info or {}).get("block_end") or main_start or 0)
                    except Exception:
                        main_start = int(written_start or 0)
                        main_end = main_start
                old_key = (
                    str(ctx.get("original_platform") or "").strip(),
                    str(ctx.get("original_contract_no") or "").strip(),
                    str(ctx.get("original_contract_type") or "").strip(),
                )
                new_key = (str(ci.platform or "").strip(), str(ci.no or "").strip(), str(ci.contract_type or "").strip())
                if old_key != new_key and all(old_key):
                    self.store.save_contract_tags(old_key[0], old_key[1], old_key[2], [], actor=actor)
                self.store.save_contract_tags(new_key[0], new_key[1], new_key[2], ctx.get("tags") or [], actor=actor)
                ctx["original_platform"] = new_key[0]
                ctx["original_contract_no"] = new_key[1]
                ctx["original_contract_type"] = new_key[2]
                ctx["original_entry_start_row"] = int(written_start or 0)
        current_key = self._context_key()
        if current_key in self._context_cache:
            self._load_cached_context(current_key)
        QMessageBox.information(self, "Kaydedildi", "Ana sözleşme ve bağlı SD kayıtları kaydedildi.")
        self._is_dirty = False
        self.accept()
        return True

    def _system_status_kind(self, status: str) -> str:
        norm = self._norm_status_text(status)
        if norm in {"teslim edildi", "tamamlandi"}:
            return "done"
        if norm in {"teslimata hazirlaniyor", "parcali teslimat"}:
            return "progress"
        return "notstarted"

    def _make_system_item_widget(self, sys_info: SystemInfo, selected: bool = False) -> QWidget:
        status = str(getattr(sys_info, "status", "") or "Başlanmadı")
        kind = self._system_status_kind(status)

        card = QFrame()
        card.setObjectName("systemListCard")
        card.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        name = QLabel(str(sys_info.name or "Sistem"))
        name.setObjectName("systemItemName")
        name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name.setMinimumWidth(0)
        name.setWordWrap(False)

        # Seçili değilse siyah, seçiliyse beyaz.
        name.setStyleSheet(
            "background: transparent; color: #FFFFFF; font-weight: 900; font-size: 12px;"
            if selected else
            "background: transparent; color: #0f172a; font-weight: 900; font-size: 12px;"
        )

        pill = QLabel(status)
        pill.setObjectName("systemStatusPill")
        pill.setProperty("kind", kind)
        pill.setAlignment(Qt.AlignCenter)
        pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pill.setMinimumWidth(108)
        pill.setMaximumWidth(138)
        pill.setFixedHeight(22)
        pill.setWordWrap(False)

        row.addWidget(name, 1)
        row.addWidget(pill, 0, Qt.AlignRight | Qt.AlignVCenter)
        lay.addLayout(row)

        return card

    def _populate_system_list(self, keep_row: Optional[int] = None):
        current = self.system_list.currentRow() if keep_row is None else keep_row

        target = 0
        if self.systems:
            target = max(0, min(current, len(self.systems) - 1))
            if self.selected_system:
                for idx, sys_info in enumerate(self.systems):
                    if sys_info.name == self.selected_system:
                        target = idx
                        break

        self.system_list.blockSignals(True)
        self.system_list.clear()

        for idx, sys_info in enumerate(self.systems):
            item = self._make_system_list_item(sys_info)
            item.setSizeHint(QSize(0, 58))
            self.system_list.addItem(item)

            is_selected = idx == target
            self.system_list.setItemWidget(
                item,
                self._make_system_item_widget(sys_info, selected=is_selected)
            )

        if self.systems:
            self.system_list.setCurrentRow(target)

        self.system_list.blockSignals(False)

    def refresh_live_statuses(self):
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self.refresh_contract_header()
        self._populate_system_list()

    def _make_system_list_item(self, sys_info: SystemInfo) -> QListWidgetItem:
        status = str(getattr(sys_info, "status", "") or "Başlanmadı")
        item = QListWidgetItem()
        item.setData(Qt.UserRole, status)
        return item

    def refresh(self):
        self.refresh_sd_sidebar()
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        self.refresh_contract_header()
        self._populate_system_list()
        self.refresh_right()
        if hasattr(self, 'update_timeline_bar'):
            self.update_timeline_bar()

    def _component_display_keys(self, sys_info: Optional[SystemInfo]) -> List[str]:
        """Sistemin tum secili bilesenleri dondur.
        excel_store artik sadece qty > 0 bilesenleri yukledigi icin
        sys_info.components'ta ne varsa kullanici secmis veya deger girmistir.
        qty=0 olsa bile (yeni eklenmis bilesenler) goster ki kullanici deger girebilsin.
        """
        if not sys_info:
            return []
        return component_display_keys(sys_info)

    def sync_summary_to_system(self):
        sys_info = self.current_system()
        if not sys_info:
            return
        for r in range(self.summary.rowCount()):
            comp_item = self.summary.item(r, 0)
            qty_item = self.summary.item(r, 1)
            if not comp_item or not qty_item:
                continue
            comp = comp_item.text()
            sys_info.components[comp] = as_number(qty_item.text())
            note_item = self.summary.item(r, 4)
            note = note_item.text() if note_item else ""
            if not hasattr(sys_info, "component_notes"):
                sys_info.component_notes = {}
            if note:
                sys_info.component_notes[comp] = note
            else:
                sys_info.component_notes.pop(comp, None)

    def on_summary_changed(self, item):
        if self._updating_summary or item.column() not in (1, 4):
            return
        self._set_dirty()
        self.sync_summary_to_system()
        if item.column() == 1:
            self.refresh_system_card_text()
            self.refresh_summary_only()

    def refresh_system_card_text(self):
        r = self.system_list.currentRow()
        if 0 <= r < len(self.systems):
            s = self.systems[r]
            self._populate_system_list(keep_row=r)

    def _parse_iso_date(self, text: str):
        return parse_iso_date(text)

    def _fmt_num(self, v):
        return fmt_num(v)

    def _as_number(self, v):
        return as_number(v)

    def _configure_table(self, table, compact: bool = False):
        return configure_table(table, compact=compact)

    @property
    def _DeliveryDialog(self):
        return DeliveryDialog

    def _show_warning(self, title: str, text: str):
        return QMessageBox.warning(self, title, text)

    def refresh_summary_only(self):
        from src.ui.contract import work_window_view as cw_view
        cw_view.refresh_summary_only(self)

    def update_system_metric_cards(self, sys_info: Optional[SystemInfo]):
        from src.ui.contract import work_window_view as cw_view
        cw_view.update_system_metric_cards(self, sys_info)

    def refresh_right(self):
        from src.ui.contract import work_window_view as cw_view
        cw_view.refresh_right(self)

    def refresh_delivery_table(self):
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.refresh_delivery_table(self)

    def update_pinned_delivery(self, d: Optional[DeliveryInfo], headers: List[str], comps: List[str]):
        self.pinned_delivery.clear()
        self.pinned_delivery.setColumnCount(len(headers))
        self.pinned_delivery.setHorizontalHeaderLabels(headers)
        if d:
            self.pinned_delivery.setRowCount(1)
            vals = ["▼", d.name, d.status, d.acceptance_date] + [d.planned.get(c, 0) for c in comps]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(fmt_num(v) if isinstance(v, (int, float)) else str(v))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if c == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.pinned_delivery.setItem(0, c, it)
        else:
            self.pinned_delivery.setRowCount(0)
        self.pinned_delivery.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self.pinned_delivery.columnCount() > 0:
            self.pinned_delivery.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.pinned_delivery.setColumnWidth(0, 44)

        header_h = self.pinned_delivery.horizontalHeader().height()
        row_h = self.pinned_delivery.rowHeight(0) if self.pinned_delivery.rowCount() else 0
        frame = 2 * self.pinned_delivery.frameWidth()
        total_h = header_h + row_h + frame + (2 if row_h else 0)
        self.pinned_delivery.setMinimumHeight(total_h)
        self.pinned_delivery.setMaximumHeight(total_h)

    def delivery_detail_widget(self, d: DeliveryInfo, comps: List[str], idx: int) -> QWidget:
        from src.ui.contract import work_window_deliveries as cw_deliveries
        return cw_deliveries.delivery_detail_widget(self, d, comps, idx)

    def edit_delivery(self, idx: int):
        from src.ui.contract import work_window_deliveries as cw_deliveries
        cw_deliveries.edit_delivery(self, idx)

    def on_delivery_clicked(self, row, col):
        if col != 0 or row not in self._delivery_row_map:
            return
        idx = self._delivery_row_map[row]
        self.edit_delivery(idx)

    def on_pinned_delivery_clicked(self, row, col):
        pass  # pinned panel kaldirildi

    def _system_has_component_quantity(self, sys_info: SystemInfo) -> bool:
        return any(as_number(v) > 0.0001 for v in (sys_info.components or {}).values())

    def _create_default_acceptance_for_system(self, sys_info: SystemInfo):
        d = self._default_acceptance_for(sys_info)
        if d:
            self.deliveries.setdefault(sys_info.name, []).append(d)
            self._deleted_delivery_systems.discard(sys_info.name)
            self._set_dirty()

    def _open_first_delivery_for_system(self, system_name: str):
        if not system_name:
            return
        self.selected_system = system_name
        self._populate_system_list()
        for idx, sys_info in enumerate(self.systems):
            if sys_info.name == system_name:
                self.system_list.setCurrentRow(idx)
                break
        self.refresh_right()
        if self.deliveries.get(system_name):
            self.edit_delivery(0)

    def _acceptance_coverage_issues(self, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]) -> List[dict]:
        return acceptance_coverage_issues(systems, deliveries)

    def _acceptance_validation_message(self, issues: List[dict]) -> Tuple[str, str]:
        unassigned = [issue for issue in issues if issue.get("kind") == "unassigned"]
        over_delivered = [issue for issue in issues if issue.get("kind") == "over_delivered"]
        delivery_over_planned = [issue for issue in issues if issue.get("kind") == "delivery_over_planned"]
        over_assigned = [issue for issue in issues if issue.get("kind") == "over_assigned"]
        if over_delivered:
            title = "Teslim edilen miktar sözleşme adedini aşıyor"
            intro = "Bazı bileşenlerde teslim edilen miktar sözleşme adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['component']}: sözleşme {fmt_num(issue['contract_qty'])}, teslim edilen {fmt_num(issue['delivered_qty'])}" for issue in over_delivered]
        elif delivery_over_planned:
            title = "Teslim edilen miktar teslimat adedini aşıyor"
            intro = "Bazı teslimatlarda teslim edilen miktar teslimat adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['delivery']} / {issue['component']}: teslimat {fmt_num(issue['planned_qty'])}, teslim edilen {fmt_num(issue['delivered_qty'])}" for issue in delivery_over_planned]
        elif over_assigned:
            title = "Teslimat miktarı sistem adedini aşıyor"
            intro = "Bazı bileşenlerde teslimatlara atanan miktar sistem adedini aşıyor. Kaydetmeden önce miktarları düzeltin."
            details = [f"• {issue['system']} / {issue['component']}: sistem {fmt_num(issue['contract_qty'])}, teslimatlar {fmt_num(issue['planned_qty'])}" for issue in over_assigned]
        else:
            title = "Atanmamış bileşenler var"
            intro = "Bu sözleşmede teslimata atanmamış bileşenler bulunuyor. Kaydetmeden önce kalan bileşenleri bir teslimata atayın."
            details = [f"• {issue['system']} / {issue['component']}: {fmt_num(issue['qty'])} adet atanmadı" for issue in unassigned]
        shown = details[:10]
        if len(details) > len(shown):
            shown.append(f"... ve {len(details) - len(shown)} kalem daha")
        return title, intro + "\n\n" + "\n".join(shown)

    def _focus_acceptance_issue(self, issues: List[dict]):
        if not issues:
            return
        system_name = str(issues[0].get("system") or "")
        if not system_name:
            return
        self.selected_system = system_name
        self._populate_system_list()
        for index, sys_info in enumerate(self.systems):
            if sys_info.name == system_name:
                self.system_list.setCurrentRow(index)
                break
        self.refresh_right()

    def _validate_acceptance_totals(self, systems: List[SystemInfo], deliveries: Dict[str, List[DeliveryInfo]]) -> List[str]:
        errors = []
        for sys_info in systems:
            sys_deliveries = deliveries.get(sys_info.name, []) or []
            components = self._component_display_keys(sys_info)
            for comp in components:
                total = max(as_number((sys_info.components or {}).get(comp, 0)), 0)
                planned_sum = sum(max(as_number((d.planned or {}).get(comp, 0)), 0) for d in sys_deliveries)
                delivered_sum = sum(max(as_number((d.delivered or {}).get(comp, 0)), 0) for d in sys_deliveries)
                if planned_sum - total > 0.0001:
                    errors.append(f"{sys_info.name} / {comp}: sistem {fmt_num(total)}, teslimatlar {fmt_num(planned_sum)}")
                if delivered_sum - planned_sum > 0.0001:
                    errors.append(f"{sys_info.name} / {comp}: teslim edilen {fmt_num(delivered_sum)}, teslimat adedi {fmt_num(planned_sum)}")
            for delivery in sys_deliveries:
                for comp, qty in (delivery.delivered or {}).items():
                    planned_qty = max(as_number((delivery.planned or {}).get(comp, 0)), 0)
                    delivered_qty = max(as_number(qty), 0)
                    if delivered_qty - planned_qty > 0.0001:
                        errors.append(f"{sys_info.name} / {delivery.name} / {comp}: teslim edilen, teslimat adedini aşıyor")
        return errors

    def ensure_systems_have_acceptances(self) -> bool:
        missing_systems = [
            sys_info for sys_info in self.systems
            if self._system_has_component_quantity(sys_info)
            and not self.deliveries.get(sys_info.name)
            and sys_info.name not in self._deleted_delivery_systems
        ]
        if not missing_systems:
            return True

        names = "\n".join(f"• {sys_info.name}" for sys_info in missing_systems)
        if not ask_yes_no(
            self,
            "Teslimat eklenmemiş sistem var",
            "Aşağıdaki sistemlere teslimat eklemediniz:\n\n"
            f"{names}\n\n"
            "Onaylarsanız bu sistemlerin içine Teslimat 1 otomatik oluşturulacak ve "
            "sistemdeki tüm bileşen adetleri Teslimat 1'e atanacaktır.\n\n"
            "Onaylamazsanız teslimat eklemeden kaydetmeye izin verilmeyecektir.",
            default_yes=True,
        ):
            QMessageBox.warning(
                self,
                "Teslimat gerekli",
                "Teslimat eklenmemiş sistemler için teslimat oluşturmadan kaydetme yapılamaz.",
            )
            return False

        first_missing_name = missing_systems[0].name
        for sys_info in missing_systems:
            self._create_default_acceptance_for_system(sys_info)
        self.expanded_delivery_index = None
        if first_missing_name:
            self.selected_system = first_missing_name
        self._populate_system_list()
        self.refresh_right()
        QMessageBox.information(
            self,
            "Teslimat oluşturuldu",
            "Otomatik Teslimat 1 kayıtları ekranda oluşturuldu. "
            "Lütfen açılan teslimat ekranını kontrol edip onaylayın; ardından tekrar Kaydet'e basın.",
        )
        QTimer.singleShot(0, lambda name=first_missing_name: self._open_first_delivery_for_system(name))
        return False

    def reject(self) -> None:
        """Kapat butonuna basıldığında değişiklik varsa onay ister."""
        current_key = self._context_key() if hasattr(self, "_context_cache") else ("", "", "")
        if self._is_dirty:
            if not ask_yes_no(
                self,
                "Değişiklikler Kaydedilmedi",
                "Yaptığınız değişiklikler kaydedilmeyecektir.\n\n"
                "Onaylıyor musunuz?",
            ):
                return
        if hasattr(self, "_context_cache") and current_key in self._context_cache:
            ctx = self._context_cache.get(current_key) or {}
            ci = ctx.get("ci")
            if int(getattr(ci, "entry_start_row", 0) or ctx.get("original_entry_start_row") or 0) <= 0:
                self._context_cache.pop(current_key, None)
        super().reject()

    def save_all(self):
        if not self._ensure_share_can_edit("Sözleşme Kaydet"):
            return
        required_permission = "create_contracts" if self.is_new_contract else "edit_contracts"
        if not self.require_permission_ui(required_permission, "Sözleşme Kaydet"):
            return
        # Belgeler/klasörler STS veritabanına anında yazılır. Bu durumda Kaydet'e
        # basıldığında "Değişiklik Yok" uyarısı gösterme; pencereyi normal kapat.
        if not self._is_dirty and not self.is_new_contract:
            if self._documents_changed:
                self._finish_persisted_side_meta_only_save()
                return
            self.accept()
            return

        if self._save_context_family():
            return
        if not self.systems:
            QMessageBox.warning(self, "Eksik", "En az bir sistem ekleyin.")
            return
        self.sync_summary_to_system()
        if not self.ensure_systems_have_acceptances():
            return
        issues = self._acceptance_coverage_issues(self.systems, self.deliveries)
        if issues:
            title, message = self._acceptance_validation_message(issues)
            self._focus_acceptance_issue(issues)
            QMessageBox.warning(self, title, message)
            return
        self._apply_derived_statuses(self.ci, self.systems, self.deliveries)
        # ── Değişiklik tespiti ──────────────────────────────────────────────
        if not self.is_new_contract:
            if self._make_data_snapshot() == self._initial_snapshot:
                if self._documents_changed:
                    self._finish_persisted_side_meta_only_save()
                    return
                self.accept()
                return
        # ───────────────────────────────────────────────────────────────────
        old_key = (
            str(self.original_platform or "").strip(),
            str(self.original_contract_no or "").strip(),
            str(self.original_contract_type or "").strip(),
        )
        new_key = (
            str(self.ci.platform or "").strip(),
            str(self.ci.no or "").strip(),
            str(self.ci.contract_type or "").strip(),
        )
        actor = self.store.current_actor()
        self._pending_contract_save_context = {
            "old_key": old_key,
            "new_key": new_key,
            "actor": actor,
            "tags": [dict(t or {}) for t in self.contract_tags],
        }
        worker = ContractSaveWorker(
            self.store.path,
            "write",
            str(self.ci.platform or ""),
            str(self.ci.no or ""),
            ci=copy.deepcopy(self.ci),
            systems=copy.deepcopy(self.systems),
            deliveries=copy.deepcopy(self.deliveries),
            old_contract_no=self.original_contract_no,
            old_start_row=self.original_entry_start_row,
            actor=actor,
            store=self.store,
        )
        self._start_contract_save_worker(worker, "Sözleşme kaydediliyor...")
