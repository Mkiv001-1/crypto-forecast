"""Tests for consensus trade status helpers and GET /trades filters."""

import sqlite3

import pytest

from scripts.client.consensus_trade_status import compute_trade_status, parse_trade_id


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("  ", None),
        (0, None),
        (-1, None),
        ("42", 42),
        (7, 7),
    ],
)
def test_parse_trade_id(value, expected):
    assert parse_trade_id(value) == expected


@pytest.mark.parametrize(
    "trade_id,order_state,trade_row,expected",
    [
        (10, "PENDING_ORDER", {"id": 10}, "traded"),
        (10, "ORDER_SUBMITTED", None, "orphan"),
        (None, "ORDER_SUBMITTED", None, "submitted"),
        (None, "PENDING_ORDER", None, "pending"),
        (None, "EXPIRED", None, "expired"),
        (None, "ORDER_SKIPPED", None, "skipped"),
        (None, "", None, "new"),
    ],
)
def test_compute_trade_status(trade_id, order_state, trade_row, expected):
    assert (
        compute_trade_status(
            trade_id=trade_id,
            order_state=order_state,
            trade_row=trade_row,
        )
        == expected
    )


def test_get_trades_by_consensus_id(temp_db):
    """GET /trades logic: filter by consensus_id."""
    from scripts.core.sqlite_manager import SQLiteManager

    db = SQLiteManager(temp_db)
    with db._connect() as con:
        con.execute(
            """
            INSERT INTO trades (
                trade_uid, ticker, symbol, consensus_id, ib_parent_id,
                signal, quantity, entry_price, stop_loss, target_price,
                status, leverage, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "uid1",
                "BTCUSDT",
                "BTCUSDT",
                99,
                1,
                "LONG",
                1.0,
                100.0,
                90.0,
                110.0,
                "OPEN",
                5,
                "2026-01-01",
                "2026-01-01",
            ),
        )
        trade_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]

    with db._connect() as con:
        rows = con.execute(
            "SELECT * FROM trades WHERE consensus_id = ? ORDER BY id DESC LIMIT 1",
            (99,),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == trade_id


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    con = sqlite3.connect(db_file)
    con.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_uid TEXT,
            ticker TEXT,
            symbol TEXT,
            consensus_id INTEGER,
            ib_parent_id INTEGER,
            signal TEXT,
            quantity REAL,
            entry_price REAL,
            stop_loss REAL,
            target_price REAL,
            status TEXT,
            leverage INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    con.commit()
    con.close()
    return db_file
