"""Bybit linear perp market snapshot at signal time (public API)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_BYBIT_PUBLIC_BASE = "https://api.bybit.com"


def fetch_ticker_snapshot(symbol: str, timeout: int = 10) -> Optional[Dict[str, float]]:
    """Funding rate, mark/index prices from public tickers endpoint."""
    params = urlencode({"category": "linear", "symbol": symbol.upper()})
    url = f"{_BYBIT_PUBLIC_BASE}/v5/market/tickers?{params}"
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "meta-label-perp/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
        logger.debug("perp_snapshot: ticker fetch failed for %s: %s", symbol, exc)
        return None

    if payload.get("retCode") != 0:
        return None

    rows = payload.get("result", {}).get("list") or []
    if not rows:
        return None

    row = rows[0]
    mark = float(row.get("markPrice") or 0)
    index = float(row.get("indexPrice") or 0)
    premium_bps = 0.0
    if index > 0 and mark > 0:
        premium_bps = round((mark - index) / index * 10000, 2)

    funding = row.get("fundingRate")
    funding_rate = float(funding) if funding not in (None, "") else 0.0

    return {
        "funding_rate": funding_rate,
        "funding_rate_pct": round(funding_rate * 100, 4),
        "mark_price": mark,
        "index_price": index,
        "mark_index_premium_bps": premium_bps,
        "volume_24h": float(row.get("volume24h") or 0),
    }


def save_perp_snapshot(db_manager, consensus_id: int, ticker: str, snap: Dict[str, Any]) -> None:
    if not snap or consensus_id is None:
        return
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db_manager._connect() as con:
            con.execute(
                """
                INSERT INTO perp_market_snapshots (
                    consensus_id, ticker, ts, funding_rate, mark_price, index_price,
                    mark_index_premium_bps, volume_24h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    consensus_id,
                    ticker,
                    ts,
                    snap.get("funding_rate"),
                    snap.get("mark_price"),
                    snap.get("index_price"),
                    snap.get("mark_index_premium_bps"),
                    snap.get("volume_24h"),
                ),
            )
    except Exception as e:
        logger.warning("perp_snapshot: save failed id=%s: %s", consensus_id, e)
