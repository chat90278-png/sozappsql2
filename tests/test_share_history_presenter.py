from src.models.share_models import (
    SHARE_STATUS_CANCELLED,
    SHARE_STATUS_MERGED,
    SHARE_STATUS_OPEN,
    SHARE_STATUS_PARTIALLY_MERGED,
    SHARE_STATUS_REJECTED,
    SHARE_STATUS_RETURNED,
)
from src.services.share_history_service import ShareHistoryRecord
from src.ui.presenters.share_history_presenter import (
    display_share_filename,
    format_share_history_datetime,
    present_share_permission,
    present_merge_result,
    present_share_status,
    summarize_share_history,
)


def _record(status=SHARE_STATUS_OPEN, filename="share.sts", package_id="abcdef123456"):
    return ShareHistoryRecord(
        id=1,
        share_package_id=package_id,
        contract_id=1,
        contract_merge_uid="contract-1",
        source_contract_revision=1,
        permission_mode="edit",
        share_format_version=2,
        snapshot_format_version=1,
        base_snapshot_sha256="sha",
        created_at="2026-07-08T09:10:00",
        exported_filename=filename,
        status=status,
    )


def test_status_labels_and_roles_cover_lifecycle_values():
    expected = {
        SHARE_STATUS_OPEN: ("Açık", "info"),
        SHARE_STATUS_RETURNED: ("Geri Döndü", "attention"),
        SHARE_STATUS_MERGED: ("Birleştirildi", "success"),
        SHARE_STATUS_PARTIALLY_MERGED: ("Kısmi Birleştirildi", "warning"),
        SHARE_STATUS_CANCELLED: ("İptal Edildi", "neutral"),
        SHARE_STATUS_REJECTED: ("Reddedildi", "error"),
        "LEGACY": ("Bilinmeyen Durum", "neutral"),
    }
    for status, (label, role) in expected.items():
        presentation = present_share_status(status)
        assert presentation.label == label
        assert presentation.role == role


def test_permission_date_and_filename_fallbacks_are_user_friendly():
    assert present_share_permission("view") == "Görüntüleme"
    assert present_share_permission("EDIT") == "Düzenleme"
    assert present_share_permission("owner") == "Bilinmeyen Yetki"
    assert format_share_history_datetime("") == "Tarih bilgisi yok"
    assert format_share_history_datetime("2026-07-08T09:10:00") == "08.07.2026 09:10"
    assert display_share_filename(_record(filename="Share.sts")) == "Share.sts"
    assert display_share_filename(_record(filename="", package_id="1234567890")) == "Paylaşım 12345678"


def test_summary_counts_statuses_without_mutating_records():
    records = [
        _record(SHARE_STATUS_OPEN),
        _record(SHARE_STATUS_MERGED),
        _record(SHARE_STATUS_MERGED),
        _record(SHARE_STATUS_PARTIALLY_MERGED),
        _record(SHARE_STATUS_CANCELLED),
        _record(SHARE_STATUS_REJECTED),
        _record(SHARE_STATUS_RETURNED),
    ]
    summary = summarize_share_history(records)
    assert summary.total == 7
    assert summary.open_count == 1
    assert summary.merged_count == 2
    assert summary.partially_merged_count == 1
    assert summary.cancelled_count == 1
    assert summary.rejected_count == 1
    assert summary.returned_count == 1


def test_merge_result_presenter_shows_recorded_merged_and_partial_counts():
    merged = _record(SHARE_STATUS_MERGED)
    object.__setattr__(merged, "merge_result_operations_applied", 18)
    object.__setattr__(merged, "merge_result_operations_skipped", 0)
    object.__setattr__(merged, "merged_at", "2026-07-08 09:10:00")
    shown = present_merge_result(merged)
    assert shown.visible is True
    assert shown.recorded is True
    assert "18" in shown.summary_label
    assert "atlandı" not in shown.summary_label
    assert shown.merged_at_label == "08.07.2026 09:10"

    partial = _record(SHARE_STATUS_PARTIALLY_MERGED)
    object.__setattr__(partial, "merge_result_operations_applied", 12)
    object.__setattr__(partial, "merge_result_operations_skipped", 3)
    shown = present_merge_result(partial)
    assert shown.visible is True
    assert shown.recorded is True
    assert "12" in shown.summary_label
    assert "3" in shown.summary_label


def test_merge_result_presenter_distinguishes_legacy_unknown_from_zero_result():
    legacy = _record(SHARE_STATUS_MERGED)
    shown = present_merge_result(legacy)
    assert shown.visible is True
    assert shown.recorded is False
    assert "eski sürüm" in shown.summary_label
    assert "0 değişiklik uygulandı" not in shown.summary_label

    zero = _record(SHARE_STATUS_MERGED)
    object.__setattr__(zero, "merge_result_operations_applied", 0)
    object.__setattr__(zero, "merge_result_operations_skipped", 0)
    shown = present_merge_result(zero)
    assert shown.visible is True
    assert shown.recorded is True
    assert "yeni değişiklik yoktu" in shown.summary_label


def test_merge_result_presenter_ignores_non_final_statuses_and_malformed_counts():
    for status in [SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED, SHARE_STATUS_CANCELLED, SHARE_STATUS_REJECTED]:
        record = _record(status)
        object.__setattr__(record, "merge_result_operations_applied", 4)
        object.__setattr__(record, "merge_result_operations_skipped", 1)
        assert present_merge_result(record).visible is False

    malformed = _record(SHARE_STATUS_PARTIALLY_MERGED)
    object.__setattr__(malformed, "merge_result_operations_applied", -4)
    object.__setattr__(malformed, "merge_result_operations_skipped", 1)
    shown = present_merge_result(malformed)
    assert shown.visible is True
    assert shown.recorded is False
