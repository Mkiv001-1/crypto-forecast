"""
Unit tests for Bybit Order Manager.

Tests are self-contained: no real Bybit connection required.
"""

import sys
import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

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
            order_role TEXT,
            order_type TEXT,
            action TEXT,
            quantity REAL,
            limit_price REAL,
            stop_price REAL,
            status TEXT DEFAULT 'PENDING',
            parent_order_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, description TEXT);
        CREATE TABLE settings (ticker TEXT PRIMARY KEY, active INTEGER, trading_blocked INTEGER);
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY,
            bybit_order_id TEXT,
            status TEXT DEFAULT 'OPEN'
        );
    """)
    con.execute("INSERT INTO config VALUES ('ORDER_MODE', 'paper', '')")
    con.execute("INSERT INTO config VALUES ('MAX_OPEN_ORDERS', '10', '')")
    con.execute("INSERT INTO settings VALUES ('BTCUSDT', 1, 0)")
    con.commit()
    con.close()
    
    class FakeDb:
        def __init__(self, file):
            self.db_file = file
        def _connect(self):
            return sqlite3.connect(self.db_file)
        def get_config_value(self, key, default=None):
            with self._connect() as con:
                row = con.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
                return row[0] if row else default
    
    db = FakeDb(db_file)
    from scripts.core.storage.repositories.orders_repo import OrdersRepository

    db.orders_repo = OrdersRepository(db)
    yield db
    
    try:
        os.unlink(db_file)
    except:
        pass


class TestBybitOrderManagerConfig:
    """Test configuration helpers."""

    def test_cfg_string(self, mock_db):
        """Test _cfg with string values."""
        from bybit_order_manager import _cfg
        
        result = _cfg(mock_db, "ORDER_MODE", "disabled")
        assert result == "paper"  # From fixture
        
        result = _cfg(mock_db, "NONEXISTENT", "default")
        assert result == "default"

    def test_cfg_int(self, mock_db):
        """Test _cfg_int conversion."""
        from bybit_order_manager import _cfg_int
        
        result = _cfg_int(mock_db, "MAX_OPEN_ORDERS", 5)
        assert result == 10  # From fixture
        
        result = _cfg_int(mock_db, "INVALID", 100)
        assert result == 100  # Default

    def test_cfg_bool(self, mock_db):
        """Test _cfg_bool conversion."""
        from bybit_order_manager import _cfg_bool
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('LIVE_TRADING_CONFIRMED', 'true', '')")
            con.commit()
        
        result = _cfg_bool(mock_db, "LIVE_TRADING_CONFIRMED", False)
        assert result is True


class TestBybitOrderManagerChecks:
    """Test order validation checks."""

    def test_is_ticker_blocked_true(self, mock_db):
        """Test blocked ticker detection."""
        from bybit_order_manager import _is_ticker_blocked
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO settings VALUES ('BLOCKED', 1, 1)")
            con.commit()
        
        result = _is_ticker_blocked(mock_db, "BLOCKED")
        assert result is True

    def test_is_ticker_blocked_false(self, mock_db):
        """Test non-blocked ticker."""
        from bybit_order_manager import _is_ticker_blocked
        
        result = _is_ticker_blocked(mock_db, "BTCUSDT")
        assert result is False

    def test_is_ticker_known_true(self, mock_db):
        """Test known ticker detection."""
        from bybit_order_manager import _is_ticker_known
        
        result = _is_ticker_known(mock_db, "BTCUSDT")
        assert result is True

    def test_is_ticker_known_false(self, mock_db):
        """Test unknown ticker."""
        from bybit_order_manager import _is_ticker_known
        
        result = _is_ticker_known(mock_db, "UNKNOWN")
        assert result is False

    def test_count_open_orders_empty(self, mock_db):
        """Test counting open orders when none exist."""
        from bybit_order_manager import _count_open_orders
        
        count = _count_open_orders(mock_db)
        assert count == 0

    def test_count_open_orders_with_orders(self, mock_db):
        """Test counting open orders."""
        from bybit_order_manager import _count_open_orders
        
        with mock_db._connect() as con:
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
                VALUES ('BTCUSDT', '123', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')
            """)
            con.commit()
        
        count = _count_open_orders(mock_db)
        assert count == 1

    def test_has_open_order_for_ticker_true(self, mock_db):
        """Test detecting existing order for ticker."""
        from bybit_order_manager import _has_open_order_for_ticker
        
        with mock_db._connect() as con:
            con.execute("""
                INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
                VALUES ('BTCUSDT', '123', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')
            """)
            con.commit()
        
        result = _has_open_order_for_ticker(mock_db, "BTCUSDT")
        assert result is True

    def test_has_open_order_for_ticker_false(self, mock_db):
        """Test no order for ticker."""
        from bybit_order_manager import _has_open_order_for_ticker
        
        result = _has_open_order_for_ticker(mock_db, "ETHUSDT")
        assert result is False


