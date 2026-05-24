"""Tests for fractional Kelly sizing helper."""

from scripts.core.kelly_sizing import fractional_kelly_fraction


def test_positive_edge():
    f = fractional_kelly_fraction(0.6, 2.0, kelly_fraction=0.25)
    assert f > 0


def test_no_edge_returns_zero():
    assert fractional_kelly_fraction(0.3, 1.0, kelly_fraction=0.25) == 0.0


def test_capped_at_one():
    f = fractional_kelly_fraction(0.9, 5.0, kelly_fraction=1.0)
    assert f <= 1.0
