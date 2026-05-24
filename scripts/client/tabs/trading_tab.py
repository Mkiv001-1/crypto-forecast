"""Trading tab: orders and trades sub-tabs with Bybit sync."""

import logging
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QMessageBox

from scripts.client.api_client import ForecastApiClient
from scripts.client.activity_runtime import window_run_activity as _window_run_activity
from scripts.client.tabs.orders_tab import OrdersTab
from scripts.client.tabs.trades_tab import TradesTab

logger = logging.getLogger(__name__)


class TradingTab(QWidget):
    """Main trading tab with Orders and Trades sub-tabs."""

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._last_sync_at: Optional[str] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self.sync_orders_btn = QPushButton("Sync Orders")
        self.sync_orders_btn.setToolTip("Synchronize order statuses from Bybit and refresh tables")
        self.sync_orders_btn.clicked.connect(self._on_sync_orders)
        bar.addWidget(self.sync_orders_btn)
        self.last_sync_label = QLabel("Last sync: Never")
        self.last_sync_label.setStyleSheet("color: #616161;")
        bar.addWidget(self.last_sync_label)
        bar.addStretch()
        layout.addLayout(bar)

        self.sub_tabs = QTabWidget()
        self.trades_tab = TradesTab(self.api, open_order_callback=self.open_trade_in_orders)
        self.sub_tabs.addTab(self.trades_tab, "📈 Trades")

        self.orders_tab = OrdersTab(self.api, open_trade_callback=self.open_order_in_trades)
        self.sub_tabs.addTab(self.orders_tab, "📋 Orders")

        layout.addWidget(self.sub_tabs)

    def load(self):
        self.trades_tab.load()
        self.orders_tab.load()
        self._load_last_sync_from_config()

    def _format_last_sync(self, synced_at: str) -> str:
        if not synced_at:
            return "Last sync: Never"
        try:
            dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
            return f"Last sync: {dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            return f"Last sync: {synced_at}"

    def _on_sync_orders(self):
        self.sync_orders_btn.setEnabled(False)
        self.sync_orders_btn.setText("Syncing...")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Requesting orders synchronization.")
            result = self.api.sync_orders()
            if not bool(result.get("ok", False)):
                errors = result.get("errors", [])
                msg = "\n".join(str(e) for e in errors) if errors else "Order sync failed"
                raise RuntimeError(msg)

            scanned = int(result.get("scanned", 0) or 0)
            updated_orders = int(result.get("updated_orders", 0) or 0)
            updated_trades = int(result.get("updated_trades", 0) or 0)
            synced_at = str(result.get("synced_at", "") or "")

            log("INFO", f"Scanned statuses: {scanned}")
            log("INFO", f"Updated orders: {updated_orders}")
            log("INFO", f"Updated trades: {updated_trades}")
            if synced_at:
                log("INFO", f"Server sync timestamp: {synced_at}")
            return result

        def on_success(result: dict):
            self.orders_tab.load()
            self.trades_tab.load()
            self._last_sync_at = str(result.get("synced_at", "") or "")
            self.last_sync_label.setText(self._format_last_sync(self._last_sync_at))

        def on_error(error: str):
            logger.warning(f"Orders sync failed: {error}")

        def on_finished():
            self.sync_orders_btn.setEnabled(True)
            self.sync_orders_btn.setText("Sync Orders")

        try:
            _window_run_activity(
                self,
                operation_id="orders.sync",
                title="Sync Orders",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.sync_orders_btn.setEnabled(True)
            self.sync_orders_btn.setText("Sync Orders")
            QMessageBox.critical(self, "Sync Error", f"Failed to sync orders:\n{e}")

    def _load_last_sync_from_config(self):
        try:
            cfg = self.api.get_config()
            cfg_map = {item.key: item.value for item in cfg.items}
            self._last_sync_at = str(cfg_map.get("LAST_ORDERS_SYNC_AT", "") or "")
            self.last_sync_label.setText(self._format_last_sync(self._last_sync_at))
        except Exception:
            # Non-fatal UI path: keep previous label when config request fails.
            pass

    def open_order_in_trades(self, ticker: str, parent_id: Optional[int] = None):
        self.sub_tabs.setCurrentWidget(self.trades_tab)
        self.trades_tab.open_from_order(ticker, parent_id)

    def open_trade_in_orders(self, ticker: str, parent_id: Optional[int] = None):
        self.sub_tabs.setCurrentWidget(self.orders_tab)
        self.orders_tab.open_from_trade(ticker, parent_id)

    def open_trade_by_id(
        self,
        trade_id: Optional[int] = None,
        ticker: Optional[str] = None,
        consensus_id: Optional[int] = None,
    ):
        """Focus Trades sub-tab and show a specific trade (or by consensus)."""
        self.sub_tabs.setCurrentWidget(self.trades_tab)
        if trade_id is not None:
            self.trades_tab.open_by_trade_id(trade_id, ticker=ticker, select=True)
        elif consensus_id is not None:
            self.trades_tab.open_by_consensus_id(consensus_id, ticker=ticker, select=True)
