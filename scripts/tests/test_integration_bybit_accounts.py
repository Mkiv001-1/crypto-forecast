"""
Integration tests for Bybit account synchronization.

Tests the complete flow from API credentials to account data storage.
Uses mocked Bybit API to avoid real network calls.
"""

import sys
import os
import sqlite3
import tempfile
import pytest

pytestmark = pytest.mark.integration

from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

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
sys.modules["pybit.unified_trading"] = fake_pybit.unified_trading

# Setup paths
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _mock_unified_wallet(
    *,
    equity: float = 100000.0,
    available: float = 80000.0,
    perp_upl: float = 2900.0,
) -> dict:
    return {
        "account_type": "UNIFIED",
        "total_equity": equity,
        "total_wallet_balance": equity - 5000.0,
        "total_available_balance": available,
        "total_perp_upl": perp_upl,
        "total_maintenance_margin": 0,
        "coins": [
            {
                "coin": "USDT",
                "equity": equity / 2,
                "wallet_balance": equity / 2,
                "usd_value": equity / 2,
                "unrealised_pnl": perp_upl,
                "available_balance": available,
                "bonus": 0,
            }
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def temp_db():
    """Create a temporary database with required tables."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, description TEXT);
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            broker TEXT,
            account_id TEXT,
            name TEXT,
            account_type TEXT,
            base_currency TEXT,
            buying_power REAL,
            net_liquidation REAL,
            available_funds REAL,
            cash REAL,
            maintenance_margin REAL,
            last_update TEXT,
            type TEXT,
            uid TEXT,
            mode TEXT,
            unrealized_pnl REAL,
            positions_count INTEGER
        );
    """)
    con.execute("INSERT INTO config VALUES ('BYBIT_API_KEY', 'test_key_123', 'Bybit API key')")
    con.execute("INSERT INTO config VALUES ('BYBIT_API_SECRET', 'test_secret_456', 'Bybit API secret')")
    con.execute("INSERT INTO config VALUES ('BYBIT_API_DEMO', 'true', 'Use demo mode')")
    con.commit()
    con.close()
    
    yield path
    
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def mock_bybit_client():
    """Create a mocked Bybit client with realistic responses."""
    client = Mock()
    
    # Mock wallet balance
    client.get_wallet_balance.return_value = {
        "coin": "USDT",
        "equity": 100000.0,
        "wallet_balance": 95000.0,
        "available_balance": 80000.0,
        "unrealised_pnl": 5000.0,
        "cum_realised_pnl": 2000.0
    }
    
    # Mock positions
    client.get_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "size": 0.5,
            "entry_price": 45000.0,
            "mark_price": 50000.0,
            "leverage": 10,
            "unrealised_pnl": 2500.0,
            "realised_pnl": 0,
            "position_value": 25000.0,
            "liq_price": 40000.0
        },
        {
            "symbol": "ETHUSDT",
            "side": "Buy",
            "size": 2.0,
            "entry_price": 3000.0,
            "mark_price": 3200.0,
            "leverage": 5,
            "unrealised_pnl": 400.0,
            "realised_pnl": 0,
            "position_value": 6400.0
        }
    ]
    
    # Mock account info
    client.get_account_info.return_value = {
        "uid": "12345678",
        "username": "test_user"
    }
    
    # Mock test connection
    client.test_connection.return_value = True
    
    # Mock demo flag
    client.demo = True
    
    return client


