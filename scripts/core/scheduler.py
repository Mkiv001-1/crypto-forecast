"""
Centralized async task scheduler.

Registers named tasks with schedules, runs them as asyncio.Tasks,
tracks status in the scheduled_tasks table, and provides a heartbeat.

Integration: call start_scheduler(db_manager) from FastAPI lifespan startup,
             call stop_scheduler() on shutdown.
"""

import asyncio
import concurrent.futures
import logging
import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, Optional, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_HEARTBEAT_PROBE_CACHE: Dict[str, tuple[float, int, str]] = {}
_HEARTBEAT_PROBE_SUCCESS_TTL_SEC = 300

# ---------------------------------------------------------------------------
# Scheduler state (encapsulated in class to avoid global state)
# ---------------------------------------------------------------------------

class SchedulerState:
    """Encapsulated scheduler state to avoid global variables."""
    
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.db_manager = None
        self.running = False
        self.task_running: Dict[str, bool] = {}  # overlap guard per task name
        self.thread_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
    
    def reset(self):
        """Reset state for clean shutdown/restart."""
        self.tasks.clear()
        self.task_running.clear()
        self.db_manager = None
        self.running = False
        if self.thread_pool:
            self.thread_pool.shutdown(wait=False, cancel_futures=True)
            self.thread_pool = None


# Module-level singleton instance
_state = SchedulerState()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _cfg(key: str, default: str = "") -> str:
    if _state.db_manager is None:
        return default
    try:
        v = _state.db_manager.get_config_value(key)
        return v if v else default
    except Exception:
        return default


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(_cfg(key, str(default)))
    except ValueError:
        return default


def _cached_probe(
    name: str,
    probe_func: Callable[[], tuple[int, str]],
    *,
    success_ttl_sec: int = _HEARTBEAT_PROBE_SUCCESS_TTL_SEC,
    failure_ttl_sec: int = 30,
) -> tuple[int, str]:
    cached = _HEARTBEAT_PROBE_CACHE.get(name)
    now = time.monotonic()
    if cached:
        cached_at, status, note = cached
        age = now - cached_at
        if status == 1 and age < success_ttl_sec:
            return status, note
        if status == 0 and age < failure_ttl_sec:
            return status, note

    status, note = probe_func()
    _HEARTBEAT_PROBE_CACHE[name] = (now, status, note)
    return status, note


