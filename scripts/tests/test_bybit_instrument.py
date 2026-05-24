"""Tests for Bybit instrument qty/price quantization."""

import pytest

from scripts.core.bybit_instrument import (
    decimals_from_step,
    format_bybit_decimal,
    normalize_order_params,
    quantize_price,
    quantize_qty,
)


class TestQuantizeQty:
    def test_sol_qty_step_one(self):
        assert quantize_qty(41.033307, 1.0) == 41.0

    def test_sol_qty_step_tenth(self):
        assert quantize_qty(41.033307, 0.1) == 41.0

    def test_eth_qty_step_hundredth(self):
        assert quantize_qty(2.905967, 0.01) == 2.9

    def test_below_min_raises(self):
        with pytest.raises(ValueError, match="below minOrderQty"):
            normalize_order_params(
                0.05,
                qty_step=0.1,
                min_order_qty=0.1,
                max_order_qty=1000.0,
            )


class TestQuantizePrice:
    def test_rounds_to_tick(self):
        assert quantize_price(85.381, 0.01) == 85.38


class TestFormatBybitDecimal:
    def test_eth_qty_string(self):
        assert format_bybit_decimal(2.9, 0.01) == "2.90"

    def test_integer_qty(self):
        assert format_bybit_decimal(41.0, 1.0) == "41"


class TestDecimalsFromStep:
    def test_hundredth(self):
        assert decimals_from_step(0.01) == 2

    def test_one(self):
        assert decimals_from_step(1.0) == 0
