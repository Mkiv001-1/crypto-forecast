"""
Bybit Configuration — настройки для Bybit API.

Поддерживает:
- Demo Trading на bybit.com (по умолчанию, api-demo.bybit.com) — не testnet
- Live торговлю на bybit.com (api.bybit.com)
- Несколько профилей (demo/live/sub1, …) через secrets.ini
- Управление leverage и рисками

Конфигурация загружается из (приоритет от низшего к высшему):
1. Default значения
2. SQLite config таблицы
3. secrets.ini[активный профиль]
4. Environment variables

API ключи хранятся в scripts/server/ini/secrets.ini (исключён из git).
Активный профиль задаётся через BYBIT_ACTIVE_PROFILE (SQLite или env var).
"""

import configparser
import os
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Path to secrets.ini (excluded from git)
_SECRETS_INI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "ini", "secrets.ini"
)


# Default конфигурация
DEFAULT_BYBIT_CONFIG = {
    # API Settings — keys are intentionally empty; use secrets.ini instead
    "BYBIT_API_KEY": "",
    "BYBIT_API_SECRET": "",
    "BYBIT_DEMO": "true",  # true = bybit.com Demo Trading (not testnet), false = live
    "BYBIT_ACTIVE_PROFILE": "demo",  # active profile name from secrets.ini
    "BYBIT_RECV_WINDOW": "60000",  # ms; must cover clock skew vs Bybit (max 60000)
    
    # Trading Settings
    "BYBIT_DEFAULT_CATEGORY": "linear",  # linear, spot, inverse
    "BYBIT_DEFAULT_LEVERAGE": "3",  # 1-100 для linear
    "BYBIT_MAX_LEVERAGE": "10",  # Максимальное разрешенное плечо
    
    # Risk Management (адаптировано для крипто)
    "MAX_RISK_PER_TRADE_PCT": "1.0",  # % от капитала на сделку
    "MAX_POSITION_PCT": "10.0",  # Макс % капитала в одной позиции
    "MAX_OPEN_POSITIONS": "5",  # Максимум одновременных позиций
    
    # Order Settings
    "DEFAULT_ORDER_TYPE": "Limit",  # Limit или Market
    "DEFAULT_TIME_IN_FORCE": "GTC",  # GTC, IOC, FOK
    "ENTRY_SLIPPAGE_TOLERANCE": "0.5",  # % допустимого проскальзывания
    
    # Data Settings
    "DATA_SOURCE": "bybit",  # bybit (не yfinance)
    "DEFAULT_INTERVAL": "60",  # Таймфрейм для анализа (1h)
    "MIN_DATA_DAYS": "30",  # Минимум дней истории для прогноза
    
    # Trading Mode
    "ORDER_MODE": "disabled",  # disabled, paper (demo), live
    "LIVE_TRADING_CONFIRMED": "false",  # Подтверждение live торговли
}


@dataclass
class BybitConfig:
    """Типизированная конфигурация Bybit."""
    
    # API
    api_key: str = ""
    api_secret: str = ""
    demo: bool = True
    recv_window: int = 60000

    # Trading
    category: str = "linear"
    default_leverage: int = 3
    max_leverage: int = 10
    
    # Risk
    max_risk_per_trade_pct: float = 1.0
    max_position_pct: float = 10.0
    max_open_positions: int = 5
    
    # Orders
    default_order_type: str = "Limit"
    default_time_in_force: str = "GTC"
    entry_slippage_tolerance: float = 0.5
    
    # Data
    data_source: str = "bybit"
    default_interval: str = "60"
    min_data_days: int = 30
    
    # Mode
    order_mode: str = "disabled"
    live_trading_confirmed: bool = False
    active_profile: str = "demo"

    @property
    def is_live(self) -> bool:
        """Проверка live режима."""
        return not self.demo and self.order_mode == "live" and self.live_trading_confirmed
    
    @property
    def is_paper(self) -> bool:
        """Проверка paper/demo режима."""
        return self.demo or self.order_mode == "paper"
    
    @property
    def is_trading_enabled(self) -> bool:
        """Проверка что торговля разрешена."""
        return self.order_mode in ["paper", "live"]


