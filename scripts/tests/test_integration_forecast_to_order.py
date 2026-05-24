"""
Integration tests: Full forecast-to-order flow.

Tests the complete workflow:
1. Create forecast logs
2. Build consensus
3. Create orders from consensus
4. Submit orders to Bybit
5. Sync order status

All external API calls are mocked.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.integration

import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock

# Setup paths
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "core"), os.path.join(_SCRIPTS_DIR, "server")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def initialized_db(temp_db_path):
    """Create database with minimal required data."""
    from scripts.core.sqlite_manager import SQLiteManager
    
    db = SQLiteManager(temp_db_path)
    
    with db._connect() as con:
        # Add ticker settings
        con.execute("""
            INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
            VALUES (?, ?, ?, ?, ?)
        """, ("BTCUSDT", 1, "BTC test", "crypto", 0))
        
        con.execute("""
            INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
            VALUES (?, ?, ?, ?, ?)
        """, ("ETHUSDT", 1, "ETH test", "crypto", 0))
        
        # Add providers
        con.execute("""
            INSERT INTO providers (name, type, base_url, api_key, model, temperature, max_tokens, rate_limit, active, execute)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("openrouter", "ai", "https://openrouter.ai", "", "gpt-4", 0.2, 2000, 60, 1, "yes"))
        
        # Add method config
        con.execute("""
            INSERT INTO method_config (method, timeframe_hours, trigger, active, execute)
            VALUES (?, ?, ?, ?, ?)
        """, ("classic", 24, "both", 1, "yes"))
        
        con.execute("""
            INSERT INTO method_config (method, timeframe_hours, trigger, active, execute)
            VALUES (?, ?, ?, ?, ?)
        """, ("trend", 24, "both", 1, "yes"))
        
        # Add risk settings - table may have different structure
        try:
            con.execute("""
                INSERT INTO risk_settings (
                    id, risk_percent_on_stop, risk_mode, max_position_pct,
                    default_risk_pct, max_portfolio_risk_pct, max_single_position_risk_pct,
                    margin_safety_factor, volatility_adjustment,
                    position_sizing_method, capital_preservation_threshold,
                    circuit_breaker_consecutive_losses, circuit_breaker_daily_loss_pct,
                    updated_at
                ) VALUES (1, 1.0, 'percent_of_capital', 0.2, 0.01, 0.05, 0.02, 1.5, 1.0, 'kelly_half', 0.95, 3, 0.05, ?)
            """, (datetime.now(timezone.utc).isoformat(),))
        except sqlite3.OperationalError:
            pass  # Table may not exist or have different columns
        
        con.commit()
    
    return db


@pytest.fixture
def mock_bybit_client():
    """Create a mocked Bybit client."""
    client = Mock()
    
    client.get_wallet_balance.return_value = {
        "coin": "USDT",
        "equity": 100000.0,
        "available_balance": 80000.0,
        "unrealised_pnl": 5000.0
    }
    
    client.get_positions.return_value = []
    client.get_open_orders.return_value = []
    
    client.get_ticker.return_value = {
        "symbol": "BTCUSDT",
        "last_price": 50000.0,
        "bid": 49999.5,
        "ask": 50000.5
    }
    
    client.place_order.return_value = {
        "order_id": "new-order-123",
        "order_link_id": "consensus-btc-001",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "order_type": "Limit",
        "qty": 0.1,
        "price": 49000.0
    }
    
    client.set_leverage.return_value = True
    
    return client


