"""Tests for fractional Kelly position sizing mode."""

from unittest.mock import patch

from scripts.core.position_sizer import calculate_position


def test_kelly_fractional_reduces_size(db_manager):
    with patch("scripts.core.position_sizer._get_str_risk_config", return_value="kelly_fractional"):
        with patch("scripts.core.position_sizer._cfg_risk") as mock_cfg:
            mock_cfg.side_effect = lambda _db, key, default: {
                "DEFAULT_RISK_PCT": 0.01,
                "MAX_POSITION_PCT": 0.5,
            }.get(key, default)
            base = calculate_position(
                "BTCUSDT",
                entry_price=100.0,
                stop_loss=95.0,
                db_manager=db_manager,
                net_liquidation=10000.0,
                win_rate=0.6,
                reward_risk=2.0,
            )
            zero_edge = calculate_position(
                "BTCUSDT",
                entry_price=100.0,
                stop_loss=95.0,
                db_manager=db_manager,
                net_liquidation=10000.0,
                win_rate=0.2,
                reward_risk=1.0,
            )
    assert base["status"] == "OK"
    assert base["quantity"] > 0
    assert zero_edge["status"] == "SKIPPED_ZERO_RISK"
