# Architecture & Technical Decisions

Живой документ. Обновляется при каждом значимом архитектурном решении.
Цель: дать следующей сессии контекст «почему так, а не иначе».

---

## Общая архитектура

```
Client (PyQt6 GUI)
    │  HTTP / REST
    ▼
Server (FastAPI, port 8000)
    │
    ├── scripts/core/              ← бизнес-логика
    │   ├── forecast_runner.py     ← главный цикл (оркестратор)
    │   ├── scheduler.py            ← централизованный планировщик + heartbeat
    │   ├── forecast_engine.py     ← промпты → OpenRouter → R/R валидация
    │   ├── multi_model_forecaster.py ← запуск N моделей × M методов
    │   ├── consensus.py           ← медианная агрегация + фильтр аномалий
    │   ├── consensus_evaluator.py ← оценка консенсуса постфактум
    │   ├── consensus_recalc.py    ← ретроспективный пересчет консенсуса
    │   ├── market_regime.py       ← ADX + MA → режим рынка
    │   ├── market_context.py      ← макро-контекст (SPY, VIX)
    │   ├── indicators.py          ← технические индикаторы
    │   ├── data_loader.py         ← yfinance / Alpha Vantage / Finnhub
    │   ├── smart_data_loader.py   ← умный выбор источника данных
    │   ├── sqlite_manager.py      ← ORM-обёртка над SQLite (WAL + WriteQueue)
    │   ├── unified_logs_manager.py ← управление таблицей logs
    │   ├── actuals_evaluator.py   ← оценка по High/Low + приоритет стопа
    │   ├── capital_provider.py    ← источник капитала из IB
    │   ├── position_sizer.py      ← расчет позиции от NetLiquidation
    │   ├── order_manager.py       ← bracket-ордера + атомарность + execute-флаги
    │   ├── ib_gateway_client.py   ← IB Gateway: позиции + балансы + спред
    │   ├── circuit_breaker.py     ← защита от сбоев OpenRouter
    │   ├── model_performance_tracker.py ← EMA-веса моделей
    │   ├── ai_client.py           ← клиент OpenRouter (HTTP + retry)
    │   ├── providers_manager.py   ← управление AI-провайдерами
    │   ├── prompt_manager.py      ← управление промпт-шаблонами
    │   ├── data_manager.py        ← абстракция над хранилищем данных
    │   ├── notification_manager.py ← уведомления (MANUAL_INTERVENTION_REQUIRED)
    │   ├── single_instance.py     ← PID-защита от дублирования процессов
    │   ├── migrate.py             ← миграции схемы SQLite
    │   ├── config.py              ← legacy-константы (fallback)
    │   ├── alpha_vantage_loader.py ← загрузчик Alpha Vantage
    │   └── finnhub_loader.py      ← загрузчик Finnhub
    │
    │   scripts/server/            ← FastAPI + фоновые задачи
    │   ├── api.py                 ← REST эндпоинты
    │   ├── robot.py               ← фоновый runner (thread wrapper)
    │   ├── config.py              ← server_config.ini парсер
    │   └── main.py                ← точка входа (uvicorn)
    │
    │   scripts/client/            ← PyQt6 GUI
    │   ├── gui_main.py            ← главное окно + вкладки
    │   ├── api_client.py          ← HTTP-клиент для API
    │   ├── config.py              ← client_config.ini парсер
    │   └── main.py                ← точка входа (QApplication)
    │
    │   scripts/shared/            ← общие модели
    │   └── models.py              ← Pydantic модели для API
    │
    └── trading_robot.db       ← SQLite (единое хранилище)
```

---

## Ключевые решения

### SQLite вместо Excel
**Решение:** основное хранилище — `trading_robot.db` (SQLite), Excel используется только для экспорта/отчётов.  
**Причина:** Excel не поддерживает параллельный доступ; SQLite надёжнее при фоновых запусках сервера.

### OpenRouter как единая точка доступа к AI
**Решение:** все AI-запросы идут через OpenRouter (`openai`-совместимый API).  
**Причина:** позволяет переключать модели (Claude, GPT-4, Gemini, DeepSeek и др.) без изменения кода.  
**Конфиг:** ключ хранится в таблице `config` (ключ `OPENROUTER_API_KEY`), не в `.env`.

