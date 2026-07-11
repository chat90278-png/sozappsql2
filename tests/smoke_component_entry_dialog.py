from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QLineEdit

try:
    import src.ui.message_boxes  # noqa: F401
except ModuleNotFoundError:
    import sys
    import types

    message_boxes = types.ModuleType("src.ui.message_boxes")
    message_boxes.ask_yes_no = lambda *args, **kwargs: True
    message_boxes.show_information = lambda *args, **kwargs: None
    message_boxes.show_warning = lambda *args, **kwargs: None
    sys.modules["src.ui.message_boxes"] = message_boxes

import src.ui.dialogs.component_entry_dialog as dialog_module
from src.ui.dialogs.component_entry_dialog import COL_NAME, ComponentEntryDialog


def _no_warning(*args, **kwargs):
    raise AssertionError(f"Unexpected warning: {args[1:]}")


dialog_module.ask_yes_no = lambda *args, **kwargs: True
dialog_module.show_information = lambda *args, **kwargs: None
dialog_module.show_warning = _no_warning


class FakeStore:
    def __init__(self):
        self.items = [
            {
                "id": 1,
                "name": "Hava Aracı",
                "unit": "Adet",
                "active": True,
                "note": "",
                "display_order": 0,
                "platforms": {"AKINCI": True},
            }
        ]
        self.write_calls = []

    def load_components_full(self):
        return [dict(item) for item in self.items]

    def current_actor(self):
        return "Smoke Test"

    def write_components(self, components, actor=None):
        self.write_calls.append((list(components), actor))
        self.items = [dict(item) for item in components]


def run() -> None:
    app = QApplication.instance() or QApplication([])

    single_store = FakeStore()
    single = ComponentEntryDialog(single_store)
    single.single_name.setText("Motor")
    single.single_unit.setCurrentText("Takım")
    single._save_single()
    assert len(single_store.write_calls) == 1
    assert single_store.write_calls[0][0][-1]["name"] == "Motor"

    edit_store = FakeStore()
    editing = ComponentEntryDialog(edit_store, initial_mode="bulk")
    editing.show()
    app.processEvents()
    table = editing.bulk_table
    first_rect = table.visualItemRect(table.item(0, COL_NAME))
    QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=first_rect.center())
    app.processEvents()
    assert table.state() == QAbstractItemView.EditingState
    editor = app.focusWidget()
    assert isinstance(editor, QLineEdit)
    QTest.keyClicks(editor, "deneme1")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert table.item(0, COL_NAME).text() == "deneme1"
    assert table.currentRow() == 1 and table.currentColumn() == COL_NAME

    # The first character must not be lost when typing directly into the
    # selected cell after Enter moved to the next row.
    QTest.keyClick(table, Qt.Key_D)
    app.processEvents()
    editor = app.focusWidget()
    assert isinstance(editor, QLineEdit)
    QTest.keyClicks(editor, "eneme2")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert table.item(1, COL_NAME).text() == "deneme2"
    editing.deleteLater()

    bulk_store = FakeStore()
    bulk = ComponentEntryDialog(bulk_store, initial_mode="bulk")
    bulk.bulk_table.item(0, COL_NAME).setText("Motor")
    bulk.bulk_table.item(1, COL_NAME).setText("YKİ")
    bulk._validate_bulk()
    assert sum(row.is_ready for row in bulk._validated_rows) == 2
    bulk._save_bulk()
    assert len(bulk_store.write_calls) == 1
    assert [item["name"] for item in bulk_store.write_calls[0][0]][-2:] == ["Motor", "YKİ"]

    excel_store = FakeStore()
    excel = ComponentEntryDialog(excel_store, initial_mode="bulk")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "liste.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Bileşen Adı", "Birim", "Not", "Durum"])
        sheet.append(["Motor", "Set", "Örnek", "Aktif"])
        workbook.save(path)
        workbook.close()

        excel._set_bulk_mode("excel")
        excel._load_excel_path(str(path))
        excel._preview_excel()
        assert excel.bulk_table.item(0, COL_NAME).text() == "Motor"

    app.processEvents()
    print("component_entry_dialog_smoke=PASS")


if __name__ == "__main__":
    run()
