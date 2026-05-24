"""Tests for consensus settings loading and regime overrides."""

import json

from scripts.core.consensus_settings import (
    FILTER_INSUFFICIENT_AGREEMENT,
    load_consensus_settings,
)


def test_load_defaults_without_db():
    s = load_consensus_settings(None, market_regime="RANGING")
    assert s.confidence_threshold == 55.0
    assert s.min_models_for_side == 2
    assert s.market_regime == "RANGING"


def test_load_from_db_and_regime_override(db_manager):
    db_manager.set_config_value("CONFIDENCE_THRESHOLD", "50")
    db_manager.set_config_value("MIN_MODELS_FOR_SIDE", "3")
    db_manager.set_config_value(
        "REGIME_CONSENSUS_OVERRIDES",
        json.dumps({"RANGING": {"confidence_threshold": 65, "min_models_for_side": 4}}),
    )
    s = load_consensus_settings(db_manager, market_regime="RANGING")
    assert s.confidence_threshold == 65.0
    assert s.min_models_for_side == 4
    assert s.regime_overrides_applied["confidence_threshold"] == 65.0


def test_weak_trend_uses_base_thresholds(db_manager):
    db_manager.set_config_value(
        "REGIME_CONSENSUS_OVERRIDES",
        json.dumps({"RANGING": {"confidence_threshold": 70}}),
    )
    s = load_consensus_settings(db_manager, market_regime="WEAK_TREND")
    assert s.confidence_threshold != 70.0
