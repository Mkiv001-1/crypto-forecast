"""
Circuit breaker for OpenRouter API calls.

States:
  CLOSED  — normal operation; all calls go through
  OPEN    — failure threshold exceeded; calls rejected immediately
  HALF    — grace period elapsed; one test call allowed

Thresholds:
  CONSECUTIVE_FAILURES  = 3   (calls to open the circuit)
  HEARTBEAT_OPENROUTER_GRACE_SEC — seconds before OPEN → HALF transition
  RECOVERY_SUCCESSES    = 2   (consecutive successes in HALF to reclose)
"""

import logging
import threading
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_lock              = threading.Lock()
_state             = "CLOSED"   # CLOSED | OPEN | HALF
_failure_count     = 0
_success_count     = 0
_last_failure_time = 0.0
_grace_seconds     = 120
_failure_threshold = 3
_recovery_threshold = 2


def configure(
    grace_seconds: int = 120,
    failure_threshold: int = 3,
    recovery_threshold: int = 2,
) -> None:
    """Configure circuit breaker parameters (call once at startup)."""
    global _grace_seconds, _failure_threshold, _recovery_threshold
    with _lock:
        _grace_seconds       = grace_seconds
        _failure_threshold   = failure_threshold
        _recovery_threshold  = recovery_threshold
    logger.info(
        f"circuit_breaker: configured grace={grace_seconds}s "
        f"failures={failure_threshold} recovery={recovery_threshold}"
    )


def get_state() -> str:
    """Return current circuit state: CLOSED | OPEN | HALF."""
    with _lock:
        return _check_transition()


def _check_transition() -> str:
    """Internal: check if OPEN → HALF grace period elapsed. Must hold _lock."""
    global _state
    if _state == "OPEN":
        elapsed = time.time() - _last_failure_time
        if elapsed >= _grace_seconds:
            _state = "HALF"
            logger.info(f"circuit_breaker: OPEN → HALF (grace {elapsed:.0f}s elapsed)")
    return _state


def record_success() -> None:
    """Record a successful OpenRouter call."""
    global _state, _failure_count, _success_count
    with _lock:
        _failure_count = 0
        if _state == "HALF":
            _success_count += 1
            if _success_count >= _recovery_threshold:
                _state = "CLOSED"
                _success_count = 0
                logger.info("circuit_breaker: HALF → CLOSED (recovered)")
        elif _state == "CLOSED":
            _success_count = 0


def record_failure() -> None:
    """Record a failed OpenRouter call."""
    global _state, _failure_count, _success_count, _last_failure_time
    with _lock:
        _failure_count += 1
        _success_count = 0
        _last_failure_time = time.time()
        if _state in ("CLOSED", "HALF") and _failure_count >= _failure_threshold:
            _state = "OPEN"
            logger.error(
                f"circuit_breaker: → OPEN after {_failure_count} consecutive failures"
            )


def is_open() -> bool:
    """Return True if circuit is OPEN (calls should be rejected)."""
    with _lock:
        return _check_transition() == "OPEN"


def call_with_breaker(func: Callable, *args, **kwargs) -> Any:
    """
    Execute func(*args, **kwargs) through the circuit breaker.

    Raises RuntimeError if circuit is OPEN.
    Propagates original exception on failure (after recording it).
    """
    with _lock:
        state = _check_transition()

    if state == "OPEN":
        raise RuntimeError(
            f"circuit_breaker: OpenRouter circuit is OPEN — call rejected"
        )

    try:
        result = func(*args, **kwargs)
        record_success()
        return result
    except Exception as e:
        record_failure()
        raise


def reset() -> None:
    """Force-reset circuit to CLOSED (for testing / manual recovery)."""
    global _state, _failure_count, _success_count, _last_failure_time
    with _lock:
        _state = "CLOSED"
        _failure_count = 0
        _success_count = 0
        _last_failure_time = 0.0
    logger.info("circuit_breaker: manually reset to CLOSED")


def status() -> dict:
    """Return a status dict for API/health endpoints."""
    with _lock:
        state = _check_transition()
        return {
            "state":          state,
            "failure_count":  _failure_count,
            "success_count":  _success_count,
            "grace_seconds":  _grace_seconds,
            "last_failure_age_sec": round(time.time() - _last_failure_time, 1) if _last_failure_time else None,
        }
