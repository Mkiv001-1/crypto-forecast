"""
Unit tests for Bybit Capital Provider.

Tests are self-contained: no real Bybit connection required.
"""

import sys
import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
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
    """Create temporary database with config table."""
    db_file = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(db_file)
    con.executescript("""
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, description TEXT);
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            broker TEXT,
            account_id TEXT,
            account_type TEXT,
            net_liquidation REAL,
            last_sync TEXT
        );
    """)
    con.execute("INSERT INTO config VALUES ('PREFERRED_ACCOUNT_TYPE', 'live', '')")
    con.execute("INSERT INTO config VALUES ('CAPITAL_STALENESS_MINUTES', '15', '')")
    con.execute("INSERT INTO config VALUES ('IB_CAPITAL_FAILSAFE', 'manual_only', '')")
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
    yield db
    
    try:
        os.unlink(db_file)
    except:
        pass


class TestBybitCapitalProviderManualOverride:
    """Test manual capital override functionality."""

    def test_manual_override_returns_value(self, mock_db):
        """Test reading manual capital override."""
        from bybit_capital_provider import _manual_override
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', '50000', '')")
            con.commit()
        
        result = _manual_override(mock_db)
        
        assert result == 50000.0

    def test_manual_override_empty_returns_none(self, mock_db):
        """Test empty manual override returns None."""
        from bybit_capital_provider import _manual_override
        
        with mock_db._connect() as con:
            con.execute("DELETE FROM config WHERE key='MANUAL_CAPITAL_OVERRIDE'")
            con.commit()
        
        result = _manual_override(mock_db)
        
        assert result is None

    def test_manual_override_invalid_returns_none(self, mock_db):
        """Test invalid manual override value returns None."""
        from bybit_capital_provider import _manual_override
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', 'invalid', '')")
            con.commit()
        
        result = _manual_override(mock_db)
        
        assert result is None

    def test_manual_override_zero_returns_none(self, mock_db):
        """Test zero manual override returns None."""
        from bybit_capital_provider import _manual_override
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', '0', '')")
            con.commit()
        
        result = _manual_override(mock_db)
        
        assert result is None

    def test_manual_override_negative_returns_none(self, mock_db):
        """Test negative manual override returns None."""
        from bybit_capital_provider import _manual_override
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', '-1000', '')")
            con.commit()
        
        result = _manual_override(mock_db)
        
        assert result is None


class TestBybitCapitalProviderBalance:
    """Test Bybit balance fetching."""

    def test_get_bybit_balance_sync_success(self, mock_db):
        """Test successful balance fetch from Bybit."""
        from bybit_capital_provider import _get_bybit_balance_sync

        mock_wallet = {
            "total_equity": 75000.0,
            "total_perp_upl": 2000.0,
            "total_available_balance": 70000.0,
            "timestamp": "2026-05-24T10:00:00+00:00",
            "coins": [
                {"coin": "USDT", "available_balance": 70000.0},
            ],
        }

        with patch("bybit_capital_provider.is_bybit_running", return_value=True):
            with patch(
                "scripts.core.bybit_unified_wallet.fetch_unified_wallet_sync",
                return_value=mock_wallet,
            ):
                result = _get_bybit_balance_sync(mock_db)

        assert result is not None
        assert result["equity"] == 75000.0
        assert result["available"] == 70000.0
        assert "timestamp" in result

    def test_get_bybit_balance_sync_worker_not_running(self, mock_db):
        """Test when Bybit worker is not running."""
        from bybit_capital_provider import _get_bybit_balance_sync

        with patch("bybit_capital_provider.is_bybit_running", return_value=False):
            result = _get_bybit_balance_sync(mock_db)

        assert result is None

    def test_get_bybit_balance_sync_api_error(self, mock_db):
        """Test handling of API error."""
        from bybit_capital_provider import _get_bybit_balance_sync

        with patch("bybit_capital_provider.is_bybit_running", return_value=True):
            with patch(
                "scripts.core.bybit_unified_wallet.fetch_unified_wallet_sync",
                return_value=None,
            ):
                result = _get_bybit_balance_sync(mock_db)

        assert result is None


