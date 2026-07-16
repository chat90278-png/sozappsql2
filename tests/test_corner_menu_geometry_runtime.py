# -*- coding: utf-8 -*-
"""Qt runtime regression coverage for corner-menu submenu geometry."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from src.ui.widgets.corner_menu_layer import CornerMenuOverlay, CornerMenuRow


def _build_menu(host: QWidget) -> tuple[QMenu, QMenu]:
    root = QMenu(host)

    file_menu = root.addMenu("Dosya İşlemleri")
    file_menu.addAction("STS Dosyasını Değiştir")
    file_menu.addAction("Excel’e Aktar")

    reports_menu = root.addMenu("Raporlar")
    reports_menu.addAction("Tahmini Teslimat Takvimi")

    management_menu = root.addMenu("Yönetim")
    management_menu.addAction("Platform / Bileşen Yönetimi")

    system_menu = root.addMenu("Sistem")
    system_menu.addAction("Veritabanı Yönetimi")

    help_menu = root.addMenu("Yardım")
    help_menu.addAction("Kullanım Kılavuzu")

    return root, file_menu


def test_submenu_geometry_survives_runtime_row_clear(qtbot) -> None:
    host = QWidget()
    host.resize(900, 700)
    qtbot.addWidget(host)
    host.show()

    root_menu, file_menu = _build_menu(host)
    overlay = CornerMenuOverlay(host, root_menu)

    overlay.set_open(True)
    qtbot.wait(250)

    root_rows = [
        child
        for child in overlay.panel.children()
        if isinstance(child, CornerMenuRow)
    ]
    file_row = next(
        row for row in root_rows if row.title_label.text() == "Dosya İşlemleri"
    )

    qtbot.mouseClick(file_row, Qt.LeftButton)

    # Old deleteLater()-only clearing leaves the root rows parented to the panel
    # until a later event-loop turn. The permanent fix detaches them immediately,
    # so same-click submenu measurement cannot observe stale panel children.
    assert all(row.parent() is None for row in root_rows)

    qtbot.wait(50)
    QApplication.processEvents()

    visible_action_count = sum(
        1
        for action in file_menu.actions()
        if action.isVisible() and not action.isSeparator()
    )
    minimum_expected_height = 20 + 24 + (42 * visible_action_count)

    panel_height = overlay.panel.height()
    geometry_height = overlay.panel.geometry().height()

    assert visible_action_count == 2
    assert panel_height >= minimum_expected_height
    assert geometry_height >= minimum_expected_height
