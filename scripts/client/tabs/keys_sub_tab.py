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

class _KeysSubTab(QWidget):
    """Sub-tab for configuration keys (moved from old ConfigTab)."""

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._items = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter key...")
        self.search_edit.textChanged.connect(self._filter)
        bar.addWidget(self.search_edit)
        self.reload_btn = QPushButton("🔄 Reload")
        self.reload_btn.clicked.connect(self.load)
        bar.addWidget(self.reload_btn)
        self.save_btn = QPushButton("💾 Save selected")
        self.save_btn.clicked.connect(self._save_selected)
        bar.addWidget(self.save_btn)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Key", "Value", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

    def load(self):
        try:
            resp = self.api.get_config()
            self._items = resp.items if resp else []
            self._render(self._items)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")

    def _render(self, items):
        self.table.setRowCount(len(items))
        for r, item in enumerate(items):
            self.table.setItem(r, 0, QTableWidgetItem(item.key or ""))
            val_item = QTableWidgetItem(item.value or "")
            self.table.setItem(r, 1, val_item)
            desc_item = QTableWidgetItem(item.description or "")
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 2, desc_item)

    def _filter(self, text):
        text = text.lower()
        filtered = [i for i in self._items if text in (i.key or "").lower()]
        self._render(filtered)

    def _save_selected(self):
        from scripts.shared.models import ConfigParam
        rows = set(i.row() for i in self.table.selectedItems())
        if not rows:
            QMessageBox.information(self, "Info", "Select a row to save.")
            return
        saved = 0
        for row in rows:
            key = self.table.item(row, 0).text()
            value = self.table.item(row, 1).text()
            try:
                self.api.update_config(key, ConfigParam(key=key, value=value))
                saved += 1
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save {key}:\n{e}")
        if saved:
            QMessageBox.information(self, "Saved", f"Saved {saved} parameter(s).")
