"""
Генерация прогнозов с использованием Perplexity API
"""

import requests
import json
import re
import logging
from datetime import datetime, timedelta

def format_number(num):
    """Форматирует большие числа для удобного отображения"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(int(num))

def get_method_instructions(method, ind, atr_percent):
    """Возвращает инструкции для конкретного метода анализа."""
    bb = ind.get('bb', {}) if isinstance(ind.get('bb'), dict) else {}
    bb_upper = ind.get('bb_upper') or bb.get('upper', 0)
    bb_lower = ind.get('bb_lower') or bb.get('lower', 0)
    ma20     = ind.get('ma20', 0) or 1  # avoid division by zero
    vol_ratio = (ind.get('volume_current', 0) / ind.get('volume_avg_20', 1)
                 if ind.get('volume_avg_20') else 0)

    instructions = {
        'momentum_trend': f"""
Метод: MOMENTUM TREND
- Тренд: MA20={ind.get('ma20',0):.2f} MA50={ind.get('ma50',0):.2f} MA200={ind.get('ma200',0):.2f}
- EMA9={ind.get('ema9',0):.2f} vs EMA21={ind.get('ema21',0):.2f}
- ADX={ind.get('adx14',0):.1f} (тренд {'сильный' if ind.get('adx14',0)>25 else 'слабый'})
- MACD hist={ind.get('macd_hist',0):+.2f}
- RSI={ind.get('rsi14',0):.1f} | OBV={'растет' if ind.get('obv',0)>0 else 'падает'}
Определи направление тренда и силу импульса. Используй выравнивание MA и ADX.
        """,

        'price_action': f"""
Метод: PRICE ACTION
- Цена: {ind.get('price',0):.2f} | BB верхняя: {bb_upper:.2f} нижняя: {bb_lower:.2f}
- Stoch RSI: {ind.get('stoch_rsi',0):.2f} | RSI: {ind.get('rsi14',0):.1f}
- ATR: {atr_percent:.1f}%
- Динамика: 5д={ind.get('change_5d',0):+.1f}% 20д={ind.get('change_20d',0):+.1f}%
Оцени уровни поддержки/сопротивления, перекупленность и свечные паттерны.
        """,

        'relative_strength': f"""
Метод: RELATIVE STRENGTH
- RSI={ind.get('rsi14',0):.1f} | ADX={ind.get('adx14',0):.1f}
- Динамика: 5д={ind.get('change_5d',0):+.1f}% 10д={ind.get('change_10d',0):+.1f}% 20д={ind.get('change_20d',0):+.1f}% 50д={ind.get('change_50d',0):+.1f}%
- Объемы: {format_number(ind.get('volume_current',0))} ({vol_ratio:.1f}x среднего)
Оцени относительную силу актива vs BTC/ETH (см. рыночный контекст), динамику тренда.
        """,

        'volatility': f"""
Метод: VOLATILITY BREAKOUT
- ATR: ${ind.get('atr14',0):.2f} ({atr_percent:.1f}%)
- BB: [{bb_lower:.2f} — {bb_upper:.2f}] ширина {bb_upper-bb_lower:.2f}
- RSI={ind.get('rsi14',0):.1f} | ADX={ind.get('adx14',0):.1f}
Оцени режим волатильности, риск пробоя Bollinger Bands.
        """,

        'mean_reversion': f"""
Метод: MEAN REVERSION
- Цена: {ind.get('price',0):.2f} | MA20: {ma20:.2f} (откл. {((ind.get('price',0)/ma20)-1)*100:.1f}%)
- MA50: {ind.get('ma50',0):.2f} | MA200: {ind.get('ma200',0):.2f}
- RSI={ind.get('rsi14',0):.1f} | Stoch RSI={ind.get('stoch_rsi',0):.2f}
Оцени вероятность возврата цены к MA20/MA50. Ищи дивергенции.
        """,

        'volume_breakout': f"""
