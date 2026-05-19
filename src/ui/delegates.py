from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QStyledItemDelegate


class CompactNumberDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setStyleSheet(
            "QLineEdit { padding:2px 6px; min-height:20px; max-height:22px; border:1px solid #9fb7d5; border-radius:4px; }"
        )
        return editor


class CenterTableDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setAlignment(Qt.AlignCenter)
        return editor


class DropdownDelegate(QStyledItemDelegate):
    """Tablo hücresine açılır seçim (QComboBox) getirir — serbest metin engellenir."""

    def __init__(self, choices: List[str], parent=None):
        super().__init__(parent)
        self.choices = choices

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self.choices)
        return cb

    def setEditorData(self, editor, index):
        val = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        idx = editor.findText(val)
        editor.setCurrentIndex(idx if idx >= 0 else 0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
