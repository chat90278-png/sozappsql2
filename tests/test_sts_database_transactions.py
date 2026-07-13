from __future__ import annotations

import pytest

from src.services.sts_database import STSDatabase


@pytest.fixture
def db(tmp_path):
    database = STSDatabase(tmp_path / "transactions.sts", source="Transaction Tests")
    database.conn.execute("CREATE TABLE IF NOT EXISTS tx_probe(value TEXT PRIMARY KEY)")
    database.conn.commit()
    try:
        yield database
    finally:
        database.close()


def _values(db: STSDatabase) -> list[str]:
    return [str(row[0]) for row in db.conn.execute("SELECT value FROM tx_probe ORDER BY value").fetchall()]


def test_tx_commits_standalone_mutation(db):
    with db.tx():
        db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("committed",))

    assert _values(db) == ["committed"]


def test_tx_rolls_back_standalone_mutation_on_exception(db):
    with pytest.raises(RuntimeError):
        with db.tx():
            db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("rolled-back",))
            raise RuntimeError("rollback standalone")

    assert _values(db) == []


def test_nested_tx_outer_exception_rolls_back_inner_success(db):
    with pytest.raises(RuntimeError):
        with db.tx():
            db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("outer",))
            with db.tx():
                db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("inner",))
            raise RuntimeError("rollback outer")

    assert _values(db) == []


def test_nested_tx_inner_exception_rolls_back_to_savepoint_and_outer_can_commit(db):
    with db.tx():
        db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("A",))
        try:
            with db.tx():
                db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("B",))
                raise RuntimeError("rollback inner")
        except RuntimeError:
            pass
        db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("C",))

    assert _values(db) == ["A", "C"]


def test_tx_marks_outer_context_as_active_before_first_write(db):
    assert db.conn.in_transaction is False

    with db.tx():
        assert db.conn.in_transaction is True

    assert db.conn.in_transaction is False


def test_db_tx_inside_existing_raw_transaction_uses_savepoint_without_committing_outer(db):
    db.conn.execute("BEGIN")
    try:
        with db.tx():
            db.conn.execute("INSERT INTO tx_probe(value) VALUES(?)", ("raw-outer",))

        assert _values(db) == ["raw-outer"]
        assert db.conn.in_transaction is True
        db.conn.rollback()
    finally:
        if db.conn.in_transaction:
            db.conn.rollback()

    assert _values(db) == []


def test_read_only_tx_closes_transaction_after_success(db):
    with db.tx():
        assert db.conn.in_transaction is True
        db.conn.execute("SELECT 1").fetchone()

    assert db.conn.in_transaction is False
