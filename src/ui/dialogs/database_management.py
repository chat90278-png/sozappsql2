from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsProxyWidget,
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
    ("contracts", "id", "systems", "contract_id"),
    ("contracts", "id", "deliveries", "contract_id"),
    ("systems", "id", "system_components", "system_id"),
    ("deliveries", "id", "delivery_components", "delivery_id"),
    ("contracts", "id", "contract_tags", "contract_id"),
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


class DatabaseManagementDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("databaseEditorDialog")
        self.setWindowTitle("Database Yönetimi - STS")
        self.resize(1400, 820)
        self.setMinimumSize(1100, 680)

        self.stats: Dict = {}
        self.table_names: List[str] = []
        self.active_table: str = ""
        self.schema_cards: Dict[str, QGraphicsProxyWidget] = {}

        self.setStyleSheet(STYLE + self._local_style())
        self._build()
        self.refresh_all()

    def _local_style(self) -> str:
        return """
QDialog#databaseEditorDialog { background:#eef4fb; }
QFrame#topBar { background:#ffffff; border:1px solid #d8e4f2; border-radius:12px; }
QLabel#titleBadge { background:#2563eb; color:white; border-radius:10px; padding:4px 8px; font-weight:800; }
QLabel#topTitle { color:#0f2742; font-size:15px; font-weight:800; }
QLabel#pathLabel { color:#6b7f98; font-size:12px; background:transparent; }
QLabel#connOk { background:#dcfce7; color:#166534; border:1px solid #bbf7d0; border-radius:10px; padding:6px 10px; font-weight:700; }

QFrame#iconRail, QFrame#sidePanel, QFrame#mainPanel, QFrame#toolbarCard { background:#ffffff; border:1px solid #d8e4f2; border-radius:12px; }
QPushButton#railBtn { background:transparent; border:none; border-radius:10px; padding:10px; color:#4b607a; font-weight:700; }
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

QFrame#schemaCanvasWrap { background:#edf3fa; border:1px solid #d8e4f2; border-radius:10px; }
QFrame#schemaCard { background:#ffffff; border:1px solid #cfdcf0; border-radius:10px; }
QLabel#schemaCardTitle { background:#2563eb; color:white; border-radius:8px; padding:5px 8px; font-weight:800; }
QLabel#schemaCol { color:#1f3b58; font-size:11px; background:transparent; }
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
        self._set_page("tables")

    def _build_topbar(self):
        bar = QFrame(); bar.setObjectName("topBar")
        lay = QHBoxLayout(bar); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(10)
        left = QHBoxLayout()
        b = QLabel("DB"); b.setObjectName("titleBadge")
        self.top_title = QLabel("STS Database Editor"); self.top_title.setObjectName("topTitle")
        left.addWidget(b); left.addWidget(self.top_title)
        lay.addLayout(left)

        self.path_lbl = QLabel("-")
        self.path_lbl.setObjectName("pathLabel")
        self.path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.path_lbl, 1)

        self.conn_lbl = QLabel("● SQLite bağlantısı aktif")
        self.conn_lbl.setObjectName("connOk")
        lay.addWidget(self.conn_lbl)

        self.backup_btn = QPushButton("Yedek Al"); self.backup_btn.setObjectName("softBtn"); self.backup_btn.clicked.connect(self.run_backup)
        self.opt_btn = QPushButton("Optimize"); self.opt_btn.setObjectName("softBtn"); self.opt_btn.clicked.connect(self.run_optimize)
        self.refresh_btn = QPushButton("Yenile"); self.refresh_btn.setObjectName("primaryBtn"); self.refresh_btn.clicked.connect(self.refresh_all)
        lay.addWidget(self.backup_btn); lay.addWidget(self.opt_btn); lay.addWidget(self.refresh_btn)
        return bar

    def _build_rail(self):
        rail = QFrame(); rail.setObjectName("iconRail"); rail.setFixedWidth(64)
        lay = QVBoxLayout(rail); lay.setContentsMargins(8, 12, 8, 12); lay.setSpacing(8)
        self.rail_tables = QPushButton("▦"); self.rail_tables.setObjectName("railBtn"); self.rail_tables.clicked.connect(lambda: self._set_page("tables"))
        self.rail_schema = QPushButton("⟲"); self.rail_schema.setObjectName("railBtn"); self.rail_schema.clicked.connect(lambda: self._set_page("schema"))
        lay.addWidget(self.rail_tables)
        lay.addWidget(self.rail_schema)
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
        self.filter_btn = QPushButton("Filtre"); self.filter_btn.setObjectName("softBtn"); self.filter_btn.clicked.connect(self._apply_table_filters)
        self.sort_btn = QPushButton("Sırala"); self.sort_btn.setObjectName("softBtn"); self.sort_btn.clicked.connect(self._sort_table)
        self.table_refresh_btn = QPushButton("Yenile"); self.table_refresh_btn.setObjectName("softBtn"); self.table_refresh_btn.clicked.connect(self._refresh_active_table)
        self.cols_btn = QPushButton("Kolonlar"); self.cols_btn.setObjectName("softBtn"); self.cols_btn.clicked.connect(self._show_columns)
        self.add_btn = QPushButton("+ Satır Ekle"); self.add_btn.setObjectName("warnBtn"); self.add_btn.clicked.connect(lambda: QMessageBox.information(self, "Bilgi", "Düzenleme modu sonraki aşamada eklenecek."))
        for w in [self.row_search, self.limit_combo, self.platform_filter, self.filter_btn, self.sort_btn, self.table_refresh_btn, self.cols_btn, self.add_btn]:
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
        self.zoom_btn = QPushButton("Yakınlaştır"); self.zoom_btn.setObjectName("softBtn"); self.zoom_btn.clicked.connect(self._zoom_schema)
        self.schema_refresh_btn = QPushButton("Yenile"); self.schema_refresh_btn.setObjectName("primaryBtn"); self.schema_refresh_btn.clicked.connect(self._render_schema)
        for w in [self.schema_combo, self.rel_combo, self.schema_search, self.auto_btn, self.zoom_btn, self.schema_refresh_btn]:
            tlay.addWidget(w)
        tlay.setStretch(3, 1)
        lay.addWidget(tb)

        wrap = QFrame(); wrap.setObjectName("schemaCanvasWrap")
        wlay = QVBoxLayout(wrap); wlay.setContentsMargins(6, 6, 6, 6)
        self.schema_view = SchemaView()
        wlay.addWidget(self.schema_view)
        lay.addWidget(wrap, 1)
        return page

    def _set_page(self, page: str):
        self.tables_page.setVisible(page == "tables")
        self.schema_page.setVisible(page == "schema")
        self.rail_tables.setProperty("active", page == "tables")
        self.rail_schema.setProperty("active", page == "schema")
        self.rail_tables.style().unpolish(self.rail_tables); self.rail_tables.style().polish(self.rail_tables)
        self.rail_schema.style().unpolish(self.rail_schema); self.rail_schema.style().polish(self.rail_schema)

    def refresh_all(self):
        self.stats = self.store.database_stats()
        path = Path(str(self.stats.get("path", "database.sts")))
        self.path_lbl.setText(f"{path.name}   {path}")
        self.path_lbl.setToolTip(str(path))
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
        self.grid.setRowCount(len(rows))
        self.grid.setColumnCount(len(cols))
        self.grid.setHorizontalHeaderLabels(cols)
        for r, row in enumerate(rows):
            for c, col in enumerate(cols):
                txt = str(row.get(col, ""))
                it = QTableWidgetItem(txt)
                it.setToolTip(txt)
                self.grid.setItem(r, c, it)
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
        has_platform = self.grid.columnCount() and any(self.grid.horizontalHeaderItem(i).text() == "platform" for i in range(self.grid.columnCount()))
        pcol = -1
        if has_platform:
            for i in range(self.grid.columnCount()):
                if self.grid.horizontalHeaderItem(i).text() == "platform":
                    pcol = i
                    break
        for r in range(self.grid.rowCount()):
            show = True
            if q:
                row_txt = " | ".join((self.grid.item(r, c).text() if self.grid.item(r, c) else "") for c in range(self.grid.columnCount())).lower()
                show = q in row_txt
            if show and has_platform and pflt and pflt != "Tümü" and pcol >= 0:
                pv = self.grid.item(r, pcol).text() if self.grid.item(r, pcol) else ""
                show = pv == pflt
            self.grid.setRowHidden(r, not show)

    def _sort_table(self):
        self.grid.sortItems(0, Qt.AscendingOrder)

    def _show_columns(self):
        cols = [self.grid.horizontalHeaderItem(i).text() for i in range(self.grid.columnCount())]
        QMessageBox.information(self, "Kolonlar", "\n".join(cols) if cols else "Kolon bulunamadı.")

    def _table_columns(self, table: str) -> List[str]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(r[1]) for r in rows]

    def _render_schema(self):
        scene = self.schema_view.scene()
        scene.clear()
        self.schema_cards.clear()
        counts = self.stats.get("table_counts") or {}
        tables = self.table_names

        col_count = 3
        w, h = 300, 220
        x_gap, y_gap = 60, 50
        for i, t in enumerate(tables):
            row = i // col_count
            col = i % col_count
            x = 40 + col * (w + x_gap)
            y = 30 + row * (h + y_gap)
            card = self._build_schema_card_widget(t, int(counts.get(t, 0)))
            proxy = scene.addWidget(card)
            proxy.setPos(x, y)
            self.schema_cards[t] = proxy

        for (src_t, src_c, dst_t, dst_c) in self._schema_relations():
            if src_t not in self.schema_cards or dst_t not in self.schema_cards:
                continue
            a = self.schema_cards[src_t].sceneBoundingRect()
            b = self.schema_cards[dst_t].sceneBoundingRect()
            p1 = a.center(); p1.setX(a.right())
            p2 = b.center(); p2.setX(b.left())
            path = self._relation_path(p1, p2)
            line = QGraphicsPathItem(path)
            pen = QPen(QColor("#8ca0bf"), 1.6, Qt.DashLine)
            line.setPen(pen)
            scene.addItem(line)

        scene.setSceneRect(QRectF(0, 0, 1400, max(900, (len(tables)//col_count + 1) * (h + y_gap))))

    def _build_schema_card_widget(self, table: str, count: int) -> QWidget:
        w = QFrame(); w.setObjectName("schemaCard"); w.setFixedWidth(290)
        lay = QVBoxLayout(w); lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(4)
        t = QLabel(f"{table}   ({self._fmt_count(count)})"); t.setObjectName("schemaCardTitle")
        lay.addWidget(t)
        for col_name, pk, fk in self._schema_columns(table)[:10]:
            row = QHBoxLayout()
            badge = QLabel("PK" if pk else ("FK" if fk else "•"))
            badge.setObjectName("pkTag" if pk else ("fkTag" if fk else "schemaCol"))
            txt = QLabel(col_name); txt.setObjectName("schemaCol")
            row.addWidget(badge); row.addWidget(txt, 1)
            lay.addLayout(row)
        return w

    def _schema_columns(self, table: str) -> List[Tuple[str, bool, bool]]:
        conn = getattr(getattr(self.store, "db", None), "conn", None)
        if conn is None:
            return []
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        fk_rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        fk_names = {str(r[3]) for r in fk_rows}
        return [(str(c[1]), bool(c[5]), str(c[1]) in fk_names) for c in cols]

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
        if not rels:
            rels.update(FALLBACK_RELATIONS)
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
        for t, proxy in self.schema_cards.items():
            w = proxy.widget()
            if not q:
                w.setStyleSheet("")
                continue
            cols = [c[0].lower() for c in self._schema_columns(t)]
            hit = q in t.lower() or any(q in c for c in cols)
            if selected and self.rel_combo.currentText() == "Sadece seçili tablo" and t != selected and hit:
                hit = False
            w.setStyleSheet("border:2px solid #2563eb; border-radius:10px;" if hit or t == selected else "")

    def _layout_schema(self):
        self._render_schema()

    def _zoom_schema(self):
        self.schema_view.zoom_in()

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
