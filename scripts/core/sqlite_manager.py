"""
SQLite storage manager — drop-in replacement for ExcelManager.
Public interface is identical so all other modules work unchanged.
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)

_CREATE_TABLES = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (
    ticker  TEXT PRIMARY KEY,
    active  INTEGER DEFAULT 0,
    comment TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS providers (
    name        TEXT PRIMARY KEY,
    type        TEXT    DEFAULT 'ai',
    base_url    TEXT    DEFAULT '',
    api_key     TEXT    DEFAULT '',
    model       TEXT    DEFAULT '',
    temperature REAL    DEFAULT 0.2,
    max_tokens  INTEGER DEFAULT 2000,
    rate_limit  INTEGER DEFAULT 60,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS config (
    key         TEXT PRIMARY KEY,
    value       TEXT DEFAULT '',
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS logs (
    id                TEXT PRIMARY KEY,
    forecast_date     TEXT,
    created_at        TEXT,
    ticker            TEXT,
    method            TEXT,
    model             TEXT,
    confidence        REAL,
    side              TEXT,
    entry_price       REAL,
    entry_conditions  TEXT,
    exit_target       TEXT,
    exit_stop         TEXT,
    position_size     TEXT DEFAULT '',
    rationale         TEXT,
    forecast_prompt   TEXT,
    prompt_response   TEXT,
    status            TEXT DEFAULT 'NEW',
    horizon_days      INTEGER DEFAULT 1,
    actual_date       TEXT,
    actual_open       REAL,
    actual_close      REAL,
    actual_high       REAL,
    actual_low        REAL,
    entry_triggered   INTEGER,
    target_hit        INTEGER,
    stop_hit          INTEGER,
    pnl_pct           REAL,
    direction_correct INTEGER,
    exit_successful   INTEGER,
    entry_order_type  TEXT    DEFAULT 'LMT',
    entry_limit_price REAL,
    entry_tif         TEXT    DEFAULT 'GTC',
    target_price      REAL,
    take_profit_tif   TEXT    DEFAULT 'GTC',
    stop_loss_tif     TEXT    DEFAULT 'GTC'
);
CREATE INDEX IF NOT EXISTS idx_logs_ticker  ON logs(ticker);
CREATE INDEX IF NOT EXISTS idx_logs_status  ON logs(status);
CREATE INDEX IF NOT EXISTS idx_logs_date    ON logs(forecast_date);

CREATE TABLE IF NOT EXISTS price_data (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  INTEGER,
    UNIQUE(ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_price_ticker ON price_data(ticker);

CREATE TABLE IF NOT EXISTS price_data_intraday (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL,
    datetime TEXT NOT NULL,
    interval TEXT NOT NULL DEFAULT '1h',
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   INTEGER,
    UNIQUE(ticker, datetime, interval)
);
CREATE INDEX IF NOT EXISTS idx_price_intraday_ticker ON price_data_intraday(ticker, datetime);

CREATE TABLE IF NOT EXISTS accounts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    broker              TEXT NOT NULL DEFAULT 'bybit',
    account_id          TEXT NOT NULL,
    name                TEXT DEFAULT '',
    account_type        TEXT DEFAULT '',
    base_currency       TEXT DEFAULT 'USD',
    buying_power        REAL DEFAULT 0,
    net_liquidation     REAL DEFAULT 0,
    available_funds     REAL DEFAULT 0,
    cash                REAL DEFAULT 0,
    maintenance_margin  REAL DEFAULT 0,
    last_update         TEXT DEFAULT '',
    type                TEXT DEFAULT '',
    UNIQUE(broker, account_id)
);
CREATE INDEX IF NOT EXISTS idx_accounts_broker ON accounts(broker);

CREATE TABLE IF NOT EXISTS portfolio (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    account       TEXT DEFAULT '',
    broker        TEXT DEFAULT 'bybit',
    type          TEXT DEFAULT 'paper',
    quantity      REAL DEFAULT 0,
    avg_cost      REAL DEFAULT 0,
    market_price  REAL DEFAULT 0,
    market_value  REAL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    realized_pnl  REAL DEFAULT 0,
    currency      TEXT DEFAULT 'USD',
    asset_type    TEXT DEFAULT 'CRYPTO',
    sector        TEXT DEFAULT '',
    last_update   TEXT DEFAULT '',
    con_id        INTEGER DEFAULT 0,
    UNIQUE(ticker, account, broker)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_ticker ON portfolio(ticker);
CREATE INDEX IF NOT EXISTS idx_portfolio_account ON portfolio(account);

CREATE TABLE IF NOT EXISTS indicators (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    date         TEXT NOT NULL,
    price        REAL,
    ma20         REAL, ma50  REAL, ma200 REAL,
    ema9         REAL, ema21 REAL,
    rsi14        REAL, stoch_rsi REAL,
    atr14        REAL, adx14    REAL,
    macd         REAL, macd_signal REAL, macd_hist REAL,
    bb_upper     REAL, bb_lower   REAL, bb_middle  REAL,
    obv          REAL,
    change_5d    REAL, change_10d REAL, change_20d REAL, change_50d REAL,
    volume_avg_20 REAL, volume_current INTEGER,
    market_regime TEXT,
    UNIQUE(ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ind_ticker ON indicators(ticker);

CREATE TABLE IF NOT EXISTS prompts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT,
    ticker      TEXT,
    method      TEXT,
    prompt_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_prompts_ticker ON prompts(ticker);

CREATE TABLE IF NOT EXISTS consensus (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT,
    ticker          TEXT,
    signal          TEXT,
    confidence      REAL,
    methods_long    TEXT,
    methods_short   TEXT,
    methods_neutral TEXT,
    rationale       TEXT
);
CREATE INDEX IF NOT EXISTS idx_cons_ticker ON consensus(ticker);

CREATE TABLE IF NOT EXISTS model_catalog (
    model_id    TEXT PRIMARY KEY,
    name        TEXT DEFAULT '',
    provider    TEXT DEFAULT '',
    context_len INTEGER DEFAULT 0,
    input_price REAL DEFAULT 0,
    output_price REAL DEFAULT 0,
    updated_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS prompt_templates (
    method      TEXT PRIMARY KEY,
    prompt_text TEXT DEFAULT '',
    updated_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ib_order_types (
    order_type_code TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    required_params TEXT DEFAULT '',
    optional_params TEXT DEFAULT '',
    tif_supported   TEXT DEFAULT '',
    active          INTEGER DEFAULT 1,
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS method_config (
    method          TEXT PRIMARY KEY,
    timeframe_hours INTEGER NOT NULL,
    trigger         TEXT    DEFAULT 'both',
    active          INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id                  TEXT    DEFAULT '',
    trade_uid               TEXT    DEFAULT NULL,
    ticker                  TEXT    NOT NULL,
    ib_order_id             INTEGER DEFAULT 0,
    ib_perm_id              INTEGER DEFAULT 0,
    ib_parent_id            INTEGER DEFAULT 0,
    order_role              TEXT    DEFAULT '',
    order_type              TEXT    DEFAULT '',
    action                  TEXT    DEFAULT '',
    quantity                REAL    DEFAULT 0,
    limit_price             REAL    DEFAULT NULL,
    stop_price              REAL    DEFAULT NULL,
    status                  TEXT    DEFAULT 'QUEUED',
    account_type            TEXT    DEFAULT '',
    created_at              TEXT    DEFAULT '',
    submitted_at            TEXT    DEFAULT '',
    filled_at               TEXT    DEFAULT '',
    filled_price            REAL    DEFAULT NULL,
    execution_latency_ms    INTEGER DEFAULT NULL,
    spread_at_submission    REAL    DEFAULT NULL,
    error_message           TEXT    DEFAULT '',
    is_test                 INTEGER DEFAULT 0,
    test_tag                TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_orders_ticker     ON orders(ticker);
CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_ib_parent  ON orders(ib_parent_id);
CREATE INDEX IF NOT EXISTS idx_orders_trade_uid  ON orders(trade_uid);
CREATE INDEX IF NOT EXISTS idx_orders_ib_perm_id ON orders(ib_perm_id);
CREATE INDEX IF NOT EXISTS idx_orders_is_test    ON orders(is_test);
CREATE INDEX IF NOT EXISTS idx_orders_test_tag   ON orders(test_tag);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    name                TEXT PRIMARY KEY,
    schedule_type       TEXT    DEFAULT 'interval',
    schedule_value      TEXT    DEFAULT '',
    is_active           INTEGER DEFAULT 1,
    last_run_at         TEXT    DEFAULT '',
    last_run_status     TEXT    DEFAULT '',
    last_error          TEXT    DEFAULT '',
    run_count           INTEGER DEFAULT 0,
    error_count         INTEGER DEFAULT 0,
    next_run_at         TEXT    DEFAULT '',
    skip_outside_market INTEGER DEFAULT 0,
    max_duration_sec    INTEGER DEFAULT 300
);

CREATE TABLE IF NOT EXISTS heartbeat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at  TEXT    NOT NULL,
    bybit_ok    INTEGER DEFAULT 0,
    openrouter_ok INTEGER DEFAULT 0,
    sqlite_ok     INTEGER DEFAULT 0,
    notes       TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    created_at  TEXT    DEFAULT '',
    action      TEXT    DEFAULT '',
    quantity    REAL    DEFAULT 0,
    price       REAL    DEFAULT 0,
    status      TEXT    DEFAULT 'NEW',
    portfolio   INTEGER DEFAULT 0,
    notes       TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tickets_ticker ON tickets(ticker);
CREATE INDEX IF NOT EXISTS idx_tickets_portfolio ON tickets(portfolio);

CREATE TABLE IF NOT EXISTS trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_uid        TEXT    DEFAULT NULL,
    ticker           TEXT    NOT NULL,
    consensus_id     INTEGER REFERENCES consensus(id),
    ib_parent_id     INTEGER DEFAULT 0,
    signal           TEXT    DEFAULT '',
    quantity         REAL    DEFAULT 0,
    entry_price      REAL    DEFAULT NULL,
    stop_loss        REAL    DEFAULT NULL,
    target_price     REAL    DEFAULT NULL,
    entry_filled_at  TEXT    DEFAULT '',
    exit_filled_at   TEXT    DEFAULT '',
    exit_price       REAL    DEFAULT NULL,
    close_reason     TEXT    DEFAULT '',
    realized_pnl     REAL    DEFAULT NULL,
    r_multiple       REAL    DEFAULT NULL,
    status           TEXT    DEFAULT 'OPEN',
    created_at       TEXT    DEFAULT '',
    updated_at       TEXT    DEFAULT '',
    is_test          INTEGER DEFAULT 0,
    test_tag         TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trades_ticker    ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_status    ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_consensus ON trades(consensus_id);
CREATE INDEX IF NOT EXISTS idx_trades_trade_uid ON trades(trade_uid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_trade_uid
ON trades(trade_uid)
WHERE trade_uid IS NOT NULL AND trade_uid <> '';
CREATE INDEX IF NOT EXISTS idx_trades_is_test   ON trades(is_test);
CREATE INDEX IF NOT EXISTS idx_trades_test_tag  ON trades(test_tag);

CREATE TABLE IF NOT EXISTS ib_gateway_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at    TEXT    NOT NULL,
    operation      TEXT    NOT NULL,
    ticker         TEXT    DEFAULT '',
    ib_order_id    INTEGER DEFAULT 0,
    status         TEXT    DEFAULT '',
    latency_ms     INTEGER DEFAULT NULL,
    request_data   TEXT    DEFAULT '',
    response_data  TEXT    DEFAULT '',
    error_msg      TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ib_log_ticker   ON ib_gateway_log(ticker);
CREATE INDEX IF NOT EXISTS idx_ib_log_occurred ON ib_gateway_log(occurred_at);

CREATE TABLE IF NOT EXISTS ib_order_transactions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at           TEXT    NOT NULL,
    event_source          TEXT    NOT NULL,
    event_type            TEXT    NOT NULL,
    operation_status      TEXT    DEFAULT '',
    status_before         TEXT    DEFAULT '',
    status_after          TEXT    DEFAULT '',
    ticker                TEXT    DEFAULT '',
    trade_uid             TEXT    DEFAULT NULL,
    ib_order_id           INTEGER DEFAULT 0,
    ib_perm_id            INTEGER DEFAULT 0,
    ib_parent_id          INTEGER DEFAULT 0,
    order_id              INTEGER REFERENCES orders(id),
    trade_id              INTEGER REFERENCES trades(id),
    consensus_id          INTEGER REFERENCES consensus(id),
    log_id                TEXT REFERENCES logs(id),
    request_payload_json  TEXT    DEFAULT '',
    response_payload_json TEXT    DEFAULT '',
    error_message         TEXT    DEFAULT '',
    latency_ms            INTEGER DEFAULT NULL
);

-- Portfolio history for dashboard
CREATE TABLE IF NOT EXISTS portfolio_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    row_type        TEXT    DEFAULT 'position',
    equity          REAL    DEFAULT 0,
    unrealized_pnl  REAL    DEFAULT 0,
    realized_pnl    REAL    DEFAULT 0,
    cumulative_pnl  REAL    DEFAULT 0,
    volume          REAL    DEFAULT 0,
    price           REAL    DEFAULT 0,
    account         TEXT    DEFAULT '',
    currency        TEXT    DEFAULT 'USD',
    net_liquidation REAL    DEFAULT 0,
    buying_power    REAL    DEFAULT 0,
    available_funds REAL    DEFAULT 0,
    cash            REAL    DEFAULT 0,
    maintenance_margin REAL DEFAULT 0,
    positions_count INTEGER DEFAULT 0,
    accounts_count  INTEGER DEFAULT 0,
    con_id          INTEGER DEFAULT NULL  -- IB Contract ID for linking to orders
);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_ticker ON portfolio_history(ticker);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_timestamp ON portfolio_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_row_type ON portfolio_history(row_type);
CREATE INDEX IF NOT EXISTS idx_ib_tx_occurred  ON ib_order_transactions(occurred_at);
CREATE INDEX IF NOT EXISTS idx_ib_tx_ticker    ON ib_order_transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_ib_tx_trade_uid ON ib_order_transactions(trade_uid);
CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_order  ON ib_order_transactions(ib_order_id);
CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_perm   ON ib_order_transactions(ib_perm_id);
CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_parent ON ib_order_transactions(ib_parent_id);
CREATE INDEX IF NOT EXISTS idx_ib_tx_source    ON ib_order_transactions(event_source);
CREATE INDEX IF NOT EXISTS idx_ib_tx_order_id  ON ib_order_transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_ib_tx_trade_id  ON ib_order_transactions(trade_id);
"""

