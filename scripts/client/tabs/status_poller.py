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

class StatusPoller(QThread):
    """Background thread that polls /run/status every 2 seconds."""
    status_updated = pyqtSignal(object)

    def __init__(self, api: ForecastApiClient):
        super().__init__()
        self.api = api
        self._active = True

    def run(self):
        import time
        while self._active:
            try:
                resp = self.api.run_status()
                self.status_updated.emit(resp)
                if resp.status in ("idle", "done", "error"):
                    self._active = False
                    break
            except Exception as e:
                logger.warning(f"Status poll error: {e}")
            time.sleep(2)

    def stop(self):
        self._active = False