# -----------------------------------------------------------------------------
# secrets.ini helpers
# -----------------------------------------------------------------------------

def _get_secrets_ini_path() -> str:
    """Return absolute path to secrets.ini."""
    return _SECRETS_INI_PATH


def _load_secrets_ini(profile: str) -> Dict[str, str]:
    """
    Load api_key / api_secret for the given profile from secrets.ini.

    Returns dict with 'api_key' and 'api_secret' (empty strings if not found).
    """
    path = _get_secrets_ini_path()
    result = {"api_key": "", "api_secret": ""}
    if not os.path.exists(path):
        return result
    try:
        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        section = f"bybit_{profile}"
        if cfg.has_section(section):
            result["api_key"] = cfg.get(section, "api_key", fallback="").strip()
            result["api_secret"] = cfg.get(section, "api_secret", fallback="").strip()
    except Exception as e:
        logger.warning(f"Failed to read secrets.ini profile '{profile}': {e}")
    return result


def list_secrets_profiles() -> List[str]:
    """
    Return list of profile names defined in secrets.ini (e.g. ['demo', 'live']).
    Each section [bybit_<name>] yields name '<name>'.
    """
    path = _get_secrets_ini_path()
    if not os.path.exists(path):
        return []
    try:
        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        profiles = []
        for section in cfg.sections():
            if section.startswith("bybit_"):
                profiles.append(section[len("bybit_"):])
        return profiles
    except Exception as e:
        logger.warning(f"Failed to list secrets.ini profiles: {e}")
        return []


def save_secrets_profile(profile: str, api_key: str, api_secret: str) -> bool:
    """
    Write or update a profile in secrets.ini.
    Creates the file if it does not exist.
    """
    path = _get_secrets_ini_path()
    try:
        cfg = configparser.ConfigParser()
        if os.path.exists(path):
            cfg.read(path, encoding="utf-8")
        section = f"bybit_{profile}"
        if not cfg.has_section(section):
            cfg.add_section(section)
        cfg.set(section, "api_key", api_key)
        cfg.set(section, "api_secret", api_secret)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            cfg.write(f)
        logger.info(f"Saved credentials for profile '{profile}' to secrets.ini")
        return True
    except Exception as e:
        logger.error(f"Failed to save secrets.ini profile '{profile}': {e}")
        return False


def get_masked_api_key(profile: str) -> str:
    """
    Return a masked version of the api_key for display (e.g. 'ywht...ML7').
    Returns empty string if not configured.
    """
    creds = _load_secrets_ini(profile)
    key = creds.get("api_key", "")
    if not key:
        return ""
    if len(key) <= 7:
        return "***"
    return f"{key[:4]}...{key[-3:]}"


# -----------------------------------------------------------------------------
# Main config loader
# -----------------------------------------------------------------------------

