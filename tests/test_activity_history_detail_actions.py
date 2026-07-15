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
    action: str = "contract_updated",
    platform_name: str | None = "AKINCI",
    contract_no: str | None = "AKINCI - TBD - 4",
    changed_fields=(),
    operation_group_key: str | None = None,
) -> ActivityHistoryItem:
    action_label = {
        "contract_deleted": "Sözleşme silindi",
        "contract_updated": "Sözleşme güncellendi",
    }.get(action, "Sözleşme güncellendi")
    return ActivityHistoryItem(
        id=item_id,
        occurred_at="2026-07-15T06:00:00Z",
        category="USER",
        action=action,
        action_label=action_label,
        status="SUCCESS",
        actor_display_name="Serhat",
        title=action_label,
        summary="Sözleşme bilgileri güncellendi",
        entity_type="contract",
        entity_label="Sözleşme",
        platform_name=platform_name,
        contract_no=contract_no,
        changed_fields=tuple(changed_fields),
        changed_fields_parse_error=False,
        operation_group_key=operation_group_key,
        technical=None,
    )


class FakeStore:
    def __init__(self, items, *, contract_ids=None, rebuilt_rows=None):
        self.items = tuple(items)
        self.contract_ids = dict(contract_ids or {})
        self.rebuilt_rows = list(rebuilt_rows or [])

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

    def activity_contract_id_for_log(self, activity_log_id):
        return self.contract_ids.get(int(activity_log_id))

    def build_contract_index(self):
        return list(self.rebuilt_rows)


class Host(QWidget):
    def __init__(self, rows=None):
        super().__init__()
        self.opened = None
        self.contract_index = list(
            rows
            if rows is not None
            else [
                {
                    "platform": "AKINCI",
                    "no": "AKINCI - TBD - 4",
                    "type": "Ana Sözleşme",
                    "row": 7,
                }
            ]
        )

    def open_contract_item(self, item):
        self.opened = item


def _open_dialog(app, item, store, host):
    dialog = ActivityLogDialog(
        store,
        parent=host,
        access=ACCESS,
        auto_load=False,
    )
    dialog.resize(1366, 768)
    dialog.show()
    assert dialog.refresh_logs()
    dialog.select_item(item)
    QApplication.processEvents()
    return dialog


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
    dialog = _open_dialog(app, item, FakeStore((item,)), host)

    assert dialog.details.open_contract_button.isVisible()
    assert dialog.details.open_contract_button.height() >= 30
    dialog.details.open_contract_button.click()
    QApplication.processEvents()

    assert host.opened is not None
    assert host.opened["no"] == "AKINCI - TBD - 4"
    dialog.close()
    host.close()


def test_contract_navigation_prefers_stable_contract_id(app):
    item = _item(
        item_id=11,
        platform_name="Eski Platform",
        contract_no="ESKI-NO",
    )
    current = {
        "platform": "Yeni Platform",
        "no": "YENI-NO",
        "type": "Ana Sözleşme",
        "row": 42,
    }
    host = Host([current])
    store = FakeStore((item,), contract_ids={11: 42})
    dialog = _open_dialog(app, item, store, host)

    dialog.details.open_contract_button.click()
    QApplication.processEvents()

    assert host.opened == current
    dialog.close()
    host.close()


def test_contract_navigation_normalizes_platform_and_contract_text(app):
    item = _item(
        platform_name="ANKA – III",
        contract_no=" demo plus 060 ",
    )
    current = {
        "platform": "ANKA-III",
        "no": "DEMO-PLUS-060",
        "type": "Ana Sözleşme",
        "row": 8,
    }
    host = Host([current])
    dialog = _open_dialog(app, item, FakeStore((item,)), host)

    dialog.details.open_contract_button.click()
    QApplication.processEvents()

    assert host.opened == current
    dialog.close()
    host.close()


def test_contract_navigation_rebuilds_stale_index(app):
    item = _item(contract_no="DEMO-CURRENT-010", platform_name="HÜRJET")
    current = {
        "platform": "HÜRJET",
        "no": "DEMO-CURRENT-010",
        "type": "Ana Sözleşme",
        "row": 91,
    }
    host = Host([{"platform": "AKINCI", "no": "OTHER", "row": 4}])
    store = FakeStore((item,), rebuilt_rows=[current])
    dialog = _open_dialog(app, item, store, host)

    dialog.details.open_contract_button.click()
    QApplication.processEvents()

    assert host.opened == current
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


def test_contract_button_hides_for_deleted_contract(app):
    item = _item(action="contract_deleted")
    dialog = ActivityLogDialog(
        FakeStore((item,), contract_ids={item.id: 7}),
        access=ACCESS,
        auto_load=False,
    )
    assert dialog.refresh_logs()
    dialog.select_item(item)
    assert dialog.details.open_contract_button.isHidden()
    dialog.close()
