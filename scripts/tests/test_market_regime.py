"""Tests for market regime detection and prompt context formatting."""

from scripts.core.market_regime import (
    classify_adx_strength,
    classify_ma_structure,
    detect_regime,
    format_regime_context,
    get_regime_rationale,
)


def test_classify_adx_strength():
    assert "боковик" in classify_adx_strength(15)
    assert "умеренное" in classify_adx_strength(22)
    assert "сильное" in classify_adx_strength(29.2)
    assert "очень сильное" in classify_adx_strength(45)


def test_classify_ma_structure():
    assert "бычий" in classify_ma_structure(110, 100, 90)
    assert "медвежий" in classify_ma_structure(90, 100, 110)
    assert "смешанная" in classify_ma_structure(110, 100, 105)


def test_weak_trend_with_high_adx_when_price_below_ma20():
    """Bullish MA stack but price below MA20 → WEAK_TREND despite ADX>25."""
    indicators = {
        "adx14": 29.2,
        "price": 100,
        "ma20": 105,
        "ma50": 100,
        "ma200": 95,
    }
    assert detect_regime(indicators) == "WEAK_TREND"


def test_weak_trend_with_high_adx_when_ma_mixed():
    indicators = {
        "adx14": 29.2,
        "price": 100,
        "ma20": 100,
        "ma50": 105,
        "ma200": 102,
    }
    assert detect_regime(indicators) == "WEAK_TREND"


def test_strong_uptrend_requires_full_alignment():
    indicators = {
        "adx14": 29.2,
        "price": 110,
        "ma20": 105,
        "ma50": 100,
        "ma200": 95,
    }
    assert detect_regime(indicators) == "STRONG_UPTREND"


def test_format_regime_context_explains_high_adx_weak_trend():
    indicators = {
        "adx14": 29.2,
        "price": 100,
        "ma20": 100,
        "ma50": 105,
        "ma200": 102,
        "market_regime": "WEAK_TREND",
    }
    ctx = format_regime_context(indicators, method="price_action")

    assert ctx["market_regime"] == "WEAK_TREND"
    assert "сильное" in ctx["adx_strength"]
    assert "смешанная" in ctx["ma_structure"]
    assert "ADX>25" in ctx["regime_rationale"]
    assert "WEAK_TREND" in ctx["regime_block"]
    assert "29.2" in ctx["regime_block"]
    assert ctx["regime_method_hint"]
    assert "price_action" not in ctx["regime_method_hint"].lower()


def test_get_regime_rationale_ranging():
    text = get_regime_rationale("RANGING", 18, "смешанная", 100, 101)
    assert "ADX<20" in text
