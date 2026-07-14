from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QItemSelectionModel, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import (
    ActivityFieldChange,
    ActivityHistoryItem,
    ActivityHistoryPage,
    ActivityHistoryQueryError,
    ActivityTechnicalDetails,
)
from src.services.sts_store import STSStore
from src.ui.activity_history.widgets import TimelineCard, activity_day_label
from src.ui.dialogs.activity_logs import ActivityLogDialog


NORMAL_ACCESS = ActivityHistoryAccess(True, frozenset({"USER", "MANAGEMENT"}), False, False, False)
TECH_ACCESS = ActivityHistoryAccess(
    True,
    frozenset({"USER", "MANAGEMENT", "TECHNICAL"}),
    True,
    True,
    True,
)
DENIED = ActivityHistoryAccess(False, frozenset(), False, False, False)


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _technical(operation_id: str = "operation-secret-id") -> ActivityTechnicalDetails:
    return ActivityTechnicalDetails(
        source="Main UI",
        device_name="PC_TEST",
        actor_staff_id=7,
        actor_admin_id=None,
        session_id="session-safe",
        entity_id="11",
        contract_id=22,
        platform_id=3,
        before={"safe": "old"},
        after={"safe": "new"},
        payload={"safe": "value"},
        technical_payload={"duration_ms": 12},
        event_schema_version=1,
        operation_id=operation_id,
    )


def _item(
    item_id: int = 1,
    *,
    category: str = "USER",
    occurred: str = "2026-07-14T10:30:00Z",
    action: str = "contract_updated",
    actor: str = "Ayşe Personel",
    operation_group_key: str | None = None,
    technical: ActivityTechnicalDetails | None = None,
    changed_fields: tuple[ActivityFieldChange, ...] | None = None,
    parse_error: bool = False,
) -> ActivityHistoryItem:
    return ActivityHistoryItem(
        id=item_id,
        occurred_at=occurred,
        category=category,
        action=action,
        action_label={
            "USER": "Sözleşme güncellendi",
            "MANAGEMENT": "Platform güncellendi",
            "TECHNICAL": "Veritabanı optimize edildi",
        }[category],
        status="SUCCESS",
        actor_display_name=actor,
        title="S-2026/145 sözleşmesini güncelledi",
        summary="Sözleşme durumu güvenli biçimde güncellendi.",
        entity_type="contract",
        entity_label="Sözleşme",
        platform_name="AKINCI",
        contract_no="S-2026/145",
        changed_fields=changed_fields
        if changed_fields is not None
        else (ActivityFieldChange("Durum", "Planlandı", "Devam Ediyor"),),
        changed_fields_parse_error=parse_error,
        operation_group_key=operation_group_key,
        technical=technical,
    )


class FakeStore:
    def __init__(self, pages=None, *, error: Exception | None = None):
        self.pages = list(pages or [ActivityHistoryPage((_item(),), None, False)])
        self.error = error
        self.queries = []
        self.operation_calls = []

    def query_activity_history(self, query, *, access, include_technical=False):
        self.queries.append((query, access, include_technical))
        if self.error:
            raise self.error
        return self.pages.pop(0) if self.pages else ActivityHistoryPage((), None, False)

    def get_activity_operation_events(self, operation_id, *, access, limit=200):
        self.operation_calls.append((operation_id, access, limit))
        return (_item(1, technical=_technical(operation_id), operation_group_key="op_group000001"),)

    def get_activity_operation_events_by_group_key(self, group_key, *, access, limit=200):
        self.operation_calls.append((group_key, access, limit))
        return (_item(1, operation_group_key=group_key), _item(2, operation_group_key=group_key))


@pytest.fixture
def dialog(app):
    value = ActivityLogDialog(FakeStore(), access=NORMAL_ACCESS, auto_load=False)
    yield value
    value.close()


def test_01_view_permission_opens_dialog(app):
    dialog = ActivityLogDialog(FakeStore(), access=NORMAL_ACCESS, auto_load=False)
    assert dialog.windowTitle() == "İşlem Geçmişi"
    dialog.close()


def test_02_permission_missing_rejects_direct_open(app):
    with pytest.raises(PermissionError):
        ActivityLogDialog(FakeStore(), access=DENIED, auto_load=False)