def load_bybit_config(db_manager=None) -> BybitConfig:
    """
    Загрузить конфигурацию Bybit.

    Приоритет (от низшего к высшему):
    1. Default значения
    2. SQLite config table
    3. secrets.ini[активный профиль]  ← API ключи
    4. Environment variables

    Args:
        db_manager: SQLiteManager для загрузки из БД

    Returns:
        BybitConfig объект
    """
    config_values = DEFAULT_BYBIT_CONFIG.copy()

    # 1. Загружаем не-секретные настройки из SQLite
    if db_manager:
        try:
            for key in config_values.keys():
                db_value = db_manager.get_config_value(key)
                if db_value:
                    config_values[key] = db_value
        except Exception as e:
            logger.warning(f"Failed to load config from DB: {e}")

    # 2. Определяем активный профиль (SQLite уже мог перезаписать дефолт)
    active_profile = config_values.get("BYBIT_ACTIVE_PROFILE", "demo") or "demo"
    # env var overrides profile selection too
    active_profile = os.getenv("BYBIT_ACTIVE_PROFILE", active_profile)

    # 3. Загружаем API ключи из secrets.ini для активного профиля
    secrets = _load_secrets_ini(active_profile)
    if secrets["api_key"]:
        config_values["BYBIT_API_KEY"] = secrets["api_key"]
    if secrets["api_secret"]:
        config_values["BYBIT_API_SECRET"] = secrets["api_secret"]

    # 4. Environment variables имеют наивысший приоритет (перезаписывают всё)
    for key in list(config_values.keys()):
        env_value = os.getenv(key)
        if env_value is not None:
            config_values[key] = env_value

    # Helper: get value with fallback for empty strings
    def _get(key: str, default: str) -> str:
        val = config_values.get(key)
        return val if val else default

    return BybitConfig(
        api_key=_get("BYBIT_API_KEY", ""),
        api_secret=_get("BYBIT_API_SECRET", ""),
        demo=_get("BYBIT_DEMO", "true").lower() == "true",
        recv_window=max(5000, min(60000, int(_get("BYBIT_RECV_WINDOW", "60000")))),
        category=_get("BYBIT_DEFAULT_CATEGORY", "linear"),
        default_leverage=int(_get("BYBIT_DEFAULT_LEVERAGE", "3")),
        max_leverage=int(_get("BYBIT_MAX_LEVERAGE", "10")),
        max_risk_per_trade_pct=float(_get("MAX_RISK_PER_TRADE_PCT", "1.0")),
        max_position_pct=float(_get("MAX_POSITION_PCT", "10.0")),
        max_open_positions=int(_get("MAX_OPEN_POSITIONS", "5")),
        default_order_type=_get("DEFAULT_ORDER_TYPE", "Limit"),
        default_time_in_force=_get("DEFAULT_TIME_IN_FORCE", "GTC"),
        entry_slippage_tolerance=float(_get("ENTRY_SLIPPAGE_TOLERANCE", "0.5")),
        data_source=_get("DATA_SOURCE", "bybit"),
        default_interval=_get("DEFAULT_INTERVAL", "60"),
        min_data_days=int(_get("MIN_DATA_DAYS", "30")),
        order_mode=_get("ORDER_MODE", "disabled"),
        live_trading_confirmed=_get("LIVE_TRADING_CONFIRMED", "false").lower() == "true",
        active_profile=active_profile,
    )


def save_bybit_config(db_manager, config: BybitConfig) -> bool:
    """
    Сохранить не-секретную конфигурацию Bybit в SQLite.
    API ключи НЕ сохраняются в SQLite — используйте save_secrets_profile().

    Args:
        db_manager: SQLiteManager
        config: BybitConfig объект

    Returns:
        True если успешно
    """
    try:
        config_dict = {
            "BYBIT_DEMO": str(config.demo).lower(),
            "BYBIT_ACTIVE_PROFILE": config.active_profile,
            "BYBIT_DEFAULT_CATEGORY": config.category,
            "BYBIT_DEFAULT_LEVERAGE": str(config.default_leverage),
            "BYBIT_MAX_LEVERAGE": str(config.max_leverage),
            "MAX_RISK_PER_TRADE_PCT": str(config.max_risk_per_trade_pct),
            "MAX_POSITION_PCT": str(config.max_position_pct),
            "MAX_OPEN_POSITIONS": str(config.max_open_positions),
            "DEFAULT_ORDER_TYPE": config.default_order_type,
            "DEFAULT_TIME_IN_FORCE": config.default_time_in_force,
            "ENTRY_SLIPPAGE_TOLERANCE": str(config.entry_slippage_tolerance),
            "DATA_SOURCE": config.data_source,
            "DEFAULT_INTERVAL": config.default_interval,
            "MIN_DATA_DAYS": str(config.min_data_days),
            "ORDER_MODE": config.order_mode,
            "LIVE_TRADING_CONFIRMED": str(config.live_trading_confirmed).lower(),
        }
        
        for key, value in config_dict.items():
            db_manager.set_config_value(key, value)
        
        logger.info("Bybit configuration saved to database")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save Bybit config: {e}")
        return False


