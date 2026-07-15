from __future__ import annotations

from datetime import datetime, time, timezone

from PySide6.QtCore import QDate, QItemSelection, QItemSelectionModel, QTimer, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProxyStyle,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.services.activity_history_infra import (
    MANAGEMENT_ACTIONS,
    TECHNICAL_ACTIONS,
    USER_ACTIONS,
)
from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import (
    ActivityHistoryItem,
    ActivityHistoryPage,
    ActivityHistoryQuery,
    ActivityHistoryQueryError,
)
from src.ui.activity_history.labels import visible_action_label
from src.ui.activity_history.styles import ACTIVITY_HISTORY_QSS
from src.ui.activity_history.widgets import (
    ActivityDetailsPanel,
    ActivityHistoryTableModel,
    ActivityTimelineView,
)


class ActivityFilterProxyStyle(QProxyStyle):
    """Draw a small antialiased chevron for Activity History drop-downs."""

    def drawPrimitive(self, element, option, painter, widget=None):  # noqa: N802
        if (
            element == QStyle.PE_IndicatorArrowDown
            and widget is not None
            and widget.objectName() == "activityFilter"
        ):
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            center = option.rect.center()
            pen = QPen(QColor("#5b6d84"), 1.7)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(center.x() - 4.0, center.y() - 1.5)
            path.lineTo(center.x(), center.y() + 2.5)
            path.lineTo(center.x() + 4.0, center.y() - 1.5)
            painter.drawPath(path)
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


