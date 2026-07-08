from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.services.share_history_service import ShareHistoryRecord
from src.ui.presenters.share_history_presenter import (
    display_share_filename,
    format_share_history_datetime,
    present_share_permission,
    present_share_status,
    summarize_share_history,
)


_ROLE_QSS = {
    "info": ("#DBEAFE", "#1D4ED8", "#93C5FD"),
    "attention": ("#FEF3C7", "#B45309", "#FCD34D"),
    "success": ("#DCFCE7", "#15803D", "#86EFAC"),
    "warning": ("#FFEDD5", "#C2410C", "#FDBA74"),
    "neutral": ("#F1F5F9", "#475569", "#CBD5E1"),
    "error": ("#FEE2E2", "#B91C1C", "#FCA5A5"),
}


class ShareHistoryDialog(QDialog):
    """Read-only contract share package lifecycle history."""

    def __init__(self, contract_title: str, records: list[ShareHistoryRecord], refresh_callback=None, parent=None):
        super().__init__(parent)
        self._contract_title = str(contract_title or "Sözleşme")
        self._records = list(records or [])
        self._refresh_callback = refresh_callback
        self.setWindowTitle("Paylaşım Geçmişi")
        self.setMinimumSize(720, 520)
        self.setObjectName("shareHistoryDialog")
        self.setStyleSheet(
            "QDialog#shareHistoryDialog{background:#F8FBFF;}"
            "QLabel{background:transparent;}"
            "QFrame#historyCard{background:#FFFFFF;border:1px solid #D8E5F5;border-radius:14px;}"
            "QFrame#historyEmpty{background:#FFFFFF;border:1px dashed #BFDBFE;border-radius:14px;}"
            "QPushButton#historyRefreshButton,QPushButton#historyCloseButton{background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;border-radius:10px;padding:7px 14px;font-weight:800;}"
            "QPushButton#historyRefreshButton:hover,QPushButton#historyCloseButton:hover{background:#DBEAFE;border-color:#93C5FD;}"
        )
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout(); title_col.setSpacing(3)
        title = QLabel("Paylaşım Geçmişi")
        title.setStyleSheet("color:#0F172A;font-size:22px;font-weight:900;")
        subtitle = QLabel(self._contract_title)
        subtitle.setStyleSheet("color:#64748B;font-size:12px;font-weight:700;")
        title_col.addWidget(title); title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)
        if self._refresh_callback is not None:
            refresh = QPushButton("Yenile")
            refresh.setObjectName("historyRefreshButton")
            refresh.clicked.connect(self.refresh)
            header.addWidget(refresh, 0, Qt.AlignVCenter)
        close = QPushButton("Kapat")
        close.setObjectName("historyCloseButton")
        close.clicked.connect(self.reject)
        header.addWidget(close, 0, Qt.AlignVCenter)
        outer.addLayout(header)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("color:#334155;font-size:12px;font-weight:800;")
        outer.addWidget(self._summary_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:0;} QScrollArea > QWidget > QWidget{background:transparent;}")
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 2, 4, 2)
        self._list.setSpacing(10)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)
        self._render_records()

    def refresh(self) -> None:
        if self._refresh_callback is None:
            return
        self._records = list(self._refresh_callback() or [])
        self._render_records()

    def _clear_list(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render_records(self) -> None:
        self._clear_list()
        summary = summarize_share_history(self._records)
        parts = [f"{summary.total} paylaşım"]
        if summary.open_count:
            parts.append(f"{summary.open_count} açık")
        if summary.returned_count:
            parts.append(f"{summary.returned_count} geri döndü")
        if summary.merged_count:
            parts.append(f"{summary.merged_count} birleştirildi")
        if summary.partially_merged_count:
            parts.append(f"{summary.partially_merged_count} kısmi")
        if summary.cancelled_count:
            parts.append(f"{summary.cancelled_count} iptal")
        if summary.rejected_count:
            parts.append(f"{summary.rejected_count} reddedildi")
        self._summary_label.setText(" · ".join(parts))
        if not self._records:
            self._list.addWidget(self._empty_state(), 0)
            self._list.addStretch(1)
            return
        for record in self._records:
            self._list.addWidget(self._record_card(record), 0)
        self._list.addStretch(1)

    def _empty_state(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("historyEmpty")
        lay = QVBoxLayout(frame); lay.setContentsMargins(22, 28, 22, 28); lay.setSpacing(8)
        title = QLabel("Bu sözleşme için henüz paylaşım oluşturulmamış.")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#0F172A;font-size:14px;font-weight:900;")
        desc = QLabel("Yeni bir paylaşım oluşturduğunuzda durumunu burada takip edebilirsiniz.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#64748B;font-size:12px;font-weight:700;")
        lay.addWidget(title); lay.addWidget(desc)
        return frame

    def _record_card(self, record: ShareHistoryRecord) -> QWidget:
        frame = QFrame()
        frame.setObjectName("historyCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(frame); lay.setContentsMargins(16, 13, 16, 13); lay.setSpacing(8)
        top = QHBoxLayout(); top.setSpacing(10)
        name = QLabel(display_share_filename(record))
        name.setStyleSheet("color:#0F172A;font-size:14px;font-weight:900;")
        top.addWidget(name, 1)
        status = present_share_status(record.status)
        badge = QLabel(status.label)
        badge.setAlignment(Qt.AlignCenter)
        bg, fg, border = _ROLE_QSS.get(status.role, _ROLE_QSS["neutral"])
        badge.setStyleSheet(f"background:{bg};color:{fg};border:1px solid {border};border-radius:10px;padding:3px 10px;font-size:11px;font-weight:900;")
        top.addWidget(badge, 0, Qt.AlignRight)
        lay.addLayout(top)

        meta = QLabel(
            f"Oluşturma: {format_share_history_datetime(record.created_at)} · "
            f"Yetki: {present_share_permission(record.permission_mode)}"
        )
        meta.setStyleSheet("color:#475569;font-size:12px;font-weight:700;")
        lay.addWidget(meta)

        detail_parts = [f"Paket: {record.share_package_id[:8]}"] if record.share_package_id else []
        if record.source_contract_revision:
            detail_parts.append(f"Base revizyon: {record.source_contract_revision}")
        if record.base_snapshot_sha256:
            detail_parts.append(f"Snapshot: {record.base_snapshot_sha256[:12]}")
        if detail_parts:
            detail = QLabel(" · ".join(detail_parts))
            detail.setStyleSheet("color:#94A3B8;font-size:10px;font-weight:700;")
            lay.addWidget(detail)
        return frame
