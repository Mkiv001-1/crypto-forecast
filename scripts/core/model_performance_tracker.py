"""
Model performance tracker — updates EMA accuracy weights for AI providers.

After each evaluation cycle:
  ema_accuracy_new = alpha * outcome + (1 - alpha) * ema_accuracy_old

Where:
  alpha   = MODEL_WEIGHT_EMA_ALPHA (default 0.2)
  outcome = 1.0 if direction_correct else 0.0
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_EMA_ALPHA = 0.2
_DEFAULT_EMA_INIT  = 0.5   # Starting accuracy for new providers


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _get_ema_alpha(db_manager) -> float:
    try:
        v = db_manager.get_config_value("MODEL_WEIGHT_EMA_ALPHA")
        return float(v) if v is not None else _DEFAULT_EMA_ALPHA
    except Exception:
        return _DEFAULT_EMA_ALPHA


def update_provider_ema(
    db_manager,
    model_name: str,
    direction_correct: bool,
) -> Optional[float]:
    """
    Update EMA accuracy for a provider after one evaluation outcome.

    Args:
        db_manager:        SQLiteManager instance
        model_name:        provider.name as stored in the providers table
        direction_correct: True if the forecast direction was correct

    Returns:
        New EMA value, or None if provider not found.
    """
    alpha = _get_ema_alpha(db_manager)
    outcome = 1.0 if direction_correct else 0.0

    try:
        with sqlite3.connect(db_manager.db_file) as con:
            row = con.execute(
                "SELECT ema_accuracy, forecast_count FROM providers WHERE name=?",
                (model_name,)
            ).fetchone()

        if row is None:
            logger.warning(f"model_performance_tracker: provider '{model_name}' not found")
            return None

        old_ema    = row[0] if row[0] is not None else _DEFAULT_EMA_INIT
        old_count  = row[1] if row[1] is not None else 0
        new_ema    = round(alpha * outcome + (1 - alpha) * float(old_ema), 6)
        new_count  = old_count + 1
        now        = _now_utc()

        with sqlite3.connect(db_manager.db_file) as con:
            con.execute(
                "UPDATE providers SET ema_accuracy=?, ema_updated_at=?, forecast_count=? WHERE name=?",
                (new_ema, now, new_count, model_name)
            )

        logger.debug(
            f"model_performance_tracker: {model_name} ema {old_ema:.4f} → {new_ema:.4f} "
            f"(outcome={outcome}, n={new_count})"
        )
        return new_ema

    except Exception as e:
        logger.error(f"model_performance_tracker: update failed for '{model_name}': {e}")
        return None


def update_all_from_evaluations(db_manager) -> int:
    """
    Scan recently evaluated logs and update provider EMA weights.

    Looks for logs where direction_correct IS NOT NULL and the model column
    is not empty, updating each provider found.

    Returns count of providers updated.
    """
    updated = 0
    try:
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            # Only process logs that have a non-empty model column and were evaluated today
            rows = con.execute(
                """
                SELECT model, direction_correct
                FROM logs
                WHERE direction_correct IS NOT NULL
                  AND model IS NOT NULL AND model != ''
                  AND DATE(actual_date) = DATE('now')
                """
            ).fetchall()

        for row in rows:
            model_name = row["model"]
            is_correct = bool(row["direction_correct"])
            result = update_provider_ema(db_manager, model_name, is_correct)
            if result is not None:
                updated += 1

        logger.info(f"model_performance_tracker: updated {updated} provider EMA weights")
    except Exception as e:
        logger.error(f"model_performance_tracker: update_all_from_evaluations failed: {e}")

    return updated


def get_provider_weights(db_manager) -> dict:
    """
    Return dict {provider_name: ema_accuracy} for all active AI providers.
    Used by consensus.py to weight signals.
    """
    weights = {}
    try:
        with sqlite3.connect(db_manager.db_file) as con:
            rows = con.execute(
                "SELECT name, ema_accuracy FROM providers WHERE type='ai' AND active=1"
            ).fetchall()
        for name, ema in rows:
            weights[name] = float(ema) if ema is not None else _DEFAULT_EMA_INIT
    except Exception as e:
        logger.error(f"model_performance_tracker: get_provider_weights failed: {e}")
    return weights
