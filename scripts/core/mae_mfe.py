"""Maximum Adverse / Favorable Excursion helpers (percent of entry)."""

from __future__ import annotations

from typing import Optional, Tuple


def compute_mae_mfe_pct(
    signal: str,
    entry: float,
    actual_high: float,
    actual_low: float,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute MAE and MFE as positive percentages of entry price.

    LONG: MFE = (high - entry) / entry * 100, MAE = (entry - low) / entry * 100
    SHORT: MFE = (entry - low) / entry * 100, MAE = (high - entry) / entry * 100
    """
    if not entry or entry <= 0:
        return None, None
    side = str(signal or "").upper()
    if side not in ("LONG", "SHORT"):
        return None, None
    try:
        high = float(actual_high)
        low = float(actual_low)
    except (TypeError, ValueError):
        return None, None

    if side == "LONG":
        mfe = max(0.0, (high - entry) / entry * 100)
        mae = max(0.0, (entry - low) / entry * 100)
    else:
        mfe = max(0.0, (entry - low) / entry * 100)
        mae = max(0.0, (high - entry) / entry * 100)

    return round(mae, 4), round(mfe, 4)
