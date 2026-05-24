"""Tests for reset_forecasts_consensus_and_trading (no Bybit network)."""

import os
import sqlite3
import sys
import tempfile

import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in (_PROJECT_ROOT, _SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.core.sqlite_manager import SQLiteManager


@pytest.fixture
def reset_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE forecast_runs (id INTEGER PRIMARY KEY);
        CREATE TABLE logs (id TEXT PRIMARY KEY);
        CREATE TABLE consensus (id INTEGER PRIMARY KEY);
        CREATE TABLE forecast_run_links (id INTEGER PRIMARY KEY);
        CREATE TABLE orders (id INTEGER PRIMARY KEY);
        CREATE TABLE trades (id INTEGER PRIMARY KEY);
        CREATE TABLE settings (ticker TEXT PRIMARY KEY, active INTEGER);
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, broker TEXT, account_id TEXT);
        CREATE TABLE bybit_order_transactions (id INTEGER PRIMARY KEY);
        CREATE TABLE providers (
            provider TEXT PRIMARY KEY,
            ema_accuracy REAL DEFAULT 0.5,
            ema_updated_at TEXT,
            forecast_count INTEGER DEFAULT 0
        );
    """)
    con.execute("INSERT INTO forecast_runs DEFAULT VALUES")
    con.execute("INSERT INTO logs VALUES ('log1')")
    con.execute("INSERT INTO consensus DEFAULT VALUES")
    con.execute("INSERT INTO forecast_run_links DEFAULT VALUES")
    con.execute("INSERT INTO orders DEFAULT VALUES")
    con.execute("INSERT INTO trades DEFAULT VALUES")
    con.execute("INSERT INTO settings VALUES ('BTC', 1)")
    con.execute("INSERT INTO accounts VALUES (1, 'bybit', 'bybit-demo')")
    con.execute("INSERT INTO bybit_order_transactions DEFAULT VALUES")
    con.execute(
        "INSERT INTO providers VALUES ('openrouter', 0.72, '2026-01-01', 10)"
    )
    con.commit()
    con.close()
    db = SQLiteManager.__new__(SQLiteManager)
    db.db_file = os.path.abspath(path)
    yield db
    try:
        os.remove(path)
    except OSError:
        pass


def test_reset_clears_trading_tables_keeps_config(reset_db):
    db = reset_db
    with db._connect() as con:
        before_tx = con.execute(
            "SELECT COUNT(*) FROM bybit_order_transactions"
        ).fetchone()[0]
    assert before_tx == 1

    summary = db.reset_forecasts_consensus_and_trading()
    assert summary["ok"] is True
    assert summary["deleted_consensus"] == 1
    assert summary["deleted_orders"] == 1

    with db._connect() as con:
        assert con.execute("SELECT COUNT(*) FROM consensus").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        assert (
            con.execute("SELECT COUNT(*) FROM bybit_order_transactions").fetchone()[0]
            == 1
        )
        ema = con.execute(
            "SELECT ema_accuracy FROM providers WHERE provider='openrouter'"
        ).fetchone()[0]
        assert ema == pytest.approx(0.72)


def test_reset_dry_run_counts(reset_db):
    db = reset_db
    summary = db.reset_forecasts_consensus_and_trading_dry_run()
    assert summary["ok"] is True
    assert summary["would_delete_consensus"] == 1
    with db._connect() as con:
        assert con.execute("SELECT COUNT(*) FROM consensus").fetchone()[0] == 1