### Мульти-модельный подход (N моделей × M методов)
**Решение:** `multi_model_forecaster.py` запускает каждый метод анализа на каждой активной AI-модели.  
**Методы:** `momentum_trend`, `price_action`, `relative_strength`, `volatility`, `mean_reversion`, `volume_breakout`.  
**Консенсус:** взвешенная агрегация в `consensus.py`, результат в таблице `consensus`.

### Детекция рыночного режима
**Решение:** `market_regime.py` определяет режим по ADX + выравниванию MA → выбирает подмножество методов.  
**Режимы:** `STRONG_UPTREND`, `STRONG_DOWNTREND`, `WEAK_TREND`, `RANGING`.

### Оценка прогнозов (статусы записей logs)
**Решение:** записи в `logs` имеют статус `NEW` → после оценки становятся `EVALUATED`.  
**Логика:** `actuals_evaluator.py` берёт записи `NEW` старше 3 часов, загружает фактические цены, считает PnL и точность направления.

### IB Gateway интеграция
**Решение:** `ib_gateway_client.py` — sync-обёртка над `ib_insync` для получения позиций и балансов из Interactive Brokers.  
**Подключение:** IB Gateway (localhost:7497 для paper, :7496 для live) по протоколу TWS API.  
**Функции:**
- `fetch_ib_accounts()` — балансы счетов (NetLiquidation, BuyingPower, AvailableFunds)
- `fetch_ib_positions()` — позиции портфеля (quantity, avg_cost, market_value, unrealized_pnl)
- `test_ib_connection()` — диагностика подключения с детальными логами
- Асинхронные обёртки для FastAPI (`*_async`) с изоляцией event loop через threads

**Хранение:** таблицы `accounts` и `portfolio` в SQLite, поле `type` = 'paper' или 'live'.  
**GUI:** вкладка "IB" для теста подключения и ручной синхронизации.

### Prompt Templates
**Решение:** шаблоны промптов хранятся в таблице `prompt_templates` (SQLite), редактируются через API.  
**Дефолты:** `_DEFAULT_PROMPT_TEMPLATES` в `sqlite_manager.py`.

---

## Таблицы SQLite

| Таблица | Назначение |
|---|---|
| `settings` | Тикеры (ticker, active, comment, sector, trading_blocked) |
| `price_data` | Исторические OHLCV (250 дней) |
| `price_data_intraday` | Часовые бары (ticker, datetime, interval, OHLCV) |
| `indicators` | Рассчитанные техиндикаторы |
| `logs` | Все прогнозы + оценки (статус NEW/EVALUATED, bracket-поля, run_id) |
| `consensus` | Агрегированные консенсус-прогнозы + поля оценки |
| `config` | Параметры конфигурации (ключи AI, настройки) |
| `providers` | Настройки AI-провайдеров (ema_accuracy, execute) |
| `prompts` | Сохранённые промпты |
| `model_catalog` | Каталог моделей OpenRouter |
| `prompt_templates` | Шаблоны промптов по методам |
| `accounts` | Счета IB (broker, account_id, балансы, тип paper/live) |
| `portfolio` | Позиции IB (ticker, quantity, avg_cost, market_value, unrealized PnL, asset_type) |
| `ib_order_types` | Типы ордеров IB (order_type_code, name, tif_supported, active) |
| `ib_gateway_log` | Лог операций IB Gateway |
| `orders` | Ордера: Entry, Take Profit, Stop Loss; полный жизненный цикл |
| `trades` | Закрытые трейды (ticker, signal, entry/exit, realized_pnl, r_multiple) |
| `tickets` | Тикеты/задачи (ticker, action, quantity, price, status) |
| `scheduled_tasks` | Реестр задач планировщика |
| `method_config` | Параметры методов: timeframe_hours, trigger, active, execute |
| `heartbeat_log` | Служебные записи для проверки SQLite |
| `forecast_runs` | Аудит запусков прогнозирования |
| `forecast_run_links` | Связь прогнозов с весами |

> **Примечание:** часть колонок (`settings.sector`, `providers.ema_accuracy`, `consensus.eval_*`, `logs.stop_loss` и др.) добавляются через `migrate.py`, а не в базовой схеме. Таблица `ib_config` упоминается в API, но CREATE TABLE для неё не создан — используйте `/ib-config` endpoints.

---

## REST API (FastAPI, порт 8000)

