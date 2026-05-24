"""
Основной файл торгового робота
"""

import time
import logging
from datetime import datetime, timedelta

from scripts.core.forecast_engine import log_error
from scripts.core.actuals_evaluator import fetch_actual_data, evaluate_forecast
from scripts.core.unified_logs_manager import get_forecasts_to_evaluate, update_forecast_with_actuals

_DEFAULT_PIPELINE = None


def _get_pipeline():
    global _DEFAULT_PIPELINE
    if _DEFAULT_PIPELINE is None:
        from scripts.core.pipeline.stages import build_default_pipeline
        _DEFAULT_PIPELINE = build_default_pipeline()
    return _DEFAULT_PIPELINE


def process_ticker(db_manager, ticker, run_id=None, client=None):
    """Полностью обрабатывает один тикер. Возвращает (log_ids, has_non_neutral_consensus)."""
    try:
        logging.info(f"🚀 Начало обработки {ticker}")
        log_ids, has_consensus = _get_pipeline().run(
            ticker, db_manager, run_id=run_id, client=client
        )
        logging.info(f"✅ Завершена обработка {ticker}")
        return log_ids, has_consensus
    except Exception as e:
        logging.error(f"❌ Критическая ошибка обработки {ticker}: {e}")
        log_error(db_manager, ticker, "GENERAL", str(e))
        return [], False

def evaluate_past_forecasts(db_manager):
    """Оценивает предыдущие прогнозы через consensus_evaluator (основной путь)."""
    try:
        logging.info("📊 Начало оценки предыдущих прогнозов")
        from scripts.core.consensus_evaluator import evaluate_consensus_records
        count = evaluate_consensus_records(db_manager)
        logging.info(f"✅ Оценка завершена. Обработано {count} consensus записей")
    except Exception as e:
        logging.error(f"❌ Критическая ошибка оценки прогнозов: {e}")
        raise


def evaluate_logs_records(db_manager) -> int:
    """Оценивает individual Logs записи (NEW → EVALUATED) с фактическими данными.

    Returns:
        int: количество успешно оценённых записей
    """
    try:
        logging.info("📊 Начало оценки individual Logs записей")

        forecasts = get_forecasts_to_evaluate(db_manager)
        if not forecasts:
            logging.info("ℹ️ Нет Logs записей для оценки")
            return 0

        evaluated = 0
        no_data = 0
        errors = 0
        total = len(forecasts)

        for idx, record in enumerate(forecasts, 1):
            log_id = record.get('id')
            ticker = record.get('ticker', '')
            forecast_date = record.get('forecast_date', '')

            try:
                # Загрузка фактических данных
                actual_data = fetch_actual_data(ticker, forecast_date, db_manager=db_manager)
                if not actual_data:
                    no_data += 1
                    logging.info(f"  [{idx}/{total}] {log_id} {ticker} → NO_DATA")
                    continue

                # Оценка прогноза
                evaluation = evaluate_forecast(record, actual_data)
                if not evaluation:
                    errors += 1
                    logging.warning(f"  [{idx}/{total}] {log_id} {ticker} → evaluation empty")
                    continue

                # Объединяем actual_data + evaluation
                merged = {}
                merged.update(actual_data)
                merged.update(evaluation)

                # Сохраняем результат
                success = update_forecast_with_actuals(db_manager, log_id, merged)
                if success:
                    evaluated += 1
                    logging.info(f"  [{idx}/{total}] {log_id} {ticker} → EVALUATED")
                else:
                    errors += 1
                    logging.warning(f"  [{idx}/{total}] {log_id} {ticker} → update failed")

            except Exception as e:
                errors += 1
                logging.error(f"  [{idx}/{total}] {log_id} {ticker} → error: {e}")

        logging.info(
            f"✅ Logs evaluation completed: evaluated={evaluated}/{total}, "
            f"no_data={no_data}, errors={errors}"
        )
        return evaluated

    except Exception as e:
        logging.error(f"❌ Критическая ошибка оценки Logs записей: {e}")
        return 0

def run_trading_bot(db_file: str = None, run_id: int = None, db_manager=None):
    """Основная функция запуска торгового робота.
    
    Args:
        db_file: Путь к файлу БД (не используется если передан db_manager)
        run_id: ID запуска для трекинга (если None - создаётся автоматически)
        db_manager: Готовый экземпляр SQLiteManager (оптимально для scheduler)
    
    Returns:
        int: run_id или None при ошибке
    """
    try:
        logging.info("🚀 Запуск торгового робота")

        from scripts.core.sqlite_manager import SQLiteManager
        import os
        
        if db_manager is None:
            if not db_file:
                from scripts.server.config import get_db_path
                db_file = get_db_path()
            db_manager = SQLiteManager(db_file)

        # Initialize Bybit client for price data fetching
        try:
            from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
            from scripts.core.bybit_client import init_bybit_client, get_bybit_client
            config = load_bybit_config(db_manager)
            is_valid, error = validate_api_credentials(config)
            if is_valid:
                init_bybit_client(
                    api_key=config.api_key,
                    api_secret=config.api_secret,
                    demo=config.demo,
                    recv_window=config.recv_window,
                )
                client = get_bybit_client()
                logging.info(f"📡 Bybit client initialized (demo={config.demo})")
            else:
                logging.warning(f"⚠️ Invalid Bybit credentials: {error}")
                client = None
        except Exception as e:
            logging.warning(f"⚠️ Failed to initialize Bybit client: {e}")
            client = None

        # Читаем настройки (один вызов — используется и для tickers_planned, и для итерации)
        active_tickers = db_manager.get_settings()

        # Создаём запись о запуске если run_id не передан
        if run_id is None:
            run_id = db_manager.create_forecast_run('scheduler', len(active_tickers))
            if run_id:
                logging.info(f"📋 Создан forecast run #{run_id}")
        
        if not active_tickers:
            logging.warning("⚠️ Нет активных тикеров для обработки")
            if run_id:
                db_manager.complete_forecast_run(run_id, status='completed', tickers_processed=0, consensus_count=0)
            return run_id
        
        logging.info(f"📊 Активные тикеры: {', '.join(active_tickers)}")
        
        # Обрабатываем каждый тикер
        processed = 0
        consensus_count = 0
        for ticker in active_tickers:
            try:
                _log_ids, _has_consensus = process_ticker(db_manager, ticker, run_id=run_id, client=client)
                processed += 1
                if _has_consensus:
                    consensus_count += 1
            except Exception as e:
                logging.error(f"❌ Ошибка обработки {ticker}: {e}")
        
        # Завершаем запись о запуске
        if run_id:
            db_manager.complete_forecast_run(run_id, status='completed', 
                                            tickers_processed=processed, 
                                            consensus_count=consensus_count)
            logging.info(f"✅ Forecast run #{run_id} завершён: {processed} тикеров, {consensus_count} консенсусов")
        else:
            logging.info("✅ Работа торгового робота завершена")
        
        return run_id
        
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")
        # При ошибке отмечаем run как failed
        if run_id and db_manager:
            try:
                db_manager.complete_forecast_run(run_id, status='failed', error_message=str(e))
            except:
                pass
        raise

