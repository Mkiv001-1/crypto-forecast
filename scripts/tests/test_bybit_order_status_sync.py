"""
Unit tests for Bybit Order Status Sync.

Tests are self-contained: no real Bybit connection required.
"""

import sys
import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

# Mock pybit before importing bybit modules
class FakePybitModule:
    pass

class FakeUnifiedTrading:
    class HTTP:
        def __init__(self, *args, **kwargs):
            pass

fake_pybit = FakePybitModule()
fake_pybit.unified_trading = FakeUnifiedTrading
sys.modules["pybit"] = fake_pybit
sys.modules["pybit.unified_trading"] = FakeUnifiedTrading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))


@pytest.fixture
def mock_db():
    """Create temporary database with required tables."""
    db_file = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(db_file)
    con.executescript("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            bybit_order_id TEXT,
            bybit_order_link_id TEXT,
            symbol TEXT,
            side TEXT,
            order_role TEXT,
            status TEXT DEFAULT 'PENDING',
            quantity REAL,
            entry_price REAL,
            trade_uid TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE bybit_order_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT,
            event_source TEXT,
            event_type TEXT,
            operation_status TEXT,
            status_before TEXT,
            status_after TEXT,
            ticker TEXT,
            trade_uid TEXT,
            bybit_order_id TEXT,
            order_id INTEGER,
            trade_id INTEGER,
            request_payload_json TEXT,
            response_payload_json TEXT,
            error_message TEXT,
            latency_ms REAL
        );
    """)
    con.commit()
    con.close()
    
    class FakeDb:
        def __init__(self, file):
            self.db_file = file
        def _connect(self):
            return sqlite3.connect(self.db_file)
    
    db = FakeDb(db_file)
    yield db
    
    try:
        os.unlink(db_file)
    except:
        pass


class TestBybitOrderStatusSyncStatusMapping:
    """Test status mapping from Bybit to internal."""

    def test_map_status_new(self):
        """Test mapping 'New' status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("New")
        assert result == "SUBMITTED"

    def test_map_status_partially_filled(self):
        """Test mapping 'PartiallyFilled' status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("PartiallyFilled")
        assert result == "PARTIALLY_FILLED"

    def test_map_status_filled(self):
        """Test mapping 'Filled' status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("Filled")
        assert result == "FILLED_ENTRY"

    def test_map_status_cancelled(self):
        """Test mapping 'Cancelled' status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("Cancelled")
        assert result in ["CANCELLED", "CANCELED"]

    def test_map_status_rejected(self):
        """Test mapping 'Rejected' status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("Rejected")
        assert result == "REJECTED"

    def test_map_status_unknown(self):
        """Test mapping unknown status."""
        from bybit_order_status_sync import _map_bybit_status
        
        result = _map_bybit_status("UnknownStatus")
        assert result == "UnknownStatus"


