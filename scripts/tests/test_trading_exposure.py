"""Tests for trading exposure guard and pending-order handling."""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# Mock pybit before bybit_order_manager import (same as test_bybit_order_manager)
class _FakeUnifiedTrading:
    class HTTP:
        def __init__(self, *args, **kwargs):
            pass


_fake_pybit = type(sys)("pybit")
_fake_pybit.unified_trading = _FakeUnifiedTrading
sys.modules.setdefault("pybit", _fake_pybit)
sys.modules.setdefault("pybit.unified_trading", _FakeUnifiedTrading)

from scripts.core.pipeline.base import PipelineContext
from scripts.core.pipeline.stages import ForecastStage, TradingExposureGuardStage
from scripts.core.trading_exposure import (
    skip_forecast_when_exposed,
    ticker_has_trading_exposure,
)


def test_ticker_has_trading_exposure_true(db_manager):
    with db_manager._connect() as con:
        con.execute(
            """INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
               VALUES ('ETHUSDT', 'oid-1', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')"""
        )
        con.commit()

    has_exp, reason = ticker_has_trading_exposure(db_manager, "ETHUSDT")
    assert has_exp is True
    assert reason == "open_order_or_position"


def test_ticker_has_trading_exposure_false(db_manager):
    has_exp, _ = ticker_has_trading_exposure(db_manager, "BTCUSDT")
    assert has_exp is False


def test_guard_skips_forecast_stage(db_manager):
    with db_manager._connect() as con:
        con.execute(
            """INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
               VALUES ('ETHUSDT', 'oid-2', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')"""
        )
        con.commit()

    ctx = PipelineContext(ticker="ETHUSDT", db_manager=db_manager, indicators={"x": 1}, methods=["m1"])
    TradingExposureGuardStage().run(ctx)
    assert ctx.skipped_forecast_exposure is True

    with patch(
        "scripts.core.multi_model_forecaster.generate_multi_model_forecasts",
        return_value=([{"side": "LONG"}], [1]),
    ) as gen:
        ForecastStage().run(ctx)
        gen.assert_not_called()


def test_forecast_runs_when_no_exposure(db_manager):
    ctx = PipelineContext(
        ticker="BTCUSDT",
        db_manager=db_manager,
        indicators={"x": 1},
        methods=["m1"],
        price_data=[{"close": 100}],
    )
    TradingExposureGuardStage().run(ctx)
    assert ctx.skipped_forecast_exposure is False

    with patch(
        "scripts.core.multi_model_forecaster.generate_multi_model_forecasts",
        return_value=([{"side": "LONG"}], [1]),
    ) as gen:
        ForecastStage().run(ctx)
        gen.assert_called_once()


def test_skip_forecast_config_disabled(db_manager):
    with db_manager._connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES ('SKIP_FORECAST_WHEN_EXPOSED', 'false')"
        )
        con.execute(
            """INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
               VALUES ('ETHUSDT', 'oid-3', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')"""
        )
        con.commit()

    assert skip_forecast_when_exposed(db_manager) is False
    ctx = PipelineContext(ticker="ETHUSDT", db_manager=db_manager, indicators={}, methods=[])
    TradingExposureGuardStage().run(ctx)
    assert ctx.skipped_forecast_exposure is False


def test_expire_stale_pending_orders(db_manager):
    old = (datetime.now(tz=timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
    with db_manager._connect() as con:
        con.execute(
            """INSERT INTO consensus (ticker, date, signal, confidence, order_state, eval_status)
               VALUES ('BTCUSDT', ?, 'LONG', 80.0, 'PENDING_ORDER', 'PENDING')""",
            (old,),
        )
        con.commit()

    n = db_manager.consensus_repo.expire_stale_pending_orders(240)
    assert n == 1

    with db_manager._connect() as con:
        row = con.execute("SELECT order_state, order_reason FROM consensus").fetchone()
    assert row[0] == "EXPIRED"
    assert row[1] == "forecast_ttl"


def test_save_consensus_skips_pending_when_exposure(db_manager):
    from scripts.core.consensus import save_consensus

    with db_manager._connect() as con:
        con.execute(
            """INSERT INTO orders (ticker, bybit_order_id, order_role, status, quantity, created_at)
               VALUES ('ETHUSDT', 'oid-4', 'ENTRY', 'SUBMITTED', 0.1, '2024-01-01')"""
        )
        con.commit()

    cons = {
        "signal": "LONG",
        "confidence": 75.0,
        "methods_long": "trend",
        "methods_short": "",
        "methods_neutral": "",
        "rationale": "test",
        "target_price": 110.0,
        "stop_loss": 90.0,
        "entry_limit_price": 100.0,
        "high_model_disagreement": False,
    }
    assert save_consensus(db_manager, "ETHUSDT", cons) is True

    with db_manager._connect() as con:
        row = con.execute(
            "SELECT order_state, order_reason FROM consensus WHERE ticker='ETHUSDT'"
        ).fetchone()
    assert row[0] == "ORDER_SKIPPED"
    assert row[1] == "existing_exposure"


def test_activate_marks_skipped_on_duplicate_order(db_manager):
    from scripts.core.bybit_order_manager import activate_consensus_order

    with db_manager._connect() as con:
        con.execute(
            """INSERT INTO consensus (
                ticker, date, signal, confidence, stop_loss, target_price,
                entry_limit_price, order_state, eval_status
            ) VALUES ('ETHUSDT', '2026-01-01', 'LONG', 80.0, 90.0, 110.0, 100.0,
                      'PENDING_ORDER', 'PENDING')"""
        )
        con.commit()
        cid = con.execute("SELECT id FROM consensus").fetchone()[0]

    with patch(
        "scripts.core.bybit_order_manager.submit_signal",
        return_value={
            "status": "REJECTED",
            "reason": "Open order already exists for ETHUSDT",
        },
    ):
        result = activate_consensus_order(cid, db_manager)

    assert result["status"] == "REJECTED"
    with db_manager._connect() as con:
        state = con.execute("SELECT order_state FROM consensus WHERE id=?", (cid,)).fetchone()[0]
    assert state == "ORDER_SKIPPED"
