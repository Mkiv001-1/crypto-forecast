# Интеграция выставления ордеров (авто + ручной)

Двухрежимная система инициации ордеров: автоматическая после генерации консенсуса и ручная через API.

---

## Статус

**Done**

---

## Описание

Система поддерживает два способа выставления bracket-ордеров:

1. **Автоматический режим** — ордер выставляется сразу после успешного расчёта консенсуса при выполнении условий
2. **Ручной режим** — ордер выставляется по запросу через API endpoint

Оба режима проходят одинаковые проверки: валидацию консенсуса, расчёт позиции, проверку капитала, execute-флаги.

---

## Архитектура

### Компоненты

```
forecast_runner.py:104-121  Автоматическая инициация после save_consensus()
api.py:997-1121          Ручная инициация через POST /orders/submit
sqlite_manager.py:853-864  Метод get_latest_forecast_log_id()
shared/models.py:307-322   Pydantic модели OrderSubmitRequest/Response
```

### Поток данных

**Автоматический:**
```
process_ticker()
  → calculate_consensus()
  → save_consensus()
  → [если AUTO_ORDER_SUBMISSION=true и signal=LONG/SHORT и confidence≥55%]
    → get_capital()
    → calculate_position()
    → get_latest_forecast_log_id()
    → submit_signal()
```

**Ручной:**
```
POST /orders/submit
  → Получить последний consensus для тикера
  → Валидация: signal LONG/SHORT, confidence ≥55%
  → [опционально] override параметры из запроса
  → get_capital()
  → Получить текущую цену из price_data
  → calculate_position()
  → [опционально] override quantity
  → get_latest_forecast_log_id()
  → submit_signal()
  → OrderSubmitResponse
```

---

## Конфигурация

| Ключ | Значение | Описание |
|------|----------|----------|
| `AUTO_ORDER_SUBMISSION` | `true` / `false` (default) | Включает автоматическое выставление ордеров |

---

## API

### POST /orders/submit

Ручное выставление ордера на основе последнего консенсуса.

**Request:**
```json
{
  "ticker": "AAPL",
  "entry_limit_price": 150.0,  // optional override
  "stop_loss": 145.0,          // optional override
  "target_price": 160.0,       // optional override
  "quantity": 10               // optional override
}
```

**Response:**
```json
{
  "status": "SUBMITTED",           // или SKIPPED_*, ERROR
  "order_ids": [123, 124, 125],
  "message": "Bracket order placed",
  "consensus_signal": "LONG",
  "confidence": 75.5
}
```

**Статусы ответа:**
- `SUBMITTED` — ордер успешно выставлен
- `SKIPPED_NEUTRAL` — сигнал NEUTRAL, не LONG/SHORT
- `SKIPPED_LOW_CONFIDENCE` — confidence < 55%
- `SKIPPED_MISSING_LEVELS` — отсутствуют stop_loss или target_price
- `SKIPPED_NO_CAPITAL` — ошибка получения капитала
- `ORDER_MODE=disabled` / `ORDER_MODE=paper` — режим блокировки
- `INVALID_POSITION` / `INSUFFICIENT_CAPITAL` — ошибка расчёта позиции
- `SKIPPED_TICKER_BLOCKED` / `SKIPPED_DUPLICATE` / `SKIPPED_MAX_ORDERS` — гарды order_manager
- `SKIPPED_EXECUTE_DISABLED` — execute=off у метода или провайдера

---

## Условия выставления ордера

Общие для обоих режимов:

1. **ORDER_MODE ≠ disabled** — глобальный выключатель в config
2. **Сигнал LONG или SHORT** — NEUTRAL игнорируется
3. **Confidence ≥ CONFIDENCE_THRESHOLD** — минимальный порог уверенности (по умолчанию 55%, константа в `config.py`)
4. **Наличие уровней** — stop_loss и target_price обязательны
5. **Капитал OK** — успешный ответ от capital_provider
6. **Позиция валидна** — quantity > 0, статус OK от position_sizer
7. **Execute-флаги** — все методы и провайдеры из консенсуса имеют execute='yes'
8. **Гарды order_manager** — не заблокирован, не дубль, не превышен лимит

---

## Тесты

```python
test_sqlite_manager_get_latest_forecast_log_id     # Метод получения log_id
test_auto_order_submission_skipped_when_disabled   # Проверка AUTO_ORDER_SUBMISSION
test_manual_order_submit_validation_neutral        # Отказ NEUTRAL
test_manual_order_submit_validation_low_confidence # Отказ low confidence
```

---

## Реализованные изменения

### sqlite_manager.py
- Добавлен `get_latest_forecast_log_id(ticker)` — возвращает ID последнего прогноза для связи ордера с логом

### forecast_runner.py
- Интеграция автоматического режима в `process_ticker()` после `save_consensus()`
- Проверка `AUTO_ORDER_SUBMISSION=true`, валидация сигнала, расчёт позиции, вызов `submit_signal()`

### api.py
- Импорт `OrderSubmitRequest`, `OrderSubmitResponse` из `shared/models`
- Новый endpoint `POST /orders/submit` с полной валидацией и override параметрами

### shared/models.py
- `OrderSubmitRequest` — Pydantic модель запроса с опциональными override
- `OrderSubmitResponse` — Pydantic модель ответа со статусом и order_ids

### test_core_logic.py
- 4 новых теста для проверки обоих режимов

---

## Безопасность

- Автоматический режим по умолчанию **выключен** (требует `AUTO_ORDER_SUBMISSION=true`)
- Ручной режим требует API key
- Оба режима подчиняются `ORDER_MODE` (disabled/paper/live)
- Работают execute-флаги методов и провайдеров
- Все гарды `order_manager.submit_signal()` активны

---

## Зависимости

- `order_manager.py` — `submit_signal()`
- `position_sizer.py` — `calculate_position()`
- `capital_provider.py` — `get_capital()`
- `consensus.py` — данные консенсуса
- `sqlite_manager.py` — `get_latest_forecast_log_id()`

---

## Примечания

- Для ручного режима цена entry берётся из `price_data.close` последней записи (не из консенсуса)
- `quantity` в ручном режиме можно override; если не указано — рассчитывается автоматически
- `log_id` используется для связи ордера с прогнозом в таблице `orders.forecast_log_id`
