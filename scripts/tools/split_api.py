"""One-off script to split api.py endpoints into routers/endpoints.py."""
from pathlib import Path

api = Path("scripts/server/api.py").read_text(encoding="utf-8")
marker = '@app.get("/health"'
start = api.index(marker)
endpoints = api[start:].replace("@app.", "@router.")

header = '''"""REST API route handlers."""

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


'''

# Replace global config/runner access
replacements = [
    ("_config.db_file", "deps.get_config().db_file"),
    ("_config.host", "deps.get_config().host"),
    ("_config.port", "deps.get_config().port"),
    ("_config.api_key", "deps.get_config().api_key"),
    ("_runner.start", "deps.get_runner().start"),
    ("_runner.status", "deps.get_runner().status"),
    ("_runner.message", "deps.get_runner().message"),
    ("_runner.started_at", "deps.get_runner().started_at"),
    ("_runner.finished_at", "deps.get_runner().finished_at"),
    ("_runner.duration_sec", "deps.get_runner().duration_sec"),
    ("_runner.get_log_lines", "deps.get_runner().get_log_lines"),
]
body = endpoints
for old, new in replacements:
    body = body.replace(old, new)

out = Path("scripts/server/routers/endpoints.py")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(header + body, encoding="utf-8")
print(f"Wrote {out} ({len(header) + len(body)} chars)")
