# Синхронизация статусов ордеров: ручной запуск из Trading UI

Кнопка в верхней строке вкладки Trading запускает ручную синхронизацию статусов ордеров с IB и отображает время последней успешной синхронизации.

---

## Статус

**In Progress**

---

## Описание

Добавляется пользовательский поток:

1. Пользователь нажимает `Sync Orders` в верхней строке вкладки Trading
2. Клиент вызывает серверный endpoint `POST /orders/sync`
3. Сервер запрашивает текущие статусы open/recent orders из IB
4. Сервер обновляет локальные таблицы `orders` и `trades`
5. UI обновляет таблицы Orders/Trades и надпись `Last sync time`

Цель: убрать ручной разрыв между фактическими статусами в IB и отображением в интерфейсе.

---

## Архитектура

### Компоненты

```
client/gui_main.py      TradingTab top bar + кнопка Sync Orders + label Last sync time
client/api_client.py    Метод sync_orders()
server/api.py           Endpoint POST /orders/sync
core/order_status_sync.py  Логика применения статусов IB к orders/trades
core/ib_gateway_client.py  Источник статусов через fetch_open_order_statuses()
```

### Поток данных

```
TradingTab._on_sync_orders()
  -> ForecastApiClient.sync_orders()
  -> POST /orders/sync
  -> order_status_sync.sync_orders_with_ib()
      -> fetch_open_order_statuses()
      -> apply status transitions to orders/trades
  -> response {ok, scanned, updated_orders, updated_trades, errors, synced_at}
  -> TradingTab.refresh Orders/Trades + update Last sync time
```

---

## API

### POST /orders/sync

Ручной запуск синхронизации статусов ордеров из IB в локальную БД.

**Request params (optional):**
- `host` (default `127.0.0.1`)
- `port` (default зависит от `ORDER_MODE`)
- `client_id` (default `14`)

**Response (пример):**

```json
{
  "ok": true,
  "scanned": 6,
  "updated_orders": 2,
  "updated_trades": 1,
  "errors": [],
  "synced_at": "2026-05-11T19:22:10.123456+00:00"
}
```

**Ошибки:**
- При сбое IB endpoint возвращает `ok=false` и диагностику в `errors`.

---

## Правила перехода статусов

### orders
- `Filled` + `ENTRY` -> `FILLED_ENTRY`
- `Filled` + `TAKE_PROFIT`/`STOP_LOSS` -> `FILLED`
- `Cancelled` -> `CANCELLED`
- `Inactive` -> `REJECTED` (дефолт для первой итерации)
- `Submitted`/`PreSubmitted` -> `SUBMITTED`

### trades
- Fill `ENTRY` -> обновить `entry_price`, `entry_filled_at`, оставить `status=OPEN`
- Fill `TAKE_PROFIT` -> `status=CLOSED`, `close_reason=TAKE_PROFIT`, расчет `realized_pnl`
- Fill `STOP_LOSS` -> `status=CLOSED`, `close_reason=STOP_LOSS`, расчет `realized_pnl`

---

## UI поведение

- Кнопка находится в верхней строке вкладки Trading (над саб-вкладками Orders/Trades)
- Во время sync:
  - кнопка disabled
  - текст: `Syncing...`
- После success:
  - кнопка enabled
  - текст: `Sync Orders`
  - обновляется `Last sync time: YYYY-MM-DD HH:MM:SS`
  - перезагружаются таблицы Orders и Trades
- После error:
  - кнопка enabled
  - текст: `Sync Orders`
  - показывается сообщение об ошибке
  - `Last sync time` не изменяется

---

## Тесты

Планируемые проверки:

1. Unit: применение IB статусов к `orders`
2. Unit: закрытие `trades` при fill target/stop
3. API: `POST /orders/sync` success path
4. API: `POST /orders/sync` failure path
5. GUI smoke: нажатие `Sync Orders` обновляет таблицы и label

---

## Ограничения

- Без новых внешних зависимостей
- Без переписывания `order_manager.py`
- Явная обработка ошибок
- Детеминированные тесты
