"""Forecast run persistence."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.core.sqlite_manager import SQLiteManager


class ForecastRunRepository:
    def __init__(self, db: "SQLiteManager"):
        self._db = db

    def mark_stuck_runs_failed(self) -> int:
        """Mark in-progress runs from a crashed server session as failed."""
        with self._db._connect() as con:
            cur = con.execute(
                "UPDATE forecast_runs SET status='failed', completed_at=started_at "
                "WHERE status='running' AND completed_at IS NULL"
            )
            return cur.rowcount