Аутентификация: заголовок `X-API-Key`.  
Ключевые группы эндпоинтов: `/run/*`, `/logs`, `/indicators`, `/consensus`, `/tickers`, `/providers`, `/config`, `/prompt-templates`, `/prompts`, `/ib-config`, `/accounts`, `/portfolio`, `/orders`, `/trades`, `/tickets`, `/scheduler`, `/method-config`, `/heartbeat`, `/circuit-breaker`, `/capital`, `/model-catalog`, `/forecast-runs`.

---

## Бизнес-логика

### Основной рабочий цикл

```
1. Загрузка тикеров → 2. Получение данных → 3. Расчёт индикаторов
         ↓
4. Определение режима рынка → 5. Генерация прогнозов (N моделей × M методов)
         ↓
6. Агрегация консенсуса → 7. Сохранение в logs → 8. Оценка результатов (через 3ч)
```

### Компоненты бизнес-логики

**`forecast_runner.py`** — оркестратор процесса
- Загружает активные тикеры из `settings`
- Последовательно вызывает: `data_loader` → `indicators` → `market_regime` → `multi_model_forecaster` → `consensus` → `order_manager` (опционально)
- Создаёт `forecast_run` запись для аудита
- Сохраняет результаты в `logs` и `consensus`

**`forecast_engine.py`** — генерация прогнозов
- Формирует промпт по шаблону метода + данные тикера
- Отправляет в OpenRouter с таймаутом и retry-логикой
- Парсит ответ: извлекает `action` (LONG/SHORT/HOLD), `target_price`, `confidence`, `reasoning`
- Обрабатывает ошибки модели (fallback на HOLD при невалидном ответе)

**`multi_model_forecaster.py`** — масштабирование
- Для каждого активного провайдера (модели) запускает все активные методы анализа
- Параллельные запросы с `asyncio.gather()` и семафором (лимит конкурентности)
- Результат: список сигналов с метаданными модели и метода

**`consensus.py`** — агрегация сигналов
- Группирует сигналы по тикеру
- **Двухуровневая точность:** `method_stats` (по методу) и `model_stats` (по AI-модели); `model_stats` имеет приоритет для `ema_accuracy`
- **Формула веса:** `weight = raw_confidence × win_rate × ema_weight`
  - `raw_confidence` — 0..1 (нормализованная уверенность модели, не калиброванная)
  - `ema_weight = max(0.3, min(1.5, ema_accuracy × 2))` — исторический EMA accuracy
  - `win_rate` — доля прибыльных прогнозов метода за последние 30 дней
- **Calibrated confidence** — рассчитывается для аналитики (`calibration_factor = ema_acc / 0.5`), НЕ влияет на вес (предотвращает двойной счёт)
- **`total_weight`** — накапливается только для не-filtered прогнозов (после `continue`)
- Финальный сигнал: доминирующее направление, медианная цель/стоп
- Фильтры: аномалии (>15% от цены), разногласие (minority >40%), ожидаемая ценность (`expected_r < 0.5`)
- `exit_successful` сохраняется в `consensus`: `1` = target first, `0` = stop first, `NULL` = open

**`market_regime.py`** — адаптация к рынку
- ADX > 25 + цена > MA → трендовые методы (`momentum_trend`, `breakout`)
- ADX > 25 + цена < MA → трендовые методы с акцентом на SHORT
- ADX < 25 + выравнивание MA → контртрендовые (`mean_reversion`, `range_trading`)

**`actuals_evaluator.py`** — обратная связь
- Периодически (каждые 10 мин) проверяет записи `logs` со статусом `NEW` и возрастом > 3 часов
- Загружает фактические цены через `data_loader`
- Рассчитывает: PnL (фактическая прибыль/убыток), точность направления, отклонение цели
- Обновляет запись: статус → `EVALUATED`, сохраняет метрики

### Правила принятия решений

| Условие | Действие |
|---------|----------|
| Консенсус confidence < 0.6 | Отклонить сигнал (не сохранять в logs) |
| Все модели дают HOLD | Нет сигнала, запись не создаётся |
| Разнонаправленные сигналы (LONG vs SHORT) | Выбирается направление с большей суммарной уверенностью |
| PnL оценки < -2% после 3ч | Помечается как неудачный прогноз (для аналитики) |

### Поток данных

