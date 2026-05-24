"""Forecast pipeline stages."""

import logging
from typing import List

from scripts.core.config import get_confidence_threshold
from scripts.core.pipeline.base import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class FetchDataStage:
    def run(self, ctx: PipelineContext) -> None:
        from scripts.core.bybit_data_loader import fetch_price_data_bybit as fetch_price_data

        price_data = fetch_price_data(
            ctx.ticker, days=250, db_manager=ctx.db_manager, client=ctx.client
        )
        if not price_data:
            raise ValueError("Не удалось загрузить данные о ценах")
        ctx.db_manager.save_price_data(price_data, ticker=ctx.ticker)
        ctx.price_data = price_data

        is_stale, last_date, hours_diff = ctx.db_manager.check_price_data_staleness(ctx.ticker)
        if is_stale and last_date:
            raise ValueError(
                f"Stale price data for {ctx.ticker}: last update {last_date} ({hours_diff}h ago)"
            )
        if is_stale:
            raise ValueError(f"No price data for {ctx.ticker}")


class IndicatorStage:
    def run(self, ctx: PipelineContext) -> None:
        from scripts.core.indicators import calculate_indicators, save_indicators

        indicators = calculate_indicators(ctx.ticker, ctx.price_data)
        if not indicators:
            raise ValueError("Не удалось рассчитать индикаторы")
        ctx.indicators = indicators


class RegimeStage:
    def run(self, ctx: PipelineContext) -> None:
        from scripts.core.market_regime import detect_regime, get_methods_for_regime
        from scripts.core.indicators import save_indicators

        regime = detect_regime(ctx.indicators)
        ctx.indicators["market_regime"] = regime
        ctx.methods = get_methods_for_regime(regime)
        logger.info("📈 Режим: %s → методы: %s", regime, ctx.methods)
        save_indicators(ctx.db_manager, ctx.indicators)


class TradingExposureGuardStage:
    """Skip LLM forecasts when ticker already has open order or position."""

    def run(self, ctx: PipelineContext) -> None:
        from scripts.core.trading_exposure import (
            skip_forecast_when_exposed,
            ticker_has_trading_exposure,
        )

        if not skip_forecast_when_exposed(ctx.db_manager):
            return

        has_exposure, reason = ticker_has_trading_exposure(ctx.db_manager, ctx.ticker)
        if not has_exposure:
            return

        ctx.skipped_forecast_exposure = True
        logger.info(
            "Skipping forecast for %s: %s (open order/position)",
            ctx.ticker,
            reason,
        )


class ForecastStage:
    def run(self, ctx: PipelineContext) -> None:
        if ctx.skipped_forecast_exposure:
            return

        from scripts.core.multi_model_forecaster import generate_multi_model_forecasts

        raw_forecasts, forecast_log_ids = generate_multi_model_forecasts(
            ctx.db_manager,
            ctx.ticker,
            ctx.indicators,
            ctx.methods,
            run_id=ctx.run_id,
            price_data=ctx.price_data,
        )
        ctx.raw_forecasts = raw_forecasts
        ctx.log_ids = forecast_log_ids
        logger.info("✅ Сгенерировано %s прогнозов для %s", len(raw_forecasts), ctx.ticker)


class ConsensusStage:
    def run(self, ctx: PipelineContext) -> None:
        if not ctx.raw_forecasts:
            return

        from scripts.core.consensus import calculate_consensus, save_consensus
        from scripts.core.consensus_settings import load_consensus_settings
        from scripts.core.unified_logs_manager import get_forecast_statistics

        stats = get_forecast_statistics(ctx.db_manager, days_back=30)
        accuracy = stats.get("accuracy", {})
        method_stats = {
            m: {"win_rate": accuracy.get(m, 50.0) / 100.0}
            for m in stats.get("methods", {})
        }
        method_timeframes = ctx.db_manager.get_method_config_timeframes()
        for m, hours in method_timeframes.items():
            if m not in method_stats:
                method_stats[m] = {}
            method_stats[m]["timeframe_hours"] = hours

        model_stats = ctx.db_manager.get_providers_ema_accuracy()
        current_price = ctx.price_data[-1]["close"] if ctx.price_data else 0.0
        market_regime = (ctx.indicators or {}).get("market_regime")
        consensus_settings = load_consensus_settings(ctx.db_manager, market_regime=market_regime)
        cons = calculate_consensus(
            ctx.raw_forecasts,
            method_stats,
            current_price=current_price,
            run_id=ctx.run_id,
            log_ids=ctx.log_ids,
            model_stats=model_stats,
            consensus_settings=consensus_settings,
            market_regime=market_regime,
        )
        save_consensus(
            ctx.db_manager, ctx.ticker, cons, method_stats=method_stats, run_id=ctx.run_id
        )
        ctx.consensus = cons
        ctx.has_consensus = cons["signal"] in ("LONG", "SHORT")
        logger.info("📊 Консенсус: %s %.1f%%", cons["signal"], cons["confidence"])


class OrderActivationStage:
    def run(self, ctx: PipelineContext) -> None:
        if not ctx.consensus or not ctx.has_consensus:
            return
        if getattr(ctx, "meta_order_blocked", False):
            return

        auto_order = (
            ctx.db_manager.get_config_value("AUTO_ORDER_SUBMISSION", "false").lower() == "true"
        )
        threshold = get_confidence_threshold(ctx.db_manager)
        if not auto_order or ctx.consensus["confidence"] < threshold:
            return

        try:
            from scripts.core.bybit_order_manager import activate_consensus_order

            consensus_id = ctx.db_manager.get_last_consensus_id(ctx.ticker)
            if consensus_id:
                result = activate_consensus_order(consensus_id, ctx.db_manager)
                logger.info(
                    "📤 Активация ордера: %s - %s",
                    result["status"],
                    result.get("message", ""),
                )
        except Exception as exc:
            logger.warning("⚠️ Ошибка немедленной активации ордера: %s", exc)


def build_default_pipeline() -> "ForecastPipeline":
    from scripts.core.meta_label.stage import MetaLabelStage
    from scripts.core.pipeline.base import ForecastPipeline

    return ForecastPipeline(
        [
            FetchDataStage(),
            IndicatorStage(),
            RegimeStage(),
            TradingExposureGuardStage(),
            ForecastStage(),
            ConsensusStage(),
            MetaLabelStage(),
            OrderActivationStage(),
        ]
    )
