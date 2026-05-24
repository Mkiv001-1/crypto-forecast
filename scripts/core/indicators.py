"""
Расчет технических индикаторов
"""

import numpy as np
import logging
import time
from datetime import datetime

def calculate_ma(prices, period):
    """Рассчитывает простое скользящее среднее"""
    if len(prices) < period:
        return 0
    return float(np.mean(prices[-period:]))

def calculate_rsi(prices, period=14):
    """Рассчитывает индекс относительной силы"""
    if len(prices) < period + 1:
        return 0
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi)

def calculate_atr(highs, lows, closes, period=14):
    """Рассчитывает средний истинный диапазон"""
    if len(highs) < period + 1:
        return 0
    
    tr_values = []
    for i in range(1, min(period + 1, len(highs))):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr = max(high_low, high_close, low_close)
        tr_values.append(tr)
    
    return float(np.mean(tr_values)) if tr_values else 0

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Рассчитывает полосы Боллинджера"""
    if len(prices) < period:
        return {'upper': 0, 'lower': 0, 'middle': 0}
    
    recent_prices = prices[-period:]
    middle = float(np.mean(recent_prices))
    std = float(np.std(recent_prices))
    
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return {'upper': upper, 'lower': lower, 'middle': middle}

def calculate_ema(prices, period):
    """Exponential Moving Average."""
    if len(prices) < period:
        return 0.0
    k = 2.0 / (period + 1)
    ema = float(np.mean(prices[:period]))
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return float(ema)


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram)."""
    if len(prices) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_val  = ema_fast - ema_slow
    # signal line: EMA of macd over last `signal` bars (approximation)
    macd_series = []
    for i in range(signal, len(prices) + 1):
        ef = calculate_ema(prices[:i], fast)
        es = calculate_ema(prices[:i], slow)
        macd_series.append(ef - es)
    if len(macd_series) < signal:
        return macd_val, 0.0, 0.0
    signal_val = float(np.mean(macd_series[-signal:]))
    hist = macd_val - signal_val
    return float(macd_val), float(signal_val), float(hist)


def calculate_stoch_rsi(prices, period=14, smooth_k=3, smooth_d=3):
    """Stochastic RSI (0-1 range)."""
    if len(prices) < period + period:
        return 0.0
    # Build RSI series
    rsi_series = []
    for i in range(period, len(prices) + 1):
        rsi_series.append(calculate_rsi(prices[:i], period))
    if len(rsi_series) < period:
        return 0.0
    recent = rsi_series[-period:]
    min_r, max_r = min(recent), max(recent)
    if max_r == min_r:
        return 0.5
    stoch = (rsi_series[-1] - min_r) / (max_r - min_r)
    return float(stoch)


def calculate_adx(highs, lows, closes, period=14):
    """Average Directional Index."""
    if len(highs) < period + 1:
        return 0.0
    plus_dm_list, minus_dm_list, tr_list = [], [], []
    for i in range(1, len(highs)):
        up   = highs[i]  - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm_list.append(up   if up > down and up > 0   else 0)
        minus_dm_list.append(down if down > up and down > 0 else 0)
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i-1])
        lpc = abs(lows[i]  - closes[i-1])
        tr_list.append(max(hl, hpc, lpc))
    if len(tr_list) < period:
        return 0.0
    atr_val   = float(np.mean(tr_list[-period:]))
    if atr_val == 0:
        return 0.0
    plus_di  = float(np.mean(plus_dm_list[-period:]))  / atr_val * 100
    minus_di = float(np.mean(minus_dm_list[-period:])) / atr_val * 100
    dx_denom = plus_di + minus_di
    dx = abs(plus_di - minus_di) / dx_denom * 100 if dx_denom else 0
    return float(dx)


def calculate_obv(closes, volumes):
    """On-Balance Volume (returns latest value)."""
    if len(closes) < 2 or len(volumes) < 2:
        return 0.0
    obv = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv += volumes[i]
        elif closes[i] < closes[i-1]:
            obv -= volumes[i]
    return float(obv)


def calculate_price_change(prices, days):
    """Рассчитывает изменение цены в процентах"""
    if len(prices) < days + 1:
        return 0
    
    current = prices[-1]
    past = prices[-(days + 1)]
    
    if past == 0:
        return 0
    
    change = ((current - past) / past) * 100
    return float(change)

