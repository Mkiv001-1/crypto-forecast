"""
Consensus engine: aggregates multi-model multi-method forecasts
into a single weighted signal for each ticker.

Robustness features (ред. 2):
- Anomaly filter: drop forecasts where |target - price| / price > CONSENSUS_MAX_DEVIATION
- Median target_price and stop_loss for the dominant direction
- Disagreement control: if minority weight > 40% → force HOLD / high_model_disagreement
"""

import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import List, Optional

from scripts.core.config import CONFIDENCE_THRESHOLD, get_confidence_threshold
from scripts.core.consensus_settings import (
    FILTER_HIGH_DISAGREEMENT,
    FILTER_INSUFFICIENT_AGREEMENT,
    FILTER_LOW_CONFIDENCE,
    FILTER_LOW_EXPECTED_R,
    ConsensusSettings,
    format_filter_reasons,
    load_consensus_settings,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEVIATION = 0.15
_DEFAULT_DISAGREEMENT_THRESHOLD = 0.40
_DEFAULT_MIN_EXPECTED_R = 0.5


def calculate_atr(df, period: int = 14) -> Optional[float]:
    """Calculate Average True Range from price DataFrame.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns (chronological order)
        period: ATR period (default 14)
    
    Returns:
        ATR value or None if insufficient data
    """
    import pandas as pd
    
    if len(df) < period + 1:
        return None
    
    # Calculate True Range
    high = df['high']
    low = df['low']
    close = df['close']
    
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Simple moving average of TR (можно заменить на EMA для более быстрой реакции)
    atr = tr.rolling(window=period, min_periods=period).mean().iloc[-1]
    
    return float(atr) if pd.notna(atr) else None


def normalize_r_multiple(r_multiple: float, atr: float, entry_price: float) -> Optional[float]:
    """Normalize R-multiple by ATR to compare across tickers.
    
    Args:
        r_multiple: Raw R-multiple (reward/risk ratio)
        atr: ATR(14) value
        entry_price: Entry price for percentage normalization
    
    Returns:
        Normalized R-multiple or None if inputs invalid
    """
    if not atr or not entry_price or atr <= 0 or entry_price <= 0:
        return None
    
    # ATR as percentage of price
    atr_pct = atr / entry_price
    
    # Normalize: R-multiple per 1% ATR
    # Example: R=2.0, ATR=2% → normalized = 2.0 / 2.0 = 1.0
    # Example: R=2.0, ATR=5% → normalized = 2.0 / 5.0 = 0.4 (тикер волатильный, сигнал "хуже")
    normalized = r_multiple / (atr_pct * 100)
    
    return round(normalized, 2)


def _parse_price(value) -> Optional[float]:
    """Extract numeric price from a value that may be a string like '$142.50 (+3.2%)'."""
    import re
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if v > 0 else None
    nums = re.findall(r'[\d.]+', str(value))
    for n in nums:
        try:
            v = float(n)
            if v > 0:
                return v
        except ValueError:
            continue
    return None


def _resolve_settings(
    consensus_settings: Optional[ConsensusSettings],
    max_deviation: Optional[float],
    disagreement_threshold: Optional[float],
    confidence_threshold: Optional[float],
    min_expected_r: Optional[float],
    min_models_for_side: Optional[int],
    market_regime: Optional[str],
) -> ConsensusSettings:
    if consensus_settings is not None:
        settings = consensus_settings
    else:
        settings = ConsensusSettings(market_regime=market_regime)
    if max_deviation is not None:
        settings.max_deviation = max_deviation
    if disagreement_threshold is not None:
        settings.disagreement_threshold = disagreement_threshold
    if confidence_threshold is not None:
        settings.confidence_threshold = confidence_threshold
    if min_expected_r is not None:
        settings.min_expected_r = min_expected_r
    if min_models_for_side is not None:
        settings.min_models_for_side = max(1, int(min_models_for_side))
    if market_regime and not settings.market_regime:
        settings.market_regime = market_regime
    return settings


def _mark_links_excluded(forecast_link_data: list) -> None:
    for link_data in forecast_link_data:
        link_data["included_in_consensus"] = 0


def calculate_consensus(
    forecasts: list,
    method_stats: dict = None,
    current_price: float = 0.0,
    max_deviation: float = None,
    disagreement_threshold: float = None,
    run_id: int = None,
    log_ids: dict = None,
    model_stats: dict = None,
    confidence_threshold: float = None,
    consensus_settings: Optional[ConsensusSettings] = None,
    min_expected_r: float = None,
    min_models_for_side: int = None,
    market_regime: str = None,
) -> dict:
    """
    Aggregate a list of forecast dicts into a consensus signal.

    Each forecast dict must have: side, confidence, method, model.
    Optional fields used for price validation: entry_price, exit_target, stop_loss.
    method_stats: optional dict {method: {win_rate: float, timeframe_hours: int, ...}}
    model_stats:  optional dict {model_name: {ema_accuracy: float, ...}} — per-AI-model accuracy
    current_price: used for anomaly filter; skip if 0.
    run_id: optional forecast run ID for linking.
    log_ids: optional dict mapping forecast index to log_id.

    Returns:
        {signal, confidence, methods_long, methods_short, methods_neutral, rationale,
         target_price, stop_loss, high_model_disagreement}
    """
    settings = _resolve_settings(
        consensus_settings,
        max_deviation,
        disagreement_threshold,
        confidence_threshold,
        min_expected_r,
        min_models_for_side,
        market_regime,
    )
    eff_max_deviation = settings.max_deviation
    eff_disagreement = settings.disagreement_threshold
    eff_conf_threshold = settings.confidence_threshold
    eff_min_expected_r = settings.min_expected_r
    eff_min_models = settings.min_models_for_side
    filter_reasons: List[str] = []

    if not forecasts:
        return {
            "signal":                 "NEUTRAL",
            "confidence":             0.0,
            "methods_long":           "",
            "methods_short":          "",
            "methods_neutral":        "",
            "rationale":              "No forecasts available",
            "target_price":           None,
            "stop_loss":              None,
            "high_model_disagreement": False,
            "filter_reasons":         [],
            "filter_reasons_json":    "[]",
            "models_long_count":      0,
            "models_short_count":     0,
            "minority_weight_pct":    None,
            "expected_r":             None,
            "active_settings":        settings.as_dict(),
            "active_settings_json":   json.dumps(settings.as_dict(), ensure_ascii=False),
            "market_regime":          settings.market_regime,
        }

    weighted_long  = 0.0
    weighted_short = 0.0
    total_weight   = 0.0

    methods_long    = []
    methods_short   = []
    methods_neutral = []

    long_targets  = []
    long_stops    = []
    long_entry_prices = []
    short_targets = []
    short_stops   = []
    short_entry_prices = []

    # TIF values — use first available or defaults
    entry_tif_values = []
    take_profit_tif_values = []
    stop_loss_tif_values = []

    filtered_count = 0
    models_long: set = set()
    models_short: set = set()

    # Store forecast data for linking (with weights)
    forecast_link_data = []  # List of dicts with all weight info

    for idx, f in enumerate(forecasts):
        side       = str(f.get("side", "NEUTRAL")).upper()
        raw_confidence = float(f.get("confidence", 50))  # 0-100 scale
        method     = str(f.get("method", ""))
        model      = str(f.get("model", ""))

        # --- Confidence Calibration (analytics only — does NOT affect weight) ---
        # calibration_factor is stored in link_data for analytics, but weight uses raw confidence
        # to avoid double-counting: ema_weight (below) already carries historical accuracy signal.
        calibration_factor = 1.0
        ema_acc = None
        # Prefer model_stats (keyed by AI model name) over method_stats for ema_accuracy
        if model_stats and model in model_stats:
            v = model_stats[model]
            ema_acc = v.get("ema_accuracy") if isinstance(v, dict) else float(v)
        elif method_stats and method in method_stats:
            ema_acc = method_stats[method].get("ema_accuracy")
        if ema_acc is not None:
            # ema_acc typically 0.3-0.7, scale to 0.6-1.4 factor (analytics reference)
            calibration_factor = max(0.5, min(1.5, float(ema_acc) / 0.5))
        
        calibrated_confidence = raw_confidence * calibration_factor
        # Clamp to 0-100 range
        calibrated_confidence = max(0.0, min(100.0, calibrated_confidence))
        # Use raw confidence for weight — ema_weight below already captures model accuracy
        confidence = raw_confidence / 100.0  # Convert to 0-1 for weight calc

        # --- Anomaly filter ---
        is_filtered = False
        if current_price > 0 and side in ("LONG", "SHORT"):
            entry = _parse_price(f.get("entry_price"))
            target = _parse_price(f.get("exit_target") or f.get("target_price"))
            if target and abs(target - current_price) / current_price > eff_max_deviation:
                logger.debug(
                    f"consensus: filtered anomaly {method}/{f.get('model','?')} "
                    f"target={target} vs price={current_price} (>{eff_max_deviation*100:.0f}%)"
                )
                filtered_count += 1
                is_filtered = True
                methods_neutral.append(f"{method}({f.get('model','?')})[filtered]")

        # --- Weight calculation ---
        win_rate    = 0.5
        ema_weight  = 1.0
        if method_stats and method in method_stats:
            win_rate   = float(method_stats[method].get("win_rate", 0.5))
            # ema_acc already resolved above (from model_stats or method_stats)
            if ema_acc is not None:
                ema_weight = max(0.3, min(1.5, float(ema_acc) * 2))

        weight = confidence * win_rate * ema_weight

        # NOTE: total_weight is accumulated only for non-filtered forecasts (below, after continue)

        # --- Collect prices ---
        target_price = _parse_price(f.get("exit_target") or f.get("target_price"))
        stop_price   = f.get("stop_loss")
        if stop_price is not None:
            try:
                stop_price = float(stop_price)
                if stop_price <= 0:
                    stop_price = None
            except (TypeError, ValueError):
                stop_price = None

        # Collect entry_limit_price and TIFs
        entry_limit = f.get("entry_limit_price")
        if entry_limit is not None:
            try:
                entry_limit = float(entry_limit)
                if entry_limit <= 0:
                    entry_limit = None
            except (TypeError, ValueError):
                entry_limit = None

        if f.get("entry_tif"):
            entry_tif_values.append(f.get("entry_tif"))
        if f.get("take_profit_tif"):
            take_profit_tif_values.append(f.get("take_profit_tif"))
        if f.get("stop_loss_tif"):
            stop_loss_tif_values.append(f.get("stop_loss_tif"))

        # Calculate R-multiple for this forecast if we have levels
        forecast_r_multiple = None
        if target_price and stop_price and entry_limit:
            risk = abs(entry_limit - stop_price)
            reward = abs(target_price - entry_limit)
            if risk > 0:
                forecast_r_multiple = round(reward / risk, 2)
        
        # Store link data for all forecasts (including filtered)
        log_id = log_ids.get(idx) if log_ids else f.get('log_id')
        if run_id and log_id:
            forecast_link_data.append({
                'run_id': run_id,
                'log_id': log_id,
                'ticker': f.get('ticker', ''),
                'method': method,
                'model': f.get('model', ''),
                'signal': side,
                'raw_confidence': raw_confidence,
                'calibrated_confidence': calibrated_confidence,
                'calibration_factor': calibration_factor,
                'win_rate': win_rate,
                'ema_accuracy': ema_acc if ema_acc is not None else 0.5,
                'final_weight': weight,
                'target_price': target_price,
                'stop_loss': stop_price,
                'entry_price': entry_limit,
                'r_multiple': forecast_r_multiple,
                'atr_14': f.get('atr_14'),  # ATR if available from price data
                'included_in_consensus': 0 if is_filtered else 1,  # Mark filtered as not included
            })
        
        if is_filtered:
            continue
            
        total_weight += weight

        model_name = str(f.get("model", "") or "").strip()
        if side == "LONG":
            weighted_long  += weight
            methods_long.append(f"{method}({f.get('model','?')})")
            if model_name:
                models_long.add(model_name)
            if target_price:
                long_targets.append(target_price)
            if stop_price:
                long_stops.append(stop_price)
            if entry_limit:
                long_entry_prices.append(entry_limit)
        elif side == "SHORT":
            weighted_short += weight
            methods_short.append(f"{method}({f.get('model','?')})")
            if model_name:
                models_short.add(model_name)
            if target_price:
                short_targets.append(target_price)
            if stop_price:
                short_stops.append(stop_price)
            if entry_limit:
                short_entry_prices.append(entry_limit)
        else:
            methods_neutral.append(f"{method}({f.get('model','?')})")

    if total_weight == 0:
        signal     = "NEUTRAL"
        confidence = 0.0
    elif weighted_long >= weighted_short:
        signal     = "LONG"
        confidence = round(weighted_long / total_weight * 100, 1)
    else:
        signal     = "SHORT"
        confidence = round(weighted_short / total_weight * 100, 1)

    # --- Disagreement check ---
    high_disagreement = False
    minority_weight_pct = None
    if total_weight > 0 and signal != "NEUTRAL":
        minority_weight = weighted_short if signal == "LONG" else weighted_long
        minority_weight_pct = round(minority_weight / total_weight * 100, 2)
        if minority_weight / total_weight > eff_disagreement:
            high_disagreement = True
            signal = "NEUTRAL"
            confidence = 0.0
            filter_reasons.append(FILTER_HIGH_DISAGREEMENT)
            _mark_links_excluded(forecast_link_data)
            logger.warning(
                f"consensus: high model disagreement "
                f"({minority_weight_pct:.0f}% minority) → forced NEUTRAL"
            )

    # Require minimum confidence to avoid noise
    if signal != "NEUTRAL" and confidence < eff_conf_threshold:
        signal = "NEUTRAL"
        filter_reasons.append(FILTER_LOW_CONFIDENCE)
        _mark_links_excluded(forecast_link_data)

    # Minimum unique models on winning side
    if signal == "LONG" and len(models_long) < eff_min_models:
        signal = "NEUTRAL"
        confidence = 0.0
        filter_reasons.append(FILTER_INSUFFICIENT_AGREEMENT)
        _mark_links_excluded(forecast_link_data)
        logger.warning(
            "consensus: insufficient LONG agreement (%s models < %s)",
            len(models_long),
            eff_min_models,
        )
    elif signal == "SHORT" and len(models_short) < eff_min_models:
        signal = "NEUTRAL"
        confidence = 0.0
        filter_reasons.append(FILTER_INSUFFICIENT_AGREEMENT)
        _mark_links_excluded(forecast_link_data)
        logger.warning(
            "consensus: insufficient SHORT agreement (%s models < %s)",
            len(models_short),
            eff_min_models,
        )

    # --- Median prices for dominant direction ---
    med_target: Optional[float] = None
    med_stop:   Optional[float] = None
    med_entry:  Optional[float] = None
    if signal == "LONG":
        if long_targets:
            med_target = round(statistics.median(long_targets), 4)
        if long_stops:
            med_stop = round(statistics.median(long_stops), 4)
        if long_entry_prices:
            med_entry = round(statistics.median(long_entry_prices), 4)
    elif signal == "SHORT":
        if short_targets:
            med_target = round(statistics.median(short_targets), 4)
        if short_stops:
            med_stop = round(statistics.median(short_stops), 4)
        if short_entry_prices:
            med_entry = round(statistics.median(short_entry_prices), 4)

    # --- Expected Value Filter ---
    # expected_r = (confidence_pct / 100) * (distance_to_target / distance_to_stop)
    # Filter out signals with expected_r below threshold
    expected_r = None
    if signal in ("LONG", "SHORT") and med_target and med_stop and med_entry:
        risk = abs(med_entry - med_stop)
        reward = abs(med_target - med_entry)
        if risk > 0:
            expected_r = (confidence / 100.0) * (reward / risk)
            if expected_r < eff_min_expected_r:
                logger.warning(
                    f"consensus: expected_r={expected_r:.2f} < {eff_min_expected_r} "
                    f"({signal} conf={confidence:.1f}%, r/r={reward/risk:.2f}) → forced NEUTRAL"
                )
                signal = "NEUTRAL"
                confidence = 0.0
                filter_reasons.append(FILTER_LOW_EXPECTED_R)
                _mark_links_excluded(forecast_link_data)

    filter_note = f" [{filtered_count} filtered by anomaly]" if filtered_count else ""
    ev_note = f" [expected_r={expected_r:.2f}]" if expected_r is not None else ""
    reasons_note = f" filters={filter_reasons}" if filter_reasons else ""
    rationale = (
        f"LONG: {len(methods_long)} signals ({len(models_long)} models), "
        f"SHORT: {len(methods_short)} signals ({len(models_short)} models), "
        f"NEUTRAL: {len(methods_neutral)} signals.{filter_note}{ev_note}{reasons_note} "
        f"Weighted confidence: {confidence:.1f}%"
        + (" ⚠️ high_model_disagreement" if high_disagreement else "")
    )

    logger.info(
        f"\U0001f4ca Consensus: {signal} {confidence:.1f}% "
        f"({len(forecasts)} forecasts, target={med_target}, stop={med_stop})"
    )
    
    # TIF defaults — use majority vote (most common value), fallback to hardcoded defaults
    entry_tif = statistics.mode(entry_tif_values) if entry_tif_values else "GTC"
    take_profit_tif = statistics.mode(take_profit_tif_values) if take_profit_tif_values else "GTC"
    stop_loss_tif = statistics.mode(stop_loss_tif_values) if stop_loss_tif_values else "GTC"

    active_settings = settings.as_dict()
    return {
        "signal":                  signal,
        "confidence":              confidence,
        "methods_long":            ", ".join(methods_long),
        "methods_short":           ", ".join(methods_short),
        "methods_neutral":         ", ".join(methods_neutral),
        "rationale":               rationale,
        "target_price":            med_target,
        "stop_loss":               med_stop,
        "entry_limit_price":       med_entry,
        "entry_tif":               entry_tif,
        "take_profit_tif":         take_profit_tif,
        "stop_loss_tif":           stop_loss_tif,
        "high_model_disagreement": high_disagreement,
        "filter_reasons":          filter_reasons,
        "filter_reasons_json":     format_filter_reasons(filter_reasons),
        "models_long_count":       len(models_long),
        "models_short_count":      len(models_short),
        "minority_weight_pct":     minority_weight_pct,
        "expected_r":              round(expected_r, 4) if expected_r is not None else None,
        "active_settings":         active_settings,
        "active_settings_json":    json.dumps(active_settings, ensure_ascii=False),
        "market_regime":           settings.market_regime,
        "_forecast_link_data":     forecast_link_data,  # Internal use for linking
    }


def save_consensus(db_manager, ticker: str, consensus: dict, method_stats: dict = None,
                   override_date: str = None, run_id: int = None, original_run_id: int = None) -> bool:
    """Save consensus record to the consensus table.

    Computes horizon_hours as the median of timeframe_hours for active methods
    that participated in the consensus (from method_stats or db_manager.method_config).
    Derives eval_target_date = consensus_date + horizon_hours.

    override_date: optional YYYY-MM-DD string to use instead of now() — for historical recalc.
    run_id: optional forecast run ID for linking (the recalc run ID).
    original_run_id: optional original forecast run ID from the source forecasts — for analytical JOINs.
    """
    try:
        now = datetime.strptime(override_date, "%Y-%m-%d") if override_date else datetime.now()

        # Compute horizon_hours from method_stats or method_config
        horizon_hours = None
        try:
            hours_list = []
            # Only consider methods that contributed to the winning signal direction
            signal_direction = consensus.get("signal", "NEUTRAL")
            if signal_direction == "LONG":
                active_methods_str = consensus.get("methods_long", "")
            elif signal_direction == "SHORT":
                active_methods_str = consensus.get("methods_short", "")
            else:
                active_methods_str = (
                    consensus.get("methods_long", "") + "," +
                    consensus.get("methods_short", "") + "," +
                    consensus.get("methods_neutral", "")
                )
            # Extract bare method names (strip model suffix in parentheses)
            import re as _re
            active_method_names = set(
                _re.sub(r'\(.*?\)', '', m).strip()
                for m in active_methods_str.split(",")
                if m.strip()
            )

            # Prefer method_stats if it contains timeframe_hours
            if method_stats:
                for method_name, stats in method_stats.items():
                    if active_method_names and method_name not in active_method_names:
                        continue
                    h = stats.get("timeframe_hours")
                    if h and int(h) > 0:
                        hours_list.append(int(h))

            # Fallback: query db directly
            if not hours_list and db_manager is not None:
                try:
                    import pandas as pd
                    with db_manager._connect() as con:
                        df = pd.read_sql_query("SELECT timeframe_hours FROM method_config WHERE active = 1", con)
                    if not df.empty:
                        hours_list = [int(h) for h in df["timeframe_hours"].dropna().tolist() if int(h) > 0]
                except Exception:
                    pass

            if hours_list:
                horizon_hours = int(statistics.median(hours_list))
        except Exception as e:
            logger.warning(f"save_consensus: could not compute horizon_hours: {e}")

        # Default horizon if no method config data available
        if not horizon_hours:
            horizon_hours = 24  # Default: evaluate after 24 hours
            logger.debug(f"save_consensus: using default horizon_hours={horizon_hours} (no method config data)")

        # Ensure eval_target_date is at least the next calendar day
        # (daily bars: entry and actual must be from different days)
        eval_dt = now + timedelta(hours=horizon_hours)
        if eval_dt.date() <= now.date():
            eval_dt = now + timedelta(days=1)
        eval_target_date = eval_dt.strftime("%Y-%m-%d %H:%M:%S")

        signal_val = consensus["signal"]
        if signal_val in ("LONG", "SHORT"):
            if override_date is not None:
                order_state = "ORDER_SKIPPED"
                order_reason = "historical_recalc"
            else:
                from scripts.core.trading_exposure import ticker_has_trading_exposure

                has_exposure, _exp_reason = ticker_has_trading_exposure(db_manager, ticker)
                if has_exposure:
                    order_state = "ORDER_SKIPPED"
                    order_reason = "existing_exposure"
                else:
                    order_state = "PENDING_ORDER"
                    order_reason = ""
        else:
            order_state = "ORDER_SKIPPED"
            order_reason = "neutral_signal"

        record = {
            "date":                    now.strftime("%Y-%m-%d %H:%M:%S"),
            "ticker":                  ticker,
            "signal":                  signal_val,
            "confidence":              consensus["confidence"],
            "methods_long":            consensus.get("methods_long", ""),
            "methods_short":           consensus.get("methods_short", ""),
            "methods_neutral":         consensus.get("methods_neutral", ""),
            "rationale":               consensus.get("rationale", ""),
            "target_price":            consensus.get("target_price"),
            "stop_loss":               consensus.get("stop_loss"),
            "entry_limit_price":       consensus.get("entry_limit_price"),
            "high_model_disagreement": int(bool(consensus.get("high_model_disagreement", False))),
            "horizon_hours":           horizon_hours,
            "eval_target_date":        eval_target_date,
            "eval_status":             "PENDING",
            "run_id":                  run_id,
            "original_run_id":         original_run_id,
            "order_state":             order_state,
            "order_reason":            order_reason,
            "filter_reasons":          consensus.get("filter_reasons_json", "[]"),
            "models_long_count":       consensus.get("models_long_count"),
            "models_short_count":      consensus.get("models_short_count"),
            "minority_weight_pct":     consensus.get("minority_weight_pct"),
            "expected_r":              consensus.get("expected_r"),
            "active_settings_json":    consensus.get("active_settings_json", "{}"),
            "market_regime":           consensus.get("market_regime"),
        }
        
        # Save all forecast links with weights (including filtered)
        link_data_list = consensus.get("_forecast_link_data", [])
        for link_data in link_data_list:
            db_manager.link_forecast_to_run(**link_data)
        
        return db_manager.save_consensus(record)
    except Exception as e:
        logger.error(f"Error saving consensus for {ticker}: {e}")
        return False


def build_method_and_model_stats(db_manager, days_back: int = 30) -> tuple:
    """Build method_stats and model_stats dicts used by calculate_consensus.

    Extracted from forecast_runner.process_ticker and consensus_recalc._process_group
    to eliminate code duplication (fix #6).

    Returns:
        (method_stats, model_stats)
        method_stats: {method: {"win_rate": float, "timeframe_hours": int}}
        model_stats:  {model_name: {"ema_accuracy": float}}
    """
    import pandas as pd
    from scripts.core.unified_logs_manager import get_forecast_statistics

    stats = get_forecast_statistics(db_manager, days_back=days_back)
    accuracy = stats.get("accuracy", {})
    method_stats = {
        m: {"win_rate": accuracy.get(m, 50.0) / 100.0}
        for m in stats.get("methods", {})
    }
    try:
        with db_manager._connect() as _con:
            _mc = pd.read_sql_query(
                "SELECT method, timeframe_hours FROM method_config WHERE active=1", _con
            )
        for _, row in _mc.iterrows():
            m = row["method"]
            if m not in method_stats:
                method_stats[m] = {}
            method_stats[m]["timeframe_hours"] = int(row["timeframe_hours"])
    except Exception as _e:
        logger.warning(f"build_method_and_model_stats: could not load method_config: {_e}")

    model_stats = {}
    try:
        with db_manager._connect() as _con:
            _prov = pd.read_sql_query(
                "SELECT name, ema_accuracy FROM providers WHERE active=1 AND ema_accuracy IS NOT NULL", _con
            )
        for _, row in _prov.iterrows():
            m = str(row["name"])
            if row["ema_accuracy"] is not None:
                model_stats[m] = {"ema_accuracy": float(row["ema_accuracy"])}
    except Exception as _e:
        logger.warning(f"build_method_and_model_stats: could not load providers ema_accuracy: {_e}")

    return method_stats, model_stats
