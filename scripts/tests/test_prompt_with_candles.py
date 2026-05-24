#!/usr/bin/env python3
"""
Test script to verify that OHLCV candles are included in the prompt.

This script tests the enhanced prompt generation that includes recent
OHLCV candles to help AI models see actual price data instead of making up numbers.
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'scripts', 'core'))

from forecast_engine import build_prompt, _format_recent_candles


def test_format_recent_candles():
    """Test the candle formatting function."""
    print("\n=== Test _format_recent_candles ===")
    
    # Sample price data (5 days)
    price_data = [
        {'date': '2026-05-12', 'open': 195.50, 'high': 198.20, 'low': 194.80, 'close': 197.30, 'volume': 45_500_000},
        {'date': '2026-05-13', 'open': 197.40, 'high': 199.50, 'low': 196.90, 'close': 198.80, 'volume': 52_300_000},
        {'date': '2026-05-14', 'open': 198.90, 'high': 200.00, 'low': 197.50, 'close': 199.20, 'volume': 48_100_000},
        {'date': '2026-05-15', 'open': 199.30, 'high': 201.50, 'low': 198.00, 'close': 200.50, 'volume': 55_700_000},
        {'date': '2026-05-16', 'open': 200.40, 'high': 202.00, 'low': 199.50, 'close': 201.80, 'volume': 49_200_000},
    ]
    
    result = _format_recent_candles(price_data, num_candles=5)
    print(result)
    
    # Verify formatting
    assert "2026-05-16" in result, "Latest date should be first"
    assert "O=200.40" in result, "Open price should be formatted"
    assert "V=49.2M" in result, "Volume should be in millions"
    print("[PASS] Candle formatting test passed")


def test_build_prompt_with_candles():
    """Test that build_prompt includes candle data when provided."""
    print("\n=== Test build_prompt with candles ===")
    
    # Sample price data
    price_data = [
        {'date': '2026-05-12', 'open': 195.50, 'high': 198.20, 'low': 194.80, 'close': 197.30, 'volume': 45_500_000},
        {'date': '2026-05-13', 'open': 197.40, 'high': 199.50, 'low': 196.90, 'close': 198.80, 'volume': 52_300_000},
        {'date': '2026-05-14', 'open': 198.90, 'high': 200.00, 'low': 197.50, 'close': 199.20, 'volume': 48_100_000},
        {'date': '2026-05-15', 'open': 199.30, 'high': 201.50, 'low': 198.00, 'close': 200.50, 'volume': 55_700_000},
        {'date': '2026-05-16', 'open': 200.40, 'high': 202.00, 'low': 199.50, 'close': 201.80, 'volume': 49_200_000},
    ]
    
    # Sample indicators
    indicators = {
        'price': 201.80,
        'ma20': 198.50,
        'ma50': 195.30,
        'ma200': 185.40,
        'ema9': 200.20,
        'ema21': 198.80,
        'rsi14': 65.5,
        'stoch_rsi': 0.75,
        'atr14': 2.30,
        'adx14': 28.5,
        'macd': 1.20,
        'macd_signal': 0.80,
        'macd_hist': 0.40,
        'bb': {'upper': 205.0, 'lower': 192.0, 'middle': 198.5},
        'bb_upper': 205.0,
        'bb_lower': 192.0,
        'obv': 150000000,
        'volume_current': 49_200_000,
        'volume_avg_20': 48_000_000,
        'change_5d': 2.5,
        'change_10d': 4.2,
        'change_20d': 6.8,
        'change_50d': 12.5,
        'market_regime': 'TRENDING',
    }
    
    # Build prompt with price_data
    prompt = build_prompt(
        db_manager=None,
        ticker='NASDAQ:AAPL',
        ind=indicators,
        method='price_action',
        price_data=price_data
    )
    
    # Verify candles are in prompt
    assert "ПОСЛЕДНИЕ ТОРГОВЫЕ ДНИ" in prompt, "Candles section should be in prompt"
    assert "2026-05-16" in prompt, "Latest candle date should be in prompt"
    assert "O=200.40" in prompt, "Open price should be in prompt"
    assert "C=201.80" in prompt, "Close price should be in prompt"
    
    print("[PASS] Prompt includes candle data")
    print("\n--- Verifying candles section exists ---")
    # Just verify the candles section exists without printing Cyrillic text
    lines = prompt.split('\n')
    candles_found = False
    candle_count = 0
    for line in lines:
        if 'O=' in line and 'H=' in line and 'L=' in line:
            candle_count += 1
            candles_found = True
    print(f"Found {candle_count} candle lines in prompt")
    if candles_found:
        print("[PASS] Candle data properly formatted in prompt")
    else:
        raise AssertionError("No candle data found in prompt")


def test_build_prompt_without_candles():
    """Test that build_prompt works without price_data (backward compatibility)."""
    print("\n=== Test build_prompt without candles (backward compat) ===")
    
    indicators = {
        'price': 201.80,
        'ma20': 198.50,
        'ma50': 195.30,
        'ma200': 185.40,
        'ema9': 200.20,
        'ema21': 198.80,
        'rsi14': 65.5,
        'atr14': 2.30,
        'adx14': 28.5,
        'macd': 1.20,
        'macd_signal': 0.80,
        'macd_hist': 0.40,
        'stoch_rsi': 0.75,
        'bb': {'upper': 205.0, 'lower': 192.0, 'middle': 198.5},
        'bb_upper': 205.0,
        'bb_lower': 192.0,
        'volume_current': 49_200_000,
        'volume_avg_20': 48_000_000,
        'change_5d': 2.5,
        'change_10d': 4.2,
        'change_20d': 6.8,
        'change_50d': 12.5,
        'obv': 150000000,
        'market_regime': 'TRENDING',
    }
    
    # Build prompt without price_data
    prompt = build_prompt(
        db_manager=None,
        ticker='NASDAQ:AAPL',
        ind=indicators,
        method='momentum_trend',
        price_data=None
    )
    
    # Should still work, just show "Нет данных о свечах"
    assert "ПОСЛЕДНИЕ ТОРГОВЫЕ ДНИ" in prompt, "Candles section should still be in prompt"
    assert "Нет данных о свечах" in prompt, "Should indicate no candle data"
    print("[PASS] Prompt works without price_data (backward compatible)")


if __name__ == '__main__':
    print("=" * 60)
    print("Testing Prompt with OHLCV Candles Enhancement")
    print("=" * 60)
    
    try:
        test_format_recent_candles()
        test_build_prompt_with_candles()
        test_build_prompt_without_candles()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe enhanced prompt now includes real OHLCV candles.")
        print("This helps AI models see actual price data instead of")
        print("making up numbers based on indicators alone.")
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
