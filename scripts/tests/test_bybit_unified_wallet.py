"""Tests for Bybit unified wallet helpers."""

import json
import os
import sqlite3
import sys
import tempfile

import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


MOCK_WALLET = {
    "account_type": "UNIFIED",
    "total_equity": 184586.77,
    "total_perp_upl": -97.73,
    "total_available_balance": 180000.0,
    "total_maintenance_margin": 1200.0,
    "coins": [
        {"coin": "USDT", "equity": 53176.92, "available_balance": 50000.0},
    ],
    "timestamp": "2026-05-24T12:00:00+00:00",
}


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, description TEXT)")
    con.commit()
    con.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db):
    from scripts.core.sqlite_manager import SQLiteManager

    return SQLiteManager(temp_db)


class TestBybitUnifiedWallet:
    def test_cache_and_load(self, db_manager):
        from scripts.core.bybit_unified_wallet import (
            cache_unified_wallet,
            load_cached_unified_wallet,
            CONFIG_KEY,
        )

        cache_unified_wallet(db_manager, MOCK_WALLET)
        loaded = load_cached_unified_wallet(db_manager)
        assert loaded["total_equity"] == 184586.77
        assert db_manager.get_config_value(CONFIG_KEY)

    def test_build_portfolio_asset_records(self):
        from scripts.core.bybit_unified_wallet import build_portfolio_asset_records

        records = build_portfolio_asset_records(MOCK_WALLET)
        assert len(records) == 1
        assert records[0]["row_type"] == "asset"
        assert records[0]["ticker"] == "USDT"

    def test_build_portfolio_summary_record(self):
        from scripts.core.bybit_unified_wallet import build_portfolio_summary_record

        record = build_portfolio_summary_record(MOCK_WALLET, positions_count=3)
        assert record["row_type"] == "summary"
        assert record["ticker"] == "__ACCOUNT_SUMMARY__"
        assert record["equity"] == 184586.77
        assert record["unrealized_pnl"] == -97.73
        assert record["positions_count"] == 3
        assert record["currency"] == "USD"

    def test_usdt_available_balance(self):
        from scripts.core.bybit_unified_wallet import usdt_available_balance

        assert usdt_available_balance(MOCK_WALLET) == 50000.0

    def test_sync_logs_portfolio_snapshot_transaction(self, db_manager):
        from scripts.core.bybit_migrate import create_bybit_transactions_table
        from scripts.core.bybit_unified_wallet import cache_unified_wallet, sync_unified_wallet_snapshot

        with db_manager._connect() as con:
            create_bybit_transactions_table(con)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    ticker TEXT,
                    row_type TEXT,
                    equity REAL,
                    unrealized_pnl REAL,
                    realized_pnl REAL,
                    cumulative_pnl REAL,
                    volume REAL,
                    price REAL,
                    account TEXT,
                    currency TEXT,
                    net_liquidation REAL,
                    buying_power REAL,
                    available_funds REAL,
                    cash REAL,
                    maintenance_margin REAL,
                    positions_count INTEGER,
                    accounts_count INTEGER,
                    con_id INTEGER
                )
                """
            )

        cache_unified_wallet(db_manager, MOCK_WALLET)
        wallet, inserted = sync_unified_wallet_snapshot(db_manager, wallet=MOCK_WALLET)
        assert wallet is not None
        assert inserted > 0

        with db_manager._connect() as con:
            row = con.execute(
                "SELECT event_type, operation_status, ticker FROM bybit_order_transactions"
            ).fetchone()
        assert row is not None
        assert row[0] == "PORTFOLIO_SNAPSHOT"
        assert row[1] == "SUCCESS"
        assert row[2] == "__ACCOUNT_SUMMARY__"
