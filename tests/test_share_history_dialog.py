import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"PySide6 Qt runtime unavailable: {exc}", allow_module_level=True)

from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_OPEN, SHARE_STATUS_PARTIALLY_MERGED
from src.services.share_history_service import ShareHistoryRecord
from src.ui.dialogs.share_history_dialog import ShareHistoryDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _record(status=SHARE_STATUS_OPEN, filename="share.sts", package_id="pkg-1", applied=None, skipped=None, merged_at=""):
    return ShareHistoryRecord(
        id=1,
        share_package_id=package_id,
        contract_id=1,
        contract_merge_uid="contract-1",
        source_contract_revision=1,
        permission_mode="edit",
        share_format_version=2,
        snapshot_format_version=1,
        base_snapshot_sha256="abc123456789",
        created_at="2026-07-08T09:10:00",
        exported_filename=filename,
        status=status,
        merge_result_operations_applied=applied,
        merge_result_operations_skipped=skipped,
        merged_at=merged_at,
    )


def test_history_dialog_empty_state_and_refresh(app):
    calls = []
    dialog = ShareHistoryDialog("C-1", [], refresh_callback=lambda: calls.append(1) or [_record()], parent=None)
    assert dialog.windowTitle() == "Paylaşım Geçmişi"
    assert "0 paylaşım" in dialog._summary_label.text()
    dialog.refresh()
    assert calls == [1]
    assert "1 paylaşım" in dialog._summary_label.text()


def test_history_dialog_renders_status_and_permission_labels(app):
    dialog = ShareHistoryDialog("C-1", [_record(SHARE_STATUS_OPEN, "open.sts"), _record(SHARE_STATUS_MERGED, "merged.sts", "pkg-2")], parent=None)
    texts = [w.text() for w in dialog.findChildren(type(dialog._summary_label))]
    joined = "\n".join(texts)
    assert "open.sts" in joined
    assert "merged.sts" in joined
    assert "Açık" in joined
    assert "Birleştirildi" in joined
    assert "Düzenleme" in joined


def _dialog_text(dialog: ShareHistoryDialog) -> str:
    return "\n".join(w.text() for w in dialog.findChildren(QLabel))


def test_history_dialog_renders_recorded_merge_result_summaries_and_timestamp(app):
    dialog = ShareHistoryDialog(
        "C-1",
        [
            _record(SHARE_STATUS_MERGED, "merged.sts", "pkg-merged", applied=18, skipped=0, merged_at="2026-07-08 09:10:00"),
            _record(SHARE_STATUS_PARTIALLY_MERGED, "partial.sts", "pkg-partial", applied=12, skipped=3, merged_at="2026-07-08 10:11:00"),
        ],
        parent=None,
    )

    joined = _dialog_text(dialog)

    assert "18 değişiklik uygulandı" in joined
    assert "12 değişiklik uygulandı" in joined
    assert "3 değişiklik atlandı" in joined
    assert "Birleştirme: 08.07.2026 09:10" in joined
    assert "Birleştirme: 08.07.2026 10:11" in joined


def test_history_dialog_hides_open_result_counts_and_shows_legacy_fallback(app):
    dialog = ShareHistoryDialog(
        "C-1",
        [
            _record(SHARE_STATUS_OPEN, "open.sts", "pkg-open", applied=4, skipped=1, merged_at="2026-07-08 09:10:00"),
            _record(SHARE_STATUS_MERGED, "legacy.sts", "pkg-legacy"),
        ],
        parent=None,
    )

    joined = _dialog_text(dialog)

    assert "open.sts" in joined
    assert "4 değişiklik uygulandı" not in joined
    assert "1 değişiklik atlandı" not in joined
    assert "Birleştirme sonucu kaydı eski sürümde oluşturulmuş." in joined


def test_history_dialog_refresh_reloads_records_and_result_summary(app):
    states = [
        [_record(SHARE_STATUS_OPEN, "share.sts", "pkg-refresh")],
        [_record(SHARE_STATUS_MERGED, "share.sts", "pkg-refresh", applied=2, skipped=0, merged_at="2026-07-08 12:34:00")],
    ]
    calls = {"n": 0}

    def refresh_records():
        calls["n"] += 1
        return states[min(calls["n"], 1)]

    dialog = ShareHistoryDialog("C-1", states[0], refresh_callback=refresh_records, parent=None)
    assert "Açık" in _dialog_text(dialog)
    assert "2 değişiklik uygulandı" not in _dialog_text(dialog)

    dialog.refresh()
    joined = _dialog_text(dialog)

    assert calls["n"] == 1
    assert "Birleştirildi" in joined
    assert "2 değişiklik uygulandı" in joined
    assert "Birleştirme: 08.07.2026 12:34" in joined


def _button_texts(dialog: ShareHistoryDialog) -> list[str]:
    from PySide6.QtWidgets import QPushButton
    return [w.text() for w in dialog.findChildren(QPushButton)]


def test_history_dialog_cancel_action_visible_only_for_authorized_cancelable_rows(app):
    dialog = ShareHistoryDialog(
        "C-1",
        [_record(SHARE_STATUS_OPEN, "open.sts", "pkg-open"), _record(SHARE_STATUS_MERGED, "merged.sts", "pkg-merged")],
        cancel_callback=lambda _record: None,
        can_cancel=True,
        parent=None,
    )
    assert _button_texts(dialog).count("Paylaşımı İptal Et") == 1

    unauthorized = ShareHistoryDialog(
        "C-1",
        [_record(SHARE_STATUS_OPEN, "open.sts", "pkg-open")],
        cancel_callback=lambda _record: None,
        can_cancel=False,
        parent=None,
    )
    assert "Paylaşımı İptal Et" not in _button_texts(unauthorized)


def test_history_dialog_active_summary_decrements_after_cancel_refresh(app):
    states = [
        [_record(SHARE_STATUS_OPEN, "open.sts", "pkg-open")],
        [_record("CANCELLED", "open.sts", "pkg-open")],
    ]
    calls = {"n": 0}

    def refresh_records():
        calls["n"] += 1
        return states[min(calls["n"], 1)]

    dialog = ShareHistoryDialog("C-1", states[0], refresh_callback=refresh_records, can_cancel=True, parent=None)
    assert "1 aktif" in dialog._summary_label.text()
    dialog.refresh()
    assert "1 aktif" not in dialog._summary_label.text()
    assert "iptal" in dialog._summary_label.text()
