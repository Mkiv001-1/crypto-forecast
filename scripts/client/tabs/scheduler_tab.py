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
from scripts.client.constants import _HB_ERR, _HB_OK, _TASK_STATUS_COLORS
from scripts.client.tabs.status_poller import StatusPoller

logger = logging.getLogger(__name__)


def _status_brush(status: str) -> QBrush:
    """Map task status string to a safe QBrush (never pass invalid types to QBrush)."""
    key = (status or "").strip().lower()
    hex_color = _TASK_STATUS_COLORS.get(key, _TASK_STATUS_COLORS.get("", "#ffffff"))
    if not isinstance(hex_color, str) or not hex_color.startswith("#"):
        hex_color = "#ffffff"
    return QBrush(QColor(hex_color))


class SchedulerTab(QWidget):
    """Main Scheduler tab: manual run buttons + task list + heartbeat log."""

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._tasks: list = []
        self._poller: Optional[StatusPoller] = None
        self._last_log_count = 0
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.load)
        self._auto_refresh_enabled = False

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Manual Run section ---
        run_group = QGroupBox("Manual Run")
        run_layout = QVBoxLayout(run_group)

        btn_row = QHBoxLayout()
        self.forecast_btn = QPushButton("🤖 Forecast")
        self.forecast_btn.setMinimumHeight(36)
        self.forecast_btn.clicked.connect(lambda: self._run("forecast"))
        btn_row.addWidget(self.forecast_btn)

        self.price_data_btn = QPushButton("📈 Price Data")
        self.price_data_btn.setMinimumHeight(36)
        self.price_data_btn.clicked.connect(lambda: self._run("price_data"))
        btn_row.addWidget(self.price_data_btn)

        self.evaluate_btn = QPushButton("📊 Evaluate")
        self.evaluate_btn.setMinimumHeight(36)
        self.evaluate_btn.clicked.connect(lambda: self._run("evaluate"))
        btn_row.addWidget(self.evaluate_btn)

        self.full_btn = QPushButton("🔄 RECALCULATE ALL")
        self.full_btn.setMinimumHeight(42)
        self.full_btn.setStyleSheet("font-weight: bold; font-size: 12px; background-color: #1976d2; color: white;")
        self.full_btn.clicked.connect(lambda: self._run("full"))
        btn_row.addWidget(self.full_btn)

        btn_row.addStretch()
        run_layout.addLayout(btn_row)

        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("Status:"))
        self.status_label = QLabel("● IDLE")
        self.status_label.setFont(QFont("", 10, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #555;")
        info_row.addWidget(self.status_label)
        info_row.addSpacing(30)
        info_row.addWidget(QLabel("Started:"))
        self.started_label = QLabel("—")
        info_row.addWidget(self.started_label)
        info_row.addSpacing(20)
        info_row.addWidget(QLabel("Duration:"))
        self.duration_label = QLabel("—")
        info_row.addWidget(self.duration_label)
        info_row.addStretch()
        run_layout.addLayout(info_row)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        self.log_edit.setMaximumHeight(120)
        run_layout.addWidget(self.log_edit)

        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.log_edit.clear)
        clear_row.addWidget(self.clear_btn)
        run_layout.addLayout(clear_row)

        layout.addWidget(run_group)

        # --- Tasks table ---
        tasks_group = QGroupBox("Scheduled Tasks")
        tasks_layout = QVBoxLayout(tasks_group)

        task_btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("↺ Refresh")
        self.refresh_btn.clicked.connect(self.load)
        task_btn_row.addWidget(self.refresh_btn)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self._save)
        task_btn_row.addWidget(self.save_btn)
        task_btn_row.addStretch()
        tasks_layout.addLayout(task_btn_row)

        self.tasks_table = QTableWidget()
        self.tasks_table.setColumnCount(9)
        self.tasks_table.setHorizontalHeaderLabels([
            "Active", "Name", "Interval (s)", "Last Run", "Status",
            "Runs", "Errors", "Last Error", "Run Now",
        ])
        hdr = self.tasks_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tasks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tasks_layout.addWidget(self.tasks_table)
        layout.addWidget(tasks_group, 1)

        # --- Heartbeat log ---
        hb_group = QGroupBox("Heartbeat Log (last 15)")
        hb_layout = QVBoxLayout(hb_group)

        self.hb_table = QTableWidget()
        self.hb_table.setColumnCount(5)
        self.hb_table.setHorizontalHeaderLabels(["Time", "Bybit", "OpenRouter", "SQLite", "Notes"])
        hb_hdr = self.hb_table.horizontalHeader()
        hb_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hb_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hb_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hb_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hb_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.hb_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.hb_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hb_layout.addWidget(self.hb_table)
        layout.addWidget(hb_group)

    # --- Manual run helpers ---

    def _run(self, mode: str):
        try:
            if mode == "forecast":
                resp = self.api.run_forecast()
            elif mode == "evaluate":
                resp = self.api.run_evaluate()
            elif mode == "price_data":
                resp = self.api.run_price_data()
            else:
                resp = self.api.run_full()
            self._set_run_buttons(False)
            self._apply_run_status(resp)
            self._start_polling()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start {mode}:\n{e}")

    def _set_run_buttons(self, enabled: bool):
        self.forecast_btn.setEnabled(enabled)
        self.price_data_btn.setEnabled(enabled)
        self.evaluate_btn.setEnabled(enabled)
        self.full_btn.setEnabled(enabled)

    def _start_polling(self):
        if self._poller and self._poller.isRunning():
            self._poller.stop()
        self._last_log_count = 0
        self._poller = StatusPoller(self.api)
        self._poller.status_updated.connect(self._apply_run_status)
        self._poller.finished.connect(lambda: self._set_run_buttons(True))
        self._poller.start()

    def _apply_run_status(self, resp):
        status = resp.status.upper()
        if status == "RUNNING":
            self.status_label.setText("● RUNNING")
            self.status_label.setStyleSheet("color: #f57f17; font-weight: bold;")
        elif status == "DONE":
            self.status_label.setText("● DONE")
            self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self._set_run_buttons(True)
        elif status == "ERROR":
            self.status_label.setText("● ERROR")
            self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")
            self._set_run_buttons(True)
        else:
            self.status_label.setText("● IDLE")
            self.status_label.setStyleSheet("color: #555; font-weight: bold;")
        if resp.started_at:
            self.started_label.setText(str(resp.started_at)[:19])
        if resp.duration_sec is not None:
            self.duration_label.setText(f"{resp.duration_sec:.1f}s")
        if resp.log_lines:
            new_lines = resp.log_lines[self._last_log_count:]
            if new_lines:
                self.log_edit.append("\n".join(new_lines))
                self._last_log_count = len(resp.log_lines)

    # --- Scheduler task helpers ---

    def load(self):
        self._load_tasks()
        self._load_heartbeat()

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        """Pause 30s polling when the Scheduler tab is not visible."""
        self._auto_refresh_enabled = enabled
        if enabled:
            if not self._timer.isActive():
                self._timer.start(30_000)
        else:
            self._timer.stop()

    def _load_tasks(self):
        try:
            self._tasks = self.api.get_scheduler_tasks()
            self._populate_tasks()
        except Exception as e:
            err_msg = str(e)
            # Suppress connection errors - MainWindow already shows connection error dialog
            if "timeout" in err_msg.lower() or "connection" in err_msg.lower():
                logger.debug(f"Scheduler tasks load skipped: server not connected")
            else:
                logger.warning(f"Scheduler tasks load error: {e}")

    def _populate_tasks(self):
        self.tasks_table.setRowCount(0)
        for row_idx, t in enumerate(self._tasks):
            self.tasks_table.insertRow(row_idx)

            # Active checkbox
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(bool(t.get("is_active", 1)))
            cb_layout.addWidget(cb)
            self.tasks_table.setCellWidget(row_idx, 0, cb_widget)

            name        = str(t.get("name", ""))
            interval    = str(t.get("schedule_value", ""))
            last_run    = str(t.get("last_run_at", "") or "—")
            status_val  = str(t.get("last_run_status", "") or "")
            if t.get("live_running"):
                status_val = "running"
            run_count   = str(t.get("run_count", 0))
            error_count = int(t.get("error_count", 0) or 0)
            last_error  = str(t.get("last_error", "") or "")

            cols = [name, interval, last_run, status_val, run_count, str(error_count), last_error]
            for col_idx, val in enumerate(cols, start=1):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 4:
                    item.setBackground(_status_brush(status_val))
                if col_idx == 6 and error_count > 0:
                    item.setForeground(QBrush(QColor("#c62828")))
                    item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.tasks_table.setItem(row_idx, col_idx, item)

            # Run Now button (col 8)
            run_btn = QPushButton("▶ Run")
            run_btn.setFixedHeight(24)
            run_btn.clicked.connect(lambda checked, task_name=name: self._trigger_task(task_name))
            self.tasks_table.setCellWidget(row_idx, 8, run_btn)

    def _trigger_task(self, task_name: str):
        _TASK_TO_MODE = {
            "forecast":           "forecast",
            "scheduled_forecast": "forecast",
            "evaluate":           "evaluate",
            "scheduled_evaluate": "evaluate",
            "consensus_evaluate": "evaluate",
            "full":               "full",
            "update_price_data":  "price_data",
        }
        mode = _TASK_TO_MODE.get(task_name)
        if mode:
            self._run(mode)
            return
        QMessageBox.information(
            self, "Run Task",
            f"Task '{task_name}' is managed by the server scheduler.\n"
            f"It runs automatically on its configured interval."
        )

    def _get_checkbox(self, row: int) -> Optional[QCheckBox]:
        w = self.tasks_table.cellWidget(row, 0)
        if w:
            for child in w.children():
                if isinstance(child, QCheckBox):
                    return child
        return None

    def _save(self):
        errors = []
        saved = 0
        for row_idx, t in enumerate(self._tasks):
            cb = self._get_checkbox(row_idx)
            if cb is None:
                continue
            new_active = 1 if cb.isChecked() else 0
            old_active = int(t.get("is_active", 1))
            if new_active != old_active:
                try:
                    self.api.set_task_active(t["name"], new_active)
                    saved += 1
                except Exception as e:
                    errors.append(f"{t['name']}: {e}")
        if errors:
            QMessageBox.warning(self, "Save Error", "\n".join(errors))
        elif saved:
            QMessageBox.information(self, "Saved", f"Updated {saved} task(s).")
        self.load()

    def _load_heartbeat(self):
        try:
            items = self.api.get_heartbeat_history(limit=15)
            self._populate_heartbeat(items)
        except Exception as e:
            err_msg = str(e)
            # Suppress connection errors - MainWindow already shows connection error dialog
            if "timeout" in err_msg.lower() or "connection" in err_msg.lower():
                logger.debug(f"Heartbeat history load skipped: server not connected")
            else:
                logger.warning(f"Heartbeat history load error: {e}")

    def _populate_heartbeat(self, items: list):
        self.hb_table.setRowCount(0)
        for row_idx, h in enumerate(items):
            self.hb_table.insertRow(row_idx)
            checked_at = str(h.get("checked_at", "") or "")
            bybit_ok = _HB_OK if h.get("bybit_ok") else _HB_ERR
            or_ok  = _HB_OK if h.get("openrouter_ok") else _HB_ERR
            sq_ok  = _HB_OK if h.get("sqlite_ok")     else _HB_ERR
            notes  = str(h.get("notes", "") or "")

            for col_idx, val in enumerate([checked_at, bybit_ok, or_ok, sq_ok, notes]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (1, 2, 3) and val == _HB_ERR:
                    item.setForeground(QBrush(QColor("#c62828")))
                self.hb_table.setItem(row_idx, col_idx, item)
