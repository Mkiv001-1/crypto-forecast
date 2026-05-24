"""Pipeline integration: consensus stage uses regime settings."""

from unittest.mock import MagicMock, patch

from scripts.core.pipeline.base import PipelineContext
from scripts.core.pipeline.stages import ConsensusStage


def test_consensus_stage_passes_regime_settings():
    ctx = PipelineContext(
        ticker="BTCUSDT",
        db_manager=MagicMock(),
        indicators={"market_regime": "RANGING"},
        price_data=[{"close": 100.0}],
        raw_forecasts=[
            {
                "side": "LONG",
                "confidence": 80,
                "method": "momentum_trend",
                "model": "a",
                "entry_limit_price": 100,
                "target_price": 108,
                "stop_loss": 97,
            },
            {
                "side": "LONG",
                "confidence": 80,
                "method": "price_action",
                "model": "b",
                "entry_limit_price": 100,
                "target_price": 108,
                "stop_loss": 97,
            },
        ],
        log_ids={},
        run_id=1,
    )
    ctx.db_manager.get_providers_ema_accuracy.return_value = {}
    ctx.db_manager.get_method_config_timeframes.return_value = {}

    with patch("scripts.core.unified_logs_manager.get_forecast_statistics") as mock_stats:
        mock_stats.return_value = {"accuracy": {}, "methods": {}}
        with patch("scripts.core.consensus.save_consensus", return_value=True):
            with patch("scripts.core.consensus_settings.load_consensus_settings") as mock_load:
                from scripts.core.consensus_settings import ConsensusSettings

                mock_load.return_value = ConsensusSettings(
                    confidence_threshold=50,
                    min_models_for_side=2,
                    min_expected_r=0.1,
                    market_regime="RANGING",
                )
                ConsensusStage().run(ctx)

    mock_load.assert_called_once()
    assert mock_load.call_args[0][0] == ctx.db_manager
    assert mock_load.call_args[1]["market_regime"] == "RANGING"
    assert ctx.consensus is not None
    assert ctx.consensus.get("market_regime") == "RANGING"
