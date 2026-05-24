# IB Live Position/Order Status API

## Статус
In Progress

## Цель
Добавить API-команды для детальной работы с Interactive Brokers:
- получить live-статус конкретной позиции по `con_id`
- получить live-статус конкретного ордера по `ib_order_id`

Также устранить расхождение после sync, когда в локальной таблице `Portfolio` остаются устаревшие позиции при пустом портфеле в IB.

## Scope
- `scripts/core/ib_gateway_client.py`
  - новый helper: `fetch_ib_position_status_by_con_id`
  - новый helper: `fetch_ib_order_status_by_order_id`
  - fix: очищать `Portfolio` перед upsert в `sync_portfolio_with_ib`
- `scripts/server/api.py`
  - `GET /ib/positions/{con_id}/status`
  - `GET /ib/orders/{ib_order_id}/status`
- `scripts/client/api_client.py`
  - `get_ib_position_status(...)`
  - `get_ib_order_status(...)`
- `scripts/tests/test_integration_api.py`
  - детерминированные тесты новых endpoint-ов через `TestClient` и monkeypatch

## API Contract

### GET /ib/positions/{con_id}/status
Query params:
- `host` (default `127.0.0.1`)
- `port` (default `7497`)
- `client_id` (default `1`)

Response (пример):
```json
{
  "found": true,
  "con_id": 76792991,
  "status": "OPEN",
  "position": {
    "symbol": "TSLA",
    "account": "DU7093209",
    "quantity": 20.0,
    "avg_cost": 420.55,
    "market_price": 419.5,
    "market_value": 8390.0,
    "unrealized_pnl": -21.0,
    "realized_pnl": 0.0,
    "currency": "USD",
    "exchange": "NASDAQ",
    "updated_at": "2026-05-11T17:11:24.921000"
  }
}
```

Если позиция не найдена:
```json
{
  "found": false,
  "con_id": 76792991,
  "status": "FLAT",
  "position": null
}
```

### GET /ib/orders/{ib_order_id}/status
Query params:
- `host` (default `127.0.0.1`)
- `port` (default `7497`)
- `client_id` (default `14`)

Response (пример):
```json
{
  "found": true,
  "ib_order_id": 12345,
  "status": "Submitted",
  "source": "openTrades",
  "order": {
    "ib_order_id": 12345,
    "perm_id": 670162540,
    "symbol": "TSLA",
    "account": "DU7093209",
    "action": "BUY",
    "order_type": "MKT",
    "total_qty": 20.0,
    "filled_qty": 0.0,
    "remaining_qty": 20.0,
    "avg_fill_price": 0.0,
    "last_fill_price": 0.0,
    "last_update": "2026-05-11T17:11:25.050000"
  }
}
```

Fallback:
- если ордер не найден в `openTrades`, используется `executions`
- если есть executions для `order_id`, возвращается статус `Filled` и `source=executions`

## Изменение API
Добавляются **новые endpoint-ы**. Existing contract не ломается.

## Тестирование
- API integration tests с monkeypatch на core helper-ы
- deterministic ответы без живого IB подключения

## Риски
- Live endpoint-ы зависят от доступности IB Gateway и корректного `client_id`.
- Для завершенных ордеров детализация ограничена тем, что возвращает `executions` в текущей сессии.
