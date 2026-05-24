#!/usr/bin/env python3
"""Export evaluated consensus rows for meta-label training."""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.bootstrap import bootstrap  # noqa: E402

bootstrap()

import pandas as pd  # noqa: E402

from scripts.core.meta_label.features import (  # noqa: E402
    FEATURE_NAMES,
    build_meta_features_from_consensus_row,
    features_to_vector,
)
from scripts.core.sqlite_manager import SQLiteManager  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Export meta-label training dataset")
    parser.add_argument("--db", default="database/trading_robot.db")
    parser.add_argument("--out", default="data/meta_label/train.csv")
    parser.add_argument("--min-date", default=None, help="YYYY-MM-DD lower bound")
    args = parser.parse_args()

    db = SQLiteManager(args.db)
    sql = """
        SELECT c.* FROM consensus c
        JOIN settings s ON c.ticker = s.ticker AND s.active = 1
        WHERE c.eval_status = 'EVALUATED'
          AND c.signal IN ('LONG', 'SHORT')
          AND c.label_meta IS NOT NULL
    """
    params = []
    if args.min_date:
        sql += " AND c.date >= ?"
        params.append(args.min_date)

    with db._connect() as con:
        df = pd.read_sql_query(sql, con, params=params)

    if df.empty:
        print("No rows to export")
        return 1

    rows = []
    for _, row in df.iterrows():
        rdict = row.to_dict()
        feats = build_meta_features_from_consensus_row(rdict, db)
        vec = {name: feats.get(name, 0.0) for name in FEATURE_NAMES}
        vec["label_meta"] = int(row["label_meta"])
        vec["net_pnl_pct"] = float(row.get("net_pnl_pct") or 0)
        vec["pnl_pct"] = float(row.get("pnl_pct") or 0)
        vec["consensus_id"] = int(row["id"])
        vec["ticker"] = row["ticker"]
        vec["date"] = row["date"]
        rows.append(vec)

    out_df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if args.out.endswith(".parquet"):
        out_df.to_parquet(args.out, index=False)
    else:
        out_df.to_csv(args.out, index=False)
    print(f"Exported {len(out_df)} rows -> {args.out}")
    print(f"  label_meta=1: {(out_df['label_meta']==1).sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
