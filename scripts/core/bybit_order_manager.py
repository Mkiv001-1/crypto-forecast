"""
Bybit Order Manager — converts consensus signals into bracket orders via Bybit API.

Адаптация order_manager.py для Bybit (Linear Perpetual).

Modes (ORDER_MODE config key):
  disabled  — no orders placed (default, safe)
  paper     — demo account (Bybit Demo)
  live      — live trading (requires LIVE_TRADING_CONFIRMED=true)

Flow:
  submit_signal()
    → guard checks (mode, blocked, duplicate, max open)
    → slippage guard (bid/ask snapshot)
    → save transient QUEUED order to DB (local pre-submit state)
    → place_bracket_order() → update to SUBMITTED
    → monitor and sync order status

Key differences from IB:
- Crypto trades 24/7 (no market hours check)
- Bybit uses different order types (Limit/Market)
- Position sizing in contracts/coins (not shares)
- Leverage support (1x-100x)
"""

import logging
import sqlite3
import threading
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

# Bybit imports
from scripts.core.bybit_worker import bybit_request_sync, is_running as is_bybit_running
from scripts.core.bybit_config import load_bybit_config
from scripts.core.bybit_instrument import normalize_order_params

logger = logging.getLogger(__name__)

# Submission failures that should not retry via PENDING_ORDER polling
_PERMANENT_ORDER_SKIP_FRAGMENTS = (
    "Open order already exists",
    "Max open positions",
    "is trading_blocked",
    "not in settings",
)

# Per-ticker locks to prevent concurrent duplicate order submission
_ticker_locks: Dict[str, threading.Lock] = {}
_ticker_locks_guard = threading.Lock()


def _get_ticker_lock(ticker: str) -> threading.Lock:
    """Return (creating if needed) a per-ticker threading.Lock."""
    key = ticker.upper()
    with _ticker_locks_guard:
        if key not in _ticker_locks:
            _ticker_locks[key] = threading.Lock()
        return _ticker_locks[key]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _cfg(db_manager, key: str, default: str = "") -> str:
    try:
        v = db_manager.get_config_value(key)
        return v if v is not None else default
    except Exception:
        return default


def _cfg_float(db_manager, key: str, default: float) -> float:
    try:
        return float(_cfg(db_manager, key, str(default)))
    except ValueError:
        return default


def _cfg_int(db_manager, key: str, default: int) -> int:
    try:
        return int(_cfg(db_manager, key, str(default)))
    except ValueError:
        return default


def _cfg_bool(db_manager, key: str, default: bool = False) -> bool:
    return _cfg(db_manager, key, str(default)).lower() == "true"


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _get_last_price(db_manager, ticker: str) -> float:
    """Return the most recent close price for ticker from price_data, or 0.0 if not found."""
    # Prefer encapsulated method if available
    if hasattr(db_manager, 'get_last_price'):
        return db_manager.get_last_price(ticker)
    
    # Fallback for backward compatibility
    try:
        import sqlite3 as _sq
        with _sq.connect(db_manager.db_file) as con:
            row = con.execute(
                "SELECT close FROM price_data WHERE ticker=? ORDER BY date DESC LIMIT 1",
                (ticker,)
            ).fetchone()
        return float(row[0]) if row and row[0] else 0.0
    except Exception:
        return 0.0


def _symbol_from_ticker(ticker: str) -> str:
    """Extract bare symbol from 'BTCUSDT' or returns as-is."""
    # Bybit symbols are already in format like BTCUSDT
    return ticker.strip().upper()


def _is_market_hours() -> bool:
    """Backward-compatible helper: crypto markets are open 24/7."""
    return True


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _open_orders_count_sql(has_trades_table: bool) -> str:
    if not has_trades_table:
        return """SELECT COUNT(*) FROM orders 
                  WHERE UPPER(order_role)='ENTRY' 
                  AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY') 
                  AND status != 'STALE'"""
    return (
        "SELECT COUNT(*) "
        "FROM orders o "
        "LEFT JOIN trades t ON t.bybit_order_id = o.bybit_order_id "
        "WHERE "
        "UPPER(o.order_role)='ENTRY' AND o.status != 'STALE' AND ("
        "o.status IN ('QUEUED','SUBMITTED') "
        "OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')"
        ")"
    )