Метод: VOLUME BREAKOUT
- Цена: {ind.get('price',0):.2f} | Объем: {format_number(ind.get('volume_current',0))} ({vol_ratio:.1f}x)
- OBV тренд: {'↑ бычий накопление' if ind.get('obv',0)>0 else '↓ медвежье распределение'}
- ATR={atr_percent:.1f}% | ADX={ind.get('adx14',0):.1f}
Оцени силу объемного импульса и вероятность пробоя ключевого уровня.
        """
    }

    return instructions.get(method, instructions['momentum_trend'])

_ADVERSARIAL_SECTION = """
ПЕРЕД ФИНАЛЬНЫМ ВЕРДИКТОМ (adversarial reasoning):
1. Сначала аргументируй сценарий SHORT (почему цена может упасть).
2. Затем аргументируй сценарий LONG (почему цена может вырасти).
3. Только после этого вынеси итоговый side и confidence, взвесив оба сценария.
"""

_PROMPT_FOOTER = """
ОТВЕЧАЙ СТРОГО В ФОРМАТЕ JSON:
{
    "confidence": число от 0 до 100,
    "side": "LONG" или "SHORT" или "NEUTRAL",
    "entry_order_type": "LMT",
    "entry_limit_price": число (цена лимитного входа, например 150.50),
    "entry_tif": "GTC",
    "target_price": число (цена тейк-профита, например 160.00),
    "take_profit_tif": "GTC",
    "stop_loss": число (цена стоп-лосса, например 145.00),
    "stop_loss_tif": "GTC",
    "timeframe_hours": целое число (ожидаемый горизонт в часах, например 24),
    "rationale": "подробное обоснование прогноза"
}

