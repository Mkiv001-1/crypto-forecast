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

class TickersTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._tickers: List[TickerSetting] = []
        self._positions: List[PositionRecord] = []
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Active", "Ticker", "Portfolio", "Comment"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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
            self.table.setItem(row_idx, 1, ticker_item)

            # Portfolio indicator: Yes if position exists with non-zero quantity
            position_qty = sum(
                (p.quantity or 0) for p in self._positions
                if p.ticker == t.ticker
            )
            portfolio_text = "Yes" if position_qty != 0 else "No"
            portfolio_item = QTableWidgetItem(portfolio_text)
            portfolio_item.setFlags(portfolio_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            portfolio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 2, portfolio_item)

            comment_item = QTableWidgetItem(str(t.comment or ""))
            self.table.setItem(row_idx, 3, comment_item)

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
                comment_item = self.table.item(row_idx, 3)
                comment = comment_item.text() if comment_item else ""
                self.api.update_ticker(t.ticker, active=active, comment=comment)
            except Exception as e:
                errors.append(f"{t.ticker}: {e}")
        if errors:
            QMessageBox.warning(self, "Partial Save", "Some tickers failed:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Saved", "All tickers saved successfully.")
        self.load()
