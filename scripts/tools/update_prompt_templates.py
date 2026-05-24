"""
One-shot script: update prompt_templates table in trading_robot.db
with the latest defaults from _DEFAULT_PROMPT_TEMPLATES (which now
include the ПОСЛЕДНИЕ 5 СВЕЧЕЙ / {recent_candles} block).

Run from repo root:
    python scripts/tools/update_prompt_templates.py
"""

import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "core"))

from sqlite_manager import SQLiteManager, _DEFAULT_PROMPT_TEMPLATES
sys.path.insert(0, _ROOT)

from scripts.server.config import get_db_path
DB_PATH = get_db_path()

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    db = SQLiteManager(DB_PATH)
    methods = [r[0] for r in _DEFAULT_PROMPT_TEMPLATES]
    print(f"Updating {len(methods)} prompt templates in {DB_PATH}")

    ok_count = 0
    for method in methods:
        ok = db.reset_prompt_template(method)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {method}")
        if ok:
            ok_count += 1

    print(f"\nDone: {ok_count}/{len(methods)} templates updated.")

if __name__ == "__main__":
    main()
