# Аудит архитектуры очередей: прогнозы -> консенсус -> ордера -> обновления ордеров

Дата: 2026-05-13

## 1. Что проверялось

Проверена фактическая очередность этапов и точки синхронизации:
- генерация прогнозов;
- формирование консенсуса;
- активация/выставление ордеров;
- обновление статусов ордеров из IB.

Фокус: консенсус должен запускаться только после завершения прогнозов (или остановки по таймауту), а ордера - только после готового консенсуса.

## 2. Фактическая архитектура очередей

## 2.1 Прогнозы -> консенсус (внутри одного тикера)

Фактический поток в orchestration:
1. Для тикера вызывается генерация всех прогнозов.
2. Консенсус считается только после завершения генерации и только если есть хотя бы один forecast.
3. Сохраненный консенсус для LONG/SHORT переводится в состояние `PENDING_ORDER`.

Доказательства:
- вызов генерации: [scripts/core/forecast_runner.py](scripts/core/forecast_runner.py#L57)
- консенсус только при `if raw_forecasts`: [scripts/core/forecast_runner.py](scripts/core/forecast_runner.py#L63)
- `save_consensus` и постановка LONG/SHORT в `PENDING_ORDER`: [scripts/core/consensus.py](scripts/core/consensus.py#L416), [scripts/core/consensus.py](scripts/core/consensus.py#L494)

## 2.2 Очередь активации ордеров

Используется DB-backed очередь через `consensus.order_state='PENDING_ORDER'`.

Потребитель очереди:
- scheduler-задача `process_pending_orders` периодически читает pending-консенсусы и вызывает активацию.

Доказательства:
- выборка pending: [scripts/core/sqlite_manager.py](scripts/core/sqlite_manager.py#L803), [scripts/core/sqlite_manager.py](scripts/core/sqlite_manager.py#L812)
- регистрация scheduler-задачи: [scripts/core/scheduler.py](scripts/core/scheduler.py#L611)
- конкурентное наличие forecast и pending-процессинга: [scripts/core/scheduler.py](scripts/core/scheduler.py#L615)

## 2.3 Выставление ордера только после консенсуса

Нормальный автоматический путь:
- `activate_consensus_order` берет запись `consensus`, проверяет TTL/окно/капитал/position sizing и только затем вызывает `submit_signal`.

Доказательства:
- точка входа: [scripts/core/order_manager.py](scripts/core/order_manager.py#L1240)
- TTL: [scripts/core/order_manager.py](scripts/core/order_manager.py#L1296)
- окно времени: [scripts/core/order_manager.py](scripts/core/order_manager.py#L1310)

## 2.4 Очередь обновления статусов ордеров

Отдельный канал синхронизации с IB:
- scheduler-задача `sync_order_statuses`;
- ручной API `/orders/sync`.

Доказательства:
- scheduler-задача sync: [scripts/core/scheduler.py](scripts/core/scheduler.py#L612)
- manual endpoint: [scripts/server/api.py](scripts/server/api.py#L1340)

## 3. Проверка требований

## 3.1 Требование: консенсус после прогнозов или их таймаута

Итог: частично выполняется.

- Плюс: консенсус действительно вызывается только после возврата из генерации прогнозов для тикера.
- Минус: нет явного общего дедлайна этапа прогнозов (per-ticker/per-run). Есть только сетевой timeout на один HTTP-запрос и retry.

Критичный нюанс:
- при `429` используется `retry_after` и `time.sleep(wait)` без верхнего лимита на весь этап, плюс цикл последовательный, не параллельный.

Доказательства:
- последовательные циклы моделей/методов: [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L66), [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L71)
- sleep по rate-limit: [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L188)
- timeout/retry на запрос: [scripts/core/ai_client.py](scripts/core/ai_client.py#L84), [scripts/core/ai_client.py](scripts/core/ai_client.py#L52)

## 3.2 Требование: ордера только после готового консенсуса

Итог: в основном выполняется, но есть обходной путь.

- Нормальный auto-flow: да, ордера идут через `activate_consensus_order` из `consensus`.
- Обход: ручной endpoint `/orders/submit` берет "последний consensus по ticker" и вызывает `submit_signal` напрямую, минуя TTL/window/order_state-проверки `activate_consensus_order`.

Доказательства:
- endpoint: [scripts/server/api.py](scripts/server/api.py#L1381)
- выбор latest consensus: [scripts/server/api.py](scripts/server/api.py#L1391)
- прямой `submit_signal`: [scripts/server/api.py](scripts/server/api.py#L1481)

## 4. Найденные ошибки и риски

## CRITICAL-1: Нет bounded timeout этапа прогнозов (нарушение ожидания "отработали или остановились по таймауту")

Симптом:
- генерация может затягиваться неопределенно долго из-за последовательной обработки и неограниченного `retry_after` sleep.

Последствие:
- консенсус может не запускаться в ожидаемом SLA-окне.

Файлы:
- [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L66)
- [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L188)
- [scripts/core/ai_client.py](scripts/core/ai_client.py#L84)

## HIGH-2: При полном провале прогнозов консенсус не создается вообще

Симптом:
- в `forecast_runner` блок консенсуса обернут в `if raw_forecasts`, иначе запись в `consensus` не появляется.

Последствие:
- нет явной фиксации состояния "consensus skipped/failed" для тикера, труднее мониторинг очередности и пост-анализ.

Файлы:
- [scripts/core/forecast_runner.py](scripts/core/forecast_runner.py#L63)

## HIGH-3: Ручной `/orders/submit` обходит guard'ы активации консенсуса

Симптом:
- endpoint не использует `activate_consensus_order`, а вызывает `submit_signal` напрямую.

Последствие:
- можно выставить ордер по устаревшему/вне окна/логически пропущенному консенсусу.

Файлы:
- [scripts/server/api.py](scripts/server/api.py#L1381)
- [scripts/server/api.py](scripts/server/api.py#L1391)
- [scripts/server/api.py](scripts/server/api.py#L1481)

## MEDIUM-4: Отсутствует межзадачная зависимость scheduler (только per-task overlap guard)

Симптом:
- overlap guard защищает только от повторного запуска той же задачи, но не задает зависимости между `scheduled_forecast`, `process_pending_orders`, `sync_order_statuses`.

Последствие:
- конкурентные окна работы задач могут создавать гонки состояния (частично гасится защитами от дубликатов в order_manager, но причинно-следственная очередность между задачами не гарантирована).

Файлы:
- [scripts/core/scheduler.py](scripts/core/scheduler.py#L205)
- [scripts/core/scheduler.py](scripts/core/scheduler.py#L607)
- [scripts/core/scheduler.py](scripts/core/scheduler.py#L611)
- [scripts/core/scheduler.py](scripts/core/scheduler.py#L615)

## MEDIUM-5: `max_duration_sec` задач пишется как метаданные, но не применяется как runtime-cancel

Симптом:
- в scheduler сохраняется `max_duration_sec`, но в `_run_task_loop` нет логики прерывания задачи при превышении.

Последствие:
- зависшие операции не обрываются автоматически по лимиту задачи.

Файлы:
- [scripts/core/scheduler.py](scripts/core/scheduler.py#L625)

## 5. Дополнительное наблюдение по документации

В архитектурной документации указано, что `multi_model_forecaster` работает через `asyncio.gather()` и семафор, но текущая реализация фактически последовательная.

Доказательства:
- doc: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#L178)
- code: [scripts/core/multi_model_forecaster.py](scripts/core/multi_model_forecaster.py#L66)

## 6. Короткий вывод

- Базовая логика pipeline соблюдается: ордера в auto-flow идут после готового консенсуса.
- Главная проблема по вашему критерию - нет жестко ограниченного таймаутом завершения стадии прогнозов на уровне тикера/рана.
- Есть важный обходной ручной путь `/orders/submit`, который может нарушать требуемую дисциплину очередности guard'ов.
- Правки кода не вносились, только аудит и фиксация выводов.
