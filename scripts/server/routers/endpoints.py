"""REST API route handlers."""

import logging
import os
from datetime import datetime
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends, Body

from scripts.shared.models import (
    ForecastLog, TickerSetting, ProviderSetting,
    LogsResponse, TickersResponse, ProvidersResponse,
    TickerUpdate, TickerCreate, ProviderUpdate,
    RunResponse, HealthResponse,
    ConfigParam, ConfigResponse,
    PromptRecord, PromptsResponse,
    PriceRecord, PriceDataResponse,
    IndicatorRecord, IndicatorsResponse,
    ConsensusRecord, ConsensusResponse,
    PositionRecord, PortfolioResponse,
    AccountRecord, AccountsResponse,
    SystemLogResponse, OrderSubmitRequest, OrderSubmitResponse,
    ForecastRunLink, ForecastRunRecord, ForecastRunsResponse, ForecastRunDetailResponse,
)
from scripts.core.config import get_confidence_threshold
from scripts.server import dependencies as deps
from scripts.server.config_validation import validate_config_value as _validate_config_value

logger = logging.getLogger(__name__)
router = APIRouter()

verify_api_key = deps.verify_api_key


def _get_db_manager():
    return deps.get_db()


def _get_data_manager():
    return deps.get_db()


def _clean_record(record):
    return deps.clean_record(record)


def _clean_records(records):
    return deps.clean_records(records)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    cfg = deps.get_config()
    db_exists = os.path.exists(cfg.db_file) if cfg else False
    return HealthResponse(
        status="ok",
        db_file=cfg.db_file if cfg else None,
        db_exists=db_exists,
        server=f"{cfg.host}:{cfg.port}" if cfg else None,
    )


@router.get("/logs", response_model=LogsResponse, dependencies=[Depends(verify_api_key)])
async def get_logs(
    ticker: Optional[str] = None,
    method: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(500, ge=1, le=5000),
):
    try:
        em = _get_data_manager()
        df = em.read_sheet("Logs")
        if df.empty:
            return LogsResponse(items=[], total=0)

        if ticker:
            df = df[df["ticker"].astype(str).str.upper() == ticker.upper()]
        if method:
            df = df[df["method"].astype(str).str.lower() == method.lower()]
        if status:
            df = df[df["status"].astype(str).str.upper() == status.upper()]
        if date_from:
            df["_fd"] = pd.to_datetime(df["forecast_date"], errors="coerce")
            df = df[df["_fd"] >= pd.to_datetime(date_from)]
            df = df.drop(columns=["_fd"])
        if date_to:
            df["_fd"] = pd.to_datetime(df["forecast_date"], errors="coerce")
            df = df[df["_fd"] <= pd.to_datetime(date_to)]
            df = df.drop(columns=["_fd"])

        df = df.sort_values("created_at", ascending=False).head(limit)
        df = df.where(df.notna(), None)
        records = df.to_dict("records")
        items = [ForecastLog(**_safe_row(r)) for r in records]
        return LogsResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading logs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/{log_id}", response_model=ForecastLog, dependencies=[Depends(verify_api_key)])
async def get_log(log_id: str):
    try:
        em = _get_data_manager()
        df = em.read_sheet("Logs")
        if df.empty:
            raise HTTPException(status_code=404, detail="Not found")
        row = df[df["id"].astype(str) == log_id]
        if row.empty:
            raise HTTPException(status_code=404, detail="Log entry not found")
        row = row.where(row.notna(), None)
        return ForecastLog(**_safe_row(row.iloc[0].to_dict()))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error reading log entry")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickers", response_model=TickersResponse, dependencies=[Depends(verify_api_key)])
async def get_tickers():
    try:
        em = _get_data_manager()
        df = em.read_sheet("Settings")
        if df.empty:
            return TickersResponse(items=[])
        df = df.where(df.notna(), None)
        items = [TickerSetting(**_safe_row(r)) for r in df.to_dict("records")]
        return TickersResponse(items=items)
    except Exception as e:
        logger.exception("Error reading tickers")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tickers/{ticker}", dependencies=[Depends(verify_api_key)])
async def delete_ticker(ticker: str):
    try:
        em = _get_db_manager()
        with em._connect() as con:
            con.execute("DELETE FROM settings WHERE ticker = ?", (ticker,))
        return {"deleted": ticker}
    except Exception as e:
        logger.exception("Error deleting ticker")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickers", response_model=TickerSetting, dependencies=[Depends(verify_api_key)])
async def add_ticker(body: TickerCreate):
    try:
        em = _get_db_manager()
        df = em.read_sheet("Settings")
        if not df.empty and body.ticker in df["ticker"].astype(str).values:
            raise HTTPException(status_code=409, detail="Ticker already exists")
        new_row = {"ticker": body.ticker, "active": body.active, "comment": body.comment or ""}
        em.append_to_sheet("Settings", new_row)
        return TickerSetting(**new_row)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding ticker")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tickers/{ticker}", response_model=TickerSetting, dependencies=[Depends(verify_api_key)])
