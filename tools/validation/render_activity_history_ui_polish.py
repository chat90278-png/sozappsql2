from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from src.services.activity_history_policy import ActivityHistoryAccess
from src.services.activity_history_query import (
    ActivityFieldChange,
    ActivityHistoryItem,
    ActivityHistoryPage,
    ActivityTechnicalDetails,
)
from src.ui.dialogs.activity_logs import ActivityLogDialog


TECH_ACCESS = ActivityHistoryAccess(
    True,
    frozenset({"USER", "MANAGEMENT", "TECHNICAL"}),
    True,
    True,
    True,
)


def _technical(operation_id: str) -> ActivityTechnicalDetails:
    return ActivityTechnicalDetails(
        source="Sentetik doğrulama",
        device_name="TEST-CI",
        actor_staff_id=7,
        actor_admin_id=None,
        session_id="session-ui-polish",
        entity_id="11",
        contract_id=22,
        platform_id=3,
        before={"safe": "önce"},
        after={"safe": "sonra"},
        payload={"safe": "değer"},
        technical_payload={"duration_ms": 18},
        event_schema_version=1,
        operation_id=operation_id,
    )


def _item(
    item_id: int,
    action: str,
    category: str,
    summary: str,
    *,
    actor: str = "Serhat",
    entity_type: str = "contract",
    entity_label: str = "Sözleşme",
    contract_no: str = "AKINCI - TBD - 4",
    minutes: int = 0,
    operation_group_key: str | None = None,
    technical: ActivityTechnicalDetails | None = None,
) -> ActivityHistoryItem:
    return ActivityHistoryItem(
        id=item_id,
        occurred_at=f"2026-07-14T10:{30 + minutes:02d}:00Z",
        category=category,
        action=action,
        action_label=action.replace("_", " ").title(),
        status="SUCCESS",
        actor_display_name=actor,
        title=action.replace("_", " ").title(),
        summary=summary,
        entity_type=entity_type,
        entity_label=entity_label,
        platform_name="AKINCI",
        contract_no=contract_no,
        changed_fields=(
            ActivityFieldChange("Durum", "Planlandı", "Devam Ediyor"),
        ),
        changed_fields_parse_error=False,
        operation_group_key=operation_group_key,
        technical=technical,
    )


USER_ITEMS = (
    _item(1, "contract_tags_updated", "USER", "Sözleşme etiketleri güncellendi"),
    _item(2, "delivery_created", "USER", "Teslimat kaydı eklendi", minutes=1, entity_type="delivery", entity_label="Teslimat"),
    _item(3, "system_created", "USER", "Sistem kaydı oluşturuldu", minutes=2, entity_type="system", entity_label="Sistem"),
    _item(4, "contract_updated", "USER", "Sözleşme ana bilgileri güncellendi", minutes=3),
    _item(5, "contract_created", "USER", "Sözleşme oluşturuldu", minutes=4),
)

MANAGEMENT_ITEMS = (
    _item(11, "platform_updated", "MANAGEMENT", "Platform bilgileri güncellendi", actor="Yönetici", entity_type="platform", entity_label="Platform"),
    _item(12, "user_updated", "MANAGEMENT", "Kullanıcı bilgileri güncellendi", actor="Yönetici", entity_type="user", entity_label="Kullanıcı", minutes=1),
)

TECHNICAL_ITEMS = (
    _item(
        21,
        "database_optimized",
        "TECHNICAL",
        "Veritabanı bakımı tamamlandı",
        actor="Sistem",
        entity_type="database",
        entity_label="Veritabanı",
        operation_group_key="op_123456789abc",
        technical=_technical("operation-ui-polish"),
    ),
)


class FakeStore:
    def query_activity_history(self, query, *, access, include_technical=False):
        category = query.categories[0] if query.categories else "USER"
        items = {
            "USER": USER_ITEMS,
            "MANAGEMENT": MANAGEMENT_ITEMS,
            "TECHNICAL": TECHNICAL_ITEMS,
        }.get(category, ())
        return ActivityHistoryPage(tuple(items), "cursor-more" if category == "USER" else None, category == "USER")

    def get_activity_operation_events(self, operation_id, *, access, limit=200):
        return TECHNICAL_ITEMS

    def get_activity_operation_events_by_group_key(self, group_key, *, access, limit=200):
        return TECHNICAL_ITEMS


def _capture(dialog: ActivityLogDialog, path: Path) -> None:
    QApplication.processEvents()
    image = dialog.grab()
    if not image.save(str(path)):
        raise RuntimeError(f"Screenshot kaydedilemedi: {path}")


def main() -> int:
    output = Path(os.environ.get("ACTIVITY_HISTORY_POLISH_OUTPUT", "activity-history-polish-artifacts"))
    output.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    dialog = ActivityLogDialog(
        FakeStore(),
        access=TECH_ACCESS,
        auto_load=False,
        now_provider=lambda: datetime(2026, 7, 14, 12, tzinfo=timezone.utc),
    )
    dialog.resize(1366, 768)
    dialog.show()
    dialog.refresh_logs()
    QApplication.processEvents()

    _capture(dialog, output / "01-user-timeline-1366.png")
    dialog.select_item(dialog.items[0])
    _capture(dialog, output / "02-selected-detail-1366.png")

    dialog.set_view("table")
    _capture(dialog, output / "03-summary-table-1366.png")

    dialog.select_tab("TECHNICAL")
    if dialog.items:
        dialog.select_item(dialog.items[0])
    _capture(dialog, output / "04-technical-1366.png")

    dialog.select_tab("USER")
    dialog.set_view("timeline")
    dialog.resize(920, 620)
    if dialog.items:
        dialog.select_item(dialog.items[0])
    _capture(dialog, output / "05-narrow-920.png")

    dialog.close()
    app.processEvents()
    print(f"ACTIVITY HISTORY UI POLISH SCREENSHOTS: PASS ({output})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
