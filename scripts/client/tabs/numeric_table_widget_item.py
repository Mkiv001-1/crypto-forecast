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

class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by numeric value rather than display text."""

    def __init__(self, display: str, value: float):
        super().__init__(display)
        self._value = value

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self._value < other._value
        try:
            return self._value < float(other.text().replace(",", ""))
        except (ValueError, AttributeError):
            return super().__lt__(other)


# ---------------------------------------------------------------------------
# Price Data Tab
# ---------------------------------------------------------------------------