Требования:
- confidence реалистичный (не более 80 без явных сигналов)
- entry_limit_price — ДОЛЖЕН быть в диапазоне ±5% от текущей цены из раздела ТЕХНИЧЕСКИЕ ДАННЫЕ выше. НЕ ИСПОЛЬЗУЙ цены из памяти модели.
- stop_loss — ДОЛЖЕН быть в диапазоне ±10% от текущей цены. Для LONG: ниже entry. Для SHORT: выше entry.
- target_price — ДОЛЖЕН быть в диапазоне ±15% от текущей цены. Минимум 1.5x R/R от стопа.
- ВСЕ три цены ВЫЧИСЛЯЙ от текущей цены (указана в ТЕХНИЧЕСКИЕ ДАННЫЕ), а не из своей памяти.
- timeframe_hours — реалистичный горизонт для данного метода анализа
- rationale — детальный анализ с обоснованием уровней"""


def _prompt_footer(db_manager=None) -> str:
    """Return prompt footer, optionally with adversarial reasoning section."""
    footer = _PROMPT_FOOTER
    if db_manager is None:
        return footer
    try:
        from scripts.core.consensus_settings import load_consensus_settings

        if load_consensus_settings(db_manager).adversarial_prompt_enabled:
            return _ADVERSARIAL_SECTION + footer
    except Exception:
        pass
    return footer


def build_prompt(db_manager, ticker, ind, method, price_data=None):
    """Build prompt from DB template if available, else fallback.
    
    Args:
        db_manager: Database manager instance
        ticker: Stock ticker symbol
        ind: Technical indicators dict (may include 'price_data' key)
        method: Forecast method name
        price_data: Optional list of OHLCV candles to include in prompt
    """
    # Pass price_data through indicators dict for backward compatibility
    if price_data and 'price_data' not in ind:
        ind = dict(ind)
        ind['price_data'] = price_data
    
    template = None
    if db_manager:
        try:
            template = db_manager.get_prompt_template(method)
        except Exception:
            pass

    if not template:
        return build_prompt_fallback(ticker, ind, method, db_manager=db_manager)

    from scripts.core.multi_model_forecaster import _METHOD_HORIZON_HOURS
    horizon_hours = _METHOD_HORIZON_HOURS.get(method, 24)
    horizon = max(1, round(horizon_hours / 24))
    forecast_date = (datetime.now() + timedelta(hours=horizon_hours)).strftime('%Y-%m-%d')

    atr_percent = (ind['atr14'] / ind['price'] * 100) if ind.get('price') else 0
    bb = ind.get('bb', {}) if isinstance(ind.get('bb'), dict) else {}
    bb_upper = bb.get('upper') or ind.get('bb_upper', 0)
    bb_lower = bb.get('lower') or ind.get('bb_lower', 0)
    bb_pos = 0
    if bb_upper > bb_lower:
        bb_pos = (ind['price'] - bb_lower) / (bb_upper - bb_lower) * 100
    vol_ratio = (ind['volume_current'] / ind['volume_avg_20']
                 if ind.get('volume_avg_20') and ind['volume_avg_20'] > 0 else 0)
    ma20 = ind.get('ma20', 1) or 1
    ma20_dev = ((ind.get('price', 0) / ma20) - 1) * 100

    mkt_ctx = ""
    try:
        from scripts.core.market_context import fetch_market_context, format_market_context
        mkt_ctx = format_market_context(fetch_market_context(db_manager))
    except Exception:
        pass

    history = ""
    if db_manager:
        try:
            from scripts.core.unified_logs_manager import get_forecast_statistics
            stats = get_forecast_statistics(db_manager, days_back=30)
            m_stats = stats.get("methods", {}).get(method, {})
            if m_stats:
                wr = stats.get("accuracy", {}).get(method, 0)
                history = (
                    f"\nИСТОРИЯ МЕТОДА {method.upper()} (30 дней):\n"
                    f"- Win rate: {wr:.0f}% ({m_stats.get('total', 0)} прогнозов)\n"
                    f"- Средний PnL: {stats.get('avg_pnl', 0) or 0:+.2f}%\n"
                )
        except Exception:
            pass

    def _fmt(v, default=0):
        try:
            return float(v)
        except Exception:
            return default

    from scripts.core.market_regime import format_regime_context
    regime_ctx = format_regime_context(ind, method=method)

    ctx = {
        "ticker":         ticker,
        "forecast_date":  forecast_date,
        "horizon":        horizon,
        "market_regime":  regime_ctx["market_regime"],
        "regime_rationale":   regime_ctx["regime_rationale"],
        "adx_strength":       regime_ctx["adx_strength"],
        "ma_structure":       regime_ctx["ma_structure"],
        "price_vs_ma20":      regime_ctx["price_vs_ma20"],
        "regime_block":       regime_ctx["regime_block"],
        "regime_method_hint": regime_ctx["regime_method_hint"],
        "market_context": mkt_ctx,
        "history":        history,
        "footer":         _prompt_footer(db_manager),
        "recent_candles": _format_recent_candles(ind.get('price_data', []), num_candles=5),
        "price":          _fmt(ind.get('price')),
        "ma20":           _fmt(ind.get('ma20')),
        "ma50":           _fmt(ind.get('ma50')),
        "ma200":          _fmt(ind.get('ma200')),
        "ema9":           _fmt(ind.get('ema9')),
        "ema21":          _fmt(ind.get('ema21')),
        "rsi":            _fmt(ind.get('rsi14')),
        "adx":            _fmt(ind.get('adx14')),
        "macd":           _fmt(ind.get('macd')),
        "macd_hist":      _fmt(ind.get('macd_hist')),
        "stoch_rsi":      _fmt(ind.get('stoch_rsi')),
        "atr":            _fmt(ind.get('atr14')),
        "atr_pct":        atr_percent,
        "bb_upper":       bb_upper,
        "bb_lower":       bb_lower,
        "bb_pos":         bb_pos,
        "bb_width":       bb_upper - bb_lower,
        "obv_trend":      "↑ бычий накопление" if _fmt(ind.get('obv')) > 0 else "↓ медвежье распределение",
        "change_5d":      _fmt(ind.get('change_5d')),
        "change_10d":     _fmt(ind.get('change_10d')),
        "change_20d":     _fmt(ind.get('change_20d')),
        "change_50d":     _fmt(ind.get('change_50d')),
        "volume_current": format_number(_fmt(ind.get('volume_current'))),
        "vol_ratio":      vol_ratio,
        "ma20_dev":       ma20_dev,
        "bb_width_pct":   (bb_upper - bb_lower) / ind.get('price', 1) * 100 if ind.get('price') else 0,
        "atr_stop_15":    _fmt(ind.get('price')) * atr_percent / 100 * 1.5,
        "atr_stop_20":    _fmt(ind.get('price')) * atr_percent / 100 * 2.0,
        "price_m2":       _fmt(ind.get('price')) * 0.98,
        "price_p2":       _fmt(ind.get('price')) * 1.02,
        "price_m3":       _fmt(ind.get('price')) * 0.97,
        "price_p3":       _fmt(ind.get('price')) * 1.03,
        "price_m5":       _fmt(ind.get('price')) * 0.95,
        "price_p5":       _fmt(ind.get('price')) * 1.05,
        "price_m8":       _fmt(ind.get('price')) * 0.92,
        "price_p8":       _fmt(ind.get('price')) * 1.08,
        "price_m10":      _fmt(ind.get('price')) * 0.90,
        "price_p10":      _fmt(ind.get('price')) * 1.10,
        "price_m15":      _fmt(ind.get('price')) * 0.85,
        "price_p15":      _fmt(ind.get('price')) * 1.15,
    }
    try:
        return template.format_map(ctx)
    except Exception as e:
        logging.warning(f"Template format error for {method}: {e}, using fallback")
        return build_prompt_fallback(ticker, ind, method, db_manager=db_manager)

def _format_recent_candles(price_data, num_candles=5):
    """Format recent OHLCV candles for prompt inclusion."""
    if not price_data or len(price_data) == 0:
        return "Нет данных о свечах"
    
    candles = price_data[-num_candles:] if len(price_data) >= num_candles else price_data
    lines = []
    for c in reversed(candles):  # Most recent first
        date_str = c.get('date', 'N/A')
        if hasattr(date_str, 'strftime'):
            date_str = date_str.strftime('%Y-%m-%d')
        lines.append(
            f"  {date_str}: O={c['open']:.2f} H={c['high']:.2f} L={c['low']:.2f} "
            f"C={c['close']:.2f} V={c['volume']/1_000_000:.1f}M"
        )
    return "\n".join(lines)


def build_prompt_fallback(ticker, ind, method, db_manager=None):
    """Build enriched forecast prompt with extended indicators and market context."""
    from scripts.core.multi_model_forecaster import _METHOD_HORIZON_HOURS
    horizon_hours = _METHOD_HORIZON_HOURS.get(method, 24)
    horizon = max(1, round(horizon_hours / 24))
    forecast_date = (datetime.now() + timedelta(hours=horizon_hours)).strftime('%Y-%m-%d')
    data_date = datetime.now().strftime('%Y-%m-%d')  # Date when data was collected
    
    # Get price data for recent candles display
    price_data = ind.get('price_data', []) if isinstance(ind, dict) else []

    atr_percent = (ind['atr14'] / ind['price'] * 100) if ind.get('price') else 0
    bb = ind.get('bb', {}) if isinstance(ind.get('bb'), dict) else {}
    bb_upper = bb.get('upper') or ind.get('bb_upper', 0)
    bb_lower = bb.get('lower') or ind.get('bb_lower', 0)
    bb_position = 0
    if bb_upper > bb_lower:
        bb_position = (ind['price'] - bb_lower) / (bb_upper - bb_lower) * 100
    volume_ratio = (ind['volume_current'] / ind['volume_avg_20']
                    if ind.get('volume_avg_20') and ind['volume_avg_20'] > 0 else 0)

    # Market context
    mkt_ctx = ""
    try:
        from scripts.core.market_context import fetch_market_context, format_market_context
        ctx = fetch_market_context(db_manager)
        mkt_ctx = format_market_context(ctx)
    except Exception:
        mkt_ctx = ""

    # Performance history for this method
    hist_section = ""
    if db_manager:
        try:
            from scripts.core.unified_logs_manager import get_forecast_statistics
            stats = get_forecast_statistics(db_manager, days_back=30)
            m_stats = stats.get("methods", {}).get(method, {})
            if m_stats:
                accuracy = stats.get("accuracy", {})
                wr = accuracy.get(method, 0)
                avg_pnl = stats.get("avg_pnl", 0) or 0
                total = m_stats.get("total", 0)
                hist_section = (
                    f"\nИСТОРИЯ МЕТОДА {method.upper()} (30 дней):\n"
                    f"- Win rate: {wr:.0f}% ({total} прогнозов)\n"
                    f"- Средний PnL: {avg_pnl:+.2f}%\n"
                )
        except Exception:
            pass

    from scripts.core.market_regime import format_regime_context
    regime_ctx = format_regime_context(ind, method=method)
    method_hint = regime_ctx["regime_method_hint"]
    method_hint_line = f"\nУчёт режима для метода: {method_hint}" if method_hint else ""

    base_prompt = f"""Сделай торговый прогноз для {ticker} на {forecast_date}.

