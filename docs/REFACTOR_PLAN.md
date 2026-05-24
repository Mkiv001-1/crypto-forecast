# План рефакторинга (статус)

Живой чеклист. Исходный план: [archives/REFACTOR_PLAN.md](archives/REFACTOR_PLAN.md).

## Выполнено

- **Фаза 0:** импорт `activate_consensus_order`, дубликаты `position_sizer_*`, `market_context`, pytest markers.
- **Фаза 1:** `scripts/bootstrap.py`, `PYTHONPATH` в bat, `AppContext`, lifespan DI.
- **Фаза 2:** `scripts/core/storage/` (forecast/consensus/orders repos); `SQLiteManager` остаётся фасадом.
- **Фаза 3:** `scripts/core/pipeline/`, тонкий `process_ticker()`.
- **Фаза 4:** тонкий `api.py`; доменные роутеры `routers/orders.py`, `forecast.py`, `scheduler_routes.py` + `routers/endpoints.py` для остального; `orders_service` для `POST /orders/submit`.
- **Фаза A (runtime):** расширен `bybit_migrate` (`side`, `entry_price`, SL/TP, …); submit через `bybit_capital_provider` + `bybit_order_manager`; клиент `get_bybit_transactions`; GUI колонка Bybit Order ID; убран noop `order_timeout_check`; fix `position_sizer` except.
- **Фаза B (частично):** IB tools в `scripts/tools/_archive/ib/`; deprecated `log_ib_transaction` / `get_ib_transactions`; `get_broker_transactions()`; `BYBIT_CAPITAL_FAILSAFE`.
- **Фаза C (инкремент):** `scripts/client/tabs/` (24 модуля), `TradingTab` вынесен; `window_run_activity` в `activity_runtime.py`.
- **Фаза D (опционально, CLI):** `migrate.py --drop-ib-legacy`; scheduler `_await_blocking` (`run_in_executor` / `to_thread`).
- **Фаза 7:** `conftest.py`, `requirements-dev.txt`, `pyproject.toml`.

## В работе / следующие PR

- Дальнейший перенос вкладок из `gui_main.py` (импорт из `tabs/` вместо дублирования классов).
- Роутеры `portfolio.py`, `config_routes.py` (остальной объём `endpoints.py`).
- Сужение публичного API `SQLiteManager` до repos-only.

## Опционально

- `DROP ib_*` на prod только после бэкапа `trading_robot.db`.
- APScheduler вместо самописного loop (фаза 8).

## Критерий «рефакторинг завершён»

- Нет runtime-зависимости от IB Gateway в `core` / `server` / `client`.
- Торговые пути: `bybit_worker` + `bybit_order_manager`.
- Схема `orders` согласована с Bybit sync; scheduler sync без SQL-ошибок.
- `gui_main.py` — тонкая оболочка + `client/tabs/*`.
- Этот файл отражает фактическое состояние.