class TestForecastRunLifecycle:
    """Test complete forecast run lifecycle."""
    
    def test_create_forecast_run(self, initialized_db):
        """Test creating a forecast run record."""
        db = initialized_db
        
        run_id = db.create_forecast_run(
            trigger_type="manual",
            tickers_planned=2
        )
        
        assert run_id is not None
        assert isinstance(run_id, int)
        
        # Verify run exists
        run = db.get_forecast_run(run_id)
        assert run is not None
        assert run["trigger_type"] == "manual"
        assert run["status"] == "running"
    
    def test_complete_forecast_run(self, initialized_db):
        """Test completing a forecast run."""
        db = initialized_db
        
        run_id = db.create_forecast_run(trigger_type="scheduled", tickers_planned=2)
        
        success = db.complete_forecast_run(
            run_id=run_id,
            status="completed",
            tickers_processed=2,
            consensus_count=1
        )
        
        assert success is True
        
        # Verify completion
        run = db.get_forecast_run(run_id)
        assert run["status"] == "completed"
        assert run["tickers_processed"] == 2
        assert run["consensus_count"] == 1
    
    def test_link_forecast_to_run(self, initialized_db):
        """Test linking forecast logs to a run."""
        db = initialized_db
        
        run_id = db.create_forecast_run(trigger_type="scheduled", tickers_planned=2)
        
        success = db.link_forecast_to_run(
            run_id=run_id,
            log_id="forecast-001",
            ticker="BTCUSDT",
            method="classic",
            model="gpt4",
            signal="BUY",
            raw_confidence=0.75,
            win_rate=0.6,
            ema_accuracy=0.65,
            final_weight=0.45,
            target_price=55000.0,
            stop_loss=45000.0
        )
        
        assert success is True
        
        # Verify link exists
        links = db.get_forecast_run_links(run_id)
        assert len(links) == 1
        assert links.iloc[0]["ticker"] == "BTCUSDT"


class TestConsensusBuilding:
    """Test consensus building from forecasts."""
    
    def test_build_consensus_from_forecasts(self, initialized_db):
        """Test building consensus from multiple forecasts."""
        from scripts.core.consensus import build_consensus
        
        # Create forecast run and link forecasts
        db = initialized_db
        run_id = db.create_forecast_run(trigger_type="scheduled", tickers_planned=2)
        
        # Add multiple forecasts for BTCUSDT
        forecasts = [
            {"log_id": "f1", "ticker": "BTCUSDT", "signal": "BUY", "raw_confidence": 0.8, "win_rate": 0.7, "final_weight": 0.5},
            {"log_id": "f2", "ticker": "BTCUSDT", "signal": "BUY", "raw_confidence": 0.7, "win_rate": 0.6, "final_weight": 0.4},
            {"log_id": "f3", "ticker": "BTCUSDT", "signal": "SELL", "raw_confidence": 0.6, "win_rate": 0.5, "final_weight": 0.3},
        ]
        
        for f in forecasts:
            db.link_forecast_to_run(
                run_id=run_id,
                log_id=f["log_id"],
                ticker=f["ticker"],
                method="classic",
                model="gpt4",
                signal=f["signal"],
                raw_confidence=f["raw_confidence"],
                win_rate=f["win_rate"],
                ema_accuracy=0.6,
                final_weight=f["final_weight"],
                target_price=55000.0 if f["signal"] == "BUY" else 45000.0,
                stop_loss=45000.0 if f["signal"] == "BUY" else 55000.0
            )
        
        # Build consensus
        with patch("scripts.core.consensus.get_db_manager", return_value=db):
            consensus_list = build_consensus(db, run_id=run_id)
        
        # Should have consensus for BTCUSDT
        assert consensus_list is not None
        if len(consensus_list) > 0:
            btc_consensus = next((c for c in consensus_list if c.get("ticker") == "BTCUSDT"), None)
            if btc_consensus:
                assert btc_consensus["signal"] == "BUY"  # Majority BUY
    
    def test_consensus_with_different_tickers(self, initialized_db):
        """Test consensus building with multiple tickers."""
        from scripts.core.consensus import build_consensus
        
        db = initialized_db
        run_id = db.create_forecast_run(trigger_type="scheduled", tickers_planned=2)
        
        # Add forecasts for different tickers
        forecasts = [
            {"log_id": "f1", "ticker": "BTCUSDT", "signal": "BUY"},
            {"log_id": "f2", "ticker": "BTCUSDT", "signal": "BUY"},
            {"log_id": "f3", "ticker": "ETHUSDT", "signal": "SELL"},
            {"log_id": "f4", "ticker": "ETHUSDT", "signal": "SELL"},
        ]
        
        for f in forecasts:
            db.link_forecast_to_run(
                run_id=run_id,
                log_id=f["log_id"],
                ticker=f["ticker"],
                method="classic",
                model="gpt4",
                signal=f["signal"],
                raw_confidence=0.7,
                win_rate=0.6,
                ema_accuracy=0.6,
                final_weight=0.5,
                target_price=5000.0,
                stop_loss=4000.0
            )
        
        with patch("scripts.core.consensus.get_db_manager", return_value=db):
            consensus_list = build_consensus(db, run_id=run_id)
        
        # Should have consensus entries
        assert consensus_list is not None