def test_03_normal_user_has_two_tabs(dialog):
    assert set(dialog.tab_buttons) == {"USER", "MANAGEMENT"}


def test_04_technical_user_has_three_tabs(app):
    dialog = ActivityLogDialog(FakeStore(), access=TECH_ACCESS, auto_load=False)
    assert set(dialog.tab_buttons) == {"USER", "MANAGEMENT", "TECHNICAL"}
    dialog.close()


def test_05_user_tab_queries_user_category(dialog):
    dialog.refresh_logs()
    assert dialog.store.queries[-1][0].categories == ("USER",)


def test_06_management_tab_queries_management_category(dialog):
    assert dialog.select_tab("MANAGEMENT")
    assert dialog.store.queries[-1][0].categories == ("MANAGEMENT",)


def test_07_technical_tab_queries_technical_category(app):
    dialog = ActivityLogDialog(FakeStore(), access=TECH_ACCESS, auto_load=False)
    assert dialog.select_tab("TECHNICAL")
    assert dialog.store.queries[-1][0].categories == ("TECHNICAL",)
    dialog.close()


def test_08_programmatic_technical_bypass_is_rejected(dialog):
    assert dialog.select_tab("TECHNICAL") is False
    assert dialog.active_category == "USER"


def test_09_default_view_is_timeline(dialog):
    assert dialog.current_view == "timeline"
    assert dialog.view_stack.currentWidget() is dialog.timeline


def test_10_timeline_table_switch_works(dialog):
    dialog.set_view("table")
    assert dialog.current_view == "table"
    assert dialog.view_stack.currentWidget() is dialog.table


def test_11_view_switch_preserves_same_item_set(dialog):
    dialog.refresh_logs()
    ids = [item.id for item in dialog.items]
    dialog.set_view("table")
    assert [item.id for item in dialog.table_model.items] == ids
    dialog.set_view("timeline")
    assert [item.id for item in dialog.timeline.items] == ids


def test_12_timeline_groups_items_by_day(app):
    items = (_item(1), _item(2, occurred="2026-07-13T09:00:00Z"))
    store = FakeStore([ActivityHistoryPage(items, None, False)])
    dialog = ActivityLogDialog(
        store,
        access=NORMAL_ACCESS,
        auto_load=False,
        now_provider=lambda: datetime(2026, 7, 14, 12, tzinfo=timezone.utc),
    )
    dialog.refresh_logs()
    assert dialog.timeline.group_labels == ("Bugün · 14.07.2026", "Dün · 13.07.2026")
    dialog.close()


def test_13_today_yesterday_date_labels_are_deterministic():
    now = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
    assert activity_day_label("2026-07-14T10:00:00Z", now).startswith("Bugün")
    assert activity_day_label("2026-07-13T10:00:00Z", now).startswith("Dün")
    assert activity_day_label("2026-07-10T10:00:00Z", now) == "10.07.2026"


def test_14_timeline_card_selection_fills_details(dialog):
    dialog.refresh_logs()
    card = dialog.timeline._cards[1]
    card.selected.emit(card.item)
    assert "S-2026/145" in dialog.details.title.text()


def test_15_table_selection_fills_same_details(dialog):
    dialog.refresh_logs()
    dialog.set_view("table")
    index = dialog.table_model.index(0, 0)
    dialog.table.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
    assert dialog.details.title.text() == dialog.items[0].title


def test_16_normal_user_has_no_technical_section(dialog):
    dialog.refresh_logs()
    dialog.select_item(dialog.items[0])
    assert not dialog.details.technical_toggle.isVisible()


def test_17_technical_user_has_sanitized_technical_section(app):
    item = _item(technical=_technical(), category="TECHNICAL", action="database_optimized")
    dialog = ActivityLogDialog(
        FakeStore([ActivityHistoryPage((item,), None, False)]),
        access=TECH_ACCESS,
        auto_load=False,
    )
    dialog.select_tab("TECHNICAL")
    dialog.select_item(dialog.items[0])
    assert not dialog.details.technical_toggle.isHidden()
    assert "PC_TEST" in dialog.details.technical_text.toPlainText()
    dialog.close()


