from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QPainter, QCursor, QLinearGradient, QBrush, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import STYLE

TABLE_INFO = {
    "contracts": "Ana sözleşme ve SD kayıtları",
    "systems": "Sözleşmelere bağlı sistemler",
    "deliveries": "Kabul / teslimat kayıtları",
    "system_components": "Sistem bileşen adetleri",
    "delivery_components": "Kabul bazlı plan/teslim",
    "contract_tags": "Sözleşme etiket bağlantıları",
    "users": "Kullanıcı / kurum tanımları",
    "tags": "Etiket tanımları",
    "platforms": "Platform adları ve logolar",
    "components": "Tanımlı bileşenler",
    "activity_logs": "İşlem geçmişi",
    "component_platforms": "Bileşen platform yetkileri",
}

FALLBACK_RELATIONS = [
    ("platforms", "id", "contracts", "platform_id"),
    ("users", "id", "contracts", "user_id"),
    ("contracts", "id", "systems", "contract_id"),
    ("users", "id", "systems", "delivery_user_id"),
    ("contracts", "id", "deliveries", "contract_id"),
    ("systems", "id", "deliveries", "system_id"),
    ("users", "id", "deliveries", "delivery_user_id"),
    ("contracts", "id", "contract_tags", "contract_id"),
    ("tags", "id", "contract_tags", "tag_id"),
    ("systems", "id", "system_components", "system_id"),
    ("components", "id", "system_components", "component_id"),
    ("deliveries", "id", "delivery_components", "delivery_id"),
    ("components", "id", "delivery_components", "component_id"),
]


class SchemaView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._zoom = 1.0

    def zoom_in(self):
        self._zoom = min(2.0, self._zoom + 0.25)
        self.resetTransform()
        self.scale(self._zoom, self._zoom)

    def reset_zoom(self):
        self._zoom = 1.0
        self.resetTransform()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 0.1 if delta > 0 else -0.1
            nz = max(0.5, min(2.0, self._zoom + step))
            if abs(nz - self._zoom) > 1e-9:
                self._zoom = nz
                self.resetTransform()
                self.scale(self._zoom, self._zoom)
            event.accept()
            return
        super().wheelEvent(event)


