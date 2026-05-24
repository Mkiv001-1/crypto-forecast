"""
Конфигурация торгового робота (legacy constants — используются как fallback).
Основные настройки хранятся в SQLite таблице config и редактируются через GUI.
"""

from scripts.core.consensus_settings import DEFAULT_CONFIDENCE_THRESHOLD

# Legacy constants kept for backward compatibility.
PPLX_MODEL = 'sonar-pro'
PPLX_TEMPERATURE = 0.2
PPLX_MAX_TOKENS = 2000

# Consensus and order submission thresholds (percent, 0-100)
CONFIDENCE_THRESHOLD = DEFAULT_CONFIDENCE_THRESHOLD

DATA_SOURCE = 'yfinance'
ALPHA_VANTAGE_RATE_LIMIT = 5

SPREADSHEET_NAME = 'Trading Robot'


def get_confidence_threshold(db_manager=None) -> float:
    """Read CONFIDENCE_THRESHOLD from SQLite config, with legacy fallback."""
    from scripts.core.consensus_settings import load_consensus_settings

    return load_consensus_settings(db_manager).confidence_threshold
