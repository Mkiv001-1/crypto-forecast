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
from scripts.client.consensus_trade_status import compute_trade_status, parse_trade_id
from scripts.client.table_colors import SIDE_COLORS
from scripts.client.activity_runtime import window_run_activity as _window_run_activity
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class ConsensusTab(QWidget):
    """Tab for displaying aggregated consensus signals from the consensus table."""

    _TABLE_COLS = [
        "Date", "Eval Date", "Ticker", "Signal", "Conf %",
        "Target", "Stop", "Entry",
        "Eval Close", "Eval Status",
        "Disagree", "Trade ID", "Trade Status", "Action",
    ]

    def __init__(
        self,
        api: ForecastApiClient,
        open_trading_callback: Optional[Callable[..., None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.api = api
        self._open_trading_callback = open_trading_callback
        self._records: List[ConsensusRecord] = []
        self._visible: List[ConsensusRecord] = []
        self._current_record: Optional[ConsensusRecord] = None
        self._placing_consensus_ids: Set[int] = set()
        self._trade_details_cache: dict = {}
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

        fl.addWidget(QLabel("Signal:"))
        self.signal_combo = QComboBox()
        self.signal_combo.setMinimumWidth(110)
        self.signal_combo.addItem("ALL", "")
        for s in ["LONG", "SHORT", "NEUTRAL"]:
            self.signal_combo.addItem(s, s)
        fl.addWidget(self.signal_combo)

        fl.addWidget(QLabel("Eval:"))
        self.eval_combo = QComboBox()
        self.eval_combo.setMinimumWidth(110)
        self.eval_combo.addItem("ALL", "")
        for s in ["PENDING", "EVALUATED", "NO_DATA"]:
            self.eval_combo.addItem(s, s)
        fl.addWidget(self.eval_combo)

        fl.addWidget(QLabel("Trade:"))
        self.trade_status_combo = QComboBox()
        self.trade_status_combo.setMinimumWidth(110)
        self.trade_status_combo.addItem("ALL", "")
        for label, value in [
            ("traded", "traded"),
            ("submitted", "submitted"),
            ("orphan", "orphan"),
            ("pending", "pending"),
            ("skipped", "skipped"),
            ("expired", "expired"),
            ("new", "new"),
        ]:
            self.trade_status_combo.addItem(label, value)
        fl.addWidget(self.trade_status_combo)

        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.clicked.connect(self.load)
        fl.addWidget(self.search_btn)

        self.refresh_btn = QPushButton("↺ Refresh")
        self.refresh_btn.clicked.connect(self.load)
        fl.addWidget(self.refresh_btn)

        self.evaluate_btn = QPushButton("📊 Evaluate Now")
        self.evaluate_btn.setToolTip("Trigger evaluation of pending consensus records")
        self.evaluate_btn.clicked.connect(self._on_evaluate_now)
        fl.addWidget(self.evaluate_btn)

        self.recalc_btn = QPushButton("🔄 Recalculate")
        self.recalc_btn.setToolTip("Recalculate consensus from historical forecast logs")
        self.recalc_btn.clicked.connect(self._on_recalculate_consensus)
        fl.addWidget(self.recalc_btn)

        fl.addStretch()
        layout.addWidget(filter_frame)

        # Stats bar
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sl = QHBoxLayout(stats_frame)
        sl.setSpacing(16)
        sl.setContentsMargins(6, 2, 6, 2)
        self.stat_total = QLabel("Total: 0")
        self.stat_evaluated = QLabel("Evaluated: 0")
        self.stat_win_rate = QLabel("Win Rate: —")
        self.stat_avg_pnl = QLabel("Avg PnL: —")
        self.stat_pending = QLabel("Pending: 0")
        for lbl in [self.stat_total, self.stat_evaluated, self.stat_win_rate, self.stat_avg_pnl, self.stat_pending]:
            lbl.setStyleSheet("font-weight: bold;")
            sl.addWidget(lbl)
        sl.addStretch()
        layout.addWidget(stats_frame)

        # Splitter: table top, details bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # Table
        table_w = QWidget()
        tl = QVBoxLayout(table_w)
        tl.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self._TABLE_COLS))
        self.table.setHorizontalHeaderLabels(self._TABLE_COLS)
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
        dl.setContentsMargins(0, 0, 0, 0)

        # Details header row
        hdr_layout = QHBoxLayout()
        hdr_layout.addWidget(QLabel("ID:"))
        self.d_id = QLabel("")
        self.d_id.setStyleSheet("font-weight: bold;")
        hdr_layout.addWidget(self.d_id)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Ticker:"))
        self.d_ticker = QLabel("")
        self.d_ticker.setStyleSheet("font-weight: bold;")
        hdr_layout.addWidget(self.d_ticker)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Date:"))
        self.d_date = QLabel("")
        self.d_date.setStyleSheet("font-weight: bold;")
        hdr_layout.addWidget(self.d_date)
        hdr_layout.addSpacing(20)
        hdr_layout.addWidget(QLabel("Signal:"))
        self.d_signal = QLabel("")
        self.d_signal.setStyleSheet("font-weight: bold;")
        hdr_layout.addWidget(self.d_signal)
        hdr_layout.addStretch()
        dl.addLayout(hdr_layout)

        # Details fields in three compact columns
        grid = QHBoxLayout()
        col_left = QVBoxLayout()
        col_mid = QVBoxLayout()
        col_right = QVBoxLayout()

        def _row(label, attr_name, parent_layout):
            row_l = QHBoxLayout()
            row_l.addWidget(QLabel(label))
            lbl = QLabel("")
            setattr(self, attr_name, lbl)
            row_l.addWidget(lbl)
            row_l.addStretch()
            parent_layout.addLayout(row_l)

        _row("Confidence:", "d_conf", col_left)
        _row("Target:", "d_target", col_left)
        _row("Stop Loss:", "d_stop", col_left)
        _row("Entry Limit:", "d_entry", col_left)
        _row("Horizon (h):", "d_horizon", col_left)
        _row("Eval Target Date:", "d_eval_date", col_left)
        _row("Eval Status:", "d_eval_status", col_left)
        _row("Actual Date:", "d_actual_date", col_left)
        _row("Eval Close:", "d_eval_close", col_left)

        _row("Trade ID:", "d_trade_id", col_mid)
        _row("Trade Status:", "d_trade_status", col_mid)
        trade_actions = QHBoxLayout()
        self.show_in_trading_btn = QPushButton("Show in Trading")
        self.show_in_trading_btn.setToolTip("Open this trade in Trading → Trades")
        self.show_in_trading_btn.clicked.connect(self._on_show_in_trading)
        self.show_in_trading_btn.setEnabled(False)
        trade_actions.addWidget(self.show_in_trading_btn)
        trade_actions.addStretch()
        col_mid.addLayout(trade_actions)
        self.d_trade_warning = QLabel("")
        self.d_trade_warning.setWordWrap(True)
        self.d_trade_warning.setStyleSheet("color: #c62828;")
        col_mid.addWidget(self.d_trade_warning)
        _row("Actual Entry:", "d_entry_actual", col_mid)
        _row("Actual Stop:", "d_actual_stop", col_mid)
        _row("Actual Close:", "d_actual_close", col_mid)

        _row("Direction:", "d_direction", col_right)
        _row("Target Hit:", "d_target_hit", col_right)
        _row("Stop Hit:", "d_stop_hit", col_right)
        _row("First Hit:", "d_first_hit", col_right)
        _row("PnL %:", "d_pnl_pct", col_right)
        _row("R Multiple:", "d_r_multiple", col_right)

        grid.addLayout(col_left, 1)
        grid.addLayout(col_mid, 1)
        grid.addLayout(col_right, 1)
        dl.addLayout(grid)

        # Methods block
        methods_frame = QFrame()
        methods_frame.setFrameShape(QFrame.Shape.StyledPanel)
        methods_layout = QHBoxLayout(methods_frame)
        methods_layout.setSpacing(8)
        for lbl_text, attr in [
            ("Methods Long:", "d_methods_long"),
            ("Methods Short:", "d_methods_short"),
            ("Methods Neutral:", "d_methods_neutral"),
        ]:
            vl = QVBoxLayout()
            vl.addWidget(QLabel(lbl_text))
            te = QTextEdit()
            te.setReadOnly(True)
            te.setMaximumHeight(55)
            setattr(self, attr, te)
            vl.addWidget(te)
            methods_layout.addLayout(vl, 1)
        dl.addWidget(methods_frame)

        # Rationale
        dl.addWidget(QLabel("Rationale:"))
        self.d_rationale = QTextEdit()
        self.d_rationale.setReadOnly(True)
        self.d_rationale.setMaximumHeight(55)
        dl.addWidget(self.d_rationale)

        splitter.addWidget(details_w)
        splitter.setSizes([350, 350])

    def load(self):
        try:
            self._trade_details_cache.clear()
            ticker = self.ticker_combo.currentData() or None
            date_from = self.date_from.text().strip() or None
            date_to = self.date_to.text().strip() or None
            limit = 500
            resp = self.api.get_consensus(ticker=ticker, limit=limit, date_from=date_from, date_to=date_to)
            self._records = resp.items
            self._prefetch_trades_for_records()
            self._populate_table()
            self._update_stats()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load consensus:\n{e}")

    def _on_evaluate_now(self):
        self.evaluate_btn.setEnabled(False)
        self.evaluate_btn.setText("⏳ Evaluating...")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Starting consensus evaluation request.")
            result = self.api.evaluate_consensus()

            processed = int(result.get("processed", 0) or 0)
            ready_before = int(result.get("ready_before", 0) or 0)
            ready_after = int(result.get("ready_after", 0) or 0)
            not_ready = int(result.get("not_ready", 0) or 0)
            no_target = int(result.get("no_target", 0) or 0)

            log("INFO", f"Processed: {processed}")
            log("INFO", f"Ready before/after: {ready_before} -> {ready_after}")
            log("INFO", f"Pending future: {not_ready}")
            log("INFO", f"Pending without target date: {no_target}")
            log("INFO", f"Total evaluated in DB: {int(result.get('total_evaluated', 0) or 0)}")
            return result

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            logger.warning(f"Evaluate consensus failed: {error}")

        def on_finished():
            self.evaluate_btn.setEnabled(True)
            self.evaluate_btn.setText("📊 Evaluate Now")

        try:
            _window_run_activity(
                self,
                operation_id="consensus.evaluate",
                title="Evaluate Consensus",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.evaluate_btn.setEnabled(True)
            self.evaluate_btn.setText("📊 Evaluate Now")
            QMessageBox.warning(self, "Error", f"Failed to evaluate consensus:\n{e}")

    def _on_recalculate_consensus(self):
        # Ask for confirmation with force option
        reply = QMessageBox.question(
            self,
            "Recalculate Consensus",
            "This will recalculate ALL consensus records from historical forecast logs,\n"
            "including already EVALUATED records.\n\n"
            "Eval fields will be reset and re-evaluated from scratch.\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.recalc_btn.setEnabled(False)
        self.recalc_btn.setText("⏳ Recalculating...")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Starting forced consensus recalculation.")
            result = self.api.recalculate_consensus(force=True)
            created = int(result.get("created", 0) or 0)
            updated = int(result.get("updated", 0) or 0)
            skipped = int(result.get("skipped", 0) or 0)
            errors = int(result.get("errors", 0) or 0)
            total = int(result.get("total_groups", 0) or 0)
            evaluated = int(result.get("evaluated", 0) or 0)

            log("INFO", f"Total groups: {total}")
            log("INFO", f"Created: {created}")
            log("INFO", f"Updated: {updated}")
            log("INFO", f"Evaluated (past dates): {evaluated}")
            log("INFO", f"Skipped (no logs): {skipped}")
            if errors > 0:
                log("WARN", f"Errors: {errors}")
            return result

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            logger.warning(f"Recalculate consensus failed: {error}")

        def on_finished():
            self.recalc_btn.setEnabled(True)
            self.recalc_btn.setText("🔄 Recalculate")

        try:
            _window_run_activity(
                self,
                operation_id="consensus.recalculate",
                title="Recalculate Consensus",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.recalc_btn.setEnabled(True)
            self.recalc_btn.setText("🔄 Recalculate")
            QMessageBox.warning(self, "Error", f"Failed to recalculate consensus:\n{e}")

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

    def _update_stats(self):
        total = len(self._records)
        evaluated = [r for r in self._records if str(r.eval_status or "") == "EVALUATED"]
        pending   = [r for r in self._records if str(r.eval_status or "") == "PENDING"]
        wins = [r for r in evaluated if r.direction_correct and int(r.direction_correct) == 1]
        win_rate = f"{len(wins)/len(evaluated)*100:.0f}%" if evaluated else "—"
        pnl_vals = []
        for r in evaluated:
            try:
                pnl_vals.append(float(r.pnl_pct))
            except (TypeError, ValueError):
                pass
        avg_pnl = f"{sum(pnl_vals)/len(pnl_vals):.2f}%" if pnl_vals else "—"
        self.stat_total.setText(f"Total: {total}")
        self.stat_evaluated.setText(f"Evaluated: {len(evaluated)}")
        self.stat_win_rate.setText(f"Win Rate: {win_rate}")
        self.stat_avg_pnl.setText(f"Avg PnL: {avg_pnl}")
        self.stat_pending.setText(f"Pending: {len(pending)}")

    def _trade_status_text(self, rec: ConsensusRecord) -> str:
        trade_id = self._parse_trade_id(rec.trade_id)
        trade_row = self._resolve_trade(rec)
        return compute_trade_status(
            trade_id=trade_id,
            order_state=str(rec.order_state or ""),
            trade_row=trade_row,
        )

    def _place_trade_disabled_reason(self, rec: ConsensusRecord) -> str:
        if rec.id is None:
            return "No consensus ID"
        trade_status = self._trade_status_text(rec)
        if trade_status == "traded":
            return "Trade already created"
        if trade_status == "orphan":
            return "Invalid trade link — repair consensus.trade_id first"
        signal = str(rec.signal or "").upper()
        if signal not in ("LONG", "SHORT"):
            return "Only LONG/SHORT can be traded"
        order_state = str(rec.order_state or "").upper()
        if order_state in ("ORDER_SUBMITTED", "PENDING_ORDER", "EXPIRED"):
            return f"Order state: {order_state}"
        try:
            if int(rec.id) in self._placing_consensus_ids:
                return "Trade is being placed"
        except Exception:
            pass
        return ""

    def _can_place_trade(self, rec: ConsensusRecord) -> bool:
        return self._place_trade_disabled_reason(rec) == ""

    def _populate_table(self):
        signal_filter = self.signal_combo.currentData() or ""
        eval_filter   = self.eval_combo.currentData() or ""
        trade_filter  = self.trade_status_combo.currentData() or ""
        self._visible = [
            r for r in self._records
            if (not signal_filter or str(r.signal or "") == signal_filter)
            and (not eval_filter or str(r.eval_status or "") == eval_filter)
            and (not trade_filter or self._trade_status_text(r) == trade_filter)
        ]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        def _fmtp(val):
            if val is None:
                return ""
            try:
                return f"{float(val):.2f}"
            except Exception:
                return str(val)

        for row_idx, rec in enumerate(self._visible):
            self.table.insertRow(row_idx)
            date_str = str(rec.date or "")[:16]
            has_disagreement = rec.high_model_disagreement or (rec.rationale and "disagreement" in rec.rationale.lower())
            eval_status = str(rec.eval_status or "")
            trade_status = self._trade_status_text(rec)
            eval_date_str = str(rec.eval_target_date or "")[:16]
            cells = [
                date_str,                    # Date
                eval_date_str,               # Eval Date (target)
                str(rec.ticker or ""),       # Ticker
                str(rec.signal or ""),       # Signal
                str(rec.confidence or ""),   # Conf%
                _fmtp(rec.target_price),     # Target
                _fmtp(rec.stop_loss),        # Stop
                _fmtp(rec.entry_limit_price), # Entry
                _fmtp(rec.actual_close),     # Eval Close
                eval_status,                 # Eval Status
                "⚠️" if has_disagreement else "",  # Disagree
                str(rec.trade_id or ""),     # Trade ID
                trade_status,                 # Trade Status
                "",                          # Action (button widget)
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_idx)
                self.table.setItem(row_idx, col, item)

            action_col = self._TABLE_COLS.index("Action")
            place_btn = QPushButton("Place Trade")
            place_btn.setProperty("consensus_id", rec.id)
            place_btn.clicked.connect(lambda _=False, cid=rec.id: self._on_place_trade_clicked(cid))
            disabled_reason = self._place_trade_disabled_reason(rec)
            if disabled_reason:
                place_btn.setEnabled(False)
                place_btn.setToolTip(disabled_reason)
            else:
                place_btn.setToolTip("Create trade record and related orders")
            self.table.setCellWidget(row_idx, action_col, place_btn)

            # Color by signal first, then override eval result column
            signal = str(rec.signal or "").upper()
            base_color = SIDE_COLORS.get(signal, QColor("#ffffff"))
            for col in range(self.table.columnCount()):
                it = self.table.item(row_idx, col)
                if it:
                    it.setBackground(QBrush(base_color))

            # Override eval-status column colors
            status_col = self._TABLE_COLS.index("Eval Status")
            status_item = self.table.item(row_idx, status_col)
            if status_item:
                if eval_status == "EVALUATED":
                    status_item.setForeground(QBrush(QColor("#1b5e20")))
                elif eval_status == "NO_DATA":
                    status_item.setForeground(QBrush(QColor("#888888")))
                elif eval_status == "PENDING":
                    status_item.setForeground(QBrush(QColor("#e65100")))

            trade_status_col = self._TABLE_COLS.index("Trade Status")
            trade_status_item = self.table.item(row_idx, trade_status_col)
            if trade_status_item:
                if trade_status == "traded":
                    trade_status_item.setForeground(QBrush(QColor("#1b5e20")))
                elif trade_status in ("pending", "submitted"):
                    trade_status_item.setForeground(QBrush(QColor("#e65100")))
                elif trade_status == "orphan":
                    trade_status_item.setForeground(QBrush(QColor("#c62828")))
                elif trade_status in ("expired", "skipped"):
                    trade_status_item.setForeground(QBrush(QColor("#888888")))

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.count_label.setText(f"Found: {len(self._visible)}")

    def _on_place_trade_clicked(self, consensus_id):
        if consensus_id is None:
            QMessageBox.warning(self, "Place Trade", "Consensus ID is missing.")
            return

        rec = next((r for r in self._records if r.id == consensus_id), None)
        if rec is None:
            QMessageBox.warning(self, "Place Trade", "Consensus record not found in current dataset.")
            return

        disabled_reason = self._place_trade_disabled_reason(rec)
        if disabled_reason:
            QMessageBox.information(self, "Place Trade", f"Trade is unavailable: {disabled_reason}")
            return

        preview = {}
        preview_note = ""
        quantity_text = "N/A"
        risk_amount_text = "N/A"
        risk_mode_text = "N/A"
        capital_source_text = "N/A"
        try:
            preview = self.api.preview_consensus_trade(int(consensus_id))
            preview_status = str(preview.get("status", ""))
            preview_message = str(preview.get("message", "")).strip()
            qty = preview.get("quantity")
            if qty is not None and str(qty).strip() != "":
                quantity_text = str(qty)
            risk_amount = preview.get("risk_amount")
            if risk_amount is not None and str(risk_amount).strip() != "":
                try:
                    risk_amount_text = f"{float(risk_amount):.2f}"
                except Exception:
                    risk_amount_text = str(risk_amount)
            risk_mode = preview.get("risk_mode")
            if risk_mode is not None and str(risk_mode).strip() != "":
                risk_mode_text = str(risk_mode)
            capital_source = preview.get("capital_source")
            if capital_source is not None and str(capital_source).strip() != "":
                capital_source_text = str(capital_source)
            if preview_status and preview_status.upper() != "OK":
                preview_note = f"Preview: {preview_status} {preview_message}".strip()
        except Exception as e:
            preview_note = f"Preview unavailable: {e}"

        signal = str(rec.signal or "").upper()
        entry_action = "BUY" if signal == "LONG" else "SELL"
        exit_action = "SELL" if signal == "LONG" else "BUY"
        if rec.entry_limit_price is not None:
            try:
                entry_price_text = f"{float(rec.entry_limit_price):.2f}"
            except Exception:
                entry_price_text = str(rec.entry_limit_price)
            entry_order_type = "LMT"
        else:
            entry_price_text = "Market"
            entry_order_type = "MKT"

        try:
            target_price_text = f"{float(rec.target_price):.2f}" if rec.target_price is not None else "N/A"
        except Exception:
            target_price_text = str(rec.target_price)
        try:
            stop_price_text = f"{float(rec.stop_loss):.2f}" if rec.stop_loss is not None else "N/A"
        except Exception:
            stop_price_text = str(rec.stop_loss)

        details = (
            f"Ticker: {str(rec.ticker or '')}\n"
            f"Consensus ID: {consensus_id}\n"
            f"Signal: {signal}\n"
            f"Quantity: {quantity_text}\n"
            f"Risk Amount: {risk_amount_text}\n"
            f"Risk Mode: {risk_mode_text}\n"
            f"Capital Source: {capital_source_text}\n"
            f"\n"
            f"Prices:\n"
            f"- Entry: {entry_price_text}\n"
            f"- Target: {target_price_text}\n"
            f"- Stop: {stop_price_text}\n"
            f"\n"
            f"Orders to place:\n"
            f"1. ENTRY: {entry_action} {entry_order_type}\n"
            f"2. TAKE_PROFIT: {exit_action} LMT\n"
            f"3. STOP_LOSS: {exit_action} STP\n"
            f"\n"
            f"{preview_note + chr(10) if preview_note else ''}"
            f"Continue?"
        )
        confirm = QMessageBox.question(
            self,
            "Confirm Place Trade",
            details,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Ok:
            return

        consensus_id = int(consensus_id)
        self._placing_consensus_ids.add(consensus_id)

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", f"Submitting consensus activation for id={consensus_id}.")
            result = self.api.activate_consensus(consensus_id)
            status = str(result.get("status", "")).strip()
            message = str(result.get("message", "")).strip()
            if status:
                log("INFO", f"Result status: {status}")
            if message:
                level = "WARN" if status.upper() in ("SKIPPED", "EXPIRED", "ERROR") else "INFO"
                log(level, message)
            return result

        def on_success(_result: dict):
            # UI refresh is done in on_finished for both success and error outcomes.
            pass

        def on_error(error: str):
            logger.warning(f"Place trade failed for consensus {consensus_id}: {error}")

        def on_finished():
            self._placing_consensus_ids.discard(consensus_id)
            self.load()

        try:
            _window_run_activity(
                self,
                operation_id=f"consensus.place_trade.{consensus_id}",
                title=f"Place Trade (Consensus #{consensus_id})",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self._placing_consensus_ids.discard(consensus_id)
            self.load()
            QMessageBox.warning(self, "Place Trade", f"Failed to place trade:\n{e}")

    @staticmethod
    def _parse_trade_id(value: Any) -> Optional[int]:
        return parse_trade_id(value)

    def _prefetch_trades_for_records(self) -> None:
        """One bulk fetch — avoids N+1 HTTP calls while building the table."""
        try:
            rows = self.api.get_trades(limit=2000)
        except Exception as e:
            logger.warning("Failed to prefetch trades for consensus tab: %s", e)
            return
        for row in rows:
            trade_id = row.get("id")
            if trade_id is not None:
                self._trade_details_cache[int(trade_id)] = row
            consensus_id = row.get("consensus_id")
            if consensus_id is not None:
                ckey = f"consensus:{consensus_id}"
                if ckey not in self._trade_details_cache:
                    self._trade_details_cache[ckey] = row

    def _resolve_trade(self, rec: ConsensusRecord, *, allow_fetch: bool = False) -> Optional[dict]:
        """Resolve trade from prefetch cache; optional single fetch for detail panel."""
        trade_id = self._parse_trade_id(rec.trade_id)
        if trade_id is not None:
            if trade_id in self._trade_details_cache:
                return self._trade_details_cache[trade_id]
            if not allow_fetch:
                return None
            try:
                trade = self.api.get_trade_by_id(trade_id)
                self._trade_details_cache[trade_id] = trade
                return trade
            except Exception as e:
                logger.warning("Failed to fetch trade details for trade_id=%s: %s", trade_id, e)
                self._trade_details_cache[trade_id] = None
                return None

        if rec.id is not None:
            ckey = f"consensus:{rec.id}"
            if ckey in self._trade_details_cache:
                return self._trade_details_cache[ckey]
            if not allow_fetch:
                return None
            try:
                rows = self.api.get_trades(consensus_id=int(rec.id), limit=1)
                trade = rows[0] if rows else None
                self._trade_details_cache[ckey] = trade
                return trade
            except Exception as e:
                logger.warning("Failed to fetch trade by consensus_id=%s: %s", rec.id, e)
                self._trade_details_cache[ckey] = None
        return None

    def _get_trade_details(self, rec: ConsensusRecord) -> Optional[dict]:
        return self._resolve_trade(rec, allow_fetch=True)

    def _on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        rec_idx = item.data(Qt.ItemDataRole.UserRole)
        if rec_idx is None or rec_idx >= len(self._visible):
            return
        rec = self._visible[rec_idx]
        self._current_record = rec
        self._update_details(rec)

    def _update_details(self, rec: ConsensusRecord):
        self.d_id.setText(str(rec.id or ""))
        self.d_ticker.setText(str(rec.ticker or ""))
        self.d_date.setText(str(rec.date or "")[:16])

        signal = str(rec.signal or "")
        self.d_signal.setText(signal)
        signal_upper = signal.upper()
        if signal_upper == "LONG":
            self.d_signal.setStyleSheet("color: #2e7d32; font-weight: bold;")
        elif signal_upper == "SHORT":
            self.d_signal.setStyleSheet("color: #c62828; font-weight: bold;")
        else:
            self.d_signal.setStyleSheet("color: #555; font-weight: bold;")

        conf = rec.confidence
        self.d_conf.setText(f"{conf}%" if conf is not None else "—")

        def _fmt(val, decimals=4):
            if val is None:
                return "—"
            try:
                return f"{float(val):.{decimals}f}"
            except Exception:
                return str(val)

        def _bool_txt(val):
            if val is None:
                return "—"
            try:
                return "Yes ✅" if int(val) == 1 else "No ❌"
            except Exception:
                return str(val)

        self.d_target.setText(_fmt(rec.target_price))
        self.d_stop.setText(_fmt(rec.stop_loss))
        self.d_entry.setText(_fmt(rec.entry_limit_price))
        self.d_horizon.setText(str(rec.horizon_hours) + "h" if rec.horizon_hours else "—")
        self.d_eval_date.setText(str(rec.eval_target_date or "")[:16] or "—")
        self.d_methods_long.setPlainText(str(rec.methods_long or "—"))
        self.d_methods_short.setPlainText(str(rec.methods_short or "—"))
        self.d_methods_neutral.setPlainText(str(rec.methods_neutral or "—"))
        self.d_rationale.setPlainText(str(rec.rationale or ""))

        # Evaluation fields
        eval_status = str(rec.eval_status or "—")
        self.d_eval_status.setText(eval_status)
        if eval_status == "EVALUATED":
            self.d_eval_status.setStyleSheet("color: #1b5e20; font-weight: bold;")
        elif eval_status == "NO_DATA":
            self.d_eval_status.setStyleSheet("color: #888;")
        elif eval_status == "PENDING":
            self.d_eval_status.setStyleSheet("color: #e65100; font-weight: bold;")
        else:
            self.d_eval_status.setStyleSheet("")

        trade_status = self._trade_status_text(rec)
        self.d_trade_status.setText(trade_status)
        if trade_status == "traded":
            self.d_trade_status.setStyleSheet("color: #1b5e20; font-weight: bold;")
        elif trade_status in ("pending", "submitted"):
            self.d_trade_status.setStyleSheet("color: #e65100; font-weight: bold;")
        elif trade_status == "orphan":
            self.d_trade_status.setStyleSheet("color: #c62828; font-weight: bold;")
        elif trade_status in ("expired", "skipped"):
            self.d_trade_status.setStyleSheet("color: #888;")
        else:
            self.d_trade_status.setStyleSheet("")

        trade = self._resolve_trade(rec)
        trade_id = self._parse_trade_id(rec.trade_id)
        if trade:
            display_trade_id = trade.get("id", trade_id)
            self.d_trade_id.setText(str(display_trade_id))
        else:
            self.d_trade_id.setText(str(trade_id) if trade_id is not None else "—")

        warning = ""
        if trade_status == "orphan" and trade_id is not None:
            warning = (
                f"Trade #{trade_id} is not in the trades table "
                f"(consensus.trade_id may point to an order id or a deleted row)."
            )
        elif trade and trade_id is not None and str(trade.get("id")) != str(trade_id):
            warning = (
                f"consensus.trade_id={trade_id} does not match trades.id={trade.get('id')}; "
                "use repair_consensus_trade_links.py to fix."
            )
        elif trade_status == "submitted":
            warning = "Order submitted; no linked trade row yet."
        self.d_trade_warning.setText(warning)

        can_open = trade is not None
        self.show_in_trading_btn.setEnabled(can_open and self._open_trading_callback is not None)
        if can_open:
            resolved_id = trade.get("id", trade_id)
            self.show_in_trading_btn.setProperty("trade_id", resolved_id)
            self.show_in_trading_btn.setProperty("consensus_id", rec.id)
            self.show_in_trading_btn.setProperty("ticker", str(rec.ticker or ""))
        else:
            self.show_in_trading_btn.setProperty("trade_id", None)
            self.show_in_trading_btn.setProperty("consensus_id", rec.id)
            self.show_in_trading_btn.setProperty("ticker", str(rec.ticker or ""))

        self.d_actual_date.setText(str(rec.actual_date or "")[:10] or "—")
        self.d_eval_close.setText(_fmt(rec.actual_close, 2))

        trade_entry = None
        trade_exit = None
        trade_close_reason = ""
        if trade:
            # Show actual entry price only if IB fill was confirmed (entry_filled_at set)
            entry_filled_at = trade.get("entry_filled_at") or ""
            if entry_filled_at:
                trade_entry = trade.get("entry_price")
            trade_exit = trade.get("exit_price")
            trade_close_reason = str(trade.get("close_reason") or "").upper()

        entry_actual = trade_entry if trade_entry not in (None, "") else rec.entry_price_actual
        self.d_entry_actual.setText(_fmt(entry_actual, 2) if entry_actual not in (None, "") else "—")
        self.d_actual_close.setText(_fmt(trade_exit, 2) if trade_exit not in (None, "") else "—")
        if trade_exit not in (None, "") and trade_close_reason == "STOP_LOSS":
            self.d_actual_stop.setText(_fmt(trade_exit, 2))
        else:
            self.d_actual_stop.setText("—")

        self.d_direction.setText(_bool_txt(rec.direction_correct))
        self.d_target_hit.setText(_bool_txt(rec.target_hit))
        self.d_stop_hit.setText(_bool_txt(rec.stop_hit))
        first_hit = str(rec.first_hit or "")
        if first_hit == "target":
            self.d_first_hit.setText("target ✅")
            self.d_first_hit.setStyleSheet("color: #1b5e20; font-weight: bold;")
        elif first_hit == "stop":
            self.d_first_hit.setText("stop ❌")
            self.d_first_hit.setStyleSheet("color: #b71c1c; font-weight: bold;")
        else:
            self.d_first_hit.setText("—")
            self.d_first_hit.setStyleSheet("")

        pnl = rec.pnl_pct
        if pnl is not None:
            try:
                pnl_f = float(pnl)
                self.d_pnl_pct.setText(f"{pnl_f:+.2f}%")
                self.d_pnl_pct.setStyleSheet("color: #1b5e20; font-weight: bold;" if pnl_f >= 0 else "color: #b71c1c; font-weight: bold;")
            except Exception:
                self.d_pnl_pct.setText(str(pnl))
                self.d_pnl_pct.setStyleSheet("")
        else:
            self.d_pnl_pct.setText("—")
            self.d_pnl_pct.setStyleSheet("")

        self.d_r_multiple.setText(_fmt(rec.r_multiple, 2))

    def _on_show_in_trading(self):
        if self._open_trading_callback is None:
            return
        trade_id = self.show_in_trading_btn.property("trade_id")
        consensus_id = self.show_in_trading_btn.property("consensus_id")
        ticker = str(self.show_in_trading_btn.property("ticker") or "")
        try:
            trade_id_int = int(trade_id) if trade_id is not None else None
        except Exception:
            trade_id_int = None
        try:
            consensus_id_int = int(consensus_id) if consensus_id is not None else None
        except Exception:
            consensus_id_int = None
        self._open_trading_callback(
            trade_id=trade_id_int,
            consensus_id=consensus_id_int,
            ticker=ticker or None,
        )
