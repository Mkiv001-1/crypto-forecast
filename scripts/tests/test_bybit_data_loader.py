"""
Unit tests for Bybit Data Loader.

Tests are self-contained: no real Bybit connection required.
"""

import sys
import os
import pytest
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


class TestBybitDataLoaderKlines:
    """Test klines/candlestick data loading."""

    def test_fetch_bybit_klines_success(self):
        """Test successful klines fetch."""
        from bybit_data_loader import fetch_bybit_klines
        
        mock_klines = [
            {
                "datetime": "2024-01-01 12:00:00",
                "timestamp_ms": 1704110400000,
                "open": 42000.0,
                "high": 42500.0,
                "low": 41800.0,
                "close": 42200.0,
                "volume": 100.5,
                "turnover": 4230000.0
            },
            {
                "datetime": "2024-01-01 13:00:00",
                "timestamp_ms": 1704114000000,
                "open": 42200.0,
                "high": 43000.0,
                "low": 42100.0,
                "close": 42800.0,
                "volume": 150.0,
                "turnover": 6420000.0
            }
        ]
        
        mock_client = Mock()
        mock_client.get_klines.return_value = mock_klines
        
        with patch("bybit_data_loader.get_bybit_client", return_value=mock_client):
            result = fetch_bybit_klines("BTCUSDT", interval="60", days=1)
        
        assert isinstance(result, list)
        assert len(result) == 2
        # Result is in OHLCV format with date field
        assert result[0]["date"] == "2024-01-01 12:00:00"
        assert result[0]["open"] == 42000.0
        assert result[0]["close"] == 42200.0

    def test_fetch_bybit_klines_no_client(self):
        """Test handling when client is not available."""
        from bybit_data_loader import fetch_bybit_klines
        
        with patch("bybit_data_loader.get_bybit_client", return_value=None):
            result = fetch_bybit_klines("BTCUSDT")
        
        assert result == []

    def test_fetch_bybit_klines_empty_response(self):
        """Test handling of empty API response."""
        from bybit_data_loader import fetch_bybit_klines
        
        mock_client = Mock()
        mock_client.get_klines.return_value = []
        
        with patch("bybit_data_loader.get_bybit_client", return_value=mock_client):
            result = fetch_bybit_klines("BTCUSDT")
        
        assert result == []

    def test_fetch_bybit_klines_interval_mapping(self):
        """Test interval string mapping."""
        from bybit_data_loader import INTERVAL_MAP
        
        assert INTERVAL_MAP["1h"] == "60"
        assert INTERVAL_MAP["1d"] == "D"
        assert INTERVAL_MAP["daily"] == "D"
        assert INTERVAL_MAP["1w"] == "W"
        assert INTERVAL_MAP["1m"] == "1"


class TestBybitDataLoaderDaily:
    """Test daily data loading."""

    def test_fetch_bybit_daily(self):
        """Test fetching daily data."""
        from bybit_data_loader import fetch_bybit_daily
        
        mock_klines = [
            {
                "datetime": "2024-01-01",
                "timestamp_ms": 1704067200000,
                "open": 42000.0,
                "high": 43000.0,
                "low": 41000.0,
                "close": 42500.0,
                "volume": 1000.0
            }
        ]
        
        mock_client = Mock()
        mock_client.get_klines.return_value = mock_klines
        
        with patch("bybit_data_loader.get_bybit_client", return_value=mock_client):
            result = fetch_bybit_daily("BTCUSDT", days=30)
        
        assert isinstance(result, list)
        mock_client.get_klines.assert_called_once()


class TestBybitDataLoaderIntraday:
    """Test intraday data loading."""

    def test_fetch_bybit_intraday(self):
        """Test fetching intraday data."""
        from bybit_data_loader import fetch_bybit_intraday
        
        mock_klines = [
            {
                "datetime": "2024-01-01 12:00:00",
                "timestamp_ms": 1704110400000,
                "open": 42000.0,
                "high": 42500.0,
                "low": 41800.0,
                "close": 42200.0,
                "volume": 100.5
            }
        ]
        
        mock_client = Mock()
        mock_client.get_klines.return_value = mock_klines
        
        with patch("bybit_data_loader.get_bybit_client", return_value=mock_client):
            result = fetch_bybit_intraday("BTCUSDT", interval="60", days=7)
        
        assert isinstance(result, list)


class TestBybitDataLoaderConvert:
    """Test data conversion functions."""

    def test_convert_bybit_to_ohlcv(self):
        """Test converting Bybit format to OHLCV."""
        from bybit_data_loader import convert_bybit_to_ohlcv
        
        bybit_klines = [
            {
                "datetime": "2024-01-01 12:00:00",
                "open": 42000.0,
                "high": 43000.0,
                "low": 41000.0,
                "close": 42500.0,
                "volume": 1000.0,
                "turnover": 42000000.0
            }
        ]
        
        result = convert_bybit_to_ohlcv(bybit_klines)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["date"] == "2024-01-01 12:00:00"
        assert result[0]["open"] == 42000.0
        assert result[0]["high"] == 43000.0
        assert result[0]["low"] == 41000.0
        assert result[0]["close"] == 42500.0
        assert result[0]["volume"] == 1000.0


class TestBybitDataLoaderTicker:
    """Test ticker info functions."""

    def test_get_bybit_ticker_info_success(self):
        """Test getting ticker info."""
        from bybit_data_loader import get_bybit_ticker_info
        
        mock_ticker = {
            "symbol": "BTCUSDT",
            "last_price": 50000.00,
            "bid": 49999.50,
            "ask": 50000.50,
            "volume_24h": 10000.00
        }
        
        mock_client = Mock()
        mock_client.get_ticker.return_value = mock_ticker
        
        with patch("bybit_data_loader.get_bybit_client", return_value=mock_client):
            result = get_bybit_ticker_info("BTCUSDT")
        
        assert result is not None
        assert result["symbol"] == "BTCUSDT"

    def test_get_bybit_ticker_info_no_client(self):
        """Test getting ticker info when client unavailable."""
        from bybit_data_loader import get_bybit_ticker_info
        
        with patch("bybit_data_loader.get_bybit_client", return_value=None):
            result = get_bybit_ticker_info("BTCUSDT")
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
