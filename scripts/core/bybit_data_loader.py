"""
Bybit Data Loader — загрузка исторических данных через Bybit API.

Замена yfinance для криптовалютных данных.
Преимущества:
- Более точные цены для торговли
- Поддержка различных таймфреймов
- Данные непосредственно из биржи
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from scripts.core.bybit_client import BybitClient, get_bybit_client

logger = logging.getLogger(__name__)

# Маппинг интервалов в формат Bybit
INTERVAL_MAP = {
    "1m": "1",
    "5m": "5", 
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1D": "D",
    "daily": "D",
    "1w": "W",
    "1W": "W",
    "weekly": "W",
    "1M": "M",
    "monthly": "M"
}


def fetch_bybit_klines(
    symbol: str,
    interval: str = "60",
    days: int = 250,
    client: Optional[BybitClient] = None
) -> List[Dict[str, Any]]:
    """
    Загрузить исторические свечи через Bybit API.
    
    Args:
        symbol: Торговая пара (например "BTCUSDT")
        interval: Таймфрейм ("1", "5", "15", "30", "60", "240", "D", "W", "M")
        days: Количество дней истории
        client: BybitClient (если None — использует глобальный)
    
    Returns:
        Список свечей с полями: date, open, high, low, close, volume
    """
    try:
        # Получаем клиент
        if client is None:
            client = get_bybit_client()
        
        if client is None:
            logger.error("Bybit client not initialized")
            return []
        
        # Конвертируем интервал
        bybit_interval = INTERVAL_MAP.get(interval, interval)
        
        # Вычисляем временной диапазон
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        logger.info(f"📈 Загрузка Bybit данных для {symbol}, interval={bybit_interval}, {days} days")
        
        # Bybit API ограничивает limit до 1000 свечей за запрос
        # Для длительной истории делаем несколько запросов
        all_klines = []
        current_start = start_time
        
        while current_start < end_time:
            klines = client.get_klines(
                symbol=symbol,
                interval=bybit_interval,
                limit=1000,
                start_time=current_start,
                end_time=end_time
            )
            
            if not klines:
                break
            
            all_klines.extend(klines)
            
            # Обновляем start_time для следующего запроса
            last_timestamp = klines[-1]["timestamp_ms"]
            if last_timestamp >= end_time or last_timestamp <= current_start:
                break
            current_start = last_timestamp + 1
        
        # Конвертируем в стандартный формат
        result = []
        for k in all_klines:
            result.append({
                "date": k["datetime"],
                "open": k["open"],
                "high": k["high"],
                "low": k["low"],
                "close": k["close"],
                "volume": k["volume"],
                "turnover": k.get("turnover", 0)
            })
        
        # Удаляем дубликаты и сортируем
        seen_dates = set()
        unique_result = []
        for r in sorted(result, key=lambda x: x["date"]):
            if r["date"] not in seen_dates:
                seen_dates.add(r["date"])
                unique_result.append(r)
        
        logger.info(f"✅ Загружено {len(unique_result)} свечей для {symbol}")
        return unique_result
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки Bybit данных для {symbol}: {e}")
        return []


def fetch_bybit_daily(
    symbol: str,
    days: int = 250,
    client: Optional[BybitClient] = None
) -> List[Dict[str, Any]]:
    """
    Загрузить дневные данные через Bybit.
    
    Args:
        symbol: Торговая пара (например "BTCUSDT")
        days: Количество дней
        client: BybitClient
    
    Returns:
        Список дневных свечей
    """
    return fetch_bybit_klines(symbol, "D", days, client)


def fetch_bybit_intraday(
    symbol: str,
    interval: str = "60",
    days: int = 30,
    client: Optional[BybitClient] = None
) -> List[Dict[str, Any]]:
    """
    Загрузить intraday данные через Bybit.
    
    Args:
        symbol: Торговая пара
        interval: Таймфрейм ("1", "5", "15", "30", "60", "240")
        days: Количество дней истории
        client: BybitClient
    
    Returns:
        Список intraday свечей
    """
    return fetch_bybit_klines(symbol, interval, days, client)


def convert_bybit_to_ohlcv(klines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Конвертировать Bybit формат в стандартный OHLCV.
    
    Args:
        klines: Данные от Bybit API
    
    Returns:
        Список словарей с полями date, open, high, low, close, volume
    """
    result = []
    for k in klines:
        result.append({
            "date": k.get("datetime", k.get("date", "")),
            "open": k.get("open", 0),
            "high": k.get("high", 0),
            "low": k.get("low", 0),
            "close": k.get("close", 0),
            "volume": k.get("volume", 0)
        })
    return result


def get_bybit_ticker_info(symbol: str, client: Optional[BybitClient] = None) -> Optional[Dict[str, Any]]:
    """
    Получить текущую информацию о тикере.
    
    Returns:
        Dict с last_price, bid, ask, volume_24h и т.д.
    """
    try:
        if client is None:
            client = get_bybit_client()
        
        if client is None:
            return None
        
        return client.get_ticker(symbol)
        
    except Exception as e:
        logger.error(f"Error fetching ticker info for {symbol}: {e}")
        return None


