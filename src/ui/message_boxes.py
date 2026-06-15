# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget


def _message_box(
    parent: Optional[QWidget],
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    informative_text: str = "",
) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(str(title or ""))
    box.setText(str(text or ""))
    if informative_text:
        box.setInformativeText(str(informative_text))
    return box


def show_information(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Information, title, text, informative_text)
    box.addButton("Tamam", QMessageBox.AcceptRole)
    box.exec()


def show_warning(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Warning, title, text, informative_text)
    box.addButton("Tamam", QMessageBox.AcceptRole)
    box.exec()


def show_critical(parent: Optional[QWidget], title: str, text: str, informative_text: str = "") -> None:
    box = _message_box(parent, QMessageBox.Critical, title, text, informative_text)
    box.addButton("Tamam", QMessageBox.AcceptRole)
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
