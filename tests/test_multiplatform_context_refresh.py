from __future__ import annotations

from types import SimpleNamespace

from src.models.app_models import SystemInfo
from src.ui.contract.contract_work_window import ContractWorkWindow
from src.ui.contract.multiplatform_context_refresh import (
    install_multiplatform_context_refresh_fix,
)

install_multiplatform_context_refresh_fix()


class _StubList:
    def __init__(self):
        self.items = []
        self.current_item = None

    def blockSignals(self, _blocked):
        pass

    def clear(self):
        self.items.clear()
        self.current_item = None

    def addItem(self, item):
        self.items.append(item)

    def setCurrentItem(self, item):
        self.current_item = item


class _StubButton:
    def __init__(self):
        self.visible = None
        self.enabled = None

    def setVisible(self, visible):
        self.visible = bool(visible)

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)


class _Store:
    def __init__(self):
        self.components = {
            1: {"AKINCI Parçası": 5.0},
            2: {"TB3 Parçası": 9.0},
        }
        self.names = {1: "AKINCI", 2: "TB3"}

    def load_contract_structure(
        self,
        _platform,
        *,
        contract_no,
        start_row,
        contract_type,
        platform_id,
    ):
        ci = SimpleNamespace(platform=self.names[platform_id])
        system = SystemInfo(
            name="Sistem 1",
            components=dict(self.components[platform_id]),
        )
        return ci, [system], {}

    def get_primary_contract_platform(self, _contract_id):
        return {"platform_id": 1, "platform_name": "AKINCI"}


class _FakeWindow:
    def __init__(self):
        self.store = _Store()
        self.ci = SimpleNamespace(
            no="141414",
            platform="AKINCI",
            platform_id=1,
            primary_platform_id=1,
            entry_start_row=17,
            contract_type="Ana Sözleşme",
        )
        self.active_platform_id = 1
        self.systems = [
            SystemInfo(
                name="Sistem 1",
                components={"AKINCI Parçası": 5.0},
            )
        ]
        self.deliveries = {}
        self.selected_system = "Sistem 1"
        self.expanded_delivery_index = None
        self.summary_components = {"AKINCI Parçası": 5.0}
        self.rendered_components = {}
        self.cache_snapshots = []
        self.sd_list = _StubList()
        self.add_sd_btn = _StubButton()
        self._refreshing_contract_context = False

    def _linked_contract_platforms(self):
        return [
            {"platform_id": 1, "platform_name": "AKINCI", "is_primary": True},
            {"platform_id": 2, "platform_name": "TB3", "is_primary": False},
        ]

    def _cache_current_context(self):
        # Mirrors the dangerous part of the real cache path. The visible summary
        # is synchronized into whatever system list is current at cache time.
        if self.systems:
            self.systems[0].components = dict(self.summary_components)
        self.cache_snapshots.append(
            (
                self.active_platform_id,
                dict(self.systems[0].components) if self.systems else {},
            )
        )

    def _context_key(self):
        return (self.ci.platform, self.ci.no, self.ci.contract_type)

    def _family_context_rows(self):
        return []

    def _is_sd_type(self, _contract_type):
        return False

    def refresh_contract_header(self):
        pass

    def refresh(self):
        # Real ContractWorkWindow.refresh starts with refresh_sd_sidebar. At this
        # point the model belongs to the new platform while the visible summary
        # still belongs to the outgoing platform.
        ContractWorkWindow.refresh_sd_sidebar(self)
        self.rendered_components = (
            dict(self.systems[0].components) if self.systems else {}
        )
        # Simulate refresh_right repainting the summary for the active platform.
        self.summary_components = dict(self.rendered_components)


def test_platform_switch_does_not_feed_old_summary_into_new_same_named_system():
    window = _FakeWindow()

    ContractWorkWindow.set_active_platform(window, 2)

    assert window.cache_snapshots == [
        (1, {"AKINCI Parçası": 5.0}),
    ]
    assert window.rendered_components == {"TB3 Parçası": 9.0}
    assert window.systems[0].components == {"TB3 Parçası": 9.0}
    assert window.selected_system == "Sistem 1"
    assert window._switching_active_platform_context is False


def test_repeated_platform_switches_render_last_active_platform_consistently():
    window = _FakeWindow()

    ContractWorkWindow.set_active_platform(window, 2)
    ContractWorkWindow.set_active_platform(window, 1)

    assert [snapshot[0] for snapshot in window.cache_snapshots] == [1, 2]
    assert window.rendered_components == {"AKINCI Parçası": 5.0}
    assert window.systems[0].components == {"AKINCI Parçası": 5.0}
    assert window.active_platform_id == 1


def test_normal_sidebar_refresh_keeps_existing_context_cache_behavior():
    window = _FakeWindow()

    ContractWorkWindow.refresh_sd_sidebar(window)

    assert len(window.cache_snapshots) == 1
    assert window.cache_snapshots[0][0] == 1
