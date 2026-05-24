"""
Unit tests for Bybit REST API Client.

Tests are self-contained: no real Bybit connection required.
All API calls are mocked.
"""

import sys
import os
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Mock pybit before importing bybit modules
class FakePybitModule:
    pass

class FakeUnifiedTrading:
    class HTTP:
        last_kwargs = {}

        def __init__(self, *args, **kwargs):
            FakeUnifiedTrading.HTTP.last_kwargs = kwargs

fake_pybit = FakePybitModule()
fake_pybit.unified_trading = FakeUnifiedTrading
sys.modules["pybit"] = fake_pybit
sys.modules["pybit.unified_trading"] = FakeUnifiedTrading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))


class TestBybitClientInit:
    """Test client initialization."""

    def test_init_with_demo_account(self):
        """Test client initializes with demo=True."""
        from bybit_client import BybitClient
        
        client = BybitClient(
            api_key="test_key",
            api_secret="test_secret",
            demo=True
        )
        
        assert client.api_key == "test_key"
        assert client.api_secret == "test_secret"
        assert client.demo is True
        assert hasattr(client, "session")
        assert client.session is not None

    def test_init_with_live_account(self):
        """Test client initializes with demo=False."""
        from bybit_client import BybitClient
        
        client = BybitClient(
            api_key="live_key",
            api_secret="live_secret",
            demo=False,
            recv_window=10000
        )
        
        assert client.demo is False
        assert client.recv_window == 10000
        assert client.session is not None


