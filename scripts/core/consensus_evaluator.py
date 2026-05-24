"""
Модуль оценки консенсусных прогнозов.

Логика:
1. Выбирает записи consensus WHERE eval_status = 'PENDING' AND eval_target_date <= now
2. Загружает фактические данные (price_data) за eval_target_date
3. Определяет entry_price_actual (close бара на дату консенсуса)
4. Рассчитывает target_hit, stop_hit, direction_correct, pnl_pct, r_multiple
5. Обновляет запись: eval_status = 'EVALUATED' | 'NO_DATA'
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd

from scripts.core.mae_mfe import compute_mae_mfe_pct

logger = logging.getLogger(__name__)


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _mae_mfe_for_eval(
    signal: str,
    entry: Optional[float],
    actual_high: float,
    actual_low: float,
) -> Tuple[Optional[float], Optional[float]]:
    if entry is None or entry <= 0:
        return None, None
    return compute_mae_mfe_pct(signal, entry, actual_high, actual_low)


def _compute_r_multiple(pnl_pct: float, entry: float, stop: float, signal: str) -> Optional[float]:
    """R-multiple = PnL / distance_to_stop (both in %)."""
    try:
        if not entry or not stop or entry <= 0 or stop <= 0:
            return None
        risk_pct = abs(entry - stop) / entry * 100
        if risk_pct == 0:
            return None
        return round(pnl_pct / risk_pct, 3)
    except Exception:
        return None


def evaluate_consensus_records(db_manager) -> int:
    """Evaluate all PENDING consensus records whose eval_target_date has passed.

    Returns:
        int: number of records evaluated
    """
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        df = db_manager.consensus_repo.fetch_pending_for_evaluation(now_str)

        if df.empty:
            logger.info("consensus_evaluator: no pending records ready for evaluation")
            return 0

        total = len(df)
        logger.info(f"consensus_evaluator: starting evaluation of {total} pending records")

        evaluated = 0
        errors = 0
        no_data = 0

        for idx, row in df.iterrows():
            rec_id    = int(row["id"])
            ticker    = str(row["ticker"] or "")
            signal    = str(row["signal"] or "NEUTRAL").upper()
            cons_date = str(row["date"] or "")
            eval_date = str(row["eval_target_date"] or "")
            target_price = _to_float(row.get("target_price"))
            stop_loss    = _to_float(row.get("stop_loss"))
            entry_limit_price = _to_float(row.get("entry_limit_price"))
            horizon_hours = row.get("horizon_hours")
            if horizon_hours is not None:
                try:
                    horizon_hours = int(horizon_hours)
                except (TypeError, ValueError):
                    horizon_hours = None

            logger.info(f"consensus_evaluator: [{idx+1}/{total}] processing id={rec_id} {ticker} {signal} target_date={eval_date}")

            try:
                result_status = _evaluate_one(
                    db_manager=db_manager,
                    rec_id=rec_id,
                    ticker=ticker,
                    signal=signal,
                    cons_date=cons_date,
                    eval_target_date=eval_date,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    entry_limit_price=entry_limit_price,
                    horizon_hours=horizon_hours,
                )
                if result_status == "NO_DATA":
                    no_data += 1
                    logger.info(f"consensus_evaluator: [{idx+1}/{total}] id={rec_id} → NO_DATA (no price data)")
                elif result_status == "NO_DATA_INTRADAY":
                    no_data += 1
                    logger.info(f"consensus_evaluator: [{idx+1}/{total}] id={rec_id} → NO_DATA_INTRADAY (intraday horizon needs intraday bars)")
                elif result_status == "PENDING":
                    logger.info(f"consensus_evaluator: [{idx+1}/{total}] id={rec_id} → PENDING (data not yet available)")
                else:
                    evaluated += 1
                    logger.info(f"consensus_evaluator: [{idx+1}/{total}] id={rec_id} → EVALUATED")
            except Exception as e:
                errors += 1
                logger.error(f"consensus_evaluator: [{idx+1}/{total}] error evaluating id={rec_id}: {e}")

        logger.info(f"consensus_evaluator: completed. evaluated={evaluated}/{total}, no_data={no_data}, errors={errors}")
        return evaluated

    except Exception as e:
        logger.error(f"consensus_evaluator: top-level error: {e}")
        return 0


def _load_price_data_from_db(db_manager, ticker: str, date_from: str) -> list:
    """Load price bars from price_data table for a ticker, starting from date_from."""
    try:
        with db_manager._connect() as con:
            rows = con.execute(
                "SELECT date, open, high, low, close, volume FROM price_data "
                "WHERE ticker = ? AND date >= ? ORDER BY date",
                (ticker, date_from),
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                "date":   r[0],
                "open":   r[1],
                "high":   r[2],
                "low":    r[3],
                "close":  r[4],
                "volume": r[5],
            })
        return result
    except Exception as e:
        logger.warning(f"consensus_evaluator: db price_data query failed for {ticker}: {e}")
        return []


def _load_intraday_from_db(db_manager, ticker: str, dt_from: str, interval: str = "1h") -> list:
    """Load hourly bars from price_data_intraday for ticker starting at dt_from."""
    try:
        with db_manager._connect() as con:
            rows = con.execute(
                "SELECT datetime, open, high, low, close, volume FROM price_data_intraday "
                "WHERE ticker = ? AND interval = ? AND datetime >= ? ORDER BY datetime",
                (ticker, interval, dt_from),
            ).fetchall()
        return [
            {"datetime": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"consensus_evaluator: intraday db query failed for {ticker}: {e}")
        return []


def _find_first_hit_intraday(bars: list, signal: str, target_price: Optional[float], stop_loss: Optional[float]):
    """Scan hourly bars in order; return (first_hit, exit_price, bar) for first target or stop breach."""
    for bar in bars:
        high = float(bar.get("high") or 0)
        low  = float(bar.get("low") or 0)
        close = float(bar.get("close") or 0)
        if signal == "LONG":
            if target_price and high >= target_price:
                return "target", target_price, bar
            if stop_loss and low <= stop_loss:
                return "stop", stop_loss, bar
        elif signal == "SHORT":
            if target_price and low <= target_price:
                return "target", target_price, bar
            if stop_loss and high >= stop_loss:
                return "stop", stop_loss, bar
    return None, None, bars[-1] if bars else None


def _evaluate_one_intraday(
    db_manager,
    rec_id: int,
    ticker: str,
    signal: str,
    cons_date: str,
    eval_target_date: str,
    target_price: Optional[float],
    stop_loss: Optional[float],
    entry_limit_price: Optional[float],
    horizon_hours: int,
) -> str:
    """Evaluate a consensus record using hourly bars (horizon < 24h)."""
    try:
        target_dt = datetime.fromisoformat(eval_target_date[:19])
    except Exception:
        logger.warning(f"consensus_evaluator: bad eval_target_date '{eval_target_date}' for id={rec_id}")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    # Start loading from cons_date (beginning of the trade window)
    dt_from = cons_date[:19] if cons_date else eval_target_date[:19]

    bars = _load_intraday_from_db(db_manager, ticker, dt_from)
    if not bars:
        logger.warning(f"consensus_evaluator: no intraday bars for {ticker} id={rec_id} from {dt_from}")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    # Filter bars up to eval_target_date
    eval_dt_str = eval_target_date[:19]
    window_bars = [b for b in bars if str(b["datetime"])[:19] <= eval_dt_str]
    if not window_bars:
        logger.warning(f"consensus_evaluator: no intraday bars for {ticker} id={rec_id} in window")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    first_bar  = window_bars[0]
    last_bar   = window_bars[-1]

    entry_price_actual = entry_limit_price or float(first_bar.get("close") or 0)
    actual_open  = float(first_bar.get("open") or 0)
    actual_close = float(last_bar.get("close") or 0)
    actual_high  = max(float(b.get("high") or 0) for b in window_bars)
    actual_low   = min(float(b.get("low") or 1e9) for b in window_bars)
    actual_date  = str(last_bar["datetime"])[:10]

    first_hit, exit_price, _ = _find_first_hit_intraday(window_bars, signal, target_price, stop_loss)
    if exit_price is None:
        exit_price = actual_close

    target_hit = first_hit == "target" or (signal == "LONG" and actual_high >= (target_price or 1e18)) or (signal == "SHORT" and actual_low <= (target_price or 0))
    stop_hit   = first_hit == "stop"  or (signal == "LONG" and actual_low <= (stop_loss or 0)) or (signal == "SHORT" and actual_high >= (stop_loss or 1e18))
    # Prefer first_hit determination for target_hit/stop_hit when ambiguous
    if first_hit == "target":
        target_hit = True
    elif first_hit == "stop":
        stop_hit = True

    exit_successful = None
    if signal in ("LONG", "SHORT"):
        exit_successful = 1 if first_hit == "target" else (0 if first_hit == "stop" else None)

    direction_correct = False
    entry = entry_price_actual
    if entry and entry > 0:
        if signal == "LONG":
            direction_correct = actual_close > entry
        elif signal == "SHORT":
            direction_correct = actual_close < entry

    pnl_pct = 0.0
    if entry and entry > 0 and exit_price > 0:
        if signal == "LONG":
            pnl_pct = round((exit_price - entry) / entry * 100, 2)
        elif signal == "SHORT":
            pnl_pct = round((entry - exit_price) / entry * 100, 2)

    r_multiple = _compute_r_multiple(pnl_pct, entry, stop_loss, signal) if stop_loss else None
    mae_pct, mfe_pct = _mae_mfe_for_eval(signal, entry, actual_high, actual_low)

    _save_eval(
        db_manager=db_manager,
        rec_id=rec_id,
        eval_status="EVALUATED",
        actual_date=actual_date,
        actual_open=actual_open,
        actual_close=actual_close,
        actual_high=actual_high,
        actual_low=actual_low,
        entry_price_actual=entry_price_actual,
        target_hit=int(target_hit),
        stop_hit=int(stop_hit),
        first_hit=first_hit,
        exit_successful=exit_successful,
        direction_correct=int(direction_correct),
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
        mae_pct=mae_pct,
        mfe_pct=mfe_pct,
    )
    logger.info(
        f"consensus_evaluator: [intraday] id={rec_id} {ticker} {signal} → "
        f"dir={direction_correct} target_hit={target_hit} stop_hit={stop_hit} "
        f"first_hit={first_hit} pnl={pnl_pct:.2f}% MAE={mae_pct} MFE={mfe_pct} R={r_multiple}"
    )
    return "EVALUATED"


def _evaluate_one(
    db_manager,
    rec_id: int,
    ticker: str,
    signal: str,
    cons_date: str,
    eval_target_date: str,
    target_price: Optional[float],
    stop_loss: Optional[float],
    entry_limit_price: Optional[float] = None,
    horizon_hours: Optional[int] = None,
) -> str:
    """Evaluate one consensus record and persist results. Returns status: 'EVALUATED' or 'NO_DATA'."""
    # --- Intraday path: horizon < 24h → use hourly bars ---
    if horizon_hours and horizon_hours < 24:
        return _evaluate_one_intraday(
            db_manager=db_manager,
            rec_id=rec_id,
            ticker=ticker,
            signal=signal,
            cons_date=cons_date,
            eval_target_date=eval_target_date,
            target_price=target_price,
            stop_loss=stop_loss,
            entry_limit_price=entry_limit_price,
            horizon_hours=horizon_hours,
        )

    # --- Load price data around eval_target_date ---
    try:
        target_dt = datetime.fromisoformat(eval_target_date[:19])
    except Exception:
        logger.warning(f"consensus_evaluator: bad eval_target_date '{eval_target_date}' for id={rec_id}")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    # Date window: from consensus date (or 30 days before target)
    cons_date_str = cons_date[:10] if cons_date else ""
    if cons_date_str:
        date_from = cons_date_str
    else:
        from datetime import timedelta
        date_from = (target_dt - timedelta(days=30)).strftime("%Y-%m-%d")

    # Try DB cache first (fast, no network)
    price_data = _load_price_data_from_db(db_manager, ticker, date_from)

    # Fallback to fetch_price_data if DB has no data
    if not price_data:
        today = datetime.now().date()
        days_back = (today - target_dt.date()).days + 14
        days_needed = max(days_back, 30)
        try:
            from scripts.core.bybit_data_loader import fetch_price_data_bybit as fetch_price_data
            price_data = fetch_price_data(ticker, days=days_needed, db_manager=db_manager)
        except Exception as e:
            logger.warning(f"consensus_evaluator: fetch_price_data failed for {ticker}: {e}")

    if not price_data:
        logger.warning(f"consensus_evaluator: no price data for {ticker} id={rec_id}")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    # --- Find bar for eval_target_date ---
    target_date_str = target_dt.strftime("%Y-%m-%d")
    cons_date_only = cons_date[:10] if cons_date else ""
    actual_bar = _find_bar(price_data, target_date_str)

    # If no exact bar and target date is already in the past, use nearest available bar
    # (handles weekends, holidays — next/prev trading day)
    if actual_bar is None and target_dt.date() <= datetime.now().date():
        actual_bar = _find_nearest_bar_on_or_after(price_data, target_date_str)
        if actual_bar is not None:
            logger.info(
                f"consensus_evaluator: no exact bar for {ticker} on {target_date_str}, "
                f"using nearest: {actual_bar['date']}"
            )

    # Validate: actual_bar must be strictly after consensus date
    # If the only available bar is on/before cons_date, the evaluation data hasn't arrived yet
    if actual_bar is not None and cons_date_only:
        actual_bar_date = actual_bar["date"]
        if hasattr(actual_bar_date, "strftime"):
            actual_bar_date = actual_bar_date.strftime("%Y-%m-%d")
        else:
            actual_bar_date = str(actual_bar_date)[:10]
        if actual_bar_date <= cons_date_only:
            logger.info(
                f"consensus_evaluator: id={rec_id} {ticker} actual_bar={actual_bar_date} "
                f"is not after cons_date={cons_date_only}, keeping PENDING"
            )
            _save_eval(db_manager, rec_id, eval_status="PENDING")
            return "PENDING"

    if actual_bar is None:
        logger.warning(f"consensus_evaluator: no bar for {ticker} on {target_date_str} (target in future or no data)")
        _save_eval(db_manager, rec_id, eval_status="NO_DATA")
        return "NO_DATA"

    actual_close = float(actual_bar["close"])
    actual_high  = float(actual_bar["high"])
    actual_low   = float(actual_bar["low"])
    actual_open  = float(actual_bar["open"])
    actual_date  = str(actual_bar["date"])
    if hasattr(actual_bar["date"], "strftime"):
        actual_date = actual_bar["date"].strftime("%Y-%m-%d")

    # --- entry_price_actual: price used for PnL calculation ---
    # Priority: 1) entry_limit_price from consensus (real trading base)
    #           2) close of consensus date (historical fallback)
    #           3) last bar before eval_target_date (data availability fallback)
    #           4) actual_close (last resort)
    entry_price_actual: Optional[float] = None

    # 1) Use entry_limit_price from consensus as primary base (matches real trading)
    if entry_limit_price and entry_limit_price > 0:
        entry_price_actual = entry_limit_price
        logger.debug(f"consensus_evaluator: id={rec_id} using entry_limit_price={entry_limit_price} as base")
    elif cons_date:
        try:
            cons_date_str = cons_date[:10]
            entry_bar = _find_bar(price_data, cons_date_str, fallback_nearest=False)
            if entry_bar:
                entry_price_actual = float(entry_bar["close"])
                logger.debug(f"consensus_evaluator: id={rec_id} using cons_date close={entry_price_actual}")
        except Exception:
            pass

    # Fallback: last bar strictly before eval_target_date
    if entry_price_actual is None:
        entry_bar = _find_last_bar_before(price_data, target_date_str)
        if entry_bar:
            entry_price_actual = float(entry_bar["close"])
            logger.debug(f"consensus_evaluator: id={rec_id} using last bar before target={entry_price_actual}")

    # Use entry_price_actual as reference; fallback to actual_close
    entry = entry_price_actual or actual_close

    # --- target_hit / stop_hit ---
    target_hit = False
    stop_hit   = False

    if signal == "LONG":
        if target_price:
            target_hit = actual_high >= target_price
        if stop_loss:
            stop_hit = actual_low <= stop_loss
    elif signal == "SHORT":
        if target_price:
            target_hit = actual_low <= target_price
        if stop_loss:
            stop_hit = actual_high >= stop_loss

    # --- First Hit Analysis (when both hit on same day) ---
    # Determine which level was hit first using distance from open
    first_hit = None  # 'target' | 'stop' | None
    if target_hit and stop_hit and actual_open:
        # Calculate distance from open to target and stop
        if signal == "LONG":
            dist_to_target = abs(target_price - actual_open) if target_price else None
            dist_to_stop = abs(stop_loss - actual_open) if stop_loss else None
        else:  # SHORT
            dist_to_target = abs(actual_open - target_price) if target_price else None
            dist_to_stop = abs(actual_open - stop_loss) if stop_loss else None
        
        if dist_to_target and dist_to_stop:
            # The level closer to open was hit first (conservatively)
            if dist_to_target < dist_to_stop:
                first_hit = "target"
            elif dist_to_stop < dist_to_target:
                first_hit = "stop"
            else:
                # Equal distance - ambiguous, default to stop (conservative)
                first_hit = "stop"
    elif target_hit and not stop_hit:
        first_hit = "target"
    elif stop_hit and not target_hit:
        first_hit = "stop"

    # pnl_pct: use first_hit to determine exit price when both levels were touched.
    # If only one level was hit, or neither, fall back to actual_close.
    if first_hit == "stop" and stop_loss:
        exit_price = stop_loss
    elif first_hit == "target" and target_price:
        exit_price = target_price
    else:
        exit_price = actual_close

    # exit_successful: True only when target was hit first (or only target hit)
    exit_successful = None
    if signal in ("LONG", "SHORT"):
        if first_hit == "target":
            exit_successful = 1
        elif first_hit == "stop":
            exit_successful = 0
        # else: neither hit (still open) → None

    # direction_correct: based on actual_close vs entry (independent of target/stop)
    direction_correct = False
    if signal == "LONG":
        direction_correct = actual_close > entry
    elif signal == "SHORT":
        direction_correct = actual_close < entry

    pnl_pct = 0.0
    if entry and entry > 0 and exit_price and exit_price > 0:
        if signal == "LONG":
            pnl_pct = round((exit_price - entry) / entry * 100, 2)
        elif signal == "SHORT":
            pnl_pct = round((entry - exit_price) / entry * 100, 2)

    r_multiple = _compute_r_multiple(pnl_pct, entry, stop_loss, signal) if stop_loss else None
    mae_pct, mfe_pct = _mae_mfe_for_eval(signal, entry, actual_high, actual_low)

    _save_eval(
        db_manager=db_manager,
        rec_id=rec_id,
        eval_status="EVALUATED",
        actual_date=actual_date,
        actual_open=actual_open,
        actual_close=actual_close,
        actual_high=actual_high,
        actual_low=actual_low,
        entry_price_actual=entry_price_actual,
        target_hit=int(target_hit),
        stop_hit=int(stop_hit),
        first_hit=first_hit,
        exit_successful=exit_successful,
        direction_correct=int(direction_correct),
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
        mae_pct=mae_pct,
        mfe_pct=mfe_pct,
    )
    logger.info(
        f"consensus_evaluator: id={rec_id} {ticker} {signal} → "
        f"dir={direction_correct} target_hit={target_hit} stop_hit={stop_hit} first_hit={first_hit} "
        f"pnl={pnl_pct:.2f}% MAE={mae_pct} MFE={mfe_pct} R={r_multiple}"
    )
    return "EVALUATED"


def _find_last_bar_before(price_data: list, date_str: str) -> Optional[dict]:
    """Return the last price bar whose date is strictly before date_str (YYYY-MM-DD)."""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None
    candidates = []
    for rec in price_data:
        d = rec["date"]
        if hasattr(d, "date"):
            d = d.date()
        elif isinstance(d, str):
            try:
                d = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except Exception:
                continue
        if d < target:
            candidates.append((d, rec))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def _find_nearest_bar_on_or_after(price_data: list, date_str: str) -> Optional[dict]:
    """Return the nearest bar on or after date_str. Falls back to last bar before if none found after."""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

    def _to_date(r):
        d = r["date"]
        if hasattr(d, "date"):
            return d.date()
        elif isinstance(d, str):
            try:
                return datetime.strptime(d[:10], "%Y-%m-%d").date()
            except Exception:
                return None
        return None

    on_or_after = [(d, r) for r in price_data if (d := _to_date(r)) is not None and d >= target]
    if on_or_after:
        on_or_after.sort(key=lambda x: x[0])
        return on_or_after[0][1]

    # Fallback: last bar before target date
    return _find_last_bar_before(price_data, date_str)


def _find_bar(price_data: list, date_str: str, fallback_nearest: bool = False) -> Optional[dict]:
    """Find price bar for given date_str (YYYY-MM-DD). Optionally return nearest."""
    for rec in price_data:
        d = rec["date"]
        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        if d_str == date_str:
            return rec

    if not fallback_nearest or not price_data:
        return None

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()

        def _dist(r):
            d = r["date"]
            if hasattr(d, "date"):
                d = d.date()
            elif isinstance(d, str):
                d = datetime.strptime(d[:10], "%Y-%m-%d").date()
            return abs((d - target).days)

        return min(price_data, key=_dist)
    except Exception:
        return None


def _save_eval(db_manager, rec_id: int, eval_status: str, **kwargs) -> None:
    """Persist evaluation results back to consensus table."""
    updates = {"eval_status": eval_status}
    updates.update(kwargs)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rec_id]
    try:
        with db_manager._connect() as con:
            con.execute(f"UPDATE consensus SET {set_clause} WHERE id = ?", values)
        logger.debug(f"consensus_evaluator: saved eval id={rec_id} status={eval_status}")
    except Exception as e:
        logger.error(f"consensus_evaluator: failed to save eval for id={rec_id}: {e}")