def test_18_secret_raw_sql_and_full_path_do_not_render(app):
    tech = _technical()
    tech = ActivityTechnicalDetails(
        **{
            **tech.__dict__,
            "payload": {
                "password": "plain-secret",
                "raw_sql": "DELETE FROM contracts",
                "database_path": r"C:\\private\\secret\\file.sts",
            },
        }
    )
    item = _item(category="TECHNICAL", action="database_optimized", technical=tech)
    dialog = ActivityLogDialog(FakeStore([ActivityHistoryPage((item,), None, False)]), access=TECH_ACCESS, auto_load=False)
    dialog.select_tab("TECHNICAL")
    dialog.select_item(dialog.items[0])
    text = dialog.details.technical_text.toPlainText()
    assert "plain-secret" not in text
    assert "DELETE FROM contracts" not in text
    assert r"C:\\private\\secret" not in text
    assert "file.sts" in text
    dialog.close()


def test_19_changed_fields_are_rendered(dialog):
    dialog.refresh_logs()
    dialog.select_item(dialog.items[0])
    assert dialog.details.changed.topLevelItem(0).text(0) == "Durum"
    assert dialog.details.changed.topLevelItem(0).text(2) == "Devam Ediyor"


def test_20_corrupt_changed_fields_state_does_not_crash(app):
    item = _item(changed_fields=(), parse_error=True)
    dialog = ActivityLogDialog(FakeStore([ActivityHistoryPage((item,), None, False)]), access=NORMAL_ACCESS, auto_load=False)
    dialog.refresh_logs()
    dialog.select_item(item)
    assert "güvenli" in dialog.details.changed.topLevelItem(0).text(0)
    dialog.close()


def test_21_operation_group_detail_uses_allowed_adapter(app):
    item = _item(operation_group_key="op_group000001")
    store = FakeStore([ActivityHistoryPage((item,), None, False)])
    dialog = ActivityLogDialog(store, access=NORMAL_ACCESS, auto_load=False)
    dialog.refresh_logs()
    dialog.select_item(item)
    assert store.operation_calls[-1][0] == "op_group000001"
    assert dialog.details.operation_events.count() == 2
    dialog.close()


def test_22_normal_user_does_not_see_full_operation_id(dialog):
    item = _item(operation_group_key="op_group000001")
    dialog.store.pages = [ActivityHistoryPage((item,), None, False)]
    dialog.refresh_logs()
    dialog.select_item(item)
    assert "operation-secret-id" not in dialog.details.meta.text()
    assert not dialog.details.technical_toggle.isVisible()


def test_23_technical_user_can_see_full_operation_id(app):
    item = _item(category="TECHNICAL", action="database_optimized", technical=_technical())
    dialog = ActivityLogDialog(FakeStore([ActivityHistoryPage((item,), None, False)]), access=TECH_ACCESS, auto_load=False)
    dialog.select_tab("TECHNICAL")
    dialog.select_item(dialog.items[0])
    assert "operation-secret-id" in dialog.details.technical_text.toPlainText()
    dialog.close()


def test_24_search_debounce_produces_one_query(dialog):
    dialog.search.setText("a")
    dialog.search.setText("ab")
    dialog.search.setText("abc")
    QTest.qWait(380)
    assert dialog.query_count == 1


def test_25_enter_applies_query_immediately(dialog):
    dialog.search.setText("contract")
    dialog._search_timer.stop()
    dialog.search.returnPressed.emit()
    assert dialog.query_count == 1


def test_26_invalid_date_range_does_not_query(dialog):
    dialog.date_from.setDate(QDate(2026, 7, 14))
    dialog.date_to.setDate(QDate(2026, 7, 13))
    dialog._search_timer.stop()
    assert dialog.refresh_logs() is False
    assert dialog.query_count == 0
    assert "Başlangıç" in dialog.last_error


def test_27_reset_filters_keeps_tab_and_resets_values(dialog):
    dialog.select_tab("MANAGEMENT")
    dialog.search.setText("x")
    dialog.actor.setText("y")
    dialog.clear_filters()
    assert dialog.active_category == "MANAGEMENT"
    assert dialog.search.text() == ""
    assert dialog.actor.text() == ""
    assert dialog.limit.currentData() == 50