def _orders(db_manager):
    return db_manager.orders_repo


def _count_open_orders(db_manager) -> int:
    return _orders(db_manager).count_open_orders()


def _has_open_order_for_ticker(db_manager, ticker: str) -> bool:
    return _orders(db_manager).has_open_order_for_ticker(ticker)


def _is_ticker_blocked(db_manager, ticker: str) -> bool:
    return _orders(db_manager).is_ticker_blocked(ticker)


def _is_ticker_known(db_manager, ticker: str) -> bool:
    return _orders(db_manager).is_ticker_known(ticker)


def _save_order(db_manager, order_data: dict) -> int:
    return _orders(db_manager).insert_order(order_data)


def _save_bracket(
    db_manager,
    *,
    ticker: str,
    symbol: str,
    side: str,
    entry_price: Optional[float],
    stop_loss: float,
    take_profit: float,
    quantity: float,
    trade_uid: str,
    order_link_id: str,
    order_type: str,
    leverage: int,
    confidence: float,
    consensus_id: Optional[int],
    methods: str,
    rationale: str,
    created_at: str,
) -> Dict[str, Any]:
    """Create trade row and three orders (ENTRY, TAKE_PROFIT, STOP_LOSS)."""
    repo = _orders(db_manager)
    bracket_ids = repo.insert_bracket_orders(
        ticker=ticker,
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        quantity=quantity,
        trade_uid=trade_uid,
        order_link_id=order_link_id,
        order_type=order_type,
        leverage=leverage,
        confidence=confidence,
        consensus_id=consensus_id,
        methods=methods,
        rationale=rationale,
        created_at=created_at,
    )
    signal = "LONG" if str(side).lower() == "buy" else "SHORT"
    trade_id = repo.insert_trade_for_bracket(
        trade_uid=trade_uid,
        ticker=ticker,
        symbol=symbol,
        signal=signal,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=take_profit,
        entry_order_id=bracket_ids["entry_id"],
        consensus_id=consensus_id,
        leverage=leverage,
        created_at=created_at,
    )
    if consensus_id is not None and trade_id:
        repo.link_consensus_trade(consensus_id, trade_id)
    return {
        **bracket_ids,
        "trade_id": trade_id,
        "trade_uid": trade_uid,
    }


def _fail_bracket(db_manager, trade_uid: str, error_message: str) -> None:
    _orders(db_manager).update_orders_by_trade_uid(
        trade_uid,
        {
            "status": "FAILED",
            "error_message": error_message,
            "updated_at": _now_utc(),
        },
    )


def _update_order(db_manager, row_id: int, updates: dict) -> None:
    _orders(db_manager).update_order(row_id, updates)


def _block_ticker(db_manager, ticker: str) -> None:
    try:
        _orders(db_manager).block_ticker(ticker)
        logger.warning(f"bybit_order_manager: ticker {ticker} BLOCKED (trading_blocked=1)")
    except Exception as e:
        logger.error(f"bybit_order_manager: could not block ticker {ticker}: {e}")


def _log_bybit_transaction(
    db_manager,
    *,
    event_source: str,
    event_type: str,
    operation_status: str = "",
    status_before: str = "",
    status_after: str = "",
    ticker: str = "",
    trade_uid: str = "",
    bybit_order_id: str = "",
    order_id: int = None,
    trade_id: int = None,
    consensus_id: int = None,
    log_id: str = "",
    request_payload = None,
    response_payload = None,
    error_message: str = "",
    latency_ms: int = None,
) -> None:
    """Best-effort write to bybit_order_transactions table."""
    try:
        import json
        
        def _json_payload(value) -> str:
            if value is None:
                return ""
            try:
                text = json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
                return text[:32000] if len(text) <= 32000 else text[:31997] + "..."
            except Exception:
                return str(value)[:32000]
        
        _orders(db_manager).log_bybit_transaction(
            (
                datetime.now(timezone.utc).isoformat(),
                event_source,
                event_type,
                operation_status,
                status_before,
                status_after,
                ticker,
                trade_uid,
                bybit_order_id,
                order_id,
                trade_id,
                consensus_id,
                log_id,
                _json_payload(request_payload),
                _json_payload(response_payload),
                error_message,
                latency_ms,
            )
        )
    except Exception as e:
        logger.warning(f"_log_bybit_transaction failed: {e}")


