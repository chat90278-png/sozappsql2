from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .analysis_custom_library import CustomAnalysisLibraryController, SavedAnalysisListItem
from .analysis_definitions import AnalysisDefinition, AnalysisValidationError
from .analysis_models import AnalysisCard
from .analysis_preview_qt import AnalysisPreviewCardHost
from .analysis_renderer import analysis_result_to_card


LOGGER = logging.getLogger(__name__)
CardFactory = Callable[[AnalysisCard, QWidget], QWidget]


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class AnalysisLibraryWidget(QWidget):
    """Saved custom-analysis library with lazy selected-item preview."""

    def __init__(
        self,
        controller: CustomAnalysisLibraryController,
        card_factory: CardFactory,
        on_new: Callable[[], None],
        on_edit: Callable[[str], None],
        on_deleted: Callable[[str], None] | None = None,
        dashboard_is_pinned: Callable[[str], bool] | None = None,
        on_dashboard_toggle: Callable[[str], bool] | None = None,
        on_delete: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.card_factory = card_factory
        self.on_new = on_new
        self.on_edit = on_edit
        self.on_deleted = on_deleted
        self.dashboard_is_pinned = dashboard_is_pinned
        self.on_dashboard_toggle = on_dashboard_toggle
        self.on_delete = on_delete
        self.items: list[SavedAnalysisListItem] = []
        self._preview_widget: QWidget | None = None
        self.last_preview_analysis_id: str | None = None
        self.last_definition: AnalysisDefinition | None = None
        self.last_result = None
        self._build_ui()
        self.refresh_items()
        self.show_initial_preview()

    def _build_ui(self) -> None:
        self.setObjectName("analysisLibraryScreen")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 8)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title = QLabel("Analizlerim", self)
        title.setObjectName("analysisScreenTitle")
        description = QLabel("Kaydettiğiniz özel analizleri yönetin.", self)
        description.setObjectName("analysisScreenDescription")
        title_box.addWidget(title)
        title_box.addWidget(description)
        header.addLayout(title_box, 1)
        self.new_button = QPushButton("Yeni Analiz Oluştur", self)
        self.new_button.setObjectName("analysisBuilderSaveButton")
        self.new_button.clicked.connect(self.on_new)
        header.addWidget(self.new_button, 0, Qt.AlignTop)
        outer.addLayout(header)

        self.issue_label = QLabel("", self)
        self.issue_label.setObjectName("analysisLibraryWarning")
        self.issue_label.setWordWrap(True)
        self.issue_label.hide()
        outer.addWidget(self.issue_label)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        outer.addLayout(body, 1)

        list_scroll = QScrollArea(self)
        list_scroll.setObjectName("analysisLibraryListScroll")
        list_scroll.setWidgetResizable(True)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_scroll.setMinimumWidth(430)
        list_scroll.setMaximumWidth(560)
        self.list_host = QWidget(list_scroll)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        list_scroll.setWidget(self.list_host)
        body.addWidget(list_scroll, 0)

        preview_panel = QFrame(self)
        preview_panel.setObjectName("analysisBuilderPreviewPanel")
        preview_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)
        preview_title = QLabel("ÖNİZLEME", preview_panel)
        preview_title.setObjectName("analysisBuilderSectionTitle")
        preview_layout.addWidget(preview_title)
        self.preview_host = QFrame(preview_panel)
        self.preview_host.setObjectName("analysisBuilderPreviewHost")
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(0)
        preview_layout.addWidget(self.preview_host, 1)
        body.addWidget(preview_panel, 1)

    def refresh_items(self) -> None:
        _clear_layout(self.list_layout)
        self.items = []
        error = self.controller.load_error()
        if error is not None:
            self.issue_label.setText(
                "Kaydedilmiş analizler yüklenemedi. Mevcut dosya korunacak ve bu oturumda üzerine yazılmayacak."
            )
            self.issue_label.show()
            self.list_layout.addWidget(self._empty_state("Kaydedilmiş analizler yüklenemedi."))
            self.list_layout.addStretch(1)
            return
        try:
            self.items = self.controller.list_items()
        except Exception:
            LOGGER.exception("Saved analysis library load failed")
            self.issue_label.setText("Kaydedilmiş analizler yüklenemedi.")
            self.issue_label.show()
            self.list_layout.addWidget(self._empty_state("Kaydedilmiş analizler yüklenemedi."))
            self.list_layout.addStretch(1)
            return

        issue_count = self.controller.load_issues_count()
        if issue_count:
            self.issue_label.setText(f"{issue_count} analiz kaydı yüklenemedi.")
            self.issue_label.show()
        else:
            self.issue_label.clear()
            self.issue_label.hide()

        if not self.items:
            self.list_layout.addWidget(self._empty_state("Henüz kaydedilmiş analiziniz yok."))
            self.list_layout.addStretch(1)
            return
        for item in self.items:
            self.list_layout.addWidget(self._build_item(item))
        self.list_layout.addStretch(1)

    def _empty_state(self, text: str) -> QFrame:
        frame = QFrame(self.list_host)
        frame.setObjectName("analysisLibraryEmptyState")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(10)
        label = QLabel(text, frame)
        label.setObjectName("analysisBuilderPreviewInfo")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        button = QPushButton("Analiz Oluştur", frame)
        button.setObjectName("analysisBuilderSecondaryButton")
        button.clicked.connect(self.on_new)
        layout.addWidget(button, 0, Qt.AlignHCenter)
        return frame

    def _build_item(self, item: SavedAnalysisListItem) -> QFrame:
        frame = QFrame(self.list_host)
        frame.setObjectName("analysisLibraryItem")
        frame.setProperty("analysisId", item.analysis_id)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        title = QLabel(item.title, frame)
        title.setObjectName("analysisLibraryItemTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        meta = QLabel(f"{item.dataset_title} • {item.visualization_title}", frame)
        meta.setObjectName("analysisLibraryItemMeta")
        layout.addWidget(meta)
        summary = QLabel(item.summary, frame)
        summary.setObjectName("analysisLibraryItemSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if item.validation_error:
            warning = QLabel("Bu analiz mevcut veri şemasıyla uyumlu değil.", frame)
            warning.setObjectName("analysisLibraryItemWarning")
            warning.setToolTip(item.validation_error)
            warning.setWordWrap(True)
            layout.addWidget(warning)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(6)
        open_button = self._action_button("Aç", "analysisLibraryOpenButton", frame)
        open_button.clicked.connect(lambda _checked=False, analysis_id=item.analysis_id: self.open_analysis(analysis_id))
        actions.addWidget(open_button)
        dashboard_pinned = bool(
            self.dashboard_is_pinned is not None
            and self.dashboard_is_pinned(item.analysis_id)
        )
        dashboard_button = self._action_button(
            "✓ Dashboard'da" if dashboard_pinned else "+ Dashboard",
            "analysisLibraryDashboardButton",
            frame,
        )
        dashboard_button.setProperty("dashboardPinned", dashboard_pinned)
        dashboard_button.setEnabled(item.is_valid and self.on_dashboard_toggle is not None)
        dashboard_button.clicked.connect(
            lambda _checked=False, analysis_id=item.analysis_id: self.toggle_dashboard(analysis_id)
        )
        actions.addWidget(dashboard_button)
        edit_button = self._action_button("Düzenle", "analysisLibraryEditButton", frame)
        edit_button.clicked.connect(lambda _checked=False, analysis_id=item.analysis_id: self.on_edit(analysis_id))
        actions.addWidget(edit_button)
        copy_button = self._action_button("Kopyala", "analysisLibraryCopyButton", frame)
        copy_button.setEnabled(item.is_valid)
        copy_button.clicked.connect(lambda _checked=False, analysis_id=item.analysis_id: self.copy_analysis(analysis_id))
        actions.addWidget(copy_button)
        delete_button = self._action_button("Sil", "analysisLibraryDeleteButton", frame)
        delete_button.clicked.connect(lambda _checked=False, analysis_id=item.analysis_id: self.delete_analysis(analysis_id))
        actions.addWidget(delete_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return frame

    @staticmethod
    def _action_button(text: str, object_name: str, parent: QWidget) -> QPushButton:
        button = QPushButton(text, parent)
        button.setObjectName(object_name)
        return button

    def open_analysis(self, analysis_id: str) -> None:
        try:
            definition, result = self.controller.preview(analysis_id)
            card = analysis_result_to_card(definition, result)
            rendered = self.card_factory(card, self.preview_host)
            widget = AnalysisPreviewCardHost(card, rendered, self.preview_host)
        except AnalysisValidationError as exc:
            self.show_preview_message(str(exc), error=True)
            return
        except Exception:
            LOGGER.exception("Saved analysis preview failed")
            self.show_preview_message("Analiz önizlenirken beklenmeyen bir hata oluştu.", error=True)
            return
        self.last_preview_analysis_id = analysis_id
        self.last_definition = definition
        self.last_result = result
        self._replace_preview_widget(widget)

    def copy_analysis(self, analysis_id: str) -> None:
        try:
            self.controller.copy(analysis_id)
        except AnalysisValidationError as exc:
            self.show_preview_message(str(exc), error=True)
            return
        except Exception:
            LOGGER.exception("Saved analysis copy failed")
            self.show_preview_message("Analiz kopyalanamadı. Mevcut dosya korunuyor.", error=True)
            return
        self.refresh_items()
        self.show_preview_message("Analiz kopyalandı.")

    def toggle_dashboard(self, analysis_id: str) -> bool:
        if self.on_dashboard_toggle is None:
            return False
        if not self.on_dashboard_toggle(analysis_id):
            return False
        self.refresh_items()
        return True

    def delete_analysis(self, analysis_id: str, *, confirmed: bool | None = None) -> bool:
        try:
            definition = self.controller.get_definition(analysis_id)
        except AnalysisValidationError:
            return False
        if confirmed is None:
            result = QMessageBox.question(
                self,
                "Analizi Sil",
                f"'{definition.title}' analizini silmek istiyor musunuz?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            confirmed = result == QMessageBox.Yes
        if not confirmed:
            return False
        try:
            deleted = (
                self.on_delete(analysis_id)
                if self.on_delete is not None
                else self.controller.delete(analysis_id)
            )
        except Exception:
            LOGGER.exception("Saved analysis delete failed")
            self.show_preview_message("Analiz silinemedi. Mevcut dosya korunuyor.", error=True)
            return False
        if not deleted:
            return False
        if self.last_preview_analysis_id == analysis_id:
            self.show_initial_preview()
        if self.on_deleted is not None:
            self.on_deleted(analysis_id)
        self.refresh_items()
        return True

    def show_initial_preview(self) -> None:
        self.show_preview_message("Bir analiz seçin ve Aç düğmesine basın.")

    def show_data_refreshed_notice(self) -> None:
        self.show_preview_message("Veri yenilendi. Analizi tekrar açın.")

    def show_preview_message(self, text: str, *, error: bool = False) -> None:
        self.last_preview_analysis_id = None
        self.last_definition = None
        self.last_result = None
        label = QLabel(text, self.preview_host)
        label.setObjectName("analysisBuilderPreviewError" if error else "analysisBuilderPreviewInfo")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        self._replace_preview_widget(label)

    def _replace_preview_widget(self, widget: QWidget) -> None:
        if self._preview_widget is not None:
            self.preview_layout.removeWidget(self._preview_widget)
            self._preview_widget.deleteLater()
        self._preview_widget = widget
        self.preview_layout.addWidget(widget, 1)


__all__ = ["AnalysisLibraryWidget"]
