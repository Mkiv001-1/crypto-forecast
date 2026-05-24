"""
Bybit Worker — single-threaded serialized queue for all Bybit API calls.

Аналог ib_worker.py, но для Bybit API.
Все серверные взаимодействия с Bybit идут через `bybit_request(op, **kwargs)`.

Usage (from async context):
    from scripts.core.bybit_worker import bybit_request
    result = await bybit_request("place_bracket", symbol="BTCUSDT", ...)

Usage (from sync thread):
    from scripts.core.bybit_worker import bybit_request_sync
    result = bybit_request_sync("place_bracket", symbol="BTCUSDT", ...)

Lifecycle (FastAPI lifespan):
    await start_bybit_worker(db_manager)
    ...
    await stop_bybit_worker()
"""

import asyncio
import concurrent.futures
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from scripts.core.bybit_client import BybitClient, get_bybit_client, init_bybit_client
from scripts.core.bybit_config import load_bybit_config, validate_api_credentials

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
# Extra wait for callers blocked on the single-worker queue (one op ahead + execution).
_QUEUE_WAIT_SLACK = _DEFAULT_TIMEOUT
_ACCOUNT_SYNC_INTERVAL = 60.0  # seconds between automatic account syncs


# -----------------------------------------------------------------------------
# Worker state
# -----------------------------------------------------------------------------

@dataclass
class _WorkerState:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    loop: Optional[asyncio.AbstractEventLoop] = None
    task: Optional[asyncio.Task] = None
    db_manager: Any = None
    running: bool = False
    _mock_handler: Optional[Any] = None  # for testing
    _last_account_sync: float = 0.0  # timestamp of last account sync
    _account_sync_task: Optional[asyncio.Task] = None  # in-flight periodic sync


_state = _WorkerState()


# -----------------------------------------------------------------------------
# Request envelope
# -----------------------------------------------------------------------------

@dataclass
class _BybitRequest:
    op: str
    kwargs: Dict[str, Any]
    future: asyncio.Future


# -----------------------------------------------------------------------------
# Operation dispatch
# -----------------------------------------------------------------------------

def _execute_op(op: str, kwargs: Dict[str, Any]) -> Any:
    """Execute a single Bybit operation synchronously. Runs inside worker thread."""
    if _state._mock_handler is not None:
        return _state._mock_handler(op, kwargs)
    
    client = get_bybit_client()
    if client is None:
        raise RuntimeError("Bybit client not initialized")
    
    # Trading operations
    if op == "place_order":
        return client.place_order(**kwargs)
    
    if op == "place_bracket":
        return client.place_bracket_order(**kwargs)
    
    if op == "cancel_order":
        return client.cancel_order(**kwargs)
    
    if op == "cancel_all_orders":
        return client.cancel_all_orders(**kwargs)
    
    if op == "close_position":
        return client.close_position_market(**kwargs)
    
    # Account operations
    if op == "get_balance":
        coin = kwargs.get("coin", "USDT")
        return client.get_wallet_balance(coin)

    if op == "get_unified_wallet":
        return client.get_unified_wallet()
    
    if op == "get_positions":
        return client.get_positions(**kwargs)
    
    if op == "get_position":
        return client.get_position(**kwargs)
    
    if op == "set_leverage":
        return client.set_leverage(**kwargs)
    
    # Market data operations
    if op == "get_ticker":
        return client.get_ticker(**kwargs)
    
    if op == "get_orderbook":
        return client.get_orderbook(**kwargs)
    
    if op == "get_klines":
        return client.get_klines(**kwargs)
    
    if op == "get_instruments":
        return client.get_instruments(**kwargs)
    
    # Order operations
    if op == "get_open_orders":
        return client.get_open_orders(**kwargs)
    
    if op == "get_order_history":
        return client.get_order_history(**kwargs)
    
    # Test/utility operations
    if op == "test_connection":
        return client.test_connection()
    
    if op == "get_server_time":
        return client.get_server_time()
    
    if op == "get_account_info":
        return client.get_account_info()
    
    raise ValueError(f"bybit_worker: unknown op '{op}'")


async def _run_periodic_account_sync() -> None:
    """Fetch balance/positions via the worker queue and persist (must not run on worker loop)."""
    if _state.db_manager is None:
        return
    try:
        from scripts.core.bybit_account_sync import sync_account_data_async

        await sync_account_data_async(_state.db_manager)
    except Exception as e:
        logger.warning(f"bybit_worker: periodic account sync failed: {e}")


def _schedule_periodic_account_sync() -> None:
    """Kick off account sync without blocking the worker loop (avoids queue deadlock)."""
    task = _state._account_sync_task
    if task is not None and not task.done():
        return
    _state._last_account_sync = time.time()
    _state._account_sync_task = asyncio.create_task(
        _run_periodic_account_sync(),
        name="bybit-account-sync",
    )


