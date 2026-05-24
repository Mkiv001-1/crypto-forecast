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
from scripts.client.table_colors import SIDE_COLORS
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class ForecastRunsTab(QWidget):
    """Tab for viewing forecast runs with full weight snapshots."""

    _RUN_COLS = ["ID", "Started", "Trigger", "Tickers", "Consensus", "Forecasts", "Included", "Status"]
    _LINK_COLS = ["Log ID", "Ticker", "Method", "Model", "Signal", "Raw Conf", "Win Rate", "EMA Acc", "Final Wt", "Cal Conf", "Norm R", "In Consensus", "Target", "Stop"]

    _RUN_STATUS_COLORS = {
        "completed": QColor("#c8e6c9"),
        "failed":    QColor("#ffcdd2"),
        "running":   QColor("#fff9c4"),
    }

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._runs: list = []
        self._current_run_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("↺ Refresh")
        self.refresh_btn.clicked.connect(self.load)
        bar.addWidget(self.refresh_btn)
        bar.addWidget(QLabel("Limit:"))
        self.limit_combo = QComboBox()
        for n in ["25", "50", "100", "200"]:
            self.limit_combo.addItem(n)
        self.limit_combo.setCurrentIndex(1)
        bar.addWidget(self.limit_combo)
        bar.addStretch()
        self.total_label = QLabel("Runs: 0")
        bar.addWidget(self.total_label)
        layout.addLayout(bar)

        # Splitter: runs table (top) + links table (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # Runs table
        runs_w = QWidget()
        rl = QVBoxLayout(runs_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("<b>Forecast Runs</b>"))
        self.runs_table = QTableWidget(0, len(self._RUN_COLS))
        self.runs_table.setHorizontalHeaderLabels(self._RUN_COLS)
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.runs_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.setSortingEnabled(True)
        self.runs_table.itemSelectionChanged.connect(self._on_run_selected)
        rl.addWidget(self.runs_table)
        splitter.addWidget(runs_w)

        # Links table
        links_w = QWidget()
        ll = QVBoxLayout(links_w)
        ll.setContentsMargins(0, 0, 0, 0)
        self.links_header = QLabel("<b>Forecast Weights</b> — select a run above")
        ll.addWidget(self.links_header)
        self.links_table = QTableWidget(0, len(self._LINK_COLS))
        self.links_table.setHorizontalHeaderLabels(self._LINK_COLS)
        self.links_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.links_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.links_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.links_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.links_table.setSortingEnabled(True)
        self.links_table.setAlternatingRowColors(True)
        ll.addWidget(self.links_table)
        splitter.addWidget(links_w)
        splitter.setSizes([300, 400])

    def load(self):
        try:
            limit = int(self.limit_combo.currentText())
            data = self.api.get_forecast_runs(limit=limit)
            self._runs = data.get("items", [])
            self._populate_runs()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load forecast runs:\n{e}")

    def _populate_runs(self):
        self.runs_table.setSortingEnabled(False)
        self.runs_table.setRowCount(0)
        for row_idx, run in enumerate(self._runs):
            self.runs_table.insertRow(row_idx)
            started = str(run.get("started_at", "") or "")[:16]
            cells = [
                str(run.get("id", "")),
                started,
                str(run.get("trigger_type", "") or ""),
                str(run.get("tickers_processed", "") or "0"),
                str(run.get("consensus_count", "") or "0"),
                str(run.get("total_forecasts", "") or ""),
                str(run.get("included_forecasts", "") or ""),
                str(run.get("status", "") or ""),
            ]
            status_val = str(run.get("status", "")).lower()
            bg = self._RUN_STATUS_COLORS.get(status_val)
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_idx)
                if bg:
                    item.setBackground(QBrush(bg))
                self.runs_table.setItem(row_idx, col, item)
        self.runs_table.setSortingEnabled(True)
        self.runs_table.resizeColumnsToContents()
        self.total_label.setText(f"Runs: {len(self._runs)}")
        self.links_table.setRowCount(0)
        self.links_header.setText("<b>Forecast Weights</b> — select a run above")

    def _on_run_selected(self):
        row = self.runs_table.currentRow()
        if row < 0:
            return
        item = self.runs_table.item(row, 0)
        if item is None:
            return
        run_idx = item.data(Qt.ItemDataRole.UserRole)
        if run_idx is None or run_idx >= len(self._runs):
            return
        run = self._runs[run_idx]
        run_id = run.get("id")
        if run_id is None:
            return
        self._current_run_id = run_id
        self._load_links(run_id)

    def _load_links(self, run_id: int):
        try:
            data = self.api.get_forecast_run(run_id)
            links = data.get("links", [])
            run = data.get("run", {})
            ticker_count = run.get("tickers_with_forecasts") or len(set(l.get("ticker") for l in links))
            self.links_header.setText(
                f"<b>Forecast Weights — Run #{run_id}</b>  "
                f"({len(links)} forecasts, {ticker_count} tickers)"
            )
            self._populate_links(links)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load run details:\n{e}")

    def _populate_links(self, links: list):
        self.links_table.setSortingEnabled(False)
        self.links_table.setRowCount(0)

        def _fmt(val, decimals=3):
            if val is None:
                return ""
            try:
                return f"{float(val):.{decimals}f}"
            except Exception:
                return str(val)

        for row_idx, lnk in enumerate(links):
            self.links_table.insertRow(row_idx)
            included = lnk.get("included_in_consensus", 1)
            cells = [
                str(lnk.get("log_id", "") or ""),
                str(lnk.get("ticker", "") or ""),
                str(lnk.get("method", "") or ""),
                str(lnk.get("model", "") or ""),
                str(lnk.get("signal", "") or ""),
                _fmt(lnk.get("raw_confidence"), 1),
                _fmt(lnk.get("win_rate"), 3),
                _fmt(lnk.get("ema_accuracy"), 3),
                _fmt(lnk.get("final_weight"), 4),
                _fmt(lnk.get("calibrated_confidence"), 1),
                _fmt(lnk.get("normalized_r"), 3),
                "✅" if included else "❌",
                _fmt(lnk.get("target_price"), 2),
                _fmt(lnk.get("stop_loss"), 2),
            ]
            signal = str(lnk.get("signal", "")).upper()
            base_color = SIDE_COLORS.get(signal, QColor("#ffffff"))
            if not included:
                base_color = QColor("#eeeeee")

            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(QBrush(base_color))
                if col == 11 and not included:
                    item.setForeground(QBrush(QColor("#888888")))
                self.links_table.setItem(row_idx, col, item)

        self.links_table.setSortingEnabled(True)
        self.links_table.resizeColumnsToContents()
