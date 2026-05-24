"""Load meta-label sklearn bundle from disk."""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_bundle_cache: dict = {}


def load_model_bundle(path: str) -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    if path in _bundle_cache:
        return _bundle_cache[path]

    try:
        import joblib
    except ImportError:
        logger.warning("meta_label: joblib not installed")
        return None

    try:
        bundle = joblib.load(path)
        if isinstance(bundle, dict) and "model" in bundle:
            _bundle_cache[path] = bundle
            return bundle
    except Exception as e:
        logger.warning("meta_label: failed to load %s: %s", path, e)
    return None


def predict_proba(bundle: dict, feature_vector: List[float]) -> float:
    """Return P(class=1)."""
    model = bundle.get("model")
    scaler = bundle.get("scaler")
    names = bundle.get("feature_names")

    import numpy as np

    x = np.array([feature_vector], dtype=float)
    if names and len(feature_vector) != len(names):
        logger.warning("meta_label: feature dim mismatch %s vs %s", len(feature_vector), len(names))

    if scaler is not None:
        try:
            x = scaler.transform(x)
        except Exception as e:
            logger.warning("meta_label: scaler transform failed: %s", e)

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x)[0]
        return float(proba[1]) if len(proba) > 1 else float(proba[0])

    pred = model.predict(x)
    return float(pred[0])
