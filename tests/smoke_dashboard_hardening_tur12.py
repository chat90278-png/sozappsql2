from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from analysis_center.analysis_dashboard_geometry import GridGeometry
from analysis_center.analysis_dashboard_layout import DashboardCardPlacement
from analysis_center.analysis_dashboard_workspace import (
    CUSTOM_DASHBOARD_ID,
    DashboardWorkspaceStore,
)
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


class FrozenSmokeDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 1)


def settings() -> VisualSettings:
    return VisualSettings(show_disabled_sections=False, empty_state_uses_sample=False)


def button(window: AnalysisCenterWindow, text: str) -> QPushButton:
    return next(
        item
        for item in window.findChildren(QPushButton)
        if item.text() == text and item.isVisible() and item.isEnabled()
    )


def placement(workspace, card_id: str):
    return next(item for item in workspace.placements if item.card_id == card_id)


def pin_cards(window: AnalysisCenterWindow, card_ids: tuple[str, ...]) -> None:
    card_index = {card.card_id: card for item in window._dashboard_items for card in item.cards}
    for card_id in card_ids:
        if not window.workspace.contains(card_index[card_id].screen_id, card_id):
            window._toggle_dashboard_card(card_index[card_id])


def assert_placeholder_matches(canvas, workspace, placement_id: str) -> None:
    current = next(item for item in workspace.placements if item.placement_id == placement_id)
    expected = GridGeometry(canvas.width(), workspace.layout).placement_rect(current)
    actual = canvas.drag_placeholder_geometry
    assert canvas.drag_placeholder_visible is True
    assert (actual.x(), actual.y(), actual.width(), actual.height()) == (
        expected.x,
        expected.y,
        expected.width,
        expected.height,
    )


def dashboard_card_frame_by_title(window: AnalysisCenterWindow, title: str) -> QFrame:
    current = window.stack.currentWidget()
    assert current is not None
    for frame in current.findChildren(QFrame, "analysisCard"):
        labels = frame.findChildren(QLabel, "analysisCardTitle")
        if labels and labels[0].text() == title:
            return frame
    raise AssertionError(f"Kart bulunamadı: {title}")


