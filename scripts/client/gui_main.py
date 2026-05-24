"""Main GUI window for Forecast Trading Robot client."""

import logging
from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scripts.client.activity_dialog import ActivityDialog
from scripts.client.activity_runtime import ActivityManager
from scripts.client.api_client import ForecastApiClient
from scripts.client.config import ClientConfig
from scripts.client.tabs import (
    ConsensusTab,
    ForecastRunsTab,
    ForecastsTab,
    IndicatorsTab,
    PortfolioHistoryTab,
    PriceDataTab,
    SchedulerTab,
    SettingsTab,
    SystemLogTab,
    TickersTab,
    TradingTab,
)

logger = logging.getLogger(__name__)


class _TabLoader:
    """Chains tab loads via QTimer.singleShot(0) so the event loop can breathe."""

    def __init__(self, win: "MainWindow"):
        self._win = win
        w = win
        self._steps = [
            ("Forecasts", lambda: w.forecasts_tab.load_logs()),
            ("Consensus", lambda: w.consensus_tab.load()),
            ("Tickers", lambda: w.tickers_tab.load()),
            ("Price Data", lambda: w.price_tab.load()),
            ("Indicators", lambda: w.indicators_tab.load()),
            ("Trading", lambda: w.trading_tab.load()),
            ("Runs", lambda: w.forecast_runs_tab.load()),
            ("Done", lambda: self._finish()),
        ]
        self._idx = 0

    def start(self):
        self._schedule_next()

    def _schedule_next(self):
        QTimer.singleShot(0, self._run_step)

    def _run_step(self):
        if self._idx >= len(self._steps):
            return
        label, fn = self._steps[self._idx]
        self._idx += 1
        if label != "Done":
            self._win.info_label.setText(f"Loading {label}…")
        try:
            fn()
        except Exception as e:
            logger.warning("Tab load error (%s): %s", label, e)
        if self._idx < len(self._steps):
            self._schedule_next()

    def _finish(self):
        try:
            tickers = [t.ticker for t in self._win.tickers_tab._tickers]
            self._win.forecasts_tab.refresh_ticker_filter(tickers)
            self._win.consensus_tab.refresh_ticker_filter(tickers)
            self._win.price_tab.refresh_ticker_filter(tickers)
            self._win.indicators_tab.refresh_ticker_filter(tickers)
        except Exception:
            pass
        self._win.info_label.setText("Ready")


