"""
Bybit Account Synchronization module.

Handles fetching account data from Bybit API and updating the accounts table.
Supports both background periodic sync and manual force-sync.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from scripts.core.bybit_worker import (
    get_positions,
    get_positions_sync,
    get_unified_wallet_sync as get_unified_wallet_async,
    get_unified_wallet_sync_blocking,
    is_running,
)

logger = logging.getLogger(__name__)


def _persist_account_data(
    db_manager: Any,
    wallet: Dict[str, Any],
    positions: list,
) -> Optional[Dict[str, Any]]:
    """Build account row from unified wallet + positions and upsert into accounts table."""
    from scripts.core.bybit_client import get_bybit_client
    from scripts.core.bybit_config import load_bybit_config
    from scripts.core.bybit_unified_wallet import cache_unified_wallet, usdt_available_balance

    cache_unified_wallet(db_manager, wallet)

    client = get_bybit_client()
    is_demo = client.demo if client else True

    uid = ""
    try:
        account_info = client.get_account_info() if client else None
        if account_info:
            uid = str(account_info.get("uid", "") or "")
    except Exception as e:
        logger.warning(f"bybit_account_sync: failed to fetch account UID: {e}")

    cfg = load_bybit_config(db_manager)
    active_profile = cfg.active_profile or "demo"
    mode = "Demo" if is_demo else "Live"

    total_equity = float(wallet.get("total_equity") or 0)
    total_perp_upl = float(wallet.get("total_perp_upl") or 0)
    available = float(wallet.get("total_available_balance") or 0)
    usdt_available = usdt_available_balance(wallet)

    account_data = {
        "broker": "bybit",
        "account_id": f"bybit-{active_profile}",
        "profile": active_profile,
        "name": f"Bybit {mode} ({active_profile})",
        "account_type": wallet.get("account_type") or "UNIFIED",
        "base_currency": "USD",
        "uid": uid,
        "mode": mode,
        "net_liquidation": total_equity,
        "buying_power": available,
        "available_funds": usdt_available,
        "cash": usdt_available,
        "maintenance_margin": float(wallet.get("total_maintenance_margin") or 0),
        "last_update": wallet.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "type": active_profile,
        "unrealized_pnl": total_perp_upl,
        "positions_count": len(positions),
    }

    result = update_accounts_table(db_manager, account_data)
    if result:
        logger.info(
            f"bybit_account_sync: synced account {account_data['account_id']} "
            f"uid={uid} "
            f"(equity={account_data['net_liquidation']:.2f} USDT, "
            f"positions={account_data['positions_count']})"
        )

    return account_data


async def sync_account_data_async(db_manager: Any) -> Optional[Dict[str, Any]]:
    """
    Synchronize account data using the Bybit worker queue (async-safe).

    Use from the worker event loop or FastAPI handlers. Do not call from inside
    the worker's thread-pool executor — that deadlocks on bybit_request_sync.
    """
    if not is_running():
        logger.warning("bybit_account_sync: worker not running, skipping sync")
        return None

    try:
        wallet = await get_unified_wallet_async()
        if wallet is None:
            logger.error("bybit_account_sync: failed to fetch unified wallet")
            return None

        positions = await get_positions()
        return _persist_account_data(db_manager, wallet, positions)

    except Exception as e:
        err = e if str(e) else f"{type(e).__name__}"
        logger.error(f"bybit_account_sync: sync failed: {err}", exc_info=not str(e))
        return None


def sync_account_data(db_manager: Any) -> Optional[Dict[str, Any]]:
    """
    Synchronize account data from Bybit API to database.
    
    Args:
        db_manager: SQLiteManager instance
    
    Returns:
        Dict with synced account data or None if failed
    """
    if not is_running():
        logger.warning("bybit_account_sync: worker not running, skipping sync")
        return None
    
    try:
        wallet = get_unified_wallet_sync_blocking()
        if wallet is None:
            logger.error("bybit_account_sync: failed to fetch unified wallet")
            return None

        positions = get_positions_sync()
        return _persist_account_data(db_manager, wallet, positions)

    except Exception as e:
        err = e if str(e) else f"{type(e).__name__}"
        logger.error(f"bybit_account_sync: sync failed: {err}", exc_info=not str(e))
        return None


def update_accounts_table(db_manager: Any, account_data: Dict[str, Any]) -> bool:
    """
    Upsert account data into accounts table.
    
    Args:
        db_manager: SQLiteManager instance
        account_data: Dict with account fields
    
    Returns:
        True if successful
    """
    try:
        with db_manager._connect() as con:
            # Check if account exists
            existing = con.execute(
                "SELECT id FROM accounts WHERE broker=? AND account_id=?",
                (account_data["broker"], account_data["account_id"])
            ).fetchone()
            
            if existing:
                # Update existing account
                con.execute(
                    """UPDATE accounts SET
                        name=?, account_type=?, base_currency=?, buying_power=?,
                        net_liquidation=?, available_funds=?, cash=?,
                        maintenance_margin=?, last_update=?, type=?,
                        uid=?, mode=?, unrealized_pnl=?, positions_count=?, profile=?
                    WHERE broker=? AND account_id=?""",
                    (
                        account_data["name"],
                        account_data["account_type"],
                        account_data["base_currency"],
                        account_data["buying_power"],
                        account_data["net_liquidation"],
                        account_data["available_funds"],
                        account_data["cash"],
                        account_data["maintenance_margin"],
                        account_data["last_update"],
                        account_data["type"],
                        account_data.get("uid", ""),
                        account_data.get("mode", ""),
                        account_data.get("unrealized_pnl", 0),
                        account_data.get("positions_count", 0),
                        account_data.get("profile", account_data.get("type", "")),
                        account_data["broker"],
                        account_data["account_id"],
                    )
                )
            else:
                # Insert new account
                con.execute(
                    """INSERT INTO accounts (
                        broker, account_id, name, account_type, base_currency,
                        buying_power, net_liquidation, available_funds, cash,
                        maintenance_margin, last_update, type,
                        uid, mode, unrealized_pnl, positions_count, profile
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        account_data["broker"],
                        account_data["account_id"],
                        account_data["name"],
                        account_data["account_type"],
                        account_data["base_currency"],
                        account_data["buying_power"],
                        account_data["net_liquidation"],
                        account_data["available_funds"],
                        account_data["cash"],
                        account_data["maintenance_margin"],
                        account_data["last_update"],
                        account_data["type"],
                        account_data.get("uid", ""),
                        account_data.get("mode", ""),
                        account_data.get("unrealized_pnl", 0),
                        account_data.get("positions_count", 0),
                        account_data.get("profile", account_data.get("type", "")),
                    )
                )
            
            con.commit()
            return True
            
    except Exception as e:
        logger.error(f"bybit_account_sync: database update failed: {e}")
        return False


def get_accounts_summary(db_manager: Any) -> Dict[str, Any]:
    """
    Get summary of all Bybit accounts from database.
    
    Args:
        db_manager: SQLiteManager instance
    
    Returns:
        Dict with accounts list and totals
    """
    try:
        with db_manager._connect() as con:
            rows = con.execute(
                """SELECT * FROM accounts WHERE broker='bybit' ORDER BY account_id"""
            ).fetchall()
            
            accounts = [dict(row) for row in rows]
            
            # Calculate totals
            totals = {
                "count": len(accounts),
                "total_net_liq": sum(a.get("net_liquidation", 0) or 0 for a in accounts),
                "total_buying_power": sum(a.get("buying_power", 0) or 0 for a in accounts),
                "total_available": sum(a.get("available_funds", 0) or 0 for a in accounts),
            }
            
            return {
                "accounts": accounts,
                "totals": totals,
            }
            
    except Exception as e:
        logger.error(f"bybit_account_sync: failed to get summary: {e}")
        return {"accounts": [], "totals": {"count": 0, "total_net_liq": 0, "total_buying_power": 0, "total_available": 0}}
