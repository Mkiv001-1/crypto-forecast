"""Tests for adversarial reasoning in forecast prompts."""

from unittest.mock import MagicMock

from scripts.core.forecast_engine import _prompt_footer


def test_adversarial_section_when_enabled(db_manager):
    db_manager.set_config_value("ADVERSARIAL_PROMPT_ENABLED", "true")
    footer = _prompt_footer(db_manager)
    assert "SHORT" in footer
    assert "LONG" in footer
    assert "JSON" in footer


def test_adversarial_section_disabled(db_manager):
    db_manager.set_config_value("ADVERSARIAL_PROMPT_ENABLED", "false")
    footer = _prompt_footer(db_manager)
    assert "adversarial" not in footer.lower()
    assert "JSON" in footer


def test_adversarial_without_db():
    footer = _prompt_footer(None)
    assert "JSON" in footer
