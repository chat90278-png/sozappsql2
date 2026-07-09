from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from src.ui.main_page_analysis_window import MainWindow
from src.ui.widgets.contract_status_summary import (
    ContractStatusSummary,
    ContractStatusSummaryWidget,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_contract_status_summary_maps_analysis_metrics_without_reclassifying():
    summary = ContractStatusSummary.from_metrics(
        {
            "total_contracts": 12,
            "completed_contract_count": 4,
            "in_progress_contract_count": 5,
            "not_started_contract_count": 3,
        }
    )

    assert summary.total_contracts == 12
    assert summary.completed_contracts == 4
    assert summary.in_progress_contracts == 5
    assert summary.not_started_contracts == 3
    assert summary.completed_percent == 33


def test_contract_status_widget_matches_calendar_hover_and_balances_inner_layout(qt_app):
    widget = ContractStatusSummaryWidget()
    try:
        assert widget.width() == 460
        assert widget.height() == 112
        assert widget.sizePolicy().horizontalPolicy() == QSizePolicy.Fixed

        content = widget.findChild(QWidget, "contractStatusContent")
        total_panel = widget.findChild(QWidget, "contractStatusTotalPanel")
        assert content is not None
        assert total_panel is not None
        assert total_panel.width() == 114

        style = widget.styleSheet()
        assert "border:1.5px solid #d8e2ed" in style
        assert "QFrame#contractStatusSummaryWidget:hover" in style
        assert "border-color:#397bd8" in style
        assert "background:#fafcff" in style
        assert "hover QWidget#contractStatusContent" in style

        assert widget.total_value.alignment() & Qt.AlignHCenter
        assert widget.total_label.alignment() & Qt.AlignHCenter
        for label in (
            widget.completed_label,
            widget.in_progress_label,
            widget.not_started_label,
        ):
            assert label.alignment() & Qt.AlignHCenter
            assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored

        calls: list[str] = []
        widget.open_analysis_requested.connect(lambda: calls.append("open"))
        widget.open_button.click()
        assert calls == ["open"]
    finally:
        widget.close()


def test_main_page_keeps_calendar_fixed_and_uses_analysis_engine(
    qt_app,
    tmp_path,
    monkeypatch,
):
    window = MainWindow()
    try:
        calendar_layout = window._cal_widget.parentWidget().layout()
        status_index = calendar_layout.indexOf(window.contract_status_widget)
        calendar_index = calendar_layout.indexOf(window._cal_widget)

        assert status_index >= 0
        assert status_index < calendar_index
        assert calendar_index - status_index >= 2  # deliberate stretch/free slot
        assert window.upcoming_scroll.isHidden()
        assert window.contract_status_widget.width() == 460
        assert window._cal_widget.sizePolicy().horizontalPolicy() == QSizePolicy.Fixed
        assert window._cal_widget.minimumWidth() == window._cal_widget.maximumWidth()

        source = tmp_path / "STS-A1__v017__2026-07-09_12-00.sts"

        class DummyDB:
            path = source

        class DummyStore:
            db = DummyDB()
            path = source

        window.store = DummyStore()
        window.path = source
        window.contract_index = [{"id": 7, "platform": "AKINCI"}]
        monkeypatch.setattr(window, "is_sts_mode", lambda: True)

        calls: dict[str, object] = {}

        def fake_load_analysis_data(*, source, contract_index, use_sample):
            calls["source"] = source
            calls["contract_index"] = contract_index
            calls["use_sample"] = use_sample
            return {"contracts": [{"id": 1}]}

        def fake_compute_metrics(data):
            calls["data"] = data
            return {
                "total_contracts": 12,
                "completed_contract_count": 4,
                "in_progress_contract_count": 5,
                "not_started_contract_count": 3,
            }

        monkeypatch.setattr(
            "src.ui.main_page_analysis_window.load_analysis_data",
            fake_load_analysis_data,
        )
        monkeypatch.setattr(
            "src.ui.main_page_analysis_window.compute_metrics",
            fake_compute_metrics,
        )

        window._refresh_contract_status_widget()

        assert Path(calls["source"]) == source
        assert calls["contract_index"] == [{"id": 7, "platform": "AKINCI"}]
        assert calls["use_sample"] is False
        assert calls["data"] == {"contracts": [{"id": 1}]}
        assert window.contract_status_widget.summary() == ContractStatusSummary(
            total_contracts=12,
            completed_contracts=4,
            in_progress_contracts=5,
            not_started_contracts=3,
        )
    finally:
        window.store = None
        window.close()
