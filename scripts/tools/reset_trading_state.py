"""
Reset trading state: forecasts, consensus, orders/trades in SQLite + Bybit.

Keeps: settings, config, accounts, price_data, providers (EMA), Bybit journals.

Usage:
    python scripts/tools/reset_trading_state.py [--dry-run] [--db-only] [--bybit-only] [--db PATH]

Stop the API server before a destructive reset to avoid concurrent writes.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _setup_paths() -> str:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.bootstrap import bootstrap_paths

    return bootstrap_paths(root)


def _print_db_summary(summary: Dict[str, Any], *, dry_run: bool) -> None:
    prefix = "Would delete" if dry_run else "Deleted"
    keys = [
        ("forecast_run_links", "would_delete_forecast_run_links", "deleted_forecast_run_links"),
        ("logs", "would_delete_logs", "deleted_logs"),
        ("consensus", "would_delete_consensus", "deleted_consensus"),
        ("forecast_runs", "would_delete_forecast_runs", "deleted_forecast_runs"),
        ("orders", "would_delete_orders", "deleted_orders"),
        ("trades", "would_delete_trades", "deleted_trades"),
    ]
    for label, dry_key, live_key in keys:
        count = summary.get(dry_key if dry_run else live_key, 0)
        print(f"  {prefix} {label}: {count}")


def _print_bybit_preview(open_orders: List[Dict[str, Any]], positions: List[Dict[str, Any]]) -> None:
    print("  Bybit open orders:", len(open_orders))
    for o in open_orders[:20]:
        print(
            f"    - {o.get('symbol')} {o.get('side')} {o.get('order_type')} "
            f"qty={o.get('qty')} status={o.get('status')} id={o.get('order_id')}"
        )
    if len(open_orders) > 20:
        print(f"    ... and {len(open_orders) - 20} more")

    print("  Bybit open positions:", len(positions))
    for p in positions:
        print(
            f"    - {p.get('symbol')} {p.get('side')} size={p.get('size')} "
            f"upl={p.get('unrealised_pnl')}"
        )


def reset_bybit_exchange(db_manager: Any, *, dry_run: bool) -> Dict[str, Any]:
    from scripts.core.bybit_client import close_bybit_client, get_bybit_client, init_bybit_client
    from scripts.core.bybit_config import load_bybit_config, validate_api_credentials

    summary: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "canceled_all": False,
        "closed_symbols": [],
        "open_orders": [],
        "positions": [],
        "errors": [],
    }

    config = load_bybit_config(db_manager)
    valid, err = validate_api_credentials(config)
    if not valid:
        summary["ok"] = False
        summary["errors"].append(err)
        return summary

    mode = "demo" if config.demo else "live"
    print(f"Bybit profile: {config.active_profile} ({mode})")

    init_bybit_client(
        api_key=config.api_key,
        api_secret=config.api_secret,
        demo=config.demo,
        recv_window=config.recv_window,
    )
    client = get_bybit_client()
    if client is None:
        summary["ok"] = False
        summary["errors"].append("Bybit client not initialized")
        return summary

    try:
        if not client.test_connection():
            summary["ok"] = False
            summary["errors"].append("Bybit connection test failed")
            return summary

        open_orders = client.get_open_orders() or []
        positions = client.get_positions() or []
        summary["open_orders"] = open_orders
        summary["positions"] = positions
        _print_bybit_preview(open_orders, positions)

        if dry_run:
            print("  [dry-run] Would cancel all open orders and close all positions")
            return summary

        if open_orders:
            if not client.cancel_all_orders():
                summary["errors"].append("cancel_all_orders failed")
            else:
                summary["canceled_all"] = True
                print("  Canceled all open orders on Bybit")
        else:
            summary["canceled_all"] = True
            print("  No open orders on Bybit")

        for pos in positions:
            symbol = str(pos.get("symbol") or "")
            if not symbol:
                continue
            result = client.close_position_market(symbol)
            if result is None:
                summary["errors"].append(f"close_position failed for {symbol}")
            else:
                summary["closed_symbols"].append(symbol)
                print(f"  Closed position: {symbol}")

        if summary["errors"]:
            summary["ok"] = False
        return summary
    finally:
        close_bybit_client()


def main() -> int:
    _setup_paths()
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.server.config import get_db_path

    parser = argparse.ArgumentParser(
        description="Reset forecasts, consensus, and trading (Bybit + SQLite)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--db-only", action="store_true", help="Skip Bybit; reset database only")
    parser.add_argument("--bybit-only", action="store_true", help="Skip database; reset Bybit only")
    parser.add_argument("--db", default=None, help="Path to trading_robot.db (default: server_config.ini)")
    args = parser.parse_args()

    if args.db_only and args.bybit_only:
        print("ERROR: --db-only and --bybit-only are mutually exclusive")
        return 2

    db_path = os.path.abspath(args.db or get_db_path())
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        return 1

    print(f"Database: {db_path}")
    db = SQLiteManager(db_path)

    exit_code = 0

    if not args.db_only:
        print("\n=== Bybit ===")
        bybit_summary = reset_bybit_exchange(db, dry_run=args.dry_run)
        if not bybit_summary.get("ok"):
            for err in bybit_summary.get("errors", []):
                print(f"  ERROR: {err}")
            if not args.dry_run:
                print("Aborting database reset due to Bybit errors.")
                return 1
            exit_code = 1

    if not args.bybit_only:
        print("\n=== Database ===")
        if args.dry_run:
            summary = db.reset_forecasts_consensus_and_trading_dry_run()
            _print_db_summary(summary, dry_run=True)
        else:
            summary = db.reset_forecasts_consensus_and_trading()
            _print_db_summary(summary, dry_run=False)
        if not summary.get("ok"):
            for err in summary.get("errors", []):
                print(f"  ERROR: {err}")
            exit_code = 1

    if args.dry_run:
        print("\nDry-run complete — no changes were made.")
    elif exit_code == 0:
        print("\nReset complete.")
    else:
        print("\nReset finished with errors.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
