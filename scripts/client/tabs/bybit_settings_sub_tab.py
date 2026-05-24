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

class _BybitSettingsSubTab(QWidget):
    """Sub-tab for Bybit trading settings."""

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── API Credentials ────────────────────────────────────────────────
        cred_group = QGroupBox("API Credentials")
        cred_layout = QVBoxLayout(cred_group)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Active Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.addItems(["demo", "live"])
        self.profile_combo.setMaximumWidth(200)
        self.profile_combo.setToolTip("Profile name (must match a [bybit_<name>] section in secrets.ini)")
        profile_row.addWidget(self.profile_combo)
        profile_row.addStretch()
        cred_layout.addLayout(profile_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter API key…")
        key_row.addWidget(self.api_key_edit)
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setMaximumWidth(32)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.show_key_btn)
        cred_layout.addLayout(key_row)

        secret_row = QHBoxLayout()
        secret_row.addWidget(QLabel("API Secret:"))
        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_secret_edit.setPlaceholderText("Enter API secret…")
        secret_row.addWidget(self.api_secret_edit)
        self.show_secret_btn = QPushButton("👁")
        self.show_secret_btn.setMaximumWidth(32)
        self.show_secret_btn.setCheckable(True)
        self.show_secret_btn.toggled.connect(
            lambda checked: self.api_secret_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        secret_row.addWidget(self.show_secret_btn)
        cred_layout.addLayout(secret_row)

        self.cred_status_label = QLabel("")
        self.cred_status_label.setStyleSheet("color: #888888; font-size: 11px;")
        cred_layout.addWidget(self.cred_status_label)

        cred_btn_row = QHBoxLayout()
        self.save_cred_btn = QPushButton("💾 Save to secrets.ini")
        self.save_cred_btn.setToolTip(
            "Saves the key+secret to secrets.ini on the server (not in git).\n"
            "Also sets this profile as active."
        )
        self.save_cred_btn.clicked.connect(self._save_credentials)
        cred_btn_row.addWidget(self.save_cred_btn)
        cred_btn_row.addStretch()
        cred_layout.addLayout(cred_btn_row)

        layout.addWidget(cred_group)

        # Scheduler Settings
        conn_group = QGroupBox("Scheduler Settings")
        conn_layout = QVBoxLayout(conn_group)

        workers_row = QHBoxLayout()
        workers_row.addWidget(QLabel("Scheduler Max Workers:"))
        self.scheduler_workers_spin = QSpinBox()
        self.scheduler_workers_spin.setRange(1, 16)
        self.scheduler_workers_spin.setValue(4)
        self.scheduler_workers_spin.setMaximumWidth(120)
        workers_row.addWidget(self.scheduler_workers_spin)
        workers_row.addWidget(QLabel("Thread pool size for scheduler background tasks"))
        workers_row.addStretch()
        conn_layout.addLayout(workers_row)

        layout.addWidget(conn_group)

        # Trading Settings
        trading_group = QGroupBox("Trading Settings")
        trading_layout = QVBoxLayout(trading_group)

        order_type_row = QHBoxLayout()
        order_type_row.addWidget(QLabel("Default Order Type:"))
        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(["Market", "Limit"])
        self.order_type_combo.setMaximumWidth(200)
        order_type_row.addWidget(self.order_type_combo)
        order_type_row.addStretch()
        trading_layout.addLayout(order_type_row)

        tif_row = QHBoxLayout()
        tif_row.addWidget(QLabel("Time in Force:"))
        self.tif_combo = QComboBox()
        self.tif_combo.addItems(["GTC", "IOC", "FOK"])
        self.tif_combo.setMaximumWidth(200)
        tif_row.addWidget(self.tif_combo)
        tif_row.addStretch()
        trading_layout.addLayout(tif_row)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["linear", "spot", "inverse"])
        self.category_combo.setMaximumWidth(200)
        category_row.addWidget(self.category_combo)
        category_row.addStretch()
        trading_layout.addLayout(category_row)

        leverage_row = QHBoxLayout()
        leverage_row.addWidget(QLabel("Default Leverage:"))
        self.leverage_spin = QSpinBox()
        self.leverage_spin.setRange(1, 100)
        self.leverage_spin.setValue(3)
        self.leverage_spin.setMaximumWidth(120)
        leverage_row.addWidget(self.leverage_spin)
        leverage_row.addStretch()
        trading_layout.addLayout(leverage_row)

        max_leverage_row = QHBoxLayout()
        max_leverage_row.addWidget(QLabel("Max Leverage:"))
        self.max_leverage_spin = QSpinBox()
        self.max_leverage_spin.setRange(1, 100)
        self.max_leverage_spin.setValue(10)
        self.max_leverage_spin.setMaximumWidth(120)
        max_leverage_row.addWidget(self.max_leverage_spin)
        max_leverage_row.addStretch()
        trading_layout.addLayout(max_leverage_row)

        order_mode_row = QHBoxLayout()
        order_mode_row.addWidget(QLabel("Order Mode:"))
        self.order_mode_combo = QComboBox()
        self.order_mode_combo.addItems(["disabled", "paper", "live"])
        self.order_mode_combo.setMaximumWidth(200)
        order_mode_row.addWidget(self.order_mode_combo)
        order_mode_row.addStretch()
        trading_layout.addLayout(order_mode_row)

        layout.addWidget(trading_group)

        # Save button
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    def _save_credentials(self):
        profile = self.profile_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        if not profile:
            QMessageBox.warning(self, "Validation", "Profile name is required.")
            return
        if not api_key or not api_secret:
            QMessageBox.warning(self, "Validation", "API Key and API Secret are required.")
            return
        try:
            self.api.put_bybit_credentials(profile, api_key, api_secret, set_active=True)
            self.cred_status_label.setText(f"Credentials saved for profile '{profile}'.")
            self.cred_status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
            QMessageBox.information(self, "Saved", f"Credentials saved for profile '{profile}'.")
        except Exception as e:
            self.cred_status_label.setText(f"Error: {e}")
            self.cred_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
            QMessageBox.critical(self, "Error", f"Failed to save credentials:\n{e}")

    def _save_settings(self):
        from scripts.shared.models import ConfigParam
        keys = {
            "SCHEDULER_MAX_WORKERS": str(self.scheduler_workers_spin.value()),
            "DEFAULT_ORDER_TYPE": self.order_type_combo.currentText(),
            "DEFAULT_TIME_IN_FORCE": self.tif_combo.currentText(),
            "BYBIT_DEFAULT_CATEGORY": self.category_combo.currentText(),
            "BYBIT_DEFAULT_LEVERAGE": str(self.leverage_spin.value()),
            "BYBIT_MAX_LEVERAGE": str(self.max_leverage_spin.value()),
            "ORDER_MODE": self.order_mode_combo.currentText(),
        }
        errors = []
        for key, value in keys.items():
            try:
                self.api.update_config(key, ConfigParam(key=key, value=value))
            except Exception as e:
                errors.append(f"{key}: {e}")
        if errors:
            QMessageBox.warning(self, "Partial Save", "Some settings failed to save:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Saved", "Settings saved.")

    def load(self):
        try:
            cfg = self.api.get_config()
            cfg_map = {c.key: c.value for c in cfg.items}

            workers = cfg_map.get("SCHEDULER_MAX_WORKERS", "4")
            try:
                self.scheduler_workers_spin.setValue(max(1, min(16, int(workers))))
            except Exception:
                self.scheduler_workers_spin.setValue(4)

            order_type = cfg_map.get("DEFAULT_ORDER_TYPE", "Market")
            idx = self.order_type_combo.findText(order_type)
            if idx >= 0:
                self.order_type_combo.setCurrentIndex(idx)

            tif = cfg_map.get("DEFAULT_TIME_IN_FORCE", "GTC")
            idx = self.tif_combo.findText(tif)
            if idx >= 0:
                self.tif_combo.setCurrentIndex(idx)

            category = cfg_map.get("BYBIT_DEFAULT_CATEGORY", "linear")
            idx = self.category_combo.findText(category)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)

            try:
                self.leverage_spin.setValue(max(1, min(100, int(cfg_map.get("BYBIT_DEFAULT_LEVERAGE", "3")))))
            except Exception:
                self.leverage_spin.setValue(3)

            try:
                self.max_leverage_spin.setValue(max(1, min(100, int(cfg_map.get("BYBIT_MAX_LEVERAGE", "10")))))
            except Exception:
                self.max_leverage_spin.setValue(10)

            order_mode = cfg_map.get("ORDER_MODE", "disabled")
            idx = self.order_mode_combo.findText(order_mode)
            if idx >= 0:
                self.order_mode_combo.setCurrentIndex(idx)
        except Exception:
            pass




