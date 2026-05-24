"""Tests for meta-label net PnL calculations."""

import pytest

from scripts.core.meta_label.net_pnl import (
    compute_label_meta,
    compute_net_pnl_pct,
)


def test_net_pnl_long_taker_fees_only():
    gross = 1.0
    net, costs = compute_net_pnl_pct(
        gross,
        signal="LONG",
        horizon_hours=4,
        funding_rate_pct=0.0,
        assume_taker=True,
        taker_fee_pct=0.055,
    )
    assert costs == pytest.approx(0.11, abs=1e-4)
    assert net == pytest.approx(0.89, abs=1e-4)


def test_net_pnl_short_funding_positive_rate():
    gross = 2.0
    net, costs = compute_net_pnl_pct(
        gross,
        signal="SHORT",
        horizon_hours=16,
        funding_rate_pct=0.01,
        assume_taker=True,
        taker_fee_pct=0.055,
    )
    # 2 periods × 0.01 funding, short receives → negative cost component
    assert costs == pytest.approx(0.11 - 0.02, abs=1e-4)
    assert net == pytest.approx(gross - costs, abs=1e-4)


def test_label_meta_threshold():
    assert compute_label_meta(0.10, min_edge_pct=0.05) == 1
    assert compute_label_meta(0.04, min_edge_pct=0.05) == 0


def test_neutral_signal_zero_costs():
    net, costs = compute_net_pnl_pct(5.0, signal="NEUTRAL", horizon_hours=24)
    assert net == 0.0
    assert costs == 0.0
