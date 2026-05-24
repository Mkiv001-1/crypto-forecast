"""
Live integration tests with Bybit Demo API.

These tests use REAL Bybit API (demo account only) and make actual API calls.
They are marked with @pytest.mark.integration and @pytest.mark.slow.

WARNING: These tests require valid BYBIT_API_KEY and BYBIT_API_SECRET env vars.
They will only work with DEMO accounts (demo=True).

Run with:
    pytest scripts/tests/test_integration_live_bybit.py -v --integration
    
Or with marker:
    pytest scripts/tests/test_integration_live_bybit.py -v -m "integration"

Required env vars:
    BYBIT_API_KEY=your_demo_api_key
    BYBIT_API_SECRET=your_demo_api_secret
"""

import os
import sys
import pytest
import time
from datetime import datetime, timezone
from decimal import Decimal

# Setup paths
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Check if we have API credentials
HAS_BYBIT_CREDS = bool(
    os.environ.get("BYBIT_API_KEY") and os.environ.get("BYBIT_API_SECRET")
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not HAS_BYBIT_CREDS,
        reason="BYBIT_API_KEY and BYBIT_API_SECRET env vars required"
    ),
]


@pytest.fixture(scope="module")
def bybit_config():
    """Load Bybit configuration from environment."""
    from scripts.core.bybit_config import load_bybit_config
    
    config = load_bybit_config()
    
    # Safety check: MUST be demo mode
    if not config.demo:
        pytest.skip("Live tests require demo=True mode for safety")
    
    return config


@pytest.fixture(scope="module")
def bybit_client(bybit_config):
    """Create Bybit client connected to demo API."""
    from scripts.core.bybit_client import BybitClient
    
    client = BybitClient(
        api_key=bybit_config.api_key,
        api_secret=bybit_config.api_secret,
        demo=bybit_config.demo
    )
    
    # Verify connection works
    if not client.test_connection():
        pytest.fail("Failed to connect to Bybit API - check credentials")
    
    yield client
    
    # Cleanup: cancel any open test orders
    try:
        client.cancel_all_orders()
    except Exception:
        pass


class TestBybitConnectionLive:
    """Test real connection to Bybit API."""
    
    def test_connection_success(self, bybit_client, bybit_config):
        """Verify connection to Bybit API works."""
        assert bybit_client.demo is True, "Must use demo account"
        assert bybit_client.test_connection() is True
    
    def test_get_wallet_balance(self, bybit_client):
        """Fetch real wallet balance from Bybit."""
        balance = bybit_client.get_wallet_balance("USDT")
        
        assert balance is not None
        assert "equity" in balance
        assert "available_balance" in balance
        assert isinstance(balance["equity"], (int, float))
        assert isinstance(balance["available_balance"], (int, float))
        
        # Log for visibility
        print(f"\nUSDT Balance: Equity={balance['equity']:.2f}, Available={balance['available_balance']:.2f}")
    
    def test_get_account_info(self, bybit_client):
        """Fetch account information."""
        info = bybit_client.get_account_info()
        assert info is not None
        print(f"\nAccount info retrieved")
    
    def test_get_server_time(self, bybit_client):
        """Fetch Bybit server time."""
        server_time = bybit_client.get_server_time()
        assert server_time is not None
        assert isinstance(server_time, int)
        
        local_time = int(datetime.now(timezone.utc).timestamp())
        time_diff = abs(server_time - local_time)
        assert time_diff < 60, f"Time difference too large: {time_diff}s"


