# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QPushButton, QSizePolicy,
)

class _UserRowWidget(QWidget):
    """Dropdown içindeki tek kullanıcı satırı: avatar + isim + checkbox."""

    toggled = Signal(str, bool)  # (name, is_checked)

    _AVATAR_PALETTES = [
        ("#e8f0fe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#ecfdf5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#e0f2fe", "#075985"),
        ("#d1fae5", "#065f46"),
    ]

    def __init__(self, name: str, palette_index: int, checked: bool = False, parent=None):
        super().__init__(parent)
        self._name = name
        self._checked = checked
        bg, fg = self._AVATAR_PALETTES[palette_index % len(self._AVATAR_PALETTES)]
        self._bg = bg
        self._fg = fg
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(10)

        # Avatar dairesi
        self._avatar = QLabel(self._initials(name))
        self._avatar.setFixedSize(26, 26)
        self._avatar.setAlignment(Qt.AlignCenter)
        self._avatar.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:13px;"
            "font-size:10px;font-weight:700;"
        )
        lay.addWidget(self._avatar)

        # İsim
        self._label = QLabel(name)
        self._label.setStyleSheet("font-size:13px;color:#0f172a;background:transparent;")
        lay.addWidget(self._label, 1)

        # Checkbox kutusu
        self._check = QLabel()
        self._check.setFixedSize(18, 18)
        self._update_check_style()
        lay.addWidget(self._check)

        self._update_bg()

    @staticmethod
    def _initials(name: str) -> str:
        parts = str(name or "").strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper() if name else "?"

    def _update_check_style(self):
        if self._checked:
            self._check.setStyleSheet(
                "background:#2563eb;border-radius:4px;border:1.5px solid #2563eb;"
            )
            self._check.setText("✓")
            self._check.setAlignment(Qt.AlignCenter)
            self._check.setStyleSheet(
                "background:#2563eb;border-radius:4px;border:1.5px solid #2563eb;"
                "color:#0f172a;font-size:11px;font-weight:700;"
            )
        else:
            self._check.setText("")
            self._check.setStyleSheet(
                "background:white;border-radius:4px;border:1.5px solid #cbd5e1;"
            )

    def _update_bg(self):
        if self._checked:
            self.setStyleSheet("QWidget{background:#f0f7ff;}QWidget:hover{background:#e8f3ff;}")
        else:
            self.setStyleSheet("QWidget{background:white;}QWidget:hover{background:#f8fafc;}")

    def set_checked(self, checked: bool):
        self._checked = checked
        self._update_check_style()
        self._update_bg()

    def is_checked(self) -> bool:
        return self._checked

    def name(self) -> str:
        return self._name

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_check_style()
        self._update_bg()
        self.toggled.emit(self._name, self._checked)

    def matches_filter(self, query: str) -> bool:
        return query.lower() in self._name.lower()


