"""FastAPI dependencies and shared server state."""

import logging
import math
import os
from typing import List, Optional

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from scripts.core.app_context import get_db_manager, init_context, reset_context
from scripts.server.config import ServerConfig
from scripts.server.robot import RobotRunner
from scripts.shared.security import mask_secret

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_config: Optional[ServerConfig] = None
_runner: Optional[RobotRunner] = None


def get_config() -> ServerConfig:
    return _config


def get_runner() -> RobotRunner:
    return _runner


def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if not _config:
        raise HTTPException(status_code=503, detail="Server not initialized")
    if not api_key or api_key != _config.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return api_key


def init_server_state(config: ServerConfig) -> None:
    global _config, _runner
    reset_context()
    _config = config
    ctx = init_context(db_file=config.db_file, server_config=config)
    _runner = RobotRunner(config.db_file)
    ctx.set_runner(_runner)


def get_db():
    return get_db_manager()


def clean_record(record: dict) -> dict:
    import numpy as np

    out = {}
    for k, v in record.items():
        if isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = None if (isinstance(v, float) and math.isnan(v)) else float(v)
        elif isinstance(v, float) and math.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return out


def clean_records(records: list) -> list:
    return [clean_record(r) for r in records]


mask_secret = mask_secret  # re-export
