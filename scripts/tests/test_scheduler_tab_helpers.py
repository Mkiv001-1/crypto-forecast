"""Tests for scheduler tab/API helpers."""

from scripts.client.tabs.scheduler_tab import _status_brush
from scripts.core.scheduler import _task_interval_specs


def test_status_brush_empty_status():
    brush = _status_brush("")
    assert brush.style() is not None


def test_status_brush_known_status():
    brush = _status_brush("ok")
    assert brush.style() is not None


def test_task_interval_specs_has_full_catalog():
    specs = _task_interval_specs(db_manager=None)
    names = {name for name, _interval, _ros in specs}
    assert "heartbeat" in names
    assert "consensus_evaluate" in names
    assert "scheduled_forecast" in names
    assert len(names) >= 14
