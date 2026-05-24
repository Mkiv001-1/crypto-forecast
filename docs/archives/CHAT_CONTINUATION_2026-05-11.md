# Продолжение работы в новом чате (2026-05-11)

## Цель
Довести до конца внедрение сквозной идентификации торгового жизненного цикла:
- trade_uid как главный lifecycle ID
- ib_perm_id как стабильный broker ID
- orderRef с метаданными tid/oid для надежной корреляции

## Что уже сделано
- Подготовлена спецификация: docs/features/trade-uid-lifecycle.md.
- Обновлены схема/миграции в SQLiteManager:
  - новые поля в orders, trades, ib_order_transactions
  - миграционная логика для отсутствующих колонок
  - индексы под новые ключи сопоставления
- Обновлен submit path:
  - генерация trade_uid при submit_signal
  - передача trade_uid и ib_perm_id в логи транзакций
  - запись orderRef в формате tid=<trade_uid>|oid=<parent_db_id>
- Обновлен IB-клиент:
  - возврат/проброс ib_perm_id и order_ref из статуса
  - для bracket leg добавлены role suffix в orderRef
  - возврат parent/target/stop perm_id после постановки
- Обновлен sync слой IB->DB:
  - парсинг orderRef
  - приоритетный матчинг:
    1) ib_order_id + ib_perm_id
    2) ib_order_id + trade_uid
    3) fallback по ib_order_id (если метаданные отсутствуют, для legacy)
  - логирование статусов с trade_uid и ib_perm_id
  - schema-aware SQL для совместимости старых фикстур

## Что проверено
- Целевые core-тесты проходили локально:
  - scripts/tests/test_ib_order_sync.py
  - scripts/tests/test_core_logic.py
- В последнем состоянии также проходил API integration:
  - scripts/tests/test_integration_api.py -q

## Актуализация статуса (2026-05-11, продолжение)
- UI-экспозиция новых полей уже реализована в Trading-вкладках:
  - Orders: отображаются Trade UID и IB Perm ID
  - Trades: отображается Trade UID
  - IB Transactions: отображаются Trade UID и IB Perm ID
- API compatibility по форме ответов соблюдена:
  - /orders -> items
  - /ib-transactions -> items
  - /trades -> items и дублирующий trades (additive-compatible)
- Интеграционные проверки на новые поля и shape ответов присутствуют в scripts/tests/test_integration_api.py.

## Что осталось сделать (следующий шаг)
1. Добить финальную валидацию на рабочей БД (если включен интеграционный флаг):
   - FORECAST_ALLOW_WORKING_DB_TEST=1
   - scripts/tests/test_working_db_trading_tab_visibility.py -q
2. Выполнить короткий ручной smoke-check в GUI Trading tab:
   - видимость колонок Trade UID / IB Perm ID
   - корректный переход Orders <-> Trades по parent
3. Подготовить итоговый changelog/PR summary по lifecycle ID (trade_uid + ib_perm_id + orderRef).

## Важные ограничения
- Не менять веса консенсуса/EMA без отдельного обсуждения.
- Не трогать напрямую критичные файлы без необходимости:
  - scripts/core/forecast_runner.py
  - scripts/core/consensus.py
  - scripts/core/order_manager.py (только точечно и осознанно)
- Не делать изменения SQLite schema/data вне стандартной миграционной логики.

## Быстрый старт для нового чата
Скопировать этот файл как контекст и дать задачу:
"Сфокусируйся на финальной валидации: рабочая БД интеграционный тест, короткий GUI smoke-check, затем подготовь финальный PR summary по trade_uid/ib_perm_id/orderRef."

## Рекомендуемый минимальный прогон после правок
- ./.venv312/Scripts/python.exe -m pytest scripts/tests/test_integration_api.py -q
- ./.venv312/Scripts/python.exe -m pytest scripts/tests/test_working_db_trading_tab_visibility.py -q
- c:/git/forecast/.venv/Scripts/python.exe -m pytest scripts/tests/test_core_logic.py -k "max_open_orders or count_open_orders or preview_consensus_order_missing_levels_is_safe"

## Служебная заметка
Если в новом чате нужно восстановить максимально полный контекст, можно сослаться на разговорный summary из текущей сессии и этот файл как актуальный handoff.