class TestBybitClientWallet:
    """Test wallet balance methods."""

    def test_get_wallet_balance_success(self):
        """Test successful wallet balance fetch."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "coin": [
                        {
                            "coin": "USDT",
                            "equity": "50000.00",
                            "walletBalance": "48000.00",
                            "availableToWithdraw": "45000.00",
                            "unrealisedPnl": "2000.00",
                            "cumRealisedPnl": "5000.00"
                        }
                    ]
                }]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_wallet_balance.return_value = mock_response
        
        result = client.get_wallet_balance("USDT")
        
        assert result is not None
        assert result["coin"] == "USDT"
        assert result["equity"] == 50000.00
        assert result["wallet_balance"] == 48000.00
        assert result["available_balance"] == 45000.00

    def test_get_wallet_balance_api_error(self):
        """Test handling of API error."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 10001,
            "retMsg": "Invalid coin"
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_wallet_balance.return_value = mock_response
        
        result = client.get_wallet_balance("INVALID")
        
        assert result is None

    def test_get_wallet_balance_empty_list(self):
        """Test when coin list is empty."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"list": []}
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_wallet_balance.return_value = mock_response
        
        result = client.get_wallet_balance("BTC")
        
        assert result is None


class TestBybitClientUnifiedWallet:
    """Test unified wallet summary."""

    def test_get_unified_wallet_success(self):
        from bybit_client import BybitClient

        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "accountType": "UNIFIED",
                    "totalEquity": "184586.77",
                    "totalWalletBalance": "184500.00",
                    "totalAvailableBalance": "180000.00",
                    "totalPerpUPL": "-97.73",
                    "totalMaintenanceMargin": "1200.00",
                    "coin": [
                        {
                            "coin": "USDT",
                            "equity": "53176.92",
                            "walletBalance": "53274.75",
                            "usdValue": "53119.75",
                            "unrealisedPnl": "-57.83",
                            "availableToWithdraw": "50000.00",
                            "bonus": "0",
                        },
                        {
                            "coin": "BTC",
                            "equity": "1.00997405",
                            "walletBalance": "1.00997405",
                            "usdValue": "77273.71",
                            "unrealisedPnl": "0",
                            "availableToWithdraw": "0",
                            "bonus": "0",
                        },
                    ],
                }]
            },
        }

        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_wallet_balance.return_value = mock_response

        result = client.get_unified_wallet()

        assert result is not None
        assert result["account_type"] == "UNIFIED"
        assert result["total_equity"] == 184586.77
        assert result["total_perp_upl"] == -97.73
        assert len(result["coins"]) == 2
        assert result["coins"][0]["coin"] == "BTC"
        assert result["coins"][1]["coin"] == "USDT"
        usdt = next(c for c in result["coins"] if c["coin"] == "USDT")
        assert usdt["usd_value"] == 53119.75


class TestBybitClientPositions:
    """Test position methods."""

    def test_get_positions_success(self):
        """Test fetching positions."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "45000.00",
                        "markPrice": "46000.00",
                        "leverage": "10",
                        "unrealisedPnl": "500.00",
                        "cumRealisedPnl": "200.00",
                        "positionValue": "23000.00",
                        "liqPrice": "40000.00",
                        "takeProfit": "50000.00",
                        "stopLoss": "42000.00"
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "Sell",
                        "size": "2.0",
                        "avgPrice": "3000.00",
                        "markPrice": "2900.00",
                        "leverage": "5",
                        "unrealisedPnl": "-200.00"
                    }
                ]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_positions.return_value = mock_response
        
        positions = client.get_positions()
        
        assert len(positions) == 2
        assert positions[0]["symbol"] == "BTCUSDT"
        assert positions[0]["side"] == "Buy"
        assert positions[0]["size"] == 0.5
        assert positions[0]["entry_price"] == 45000.00
        assert positions[1]["side"] == "Sell"

    def test_get_positions_filter_by_symbol(self):
        """Test filtering positions by symbol."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "1.0"
                }]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_positions.return_value = mock_response
        
        positions = client.get_positions(symbol="BTCUSDT")
        
        assert len(positions) == 1
        client.session.get_positions.assert_called_with(
            category="linear",
            settleCoin="USDT",
            symbol="BTCUSDT"
        )

    def test_get_positions_zero_size_filtered(self):
        """Test that zero-size positions are filtered out."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {"symbol": "BTCUSDT", "size": "0.0"},
                    {"symbol": "ETHUSDT", "size": "1.0"}
                ]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_positions.return_value = mock_response
        
        positions = client.get_positions()
        
        assert len(positions) == 1
        assert positions[0]["symbol"] == "ETHUSDT"

    def test_get_position_single(self):
        """Test get_position for specific symbol."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "size": "0.5"
                }]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_positions.return_value = mock_response
        
        position = client.get_position("BTCUSDT")
        
        assert position is not None
        assert position["symbol"] == "BTCUSDT"

    def test_get_position_not_found(self):
        """Test get_position when no position exists."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {"list": []}
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_positions.return_value = mock_response
        
        position = client.get_position("BTCUSDT")
        
        assert position is None


class TestBybitClientLeverage:
    """Test leverage methods."""

    def test_set_leverage_success(self):
        """Test successful leverage setting."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK"
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.set_leverage.return_value = mock_response
        
        result = client.set_leverage("BTCUSDT", 10)
        
        assert result is True
        client.session.set_leverage.assert_called_with(
            category="linear",
            symbol="BTCUSDT",
            buyLeverage="10",
            sellLeverage="10"
        )

    def test_set_leverage_error(self):
        """Test leverage setting error."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 10001,
            "retMsg": "Invalid leverage"
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.set_leverage.return_value = mock_response
        
        result = client.set_leverage("BTCUSDT", 200)  # Too high
        
        assert result is False

    def test_set_leverage_unchanged_is_success(self):
        """ErrCode 110043 means leverage is already at the requested value."""
        from bybit_client import BybitClient

        mock_response = {
            "retCode": 110043,
            "retMsg": "leverage not modified",
        }

        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.set_leverage.return_value = mock_response

        assert client.set_leverage("SOLUSDT", 3) is True

    def test_set_leverage_unchanged_exception_is_success(self):
        """pybit may raise when retCode != 0."""
        from bybit_client import BybitClient

        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.set_leverage.side_effect = Exception(
            "leverage not modified (ErrCode: 110043)"
        )

        assert client.set_leverage("ETHUSDT", 3) is True