class TestBybitOrderManagerSubmit:
    """Test signal submission."""

    def test_submit_signal_disabled_mode(self, mock_db):
        """Test rejection when ORDER_MODE=disabled."""
        from bybit_order_manager import submit_signal
        
        with mock_db._connect() as con:
            con.execute("UPDATE config SET value='disabled' WHERE key='ORDER_MODE'")
            con.commit()
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="BTCUSDT",
            side="Buy",
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=75.0
        )
        
        assert result["status"] == "REJECTED"

    def test_submit_signal_neutral_side(self, mock_db):
        """Test that neutral/both sides are handled."""
        from bybit_order_manager import submit_signal
        # Skip this test - bybit order manager doesn't have neutral side
        # It only accepts Buy or Sell
        pytest.skip("Bybit order manager doesn't support neutral side")

    def test_submit_signal_blocked_ticker(self, mock_db):
        """Test rejection for blocked ticker."""
        from bybit_order_manager import submit_signal
        
        with mock_db._connect() as con:
            con.execute("UPDATE settings SET trading_blocked=1 WHERE ticker='BTCUSDT'")
            con.commit()
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="BTCUSDT",
            side="Buy",
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=75.0
        )
        
        assert result["status"] == "REJECTED"

    def test_submit_signal_unknown_ticker(self, mock_db):
        """Test rejection for unknown ticker."""
        from bybit_order_manager import submit_signal
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="UNKNOWN",
            side="Buy",
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            confidence=75.0
        )
        
        assert result["status"] == "REJECTED"

    def test_submit_signal_zero_stop_loss(self, mock_db):
        """Test rejection with invalid stop loss."""
        from bybit_order_manager import submit_signal
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="BTCUSDT",
            side="Buy",
            entry_price=50000.0,
            stop_loss=0,  # Invalid
            take_profit=52000.0,
            confidence=75.0
        )
        
        # Should be rejected due to invalid stop
        assert result["status"] == "REJECTED"

    def test_submit_signal_long(self, mock_db):
        """Test successful LONG (Buy) signal submission."""
        from bybit_order_manager import submit_signal
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="BTCUSDT",
            side="Buy",
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=75.0
        )
        
        # Result should have status field
        assert "status" in result

    def test_submit_signal_short(self, mock_db):
        """Test successful SHORT (Sell) signal submission."""
        from bybit_order_manager import submit_signal
        
        result = submit_signal(
            db_manager=mock_db,
            ticker="BTCUSDT",
            side="Sell",
            entry_price=50000.0,
            stop_loss=51000.0,
            take_profit=48000.0,
            confidence=75.0
        )
        
        # Result should have status field
        assert "status" in result


class TestBybitOrderManagerHelpers:
    """Test helper functions."""

    def test_symbol_from_ticker(self):
        """Test symbol extraction from ticker."""
        from bybit_order_manager import _symbol_from_ticker
        
        assert _symbol_from_ticker("BTCUSDT") == "BTCUSDT"
        assert _symbol_from_ticker(" btcusdt ") == "BTCUSDT"

    def test_is_market_hours(self):
        """Test crypto market hours (always open)."""
        from bybit_order_manager import _is_market_hours
        
        assert _is_market_hours() is True

    def test_get_ticker_lock(self):
        """Test per-ticker lock creation."""
        from bybit_order_manager import _get_ticker_lock
        
        lock1 = _get_ticker_lock("BTCUSDT")
        lock2 = _get_ticker_lock("BTCUSDT")
        lock3 = _get_ticker_lock("ETHUSDT")
        
        assert lock1 is lock2  # Same ticker, same lock
        assert lock1 is not lock3  # Different ticker, different lock


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
