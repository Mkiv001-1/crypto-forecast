"""HTTP client for the Forecast Trading Robot API."""

import logging
from typing import List, Optional
import requests

from scripts.shared.models import (
    ForecastLog, TickerSetting, ProviderSetting,
    LogsResponse, TickersResponse, ProvidersResponse,
    TickerCreate, TickerUpdate, ProviderUpdate,
    RunResponse, HealthResponse,
    ConfigParam, ConfigResponse,
    PromptRecord, PromptsResponse,
    PriceRecord, PriceDataResponse,
    IndicatorRecord, IndicatorsResponse,
    ConsensusRecord, ConsensusResponse,
    PositionRecord, PortfolioResponse,
    AccountRecord, AccountsResponse,
    SystemLogResponse,
)

logger = logging.getLogger(__name__)


class ForecastApiClient:
    """Synchronous HTTP client for the Forecast server."""

    def __init__(self, server_url: str, api_key: str, timeout: int = 8):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"X-API-Key": api_key})

    def _get(self, path: str, params: dict = None):
        url = f"{self.server_url}{path}"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict = None, params: dict = None):
        url = f"{self.server_url}{path}"
        resp = self._session.post(url, json=json, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, json: dict = None):
        url = f"{self.server_url}{path}"
        resp = self._session.put(url, json=json, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, json: dict = None):
        url = f"{self.server_url}{path}"
        resp = self._session.patch(url, json=json, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_portfolio_history(
        self,
        ticker: Optional[str] = None,
        account: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_summary: bool = False,
        limit: int = 500,
    ) -> dict:
        """Получить историю портфеля (список снимков)."""
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if account:
            params["account"] = account
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if include_summary:
            params["include_summary"] = "true"
        return self._get("/portfolio/history", params=params)

    def trigger_portfolio_history_snapshot(
        self,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        currency: Optional[str] = None,
        trans_type: Optional[str] = None,
    ) -> dict:
        """Принудительно сделать снимок портфеля и синхронизировать transaction log."""
        url = f"{self.server_url}/portfolio/history/snapshot"
        body: dict = {}
        if date_from:
            body["date_from"] = date_from
        if date_to:
            body["date_to"] = date_to
        if currency:
            body["currency"] = currency
        if trans_type:
            body["type"] = trans_type
        resp = self._session.post(
            url, json=body, timeout=max(self.timeout, 90)
        )
        resp.raise_for_status()
        return resp.json()

    def get_portfolio_transaction_log(
        self,
        *,
        currency: Optional[str] = None,
        symbol: Optional[str] = None,
        trans_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
    ) -> dict:
        """Return Bybit UTA transaction log rows from local DB."""
        params: dict = {"limit": limit}
        if currency:
            params["currency"] = currency
        if symbol:
            params["symbol"] = symbol
        if trans_type:
            params["type"] = trans_type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return self._get("/portfolio/transaction-log", params=params)

    def sync_portfolio_transaction_log(
        self,
        *,
        currency: Optional[str] = None,
        trans_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """Pull Bybit UTA transaction log into local DB."""
        params: dict = {}
        if currency:
            params["currency"] = currency
        if trans_type:
            params["type"] = trans_type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        url = f"{self.server_url}/portfolio/transaction-log/sync"
        resp = self._session.post(url, params=params, timeout=max(self.timeout, 90))
        resp.raise_for_status()
        return resp.json()

    def get_portfolio_unified_summary(self, *, live: bool = False) -> dict:
        """Сводка Unified Trading аккаунта Bybit (equity, perp UPL, assets)."""
        return self._get("/portfolio/unified-summary", params={"live": str(live).lower()})

    def health(self, timeout: Optional[int] = None) -> HealthResponse:
        req_timeout = timeout if timeout is not None else self.timeout
        data = self._session.get(f"{self.server_url}/health", timeout=req_timeout).json()
        return HealthResponse(**data)

    def get_logs(
        self,
        ticker: Optional[str] = None,
        method: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
    ) -> List[ForecastLog]:
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if method:
            params["method"] = method
        if status:
            params["status"] = status
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        data = self._get("/logs", params=params)
        return [ForecastLog(**item) for item in data.get("items", [])]

    def get_log(self, log_id: str) -> ForecastLog:
        data = self._get(f"/logs/{log_id}")
        return ForecastLog(**data)

    def get_tickers(self) -> List[TickerSetting]:
        data = self._get("/tickers")
        return [TickerSetting(**item) for item in data.get("items", [])]

    def add_ticker(self, ticker: str, active: int = 1, comment: str = "") -> TickerSetting:
        data = self._post("/tickers", json={"ticker": ticker, "active": active, "comment": comment})
        return TickerSetting(**data)

    def update_ticker(self, ticker: str, active: int, comment: str = "") -> TickerSetting:
        data = self._put(f"/tickers/{ticker}", json={"active": active, "comment": comment})
        return TickerSetting(**data)

    def get_providers(self) -> List[ProviderSetting]:
        data = self._get("/providers")
        return [ProviderSetting(**item) for item in data.get("items", [])]

    def update_provider(self, name: str, **kwargs) -> ProviderSetting:
        data = self._put(f"/providers/{name}", json={k: v for k, v in kwargs.items() if v is not None})
        return ProviderSetting(**data)

    def run_forecast(self) -> RunResponse:
        data = self._post("/run/forecast")
        return RunResponse(**data)

    def run_forecast_ticker(self, ticker: str) -> RunResponse:
        data = self._post(f"/run/forecast/{ticker.strip().upper()}")
        return RunResponse(**data)

    def run_evaluate(self) -> RunResponse:
        data = self._post("/run/evaluate")
        return RunResponse(**data)

    def run_full(self) -> RunResponse:
        data = self._post("/run/full")
        return RunResponse(**data)

    def run_price_data(self) -> RunResponse:
        data = self._post("/run/price-data")
        return RunResponse(**data)

    def run_status(self) -> RunResponse:
        data = self._get("/run/status")
        return RunResponse(**data)

    def _delete(self, path: str):
        url = f"{self.server_url}{path}"
        resp = self._session.delete(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def delete_ticker(self, ticker: str) -> dict:
        return self._delete(f"/tickers/{ticker}")

    def delete_provider(self, name: str) -> dict:
        return self._delete(f"/providers/{name}")

    def get_logs_response(
        self,
        ticker: Optional[str] = None,
        method: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
    ) -> LogsResponse:
        params = {"limit": limit}
        if ticker: params["ticker"] = ticker
        if method: params["method"] = method
        if status: params["status"] = status
        if date_from: params["date_from"] = date_from
        if date_to: params["date_to"] = date_to
        data = self._get("/logs", params=params)
        return LogsResponse(**data)

    def get_config(self) -> ConfigResponse:
        data = self._get("/config")
        return ConfigResponse(**data)

    def set_config(self, key: str, value: str) -> None:
        """Convenience wrapper: PUT /config/{key}."""
        self._put(f"/config/{key}", json={"key": key, "value": value, "description": ""})

    def get(self, path: str, params: dict = None) -> dict:
        """Generic GET — returns raw dict. Used by new tabs (trades, ib-log, etc.)."""
        return self._get(path, params=params)

    def update_config(self, key: str, body: ConfigParam) -> ConfigParam:
        data = self._put(f"/config/{key}", json=body.model_dump())
        return ConfigParam(**data)

    def get_prompts(
        self,
        ticker: Optional[str] = None,
        method: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 200,
    ) -> PromptsResponse:
        params = {"limit": limit}
        if ticker: params["ticker"] = ticker
        if method: params["method"] = method
        if date_from: params["date_from"] = date_from
        if date_to: params["date_to"] = date_to
        data = self._get("/prompts", params=params)
        return PromptsResponse(**data)

    def get_price_data(
        self,
        ticker: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
    ) -> PriceDataResponse:
        params = {"limit": limit}
        if ticker: params["ticker"] = ticker
        if date_from: params["date_from"] = date_from
        if date_to: params["date_to"] = date_to
        data = self._get("/price-data", params=params)
        return PriceDataResponse(**data)

    def get_indicators(
        self,
        ticker: Optional[str] = None,
        limit: int = 200,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> IndicatorsResponse:
        params = {"limit": limit}
        if ticker: params["ticker"] = ticker
        if date_from: params["date_from"] = date_from
        if date_to: params["date_to"] = date_to
        data = self._get("/indicators", params=params)
        return IndicatorsResponse(**data)

    def get_consensus(
        self,
        ticker: Optional[str] = None,
        limit: int = 100,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> ConsensusResponse:
        params = {"limit": limit}
        if ticker: params["ticker"] = ticker
        if date_from: params["date_from"] = date_from
        if date_to: params["date_to"] = date_to
        data = self._get("/consensus", params=params)
        return ConsensusResponse(**data)

    def evaluate_consensus(self) -> dict:
        """Trigger evaluation of pending consensus records."""
        return self._post("/consensus/evaluate")

    def recalculate_consensus(self, date_from: str = None, date_to: str = None, force: bool = False) -> dict:
        """Recalculate consensus from historical forecast logs."""
        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if force:
            params["force"] = "true"
        return self._post("/consensus/recalculate", params=params)

    def activate_consensus(self, consensus_id: int) -> dict:
        """Trigger trade placement for one consensus record."""
        return self._post(f"/consensus/{int(consensus_id)}/activate")

    def preview_consensus_trade(self, consensus_id: int) -> dict:
        """Fetch trade preview details for one consensus record."""
        return self._get(f"/consensus/{int(consensus_id)}/preview-trade")

    def get_system_log(
        self,
        lines: int = 200,
        level: Optional[str] = None,
    ) -> SystemLogResponse:
        params = {"lines": lines}
        if level: params["level"] = level
        data = self._get("/system-log", params=params)
        return SystemLogResponse(**data)

    def get_model_catalog(self, provider: Optional[str] = None) -> dict:
        params = {}
        if provider:
            params["provider"] = provider
        return self._get("/model-catalog", params=params)

    def refresh_model_catalog(self) -> dict:
        return self._post("/model-catalog/refresh", {})

    def get_prompt_templates(self) -> dict:
        return self._get("/prompt-templates")

    def save_prompt_template(self, method: str, prompt_text: str) -> dict:
        return self._put(f"/prompt-templates/{method}", {"prompt_text": prompt_text})

    def reset_prompt_template(self, method: str) -> dict:
        return self._post(f"/prompt-templates/{method}/reset", {})

    def get_accounts(self, broker: Optional[str] = None) -> AccountsResponse:
        params = {}
        if broker:
            params["broker"] = broker
        data = self._get("/accounts", params=params)
        return AccountsResponse(**data)

    def sync_accounts(self) -> dict:
        return self._post("/accounts/sync", json={})

    def get_bybit_credentials(self) -> dict:
        return self._get("/bybit-credentials")

    def put_bybit_credentials(self, profile: str, api_key: str, api_secret: str, set_active: bool = False) -> dict:
        return self._put("/bybit-credentials", json={
            "profile": profile,
            "api_key": api_key,
            "api_secret": api_secret,
            "set_active": set_active,
        })

    def get_portfolio(self, account: Optional[str] = None) -> PortfolioResponse:
        params = {}
        if account:
            params["account"] = account
        data = self._get("/portfolio", params=params)
        return PortfolioResponse(**data)

    def sync_portfolio(self) -> dict:
        return self._post("/portfolio/sync", json={})

    def get_scheduler_tasks(self) -> list:
        """Return all rows from scheduled_tasks."""
        data = self._get("/scheduler/tasks")
        return data.get("items", [])

    def set_task_active(self, name: str, active: int) -> dict:
        """Enable (1) or disable (0) a scheduled task."""
        return self._patch(f"/scheduler/tasks/{name}/active", json={"active": active})

    def get_heartbeat_history(self, limit: int = 20) -> list:
        """Return recent heartbeat_log entries."""
        data = self._get("/heartbeat/history", params={"limit": limit})
        return data.get("items", [])

    def get_orders(
        self,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        include_test: Optional[bool] = None,
        test_only: Optional[bool] = None,
    ) -> list:
        """Return orders from the server."""
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if include_test is not None:
            params["include_test"] = include_test
        if test_only is not None:
            params["test_only"] = test_only
        data = self._get("/orders", params=params)
        return data.get("items", [])

    def get_trades(
        self,
        trade_id: Optional[int] = None,
        consensus_id: Optional[int] = None,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        include_test: Optional[bool] = None,
        test_only: Optional[bool] = None,
    ) -> list:
        """Return trades from the server."""
        params = {"limit": limit}
        if trade_id is not None:
            params["trade_id"] = int(trade_id)
        if consensus_id is not None:
            params["consensus_id"] = int(consensus_id)
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if include_test is not None:
            params["include_test"] = include_test
        if test_only is not None:
            params["test_only"] = test_only
        data = self._get("/trades", params=params)
        return data.get("items", data.get("trades", []))

    def get_trade_by_id(self, trade_id: int, include_test: Optional[bool] = None) -> Optional[dict]:
        """Return one trade by DB id or None when not found."""
        rows = self.get_trades(trade_id=trade_id, limit=1, include_test=include_test)
        if not rows:
            return None
        return rows[0]

    def cancel_order(self, order_id: int) -> dict:
        """Cancel an order by DB id."""
        return self._post(f"/orders/{order_id}/cancel")

    def sync_orders(self) -> dict:
        """Trigger one-shot Bybit -> local orders/trades synchronization."""
        return self._post("/orders/sync", json={})

    def get_bybit_transactions(
        self,
        ticker: Optional[str] = None,
        bybit_order_id: Optional[str] = None,
        event_source: Optional[str] = None,
        event_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
    ) -> list:
        """Return rows from bybit_order_transactions."""
        params: dict = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if bybit_order_id:
            params["bybit_order_id"] = str(bybit_order_id)
        if event_source:
            params["event_source"] = event_source
        if event_type:
            params["event_type"] = event_type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        data = self._get("/bybit-transactions", params=params)
        return data.get("items", [])

    def get_ib_transactions(
        self,
        ticker: Optional[str] = None,
        ib_order_id: Optional[int] = None,
        ib_parent_id: Optional[int] = None,
        event_source: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 500,
    ) -> list:
        """Deprecated: use get_bybit_transactions. ib_order_id maps to bybit_order_id filter."""
        bybit_id = str(ib_order_id) if ib_order_id is not None else None
        return self.get_bybit_transactions(
            ticker=ticker,
            bybit_order_id=bybit_id,
            event_source=event_source,
            event_type=event_type,
            limit=limit,
        )

    def get_tickets(
        self,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
        portfolio: Optional[int] = None,
        limit: int = 500,
    ) -> list:
        """Return tickets list."""
        params: dict = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        if portfolio is not None:
            params["portfolio"] = portfolio
        data = self._get("/tickets", params=params)
        return data.get("items", [])

    def create_ticket(self, ticker: str, **kwargs) -> dict:
        """Create a new ticket."""
        return self._post("/tickets", {"ticker": ticker, **kwargs})

    def update_ticket(self, ticket_id: int, **kwargs) -> dict:
        """Update ticket fields."""
        return self._patch(f"/tickets/{ticket_id}", kwargs)

    def delete_ticket(self, ticket_id: int) -> dict:
        """Delete a ticket."""
        return self._delete(f"/tickets/{ticket_id}")

    def create_method(self, method: str, timeframe_hours: int = 24,
                      trigger: str = "both", execute: str = "yes") -> dict:
        """Create a new method configuration."""
        return self._post("/method-config", json={
            "method": method,
            "timeframe_hours": timeframe_hours,
            "trigger": trigger,
            "execute": execute,
        })

    def get_method_configs(self) -> list:
        """Return all method configurations."""
        data = self._get("/method-config")
        return data.get("items", [])

    def get_method_config(self, method: str) -> dict:
        """Return detailed configuration for a specific method."""
        return self._get(f"/method-config/{method}")

    def update_method_execute(self, method: str, execute: str) -> dict:
        """Update execute flag for a method ('yes' or 'no')."""
        return self._put(f"/method-config/{method}/execute", json={"execute": execute})

    def update_provider_execute(self, provider: str, execute: str) -> dict:
        """Update execute flag for a provider ('yes' or 'no')."""
        return self._put(f"/providers/{provider}/execute", json={"execute": execute})

    def get_forecast_runs(self, limit: int = 50) -> dict:
        """Return list of forecast runs with aggregated stats."""
        return self._get("/forecast-runs", params={"limit": limit})

    def get_forecast_run(self, run_id: int) -> dict:
        """Return details of a specific forecast run including links."""
        return self._get(f"/forecast-runs/{run_id}")