class _MultiUserDropdown(QFrame):
    """Açılır panel: arama + kullanıcı satırları + alt bilgi."""

    selection_changed = Signal(list)  # List[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("multiUserDropdown")
        self.setStyleSheet(
            "QFrame#multiUserDropdown{"
            "background:white;border:1.5px solid #e2e8f0;"
            "border-radius:10px;"
            "}"
        )
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._rows: List[_UserRowWidget] = []
        self._selected: List[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Arama satırı
        search_row = QWidget()
        search_row.setStyleSheet("background:white;border-bottom:1px solid #f1f5f9;")
        sr = QHBoxLayout(search_row)
        sr.setContentsMargins(10, 6, 10, 6)
        sr.setSpacing(6)
        lupe = QLabel("⌕")
        lupe.setStyleSheet("color:#94a3b8;font-size:16px;background:transparent;")
        sr.addWidget(lupe)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Ara...")
        self._search.setStyleSheet(
            "border:none;outline:none;font-size:13px;color:#0f172a;"
            "background:transparent;"
        )
        self._search.textChanged.connect(self._apply_filter)
        sr.addWidget(self._search, 1)
        root.addWidget(search_row)

        # Scroll alan
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(210)
        scroll.setStyleSheet("QScrollArea{background:white;border:none;}")
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:white;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        root.addWidget(scroll)

        # Alt satır
        footer = QWidget()
        footer.setStyleSheet(
            "background:white;border-top:1px solid #f1f5f9;"
        )
        fr = QHBoxLayout(footer)
        fr.setContentsMargins(12, 6, 12, 6)
        self._count_lbl = QLabel("0 seçili")
        self._count_lbl.setStyleSheet("font-size:11px;color:#64748b;background:transparent;")
        fr.addWidget(self._count_lbl)
        fr.addStretch()
        clear_btn = QPushButton("Temizle")
        clear_btn.setStyleSheet(
            "QPushButton{border:none;background:transparent;color:#3b82f6;"
            "font-size:11px;font-weight:700;padding:0;}"
            "QPushButton:hover{color:#1d4ed8;}"
        )
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all)
        fr.addWidget(clear_btn)
        root.addWidget(footer)

    def populate(self, available: List[str], selected: List[str]):
        # Mevcut satırları temizle
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()
        self._selected = list(selected)

        for i, name in enumerate(available):
            row = _UserRowWidget(name, i, name in self._selected)
            row.toggled.connect(self._on_row_toggled)
            self._list_layout.addWidget(row)
            self._rows.append(row)

        self._list_layout.addStretch()
        self._update_count()
        self._search.clear()

    def _on_row_toggled(self, name: str, checked: bool):
        if checked and name not in self._selected:
            self._selected.append(name)
        elif not checked:
            self._selected = [x for x in self._selected if x != name]
        self._update_count()
        self.selection_changed.emit(list(self._selected))

    def _clear_all(self):
        self._selected.clear()
        for row in self._rows:
            row.set_checked(False)
        self._update_count()
        self.selection_changed.emit([])

    def _update_count(self):
        n = len(self._selected)
        self._count_lbl.setText(f"{n} seçili" if n else "Seçim yok")

    def _apply_filter(self, query: str):
        for row in self._rows:
            row.setVisible(row.matches_filter(query))

    def selected_names(self) -> List[str]:
        return list(self._selected)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.hide()
        else:
            super().keyPressEvent(event)


