from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from scripts.client.activity_runtime import ActivityRun


class ActivityDialog(QDialog):
    def __init__(self, run: ActivityRun, parent=None):
        super().__init__(parent)
        self._run = run
        self.setWindowTitle(run.title)
        self.resize(860, 520)
        self.setModal(False)
        self._build_ui()
        self._wire_signals()
        self._load_existing_log()
        self._update_status_badge(run.status)
        self._update_close_button()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.title_label = QLabel(self._run.title)
        self.title_label.setStyleSheet("font-weight: 600;")
        header.addWidget(self.title_label)

        self.status_label = QLabel("")
        self.status_label.setMinimumWidth(120)
        self.status_label.setStyleSheet("padding: 4px 8px; border-radius: 8px;")
        header.addWidget(self.status_label)
        header.addStretch()

        layout.addLayout(header)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_edit, 1)

        footer = QHBoxLayout()
        self.hint_label = QLabel("Close hides this window. Task keeps running in background.")
        self.hint_label.setStyleSheet("color: #616161;")
        footer.addWidget(self.hint_label)
        footer.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        footer.addWidget(self.close_btn)

        layout.addLayout(footer)

    def _wire_signals(self):
        self._run.log_appended.connect(self._append_line)
        self._run.status_changed.connect(self._on_status_changed)
        self._run.finished.connect(self._on_finished)

    def _load_existing_log(self):
        lines = self._run.log_lines
        if lines:
            self.log_edit.setPlainText("\n".join(lines))
            sb = self.log_edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _append_line(self, line: str):
        if self.log_edit.toPlainText():
            self.log_edit.append(line)
        else:
            self.log_edit.setPlainText(line)
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_status_changed(self, status: str):
        self._update_status_badge(status)
        self._update_close_button()

    def _on_finished(self):
        self._update_close_button()

    def _update_status_badge(self, status: str):
        status_norm = (status or "").lower()
        if status_norm == "running":
            text = "RUNNING"
            style = "background: #fff3cd; color: #7a5d00;"
        elif status_norm == "success":
            text = "SUCCESS"
            style = "background: #d4edda; color: #1f6f43;"
        elif status_norm == "error":
            text = "ERROR"
            style = "background: #f8d7da; color: #842029;"
        else:
            text = (status or "UNKNOWN").upper()
            style = "background: #eceff1; color: #37474f;"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"padding: 4px 8px; border-radius: 8px; {style}")

    def _update_close_button(self):
        if self._run.status == "running":
            self.close_btn.setText("Close (Background)")
            self.hint_label.setVisible(True)
        else:
            self.close_btn.setText("Close")
            self.hint_label.setVisible(False)
