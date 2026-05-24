"""Pydantic models shared between server and client."""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ForecastLog(BaseModel):
    """One row from the Logs table."""
    id: Optional[str] = None
    forecast_date: Optional[str] = None
    created_at: Optional[str] = None
    ticker: Optional[str] = None
    method: Optional[str] = None
    confidence: Optional[Any] = None
    side: Optional[str] = None
    entry_price: Optional[Any] = None
    entry_conditions: Optional[str] = None
    exit_target: Optional[str] = None
    exit_stop: Optional[str] = None
    position_size: Optional[str] = None
    rationale: Optional[str] = None
    forecast_prompt: Optional[str] = None
    prompt_response: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    horizon_days: Optional[int] = None
    actual_date: Optional[str] = None
    actual_open: Optional[Any] = None
    actual_close: Optional[Any] = None
    actual_high: Optional[Any] = None
    actual_low: Optional[Any] = None
    entry_triggered: Optional[Any] = None
    target_hit: Optional[Any] = None
    stop_hit: Optional[Any] = None
    pnl_pct: Optional[Any] = None
    direction_correct: Optional[Any] = None
    exit_successful: Optional[Any] = None

    class Config:
        populate_by_name = True


class TickerSetting(BaseModel):
    """One row from the Settings sheet."""
    ticker: str
    active: int = 0
    comment: Optional[str] = ""

    class Config:
        populate_by_name = True


class ProviderSetting(BaseModel):
    """One row from the Providers sheet."""
    provider: Optional[str] = None
    name: Optional[str] = None
    api_key: Optional[str] = None
    api: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[Any] = None
    max_tokens: Optional[Any] = None
    rate_limit: Optional[Any] = None
    active: Optional[Any] = None
    execute: Optional[str] = "yes"  # 'yes' or 'no' - allow orders from this provider

    def get_name(self) -> str:
        return self.name or self.provider or ""

    def get_api_key(self) -> str:
        return self.api_key or self.api or ""

    class Config:
        populate_by_name = True


class LogsResponse(BaseModel):
    """Response for GET /logs."""
    items: List[ForecastLog]
    total: int


class TickersResponse(BaseModel):
    """Response for GET /tickers."""
    items: List[TickerSetting]


class ProvidersResponse(BaseModel):
    """Response for GET /providers."""
    items: List[ProviderSetting]


class TickerUpdate(BaseModel):
    """Body for PUT /tickers/{ticker}."""
    active: int
    comment: Optional[str] = ""


class ProviderUpdate(BaseModel):
    """Body for PUT /providers/{name}."""
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    rate_limit: Optional[int] = None
    active: Optional[int] = None


class TickerCreate(BaseModel):
    """Body for POST /tickers."""
    ticker: str
    active: int = 1
    comment: Optional[str] = ""


class RunResponse(BaseModel):
    """Response for POST /run/* and GET /run/status."""
    status: str
    message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_sec: Optional[float] = None
    log_lines: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str = "ok"
    version: str = "1.0.0"
    db_file: Optional[str] = None
    db_exists: bool = False
    server: Optional[str] = None
    excel_file: Optional[str] = None
    excel_exists: bool = False


# ---------------------------------------------------------------------------
# New models for SQLite-backed endpoints
# ---------------------------------------------------------------------------

class ConfigParam(BaseModel):
    """One row from the config table."""
    key: str
    value: str = ""
    description: Optional[str] = ""


class ConfigResponse(BaseModel):
    items: List[ConfigParam]


class PromptRecord(BaseModel):
    """One row from the prompts table."""
    id: Optional[int] = None
    date: Optional[str] = None
    ticker: Optional[str] = None
    method: Optional[str] = None
    prompt_text: Optional[str] = None


class PromptsResponse(BaseModel):
    items: List[PromptRecord]
    total: int


class PriceRecord(BaseModel):
    """One row from the price_data table."""
    id: Optional[int] = None
    ticker: Optional[str] = None
    date: Optional[str] = None
    open: Optional[Any] = None
    high: Optional[Any] = None
    low: Optional[Any] = None
    close: Optional[Any] = None
    volume: Optional[Any] = None


class PriceDataResponse(BaseModel):
    items: List[PriceRecord]
    total: int


class IndicatorRecord(BaseModel):
    """One row from the indicators table."""
    id: Optional[int] = None
    ticker: Optional[str] = None
    date: Optional[str] = None
    price: Optional[Any] = None
    ma20: Optional[Any] = None
    ma50: Optional[Any] = None
    ma200: Optional[Any] = None
    ema9: Optional[Any] = None
    ema21: Optional[Any] = None
    rsi14: Optional[Any] = None
    stoch_rsi: Optional[Any] = None
    atr14: Optional[Any] = None
    adx14: Optional[Any] = None
    macd: Optional[Any] = None
    macd_signal: Optional[Any] = None
    macd_hist: Optional[Any] = None
    bb_upper: Optional[Any] = None
    bb_lower: Optional[Any] = None
    bb_middle: Optional[Any] = None
    obv: Optional[Any] = None
    change_5d: Optional[Any] = None
    change_10d: Optional[Any] = None
    change_20d: Optional[Any] = None
    change_50d: Optional[Any] = None
    volume_avg_20: Optional[Any] = None
    volume_current: Optional[Any] = None
    market_regime: Optional[str] = None


class IndicatorsResponse(BaseModel):
    items: List[IndicatorRecord]
    total: int


