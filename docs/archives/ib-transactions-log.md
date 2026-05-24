# IB Transactions Log

## Goal

Добавить нормализованный журнал реальных транзакций с IB для:

- записи отправки ордеров и ответа от IB;
- записи обновлений статусов ордеров из ручного sync и scheduler sync;
- трассировки через связи с `orders`, `trades`, `consensus`, `logs`.

## API Change Warning

Вводится новый read endpoint: `GET /ib-transactions`.

Это расширение API (backward-compatible): существующий `GET /ib-log` сохраняется.

## Data Model

Новая таблица: `ib_order_transactions`.

Поля:

- `id` INTEGER PK AUTOINCREMENT
- `occurred_at` TEXT NOT NULL
- `event_source` TEXT NOT NULL
- `event_type` TEXT NOT NULL
- `operation_status` TEXT DEFAULT ''
- `status_before` TEXT DEFAULT ''
- `status_after` TEXT DEFAULT ''
- `ticker` TEXT DEFAULT ''
- `ib_order_id` INTEGER DEFAULT 0
- `ib_parent_id` INTEGER DEFAULT 0
- `order_id` INTEGER REFERENCES orders(id)
- `trade_id` INTEGER REFERENCES trades(id)
- `consensus_id` INTEGER REFERENCES consensus(id)
- `log_id` TEXT REFERENCES logs(id)
- `request_payload_json` TEXT DEFAULT ''
- `response_payload_json` TEXT DEFAULT ''
- `error_message` TEXT DEFAULT ''
- `latency_ms` INTEGER DEFAULT NULL

Индексы:

- `idx_ib_tx_occurred` on `occurred_at`
- `idx_ib_tx_ticker` on `ticker`
- `idx_ib_tx_ib_order` on `ib_order_id`
- `idx_ib_tx_ib_parent` on `ib_parent_id`
- `idx_ib_tx_source` on `event_source`
- `idx_ib_tx_order_id` on `order_id`
- `idx_ib_tx_trade_id` on `trade_id`

## Event Semantics

### submit flow

- `ORDER_SUBMIT_REQUEST`
  - source: `submit_manual` или `submit_auto`
  - содержит request payload, связи (`order_id`, `consensus_id`, `log_id`)
- `ORDER_SUBMIT_RESPONSE`
  - source: `submit_manual` или `submit_auto`
  - содержит response payload и `latency_ms`
  - `operation_status`: `SUCCESS` | `FAILED`

### sync flow

- `ORDER_STATUS_UPDATE`
  - source: `sync_manual` или `sync_scheduler`
  - содержит `status_before` -> `status_after`
  - содержит snapshot IB status в `response_payload_json`

## UI Scope (Trading tab)

Новая под-вкладка: `IB transactions`.

Показывает только новую таблицу `ib_order_transactions`.

Функциональность (phase 1):

- фильтры: ticker, source, event type;
- refresh;
- табличный просмотр ключевых колонок.

Без CSV export и без отдельной панели JSON в этом этапе.

## Non-goals

- удаление `ib_gateway_log`;
- изменение торговой логики/весов;
- изменение существующего поведения `orders` и `trades` кроме аудита.