def test_single_ticker(ticker='BTCUSDT', db_file: str = None):
    """Тестирование робота на одном тикере с созданием run"""
    try:
        logging.info(f"🧪 Тестирование на тикере {ticker}")

        from scripts.core.sqlite_manager import SQLiteManager
        import os
        if not db_file:
            from scripts.server.config import get_db_path
            db_file = get_db_path()
        db_manager = SQLiteManager(db_file)

        # Initialize Bybit client for price data fetching
        try:
            from scripts.core.bybit_config import load_bybit_config, validate_api_credentials
            from scripts.core.bybit_client import init_bybit_client, get_bybit_client
            config = load_bybit_config(db_manager)
            is_valid, error = validate_api_credentials(config)
            if is_valid:
                init_bybit_client(
                    api_key=config.api_key,
                    api_secret=config.api_secret,
                    demo=config.demo,
                    recv_window=config.recv_window,
                )
                client = get_bybit_client()
                logging.info(f"📡 Bybit client initialized (demo={config.demo})")
            else:
                logging.warning(f"⚠️ Invalid Bybit credentials: {error}")
                client = None
        except Exception as e:
            logging.warning(f"⚠️ Failed to initialize Bybit client: {e}")
            client = None

        # Создаём run для теста
        run_id = db_manager.create_forecast_run('manual', 1)
        _, has_consensus = process_ticker(db_manager, ticker, run_id=run_id, client=client)
        consensus_count = 1 if has_consensus else 0
        db_manager.complete_forecast_run(run_id, status='completed', tickers_processed=1, consensus_count=consensus_count)

        logging.info(f"✅ Тест для {ticker} завершен, run #{run_id}")
        return run_id

    except Exception as e:
        logging.error(f"❌ Ошибка теста: {e}")
        return None

def clear_all_data(db_file: str = None):
    """Очищает все данные (кроме настроек и конфига)"""
    try:
        logging.info("🧹 Очистка всех данных...")

        from scripts.core.sqlite_manager import SQLiteManager
        import os
        if not db_file:
            from scripts.server.config import get_db_path
            db_file = get_db_path()
        db_manager = SQLiteManager(db_file)

        sheets_to_clear = ['PriceData', 'Indicators', 'Logs']
        
        for sheet_name in sheets_to_clear:
            success = db_manager.clear_sheet(sheet_name, keep_headers=True)
            if success:
                logging.info(f"✅ Лист {sheet_name} очищен")
            else:
                logging.warning(f"⚠️ Лист {sheet_name} не найден")
        
        logging.info("✅ Очистка завершена")
        
    except Exception as e:
        logging.error(f"❌ Ошибка очистки: {e}")

if __name__ == "__main__":
    import sys
    from scripts.bootstrap import bootstrap_paths

    bootstrap_paths()

    # Обработка командной строки
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == '--init':
            logging.info("🔧 Инициализация базы данных...")
            from scripts.core.sqlite_manager import SQLiteManager
            SQLiteManager()

        elif command == '--test':
            ticker = sys.argv[2] if len(sys.argv) > 2 else 'BTCUSDT'
            test_single_ticker(ticker)
            
        elif command == '--evaluate':
            logging.info("📊 Оценка предыдущих прогнозов")
            from scripts.core.sqlite_manager import SQLiteManager
            db_manager = SQLiteManager()
            evaluate_past_forecasts(db_manager)
            evaluate_logs_records(db_manager)
            
        elif command == '--forecast':
            logging.info("🤖 Генерация новых прогнозов")
            run_trading_bot()
            
        elif command == '--full':
            logging.info("🔄 Полный цикл: оценка + генерация")
            from scripts.core.sqlite_manager import SQLiteManager
            db_manager = SQLiteManager()
            evaluate_past_forecasts(db_manager)
            evaluate_logs_records(db_manager)
            run_trading_bot()
            
        elif command == '--clear':
            clear_all_data()
            
        else:
            print("Неизвестная команда")
            print("Доступные команды:")
            print("  --init - инициализация базы данных")
            print("  --test [ticker] - тестовый запуск")
            print("  --evaluate - оценка предыдущих прогнозов")
            print("  --forecast - генерация новых прогнозов")
            print("  --full - полный цикл (оценка + генерация)")
            print("  --clear - очистка данных")
    else:
        # Обычный запуск
        run_trading_bot()
