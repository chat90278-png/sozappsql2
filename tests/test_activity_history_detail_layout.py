from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import ActivityHistoryItem, ActivityHistoryPage
from src.ui.dialogs.activity_logs import ActivityLogDialog


ACCESS = ActivityHistoryAccess(
    True,
    frozenset({"USER", "MANAGEMENT"}),
    False,
    False,
    False,
)


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _item() -> ActivityHistoryItem:
    return ActivityHistoryItem(
        id=1,
        occurred_at="2026-07-15T06:00:00Z",
        category="USER",
        action="contract_tags_updated",
        action_label="Sözleşme etiketleri güncellendi",
        status="SUCCESS",
        actor_display_name="Serhat",
        title="Sözleşme etiketleri güncellendi",
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
    def query_activity_history(self, query, *, access, include_technical=False):
        return ActivityHistoryPage((_item(),), None, False)

    def platform_names(self):
        return ["AKINCI"]


def test_detail_values_stay_top_aligned_without_optional_sections(app):
    item = _item()
    dialog = ActivityLogDialog(
        FakeStore(),
        access=ACCESS,
        auto_load=False,
    )
    dialog.resize(1366, 768)
    dialog.show()
    assert dialog.refresh_logs()
    dialog.select_item(item)
    QApplication.processEvents()

    details = dialog.details
    content = details.scroll.widget()
    layout = content.layout()

    assert layout.alignment() & Qt.AlignTop
    assert layout.stretch(layout.count() - 1) == 1
    assert details.changed.isHidden()
    assert details.operation_events.isHidden()

    title_gap = details.title.y() - details.subtitle.geometry().bottom()
    summary_gap = details.summary.y() - details.title.geometry().bottom()
    meta_gap = details.meta.y() - details.summary.geometry().bottom()
    button_gap = details.open_contract_button.y() - details.meta.geometry().bottom()

    assert max(title_gap, summary_gap, meta_gap, button_gap) <= 32
    assert details.open_contract_button.geometry().bottom() < content.height() * 0.55
    assert details.title.text() == "Sözleşme etiketleri güncellendi"
    assert details.summary.text() == "Sözleşme etiketleri güncellendi"
    assert "AKINCI - TBD - 4" in details.meta.text()

    dialog.close()
