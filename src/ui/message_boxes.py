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
    yes_btn = box.addButton("Evet", QMessageBox.YesRole)
    no_btn = box.addButton("Hayır", QMessageBox.NoRole)
    box.setDefaultButton(yes_btn if default_yes else no_btn)
    box.exec()
    return box.clickedButton() == yes_btn
