from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import ActivityHistoryItem, ActivityHistoryPage
from src.ui.activity_history.labels import visible_action_label
from src.ui.activity_history.styles import ACTIVITY_HISTORY_QSS
from src.ui.activity_history.widgets import TimelineCard
from src.ui.dialogs.activity_logs import ActivityLogDialog


NORMAL_ACCESS = ActivityHistoryAccess(
    True,
    frozenset({"USER", "MANAGEMENT"}),
    False,
    False,
    False,
)


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _item(
    item_id: int = 1,
    *,
    action: str = "contract_tags_updated",
    action_label: str = "Contract tags updated",
) -> ActivityHistoryItem:
    return ActivityHistoryItem(
        id=item_id,
        occurred_at="2026-07-14T10:30:00Z",
        category="USER",
        action=action,
        action_label=action_label,
        status="SUCCESS",
        actor_display_name="Serhat",
        title=action_label,
        summary="Sözleşme etiketleri güncellendi",
        entity_type="contract",
        entity_label="Sözleşme",
        platform_name="AKINCI",
        contract_no="AKINCI - TBD - 4",
        changed_fields=(),
        changed_fields_parse_error=False,
        operation_group_key=None,
        technical=None,
    )


class FakeStore:
    def __init__(self, page: ActivityHistoryPage):
        self.page = page

    def query_activity_history(self, query, *, access, include_technical=False):
        return self.page


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("contract_tags_updated", "Sözleşme etiketleri güncellendi"),
        ("contract_status_changed", "Sözleşme durumu değiştirildi"),
        ("system_component_updated", "Sistem bileşeni güncellendi"),
        ("excel_export_failed", "Excel dışa aktarımı başarısız oldu"),
        ("user_deleted", "Kullanıcı silindi"),
    ],
)
def test_known_action_codes_have_turkish_labels(action, expected):
    assert visible_action_label(action) == expected


def test_unknown_action_fallback_hides_underscores():
    label = visible_action_label("custom_record_updated")
    assert "_" not in label
    assert label.startswith("Custom")


def test_timeline_card_uses_turkish_label_and_compact_height(app):
    card = TimelineCard(_item())
    assert card.display_action_label == "Sözleşme etiketleri güncellendi"
    assert card.maximumHeight() <= 92
    assert card.icon.width() == 32
    card.deleteLater()


def test_loaded_count_uses_readable_continuation_text(app):
    page = ActivityHistoryPage((_item(),), "cursor-1", True)
    dialog = ActivityLogDialog(
        FakeStore(page),
        access=NORMAL_ACCESS,
        auto_load=False,
        now_provider=lambda: datetime(2026, 7, 14, 12, tzinfo=timezone.utc),
    )
    assert dialog.refresh_logs()
    assert dialog.loaded_label.text() == "1 kayıt yüklendi · devamı var"
    assert not dialog.loaded_label.text().endswith("+")
    dialog.close()


def test_detail_title_translates_legacy_english_action(app):
    item = _item()
    dialog = ActivityLogDialog(
        FakeStore(ActivityHistoryPage((item,), None, False)),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    assert dialog.refresh_logs()
    dialog.select_item(item)
    assert dialog.details.title.text() == "Sözleşme etiketleri güncellendi"
    dialog.close()


def test_dialog_root_spacing_is_compact(app):
    dialog = ActivityLogDialog(
        FakeStore(ActivityHistoryPage((_item(),), None, False)),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    margins = dialog.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        10,
        10,
        10,
        10,
    )
    assert dialog.layout().spacing() == 8
    dialog.close()


def test_narrow_layout_keeps_vertical_splitter(app):
    dialog = ActivityLogDialog(
        FakeStore(ActivityHistoryPage((_item(),), None, False)),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    dialog.resize(920, 620)
    dialog.show()
    QApplication.processEvents()
    assert dialog.splitter.orientation() == Qt.Vertical
    dialog.close()


def test_filter_widgets_use_overlay_chevrons_and_segmented_dropdowns(app):
    dialog = ActivityLogDialog(
        FakeStore(ActivityHistoryPage((_item(),), None, False)),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    assert set(dialog._filter_chevrons) == {
        dialog.action,
        dialog.limit,
        dialog.date_from,
        dialog.date_to,
    }
    assert all(label.text() == "⌄" for label in dialog._filter_chevrons.values())
    assert "QComboBox#activityFilter::drop-down" in ACTIVITY_HISTORY_QSS
    assert "QDateEdit#activityFilter::drop-down" in ACTIVITY_HISTORY_QSS
    assert "QLabel#activityFilterChevron" in ACTIVITY_HISTORY_QSS
    assert "QComboBox#activityFilter QAbstractItemView" in ACTIVITY_HISTORY_QSS
    dialog.close()


def test_detail_panel_removes_gray_fill_from_readable_sections():
    assert "QFrame#activityDetailsPanel QWidget" in ACTIVITY_HISTORY_QSS
    assert "QLabel#activityDetailMeta" in ACTIVITY_HISTORY_QSS
    assert "background: transparent" in ACTIVITY_HISTORY_QSS
    assert "alternate-background-color: #ffffff" in ACTIVITY_HISTORY_QSS
    assert "QFrame#activityDetailsPanel QHeaderView::section" in ACTIVITY_HISTORY_QSS


def test_splitter_children_fill_available_width(app):
    page = ActivityHistoryPage((_item(),), None, False)
    dialog = ActivityLogDialog(
        FakeStore(page),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    dialog.resize(1366, 768)
    dialog.show()
    assert dialog.refresh_logs()
    QApplication.processEvents()
    child_width = dialog.left_stack.width() + dialog.details.width()
    assert child_width >= dialog.splitter.width() - 12
    dialog.close()


def test_timeline_content_tracks_viewport_width(app):
    page = ActivityHistoryPage((_item(),), None, False)
    dialog = ActivityLogDialog(
        FakeStore(page),
        access=NORMAL_ACCESS,
        auto_load=False,
    )
    dialog.resize(1366, 768)
    dialog.show()
    assert dialog.refresh_logs()
    QApplication.processEvents()
    dialog._sync_timeline_width()
    assert dialog.timeline._content.minimumWidth() >= dialog.timeline.viewport().width() - 4
    dialog.close()