def log_portfolio_snapshot_transaction(
    db_manager,
    *,
    snapshots_added: int,
    wallet: Dict[str, Any],
    event_source: str = "portfolio_sync",
) -> None:
    """Record a portfolio snapshot sync in bybit_order_transactions (Transaction Log UI)."""
    if snapshots_added <= 0 or not wallet:
        return
    _log_bybit_transaction(
        db_manager,
        event_source=event_source,
        event_type="PORTFOLIO_SNAPSHOT",
        operation_status="SUCCESS",
        ticker="__ACCOUNT_SUMMARY__",
        response_payload={
            "snapshots_added": snapshots_added,
            "total_equity": wallet.get("total_equity"),
            "total_perp_upl": wallet.get("total_perp_upl"),
            "timestamp": wallet.get("timestamp"),
            "coins": [c.get("coin") for c in (wallet.get("coins") or []) if c.get("coin")],
        },
    )


# ---------------------------------------------------------------------------
# Bybit-specific helpers
# ---------------------------------------------------------------------------

def _get_bybit_ticker_snapshot(symbol: str) -> Optional[Dict[str, Any]]:
    """Get current bid/ask from Bybit."""
    try:
        result = bybit_request_sync("get_ticker", symbol=symbol)
        return result
    except Exception as e:
        logger.warning(f"Failed to get Bybit ticker for {symbol}: {e}")
        return None


def _get_symbol_instrument_filters(symbol: str) -> Optional[Dict[str, float]]:
    """Fetch lot size and price tick filters for a linear symbol."""
    try:
        instruments = bybit_request_sync("get_instruments", symbol=symbol)
        if not instruments:
            return None
        inst = instruments[0]
        return {
            "qty_step": float(inst.get("qty_step") or 0),
            "min_order_qty": float(inst.get("min_order_qty") or 0),
            "max_order_qty": float(inst.get("max_order_qty") or 0),
            "tick_size": float(inst.get("tick_size") or 0),
        }
    except Exception as e:
        logger.warning(f"Failed to get instrument filters for {symbol}: {e}")
        return None


def _calculate_position_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    leverage: int = 3,
    min_qty: float = 0.001
) -> float:
    """
    Calculate position size based on risk parameters.
    
    Args:
        equity: Account equity in USDT
        risk_pct: Risk percentage per trade
        entry_price: Entry price
        stop_price: Stop loss price
        leverage: Leverage multiplier
        min_qty: Minimum order quantity
    
    Returns:
        Position size in base currency (e.g., BTC)
    """
    risk_amount = equity * (risk_pct / 100)
    
    # Price distance to stop
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0:
        stop_distance = entry_price * 0.01  # Default 1% if no stop
    
    # Position size without leverage
    position_size = risk_amount / stop_distance
    
    # Apply leverage
    position_size = position_size / leverage
    
    position_size = max(position_size, min_qty)
    return position_size


def _validate_slippage(
    signal_price: float,
    market_bid: float,
    market_ask: float,
    tolerance_pct: float = 0.5
) -> tuple[bool, str]:
    """
    Validate that market price is within acceptable slippage of signal price.
    
    Returns:
        (is_valid, reason)
    """
    mid_price = (market_bid + market_ask) / 2
    slippage_pct = abs(mid_price - signal_price) / signal_price * 100
    
    if slippage_pct > tolerance_pct:
        return False, f"Slippage {slippage_pct:.2f}% exceeds tolerance {tolerance_pct}%"
    
    return True, ""


# ---------------------------------------------------------------------------
# Main submit function
# ---------------------------------------------------------------------------

