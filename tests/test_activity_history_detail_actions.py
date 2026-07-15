from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import (
    ActivityFieldChange,
    ActivityHistoryItem,
    ActivityHistoryPage,
)
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


def _item(
    item_id: int = 1,
    *,
    contract_no: str | None = "AKINCI - TBD - 4",
    changed_fields=(),
    operation_group_key: str | None = None,
) -> ActivityHistoryItem:
    return ActivityHistoryItem(
        id=item_id,
        occurred_at="2026-07-15T06:00:00Z",
        category="USER",
        action="contract_updated",
        action_label="Sözleşme güncellendi",
        status="SUCCESS",
        actor_display_name="Serhat",
        title="Sözleşme güncellendi",
        summary="Sözleşme bilgileri güncellendi",
        entity_type="contract",
        entity_label="Sözleşme",
        platform_name="AKINCI",
        contract_no=contract_no,
        changed_fields=tuple(changed_fields),
        changed_fields_parse_error=False,
        operation_group_key=operation_group_key,
        technical=None,
    )


class FakeStore:
    def __init__(self, items):
        self.items = tuple(items)

    def platform_names(self):
        return ["AKINCI", "BAYRAKTAR TB3"]

    def query_activity_history(self, query, *, access, include_technical=False):
        if query.platform_text:
            items = tuple(
                item for item in self.items if item.platform_name == query.platform_text
            )
        else:
            items = self.items
        return ActivityHistoryPage(items, None, False)

    def get_activity_operation_events_by_group_key(
        self,
        operation_group_key,
        *,
        access,
        limit=200,
    ):
        return self.items


class Host(QWidget):
    def __init__(self):
        super().__init__()
        self.opened = None
        self.contract_index = [
            {
                "platform": "AKINCI",
                "no": "AKINCI - TBD - 4",
                "type": "Ana Sözleşme",
                "row": 7,
            }
        ]

    def open_contract_item(self, item):
        self.opened = item


def test_empty_detail_sections_are_hidden(app):
    item = _item()
    dialog = ActivityLogDialog(
        FakeStore((item,)),
        access=ACCESS,
        auto_load=False,
    )
    assert dialog.refresh_logs()
    dialog.select_item(item)

    assert dialog.details.changed.isHidden()
    assert dialog.details.changed_title.isHidden()
    assert dialog.details.operation_events.isHidden()
    assert dialog.details.operation_title.isHidden()
    dialog.close()


def test_detail_sections_show_only_real_content(app):
    first = _item(
        1,
        changed_fields=(ActivityFieldChange("Durum", "Taslak", "Aktif"),),
        operation_group_key="op_same",
    )
    second = _item(2, operation_group_key="op_same")
    dialog = ActivityLogDialog(
        FakeStore((first, second)),
        access=ACCESS,
        auto_load=False,
    )
    assert dialog.refresh_logs()
    dialog.select_item(first)

    assert not dialog.details.changed.isHidden()
    assert dialog.details.changed.topLevelItemCount() == 1
    assert not dialog.details.operation_events.isHidden()
    assert dialog.details.operation_events.count() == 2
    dialog.close()


def test_platform_filter_is_searchable_dropdown(app):
    item = _item()
    dialog = ActivityLogDialog(
        FakeStore((item,)),
        access=ACCESS,
        auto_load=False,
    )

    assert isinstance(dialog.platform, QComboBox)
    assert dialog.platform.isEditable()
    assert dialog.platform.findData("AKINCI") >= 0
    assert dialog.platform.findData("BAYRAKTAR TB3") >= 0

    dialog.platform.setCurrentIndex(dialog.platform.findData("AKINCI"))
    assert dialog.build_query().platform_text == "AKINCI"
    dialog.close()


def test_contract_button_opens_matching_contract(app):
    item = _item()
    host = Host()
    dialog = ActivityLogDialog(
        FakeStore((item,)),
        parent=host,
        access=ACCESS,
        auto_load=False,
    )
    dialog.resize(1366, 768)
    dialog.show()
    assert dialog.refresh_logs()
    dialog.select_item(item)
    QApplication.processEvents()
    assert dialog.details.open_contract_button.isVisible()
    assert dialog.details.open_contract_button.height() >= 30

    dialog.details.open_contract_button.click()
    QApplication.processEvents()

    assert host.opened is not None
    assert host.opened["no"] == "AKINCI - TBD - 4"
    dialog.close()
    host.close()


def test_contract_button_hides_when_record_has_no_contract(app):
    item = _item(contract_no=None)
    dialog = ActivityLogDialog(
        FakeStore((item,)),
        access=ACCESS,
        auto_load=False,
    )
    assert dialog.refresh_logs()
    dialog.select_item(item)
    assert dialog.details.open_contract_button.isHidden()
    dialog.close()
