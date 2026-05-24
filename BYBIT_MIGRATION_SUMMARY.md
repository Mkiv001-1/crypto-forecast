# Bybit Migration Summary

Сводка по миграции Forecast Trading Robot с Interactive Brokers на Bybit.

**Окружения:** робот использует **Demo Trading** и **Live** на [bybit.com](https://www.bybit.com). **Testnet** (testnet.bybit.com) **не используется**. При `BYBIT_DEMO=true` API: `https://api-demo.bybit.com`. Подробности: [docs/BYBIT_SETUP.md](docs/BYBIT_SETUP.md).

---

## Созданные файлы

### Core модули Bybit

| Файл | Описание |
|------|----------|
| `scripts/core/bybit_client.py` | REST API клиент для Bybit (Linear Perpetual) |
| `scripts/core/bybit_ws_client.py` | WebSocket клиент для real-time данных |
| `scripts/core/bybit_data_loader.py` | Загрузка исторических данных через Bybit API |
| `scripts/core/bybit_config.py` | Конфигурация и настройки Bybit |
| `scripts/core/bybit_worker.py` | Worker pattern (аналог ib_worker) |
| `scripts/core/bybit_order_manager.py` | Менеджер ордеров для Bybit |
| `scripts/core/bybit_order_status_sync.py` | Синхронизация статусов ордеров (аналог order_status_sync) |
| `scripts/core/bybit_capital_provider.py` | Источник капитала из Bybit (замена IB capital_provider) |
| `scripts/core/bybit_migrate.py` | Миграция базы данных |

### Документация и тесты

| Файл | Описание |
|------|----------|
| `docs/BYBIT_SETUP.md` | Руководство по настройке Bybit |
| `test_bybit.py` | Тест подключения к Bybit |
| `BYBIT_MIGRATION_SUMMARY.md` | Этот файл |

### Обновленные файлы

| Файл | Изменения |
|------|-----------|
| `requirements_server.txt` | Добавлен pybit и websockets, убран ib_insync |
| `scripts/server/api.py` | Заменен ib_worker на bybit_worker в lifespan |
| `scripts/core/scheduler.py` | Заменен ib_worker на bybit_worker в heartbeat |

---

## Архитектура изменений

### Было (IB):
```
┌─────────────────┐
│   IB Gateway    │
│   (TWS/IBG)     │
└────────┬────────┘
         │
┌────────▼────────┐
│  ib_worker.py   │
│  (ib_insync)    │
└────────┬────────┘
         │
┌────────▼────────┐
│ order_manager.py│
└─────────────────┘
```

### Стало (Bybit):
```
┌─────────────────┐
│   Bybit API     │
│  (api.bybit.com)│
└────────┬────────┘
         │
┌────────▼────────┐
│  bybit_worker.py│
│    (pybit)      │
└────────┬────────┘
         │
┌────────▼────────┐
│bybit_order_mgr.py│
└─────────────────┘
```

---

## Ключевые изменения

### 1. Exchange Integration
- **Убрано**: IB Gateway, ib_worker.py, ib_gateway_client.py
- **Добавлено**: Bybit REST API + WebSocket через pybit

### 2. Data Sources
- **Было**: yfinance + Alpha Vantage для исторических данных
- **Стало**: Bybit API как primary source для всего

### 3. Trading Features
- **Было**: Акции, рыночные часы 9:30-16:00 EST
- **Стало**: Crypto perpetuals, 24/7 торговля, плечо 1-100x

### 4. Order Types
- **Было**: Bracket orders через IB
- **Стало**: Limit/Market с attached TP/SL через Bybit

### 5. Symbol Format
- **Было**: `NASDAQ:AAPL`, `NYSE:MSFT`
- **Стало**: `BTCUSDT`, `ETHUSDT`

### 6. Default Tickers (исправлено)
- `sqlite_manager.py` — `_DEFAULT_SETTINGS` теперь BTCUSDT, ETHUSDT, SOLUSDT
- `data_manager.py` — начальные данные теперь криптовалюты
- `forecast_runner.py` — дефолтный тикер `BTCUSDT` (был `NASDAQ:NVDA`)
- `data_loader.py` — комментарии обновлены
- `order_manager.py` — комментарии обновлены
- `notification_manager.py` — пример обновлен
- `alpha_vantage_loader.py` — комментарии обновлены
- `finnhub_loader.py` — комментарии обновлены

### 7. IB Transactions → Bybit Transactions
- **Новые таблицы**: `bybit_order_transactions`, `bybit_gateway_log`
- **Новые поля**: `bybit_ok` в `heartbeat_log`
- **Функция**: `_log_bybit_transaction()` в `bybit_order_manager.py`
- **Старые таблицы**: `ib_order_transactions`, `ib_gateway_log` (оставлены для истории)

### 8. Capital Provider
- **Было**: `capital_provider.py` — получал капитал из IB Gateway
- **Стало**: `bybit_capital_provider.py` — получает USDT баланс из Bybit API

### 9. Order Status Sync
- **Было**: `order_status_sync.py` — синхронизация с IB Gateway
- **Стало**: `bybit_order_status_sync.py` — синхронизация с Bybit API

---

## Шаги для завершения миграции

### 1. Установить зависимости
```bash
cd d:\Git\crypto-forecast
pip install -r requirements_server.txt
```

### 2. Получить API Key
- Зайти на bybit.com
- Settings → API Management
- Создать ключ для Demo торговли
- Сохранить API Key и Secret

### 3. Настроить переменные окружения
```bash
set BYBIT_API_KEY=your_api_key_here
set BYBIT_API_SECRET=your_api_secret_here
set BYBIT_DEMO=true
set ORDER_MODE=disabled
```

### 4. Протестировать подключение
```bash
python test_bybit.py
```

### 5. Выполнить миграцию БД
```bash
python -m scripts.core.bybit_migrate
```

### 6. Настроить криптовалюты в БД
```sql
-- Добавить в settings
INSERT INTO settings (ticker, active, trading_blocked, symbol, leverage) VALUES
('BTCUSDT', 1, 0, 'BTCUSDT', 3),
('ETHUSDT', 1, 0, 'ETHUSDT', 3);
```

### 7. Запустить сервер
```bash
cd scripts\server
python main.py
```

### 8. Проверить работу
- Открыть http://localhost:8000/docs
- Проверить эндпоинт `/bybit/status`
- Убедиться что данные приходят

### 9. Включить торговлю (когда готовы)
```bash
set ORDER_MODE=paper  # или live (осторожно!)
```

---

## Риски и предостережения

### ⚠️ Важно!
1. **Всегда начинайте с DEMO**
2. **Никогда не используйте live сразу**
3. **Проверьте все настройки перед live**
4. **Используйте небольшое плечо (2-3x) в начале**

### По сравнению с акциями:
- Крипто более волатильна (±10% за день норма)
- Плечо увеличивает прибыль И убытки
- 24/7 торговля = больше возможностей и рисков
- Без защиты от разрывов гэпов (gap protection)

---

## TODO для дальнейшей разработки

### Приоритет: Высокий
- [ ] Добавить эндпоинты Bybit в API (аналоги IB эндпоинтов)
- [ ] Адаптировать position_sizer.py под Bybit контракты
- [ ] Обновить UI клиента для криптовалют
- [ ] Добавить тесты для Bybit модулей

### Приоритет: Средний
- [ ] WebSocket интеграция в scheduler
- [ ] Автоматическая установка плеча для новых символов
- [ ] Улучшенная обработка отклоненных ордеров
- [ ] Funding rate индикатор

### Приоритет: Низкий
- [ ] Поддержка Spot торговли
- [ ] Поддержка Inverse perpetuals
- [ ] Grid trading стратегии
- [ ] Мультисчетная торговля

---

## Структура конфигурации

### Обязательные переменные окружения
```bash
BYBIT_API_KEY=          # API Key из Bybit
BYBIT_API_SECRET=       # API Secret из Bybit
BYBIT_DEMO=true         # true = demo, false = live
ORDER_MODE=disabled     # disabled/paper/live
```

### Опциональные переменные
```bash
BYBIT_DEFAULT_LEVERAGE=3
BYBIT_MAX_LEVERAGE=10
MAX_RISK_PER_TRADE_PCT=1.0
MAX_POSITION_PCT=10.0
MAX_OPEN_POSITIONS=5
DEFAULT_ORDER_TYPE=Limit
DATA_SOURCE=bybit
```

---

## Полезные команды

```bash
# Тест подключения
python test_bybit.py

# Тест с размещением ордера (demo only)
python test_bybit.py --order

# Миграция БД
python -m scripts.core.bybit_migrate

# Запуск сервера
python -m scripts.server.main

# Проверка логов
tail -f trading_robot.log
```

---

## Ссылки

- [Bybit API Docs](https://bybit-exchange.github.io/docs/)
- [pybit SDK](https://github.com/bybit-exchange/pybit)
- [Bybit Demo Trading](https://www.bybit.com/en-US/trade/demo/)

---

## Вопросы и поддержка

При возникновении проблем:
1. Проверьте `trading_robot.log`
2. Запустите `python test_bybit.py`
3. Проверьте API Key в настройках Bybit
4. Убедитесь что IP разрешен в whitelist