def submit_signal(
    db_manager,
    ticker: str,
    side: str,  # "Buy" or "Sell"
    entry_price: Optional[float],
    stop_loss: float,
    take_profit: float,
    confidence: float,
    consensus_id: Optional[int] = None,
    methods: str = "",
    rationale: str = "",
) -> Dict[str, Any]:
    """
    Convert a trading signal into a Bybit bracket order.
    
    Args:
        db_manager: SQLiteManager instance
        ticker: Trading pair (e.g., "BTCUSDT")
        side: "Buy" (long) or "Sell" (short)
        entry_price: Entry price (None for market order)
        stop_loss: Stop loss price
        take_profit: Take profit price
        confidence: Signal confidence (0-100)
        consensus_id: Optional consensus log ID
        methods: String of prediction methods used
        rationale: Trading rationale
    
    Returns:
        Dict with status and details
    """
    result = {
        "status": "REJECTED",
        "reason": "",
        "order_id": None,
        "order_ids": [],
        "trade_id": None,
        "trade_uid": None,
        "bybit_order_id": None,
    }
    
    symbol = _symbol_from_ticker(ticker)
    
    # Acquire ticker lock
    lock = _get_ticker_lock(ticker)
    if not lock.acquire(blocking=False):
        result["reason"] = "Concurrent submission blocked"
        logger.warning(f"bybit_order_manager: {ticker} submission blocked by lock")
        return result
    
    try:
        # 1. Check Bybit worker is running
        if not is_bybit_running():
            result["reason"] = "Bybit worker not running"
            logger.error("bybit_order_manager: Cannot submit — bybit_worker is not running")
            return result
        
        # 2. Load config
        config = load_bybit_config(db_manager)
        
        # 3. Check trading mode
        if config.order_mode == "disabled":
            result["reason"] = "Trading disabled (ORDER_MODE=disabled)"
            logger.info(f"bybit_order_manager: {ticker} — trading disabled")
            return result
        
        if config.order_mode == "live" and not config.live_trading_confirmed:
            result["reason"] = "Live trading not confirmed"
            logger.error("bybit_order_manager: Live trading requested but not confirmed")
            return result
        
        # 4. Check ticker is known
        if not _is_ticker_known(db_manager, ticker):
            result["reason"] = f"Ticker {ticker} not in settings"
            logger.warning(f"bybit_order_manager: {ticker} not in settings")
            return result
        
        # 5. Check not blocked
        if _is_ticker_blocked(db_manager, ticker):
            result["reason"] = f"Ticker {ticker} is trading_blocked"
            logger.warning(f"bybit_order_manager: {ticker} is blocked")
            return result
        
        # 6. Check no duplicate order
        if _has_open_order_for_ticker(db_manager, ticker):
            result["reason"] = f"Open order already exists for {ticker}"
            logger.warning(f"bybit_order_manager: {ticker} already has open order")
            return result
        
        # 7. Check max open positions
        max_positions = config.max_open_positions
        current_open = _count_open_orders(db_manager)
        if current_open >= max_positions:
            result["reason"] = f"Max open positions ({max_positions}) reached"
            logger.warning(f"bybit_order_manager: max positions ({max_positions}) reached")
            return result
        
        # 8. Get account balance
        balance = bybit_request_sync("get_balance", coin="USDT")
        if not balance:
            result["reason"] = "Failed to get account balance"
            logger.error("bybit_order_manager: Failed to get USDT balance")
            return result
        
        equity = balance.get("equity", 0)
        available = balance.get("available_balance", 0)
        
        if equity <= 0:
            result["reason"] = "Insufficient equity"
            logger.error(f"bybit_order_manager: Equity is {equity}")
            return result
        
        # 9. Calculate position size
        position_size = _calculate_position_size(
            equity=equity,
            risk_pct=config.max_risk_per_trade_pct,
            entry_price=entry_price or stop_loss * 1.01,  # Approximate if market order
            stop_price=stop_loss,
            leverage=config.default_leverage
        )

        # 9b. Snap qty and prices to Bybit instrument filters (qtyStep / tickSize)
        filters = _get_symbol_instrument_filters(symbol)
        if not filters or filters.get("qty_step", 0) <= 0:
            result["reason"] = "Failed to load instrument lot size filters"
            logger.error(f"bybit_order_manager: no instrument filters for {symbol}")
            return result
        try:
            position_size, entry_price, stop_loss, take_profit = normalize_order_params(
                position_size,
                qty_step=filters["qty_step"],
                min_order_qty=filters["min_order_qty"],
                max_order_qty=filters["max_order_qty"],
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_price=entry_price,
                tick_size=filters["tick_size"],
            )
        except ValueError as e:
            result["reason"] = str(e)
            logger.warning(f"bybit_order_manager: {ticker} — {e}")
            return result

        # 10. Get current market price for slippage check
        ticker_info = _get_bybit_ticker_snapshot(symbol)
        if not ticker_info:
            result["reason"] = "Failed to get market price"
            logger.warning(f"bybit_order_manager: Failed to get ticker for {symbol}")
            return result
        
        market_bid = ticker_info.get("bid", 0)
        market_ask = ticker_info.get("ask", 0)
        
        # 11. Slippage check if entry price specified
        if entry_price:
            is_valid, reason = _validate_slippage(
                entry_price, market_bid, market_ask, config.entry_slippage_tolerance
            )
            if not is_valid:
                result["reason"] = f"Slippage check failed: {reason}"
                logger.warning(f"bybit_order_manager: {ticker} — {reason}")
                return result
        
        # 12. Set leverage for symbol
        leverage_set = bybit_request_sync("set_leverage", symbol=symbol, leverage=config.default_leverage)
        if not leverage_set:
            logger.warning(f"bybit_order_manager: Failed to set leverage for {symbol}")
        
        # 13. Generate unique IDs
        trade_uid = str(uuid.uuid4())[:12]
        order_link_id = f"forecast_{trade_uid}"
        
        # 14. Save trade + three orders as transient local QUEUED state
        order_type = config.default_order_type if entry_price else "Market"
        created_at = _now_utc()

        bracket = _save_bracket(
            db_manager,
            ticker=ticker,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=position_size,
            trade_uid=trade_uid,
            order_link_id=order_link_id,
            order_type=order_type,
            leverage=config.default_leverage,
            confidence=confidence,
            consensus_id=consensus_id,
            methods=methods,
            rationale=rationale,
            created_at=created_at,
        )
        order_row_id = bracket["entry_id"]
        result["order_id"] = order_row_id
        result["order_ids"] = [
            bracket["entry_id"],
            bracket["take_profit_id"],
            bracket["stop_loss_id"],
        ]
        result["trade_id"] = bracket.get("trade_id")
        result["trade_uid"] = trade_uid

        logger.info(
            f"bybit_order_manager: {ticker} QUEUED(local) bracket — {side} {position_size:.6f} @ "
            f"{entry_price or 'MARKET'} (TP: {take_profit}, SL: {stop_loss}) "
            f"orders={result['order_ids']} trade_id={result['trade_id']} "
            f"[Leverage: {config.default_leverage}x]"
        )
        
        # 15. Place bracket order via Bybit
        try:
            bybit_result = bybit_request_sync(
                "place_bracket",
                symbol=symbol,
                side=side,
                qty=position_size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                order_type=order_type,
                time_in_force=config.default_time_in_force,
                order_link_id=order_link_id
            )
            
            if not bybit_result:
                _fail_bracket(
                    db_manager,
                    trade_uid,
                    "Bybit API returned empty result",
                )
                result["reason"] = "Bybit order placement failed"
                logger.error(f"bybit_order_manager: {ticker} order placement failed")
                return result

            bybit_order_id = bybit_result.get("order_id")
            if not bybit_order_id:
                _fail_bracket(
                    db_manager,
                    trade_uid,
                    "Bybit API response missing order_id",
                )
                result["reason"] = "Bybit order placement returned no order_id"
                logger.error(f"bybit_order_manager: {ticker} missing order_id in Bybit response")
                return result
            submitted_at = _now_utc()
            _update_order(db_manager, order_row_id, {
                "status": "SUBMITTED",
                "bybit_order_id": bybit_order_id,
                "submitted_at": submitted_at,
                "updated_at": submitted_at,
            })
            for child_id in (bracket["take_profit_id"], bracket["stop_loss_id"]):
                _update_order(db_manager, child_id, {
                    "status": "SUBMITTED",
                    "submitted_at": submitted_at,
                    "updated_at": submitted_at,
                })

            result["status"] = "SUBMITTED"
            result["bybit_order_id"] = bybit_order_id
            
            logger.info(
                f"bybit_order_manager: {ticker} SUBMITTED — Bybit order {bybit_order_id}"
            )
            
        except Exception as e:
            _fail_bracket(db_manager, trade_uid, str(e))
            result["reason"] = f"Order placement exception: {e}"
            logger.error(f"bybit_order_manager: {ticker} order placement exception: {e}")
            return result
        
        return result
        
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Order synchronization
# ---------------------------------------------------------------------------

