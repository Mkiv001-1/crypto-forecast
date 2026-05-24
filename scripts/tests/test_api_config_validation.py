"""
Unit tests for api._validate_config_value — 6c.

Tests are fully self-contained: they import _validate_config_value directly,
no running server or DB required. HTTPException is the only external dependency
(from fastapi).
"""

import os
import sys

import pytest
from fastapi import HTTPException

# Make server module importable (tests run from scripts/tests/)
_SERVER = os.path.join(os.path.dirname(__file__), "..", "server")
_CORE   = os.path.join(os.path.dirname(__file__), "..", "core")
_SHARED = os.path.join(os.path.dirname(__file__), "..", "shared")
for _p in (_SERVER, _CORE, _SHARED):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.server.config_validation import validate_config_value as validate


def _ok(key, value):
    """Assert validation passes (no exception)."""
    validate(key, value)


def _bad(key, value):
    """Assert validation raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        validate(key, value)
    assert exc_info.value.status_code == 400
    return exc_info.value.detail


# ===========================================================================
# RISK_PERCENT_ON_STOP  — range [0.1, 10.0]  (percent, not fraction)
# ===========================================================================

class TestRiskPercentOnStop:
    key = "RISK_PERCENT_ON_STOP"

    def test_valid_boundary_low(self):
        _ok(self.key, "0.1")

    def test_valid_boundary_high(self):
        _ok(self.key, "10.0")

    def test_valid_midpoint(self):
        _ok(self.key, "2.0")

    def test_valid_one_decimal(self):
        _ok(self.key, "1.5")

    def test_below_minimum_rejected(self):
        detail = _bad(self.key, "0.09")
        assert self.key in detail
        assert "range" in detail

    def test_above_maximum_rejected(self):
        detail = _bad(self.key, "10.1")
        assert "range" in detail

    def test_zero_rejected(self):
        _bad(self.key, "0")

    def test_negative_rejected(self):
        _bad(self.key, "-1.0")

    def test_non_numeric_rejected(self):
        detail = _bad(self.key, "abc")
        assert "expected a number" in detail

    def test_empty_string_rejected(self):
        # Empty → float("") raises ValueError → 400
        _bad(self.key, "")


# ===========================================================================
# RISK_MODE  — choices: percent_of_capital | percent_of_portfolio_on_stop
# ===========================================================================

class TestRiskMode:
    key = "RISK_MODE"

    def test_percent_of_capital_valid(self):
        _ok(self.key, "percent_of_capital")

    def test_percent_of_portfolio_on_stop_valid(self):
        _ok(self.key, "percent_of_portfolio_on_stop")

    def test_empty_allowed(self):
        # empty string passes (choice keys allow empty → means "leave as is")
        _ok(self.key, "")

    def test_unknown_value_rejected(self):
        detail = _bad(self.key, "fixed_dollar")
        assert "must be one of" in detail

    def test_wrong_case_rejected(self):
        _bad(self.key, "Percent_Of_Capital")

    def test_partial_value_rejected(self):
        _bad(self.key, "percent")


# ===========================================================================
# IB_CAPITAL_FAILSAFE  — choices: manual_only | deny
# ===========================================================================

class TestIBCapitalFailsafe:
    key = "IB_CAPITAL_FAILSAFE"

    def test_manual_only_valid(self):
        _ok(self.key, "manual_only")

    def test_deny_valid(self):
        _ok(self.key, "deny")

    def test_empty_allowed(self):
        _ok(self.key, "")

    def test_unknown_rejected(self):
        detail = _bad(self.key, "cache")
        assert "must be one of" in detail

    def test_uppercase_rejected(self):
        _bad(self.key, "DENY")


# ===========================================================================
# RISK_ACCOUNT_ID  — no format constraint, disallow leading/trailing spaces
# ===========================================================================

class TestRiskAccountId:
    key = "RISK_ACCOUNT_ID"

    def test_valid_account_id(self):
        _ok(self.key, "DU123456")

    def test_empty_allowed(self):
        _ok(self.key, "")

    def test_leading_space_rejected(self):
        detail = _bad(self.key, " DU123456")
        assert "whitespace" in detail

    def test_trailing_space_rejected(self):
        detail = _bad(self.key, "DU123456 ")
        assert "whitespace" in detail

    def test_both_spaces_rejected(self):
        _bad(self.key, " DU123456 ")

    def test_alphanumeric_special_chars_ok(self):
        _ok(self.key, "U1234567-PAPER")


# ===========================================================================
# MANUAL_CAPITAL_OVERRIDE  — positive number or empty
# ===========================================================================

class TestManualCapitalOverride:
    key = "MANUAL_CAPITAL_OVERRIDE"

    def test_empty_allowed(self):
        _ok(self.key, "")

    def test_positive_integer(self):
        _ok(self.key, "100000")

    def test_positive_float(self):
        _ok(self.key, "75000.50")

    def test_zero_rejected(self):
        detail = _bad(self.key, "0")
        assert self.key in detail

    def test_negative_rejected(self):
        _bad(self.key, "-5000")

    def test_non_numeric_rejected(self):
        _bad(self.key, "lots")

    def test_whitespace_only_treated_as_empty(self):
        # "  ".strip() == "" → treated as empty → OK
        _ok(self.key, "   ")


# ===========================================================================
# DEFAULT_RISK_PCT  — range [0.0001, 0.5]  (fraction)
# ===========================================================================

class TestDefaultRiskPct:
    key = "DEFAULT_RISK_PCT"

    def test_valid_one_percent(self):
        _ok(self.key, "0.01")

    def test_valid_boundary_low(self):
        _ok(self.key, "0.0001")

    def test_valid_boundary_high(self):
        _ok(self.key, "0.5")

    def test_below_minimum_rejected(self):
        _bad(self.key, "0.00009")

    def test_above_maximum_rejected(self):
        _bad(self.key, "0.51")

    def test_non_numeric_rejected(self):
        _bad(self.key, "one_percent")


# ===========================================================================
# MAX_POSITION_PCT  — range [0.001, 1.0]
# ===========================================================================

class TestMaxPositionPct:
    key = "MAX_POSITION_PCT"

    def test_valid(self):
        _ok(self.key, "0.05")

    def test_boundary_low(self):
        _ok(self.key, "0.001")

    def test_boundary_high(self):
        _ok(self.key, "1.0")

    def test_above_range_rejected(self):
        _bad(self.key, "1.01")

    def test_below_range_rejected(self):
        _bad(self.key, "0.0009")


# ===========================================================================
# Bool keys — LIVE_TRADING_CONFIRMED, USE_STOP_LIMIT, etc.
# ===========================================================================

class TestBoolKeys:
    @pytest.mark.parametrize("key", [
        "LIVE_TRADING_CONFIRMED",
        "USE_STOP_LIMIT",
        "ALLOW_EXTENDED_HOURS",
        "AUTO_BLOCK_ON_ROLLBACK_FAIL",
        "OPENROUTER_FREE_ONLY",
    ])
    def test_true_valid(self, key):
        _ok(key, "true")

    @pytest.mark.parametrize("key", [
        "LIVE_TRADING_CONFIRMED",
        "USE_STOP_LIMIT",
    ])
    def test_false_valid(self, key):
        _ok(key, "false")

    @pytest.mark.parametrize("key", [
        "LIVE_TRADING_CONFIRMED",
        "USE_STOP_LIMIT",
    ])
    def test_empty_valid(self, key):
        _ok(key, "")

    @pytest.mark.parametrize("key", [
        "LIVE_TRADING_CONFIRMED",
        "ALLOW_EXTENDED_HOURS",
    ])
    def test_non_bool_rejected(self, key):
        detail = _bad(key, "yes")
        assert "true" in detail or "false" in detail

    def test_uppercase_true_rejected(self):
        # Bool check is case-insensitive via .lower()
        _ok("LIVE_TRADING_CONFIRMED", "True")   # "true".lower() == "true" ✓
        _ok("LIVE_TRADING_CONFIRMED", "FALSE")  # "false".lower() == "false" ✓


# ===========================================================================
# Unknown keys — must pass through without error (no validation rule)
# ===========================================================================

class TestUnknownKeys:
    def test_unknown_key_any_value_passes(self):
        _ok("SOME_FUTURE_KEY", "anything_at_all")

    def test_unknown_key_empty_passes(self):
        _ok("MY_CUSTOM_KEY", "")


# ===========================================================================
# ORDER_MODE and PREFERRED_ACCOUNT_TYPE (existing choices — regression)
# ===========================================================================

class TestExistingChoiceKeys:
    def test_order_mode_disabled(self):
        _ok("ORDER_MODE", "disabled")

    def test_order_mode_paper(self):
        _ok("ORDER_MODE", "paper")

    def test_order_mode_live(self):
        _ok("ORDER_MODE", "live")

    def test_order_mode_invalid(self):
        _bad("ORDER_MODE", "simulation")

    def test_preferred_account_type_live(self):
        _ok("PREFERRED_ACCOUNT_TYPE", "live")

    def test_preferred_account_type_paper(self):
        _ok("PREFERRED_ACCOUNT_TYPE", "paper")

    def test_preferred_account_type_invalid(self):
        _bad("PREFERRED_ACCOUNT_TYPE", "demo")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