def test_28_load_more_deduplicates_ids(app):
    first = ActivityHistoryPage((_item(3), _item(2)), "cursor-1", True)
    second = ActivityHistoryPage((_item(2), _item(1)), None, False)
    dialog = ActivityLogDialog(FakeStore([first, second]), access=NORMAL_ACCESS, auto_load=False)
    dialog.refresh_logs()
    dialog.refresh_logs(reset=False)
    assert [item.id for item in dialog.items] == [3, 2, 1]
    dialog.close()


def test_29_load_more_hidden_without_next_cursor(dialog):
    dialog.refresh_logs()
    assert not dialog.load_more.isVisible()


def test_30_loading_state_blocks_double_request(dialog):
    dialog._loading = True
    assert dialog.refresh_logs() is False
    assert dialog.query_count == 0


def test_31_empty_state_is_shown(app):
    dialog = ActivityLogDialog(FakeStore([ActivityHistoryPage((), None, False)]), access=NORMAL_ACCESS, auto_load=False)
    dialog.refresh_logs()
    assert "eşleşen" in dialog.state_title.text()
    assert dialog.left_stack.currentIndex() == 1
    dialog.close()


def test_32_query_error_is_controlled(app):
    dialog = ActivityLogDialog(FakeStore(error=RuntimeError("database exploded")), access=NORMAL_ACCESS, auto_load=False)
    assert dialog.refresh_logs() is False
    assert "yüklenemedi" in dialog.state_title.text().casefold()
    assert "database exploded" not in dialog.state_message.text()
    dialog.close()


def test_33_stale_response_cannot_overwrite_new_result(dialog):
    dialog._query_generation = 2
    page = ActivityHistoryPage((_item(99),), None, False)
    assert dialog._accept_page(page, generation=1, reset=True) is False
    assert dialog.items == []


def test_34_closed_dialog_ignores_callback(dialog):
    dialog.close()
    page = ActivityHistoryPage((_item(99),), None, False)
    assert dialog._accept_page(page, generation=dialog._query_generation, reset=True) is False


def test_35_limit_options_are_bounded(dialog):
    assert [dialog.limit.itemData(i) for i in range(dialog.limit.count())] == [50, 100, 200]


def test_36_table_has_no_raw_or_internal_columns(dialog):
    headers = dialog.table_model.HEADERS
    assert headers == ("Tarih / Saat", "İşlem", "Kullanıcı", "Varlık / Kayıt", "Platform", "Sözleşme", "Durum")
    assert all("JSON" not in value and "ID" not in value for value in headers)


def test_37_timeline_card_keyboard_selection(app):
    item = _item()
    card = TimelineCard(item)
    selected = []
    card.selected.connect(selected.append)
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    QApplication.sendEvent(card, event)
    assert selected == [item]
    card.deleteLater()


def test_38_1366_geometry_keeps_critical_widgets_visible(dialog):
    dialog.resize(1366, 768)
    dialog.show()
    QApplication.processEvents()
    assert dialog.search.isVisible()
    assert dialog.timeline_button.isVisible()
    assert dialog.details.isVisible()


def test_39_narrow_layout_switches_splitter_vertical(dialog):
    dialog.resize(920, 620)
    dialog.show()
    QApplication.processEvents()
    assert dialog.splitter.orientation() == Qt.Vertical


def test_40_qss_is_scoped_and_does_not_modify_other_dialog(app, dialog):
    other = QDialog()
    label = QLabel("Other", other)
    assert other.styleSheet() == ""
    assert dialog.objectName() == "activityHistoryDialog"
    assert label.styleSheet() == ""
    other.close()


def test_41_real_store_query_integration(tmp_path, app):
    store = STSStore(tmp_path / "activity-ui.sts", actor_context={"id": 7, "full_name": "Ayşe"})
    try:
        store.db.add_log(
            "contract_updated",
            actor="Ayşe",
            actor_display_name="Ayşe",
            actor_type="STAFF",
            actor_staff_id=7,
            category="USER",
            message="Gerçek sorgu entegrasyonu",
            contract_no="S-1",
            platform="AKINCI",
        )
        dialog = ActivityLogDialog(store, access=NORMAL_ACCESS, auto_load=False)
        assert dialog.refresh_logs()
        assert dialog.items and dialog.items[0].summary == "Gerçek sorgu entegrasyonu"
        dialog.close()
    finally:
        store.db.close()
