# Reset Orders/Trades To Initial State

## Goal
Сбросить систему к состоянию "консенсусы созданы, ордера и сделки еще не созданы":
- закрыть активные ордера и позиции в IB;
- очистить в SQLite таблицы ордеров/сделок;
- очистить в consensus поля фактического исполнения и связи со сделками;
- не удалять consensus и forecast logs.

## Scope
- Новый CLI-скрипт: `scripts/tools/reset_trading_state.py`
- Новый BAT-скрипт: `reset_trading_state.bat`
- Новый метод в `scripts/core/sqlite_manager.py` для централизованного reset

## Safety
- По умолчанию выполняется полный reset (IB + DB).
- Поддерживается `--dry-run` для проверки без изменений.
- Поддерживаются режимы `--ib-only` и `--db-only`.
- Скрипт завершает работу с ненулевым кодом, если IB-операции не удалось выполнить полностью.

## DB Reset Details
Очищаются таблицы:
- `ib_order_transactions`
- `orders`
- `trades`

В `consensus` очищаются/сбрасываются поля:
- `trade_id` -> `NULL`
- `order_checked_at`, `order_attempted_at` -> `''`
- `entry_price_actual`, `target_hit`, `stop_hit`, `first_hit`, `exit_successful`, `direction_correct`, `pnl_pct`, `r_multiple` -> `NULL`
- `actual_date` -> `''`, `actual_open`, `actual_close`, `actual_high`, `actual_low` -> `NULL`
- `eval_status` -> `PENDING`
- `order_state` -> `PENDING_ORDER` для `LONG/SHORT`, иначе `ORDER_SKIPPED`
- `order_reason` -> `''` для `LONG/SHORT`, иначе `neutral_signal`

## Notes
- API сервера не меняется.
- Новые зависимости не добавляются.
