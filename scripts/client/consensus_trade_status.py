"""Consensus trade-status helpers (GUI + tests)."""

from typing import Any, Optional


def parse_trade_id(value: Any) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return None
        parsed = int(value)
        if parsed <= 0:
            return None
        return parsed
    except Exception:
        return None


def compute_trade_status(
    *,
    trade_id: Optional[int],
    order_state: str,
    trade_row: Optional[dict],
) -> str:
    """
    Derive consensus Trade Status from DB fields and optional resolved trade row.

    - traded: trade_id points to an existing trades row
    - orphan: trade_id set but no trades row (stale or order id stored by mistake)
    - submitted: order submitted but no linked trade yet
    - pending / expired / skipped / new: order workflow states
    """
    order_state_u = str(order_state or "").upper()

    if trade_id is not None:
        if trade_row is not None:
            return "traded"
        return "orphan"

    if order_state_u == "ORDER_SUBMITTED":
        return "submitted"
    if order_state_u == "PENDING_ORDER":
        return "pending"
    if order_state_u == "EXPIRED":
        return "expired"
    if order_state_u == "ORDER_SKIPPED":
        return "skipped"
    return "new"
