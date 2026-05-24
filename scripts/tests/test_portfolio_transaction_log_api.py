"""Tests for portfolio transaction log API helpers."""

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    from scripts.core.bybit_migrate import create_bybit_uta_transaction_log_table

    create_bybit_uta_transaction_log_table(con)
    synced = datetime.now(tz=timezone.utc).isoformat()
    con.execute(
        """
        INSERT INTO bybit_uta_transaction_log (
            bybit_id, transaction_time, currency, symbol, type, direction,
            side, qty, size, trade_price, funding, fee, cash_flow, change,
            cash_balance, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "a1", "2026-05-20T10:00:00+00:00", "USDT", "BTCUSDT", "TRADE",
            "Open Buy", "Buy", "1", "1", "50000", "0", "1", "0", "-1", "1000",
            synced,
        ),
    )
    con.execute(
        """
        INSERT INTO bybit_uta_transaction_log (
            bybit_id, transaction_time, currency, symbol, type, direction,
            side, qty, size, trade_price, funding, fee, cash_flow, change,
            cash_balance, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "a2", "2026-05-22T10:00:00+00:00", "ETH", "", "TRANSFER_IN",
            "--", "None", "", "", "", "", "", "100", "100", "200",
            synced,
        ),
    )
    con.commit()
    con.close()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


class TestPortfolioTransactionLogQuery:
    def test_filter_by_currency_and_date(self, temp_db):
        from scripts.core.sqlite_manager import SQLiteManager

        em = SQLiteManager(temp_db)
        clauses = ["UPPER(currency)=UPPER(?)", "transaction_time>=?"]
        params = ["USDT", "2026-05-19"]
        where_sql = f" WHERE {' AND '.join(clauses)}"
        with em._connect() as con:
            rows = con.execute(
                f"SELECT * FROM bybit_uta_transaction_log{where_sql} "
                f"ORDER BY transaction_time DESC",
                params,
            ).fetchall()
        assert len(rows) == 1
        assert dict(rows[0])["symbol"] == "BTCUSDT"

    def test_filter_by_symbol(self, temp_db):
        from scripts.core.sqlite_manager import SQLiteManager

        em = SQLiteManager(temp_db)
        with em._connect() as con:
            rows = con.execute(
                "SELECT * FROM bybit_uta_transaction_log "
                "WHERE UPPER(symbol)=UPPER(?) ORDER BY transaction_time DESC",
                ("BTCUSDT",),
            ).fetchall()
        assert len(rows) == 1