@patch("analysis_center.analysis_metrics.date", FrozenSmokeDate)
def main() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    source = next(root.glob("*.sts"))

    with TemporaryDirectory(prefix="tur12-dashboard-termin-smoke-") as temp_root:
        temp = Path(temp_root)
        store = DashboardWorkspaceStore(temp / "dashboards")
        window = AnalysisCenterWindow(source=str(source), settings=settings(), workspace_store=store)
        window.resize(1250, 820)
        window.show()
        app.processEvents()

        assert window.current_item_id() == CUSTOM_DASHBOARD_ID
        assert "Salt-okunur STS bağlantısı" in window.status_text.text()
        print("1-2 OK: gerçek STS ile uygulama açıldı; Dashboard aktif.")

        pin_cards(
            window,
            ("exec_total_contracts", "exec_upcoming_deadlines", "exec_status_distribution"),
        )
        baseline = window.workspace.to_dict()
        QTest.mouseClick(button(window, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        print("3 OK: Dashboard edit mode açıldı.")

        moving = placement(session.working_workspace, "exec_total_contracts")
        pushed_before = placement(session.working_workspace, "exec_upcoming_deadlines").y
        frame = canvas._frames[moving.placement_id]
        handle = frame.drag_handle
        original = (moving.x, moving.y, moving.w, moving.h)

        for press_point in (QPoint(3, 4), QPoint(max(3, handle.width() - 4), handle.height() - 4)):
            QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, press_point)
            app.processEvents()
            same = placement(session.working_workspace, "exec_total_contracts")
            assert (same.x, same.y, same.w, same.h) == original
            assert_placeholder_matches(canvas, session.working_workspace, moving.placement_id)
            QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, press_point)
            app.processEvents()
            assert canvas.drag_placeholder_visible is False
        print("4-5 OK: drag handle farklı noktalardan tutuldu; kart başlangıçta mouse origin'e zıplamadı.")

        geometry = GridGeometry(canvas.width(), session.working_workspace.layout)
        start = QPoint(max(3, handle.width() - 5), 5)
        target = QPoint(start.x() + int(geometry.column_pitch * 3.1), start.y())
        QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(handle, target)
        app.processEvents()
        assert_placeholder_matches(canvas, session.working_workspace, moving.placement_id)
        QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, target)
        app.processEvents()
        moved = placement(session.working_workspace, "exec_total_contracts")
        pushed = placement(session.working_workspace, "exec_upcoming_deadlines")
        assert (moved.x, moved.y) != original[:2]
        assert pushed.y > pushed_before
        assert canvas._frames[pushed.placement_id].y() > canvas._frames[moved.placement_id].y()
        assert session.undo_depth == 1
        print("6-8 OK: birkaç kolon drag, engine-preview placeholder ve collision/push-reflow doğrulandı.")

        chart = placement(session.working_workspace, "exec_status_distribution")
        chart_frame = canvas._frames[chart.placement_id]
        resize = chart_frame.resize_handle
        resize_start = resize.rect().center()
        chart_before = (chart.w, chart.h)
        QTest.mousePress(resize, Qt.LeftButton, Qt.NoModifier, resize_start)
        QTest.mouseMove(resize, QPoint(resize_start.x() + 150, resize_start.y() + 95))
        QTest.mouseRelease(
            resize,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(resize_start.x() + 150, resize_start.y() + 95),
        )
        app.processEvents()
        resized = placement(session.working_workspace, "exec_status_distribution")
        assert (resized.w, resized.h) != chart_before
        print("9 OK: geniş hit area'lı sağ-alt handle ile gerçek chart resize çalıştı.")

        after_drag_resize = session.working_workspace.to_dict()
        QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
        app.processEvents()
        assert session.working_workspace.to_dict() != after_drag_resize
        QTest.keyClick(window, Qt.Key_Y, Qt.ControlModifier)
        app.processEvents()
        assert session.working_workspace.to_dict() == after_drag_resize
        print("11 OK: Ctrl+Z/Ctrl+Y edit history davranışı korundu.")

        logical_before_resize = session.working_workspace.to_dict()
        frame_before_resize = canvas._frames[resized.placement_id].geometry()
        window.resize(1550, 920)
        app.processEvents()
        frame_after_resize = canvas._frames[resized.placement_id].geometry()
        assert session.working_workspace.to_dict() == logical_before_resize
        assert frame_after_resize.width() != frame_before_resize.width()
        print("12 OK: viewport resize pixel geometry'yi değiştirdi; logical workspace aynı kaldı.")

        QTest.mouseClick(button(window, "Vazgeç"), Qt.LeftButton)
        app.processEvents()
        assert window.workspace.to_dict() == baseline
        QTest.mouseClick(button(window, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        moving = placement(session.working_workspace, "exec_total_contracts")
        handle = canvas._frames[moving.placement_id].drag_handle
        geometry = GridGeometry(canvas.width(), session.working_workspace.layout)
        start = QPoint(4, 4)
        target = QPoint(start.x() + int(geometry.column_pitch * 4.1), start.y() + int(geometry.row_pitch))
        QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(handle, target)
        QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, target)
        app.processEvents()
        persisted = session.working_workspace.to_dict()
        QTest.mouseClick(button(window, "Kaydet"), Qt.LeftButton)
        app.processEvents()
        assert window.workspace.to_dict() == persisted
        assert store.load(str(source), dashboard_items=window._dashboard_items).to_dict() == persisted
        print("10 OK: Vazgeç saved layout'u geri getirdi; ikinci edit Kaydet ile persist edildi.")

        nav_texts = [window.navigation.item(index).text() for index in range(window.navigation.count())]
        assert "Mini Veri Sağlığı" not in nav_texts
        assert "mini_data_health" not in window._item_ids
        window._render_items("mini_data_health")
        app.processEvents()
        assert window.current_item_id() == CUSTOM_DASHBOARD_ID
        print("13-14 OK: Mini Veri Sağlığı navigation/route listesinde yok; eski screen id render isteği crash etmeden Dashboard'a düştü.")

        orphan_store = DashboardWorkspaceStore(temp / "orphan-dashboards")
        orphan_workspace = window.workspace.working_copy()
        orphan_workspace.add_placement(
            DashboardCardPlacement(
                placement_id="removed-health-placement",
                source_screen_id="mini_data_health",
                card_id="health_missing_count",
                x=0,
                y=20,
                w=3,
                h=2,
            )
        )
        valid_signature = {
            item.placement_id: (item.x, item.y, item.w, item.h)
            for item in orphan_workspace.placements
            if item.source_screen_id != "mini_data_health"
        }
        orphan_store.save(str(source), orphan_workspace)
        orphan_window = AnalysisCenterWindow(
            source=str(source),
            settings=settings(),
            workspace_store=orphan_store,
        )
        orphan_window.show()
        app.processEvents()
        assert all(item.source_screen_id != "mini_data_health" for item in orphan_window.workspace.placements)
        assert {
            item.placement_id: (item.x, item.y, item.w, item.h)
            for item in orphan_window.workspace.placements
        } == valid_signature
        orphan_window.close()
        print("15 OK: eski health placement load-time orphan cleanup ile silindi; diğer placement geometrileri aynen korundu.")

        deadline_row = window._item_ids.index("deadline_analysis")
        window.navigation.setCurrentRow(deadline_row)
        app.processEvents()
        assert window.current_item_id() == "deadline_analysis"
        metrics = window._payload["metrics"]
        upcoming = int(metrics["upcoming_deadline_count"])
        past = int(metrics["past_deadline_count"])
        unknown = int(metrics["unknown_deadline_count"])
        assert metrics["generated_at"] == "2026-07-01"
        assert (upcoming, past, unknown) == (1, 0, 2)
        assert any(
            row.get("date_field") == "planned_acceptance_date" and row.get("due_date") == "2026-07-09"
            for row in window._payload["data"]["deadlines"]
        )
        assert any(
            row.get("date_field") == "planned_acceptance_date" and row.get("raw_date_value") == "TBD"
            for row in metrics["unknown_deadlines"]
        )
        print(f"16-20 OK: Termin Analizi açıldı; upcoming={upcoming}, past={past}, unknown={unknown}; üç kart/tablo modeli üretildi.")
        print("21-22 OK: gerçek STS planned_acceptance_date=2026-07-09 upcoming; planned_acceptance_date=TBD unknown tabloda ham değerle bulundu.")

        unknown_card_frame = dashboard_card_frame_by_title(window, "Tarihi Belirsiz")
        pin_button = next(item for item in unknown_card_frame.findChildren(QPushButton) if item.objectName() == "analysisPinButton")
        QTest.mouseClick(pin_button, Qt.LeftButton)
        app.processEvents()
        assert window.workspace.contains("deadline_analysis", "deadline_unknown_count")
        window.navigation.setCurrentRow(0)
        app.processEvents()
        dashboard_cards, missing = window.workspace.resolve_cards(window._dashboard_items)
        assert missing == []
        assert any(card.card_id == "deadline_unknown_count" for card in dashboard_cards)
        assert window._dashboard_canvas is not None
        assert any(frame.card.card_id == "deadline_unknown_count" for frame in window._dashboard_canvas._frames.values())
        print("23-24 OK: yeni Tarihi Belirsiz KPI + Dashboard düğmesiyle pinlendi ve gerçek Dashboard Canvas'ta render oldu.")

        window.close()
        print("TUR 12 DASHBOARD/TERMIN SMOKE: PASS")


if __name__ == "__main__":
    main()