_DEFAULT_CONFIG = [
    ("OPENROUTER_API_KEY",           "",           "OpenRouter API key (https://openrouter.ai)"),
    ("OPENROUTER_FREE_ONLY",         "false",      "Use only free OpenRouter models (appends :free suffix to model IDs)"),
    ("ALPHA_VANTAGE_API_KEY",        "",           "Alpha Vantage API key"),
    ("DATA_SOURCE",                  "bybit",      "Primary price data source: bybit | yfinance | alpha_vantage | finnhub"),
    # Bybit API
    ("BYBIT_API_KEY",                "",            "Bybit API Key (demo or live)"),
    ("BYBIT_API_SECRET",             "",            "Bybit API Secret (demo or live)"),
    ("BYBIT_DEMO",                   "true",        "Bybit.com Demo Trading (api-demo); not testnet"),
    ("BYBIT_DEFAULT_CATEGORY",       "linear",      "Bybit trading category: linear | spot | inverse"),
    ("BYBIT_DEFAULT_LEVERAGE",       "3",           "Default leverage for linear perpetual"),
    ("BYBIT_MAX_LEVERAGE",           "10",          "Maximum allowed leverage"),
    ("MAX_RISK_PER_TRADE",           "2.0",        "Max risk per trade % of account"),
    ("MAX_POSITIONS",                "3",          "Max simultaneous open positions"),
    ("DEFAULT_HORIZON_DAYS",         "1",          "Deprecated: horizon now uses timeframe_hours"),
    # Risk & position sizing
    ("DEFAULT_RISK_PCT",             "0.01",       "Risk per trade as fraction of NetLiquidation (1%)"),
    ("MAX_POSITION_PCT",             "0.05",       "Max single position as fraction of NetLiquidation (5%)"),
    ("MAX_SECTOR_EXPOSURE_PCT",      "0.15",       "Soft sector exposure limit (15%)"),
    ("MAX_SECTOR_HARD_LIMIT_PCT",    "0.25",       "Hard sector exposure limit — signal rejected (25%)"),
    ("SECTOR_OVERWEIGHT_FACTOR",     "0.5",        "Position size multiplier when sector soft limit exceeded"),
    # Capital provider
    ("CAPITAL_STALENESS_MINUTES",    "15",         "Bybit data staleness threshold in minutes"),
    ("PRICE_STALENESS_HOURS",        "6",          "Price data staleness threshold in hours"),
    ("PRICE_STALENESS_DAILY_DAYS",   "1",          "Price data staleness threshold for daily candles (UTC calendar days)"),
    ("MARKET_CONTEXT_BTC_SYMBOL",    "BTCUSDT",    "Benchmark symbol for crypto market context in prompts"),
    ("MARKET_CONTEXT_ETH_SYMBOL",    "ETHUSDT",    "Secondary benchmark symbol for crypto market context"),
    ("PREFERRED_ACCOUNT_TYPE",       "live",       "Preferred account type: live | paper"),
    ("MANUAL_CAPITAL_OVERRIDE",      "",           "Manual capital override (leave empty to use Bybit)"),
    # Portfolio risk sizing
    ("RISK_MODE",                    "percent_of_capital", "Risk sizing mode: percent_of_capital | percent_of_portfolio_on_stop"),
    ("RISK_PERCENT_ON_STOP",         "1.0",        "Risk as % of portfolio when stop is hit (used when RISK_MODE=percent_of_portfolio_on_stop, e.g. 1.0 = 1%)"),
    ("RISK_ACCOUNT_ID",              "",           "Account ID to use for portfolio value (required in percent_of_portfolio_on_stop mode)"),
    ("BYBIT_CAPITAL_FAILSAFE",      "manual_only", "Fallback when Bybit data stale/unavailable: manual_only | deny"),
    ("IB_CAPITAL_FAILSAFE",         "manual_only", "Deprecated alias for BYBIT_CAPITAL_FAILSAFE"),
    # Order management
    ("ORDER_MODE",                   "disabled",   "Order mode: disabled | paper | live"),
    ("LIVE_TRADING_CONFIRMED",       "false",      "Must be 'true' to enable live trading"),
    ("ENTRY_SLIPPAGE_PCT",           "0.001",      "Allowed entry slippage fraction (0.1%)"),
    ("MAX_SPREAD_PCT",               "0.005",      "Max bid/ask spread for Market orders (Slippage Guard)"),
    ("USE_STOP_LIMIT",               "false",      "Use Stop-Limit instead of Stop for stop-loss orders"),
    ("STOP_LIMIT_OFFSET_PCT",        "0.0005",     "Offset for Stop-Limit orders"),
    ("ORDER_QUEUE_MAX_AGE_HOURS",    "24",         "Hours before QUEUED order becomes EXPIRED"),
    ("MAX_OPEN_ORDERS",              "5",          "Maximum simultaneous open orders"),
    ("ORDER_CHILD_TIMEOUT_SEC",      "10",         "Seconds after Entry fill to wait for child orders"),
    ("ORDER_ROLLBACK_TIMEOUT_SEC",   "30",         "Seconds to wait for rollback confirmation"),
    ("AUTO_BLOCK_ON_ROLLBACK_FAIL",  "true",       "Block ticker trading on ROLLBACK_FAILED"),
    ("ALERT_CHANNELS",               "[]",         "Notification channels: push, email, telegram (JSON list)"),
    # Order queue and cleanup
    ("FILLED_ORDERS_RETENTION_DAYS", "30",         "Days to keep FILLED_ENTRY orders before cleanup"),
    ("SUBMITTED_ORDERS_MAX_AGE_HOURS", "12",       "Hours before SUBMITTED orders become STALE (if not updated)"),
    # Consensus
    ("CONSENSUS_MAX_DEVIATION",      "0.15",       "Max target_price deviation from current price (15%)"),
    ("CONFIDENCE_THRESHOLD",         "55",         "Min weighted confidence % for directional signal (0-100)"),
    ("DISAGREEMENT_THRESHOLD",       "0.40",       "Max minority weight share before forcing NEUTRAL (0-1)"),
    ("MIN_EXPECTED_R",             "0.5",        "Min expected R (confidence × reward/risk) for signal"),
    ("MIN_MODELS_FOR_SIDE",        "2",          "Min unique AI models agreeing on winning side"),
    ("REGIME_CONSENSUS_OVERRIDES",   "{}",         "Per-regime JSON overrides for consensus thresholds"),
    ("ADVERSARIAL_PROMPT_ENABLED",   "true",       "Require SHORT/LONG debate in forecast prompts"),
    ("KELLY_FRACTION",               "0.25",       "Fraction of full Kelly for position sizing (0-1)"),
    # Model weights
    ("MODEL_WEIGHT_EMA_ALPHA",       "0.2",        "EMA smoothing factor for provider accuracy weights"),
    # Scheduler
    ("FORECAST_INTERVAL_MINUTES",    "240",        "Forecast cycle interval in minutes"),
    ("EVALUATE_INTERVAL_MINUTES",    "120",        "Evaluate past forecasts interval in minutes"),
    ("PRICE_DATA_INTERVAL_MINUTES",  "60",         "Price data refresh interval in minutes"),
    ("INTRADAY_UPDATE_INTERVAL_MINUTES", "60",     "Intraday (hourly) price data refresh interval in minutes"),
    ("SCHEDULER_MAX_WORKERS",        "4",          "Scheduler thread pool worker count"),
    ("SCHEDULER_MAX_RETRIES",        "2",          "Max retries for failed scheduled tasks"),
    ("ORDER_STATUS_SYNC_INTERVAL_SECONDS", "60",   "Interval for automatic order status synchronization in seconds"),
    ("HEARTBEAT_OPENROUTER_GRACE_SEC","120",        "Grace period before circuit-open triggers degradation"),
    ("PORTFOLIO_HISTORY_SNAPSHOT_INTERVAL_MINUTES", "1440", "How often to collect portfolio history snapshot (minutes)"),
    ("PORTFOLIO_SYNC_INTERVAL_MINUTES", "5",       "How often to sync Portfolio table from Bybit (minutes)"),
    ("BYBIT_TRANSACTION_LOG_SYNC_INTERVAL_MINUTES", "60", "Bybit UTA transaction log sync interval (minutes)"),
    ("BYBIT_TRANSACTION_LOG_SYNC_LOOKBACK_DAYS", "7", "Default lookback days for Bybit UTA transaction log sync"),
    ("LAST_BYBIT_TRANSACTION_LOG_SYNC_AT", "", "Last successful Bybit UTA transaction log sync (ISO UTC)"),
    # Order activation pipeline
    ("SKIP_FORECAST_WHEN_EXPOSED",   "true",       "Skip LLM forecasts when ticker has open order or position"),
    ("FORECAST_TTL_MINUTES",         "240",        "Signal TTL in minutes — PENDING_ORDER older than this becomes EXPIRED"),
    ("PENDING_ORDERS_INTERVAL_MINUTES","1",        "How often to process PENDING_ORDER consensus (minutes)"),
]

_DEFAULT_PROVIDERS = [
    ("claude-sonnet",   "ai",   "https://openrouter.ai/api/v1", "", "anthropic/claude-sonnet-4",           0.2, 2000, 60, 1),
    ("gpt-4o",          "ai",   "https://openrouter.ai/api/v1", "", "openai/gpt-4o",                       0.2, 2000, 60, 1),
    ("deepseek-v3",     "ai",   "https://openrouter.ai/api/v1", "", "deepseek/deepseek-chat-v3-0324",       0.2, 2000, 60, 1),
    ("gemini-flash",    "ai",   "https://openrouter.ai/api/v1", "", "google/gemini-2.5-flash-preview",      0.2, 2000, 60, 1),
    ("sonar-pro",       "ai",   "https://openrouter.ai/api/v1", "", "perplexity/sonar-pro",                 0.2, 2000, 60, 1),
    ("alpha_vantage",   "data", "",                             "", "",                                     0.0,    0,  5, 1),
    ("yfinance",        "data", "",                             "", "",                                     0.0,    0, 60, 1),
    ("finnhub",         "data", "",                             "", "",                                     0.0,    0, 60, 0),
]

_DEFAULT_CATALOG = [
    # (model_id, name, provider, context_len, input_$/1M, output_$/1M)
    ("anthropic/claude-sonnet-4",           "Claude Sonnet 4",             "Anthropic",  200000, 3.00,  15.00),
    ("anthropic/claude-3.5-sonnet",          "Claude 3.5 Sonnet",           "Anthropic",  200000, 3.00,  15.00),
    ("anthropic/claude-3.5-haiku",           "Claude 3.5 Haiku",            "Anthropic",  200000, 0.80,   4.00),
    ("anthropic/claude-3-opus",              "Claude 3 Opus",               "Anthropic",  200000, 15.00, 75.00),
    ("openai/gpt-4.1",                       "GPT-4.1",                     "OpenAI",     128000, 2.00,   8.00),
    ("openai/gpt-4o",                        "GPT-4o",                      "OpenAI",     128000, 2.50,  10.00),
    ("openai/gpt-4o-mini",                   "GPT-4o Mini",                 "OpenAI",     128000, 0.15,   0.60),
    ("openai/o3",                            "o3",                          "OpenAI",     200000, 10.00, 40.00),
    ("openai/o3-mini",                       "o3-mini",                     "OpenAI",     200000, 1.10,   4.40),
    ("openai/o4-mini",                       "o4-mini",                     "OpenAI",     200000, 1.10,   4.40),
    ("deepseek/deepseek-chat-v3-0324",        "DeepSeek V3 0324",            "DeepSeek",   65536,  0.27,   1.10),
    ("deepseek/deepseek-chat",               "DeepSeek Chat",               "DeepSeek",   65536,  0.27,   1.10),
    ("deepseek/deepseek-r1",                 "DeepSeek R1",                 "DeepSeek",   65536,  0.55,   2.19),
    ("deepseek/deepseek-r1-distill-llama-70b","DeepSeek R1 Distill 70B",    "DeepSeek",   65536,  0.23,   0.69),
    ("google/gemini-2.5-pro-preview",         "Gemini 2.5 Pro",             "Google",    1000000, 1.25,  10.00),
    ("google/gemini-2.5-flash-preview",       "Gemini 2.5 Flash",           "Google",    1000000, 0.15,   0.60),
    ("google/gemini-2.0-flash-001",           "Gemini 2.0 Flash",           "Google",    1000000, 0.10,   0.40),
    ("perplexity/sonar-pro",                 "Sonar Pro",                   "Perplexity",  200000, 3.00,  15.00),
    ("perplexity/sonar",                     "Sonar",                       "Perplexity",  127072, 1.00,   1.00),
    ("perplexity/sonar-reasoning-pro",        "Sonar Reasoning Pro",        "Perplexity",  127072, 8.00,  40.00),
    ("meta-llama/llama-4-maverick",           "Llama 4 Maverick",           "Meta",       524288, 0.17,   0.60),
    ("meta-llama/llama-3.3-70b-instruct",     "Llama 3.3 70B",              "Meta",       131072, 0.12,   0.30),
    ("mistralai/mistral-large-2411",          "Mistral Large 24.11",        "Mistral",    131072, 2.00,   6.00),
    ("mistralai/mistral-small-3.1-24b-instruct","Mistral Small 3.1 24B",   "Mistral",    131072, 0.10,   0.30),
    ("x-ai/grok-3-mini-beta",                "Grok 3 Mini",                 "xAI",        131072, 0.30,   0.50),
    ("x-ai/grok-2-1212",                     "Grok 2",                      "xAI",        131072, 2.00,  10.00),
    ("qwen/qwen-2.5-72b-instruct",            "Qwen 2.5 72B",               "Qwen",        32768, 0.13,   0.40),
    ("qwen/qwq-32b",                         "QwQ 32B",                     "Qwen",        32768, 0.15,   0.60),
]

_DEFAULT_SETTINGS = [
    ("BTCUSDT", 1, "Bitcoin - Linear Perpetual"),
    ("ETHUSDT", 1, "Ethereum - Linear Perpetual"),
    ("SOLUSDT", 0, "Solana - Linear Perpetual (inactive)"),
]

_DEFAULT_ORDER_TYPES = [
    # (order_type_code, name, description, required_params, optional_params, tif_supported, active, notes)
    ("MKT",       "Market",            "Рыночный ордер по текущей цене", "action, totalQuantity", "tif, account, outsideRth", "DAY, GTC, IOC", 1, ""),
    ("LMT",       "Limit",             "Лимитный ордер", "action, totalQuantity, lmtPrice", "tif, account, outsideRth", "DAY, GTC, IOC", 1, ""),
    ("STP",       "Stop",              "Стоп-ордер", "action, totalQuantity, auxPrice", "tif, account", "DAY, GTC", 1, ""),
    ("STP LMT",   "Stop Limit",        "Стоп-лимит", "action, totalQuantity, lmtPrice, auxPrice", "tif, account", "DAY, GTC", 1, ""),
    ("TRAIL",     "Trailing Stop",     "Трейлинг-стоп", "action, totalQuantity", "trailingPercent, trailStopPrice, tif, account", "DAY, GTC", 1, "auxPrice для trailStopPrice"),
    ("TRAIL LMT", "Trailing Stop Limit", "Трейлинг-стоп лимит", "action, totalQuantity, lmtPrice", "trailingPercent, trailStopPrice, tif, account", "DAY, GTC", 1, ""),
    ("MOC",       "Market on Close",   "Рыночный на закрытии", "action, totalQuantity", "account", "DAY", 1, "Только для акций, не для фьючерсов"),
    ("LOC",       "Limit on Close",    "Лимитный на закрытии", "action, totalQuantity, lmtPrice", "account", "DAY", 1, "Только для акций"),
    ("MIT",       "Market if Touched", "Рыночный при касании", "action, totalQuantity, auxPrice", "tif, account", "DAY, GTC", 0, "Исполняется когда цена касается уровня"),
    ("LIT",       "Limit if Touched",  "Лимитный при касании", "action, totalQuantity, lmtPrice, auxPrice", "tif, account", "DAY, GTC", 0, ""),
    ("PEG MKT",   "Pegged to Market",  "Привязан к рынку", "action, totalQuantity", "peggedChangeAmount, tif, account", "DAY", 0, "Привязка к национальному BEST bid/ask"),
    ("PEG LMT",   "Pegged to Limit",   "Привязан к лимиту", "action, totalQuantity, lmtPrice", "peggedChangeAmount, tif, account", "DAY", 0, ""),
    ("REL",       "Relative",          "Относительный спред", "action, totalQuantity", "percentOffset, tif, account", "DAY, GTC", 0, "Лимит +/- % от последней цены"),
    ("VWAP",      "VWAP",              "Средневзвешенная цена", "action, totalQuantity", "vwapStartTime, vwapEndTime, account", "DAY", 0, "Алго-ордер, требует подписку"),
]

_DEFAULT_PROMPT_TEMPLATES = [
    ("momentum_trend", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | MA20: ${ma20:.2f} | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}
- EMA9: ${ema9:.2f} | EMA21: ${ema21:.2f}
- RSI(14): {rsi:.1f} | MACD hist: {macd_hist:+.2f} | ADX: {adx:.1f}
- OBV: {obv_trend} | Динамика: 5д={change_5d:+.1f}% 20д={change_20d:+.1f}%

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — использовать для всех ценовых уровней):
{recent_candles}

