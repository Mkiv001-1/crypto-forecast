"""
Multi-model forecaster using OpenRouter as the single AI gateway.
All active AI models from the providers table are called via AIClient.
"""

import logging
import re
import time
from datetime import datetime, timedelta


def normalize_prices_via_atr(forecast: dict, current_price: float, atr: float) -> dict:
    """Normalise stale AI-returned price levels to be anchored at current_price.

    If stop_loss or target_price deviate more than 10% / 15% from current_price
    respectively, recompute them using ATR-based offsets.  entry_limit_price is
    always clamped to current_price ± 5%.

    Returns a *copy* of forecast with corrected numeric fields.
    """
    if not current_price or current_price <= 0:
        return forecast

    atr = atr if atr and atr > 0 else current_price * 0.02  # fallback: 2% ATR
    result = dict(forecast)
    side = str(result.get('side', 'NEUTRAL')).upper()
    if side == 'NEUTRAL':
        return result

    # --- entry_limit_price: clamp to ±5% ---
    entry = result.get('entry_limit_price') or result.get('entry_price') or current_price
    try:
        entry = float(entry)
    except (TypeError, ValueError):
        entry = current_price
    if abs(entry - current_price) / current_price > 0.05:
        logging.warning(
            f"normalize_prices_via_atr: entry {entry:.2f} → {current_price:.2f} "
            f"(clamped to current price)"
        )
        entry = current_price
    # Limit orders: SHORT sells at/above market; LONG buys at/below market.
    if side == 'SHORT' and entry < current_price:
        entry = current_price
    elif side == 'LONG' and entry > current_price:
        entry = current_price
    result['entry_limit_price'] = entry
    result['entry_price'] = entry

    # --- stop_loss: clamp to ±10% ---
    stop = result.get('stop_loss')
    try:
        stop = float(stop) if stop is not None else None
    except (TypeError, ValueError):
        stop = None
    if stop is None or abs(stop - current_price) / current_price > 0.10:
        if stop is not None:
            logging.warning(
                f"normalize_prices_via_atr: stop_loss {stop:.2f} → ATR-based "
                f"(was {abs(stop-current_price)/current_price*100:.1f}% from current)"
            )
        stop = (entry - 2 * atr) if side == 'LONG' else (entry + 2 * atr)
        result['stop_loss'] = round(stop, 2)

    # --- target_price: clamp to ±15% ---
    target = result.get('target_price')
    try:
        target = float(target) if target is not None else None
    except (TypeError, ValueError):
        target = None
    if target is None or abs(target - current_price) / current_price > 0.15:
        if target is not None:
            logging.warning(
                f"normalize_prices_via_atr: target_price {target:.2f} → ATR-based "
                f"(was {abs(target-current_price)/current_price*100:.1f}% from current)"
            )
        risk = abs(entry - result['stop_loss'])
        target = (entry + 2.0 * risk) if side == 'LONG' else (entry - 2.0 * risk)
        result['target_price'] = round(target, 2)

    return result

_METHOD_HORIZON_HOURS = {
    'momentum_trend':    24,
    'price_action':       8,
    'relative_strength': 48,
    'volatility':         4,
    'mean_reversion':    72,
    'volume_breakout':    2,
}

_METHOD_HORIZON = _METHOD_HORIZON_HOURS  # backward-compat alias (values now in hours)


def generate_forecast_with_model(db_manager, ticker, indicators, method, model_cfg, price_data=None):
    """Generate a forecast for one method + one model via OpenRouter."""
    from scripts.core.forecast_engine import (
        build_prompt,
        call_ai_model,
        parse_json_response,
        request_json_repair,
    )
    model_name = model_cfg['name']
    logging.info(f"🤖 {ticker} | {method} | {model_name} ({model_cfg['model']})")

    prompt = build_prompt(db_manager, ticker, indicators, method, price_data=price_data)

    response = call_ai_model(db_manager, model_cfg, prompt)
    if not response:
        logging.error(f"❌ No response from {model_name}")
        return None, None, None

    forecast = parse_json_response(response)
    final_response = response
    if not forecast:
        logging.warning(
            f"⚠️ {method}/{model_name}: JSON parse failed, attempting repair"
        )
        repair_response = request_json_repair(db_manager, model_cfg, response)
        if repair_response:
            forecast = parse_json_response(repair_response)
            if forecast:
                final_response = repair_response
                logging.info(f"✅ JSON repair succeeded for {method}/{model_name}")
            else:
                logging.error(f"❌ JSON repair still invalid for {model_name}")
        if not forecast:
            logging.error(f"❌ Could not parse JSON from {model_name}")
            return None, None, None

    logging.info(f"✅ {method}/{model_name}: {forecast['side']} conf={forecast['confidence']}%")
    return forecast, prompt, final_response


