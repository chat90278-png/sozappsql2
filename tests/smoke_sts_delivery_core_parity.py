from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QDialog

from src.models.app_models import ContractInfo, SystemInfo
from src.ui.dialogs.auto_accept_dialog import AutoAcceptDialog
from src.ui.dialogs.delivery_dialog import DeliveryDialog


# Regression insurance: if one delivery dialog changes a delivery rule and the
# other dialog is not updated, this parity smoke must fail and name the field
# that diverged.
PARITY_FIELDS = (
    "name",
    "status",
    "planned",
    "delivered",
    "component_units",
    "acceptance_date",
    "planned_acceptance_date",
    "t0_date",
    "t0_months",
    "completion_date",
)


def _build_host(system: SystemInfo) -> QDialog:
    host = QDialog()
    host.ci = ContractInfo(
        no="STS-PARITY-001",
        platform="PARITY",
        user="",
        yi_yd="Yİ",
        contract_type="TEST",
        signature_date="2026-01-01",
        t0_date=system.t0_date,
        t0_months=system.t0_months,
        completion_date=system.completion_date,
    )
    host.store = None
    host.deliveries = {system.name: []}
    return host


def _set_delivery_quantities(dialog: DeliveryDialog, quantities: dict[str, float]) -> None:
    for component, quantity in quantities.items():
        planned_item, delivered_item, _remaining_item = dialog.inputs[component]
        planned_item.setText(str(quantity))
        delivered_item.setText(str(quantity))


def _set_auto_quantities(dialog: AutoAcceptDialog, quantities: dict[str, float]) -> None:
    table = dialog.tables[0]
    for row, component in enumerate(dialog.component_keys):
        quantity = quantities[component]
        table.item(row, 1).setText(str(quantity))
        table.item(row, 2).setText(str(quantity))


def _set_delivery_serials(dialog: DeliveryDialog, component: str, serials: list[str]) -> None:
    dialog._activate_unit_component(component)
    cards = dialog.unit_side_panel._cards
    assert len(cards) == len(serials), (
        f"DeliveryDialog {component} slot count mismatch: "
        f"expected={len(serials)!r}, actual={len(cards)!r}"
    )
    for card, serial in zip(cards, serials):
        card.set_identifier(serial)


def _set_auto_serials(dialog: AutoAcceptDialog, component: str, serials: list[str]) -> None:
    dialog._activate_unit_component(0, component)
    panel = dialog.card_states[0]["unit_side_panel"]
    cards = panel._cards
    assert len(cards) == len(serials), (
        f"AutoAcceptDialog {component} slot count mismatch: "
        f"expected={len(serials)!r}, actual={len(cards)!r}"
    )
    for card, serial in zip(cards, serials):
        card.set_identifier(serial)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    quantities = {"GÖVDE": 4, "KANAT": 2}
    planned_assigned = {"GÖVDE": 0, "KANAT": 0}
    serials = ["SER-1", "SER-2", "SER-3", "SER-4"]
    system = SystemInfo(
        name="PARITY SİSTEMİ",
        components=dict(quantities),
        t0_date="2026-01-15",
        t0_months=6,
        completion_date="2026-07-15",
    )
    host = _build_host(system)

    delivery_dialog = DeliveryDialog(
        system,
        default_name="Parity Teslimat",
        parent=host,
        component_keys=list(quantities),
        planned_assigned=dict(planned_assigned),
        contract_t0_date=system.t0_date,
    )
    auto_dialog = AutoAcceptDialog(host, system, accept_count=1, parent=host)

    delivery_dialog.name.setText("Parity Teslimat")
    auto_dialog.name_edits[0].setText("Parity Teslimat")

    _set_delivery_quantities(delivery_dialog, quantities)
    _set_auto_quantities(auto_dialog, quantities)

    delivery_dialog.status.setCurrentText("Teslim Edildi")
    auto_dialog.status_boxes[0].setCurrentText("Teslim Edildi")

    delivery_dialog.planned_acceptance_date.setText("2026-07-TBD")
    auto_dialog.planned_acc_date_edits[0].setText("2026-07-TBD")
    delivery_dialog.acceptance_date.setText("2026-07-09")
    auto_dialog.acc_date_edits[0].setText("2026-07-09")

    _set_delivery_serials(delivery_dialog, "GÖVDE", serials)
    _set_auto_serials(auto_dialog, "GÖVDE", serials)
    app.processEvents()

    delivery_dialog.save()
    auto_dialog.save()

    delivery_info = delivery_dialog.result
    assert delivery_info is not None, "DeliveryDialog.save() did not produce DeliveryInfo"
    assert len(auto_dialog.result_deliveries) == 1, (
        "AutoAcceptDialog.save() did not produce exactly one DeliveryInfo: "
        f"actual_count={len(auto_dialog.result_deliveries)!r}"
    )
    auto_info = auto_dialog.result_deliveries[0]

    for field_name in PARITY_FIELDS:
        delivery_value = getattr(delivery_info, field_name)
        auto_value = getattr(auto_info, field_name)
        assert delivery_value == auto_value, (
            f"DeliveryInfo parity mismatch for field {field_name!r}: "
            f"DeliveryDialog={delivery_value!r}, AutoAcceptDialog={auto_value!r}"
        )

    print("delivery_core_parity=PASS")
    print(f"compared_fields={','.join(PARITY_FIELDS)}")
    print(f"component_units={delivery_info.component_units!r}")

    delivery_dialog.deleteLater()
    auto_dialog.deleteLater()
    host.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
