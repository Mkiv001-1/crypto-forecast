"""
Notification manager — stub implementation.

Currently logs all notifications. Real channels (Telegram, Email, Push)
will be integrated in a future step.

Usage:
    from notification_manager import notify
    notify("Order submitted for BTCUSDT", level="INFO")
"""

import logging

logger = logging.getLogger(__name__)

_LEVEL_MAP = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "CRITICAL": logging.CRITICAL,
}


def notify(message: str, level: str = "INFO", channel: str = "all") -> None:
    """
    Send a notification.

    Args:
        message: Human-readable message text.
        level:   Severity — DEBUG | INFO | WARNING | CRITICAL
        channel: Target channel (stub: ignored, all go to log)
    """
    log_level = _LEVEL_MAP.get(level.upper(), logging.INFO)
    logger.log(log_level, f"[NOTIFY] {message}")


async def notify_async(message: str, level: str = "INFO", channel: str = "all") -> None:
    """Async wrapper — delegates to sync notify (no I/O yet)."""
    notify(message, level=level, channel=channel)