class TestBybitCapitalProviderMain:
    """Test main get_available_capital function."""

    def test_get_available_capital_manual_override(self, mock_db):
        """Test using manual capital override."""
        from bybit_capital_provider import get_available_capital
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', '50000', '')")
            con.commit()
        
        capital = get_available_capital(mock_db)
        
        assert capital == 50000.0

    def test_get_available_capital_from_bybit(self, mock_db):
        """Test getting capital from Bybit API."""
        from bybit_capital_provider import get_available_capital
        
        # No manual override
        with mock_db._connect() as con:
            con.execute("DELETE FROM config WHERE key='MANUAL_CAPITAL_OVERRIDE'")
            con.commit()
        
        mock_balance = {
            "equity": 60000.0,
            "available": 55000.0,
            "unrealized_pnl": 1000.0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with patch("bybit_capital_provider.is_bybit_running", return_value=True):
            with patch("bybit_capital_provider._get_bybit_balance_sync", return_value=mock_balance):
                capital = get_available_capital(mock_db)
        
        assert capital == 55000.0  # available balance is used

    def test_get_available_capital_min_capital_check(self, mock_db):
        """Test minimum capital enforcement."""
        from bybit_capital_provider import get_available_capital, CapitalUnavailableError
        
        with mock_db._connect() as con:
            con.execute("INSERT OR REPLACE INTO config VALUES ('MANUAL_CAPITAL_OVERRIDE', '100', '')")
            con.commit()
        
        with pytest.raises(CapitalUnavailableError) as exc_info:
            get_available_capital(mock_db, min_capital=1000.0)
        
        assert "below minimum" in str(exc_info.value).lower()

    def test_get_available_capital_fallback_to_cache(self, mock_db):
        """Test fallback to cached value."""
        from bybit_capital_provider import get_available_capital, _FALLBACK_CAPITAL_CACHE
        
        # Clear and set cache (use "value" key as per implementation)
        _FALLBACK_CAPITAL_CACHE.clear()
        _FALLBACK_CAPITAL_CACHE["value"] = 45000.0
        _FALLBACK_CAPITAL_CACHE["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # No manual override, API fails
        with mock_db._connect() as con:
            con.execute("DELETE FROM config WHERE key='MANUAL_CAPITAL_OVERRIDE'")
            con.commit()
        
        with patch("bybit_capital_provider.is_bybit_running", return_value=True):
            with patch("bybit_capital_provider._get_bybit_balance_sync", return_value=None):
                capital = get_available_capital(mock_db, allow_fallback=True)
        
        assert capital == 45000.0




class TestBybitCapitalProviderStaleness:
    """Test data staleness checking - skipped as functions not implemented."""
    
    def test_staleness_check_not_implemented(self):
        """staleness check functions are not in current implementation."""
        pytest.skip("staleness checking not implemented in bybit_capital_provider")


class TestBybitCapitalProviderConfig:
    """Test configuration helpers."""

    def test_get_config_existing(self, mock_db):
        """Test reading existing config."""
        from bybit_capital_provider import _get_config
        
        result = _get_config(mock_db, "PREFERRED_ACCOUNT_TYPE", "paper")
        
        assert result == "live"  # From fixture

    def test_get_config_default(self, mock_db):
        """Test default value for missing config."""
        from bybit_capital_provider import _get_config
        
        result = _get_config(mock_db, "NONEXISTENT", "default_value")
        
        assert result == "default_value"


class TestBybitCapitalProviderError:
    """Test error handling."""

    def test_capital_unavailable_error(self):
        """Test CapitalUnavailableError exception."""
        from bybit_capital_provider import CapitalUnavailableError
        
        with pytest.raises(CapitalUnavailableError) as exc_info:
            raise CapitalUnavailableError("Test error message")
        
        assert "Test error message" in str(exc_info.value)
        assert isinstance(exc_info.value, RuntimeError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