def _probe_openrouter() -> tuple[int, str]:
    if _state.db_manager is None:
        return 0, "openrouter_err:no_db_manager"

    api_key = _cfg("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return 0, "openrouter_err:no_api_key"

    request = Request(
        "https://openrouter.ai/api/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "forecast-heartbeat/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            status_code = getattr(response, "status", response.getcode())
            if 200 <= int(status_code) < 300:
                return 1, ""
            return 0, f"openrouter_err:http_{status_code}"
    except HTTPError as e:
        return 0, f"openrouter_err:http_{e.code}"
    except URLError as e:
        return 0, f"openrouter_err:{getattr(e, 'reason', e)}"
    except Exception as e:
        return 0, f"openrouter_err:{e}"


def _probe_market_data() -> tuple[int, str]:
    request = Request(
        "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
        headers={
            "Accept": "application/json",
            "User-Agent": "forecast-heartbeat/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            status_code = getattr(response, "status", response.getcode())
            if not (200 <= int(status_code) < 300):
                return 0, f"marketdata_err:http_{status_code}"
            raw = response.read(2048)
            if not raw:
                return 0, "marketdata_err:empty_response"
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(payload, dict):
                return 0, "marketdata_err:invalid_payload"
            ret_code = payload.get("retCode")
            if ret_code != 0:
                return 0, f"marketdata_err:retCode_{ret_code}"
            result = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
            tickers = result.get("list", []) if isinstance(result.get("list"), list) else []
            if tickers:
                return 1, ""
            return 0, "marketdata_err:missing_ticker_list"
    except HTTPError as e:
        return 0, f"marketdata_err:http_{e.code}"
    except URLError as e:
        return 0, f"marketdata_err:{getattr(e, 'reason', e)}"
    except Exception as e:
        return 0, f"marketdata_err:{e}"


# ---------------------------------------------------------------------------
# DB helpers (using encapsulated db_manager methods)
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _upsert_task(name: str, updates: dict) -> None:
    """Upsert scheduled task using db_manager method."""
    if _state.db_manager is None:
        return
    _state.db_manager.upsert_scheduled_task(name, updates)


def _increment_counters(name: str, success: bool, error_msg: str = "") -> None:
    """Increment task counters using db_manager method."""
    if _state.db_manager is None:
        return
    _state.db_manager.increment_task_counters(name, success, error_msg)


# ---------------------------------------------------------------------------
# Task runner
# ---------------------------------------------------------------------------

async def _run_task_loop(
    name: str,
    coro_factory: Callable,
    interval_seconds: float,
    max_retries: int = 2,
    run_on_start: bool = False,
) -> None:
    """Repeatedly call coro_factory() every interval_seconds, with retries."""
    logger.info(f"scheduler: task '{name}' started (interval={interval_seconds}s)")
    _state.task_running[name] = False

    # Calculate initial sleep: if not run_on_start, check last_run_at from DB
    # so that after restart we don't wait a full interval if the task is overdue.
    initial_sleep = interval_seconds
    if not run_on_start and _state.db_manager:
        last_run_str = _state.db_manager.get_scheduled_task_last_run(name)
        if last_run_str:
            try:
                last_run = datetime.fromisoformat(last_run_str)
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(tz=timezone.utc) - last_run).total_seconds()
                remaining = interval_seconds - elapsed
                if remaining <= 0:
                    initial_sleep = 0.0
                    logger.info(f"scheduler: '{name}' overdue by {-remaining:.0f}s, running immediately")
                else:
                    initial_sleep = remaining
                    logger.info(f"scheduler: '{name}' resuming, next run in {remaining:.0f}s")
            except Exception:
                pass
    elif run_on_start:
        initial_sleep = 0.0

    if initial_sleep > 0:
        await asyncio.sleep(initial_sleep)

    while _state.running:
        if _state.task_running.get(name):
            logger.warning(f"scheduler: '{name}' previous run still in progress, skipping interval")
            await asyncio.sleep(interval_seconds)
            continue
        _state.task_running[name] = True
        attempt = 0
        success = False
        last_error = ""
        try:
            while attempt <= max_retries and not success:
                try:
                    await coro_factory()
                    success = True
                except Exception as e:
                    last_error = str(e)
                    attempt += 1
                    if attempt <= max_retries:
                        wait = 2 ** attempt
                        logger.warning(
                            f"scheduler: '{name}' attempt {attempt}/{max_retries} failed: {e}. "
                            f"Retrying in {wait}s"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"scheduler: '{name}' failed after {max_retries} retries: {e}")
        finally:
            _state.task_running[name] = False

        _increment_counters(name, success, last_error)
        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# Built-in tasks
# ---------------------------------------------------------------------------

async def _heartbeat_task() -> None:
    """Check Bybit / OpenRouter / market data / SQLite health and log to heartbeat_log."""
    bybit_ok = 0
    or_ok = 0
    marketdata_ok = 0
    db_ok = 0
    notes = []

    # SQLite check
    if _state.db_manager:
        try:
            with _state.db_manager._connect() as con:
                con.execute("SELECT 1")
            db_ok = 1
        except Exception as e:
            notes.append(f"sqlite_err:{e}")

    # OpenRouter check: probe the real API instead of trusting circuit state.
    try:
        or_ok, or_note = _cached_probe("openrouter", _probe_openrouter)
        if or_note:
            notes.append(or_note)
    except Exception as e:
        notes.append(f"openrouter_err:{e}")

    # Market data check: probe a lightweight public Bybit ticker endpoint.
    try:
        marketdata_ok, marketdata_note = _cached_probe("marketdata", _probe_market_data)
        if marketdata_note:
            notes.append(marketdata_note)
    except Exception as e:
        notes.append(f"marketdata_err:{e}")

    # Bybit check: verify a live Bybit connection via bybit_worker queue.
    if _state.db_manager:
        try:
            from scripts.core.bybit_worker import bybit_request, is_running
            if not is_running():
                notes.append("bybit_err:worker_not_running")
            else:
                result = await asyncio.wait_for(
                    bybit_request("test_connection"),
                    timeout=20,
                )
                bybit_ok = 1 if result else 0
                if not result:
                    notes.append("bybit_err:connection_failed")
        except Exception as e:
            notes.append(f"bybit_err:{e}")

    # Write to heartbeat_log
    if _state.db_manager:
        _state.db_manager.log_heartbeat(bybit_ok, or_ok, db_ok, "; ".join(notes))

    logger.debug(
        f"heartbeat: bybit={bybit_ok} openrouter={or_ok} "
        f"marketdata={marketdata_ok} sqlite={db_ok}"
    )


def _prepare_worker_cwd() -> None:
    from scripts.bootstrap import bootstrap_paths, get_project_root

    bootstrap_paths()
    os.chdir(get_project_root())


def _run_forecast_sync() -> None:
    """Blocking call to run_trading_bot — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.forecast_runner import run_trading_bot
    from scripts.core.sqlite_manager import SQLiteManager

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    run_id = None
    try:
        active_tickers = db.get_settings()
        run_id = db.create_forecast_run('scheduler', len(active_tickers))
        run_trading_bot(db_manager=db, run_id=run_id)
    except Exception as e:
        if run_id:
            db.complete_forecast_run(run_id, status='failed', error_message=str(e))
        raise


def _run_evaluate_sync() -> None:
    """Blocking call to evaluate_past_forecasts — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.forecast_runner import evaluate_past_forecasts
    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    evaluate_past_forecasts(db)


async def _scheduled_forecast_task() -> None:
    """Run forecast generation in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting scheduled forecast run")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_forecast_sync)
    logger.info("scheduler: scheduled forecast run complete")


async def _scheduled_evaluate_task() -> None:
    """Run evaluation of past forecasts in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting scheduled evaluate run")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_evaluate_sync)
    logger.info("scheduler: scheduled evaluate run complete")


def _run_consensus_evaluate_sync() -> None:
    """Blocking call to evaluate_consensus_records — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.consensus_evaluator import evaluate_consensus_records
    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    count = evaluate_consensus_records(db)
    try:
        from scripts.core.model_performance_tracker import update_all_from_evaluations

        updated = update_all_from_evaluations(db)
        logger.info("scheduler: provider EMA updated for %s models", updated)
    except Exception as exc:
        logger.warning("scheduler: provider EMA update failed: %s", exc)
    logger.info(f"scheduler: consensus_evaluate completed, {count} records evaluated")


async def _scheduled_consensus_evaluate_task() -> None:
    """Run evaluation of consensus records in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting scheduled consensus evaluate run")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_consensus_evaluate_sync)
    logger.info("scheduler: scheduled consensus evaluate run complete")


def _run_logs_evaluate_sync() -> None:
    """Blocking call to evaluate_logs_records — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.forecast_runner import evaluate_logs_records
    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    count = evaluate_logs_records(db)
    logger.info(f"scheduler: logs_evaluate completed, {count} records evaluated")


async def _scheduled_logs_evaluate_task() -> None:
    """Run evaluation of individual Logs records in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting scheduled logs evaluate run")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_logs_evaluate_sync)
    logger.info("scheduler: scheduled logs evaluate run complete")


def _run_price_data_update_sync() -> None:
    """Fetch and save fresh price data for all active tickers."""
    _prepare_worker_cwd()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_data_loader import fetch_price_data_bybit
    from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
    from scripts.core.bybit_client import init_bybit_client, get_bybit_client

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    tickers = db.get_active_tickers() if hasattr(db, "get_active_tickers") else []
    if not tickers:
        # fallback: read from settings table directly using encapsulated method
        tickers = db.get_active_tickers_direct()
    if not tickers:
        logger.warning("scheduler: price_data_update — no active tickers")
        return

    # Initialize Bybit client in thread context
    client = None
    try:
        config = load_bybit_config(db)
        is_valid, error = validate_api_credentials(config)
        if is_valid:
            init_bybit_client(
                api_key=config.api_key,
                api_secret=config.api_secret,
                demo=config.demo,
                recv_window=config.recv_window,
            )
            client = get_bybit_client()
        else:
            logger.warning(f"scheduler: price_data_update — invalid Bybit credentials - {error}")
    except Exception as e:
        logger.warning(f"scheduler: price_data_update — failed to initialize Bybit client: {e}")

    updated = 0
    for ticker in tickers:
        try:
            # Convert ticker format for Bybit
            symbol = ticker.split(":")[-1] if ":" in ticker else ticker
            data = fetch_price_data_bybit(symbol, days=30, db_manager=db, client=client)
            if data:
                db.save_price_data(data, ticker=ticker)
                updated += 1
                logger.info(f"scheduler: price_data updated for {ticker} ({len(data)} bars)")
            else:
                logger.warning(f"scheduler: price_data_update — no data returned for {ticker}")
        except Exception as e:
            logger.error(f"scheduler: price_data_update error for {ticker}: {e}")
    logger.info(f"scheduler: price_data_update done. updated={updated}/{len(tickers)}")


def _run_startup_price_data_backfill() -> None:
    """On server startup: check last date per ticker and fetch any missing UTC calendar days."""
    _prepare_worker_cwd()
    from datetime import date as _date
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_data_loader import fetch_price_data_bybit
    from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
    from scripts.core.bybit_client import init_bybit_client, get_bybit_client

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    tickers = db.get_active_tickers() if hasattr(db, "get_active_tickers") else []
    if not tickers:
        tickers = db.get_active_tickers_direct()
    if not tickers:
        logger.warning("startup backfill: no active tickers")
        return

    # Initialize Bybit client in thread context (global may not be visible across threads)
    try:
        config = load_bybit_config(db)
        is_valid, error = validate_api_credentials(config)
        if is_valid:
            init_bybit_client(
                api_key=config.api_key,
                api_secret=config.api_secret,
                demo=config.demo,
                recv_window=config.recv_window,
            )
            client = get_bybit_client()
            logger.debug("startup backfill: Bybit client initialized in thread context")
        else:
            logger.warning(f"startup backfill: invalid Bybit credentials - {error}")
            client = None
    except Exception as e:
        logger.warning(f"startup backfill: failed to initialize Bybit client: {e}")
        client = None

    from datetime import datetime as _dt
    today = _date.today()
    # Crypto runs 24/7. Treat daily bars as UTC calendar-day candles.
    last_completed_day = today

    updated = 0
    for ticker in tickers:
        try:
            # Read last date directly — avoids the configurable staleness threshold
            last_date_str = db.get_max_price_data_date(ticker)

            if last_date_str:
                last_day = _dt.strptime(last_date_str[:10], "%Y-%m-%d").date()
                missing_days = max((last_completed_day - last_day).days, 0)
            else:
                last_day = None
                missing_days = 999

            if missing_days == 0:
                logger.info(f"startup backfill: {ticker} is up to date (last={last_date_str}), skipping")
                continue

            if last_date_str:
                days_to_fetch = max(missing_days + 5, 10)
                logger.info(
                    f"startup backfill: {ticker} missing ~{missing_days} calendar days since {last_date_str}, "
                    f"fetching {days_to_fetch}d"
                )
            else:
                days_to_fetch = 250
                logger.info(f"startup backfill: {ticker} has no data, fetching {days_to_fetch}d")

            # Convert ticker format for Bybit
            symbol = ticker.split(":")[-1] if ":" in ticker else ticker
            data = fetch_price_data_bybit(symbol, days=days_to_fetch, db_manager=db, client=client)
            if data:
                db.save_price_data(data, ticker=ticker)
                updated += 1
                logger.info(f"startup backfill: {ticker} saved {len(data)} bars")
            else:
                logger.warning(f"startup backfill: no data returned for {ticker}")
        except Exception as e:
            logger.error(f"startup backfill: error for {ticker}: {e}")

    logger.info(f"startup backfill: done. updated={updated}/{len(tickers)}")


async def run_startup_price_data_backfill() -> None:
    """Async wrapper: run startup price backfill in a thread pool."""
    loop = asyncio.get_running_loop()
    if _state.thread_pool is not None:
        await loop.run_in_executor(_state.thread_pool, _run_startup_price_data_backfill)
    else:
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="startup-backfill"
        )
        try:
            await loop.run_in_executor(pool, _run_startup_price_data_backfill)
        finally:
            pool.shutdown(wait=False)


async def _scheduled_price_data_task() -> None:
    """Refresh price data for all active tickers in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting price_data update")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_price_data_update_sync)
    logger.info("scheduler: price_data update complete")


def _run_intraday_update_sync() -> None:
    """Fetch and save fresh hourly bars for all active tickers."""
    _prepare_worker_cwd()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_data_loader import fetch_bybit_intraday
    from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
    from scripts.core.bybit_client import init_bybit_client, get_bybit_client

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    tickers = db.get_active_tickers() if hasattr(db, "get_active_tickers") else []
    if not tickers:
        tickers = db.get_active_tickers_direct()
    if not tickers:
        logger.warning("scheduler: intraday_update — no active tickers")
        return

    # Initialize Bybit client in thread context
    client = None
    try:
        config = load_bybit_config(db)
        is_valid, error = validate_api_credentials(config)
        if is_valid:
            init_bybit_client(
                api_key=config.api_key,
                api_secret=config.api_secret,
                demo=config.demo,
                recv_window=config.recv_window,
            )
            client = get_bybit_client()
        else:
            logger.warning(f"scheduler: intraday_update — invalid Bybit credentials - {error}")
    except Exception as e:
        logger.warning(f"scheduler: intraday_update — failed to initialize Bybit client: {e}")

    updated = 0
    for ticker in tickers:
        try:
            # Convert ticker format (e.g., BTCUSDT) for Bybit
            symbol = ticker.split(":")[-1] if ":" in ticker else ticker
            bars = fetch_bybit_intraday(symbol, interval="60", days=30, client=client)
            if bars:
                db.save_intraday_data(bars, ticker=ticker, interval="1h")
                updated += 1
                logger.info(f"scheduler: intraday updated for {ticker} ({len(bars)} bars)")
            else:
                logger.warning(f"scheduler: intraday_update — no data returned for {ticker}")
        except Exception as e:
            logger.error(f"scheduler: intraday_update error for {ticker}: {e}")
    logger.info(f"scheduler: intraday_update done. updated={updated}/{len(tickers)}")


async def _scheduled_intraday_task() -> None:
    """Refresh hourly intraday bars for all active tickers (non-blocking)."""
    loop = asyncio.get_running_loop()
    logger.info("scheduler: starting intraday update")
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_intraday_update_sync)
    logger.info("scheduler: intraday update complete")


async def _expire_queued_orders_task() -> None:
    """Expire stale local QUEUED orders older than ORDER_QUEUE_MAX_AGE_HOURS."""
    max_age_hours = _cfg_int("ORDER_QUEUE_MAX_AGE_HOURS", 24)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    try:
        if _state.db_manager:
            expired = _state.db_manager.expire_queued_orders(cutoff)
            if expired:
                logger.info(f"scheduler: expired {expired} stale QUEUED(local) orders older than {max_age_hours}h")
    except Exception as e:
        logger.error(f"scheduler: expire_queued_orders error: {e}")


async def _expire_filled_orders_task() -> None:
    """Archive FILLED_ENTRY orders older than FILLED_ORDERS_RETENTION_DAYS."""
    retention_days = _cfg_int("FILLED_ORDERS_RETENTION_DAYS", 30)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=retention_days)).isoformat()
    try:
        if _state.db_manager:
            archived = _state.db_manager.expire_filled_orders(cutoff)
            if archived:
                logger.info(f"scheduler: archived {archived} FILLED_ENTRY orders older than {retention_days} days")
    except Exception as e:
        logger.error(f"scheduler: expire_filled_orders error: {e}")


async def _expire_stuck_submitted_orders_task() -> None:
    """Mark stuck SUBMITTED orders as STALE if older than SUBMITTED_ORDERS_MAX_AGE_HOURS."""
    max_age_hours = _cfg_int("SUBMITTED_ORDERS_MAX_AGE_HOURS", 12)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    try:
        if _state.db_manager:
            stale = _state.db_manager.expire_stuck_submitted_orders(cutoff)
            if stale:
                logger.info(f"scheduler: marked {stale} SUBMITTED orders as STALE (older than {max_age_hours}h)")
    except Exception as e:
        logger.error(f"scheduler: expire_stuck_submitted_orders error: {e}")


def _run_process_pending_orders_sync() -> None:
    """Expire stale PENDING_ORDER rows, then activate fresh candidates."""
    _prepare_worker_cwd()
    from datetime import datetime, timezone

    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_order_manager import activate_consensus_order
    from scripts.core.trading_exposure import ticker_has_trading_exposure

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)

    ttl_minutes = _cfg_int("FORECAST_TTL_MINUTES", 240)
    expired = db.consensus_repo.expire_stale_pending_orders(ttl_minutes)
    if expired:
        logger.info(f"scheduler: pending_orders — expired {expired} stale PENDING_ORDER row(s)")

    rows = db.get_pending_consensus_orders()
    if not rows:
        return

    logger.info(f"scheduler: pending_orders — processing {len(rows)} candidates")
    now_utc = datetime.now(tz=timezone.utc).isoformat()
    for row_id, ticker in rows:
        try:
            has_exposure, exp_reason = ticker_has_trading_exposure(db, ticker)
            if has_exposure:
                db.consensus_repo.mark_order_skipped(row_id, exp_reason or "existing_exposure", now_utc)
                logger.debug(
                    f"scheduler: pending_orders consensus={row_id} {ticker} → skipped (exposure)"
                )
                continue
            result = activate_consensus_order(row_id, db)
            logger.debug(f"scheduler: pending_orders consensus={row_id} {ticker} → {result['status']}: {result.get('message','')}")
        except Exception as e:
            logger.error(f"scheduler: pending_orders error for consensus={row_id} {ticker}: {e}")


async def _scheduled_pending_orders_task() -> None:
    """Activate pending consensus orders (non-blocking)."""
    loop = asyncio.get_running_loop()
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_process_pending_orders_sync)


def _run_order_status_sync_sync() -> None:
    """Sync local orders/trades statuses from Bybit as a scheduler task."""
    _prepare_worker_cwd()
    from scripts.core.bybit_worker import is_running as _bybit_running
    if not _bybit_running():
        logger.debug("scheduler: sync_order_statuses skipped — Bybit worker not running")
        return
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_order_status_sync import sync_orders_with_bybit

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)

    result = sync_orders_with_bybit(db, source="scheduler")
    if not result.get("ok", False):
        errors = result.get("errors") or []
        detail = errors[0] if errors else "order status sync failed"
        raise RuntimeError(detail)


async def _await_blocking(sync_fn) -> None:
    """Run blocking scheduler work off the event loop (thread pool or asyncio.to_thread)."""
    if _state.thread_pool is not None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_state.thread_pool, sync_fn)
    else:
        await asyncio.to_thread(sync_fn)


async def _scheduled_order_status_sync_task() -> None:
    """Run Bybit order status synchronization in a background thread."""
    await _await_blocking(_run_order_status_sync_sync)


async def _scheduled_portfolio_history_snapshot_task() -> None:
    """Persist one portfolio history snapshot (account summary) from Bybit unified wallet."""
    if _state.db_manager is None:
        raise RuntimeError("scheduler: db manager is not initialized")

    from scripts.core.bybit_unified_wallet import sync_unified_wallet_snapshot

    wallet, inserted = sync_unified_wallet_snapshot(_state.db_manager)
    if wallet:
        logger.info("scheduler: portfolio_history_snapshot inserted %d row(s)", inserted)
    else:
        logger.warning("scheduler: portfolio_history_snapshot failed - no unified wallet data")


def _run_bybit_transaction_log_sync_sync() -> None:
    """Sync Bybit UTA transaction log — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.bybit_worker import is_running as _bybit_running
    if not _bybit_running():
        logger.debug("scheduler: bybit_transaction_log_sync skipped — worker not running")
        return
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_transaction_log_sync import sync_bybit_transaction_log

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)
    result = sync_bybit_transaction_log(db)
    logger.info(
        "scheduler: bybit_transaction_log_sync fetched=%s synced=%s",
        result.get("fetched"),
        result.get("synced"),
    )


async def _scheduled_bybit_transaction_log_sync_task() -> None:
    """Run Bybit UTA transaction log sync in a thread pool."""
    await _await_blocking(_run_bybit_transaction_log_sync_sync)


def _run_portfolio_sync_sync() -> None:
    """Fetch positions from Bybit and update Portfolio table — executed in thread pool."""
    _prepare_worker_cwd()
    from scripts.core.bybit_worker import is_running as _bybit_running
    if not _bybit_running():
        logger.debug("scheduler: portfolio_sync skipped — Bybit worker not running")
        return
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.core.bybit_order_status_sync import sync_positions_with_bybit
    from datetime import datetime, timezone

    db_file = _state.db_manager.db_file if _state.db_manager else None
    db = SQLiteManager(db_file)

    result = sync_positions_with_bybit(db)
    if result.get("sync_ok"):
        synced_at = datetime.now(tz=timezone.utc).isoformat()
        db.set_config_value("LAST_PORTFOLIO_SYNC_AT", synced_at)
        logger.info(f"scheduler: portfolio_sync completed at {synced_at}")
    else:
        raise RuntimeError("portfolio sync failed - check Bybit connection")


async def _scheduled_portfolio_sync_task() -> None:
    """Run Bybit portfolio synchronization in a thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    if _state.thread_pool is None:
        raise RuntimeError("scheduler: thread pool is not initialized")
    await loop.run_in_executor(_state.thread_pool, _run_portfolio_sync_sync)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TASK_FACTORIES = {
    "heartbeat": _heartbeat_task,
    "expire_queued_orders": _expire_queued_orders_task,
    "expire_filled_orders": _expire_filled_orders_task,
    "expire_stuck_submitted": _expire_stuck_submitted_orders_task,
    "process_pending_orders": _scheduled_pending_orders_task,
    "sync_order_statuses": _scheduled_order_status_sync_task,
    "portfolio_sync": _scheduled_portfolio_sync_task,
    "portfolio_history_snapshot": _scheduled_portfolio_history_snapshot_task,
    "bybit_transaction_log_sync": _scheduled_bybit_transaction_log_sync_task,
    "update_price_data": _scheduled_price_data_task,
    "update_intraday": _scheduled_intraday_task,
    "scheduled_forecast": _scheduled_forecast_task,
    "scheduled_evaluate": _scheduled_evaluate_task,
    "consensus_evaluate": _scheduled_consensus_evaluate_task,
    "logs_evaluate": _scheduled_logs_evaluate_task,
}


def _cfg_int_for(db_manager, key: str, default: int) -> int:
    """Read config int using explicit db_manager (for API paths before scheduler start)."""
    if db_manager is None:
        return default
    try:
        v = db_manager.get_config_value(key)
        return int(v) if v else default
    except (ValueError, TypeError):
        return default
    except Exception:
        return default


def _task_interval_specs(db_manager=None) -> list[tuple[str, int, bool]]:
    """Return (name, interval_seconds, run_on_start) for all scheduler tasks."""
    mgr = db_manager or _state.db_manager
    forecast_interval = _cfg_int_for(mgr, "FORECAST_INTERVAL_MINUTES", 240) * 60
    evaluate_interval = _cfg_int_for(mgr, "EVALUATE_INTERVAL_MINUTES", 120) * 60
    price_data_interval = _cfg_int_for(mgr, "PRICE_DATA_INTERVAL_MINUTES", 60) * 60
    intraday_interval = _cfg_int_for(mgr, "INTRADAY_UPDATE_INTERVAL_MINUTES", 60) * 60
    pending_orders_interval = _cfg_int_for(mgr, "PENDING_ORDERS_INTERVAL_MINUTES", 1) * 60
    order_status_sync_interval = _cfg_int_for(mgr, "ORDER_STATUS_SYNC_INTERVAL_SECONDS", 60)
    portfolio_history_interval = _cfg_int_for(mgr, "PORTFOLIO_HISTORY_SNAPSHOT_INTERVAL_MINUTES", 1440) * 60
    portfolio_sync_interval = _cfg_int_for(mgr, "PORTFOLIO_SYNC_INTERVAL_MINUTES", 5) * 60
    transaction_log_interval = (
        _cfg_int_for(mgr, "BYBIT_TRANSACTION_LOG_SYNC_INTERVAL_MINUTES", 60) * 60
    )
    logs_evaluate_interval = _cfg_int_for(mgr, "LOGS_EVALUATE_INTERVAL_MINUTES", 120) * 60

    return [
        ("heartbeat", 30, True),
        ("expire_queued_orders", 300, False),
        ("expire_filled_orders", 86400, False),
        ("expire_stuck_submitted", 3600, False),
        ("process_pending_orders", pending_orders_interval, False),
        ("sync_order_statuses", order_status_sync_interval, False),
        ("portfolio_sync", portfolio_sync_interval, True),
        ("portfolio_history_snapshot", portfolio_history_interval, False),
        ("bybit_transaction_log_sync", transaction_log_interval, False),
        ("update_price_data", price_data_interval, False),
        ("update_intraday", intraday_interval, False),
        ("scheduled_forecast", forecast_interval, False),
        ("scheduled_evaluate", evaluate_interval, False),
        ("consensus_evaluate", evaluate_interval, False),
        ("logs_evaluate", logs_evaluate_interval, False),
    ]


def ensure_scheduled_tasks_catalog(db_manager) -> None:
    """Insert missing scheduled_tasks rows so GUI/API always see the full catalog."""
    if db_manager is None:
        return
    try:
        with db_manager._connect() as con:
            existing = {
                row[0]
                for row in con.execute("SELECT name FROM scheduled_tasks").fetchall()
            }
        for name, interval, _run_on_start in _task_interval_specs(db_manager=db_manager):
            if name in existing:
                continue
            db_manager.upsert_scheduled_task(
                name,
                {
                    "schedule_type": "interval",
                    "schedule_value": str(interval),
                    "is_active": 1,
                    "max_duration_sec": interval * 2,
                },
            )
    except Exception as exc:
        logger.warning("scheduler: ensure_scheduled_tasks_catalog failed: %s", exc)


def list_scheduler_tasks_for_api(db_manager) -> list[dict]:
    """Return scheduled_tasks rows enriched with live asyncio runtime status."""
    ensure_scheduled_tasks_catalog(db_manager)
    items: list[dict] = []
    try:
        with db_manager._connect() as con:
            rows = con.execute("SELECT * FROM scheduled_tasks ORDER BY name").fetchall()
        items = [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("scheduler: list_scheduler_tasks_for_api failed: %s", exc)
        return items

    runtime = get_task_status()
    for item in items:
        name = item.get("name", "")
        rt = runtime.get(name, {})
        item["live_running"] = bool(rt.get("running"))
        if rt.get("running"):
            item["last_run_status"] = "running"
        elif rt.get("exception") and not item.get("last_run_status"):
            item["last_run_status"] = "error"
    return items


async def start_scheduler(db_manager) -> None:
    """Start all scheduler tasks. Call from FastAPI lifespan."""
    # Reset any previous state
    _state.reset()
    
    _state.db_manager = db_manager
    _state.running = True

    max_workers = _cfg_int("SCHEDULER_MAX_WORKERS", 4)
    if max_workers < 1:
        max_workers = 4
    _state.thread_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="scheduler-robot",
    )
    logger.info(f"scheduler: thread pool initialized with max_workers={max_workers}")

    max_retries = _cfg_int("SCHEDULER_MAX_RETRIES", 2)
    task_specs = [
        (name, _TASK_FACTORIES[name], interval, run_on_start)
        for name, interval, run_on_start in _task_interval_specs(db_manager=db_manager)
    ]

    for name, factory, interval, run_on_start in task_specs:
        _upsert_task(name, {
            "schedule_type":  "interval",
            "schedule_value": str(interval),
            "is_active":      1,
            "max_duration_sec": interval * 2,
        })

        task = asyncio.create_task(
            _run_task_loop(name, factory, interval, max_retries, run_on_start),
            name=name,
        )
        _state.tasks[name] = task
        logger.info(f"scheduler: registered task '{name}' every {interval}s")

    logger.info(f"scheduler: started with {len(_state.tasks)} tasks")


async def stop_scheduler() -> None:
    """Cancel all scheduler tasks. Call from FastAPI lifespan shutdown."""
    _state.running = False
    for name, task in _state.tasks.items():
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"scheduler: task '{name}' stopped")
    _state.tasks.clear()

    if _state.thread_pool is not None:
        _state.thread_pool.shutdown(wait=False, cancel_futures=True)
        _state.thread_pool = None

    logger.info("scheduler: all tasks stopped")


def get_task_status() -> Dict[str, Any]:
    """Return current status of all registered tasks."""
    result = {}
    for name, task in _state.tasks.items():
        result[name] = {
            "running": not task.done(),
            "cancelled": task.cancelled(),
            "exception": str(task.exception()) if task.done() and not task.cancelled() and task.exception() else None,
        }
    return result
