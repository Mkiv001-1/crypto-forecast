# Trade UID Lifecycle

## Статус
In Progress

## Цель
Ввести надежный сквозной идентификатор сделки и однозначный маппинг ордеров между локальной БД и IB.

## Решение
- Внутренний мастер-ключ: `trade_uid` (UUIDv4) на весь lifecycle bracket-сделки.
- Внешний correlation ключ в IB: `orderRef` с форматом `tid=<trade_uid>|oid=<order_id>|role=<role>`.
- Стабильный IB-ключ ордера: `ib_perm_id`.

## Strict Mode
Проект в разработке, поэтому legacy-совместимость не требуется.

Перед включением новых инвариантов выполняется одноразовый сброс данных в таблицах:
- `orders`
- `trades`
- `ib_order_transactions`
- `ib_gateway_log`

## Изменения схемы
- `trades.trade_uid` TEXT
- `orders.trade_uid` TEXT
- `orders.ib_perm_id` INTEGER
- `ib_order_transactions.trade_uid` TEXT
- `ib_order_transactions.ib_perm_id` INTEGER

Индексы:
- `idx_trades_trade_uid`
- `idx_orders_trade_uid`
- `idx_orders_ib_perm_id`
- `idx_ib_tx_trade_uid`
- `idx_ib_tx_ib_perm_id`

## Правила записи
1. `trade_uid` генерируется один раз в `submit_signal`.
2. Все 3 ордера bracket получают одинаковый `trade_uid`.
3. В `orderRef` всегда передаются `trade_uid + order_id + role`.
4. Все события в `ib_order_transactions` пишутся с `trade_uid` и (когда доступен) `ib_perm_id`.

## Правила синхронизации
Матчинг статусов из IB выполняется по приоритету:
1. `(ib_order_id, ib_perm_id)`
2. `(ib_order_id, trade_uid из orderRef)`
3. Иначе ошибка маппинга (без fallback на legacy)

## API Change Warning
Изменяются контракты ответов (backward-incompatible для старых клиентов без сброса):
- `/orders`
- `/trades`
- `/ib-transactions`

Новые поля: `trade_uid`, `ib_perm_id`.

## Тестирование
- Unit: генерация и распространение `trade_uid` в submit.
- Unit: парсинг `orderRef` в sync.
- Unit: строгий матчинг по приоритету ключей.
- Integration: один lifecycle от submit до close сохраняет одинаковый `trade_uid` во всех таблицах.
