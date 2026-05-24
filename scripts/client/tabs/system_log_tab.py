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

class SystemLogTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.load)
        self._auto_refresh_enabled = False

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        for lvl in ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"]:
            self.level_combo.addItem(lvl)
        bar.addWidget(self.level_combo)
        bar.addWidget(QLabel("Lines:"))
        self.lines_spin = QComboBox()
        for n in ["100", "200", "500", "1000"]:
            self.lines_spin.addItem(n)
        self.lines_spin.setCurrentIndex(1)
        bar.addWidget(self.lines_spin)
        self.reload_btn = QPushButton("🔄 Reload")
        self.reload_btn.clicked.connect(self.load)
        bar.addWidget(self.reload_btn)
        self.auto_cb = QCheckBox("Auto (5s)")
        self.auto_cb.toggled.connect(self._toggle_auto)
        bar.addWidget(self.auto_cb)
        bar.addStretch()
        layout.addLayout(bar)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_edit)

    def load(self):
        try:
            level = self.level_combo.currentText()
            lines = int(self.lines_spin.currentText())
            resp = self.api.get_system_log(lines=lines, level=level if level != "ALL" else None)
            if resp:
                self.log_edit.setPlainText("\n".join(resp.lines))
                sb = self.log_edit.verticalScrollBar()
                sb.setValue(sb.maximum())
        except Exception as e:
            logger.warning(f"System log load error: {e}")

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        """Pause periodic reload when the main tab is not visible."""
        self._auto_refresh_enabled = enabled
        if enabled and self.auto_cb.isChecked():
            if not self._timer.isActive():
                self._timer.start(5000)
        else:
            self._timer.stop()

    def _toggle_auto(self, checked: bool):
        if checked and self._auto_refresh_enabled:
            self._timer.start(5000)
        else:
            self._timer.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
