"""Tests for Bybit UTA transaction log sync."""

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
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
    con = sqlite3.connect(path)
    from scripts.core.bybit_migrate import create_bybit_uta_transaction_log_table

    create_bybit_uta_transaction_log_table(con)
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


SAMPLE_TRADE = {
    "id": "tx-001",
    "transactionTime": "1672121182224",
    "currency": "USDT",
    "symbol": "ETHUSDT",
    "category": "linear",
    "type": "TRADE",
    "side": "Sell",
    "qty": "0.4",
    "size": "-0.4",
    "tradePrice": "2101.25",
    "funding": "0",
    "fee": "0.4623",
    "cashFlow": "14.9126",
    "change": "14.4503",
    "cashBalance": "5086.58",
    "orderId": "ord-1",
    "tradeId": "tr-1",
    "feeRate": "0.0006",
    "transSubType": "",
}


class TestTransactionLogHelpers:
    def test_iter_time_chunks_splits_14_days(self):
        from scripts.core.bybit_transaction_log_sync import iter_time_chunks, _CHUNK_MS

        start = 0
        end = 14 * 24 * 3600 * 1000
        chunks = iter_time_chunks(start, end)
        assert len(chunks) == 2
        assert chunks[0][1] - chunks[0][0] <= _CHUNK_MS

    def test_compute_trade_direction_open_sell(self):
        from scripts.core.bybit_transaction_log_sync import compute_trade_direction

        # short position -0.4 after sell of 0.4 from flat
        direction = compute_trade_direction("TRADE", "Sell", "0.4", "-0.4")
        assert direction == "Open Sell"

    def test_compute_trade_direction_transfer(self):
        from scripts.core.bybit_transaction_log_sync import compute_trade_direction

        assert compute_trade_direction("TRANSFER_IN", "None", "", "") == "--"

    def test_normalize_row(self):
        from scripts.core.bybit_transaction_log_sync import normalize_transaction_row

        row = normalize_transaction_row(SAMPLE_TRADE, synced_at="2026-05-24T00:00:00+00:00")
        assert row["bybit_id"] == "tx-001"
        assert row["currency"] == "USDT"
        assert row["symbol"] == "ETHUSDT"
        assert "+00:00" in row["transaction_time"]


class TestUpsertAndSync:
    def test_upsert_dedup_by_bybit_id(self, db_manager):
        from scripts.core.bybit_transaction_log_sync import (
            normalize_transaction_row,
            upsert_transaction_rows,
        )

        synced_at = datetime.now(tz=timezone.utc).isoformat()
        row = normalize_transaction_row(SAMPLE_TRADE, synced_at=synced_at)
        assert upsert_transaction_rows(db_manager, [row]) == 1

        updated = dict(SAMPLE_TRADE)
        updated["fee"] = "0.99"
        row2 = normalize_transaction_row(updated, synced_at=synced_at)
        assert upsert_transaction_rows(db_manager, [row2]) == 1

        with db_manager._connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM bybit_uta_transaction_log"
            ).fetchone()[0]
            fee = con.execute(
                "SELECT fee FROM bybit_uta_transaction_log WHERE bybit_id=?",
                ("tx-001",),
            ).fetchone()[0]
        assert count == 1
        assert fee == "0.99"

    def test_sync_paginates_cursor(self, db_manager):
        from scripts.core.bybit_transaction_log_sync import sync_bybit_transaction_log

        page1 = {"list": [SAMPLE_TRADE], "nextPageCursor": "cursor-2"}
        page2 = {
            "list": [
                {
                    **SAMPLE_TRADE,
                    "id": "tx-002",
                    "transactionTime": "1672121183000",
                }
            ],
            "nextPageCursor": "",
        }

        def fake_fetch(**kwargs):
            if kwargs.get("cursor"):
                return page2
            return page1

        with patch(
            "scripts.core.bybit_transaction_log_sync._fetch_page",
            side_effect=fake_fetch,
        ):
            result = sync_bybit_transaction_log(
                db_manager,
                start_ms=1672000000000,
                end_ms=1672000000000 + 24 * 3600 * 1000,
            )

        assert result["fetched"] == 2
        assert result["synced"] == 2
        with db_manager._connect() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM bybit_uta_transaction_log"
            ).fetchone()[0]
        assert count == 2
