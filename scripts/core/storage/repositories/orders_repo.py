"""Order persistence used by Bybit order manager."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from scripts.core.sqlite_manager import SQLiteManager


def _table_exists(con, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _open_orders_count_sql(has_trades_table: bool) -> str:
    if not has_trades_table:
        return """SELECT COUNT(*) FROM orders
                  WHERE UPPER(order_role)='ENTRY'
                  AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY')
                  AND status != 'STALE'"""
    return (
        "SELECT COUNT(*) "
        "FROM orders o "
        "LEFT JOIN trades t ON t.bybit_order_id = o.bybit_order_id "
        "WHERE UPPER(o.order_role)='ENTRY' AND o.status != 'STALE' AND ("
        "o.status IN ('QUEUED','SUBMITTED') "
        "OR (o.status = 'FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN') = 'OPEN')"
        ")"
    )


class OrdersRepository:
    def __init__(self, db: "SQLiteManager"):
        self._db = db

    def count_open_orders(self) -> int:
        try:
            with self._db._connect() as con:
                has_trades = _table_exists(con, "trades")
                row = con.execute(_open_orders_count_sql(has_trades)).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def has_open_order_for_ticker(self, ticker: str) -> bool:
        try:
            with self._db._connect() as con:
                has_trades_table = _table_exists(con, "trades")
                if not has_trades_table:
                    row = con.execute(
                        """SELECT COUNT(*) FROM orders
                           WHERE UPPER(ticker)=UPPER(?)
                           AND UPPER(order_role)='ENTRY'
                           AND status IN ('QUEUED','SUBMITTED','FILLED_ENTRY')""",
                        (ticker,),
                    ).fetchone()
                else:
                    row = con.execute(
                        """SELECT COUNT(*) FROM orders o
                           LEFT JOIN trades t ON t.bybit_order_id = o.bybit_order_id
                           WHERE UPPER(o.ticker)=UPPER(?)
                           AND (
                           UPPER(o.order_role)='ENTRY' AND (
                           o.status IN ('QUEUED','SUBMITTED')
                           OR (o.status='FILLED_ENTRY' AND COALESCE(UPPER(t.status), 'OPEN')='OPEN')
                           )
                           )""",
                        (ticker,),
                    ).fetchone()
                return (row[0] if row else 0) > 0
        except Exception:
            return False

    def is_ticker_blocked(self, ticker: str) -> bool:
        try:
            with self._db._connect() as con:
                row = con.execute(
                    "SELECT trading_blocked FROM settings WHERE UPPER(ticker)=UPPER(?)",
                    (ticker,),
                ).fetchone()
                return bool(row[0]) if row else False
        except Exception:
            return False

    def is_ticker_known(self, ticker: str) -> bool:
        try:
            with self._db._connect() as con:
                cols = {r[1].lower() for r in con.execute("PRAGMA table_info(settings)").fetchall()}
                if "active" in cols:
                    row = con.execute(
                        "SELECT 1 FROM settings WHERE UPPER(ticker)=UPPER(?) AND active=1",
                        (ticker,),
                    ).fetchone()
                else:
                    row = con.execute(
                        "SELECT 1 FROM settings WHERE UPPER(ticker)=UPPER(?)",
                        (ticker,),
                    ).fetchone()
                return row is not None
        except Exception:
            return False

    def insert_order(self, order_data: Dict[str, Any]) -> int:
        cols = list(order_data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO orders ({', '.join(cols)}) VALUES ({placeholders})"
        with self._db._connect() as con:
            cur = con.execute(sql, list(order_data.values()))
            return cur.lastrowid

    def insert_bracket_orders(
        self,
        *,
        ticker: str,
        symbol: str,
        side: str,
        entry_price: Optional[float],
        stop_loss: float,
        take_profit: float,
        quantity: float,
        trade_uid: str,
        order_link_id: str,
        order_type: str,
        leverage: int,
        confidence: float,
        consensus_id: Optional[int],
        methods: str,
        rationale: str,
        created_at: str,
        log_id: str = "",
    ) -> Dict[str, int]:
        """Persist ENTRY + TAKE_PROFIT + STOP_LOSS rows sharing one trade_uid."""
        signal = "LONG" if str(side).lower() == "buy" else "SHORT"
        entry_action = "BUY" if signal == "LONG" else "SELL"
        exit_action = "SELL" if signal == "LONG" else "BUY"
        entry_ot = "LMT" if entry_price is not None else "MKT"
        resolved_log_id = log_id or (str(consensus_id) if consensus_id is not None else "")

        common: Dict[str, Any] = {
            "ticker": ticker,
            "symbol": symbol,
            "trade_uid": trade_uid,
            "quantity": quantity,
            "leverage": leverage,
            "confidence": confidence,
            "consensus_id": consensus_id,
            "methods": methods,
            "rationale": rationale,
            "created_at": created_at,
            "status": "QUEUED",
            "log_id": resolved_log_id,
            "is_test": 0,
            "ib_perm_id": 0,
            "ib_order_id": 0,
            "account_type": "",
            "error_message": "",
        }

        entry_id = self.insert_order(
            {
                **common,
                "side": side,
                "order_role": "ENTRY",
                "order_type": entry_ot,
                "action": entry_action,
                "limit_price": entry_price,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "ib_parent_id": 0,
                "bybit_order_link_id": order_link_id,
            }
        )

        take_profit_id = self.insert_order(
            {
                **common,
                "order_role": "TAKE_PROFIT",
                "order_type": "LMT",
                "action": exit_action,
                "limit_price": take_profit,
                "ib_parent_id": entry_id,
            }
        )

        stop_loss_id = self.insert_order(
            {
                **common,
                "order_role": "STOP_LOSS",
                "order_type": "STP",
                "action": exit_action,
                "stop_price": stop_loss,
                "ib_parent_id": entry_id,
            }
        )

        return {
            "entry_id": entry_id,
            "take_profit_id": take_profit_id,
            "stop_loss_id": stop_loss_id,
        }

    def insert_trade_for_bracket(
        self,
        *,
        trade_uid: str,
        ticker: str,
        symbol: str,
        signal: str,
        quantity: float,
        entry_price: Optional[float],
        stop_loss: float,
        target_price: float,
        entry_order_id: int,
        consensus_id: Optional[int],
        leverage: int,
        created_at: str,
    ) -> int:
        """Create OPEN trade linked to bracket entry order."""
        with self._db._connect() as con:
            if not _table_exists(con, "trades"):
                return 0
            cur = con.execute(
                """
                INSERT INTO trades (
                    trade_uid, ticker, symbol, consensus_id, ib_parent_id,
                    signal, quantity, entry_price, stop_loss, target_price,
                    status, leverage, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_uid,
                    ticker,
                    symbol,
                    consensus_id,
                    entry_order_id,
                    signal,
                    quantity,
                    entry_price,
                    stop_loss,
                    target_price,
                    "OPEN",
                    leverage,
                    created_at,
                    created_at,
                ),
            )
            return int(cur.lastrowid)

    def link_consensus_trade(self, consensus_id: int, trade_id: int) -> None:
        with self._db._connect() as con:
            con.execute(
                "UPDATE consensus SET trade_id=? WHERE id=?",
                (trade_id, consensus_id),
            )

    def update_orders_by_trade_uid(
        self, trade_uid: str, updates: Dict[str, Any]
    ) -> None:
        if not trade_uid:
            return
        set_parts = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [trade_uid]
        with self._db._connect() as con:
            con.execute(
                f"UPDATE orders SET {set_parts} WHERE trade_uid=?",
                vals,
            )

    def update_order(self, row_id: int, updates: Dict[str, Any]) -> None:
        set_parts = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [row_id]
        with self._db._connect() as con:
            con.execute(f"UPDATE orders SET {set_parts} WHERE id=?", vals)

    def block_ticker(self, ticker: str) -> None:
        with self._db._connect() as con:
            con.execute(
                "UPDATE settings SET trading_blocked=1 WHERE UPPER(ticker)=UPPER(?)",
                (ticker,),
            )

    def get_max_price_data_date(self, ticker: str) -> Optional[str]:
        with self._db._connect() as con:
            row = con.execute(
                "SELECT MAX(date) as last_date FROM price_data WHERE ticker=?",
                (ticker,),
            ).fetchone()
            if not row:
                return None
            return row["last_date"] if hasattr(row, "keys") else row[0]

    def fetch_submitted_orders(self) -> List:
        with self._db._connect() as con:
            return con.execute(
                """SELECT id, bybit_order_id, symbol, status
                   FROM orders
                   WHERE status IN ('SUBMITTED', 'PARTIALLY_FILLED')"""
            ).fetchall()

    def close_ticker_positions(self, ticker: str, closed_at: str, reason: str) -> None:
        with self._db._connect() as con:
            con.execute(
                """UPDATE orders
                   SET status = 'CLOSED',
                       closed_at = ?,
                       close_reason = ?
                   WHERE UPPER(ticker)=UPPER(?)
                   AND status IN ('FILLED_ENTRY', 'PARTIALLY_FILLED')""",
                (closed_at, reason or "Manual close", ticker),
            )

    def get_order_bybit_row(self, order_id: int):
        with self._db._connect() as con:
            return con.execute(
                "SELECT bybit_order_id, symbol, status FROM orders WHERE id=?",
                (order_id,),
            ).fetchone()

    def log_bybit_transaction(self, values: tuple) -> None:
        with self._db._connect() as con:
            con.execute(
                """INSERT INTO bybit_order_transactions (
                    occurred_at, event_source, event_type, operation_status,
                    status_before, status_after, ticker, trade_uid, bybit_order_id,
                    order_id, trade_id, consensus_id, log_id,
                    request_payload_json, response_payload_json, error_message, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
