"""Unit tests for forecast JSON parsing helpers."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from forecast_engine import (  # noqa: E402
    _sanitize_json_numeric_expressions,
    parse_json_response,
)


class TestSanitizeJsonNumericExpressions:
    def test_replaces_multiplication_in_json(self):
        raw = '{"entry_limit_price": 76444.00 * 0.97, "stop_loss": 76444.00 * 1.03}'
        sanitized = _sanitize_json_numeric_expressions(raw)
        data = json.loads(sanitized)
        assert abs(data["entry_limit_price"] - 76444.00 * 0.97) < 0.01
        assert abs(data["stop_loss"] - 76444.00 * 1.03) < 0.01

    def test_parse_json_response_with_expressions(self):
        text = """```json
{
    "confidence": 68,
    "side": "SHORT",
    "rationale": "test",
    "entry_limit_price": 100.0 * 0.97,
    "target_price": 100.0 * 0.88,
    "stop_loss": 100.0 * 1.03
}
```"""
        result = parse_json_response(text)
        assert result is not None
        assert result["side"] == "SHORT"
        assert result["entry_limit_price"] == 97.0
        assert result["stop_loss"] == 103.0