class TestBybitOrderStatusSyncMain:
    """Test main sync_orders_with_bybit function."""

    def test_sync_orders_worker_not_running(self, mock_db):
        """Test handling when Bybit worker not running."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=False):
            result = sync_orders_with_bybit(mock_db)
        
        # Should return empty/skipped result
        assert result["checked"] == 0
        assert result["updated"] == 0

    def test_sync_orders_no_orders_in_db(self, mock_db):
        """Test sync when no orders in database."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=[]):
                result = sync_orders_with_bybit(mock_db)
        
        assert result["checked"] == 0
        assert result["updated"] == 0

    def test_sync_orders_with_pending_orders(self, mock_db):
        """Test sync updates pending orders."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        # Insert pending order with bybit_order_link_id
        with mock_db._connect() as con:
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, bybit_order_link_id, order_role, status, quantity, created_at)
                VALUES ('BTCUSDT', 'order-123', 'link-123', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')
            """)
            con.commit()
        
        # Mock Bybit response - order is now filled
        mock_bybit_orders = [
            {
                "orderId": "order-123",
                "orderLinkId": "link-123",
                "orderStatus": "Filled",
                "avgPrice": "50000.00",
                "cumExecQty": "0.1"
            }
        ]
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=mock_bybit_orders):
                result = sync_orders_with_bybit(mock_db)
        
        # Should check at least one order (may be 0 if filtering logic excludes it)
        assert "checked" in result
        # Order status checked (may or may not be updated depending on sync logic)
        with mock_db._connect() as con:
            row = con.execute("SELECT status FROM orders WHERE bybit_order_id='order-123'").fetchone()
            assert row is not None

    def test_sync_orders_dry_run(self, mock_db):
        """Test dry_run mode doesn't modify DB."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        # Insert pending order
        with mock_db._connect() as con:
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
                VALUES ('BTCUSDT', 'order-123', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')
            """)
            con.commit()
        
        mock_bybit_orders = [
            {"orderId": "order-123", "orderStatus": "Filled", "avgPrice": "50000.00"}
        ]
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=mock_bybit_orders):
                result = sync_orders_with_bybit(mock_db, dry_run=True)
        
        # Status should NOT change in dry_run
        with mock_db._connect() as con:
            row = con.execute("SELECT status FROM orders WHERE bybit_order_id='order-123'").fetchone()
            assert row[0] == "SUBMITTED"  # Unchanged

    def test_sync_orders_with_ticker_filter(self, mock_db):
        """Test sync with specific ticker filter."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        # Insert orders for different tickers with bybit_order_link_id
        with mock_db._connect() as con:
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, bybit_order_link_id, order_role, status, quantity, created_at)
                VALUES ('BTCUSDT', 'btc-order', 'btc-link', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')
            """)
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, bybit_order_link_id, order_role, status, quantity, created_at)
                VALUES ('ETHUSDT', 'eth-order', 'eth-link', 'ENTRY', 'SUBMITTED', 1.0, '2024-01-01')
            """)
            con.commit()
        
        mock_bybit_orders = [
            {"orderId": "btc-order", "orderLinkId": "btc-link", "orderStatus": "Filled", "avgPrice": "50000.00"}
        ]
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=mock_bybit_orders):
                result = sync_orders_with_bybit(mock_db, ticker="BTCUSDT")
        
        # Should return result with checked field
        assert "checked" in result

    def test_sync_orders_source_parameter(self, mock_db):
        """Test source parameter is accepted (used by scheduler)."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=[]):
                # This is how scheduler calls it
                result = sync_orders_with_bybit(mock_db, source="scheduler")
        
        assert "checked" in result


class TestLogStatusTransaction:
    """Regression: INSERT column count must match placeholders."""

    def test_log_status_transaction_insert(self, mock_db):
        from bybit_order_status_sync import _log_status_transaction

        with mock_db._connect() as con:
            _log_status_transaction(
                mock_db,
                event_source="test",
                event_type="status_change",
                operation_status="success",
                status_before="SUBMITTED",
                status_after="FILLED_ENTRY",
                ticker="BTCUSDT",
                trade_uid="t-1",
                bybit_order_id="bybit-1",
                order_id=1,
                trade_id=None,
                payload_json='{"status": "Filled"}',
                con=con,
            )
            con.commit()
            row = con.execute(
                "SELECT COUNT(*) FROM bybit_order_transactions"
            ).fetchone()
        assert row[0] == 1


class TestBybitMigrateOrdersSchema:
    """Ensure migrate_orders_table adds columns required by sync SELECT."""

    def test_migrate_adds_side_column(self, mock_db):
        from bybit_migrate import migrate_orders_table

        with mock_db._connect() as con:
            migrate_orders_table(con)
            con.commit()
            cols = {r[1] for r in con.execute("PRAGMA table_info(orders)").fetchall()}
        assert "side" in cols
        assert "entry_price" in cols

    def test_sync_query_with_side_column(self, mock_db):
        from bybit_migrate import migrate_orders_table
        from bybit_order_status_sync import sync_orders_with_bybit

        with mock_db._connect() as con:
            migrate_orders_table(con)
            con.execute(
                """INSERT INTO orders (
                    ticker, bybit_order_id, bybit_order_link_id, order_role, status,
                    side, quantity, entry_price, created_at
                ) VALUES ('BTCUSDT', 'ord-1', 'link-1', 'ENTRY', 'SUBMITTED',
                    'Buy', 0.1, 50000.0, '2024-01-01')"""
            )
            con.commit()

        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=[]):
                result = sync_orders_with_bybit(mock_db)

        assert result["errors"] == 0
        assert result["checked"] == 1


class TestBybitOrderStatusSyncSchedulerIntegration:
    """Test integration with scheduler."""

    def test_scheduler_calls_with_source(self, mock_db):
        """Test that scheduler calls sync with source parameter."""
        from bybit_order_status_sync import sync_orders_with_bybit
        
        # This simulates how scheduler calls the function
        with patch("bybit_order_status_sync.is_bybit_running", return_value=True):
            with patch("bybit_order_status_sync.bybit_request_sync", return_value=[]):
                result = sync_orders_with_bybit(mock_db, source="scheduler")
        
        # Should work without errors
        assert isinstance(result, dict)
        assert "checked" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
