"""
Модуль оценки прогнозов и добавления фактических данных
"""

import logging
from datetime import datetime, timedelta
import pandas as pd
from scripts.core.bybit_data_loader import fetch_price_data_bybit as fetch_price_data

def fetch_actual_data(ticker, forecast_date, db_manager=None):
    try:
        # Преобразуем forecast_date в datetime если это строка
        if isinstance(forecast_date, str):
            target_date = datetime.strptime(forecast_date, '%Y-%m-%d').date()
        elif hasattr(forecast_date, 'date'):
            target_date = forecast_date.date()
        else:
            target_date = forecast_date

        # Загружаем данные за период вокруг даты прогноза
        # days_needed считаем от сегодня, чтобы target_date гарантированно попал в окно
        today = datetime.now().date()
        days_back = (today - target_date).days + 14  # +14 дней запаса
        days_needed = max(days_back, 30)
        
        logging.info(f"📊 Загрузка фактических данных для {ticker} на {forecast_date}")
        
        # Используем кэширование если доступно
        price_data = fetch_price_data(ticker, days=days_needed, db_manager=db_manager)
        
        if not price_data:
            logging.error(f"❌ Не удалось загрузить данные для {ticker}")
            return None
        
        # Ищем данные за конкретную дату
        actual_record = None
        for record in price_data:
            # Унифицируем форматы дат для сравнения
            record_date = record['date'].strftime('%Y-%m-%d') if hasattr(record['date'], 'strftime') else str(record['date'])
            forecast_date_str = target_date.strftime('%Y-%m-%d') if hasattr(target_date, 'strftime') else str(target_date)
            
            if record_date == forecast_date_str:
                actual_record = record
                break
        
        if not actual_record:
            logging.warning(f"⚠️ Данные за {forecast_date} не найдены для {ticker}")
            # Берем ближайшую доступную дату
            if price_data:
                # Унифицируем даты для сравнения
                def date_distance(record):
                    record_date = record['date']
                    if hasattr(record_date, 'date'):
                        record_date = record_date.date()
                    elif isinstance(record_date, str):
                        record_date = datetime.strptime(record_date, '%Y-%m-%d').date()
                    return abs((record_date - target_date).days)
                
                actual_record = min(price_data, key=date_distance)
                logging.info(f"📅 Используем ближайшую дату: {actual_record['date']}")
            else:
                return None
        
        # Формируем результат
        actual_date = actual_record['date']
        if hasattr(actual_date, 'strftime'):
            actual_date_str = actual_date.strftime('%Y-%m-%d')
        else:
            actual_date_str = str(actual_date)
        
        actual_data = {
            'actual_date': actual_date_str,
            'actual_open': float(actual_record['open']),
            'actual_close': float(actual_record['close']),
            'actual_high': float(actual_record['high']),
            'actual_low': float(actual_record['low']),
            'actual_volume': int(actual_record['volume'])
        }
        
        logging.info(f"✅ Загружены фактические данные для {ticker}: close=${actual_data['actual_close']:.2f}")
        return actual_data
        
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки фактических данных: {e}")
        return None

