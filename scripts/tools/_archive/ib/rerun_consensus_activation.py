"""
Manual consensus activation rerun tool.

Runs activate_consensus_order for selected consensus rows.

Examples:
    python scripts/tools/rerun_consensus_activation.py --dry-run
    python scripts/tools/rerun_consensus_activation.py --limit 20
    python scripts/tools/rerun_consensus_activation.py --ticker NASDAQ:TQQQ --all
    python scripts/tools/rerun_consensus_activation.py --ids 205 206 207
    python scripts/tools/rerun_consensus_activation.py --date-from 2026-05-11 --all
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections import Counter
from typing import Iterable


_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_TOOLS_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
_CORE_DIR = os.path.join(_SCRIPTS_DIR, "core")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from core.sqlite_manager import SQLiteManager
from core.order_manager import activate_consensus_order


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


DEFAULT_STATES = ["", "PENDING_ORDER", "ORDER_SKIPPED", "EXPIRED"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually rerun consensus activation for selected rows."
    )
    parser.add_argument(
        "--db-file",
        default=None,
        help="Path to SQLite DB file (default: from server_config.ini)",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        type=int,
        help="Explicit consensus IDs to process",
    )
    parser.add_argument("--ticker", help="Process only one ticker (e.g. NASDAQ:TQQQ)")
    parser.add_argument(
        "--date-from",
        help="Process rows with date >= YYYY-MM-DD",
    )
    parser.add_argument(
        "--states",
        nargs="+",
        help="Order states to include (use EMPTY for empty state)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all order_state values (ignore --states/default state filter)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max rows to process when --ids is not provided",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidates only, do not execute activation",
    )
    return parser.parse_args()


def _normalize_states(raw_states: Iterable[str] | None) -> list[str]:
    if not raw_states:
        return DEFAULT_STATES
    out: list[str] = []
    for state in raw_states:
        s = (state or "").strip()
        if s.upper() in ("EMPTY", "<EMPTY>"):
            s = ""
        out.append(s)
    return out


def _select_candidates(con: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    where: list[str] = ["UPPER(COALESCE(signal,'')) IN ('LONG','SHORT')", "trade_id IS NULL"]
    params: list[object] = []

    if args.ids:
        placeholders = ",".join(["?"] * len(args.ids))
        where.append(f"id IN ({placeholders})")
        params.extend(args.ids)
    else:
        if args.ticker:
            where.append("UPPER(ticker)=UPPER(?)")
            params.append(args.ticker)

        if args.date_from:
            where.append("substr(date, 1, 10) >= ?")
            params.append(args.date_from)

        if not args.all:
            states = _normalize_states(args.states)
            placeholders = ",".join(["?"] * len(states))
            where.append(f"COALESCE(order_state,'') IN ({placeholders})")
            params.extend(states)

    sql = (
        "SELECT id, ticker, signal, date, COALESCE(order_state,'') AS order_state, "
        "COALESCE(order_reason,'') AS order_reason "
        "FROM consensus "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY id DESC"
    )

    if not args.ids:
        sql += " LIMIT ?"
        params.append(max(1, int(args.limit)))

    return con.execute(sql, params).fetchall()


def main() -> int:
    args = _parse_args()
    if args.db_file:
        db_file = os.path.abspath(args.db_file)
    else:
        from scripts.server.config import get_db_path
        db_file = get_db_path()

    if not os.path.exists(db_file):
        logger.error(f"DB file not found: {db_file}")
        return 2

    logger.info("=== Rerun Consensus Activation ===")
    logger.info(f"DB: {db_file}")

    with sqlite3.connect(db_file) as con:
        con.row_factory = sqlite3.Row
        candidates = _select_candidates(con, args)

    logger.info(f"Candidates: {len(candidates)}")
    for row in candidates[:20]:
        logger.info(
            f"  id={row['id']} ticker={row['ticker']} signal={row['signal']} "
            f"state='{row['order_state']}' date={row['date']}"
        )
    if len(candidates) > 20:
        logger.info(f"  ... and {len(candidates) - 20} more")

    if args.dry_run or not candidates:
        logger.info("Dry-run mode or no candidates: nothing executed.")
        return 0

    db_manager = SQLiteManager(db_file)
    status_counter: Counter[str] = Counter()
    failures = 0

    for row in candidates:
        cid = int(row["id"])
        try:
            result = activate_consensus_order(cid, db_manager)
            status = str(result.get("status", "UNKNOWN"))
            message = str(result.get("message", ""))
            status_counter[status] += 1
            logger.info(f"  id={cid} -> {status}: {message}")
        except Exception as e:
            failures += 1
            status_counter["EXCEPTION"] += 1
            logger.error(f"  id={cid} -> EXCEPTION: {e}")

    logger.info("\n=== Summary ===")
    for status, count in sorted(status_counter.items(), key=lambda x: (-x[1], x[0])):
        logger.info(f"  {status}: {count}")
    logger.info(f"  failures: {failures}")
    logger.info(f"  processed: {len(candidates)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