МЕТОД: MOMENTUM TREND — АЛГОРИТМ АНАЛИЗА:
1. СИЛА ДВИЖЕНИЯ (ADX): ADX={adx:.1f} → {adx_strength}. Это НЕ то же самое, что режим {market_regime}.
2. СИСТЕМНЫЙ РЕЖИМ: {market_regime} — {regime_rationale}. Структура MA: {ma_structure}, цена {price_vs_ma20}.
3. НАПРАВЛЕНИЕ: EMA9 vs EMA21 — бычий если EMA9>EMA21, медвежий если EMA9<EMA21.
4. ПОДТВЕРЖДЕНИЕ MA: цена выше MA20+MA50 = двойное бычье подтверждение; ниже = медвежье.
5. ИМПУЛЬС: MACD hist>0 и растёт = усиление бычьего импульса; <0 и падает = медвежий.
6. ОБЪЁМ: OBV {obv_trend} — подтверждает или опровергает направление.
7. ФИЛЬТР RSI: RSI>70 при LONG = риск перекупленности, снизь confidence; RSI<30 при SHORT = риск отскока.
СИГНАЛ LONG (высокий confidence): режим STRONG_UPTREND + EMA9>EMA21 + цена>MA50 + MACD hist>0 + OBV растёт → 65-80.
СИГНАЛ LONG (умеренный): режим WEAK_TREND + ADX>25 + EMA9>EMA21 + ≥2 подтверждения → 55-65.
СИГНАЛ SHORT (высокий confidence): режим STRONG_DOWNTREND + EMA9<EMA21 + цена<MA50 + MACD hist<0 + OBV падает → 65-80.
NEUTRAL: режим RANGING, или WEAK_TREND без согласованных EMA/MA/OBV, или противоречивые сигналы → confidence<50.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: ±3% от ${price:.2f} (диапазон: ${price_m3:.2f}–${price_p3:.2f})
- stop_loss LONG: на ${price_m5:.2f}–${price_m2:.2f} (ниже MA или ATR-стоп)
- stop_loss SHORT: на ${price_p2:.2f}–${price_p5:.2f} (выше MA или ATR-стоп)
- target_price: минимум 2:1 R/R от стопа
{history}
{footer}"""),

    ("price_action", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | BB верх: ${bb_upper:.2f} | BB низ: ${bb_lower:.2f} | Позиция в BB: {bb_pos:.0f}%
- Stoch RSI: {stoch_rsi:.2f} | RSI: {rsi:.1f} | ATR: {atr_pct:.1f}% | BB ширина: {bb_width:.2f}
- MA20: ${ma20:.2f} (откл. {ma20_dev:+.1f}%) | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}
- Структура MA: {ma_structure} | Цена {price_vs_ma20}
- Динамика: 5д={change_5d:+.1f}% 20д={change_20d:+.1f}%

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — анализировать паттерны разворота/продолжения):
{recent_candles}

МЕТОД: PRICE ACTION — АЛГОРИТМ АНАЛИЗА:
0. КОНТЕКСТ РЕЖИМА: {market_regime} — {regime_rationale}. ADX={adx:.1f} ({adx_strength}) — сила движения, не метка режима.
1. ПОЗИЦИЯ В BB ({bb_pos:.0f}%): >85% = жёсткое сопротивление, <15% = жёсткая поддержка, 40-60% = нейтральная зона.
2. ПЕРЕКУПЛЕННОСТЬ/ПЕРЕПРОДАННОСТЬ: RSI>70 + Stoch RSI>0.8 = перекуплен (SHORT-биас); RSI<30 + Stoch RSI<0.2 = перепродан (LONG-биас).
3. СВЕЧНЫЕ ПАТТЕРНЫ: анализируй последние 3 свечи — пин-бары, поглощение, доджи у уровней BB.
4. ПОДДЕРЖКА/СОПРОТИВЛЕНИЕ: MA20=${ma20:.2f}, MA50=${ma50:.2f}, MA200=${ma200:.2f} — ключевые уровни. Цена отскочила или пробила?
5. ATR-ФИЛЬТР: ATR={atr_pct:.1f}% — при ATR>4% волатильность высокая, расширяй стопы; при ATR<1.5% — узкие диапазоны.
6. ПОДТВЕРЖДЕНИЕ: сигнал сильнее если RSI + Stoch RSI + позиция в BB указывают в одну сторону.
СИГНАЛ LONG: BB-позиция<20% + RSI<35 + Stoch RSI<0.3 + бычья свеча → confidence 60-75 (при RANGING/WEAK_TREND).
СИГНАЛ SHORT: BB-позиция>80% + RSI>65 + Stoch RSI>0.7 + медвежья свеча → confidence 60-75 (при RANGING/WEAK_TREND).
NEUTRAL: STRONG_* без паттерна по тренду, или WEAK_TREND без подтверждения 2–3 свечами → confidence<50.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: вход у ключевого уровня ±2% от ${price:.2f}
- stop_loss: за BB-границу или MA, не более 8% от входа
- target_price: противоположная BB-граница или следующий уровень MA, R/R ≥ 1.5:1
{history}
{footer}"""),

    ("relative_strength", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | RSI(14): {rsi:.1f} | ADX: {adx:.1f} ({adx_strength})
- EMA9: ${ema9:.2f} | EMA21: ${ema21:.2f} | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}
- Структура MA: {ma_structure} | Цена {price_vs_ma20}
- Динамика: 5д={change_5d:+.1f}% 10д={change_10d:+.1f}% 20д={change_20d:+.1f}% 50д={change_50d:+.1f}%
- Объём: {volume_current} ({vol_ratio:.1f}x среднего) | OBV: {obv_trend}

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — использовать для всех ценовых уровней):
{recent_candles}

МЕТОД: RELATIVE STRENGTH — АЛГОРИТМ АНАЛИЗА:
1. РЕЖИМ: {market_regime} — {regime_rationale}. Сравни динамику тикера с BTC/ETH из рыночного контекста.
2. МНОГОПЕРИОДНАЯ ДИНАМИКА: оцени консистентность роста/падения по всем таймфреймам (5д/10д/20д/50д).
   - Все периоды положительные = устойчивый uptrend (LONG-биас)
   - Все периоды отрицательные = устойчивый downtrend (SHORT-биас)
   - Расхождение периодов = ослабление тренда, снизь confidence (особенно при WEAK_TREND)
3. УСКОРЕНИЕ/ЗАМЕДЛЕНИЕ: сравни 5д vs 20д динамику. Если 5д > 20д → ускорение; 5д < 20д → замедление.
4. RSI КАК МЕРА СИЛЫ: RSI 50-70 = зона силы (подтверждает LONG); RSI 30-50 = зона слабости (подтверждает SHORT); RSI>70 = перекупленность, жди коррекции.
5. ОБЪЁМНОЕ ПОДТВЕРЖДЕНИЕ: рост цены + объём {vol_ratio:.1f}x среднего → подтверждённый импульс.
   При vol_ratio>1.5 движение более надёжно.
6. MA-СТРУКТУРА: {ma_structure}. Цена выше MA50 и MA200 = бычья структура; ниже = медвежья.
7. OBV: {obv_trend} — институциональное накопление/распределение.
СИЛЬНЫЙ СИГНАЛ LONG: режим STRONG_UPTREND + 5д>0% + 20д>0% + 50д>0% + RSI 55-70 + vol_ratio>1.2 + цена>MA50 → 65-80.
СИЛЬНЫЙ СИГНАЛ SHORT: режим STRONG_DOWNTREND + 5д<0% + 20д<0% + 50д<0% + RSI 30-45 + цена<MA50 → 65-80.
NEUTRAL: RANGING без vol_ratio>1.2, или WEAK_TREND с расхождением периодов → confidence<50.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: в направлении тренда ±3% от ${price:.2f}
- stop_loss: за MA50 или -6% от входа (меньшее из двух)
- target_price: проекция тренда, R/R ≥ 2:1
{history}
{footer}"""),

    ("volatility", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | ATR(14): ${atr:.2f} ({atr_pct:.1f}%) | ADX: {adx:.1f} ({adx_strength})
- BB верх: ${bb_upper:.2f} | BB низ: ${bb_lower:.2f} | Ширина BB: {bb_width:.2f} ({bb_width_pct:.1f}% цены)
- BB позиция: {bb_pos:.0f}% | RSI: {rsi:.1f} | MACD hist: {macd_hist:+.2f}
- Структура MA: {ma_structure} | Цена {price_vs_ma20}
- Динамика: 5д={change_5d:+.1f}% 20д={change_20d:+.1f}%

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — ключевые для определения направления пробоя):
{recent_candles}

МЕТОД: VOLATILITY BREAKOUT — АЛГОРИТМ АНАЛИЗА:
1. СИСТЕМНЫЙ РЕЖИМ: {market_regime} — {regime_rationale}. При RANGING + BB-сжатие — основной сценарий пробоя.
2. РЕЖИМ ВОЛАТИЛЬНОСТИ: BB-ширина={bb_width:.2f} ({bb_width_pct:.1f}% цены).
   - <2% цены = сжатие (squeeze), высокая вероятность пробоя → повышенный confidence
   - 2-4% = нормальная волатильность
   - >6% цены = расширение (после пробоя), возможен откат
3. ATR-ОЦЕНКА: ATR={atr_pct:.1f}% — размер стопа = 1.5×ATR от входа. Стоп для текущего ATR ≈ ${atr_stop_15:.2f}.
4. НАПРАВЛЕНИЕ ПРОБОЯ: анализируй последние свечи — куда давление? Цена у верхней BB ({bb_pos:.0f}%) → вероятный пробой вверх; у нижней → вниз.
5. ПОДТВЕРЖДЕНИЕ ADX: ADX={adx:.1f} ({adx_strength}). При сжатии BB + рост ADX → пробой формируется. ADX>30 = сильное направленное движение (не путать с режимом {market_regime}).
6. RSI ПРИ ПРОБОЕ: RSI>55 при пробое вверх = бычье подтверждение; RSI<45 при пробое вниз = медвежье.
7. ЛОЖНЫЙ ПРОБОЙ: если цена вышла за BB и вернулась = ловушка. Торгуй в обратном направлении.
СИГНАЛ LONG (пробой вверх): BB-сжатие + цена закрылась выше BB-верх + RSI>50 + направление по {ma_structure} → 60-75.
СИГНАЛ SHORT (пробой вниз): BB-сжатие + цена закрылась ниже BB-низ + RSI<50 + направление по {ma_structure} → 60-75.
NEUTRAL: BB расширяется без направления, или WEAK_TREND без подтверждения свечой → confidence<45.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: у границы BB или ±2% от ${price:.2f}
- stop_loss: за противоположную BB-границу или 1.5×ATR=${atr_stop_15:.2f} от входа
- target_price: проекция ширины BB от точки пробоя, R/R ≥ 1.5:1
{history}
{footer}"""),

    ("mean_reversion", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | MA20: ${ma20:.2f} (откл. {ma20_dev:+.1f}%) | MA50: ${ma50:.2f} | MA200: ${ma200:.2f}
- Структура MA: {ma_structure} | Цена {price_vs_ma20}
- RSI(14): {rsi:.1f} | Stoch RSI: {stoch_rsi:.2f} | MACD hist: {macd_hist:+.2f}
- BB верх: ${bb_upper:.2f} | BB низ: ${bb_lower:.2f} | ATR: {atr_pct:.1f}% | ADX: {adx:.1f} ({adx_strength})
- Динамика: 5д={change_5d:+.1f}% 20д={change_20d:+.1f}%

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — искать свечи разворота):
{recent_candles}

МЕТОД: MEAN REVERSION — АЛГОРИТМ АНАЛИЗА:
1. ОТКЛОНЕНИЕ ОТ СРЕДНЕГО: цена отклонена от MA20 на {ma20_dev:+.1f}%.
   - Отклонение >+5% = перегрев (SHORT к MA20); <-5% = перепроданность (LONG к MA20)
   - Отклонение >+10% = экстремальное (высокий confidence SHORT); <-10% = экстремальное (высокий confidence LONG)
2. ОСЦИЛЛЯТОРНОЕ ПОДТВЕРЖДЕНИЕ: нужно ≥2 из 3:
   - RSI={rsi:.1f}: перепродан (<35) → LONG; перекуплен (>65) → SHORT
   - Stoch RSI={stoch_rsi:.2f}: <0.25 → LONG; >0.75 → SHORT
   - MACD hist={macd_hist:+.2f}: разворот → подтверждение
3. ДИВЕРГЕНЦИЯ: цена обновила минимум, но RSI — нет = бычья дивергенция (сильный LONG-сигнал).
   Цена обновила максимум, RSI — нет = медвежья дивергенция (сильный SHORT-сигнал).
4. ФИЛЬТР РЕЖИМА: {market_regime} — {regime_rationale}. Mean reversion оптимален при RANGING.
   При STRONG_* или WEAK_TREND + ADX>25 — снижай confidence; при ADX>30 — предпочитай NEUTRAL; при ADX>35 — NEUTRAL.
5. ЦЕЛЬ ВОЗВРАТА: LONG цель = MA20 (${ma20:.2f}), затем MA50 (${ma50:.2f}). SHORT цель = MA20 (${ma20:.2f}).
6. СВЕЧИ РАЗВОРОТА: анализируй последние 3 свечи — есть ли пин-бар, молот, поглощение у уровня MA или BB?
СИГНАЛ LONG (oversold bounce): режим RANGING + откл.<-5% + RSI<35 + Stoch RSI<0.3 + ADX<25 → 60-75.
СИГНАЛ SHORT (overbought revert): режим RANGING + откл.>+5% + RSI>65 + Stoch RSI>0.7 + ADX<25 → 60-75.
НЕЛЬЗЯ ТОРГОВАТЬ: режим STRONG_* при ADX>30, или ADX>35 → NEUTRAL.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: ±2% от ${price:.2f}, с подтверждением свечного разворота
- stop_loss: за экстремум последних 3 свечей или 1.2×ATR от входа
- target_price: MA20=${ma20:.2f} для первой цели, R/R ≥ 1.5:1
{history}
{footer}"""),

    ("volume_breakout", """Сделай торговый прогноз для {ticker} на {forecast_date} (горизонт {horizon} дней).

{regime_block}

Учёт режима для метода: {regime_method_hint}
{market_context}
ТЕХНИЧЕСКИЕ ДАННЫЕ:
- Цена: ${price:.2f} | Объём: {volume_current} ({vol_ratio:.1f}x среднего)
- OBV тренд: {obv_trend} | ATR: ${atr:.2f} ({atr_pct:.1f}%) | ADX: {adx:.1f} ({adx_strength})
- MA20: ${ma20:.2f} | MA50: ${ma50:.2f} | MA200: ${ma200:.2f} | Структура MA: {ma_structure}
- EMA9: ${ema9:.2f} | EMA21: ${ema21:.2f} | Цена {price_vs_ma20}
- RSI: {rsi:.1f} | MACD hist: {macd_hist:+.2f}
- Динамика: 5д={change_5d:+.1f}% 20д={change_20d:+.1f}%

ПОСЛЕДНИЕ 5 СВЕЧЕЙ (актуальные OHLCV — анализировать объём каждой свечи):
{recent_candles}

МЕТОД: VOLUME BREAKOUT — АЛГОРИТМ АНАЛИЗА:
1. СИСТЕМНЫЙ РЕЖИМ: {market_regime} — {regime_rationale}. При WEAK_TREND требуй vol_ratio>2.5.
2. ОБЪЁМНЫЙ ИМПУЛЬС: текущий объём {vol_ratio:.1f}x среднего.
   - >3x = экстремальный импульс (очень высокий confidence при чётком направлении)
   - 2-3x = сильный импульс (высокий confidence)
   - 1.5-2x = умеренный импульс (средний confidence)
   - <1.5x = слабый объём, пробой ненадёжен (снизь confidence, рассмотри NEUTRAL)