КРИТИЧЕСКИ ВАЖНО — ПРИВЯЗКА ЦЕН:
- Используй ТОЛЬКО предоставленные ниже данные, актуальные на {data_date}
- НЕ используй свои знания о ценах {ticker} — они УСТАРЕЛИ и неверны
- Текущая цена = ${ind['price']:.2f} — ЭТО ЕДИНСТВЕННАЯ ПРАВИЛЬНАЯ ЦЕНА
- entry_limit_price = ${ind['price']:.2f} ± 5% (диапазон: ${ind['price']*0.95:.2f} — ${ind['price']*1.05:.2f})
- stop_loss = ${ind['price']:.2f} ± 10% (диапазон: ${ind['price']*0.90:.2f} — ${ind['price']*1.10:.2f})
- target_price = ${ind['price']:.2f} ± 15% (диапазон: ${ind['price']*0.85:.2f} — ${ind['price']*1.15:.2f})
- Уровни вне этих диапазонов будут АВТОМАТИЧЕСКИ ОТКЛОНЕНЫ системой

Горизонт прогноза: {horizon} календарных дней (UTC).

{regime_ctx["regime_block"]}{method_hint_line}

РЫНОЧНЫЙ КОНТЕКСТ:
{mkt_ctx}
{hist_section}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
Цена и тренд:
- Текущая цена: ${ind['price']:.2f}
- EMA9: ${ind.get('ema9', 0):.2f}  EMA21: ${ind.get('ema21', 0):.2f}
- MA20: ${ind['ma20']:.2f} ({'▲' if ind['price'] > ind['ma20'] else '▼'})
- MA50: ${ind['ma50']:.2f} ({'▲' if ind['price'] > ind['ma50'] else '▼'})
- MA200: ${ind['ma200']:.2f} ({'▲' if ind['price'] > ind['ma200'] else '▼'})