def validate_symbol(symbol: str, client: Optional[BybitClient] = None) -> bool:
    """
    Проверить, существует ли торговая пара на Bybit.
    
    Args:
        symbol: Торговая пара (например "BTCUSDT")
        client: BybitClient
    
    Returns:
        True если символ валиден
    """
    try:
        if client is None:
            client = get_bybit_client()
        
        if client is None:
            return False
        
        instruments = client.get_instruments(symbol=symbol)
        return len(instruments) > 0 and instruments[0].get("status") == "Trading"
        
    except Exception as e:
        logger.error(f"Error validating symbol {symbol}: {e}")
        return False


def get_available_symbols(quote_coin: str = "USDT", client: Optional[BybitClient] = None) -> List[str]:
    """
    Получить список доступных торговых пар.
    
    Args:
        quote_coin: Базовая валюта (USDT, USDC)
        client: BybitClient
    
    Returns:
        Список символов (например ["BTCUSDT", "ETHUSDT", ...])
    """
    try:
        if client is None:
            client = get_bybit_client()
        
        if client is None:
            return []
        
        instruments = client.get_instruments()
        symbols = []
        
        for inst in instruments:
            if inst.get("quote_coin") == quote_coin and inst.get("status") == "Trading":
                symbols.append(inst.get("symbol"))
        
        return sorted(symbols)
        
    except Exception as e:
        logger.error(f"Error fetching available symbols: {e}")
        return []


# -----------------------------------------------------------------------------
# Integration with existing data_loader interface
# -----------------------------------------------------------------------------

def fetch_price_data_bybit(
    ticker: str,
    days: int = 250,
    db_manager=None,
    client: Optional[BybitClient] = None
) -> List[Dict[str, Any]]:
    """
    Универсальная функция для совместимости с существующим data_loader.
    
    Args:
        ticker: Тикер в формате Bybit (например "BTCUSDT")
        days: Количество дней
        db_manager: SQLiteManager (опционально для кэширования)
        client: BybitClient
    
    Returns:
        Список ценовых данных
    """
    # Проверяем кэш если db_manager предоставлен
    if db_manager:
        try:
            cached = _load_cached_data(db_manager, ticker, days)
            if cached:
                # Проверяем свежесть кэша
                if _is_cache_fresh(cached, max_age_days=1):
                    logger.info(f"✅ Используем кэшированные данные для {ticker}")
                    return cached
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить кэш: {e}")
    
    # Загружаем через Bybit
    data = fetch_bybit_daily(ticker, days, client)
    
    # Сохраняем в кэш
    if data and db_manager:
        try:
            _save_to_cache(db_manager, ticker, data)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить кэш: {e}")
    
    return data


def _load_cached_data(db_manager, ticker: str, days: int) -> List[Dict[str, Any]]:
    """Загрузить данные из SQLite кэша."""
    try:
        df = db_manager.read_sheet("PriceData")
        if df is None or df.empty:
            return []
        
        # Фильтруем по тикеру
        if "ticker" in df.columns:
            df = df[df["ticker"] == ticker]
        
        if df.empty:
            return []
        
        # Конвертируем в список словарей
        result = []
        for _, row in df.iterrows():
            result.append({
                "date": row.get("date"),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0))
            })
        
        # Сортируем и ограничиваем
        result.sort(key=lambda x: str(x["date"]))
        return result[-days:]
        
    except Exception as e:
        logger.warning(f"Cache load error: {e}")
        return []


def _is_cache_fresh(data: List[Dict[str, Any]], max_age_days: int = 1) -> bool:
    """Проверить, свежи ли данные в кэше."""
    if not data:
        return False
    
    try:
        # Получаем последнюю дату
        last_date_str = data[-1].get("date", "")
        if isinstance(last_date_str, str):
            last_date = datetime.strptime(last_date_str[:10], "%Y-%m-%d")
        else:
            last_date = last_date_str
        
        # Проверяем разницу
        days_diff = (datetime.now() - last_date).days
        return days_diff <= max_age_days
        
    except Exception as e:
        logger.warning(f"Cache freshness check error: {e}")
        return False


def _save_to_cache(db_manager, ticker: str, data: List[Dict[str, Any]]):
    """Сохранить данные в SQLite кэш."""
    try:
        # Преобразуем данные для вставки
        records = []
        for d in data:
            records.append({
                "ticker": ticker,
                "date": d["date"],
                "open": d["open"],
                "high": d["high"],
                "low": d["low"],
                "close": d["close"],
                "volume": d["volume"]
            })
        
        # Используем метод db_manager для вставки/обновления
        if hasattr(db_manager, "bulk_insert_price_data"):
            db_manager.bulk_insert_price_data(records)
        else:
            # Fallback — insert по одному
            for record in records:
                try:
                    db_manager.insert_or_update_price_data(record)
                except Exception:
                    pass
        
        logger.info(f"💾 Сохранено {len(records)} записей в кэш для {ticker}")
        
    except Exception as e:
        logger.warning(f"Cache save error: {e}")
