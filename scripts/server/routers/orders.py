"""Order, trade, and Bybit audit API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from scripts.shared.models import OrderSubmitRequest, OrderSubmitResponse
from scripts.server.routers import common

logger = logging.getLogger(__name__)
router = APIRouter()

verify_api_key = common.verify_api_key
_get_db_manager = common.get_db_manager


@router.get("/orders", dependencies=[Depends(verify_api_key)])
async def get_orders(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
    include_test: bool = Query(True, description="Include test rows (is_test=1)"),
    test_only: bool = Query(False, description="Return only test rows (is_test=1)"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Return orders from the orders table."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            clauses = []
            params: list = []
            if ticker:
                clauses.append("UPPER(ticker)=UPPER(?)")
                params.append(ticker)
            if status:
                clauses.append("UPPER(status)=UPPER(?)")
                params.append(status)
            if test_only:
                clauses.append("COALESCE(is_test, 0)=1")
            elif not include_test:
                clauses.append("COALESCE(is_test, 0)=0")
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = con.execute(
                f"SELECT * FROM orders {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.exception("Error fetching orders")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_order_endpoint(order_id: int):
    """Cancel a Bybit order by DB id."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            row = con.execute(
                "SELECT bybit_order_id, ticker FROM orders WHERE id=?", (order_id,)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        bybit_id = row["bybit_order_id"]
        ticker = row["ticker"]
        if not bybit_id:
            raise HTTPException(status_code=400, detail="Order has no Bybit ID")

        from scripts.core.bybit_worker import bybit_request

        symbol = ticker.split(":")[-1] if ":" in ticker else ticker
        result = await bybit_request("cancel_order", order_id=bybit_id, symbol=symbol)
        ok = result.get("success", False) if result else False
        return {"cancelled": ok, "order_id": order_id, "bybit_order_id": bybit_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error cancelling order")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/orders/sync", dependencies=[Depends(verify_api_key)])
async def sync_orders_from_bybit():
    """Manually synchronize order statuses from Bybit into local orders/trades."""
    try:
        em = _get_db_manager()
        from scripts.core.bybit_order_status_sync import sync_orders_with_bybit
        from scripts.server.async_blocking import run_blocking

        result = await run_blocking(sync_orders_with_bybit, em, source="manual")
        if bool(result.get("ok", False)):
            synced_at = str(result.get("synced_at", "") or "")
            if synced_at:
                em.set_config_value("LAST_ORDERS_SYNC_AT", synced_at)
        return result
    except Exception as e:
        logger.exception("Error syncing orders from Bybit")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/orders/submit", response_model=OrderSubmitResponse, dependencies=[Depends(verify_api_key)])
async def submit_order_manual(body: OrderSubmitRequest):
    """Manually submit order for ticker based on latest consensus."""
    try:
        from scripts.server.services.orders_service import submit_manual_from_consensus

        em = _get_db_manager()
        from scripts.server.async_blocking import run_blocking

        result = await run_blocking(
            submit_manual_from_consensus,
            em,
            ticker=body.ticker,
            stop_loss=body.stop_loss,
            target_price=body.target_price,
            entry_limit_price=body.entry_limit_price,
            quantity_override=body.quantity,
        )
        if result["status"] == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        return OrderSubmitResponse(
            status=result["status"],
            order_ids=result.get("order_ids", []),
            message=result.get("message", ""),
            consensus_signal=result.get("consensus_signal", ""),
            confidence=result.get("confidence", 0.0),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error submitting order")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/trades", dependencies=[Depends(verify_api_key)])
async def get_trades(
    trade_id: Optional[int] = None,
    consensus_id: Optional[int] = None,
    status: Optional[str] = None,
    ticker: Optional[str] = None,
    include_test: bool = Query(True, description="Include test rows (is_test=1)"),
    test_only: bool = Query(False, description="Return only test rows (is_test=1)"),
    limit: int = Query(200, ge=1, le=5000),
):
    """Return trades list from the trades table."""
    try:
        em = _get_db_manager()
        where_parts = []
        params = []
        if trade_id is not None:
            where_parts.append("id = ?")
            params.append(int(trade_id))
        if consensus_id is not None:
            where_parts.append("consensus_id = ?")
            params.append(int(consensus_id))
        if status:
            where_parts.append("status = ?")
            params.append(status)
        if ticker:
            where_parts.append("UPPER(ticker) = UPPER(?)")
            params.append(ticker)
        if test_only:
            where_parts.append("COALESCE(is_test, 0)=1")
        elif not include_test:
            where_parts.append("COALESCE(is_test, 0)=0")
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        effective_limit = 1 if (trade_id is not None or consensus_id is not None) else limit
        with em._connect() as con:
            rows = con.execute(
                f"SELECT * FROM trades {where_sql} ORDER BY id DESC LIMIT ?",
                params + [effective_limit],
            ).fetchall()
        items = [dict(r) for r in rows]
        return {"items": items, "trades": items, "total": len(items)}
    except Exception as e:
        logger.exception("Error fetching trades")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/bybit-log", dependencies=[Depends(verify_api_key)])
async def get_bybit_log(ticker: Optional[str] = None, limit: int = 500):
    """Return recent Bybit API audit log entries."""
    try:
        em = _get_db_manager()
        where_sql = "WHERE ticker = ?" if ticker else ""
        params = [ticker] if ticker else []
        with em._connect() as con:
            rows = con.execute(
                f"SELECT * FROM bybit_gateway_log {where_sql} ORDER BY id DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return {"log": [dict(r) for r in rows]}
    except Exception as e:
        logger.exception("Error fetching bybit_gateway_log")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/bybit-transactions", dependencies=[Depends(verify_api_key)])
async def get_bybit_transactions(
    ticker: Optional[str] = None,
    bybit_order_id: Optional[str] = None,
    event_source: Optional[str] = None,
    event_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
):
    """Return rows from bybit_order_transactions with optional filters."""
    try:
        em = _get_db_manager()
        where_parts = []
        params = []
        if ticker:
            where_parts.append("ticker = ?")
            params.append(ticker)
        if bybit_order_id:
            where_parts.append("bybit_order_id = ?")
            params.append(bybit_order_id)
        if event_source:
            where_parts.append("event_source = ?")
            params.append(event_source)
        if event_type:
            where_parts.append("event_type = ?")
            params.append(event_type)
        if date_from:
            where_parts.append("occurred_at >= ?")
            params.append(date_from)
        if date_to:
            where_parts.append("occurred_at <= ?")
            params.append(date_to + "T23:59:59")
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with em._connect() as con:
            rows = con.execute(
                f"SELECT * FROM bybit_order_transactions {where_sql} ORDER BY occurred_at DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        items = [dict(r) for r in rows]
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("Error fetching bybit_order_transactions")
        raise HTTPException(status_code=500, detail=str(e)) from e