async def update_ticker(ticker: str, body: TickerUpdate):
    try:
        em = _get_db_manager()
        df = em.read_sheet("Settings")
        if df.empty:
            raise HTTPException(status_code=404, detail="Settings sheet empty")
        mask = df["ticker"].astype(str) == ticker
        if not mask.any():
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
        em.upsert_row("settings", {
            "ticker":  ticker,
            "active":  body.active,
            "comment": body.comment or "",
        })
        return TickerSetting(ticker=ticker, active=body.active, comment=body.comment)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating ticker")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", response_model=ProvidersResponse, dependencies=[Depends(verify_api_key)])
async def get_providers():
    try:
        em = _get_db_manager()
        df = em.read_sheet("Providers")
        if df.empty:
            return ProvidersResponse(items=[])
        df = df.where(df.notna(), None)
        items = [ProviderSetting(**_safe_row(r)) for r in df.to_dict("records")]
        return ProvidersResponse(items=items)
    except Exception as e:
        logger.exception("Error reading providers")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/providers/{name}", response_model=ProviderSetting, dependencies=[Depends(verify_api_key)])
async def update_provider(name: str, body: ProviderUpdate):
    try:
        em = _get_db_manager()
        # Build upsert payload — merge existing row with updates
        with em._connect() as con:
            cur = con.execute("SELECT * FROM providers WHERE name = ?", (name,))
            row = cur.fetchone()
        if row:
            existing = dict(row)
        else:
            existing = {"name": name, "type": "ai",
                        "base_url": "https://openrouter.ai/api/v1",
                        "api_key": "", "model": "",
                        "temperature": 0.2, "max_tokens": 2000,
                        "rate_limit": 60, "active": 1}
        if body.api_key is not None:   existing["api_key"]     = body.api_key
        if body.model is not None:     existing["model"]       = body.model
        if body.temperature is not None: existing["temperature"] = body.temperature
        if body.max_tokens is not None: existing["max_tokens"]  = body.max_tokens
        if body.rate_limit is not None: existing["rate_limit"]  = body.rate_limit
        if body.active is not None:    existing["active"]      = body.active
        em.upsert_row("providers", existing)
        return ProviderSetting(**_safe_row(existing))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating provider")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/forecast", response_model=RunResponse, dependencies=[Depends(verify_api_key)])
async def run_forecast():
    if not deps.get_runner().start("forecast"):
        raise HTTPException(status_code=409, detail="Robot is already running")
    return RunResponse(status="running", message="Forecast started", started_at=deps.get_runner().started_at)


@router.post("/run/evaluate", response_model=RunResponse, dependencies=[Depends(verify_api_key)])
async def run_evaluate():
    if not deps.get_runner().start("evaluate"):
        raise HTTPException(status_code=409, detail="Robot is already running")
    return RunResponse(status="running", message="Evaluation started", started_at=deps.get_runner().started_at)


@router.post("/run/full", response_model=RunResponse, dependencies=[Depends(verify_api_key)])
async def run_full():
    if not deps.get_runner().start("full"):
        raise HTTPException(status_code=409, detail="Robot is already running")
    return RunResponse(status="running", message="Full cycle started", started_at=deps.get_runner().started_at)


@router.post("/run/price-data", response_model=RunResponse, dependencies=[Depends(verify_api_key)])
async def run_price_data():
    if not deps.get_runner().start("price_data"):
        raise HTTPException(status_code=409, detail="Robot is already running")
    return RunResponse(status="running", message="Price data update started", started_at=deps.get_runner().started_at)


@router.get("/run/status", response_model=RunResponse, dependencies=[Depends(verify_api_key)])
async def run_status():
    return RunResponse(
        status=deps.get_runner().status,
        message=deps.get_runner().message,
        started_at=deps.get_runner().started_at,
        finished_at=deps.get_runner().finished_at,
        duration_sec=deps.get_runner().duration_sec,
        log_lines=deps.get_runner().get_log_lines(),
    )


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@router.get("/config", response_model=ConfigResponse, dependencies=[Depends(verify_api_key)])
async def get_config_all():
    try:
        em = _get_db_manager()
        df = em.read_sheet("Config")
        if df.empty:
            return ConfigResponse(items=[])
        df = df.where(df.notna(), None)
        items = [ConfigParam(**_safe_row(r)) for r in df.to_dict("records")]
        return ConfigResponse(items=items)
    except Exception as e:
        logger.exception("Error reading config")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/{key}", response_model=ConfigParam, dependencies=[Depends(verify_api_key)])
async def update_config(key: str, body: ConfigParam):
    try:
        em = _get_db_manager()
        value = body.value or ""
        _validate_config_value(key, value)
        em.set_config_value(key, value)
        logger.info(f"[API] Config updated: {key} = {value!r}")
        return ConfigParam(key=key, value=value, description=body.description)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating config")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Prompts endpoint
# ---------------------------------------------------------------------------

@router.get("/prompts", response_model=PromptsResponse, dependencies=[Depends(verify_api_key)])
async def get_prompts(
    ticker: Optional[str] = None,
    method: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(200, le=1000),
):
    try:
        em = _get_db_manager()
        df = em.get_prompts(ticker=ticker, method=method, date_from=date_from, date_to=date_to, limit=limit)
        if df.empty:
            return PromptsResponse(items=[], total=0)
        df = df.where(df.notna(), None)
        items = [PromptRecord(**_safe_row(r)) for r in df.to_dict("records")]
        return PromptsResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading prompts")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Price data endpoint
