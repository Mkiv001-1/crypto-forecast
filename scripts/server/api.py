"""FastAPI application factory and lifespan."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scripts.core.app_context import get_db_manager
from scripts.server import dependencies as deps
from scripts.server.config import ServerConfig
from scripts.server.routers.endpoints import router as endpoints_router
from scripts.server.routers.orders import router as orders_router
from scripts.server.routers.forecast import router as forecast_router
from scripts.server.routers.scheduler_routes import router as scheduler_router
from scripts.shared.security import mask_secret

logger = logging.getLogger(__name__)


async def _startup_background_services() -> None:
    """Heavy startup (Bybit, scheduler, backfill) — must not block HTTP bind."""
    db = get_db_manager()
    try:
        from scripts.core.bybit_worker import start_bybit_worker

        await start_bybit_worker(db)
        logger.info("Bybit worker started")
    except Exception as e:
        logger.warning("Bybit worker startup failed (non-fatal): %s", e)

    try:
        from scripts.core.scheduler import start_scheduler

        await start_scheduler(db)
        logger.info("Scheduler started")
    except Exception as e:
        logger.warning("Scheduler startup failed (non-fatal): %s", e)

    try:
        from scripts.core.scheduler import run_startup_price_data_backfill

        logger.info("startup: checking price data freshness...")
        await run_startup_price_data_backfill()
    except Exception as e:
        logger.warning("startup: price data backfill failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    deps.init_server_state(ServerConfig())
    cfg = deps.get_config()
    logger.info("Server started on %s:%s", cfg.host, cfg.port)
    logger.info("DB file: %s", cfg.db_file)
    logger.info("API Key: %s", mask_secret(cfg.api_key))

    try:
        rows = get_db_manager().mark_stuck_forecast_runs_failed()
        if rows:
            logger.info("startup: marked %s stuck forecast_run(s) as failed", rows)
    except Exception as e:
        logger.warning("startup: cleanup stuck runs failed: %s", e)

    startup_task = asyncio.create_task(
        _startup_background_services(), name="server-background-startup"
    )

    yield

    if not startup_task.done():
        startup_task.cancel()
        try:
            await startup_task
        except asyncio.CancelledError:
            pass

    try:
        from scripts.core.bybit_worker import stop_bybit_worker

        await stop_bybit_worker()
        logger.info("Bybit worker stopped")
    except Exception as e:
        logger.warning("Bybit worker shutdown error: %s", e)

    try:
        from scripts.core.scheduler import stop_scheduler

        await stop_scheduler()
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.warning("Scheduler shutdown error: %s", e)

    logger.info("Server shutting down")


app = FastAPI(
    title="Forecast Trading Robot API",
    description="API for forecast trading robot management",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints_router)
app.include_router(orders_router)
app.include_router(forecast_router)
app.include_router(scheduler_router)