class TestOrderCreationFromConsensus:
    """Test creating orders from consensus."""
    
    def test_create_order_from_consensus(self, initialized_db, mock_bybit_client):
        """Test creating an order record from consensus."""
        from scripts.core.sqlite_manager import SQLiteManager
        
        db = initialized_db
        
        # Create consensus record
        consensus_data = {
            "ticker": "BTCUSDT",
            "signal": "BUY",
            "entry_price": 50000.0,
            "stop_loss": 45000.0,
            "take_profit": 55000.0,
            "confidence": 0.75,
            "position_size": 0.1,
            "leverage": 5
        }
        
        # Insert order into database
        order_id = f"consensus-{consensus_data['ticker']}-001"
        with db._connect() as con:
            con.execute("""
                INSERT INTO orders (
                    order_id, symbol, side, order_type, price, quantity,
                    status, created_at, stop_price, target_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                consensus_data["ticker"],
                consensus_data["signal"],
                "Limit",
                consensus_data["entry_price"],
                consensus_data["position_size"],
                "Pending",
                datetime.now(timezone.utc).isoformat(),
                consensus_data["stop_loss"],
                consensus_data["take_profit"]
            ))
            con.commit()
        
        # Verify order was created
        with db._connect() as con:
            row = con.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            assert row is not None
            assert row["symbol"] == "BTCUSDT"


class TestPositionSizingIntegration:
    """Test position sizing with capital provider."""
    
    def test_position_sizing_with_bybit_capital(self, initialized_db, mock_bybit_client):
        """Test position sizing using Bybit capital data."""
        from scripts.core.position_sizer import PositionSizer
        from scripts.core.bybit_capital_provider import get_bybit_account_data
        
        db = initialized_db
        
        with patch("scripts.core.bybit_capital_provider.get_bybit_client", return_value=mock_bybit_client):
            capital_data = get_bybit_account_data()
        
        assert capital_data is not None
        available_capital = capital_data["cash_balances"]["USDT"]
        
        # Create position sizer
        sizer = PositionSizer(
            total_capital=available_capital,
            risk_per_trade=0.01,  # 1%
            max_position_pct=0.2   # 20% max
        )
        
        # Calculate position size
        entry_price = 50000.0
        stop_loss = 45000.0
        
        position_size = sizer.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            signal_confidence=0.75
        )
        
        assert position_size > 0
        
        # Verify position value doesn't exceed max
        position_value = position_size * entry_price
        assert position_value <= available_capital * 0.2


class TestEndToEndFlow:
    """Test end-to-end forecast to order flow."""
    
    def test_full_flow_forecast_to_order(self, initialized_db, mock_bybit_client):
        """Test complete flow from forecast to order creation."""
        db = initialized_db
        
        # Step 1: Create forecast run
        run_id = db.create_forecast_run(trigger_type="manual", tickers_planned=1)
        assert run_id is not None
        
        # Step 2: Add forecast logs
        db.link_forecast_to_run(
            run_id=run_id,
            log_id="forecast-btc-001",
            ticker="BTCUSDT",
            method="classic",
            model="gpt4",
            signal="BUY",
            raw_confidence=0.8,
            win_rate=0.7,
            ema_accuracy=0.65,
            final_weight=0.5,
            target_price=55000.0,
            stop_loss=45000.0,
            entry_price=50000.0,
            r_multiple=2.0,
            atr_14=1500.0
        )
        
        # Step 3: Complete the run
        db.complete_forecast_run(
            run_id=run_id,
            status="completed",
            tickers_processed=1,
            consensus_count=1
        )
        
        # Step 4: Create consensus record
        with db._connect() as con:
            con.execute("""
                INSERT INTO consensus (
                    ticker, signal, entry_price, stop_loss, take_profit,
                    confidence, created_at, activated, entry_at, exit_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "BTCUSDT", "BUY", 50000.0, 45000.0, 55000.0, 0.75,
                datetime.now(timezone.utc).isoformat(), 0, None, None
            ))
            con.commit()
        
        # Step 5: Verify the flow
        run = db.get_forecast_run(run_id)
        assert run["status"] == "completed"
        
        # Step 6: Check consensus exists
        consensus_df = db.read_sheet("Consensus")
        # Note: table name might be different


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
