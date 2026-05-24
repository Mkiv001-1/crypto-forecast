"""Fractional Kelly Criterion for position size scaling."""

from __future__ import annotations

from typing import Optional


def fractional_kelly_fraction(
    win_rate: float,
    reward_risk: float,
    kelly_fraction: float = 0.25,
) -> float:
    """
    Full Kelly: f* = (p*b - q) / b, where p=win_rate, q=1-p, b=reward/risk.
    Returns fractional Kelly capped to [0, 1].

    win_rate and reward_risk are fractions (e.g. 0.55 and 2.0).
    """
    try:
        p = float(win_rate)
        b = float(reward_risk)
        kf = float(kelly_fraction)
    except (TypeError, ValueError):
        return 0.0
    if p <= 0 or p >= 1 or b <= 0 or kf <= 0:
        return 0.0
    q = 1.0 - p
    full_kelly = (p * b - q) / b
    if full_kelly <= 0:
        return 0.0
    return min(1.0, full_kelly * kf)
