"""
vacuum_db.py - Compress (VACUUM) the SQLite trading database.

Usage:
    python scripts/tools/maintenance/vacuum_db.py [--db PATH]

By default uses the path from server_config.ini (database/trading_robot.db).
"""

import argparse
import os
import sqlite3
import sys
import time


def vacuum_database(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    size_before = os.path.getsize(db_path)
    print(f"Database : {db_path}")
    print(f"Size before VACUUM : {size_before / 1_048_576:.2f} MB")

    print("Running VACUUM ... (this may take a moment)")
    t0 = time.time()
    con = sqlite3.connect(db_path)
    try:
        con.execute("VACUUM")
        con.commit()
    finally:
        con.close()
    elapsed = time.time() - t0

    size_after = os.path.getsize(db_path)
    saved = size_before - size_after
    print(f"Size after  VACUUM : {size_after / 1_048_576:.2f} MB")
    print(f"Space freed        : {saved / 1_048_576:.2f} MB  ({elapsed:.1f}s)")


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    sys.path.insert(0, root)
    from scripts.server.config import get_db_path
    default_db = get_db_path()

    parser = argparse.ArgumentParser(description="VACUUM the trading SQLite database")
    parser.add_argument("--db", default=default_db, help="Path to the .db file")
    args = parser.parse_args()

    vacuum_database(os.path.abspath(args.db))


if __name__ == "__main__":
    main()
