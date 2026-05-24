"""Tests for weighted consensus aggregation and filters."""

from scripts.core.consensus import calculate_consensus
from scripts.core.consensus_settings import (
    FILTER_HIGH_DISAGREEMENT,
    FILTER_INSUFFICIENT_AGREEMENT,
    FILTER_LOW_CONFIDENCE,
    FILTER_LOW_EXPECTED_R,
    ConsensusSettings,
)


def _forecast(side, confidence=80, method="momentum_trend", model="gpt-4o", price=100.0):
    return {
        "side": side,
        "confidence": confidence,
        "method": method,
        "model": model,
        "entry_limit_price": price,
        "target_price": price * 1.08 if side == "LONG" else price * 0.92,
        "stop_loss": price * 0.97 if side == "LONG" else price * 1.03,
    }


def test_empty_forecasts_neutral():
    r = calculate_consensus([])
    assert r["signal"] == "NEUTRAL"
    assert r["confidence"] == 0.0


def test_unanimous_long_signal():
    forecasts = [
        _forecast("LONG", model="m1"),
        _forecast("LONG", model="m2", method="price_action"),
    ]
    settings = ConsensusSettings(
        confidence_threshold=50,
        min_models_for_side=2,
        min_expected_r=0.1,
        disagreement_threshold=0.5,
    )
    r = calculate_consensus(
        forecasts,
        current_price=100.0,
        consensus_settings=settings,
    )
    assert r["signal"] == "LONG"
    assert r["models_long_count"] == 2
    assert r["filter_reasons"] == []


def test_insufficient_agreement_forces_neutral():
    forecasts = [
        _forecast("LONG", model="only_one"),
    ]
    settings = ConsensusSettings(
        confidence_threshold=50,
        min_models_for_side=2,
        min_expected_r=0.1,
    )
    r = calculate_consensus(forecasts, current_price=100.0, consensus_settings=settings)
    assert r["signal"] == "NEUTRAL"
    assert FILTER_INSUFFICIENT_AGREEMENT in r["filter_reasons"]


def test_high_disagreement_forces_neutral():
    forecasts = [
        _forecast("LONG", confidence=90, model="a"),
        _forecast("LONG", confidence=90, model="b"),
        _forecast("SHORT", confidence=85, model="c"),
        _forecast("SHORT", confidence=85, model="d"),
    ]
    settings = ConsensusSettings(
        confidence_threshold=50,
        min_models_for_side=2,
        disagreement_threshold=0.35,
        min_expected_r=0.1,
    )
    r = calculate_consensus(forecasts, current_price=100.0, consensus_settings=settings)
    assert r["signal"] == "NEUTRAL"
    assert FILTER_HIGH_DISAGREEMENT in r["filter_reasons"]
    assert r["high_model_disagreement"] is True


def test_low_confidence_filter():
    forecasts = [
        _forecast("LONG", confidence=59, model="a", method="m1"),
        _forecast("SHORT", confidence=82, model="c", method="m2"),
    ]
    method_stats = {
        "m1": {"win_rate": 1.0},
        "m2": {"win_rate": 0.5},
    }
    settings = ConsensusSettings(
        confidence_threshold=60,
        min_models_for_side=1,
        min_expected_r=0.1,
        disagreement_threshold=0.5,
    )
    r = calculate_consensus(
        forecasts,
        current_price=100.0,
        consensus_settings=settings,
        method_stats=method_stats,
    )
    assert r["signal"] == "NEUTRAL"
    assert FILTER_LOW_CONFIDENCE in r["filter_reasons"]


def test_low_expected_r_filter():
    forecasts = [
        _forecast("LONG", confidence=60, model="a"),
        _forecast("LONG", confidence=60, model="b"),
    ]
    for f in forecasts:
        f["target_price"] = 100.5
        f["stop_loss"] = 99.0
    settings = ConsensusSettings(
        confidence_threshold=50,
        min_models_for_side=2,
        min_expected_r=2.0,
    )
    r = calculate_consensus(forecasts, current_price=100.0, consensus_settings=settings)
    assert r["signal"] == "NEUTRAL"
    assert FILTER_LOW_EXPECTED_R in r["filter_reasons"]


def test_active_settings_exposed_in_result():
    settings = ConsensusSettings(confidence_threshold=61, min_models_for_side=2, min_expected_r=0.1)
    r = calculate_consensus(
        [_forecast("LONG", model="a"), _forecast("LONG", model="b")],
        current_price=100.0,
        consensus_settings=settings,
    )
    assert r["active_settings"]["confidence_threshold"] == 61


def test_save_consensus_persists_transparency_fields(db_manager):
    from scripts.core.consensus import save_consensus

    consensus = {
        "signal": "LONG",
        "confidence": 70.0,
        "methods_long": "m(a)",
        "methods_short": "",
        "methods_neutral": "",
        "rationale": "test",
        "target_price": 110.0,
        "stop_loss": 95.0,
        "entry_limit_price": 100.0,
        "high_model_disagreement": False,
        "filter_reasons_json": "[]",
        "models_long_count": 2,
        "models_short_count": 0,
        "minority_weight_pct": 5.0,
        "expected_r": 1.2,
        "active_settings_json": '{"confidence_threshold": 55}',
        "market_regime": "RANGING",
        "_forecast_link_data": [],
    }
    ok = save_consensus(db_manager, "BTCUSDT", consensus, override_date="2025-01-15")
    assert ok is True
    with db_manager._connect() as con:
        row = con.execute(
            "SELECT market_regime, models_long_count, expected_r, filter_reasons "
            "FROM consensus WHERE ticker=? ORDER BY id DESC LIMIT 1",
            ("BTCUSDT",),
        ).fetchone()
    assert row[0] == "RANGING"
    assert row[1] == 2
    assert float(row[2]) == 1.2
