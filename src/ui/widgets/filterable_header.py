from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QDateEdit, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QStyle, QStyledItemDelegate, QTableView, QTableWidget, QVBoxLayout,
    QWidget, QWidgetAction,
)


COL_CONTRACT_NO = 2
COL_USER = 3
COL_T_DATE = 5
COL_REMAINING = 6
PLATFORM_SELECTED_ROLE = Qt.UserRole + 100


class PlatformListDelegate(QStyledItemDelegate):
    """Platform listesi: renkli kısaltma kutusu + isim + sayı."""

    _PALETTES = [
        ("#dbeafe", "#1e40af"),
        ("#fce7f3", "#9d174d"),
        ("#d1fae5", "#065f46"),
        ("#fef3c7", "#92400e"),
        ("#ede9fe", "#5b21b6"),
        ("#fee2e2", "#991b1b"),
        ("#e0f2fe", "#075985"),
        ("#fef9c3", "#713f12"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict = {}   # row -> count string

    def set_count(self, row: int, count: int):
        self._counts[row] = str(count) if count else ""

    def paint(self, painter, option, index):
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QStyle

        painter.save()

        # PySide6: option.state is StateFlag enum — use QStyle.StateFlag members
        state = option.state
        # QListWidget'in native selection state'i tekli seçim/current item ile sınırlı
        # kalabildiği için platform seçim mantığını ayrı bir item role'ünden okuyoruz.
        # Böylece çoklu seçimde selected_platforms set'indeki her satır aynı aktif
        # stili alır; focus/current satır tek başına selected gibi boyanmaz.
        is_selected = bool(index.data(PLATFORM_SELECTED_ROLE))
        is_hover    = bool(state & QStyle.State_MouseOver)

        # Arka plan
        if is_selected:
            painter.fillRect(option.rect, QColor("#eff6ff"))
            # Sol mavi çizgi
            painter.fillRect(
                QRect(option.rect.left(), option.rect.top(), 3, option.rect.height()),
                QColor("#2563eb")
            )
        elif is_hover:
            painter.fillRect(option.rect, QColor("#f0f7ff"))
        else:
            painter.fillRect(option.rect, QColor("#ffffff"))

        row = index.row()
        pal_bg, pal_fg = self._PALETTES[row % len(self._PALETTES)]

        # UserRole'den platform adını al (text'te sayaç olabilir)
        platform_name = str(index.data(Qt.UserRole) or index.data(Qt.DisplayRole) or "").strip()
        abbr = platform_name[:3].upper() if platform_name else "?"

        rect = option.rect
        abbr_rect = QRect(
            rect.left() + 10,
            rect.top() + (rect.height() - 26) // 2,
            34, 26
        )

        # Kısaltma kutusu
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(pal_bg))
        painter.drawRoundedRect(abbr_rect, 5, 5)

        af = painter.font()
        af.setPointSize(8)
        af.setBold(True)
        painter.setFont(af)
        painter.setPen(QColor(pal_fg))
        painter.drawText(abbr_rect, Qt.AlignCenter, abbr)

        # Platform adı
        name_x = abbr_rect.right() + 10
        count_str = self._counts.get(row, "")
        count_w = 30 if count_str else 0
        name_rect = QRect(name_x, rect.top(), rect.width() - name_x - count_w - 8, rect.height())

        nf = painter.font()
        nf.setPointSize(10)
        nf.setBold(is_selected)
        painter.setFont(nf)
        painter.setPen(QColor("#1e40af") if is_selected else QColor("#374151"))
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, platform_name)

        # Sağda sözleşme sayısı
        if count_str:
            cnt_rect = QRect(rect.right() - count_w - 6, rect.top(), count_w, rect.height())
            cf = painter.font()
            cf.setPointSize(9)
            cf.setBold(False)
            painter.setFont(cf)
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(cnt_rect, Qt.AlignVCenter | Qt.AlignRight, count_str)

        painter.restore()

    def sizeHint(self, option, index):
        try:
            w = int(option.rect.width()) if option is not None else 200
            return QSize(w if w > 0 else 200, 46)
        except Exception:
            return QSize(200, 46)


