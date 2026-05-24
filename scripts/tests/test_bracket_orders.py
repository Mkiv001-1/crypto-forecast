"""Tests for bracket trade + three orders persistence."""

import os
import sys
import sqlite3
import tempfile

import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def bracket_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from scripts.core.sqlite_manager import SQLiteManager

    db = SQLiteManager(path)
    with db._connect() as con:
        con.execute(
            """INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
               VALUES ('BTCUSDT', 1, 'test', 'crypto', 0)"""
        )
        con.commit()
    yield db
    try:
        os.unlink(path)
    except OSError:
        pass


def test_insert_bracket_orders_creates_three_rows(bracket_db):
    from scripts.core.storage.repositories.orders_repo import OrdersRepository

    repo = OrdersRepository(bracket_db)
    ids = repo.insert_bracket_orders(
        ticker="BTCUSDT",
        symbol="BTCUSDT",
        side="Buy",
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=52000.0,
        quantity=0.01,
        trade_uid="test-uid-001",
        order_link_id="forecast_test-uid-001",
        order_type="Limit",
        leverage=3,
        confidence=75.0,
        consensus_id=None,
        methods="classic",
        rationale="test",
        created_at="2024-01-01T00:00:00+00:00",
    )

    assert set(ids.keys()) == {"entry_id", "take_profit_id", "stop_loss_id"}

    with bracket_db._connect() as con:
        rows = con.execute(
            "SELECT id, order_role, ib_parent_id, trade_uid, action, limit_price, stop_price "
            "FROM orders WHERE trade_uid=? ORDER BY id",
            ("test-uid-001",),
        ).fetchall()

    assert len(rows) == 3
    roles = {str(r["order_role"]).upper() for r in rows}
    assert roles == {"ENTRY", "TAKE_PROFIT", "STOP_LOSS"}

    entry = next(r for r in rows if r["order_role"].upper() == "ENTRY")
    tp = next(r for r in rows if r["order_role"].upper() == "TAKE_PROFIT")
    sl = next(r for r in rows if r["order_role"].upper() == "STOP_LOSS")

    assert entry["ib_parent_id"] == 0
    assert tp["ib_parent_id"] == entry["id"]
    assert sl["ib_parent_id"] == entry["id"]
    assert entry["action"] == "BUY"
    assert tp["action"] == "SELL"
    assert sl["action"] == "SELL"
    assert tp["limit_price"] == pytest.approx(52000.0)
    assert sl["stop_price"] == pytest.approx(49000.0)


def test_insert_trade_for_bracket_links_entry(bracket_db):
    from scripts.core.storage.repositories.orders_repo import OrdersRepository

    repo = OrdersRepository(bracket_db)
    ids = repo.insert_bracket_orders(
        ticker="BTCUSDT",
        symbol="BTCUSDT",
        side="Sell",
        entry_price=50000.0,
        stop_loss=51000.0,
        take_profit=48000.0,
        quantity=0.02,
        trade_uid="test-uid-002",
        order_link_id="forecast_test-uid-002",
        order_type="Limit",
        leverage=5,
        confidence=80.0,
        consensus_id=None,
        methods="",
        rationale="",
        created_at="2024-01-01T00:00:00+00:00",
    )
    trade_id = repo.insert_trade_for_bracket(
        trade_uid="test-uid-002",
        ticker="BTCUSDT",
        symbol="BTCUSDT",
        signal="SHORT",
        quantity=0.02,
        entry_price=50000.0,
        stop_loss=51000.0,
        target_price=48000.0,
        entry_order_id=ids["entry_id"],
        consensus_id=None,
        leverage=5,
        created_at="2024-01-01T00:00:00+00:00",
    )

    assert trade_id > 0
    with bracket_db._connect() as con:
        trade = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    assert trade is not None
    assert trade["trade_uid"] == "test-uid-002"
    assert trade["ib_parent_id"] == ids["entry_id"]
    assert trade["signal"] == "SHORT"