def generate_multi_model_forecasts(db_manager, ticker, indicators, methods, run_id=None, price_data=None):
    """Generate forecasts for all active AI models × given methods.
    
    Args:
        db_manager: Database manager instance
        ticker: Stock ticker symbol
        indicators: Technical indicators dict
        methods: List of forecast methods
        run_id: Optional forecast run ID
        price_data: Optional list of OHLCV candles for prompt inclusion
    
    Returns:
        tuple: (all_forecasts, log_ids) where log_ids is dict mapping forecast index to log_id
    """
    from scripts.core.ai_client import get_active_ai_models, RateLimitError
    from scripts.core.unified_logs_manager import save_forecast_to_logs

    active_models = get_active_ai_models(db_manager)
    if not active_models:
        logging.warning("⚠️ No active AI models configured")
        return [], {}

    logging.info(f"🚀 {len(active_models)} models × {len(methods)} methods for {ticker}")
    all_forecasts = []
    log_ids = {}
    import re

    for model_cfg in active_models:
        rate_limit = model_cfg.get('rate_limit', 60)
        min_interval = 60.0 / max(rate_limit, 1)
        model_name = model_cfg['name']

        for method in methods:
            try:
                t0 = time.time()
                forecast, prompt, response = generate_forecast_with_model(
                    db_manager, ticker, indicators, method, model_cfg, price_data=price_data
                )

                if forecast:
                    timeframe_hours = forecast.get('timeframe_hours') or _METHOD_HORIZON_HOURS.get(method, 24)
                    try:
                        timeframe_hours = int(timeframe_hours)
                    except (TypeError, ValueError):
                        timeframe_hours = _METHOD_HORIZON_HOURS.get(method, 24)
                    horizon_days = max(1, round(timeframe_hours / 24))
                    forecast_date = (datetime.now() + timedelta(hours=timeframe_hours)).strftime('%Y-%m-%d')

                    raw_entry = forecast.get('entry_price', '')
                    ep_match = re.search(r'[\d.]+', str(raw_entry))
                    ai_entry_price = float(ep_match.group()) if ep_match else None

                    # Validate AI-returned entry_price against actual current price
                    current_price = indicators.get('price', 0)
                    if ai_entry_price and current_price > 0:
                        price_diff_pct = abs(ai_entry_price - current_price) / current_price
                        if price_diff_pct > 0.05:  # > 5% difference indicates stale data
                            logging.warning(
                                f"⚠️ {method}/{model_name}: AI entry_price ${ai_entry_price:.2f} "
                                f"differs {price_diff_pct*100:.1f}% from current ${current_price:.2f}. "
                                f"Using current price."
                            )
                            entry_price = current_price
                        else:
                            entry_price = ai_entry_price
                    else:
                        entry_price = current_price if current_price > 0 else (ai_entry_price or 0)

                    # Normalise stale price levels via ATR before R/R validation
                    atr_val = indicators.get('atr14', 0)
                    forecast = normalize_prices_via_atr(forecast, current_price, atr_val)
                    entry_price = forecast.get('entry_limit_price') or entry_price

                    # R/R validation (market price vs normalised levels)
                    from scripts.core.forecast_engine import validate_signal_rr
                    rr_valid, rr_reason = validate_signal_rr(forecast, current_price)
                    if not rr_valid:
                        logging.warning(f"⏭️ {method}/{model_name}: skipped ({rr_reason})")
                        continue

                    stop_loss = forecast.get('stop_loss')
                    rr_value = None
                    if stop_loss and entry_price > 0:
                        try:
                            exit_target_str = str(forecast.get('exit_target', ''))
                            t_nums = re.findall(r'[\d.]+', exit_target_str)
                            if t_nums:
                                target_price = float(t_nums[-1])
                                side = str(forecast.get('side', '')).upper()
                                if side == 'LONG' and entry_price > stop_loss:
                                    rr_value = round((target_price - entry_price) / (entry_price - stop_loss), 2)
                                elif side == 'SHORT' and stop_loss > entry_price:
                                    rr_value = round((entry_price - target_price) / (stop_loss - entry_price), 2)
                        except Exception:
                            pass

                    # Extract numeric target_price
                    raw_target = forecast.get('target_price')
                    if raw_target is None:
                        exit_target_str = str(forecast.get('exit_target', ''))
                        t_nums2 = re.findall(r'[\d.]+', exit_target_str)
                        raw_target = float(t_nums2[-1]) if t_nums2 else None
                    else:
                        try:
                            raw_target = float(raw_target)
                        except (TypeError, ValueError):
                            raw_target = None
                    if raw_target is None:
                        raw_target = forecast.get('target_price')

                    forecast_data = {
                        'forecast_date':    forecast_date,
                        'created_at':       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'ticker':           ticker,
                        'method':           method,
                        'confidence':       forecast['confidence'],
                        'side':             forecast['side'],
                        'entry_price':      entry_price,
                        'entry_conditions': '; '.join(forecast.get('entry_conditions', [])),
                        'exit_target':      forecast.get('exit_target', ''),
                        'exit_stop':        forecast.get('exit_stop', ''),
                        'target_price':     raw_target,
                        'stop_loss':        stop_loss,
                        'rr_ratio':         rr_value,
                        'timeframe_hours':  timeframe_hours,
                        'position_size':    '',
                        'rationale':        forecast['rationale'],
                        'horizon_days':     horizon_days,
                        'entry_order_type': forecast.get('entry_order_type', 'LMT'),
                        'entry_limit_price': entry_price,  # Use validated entry_price, not AI raw value
                        'entry_tif':        forecast.get('entry_tif', 'GTC'),
                        'take_profit_tif':  forecast.get('take_profit_tif', 'GTC'),
                        'stop_loss_tif':    forecast.get('stop_loss_tif', 'GTC'),
                    }
                    log_id = save_forecast_to_logs(
                        db_manager, forecast_data,
                        prompt_text=prompt, api_response=response,
                        model_name=model_name,
                    )
                    if log_id:
                        # Update logs with run_id
                        if run_id:
                            db_manager.update_log_run_id(log_id, run_id)
                        
                        # Flatten structure for consensus calculation
                        # Use validated entry_price, not AI raw entry_limit_price
                        ai_entry_limit = entry_price  # Already validated above
                        forecast_idx = len(all_forecasts)
                        all_forecasts.append({
                            'model': model_name,
                            'method': method,
                            'side': forecast.get('side', 'NEUTRAL'),
                            'confidence': forecast.get('confidence', 50),
                            'exit_target': forecast.get('exit_target', ''),
                            'target_price': raw_target,
                            'stop_loss': stop_loss,
                            'entry_limit_price': ai_entry_limit,
                            'entry_tif': forecast.get('entry_tif', 'GTC'),
                            'take_profit_tif': forecast.get('take_profit_tif', 'GTC'),
                            'stop_loss_tif': forecast.get('stop_loss_tif', 'GTC'),
                            'log_id': log_id,  # Keep log_id for linking
                            'run_id': run_id,
                        })
                        log_ids[forecast_idx] = log_id

                # Rate limiting between requests
                elapsed = time.time() - t0
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)

            except RateLimitError as e:
                wait = getattr(e, "retry_after", None) or 60
                logging.warning(f"⏭️ Skipping model '{model_name}' — rate limited, sleeping {wait}s (retry_after={e.retry_after})")
                time.sleep(wait)
                break  # skip remaining methods for this model, try next model

            except Exception as e:
                logging.error(f"❌ Error {method}/{model_name}: {e}")
                continue

    logging.info(f"✅ Generated {len(all_forecasts)} forecasts (run_id={run_id})")
    return all_forecasts, log_ids
