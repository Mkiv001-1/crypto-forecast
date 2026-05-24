"""Server configuration loaded from server_config.ini."""

import configparser
import os
import uuid
import logging

logger = logging.getLogger(__name__)

_DEFAULT_INI = os.path.join(os.path.dirname(__file__), "ini", "server_config.ini")


def _mask_secret(value: str) -> str:
    """Mask API key for logging (show only first/last 4 chars)."""
    text = str(value or "").strip()
    if not text:
        return "<empty>"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def get_db_path() -> str:
    """Return the absolute path to the database file from server config."""
    return ServerConfig().db_file


class ServerConfig:
    CONFIG_FILE = _DEFAULT_INI

    def __init__(self, config_file: str = None):
        self.config_file = config_file or self.CONFIG_FILE
        self._cfg = configparser.ConfigParser()
        self._load()

    def _load(self):
        if not os.path.exists(self.config_file):
            self._create_default()
        self._cfg.read(self.config_file, encoding="utf-8")
        self._ensure_api_key()

    def _create_default(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        self._cfg["server"] = {
            "host": "0.0.0.0",
            "port": "8000",
        }
        self._cfg["data"] = {
            "db_file": "database/trading_robot.db",
            "excel_file": "trading_robot.xlsx",
        }
        self._cfg["security"] = {
            "api_key": "",
        }
        self._write()
        logger.info(f"Created default config: {self.config_file}")

    def _ensure_api_key(self):
        """Auto-generate api_key if empty."""
        if not self._cfg.has_section("security"):
            self._cfg["security"] = {}
        current = self._cfg.get("security", "api_key", fallback="").strip()
        if not current:
            new_key = str(uuid.uuid4())
            self._cfg["security"]["api_key"] = new_key
            self._write()
            logger.info(f"Generated new API key and saved to {self.config_file}")
            logger.info(f"API Key: {_mask_secret(new_key)}")

    def _write(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            self._cfg.write(f)

    @property
    def host(self) -> str:
        return self._cfg.get("server", "host", fallback="0.0.0.0")

    @property
    def port(self) -> int:
        return int(self._cfg.get("server", "port", fallback="8000"))

    @property
    def db_file(self) -> str:
        raw = self._cfg.get("data", "db_file", fallback="database/trading_robot.db")
        if not os.path.isabs(raw):
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(root, raw)
        return raw

    @property
    def excel_file(self) -> str:
        """Legacy property — returns db_file path for backward compat."""
        return self.db_file

    @property
    def api_key(self) -> str:
        return self._cfg.get("security", "api_key", fallback="").strip()