# -----------------------------------------------------------------------------
# Worker loop
# -----------------------------------------------------------------------------

async def _worker_loop() -> None:
    """Drain the queue, execute each request in a thread executor."""
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="bybit-worker"
    )
    loop = asyncio.get_running_loop()
    logger.info("bybit_worker: started")
    
    try:
        while _state.running:
            # Periodic account sync runs in a sibling task so this loop can drain the queue.
            now = time.time()
            if now - _state._last_account_sync >= _ACCOUNT_SYNC_INTERVAL:
                if _state.db_manager is not None:
                    _schedule_periodic_account_sync()
            
            try:
                req: _BybitRequest = await asyncio.wait_for(_state.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            if req.future.cancelled():
                _state.queue.task_done()
                continue
            
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(executor, _execute_op, req.op, req.kwargs),
                    timeout=_DEFAULT_TIMEOUT,
                )
                if not req.future.done():
                    req.future.set_result(result)
            except asyncio.TimeoutError:
                logger.error(f"bybit_worker: op='{req.op}' timed out after {_DEFAULT_TIMEOUT}s")
                if not req.future.done():
                    req.future.set_exception(
                        TimeoutError(f"Bybit op '{req.op}' timed out after {_DEFAULT_TIMEOUT}s")
                    )
            except Exception as e:
                logger.error(f"bybit_worker: op='{req.op}' failed: {e}")
                if not req.future.done():
                    req.future.set_exception(e)
            finally:
                _state.queue.task_done()
    finally:
        executor.shutdown(wait=False)
        logger.info("bybit_worker: stopped")


# -----------------------------------------------------------------------------
# Public lifecycle API
# -----------------------------------------------------------------------------

async def start_bybit_worker(db_manager: Any = None) -> None:
    """
    Start the Bybit worker. Call from FastAPI lifespan startup.
    
    Args:
        db_manager: SQLiteManager для загрузки конфигурации
    """
    if _state.running:
        logger.warning("bybit_worker: already running, ignoring start")
        return
    
    # Load configuration
    config = load_bybit_config(db_manager)
    
    # Validate credentials
    is_valid, error = validate_api_credentials(config)
    if not is_valid:
        logger.error(f"bybit_worker: invalid credentials — {error}")
        logger.error("Trading will be disabled. Set BYBIT_API_KEY and BYBIT_API_SECRET.")
        return
    
    # Initialize client
    try:
        init_bybit_client(
            api_key=config.api_key,
            api_secret=config.api_secret,
            demo=config.demo,
            recv_window=config.recv_window,
        )

        # Test connection
        client = get_bybit_client()
        if client:
            client.log_time_skew_warning()
        if client and client.test_connection():
            logger.info(f"bybit_worker: connected to Bybit ({'demo' if config.demo else 'live'})")
        else:
            logger.warning("bybit_worker: connection test failed")
    except Exception as e:
        logger.error(f"bybit_worker: failed to initialize client: {e}")
        return
    
    _state.db_manager = db_manager
    _state.running = True
    _state.queue = asyncio.Queue()
    _state.loop = asyncio.get_running_loop()
    # Defer first periodic sync so startup does not block the HTTP event loop.
    _state._last_account_sync = time.time()
    _state.task = asyncio.create_task(_worker_loop(), name="bybit-worker")
    logger.debug("bybit_worker: task created")


