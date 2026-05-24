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

class NewMethodDialog(QDialog):
    """Dialog to create a new forecast method."""

    def __init__(self, existing_methods: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Method")
        self.setMinimumWidth(360)
        self._existing = [m.lower() for m in existing_methods]

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. my_custom_method")
        form.addRow("Method name:", self.name_edit)

        self.timeframe_spin = QSpinBox()
        self.timeframe_spin.setRange(1, 8760)
        self.timeframe_spin.setValue(24)
        self.timeframe_spin.setSuffix(" h")
        form.addRow("Timeframe:", self.timeframe_spin)

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems(["both", "time", "price_level"])
        form.addRow("Trigger:", self.trigger_combo)

        self.execute_cb = QCheckBox("Execute Orders")
        self.execute_cb.setChecked(True)
        form.addRow("", self.execute_cb)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Method name cannot be empty.")
            return
        import re
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            QMessageBox.warning(self, "Validation",
                                "Use snake_case (lowercase letters, digits, underscores).")
            return
        if name.lower() in self._existing:
            QMessageBox.warning(self, "Validation", f"Method '{name}' already exists.")
            return
        self.accept()

    def result_data(self) -> dict:
        return {
            "method": self.name_edit.text().strip(),
            "timeframe_hours": self.timeframe_spin.value(),
            "trigger": self.trigger_combo.currentText(),
            "execute": "yes" if self.execute_cb.isChecked() else "no",
        }