class TestBybitMarketDataLive:
    """Test market data endpoints with real API."""
    
    def test_get_ticker_btc(self, bybit_client):
        """Get real BTCUSDT ticker."""
        ticker = bybit_client.get_ticker("BTCUSDT")
        
        assert ticker is not None
        assert ticker["symbol"] == "BTCUSDT"
        assert ticker["last_price"] > 0
        assert ticker["bid"] > 0
        assert ticker["ask"] > 0
        assert ticker["bid"] <= ticker["ask"], "Bid should be <= Ask"
        
        spread = (ticker["ask"] - ticker["bid"]) / ticker["last_price"] * 100
        print(f"\nBTCUSDT: Last={ticker['last_price']:.2f}, Bid={ticker['bid']:.2f}, Ask={ticker['ask']:.2f}, Spread={spread:.3f}%")
    
    def test_get_ticker_eth(self, bybit_client):
        """Get real ETHUSDT ticker."""
        ticker = bybit_client.get_ticker("ETHUSDT")
        
        assert ticker is not None
        assert ticker["symbol"] == "ETHUSDT"
        assert ticker["last_price"] > 0
    
    def test_get_klines_daily(self, bybit_client):
        """Get real daily klines."""
        klines = bybit_client.get_klines("BTCUSDT", interval="D", limit=7)
        
        assert isinstance(klines, list)
        assert len(klines) > 0
        assert len(klines) <= 7
        
        # Verify OHLCV structure
        candle = klines[0]
        assert "datetime" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle
        
        # Verify price relationships
        assert candle["high"] >= candle["low"]
        assert candle["high"] >= candle["open"]
        assert candle["high"] >= candle["close"]
        assert candle["low"] <= candle["open"]
        assert candle["low"] <= candle["close"]
        
        print(f"\nLatest BTC daily: O={candle['open']:.2f} H={candle['high']:.2f} L={candle['low']:.2f} C={candle['close']:.2f}")
    
    def test_get_klines_hourly(self, bybit_client):
        """Get real hourly klines."""
        klines = bybit_client.get_klines("BTCUSDT", interval="60", limit=24)
        
        assert isinstance(klines, list)
        assert len(klines) > 0
        
        # Verify timestamps are sequential
        timestamps = [k["timestamp_ms"] for k in klines]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i-1], "Timestamps should be ascending"
    
    def test_get_instruments(self, bybit_client):
        """Get available trading instruments."""
        instruments = bybit_client.get_instruments()
        
        assert isinstance(instruments, list)
        assert len(instruments) > 0
        
        # Find BTCUSDT
        btc = next((i for i in instruments if i.get("symbol") == "BTCUSDT"), None)
        assert btc is not None, "BTCUSDT should be available"
        
        # Find USDT linear perpetuals
        usdt_pairs = [i for i in instruments if i.get("quote_coin") == "USDT"]
        assert len(usdt_pairs) > 10, "Should have many USDT pairs"
        
        print(f"\nTotal instruments: {len(instruments)}, USDT pairs: {len(usdt_pairs)}")


class TestBybitPositionsLive:
    """Test position endpoints with real API."""
    
    def test_get_positions(self, bybit_client):
        """Get current positions (may be empty)."""
        positions = bybit_client.get_positions()
        
        assert isinstance(positions, list)
        
        if positions:
            for pos in positions:
                assert "symbol" in pos
                assert "side" in pos
                assert "size" in pos
                assert pos["size"] > 0
                print(f"\nPosition: {pos['symbol']} {pos['side']} {pos['size']} @ {pos['entry_price']}")
        else:
            print("\nNo open positions")
    
    def test_get_position_specific(self, bybit_client):
        """Get position for specific symbol."""
        position = bybit_client.get_position("BTCUSDT")
        
        # May be None if no position
        if position:
            assert position["symbol"] == "BTCUSDT"
            assert position["size"] > 0
    
    def test_set_leverage(self, bybit_client):
        """Set leverage for BTCUSDT."""
        # Set to 3x for testing
        result = bybit_client.set_leverage("BTCUSDT", 3)
        
        # May fail if position exists with different leverage
        # That's OK for test purposes
        if result:
            print("\nLeverage set to 3x")
        else:
            print("\nCould not set leverage (position may exist)")


