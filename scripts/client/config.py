"""Client configuration loaded from client_config.ini."""

import configparser
import os
import logging

logger = logging.getLogger(__name__)

_DEFAULT_INI = os.path.join(os.path.dirname(__file__), "ini", "client_config.ini")


class ClientConfig:
    CONFIG_FILE = _DEFAULT_INI

    def __init__(self, config_file: str = None):
        self.config_file = config_file or self.CONFIG_FILE
        self._cfg = configparser.ConfigParser()
        self._load()

    def _load(self):
        if not os.path.exists(self.config_file):
            self._create_default()
        self._cfg.read(self.config_file, encoding="utf-8")

    def _create_default(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        self._cfg["server"] = {
            "url": "http://localhost:8000",
            "api_key": "CHANGE-ME-TO-A-STRONG-SECRET-KEY",
        }
        self._write()
        logger.info(f"Created default client config: {self.config_file}")

    def _write(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            self._cfg.write(f)

    @property
    def server_url(self) -> str:
        return self._cfg.get("server", "url", fallback="http://localhost:8000").rstrip("/")

    @property
    def api_key(self) -> str:
        return self._cfg.get("server", "api_key", fallback="").strip()
