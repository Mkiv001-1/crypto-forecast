"""
Application context — centralized dependency container.

Provides singleton access to:
- Database manager (SQLiteManager)
- Server configuration
- Robot runner (optional)

Usage:
    from scripts.core.app_context import get_context, init_context

    init_context(db_file="database/trading_robot.db", server_config=cfg)
    ctx = get_context()
    db = ctx.db_manager
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.core.sqlite_manager import SQLiteManager
    from scripts.server.config import ServerConfig
    from scripts.server.robot import RobotRunner

logger = logging.getLogger(__name__)


class AppContext:
    """Container for application dependencies."""

    def __init__(
        self,
        db_file: Optional[str] = None,
        server_config: Optional["ServerConfig"] = None,
    ):
        from scripts.core.sqlite_manager import SQLiteManager

        self._db_manager: SQLiteManager = SQLiteManager(db_file)
        self._server_config = server_config
        self._runner: Optional["RobotRunner"] = None
        self._initialized = True
        logger.info("AppContext initialized with DB: %s", self._db_manager.db_file)

    @property
    def db_manager(self) -> "SQLiteManager":
        return self._db_manager

    @property
    def db_file(self) -> str:
        return self._db_manager.db_file

    @property
    def server_config(self) -> Optional["ServerConfig"]:
        return self._server_config

    @property
    def runner(self) -> Optional["RobotRunner"]:
        return self._runner

    def set_runner(self, runner: "RobotRunner") -> None:
        self._runner = runner


_context: Optional[AppContext] = None


def init_context(
    db_file: Optional[str] = None,
    server_config: Optional["ServerConfig"] = None,
    *,
    force: bool = False,
) -> AppContext:
    """Initialize the application context singleton."""
    global _context
    if _context is None or force:
        _context = AppContext(db_file, server_config=server_config)
    elif server_config is not None and _context._server_config is None:
        _context._server_config = server_config
    return _context


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError(
            "AppContext not initialized. Call init_context() first."
        )
    return _context


def reset_context() -> None:
    global _context
    _context = None
    logger.debug("AppContext reset")


def get_db_manager() -> "SQLiteManager":
    return get_context().db_manager
