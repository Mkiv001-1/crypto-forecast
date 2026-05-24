"""Auto-split from gui_main."""

"""Main GUI window for Forecast Trading Robot client."""

import os
import sys
import logging
from datetime import datetime
from typing import Any, Callable, List, Optional, Set

# Suppress Qt diagnostic messages (fonts, layout, plugins)
os.environ["QT_QPA_FONTDIR"] = ""
os.environ["QT_DEBUG_PLUGINS"] = "0"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QComboBox, QTabWidget, QTextEdit,
    QSplitter, QFrame, QCheckBox, QDialog, QDialogButtonBox,
    QGroupBox, QStatusBar, QSizePolicy, QAbstractItemView,
    QApplication, QListWidget, QListWidgetItem,
    QSpinBox, QFormLayout,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QtMsgType
from PyQt6.QtGui import QColor, QFont, QBrush

from scripts.shared.models import ForecastLog, TickerSetting, ProviderSetting, PositionRecord, AccountRecord, ConsensusRecord
from scripts.client.api_client import ForecastApiClient
from scripts.client.activity_runtime import window_run_activity as _window_run_activity
from scripts.client.table_colors import TEST_ROW_COLOR
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class OrdersTab(QWidget):
    """Tab showing all orders from the orders table with cancel support."""

    _COLUMNS = [
        "ID", "Ticker", "Action", "Qty", "Price", "Status", "Type", "Role",
        "Trade UID", "Perm ID", "Account", "Bybit Order ID", "Created At"
    ]
    _STATUS_COLORS = {
        "FILLED": QColor("#c8e6c9"),
        "CANCELLED": QColor("#ffcdd2"),
        "REJECTED": QColor("#ffcdd2"),
        "SUBMITTED": QColor("#fff9c4"),
        "PENDING": QColor("#fff9c4"),
    }

    def __init__(
        self,
        api: ForecastApiClient,
        open_trade_callback: Optional[Callable[[str, Optional[int]], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.api = api
        self._open_trade_callback = open_trade_callback
        self._orders: list = []
        self._visible_orders: list = []
        self._known_statuses: set[str] = set()
        self._linked_parent_id: Optional[int] = None
        self._last_error = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Ticker:"))
        self.ticker_filter = QLineEdit()
        self.ticker_filter.setPlaceholderText("All")
        self.ticker_filter.setMaximumWidth(120)
        filter_row.addWidget(self.ticker_filter)

        filter_row.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All")
        self.status_filter.setMaximumWidth(120)
        filter_row.addWidget(self.status_filter)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.load)
        filter_row.addWidget(self.refresh_btn)

        self.reset_btn = QPushButton("✕ Reset Filters")
        self.reset_btn.clicked.connect(self.reset_filters)
        filter_row.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("❌ Cancel Selected")
        self.cancel_btn.clicked.connect(self._cancel_selected)
        filter_row.addWidget(self.cancel_btn)

        self.export_btn = QPushButton("📥 Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        filter_row.addWidget(self.export_btn)

        self.find_trade_btn = QPushButton("↪ Show In Trades")
        self.find_trade_btn.clicked.connect(self._open_selected_in_trades)
        filter_row.addWidget(self.find_trade_btn)

        filter_row.addStretch()
        self.total_label = QLabel("Orders: 0")
        filter_row.addWidget(self.total_label)
        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(12, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda _: self._open_selected_in_trades())
        self.table.itemSelectionChanged.connect(self._update_details)
        layout.addWidget(self.table, 1)

        self.state_label = QLabel("")
        self.state_label.setStyleSheet("color: #616161;")
        layout.addWidget(self.state_label)

        self.details_label = QLabel("Selected order: —")
        self.details_label.setStyleSheet("color: #424242;")
        layout.addWidget(self.details_label)

        self.linked_label = QLabel("")
        self.linked_label.setStyleSheet("color: #1565c0;")
        layout.addWidget(self.linked_label)

    def load(self):
        ticker = self.ticker_filter.text().strip() or None
        selected_status = self.status_filter.currentText()
        status = None if selected_status == "All" else selected_status
        try:
            self._orders = self.api.get_orders(ticker=ticker, status=status, limit=500)
            self._last_error = ""
        except Exception as e:
            logger.warning(f"OrdersTab.load error: {e}")
            self._last_error = str(e)
            self._orders = []
        self._refresh_status_filter_options(self._orders, selected_status)
        self._populate()

    def _refresh_status_filter_options(self, rows: list, selected_status: str):
        statuses = {
            str(o.get("status", "") or "").strip()
            for o in rows
            if str(o.get("status", "") or "").strip()
        }
        self._known_statuses.update(statuses)

        options = ["All"] + sorted(self._known_statuses)
        if selected_status and selected_status != "All" and selected_status not in options:
            options.append(selected_status)

        self.status_filter.clear()
        self.status_filter.addItems(options)
        if selected_status in options:
            self.status_filter.setCurrentText(selected_status)
        else:
            self.status_filter.setCurrentText("All")

    def _populate(self):
        orders = self._orders
        if self._linked_parent_id is not None:
            parent_key = str(self._linked_parent_id)
            orders = [
                o for o in orders
                if str(o.get("ib_parent_id", "") or "") == parent_key
                or str(o.get("id", "") or "") == parent_key
            ]
        self._visible_orders = list(orders)
        self.table.setRowCount(len(self._visible_orders))

        def _format_order_price(order: dict) -> str:
            """Return display price based on order role/type.

            STOP_LOSS/STP orders store trigger in stop_price, while
            entry/target orders use limit_price.
            """
            role = str(order.get("order_role", "") or "").upper()
            order_type = str(order.get("order_type", "") or "").upper()

            use_stop_price = role == "STOP_LOSS" or order_type.startswith("STP")
            raw_price = order.get("stop_price") if use_stop_price else order.get("limit_price")

            # Fallback to the other field if primary is empty.
            if raw_price in (None, ""):
                raw_price = order.get("limit_price") if use_stop_price else order.get("stop_price")

            if raw_price in (None, ""):
                return ""
            try:
                return f"{float(raw_price):.2f}"
            except (TypeError, ValueError):
                return str(raw_price)

        for row, o in enumerate(orders):
            is_test = bool(o.get("is_test", 0))
            test_tag = str(o.get("test_tag", "") or "").strip()
            ticker_val = str(o.get("ticker", ""))
            if is_test:
                ticker_val = f"{ticker_val} [TEST]" if not test_tag else f"{ticker_val} [TEST:{test_tag}]"
            vals = [
                str(o.get("id", "")),
                ticker_val,
                str(o.get("action", "")),
                str(o.get("quantity", "")),
                _format_order_price(o),
                str(o.get("status", "")),
                str(o.get("order_type", "") or ""),
                str(o.get("order_role", "") or ""),
                str(o.get("trade_uid", "") or ""),
                str(o.get("ib_perm_id", "") or ""),
                str(o.get("account_type", "") or ""),
                str(o.get("bybit_order_id", "") or o.get("ib_order_id", "") or ""),
                str(o.get("created_at", "") or ""),
            ]
            bg = self._STATUS_COLORS.get(o.get("status", ""))
            if is_test:
                bg = TEST_ROW_COLOR
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg:
                    item.setBackground(QBrush(bg))
                self.table.setItem(row, col, item)

        self.total_label.setText(f"Orders: {len(orders)}")
        if self._last_error:
            self.state_label.setStyleSheet("color: #c62828;")
            self.state_label.setText(f"Orders load error: {self._last_error}")
        elif not orders:
            self.state_label.setStyleSheet("color: #616161;")
            if self._linked_parent_id is not None:
                self.state_label.setText(f"No orders found for parent #{self._linked_parent_id}.")
            else:
                self.state_label.setText("No orders found for selected filters.")
        else:
            self.state_label.setText("")

        if self._linked_parent_id is not None:
            self.linked_label.setText(f"Linked mode: parent #{self._linked_parent_id} from Trades")
        else:
            self.linked_label.setText("")

    def _open_selected_in_trades(self):
        if self._open_trade_callback is None:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select an order first.")
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._visible_orders):
            return
        order = self._visible_orders[row]
        ticker = str(order.get("ticker", "") or "").strip()
        if not ticker:
            QMessageBox.information(self, "Info", "Selected order has no ticker.")
            return
        role = str(order.get("order_role", "") or "").upper()
        parent_id = order.get("ib_parent_id")
        try:
            parent_id = int(parent_id) if parent_id not in (None, "", 0) else None
        except Exception:
            parent_id = None
        if role == "ENTRY" or parent_id is None:
            try:
                parent_id = int(order.get("id"))
            except Exception:
                parent_id = None
        self._open_trade_callback(ticker, parent_id)

    def open_from_trade(self, ticker: str, parent_id: Optional[int] = None):
        self.ticker_filter.setText(str(ticker or ""))
        self._linked_parent_id = parent_id
        self.load()

    def reset_filters(self):
        self.ticker_filter.clear()
        self.status_filter.setCurrentText("All")
        self._linked_parent_id = None
        self.load()

    def _update_details(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.details_label.setText("Selected order: —")
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._visible_orders):
            self.details_label.setText("Selected order: —")
            return
        order = self._visible_orders[row]
        order_id = order.get("id", "")
        ticker = order.get("ticker", "")
        status = order.get("status", "")
        role = order.get("order_role", "")
        parent_id = order.get("ib_parent_id", "")
        trade_uid = str(order.get("trade_uid", "") or "")
        ib_perm_id = str(order.get("ib_perm_id", "") or "")
        test_suffix = ""
        if bool(order.get("is_test", 0)):
            tag = str(order.get("test_tag", "") or "").strip()
            test_suffix = "  TEST" if not tag else f"  TEST:{tag}"
        self.details_label.setText(
            f"Selected order: #{order_id}  {ticker}  status={status}  role={role}  "
            f"parent={parent_id}  trade_uid={trade_uid}  perm_id={ib_perm_id}{test_suffix}"
        )

    def _cancel_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select at least one order to cancel.")
            return
        
        # Collect order IDs from selected rows
        order_ids = []
        for row_index in rows:
            row = row_index.row()
            if 0 <= row < len(self._visible_orders):
                try:
                    order_id = int(self._visible_orders[row].get("id", 0))
                    order_ids.append(order_id)
                except Exception:
                    pass
        
        if not order_ids:
            QMessageBox.warning(self, "Warning", "Could not extract valid order IDs from selected rows.")
            return
        
        # Confirmation dialog
        msg = f"Cancel {len(order_ids)} order(s)?"
        if len(order_ids) == 1:
            msg = f"Cancel order #{order_ids[0]}?"
        
        if QMessageBox.question(
            self, "Cancel Orders",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")

        def task(log: Callable[[str, str], None]) -> dict:
            results: list[tuple[int, bool, str]] = []
            log("INFO", f"Cancelling {len(order_ids)} order(s).")
            for order_id in order_ids:
                try:
                    response = self.api.cancel_order(order_id)
                    ok = bool(response.get("cancelled", False))
                    if ok:
                        log("INFO", f"Order #{order_id}: cancelled")
                        results.append((order_id, True, "cancelled"))
                    else:
                        msg_local = str(response.get("message", "not cancelled") or "not cancelled")
                        log("WARN", f"Order #{order_id}: {msg_local}")
                        results.append((order_id, False, msg_local))
                except Exception as e:
                    err = str(e)
                    logger.warning(f"Failed to cancel order {order_id}: {err}")
                    log("ERROR", f"Order #{order_id}: {err}")
                    results.append((order_id, False, err))

            succeeded = sum(1 for _, ok, _ in results if ok)
            total = len(results)
            log("INFO", f"Cancelled: {succeeded}/{total}")
            return {"results": results, "succeeded": succeeded, "total": total}

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            logger.warning(f"Cancel selected orders failed: {error}")

        def on_finished():
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("❌ Cancel Selected")

        try:
            _window_run_activity(
                self,
                operation_id="orders.cancel_selected",
                title="Cancel Selected Orders",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("❌ Cancel Selected")
            QMessageBox.warning(self, "Cancel Orders", f"Failed to cancel selected orders:\n{e}")

    def _export_csv(self):
        """Export visible orders to CSV file."""
        import csv
        from datetime import datetime
        from pathlib import Path
        
        if not self._visible_orders:
            QMessageBox.information(self, "Info", "No orders to export.")
            return
        
        # Determine file path
        export_dir = Path.home() / "Downloads"
        export_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"orders_export_{timestamp}.csv"
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self._COLUMNS)
                for order in self._visible_orders:
                    row = [
                        str(order.get("id", "")),
                        str(order.get("ticker", "")),
                        str(order.get("action", "")),
                        str(order.get("quantity", "")),
                        str(order.get("limit_price", "") or ""),
                        str(order.get("status", "")),
                        str(order.get("order_type", "") or ""),
                        str(order.get("order_role", "") or ""),
                        str(order.get("account_type", "") or ""),
                        str(order.get("bybit_order_id", "") or order.get("ib_order_id", "") or ""),
                        str(order.get("created_at", "") or ""),
                    ]
                    writer.writerow(row)
            
            QMessageBox.information(
                self, "Export Complete",
                f"Orders exported to:\n{file_path}\n\n({len(self._visible_orders)} rows)"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
