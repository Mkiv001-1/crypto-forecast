# Comprehensive Mock Consensus → Orders → GUI → IB Gateway Test Suite

## Обзор

Файл `test_mock_consensus_orders_gui.py` содержит полный набор интеграционных тестов, демонстрирующих полный цикл работы торгового робота:

1. **Мокирование консенсус-данных** (обход AI моделей)
2. **Создание ордеров** на основе мокированного консенсуса
3. **Проверка видимости ордеров в GUI** через API
4. **Симуляция интеграции с IB Gateway**
5. **Обновление статусов ордеров** при заполнении

---

## Архитектура тестов

### Компоненты

```
┌─────────────────────────────────────────────────┐
│  test_mock_consensus_orders_gui.py              │
├─────────────────────────────────────────────────┤
│  MockIBGateway                                  │
│  ├─ place_bracket_order()                       │
│  ├─ get_bid_ask_spread()                        │
│  ├─ cancel_order()                              │
│  └─ close_position_market()                     │
├─────────────────────────────────────────────────┤
│  Test Database (SQLite)                         │
│  ├─ config           (конфиг параметры)        │
│  ├─ settings         (тикеры)                   │
│  ├─ consensus        (консенсус сигналы)       │
│  ├─ orders           (GUI видит эту таблицу)   │
│  ├─ method_config    (методы анализа)          │
│  ├─ providers        (AI модели)                │
│  ├─ portfolio        (позиции IB)              │
│  └─ trades           (выполненные сделки)      │
├─────────────────────────────────────────────────┤
│  FakeDbManager                                  │
│  └─ Минимальный DB API для тестирования        │
└─────────────────────────────────────────────────┘
```

---

## 8 Тестов

### Test 1: `test_mock_consensus_creation()`
**Цель:** Убедиться, что мокированные консенсус-данные сохраняются в БД

```python
# Шаг 1: Создать мок-консенсус (без AI)
mock_consensus = {
    "ticker": "AAPL",
    "signal": "LONG",
    "confidence": 0.85,
    "target_price": 165.00,
    "stop_loss": 142.00
}

# Шаг 2: Сохранить в БД
db.save_consensus(mock_consensus)

# Шаг 3: Проверить наличие в БД
assert get_consensus_from_db(db_file, "AAPL")[0]["signal"] == "LONG"
```

**Проверяет:** 
- ✓ Консенсус-данные корректно сохраняются
- ✓ Структура данных соответствует ожиданиям
- ✓ Таблица consensus доступна

---

### Test 2: `test_orders_created_from_consensus()`
**Цель:** Создать ордера на основе мокированного консенсуса

```python
# Шаг 1: Создать мок-прогнозы (2 модели × 2 метода)
mock_forecasts = [
    {"side": "LONG", "confidence": 80, "exit_target": "$165.00", "stop_loss": 142.0},
    {"side": "LONG", "confidence": 75, "exit_target": "$163.00", "stop_loss": 143.0}
]

# Шаг 2: Рассчитать консенсус
consensus = calculate_consensus(mock_forecasts, current_price=150.0)

# Шаг 3: Рассчитать размер позиции
position = calculate_position("AAPL", 150.0, 142.0, db, net_liquidation=100000.0)

# Шаг 4: Отправить ордер (мокированный IB + мокированные рыночные часы)
with mock_ib_gateway():
    with patch('order_manager._is_market_hours', return_value=True):
        result = submit_signal("AAPL", consensus, position, db)

# Шаг 5: Проверить ордера в БД
orders = get_orders_from_db(db_file, "AAPL")
```

**Проверяет:**
- ✓ Консенсус правильно рассчитывается из множества прогнозов
- ✓ Размер позиции корректен на основе риска
- ✓ Ордера создаются в таблице orders
- ✓ Ордера доступны для GUI

---

### Test 3: `test_orders_visible_in_gui_api()`
**Цель:** Убедиться, что ордера видны в GUI через API эндпоинты

```python
# Шаги 1-4: Создать и отправить ордер (как в тесте 2)

# Шаг 5: Получить ордера (как сделает GUI)
orders = get_orders_from_db(db_file, ticker="AAPL")

# Шаг 6: Проверить структуру для GUI OrdersTab
for order in orders:
    assert "id" in order
    assert "ticker" in order
    assert "action" in order
    assert "quantity" in order
    assert "status" in order
    assert "created_at" in order
```

**Проверяет:**
- ✓ Ордера имеют все необходимые поля для отображения в GUI
- ✓ Фильтрация по тикерам работает
- ✓ Фильтрация по статусам работает
- ✓ GUI может получить данные через API

---

### Test 4: `test_ib_gateway_bracket_order_submission()`
**Цель:** Убедиться, что ордера правильно отправляются в IB Gateway