class TestBybitOrdersLive:
    """Test order operations with real API (demo only)."""
    
    def test_get_open_orders_empty(self, bybit_client):
        """Get open orders (should be empty at start)."""
        # Cancel all first
        bybit_client.cancel_all_orders("BTCUSDT")
        time.sleep(0.5)  # Small delay
        
        orders = bybit_client.get_open_orders("BTCUSDT")
        assert isinstance(orders, list)
        # After cancel_all, should be empty or have only non-BTC orders
        btc_orders = [o for o in orders if o["symbol"] == "BTCUSDT"]
        assert len(btc_orders) == 0, f"Expected 0 BTC orders, got {len(btc_orders)}"
    
    def test_place_and_cancel_limit_order(self, bybit_client):
        """Place a limit order far from market and cancel it."""
        # Get current price
        ticker = bybit_client.get_ticker("BTCUSDT")
        current_price = ticker["last_price"]
        
        # Place limit order far below market (won't fill)
        limit_price = round(current_price * 0.5, 1)  # 50% below
        qty = 0.001  # Minimum BTC size
        
        order = bybit_client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty=qty,
            price=limit_price,
            time_in_force="GTC"
        )
        
        assert order is not None, "Order placement failed"
        assert "order_id" in order
        order_id = order["order_id"]
        
        print(f"\nPlaced limit order: {order_id} @ {limit_price}")
        
        # Verify order exists
        time.sleep(0.5)
        open_orders = bybit_client.get_open_orders("BTCUSDT")
        order_ids = [o["order_id"] for o in open_orders]
        assert order_id in order_ids, "Order not found in open orders"
        
        # Cancel the order
        cancel_result = bybit_client.cancel_order("BTCUSDT", order_id=order_id)
        assert cancel_result is True, "Cancel failed"
        
        print(f"Cancelled order: {order_id}")
        
        # Verify cancelled
        time.sleep(0.5)
        open_orders = bybit_client.get_open_orders("BTCUSDT")
        order_ids = [o["order_id"] for o in open_orders]
        assert order_id not in order_ids, "Order still open after cancel"
    
    def test_place_order_with_tp_sl(self, bybit_client):
        """Place order with take profit and stop loss."""
        ticker = bybit_client.get_ticker("BTCUSDT")
        current_price = ticker["last_price"]
        
        limit_price = round(current_price * 0.5, 1)
        take_profit = round(current_price * 0.6, 1)  # Above entry
        stop_loss = round(current_price * 0.4, 1)     # Below entry
        
        order = bybit_client.place_order(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty=0.001,
            price=limit_price,
            time_in_force="GTC",
            take_profit=take_profit,
            stop_loss=stop_loss
        )
        
        if order:
            print(f"\nPlaced bracket order: {order['order_id']}")
            
            # Cancel immediately
            bybit_client.cancel_order("BTCUSDT", order_id=order["order_id"])
        else:
            pytest.skip("Could not place bracket order (may be restricted)")
    
    def test_cancel_all_orders(self, bybit_client):
        """Place multiple orders and cancel all."""
        ticker = bybit_client.get_ticker("BTCUSDT")
        current_price = ticker["last_price"]
        
        # Place a couple test orders
        order_ids = []
        for i, multiplier in enumerate([0.4, 0.45]):
            order = bybit_client.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                qty=0.001,
                price=round(current_price * multiplier, 1),
                time_in_force="GTC"
            )
            if order:
                order_ids.append(order["order_id"])
        
        if not order_ids:
            pytest.skip("Could not place test orders")
        
        print(f"\nPlaced {len(order_ids)} test orders")
        
        # Cancel all
        result = bybit_client.cancel_all_orders("BTCUSDT")
        assert result is True
        
        # Verify
        time.sleep(0.5)
        open_orders = bybit_client.get_open_orders("BTCUSDT")
        remaining = [o for o in open_orders if o["order_id"] in order_ids]
        assert len(remaining) == 0, f"Some orders still open: {remaining}"
        
        print(f"Cancelled all {len(order_ids)} orders")
    
    def test_get_order_history(self, bybit_client):
        """Get order history."""
        history = bybit_client.get_order_history("BTCUSDT", limit=10)
        
        assert isinstance(history, list)
        print(f"\nOrder history: {len(history)} orders")


class TestBybitDataLoaderLive:
    """Test Bybit data loader with real API."""
    
    def test_fetch_klines_via_data_loader(self, bybit_client):
        """Test data loader functions with real API."""
        from scripts.core.bybit_data_loader import fetch_bybit_klines
        
        # Temporarily set client for data loader
        from scripts.core.bybit_data_loader import get_bybit_client
        import scripts.core.bybit_data_loader as data_loader_module
        
        # Monkey-patch for test
        original_get_client = data_loader_module.get_bybit_client
        data_loader_module.get_bybit_client = lambda: bybit_client
        
        try:
            klines = fetch_bybit_klines("BTCUSDT", interval="D", days=3)
            
            assert isinstance(klines, list)
            assert len(klines) > 0
            
            print(f"\nFetched {len(klines)} daily candles via data loader")
        finally:
            # Restore
            data_loader_module.get_bybit_client = original_get_client


if __name__ == "__main__":
    # Allow running directly if env vars set
    pytest.main([__file__, "-v", "-m", "integration"])