def get_bybit_config_value(db_manager, key: str, default: str = "") -> str:
    """Получить значение конфигурации Bybit."""
    try:
        value = db_manager.get_config_value(key)
        return value if value is not None else default
    except Exception:
        return os.getenv(key, default)


def set_bybit_config_value(db_manager, key: str, value: str):
    """Установить значение конфигурации Bybit."""
    try:
        db_manager.set_config_value(key, value)
    except Exception as e:
        logger.error(f"Failed to set config value {key}: {e}")


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------

def validate_api_credentials(config: BybitConfig) -> tuple[bool, str]:
    """
    Проверить валидность API credentials.
    
    Returns:
        (is_valid, error_message)
    """
    if not config.api_key:
        return False, "BYBIT_API_KEY не задан"
    
    if not config.api_secret:
        return False, "BYBIT_API_SECRET не задан"
    
    if len(config.api_key) < 10:
        return False, "BYBIT_API_KEY выглядит невалидным (слишком короткий)"
    
    if len(config.api_secret) < 10:
        return False, "BYBIT_API_SECRET выглядит невалидным (слишком короткий)"
    
    return True, ""


def validate_trading_settings(config: BybitConfig) -> tuple[bool, list]:
    """
    Проверить настройки торговли.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    if config.default_leverage < 1 or config.default_leverage > 100:
        errors.append(f"BYBIT_DEFAULT_LEVERAGE должен быть 1-100, получено {config.default_leverage}")
    
    if config.max_leverage < config.default_leverage:
        errors.append(f"BYBIT_MAX_LEVERAGE ({config.max_leverage}) должен быть >= BYBIT_DEFAULT_LEVERAGE ({config.default_leverage})")
    
    if config.max_risk_per_trade_pct <= 0 or config.max_risk_per_trade_pct > 100:
        errors.append(f"MAX_RISK_PER_TRADE_PCT должен быть 0-100, получено {config.max_risk_per_trade_pct}")
    
    if config.max_position_pct <= 0 or config.max_position_pct > 100:
        errors.append(f"MAX_POSITION_PCT должен быть 0-100, получено {config.max_position_pct}")
    
    if config.category not in ["linear", "spot", "inverse"]:
        errors.append(f"BYBIT_DEFAULT_CATEGORY должен быть linear/spot/inverse, получено {config.category}")
    
    if config.order_mode not in ["disabled", "paper", "live"]:
        errors.append(f"ORDER_MODE должен быть disabled/paper/live, получено {config.order_mode}")
    
    if config.order_mode == "live" and not config.live_trading_confirmed:
        errors.append("LIVE_TRADING_CONFIRMED должен быть true для live торговли")
    
    if config.order_mode == "live" and config.demo:
        errors.append("Нельзя использовать demo режим с live торговлей")
    
    return len(errors) == 0, errors


def get_config_summary(config: BybitConfig) -> Dict[str, Any]:
    """Получить сводку конфигурации (для логирования/UI)."""
    return {
        "mode": config.order_mode,
        "is_demo": config.demo,
        "is_live": config.is_live,
        "is_paper": config.is_paper,
        "category": config.category,
        "default_leverage": config.default_leverage,
        "max_leverage": config.max_leverage,
        "risk_per_trade": f"{config.max_risk_per_trade_pct}%",
        "max_position": f"{config.max_position_pct}%",
        "max_open_positions": config.max_open_positions,
        "data_source": config.data_source,
        "api_key_configured": bool(config.api_key),
    }
