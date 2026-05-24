#!/usr/bin/env python3
"""
Test script to diagnose AI price accuracy issues.
Tests multiple AI models across multiple tickers and methods,
comparing returned prices with actual market prices.
"""

import sys
import os
import json
import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

import yfinance as yf
import sqlite3

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


# Module-level imports (after path setup)
try:
    from ai_client import get_active_ai_models as _get_models, AIClient
    from sqlite_manager import SQLiteManager
    from indicators import calculate_indicators
    from forecast_engine import build_prompt_fallback, parse_json_response
    IMPORTS_OK = True
except ImportError as e:
    logger.error(f"Import error: {e}")
    IMPORTS_OK = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_TICKERS = ['NASDAQ:TQQQ', 'NASDAQ:AAPL', 'NASDAQ:NVDA', 'NASDAQ:MSFT', 'NASDAQ:TSLA']
TEST_METHODS = ['momentum_trend', 'price_action', 'relative_strength', 'volatility', 'mean_reversion']
DB_PATH = _get_db_path()


def get_active_ai_models(db_manager):
    """Fetch active AI models from database."""
    try:
        return _get_models(db_manager)
    except Exception as e:
        logger.error(f"Failed to get active models: {e}")
        return []


def fetch_current_price_yf(ticker: str) -> Optional[float]:
    """Fetch current price via yfinance."""
    try:
        symbol = ticker.replace('NASDAQ:', '').replace('NYSE:', '')
        ticker_obj = yf.Ticker(symbol)
        info = ticker_obj.info
        current = info.get('regularMarketPrice') or info.get('previousClose')
        if current:
            return float(current)
        
        # Fallback to recent history
        hist = ticker_obj.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        logger.error(f"yfinance error for {ticker}: {e}")
    return None


def load_price_data_from_db(db_manager, ticker: str, days: int = 60):
    """Load price data from SQLite database."""
    try:
        if isinstance(db_manager, SQLiteManager):
            price_df = db_manager.read_sheet('PriceData')
            if price_df is not None and not price_df.empty:
                # Filter by ticker
                if 'ticker' in price_df.columns:
                    ticker_data = price_df[price_df['ticker'] == ticker].copy()
                else:
                    ticker_data = price_df.copy()
                
                if ticker_data.empty:
                    return None
                
                # Convert to list of dicts
                price_data = []
                for _, row in ticker_data.iterrows():
                    try:
                        price_data.append({
                            'date': row.get('date') or row.get('Date'),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume'])
                        })
                    except (ValueError, KeyError):
                        continue
                
                price_data.sort(key=lambda x: str(x['date']), reverse=True)
                return price_data[:days]
    except Exception as e:
        logger.error(f"DB load error for {ticker}: {e}")
    return None


def calculate_indicators_for_ticker(ticker: str, price_data: List[Dict]) -> Dict[str, Any]:
    """Calculate technical indicators for ticker."""
    try:
        return calculate_indicators(ticker, price_data)
    except Exception as e:
        logger.error(f"Indicator calculation error for {ticker}: {e}")
        return {}


def build_test_prompt(ticker: str, indicators: Dict, method: str) -> str:
    """Build prompt using forecast_engine."""
    try:
        return build_prompt_fallback(ticker, indicators, method, db_manager=None)
    except Exception as e:
        logger.error(f"Prompt build error: {e}")
        return ""


