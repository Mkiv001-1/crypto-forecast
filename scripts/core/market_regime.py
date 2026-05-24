"""
Market regime detection based on ADX and moving averages.
Used to select the most appropriate forecast methods for current conditions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_METHODS_BY_REGIME = {
    "STRONG_UPTREND":   ["momentum_trend", "relative_strength", "volume_breakout"],
    "STRONG_DOWNTREND": ["momentum_trend", "relative_strength"],
    "RANGING":          ["mean_reversion", "price_action", "volatility"],
    "WEAK_TREND":       ["momentum_trend", "price_action", "mean_reversion",
                         "volatility", "relative_strength", "volume_breakout"],
}

ALL_METHODS = [
    "momentum_trend", "price_action", "relative_strength",
    "volatility", "mean_reversion", "volume_breakout",
]

_METHOD_HINTS: Dict[str, Dict[str, str]] = {
    "momentum_trend": {
        "STRONG_UPTREND":    "Оптимальные условия: агрессивные трендовые сигналы по направлению MA-структуры.",
        "STRONG_DOWNTREND":  "Оптимальные условия: агрессивные трендовые сигналы по направлению MA-структуры.",
        "WEAK_TREND":        "ADX может быть высоким, но структура неоднозначна — снижай confidence на 10–15 п.п., требуй ≥3 подтверждения.",
        "RANGING":           "Боковик — избегай трендовых сделок, предпочитай NEUTRAL.",
    },
    "price_action": {
        "STRONG_UPTREND":    "Price action — точки входа по тренду; не торгуй SHORT против бычьей MA-структуры.",
        "STRONG_DOWNTREND":  "Price action — точки входа по тренду; не торгуй LONG против медвежьей MA-структуры.",
        "WEAK_TREND":        "Паттерны у уровней ненадёжны; требуй подтверждения 2–3 свечами и согласованности RSI/BB.",
        "RANGING":           "Приоритет отскоков от BB/MA; ищи разворотные свечи у границ диапазона.",
    },
    "relative_strength": {
        "STRONG_UPTREND":    "Сравни с BTC/ETH: опережение бенчмарка усиливает LONG-сигнал.",
        "STRONG_DOWNTREND":  "Сравни с BTC/ETH: отставание от бенчмарка усиливает SHORT-сигнал.",
        "WEAK_TREND":        "При смешанной MA-структуре снижай confidence при расхождении периодов 5д/20д/50д.",
        "RANGING":           "Относительная сила менее надёжна в боковике — требуй vol_ratio>1.2.",
    },
    "volatility": {
        "STRONG_UPTREND":    "Торгуй пробой по направлению тренда; ложные пробои против MA-структуры — NEUTRAL.",
        "STRONG_DOWNTREND":  "Торгуй пробой по направлению тренда; ложные пробои против MA-структуры — NEUTRAL.",
        "WEAK_TREND":        "BB-сжатие + рост ADX — жди направленного пробоя; без подтверждения свечой — NEUTRAL.",
        "RANGING":           "Основной сценарий: BB-сжатие → пробой; при ADX<20 ложные пробои чаще.",
    },
    "mean_reversion": {
        "STRONG_UPTREND":    "Mean reversion против тренда опасен — снижай confidence, при ADX>30 предпочитай NEUTRAL.",
        "STRONG_DOWNTREND":  "Mean reversion против тренда опасен — снижай confidence, при ADX>30 предпочитай NEUTRAL.",
        "WEAK_TREND":        "Возможны откаты к MA20; при ADX>25 снижай confidence, при ADX>35 — NEUTRAL.",
        "RANGING":           "Оптимальные условия: отклонения от MA20/BB с осцилляторным подтверждением.",
    },
    "volume_breakout": {
        "STRONG_UPTREND":    "Объёмный пробой по направлению тренда — высокий confidence при vol_ratio>2.",
        "STRONG_DOWNTREND":  "Объёмный пробой по направлению тренда — высокий confidence при vol_ratio>2.",
        "WEAK_TREND":        "Требуй vol_ratio>2.5 и закрытие за ключевым уровнем; иначе NEUTRAL.",
        "RANGING":           "Объём без тренда (ADX<20) — пробой ненадёжен, vol_ratio>2 обязателен.",
    },
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def classify_adx_strength(adx: float) -> str:
    """Pure ADX-based strength label (independent of market_regime)."""
    if adx < 20:
        return "боковик (слабое направленное движение)"
    if adx <= 25:
        return "умеренное (переходная зона)"
    if adx <= 40:
        return "сильное направленное движение"
    return "очень сильное направленное движение"


def classify_ma_structure(ma20: float, ma50: float, ma200: float) -> str:
    if ma20 > ma50 and ma50 > ma200:
        return "бычий стек (MA20>MA50>MA200)"
    if ma20 < ma50 and ma50 < ma200:
        return "медвежий стек (MA20<MA50<MA200)"
    return "смешанная (MA не выстроены)"


def get_regime_rationale(
    regime: str,
    adx: float,
    ma_structure: str,
    price: float,
    ma20: float,
) -> str:
    if regime == "STRONG_UPTREND":
        return "ADX>25 + бычий стек MA + цена выше MA20"
    if regime == "STRONG_DOWNTREND":
        return "ADX>25 + медвежий стек MA + цена ниже MA20"
    if regime == "RANGING":
        return "ADX<20 — боковик, трендовые сигналы ненадёжны"
    if adx > 25:
        parts = ["ADX>25, но MA не выстроены в бычий/медвежий стек"]
        if "бычий" in ma_structure and price <= ma20:
            parts.append("цена ниже MA20 при частично бычьей структуре")
        elif "медвежий" in ma_structure and price >= ma20:
            parts.append("цена выше MA20 при частично медвежьей структуре")
        return "; ".join(parts)
    return "ADX 20–25 — переходная зона без чёткой MA-структуры"


def get_regime_method_hint(regime: str, method: Optional[str]) -> str:
    if not method:
        return ""
    hints = _METHOD_HINTS.get(method, {})
    return hints.get(regime, hints.get("WEAK_TREND", ""))


def detect_regime(indicators: dict) -> str:
    """
    Detect market regime from calculated indicators.

    Returns one of: STRONG_UPTREND, STRONG_DOWNTREND, RANGING, WEAK_TREND
    """
    adx   = _f(indicators.get("adx14"))
    price = _f(indicators.get("price"))
    ma20  = _f(indicators.get("ma20"))
    ma50  = _f(indicators.get("ma50"))
    ma200 = _f(indicators.get("ma200"))

    if adx > 25:
        if ma20 > ma50 and ma50 > ma200 and price > ma20:
            regime = "STRONG_UPTREND"
        elif ma20 < ma50 and ma50 < ma200 and price < ma20:
            regime = "STRONG_DOWNTREND"
        else:
            regime = "WEAK_TREND"
    elif adx < 20:
        regime = "RANGING"
    else:
        regime = "WEAK_TREND"

    logging.info(f"📈 Market regime: {regime} (ADX={adx:.1f})")
    return regime


def format_regime_context(indicators: dict, method: Optional[str] = None) -> dict:
    """
    Build human-readable regime fields for prompt templates.

    Returns dict with: market_regime, regime_rationale, adx_strength, ma_structure,
    price_vs_ma20, regime_block, regime_method_hint, adx (float).
    """
    adx   = _f(indicators.get("adx14"))
    price = _f(indicators.get("price"))
    ma20  = _f(indicators.get("ma20"))
    ma50  = _f(indicators.get("ma50"))
    ma200 = _f(indicators.get("ma200"))

    regime = indicators.get("market_regime") or detect_regime(indicators)
    adx_strength = classify_adx_strength(adx)
    ma_structure = classify_ma_structure(ma20, ma50, ma200)
    price_vs_ma20 = "выше MA20" if price > ma20 else ("ниже MA20" if price < ma20 else "на MA20")
    regime_rationale = get_regime_rationale(regime, adx, ma_structure, price, ma20)
    regime_method_hint = get_regime_method_hint(regime, method)

    regime_block = (
        "РЕЖИМ РЫНКА (системная классификация):\n"
        f"- Режим: {regime} — {regime_rationale}\n"
        f"- Сила движения (ADX): {adx_strength} (ADX={adx:.1f}; "
        "<20 боковик, 20–25 переход, >25 направленное движение)\n"
        f"- Структура MA: {ma_structure}\n"
        f"  MA20=${ma20:.2f} MA50=${ma50:.2f} MA200=${ma200:.2f} | "
        f"Цена ${price:.2f}, {price_vs_ma20}\n"
        "ГЛОССАРИЙ: STRONG_UP/DOWN = ADX>25 + выровненные MA + цена по сторону тренда; "
        "WEAK_TREND = ADX 20–25 ИЛИ ADX>25 без чистого MA-стека (не «слабый ADX»); "
        "RANGING = ADX<20."
    )

    return {
        "market_regime":      regime,
        "regime_rationale":   regime_rationale,
        "adx_strength":       adx_strength,
        "ma_structure":       ma_structure,
        "price_vs_ma20":      price_vs_ma20,
        "regime_block":       regime_block,
        "regime_method_hint": regime_method_hint,
        "adx":                adx,
    }


def get_methods_for_regime(regime: str) -> list:
    """Return the list of forecast methods appropriate for the given regime."""
    return _METHODS_BY_REGIME.get(regime, ALL_METHODS)
