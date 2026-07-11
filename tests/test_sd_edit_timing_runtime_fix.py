from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.models.app_models import ContractInfo
from src.services.multiplatform_contract_persistence import install_multiplatform_contract_persistence_fix
from src.services.sts_store import STSStore
from src.ui.dialogs.contract_edit_dialog import ContractEditDialog
from src.ui.dialogs.contract_edit_timing_runtime_fix import install_contract_edit_timing_fix
from src.ui.dialogs.sd_edit_timing_runtime_fix import install_sd_edit_timing_fix


install_multiplatform_contract_persistence_fix()
install_contract_edit_timing_fix()
install_sd_edit_timing_fix()


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _seed_store(tmp_path) -> STSStore:
    store = STSStore(tmp_path / "sd-timing-test.sts", actor="Test")
    store.get_platform_id("AKINCI", create=True)
    store.get_user_id("KKK", create=True)
    store.save()
    return store


def _sd_contract(
    signature_date: str = "",
    t0_date: str = "",
    t0_months: int = 0,
    completion_date: str = "",
) -> ContractInfo:
    return ContractInfo(
        no="141414",
        platform="AKINCI",
        user="KKK",
        users=["KKK"],
        yi_yd="Yİ",
        contract_type="SD-1",
        signature_date=signature_date,
        t0_date=t0_date,
        t0_months=t0_months,
        completion_date=completion_date,
        status="Başlanmadı",
        note="",
        platform_names=["AKINCI"],
    )


def test_sd_dialog_shows_timing_fields_and_collects_dates(tmp_path):
    _app()
    store = _seed_store(tmp_path)
    try:
        dialog = ContractEditDialog(
            store,
            _sd_contract(),
            title_text="SD Ekleme Tablosu",
            save_text="SD Ekle",
        )

        assert hasattr(dialog, "sig")
        assert hasattr(dialog, "timeline_card")
        assert not dialog.timeline_card.isHidden()
        assert not hasattr(dialog, "unknown_no_btn")

        dialog.sig.setText("2026-07-08")
        dialog.t0.setText("2026-07-08")
        dialog.months.setValue(16)
        assert dialog.completion.text() == "2027-11-08"

        dialog.save()
        assert dialog.result is not None
        assert dialog.result.contract_type == "SD-1"
        assert dialog.result.signature_date == "2026-07-08"
        assert dialog.result.t0_date == "2026-07-08"
        assert dialog.result.t0_months == 16
        assert dialog.result.completion_date == "2027-11-08"
    finally:
        store.db.close()


def test_existing_sd_timing_is_preloaded_and_recalculates(tmp_path):
    _app()
    store = _seed_store(tmp_path)
    try:
        dialog = ContractEditDialog(
            store,
            _sd_contract(
                signature_date="2026-01-10",
                t0_date="2026-01-31",
                t0_months=1,
                completion_date="2026-02-28",
            ),
        )

        assert dialog.sig.text() == "2026-01-10"
        assert dialog.t0.text() == "2026-01-31"
        assert dialog.months.value() == 1
        assert dialog.completion.text() == "2026-02-28"

        dialog.t0.setText("2024-01-31")
        assert dialog.completion.text() == "2024-02-29"
    finally:
        store.db.close()


def test_sd_timing_can_remain_empty_for_legacy_flow(tmp_path):
    _app()
    store = _seed_store(tmp_path)
    try:
        dialog = ContractEditDialog(store, _sd_contract())
        dialog.save()

        assert dialog.result is not None
        assert dialog.result.signature_date == ""
        assert dialog.result.t0_date == ""
        assert dialog.result.t0_months == 0
        assert dialog.result.completion_date == ""
    finally:
        store.db.close()
