"""
Integration tests: API endpoints + Database.

Tests FastAPI endpoints with real SQLite database (in-memory or temp file).
No external services (Bybit, IB) are called — all external calls are mocked.
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
def mock_config(temp_db_path):
    """Create mocked server config."""
    with patch("scripts.server.config.ServerConfig") as mock_cfg_class:
        mock_cfg = Mock()
        mock_cfg.db_file = temp_db_path
        mock_cfg.host = "127.0.0.1"
        mock_cfg.port = 8000
        mock_cfg.api_key = "test-api-key-12345"
        mock_cfg.excel_file = temp_db_path.replace(".db", ".xlsx")
        mock_cfg_class.return_value = mock_cfg
        yield mock_cfg


@pytest.fixture
def client(temp_db_path, mock_config):
    """Create test client with initialized database."""
    # Initialize database schema
    from scripts.core.sqlite_manager import SQLiteManager
    db = SQLiteManager(temp_db_path)
    
    # Seed minimal data
    with db._connect() as con:
        # Add a ticker setting
        con.execute("""
            INSERT INTO settings (ticker, active, comment, sector, trading_blocked)
            VALUES (?, ?, ?, ?, ?)
        """, ("BTCUSDT", 1, "Test ticker", "crypto", 0))
        
        # Add a provider
        con.execute("""
            INSERT INTO providers (name, type, base_url, api_key, model, temperature, max_tokens, rate_limit, active, execute)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("openrouter", "ai", "https://openrouter.ai", "", "gpt-4", 0.2, 2000, 60, 1, "yes"))
        
        # Add method config
        con.execute("""
            INSERT INTO method_config (method, timeframe_hours, trigger, active, execute)
            VALUES (?, ?, ?, ?, ?)
        """, ("classic", 24, "both", 1, "yes"))
        
        con.commit()
    
    # Mock scheduler and bybit worker startup
    with patch("scripts.core.scheduler.start_scheduler", new=AsyncMock()), \
         patch("scripts.core.scheduler.stop_scheduler", new=AsyncMock()), \
         patch("scripts.core.scheduler.run_startup_price_data_backfill", new=AsyncMock()), \
         patch("scripts.core.bybit_worker.start_bybit_worker", new=AsyncMock()), \
         patch("scripts.core.bybit_worker.stop_bybit_worker", new=AsyncMock()), \
         patch("scripts.server.api.ServerConfig") as mock_cfg_class:
        
        # Create mock config
        mock_cfg = Mock()
        mock_cfg.db_file = temp_db_path
        mock_cfg.host = "127.0.0.1"
        mock_cfg.port = 8000
        mock_cfg.api_key = "test-api-key-12345"
        mock_cfg.excel_file = temp_db_path.replace(".db", ".xlsx")
        mock_cfg_class.return_value = mock_cfg
        
        from scripts.server.api import app
        
        with TestClient(app) as test_client:
            yield test_client


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_no_auth_required(self, client):
        """Health endpoint should not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "db_file" in data
        assert "db_exists" in data


class TestTickersEndpoints:
    """Test tickers API with real database."""
    
    def test_get_tickers_with_auth(self, client):
        """Get tickers with valid API key."""
        response = client.get("/tickers", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["ticker"] == "BTCUSDT"
    
    def test_get_tickers_no_auth(self, client):
        """Get tickers without API key should fail."""
        response = client.get("/tickers")
        assert response.status_code == 401
    
    def test_get_tickers_wrong_auth(self, client):
        """Get tickers with wrong API key should fail."""
        response = client.get("/tickers", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401
    
    def test_create_ticker(self, client):
        """Create new ticker setting."""
        new_ticker = {
            "ticker": "ETHUSDT",
            "active": True,
            "comment": "ETH test",
            "sector": "crypto",
            "trading_blocked": False
        }
        response = client.post(
            "/tickers",
            headers={"X-API-Key": "test-api-key-12345"},
            json=new_ticker
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ETHUSDT"
        
        # Verify it was created
        response = client.get("/tickers", headers={"X-API-Key": "test-api-key-12345"})
        data = response.json()
        assert len(data["items"]) == 2
    
    def test_update_ticker(self, client):
        """Update existing ticker."""
        update = {"active": 1, "comment": "Updated comment"}
        response = client.put(
            "/tickers/BTCUSDT",
            headers={"X-API-Key": "test-api-key-12345"},
            json=update
        )
        assert response.status_code == 200
        
        # Verify update
        response = client.get("/tickers", headers={"X-API-Key": "test-api-key-12345"})
        data = response.json()
        btc = next(t for t in data["items"] if t["ticker"] == "BTCUSDT")
        assert btc["comment"] == "Updated comment"
    
    def test_delete_ticker(self, client):
        """Delete ticker."""
        response = client.delete(
            "/tickers/BTCUSDT",
            headers={"X-API-Key": "test-api-key-12345"}
        )
        assert response.status_code == 200
        
        # Verify deletion
        response = client.get("/tickers", headers={"X-API-Key": "test-api-key-12345"})
        data = response.json()
        assert len(data["items"]) == 0


class TestProvidersEndpoints:
    """Test providers API."""
    
    def test_get_providers(self, client):
        """Get providers list."""
        response = client.get("/providers", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "openrouter"
    
    def test_update_provider_execute(self, client):
        """Update provider execute flag."""
        response = client.put(
            "/providers/openrouter/execute",
            headers={"X-API-Key": "test-api-key-12345"},
            json={"execute": "no"}
        )
        assert response.status_code == 200
        
        # Verify
        response = client.get("/providers/openrouter", headers={"X-API-Key": "test-api-key-12345"})
        data = response.json()
        assert data["execute"] == "no"


class TestMethodConfigEndpoints:
    """Test method configuration endpoints."""
    
    def test_get_method_config(self, client):
        """Get method config list."""
        response = client.get("/method-config", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
    
    def test_update_method_execute(self, client):
        """Update method execute flag."""
        response = client.put(
            "/method-config/classic/execute",
            headers={"X-API-Key": "test-api-key-12345"},
            json={"execute": "no"}
        )
        assert response.status_code == 200
        
        # Verify
        response = client.get("/method-config/classic", headers={"X-API-Key": "test-api-key-12345"})
        data = response.json()
        assert data["execute"] == "no"


class TestLogsEndpoints:
    """Test logs endpoints."""
    
    def test_get_logs_empty(self, client):
        """Get logs when empty."""
        response = client.get("/logs", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
    
    def test_get_logs_with_filters(self, client):
        """Get logs with ticker filter."""
        response = client.get("/logs?ticker=BTCUSDT", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestConsensusEndpoints:
    """Test consensus endpoints."""
    
    def test_get_consensus_empty(self, client):
        """Get consensus when empty."""
        response = client.get("/consensus", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []


class TestOrdersEndpoints:
    """Test orders endpoints."""
    
    def test_get_orders_empty(self, client):
        """Get orders when empty."""
        response = client.get("/orders", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestTicketsEndpoints:
    """Test tickets CRUD operations."""
    
    def test_create_ticket(self, client):
        """Create a ticket."""
        ticket = {
            "ticker": "BTCUSDT",
            "action": "BUY",
            "quantity": 0.1,
            "price": 50000,
            "status": "NEW",
            "portfolio": 1,
            "notes": "Test ticket"
        }
        response = client.post(
            "/tickets",
            headers={"X-API-Key": "test-api-key-12345"},
            json=ticket
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "BTCUSDT"
        assert "id" in data
    
    def test_get_tickets(self, client):
        """Get tickets list."""
        # Create a ticket first
        ticket = {"ticker": "BTCUSDT", "action": "BUY"}
        client.post("/tickets", headers={"X-API-Key": "test-api-key-12345"}, json=ticket)
        
        response = client.get("/tickets", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
    
    def test_update_ticket(self, client):
        """Update ticket status."""
        # Create ticket
        ticket = {"ticker": "BTCUSDT"}
        create_resp = client.post("/tickets", headers={"X-API-Key": "test-api-key-12345"}, json=ticket)
        ticket_id = create_resp.json()["id"]
        
        # Update
        response = client.patch(
            f"/tickets/{ticket_id}",
            headers={"X-API-Key": "test-api-key-12345"},
            json={"status": "EXECUTED"}
        )
        assert response.status_code == 200
        assert response.json()["updated"] is True
    
    def test_delete_ticket(self, client):
        """Delete ticket."""
        # Create ticket
        ticket = {"ticker": "BTCUSDT"}
        create_resp = client.post("/tickets", headers={"X-API-Key": "test-api-key-12345"}, json=ticket)
        ticket_id = create_resp.json()["id"]
        
        # Delete
        response = client.delete(f"/tickets/{ticket_id}", headers={"X-API-Key": "test-api-key-12345"})
        assert response.status_code == 200
        assert response.json()["deleted"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
