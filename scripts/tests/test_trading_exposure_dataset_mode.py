"""META_DATASET_MODE disables exposure skip."""

from unittest.mock import MagicMock

from scripts.core.trading_exposure import skip_forecast_when_exposed


def test_dataset_mode_disables_skip():
    db = MagicMock()
    db.get_config_value = lambda key, default="": (
        "true" if key == "META_DATASET_MODE" else "true"
    )
    assert skip_forecast_when_exposed(db) is False


def test_normal_mode_respects_skip_flag():
    db = MagicMock()
    db.get_config_value = lambda key, default="": (
        "false" if key == "META_DATASET_MODE" else "true"
    )
    assert skip_forecast_when_exposed(db) is True
