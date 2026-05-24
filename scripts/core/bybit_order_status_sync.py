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
        Dict с результатами синхронизации
    """
    result = {
        "checked": 0,
        "updated": 0,
        "errors": 0,
        "skipped": 0,
        "details": [],
    }
    
    if not is_bybit_running():
        logger.debug("bybit_order_status_sync: Bybit worker not running")
        result["errors"] += 1
        return result
    
    try:
        with sqlite3.connect(db_manager.db_file) as con:
            # Получаем открытые ордера из локальной БД
            if ticker:
                local_orders = con.execute(
                    """SELECT id, ticker, bybit_order_id, bybit_order_link_id, 
                              status, side, quantity, entry_price, trade_uid
                       FROM orders 
                       WHERE UPPER(ticker)=UPPER(?) 
                       AND status IN ('SUBMITTED', 'PARTIALLY_FILLED', 'QUEUED')""",
                    (ticker,)
                ).fetchall()
            else:
                local_orders = con.execute(
                    """SELECT id, ticker, bybit_order_id, bybit_order_link_id,
                              status, side, quantity, entry_price, trade_uid
                       FROM orders 
                       WHERE status IN ('SUBMITTED', 'PARTIALLY_FILLED', 'QUEUED')"""
                ).fetchall()
            
            for local_order in local_orders:
                result["checked"] += 1
                order_id, symbol, bybit_id, link_id, local_status, side, qty, entry, trade_uid = local_order
                
                # Пропускаем если нет Bybit ID
                search_id = bybit_id or link_id
                if not search_id:
                    result["skipped"] += 1
                    continue
                
                try:
                    # Получаем статус от Bybit
                    bybit_orders = bybit_request_sync(
                        "get_open_orders",
                        symbol=symbol,
                        order_id=bybit_id if bybit_id else None,
                        order_link_id=link_id if link_id and not bybit_id else None,
                    )
                    
                    # Если не найден в открытых — проверяем историю
                    if not bybit_orders:
                        history = bybit_request_sync(
                            "get_order_history",
                            symbol=symbol,
                            order_id=bybit_id if bybit_id else None,
                            order_link_id=link_id if link_id and not bybit_id else None,
                            limit=10,
                        )
                        if history:
                            bybit_order = history[0]
                        else:
                            bybit_order = None
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
                        result["skipped"] += 1
                        continue
                    
                    # Маппим статус
                    bybit_status = bybit_order.get("status", "")
                    new_status = _map_bybit_status(bybit_status)
                    
                    if new_status != local_status:
                        updates = {
                            "status": new_status,
                            "updated_at": _now_utc_iso(),
                        }
                        
                        # Если исполнен — заполняем цену и время
                        if new_status == "FILLED_ENTRY":
                            cum_exec_qty = bybit_order.get("cum_exec_qty", 0)
                            cum_exec_value = bybit_order.get("cum_exec_value", 0)
                            avg_price = cum_exec_value / cum_exec_qty if cum_exec_qty > 0 else entry
                            
                            updates["filled_at"] = _now_utc_iso()
                            updates["filled_price"] = avg_price
                            updates["cum_exec_qty"] = cum_exec_qty
                            updates["cum_exec_value"] = cum_exec_value
                        
                        if not dry_run:
                            # Обновляем ордер
                            set_clause = ", ".join(f"{k}=?" for k in updates.keys())
                            con.execute(
                                f"UPDATE orders SET {set_clause} WHERE id=?",
                                list(updates.values()) + [order_id]
                            )
                            
                            # Логируем транзакцию
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
                            con.commit()
                        
                        result["updated"] += 1
                        result["details"].append({
                            "order_id": order_id,
                            "symbol": symbol,
                            "old_status": local_status,
                            "new_status": new_status,
                        })
                        
                        logger.info(
                            f"bybit_order_status_sync: {symbol} order {order_id} "
                            f"{local_status} -> {new_status}"
                        )
                    
                except Exception as e:
                    result["errors"] += 1
                    logger.exception(
                        "bybit_order_status_sync: Error syncing order %s "
                        "(symbol=%s bybit_id=%s link_id=%s source=%s)",
                        order_id,
                        symbol,
                        bybit_id,
                        link_id,
                        source,
                    )
    
    except Exception as e:
        logger.exception(
            "bybit_order_status_sync: Fatal error (ticker=%s source=%s): %s",
            ticker,
            source,
            e,
        )
        result["errors"] += 1
    
    return result


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
    
    logger.info(f"bybit_order_status_sync: Full sync complete. "
                f"Orders updated: {orders_result['updated']}, "
                f"Positions: {positions_result['bybit_positions']}")
    
    return result