# ---------------------------------------------------------------------------

@router.get("/price-data", response_model=PriceDataResponse, dependencies=[Depends(verify_api_key)])
async def get_price_data(
    ticker: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(500, le=5000),
):
    try:
        em = _get_db_manager()
        df = em.get_price_data(ticker=ticker, date_from=date_from, date_to=date_to, limit=limit)
        if df.empty:
            return PriceDataResponse(items=[], total=0)
        df = df.where(df.notna(), None)
        items = [PriceRecord(**_safe_row(r)) for r in df.to_dict("records")]
        return PriceDataResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading price data")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Indicators endpoint
# ---------------------------------------------------------------------------

@router.get("/indicators", response_model=IndicatorsResponse, dependencies=[Depends(verify_api_key)])
async def get_indicators(
    ticker: Optional[str] = None,
    limit: int = Query(200, le=2000),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    try:
        em = _get_db_manager()
        df = em.get_indicators(ticker=ticker, limit=limit, date_from=date_from, date_to=date_to)
        if df.empty:
            return IndicatorsResponse(items=[], total=0)
        df = df.where(df.notna(), None)
        items = [IndicatorRecord(**_safe_row(r)) for r in df.to_dict("records")]
        return IndicatorsResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading indicators")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Consensus evaluation & recalculation
# ---------------------------------------------------------------------------

@router.post("/consensus/evaluate", dependencies=[Depends(verify_api_key)])
async def evaluate_consensus():
    """Manually trigger evaluation of pending consensus records.

    Returns detailed result with counts of processed records.
    This is a synchronous call - waits for evaluation to complete.
    """
    logger.info("consensus/evaluate: starting manual evaluation request")
    try:
        from scripts.core.consensus_evaluator import evaluate_consensus_records
        em = _get_db_manager()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check pending records - ready vs not ready
        with em._connect() as con:
            # Ready for evaluation (target date passed)
            cur = con.execute(
                "SELECT COUNT(*) FROM consensus WHERE eval_status = 'PENDING' AND eval_target_date IS NOT NULL AND eval_target_date <= ?",
                (now_str,)
            )
            ready_before = cur.fetchone()[0]
            # Pending but not ready yet (target date in future)
            cur = con.execute(
                "SELECT COUNT(*) FROM consensus WHERE eval_status = 'PENDING' AND eval_target_date IS NOT NULL AND eval_target_date > ?",
                (now_str,)
            )
            not_ready = cur.fetchone()[0]
            # Pending without target date
            cur = con.execute(
                "SELECT COUNT(*) FROM consensus WHERE eval_status = 'PENDING' AND (eval_target_date IS NULL OR eval_target_date = '')"
            )
            no_target = cur.fetchone()[0]

        logger.info(f"consensus/evaluate: ready={ready_before}, not_ready={not_ready}, no_target={no_target}")

        from scripts.server.async_blocking import run_blocking

        count = await run_blocking(evaluate_consensus_records, em)

        # Check results after evaluation
        with em._connect() as con:
            cur = con.execute(
                "SELECT COUNT(*) FROM consensus WHERE eval_status = 'PENDING' AND eval_target_date IS NOT NULL AND eval_target_date <= ?",
                (now_str,)
            )
            ready_after = cur.fetchone()[0]
            cur = con.execute(
                "SELECT COUNT(*) FROM consensus WHERE eval_status = 'EVALUATED'"
            )
            total_evaluated = cur.fetchone()[0]

        logger.info(
            f"consensus/evaluate: completed. processed={count}, "
            f"ready_before={ready_before}, ready_after={ready_after}, "
            f"total_evaluated={total_evaluated}"
        )

        return {
            "status": "completed",
            "message": f"Evaluated {count} consensus records",
            "processed": count,
            "ready_before": ready_before,
            "ready_after": ready_after,
            "not_ready": not_ready,
            "no_target": no_target,
            "total_evaluated": total_evaluated,
        }
    except Exception as e:
        logger.exception(f"consensus/evaluate error: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


# ---------------------------------------------------------------------------
# Consensus recalculate endpoint
# ---------------------------------------------------------------------------

@router.post("/consensus/recalculate", dependencies=[Depends(verify_api_key)])
async def recalculate_consensus(
    date_from: str = Query(None, description="Start date YYYY-MM-DD"),
    date_to: str = Query(None, description="End date YYYY-MM-DD"),
    force: bool = Query(False, description="If true, overwrite EVALUATED records and reset eval fields"),
):
    """Recalculate consensus records from historical forecast logs.

    Groups forecasts by (created_date, ticker), calculates consensus for each group,
    and creates/updates consensus records.
    When force=True, overwrites all records including EVALUATED and resets eval fields.
    """
    logger.info(f"consensus/recalculate: starting date_from={date_from}, date_to={date_to}, force={force}")
    try:
        from scripts.core.consensus_recalc import recalculate_consensus as run_recalculate_consensus
        em = _get_db_manager()

        from scripts.server.async_blocking import run_blocking

        stats = await run_blocking(
            run_recalculate_consensus, em, date_from=date_from, date_to=date_to, force=force
        )

        logger.info(
            f"consensus/recalculate: completed. "
            f"created={stats['created']}, updated={stats['updated']}, "
            f"skipped={stats['skipped']}, errors={stats['errors']}"
        )

        return {
            "status": "completed",
            "message": f"Recalculated {stats['total_groups']} consensus groups",
            "created": stats["created"],
            "updated": stats["updated"],
            "skipped": stats["skipped"],
            "evaluated": stats.get("evaluated", 0),
            "errors": stats["errors"],
            "total_groups": stats["total_groups"],
        }
    except Exception as e:
        logger.exception(f"consensus/recalculate error: {e}")
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {str(e)}")


# ---------------------------------------------------------------------------
# System log endpoint
# ---------------------------------------------------------------------------

@router.get("/system-log", response_model=SystemLogResponse, dependencies=[Depends(verify_api_key)])
async def get_system_log(
    lines: int = Query(200, le=2000),
    level: Optional[str] = None,
):
    try:
        from scripts.bootstrap import get_project_root

        log_file = os.path.join(get_project_root(), "trading_robot.log")
        if not os.path.exists(log_file):
            return SystemLogResponse(lines=[], total=0)
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        all_lines = [l.rstrip() for l in all_lines]
        if level:
            lvl = level.upper()
            all_lines = [l for l in all_lines if lvl in l]
        result = all_lines[-lines:]
        return SystemLogResponse(lines=result, total=len(result))
    except Exception as e:
        logger.exception("Error reading system log")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Provider management: add / delete
# ---------------------------------------------------------------------------

@router.post("/providers", response_model=ProviderSetting, dependencies=[Depends(verify_api_key)])
async def add_provider(body: ProviderSetting):
    try:
        em = _get_db_manager()
        name = body.get_name()
        if not name:
            raise HTTPException(status_code=422, detail="Provider name is required")
        em.upsert_row("providers", {
            "name":        name,
            "type":        "ai",
            "base_url":    "https://openrouter.ai/api/v1",
            "api_key":     body.get_api_key(),
            "model":       body.model or "",
            "temperature": body.temperature or 0.2,
            "max_tokens":  body.max_tokens or 2000,
            "rate_limit":  body.rate_limit or 60,
            "active":      body.active if body.active is not None else 1,
        })
        return body
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding provider")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/providers/{name}", dependencies=[Depends(verify_api_key)])
async def delete_provider(name: str):
    try:
        em = _get_db_manager()
        with em._connect() as con:
            con.execute("DELETE FROM providers WHERE name = ?", (name,))
        return {"deleted": name}
    except Exception as e:
        logger.exception("Error deleting provider")
        raise HTTPException(status_code=500, detail=str(e))


def _safe_row(row: dict) -> dict:
    """Convert NaN / numpy types to plain Python for Pydantic."""
    import math
    result = {}
    for k, v in row.items():
        if v is None:
            result[k] = None
        elif isinstance(v, float) and math.isnan(v):
            result[k] = None
        else:
            try:
                import numpy as np
                if isinstance(v, (np.integer,)):
                    result[k] = int(v)
                elif isinstance(v, (np.floating,)):
                    result[k] = float(v)
                elif isinstance(v, (np.bool_,)):
                    result[k] = bool(v)
                else:
                    result[k] = v
            except ImportError:
                result[k] = v
    return result


# ---------------------------------------------------------------------------
# Prompt templates endpoints
# ---------------------------------------------------------------------------

@router.get("/prompt-templates", dependencies=[Depends(verify_api_key)])
async def get_prompt_templates():
    try:
        em = _get_db_manager()
        templates = em.get_all_prompt_templates()
        return {"templates": templates}
    except Exception as e:
        logger.exception("Error reading prompt templates")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/prompt-templates/{method}", dependencies=[Depends(verify_api_key)])
async def save_prompt_template(method: str, body: dict = Body(...)):
    try:
        em = _get_db_manager()
        text = body.get("prompt_text", "")
        ok = em.save_prompt_template(method, text)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to save template")
        return {"saved": method}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error saving prompt template")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt-templates/{method}/reset", dependencies=[Depends(verify_api_key)])