Осцилляторы:
- RSI(14): {ind['rsi14']:.1f} ({'перекуплен' if ind['rsi14'] > 70 else 'перепродан' if ind['rsi14'] < 30 else 'нейтрален'})
- Stoch RSI: {ind.get('stoch_rsi', 0):.2f}
- MACD: {ind.get('macd', 0):.2f}  Signal: {ind.get('macd_signal', 0):.2f}  Hist: {ind.get('macd_hist', 0):+.2f}

Волатильность:
- ATR(14): ${ind['atr14']:.2f} ({atr_percent:.1f}%)
- Bollinger Bands: верх ${bb_upper:.2f} / низ ${bb_lower:.2f} — позиция {bb_position:.0f}%

Объемы:
- Текущий: {format_number(ind['volume_current'])}  Средний 20д: {format_number(ind['volume_avg_20'])}  ({volume_ratio:.1f}x)
- OBV тренд: {'↑ бычий' if ind.get('obv', 0) > 0 else '↓ медвежий'}

Динамика цены:
- 5д: {ind['change_5d']:+.1f}%  10д: {ind.get('change_10d', 0):+.1f}%  20д: {ind['change_20d']:+.1f}%  50д: {ind.get('change_50d', 0):+.1f}%

ПОСЛЕДНИЕ ТОРГОВЫЕ ДНИ (реальные OHLCV данные):
{_format_recent_candles(price_data, num_candles=5)}
"""

    method_instructions = get_method_instructions(method, ind, atr_percent)

    return base_prompt + method_instructions + _prompt_footer(db_manager)

def call_ai_model(db_manager, model_cfg: dict, prompt: str) -> str:
    """
    Call an AI model via OpenRouter.
    model_cfg: dict with keys model, temperature, max_tokens.
    Returns raw response string.
    """
    from scripts.core.ai_client import get_ai_client
    client = get_ai_client(db_manager)
    if not client:
        raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY in Config tab.")
    return client.call(
        model=model_cfg["model"],
        user_prompt=prompt,
        temperature=float(model_cfg.get("temperature", 0.2)),
        max_tokens=int(model_cfg.get("max_tokens", 2000)),
        json_mode=True,
    )


def call_perplexity_api(prompt, providers_manager):
    """Legacy wrapper — routes through OpenRouter via AIClient."""
    try:
        db_manager = providers_manager.db_manager
        models = []
        try:
            from scripts.core.ai_client import get_active_ai_models
            models = get_active_ai_models(db_manager)
        except Exception:
            pass
        model_cfg = next(
            (m for m in models if "sonar" in m.get("model", "") or "perplexity" in m.get("model", "")),
            {"model": "perplexity/sonar-pro", "temperature": 0.2, "max_tokens": 2000},
        )
        return call_ai_model(db_manager, model_cfg, prompt)
    except Exception as e:
        logging.error(f"❌ Ошибка API: {e}")
        raise

_NUMERIC_EXPR_RE = re.compile(
    r'(?<=[:\s])(-?\d+(?:\.\d+)?)\s*([*+\-/])\s*(-?\d+(?:\.\d+)?)(?=\s*[,}\]])'
)


def _eval_numeric_expr(left: float, op: str, right: float) -> float:
    if op == '*':
        return left * right
    if op == '+':
        return left + right
    if op == '-':
        return left - right
    if op == '/':
        return left / right if right else left
    return left


def _sanitize_json_numeric_expressions(text: str) -> str:
    """Replace simple arithmetic in JSON values (e.g. 76444.00 * 0.97) with literals."""
    prev = None
    out = text
    while prev != out:
        prev = out

        def _repl(match: re.Match) -> str:
            try:
                result = _eval_numeric_expr(
                    float(match.group(1)),
                    match.group(2),
                    float(match.group(3)),
                )
                return f"{result:.8g}"
            except (TypeError, ValueError):
                return match.group(0)

        out = _NUMERIC_EXPR_RE.sub(_repl, out)
    return out


def _coerce_json_number(value) -> float | None:
    """Parse a JSON numeric field; reject non-numeric expressions after sanitization."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if re.search(r'[*+\-/]', s):
            sanitized = _sanitize_json_numeric_expressions(s)
            try:
                return float(sanitized)
            except ValueError:
                return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


