"""
Управление промптами из Excel таблицы
"""

import pandas as pd
import logging
from datetime import datetime

def get_prompts_from_excel(db_manager, ticker=None):
    """
    Загружает промпты из Excel таблицы
    
    Args:
        db_manager: ExcelManager объект
        ticker: тикер для фильтрации (опционально)
    
    Returns:
        dict: словарь промптов по методам
    """
    try:
        # Читаем лист Prompts
        df = db_manager.read_sheet('Prompts')
        
        if df.empty:
            logging.warning("⚠️ Лист Prompts пуст")
            return get_default_prompts()
        
        # Фильтруем по тикеру если указан
        if ticker and 'ticker' in df.columns:
            ticker_df = df[df['ticker'] == ticker]
            if not ticker_df.empty:
                df = ticker_df
            else:
                logging.warning(f"⚠️ Промпты для тикера {ticker} не найдены, используем последние")
        
        # Берем последнюю запись
        if len(df) > 0:
            latest_prompt = df.iloc[-1]
            logging.info(f"📝 Используем промпты от {latest_prompt.get('request_date', 'unknown')}")
            
            # Формируем словарь промптов
            prompts = {}
            for i in range(1, 7):
                prompt_key = f'prompt_{i}'
                method_key = get_method_key(i)
                
                if prompt_key in latest_prompt and pd.notna(latest_prompt[prompt_key]):
                    prompts[method_key] = latest_prompt[prompt_key]
                else:
                    logging.warning(f"⚠️ Промпт {prompt_key} не найден")
                    prompts[method_key] = get_default_prompt(method_key)
            
            return prompts
        else:
            logging.warning("⚠️ Нет данных в Prompts")
            return get_default_prompts()
            
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки промптов из Excel: {e}")
        return get_default_prompts()

def get_method_key(prompt_number):
    """Возвращает ключ метода по номеру промпта"""
    method_map = {
        1: 'momentum_trend',
        2: 'price_action',
        3: 'relative_strength',
        4: 'volatility',
        5: 'mean_reversion',
        6: 'volume_breakout'
    }
    return method_map.get(prompt_number, f'method_{prompt_number}')

def get_default_prompts():
    """Возвращает промпты по умолчанию из кода"""
    return {
        'momentum_trend': get_default_prompt('momentum_trend'),
        'price_action': get_default_prompt('price_action'),
        'relative_strength': get_default_prompt('relative_strength'),
        'volatility': get_default_prompt('volatility'),
        'mean_reversion': get_default_prompt('mean_reversion'),
        'volume_breakout': get_default_prompt('volume_breakout')
    }

def get_default_prompt(method):
    """Возвращает промпт по умолчанию для метода"""
    default_prompts = {
        'momentum_trend': """
        Проанализируй тренд и импульс для {ticker} на {date}.
        Используй технические индикаторы для определения направления.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """,
        
        'price_action': """
        Проанализируй price action для {ticker} на {date}.
        Оцени позицию цены относительно уровней поддержки и сопротивления.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """,
        
        'relative_strength': """
        Проанализируй относительную силу {ticker} на {date}.
        Сравни с рынком и оцени силу тренда.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """,
        
        'volatility': """
        Проанализируй волатильность {ticker} на {date}.
        Оцени уровень риска и возможные движения.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """,
        
        'mean_reversion': """
        Проанализируй возможность возврата к среднему для {ticker} на {date}.
        Оцени отклонение от исторических средних.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """,
        
        'volume_breakout': """
        Проанализируй объемы и пробои для {ticker} на {date}.
        Оцени силу тренда по объемам.
        Ответь в формате JSON с confidence, side, entry_conditions, exit_target, exit_stop, rationale.
        """
    }
    
    return default_prompts.get(method, "Проанализируй {ticker} на {date}. Ответь в формате JSON.")

def format_prompt_with_data(prompt, ticker, indicators):
    """
    Форматирует промпт с данными тикера и индикаторов
    
    Args:
        prompt: шаблон промпта
        ticker: тикер
        indicators: словарь индикаторов
    
    Returns:
        str: отформатированный промпт
    """
    try:
        from datetime import datetime, timedelta
        
        # Определяем дату прогноза
        tomorrow = datetime.now() + timedelta(days=1)
        forecast_date = tomorrow.strftime('%Y-%m-%d')
        
        # Базовые замены
        formatted_prompt = prompt.replace('{ticker}', ticker)
        formatted_prompt = formatted_prompt.replace('{date}', forecast_date)
        
        # Добавляем технические данные если нужно
        if '{' in formatted_prompt and '}' in formatted_prompt:
            # Рассчитываем ATR в процентах
            atr_percent = (indicators['atr14'] / indicators['price'] * 100) if indicators['price'] > 0 else 0
            
            # Формируем технические данные
            tech_data = f"""
            
            ТЕХНИЧЕСКИЕ ДАННЫЕ:
            Цена: ${indicators['price']:.2f}
            MA20: ${indicators['ma20']:.2f}, MA50: ${indicators['ma50']:.2f}, MA200: ${indicators['ma200']:.2f}
            RSI: {indicators['rsi14']:.1f}, ATR: ${indicators['atr14']:.2f} ({atr_percent:.1f}%)
            Bollinger Bands: верхняя ${indicators['bb']['upper']:.2f}, нижняя ${indicators['bb']['lower']:.2f}
            Динамика: 5д: {indicators['change_5d']:.1f}%, 20д: {indicators['change_20d']:.1f}%
            Объем: текущий {indicators['volume_current']:,}, средний {indicators['volume_avg_20']:,}
            """
            
            formatted_prompt += tech_data
        
        # Добавляем требуемый формат ответа
        if "JSON" not in formatted_prompt:
            formatted_prompt += """
            
            ОТВЕТЬ В ФОРМАТЕ JSON:
            {
                "confidence": число от 0 до 100,
                "side": "LONG" или "SHORT" или "NEUTRAL", 
                "entry_conditions": ["условие1", "условие2"],
                "exit_target": "цель выхода",
                "exit_stop": "стоп-лосс",
                "rationale": "обоснование прогноза"
            }
            """
        
        return formatted_prompt
        
    except Exception as e:
        logging.error(f"❌ Ошибка форматирования промпта: {e}")
        return prompt
