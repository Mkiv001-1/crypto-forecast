"""
Bybit Unified Trading wallet — total equity, perp UPL, and asset breakdown.

Used by portfolio history summary, account sync, and capital provider cache.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CONFIG_KEY = "BYBIT_UNIFIED_WALLET_JSON"


def fetch_unified_wallet_sync(*, timeout: float | None = None) -> Optional[Dict[str, Any]]:
    """Fetch live unified wallet via Bybit worker."""
    from scripts.core.bybit_worker import _DEFAULT_TIMEOUT, bybit_request_sync, is_running

    if timeout is None:
        timeout = _DEFAULT_TIMEOUT

    if not is_running():
        logger.debug("bybit_unified_wallet: worker not running")
        return None

    try:
        return bybit_request_sync("get_unified_wallet", timeout=timeout)
    except TimeoutError as e:
        logger.warning(
            "bybit_unified_wallet: fetch timed out after %.1fs (using cache if available): %r",
            timeout,
            e,
        )
        return None
    except Exception as e:
        logger.warning(
            "bybit_unified_wallet: fetch failed (%s): %r timeout=%.1f",
            type(e).__name__,
            e,
            timeout,
            exc_info=True,
        )
        return None


def cache_unified_wallet(db_manager: Any, wallet: Dict[str, Any]) -> None:
    """Persist last-known unified wallet JSON in config."""
    try:
        db_manager.set_config_value(CONFIG_KEY, json.dumps(wallet))
    except Exception as e:
        logger.warning(
            "bybit_unified_wallet: cache write failed (%s): %r",
            type(e).__name__,
            e,
            exc_info=True,
        )


def load_cached_unified_wallet(db_manager: Any) -> Optional[Dict[str, Any]]:
    """Load last cached unified wallet from config."""
    try:
        raw = db_manager.get_config_value(CONFIG_KEY, "") or ""
        if not raw:
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "bybit_unified_wallet: cache read failed (%s): %r",
            type(e).__name__,
            e,
            exc_info=True,
        )
        return None


def get_unified_wallet(
    db_manager: Any,
    *,
    live: bool = True,
    timeout: float | None = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    """
    Return unified wallet data and source tag ('live' | 'cached' | 'none').
    """
    if live:
        wallet = fetch_unified_wallet_sync(timeout=timeout)
        if wallet:
            cache_unified_wallet(db_manager, wallet)
            return wallet, "live"

    cached = load_cached_unified_wallet(db_manager)
    if cached:
        return cached, "cached"

    return None, "none"


def usdt_available_balance(wallet: Dict[str, Any]) -> float:
    """Extract USDT available balance from unified wallet coins list."""
    for coin in wallet.get("coins") or []:
        if coin.get("coin") == "USDT":
            return float(coin.get("available_balance") or 0)
    return float(wallet.get("total_available_balance") or 0)


def build_portfolio_summary_record(
    wallet: Dict[str, Any],
    *,
    positions_count: int = 0,
    account: str = "BYBIT",
) -> Dict[str, Any]:
    """Build portfolio_history summary row from unified wallet snapshot."""
    ts = wallet.get("timestamp") or datetime.now(timezone.utc).isoformat()
    total_equity = float(wallet.get("total_equity") or 0)
    total_perp_upl = float(wallet.get("total_perp_upl") or 0)
    available = float(wallet.get("total_available_balance") or 0)

    return {
        "timestamp": ts,
        "ticker": "__ACCOUNT_SUMMARY__",
        "row_type": "summary",
        "equity": total_equity,
        "unrealized_pnl": total_perp_upl,
        "realized_pnl": 0,
        "cumulative_pnl": total_perp_upl,
        "volume": 0,
        "price": 0,
        "account": account,
        "currency": "USD",
        "net_liquidation": total_equity,
        "buying_power": available,
        "available_funds": available,
        "cash": usdt_available_balance(wallet),
        "maintenance_margin": float(wallet.get("total_maintenance_margin") or 0),
        "positions_count": positions_count,
        "accounts_count": 1,
    }


def build_portfolio_asset_records(
    wallet: Dict[str, Any],
    *,
    account: str = "BYBIT",
) -> List[Dict[str, Any]]:
    """Build portfolio_history asset rows (one per coin) for the history table."""
    ts = wallet.get("timestamp") or datetime.now(timezone.utc).isoformat()
    records: List[Dict[str, Any]] = []
    for coin in wallet.get("coins") or []:
        code = str(coin.get("coin") or "").strip()
        if not code:
            continue
        equity = float(coin.get("equity") or 0)
        usd_value = float(coin.get("usd_value") or 0)
        wallet_balance = float(coin.get("wallet_balance") or 0)
        upnl = float(coin.get("unrealised_pnl") or 0)
        records.append({
            "timestamp": ts,
            "ticker": code,
            "row_type": "asset",
            "equity": usd_value or equity,
            "unrealized_pnl": upnl,
            "realized_pnl": 0,
            "cumulative_pnl": upnl,
            "volume": wallet_balance,
            "price": (usd_value / wallet_balance) if wallet_balance else 0,
            "account": account,
            "currency": code,
            "net_liquidation": usd_value or equity,
            "buying_power": float(coin.get("available_balance") or 0),
            "available_funds": float(coin.get("available_balance") or 0),
            "cash": wallet_balance,
            "maintenance_margin": 0,
            "positions_count": 0,
            "accounts_count": 1,
        })
    return records


def sync_unified_wallet_snapshot(
    db_manager: Any,
    *,
    positions_count: int = 0,
    wallet: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Dict[str, Any]], int]:
    """
    Fetch unified wallet, cache it, insert portfolio_history rows.

    Inserts one summary row (row_type=summary) plus one asset row per coin
    (row_type=asset) so the Position history table is populated.

    Pass ``wallet`` when the caller already fetched/cached it (e.g. account sync)
    to avoid a second Bybit API round-trip on the worker queue.

    Returns (wallet, snapshots_added).
    """
    if wallet is None:
        wallet, _source = get_unified_wallet(db_manager, live=True)
    else:
        cache_unified_wallet(db_manager, wallet)
    if not wallet:
        return None, 0

    records = [build_portfolio_summary_record(wallet, positions_count=positions_count)]
    records.extend(build_portfolio_asset_records(wallet))
    inserted = db_manager.insert_portfolio_history(records)
    if inserted > 0:
        from scripts.core.bybit_order_manager import log_portfolio_snapshot_transaction

        log_portfolio_snapshot_transaction(
            db_manager,
            snapshots_added=inserted,
            wallet=wallet,
        )
    return wallet, inserted