def sync_orders_with_bybit(db_manager) -> Dict[str, Any]:
    """
    Synchronize local orders with Bybit API status.
    
    Updates order statuses based on Bybit order status.
    
    Returns:
        Dict with sync statistics
    """
    result = {
        "checked": 0,
        "updated": 0,
        "errors": 0
    }
    
    try:
        rows = _orders(db_manager).fetch_submitted_orders()
        
        for row in rows:
            result["checked"] += 1
            order_id, bybit_order_id, symbol, local_status = row
            
            if not bybit_order_id:
                continue
            
            try:
                # Query Bybit for order status
                bybit_orders = bybit_request_sync(
                    "get_open_orders",
                    symbol=symbol,
                    order_id=bybit_order_id
                )
                
                if not bybit_orders:
                    # Order not found — might be filled or cancelled
                    # Check order history
                    history = bybit_request_sync(
                        "get_order_history",
                        symbol=symbol,
                        order_id=bybit_order_id
                    )
                    
                    if history:
                        bybit_status = history[0].get("status", "UNKNOWN")
                    else:
                        bybit_status = "UNKNOWN"
                else:
                    bybit_status = bybit_orders[0].get("status", "UNKNOWN")
                
                # Map Bybit status to local status
                status_mapping = {
                    "New": "SUBMITTED",
                    "PartiallyFilled": "PARTIALLY_FILLED",
                    "Filled": "FILLED_ENTRY",
                    "Cancelled": "CANCELLED",
                    "Rejected": "REJECTED"
                }
                
                new_status = status_mapping.get(bybit_status, local_status)
                
                if new_status != local_status:
                    _update_order(db_manager, order_id, {
                        "status": new_status,
                        "updated_at": _now_utc(),
                        "filled_at": _now_utc() if new_status == "FILLED_ENTRY" else None
                    })
                    result["updated"] += 1
                    logger.info(
                        f"bybit_order_manager: Order {order_id} status {local_status} -> {new_status}"
                    )
                
            except Exception as e:
                result["errors"] += 1
                logger.error(f"bybit_order_manager: Error syncing order {order_id}: {e}")
        
    except Exception as e:
        logger.error(f"bybit_order_manager: Error in sync_orders: {e}")
    
    return result


