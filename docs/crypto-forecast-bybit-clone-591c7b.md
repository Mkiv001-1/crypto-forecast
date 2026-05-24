v# План: Клон Forecast Trading Robot для Bybit (Crypto)

Создать полную копию проекта forecast, адаптированную для криптовалютной торговли на бирже Bybit в `d:\Git\crypto-forecast`.

---

## Основные изменения для Bybit адаптации

### 1. Exchange Integration
- **Удалить**: `ib_worker.py`, `capital_provider.py` (IB Gateway интеграция)
- **Создать**: `bybit_client.py` — REST API клиент для Bybit
- **Создать**: `bybit_ws_client.py` — WebSocket клиент для real-time данных
- **Конфигурация**: API Key/Secret для Bybit (вместо IB Gateway host/port)

### 2. Data Sources
- **Заменить**: `data_loader.py` — использовать Bybit API для исторических данных
- **Символы**: формат `BTCUSDT`, `ETHUSDT` (вместо AAPL, MSFT)

### 3. Order Management
- **Заменить**: `order_manager.py` — адаптировать под Bybit order types
- **Убрать**: логику рыночных часов (крипта 24/7)
- **Адаптировать**: position sizing под контракты (qty в Bybit)

### 4. Risk Management
- **Обновить**: дефолтные параметры риска для крипты (более высокая волатильность)
- **Убрать**: EXTENDED_HOURS, PRE_MARKET логику, sector exposure limits

### 5. Database Schema
- **Адаптировать**: поле `ticker` → поддержка крипто-символов
- **Заменить**: IB-поля (ib_order_id) → Bybit-поля (bybit_order_id)

### 6. AI/Forecast Engine
- **Сохранить**: существующую логику прогнозирования через OpenRouter
- **Адаптировать**: промпты под криптовалюты (24/7 торговля)

---

## Этапы реализации

1. **Базовая структура** — скопировать проект, удалить IB-файлы
2. **Bybit Integration** — создать клиенты REST/WebSocket, order manager
3. **Data & Forecast** — адаптировать загрузку данных, индикаторы
4. **Server & API** — обновить endpoints, конфигурации
5. **Testing** — тестирование на Bybit Testnet

---

## Технические детали Bybit API

- **Библиотека**: `pybit` (официальная Python SDK)
- **Testnet**: доступен для тестирования
- **Аутентификация**: API Key + API Secret + Timestamp подпись

---

## Новые конфигурационные параметры

```ini
[bybit]
api_key = your_api_key
api_secret = your_api_secret
testnet = true
default_category = linear  ; linear, spot, inverse

[risk]
max_risk_per_trade_pct = 1.0
max_position_pct = 10.0
leverage = 3
```
