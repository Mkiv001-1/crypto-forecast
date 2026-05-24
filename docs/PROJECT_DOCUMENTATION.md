# Trading Robot — Project Documentation

**Version:** 1.0  
**Date:** 2026-05-15  
**Status:** Consolidated technical documentation  

> **Rule of truth:** Code is primary. If documentation contradicts code — code wins; update docs.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Core Modules](#3-core-modules)
4. [Data Flow & Workflow](#4-data-flow--workflow)
5. [SQLite Schema](#5-sqlite-schema)
6. [Scheduler & Background Tasks](#6-scheduler--background-tasks)
7. [Forecast Pipeline](#7-forecast-pipeline)
8. [Consensus Logic](#8-consensus-logic)
9. [Orders, Trades & Risk Management](#9-orders-trades--risk-management)
10. [Bybit Integration](#10-bybit-integration)
11. [REST API](#11-rest-api)
12. [GUI](#12-gui)
13. [Configuration & Deployment](#13-configuration--deployment)
14. [Testing](#14-testing)
15. [Operations & Troubleshooting](#15-operations--troubleshooting)
16. [Known Limitations & Technical Debt](#16-known-limitations--technical-debt)
17. [Documentation Map](#17-documentation-map)

---

## 1. Purpose

Trading robot generating forecasts using AI models via OpenRouter, with execution through Bybit (linear perpetuals).

### Core Scenario

1. Load active symbols from `settings`
2. Fetch market data (Bybit API primary, yfinance fallback)
3. Calculate technical indicators
4. Detect market regime (ADX + MA alignment)
5. Generate forecasts: N AI models × M analysis methods
6. Aggregate into consensus with weighted confidence
7. Calculate position size from Bybit USDT wallet balance
8. Submit orders (Limit/Market with TP/SL) to Bybit
9. Evaluate results post-factum (3h+ horizon)
10. Update model weights via EMA accuracy tracking

### Key Subsystems

| Subsystem | Responsibility |
|-----------|---------------|
| **Client** | PyQt6 GUI for monitoring and manual control |
| **Server** | FastAPI REST API + background scheduler |
| **Core** | Business logic: forecasting, consensus, orders, risk |
| **SQLite** | Single source of truth for all data |
| **Bybit API** | Live broker integration (positions, balances, execution via pybit) |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Client (PyQt6 GUI)                                         │
│  ├── gui_main.py — main window + tabs                     │
│  ├── api_client.py — HTTP client                          │
│  └── config.py — client_config.ini parser                  │
│                      │                                      │
│                      ▼ HTTP/REST                           │
├─────────────────────────────────────────────────────────────┤
│  Server (FastAPI, port 8000)                                │
│  ├── main.py — uvicorn entry point                          │
│  ├── api.py — REST endpoints                                │
│  ├── robot.py — background runner wrapper                   │
│  └── config.py — server_config.ini parser                   │
│                      │                                      │
│                      ▼                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Core (scripts/core/)                                 │   │
│  │ ├── forecast_runner.py — orchestrator               │   │
│  │ ├── scheduler.py — centralized scheduler            │   │
│  │ ├── sqlite_manager.py — SQLite ORM wrapper          │   │
│  │ ├── multi_model_forecaster.py — N×M forecasts       │   │
│  │ ├── forecast_engine.py — AI prompts → OpenRouter    │   │
│  │ ├── consensus.py — weighted aggregation             │   │
│  │ ├── consensus_evaluator.py — post-factum evaluation │   │
│  │ ├── market_regime.py — ADX + MA regime detection    │   │
│  │ ├── indicators.py — technical indicators            │   │
│  │ ├── data_loader.py — yfinance fallback               │   │
│  │ ├── bybit_data_loader.py — Bybit historical data    │   │
│  │ ├── actuals_evaluator.py — PnL calculation          │   │
│  │ ├── bybit_capital_provider.py — Bybit capital source│   │
│  │ ├── position_sizer.py — risk-based sizing           │   │
│  │ ├── bybit_order_manager.py — Bybit orders (TP/SL)  │   │
│  │ ├── bybit_client.py — Bybit REST API client         │   │
│  │ ├── bybit_ws_client.py — Bybit WebSocket client     │   │
│  │ ├── bybit_worker.py — serialized queue worker       │   │
│  │ ├── bybit_order_status_sync.py — order sync         │   │
│  │ ├── bybit_account_sync.py — account/position sync   │   │
│  │ ├── bybit_config.py — Bybit configuration           │   │
│  │ ├── circuit_breaker.py — OpenRouter fault protection│   │
│  │ ├── model_performance_tracker.py — EMA weights       │   │
│  │ ├── ai_client.py — OpenRouter HTTP client           │   │
│  │ ├── providers_manager.py — AI provider management   │   │
│  │ ├── prompt_manager.py — prompt template management  │   │
│  │ ├── notification_manager.py — alerts              │   │
│  │ ├── single_instance.py — PID-based singleton        │   │
│  │ ├── migrate.py — schema migrations                  │   │
│  │ └── bybit_migrate.py — Bybit schema migrations      │   │
│  └─────────────────────────────────────────────────────┘   │
│                      │                                      │
│                      ▼                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Shared (scripts/shared/)                              │   │
│  │ └── models.py — Pydantic API models                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                      │                                      │
│                      ▼                                      │
│  trading_robot.db — SQLite (single storage)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Core Modules

### 3.1 Server (`scripts/server/`)

| File | Purpose |
|------|---------|
| `main.py` | Uvicorn entry point, FastAPI app initialization |
| `api.py` | REST endpoints (see [REST API](#11-rest-api)) |
| `robot.py` | Thread wrapper for background forecast execution |
| `config.py` | `server_config.ini` parser |

### 3.2 Client (`scripts/client/`)

| File | Purpose |
|------|---------|
| `main.py` | QApplication entry point |
| `gui_main.py` | Main window, tab management (Consensus, Trading, Bybit, Settings) |
| `api_client.py` | HTTP client for API calls |
| `config.py` | `client_config.ini` parser |

### 3.3 Core Business Logic (`scripts/core/`)

| File | Purpose |
|------|---------|
| `forecast_runner.py` | Main orchestrator: loads symbols → data → indicators → regime → forecasts → consensus → orders |
| `scheduler.py` | Centralized task scheduler with background tasks + heartbeat |
| `sqlite_manager.py` | SQLite ORM wrapper with WAL mode, schema creation, migrations |
| `multi_model_forecaster.py` | Parallel execution of N models × M methods |
| `forecast_engine.py` | Prompt building, OpenRouter calls, R/R validation, response parsing |
| `consensus.py` | Weighted aggregation: raw_confidence × win_rate × ema_accuracy |
| `consensus_evaluator.py` | Post-factum evaluation of consensus predictions |
| `consensus_recalc.py` | Retrospective recalculation with new weights |
| `market_regime.py` | ADX + MA alignment → STRONG_UPTREND/DOWNTREND/WEAK_TREND/RANGING |
| `market_context.py` | Crypto market context (BTC/ETH moves, funding via Bybit public API) |
| `indicators.py` | Technical indicators: MA, RSI, MACD, BB, ATR, ADX, OBV, Stoch RSI |
| `data_loader.py` | yfinance fallback data fetching |
| `bybit_data_loader.py` | Bybit API historical data fetching |
| `smart_data_loader.py` | Intelligent source selection with fallback |
| `actuals_evaluator.py` | Post-factum PnL calculation with stop priority |
| `bybit_capital_provider.py` | Bybit capital source: USDT wallet balance |
| `position_sizer.py` | Risk-based position calculation from capital and stop distance |
| `bybit_order_manager.py` | Bybit orders: Limit/Market with attached TP/SL |
| `bybit_client.py` | Bybit REST API client (pybit) |
| `bybit_ws_client.py` | Bybit WebSocket client for real-time data |
| `bybit_worker.py` | Serialized queue worker for Bybit operations |
| `bybit_order_status_sync.py` | Synchronize order statuses with Bybit API |
| `bybit_account_sync.py` | Synchronize accounts and positions with Bybit |
| `bybit_config.py` | Bybit configuration and secrets management |
| `circuit_breaker.py` | OpenRouter fault protection with automatic recovery |
| `model_performance_tracker.py` | EMA-based model weight calculation (α=0.2) |
| `ai_client.py` | OpenRouter HTTP client with retry logic |
| `providers_manager.py` | AI provider CRUD with `execute` flag |
| `prompt_manager.py` | Prompt template management in SQLite |
| `notification_manager.py` | Alerts for `MANUAL_INTERVENTION_REQUIRED` |
| `single_instance.py` | PID file-based process singleton |
| `migrate.py` | Schema migrations for new columns/tables |
| `bybit_migrate.py` | Bybit-specific schema migrations |
| `config.py` | Legacy constants (fallback only) |

### 3.4 Shared (`scripts/shared/`)

| File | Purpose |
|------|---------|
| `models.py` | Pydantic models for API request/response validation |

---

## 4. Data Flow & Workflow

### 4.1 Main Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  1. TICKER LOADING                                               │
│     SELECT * FROM settings WHERE active=1                        │
├─────────────────────────────────────────────────────────────────┤
│  2. DATA FETCHING                                                │
│     Bybit API → price_data (90+ days); yfinance fallback          │
├─────────────────────────────────────────────────────────────────┤
│  3. INDICATOR CALCULATION                                        │
│     MA, RSI, MACD, BB, ATR, ADX, OBV, Stoch RSI → indicators    │
├─────────────────────────────────────────────────────────────────┤
│  4. MARKET REGIME DETECTION                                      │
│     ADX > 25 + MA alignment → STRONG_UPTREND/DOWNTREND/...      │
├─────────────────────────────────────────────────────────────────┤
│  5. FORECAST GENERATION (N models × M methods)                   │
│     For each active provider:                                  │
│       For each active method:                                  │
│         Build prompt from template                              │
│         Call OpenRouter                                         │
│         Parse JSON (action, target, stop, confidence)           │
│         R/R validation (min 1.5)                                  │
│         Save to logs with run_id                                │
├─────────────────────────────────────────────────────────────────┤
│  6. CONSENSUS AGGREGATION                                        │
│     Group by ticker → Filter anomalies (>15%)                   │
│     Calibrate confidence: raw × (ema_acc / 0.5)                 │
│     Calculate weight: calibrated × win_rate × ema_acc            │
│     Expected value filter (< 0.5 → NEUTRAL)                      │
│     Median target/stop of dominant direction                    │
│     Save to consensus                                           │
├─────────────────────────────────────────────────────────────────┤
│  7. POSITION SIZING                                              │
│     USDT wallet balance from Bybit accounts                       │
│     Risk % from config; leverage from settings                    │
│     Position = Risk$ / (Entry - Stop) × Leverage                  │
├─────────────────────────────────────────────────────────────────┤
│  8. ORDER SUBMISSION (optional)                                  │
│     Limit/Market order with attached TP/SL via Bybit API        │
│     Validate spread, slippage, max open positions               │
│     Submit via bybit_worker (serialized queue)                    │
│     Track in orders table                                       │
├─────────────────────────────────────────────────────────────────┤
│  9. EVALUATION (after horizon_hours)                             │
│     Check price_data at eval_target_date                       │
│     target_hit? stop_hit? (stop has priority)                   │
│     Calculate pnl_pct, r_multiple, direction_correct          │
│     Update consensus evaluation fields                           │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Analysis Methods (6 Methods)

| Method | Description | Key Indicators | Horizon | Trigger |
|--------|-------------|----------------|---------|---------|
| `momentum_trend` | Trend and momentum | MA20/50/200, EMA9/21, ADX, MACD, RSI, OBV | 24h | `both` |
| `price_action` | Position in BB | BB upper/lower, Stoch RSI, 5d/20d dynamics | 8h | `price_level` |
| `relative_strength` | Relative strength vs BTC/ETH benchmark | RSI, ADX, 5/10/20/50d dynamics, volume coef | 48h | `time` |
| `volatility` | Volatility breakout | ATR, BB width, RSI, ADX | 4h | `price_level` |
| `mean_reversion` | Mean reversion | Deviation from MA20/50, RSI, Stoch RSI | 72h | `price_level` |
| `volume_breakout` | Volume impulse | Volume vs average, OBV trend, ATR, ADX | 2h | `price_level` |

---

## 5. SQLite Schema

### 5.1 Core Tables

| Table | Purpose |
|-------|---------|
| `settings` | Tickers (ticker, active, comment, sector, trading_blocked) |
| `price_data` | Historical daily OHLCV (250 days) |
| `price_data_intraday` | Hourly bars (ticker, datetime, interval, OHLCV) |
| `indicators` | Calculated technical indicators |
| `logs` | All forecasts + evaluations (status NEW/EVALUATED, bracket fields, run_id) |
| `consensus` | Aggregated consensus forecasts + evaluation fields |
| `config` | Configuration parameters (API keys, settings) |
| `providers` | AI provider settings (ema_accuracy, ema_updated_at, execute) |
| `method_config` | Method parameters (timeframe_hours, trigger, active, execute) |
| `prompts` | Saved prompts |
| `prompt_templates` | Method-specific prompt templates |
| `model_catalog` | OpenRouter model catalog |
| `scheduled_tasks` | Scheduler task registry |
| `heartbeat_log` | Health check records |

### 5.2 Bybit Integration Tables

| Table | Purpose |
|-------|---------|
| `accounts` | Bybit accounts (broker, account_id, wallet_balance, available_balance, margin_balance, type: demo/live) |
| `portfolio` | Bybit positions (ticker, quantity, avg_cost, market_value, unrealized_pnl, leverage, symbol) |
| `bybit_order_transactions` | Bot audit log (order status changes, portfolio snapshots) |
| `bybit_uta_transaction_log` | Bybit UTA exchange transaction log (synced via `/v5/account/transaction-log`) |
| `bybit_gateway_log` | Bybit API operation log |

### 5.3 Orders & Trades Tables

| Table | Purpose |
|-------|---------|
| `orders` | Orders (bybit_order_id, symbol, side, qty, price, tp/sl; statuses, execution_latency_ms) |
| `trades` | Closed trades (ticker, signal, entry/exit, realized_pnl, r_multiple, status) |
| `tickets` | Tickets/tasks (ticker, action, quantity, price, status) |

### 5.4 Audit Tables

| Table | Purpose |
|-------|---------|
| `forecast_runs` | Forecast run audit |
| `forecast_run_links` | Forecast-weight links (raw_confidence, win_rate, ema_accuracy, final_weight) |

### 5.5 Schema Notes

- **Migrations:** New columns added via `migrate.py`, not base schema
- **Foreign Keys:** `logs.run_id` → `forecast_runs.id`, `consensus.trade_id` → `trades.id`
- **WAL Mode:** Enabled in `sqlite_manager.py` for concurrent access
- **Missing Columns:** Added via `_migrate_schema()` in `sqlite_manager.py`

---

## 6. Scheduler & Background Tasks

Scheduler (`scheduler.py`) manages 14 periodic tasks:

| Task | Interval | Description |
|------|----------|-------------|
| `heartbeat` | 30s | Health check, SQLite validation |
| `expire_queued_orders` | 300s | Expire QUEUED orders past `ORDER_QUEUE_MAX_AGE_HOURS` |
| `expire_filled_orders` | 86400s | Archive old `FILLED_ENTRY` orders |
| `expire_stuck_submitted` | 3600s | Mark stale `SUBMITTED` orders as `STALE` |
| `process_pending_orders` | 60s | Process PENDING orders |
| `sync_order_statuses` | 60s | Sync order statuses with Bybit |
| `portfolio_sync` | 300s | Sync portfolio positions from Bybit |
| `portfolio_history_snapshot` | 1440m | Save portfolio/account snapshots |
| `update_price_data` | 60m | Fetch daily price data |
| `update_intraday` | 60m | Fetch hourly bars |
| `scheduled_forecast` | 240m | Run forecast pipeline |
| `scheduled_evaluate` | 120m | Evaluate past forecasts |
| `consensus_evaluate` | 120m | Evaluate consensus predictions |
| `logs_evaluate` | 120m | Evaluate logs records |

### Scheduler Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `SCHEDULER_MAX_WORKERS` | 4 | Thread pool size |
| `SCHEDULER_MAX_RETRIES` | 2 | Max retries per task |
| `FORECAST_INTERVAL_MINUTES` | 240 | Forecast interval |
| `EVALUATE_INTERVAL_MINUTES` | 120 | Evaluation interval |

---

## 7. Forecast Pipeline

Per-ticker processing is delegated to `scripts/core/pipeline/stages.py` via thin `forecast_runner.process_ticker()`.

### 7.0 Pipeline Stages (default order)

| Stage | Module | Purpose |
|-------|--------|---------|
| `FetchDataStage` | `bybit_data_loader` | Load 250d OHLCV, staleness check |
| `IndicatorStage` | `indicators` | Technical indicators |
| `RegimeStage` | `market_regime` | Regime + active methods |
| `TradingExposureGuardStage` | `trading_exposure` | Skip LLM if open order/position (`SKIP_FORECAST_WHEN_EXPOSED`) |
| `ForecastStage` | `multi_model_forecaster` | LLM forecasts → `logs` |
| `ConsensusStage` | `consensus` | Weighted aggregation → `consensus` |
| `MetaLabelStage` | `meta_label.stage` | ML gate before orders (optional, `META_LABEL_ENABLED`) |
| `OrderActivationStage` | `bybit_order_manager` | Auto submit if `AUTO_ORDER_SUBMISSION` |

See also: [META_LABELING.md](META_LABELING.md).

### 7.1 Multi-Model Execution

```python
# multi_model_forecaster.py
for provider in active_providers:
    for method in active_methods:
        if provider.execute == 'yes' and method.execute == 'yes':
            task = asyncio.create_task(
                forecast_engine.generate(provider, method, ticker)
            )
```

### 7.2 Forecast Engine Flow

1. **Build Prompt:** Template from `prompt_templates` + method-specific indicators
2. **Call OpenRouter:** HTTP POST with timeout and retry (3 attempts)
3. **Parse Response:** Extract `action`, `target_price`, `stop_loss`, `confidence`, `reasoning`, `tif`
4. **R/R Validation:** `(target - price) / (price - stop) >= 1.5`
5. **Save:** Insert into `logs` with `run_id`, status `NEW`

### 7.3 Forecast Run Tracking

- Each run gets unique `run_id` in `forecast_runs`
- All forecasts linked via `forecast_run_links` with weight snapshot
- Enables post-factum analysis: which models/methods performed best

---

## 8. Consensus Logic

### 8.1 Weight Formula

```
ema_weight = max(0.3, min(1.5, ema_accuracy × 2))
calibration_factor = ema_accuracy / 0.5  # for analytics only
calibrated_confidence = raw_confidence × calibration_factor
final_weight = calibrated_confidence × win_rate × ema_weight
```

### 8.2 Aggregation Steps

1. **Filter Anomalies:** `|target - price| / price > 15%` → discard
2. **Filter Low Confidence:** `expected_r = (confidence/100) × (R/R) < 0.5` → NEUTRAL
3. **Check Disagreement:** If minority direction has >40% weight → `high_model_disagreement=true` → NEUTRAL
4. **Calculate Medians:** Target and stop of dominant direction
5. **Save:** Insert into `consensus` with `horizon_hours`, `eval_target_date`

### 8.3 Evaluation

After `horizon_hours`:
- Load `price_data` at `eval_target_date`
- Check `target_hit`: High >= target (LONG) or Low <= target (SHORT)
- Check `stop_hit`: Low <= stop (LONG) or High >= stop (SHORT)
- **Stop Priority:** If both hit same day → stop wins (conservative)
- Calculate: `pnl_pct` (gross), `net_pnl_pct` (after fees/funding), `label_meta`, `r_multiple`, `direction_correct`
- Update `consensus` evaluation fields

---

## 9. Orders, Trades & Risk Management

### 9.1 Capital Source

**Single source of truth:** USDT `wallet_balance` from Bybit accounts table.

- `MANUAL_CAPITAL_OVERRIDE` — optional manual override
- `PREFERRED_ACCOUNT_TYPE` — `live` or `paper`
- `CAPITAL_STALENESS_MINUTES` — 15 minutes default

### 9.2 Position Sizing

```
risk_dollars = capital × RISK_PERCENT_ON_STOP / 100
stop_distance = |entry - stop|
position_qty = (risk_dollars / stop_distance) × leverage
position_value = position_qty × entry
max_position_value = capital × MAX_POSITION_PCT
final_qty = min(position_qty, max_position_value / entry)
```

### 9.3 Bybit Orders

**Order type:** Limit or Market with attached TP/SL

| Component | Type | TIF | Description |
|-----------|------|-----|-------------|
| Entry | Limit/Market | GTC/IOC/FOK | Primary entry order |
| Take Profit | Limit | GTC | Profit target (attached) |
| Stop Loss | Market/Limit | GTC | Loss limit (attached) |

**Safety Rules:**
- `LIVE_TRADING_CONFIRMED` must be `true` for live orders
- `ORDER_MODE`: `disabled` → no orders, `paper` → demo trading, `live` → live trading
- `MAX_SPREAD_PCT` — slippage guard
- `MAX_OPEN_POSITIONS` — limit concurrent positions
- `ENTRY_SLIPPAGE_TOLERANCE` — entry price deviation guard
- Crypto trades 24/7 — no market hours restriction

### 9.4 Order Lifecycle

```
QUEUED(local) → SUBMITTED → PARTIALLY_FILLED/FILLED_ENTRY
                    ↓
                CANCELLED/ERROR
```

**Race Condition Protection:**
- Lock on consensus ID during submission
- `expire_queued_orders` task cleans stale QUEUED orders
- Serialized via `bybit_worker` queue

### 9.5 Trade Lifecycle

- Created when entry order fills
- Tracks entry/exit prices, realized_pnl, r_multiple
- `trade_uid` for test identification

---

## 10. Bybit Integration

### 10.1 Connection

- **Bybit REST API** (`api.bybit.com`) via `pybit`
- **Bybit WebSocket** for real-time data
- **Demo/Live:** Controlled by `BYBIT_DEMO` config flag

### 10.2 Key Modules

| Module | Description |
|----------|-------------|
| `bybit_client.py` | REST API client: market data, orders, account info |
| `bybit_ws_client.py` | WebSocket client: real-time tickers, orders, positions |
| `bybit_worker.py` | Serialized queue worker for thread-safe order submission |
| `bybit_order_manager.py` | Order lifecycle: create, cancel, track TP/SL |
| `bybit_order_status_sync.py` | Sync local order statuses with Bybit API |
| `bybit_account_sync.py` | Sync accounts, balances, positions with Bybit |
| `bybit_capital_provider.py` | Get USDT wallet balance for position sizing |
| `bybit_config.py` | Configuration, profile management, secrets.ini handling |

### 10.3 Data Flow

```
Bybit API (api.bybit.com)
    ↓ pybit / websockets
bybit_client.py / bybit_ws_client.py
    ↓
bybit_worker.py (serialized queue)
    ↓
bybit_order_manager.py
    ↓
orders / portfolio / accounts tables (SQLite)
    ↓
bybit_capital_provider.py → position_sizer.py
```

### 10.4 Bybit environments

| Mode | Site | API | Used |
|------|------|-----|------|
| Demo | bybit.com → Demo Trading | `api-demo.bybit.com` | Yes (default) |
| Live | bybit.com → Live Trading | `api.bybit.com` | Yes |
| Testnet | testnet.bybit.com | `api-testnet.bybit.com` | **Never** |

See [BYBIT_SETUP.md](BYBIT_SETUP.md) for key creation and `BYBIT_DEMO`.

### 10.5 Safety

- Account `type` field: `demo` or `live`
- `BYBIT_DEMO=true` → Demo Trading on bybit.com (not testnet)
- `LIVE_TRADING_CONFIRMED` must be `true` for live orders
- `ORDER_MODE` controls execution: `disabled` / `paper` / `live`
- Heartbeat detects connection degradation within 30 seconds

---

## 11. REST API

**Base URL:** `http://localhost:8000`  
**Authentication:** `X-API-Key` header

### 11.1 Key Endpoint Groups

| Group | Endpoints |
|-------|-----------|
| **System** | `GET /health`, `GET /system-log`, `GET /circuit-breaker/status`, `POST /circuit-breaker/reset` |
| **Run** | `POST /run/forecast`, `POST /run/evaluate`, `POST /run/full`, `GET /run/status` |
| **Data** | `GET /logs`, `GET /indicators`, `GET /price-data`, `GET /consensus` |
| **Consensus Actions** | `POST /consensus/{id}/activate`, `GET /consensus/{id}/preview-trade`, `POST /consensus/recalculate` |
| **Config** | `GET /config`, `PUT /config/{key}` |
| **Tickers** | `GET /tickers`, `POST /tickers`, `PUT /tickers/{ticker}`, `DELETE /tickers/{ticker}` |
| **Providers** | `GET /providers`, `POST /providers`, `PUT /providers/{name}/execute` |
| **Methods** | `GET /method-config`, `PUT /method-config/{method}/execute` |
| **Orders** | `GET /orders`, `POST /orders/submit`, `POST /orders/{id}/cancel`, `POST /orders/sync` |
| **Trades** | `GET /trades` |
| **Capital** | `GET /capital` |
| **Accounts** | `GET /accounts`, `POST /accounts/sync` |
| **Portfolio** | `GET /portfolio`, `POST /portfolio/sync`, `POST /portfolio/history/snapshot`, `GET /portfolio/transaction-log`, `POST /portfolio/transaction-log/sync` |
| **Bybit** | `GET /bybit-credentials`, `PUT /bybit-credentials`, `GET /bybit-log`, `GET /bybit-transactions` |
| **Forecast Runs** | `GET /forecast-runs`, `GET /forecast-runs/{id}` |
| **Scheduler** | `GET /scheduler/status`, `GET /scheduler/tasks`, `PATCH /scheduler/tasks/{name}/active` |
| **Prompts** | `GET /prompt-templates`, `PUT /prompt-templates/{method}`, `POST /prompt-templates/{method}/reset` |

### 11.2 Example Calls

```bash
# Health check
curl http://localhost:8000/health -H "X-API-Key: your-key"

# Run forecast
curl -X POST http://localhost:8000/run/forecast -H "X-API-Key: your-key"

# Get consensus
curl http://localhost:8000/consensus -H "X-API-Key: your-key"

# Update config
curl -X PUT http://localhost:8000/config/ORDER_MODE \
  -H "X-API-Key: your-key" \
  -d '{"key": "ORDER_MODE", "value": "paper"}'
```

---

## 12. GUI

### 12.1 Architecture

PyQt6 client connects to server via HTTP API.

### 12.2 Main Tabs

| Tab | Purpose |
|-----|---------|
| **Consensus** | View consensus forecasts, activate orders |
| **Trading / Orders** | View orders, trades, tickets; manual order submission |
| **Bybit** | Test Bybit connection, sync accounts/portfolio, manage credentials |
| **Settings** | Configure tickers, providers, methods, general settings |
| **Logs** | View forecast logs and evaluations |

### 12.3 Key Features

- **Execute Checkboxes:** Toggle `execute` flag for providers and methods
- **Forced Recalculation:** Button to trigger consensus recalculation
- **Consensus Preview:** Preview trade parameters before activation
- **Unified Activity Window:** Combined view of orders, trades, and tickets

---

## 13. Configuration & Deployment

### 13.1 Requirements

- **Python 3.12**
- **Virtual Environment:** `.venv312` (created with `py -3.12 -m venv .venv312`)
- **Dependencies:** See `requirements_server.txt` and `requirements_client.txt`
- **Bybit Account:** Demo account recommended for testing

### 13.2 Installation

```powershell
# Create virtual environment
py -3.12 -m venv .venv312

# Install server dependencies
.\.venv312\Scripts\python.exe -m pip install -r requirements_server.txt

# Install client dependencies (if separate)
.\.venv312\Scripts\python.exe -m pip install -r requirements_client.txt
```

### 13.3 Configuration Files

**Server** (`scripts/server/ini/server_config.ini`):
```ini
[server]
host = 0.0.0.0
port = 8000

[data]
excel_file = trading_robot.db

[security]
api_key = your-api-key
```

**Client** (`scripts/client/ini/client_config.ini`):
```ini
[server]
url = http://localhost:8000
api_key = your-api-key
```

**Bybit Secrets** (`scripts/server/ini/secrets.ini`) — excluded from git:
```ini
[demo]
api_key = your_bybit_api_key
api_secret = your_bybit_api_secret

[live]
api_key = your_live_api_key
api_secret = your_live_api_secret
```

### 13.4 Key Config Parameters

| Key | Default | Description |
|-----|---------|-------------|
| `OPENROUTER_API_KEY` | `""` | OpenRouter API key |
| `BYBIT_API_KEY` | `""` | Bybit API key (or use secrets.ini) |
| `BYBIT_API_SECRET` | `""` | Bybit API secret (or use secrets.ini) |
| `BYBIT_DEMO` | `true` | `true` = bybit.com Demo (`api-demo`), `false` = live; testnet unused |
| `BYBIT_DEFAULT_LEVERAGE` | `3` | Default leverage (1-100) |
| `ORDER_MODE` | `disabled` | `disabled` / `paper` / `live` |
| `LIVE_TRADING_CONFIRMED` | `false` | Must be `true` for live orders |
| `DEFAULT_RISK_PCT` | 0.01 | Risk per trade (1%) |
| `MAX_POSITION_PCT` | 0.10 | Max position size (10%) |
| `MAX_OPEN_POSITIONS` | 5 | Max concurrent positions |
| `CONSENSUS_MAX_DEVIATION` | 0.15 | Max target deviation (15%) |
| `MODEL_WEIGHT_EMA_ALPHA` | 0.2 | EMA coefficient for model weights |

### 13.5 Running

```powershell
# Start server
run_server.bat
# Or manually:
.\.venv312\Scripts\python.exe scripts\server\main.py

# Start client
run_client.bat
```

---

## 14. Testing

### 14.1 Test Structure

All tests in `scripts/tests/`:

| Test File | Type | Duration |
|-----------|------|----------|
| `test_mock_consensus_orders_gui.py` | Mock | ~2s |
| `test_bybit_*.py` | Bybit integration | Varies |
| `test_integration_*.py` | Integration | Varies |
| `test_api_*.py` | API unit tests | <1s |

### 14.2 Running Tests

```powershell
# Mock tests only (fast feedback)
pytest scripts/tests/test_mock_consensus_orders_gui.py -v

# All tests
pytest scripts/tests/ -v

# Real Bybit connection (requires API key)
python test_bybit.py
```

### 14.3 Test Safety

- `ORDER_MODE = "paper"` — always for tests
- `LIVE_TRADING_CONFIRMED = false` — required
- `BYBIT_DEMO = true` — bybit.com Demo Trading for tests (not testnet)

### 14.4 What's Tested

- Consensus creation and storage
- Order generation from consensus
- Position sizing calculations (with leverage)
- Bybit order structure (TP/SL)
- GUI API integration
- Bybit connectivity (optional real tests)

---

## 15. Operations & Troubleshooting

### 15.1 Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| `database disk image is malformed` | Corrupted SQLite | Rename `trading_robot.db` → `.backup`, restart server (new DB will be created) |
| `.venv312 not found` | Virtual environment missing | `py -3.12 -m venv .venv312` + install requirements |
| `Python was not found` | Python not in PATH | Install Python 3.12, check `py -3.12 --version` |
| Scheduler fails at startup | Malformed DB or missing tables | Check DB integrity, run with `--init` if needed |
| Bybit connection failed | Invalid API key or IP whitelist | Check API keys in secrets.ini, verify IP whitelist in Bybit settings |
| API key mismatch | Wrong key in client | Sync `server_config.ini` and `client_config.ini` |
| Orders stuck in QUEUED(local) | Submit flow interrupted before Bybit ack | Check Bybit worker status, verify ORDER_MODE and gateway logs |
| `Max open positions reached` | Too many open positions | Close some positions or increase `MAX_OPEN_POSITIONS` |
| `Slippage check failed` | Market price too far from signal | Increase `ENTRY_SLIPPAGE_TOLERANCE` or use Market orders |

### 15.2 Database Recovery

```powershell
# Check integrity
.\.venv312\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('trading_robot.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0])"

# If corrupted:
move trading_robot.db trading_robot.db.corrupted.$(Get-Date -Format yyyyMMdd)
# Restart server — new DB will be created with schema
```

### 15.3 PID Files

- `.client.pid` — client process lock
- `.server.pid` — server process lock
- Delete if stale (process crashed without cleanup)

---

## 16. Known Limitations & Technical Debt

### 16.1 Current Limitations

| Issue | Impact | Status |
|-------|--------|--------|
| PAUSED order state incomplete | QUEUED orders don't auto-pause on Bybit disconnect | Known |
| PAUSED resubmit not implemented | Manual resubmit only via API | Known |
| Price check after pause | No validation of stale prices on resubmit | Known |

### 16.2 Technical Debt

| Item | Description | Priority |
|------|-------------|----------|
| **sys.path duplication** | Identical bootstrap blocks in multiple files — needs `bootstrap.py` | Medium |
| **Ad-hoc SQL** | Direct SQL in `forecast_runner.py` and `scheduler.py` — should use `sqlite_manager.py` | Medium |
| **robot.py / forecast_runner.py split** | Thin wrapper — could merge or clarify responsibilities | Low |
| **No DI container** | `SQLiteManager` created ad-hoc — needs `AppContext` | Medium |
| **Type hints** | Most core modules lack typing — impedes refactoring | Medium |

### 16.3 Resolved Debt

| Date | Item | Status |
|------|------|--------|
| 2026-05-06 | Google Sheets (`gspread`) removed | ✅ Done |
| 2026-05-07 | `main_excel.py` removed | ✅ Done |
| 2026-05-07 | Files reorganized (tests in `scripts/tests/`, docs in `docs/`) | ✅ Done |
| 2026-05-24 | Pipeline decomposition (`scripts/core/pipeline/`, thin `process_ticker`) | ✅ Done |
| 2026-05-24 | Meta-labeling (net PnL labels, optional ML gate) | ✅ In progress — see [META_LABELING.md](META_LABELING.md) |

---

## 17. Documentation Map

### 17.1 This Document

`docs/PROJECT_DOCUMENTATION.md` — current consolidated technical documentation.

`docs/META_LABELING.md` — meta-labeling (ML filter, net PnL labels, training).

`docs/NEWS_FADE_PLAN.md` — план модуля news intelligence и fade-the-reaction (не реализован).

### 17.2 Archive (Historical Documents)

Moved to `docs/archives/`:

- `ARCHITECTURE.md` — predecessor architecture doc
- `REFACTOR_PLAN.md` — refactoring plan
- `CHANGELOG.md` — session-by-session changelog
- `README_TEST_SUITE.md` — test suite docs
- `INTEGRATION_TEST_SUITE.md` — integration test guide
- `features/*.md` — 25+ feature specification documents
- Other `TEST_*.md` files

### 17.3 External References

- **Root README:** `README.md` — user-facing overview, installation, API quick reference
- **Code:** `scripts/` — primary source of truth
- **Requirements:** `requirements_server.txt`, `requirements_client.txt`

### 17.4 Documentation Rules

1. **Code is primary** — if docs contradict code, code wins
2. **Living documents** — `PROJECT_DOCUMENTATION.md` updated on significant changes
3. **Feature specs frozen** — feature documents archived after implementation
4. **This doc is technical** — for developers and operators; user guide is root README

---

## Appendix: Quick Reference

### File Locations

```
d:\Git\forecast\
├── README.md                    # User documentation
├── docs/
│   ├── PROJECT_DOCUMENTATION.md # This file
│   ├── archives/                # Historical docs
│   └── README.md                # Doc index (legacy)
├── scripts/
│   ├── core/                    # Business logic
│   ├── server/                  # FastAPI server
│   ├── client/                  # PyQt6 GUI
│   ├── shared/                  # Common models
│   └── tests/                   # Test suite
├── trading_robot.db             # SQLite database
├── requirements_server.txt      # Server dependencies
└── requirements_client.txt      # Client dependencies
```

### Key Commands

```powershell
# Server
run_server.bat
.\.venv312\Scripts\python.exe scripts\server\main.py

# Client
run_client.bat

# Tests
pytest scripts/tests/test_mock_consensus_orders_gui.py -v
pytest scripts/tests/ -v

# API
curl http://localhost:8000/health -H "X-API-Key: key"
curl -X POST http://localhost:8000/run/forecast -H "X-API-Key: key"
```

---

*End of Project Documentation*
