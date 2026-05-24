"""Order submission helpers for API layer."""

from typing import Any, Dict, Optional

from scripts.core.bybit_capital_provider import get_available_capital
from scripts.core.config import get_confidence_threshold
from scripts.core.position_sizer import calculate_position


def _signal_to_side(signal: str) -> str:
    return "Buy" if str(signal).upper() == "LONG" else "Sell"


def submit_manual_from_consensus(
    db_manager,
    *,
    ticker: str,
    stop_loss: Optional[float] = None,
    target_price: Optional[float] = None,
    entry_limit_price: Optional[float] = None,
    quantity_override: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build and submit a Bybit order from the latest consensus row for ticker.

    Returns dict suitable for OrderSubmitResponse fields plus internal keys.
    """
    with db_manager._connect() as con:
        row = con.execute(
            "SELECT * FROM consensus WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()

    if not row:
        return {
            "status": "NOT_FOUND",
            "order_ids": [],
            "message": f"No consensus found for {ticker}",
            "consensus_signal": "",
            "confidence": 0.0,
        }

    consensus = dict(row)
    consensus_id = consensus.get("id")
    signal = consensus.get("signal", "NEUTRAL")
    confidence = float(consensus.get("confidence") or 0.0)

    if signal not in ("LONG", "SHORT"):
        return {
            "status": "SKIPPED_NEUTRAL",
            "order_ids": [],
            "message": f"Signal is {signal}, not LONG/SHORT",
            "consensus_signal": signal,
            "confidence": confidence,
        }

    threshold = get_confidence_threshold(db_manager)
    if confidence < threshold:
        return {
            "status": "SKIPPED_LOW_CONFIDENCE",
            "order_ids": [],
            "message": f"Confidence {confidence:.1f}% < {threshold}%",
            "consensus_signal": signal,
            "confidence": confidence,
        }

    if stop_loss is not None:
        consensus["stop_loss"] = stop_loss
    if target_price is not None:
        consensus["target_price"] = target_price
    if entry_limit_price is not None:
        consensus["entry_limit_price"] = entry_limit_price

    stop = consensus.get("stop_loss")
    take_profit = consensus.get("target_price")
    if not stop or not take_profit:
        return {
            "status": "SKIPPED_MISSING_LEVELS",
            "order_ids": [],
            "message": "Missing stop_loss or target_price",
            "consensus_signal": signal,
            "confidence": confidence,
        }

    try:
        net_liquidation = get_available_capital(db_manager, allow_fallback=True)
    except Exception as e:
        return {
            "status": "SKIPPED_NO_CAPITAL",
            "order_ids": [],
            "message": f"Capital unavailable: {e}",
            "consensus_signal": signal,
            "confidence": confidence,
        }

    with db_manager._connect() as con:
        price_row = con.execute(
            "SELECT close FROM price_data WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if entry_limit_price is not None:
        sizing_entry = float(entry_limit_price)
    elif price_row and price_row["close"]:
        sizing_entry = float(price_row["close"])
    else:
        sizing_entry = float(take_profit)

    position = calculate_position(
        ticker=ticker,
        entry_price=sizing_entry,
        stop_loss=float(stop),
        db_manager=db_manager,
        net_liquidation=net_liquidation,
    )

    if position["status"] != "OK" or position["quantity"] <= 0:
        return {
            "status": position.get("status", "INVALID_POSITION"),
            "order_ids": [],
            "message": f"Position sizing failed: {position.get('status', 'unknown')}",
            "consensus_signal": signal,
            "confidence": confidence,
        }

    qty = float(position["quantity"])
    if quantity_override is not None and quantity_override > 0:
        qty = float(quantity_override)

    from scripts.core.bybit_order_manager import submit_signal

    result = submit_signal(
        db_manager=db_manager,
        ticker=ticker,
        side=_signal_to_side(signal),
        entry_price=entry_limit_price,
        stop_loss=float(stop),
        take_profit=float(take_profit),
        confidence=confidence,
        consensus_id=int(consensus_id) if consensus_id is not None else None,
        methods=str(consensus.get("methods") or ""),
        rationale=str(consensus.get("rationale") or ""),
    )

    order_ids = list(result.get("order_ids") or [])
    order_id = result.get("order_id")
    if not order_ids and order_id:
        order_ids = [order_id]
    status = result.get("status", "REJECTED")
    if status == "SUBMITTED":
        status = "SUCCESS"
    message = result.get("reason") or (
        f"Order submitted: {result.get('bybit_order_id', 'N/A')}" if status == "SUCCESS" else ""
    )

    return {
        "status": status,
        "order_ids": order_ids,
        "message": message,
        "consensus_signal": signal,
        "confidence": confidence,
    }
