from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
try:
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMessageBox
except ImportError as exc:
    pytest.skip(f"PySide6 Qt runtime unavailable: {exc}", allow_module_level=True)

from src.domain.share_merge_resolution import resolve_merge_plan
from src.models.app_models import DeliveryInfo
from src.models.share_merge_resolution_models import MergeDecisionKind
from src.services.share_merge_apply_service import MergeSourceChangedError
from src.services.share_merge_service import prepare_share_merge_plan
from src.ui.dialogs.share_merge_dialog import ShareMergeDialog
from src.ui.presenters.share_merge_error_presenter import present_share_merge_error

from tests.test_share_assignment_merge import _save_units
from tests.test_share_merge_end_to_end import _edit_note, _prepare_keep_both_conflict, make_registered_share


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _conflict_dialog(tmp_path: Path, *, apply_callback=None, preflight_callback=None):
    source, share, _ci, _cid, metadata = make_registered_share(tmp_path)
    _edit_note(source, "LOCAL")
    _edit_note(share, "REMOTE")
    plan = prepare_share_merge_plan(source, share.path)
    dialog = ShareMergeDialog(
        merge_plan=plan,
        share_path=share.path,
        metadata=None,
        preflight_callback=preflight_callback or (lambda resolved, allow_partial: None),
        apply_callback=apply_callback or (lambda resolved, allow_partial: None),
    )
    return dialog, source, share, metadata


def _conflict_combo(dialog: ShareMergeDialog) -> QComboBox:
    for target_id, combo in dialog._decision_combos.items():
        item = dialog.controller.item_by_target(target_id)
        if item and item.is_conflict:
            return combo
    raise AssertionError("conflict combo not found")


def _choose(combo: QComboBox, decision: MergeDecisionKind) -> None:
    idx = combo.findData(decision.value)
    assert idx >= 0
    combo.setCurrentIndex(idx)


def test_dialog_instantiation_unresolved_conflict_and_explicit_decision(qapp, tmp_path):
    dialog, source, share, _metadata = _conflict_dialog(tmp_path)
    try:
        assert dialog.windowTitle() == "Paylaşım Değişikliklerini Birleştir"
        assert dialog.findChild(type(dialog.apply_btn), "shareMergeApply") is dialog.apply_btn
        assert dialog.cancel_btn.text() == "Vazgeç"
        assert not dialog.apply_btn.isEnabled()
        assert "tüm çakışmalar" in dialog.status_label.text()

        combo = _conflict_combo(dialog)
        assert combo.currentData() is None
        _choose(combo, MergeDecisionKind.LOCAL_KEEP)

        assert dialog.controller.explicit_decisions
        assert next(iter(dialog.controller.explicit_decisions.values())) == MergeDecisionKind.LOCAL_KEEP
        assert dialog.controller.resolved_plan.summary["unresolved_conflict_count"] == 0
        assert dialog.apply_btn.isEnabled()
    finally:
        dialog.close(); source.db.close(); share.db.close()


def test_document_keep_both_visibility_uses_allowed_decisions(qapp, tmp_path):
    normal, source, share, _metadata = _conflict_dialog(tmp_path)
    try:
        normal_combo = _conflict_combo(normal)
        normal_options = {normal_combo.itemData(i) for i in range(normal_combo.count())}
        assert MergeDecisionKind.DOCUMENT_KEEP_BOTH.value not in normal_options
    finally:
        normal.close(); source.db.close(); share.db.close()

    source2, share2, _cid, _fid, _metadata2 = _prepare_keep_both_conflict(tmp_path)
    plan = prepare_share_merge_plan(source2, share2.path)
    doc_dialog = ShareMergeDialog(
        merge_plan=plan,
        share_path=share2.path,
        metadata=None,
        preflight_callback=lambda resolved, allow_partial: None,
        apply_callback=lambda resolved, allow_partial: None,
    )
    try:
        doc_combo = _conflict_combo(doc_dialog)
        doc_options = {doc_combo.itemData(i) for i in range(doc_combo.count())}
        assert MergeDecisionKind.DOCUMENT_KEEP_BOTH.value in doc_options
    finally:
        doc_dialog.close(); source2.db.close(); share2.db.close()


def test_skip_partial_warning_and_button_state(qapp, tmp_path):
    dialog, source, share, _metadata = _conflict_dialog(tmp_path)
    try:
        combo = _conflict_combo(dialog)
        _choose(combo, MergeDecisionKind.SKIP)
        assert dialog.controller.resolved_plan.is_partial
        assert dialog.apply_btn.isEnabled()
        assert dialog.partial_warning.isVisible()
    finally:
        dialog.close(); source.db.close(); share.db.close()


