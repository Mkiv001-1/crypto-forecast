# Order Race Condition Fix

## Описание
При автоматическом режиме (`AUTO_ORDER_SUBMISSION=true`) scheduler может запустить
два параллельных цикла `run_trading_bot` (через `ThreadPoolExecutor` с `max_workers=2`).
Оба цикла вызывают `submit_signal()` для одного тикера. Гард `_has_open_order_for_ticker`
выполняет SELECT без эксклюзивной блокировки, поэтому оба потока проходят проверку
до того, как первый поток успевает вставить строку — и выставляются два ордера.

## Требования
- Для одного тикера одновременно может выполняться только один вызов `submit_signal`.
- Решение должно работать в рамках одного OS-процесса (два потока scheduler).
- Не должно блокировать ордера для разных тикеров.
- Не требует изменений схемы БД.

## Архитектурные решения

### Выбранный подход: per-ticker threading.Lock в order_manager
- Словарь `_ticker_locks: Dict[str, threading.Lock]` + `_ticker_locks_guard: threading.Lock`
  хранятся как module-level переменные в `order_manager.py`.
- `submit_signal` получает lock для своего тикера и удерживает его на всё время
  от CHECK до INSERT (критическая секция ~строки 283–369).
- Это полностью исключает race condition внутри одного процесса.

### Дополнительно: overlap-guard для scheduled_forecast
- `_run_task_loop` в `scheduler.py` запускает `_scheduled_forecast_task` даже если
  предыдущий запуск ещё выполняется. Добавлен флаг `_task_running` (per-task asyncio.Event)
  чтобы пропускать запуск, если предыдущий не завершён.

## План реализации
1. [x] `order_manager.py` — добавить `_ticker_locks` и `_ticker_locks_guard`, обернуть
       критическую секцию в `submit_signal` per-ticker Lock.
2. [x] `scheduler.py` — добавить overlap-guard (`_task_running` dict[str, bool]) в
       `_run_task_loop`, пропускать итерацию если задача ещё выполняется.

## Тесты
- Существующий `test_order_manager_duplicate_order` покрывает последовательный дубль.
- Новый тест `test_order_manager_concurrent_duplicate` запускает два потока одновременно
  и проверяет, что только один ордер вставлен в БД.

## Статус
Done
