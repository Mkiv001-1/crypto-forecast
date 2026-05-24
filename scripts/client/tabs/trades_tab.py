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
from scripts.client.table_colors import SIDE_COLORS, TEST_ROW_COLOR
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class TradesTab(QWidget):
    """Tab showing rows from the trades table."""

    _COLUMNS = ["ID", "Ticker", "Signal", "Qty", "Entry", "Exit", "PnL", "R", "Trade UID", "Status", "Updated"]

    def __init__(
        self,
        api: ForecastApiClient,
        open_order_callback: Optional[Callable[[str, Optional[int]], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.api = api
        self._open_order_callback = open_order_callback
        self._trades: list = []
        self._known_statuses: set[str] = set()
        self._linked_parent_id: Optional[int] = None
        self._lookup_trade_id: Optional[int] = None
        self._lookup_consensus_id: Optional[int] = None
        self._select_trade_id: Optional[int] = None
        self._visible_trades: list = []
        self._last_error = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Ticker:"))
        self.ticker_filter = QLineEdit()
        self.ticker_filter.setPlaceholderText("All")
        self.ticker_filter.setMaximumWidth(120)
        filter_row.addWidget(self.ticker_filter)

        filter_row.addWidget(QLabel("Trade ID:"))
        self.trade_id_filter = QLineEdit()
        self.trade_id_filter.setPlaceholderText("Any")
        self.trade_id_filter.setMaximumWidth(80)
        filter_row.addWidget(self.trade_id_filter)

        filter_row.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All")
        self.status_filter.setMaximumWidth(170)
        filter_row.addWidget(self.status_filter)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.load)
        filter_row.addWidget(self.refresh_btn)

        self.reset_btn = QPushButton("✕ Reset Filters")
        self.reset_btn.clicked.connect(self.reset_filters)
        filter_row.addWidget(self.reset_btn)

        self.clear_link_btn = QPushButton("✕ Clear Link")
        self.clear_link_btn.clicked.connect(self.clear_link)
        filter_row.addWidget(self.clear_link_btn)

        self.find_orders_btn = QPushButton("↩ Show In Orders")
        self.find_orders_btn.clicked.connect(self._open_selected_in_orders)
        filter_row.addWidget(self.find_orders_btn)

        self.export_btn = QPushButton("📥 Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        filter_row.addWidget(self.export_btn)

        filter_row.addStretch()
        self.total_label = QLabel("Trades: 0")
        filter_row.addWidget(self.total_label)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda _: self._open_selected_in_orders())
        self.table.itemSelectionChanged.connect(self._update_details)
        layout.addWidget(self.table, 1)

        self.state_label = QLabel("")
        self.state_label.setStyleSheet("color: #616161;")
        layout.addWidget(self.state_label)

        self.details_label = QLabel("Selected trade: —")
        self.details_label.setStyleSheet("color: #424242;")
        layout.addWidget(self.details_label)

        self.linked_label = QLabel("")
        self.linked_label.setStyleSheet("color: #1565c0;")
        layout.addWidget(self.linked_label)

    def load(self):
        ticker = self.ticker_filter.text().strip() or None
        selected_status = self.status_filter.currentText()
        status = None if selected_status == "All" else selected_status
        trade_id = self._lookup_trade_id
        consensus_id = self._lookup_consensus_id
        if trade_id is None:
            raw_tid = self.trade_id_filter.text().strip()
            if raw_tid:
                try:
                    trade_id = int(raw_tid)
                except ValueError:
                    trade_id = None
        try:
            self._trades = self.api.get_trades(
                trade_id=trade_id,
                consensus_id=consensus_id,
                ticker=ticker,
                status=status,
                limit=500 if trade_id is None and consensus_id is None else 1,
            )
            self._last_error = ""
        except Exception as e:
            logger.warning(f"TradesTab.load error: {e}")
            self._last_error = str(e)
            self._trades = []
        self._refresh_status_filter_options(self._trades, selected_status)
        self._populate()

    def _refresh_status_filter_options(self, rows: list, selected_status: str):
        statuses = {
            str(t.get("status", "") or "").strip()
            for t in rows
            if str(t.get("status", "") or "").strip()
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
        trades = self._trades
        if self._linked_parent_id is not None:
            trades = [
                t for t in trades
                if str(t.get("ib_parent_id", "") or "") == str(self._linked_parent_id)
            ]
        self._visible_trades = list(trades)
        self.table.setRowCount(len(trades))
        for row, t in enumerate(trades):
            is_test = bool(t.get("is_test", 0))
            test_tag = str(t.get("test_tag", "") or "").strip()
            ticker_val = str(t.get("ticker", "") or "")
            if is_test:
                ticker_val = f"{ticker_val} [TEST]" if not test_tag else f"{ticker_val} [TEST:{test_tag}]"
            vals = [
                str(t.get("id", "")),
                ticker_val,
                str(t.get("signal", "") or ""),
                str(t.get("quantity", "") or ""),
                str(t.get("entry_price", "") or ""),
                str(t.get("exit_price", "") or ""),
                str(t.get("realized_pnl", "") or ""),
                str(t.get("r_multiple", "") or ""),
                str(t.get("trade_uid", "") or ""),
                str(t.get("status", "") or ""),
                str(t.get("updated_at", "") or t.get("created_at", "") or ""),
            ]

            signal = str(t.get("signal", "")).upper()
            base_bg = SIDE_COLORS.get(signal)
            if is_test:
                base_bg = TEST_ROW_COLOR

            pnl_val = t.get("realized_pnl")
            pnl_fg = None
            try:
                if pnl_val is not None and str(pnl_val) != "":
                    pnl_num = float(pnl_val)
                    if pnl_num > 0:
                        pnl_fg = QColor("#2e7d32")
                    elif pnl_num < 0:
                        pnl_fg = QColor("#c62828")
            except Exception:
                pass

            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if base_bg:
                    item.setBackground(QBrush(base_bg))
                if col == 6 and pnl_fg is not None:
                    item.setForeground(QBrush(pnl_fg))
                self.table.setItem(row, col, item)
        self.total_label.setText(f"Trades: {len(trades)}")
        if self._last_error:
            self.state_label.setStyleSheet("color: #c62828;")
            self.state_label.setText(f"Trades load error: {self._last_error}")
        elif not trades:
            self.state_label.setStyleSheet("color: #616161;")
            if self._linked_parent_id is not None:
                self.state_label.setText(
                    f"No trades found for parent #{self._linked_parent_id}. "
                    "Clear Link or Reset Filters."
                )
            elif self._lookup_trade_id is not None:
                self.state_label.setText(f"No trade found for id #{self._lookup_trade_id}.")
            elif self._lookup_consensus_id is not None:
                self.state_label.setText(
                    f"No trade found for consensus #{self._lookup_consensus_id}."
                )
            else:
                self.state_label.setText("No trades found for selected filters.")
        else:
            self.state_label.setText("")

        if self._linked_parent_id is not None:
            self.linked_label.setText(f"Linked mode: parent #{self._linked_parent_id} from Orders")
        else:
            self.linked_label.setText("")

        if self._select_trade_id is not None:
            for row, t in enumerate(trades):
                if str(t.get("id", "")) == str(self._select_trade_id):
                    self.table.selectRow(row)
                    break
            else:
                self.table.selectRow(0) if trades else None
            self._select_trade_id = None
        elif trades:
            self.table.selectRow(0)

    def open_by_trade_id(
        self,
        trade_id: int,
        ticker: Optional[str] = None,
        *,
        select: bool = True,
    ):
        self._lookup_trade_id = int(trade_id)
        self._lookup_consensus_id = None
        self._linked_parent_id = None
        if ticker:
            self.ticker_filter.setText(ticker)
        self.trade_id_filter.setText(str(trade_id))
        if select:
            self._select_trade_id = int(trade_id)
        self.status_filter.setCurrentText("All")
        self.load()

    def open_by_consensus_id(
        self,
        consensus_id: int,
        ticker: Optional[str] = None,
        *,
        select: bool = True,
    ):
        self._lookup_consensus_id = int(consensus_id)
        self._lookup_trade_id = None
        self._linked_parent_id = None
        self.trade_id_filter.clear()
        if ticker:
            self.ticker_filter.setText(ticker)
        self.status_filter.setCurrentText("All")
        self.load()
        if select and self.table.rowCount() > 0:
            self.table.selectRow(0)

    def open_from_order(self, ticker: str, parent_id: Optional[int] = None):
        self._lookup_trade_id = None
        self._lookup_consensus_id = None
        self.ticker_filter.setText(str(ticker or ""))
        self._linked_parent_id = parent_id
        self.load()

    def clear_link(self):
        self._linked_parent_id = None
        self._lookup_trade_id = None
        self._lookup_consensus_id = None
        self.load()

    def reset_filters(self):
        self.ticker_filter.clear()
        self.trade_id_filter.clear()
        self.status_filter.setCurrentText("All")
        self._linked_parent_id = None
        self._lookup_trade_id = None
        self._lookup_consensus_id = None
        self._select_trade_id = None
        self.load()

    def _open_selected_in_orders(self):
        if self._open_order_callback is None:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select a trade first.")
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._visible_trades):
            return
        trade = self._visible_trades[row]
        ticker = str(trade.get("ticker", "") or "").strip()
        if not ticker:
            QMessageBox.information(self, "Info", "Selected trade has no ticker.")
            return
        parent_id = trade.get("ib_parent_id")
        try:
            parent_id = int(parent_id) if parent_id not in (None, "") else None
        except Exception:
            parent_id = None
        self._open_order_callback(ticker, parent_id)

    def _update_details(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.details_label.setText("Selected trade: —")
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._visible_trades):
            self.details_label.setText("Selected trade: —")
            return
        trade = self._visible_trades[row]
        trade_id = trade.get("id", "")
        ticker = trade.get("ticker", "")
        status = trade.get("status", "")
        signal = trade.get("signal", "")
        parent_id = trade.get("ib_parent_id", "")
        trade_uid = str(trade.get("trade_uid", "") or "")
        test_suffix = ""
        if bool(trade.get("is_test", 0)):
            tag = str(trade.get("test_tag", "") or "").strip()
            test_suffix = "  TEST" if not tag else f"  TEST:{tag}"
        self.details_label.setText(
            f"Selected trade: #{trade_id}  {ticker}  signal={signal}  status={status}  "
            f"parent={parent_id}  trade_uid={trade_uid}{test_suffix}"
        )

    def _export_csv(self):
        """Export visible trades to CSV file."""
        import csv
        from datetime import datetime
        from pathlib import Path
        
        if not self._visible_trades:
            QMessageBox.information(self, "Info", "No trades to export.")
            return
        
        # Determine file path
        export_dir = Path.home() / "Downloads"
        export_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"trades_export_{timestamp}.csv"
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self._COLUMNS)
                for trade in self._visible_trades:
                    row = [
                        str(trade.get("id", "")),
                        str(trade.get("ticker", "")),
                        str(trade.get("signal", "") or ""),
                        str(trade.get("quantity", "") or ""),
                        str(trade.get("entry_price", "") or ""),
                        str(trade.get("exit_price", "") or ""),
                        str(trade.get("realized_pnl", "") or ""),
                        str(trade.get("r_multiple", "") or ""),
                        str(trade.get("trade_uid", "") or ""),
                        str(trade.get("status", "") or ""),
                        str(trade.get("updated_at", "") or trade.get("created_at", "") or ""),
                    ]
                    writer.writerow(row)
            
            QMessageBox.information(
                self, "Export Complete",
                f"Trades exported to:\n{file_path}\n\n({len(self._visible_trades)} rows)"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