class MultiUserSelectWidget(QWidget):
    """
    Kullanıcı seçim widget'ı — pill + flow wrap + avatar dropdown.

    Public API (değişmez):
        set_available_users(names: List[str])
        set_users(names: List[str])
        selected_users() -> List[str]
        changed  Signal
    """

    changed = Signal()

    _PILL_COLORS = [
        ("#e8f0fe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#ecfdf5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#e0f2fe", "#075985"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._available: List[str] = []
        self._selected: List[str] = []
        self._placeholder = "Kullanıcı seçiniz..."
        self._dropdown: Optional[_MultiUserDropdown] = None
        self._rendered_rows = 1
        self._display_height = 40
        self._max_visible_rows = 4
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._display = QFrame()
        self._display.setObjectName("multiUserDisplay")
        self._display.setCursor(Qt.PointingHandCursor)
        self._display.setMinimumHeight(40)
        self._display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._display.setStyleSheet(
            "QFrame#multiUserDisplay{"
            "background:white;border:1.5px solid #d8e2ed;border-radius:8px;"
            "}"
            "QFrame#multiUserDisplay:hover{border-color:#93c5fd;}"
        )
        self._vlay = QVBoxLayout(self._display)
        self._vlay.setContentsMargins(8, 6, 8, 6)
        self._vlay.setSpacing(5)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("multiUserScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._scroll.setStyleSheet("QScrollArea#multiUserScroll{background:transparent;border:none;}")
        self._scroll.setWidget(self._display)

        outer.addWidget(self._scroll)
        self._display.mousePressEvent = self._toggle_dropdown
        self._render_pills()

    # ── Public API ────────────────────────────────────────────────────────

    def set_available_users(self, user_names: List[str]):
        seen: set = set()
        vals: List[str] = []
        for u in list(user_names or []):
            n = str(u or "").strip()
            if not n:
                continue
            k = n.casefold()
            if k in seen:
                continue
            seen.add(k)
            vals.append(n)
        self._available = vals
        self._selected = [x for x in self._selected if x in self._available]
        self._render_pills()

    def set_users(self, user_names: List[str]):
        seen: set = set()
        vals: List[str] = []
        for u in list(user_names or []):
            n = str(u or "").strip()
            if not n:
                continue
            k = n.casefold()
            if k in seen:
                continue
            seen.add(k)
            vals.append(n)
        if vals == self._selected:
            self._render_pills()
            return
        self._selected = vals
        self._render_pills()
        self.changed.emit()

    def selected_users(self) -> List[str]:
        return list(self._selected)

    # ── İç metodlar ──────────────────────────────────────────────────────

    def _pill_colors(self, name: str):
        idx = sum(ord(c) for c in name) % len(self._PILL_COLORS)
        return self._PILL_COLORS[idx]

    def _make_pill(self, name: str) -> QWidget:
        bg, fg = self._pill_colors(name)
        pill = QWidget()
        pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        pill.setMinimumHeight(self._row_height())
        pill.setStyleSheet(f"QWidget{{background:{bg};border-radius:11px;border:none;}}")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(10, 4, 8, 4)
        pl.setSpacing(5)
        max_label_width = max(90, self._available_pill_width() - 44)
        display_name = QFontMetrics(self.font()).elidedText(str(name), Qt.ElideRight, max_label_width)
        lbl = QLabel(display_name)
        lbl.setToolTip(str(name))
        lbl.setMaximumWidth(max_label_width)
        lbl.setStyleSheet(
            f"color:{fg};font-size:12px;font-weight:600;background:transparent;border:none;"
        )
        pl.addWidget(lbl)
        if self._pill_removable(name):
            x = QLabel("×")
            x.setStyleSheet(
                f"color:{fg};font-size:15px;background:transparent;border:none;padding:0 1px;"
            )
            x.setCursor(Qt.PointingHandCursor)
            x.mousePressEvent = lambda e, n=name: self._remove_user(e, n)
            pl.addWidget(x)
        return pill

    def _pill_removable(self, name: str) -> bool:
        return True

    def _pill_width(self, name: str) -> int:
        metrics = QFontMetrics(self.font())
        return metrics.horizontalAdvance(str(name or "")) + 44

    def _row_height(self) -> int:
        return max(QFontMetrics(self.font()).height() + 12, 28)

    def _available_pill_width(self, width: Optional[int] = None) -> int:
        source_width = int(width or self._display.width() or self.width() or 0)
        # İç marginler + son satırdaki açılır liste oku için güvenli alan bırak.
        # Ok genişliği hesaba katılmazsa özellikle 4. chip son satırda kırpılabiliyor.
        reserved = 58
        return max(source_width - reserved, 160) if source_width > 20 else 300

    def _pill_rows(self, width: Optional[int] = None) -> List[List[str]]:
        if not self._selected:
            return [[]]
        avail = self._available_pill_width(width)
        gap = 5
        rows: List[List[str]] = []
        cur_row: List[str] = []
        cur_w = 0
        for name in self._selected:
            pw = min(self._pill_width(name), max(avail, 160))
            if cur_row and cur_w + gap + pw > avail:
                rows.append(cur_row)
                cur_row = [name]
                cur_w = pw
            else:
                cur_row.append(name)
                cur_w += (gap if len(cur_row) > 1 else 0) + pw
        if cur_row:
            rows.append(cur_row)
        return rows or [[]]

    def _height_for_rows(self, row_count: int) -> int:
        margins = self._vlay.contentsMargins()
        spacing = self._vlay.spacing()
        rows = max(1, int(row_count or 1))
        visible_rows = min(rows, self._max_visible_rows)
        return max(40, margins.top() + margins.bottom() + visible_rows * self._row_height() + max(0, visible_rows - 1) * spacing)

    def _content_height_for_rows(self, row_count: int) -> int:
        margins = self._vlay.contentsMargins()
        spacing = self._vlay.spacing()
        rows = max(1, int(row_count or 1))
        return max(40, margins.top() + margins.bottom() + rows * self._row_height() + max(0, rows - 1) * spacing)

    def _apply_display_height(self, row_count: int):
        height = self._height_for_rows(row_count)
        content_height = self._content_height_for_rows(row_count)
        if height != self._display_height:
            self._display_height = height
        self.setMinimumHeight(height)
        self._scroll.setMinimumHeight(height)
        self._scroll.setMaximumHeight(height)
        self._display.setMinimumHeight(content_height)
        self._display.setMaximumHeight(16777215)
        self._rendered_rows = max(1, int(row_count or 1))
        self._display.updateGeometry()
        self._scroll.updateGeometry()
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            layout = parent.layout()
            if layout is not None:
                layout.invalidate()
            parent.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._height_for_rows(len(self._pill_rows(width)))

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        width = max(hint.width(), self.width(), 240)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(160, self.heightForWidth(max(self.width(), 160)))

    def _clear_rows(self):
        """_vlay içindeki tüm satır widget'larını sil (her seferinde yeni QLabel yaratılıyor)."""
        while self._vlay.count():
            item = self._vlay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_pills(self):
        """Her çağrıda tüm satırları sıfırdan yeni widget'larla yeniden çizer.
        _placeholder / _chevron artık kalıcı widget değil — her seferinde yeni QLabel."""
        self._clear_rows()

        if not self._selected:
            row = QWidget()
            row.setStyleSheet("background:transparent;border:none;")
            row.setMinimumHeight(self._row_height())
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            ph = QLabel(getattr(self, "_placeholder", "Kullanıcı seçiniz..."))
            ph.setStyleSheet(
                "color:#94a3b8;font-size:13px;background:transparent;border:none;"
            )
            rl.addWidget(ph)
            rl.addStretch()
            ch = QLabel("▾")
            ch.setStyleSheet(
                "color:#94a3b8;font-size:13px;background:transparent;border:none;"
            )
            rl.addWidget(ch)
            self._vlay.addWidget(row)
        else:
            GAP = 5
            all_rows = self._pill_rows()

            for ri, row_names in enumerate(all_rows):
                row = QWidget()
                row.setStyleSheet("background:transparent;border:none;")
                row.setMinimumHeight(self._row_height())
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(GAP)
                for nm in row_names:
                    rl.addWidget(self._make_pill(nm))
                rl.addStretch()
                if ri == len(all_rows) - 1:
                    ch = QLabel("▾")
                    ch.setStyleSheet(
                        "color:#94a3b8;font-size:13px;background:transparent;border:none;"
                    )
                    rl.addWidget(ch)
                self._vlay.addWidget(row)

        self._apply_display_height(1 if not self._selected else len(all_rows))
        self._display.setToolTip(", ".join(self._selected))

    def _remove_user(self, event, name: str):
        event.accept()
        self._selected = [x for x in self._selected if x != name]
        self._render_pills()
        if self._dropdown and self._dropdown.isVisible():
            self._dropdown.populate(self._available, self._selected)
        self.changed.emit()

    def _toggle_dropdown(self, event=None):
        if self._dropdown is None:
            self._dropdown = _MultiUserDropdown(self)
            self._dropdown.setFixedWidth(max(self.width(), 240))
            self._dropdown.selection_changed.connect(self._on_dropdown_changed)

        if self._dropdown.isVisible():
            self._dropdown.hide()
            return

        self._dropdown.setFixedWidth(max(self.width(), 240))
        self._dropdown.populate(self._available, self._selected)
        pos = self.mapToGlobal(self._scroll.rect().bottomLeft())
        self._dropdown.move(pos.x(), pos.y() + 2)
        self._dropdown.show()
        self._dropdown.raise_()

    def _on_dropdown_changed(self, names: List[str]):
        self._selected = list(names)
        self._render_pills()
        self.changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_pills()
        if self._dropdown:
            self._dropdown.setFixedWidth(max(self.width(), 240))


class MultiStaffSelectWidget(MultiUserSelectWidget):
    """Personel/staff seçim widget'ı — isim chip'i tutar, kayıt için staff id döndürür."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder = "Sorumlu mühendis seçiniz..."
        self._staff_id_by_name: Dict[str, int] = {}
        self._staff_name_by_id: Dict[int, str] = {}

    def set_staff_options(self, staff_rows: List[dict]):
        names: List[str] = []
        self._staff_id_by_name = {}
        self._staff_name_by_id = {}
        for row in staff_rows or []:
            try:
                sid = int(row.get("id") or row.get("staff_id") or 0)
            except Exception:
                sid = 0
            name = str(row.get("full_name") or row.get("name") or "").strip()
            if not sid or not name:
                continue
            names.append(name)
            self._staff_id_by_name[name] = sid
            self._staff_name_by_id[sid] = name
        self.set_available_users(names)

    def set_users(self, users: List[str]):
        super().set_users(list(users or [])[:1])

    def set_selected_staff_ids(self, staff_ids: List[int]):
        names: List[str] = []
        for sid in staff_ids or []:
            name = self._staff_name_by_id.get(int(sid or 0))
            if name:
                names.append(name)
                break
        self.set_users(names)

    def _on_dropdown_changed(self, names: List[str]):
        self._selected = list(names or [])[-1:]
        self._render_pills()
        self.changed.emit()

    def selected_staff_ids(self) -> List[int]:
        ids: List[int] = []
        seen = set()
        for name in self.selected_users():
            sid = int(self._staff_id_by_name.get(name) or 0)
            if sid and sid not in seen:
                seen.add(sid)
                ids.append(sid)
                break
        return ids

    def selected_staff_id(self) -> int:
        ids = self.selected_staff_ids()
        return int(ids[0]) if ids else 0


class MultiPlatformSelectWidget(MultiUserSelectWidget):
    """Faz 1 çoklu platform seçim prototipi.

    MultiUserSelectWidget'in denenmiş chip/dropdown altyapısını generic API ile
    kullanır; state UI tarafında çoklu platform adlarını tutar, backend'e sadece
    ilk seçili platform currentText uyumluluğu ile verilir.
    """

    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder = "Platform seçiniz..."
        self._platform_id_by_name: Dict[str, int] = {}
        self._locked_platform_keys: set[str] = set()
        self._display.setObjectName("multiPlatformDisplay")
        self._display.setStyleSheet(
            "QFrame#multiPlatformDisplay{background:white;border:1.5px solid #d8e2ed;border-radius:8px;}"
            "QFrame#multiPlatformDisplay:hover{border-color:#93c5fd;}"
        )

    def set_platforms(self, platforms: List[object]):
        names: List[str] = []
        self._platform_id_by_name = {}
        for item in platforms or []:
            if isinstance(item, dict):
                pid = int(item.get("id") or item.get("platform_id") or 0)
                name = str(item.get("name") or item.get("platform_name") or "").strip()
            else:
                pid = 0
                name = str(item or "").strip()
            if name:
                names.append(name)
                if pid:
                    self._platform_id_by_name[name] = pid
        self.set_available_users(names)

    def selected_platform_names(self) -> List[str]:
        return self.selected_users()

    def selected_platform_ids(self) -> List[int]:
        ids: List[int] = []
        seen = set()
        for name in self.selected_platform_names():
            pid = int(self._platform_id_by_name.get(name) or 0)
            if pid and pid not in seen:
                seen.add(pid); ids.append(pid)
        return ids

    def selected_platforms(self) -> List[str]:
        return self.selected_platform_names()

    def selected_platform_records(self) -> List[dict]:
        ids = self.selected_platform_ids()
        names = self.selected_platform_names()
        return [{"id": pid, "name": name, "platform_id": pid, "platform_name": name} for pid, name in zip(ids, names)]

    def set_selected_platforms(self, names: List[str]):
        self.set_users(names)

    def set_locked_platforms(self, names: List[str]):
        self._locked_platform_keys = {str(name or "").strip().casefold() for name in names or [] if str(name or "").strip()}
        self._render_pills()

    def _pill_removable(self, name: str) -> bool:
        return str(name or "").strip().casefold() not in self._locked_platform_keys

    def currentText(self) -> str:
        vals = self.selected_platforms()
        return vals[0] if vals else ""

    def currentIndex(self) -> int:
        cur = self.currentText()
        try:
            return self._available.index(cur)
        except ValueError:
            return -1

    def setCurrentIndex(self, idx: int):
        if 0 <= idx < len(self._available):
            self.set_selected_platforms([self._available[idx]])

    def setCurrentText(self, text: str):
        t = str(text or "").strip()
        self.set_selected_platforms([t] if t else [])

    @property
    def currentIndexChanged(self):
        return self.currentTextChanged

    def _on_dropdown_changed(self, names: List[str]):
        old = self.currentText()
        locked = [name for name in self._selected if str(name or "").strip().casefold() in self._locked_platform_keys]
        merged: List[str] = []
        seen = set()
        for name in list(locked) + list(names or []):
            clean = str(name or "").strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                merged.append(clean)
        super()._on_dropdown_changed(merged)
        new = self.currentText()
        if old != new:
            self.currentTextChanged.emit(new)

    def _remove_user(self, event, name: str):
        old = self.currentText()
        super()._remove_user(event, name)
        new = self.currentText()
        if old != new:
            self.currentTextChanged.emit(new)

