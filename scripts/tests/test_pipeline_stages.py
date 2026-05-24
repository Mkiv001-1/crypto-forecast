"""Unit tests for forecast pipeline stages."""

from unittest.mock import MagicMock, patch

from scripts.core.pipeline.base import PipelineContext
from scripts.core.pipeline.stages import ConsensusStage, FetchDataStage


def test_consensus_stage_skips_without_forecasts():
    ctx = PipelineContext(ticker="BTCUSDT", db_manager=MagicMock(), raw_forecasts=[])
    ConsensusStage().run(ctx)
    assert ctx.consensus is None


def test_fetch_data_stage_raises_on_empty_data():
    ctx = PipelineContext(ticker="BTCUSDT", db_manager=MagicMock())
    with patch(
        "scripts.core.bybit_data_loader.fetch_price_data_bybit",
        return_value=None,
    ):
        try:
            FetchDataStage().run(ctx)
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "Не удалось загрузить" in str(exc)
