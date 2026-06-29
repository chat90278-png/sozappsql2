from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QFileDialog

from src.ui.message_boxes import show_warning
from src.ui.theme import STYLE


class WorkbookStartDialog(QDialog):
    """Uygulama açılışında STS veri dosyası seçtirir."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_path: Optional[Path] = None
        self.setWindowTitle("Veri Dosyası Bağla")
        self.setModal(True)
        self.setAcceptDrops(True)
        self.resize(720, 360)
        self.setStyleSheet(STYLE)
        self.build()

    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title = QLabel("Veri dosyasını bağla")
        title.setObjectName("mainTitle")
        root.addWidget(title)

        desc = QLabel("STS veri dosyanızı seçin veya buraya sürükleyin. Dosya seçildikten sonra platformlar, kullanıcılar, bileşenler ve ana sözleşmeler hazırlanır.")
        desc.setWordWrap(True)
        desc.setObjectName("muted")
        root.addWidget(desc)

        self.drop_box = QLabel("STS veri dosyanızı buraya sürükleyip bırakın\n.sts")
        self.drop_box.setAlignment(Qt.AlignCenter)
        self.drop_box.setMinimumHeight(150)
        self.drop_box.setStyleSheet(
            """
            QLabel {
                background: #f8fbff;
                border: 2px dashed #9fb7d5;
                border-radius: 14px;
                color: #506783;
                font-size: 16px;
                font-weight: 800;
                padding: 24px;
            }
            """
        )
        root.addWidget(self.drop_box)

        row = QHBoxLayout()
        pick = QPushButton("Dosya Seç")
        pick.clicked.connect(self.pick_file)
        row.addStretch()
        row.addWidget(pick)
        root.addLayout(row)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".sts"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".sts":
                self.selected_path = path
                self.accept()
                return
        show_warning(self, "Dosya uygun değil", "Lütfen .sts uzantılı bir STS veri dosyası bırakın.")

    def pick_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "STS veri dosyası seç", str(Path.cwd()), "STS Dosyası (*.sts)")
        if p:
            self.selected_path = Path(p)
            self.accept()