# ---------------------------------------------------------------------------
# Prompts Tab
# ---------------------------------------------------------------------------

_VARIABLES_HELP = """\
Доступные переменные шаблона:

  {ticker}          — тикер (BTCUSDT)
  {forecast_date}   — дата прогноза
  {horizon}         — горизонт в днях
  {market_regime}   — рыночный режим
  {market_context}  — crypto-контекст (BTC/ETH, funding)
  {history}         — история метода (win rate, PnL)
  {footer}          — инструкция формата JSON (вставлять в конец)

  {price}           — текущая цена
  {ma20}  {ma50}  {ma200}
  {ema9}  {ema21}
  {rsi}             — RSI(14)
  {adx}             — ADX(14)
  {macd}  {macd_hist}
  {stoch_rsi}
  {atr}             — ATR в $
  {atr_pct}         — ATR в %
  {bb_upper}  {bb_lower}  {bb_pos}  {bb_width}
  {obv_trend}       — «↑ бычий» / «↓ медвежий»
  {change_5d}  {change_10d}  {change_20d}  {change_50d}
  {volume_current}  {vol_ratio}  {ma20_dev}

Формат числовых переменных: {price:.2f}, {rsi:.1f}, {adx:.1f}
"""

_METHOD_LABELS = {
    "momentum_trend":    "📈 Momentum Trend",
    "price_action":      "🕯 Price Action",
    "relative_strength": "💪 Relative Strength",
    "volatility":        "⚡ Volatility Breakout",
    "mean_reversion":    "↩ Mean Reversion",
    "volume_breakout":   "📦 Volume Breakout",
}
