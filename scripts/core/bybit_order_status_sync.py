"""
Bybit Order Status Sync — синхронизация статусов ордеров с Bybit API.

Аналог order_status_sync.py для Bybit.

Задачи:
- Периодическая синхронизация открытых ордеров с Bybit
- Обновление статусов локальных ордеров на основе Bybit статусов
- Заполнение filled_at, filled_price при исполнении
- Расчет realized_pnl для закрытых позиций
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List

from scripts.core.bybit_worker import bybit_request_sync, is_running as is_bybit_running

logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(con: sqlite3.Connection, table: str) -> set:
    try:
        return {str(r[1]) for r in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _filter_row_updates(con: sqlite3.Connection, table: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    cols = _table_columns(con, table)
    if not cols:
        return updates
    return {k: v for k, v in updates.items() if k in cols}


def _log_status_transaction(
    db_manager,
    event_source: str,
    event_type: str,
    operation_status: str,
    status_before: str,
    status_after: str,
    ticker: str,
    trade_uid: str,
    bybit_order_id: str,
    order_id: int,
    trade_id: int,
    payload_json: str = "",
    con: sqlite3.Connection = None,
) -> None:
    """Логирование операции синхронизации в bybit_order_transactions."""
    try:
        if con is not None:
            con.execute(
                """
                INSERT INTO bybit_order_transactions (
                    occurred_at, event_source, event_type, operation_status,
                    status_before, status_after, ticker, trade_uid,
                    bybit_order_id, order_id, trade_id,
                    request_payload_json, response_payload_json, error_message, latency_ms
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _now_utc_iso(),
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
                    "",
                    payload_json,
                    "",
                    None,
                ),
            )
            return
    except Exception as e:
        logger.warning(
            "_log_status_transaction in-transaction write failed: %s "
            "(order_id=%s ticker=%s bybit_order_id=%s)",
            e,
            order_id,
            ticker,
            bybit_order_id,
            exc_info=True,
        )


def _calculate_realized_pnl(signal: str, qty: float, entry: float, exit_price: float) -> float:
    """Расчет реализованного PnL."""
    if (signal or "").upper() == "SHORT":
        return (entry - exit_price) * qty
    return (exit_price - entry) * qty


def _find_order_by_bybit_id(
    con: sqlite3.Connection,
    bybit_order_id: str,
) -> Optional[sqlite3.Row]:
    """Найти локальный ордер по Bybit order ID."""
    if not bybit_order_id:
        return None
    
    row = con.execute(
        """SELECT id, ticker, trade_uid, order_role, status, side, 
                  quantity, entry_price, target_price, stop_loss
           FROM orders 
           WHERE bybit_order_id=? OR bybit_order_link_id=?
           ORDER BY id DESC LIMIT 1""",
        (bybit_order_id, bybit_order_id),
    ).fetchone()
    
    return row


def _map_bybit_status(bybit_status: str) -> str:
    """Маппинг статуса Bybit на локальный статус."""
    status_map = {
        "New": "SUBMITTED",
        "PartiallyFilled": "PARTIALLY_FILLED",
        "Filled": "FILLED_ENTRY",
        "Cancelled": "CANCELLED",
        "Rejected": "REJECTED",
        "PendingCancel": "PENDING_CANCEL",
    }
    return status_map.get(bybit_status, bybit_status)


