"""MetaLabelStage — ML gate between consensus and order activation."""

from __future__ import annotations

import json
import logging

from scripts.core.meta_label.config import load_meta_label_config
from scripts.core.meta_label.features import build_meta_features, features_to_vector
from scripts.core.meta_label.model_loader import load_model_bundle, predict_proba
from scripts.core.meta_label.perp_snapshot import fetch_ticker_snapshot, save_perp_snapshot
from scripts.core.pipeline.base import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class MetaLabelStage:
    def run(self, ctx: PipelineContext) -> None:
        if not ctx.consensus or not ctx.has_consensus:
            return

        cfg = load_meta_label_config(ctx.db_manager)
        if not cfg.enabled:
            return

        signal = str(ctx.consensus.get("signal") or "").upper()
        if signal not in ("LONG", "SHORT"):
            return

        consensus_id = ctx.db_manager.get_last_consensus_id(ctx.ticker)
        if not consensus_id:
            logger.warning("MetaLabelStage: no consensus id for %s", ctx.ticker)
            return

        sector = ""
        try:
            with ctx.db_manager._connect() as con:
                row = con.execute(
                    "SELECT sector FROM settings WHERE ticker = ?", (ctx.ticker,)
                ).fetchone()
                if row:
                    sector = row[0] or ""
        except Exception:
            pass

        perp_snap = fetch_ticker_snapshot(ctx.ticker)
        if perp_snap:
            save_perp_snapshot(ctx.db_manager, consensus_id, ctx.ticker, perp_snap)

        horizon = ctx.consensus.get("horizon_hours")
        ctx.consensus["ticker"] = ctx.ticker
        features = build_meta_features(
            consensus=ctx.consensus,
            indicators=ctx.indicators,
            price_data=ctx.price_data,
            db_manager=ctx.db_manager,
            run_id=ctx.run_id,
            sector=sector,
            perp_snap=perp_snap,
            horizon_hours=horizon,
        )
        vector = features_to_vector(features)

        score = 0.5
        bundle = load_model_bundle(cfg.model_path) if cfg.model_path else None
        if bundle:
            score = predict_proba(bundle, vector)
        else:
            logger.debug("MetaLabelStage: no model at %s — using score=0.5", cfg.model_path)

        decision = "PASS" if score >= cfg.threshold else "REJECT"
        ctx.meta_score = score
        ctx.meta_decision = decision
        ctx.meta_model_version = cfg.model_version or (cfg.model_path or "")
        ctx.meta_features = features

        self._persist_meta(ctx, consensus_id, score, decision, cfg.model_version, features)

        if decision == "REJECT" and cfg.enforce:
            ctx.meta_order_blocked = True
            try:
                from datetime import datetime, timezone

                ts = datetime.now(tz=timezone.utc).isoformat()
                ctx.db_manager.consensus_repo.mark_order_skipped(
                    consensus_id, f"meta_label_reject score={score:.3f}", ts
                )
            except Exception as e:
                logger.warning("MetaLabelStage: mark_order_skipped failed: %s", e)
            logger.info(
                "MetaLabelStage: REJECT %s id=%s score=%.3f < %.3f",
                ctx.ticker,
                consensus_id,
                score,
                cfg.threshold,
            )
        else:
            logger.info(
                "MetaLabelStage: %s %s id=%s score=%.3f threshold=%.3f enforce=%s",
                decision,
                ctx.ticker,
                consensus_id,
                score,
                cfg.threshold,
                cfg.enforce,
            )

    @staticmethod
    def _persist_meta(ctx, consensus_id, score, decision, version, features):
        try:
            with ctx.db_manager._connect() as con:
                con.execute(
                    """
                    UPDATE consensus SET
                        meta_score = ?,
                        meta_decision = ?,
                        meta_model_version = ?,
                        meta_features_json = ?
                    WHERE id = ?
                    """,
                    (
                        score,
                        decision,
                        version or "",
                        json.dumps(features, ensure_ascii=False),
                        consensus_id,
                    ),
                )
        except Exception as e:
            logger.warning("MetaLabelStage: persist meta fields failed: %s", e)
