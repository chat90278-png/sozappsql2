# -*- coding: utf-8 -*-
"""Current-main Analysis Center and personal agenda integration layer."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from analysis_center.analysis_data_loader import load_analysis_data
from analysis_center.analysis_metrics import compute_metrics
from src.services.personal_agenda_facade import PersonalAgendaFacade
from src.ui.agenda_compact_widget import AgendaCompactWidget
from src.ui.agenda_detail_window import AgendaDetailWindow
from src.ui.main_page_final_window import MainWindow as CompactMainWindow
from src.ui.main_window import app_icon_path
from src.ui.widgets.contract_status_summary import (
    ContractStatusSummary,
    ContractStatusSummaryWidget,
)
from src.ui.widgets.corner_menu_layer import CornerMenuOverlay
from src.ui.widgets.filterable_header import PLATFORM_SELECTED_ROLE, PlatformListDelegate


_log = logging.getLogger(__name__)


class CompactPlatformListDelegate(PlatformListDelegate):
    """Same platform semantics with tighter rhythm for the 275 px rail."""

    def paint(self, painter, option, index):
        painter.save()
        try:
            state = option.state
            is_selected = bool(index.data(PLATFORM_SELECTED_ROLE))
            is_hover = bool(state & QStyle.State_MouseOver)
            if is_selected:
                painter.fillRect(option.rect, QColor("#eff6ff"))
                painter.fillRect(
                    QRect(
                        option.rect.left(),
                        option.rect.top(),
                        3,
                        option.rect.height(),
                    ),
                    QColor("#2563eb"),
                )
            elif is_hover:
                painter.fillRect(option.rect, QColor("#f0f7ff"))
            else:
                painter.fillRect(option.rect, QColor("#ffffff"))

            row = index.row()
            pal_bg, pal_fg = self._PALETTES[row % len(self._PALETTES)]
            platform_name = str(
                index.data(Qt.UserRole) or index.data(Qt.DisplayRole) or ""
            ).strip()
            abbr = platform_name[:3].upper() if platform_name else "?"
            rect = option.rect
            abbr_rect = QRect(
                rect.left() + 8,
                rect.top() + (rect.height() - 24) // 2,
                30,
                24,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(pal_bg))
            painter.drawRoundedRect(abbr_rect, 5, 5)

            abbr_font = painter.font()
            abbr_font.setPointSize(8)
            abbr_font.setBold(True)
            painter.setFont(abbr_font)
            painter.setPen(QColor(pal_fg))
            painter.drawText(abbr_rect, Qt.AlignCenter, abbr)

            name_x = abbr_rect.right() + 7
            count_str = self._counts.get(row, "")
            count_w = 24 if count_str else 0
            name_rect = QRect(
                name_x,
                rect.top(),
                max(0, rect.width() - name_x - count_w - 6),
                rect.height(),
            )
            name_font = painter.font()
            name_font.setPointSize(9)
            name_font.setBold(is_selected)
            painter.setFont(name_font)
            painter.setPen(
                QColor("#1e40af") if is_selected else QColor("#374151")
            )
            painter.drawText(
                name_rect,
                Qt.AlignVCenter | Qt.AlignLeft,
                platform_name,
            )
            if count_str:
                count_rect = QRect(
                    rect.right() - count_w - 5,
                    rect.top(),
                    count_w,
                    rect.height(),
                )
                count_font = painter.font()
                count_font.setPointSize(8)
                count_font.setBold(False)
                painter.setFont(count_font)
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(
                    count_rect,
                    Qt.AlignVCenter | Qt.AlignRight,
                    count_str,
                )
        finally:
            painter.restore()

    def sizeHint(self, option, index):
        try:
            width = int(option.rect.width()) if option is not None else 275
            return QSize(width if width > 0 else 275, 40)
        except Exception:
            return QSize(275, 40)


class MainWindow(CompactMainWindow):
    """Compact main window with Analysis Center, agenda and corner menu."""

    def build(self):
        self._agenda_facade = None
        self._agenda_bound_db = None
        self._agenda_snapshot = None
        self._agenda_detail_window = None
        self._agenda_refresh_timer = None

        super().build()
        self._polish_compact_main_page()
        self._install_contract_status_widget()
        self._install_personal_agenda_widget()

        root = self.centralWidget()
        experimental_btn = getattr(self, "top_actions_btn", None)
        experimental_menu = (
            experimental_btn.menu()
            if isinstance(experimental_btn, QToolButton)
            else None
        )
        if root is not None and isinstance(experimental_btn, QToolButton):
            if experimental_menu is not None:
                try:
                    experimental_menu.hide()
                except Exception:
                    pass
            experimental_btn.hide()
            experimental_btn.setMenu(None)
            experimental_btn.deleteLater()

            self._corner_menu_model_host = QWidget(root)
            self._corner_menu_model_host.setObjectName("cornerMenuModelHost")
            self._corner_menu_model_host.setFixedSize(0, 0)
            self._corner_menu_model_host.hide()
            source_menu = self._build_top_actions_menu(
                self._corner_menu_model_host
            )
            source_menu.hide()
            self._corner_menu_overlay = CornerMenuOverlay(
                host=root,
                source_menu=source_menu,
                before_open=self._refresh_permission_actions,
                parent=self,
            )
            self.top_actions_btn = self._corner_menu_overlay.button
            self.top_actions_menu = source_menu
            self._corner_menu_overlay.reposition()
            if experimental_menu is not None:
                experimental_menu.deleteLater()

    def _polish_compact_main_page(self) -> None:
        self._polish_left_platform_rail()
        self._polish_identity_logo()
        self._fix_today_badge_text_width()

    def _polish_left_platform_rail(self) -> None:
        platform_list = getattr(self, "platform_list", None)
        if platform_list is None:
            return
        left_panel = platform_list.parentWidget()
        left_column = left_panel.parentWidget() if left_panel is not None else None
        if left_column is not None:
            left_column.setFixedWidth(275)
        if left_panel is not None:
            left_panel.setFixedWidth(275)

        self._platform_list_delegate = CompactPlatformListDelegate(platform_list)
        platform_list.setItemDelegate(self._platform_list_delegate)

        title_label = None
        if left_panel is not None:
            for label in left_panel.findChildren(QLabel, "panelTitle"):
                if str(label.text() or "").strip() == "Platformlar":
                    title_label = label
                    break
        if title_label is not None:
            header = title_label.parentWidget()
            if header is not None:
                header.setObjectName("platformPanelHeader")
                header.setAutoFillBackground(False)
                header_layout = header.layout()
                if header_layout is not None:
                    header_layout.setContentsMargins(10, 7, 10, 7)
                    header_layout.setSpacing(5)
                header.setStyleSheet(
                    "QWidget#platformPanelHeader{background:transparent;border:none;}"
                    "QLabel#platformPanelTitle{background:transparent;border:none;"
                    "padding:0;margin:0;}"
                )
            title_label.setObjectName("platformPanelTitle")
            title_label.setAutoFillBackground(False)
            title_label.setStyleSheet(
                "QLabel#platformPanelTitle{background:transparent;border:none;"
                "padding:0;margin:0;}"
            )

        new_button = (
            left_panel.findChild(QWidget, "newContractBtn")
            if left_panel is not None
            else None
        )
        if new_button is not None:
            new_button.setMinimumHeight(42)
            new_button.setMaximumHeight(42)
        info_bar = getattr(self, "platform_info_bar", None)
        if info_bar is not None and info_bar.layout() is not None:
            info_bar.layout().setContentsMargins(8, 3, 6, 3)
            info_bar.layout().setSpacing(3)

    def _polish_identity_logo(self) -> None:
        root = self.centralWidget()
        logo = (
            root.findChild(QLabel, "appIdentityLogo")
            if root is not None
            else None
        )
        if logo is None:
            return
        logo.setFixedSize(72, 72)
        logo.setStyleSheet(
            "QLabel#appIdentityLogo{background:#0f2b61;"
            "border:1px solid #5fb7ff;border-radius:18px;padding:1px;}"
        )
        source = app_icon_path()
        if source and source.exists():
            pixmap = QPixmap(str(source))
            if not pixmap.isNull():
                logo.setPixmap(
                    pixmap.scaled(
                        68,
                        68,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )

    def _fix_today_badge_text_width(self) -> None:
        today_num = getattr(self, "today_num", None)
        today_info = getattr(self, "today_info", None)
        if today_num is None or today_info is None:
            return
        today_box = today_num.parentWidget()
        today_layout = today_box.layout() if today_box is not None else None
        if today_box is not None:
            today_box.setFixedSize(68, 112)
        if today_layout is not None:
            today_layout.setContentsMargins(4, 8, 4, 8)
            today_layout.setSpacing(1)
        today_info.setMinimumWidth(58)
        today_info.setMaximumWidth(58)
        today_info.setAlignment(Qt.AlignCenter)
        today_info.setWordWrap(False)
        today_info.setStyleSheet(
            "background:transparent;border:none;padding:0;margin:0;"
        )

    def _install_contract_status_widget(self) -> None:
        calendar_widget = getattr(self, "_cal_widget", None)
        if calendar_widget is None:
            return
        calendar_card = calendar_widget.parentWidget()
        calendar_layout = (
            calendar_card.layout() if calendar_card is not None else None
        )
        if calendar_layout is None:
            return
        upcoming_scroll = getattr(self, "upcoming_scroll", None)
        if upcoming_scroll is not None:
            calendar_layout.removeWidget(upcoming_scroll)
            upcoming_scroll.hide()
        try:
            calendar_widget.ensurePolished()
            calendar_width = max(
                int(calendar_widget.sizeHint().width()),
                int(calendar_widget.minimumSizeHint().width()),
            )
            if calendar_width > 0:
                calendar_widget.setFixedWidth(calendar_width)
            calendar_widget.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Fixed,
            )
        except Exception:
            _log.exception(
                "Calendar size could not be locked while installing status widget"
            )
        self.contract_status_widget = ContractStatusSummaryWidget(calendar_card)
        self.contract_status_widget.open_analysis_requested.connect(
            self.open_analysis_center
        )
        calendar_index = calendar_layout.indexOf(calendar_widget)
        insert_index = calendar_index if calendar_index >= 0 else 1
        calendar_layout.insertWidget(
            insert_index,
            self.contract_status_widget,
            0,
            Qt.AlignVCenter,
        )

    def _install_personal_agenda_widget(self) -> None:
        calendar_widget = getattr(self, "_cal_widget", None)
        if calendar_widget is None:
            return
        calendar_card = calendar_widget.parentWidget()
        calendar_layout = (
            calendar_card.layout() if calendar_card is not None else None
        )
        if calendar_layout is None:
            return

        self.agenda_compact_widget = AgendaCompactWidget(calendar_card)
        self.agenda_compact_widget.open_details_requested.connect(
            self._open_agenda_details
        )
        self.agenda_compact_widget.open_contract_requested.connect(
            self._open_agenda_contract
        )
        self.agenda_compact_widget.item_dwell_seen_requested.connect(
            self._agenda_mark_seen
        )
        self.agenda_compact_widget.snooze_requested.connect(
            self._agenda_snooze
        )
        calendar_index = calendar_layout.indexOf(calendar_widget)
        insert_index = (
            calendar_index
            if calendar_index >= 0
            else calendar_layout.count()
        )
        calendar_layout.insertWidget(
            insert_index,
            self.agenda_compact_widget,
            1,
            Qt.AlignVCenter,
        )

        self._agenda_refresh_timer = QTimer(self)
        self._agenda_refresh_timer.setSingleShot(True)
        self._agenda_refresh_timer.setInterval(200)
        self._agenda_refresh_timer.timeout.connect(self.refresh_agenda)
        self._sync_agenda_permission_visibility()

    def _sync_agenda_permission_visibility(self) -> bool:
        widget = getattr(self, "agenda_compact_widget", None)
        try:
            allowed = bool(
                self.current_staff
                and self.is_sts_mode()
                and self.has_permission("view_contracts")
            )
        except Exception:
            allowed = False
        if widget is not None:
            widget.setVisible(allowed)
        if not allowed:
            detail = getattr(self, "_agenda_detail_window", None)
            if detail is not None:
                detail.close()
            self._agenda_snapshot = None
        return allowed

    def _ensure_agenda_facade(self) -> PersonalAgendaFacade | None:
        if not self.store or not self.is_sts_mode():
            return None
        db = getattr(self.store, "db", None)
        if db is None:
            return None
        if self._agenda_facade is None or self._agenda_bound_db is not db:
            detail = getattr(self, "_agenda_detail_window", None)
            if detail is not None:
                detail.close()
            self._agenda_detail_window = None
            self._agenda_snapshot = None
            self._agenda_bound_db = db
            self._agenda_facade = PersonalAgendaFacade(db)
        return self._agenda_facade

    def schedule_agenda_refresh(self) -> None:
        timer = getattr(self, "_agenda_refresh_timer", None)
        if timer is not None:
            timer.start(200)

    def refresh_agenda(self, *, touch_presented: bool = True) -> None:
        widget = getattr(self, "agenda_compact_widget", None)
        if widget is None:
            return
        if not self._sync_agenda_permission_visibility():
            widget.clear()
            return
        facade = self._ensure_agenda_facade()
        if facade is None:
            widget.clear()
            return

        widget.set_loading(True)
        detail = getattr(self, "_agenda_detail_window", None)
        if detail is not None:
            detail.set_loading(True)
        try:
            snapshot = facade.load(
                self.current_staff,
                now=datetime.now(),
                compact_limit=2,
                detail_limit=20,
                touch_presented=touch_presented,
            )
        except Exception as exc:
            _log.exception("Personal agenda could not be loaded")
            message = str(exc or "Gündem yüklenemedi")
            widget.set_error(message)
            if detail is not None:
                detail.set_error(message)
            return

        self._agenda_snapshot = snapshot
        widget.set_snapshot(snapshot)
        if detail is not None:
            detail.set_snapshot(snapshot)

    def _open_agenda_details(self) -> None:
        if not self._sync_agenda_permission_visibility():
            return
        detail = getattr(self, "_agenda_detail_window", None)
        if detail is None:
            detail = AgendaDetailWindow(self)
            detail.open_contract_requested.connect(
                self._open_agenda_contract
            )
            detail.item_dwell_seen_requested.connect(
                self._agenda_mark_seen
            )
            detail.snooze_requested.connect(self._agenda_snooze)
            detail.refresh_requested.connect(
                lambda: self.refresh_agenda(touch_presented=True)
            )
            detail.destroyed.connect(
                lambda *_args: setattr(
                    self,
                    "_agenda_detail_window",
                    None,
                )
            )
            self._agenda_detail_window = detail
        snapshot = getattr(self, "_agenda_snapshot", None)
        if snapshot is not None:
            detail.set_snapshot(snapshot)
        else:
            detail.set_loading(True)
            self.refresh_agenda(touch_presented=True)
        detail.show()
        detail.raise_()
        detail.activateWindow()
        detail.focus_item()

    def _agenda_mark_seen(self, item) -> None:
        facade = self._ensure_agenda_facade()
        if facade is None:
            return
        try:
            facade.mark_seen(
                self.current_staff,
                item,
                seen_at=datetime.now(),
            )
        except Exception as exc:
            _log.exception("Agenda seen interaction failed")
            self._agenda_interaction_error(
                str(exc or "Gündem güncellenemedi")
            )
            return
        self.refresh_agenda(touch_presented=False)

    def _agenda_snooze(self, item, preset: str) -> None:
        facade = self._ensure_agenda_facade()
        if facade is None:
            return
        now = datetime.now()
        try:
            until = facade.snooze_until_for_preset(preset, now=now)
            facade.snooze(
                self.current_staff,
                item,
                until=until,
                now=now,
            )
        except Exception as exc:
            _log.exception("Agenda snooze interaction failed")
            self._agenda_interaction_error(
                str(exc or "Gündem ertelenemedi")
            )
            return
        self.refresh_agenda(touch_presented=False)

    def _agenda_interaction_error(self, message: str) -> None:
        widget = getattr(self, "agenda_compact_widget", None)
        if widget is not None:
            widget.set_error(message)
        detail = getattr(self, "_agenda_detail_window", None)
        if detail is not None:
            detail.set_error(message)

    @staticmethod
    def _agenda_contract_id(item: dict) -> int:
        for key in (
            "contract_id",
            "id",
            "row_id",
            "row",
            "start_row",
            "entry_start_row",
        ):
            try:
                value = int(item.get(key, 0) or 0)
            except Exception:
                value = 0
            if value > 0:
                return value
        return 0

    def _open_agenda_contract(self, contract_id: int) -> None:
        try:
            wanted = int(contract_id or 0)
        except Exception:
            wanted = 0
        if wanted <= 0:
            return
        match = next(
            (
                dict(item)
                for item in list(self.contract_index or [])
                if isinstance(item, dict)
                and self._agenda_contract_id(item) == wanted
            ),
            None,
        )
        if match is None:
            _log.warning(
                "Agenda contract navigation target was not found: %s",
                wanted,
            )
            return
        self.open_contract_item(match)

    def _reset_agenda_binding(self) -> None:
        timer = getattr(self, "_agenda_refresh_timer", None)
        if timer is not None:
            timer.stop()
        detail = getattr(self, "_agenda_detail_window", None)
        if detail is not None:
            detail.close()
        self._agenda_detail_window = None
        self._agenda_snapshot = None
        self._agenda_facade = None
        self._agenda_bound_db = None
        widget = getattr(self, "agenda_compact_widget", None)
        if widget is not None:
            widget.clear()
            widget.hide()

    def _analysis_source_path(self) -> Path | None:
        if not self.store:
            return None
        source_path = (
            getattr(getattr(self.store, "db", None), "path", None)
            or getattr(self.store, "path", None)
            or self.path
        )
        try:
            return Path(source_path) if source_path else None
        except Exception:
            return None

    def _refresh_contract_status_widget(self) -> None:
        widget = getattr(self, "contract_status_widget", None)
        if widget is None:
            return
        if not self.store or not self.is_sts_mode():
            widget.clear_summary()
            return
        source_path = self._analysis_source_path()
        if source_path is None:
            widget.clear_summary()
            return
        try:
            data = load_analysis_data(
                source=source_path,
                contract_index=list(self.contract_index or []),
                use_sample=False,
            )
            metrics = compute_metrics(data)
            widget.set_summary(ContractStatusSummary.from_metrics(metrics))
        except Exception:
            _log.exception(
                "Main-page contract status summary could not be refreshed"
            )
            widget.clear_summary()

    def update_alert_strip(self):
        super().update_alert_strip()
        self._refresh_contract_status_widget()
        self.schedule_agenda_refresh()

    def set_empty_state(self):
        super().set_empty_state()
        widget = getattr(self, "contract_status_widget", None)
        if widget is not None:
            widget.clear_summary()
        agenda = getattr(self, "agenda_compact_widget", None)
        if agenda is not None:
            agenda.clear()
            agenda.hide()

    def start_sts_load(self, path):
        self._reset_agenda_binding()
        return super().start_sts_load(path)

    def position_corner_menu(self):
        overlay = getattr(self, "_corner_menu_overlay", None)
        if overlay is not None:
            overlay.reposition()
            return
        super().position_corner_menu()

    def _build_top_actions_menu(self, parent) -> object:
        menu = super()._build_top_actions_menu(parent)
        for action in menu.actions():
            submenu = action.menu()
            if (
                submenu is None
                or str(action.text() or "").replace("&", "") != "Raporlar"
            ):
                continue
            if not any(
                str(item.text() or "").replace("&", "")
                == "Analiz Merkezi"
                for item in submenu.actions()
            ):
                submenu.addAction(
                    "Analiz Merkezi",
                    self.open_analysis_center,
                )
            break
        return menu

    def _analysis_export_guard(self) -> bool:
        return self.require_permission_ui("export_data", "Dashboard Excel")

    def open_analysis_center(self) -> QWidget | None:
        if not self.store or not self.is_sts_mode():
            QMessageBox.information(
                self,
                "Veri dosyası gerekli",
                "Analiz Merkezi için önce bir STS veri dosyası açın.",
            )
            return None
        from src.ui.analysis_center_window import AnalysisCenterWindow

        source_path = self._analysis_source_path()
        if source_path is None:
            QMessageBox.information(
                self,
                "Veri dosyası gerekli",
                "Analiz Merkezi veri kaynağı belirlenemedi.",
            )
            return None
        return self.open_or_raise_tool_window(
            "report:analysis_center",
            "Analiz Merkezi",
            lambda: AnalysisCenterWindow(
                source=source_path,
                contract_index=list(self.contract_index or []),
                parent=self,
                export_guard=self._analysis_export_guard,
            ),
        )

    def closeEvent(self, event):
        timer = getattr(self, "_agenda_refresh_timer", None)
        if timer is not None:
            timer.stop()
        detail = getattr(self, "_agenda_detail_window", None)
        if detail is not None:
            detail.close()
        super().closeEvent(event)