def _make_sync_result(
    *,
    ok: bool,
    scanned: int,
    updated_orders: int,
    updated_trades: int,
    errors: List[str],
    skipped: int = 0,
    details: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Response shape expected by POST /orders/sync and Trading UI."""
    synced_at = _now_utc_iso()
    return {
        "ok": ok,
        "scanned": scanned,
        "updated_orders": updated_orders,
        "updated_trades": updated_trades,
        "errors": errors,
        "synced_at": synced_at,
        "skipped": skipped,
        "details": details or [],
        # Legacy keys used by scheduler / older tests
        "checked": scanned,
        "updated": updated_orders,
    }


def _apply_trade_updates(
    con: sqlite3.Connection,
    *,
    trade_uid: str,
    order_role: str,
    new_status: str,
    filled_price: Optional[float],
    filled_at: str,
    cum_exec_qty: float,
) -> bool:
    """Mirror order status transitions onto the trades row for this trade_uid."""
    if not trade_uid or not _table_exists(con, "trades"):
        return False

    row = con.execute(
        """SELECT id, status, signal, quantity, entry_price
           FROM trades WHERE trade_uid=? LIMIT 1""",
        (trade_uid,),
    ).fetchone()
    if not row:
        return False

    trade_id, trade_status, signal, qty, entry_price = row
    now = _now_utc_iso()
    role = (order_role or "").upper()
    trade_status_u = (trade_status or "").upper()

    if new_status == "FILLED_ENTRY" and role == "ENTRY":
        updates: Dict[str, Any] = {
            "entry_filled_at": filled_at,
            "updated_at": now,
        }
        if filled_price is not None:
            updates["entry_price"] = filled_price
        if cum_exec_qty > 0:
            updates["quantity"] = cum_exec_qty
        set_clause = ", ".join(f"{k}=?" for k in updates)
        con.execute(
            f"UPDATE trades SET {set_clause} WHERE id=?",
            list(updates.values()) + [trade_id],
        )
        return True

    if new_status == "FILLED_ENTRY" and role in ("TAKE_PROFIT", "STOP_LOSS"):
        exit_price = filled_price if filled_price is not None else entry_price
        qty_f = float(qty or 0)
        entry_f = float(entry_price or 0)
        exit_f = float(exit_price or 0)
        realized = _calculate_realized_pnl(signal or "", qty_f, entry_f, exit_f)

        con.execute(
            """UPDATE trades SET
                   status='CLOSED',
                   exit_filled_at=?,
                   exit_price=?,
                   close_reason=?,
                   realized_pnl=?,
                   updated_at=?
               WHERE id=? AND status='OPEN'""",
            (
                filled_at,
                exit_price,
                role.lower(),
                realized,
                now,
                trade_id,
            ),
        )
        return con.total_changes > 0

    if new_status == "CANCELLED" and role == "ENTRY" and trade_status_u == "OPEN":
        entry_filled = con.execute(
            """SELECT 1 FROM orders
               WHERE trade_uid=? AND UPPER(order_role)='ENTRY'
                 AND status IN ('FILLED_ENTRY', 'PARTIALLY_FILLED')
               LIMIT 1""",
            (trade_uid,),
        ).fetchone()
        if entry_filled:
            return False
        con.execute(
            """UPDATE trades SET status='CANCELLED', close_reason='entry_cancelled', updated_at=?
               WHERE id=? AND status='OPEN'""",
            (now, trade_id),
        )
        return con.total_changes > 0

    return False


def _sync_open_trades_with_positions(
    con: sqlite3.Connection,
    *,
    dry_run: bool,
) -> int:
    """Close OPEN trades when Bybit reports no position for the symbol."""
    if not is_bybit_running() or not _table_exists(con, "trades"):
        return 0

    positions = bybit_request_sync("get_positions") or []
    open_sizes: Dict[str, float] = {}
    for pos in positions:
        symbol = str(pos.get("symbol") or "").upper()
        if symbol:
            open_sizes[symbol] = float(pos.get("size", 0) or 0)

    updated = 0
    open_trades = con.execute(
        """SELECT id, trade_uid, ticker, COALESCE(symbol, ticker) AS sym,
                  signal, quantity, entry_price
           FROM trades WHERE UPPER(status)='OPEN'"""
    ).fetchall()

    now = _now_utc_iso()
    for trade_id, trade_uid, ticker, sym, signal, qty, entry_price in open_trades:
        symbol_key = str(sym or ticker or "").upper()
        if not symbol_key:
            continue
        if open_sizes.get(symbol_key, 0) > 0.0001:
            continue

        entry_row = con.execute(
            """SELECT status FROM orders
               WHERE trade_uid=? AND UPPER(order_role)='ENTRY' LIMIT 1""",
            (trade_uid or "",),
        ).fetchone()
        if not entry_row or entry_row[0] not in ("FILLED_ENTRY", "PARTIALLY_FILLED"):
            continue

        exit_row = con.execute(
            """SELECT filled_price, filled_at, order_role FROM orders
               WHERE trade_uid=? AND status='FILLED_ENTRY'
                 AND UPPER(order_role) IN ('TAKE_PROFIT', 'STOP_LOSS')
               ORDER BY filled_at DESC LIMIT 1""",
            (trade_uid or "",),
        ).fetchone()
        exit_price = entry_price
        exit_at = now
        close_reason = "position_closed_on_bybit"
        if exit_row and exit_row[0] is not None:
            exit_price = exit_row[0]
            exit_at = exit_row[1] or now
            close_reason = str(exit_row[2] or close_reason).lower()

        qty_f = float(qty or 0)
        entry_f = float(entry_price or 0)
        exit_f = float(exit_price or 0)
        realized = _calculate_realized_pnl(signal or "", qty_f, entry_f, exit_f)

        if dry_run:
            updated += 1
            continue

        con.execute(
            """UPDATE trades SET
                   status='CLOSED',
                   exit_filled_at=?,
                   exit_price=?,
                   close_reason=?,
                   realized_pnl=?,
                   updated_at=?
               WHERE id=? AND UPPER(status)='OPEN'""",
            (exit_at, exit_price, close_reason, realized, now, trade_id),
        )
        if con.total_changes > 0:
            updated += 1

    return updated


def sync_orders_with_bybit(
    db_manager,
    *,
    ticker: Optional[str] = None,
    dry_run: bool = False,
    source: str = "api",
) -> Dict[str, Any]:
    """
    Синхронизировать статусы ордеров с Bybit API.
    
    Args:
        db_manager: SQLiteManager instance
        ticker: Опционально — синхронизировать только один тикер
        dry_run: Только показать что будет изменено, не применять
    
    Returns:
        Dict with ok/scanned/updated_orders/updated_trades/errors/synced_at for API clients
    """
    scanned = 0
    updated_orders = 0
    updated_trades = 0
    skipped = 0
    error_messages: List[str] = []
    details: List[Dict[str, Any]] = []

    if not is_bybit_running():
        logger.debug("bybit_order_status_sync: Bybit worker not running")
        return _make_sync_result(
            ok=False,
            scanned=0,
            updated_orders=0,
            updated_trades=0,
            errors=["Bybit worker is not running"],
        )

    try:
        with sqlite3.connect(db_manager.db_file) as con:
            if ticker:
                local_orders = con.execute(
                    """SELECT id, ticker, bybit_order_id, bybit_order_link_id,
                              status, side, quantity, entry_price, trade_uid, order_role
                       FROM orders
                       WHERE UPPER(ticker)=UPPER(?)
                       AND status IN ('SUBMITTED', 'PARTIALLY_FILLED', 'QUEUED')""",
                    (ticker,),
                ).fetchall()
            else:
                local_orders = con.execute(
                    """SELECT id, ticker, bybit_order_id, bybit_order_link_id,
                              status, side, quantity, entry_price, trade_uid, order_role
                       FROM orders
                       WHERE status IN ('SUBMITTED', 'PARTIALLY_FILLED', 'QUEUED')"""
                ).fetchall()

            for local_order in local_orders:
                scanned += 1
                (
                    order_id,
                    symbol,
                    bybit_id,
                    link_id,
                    local_status,
                    side,
                    qty,
                    entry,
                    trade_uid,
                    order_role,
                ) = local_order

                search_id = bybit_id or link_id
                if not search_id:
                    skipped += 1
                    continue

                try:
                    bybit_orders = bybit_request_sync(
                        "get_open_orders",
                        symbol=symbol,
                        order_id=bybit_id if bybit_id else None,
                        order_link_id=link_id if link_id and not bybit_id else None,
                    )

                    if not bybit_orders:
                        history = bybit_request_sync(
                            "get_order_history",
                            symbol=symbol,
                            order_id=bybit_id if bybit_id else None,
                            order_link_id=link_id if link_id and not bybit_id else None,
                            limit=10,
                        )
                        bybit_order = history[0] if history else None
                    else:
                        bybit_order = bybit_orders[0]

                    if not bybit_order:
                        logger.warning(
                            "bybit_order_status_sync: Order %s not found on Bybit "
                            "(order_id=%s symbol=%s local_status=%s)",
                            search_id,
                            order_id,
                            symbol,
                            local_status,
                        )
                        skipped += 1
                        continue

                    bybit_status = bybit_order.get("status", "")
                    new_status = _map_bybit_status(bybit_status)

                    if new_status == local_status:
                        continue

                    filled_at = _now_utc_iso()
                    cum_exec_qty = float(bybit_order.get("cum_exec_qty", 0) or 0)
                    cum_exec_value = float(bybit_order.get("cum_exec_value", 0) or 0)
                    avg_price = (
                        cum_exec_value / cum_exec_qty
                        if cum_exec_qty > 0
                        else entry
                    )

                    updates: Dict[str, Any] = {
                        "status": new_status,
                        "updated_at": filled_at,
                    }
                    if new_status == "FILLED_ENTRY":
                        updates["filled_at"] = filled_at
                        updates["filled_price"] = avg_price
                        updates["cum_exec_qty"] = cum_exec_qty
                        updates["cum_exec_value"] = cum_exec_value

                    updates = _filter_row_updates(con, "orders", updates)

                    if not dry_run:
                        if not updates:
                            continue
                        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
                        con.execute(
                            f"UPDATE orders SET {set_clause} WHERE id=?",
                            list(updates.values()) + [order_id],
                        )
                        _log_status_transaction(
                            db_manager,
                            event_source="bybit_sync",
                            event_type="status_change",
                            operation_status="success",
                            status_before=local_status,
                            status_after=new_status,
                            ticker=symbol,
                            trade_uid=trade_uid or "",
                            bybit_order_id=bybit_id or "",
                            order_id=order_id,
                            trade_id=None,
                            payload_json=str(bybit_order),
                            con=con,
                        )
                        if _apply_trade_updates(
                            con,
                            trade_uid=trade_uid or "",
                            order_role=order_role or "",
                            new_status=new_status,
                            filled_price=avg_price,
                            filled_at=filled_at,
                            cum_exec_qty=cum_exec_qty,
                        ):
                            updated_trades += 1
                        con.commit()

                    updated_orders += 1
                    details.append({
                        "order_id": order_id,
                        "symbol": symbol,
                        "old_status": local_status,
                        "new_status": new_status,
                    })
                    logger.info(
                        "bybit_order_status_sync: %s order %s %s -> %s",
                        symbol,
                        order_id,
                        local_status,
                        new_status,
                    )

                except Exception as e:
                    error_messages.append(
                        f"order {order_id} ({symbol}): {e}"
                    )
                    logger.exception(
                        "bybit_order_status_sync: Error syncing order %s "
                        "(symbol=%s bybit_id=%s link_id=%s source=%s)",
                        order_id,
                        symbol,
                        bybit_id,
                        link_id,
                        source,
                    )

            if not dry_run:
                position_trade_updates = _sync_open_trades_with_positions(
                    con, dry_run=False
                )
                if position_trade_updates:
                    updated_trades += position_trade_updates
                    con.commit()

    except Exception as e:
        logger.exception(
            "bybit_order_status_sync: Fatal error (ticker=%s source=%s): %s",
            ticker,
            source,
            e,
        )
        return _make_sync_result(
            ok=False,
            scanned=scanned,
            updated_orders=updated_orders,
            updated_trades=updated_trades,
            errors=[str(e)],
            skipped=skipped,
            details=details,
        )

    return _make_sync_result(
        ok=True,
        scanned=scanned,
        updated_orders=updated_orders,
        updated_trades=updated_trades,
        errors=error_messages,
        skipped=skipped,
        details=details,
    )


def sync_positions_with_bybit(db_manager) -> Dict[str, Any]:
    """
    Синхронизировать позиции с Bybit.
    
    Проверяет открытые позиции на Bybit и обновляет локальные записи.
    """
    result = {
        "bybit_positions": 0,
        "local_matches": 0,
        "mismatches": [],
        "sync_ok": False,
    }
    
    if not is_bybit_running():
        logger.debug("bybit_order_status_sync: Bybit worker not running")
        return result
    
    try:
        # Получаем позиции от Bybit
        positions = bybit_request_sync("get_positions")
        result["bybit_positions"] = len(positions)
        result["sync_ok"] = True
        
        with sqlite3.connect(db_manager.db_file) as con:
            for pos in positions:
                symbol = pos.get("symbol")
                size = pos.get("size", 0)
                side = pos.get("side")
                
                # Ищем соответствующий трейд в локальной БД
                local_trade = con.execute(
                    """SELECT id, ticker, status, quantity, signal 
                       FROM trades 
                       WHERE UPPER(ticker)=UPPER(?) AND status='OPEN'""",
                    (symbol,)
                ).fetchone()
                
                if local_trade:
                    result["local_matches"] += 1
                    # Проверяем соответствие размера позиции
                    local_qty = local_trade[3]
                    if abs(local_qty - size) > 0.0001:  # Допустимая погрешность
                        result["mismatches"].append({
                            "symbol": symbol,
                            "local_qty": local_qty,
                            "bybit_qty": size,
                        })
                else:
                    # Есть позиция на Bybit, но нет в локальной БД
                    result["mismatches"].append({
                        "symbol": symbol,
                        "local_qty": 0,
                        "bybit_qty": size,
                        "note": "Position exists on Bybit but not in local DB",
                    })
    
    except Exception as e:
        logger.exception("bybit_order_status_sync: Error syncing positions: %s", e)
    
    return result


def run_full_sync(db_manager, dry_run: bool = False) -> Dict[str, Any]:
    """Полная синхронизация ордеров и позиций."""
    logger.info("bybit_order_status_sync: Starting full sync")
    
    orders_result = sync_orders_with_bybit(db_manager, dry_run=dry_run)
    positions_result = sync_positions_with_bybit(db_manager)
    
    result = {
        "orders": orders_result,
        "positions": positions_result,
        "timestamp": _now_utc_iso(),
    }
    
    logger.info(
        "bybit_order_status_sync: Full sync complete. "
        "Orders updated: %s, trades updated: %s, positions: %s",
        orders_result.get("updated_orders", 0),
        orders_result.get("updated_trades", 0),
        positions_result["bybit_positions"],
    )
    
    return result