async def reset_prompt_template(method: str):
    try:
        em = _get_db_manager()
        ok = em.reset_prompt_template(method)
        if not ok:
            raise HTTPException(status_code=404, detail=f"No default for method '{method}'")
        return {"reset": method}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resetting prompt template")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Model catalog endpoints
# ---------------------------------------------------------------------------

@router.get("/model-catalog", dependencies=[Depends(verify_api_key)])
async def get_model_catalog(provider: str = Query(None)):
    try:
        em = _get_db_manager()
        df = em.get_model_catalog(provider=provider)
        if df.empty:
            return {"items": [], "total": 0}
        df = df.where(df.notna(), None)
        return {"items": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        logger.exception("Error reading model catalog")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model-catalog/refresh", dependencies=[Depends(verify_api_key)])
async def refresh_model_catalog():
    try:
        em = _get_db_manager()
        api_key = em.get_config_value("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY not configured")
        count = em.refresh_model_catalog(api_key)
        if count < 0:
            raise HTTPException(status_code=502, detail="Failed to fetch models from OpenRouter")
        return {"refreshed": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error refreshing model catalog")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Accounts endpoints
# ---------------------------------------------------------------------------

@router.get("/accounts", response_model=AccountsResponse, dependencies=[Depends(verify_api_key)])
async def get_accounts(broker: str = Query(None)):
    try:
        from scripts.core.bybit_config import (
            list_secrets_profiles, _load_secrets_ini, get_masked_api_key,
        )
        em = _get_db_manager()

        # Active profile from DB config
        active_profile = em.get_config_value("BYBIT_ACTIVE_PROFILE", "demo") or "demo"
        bybit_demo_flag = (em.get_config_value("BYBIT_DEMO", "true") or "true").lower() == "true"

        # Read DB accounts keyed by profile / account_id
        db_rows: dict = {}
        try:
            with em._connect() as con:
                rows = con.execute("SELECT * FROM accounts WHERE broker='bybit'").fetchall()
            for row in rows:
                d = dict(row)
                key = d.get("profile") or d.get("type") or d.get("account_id", "")
                if key:
                    db_rows[key] = d
                account_id = d.get("account_id")
                if account_id:
                    db_rows[account_id] = d
        except Exception as e:
            logger.warning(f"get_accounts: failed to read DB rows: {e}")

        # Build one item per profile in secrets.ini
        profiles = list_secrets_profiles()
        if not profiles:
            profiles = [active_profile]

        items = []
        for profile in profiles:
            creds = _load_secrets_ini(profile)
            connected = bool(creds.get("api_key") and creds.get("api_secret"))
            is_active = (profile == active_profile)
            # Determine mode: active profile uses BYBIT_DEMO flag; others use profile name heuristic
            if is_active:
                mode = "Demo" if bybit_demo_flag else "Live"
            else:
                mode = "Live" if profile == "live" else "Demo"

            db = db_rows.get(profile) or db_rows.get(f"bybit-{profile}") or {}
            items.append(AccountRecord(
                profile=profile,
                mode=mode,
                uid=db.get("uid") or "",
                account_type=db.get("account_type") or "UNIFIED",
                net_liquidation=db.get("net_liquidation") if db else None,
                available_funds=db.get("available_funds") if db else None,
                unrealized_pnl=db.get("unrealized_pnl") if db else None,
                positions_count=db.get("positions_count") if db else None,
                active=is_active,
                connected=connected,
                last_update=db.get("last_update") or "",
                # legacy fields
                broker="bybit",
                account_id=db.get("account_id") or f"bybit-{profile}",
                name=db.get("name") or f"Bybit {mode} ({profile})",
                base_currency="USDT",
            ))

        return AccountsResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading accounts")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Bybit credentials endpoints
# ---------------------------------------------------------------------------

@router.get("/bybit-credentials", dependencies=[Depends(verify_api_key)])
async def get_bybit_credentials():
    """
    Return list of profiles with masked api_key.
    Secret is NEVER returned to the client.
    """
    try:
        from scripts.core.bybit_config import list_secrets_profiles, get_masked_api_key, _load_secrets_ini
        em = _get_db_manager()
        active_profile = em.get_config_value("BYBIT_ACTIVE_PROFILE", "demo") or "demo"
        profiles = list_secrets_profiles()
        result = []
        for profile in profiles:
            creds = _load_secrets_ini(profile)
            result.append({
                "profile": profile,
                "api_key_masked": get_masked_api_key(profile),
                "api_secret_set": bool(creds.get("api_secret")),
                "active": profile == active_profile,
            })
        return {"profiles": result, "active_profile": active_profile}
    except Exception as e:
        logger.exception("Error reading bybit credentials")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/bybit-credentials", dependencies=[Depends(verify_api_key)])
async def put_bybit_credentials(body: dict = Body(...)):
    """
    Save api_key + api_secret for a profile to secrets.ini (server-side file).
    Also updates BYBIT_ACTIVE_PROFILE in SQLite if set_active=True.
    Body: {profile, api_key, api_secret, set_active?}
    """
    try:
        from scripts.core.bybit_config import save_secrets_profile
        profile = (body.get("profile") or "").strip()
        api_key = (body.get("api_key") or "").strip()
        api_secret = (body.get("api_secret") or "").strip()
        set_active = bool(body.get("set_active", False))
        if not profile:
            raise HTTPException(status_code=422, detail="profile is required")
        ok = save_secrets_profile(profile, api_key, api_secret)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to write secrets.ini")
        em = _get_db_manager()
        if set_active:
            em.set_config_value("BYBIT_ACTIVE_PROFILE", profile)
        return {"saved": True, "profile": profile, "active_profile_updated": set_active}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error saving bybit credentials")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/sync", dependencies=[Depends(verify_api_key)])
async def sync_accounts():
    """Force immediate sync of Bybit account data."""
    try:
        from scripts.core.bybit_worker import is_running
        from scripts.core.bybit_account_sync import sync_account_data_async
        
        if not is_running():
            raise HTTPException(status_code=503, detail="Bybit worker is not running - check API configuration")
        
        em = _get_db_manager()
        result = await sync_account_data_async(em)
        
        if result is None:
            raise HTTPException(status_code=502, detail="Failed to sync account data from Bybit API")
        
        logger.info(f"Manual account sync: {result['account_id']} - equity={result['net_liquidation']:.2f} USDT")
        
        return {
            "synced": True,
            "account": {
                "account_id": result["account_id"],
                "name": result["name"],
                "type": result["type"],
                "net_liquidation": result["net_liquidation"],
                "buying_power": result["buying_power"],
                "available_funds": result["available_funds"],
                "base_currency": result["base_currency"],
                "positions_count": result["positions_count"],
            },
            "timestamp": result["last_update"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error syncing accounts")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------

@router.get("/portfolio", response_model=PortfolioResponse, dependencies=[Depends(verify_api_key)])
async def get_portfolio(account: str = Query(None)):
    try:
        em = _get_db_manager()
        df = em.read_sheet('Portfolio')
        if df.empty:
            return PortfolioResponse(items=[], total=0)
        if account:
            df = df[df.get('account', '') == account]
        df = df.where(df.notna(), None)
        items = [PositionRecord(**row) for row in df.to_dict('records')]
        return PortfolioResponse(items=items, total=len(items))
    except Exception as e:
        logger.exception("Error reading portfolio")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/history", dependencies=[Depends(verify_api_key)])
async def get_portfolio_history(
    ticker: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    include_summary: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
):
    """Вернуть историю портфеля (снимки) с фильтрами по account и дате."""
    try:
        em = _get_db_manager()
        query = "SELECT * FROM portfolio_history"
        clauses = []
        params = []
        if not include_summary:
            clauses.append("COALESCE(row_type, 'position') <> 'summary'")
        if ticker:
            clauses.append("ticker=?")
            params.append(ticker)
        if account:
            clauses.append("account=?")
            params.append(account)
        if date_from:
            clauses.append("timestamp>=?")
            params.append(date_from)
        if date_to:
            clauses.append("timestamp<=?")
            params.append(date_to + "T23:59:59")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with em._connect() as con:
            rows = con.execute(query, params).fetchall()
        items = [dict(r) for r in rows]
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("Error fetching portfolio history")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio/sync", dependencies=[Depends(verify_api_key)])
async def sync_portfolio():
    """Trigger an immediate portfolio sync from Bybit and update the Portfolio table."""
    try:
        from scripts.core.bybit_order_status_sync import sync_positions_with_bybit
        from datetime import datetime, timezone
        em = _get_db_manager()
        from scripts.server.async_blocking import run_blocking

        result = await run_blocking(sync_positions_with_bybit, em)
        synced_at = datetime.now(tz=timezone.utc).isoformat()
        em.set_config_value("LAST_PORTFOLIO_SYNC_AT", synced_at)
        return {"synced_at": synced_at, "positions": result}
    except Exception as e:
        logger.exception("Error syncing portfolio")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio/history/snapshot", dependencies=[Depends(verify_api_key)])
async def trigger_portfolio_history_snapshot():
    """Принудительно собрать snapshot портфеля через Bybit API."""
    try:
        from scripts.core.bybit_unified_wallet import (
            load_cached_unified_wallet,
            sync_unified_wallet_snapshot,
        )
        from scripts.core.bybit_account_sync import sync_account_data_async

        em = _get_db_manager()
        account = await sync_account_data_async(em)
        positions_count = int((account or {}).get("positions_count") or 0)
        # Account sync already fetched and cached the unified wallet.
        wallet = load_cached_unified_wallet(em)

        wallet, inserted = sync_unified_wallet_snapshot(
            em, positions_count=positions_count, wallet=wallet
        )
        if wallet:
            return {"snapshots_added": inserted, "total_equity": wallet.get("total_equity", 0)}
        return {"snapshots_added": 0}
    except Exception as e:
        logger.exception("Error triggering portfolio history snapshot")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/unified-summary", dependencies=[Depends(verify_api_key)])
async def get_portfolio_unified_summary(live: bool = Query(False)):
    """Сводка Unified Trading аккаунта Bybit (total equity, perp UPL, assets)."""
    try:
        from scripts.core.bybit_config import load_bybit_config
        from scripts.core.bybit_unified_wallet import get_unified_wallet
        from scripts.server.async_blocking import run_blocking

        em = _get_db_manager()
        cfg = load_bybit_config(em)
        wallet, source = await run_blocking(get_unified_wallet, em, live=live)

        if not wallet:
            return {
                "available": False,
                "source": source,
                "account_type": "UNIFIED",
                "mode": "Demo" if cfg.demo else "Live",
                "profile": cfg.active_profile or "demo",
                "total_equity": 0,
                "total_perp_upl": 0,
                "total_available_balance": 0,
                "coins": [],
                "timestamp": "",
            }

        return {
            "available": True,
            "source": source,
            "account_type": wallet.get("account_type", "UNIFIED"),
            "mode": "Demo" if cfg.demo else "Live",
            "profile": cfg.active_profile or "demo",
            "total_equity": wallet.get("total_equity", 0),
            "total_perp_upl": wallet.get("total_perp_upl", 0),
            "total_available_balance": wallet.get("total_available_balance", 0),
            "total_wallet_balance": wallet.get("total_wallet_balance", 0),
            "coins": wallet.get("coins", []),
            "timestamp": wallet.get("timestamp", ""),
        }
    except Exception as e:
        logger.exception("Error fetching unified portfolio summary")
        raise HTTPException(status_code=500, detail=str(e))




# ---------------------------------------------------------------------------
# Capital & consensus endpoints (ред. 2)
# ---------------------------------------------------------------------------

@router.get("/capital", dependencies=[Depends(verify_api_key)])
async def get_capital():
    """Return available capital from Bybit or manual override."""
    try:
        from scripts.core.bybit_capital_provider import get_available_capital
        em = _get_db_manager()
        capital = get_available_capital(em, allow_fallback=True)
        return {"net_liquidation": capital, "source": "bybit"}
    except Exception as e:
        logger.exception("Error fetching capital")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consensus", dependencies=[Depends(verify_api_key)])
async def get_consensus(ticker: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    """Return recent consensus records, optionally filtered by ticker."""
    try:
        import sqlite3
        em = _get_db_manager()
        with em._connect() as con:
            if ticker:
                rows = con.execute(
                    "SELECT * FROM consensus WHERE UPPER(ticker)=UPPER(?) ORDER BY date DESC LIMIT ?",
                    (ticker, limit)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM consensus ORDER BY date DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.exception("Error fetching consensus")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Forecast Run tracking endpoints
# ---------------------------------------------------------------------------

@router.get("/forecast-runs", dependencies=[Depends(verify_api_key)])
async def get_forecast_runs(limit: int = Query(50, ge=1, le=200)):
    """Return recent forecast runs with aggregated statistics."""
    try:
        em = _get_db_manager()
        df = em.get_forecast_runs(limit=limit)
        items = _clean_records(df.to_dict('records')) if not df.empty else []
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.exception("Error fetching forecast runs")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast-runs/{run_id}", dependencies=[Depends(verify_api_key)])
async def get_forecast_run_detail(run_id: int):
    """Return detailed info for a specific forecast run including all links."""
    try:
        em = _get_db_manager()

        run = em.get_forecast_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Forecast run {run_id} not found")

        links_df = em.get_forecast_run_links(run_id)
        links = _clean_records(links_df.to_dict('records')) if not links_df.empty else []

        consensus = []
        try:
            with em._connect() as con:
                rows = con.execute(
                    "SELECT * FROM consensus WHERE run_id = ? ORDER BY date DESC",
                    (run_id,)
                ).fetchall()
                consensus = _clean_records([dict(r) for r in rows])
        except Exception:
            pass

        return {
            "run": _clean_record(run) if isinstance(run, dict) else run,
            "links": links,
            "consensus": consensus if consensus else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching forecast run {run_id}")
        raise HTTPException(status_code=500, detail=str(e))


# Order, trade, Bybit, forecast activation, and scheduler routes live in
# scripts/server/routers/orders.py, forecast.py, scheduler_routes.py (included from api.py).

# ---------------------------------------------------------------------------
# Method config endpoints
# ---------------------------------------------------------------------------

@router.get("/method-config", dependencies=[Depends(verify_api_key)])
async def get_method_config():
    """Return method configuration (timeframe_hours, trigger, active)."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            rows = con.execute("SELECT * FROM method_config ORDER BY method").fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.exception("Error fetching method_config")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/method-config", dependencies=[Depends(verify_api_key)])
async def create_method_config(body: dict = Body(...)):
    """Create a new method with its config and empty prompt template."""
    try:
        method = body.get("method", "").strip()
        if not method:
            raise HTTPException(status_code=400, detail="method name is required")
        timeframe_hours = int(body.get("timeframe_hours", 24))
        trigger = body.get("trigger", "both")
        if trigger not in ("both", "time", "price_level"):
            raise HTTPException(status_code=400, detail="trigger must be 'both', 'time', or 'price_level'")
        execute = body.get("execute", "yes")
        if execute not in ("yes", "no"):
            execute = "yes"

        em = _get_db_manager()
        ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with em._connect() as con:
            existing = con.execute(
                "SELECT 1 FROM method_config WHERE method=?", (method,)
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail=f"Method '{method}' already exists")
            con.execute(
                "INSERT INTO method_config(method, timeframe_hours, trigger, active, execute) VALUES (?,?,?,1,?)",
                (method, timeframe_hours, trigger, execute),
            )
            con.execute(
                "INSERT OR IGNORE INTO prompt_templates(method, prompt_text, updated_at) VALUES (?,?,?)",
                (method, "", ts),
            )
        logger.info(f"Created new method: {method}")
        return {"method": method, "timeframe_hours": timeframe_hours, "trigger": trigger, "execute": execute}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating method_config")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/method-config/{method}", dependencies=[Depends(verify_api_key)])
async def update_method_config(method: str, body: dict = Body(...)):
    """Update timeframe_hours / trigger / active for a method."""
    try:
        em = _get_db_manager()
        allowed = {"timeframe_hours", "trigger", "active"}
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            raise HTTPException(status_code=400, detail="No valid fields provided")
        set_parts = ", ".join(f"{k}=?" for k in updates)
        params = list(updates.values()) + [method]
        with em._connect() as con:
            cur = con.execute(
                f"UPDATE method_config SET {set_parts} WHERE method=?", params
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Method '{method}' not found")
        return {"method": method, "updated": updates}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating method_config")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Execute field management endpoints
# ---------------------------------------------------------------------------

@router.put("/method-config/{method}/execute", dependencies=[Depends(verify_api_key)])
async def update_method_execute(method: str, execute: str = Body(..., embed=True)):
    """Update execute flag for a method ('yes' or 'no')."""
    try:
        if execute not in ("yes", "no"):
            raise HTTPException(status_code=400, detail="execute must be 'yes' or 'no'")
        
        em = _get_db_manager()
        with em._connect() as con:
            cur = con.execute(
                "UPDATE method_config SET execute=? WHERE method=?", 
                (execute, method)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Method '{method}' not found")
        
        logger.info(f"Updated method {method} execute={execute}")
        return {"method": method, "execute": execute}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating method execute")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/providers/{provider}/execute", dependencies=[Depends(verify_api_key)])
async def update_provider_execute(provider: str, execute: str = Body(..., embed=True)):
    """Update execute flag for a provider ('yes' or 'no')."""
    try:
        if execute not in ("yes", "no"):
            raise HTTPException(status_code=400, detail="execute must be 'yes' or 'no'")
        
        em = _get_db_manager()
        with em._connect() as con:
            cur = con.execute(
                "UPDATE providers SET execute=? WHERE name=?", 
                (execute, provider)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
        
        logger.info(f"Updated provider {provider} execute={execute}")
        return {"provider": provider, "execute": execute}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating provider execute")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/method-config/{method}", dependencies=[Depends(verify_api_key)])
async def get_method_config_detail(method: str):
    """Return detailed configuration for a specific method including execute flag."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            row = con.execute(
                "SELECT * FROM method_config WHERE method=?", 
                (method,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Method '{method}' not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching method config")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers/{provider}", dependencies=[Depends(verify_api_key)])
async def get_provider_detail(provider: str):
    """Return detailed configuration for a specific provider including execute flag."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            row = con.execute(
                "SELECT * FROM providers WHERE name=?", 
                (provider,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching provider config")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Heartbeat log endpoint
# ---------------------------------------------------------------------------

@router.get("/heartbeat/history", dependencies=[Depends(verify_api_key)])
async def get_heartbeat_history(limit: int = Query(50, ge=1, le=500)):
    """Return recent heartbeat log entries."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            rows = con.execute(
                "SELECT * FROM heartbeat_log ORDER BY checked_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.exception("Error fetching heartbeat history")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Tickets endpoints
# ---------------------------------------------------------------------------

@router.get("/tickets", dependencies=[Depends(verify_api_key)])
async def get_tickets(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
    portfolio: Optional[int] = None,
    limit: int = Query(200, ge=1, le=2000),
):
    """Return tickets list with optional filters."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            clauses = []
            params: list = []
            if ticker:
                clauses.append("UPPER(ticker)=UPPER(?)")
                params.append(ticker)
            if status:
                clauses.append("UPPER(status)=UPPER(?)")
                params.append(status)
            if portfolio is not None:
                clauses.append("portfolio=?")
                params.append(portfolio)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = con.execute(
                f"SELECT * FROM tickets {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        logger.exception("Error fetching tickets")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets", dependencies=[Depends(verify_api_key)])
async def create_ticket(body: dict = Body(...)):
    """Create a new ticket. Required: ticker. Optional: action, quantity, price, status, portfolio, notes."""
    try:
        em = _get_db_manager()
        ticker = (body.get("ticker") or "").strip()
        if not ticker:
            raise HTTPException(status_code=422, detail="ticker is required")
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        row = {
            "ticker":    ticker,
            "created_at": now,
            "action":    body.get("action", ""),
            "quantity":  float(body.get("quantity") or 0),
            "price":     float(body.get("price") or 0),
            "status":    body.get("status", "NEW"),
            "portfolio": int(body.get("portfolio") or 0),
            "notes":     body.get("notes", ""),
        }
        cols = list(row.keys())
        ph = ", ".join(["?"] * len(cols))
        with em._connect() as con:
            cur = con.execute(
                f"INSERT INTO tickets ({', '.join(cols)}) VALUES ({ph})",
                list(row.values()),
            )
            new_id = cur.lastrowid
        return {"id": new_id, **row}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating ticket")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tickets/{ticket_id}", dependencies=[Depends(verify_api_key)])
async def update_ticket(ticket_id: int, body: dict = Body(...)):
    """Update ticket fields (status, notes, action, quantity, price, portfolio)."""
    allowed = {"status", "notes", "action", "quantity", "price", "portfolio"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    try:
        em = _get_db_manager()
        with em._connect() as con:
            row = con.execute("SELECT id FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Ticket not found")
            set_parts = ", ".join(f"{k}=?" for k in updates)
            con.execute(
                f"UPDATE tickets SET {set_parts} WHERE id=?",
                list(updates.values()) + [ticket_id],
            )
        return {"updated": True, "id": ticket_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating ticket")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tickets/{ticket_id}", dependencies=[Depends(verify_api_key)])
async def delete_ticket(ticket_id: int):
    """Delete a ticket by id."""
    try:
        em = _get_db_manager()
        with em._connect() as con:
            row = con.execute("SELECT id FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Ticket not found")
            con.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
        return {"deleted": True, "id": ticket_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting ticket")
        raise HTTPException(status_code=500, detail=str(e))