3. НАПРАВЛЕНИЕ ПРОБОЯ: OBV {obv_trend}. Цена растёт + OBV растёт = накопление (LONG). Цена падает + OBV падает = распределение (SHORT).
4. УРОВЕНЬ ПРОБОЯ: определи ключевой уровень из последних свечей. Объём >2x при закрытии выше/ниже уровня = подтверждённый пробой.
5. ADX-ПОДТВЕРЖДЕНИЕ: ADX={adx:.1f} ({adx_strength}). ADX растёт при объёмном пробое = усиление движения. ADX<20 = объём без тренда (менее надёжно).
6. RSI ПРИ ПРОБОЕ: RSI 50-65 при пробое вверх = устойчивый рост (не перекуплен); RSI 35-50 при пробое вниз = устойчивое падение.
7. ЛОЖНЫЙ ПРОБОЙ: объём высокий, но цена вернулась в диапазон = ловушка. Торгуй в противоположную сторону с подтверждением.
8. ЦЕЛИ ПОСЛЕ ПРОБОЯ: проекция высоты предыдущего диапазона от точки пробоя.
СИГНАЛ LONG: режим STRONG_UPTREND + vol_ratio>2 + OBV растёт + цена>MA20 + RSI 50-70 → 65-80.
СИГНАЛ SHORT: режим STRONG_DOWNTREND + vol_ratio>2 + OBV падает + цена<MA20 + RSI 30-50 → 65-80.
NEUTRAL: vol_ratio<1.5, RANGING без ADX-роста, или противоречие OBV и цены → confidence<50.
ЦЕНОВЫЕ УРОВНИ (только от текущей цены ${price:.2f}):
- entry_limit_price: у уровня пробоя ±2% от ${price:.2f} (диапазон: ${price_m2:.2f}–${price_p2:.2f})
- stop_loss: за уровень пробоя, не более 2×ATR=${atr_stop_20:.2f} от входа
- target_price: проекция диапазона, минимум R/R 2:1 от стопа
{history}
{footer}"""),
]


# ---------------------------------------------------------------------------
# Table name alias: keep Excel sheet names working
# ---------------------------------------------------------------------------
_SHEET_TO_TABLE = {
    "Settings":      "settings",
    "Providers":     "providers",
    "Config":        "config",
    "Logs":          "logs",
    "PriceData":     "price_data",
    "Indicators":    "indicators",
    "Prompts":       "prompts",
    "Consensus":     "consensus",
    "Portfolio":     "portfolio",
    "Accounts":      "accounts",
    "IBOrderTypes":  "ib_order_types",
    "Tickets":       "tickets",
    # legacy
    "Log":           "logs",
    "Forecasts":     "logs",
}


def _tbl(sheet_name: str) -> str:
    return _SHEET_TO_TABLE.get(sheet_name, sheet_name.lower())


class _SQLiteManagerQueriesMixin:
    """Mixin class providing encapsulated query methods for SQLiteManager.

    These methods replace direct SQL queries that were previously scattered
    across forecast_runner.py, scheduler.py, and order_manager.py.
    """

    def insert_portfolio_history(self, records: List[Dict[str, Any]]) -> int:
        """Массовая вставка истории портфеля в таблицу portfolio_history.

        Предотвращает дублирование записей на основе (timestamp, ticker, account, row_type).

        Args:
            records: список dict с ключами: timestamp, ticker, equity, unrealized_pnl,
                realized_pnl, cumulative_pnl, volume, price, account, currency

        Returns:
            Число успешно вставленных записей.
        """
        if not records:
            return 0

        cols = [
            "timestamp", "ticker", "row_type", "equity", "unrealized_pnl", "realized_pnl", "cumulative_pnl",
            "volume", "price", "account", "currency",
            "net_liquidation", "buying_power", "available_funds", "cash",
            "maintenance_margin", "positions_count", "accounts_count", "con_id",
        ]

        try:
            with self._connect() as con:
                inserted = 0
                skipped = 0
                for r in records:
                    # Проверка на дубликат по (timestamp, ticker, account, row_type)
                    check_sql = """
                        SELECT 1 FROM portfolio_history
                        WHERE timestamp = ? AND ticker = ? AND account = ? AND row_type = ?
                        LIMIT 1
                    """
                    exists = con.execute(
                        check_sql,
                        (
                            r.get("timestamp"),
                            r.get("ticker"),
                            r.get("account", ""),
                            r.get("row_type", "position"),
                        ),
                    ).fetchone()

                    if exists:
                        skipped += 1
                        continue

                    values = [
                        r.get("timestamp", None),
                        r.get("ticker", None),
                        r.get("row_type", "position"),
                        r.get("equity", None),
                        r.get("unrealized_pnl", None),
                        r.get("realized_pnl", None),
                        r.get("cumulative_pnl", None),
                        r.get("volume", None),
                        r.get("price", None),
                        r.get("account", None),
                        r.get("currency", None),
                        r.get("net_liquidation", None),
                        r.get("buying_power", None),
                        r.get("available_funds", None),
                        r.get("cash", None),
                        r.get("maintenance_margin", None),
                        r.get("positions_count", None),
                        r.get("accounts_count", None),
                        r.get("con_id", None),
                    ]
                    sql = f"""
                        INSERT INTO portfolio_history
                        ({', '.join(cols)})
                        VALUES ({', '.join(['?'] * len(cols))})
                    """
                    con.execute(sql, values)
                    inserted += 1

                con.commit()
                if skipped > 0:
                    logger.info(f"insert_portfolio_history: inserted={inserted}, skipped duplicates={skipped}")
                return inserted
        except Exception as e:
            logger.error(f"insert_portfolio_history error: {e}")
            return 0

    def get_method_config_timeframes(self) -> dict:
        """Get active method configurations with timeframe_hours.
        
        Returns:
            Dict mapping method name to timeframe_hours
        """
        try:
            with self._connect() as con:
                df = pd.read_sql_query(
                    "SELECT method, timeframe_hours FROM method_config WHERE active=1",
                    con
                )
            result = {}
            for _, row in df.iterrows():
                result[row["method"]] = int(row["timeframe_hours"])
            return result
        except Exception as e:
            logger.warning(f"Could not load method_config timeframe_hours: {e}")
            return {}

    def get_providers_ema_accuracy(self) -> dict:
        """Get active providers with their EMA accuracy.
        
        Returns:
            Dict mapping provider name to ema_accuracy value
        """
        try:
            with self._connect() as con:
                df = pd.read_sql_query(
                    "SELECT name, ema_accuracy FROM providers WHERE active=1 AND ema_accuracy IS NOT NULL",
                    con
                )
            result = {}
            for _, row in df.iterrows():
                if row["ema_accuracy"] is not None:
                    result[str(row["name"])] = float(row["ema_accuracy"])
            return result
        except Exception as e:
            logger.warning(f"Could not load providers ema_accuracy: {e}")
            return {}

    def get_last_consensus_id(self, ticker: str) -> Optional[int]:
        """Get most recent consensus record ID for a ticker.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Consensus record ID or None
        """
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT id FROM consensus WHERE ticker=? ORDER BY id DESC LIMIT 1",
                    (ticker,)
                ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f"Could not get last consensus ID for {ticker}: {e}")
            return None

    def get_scheduled_task_last_run(self, name: str) -> Optional[str]:
        """Get last_run_at for a scheduled task.
        
        Args:
            name: Task name
            
        Returns:
            ISO datetime string or None
        """
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT last_run_at FROM scheduled_tasks WHERE name=?",
                    (name,)
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def upsert_scheduled_task(self, name: str, updates: dict) -> bool:
        """Upsert a scheduled task record.
        
        Args:
            name: Task name
            updates: Dict of column values to update
            
        Returns:
            True if successful
        """
        try:
            updates["name"] = name
            cols = list(updates.keys())
            ph = ", ".join(["?"] * len(cols))
            set_parts = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "name")
            sql = (
                f"INSERT INTO scheduled_tasks ({', '.join(cols)}) VALUES ({ph}) "
                f"ON CONFLICT(name) DO UPDATE SET {set_parts}"
            )
            with self._connect() as con:
                con.execute(sql, list(updates.values()))
            return True
        except Exception as e:
            logger.warning(f"_upsert_task {name} failed: {e}")
            return False

    def increment_task_counters(self, name: str, success: bool, error_msg: str = "") -> bool:
        """Increment run_count and error_count for a scheduled task.
        
        Args:
            name: Task name
            success: Whether the run was successful
            error_msg: Error message if failed
            
        Returns:
            True if successful
        """
        from datetime import datetime, timezone
        status = "ok" if success else "error"
        now_str = datetime.now(tz=timezone.utc).isoformat()
        try:
            with self._connect() as con:
                con.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run_at=?, last_run_status=?, last_error=?,
                        run_count = run_count + 1,
                        error_count = error_count + (CASE WHEN ? = 'error' THEN 1 ELSE 0 END)
                    WHERE name=?
                    """,
                    (now_str, status, error_msg, status, name),
                )
            return True
        except Exception as e:
            logger.warning(f"_increment_counters {name} failed: {e}")
            return False

    def get_active_tickers_direct(self) -> list:
        """Get active tickers directly from settings (fallback method).
        
        Returns:
            List of ticker strings
        """
        try:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT ticker FROM settings WHERE active=1"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            logger.warning(f"Could not get active tickers: {e}")
            return []

    def expire_queued_orders(self, cutoff_iso: str) -> int:
        """Expire stale local QUEUED orders older than cutoff.
        
        Args:
            cutoff_iso: ISO datetime string for cutoff
            
        Returns:
            Number of orders expired
        """
        try:
            with self._connect() as con:
                cur = con.execute(
                    "UPDATE orders SET status='EXPIRED' WHERE status='QUEUED' AND created_at < ?",
                    (cutoff_iso,)
                )
            return cur.rowcount
        except Exception as e:
            logger.warning(f"expire_queued_orders failed: {e}")
            return 0

    def expire_filled_orders(self, cutoff_iso: str) -> int:
        """Archive FILLED_ENTRY orders older than cutoff.
        
        Args:
            cutoff_iso: ISO datetime string for cutoff
            
        Returns:
            Number of orders archived
        """
        try:
            with self._connect() as con:
                cur = con.execute(
                    "UPDATE orders SET status='ARCHIVED' WHERE status='FILLED_ENTRY' AND filled_at < ?",
                    (cutoff_iso,)
                )
            return cur.rowcount
        except Exception as e:
            logger.warning(f"expire_filled_orders failed: {e}")
            return 0

    def expire_stuck_submitted_orders(self, cutoff_iso: str) -> int:
        """Mark stuck SUBMITTED orders as STALE if they're older than cutoff.

        Also closes any OPEN trades whose ENTRY order is being marked STALE,
        preventing phantom open positions in the portfolio.

        Args:
            cutoff_iso: ISO datetime string for cutoff

        Returns:
            Number of ENTRY orders marked as STALE
        """
        from datetime import datetime, timezone
        now_utc = datetime.now(tz=timezone.utc).isoformat()
        try:
            with self._connect() as con:
                con.execute(
                    """UPDATE trades SET status='CANCELLED', updated_at=?
                       WHERE status='OPEN'
                         AND ib_parent_id IN (
                             SELECT ib_parent_id FROM orders
                             WHERE UPPER(order_role)='ENTRY'
                               AND status='SUBMITTED'
                               AND submitted_at < ?
                         )""",
                    (now_utc, cutoff_iso),
                )
                cur = con.execute(
                    "UPDATE orders SET status='STALE' WHERE status='SUBMITTED' AND submitted_at < ?",
                    (cutoff_iso,)
                )
            return cur.rowcount
        except Exception as e:
            logger.warning(f"expire_stuck_submitted_orders failed: {e}")
            return 0

    def get_pending_consensus_orders(self) -> list:
        """Get fresh PENDING_ORDER consensus rows (within FORECAST_TTL_MINUTES)."""
        try:
            ttl = int(self.get_config_value("FORECAST_TTL_MINUTES", "240") or 240)
        except ValueError:
            ttl = 240
        try:
            return self.consensus_repo.get_pending_order_candidates(ttl)
        except Exception as e:
            logger.warning(f"get_pending_consensus_orders failed: {e}")
            return []

    def get_accounts_count(self) -> int:
        """Get count of accounts for health checks.
        
        Returns:
            Number of accounts or 0 on error
        """
        try:
            with self._connect() as con:
                row = con.execute("SELECT COUNT(*) FROM accounts").fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def log_heartbeat(self, bybit_ok: int, openrouter_ok: int, sqlite_ok: int, notes: str) -> bool:
        """Log heartbeat entry.
        
        Args:
            bybit_ok: Bybit API status (0/1)
            openrouter_ok: OpenRouter status (0/1)
            sqlite_ok: SQLite status (0/1)
            notes: Semicolon-separated notes
            
        Returns:
            True if logged successfully
        """
        from datetime import datetime, timezone
        try:
            now_str = datetime.now(tz=timezone.utc).isoformat()
            with self._connect() as con:
                con.execute(
                    "INSERT INTO heartbeat_log(checked_at, bybit_ok, openrouter_ok, sqlite_ok, notes) VALUES (?,?,?,?,?)",
                    (now_str, bybit_ok, openrouter_ok, sqlite_ok, notes),
                )
            return True
        except Exception as e:
            logger.warning(f"heartbeat: write failed: {e}")
            return False

    def get_last_price(self, ticker: str) -> float:
        """Get most recent close price for a ticker.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Last close price or 0.0 if not found
        """
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT close FROM price_data WHERE ticker=? ORDER BY date DESC LIMIT 1",
                    (ticker,)
                ).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0


