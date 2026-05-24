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
from scripts.client.constants import METHODS, STATUSES
from scripts.client.table_colors import SIDE_COLORS
from scripts.client.tabs.text_dialog import TextDialog
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class ForecastsTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._logs: List[ForecastLog] = []
        self._visible: List[ForecastLog] = []
        self._current_log: Optional[ForecastLog] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter bar
        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.Shape.StyledPanel)
        fl = QHBoxLayout(filter_frame)
        fl.setSpacing(6)

        fl.addWidget(QLabel("Ticker:"))
        self.ticker_combo = QComboBox()
        self.ticker_combo.setMinimumWidth(140)
        self.ticker_combo.addItem("ALL", "")
        fl.addWidget(self.ticker_combo)

        fl.addWidget(QLabel("Method:"))
        self.method_combo = QComboBox()
        self.method_combo.setMinimumWidth(160)
        self.method_combo.addItem("ALL", "")
        for m in METHODS:
            self.method_combo.addItem(m, m)
        fl.addWidget(self.method_combo)

        fl.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(130)
        self.model_combo.addItem("ALL", "")
        self.model_combo.currentIndexChanged.connect(self._populate_table)
        fl.addWidget(self.model_combo)

        fl.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.setMinimumWidth(110)
        self.status_combo.addItem("ALL", "")
        for s in STATUSES:
            self.status_combo.addItem(s, s)
        fl.addWidget(self.status_combo)

        fl.addWidget(QLabel("From:"))
        self.date_from = QLineEdit()
        self.date_from.setPlaceholderText("YYYY-MM-DD")
        self.date_from.setMaximumWidth(110)
        fl.addWidget(self.date_from)

        fl.addWidget(QLabel("To:"))
        self.date_to = QLineEdit()
        self.date_to.setPlaceholderText("YYYY-MM-DD")
        self.date_to.setMaximumWidth(110)
        fl.addWidget(self.date_to)

        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.clicked.connect(self.load_logs)
        fl.addWidget(self.search_btn)

        self.refresh_btn = QPushButton("↺ Refresh")
        self.refresh_btn.clicked.connect(self.load_logs)
        fl.addWidget(self.refresh_btn)

        fl.addStretch()
        layout.addWidget(filter_frame)

        # Splitter: table top, details bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # Table
        table_w = QWidget()
        tl = QVBoxLayout(table_w)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        cols = ["Created", "Forecast Date", "Ticker", "Method", "Model", "Side", "Conf%", "Status", "Dir✓", "Tgt✓", "Stop✓", "PnL%"]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setAlternatingRowColors(False)
        tl.addWidget(self.table)

        self.count_label = QLabel("Found: 0")
        tl.addWidget(self.count_label)
        splitter.addWidget(table_w)

        # Details panel
        details_w = QWidget()
        dl = QVBoxLayout(details_w)
        dl.setContentsMargins(4, 4, 4, 4)
        dl.setSpacing(4)

        # Header row
        hdr_layout = QHBoxLayout()
        self.d_id = QLabel("")
        self.d_id.setFont(QFont("", 9, QFont.Weight.Bold))
        hdr_layout.addWidget(QLabel("ID:"))
        hdr_layout.addWidget(self.d_id)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Ticker:"))
        self.d_ticker = QLabel("")
        self.d_ticker.setFont(QFont("", 9, QFont.Weight.Bold))
        hdr_layout.addWidget(self.d_ticker)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Created:"))
        self.d_date = QLabel("")
        hdr_layout.addWidget(self.d_date)
        hdr_layout.addSpacing(10)
        hdr_layout.addWidget(QLabel("→"))
        self.d_fdate = QLabel("")
        self.d_fdate.setToolTip("Forecast target date")
        hdr_layout.addWidget(self.d_fdate)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Method:"))
        self.d_method = QLabel("")
        hdr_layout.addWidget(self.d_method)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Model:"))
        self.d_model = QLabel("")
        hdr_layout.addWidget(self.d_model)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Side:"))
        self.d_side = QLabel("")
        self.d_side.setFont(QFont("", 9, QFont.Weight.Bold))
        hdr_layout.addWidget(self.d_side)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Conf:"))
        self.d_conf = QLabel("")
        hdr_layout.addWidget(self.d_conf)
        hdr_layout.addStretch()
        dl.addLayout(hdr_layout)

        # Entry / Exit
        entry_layout = QHBoxLayout()
        entry_layout.addWidget(QLabel("Entry:"))
        self.d_entry = QLabel("")
        self.d_entry.setWordWrap(True)
        entry_layout.addWidget(self.d_entry, 1)
        entry_layout.addSpacing(20)
        entry_layout.addWidget(QLabel("Target:"))
        self.d_target = QLabel("")
        entry_layout.addWidget(self.d_target)
        entry_layout.addSpacing(20)
        entry_layout.addWidget(QLabel("Stop:"))
        self.d_stop = QLabel("")
        entry_layout.addWidget(self.d_stop)
        entry_layout.addStretch()
        dl.addLayout(entry_layout)

        # Rationale
        dl.addWidget(QLabel("Rationale:"))
        self.d_rationale = QTextEdit()
        self.d_rationale.setReadOnly(True)
        self.d_rationale.setMaximumHeight(80)
        dl.addWidget(self.d_rationale)

        # Actuals box
        actuals_group = QGroupBox("Actuals")
        ag = QHBoxLayout(actuals_group)
        ag.addWidget(QLabel("Open:"))
        self.d_aopen = QLabel("—")
        ag.addWidget(self.d_aopen)
        ag.addSpacing(10)
        ag.addWidget(QLabel("Close:"))
        self.d_aclose = QLabel("—")
        ag.addWidget(self.d_aclose)
        ag.addSpacing(10)
        ag.addWidget(QLabel("High:"))
        self.d_ahigh = QLabel("—")
        ag.addWidget(self.d_ahigh)
        ag.addSpacing(10)
        ag.addWidget(QLabel("Low:"))
        self.d_alow = QLabel("—")
        ag.addWidget(self.d_alow)
        ag.addSpacing(20)
        ag.addWidget(QLabel("Dir✓:"))
        self.d_dir = QLabel("—")
        ag.addWidget(self.d_dir)
        ag.addSpacing(10)
        ag.addWidget(QLabel("Target✓:"))
        self.d_tgt = QLabel("—")
        ag.addWidget(self.d_tgt)
        ag.addSpacing(10)
        ag.addWidget(QLabel("Stop✓:"))
        self.d_stp = QLabel("—")
        ag.addWidget(self.d_stp)
        ag.addSpacing(10)
        ag.addWidget(QLabel("Exit✓:"))
        self.d_exit = QLabel("—")
        ag.addWidget(self.d_exit)
        ag.addSpacing(10)
        ag.addWidget(QLabel("PnL:"))
        self.d_pnl = QLabel("—")
        ag.addWidget(self.d_pnl)
        ag.addStretch()
        dl.addWidget(actuals_group)

        # Buttons for prompt/response
        btn_row = QHBoxLayout()
        self.btn_prompt = QPushButton("📋 Show Prompt")
        self.btn_prompt.clicked.connect(self._show_prompt)
        btn_row.addWidget(self.btn_prompt)
        self.btn_response = QPushButton("📋 Show API Response")
        self.btn_response.clicked.connect(self._show_response)
        btn_row.addWidget(self.btn_response)
        btn_row.addStretch()
        dl.addLayout(btn_row)

        splitter.addWidget(details_w)
        splitter.setSizes([420, 280])

    def load_logs(self):
        try:
            ticker = self.ticker_combo.currentData() or None
            method = self.method_combo.currentData() or None
            status = self.status_combo.currentData() or None
            date_from = self.date_from.text().strip() or None
            date_to = self.date_to.text().strip() or None
            self._logs = self.api.get_logs(
                ticker=ticker, method=method, status=status,
                date_from=date_from, date_to=date_to, limit=500,
            )
            self._refresh_model_filter()
            self._populate_table()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load logs:\n{e}")

    def _refresh_model_filter(self):
        current = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("ALL", "")
        models = sorted({str(log.model or "") for log in self._logs if log.model})
        for m in models:
            self.model_combo.addItem(m, m)
        idx = self.model_combo.findData(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

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

    def _populate_table(self):
        model_filter = self.model_combo.currentData() or ""
        self._visible = [
            log for log in self._logs
            if not model_filter or str(log.model or "") == model_filter
        ]
        self.table.setSortingEnabled(False)  # disable while filling
        self.table.setRowCount(0)
        def _bool_cell(v):
            if v is None:
                return ""
            try:
                return "✅" if bool(v) else "❌"
            except Exception:
                return str(v)

        def _pnl_cell(v):
            if v is None:
                return ""
            try:
                return f"{float(v):+.2f}%"
            except Exception:
                return str(v)

        for row_idx, log in enumerate(self._visible):
            self.table.insertRow(row_idx)
            created = str(log.created_at or "")[:16]  # YYYY-MM-DD HH:MM
            fdate   = str(log.forecast_date or "")[:10]
            cells = [
                created,
                fdate,
                str(log.ticker or ""),
                str(log.method or ""),
                str(log.model or ""),
                str(log.side or ""),
                str(log.confidence or ""),
                str(log.status or ""),
                _bool_cell(log.direction_correct),
                _bool_cell(log.target_hit),
                _bool_cell(log.stop_hit),
                _pnl_cell(log.pnl_pct),
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_idx)
                self.table.setItem(row_idx, col, item)

            # Color by side/status
            side = str(log.side or "").upper()
            status = str(log.status or "").upper()
            color = SIDE_COLORS.get(side, QColor("#ffffff"))
            if status == "EVALUATED":
                color = color.darker(115)
            for col in range(self.table.columnCount()):
                it = self.table.item(row_idx, col)
                if it:
                    it.setBackground(QBrush(color))

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.count_label.setText(f"Found: {len(self._visible)}")

    def _on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        log_idx = item.data(Qt.ItemDataRole.UserRole)
        if log_idx is None or log_idx >= len(self._visible):
            return
        log = self._visible[log_idx]
        self._current_log = log
        self._update_details(log)

    def _update_details(self, log: ForecastLog):
        self.d_id.setText(str(log.id or ""))
        self.d_ticker.setText(str(log.ticker or ""))
        self.d_date.setText(str(log.created_at or "")[:16])
        self.d_fdate.setText(str(log.forecast_date or "")[:10])
        self.d_method.setText(str(log.method or ""))
        self.d_model.setText(str(log.model or ""))
        side = str(log.side or "")
        self.d_side.setText(side)
        side_upper = side.upper()
        if side_upper == "LONG":
            self.d_side.setStyleSheet("color: #2e7d32; font-weight: bold;")
        elif side_upper == "SHORT":
            self.d_side.setStyleSheet("color: #c62828; font-weight: bold;")
        else:
            self.d_side.setStyleSheet("color: #555; font-weight: bold;")
        self.d_conf.setText(f"{log.confidence}%" if log.confidence is not None else "—")
        self.d_entry.setText(str(log.entry_conditions or "—"))
        self.d_target.setText(str(log.exit_target or "—"))
        self.d_stop.setText(str(log.exit_stop or "—"))
        self.d_rationale.setPlainText(str(log.rationale or ""))

        def _fmt(val):
            if val is None:
                return "—"
            try:
                return f"{float(val):.4f}"
            except Exception:
                return str(val)

        def _bool_icon(val):
            if val is None:
                return "—"
            try:
                return "✅" if bool(val) else "❌"
            except Exception:
                return str(val)

        self.d_aopen.setText(_fmt(log.actual_open))
        self.d_aclose.setText(_fmt(log.actual_close))
        self.d_ahigh.setText(_fmt(log.actual_high))
        self.d_alow.setText(_fmt(log.actual_low))
        self.d_dir.setText(_bool_icon(log.direction_correct))
        self.d_tgt.setText(_bool_icon(log.target_hit))
        self.d_stp.setText(_bool_icon(log.stop_hit))
        self.d_exit.setText(_bool_icon(log.exit_successful))
        pnl = log.pnl_pct
        if pnl is not None:
            try:
                pnl_f = float(pnl)
                pnl_txt = f"{pnl_f:+.2f}%"
                self.d_pnl.setStyleSheet("color: #2e7d32;" if pnl_f >= 0 else "color: #c62828;")
            except Exception:
                pnl_txt = str(pnl)
                self.d_pnl.setStyleSheet("")
            self.d_pnl.setText(pnl_txt)
        else:
            self.d_pnl.setText("—")
            self.d_pnl.setStyleSheet("")

    def _show_prompt(self):
        if self._current_log:
            dlg = TextDialog("Forecast Prompt", self._current_log.forecast_prompt, self)
            dlg.exec()

    def _show_response(self):
        if self._current_log:
            dlg = TextDialog("API Response", self._current_log.prompt_response, self)
            dlg.exec()
