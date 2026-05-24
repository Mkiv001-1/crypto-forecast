"""
Sync Bybit Unified Trading Account transaction log into SQLite.

Uses GET /v5/account/transaction-log with 7-day window chunks and cursor pagination.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CONFIG_LAST_SYNC = "LAST_BYBIT_TRANSACTION_LOG_SYNC_AT"
CONFIG_LOOKBACK_DAYS = "BYBIT_TRANSACTION_LOG_SYNC_LOOKBACK_DAYS"

_CHUNK_MS = 7 * 24 * 60 * 60 * 1000
_OVERLAP_MS = 60 * 1000


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso_from_ms(ms: Any) -> str:
    try:
        ts = int(ms) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _parse_iso_to_ms(iso: str) -> Optional[int]:
    if not iso:
        return None
    try:
        text = iso.strip().replace("Z", "+00:00")
        if len(text) == 10:
            text += "T00:00:00+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _format_type_display(trans_type: str) -> str:
    t = (trans_type or "").strip().upper()
    if not t:
        return ""
    return t.replace("_", " ").title()


def compute_trade_direction(
    trans_type: str,
    side: str,
    qty: Any,
    size_after: Any,
) -> str:
    """Map TRADE rows to Bybit-style direction (e.g. Open Sell, Close Buy)."""
    if (trans_type or "").upper() != "TRADE":
        return "--"

    s = (side or "").strip()
    if s not in ("Buy", "Sell"):
        return "--"

    q = abs(_safe_float(qty))
    size_after_f = _safe_float(size_after)
    if q == 0:
        return s

    if s == "Buy":
        size_before = size_after_f - q
    else:
        size_before = size_after_f + q

    if abs(size_after_f) > abs(size_before) + 1e-12:
        return f"Open {s}"
    if abs(size_after_f) < abs(size_before) - 1e-12:
        return f"Close {s}"

    if size_before <= 0 < size_after_f:
        return "Open Buy"
    if size_before >= 0 > size_after_f:
        return "Open Sell"
    if size_before > 0 >= size_after_f:
        return "Close Sell"
    if size_before < 0 <= size_after_f:
        return "Close Buy"
    return s


def iter_time_chunks(start_ms: int, end_ms: int) -> List[Tuple[int, int]]:
    """Split [start_ms, end_ms] into windows of at most 7 days (Bybit API limit)."""
    if start_ms >= end_ms:
        return [(start_ms, end_ms)]
    chunks: List[Tuple[int, int]] = []
    cursor = start_ms
    while cursor < end_ms:
        chunk_end = min(cursor + _CHUNK_MS, end_ms)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return chunks


def _fetch_page(
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    currency: Optional[str] = None,
    trans_type: Optional[str] = None,
    category: Optional[str] = None,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    from scripts.core.bybit_worker import bybit_request_sync, is_running

    kwargs: Dict[str, Any] = {"limit": 50}
    if start_time is not None:
        kwargs["start_time"] = start_time
    if end_time is not None:
        kwargs["end_time"] = end_time
    if currency:
        kwargs["currency"] = currency
    if trans_type:
        kwargs["trans_type"] = trans_type
    if category:
        kwargs["category"] = category
    if cursor:
        kwargs["cursor"] = cursor

    if is_running():
        return bybit_request_sync("get_transaction_log", timeout=60.0, **kwargs)

    from scripts.core.bybit_client import get_bybit_client

    client = get_bybit_client()
    if client is None:
        logger.warning("bybit_transaction_log_sync: no Bybit client")
        return {"list": [], "nextPageCursor": ""}
    return client.get_transaction_log(**kwargs)


def normalize_transaction_row(raw: Dict[str, Any], *, synced_at: str) -> Dict[str, Any]:
    """Map Bybit API record to DB row dict."""
    trans_type = str(raw.get("type") or "")
    side = str(raw.get("side") or "")
    return {
        "bybit_id": str(raw.get("id") or ""),
        "transaction_time": _iso_from_ms(raw.get("transactionTime")),
        "currency": str(raw.get("currency") or ""),
        "symbol": str(raw.get("symbol") or ""),
        "category": str(raw.get("category") or ""),
        "type": trans_type,
        "direction": compute_trade_direction(
            trans_type, side, raw.get("qty"), raw.get("size")
        ),
        "side": side,
        "qty": str(raw.get("qty") or ""),
        "size": str(raw.get("size") or ""),
        "trade_price": str(raw.get("tradePrice") or ""),
        "funding": str(raw.get("funding") or ""),
        "fee": str(raw.get("fee") or ""),
        "cash_flow": str(raw.get("cashFlow") or ""),
        "change": str(raw.get("change") or ""),
        "cash_balance": str(raw.get("cashBalance") or ""),
        "order_id": str(raw.get("orderId") or ""),
        "trade_id": str(raw.get("tradeId") or ""),
        "fee_rate": str(raw.get("feeRate") or ""),
        "trans_sub_type": str(raw.get("transSubType") or ""),
        "synced_at": synced_at,
    }


def upsert_transaction_rows(db_manager: Any, rows: List[Dict[str, Any]]) -> int:
    """Insert or update rows by bybit_id. Returns number of rows touched."""
    if not rows:
        return 0
    sql = """
        INSERT INTO bybit_uta_transaction_log (
            bybit_id, transaction_time, currency, symbol, category, type,
            direction, side, qty, size, trade_price, funding, fee,
            cash_flow, change, cash_balance, order_id, trade_id,
            fee_rate, trans_sub_type, synced_at
        ) VALUES (
            :bybit_id, :transaction_time, :currency, :symbol, :category, :type,
            :direction, :side, :qty, :size, :trade_price, :funding, :fee,
            :cash_flow, :change, :cash_balance, :order_id, :trade_id,
            :fee_rate, :trans_sub_type, :synced_at
        )
        ON CONFLICT(bybit_id) DO UPDATE SET
            transaction_time=excluded.transaction_time,
            currency=excluded.currency,
            symbol=excluded.symbol,
            category=excluded.category,
            type=excluded.type,
            direction=excluded.direction,
            side=excluded.side,
            qty=excluded.qty,
            size=excluded.size,
            trade_price=excluded.trade_price,
            funding=excluded.funding,
            fee=excluded.fee,
            cash_flow=excluded.cash_flow,
            change=excluded.change,
            cash_balance=excluded.cash_balance,
            order_id=excluded.order_id,
            trade_id=excluded.trade_id,
            fee_rate=excluded.fee_rate,
            trans_sub_type=excluded.trans_sub_type,
            synced_at=excluded.synced_at
    """
    count = 0
    with db_manager._connect() as con:
        for row in rows:
            if not row.get("bybit_id"):
                continue
            con.execute(sql, row)
            count += 1
        con.commit()
    return count


def _resolve_sync_range(
    db_manager: Any,
    *,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[int, int]:
    now = datetime.now(tz=timezone.utc)
    end = end_ms if end_ms is not None else int(now.timestamp() * 1000)

    if start_ms is not None:
        start = start_ms
    elif date_from:
        parsed = _parse_iso_to_ms(date_from)
        start = parsed if parsed is not None else end - _CHUNK_MS
    else:
        lookback_days = 7
        try:
            raw = db_manager.get_config_value(CONFIG_LOOKBACK_DAYS, "7")
            lookback_days = max(1, int(raw or 7))
        except (TypeError, ValueError):
            pass
        last_sync = db_manager.get_config_value(CONFIG_LAST_SYNC, "") or ""
        last_ms = _parse_iso_to_ms(last_sync)
        if last_ms is not None:
            start = max(last_ms - _OVERLAP_MS, end - lookback_days * 24 * 3600 * 1000)
        else:
            start = end - lookback_days * 24 * 3600 * 1000

    if date_to:
        parsed_end = _parse_iso_to_ms(date_to)
        if parsed_end is not None:
            end = parsed_end + 24 * 3600 * 1000 - 1

    if start >= end:
        start = end - 24 * 3600 * 1000
    return start, end


def sync_bybit_transaction_log(
    db_manager: Any,
    *,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    currency: Optional[str] = None,
    trans_type: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pull transaction log from Bybit and upsert into bybit_uta_transaction_log.

    Returns summary dict with keys: synced, fetched, start_ms, end_ms, synced_at.
    """
    synced_at = datetime.now(tz=timezone.utc).isoformat()
    start, end = _resolve_sync_range(
        db_manager,
        start_ms=start_ms,
        end_ms=end_ms,
        date_from=date_from,
        date_to=date_to,
    )

    all_raw: List[Dict[str, Any]] = []
    for chunk_start, chunk_end in iter_time_chunks(start, end):
        cursor: Optional[str] = None
        while True:
            page = _fetch_page(
                start_time=chunk_start,
                end_time=chunk_end,
                currency=currency,
                trans_type=trans_type,
                category=category,
                cursor=cursor,
            )
            items = page.get("list") or []
            all_raw.extend(items)
            cursor = page.get("nextPageCursor") or ""
            if not cursor or not items:
                break

    rows = [
        normalize_transaction_row(raw, synced_at=synced_at)
        for raw in all_raw
        if raw.get("id")
    ]
    upserted = upsert_transaction_rows(db_manager, rows)

    if upserted > 0 or all_raw:
        db_manager.set_config_value(CONFIG_LAST_SYNC, synced_at)

    return {
        "synced": upserted,
        "fetched": len(all_raw),
        "start_ms": start,
        "end_ms": end,
        "synced_at": synced_at,
    }