_JSON_REPAIR_SYSTEM = (
    "You fix invalid trading forecast JSON. Respond with ONE valid JSON object only. "
    "Use numeric literals only (no formulas, no markdown, no comments)."
)

_JSON_REPAIR_USER_TEMPLATE = (
    "The response below is invalid JSON. Return corrected JSON with fields: "
    "confidence (int), side (LONG|SHORT|NEUTRAL), rationale (string), "
    "entry_order_type, entry_limit_price (number), entry_tif, target_price (number), "
    "take_profit_tif, stop_loss (number), stop_loss_tif, timeframe_hours (int).\n\n"
    "Invalid response:\n{raw}"
)


def request_json_repair(db_manager, model_cfg: dict, raw_response: str) -> str | None:
    """One-shot repair call when the model returned unparseable JSON."""
    from scripts.core.ai_client import get_ai_client

    client = get_ai_client(db_manager)
    if not client:
        return None
    snippet = (raw_response or "")[:2000]
    try:
        return client.call(
            model=model_cfg["model"],
            user_prompt=_JSON_REPAIR_USER_TEMPLATE.format(raw=snippet),
            system_prompt=_JSON_REPAIR_SYSTEM,
            temperature=0.0,
            max_tokens=1200,
            json_mode=True,
        )
    except Exception as e:
        logging.warning("JSON repair call failed for %s: %s", model_cfg.get("name"), e)
        return None