# ---------------------------------------------------------------------------
# Position management
# ---------------------------------------------------------------------------

def close_position(db_manager, ticker: str, reason: str = "") -> Dict[str, Any]:
    """
    Close position for a ticker at market price.
    
    Args:
        db_manager: SQLiteManager
        ticker: Trading pair
        reason: Reason for closing
    
    Returns:
        Dict with result status
    """
    result = {"status": "FAILED", "reason": "", "bybit_order_id": None}
    
    symbol = _symbol_from_ticker(ticker)
    
    try:
        # Check Bybit worker
        if not is_bybit_running():
            result["reason"] = "Bybit worker not running"
            return result
        
        # Close position via Bybit
        close_result = bybit_request_sync("close_position", symbol=symbol)
        
        if not close_result:
            result["reason"] = "Bybit close position failed"
            logger.error(f"bybit_order_manager: Failed to close position for {ticker}")
            return result
        
        _orders(db_manager).close_ticker_positions(
            ticker, _now_utc(), reason or "Manual close"
        )
        
        result["status"] = "SUCCESS"
        result["bybit_order_id"] = close_result.get("order_id")
        
        logger.info(f"bybit_order_manager: Position {ticker} closed — reason: {reason}")
        
    except Exception as e:
        result["reason"] = f"Exception: {e}"
        logger.error(f"bybit_order_manager: Error closing position {ticker}: {e}")
    
    return result


