"""Entry point for Forecast Trading Robot Server."""

import os
import sys
import logging
import argparse
from logging.handlers import RotatingFileHandler

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_SERVER_DIR)
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)

_log_file = os.path.join(_PROJECT_ROOT, "trading_robot.log")
_log_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if not any(isinstance(h, RotatingFileHandler) for h in _root_logger.handlers):
    _fh = RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _fh.setFormatter(_log_fmt)
    _root_logger.addHandler(_fh)
if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in _root_logger.handlers):
    _sh = logging.StreamHandler()
    _sh.setFormatter(_log_fmt)
    _root_logger.addHandler(_sh)

logger = logging.getLogger(__name__)

from scripts.bootstrap import bootstrap_paths

bootstrap_paths(_PROJECT_ROOT)


from scripts.shared.security import mask_secret as _mask_secret


def main():
    from scripts.core.single_instance import SingleInstance
    SingleInstance("server").acquire()

    parser = argparse.ArgumentParser(description="Forecast Trading Robot Server")
    parser.add_argument("--host", help="Host to bind (overrides config)")
    parser.add_argument("--port", type=int, help="Port to bind (overrides config)")
    parser.add_argument("--config", help="Path to server_config.ini")
    args = parser.parse_args()

    from scripts.server.config import ServerConfig
    cfg = ServerConfig(args.config) if args.config else ServerConfig()

    host = args.host or cfg.host
    port = args.port or cfg.port

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn[standard]")
        return 1

    logger.info(f"Starting server on http://{host}:{port}")
    logger.info(f"Excel: {cfg.excel_file}")
    logger.info(f"API Key: {_mask_secret(cfg.api_key)}")

    uvicorn.run(
        "scripts.server.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
