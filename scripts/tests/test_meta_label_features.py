"""Tests for meta-label feature builder."""

from scripts.core.meta_label.features import FEATURE_NAMES, build_meta_features, features_to_vector


def test_build_meta_features_keys():
    feats = build_meta_features(
        consensus={
            "signal": "LONG",
            "confidence": 70.0,
            "expected_r": 1.2,
            "target_price": 110.0,
            "stop_loss": 95.0,
            "horizon_hours": 24,
        },
        indicators={
            "price": 100.0,
            "rsi14": 55.0,
            "adx14": 25.0,
            "atr14": 2.0,
            "bb_upper": 105.0,
            "bb_lower": 95.0,
            "macd_hist": 0.5,
            "volume_avg_20": 1000.0,
            "volume_current": 1200.0,
        },
        price_data=[
            {"open": 98, "high": 101, "low": 97, "close": 100, "volume": 1000},
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1100},
        ],
        sector="DeFi",
    )
    assert set(feats.keys()) == set(FEATURE_NAMES)
    assert feats["signal_is_long"] == 1.0
    vec = features_to_vector(feats)
    assert len(vec) == len(FEATURE_NAMES)
