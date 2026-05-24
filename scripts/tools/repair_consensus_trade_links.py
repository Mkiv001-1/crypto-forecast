"""
Repair consensus.trade_id when it points to orders.id or a missing trades row.

Usage:
  python scripts/tools/repair_consensus_trade_links.py
  python scripts/tools/repair_consensus_trade_links.py --dry-run
  python scripts/tools/repair_consensus_trade_links.py --db path/to/trading_robot.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.server.config import get_db_path


def repair_links(db_path: str, *, dry_run: bool = False) -> dict:
    summary = {
        "scanned": 0,
        "fixed_from_trades_consensus_id": 0,
        "cleared_orphan": 0,
        "unchanged": 0,
        "errors": [],
    }
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT c.id AS consensus_id, c.trade_id, c.ticker, c.order_state
            FROM consensus c
            WHERE c.trade_id IS NOT NULL AND TRIM(CAST(c.trade_id AS TEXT)) != ''
            """
        ).fetchall()
        summary["scanned"] = len(rows)
        for row in rows:
            cid = int(row["consensus_id"])
            tid = int(row["trade_id"])
            trade = con.execute("SELECT id FROM trades WHERE id=?", (tid,)).fetchone()
            if trade:
                summary["unchanged"] += 1
                continue

            alt = con.execute(
                "SELECT id FROM trades WHERE consensus_id=? ORDER BY id DESC LIMIT 1",
                (cid,),
            ).fetchone()
            if alt:
                new_id = int(alt["id"])
                if not dry_run:
                    con.execute(
                        "UPDATE consensus SET trade_id=? WHERE id=?",
                        (new_id, cid),
                    )
                summary["fixed_from_trades_consensus_id"] += 1
                continue

            order = con.execute("SELECT id FROM orders WHERE id=?", (tid,)).fetchone()
            if order and not dry_run:
                con.execute(
                    """
                    UPDATE consensus
                    SET trade_id = NULL,
                        order_state = CASE
                            WHEN UPPER(COALESCE(order_state, '')) = 'ORDER_SUBMITTED'
                            THEN 'PENDING_ORDER'
                            ELSE order_state
                        END
                    WHERE id = ?
                    """,
                    (cid,),
                )
            elif order and dry_run:
                pass
            elif not dry_run:
                con.execute(
                    "UPDATE consensus SET trade_id = NULL WHERE id = ?",
                    (cid,),
                )
            summary["cleared_orphan"] += 1

        if not dry_run:
            con.commit()
    except Exception as e:
        summary["errors"].append(str(e))
        con.rollback()
    finally:
        con.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Path to trading_robot.db")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing",
    )
    args = parser.parse_args()
    db_path = os.path.abspath(args.db or get_db_path())
    if not os.path.isfile(db_path):
        print(f"Database not found: {db_path}")
        return 1
    summary = repair_links(db_path, dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] {db_path}")
    print(summary)
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
