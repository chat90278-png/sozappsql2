from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.models.app_models import ContractInfo
from src.services.multiplatform_contract_persistence import install_multiplatform_contract_persistence_fix
from src.services.sts_store import STSStore
from src.ui.dialogs.contract_edit_dialog import ContractEditDialog
from src.ui.dialogs.contract_edit_timing_runtime_fix import install_contract_edit_timing_fix


install_multiplatform_contract_persistence_fix()
install_contract_edit_timing_fix()


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _seed_store(tmp_path) -> STSStore:
    store = STSStore(tmp_path / "timing-test.sts", actor="Test")
    store.get_platform_id("AKINCI", create=True)
    store.get_user_id("KKK", create=True)
    store.save()
    return store


def _contract(no: str = "SZL-2026-001", contract_type: str = "Ana Sözleşme") -> ContractInfo:
    return ContractInfo(
        no=no,
        platform="AKINCI",
        user="KKK",
        users=["KKK"],
        yi_yd="Yİ",
        contract_type=contract_type,
        signature_date="2026-01-10" if "TBD" not in no else "TBD",
        t0_date="2026-01-31" if "TBD" not in no else "TBD",
        t0_months=1 if "TBD" not in no else 0,
        completion_date="2026-02-28" if "TBD" not in no else "TBD",
        status="Başlanmadı",
        platform_names=["AKINCI"],
    )


def test_edit_dialog_loads_existing_timing_and_recalculates_month_end(tmp_path):
    _app()
    store = _seed_store(tmp_path)
    try:
        dialog = ContractEditDialog(store, _contract())
        assert dialog.sig.text() == "2026-01-10"
        assert dialog.t0.text() == "2026-01-31"
        assert dialog.months.value() == 1
        assert dialog.completion.text() == "2026-02-28"
        assert not dialog.timeline_card.isHidden()

        dialog.t0.setText("2024-01-31")
        dialog.months.setValue(1)
        assert dialog.completion.text() == "2024-02-29"
    finally:
        store.db.close()


def test_tbd_edit_mode_can_switch_to_real_contract_and_collect_dates(tmp_path):
    _app()
    store = _seed_store(tmp_path)
    try:
        dialog = ContractEditDialog(store, _contract("AKINCI - TBD - 1", "-"))
        assert dialog.unknown_no_btn.isChecked()
        assert dialog.timeline_card.isHidden()
        assert not dialog._timing_tbd_info.isHidden()

        dialog.unknown_no_btn.setChecked(False)
        dialog._no_lbl.setText("SZL-2026-145")
        dialog.sig.setText("2026-07-01")
        dialog.t0.setText("2026-07-15")
        dialog.months.setValue(18)
        dialog.save()

        assert dialog.result is not None
        assert dialog.result.no == "SZL-2026-145"
        assert dialog.result.contract_type == "Ana Sözleşme"
        assert dialog.result.signature_date == "2026-07-01"
        assert dialog.result.t0_date == "2026-07-15"
        assert dialog.result.t0_months == 18
        assert dialog.result.completion_date == "2028-01-15"
    finally:
        store.db.close()


def test_store_persists_tbd_to_real_identity_and_timing(tmp_path):
    store = _seed_store(tmp_path)
    try:
        ci = _contract("AKINCI - TBD - 1", "-")
        contract_id = store.write_contract(ci, [], {})
        assert contract_id

        ci.no = "SZL-2026-145"
        ci.contract_type = "Ana Sözleşme"
        ci.signature_date = "2026-07-01"
        ci.t0_date = "2026-07-15"
        ci.t0_months = 18
        ci.completion_date = "2028-01-15"
        store.write_contract(ci, [], {})

        row = store.db.conn.execute(
            "SELECT contract_no,contract_type,is_main,signed_date,t0_date,t0_months,completion_date FROM contracts WHERE id=?",
            (int(contract_id),),
        ).fetchone()
        assert tuple(row) == (
            "SZL-2026-145",
            "Ana Sözleşme",
            1,
            "2026-07-01",
            "2026-07-15",
            18,
            "2028-01-15",
        )
    finally:
        store.db.close()