class MainWindow(QMainWindow):
    def __init__(self, config: ClientConfig):
        super().__init__()
        self.config = config
        self.api = ForecastApiClient(config.server_url, config.api_key)
        self._connected = False
        self.setWindowTitle("Forecast Trading Robot")
        self.resize(1400, 900)
        self._build_ui()
        self._check_connection()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 4)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.forecasts_tab = ForecastsTab(self.api)
        self.tabs.addTab(self.forecasts_tab, "📊 Forecasts")

        self.consensus_tab = ConsensusTab(
            self.api,
            open_trading_callback=self._open_consensus_in_trading,
        )
        self.tabs.addTab(self.consensus_tab, "🎯 Consensus")

        self.tickers_tab = TickersTab(self.api)
        self.tabs.addTab(self.tickers_tab, "📈 Tickers")

        self.scheduler_tab = SchedulerTab(self.api)
        self.tabs.addTab(self.scheduler_tab, "Scheduler")

        self.price_tab = PriceDataTab(self.api)
        self.tabs.addTab(self.price_tab, "💹 Price Data")

        self.indicators_tab = IndicatorsTab(self.api)
        self.tabs.addTab(self.indicators_tab, "📈 Indicators")

        self.portfolio_history_tab = PortfolioHistoryTab(self.api)
        self.tabs.addTab(self.portfolio_history_tab, "📊 Portfolio History")

        self.trading_tab = TradingTab(self.api)
        self.tabs.addTab(self.trading_tab, "💱 Trading")

        self.forecast_runs_tab = ForecastRunsTab(self.api)
        self.tabs.addTab(self.forecast_runs_tab, "🔬 Runs")

        self.settings_tab = SettingsTab(self.api)
        self.tabs.addTab(self.settings_tab, "Settings")

        self.syslog_tab = SystemLogTab(self.api)
        self.tabs.addTab(self.syslog_tab, "📋 System Log")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.conn_label = QLabel("Connecting...")
        self.conn_label.setStyleSheet("color: #f57f17;")
        self.status_bar.addPermanentWidget(self.conn_label)
        self.info_label = QLabel("")
        self.status_bar.addWidget(self.info_label)

        self.activity_manager = ActivityManager(self)
        self.activity_manager.activity_status.connect(self._on_activity_status)
        self._activity_dialogs: dict[str, ActivityDialog] = {}

        self._lazy_loaded_tabs: set[int] = set()
        self._previous_tab_index = -1
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_activity_status(self, text: str):
        self.info_label.setText(text)

    def run_activity(
        self,
        operation_id: str,
        title: str,
        task: Callable[[Callable[[str, str], None]], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ):
        run = self.activity_manager.start(
            operation_id=operation_id,
            title=title,
            task=task,
            on_success=on_success,
            on_error=on_error,
            on_finished=on_finished,
        )

        dialog = self._activity_dialogs.get(run.operation_id)
        if dialog is None:
            dialog = ActivityDialog(run, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.destroyed.connect(
                lambda _obj=None, op_id=run.operation_id: self._activity_dialogs.pop(op_id, None)
            )
            self._activity_dialogs[run.operation_id] = dialog

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return run

    def _set_tab_auto_refresh(self, widget: Optional[QWidget], enabled: bool) -> None:
        if widget is None:
            return
        setter = getattr(widget, "set_auto_refresh_enabled", None)
        if callable(setter):
            setter(enabled)

    def _on_tab_changed(self, index: int) -> None:
        """Lazy-load heavy tabs; pause background timers when not visible."""
        if self._previous_tab_index >= 0:
            prev = self.tabs.widget(self._previous_tab_index)
            self._set_tab_auto_refresh(prev, False)

        if index >= 0:
            current = self.tabs.widget(index)
            self._set_tab_auto_refresh(current, True)
            self._previous_tab_index = index

        if index < 0 or index in self._lazy_loaded_tabs:
            return

        widget = self.tabs.widget(index)
        if widget is self.portfolio_history_tab:
            self._lazy_loaded_tabs.add(index)
            self.info_label.setText("Loading Portfolio History…")
            try:
                self.portfolio_history_tab.load()
            except Exception as e:
                logger.warning("Portfolio history tab load failed: %s", e)
            finally:
                self.info_label.setText("Ready")
        elif widget is self.syslog_tab:
            self._lazy_loaded_tabs.add(index)
            try:
                self.syslog_tab.load()
            except Exception as e:
                logger.warning("System log tab load failed: %s", e)
        elif widget is self.settings_tab:
            self._lazy_loaded_tabs.add(index)
            try:
                self.settings_tab.load()
            except Exception as e:
                logger.warning("Settings tab load failed: %s", e)
        elif widget is self.scheduler_tab:
            self._lazy_loaded_tabs.add(index)
            try:
                self.scheduler_tab.load()
            except Exception as e:
                logger.warning("Scheduler tab load failed: %s", e)

    def _open_consensus_in_trading(
        self,
        *,
        trade_id: Optional[int] = None,
        consensus_id: Optional[int] = None,
        ticker: Optional[str] = None,
    ):
        idx = self.tabs.indexOf(self.trading_tab)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        self.trading_tab.open_trade_by_id(
            trade_id=trade_id,
            ticker=ticker,
            consensus_id=consensus_id,
        )

    def _check_connection(self, attempt: int = 0, max_attempts: int = 24):
        """Retry /health while the server finishes background startup (~30–60s)."""
        try:
            h = self.api.health(timeout=5)
            self._connected = True
            self.conn_label.setText(f"Connected  {self.config.server_url}")
            self.conn_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self.info_label.setText(f"Server: {h.server}")
            self._load_all()
        except Exception as e:
            if attempt + 1 < max_attempts:
                self._connected = False
                self.conn_label.setText(
                    f"Waiting for server… ({attempt + 1}/{max_attempts})"
                )
                self.conn_label.setStyleSheet("color: #f57f17; font-weight: bold;")
                self.info_label.setText(
                    "Server is starting (Bybit/scheduler). Retrying in 2s…"
                )
                QTimer.singleShot(
                    2000, lambda: self._check_connection(attempt + 1, max_attempts)
                )
                return
            self._connected = False
            self.conn_label.setText(f"Disconnected — {e}")
            self.conn_label.setStyleSheet("color: #c62828; font-weight: bold;")
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Cannot connect to server at {self.config.server_url}\n\n{e}\n\n"
                f"Make sure run_server.bat is running and wait until you see "
                f"'Uvicorn running on http://0.0.0.0:8000' in the server window.\n"
                f"If the server is up, check that client_config.ini url matches.",
            )

    def _load_all(self):
        """Load core tabs at startup; heavy tabs load on first visit."""
        self.info_label.setText("Loading data…")
        self._loader = _TabLoader(self)
        self._loader.start()
