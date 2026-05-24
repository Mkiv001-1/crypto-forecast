"""Runtime config for meta-labeling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetaLabelConfig:
    enabled: bool = False
    enforce: bool = False
    threshold: float = 0.55
    model_path: str = ""
    model_version: str = ""
    dataset_mode: bool = False


def load_meta_label_config(db_manager) -> MetaLabelConfig:
    def _cfg(key: str, default: str) -> str:
        try:
            v = db_manager.get_config_value(key)
            return v if v is not None and str(v).strip() != "" else default
        except Exception:
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(_cfg(key, str(default)))
        except ValueError:
            return default

    return MetaLabelConfig(
        enabled=_cfg("META_LABEL_ENABLED", "false").lower() == "true",
        enforce=_cfg("META_LABEL_ENFORCE", "false").lower() == "true",
        threshold=_float("META_LABEL_THRESHOLD", 0.55),
        model_path=_cfg("META_MODEL_PATH", ""),
        model_version=_cfg("META_MODEL_VERSION", ""),
        dataset_mode=_cfg("META_DATASET_MODE", "false").lower() == "true",
    )