def evaluate_forecast(forecast_record, actual_data):
    """
    Оценивает прогноз против фактических данных.

    Improvements (ред. 2):
    - Uses numeric stop_loss column (preferred over exit_stop string)
    - Stop-loss PRIORITY: stop_hit=True always → exit_successful=0 (conservative)
    - PnL uses numeric stop_loss when stop triggered, numeric target otherwise

    Args:
        forecast_record: dict — запись прогноза
        actual_data: dict — фактические данные {actual_close, actual_high, actual_low}

    Returns:
        dict: результаты оценки
    """
    try:
        evaluation = {}

        # entry_price
        raw_entry = forecast_record.get('entry_price')
        try:
            _ep = float(raw_entry) if raw_entry is not None else 0.0
        except (TypeError, ValueError):
            _ep = 0.0
        forecast_price = _ep if _ep > 0 else actual_data['actual_close']
        actual_close = actual_data['actual_close']
        actual_high  = actual_data['actual_high']
        actual_low   = actual_data['actual_low']

        forecast_side = str(forecast_record.get('side', 'NEUTRAL')).upper()
        exit_target   = forecast_record.get('exit_target', '')
        exit_stop     = forecast_record.get('exit_stop', '')

        # Prefer numeric stop_loss column; fallback to parsing exit_stop string
        numeric_stop = None
        raw_sl = forecast_record.get('stop_loss')
        if raw_sl is not None:
            try:
                v = float(raw_sl)
                if v > 0:
                    numeric_stop = v
            except (TypeError, ValueError):
                pass

        # Проверяем достижение целей (conservative High/Low with stop priority)
        target_hit, stop_hit, entry_triggered = check_targets(
            forecast_side, exit_target, exit_stop, actual_high, actual_low, forecast_price,
            numeric_stop=numeric_stop,
        )

        # Stop-loss PRIORITY: if stop was hit at all → failure (conservative; no intraday data)
        exit_successful = None
        if forecast_side != 'NEUTRAL' and entry_triggered:
            if stop_hit:
                exit_successful = 0  # Stop has priority — always failure
            elif target_hit:
                exit_successful = 1  # Only target, no stop → success
            # else: still open (neither hit)

        evaluation.update({
            'entry_triggered': entry_triggered,
            'target_hit':      target_hit,
            'stop_hit':        stop_hit,
            'exit_successful': exit_successful,
        })

        # PnL: if stop_hit use stop_loss price; else use actual_close or parsed target
        if stop_hit and numeric_stop:
            pnl_exit = numeric_stop
        else:
            pnl_exit = actual_close
        pnl_pct = calculate_pnl(forecast_side, forecast_price, pnl_exit, target_hit, stop_hit)
        evaluation['pnl_pct'] = pnl_pct

        direction_correct = evaluate_direction(forecast_side, forecast_price, actual_close)
        evaluation['direction_correct'] = direction_correct

        logging.info(
            f"\U0001f4ca Оценка прогноза {forecast_record.get('method')}: "
            f"direction_correct={direction_correct}, pnl_pct={pnl_pct:.2f}% "
            f"(stop_priority={stop_hit})"
        )

        return evaluation

    except Exception as e:
        logging.error(f"❌ Ошибка оценки прогноза: {e}")
        return {}

def check_targets(side, target_str, stop_str, actual_high, actual_low, entry_price,
                  numeric_stop=None):
    """
    Проверяет достижение целей и стопов.

    Conservative High/Low evaluation (daily bars only):
    - For LONG: target hit if actual_high >= target; stop hit if actual_low <= stop
    - For SHORT: target hit if actual_low <= target; stop hit if actual_high >= stop
    - numeric_stop preferred over parsing stop_str

    Returns:
        tuple: (target_hit, stop_hit, entry_triggered)
    """
    try:
        side = str(side).upper()
        if side == 'NEUTRAL':
            return False, False, False

        target_price = parse_price_target(target_str, entry_price, side)
        # Prefer numeric stop_loss; fallback to parsing exit_stop
        if numeric_stop and numeric_stop > 0:
            stop_price = numeric_stop
        else:
            stop_price = parse_price_target(stop_str, entry_price, side, is_stop=True)

        target_hit = False
        stop_hit   = False
        # entry_triggered: price must have reached the entry level
        if entry_price and entry_price > 0:
            if side == 'LONG':
                entry_triggered = actual_low <= entry_price
            elif side == 'SHORT':
                entry_triggered = actual_high >= entry_price
            else:
                entry_triggered = True
        else:
            entry_triggered = True

        if side == 'LONG':
            target_hit = bool(target_price and actual_high >= target_price)
            stop_hit   = bool(stop_price   and actual_low  <= stop_price)
        elif side == 'SHORT':
            target_hit = bool(target_price and actual_low  <= target_price)
            stop_hit   = bool(stop_price   and actual_high >= stop_price)

        return target_hit, stop_hit, entry_triggered

    except Exception as e:
        logging.error(f"\u274c Ошибка проверки целей: {e}")
        return False, False, False

