"""
Bybit Capital Provider — источник капитала для торговли на Bybit.

Использует Bybit API для получения баланса USDT.

Priority hierarchy:
  1. MANUAL_CAPITAL_OVERRIDE (if set and > 0)
  2. Bybit API wallet balance (real-time)
  3. Cached last-known value (with warning)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from scripts.core.bybit_worker import is_running as is_bybit_running

logger = logging.getLogger(__name__)

_FALLBACK_CAPITAL_CACHE: dict = {}


class CapitalUnavailableError(RuntimeError):
    """Raised when capital cannot be obtained and failsafe denies fallback."""


def _get_config(db_manager, key: str, default: str = "") -> str:
    try:
        v = db_manager.get_config_value(key)
        return v if v is not None else default
    except Exception:
        return default


def _manual_override(db_manager) -> Optional[float]:
    raw = _get_config(db_manager, "MANUAL_CAPITAL_OVERRIDE", "")
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return None


def _get_bybit_balance_sync(db_manager) -> Optional[dict]:
    """Fetch unified wallet from Bybit API (total equity + perp UPL)."""
    from scripts.core.bybit_unified_wallet import (
        fetch_unified_wallet_sync,
        cache_unified_wallet,
        usdt_available_balance,
    )

    if not is_bybit_running():
        logger.warning("bybit_capital_provider: Bybit worker not running")
        return None
    
    try:
        wallet = fetch_unified_wallet_sync()
        if wallet:
            cache_unified_wallet(db_manager, wallet)
            return {
                "equity": wallet.get("total_equity", 0),
                "available": usdt_available_balance(wallet),
                "unrealized_pnl": wallet.get("total_perp_upl", 0),
                "timestamp": wallet.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "wallet": wallet,
            }
    except Exception as e:
        logger.warning(f"bybit_capital_provider: Failed to fetch balance: {e}")
    
    return None


def get_available_capital(
    db_manager,
    *,
    allow_fallback: bool = True,
    min_capital: float = 0.0
) -> float:
    """
    Get available trading capital from Bybit.

    Priority:
        1. MANUAL_CAPITAL_OVERRIDE (if set and > 0)
        2. Bybit API wallet balance (USDT equity)
        3. Cached value (if allow_fallback=True)

    Args:
        db_manager: SQLiteManager instance
        allow_fallback: Whether to use cached value if API fails
        min_capital: Minimum required capital (fails if below)

    Returns:
        Available capital in USDT

    Raises:
        CapitalUnavailableError: If capital cannot be obtained and allow_fallback=False
    """
    # 1. Manual override
    manual = _manual_override(db_manager)
    if manual is not None:
        logger.info(f"bybit_capital_provider: Using MANUAL_CAPITAL_OVERRIDE = {manual:.2f} USDT")
        if manual < min_capital:
            raise CapitalUnavailableError(f"Manual capital {manual:.2f} below minimum {min_capital:.2f}")
        return manual

    # 2. Bybit API
    balance = _get_bybit_balance_sync(db_manager)
    if balance:
        equity = balance.get("equity", 0)
        available = balance.get("available", 0)
        unrealized = balance.get("unrealized_pnl", 0)
        
        logger.debug(
            f"bybit_capital_provider: Bybit equity={equity:.2f} USDT, "
            f"available={available:.2f}, unrealized_pnl={unrealized:.2f}"
        )
        
        # Use available balance for new positions
        usable_capital = available
        
        if usable_capital >= min_capital:
            # Cache the successful result
            _FALLBACK_CAPITAL_CACHE["value"] = usable_capital
            _FALLBACK_CAPITAL_CACHE["timestamp"] = balance.get("timestamp", "")
            return usable_capital
        else:
            raise CapitalUnavailableError(
                f"Bybit available balance {usable_capital:.2f} USDT below minimum {min_capital:.2f}"
            )

    # 3. Fallback to cached value
    if allow_fallback:
        cached = _FALLBACK_CAPITAL_CACHE.get("value")
        if cached is not None:
            logger.warning(f"bybit_capital_provider: Using cached capital = {cached:.2f} USDT")
            return cached

    raise CapitalUnavailableError(
        "Cannot obtain capital from Bybit API and no fallback available"
    )


def get_equity_with_unrealized(db_manager) -> tuple[float, float]:
    """
    Get total equity including unrealized PnL.
    
    Returns:
        (equity, unrealized_pnl)
    """
    manual = _manual_override(db_manager)
    if manual is not None:
        return manual, 0.0
    
    balance = _get_bybit_balance_sync(db_manager)
    if balance:
        return balance.get("equity", 0), balance.get("unrealized_pnl", 0)
    
    cached = _FALLBACK_CAPITAL_CACHE.get("value")
    if cached:
        return cached, 0.0
    
    return 0.0, 0.0


def get_net_liquidation(db_manager) -> float:
    """Return available capital as net liquidation equivalent. Returns 0.0 on failure."""
    try:
        return get_available_capital(db_manager)
    except CapitalUnavailableError:
        return 0.0


def get_portfolio_net_liquidation(db_manager) -> tuple:
    """Return (portfolio_value: float, capital_source: str) for position sizing."""
    manual = _manual_override(db_manager)
    if manual is not None:
        return manual, "manual_override"

    balance = _get_bybit_balance_sync(db_manager)
    if balance:
        equity = float(balance.get("equity", 0) or 0)
        if equity > 0:
            _FALLBACK_CAPITAL_CACHE["value"] = equity
            _FALLBACK_CAPITAL_CACHE["timestamp"] = balance.get("timestamp", "")
            return equity, "bybit"

    failsafe = _get_config(
        db_manager,
        "BYBIT_CAPITAL_FAILSAFE",
        _get_config(db_manager, "IB_CAPITAL_FAILSAFE", "manual_only"),
    )
    cached = _FALLBACK_CAPITAL_CACHE.get("value")
    if cached is not None:
        logger.warning(f"bybit_capital_provider: Using cached capital = {cached:.2f} USDT")
        return cached, "cached"

    if failsafe == "deny":
        raise CapitalUnavailableError("Bybit capital unavailable and BYBIT_CAPITAL_FAILSAFE=deny")
    raise CapitalUnavailableError("Cannot obtain capital from Bybit API and no fallback available")


def clear_capital_cache():
    """Clear the fallback capital cache."""
    _FALLBACK_CAPITAL_CACHE.clear()
    logger.info("bybit_capital_provider: Cache cleared")
