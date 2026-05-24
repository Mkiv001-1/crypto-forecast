"""
Bybit instrument lot/price filters — quantize qty and prices for order API.

Bybit rejects orders when qty is not a multiple of qtyStep (ErrCode 10001).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional, Tuple


def decimals_from_step(step: float) -> int:
    """Number of decimal places implied by a step/tick size (e.g. 0.01 → 2)."""
    if step <= 0:
        return 8
    d = Decimal(str(step)).normalize()
    exp = d.as_tuple().exponent
    return max(0, -exp)


def quantize_qty(qty: float, qty_step: float, *, round_down: bool = True) -> float:
    """Snap quantity to qtyStep (floor by default — do not exceed risk budget)."""
    if qty_step <= 0:
        return qty
    units = qty / qty_step
    if round_down:
        units = math.floor(units + 1e-12)
    else:
        units = round(units)
    result = units * qty_step
    return round(result, decimals_from_step(qty_step))


def quantize_price(price: float, tick_size: float) -> float:
    """Snap price to tickSize (nearest tick)."""
    if tick_size <= 0:
        return price
    units = round(price / tick_size)
    result = units * tick_size
    return round(result, decimals_from_step(tick_size))


def format_bybit_decimal(value: float, step: float) -> str:
    """Format a value for Bybit API string fields (no float noise)."""
    prec = decimals_from_step(step)
    if prec == 0:
        return str(int(round(value)))
    return f"{value:.{prec}f}"


def normalize_order_params(
    qty: float,
    *,
    qty_step: float,
    min_order_qty: float,
    max_order_qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    entry_price: Optional[float] = None,
    tick_size: float = 0,
) -> Tuple[float, Optional[float], Optional[float], Optional[float]]:
    """
    Quantize qty and prices to instrument filters.

    Returns (qty, entry_price, stop_loss, take_profit).
    Raises ValueError if qty is below min after quantization.
    """
    qty = quantize_qty(qty, qty_step)
    if qty < min_order_qty:
        raise ValueError(
            f"quantity {qty} below minOrderQty {min_order_qty} (step={qty_step})"
        )
    if max_order_qty > 0 and qty > max_order_qty:
        qty = quantize_qty(max_order_qty, qty_step, round_down=True)

    sl = quantize_price(stop_loss, tick_size) if stop_loss is not None and tick_size > 0 else stop_loss
    tp = quantize_price(take_profit, tick_size) if take_profit is not None and tick_size > 0 else take_profit
    entry = (
        quantize_price(entry_price, tick_size)
        if entry_price is not None and tick_size > 0
        else entry_price
    )
    return qty, entry, sl, tp
