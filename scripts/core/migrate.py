"""
One-shot migration: trading_robot.xlsx  ->  trading_robot.db

Run from project root:
    python scripts/core/migrate.py

After successful migration trading_robot.xlsx is renamed to
trading_robot.xlsx.bak so the server will use the SQLite DB.
"""

import os
import sys
import logging
import shutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
for _p in [_PROJECT_ROOT, os.path.join(_PROJECT_ROOT, "scripts")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
from scripts.core.sqlite_manager import SQLiteManager


# ---------------------------------------------------------------------------
# Column normalisation maps
# ---------------------------------------------------------------------------

_PROVIDERS_COL_MAP = {
    "provider": "name",
    "api_key":  "api_key",
    "api":      "api_key",
}

_PRICE_COL_MAP = {
    "Date":   "date",
    "Open":   "open",
    "High":   "high",
    "Low":    "low",
    "Close":  "close",
    "Volume": "volume",
}

_IND_COL_MAP = {
    "bb_upper": "bb_upper",
    "bb_lower": "bb_lower",
}

_CONFIG_FROM_CONFIG_PY = {
    "ALPHA_VANTAGE_API_KEY": "IK91FANGC89AYYO3",
    "DATA_SOURCE":           "alphavantage",
}


def _norm(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})


def migrate(xlsx_path: str, db_path: str):
    if not os.path.exists(xlsx_path):
        logger.error(f"Excel file not found: {xlsx_path}")
        sys.exit(1)

    logger.info(f"Source: {xlsx_path}")
    logger.info(f"Target: {db_path}")

    db = SQLiteManager(db_path)
    totals = {}
    # Table ib_order_transactions has no Excel source and is created by SQLiteManager schema init.
    # ID lifecycle fields (trade_uid, ib_perm_id) are also managed by SQLiteManager migrations.
    totals["ib_order_transactions"] = 0

    # ---- Settings -----------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Settings")
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            db.clear_sheet("settings")
            for _, row in df.iterrows():
                db.upsert_row("settings", {
                    "ticker":  str(row.get("ticker", "")),
                    "active":  int(row.get("active", 0)),
                    "comment": str(row.get("comment", "")),
                })
            totals["settings"] = len(df)
            logger.info(f"  Settings:   {len(df)} rows")
    except Exception as e:
        logger.warning(f"  Settings: skipped ({e})")

    # ---- Providers ----------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Providers")
        df = _norm(df, _PROVIDERS_COL_MAP)
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            for _, row in df.iterrows():
                name = str(row.get("name") or row.get("provider", ""))
                if not name:
                    continue
                db.upsert_row("providers", {
                    "name":      name,
                    "api_key":   str(row.get("api_key") or row.get("api", "")),
                    "model":     str(row.get("model", "")),
                    "temperature": float(row.get("temperature") or 0.2),
                    "max_tokens":  int(row.get("max_tokens") or 2000),
                    "rate_limit":  int(row.get("rate_limit") or 60),
                    "active":      int(row.get("active", 1)),
                })
            totals["providers"] = len(df)
            logger.info(f"  Providers:  {len(df)} rows")
    except Exception as e:
        logger.warning(f"  Providers: skipped ({e})")

    # ---- Logs ---------------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Logs")
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            db.clear_sheet("logs")
            inserted = 0
            for _, row in df.iterrows():
                rec = {k: _clean(v) for k, v in row.items()}
                if not rec.get("id"):
                    continue
                db.upsert_row("logs", rec)
                inserted += 1
            totals["logs"] = inserted
            logger.info(f"  Logs:       {inserted} rows")
    except Exception as e:
        logger.warning(f"  Logs: skipped ({e})")

    # ---- PriceData ----------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="PriceData")
        df = _norm(df, _PRICE_COL_MAP)
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            records = []
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
                records.append({
                    "ticker": str(row.get("ticker", "")),
                    "date":   date_str,
                    "open":   _flt(row.get("open")),
                    "high":   _flt(row.get("high")),
                    "low":    _flt(row.get("low")),
                    "close":  _flt(row.get("close")),
                    "volume": _int(row.get("volume")),
                })
            db.save_price_data(records)
            totals["price_data"] = len(records)
            logger.info(f"  PriceData:  {len(records)} rows")
    except Exception as e:
        logger.warning(f"  PriceData: skipped ({e})")

    # ---- Indicators ---------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Indicators")
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            inserted = 0
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
                db.upsert_row("indicators", {
                    "ticker":    str(row.get("ticker", "")),
                    "date":      date_str,
                    "price":     _flt(row.get("price")),
                    "ma20":      _flt(row.get("ma20")),
                    "ma50":      _flt(row.get("ma50")),
                    "ma200":     _flt(row.get("ma200")),
                    "rsi14":     _flt(row.get("rsi14")),
                    "atr14":     _flt(row.get("atr14")),
                    "bb_upper":  _flt(row.get("bb_upper")),
                    "bb_lower":  _flt(row.get("bb_lower")),
                    "change_5d": _flt(row.get("change_5d")),
                    "change_20d":_flt(row.get("change_20d")),
                })
                inserted += 1
            totals["indicators"] = inserted
            logger.info(f"  Indicators: {inserted} rows")
    except Exception as e:
        logger.warning(f"  Indicators: skipped ({e})")

    # ---- Prompts ------------------------------------------------------------
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Prompts")
        df.columns = [c.lower() for c in df.columns]
        if not df.empty:
            inserted = 0
            for _, row in df.iterrows():
                # Parse request_date
                rd = row.get("request_date") or row.get("date")
                if pd.notna(rd):
                    if hasattr(rd, "strftime"):
                        date_str = rd.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        try:
                            date_str = pd.to_datetime(str(rd)).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            date_str = str(rd)
                else:
                    date_str = None

                ticker = str(row.get("ticker", "")) if pd.notna(row.get("ticker")) else ""

                for i in range(1, 7):
                    key = f"prompt_{i}"
                    if key in row and pd.notna(row[key]) and str(row[key]).strip():
                        db.save_prompt(
                            ticker=ticker,
                            method=_method_key(i),
                            prompt_text=str(row[key]),
                            date=date_str,
                        )
                        inserted += 1
            totals["prompts"] = inserted
            logger.info(f"  Prompts:    {inserted} rows")
    except Exception as e:
        logger.warning(f"  Prompts: skipped ({e})")

    # ---- Config from config.py constants ------------------------------------
    for key, value in _CONFIG_FROM_CONFIG_PY.items():
        cur = db.get_config_value(key)
        if not cur:
            db.set_config_value(key, value)
    logger.info("  Config:     seeded from config.py constants")

    # ---- Summary ------------------------------------------------------------
    logger.info("")
    logger.debug("Migration complete:")
    for table, count in totals.items():
        logger.info(f"  {table:<15} {count} rows")

    # ---- Backup xlsx --------------------------------------------------------
    bak_path = xlsx_path + ".bak"
    shutil.move(xlsx_path, bak_path)
    logger.info(f"\nOriginal Excel backed up to: {bak_path}")
    logger.info("Server will now use SQLite database.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(v):
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        if isinstance(v, np.bool_):
            return bool(v)
    except ImportError:
        pass
    return v


def _flt(v, default=0.0) -> float:
    try:
        return float(v) if v is not None and str(v) not in ("nan", "") else default
    except Exception:
        return default


def _int(v, default=0) -> int:
    try:
        return int(float(v)) if v is not None and str(v) not in ("nan", "") else default
    except Exception:
        return default


_METHOD_MAP = {
    1: "momentum_trend",
    2: "price_action",
    3: "relative_strength",
    4: "volatility",
    5: "mean_reversion",
    6: "volume_breakout",
}


def _method_key(n: int) -> str:
    return _METHOD_MAP.get(n, f"method_{n}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_MODEL_FIXES = {
    "anthropic/claude-3.5-sonnet": "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash-exp":  "google/gemini-2.5-flash-preview",
    "deepseek/deepseek-chat":       "deepseek/deepseek-chat-v3-0324",
}


def fix_models(db_path: str):
    """Update stale OpenRouter model slugs in existing DB."""
    db = SQLiteManager(db_path)
    updated = 0
    with db._connect() as con:
        for old, new in _MODEL_FIXES.items():
            cur = con.execute(
                "UPDATE providers SET model = ? WHERE model = ?", (new, old)
            )
            updated += cur.rowcount
    logger.info(f"Model slugs updated: {updated} row(s) in {db_path}")


def migrate_db_schema(db_path: str):
    """Add missing columns to existing SQLite database (idempotent)."""
    import sqlite3
    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    con = sqlite3.connect(db_path)
    try:
        # Get existing columns in logs table
        cur = con.execute("PRAGMA table_info(logs)")
        existing_cols = {row[1] for row in cur.fetchall()}

        new_columns = [
            ("actual_open", "REAL"),
            ("exit_successful", "INTEGER"),
        ]

        added = 0
        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                con.execute(f"ALTER TABLE logs ADD COLUMN {col_name} {col_type}")
                logger.info(f"  Added column: {col_name} ({col_type})")
                added += 1
            else:
                logger.info(f"  Column already exists: {col_name}")

        con.commit()
        if added:
            logger.debug(f"Schema migration complete: {added} column(s) added")
        else:
            logger.debug("Schema migration: all columns already present")
    except Exception as e:
        logger.error(f"Schema migration failed: {e}")
        raise
    finally:
        con.close()


def drop_ib_legacy_tables(db_path: str) -> None:
    """
    Drop legacy IB audit tables after backup. Does not rename orders.ib_* columns.

    Set env DROP_IB_LEGACY=1 or pass --drop-ib-legacy to migrate.py CLI.
    """
    import sqlite3

    tables = ("ib_gateway_log", "ib_order_transactions", "ib_order_types")
    con = sqlite3.connect(db_path)
    try:
        for name in tables:
            con.execute(f"DROP TABLE IF EXISTS {name}")
            logger.info("Dropped table %s", name)
        con.commit()
    finally:
        con.close()


def migrate_prompts_only(xlsx_path: str, db_path: str):
    """Re-import only the Prompts sheet into an existing DB."""
    if not os.path.exists(xlsx_path):
        logger.error(f"Excel file not found: {xlsx_path}")
        sys.exit(1)
    db = SQLiteManager(db_path)
    try:
        df = pd.read_excel(xlsx_path, sheet_name="Prompts")
        df.columns = [c.lower() for c in df.columns]
        if df.empty:
            logger.warning("Prompts sheet is empty.")
            return
        # Clear existing prompts first
        with db._connect() as con:
            con.execute("DELETE FROM prompts")
        inserted = 0
        for _, row in df.iterrows():
            rd = row.get("request_date") or row.get("date")
            if pd.notna(rd):
                if hasattr(rd, "strftime"):
                    date_str = rd.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    try:
                        date_str = pd.to_datetime(str(rd)).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        date_str = str(rd)
            else:
                date_str = None
            ticker = str(row.get("ticker", "")) if pd.notna(row.get("ticker")) else ""
            for i in range(1, 7):
                key = f"prompt_{i}"
                if key in row and pd.notna(row[key]) and str(row[key]).strip():
                    db.save_prompt(ticker=ticker, method=_method_key(i),
                                   prompt_text=str(row[key]), date=date_str)
                    inserted += 1
        logger.debug(f"Prompts migrated: {inserted} rows into {db_path}")
    except Exception as e:
        logger.error(f"Prompts migration failed: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate trading_robot.xlsx → SQLite")
    parser.add_argument("--prompts-only", action="store_true",
                        help="Re-import only the Prompts sheet into existing DB (no backup/overwrite)")
    parser.add_argument("--fix-models", action="store_true",
                        help="Update stale OpenRouter model slugs in existing DB")
    parser.add_argument("--migrate-schema", action="store_true",
                        help="Add missing columns to existing DB schema (e.g., actual_open, exit_successful)")
    parser.add_argument("--drop-ib-legacy", action="store_true",
                        help="Drop ib_gateway_log, ib_order_transactions, ib_order_types (backup DB first)")
    parser.add_argument("--xlsx", default=os.path.join(_PROJECT_ROOT, "trading_robot.xlsx"))
    from scripts.server.config import get_db_path
    parser.add_argument("--db",   default=get_db_path())
    args = parser.parse_args()

    if args.migrate_schema:
        migrate_db_schema(args.db)
        sys.exit(0)

    if args.drop_ib_legacy or os.environ.get("DROP_IB_LEGACY", "").strip() in ("1", "true", "yes"):
        drop_ib_legacy_tables(args.db)
        sys.exit(0)

    if args.prompts_only:
        migrate_prompts_only(args.xlsx, args.db)
        sys.exit(0)

    if args.fix_models:
        fix_models(args.db)
        sys.exit(0)

    xlsx = args.xlsx
    db   = args.db

    if os.path.exists(db):
        ans = input(f"'{db}' already exists. Overwrite? [y/N]: ").strip().lower()
        if ans != "y":
            logger.info("Aborted.")
            sys.exit(0)
        os.remove(db)

    migrate(xlsx, db)
