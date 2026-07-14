from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
try:
    from PySide6.QtWidgets import QFileDialog
except ImportError as exc:
    pytest.skip(f"PySide6 Qt runtime unavailable: {exc}", allow_module_level=True)


def test_window_orchestration_requires_qt_runtime():
    # Real ContractWorkWindow orchestration tests live behind the Qt runtime gate;
    # this assertion prevents an empty module when Qt is available.
    assert QFileDialog is not None


from types import SimpleNamespace

import src.ui.contract.contract_work_window as cww
from src.ui.contract.contract_work_window import ContractWorkWindow
from src.models.share_models import SHARE_STATUS_OPEN, SHARE_STATUS_RETURNED


class _FakeWarningBox:
    Warning = 2
    AcceptRole = 0
    ActionRole = 1
    RejectRole = 2
    choice_label = "Vazgeç"
    instances = []
    warnings = []

    def __init__(self, parent=None):
        self.parent = parent
        self.text = ""
        self.buttons = []
        self._clicked = None
        _FakeWarningBox.instances.append(self)

    def setIcon(self, icon):
        self.icon = icon

    def setWindowTitle(self, title):
        self.title = title

    def setText(self, text):
        self.text = text

    def addButton(self, label, role):
        button = SimpleNamespace(label=label, role=role)
        self.buttons.append(button)
        return button

    def exec(self):
        for button in self.buttons:
            if button.label == self.choice_label:
                self._clicked = button
                break
        return 0

    def clickedButton(self):
        return self._clicked

    @staticmethod
    def warning(parent, title, message):
        _FakeWarningBox.warnings.append((title, message))

    @staticmethod
    def information(parent, title, message):
        pass


def _fake_window(*, permitted=True, share_mode=False):
    calls = []
    window = SimpleNamespace()
    window.store = SimpleNamespace(name="store")
    window.ci = SimpleNamespace(merge_uid="contract-uid")
    window.share_mode_enabled = share_mode
    window.require_permission_ui = lambda permission, title: calls.append(("permission", permission)) or permitted
    window._current_contract_merge_uid = lambda: calls.append(("merge_uid",)) or "contract-uid"
    window._contract_document_share_stats = lambda: calls.append(("doc_stats",)) or (0, 0)
    window.show_share_history = lambda: calls.append(("history",))
    window._confirm_active_share_creation = (
        lambda: ContractWorkWindow._confirm_active_share_creation(window)
    )
    return window, calls


def _install_warning_harness(monkeypatch, calls, active_rows, *, choice="Vazgeç"):
    _FakeWarningBox.choice_label = choice
    _FakeWarningBox.instances = []
    _FakeWarningBox.warnings = []

    def active_query(store, merge_uid):
        calls.append(("active_query", merge_uid))
        return list(active_rows)

    def save_file(*args, **kwargs):
        calls.append(("file_picker",))
        return "", ""

    monkeypatch.setattr(cww, "QMessageBox", _FakeWarningBox)
    monkeypatch.setattr(cww, "list_active_share_packages", active_query)
    monkeypatch.setattr(cww.QFileDialog, "getSaveFileName", save_file)


def test_active_warning_no_active_continues_to_file_picker_without_warning(monkeypatch):
    window, calls = _fake_window()
    _install_warning_harness(monkeypatch, calls, [], choice="Vazgeç")

    ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

    assert calls[:4] == [("permission", "export_data"), ("merge_uid",), ("active_query", "contract-uid"), ("doc_stats",)]
    assert ("file_picker",) in calls
    assert _FakeWarningBox.instances == []


def test_active_warning_open_row_is_shown_before_file_picker_and_continue_continues(monkeypatch):
    window, calls = _fake_window()
    _install_warning_harness(monkeypatch, calls, [{"status": SHARE_STATUS_OPEN}], choice="Yine de Paylaşım Oluştur")

    ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

    assert len(_FakeWarningBox.instances) == 1
    assert "1 aktif paylaşım" in _FakeWarningBox.instances[0].text
    assert calls.index(("active_query", "contract-uid")) < calls.index(("file_picker",))
    assert ("history",) not in calls


def test_active_warning_multiple_open_returned_count_uses_active_helper_result(monkeypatch):
    window, calls = _fake_window()
    rows = [{"status": SHARE_STATUS_OPEN}, {"status": SHARE_STATUS_RETURNED}]
    _install_warning_harness(monkeypatch, calls, rows, choice="Vazgeç")

    ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

    assert len(_FakeWarningBox.instances) == 1
    assert "2 aktif paylaşım" in _FakeWarningBox.instances[0].text
    assert ("file_picker",) not in calls


def test_active_warning_history_choice_reuses_history_callback_and_has_no_create_side_effect(monkeypatch):
    window, calls = _fake_window()
    _install_warning_harness(monkeypatch, calls, [{"status": SHARE_STATUS_OPEN}], choice="Paylaşım Geçmişini Aç")

    ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

    assert calls.count(("history",)) == 1
    assert ("file_picker",) not in calls
    assert ("doc_stats",) not in calls


def test_active_warning_cancel_and_close_are_no_create_paths(monkeypatch):
    for choice in ["Vazgeç", "__close__"]:
        window, calls = _fake_window()
        _install_warning_harness(monkeypatch, calls, [{"status": SHARE_STATUS_OPEN}], choice=choice)

        ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

        assert ("history",) not in calls
        assert ("file_picker",) not in calls
        assert ("doc_stats",) not in calls


def test_share_creation_permission_and_share_mode_stop_before_active_warning(monkeypatch):
    for permitted, share_mode in [(False, False), (True, True)]:
        window, calls = _fake_window(permitted=permitted, share_mode=share_mode)
        _install_warning_harness(monkeypatch, calls, [{"status": SHARE_STATUS_OPEN}], choice="Yine de Paylaşım Oluştur")

        ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

        assert not any(call[0] == "active_query" for call in calls)
        assert ("file_picker",) not in calls
        assert _FakeWarningBox.instances == []


def test_active_warning_query_failure_fails_closed_before_file_picker(monkeypatch):
    window, calls = _fake_window()
    _FakeWarningBox.instances = []
    _FakeWarningBox.warnings = []
    monkeypatch.setattr(cww, "QMessageBox", _FakeWarningBox)

    def active_query(store, merge_uid):
        calls.append(("active_query", merge_uid))
        raise RuntimeError("database unavailable")

    def save_file(*args, **kwargs):
        calls.append(("file_picker",))
        return "", ""

    monkeypatch.setattr(cww, "list_active_share_packages", active_query)
    monkeypatch.setattr(cww.QFileDialog, "getSaveFileName", save_file)

    ContractWorkWindow.create_contract_share_file(window, "duzenle", "share.sts")

    assert _FakeWarningBox.warnings
    assert "kontrol edilemedi" in _FakeWarningBox.warnings[0][1]
    assert ("file_picker",) not in calls
    assert ("doc_stats",) not in calls
