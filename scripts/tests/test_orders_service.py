"""Unit tests for manual order submission service."""

import os
import sys
import sqlite3
import tempfile
from unittest.mock import patch

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
    from scripts.core.sqlite_manager import SQLiteManager

    db = SQLiteManager(path)
    with db._connect() as con:
        con.execute(
            """INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
               VALUES ('BTCUSDT', 1, 'test', 'crypto', 0)"""
        )
        con.execute(
            """INSERT INTO consensus (
                ticker, date, signal, confidence, stop_loss, target_price
            ) VALUES ('BTCUSDT', '2024-01-01', 'NEUTRAL', 80.0, 48000, 52000)"""
        )
        con.commit()
    yield db
    try:
        os.unlink(path)
    except OSError:
        pass


def test_submit_skipped_neutral(temp_db):
    from scripts.server.services.orders_service import submit_manual_from_consensus

    result = submit_manual_from_consensus(temp_db, ticker="BTCUSDT")
    assert result["status"] == "SKIPPED_NEUTRAL"
    assert result["order_ids"] == []


def test_submit_no_import_error_on_long(temp_db):
    from scripts.server.services.orders_service import submit_manual_from_consensus

    with temp_db._connect() as con:
        con.execute(
            "UPDATE consensus SET signal='LONG' WHERE ticker='BTCUSDT'"
        )
        con.commit()

    with patch(
        "scripts.server.services.orders_service.get_available_capital",
        return_value=10000.0,
    ), patch(
        "scripts.server.services.orders_service.calculate_position",
        return_value={"status": "OK", "quantity": 1},
    ), patch(
        "scripts.core.bybit_order_manager.submit_signal",
        return_value={"status": "REJECTED", "reason": "Bybit worker not running"},
    ):
        result = submit_manual_from_consensus(temp_db, ticker="BTCUSDT")

    assert result["status"] == "REJECTED"
    assert "Bybit" in result["message"] or result["message"] == ""
