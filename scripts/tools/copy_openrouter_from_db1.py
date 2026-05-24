"""
Copy OpenRouter config, model_catalog, and AI providers from db1/trading_robot.db
into database/trading_robot.db.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "db1" / "trading_robot.db"
TARGET = ROOT / "database" / "trading_robot.db"

OPENROUTER_CONFIG_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_FREE_ONLY",
    "HEARTBEAT_OPENROUTER_GRACE_SEC",
)


def copy_openrouter(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise SystemExit(f"Source DB not found: {src}")
    if not dst.is_file():
        raise SystemExit(f"Target DB not found: {dst}")

    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    try:
        sc, dc = s.cursor(), d.cursor()

        for key in OPENROUTER_CONFIG_KEYS:
            row = sc.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
            if row is None:
                continue
            dc.execute(
                "INSERT INTO config(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, row[0]),
            )

        catalog_rows = sc.execute(
            "SELECT model_id, name, provider, context_len, input_price, output_price, updated_at "
            "FROM model_catalog"
        ).fetchall()
        dc.executemany(
            "INSERT OR REPLACE INTO model_catalog"
            "(model_id, name, provider, context_len, input_price, output_price, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            catalog_rows,
        )

        provider_rows = sc.execute(
            "SELECT name, type, base_url, api_key, model, temperature, max_tokens, rate_limit, active "
            "FROM providers WHERE base_url LIKE '%openrouter%'"
        ).fetchall()
        dc.executemany(
            "INSERT OR REPLACE INTO providers"
            "(name, type, base_url, api_key, model, temperature, max_tokens, rate_limit, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            provider_rows,
        )

        d.commit()
        print(f"config keys updated: {len(OPENROUTER_CONFIG_KEYS)}")
        print(f"model_catalog rows: {len(catalog_rows)}")
        print(f"providers rows: {len(provider_rows)}")
    finally:
        s.close()
        d.close()


if __name__ == "__main__":
    copy_openrouter(SOURCE, TARGET)
