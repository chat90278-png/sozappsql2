from __future__ import annotations

import unicodedata
from typing import Dict, List, Optional, Protocol, Tuple

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from src.models.app_models import TagDef
from src.services.excel_store import ExcelStore
from src.services.sts_store import STSStore
from src.ui.delegates import DropdownDelegate
from src.ui.theme import STYLE
from src.ui.toast import ToastNotification


EXCEL_DATA_SOURCE_DISABLED_MESSAGE = (
    "Excel dosyaları artık veri kaynağı olarak açılamaz. Lütfen .sts dosyası seçin. "
    "Excel yalnızca rapor/export çıktısı olarak kullanılmaktadır."
)


def normalized_tag_key(value: str) -> str:
    """Return a stable comparison key for tag names, including Turkish case variants."""
    text = str(value or "").strip().replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def form_label(txt):
    l = QLabel(txt)
    l.setObjectName("formLabel")
    return l


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


def _is_sts_store(store) -> bool:
    return bool(
        store is not None
        and hasattr(store, "db")
        and hasattr(store, "write_users")
        and hasattr(store, "write_components")
    )


class SystemTypeStore(Protocol):
    """System dialogs depend on this store API in both ExcelStore and STSStore modes."""

    def assigned_components(self, platform: str) -> List[str]: ...
    def list_system_type_names(self, platform: str = "") -> List[str]: ...
    def get_system_type_components(self, type_name: str, platform: str = "") -> List[str]: ...
    def get_system_type_component_quantities(self, type_name: str, platform: str = "") -> Dict[str, float]: ...
    def save_system_type(self, type_name: str, platform: str, components) -> int: ...


class StyledDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(STYLE)

    def make_footer_status_label(self) -> QLabel:
        label = QLabel("")
        label.setObjectName("footerStatus")
        label.setMinimumWidth(0)
        label.setMinimumHeight(34)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.hide()
        return label

    def show_footer_status(self, message: str, kind: str = "success", duration: int = 2600):
        label = getattr(self, "footer_status", None)
        if label is None:
            ToastNotification.show_in(self, message, kind=kind, duration=duration)
            return

        colors = {
            "success": ("#166534", "#dcfce7", "#16a34a"),
            "error": ("#991b1b", "#fee2e2", "#dc2626"),
            "info": ("#1e3a8a", "#dbeafe", "#2563eb"),
        }
        icons = {"success": "\u2713", "error": "\u2715", "info": "i"}
        fg, bg, border = colors.get(kind, colors["success"])
        text = str(message or "")
        visible_text = text if len(text) <= 96 else f"{text[:93]}..."
        label.setText(f"{icons.get(kind, 'i')}  {visible_text}")
        label.setToolTip(text)
        label.setStyleSheet(
            f"color:{fg};background-color:{bg};border:1px solid {border};"
            "border-radius:7px;padding:6px 10px;font-size:12px;font-weight:700;"
        )
        label.show()

        token = getattr(self, "_footer_status_token", 0) + 1
        self._footer_status_token = token
        QTimer.singleShot(duration, lambda: self.clear_footer_status(token))

    def clear_footer_status(self, token: Optional[int] = None):
        if token is not None and token != getattr(self, "_footer_status_token", None):
            return
        label = getattr(self, "footer_status", None)
        if label is not None:
            label.hide()


