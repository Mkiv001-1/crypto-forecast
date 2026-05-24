"""Portfolio history tab — Bybit Unified Trading summary (top) and history table (bottom)."""

import logging
from datetime import date
from typing import Any, Callable, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scripts.client.api_client import ForecastApiClient
from scripts.client.activity_runtime import window_run_activity as _window_run_activity

logger = logging.getLogger(__name__)


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pnl_color(value: float) -> QColor:
    if value > 0:
        return QColor("#2e7d32")
    if value < 0:
        return QColor("#c62828")
    return QColor("#263238")


def _format_num(value: Any, *, decimals: int = 4) -> str:
    f = _as_float(value)
    if value in (None, "", "--"):
        return "--"
    text = f"{f:,.{decimals}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _format_type_label(trans_type: str) -> str:
    t = (trans_type or "").strip().upper()
    if not t:
        return "--"
    return t.replace("_", " ").title()


def _direction_color(direction: str) -> QColor:
    d = (direction or "").lower()
    if "sell" in d:
        return QColor("#c62828")
    if "buy" in d:
        return QColor("#2e7d32")
    return QColor("#263238")


class PortfolioHistoryTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._position_rows: List[dict] = []
        self._transaction_rows: List[dict] = []
        self._uta_transaction_rows: List[dict] = []
        self._transactions_loaded = False
        self._uta_transactions_loaded = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(self._build_summary_panel())

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Ticker:"))
        self.ticker_combo = QComboBox()
        self.ticker_combo.setMinimumWidth(120)
        self.ticker_combo.addItem("ALL", "")
        filter_row.addWidget(self.ticker_combo)

        filter_row.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(date.today().replace(day=1))
        filter_row.addWidget(self.from_date)

        filter_row.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(date.today())
        filter_row.addWidget(self.to_date)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.on_refresh)
        filter_row.addWidget(self.refresh_btn)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        history_label = QLabel("Portfolio Logs")
        history_label.setStyleSheet("font-weight: bold; color: #455a64; margin-top: 4px;")
        layout.addWidget(history_label)

        self.history_tabs = QTabWidget()
        self.uta_transaction_table = self._create_uta_transaction_table()
        self.transaction_table = self._create_transaction_table()
        self.position_table = self._create_position_table()
        self.history_tabs.addTab(self.uta_transaction_table, "Transactions")
        self.history_tabs.addTab(self.transaction_table, "Transaction Log")
        self.history_tabs.addTab(self.position_table, "Position history (legacy)")
        self.history_tabs.currentChanged.connect(self._on_history_sub_tab_changed)
        layout.addWidget(self.history_tabs, 1)

        self.total_label = QLabel("Rows: 0")
        layout.addWidget(self.total_label)

    def _create_position_table(self) -> QTableWidget:
        table = QTableWidget(0, 9)
        table.setHorizontalHeaderLabels([
            "Timestamp", "Ticker", "Equity", "Unrealized PnL", "Realized PnL",
            "Cumulative PnL", "Volume", "Price", "Account",
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        return table

    def _create_uta_transaction_table(self) -> QTableWidget:
        table = QTableWidget(0, 13)
        table.setHorizontalHeaderLabels([
            "Time", "Currency", "Contract", "Type", "Direction",
            "Quantity", "Position", "Filled Price", "Funding",
            "Fee Paid", "Cash Flow", "Change", "Wallet Balance",
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(12, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        return table

    def _create_transaction_table(self) -> QTableWidget:
        table = QTableWidget(0, 10)
        table.setHorizontalHeaderLabels([
            "Occurred At", "Ticker", "Event Source", "Event Type", "Operation Status",
            "Status Before", "Status After", "Bybit Order ID", "Trade UID", "Error",
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)
        return table

    def _build_summary_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setStyleSheet(
            "QFrame { background: #fafafa; border: 1px solid #cfd8dc; border-radius: 6px; }"
        )

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.summary_title = QLabel("Unified Trading")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        self.summary_title.setFont(title_font)
        header.addWidget(self.summary_title)

        self.summary_mode = QLabel("")
        self.summary_mode.setStyleSheet(
            "background: #fff3e0; color: #e65100; padding: 2px 8px; border-radius: 4px;"
        )
        header.addWidget(self.summary_mode)
        header.addStretch()

        self.summary_status = QLabel("")
        self.summary_status.setStyleSheet("color: #607d8b;")
        header.addWidget(self.summary_status)
        outer.addLayout(header)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(24)
        metrics.setVerticalSpacing(4)

        equity_caption = QLabel("Total Equity")
        equity_caption.setStyleSheet("color: #607d8b;")
        metrics.addWidget(equity_caption, 0, 0)

        self.equity_value = QLabel("—")
        equity_font = QFont()
        equity_font.setPointSize(20)
        equity_font.setBold(True)
        self.equity_value.setFont(equity_font)
        metrics.addWidget(self.equity_value, 1, 0)

        upnl_caption = QLabel("Unrealized PnL of Perpetual and Futures")
        upnl_caption.setStyleSheet("color: #607d8b;")
        metrics.addWidget(upnl_caption, 0, 1)

        self.upnl_value = QLabel("—")
        upnl_font = QFont()
        upnl_font.setPointSize(16)
        upnl_font.setBold(True)
        self.upnl_value.setFont(upnl_font)
        metrics.addWidget(self.upnl_value, 1, 1)

        outer.addLayout(metrics)

        self.assets_table = QTableWidget(0, 3)
        self.assets_table.setHorizontalHeaderLabels([
            "Currency", "Equity", "Wallet Balance",
        ])
        self.assets_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.assets_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assets_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.assets_table.setMaximumHeight(180)
        self.assets_table.verticalHeader().setVisible(False)
        outer.addWidget(self.assets_table)

        return panel

    def on_refresh(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Refreshing…")

        date_from = self.from_date.date().toString("yyyy-MM-dd")
        date_to = self.to_date.date().toString("yyyy-MM-dd")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Syncing Unified Trading account from Bybit…")
            result = self.api.trigger_portfolio_history_snapshot(
                date_from=date_from,
                date_to=date_to,
            )
            added = int(result.get("snapshots_added", 0) or 0) if isinstance(result, dict) else 0
            equity = _as_float(result.get("total_equity")) if isinstance(result, dict) else 0
            tx = result.get("transaction_log") if isinstance(result, dict) else {}
            tx_synced = int((tx or {}).get("synced", 0) or 0)
            log(
                "INFO",
                f"Sync complete ({added} snapshot row(s), {tx_synced} transaction log row(s), "
                f"equity ${equity:,.2f}).",
            )
            return result

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            QMessageBox.warning(self, "Sync failed", error)

        def on_finished():
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("🔄 Refresh")

        try:
            _window_run_activity(
                self,
                operation_id="portfolio.refresh",
                title="Portfolio",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            on_finished()
            QMessageBox.critical(self, "Error", str(e))

    def _on_history_sub_tab_changed(self, index: int) -> None:
        if index == 0 and not self._uta_transactions_loaded:
            self._load_uta_transactions()
        elif index == 1 and not self._transactions_loaded:
            self._load_transactions()
        self._update_total_label()

    def _load_uta_transactions(self) -> None:
        symbol = self.ticker_combo.currentData() or None
        date_from = self.from_date.date().toString("yyyy-MM-dd")
        date_to = self.to_date.date().toString("yyyy-MM-dd")
        try:
            resp = self.api.get_portfolio_transaction_log(
                symbol=symbol or None,
                date_from=date_from,
                date_to=date_to,
                limit=5000,
            )
            items = resp.get("items", []) if isinstance(resp, dict) else []
            self._uta_transaction_rows = items if isinstance(items, list) else []
            self._uta_transactions_loaded = True
            self._populate_uta_transaction_table()
        except Exception as e:
            logger.warning("portfolio UTA transactions load failed: %s", e)

    def _load_transactions(self) -> None:
        ticker = self.ticker_combo.currentData() or None
        date_from = self.from_date.date().toString("yyyy-MM-dd")
        date_to = self.to_date.date().toString("yyyy-MM-dd")
        try:
            tx_rows = self.api.get_bybit_transactions(
                ticker=ticker,
                date_from=date_from,
                date_to=date_to,
                limit=500,
            )
            rows = tx_rows if isinstance(tx_rows, list) else []
            self._transaction_rows = self._filter_transaction_rows_by_date(
                rows,
                date_from=date_from,
                date_to=date_to,
            )
            self._transactions_loaded = True
            self._populate_transaction_table()
        except Exception as e:
            logger.warning("portfolio transactions load failed: %s", e)

    def load(self):
        try:
            ticker = self.ticker_combo.currentData() or None
            date_from = self.from_date.date().toString("yyyy-MM-dd")
            date_to = self.to_date.date().toString("yyyy-MM-dd")
            self._transactions_loaded = False
            self._uta_transactions_loaded = False
            resp = self.api.get_portfolio_history(
                ticker=ticker, date_from=date_from, date_to=date_to
            )
            self._position_rows = resp.get("items", []) if isinstance(resp, dict) else []
            self._populate_position_table()
            self._refresh_ticker_filter()
            self._update_unified_summary(live=False)
            self._load_uta_transactions()
            self._load_transactions()
            self._update_total_label()
        except Exception as e:
            self._set_summary_unavailable(str(e))
            QMessageBox.critical(self, "Error", f"Failed to load portfolio history data:\n{e}")

    def _set_summary_unavailable(self, message: str):
        self.equity_value.setText("—")
        self.upnl_value.setText("—")
        self.summary_status.setText(message)
        self.assets_table.setRowCount(0)

    def _update_unified_summary(self, *, live: bool = False):
        try:
            resp = self.api.get_portfolio_unified_summary(live=live)
        except Exception as e:
            logger.warning("portfolio unified summary failed: %s", e)
            if live:
                try:
                    resp = self.api.get_portfolio_unified_summary(live=False)
                except Exception as e2:
                    self._set_summary_unavailable(f"Unavailable ({e2})")
                    return
            else:
                self._set_summary_unavailable(f"Unavailable ({e})")
                return

        if not isinstance(resp, dict):
            self._set_summary_unavailable("Invalid response")
            return

        available = bool(resp.get("available"))
        source = str(resp.get("source") or "")
        mode = str(resp.get("mode") or "")
        profile = str(resp.get("profile") or "")

        self.summary_title.setText("Unified Trading")
        self.summary_mode.setText(mode or profile or "Bybit")

        total_equity = _as_float(resp.get("total_equity"))
        total_perp_upl = _as_float(resp.get("total_perp_upl"))
        ts = str(resp.get("timestamp") or "")[:19]

        self.equity_value.setText(f"${total_equity:,.2f} USD")
        self.upnl_value.setText(f"${total_perp_upl:,.2f} USD")
        self.upnl_value.setStyleSheet(f"color: {_pnl_color(total_perp_upl).name()};")

        if available:
            status = f"Updated {ts}" if ts else "Synced"
            if source == "cached":
                status += " (cached)"
            self.summary_status.setText(status)
        else:
            self.summary_status.setText(
                "No data — press Refresh or sync in Settings → Accounts"
            )

        self._populate_assets_table(resp.get("coins") or [])

    def _populate_assets_table(self, coins: List[dict]):
        self.assets_table.setRowCount(0)
        for row_idx, coin in enumerate(coins):
            code = str(coin.get("coin") or "")
            equity = _as_float(coin.get("equity"))
            usd_value = _as_float(coin.get("usd_value"))
            wallet = _as_float(coin.get("wallet_balance"))

            equity_text = f"{equity:,.8f}".rstrip("0").rstrip(".")
            if usd_value > 0:
                equity_text += f"  (≈ ${usd_value:,.2f})"

            wallet_text = f"{wallet:,.8f}".rstrip("0").rstrip(".")

            self.assets_table.insertRow(row_idx)
            for col, text in enumerate([code, equity_text, wallet_text]):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.assets_table.setItem(row_idx, col, item)

    def _populate_position_table(self):
        self.position_table.setSortingEnabled(False)
        self.position_table.setRowCount(0)
        for r, row in enumerate(self._position_rows):
            vals = [
                str(row.get("timestamp", "")),
                str(row.get("ticker", "")),
                f"{row.get('equity', 0):,.2f}",
                f"{row.get('unrealized_pnl', 0):,.2f}",
                f"{row.get('realized_pnl', 0):,.2f}",
                f"{row.get('cumulative_pnl', 0):,.2f}",
                f"{row.get('volume', 0):,.2f}",
                f"{row.get('price', 0):,.2f}",
                str(row.get("account", "")),
            ]
            self.position_table.insertRow(r)
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c in (3, 4, 5):
                    try:
                        val = float(v.replace(",", ""))
                        item.setForeground(QBrush(_pnl_color(val)))
                    except Exception:
                        pass
                self.position_table.setItem(r, c, item)
        self.position_table.setSortingEnabled(True)

    def _populate_transaction_table(self):
        self.transaction_table.setSortingEnabled(False)
        self.transaction_table.setRowCount(0)
        for r, row in enumerate(self._transaction_rows):
            values = [
                str(row.get("occurred_at", "")),
                str(row.get("ticker", "")),
                str(row.get("event_source", "")),
                str(row.get("event_type", "")),
                str(row.get("operation_status", "")),
                str(row.get("status_before", "")),
                str(row.get("status_after", "")),
                str(row.get("bybit_order_id", "")),
                str(row.get("trade_uid", "")),
                str(row.get("error_message", "")),
            ]
            self.transaction_table.insertRow(r)
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 4:
                    status = value.lower()
                    if status in {"ok", "success"}:
                        item.setForeground(QBrush(QColor("#2e7d32")))
                    elif status in {"error", "failed"}:
                        item.setForeground(QBrush(QColor("#c62828")))
                if c == 9 and value:
                    item.setForeground(QBrush(QColor("#c62828")))
                self.transaction_table.setItem(r, c, item)
        self.transaction_table.setSortingEnabled(True)

    def _populate_uta_transaction_table(self):
        self.uta_transaction_table.setSortingEnabled(False)
        self.uta_transaction_table.setRowCount(0)
        for r, row in enumerate(self._uta_transaction_rows):
            symbol = str(row.get("symbol") or "").strip()
            contract = symbol if symbol else "--"
            direction = str(row.get("direction") or "--")
            time_text = str(row.get("transaction_time", ""))[:19].replace("T", " ")
            currency = str(row.get("currency") or "")
            fee_text = _format_num(row.get("fee"), decimals=8)
            if currency and fee_text != "--":
                fee_text = f"{fee_text} {currency}"

            values = [
                time_text,
                currency or "--",
                contract,
                _format_type_label(str(row.get("type") or "")),
                direction,
                _format_num(row.get("qty")),
                _format_num(row.get("size")),
                _format_num(row.get("trade_price"), decimals=8),
                _format_num(row.get("funding"), decimals=8),
                fee_text,
                _format_num(row.get("cash_flow"), decimals=4),
                _format_num(row.get("change"), decimals=4),
                _format_num(row.get("cash_balance"), decimals=8),
            ]
            self.uta_transaction_table.insertRow(r)
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 4:
                    item.setForeground(QBrush(_direction_color(direction)))
                if c in (9, 10, 11):
                    num = _as_float(
                        row.get("fee") if c == 9 else row.get("cash_flow") if c == 10 else row.get("change")
                    )
                    if num != 0:
                        item.setForeground(QBrush(_pnl_color(num)))
                self.uta_transaction_table.setItem(r, c, item)
        self.uta_transaction_table.setSortingEnabled(True)

    def _filter_transaction_rows_by_date(
        self,
        rows: List[dict],
        *,
        date_from: str,
        date_to: str,
    ) -> List[dict]:
        if not rows:
            return []
        result: List[dict] = []
        for row in rows:
            occurred = str(row.get("occurred_at", ""))
            date_part = occurred[:10]
            if len(date_part) != 10:
                result.append(row)
                continue
            if date_from <= date_part <= date_to:
                result.append(row)
        return result

    def _update_total_label(self):
        tab_idx = self.history_tabs.currentIndex() if hasattr(self, "history_tabs") else 0
        if tab_idx == 0:
            self.total_label.setText(
                f"Transaction log rows: {len(self._uta_transaction_rows)}"
            )
        elif tab_idx == 1:
            self.total_label.setText(f"Audit rows: {len(self._transaction_rows)}")
        else:
            self.total_label.setText(f"Position rows: {len(self._position_rows)}")

    def _refresh_ticker_filter(self):
        uta_symbols = {
            str(row.get("symbol", ""))
            for row in self._uta_transaction_rows
            if row.get("symbol")
        }
        tickers = sorted({
            str(row.get("ticker", ""))
            for row in (self._position_rows + self._transaction_rows)
            if row.get("ticker")
        } | uta_symbols)
        current = self.ticker_combo.currentData()
        self.ticker_combo.blockSignals(True)
        self.ticker_combo.clear()
        self.ticker_combo.addItem("ALL", "")
        for t in tickers:
            self.ticker_combo.addItem(t, t)
        idx = self.ticker_combo.findData(current)
        if idx >= 0:
            self.ticker_combo.setCurrentIndex(idx)
        self.ticker_combo.blockSignals(False)
