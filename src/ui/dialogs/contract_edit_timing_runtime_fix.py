from __future__ import annotations

import re
from functools import wraps

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.domain.flexible_date import is_tbd_contract_no
from src.services.excel_store import add_months, parse_iso_date
from src.services.sts_database import now_iso
from src.services.sts_store import STSStore
from src.ui.date_picker import build_date_input
from src.ui.dialogs.contract_edit_dialog import ContractEditDialog, form_label


_DIALOG_PATCH_FLAG = "_contract_edit_timing_patch_installed"
_STORE_PATCH_FLAG = "_contract_identity_persistence_patch_installed"


def _selected_platform_name(dialog: ContractEditDialog) -> str:
    try:
        selected = list(dialog._selected_platforms() or [])
    except Exception:
        selected = []
    if selected:
        return str(selected[0] or "").strip()
    return str(getattr(dialog.ci, "platform", "") or "").strip()


def _next_tbd_contract_no(dialog: ContractEditDialog) -> str:
    platform = _selected_platform_name(dialog)
    if not platform:
        return ""
    pattern = re.compile(
        rf"^\s*{re.escape(platform)}\s*-\s*TBD\s*-\s*(\d+)\s*$",
        re.IGNORECASE,
    )
    max_number = 0
    try:
        rows = dialog.store.list_main_contracts(platform)
    except Exception:
        rows = []
    for row in rows:
        match = pattern.match(str(row.get("no", "") or ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{platform} - TBD - {max_number + 1}"


def _refresh_unknown_button_style(dialog: ContractEditDialog) -> None:
    button = getattr(dialog, "unknown_no_btn", None)
    if button is None:
        return
    active = bool(button.isChecked())
    if active:
        button.setStyleSheet(
            "QPushButton{background:#2563eb;color:#ffffff;border:1px solid #1d4ed8;"
            "border-radius:8px;padding:6px 14px;font-weight:900;}"
            "QPushButton:hover{background:#1d4ed8;}"
            "QPushButton:pressed{background:#1e40af;}"
        )
    else:
        button.setStyleSheet(
            "QPushButton{background:#f8fafc;color:#0f172a;border:1px solid #cbd5e1;"
            "border-radius:8px;padding:6px 14px;font-weight:900;}"
            "QPushButton:hover{background:#eef2f7;border-color:#93c5fd;}"
            "QPushButton:pressed{background:#dbeafe;}"
        )


def _recalculate_completion(dialog: ContractEditDialog) -> None:
    if bool(getattr(dialog, "unknown_no_btn", None) and dialog.unknown_no_btn.isChecked()):
        dialog.completion.setText("TBD")
        return
    t0_date = parse_iso_date(dialog.t0.text().strip())
    if not t0_date:
        dialog.completion.clear()
        return
    try:
        dialog.completion.setText(add_months(t0_date, int(dialog.months.value())).isoformat())
    except Exception:
        dialog.completion.clear()


def _set_timing_mode(dialog: ContractEditDialog, unknown_mode: bool, *, update_number: bool = True) -> bool:
    if unknown_mode and update_number:
        current_no = dialog._no_lbl.text().strip()
        if not is_tbd_contract_no(current_no):
            platform = _selected_platform_name(dialog)
            if not platform:
                QMessageBox.warning(
                    dialog,
                    "Platform gerekli",
                    "Sözleşme Yok moduna geçmek için önce en az bir platform seçiniz.",
                )
                button = getattr(dialog, "unknown_no_btn", None)
                if button is not None:
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
                _refresh_unknown_button_style(dialog)
                return False
            dialog._timing_normal_no_before_tbd = current_no
            tbd_number = str(getattr(dialog, "_timing_tbd_no", "") or "").strip()
            if not is_tbd_contract_no(tbd_number):
                tbd_number = _next_tbd_contract_no(dialog)
                dialog._timing_tbd_no = tbd_number
            dialog._no_lbl.setText(tbd_number)
    elif not unknown_mode and update_number:
        current_no = dialog._no_lbl.text().strip()
        if is_tbd_contract_no(current_no):
            dialog._timing_tbd_no = current_no
            dialog._no_lbl.setText(str(getattr(dialog, "_timing_normal_no_before_tbd", "") or ""))

    for widget in (
        getattr(dialog, "_timing_signature_label", None),
        getattr(dialog, "sig_wrap", None),
        getattr(dialog, "timeline_card", None),
        getattr(dialog, "_timing_type_label", None),
        getattr(dialog, "_type_lbl", None),
    ):
        if widget is not None:
            widget.setVisible(not unknown_mode)

    info_label = getattr(dialog, "_timing_tbd_info", None)
    if info_label is not None:
        info_label.setVisible(unknown_mode)

    if unknown_mode:
        dialog._type_lbl.setText("-")
        dialog.completion.setText("TBD")
    else:
        dialog._type_lbl.setText("Ana Sözleşme")
        _recalculate_completion(dialog)

    _refresh_unknown_button_style(dialog)
    QTimer.singleShot(0, dialog._resize_to_safe_default)
    return True


def _inject_contract_timing_fields(dialog: ContractEditDialog) -> None:
    if bool(getattr(dialog, "_is_sd_contract", False)):
        return

    form = getattr(dialog, "_form_container", None)
    form_layout = form.layout() if form is not None else None
    if not isinstance(form_layout, QVBoxLayout) or form_layout.count() < 1:
        return
    grid = form_layout.itemAt(0).layout()
    if not isinstance(grid, QGridLayout):
        return

    initial_unknown = is_tbd_contract_no(str(getattr(dialog.ci, "no", "") or ""))
    dialog._timing_normal_no_before_tbd = "" if initial_unknown else dialog._no_lbl.text().strip()
    dialog._timing_tbd_no = dialog._no_lbl.text().strip() if initial_unknown else ""

    no_container = QWidget(dialog)
    no_layout = QHBoxLayout(no_container)
    no_layout.setContentsMargins(0, 0, 0, 0)
    no_layout.setSpacing(6)
    grid.removeWidget(dialog._no_lbl)
    no_layout.addWidget(dialog._no_lbl, 1)

    dialog.unknown_no_btn = QPushButton("Sözleşme Yok", no_container)
    dialog.unknown_no_btn.setObjectName("secondary")
    dialog.unknown_no_btn.setCheckable(True)
    dialog.unknown_no_btn.setCursor(Qt.PointingHandCursor)
    dialog.unknown_no_btn.setMinimumHeight(34)
    dialog.unknown_no_btn.setToolTip(
        "Sözleşme henüz mevcut değilse tarihleri TBD olarak tutar."
    )
    dialog.unknown_no_btn.setChecked(initial_unknown)
    no_layout.addWidget(dialog.unknown_no_btn, 0)
    grid.addWidget(no_container, 1, 0)

    dialog.sig, dialog.sig_wrap = build_date_input(
        dialog,
        events_provider=dialog.date_picker_events,
    )
    if not initial_unknown:
        dialog.sig.setText(str(getattr(dialog.ci, "signature_date", "") or ""))
    dialog._timing_signature_label = form_label("İmza Tarihi")
    grid.addWidget(dialog._timing_signature_label, 4, 1)
    grid.addWidget(dialog.sig_wrap, 5, 1)
    type_item = grid.itemAtPosition(4, 0)
    dialog._timing_type_label = type_item.widget() if type_item is not None else None

    dialog.t0, dialog.t0_wrap = build_date_input(
        dialog,
        events_provider=dialog.date_picker_events,
    )
    dialog.months = QSpinBox(dialog)
    dialog.months.setRange(0, 600)
    dialog.months.setSuffix(" ay")
    dialog.completion = QLineEdit(dialog)
    dialog.completion.setReadOnly(True)
    dialog.completion.setPlaceholderText("T0 + Ay ile otomatik hesaplanır (Termin)")

    if not initial_unknown:
        dialog.t0.setText(str(getattr(dialog.ci, "t0_date", "") or ""))
        dialog.months.setValue(int(getattr(dialog.ci, "t0_months", 0) or 0))
        dialog.completion.setText(str(getattr(dialog.ci, "completion_date", "") or ""))

    dialog.timeline_card = QFrame(dialog)
    dialog.timeline_card.setObjectName("subtleCard")
    dialog.timeline_card.setStyleSheet(
        "QFrame#subtleCard{background:#F8FBFF;border:1px solid #D8E6F5;border-radius:10px;}"
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

    dialog._timing_tbd_info = QLabel(
        "Sözleşme henüz mevcut olmadığı için İmza, T0 ve Termin bilgileri TBD olarak tutulur.",
        dialog,
    )
    dialog._timing_tbd_info.setObjectName("muted")
    dialog._timing_tbd_info.setWordWrap(True)
    form_layout.insertWidget(2, dialog._timing_tbd_info)

    dialog.t0.textChanged.connect(lambda _text: _recalculate_completion(dialog))
    dialog.months.valueChanged.connect(lambda _value: _recalculate_completion(dialog))
    dialog.unknown_no_btn.toggled.connect(
        lambda checked: _set_timing_mode(dialog, bool(checked), update_number=True)
    )

    _set_timing_mode(dialog, initial_unknown, update_number=False)


def _install_dialog_patch() -> None:
    if getattr(ContractEditDialog, _DIALOG_PATCH_FLAG, False):
        return

    original_build = ContractEditDialog.build
    original_save = ContractEditDialog.save

    @wraps(original_build)
    def build_with_contract_timing(self: ContractEditDialog):
        original_build(self)
        _inject_contract_timing_fields(self)

    @wraps(original_save)
    def save_with_contract_timing(self: ContractEditDialog):
        if bool(getattr(self, "_is_sd_contract", False)) or not hasattr(self, "unknown_no_btn"):
            return original_save(self)

        unknown_mode = bool(self.unknown_no_btn.isChecked())
        new_no = self._no_lbl.text().strip()
        old_no = str(getattr(self.ci, "no", "") or "").strip()

        if unknown_mode:
            if not is_tbd_contract_no(new_no):
                QMessageBox.warning(
                    self,
                    "Sözleşme Yok",
                    "Sözleşme Yok modunda geçerli bir TBD sözleşme numarası kullanılmalıdır.",
                )
                return
            if not is_tbd_contract_no(old_no):
                response = QMessageBox.question(
                    self,
                    "Tarih bilgileri sıfırlanacak",
                    "Sözleşme Yok moduna geçildiğinde İmza, T0 ve Termin bilgileri TBD olarak sıfırlanacaktır. Devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if response != QMessageBox.Yes:
                    return
            target_contract_type = "-"
            timing_values = ("TBD", "TBD", 0, "TBD")
        else:
            if is_tbd_contract_no(new_no):
                QMessageBox.warning(
                    self,
                    "Gerçek sözleşme numarası gerekli",
                    "Sözleşme Yok seçimini kapattığınızda gerçek sözleşme numarasını girmelisiniz.",
                )
                return
            signature_date = parse_iso_date(self.sig.text().strip())
            if not signature_date:
                QMessageBox.warning(self, "Eksik", "İmza Tarihi girin.")
                return
            t0_date = parse_iso_date(self.t0.text().strip())
            if not t0_date:
                QMessageBox.warning(self, "Eksik", "T0 Başlangıç tarihi girin.")
                return
            _recalculate_completion(self)
            completion_date = parse_iso_date(self.completion.text().strip())
            if not completion_date:
                QMessageBox.warning(
                    self,
                    "Eksik",
                    "Termin Tarihi hesaplanamadı. T0 ve T0+Ay alanlarını kontrol edin.",
                )
                return
            target_contract_type = "Ana Sözleşme"
            timing_values = (
                signature_date.isoformat(),
                t0_date.isoformat(),
                int(self.months.value()),
                completion_date.isoformat(),
            )

        original_contract_type = str(getattr(self.ci, "contract_type", "") or "")
        self.ci.contract_type = target_contract_type
        try:
            original_save(self)
        finally:
            self.ci.contract_type = original_contract_type

        if not self.result:
            return
        self.result.contract_type = target_contract_type
        self.result.signature_date = timing_values[0]
        self.result.t0_date = timing_values[1]
        self.result.t0_months = timing_values[2]
        self.result.completion_date = timing_values[3]

    ContractEditDialog.build = build_with_contract_timing
    ContractEditDialog.save = save_with_contract_timing
    setattr(ContractEditDialog, _DIALOG_PATCH_FLAG, True)


def _install_store_patch() -> None:
    if getattr(STSStore, _STORE_PATCH_FLAG, False):
        return

    original_write_contract = STSStore.write_contract

    @wraps(original_write_contract)
    def write_contract_with_identity(
        self: STSStore,
        ci,
        systems,
        deliveries,
        old_contract_no=None,
        old_start_row=None,
    ):
        contract_id = int(
            getattr(ci, "entry_start_row", 0)
            or getattr(ci, "contract_id", 0)
            or getattr(ci, "id", 0)
            or 0
        )
        before = None
        if contract_id:
            before = self.db.conn.execute(
                "SELECT contract_no,contract_type,type_display,is_main,revision FROM contracts WHERE id=?",
                (contract_id,),
            ).fetchone()

        result = original_write_contract(
            self,
            ci,
            systems,
            deliveries,
            old_contract_no=old_contract_no,
            old_start_row=old_start_row,
        )
        contract_id = int(result or getattr(ci, "entry_start_row", 0) or contract_id or 0)
        if not contract_id or before is None:
            return result

        requested_no = str(getattr(ci, "no", "") or "").strip()
        requested_type = str(getattr(ci, "contract_type", "") or "").strip()
        old_no = str(before[0] or "")
        old_type = str(before[1] or "")
        identity_changed = old_no != requested_no or old_type != requested_type
        if not identity_changed:
            return result

        current = self.db.conn.execute(
            "SELECT revision FROM contracts WHERE id=?",
            (contract_id,),
        ).fetchone()
        old_revision = int(before[4] or 1)
        current_revision = int(current[0] or 1) if current else old_revision
        final_revision = current_revision if current_revision > old_revision else old_revision + 1
        is_main = 1 if self._normalize_label(requested_type) == self._normalize_label("Ana Sözleşme") else 0
        timestamp = now_iso()

        with self.db.tx():
            self.db.conn.execute(
                """
                UPDATE contracts
                SET contract_no=?, contract_type=?, type_display=?, is_main=?, revision=?, updated_at=?
                WHERE id=?
                """,
                (
                    requested_no,
                    requested_type,
                    requested_type,
                    is_main,
                    final_revision,
                    timestamp,
                    contract_id,
                ),
            )

        setattr(ci, "revision", final_revision)
        self._log(
            "contract_identity_updated",
            entity_type="contract",
            entity_id=contract_id,
            platform=str(getattr(ci, "platform", "") or ""),
            contract_no=requested_no,
            source="Contract Detail",
            message="Sözleşme numarası veya tipi güncellendi",
            before={"contract_no": old_no, "contract_type": old_type},
            after={"contract_no": requested_no, "contract_type": requested_type},
            actor=self.current_actor(),
        )
        return result

    STSStore.write_contract = write_contract_with_identity
    setattr(STSStore, _STORE_PATCH_FLAG, True)


def install_contract_edit_timing_fix() -> None:
    """Install the edit-dialog timeline/TBD-mode and identity persistence fixes."""
    _install_dialog_patch()
    _install_store_patch()
