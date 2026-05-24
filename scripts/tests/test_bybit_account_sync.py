"""
Unit tests for Bybit account sync and worker deadlock regression.

Runs in default pytest (no integration marker): no real Bybit network calls.
"""

import asyncio
import concurrent.futures
import os
import sqlite3
import sys
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

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

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TEST_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
for _p in [_PROJECT_ROOT, _SCRIPTS_DIR, os.path.join(_SCRIPTS_DIR, "core")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


MOCK_UNIFIED_WALLET = {
    "account_type": "UNIFIED",
    "total_equity": 100000.0,
    "total_wallet_balance": 95000.0,
    "total_available_balance": 80000.0,
    "total_perp_upl": 2900.0,
    "total_maintenance_margin": 0,
    "coins": [
        {
            "coin": "USDT",
            "equity": 50000.0,
            "wallet_balance": 48000.0,
            "usd_value": 50000.0,
            "unrealised_pnl": 2000.0,
            "available_balance": 80000.0,
            "bonus": 0,
        }
    ],
    "timestamp": "2026-05-24T10:00:00+00:00",
}

MOCK_BALANCE = {
    "coin": "USDT",
    "equity": 100000.0,
    "wallet_balance": 95000.0,
    "available_balance": 80000.0,
    "unrealised_pnl": 5000.0,
}

MOCK_POSITIONS = [
    {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": 0.5,
        "unrealised_pnl": 2500.0,
    },
    {
        "symbol": "ETHUSDT",
        "side": "Buy",
        "size": 2.0,
        "unrealised_pnl": 400.0,
    },
]


@pytest.fixture
def temp_db():
    """Temporary database with config and accounts tables."""
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
    except OSError:
        pass


@pytest.fixture
def db_manager(temp_db):
    from scripts.core.sqlite_manager import SQLiteManager

    return SQLiteManager(temp_db)


@pytest.fixture
def mock_bybit_client():
    client = Mock()
    client.get_wallet_balance.return_value = MOCK_BALANCE
    client.get_positions.return_value = MOCK_POSITIONS
    client.get_account_info.return_value = {"uid": "12345678", "username": "test_user"}
    client.test_connection.return_value = True
    client.demo = True
    return client


@pytest.fixture
def reset_worker_state():
    import scripts.core.bybit_worker as worker

    saved = {
        "running": worker._state.running,
        "loop": worker._state.loop,
        "task": worker._state.task,
        "queue": worker._state.queue,
        "db_manager": worker._state.db_manager,
        "mock_handler": worker._state._mock_handler,
        "last_account_sync": worker._state._last_account_sync,
        "account_sync_task": worker._state._account_sync_task,
    }
    yield worker
    worker._state.running = saved["running"]
    worker._state.loop = saved["loop"]
    worker._state.task = saved["task"]
    worker._state.queue = saved["queue"]
    worker._state.db_manager = saved["db_manager"]
    worker._state._mock_handler = saved["mock_handler"]
    worker._state._last_account_sync = saved["last_account_sync"]
    worker._state._account_sync_task = saved["account_sync_task"]
    worker.set_mock_handler(None)


class TestPersistAccountData:
    def test_persist_account_data_inserts_account(self, db_manager, mock_bybit_client):
        from scripts.core.bybit_account_sync import _persist_account_data

        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client):
            result = _persist_account_data(db_manager, MOCK_UNIFIED_WALLET, MOCK_POSITIONS[:1])

        assert result is not None
        assert result["broker"] == "bybit"
        assert result["account_id"] == "bybit-demo"
        assert result["net_liquidation"] == 100000.0

        with db_manager._connect() as con:
            row = con.execute(
                "SELECT account_id, net_liquidation FROM accounts WHERE broker='bybit'"
            ).fetchone()
        assert row is not None
        assert row[0] == "bybit-demo"
        assert row[1] == 100000.0

    def test_persist_account_data_uses_total_perp_upl(self, db_manager, mock_bybit_client):
        from scripts.core.bybit_account_sync import _persist_account_data

        with patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client):
            result = _persist_account_data(db_manager, MOCK_UNIFIED_WALLET, MOCK_POSITIONS)

        assert result["unrealized_pnl"] == 2900.0
        assert result["positions_count"] == 2


class TestSyncAccountDataAsync:
    async def test_async_path_uses_async_fetch_not_sync(self, db_manager):
        from scripts.core.bybit_account_sync import sync_account_data_async

        with patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch(
                 "scripts.core.bybit_account_sync.get_unified_wallet_async",
                 new_callable=AsyncMock,
                 return_value=MOCK_UNIFIED_WALLET,
             ), \
             patch(
                 "scripts.core.bybit_account_sync.get_positions",
                 new_callable=AsyncMock,
                 return_value=MOCK_POSITIONS[:1],
             ), \
             patch(
                 "scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking",
                 side_effect=AssertionError("must not use sync from async path"),
             ), \
             patch(
                 "scripts.core.bybit_account_sync.get_positions_sync",
                 side_effect=AssertionError("must not use sync from async path"),
             ), \
             patch("scripts.core.bybit_client.get_bybit_client") as mock_client:
            mock_client.return_value = Mock(
                demo=True,
                get_account_info=Mock(return_value={"uid": "99"}),
            )
            result = await sync_account_data_async(db_manager)

        assert result is not None
        assert result["net_liquidation"] == 100000.0

    async def test_async_returns_none_when_worker_not_running(self, db_manager):
        from scripts.core.bybit_account_sync import sync_account_data_async

        with patch("scripts.core.bybit_account_sync.is_running", return_value=False):
            result = await sync_account_data_async(db_manager)

        assert result is None

    async def test_async_returns_none_when_wallet_missing(self, db_manager):
        from scripts.core.bybit_account_sync import sync_account_data_async

        with patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch(
                 "scripts.core.bybit_account_sync.get_unified_wallet_async",
                 new_callable=AsyncMock,
                 return_value=None,
             ):
            result = await sync_account_data_async(db_manager)

        assert result is None