class FilterableHeaderView(QHeaderView):
    """Excel gibi sutun filtresi destekleyen header.
    Her sutun basliginda kucuk bir filtre ikonu gosterir.
    Tiklayinca o sutunun benzersiz degerlerini checkbox listesi olarak acar.
    """
    filterChanged = Signal()

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        # col_index -> set of selected values (None = tumu secili)
        self._col_filters: Dict[int, Optional[set]] = {}
        self._date_ranges: Dict[int, Tuple[Optional[date], Optional[date]]] = {}
        self._day_ranges: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
        self.sectionClicked.connect(self._on_section_clicked)

    def _filter_disabled_for_col(self, col: int) -> bool:
        # Sözleşme No ve Kullanıcı sütunlarında Excel-tipi header filtresi istenmiyor.
        return int(col) in (COL_CONTRACT_NO, COL_USER)

    def has_active_filter(self, col: int) -> bool:
        if self._filter_disabled_for_col(col):
            return False
        return (
            (col in self._col_filters and self._col_filters[col] is not None)
            or col in self._date_ranges
            or col in self._day_ranges
        )

    def get_filter(self, col: int) -> Optional[set]:
        return self._col_filters.get(col)

    def clear_filter(self, col: int):
        self._col_filters.pop(col, None)
        self._date_ranges.pop(col, None)
        self._day_ranges.pop(col, None)
        self.filterChanged.emit()
        self.viewport().update()

    def clear_all_filters(self):
        self._col_filters.clear()
        self._date_ranges.clear()
        self._day_ranges.clear()
        self.filterChanged.emit()
        self.viewport().update()

    def _get_column_values(self, col: int) -> List[str]:
        table = self.parent()
        if not isinstance(table, (QTableWidget, QTableView)):
            return []
        vals = set()
        # Tum satirlari tara (visible_rows varsa onu kullan)
        source = getattr(table, '_all_rows_for_filter', None)
        if source is not None:
            col_keys = getattr(table, "_filter_col_keys", ["platform", "type", "no", "user", "status", "date", "days", "tags", "summary"])
            if col < len(col_keys):
                window = table.window()
                for row_index, it in enumerate(source, start=1):
                    key = col_keys[col]
                    if key == "type":
                        v = str(it.get("type_display", it.get("type", "")) or "").strip()
                    elif key in {"status", "date", "days"} and hasattr(window, "_contract_health"):
                        _cls, st, days, dt = window._contract_health(it)
                        v = {"status": st, "date": dt, "days": days}.get(key, "")
                    elif key == "tags":
                        for tg in list(it.get("tags", []) or []):
                            tg = str(tg or "").strip()
                            if tg:
                                vals.add(tg)
                        continue
                    elif key == "summary":
                        v = "Özet"
                    else:
                        v = str(it.get(key, "") or "").strip()
                    if v:
                        vals.add(v)
        else:
            if isinstance(table, QTableWidget):
                for r in range(table.rowCount()):
                    item = table.item(r, col)
                    v = str(item.text() if item else "").strip()
                    if v:
                        vals.add(v)
            elif isinstance(table, QTableView):
                model = table.model()
                if model is not None:
                    for r in range(model.rowCount()):
                        idx = model.index(r, col)
                        v = str(model.data(idx, Qt.DisplayRole) or "").strip()
                        if v:
                            vals.add(v)
        return sorted(vals, key=lambda x: x.lower())

    def _on_section_clicked(self, col: int):
        if self._filter_disabled_for_col(col):
            return
        values = self._get_column_values(col)
        if not values and col not in (COL_T_DATE, COL_REMAINING):
            return
        current_filter = self._col_filters.get(col)  # None = tumu

        popup = QMenu(self.viewport())
        popup.setObjectName("filterPopup")
        popup.setStyleSheet(
            "QMenu { background:#fff; border:1px solid #d8e2ed; border-radius:6px; padding:4px; }"
            "QMenu::item { padding:4px 14px; border-radius:4px; }"
            "QMenu::item:selected { background:#EEF2F6; }"
        )

        # Tumunu sec / temizle
        select_all_action = popup.addAction("✔ Tümünü Seç")
        clear_action = popup.addAction("✕ Filtreyi Temizle")
        clear_action.setEnabled(current_filter is not None or col in self._date_ranges or col in self._day_ranges)
        popup.addSeparator()
        # Kalan Gun sutunu - siralama secenekleri ekle
        sort_asc_action = None
        sort_desc_action = None
        if col == COL_REMAINING:  # Kalan Gun sutunu
            sort_asc_action = popup.addAction("↑ Artan Sırala (Az → Çok)")
            sort_desc_action = popup.addAction("↓ Azalan Sırala (Çok → Az)")
            popup.addSeparator()


        if col == COL_T_DATE:
            self._add_date_range_controls(popup, col)
            popup.addSeparator()
        elif col == COL_REMAINING:
            self._add_day_range_controls(popup, col)
            popup.addSeparator()
        # Her deger icin checkbox action
        check_actions: List[Tuple[QAction, str]] = []
        if col not in (COL_T_DATE, COL_REMAINING):
            for val in values:
                icon_txt = "✔" if (current_filter is None or val in current_filter) else "□"
                a = popup.addAction(f"{icon_txt}  {val}")
                a.setCheckable(False)
                check_actions.append((a, val))

        # Sutun basliginin ekran koordinati
        x = self.sectionViewportPosition(col)
        y = self.height()
        global_pos = self.viewport().mapToGlobal(QPoint(x, y))

        chosen = popup.exec(global_pos)
        if not chosen:
            return
        if chosen is select_all_action:
            self._col_filters.pop(col, None)
            self._date_ranges.pop(col, None)
            self._day_ranges.pop(col, None)
        elif chosen is clear_action:
            self._col_filters.pop(col, None)
            self._date_ranges.pop(col, None)
            self._day_ranges.pop(col, None)
        elif sort_asc_action is not None and chosen is sort_asc_action:
            # Kalan gun artan siralama - table parent'ina sort_mode set et
            table = self.parent()
            if hasattr(table, '_sort_mode'):
                table._sort_mode = 'days_asc'
            self.filterChanged.emit()
            return
        elif sort_desc_action is not None and chosen is sort_desc_action:
            table = self.parent()
            if hasattr(table, '_sort_mode'):
                table._sort_mode = 'days_desc'
            self.filterChanged.emit()
            return
        else:
            # Tiklanana gore toggle
            clicked_val = next((v for a, v in check_actions if a is chosen), None)
            if clicked_val is not None:
                if current_filter is None:
                    # Ilk tiklamada sadece o degeri sec
                    self._col_filters[col] = {clicked_val}
                elif clicked_val in current_filter:
                    current_filter.discard(clicked_val)
                    if not current_filter:
                        self._col_filters.pop(col, None)
                    else:
                        self._col_filters[col] = current_filter
                else:
                    current_filter.add(clicked_val)
                    self._col_filters[col] = current_filter
        self.filterChanged.emit()
        self.viewport().update()

    def _add_date_range_controls(self, popup: QMenu, col: int):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(5)
        title = QLabel("Tarih aralığı")
        title.setStyleSheet("font-weight:800;color:#1b3150;")
        lay.addWidget(title)
        current_from, current_to = self._date_ranges.get(col, (None, None))
        start = QDateEdit()
        start.setCalendarPopup(True)
        start.setDisplayFormat("dd.MM.yyyy")
        start.setSpecialValueText("Başlangıç")
        start.setMinimumDate(QDate(2000, 1, 1))
        start.setMaximumDate(QDate(2100, 12, 31))
        start.setDate(QDate(current_from.year, current_from.month, current_from.day) if current_from else QDate.currentDate())
        if not current_from:
            start.lineEdit().clear()
        end = QDateEdit()
        end.setCalendarPopup(True)
        end.setDisplayFormat("dd.MM.yyyy")
        end.setSpecialValueText("Bitiş")
        end.setMinimumDate(QDate(2000, 1, 1))
        end.setMaximumDate(QDate(2100, 12, 31))
        end.setDate(QDate(current_to.year, current_to.month, current_to.day) if current_to else QDate.currentDate())
        if not current_to:
            end.lineEdit().clear()
        lay.addWidget(start)
        lay.addWidget(end)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Uygula")
        clear_btn = QPushButton("Aralığı Temizle")
        buttons.addWidget(apply_btn)
        buttons.addWidget(clear_btn)
        lay.addLayout(buttons)

        def apply_range():
            start_date = start.date().toPython() if start.lineEdit().text().strip() else None
            end_date = end.date().toPython() if end.lineEdit().text().strip() else None
            if start_date or end_date:
                self._date_ranges[col] = (start_date, end_date)
            else:
                self._date_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        def clear_range():
            self._date_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        apply_btn.clicked.connect(apply_range)
        clear_btn.clicked.connect(clear_range)
        action = QWidgetAction(popup)
        action.setDefaultWidget(box)
        popup.addAction(action)

    def _add_day_range_controls(self, popup: QMenu, col: int):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(5)
        title = QLabel("Kalan gün aralığı")
        title.setStyleSheet("font-weight:800;color:#1b3150;")
        lay.addWidget(title)
        current_min, current_max = self._day_ranges.get(col, (None, None))
        min_edit = QLineEdit()
        min_edit.setPlaceholderText("Min / tek gün")
        min_edit.setText("" if current_min is None else str(current_min))
        max_edit = QLineEdit()
        max_edit.setPlaceholderText("Maks")
        max_edit.setText("" if current_max is None else str(current_max))
        lay.addWidget(min_edit)
        lay.addWidget(max_edit)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Uygula")
        clear_btn = QPushButton("Aralığı Temizle")
        buttons.addWidget(apply_btn)
        buttons.addWidget(clear_btn)
        lay.addLayout(buttons)

        def parse_int(widget: QLineEdit):
            txt = widget.text().strip()
            if not txt:
                return None
            try:
                return int(txt)
            except ValueError:
                return None

        def apply_range():
            min_val = parse_int(min_edit)
            max_val = parse_int(max_edit)
            if min_val is not None or max_val is not None:
                if min_val is not None and max_val is None:
                    max_val = min_val
                self._day_ranges[col] = (min_val, max_val)
            else:
                self._day_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        def clear_range():
            self._day_ranges.pop(col, None)
            popup.close()
            self.filterChanged.emit()
            self.viewport().update()

        apply_btn.clicked.connect(apply_range)
        clear_btn.clicked.connect(clear_range)
        action = QWidgetAction(popup)
        action.setDefaultWidget(box)
        popup.addAction(action)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if self._filter_disabled_for_col(logical_index):
            return
        # Filtre aktifse ikonu farkli goster
        active = self.has_active_filter(logical_index)
        icon = "▼" if active else "▾"  # solid down vs outline down
        painter.save()
        painter.setPen(QColor("#1F5BE3" if active else "#94A3B8"))
        f = painter.font()
        f.setPointSize(9)  # daha buyuk
        f.setBold(active)
        painter.setFont(f)
        painter.drawText(rect.adjusted(0, 0, -6, 0), Qt.AlignRight | Qt.AlignVCenter, icon)
        painter.restore()

