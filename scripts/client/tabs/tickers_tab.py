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
from scripts.client.tabs.add_ticker_dialog import AddTickerDialog
from scripts.client.tabs.status_poller import StatusPoller

class TickersTab(QWidget):
    _TICKER_COL = 1
    _RUN_COL = 2
    _PORTFOLIO_COL = 3
    _COMMENT_COL = 4

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._tickers: List[TickerSetting] = []
        self._positions: List[PositionRecord] = []
        self._poller: Optional[StatusPoller] = None
        self._running_ticker: Optional[str] = None
        self._run_completion_pending = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Ticker")
        self.add_btn.clicked.connect(self._add_ticker)
        btn_row.addWidget(self.add_btn)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)
        self.refresh_btn = QPushButton("↺ Refresh")
        self.refresh_btn.clicked.connect(self.load)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Active", "Ticker", "Run Forecasts", "Portfolio", "Comment"])
        self.table.horizontalHeader().setSectionResizeMode(self._TICKER_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self._RUN_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self._PORTFOLIO_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(self._COMMENT_COL, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

    def load(self):
        try:
            self._tickers = self.api.get_tickers()
            portfolio_resp = self.api.get_portfolio()
            self._positions = portfolio_resp.items
            self._populate_table()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load tickers:\n{e}")

    def _populate_table(self):
        self.table.setRowCount(0)
        for row_idx, t in enumerate(self._tickers):
            self.table.insertRow(row_idx)

            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(bool(t.active))
            cb_layout.addWidget(cb)
            self.table.setCellWidget(row_idx, 0, cb_widget)

            ticker_item = QTableWidgetItem(str(t.ticker or ""))
            ticker_item.setFlags(ticker_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, self._TICKER_COL, ticker_item)

            run_btn = QPushButton("▶ Run")
            run_btn.setToolTip(f"Generate forecasts and consensus for {t.ticker}")
            run_btn.clicked.connect(lambda _=False, tk=t.ticker: self._run_forecasts(tk))
            self.table.setCellWidget(row_idx, self._RUN_COL, run_btn)

            # Portfolio indicator: Yes if position exists with non-zero quantity
            position_qty = sum(
                (p.quantity or 0) for p in self._positions
                if p.ticker == t.ticker
            )
            portfolio_text = "Yes" if position_qty != 0 else "No"
            portfolio_item = QTableWidgetItem(portfolio_text)
            portfolio_item.setFlags(portfolio_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            portfolio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, self._PORTFOLIO_COL, portfolio_item)

            comment_item = QTableWidgetItem(str(t.comment or ""))
            self.table.setItem(row_idx, self._COMMENT_COL, comment_item)

    def _set_run_buttons_enabled(self, enabled: bool):
        for row in range(self.table.rowCount()):
            btn = self.table.cellWidget(row, self._RUN_COL)
            if isinstance(btn, QPushButton):
                btn.setEnabled(enabled)

    def _run_forecasts(self, ticker: str):
        reply = QMessageBox.question(
            self,
            "Run Forecasts",
            f"Run forecast generation and consensus for {ticker}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.run_forecast_ticker(ticker)
            self._running_ticker = ticker
            self._run_completion_pending = True
            self._set_run_buttons_enabled(False)
            self._start_polling()
        except Exception as e:
            err = str(e)
            if "409" in err or "already running" in err.lower():
                QMessageBox.warning(self, "Busy", "Another forecast run is already in progress.")
            else:
                QMessageBox.critical(self, "Error", f"Failed to start forecast for {ticker}:\n{e}")

    def _start_polling(self):
        if self._poller and self._poller.isRunning():
            self._poller.stop()
        self._poller = StatusPoller(self.api)
        self._poller.finished.connect(self._on_run_finished)
        self._poller.start()

    def _on_run_finished(self):
        if not self._run_completion_pending:
            return
        self._run_completion_pending = False
        self._set_run_buttons_enabled(True)
        ticker = self._running_ticker
        self._running_ticker = None
        try:
            resp = self.api.run_status()
            if resp.status == "done":
                QMessageBox.information(
                    self,
                    "Complete",
                    f"Forecast run for {ticker} completed successfully.",
                )
            elif resp.status == "error":
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Forecast run for {ticker} failed:\n{resp.message or 'Unknown error'}",
                )
        except Exception:
            pass

    def _get_checkbox(self, row: int) -> Optional[QCheckBox]:
        w = self.table.cellWidget(row, 0)
        if w:
            for child in w.children():
                if isinstance(child, QCheckBox):
                    return child
        return None

    def _add_ticker(self):
        dlg = AddTickerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data["ticker"]:
                QMessageBox.warning(self, "Error", "Ticker cannot be empty")
                return
            try:
                t = self.api.add_ticker(data["ticker"], data["active"], data["comment"])
                self._tickers.append(t)
                self._populate_table()
                QMessageBox.information(self, "Added", f"Ticker {t.ticker} added.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add ticker:\n{e}")

    def _save(self):
        errors = []
        for row_idx, t in enumerate(self._tickers):
            try:
                cb = self._get_checkbox(row_idx)
                active = 1 if (cb and cb.isChecked()) else 0
                comment_item = self.table.item(row_idx, self._COMMENT_COL)
                comment = comment_item.text() if comment_item else ""
                self.api.update_ticker(t.ticker, active=active, comment=comment)
            except Exception as e:
                errors.append(f"{t.ticker}: {e}")
        if errors:
            QMessageBox.warning(self, "Partial Save", "Some tickers failed:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Saved", "All tickers saved successfully.")
        self.load()
