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
from scripts.client.tabs.numeric_table_widget_item import NumericTableWidgetItem

class PriceDataTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._items: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Filter bar ---
        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bar = QHBoxLayout(filter_frame)
        bar.setSpacing(6)

        bar.addWidget(QLabel("Ticker:"))
        self.ticker_combo = QComboBox()
        self.ticker_combo.setMinimumWidth(140)
        self.ticker_combo.addItem("ALL", "")
        bar.addWidget(self.ticker_combo)

        bar.addWidget(QLabel("From:"))
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("2025-01-01")
        self.from_edit.setMaximumWidth(110)
        bar.addWidget(self.from_edit)

        bar.addWidget(QLabel("To:"))
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("2025-12-31")
        self.to_edit.setMaximumWidth(110)
        bar.addWidget(self.to_edit)

        bar.addWidget(QLabel("Price ≥:"))
        self.price_min_edit = QLineEdit()
        self.price_min_edit.setPlaceholderText("0")
        self.price_min_edit.setMaximumWidth(80)
        bar.addWidget(self.price_min_edit)

        bar.addWidget(QLabel("Price ≤:"))
        self.price_max_edit = QLineEdit()
        self.price_max_edit.setPlaceholderText("∞")
        self.price_max_edit.setMaximumWidth(80)
        bar.addWidget(self.price_max_edit)

        bar.addWidget(QLabel("Vol ≥:"))
        self.vol_min_edit = QLineEdit()
        self.vol_min_edit.setPlaceholderText("0")
        self.vol_min_edit.setMaximumWidth(90)
        bar.addWidget(self.vol_min_edit)

        self.load_btn = QPushButton("🔄 Load")
        self.load_btn.clicked.connect(self.load)
        bar.addWidget(self.load_btn)

        self.filter_btn = QPushButton("🔍 Filter")
        self.filter_btn.clicked.connect(lambda: self._populate_table(self._items))
        bar.addWidget(self.filter_btn)

        self.total_label = QLabel("")
        bar.addWidget(self.total_label)
        bar.addStretch()
        layout.addWidget(filter_frame)

        # --- Table ---
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

    def refresh_ticker_filter(self, tickers: List[str]):
        current = self.ticker_combo.currentData()
        self.ticker_combo.blockSignals(True)
        self.ticker_combo.clear()
        self.ticker_combo.addItem("ALL", "")
        for t in sorted(set(tickers)):
            self.ticker_combo.addItem(t, t)
        idx = self.ticker_combo.findData(current)
        if idx >= 0:
            self.ticker_combo.setCurrentIndex(idx)
        self.ticker_combo.blockSignals(False)

    def load(self):
        try:
            ticker = self.ticker_combo.currentData() or None
            date_from = self.from_edit.text().strip() or None
            date_to = self.to_edit.text().strip() or None
            resp = self.api.get_price_data(ticker=ticker, date_from=date_from, date_to=date_to, limit=2000)
            self._items = resp.items if resp else []
            self._populate_table(self._items)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load price data:\n{e}")

    def _populate_table(self, items: list):
        try:
            price_min = float(self.price_min_edit.text().strip()) if self.price_min_edit.text().strip() else None
            price_max = float(self.price_max_edit.text().strip()) if self.price_max_edit.text().strip() else None
            vol_min   = float(self.vol_min_edit.text().strip())   if self.vol_min_edit.text().strip()   else None
        except ValueError:
            price_min = price_max = vol_min = None

        filtered = []
        for p in items:
            close = float(p.close) if p.close is not None else None
            vol   = float(p.volume) if p.volume is not None else None
            if price_min is not None and (close is None or close < price_min):
                continue
            if price_max is not None and (close is None or close > price_max):
                continue
            if vol_min is not None and (vol is None or vol < vol_min):
                continue
            filtered.append(p)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r, p in enumerate(filtered):
            self.table.insertRow(r)
            # Ticker (text)
            self.table.setItem(r, 0, QTableWidgetItem(str(p.ticker or "")))
            # Date (text — sorts correctly as ISO)
            self.table.setItem(r, 1, QTableWidgetItem(str(p.date or "")))
            # Numeric columns: Open, High, Low, Close
            for col, raw in [(2, p.open), (3, p.high), (4, p.low), (5, p.close)]:
                try:
                    fval = float(raw)
                    item = NumericTableWidgetItem(f"{fval:.2f}", fval)
                except (TypeError, ValueError):
                    item = NumericTableWidgetItem("", -1.0)
                self.table.setItem(r, col, item)
            # Volume (numeric)
            try:
                vval = float(p.volume)
                vitem = NumericTableWidgetItem(f"{int(vval):,}", vval)
            except (TypeError, ValueError):
                vitem = NumericTableWidgetItem("", -1.0)
            self.table.setItem(r, 6, vitem)
        self.table.setSortingEnabled(True)
        self.total_label.setText(f"Rows: {len(filtered)}")


# ---------------------------------------------------------------------------
# Indicators Tab
# ---------------------------------------------------------------------------
