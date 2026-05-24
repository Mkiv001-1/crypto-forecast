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
from scripts.client.constants import _OPENROUTER_MODELS
from PyQt6.QtWidgets import QDateEdit
from datetime import date

class ProvidersTab(QWidget):
    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._providers: List[ProviderSetting] = []
        self._or_key_visible = False
        self._catalog_ids: List[str] = list(_OPENROUTER_MODELS)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── OpenRouter API Key block ──────────────────────────────────────────
        key_group = QGroupBox("OpenRouter API Key")
        kg_outer = QVBoxLayout()
        kg_outer.setContentsMargins(0, 0, 0, 0)
        kg_outer.setSpacing(4)
        
        kg = QHBoxLayout()
        self.or_key_edit = QLineEdit()
        self.or_key_edit.setPlaceholderText("sk-or-v1-...")
        self.or_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        kg.addWidget(self.or_key_edit, 1)
        self.reveal_key_btn = QPushButton("�")
        self.reveal_key_btn.setFixedWidth(36)
        self.reveal_key_btn.setCheckable(True)
        self.reveal_key_btn.toggled.connect(self._toggle_key_visibility)
        kg.addWidget(self.reveal_key_btn)
        save_key_btn = QPushButton("💾 Save Key")
        save_key_btn.clicked.connect(self._save_or_key)
        kg.addWidget(save_key_btn)
        kg_outer.addLayout(kg)
        
        self.free_only_cb = QCheckBox("Use only free models (:free suffix)")
        self.free_only_cb.setToolTip(
            "When checked, ':free' is appended to every model ID before calling OpenRouter.\n"
            "Free models have usage limits but require no credits."
        )
        kg_outer.addWidget(self.free_only_cb)
        key_group.setLayout(kg_outer)
        layout.addWidget(key_group)

        # ── AI Models table ───────────────────────────────────────────────────
        models_group = QGroupBox("AI Models (OpenRouter)")
        mg = QVBoxLayout(models_group)

        bar = QHBoxLayout()
        add_btn = QPushButton("➕ Add Model")
        add_btn.clicked.connect(self._add_row)
        bar.addWidget(add_btn)
        self.del_btn = QPushButton("🗑 Remove Selected")
        self.del_btn.clicked.connect(self._remove_selected)
        bar.addWidget(self.del_btn)
        bar.addStretch()
        self.catalog_btn = QPushButton("🌐 Update Catalog")
        self.catalog_btn.setToolTip("Fetch full model list from OpenRouter API")
        self.catalog_btn.clicked.connect(self._refresh_catalog)
        bar.addWidget(self.catalog_btn)
        self.save_btn = QPushButton("💾 Save All")
        self.save_btn.clicked.connect(self._save_models)
        bar.addWidget(self.save_btn)
        self.refresh_btn = QPushButton("🔄 Reload")
        self.refresh_btn.clicked.connect(self.load)
        bar.addWidget(self.refresh_btn)
        mg.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Active", "Execute", "Name", "Model", "Rate/min", "Max Tokens"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        mg.addWidget(self.table)
        layout.addWidget(models_group, 1)

        # ── Data providers (read-only info) ──────────────────────────────────
        data_group = QGroupBox("Data Providers")
        dg = QVBoxLayout(data_group)
        self.data_table = QTableWidget(0, 4)
        self.data_table.setHorizontalHeaderLabels(["Active", "Name", "API Key", "Rate/min"])
        self.data_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.data_table.setMaximumHeight(140)
        dg.addWidget(self.data_table)
        save_data_btn = QPushButton("💾 Save Data Providers")
        save_data_btn.clicked.connect(self._save_data_providers)
        dg.addWidget(save_data_btn)
        layout.addWidget(data_group)

    # ── Load ─────────────────────────────────────────────────────────────────

    def load(self):
        try:
            # Load OpenRouter key from config
            cfg = self.api.get_config()
            or_key = next((c.value for c in cfg.items if c.key == "OPENROUTER_API_KEY"), "")
            self.or_key_edit.setText(or_key)
            free_only = next((c.value for c in cfg.items if c.key == "OPENROUTER_FREE_ONLY"), "false")
            self.free_only_cb.setChecked(free_only.strip().lower() == "true")

            # Load model catalog for combos
            try:
                cat = self.api.get_model_catalog()
                ids = [item["model_id"] for item in cat.get("items", [])]
                if ids:
                    self._catalog_ids = ids
            except Exception:
                pass

            # Load providers — split by type field or presence of model string
            self._providers = self.api.get_providers()
            _DATA_NAMES = {"alpha_vantage", "yfinance", "finnhub", "polygon"}
            ai_providers = [
                p for p in self._providers
                if getattr(p, 'model', '') and
                   (p.get_name().lower() not in _DATA_NAMES)
            ]
            data_providers = [
                p for p in self._providers
                if p.get_name().lower() in _DATA_NAMES or not getattr(p, 'model', '')
            ]
            self._populate_ai_table(ai_providers)
            self._populate_data_table(data_providers)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load providers:\n{e}")

    def _populate_ai_table(self, providers):
        self.table.setRowCount(0)
        for p in providers:
            self._insert_ai_row(
                active=bool(int(p.active or 0)),
                execute=getattr(p, 'execute', 'yes') == 'yes',
                name=p.get_name(),
                model=p.model or "",
                rate=int(p.rate_limit or 60),
                tokens=int(p.max_tokens or 2000),
            )

    def _insert_ai_row(self, active=True, execute=True, name="", model="", rate=60, tokens=2000):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Active checkbox (col 0)
        cb_w = QWidget(); cb_l = QHBoxLayout(cb_w)
        cb_l.setAlignment(Qt.AlignmentFlag.AlignCenter); cb_l.setContentsMargins(0,0,0,0)
        cb = QCheckBox(); cb.setChecked(active); cb_l.addWidget(cb)
        self.table.setCellWidget(row, 0, cb_w)

        # Execute checkbox (col 1)
        exec_w = QWidget(); exec_l = QHBoxLayout(exec_w)
        exec_l.setAlignment(Qt.AlignmentFlag.AlignCenter); exec_l.setContentsMargins(0,0,0,0)
        exec_cb = QCheckBox(); exec_cb.setChecked(execute); exec_l.addWidget(exec_cb)
        self.table.setCellWidget(row, 1, exec_w)

        self.table.setItem(row, 2, QTableWidgetItem(name))

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._catalog_ids)
        if model and model not in self._catalog_ids:
            combo.insertItem(0, model)
        combo.setCurrentText(model or (self._catalog_ids[0] if self._catalog_ids else ""))
        self.table.setCellWidget(row, 3, combo)

        self.table.setItem(row, 4, QTableWidgetItem(str(rate)))
        self.table.setItem(row, 5, QTableWidgetItem(str(tokens)))

    def _populate_data_table(self, providers):
        self.data_table.setRowCount(0)
        for p in providers:
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)
            cb_w = QWidget(); cb_l = QHBoxLayout(cb_w)
            cb_l.setAlignment(Qt.AlignmentFlag.AlignCenter); cb_l.setContentsMargins(0,0,0,0)
            cb = QCheckBox(); cb.setChecked(bool(int(p.active or 0))); cb_l.addWidget(cb)
            self.data_table.setCellWidget(row, 0, cb_w)
            self.data_table.setItem(row, 1, QTableWidgetItem(p.get_name()))
            self.data_table.setItem(row, 2, QTableWidgetItem(p.get_api_key()))
            self.data_table.setItem(row, 3, QTableWidgetItem(str(p.rate_limit or "")))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_key_visibility(self, checked: bool):
        self.or_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _save_or_key(self):
        from scripts.shared.models import ConfigParam
        key = self.or_key_edit.text().strip()
        free_only = "true" if self.free_only_cb.isChecked() else "false"
        try:
            self.api.update_config("OPENROUTER_API_KEY", ConfigParam(key="OPENROUTER_API_KEY", value=key))
            self.api.update_config("OPENROUTER_FREE_ONLY", ConfigParam(key="OPENROUTER_FREE_ONLY", value=free_only))
            QMessageBox.information(self, "Saved", "OpenRouter settings saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    def _refresh_catalog(self):
        self.catalog_btn.setEnabled(False)
        self.catalog_btn.setText("⏳ Updating...")

        def task(log: Callable[[str, str], None]) -> dict:
            log("INFO", "Requesting model catalog refresh from OpenRouter.")
            result = self.api.refresh_model_catalog()
            count = int(result.get("refreshed", 0) or 0)
            log("INFO", f"Loaded models: {count}")
            return result

        def on_success(_result: dict):
            self.load()

        def on_error(error: str):
            logger.warning(f"Catalog refresh failed: {error}")

        def on_finished():
            self.catalog_btn.setEnabled(True)
            self.catalog_btn.setText("🌐 Update Catalog")

        try:
            _window_run_activity(
                self,
                operation_id="providers.refresh_catalog",
                title="Update Model Catalog",
                task=task,
                on_success=on_success,
                on_error=on_error,
                on_finished=on_finished,
            )
        except Exception as e:
            self.catalog_btn.setEnabled(True)
            self.catalog_btn.setText("🌐 Update Catalog")
            QMessageBox.critical(self, "Error", f"Failed to update catalog:\n{e}")

    def _add_row(self):
        self._insert_ai_row(active=True, name="",
                            model=self._catalog_ids[0] if self._catalog_ids else "")

    def _remove_selected(self):
        rows = sorted(set(i.row() for i in self.table.selectedItems()), reverse=True)
        if not rows:
            QMessageBox.information(self, "Info", "Select a row to remove.")
            return
        for row in rows:
            name_item = self.table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            if name:
                try:
                    self.api.delete_provider(name)
                except Exception:
                    pass
            self.table.removeRow(row)

    def _get_cb(self, table, row) -> Optional[QCheckBox]:
        w = table.cellWidget(row, 0)
        if w:
            for c in w.children():
                if isinstance(c, QCheckBox):
                    return c
        return None

    def _get_execute_cb(self, table, row) -> Optional[QCheckBox]:
        """Get execute checkbox from column 1."""
        w = table.cellWidget(row, 1)
        if w:
            for c in w.children():
                if isinstance(c, QCheckBox):
                    return c
        return None

    def _save_models(self):
        errors = []
        for row in range(self.table.rowCount()):
            try:
                cb = self._get_cb(self.table, row)
                active = 1 if (cb and cb.isChecked()) else 0
                exec_cb = self._get_execute_cb(self.table, row)
                execute = "yes" if (exec_cb and exec_cb.isChecked()) else "no"
                name_item = self.table.item(row, 2)
                name = (name_item.text().strip() if name_item else "").replace(" ", "_")
                if not name:
                    continue
                combo = self.table.cellWidget(row, 3)
                model = combo.currentText().strip() if combo else ""
                rate_item = self.table.item(row, 4)
                tokens_item = self.table.item(row, 5)
                try:
                    rate = int(rate_item.text()) if rate_item and rate_item.text() else 60
                except ValueError:
                    rate = 60
                try:
                    tokens = int(tokens_item.text()) if tokens_item and tokens_item.text() else 2000
                except ValueError:
                    tokens = 2000
                self.api.update_provider(name, model=model, rate_limit=rate,
                                         max_tokens=tokens, active=active)
                # Save execute flag separately via dedicated endpoint
                self.api.update_provider_execute(name, execute)
            except Exception as e:
                errors.append(f"Row {row}: {e}")
        if errors:
            QMessageBox.warning(self, "Partial Save", "\n".join(errors))
        else:
            QMessageBox.information(self, "Saved", "AI models saved.")
        self.load()

    def _save_data_providers(self):
        errors = []
        for row in range(self.data_table.rowCount()):
            try:
                name_item = self.data_table.item(row, 1)
                name = name_item.text().strip() if name_item else ""
                if not name:
                    continue
                cb = self._get_cb(self.data_table, row)
                active = 1 if (cb and cb.isChecked()) else 0
                key_item = self.data_table.item(row, 2)
                api_key = key_item.text().strip() if key_item else ""
                rate_item = self.data_table.item(row, 3)
                try:
                    rate = int(rate_item.text()) if rate_item and rate_item.text() else 60
                except ValueError:
                    rate = 60
                self.api.update_provider(name, api_key=api_key or None,
                                         rate_limit=rate, active=active)
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            QMessageBox.warning(self, "Partial Save", "\n".join(errors))
        else:
            QMessageBox.information(self, "Saved", "Data providers saved.")
        self.load()


# ---------------------------------------------------------------------------
# Settings Tab with sub-tabs
# ---------------------------------------------------------------------------
