"""Net PnL and meta labels after trading costs (Bybit linear perps)."""

from __future__ import annotations

from typing import Optional, Tuple


def compute_net_pnl_pct(
    gross_pnl_pct: float,
    *,
    signal: str,
    horizon_hours: int = 24,
    funding_rate_pct: float = 0.0,
    assume_taker: bool = True,
    taker_fee_pct: float = 0.055,
    maker_fee_pct: float = 0.02,
) -> Tuple[float, float]:
    """
    Return (net_pnl_pct, costs_pct).

    gross_pnl_pct: price move % (entry to exit).
    funding_rate_pct: exchange funding rate in percent (e.g. 0.01 = 0.01%), per 8h period.
    Fees: round-trip = 2 × one-side fee.
    Funding: LONG pays when rate > 0; SHORT receives (cost sign flipped).
    """
    side = (signal or "").upper()
    if side not in ("LONG", "SHORT"):
        return 0.0, 0.0

    one_side = taker_fee_pct if assume_taker else maker_fee_pct
    fee_round_trip = 2.0 * one_side

    n_periods = max(int(horizon_hours) // 8, 0) if horizon_hours else 0
    # Signed funding cost as % of notional over hold (simplified: rate × periods)
    funding_cost = n_periods * funding_rate_pct
    if side == "SHORT":
        funding_cost = -funding_cost

    costs_pct = round(fee_round_trip + funding_cost, 4)
    net_pnl_pct = round(gross_pnl_pct - costs_pct, 4)
    return net_pnl_pct, costs_pct


def compute_label_meta(
    net_pnl_pct: float,
    min_edge_pct: float = 0.05,
) -> int:
    """1 if net PnL clears minimum edge threshold, else 0."""
    return 1 if net_pnl_pct >= min_edge_pct else 0


def load_cost_config(db_manager) -> dict:
    """Load fee/label settings from config table."""

    def _cfg(key: str, default: str) -> str:
        try:
            v = db_manager.get_config_value(key)
            return v if v is not None and str(v).strip() != "" else default
        except Exception:
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(_cfg(key, str(default)))
        except ValueError:
            return default

    return {
        "assume_taker": _cfg("META_LABEL_ASSUME_TAKER", "true").lower() == "true",
        "taker_fee_pct": _float("BYBIT_TAKER_FEE_PCT", 0.055),
        "maker_fee_pct": _float("BYBIT_MAKER_FEE_PCT", 0.02),
        "min_edge_pct": _float("META_LABEL_MIN_EDGE_PCT", 0.05),
    }