def test_duplicate_submit_busy_guard_and_failure_state(qapp, monkeypatch, tmp_path):
    calls = {"preflight": 0, "apply": 0}

    def preflight(_resolved, _allow_partial):
        calls["preflight"] += 1

    def apply(_resolved, _allow_partial):
        calls["apply"] += 1
        raise MergeSourceChangedError("stale")

    dialog, source, share, _metadata = _conflict_dialog(tmp_path, preflight_callback=preflight, apply_callback=apply)
    warnings = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: warnings.append((self.windowTitle(), self.text(), self.informativeText())) or QMessageBox.AcceptRole)
    monkeypatch.setattr(dialog, "_confirm_apply", lambda _resolved: True)
    try:
        _choose(_conflict_combo(dialog), MergeDecisionKind.LOCAL_KEEP)
        dialog._set_busy(True, "busy")
        dialog._submit()
        assert calls == {"preflight": 0, "apply": 0}
        assert not dialog.apply_btn.isEnabled()
        assert not dialog.cancel_btn.isEnabled()
        dialog._set_busy(False)

        dialog._submit()
        assert calls == {"preflight": 1, "apply": 1}
        assert dialog.apply_result is None
        assert dialog.apply_btn.isEnabled()
        assert dialog.cancel_btn.isEnabled()
        assert warnings and "Ana STS" in warnings[-1][1]
    finally:
        dialog.close(); source.db.close(); share.db.close()


def test_unexpected_error_presenter_is_safe():
    presentation = present_share_merge_error(RuntimeError("raw bytes deadbeef"))
    assert presentation.severity == "error"
    assert "Beklenmeyen" in presentation.message
    assert "raw bytes" not in presentation.message


def test_mixed_graph_last_decision_enables_button_and_clear_disables(qapp, tmp_path):
    source, share, _ci, _cid, _metadata = make_registered_share(tmp_path)
    _save_units(source, identifier="LOCAL-SER", note="LOCAL-Q")
    _save_units(share, identifier="REMOTE-SER", note="REMOTE-Q")
    _edit_note(source, "LOCAL-NOTE")
    _edit_note(share, "REMOTE-NOTE")

    ci, systems, deliveries = share.load_contract_structure("AKINCI", "C-1", contract_type="Ana Sözleşme")
    remote_delivery = DeliveryInfo("DEL-REMOTE", "PLAN", "", "", {"C": 1}, {"C": 0})
    remote_delivery.component_units = {
        "C": [{"slot_no": 1, "identifier": "REMOTE-NEW", "is_delivered": 0, "note": "REMOTE-QUEUE"}]
    }
    deliveries["SYS"].append(remote_delivery)
    share.write_contract(ci, systems, deliveries)

    plan = prepare_share_merge_plan(source, share.path)
    dialog = ShareMergeDialog(
        merge_plan=plan,
        share_path=share.path,
        metadata=None,
        preflight_callback=lambda resolved, allow_partial: None,
        apply_callback=lambda resolved, allow_partial: None,
    )
    try:
        initial = dialog.controller.live_summary()
        assert initial["unresolved_conflict_count"] >= 2
        assert initial["structural_issue_count"] == 0
        assert not dialog.apply_btn.isEnabled()

        conflict_combos = [
  combo
  for target_id, combo in dialog._decision_combos.items()
  if (dialog.controller.item_by_target(target_id) and dialog.controller.item_by_target(target_id).is_conflict)
        ]
        assert len(conflict_combos) >= 2
        for combo in conflict_combos[:-1]:
  _choose(combo, MergeDecisionKind.REMOTE_USE)
        assert not dialog.apply_btn.isEnabled()

        _choose(conflict_combos[-1], MergeDecisionKind.REMOTE_USE)
        summary = dialog.controller.live_summary()
        assert summary["unresolved_conflict_count"] == 0
        assert summary["structural_issue_count"] == 0
        assert dialog.apply_btn.isEnabled()
        assert "Plan doğrulama" not in dialog.status_label.text()

        conflict_combos[-1].setCurrentIndex(0)
        assert dialog.controller.live_summary()["unresolved_conflict_count"] == 1
        assert not dialog.apply_btn.isEnabled()

        caption = dialog.findChild(QLabel, "shareMergeDecisionCaption")
        assert caption is not None
        assert "QDialog#shareMergeDialog QLabel#shareMergeDecisionCaption" in dialog.styleSheet()
    finally:
        dialog.close(); source.db.close(); share.db.close()
