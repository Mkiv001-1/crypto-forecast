"""Config value validation for API updates."""

from fastapi import HTTPException


def validate_config_value(key: str, value: str) -> None:
    """Raise HTTPException(400) if the value is out of acceptable range."""
    float_ranges = {
        "DEFAULT_RISK_PCT": (0.0001, 0.5),
        "MAX_POSITION_PCT": (0.001, 1.0),
        "MAX_SECTOR_EXPOSURE_PCT": (0.01, 1.0),
        "MAX_SECTOR_HARD_LIMIT_PCT": (0.01, 1.0),
        "SECTOR_OVERWEIGHT_FACTOR": (0.01, 1.0),
        "RISK_PERCENT_ON_STOP": (0.1, 10.0),
        "CONFIDENCE_THRESHOLD": (0.0, 100.0),
        "DISAGREEMENT_THRESHOLD": (0.0, 1.0),
        "MIN_EXPECTED_R": (0.0, 10.0),
        "CONSENSUS_MAX_DEVIATION": (0.01, 1.0),
        "KELLY_FRACTION": (0.01, 1.0),
    }
    int_ranges = {
        "MIN_MODELS_FOR_SIDE": (1, 20),
    }
    bool_keys = {
        "LIVE_TRADING_CONFIRMED",
        "USE_STOP_LIMIT",
        "ALLOW_EXTENDED_HOURS",
        "AUTO_BLOCK_ON_ROLLBACK_FAIL",
        "OPENROUTER_FREE_ONLY",
        "ADVERSARIAL_PROMPT_ENABLED",
    }
    json_keys = {
        "REGIME_CONSENSUS_OVERRIDES",
    }
    choice_keys = {
        "RISK_MODE": {"percent_of_capital", "percent_of_portfolio_on_stop", "kelly_fractional"},
        "BYBIT_CAPITAL_FAILSAFE": {"manual_only", "deny"},
        "IB_CAPITAL_FAILSAFE": {"manual_only", "deny"},
        "ORDER_MODE": {"disabled", "paper", "live"},
        "PREFERRED_ACCOUNT_TYPE": {"live", "paper"},
    }

    if key in float_ranges:
        lo, hi = float_ranges[key]
        try:
            v = float(value)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"{key}: expected a number, got {value!r}")
        if not (lo <= v <= hi):
            raise HTTPException(status_code=400, detail=f"{key}: value {v} out of range [{lo}, {hi}]")

    elif key in int_ranges:
        lo, hi = int_ranges[key]
        try:
            v = int(float(value))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"{key}: expected an integer, got {value!r}")
        if not (lo <= v <= hi):
            raise HTTPException(status_code=400, detail=f"{key}: value {v} out of range [{lo}, {hi}]")

    elif key in json_keys:
        import json

        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=f"{key}: invalid JSON")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail=f"{key}: must be a JSON object")

    elif key in bool_keys:
        if value.lower() not in ("true", "false", ""):
            raise HTTPException(status_code=400, detail=f"{key}: expected 'true' or 'false', got {value!r}")

    elif key in choice_keys:
        choices = choice_keys[key]
        if value and value not in choices:
            raise HTTPException(status_code=400, detail=f"{key}: must be one of {sorted(choices)}, got {value!r}")

    elif key == "MANUAL_CAPITAL_OVERRIDE":
        if value.strip():
            try:
                v = float(value)
                if v <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"{key}: must be a positive number or empty")

    elif key == "RISK_ACCOUNT_ID":
        if value != value.strip():
            raise HTTPException(status_code=400, detail=f"{key}: must not have leading/trailing whitespace")