class TestBybitAccountSyncIntegration:
    """Integration tests for Bybit account synchronization."""
    
    def test_sync_account_data_creates_account(self, temp_db, mock_bybit_client):
        """Test that sync_account_data creates account record."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data
        
        db = SQLiteManager(temp_db)
        
        mock_wallet = _mock_unified_wallet()
        
        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": 0.5,
                "entry_price": 45000.0,
                "mark_price": 50000.0,
                "leverage": 10,
                "unrealised_pnl": 2500.0,
                "position_value": 25000.0,
            }
        ]
        
        # Patch at bybit_account_sync namespace (bound imports)
        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=mock_wallet), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=mock_positions):
            result = sync_account_data(db)
        
        assert result is not None
        assert result["broker"] == "bybit"
        assert result["net_liquidation"] == 100000.0
        assert result["buying_power"] == 80000.0

    async def test_sync_account_data_async_creates_account(self, temp_db, mock_bybit_client):
        """Test that sync_account_data_async creates account record."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data_async

        db = SQLiteManager(temp_db)

        mock_wallet = _mock_unified_wallet()

        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": 0.5,
                "entry_price": 45000.0,
                "mark_price": 50000.0,
                "leverage": 10,
                "unrealised_pnl": 2500.0,
                "position_value": 25000.0,
            }
        ]

        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch(
                 "scripts.core.bybit_account_sync.get_unified_wallet_async",
                 new=AsyncMock(return_value=mock_wallet),
             ), \
             patch(
                 "scripts.core.bybit_account_sync.get_positions",
                 new=AsyncMock(return_value=mock_positions),
             ):
            result = await sync_account_data_async(db)

        assert result is not None
        assert result["broker"] == "bybit"
        assert result["net_liquidation"] == 100000.0
        assert result["buying_power"] == 80000.0
    
    def test_sync_account_data_updates_existing(self, temp_db, mock_bybit_client):
        """Test that sync_account_data updates existing account."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data
        
        db = SQLiteManager(temp_db)
        
        mock_wallet_1 = _mock_unified_wallet(equity=100000.0, available=80000.0)
        mock_wallet_2 = _mock_unified_wallet(equity=150000.0, available=120000.0)
        
        mock_positions = []
        
        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=mock_wallet_1), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=mock_positions):
            result1 = sync_account_data(db)
        
        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=mock_wallet_2), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=mock_positions):
            result2 = sync_account_data(db)
        
        assert result2["net_liquidation"] == 150000.0
        
        with db._connect() as con:
            count = con.execute("SELECT COUNT(*) FROM accounts WHERE broker='bybit'").fetchone()[0]
            assert count == 1
    
    def test_sync_fails_when_worker_not_running(self, temp_db):
        """Test that sync returns None when worker is not running."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data
        
        db = SQLiteManager(temp_db)
        
        # Patch is_running to return False (worker not running)
        import scripts.core.bybit_account_sync as sync_module
        original_is_running = sync_module.is_running
        sync_module.is_running = lambda: False
        
        try:
            result = sync_account_data(db)
            assert result is None
        finally:
            sync_module.is_running = original_is_running
    
    def test_sync_uses_total_perp_upl(self, temp_db, mock_bybit_client):
        """Test that unrealized PnL comes from unified wallet totalPerpUPL."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data
        
        db = SQLiteManager(temp_db)
        
        mock_wallet = _mock_unified_wallet(perp_upl=-97.73)
        
        mock_positions = [
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": 0.5,
                "entry_price": 45000.0,
                "mark_price": 50000.0,
                "unrealised_pnl": 2500.0,
            },
            {
                "symbol": "ETHUSDT",
                "side": "Buy",
                "size": 2.0,
                "entry_price": 3000.0,
                "mark_price": 3200.0,
                "unrealised_pnl": 400.0,
            }
        ]
        
        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=mock_wallet), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=mock_positions):
            result = sync_account_data(db)
        
        assert result["unrealized_pnl"] == -97.73
    
    def test_sync_counts_positions(self, temp_db, mock_bybit_client):
        """Test that positions count is correct."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import sync_account_data
        
        db = SQLiteManager(temp_db)
        
        mock_wallet = _mock_unified_wallet()
        
        mock_positions = [
            {"symbol": "BTCUSDT", "unrealised_pnl": 2500.0},
            {"symbol": "ETHUSDT", "unrealised_pnl": 400.0},
        ]
        
        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client), \
             patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=mock_wallet), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=mock_positions):
            result = sync_account_data(db)
        
        assert result["positions_count"] == 2
    
    def test_get_accounts_summary(self, temp_db):
        """Test getting accounts summary."""
        from scripts.core.sqlite_manager import SQLiteManager
        from scripts.core.bybit_account_sync import get_accounts_summary
        
        with SQLiteManager(temp_db)._connect() as con:
            con.execute("""
                INSERT INTO accounts (broker, account_id, name, net_liquidation, buying_power, available_funds)
                VALUES ('bybit', 'bybit-demo', 'Bybit Demo', 100000, 80000, 80000)
            """)
            con.execute("""
                INSERT INTO accounts (broker, account_id, name, net_liquidation, buying_power, available_funds)  
                VALUES ('bybit', 'bybit-live', 'Bybit Live', 200000, 150000, 150000)
            """)
            con.commit()
        
        db = SQLiteManager(temp_db)
        summary = get_accounts_summary(db)
        
        assert summary["totals"]["count"] == 2
        assert summary["totals"]["total_net_liq"] == 300000
        assert summary["totals"]["total_buying_power"] == 230000
        assert summary["totals"]["total_available"] == 230000


class TestBybitWorkerLifecycle:
    """Test worker lifecycle and connection state."""
    
    def test_worker_not_running_by_default(self):
        """Test that worker is not running before start."""
        from scripts.core.bybit_worker import is_running
        
        assert is_running() is False
    
    def test_bybit_request_fails_when_not_running(self, temp_db):
        """Test that bybit_request raises when worker not running."""
        from scripts.core.bybit_worker import bybit_request_sync
        
        with pytest.raises(RuntimeError, match="not running"):
            bybit_request_sync("get_balance", coin="USDT")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])