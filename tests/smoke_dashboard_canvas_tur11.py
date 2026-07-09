from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from analysis_center.analysis_dashboard_workspace import CUSTOM_DASHBOARD_ID, DashboardWorkspaceStore
from analysis_center.analysis_models import VisualSettings
from analysis_center.analysis_qt_window import AnalysisCenterWindow


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


def drag_handle(app, canvas, frame, dx: int, dy: int) -> None:
    handle = frame.drag_handle
    start = handle.rect().center()
    QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(handle, QPoint(start.x() + dx, start.y() + dy))
    QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + dx, start.y() + dy))
    app.processEvents()


def resize_handle(app, frame, dx: int, dy: int) -> None:
    handle = frame.resize_handle
    start = handle.rect().center()
    QTest.mousePress(handle, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(handle, QPoint(start.x() + dx, start.y() + dy))
    QTest.mouseRelease(handle, Qt.LeftButton, Qt.NoModifier, QPoint(start.x() + dx, start.y() + dy))
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    source = next(Path(__file__).resolve().parents[1].glob("*.sts"))
    with TemporaryDirectory(prefix="tur11-dashboard-smoke-") as temp_root:
        store = DashboardWorkspaceStore(Path(temp_root) / "dashboards")
        window = AnalysisCenterWindow(source=str(source), settings=settings(), workspace_store=store)
        window.show()
        app.processEvents()
        assert window.current_item_id() == CUSTOM_DASHBOARD_ID
        assert "Salt-okunur STS bağlantısı" in window.status_text.text()
        print("1-2 OK: gerçek STS ile uygulama/Analiz Merkezi açıldı ve Dashboard aktif.")

        card_index = {card.card_id: card for item in window._dashboard_items for card in item.cards}
        for card_id in ("exec_total_contracts", "exec_upcoming_deadlines", "exec_status_distribution"):
            window._toggle_dashboard_card(card_index[card_id])
        baseline = window.workspace.to_dict()

        QTest.mouseClick(button(window, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        print("3 OK: Dashboard'u Düzenle ile working edit session açıldı.")

        kpi = placement(session.working_workspace, "exec_total_contracts")
        other = placement(session.working_workspace, "exec_upcoming_deadlines")
        drag_handle(app, canvas, canvas._frames[kpi.placement_id], int(canvas.width() * 0.35), 0)
        moved = placement(session.working_workspace, "exec_total_contracts")
        pushed = placement(session.working_workspace, "exec_upcoming_deadlines")
        assert moved.x != kpi.x or moved.y != kpi.y
        assert pushed.y > other.y
        assert canvas._frames[pushed.placement_id].y() > canvas._frames[moved.placement_id].y()
        print("4-6 OK: gerçek mouse drag + collision + engine push/reflow Canvas geometrisine yansıdı.")

        chart = placement(session.working_workspace, "exec_status_distribution")
        chart_hints = session.working_workspace.layout_hints_for(chart.placement_id)
        frame = canvas._frames[chart.placement_id]
        original_size = (chart.w, chart.h)
        resize_handle(app, frame, 150, 90)
        resized = placement(session.working_workspace, "exec_status_distribution")
        assert (resized.w, resized.h) != original_size
        resize_handle(app, frame, -5000, -5000)
        constrained = placement(session.working_workspace, "exec_status_distribution")
        assert constrained.w >= chart_hints.min_w
        assert constrained.h >= chart_hints.min_h
        print("7-8 OK: chart gerçek mouse resize edildi; min_w/min_h sınırları engine tarafından korundu.")

        QTest.mouseClick(button(window, "Vazgeç"), Qt.LeftButton)
        app.processEvents()
        assert window.workspace.to_dict() == baseline
        print("9-10 OK: Vazgeç working değişikliklerini attı, saved layout aynen geri geldi.")

        QTest.mouseClick(button(window, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        session = window._dashboard_edit_session
        canvas = window._dashboard_canvas
        assert session is not None and canvas is not None
        kpi = placement(session.working_workspace, "exec_total_contracts")
        drag_handle(app, canvas, canvas._frames[kpi.placement_id], int(canvas.width() * 0.48), 130)
        chart = placement(session.working_workspace, "exec_status_distribution")
        resize_handle(app, canvas._frames[chart.placement_id], 120, 70)
        persisted_expected = session.working_workspace.to_dict()
        QTest.mouseClick(button(window, "Kaydet"), Qt.LeftButton)
        app.processEvents()
        assert window.workspace.to_dict() == persisted_expected
        print("11-14 OK: ikinci edit session'da move+resize yapıldı ve Kaydet persisted workspace'i güncelledi.")
        window.close()

        reloaded = AnalysisCenterWindow(source=str(source), settings=settings(), workspace_store=store)
        reloaded.show()
        app.processEvents()
        assert reloaded.workspace.to_dict() == persisted_expected
        print("15-16 OK: Dashboard yeniden açıldı; saved logical layout diskten aynı şekilde yüklendi.")

        QTest.mouseClick(button(reloaded, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        session = reloaded._dashboard_edit_session
        canvas = reloaded._dashboard_canvas
        assert session is not None and canvas is not None
        kpi = placement(session.working_workspace, "exec_total_contracts")
        before_history_move = session.working_workspace.to_dict()
        drag_handle(app, canvas, canvas._frames[kpi.placement_id], -int(canvas.width() * 0.28), 70)
        after_history_move = session.working_workspace.to_dict()
        assert after_history_move != before_history_move
        QTest.keyClick(reloaded, Qt.Key_Z, Qt.ControlModifier)
        app.processEvents()
        assert session.working_workspace.to_dict() == before_history_move
        QTest.keyClick(reloaded, Qt.Key_Y, Qt.ControlModifier)
        app.processEvents()
        assert session.working_workspace.to_dict() == after_history_move
        print("17 OK: Ctrl+Z ve Ctrl+Y bir drag session'ı tek history step olarak undo/redo etti.")

        QTest.mouseClick(button(reloaded, "Vazgeç"), Qt.LeftButton)
        app.processEvents()
        saved_before_reset = reloaded.workspace.to_dict()
        QTest.mouseClick(button(reloaded, "Dashboard'u Düzenle"), Qt.LeftButton)
        app.processEvents()
        QTest.mouseClick(button(reloaded, "Yerleşimi Sıfırla"), Qt.LeftButton)
        app.processEvents()
        assert reloaded._dashboard_edit_session is not None
        assert reloaded._dashboard_edit_session.working_workspace.to_dict() != saved_before_reset
        QTest.mouseClick(button(reloaded, "Vazgeç"), Qt.LeftButton)
        app.processEvents()
        assert reloaded.workspace.to_dict() == saved_before_reset
        print("18 OK: Yerleşimi Sıfırla yalnız working layout'u değiştirdi; Vazgeç saved layout'u korudu.")
        reloaded.close()

        print("TUR 11 DASHBOARD CANVAS SMOKE: PASS")


if __name__ == "__main__":
    main()
