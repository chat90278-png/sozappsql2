from __future__ import annotations

from functools import wraps

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from src.services.excel_store import add_months, parse_iso_date
from src.ui.date_picker import build_date_input
from src.ui.dialogs.contract_edit_dialog import ContractEditDialog, form_label


_PATCH_FLAG = "_sd_edit_timing_patch_installed"
_FIELDS_FLAG = "_sd_timing_fields_installed"


def _recalculate_sd_completion(dialog: ContractEditDialog) -> None:
    t0_date = parse_iso_date(dialog.t0.text().strip())
    if not t0_date:
        dialog.completion.clear()
        return
    try:
        dialog.completion.setText(
            add_months(t0_date, int(dialog.months.value())).isoformat()
        )
    except Exception:
        dialog.completion.clear()


def _inject_sd_timing_fields(dialog: ContractEditDialog) -> None:
    if not bool(getattr(dialog, "_is_sd_contract", False)):
        return
    if bool(getattr(dialog, _FIELDS_FLAG, False)):
        return

    form = getattr(dialog, "_form_container", None)
    form_layout = form.layout() if form is not None else None
    if not isinstance(form_layout, QVBoxLayout) or form_layout.count() < 1:
        return
    grid = form_layout.itemAt(0).layout()
    if not isinstance(grid, QGridLayout):
        return

    dialog.sig, dialog.sig_wrap = build_date_input(
        dialog,
        events_provider=dialog.date_picker_events,
    )
    dialog.sig.setText(str(getattr(dialog.ci, "signature_date", "") or ""))
    dialog._sd_timing_signature_label = form_label("İmza Tarihi")
    grid.addWidget(dialog._sd_timing_signature_label, 4, 1)
    grid.addWidget(dialog.sig_wrap, 5, 1)

    dialog.t0, dialog.t0_wrap = build_date_input(
        dialog,
        events_provider=dialog.date_picker_events,
    )
    dialog.t0.setText(str(getattr(dialog.ci, "t0_date", "") or ""))

    dialog.months = QSpinBox(dialog)
    dialog.months.setRange(0, 600)
    dialog.months.setSuffix(" ay")
    dialog.months.setValue(int(getattr(dialog.ci, "t0_months", 0) or 0))

    dialog.completion = QLineEdit(dialog)
    dialog.completion.setReadOnly(True)
    dialog.completion.setPlaceholderText(
        "T0 + Ay ile otomatik hesaplanır (Termin)"
    )
    dialog.completion.setText(
        str(getattr(dialog.ci, "completion_date", "") or "")
    )

    dialog.timeline_card = QFrame(dialog)
    dialog.timeline_card.setObjectName("subtleCard")
    dialog.timeline_card.setStyleSheet(
        "QFrame#subtleCard{background:#F8FBFF;border:1px solid #D8E6F5;"
        "border-radius:10px;}"
    )
    timeline_layout = QGridLayout(dialog.timeline_card)
    timeline_layout.setContentsMargins(10, 8, 10, 8)
    timeline_layout.setHorizontalSpacing(8)
    timeline_layout.setVerticalSpacing(4)
    timeline_layout.addWidget(form_label("T0 Başlangıç"), 0, 0)
    timeline_layout.addWidget(form_label("T0+Ay"), 0, 2)
    timeline_layout.addWidget(form_label("Termin Tarihi"), 0, 4)
    timeline_layout.addWidget(dialog.t0_wrap, 1, 0)

    plus = QLabel("+", dialog.timeline_card)
    plus.setAlignment(Qt.AlignCenter)
    timeline_layout.addWidget(plus, 1, 1)
    timeline_layout.addWidget(dialog.months, 1, 2)

    equals = QLabel("=", dialog.timeline_card)
    equals.setAlignment(Qt.AlignCenter)
    timeline_layout.addWidget(equals, 1, 3)
    timeline_layout.addWidget(dialog.completion, 1, 4)
    timeline_layout.setColumnStretch(0, 2)
    timeline_layout.setColumnStretch(2, 1)
    timeline_layout.setColumnStretch(4, 2)
    form_layout.insertWidget(1, dialog.timeline_card)

    dialog.t0.textChanged.connect(
        lambda _text: _recalculate_sd_completion(dialog)
    )
    dialog.months.valueChanged.connect(
        lambda _value: _recalculate_sd_completion(dialog)
    )

    if not dialog.completion.text().strip() and parse_iso_date(dialog.t0.text().strip()):
        _recalculate_sd_completion(dialog)

    setattr(dialog, _FIELDS_FLAG, True)
    QTimer.singleShot(0, dialog._resize_to_safe_default)


def _collect_sd_timing(dialog: ContractEditDialog):
    signature_text = dialog.sig.text().strip()
    t0_text = dialog.t0.text().strip()

    # Eski SD akışını bozmamak için tarih bölümü opsiyoneldir. Ancak tarih
    # girilmeye başlanmışsa İmza ve T0 birlikte, geçerli ISO tarih olarak girilir.
    if not signature_text and not t0_text:
        return "", "", 0, ""

    signature_date = parse_iso_date(signature_text)
    if not signature_date:
        QMessageBox.warning(
            dialog,
            "Eksik",
            "SD için İmza Tarihi girin veya tarih alanlarını tamamen boş bırakın.",
        )
        return None

    t0_date = parse_iso_date(t0_text)
    if not t0_date:
        QMessageBox.warning(
            dialog,
            "Eksik",
            "SD için T0 Başlangıç tarihi girin veya tarih alanlarını tamamen boş bırakın.",
        )
        return None

    _recalculate_sd_completion(dialog)
    completion_date = parse_iso_date(dialog.completion.text().strip())
    if not completion_date:
        QMessageBox.warning(
            dialog,
            "Eksik",
            "SD Termin Tarihi hesaplanamadı. T0 ve T0+Ay alanlarını kontrol edin.",
        )
        return None

    return (
        signature_date.isoformat(),
        t0_date.isoformat(),
        int(dialog.months.value()),
        completion_date.isoformat(),
    )


def install_sd_edit_timing_fix() -> None:
    """Add the existing contract timing controls to SD add/edit dialogs."""
    if getattr(ContractEditDialog, _PATCH_FLAG, False):
        return

    original_build = ContractEditDialog.build
    original_save = ContractEditDialog.save

    @wraps(original_build)
    def build_with_sd_timing(self: ContractEditDialog):
        original_build(self)
        _inject_sd_timing_fields(self)

    @wraps(original_save)
    def save_with_sd_timing(self: ContractEditDialog):
        if not bool(getattr(self, "_is_sd_contract", False)):
            return original_save(self)
        if not bool(getattr(self, _FIELDS_FLAG, False)):
            return original_save(self)

        timing_values = _collect_sd_timing(self)
        if timing_values is None:
            return

        original_save(self)
        if not self.result:
            return

        self.result.signature_date = timing_values[0]
        self.result.t0_date = timing_values[1]
        self.result.t0_months = timing_values[2]
        self.result.completion_date = timing_values[3]

    ContractEditDialog.build = build_with_sd_timing
    ContractEditDialog.save = save_with_sd_timing
    setattr(ContractEditDialog, _PATCH_FLAG, True)
