"""
Модуль ретроспективного пересчета консенсуса.

Для каждой группы (дата, тикер) из logs:
1. Вычисляет консенсус из прогнозов
2. Сохраняет запись
3. Если eval_target_date уже в прошлом — сразу оценивает (target_hit, direction_correct, pnl и т.д.)
"""

import logging
from datetime import datetime, timedelta
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


def recalculate_consensus(
    db_manager,
    date_from: str = None,
    date_to: str = None,
    tickers: List[str] = None,
    force: bool = False,
) -> dict:
    """
    Пересчитать консенсус из прогнозов и сразу оценить записи с датой в прошлом.

    Для каждой группы (created_date, ticker):
      1. Вычисляет консенсус из прогнозов (signal, target, stop и т.д.)
      2. Сохраняет/обновляет запись в consensus
      3. Если eval_target_date <= now — немедленно запускает оценку

    Args:
        db_manager: SQLiteManager instance
        date_from: начало периода (YYYY-MM-DD), по умолчанию 30 дней назад
        date_to: конец периода (YYYY-MM-DD), по умолчанию сегодня
        tickers: список тикеров, по умолчанию все
        force: если True — перезаписывает даже EVALUATED записи

    Returns:
        dict: created, updated, skipped, evaluated, errors, total_groups
    """
    try:
        if date_to is None:
            date_to = datetime.now().strftime("%Y-%m-%d")
        if date_from is None:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        logger.info(f"consensus_recalc: starting for {date_from} to {date_to}, tickers={tickers}, force={force}")

        logs_df = _load_forecast_logs(db_manager, date_from, date_to, tickers)
        if logs_df.empty:
            logger.info("consensus_recalc: no forecast logs found")
            return {"created": 0, "updated": 0, "skipped": 0, "evaluated": 0, "errors": 0, "total_groups": 0}

        logger.info(f"consensus_recalc: loaded {len(logs_df)} forecast logs")

        logs_df["created_date"] = logs_df["created_at"].str[:10]
        groups = logs_df.groupby(["created_date", "ticker"])
        total_groups = len(groups)
        logger.info(f"consensus_recalc: processing {total_groups} (date, ticker) groups")

        stats = {"created": 0, "updated": 0, "skipped": 0, "evaluated": 0, "errors": 0, "total_groups": total_groups}

        for idx, ((created_date, ticker), group_df) in enumerate(groups, 1):
            try:
                result, evaluated = _process_group(db_manager, created_date, ticker, group_df, force=force)
                if result in stats:
                    stats[result] += 1
                if evaluated:
                    stats["evaluated"] += 1
                logger.info(f"consensus_recalc: [{idx}/{total_groups}] {created_date} {ticker} → {result}" +
                            (" (evaluated)" if evaluated else ""))
            except Exception as e:
                logger.error(f"consensus_recalc: error processing {created_date} {ticker}: {e}")
                stats["errors"] += 1

        logger.info(
            f"consensus_recalc: done. created={stats['created']}, updated={stats['updated']}, "
            f"skipped={stats['skipped']}, evaluated={stats['evaluated']}, errors={stats['errors']}"
        )
        return stats

    except Exception as e:
        logger.exception(f"consensus_recalc: top-level error: {e}")
        return {"created": 0, "updated": 0, "skipped": 0, "evaluated": 0, "errors": 1, "total_groups": 0}


def _load_forecast_logs(
    db_manager,
    date_from: str,
    date_to: str,
    tickers: List[str] = None,
) -> pd.DataFrame:
    """Load forecast logs from the database."""
    try:
        sql = """
            SELECT id, created_at, forecast_date, ticker, method, model,
                   side, confidence, entry_price, exit_target, exit_stop,
                   target_price, stop_loss, rationale, run_id
            FROM logs
            WHERE created_at >= ?
              AND created_at < ?
              AND status IN ('NEW', 'PENDING', 'CONFIRMED', 'EVALUATED')
        """
        params = [f"{date_from} 00:00:00", f"{date_to} 23:59:59"]
        if tickers:
            placeholders = ",".join(["?"] * len(tickers))
            sql += f" AND ticker IN ({placeholders})"
            params.extend(tickers)
        with db_manager._connect() as con:
            df = pd.read_sql_query(sql, con, params=params)
        return df
    except Exception as e:
        logger.error(f"consensus_recalc: failed to load logs: {e}")
        return pd.DataFrame()


