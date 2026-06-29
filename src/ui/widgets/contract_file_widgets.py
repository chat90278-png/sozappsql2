from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QPushButton, QSizePolicy, QTreeWidget,
)


class ContractFileDropButton(QPushButton):
    """Clickable upload target that also accepts local file drops."""

    filesDropped = Signal(list)
    invalidDrop = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._default_text = text
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
            self.setText("  ↓    Dosyaları buraya bırakın")
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setText(self._default_text)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setText(self._default_text)
        mime = event.mimeData()
        if not mime.hasUrls():
            self.invalidDrop.emit("Yalnızca yerel dosyalar yüklenebilir.")
            event.ignore()
            return
        file_paths = []
        folder_paths = []
        unsupported_url = False
        for url in mime.urls():
            if not url.isLocalFile():
                unsupported_url = True
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                folder_paths.append(str(path))
            else:
                file_paths.append(str(path))
        if unsupported_url:
            self.invalidDrop.emit("Web bağlantısı yüklenemez, lütfen yerel dosya seçin.")
        if folder_paths:
            # Klasör sürükle-bırak: parent widget'a ilet
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, "_import_contract_folders"):
                    parent._import_contract_folders(folder_paths, parent_folder_id=None)
                    break
                parent = parent.parent() if hasattr(parent, "parent") else None
        if file_paths:
            self.filesDropped.emit(file_paths)
        if file_paths or folder_paths:
            event.acceptProposedAction()
        else:
            event.ignore()


class ContractFileTreeWidget(QTreeWidget):
    """Folder-aware document tree with external file drop support."""

    filesDropped = Signal(list, object)
    invalidDrop = Signal(str)

    # Signal: (item_kind, item_id, target_folder_id_or_None)
    itemMoved = Signal(str, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(True)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self._drag_item_kind = None
        self._drag_item_id = None

    def _drop_folder_id(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        kind = item.data(0, Qt.UserRole)
        if kind == "folder":
            return item.data(0, Qt.UserRole + 1)
        if kind == "file":
            return item.data(0, Qt.UserRole + 2)
        return None

    def _local_file_paths_from_event(self, event):
        """Dosya ve klasör yollarını ayrı listeler halinde döner: (file_paths, folder_paths, error)"""
        mime = event.mimeData()
        if not mime.hasUrls():
            return [], [], "Yalnızca yerel dosyalar yüklenebilir."
        file_paths = []
        folder_paths = []
        unsupported_url = False
        for url in mime.urls():
            if not url.isLocalFile():
                unsupported_url = True
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                folder_paths.append(str(path))
            else:
                file_paths.append(str(path))
        if unsupported_url:
            self.invalidDrop.emit("Web bağlantısı yüklenemez, lütfen yerel dosya seçin.")
        if not file_paths and not folder_paths:
            return [], [], "Yüklenecek yerel dosya veya klasör bulunamadı."
        return file_paths, folder_paths, ""

    def _get_dragged_item_info(self):
        """Sürüklenen item'ın kind ve id'sini döner."""
        item = self.currentItem()
        if not item:
            return None, None
        kind = item.data(0, Qt.UserRole)
        if kind in ("file", "folder"):
            return kind, int(item.data(0, Qt.UserRole + 1))
        return None, None

    def dragEnterEvent(self, event):
        if event.source() is self:
            # Internal move – kendi tree'sinden sürükleme
            kind, item_id = self._get_dragged_item_info()
            if kind in ("file", "folder"):
                self._drag_item_kind = kind
                self._drag_item_id = item_id
                event.acceptProposedAction()
                return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        drop_folder_id = self._drop_folder_id(pos)

        if event.source() is self:
            # Internal move
            kind = self._drag_item_kind
            item_id = self._drag_item_id
            self._drag_item_kind = None
            self._drag_item_id = None
            if kind and item_id is not None:
                self.itemMoved.emit(kind, item_id, drop_folder_id)
            event.acceptProposedAction()
            return

        file_paths, folder_paths, error = self._local_file_paths_from_event(event)
        if not file_paths and not folder_paths:
            if error:
                self.invalidDrop.emit(error)
            event.ignore()
            return
        if folder_paths:
            parent = self.parent()
            while parent is not None:
                if hasattr(parent, "_import_contract_folders"):
                    parent._import_contract_folders(folder_paths, parent_folder_id=drop_folder_id)
                    break
                parent = parent.parent() if hasattr(parent, "parent") else None
        if file_paths:
            self.filesDropped.emit(file_paths, drop_folder_id)
        event.acceptProposedAction()


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self._full_text = ""
        self.setText(text)

    def setText(self, text: str):  # type: ignore[override]
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elide()

    def _refresh_elide(self):
        width = max(12, self.width())
        super().setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width))


class ElidedValueLabel(QLabel):
    """Tek satır ellipsis + tam değer tooltip gösteren kompakt header etiketi."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(40)
        super().setText("")
        self.setText(text)

    def setText(self, text: str):
        self._full_text = str(text or "-")
        self.setToolTip(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full_text, Qt.ElideRight, max(20, self.width() - 2)))

