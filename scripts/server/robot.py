"""Robot runner — wraps forecast_runner.py business logic in a background thread."""

import threading
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


class RobotRunner:
    """Runs trading robot tasks in a background thread and captures log output."""

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"

    def __init__(self, db_file: str):
        self.excel_file = db_file  # kept for API compat
        self.db_file = db_file
        self._status = self.STATUS_IDLE
        self._message: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._finished_at: Optional[datetime] = None
        self._log_lines: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def message(self) -> Optional[str]:
        return self._message

    @property
    def started_at(self) -> Optional[str]:
        return self._started_at.isoformat() if self._started_at else None

    @property
    def finished_at(self) -> Optional[str]:
        return self._finished_at.isoformat() if self._finished_at else None

    @property
    def duration_sec(self) -> Optional[float]:
        if self._started_at and self._finished_at:
            return (self._finished_at - self._started_at).total_seconds()
        return None

    def get_log_lines(self) -> List[str]:
        with self._lock:
            return list(self._log_lines)

    def _add_log(self, line: str):
        with self._lock:
            self._log_lines.append(line)
        logger.info(line)

    def _run(self, mode: str):
        self._status = self.STATUS_RUNNING
        self._started_at = datetime.now()
        self._finished_at = None
        with self._lock:
            self._log_lines = []

        try:
            import os
            import sys as _sys
            from scripts.bootstrap import get_project_root

            os.chdir(get_project_root())
            # Drop cached modules so fresh code is loaded from disk each run
            for _mod in list(_sys.modules.keys()):
                if any(x in _mod for x in ('forecast_runner', 'unified_logs_manager', 'actuals_evaluator', 'data_loader', 'sqlite_manager')):
                    _sys.modules.pop(_mod, None)

            from scripts.core.sqlite_manager import SQLiteManager
            from scripts.core.forecast_runner import (
                run_trading_bot,
                evaluate_past_forecasts,
                evaluate_logs_records,
                run_single_ticker_forecast,
            )

            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Starting mode: {mode}")
            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] DB: {self.db_file}")

            db_manager = SQLiteManager(self.db_file)

            if mode.startswith("forecast_ticker:"):
                ticker = mode.split(":", 1)[1].upper()
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Running forecast for {ticker}...")
                run_id = run_single_ticker_forecast(ticker, db_manager=db_manager)
                self._add_log(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Forecast for {ticker} complete (run #{run_id})."
                )

            elif mode == "forecast":
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Running forecast generation...")
                run_trading_bot(db_file=self.db_file)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Forecast generation complete.")

            elif mode == "price_data":
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Updating price data for active tickers...")
                from scripts.core.bybit_data_loader import fetch_price_data_bybit as fetch_price_data
                from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
                from scripts.core.bybit_client import init_bybit_client, get_bybit_client
                import sqlite3 as _sq
                with _sq.connect(self.db_file) as _con:
                    active_tickers = [r[0] for r in _con.execute("SELECT ticker FROM settings WHERE active=1").fetchall()]
                # Initialize Bybit client with credentials from config
                config = load_bybit_config(db_manager)
                is_valid, error = validate_api_credentials(config)
                if is_valid:
                    init_bybit_client(
                        api_key=config.api_key,
                        api_secret=config.api_secret,
                        demo=config.demo,
                        recv_window=config.recv_window,
                    )
                    client = get_bybit_client()
                    self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Bybit client initialized (demo={config.demo})")
                else:
                    self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] WARNING: Invalid Bybit credentials - {error}")
                    client = None
                updated = 0
                for tkr in active_tickers:
                    try:
                        data = fetch_price_data(tkr, days=30, db_manager=db_manager, client=client)
                        if data:
                            db_manager.save_price_data(data, ticker=tkr)
                            updated += 1
                            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}]   {tkr}: {len(data)} bars saved")
                        else:
                            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}]   {tkr}: no data returned")
                    except Exception as _e:
                        self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}]   {tkr}: ERROR {_e}")
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Price data update complete. Updated {updated}/{len(active_tickers)} tickers.")

            elif mode == "evaluate":
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Running evaluation of past forecasts...")
                evaluate_past_forecasts(db_manager)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Consensus evaluation complete.")
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Running evaluation of individual forecast logs...")
                logs_evaluated = evaluate_logs_records(db_manager)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Logs evaluation complete. Evaluated {logs_evaluated} records.")

            elif mode == "full":
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Running full cycle (evaluate + forecast)...")
                evaluate_past_forecasts(db_manager)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Consensus evaluation done.")
                logs_evaluated = evaluate_logs_records(db_manager)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Logs evaluation done ({logs_evaluated} records). Starting forecast...")
                run_trading_bot(db_file=self.db_file)
                self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Full cycle complete.")

            else:
                raise ValueError(f"Unknown mode: {mode}")

            self._status = self.STATUS_DONE
            self._message = f"Completed: {mode}"

        except Exception as exc:
            self._status = self.STATUS_ERROR
            self._message = str(exc)
            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {exc}")
            logger.exception(f"Robot error in mode={mode}")

        finally:
            self._finished_at = datetime.now()
            elapsed = self.duration_sec
            self._add_log(f"[{datetime.now().strftime('%H:%M:%S')}] Duration: {elapsed:.1f}s")

    def start(self, mode: str) -> bool:
        """Start a robot run. Returns False if already running."""
        if self._status == self.STATUS_RUNNING:
            return False
        self._thread = threading.Thread(target=self._run, args=(mode,), daemon=True)
        self._thread.start()
        return True
