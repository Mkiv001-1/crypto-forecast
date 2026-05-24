"""
Consensus aggregation settings loaded from SQLite config with optional per-regime overrides.

REGIME_CONSENSUS_OVERRIDES JSON example:
{
  "RANGING": {"confidence_threshold": 60, "min_expected_r": 0.6, "min_models_for_side": 3},
  "STRONG_UPTREND": {"min_models_for_side": 2}
}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Filter reason codes (persisted in consensus.filter_reasons JSON)
FILTER_ANOMALY = "ANOMALY_FILTERED"
FILTER_HIGH_DISAGREEMENT = "HIGH_DISAGREEMENT"
FILTER_LOW_CONFIDENCE = "LOW_CONFIDENCE"
FILTER_LOW_EXPECTED_R = "LOW_EXPECTED_R"
FILTER_INSUFFICIENT_AGREEMENT = "INSUFFICIENT_AGREEMENT"

DEFAULT_CONFIDENCE_THRESHOLD = 55.0
DEFAULT_DISAGREEMENT_THRESHOLD = 0.40
DEFAULT_MIN_EXPECTED_R = 0.5
DEFAULT_MAX_DEVIATION = 0.15
DEFAULT_MIN_MODELS_FOR_SIDE = 2
DEFAULT_ADVERSARIAL_PROMPT = True
DEFAULT_KELLY_FRACTION = 0.25


@dataclass
class ConsensusSettings:
    """Effective thresholds for one consensus calculation."""

    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    disagreement_threshold: float = DEFAULT_DISAGREEMENT_THRESHOLD
    min_expected_r: float = DEFAULT_MIN_EXPECTED_R
    max_deviation: float = DEFAULT_MAX_DEVIATION
    min_models_for_side: int = DEFAULT_MIN_MODELS_FOR_SIDE
    adversarial_prompt_enabled: bool = DEFAULT_ADVERSARIAL_PROMPT
    market_regime: Optional[str] = None
    regime_overrides_applied: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "disagreement_threshold": self.disagreement_threshold,
            "min_expected_r": self.min_expected_r,
            "max_deviation": self.max_deviation,
            "min_models_for_side": self.min_models_for_side,
            "adversarial_prompt_enabled": self.adversarial_prompt_enabled,
            "market_regime": self.market_regime,
            "regime_overrides_applied": self.regime_overrides_applied,
        }


def _parse_float(raw: str, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_int(raw: str, default: int) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _parse_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _load_regime_overrides(db_manager) -> Dict[str, Dict[str, Any]]:
    if db_manager is None:
        return {}
    try:
        raw = db_manager.get_config_value("REGIME_CONSENSUS_OVERRIDES", "{}")
        data = json.loads(raw or "{}")
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("consensus_settings: invalid REGIME_CONSENSUS_OVERRIDES: %s", exc)
    return {}


def load_consensus_settings(
    db_manager=None,
    market_regime: Optional[str] = None,
) -> ConsensusSettings:
    """Build effective settings from DB config and optional regime overrides."""
    if db_manager is not None:
        confidence = _parse_float(
            db_manager.get_config_value(
                "CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD)
            ),
            DEFAULT_CONFIDENCE_THRESHOLD,
        )
        disagreement = _parse_float(
            db_manager.get_config_value(
                "DISAGREEMENT_THRESHOLD", str(DEFAULT_DISAGREEMENT_THRESHOLD)
            ),
            DEFAULT_DISAGREEMENT_THRESHOLD,
        )
        min_expected_r = _parse_float(
            db_manager.get_config_value("MIN_EXPECTED_R", str(DEFAULT_MIN_EXPECTED_R)),
            DEFAULT_MIN_EXPECTED_R,
        )
        max_deviation = _parse_float(
            db_manager.get_config_value(
                "CONSENSUS_MAX_DEVIATION", str(DEFAULT_MAX_DEVIATION)
            ),
            DEFAULT_MAX_DEVIATION,
        )
        min_models = _parse_int(
            db_manager.get_config_value(
                "MIN_MODELS_FOR_SIDE", str(DEFAULT_MIN_MODELS_FOR_SIDE)
            ),
            DEFAULT_MIN_MODELS_FOR_SIDE,
        )
        adversarial = _parse_bool(
            db_manager.get_config_value(
                "ADVERSARIAL_PROMPT_ENABLED", str(DEFAULT_ADVERSARIAL_PROMPT).lower()
            ),
            DEFAULT_ADVERSARIAL_PROMPT,
        )
    else:
        confidence = DEFAULT_CONFIDENCE_THRESHOLD
        disagreement = DEFAULT_DISAGREEMENT_THRESHOLD
        min_expected_r = DEFAULT_MIN_EXPECTED_R
        max_deviation = DEFAULT_MAX_DEVIATION
        min_models = DEFAULT_MIN_MODELS_FOR_SIDE
        adversarial = DEFAULT_ADVERSARIAL_PROMPT

    settings = ConsensusSettings(
        confidence_threshold=confidence,
        disagreement_threshold=disagreement,
        min_expected_r=min_expected_r,
        max_deviation=max_deviation,
        min_models_for_side=max(1, min_models),
        adversarial_prompt_enabled=adversarial,
        market_regime=market_regime,
    )

    if db_manager and market_regime:
        overrides = _load_regime_overrides(db_manager).get(market_regime, {})
        applied: Dict[str, Any] = {}
        for key, value in overrides.items():
            if key == "confidence_threshold":
                settings.confidence_threshold = float(value)
                applied[key] = settings.confidence_threshold
            elif key == "disagreement_threshold":
                settings.disagreement_threshold = float(value)
                applied[key] = settings.disagreement_threshold
            elif key == "min_expected_r":
                settings.min_expected_r = float(value)
                applied[key] = settings.min_expected_r
            elif key == "max_deviation":
                settings.max_deviation = float(value)
                applied[key] = settings.max_deviation
            elif key == "min_models_for_side":
                settings.min_models_for_side = max(1, int(value))
                applied[key] = settings.min_models_for_side
        settings.regime_overrides_applied = applied

    return settings


def format_filter_reasons(reasons: List[str]) -> str:
    """Serialize filter reasons for DB storage."""
    return json.dumps(reasons or [], ensure_ascii=False)


def parse_filter_reasons(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []
