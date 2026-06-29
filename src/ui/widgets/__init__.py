from PySide6.QtWidgets import QLabel, QFrame, QVBoxLayout

from .contract_file_widgets import (
    ContractFileDropButton,
    ContractFileTreeWidget,
    ElidedLabel,
    ElidedValueLabel,
)
from .filterable_header import FilterableHeaderView, PlatformListDelegate


def stat_card(title, value):
    f = QFrame()
    f.setObjectName("statCard")
    l = QVBoxLayout(f)
    a = QLabel(title.upper())
    a.setObjectName("metaLabel")
    b = QLabel(str(value))
    b.setObjectName("statValue")
    l.addWidget(a)
    l.addWidget(b)
    return f


def set_card_value(card, value):
    labs = card.findChildren(QLabel)
    if len(labs) > 1:
        labs[1].setText(str(value))