class TestSyncAccountDataSync:
    def test_sync_path_uses_sync_fetch(self, db_manager, mock_bybit_client):
        from scripts.core.bybit_account_sync import sync_account_data

        async def _must_not_be_called(*_args, **_kwargs):
            raise AssertionError("must not use async from sync path")

        with patch("scripts.core.bybit_account_sync.is_running", return_value=True), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_sync_blocking", return_value=MOCK_UNIFIED_WALLET), \
             patch("scripts.core.bybit_account_sync.get_positions_sync", return_value=MOCK_POSITIONS[:1]), \
             patch("scripts.core.bybit_account_sync.get_unified_wallet_async", side_effect=_must_not_be_called), \
             patch("scripts.core.bybit_account_sync.get_positions", side_effect=_must_not_be_called), \
             patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client):
            result = sync_account_data(db_manager)

        assert result is not None
        assert result["buying_power"] == 80000.0


class TestWorkerDeadlockRegression:
    async def test_sync_account_data_from_executor_times_out_while_worker_busy(
        self, db_manager, reset_worker_state
    ):
        """
        Regression: sync_account_data inside worker executor deadlocks on bybit_request_sync.

        The worker event loop waits for the executor while the executor waits for the queue.
        """
        worker = reset_worker_state
        loop = asyncio.get_running_loop()
        worker._state.running = True
        worker._state.loop = loop
        worker._state.queue = asyncio.Queue()
        worker.set_mock_handler(lambda op, _kwargs: {"ok": True})

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="test-bybit-worker"
        )
        try:
            from scripts.core.bybit_account_sync import sync_account_data

            async def old_periodic_sync_path():
                await loop.run_in_executor(executor, sync_account_data, db_manager)

            with patch("scripts.core.bybit_account_sync.is_running", return_value=True):
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(old_periodic_sync_path(), timeout=3.0)
        finally:
            executor.shutdown(wait=False)

    async def test_worker_periodic_sync_calls_async_not_executor_sync(
        self, db_manager, reset_worker_state
    ):
        worker = reset_worker_state
        loop = asyncio.get_running_loop()
        worker._state.running = True
        worker._state.loop = loop
        worker._state.queue = asyncio.Queue()
        worker._state.db_manager = db_manager
        worker._state._last_account_sync = 0.0
        worker.set_mock_handler(lambda op, _kwargs: {"ok": True})

        mock_async = AsyncMock(return_value={"account_id": "bybit-demo"})
        with patch.object(worker, "_ACCOUNT_SYNC_INTERVAL", 0.0), \
             patch("scripts.core.bybit_account_sync.sync_account_data_async", mock_async), \
             patch(
                 "scripts.core.bybit_account_sync.sync_account_data",
                 side_effect=AssertionError("periodic sync must not call sync_account_data"),
             ):
            task = asyncio.create_task(worker._worker_loop())
            await asyncio.sleep(0.4)
            worker._state.running = False
            await asyncio.wait_for(task, timeout=3.0)

        mock_async.assert_called_once_with(db_manager)

    async def test_worker_periodic_sync_drains_queue_without_deadlock(
        self, db_manager, mock_bybit_client, reset_worker_state
    ):
        """Regression: awaiting sync on the worker loop starves the request queue."""
        worker = reset_worker_state
        loop = asyncio.get_running_loop()
        worker._state.running = True
        worker._state.loop = loop
        worker._state.queue = asyncio.Queue()
        worker._state.db_manager = db_manager
        worker._state._last_account_sync = 0.0

        def mock_handler(op, kwargs):
            if op == "get_balance":
                return MOCK_BALANCE
            if op == "get_positions":
                return MOCK_POSITIONS[:1]
            return {"ok": True}

        worker.set_mock_handler(mock_handler)

        with patch.object(worker, "_ACCOUNT_SYNC_INTERVAL", 0.0), \
             patch("scripts.core.bybit_client.get_bybit_client", return_value=mock_bybit_client):
            task = asyncio.create_task(worker._worker_loop())
            await asyncio.sleep(1.0)
            worker._state.running = False
            await asyncio.wait_for(task, timeout=3.0)

        with db_manager._connect() as con:
            row = con.execute(
                "SELECT account_id, net_liquidation FROM accounts WHERE broker='bybit'"
            ).fetchone()
        assert row is not None
        assert row[0] == "bybit-demo"
        assert row[1] == 100000.0
