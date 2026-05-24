from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


ActivityTask = Callable[[Callable[[str, str], None]], Any]
ActivitySuccessCallback = Callable[[Any], None]
ActivityErrorCallback = Callable[[str], None]
ActivityFinishedCallback = Callable[[], None]


@dataclass
class ActivityEvent:
    timestamp: datetime
    level: str
    message: str


@dataclass
class ActivityState:
    operation_id: str
    title: str
    status: str = "running"
    events: list[ActivityEvent] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None


class ActivityRun(QObject):
    log_appended = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, operation_id: str, title: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.state = ActivityState(operation_id=operation_id, title=title)
        self._lines: list[str] = []

    @property
    def operation_id(self) -> str:
        return self.state.operation_id

    @property
    def title(self) -> str:
        return self.state.title

    @property
    def status(self) -> str:
        return self.state.status

    @property
    def log_lines(self) -> list[str]:
        return list(self._lines)

    def append_event(self, level: str, message: str):
        evt = ActivityEvent(timestamp=datetime.now(), level=(level or "INFO").upper(), message=str(message))
        self.state.events.append(evt)
        line = f"[{evt.timestamp.strftime('%H:%M:%S')}] [{evt.level}] {evt.message}"
        self._lines.append(line)
        self.log_appended.emit(line)

    def set_status(self, status: str):
        self.state.status = status
        self.status_changed.emit(status)


class _ActivityWorker(QObject):
    log_event = pyqtSignal(str, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, task: ActivityTask):
        super().__init__()
        self._task = task

    @pyqtSlot()
    def run(self):
        try:
            result = self._task(self._log)
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def _log(self, level: str, message: str):
        self.log_event.emit((level or "INFO").upper(), str(message))


class ActivityManager(QObject):
    activity_status = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._runs: dict[str, ActivityRun] = {}
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, _ActivityWorker] = {}
        self._success_callbacks: dict[str, Optional[ActivitySuccessCallback]] = {}
        self._error_callbacks: dict[str, Optional[ActivityErrorCallback]] = {}
        self._finished_callbacks: dict[str, Optional[ActivityFinishedCallback]] = {}

    def start(
        self,
        operation_id: str,
        title: str,
        task: ActivityTask,
        on_success: Optional[ActivitySuccessCallback] = None,
        on_error: Optional[ActivityErrorCallback] = None,
        on_finished: Optional[ActivityFinishedCallback] = None,
    ) -> ActivityRun:
        existing = self._runs.get(operation_id)
        if existing is not None and existing.status == "running":
            existing.append_event("WARN", "Operation is already running. Focusing current task window.")
            return existing

        run = ActivityRun(operation_id=operation_id, title=title, parent=self)
        run.set_status("running")
        run.append_event("INFO", f"Started: {title}")

        thread = QThread(self)
        worker = _ActivityWorker(task)
        worker.moveToThread(thread)

        self._runs[operation_id] = run
        self._threads[operation_id] = thread
        self._workers[operation_id] = worker
        self._success_callbacks[operation_id] = on_success
        self._error_callbacks[operation_id] = on_error
        self._finished_callbacks[operation_id] = on_finished

        thread.started.connect(worker.run)
        worker.log_event.connect(lambda level, msg, op=operation_id: self._on_log(op, level, msg))
        worker.succeeded.connect(lambda result, op=operation_id: self._on_success(op, result))
        worker.failed.connect(lambda error, op=operation_id: self._on_error(op, error))
        worker.finished.connect(lambda op=operation_id: self._on_finished(op))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        return run

    def get_run(self, operation_id: str) -> Optional[ActivityRun]:
        return self._runs.get(operation_id)

    def _on_log(self, operation_id: str, level: str, message: str):
        run = self._runs.get(operation_id)
        if run is None:
            return
        run.append_event(level, message)
        self.activity_status.emit(f"{run.title}: {message}")

    def _on_success(self, operation_id: str, result: Any):
        run = self._runs.get(operation_id)
        if run is None:
            return
        run.state.result = result
        run.set_status("success")
        run.append_event("INFO", "Completed successfully.")

        callback = self._success_callbacks.get(operation_id)
        if callback is not None:
            callback(result)

    def _on_error(self, operation_id: str, error: str):
        run = self._runs.get(operation_id)
        if run is None:
            return
        run.state.error = error
        run.set_status("error")
        run.append_event("ERROR", error)

        callback = self._error_callbacks.get(operation_id)
        if callback is not None:
            callback(error)

    def _on_finished(self, operation_id: str):
        run = self._runs.get(operation_id)
        if run is None:
            return

        callback = self._finished_callbacks.get(operation_id)
        if callback is not None:
            callback()

        run.finished.emit()

        self._workers.pop(operation_id, None)
        self._threads.pop(operation_id, None)
        self._success_callbacks.pop(operation_id, None)
        self._error_callbacks.pop(operation_id, None)
        self._finished_callbacks.pop(operation_id, None)


def window_run_activity(
    widget,
    operation_id: str,
    title: str,
    task: ActivityTask,
    on_success: Optional[ActivitySuccessCallback] = None,
    on_error: Optional[ActivityErrorCallback] = None,
    on_finished: Optional[ActivityFinishedCallback] = None,
):
    """Run a background activity on the main window's ActivityManager."""
    main_win = widget.window()
    if main_win is None or not hasattr(main_win, "run_activity"):
        raise RuntimeError("Main window activity manager is unavailable")
    return main_win.run_activity(
        operation_id=operation_id,
        title=title,
        task=task,
        on_success=on_success,
        on_error=on_error,
        on_finished=on_finished,
    )
