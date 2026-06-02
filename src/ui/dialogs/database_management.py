from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QPainter, QCursor, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsTextItem,
    QGraphicsScene,
    QGraphicsView,
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
    QStackedWidget,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import STYLE
from src.ui.dialogs.schema_relationships import (
    compact_relationship_text,
    filter_relationship_groups,
    get_schema_relationships as read_schema_relationships,
    get_table_columns as read_table_columns,
    group_relationships_by_source,
    relationship_key,
    relationship_text,
)

TABLE_INFO = {
    "contracts": "Ana sözleşme ve SD kayıtları",
    "systems": "Sözleşmelere bağlı sistemler",
    "deliveries": "Kabul / teslimat kayıtları",
    "system_components": "Sistem bileşen adetleri",
    "delivery_components": "Kabul bazlı plan/teslim",
    "contract_tags": "Sözleşme etiket bağlantıları",
    "contract_files": "Sözleşmeye gömülü belgeler",
    "users": "Kullanıcı / kurum tanımları",
    "tags": "Etiket tanımları",
    "platforms": "Platform adları ve logolar",
    "components": "Tanımlı bileşenler",
    "activity_logs": "İşlem geçmişi",
    "component_platforms": "Bileşen platform yetkileri",
}


class SchemaView(QGraphicsView):
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
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

    def mousePressEvent(self, event):
        if self.itemAt(event.pos()) is None:
            self.dialog._clear_schema_selection()
        super().mousePressEvent(event)

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
    def __init__(self, table_name: str, count: int, cols: List[dict], dialog: "DatabaseManagementDialog"):
        super().__init__()
        self.table_name = table_name
        self.count = count
        self.cols = cols
        self.dialog = dialog
        self.card_width = 300
        self.header_height = 32
        self.row_height = 20
        visible_rows = max(1, len(cols))
        self.card_height = 10 + self.header_height + (visible_rows * self.row_height) + 10
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
        state = self.dialog._schema_card_state(self.table_name)
        painter.setPen(QPen(QColor("#3b82f6") if state == "focus" else QColor("#e2e8f0"), 2.0 if state == "focus" else 1.0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 8, 8)
        header_rect = QRectF(1, 1, rect.width() - 2, self.header_height)
        palette = ("#0f766e", "#1d4ed8", "#7c3aed", "#0369a1", "#047857")
        header_color = QColor(palette[sum(ord(char) for char in self.table_name) % len(palette)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(header_color)
        painter.drawRoundedRect(header_rect, 7, 7)
        painter.setPen(Qt.white)
        painter.drawText(QRectF(header_rect.left() + 10, header_rect.top(), header_rect.width() - 120, header_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, self.table_name)
        badge_rect = QRectF(header_rect.right() - 48, header_rect.top() + 7, 38, 18)
        painter.setBrush(QColor(255, 255, 255, 52))
        painter.drawRoundedRect(badge_rect, 9, 9)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, self.dialog._fmt_count(self.count))
        y = self.header_height + 16
        painter.setPen(QColor("#1f3b58"))
        fm = QFontMetrics(painter.font())
        for column in self.cols:
            col_name = column["name"]
            col_type = column["type"]
            pk = column["primary_key"]
            fk = column.get("foreign_key")
            badge = "PK" if pk else ("FK" if fk else "•")
            painter.setPen(QColor("#f59e0b") if pk else (QColor("#3b82f6") if fk else QColor("#94a3b8")))
            painter.drawText(QRectF(14, y, 24, 18), Qt.AlignVCenter | Qt.AlignLeft, badge)
            label = col_name if not fk else f"{col_name} → {fk['target_table']}.{fk['target_column']}"
            painter.setPen(QColor("#312e81") if fk else QColor("#1f3b58"))
            painter.drawText(QRectF(38, y, 184, 18), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(label, Qt.ElideRight, 180))
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(rect.width() - 72, y, 62, 18), Qt.AlignVCenter | Qt.AlignRight, fm.elidedText(col_type, Qt.ElideRight, 58))
            y += self.row_height
        if self.isSelected():
            painter.setPen(QPen(QColor("#3b82f6"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

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
            if bool(value) and not getattr(self.dialog, "_schema_rendering", False):
                self.dialog._select_schema_table(self.table_name)
        return super().itemChange(change, value)

    def column_scene_y(self, column_name: str):
        for index, column in enumerate(self.cols):
            if column["name"] == column_name:
                return self.scenePos().y() + self.header_height + 16 + (index * self.row_height) + 9
        return self.sceneBoundingRect().center().y()

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
        self.schema_relationships: List[dict] = []
        self.selected_schema_table: str = ""
        self.selected_relationship = None
        self._schema_rendering = False

        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        QTimer.singleShot(0, self.showMaximized)
        self.refresh_all()

    def apply_database_editor_styles(self) -> str:
        return """
/* ── Temel ── */
QDialog#databaseEditorDialog { background:#f1f5f9; }

/* ── Top Bar ── */
QFrame#topBar { background:#0d1e33; border:0; border-bottom:1px solid #162840; }
QLabel#titleBadge {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    color:#ffffff; border-radius:8px; padding:5px 9px; font-size:11px; font-weight:900;
}
QLabel#topTitle { color:#94b8d8; font-size:13px; font-weight:600; letter-spacing:0.3px; }
QFrame#topSeparator { background:#1e3654; border:0; }
QPushButton#topTab {
    background:transparent; border:0; border-bottom:3px solid transparent;
    border-radius:0; color:#5b85a8; padding:0 22px; font-size:13px; font-weight:600;
}
QPushButton#topTab:hover { background:rgba(255,255,255,0.04); color:#a8c8e8; }
QPushButton#topTab[active='true'] {
    color:#e8f2ff; border-bottom:3px solid #3b82f6;
    background:rgba(59,130,246,0.07);
    font-weight:700;
}
QLabel { background:transparent; }

/* ── Sidebar ── */
QFrame#tableSidebar { background:#ffffff; border:0; border-right:1px solid #e8edf5; }
QListWidget#tableList { background:#ffffff; border:0; outline:0; font-size:12px; }
QListWidget#tableList::item {
    border:0;
    border-left:3px solid transparent;
    border-bottom:1px solid #f0f4fa;
    padding:9px 14px;
    color:#374151;
    font-size:12px;
    font-weight:500;
}
QListWidget#tableList::item:hover {
    background:#f0f5ff;
    color:#1e40af;
    border-left:3px solid #93c5fd;
    border-bottom:1px solid #f0f4fa;
}
QListWidget#tableList::item:selected {
    background:#dbeafe;
    border-left:3px solid #2563eb;
    border-bottom:1px solid #bcd3f5;
    color:#1e40af;
    font-weight:700;
}

/* ── Toolbar ── */
QFrame#toolbarCard {
    background:#ffffff; border:0;
    border-bottom:1px solid #e8edf5;
}
QLineEdit, QComboBox {
    background:#f8fafc; border:1px solid #dde5ef;
    border-radius:7px; padding:6px 10px; color:#334155;
    font-size:12px;
}
QLineEdit:focus, QComboBox:focus { border-color:#3b82f6; background:#ffffff; }
QPushButton#softBtn {
    background:#ffffff; border:1px solid #dde5ef; color:#475569;
    border-radius:7px; padding:6px 12px; font-size:12px; font-weight:600;
}
QPushButton#softBtn:hover { background:#f1f5f9; border-color:#c0cfe0; color:#1e293b; }
QPushButton#primaryBtn {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
    border:0; color:#ffffff; border-radius:7px; padding:6px 16px;
    font-size:12px; font-weight:700;
}
QPushButton#primaryBtn:hover { background:#1d4ed8; }

/* ── Data Table ── */
QFrame#tableMain { background:#ffffff; border:0; }
QTableWidget {
    background:#ffffff; border:0;
    gridline-color:#edf0f7;
    alternate-background-color:#fafbfe;
    selection-background-color:#eff6ff; selection-color:#1e293b;
    font-size:12px;
}
QHeaderView::section {
    background:#f4f7fc; border:0;
    border-right:1px solid #e8edf5; border-bottom:2px solid #dde5ef;
    padding:7px 10px; color:#475569; font-size:11px; font-weight:700;
    letter-spacing:0.3px; text-transform:uppercase;
}
QLabel#tableStatus { color:#64748b; font-size:11px; padding:5px 14px; background:#f8fafc; border-top:1px solid #e8edf5; }

/* ── Schema / Relations ── */
QFrame#schemaCanvasWrap { background:#edf2f8; border:0; }
QFrame#relationPanel {
    background:#fafbfe; border:0; border-left:1px solid #e2e8f2;
}
QLabel#relationTitle { color:#1e293b; font-size:12px; font-weight:800; letter-spacing:0.3px; text-transform:uppercase; }
QScrollArea#relationScroll { border:0; background:#ffffff; }
QWidget#relationScrollBody { background:#ffffff; }
QFrame#relationGroupCard { background:#ffffff; border:0; border-bottom:1px solid #f1f5f9; }
QPushButton#relationGroupHeader {
    background:transparent; border:0; color:#1e293b;
    padding:6px 4px; text-align:left; font-size:12px; font-weight:700;
}
QPushButton#relationGroupHeader:hover { color:#2563eb; }
QPushButton#relationGroupHeader[active='true'] { color:#2563eb; }
QPushButton#relationRow {
    background:transparent; border:0; color:#64748b;
    padding:3px 6px; text-align:left; font-size:11px;
}
QPushButton#relationRow:hover { background:#f0f6ff; color:#2563eb; border-radius:4px; }
QPushButton#relationRow[selected='true'] {
    background:#eff6ff; color:#1d4ed8; border-radius:4px;
}

/* ── SQL Terminal ── */
QPlainTextEdit#sqlEditor {
    background:#1a1b2e; border:0;
    border-bottom:2px solid #12131f;
    padding:16px 18px; color:#c9d1f5;
    font-family:Consolas, 'Cascadia Code', 'Courier New', monospace;
    font-size:13px; line-height:1.6;
    selection-background-color:#2d2f5e;
}
QFrame#sqlResultPanel { background:#ffffff; border:0; border-top:1px solid #e8edf5; }
QLabel#sqlResultTitle { color:#334155; font-size:12px; font-weight:700; }
QLabel#sqlResultBadge {
    background:#dcfce7; color:#166534; border-radius:6px;
    padding:2px 9px; font-size:11px; font-weight:700;
}
QFrame#sqlFooter {
    background:#f8fafc; border:0; border-top:1px solid #e8edf5;
}
QLabel#sqlHint { color:#94a3b8; font-size:11px; }
"""

    def _local_style(self) -> str:
        return self.apply_database_editor_styles()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_topbar())
        self.page_stack = QStackedWidget()
        self.tables_page = self.build_tables_tab()
        self.schema_page = self.build_relationships_tab()
        self.sql_page = self.build_sql_tab()
        self.page_stack.addWidget(self.tables_page)
        self.page_stack.addWidget(self.schema_page)
        self.page_stack.addWidget(self.sql_page)
        root.addWidget(self.page_stack, 1)
        self.switch_database_tab("tables")

    def _make_tab_button(self, icon_svg: str, label: str, page: str) -> QPushButton:
        """İkon (SVG) + yazı yan yana, tek QPushButton olarak oluşturur."""
        btn = QPushButton()
        btn.setObjectName("topTab")
        btn.setFixedHeight(58)
        # İkon SVG'yi QPixmap'e çevirip QIcon olarak ata
        from PySide6.QtGui import QPixmap, QIcon
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPainter
        px = QPixmap(18, 18)
        px.fill(Qt.transparent)
        renderer = QSvgRenderer(QByteArray(icon_svg.encode()))
        painter = QPainter(px)
        renderer.render(painter)
        painter.end()
        btn.setIcon(QIcon(px))
        btn.setIconSize(px.size())
        btn.setText(f"  {label}")
        btn.setMinimumWidth(140)
        btn.clicked.connect(lambda _=False, p=page: self.switch_database_tab(p))
        return btn

    def build_topbar(self):
        bar = QFrame(); bar.setObjectName("topBar"); bar.setFixedHeight(58)
        lay = QHBoxLayout(bar); lay.setContentsMargins(16, 0, 12, 0); lay.setSpacing(0)
        logo = QLabel("DB"); logo.setObjectName("titleBadge"); logo.setAlignment(Qt.AlignCenter); logo.setFixedSize(34, 34)
        title = QLabel("STS Database Editor"); title.setObjectName("topTitle")
        sep = QFrame(); sep.setObjectName("topSeparator"); sep.setFixedSize(1, 24)
        lay.addWidget(logo); lay.addSpacing(10); lay.addWidget(title); lay.addSpacing(18); lay.addWidget(sep); lay.addSpacing(6)

        _ICON_TABLES = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#6f9dca" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/>'
            '<line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/>'
            '</svg>'
        )
        _ICON_RELATIONS = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#6f9dca" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/>'
            '<line x1="7" y1="12" x2="17" y2="6"/><line x1="7" y1="12" x2="17" y2="18"/>'
            '</svg>'
        )
        _ICON_SQL = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#6f9dca" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>'
            '</svg>'
        )

        self.top_tabs = {}
        for name, icon_svg, label in (
            ("tables",  _ICON_TABLES,    "Tablolar"),
            ("schema",  _ICON_RELATIONS, "İlişkiler"),
            ("sql",     _ICON_SQL,       "SQL Terminali"),
        ):
            tab = self._make_tab_button(icon_svg, label, name)
            lay.addWidget(tab)
            self.top_tabs[name] = tab
        lay.addStretch(1)
        return bar

    def _build_topbar(self):
        return self.build_topbar()

    def build_tables_tab(self):
        page = QWidget(); body = QHBoxLayout(page); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("tableSidebar"); sidebar.setFixedWidth(230)
        slay = QVBoxLayout(sidebar); slay.setContentsMargins(0, 0, 0, 0); slay.setSpacing(0)
        # Sidebar header
        sidebar_head = QWidget(); sidebar_head.setStyleSheet("background:#f4f7fc; border-bottom:1px solid #e2e8f2;")
        sh_lay = QVBoxLayout(sidebar_head); sh_lay.setContentsMargins(14, 12, 14, 8); sh_lay.setSpacing(6)
        sidebar_title = QLabel("TABLOLAR"); sidebar_title.setStyleSheet("color:#475569; font-size:10px; font-weight:800; letter-spacing:1px; background:transparent;")
        sh_lay.addWidget(sidebar_title)
        self.table_search = QLineEdit(); self.table_search.setPlaceholderText("Tablo ara..."); self.table_search.textChanged.connect(self._refresh_sidebar)
        sh_lay.addWidget(self.table_search)
        slay.addWidget(sidebar_head)
        self.table_list = QListWidget(); self.table_list.setObjectName("tableList"); self.table_list.itemSelectionChanged.connect(self._on_table_selected); slay.addWidget(self.table_list, 1)
        body.addWidget(sidebar)
        main = QFrame(); main.setObjectName("tableMain"); mlay = QVBoxLayout(main); mlay.setContentsMargins(0, 0, 0, 0); mlay.setSpacing(0)
        tb = QFrame(); tb.setObjectName("toolbarCard"); tlay = QHBoxLayout(tb); tlay.setContentsMargins(14, 8, 14, 8); tlay.setSpacing(8)
        self.row_search = QLineEdit(); self.row_search.setPlaceholderText("Satır ara / filtrele..."); self.row_search.textChanged.connect(self._apply_table_filters); self.row_search.returnPressed.connect(self._apply_table_filters)
        self.limit_combo = QComboBox(); self.limit_combo.addItems(["100", "250", "500"]); self.limit_combo.currentTextChanged.connect(self._refresh_active_table)
        self.platform_filter = QComboBox(); self.platform_filter.addItem("Tümü"); self.platform_filter.currentTextChanged.connect(self._apply_table_filters)
        self.filter_btn = QPushButton("Filtrele"); self.filter_btn.setObjectName("softBtn"); self.filter_btn.clicked.connect(self._apply_table_filters)
        self.sort_btn = QPushButton("Sırala"); self.sort_btn.setObjectName("softBtn"); self.sort_btn.clicked.connect(self._sort_table)
        for widget in (self.row_search, self.limit_combo, self.platform_filter, self.filter_btn, self.sort_btn): tlay.addWidget(widget)
        tlay.setStretch(0, 1); mlay.addWidget(tb)
        self.grid = QTableWidget(0, 0); self.grid.setEditTriggers(QTableWidget.NoEditTriggers); self.grid.setAlternatingRowColors(True); self.grid.verticalHeader().setVisible(False); self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); self.grid.setTextElideMode(Qt.ElideRight)
        mlay.addWidget(self.grid, 1)
        self.table_status_lbl = QLabel(""); self.table_status_lbl.setObjectName("tableStatus"); self.table_status_lbl.setContentsMargins(14, 5, 14, 5); mlay.addWidget(self.table_status_lbl)
        body.addWidget(main, 1)
        return page

    def _build_tables_page(self):
        return self.build_tables_tab()

    def build_relationships_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        tb = QFrame(); tb.setObjectName("toolbarCard"); tlay = QHBoxLayout(tb); tlay.setContentsMargins(14, 8, 14, 8); tlay.setSpacing(8)
        self.schema_search = QLineEdit(); self.schema_search.setPlaceholderText("Tablo, kolon veya ilişki ara..."); self.schema_search.textChanged.connect(self._on_schema_search_changed)
        self.auto_btn = QPushButton("Otomatik Yerleştir"); self.auto_btn.setObjectName("primaryBtn"); self.auto_btn.clicked.connect(self._layout_schema)
        tlay.addWidget(self.schema_search, 1); tlay.addWidget(self.auto_btn); lay.addWidget(tb)
        wrap = QFrame(); wrap.setObjectName("schemaCanvasWrap"); wlay = QVBoxLayout(wrap); wlay.setContentsMargins(0, 0, 0, 0)
        self.schema_view = SchemaView(self); wlay.addWidget(self.schema_view)
        relation_panel = QFrame(); relation_panel.setObjectName("relationPanel"); relation_panel.setFixedWidth(230)
        relation_lay = QVBoxLayout(relation_panel); relation_lay.setContentsMargins(10, 10, 10, 10); relation_lay.setSpacing(8)
        relation_title = QLabel("İlişki Listesi"); relation_title.setObjectName("relationTitle"); relation_lay.addWidget(relation_title)
        self.relation_search = QLineEdit(); self.relation_search.setPlaceholderText("İlişki ara..."); self.relation_search.textChanged.connect(self._refresh_relationship_list); relation_lay.addWidget(self.relation_search)
        self.relation_scroll = QScrollArea(); self.relation_scroll.setObjectName("relationScroll"); self.relation_scroll.setWidgetResizable(True); self.relation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.relation_scroll_body = QWidget(); self.relation_scroll_body.setObjectName("relationScrollBody")
        self.relation_groups_layout = QVBoxLayout(self.relation_scroll_body); self.relation_groups_layout.setContentsMargins(0, 0, 0, 0); self.relation_groups_layout.setSpacing(2); self.relation_groups_layout.addStretch(1)
        self.relation_scroll.setWidget(self.relation_scroll_body); relation_lay.addWidget(self.relation_scroll, 1)
        splitter = QSplitter(Qt.Horizontal); splitter.addWidget(wrap); splitter.addWidget(relation_panel); splitter.setSizes([1180, 230]); lay.addWidget(splitter, 1)
        return page

    def _build_schema_page(self):
        return self.build_relationships_tab()

    def build_sql_tab(self):
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        splitter = QSplitter(Qt.Vertical)
        self.sql_editor = QPlainTextEdit(); self.sql_editor.setObjectName("sqlEditor"); self.sql_editor.setPlainText("SELECT * FROM contracts LIMIT 100;"); self.sql_editor.setMinimumHeight(210)
        splitter.addWidget(self.sql_editor)
        result_panel = QFrame(); result_panel.setObjectName("sqlResultPanel"); rlay = QVBoxLayout(result_panel); rlay.setContentsMargins(0, 0, 0, 0); rlay.setSpacing(0)
        head = QWidget(); head.setStyleSheet("background:#f8fafc; border-bottom:1px solid #e8edf5;"); hlay = QHBoxLayout(head); hlay.setContentsMargins(14, 8, 14, 8)
        title = QLabel("Sonuçlar"); title.setObjectName("sqlResultTitle"); self.sql_result_badge = QLabel("0 satır · 0ms"); self.sql_result_badge.setObjectName("sqlResultBadge")
        hint = QLabel("Ctrl+Enter ile çalıştır"); hint.setObjectName("sqlHint"); hlay.addWidget(title); hlay.addWidget(self.sql_result_badge); hlay.addStretch(1); hlay.addWidget(hint); rlay.addWidget(head)
        self.sql_result = QTableWidget(0, 0); self.sql_result.setEditTriggers(QTableWidget.NoEditTriggers); self.sql_result.verticalHeader().setVisible(False); self.sql_result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); self.sql_result.setAlternatingRowColors(True); self.sql_result.setTextElideMode(Qt.ElideRight); rlay.addWidget(self.sql_result, 1)
        splitter.addWidget(result_panel); splitter.setSizes([360, 300]); lay.addWidget(splitter, 1)
        footer = QFrame(); footer.setObjectName("sqlFooter"); flay = QHBoxLayout(footer); flay.setContentsMargins(14, 7, 14, 7)
        self.sql_status_lbl = QLabel("  Ctrl+Enter → Çalıştır   ·   Ctrl+L → Temizle"); self.sql_status_lbl.setObjectName("sqlHint"); flay.addWidget(self.sql_status_lbl, 1)
        self.sql_clear_btn = QPushButton("Temizle"); self.sql_clear_btn.setObjectName("softBtn"); self.sql_clear_btn.clicked.connect(self._clear_sql_terminal)
        self.sql_run_btn = QPushButton("Çalıştır"); self.sql_run_btn.setObjectName("primaryBtn"); self.sql_run_btn.clicked.connect(self._run_sql_terminal)
        flay.addWidget(self.sql_clear_btn); flay.addWidget(self.sql_run_btn); lay.addWidget(footer)
        self.sql_shortcuts = []
        for sequence, handler in (("Ctrl+Return", self._run_sql_terminal), ("Ctrl+Enter", self._run_sql_terminal), ("Ctrl+L", self._clear_sql_terminal)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self.sql_shortcuts.append(shortcut)
        return page

    def _build_sql_page(self):
        return self.build_sql_tab()

    def switch_database_tab(self, page: str):
        from PySide6.QtGui import QPixmap, QIcon, QPainter
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        _ICONS = {
            "tables": (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/>'
                '<line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/>'
                '</svg>'
            ),
            "schema": (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/>'
                '<line x1="7" y1="12" x2="17" y2="6"/><line x1="7" y1="12" x2="17" y2="18"/>'
                '</svg>'
            ),
            "sql": (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>'
                '</svg>'
            ),
        }
        indexes = {"tables": 0, "schema": 1, "sql": 2}
        page = page if page in indexes else "tables"
        self.page_stack.setCurrentIndex(indexes[page])
        for name, tab in self.top_tabs.items():
            active = name == page
            tab.setProperty("active", active)
            tab.style().unpolish(tab); tab.style().polish(tab)
            color = "#ffffff" if active else "#6f9dca"
            svg = _ICONS.get(name, "").replace("{c}", color)
            px = QPixmap(18, 18); px.fill(Qt.transparent)
            renderer = QSvgRenderer(QByteArray(svg.encode()))
            painter = QPainter(px); renderer.render(painter); painter.end()
            tab.setIcon(QIcon(px)); tab.setIconSize(px.size())

    def _set_page(self, page: str):
        self.switch_database_tab(page)

    def refresh_all(self):
        self.stats = self.store.database_stats()
        self.table_names = sorted(list((self.stats.get("table_counts") or {}).keys()))
        if not self.active_table and self.table_names:
            self.active_table = self.table_names[0]
        self._refresh_sidebar()
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
            cnt = counts.get(t, 0)
            label = f"{t}  ·  {cnt}"
            if desc:
                label += f"\n{desc}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, t)
            item.setToolTip(f"{t}\n{desc}\nKayıt: {cnt}")
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
        if hasattr(self, "table_status_lbl"):
            total = int((self.stats.get("table_counts") or {}).get(self.active_table, len(self._current_rows)))
            limit = self.limit_combo.currentText()
            self.table_status_lbl.setText(f"{self.active_table} · {total} satır · {limit} gösteriliyor")

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
            x_step = 330
            y_gap = 52
            row_heights: List[float] = []
            max_x = 0.0
            max_y = 0.0
            self.schema_relationships = self.get_schema_relationships()

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
        self._refresh_relationship_list()
        self._apply_schema_focus()
        scene.setSceneRect(QRectF(0, 0, max(3000, max_x + 600), max(2200, max_y + 500)))

    def get_table_columns(self, table: str) -> List[dict]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        return read_table_columns(conn, table)

    def get_schema_relationships(self) -> List[dict]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        return read_schema_relationships(conn, self.table_names)

    def _schema_columns(self, table: str) -> List[dict]:
        by_source = {
            relationship["source_column"]: relationship
            for relationship in self.schema_relationships
            if relationship["source_table"] == table
        }
        columns = self.get_table_columns(table)
        for column in columns:
            column["foreign_key"] = by_source.get(column["name"])
        return columns

    def _relation_path(self, p1, p2):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath(p1)
        cx = (p1.x() + p2.x()) / 2.0
        path.cubicTo(cx, p1.y(), cx, p2.y(), p2.x(), p2.y())
        return path

    def _schema_card_state(self, table: str) -> str:
        if not self.selected_schema_table and not self.selected_relationship:
            return "normal"
        related = self._focused_tables()
        return "focus" if table in related else "dim"

    def _focused_tables(self) -> set[str]:
        if self.selected_relationship:
            return {self.selected_relationship["source_table"], self.selected_relationship["target_table"]}
        if self.selected_schema_table:
            related = {self.selected_schema_table}
            for relationship in self.schema_relationships:
                if relationship["source_table"] == self.selected_schema_table or relationship["target_table"] == self.selected_schema_table:
                    related.update([relationship["source_table"], relationship["target_table"]])
            return related
        return set()

    def _select_schema_table(self, table: str):
        self.selected_schema_table = str(table or "")
        self.selected_relationship = None
        for name, card in self.schema_cards.items():
            card.setSelected(name == self.selected_schema_table)
        self._refresh_relationship_list()
        self._apply_schema_focus()

    def _clear_schema_selection(self):
        self.selected_schema_table = ""
        self.selected_relationship = None
        for card in self.schema_cards.values():
            card.setSelected(False)
        self._refresh_relationship_list()
        self._apply_schema_focus()

    def _on_relationship_selected(self, key):
        self.selected_relationship = next((rel for rel in self.schema_relationships if relationship_key(rel) == key), None)
        self.selected_schema_table = ""
        for card in self.schema_cards.values():
            card.setSelected(False)
        self._refresh_relationship_list()
        self._apply_schema_focus()

    def _clear_relationship_group_cards(self):
        if not hasattr(self, "relation_groups_layout"):
            return
        while self.relation_groups_layout.count() > 1:
            item = self.relation_groups_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_relationship_list(self):
        if not hasattr(self, "relation_groups_layout"):
            return
        groups = group_relationships_by_source(self.schema_relationships)
        for query in (self.schema_search.text(), self.relation_search.text()):
            groups = filter_relationship_groups(groups, query)
        selected_key = relationship_key(self.selected_relationship) if self.selected_relationship else None
        self._clear_relationship_group_cards()
        for source_table, relationships in groups.items():
            card = QFrame(); card.setObjectName("relationGroupCard")
            card_lay = QVBoxLayout(card); card_lay.setContentsMargins(4, 4, 4, 4); card_lay.setSpacing(1)
            header = QPushButton(f"{source_table} · {len(relationships)} ilişki"); header.setObjectName("relationGroupHeader")
            header.setProperty("active", source_table == self.selected_schema_table); header.setToolTip(f"{source_table} tablosunu ve bağlı tabloları vurgula")
            header.clicked.connect(lambda _checked=False, table=source_table: self._select_schema_table(table))
            card_lay.addWidget(header)
            for relationship in relationships:
                key = relationship_key(relationship)
                full_text = relationship_text(relationship)
                row = QPushButton(compact_relationship_text(relationship)); row.setObjectName("relationRow")
                row.setProperty("selected", key == selected_key); row.setToolTip(f"{full_text}\nON DELETE {relationship['on_delete']} | ON UPDATE {relationship['on_update']}")
                row.clicked.connect(lambda _checked=False, rel_key=key: self._on_relationship_selected(rel_key))
                card_lay.addWidget(row)
            self.relation_groups_layout.insertWidget(self.relation_groups_layout.count() - 1, card)

    def _on_schema_search_changed(self):
        self._refresh_relationship_list()
        self._apply_schema_focus()

    def _highlight_schema(self):
        self._apply_schema_focus()

    def _apply_schema_focus(self):
        query = self.schema_search.text().strip().casefold() if hasattr(self, "schema_search") else ""
        focused_tables = self._focused_tables()
        for table, card in self.schema_cards.items():
            columns = [column["name"].casefold() for column in self._schema_columns(table)]
            search_hit = not query or query in table.casefold() or any(query in column for column in columns)
            focus_hit = not focused_tables or table in focused_tables
            card.setOpacity(1.0 if search_hit and focus_hit else 0.25)
            card.update()
        for rec in self.schema_rel_lines:
            relationship = rec["relationship"]
            is_selected = bool(self.selected_relationship and relationship_key(relationship) == relationship_key(self.selected_relationship))
            touches_table = bool(self.selected_schema_table and self.selected_schema_table in {relationship["source_table"], relationship["target_table"]})
            strong = is_selected or touches_table
            rec["line"].setVisible(True)
            rec["label"].setVisible(True)
            rec["line"].setPen(QPen(QColor("#2563eb") if strong else QColor("#9db2cf"), 3.0 if strong else 1.2, Qt.SolidLine if strong else Qt.DashLine))
            rec["line"].setOpacity(1.0 if strong else (0.38 if focused_tables else 0.55))
            rec["label"].setOpacity(1.0 if strong else (0.35 if focused_tables else 0.7))

    def _layout_schema(self):
        self._render_schema()

    def _build_relation_lines(self):
        scene = self.schema_view.scene()
        self.schema_rel_lines = []
        for relationship in self.schema_relationships:
            source_table = relationship["source_table"]
            target_table = relationship["target_table"]
            if source_table not in self.schema_cards or target_table not in self.schema_cards:
                continue
            line = QGraphicsPathItem()
            line.setPen(QPen(QColor("#9db2cf"), 1.2, Qt.DashLine))
            line.setZValue(-10)
            scene.addItem(line)
            label = QGraphicsTextItem()
            text = relationship_text(relationship)
            label.setHtml(f"<div style='background:#ffffff;color:#31557b;font-size:9px;padding:2px;'>{text}</div>")
            label.setToolTip(f"{text}\nON DELETE {relationship['on_delete']} | ON UPDATE {relationship['on_update']}")
            label.setZValue(-5)
            scene.addItem(label)
            rec = {"src": source_table, "dst": target_table, "line": line, "label": label, "relationship": relationship}
            self.schema_rel_lines.append(rec)
            self._update_relation_line(rec)

    def _update_relation_line(self, rel):
        relationship = rel["relationship"]
        if rel["src"] not in self.schema_cards or rel["dst"] not in self.schema_cards:
            return
        source_card = self.schema_cards[rel["src"]]
        target_card = self.schema_cards[rel["dst"]]
        a = source_card.sceneBoundingRect()
        b = target_card.sceneBoundingRect()
        p1 = a.center(); p1.setY(source_card.column_scene_y(relationship["source_column"]))
        p2 = b.center(); p2.setY(target_card.column_scene_y(relationship["target_column"]))
        if a.center().x() <= b.center().x():
            p1.setX(a.right()); p2.setX(b.left())
        else:
            p1.setX(a.left()); p2.setX(b.right())
        rel["line"].setPath(self._relation_path(p1, p2))
        bounds = rel["line"].path().boundingRect()
        label_bounds = rel["label"].boundingRect()
        rel["label"].setPos(bounds.center().x() - (label_bounds.width() / 2), bounds.center().y() - (label_bounds.height() / 2))

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
        self.sql_status_lbl.setText("Ctrl+Enter → Çalıştır · Ctrl+L → Temizle")
        self.sql_result_badge.setText("0 satır · 0ms")

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
                self.sql_result_badge.setText(f"{row_count} satır · {ms}ms")
            else:
                conn.commit()
                row_count = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
                ms = int((time.perf_counter() - started) * 1000)
                self.sql_result.setRowCount(0); self.sql_result.setColumnCount(0)
                self.sql_result_badge.setText(f"{row_count} satır · {ms}ms")
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

    @staticmethod
    def _fmt_count(v: int) -> str:
        v = int(v or 0)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v / 1_000:.1f}K"
        return str(v)