class SchemaTableItem(QGraphicsObject):
    def __init__(self, table_name: str, count: int, cols: List[Tuple[str, str, bool, bool]], dialog: "DatabaseManagementDialog"):
        super().__init__()
        self.table_name = table_name
        self.count = count
        self.cols = cols
        self.dialog = dialog
        self.card_width = 320
        self.header_height = 36
        self.row_height = 20
        visible_rows = max(1, len(cols))
        self.card_height = 14 + self.header_height + (visible_rows * self.row_height) + 14
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(10)

    def boundingRect(self):
        return QRectF(0, 0, self.card_width, self.card_height)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#bdd0ea"), 1.1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 14, 14)
        header_rect = QRectF(8, 8, rect.width() - 16, self.header_height)
        grad = QLinearGradient(header_rect.topLeft(), header_rect.topRight())
        grad.setColorAt(0.0, QColor("#2563eb"))
        grad.setColorAt(1.0, QColor("#0f9f6e"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(header_rect, 10, 10)
        painter.setPen(Qt.white)
        painter.drawText(QRectF(header_rect.left() + 10, header_rect.top(), header_rect.width() - 120, header_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, self.table_name)
        badge_rect = QRectF(header_rect.right() - 82, header_rect.top() + 7, 72, 22)
        painter.setBrush(QColor("#e6f9ef"))
        painter.drawRoundedRect(badge_rect, 10, 10)
        painter.setPen(QColor("#0f5132"))
        painter.drawText(badge_rect, Qt.AlignCenter, self.dialog._fmt_count(self.count))
        y = self.header_height + 16
        painter.setPen(QColor("#1f3b58"))
        fm = QFontMetrics(painter.font())
        for col_name, col_type, pk, fk in self.cols:
            badge = "PK" if pk else ("FK" if fk else "•")
            painter.setPen(QColor("#0f9f6e") if pk else (QColor("#4f46e5") if fk else QColor("#1f3b58")))
            painter.drawText(QRectF(14, y, 24, 18), Qt.AlignVCenter | Qt.AlignLeft, badge)
            painter.setPen(QColor("#1f3b58"))
            painter.drawText(QRectF(38, y, 180, 18), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(col_name, Qt.ElideRight, 170))
            painter.setPen(QColor("#6b7f98"))
            painter.drawText(QRectF(rect.width() - 110, y, 96, 18), Qt.AlignVCenter | Qt.AlignRight, fm.elidedText(col_type, Qt.ElideRight, 92))
            y += self.row_height
        if self.isSelected():
            painter.setPen(QPen(QColor("#3b82f6"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 14, 14)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            rect = self.scene().sceneRect()
            br = self.boundingRect()
            x = min(max(value.x(), rect.left()), rect.right() - br.width())
            y = min(max(value.y(), rect.top()), rect.bottom() - br.height())
            return super().itemChange(change, value.__class__(x, y))
        if change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.dialog, "_schema_rendering", False):
                self.dialog._update_relation_lines_for_table(self.table_name)
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.setCursor(QCursor(Qt.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(QCursor(Qt.OpenHandCursor))
        super().mouseReleaseEvent(event)


class DatabaseManagementDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("databaseEditorDialog")
        self.setWindowTitle("Database Yönetimi - STS")
        self.resize(1400, 820)
        self.setMinimumSize(1100, 680)
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

        self.stats: Dict = {}
        self.table_names: List[str] = []
        self.active_table: str = ""
        self._current_rows: List[dict] = []
        self._current_columns: List[str] = []
        self._sort_column: Optional[str] = None
        self._sort_ascending: bool = True
        self.schema_cards: Dict[str, SchemaTableItem] = {}
        self.schema_rel_lines = []
        self._schema_rendering = False

        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        QTimer.singleShot(0, self.showMaximized)
        self.refresh_all()

    def _local_style(self) -> str:
        return """
QDialog#databaseEditorDialog { background:#eef4fb; }
QFrame#topBar { background:#ffffff; border:1px solid #d8e4f2; border-radius:12px; }
QLabel#titleBadge { background:#2563eb; color:white; border-radius:10px; padding:4px 8px; font-weight:800; }
QLabel#topTitle { color:#0f2742; font-size:15px; font-weight:800; }
QLabel#connOk { background:#dcfce7; color:#166534; border:1px solid #bbf7d0; border-radius:10px; padding:6px 10px; font-weight:700; }

QFrame#iconRail, QFrame#sidePanel, QFrame#mainPanel, QFrame#toolbarCard { background:#ffffff; border:1px solid #d8e4f2; border-radius:12px; }
QPushButton#railBtn { background:transparent; border:1px solid transparent; border-radius:10px; min-width:48px; min-height:48px; padding:8px; color:#2d4a6b; font-weight:900; font-size:12px; }
QPushButton#railBtn[active='true'] { background:#2563eb; color:white; }

QLabel { background:transparent; }
QCheckBox, QRadioButton { background:transparent; }

QLineEdit, QComboBox { background:#ffffff; border:1px solid #d8e4f2; border-radius:8px; padding:7px 9px; }
QPushButton#softBtn { background:#f1f5ff; border:1px solid #cddafb; color:#1d4ed8; border-radius:8px; padding:7px 11px; font-weight:700; }
QPushButton#primaryBtn { background:#2563eb; border:none; color:white; border-radius:8px; padding:7px 11px; font-weight:800; }
QPushButton#warnBtn { background:#eaf1ff; border:1px solid #cddafb; color:#1d4ed8; border-radius:8px; padding:7px 11px; font-weight:700; }

QListWidget#tableList { background:transparent; border:none; }
QListWidget#tableList::item { border:1px solid #d8e4f2; border-radius:10px; margin:4px 2px; padding:8px; background:#f8fbff; }
QListWidget#tableList::item:selected { background:#eaf1ff; border:1px solid #8bb3ff; color:#0f2742; }

QTableWidget { background:#ffffff; border:1px solid #d8e4f2; border-radius:10px; gridline-color:#e5edf8; alternate-background-color:#f8fbff; }
QHeaderView::section { background:#edf3ff; border:none; border-right:1px solid #d8e4f2; padding:6px; color:#264463; font-weight:700; }

QFrame#schemaCanvasWrap { background:#f2f6fc; border:1px solid #d8e4f2; border-radius:10px; }
QFrame#schemaCard { background:#ffffff; border:1px solid #bdd0ea; border-radius:14px; }
QLabel#schemaCardTitle { color:white; border-radius:8px; padding:6px 10px; font-size:13px; font-weight:800; }
QLabel#schemaCol { color:#1f3b58; font-size:12px; background:transparent; }
QLabel#pkTag { color:#0f9f6e; font-weight:800; }
QLabel#fkTag { color:#4f46e5; font-weight:800; }
"""

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)

        self.rail = self._build_rail()
        body.addWidget(self.rail)

        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)

        self.main = QFrame()
        self.main.setObjectName("mainPanel")
        mlay = QVBoxLayout(self.main)
        mlay.setContentsMargins(10, 10, 10, 10)
        mlay.setSpacing(8)
        self.main_stack = QVBoxLayout()
        mlay.addLayout(self.main_stack, 1)
        body.addWidget(self.main, 1)

        self.tables_page = self._build_tables_page()
        self.schema_page = self._build_schema_page()
        self.main_stack.addWidget(self.tables_page)
        self.main_stack.addWidget(self.schema_page)
        self.sql_page = self._build_sql_page()
        self.main_stack.addWidget(self.sql_page)
        self._set_page("tables")

    def _build_topbar(self):
        bar = QFrame(); bar.setObjectName("topBar")
        lay = QHBoxLayout(bar); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(10)
        left = QHBoxLayout()
        b = QLabel("DB"); b.setObjectName("titleBadge")
        self.top_title = QLabel("STS Database Editor"); self.top_title.setObjectName("topTitle")
        left.addWidget(b); left.addWidget(self.top_title)
        lay.addLayout(left)

        lay.addStretch(1)

        self.conn_lbl = QLabel("● SQLite bağlantısı aktif")
        self.conn_lbl.setObjectName("connOk")
        lay.addWidget(self.conn_lbl)

        self.backup_btn = QPushButton("Yedek Al"); self.backup_btn.setObjectName("softBtn"); self.backup_btn.clicked.connect(self.run_backup)
        self.opt_btn = QPushButton("Optimize"); self.opt_btn.setObjectName("softBtn"); self.opt_btn.clicked.connect(self.run_optimize)
        lay.addWidget(self.backup_btn); lay.addWidget(self.opt_btn)
        return bar

    def _build_rail(self):
        rail = QFrame(); rail.setObjectName("iconRail"); rail.setFixedWidth(72)
        lay = QVBoxLayout(rail); lay.setContentsMargins(8, 12, 8, 12); lay.setSpacing(8)
        self.rail_tables = QPushButton("TAB"); self.rail_tables.setObjectName("railBtn"); self.rail_tables.clicked.connect(lambda: self._set_page("tables"))
        self.rail_schema = QPushButton("REL"); self.rail_schema.setObjectName("railBtn"); self.rail_schema.clicked.connect(lambda: self._set_page("schema"))
        self.rail_sql = QPushButton("SQL"); self.rail_sql.setObjectName("railBtn"); self.rail_sql.clicked.connect(lambda: self._set_page("sql"))
        self.rail_tables.setToolTip("Tablolar")
        self.rail_schema.setToolTip("Şema Görselleştirici")
        self.rail_sql.setToolTip("SQL Terminal")
        lay.addWidget(self.rail_tables)
        lay.addWidget(self.rail_schema)
        lay.addWidget(self.rail_sql)
        lay.addStretch(1)
        return rail

    def _build_sidebar(self):
        w = QFrame(); w.setObjectName("sidePanel"); w.setFixedWidth(300)
        lay = QVBoxLayout(w); lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(8)
        lay.addWidget(QLabel("Tablolar"))
        self.table_search = QLineEdit(); self.table_search.setPlaceholderText("Tablo ara..."); self.table_search.textChanged.connect(self._refresh_sidebar)
        lay.addWidget(self.table_search)
        self.table_list = QListWidget(); self.table_list.setObjectName("tableList"); self.table_list.itemSelectionChanged.connect(self._on_table_selected)
        lay.addWidget(self.table_list, 1)
        return w

    def _build_tables_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setSpacing(8)

        tb = QFrame(); tb.setObjectName("toolbarCard")
        tlay = QHBoxLayout(tb); tlay.setContentsMargins(8, 8, 8, 8); tlay.setSpacing(8)
        self.row_search = QLineEdit(); self.row_search.setPlaceholderText("Satır ara / filtrele..."); self.row_search.textChanged.connect(self._apply_table_filters)
        self.limit_combo = QComboBox(); self.limit_combo.addItems(["100", "500", "1000"]); self.limit_combo.setCurrentText("100"); self.limit_combo.currentTextChanged.connect(self._refresh_active_table)
        self.platform_filter = QComboBox(); self.platform_filter.addItem("Tümü"); self.platform_filter.currentTextChanged.connect(self._apply_table_filters)
        self.filter_btn = QPushButton("Filtrele"); self.filter_btn.setObjectName("softBtn"); self.filter_btn.clicked.connect(self._apply_table_filters)
        self.sort_btn = QPushButton("Sırala"); self.sort_btn.setObjectName("softBtn"); self.sort_btn.clicked.connect(self._sort_table)
        self.row_search.returnPressed.connect(self._apply_table_filters)
        for w in [self.row_search, self.limit_combo, self.platform_filter, self.filter_btn, self.sort_btn]:
            tlay.addWidget(w)
        tlay.setStretch(0, 1)
        lay.addWidget(tb)

        self.grid = QTableWidget(0, 0)
        self.grid.setEditTriggers(QTableWidget.NoEditTriggers)
        self.grid.setAlternatingRowColors(True)
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        lay.addWidget(self.grid, 1)
        return page

    def _build_schema_page(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setSpacing(8)
        tb = QFrame(); tb.setObjectName("toolbarCard")
        tlay = QHBoxLayout(tb); tlay.setContentsMargins(8, 8, 8, 8); tlay.setSpacing(8)
        tlay.addWidget(QLabel("Şema Görselleştirici"))
        self.schema_combo = QComboBox(); self.schema_combo.addItem("schema = main")
        self.rel_combo = QComboBox(); self.rel_combo.addItems(["Tüm ilişkiler", "Sadece seçili tablo", "Kritik ilişkiler"])
        self.schema_search = QLineEdit(); self.schema_search.setPlaceholderText("Tablo veya kolon ara..."); self.schema_search.textChanged.connect(self._highlight_schema)
        self.auto_btn = QPushButton("Otomatik Yerleştir"); self.auto_btn.setObjectName("softBtn"); self.auto_btn.clicked.connect(self._layout_schema)
        for w in [self.schema_combo, self.rel_combo, self.schema_search, self.auto_btn]:
            tlay.addWidget(w)
        tlay.setStretch(3, 1)
        lay.addWidget(tb)

        wrap = QFrame(); wrap.setObjectName("schemaCanvasWrap")
        wlay = QVBoxLayout(wrap); wlay.setContentsMargins(6, 6, 6, 6)
        self.schema_view = SchemaView()
        wlay.addWidget(self.schema_view)
        lay.addWidget(wrap, 1)
        return page

    def _build_sql_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)
        self.sql_editor = QPlainTextEdit()
        self.sql_editor.setPlaceholderText("SELECT * FROM contracts LIMIT 100;")
        self.sql_editor.setStyleSheet("QPlainTextEdit { font-family: Consolas, 'Courier New', monospace; font-size: 13px; }")
        splitter.addWidget(self.sql_editor)

        result_wrap = QWidget()
        rlay = QVBoxLayout(result_wrap)
        self.sql_result = QTableWidget(0, 0)
        self.sql_result.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sql_result.verticalHeader().setVisible(False)
        self.sql_result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sql_result.setAlternatingRowColors(True)
        rlay.addWidget(self.sql_result, 1)
        splitter.addWidget(result_wrap)
        splitter.setSizes([260, 340])
        lay.addWidget(splitter, 1)

        bl = QHBoxLayout()
        self.sql_status_lbl = QLabel("")
        self.sql_status_lbl.setStyleSheet("color:#1f3b58;")
        bl.addWidget(self.sql_status_lbl, 1)
        self.sql_clear_btn = QPushButton("Temizle"); self.sql_clear_btn.setObjectName("softBtn"); self.sql_clear_btn.clicked.connect(self._clear_sql_terminal)
        self.sql_run_btn = QPushButton("Çalıştır"); self.sql_run_btn.setObjectName("primaryBtn"); self.sql_run_btn.clicked.connect(self._run_sql_terminal)
        bl.addWidget(self.sql_clear_btn)
        bl.addWidget(self.sql_run_btn)
        lay.addLayout(bl)
        return page

    def _set_page(self, page: str):
        self.tables_page.setVisible(page == "tables")
        self.schema_page.setVisible(page == "schema")
        self.sql_page.setVisible(page == "sql")
        self.sidebar.setVisible(page == "tables")
        self.rail_tables.setProperty("active", page == "tables")
        self.rail_schema.setProperty("active", page == "schema")
        self.rail_sql.setProperty("active", page == "sql")
        self.rail_tables.style().unpolish(self.rail_tables); self.rail_tables.style().polish(self.rail_tables)
        self.rail_schema.style().unpolish(self.rail_schema); self.rail_schema.style().polish(self.rail_schema)
        self.rail_sql.style().unpolish(self.rail_sql); self.rail_sql.style().polish(self.rail_sql)

    def refresh_all(self):
        self.stats = self.store.database_stats()
        _path = Path(str(self.stats.get("path", "database.sts")))
        self.table_names = sorted(list((self.stats.get("table_counts") or {}).keys()))
        self._refresh_sidebar()
        if not self.active_table and self.table_names:
            self.active_table = self.table_names[0]
        self._refresh_active_table()
        self._render_schema()

    def _refresh_sidebar(self):
        q = self.table_search.text().strip().lower()
        counts = self.stats.get("table_counts") or {}
        self.table_list.clear()
        for t in self.table_names:
            desc = TABLE_INFO.get(t, "")
            if q and q not in t.lower() and q not in desc.lower():
                continue
            item = QListWidgetItem(f"{t}\n{desc}  ({counts.get(t, 0)})")
            item.setData(Qt.UserRole, t)
            item.setToolTip(f"{t}\n{desc}\nKayıt: {counts.get(t, 0)}")
            self.table_list.addItem(item)
            if t == self.active_table:
                item.setSelected(True)

    def _on_table_selected(self):
        items = self.table_list.selectedItems()
        if not items:
            return
        self.active_table = str(items[0].data(Qt.UserRole) or "")
        self._refresh_active_table()
        self._highlight_schema()

    def _refresh_active_table(self):
        if not self.active_table:
            return
        try:
            limit = int(self.limit_combo.currentText())
        except Exception:
            limit = 100
        rows = self.store.preview_table(self.active_table, limit)
        cols = list(rows[0].keys()) if rows else self._table_columns(self.active_table)
        self._current_rows = list(rows or [])
        self._current_columns = list(cols or [])
        self._sort_column = None
        self._sort_ascending = True
        self._fill_table_grid(self._current_rows, self._current_columns)
        self._fill_platform_filter(cols, rows)
        self._apply_table_filters()

    def _fill_platform_filter(self, cols: List[str], rows: List[dict]):
        self.platform_filter.blockSignals(True)
        cur = self.platform_filter.currentText()
        self.platform_filter.clear()
        self.platform_filter.addItem("Tümü")
        if "platform" in cols:
            vals = sorted({str((r.get("platform") or "")).strip() for r in rows if str((r.get("platform") or "")).strip()})
            for v in vals:
                self.platform_filter.addItem(v)
        self.platform_filter.setVisible("platform" in cols)
        if cur and self.platform_filter.findText(cur) >= 0:
            self.platform_filter.setCurrentText(cur)
        self.platform_filter.blockSignals(False)

    def _apply_table_filters(self):
        q = self.row_search.text().strip().lower()
        pflt = self.platform_filter.currentText().strip()
        rows = list(self._current_rows)
        has_platform = "platform" in self._current_columns
        if q:
            rows = [r for r in rows if q in " | ".join(str(r.get(c, "")) for c in self._current_columns).lower()]
        if has_platform and pflt and pflt != "Tümü":
            rows = [r for r in rows if str(r.get("platform", "")) == pflt]
        if self._sort_column:
            rows = self._sorted_rows(rows, self._sort_column, self._sort_ascending)
        self._fill_table_grid(rows, self._current_columns)

    def _sort_table(self):
        if not self._current_columns:
            return
        current_idx = self.grid.currentColumn()
        if 0 <= current_idx < len(self._current_columns):
            target_col = self._current_columns[current_idx]
        else:
            target_col = "id" if "id" in self._current_columns else self._current_columns[0]
        if self._sort_column == target_col:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = target_col
            self._sort_ascending = True
        self._apply_table_filters()

    def _fill_table_grid(self, rows: List[dict], cols: List[str]):
        self.grid.setRowCount(len(rows))
        self.grid.setColumnCount(len(cols))
        self.grid.setHorizontalHeaderLabels(cols)
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                txt = str(row.get(col, ""))
                it = QTableWidgetItem(txt)
                it.setToolTip(txt)
                self.grid.setItem(r, c, it)

    @staticmethod
    def _sorted_rows(rows: List[dict], column: str, ascending: bool) -> List[dict]:
        def _key(row: dict):
            raw = str(row.get(column, "")).strip()
            try:
                return (0, float(raw.replace(",", ".")))
            except Exception:
                return (1, raw.lower())
        return sorted(rows, key=_key, reverse=not ascending)

    def _table_columns(self, table: str) -> List[str]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(r[1]) for r in rows]

    def _render_schema(self):
        scene = self.schema_view.scene()
        self._schema_rendering = True
        try:
            scene.clear()
            self.schema_cards.clear()
            self.schema_rel_lines = []
            counts = self.stats.get("table_counts") or {}
            tables = list(self.table_names)

            col_count = 4
            x_start, y_start = 40, 30
            x_step = 340
            y_gap = 52
            row_heights: List[float] = []
            max_x = 0.0
            max_y = 0.0

            for t in tables:
                cols = self._schema_columns(t)
                card_item = SchemaTableItem(t, int(counts.get(t, 0)), cols, self)
                scene.addItem(card_item)
                self.schema_cards[t] = card_item

            for idx, t in enumerate(tables):
                card_item = self.schema_cards[t]
                row = idx // col_count
                col = idx % col_count
                while len(row_heights) <= row:
                    row_heights.append(0.0)
                row_heights[row] = max(row_heights[row], card_item.boundingRect().height())
                y = y_start + sum(row_heights[:row]) + (row * y_gap)
                x = x_start + (col * x_step)
                card_item.setPos(x, y)
                max_x = max(max_x, x + card_item.boundingRect().width())
                max_y = max(max_y, y + card_item.boundingRect().height())
        finally:
            self._schema_rendering = False

        self._build_relation_lines()
        self._update_all_relation_lines()
        scene.setSceneRect(QRectF(0, 0, max(3000, max_x + 600), max(2200, max_y + 500)))

    def _schema_columns(self, table: str) -> List[Tuple[str, str, bool, bool]]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        fk_rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        fk_names = {str(r[3]) for r in fk_rows}
        return [(str(c[1]), str(c[2]), bool(c[5]), str(c[1]) in fk_names) for c in cols]

    def _schema_relations(self):
        rels = set()
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is not None:
            for t in self.table_names:
                try:
                    rows = conn.execute(f"PRAGMA foreign_key_list({t})").fetchall()
                except Exception:
                    rows = []
                for r in rows:
                    rels.add((str(r[2]), str(r[4]), t, str(r[3])))
        rels.update(FALLBACK_RELATIONS)
        if "component_platforms" in self.table_names:
            cols = {name for (name, _, _, _) in self._schema_columns("component_platforms")}
            if "component_id" in cols:
                rels.add(("components", "id", "component_platforms", "component_id"))
            if "component_name" in cols:
                rels.add(("components", "name", "component_platforms", "component_name"))
            if "platform_name" in cols:
                rels.add(("platforms", "name", "component_platforms", "platform_name"))
        return sorted(rels)

    def _relation_path(self, p1, p2):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath(p1)
        cx = (p1.x() + p2.x()) / 2.0
        path.cubicTo(cx, p1.y(), cx, p2.y(), p2.x(), p2.y())
        return path

    def _highlight_schema(self):
        q = self.schema_search.text().strip().lower()
        selected = self.active_table
        for t, card_item in self.schema_cards.items():
            card_item.setOpacity(1.0)
            if not q:
                card_item.update()
                continue
            cols = [c[0].lower() for c in self._schema_columns(t)]
            hit = q in t.lower() or any(q in c for c in cols)
            if selected and self.rel_combo.currentText() == "Sadece seçili tablo" and t != selected and hit:
                hit = False
            if not (hit or t == selected):
                card_item.setOpacity(0.35)
            card_item.update()

    def _layout_schema(self):
        self._render_schema()

    def _build_relation_lines(self):
        scene = self.schema_view.scene()
        self.schema_rel_lines = []
        for (src_t, src_c, dst_t, dst_c) in self._schema_relations():
            if src_t not in self.schema_cards or dst_t not in self.schema_cards:
                continue
            line = QGraphicsPathItem()
            pen = QPen(QColor("#8aa7cc"), 2.0, Qt.DashLine)
            line.setPen(pen)
            line.setZValue(-10)
            scene.addItem(line)
            rec = {"src": src_t, "dst": dst_t, "line": line}
            self.schema_rel_lines.append(rec)
            self._update_relation_line(rec)

    def _update_relation_line(self, rel):
        if rel["src"] not in self.schema_cards or rel["dst"] not in self.schema_cards:
            return
        a = self.schema_cards[rel["src"]].sceneBoundingRect()
        b = self.schema_cards[rel["dst"]].sceneBoundingRect()
        p1 = a.center()
        p2 = b.center()
        if a.center().x() <= b.center().x():
            p1.setX(a.right())
            p2.setX(b.left())
        else:
            p1.setX(a.left())
            p2.setX(b.right())
        rel["line"].setPath(self._relation_path(p1, p2))

    def _update_relation_lines_for_table(self, table: str):
        for rel in self.schema_rel_lines:
            if rel["src"] == table or rel["dst"] == table:
                self._update_relation_line(rel)

    def _update_all_relation_lines(self):
        for rel in self.schema_rel_lines:
            self._update_relation_line(rel)

    def _clear_sql_terminal(self):
        self.sql_editor.clear()
        self.sql_result.setRowCount(0)
        self.sql_result.setColumnCount(0)
        self.sql_status_lbl.setText("")

    def _run_sql_terminal(self):
        sql = self.sql_editor.toPlainText().strip()
        if not sql:
            return
        if not self._is_single_statement(sql):
            self._set_sql_status("Lütfen tek SQL komutu çalıştırın.", error=True)
            return
        op = self._sql_operation(sql)
        if not self._confirm_sql_operation(op):
            return
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            self._set_sql_status("SQL hatası: Veritabanı bağlantısı yok.", error=True)
            return
        started = time.perf_counter()
        changed = op not in {"SELECT", "PRAGMA", "WITH", "EXPLAIN"}
        try:
            cursor = conn.execute(sql)
            if op in {"SELECT", "PRAGMA", "WITH", "EXPLAIN"}:
                rows = cursor.fetchmany(1000)
                cols = [d[0] for d in (cursor.description or [])]
                self._show_sql_result(cols, rows)
                ms = int((time.perf_counter() - started) * 1000)
                self._set_sql_status(f"Çalışma süresi: {ms} ms | Satır: {len(rows)}")
                row_count = len(rows)
            else:
                conn.commit()
                row_count = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
                ms = int((time.perf_counter() - started) * 1000)
                self.sql_result.setRowCount(0); self.sql_result.setColumnCount(0)
                self._set_sql_status(f"Sorgu tamamlandı. Etkilenen satır: {row_count} | Çalışma süresi: {ms} ms")
                self.refresh_all()
            self.store._log("sql_query_executed", message="SQL Terminal sorgusu çalıştırıldı", payload={"operation": op, "duration_ms": ms, "changed": changed, "row_count": row_count})
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            self._set_sql_status(f"SQL hatası: {exc}", error=True)

    def _show_sql_result(self, cols, rows):
        self.sql_result.setRowCount(len(rows))
        self.sql_result.setColumnCount(len(cols))
        self.sql_result.setHorizontalHeaderLabels([str(c) for c in cols])
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                txt = str(row[col] if isinstance(row, dict) else row[c])
                self.sql_result.setItem(r, c, QTableWidgetItem(txt))

    def _is_single_statement(self, sql: str) -> bool:
        chunks = [s.strip() for s in sql.split(";") if s.strip()]
        return len(chunks) == 1

    def _sql_operation(self, sql: str) -> str:
        cleaned = re.sub(r"^\s*(--[^\n]*\n|/\*.*?\*/\s*)*", "", sql, flags=re.S).strip()
        token = cleaned.split(None, 1)[0].upper() if cleaned else ""
        return token

    def _confirm_sql_operation(self, op: str) -> bool:
        if op in {"SELECT", "PRAGMA", "WITH", "EXPLAIN"}:
            return True
        msg = "Bu işlem veriyi değiştirebilir. Devam edilsin mi?"
        if op in {"DROP", "ALTER", "VACUUM", "ATTACH", "DETACH", "REINDEX"}:
            msg = "Bu işlem veritabanı yapısını/veriyi değiştirebilir. Devam edilsin mi?"
        return QMessageBox.question(self, "SQL Terminal Onayı", msg) == QMessageBox.Yes

    def _set_sql_status(self, text: str, error: bool = False):
        self.sql_status_lbl.setText(text)
        self.sql_status_lbl.setStyleSheet("color:#dc2626;" if error else "color:#1f3b58;")

    def run_backup(self):
        base = Path(str(getattr(self.store, "path", "database.sts")))
        p, _ = QFileDialog.getSaveFileName(self, "Yedek Al", str(base.with_name(f"{base.stem}_backup.sts")), "STS (*.sts)")
        if not p:
            return
        res = self.store.backup_database(p)
        QMessageBox.information(self, "Yedek", f"Yedek oluşturuldu:\n{res.get('target_path')}")

    def run_optimize(self):
        if QMessageBox.question(self, "Onay", "Optimize işlemi çalıştırılsın mı?") != QMessageBox.Yes:
            return
        self.store.vacuum()
        self.store.optimize()
        self.refresh_all()

    @staticmethod
    def _fmt_count(v: int) -> str:
        v = int(v or 0)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v / 1_000:.1f}K"
        return str(v)
