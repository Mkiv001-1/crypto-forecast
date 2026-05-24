# Bybit Setup Guide — Crypto Forecast Trading Robot

Руководство по настройке торгового робота для работы с Bybit (Demo/Live).

---

## Demo, Live и Testnet — что использует проект

| Режим | Сайт | API endpoint | Используется? |
|-------|------|--------------|---------------|
| **Demo Trading** | [bybit.com](https://www.bybit.com) → переключатель **Demo Trading** | `https://api-demo.bybit.com` | **Да** (по умолчанию, `BYBIT_DEMO=true`) |
| **Live** | [bybit.com](https://www.bybit.com) → **Live Trading** | `https://api.bybit.com` | Да (`BYBIT_DEMO=false`) |
| **Testnet** | testnet.bybit.com | `https://api-testnet.bybit.com` | **Нет, никогда** |

**Важно:**

- **Demo** — это виртуальный счёт **на основном сайте bybit.com**, раздел API Management → **Demo Trading**. Ключи создаются там же, где live, но в режиме Demo.
- **Testnet** (отдельный сайт testnet.bybit.com) **проектом не поддерживается и не нужен**. Ключи с testnet не подойдут.
- Для paper-торговли и тестов робота: `BYBIT_DEMO=true`, `ORDER_MODE=paper`, ключи только из **Demo Trading** на bybit.com.
- pybit получает `demo=True` и `testnet=False` — запросы идут на `api-demo.bybit.com`, не на testnet.

---

## Быстрый старт

1. Создать API Key в Bybit (Demo или Live)
2. Обновить конфигурацию в БД
3. Запустить миграцию БД
4. Настроить тикеры (криптовалюты)
5. Запустить сервер

---

## 1. Создание API Key

### Demo Account (рекомендуется для начала)

Ключи берутся **только с bybit.com**, режим **Demo Trading** — не с testnet.bybit.com.

1. Зайдите на [bybit.com](https://www.bybit.com) и авторизуйтесь
2. Перейдите в **Settings** → **API Management**
3. В верхнем переключателе выберите **Demo Trading** (не Live и не Testnet)
4. Нажмите **Create New Key**
5. Настройки:
   - **API Key Type**: System-generated
   - **Permissions**: 
     - ✅ Read (чтение)
     - ✅ Orders (торговля)
     - ✅ Positions (позиции)
   - **IP Restriction**: включите и добавьте свой IP (рекомендуется)
6. Сохраните **API Key** и **API Secret** (показывается только один раз!)

### Live Account

Те же шаги, но выберите **Live Trading** в переключателе.

⚠️ **ВНИМАНИЕ**: Live торговля использует реальные деньги!

---

## 2. Конфигурация

### Через SQLite БД

```sql
-- В таблице config установите:
UPDATE config SET value = 'your_api_key' WHERE key = 'BYBIT_API_KEY';
UPDATE config SET value = 'your_api_secret' WHERE key = 'BYBIT_API_SECRET';
UPDATE config SET value = 'true' WHERE key = 'BYBIT_DEMO';  -- или 'false' для live
UPDATE config SET value = 'paper' WHERE key = 'ORDER_MODE';  -- 'disabled', 'paper', 'live'
```

### Через Environment Variables

```bash
set BYBIT_API_KEY=your_api_key
set BYBIT_API_SECRET=your_api_secret
set BYBIT_DEMO=true
set ORDER_MODE=paper
```

### Рекомендуемые начальные настройки

| Key | Значение | Описание |
|-----|----------|----------|
| `BYBIT_API_KEY` | ваш ключ | API Key |
| `BYBIT_API_SECRET` | ваш секрет | API Secret |
| `BYBIT_DEMO` | `true` | Demo на bybit.com (`api-demo.bybit.com`), не testnet |
| `BYBIT_DEFAULT_LEVERAGE` | `3` | Плечо 3x |
| `BYBIT_MAX_LEVERAGE` | `10` | Макс плечо 10x |
| `MAX_RISK_PER_TRADE_PCT` | `1.0` | Риск 1% на сделку |
| `MAX_POSITION_PCT` | `10.0` | Макс 10% капитала в позицию |
| `MAX_OPEN_POSITIONS` | `5` | Макс 5 позиций |
| `ORDER_MODE` | `paper` | Режим торговли |
| `DATA_SOURCE` | `bybit` | Источник данных |
| `DEFAULT_INTERVAL` | `60` | Таймфрейм 1H |

---

## 3. Миграция БД

Запустите миграцию для добавления Bybit-полей:

```bash
# Автоматически найдет database/trading_robot.db
python -m scripts.core.bybit_migrate

# Или с указанием пути
python -m scripts.core.bybit_migrate D:\Git\crypto-forecast\database\trading_robot.db
```

---

## 4. Настройка тикеров (криптовалют)

Добавьте криптовалюты в таблицу `settings`:

```sql
-- Примеры криптовалют
INSERT INTO settings (ticker, active, trading_blocked, symbol, leverage) VALUES
('BTCUSDT', 1, 0, 'BTCUSDT', 3),
('ETHUSDT', 1, 0, 'ETHUSDT', 3),
('SOLUSDT', 1, 0, 'SOLUSDT', 3),
('XRPUSDT', 1, 0, 'XRPUSDT', 3);
```

### Популярные линейные перпетуалы на Bybit

| Символ | Описание | Рекомендуемое плечо |
|--------|----------|---------------------|
| BTCUSDT | Bitcoin | 3-5x |
| ETHUSDT | Ethereum | 3-5x |
| SOLUSDT | Solana | 3-5x |
| XRPUSDT | Ripple | 3-5x |
| DOGEUSDT | Dogecoin | 2-3x |
| ADAUSDT | Cardano | 3x |
| AVAXUSDT | Avalanche | 3x |
| LINKUSDT | Chainlink | 3x |
| LTCUSDT | Litecoin | 3x |
| DOTUSDT | Polkadot | 3x |

---

## 5. Запуск сервера

```bash
# Убедитесь что зависимости установлены
pip install -r requirements_server.txt

# Запуск сервера
cd scripts\server
python main.py

# Или через batch файл (если настроен)
run_server.bat
```

---

## Проверка подключения

После запуска сервера проверьте логи:

```
INFO bybit_worker: connected to Bybit (demo)
INFO bybit_worker: task created
INFO Bybit worker started
```

API endpoint для проверки:
```
GET http://localhost:8000/bybit/status
```

---

## Режимы торговли

### disabled (безопасный режим)
- Ордера не размещаются
- Рекомендуется при первой настройке

### paper (demo)
- Использует **Demo Trading** на bybit.com (`BYBIT_DEMO=true`)
- Виртуальные деньги на demo-счёте (не рискуете live-балансом)
- Полностью функциональный тест; testnet не требуется

### live
- ⚠️ Использует реальные деньги
- Требует `LIVE_TRADING_CONFIRMED=true`
- Требует `BYBIT_DEMO=false`

---

## Устранение неполадок

### HTTP 401 на wallet-balance

1. Ключи должны быть созданы в **Demo Trading** на bybit.com, если `BYBIT_DEMO=true`.
2. Ключи с **testnet.bybit.com** не работают — проект их не использует.
3. Ключи из **Live Trading** не работают при `BYBIT_DEMO=true` (нужен demo-ключ или `BYBIT_DEMO=false` для live).
4. После смены ключей или `BYBIT_DEMO` перезапустите сервер.

### "Bybit worker startup failed"

1. Проверьте API Key и Secret:
   ```python
   from scripts.core.bybit_config import load_bybit_config
   config = load_bybit_config(db_manager)
   print(f"API Key: {config.api_key[:8]}...")
   ```

2. Проверьте соединение вручную:
   ```python
   from scripts.core.bybit_client import BybitClient
   client = BybitClient(api_key, api_secret, demo=True)
   print(client.test_connection())
   ```

### "bybit_err:connection_failed"

1. Проверьте интернет-соединение
2. Проверьте IP whitelist в настройках API
3. Попробуйте пересоздать API Key

### "Max open positions reached"

- Увеличьте `MAX_OPEN_POSITIONS` в конфиге
- Или закройте часть позиций

### "Slippage check failed"

- Рыночная цена слишком далеко от сигнала
- Увеличьте `ENTRY_SLIPPAGE_TOLERANCE` (например до 1.0)
- Или используйте Market ордера (set `DEFAULT_ORDER_TYPE=Market`)

---

## Дополнительно

### WebSocket данные в реальном времени

```python
from scripts.core.bybit_ws_client import create_ws_client

async def main():
    client = await create_ws_client(
        api_key="your_key",
        api_secret="your_secret",
        symbols=["BTCUSDT", "ETHUSDT"]
    )
    # Данные будут приходить в логи

asyncio.run(main())
```

### Получение исторических данных

```python
from scripts.core.bybit_data_loader import fetch_bybit_daily

data = fetch_bybit_daily("BTCUSDT", days=90)
print(f"Loaded {len(data)} candles")
```

---

## Ссылки

- [Bybit API Docs](https://bybit-exchange.github.io/docs/)
- [Bybit Demo Trading (V5)](https://bybit-exchange.github.io/docs/v5/demo)
- [pybit SDK](https://github.com/bybit-exchange/pybit)
- Основной сайт: [bybit.com](https://www.bybit.com) (Demo и Live)
- **Не используется:** [testnet.bybit.com](https://testnet.bybit.com) — отдельная песочница, для этого робота не нужна
