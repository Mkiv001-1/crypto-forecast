"""Tests for consensus-related API config validation."""

import pytest
from fastapi import HTTPException

from scripts.server.config_validation import validate_config_value


def test_confidence_threshold_range():
    validate_config_value("CONFIDENCE_THRESHOLD", "55")
    with pytest.raises(HTTPException):
        validate_config_value("CONFIDENCE_THRESHOLD", "150")


def test_min_models_for_side_integer():
    validate_config_value("MIN_MODELS_FOR_SIDE", "3")
    with pytest.raises(HTTPException):
        validate_config_value("MIN_MODELS_FOR_SIDE", "0")


def test_regime_overrides_json():
    validate_config_value("REGIME_CONSENSUS_OVERRIDES", '{"RANGING": {"min_models_for_side": 3}}')
    with pytest.raises(HTTPException):
        validate_config_value("REGIME_CONSENSUS_OVERRIDES", "not-json")


def test_adversarial_bool():
    validate_config_value("ADVERSARIAL_PROMPT_ENABLED", "true")
    with pytest.raises(HTTPException):
        validate_config_value("ADVERSARIAL_PROMPT_ENABLED", "maybe")
