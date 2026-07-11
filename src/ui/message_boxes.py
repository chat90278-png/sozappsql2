# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget


_MESSAGE_BOX_STYLE = """
QMessageBox {
    background-color:#FFFFFF;
    color:#152238;
}
QMessageBox QLabel {
    background:transparent;
    color:#152238;
    font-size:12px;
}
QMessageBox QPushButton {
    min-width:88px;
    min-height:30px;
    padding:0 14px;
    background:#FFFFFF;
    color:#33475F;
    border:1px solid #C8D5E6;
    border-radius:7px;
    font-weight:600;
}
QMessageBox QPushButton:hover {
    background:#F5F8FC;
    border-color:#9FB4CF;
}
QMessageBox QPushButton:default {
    background:#3B6FE8;
    color:#FFFFFF;
    border-color:#3B6FE8;
}
QMessageBox QPushButton:pressed {
    background:#2F5FD1;
    color:#FFFFFF;
    border-color:#2F5FD1;
}
"""


def _message_box(
    parent: Optional[QWidget],
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    informative_text: str = "",
) -> QMessageBox:
    box = QMessageBox(parent)
    # A frameless/translucent parent can otherwise leak a transparent QDialog
    # rule into QMessageBox and leave its client area black on Windows.
    box.setStyleSheet(_MESSAGE_BOX_STYLE)
    box.setIcon(icon)
    box.setWindowTitle(str(title or ""))
    box.setText(str(text or ""))
    if informative_text:
        box.setInformativeText(str(informative_text))
    return box


def show_information(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Information, title, text, informative_text)
    ok_btn = box.addButton("Tamam", QMessageBox.AcceptRole)
    box.setDefaultButton(ok_btn)
    box.setEscapeButton(ok_btn)
    box.exec()


def show_warning(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Warning, title, text, informative_text)
    ok_btn = box.addButton("Tamam", QMessageBox.AcceptRole)
    box.setDefaultButton(ok_btn)
    box.setEscapeButton(ok_btn)
    box.exec()


def show_critical(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Critical, title, text, informative_text)
    ok_btn = box.addButton("Tamam", QMessageBox.AcceptRole)
    box.setDefaultButton(ok_btn)
    box.setEscapeButton(ok_btn)
    box.exec()


def ask_yes_no(
    parent: Optional[QWidget],
    title: str,
    text: str,
    informative_text: str = "",
    default_yes: bool = False,
) -> bool:
    box = _message_box(parent, QMessageBox.Question, title, text, informative_text)
    # Standard Yes/No buttons can be localized by the OS/Qt style as "Yes"/"No".
    # Use custom Accept/Reject role buttons with explicit Turkish text so every
    # confirmation dialog is consistent across platforms and styles.
    yes_btn = box.addButton("Evet", QMessageBox.AcceptRole)
    no_btn = box.addButton("Hayır", QMessageBox.RejectRole)
    yes_btn.setText("Evet")
    no_btn.setText("Hayır")
    box.setDefaultButton(yes_btn if default_yes else no_btn)
    box.setEscapeButton(no_btn)
    box.exec()
    return box.clickedButton() == yes_btn
