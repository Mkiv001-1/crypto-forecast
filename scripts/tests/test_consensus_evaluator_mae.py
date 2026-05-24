"""Tests for MAE/MFE in consensus evaluator."""

from scripts.core.consensus_evaluator import _mae_mfe_for_eval


def test_mae_mfe_for_long_eval():
    mae, mfe = _mae_mfe_for_eval("LONG", 100.0, actual_high=103.0, actual_low=98.0)
    assert mae == 2.0
    assert mfe == 3.0