def calculate_indicators(ticker, price_data):
    """Рассчитывает все индикаторы для тикера."""
    if not price_data:
        logging.error(f"❌ Нет данных для расчета индикаторов {ticker}")
        return {}

    closes  = [r['close']  for r in price_data]
    highs   = [r['high']   for r in price_data]
    lows    = [r['low']    for r in price_data]
    volumes = [r['volume'] for r in price_data]

    current_price = closes[-1]
    current_date  = price_data[-1]['date']

    logging.info(f"📊 Расчет индикаторов для {ticker}, цена: {current_price}")

    bb = calculate_bollinger_bands(closes, 20, 2)
    macd_val, macd_sig, macd_hist = calculate_macd(closes)

    indicators = {
        'ticker':          ticker,
        'date':            current_date,
        'price':           current_price,
        # Moving averages
        'ma20':            calculate_ma(closes, 20),
        'ma50':            calculate_ma(closes, 50),
        'ma200':           calculate_ma(closes, 200),
        'ema9':            calculate_ema(closes, 9),
        'ema21':           calculate_ema(closes, 21),
        # Oscillators
        'rsi14':           calculate_rsi(closes, 14),
        'stoch_rsi':       calculate_stoch_rsi(closes, 14),
        # Trend / volatility
        'atr14':           calculate_atr(highs, lows, closes, 14),
        'adx14':           calculate_adx(highs, lows, closes, 14),
        # MACD
        'macd':            macd_val,
        'macd_signal':     macd_sig,
        'macd_hist':       macd_hist,
        # Bollinger Bands
        'bb':              bb,
        'bb_upper':        bb['upper'],
        'bb_lower':        bb['lower'],
        'bb_middle':       bb['middle'],
        # Volume
        'obv':             calculate_obv(closes, volumes),
        'volume_avg_20':   float(np.mean(volumes[-20:])) if len(volumes) >= 20 else 0,
        'volume_current':  volumes[-1] if volumes else 0,
        # Price change
        'change_5d':       calculate_price_change(closes, 5),
        'change_10d':      calculate_price_change(closes, 10),
        'change_20d':      calculate_price_change(closes, 20),
        'change_50d':      calculate_price_change(closes, 50),
    }

    logging.info(
        f"✅ {ticker}: RSI={indicators['rsi14']:.1f} ADX={indicators['adx14']:.1f}"
        f" MACD={indicators['macd']:.2f} MA20={indicators['ma20']:.2f}"
    )
    return indicators

def save_indicators(db_manager, indicators):
    """Сохраняет индикаторы в SQLite (INSERT OR REPLACE по ticker+date)."""
    try:
        date_val = indicators['date']
        if hasattr(date_val, 'strftime'):
            date_str = date_val.strftime('%Y-%m-%d')
        else:
            date_str = str(date_val)[:10]

        bb = indicators.get('bb', {})
        data = {
            'ticker':         indicators['ticker'],
            'date':           date_str,
            'price':          indicators.get('price', 0),
            'ma20':           indicators.get('ma20', 0),
            'ma50':           indicators.get('ma50', 0),
            'ma200':          indicators.get('ma200', 0),
            'ema9':           indicators.get('ema9', 0),
            'ema21':          indicators.get('ema21', 0),
            'rsi14':          indicators.get('rsi14', 0),
            'stoch_rsi':      indicators.get('stoch_rsi', 0),
            'atr14':          indicators.get('atr14', 0),
            'adx14':          indicators.get('adx14', 0),
            'macd':           indicators.get('macd', 0),
            'macd_signal':    indicators.get('macd_signal', 0),
            'macd_hist':      indicators.get('macd_hist', 0),
            'bb_upper':       indicators.get('bb_upper') or bb.get('upper', 0),
            'bb_lower':       indicators.get('bb_lower') or bb.get('lower', 0),
            'bb_middle':      indicators.get('bb_middle') or bb.get('middle', 0),
            'obv':            indicators.get('obv', 0),
            'change_5d':      indicators.get('change_5d', 0),
            'change_10d':     indicators.get('change_10d', 0),
            'change_20d':     indicators.get('change_20d', 0),
            'change_50d':     indicators.get('change_50d', 0),
            'volume_avg_20':  indicators.get('volume_avg_20', 0),
            'volume_current': indicators.get('volume_current', 0),
            'market_regime':  indicators.get('market_regime', ''),
        }
        success = db_manager.upsert_row('Indicators', data)
        if success:
            logging.info(f"✅ Сохранены индикаторы для {indicators['ticker']}")
        else:
            logging.error(f"❌ Не удалось сохранить индикаторы для {indicators['ticker']}")
        return success
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения индикаторов: {e}")
        return False
