"""Single-instance guard using a PID lock file.

Usage:
    guard = SingleInstance("server")   # or "client"
    guard.acquire()   # raises SystemExit if another instance is running
    ...
    # guard released automatically via __del__ / atexit
"""

import atexit
import logging
import os
import sys

logger = logging.getLogger(__name__)

_LOCK_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SingleInstance:
    def __init__(self, name: str):
        self._lock_path = os.path.join(_LOCK_DIR, f".{name}.pid")
        self._name = name
        atexit.register(self.release)

    def acquire(self):
        existing_pid = self._read_pid()
        if existing_pid and self._pid_alive(existing_pid):
            msg = (
                f"\n{'='*55}\n"
                f"  {self._name.upper()} already running (PID {existing_pid}).\n"
                f"  Close the existing instance before starting a new one.\n"
                f"{'='*55}\n"
            )
            print(msg, file=sys.stderr)
            logger.error(f"{self._name} already running (PID {existing_pid})")
            sys.exit(1)
        # Write our PID
        try:
            with open(self._lock_path, "w") as f:
                f.write(str(os.getpid()))
        except OSError as e:
            logger.warning(f"Could not write PID file {self._lock_path}: {e}")

    def release(self):
        try:
            if os.path.exists(self._lock_path):
                stored = self._read_pid()
                if stored == os.getpid():
                    os.remove(self._lock_path)
        except OSError:
            pass

    def _read_pid(self):
        try:
            with open(self._lock_path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Return True if process with given PID is running."""
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        except Exception:
            # Fallback: os.kill with signal 0
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False
