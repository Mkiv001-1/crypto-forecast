"""Consensus activation and forecast-run API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from scripts.server.routers import common

logger = logging.getLogger(__name__)
router = APIRouter()

verify_api_key = common.verify_api_key
_get_db_manager = common.get_db_manager


@router.post("/consensus/{consensus_id}/activate", dependencies=[Depends(verify_api_key)])
async def activate_consensus(consensus_id: int):
    """Manually trigger order activation for a specific consensus record."""
    try:
        from scripts.core.bybit_order_manager import activate_consensus_order

        from scripts.server.async_blocking import run_blocking

        em = _get_db_manager()
        return await run_blocking(activate_consensus_order, consensus_id, em)
    except Exception as e:
        logger.exception("Error activating consensus order")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/consensus/{consensus_id}/preview-trade", dependencies=[Depends(verify_api_key)])
async def preview_consensus_trade(consensus_id: int):
    """Return trade preview details for confirmation popup."""
    try:
        em = _get_db_manager()
        row = em.consensus_repo.get_pending_order_row(consensus_id)
        if not row:
            raise HTTPException(status_code=404, detail="Consensus not found or not pending")
        ticker, signal, entry_price, stop_loss, take_profit, confidence, methods, rationale = row
        return {
            "consensus_id": consensus_id,
            "ticker": ticker,
            "signal": signal,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "methods": methods,
            "rationale": rationale,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error previewing consensus trade")
        raise HTTPException(status_code=500, detail=str(e)) from e