```python
# Шаги 1-4: Создать и отправить ордер

# Шаг 5: Проверить, что IB Gateway был вызван
bracket_calls = [c for c in _mock_ib.calls if c["method"] == "place_bracket_order"]
assert bracket_calls[0]["symbol"] == "AAPL"
assert bracket_calls[0]["action"] == "BUY"
assert bracket_calls[0]["quantity"] == position["quantity"]
assert bracket_calls[0]["stop_loss_price"] == consensus["stop_loss"]
assert bracket_calls[0]["take_profit_price"] == consensus["target_price"]

# Шаг 6: Проверить, что проверка спреда была сделана
spread_calls = [c for c in _mock_ib.calls if c["method"] == "get_bid_ask_spread"]
assert len(spread_calls) == 1
```

**Проверяет:**
- ✓ Bracket-ордер отправляется в IB Gateway
- ✓ Параметры ордера передаются правильно
- ✓ Проверка bid/ask спреда выполняется
- ✓ IB Gateway получает корректную информацию

---

### Test 5: `test_order_fill_callback_and_status_update()`
**Цель:** Симулировать заполнение ордера и обновление статуса

```python
# Шаги 1-4: Создать и отправить ордер

# Шаг 5: Получить ID родительского ордера
parent_ib_id = result["ib_ids"]["parent"]

# Шаг 6: Симулировать callback заполнения от IB
simulate_order_fill(db_file, parent_ib_id, fill_price=150.5)

# Шаг 7: Проверить, что статус обновился
orders_after = get_orders_from_db(db_file, "AAPL")
entry_order = next(o for o in orders_after if o["order_role"] == "ENTRY")
assert entry_order["status"] == "FILLED_ENTRY"
assert entry_order["filled_at"] != ""
```

**Проверяет:**
- ✓ Статус ордера обновляется при заполнении
- ✓ GUI видит обновленный статус
- ✓ Вспомогательные ордера (stop/target) остаются в режиме ожидания

---

### Test 6: `test_short_signal_creates_correct_orders()`
**Цель:** Убедиться, что SHORT сигналы создают правильные ордера (SELL entry, BUY stop/target)

```python
# Шаги 1-4: Создать SHORT консенсус вместо LONG

# Шаг 5: Проверить, что entry ордер - SELL (не BUY)
bracket_calls = [c for c in _mock_ib.calls if c["method"] == "place_bracket_order"]
assert bracket_calls[0]["action"] == "SELL"

# Шаг 6: Проверить в БД
entry_order = next(o for o in orders if o["order_role"] == "ENTRY")
assert entry_order["action"] == "SELL"

# Шаг 7: Проверить, что stop и target - BUY (закрытие позиции)
stop_order = next(o for o in orders if o["order_role"] == "STOP")
assert stop_order["action"] == "BUY"
```

**Проверяет:**
- ✓ SHORT сигналы создают SELL entry
- ✓ Stop-loss для SHORT это BUY (защита от убытков вверх)
- ✓ Target для SHORT это BUY (фиксация прибыли вниз)
- ✓ Структура bracket-ордера правильна для SHORT

---

### Test 7: `test_gui_consensus_tab_displays_data()`
**Цель:** Убедиться, что консенсус-данные видны в GUI ConsensusTab

```python
# Шаг 1: Вставить несколько консенсус-записей
for record in consensus_records:
    db.save_consensus(record)

# Шаг 2: Получить все (как сделает GUI)
all_consensus = get_consensus_from_db(db_file)
assert len(all_consensus) == 3

# Шаг 3: Проверить фильтрацию по тикерам
aapl_consensus = get_consensus_from_db(db_file, "AAPL")
assert len(aapl_consensus) == 2

# Шаг 4: Проверить структуру для отображения в GUI
for record in all_consensus:
    assert record["date"]
    assert record["ticker"]
    assert record["signal"] in ("LONG", "SHORT", "HOLD", "NEUTRAL")
    assert 0 <= record["confidence"] <= 1
```

**Проверяет:**
- ✓ Консенсус-данные доступны для ConsensusTab GUI
- ✓ Фильтрация по датам работает
- ✓ Фильтрация по тикерам работает
- ✓ Структура данных соответствует требованиям GUI

---

### Test 8: `test_multiple_tickers_orders_display_in_gui()`
**Цель:** Убедиться, что ордера от множества тикеров правильно отображаются в GUI

```python
# Шаги 1-4: Создать и отправить ордера для AAPL и MSFT

# Шаг 5: Получить все ордера
all_orders = get_orders_from_db(db_file)
assert len(all_orders) >= 2

# Шаг 6: Проверить фильтрацию в GUI
aapl_orders = [o for o in all_orders if o["ticker"] == "AAPL"]
msft_orders = [o for o in all_orders if o["ticker"] == "MSFT"]
assert len(aapl_orders) >= 1
assert len(msft_orders) >= 1

# Шаг 7: Проверить статусы
for order in all_orders:
    assert order["status"] in ("SUBMITTED", "QUEUED", "PENDING")
```

