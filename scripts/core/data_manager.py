"""
Работа с локальными данными

.. deprecated::
    DataManager is superseded by SQLiteManager. This module will be removed in a future
    version. Import from scripts.core.sqlite_manager instead.
"""

import warnings
warnings.warn(
    "data_manager.DataManager is deprecated and will be removed. "
    "Use scripts.core.sqlite_manager.SQLiteManager instead.",
    DeprecationWarning,
    stacklevel=2,
)

import pandas as pd
import os
from datetime import datetime
import logging

class DataManager:
    """Управление локальными данными"""
    
    def __init__(self, data_file='trading_robot.xlsx'):
        self.data_file = data_file
        self.initialize_storage()
    
    def initialize_storage(self):
        """Создает файл данных с необходимыми листами"""
        try:
            # Проверяем существует ли файл
            if not os.path.exists(self.data_file):
                logging.info(f"📋 Создание нового файла данных: {self.data_file}")
                
                # Создаем Excel writer
                with pd.ExcelWriter(self.data_file, engine='openpyxl') as writer:
                    # Config
                    config_df = pd.DataFrame(columns=['Parameter', 'Value'])
                    config_df.to_excel(writer, sheet_name='Config', index=False)
                    
                    # Settings
                    settings_df = pd.DataFrame(columns=['ticker', 'active', 'comment'])
                    settings_df.to_excel(writer, sheet_name='Settings', index=False)
                    
                    # Добавляем начальные данные (crypto by default)
                    settings_data = [
                        ['BTCUSDT', 1, 'Bitcoin - Linear Perpetual'],
                        ['ETHUSDT', 1, 'Ethereum - Linear Perpetual'],
                        ['SOLUSDT', 0, 'Solana - Linear Perpetual (inactive)']
                    ]
                    settings_df = pd.DataFrame(settings_data, columns=['ticker', 'active', 'comment'])
                    settings_df.to_excel(writer, sheet_name='Settings', index=False)
                    
                    # Prompts (промпты для ИИ)
                    prompts_df = pd.DataFrame(columns=[
                        'date', 'ticker', 'method', 'prompt_text'
                    ])
                    prompts_df.to_excel(writer, sheet_name='Prompts', index=False)
                    
                    # Providers (API ключи и настройки)
                    providers_df = pd.DataFrame(columns=[
                        'provider', 'api_key', 'model', 'temperature', 'max_tokens', 'rate_limit', 'active'
                    ])
                    # Добавляем настройки по умолчанию
                    default_providers = [
                        {
                            'provider': 'perplexity',
                            'api_key': '',
                            'model': 'sonar-pro',
                            'temperature': 0.2,
                            'max_tokens': 1500,
                            'rate_limit': 60,
                            'active': 1
                        },
                        {
                            'provider': 'alpha_vantage',
                            'api_key': '',
                            'model': '',
                            'temperature': '',
                            'max_tokens': '',
                            'rate_limit': 5,
                            'active': 1
                        }
                    ]
                    providers_df = pd.DataFrame(default_providers)
                    providers_df.to_excel(writer, sheet_name='Providers', index=False)
                    
                    # PriceData
                    price_df = pd.DataFrame(columns=['ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                    price_df.to_excel(writer, sheet_name='PriceData', index=False)
                    
                    # Indicators
                    indicators_df = pd.DataFrame(columns=[
                        'ticker', 'date', 'price', 'ma20', 'ma50', 'ma200',
                        'rsi14', 'atr14', 'bb_upper', 'bb_lower', 'change_5d', 'change_20d'
                    ])
                    indicators_df.to_excel(writer, sheet_name='Indicators', index=False)
                    
                                        
                    # Logs (единая таблица логов и прогнозов)
                    log_df = pd.DataFrame(columns=[
                        'id', 'forecast_date', 'created_at', 'ticker', 'method', 'confidence', 'side',
                        'entry_conditions', 'exit_target', 'exit_stop', 'position_size', 'rationale',
                        'forecast_prompt', 'prompt_response', 'model', 'status', 'actual_date', 'actual_close', 'actual_high', 'actual_low',
                        'entry_triggered', 'target_hit', 'stop_hit', 'pnl_pct', 'direction_correct'
                    ])
                    log_df.to_excel(writer, sheet_name='Logs', index=False)
                
                logging.info("✅ Файл данных успешно создан со всеми листами")
            else:
                logging.info(f"📋 Используем существующий файл данных: {self.data_file}")
                
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации хранилища: {e}")
            raise
    
    def read_sheet(self, sheet_name):
        """Читает данные из листа"""
        try:
            df = pd.read_excel(self.data_file, sheet_name=sheet_name)
            logging.info(f"📊 Прочитано {len(df)} записей из листа '{sheet_name}'")
            return df
        except Exception as e:
            logging.error(f"❌ Ошибка чтения листа '{sheet_name}': {e}")
            return pd.DataFrame()
    
    def update_row_by_id(self, sheet_name, row_id, update_data):
        """Обновляет строку по ID"""
        try:
            # Читаем существующие данные
            df = self.read_sheet(sheet_name)
            
            if df.empty:
                logging.error(f"❌ Лист '{sheet_name}' пуст")
                return False
            
            # Находим строку по ID
            if 'id' not in df.columns:
                logging.error(f"❌ В листе '{sheet_name}' нет колонки 'id'")
                return False
            
            mask = df['id'] == row_id
            if not mask.any():
                logging.error(f"❌ Строка с ID '{row_id}' не найдена")
                return False
            
            # Обновляем данные
            for key, value in update_data.items():
                if key in df.columns:
                    df.loc[mask, key] = value
                else:
                    logging.warning(f"⚠️ Колонка '{key}' не существует в листе '{sheet_name}'")
            
            # Сохраняем обновленные данные
            with pd.ExcelWriter(self.data_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            logging.info(f"✅ Обновлена строка с ID '{row_id}' в листе '{sheet_name}'")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка обновления строки: {e}")
            return False
    
    def append_to_sheet(self, sheet_name, data):
        """Добавляет данные в лист"""
        try:
            # Читаем существующие данные
            existing_df = self.read_sheet(sheet_name)
            
            # Конвертируем данные в DataFrame
            if isinstance(data, dict):
                # Если это одна запись
                new_df = pd.DataFrame([data])
            elif isinstance(data, list):
                # Если это список записей
                new_df = pd.DataFrame(data)
            else:
                # Если это уже DataFrame
                new_df = data
            
            # Объединяем данные
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Сохраняем в Excel
            with pd.ExcelWriter(self.data_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            logging.info(f"✅ Добавлено {len(new_df)} записей в лист '{sheet_name}'")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка добавления данных в лист '{sheet_name}': {e}")
            return False
    
    def clear_sheet(self, sheet_name, keep_headers=True):
        """Очищает лист"""
        try:
            if keep_headers:
                # Читаем заголовки
                df = pd.read_excel(self.data_file, sheet_name=sheet_name, nrows=0)
                
                # Сохраняем только заголовки
                with pd.ExcelWriter(self.data_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                # Создаем пустой лист
                empty_df = pd.DataFrame()
                with pd.ExcelWriter(self.data_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    empty_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            logging.info(f"✅ Лист '{sheet_name}' очищен")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка очистки листа '{sheet_name}': {e}")
            return False
    
    def get_settings(self):
        """Получает настройки тикеров"""
        try:
            df = self.read_sheet('Settings')
            # Фильтруем активные тикеры
            active_tickers = df[df['active'].isin([1, '1', True, 'true', 'True'])]['ticker'].tolist()
            return active_tickers
        except Exception as e:
            logging.error(f"❌ Ошибка получения настроек: {e}")
            return []
    
    def get_cached_price_data(self, ticker, days=250):
        """Получает кэшированные данные цен"""
        try:
            df = self.read_sheet('PriceData')
            
            # Фильтруем по тикеру
            ticker_data = df[df['ticker'] == ticker].copy()
            
            if ticker_data.empty:
                return None
            
            # Конвертируем даты
            ticker_data['Date'] = pd.to_datetime(ticker_data['Date'])
            
            # Сортируем по дате
            ticker_data = ticker_data.sort_values('Date')
            
            # Фильтруем по последним дням
            cutoff_date = datetime.now() - pd.Timedelta(days=days)
            recent_data = ticker_data[ticker_data['Date'] >= cutoff_date]
            
            if recent_data.empty:
                return None
            
            # Конвертируем в формат словарей
            price_data = []
            for _, row in recent_data.iterrows():
                price_data.append({
                    'ticker': row['ticker'],
                    'date': row['Date'],
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })
            
            logging.info(f"✅ Загружено {len(price_data)} дней кэшированных данных для {ticker}")
            return price_data
            
        except Exception as e:
            logging.error(f"❌ Ошибка загрузки кэшированных данных: {e}")
            return None
    
    def save_price_data(self, price_data):
        """Сохраняет данные цен с кэшированием"""
        try:
            if not price_data:
                return True
            
            # Получаем существующие данные
            existing_df = self.read_sheet('PriceData')
            
            # Конвертируем новые данные в DataFrame
            new_df = pd.DataFrame(price_data)
            
            # Создаем уникальный ключ для каждой записи
            if 'ticker' not in new_df.columns:
                new_df['ticker'] = new_df.get('ticker', '')
            
            new_df['date_str'] = pd.to_datetime(new_df['date']).dt.strftime('%Y-%m-%d')
            new_df['unique_key'] = new_df['ticker'] + '_' + new_df['date_str']
            
            if not existing_df.empty:
                existing_df['date_str'] = pd.to_datetime(existing_df['Date']).dt.strftime('%Y-%m-%d')
                existing_df['unique_key'] = existing_df['ticker'] + '_' + existing_df['date_str']
                
                # Фильтруем только новые записи
                existing_keys = set(existing_df['unique_key'])
                new_records = new_df[~new_df['unique_key'].isin(existing_keys)]
                
                # Объединяем данные
                combined_df = pd.concat([existing_df, new_records], ignore_index=True)
            else:
                combined_df = new_df
                new_records = new_df
            
            # Удаляем временные колонки
            combined_df = combined_df.drop(['date_str', 'unique_key'], axis=1, errors='ignore')
            
            # Сохраняем в Excel
            with pd.ExcelWriter(self.data_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                combined_df.to_excel(writer, sheet_name='PriceData', index=False)
            
            logging.info(f"✅ Добавлено {len(new_records)} новых записей в PriceData")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения данных цен: {e}")
            return False
