"""Feature vector for meta-label model (train + inference)."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

# Fixed column order for sklearn pipeline parity
FEATURE_NAMES: List[str] = [
    "confidence",
    "expected_r",
    "high_model_disagreement",
    "models_long_count",
    "models_short_count",
    "minority_weight_pct",
    "signal_is_long",
    "rr_ratio",
    "horizon_hours",
    "rsi14",
    "adx14",
    "atr_pct",
    "bb_position",
    "macd_hist",
    "volume_ratio",
    "ret_1d",
    "ret_5d",
    "range_pct_last",
    "vol_zscore_5",
    "is_major",
    "sector_hash",
    "ema_accuracy_mean",
    "ema_accuracy_min",
    "final_weight_sum",
    "n_links",
    "funding_rate_pct",
    "mark_index_premium_bps",
]


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _sector_hash(sector: str) -> float:
    s = (sector or "").strip().lower()
    if not s:
        return 0.0
    return float(hash(s) % 1000) / 1000.0


def _candle_features(price_data: List[dict]) -> Dict[str, float]:
    out = {
        "ret_1d": 0.0,
        "ret_5d": 0.0,
        "range_pct_last": 0.0,
        "vol_zscore_5": 0.0,
    }
    if not price_data:
        return out

    candles = price_data[-5:] if len(price_data) >= 5 else price_data
    closes = [_safe_float(c.get("close")) for c in candles]
    if len(closes) >= 2 and closes[-2] > 0:
        out["ret_1d"] = round((closes[-1] - closes[-2]) / closes[-2] * 100, 4)

    if len(price_data) >= 6:
        c0 = _safe_float(price_data[-6].get("close"))
        if c0 > 0:
            out["ret_5d"] = round((closes[-1] - c0) / c0 * 100, 4)

    last = candles[-1]
    close = _safe_float(last.get("close"), 1.0)
    high = _safe_float(last.get("high"))
    low = _safe_float(last.get("low"))
    if close > 0:
        out["range_pct_last"] = round((high - low) / close * 100, 4)

    vols = [_safe_float(c.get("volume")) for c in candles]
    if vols:
        mean_v = sum(vols) / len(vols)
        std_v = (sum((v - mean_v) ** 2 for v in vols) / len(vols)) ** 0.5
        if std_v > 0:
            out["vol_zscore_5"] = round((vols[-1] - mean_v) / std_v, 4)

    return out


def _link_aggregates(db_manager, run_id: Optional[int]) -> Dict[str, float]:
    out = {
        "ema_accuracy_mean": 0.5,
        "ema_accuracy_min": 0.5,
        "final_weight_sum": 0.0,
        "n_links": 0.0,
    }
    if not run_id or db_manager is None:
        return out
    try:
        with db_manager._connect() as con:
            rows = con.execute(
                """
                SELECT ema_accuracy, final_weight FROM forecast_run_links
                WHERE run_id = ?
                """,
                (int(run_id),),
            ).fetchall()
    except Exception:
        return out

    if not rows:
        return out

    emas = [_safe_float(r[0], 0.5) for r in rows]
    weights = [_safe_float(r[1]) for r in rows]
    out["ema_accuracy_mean"] = round(sum(emas) / len(emas), 4)
    out["ema_accuracy_min"] = round(min(emas), 4)
    out["final_weight_sum"] = round(sum(weights), 4)
    out["n_links"] = float(len(rows))
    return out


def build_meta_features(
    *,
    consensus: dict,
    indicators: Optional[dict] = None,
    price_data: Optional[List[dict]] = None,
    db_manager=None,
    run_id: Optional[int] = None,
    sector: str = "",
    perp_snap: Optional[dict] = None,
    horizon_hours: Optional[int] = None,
) -> Dict[str, float]:
    """Build feature dict keyed by FEATURE_NAMES."""
    ind = indicators or {}
    cons = consensus or {}
    signal = str(cons.get("signal") or "NEUTRAL").upper()

    price = _safe_float(ind.get("price") or cons.get("entry_limit_price"), 1.0)
    target = _safe_float(cons.get("target_price"))
    stop = _safe_float(cons.get("stop_loss"))
    rr = 0.0
    if price > 0 and target and stop:
        risk = abs(price - stop)
        reward = abs(target - price)
        if risk > 0:
            rr = round(reward / risk, 4)

    bb_u = _safe_float(ind.get("bb_upper"))
    bb_l = _safe_float(ind.get("bb_lower"))
    bb_pos = 0.5
    if bb_u > bb_l and price > 0:
        bb_pos = round((price - bb_l) / (bb_u - bb_l), 4)

    atr = _safe_float(ind.get("atr14"))
    atr_pct = round(atr / price * 100, 4) if price > 0 else 0.0

    vol_avg = _safe_float(ind.get("volume_avg_20"), 1.0)
    vol_cur = _safe_float(ind.get("volume_current"))
    vol_ratio = round(vol_cur / vol_avg, 4) if vol_avg > 0 else 0.0

    ticker = str(cons.get("ticker") or ind.get("ticker") or "")
    is_major = 1.0 if ticker.upper() in ("BTCUSDT", "ETHUSDT") else 0.0

    h = horizon_hours
    if h is None:
        h = cons.get("horizon_hours")
    try:
        h = int(h) if h is not None else 24
    except (TypeError, ValueError):
        h = 24

    feats = {
        "confidence": _safe_float(cons.get("confidence")),
        "expected_r": _safe_float(cons.get("expected_r")),
        "high_model_disagreement": float(bool(cons.get("high_model_disagreement"))),
        "models_long_count": _safe_float(cons.get("models_long_count")),
        "models_short_count": _safe_float(cons.get("models_short_count")),
        "minority_weight_pct": _safe_float(cons.get("minority_weight_pct")),
        "signal_is_long": 1.0 if signal == "LONG" else 0.0,
        "rr_ratio": rr,
        "horizon_hours": float(h),
        "rsi14": _safe_float(ind.get("rsi14")),
        "adx14": _safe_float(ind.get("adx14")),
        "atr_pct": atr_pct,
        "bb_position": bb_pos,
        "macd_hist": _safe_float(ind.get("macd_hist")),
        "volume_ratio": vol_ratio,
        "is_major": is_major,
        "sector_hash": _sector_hash(sector),
        "funding_rate_pct": _safe_float((perp_snap or {}).get("funding_rate_pct")),
        "mark_index_premium_bps": _safe_float((perp_snap or {}).get("mark_index_premium_bps")),
    }
    feats.update(_candle_features(price_data or []))
    feats.update(_link_aggregates(db_manager, run_id))

    return {k: feats.get(k, 0.0) for k in FEATURE_NAMES}


def features_to_vector(features: Dict[str, float]) -> List[float]:
    return [float(features.get(k, 0.0)) for k in FEATURE_NAMES]


def build_meta_features_from_consensus_row(row: dict, db_manager) -> Dict[str, float]:
    """Rebuild features from DB consensus row (export / replay)."""
    ticker = row.get("ticker", "")
    sector = ""
    try:
        with db_manager._connect() as con:
            srow = con.execute(
                "SELECT sector FROM settings WHERE ticker = ?", (ticker,)
            ).fetchone()
            if srow:
                sector = srow[0] or ""
    except Exception:
        pass

    perp_snap = None
    try:
        with db_manager._connect() as con:
            prow = con.execute(
                """
                SELECT funding_rate, mark_index_premium_bps FROM perp_market_snapshots
                WHERE consensus_id = ? ORDER BY id DESC LIMIT 1
                """,
                (int(row["id"]),),
            ).fetchone()
            if prow:
                fr = _safe_float(prow[0])
                perp_snap = {
                    "funding_rate_pct": round(fr * 100, 4),
                    "mark_index_premium_bps": _safe_float(prow[1]),
                }
    except Exception:
        pass

    stored = row.get("meta_features_json")
    if stored:
        try:
            parsed = json.loads(stored)
            if isinstance(parsed, dict) and parsed:
                return {k: _safe_float(parsed.get(k)) for k in FEATURE_NAMES}
        except json.JSONDecodeError:
            pass

    return build_meta_features(
        consensus=row,
        indicators={},
        price_data=[],
        db_manager=db_manager,
        run_id=row.get("run_id"),
        sector=sector,
        perp_snap=perp_snap,
        horizon_hours=row.get("horizon_hours"),
    )
