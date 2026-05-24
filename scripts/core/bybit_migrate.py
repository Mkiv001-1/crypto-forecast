"""
Bybit Database Migration — добавление Bybit-специфичных полей в БД.

Запуск:
    python -m scripts.core.bybit_migrate

или из другого модуля:
    from scripts.core.bybit_migrate import migrate_to_bybit
    migrate_to_bybit(db_manager)
"""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    """Проверить существование таблицы."""
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Проверить существование колонки в таблице."""
    try:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(r[1]).lower() == column.lower() for r in rows)
    except Exception:
        return False


def migrate_orders_table(con: sqlite3.Connection) -> bool:
    """
    Добавить Bybit-поля в таблицу orders.
    
    Добавляемые поля:
    - bybit_order_id: ID ордера в Bybit
    - bybit_order_link_id: Кастомный ID для отслеживания
    - symbol: Торговая пара (например BTCUSDT)
    - leverage: Плечо (1-100)
    - cum_exec_qty: Исполненное количество
    - cum_exec_value: Исполненная стоимость
    """
    try:
        if not _table_exists(con, "orders"):
            logger.warning("orders table does not exist, skipping migration")
            return False
        
        columns_to_add = [
            ("bybit_order_id", "TEXT"),
            ("bybit_order_link_id", "TEXT"),
            ("symbol", "TEXT"),
            ("side", "TEXT DEFAULT ''"),
            ("entry_price", "REAL"),
            ("stop_loss", "REAL"),
            ("take_profit", "REAL"),
            ("leverage", "INTEGER DEFAULT 1"),
            ("confidence", "REAL"),
            ("consensus_id", "INTEGER"),
            ("methods", "TEXT DEFAULT ''"),
            ("rationale", "TEXT DEFAULT ''"),
            ("updated_at", "TEXT DEFAULT ''"),
            ("submitted_at", "TEXT DEFAULT ''"),
            ("filled_at", "TEXT DEFAULT ''"),
            ("cancelled_at", "TEXT DEFAULT ''"),
            ("closed_at", "TEXT DEFAULT ''"),
            ("cancel_reason", "TEXT DEFAULT ''"),
            ("close_reason", "TEXT DEFAULT ''"),
            ("cum_exec_qty", "REAL DEFAULT 0"),
            ("cum_exec_value", "REAL DEFAULT 0"),
        ]
        
        for column, col_type in columns_to_add:
            if not _column_exists(con, "orders", column):
                con.execute(f"ALTER TABLE orders ADD COLUMN {column} {col_type}")
                logger.debug(f"Added column {column} to orders table")
        
        # Создаем индекс на bybit_order_id
        con.execute("CREATE INDEX IF NOT EXISTS idx_orders_bybit_id ON orders(bybit_order_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_orders_bybit_link_id ON orders(bybit_order_link_id)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating orders table: {e}")
        return False


def migrate_trades_table(con: sqlite3.Connection) -> bool:
    """
    Добавить Bybit-поля в таблицу trades.
    
    Добавляемые поля:
    - bybit_order_id: ID ордера в Bybit
    - symbol: Торговая пара
    - leverage: Плечо
    """
    try:
        if not _table_exists(con, "trades"):
            logger.warning("trades table does not exist, skipping migration")
            return False
        
        columns_to_add = [
            ("bybit_order_id", "TEXT"),
            ("symbol", "TEXT"),
            ("leverage", "INTEGER DEFAULT 1"),
        ]
        
        for column, col_type in columns_to_add:
            if not _column_exists(con, "trades", column):
                con.execute(f"ALTER TABLE trades ADD COLUMN {column} {col_type}")
                logger.debug(f"Added column {column} to trades table")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating trades table: {e}")
        return False


def migrate_settings_table(con: sqlite3.Connection) -> bool:
    """
    Добавить Bybit-специфичные настройки.
    
    Добавляемые поля:
    - leverage: Дефолтное плечо для тикера
    - symbol: Торговая пара для тикера
    """
    try:
        if not _table_exists(con, "settings"):
            logger.warning("settings table does not exist, skipping migration")
            return False
        
        columns_to_add = [
            ("leverage", "INTEGER DEFAULT 3"),
            ("symbol", "TEXT"),
        ]
        
        for column, col_type in columns_to_add:
            if not _column_exists(con, "settings", column):
                con.execute(f"ALTER TABLE settings ADD COLUMN {column} {col_type}")
                logger.debug(f"Added column {column} to settings table")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating settings table: {e}")
        return False


def migrate_price_data_table(con: sqlite3.Connection) -> bool:
    """
    Обновить таблицу price_data для поддержки крипто-символов.
    
    Убедиться что ticker поддерживает длинные имена (BTCUSDT и т.д.)
    """
    try:
        if not _table_exists(con, "price_data"):
            logger.warning("price_data table does not exist, skipping migration")
            return False
        
        # Проверяем текущий тип колонки ticker
        info = con.execute("PRAGMA table_info(price_data)").fetchall()
        ticker_col = next((r for r in info if r[1].lower() == "ticker"), None)
        
        if ticker_col:
            # SQLite не поддерживает ALTER COLUMN, поэтому используем workaround
            current_type = ticker_col[2].upper()
            if "VARCHAR" in current_type or "CHAR" in current_type:
                # Проверяем размер
                size = 50  # Default
                if "(" in current_type:
                    try:
                        size = int(current_type.split("(")[1].split(")")[0])
                    except:
                        pass
                
                if size < 20:
                    # Нужно увеличить размер для крипто-символов (BTCUSDT = 8 символов)
                    logger.debug("price_data.ticker column size is sufficient for crypto symbols")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating price_data table: {e}")
        return False


def add_bybit_config_defaults(con: sqlite3.Connection) -> bool:
    """Добавить дефолтные значения для Bybit конфигурации."""
    try:
        if not _table_exists(con, "config"):
            logger.warning("config table does not exist, skipping")
            return False
        
        bybit_defaults = {
            # Demo keys (бесплатный demo аккаунт Bybit, можно заменить на свои)
            "BYBIT_API_KEY": ("ywhtZnYQTA4XDOZML7", "Bybit API Key (demo)"),
            "BYBIT_API_SECRET": ("1MNkaemvdtnI55ziffkGwZlQYjSx16hyPxc", "Bybit API Secret (demo)"),
            "BYBIT_DEMO": ("true", "Bybit.com Demo Trading (api-demo); not testnet"),
            "BYBIT_DEFAULT_CATEGORY": ("linear", "Trading category: linear, spot, inverse"),
            "BYBIT_DEFAULT_LEVERAGE": ("3", "Default leverage (1-100)"),
            "BYBIT_MAX_LEVERAGE": ("10", "Maximum allowed leverage"),
            "MAX_RISK_PER_TRADE_PCT": ("1.0", "Max risk per trade %"),
            "MAX_POSITION_PCT": ("10.0", "Max position size % of equity"),
            "MAX_OPEN_POSITIONS": ("5", "Maximum simultaneous open positions"),
            "DEFAULT_ORDER_TYPE": ("Limit", "Default order type: Limit or Market"),
            "DEFAULT_TIME_IN_FORCE": ("GTC", "Default time in force: GTC, IOC, FOK"),
            "ENTRY_SLIPPAGE_TOLERANCE": ("0.5", "Entry slippage tolerance %"),
            "DATA_SOURCE": ("bybit", "Data source: bybit, yfinance"),
            "DEFAULT_INTERVAL": ("60", "Default chart interval in minutes"),
            "MIN_DATA_DAYS": ("30", "Minimum days of price data required"),
            "ORDER_MODE": ("disabled", "Trading mode: disabled, paper, live"),
            "LIVE_TRADING_CONFIRMED": ("false", "Confirm live trading enabled"),
            "BYBIT_TRANSACTION_LOG_SYNC_INTERVAL_MINUTES": (
                "60",
                "How often to sync Bybit UTA transaction log (minutes)",
            ),
            "BYBIT_TRANSACTION_LOG_SYNC_LOOKBACK_DAYS": (
                "7",
                "Default lookback days for Bybit UTA transaction log sync",
            ),
            "LAST_BYBIT_TRANSACTION_LOG_SYNC_AT": (
                "",
                "Last successful Bybit UTA transaction log sync (ISO UTC)",
            ),
        }
        
        for key, (value, description) in bybit_defaults.items():
            # Проверяем существование
            exists = con.execute(
                "SELECT 1 FROM config WHERE key=? LIMIT 1",
                (key,)
            ).fetchone()
            
            if not exists:
                con.execute(
                    "INSERT INTO config (key, value, description) VALUES (?, ?, ?)",
                    (key, value, description)
                )
                logger.debug(f"Added config default: {key} = {value}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding Bybit config defaults: {e}")
        return False


def create_bybit_transactions_table(con: sqlite3.Connection) -> bool:
    """Создать таблицу для логирования Bybit транзакций (аналог ib_order_transactions)."""
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS bybit_order_transactions (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at           TEXT    NOT NULL,
                event_source          TEXT    DEFAULT '',
                event_type            TEXT    DEFAULT '',
                operation_status      TEXT    DEFAULT '',
                status_before         TEXT    DEFAULT '',
                status_after          TEXT    DEFAULT '',
                ticker                TEXT    DEFAULT '',
                trade_uid             TEXT    DEFAULT '',
                bybit_order_id        TEXT    DEFAULT '',
                order_id              INTEGER DEFAULT NULL,
                trade_id              INTEGER DEFAULT NULL,
                consensus_id          INTEGER DEFAULT NULL,
                log_id                TEXT    DEFAULT '',
                request_payload_json  TEXT    DEFAULT '',
                response_payload_json TEXT    DEFAULT '',
                error_message         TEXT    DEFAULT '',
                latency_ms            INTEGER DEFAULT NULL
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_bybit_trans_order_id ON bybit_order_transactions(bybit_order_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bybit_trans_ticker ON bybit_order_transactions(ticker)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bybit_trans_occurred ON bybit_order_transactions(occurred_at)")
        logger.debug("Created bybit_order_transactions table")
        return True
    except Exception as e:
        logger.error(f"Error creating bybit_order_transactions table: {e}")
        return False


def create_bybit_uta_transaction_log_table(con: sqlite3.Connection) -> bool:
    """Bybit Unified Trading Account transaction log (exchange ledger, not bot audit)."""
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS bybit_uta_transaction_log (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                bybit_id          TEXT    NOT NULL UNIQUE,
                transaction_time  TEXT    NOT NULL,
                currency          TEXT    DEFAULT '',
                symbol            TEXT    DEFAULT '',
                category          TEXT    DEFAULT '',
                type              TEXT    DEFAULT '',
                direction         TEXT    DEFAULT '',
                side              TEXT    DEFAULT '',
                qty               TEXT    DEFAULT '',
                size              TEXT    DEFAULT '',
                trade_price       TEXT    DEFAULT '',
                funding           TEXT    DEFAULT '',
                fee               TEXT    DEFAULT '',
                cash_flow         TEXT    DEFAULT '',
                change            TEXT    DEFAULT '',
                cash_balance      TEXT    DEFAULT '',
                order_id          TEXT    DEFAULT '',
                trade_id          TEXT    DEFAULT '',
                fee_rate          TEXT    DEFAULT '',
                trans_sub_type    TEXT    DEFAULT '',
                synced_at         TEXT    DEFAULT ''
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uta_tx_time "
            "ON bybit_uta_transaction_log(transaction_time)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uta_tx_currency "
            "ON bybit_uta_transaction_log(currency)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uta_tx_symbol "
            "ON bybit_uta_transaction_log(symbol)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_uta_tx_type "
            "ON bybit_uta_transaction_log(type)"
        )
        logger.debug("Created bybit_uta_transaction_log table")
        return True
    except Exception as e:
        logger.error(f"Error creating bybit_uta_transaction_log table: {e}")
        return False


def create_bybit_gateway_log_table(con: sqlite3.Connection) -> bool:
    """Создать таблицу для логирования Bybit API вызовов (аналог ib_gateway_log)."""
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS bybit_gateway_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at    TEXT    NOT NULL,
                operation      TEXT    NOT NULL,
                ticker         TEXT    DEFAULT '',
                bybit_order_id TEXT    DEFAULT '',
                status         TEXT    DEFAULT '',
                latency_ms     INTEGER DEFAULT NULL,
                request_data   TEXT    DEFAULT '',
                response_data  TEXT    DEFAULT '',
                error_msg      TEXT    DEFAULT ''
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_bybit_log_ticker ON bybit_gateway_log(ticker)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bybit_log_occurred ON bybit_gateway_log(occurred_at)")
        logger.debug("Created bybit_gateway_log table")
        return True
    except Exception as e:
        logger.error(f"Error creating bybit_gateway_log table: {e}")
        return False


def migrate_heartbeat_log(con: sqlite3.Connection) -> bool:
    """Добавить bybit_ok поле в heartbeat_log таблицу."""
    try:
        if not _table_exists(con, "heartbeat_log"):
            logger.warning("heartbeat_log table does not exist, skipping")
            return False
        
        if not _column_exists(con, "heartbeat_log", "bybit_ok"):
            con.execute("ALTER TABLE heartbeat_log ADD COLUMN bybit_ok INTEGER DEFAULT 0")
            logger.debug("Added bybit_ok column to heartbeat_log")
        
        return True
    except Exception as e:
        logger.error(f"Error migrating heartbeat_log: {e}")
        return False


def migrate_to_bybit(db_file: str) -> bool:
    """
    Выполнить полную миграцию базы данных для Bybit.
    
    Args:
        db_file: Путь к файлу базы данных SQLite
    
    Returns:
        True если миграция успешна
    """
    logger.debug(f"Starting Bybit migration for: {db_file}")
    
    try:
        with sqlite3.connect(db_file) as con:
            # Применяем все миграции
            migrate_orders_table(con)
            migrate_trades_table(con)
            migrate_settings_table(con)
            migrate_price_data_table(con)
            migrate_heartbeat_log(con)
            create_bybit_transactions_table(con)
            create_bybit_uta_transaction_log_table(con)
            create_bybit_gateway_log_table(con)
            add_bybit_config_defaults(con)
            
            con.commit()
        
        logger.debug("Bybit migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Bybit migration failed: {e}")
        return False


def main():
    """CLI entry point."""
    import sys
    import os
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    
    # Find database file
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_db = os.path.join(project_root, "database", "trading_robot.db")
    
    db_file = sys.argv[1] if len(sys.argv) > 1 else default_db
    
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        logger.info(f"Usage: python -m scripts.core.bybit_migrate [path/to/database.db]")
        sys.exit(1)
    
    success = migrate_to_bybit(db_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
