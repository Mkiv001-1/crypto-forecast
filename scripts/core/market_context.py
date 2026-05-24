"""
Market context loader: crypto-native macro indicators for forecast prompts.

Uses public Bybit market endpoints (no API keys). When unavailable, returns empty context.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_BYBIT_PUBLIC_BASE = "https://api.bybit.com"
_DEFAULT_BTC_SYMBOL = "BTCUSDT"
_DEFAULT_ETH_SYMBOL = "ETHUSDT"


def _cfg(db_manager, key: str, default: str) -> str:
    if db_manager is None:
        return default
    try:
        value = db_manager.get_config_value(key)
        return value.strip() if value else default
    except Exception:
        return default


def _bybit_public_get(path: str, params: Dict[str, str], timeout: int = 10) -> Optional[dict]:
    query = urlencode(params)
    url = f"{_BYBIT_PUBLIC_BASE}{path}?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "forecast-market-context/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", response.getcode())
            if not (200 <= int(status_code) < 300):
                logger.debug("Bybit public API HTTP %s for %s", status_code, path)
                return None
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
        logger.debug("Bybit public API error for %s: %s", path, exc)
        return None

    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        return None
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def _fetch_bybit_daily_closes(symbol: str, days: int = 10) -> Optional[List[float]]:
    """Fetch recent daily close prices for a linear perpetual symbol."""
    limit = max(min(days, 200), 2)
    result = _bybit_public_get(
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol.upper(),
            "interval": "D",
            "limit": str(limit),
        },
    )
    if not result:
        return None

    rows = result.get("list")
    if not isinstance(rows, list) or len(rows) < 2:
        return None

    closes: List[float] = []
    # Bybit returns newest first: [timestamp, open, high, low, close, volume, turnover]
    for row in reversed(rows):
        try:
            closes.append(float(row[4]))
        except (IndexError, TypeError, ValueError):
            continue

    return closes if len(closes) >= 2 else None


def _fetch_bybit_ticker_snapshot(symbol: str) -> Optional[Dict[str, float]]:
    """Fetch 24h change and funding rate from ticker endpoint."""
    result = _bybit_public_get(
        "/v5/market/tickers",
        {"category": "linear", "symbol": symbol.upper()},
    )
    if not result:
        return None

    tickers = result.get("list")
    if not isinstance(tickers, list) or not tickers:
        return None

    row = tickers[0]
    if not isinstance(row, dict):
        return None

    out: Dict[str, float] = {}
    try:
        if row.get("price24hPcnt") not in (None, ""):
            # API returns fraction (0.0123) or percent depending on version — normalize to %
            raw = float(row["price24hPcnt"])
            out["change_24h_pct"] = round(raw * 100 if abs(raw) <= 1 else raw, 2)
    except (TypeError, ValueError):
        pass

    try:
        if row.get("fundingRate") not in (None, ""):
            out["funding_rate_pct"] = round(float(row["fundingRate"]) * 100, 4)
    except (TypeError, ValueError):
        pass

    return out or None


def _pct_change(closes: List[float], lookback: int) -> Optional[float]:
    if len(closes) <= lookback:
        return None
    prev = closes[-(lookback + 1)]
    if prev == 0:
        return None
    return round((closes[-1] - prev) / prev * 100, 2)


def _risk_sentiment(btc_change_5d: Optional[float], btc_change_1d: Optional[float]) -> Optional[str]:
    if btc_change_5d is None and btc_change_1d is None:
        return None
    ref = btc_change_5d if btc_change_5d is not None else btc_change_1d
    if ref is None:
        return None
    if ref >= 3:
        return "risk-on"
    if ref <= -3:
        return "risk-off"
    return "neutral"


def fetch_market_context(db_manager=None) -> dict:
    """
    Load crypto market context for forecast prompts.

    Returns dict with BTC/ETH moves, BTC funding, and derived risk sentiment.
    """
    btc_symbol = _cfg(db_manager, "MARKET_CONTEXT_BTC_SYMBOL", _DEFAULT_BTC_SYMBOL).upper()
    eth_symbol = _cfg(db_manager, "MARKET_CONTEXT_ETH_SYMBOL", _DEFAULT_ETH_SYMBOL).upper()

    ctx: Dict[str, Any] = {
        "btc_symbol": btc_symbol,
        "eth_symbol": eth_symbol,
        "btc_change_1d": None,
        "btc_change_5d": None,
        "eth_change_1d": None,
        "eth_change_5d": None,
        "btc_change_24h_pct": None,
        "btc_funding_rate_pct": None,
        "risk_sentiment": None,
    }

    btc_closes = _fetch_bybit_daily_closes(btc_symbol, days=10)
    if btc_closes:
        ctx["btc_change_1d"] = _pct_change(btc_closes, 1)
        ctx["btc_change_5d"] = _pct_change(btc_closes, 5)

    eth_closes = _fetch_bybit_daily_closes(eth_symbol, days=10)
    if eth_closes:
        ctx["eth_change_1d"] = _pct_change(eth_closes, 1)
        ctx["eth_change_5d"] = _pct_change(eth_closes, 5)

    btc_ticker = _fetch_bybit_ticker_snapshot(btc_symbol)
    if btc_ticker:
        ctx["btc_change_24h_pct"] = btc_ticker.get("change_24h_pct")
        ctx["btc_funding_rate_pct"] = btc_ticker.get("funding_rate_pct")

    ctx["risk_sentiment"] = _risk_sentiment(ctx.get("btc_change_5d"), ctx.get("btc_change_1d"))
    return ctx


def format_market_context(ctx: dict) -> str:
    """Format crypto market context dict for inclusion in a prompt."""
    parts: List[str] = []

    btc = ctx.get("btc_symbol", _DEFAULT_BTC_SYMBOL)
    eth = ctx.get("eth_symbol", _DEFAULT_ETH_SYMBOL)

    if ctx.get("btc_change_1d") is not None:
        parts.append(f"{btc} (1d): {ctx['btc_change_1d']:+.2f}%")
    if ctx.get("btc_change_5d") is not None:
        parts.append(f"{btc} (5d): {ctx['btc_change_5d']:+.2f}%")
    if ctx.get("btc_change_24h_pct") is not None:
        parts.append(f"{btc} (24h): {ctx['btc_change_24h_pct']:+.2f}%")

    if ctx.get("eth_change_1d") is not None:
        parts.append(f"{eth} (1d): {ctx['eth_change_1d']:+.2f}%")
    if ctx.get("eth_change_5d") is not None:
        parts.append(f"{eth} (5d): {ctx['eth_change_5d']:+.2f}%")

    if ctx.get("btc_funding_rate_pct") is not None:
        fr = ctx["btc_funding_rate_pct"]
        bias = "longs pay shorts" if fr > 0 else ("shorts pay longs" if fr < 0 else "neutral funding")
        parts.append(f"{btc} funding: {fr:+.4f}% ({bias})")

    sentiment = ctx.get("risk_sentiment")
    if sentiment:
        parts.append(f"Crypto risk tone: {sentiment}")

    return ", ".join(parts) if parts else "Crypto market context unavailable"
