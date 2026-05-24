"""Consensus query helpers."""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List, Tuple

import pandas as pd

if TYPE_CHECKING:
    from scripts.core.sqlite_manager import SQLiteManager


class ConsensusRepository:
    def __init__(self, db: "SQLiteManager"):
        self._db = db

    def fetch_pending_for_evaluation(self, now_str: str) -> pd.DataFrame:
        with self._db._connect() as con:
            return pd.read_sql_query(
                """
                SELECT c.* FROM consensus c
                JOIN settings s ON c.ticker = s.ticker AND s.active = 1
                WHERE c.eval_status IN ('PENDING', 'NO_DATA')
                  AND c.eval_target_date IS NOT NULL
                  AND c.eval_target_date != ''
                  AND c.eval_target_date <= ?
                ORDER BY c.eval_target_date ASC
                """,
                con,
                params=[now_str],
            )

    def get_pending_order_row(self, consensus_id: int):
        """Return (ticker, signal, entry_price, stop_loss, take_profit, confidence, methods, rationale)."""
        with self._db._connect() as con:
            row = con.execute(
                """SELECT ticker, signal, entry_limit_price, stop_loss, target_price,
                          confidence, methods_long, methods_short, rationale
                   FROM consensus
                   WHERE id=? AND order_state='PENDING_ORDER' AND trade_id IS NULL""",
                (consensus_id,),
            ).fetchone()
        if not row:
            return None
        (
            ticker,
            signal,
            entry_limit_price,
            stop_loss,
            target_price,
            confidence,
            methods_long,
            methods_short,
            rationale,
        ) = row
        signal_u = (signal or "").upper()
        if signal_u == "LONG":
            methods = methods_long or ""
        elif signal_u == "SHORT":
            methods = methods_short or ""
        else:
            methods = ",".join(m for m in (methods_long, methods_short) if m)
        return (
            ticker,
            signal,
            entry_limit_price,
            stop_loss,
            target_price,
            confidence,
            methods,
            rationale,
        )

    def mark_order_submitted(self, consensus_id: int, updated_at: str) -> None:
        with self._db._connect() as con:
            con.execute(
                """UPDATE consensus
                   SET order_state='ORDER_SUBMITTED', order_checked_at=?
                   WHERE id=?""",
                (updated_at, consensus_id),
            )

    def mark_order_skipped(self, consensus_id: int, reason: str, updated_at: str) -> None:
        with self._db._connect() as con:
            con.execute(
                """UPDATE consensus
                   SET order_state='ORDER_SKIPPED', order_reason=?, order_checked_at=?
                   WHERE id=?""",
                (reason[:500] if reason else "", updated_at, consensus_id),
            )

    def mark_order_expired(self, consensus_id: int, updated_at: str) -> None:
        with self._db._connect() as con:
            con.execute(
                """UPDATE consensus
                   SET order_state='EXPIRED', order_reason='forecast_ttl', order_checked_at=?
                   WHERE id=? AND order_state='PENDING_ORDER'""",
                (updated_at, consensus_id),
            )

    def expire_stale_pending_orders(self, ttl_minutes: int) -> int:
        """Mark PENDING_ORDER rows older than TTL as EXPIRED."""
        if ttl_minutes <= 0:
            return 0
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(minutes=ttl_minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        try:
            with self._db._connect() as con:
                cur = con.execute(
                    """UPDATE consensus
                       SET order_state='EXPIRED', order_reason='forecast_ttl', order_checked_at=?
                       WHERE order_state='PENDING_ORDER' AND trade_id IS NULL AND date < ?""",
                    (now_utc, cutoff),
                )
            return cur.rowcount
        except Exception:
            return 0

    def get_pending_order_candidates(self, ttl_minutes: int) -> List[Tuple[int, str]]:
        """PENDING_ORDER rows within FORECAST_TTL (not expired)."""
        if ttl_minutes <= 0:
            sql = (
                "SELECT id, ticker FROM consensus "
                "WHERE order_state='PENDING_ORDER' AND trade_id IS NULL"
            )
            params: list = []
        else:
            cutoff = (
                datetime.now(tz=timezone.utc) - timedelta(minutes=ttl_minutes)
            ).strftime("%Y-%m-%d %H:%M:%S")
            sql = (
                "SELECT id, ticker FROM consensus "
                "WHERE order_state='PENDING_ORDER' AND trade_id IS NULL AND date >= ?"
            )
            params = [cutoff]
        try:
            with self._db._connect() as con:
                rows = con.execute(sql, params).fetchall()
            return [(int(r[0]), r[1]) for r in rows]
        except Exception:
            return []