class ConsensusRecord(BaseModel):
    """One row from the consensus table."""
    id: Optional[int] = None
    date: Optional[str] = None
    ticker: Optional[str] = None
    signal: Optional[str] = None
    confidence: Optional[Any] = None
    methods_long: Optional[str] = None
    methods_short: Optional[str] = None
    methods_neutral: Optional[str] = None
    rationale: Optional[str] = None
    target_price: Optional[Any] = None
    stop_loss: Optional[Any] = None
    entry_limit_price: Optional[Any] = None
    high_model_disagreement: Optional[bool] = None
    # Evaluation fields
    horizon_hours: Optional[int] = None
    eval_target_date: Optional[str] = None
    eval_status: Optional[str] = None
    actual_date: Optional[str] = None
    actual_open: Optional[Any] = None
    actual_close: Optional[Any] = None
    actual_high: Optional[Any] = None
    actual_low: Optional[Any] = None
    entry_price_actual: Optional[Any] = None
    target_hit: Optional[Any] = None
    stop_hit: Optional[Any] = None
    direction_correct: Optional[Any] = None
    pnl_pct: Optional[Any] = None
    r_multiple: Optional[Any] = None
    first_hit: Optional[str] = None
    # Order activation fields
    order_state: Optional[str] = None
    order_checked_at: Optional[str] = None
    order_attempted_at: Optional[str] = None
    order_reason: Optional[str] = None
    trade_id: Optional[int] = None


class ConsensusResponse(BaseModel):
    items: List[ConsensusRecord]
    total: int


class AccountRecord(BaseModel):
    """One Bybit account/profile row."""
    id: Optional[int] = None
    profile: Optional[str] = None          # secrets.ini section name, e.g. 'demo', 'live'
    mode: Optional[str] = None             # 'Demo' or 'Live'
    uid: Optional[str] = None              # Bybit UID from get_account_info()
    account_type: Optional[str] = None     # 'UNIFIED'
    net_liquidation: Optional[Any] = None  # Equity USDT
    available_funds: Optional[Any] = None  # Available USDT (availableToWithdraw)
    unrealized_pnl: Optional[Any] = None   # Sum of unrealised PnL across positions
    positions_count: Optional[int] = None  # Number of open positions
    active: Optional[bool] = None          # True if this is the BYBIT_ACTIVE_PROFILE
    connected: Optional[bool] = None       # True if api_key+secret configured
    last_update: Optional[str] = None      # ISO timestamp of last sync
    # Legacy fields kept for DB compatibility
    broker: Optional[str] = None
    account_id: Optional[str] = None
    name: Optional[str] = None
    base_currency: Optional[str] = None
    buying_power: Optional[Any] = None
    cash: Optional[Any] = None
    maintenance_margin: Optional[Any] = None
    type: Optional[str] = None


class AccountsResponse(BaseModel):
    items: List[AccountRecord]
    total: int


class PositionRecord(BaseModel):
    """One row from the portfolio table."""
    id: Optional[int] = None
    ticker: Optional[str] = None
    account: Optional[str] = None
    account_id: Optional[int] = None
    broker: Optional[str] = None
    quantity: Optional[Any] = None
    avg_cost: Optional[Any] = None
    market_price: Optional[Any] = None
    market_value: Optional[Any] = None
    unrealized_pnl: Optional[Any] = None
    realized_pnl: Optional[Any] = None
    currency: Optional[str] = None
    asset_type: Optional[str] = None
    sector: Optional[str] = None
    last_update: Optional[str] = None
    con_id: Optional[int] = None
    type: Optional[str] = None  # 'paper' or 'live'


class PortfolioResponse(BaseModel):
    items: List[PositionRecord]
    total: int


class IBConfigRecord(BaseModel):
    """IB Gateway connection settings."""
    id: Optional[int] = None
    name: str = "default"
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    type: str = "paper"  # 'paper' or 'live'
    active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IBConfigResponse(BaseModel):
    items: List[IBConfigRecord]
    total: int


class SystemLogResponse(BaseModel):
    lines: List[str]
    total: int


class OrderSubmitRequest(BaseModel):
    """Manual order submission request."""
    ticker: str
    entry_limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    quantity: Optional[int] = None


class OrderSubmitResponse(BaseModel):
    """Manual order submission response."""
    status: str
    order_ids: List[int]
    message: str
    consensus_signal: str
    confidence: float


# Forecast Run tracking models
class ForecastRunLink(BaseModel):
    """Single forecast link with weight snapshot."""
    id: int
    run_id: int
    log_id: str
    ticker: str
    method: str
    model: str
    signal: str
    raw_confidence: float
    win_rate: float
    ema_accuracy: float
    final_weight: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    included_in_consensus: int = 1


class ForecastRunRecord(BaseModel):
    """Single forecast run with aggregated stats."""
    id: int
    started_at: str
    completed_at: Optional[str] = None
    trigger_type: str
    tickers_planned: int
    tickers_processed: int
    consensus_count: int
    status: str
    error_message: Optional[str] = None
    # Aggregated stats
    total_forecasts: Optional[int] = None
    included_forecasts: Optional[int] = None
    tickers_with_forecasts: Optional[int] = None


class ForecastRunsResponse(BaseModel):
    """Response for GET /forecast-runs."""
    items: List[ForecastRunRecord]
    total: int


class ForecastRunDetailResponse(BaseModel):
    """Response for GET /forecast-runs/{id}."""
    run: ForecastRunRecord
    links: List[ForecastRunLink]
    consensus: Optional[List[ConsensusRecord]] = None
