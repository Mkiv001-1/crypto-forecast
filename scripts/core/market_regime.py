"""
Market regime detection based on ADX and moving averages.
Used to select the most appropriate forecast methods for current conditions.
"""

import logging

_METHODS_BY_REGIME = {
    "STRONG_UPTREND":   ["momentum_trend", "relative_strength", "volume_breakout"],
    "STRONG_DOWNTREND": ["momentum_trend", "relative_strength"],
    "RANGING":          ["mean_reversion", "price_action", "volatility"],
    "WEAK_TREND":       ["momentum_trend", "price_action", "mean_reversion",
                         "volatility", "relative_strength", "volume_breakout"],
}

ALL_METHODS = [
    "momentum_trend", "price_action", "relative_strength",
    "volatility", "mean_reversion", "volume_breakout",
]


def detect_regime(indicators: dict) -> str:
    """
    Detect market regime from calculated indicators.

    Returns one of: STRONG_UPTREND, STRONG_DOWNTREND, RANGING, WEAK_TREND
    """
    adx   = indicators.get("adx14", 0) or 0
    price = indicators.get("price", 0) or 0
    ma20  = indicators.get("ma20",  0) or 0
    ma50  = indicators.get("ma50",  0) or 0
    ma200 = indicators.get("ma200", 0) or 0

    if adx > 25:
        if ma20 > ma50 and ma50 > ma200 and price > ma20:
            regime = "STRONG_UPTREND"
        elif ma20 < ma50 and ma50 < ma200 and price < ma20:
            regime = "STRONG_DOWNTREND"
        else:
            regime = "WEAK_TREND"
    elif adx < 20:
        regime = "RANGING"
    else:
        regime = "WEAK_TREND"

    logging.info(f"📈 Market regime: {regime} (ADX={adx:.1f})")
    return regime


def get_methods_for_regime(regime: str) -> list:
    """Return the list of forecast methods appropriate for the given regime."""
    return _METHODS_BY_REGIME.get(regime, ALL_METHODS)
