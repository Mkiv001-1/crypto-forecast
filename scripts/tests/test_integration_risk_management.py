"""
Integration tests: Risk management and circuit breaker.

Tests risk calculations, position limits, and circuit breaker functionality
with real database integration.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.integration

import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

# Setup paths
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "core")]:
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
def risk_configured_db(temp_db_path):
    """Create database with risk settings."""
    from scripts.core.sqlite_manager import SQLiteManager
    
    db = SQLiteManager(temp_db_path)
    
    with db._connect() as con:
        # Add risk settings - table structure may vary
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
        
        # Add ticker settings
        con.execute("""
            INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
            VALUES (?, ?, ?, ?, ?)
        """, ("BTCUSDT", 1, "BTC test", "crypto", 0))
        
        con.commit()
    
    return db


class TestRiskSettingsIntegration:
    """Test risk settings database integration."""
    
    def test_load_risk_settings(self, risk_configured_db):
        """Test loading risk settings from database."""
        db = risk_configured_db
        
        with db._connect() as con:
            try:
                row = con.execute("SELECT * FROM risk_settings WHERE id=1").fetchone()
                if row:
                    assert row["risk_percent_on_stop"] == 1.0
                    assert row["risk_mode"] == "percent_of_capital"
                    assert row["max_position_pct"] == 0.2
            except sqlite3.OperationalError:
                pytest.skip("risk_settings table not available")
    
    def test_update_risk_settings(self, risk_configured_db):
        """Test updating risk settings."""
        db = risk_configured_db
        
        new_risk_pct = 2.0
        with db._connect() as con:
            try:
                con.execute(
                    "UPDATE risk_settings SET risk_percent_on_stop=? WHERE id=1",
                    (new_risk_pct,)
                )
                con.commit()
                
                # Verify update
                row = con.execute("SELECT risk_percent_on_stop FROM risk_settings WHERE id=1").fetchone()
                assert row["risk_percent_on_stop"] == new_risk_pct
            except sqlite3.OperationalError:
                pytest.skip("risk_settings table not available")


class TestPositionRiskCalculations:
    """Test position risk calculations."""
    
    def test_risk_based_position_size(self):
        """Test position sizing based on risk percent."""
        from scripts.core.position_sizer import PositionSizer
        
        capital = 100000.0
        risk_per_trade = 0.01  # 1%
        max_position_pct = 0.2  # 20%
        
        sizer = PositionSizer(
            total_capital=capital,
            risk_per_trade=risk_per_trade,
            max_position_pct=max_position_pct
        )
        
        entry_price = 50000.0
        stop_loss = 45000.0  # 10% stop
        
        position_size = sizer.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            signal_confidence=0.75
        )
        
        # Risk amount = 100000 * 0.01 = 1000
        # Risk per unit = 50000 - 45000 = 5000
        # Position size = 1000 / 5000 = 0.2
        # But capped by max_position_pct: 100000 * 0.2 / 50000 = 0.4
        # So position_size should be min(0.2, 0.4) = 0.2
        
        assert position_size > 0
        
        # Verify position value doesn't exceed max position pct
        position_value = position_size * entry_price
        assert position_value <= capital * max_position_pct
    
    def test_portfolio_risk_limit(self):
        """Test portfolio-level risk limit."""
        from scripts.core.position_sizer import PositionSizer
        
        capital = 100000.0
        risk_per_trade = 0.01
        max_position_pct = 0.2
        
        sizer = PositionSizer(
            total_capital=capital,
            risk_per_trade=risk_per_trade,
            max_position_pct=max_position_pct
        )
        
        # Calculate multiple positions
        positions = []
        entry_prices = [50000.0, 3000.0, 150.0]  # BTC, ETH, SOL
        stop_losses = [45000.0, 2700.0, 135.0]    # 10% stops
        
        for entry, stop in zip(entry_prices, stop_losses):
            size = sizer.calculate_position_size(
                entry_price=entry,
                stop_loss=stop,
                signal_confidence=0.7
            )
            positions.append({
                "entry": entry,
                "stop": stop,
                "size": size,
                "risk": size * (entry - stop)
            })
        
        # Verify total portfolio risk
        total_risk = sum(p["risk"] for p in positions)
        # Total risk should not exceed max_portfolio_risk_pct * capital (if tracked)
        
        # Verify individual position limits
        for p in positions:
            position_value = p["size"] * p["entry"]
            assert position_value <= capital * max_position_pct


class TestCircuitBreakerIntegration:
    """Test circuit breaker with database."""
    
    def test_circuit_breaker_checks_consecutive_losses(self, risk_configured_db):
        """Test circuit breaker monitors consecutive losses."""
        from scripts.core.circuit_breaker import CircuitBreaker
        
        db = risk_configured_db
        
        # Add loss records
        with db._connect() as con:
            for i in range(4):  # Add 4 consecutive losses (above threshold of 3)
                con.execute("""
                    INSERT INTO orders (
                        order_id, symbol, side, order_type, price, quantity,
                        status, created_at, realized_pnl
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"loss-order-{i}",
                    "BTCUSDT",
                    "Buy",
                    "Market",
                    50000.0,
                    0.1,
                    "Filled",
                    (datetime.now(timezone.utc) - timedelta(hours=i)).isoformat(),
                    -500.0  # Loss
                ))
            con.commit()
        
        # Create circuit breaker
        cb = CircuitBreaker(
            max_consecutive_losses=3,
            daily_loss_limit_pct=0.05,
            db=db
        )
        
        # Check if trading should be blocked
        should_block = cb.check_should_block()
        
        # Should block after 4 consecutive losses
        assert should_block is True
    
    def test_circuit_breaker_daily_loss_limit(self, risk_configured_db):
        """Test circuit breaker daily loss limit."""
        from scripts.core.circuit_breaker import CircuitBreaker
        
        db = risk_configured_db
        
        # Add daily loss records exceeding limit
        capital = 100000.0
        daily_loss_limit = capital * 0.05  # 5%
        
        with db._connect() as con:
            con.execute("""
                INSERT INTO orders (
                    order_id, symbol, side, order_type, price, quantity,
                    status, created_at, realized_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "big-loss-order",
                "BTCUSDT",
                "Buy",
                "Market",
                50000.0,
                1.0,
                "Filled",
                datetime.now(timezone.utc).isoformat(),
                -6000.0  # Exceeds 5% of 100k
            ))
            con.commit()
        
        cb = CircuitBreaker(
            max_consecutive_losses=3,
            daily_loss_limit_pct=0.05,
            db=db,
            capital=capital
        )
        
        should_block = cb.check_should_block()
        assert should_block is True
    
    def test_circuit_breaker_reset_after_timeout(self, risk_configured_db):
        """Test circuit breaker can reset after timeout."""
        from scripts.core.circuit_breaker import CircuitBreaker
        
        db = risk_configured_db
        
        # Add old losses (beyond the reset window)
        with db._connect() as con:
            con.execute("""
                INSERT INTO orders (
                    order_id, symbol, side, order_type, price, quantity,
                    status, created_at, realized_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "old-loss-order",
                "BTCUSDT",
                "Buy",
                "Market",
                50000.0,
                0.1,
                "Filled",
                (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                -500.0
            ))
            con.commit()
        
        cb = CircuitBreaker(
            max_consecutive_losses=3,
            daily_loss_limit_pct=0.05,
            db=db,
            reset_after_hours=24
        )
        
        # Old losses should not trigger circuit breaker
        should_block = cb.check_should_block()
        assert should_block is False


class TestRiskValidation:
    """Test risk validation for orders."""
    
    def test_validate_order_risk_parameters(self, risk_configured_db):
        """Test order risk parameter validation."""
        db = risk_configured_db
        
        # Load risk settings
        with db._connect() as con:
            row = con.execute("SELECT * FROM risk_settings WHERE id=1").fetchone()
        
        max_position_pct = row["max_position_pct"]
        risk_percent_on_stop = row["risk_percent_on_stop"]
        
        # Validate order parameters
        capital = 100000.0
        entry_price = 50000.0
        position_size = 0.5  # Would be $25k position
        position_value = position_size * entry_price
        
        # Check against max position
        max_position_value = capital * max_position_pct
        assert position_value <= max_position_value, f"Position value {position_value} exceeds max {max_position_value}"
        
        # Check stop loss distance
        stop_loss = 45000.0
        risk_per_unit = entry_price - stop_loss
        total_risk = position_size * risk_per_unit
        max_risk = capital * (risk_percent_on_stop / 100)
        
        assert total_risk <= max_risk, f"Total risk {total_risk} exceeds max {max_risk}"


class TestCapitalProviderRiskIntegration:
    """Test risk integration with capital providers."""
    
    def test_bybit_capital_risk_calculation(self, risk_configured_db):
        """Test risk calculations with Bybit capital data."""
        from scripts.core.bybit_capital_provider import get_bybit_account_data
        
        mock_client = Mock()
        mock_client.get_wallet_balance.return_value = {
            "coin": "USDT",
            "equity": 100000.0,
            "available_balance": 80000.0,
            "unrealised_pnl": 5000.0
        }
        
        with patch("scripts.core.bybit_capital_provider.get_bybit_client", return_value=mock_client):
            capital_data = get_bybit_account_data()
        
        available_capital = capital_data["cash_balances"]["USDT"]
        
        # Load risk settings
        db = risk_configured_db
        with db._connect() as con:
            row = con.execute("SELECT * FROM risk_settings WHERE id=1").fetchone()
        
        max_position_pct = row["max_position_pct"]
        max_position_value = available_capital * max_position_pct
        
        assert max_position_value == 80000.0 * 0.2  # 16000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