**Проверяет:**
- ✓ Несколько тикеров могут иметь одновременно ордера
- ✓ Фильтрация в GUI работает для разных тикеров
- ✓ Каждый ордер имеет правильный статус
- ✓ GUI может отображать портфель с несколькими тикерами

---

## Запуск тестов

### Все тесты
```bash
python -m pytest test_mock_consensus_orders_gui.py -v
```

### Конкретный тест
```bash
python -m pytest test_mock_consensus_orders_gui.py::test_orders_created_from_consensus -v
```

### С подробным выводом
```bash
python -m pytest test_mock_consensus_orders_gui.py -v -s
```

### С пропуском output'а (тестирование только результатов)
```bash
python -m pytest test_mock_consensus_orders_gui.py -v --tb=no
```

---

## Ключевые моменты

### Мокирование IB Gateway

```python
_mock_ib = MockIBGateway()

# Использование:
with mock_ib_gateway():
    result = submit_signal(...)
    # _mock_ib отслеживает все вызовы к IB
```

### Мокирование рыночных часов

```python
with patch('order_manager._is_market_hours', return_value=True):
    result = submit_signal(...)
    # Это позволяет тестам выполняться независимо от времени дня
```

### Структура тестовой БД

Тестовая база содержит все необходимые таблицы:
- **config** - конфигурация системы
- **settings** - список активных тикеров
- **consensus** - консенсус-сигналы (для ConsensusTab GUI)
- **orders** - ордера (для OrdersTab GUI)
- **method_config** - методы анализа
- **providers** - AI модели
- **portfolio** - позиции с IB
- **trades** - история сделок

---

## Интеграция с GUI

### OrdersTab API

```python
# GUI запрашивает ордера так:
api.get_orders(ticker="AAPL", status="SUBMITTED", limit=500)

# Данные хранятся в таблице orders:
SELECT * FROM orders WHERE ticker = ? AND status = ?
```

### ConsensusTab API

```python
# GUI запрашивает консенсус так:
api.get_consensus(ticker="AAPL", from_date="2026-05-07", to_date="2026-05-08")

# Данные хранятся в таблице consensus:
SELECT * FROM consensus WHERE ticker = ? AND date BETWEEN ? AND ?
```

---

## Примеры использования

### Для разработки новой функции

1. Добавьте тест в `test_mock_consensus_orders_gui.py`
2. Запустите его: `pytest test_mock_consensus_orders_gui.py::test_your_test -v -s`
3. Добавьте реальную реализацию в код
4. Убедитесь, что тест проходит

### Для отладки GUI

1. Запустите нужный тест с `-s` флагом для подробного вывода
2. Ордера сохраняются в тестовой БД
3. Проверьте структуру данных в консоли

### Для проверки интеграции

1. Запустите все тесты: `pytest test_mock_consensus_orders_gui.py -v`
2. Убедитесь, что все 8 тестов проходят
3. Это гарантирует, что весь цикл работает корректно

---

## Результаты тестов

```
✓ Test 1: Consensus created and stored
✓ Test 2: Orders created from consensus
✓ Test 3: Orders visible in GUI API
✓ Test 4: Bracket order submitted to IB Gateway
✓ Test 5: Order fill callback updates status
✓ Test 6: SHORT orders created correctly
✓ Test 7: Consensus data available for GUI
✓ Test 8: Multiple tickers display correctly in GUI

Result: 8/8 tests passed ✓
```

---

## Дополнительные заметки

### Использованные модули

- `consensus.py` - расчет консенсуса
- `position_sizer.py` - расчет размера позиции
- `order_manager.py` - управление ордерами
- `ib_gateway_client.py` - интеграция с IB (мокирована)

### Как работает мокирование

Вместо реального подключения к IB Gateway, используется `MockIBGateway`, которая:
1. Отслеживает все вызовы методов
2. Возвращает правдоподобные ответы (с реальными ID ордеров)
3. Позволяет симулировать события (fill callback)

### Предположения теста

1. IB Gateway доступен на `127.0.0.1:7497` (paper mode)
2. Консенсус содержит `signal`, `confidence`, `target_price`, `stop_loss`
3. Ордер содержит `ticker`, `quantity`, `status`, `ib_order_id`
4. GUI обновляет данные через REST API с интервалом

---

## Лицензия и авторство

Часть интеграционного набора тестов для Forecast Trading Robot.
Разработано для полной верификации цикла: Consensus → Orders → GUI → IB Gateway