def _extract_json_str(text: str) -> str:
    """Extract the outermost JSON object from text using bracket balancing."""
    # Try markdown code block first
    md = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if md:
        return md.group(1).strip()
    # Balance braces
    start = text.find('{')
    if start == -1:
        return text.strip()
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:].strip()


def parse_json_response(text):
    """Парсит JSON из ответа модели с балансировкой скобок."""
    required_fields = ['confidence', 'side', 'rationale']
    try:
        json_text = _extract_json_str(text)
        json_text = re.sub(r'```', '', json_text).strip()
        json_text = _sanitize_json_numeric_expressions(json_text)
        data = json.loads(json_text)
        for field in required_fields:
            if field not in data:
                logging.error(f"❌ Отсутствует поле: {field}")
                return None

        # Ensure numeric stop_loss — fall back to parsing exit_stop string
        if 'stop_loss' not in data or data.get('stop_loss') is None:
            exit_stop = str(data.get('exit_stop', ''))
            nums = re.findall(r'[\d.]+', exit_stop)
            if nums:
                try:
                    data['stop_loss'] = float(nums[-1])
                except ValueError:
                    data['stop_loss'] = None
            else:
                data['stop_loss'] = None
        else:
            data['stop_loss'] = _coerce_json_number(data.get('stop_loss'))

        # Ensure numeric entry_limit_price
        if 'entry_limit_price' in data and data.get('entry_limit_price') is not None:
            data['entry_limit_price'] = _coerce_json_number(data.get('entry_limit_price'))

        # Ensure numeric target_price — fall back to parsing exit_target string
        if 'target_price' not in data or data.get('target_price') is None:
            exit_target = str(data.get('exit_target', ''))
            nums = re.findall(r'[\d.]+', exit_target)
            if nums:
                try:
                    data['target_price'] = float(nums[-1])
                except ValueError:
                    data['target_price'] = None
            else:
                data['target_price'] = None
        else:
            data['target_price'] = _coerce_json_number(data.get('target_price'))

        # Set defaults for bracket order fields
        data.setdefault('entry_order_type', 'LMT')
        data.setdefault('entry_tif', 'GTC')
        data.setdefault('take_profit_tif', 'GTC')
        data.setdefault('stop_loss_tif', 'GTC')

        return data
    except json.JSONDecodeError as e:
        logging.error(f"❌ Ошибка парсинга JSON: {e}")
        logging.error(f"❌ Сырой ответ: {text[:500]}")
        return None
    except Exception as e:
        logging.error(f"❌ Ошибка парсинга JSON: {e}")
        logging.error(f"❌ Сырой ответ: {text[:500]}")
        return None


def validate_signal_rr(forecast: dict, current_price: float, min_rr: float = 1.5) -> tuple:
    """Validate R/R ratio and stop-loss direction.

    Returns (is_valid: bool, reason: str).
    Rejects signals with:
    - Missing stop_loss
    - Stop on wrong side (LONG: stop >= entry; SHORT: stop <= entry)
    - R/R < min_rr
    - Invalid entry_limit_price (must be between current price and stop)
    """
    side = str(forecast.get('side', 'NEUTRAL')).upper()
    if side == 'NEUTRAL':
        return True, 'NEUTRAL'

    stop_loss = forecast.get('stop_loss')
    if stop_loss is None or stop_loss <= 0:
        return False, 'MISSING_STOP_LOSS'

    # Use target_price if available, fallback to parsing exit_target
    target_price = forecast.get('target_price')
    if target_price is None or target_price <= 0:
        exit_target_str = str(forecast.get('exit_target', ''))
        target_nums = re.findall(r'[\d.]+', exit_target_str)
        if not target_nums:
            return False, 'MISSING_TARGET_PRICE'
        try:
            target_price = float(target_nums[-1])
        except ValueError:
            return False, 'MISSING_TARGET_PRICE'

    # Use entry_limit_price if available, otherwise use current_price
    entry_price = forecast.get('entry_limit_price') or current_price
    if entry_price is None or entry_price <= 0:
        entry_price = current_price

    if current_price <= 0:
        return False, 'INVALID_CURRENT_PRICE'

    # Validate entry_limit_price position relative to current and stop
    if side == 'LONG':
        if stop_loss >= entry_price:
            return False, 'STOP_ABOVE_ENTRY_FOR_LONG'
        if entry_price > current_price:
            return False, 'ENTRY_ABOVE_CURRENT_FOR_LONG'
        rr = (target_price - entry_price) / (entry_price - stop_loss)
    else:  # SHORT
        if stop_loss <= entry_price:
            return False, 'STOP_BELOW_ENTRY_FOR_SHORT'
        if entry_price < current_price:
            return False, 'ENTRY_BELOW_CURRENT_FOR_SHORT'
        rr = (entry_price - target_price) / (stop_loss - entry_price)

    if rr < min_rr:
        return False, f'LOW_RR_{rr:.2f}'

    return True, f'RR_{rr:.2f}'

