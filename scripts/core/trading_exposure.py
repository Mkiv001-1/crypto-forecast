"""Trading exposure checks — open orders and positions per ticker."""

from typing import Tuple


def skip_forecast_when_exposed(db_manager) -> bool:
    """Whether to skip LLM forecasts when the ticker already has exposure."""
    try:
        dataset = db_manager.get_config_value("META_DATASET_MODE", "false")
        if str(dataset).strip().lower() in ("1", "true", "yes", "on"):
            return False
    except Exception:
        pass
    try:
        raw = db_manager.get_config_value("SKIP_FORECAST_WHEN_EXPOSED", "true")
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return True


def ticker_has_trading_exposure(db_manager, ticker: str) -> Tuple[bool, str]:
    """
    True if ticker has an active entry order or open position in local DB.

    Uses OrdersRepository.has_open_order_for_ticker (QUEUED/SUBMITTED or FILLED_ENTRY + OPEN trade).
    """
    try:
        if db_manager.orders_repo.has_open_order_for_ticker(ticker):
            return True, "open_order_or_position"
    except Exception:
        pass
    return False, ""