class ActivityLogDialog(QDialog):
    """Native timeline/table Activity History UI backed by the secure read model."""

    CATEGORY_TABS = (
        ("USER", "Kullanıcı İşlemleri"),
        ("MANAGEMENT", "Yönetim İşlemleri"),
        ("TECHNICAL", "Teknik Kayıtlar"),
    )
    ACTIONS_BY_CATEGORY = {
        "USER": tuple(sorted(USER_ACTIONS)),
        "MANAGEMENT": tuple(sorted(MANAGEMENT_ACTIONS)),
        "TECHNICAL": tuple(sorted(TECHNICAL_ACTIONS)),
    }

    def __init__(
        self,
        store,
        parent=None,
        *,
        access: ActivityHistoryAccess | None = None,
        now_provider=None,
        auto_load: bool = True,
    ):
        if access is None or not access.can_view:
            raise PermissionError("İşlem geçmişi erişimi reddedildi.")
        super().__init__(parent)

        self.store = store
        self.access = access
        self._now_provider = now_provider or (lambda: datetime.now().astimezone())
        self.items: list[ActivityHistoryItem] = []
        self.next_cursor: str | None = None
        self.has_more = False
        self._loading = False
        self._closed = False
        self._query_generation = 0
        self._selected_id: int | None = None
        self._active_category = "USER"
        self._current_view = "timeline"
        self.last_error = ""
        self.query_count = 0

        self._filter_style = ActivityFilterProxyStyle()
        self._filter_style.setParent(self)

        self.setObjectName("activityHistoryDialog")
        self.setWindowTitle("İşlem Geçmişi")
        self.resize(1360, 790)
        self.setMinimumSize(920, 620)
        self.setStyleSheet(ACTIVITY_HISTORY_QSS)

        self._build()
        self._wire_shortcuts()
        self._sync_action_options()
        if auto_load:
            QTimer.singleShot(0, lambda: self.refresh_logs(reset=True))

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(self._build_header())
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_viewbar())

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("activitySplitter")
        self.splitter.setChildrenCollapsible(False)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self._build_results_page())
        self.left_stack.addWidget(self._build_state_page())
        self.splitter.addWidget(self.left_stack)

        self.details = ActivityDetailsPanel()
        self.details.copy_requested.connect(self._copy_text)
        self.splitter.addWidget(self.details)
        self.splitter.setSizes([980, 340])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        root.addWidget(self.splitter, 1)

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("activityHeader")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        eyebrow = QLabel("DENETİM VE KULLANICI HAREKETLERİ")
        eyebrow.setObjectName("activityEyebrow")
        layout.addWidget(eyebrow)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        title = QLabel("İşlem Geçmişi")
        title.setObjectName("activityTitle")
        text_col.addWidget(title)
        subtitle = QLabel(
            "Kullanıcı değişikliklerini okunabilir özetlerle izleyin. "
            "Teknik kayıtlar yalnız yetkili kullanıcılara gösterilir."
        )
        subtitle.setObjectName("activitySubtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(subtitle)
        row.addLayout(text_col, 1)

        summary = QVBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(1)
        self.context_label = QLabel("Güvenli görünüm · Sayfalı kayıtlar")
        self.context_label.setObjectName("activityMuted")
        self.context_label.setAlignment(Qt.AlignRight)
        summary.addWidget(self.context_label)
        self.loaded_label = QLabel("0 kayıt yüklendi")
        self.loaded_label.setObjectName("activitySummaryValue")
        self.loaded_label.setAlignment(Qt.AlignRight)
        summary.addWidget(self.loaded_label)
        row.addLayout(summary)
        layout.addLayout(row)

        self.tab_row = QHBoxLayout()
        self.tab_row.setContentsMargins(0, 2, 0, 0)
        self.tab_row.setSpacing(6)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_buttons: dict[str, QPushButton] = {}
        for category, label in self.CATEGORY_TABS:
            if category == "TECHNICAL" and not self.access.can_view_technical:
                continue
            button = QPushButton(label)
            button.setObjectName("activityTab")
            button.setCheckable(True)
            button.setProperty("category", category)
            button.clicked.connect(
                lambda checked=False, value=category: self._change_tab(value)
            )
            self.tab_group.addButton(button)
            self.tab_buttons[category] = button
            self.tab_row.addWidget(button)
        self.tab_row.addStretch(1)
        self.tab_buttons["USER"].setChecked(True)
        layout.addLayout(self.tab_row)
        return frame

    def _apply_filter_style(self, widget) -> None:
        widget.setObjectName("activityFilter")
        widget.setStyle(self._filter_style)

    def _build_toolbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("activityToolbar")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(6)

        self.search = self._line_edit("Kişi, sözleşme, platform veya işlem ara…")
        self.search.textChanged.connect(self._schedule_search)
        self.search.returnPressed.connect(lambda: self.refresh_logs(reset=True))
        first_row.addWidget(self.search, 5)

        self.action = QComboBox()
        self._apply_filter_style(self.action)
        self.action.setMinimumWidth(0)
        self.action.setMaxVisibleItems(12)
        self.action.setAccessibleName("İşlem türü")
        self.action.currentIndexChanged.connect(
            lambda _=0: self.refresh_logs(reset=True)
        )
        first_row.addWidget(self.action, 2)

        self.actor = self._line_edit("İşlem yapan")
        self.actor.textChanged.connect(self._schedule_search)
        self.actor.returnPressed.connect(lambda: self.refresh_logs(reset=True))
        first_row.addWidget(self.actor, 2)

        self.limit = QComboBox()
        self._apply_filter_style(self.limit)
        self.limit.setFixedWidth(68)
        self.limit.setAccessibleName("Sayfa başına kayıt sayısı")
        for value in (50, 100, 200):
            self.limit.addItem(str(value), value)
        self.limit.currentIndexChanged.connect(
            lambda _=0: self.refresh_logs(reset=True)
        )
        first_row.addWidget(self.limit, 0)

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setObjectName("activityPrimary")
        self.refresh_button.setFixedWidth(74)
        self.refresh_button.clicked.connect(lambda: self.refresh_logs(reset=True))
        first_row.addWidget(self.refresh_button, 0)
        layout.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setContentsMargins(0, 0, 0, 0)
        second_row.setSpacing(6)

        self.date_from = self._date_edit("Başlangıç")
        self.date_to = self._date_edit("Bitiş")
        second_row.addWidget(self.date_from, 1)
        second_row.addWidget(self.date_to, 1)

        self.contract_no = self._line_edit("Sözleşme no")
        self.contract_no.returnPressed.connect(lambda: self.refresh_logs(reset=True))
        second_row.addWidget(self.contract_no, 2)

        self.platform = self._line_edit("Platform")
        self.platform.textChanged.connect(self._schedule_search)
        self.platform.returnPressed.connect(lambda: self.refresh_logs(reset=True))
        second_row.addWidget(self.platform, 2)

        self.clear_button = QPushButton("Filtreleri temizle")
        self.clear_button.setObjectName("activitySecondary")
        self.clear_button.setFixedWidth(118)
        self.clear_button.clicked.connect(self.clear_filters)
        second_row.addWidget(self.clear_button, 0)
        layout.addLayout(second_row)
        return frame

    def _build_viewbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("activityViewBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.result_label = QLabel("0 işlem · En yeni önce")
        self.result_label.setObjectName("activityMuted")
        layout.addWidget(self.result_label)
        layout.addStretch(1)

        self.timeline_button = QPushButton("Zaman Akışı")
        self.table_button = QPushButton("Özet Tablo")
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        for button in (self.timeline_button, self.table_button):
            button.setObjectName("activitySegment")
            button.setCheckable(True)
            self.view_group.addButton(button)
            layout.addWidget(button)
        self.timeline_button.setChecked(True)
        self.timeline_button.clicked.connect(lambda: self.set_view("timeline"))
        self.table_button.clicked.connect(lambda: self.set_view("table"))
        return frame

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.view_stack = QStackedWidget()
        self.timeline = ActivityTimelineView(now_provider=self._now_provider)
        self.timeline.item_selected.connect(self.select_item)
        self.view_stack.addWidget(self.timeline)

        self.table_model = ActivityHistoryTableModel(self)
        self.table = QTableView()
        self.table.setObjectName("activityTable")
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setMinimumHeight(30)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.table_model.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.selectionModel().selectionChanged.connect(
            self._table_selection_changed
        )
        self.view_stack.addWidget(self.table)
        layout.addWidget(self.view_stack, 1)

        self.load_more = QPushButton("Daha Fazla Yükle")
        self.load_more.setObjectName("activityLoadMore")
        self.load_more.clicked.connect(lambda: self.refresh_logs(reset=False))
        self.load_more.setVisible(False)
        layout.addWidget(self.load_more)
        return page

    def _build_state_page(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("activityStatePanel")
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)

        self.state_title = QLabel("Yükleniyor…")
        self.state_title.setObjectName("activityStateTitle")
        self.state_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.state_title)

        self.state_message = QLabel("İşlem geçmişi güvenli biçimde hazırlanıyor.")
        self.state_message.setObjectName("activityMuted")
        self.state_message.setAlignment(Qt.AlignCenter)
        self.state_message.setWordWrap(True)
        layout.addWidget(self.state_message)

        self.retry_button = QPushButton("Tekrar dene")
        self.retry_button.setObjectName("activityPrimary")
        self.retry_button.clicked.connect(lambda: self.refresh_logs(reset=True))
        self.retry_button.setVisible(False)
        layout.addWidget(self.retry_button, 0, Qt.AlignCenter)
        return frame

    def _line_edit(self, placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        self._apply_filter_style(edit)
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return edit

    def _date_edit(self, special: str) -> QDateEdit:
        edit = QDateEdit()
        self._apply_filter_style(edit)
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setMinimumDate(QDate(2000, 1, 1))
        edit.setSpecialValueText(special)
        edit.setDate(edit.minimumDate())
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit.dateChanged.connect(lambda _date: self._schedule_search())
        return edit

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence.Find, self, activated=self.search.setFocus)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(320)
        self._search_timer.timeout.connect(lambda: self.refresh_logs(reset=True))

    # -------------------------------------------------------------- interaction
    @property
    def active_category(self) -> str:
        return self._active_category

    @property
    def current_view(self) -> str:
        return self._current_view

    @property
    def is_loading(self) -> bool:
        return self._loading

    def _schedule_search(self, *_args) -> None:
        if not self._closed:
            self._search_timer.start()

    def _change_tab(self, category: str) -> None:
        if category == "TECHNICAL" and not self.access.can_view_technical:
            return
        if category not in self.tab_buttons:
            return
        self._active_category = category
        self.tab_buttons[category].setChecked(True)
        self._sync_action_options()
        self._clear_selection()
        self.refresh_logs(reset=True)

    def select_tab(self, category: str) -> bool:
        if category == "TECHNICAL" and not self.access.can_view_technical:
            return False
        if category not in self.tab_buttons:
            return False
        self._change_tab(category)
        return True

    def _sync_action_options(self) -> None:
        current = self.action.currentData() if hasattr(self, "action") else ""
        if not hasattr(self, "action"):
            return
        self.action.blockSignals(True)
        self.action.clear()
        self.action.addItem("Tüm işlemler", "")
        for action in self.ACTIONS_BY_CATEGORY.get(self._active_category, ()):
            self.action.addItem(visible_action_label(action), action)
        index = self.action.findData(current)
        self.action.setCurrentIndex(index if index >= 0 else 0)
        self.action.blockSignals(False)

    def set_view(self, view: str) -> None:
        if view not in {"timeline", "table"}:
            return
        self._current_view = view
        self.view_stack.setCurrentIndex(0 if view == "timeline" else 1)
        self.timeline_button.setChecked(view == "timeline")
        self.table_button.setChecked(view == "table")
        if self._selected_id is not None:
            self._restore_selection(self._selected_id)

    def clear_filters(self) -> None:
        for widget in (self.search, self.actor, self.contract_no, self.platform):
            widget.blockSignals(True)
            widget.clear()
            widget.blockSignals(False)
        for edit in (self.date_from, self.date_to):
            edit.blockSignals(True)
            edit.setDate(edit.minimumDate())
            edit.blockSignals(False)
        self.action.blockSignals(True)
        self.action.setCurrentIndex(0)
        self.action.blockSignals(False)
        self.limit.blockSignals(True)
        self.limit.setCurrentIndex(0)
        self.limit.blockSignals(False)
        self.refresh_logs(reset=True)

    def _validate_dates(self) -> tuple[str | None, str | None]:
        start = None if self.date_from.date() == self.date_from.minimumDate() else self.date_from.date()
        end = None if self.date_to.date() == self.date_to.minimumDate() else self.date_to.date()
        if start is not None and end is not None and start > end:
            raise ActivityHistoryQueryError(
                "Başlangıç tarihi bitiş tarihinden sonra olamaz."
            )
        start_iso = None
        end_iso = None
        if start is not None:
            start_iso = datetime.combine(
                start.toPython(), time.min, tzinfo=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        if end is not None:
            end_iso = datetime.combine(
                end.toPython(), time.max, tzinfo=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        return start_iso, end_iso

    def build_query(self, *, cursor: str | None = None) -> ActivityHistoryQuery:
        start, end = self._validate_dates()
        return ActivityHistoryQuery(
            categories=(self._active_category,),
            actions=(str(self.action.currentData()),)
            if self.action.currentData()
            else (),
            actor_text=self.actor.text().strip(),
            search_text=self.search.text().strip(),
            platform_text=self.platform.text().strip(),
            contract_no=self.contract_no.text().strip(),
            occurred_from_utc=start,
            occurred_to_utc=end,
            limit=int(self.limit.currentData() or 50),
            cursor=cursor,
        )

    # ----------------------------------------------------------------- querying
    def refresh_logs(self, reset: bool = True) -> bool:
        if self._closed or self._loading:
            return False
        self._search_timer.stop()
        try:
            query = self.build_query(cursor=None if reset else self.next_cursor)
        except ActivityHistoryQueryError as exc:
            self._show_error(str(exc), retry=False)
            return False
        if not reset and not self.next_cursor:
            return False

        self._loading = True
        self.query_count += 1
        self._query_generation += 1
        generation = self._query_generation
        self.refresh_button.setEnabled(False)
        self.load_more.setEnabled(False)
        self._show_loading(append=not reset)
        QApplication.processEvents()
        try:
            page = self.store.query_activity_history(
                query,
                access=self.access,
                include_technical=self.access.can_view_technical,
            )
            self._accept_page(page, generation=generation, reset=reset)
            return True
        except (ActivityHistoryQueryError, PermissionError) as exc:
            self._show_error(str(exc), retry=True)
            return False
        except Exception:
            self._show_error(
                "İşlem geçmişi yüklenemedi. Uygulama çalışmaya devam ediyor.",
                retry=True,
            )
            return False
        finally:
            self._loading = False
            self.refresh_button.setEnabled(True)
            self.load_more.setEnabled(True)

    def _accept_page(
        self,
        page: ActivityHistoryPage,
        *,
        generation: int,
        reset: bool,
    ) -> bool:
        if self._closed or generation != self._query_generation:
            return False
        incoming = list(page.items)
        if reset:
            self.items = incoming
            self._clear_selection()
        else:
            known = {item.id for item in self.items}
            self.items.extend(item for item in incoming if item.id not in known)
        self.next_cursor = page.next_cursor
        self.has_more = bool(page.has_more and page.next_cursor)
        self._render_items()
        return True

    def _sync_timeline_width(self) -> None:
        if not hasattr(self, "timeline"):
            return
        viewport_width = max(0, self.timeline.viewport().width() - 2)
        content = getattr(self.timeline, "_content", None)
        if content is not None and viewport_width:
            content.setMinimumWidth(viewport_width)

    def _render_items(self) -> None:
        self.timeline.set_items(self.items)
        self.table_model.set_items(self.items)
        count = len(self.items)
        loaded_text = f"{count} kayıt yüklendi"
        if self.has_more:
            loaded_text += " · devamı var"
        self.loaded_label.setText(loaded_text)
        self.result_label.setText(f"{count} işlem · En yeni önce")
        self.load_more.setText("Daha Fazla Yükle")
        self.load_more.setVisible(self.has_more)
        self.load_more.setEnabled(not self._loading)
        if self.items:
            self.left_stack.setCurrentIndex(0)
            self._restore_selection(self._selected_id)
            QTimer.singleShot(0, self._sync_timeline_width)
        else:
            self._show_empty()

    def _restyle_state_message(self, object_name: str) -> None:
        self.state_message.setObjectName(object_name)
        self.state_message.style().unpolish(self.state_message)
        self.state_message.style().polish(self.state_message)

    def _show_loading(self, *, append: bool) -> None:
        if append:
            self.load_more.setText("Yükleniyor…")
            self.load_more.setEnabled(False)
            return
        self.state_title.setText("Yükleniyor…")
        self.state_message.setText("İşlem geçmişi güvenli biçimde hazırlanıyor.")
        self._restyle_state_message("activityMuted")
        self.retry_button.setVisible(False)
        self.left_stack.setCurrentIndex(1)

    def _show_empty(self) -> None:
        self.state_title.setText("Bu filtrelerle eşleşen işlem bulunamadı")
        self.state_message.setText("Arama, tarih veya kategori seçimini değiştirin.")
        self._restyle_state_message("activityMuted")
        self.retry_button.setVisible(False)
        self.left_stack.setCurrentIndex(1)
        self.load_more.setVisible(False)

    def _show_error(self, message: str, *, retry: bool) -> None:
        self.last_error = message
        self.state_title.setText("İşlem geçmişi yüklenemedi")
        self.state_message.setText(message)
        self._restyle_state_message("activityError")
        self.retry_button.setVisible(retry)
        self.left_stack.setCurrentIndex(1)
        self.load_more.setVisible(False)

    # --------------------------------------------------------------- selection
    def _table_selection_changed(
        self,
        selected: QItemSelection,
        _deselected: QItemSelection,
    ) -> None:
        indexes = selected.indexes()
        if not indexes:
            return
        item = self.table_model.item_at(indexes[0].row())
        if item is not None:
            self.select_item(item)

    def select_item(self, item: ActivityHistoryItem) -> None:
        if item not in self.items:
            return
        self._selected_id = item.id
        self.details.setVisible(True)
        if self.splitter.orientation() == Qt.Vertical:
            self.splitter.setSizes([330, 270])
        self.timeline.select_item(item.id)
        self._select_table_row(item.id)
        self.details.set_item(item, self._operation_events_for(item))

    def _operation_events_for(
        self,
        item: ActivityHistoryItem,
    ) -> tuple[ActivityHistoryItem, ...]:
        if not item.operation_group_key:
            return ()
        try:
            if item.technical is not None and item.technical.operation_id:
                return tuple(
                    self.store.get_activity_operation_events(
                        item.technical.operation_id,
                        access=self.access,
                        limit=200,
                    )
                )
            adapter = getattr(
                self.store,
                "get_activity_operation_events_by_group_key",
                None,
            )
            if callable(adapter):
                return tuple(
                    adapter(
                        item.operation_group_key,
                        access=self.access,
                        limit=200,
                    )
                )
        except Exception:
            return ()
        return tuple(
            value
            for value in self.items
            if value.operation_group_key == item.operation_group_key
        )

    def _select_table_row(self, item_id: int) -> None:
        for row, item in enumerate(self.table_model.items):
            if item.id == item_id:
                selection = self.table.selectionModel()
                selection.select(
                    self.table_model.index(row, 0),
                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                )
                self.table.scrollTo(self.table_model.index(row, 0))
                return

    def _restore_selection(self, item_id: int | None) -> None:
        if item_id is None:
            return
        item = next((value for value in self.items if value.id == item_id), None)
        if item is not None:
            self.timeline.select_item(item_id)
            self._select_table_row(item_id)

    def _clear_selection(self) -> None:
        self._selected_id = None
        self.timeline.clear_selection()
        if hasattr(self, "table"):
            self.table.clearSelection()
        if hasattr(self, "details"):
            self.details.clear()
            if self.width() < 1020:
                self.details.setVisible(False)

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    # ------------------------------------------------------------- Qt events
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_timeline_width)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        orientation = Qt.Vertical if self.width() < 1020 else Qt.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
        if orientation == Qt.Vertical:
            self.details.setMaximumWidth(16777215)
            self.details.setVisible(self._selected_id is not None)
            self.splitter.setSizes([330, 270])
        else:
            self.details.setMaximumWidth(430)
            self.details.setVisible(True)
            self.splitter.setSizes([980, 340])
        QTimer.singleShot(0, self._sync_timeline_width)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._closed = True
        self._query_generation += 1
        self._search_timer.stop()
        super().closeEvent(event)

    # Backward-compatible detail API used by older callers/tests.
    def open_detail(self, row: int, _column: int = 0) -> None:
        item = self.table_model.item_at(row)
        if item is not None:
            self.select_item(item)