def _process_group(
    db_manager,
    created_date: str,
    ticker: str,
    group_df: pd.DataFrame,
    force: bool = False,
) -> tuple:
    """
    Process one (date, ticker) group — mirrors process_ticker() from forecast_runner exactly:
      1. Build method_stats with real win_rate + ema_accuracy (same as scheduler)
      2. Get current_price from price_data for anomaly filter
      3. calculate_consensus(raw_forecasts, method_stats, current_price)
      4. save_consensus(..., override_date=created_date)  ← identical to scheduler, just historical date
      5. If eval_target_date is now in the past — immediately evaluate

    Returns: (result: str, evaluated: bool)
      result = 'created' | 'updated' | 'skipped'
    """
    from scripts.core.consensus import calculate_consensus, save_consensus
    from scripts.core.unified_logs_manager import get_forecast_statistics

    # --- Skip already-processed records unless force ---
    with db_manager._connect() as con:
        existing = con.execute(
            "SELECT id, eval_status FROM consensus WHERE date LIKE ? AND ticker = ?",
            (f"{created_date}%", ticker)
        ).fetchone()

    existing_id = existing[0] if existing else None
    existing_eval_status = existing[1] if existing else None

    if existing and not force and existing_eval_status in ("EVALUATED", "PENDING"):
        logger.debug(f"consensus_recalc: skipping {created_date} {ticker} (status={existing_eval_status})")
        return "skipped", False

    # --- Create run for this recalc ---
    run_id = db_manager.create_forecast_run('recalc', 1)
    
    # --- Build raw_forecasts from logs (same fields as generate_multi_model_forecasts output) ---
    raw_forecasts = []
    log_ids = {}  # Map forecast index to log_id
    
    # Track original_run_id from the source forecasts (for analytical JOINs)
    original_run_ids = set()
    for idx, row in group_df.iterrows():
        log_id = row.get('id')
        log_ids[idx] = log_id
        raw_forecasts.append({
            "ticker":            row["ticker"],
            "method":            row["method"],
            "model":             row["model"],
            "side":              row["side"],
            "confidence":        float(row["confidence"]) if pd.notna(row["confidence"]) else 50.0,
            "entry_price":       row.get("entry_price"),
            "exit_target":       row.get("exit_target"),
            "target_price":      row["target_price"] if pd.notna(row["target_price"]) else None,
            "stop_loss":         row["stop_loss"] if pd.notna(row["stop_loss"]) else None,
            "rationale":         row["rationale"] or "",
            "log_id":            log_id,
            "run_id":            run_id,
        })
        # Collect original run_id if present
        orig_rid = row.get('run_id')
        if pd.notna(orig_rid) and orig_rid:
            original_run_ids.add(int(orig_rid))

    if not raw_forecasts:
        return "skipped", False
    
    # Determine original_run_id: if all forecasts from same run, use it; else None
    original_run_id = None
    if len(original_run_ids) == 1:
        original_run_id = original_run_ids.pop()
    elif len(original_run_ids) > 1:
        logger.warning(f"consensus_recalc: mixed original run_ids {original_run_ids} for {ticker} {created_date}, not setting original_run_id")

    # --- Build method_stats — same as forecast_runner.process_ticker ---
    stats = get_forecast_statistics(db_manager, days_back=30)
    accuracy = stats.get("accuracy", {})
    method_stats = {
        m: {"win_rate": accuracy.get(m, 50.0) / 100.0}
        for m in stats.get("methods", {})
    }
    # Enrich with timeframe_hours from method_config
    try:
        with db_manager._connect() as _con:
            _mc = pd.read_sql_query(
                "SELECT method, timeframe_hours FROM method_config WHERE active=1", _con
            )
        for _, r in _mc.iterrows():
            m = r["method"]
            if m not in method_stats:
                method_stats[m] = {}
            method_stats[m]["timeframe_hours"] = int(r["timeframe_hours"])
    except Exception as e:
        logger.warning(f"consensus_recalc: could not load method_config: {e}")
    # Build model_stats keyed by AI model name (providers.name) for ema_accuracy lookup
    model_stats = {}
    try:
        with db_manager._connect() as _con:
            _prov = pd.read_sql_query(
                "SELECT name, ema_accuracy FROM providers WHERE active=1 AND ema_accuracy IS NOT NULL", _con
            )
        for _, r in _prov.iterrows():
            m = str(r["name"])
            if r["ema_accuracy"] is not None:
                model_stats[m] = {"ema_accuracy": float(r["ema_accuracy"])}
    except Exception as e:
        logger.warning(f"consensus_recalc: could not load providers ema_accuracy: {e}")

    # --- Get current_price for anomaly filter (close of created_date bar) ---
    current_price = 0.0
    try:
        with db_manager._connect() as _con:
            row = _con.execute(
                "SELECT close FROM price_data WHERE ticker = ? AND date LIKE ? ORDER BY date DESC LIMIT 1",
                (ticker, f"{created_date}%")
            ).fetchone()
            if row:
                current_price = float(row[0])
    except Exception:
        pass

    # --- Calculate consensus — with run_id for tracking ---
    cons = calculate_consensus(raw_forecasts, method_stats, current_price=current_price, 
                               run_id=run_id, log_ids=log_ids, model_stats=model_stats)

    # --- Save via save_consensus with override_date and run_id ---
    # If existing record, delete it first so save_consensus can insert fresh
    if existing_id:
        try:
            with db_manager._connect() as con:
                con.execute("DELETE FROM consensus WHERE id = ?", (existing_id,))
        except Exception as e:
            logger.warning(f"consensus_recalc: could not delete existing id={existing_id}: {e}")

    save_result = save_consensus(db_manager, ticker, cons, method_stats=method_stats, 
                                 override_date=created_date, run_id=run_id,
                                 original_run_id=original_run_id)
    
    # Complete the run
    if run_id:
        db_manager.complete_forecast_run(run_id, status='completed', tickers_processed=1, 
                                        consensus_count=1 if save_result else 0)
    
    result = "updated" if existing_id else "created"

    # --- Get the id of the just-saved record ---
    with db_manager._connect() as con:
        saved = con.execute(
            "SELECT id, eval_target_date FROM consensus WHERE date LIKE ? AND ticker = ? ORDER BY id DESC LIMIT 1",
            (f"{created_date}%", ticker)
        ).fetchone()

    if not saved:
        logger.warning(f"consensus_recalc: could not find saved record for {ticker} {created_date}")
        return result, False

    saved_id = saved[0]
    eval_target_date = saved[1]

    # --- Immediately evaluate if eval_target_date is already in the past ---
    evaluated = False
    try:
        eval_target_dt = datetime.fromisoformat(eval_target_date[:19])
        if eval_target_dt <= datetime.now():
            from scripts.core.consensus_evaluator import _evaluate_one
            status = _evaluate_one(
                db_manager=db_manager,
                rec_id=saved_id,
                ticker=ticker,
                signal=cons["signal"],
                cons_date=f"{created_date} 00:00:00",
                eval_target_date=eval_target_date,
                target_price=cons.get("target_price"),
                stop_loss=cons.get("stop_loss"),
            )
            evaluated = status == "EVALUATED"
            logger.debug(f"consensus_recalc: immediate eval id={saved_id} → {status}")
    except Exception as e:
        logger.warning(f"consensus_recalc: immediate eval failed for {ticker} {created_date}: {e}")

    return result, evaluated
