"""
Integration tests: Server API comprehensive coverage.

Tests all major FastAPI endpoints with real database.
Uses TestClient for HTTP-level testing.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.integration
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

# Setup paths
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "server"), os.path.join(_SCRIPTS_DIR, "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def test_env():
    """Setup test environment with temp database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Create minimal config
    config_data = {
        "db_file": db_path,
        "api_key": "test-integration-key",
        "host": "127.0.0.1",
        "port": 8000,
        "excel_file": db_path.replace(".db", ".xlsx")
    }
    
    yield config_data
    
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def api_client(test_env):
    """Create FastAPI test client with mocked dependencies."""
    # Mock the ServerConfig
    with patch("scripts.server.config.ServerConfig") as mock_config_class:
        mock_config = Mock()
        for key, value in test_env.items():
            setattr(mock_config, key, value)
        mock_config_class.return_value = mock_config
        
        # Initialize database
        from scripts.core.sqlite_manager import SQLiteManager
        db = SQLiteManager(test_env["db_file"])
        
        # Seed data
        with db._connect() as con:
            # Settings
            con.execute("INSERT INTO settings (ticker, active, comment, sector, trading_blocked) VALUES (?, ?, ?, ?, ?)",
                       ("BTCUSDT", 1, "BTC test", "crypto", 0))
            
            # Providers
            con.execute("""
                INSERT INTO providers (name, type, base_url, api_key, model, temperature, max_tokens, rate_limit, active, execute)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("openrouter", "ai", "https://api.openrouter.ai", "", "gpt-4", 0.2, 2000, 60, 1, "yes"))
            
            # Method config
            con.execute("INSERT INTO method_config (method, timeframe_hours, trigger, active, execute) VALUES (?, ?, ?, ?, ?)",
                       ("classic", 24, "both", 1, "yes"))
            
            # Risk settings - check if table exists first
            try:
                con.execute("""
                    INSERT INTO risk_settings (id, risk_percent_on_stop, risk_mode, max_position_pct)
                    VALUES (1, 1.0, 'percent_of_capital', 0.2)
                """)
            except sqlite3.OperationalError:
                pass  # Table may not exist with these columns
            
            con.commit()
        
        # Mock startup/shutdown tasks
        with patch("scripts.core.scheduler.start_scheduler", new=AsyncMock()), \
             patch("scripts.core.scheduler.stop_scheduler", new=AsyncMock()), \
             patch("scripts.core.scheduler.run_startup_price_data_backfill", new=AsyncMock()), \
             patch("scripts.core.bybit_worker.start_bybit_worker", new=AsyncMock()), \
             patch("scripts.core.bybit_worker.stop_bybit_worker", new=AsyncMock()), \
             patch("scripts.server.api.ServerConfig") as mock_cfg_class:
            
            # Create mock config
            mock_cfg = Mock()
            mock_cfg.db_file = test_env["db_file"]
            mock_cfg.host = test_env["host"]
            mock_cfg.port = test_env["port"]
            mock_cfg.api_key = test_env["api_key"]
            mock_cfg.excel_file = test_env["excel_file"]
            mock_cfg_class.return_value = mock_cfg
            
            from scripts.server.api import app
            
            with TestClient(app) as client:
                yield client, test_env["api_key"]


class TestAuthentication:
    """Test API authentication."""
    
    def test_health_no_auth(self, api_client):
        """Health check without auth."""
        client, _ = api_client
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_protected_endpoint_no_auth(self, api_client):
        """Protected endpoint without auth fails."""
        client, _ = api_client
        response = client.get("/tickers")
        assert response.status_code == 401
    
    def test_protected_endpoint_with_auth(self, api_client):
        """Protected endpoint with valid auth succeeds."""
        client, api_key = api_client
        response = client.get("/tickers", headers={"X-API-Key": api_key})
        assert response.status_code == 200
    
    def test_protected_endpoint_wrong_auth(self, api_client):
        """Protected endpoint with wrong auth fails."""
        client, _ = api_client
        response = client.get("/tickers", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401


class TestTickersCRUD:
    """Test tickers CRUD operations."""
    
    def test_list_tickers(self, api_client):
        """List all tickers."""
        client, api_key = api_client
        response = client.get("/tickers", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["ticker"] == "BTCUSDT"
    
    def test_create_ticker(self, api_client):
        """Create new ticker."""
        client, api_key = api_client
        
        new_ticker = {
            "ticker": "ETHUSDT",
            "active": True,
            "daily_time": "10:00",
            "intraday_time": "16:00",
            "max_pos_pct": 0.15
        }
        
        response = client.post("/tickers", headers={"X-API-Key": api_key}, json=new_ticker)
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ETHUSDT"
        
        # Verify creation
        response = client.get("/tickers", headers={"X-API-Key": api_key})
        assert len(response.json()["items"]) == 2
    
    def test_update_ticker(self, api_client):
        """Update ticker."""
        client, api_key = api_client
        
        update = {"active": 1, "comment": "Updated BTC"}
        response = client.put("/tickers/BTCUSDT", headers={"X-API-Key": api_key}, json=update)
        assert response.status_code == 200
        
        # Verify update
        response = client.get("/tickers", headers={"X-API-Key": api_key})
        data = response.json()
        btc = next(t for t in data["items"] if t["ticker"] == "BTCUSDT")
        assert btc["comment"] == "Updated BTC"
    
    def test_delete_ticker(self, api_client):
        """Delete ticker."""
        client, api_key = api_client
        
        response = client.delete("/tickers/BTCUSDT", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        
        # Verify deletion
        response = client.get("/tickers", headers={"X-API-Key": api_key})
        assert len(response.json()["items"]) == 0
    
    def test_update_nonexistent_ticker(self, api_client):
        """Update non-existent ticker returns 404."""
        client, api_key = api_client
        
        response = client.put("/tickers/NONEXISTENT", headers={"X-API-Key": api_key}, json={"active": 1, "comment": "test"})
        assert response.status_code == 404


class TestProviders:
    """Test providers endpoints."""
    
    def test_list_providers(self, api_client):
        """List all providers."""
        client, api_key = api_client
        response = client.get("/providers", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
    
    def test_get_provider_detail(self, api_client):
        """Get provider details."""
        client, api_key = api_client
        response = client.get("/providers/openrouter", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "openrouter"
    
    def test_update_provider_execute(self, api_client):
        """Update provider execute flag."""
        client, api_key = api_client
        
        response = client.put(
            "/providers/openrouter/execute",
            headers={"X-API-Key": api_key},
            json={"execute": "no"}
        )
        assert response.status_code == 200
        
        # Verify
        response = client.get("/providers/openrouter", headers={"X-API-Key": api_key})
        assert response.json()["execute"] == "no"
    
    def test_update_provider_invalid_execute(self, api_client):
        """Update provider with invalid execute value fails."""
        client, api_key = api_client
        
        response = client.put(
            "/providers/openrouter/execute",
            headers={"X-API-Key": api_key},
            json={"execute": "invalid"}
        )
        assert response.status_code == 400


class TestMethodConfig:
    """Test method configuration endpoints."""
    
    def test_list_methods(self, api_client):
        """List method configurations."""
        client, api_key = api_client
        response = client.get("/method-config", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
    
    def test_get_method_detail(self, api_client):
        """Get method details."""
        client, api_key = api_client
        response = client.get("/method-config/classic", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "classic"
    
    def test_update_method_execute(self, api_client):
        """Update method execute flag."""
        client, api_key = api_client
        
        response = client.put(
            "/method-config/classic/execute",
            headers={"X-API-Key": api_key},
            json={"execute": "no"}
        )
        assert response.status_code == 200
        
        # Verify
        response = client.get("/method-config/classic", headers={"X-API-Key": api_key})
        assert response.json()["execute"] == "no"


class TestConfigEndpoints:
    """Test configuration endpoints."""
    
    def test_get_config(self, api_client):
        """Get configuration."""
        client, api_key = api_client
        response = client.get("/config", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_update_config(self, api_client):
        """Update configuration."""
        client, api_key = api_client
        
        # Config uses PUT with key in path
        response = client.put(
            "/config/RISK_PERCENT_ON_STOP",
            headers={"X-API-Key": api_key},
            json={"key": "RISK_PERCENT_ON_STOP", "value": "2.0"}
        )
        assert response.status_code == 200


class TestTickets:
    """Test tickets endpoints."""
    
    def test_create_ticket(self, api_client):
        """Create ticket."""
        client, api_key = api_client
        
        ticket = {
            "ticker": "BTCUSDT",
            "action": "BUY",
            "quantity": 0.1,
            "price": 50000,
            "status": "NEW"
        }
        
        response = client.post("/tickets", headers={"X-API-Key": api_key}, json=ticket)
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "BTCUSDT"
        assert "id" in data
    
    def test_list_tickets(self, api_client):
        """List tickets."""
        client, api_key = api_client
        
        # Create a ticket first
        ticket = {"ticker": "BTCUSDT", "action": "BUY"}
        client.post("/tickets", headers={"X-API-Key": api_key}, json=ticket)
        
        response = client.get("/tickets", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
    
    def test_filter_tickets_by_ticker(self, api_client):
        """Filter tickets by ticker."""
        client, api_key = api_client
        
        # Create tickets
        client.post("/tickets", headers={"X-API-Key": api_key}, json={"ticker": "BTCUSDT"})
        client.post("/tickets", headers={"X-API-Key": api_key}, json={"ticker": "ETHUSDT"})
        
        response = client.get("/tickets?ticker=BTCUSDT", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["ticker"] == "BTCUSDT"
    
    def test_update_ticket(self, api_client):
        """Update ticket."""
        client, api_key = api_client
        
        # Create
        create_resp = client.post("/tickets", headers={"X-API-Key": api_key}, json={"ticker": "BTCUSDT"})
        ticket_id = create_resp.json()["id"]
        
        # Update - tickets use PATCH
        response = client.patch(
            f"/tickets/{ticket_id}",
            headers={"X-API-Key": api_key},
            json={"status": "EXECUTED"}
        )
        assert response.status_code == 200
        assert response.json()["updated"] is True
    
    def test_delete_ticket(self, api_client):
        """Delete ticket."""
        client, api_key = api_client
        
        # Create
        create_resp = client.post("/tickets", headers={"X-API-Key": api_key}, json={"ticker": "BTCUSDT"})
        ticket_id = create_resp.json()["id"]
        
        # Delete
        response = client.delete(f"/tickets/{ticket_id}", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        assert response.json()["deleted"] is True


class TestPortfolio:
    """Test portfolio endpoints."""
    
    def test_get_portfolio_empty(self, api_client):
        """Get empty portfolio."""
        client, api_key = api_client
        response = client.get("/portfolio", headers={"X-API-Key": api_key})
        assert response.status_code == 200


class TestAccounts:
    """Test accounts endpoints."""
    
    def test_get_accounts(self, api_client):
        """Get accounts."""
        client, api_key = api_client
        response = client.get("/accounts", headers={"X-API-Key": api_key})
        assert response.status_code == 200


class TestPriceData:
    """Test price data endpoints."""
    
    def test_get_price_data_empty(self, api_client):
        """Get price data when empty."""
        client, api_key = api_client
        response = client.get("/price-data?ticker=BTCUSDT", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


class TestConsensus:
    """Test consensus endpoints."""
    
    def test_get_consensus_empty(self, api_client):
        """Get consensus when empty."""
        client, api_key = api_client
        response = client.get("/consensus", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


class TestForecastRuns:
    """Test forecast runs endpoints."""
    
    def test_get_forecast_runs_empty(self, api_client):
        """Get forecast runs when empty."""
        client, api_key = api_client
        response = client.get("/forecast-runs", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