def cancel_order(db_manager, order_id: int, reason: str = "") -> Dict[str, Any]:
    """
    Cancel an order by local order ID.
    
    Args:
        db_manager: SQLiteManager
        order_id: Local order ID
        reason: Reason for cancellation
    
    Returns:
        Dict with result status
    """
    result = {"status": "FAILED", "reason": "", "bybit_order_id": None}
    
    try:
        row = _orders(db_manager).get_order_bybit_row(order_id)
        
        if not row:
            result["reason"] = f"Order {order_id} not found"
            return result
        
        bybit_order_id, symbol, status = row
        
        if status not in ["QUEUED", "SUBMITTED", "PARTIALLY_FILLED"]:
            result["reason"] = f"Cannot cancel order with status {status}"
            return result
        
        # Cancel via Bybit
        if bybit_order_id and is_bybit_running():
            cancelled = bybit_request_sync(
                "cancel_order",
                symbol=symbol,
                order_id=bybit_order_id
            )
            
            if not cancelled:
                result["reason"] = "Bybit cancel failed"
                logger.error(f"bybit_order_manager: Failed to cancel order {order_id}")
                return result
        
        # Update local status
        _update_order(db_manager, order_id, {
            "status": "CANCELLED",
            "cancelled_at": _now_utc(),
            "cancel_reason": reason or "Manual cancel"
        })
        
        result["status"] = "SUCCESS"
        result["bybit_order_id"] = bybit_order_id
        
        logger.info(f"bybit_order_manager: Order {order_id} cancelled — reason: {reason}")
        
    except Exception as e:
        result["reason"] = f"Exception: {e}"
        logger.error(f"bybit_order_manager: Error cancelling order {order_id}: {e}")

    return result


def activate_consensus_order(consensus_id: int, db_manager) -> Dict[str, Any]:
    """
    Activate a consensus order by submitting it to Bybit.

    Retrieves consensus data from DB and calls submit_signal to place the order.

    Args:
        consensus_id: ID of the consensus record to activate
        db_manager: SQLiteManager instance

    Returns:
        Dict with status and details
    """
    result = {
        "status": "REJECTED",
        "message": "",
        "consensus_id": consensus_id,
        "order_id": None,
    }

    try:
        row = db_manager.consensus_repo.get_pending_order_row(consensus_id)

        if not row:
            result["message"] = "Consensus not found or not in PENDING_ORDER status"
            logger.warning(f"bybit_order_manager: Consensus {consensus_id} not found or not pending")
            return result

        ticker, signal, entry_price, stop_loss, take_profit, confidence, methods, rationale = row

        # Map signal to side
        side = "Buy" if signal.upper() == "LONG" else "Sell"

        # Submit the signal
        submit_result = submit_signal(
            db_manager=db_manager,
            ticker=ticker,
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence or 50.0,
            consensus_id=consensus_id,
            methods=methods or "",
            rationale=rationale or "",
        )

        # Update result based on submit_signal response
        if submit_result.get("status") == "SUBMITTED":
            result["status"] = "SUCCESS"
            result["message"] = f"Order submitted: {submit_result.get('bybit_order_id', 'N/A')}"
            result["order_id"] = submit_result.get("order_id")
            result["order_ids"] = submit_result.get("order_ids") or []
            result["trade_id"] = submit_result.get("trade_id")

            db_manager.consensus_repo.mark_order_submitted(consensus_id, _now_utc())
        else:
            fail_reason = submit_result.get("reason", "Order submission failed")
            result["message"] = fail_reason
            logger.warning(
                f"bybit_order_manager: Consensus {consensus_id} submission failed: {fail_reason}"
            )
            if any(frag in fail_reason for frag in _PERMANENT_ORDER_SKIP_FRAGMENTS):
                db_manager.consensus_repo.mark_order_skipped(
                    consensus_id, fail_reason, _now_utc()
                )

    except Exception as e:
        result["message"] = f"Exception: {e}"
        logger.error(f"bybit_order_manager: Error activating consensus {consensus_id}: {e}")

    return result
