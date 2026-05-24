# Prompt Enhancement: Real OHLCV Candles

## Overview

This enhancement adds real OHLCV (Open, High, Low, Close, Volume) candle data to the AI prompt, helping models see actual price action instead of making up numbers based on indicators alone.

## Problem

Previously, AI models only received aggregated technical indicators:
```
- Текущая цена: $297.33
- MA20: 298.50
- RSI(14): 45.2
- ATR(14): $2.30 (0.8%)
```

Without seeing actual recent candles, models would sometimes:
- Make up current prices that don't match reality
- Generate entry/stop/target prices based on stale assumptions
- Miss important price action patterns visible in raw candles

## Solution

The prompt now includes the last 5 trading days with real OHLCV data:
```
ПОСЛЕДНИЕ ТОРГОВЫЕ ДНИ (реальные OHLCV данные):
  2026-05-16: O=200.40 H=202.00 L=199.50 C=201.80 V=49.2M
  2026-05-15: O=199.30 H=201.50 L=198.00 C=200.50 V=55.7M
  2026-05-14: O=198.90 H=200.00 L=197.50 C=199.20 V=48.1M
  2026-05-13: O=197.40 H=199.50 L=196.90 C=198.80 V=52.3M
  2026-05-12: O=195.50 H=198.20 L=194.80 C=197.30 V=45.5M
```

## Implementation

### Modified Files

1. **`scripts/core/forecast_engine.py`**
   - Added `_format_recent_candles(price_data, num_candles=5)` function
   - Modified `build_prompt()` to accept optional `price_data` parameter
   - Updated `build_prompt_fallback()` to include candles section in prompt

2. **`scripts/core/multi_model_forecaster.py`**
   - Added `price_data` parameter to `generate_forecast_with_model()`
   - Added `price_data` parameter to `generate_multi_model_forecasts()`
   - Passes candles through the call chain to `build_prompt()`

3. **`scripts/core/forecast_runner.py`**
   - Updated call to `generate_multi_model_forecasts()` to pass `price_data`

### Flow of Data

```
process_ticker()
    ↓ price_data
    generate_multi_model_forecasts(price_data=price_data)
        ↓ price_data
        generate_forecast_with_model(price_data=price_data)
            ↓ price_data
            build_prompt(price_data=price_data)
                ↓ price_data
                _format_recent_candles(price_data)
```

## Testing

Run the test script to verify the implementation:

```bash
cd d:\Git\forecast
python scripts\tests\test_prompt_with_candles.py
```

Expected output:
```
============================================================
Testing Prompt with OHLCV Candles Enhancement
============================================================

=== Test _format_recent_candles ===
  2026-05-16: O=200.40 H=202.00 L=199.50 C=201.80 V=49.2M
  2026-05-15: O=199.30 H=201.50 L=198.00 C=200.50 V=55.7M
  ...
✅ Candle formatting test passed

=== Test build_prompt with candles ===
✅ Prompt includes candle data

--- Sample from prompt ---
ПОСЛЕДНИЕ ТОРГОВЫЕ ДНИ (реальные OHLCV данные):
  2026-05-16: O=200.40 H=202.00 L=199.50 C=201.80 V=49.2M
  ...

=== Test build_prompt without candles (backward compat) ===
✅ Prompt works without price_data (backward compatible)

============================================================
✅ ALL TESTS PASSED
============================================================
```

## Backward Compatibility

The implementation is fully backward compatible:
- If `price_data` is not provided, the prompt shows "Нет данных о свечах"
- All existing code paths continue to work without modifications
- Only the forecast generation flow passes candle data

## Benefits

1. **More Accurate Entry Prices**: Models see real recent closes
2. **Better Support/Resistance**: Models see actual highs/lows
3. **Volume Context**: Models see real volume patterns
4. **Reduced Hallucination**: Less chance of making up prices

## Future Improvements

- Include intraday candles for short-term methods (volatility, volume_breakout)
- Add key levels (pivot points, previous day high/low)
- Include sector/market context with real index prices
