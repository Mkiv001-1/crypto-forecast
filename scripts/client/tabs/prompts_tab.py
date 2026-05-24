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
from scripts.client.constants import METHODS, _METHOD_LABELS
from datetime import date

class PromptsTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._templates: dict = {}
        self._method_configs: dict = {}  # method -> {execute: bool, ...}
        self._current_method: str = ""
        self._dirty = False
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(8)

        # ── Left: method list ─────────────────────────────────────────
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Methods</b>"))

        # Execute checkbox for selected method
        self.execute_cb = QCheckBox("Execute Orders")
        self.execute_cb.setToolTip("Allow this method to create trading orders")
        self.execute_cb.stateChanged.connect(self._on_execute_changed)
        left.addWidget(self.execute_cb)

        self.method_list = QListWidget()
        self.method_list.setMaximumWidth(210)
        self.method_list.setMinimumWidth(170)
        for m in METHODS:
            item = QListWidgetItem(_METHOD_LABELS.get(m, m))
            item.setData(Qt.ItemDataRole.UserRole, m)
            self.method_list.addItem(item)
        self.method_list.currentItemChanged.connect(self._on_method_changed)
        left.addWidget(self.method_list)
        left.addStretch()
        root.addLayout(left)

        # ── Right: editor ─────────────────────────────────────────────
        right = QVBoxLayout()

        top_bar = QHBoxLayout()
        self.method_lbl = QLabel("Select a method")
        self.method_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        top_bar.addWidget(self.method_lbl)
        top_bar.addStretch()
        vars_btn = QPushButton("{…} Variables")
        vars_btn.setToolTip("Show available template variables")
        vars_btn.clicked.connect(self._show_variables)
        top_bar.addWidget(vars_btn)
        right.addLayout(top_bar)

        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 9))
        self.editor.setPlaceholderText("Select a method on the left to edit its prompt template...")
        self.editor.textChanged.connect(self._on_text_changed)
        right.addWidget(self.editor, 1)

        btn_bar = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_current)
        btn_bar.addWidget(self.save_btn)
        self.reset_btn = QPushButton("↺ Reset to Default")
        self.reset_btn.setEnabled(False)
        self.reset_btn.clicked.connect(self._reset_current)
        btn_bar.addWidget(self.reset_btn)
        btn_bar.addStretch()
        reload_btn = QPushButton("🔄 Reload")
        reload_btn.clicked.connect(self.load)
        btn_bar.addWidget(reload_btn)
        right.addLayout(btn_bar)

        root.addLayout(right, 1)

    # ── Load ─────────────────────────────────────────────────────────

    def load(self):
        try:
            # Load prompt templates
            data = self.api.get_prompt_templates()
            self._templates = data.get("templates", {})

            # Load method configs with execute flags
            configs = self.api.get_method_configs()
            self._method_configs = {cfg["method"]: cfg for cfg in configs}

            if self._current_method:
                self._load_editor(self._current_method)
            elif self.method_list.count() > 0:
                self.method_list.setCurrentRow(0)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load templates:\n{e}")

    def _load_editor(self, method: str):
        self._current_method = method
        self.method_lbl.setText(_METHOD_LABELS.get(method, method))
        text = self._templates.get(method, "")
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.reset_btn.setEnabled(bool(method))
        self._update_execute_checkbox()

    def _update_execute_checkbox(self):
        """Update execute checkbox based on current method config."""
        if not self._current_method:
            self.execute_cb.setEnabled(False)
            self.execute_cb.setChecked(False)
            return

        cfg = self._method_configs.get(self._current_method, {})
        execute = cfg.get("execute", "yes")
        self.execute_cb.blockSignals(True)
        self.execute_cb.setEnabled(True)
        self.execute_cb.setChecked(execute == "yes")
        self.execute_cb.blockSignals(False)

    def _on_execute_changed(self, state):
        """Handle execute checkbox change and save to API."""
        if not self._current_method:
            return

        execute = "yes" if state == Qt.CheckState.Checked.value else "no"
        try:
            self.api.update_method_execute(self._current_method, execute)
            # Update local cache
            if self._current_method in self._method_configs:
                self._method_configs[self._current_method]["execute"] = execute
            else:
                self._method_configs[self._current_method] = {"execute": execute}
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update execute flag:\n{e}")
            # Revert checkbox
            self._update_execute_checkbox()

    def _on_method_changed(self, current, previous):
        if previous and self._dirty:
            method = previous.data(Qt.ItemDataRole.UserRole)
            ans = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to {_METHOD_LABELS.get(method, method)}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ans == QMessageBox.StandardButton.Yes:
                self._save_template(method, self.editor.toPlainText())
        if current:
            self._load_editor(current.data(Qt.ItemDataRole.UserRole))

    def _on_text_changed(self):
        if self._current_method:
            self._dirty = True
            self.save_btn.setEnabled(True)

    # ── Save / Reset ─────────────────────────────────────────────────

    def _save_template(self, method: str, text: str):
        try:
            self.api.save_prompt_template(method, text)
            self._templates[method] = text
            self._dirty = False
            self.save_btn.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _save_current(self):
        if self._current_method:
            self._save_template(self._current_method, self.editor.toPlainText())
            QMessageBox.information(self, "Saved",
                f"{_METHOD_LABELS.get(self._current_method, self._current_method)} saved.")

    def _reset_current(self):
        if not self._current_method:
            return
        ans = QMessageBox.question(
            self, "Reset to Default",
            f"Reset {_METHOD_LABELS.get(self._current_method)} to built-in default?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.reset_prompt_template(self._current_method)
            self.load()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset:\n{e}")

    def _show_variables(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Template Variables")
        dlg.resize(480, 440)
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFont(QFont("Consolas", 9))
        txt.setPlainText(_VARIABLES_HELP)
        lay.addWidget(txt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()


# ---------------------------------------------------------------------------
# System Log Tab
# ---------------------------------------------------------------------------
