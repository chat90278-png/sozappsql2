import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"PySide6 Qt runtime unavailable: {exc}", allow_module_level=True)

from src.models.share_models import SHARE_STATUS_MERGED, SHARE_STATUS_OPEN
from src.services.share_history_service import ShareHistoryRecord
from src.ui.dialogs.share_history_dialog import ShareHistoryDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _record(status=SHARE_STATUS_OPEN, filename="share.sts", package_id="pkg-1"):
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