```
Yahoo Finance / Alpha Vantage / Finnhub
              ↓
         price_data (SQLite)
              ↓
    indicators.py → indicators (SQLite)
              ↓
    market_regime.py + forecast_engine.py
              ↓
         logs (SQLite) + consensus (SQLite)
              ↓
    actuals_evaluator.py (через 3ч)
              ↓
    Оценка точности → обновление logs
```

---

## Известные нюансы и ограничения

- `~$trading_robot.xlsx` — временный файл Excel (Lock-файл Office), не коммитится
- `.client.pid` / `.server.pid` — PID-файлы для управления процессами через bat-скрипты
- `venv_client/` и `venv_server/` — раздельные виртуальные окружения для клиента и сервера

---

## Ключевые архитектурные принципы

**Атомарность ордеров.** Bracket-группа неделима. При частичном исполнении Entry сначала отменяется остаток лимитной заявки — только потом выставляется закрывающий Market-ордер. Последовательность строго обязательна.

**Приоритет стопа при оценке.** Если за интервал оценки цена касалась и `stop_loss`, и `target_price`, результат всегда фиксируется как убыток. Это инвариант, не конфигурируемый через `config`.

**EMA быстрее реагирует на деградацию.** Веса провайдеров рассчитываются через EMA с α=0.2, а не скользящее среднее, чтобы система адаптировалась к внешним изменениям модели быстрее, чем за 30 дней.

**Heartbeat как защита от «тихих» сбоев.** Потеря связи с IB без активных ордеров незаметна. Heartbeat обнаруживает деградацию за 30 секунд и логирует состояние в `heartbeat_log`. Для QUEUED-ордеров автоматический переход в PAUSED и обратно не реализован — ордера остаются в QUEUED до истечения `ORDER_QUEUE_MAX_AGE_HOURS`.

**Единственный источник капитала.** `NetLiquidation` из IB — единственная база для расчётов. `BuyingPower` не используется как основа.

**`MANUAL_INTERVENTION_REQUIRED` — единственный сценарий для уведомлений.** Все остальные ошибки система обрабатывает автоматически. Уведомление отправляется только когда на счету есть неуправляемый риск (орфан-позиция).

---

## Технический долг

| Дата | Пункт | Статус |
|------|-------|--------|
| 2026-05-06 | **Google Sheets (`gspread`) удалён** — legacy-зависимость с устаревшей oauth2client; код (`save_price_data_to_sheet`) и документация очищены | ✅ Выполнено |
| 2026-05-07 | **`main_excel.py` удалён** — заменён на `forecast_runner.py`; ARCHITECTURE.md и README.md синхронизированы | ✅ Выполнено |
| 2026-05-07 | **Файлы структурированы** — тесты в `scripts/tests/`, документация в `docs/`, корень очищен | ✅ Выполнено |

1. **PAUSED статус для ордеров.** Не реализована логика: (a) перевод QUEUED в PAUSED при потере связи с IB, (b) автоматический resubmit в QUEUED при восстановлении, (c) проверка актуальности цен перед resubmit после длительной паузы. Текущее поведение: QUEUED-ордера expire по `ORDER_QUEUE_MAX_AGE_HOURS` (задача `expire_queued_orders` в scheduler.py), ручной resubmit через API `/orders/submit`.

2. **`forecast_runner.py` — God Object.** `process_ticker()` делает загрузку данных, индикаторы, прогнозы, консенсус, ордера (~120 строк). Нужно декомпозировать на pipeline-стадии.

3. **Дублирование `sys.path` манипуляций.** `forecast_runner.py`, `robot.py`, `scheduler.py`, `api.py` — все содержат идентичные блоки `sys.path.insert`. Нужен единый `bootstrap.py` или `PYTHONPATH` в скриптах запуска.

4. **Ad-hoc SQL в `forecast_runner.py` и `scheduler.py`.** Прямые запросы к SQLite вместо методов `sqlite_manager.py`. Нарушает инкапсуляцию и дублирует логику.

5. **Разделение `robot.py` и `forecast_runner.py`.** `robot.py` — thin wrapper вокруг `forecast_runner.py`. Можно объединить или сделать `robot.py` чистым FastAPI-адаптером.

6. **Отсутствие централизованного DI-контейнера.** `db_manager` передаётся через аргументы, но часто создаётся заново внутри функций (`SQLiteManager(db_file)`). Нужен `AppContext` или `Container`.

7. **Типизация.** Большинство core-модулей не используют type hints. Усложняет рефакторинг и поиск ошибок.

---