class SQLiteManager(_SQLiteManagerQueriesMixin):
    """SQLite-backed storage. Drop-in replacement for ExcelManager."""

    def __init__(self, db_file: str = "database/trading_robot.db"):
        self.db_file = os.path.abspath(db_file)
        self._init_db()
        from scripts.core.storage.repositories.forecast_run_repo import ForecastRunRepository
        from scripts.core.storage.repositories.consensus_repo import ConsensusRepository
        from scripts.core.storage.repositories.orders_repo import OrdersRepository

        self.forecast_runs_repo = ForecastRunRepository(self)
        self.consensus_repo = ConsensusRepository(self)
        self.orders_repo = OrdersRepository(self)

    def mark_stuck_forecast_runs_failed(self) -> int:
        return self.forecast_runs_repo.mark_stuck_runs_failed()

    def get_max_price_data_date(self, ticker: str) -> Optional[str]:
        return self.orders_repo.get_max_price_data_date(ticker)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_db(self):
        """Create tables and seed defaults if DB is new."""
        is_new = not os.path.exists(self.db_file)
        con = self._connect()
        try:
            try:
                con.executescript(_CREATE_TABLES)
            except sqlite3.OperationalError as e:
                # If indexes fail on existing tables with different schema, log and continue
                if "no such column" in str(e).lower():
                    logger.warning(f"DB schema mismatch (likely test DB with partial tables): {e}")
                else:
                    raise
            con.commit()
            if is_new:
                self._seed_defaults(con)
                con.commit()
                logger.debug(f"Created new database: {self.db_file}")
            else:
                self._migrate_schema(con)
        finally:
            con.close()

    def _seed_defaults(self, con: sqlite3.Connection):
        con.executemany(
            "INSERT OR IGNORE INTO config(key, value, description) VALUES (?,?,?)",
            _DEFAULT_CONFIG,
        )
        con.executemany(
            "INSERT OR IGNORE INTO providers(name,type,base_url,api_key,model,temperature,max_tokens,rate_limit,active) VALUES (?,?,?,?,?,?,?,?,?)",
            _DEFAULT_PROVIDERS,
        )
        con.executemany(
            "INSERT OR IGNORE INTO settings(ticker,active,comment) VALUES (?,?,?)",
            _DEFAULT_SETTINGS,
        )
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.executemany(
            "INSERT OR IGNORE INTO model_catalog(model_id,name,provider,context_len,input_price,output_price,updated_at) VALUES (?,?,?,?,?,?,?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], ts) for r in _DEFAULT_CATALOG],
        )
        con.executemany(
            "INSERT OR REPLACE INTO prompt_templates(method, prompt_text, updated_at) VALUES (?,?,?)",
            [(r[0], r[1], ts) for r in _DEFAULT_PROMPT_TEMPLATES],
        )
        con.executemany(
            "INSERT OR IGNORE INTO ib_order_types(order_type_code, name, description, required_params, optional_params, tif_supported, active, notes) VALUES (?,?,?,?,?,?,?,?)",
            _DEFAULT_ORDER_TYPES,
        )
        _METHOD_CONFIG_DEFAULTS = [
            ("momentum_trend",    24, "both",        1),
            ("price_action",       8, "price_level",  1),
            ("relative_strength", 48, "time",         1),
            ("volatility",         4, "price_level",  1),
            ("mean_reversion",    72, "price_level",  1),
            ("volume_breakout",    2, "price_level",  1),
        ]
        con.executemany(
            "INSERT OR IGNORE INTO method_config(method, timeframe_hours, trigger, active) VALUES (?,?,?,?)",
            _METHOD_CONFIG_DEFAULTS,
        )

    def _migrate_schema(self, con: sqlite3.Connection):
        """Idempotently add columns that may be missing from older DB instances."""
        _MISSING_COLS = [
            ("logs",      "actual_open",               "REAL"),
            ("logs",      "exit_successful",           "INTEGER"),
            ("accounts",  "type",                      "TEXT DEFAULT ''"),
            ("portfolio", "type",                      "TEXT DEFAULT 'paper'"),
            # Step 1 additions
            ("settings",  "sector",                    "TEXT DEFAULT ''"),
            ("settings",  "trading_blocked",           "INTEGER DEFAULT 0"),
            ("logs",      "stop_loss",                 "REAL"),
            ("logs",      "rr_ratio",                  "REAL"),
            ("logs",      "timeframe_hours",           "INTEGER"),
            ("logs",      "risk_amount",               "REAL"),
            ("logs",      "risk_pct",                  "REAL"),
            ("logs",      "sector",                    "TEXT DEFAULT ''"),
            ("logs",      "sector_exposure_at_signal", "REAL"),
            ("providers", "ema_accuracy",              "REAL"),
            ("providers", "ema_updated_at",            "TEXT DEFAULT ''"),
            ("providers", "forecast_count",            "INTEGER DEFAULT 0"),
            ("accounts",  "last_sync",                 "TEXT DEFAULT ''"),
            ("consensus", "target_price",              "REAL"),
            ("consensus", "stop_loss",                 "REAL"),
            # Bracket order fields for logs
            ("logs",      "entry_order_type",          "TEXT DEFAULT 'LMT'"),
            ("logs",      "entry_limit_price",         "REAL"),
            ("logs",      "entry_tif",                 "TEXT DEFAULT 'GTC'"),
            ("logs",      "target_price",              "REAL"),
            ("logs",      "take_profit_tif",           "TEXT DEFAULT 'GTC'"),
            ("logs",      "stop_loss_tif",             "TEXT DEFAULT 'GTC'"),
            # Execute field additions
            ("providers", "execute",                   "TEXT DEFAULT 'yes' CHECK (execute IN ('yes', 'no'))"),
            ("method_config", "execute",               "TEXT DEFAULT 'yes' CHECK (execute IN ('yes', 'no'))"),
            # Consensus extended fields
            ("consensus", "entry_limit_price",          "REAL"),
            ("consensus", "high_model_disagreement",    "INTEGER DEFAULT 0"),
            # Consensus evaluation fields
            ("consensus", "horizon_hours",              "INTEGER"),
            ("consensus", "eval_target_date",           "TEXT DEFAULT ''"),
            ("consensus", "eval_status",                "TEXT DEFAULT 'PENDING'"),
            ("consensus", "actual_date",                "TEXT DEFAULT ''"),
            ("consensus", "actual_open",                "REAL"),
            ("consensus", "actual_close",               "REAL"),
            ("consensus", "actual_high",                "REAL"),
            ("consensus", "actual_low",                 "REAL"),
            ("consensus", "entry_price_actual",         "REAL"),
            ("consensus", "target_hit",                 "INTEGER"),
            ("consensus", "stop_hit",                   "INTEGER"),
            ("consensus", "first_hit",                  "TEXT"),
            ("consensus", "exit_successful",             "INTEGER"),
            ("consensus", "direction_correct",          "INTEGER"),
            ("consensus", "pnl_pct",                    "REAL"),
            ("consensus", "r_multiple",                 "REAL"),
            # Forecast run tracking fields
            ("logs",      "run_id",                     "INTEGER REFERENCES forecast_runs(id)"),
            ("consensus", "run_id",                     "INTEGER REFERENCES forecast_runs(id)"),
            ("consensus", "original_run_id",            "INTEGER REFERENCES forecast_runs(id)"),
            # forecast_run_links extended fields
            ("forecast_run_links", "calibrated_confidence", "REAL"),
            ("forecast_run_links", "calibration_factor",    "REAL"),
            ("forecast_run_links", "entry_price",            "REAL"),
            ("forecast_run_links", "r_multiple",             "REAL"),
            ("forecast_run_links", "atr_14",                 "REAL"),
            # Order activation fields (Phase 1)
            ("consensus", "order_state",       "TEXT DEFAULT ''"),
            ("consensus", "order_checked_at",  "TEXT DEFAULT ''"),
            ("consensus", "order_attempted_at","TEXT DEFAULT ''"),
            ("consensus", "order_reason",      "TEXT DEFAULT ''"),
            ("consensus", "trade_id",          "INTEGER REFERENCES trades(id)"),
            # Consensus transparency & MAE/MFE
            ("consensus", "filter_reasons",           "TEXT DEFAULT '[]'"),
            ("consensus", "models_long_count",        "INTEGER"),
            ("consensus", "models_short_count",       "INTEGER"),
            ("consensus", "minority_weight_pct",      "REAL"),
            ("consensus", "expected_r",               "REAL"),
            ("consensus", "active_settings_json",     "TEXT DEFAULT '{}'"),
            ("consensus", "market_regime",            "TEXT DEFAULT ''"),
            ("consensus", "mae_pct",                  "REAL"),
            ("consensus", "mfe_pct",                  "REAL"),
            # Meta-labeling
            ("consensus", "net_pnl_pct",              "REAL"),
            ("consensus", "costs_pct",                "REAL"),
            ("consensus", "label_meta",               "INTEGER"),
            ("consensus", "meta_score",               "REAL"),
            ("consensus", "meta_decision",            "TEXT DEFAULT ''"),
            ("consensus", "meta_model_version",       "TEXT DEFAULT ''"),
            ("consensus", "meta_features_json",       "TEXT DEFAULT ''"),
            # Test marker fields
            ("orders",    "trade_uid",         "TEXT DEFAULT NULL"),
            ("orders",    "ib_perm_id",        "INTEGER DEFAULT 0"),
            ("trades",    "trade_uid",         "TEXT DEFAULT NULL"),
            ("ib_order_transactions", "trade_uid", "TEXT DEFAULT NULL"),
            ("ib_order_transactions", "ib_perm_id", "INTEGER DEFAULT 0"),
            ("orders",    "is_test",           "INTEGER DEFAULT 0"),
            ("orders",    "test_tag",          "TEXT DEFAULT ''"),
            ("trades",    "is_test",           "INTEGER DEFAULT 0"),
            ("trades",    "test_tag",          "TEXT DEFAULT ''"),
            ("portfolio_history", "row_type",            "TEXT DEFAULT 'position'"),
            ("portfolio_history", "net_liquidation",     "REAL DEFAULT 0"),
            ("portfolio_history", "buying_power",        "REAL DEFAULT 0"),
            ("portfolio_history", "available_funds",     "REAL DEFAULT 0"),
            ("portfolio_history", "cash",                "REAL DEFAULT 0"),
            ("portfolio_history", "maintenance_margin",  "REAL DEFAULT 0"),
            ("portfolio_history", "positions_count",     "INTEGER DEFAULT 0"),
            ("portfolio_history", "accounts_count",      "INTEGER DEFAULT 0"),
            # Bybit multi-profile account fields
            ("accounts",  "uid",                       "TEXT DEFAULT ''"),
            ("accounts",  "mode",                      "TEXT DEFAULT ''"),
            ("accounts",  "unrealized_pnl",            "REAL DEFAULT 0"),
            ("accounts",  "positions_count",           "INTEGER DEFAULT 0"),
            ("accounts",  "profile",                   "TEXT DEFAULT ''"),
        ]
        for table, col, col_type in _MISSING_COLS:
            try:
                cur = con.execute(f"PRAGMA table_info({table})")
                existing = {row[1] for row in cur.fetchall()}
                if col not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                    con.commit()
                    logger.debug(f"Schema migration: added column {table}.{col}")
            except Exception as e:
                logger.warning(f"Schema migration skipped {table}.{col}: {e}")

        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_history_row_type ON portfolio_history(row_type)")
            con.commit()
        except Exception as e:
            logger.warning(f"Schema migration skipped idx_portfolio_history_row_type: {e}")

        # Seed missing Bybit config keys into existing DBs
        _BYBIT_CONFIG_KEYS = [
            ("BYBIT_API_KEY",          "",       "Bybit API Key (demo or live)"),
            ("BYBIT_API_SECRET",       "",       "Bybit API Secret (demo or live)"),
            ("BYBIT_DEMO",             "true",   "Bybit.com Demo Trading (api-demo); not testnet"),
            ("BYBIT_DEFAULT_CATEGORY", "linear", "Bybit trading category: linear | spot | inverse"),
            ("BYBIT_DEFAULT_LEVERAGE", "3",      "Default leverage for linear perpetual"),
            ("BYBIT_MAX_LEVERAGE",     "10",     "Maximum allowed leverage"),
        ]
        try:
            con.executemany(
                "INSERT OR IGNORE INTO config(key, value, description) VALUES (?,?,?)",
                _BYBIT_CONFIG_KEYS,
            )
            con.commit()
        except Exception as e:
            logger.warning(f"Schema migration: Bybit config seed skipped: {e}")

        # Rename heartbeat_log.ib_ok -> bybit_ok (SQLite 3.25.0+)
        try:
            cur = con.execute("PRAGMA table_info(heartbeat_log)")
            cols = {row[1] for row in cur.fetchall()}
            if "ib_ok" in cols and "bybit_ok" not in cols:
                con.execute("ALTER TABLE heartbeat_log RENAME COLUMN ib_ok TO bybit_ok")
                con.commit()
                logger.debug("Schema migration: renamed heartbeat_log.ib_ok -> bybit_ok")
        except Exception as e:
            logger.warning(f"Schema migration skipped heartbeat_log rename: {e}")

        # Ensure new tables exist (for DBs created before this migration)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS method_config (
                method          TEXT PRIMARY KEY,
                timeframe_hours INTEGER NOT NULL,
                trigger         TEXT    DEFAULT 'both',
                active          INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id               TEXT    DEFAULT '',
                trade_uid            TEXT    DEFAULT NULL,
                ticker               TEXT    NOT NULL,
                ib_order_id          INTEGER DEFAULT 0,
                ib_perm_id           INTEGER DEFAULT 0,
                ib_parent_id         INTEGER DEFAULT 0,
                order_role           TEXT    DEFAULT '',
                order_type           TEXT    DEFAULT '',
                action               TEXT    DEFAULT '',
                quantity             REAL    DEFAULT 0,
                limit_price          REAL    DEFAULT NULL,
                stop_price           REAL    DEFAULT NULL,
                status               TEXT    DEFAULT 'QUEUED',
                account_type         TEXT    DEFAULT '',
                created_at           TEXT    DEFAULT '',
                submitted_at         TEXT    DEFAULT '',
                filled_at            TEXT    DEFAULT '',
                filled_price         REAL    DEFAULT NULL,
                execution_latency_ms INTEGER DEFAULT NULL,
                spread_at_submission REAL    DEFAULT NULL,
                error_message        TEXT    DEFAULT '',
                is_test              INTEGER DEFAULT 0,
                test_tag             TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_orders_ticker    ON orders(ticker);
            CREATE INDEX IF NOT EXISTS idx_orders_status    ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_ib_parent ON orders(ib_parent_id);
            CREATE INDEX IF NOT EXISTS idx_orders_trade_uid ON orders(trade_uid);
            CREATE INDEX IF NOT EXISTS idx_orders_ib_perm_id ON orders(ib_perm_id);
            CREATE INDEX IF NOT EXISTS idx_orders_is_test   ON orders(is_test);
            CREATE INDEX IF NOT EXISTS idx_orders_test_tag  ON orders(test_tag);
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                name                TEXT PRIMARY KEY,
                schedule_type       TEXT    DEFAULT 'interval',
                schedule_value      TEXT    DEFAULT '',
                is_active           INTEGER DEFAULT 1,
                last_run_at         TEXT    DEFAULT '',
                last_run_status     TEXT    DEFAULT '',
                last_error          TEXT    DEFAULT '',
                run_count           INTEGER DEFAULT 0,
                error_count         INTEGER DEFAULT 0,
                next_run_at         TEXT    DEFAULT '',
                skip_outside_market INTEGER DEFAULT 0,
                max_duration_sec    INTEGER DEFAULT 300
            );
            CREATE TABLE IF NOT EXISTS heartbeat_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                checked_at    TEXT    NOT NULL,
                bybit_ok      INTEGER DEFAULT 0,
                openrouter_ok INTEGER DEFAULT 0,
                sqlite_ok     INTEGER DEFAULT 0,
                notes         TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT    NOT NULL,
                created_at  TEXT    DEFAULT '',
                action      TEXT    DEFAULT '',
                quantity    REAL    DEFAULT 0,
                price       REAL    DEFAULT 0,
                status      TEXT    DEFAULT 'NEW',
                portfolio   INTEGER DEFAULT 0,
                notes       TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_ticker ON tickets(ticker);
            CREATE INDEX IF NOT EXISTS idx_tickets_portfolio ON tickets(portfolio);

            -- Forecast run tracking tables
            CREATE TABLE IF NOT EXISTS forecast_runs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at          TEXT NOT NULL,
                completed_at        TEXT,
                trigger_type        TEXT NOT NULL,  -- 'scheduler' | 'manual' | 'recalc'
                tickers_planned     INTEGER DEFAULT 0,
                tickers_processed   INTEGER DEFAULT 0,
                consensus_count     INTEGER DEFAULT 0,
                status              TEXT DEFAULT 'running',  -- 'running' | 'completed' | 'failed'
                error_message       TEXT
            );
            CREATE TABLE IF NOT EXISTS forecast_run_links (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id                  INTEGER NOT NULL REFERENCES forecast_runs(id),
                log_id                  TEXT NOT NULL REFERENCES logs(id),
                ticker                  TEXT NOT NULL,
                method                  TEXT NOT NULL,
                model                   TEXT NOT NULL,
                signal                  TEXT,  -- 'LONG' | 'SHORT' | 'NEUTRAL'
                raw_confidence          REAL,
                calibrated_confidence   REAL,
                calibration_factor      REAL,
                win_rate                REAL,
                ema_accuracy            REAL,
                final_weight            REAL,  -- confidence × win_rate × ema_accuracy
                target_price            REAL,
                stop_loss               REAL,
                entry_price             REAL,
                r_multiple              REAL,
                atr_14                  REAL,
                included_in_consensus   INTEGER DEFAULT 1,  -- 0 если filtered (anomaly) или отклонён disagreement
                UNIQUE(run_id, log_id)
            );
            CREATE INDEX IF NOT EXISTS idx_run_links_run_id ON forecast_run_links(run_id);
            CREATE INDEX IF NOT EXISTS idx_run_links_ticker ON forecast_run_links(ticker, run_id);
            CREATE INDEX IF NOT EXISTS idx_run_links_weight ON forecast_run_links(run_id, final_weight DESC);

            CREATE TABLE IF NOT EXISTS trades (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_uid        TEXT    DEFAULT NULL,
                ticker           TEXT    NOT NULL,
                consensus_id     INTEGER REFERENCES consensus(id),
                ib_parent_id     INTEGER DEFAULT 0,
                signal           TEXT    DEFAULT '',
                quantity         REAL    DEFAULT 0,
                entry_price      REAL    DEFAULT NULL,
                stop_loss        REAL    DEFAULT NULL,
                target_price     REAL    DEFAULT NULL,
                entry_filled_at  TEXT    DEFAULT '',
                exit_filled_at   TEXT    DEFAULT '',
                exit_price       REAL    DEFAULT NULL,
                close_reason     TEXT    DEFAULT '',
                realized_pnl     REAL    DEFAULT NULL,
                r_multiple       REAL    DEFAULT NULL,
                status           TEXT    DEFAULT 'OPEN',
                created_at       TEXT    DEFAULT '',
                updated_at       TEXT    DEFAULT '',
                is_test          INTEGER DEFAULT 0,
                test_tag         TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_trades_ticker    ON trades(ticker);
            CREATE INDEX IF NOT EXISTS idx_trades_status    ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_consensus ON trades(consensus_id);
            CREATE INDEX IF NOT EXISTS idx_trades_trade_uid ON trades(trade_uid);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_trade_uid
            ON trades(trade_uid)
            WHERE trade_uid IS NOT NULL AND trade_uid <> '';
            CREATE INDEX IF NOT EXISTS idx_trades_is_test   ON trades(is_test);
            CREATE INDEX IF NOT EXISTS idx_trades_test_tag  ON trades(test_tag);

            CREATE TABLE IF NOT EXISTS ib_gateway_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at    TEXT    NOT NULL,
                operation      TEXT    NOT NULL,
                ticker         TEXT    DEFAULT '',
                ib_order_id    INTEGER DEFAULT 0,
                status         TEXT    DEFAULT '',
                latency_ms     INTEGER DEFAULT NULL,
                request_data   TEXT    DEFAULT '',
                response_data  TEXT    DEFAULT '',
                error_msg      TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ib_log_ticker   ON ib_gateway_log(ticker);
            CREATE INDEX IF NOT EXISTS idx_ib_log_occurred ON ib_gateway_log(occurred_at);

            CREATE TABLE IF NOT EXISTS ib_order_transactions (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at           TEXT    NOT NULL,
                event_source          TEXT    NOT NULL,
                event_type            TEXT    NOT NULL,
                operation_status      TEXT    DEFAULT '',
                status_before         TEXT    DEFAULT '',
                status_after          TEXT    DEFAULT '',
                ticker                TEXT    DEFAULT '',
                trade_uid             TEXT    DEFAULT NULL,
                ib_order_id           INTEGER DEFAULT 0,
                ib_perm_id            INTEGER DEFAULT 0,
                ib_parent_id          INTEGER DEFAULT 0,
                order_id              INTEGER REFERENCES orders(id),
                trade_id              INTEGER REFERENCES trades(id),
                consensus_id          INTEGER REFERENCES consensus(id),
                log_id                TEXT REFERENCES logs(id),
                request_payload_json  TEXT    DEFAULT '',
                response_payload_json TEXT    DEFAULT '',
                error_message         TEXT    DEFAULT '',
                latency_ms            INTEGER DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ib_tx_occurred  ON ib_order_transactions(occurred_at);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_ticker    ON ib_order_transactions(ticker);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_trade_uid ON ib_order_transactions(trade_uid);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_order  ON ib_order_transactions(ib_order_id);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_perm   ON ib_order_transactions(ib_perm_id);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_ib_parent ON ib_order_transactions(ib_parent_id);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_source    ON ib_order_transactions(event_source);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_order_id  ON ib_order_transactions(order_id);
            CREATE INDEX IF NOT EXISTS idx_ib_tx_trade_id  ON ib_order_transactions(trade_id);
        """)
        con.commit()

        # Seed method_config defaults if empty
        cur = con.execute("SELECT COUNT(*) FROM method_config")
        if cur.fetchone()[0] == 0:
            _METHOD_CONFIG_DEFAULTS = [
                ("momentum_trend",    24, "both",        1),
                ("price_action",       8, "price_level",  1),
                ("relative_strength", 48, "time",         1),
                ("volatility",         4, "price_level",  1),
                ("mean_reversion",    72, "price_level",  1),
                ("volume_breakout",    2, "price_level",  1),
            ]
            con.executemany(
                "INSERT OR IGNORE INTO method_config(method, timeframe_hours, trigger, active) VALUES (?,?,?,?)",
                _METHOD_CONFIG_DEFAULTS,
            )
            con.commit()
            logger.debug("Schema migration: seeded method_config defaults")

        # Add index on accounts.type if missing
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(type)")
            con.commit()
        except Exception:
            pass

        # Seed new config keys for existing databases
        _NEW_CONFIG_KEYS = [
            ("DEFAULT_RISK_PCT",             "0.01",   "Risk per trade as fraction of NetLiquidation (1%)"),
            ("MAX_POSITION_PCT",             "0.05",   "Max single position as fraction of NetLiquidation (5%)"),
            ("MAX_SECTOR_EXPOSURE_PCT",      "0.15",   "Soft sector exposure limit (15%)"),
            ("MAX_SECTOR_HARD_LIMIT_PCT",    "0.25",   "Hard sector exposure limit — signal rejected (25%)"),
            ("SECTOR_OVERWEIGHT_FACTOR",     "0.5",    "Position size multiplier when sector soft limit exceeded"),
            ("CAPITAL_STALENESS_MINUTES",    "15",     "Bybit data staleness threshold in minutes"),
            ("PRICE_STALENESS_HOURS",        "6",      "Price data staleness threshold in hours"),
            ("PRICE_STALENESS_DAILY_DAYS",   "1",      "Price data staleness threshold for daily candles (UTC calendar days)"),
            ("MARKET_CONTEXT_BTC_SYMBOL",    "BTCUSDT", "Benchmark symbol for crypto market context in prompts"),
            ("MARKET_CONTEXT_ETH_SYMBOL",    "ETHUSDT", "Secondary benchmark symbol for crypto market context"),
            ("PREFERRED_ACCOUNT_TYPE",       "live",   "Preferred account type: live | paper"),
            ("MANUAL_CAPITAL_OVERRIDE",      "",       "Manual capital override (leave empty to use Bybit)"),
            ("ORDER_MODE",                   "disabled","Order mode: disabled | paper | live"),
            ("LIVE_TRADING_CONFIRMED",       "false",  "Must be 'true' to enable live trading"),
            ("ENTRY_SLIPPAGE_PCT",           "0.001",  "Allowed entry slippage fraction (0.1%)"),
            ("MAX_SPREAD_PCT",               "0.005",  "Max bid/ask spread for Market orders (Slippage Guard)"),
            ("USE_STOP_LIMIT",               "false",  "Use Stop-Limit instead of Stop for stop-loss orders"),
            ("STOP_LIMIT_OFFSET_PCT",        "0.0005", "Offset for Stop-Limit orders"),
            ("ORDER_QUEUE_MAX_AGE_HOURS",    "24",     "Hours before QUEUED order becomes EXPIRED"),
            ("MAX_OPEN_ORDERS",              "5",      "Maximum simultaneous open orders"),
            ("ORDER_CHILD_TIMEOUT_SEC",      "10",     "Seconds after Entry fill to wait for child orders"),
            ("ORDER_ROLLBACK_TIMEOUT_SEC",   "30",     "Seconds to wait for rollback confirmation"),
            ("AUTO_BLOCK_ON_ROLLBACK_FAIL",  "true",   "Block ticker trading on ROLLBACK_FAILED"),
            ("ALERT_CHANNELS",               "[]",     "Notification channels: push, email, telegram (JSON list)"),
            ("CONSENSUS_MAX_DEVIATION",      "0.15",   "Max target_price deviation from current price (15%)"),
            ("CONFIDENCE_THRESHOLD",         "55",     "Min weighted confidence % for directional signal"),
            ("DISAGREEMENT_THRESHOLD",       "0.40",   "Max minority weight share before NEUTRAL"),
            ("MIN_EXPECTED_R",             "0.5",    "Min expected R for consensus signal"),
            ("MIN_MODELS_FOR_SIDE",        "2",      "Min unique models on winning side"),
            ("REGIME_CONSENSUS_OVERRIDES",   "{}",     "Per-regime JSON threshold overrides"),
            ("ADVERSARIAL_PROMPT_ENABLED",   "true",   "Adversarial SHORT/LONG debate in prompts"),
            ("KELLY_FRACTION",               "0.25",   "Fractional Kelly multiplier cap"),
            ("AUTO_ORDER_SUBMISSION",        "false",  "Auto-submit orders after consensus (true/false)"),
            ("MODEL_WEIGHT_EMA_ALPHA",       "0.2",    "EMA smoothing factor for provider accuracy weights"),
            ("FORECAST_INTERVAL_MINUTES",    "240",    "Forecast cycle interval in minutes"),
            ("EVALUATE_INTERVAL_MINUTES",    "120",    "Evaluate past forecasts interval in minutes"),
            ("SCHEDULER_MAX_WORKERS",        "4",      "Scheduler thread pool worker count"),
            ("SCHEDULER_MAX_RETRIES",        "2",      "Max retries for failed scheduled tasks"),
            ("ORDER_STATUS_SYNC_INTERVAL_SECONDS", "60", "Interval for automatic order status synchronization in seconds"),
            ("HEARTBEAT_OPENROUTER_GRACE_SEC","120",   "Grace period before circuit-open triggers degradation"),
            # Order activation pipeline (Phase 1)
            ("SKIP_FORECAST_WHEN_EXPOSED",   "true",   "Skip LLM forecasts when ticker has open order or position"),
            ("FORECAST_TTL_MINUTES",         "240",    "Signal TTL in minutes — PENDING_ORDER older than this becomes EXPIRED"),
            ("PENDING_ORDERS_INTERVAL_MINUTES","1",   "How often to process PENDING_ORDER consensus (minutes)"),
            # Meta-labeling
            ("META_LABEL_ENABLED",           "false",  "Enable meta-label ML inference stage"),
            ("META_LABEL_ENFORCE",           "false",  "Block orders when meta rejects (false=shadow)"),
            ("META_LABEL_THRESHOLD",         "0.55",   "Min P(profitable) to pass meta gate"),
            ("META_MODEL_PATH",              "",       "Path to meta-label joblib model"),
            ("META_MODEL_VERSION",           "",       "Meta model version string for audit"),
            ("META_LABEL_MIN_EDGE_PCT",      "0.05",   "Min net PnL % for label_meta=1"),
            ("META_DATASET_MODE",            "false",  "Collect forecasts even when ticker has exposure"),
            ("BYBIT_TAKER_FEE_PCT",          "0.055",  "Bybit taker fee % (one side)"),
            ("BYBIT_MAKER_FEE_PCT",          "0.02",   "Bybit maker fee % (one side)"),
            ("META_LABEL_ASSUME_TAKER",      "true",   "Use taker fee for net PnL estimate"),
        ]
        con.executemany(
            "INSERT OR IGNORE INTO config(key, value, description) VALUES (?,?,?)",
            _NEW_CONFIG_KEYS,
        )
        con.commit()

        # Bridge old daily staleness key before removing deprecated keys.
        row = con.execute(
            "SELECT value FROM config WHERE key='PRICE_STALENESS_BUSINESS_DAYS'"
        ).fetchone()
        if row and row[0]:
            con.execute(
                """
                INSERT INTO config(key, value, description)
                VALUES ('PRICE_STALENESS_DAILY_DAYS', ?, 'Price data staleness threshold for daily candles (UTC calendar days)')
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(row[0]),),
            )
            con.commit()

        # Remove legacy stock/IB scheduler keys from existing databases.
        _DEPRECATED_CONFIG_KEYS = (
            "SCHEDULE_FORECAST",
            "SCHEDULE_EVALUATE",
            "PRICE_STALENESS_BUSINESS_DAYS",
            "ALLOW_EXTENDED_HOURS",
            "PRE_MARKET_MINUTES",
            "QUEUE_DAY_ORDERS",
            "ORDER_WINDOW_ENABLED",
            "ORDER_WINDOW_START",
            "ORDER_WINDOW_END",
            "ORDER_WINDOW_WEEKDAYS",
        )
        placeholders = ",".join("?" for _ in _DEPRECATED_CONFIG_KEYS)
        con.execute(
            f"DELETE FROM config WHERE key IN ({placeholders})",
            _DEPRECATED_CONFIG_KEYS,
        )
        con.commit()

        # Fix malformed settings table (missing ticker column) - recreate if necessary
        try:
            cur = con.execute("PRAGMA table_info(settings)")
            columns = {row[1] for row in cur.fetchall()}
            if columns and "ticker" not in columns:
                # Settings table exists but missing ticker column - need to recreate
                import time
                backup_name = f"settings_backup_{int(time.time())}"
                con.execute(f"ALTER TABLE settings RENAME TO {backup_name}")
                con.execute("""
                    CREATE TABLE settings (
                        ticker  TEXT PRIMARY KEY,
                        active  INTEGER DEFAULT 0,
                        comment TEXT    DEFAULT ''
                    )
                """)
                con.commit()
                logger.warning(
                    f"Schema migration: recreated settings table (backup: {backup_name}). "
                    f"Previous table had columns: {columns}"
                )
        except Exception as e:
            logger.warning(f"Schema migration: settings table check/fix skipped: {e}")

        # Bybit-specific columns and tables (orders.bybit_order_id, bybit_order_transactions, …)
        try:
            from scripts.core.bybit_migrate import (
                migrate_orders_table,
                migrate_trades_table,
                migrate_settings_table,
                migrate_price_data_table,
                migrate_heartbeat_log,
                create_bybit_transactions_table,
                create_bybit_uta_transaction_log_table,
                create_bybit_gateway_log_table,
                add_bybit_config_defaults,
            )
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
        except Exception as e:
            logger.warning(f"Schema migration: Bybit schema skipped: {e}")

        self._ensure_meta_label_tables(con)

    @staticmethod
    def _ensure_meta_label_tables(con: sqlite3.Connection) -> None:
        """Meta-labeling auxiliary tables."""
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS perp_market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consensus_id INTEGER,
                    ticker TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    funding_rate REAL,
                    mark_price REAL,
                    index_price REAL,
                    mark_index_premium_bps REAL,
                    volume_24h REAL
                );
                CREATE INDEX IF NOT EXISTS idx_perp_snap_consensus
                    ON perp_market_snapshots(consensus_id);
                """
            )
            con.commit()
        except Exception as e:
            logger.warning(f"Schema migration: meta-label tables skipped: {e}")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_file, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA cache_size=-65536")
        return con

    # ------------------------------------------------------------------
    # Generic read/write (ExcelManager-compatible interface)
    # ------------------------------------------------------------------

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        """Read entire table as DataFrame."""
        table = _tbl(sheet_name)
        try:
            with self._connect() as con:
                df = pd.read_sql_query(f"SELECT * FROM {table}", con)
            logger.debug(f"Read {len(df)} rows from '{table}'")
            return df
        except Exception as e:
            logger.error(f"Error reading '{table}': {e}")
            return pd.DataFrame()

    def append_to_sheet(self, sheet_name: str, data) -> bool:
        """Insert one row (dict) or many rows (list[dict] / DataFrame)."""
        table = _tbl(sheet_name)
        try:
            if isinstance(data, dict):
                rows = [data]
            elif isinstance(data, list):
                rows = data
            elif isinstance(data, pd.DataFrame):
                rows = data.to_dict("records")
            else:
                rows = [data]

            if not rows:
                return True

            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_str = ", ".join(cols)
            sql = f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders})"

            with self._connect() as con:
                for row in rows:
                    values = [_py_val(row.get(c)) for c in cols]
                    con.execute(sql, values)
            logger.debug(f"Appended {len(rows)} rows to '{table}'")
            return True
        except Exception as e:
            logger.error(f"Error appending to '{table}': {e}")
            return False

    def update_row_by_id(self, sheet_name: str, row_id: Any, update_data: dict) -> bool:
        """Update a row by its 'id' column."""
        table = _tbl(sheet_name)
        try:
            set_parts = ", ".join([f"{k} = ?" for k in update_data.keys()])
            values = [_py_val(v) for v in update_data.values()] + [str(row_id)]
            sql = f"UPDATE {table} SET {set_parts} WHERE id = ?"
            with self._connect() as con:
                con.execute(sql, values)
            return True
        except Exception as e:
            logger.error(f"Error updating row {row_id} in '{table}': {e}")
            return False

    def upsert_row(self, sheet_name: str, data: dict) -> bool:
        """Insert or replace a row."""
        table = _tbl(sheet_name)
        try:
            cols = list(data.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_str = ", ".join(cols)
            sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})"
            values = [_py_val(data[c]) for c in cols]
            with self._connect() as con:
                con.execute(sql, values)
            return True
        except Exception as e:
            logger.error(f"Error upserting to '{table}': {e}")
            return False

    def clear_sheet(self, sheet_name: str, keep_headers: bool = True) -> bool:
        """Delete all rows from table (keep_headers is a no-op for SQLite)."""
        table = _tbl(sheet_name)
        try:
            with self._connect() as con:
                con.execute(f"DELETE FROM {table}")
            logger.info(f"Cleared '{table}'")
            return True
        except Exception as e:
            logger.error(f"Error clearing '{table}': {e}")
            return False

    def reset_orders_and_trades_state(self, reset_eval_status: bool = True) -> dict:
        """Reset DB order/trade state while keeping forecasts and consensus rows.

        Returns:
            Dict with counters and status flags.
        """
        summary: Dict[str, Any] = {
            "ok": False,
            "deleted_orders": 0,
            "deleted_trades": 0,
            "deleted_ib_transactions": 0,
            "updated_consensus": 0,
            "errors": [],
        }

        try:
            with self._connect() as con:
                cur = con.cursor()
                con_cols = {r[1] for r in cur.execute("PRAGMA table_info(consensus)").fetchall()}

                # 1) Drop links from consensus to trades before deleting trade rows.
                if "trade_id" in con_cols:
                    cur.execute("UPDATE consensus SET trade_id = NULL WHERE trade_id IS NOT NULL")

                # 2) Remove execution/order records.
                try:
                    cur.execute("DELETE FROM ib_order_transactions")
                    summary["deleted_ib_transactions"] = cur.rowcount if cur.rowcount is not None else 0
                except Exception as e:
                    summary["errors"].append(f"delete ib_order_transactions failed: {e}")

                cur.execute("DELETE FROM orders")
                summary["deleted_orders"] = cur.rowcount if cur.rowcount is not None else 0

                cur.execute("DELETE FROM trades")
                summary["deleted_trades"] = cur.rowcount if cur.rowcount is not None else 0

                # 3) Restore consensus to pre-order state and clear actual-trade fields.
                set_parts: List[str] = []
                values: List[Any] = []

                if "order_checked_at" in con_cols:
                    set_parts.append("order_checked_at = ''")
                if "order_attempted_at" in con_cols:
                    set_parts.append("order_attempted_at = ''")

                if "order_state" in con_cols:
                    set_parts.append("order_state = CASE WHEN signal IN ('LONG','SHORT') THEN 'PENDING_ORDER' ELSE 'ORDER_SKIPPED' END")
                if "order_reason" in con_cols:
                    set_parts.append("order_reason = CASE WHEN signal IN ('LONG','SHORT') THEN '' ELSE 'neutral_signal' END")

                if "entry_price_actual" in con_cols:
                    set_parts.append("entry_price_actual = NULL")
                if "target_hit" in con_cols:
                    set_parts.append("target_hit = NULL")
                if "stop_hit" in con_cols:
                    set_parts.append("stop_hit = NULL")
                if "first_hit" in con_cols:
                    set_parts.append("first_hit = NULL")
                if "exit_successful" in con_cols:
                    set_parts.append("exit_successful = NULL")
                if "direction_correct" in con_cols:
                    set_parts.append("direction_correct = NULL")
                if "pnl_pct" in con_cols:
                    set_parts.append("pnl_pct = NULL")
                if "r_multiple" in con_cols:
                    set_parts.append("r_multiple = NULL")

                if "actual_date" in con_cols:
                    set_parts.append("actual_date = ''")
                if "actual_open" in con_cols:
                    set_parts.append("actual_open = NULL")
                if "actual_close" in con_cols:
                    set_parts.append("actual_close = NULL")
                if "actual_high" in con_cols:
                    set_parts.append("actual_high = NULL")
                if "actual_low" in con_cols:
                    set_parts.append("actual_low = NULL")

                if reset_eval_status and "eval_status" in con_cols:
                    set_parts.append("eval_status = ?")
                    values.append("PENDING")

                if set_parts:
                    sql = f"UPDATE consensus SET {', '.join(set_parts)}"
                    cur.execute(sql, values)
                    summary["updated_consensus"] = cur.rowcount if cur.rowcount is not None else 0

                con.commit()

            summary["ok"] = True
            return summary
        except Exception as e:
            summary["errors"].append(str(e))
            logger.error(f"Error resetting orders/trades state: {e}")
            return summary

    def reset_forecasts_consensus_and_trading(self) -> dict:
        """Remove forecasts, consensus, and local orders/trades.

        Preserves settings, accounts, price data, provider EMA, and Bybit audit
        tables (bybit_order_transactions, bybit_gateway_log).
        """
        summary: Dict[str, Any] = {
            "ok": False,
            "deleted_forecast_run_links": 0,
            "deleted_logs": 0,
            "deleted_consensus": 0,
            "deleted_forecast_runs": 0,
            "deleted_orders": 0,
            "deleted_trades": 0,
            "errors": [],
        }
        delete_steps = [
            ("deleted_forecast_run_links", "forecast_run_links"),
            ("deleted_logs", "logs"),
            ("deleted_consensus", "consensus"),
            ("deleted_forecast_runs", "forecast_runs"),
            ("deleted_orders", "orders"),
            ("deleted_trades", "trades"),
        ]
        try:
            with self._connect() as con:
                cur = con.cursor()
                for key, table in delete_steps:
                    try:
                        cur.execute(f"DELETE FROM {table}")
                        summary[key] = cur.rowcount if cur.rowcount is not None else 0
                    except Exception as e:
                        summary["errors"].append(f"delete {table}: {e}")
                con.commit()
            summary["ok"] = len(summary["errors"]) == 0
            return summary
        except Exception as e:
            summary["errors"].append(str(e))
            logger.error(f"reset_forecasts_consensus_and_trading: {e}")
            return summary

    def reset_forecasts_consensus_and_trading_dry_run(self) -> dict:
        """Row counts that would be deleted by reset_forecasts_consensus_and_trading()."""
        summary: Dict[str, Any] = {
            "ok": True,
            "would_delete_forecast_run_links": 0,
            "would_delete_logs": 0,
            "would_delete_consensus": 0,
            "would_delete_forecast_runs": 0,
            "would_delete_orders": 0,
            "would_delete_trades": 0,
            "errors": [],
        }
        table_map = {
            "would_delete_forecast_run_links": "forecast_run_links",
            "would_delete_logs": "logs",
            "would_delete_consensus": "consensus",
            "would_delete_forecast_runs": "forecast_runs",
            "would_delete_orders": "orders",
            "would_delete_trades": "trades",
        }
        try:
            with self._connect() as con:
                for key, table in table_map.items():
                    try:
                        row = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                        summary[key] = int(row[0]) if row else 0
                    except Exception:
                        summary[key] = 0
        except Exception as e:
            summary["errors"].append(str(e))
            summary["ok"] = False
        return summary

    def full_clean_slate(self) -> dict:
        """Delete all forecast/consensus/order data and reset provider EMA weights.

        Keeps configuration tables intact:
          providers, tickers/settings, method_config, config, price_data, indicators.

        Deletion order respects FK dependencies:
          forecast_run_links → logs → consensus → forecast_runs
          ib_order_transactions → orders → trades  (already done by reset_orders_and_trades_state)

        Returns:
            Dict with row counts and errors list.
        """
        summary: Dict[str, Any] = {
            "ok": False,
            "deleted_forecast_run_links": 0,
            "deleted_logs": 0,
            "deleted_consensus": 0,
            "deleted_forecast_runs": 0,
            "deleted_orders": 0,
            "deleted_trades": 0,
            "deleted_ib_transactions": 0,
            "reset_providers": 0,
            "errors": [],
        }

        try:
            with self._connect() as con:
                cur = con.cursor()

                # 1) forecast_run_links (references logs + forecast_runs)
                try:
                    cur.execute("DELETE FROM forecast_run_links")
                    summary["deleted_forecast_run_links"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete forecast_run_links: {e}")

                # 2) logs
                try:
                    cur.execute("DELETE FROM logs")
                    summary["deleted_logs"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete logs: {e}")

                # 3) consensus
                try:
                    cur.execute("DELETE FROM consensus")
                    summary["deleted_consensus"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete consensus: {e}")

                # 4) forecast_runs
                try:
                    cur.execute("DELETE FROM forecast_runs")
                    summary["deleted_forecast_runs"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete forecast_runs: {e}")

                # 5) execution tables
                try:
                    cur.execute("DELETE FROM ib_order_transactions")
                    summary["deleted_ib_transactions"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete ib_order_transactions: {e}")

                try:
                    cur.execute("DELETE FROM orders")
                    summary["deleted_orders"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete orders: {e}")

                try:
                    cur.execute("DELETE FROM trades")
                    summary["deleted_trades"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"delete trades: {e}")

                # 6) Reset provider EMA weights to neutral 0.5
                try:
                    cur.execute(
                        "UPDATE providers SET ema_accuracy = 0.5, ema_updated_at = NULL, forecast_count = 0"
                    )
                    summary["reset_providers"] = cur.rowcount or 0
                except Exception as e:
                    summary["errors"].append(f"reset providers ema_accuracy: {e}")

                con.commit()

            summary["ok"] = len(summary["errors"]) == 0
            return summary
        except Exception as e:
            summary["errors"].append(str(e))
            logger.error(f"full_clean_slate: fatal error: {e}")
            return summary

    def full_clean_slate_dry_run(self) -> dict:
        """Return row counts that would be deleted by full_clean_slate() without making changes."""
        summary: Dict[str, Any] = {
            "ok": True,
            "would_delete_forecast_run_links": 0,
            "would_delete_logs": 0,
            "would_delete_consensus": 0,
            "would_delete_forecast_runs": 0,
            "would_delete_orders": 0,
            "would_delete_trades": 0,
            "would_delete_ib_transactions": 0,
            "would_reset_providers": 0,
            "errors": [],
        }
        table_map = {
            "would_delete_forecast_run_links": "forecast_run_links",
            "would_delete_logs": "logs",
            "would_delete_consensus": "consensus",
            "would_delete_forecast_runs": "forecast_runs",
            "would_delete_orders": "orders",
            "would_delete_trades": "trades",
            "would_delete_ib_transactions": "ib_order_transactions",
        }
        try:
            with self._connect() as con:
                for key, table in table_map.items():
                    try:
                        row = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                        summary[key] = int(row[0]) if row else 0
                    except Exception:
                        summary[key] = 0
                try:
                    row = con.execute(
                        "SELECT COUNT(*) FROM providers WHERE ema_accuracy IS NOT NULL"
                    ).fetchone()
                    summary["would_reset_providers"] = int(row[0]) if row else 0
                except Exception:
                    pass
        except Exception as e:
            summary["errors"].append(str(e))
            summary["ok"] = False
        return summary

    # ------------------------------------------------------------------
    # Domain helpers (ExcelManager-compatible)
    # ------------------------------------------------------------------

    def get_settings(self) -> List[str]:
        """Return list of active ticker symbols."""
        try:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT ticker FROM settings WHERE active = 1"
                ).fetchall()
            return [r["ticker"] for r in rows]
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return []

    def get_latest_forecast_log_id(self, ticker: str) -> Optional[str]:
        """Return the log_id of the most recent forecast for a ticker."""
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT id FROM logs WHERE ticker = ? ORDER BY forecast_date DESC LIMIT 1",
                    (ticker,)
                ).fetchone()
            return row["id"] if row else None
        except Exception as e:
            logger.error(f"Error getting latest forecast log id for {ticker}: {e}")
            return None

    def get_cached_price_data(self, ticker: str, days: int = 250):
        """Return cached price data as list of dicts (newest first)."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            with self._connect() as con:
                rows = con.execute(
                    "SELECT * FROM price_data WHERE ticker=? AND date>=? ORDER BY date DESC",
                    (ticker, cutoff),
                ).fetchall()
            if not rows:
                return None
            result = []
            for r in rows:
                result.append({
                    "ticker": r["ticker"],
                    "date":   datetime.strptime(r["date"], "%Y-%m-%d"),
                    "open":   float(r["open"]),
                    "high":   float(r["high"]),
                    "low":    float(r["low"]),
                    "close":  float(r["close"]),
                    "volume": int(r["volume"]),
                })
            logger.info(f"Loaded {len(result)} cached days for {ticker}")
            return result
        except Exception as e:
            logger.error(f"Error loading cached price data: {e}")
            return None

    def save_price_data(self, price_data: list, ticker: str = None) -> bool:
        """Upsert price data records."""
        if not price_data:
            return True
        try:
            sql = """
                INSERT OR REPLACE INTO price_data (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            rows = []
            for rec in price_data:
                date_val = rec.get("date") or rec.get("Date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
                rec_ticker = rec.get("ticker") or rec.get("Ticker") or ticker or ""
                rows.append((
                    rec_ticker,
                    date_str,
                    float(rec.get("open") or rec.get("Open") or 0),
                    float(rec.get("high") or rec.get("High") or 0),
                    float(rec.get("low")  or rec.get("Low")  or 0),
                    float(rec.get("close") or rec.get("Close") or 0),
                    int(rec.get("volume") or rec.get("Volume") or 0),
                ))
            with self._connect() as con:
                con.executemany(sql, rows)
            logger.info(f"Saved {len(rows)} price records")
            return True
        except Exception as e:
            logger.error(f"Error saving price data: {e}")
            return False

    def save_intraday_data(self, bars: list, ticker: str = None, interval: str = "1h") -> bool:
        """Upsert intraday price bars into price_data_intraday."""
        if not bars:
            return True
        try:
            sql = """
                INSERT OR REPLACE INTO price_data_intraday
                    (ticker, datetime, interval, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            rows = []
            for rec in bars:
                dt_val = rec.get("datetime") or rec.get("date")
                if hasattr(dt_val, "strftime"):
                    dt_str = dt_val.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    dt_str = str(dt_val)[:19]
                rec_ticker = rec.get("ticker") or ticker or ""
                rec_interval = rec.get("interval") or interval
                rows.append((
                    rec_ticker,
                    dt_str,
                    rec_interval,
                    float(rec.get("open") or 0),
                    float(rec.get("high") or 0),
                    float(rec.get("low") or 0),
                    float(rec.get("close") or 0),
                    int(rec.get("volume") or 0),
                ))
            with self._connect() as con:
                con.executemany(sql, rows)
            logger.info(f"Saved {len(rows)} intraday bars ({interval}) for {ticker}")
            return True
        except Exception as e:
            logger.error(f"Error saving intraday data: {e}")
            return False

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def get_config_value(self, key: str, default: str = "") -> str:
        """Get a single config value."""
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT value FROM config WHERE key=?", (key,)
                ).fetchone()
            return row["value"] if row else default
        except Exception as e:
            logger.error(f"Error reading config key '{key}': {e}")
            return default

    def set_config_value(self, key: str, value: str) -> bool:
        """Set a config value."""
        try:
            with self._connect() as con:
                con.execute(
                    "INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)",
                    (key, value),
                )
            return True
        except Exception as e:
            logger.error(f"Error setting config key '{key}': {e}")
            return False

    # ------------------------------------------------------------------
    # Price data staleness check
    # ------------------------------------------------------------------

    def check_price_data_staleness(self, ticker: str) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Check if price_data for ticker is stale.

        Returns:
            (is_stale, last_date, hours_diff): is_stale=True if data is stale or missing,
            last_date is the latest date string or None,
            hours_diff is hours since last update or None.
        """
        try:
            # Get staleness threshold
            staleness_hours_str = self.get_config_value("PRICE_STALENESS_HOURS", "6")
            try:
                staleness_hours = int(staleness_hours_str)
            except ValueError:
                staleness_hours = 6
            try:
                staleness_daily_days = int(self.get_config_value("PRICE_STALENESS_DAILY_DAYS", "1"))
            except ValueError:
                staleness_daily_days = 1

            with self._connect() as con:
                row = con.execute(
                    "SELECT MAX(date) as last_date FROM price_data WHERE ticker=?",
                    (ticker,),
                ).fetchone()

            if not row or not row["last_date"]:
                # No data at all — consider stale (will trigger fresh load)
                return True, None, None

            last_date_str = row["last_date"]
            from datetime import datetime, timezone

            last_date_raw = str(last_date_str).strip()
            is_date_only = len(last_date_raw) >= 10 and last_date_raw[4] == '-' and last_date_raw[7] == '-' and ':' not in last_date_raw

            # For daily candles (YYYY-MM-DD), compare UTC calendar-day age.
            if is_date_only:
                try:
                    last_day = datetime.strptime(last_date_raw[:10], '%Y-%m-%d').date()
                except ValueError:
                    return True, last_date_str, None

                today = datetime.now(timezone.utc).date()
                if today <= last_day:
                    return False, last_date_str, 0

                calendar_days_diff = max((today - last_day).days, 0)
                is_stale = calendar_days_diff > staleness_daily_days
                return is_stale, last_date_str, calendar_days_diff * 24

            # Parse date (handle both ISO format and legacy formats)
            try:
                last_date = datetime.fromisoformat(last_date_str.replace('Z', '+00:00'))
            except ValueError:
                try:
                    last_date = datetime.strptime(last_date_str[:10], '%Y-%m-%d')
                except ValueError:
                    return True, last_date_str, None

            now = datetime.now(last_date.tzinfo) if last_date.tzinfo else datetime.now()
            hours_diff = int((now - last_date).total_seconds() / 3600)

            is_stale = hours_diff > staleness_hours
            return is_stale, last_date_str, hours_diff

        except Exception as e:
            logger.error(f"Error checking price data staleness for {ticker}: {e}")
            return True, None, None

    # ------------------------------------------------------------------
    # Model catalog
    # ------------------------------------------------------------------

    def get_model_catalog(self, provider: str = None) -> pd.DataFrame:
        """Return model_catalog as DataFrame, optionally filtered by provider."""
        try:
            where = "WHERE provider = ?" if provider else ""
            params = (provider,) if provider else ()
            with self._connect() as con:
                return pd.read_sql_query(
                    f"SELECT * FROM model_catalog {where} ORDER BY provider, name",
                    con, params=params,
                )
        except Exception as e:
            logger.error(f"Error reading model_catalog: {e}")
            return pd.DataFrame()

    def refresh_model_catalog(self, api_key: str) -> int:
        """
        Fetch the full model list from OpenRouter /models and upsert into model_catalog.
        Returns number of models upserted, or -1 on error.
        """
        import requests
        try:
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            resp.raise_for_status()
            models = resp.json().get("data", [])
            if not models:
                logger.warning("OpenRouter /models returned empty list")
                return 0
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for m in models:
                mid = m.get("id", "")
                if not mid:
                    continue
                pricing = m.get("pricing", {})
                try:
                    inp = float(pricing.get("prompt", 0)) * 1_000_000
                    out = float(pricing.get("completion", 0)) * 1_000_000
                except (TypeError, ValueError):
                    inp = out = 0.0
                ctx = m.get("context_length") or 0
                rows.append((mid, m.get("name", mid),
                             mid.split("/")[0].capitalize(),
                             int(ctx), inp, out, ts))
            with self._connect() as con:
                con.executemany(
                    "INSERT OR REPLACE INTO model_catalog"
                    "(model_id,name,provider,context_len,input_price,output_price,updated_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    rows,
                )
            logger.info(f"Model catalog refreshed: {len(rows)} models")
            return len(rows)
        except Exception as e:
            logger.error(f"Error refreshing model catalog: {e}")
            return -1

    def get_model_ids(self) -> list:
        """Return sorted list of model_id strings from catalog."""
        try:
            with self._connect() as con:
                cur = con.execute(
                    "SELECT model_id FROM model_catalog ORDER BY provider, name"
                )
                return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error reading model ids: {e}")
            return []

    # ------------------------------------------------------------------
    # Prompt templates (global, per-method)
    # ------------------------------------------------------------------

    def get_prompt_template(self, method: str) -> Optional[str]:
        """Return the template text for a method, or None if not found."""
        try:
            with self._connect() as con:
                cur = con.execute(
                    "SELECT prompt_text FROM prompt_templates WHERE method=?", (method,)
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error reading prompt template for '{method}': {e}")
            return None

    def get_all_prompt_templates(self) -> dict:
        """Return {method: prompt_text} for all methods."""
        try:
            with self._connect() as con:
                cur = con.execute(
                    "SELECT method, prompt_text FROM prompt_templates ORDER BY method"
                )
                return {r[0]: r[1] for r in cur.fetchall()}
        except Exception as e:
            logger.error(f"Error reading prompt templates: {e}")
            return {}

    def save_prompt_template(self, method: str, prompt_text: str) -> bool:
        """Upsert a prompt template for a method."""
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._connect() as con:
                con.execute(
                    "INSERT OR REPLACE INTO prompt_templates(method, prompt_text, updated_at)"
                    " VALUES (?,?,?)",
                    (method, prompt_text, ts),
                )
            return True
        except Exception as e:
            logger.error(f"Error saving prompt template for '{method}': {e}")
            return False

    def reset_prompt_template(self, method: str) -> bool:
        """Reset a prompt template to its built-in default."""
        default = next((r[1] for r in _DEFAULT_PROMPT_TEMPLATES if r[0] == method), None)
        if default is None:
            return False
        return self.save_prompt_template(method, default)

    # ------------------------------------------------------------------
    # IB Order Types helpers
    # ------------------------------------------------------------------

    def get_order_types(self, active_only: bool = False) -> pd.DataFrame:
        """Return IB order types as DataFrame. If active_only, filter active=1."""
        try:
            sql = "SELECT * FROM ib_order_types"
            params = ()
            if active_only:
                sql += " WHERE active = 1"
            sql += " ORDER BY active DESC, order_type_code"
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=params)
        except Exception as e:
            logger.error(f"Error reading order types: {e}")
            return pd.DataFrame()

    def is_order_type_active(self, order_type_code: str) -> bool:
        """Check if an order type is active."""
        try:
            with self._connect() as con:
                cur = con.execute(
                    "SELECT active FROM ib_order_types WHERE order_type_code = ?",
                    (order_type_code,)
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
        except Exception as e:
            logger.error(f"Error checking order type '{order_type_code}': {e}")
            return False

    def set_order_type_active(self, order_type_code: str, active: bool) -> bool:
        """Enable/disable an order type."""
        try:
            with self._connect() as con:
                con.execute(
                    "UPDATE ib_order_types SET active = ? WHERE order_type_code = ?",
                    (1 if active else 0, order_type_code)
                )
            return True
        except Exception as e:
            logger.error(f"Error updating order type '{order_type_code}': {e}")
            return False

    def reset_order_types(self) -> bool:
        """Reset all order types to defaults."""
        try:
            with self._connect() as con:
                con.execute("DELETE FROM ib_order_types")
                con.executemany(
                    "INSERT INTO ib_order_types(order_type_code, name, description, required_params, optional_params, tif_supported, active, notes) VALUES (?,?,?,?,?,?,?,?)",
                    _DEFAULT_ORDER_TYPES,
                )
            return True
        except Exception as e:
            logger.error(f"Error resetting order types: {e}")
            return False

    # ------------------------------------------------------------------
    # Prompt helpers (log)
    # ------------------------------------------------------------------

    def save_prompt(self, ticker: str, method: str, prompt_text: str, date: str = None) -> bool:
        """Save a prompt record."""
        try:
            ts = date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._connect() as con:
                con.execute(
                    "INSERT INTO prompts(date, ticker, method, prompt_text) VALUES (?,?,?,?)",
                    (ts, ticker, method, prompt_text),
                )
            return True
        except Exception as e:
            logger.error(f"Error saving prompt: {e}")
            return False

    def get_prompts(self, ticker: str = None, method: str = None,
                    date_from: str = None, date_to: str = None,
                    limit: int = 200) -> pd.DataFrame:
        """Fetch prompts with optional filters."""
        try:
            where = []
            params = []
            if ticker:
                where.append("ticker = ?"); params.append(ticker)
            if method:
                where.append("method = ?"); params.append(method)
            if date_from:
                where.append("date >= ?"); params.append(date_from)
            if date_to:
                where.append("date <= ?"); params.append(date_to)
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            sql = f"SELECT * FROM prompts {clause} ORDER BY date DESC LIMIT {limit}"
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=params)
        except Exception as e:
            logger.error(f"Error reading prompts: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Consensus helper
    # ------------------------------------------------------------------

    def save_consensus(self, data: dict) -> bool:
        cols = list(data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO consensus ({col_str}) VALUES ({placeholders})"
        try:
            values = [_py_val(data[c]) for c in cols]
            with self._connect() as con:
                con.execute(sql, values)
            return True
        except Exception as e:
            logger.error(f"Error saving consensus: {e}")
            return False

    def log_ib_transaction(
        self,
        *,
        occurred_at: str,
        event_source: str,
        event_type: str,
        operation_status: str = "",
        status_before: str = "",
        status_after: str = "",
        ticker: str = "",
        trade_uid: str = "",
        ib_order_id: int = 0,
        ib_perm_id: int = 0,
        ib_parent_id: int = 0,
        order_id: Optional[int] = None,
        trade_id: Optional[int] = None,
        consensus_id: Optional[int] = None,
        log_id: str = "",
        request_payload_json: str = "",
        response_payload_json: str = "",
        error_message: str = "",
        latency_ms: Optional[int] = None,
    ) -> bool:
        """Insert one row into ib_order_transactions (deprecated — use bybit_order_transactions)."""
        import warnings

        warnings.warn(
            "log_ib_transaction is deprecated; new events use bybit_order_transactions",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            with self._connect() as con:
                con.execute(
                    """
                    INSERT INTO ib_order_transactions (
                        occurred_at, event_source, event_type, operation_status,
                        status_before, status_after, ticker, trade_uid,
                        ib_order_id, ib_perm_id, ib_parent_id,
                        order_id, trade_id, consensus_id, log_id,
                        request_payload_json, response_payload_json,
                        error_message, latency_ms
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        occurred_at,
                        event_source,
                        event_type,
                        operation_status,
                        status_before,
                        status_after,
                        ticker,
                        trade_uid,
                        ib_order_id,
                        ib_perm_id,
                        ib_parent_id,
                        order_id,
                        trade_id,
                        consensus_id,
                        log_id,
                        request_payload_json,
                        response_payload_json,
                        error_message,
                        latency_ms,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"log_ib_transaction: failed to write log: {e}")
            return False

    def get_ib_transactions(
        self,
        *,
        ticker: Optional[str] = None,
        ib_order_id: Optional[int] = None,
        ib_parent_id: Optional[int] = None,
        event_source: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Return rows from ib_order_transactions (deprecated — use get_bybit_transactions)."""
        import warnings

        warnings.warn(
            "get_ib_transactions is deprecated; use get_bybit_transactions or get_broker_transactions",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            where = []
            params: list[Any] = []
            if ticker:
                where.append("UPPER(ticker)=UPPER(?)")
                params.append(ticker)
            if ib_order_id is not None:
                where.append("ib_order_id=?")
                params.append(int(ib_order_id))
            if ib_parent_id is not None:
                where.append("ib_parent_id=?")
                params.append(int(ib_parent_id))
            if event_source:
                where.append("event_source=?")
                params.append(event_source)
            if event_type:
                where.append("event_type=?")
                params.append(event_type)

            clause = f"WHERE {' AND '.join(where)}" if where else ""
            params.append(int(limit))

            with self._connect() as con:
                return pd.read_sql_query(
                    f"SELECT * FROM ib_order_transactions {clause} ORDER BY occurred_at DESC, id DESC LIMIT ?",
                    con,
                    params=params,
                )
        except Exception as e:
            logger.error(f"Error reading ib_order_transactions: {e}")
            return pd.DataFrame()

    def get_bybit_transactions(
        self,
        *,
        ticker: Optional[str] = None,
        bybit_order_id: Optional[str] = None,
        event_source: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Return rows from bybit_order_transactions with optional filters."""
        try:
            where = []
            params: list[Any] = []
            if ticker:
                where.append("UPPER(ticker)=UPPER(?)")
                params.append(ticker)
            if bybit_order_id:
                where.append("bybit_order_id=?")
                params.append(str(bybit_order_id))
            if event_source:
                where.append("event_source=?")
                params.append(event_source)
            if event_type:
                where.append("event_type=?")
                params.append(event_type)
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            params.append(int(limit))
            with self._connect() as con:
                return pd.read_sql_query(
                    f"SELECT * FROM bybit_order_transactions {clause} "
                    f"ORDER BY occurred_at DESC, id DESC LIMIT ?",
                    con,
                    params=params,
                )
        except Exception as e:
            logger.error(f"Error reading bybit_order_transactions: {e}")
            return pd.DataFrame()

    def get_broker_transactions(
        self,
        *,
        ticker: Optional[str] = None,
        order_id: Optional[str] = None,
        event_source: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 500,
        include_ib_history: bool = True,
    ) -> pd.DataFrame:
        """Unified broker transaction history (Bybit primary, optional IB legacy)."""
        bybit_df = self.get_bybit_transactions(
            ticker=ticker,
            bybit_order_id=order_id,
            event_source=event_source,
            event_type=event_type,
            limit=limit,
        )
        if not include_ib_history:
            return bybit_df
        ib_id = None
        if order_id and str(order_id).isdigit():
            ib_id = int(order_id)
        ib_df = self.get_ib_transactions(
            ticker=ticker,
            ib_order_id=ib_id,
            event_source=event_source,
            event_type=event_type,
            limit=limit,
        )
        if bybit_df.empty:
            return ib_df
        if ib_df.empty:
            return bybit_df
        return pd.concat([bybit_df, ib_df], ignore_index=True).head(limit)

    # ------------------------------------------------------------------
    # Forecast Run tracking
    # ------------------------------------------------------------------

    def create_forecast_run(self, trigger_type: str, tickers_planned: int = 0) -> int:
        """Create a new forecast run record and return its ID."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._connect() as con:
                cur = con.execute(
                    """INSERT INTO forecast_runs (started_at, trigger_type, tickers_planned, status)
                       VALUES (?, ?, ?, 'running')""",
                    (now, trigger_type, tickers_planned)
                )
                return cur.lastrowid
        except Exception as e:
            logger.error(f"Error creating forecast run: {e}")
            return None

    def complete_forecast_run(self, run_id: int, status: str = 'completed', 
                              tickers_processed: int = None, consensus_count: int = None,
                              error_message: str = None) -> bool:
        """Mark a forecast run as completed or failed."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updates = ["completed_at = ?", "status = ?"]
            params = [now, status]
            if tickers_processed is not None:
                updates.append("tickers_processed = ?")
                params.append(tickers_processed)
            if consensus_count is not None:
                updates.append("consensus_count = ?")
                params.append(consensus_count)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            params.append(run_id)
            sql = f"UPDATE forecast_runs SET {', '.join(updates)} WHERE id = ?"
            with self._connect() as con:
                con.execute(sql, params)
            return True
        except Exception as e:
            logger.error(f"Error completing forecast run {run_id}: {e}")
            return False

    def link_forecast_to_run(self, run_id: int, log_id: str, ticker: str, method: str, model: str,
                             signal: str, raw_confidence: float, win_rate: float, ema_accuracy: float,
                             final_weight: float, target_price: float = None, stop_loss: float = None,
                             included_in_consensus: int = 1,
                             calibrated_confidence: float = None, calibration_factor: float = None,
                             entry_price: float = None, r_multiple: float = None, atr_14: float = None) -> bool:
        """Link a forecast log entry to a run with full weight snapshot."""
        try:
            with self._connect() as con:
                con.execute(
                    """INSERT OR REPLACE INTO forecast_run_links
                       (run_id, log_id, ticker, method, model, signal, raw_confidence, calibrated_confidence,
                        calibration_factor, win_rate, ema_accuracy, final_weight, target_price, stop_loss,
                        entry_price, r_multiple, atr_14, included_in_consensus)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (run_id, log_id, ticker, method, model, signal, raw_confidence, calibrated_confidence,
                     calibration_factor, win_rate, ema_accuracy, final_weight, target_price, stop_loss,
                     entry_price, r_multiple, atr_14, included_in_consensus)
                )
            return True
        except Exception as e:
            logger.error(f"Error linking forecast {log_id} to run {run_id}: {e}")
            return False

    def update_log_run_id(self, log_id: str, run_id: int) -> bool:
        """Update the run_id for a specific log entry."""
        try:
            with self._connect() as con:
                con.execute("UPDATE logs SET run_id = ? WHERE id = ?", (run_id, log_id))
            return True
        except Exception as e:
            logger.error(f"Error updating run_id for log {log_id}: {e}")
            return False

    def get_forecast_run(self, run_id: int) -> dict:
        """Get forecast run details with aggregated statistics."""
        try:
            with self._connect() as con:
                con.row_factory = sqlite3.Row
                # Run meta
                run = dict(con.execute(
                    "SELECT * FROM forecast_runs WHERE id = ?", (run_id,)
                ).fetchone() or {})
                if not run:
                    return None
                # Aggregated stats from links
                stats = con.execute(
                    """SELECT 
                        COUNT(*) as total_forecasts,
                        COUNT(CASE WHEN included_in_consensus = 1 THEN 1 END) as included_forecasts,
                        COUNT(DISTINCT ticker) as tickers_count,
                        COUNT(DISTINCT method) as methods_count,
                        COUNT(DISTINCT model) as models_count,
                        AVG(final_weight) as avg_weight,
                        MAX(final_weight) as max_weight
                       FROM forecast_run_links WHERE run_id = ?""",
                    (run_id,)
                ).fetchone()
                run.update({k: stats[k] for k in stats.keys()})
                return run
        except Exception as e:
            logger.error(f"Error fetching forecast run {run_id}: {e}")
            return None

    def get_forecast_run_links(self, run_id: int, ticker: str = None) -> pd.DataFrame:
        """Get all forecast links for a run, optionally filtered by ticker."""
        try:
            sql = "SELECT * FROM forecast_run_links WHERE run_id = ?"
            params = [run_id]
            if ticker:
                sql += " AND ticker = ?"
                params.append(ticker)
            sql += " ORDER BY final_weight DESC"
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=params)
        except Exception as e:
            logger.error(f"Error fetching forecast run links for run {run_id}: {e}")
            return pd.DataFrame()

    def get_forecast_runs(self, limit: int = 50) -> pd.DataFrame:
        """Get list of forecast runs with aggregated stats."""
        try:
            sql = """SELECT 
                        r.*,
                        COUNT(l.id) as total_forecasts,
                        COUNT(CASE WHEN l.included_in_consensus = 1 THEN 1 END) as included_forecasts,
                        COUNT(DISTINCT l.ticker) as tickers_with_forecasts
                     FROM forecast_runs r
                     LEFT JOIN forecast_run_links l ON r.id = l.run_id
                     GROUP BY r.id
                     ORDER BY r.started_at DESC
                     LIMIT ?"""
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=[limit])
        except Exception as e:
            logger.error(f"Error fetching forecast runs: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Price / Indicator queries
    # ------------------------------------------------------------------

    def get_price_data(self, ticker: str = None, date_from: str = None,
                       date_to: str = None, limit: int = 500) -> pd.DataFrame:
        try:
            where = []
            params = []
            if ticker:
                where.append("ticker = ?"); params.append(ticker)
            if date_from:
                where.append("date >= ?"); params.append(date_from)
            if date_to:
                where.append("date <= ?"); params.append(date_to)
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            sql = f"SELECT * FROM price_data {clause} ORDER BY ticker, date DESC LIMIT {limit}"
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=params)
        except Exception as e:
            logger.error(f"Error reading price_data: {e}")
            return pd.DataFrame()

    def get_indicators(
        self, ticker: str = None, limit: int = 200, date_from: str = None, date_to: str = None
    ) -> pd.DataFrame:
        try:
            where = []
            params = []
            if ticker:
                where.append("ticker = ?")
                params.append(ticker)
            if date_from:
                where.append("date >= ?")
                params.append(date_from)
            if date_to:
                where.append("date <= ?")
                params.append(date_to)
            clause = ("WHERE " + " AND ".join(where)) if where else ""
            sql = f"SELECT * FROM indicators {clause} ORDER BY ticker, date DESC LIMIT {limit}"
            with self._connect() as con:
                return pd.read_sql_query(sql, con, params=params)
        except Exception as e:
            logger.error(f"Error reading indicators: {e}")
            return pd.DataFrame()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _py_val(v):
    """Convert numpy/pandas types to plain Python for SQLite."""
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
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
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v
