"""Pipeline framework for per-ticker forecast processing."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple


@dataclass
class PipelineContext:
    ticker: str
    db_manager: Any
    run_id: Optional[int] = None
    client: Any = None
    price_data: List[dict] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    methods: List[str] = field(default_factory=list)
    raw_forecasts: List[dict] = field(default_factory=list)
    log_ids: List = field(default_factory=list)
    consensus: Optional[dict] = None
    has_consensus: bool = False
    skipped_forecast_exposure: bool = False


class PipelineStage(Protocol):
    def run(self, ctx: PipelineContext) -> None: ...


class ForecastPipeline:
    def __init__(self, stages: List[PipelineStage]):
        self._stages = stages

    def run(self, ticker: str, db_manager, run_id=None, client=None) -> Tuple[List, bool]:
        ctx = PipelineContext(
            ticker=ticker,
            db_manager=db_manager,
            run_id=run_id,
            client=client,
        )
        for stage in self._stages:
            stage.run(ctx)
        return ctx.log_ids, ctx.has_consensus
