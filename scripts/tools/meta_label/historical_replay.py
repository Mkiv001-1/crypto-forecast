#!/usr/bin/env python3
"""
Stub for historical consensus replay (cold-start dataset).

Full LLM replay is expensive; this script documents the workflow and runs
consensus evaluation on existing PENDING rows only.

Usage:
  python scripts/tools/meta_label/historical_replay.py --db database/trading_robot.db
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.bootstrap import bootstrap

bootstrap()


def main():
    parser = argparse.ArgumentParser(description="Evaluate pending consensus (replay helper)")
    parser.add_argument("--db", default="database/trading_robot.db")
    args = parser.parse_args()

    from scripts.core.consensus_evaluator import evaluate_consensus_records
    from scripts.core.sqlite_manager import SQLiteManager

    db = SQLiteManager(args.db)
    n = evaluate_consensus_records(db)
    print(f"Evaluated {n} consensus records")
    print(
        "For full historical LLM replay, use consensus_recalc + archived logs; "
        "see docs/META_LABELING.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