def parse_price_target(target_str, entry_price, side, is_stop=False):
    """
    Парсит строку цели в числовое значение
    
    Args:
        target_str: строка цели ("цена + 5%", "$185.50", и т.д.)
        entry_price: цена входа
        side: LONG/SHORT
        is_stop: это стоп-лосс
    
    Returns:
        float: целевая цена или None
    """
    import re
    try:
        if not target_str or pd.isna(target_str):
            return None
        
        target_str = str(target_str).strip()
        
        # Процент имеет приоритет над абсолютным числом
        if '%' in target_str:
            percent_match = re.search(r'([+-]?\d+\.?\d*)%', target_str)
            if percent_match:
                percent = abs(float(percent_match.group(1)))
                if is_stop:
                    # Стоп всегда против направления сделки
                    percent = -percent if side == 'LONG' else percent
                else:
                    # Тейк всегда по направлению сделки
                    percent = percent if side == 'LONG' else -percent
                return entry_price * (1 + percent / 100)
        
        # Ищем число после знака $ (приоритет), иначе первое число в строке
        dollar_match = re.search(r'\$(\d+\.?\d*)', target_str)
        if dollar_match:
            return float(dollar_match.group(1))
        numbers = re.findall(r'\d+\.?\d*', target_str)
        if numbers:
            return float(numbers[0])  # берём первое число — обычно это цена
        
        return None
        
    except Exception as e:
        logging.error(f"❌ Ошибка парсинга цели '{target_str}': {e}")
        return None

def calculate_pnl(side, entry_price, exit_price, target_hit, stop_hit):
    """
    Рассчитывает PnL в процентах
    
    Args:
        side: LONG/SHORT/NEUTRAL
        entry_price: цена входа
        exit_price: цена выхода
        target_hit: была ли достигнута цель
        stop_hit: был ли сработан стоп
    
    Returns:
        float: PnL в процентах
    """
    try:
        if side == 'NEUTRAL':
            return 0.0
        
        # Проверяем валидность цен
        if entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0:
            logging.warning(f"⚠️ Некорректные цены: entry={entry_price}, exit={exit_price}")
            return 0.0
        
        # Базовый PnL
        if side == 'LONG':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:  # SHORT
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        
        # No artificial multipliers — PnL reflects actual price movement only
        
        return round(pnl_pct, 2)
        
    except Exception as e:
        logging.error(f"❌ Ошибка расчета PnL: {e}")
        return 0.0

def evaluate_direction(side, entry_price, exit_price):
    """
    Оценивает правильность направления прогноза
    
    Args:
        side: LONG/SHORT/NEUTRAL
        entry_price: цена входа
        exit_price: цена выхода
    
    Returns:
        bool: правильность направления
    """
    try:
        if side == 'NEUTRAL':
            return abs(exit_price - entry_price) / entry_price < 0.01  # <1% изменения
        
        if side == 'LONG':
            return exit_price > entry_price
        else:  # SHORT
            return exit_price < entry_price
            
    except Exception as e:
        logging.error(f"❌ Ошибка оценки направления: {e}")
        return False

def calibrate_confidence(predicted_confidence, was_correct):
    """
    Калибрует уверенность прогноза
    
    Args:
        predicted_confidence: предсказанная уверенность (0-100)
        was_correct: был ли прогноз правильным
    
    Returns:
        float: калиброванная уверенность
    """
    try:
        # Простая калибровка: если прогноз правильный, повышаем уверенность
        # если неправильный, понижаем
        if was_correct:
            # Увеличиваем уверенность, но не выше 95
            calibrated = min(95, predicted_confidence + 5)
        else:
            # Уменьшаем уверенность, но не ниже 5
            calibrated = max(5, predicted_confidence - 10)
        
        return round(calibrated, 1)
        
    except Exception as e:
        logging.error(f"❌ Ошибка калибровки уверенности: {e}")
        return predicted_confidence
