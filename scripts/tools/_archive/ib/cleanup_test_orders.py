"""Cancel test orders in IB and remove test rows from working database.

Usage:
  python scripts/tools/cleanup_test_orders.py
  python scripts/tools/cleanup_test_orders.py --dry-run
  python scripts/tools/cleanup_test_orders.py --tag TEST:GUI-DEMO
  python scripts/tools/cleanup_test_orders.py --port 7497
"""

import argparse
import os
import sqlite3
import sys
from typing import Dict, List, Tuple


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE_DIR = os.path.join(PROJECT_ROOT, "scripts", "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from scripts.server.config import ServerConfig
from scripts.core.sqlite_manager import SQLiteManager
from ib_gateway_client import cancel_order


OPEN_STATUSES = {"QUEUED", "SUBMITTED", "PENDING", "FILLED_ENTRY", "ROLLBACK_PENDING"}


def _get_db_path() -> str:
    cfg = ServerConfig()
    return cfg.db_file


def _get_order_mode(db_file: str) -> str:
    try:
        with sqlite3.connect(db_file) as con:
            row = con.execute("SELECT value FROM config WHERE key='ORDER_MODE'").fetchone()
            if row and row[0]:
                return str(row[0]).lower()
    except Exception:
        pass
    return "paper"


def _resolve_port(explicit_port: int, mode: str) -> int:
    if explicit_port:
        return explicit_port
    return 7496 if mode == "live" else 7497


def _build_where(tag: str) -> Tuple[str, List[str]]:
    clauses = ["COALESCE(is_test, 0)=1"]
    params: List[str] = []
    if tag:
        clauses.append("test_tag = ?")
        params.append(tag)
    return " AND ".join(clauses), params


def _has_test_columns(db_file: str) -> bool:
    try:
        with sqlite3.connect(db_file) as con:
            order_cols = {r[1] for r in con.execute("PRAGMA table_info(orders)").fetchall()}
            trade_cols = {r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()}
        return ("is_test" in order_cols and "test_tag" in order_cols and
                "is_test" in trade_cols and "test_tag" in trade_cols)
    except Exception:
        return False


def _load_test_orders_for_cancel(db_file: str, tag: str) -> List[Dict]:
    where_sql, params = _build_where(tag)
    sql = f"""
        SELECT id, ticker, status, ib_order_id, test_tag
        FROM orders
        WHERE {where_sql}
          AND COALESCE(ib_order_id, 0) > 0
        ORDER BY id DESC
    """
    with sqlite3.connect(db_file) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
    out: List[Dict] = []
    for row in rows:
        out.append(dict(row))
    return out


def _delete_test_rows(db_file: str, tag: str) -> Tuple[int, int]:
    where_sql, params = _build_where(tag)
    with sqlite3.connect(db_file) as con:
        cur_o = con.execute(f"DELETE FROM orders WHERE {where_sql}", params)
        deleted_orders = cur_o.rowcount if cur_o.rowcount is not None else 0
        cur_t = con.execute(f"DELETE FROM trades WHERE {where_sql}", params)
        deleted_trades = cur_t.rowcount if cur_t.rowcount is not None else 0
        con.commit()
    return deleted_orders, deleted_trades


def main() -> int:
    parser = argparse.ArgumentParser(description="Cancel test IB orders and cleanup test rows from DB")
    parser.add_argument("--tag", default="", help="Delete only this exact test_tag")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be canceled/deleted")
    parser.add_argument("--host", default="127.0.0.1", help="IB host")
    parser.add_argument("--port", type=int, default=0, help="IB port (default by ORDER_MODE)")
    parser.add_argument("--client-id", type=int, default=211, help="IB client id for cancel requests")
    args = parser.parse_args()

    db_file = _get_db_path()
    # Ensure schema migrations are applied to existing working DB.
    SQLiteManager(db_file)
    mode = _get_order_mode(db_file)
    port = _resolve_port(args.port, mode)

    if not _has_test_columns(db_file):
        print("This database does not have is_test/test_tag columns yet. Run app initialization/migration first.")
        return 1

    print(f"DB: {db_file}")
    print(f"ORDER_MODE: {mode}")
    print(f"IB endpoint: {args.host}:{port} (client_id={args.client_id})")
    if args.tag:
        print(f"Tag filter: {args.tag}")

    rows = _load_test_orders_for_cancel(db_file, args.tag)
    cancellable = [r for r in rows if str(r.get("status", "")).upper() in OPEN_STATUSES]

    print(f"Test orders found: {len(rows)}")
    print(f"Open test orders to cancel in IB: {len(cancellable)}")

    if args.dry_run:
        for r in cancellable[:20]:
            print(
                f"  would_cancel order_id={r.get('id')} ib_order_id={r.get('ib_order_id')} "
                f"ticker={r.get('ticker')} status={r.get('status')} tag={r.get('test_tag')}"
            )
        print("Dry-run complete. No IB or DB changes applied.")
        return 0

    cancel_attempted = len(cancellable)
    cancelled_ok = 0
    cancelled_fail = 0
    for r in cancellable:
        ok = cancel_order(
            order_id=int(r["ib_order_id"]),
            host=args.host,
            port=port,
            client_id=args.client_id,
        )
        if ok:
            cancelled_ok += 1
        else:
            cancelled_fail += 1
            print(
                f"  cancel_failed order_id={r.get('id')} ib_order_id={r.get('ib_order_id')} "
                f"ticker={r.get('ticker')} status={r.get('status')} tag={r.get('test_tag')}"
            )

    deleted_orders, deleted_trades = _delete_test_rows(db_file, args.tag)

    print("Cleanup summary:")
    print(f"  cancel_attempted: {cancel_attempted}")
    print(f"  cancelled_in_ib:  {cancelled_ok}")
    print(f"  cancel_failed:    {cancelled_fail}")
    print(f"  db_orders_deleted: {deleted_orders}")
    print(f"  db_trades_deleted: {deleted_trades}")

    return 0 if cancelled_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
