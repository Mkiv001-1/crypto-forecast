"""Tests for crypto-native market context."""

import json
from unittest.mock import patch

from scripts.core.market_context import (
    fetch_market_context,
    format_market_context,
    _fetch_bybit_daily_closes,
    _fetch_bybit_ticker_snapshot,
)


def _kline_payload(closes_oldest_to_newest):
    """Build Bybit kline list (newest candle first)."""
    rows_newest_first = []
    ts = 1_700_000_000_000 + (len(closes_oldest_to_newest) - 1) * 86_400_000
    for close in reversed(closes_oldest_to_newest):
        rows_newest_first.append([str(ts), "1", "2", "0.5", str(close), "100", "1000"])
        ts -= 86_400_000
    return {"retCode": 0, "result": {"list": rows_newest_first}}


def _ticker_payload(change_24h=0.02, funding=0.0001):
    return {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "price24hPcnt": str(change_24h),
                    "fundingRate": str(funding),
                }
            ]
        },
    }


class TestMarketContextFetch:
    @patch("scripts.core.market_context.urlopen")
    def test_fetch_market_context_bybit(self, mock_urlopen):
        responses = [
            _kline_payload([100, 101, 102, 103, 104, 110]),  # BTC (6 bars for 5d)
            _kline_payload([50, 51, 52, 53, 54, 55]),      # ETH
            _ticker_payload(),
        ]

        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def getcode(self):
                return 200

            def read(self):
                return json.dumps(self._payload).encode()

        mock_urlopen.side_effect = [_Resp(p) for p in responses]

        ctx = fetch_market_context()
        assert ctx["btc_change_1d"] is not None
        assert ctx["btc_change_5d"] is not None
        assert ctx["eth_change_1d"] is not None
        assert ctx["btc_funding_rate_pct"] is not None
        assert ctx["risk_sentiment"] in ("risk-on", "risk-off", "neutral")

        text = format_market_context(ctx)
        assert "BTCUSDT" in text
        assert "ETHUSDT" in text
        assert "funding" in text.lower()

    @patch("scripts.core.market_context._bybit_public_get", return_value=None)
    def test_format_empty_context(self, _mock_get):
        assert format_market_context({}) == "Crypto market context unavailable"

    @patch("scripts.core.market_context._bybit_public_get")
    def test_daily_closes_parsing(self, mock_get):
        mock_get.return_value = _kline_payload([90, 95, 100])["result"]
        closes = _fetch_bybit_daily_closes("BTCUSDT", days=5)
        assert closes == [90.0, 95.0, 100.0]

    @patch("scripts.core.market_context._bybit_public_get")
    def test_ticker_snapshot(self, mock_get):
        mock_get.return_value = _ticker_payload()["result"]
        snap = _fetch_bybit_ticker_snapshot("BTCUSDT")
        assert snap is not None
        assert "change_24h_pct" in snap
        assert "funding_rate_pct" in snap
