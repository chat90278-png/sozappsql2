from __future__ import annotations

import sqlite3
from pathlib import Path

from analysis_center.analysis_data_loader import _readonly_connect


class _ProbeConnection:
    def __init__(self, *, fail_probe: bool):
        self.fail_probe = fail_probe
        self.row_factory = None
        self.closed = False
        self.statements: list[str] = []

    def execute(self, sql: str, *_args):
        self.statements.append(sql)
        if self.fail_probe and sql.startswith("SELECT 1 FROM sqlite_master"):
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return self

    def fetchone(self):
        return (1,)

    def close(self):
        self.closed = True


def test_readonly_connection_falls_back_to_immutable_for_wal_recovery(monkeypatch, tmp_path):
    first = _ProbeConnection(fail_probe=True)
    second = _ProbeConnection(fail_probe=False)
    calls: list[str] = []

    def fake_connect(database_uri: str, *, uri: bool):
        assert uri is True
        calls.append(database_uri)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    result = _readonly_connect(tmp_path / "copy.sts")

    assert result is second
    assert first.closed is True
    assert calls[0].endswith("?mode=ro")
    assert calls[1].endswith("?mode=ro&immutable=1")
    assert "PRAGMA query_only=ON" in second.statements


def test_readonly_connection_does_not_hide_non_readonly_errors(monkeypatch, tmp_path):
    connection = _ProbeConnection(fail_probe=False)

    def broken_execute(sql: str, *_args):
        if sql.startswith("SELECT 1 FROM sqlite_master"):
            raise sqlite3.OperationalError("database disk image is malformed")
        return connection

    connection.execute = broken_execute
    monkeypatch.setattr(sqlite3, "connect", lambda *_args, **_kwargs: connection)

    try:
        _readonly_connect(tmp_path / "broken.sts")
    except sqlite3.OperationalError as exc:
        assert "malformed" in str(exc)
    else:
        raise AssertionError("Non-readonly OperationalError must propagate")