class TestBybitClientKlines:
    """Test klines/candlestick methods."""

    def test_get_klines_success(self):
        """Test successful klines fetch."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    # [timestamp, open, high, low, close, volume, turnover]
                    ["1609459200000", "10000.00", "11000.00", "9000.00", "10500.00", "100.00", "1000000.00"],
                    ["1609462800000", "10500.00", "11500.00", "9500.00", "11000.00", "150.00", "1500000.00"]
                ]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_kline.return_value = mock_response
        
        klines = client.get_klines("BTCUSDT", interval="60", limit=2)
        
        assert len(klines) == 2
        assert "datetime" in klines[0]
        assert "open" in klines[0]
        assert "high" in klines[0]
        assert "low" in klines[0]
        assert "close" in klines[0]
        assert "volume" in klines[0]
        # Bybit returns candles from oldest to newest (reversed)
        assert klines[0]["open"] == 10500.00  # Second candle (reversed)
        assert klines[0]["close"] == 11000.00

    def test_get_klines_api_error(self):
        """Test klines fetch with API error."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 10001,
            "retMsg": "Invalid symbol"
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_kline.return_value = mock_response
        
        klines = client.get_klines("INVALID")
        
        assert klines == []


class TestBybitClientTicker:
    """Test ticker/price methods."""

    def test_get_ticker_success(self):
        """Test successful ticker fetch."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000.00",
                    "bid1Price": "49999.50",
                    "ask1Price": "50000.50",
                    "markPrice": "50000.00",
                    "indexPrice": "49950.00",
                    "volume24h": "10000.00",
                    "turnover24h": "500000000.00"
                }]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_tickers.return_value = mock_response
        
        ticker = client.get_ticker("BTCUSDT")
        
        assert ticker is not None
        assert ticker["symbol"] == "BTCUSDT"
        assert ticker["last_price"] == 50000.00
        assert ticker["bid"] == 49999.50
        assert ticker["ask"] == 50000.50


class TestBybitClientOrders:
    """Test order placement methods."""

    def test_place_order_market(self):
        """Test market order submission."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "order-123",
                "orderLinkId": "link-456"
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.place_order.return_value = mock_response
        
        result = client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Market",
            qty=0.1
        )
        
        assert result is not None
        assert result["order_id"] == "order-123"

    def test_place_order_limit(self):
        """Test limit order submission."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {"orderId": "order-789"}
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.place_order.return_value = mock_response
        
        result = client.place_order(
            symbol="BTCUSDT",
            side="Sell",
            order_type="Limit",
            qty=0.5,
            price=55000.00
        )
        
        assert result is not None

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "order-123"}
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.cancel_order.return_value = mock_response
        
        result = client.cancel_order("BTCUSDT", "order-123")
        
        assert result is True

    def test_get_open_orders(self):
        """Test fetching open orders."""
        from bybit_client import BybitClient
        
        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {"orderId": "order-1", "symbol": "BTCUSDT", "orderStatus": "New"},
                    {"orderId": "order-2", "symbol": "ETHUSDT", "orderStatus": "PartiallyFilled"},
                ]
            }
        }
        
        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_open_orders.return_value = mock_response
        
        orders = client.get_open_orders()

        assert len(orders) == 2
        assert orders[0]["status"] == "New"
        client.session.get_open_orders.assert_called_with(
            category="linear",
            settleCoin="USDT",
        )

    def test_get_open_orders_by_link_id(self):
        """Test lookup by orderLinkId."""
        from bybit_client import BybitClient

        mock_response = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "orderId": "order-1",
                        "orderLinkId": "forecast_abc",
                        "symbol": "SOLUSDT",
                        "orderStatus": "Filled",
                    }
                ]
            },
        }

        client = BybitClient("key", "secret")
        client.session = Mock()
        client.session.get_open_orders.return_value = mock_response

        orders = client.get_open_orders(symbol="SOLUSDT", order_link_id="forecast_abc")

        assert len(orders) == 1
        client.session.get_open_orders.assert_called_with(
            category="linear",
            symbol="SOLUSDT",
            orderLinkId="forecast_abc",
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
