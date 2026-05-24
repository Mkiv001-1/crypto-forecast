# Интеграционные тесты

## Обзор

В проекте есть два типа интеграционных тестов:

1. **Тесты с моками** (API + Database) - используют временную SQLite БД и моки для внешних сервисов
2. **Тесты с реальным API** (Live Bybit) - делают реальные запросы к Bybit Demo API

## Запуск тестов

### Обычные тесты (с моками)

По умолчанию пропускают интеграционные тесты с реальным API:

```bash
# Все тесты кроме live-интеграционных
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_api_db.py scripts/tests/test_integration_server_api.py -v

# Только unit-тесты (по умолчанию)
.venv312\Scripts\python.exe -m pytest
```

### Live тесты с Bybit Demo API

Требуют переменных окружения:

```bash
# Windows PowerShell
$env:BYBIT_API_KEY="your_demo_api_key"
$env:BYBIT_API_SECRET="your_demo_api_secret"
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v -m integration

# Windows CMD
set BYBIT_API_KEY=your_demo_api_key
set BYBIT_API_SECRET=your_demo_api_secret
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v -m integration

# Или сразу
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v -m integration --override-ini="addopts="
```

## Файлы тестов

| Файл | Описание | Зависимости |
|------|----------|-------------|
| `test_integration_api_db.py` | API + SQLite тесты | Только временная БД |
| `test_integration_server_api.py` | Полное покрытие API endpoints | Только временная БД |
| `test_integration_live_bybit.py` | Live Bybit API тесты | BYBIT_API_KEY, BYBIT_API_SECRET |
| `test_integration_bybit_flow.py` | Bybit + DB flow (моки) | Временная БД |
| `test_integration_forecast_to_order.py` | Forecast-to-order flow (моки) | Временная БД |
| `test_integration_risk_management.py` | Risk management (моки) | Временная БД |

## Безопасность Live тестов

Тесты `test_integration_live_bybit.py` имеют следующие защиты:

1. **Только demo аккаунт** - проверяют `config.demo is True`
2. **Лимитные ордера далеко от рынка** - не исполнятся
3. **Минимальный размер** - 0.001 BTC (минимум для Bybit)
4. **Авто-отмена** - все тестовые ордера удаляются после теста
5. **Skip без ключей** - тесты пропускаются если нет env vars

## Что проверяют live тесты

### TestBybitConnectionLive
- Подключение к API
- Баланс кошелька
- Информация об аккаунте
- Синхронизация времени

### TestBybitMarketDataLive
- Тикеры BTCUSDT, ETHUSDT
- Свечи (klines) daily и hourly
- Список инструментов

### TestBybitPositionsLive
- Получение позиций
- Установка плеча (leverage)

### TestBybitOrdersLive
- Выставление лимитных ордеров
- Отмена ордеров
- TP/SL ордера
- Массовая отмена
- История ордеров

### TestBybitDataLoaderLive
- Data loader с реальным API

## Маркеры pytest

- `integration` - тесты с внешними сервисами
- `slow` - тесты > 5 секунд
- `skipif` - пропуск если нет creds

## Полный запуск всех интеграционных тестов

```bash
# С моками (всегда проходят)
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_api_db.py scripts/tests/test_integration_server_api.py -v

# С реальным API (требуют ключи)
$env:BYBIT_API_KEY="xxx"
$env:BYBIT_API_SECRET="yyy"
.venv312\Scripts\python.exe -m pytest scripts/tests/test_integration_live_bybit.py -v
```