async def stop_bybit_worker() -> None:
    """Stop the Bybit worker. Call from FastAPI lifespan shutdown."""
    _state.running = False

    sync_task = _state._account_sync_task
    if sync_task is not None and not sync_task.done():
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
    _state._account_sync_task = None

    if _state.task and not _state.task.done():
        try:
            await asyncio.wait_for(_state.task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _state.task.cancel()
    
    _state.task = None
    _state.loop = None
    
    # Close client
    from scripts.core.bybit_client import close_bybit_client
    close_bybit_client()
    
    logger.info("bybit_worker: shutdown complete")


# -----------------------------------------------------------------------------
# Public request API
# -----------------------------------------------------------------------------

def _resolve_worker_module():
    """Use the canonical worker module when loaded as bare ``bybit_worker`` (scheduler threads)."""
    canonical = sys.modules.get("scripts.core.bybit_worker")
    if canonical is not None and canonical is not sys.modules.get(__name__):
        return canonical
    return sys.modules[__name__]


async def bybit_request(op: str, timeout: float = _DEFAULT_TIMEOUT, **kwargs) -> Any:
    """
    Submit a Bybit operation and await the result (non-blocking).
    
    Args:
        op: Operation name
        timeout: Timeout in seconds
        **kwargs: Operation arguments
    
    Raises:
        TimeoutError: If operation exceeds timeout
        RuntimeError: If worker is not running
    """
    mod = _resolve_worker_module()
    if mod is not sys.modules[__name__]:
        return await mod.bybit_request(op, timeout=timeout, **kwargs)

    if not _state.running or _state.loop is None:
        raise RuntimeError("bybit_worker is not running — call start_bybit_worker() first")

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    await _state.queue.put(_BybitRequest(op=op, kwargs=kwargs, future=future))
    return await asyncio.wait_for(
        future, timeout=timeout + _QUEUE_WAIT_SLACK + 2.0
    )


def bybit_request_sync(op: str, timeout: float = _DEFAULT_TIMEOUT, **kwargs) -> Any:
    """
    Submit a Bybit operation from a synchronous (non-async) thread.
    
    Uses run_coroutine_threadsafe to bridge into the worker's event loop.
    Blocks the calling thread until the result is available.
    
    Raises:
        RuntimeError: If worker is not running
    """
    mod = _resolve_worker_module()
    if mod is not sys.modules[__name__]:
        return mod.bybit_request_sync(op, timeout=timeout, **kwargs)

    if not _state.running or _state.loop is None:
        raise RuntimeError("bybit_worker is not running — call start_bybit_worker() first")

    future = asyncio.run_coroutine_threadsafe(
        bybit_request(op, timeout=timeout, **kwargs),
        _state.loop,
    )
    return future.result(timeout=timeout + _QUEUE_WAIT_SLACK + 5.0)


# -----------------------------------------------------------------------------
# Convenience methods
# -----------------------------------------------------------------------------

async def get_wallet_balance(coin: str = "USDT") -> Optional[Dict]:
    """Get wallet balance (async)."""
    return await bybit_request("get_balance", coin=coin)


def get_wallet_balance_sync(coin: str = "USDT") -> Optional[Dict]:
    """Get wallet balance (sync)."""
    return bybit_request_sync("get_balance", coin=coin)


async def get_unified_wallet_sync() -> Optional[Dict]:
    """Get unified trading wallet summary (async)."""
    return await bybit_request("get_unified_wallet")


def get_unified_wallet_sync_blocking() -> Optional[Dict]:
    """Get unified trading wallet summary (sync)."""
    return bybit_request_sync("get_unified_wallet")


async def get_positions(symbol: Optional[str] = None) -> list:
    """Get positions (async)."""
    return await bybit_request("get_positions", symbol=symbol)


def get_positions_sync(symbol: Optional[str] = None) -> list:
    """Get positions (sync)."""
    return bybit_request_sync("get_positions", symbol=symbol)


async def place_bracket_order(
    symbol: str,
    side: str,
    qty: float,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
) -> Optional[Dict]:
    """
    Place bracket order (entry + TP + SL).
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        side: "Buy" or "Sell"
        qty: Quantity
        entry_price: Entry price (None for market order)
        stop_loss: Stop loss price
        take_profit: Take profit price
    
    Returns:
        Order result dict or None
    """
    order_type = "Limit" if entry_price else "Market"
    
    return await bybit_request(
        "place_bracket",
        symbol=symbol,
        side=side,
        qty=qty,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_type=order_type
    )


def place_bracket_order_sync(
    symbol: str,
    side: str,
    qty: float,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
) -> Optional[Dict]:
    """Place bracket order (sync)."""
    order_type = "Limit" if entry_price else "Market"
    
    return bybit_request_sync(
        "place_bracket",
        symbol=symbol,
        side=side,
        qty=qty,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_type=order_type
    )


async def cancel_order(symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
    """Cancel order (async)."""
    return await bybit_request("cancel_order", symbol=symbol, order_id=order_id, order_link_id=order_link_id)


def cancel_order_sync(symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
    """Cancel order (sync)."""
    return bybit_request_sync("cancel_order", symbol=symbol, order_id=order_id, order_link_id=order_link_id)


async def close_position(symbol: str) -> Optional[Dict]:
    """Close position at market price (async)."""
    return await bybit_request("close_position", symbol=symbol)


def close_position_sync(symbol: str) -> Optional[Dict]:
    """Close position at market price (sync)."""
    return bybit_request_sync("close_position", symbol=symbol)


async def get_ticker(symbol: str) -> Optional[Dict]:
    """Get ticker info (async)."""
    return await bybit_request("get_ticker", symbol=symbol)


def get_ticker_sync(symbol: str) -> Optional[Dict]:
    """Get ticker info (sync)."""
    return bybit_request_sync("get_ticker", symbol=symbol)


# -----------------------------------------------------------------------------
# Testing helpers
# -----------------------------------------------------------------------------

def set_mock_handler(handler: Optional[Any]) -> None:
    """Set a mock handler for testing. handler(op, kwargs) -> result. Pass None to clear."""
    _state._mock_handler = handler


def is_running() -> bool:
    """Return True if the worker is active."""
    return _resolve_worker_module()._state.running


def get_queue_size() -> int:
    """Get current queue size (for monitoring)."""
    return _state.queue.qsize() if _state.queue else 0