def call_ai_model_test(db_manager, model_cfg: Dict, prompt: str) -> Optional[Dict]:
    """Call AI model and parse response."""
    try:
        # Get API key from config
        api_key = db_manager.get_config_value("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.error("No OpenRouter API key configured")
            return None
        
        client = AIClient(api_key)
        model_name = model_cfg.get('model')
        model_display = model_cfg.get('name', model_name)
        
        logger.info(f"  Calling {model_display} ({model_name})...")
        response = client.call(
            model=model_name,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=2000,
            max_retries=2
        )
        
        if not response:
            return None
        
        # Parse JSON response
        parsed = parse_json_response(response)
        
        if parsed:
            return {
                'parsed': parsed,
                'raw_response': response[:1000]  # First 1000 chars
            }
        
        return None
        
    except Exception as e:
        logger.error(f"AI call error: {e}")
        return None


def analyze_price_deviation(actual_price: float, ai_prices: Dict[str, float]) -> Dict[str, Any]:
    """Analyze deviation between actual and AI prices."""
    results = {}
    
    for key, ai_price in ai_prices.items():
        if ai_price and actual_price > 0:
            diff_pct = ((ai_price - actual_price) / actual_price) * 100
            results[key] = {
                'ai_price': ai_price,
                'diff_pct': round(diff_pct, 2),
                'is_stale': abs(diff_pct) > 10.0  # > 10% considered stale
            }
        else:
            results[key] = {'ai_price': ai_price, 'diff_pct': None, 'is_stale': False}
    
    return results


def run_price_accuracy_test():
    """Main test function."""
    logger.info("=" * 80)
    logger.info("AI PRICE ACCURACY TEST")
    logger.info("=" * 80)
    
    # Initialize DB manager
    try:
        from sqlite_manager import SQLiteManager
        db_manager = SQLiteManager(DB_PATH)
    except Exception as e:
        logger.error(f"Failed to initialize DB manager: {e}")
        return
    
    # Get active AI models
    models = get_active_ai_models(db_manager)
    if not models:
        logger.error("No active AI models found")
        return
    
    logger.info(f"Found {len(models)} active models: {[m.get('name') for m in models]}")
    logger.info(f"Testing {len(TEST_TICKERS)} tickers with {len(TEST_METHODS)} methods")
    
    # Results collection
    all_results = []
    stale_count = 0
    model_stale_stats = {}
    ticker_stale_stats = {}
    
    # Test each combination
    for ticker in TEST_TICKERS:
        logger.info(f"\n--- Testing {ticker} ---")
        
        # Fetch actual current price via yfinance
        actual_price = fetch_current_price_yf(ticker)
        if not actual_price:
            logger.warning(f"Could not fetch actual price for {ticker}, skipping")
            continue
        
        logger.info(f"Actual current price: ${actual_price:.2f}")
        
        # Load price data and calculate indicators
        price_data = load_price_data_from_db(db_manager, ticker, days=60)
        if not price_data:
            logger.warning(f"No price data for {ticker}, skipping")
            continue
        
        indicators = calculate_indicators_for_ticker(ticker, price_data)
        if not indicators:
            logger.warning(f"Could not calculate indicators for {ticker}, skipping")
            continue
        
        db_indicator_price = indicators.get('price', 0)
        logger.info(f"DB indicator price: ${db_indicator_price:.2f}")
        
        # Test each model and method
        for model_cfg in models:
            model_name = model_cfg.get('name', 'unknown')
            
            for method in TEST_METHODS:
                # Build prompt
                prompt = build_test_prompt(ticker, indicators, method)
                if not prompt:
                    continue
                
                # Call AI model
                result = call_ai_model_test(db_manager, model_cfg, prompt)
                if not result:
                    continue
                
                parsed = result['parsed']
                
                # Extract AI prices
                ai_entry = parsed.get('entry_price') or parsed.get('entry_limit_price')
                ai_target = parsed.get('target_price')
                ai_stop = parsed.get('stop_loss')
                
                # Analyze deviations
                ai_prices = {
                    'entry': ai_entry,
                    'target': ai_target,
                    'stop': ai_stop
                }
                deviation = analyze_price_deviation(actual_price, ai_prices)
                
                # Record result
                test_result = {
                    'timestamp': datetime.now().isoformat(),
                    'ticker': ticker,
                    'actual_price': actual_price,
                    'db_indicator_price': db_indicator_price,
                    'model': model_name,
                    'method': method,
                    'side': parsed.get('side', 'UNKNOWN'),
                    'confidence': parsed.get('confidence', 0),
                    'ai_entry_price': ai_entry,
                    'ai_target_price': ai_target,
                    'ai_stop_loss': ai_stop,
                    'entry_deviation_pct': deviation.get('entry', {}).get('diff_pct'),
                    'target_deviation_pct': deviation.get('target', {}).get('diff_pct'),
                    'stop_deviation_pct': deviation.get('stop', {}).get('diff_pct'),
                    'entry_is_stale': deviation.get('entry', {}).get('is_stale', False),
                    'rationale_snippet': parsed.get('rationale', '')[:200]
                }
                
                all_results.append(test_result)
                
                # Update statistics
                if deviation.get('entry', {}).get('is_stale'):
                    stale_count += 1
                    model_stale_stats[model_name] = model_stale_stats.get(model_name, 0) + 1
                    ticker_stale_stats[ticker] = ticker_stale_stats.get(ticker, 0) + 1
                    logger.warning(
                        f"  STALE DATA: {model_name}/{method} - "
                        f"AI entry ${ai_entry:.2f} vs actual ${actual_price:.2f} "
                        f"({deviation['entry']['diff_pct']:+.1f}%)"
                    )
                else:
                    logger.info(
                        f"  OK: {model_name}/{method} - "
                        f"AI entry ${ai_entry:.2f} vs actual ${actual_price:.2f} "
                        f"({deviation.get('entry', {}).get('diff_pct', 0):+.1f}%)"
                    )
    
    # Generate summary report
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    total_tests = len(all_results)
    stale_pct = (stale_count / total_tests * 100) if total_tests > 0 else 0
    
    summary = {
        'test_date': datetime.now().isoformat(),
        'total_tests': total_tests,
        'stale_entry_price_count': stale_count,
        'stale_percentage': round(stale_pct, 2),
        'models_with_stale_data': sorted(model_stale_stats.items(), key=lambda x: x[1], reverse=True),
        'tickers_most_affected': sorted(ticker_stale_stats.items(), key=lambda x: x[1], reverse=True),
        'all_results': all_results
    }
    
    logger.info(f"Total tests: {total_tests}")
    logger.info(f"Stale entry prices: {stale_count} ({stale_pct:.1f}%)")
    logger.info(f"Models with stale data: {dict(model_stale_stats)}")
    logger.info(f"Tickers most affected: {dict(ticker_stale_stats)}")
    
    # Save report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_price_accuracy_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"\nFull report saved to: {report_path}")
    
    # Print recommendations
    logger.info("\n" + "=" * 80)
    logger.info("RECOMMENDATIONS")
    logger.info("=" * 80)
    
    if stale_pct > 20:
        logger.warning(f"High stale data rate ({stale_pct:.1f}%) - immediate fix required!")
        logger.info("Recommendation: Implement strict price validation (reject AI forecasts with >5% deviation)")
    elif stale_pct > 5:
        logger.warning(f"Moderate stale data rate ({stale_pct:.1f}%)")
        logger.info("Recommendation: Implement price validation with auto-correction")
    else:
        logger.info(f"Low stale data rate ({stale_pct:.1f}%) - acceptable")
        logger.info("Recommendation: Keep monitoring with 10% threshold")
    
    # Show worst offenders
    if model_stale_stats:
        worst_model = max(model_stale_stats.items(), key=lambda x: x[1])
        logger.info(f"\nWorst model: {worst_model[0]} ({worst_model[1]} stale responses)")
    
    return summary


if __name__ == "__main__":
    run_price_accuracy_test()
