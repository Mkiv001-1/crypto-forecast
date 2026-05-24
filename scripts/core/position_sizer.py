"""
Position sizer — calculates safe position size for a given signal.

Modes (controlled by RISK_MODE risk_settings key):

  percent_of_capital (default / legacy):
    risk = NetLiquidation × DEFAULT_RISK_PCT
    qty  = risk / |entry - stop_loss|
    Clamp to MAX_POSITION_PCT × NetLiquidation / entry

  percent_of_portfolio_on_stop:
    Portfolio value = NetLiquidation of the account set in RISK_ACCOUNT_ID (from Bybit).
    risk = portfolio_value × (RISK_PERCENT_ON_STOP / 100)
    qty  = risk / |entry - stop_loss|
    Clamp to MAX_POSITION_PCT × portfolio_value / entry
    Fail-safe controlled by BYBIT_CAPITAL_FAILSAFE (IB_CAPITAL_FAILSAFE alias).

Both modes apply sector correlation checks:
  > MAX_SECTOR_EXPOSURE_PCT  → qty × SECTOR_OVERWEIGHT_FACTOR
  > MAX_SECTOR_HARD_LIMIT_PCT → reject (SKIPPED_SECTOR_OVERWEIGHT)
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def _get_risk_setting(db_manager, key: str, default_value):
    """Get risk setting from risk_settings table."""
    try:
        import sqlite3
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT setting_value, setting_type FROM risk_settings WHERE setting_key = ?",
                (key,)
            ).fetchone()
            
            if row:
                value = row["setting_value"]
                setting_type = row["setting_type"]
                
                # Convert based on type
                if setting_type == "float":
                    return float(value)
                elif setting_type == "integer":
                    return int(value)
                else:
                    return value
            else:
                return default_value
    except Exception as e:
        logger.warning(f"position_sizer: Could not get risk setting {key}: {e}")
        return default_value


def _cfg_risk(db_manager, key: str, default_value):
    """Get configuration value from risk_settings table."""
    return _get_risk_setting(db_manager, key, default_value)


def _get_str_risk_config(db_manager, key: str, default: str) -> str:
    """Get string configuration value from risk_settings."""
    value = _get_risk_setting(db_manager, key, default)
    return str(value).strip() if value is not None else default


def _get_sector_exposure(db_manager, sector: str) -> float:
    """Return total market value of portfolio positions in the given sector."""
    if not sector:
        return 0.0
    try:
        with sqlite3.connect(db_manager.db_file) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """
                SELECT p.market_value, s.sector
                FROM portfolio p
                LEFT JOIN settings s ON UPPER(p.ticker) = UPPER(s.ticker)
                WHERE LOWER(COALESCE(s.sector, '')) = LOWER(?)
                """,
                (sector,)
            ).fetchall()
        return sum(float(r["market_value"] or 0) for r in rows)
    except Exception as e:
        logger.warning(f"position_sizer: sector exposure query failed: {e}")
        return 0.0


def _get_ticker_sector(db_manager, ticker: str) -> str:
    """Lookup sector for a ticker from settings table."""
    try:
        with sqlite3.connect(db_manager.db_file) as con:
            row = con.execute(
                "SELECT sector FROM settings WHERE UPPER(ticker) = UPPER(?)",
                (ticker,)
            ).fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def calculate_position(
    ticker: str,
    entry_price: float,
    stop_loss: float,
    db_manager,
    net_liquidation: Optional[float] = None,
    win_rate: Optional[float] = None,
    reward_risk: Optional[float] = None,
) -> dict:
    """
    Calculate safe position size.

    Returns dict with keys:
      quantity        (int, shares)
      risk_amount     (float, USD at risk)
      risk_pct        (float, fraction of portfolio/capital used for risk)
      position_value  (float, entry × quantity)
      sector          (str)
      sector_exposure_at_signal (float, existing sector exposure USD)
      capital_source  (str, 'bybit' | 'manual_override' | 'provided' | 'legacy')
      risk_mode       (str, active RISK_MODE value)
      status          (str: OK | SKIPPED_SECTOR_OVERWEIGHT | SKIPPED_ZERO_RISK |
                            SKIPPED_INVALID_STOP | SKIPPED_NO_CAPITAL |
                            SKIPPED_CAPITAL_UNAVAILABLE)
    """
    risk_mode = _get_str_risk_config(db_manager, "RISK_MODE", "percent_of_capital")

    if risk_mode == "percent_of_portfolio_on_stop":
        return _calculate_portfolio_risk_mode(
            ticker, entry_price, stop_loss, db_manager
        )

    if risk_mode == "kelly_fractional":
        return _calculate_kelly_fractional_mode(
            ticker,
            entry_price,
            stop_loss,
            db_manager,
            net_liquidation=net_liquidation,
            win_rate=win_rate,
            reward_risk=reward_risk,
        )

    # --- Legacy: percent_of_capital ---
    if net_liquidation is None:
        from scripts.core.bybit_capital_provider import get_net_liquidation
        net_liquidation = get_net_liquidation(db_manager)

    if net_liquidation <= 0:
        return _reject("SKIPPED_NO_CAPITAL", ticker, 0, 0, "", 0)

    if stop_loss <= 0 or entry_price <= 0:
        return _reject("SKIPPED_INVALID_STOP", ticker, net_liquidation, 0, "", 0)

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance < 0.0001:
        return _reject("SKIPPED_ZERO_RISK", ticker, net_liquidation, 0, "", 0)

    # Get risk settings from risk_settings table
    default_risk_pct    = _cfg_risk(db_manager, "DEFAULT_RISK_PCT", 0.01)
    max_position_pct    = _cfg_risk(db_manager, "MAX_POSITION_PCT", 0.05)
    soft_limit_pct      = _cfg_risk(db_manager, "MAX_SECTOR_EXPOSURE_PCT", 0.15)
    hard_limit_pct      = _cfg_risk(db_manager, "MAX_SECTOR_HARD_LIMIT_PCT", 0.25)
    overweight_factor   = _cfg_risk(db_manager, "SECTOR_OVERWEIGHT_FACTOR", 0.5)

    risk_amount = net_liquidation * default_risk_pct
    qty_by_risk = risk_amount / stop_distance

    max_qty_by_position = (net_liquidation * max_position_pct) / entry_price
    qty = min(qty_by_risk, max_qty_by_position)

    # --- Sector check ---
    sector = _get_ticker_sector(db_manager, ticker)
    sector_exposure = _get_sector_exposure(db_manager, sector) if sector else 0.0
    sector_exposure_pct = sector_exposure / net_liquidation if net_liquidation > 0 else 0.0

    if sector_exposure_pct > hard_limit_pct:
        logger.warning(
            f"position_sizer: {ticker} sector '{sector}' "
            f"at {sector_exposure_pct*100:.1f}% > hard limit {hard_limit_pct*100:.0f}% → rejected"
        )
        return _reject("SKIPPED_SECTOR_OVERWEIGHT", ticker, net_liquidation, risk_amount, sector, sector_exposure)

    if sector_exposure_pct > soft_limit_pct:
        logger.info(
            f"position_sizer: {ticker} sector '{sector}' "
            f"at {sector_exposure_pct*100:.1f}% > soft limit → qty × {overweight_factor}"
        )
        qty *= overweight_factor

    qty = max(0, int(qty))
    position_value = qty * entry_price
    actual_risk_pct = risk_amount / net_liquidation

    logger.info(
        f"position_sizer [{risk_mode}]: {ticker} qty={qty} entry={entry_price:.2f} "
        f"stop={stop_loss:.2f} risk={risk_amount:.2f} ({actual_risk_pct*100:.2f}%)"
    )

    return {
        "quantity":                  qty,
        "risk_amount":               round(risk_amount, 2),
        "risk_pct":                  round(actual_risk_pct, 6),
        "position_value":            round(position_value, 2),
        "sector":                    sector,
        "sector_exposure_at_signal": round(sector_exposure, 2),
        "capital_source":            "provided" if net_liquidation else "legacy",
        "risk_mode":                 risk_mode,
        "status":                    "OK",
    }


def _calculate_kelly_fractional_mode(
    ticker: str,
    entry_price: float,
    stop_loss: float,
    db_manager,
    net_liquidation: Optional[float] = None,
    win_rate: Optional[float] = None,
    reward_risk: Optional[float] = None,
) -> dict:
    """Scale base risk by fractional Kelly when signal quality stats are available."""
    from scripts.core.kelly_sizing import fractional_kelly_fraction

    risk_mode = "kelly_fractional"
    if net_liquidation is None:
        from scripts.core.bybit_capital_provider import get_net_liquidation

        net_liquidation = get_net_liquidation(db_manager)

    if net_liquidation <= 0:
        return _reject("SKIPPED_NO_CAPITAL", ticker, 0, 0, "", 0, risk_mode=risk_mode)

    if stop_loss <= 0 or entry_price <= 0:
        return _reject("SKIPPED_INVALID_STOP", ticker, net_liquidation, 0, "", 0, risk_mode=risk_mode)

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance < 0.0001:
        return _reject("SKIPPED_ZERO_RISK", ticker, net_liquidation, 0, "", 0, risk_mode=risk_mode)

    p = float(win_rate) if win_rate is not None else 0.5
    b = float(reward_risk) if reward_risk is not None else 1.5

    try:
        kelly_frac = float(db_manager.get_config_value("KELLY_FRACTION", "0.25"))
    except (TypeError, ValueError):
        kelly_frac = 0.25

    kelly_scale = fractional_kelly_fraction(p, b, kelly_frac)
    if kelly_scale <= 0:
        return _reject("SKIPPED_ZERO_RISK", ticker, net_liquidation, 0, "", 0, risk_mode=risk_mode)

    default_risk_pct = _cfg_risk(db_manager, "DEFAULT_RISK_PCT", 0.01)
    max_position_pct = _cfg_risk(db_manager, "MAX_POSITION_PCT", 0.05)

    risk_amount = net_liquidation * default_risk_pct * kelly_scale
    qty_by_risk = risk_amount / stop_distance
    max_qty_by_position = (net_liquidation * max_position_pct) / entry_price
    qty = max(0, int(min(qty_by_risk, max_qty_by_position)))
    position_value = qty * entry_price
    actual_risk_pct = risk_amount / net_liquidation if net_liquidation else 0.0

    logger.info(
        "position_sizer [%s]: %s qty=%s kelly_scale=%.4f p=%.2f b=%.2f",
        risk_mode,
        ticker,
        qty,
        kelly_scale,
        p,
        b,
    )

    return {
        "quantity": qty,
        "risk_amount": round(risk_amount, 2),
        "risk_pct": round(actual_risk_pct, 6),
        "position_value": round(position_value, 2),
        "sector": _get_ticker_sector(db_manager, ticker),
        "sector_exposure_at_signal": 0.0,
        "capital_source": "provided",
        "risk_mode": risk_mode,
        "kelly_scale": round(kelly_scale, 6),
        "status": "OK",
    }


def _calculate_portfolio_risk_mode(
    ticker: str,
    entry_price: float,
    stop_loss: float,
    db_manager,
) -> dict:
    """
    Position sizing using percent_of_portfolio_on_stop mode.

    qty = (portfolio_value × RISK_PERCENT_ON_STOP/100) / |entry - stop_loss|
    """
    from scripts.core.bybit_capital_provider import get_portfolio_net_liquidation, CapitalUnavailableError

    risk_mode = "percent_of_portfolio_on_stop"

    try:
        portfolio_value, capital_source = get_portfolio_net_liquidation(db_manager)
    except CapitalUnavailableError as e:
        logger.error(f"position_sizer [{risk_mode}]: {ticker} capital unavailable — {e}")
        return _reject_with_meta(
            "SKIPPED_CAPITAL_UNAVAILABLE", ticker, 0, 0, "", 0,
            risk_mode=risk_mode, capital_source="unavailable",
        )

    if portfolio_value <= 0:
        return _reject("SKIPPED_NO_CAPITAL", ticker, portfolio_value, 0, "", 0, risk_mode=risk_mode)

    if stop_loss <= 0 or entry_price <= 0:
        return _reject("SKIPPED_INVALID_STOP", ticker, portfolio_value, 0, "", 0, risk_mode=risk_mode)

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance < 0.0001:
        return _reject("SKIPPED_ZERO_RISK", ticker, portfolio_value, 0, "", 0, risk_mode=risk_mode)

    # Get risk settings from risk_settings table
    risk_percent_on_stop = _cfg_risk(db_manager, "RISK_PERCENT_ON_STOP", 1.0)
    max_position_pct     = _cfg_risk(db_manager, "MAX_POSITION_PCT", 0.05)
    soft_limit_pct       = _cfg_risk(db_manager, "MAX_SECTOR_EXPOSURE_PCT", 0.15)
    hard_limit_pct       = _cfg_risk(db_manager, "MAX_SECTOR_HARD_LIMIT_PCT", 0.25)
    overweight_factor    = _cfg_risk(db_manager, "SECTOR_OVERWEIGHT_FACTOR", 0.5)

    risk_amount = portfolio_value * (risk_percent_on_stop / 100.0)
    qty_by_risk = risk_amount / stop_distance

    max_qty_by_position = (portfolio_value * max_position_pct) / entry_price
    qty = min(qty_by_risk, max_qty_by_position)

    # --- Sector check ---
    sector = _get_ticker_sector(db_manager, ticker)
    sector_exposure = _get_sector_exposure(db_manager, sector) if sector else 0.0
    sector_exposure_pct = sector_exposure / portfolio_value if portfolio_value > 0 else 0.0

    if sector_exposure_pct > hard_limit_pct:
        logger.warning(
            f"position_sizer [{risk_mode}]: {ticker} sector '{sector}' "
            f"at {sector_exposure_pct*100:.1f}% > hard limit {hard_limit_pct*100:.0f}% → rejected"
        )
        return _reject_with_meta(
            "SKIPPED_SECTOR_OVERWEIGHT", ticker, portfolio_value, risk_amount, sector, sector_exposure,
            risk_mode=risk_mode, capital_source=capital_source
        )

    if sector_exposure_pct > soft_limit_pct:
        logger.info(
            f"position_sizer [{risk_mode}]: {ticker} sector '{sector}' "
            f"at {sector_exposure_pct*100:.1f}% > soft limit → qty × {overweight_factor}"
        )
        qty *= overweight_factor

    qty = max(0, int(qty))
    position_value = qty * entry_price
    actual_risk_pct = risk_amount / portfolio_value

    logger.info(
        f"position_sizer [{risk_mode}]: {ticker} qty={qty} entry={entry_price:.2f} "
        f"stop={stop_loss:.2f} risk={risk_amount:.2f} ({actual_risk_pct*100:.2f}%)"
    )

    return {
        "quantity":                  qty,
        "risk_amount":               round(risk_amount, 2),
        "risk_pct":                  round(actual_risk_pct, 6),
        "position_value":            round(position_value, 2),
        "sector":                    sector,
        "sector_exposure_at_signal": round(sector_exposure, 2),
        "capital_source":            capital_source,
        "risk_mode":                 risk_mode,
        "status":                    "OK",
    }


def _reject(reason: str, ticker: str, net_liq: float, risk_amount: float, sector: str, sector_exposure: float, risk_mode: str = "percent_of_capital") -> dict:
    """Helper to build a rejection response."""
    return {
        "quantity": 0,
        "risk_amount": round(risk_amount, 2),
        "risk_pct": 0.0,
        "position_value": 0.0,
        "sector": sector,
        "sector_exposure_at_signal": round(sector_exposure, 2),
        "capital_source": "legacy",
        "risk_mode": risk_mode,
        "status": reason,
    }


def _reject_with_meta(reason: str, ticker: str, net_liq: float, risk_amount: float, sector: str, sector_exposure: float, *, risk_mode: str, capital_source: str) -> dict:
    """Helper to build a rejection response with metadata."""
    return {
        "quantity": 0,
        "risk_amount": round(risk_amount, 2),
        "risk_pct": 0.0,
        "position_value": 0.0,
        "sector": sector,
        "sector_exposure_at_signal": round(sector_exposure, 2),
        "capital_source": capital_source,
        "risk_mode": risk_mode,
        "status": reason,
    }