class UserManagerDialog(StyledDialog):
    def __init__(self, store: ExcelStore, parent=None):
        super().__init__("Kullanıcı Yönetimi", parent)
        self.store = store
        self.users = store.load_users(active_only=False)
        self.changed = False
        self._save_thread: Optional[QThread] = None
        self._save_worker = None
        self._save_payload: List[dict] = []
        self._saving = False
        self._busy_cursor_on = False
        self.resize(760, 500)
        self.build()
        self.load_table()

    def build(self):
        root = QVBoxLayout(self)
        title = QLabel("Kullanıcı Yönetimi")
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        desc = QLabel("Sözleşme girişinde seçilecek kullanıcıları burada tanımlayın. Aktif olmayanlar yeni sözleşme ekranında görünmez.")
        desc.setObjectName("muted")
        root.addWidget(desc)

        btns = QHBoxLayout()
        add = QPushButton("+ Kullanıcı Ekle")
        add.clicked.connect(self.add_user)
        delete = QPushButton("Seçili Kullanıcıyı Sil")
        delete.setObjectName("danger")
        delete.clicked.connect(self.delete_selected)
        btns.addWidget(add)
        btns.addWidget(delete)
        btns.addStretch()
        root.addLayout(btns)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Kullanıcı Adı", "Yİ/YD", "Aktif", "Not"])
        root.addWidget(self.table, 1)

        foot = QHBoxLayout()
        self.footer_status = self.make_footer_status_label()
        foot.addWidget(self.footer_status, 1, Qt.AlignVCenter)
        foot.addStretch()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self.save)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.setObjectName("secondary")
        self.close_btn.clicked.connect(self.reject)
        foot.addWidget(self.save_btn)
        foot.addWidget(self.close_btn)
        root.addLayout(foot)

        self.busy_overlay = QFrame(self)
        self.busy_overlay.setStyleSheet("QFrame { background: rgba(248, 251, 255, 0.86); }")
        self.busy_overlay.hide()
        self.busy_card = QFrame(self.busy_overlay)
        self.busy_card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.97); border: 1px solid #d8e2ed; border-radius: 10px; }"
        )
        bl = QVBoxLayout(self.busy_card)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(8)
        self.busy_label = QLabel("İşlem yapılıyor...")
        self.busy_label.setObjectName("mainTitle")
        self.busy_label.setAlignment(Qt.AlignCenter)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setTextVisible(True)
        self.busy_progress.setFormat("%p%")
        bl.addWidget(self.busy_label)
        bl.addWidget(self.busy_progress)
        self.position_busy_overlay()

    def load_table(self):
        self.table.setRowCount(len(self.users))
        for r, u in enumerate(self.users):
            vals = [u.get("name", ""), u.get("yi_yd", "Yİ"), "Evet" if u.get("active", True) else "Hayır", u.get("note", "")]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Sütun 1: Yİ / YD dropdown
        self.table.setItemDelegateForColumn(1, DropdownDelegate(["Yİ", "YD"], self.table))
        # Sütun 2: Evet / Hayır dropdown
        self.table.setItemDelegateForColumn(2, DropdownDelegate(["Evet", "Hayır"], self.table))

    def position_busy_overlay(self):
        if not hasattr(self, "busy_overlay"):
            return
        self.busy_overlay.setGeometry(self.rect())
        w, h = 420, 130
        x = max((self.busy_overlay.width() - w) // 2, 0)
        y = max((self.busy_overlay.height() - h) // 2, 0)
        self.busy_card.setGeometry(x, y, w, h)
        self.busy_overlay.raise_()

    def set_busy(self, visible: bool, message: str = "İşlem yapılıyor...", percent: int = 0):
        if not hasattr(self, "busy_overlay"):
            return
        self._saving = bool(visible)
        if visible:
            self.busy_label.setText(str(message or "İşlem yapılıyor..."))
            self.busy_progress.setValue(int(max(0, min(100, percent))))
            self.position_busy_overlay()
            self.save_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.table.setEnabled(False)
            if hasattr(self, "frozen_table"): self.frozen_table.setEnabled(False)
            self.busy_overlay.show()
            if not self._busy_cursor_on:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                self._busy_cursor_on = True
            QApplication.processEvents()
        else:
            self.busy_overlay.hide()
            self.save_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            self.table.setEnabled(True)
            if hasattr(self, "frozen_table"): self.frozen_table.setEnabled(True)
            if self._busy_cursor_on:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_on = False
            QApplication.processEvents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()

    def closeEvent(self, event):
        if self._saving:
            event.ignore()
            return
        super().closeEvent(event)

    def _sync_table_to_users(self):
        """Tablodaki hücre değerlerini self.users listesine yansıt."""
        for r in range(min(self.table.rowCount(), len(self.users))):
            u = self.users[r]
            if self.table.item(r, 0):
                u["name"] = self.table.item(r, 0).text().strip() or u.get("name", "")
            if self.table.item(r, 1):
                u["yi_yd"] = self.table.item(r, 1).text().strip() or "Yİ"
            if self.table.item(r, 2):
                u["active"] = self.table.item(r, 2).text().strip().lower() in ["evet", "true", "1", "aktif"]
            if self.table.item(r, 3):
                u["note"] = self.table.item(r, 3).text().strip()

    def add_user(self):
        self._sync_table_to_users()   # ← önce mevcut değerleri koru
        self.users.append({"name": "Yeni Kullanıcı", "yi_yd": "Yİ", "active": True, "note": ""})
        self.load_table()
        last = self.table.rowCount() - 1
        self.table.setCurrentCell(last, 0)
        self.table.editItem(self.table.item(last, 0))

    def delete_selected(self):
        r = self.table.currentRow()
        if r >= 0:
            self._sync_table_to_users()   # ← önce mevcut değerleri koru
            self.users.pop(r)
            self.load_table()

    def save(self):
        result = []
        seen = set()
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not name:
                continue
            if name.lower() in seen:
                QMessageBox.warning(self, "Uyarı", f"Tekrarlanan kullanıcı: {name}")
                return
            seen.add(name.lower())
            yi_yd_txt = (self.table.item(r, 1).text() if self.table.item(r, 1) else "Yİ").strip().upper()
            yi_yd = "YD" if yi_yd_txt == "YD" else "Yİ"
            active_txt = (self.table.item(r, 2).text() if self.table.item(r, 2) else "Evet").strip().lower()
            result.append({
                "name": name,
                "yi_yd": yi_yd,
                "active": active_txt in ["evet", "true", "1", "aktif", "yes"],
                "note": (self.table.item(r, 3).text() if self.table.item(r, 3) else ""),
            })
        self._save_payload = list(result)
        if _is_sts_store(self.store):
            try:
                self.set_busy(True, "Kullanıcılar kaydediliyor...", 25)
                self.store.write_users(self._save_payload, actor=self.store.current_actor())
                self.store.save()
                self.on_save_finished()
            except Exception as exc:
                self.on_save_failed(str(exc))
            return
        self._start_async_save()

    def _start_async_save(self):
        QMessageBox.warning(self, "STS dosyası gerekli", EXCEL_DATA_SOURCE_DISABLED_MESSAGE)
        self._clear_save_refs()

    def _clear_save_refs(self):
        self._save_worker = None
        self._save_thread = None

    def on_save_progress(self, percent: int, message: str):
        self.set_busy(True, str(message or "İşlem yapılıyor..."), int(max(0, min(100, int(percent or 0)))))

    def on_save_finished(self):
        try:
            self.set_busy(True, "Yerel önbellek yenileniyor...", 98)
            self.store.reload_from_disk()
            self.users = self.store.load_users(active_only=False)
            self.changed = True
            self.set_busy(False)
            self.show_footer_status("Kullanıcılar kaydedildi", kind="success")
        except Exception as exc:
            self.set_busy(False)
            self.show_footer_status(f"Yenileme hatası: {exc}", kind="error", duration=4000)

    def on_save_failed(self, error_text: str):
        self.set_busy(False)
        self.show_footer_status("Kaydetme hatası! Detay için loga bakın.", kind="error", duration=4000)
        QMessageBox.critical(self, "Kullanıcı kaydetme hatası", f"Kaydetme sırasında hata oluştu:\n\n{error_text}")


class TagAssignDialog(StyledDialog):
    def __init__(self, store: ExcelStore, already_assigned: Optional[List[dict]] = None, parent=None):
        super().__init__("Etiket Ekle", parent)
        self.store = store
        self.all_tags = list(store.load_tag_defs(active_only=True))
        self.already_keys = {
            self._tag_key(str((t or {}).get("name") or ""))
            for t in list(already_assigned or [])
            if str((t or {}).get("name") or "").strip()
        }
        self.available_tags = [tag for tag in self.all_tags if self._tag_key(tag.name) not in self.already_keys]
        self.selected: Dict[str, TagDef] = {}
        self.result: List[dict] = []
        self.save_btn: Optional[QPushButton] = None
        self.resize(520, 380)
        self.build()

    def _tag_key(self, name: str) -> str:
        return normalized_tag_key(name)

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        title = QLabel("Etiket Ekle")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        root.addWidget(form_label("Etiket Seç"))
        self.tags_wrap = QFrame()
        self.tags_wrap.setObjectName("tagPanel")
        tags_lay = QGridLayout(self.tags_wrap)
        tags_lay.setContentsMargins(10, 10, 10, 10)
        tags_lay.setHorizontalSpacing(8)
        tags_lay.setVerticalSpacing(8)
        if not self.all_tags:
            warn = QLabel("Aktif etiket yok. Önce Etiket Yönetimi ekranından etiket oluşturun.")
            warn.setObjectName("warning")
            warn.setWordWrap(True)
            tags_lay.addWidget(warn, 0, 0, 1, 3)
        elif not self.available_tags:
            empty = QLabel("Atanabilecek etiket bulunmuyor.")
            empty.setObjectName("warning")
            empty.setWordWrap(True)
            tags_lay.addWidget(empty, 0, 0, 1, 3)
        else:
            for i, t in enumerate(self.available_tags):
                b = QPushButton(f"● {t.name}")
                b.setCheckable(True)
                b.setObjectName("tagChipBtn")
                b.setStyleSheet(tag_chip_style(t.color, selected=False))
                b.clicked.connect(lambda checked, tag=t, btn=b: self.toggle_tag(tag, btn, checked))
                tags_lay.addWidget(b, i // 3, i % 3)
        root.addWidget(self.tags_wrap)

        root.addWidget(form_label("Sözleşmeye Özel Not (Opsiyonel)"))
        self.note = QTextEdit()
        self.note.setPlaceholderText("Bu atama için özel bir not ekleyin...")
        self.note.setMinimumHeight(72)
        root.addWidget(self.note)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Ekle")
        save.setEnabled(False)
        save.clicked.connect(self.save)
        self.save_btn = save
        row.addWidget(cancel)
        row.addWidget(save)
        root.addLayout(row)

    def toggle_tag(self, tag: TagDef, btn: QPushButton, checked: bool):
        key = self._tag_key(tag.name)
        if checked:
            self.selected[key] = tag
        else:
            self.selected.pop(key, None)
        btn.setStyleSheet(tag_chip_style(tag.color, selected=bool(checked)))
        if self.save_btn is not None:
            self.save_btn.setEnabled(bool(self.selected))

    def save(self):
        if not self.available_tags:
            return
        if not self.selected:
            QMessageBox.warning(self, "Seçim", "En az bir etiket seçin.")
            return
        if self.save_btn is not None:
            self.save_btn.setEnabled(False)
        note = self.note.toPlainText().strip()
        out: List[dict] = []
        for tag in self.selected.values():
            out.append({
                "name": str(tag.name or "").strip(),
                "color": str(tag.color or "#3B82F6"),
                "note": note or str(tag.note or "").strip(),
            })
        self.result = out
        self.accept()

