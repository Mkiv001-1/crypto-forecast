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
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class IndicatorsTab(QWidget):
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
        headers = ["Ticker", "Date", "Price", "MA20", "MA50", "MA200",
                   "EMA9", "EMA21", "RSI14", "StochRSI", "ATR14", "ADX14",
                   "MACD", "Signal", "Hist", "BB▲", "BB▼", "OBV",
                   "Chg5d%", "Chg20d%", "Vol/Avg", "Regime"]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
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
            resp = self.api.get_indicators(ticker=ticker, date_from=date_from, date_to=date_to, limit=2000)
            self._items = resp.items if resp else []
            self._populate_table(self._items)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load indicators:\n{e}")

    def _populate_table(self, items: list):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r, ind in enumerate(items):
            vol_ratio = ""
            if ind.volume_current and ind.volume_avg_20 and float(ind.volume_avg_20) > 0:
                vol_ratio = f"{float(ind.volume_current)/float(ind.volume_avg_20):.1f}x"
            vals = [
                ind.ticker, ind.date,
                f"{ind.price:.2f}" if ind.price else "",
                f"{ind.ma20:.2f}" if ind.ma20 else "",
                f"{ind.ma50:.2f}" if ind.ma50 else "",
                f"{ind.ma200:.2f}" if ind.ma200 else "",
                f"{ind.ema9:.2f}" if ind.ema9 else "",
                f"{ind.ema21:.2f}" if ind.ema21 else "",
                f"{ind.rsi14:.1f}" if ind.rsi14 else "",
                f"{ind.stoch_rsi:.2f}" if ind.stoch_rsi else "",
                f"{ind.atr14:.2f}" if ind.atr14 else "",
                f"{ind.adx14:.1f}" if ind.adx14 else "",
                f"{ind.macd:.2f}" if ind.macd else "",
                f"{ind.macd_signal:.2f}" if ind.macd_signal else "",
                f"{ind.macd_hist:+.2f}" if ind.macd_hist else "",
                f"{ind.bb_upper:.2f}" if ind.bb_upper else "",
                f"{ind.bb_lower:.2f}" if ind.bb_lower else "",
                f"{ind.obv:.0f}" if ind.obv else "",
                f"{ind.change_5d:+.1f}%" if ind.change_5d else "",
                f"{ind.change_20d:+.1f}%" if ind.change_20d else "",
                vol_ratio,
                ind.market_regime or "",
            ]
            self.table.insertRow(r)
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if c == 21 and v:  # market_regime
                    colors = {
                        "STRONG_UPTREND":   "#c8e6c9",
                        "STRONG_DOWNTREND": "#ffcdd2",
                        "RANGING":          "#fff9c4",
                        "WEAK_TREND":       "#f5f5f5",
                    }
                    item.setBackground(QBrush(QColor(colors.get(v, "#f5f5f5"))))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.total_label.setText(f"Rows: {len(items)}")
