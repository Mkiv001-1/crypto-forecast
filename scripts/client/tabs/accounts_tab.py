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
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class AccountsTab(QWidget):
    _COL_HEADERS = [
        "Profile", "Mode", "UID", "Account Type",
        "Equity (USDT)", "Available (USDT)", "Unrealized PnL",
        "Positions", "Active", "Connected", "Last Sync",
    ]

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._accounts: List[AccountRecord] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.sync_btn = QPushButton("Sync with Bybit")
        self.sync_btn.setToolTip("Fetch account balances from Bybit (active profile only)")
        self.sync_btn.clicked.connect(self._on_sync)
        toolbar.addWidget(self.sync_btn)
        toolbar.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self._COL_HEADERS))
        self.table.setHorizontalHeaderLabels(self._COL_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        self.summary_label = QLabel("Accounts: 0 | Active profile equity: —")
        layout.addWidget(self.summary_label)

        hint = QLabel("Double-click an inactive profile to switch to it as active.")
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(hint)

    def _on_sync(self):
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("Syncing…")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Syncing account balances from Bybit...")
            result = self.api.sync_accounts()
            log("INFO", "Account balances synchronized.")
            return result

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            logger.warning(f"Account sync failed: {error}")
            QMessageBox.warning(self, "Sync Failed", error)

        def on_finished():
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("Sync with Bybit")

        try:
            _window_run_activity(
                self,
                operation_id="accounts.sync",
                title="Sync Accounts",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("Sync with Bybit")
            QMessageBox.critical(self, "Sync Failed", str(e))

    def _on_double_click(self, row: int, _col: int):
        if row < 0 or row >= len(self._accounts):
            return
        acc = self._accounts[row]
        if acc.active:
            QMessageBox.information(self, "Already Active",
                                    f"Profile '{acc.profile}' is already the active profile.")
            return
        reply = QMessageBox.question(
            self, "Switch Active Profile",
            f"Switch active Bybit profile to '{acc.profile}'?\n\n"
            f"The server will need to be restarted to connect with the new credentials.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from scripts.shared.models import ConfigParam
            self.api.update_config(
                "BYBIT_ACTIVE_PROFILE",
                ConfigParam(key="BYBIT_ACTIVE_PROFILE", value=acc.profile or "demo"),
            )
            QMessageBox.information(self, "Profile Switched",
                                    f"Active profile set to '{acc.profile}'.\n"
                                    f"Restart the server to apply.")
            self.load()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to switch profile:\n{e}")

    def load(self):
        try:
            resp = self.api.get_accounts()
            self._accounts = resp.items
            self._populate_table()
            self._update_summary()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load accounts:\n{e}")

    def _populate_table(self):
        _ACTIVE_BG = QColor("#d4edda")
        _INACTIVE_BG = QColor("#ffffff")
        _DISCONNECTED_BG = QColor("#fff3cd")

        self.table.setRowCount(len(self._accounts))
        for r, acc in enumerate(self._accounts):
            has_data = acc.net_liquidation is not None

            def _fmt_usd(v):
                if v is None:
                    return ""
                try:
                    fv = float(v)
                    sign = "+" if fv > 0 else ""
                    return f"{sign}${fv:,.2f}" if fv != 0 else "$0.00"
                except Exception:
                    return str(v)

            def _fmt_pnl(v):
                if v is None:
                    return ""
                try:
                    fv = float(v)
                    sign = "+" if fv >= 0 else ""
                    return f"{sign}${fv:,.2f}"
                except Exception:
                    return str(v)

            last_sync = acc.last_update or ""
            if last_sync and "T" in last_sync:
                try:
                    last_sync = last_sync.split("T")[1][:8]
                except Exception:
                    pass

            vals = [
                acc.profile or "",
                acc.mode or "",
                acc.uid or "",
                acc.account_type or "UNIFIED",
                _fmt_usd(acc.net_liquidation) if has_data else "",
                _fmt_usd(acc.available_funds) if has_data else "",
                _fmt_pnl(acc.unrealized_pnl) if has_data else "",
                str(acc.positions_count) if acc.positions_count is not None else "",
                "✅" if acc.active else "—",
                "✅" if acc.connected else "❌",
                last_sync,
            ]

            if acc.active:
                row_bg = _ACTIVE_BG
            elif not acc.connected:
                row_bg = _DISCONNECTED_BG
            else:
                row_bg = _INACTIVE_BG

            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setBackground(QBrush(row_bg))
                # Right-align numeric columns
                if c in (4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Color PnL
                if c == 6 and v:
                    try:
                        pnl_val = float(v.replace("+", "").replace("$", "").replace(",", ""))
                        if pnl_val > 0:
                            item.setForeground(QBrush(QColor("#155724")))
                        elif pnl_val < 0:
                            item.setForeground(QBrush(QColor("#721c24")))
                    except Exception:
                        pass
                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()

    def _update_summary(self):
        active = next((a for a in self._accounts if a.active), None)
        total = len(self._accounts)
        if active and active.net_liquidation is not None:
            try:
                equity = float(active.net_liquidation)
                self.summary_label.setText(
                    f"Accounts: {total} | Active: {active.profile} ({active.mode}) | "
                    f"Equity: ${equity:,.2f} USDT"
                )
                return
            except Exception:
                pass
        self.summary_label.setText(f"Accounts: {total} | Active profile equity: —")