def generate_forecast(db_manager, ticker, indicators, method, method_num=1, model_cfg=None):
    """Генерирует прогноз для указанного метода через OpenRouter."""
    try:
        logging.info(f"🤖 Метод {method_num}: {method} для {ticker}")
        prompt = build_prompt(db_manager, ticker, indicators, method)
        if model_cfg is None:
            from scripts.core.ai_client import get_active_ai_models
            models = get_active_ai_models(db_manager)
            model_cfg = models[0] if models else {"model": "perplexity/sonar-pro", "temperature": 0.2, "max_tokens": 2000}
        response = call_ai_model(db_manager, model_cfg, prompt)
        logging.info(f"📝 Получен ответ от {model_cfg.get('model')} для {method}")
        forecast = parse_json_response(response)
        if not forecast:
            raise ValueError("Не удалось распарсить JSON ответ")
        logging.info(f"✅ Прогноз {method}: {forecast['side']} (уверенность: {forecast['confidence']}%)")
        return forecast, prompt, response
    except Exception as e:
        logging.error(f"❌ Ошибка генерации прогноза {method}: {e}")
        raise

def log_error(db_manager, ticker, method, error):
    """Логирует ошибку в таблицу Logs как запись с side=ERROR."""
    try:
        from scripts.core.unified_logs_manager import save_forecast_to_logs
        save_forecast_to_logs(
            db_manager,
            {
                'forecast_date': datetime.now().strftime('%Y-%m-%d'),
                'created_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ticker':        ticker,
                'method':        method,
                'confidence':    0,
                'side':          'ERROR',
                'entry_conditions': '',
                'exit_target':   '',
                'exit_stop':     '',
                'rationale':     str(error),
            },
            prompt_text=None,
            api_response=None,
            model_name='system',
        )
    except Exception as e:
        logging.error(f"❌ Ошибка логирования ошибки: {e}")

def save_forecast(db_manager, ticker, method, forecast, prompt_text=None, api_response=None, model_name=None):
    """Сохраняет прогноз в единую таблицу Logs"""
    try:
        from scripts.core.unified_logs_manager import save_forecast_to_logs
        from scripts.core.multi_model_forecaster import _METHOD_HORIZON_HOURS
        horizon_hours = _METHOD_HORIZON_HOURS.get(method, 24)
        horizon = max(1, round(horizon_hours / 24))
        forecast_date = (datetime.now() + timedelta(hours=horizon_hours)).strftime('%Y-%m-%d')
        entry_conditions = '; '.join(forecast.get('entry_conditions', []))
        forecast_data = {
            'forecast_date': forecast_date,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ticker': ticker,
            'method': method,
            'confidence': forecast['confidence'],
            'side': forecast['side'],
            'entry_conditions': entry_conditions,
            'exit_target': forecast.get('exit_target', ''),
            'exit_stop': forecast.get('exit_stop', ''),
            'position_size': '',
            'rationale': forecast['rationale'],
            'horizon_days': horizon,
        }
        success = save_forecast_to_logs(db_manager, forecast_data, prompt_text, api_response, model_name)
        if success:
            logging.info(f"✅ Сохранен прогноз {method} для {ticker} в Logs")
        else:
            logging.error(f"❌ Не удалось сохранить прогноз {method} для {ticker} в Logs")
        
        return success
        
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения прогноза: {e}")
        return False
