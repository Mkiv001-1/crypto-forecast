"""Tests for MAE/MFE computation."""

from scripts.core.mae_mfe import compute_mae_mfe_pct


def test_long_mae_mfe():
    mae, mfe = compute_mae_mfe_pct("LONG", entry=100.0, actual_high=105.0, actual_low=97.0)
    assert mae == 3.0
    assert mfe == 5.0


def test_short_mae_mfe():
    mae, mfe = compute_mae_mfe_pct("SHORT", entry=100.0, actual_high=102.0, actual_low=94.0)
    assert mae == 2.0
    assert mfe == 6.0


def test_neutral_returns_none():
    assert compute_mae_mfe_pct("NEUTRAL", 100.0, 105.0, 95.0) == (None, None)
